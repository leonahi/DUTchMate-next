"""Immutable observation values and authoritative status eligibility facts."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import FrozenInstanceError, fields, replace
from itertools import product
from pathlib import Path
from typing import Any, cast

import pytest

from dutchmate_core import acquisition as aq
from dutchmate_core import model, profile
from dutchmate_core import runtime as runtime_api
from dutchmate_core.adapters.sqlite_evidence import SqliteEvidenceJournal
from dutchmate_core.evidence import JournalFailureKind
from dutchmate_core.runtime import (
    ObservationRecorder,
    PreparedObservationRun,
    PrepareObservationRun,
)
from tests.fakes import BasicShapedBackend


def _profile() -> profile.ResolvedDutProfile:
    return profile.ResolvedDutProfile(
        format_version=profile.ProfileFormatVersion(1),
        dut=profile.DutIdentity(id="fixture-board", name="Fixture"),
        backend=profile.ProfileBackendSelection(
            kind="basic_serial", expected_device="fixture-explicit-device"
        ),
        uart=profile.ProfileUartConfiguration(
            baud_rate=115_200,
            data_bits=8,
            parity="none",
            stop_bits=1,
            hardware_flow_control=False,
            software_flow_control=False,
        ),
        open_lines=profile.ProfileSerialOpenLineIntent(
            dtr="deasserted", rts="deasserted"
        ),
        policy=profile.ObservationPolicy(),
        session_policy=model.SessionPolicy(
            max_retained_records=100,
            max_retained_charged_bytes=65_536,
            max_record_charged_bytes=8_192,
            max_database_pages=100,
            max_retrieval_page_records=10,
            max_retrieval_page_charged_bytes=16_384,
        ),
    )


def test_run_id_generation_and_validation() -> None:
    ids = [runtime_api.RunId() for _ in range(20)]
    assert len({run_id.value for run_id in ids}) == 20
    assert all(isinstance(run_id.value, str) and run_id.value for run_id in ids)
    field = "value"
    with pytest.raises(FrozenInstanceError):
        setattr(ids[0], field, "changed")
    for invalid in ("", "   ", None, 17, b"bytes"):
        with pytest.raises((TypeError, ValueError)):
            runtime_api.RunId(cast("str", invalid))


def test_initial_status_has_only_confirmed_inactive_facts() -> None:
    status = runtime_api.RuntimeStatus()
    assert status.state == "inactive"
    assert status.owner_settled
    assert status.physical_release_confirmed
    assert status.recorder_close_confirmed
    assert status.attach_admissible
    assert all(
        value is None
        for value in (
            status.run_id,
            status.profile,
            status.session_id,
            status.acquisition,
            status.terminal_reason,
            status.primary_issue,
        )
    )
    assert status.cleanup_issues == ()
    assert status.stop_intent == "none"
    assert "attach_admissible" not in {field.name for field in fields(status)}
    field = "attach_admissible"
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        setattr(status, field, False)
    with pytest.raises(TypeError):
        runtime_api.RuntimeStatus(**cast("Any", {"attach_admissible": False}))


@pytest.mark.parametrize(
    ("state", "settled", "physical", "recorder"),
    list(
        product(
            ("inactive", "attaching", "active", "detaching", "terminated", "failed"),
            (False, True),
            (False, True),
            (False, True),
        )
    ),
)
def test_status_fact_matrix_rejects_impossible_states_and_derives_admission(
    state: str,
    settled: bool,
    physical: bool,
    recorder: bool,
) -> None:
    arguments: dict[str, object] = {
        "state": runtime_api.RuntimeState(state),
        "owner_settled": settled,
        "physical_release_confirmed": physical,
        "recorder_close_confirmed": recorder,
    }
    if state != "inactive":
        arguments.update(run_id=runtime_api.RunId(), profile=_profile())
    if state in {"terminated", "failed"}:
        arguments["terminal_reason"] = runtime_api.RuntimeTerminalReason.DETACHED
    if state == "failed":
        arguments["primary_issue"] = runtime_api.RuntimeIssue(
            runtime_api.RuntimeIssueSource.ACQUISITION,
            aq.AcquisitionFailureKind.RECORDING_FAILURE,
        )
    valid = (
        (state == "inactive" and settled and physical and recorder)
        or (state in {"attaching", "active", "detaching"} and not settled)
        or (state in {"terminated", "failed"} and settled)
    )
    if not valid:
        with pytest.raises(ValueError):
            runtime_api.RuntimeStatus(**cast("Any", arguments))
        return
    status = runtime_api.RuntimeStatus(**cast("Any", arguments))
    expected = state in {"inactive", "terminated", "failed"} and physical and recorder
    assert status.attach_admissible is expected


@pytest.mark.parametrize("missing", ["run_id", "profile"])
def test_admitted_status_requires_both_identity_and_profile(
    missing: str,
) -> None:
    arguments = {
        "state": runtime_api.RuntimeState.ATTACHING,
        "run_id": runtime_api.RunId(),
        "profile": _profile(),
        "owner_settled": False,
    }
    arguments[missing] = None
    with pytest.raises(ValueError):
        runtime_api.RuntimeStatus(**cast("Any", arguments))


def test_pending_status_keeps_unknown_session_and_acquisition_absent() -> None:
    status = runtime_api.RuntimeStatus(
        state=runtime_api.RuntimeState.ATTACHING,
        run_id=runtime_api.RunId(),
        profile=_profile(),
        owner_settled=False,
        recorder_close_confirmed=False,
    )
    assert status.session_id is None
    assert status.acquisition is None
    assert status.terminal_reason is None
    assert not status.attach_admissible
    assert status.profile is not None
    field = "dut"
    with pytest.raises(FrozenInstanceError):
        setattr(status.profile, field, profile.DutIdentity("new", "New"))


@pytest.mark.parametrize(
    "state",
    [
        aq.AcquisitionState.STARTING,
        aq.AcquisitionState.ACQUIRING,
        aq.AcquisitionState.STOPPING,
    ],
)
def test_settled_owner_cannot_contain_live_acquisition(
    state: aq.AcquisitionState,
) -> None:
    with pytest.raises(ValueError):
        runtime_api.RuntimeStatus(
            state=runtime_api.RuntimeState.TERMINATED,
            run_id=runtime_api.RunId(),
            profile=_profile(),
            terminal_reason=runtime_api.RuntimeTerminalReason.DETACHED,
            acquisition=aq.AcquisitionSnapshot(state),
        )


@pytest.mark.parametrize(
    ("runtime_release", "acquisition_release"), [(True, False), (False, True)]
)
def test_runtime_cannot_override_acquisition_release_fact(
    runtime_release: bool,
    acquisition_release: bool,
) -> None:
    with pytest.raises(ValueError):
        runtime_api.RuntimeStatus(
            state=runtime_api.RuntimeState.DETACHING,
            run_id=runtime_api.RunId(),
            profile=_profile(),
            owner_settled=False,
            physical_release_confirmed=runtime_release,
            acquisition=aq.AcquisitionSnapshot(
                aq.AcquisitionState.STOPPING,
                physical_release_confirmed=acquisition_release,
            ),
        )


def test_cleanup_facts_are_bounded_ordered_and_do_not_replace_primary() -> None:
    primary = runtime_api.RuntimeIssue(
        runtime_api.RuntimeIssueSource.ACQUISITION,
        aq.AcquisitionFailureKind.RECORDING_FAILURE,
    )
    backend = runtime_api.RuntimeIssue(
        runtime_api.RuntimeIssueSource.BACKEND_CLOSE, "close_failed"
    )
    recorder = runtime_api.RuntimeIssue(
        runtime_api.RuntimeIssueSource.RECORDER_CLOSE, JournalFailureKind.IO_FAILURE
    )
    status = runtime_api.RuntimeStatus(
        state=runtime_api.RuntimeState.FAILED,
        run_id=runtime_api.RunId(),
        profile=_profile(),
        terminal_reason=runtime_api.RuntimeTerminalReason.DISCONNECTED,
        primary_issue=primary,
        cleanup_issues=(backend, recorder),
        physical_release_confirmed=False,
        recorder_close_confirmed=False,
    )
    assert status.primary_issue == primary
    assert status.cleanup_issues == (backend, recorder)
    assert status.terminal_reason == "disconnected"
    assert not status.attach_admissible
    for invalid in (
        [backend],
        (backend, backend, recorder),
        (recorder, backend),
        (backend, backend),
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(
                status,
                cleanup_issues=cast("tuple[runtime_api.RuntimeIssue, ...]", invalid),
            )
    with pytest.raises(ValueError):
        replace(status, physical_release_confirmed=True)
    with pytest.raises(ValueError):
        replace(status, recorder_close_confirmed=True)


def test_status_rejects_untyped_causes_contexts_and_identifiers() -> None:
    arguments: dict[str, object] = {
        "state": runtime_api.RuntimeState.ATTACHING,
        "run_id": runtime_api.RunId(),
        "profile": _profile(),
        "owner_settled": False,
    }
    for name, invalid in (
        ("primary_issue", RuntimeError("private diagnostic")),
        ("profile", {"path": "/private/profile.toml"}),
        ("session_id", "unvalidated"),
        ("acquisition", {"raw_connection": object()}),
        ("owner_settled", 0),
    ):
        with pytest.raises((TypeError, ValueError)):
            runtime_api.RuntimeStatus(**cast("Any", arguments | {name: invalid}))
    with pytest.raises((TypeError, ValueError)):
        runtime_api.RuntimeIssue(
            runtime_api.RuntimeIssueSource.ACQUISITION,
            cast("runtime_api.RuntimeIssueCode", RuntimeError("raw")),
        )
    with pytest.raises((TypeError, ValueError)):
        runtime_api.RuntimeIssue(
            runtime_api.RuntimeIssueSource.PREPARATION,
            cast("runtime_api.RuntimeIssueCode", "arbitrary exception text"),
        )
    with pytest.raises(TypeError):
        runtime_api.RuntimeIssue(
            runtime_api.RuntimeIssueSource.ACQUISITION,
            aq.AcquisitionFailureKind.RECORDING_FAILURE,
            **cast("Any", {"context": object()}),
        )


@pytest.mark.asyncio
async def test_terminal_provenance_is_an_immutable_historical_value() -> None:
    from dutchmate_core.evidence import InMemoryEvidenceRecorder

    acquisition = aq.Acquisition(InMemoryEvidenceRecorder())
    connection_id = await acquisition.start(BasicShapedBackend())
    await acquisition.stop()
    snapshot = await acquisition.join_terminated()
    status = runtime_api.RuntimeStatus(
        state=runtime_api.RuntimeState.TERMINATED,
        run_id=runtime_api.RunId(),
        profile=_profile(),
        session_id=model.SessionId("known-session"),
        acquisition=snapshot,
        terminal_reason=runtime_api.RuntimeTerminalReason.DETACHED,
    )
    assert status.acquisition is not None
    assert status.acquisition.provenance is not None
    assert status.acquisition.state is aq.AcquisitionState.STOPPED
    assert status.acquisition.provenance.connection_id == connection_id
    assert status.attach_admissible
    assert status.session_id == model.SessionId("known-session")
    field = "state"
    with pytest.raises(FrozenInstanceError):
        setattr(status, field, runtime_api.RuntimeState.ACTIVE)


@pytest.mark.asyncio
async def test_preparation_subset_preserves_exact_profile_policy_by_value(
    tmp_path: Path,
) -> None:
    resolved = _profile()
    policy_copy = replace(resolved.session_policy)
    journal = await SqliteEvidenceJournal.create(
        tmp_path / "session.sqlite", policy_copy
    )
    try:
        recorder: ObservationRecorder = journal

        async def prepare(p: profile.ResolvedDutProfile) -> PreparedObservationRun:
            assert recorder.policy == p.session_policy
            return runtime_api.PreparedObservationRun(recorder, BasicShapedBackend())

        preparation: PrepareObservationRun = prepare
        prepared = await preparation(resolved)
        assert prepared.recorder.policy == resolved.session_policy
        assert prepared.recorder.policy is not resolved.session_policy
        assert prepared.recorder.session_id == journal.session_id
        field = "recorder"
        with pytest.raises(FrozenInstanceError):
            setattr(prepared, field, None)
        # T008/T013 enforce mismatch rejection; this value exposes the policy
        # for that check without accepting a hidden Profile constructor input.
        assert prepared.recorder.policy != replace(
            policy_copy, max_retained_records=101
        )
    finally:
        await journal.close()


def test_preparation_failure_is_normalized_and_carries_only_known_identity() -> None:
    primary = runtime_api.RuntimeIssue(
        runtime_api.RuntimeIssueSource.PREPARATION, JournalFailureKind.IO_FAILURE
    )
    cleanup = runtime_api.RuntimeIssue(
        runtime_api.RuntimeIssueSource.RECORDER_CLOSE, JournalFailureKind.IO_FAILURE
    )
    failure = runtime_api.PreparationFailure(
        primary_issue=primary,
        session_id=model.SessionId("created-session"),
        recorder_close_confirmed=False,
        cleanup_issue=cleanup,
    )
    assert failure.primary_issue == primary
    assert failure.session_id == model.SessionId("created-session")
    assert failure.cleanup_issue == cleanup
    assert not failure.recorder_close_confirmed
    unknown = runtime_api.PreparationFailure(primary_issue=primary)
    assert unknown.session_id is None
    assert not unknown.recorder_close_confirmed
    field = "primary_issue"
    with pytest.raises(FrozenInstanceError):
        setattr(failure, field, RuntimeError("raw"))
    with pytest.raises(ValueError):
        replace(failure, recorder_close_confirmed=True)
    with pytest.raises((TypeError, ValueError)):
        runtime_api.PreparationFailure(
            primary_issue=cast("runtime_api.RuntimeIssue", RuntimeError("raw"))
        )
    with pytest.raises(TypeError):
        runtime_api.PreparationFailure(
            primary_issue=primary, **cast("Any", {"cause": RuntimeError("raw")})
        )


@pytest.mark.parametrize(
    "kind",
    ["invalid_request", "busy", "cleanup_unconfirmed", "wrong_execution_context"],
)
def test_rejected_request_categories_are_normalized(kind: str) -> None:
    failure = runtime_api.RuntimeRejectedError(runtime_api.RuntimeRejectedKind(kind))
    assert failure.kind == kind
    assert isinstance(failure, RuntimeError)
    assert str(failure) == kind
    # Exception transport must not mask the normalized category with TypeError
    # when contextlib forwards it by assigning its standard traceback field.
    with pytest.raises(runtime_api.RuntimeRejectedError) as propagated:
        with _forward_exception():
            raise failure
    assert propagated.value is failure
    field = "kind"
    with pytest.raises(AttributeError):
        setattr(failure, field, runtime_api.RuntimeRejectedKind.INVALID_REQUEST)


@contextmanager
def _forward_exception() -> Iterator[None]:
    yield


def test_no_loop_constructor_rejection_survives_context_manager() -> None:
    with pytest.raises(runtime_api.RuntimeRejectedError) as rejected:
        with _forward_exception():
            runtime_api.ObservationRuntime()
    assert (
        rejected.value.kind is runtime_api.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT
    )
    assert rejected.value.__cause__ is None
    assert rejected.value.__context__ is None


@asynccontextmanager
async def _forward_async_exception() -> AsyncIterator[None]:
    yield


@pytest.mark.asyncio
async def test_invalid_attach_rejection_survives_async_context_manager() -> None:
    runtime = runtime_api.ObservationRuntime()
    before = runtime.status()

    async def forbidden_prepare(
        _: profile.ResolvedDutProfile,
    ) -> PreparedObservationRun:
        raise AssertionError("invalid request must never prepare resources")

    with pytest.raises(runtime_api.RuntimeRejectedError) as rejected:
        async with _forward_async_exception():
            await runtime.attach(
                cast("profile.ResolvedDutProfile", None), forbidden_prepare
            )
    assert rejected.value.kind is runtime_api.RuntimeRejectedKind.INVALID_REQUEST
    assert runtime.status() == before


def test_t024_preparation_failure_survives_sync_context_exception_transport() -> None:
    failure = runtime_api.PreparationFailure(
        runtime_api.RuntimeIssue(
            runtime_api.RuntimeIssueSource.PREPARATION, JournalFailureKind.IO_FAILURE
        ),
        model.SessionId("known-created-session"),
        True,
    )
    with pytest.raises(runtime_api.PreparationFailure) as propagated:
        with _forward_exception():
            raise failure
    assert propagated.value is failure
    assert failure.__traceback__ is not None
    assert failure.__cause__ is None and failure.__context__ is None


@pytest.mark.asyncio
async def test_t024_preparation_failure_survives_async_context_exception_transport() -> (
    None
):
    failure = runtime_api.PreparationFailure(
        runtime_api.RuntimeIssue(
            runtime_api.RuntimeIssueSource.PREPARATION, JournalFailureKind.IO_FAILURE
        ),
        model.SessionId("known-created-session"),
        False,
        runtime_api.RuntimeIssue(
            runtime_api.RuntimeIssueSource.RECORDER_CLOSE, JournalFailureKind.IO_FAILURE
        ),
    )
    with pytest.raises(runtime_api.PreparationFailure) as propagated:
        async with _forward_async_exception():
            raise failure
    assert propagated.value is failure
    assert failure.__traceback__ is not None
    assert failure.__cause__ is None and failure.__context__ is None


@pytest.mark.parametrize("context", ["sync", "async"])
@pytest.mark.parametrize("close_failed", [False, True])
@pytest.mark.asyncio
async def test_t024_context_forwarded_preparation_keeps_session_primary_and_cleanup(
    tmp_path: Path, context: str, close_failed: bool
) -> None:
    # Catch transport masking turning a known, normalized report into an
    # internal-contract failure with missing identity/unconfirmed cleanup.
    runtime = runtime_api.ObservationRuntime()
    primary = runtime_api.RuntimeIssue(
        runtime_api.RuntimeIssueSource.PREPARATION, JournalFailureKind.CAPACITY
    )
    cleanup = runtime_api.RuntimeIssue(
        runtime_api.RuntimeIssueSource.RECORDER_CLOSE, JournalFailureKind.IO_FAILURE
    )
    path = tmp_path / "retained-preparation.sqlite3"
    journal = await SqliteEvidenceJournal.create(path, _profile().session_policy)
    await journal.close()
    failure = runtime_api.PreparationFailure(
        primary, journal.session_id, not close_failed, cleanup if close_failed else None
    )

    async def prepare(_: profile.ResolvedDutProfile) -> PreparedObservationRun:
        # The recorder is actually created/closed. A failed reported close
        # remains uncertain even if the underlying library handle closed.
        if context == "sync":
            with _forward_exception():
                raise failure
        async with _forward_async_exception():
            raise failure

    try:
        result = await runtime.attach(_profile(), prepare)
        assert result.state is runtime_api.RuntimeState.FAILED and result.owner_settled
        assert (
            result.terminal_reason is runtime_api.RuntimeTerminalReason.STARTUP_FAILURE
        )
        assert result.primary_issue == primary
        assert result.session_id == journal.session_id and path.is_file()
        assert result.cleanup_issues == ((cleanup,) if close_failed else ())
        assert result.recorder_close_confirmed is not close_failed
        assert result.attach_admissible is not close_failed
        assert result.physical_release_confirmed and result.acquisition is None
        assert await runtime.detach() == result
        assert runtime.status() == result
    finally:
        await runtime.detach()
        await journal.close()


@pytest.mark.parametrize(
    "name",
    ["primary_issue", "session_id", "recorder_close_confirmed", "cleanup_issue"],
)
@pytest.mark.parametrize("operation", ["assign", "delete"])
def test_t024_preparation_facts_remain_read_only(name: str, operation: str) -> None:
    failure = runtime_api.PreparationFailure(
        runtime_api.RuntimeIssue(
            runtime_api.RuntimeIssueSource.PREPARATION, JournalFailureKind.IO_FAILURE
        )
    )
    before = (
        failure.primary_issue,
        failure.session_id,
        failure.recorder_close_confirmed,
        failure.cleanup_issue,
    )
    with pytest.raises(FrozenInstanceError):
        if operation == "assign":
            setattr(failure, name, RuntimeError("raw"))
        else:
            delattr(failure, name)
    assert (
        failure.primary_issue,
        failure.session_id,
        failure.recorder_close_confirmed,
        failure.cleanup_issue,
    ) == before
