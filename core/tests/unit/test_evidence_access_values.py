"""Constrained, resource-free values for the normalized evidence read boundary."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import FrozenInstanceError, replace
from inspect import iscoroutinefunction
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from dutchmate_core import evidence_access as boundary
from dutchmate_core.adapters.sqlite_evidence import SqliteEvidenceJournal
from dutchmate_core.evidence import (
    EvidenceCursor,
    EvidencePage,
    EvidencePageOutcome,
    EvidenceRetrievalRequest,
    JournalFailure,
    JournalFailureKind,
    JournalOperation,
)
from dutchmate_core.model import EvidenceReference, SessionId, SessionPolicy
from dutchmate_core.runtime import RunId

if TYPE_CHECKING:
    from dutchmate_core.evidence_access import EvidenceReadPort, OwnedEvidenceReadPort


def _policy() -> SessionPolicy:
    return SessionPolicy(100, 10000, 1000, 100, 25, 2000)


async def _never_open() -> OwnedEvidenceReadPort:
    raise AssertionError("constructing read values must not acquire resources")


@contextmanager
def _scope() -> Iterator[None]:
    yield


@asynccontextmanager
async def _async_scope() -> AsyncIterator[None]:
    yield


def test_ports_narrow_live_reads_and_add_only_owned_terminal_close() -> None:
    live = boundary.EvidenceReadPort
    owned = boundary.OwnedEvidenceReadPort
    assert iscoroutinefunction(live.resolve_record)
    assert iscoroutinefunction(live.retrieve)
    assert isinstance(live.session_id, property) and isinstance(live.policy, property)
    for name in ("append", "open", "close"):
        assert not hasattr(live, name)
    assert iscoroutinefunction(owned.close)
    assert not hasattr(owned, "append") and not hasattr(owned, "open")


@pytest.mark.asyncio
async def test_existing_journal_satisfies_live_port_without_another_reader(
    tmp_path: Path,
) -> None:
    journal = await SqliteEvidenceJournal.create(tmp_path / "live.sqlite3", _policy())
    try:
        reader: EvidenceReadPort = journal
        access = boundary.PreparedEvidenceAccess(
            journal.session_id, journal.policy, live_reader=reader
        )
        assert access.live_reader is journal and access.terminal_opener is None
        page = await reader.retrieve(
            EvidenceRetrievalRequest(journal.session_id, 1, 2000)
        )
        missing = await reader.resolve_record(EvidenceReference(journal.session_id, 0))
        assert page.outcome is EvidencePageOutcome.COMPLETE and page.records == ()
        assert missing.outcome is EvidencePageOutcome.NOT_FOUND
        # This test owns the recorder; the narrowed port grants no close operation.
    finally:
        await journal.close()


def test_terminal_only_access_construction_never_calls_opener() -> None:
    access = boundary.PreparedEvidenceAccess(
        SessionId("opaque session"), _policy(), terminal_opener=_never_open
    )
    assert access.live_reader is None and access.terminal_opener is _never_open


def test_access_requires_at_least_one_read_capability() -> None:
    with pytest.raises(ValueError, match="capability"):
        boundary.PreparedEvidenceAccess(SessionId("session"), _policy())


@pytest.mark.parametrize(
    "field", ["session_id", "policy", "live_reader", "terminal_opener"]
)
def test_access_rejects_unvalidated_fields(field: str) -> None:
    kwargs: dict[str, Any] = {
        "session_id": SessionId("session"),
        "policy": _policy(),
        "terminal_opener": _never_open,
    }
    kwargs[field] = object()
    with pytest.raises(TypeError):
        boundary.PreparedEvidenceAccess(**kwargs)


@pytest.mark.parametrize("field", ["session_id", "policy"])
@pytest.mark.asyncio
async def test_live_access_cannot_claim_another_session_or_policy(
    tmp_path: Path, field: str
) -> None:
    journal = await SqliteEvidenceJournal.create(tmp_path / "source.sqlite3", _policy())
    try:
        kwargs: dict[str, Any] = {
            "session_id": journal.session_id,
            "policy": journal.policy,
            "live_reader": journal,
            "terminal_opener": _never_open,
        }
        kwargs[field] = (
            SessionId("another-session")
            if field == "session_id"
            else replace(journal.policy, max_retained_records=101)
        )
        with pytest.raises(ValueError, match=field):
            boundary.PreparedEvidenceAccess(**kwargs)
    finally:
        await journal.close()


@pytest.mark.parametrize(
    "field", ["session_id", "policy", "live_reader", "terminal_opener"]
)
@pytest.mark.parametrize("action", ["assign", "delete"])
def test_prepared_read_access_is_immutable(field: str, action: str) -> None:
    access = boundary.PreparedEvidenceAccess(
        SessionId("session"), _policy(), terminal_opener=_never_open
    )
    with pytest.raises(FrozenInstanceError):
        if action == "assign":
            setattr(access, field, None)
        else:
            delattr(access, field)
    assert access.session_id == SessionId("session")
    assert access.policy == _policy()
    assert access.live_reader is None and access.terminal_opener is _never_open


@pytest.mark.parametrize("outcome", list(EvidencePageOutcome))
def test_run_page_preserves_normalized_report_without_recomputing_it(
    outcome: EvidencePageOutcome,
) -> None:
    session = SessionId("session")
    page = EvidencePage(
        (),
        1,
        None,
        None,
        None,
        outcome,
        True,
        EvidenceCursor(session, 0, None, 1, 0),
        0,
        100,
    )
    report = boundary.RunEvidencePage(RunId("run"), session, page)
    assert report.page is page and report.session_id is session
    assert report.run_id == RunId("run")
    assert report.page.outcome is outcome
    assert report.page.truncated and report.page.next_record_required_bytes == 100
    for field in ("run_id", "session_id", "page"):
        with pytest.raises(FrozenInstanceError):
            setattr(report, field, None)


@pytest.mark.parametrize("field", ["run_id", "session_id", "page"])
def test_run_page_rejects_unnormalized_identity_or_report(field: str) -> None:
    kwargs: dict[str, Any] = {
        "run_id": RunId("run"),
        "session_id": SessionId("session"),
        "page": EvidencePage(
            (), 0, None, None, None, EvidencePageOutcome.COMPLETE, False, None, 0, None
        ),
    }
    kwargs[field] = object()
    with pytest.raises(TypeError, match=field):
        boundary.RunEvidencePage(**kwargs)


@pytest.mark.parametrize(
    "kind",
    [
        "no_associated_session",
        "session_not_associated",
        "read_unavailable",
        "source_changed",
        "read_capacity",
    ],
)
@pytest.mark.parametrize("scope", ["sync", "async"])
@pytest.mark.asyncio
async def test_read_rejection_keeps_fixed_kind_through_exception_transport(
    kind: boundary.EvidenceReadRejectedKind,
    scope: str,
) -> None:
    failure = boundary.EvidenceReadRejected(kind)
    failure.add_note("scope settled")
    with pytest.raises(boundary.EvidenceReadRejected) as caught:
        if scope == "sync":
            with _scope():
                raise failure
        else:
            async with _async_scope():
                raise failure
    assert caught.value is failure
    assert failure.kind == kind and str(failure) == kind
    assert failure.__traceback__ is not None and failure.__notes__ == ["scope settled"]
    with pytest.raises(FrozenInstanceError):
        failure.kind = "read_capacity"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        del failure.kind


@pytest.mark.parametrize("kind", [None, 1, "unknown", RuntimeError("private")])
def test_read_rejection_rejects_noncontract_categories(kind: object) -> None:
    with pytest.raises(TypeError, match="kind"):
        boundary.EvidenceReadRejected(cast("boundary.EvidenceReadRejectedKind", kind))


@pytest.mark.parametrize("primary_kind", ["journal", "rejection"])
@pytest.mark.parametrize("confirmed", [False, True])
@pytest.mark.parametrize("scope", ["sync", "async"])
@pytest.mark.asyncio
async def test_open_failure_preserves_primary_and_actual_close_certainty(
    primary_kind: str,
    confirmed: bool,
    scope: str,
) -> None:
    primary = (
        JournalFailure(JournalOperation.OPEN, JournalFailureKind.IO_FAILURE, "private")
        if primary_kind == "journal"
        else boundary.EvidenceReadRejected("source_changed")
    )
    failure = boundary.EvidenceSourceOpenFailure(primary, confirmed)
    cause = OSError("raw storage detail")
    failure.__context__ = cause
    failure.add_note("open cleanup attempted")
    with pytest.raises(boundary.EvidenceSourceOpenFailure) as caught:
        if scope == "sync":
            with _scope():
                raise failure from cause
        else:
            async with _async_scope():
                raise failure from cause
    assert caught.value is failure
    assert failure.primary is primary and failure.reader_close_confirmed is confirmed
    assert failure.__cause__ is cause and failure.__traceback__ is not None
    assert "private" not in str(failure) and "raw storage" not in str(failure)
    for field in ("primary", "reader_close_confirmed"):
        with pytest.raises(FrozenInstanceError):
            setattr(failure, field, None)
        with pytest.raises(FrozenInstanceError):
            delattr(failure, field)


@pytest.mark.parametrize("primary", [None, "private", OSError("raw")])
def test_open_failure_requires_normalized_primary(primary: object) -> None:
    with pytest.raises(TypeError, match="primary"):
        boundary.EvidenceSourceOpenFailure(
            cast("JournalFailure | boundary.EvidenceReadRejected", primary), True
        )


@pytest.mark.parametrize("confirmed", [0, 1, None, "true"])
def test_open_failure_requires_exact_boolean_close_certainty(confirmed: object) -> None:
    primary = JournalFailure(JournalOperation.OPEN, JournalFailureKind.IO_FAILURE)
    with pytest.raises(TypeError, match="boolean"):
        boundary.EvidenceSourceOpenFailure(primary, cast("bool", confirmed))
