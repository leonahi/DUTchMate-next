"""008 T015 RED: immutable native targets and request-owned read-only SQLite.

Provisional adapter-private seam (not HTTP/CLI/application API):
 capture_terminal_target(path, *, session_id, policy) -> immutable target or None;
 await open_terminal_reader(target) -> existing OwnedEvidenceReadPort.
Tests observe real SQLite/native boundaries and existing003 results. They never
implement a terminal reader, selection algorithm, owner cleanup latch or fallback.
"""

import asyncio
import errno
import gc
import hashlib
import importlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import weakref
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, fields, is_dataclass, replace
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
import pytest_asyncio

from dutchmate_core import evidence, evidence_access, model
from dutchmate_core.adapters import sqlite_evidence
from tests.contract.test_observation_runtime import _profile
from tests.fakes import BACKEND_FIXTURE_FACTORIES

_MODULE = "dutchmate_core.adapters.terminal_evidence"
_DETAIL = "private-terminal-file-SQL-resource-detail"


def _adapter() -> Any:
    try:
        return importlib.import_module(_MODULE)
    except ModuleNotFoundError as error:
        if error.name == _MODULE:
            pytest.fail(
                "T016 terminal evidence adapter is not implemented", pytrace=False
            )
        raise


def _capture(
    api: Any, path: Path, session: model.SessionId, policy: model.SessionPolicy
) -> Any:
    operation = getattr(api, "capture_terminal_target", None)
    assert callable(operation), "private native target capture is absent"
    return operation(path, session_id=session, policy=policy)


async def _open(api: Any, target: Any) -> Any:
    operation = getattr(api, "open_terminal_reader", None)
    assert callable(operation), "private terminal reader opener is absent"
    return await asyncio.wait_for(operation(target), 3)


def _primary(
    error: Exception,
) -> evidence.JournalFailure | evidence_access.EvidenceReadRejected:
    if isinstance(error, evidence_access.EvidenceSourceOpenFailure):
        return error.primary
    assert isinstance(
        error, (evidence.JournalFailure, evidence_access.EvidenceReadRejected)
    ), type(error)
    return error


def _files(root: Path) -> dict[str, tuple[str, int]]:
    return {
        path.name: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mode)
        for path in root.iterdir()
        if path.is_file()
    }


@dataclass
class ClosedJournal:
    path: Path
    session: model.SessionId
    policy: model.SessionPolicy
    page: evidence.EvidencePage
    record: evidence.EvidencePage
    records: tuple[model.EvidenceRecord, ...]


async def _seed(
    path: Path, backend_index: int, *, retained: int = 100
) -> ClosedJournal:
    policy = replace(_profile().session_policy, max_retained_records=retained)
    descriptor = BACKEND_FIXTURE_FACTORIES[backend_index]().connection.descriptor
    provenance = model.SegmentProvenance(
        model.ConnectionInstanceId("terminal-connection"),
        model.SegmentId("terminal-segment"),
        descriptor.capabilities,
        descriptor.backend_observation_timestamp_domain,
        descriptor.loss_observability,
        model.PersistedConnectionProvenance(
            model.ConnectionProvenanceSnapshot(
                1,
                "opaque/terminal-fixture",
                37,
                (
                    model.ProvenanceField("count", 7),
                    model.ProvenanceField("flag", False),
                    model.ProvenanceField("text", "opaque-é"),
                    model.ProvenanceField("unknown", None),
                ),
            )
        ),
    )
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, policy)
    accepted: list[model.EvidenceRecord] = []
    try:
        session = journal.session_id
        accepted.append(
            await journal.append(evidence.PendingSegmentStartedEvidence(provenance))
        )
        for timestamp, payload in ((11, bytes(range(256))), (20, b"\0\xff\xfe\r\n")):
            accepted.append(
                await journal.append(
                    evidence.PendingRxBytesEvidence(
                        provenance.connection_id,
                        provenance.segment_id,
                        payload,
                        model.BackendObservationTimestamp(
                            provenance.backend_observation_timestamp_domain.domain_id,
                            timestamp,
                        ),
                    )
                )
            )
        if isinstance(provenance.loss_observability, model.ObserverReportsUartLoss):
            loss = provenance.loss_observability
            accepted.append(
                await journal.append(
                    evidence.PendingObserverLossEvidence(
                        provenance.connection_id,
                        provenance.segment_id,
                        loss.observer_id,
                        loss.scope,
                        model.ObserverLossCause.OVERFLOW,
                        3,
                        model.BackendObservationTimestamp(
                            provenance.backend_observation_timestamp_domain.domain_id,
                            25,
                        ),
                    )
                )
            )
        accepted.append(
            await journal.append(
                evidence.PendingSegmentEndedEvidence(
                    provenance.connection_id,
                    provenance.segment_id,
                    model.SegmentEndReason.EXPLICIT_STOP,
                )
            )
        )
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(session, 10, 16384)
        )
        single = await journal.resolve_record(model.EvidenceReference(session, 1))
    finally:
        await journal.close()
    return ClosedJournal(path, session, policy, page, single, tuple(accepted))


@pytest_asyncio.fixture(params=[0, 1], ids=["basic", "enhanced-shaped"])
async def closed(tmp_path: Path, request: pytest.FixtureRequest) -> ClosedJournal:
    return await _seed(tmp_path / "journal spaced-é ?#%.sqlite3", int(request.param))


class ConnectionProbe:
    """Real SQLite connection observer with only boundary faults/gates substituted."""

    def __init__(self, patch: pytest.MonkeyPatch) -> None:
        self.connections: list[Any] = []
        self.uris: list[tuple[str, bool]] = []
        self.statements: list[tuple[str, bool, int]] = []
        self.close_calls = 0
        self.closed: list[Any] = []
        self.threads: list[int] = []
        self.after_connect: Callable[[], object] | None = None
        self.connect_failure: Exception | None = None
        self.read_failure: Exception | None = None
        self.close_failure: Exception | None = None
        self.refuse_query_only = False
        self.block: str | None = None
        self.entered = asyncio.Event()
        self.release = threading.Event()
        loop = asyncio.get_running_loop()
        connect = sqlite3.connect
        probe = self

        class Connection:
            def __init__(self, raw: sqlite3.Connection) -> None:
                self.raw = raw

            def execute(self, sql: str, parameters: Any = ()) -> sqlite3.Cursor:
                probe.threads.append(threading.get_ident())
                upper = " ".join(sql.upper().split())
                if upper.startswith(
                    (
                        "UPDATE ",
                        "INSERT ",
                        "DELETE ",
                        "CREATE ",
                        "DROP ",
                        "ALTER ",
                        "VACUUM",
                        "REPLACE ",
                        "BEGIN IMMEDIATE",
                        "BEGIN EXCLUSIVE",
                    )
                ):
                    pytest.fail("terminal reader attempted writable SQL")
                if (
                    upper.startswith("PRAGMA")
                    and "=" in upper
                    and any(
                        name in upper
                        for name in (
                            "JOURNAL_MODE",
                            "MAX_PAGE_COUNT",
                            "USER_VERSION",
                            "APPLICATION_ID",
                            "PAGE_SIZE",
                        )
                    )
                ):
                    pytest.fail("terminal reader changed journal configuration")
                if (
                    probe.refuse_query_only
                    and upper.startswith("PRAGMA QUERY_ONLY")
                    and "=" in upper
                ):
                    return self.raw.execute("PRAGMA query_only")
                if upper.startswith("SELECT") and "EVIDENCE_RECORDS" in upper:
                    probe.gate("read")
                    if probe.read_failure is not None:
                        raise probe.read_failure
                return self.raw.execute(sql, parameters)

            def close(self) -> None:
                probe.threads.append(threading.get_ident())
                probe.close_calls += 1
                probe.gate("close")
                self.raw.close()
                probe.closed.append(self)
                # Error after native close lets the harness avoid leaks while
                # application code has no successful close acknowledgment.
                if probe.close_failure is not None:
                    raise probe.close_failure

            def __getattr__(self, name: str) -> Any:
                return getattr(self.raw, name)

        def opened(database: Any, *args: Any, **kwargs: Any) -> Any:
            self.threads.append(threading.get_ident())
            self.uris.append((str(database), bool(kwargs.get("uri", False))))
            if self.connect_failure is not None:
                raise self.connect_failure
            raw = connect(database, *args, **kwargs)
            connection = Connection(raw)
            self.connections.append(connection)
            raw.set_trace_callback(
                lambda sql: self.statements.append(
                    (sql, raw.in_transaction, threading.get_ident())
                )
            )
            self.gate("open")
            if self.after_connect is not None:
                self.after_connect()
            return connection

        def gate(kind: str) -> None:
            if self.block == kind:
                loop.call_soon_threadsafe(self.entered.set)
                if not self.release.wait(3):
                    raise AssertionError("test worker gate was not released")

        self.gate = gate
        patch.setattr(sqlite3, "connect", opened)
        for name, module in tuple(sys.modules.items()):
            if name.startswith("dutchmate_core.adapters") and module is not None:
                for key, value in tuple(vars(module).items()):
                    if value is connect:
                        patch.setattr(module, key, opened)

    def read_only(self, path: Path) -> None:
        assert len(self.connections) == len(self.uris) == 1
        uri, enabled = self.uris[0]
        assert enabled
        parsed = urlsplit(uri)
        assert (
            parsed.scheme == "file"
            and Path(unquote(parsed.path)).resolve() == path.resolve()
        )
        assert parse_qs(parsed.query).get("mode") == ["ro"]
        assert parse_qs(parsed.query).get("cache") == ["private"]
        assert "immutable" not in parse_qs(parsed.query) and "nolock" not in parse_qs(
            parsed.query
        )
        statements = [" ".join(sql.upper().split()) for sql, _, _ in self.statements]
        assert any(
            sql.startswith("PRAGMA QUERY_ONLY") and "=" in sql for sql in statements
        )
        assert any(sql == "PRAGMA QUERY_ONLY" for sql in statements)
        assert len([sql for sql in statements if sql.startswith("BEGIN")]) == 1
        # Full validation and selected rows must share the explicit read snapshot.
        validation = [
            (sql.upper(), transaction)
            for sql, transaction, _ in self.statements
            if " ".join(sql.upper().split()).startswith("SELECT")
            or "QUICK_CHECK" in sql.upper()
        ]
        assert validation and all(transaction for _, transaction in validation)
        assert any("SQLITE_SCHEMA" in sql for sql, _ in validation)
        assert any("SESSION_METADATA" in sql for sql, _ in validation)
        assert any("EVIDENCE_RECORDS" in sql for sql, _ in validation)
        assert any("RETENTION_MARKER" in sql for sql, _ in validation)
        assert any(sql in {"ROLLBACK", "COMMIT", "END"} for sql in statements)
        assert self.close_calls == 1 and self.closed == self.connections
        assert len(set(self.threads)) == 1 and self.threads[0] != threading.get_ident()


def _forbid_writable(patch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> Any:
        pytest.fail(
            "terminal retrieval cannot use writable journal/open/recovery/repair"
        )

    for name in ("open", "create", "append"):
        patch.setattr(sqlite_evidence.SqliteEvidenceJournal, name, forbidden)
    for name in (
        "_force_rollback_recovery",
        "_prove_writable_connection",
        "_configure_writable_connection",
        "_establish_physical_ceiling",
        "_apply_max_page_count",
    ):
        patch.setattr(sqlite_evidence, name, forbidden)
    for name in ("chmod", "fchmod", "unlink", "remove", "mkdir"):
        patch.setattr(os, name, forbidden)
    patch.setattr(Path, "chmod", forbidden)
    patch.setattr(Path, "unlink", forbidden)


@pytest.mark.asyncio
async def test_target_is_immutable_metadata_only_with_no_recorder_connection_or_fd(
    closed: ClosedJournal,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    assert target is not None and is_dataclass(target)
    assert fields(target)
    for field in fields(target):
        with pytest.raises((FrozenInstanceError, AttributeError)):
            setattr(target, field.name, object())

    def metadata(value: Any) -> None:
        assert not isinstance(
            value,
            (
                sqlite3.Connection,
                sqlite_evidence.SqliteEvidenceJournal,
                asyncio.Future,
                io.IOBase,
            ),
        )
        if is_dataclass(value):
            for field in fields(value):
                metadata(getattr(value, field.name))
        elif isinstance(value, (tuple, list)):
            for member in value:
                metadata(member)
        else:
            assert isinstance(value, (Path, str, int, type(None))), type(value)

    metadata(target)


@pytest.mark.asyncio
async def test_terminal_reference_preserves_exact_binary_and_closes_one_private_worker(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    before = _files(closed.path.parent)
    _forbid_writable(monkeypatch)
    probe = ConnectionProbe(monkeypatch)
    reader = await _open(api, target)
    try:
        assert reader.session_id == closed.session and reader.policy == closed.policy
        assert not hasattr(reader, "append") and not hasattr(reader, "create")
        report = await reader.resolve_record(model.EvidenceReference(closed.session, 1))
        assert report == closed.record
        assert isinstance(report.records[0], model.RxBytesEvidence)
        assert report.records[0].payload == bytes(range(256))
    finally:
        await reader.close()
    probe.read_only(closed.path)
    assert _files(closed.path.parent) == before


@pytest.mark.parametrize("records,charged", [(10, 16384), (1, 16384), (10, 1)])
@pytest.mark.asyncio
async def test_terminal_pages_reuse003_order_provenance_snapshot_and_byte_shortage(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
    records: int,
    charged: int,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    probe = ConnectionProbe(monkeypatch)
    reader = await _open(api, target)
    try:
        page = await reader.retrieve(
            evidence.EvidenceRetrievalRequest(closed.session, records, charged)
        )
        assert page.snapshot_end_exclusive == len(closed.records)
        assert page.outcome is evidence.EvidencePageOutcome.COMPLETE
        if charged == 1:
            assert page.records == () and page.truncated and page.charged_bytes == 0
            assert (
                page.next_record_required_bytes is not None
                and page.next_record_required_bytes > 1
            )
            assert page.continuation == evidence.EvidenceCursor(
                closed.session, 0, None, len(closed.records), 0
            )
        elif records == 1:
            assert page.records == closed.records[:1] and page.truncated
        else:
            assert page == closed.page
    finally:
        await reader.close()
    probe.read_only(closed.path)


@pytest.mark.asyncio
async def test_each_terminal_request_uses_fresh_connection_and_returns_resource_free_cursor(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    probe = ConnectionProbe(monkeypatch)
    first = await _open(api, target)
    page = await first.retrieve(
        evidence.EvidenceRetrievalRequest(closed.session, 1, 16384)
    )
    await first.close()
    assert probe.closed == probe.connections
    second = await _open(api, target)
    try:
        continued = await second.retrieve(
            evidence.EvidenceRetrievalRequest(
                closed.session, 10, 16384, page.continuation
            )
        )
        assert continued.records == closed.records[
            1:
        ] and continued.snapshot_end_exclusive == len(closed.records)
    finally:
        await second.close()
    assert len(probe.connections) == len(probe.closed) == 2
    assert first is not second


@pytest.mark.asyncio
async def test_terminal_retention_reports_expired_and_partial_without_repair(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    seed = await _seed(closed.path.with_name("retained.sqlite3"), 1, retained=2)
    target = _capture(api, seed.path, seed.session, seed.policy)
    _forbid_writable(monkeypatch)
    reader = await _open(api, target)
    try:
        assert (
            await reader.retrieve(
                evidence.EvidenceRetrievalRequest(seed.session, 10, 16384)
            )
            == seed.page
        )
    finally:
        await reader.close()
    reader = await _open(api, target)
    try:
        expired = await reader.resolve_record(model.EvidenceReference(seed.session, 1))
        assert (
            expired.outcome is evidence.EvidencePageOutcome.EXPIRED
            and expired.records == ()
        )
        assert expired.retention_marker == seed.page.retention_marker
    finally:
        await reader.close()


@pytest.mark.parametrize("change", ["missing", "replacement"])
@pytest.mark.asyncio
async def test_native_identity_is_checked_before_open_without_path_fallback(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    if change == "missing":
        closed.path.unlink()
    else:
        replacement = closed.path.with_name("replacement.sqlite3")
        shutil.copyfile(closed.path, replacement)
        replacement.replace(closed.path)
    before = _files(closed.path.parent)
    probe = ConnectionProbe(monkeypatch)
    with pytest.raises(
        (
            evidence.JournalFailure,
            evidence_access.EvidenceReadRejected,
            evidence_access.EvidenceSourceOpenFailure,
        )
    ) as caught:
        await _open(api, target)
    failure = _primary(caught.value)
    if change == "missing":
        assert (
            isinstance(failure, evidence.JournalFailure)
            and failure.kind is evidence.JournalFailureKind.JOURNAL_MISSING
        )
    else:
        assert (
            isinstance(failure, evidence_access.EvidenceReadRejected)
            and failure.kind == "source_changed"
        )
    assert probe.connections == [] and _files(closed.path.parent) == before


@pytest.mark.asyncio
async def test_native_replacement_after_connect_is_rejected_and_partial_reader_closes(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    replacement = closed.path.with_name("replacement.sqlite3")
    shutil.copyfile(closed.path, replacement)
    probe = ConnectionProbe(monkeypatch)
    probe.after_connect = lambda: replacement.replace(closed.path)
    with pytest.raises(evidence_access.EvidenceSourceOpenFailure) as caught:
        await _open(api, target)
    assert isinstance(caught.value.primary, evidence_access.EvidenceReadRejected)
    assert (
        caught.value.primary.kind == "source_changed"
        and caught.value.reader_close_confirmed is True
    )
    assert probe.close_calls == 1 and probe.closed == probe.connections


@pytest.mark.parametrize(
    "field_name", [field.name for field in fields(model.SessionPolicy)]
)
@pytest.mark.asyncio
async def test_every_captured_policy_field_is_checked_exactly(
    closed: ClosedJournal,
    field_name: str,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    connection = sqlite3.connect(closed.path)
    try:
        connection.execute(
            f"UPDATE session_metadata SET {field_name} = {field_name} + 1"
        )
        connection.commit()
    finally:
        connection.close()
    before = _files(closed.path.parent)
    with pytest.raises(
        (
            evidence_access.EvidenceReadRejected,
            evidence_access.EvidenceSourceOpenFailure,
        )
    ) as caught:
        await _open(api, target)
    failure = _primary(caught.value)
    assert (
        isinstance(failure, evidence_access.EvidenceReadRejected)
        and failure.kind == "source_changed"
    )
    assert _files(closed.path.parent) == before


@pytest.mark.asyncio
async def test_expected_session_mismatch_stays_journal_session_mismatch(
    closed: ClosedJournal,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, model.SessionId("other-session"), closed.policy)
    with pytest.raises(
        (evidence.JournalFailure, evidence_access.EvidenceSourceOpenFailure)
    ) as caught:
        await _open(api, target)
    failure = _primary(caught.value)
    assert (
        isinstance(failure, evidence.JournalFailure)
        and failure.kind is evidence.JournalFailureKind.SESSION_MISMATCH
    )


_CORRUPTIONS = [
    ("PRAGMA application_id = 1", evidence.JournalFailureKind.INCOMPATIBLE_APPLICATION),
    (
        "PRAGMA user_version = 2",
        evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION,
    ),
    (
        "UPDATE evidence_records SET record_version = 2 WHERE sequence = 1",
        evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION,
    ),
    ("DROP TABLE retention_marker", evidence.JournalFailureKind.CORRUPT_JOURNAL),
    (
        "ALTER TABLE evidence_records ADD COLUMN unexpected TEXT",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "UPDATE session_metadata SET retained_record_count = retained_record_count + 1",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "UPDATE session_metadata SET retained_charged_bytes = retained_charged_bytes + 1",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "DELETE FROM evidence_records WHERE sequence = 1",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "UPDATE evidence_records SET metadata_json = X'7B7D' WHERE sequence = 2",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "UPDATE evidence_records SET payload = X'FF' WHERE sequence = 2",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "UPDATE evidence_records SET timestamp_endpoint_json = X'7B7D' WHERE sequence = 2",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
]


@pytest.mark.parametrize("sql,kind", _CORRUPTIONS)
@pytest.mark.asyncio
async def test_full_v1_validation_rejects_unselected_corruption_without_source_writes(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
    sql: str,
    kind: evidence.JournalFailureKind,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    connection = sqlite3.connect(closed.path)
    try:
        connection.execute(sql)
        connection.commit()
    finally:
        connection.close()
    before = _files(closed.path.parent)
    _forbid_writable(monkeypatch)
    probe = ConnectionProbe(monkeypatch)
    with pytest.raises(
        (evidence.JournalFailure, evidence_access.EvidenceSourceOpenFailure)
    ) as caught:
        reader = await _open(api, target)
        try:
            await reader.resolve_record(model.EvidenceReference(closed.session, 0))
        finally:
            await reader.close()
    failure = _primary(caught.value)
    assert isinstance(failure, evidence.JournalFailure) and failure.kind is kind
    assert _files(closed.path.parent) == before and probe.closed == probe.connections


@pytest.mark.asyncio
async def test_incompatible_provenance_envelope_is_not_rewritten_or_hidden(
    closed: ClosedJournal,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    connection = sqlite3.connect(closed.path)
    try:
        kind, metadata, old_charge = connection.execute(
            "SELECT record_kind, metadata_json, charged_bytes FROM evidence_records WHERE sequence = 0"
        ).fetchone()
        value = json.loads(metadata)
        value["connection_provenance"]["envelope_version"] = 2
        encoded = json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
        charge = 16 + len(kind.encode()) + len(encoded)
        connection.execute(
            "UPDATE evidence_records SET metadata_json = ?, charged_bytes = ? WHERE sequence = 0",
            (encoded, charge),
        )
        connection.execute(
            "UPDATE session_metadata SET retained_charged_bytes = retained_charged_bytes + ?",
            (charge - old_charge,),
        )
        connection.commit()
    finally:
        connection.close()
    before = _files(closed.path.parent)
    with pytest.raises(
        (evidence.JournalFailure, evidence_access.EvidenceSourceOpenFailure)
    ) as caught:
        await _open(api, target)
    failure = _primary(caught.value)
    assert (
        isinstance(failure, evidence.JournalFailure)
        and failure.kind
        is evidence.JournalFailureKind.INCOMPATIBLE_PROVENANCE_ENVELOPE_VERSION
    )
    assert _files(closed.path.parent) == before


@pytest.mark.asyncio
async def test_query_only_must_be_verified_not_merely_requested(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    probe = ConnectionProbe(monkeypatch)
    probe.refuse_query_only = True
    with pytest.raises(evidence_access.EvidenceSourceOpenFailure) as caught:
        await _open(api, target)
    assert isinstance(caught.value.primary, evidence.JournalFailure)
    assert caught.value.reader_close_confirmed is True
    assert probe.close_calls == 1 and probe.closed == probe.connections


@pytest.mark.parametrize(
    "error,kind",
    [
        (
            PermissionError(errno.EACCES, _DETAIL),
            evidence.JournalFailureKind.PERMISSION_DENIED,
        ),
        (OSError(errno.EIO, _DETAIL), evidence.JournalFailureKind.IO_FAILURE),
        (sqlite3.DatabaseError(_DETAIL), evidence.JournalFailureKind.IO_FAILURE),
    ],
)
@pytest.mark.asyncio
async def test_connect_failures_are_normalized_without_creating_or_repairing_source(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    kind: evidence.JournalFailureKind,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    before = _files(closed.path.parent)
    probe = ConnectionProbe(monkeypatch)
    probe.connect_failure = error
    with pytest.raises(
        (evidence.JournalFailure, evidence_access.EvidenceSourceOpenFailure)
    ) as caught:
        await _open(api, target)
    failure = _primary(caught.value)
    assert isinstance(failure, evidence.JournalFailure) and failure.kind is kind
    assert failure.detail is None and _files(closed.path.parent) == before
    assert probe.connections == []


@pytest.mark.asyncio
async def test_partial_open_primary_survives_secondary_close_failure_with_uncertain_cleanup(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, model.SessionId("wrong-session"), closed.policy)
    probe = ConnectionProbe(monkeypatch)
    probe.close_failure = OSError(errno.EIO, _DETAIL)
    with pytest.raises(evidence_access.EvidenceSourceOpenFailure) as caught:
        await _open(api, target)
    assert isinstance(caught.value.primary, evidence.JournalFailure)
    assert caught.value.primary.kind is evidence.JournalFailureKind.SESSION_MISMATCH
    assert caught.value.reader_close_confirmed is False and probe.close_calls == 1


@pytest.mark.asyncio
async def test_read_and_close_faults_keep_their_original_normalized_operations(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    probe = ConnectionProbe(monkeypatch)
    reader = await _open(api, target)
    probe.read_failure = OSError(errno.EIO, _DETAIL)
    probe.close_failure = OSError(errno.EIO, "secondary-close-detail")
    with pytest.raises(evidence.JournalFailure) as read:
        await reader.retrieve(
            evidence.EvidenceRetrievalRequest(closed.session, 10, 16384)
        )
    assert read.value.operation is evidence.JournalOperation.RETRIEVE
    assert (
        read.value.kind is evidence.JournalFailureKind.IO_FAILURE
        and read.value.detail is None
    )
    with pytest.raises(evidence.JournalFailure) as close:
        await reader.close()
    assert (
        close.value.operation is evidence.JournalOperation.CLOSE
        and close.value.kind is evidence.JournalFailureKind.IO_FAILURE
    )
    assert probe.close_calls == 1


@pytest.mark.asyncio
async def test_close_only_failure_cannot_attest_successful_reader_settlement(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    probe = ConnectionProbe(monkeypatch)
    reader = await _open(api, target)
    assert (
        await reader.retrieve(
            evidence.EvidenceRetrievalRequest(closed.session, 10, 16384)
        )
        == closed.page
    )
    probe.close_failure = OSError(errno.EIO, _DETAIL)
    with pytest.raises(evidence.JournalFailure) as caught:
        await reader.close()
    assert (
        caught.value.operation is evidence.JournalOperation.CLOSE
        and caught.value.detail is None
    )
    assert probe.close_calls == 1


@pytest.mark.parametrize("stage", ["open", "read", "close"])
@pytest.mark.asyncio
async def test_cancellation_joins_submitted_native_work_before_reader_or_worker_release(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    probe = ConnectionProbe(monkeypatch)
    reader: Any = None
    if stage != "open":
        reader = await _open(api, target)
    probe.block = stage
    task = asyncio.create_task(
        _open(api, target)
        if stage == "open"
        else (
            reader.retrieve(
                evidence.EvidenceRetrievalRequest(closed.session, 10, 16384)
            )
            if stage == "read"
            else reader.close()
        )
    )
    try:
        await asyncio.wait_for(probe.entered.wait(), 2)
        task.cancel()
        task.cancel()
        # Event-loop checkpoints only; the worker gate is the ordering witness.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done(), "submitted work was abandoned on waiter cancellation"
        probe.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        if stage == "read":
            await reader.close()
        assert probe.close_calls == 1 and probe.closed == probe.connections
    finally:
        probe.release.set()
        await asyncio.gather(task, return_exceptions=True)
        if reader is not None and not probe.closed:
            await reader.close()


@pytest.mark.asyncio
async def test_failed_close_cannot_be_acknowledged_by_a_second_close_call(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    probe = ConnectionProbe(monkeypatch)
    reader = await _open(api, target)
    probe.close_failure = OSError(errno.EIO, _DETAIL)
    for _ in range(2):
        with pytest.raises(evidence.JournalFailure) as caught:
            await reader.close()
        assert caught.value.operation is evidence.JournalOperation.CLOSE
        assert caught.value.kind is evidence.JournalFailureKind.IO_FAILURE
        assert caught.value.detail is None
    assert probe.close_calls == 1


@pytest.mark.asyncio
async def test_cancellation_cannot_hide_uncertain_native_close(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    probe = ConnectionProbe(monkeypatch)
    reader = await _open(api, target)
    probe.close_failure = OSError(errno.EIO, _DETAIL)
    probe.block = "close"
    task = asyncio.create_task(reader.close())
    try:
        await asyncio.wait_for(probe.entered.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        probe.release.set()
        with pytest.raises(evidence.JournalFailure) as caught:
            await task
        assert caught.value.operation is evidence.JournalOperation.CLOSE
        assert caught.value.kind is evidence.JournalFailureKind.IO_FAILURE
        assert caught.value.detail is None
        assert probe.close_calls == 1
    finally:
        probe.release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_unexpected_connect_fault_does_not_assert_resource_cleanup(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    probe = ConnectionProbe(monkeypatch)
    probe.connect_failure = RuntimeError(_DETAIL)
    with pytest.raises(evidence_access.EvidenceSourceOpenFailure) as caught:
        await _open(api, target)
    assert caught.value.reader_close_confirmed is False
    assert isinstance(caught.value.primary, evidence.JournalFailure)
    assert caught.value.primary.operation is evidence.JournalOperation.OPEN
    assert caught.value.primary.kind is evidence.JournalFailureKind.IO_FAILURE
    assert caught.value.primary.detail is None


@pytest.mark.parametrize(
    "error", [PermissionError(errno.EACCES, _DETAIL), OSError(errno.EIO, _DETAIL)]
)
@pytest.mark.asyncio
async def test_identity_capture_failure_is_optional_and_leaves_live_recorder_usable(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
    error: OSError,
) -> None:
    api = _adapter()
    path = closed.path.with_name("live-capture.sqlite3")
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, closed.policy)
    stat = os.stat

    def failed(candidate: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if (
            isinstance(candidate, (str, bytes, Path))
            and Path(os.fsdecode(candidate)) == path
        ):
            raise error
        return stat(candidate, *args, **kwargs)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "stat", failed)
            assert _capture(api, path, journal.session_id, journal.policy) is None
        # No fake production composition or terminal fallback is introduced here.
        record = await journal.append(
            evidence.PendingRxBytesEvidence(
                model.ConnectionInstanceId("live-c"),
                model.SegmentId("live-s"),
                b"still-recording\0",
                model.BackendObservationTimestamp("live-domain", 0),
            )
        )
        assert (
            isinstance(record, model.RxBytesEvidence)
            and record.payload == b"still-recording\0"
        )
    finally:
        await journal.close()


@pytest.mark.asyncio
async def test_target_capture_does_not_retain_authoritative_writer_after_close(
    closed: ClosedJournal,
) -> None:
    api = _adapter()
    path = closed.path.with_name("weak-owner.sqlite3")
    writer = await sqlite_evidence.SqliteEvidenceJournal.create(path, closed.policy)
    reference = weakref.ref(writer)
    target = _capture(api, path, writer.session_id, writer.policy)
    await writer.close()
    del writer
    gc.collect()
    assert target is not None and reference() is None


def _native_descriptors(path: Path) -> set[int]:
    root = Path("/proc/self/fd") if Path("/proc/self/fd").is_dir() else Path("/dev/fd")
    if not root.is_dir():
        pytest.skip(
            "native descriptor inspection requires POSIX /proc/self/fd or /dev/fd"
        )
    identity = path.stat()
    result: set[int] = set()
    for entry in root.iterdir():
        if entry.name.isdecimal():
            try:
                native = os.fstat(int(entry.name))
            except OSError:
                continue
            if (native.st_dev, native.st_ino) == (identity.st_dev, identity.st_ino):
                result.add(int(entry.name))
    return result


@pytest.mark.asyncio
async def test_capture_holds_no_fd_and_close_releases_the_terminal_file_descriptor(
    closed: ClosedJournal,
) -> None:
    api = _adapter()
    assert _native_descriptors(closed.path) == set()
    target = _capture(api, closed.path, closed.session, closed.policy)
    assert _native_descriptors(closed.path) == set()
    reader = await _open(api, target)
    try:
        assert _native_descriptors(closed.path), (
            "reader never opened the captured journal"
        )
        assert (
            await reader.resolve_record(model.EvidenceReference(closed.session, 1))
            == closed.record
        )
    finally:
        await reader.close()
    assert _native_descriptors(closed.path) == set()


@pytest.mark.asyncio
async def test_non_sqlite_source_is_corrupt_and_never_recreated(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    closed.path.write_bytes(b"not-a-sqlite-journal-" + _DETAIL.encode())
    before = _files(closed.path.parent)
    _forbid_writable(monkeypatch)
    probe = ConnectionProbe(monkeypatch)
    with pytest.raises(
        (evidence.JournalFailure, evidence_access.EvidenceSourceOpenFailure)
    ) as caught:
        await _open(api, target)
    failure = _primary(caught.value)
    assert isinstance(failure, evidence.JournalFailure)
    assert (
        failure.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL
        and failure.detail is None
    )
    assert _files(closed.path.parent) == before and probe.closed == probe.connections


@pytest.mark.asyncio
async def test_corrupt_retention_marker_is_validated_before_any_bounded_page(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    seed = await _seed(closed.path.with_name("invalid-marker.sqlite3"), 1, retained=2)
    target = _capture(api, seed.path, seed.session, seed.policy)
    connection = sqlite3.connect(seed.path)
    try:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE retention_marker SET discarded_record_count = discarded_record_count + 1"
        )
        connection.commit()
    finally:
        connection.close()
    before = _files(seed.path.parent)
    _forbid_writable(monkeypatch)
    with pytest.raises(
        (evidence.JournalFailure, evidence_access.EvidenceSourceOpenFailure)
    ) as caught:
        reader = await _open(api, target)
        try:
            await reader.retrieve(
                evidence.EvidenceRetrievalRequest(seed.session, 1, 16384)
            )
        finally:
            await reader.close()
    failure = _primary(caught.value)
    assert (
        isinstance(failure, evidence.JournalFailure)
        and failure.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL
    )
    assert _files(seed.path.parent) == before


@pytest.mark.asyncio
async def test_read_only_file_and_directory_are_not_chmodded_or_repaired(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    old_file = closed.path.stat().st_mode & 0o777
    old_directory = closed.path.parent.stat().st_mode & 0o777
    closed.path.chmod(0o400)
    closed.path.parent.chmod(0o500)
    before = _files(closed.path.parent)
    try:
        with monkeypatch.context() as patch:
            _forbid_writable(patch)
            reader = await _open(api, target)
            try:
                assert (
                    await reader.retrieve(
                        evidence.EvidenceRetrievalRequest(closed.session, 10, 16384)
                    )
                    == closed.page
                )
            finally:
                await reader.close()
            assert _files(closed.path.parent) == before
    finally:
        closed.path.parent.chmod(old_directory)
        closed.path.chmod(old_file)


@pytest.mark.asyncio
async def test_locked_source_fails_busy_without_writer_retry(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    connect = sqlite3.connect
    locker = connect(closed.path)
    locker.execute("BEGIN EXCLUSIVE")
    before = _files(closed.path.parent)

    def no_wait(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        kwargs["timeout"] = 0
        return cast(sqlite3.Connection, connect(database, *args, **kwargs))

    try:
        monkeypatch.setattr(sqlite3, "connect", no_wait)
        _forbid_writable(monkeypatch)
        with pytest.raises(
            (evidence.JournalFailure, evidence_access.EvidenceSourceOpenFailure)
        ) as caught:
            await _open(api, target)
        failure = _primary(caught.value)
        assert (
            isinstance(failure, evidence.JournalFailure)
            and failure.kind is evidence.JournalFailureKind.BUSY
        )
        assert _files(closed.path.parent) == before
    finally:
        locker.rollback()
        locker.close()


_HOT_CHILD = r"""
import os, pathlib, sqlite3, sys, threading
import serial, serial.tools.list_ports

def forbidden(*args, **kwargs):
    raise AssertionError("hot-journal child cannot access physical hardware")
serial.Serial = serial.serial_for_url = serial.tools.list_ports.comports = forbidden
source, signal, root = map(pathlib.Path, sys.argv[1:4])
assert source.resolve().is_relative_to(root.resolve())
assert signal.resolve().is_relative_to(root.resolve())
connection = sqlite3.connect(source)
connection.execute("PRAGMA cache_size = 1")
connection.execute("BEGIN IMMEDIATE")
connection.execute("UPDATE evidence_records SET payload = zeroblob(200000) WHERE sequence = 1")
signal.write_text("dirty", encoding="utf-8")
threading.Event().wait()
"""


@pytest.mark.asyncio
async def test_hot_source_is_rejected_as_is_without_rollback_recovery(
    closed: ClosedJournal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    signal = closed.path.with_name("hot-ready.txt")
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _HOT_CHILD,
            str(closed.path),
            str(signal),
            str(closed.path.parent),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(5):
            while not signal.exists():
                assert process.poll() is None, (
                    "guarded hot-journal child exited before its barrier"
                )
                await asyncio.sleep(0.01)
    finally:
        if process.poll() is None:
            process.kill()
        await asyncio.to_thread(process.communicate, timeout=3)
    rollback = closed.path.with_name(closed.path.name + "-journal")
    assert rollback.is_file() and rollback.read_bytes()[:8] == bytes.fromhex(
        "d9d505f920a163d7"
    )
    before = _files(closed.path.parent)
    _forbid_writable(monkeypatch)
    with pytest.raises(
        (evidence.JournalFailure, evidence_access.EvidenceSourceOpenFailure)
    ) as caught:
        await _open(api, target)
    failure = _primary(caught.value)
    assert isinstance(failure, evidence.JournalFailure)
    assert failure.kind in {
        evidence.JournalFailureKind.READ_ONLY,
        evidence.JournalFailureKind.BUSY,
        evidence.JournalFailureKind.IO_FAILURE,
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    }
    assert _files(closed.path.parent) == before


# 009 T006 adds a private expected_schema_version capture argument (default 1,
# explicit 2). This is an adapter-private test seam, not a client-selected format.
# Existing 008 tests above remain unchanged; no terminal implementation lives here.


def _t006_capture(api: Any, seed: Any, expected: int | None = 2) -> Any:
    if expected is None:
        return _capture(api, seed.path, seed.session, seed.policy)
    return api.capture_terminal_target(
        seed.path,
        session_id=seed.session,
        policy=seed.policy,
        expected_schema_version=expected,
    )


def _t006_forbid_writable(patch: pytest.MonkeyPatch) -> None:
    _forbid_writable(patch)

    def forbidden(*args: object, **kwargs: object) -> Any:
        pytest.fail("terminal v2 retrieval cannot use writable v2 factories")

    for name in ("create_v2", "open_v2"):
        if hasattr(sqlite_evidence.SqliteEvidenceJournal, name):
            patch.setattr(sqlite_evidence.SqliteEvidenceJournal, name, forbidden)


@pytest.mark.asyncio
async def test_t006_default_target_captures_immutable_v1_expectation_and_preserves_legacy_read(
    closed: ClosedJournal,
) -> None:
    api = _adapter()
    target = _capture(api, closed.path, closed.session, closed.policy)
    assert getattr(target, "expected_schema_version", None) == 1
    with pytest.raises(FrozenInstanceError):
        target.expected_schema_version = 2
    reader = await _open(api, target)
    try:
        assert (
            await reader.retrieve(
                evidence.EvidenceRetrievalRequest(closed.session, 10, 16384)
            )
            == closed.page
        )
    finally:
        await reader.close()


@pytest.mark.asyncio
async def test_t006_explicit_v2_expectation_rejects_a_legacy_v1_file_without_guessing_or_mutation(
    closed: ClosedJournal, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _adapter()
    target = _t006_capture(api, closed)
    before = _files(closed.path.parent)
    _t006_forbid_writable(monkeypatch)
    probe = ConnectionProbe(monkeypatch)
    with pytest.raises(evidence_access.EvidenceSourceOpenFailure) as caught:
        reader = await _open(api, target)
        await reader.close()
    failure = caught.value.primary
    assert isinstance(failure, evidence.JournalFailure)
    assert failure.kind is evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION
    assert caught.value.reader_close_confirmed is True
    assert probe.close_calls == 1 and probe.closed == probe.connections
    assert _files(closed.path.parent) == before


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t006_v2_terminal_markers_and_raw_bytes_use_fresh_verified_read_only_transactions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, index: int
) -> None:
    from tests.contract.test_monitor_journal import _seed_v2

    seed = await _seed_v2(tmp_path / "terminal-v2 spaced-é ?#%.sqlite3", index)
    api = _adapter()
    target = _t006_capture(api, seed)
    assert target.expected_schema_version == 2
    with pytest.raises(FrozenInstanceError):
        target.expected_schema_version = 1
    before = _files(seed.path.parent)
    for sequence in (1, 4):
        with monkeypatch.context() as patch:
            _t006_forbid_writable(patch)
            probe = ConnectionProbe(patch)
            reader = await _open(api, target)
            try:
                marker = await reader.resolve_record(
                    model.EvidenceReference(seed.session, sequence)
                )
                assert marker.records == (seed.records[sequence],)
                page = await reader.retrieve(
                    evidence.EvidenceRetrievalRequest(seed.session, 20, 20000)
                )
                assert page == seed.page
            finally:
                await reader.close()
            probe.read_only(seed.path)
        assert _files(seed.path.parent) == before


@pytest.mark.asyncio
async def test_t006_legacy_default_terminal_target_rejects_v2_even_without_operation_rows(
    tmp_path: Path,
) -> None:
    from tests.contract.test_monitor_journal import _create_v2
    from tests.contract.test_sqlite_evidence_journal import _policy

    path = tmp_path / "empty-v2.sqlite3"
    journal = await _create_v2(path, _policy())
    session, policy = journal.session_id, journal.policy
    await journal.close()
    api = _adapter()
    target = _capture(api, path, session, policy)
    before = _files(path.parent)
    with pytest.raises(evidence_access.EvidenceSourceOpenFailure) as caught:
        reader = await _open(api, target)
        await reader.close()
    failure = caught.value.primary
    assert isinstance(failure, evidence.JournalFailure)
    assert failure.kind is evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION
    assert caught.value.reader_close_confirmed is True
    assert _files(path.parent) == before


@pytest.mark.parametrize("retained", [2, 100])
@pytest.mark.asyncio
async def test_t006_terminal_v2_reuses_fixed_snapshot_shortage_and_expired_marker_results(
    tmp_path: Path, retained: int
) -> None:
    from tests.contract.test_monitor_journal import _seed_v2

    seed = await _seed_v2(tmp_path / "terminal-pages.sqlite3", retained=retained)
    api = _adapter()
    target = _t006_capture(api, seed)
    reader = await _open(api, target)
    try:
        page = await reader.retrieve(
            evidence.EvidenceRetrievalRequest(seed.session, 20, 20000)
        )
        assert page == seed.page
        sequence = 4
        shortage = await reader.retrieve(
            evidence.EvidenceRetrievalRequest(
                model.EvidenceRangeReference(seed.session, sequence, 5),
                20,
                1,
            )
        )
        assert shortage.records == () and shortage.truncated
        assert shortage.continuation is not None
        assert shortage.continuation.next_sequence == sequence
        assert shortage.snapshot_end_exclusive == 5
        assert (
            shortage.next_record_required_bytes
            == sqlite_evidence.encode_evidence_record_v2(seed.records[4]).charged_bytes
        )
        if retained == 2:
            expired = await reader.resolve_record(
                model.EvidenceReference(seed.session, 1)
            )
            assert expired.outcome is evidence.EvidencePageOutcome.EXPIRED
            assert expired.retention_marker == seed.page.retention_marker
    finally:
        await reader.close()


@pytest.mark.parametrize(
    "change", ["session", "identity", *[f.name for f in fields(model.SessionPolicy)]]
)
@pytest.mark.asyncio
async def test_t006_v2_terminal_keeps_exact_session_native_identity_and_each_policy_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    from tests.contract.test_monitor_journal import _seed_v2, _sql

    seed = await _seed_v2(tmp_path / "captured-v2.sqlite3")
    api = _adapter()
    target = _t006_capture(api, seed)
    if change == "session":
        _sql(seed.path, "UPDATE session_metadata SET session_id='different-session'")
    elif change == "identity":
        replacement = seed.path.with_name("replacement.sqlite3")
        shutil.copyfile(seed.path, replacement)
        replacement.replace(seed.path)
    else:
        assert change in {f.name for f in fields(model.SessionPolicy)}
        _sql(seed.path, f"UPDATE session_metadata SET {change}={change}+1")
    before = _files(seed.path.parent)
    _t006_forbid_writable(monkeypatch)
    probe = ConnectionProbe(monkeypatch)
    with pytest.raises(evidence_access.EvidenceSourceOpenFailure) as caught:
        reader = await _open(api, target)
        await reader.close()
    primary = caught.value.primary
    if change == "session":
        assert isinstance(primary, evidence.JournalFailure)
        assert primary.kind is evidence.JournalFailureKind.SESSION_MISMATCH
    else:
        assert isinstance(primary, evidence_access.EvidenceReadRejected)
        assert primary.kind == "source_changed"
    assert caught.value.reader_close_confirmed is True
    assert probe.closed == probe.connections
    assert _files(seed.path.parent) == before


@pytest.mark.parametrize(
    "failure_stage", ["query_only", "partial_open_close", "read", "close"]
)
@pytest.mark.asyncio
async def test_t006_v2_terminal_does_not_hide_query_only_or_cleanup_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    from tests.contract.test_monitor_journal import _seed_v2

    seed = await _seed_v2(tmp_path / "cleanup-v2.sqlite3")
    api = _adapter()
    target = _t006_capture(api, seed)
    if failure_stage == "partial_open_close":
        target = replace(target, session_id=model.SessionId("wrong-session"))
    _t006_forbid_writable(monkeypatch)
    probe = ConnectionProbe(monkeypatch)
    if failure_stage in {"query_only", "partial_open_close"}:
        if failure_stage == "query_only":
            probe.refuse_query_only = True
        else:
            probe.close_failure = OSError(errno.EIO, _DETAIL)
        with pytest.raises(evidence_access.EvidenceSourceOpenFailure) as caught:
            await _open(api, target)
        assert isinstance(caught.value.primary, evidence.JournalFailure)
        assert caught.value.primary.kind is (
            evidence.JournalFailureKind.READ_ONLY
            if failure_stage == "query_only"
            else evidence.JournalFailureKind.SESSION_MISMATCH
        )
        assert caught.value.reader_close_confirmed is (failure_stage == "query_only")
    else:
        reader = await _open(api, target)
        if failure_stage == "read":
            probe.read_failure = OSError(errno.EIO, _DETAIL)
            try:
                with pytest.raises(evidence.JournalFailure) as read:
                    await reader.retrieve(
                        evidence.EvidenceRetrievalRequest(seed.session, 20, 20000)
                    )
                assert read.value.operation is evidence.JournalOperation.RETRIEVE
                assert read.value.kind is evidence.JournalFailureKind.IO_FAILURE
                assert read.value.detail is None
            finally:
                await reader.close()
        else:
            probe.close_failure = OSError(errno.EIO, _DETAIL)
            with pytest.raises(evidence.JournalFailure) as close:
                await reader.close()
            assert close.value.operation is evidence.JournalOperation.CLOSE
            assert close.value.kind is evidence.JournalFailureKind.IO_FAILURE
            assert close.value.detail is None
    assert probe.close_calls == 1 and probe.closed == probe.connections


@pytest.mark.parametrize(
    "statement,kind",
    [
        (
            "PRAGMA user_version=1",
            evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION,
        ),
        (
            "UPDATE evidence_records SET record_version=1 WHERE sequence=1",
            evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION,
        ),
        (
            "UPDATE evidence_records SET record_kind='operation_other' WHERE sequence=4",
            evidence.JournalFailureKind.CORRUPT_JOURNAL,
        ),
        (
            "UPDATE evidence_records SET payload=NULL WHERE sequence=4",
            evidence.JournalFailureKind.CORRUPT_JOURNAL,
        ),
        (
            "UPDATE evidence_records SET timestamp_endpoint_json=X'7b7d' WHERE sequence=1",
            evidence.JournalFailureKind.CORRUPT_JOURNAL,
        ),
    ],
)
@pytest.mark.asyncio
async def test_t006_terminal_v2_validates_unselected_operation_rows_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    statement: str,
    kind: evidence.JournalFailureKind,
) -> None:
    from tests.contract.test_monitor_journal import _seed_v2, _sql

    seed = await _seed_v2(tmp_path / "invalid-v2.sqlite3")
    api = _adapter()
    target = _t006_capture(api, seed)
    _sql(seed.path, statement)
    before = _files(seed.path.parent)
    _t006_forbid_writable(monkeypatch)
    probe = ConnectionProbe(monkeypatch)
    with pytest.raises(evidence_access.EvidenceSourceOpenFailure) as caught:
        reader = await _open(api, target)
        try:
            await reader.resolve_record(model.EvidenceReference(seed.session, 0))
        finally:
            await reader.close()
    assert isinstance(caught.value.primary, evidence.JournalFailure)
    assert caught.value.primary.kind is kind
    assert caught.value.reader_close_confirmed is True
    assert probe.closed == probe.connections and _files(seed.path.parent) == before
