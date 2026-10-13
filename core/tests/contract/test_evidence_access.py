"""T006 RED: live read admission and ownership on the real observation runtime.

Test-owned gates control persistence/backend boundaries, never runtime policy.
The protocol and constructor cast describe the documented T008 additions without
implementing them or preventing collection against the current production runtime.
Terminal readers, delivery and the T007 binary integration matrix are outside scope.
"""

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, NoReturn, Protocol, cast

import pytest
import pytest_asyncio

from dutchmate_core import evidence_access as access
from dutchmate_core import model, profile
from dutchmate_core import runtime as rt
from dutchmate_core.acquisition import Acquisition, AcquisitionSnapshot
from dutchmate_core.adapters.sqlite_evidence import SqliteEvidenceJournal
from dutchmate_core.adapters.terminal_evidence import (
    capture_terminal_target,
    open_terminal_reader,
)
from dutchmate_core.evidence import (
    EvidencePage,
    EvidencePageOutcome,
    EvidenceRetrievalRequest,
    JournalFailure,
    JournalFailureKind,
    JournalOperation,
    PendingEvidenceRecord,
    PendingSegmentEndedEvidence,
)
from tests.contract.test_observation_runtime import _profile
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixture,
    BackendFixtureFactory,
    FixtureLifecycleGate,
)

type QueryKind = Literal["record", "page"]


class ReadRuntime(Protocol):
    async def attach(
        self, resolved: profile.ResolvedDutProfile, prepare: rt.PrepareObservationRun
    ) -> rt.RuntimeStatus: ...

    async def detach(self) -> rt.RuntimeStatus: ...

    def status(self) -> rt.RuntimeStatus: ...

    async def read_record(
        self, reference: model.EvidenceReference
    ) -> access.RunEvidencePage: ...

    async def read_page(
        self, request: EvidenceRetrievalRequest
    ) -> access.RunEvidencePage: ...


async def _await[T](work: Awaitable[T]) -> T:
    # Harness watchdog only; no elapsed-time acceptance condition or Core timeout.
    async with asyncio.timeout(3):
        return await work


async def _checkpoint() -> None:
    # Ready-queue barrier, not a sleep used to arrange a race by elapsed time.
    loop = asyncio.get_running_loop()
    reached = loop.create_future()
    loop.call_soon(reached.set_result, None)
    await reached


async def _query(
    runtime: ReadRuntime, kind: QueryKind, session: model.SessionId
) -> access.RunEvidencePage:
    if kind == "record":
        method = getattr(runtime, "read_record", None)
        assert callable(method), (
            "T008 ObservationRuntime.read_record is not implemented"
        )
        return await runtime.read_record(model.EvidenceReference(session, 0))
    method = getattr(runtime, "read_page", None)
    assert callable(method), "T008 ObservationRuntime.read_page is not implemented"
    return await runtime.read_page(EvidenceRetrievalRequest(session, 10, 16384))


class RecorderProbe:
    """Only capture's lifecycle port; deliberately provides no retrieval methods."""

    def __init__(self, journal: SqliteEvidenceJournal) -> None:
        self.journal = journal
        self.final_append = FixtureLifecycleGate()
        self.close_gate = FixtureLifecycleGate()
        self.close_calls = 0
        self.trace: list[str] = []

    @property
    def session_id(self) -> model.SessionId:
        return self.journal.session_id

    @property
    def policy(self) -> model.SessionPolicy:
        return self.journal.policy

    async def append(self, draft: PendingEvidenceRecord) -> model.EvidenceRecord:
        if isinstance(draft, PendingSegmentEndedEvidence):
            await self.final_append.enter()
        record = await self.journal.append(draft)
        if isinstance(draft, PendingSegmentEndedEvidence):
            self.trace.append("final_append.committed")
        return record

    async def close(self) -> None:
        self.close_calls += 1
        self.trace.append("recorder.close_entered")
        await self.close_gate.enter()
        await self.journal.close()
        self.trace.append("recorder.closed")


class ReaderProbe:
    """Gated queries on the same actual journal/worker used by RecorderProbe."""

    def __init__(self, journal: SqliteEvidenceJournal, trace: list[str]) -> None:
        self.journal = journal
        self.trace = trace
        self.gate = FixtureLifecycleGate()
        self.entered: asyncio.Queue[
            model.EvidenceReference | EvidenceRetrievalRequest
        ] = asyncio.Queue()
        self.finished: asyncio.Queue[None] = asyncio.Queue()
        self.calls: list[model.EvidenceReference | EvidenceRetrievalRequest] = []
        self.cancelled = 0
        self.failure: JournalFailure | None = None

    @property
    def session_id(self) -> model.SessionId:
        return self.journal.session_id

    @property
    def policy(self) -> model.SessionPolicy:
        return self.journal.policy

    async def resolve_record(self, reference: model.EvidenceReference) -> EvidencePage:
        await self._enter(reference)
        try:
            if self.failure is not None:
                raise self.failure
            return await self.journal.resolve_record(reference)
        finally:
            self._finish()

    async def retrieve(self, request: EvidenceRetrievalRequest) -> EvidencePage:
        await self._enter(request)
        try:
            if self.failure is not None:
                raise self.failure
            return await self.journal.retrieve(request)
        finally:
            self._finish()

    async def _enter(
        self, query: model.EvidenceReference | EvidenceRetrievalRequest
    ) -> None:
        self.calls.append(query)
        self.entered.put_nowait(query)
        try:
            await self.gate.enter()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise

    def _finish(self) -> None:
        self.trace.append("read.finished")
        self.finished.put_nowait(None)


@dataclass(frozen=True)
class ForeignReader:
    """Malformed handoff identity, with no resource or fake runtime behavior."""

    session_id: model.SessionId
    policy: model.SessionPolicy

    async def resolve_record(self, reference: model.EvidenceReference) -> EvidencePage:
        raise AssertionError("mismatched read source must never be queried")

    async def retrieve(self, request: EvidenceRetrievalRequest) -> EvidencePage:
        raise AssertionError("mismatched read source must never be queried")


class LiveCase:
    def __init__(
        self,
        journal: SqliteEvidenceJournal,
        backend: BackendFixture,
        runtime: ReadRuntime | None = None,
    ) -> None:
        self.runtime = (
            runtime
            if runtime is not None
            else cast("ReadRuntime", rt.ObservationRuntime())
        )
        self.backend = backend
        # Generic fixture provenance is intentionally not durable. Supply the
        # smallest persistable envelope for this journal-owning test, preserving
        # each fixture's reported capabilities, timestamp domain and loss scope.
        backend.connection.descriptor = replace(
            backend.connection.descriptor,
            connection_provenance=model.PersistedConnectionProvenance(
                model.ConnectionProvenanceSnapshot(
                    envelope_version=1,
                    backend_kind="fixture/evidence-ownership",
                    backend_schema_version=1,
                    fields=(model.ProvenanceField("transport", "simulated"),),
                )
            ),
        )
        self.recorder = RecorderProbe(journal)
        self.reader = ReaderProbe(journal, self.recorder.trace)
        self.preparation = FixtureLifecycleGate()
        open_gate = getattr(backend.backend, "open_gate", None)
        assert isinstance(open_gate, FixtureLifecycleGate)
        self.backend_open = open_gate
        self.received_profiles: list[profile.ResolvedDutProfile] = []
        self.tasks: list[asyncio.Task[Any]] = []

    @property
    def session_id(self) -> model.SessionId:
        return self.recorder.session_id

    def attach(
        self,
        *,
        mode: Literal["live", "legacy", "none"] = "live",
        override: access.PreparedEvidenceAccess | None = None,
    ) -> asyncio.Task[rt.RuntimeStatus]:
        if mode == "legacy":
            prepared = rt.PreparedObservationRun(self.recorder, self.backend.backend)
        else:
            read_access = (
                override
                or access.PreparedEvidenceAccess(
                    self.session_id,
                    replace(self.recorder.policy),
                    live_reader=self.reader,
                )
                if mode == "live"
                else None
            )
            constructor = cast(
                "Callable[..., rt.PreparedObservationRun]", rt.PreparedObservationRun
            )
            prepared = constructor(
                recorder=self.recorder,
                backend=self.backend.backend,
                evidence_access=read_access,
            )

        async def prepare(
            resolved: profile.ResolvedDutProfile,
        ) -> rt.PreparedObservationRun:
            self.received_profiles.append(resolved)
            await self.preparation.enter()
            return prepared

        task = asyncio.create_task(self.runtime.attach(_profile(), prepare))
        self.tasks.append(task)
        return task

    def read(self, kind: QueryKind) -> asyncio.Task[access.RunEvidencePage]:
        task = asyncio.create_task(_query(self.runtime, kind, self.session_id))
        self.tasks.append(task)
        return task

    def detach(self) -> asyncio.Task[rt.RuntimeStatus]:
        task = asyncio.create_task(self.runtime.detach())
        self.tasks.append(task)
        return task

    async def finish(self) -> None:
        for gate in (
            self.preparation,
            self.backend_open,
            self.recorder.final_append,
            self.recorder.close_gate,
            self.reader.gate,
            self.backend.connection.read_gate,
            self.backend.connection.event_gate,
            self.backend.connection.consumer_exit_gate,
            self.backend.connection.close_gate,
        ):
            gate.allow.set()
        try:
            await _await(asyncio.gather(*self.tasks, return_exceptions=True))
            await _await(self.runtime.detach())
        finally:
            # Harness fallback, never proof that runtime confirmed recorder close.
            await _await(self.recorder.journal.close())


@pytest.fixture(params=BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"])
def backend_factory(request: pytest.FixtureRequest) -> BackendFixtureFactory:
    return cast("BackendFixtureFactory", request.param)


@pytest.fixture
def backend(backend_factory: BackendFixtureFactory) -> BackendFixture:
    return backend_factory()


@pytest_asyncio.fixture
async def case(tmp_path: Path, backend: BackendFixture) -> AsyncIterator[LiveCase]:
    journal = await SqliteEvidenceJournal.create(
        tmp_path / "live.sqlite3", _profile().session_policy
    )
    source = LiveCase(journal, backend)
    try:
        yield source
    finally:
        await source.finish()


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_no_run_rejects_without_reading_or_changing_status(
    case: LiveCase, kind: QueryKind
) -> None:
    before = case.runtime.status()
    with pytest.raises(access.EvidenceReadRejected) as rejected:
        await _query(case.runtime, kind, case.session_id)
    assert rejected.value.kind == "no_associated_session"
    assert case.runtime.status() == before and case.reader.calls == []


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_unknown_session_during_preparation_has_no_association(
    case: LiveCase, kind: QueryKind
) -> None:
    case.preparation.allow.clear()
    attach = case.attach(mode="legacy")
    await _await(case.preparation.entered.wait())
    before = case.runtime.status()
    assert before.state is rt.RuntimeState.ATTACHING and before.session_id is None
    with pytest.raises(access.EvidenceReadRejected) as rejected:
        await _query(case.runtime, kind, case.session_id)
    assert rejected.value.kind == "no_associated_session"
    assert case.runtime.status() == before and case.reader.calls == []
    case.preparation.allow.set()
    assert (await _await(attach)).state is rt.RuntimeState.ACTIVE


@pytest.mark.parametrize("mode", ["legacy", "none"])
@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_missing_optional_access_preserves_attach_and_rejects_read(
    case: LiveCase, mode: Literal["legacy", "none"], kind: QueryKind
) -> None:
    active = await _await(case.attach(mode=mode))
    assert active.state is rt.RuntimeState.ACTIVE
    before = case.runtime.status()
    with pytest.raises(access.EvidenceReadRejected) as rejected:
        await _query(case.runtime, kind, case.session_id)
    assert rejected.value.kind == "read_unavailable"
    assert case.runtime.status() == before and case.reader.calls == []
    assert case.backend.connection.consumer_calls == 1


@pytest.mark.asyncio
async def test_legacy_prepared_constructor_has_explicit_null_read_access(
    case: LiveCase,
) -> None:
    prepared = rt.PreparedObservationRun(case.recorder, case.backend.backend)
    absent = object()
    assert getattr(prepared, "evidence_access", absent) is None


@pytest.mark.parametrize("field", ["session_id", "policy"])
@pytest.mark.asyncio
async def test_handoff_mismatch_rejects_before_backend_open_and_closes_recorder(
    case: LiveCase, field: str
) -> None:
    foreign = ForeignReader(
        model.SessionId("different-session")
        if field == "session_id"
        else case.session_id,
        replace(case.recorder.policy, max_retained_records=101)
        if field == "policy"
        else case.recorder.policy,
    )
    override = access.PreparedEvidenceAccess(
        foreign.session_id, foreign.policy, live_reader=foreign
    )
    result = await _await(case.attach(override=override))
    assert result.state is rt.RuntimeState.FAILED
    assert result.primary_issue == rt.RuntimeIssue(
        rt.RuntimeIssueSource.INTERNAL_CONTRACT, "internal_contract_failure"
    )
    assert result.session_id == case.session_id and result.recorder_close_confirmed
    assert (
        case.recorder.close_calls == 1 and case.backend.connection.consumer_calls == 0
    )
    assert not case.backend_open.entered.is_set() and case.reader.calls == []


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_active_reads_use_supplied_port_and_same_journal_without_new_owner(
    case: LiveCase, kind: QueryKind, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = await _await(case.attach())
    before = case.runtime.status()

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("live retrieval must not open another database or RX stream")

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", forbidden)
        patch.setattr(case.backend.connection, "events", forbidden)
        report = await _await(_query(case.runtime, kind, case.session_id))
    assert report.run_id == active.run_id and report.session_id == case.session_id
    assert report.page.records[0].sequence == 0
    assert isinstance(report.page.records[0], model.SegmentStartedEvidence)
    assert len(case.reader.calls) == 1 and case.backend.connection.consumer_calls == 1
    assert case.runtime.status() == before and not before.attach_admissible
    assert case.recorder.close_calls == 0


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_live_reads_work_after_transfer_before_backend_open(
    case: LiveCase, kind: QueryKind
) -> None:
    case.backend_open.allow.clear()
    attach = case.attach()
    await _await(case.backend_open.entered.wait())
    before = case.runtime.status()
    assert (
        before.state is rt.RuntimeState.ATTACHING
        and before.session_id == case.session_id
    )
    report = await _await(_query(case.runtime, kind, case.session_id))
    assert report.run_id == before.run_id and report.page.records == ()
    assert (
        case.runtime.status() == before and case.backend.connection.consumer_calls == 0
    )
    case.backend_open.allow.set()
    assert (await _await(attach)).state is rt.RuntimeState.ACTIVE


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_different_known_session_rejects_before_source_query(
    case: LiveCase, kind: QueryKind
) -> None:
    await _await(case.attach())
    before = case.runtime.status()
    with pytest.raises(access.EvidenceReadRejected) as rejected:
        await _query(case.runtime, kind, model.SessionId("unrelated-session"))
    assert rejected.value.kind == "session_not_associated"
    assert case.reader.calls == [] and case.runtime.status() == before


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.parametrize("rejection", ["busy", "invalid_request"])
@pytest.mark.asyncio
async def test_rejected_attach_preserves_current_read_association(
    case: LiveCase, kind: QueryKind, rejection: str
) -> None:
    active = await _await(case.attach())
    before = case.runtime.status()

    async def forbidden_prepare(
        _: profile.ResolvedDutProfile,
    ) -> rt.PreparedObservationRun:
        raise AssertionError("rejected attach must not prepare another run")

    with pytest.raises(rt.RuntimeRejectedError) as rejected:
        await case.runtime.attach(
            _profile()
            if rejection == "busy"
            else cast("profile.ResolvedDutProfile", None),
            forbidden_prepare,
        )
    assert rejected.value.kind.value == rejection
    report = await _await(_query(case.runtime, kind, case.session_id))
    assert report.run_id == active.run_id and case.runtime.status() == before


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_new_attach_clears_old_selection_before_new_session_exists(
    case: LiveCase,
    kind: QueryKind,
    tmp_path: Path,
    backend_factory: BackendFixtureFactory,
) -> None:
    old = await _await(case.attach())
    await _await(case.runtime.detach())
    next_journal = await SqliteEvidenceJournal.create(
        tmp_path / "next.sqlite3", _profile().session_policy
    )
    next_case = LiveCase(next_journal, backend_factory(), runtime=case.runtime)
    next_case.preparation.allow.clear()
    entered, admit = asyncio.Event(), asyncio.Event()

    async def delayed_request() -> access.RunEvidencePage:
        # Capture only request data; until Core entry it holds no association lease.
        entered.set()
        await admit.wait()
        return await _query(case.runtime, kind, case.session_id)

    old_request = asyncio.create_task(delayed_request())
    case.tasks.append(old_request)
    try:
        await _await(entered.wait())
        next_attach = next_case.attach()
        await _await(next_case.preparation.entered.wait())
        pending = case.runtime.status()
        assert pending.run_id != old.run_id and pending.session_id is None
        admit.set()
        with pytest.raises(access.EvidenceReadRejected) as rejected:
            await _await(old_request)
        assert rejected.value.kind == "no_associated_session"
        next_case.preparation.allow.set()
        new = await _await(next_attach)
        with pytest.raises(access.EvidenceReadRejected) as rejected:
            await _query(case.runtime, kind, case.session_id)
        assert rejected.value.kind == "session_not_associated"
        report = await _query(case.runtime, kind, next_case.session_id)
        assert report.run_id == new.run_id and report.run_id != old.run_id
        assert case.reader.calls == []
    finally:
        admit.set()
        await next_case.finish()


@pytest.mark.asyncio
async def test_eight_read_leases_reject_ninth_without_queue_and_release_after_settlement(
    case: LiveCase,
) -> None:
    await _await(case.attach())
    case.reader.gate.allow.clear()
    reads = [case.read("record" if n % 2 == 0 else "page") for n in range(8)]
    for _ in reads:
        await _await(case.reader.entered.get())
    before = case.runtime.status()
    with pytest.raises(access.EvidenceReadRejected) as rejected:
        await _await(_query(case.runtime, "page", case.session_id))
    assert rejected.value.kind == "read_capacity" and len(case.reader.calls) == 8
    with pytest.raises(access.EvidenceReadRejected) as rejected:
        await _await(_query(case.runtime, "record", model.SessionId("wrong-session")))
    assert rejected.value.kind == "session_not_associated"
    assert case.runtime.status() == before
    reads[0].cancel()
    await _checkpoint()
    assert not reads[0].done() and case.reader.cancelled == 0
    with pytest.raises(access.EvidenceReadRejected) as rejected:
        await _await(_query(case.runtime, "record", case.session_id))
    assert rejected.value.kind == "read_capacity" and len(case.reader.calls) == 8
    case.reader.gate.allow.set()
    reports = await _await(asyncio.gather(*reads, return_exceptions=True))
    assert isinstance(reports[0], asyncio.CancelledError)
    assert all(
        isinstance(report, access.RunEvidencePage) and report.run_id == before.run_id
        for report in reports[1:]
    )
    assert (await _query(case.runtime, "page", case.session_id)).run_id == before.run_id
    assert len(case.reader.calls) == 9


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_cancel_before_core_admission_submits_no_read_or_lifecycle_work(
    case: LiveCase, kind: QueryKind
) -> None:
    await _await(case.attach())
    before = case.runtime.status()
    ready, allow = asyncio.Event(), asyncio.Event()

    async def not_admitted() -> access.RunEvidencePage:
        ready.set()
        await allow.wait()
        return await _query(case.runtime, kind, case.session_id)

    task = asyncio.create_task(not_admitted())
    case.tasks.append(task)
    await _await(ready.wait())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert case.reader.calls == [] and case.runtime.status() == before
    assert (await _query(case.runtime, kind, case.session_id)).run_id == before.run_id


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_cancel_after_admission_joins_private_read_without_cancelling_capture(
    case: LiveCase, kind: QueryKind
) -> None:
    active = await _await(case.attach())
    case.reader.gate.allow.clear()
    read = case.read(kind)
    await _await(case.reader.entered.get())
    read.cancel()
    await _checkpoint()
    read.cancel()
    await _checkpoint()
    assert not read.done() and case.reader.cancelled == 0
    assert case.runtime.status().state is rt.RuntimeState.ACTIVE
    assert case.recorder.close_calls == 0 and not case.backend.connection.closed
    case.reader.gate.allow.set()
    with pytest.raises(asyncio.CancelledError):
        await _await(read)
    await _await(case.reader.finished.get())
    report = await _query(case.runtime, kind, case.session_id)
    assert report.run_id == active.run_id and case.reader.cancelled == 0


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_journal_failure_releases_lease_without_changing_capture_facts(
    case: LiveCase, kind: QueryKind
) -> None:
    await _await(case.attach())
    before = case.runtime.status()
    failure = JournalFailure(JournalOperation.RETRIEVE, JournalFailureKind.BUSY)
    case.reader.failure = failure
    with pytest.raises(JournalFailure) as rejected:
        await _query(case.runtime, kind, case.session_id)
    assert rejected.value is failure and case.runtime.status() == before
    case.reader.failure = None
    assert (await _query(case.runtime, kind, case.session_id)).run_id == before.run_id
    assert (
        case.recorder.close_calls == 0 and case.backend.connection.consumer_calls == 1
    )


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_reads_remain_live_while_acquisition_is_still_draining(
    case: LiveCase, kind: QueryKind
) -> None:
    active = await _await(case.attach())
    case.recorder.final_append.allow.clear()
    detach = case.detach()
    await _await(case.recorder.final_append.entered.wait())
    before = case.runtime.status()
    assert before.state is rt.RuntimeState.DETACHING and not before.owner_settled
    report = await _query(case.runtime, kind, case.session_id)
    assert report.run_id == active.run_id and case.recorder.close_calls == 0
    assert not detach.done() and case.runtime.status() == before
    case.recorder.final_append.allow.set()
    assert (await _await(detach)).recorder_close_confirmed


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_detach_joins_pinned_read_then_seals_admission_before_recorder_close(
    case: LiveCase, kind: QueryKind, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = await _await(case.attach())
    acquisition_joined = asyncio.Event()
    original_join = Acquisition.join_terminated

    async def observed_join(acquisition: Acquisition) -> AcquisitionSnapshot:
        snapshot = await original_join(acquisition)
        acquisition_joined.set()
        return snapshot

    # Observe the real normalized acquisition join; never replace its behavior.
    monkeypatch.setattr(Acquisition, "join_terminated", observed_join)
    case.reader.gate.allow.clear()
    case.recorder.close_gate.allow.clear()
    read = case.read(kind)
    await _await(case.reader.entered.get())
    detach = case.detach()
    await _await(acquisition_joined.wait())
    await _checkpoint()
    assert not detach.done() and case.recorder.close_calls == 0
    assert not case.runtime.status().attach_admissible
    with pytest.raises(access.EvidenceReadRejected) as rejected_read:
        await _await(_query(case.runtime, kind, case.session_id))
    assert rejected_read.value.kind == "read_unavailable"
    assert len(case.reader.calls) == 1 and not read.done()

    # A lifecycle call must reject promptly rather than deadlock on a lock held
    # across read joining. Its preparation callback is never invoked.
    async def forbidden_prepare(
        _: profile.ResolvedDutProfile,
    ) -> rt.PreparedObservationRun:
        raise AssertionError("join must not admit another physical owner")

    with pytest.raises(rt.RuntimeRejectedError) as rejected:
        await _await(case.runtime.attach(_profile(), forbidden_prepare))
    assert rejected.value.kind is rt.RuntimeRejectedKind.BUSY
    case.reader.gate.allow.set()
    report = await _await(read)
    await _await(case.recorder.close_gate.entered.wait())
    assert report.run_id == active.run_id and report.session_id == case.session_id
    assert case.recorder.trace.index("read.finished") < case.recorder.trace.index(
        "recorder.close_entered"
    )
    with pytest.raises(access.EvidenceReadRejected) as rejected_read:
        await _await(_query(case.runtime, kind, case.session_id))
    assert rejected_read.value.kind == "read_unavailable"
    assert len(case.reader.calls) == 1 and not detach.done()
    case.recorder.close_gate.allow.set()
    terminal = await _await(detach)
    assert terminal.state is rt.RuntimeState.TERMINATED
    assert (
        terminal.owner_settled
        and terminal.recorder_close_confirmed
        and terminal.attach_admissible
    )
    # A live-only access capability cannot reopen after recorder closure, but the
    # last known session stays associated for explicit unavailable/mismatch results.
    with pytest.raises(access.EvidenceReadRejected) as rejected_read:
        await _query(case.runtime, kind, case.session_id)
    assert rejected_read.value.kind == "read_unavailable"
    with pytest.raises(access.EvidenceReadRejected) as rejected_read:
        await _query(case.runtime, kind, model.SessionId("unrelated"))
    assert rejected_read.value.kind == "session_not_associated"
    assert case.runtime.status() == terminal and case.recorder.close_calls == 1


async def _invalid_read(
    runtime: ReadRuntime, kind: QueryKind
) -> access.RunEvidencePage:
    method = getattr(runtime, "read_record" if kind == "record" else "read_page", None)
    assert callable(method), f"T008 ObservationRuntime.read_{kind} is not implemented"
    if kind == "record":
        return await runtime.read_record(cast("model.EvidenceReference", object()))
    return await runtime.read_page(cast("EvidenceRetrievalRequest", object()))


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_owner_context_invalid_argument_precedes_association_checks(
    kind: QueryKind,
) -> None:
    runtime = cast("ReadRuntime", rt.ObservationRuntime())
    before = runtime.status()
    with pytest.raises(rt.RuntimeRejectedError) as rejected:
        await _invalid_read(runtime, kind)
    assert rejected.value.kind is rt.RuntimeRejectedKind.INVALID_REQUEST
    assert runtime.status() == before


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.parametrize(
    "context", ["other-loop", "other-thread", "no-running-loop", "closed-owner"]
)
def test_wrong_context_precedes_argument_validation_or_resource_work(
    kind: QueryKind, context: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = asyncio.new_event_loop()

    async def construct() -> ReadRuntime:
        return cast("ReadRuntime", rt.ObservationRuntime())

    runtime = owner.run_until_complete(construct())

    async def snapshot() -> rt.RuntimeStatus:
        return runtime.status()

    before = owner.run_until_complete(snapshot())

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("wrong context must reject before locking/scheduling/resource work")

    if context == "closed-owner":
        owner.close()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(asyncio.Lock, "acquire", forbidden)
            patch.setattr(asyncio, "create_task", forbidden)
            patch.setattr(sqlite3, "connect", forbidden)
            with pytest.raises(rt.RuntimeRejectedError) as rejected:
                if context == "no-running-loop":
                    coroutine = _invalid_read(runtime, kind)
                    try:
                        coroutine.send(None)
                        pytest.fail("context must reject before its first await")
                    finally:
                        coroutine.close()
                elif context == "other-thread":
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(
                            lambda: asyncio.run(_invalid_read(runtime, kind))
                        ).result(timeout=3)
                else:
                    asyncio.run(_invalid_read(runtime, kind))
            assert rejected.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT
        if not owner.is_closed():
            assert owner.run_until_complete(snapshot()) == before
    finally:
        owner.close()


# T017: terminal association/cleanup RED contracts. All runtime policy remains
# production code; these probes gate actual owned read-only SQLite boundaries.


def _t017_cleanup(runtime: ReadRuntime) -> bool:
    value = getattr(runtime, "evidence_read_cleanup_confirmed", None)
    assert type(value) is bool, "T018 runtime read-cleanup latch is not implemented"
    return value


async def _t017_reached(event: asyncio.Event, task: asyncio.Task[Any]) -> None:
    notification = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait(
            (notification, task), timeout=3, return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            await task  # Missing terminal admission stays an explicit RED failure.
            pytest.fail("terminal request bypassed its owned source boundary")
        assert notification in done, "terminal source boundary was never entered"
    finally:
        notification.cancel()
        await asyncio.gather(notification, return_exceptions=True)


class _T017OwnedReader:
    def __init__(
        self, raw: access.OwnedEvidenceReadPort, source: _T017TerminalSource
    ) -> None:
        self.raw = raw
        self.source = source
        self.close_calls = 0
        self.close_gate = FixtureLifecycleGate()
        self.close_error: JournalFailure | None = None

    @property
    def session_id(self) -> model.SessionId:
        return self.raw.session_id

    @property
    def policy(self) -> model.SessionPolicy:
        return self.raw.policy

    async def resolve_record(self, reference: model.EvidenceReference) -> EvidencePage:
        await self.source.read_gate.enter()
        if self.source.read_error is not None:
            raise self.source.read_error
        return await self.raw.resolve_record(reference)

    async def retrieve(self, request: EvidenceRetrievalRequest) -> EvidencePage:
        await self.source.read_gate.enter()
        if self.source.read_error is not None:
            raise self.source.read_error
        return await self.raw.retrieve(request)

    async def close(self) -> None:
        self.close_calls += 1
        await self.source.close_gate.enter()
        await self.close_gate.enter()
        await self.raw.close()
        self.source.closed += 1
        # Inject an unacknowledged close after actual cleanup to avoid test leaks.
        if self.close_error is not None:
            raise self.close_error
        if self.source.close_error is not None:
            raise self.source.close_error


class _T017TerminalSource:
    def __init__(self, case: LiveCase, path: Path) -> None:
        self.session_id = case.session_id
        self.policy = case.recorder.policy
        self.target = capture_terminal_target(
            path, session_id=self.session_id, policy=self.policy
        )
        assert self.target is not None
        self.open_gate = FixtureLifecycleGate()
        self.read_gate = FixtureLifecycleGate()
        self.close_gate = FixtureLifecycleGate()
        self.open_calls = 0
        self.closed = 0
        self.open_error: Exception | None = None
        self.read_error: JournalFailure | None = None
        self.close_error: JournalFailure | None = None
        self.readers: list[_T017OwnedReader] = []

    async def open(self) -> access.OwnedEvidenceReadPort:
        self.open_calls += 1
        await self.open_gate.enter()
        if self.open_error is not None:
            raise self.open_error
        assert self.target is not None
        raw = await open_terminal_reader(self.target)
        reader = _T017OwnedReader(raw, self)
        self.readers.append(reader)
        return reader

    def access(self, case: LiveCase) -> access.PreparedEvidenceAccess:
        return access.PreparedEvidenceAccess(
            self.session_id, self.policy, case.reader, self.open
        )

    async def finish(self) -> None:
        for gate in (self.open_gate, self.read_gate, self.close_gate):
            gate.allow.set()
        # Harness fallback only, never a runtime cleanup acknowledgment.
        for reader in self.readers:
            reader.close_gate.allow.set()
            await reader.raw.close()


@pytest_asyncio.fixture
async def terminal_case(
    case: LiveCase, tmp_path: Path
) -> AsyncIterator[tuple[LiveCase, _T017TerminalSource]]:
    source = _T017TerminalSource(case, tmp_path / "live.sqlite3")
    try:
        yield case, source
    finally:
        for gate in (source.open_gate, source.read_gate, source.close_gate):
            gate.allow.set()
        for reader in source.readers:
            reader.close_gate.allow.set()
        await _await(asyncio.gather(*case.tasks, return_exceptions=True))
        await source.finish()


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.parametrize("stop", ["detach", "disconnect", "stream_failure"])
@pytest.mark.asyncio
async def test_t017_terminal_query_closes_reader_and_preserves_lifecycle_facts(
    terminal_case: tuple[LiveCase, _T017TerminalSource], kind: QueryKind, stop: str
) -> None:
    case, source = terminal_case
    active = await _await(case.attach(override=source.access(case)))
    live = await _query(case.runtime, kind, case.session_id)
    assert live.run_id == active.run_id and source.open_calls == 0
    if stop == "disconnect":
        await case.backend.connection.disconnect()
        await _await(case.recorder.close_gate.entered.wait())
    elif stop == "stream_failure":
        await case.backend.connection.end_stream_unexpectedly()
        await _await(case.recorder.close_gate.entered.wait())
    terminal = await _await(case.runtime.detach())
    assert terminal.owner_settled and terminal.recorder_close_confirmed
    report = await _query(case.runtime, kind, case.session_id)
    assert report.run_id == active.run_id and report.session_id == active.session_id
    assert report.page.records[0] == live.page.records[0]
    assert source.open_calls == source.closed == 1
    assert source.readers[0].close_calls == 1 and case.recorder.close_calls == 1
    assert case.backend.connection.consumer_calls == 1
    assert case.runtime.status() == terminal and _t017_cleanup(case.runtime)


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_t017_terminal_opener_is_not_used_during_recorder_close(
    terminal_case: tuple[LiveCase, _T017TerminalSource], kind: QueryKind
) -> None:
    case, source = terminal_case
    await _await(case.attach(override=source.access(case)))
    case.recorder.close_gate.allow.clear()
    detach = case.detach()
    try:
        await _await(case.recorder.close_gate.entered.wait())
        before = case.runtime.status()
        assert not before.owner_settled and not before.recorder_close_confirmed
        with pytest.raises(access.EvidenceReadRejected) as caught:
            await _query(case.runtime, kind, case.session_id)
        assert caught.value.kind == "read_unavailable" and source.open_calls == 0
        assert case.runtime.status() == before
    finally:
        case.recorder.close_gate.allow.set()
        await _await(detach)


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_t017_unconfirmed_recorder_close_forbids_available_terminal_opener(
    terminal_case: tuple[LiveCase, _T017TerminalSource],
    monkeypatch: pytest.MonkeyPatch,
    kind: QueryKind,
) -> None:
    case, source = terminal_case
    close = case.recorder.close

    async def unconfirmed() -> None:
        await close()
        raise JournalFailure(JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE)

    monkeypatch.setattr(case.recorder, "close", unconfirmed)
    await _await(case.attach(override=source.access(case)))
    terminal = await _await(case.runtime.detach())
    assert terminal.owner_settled and not terminal.recorder_close_confirmed
    assert not terminal.attach_admissible
    with pytest.raises(access.EvidenceReadRejected) as caught:
        await _query(case.runtime, kind, case.session_id)
    assert caught.value.kind == "read_unavailable" and source.open_calls == 0
    assert case.runtime.status() == terminal


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_t017_physical_release_uncertainty_does_not_block_closed_evidence(
    terminal_case: tuple[LiveCase, _T017TerminalSource],
    monkeypatch: pytest.MonkeyPatch,
    kind: QueryKind,
) -> None:
    case, source = terminal_case
    close = case.backend.connection.close

    async def unconfirmed() -> None:
        await close()
        raise RuntimeError("test-only unacknowledged physical close")

    monkeypatch.setattr(case.backend.connection, "close", unconfirmed)
    await _await(case.attach(override=source.access(case)))
    terminal = await _await(case.runtime.detach())
    assert terminal.owner_settled and terminal.recorder_close_confirmed
    assert not terminal.physical_release_confirmed and not terminal.attach_admissible
    report = await _query(case.runtime, kind, case.session_id)
    assert report.run_id == terminal.run_id and source.closed == 1
    assert case.runtime.status() == terminal and _t017_cleanup(case.runtime)


@pytest.mark.parametrize("known", [False, True])
@pytest.mark.asyncio
async def test_t017_failed_preparation_without_target_never_discovers_a_source(
    terminal_case: tuple[LiveCase, _T017TerminalSource], known: bool
) -> None:
    case, source = terminal_case
    await case.recorder.journal.close()
    failure = rt.PreparationFailure(
        rt.RuntimeIssue(
            rt.RuntimeIssueSource.PREPARATION, JournalFailureKind.IO_FAILURE
        ),
        session_id=case.session_id if known else None,
        recorder_close_confirmed=True,
    )

    async def prepare(
        resolved: profile.ResolvedDutProfile,
    ) -> rt.PreparedObservationRun:
        raise failure

    terminal = await _await(case.runtime.attach(_profile(), prepare))
    with pytest.raises(access.EvidenceReadRejected) as caught:
        await _query(case.runtime, "page", case.session_id)
    assert caught.value.kind == (
        "read_unavailable" if known else "no_associated_session"
    )
    assert source.open_calls == 0 and terminal.owner_settled
    assert terminal.primary_issue == failure.primary_issue
    assert case.runtime.status() == terminal


@pytest.mark.parametrize("confirmed", [False, True])
@pytest.mark.asyncio
async def test_t017_known_failed_preparation_transfers_only_optional_terminal_access(
    terminal_case: tuple[LiveCase, _T017TerminalSource], confirmed: bool
) -> None:
    case, source = terminal_case
    await case.recorder.journal.close()
    assert "terminal_evidence_access" in rt.PreparationFailure.__dataclass_fields__, (
        "T018 PreparationFailure terminal evidence handoff is not implemented"
    )
    constructor = cast("Callable[..., rt.PreparationFailure]", rt.PreparationFailure)
    failure = constructor(
        primary_issue=rt.RuntimeIssue(
            rt.RuntimeIssueSource.PREPARATION, JournalFailureKind.IO_FAILURE
        ),
        session_id=case.session_id,
        recorder_close_confirmed=confirmed,
        cleanup_issue=None
        if confirmed
        else rt.RuntimeIssue(
            rt.RuntimeIssueSource.RECORDER_CLOSE, JournalFailureKind.IO_FAILURE
        ),
        terminal_evidence_access=access.PreparedEvidenceAccess(
            case.session_id, case.recorder.policy, terminal_opener=source.open
        ),
    )

    async def prepare(
        resolved: profile.ResolvedDutProfile,
    ) -> rt.PreparedObservationRun:
        raise failure

    terminal = await _await(case.runtime.attach(_profile(), prepare))
    assert terminal.primary_issue == failure.primary_issue and terminal.owner_settled
    assert terminal.recorder_close_confirmed is confirmed
    if confirmed:
        report = await _query(case.runtime, "page", case.session_id)
        assert report.page.records == () and report.run_id == terminal.run_id
        assert source.open_calls == source.closed == 1
    else:
        with pytest.raises(access.EvidenceReadRejected) as caught:
            await _query(case.runtime, "page", case.session_id)
        assert caught.value.kind == "read_unavailable" and source.open_calls == 0
    assert case.runtime.status() == terminal


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.parametrize(
    "fault",
    [
        "partial_clean",
        "partial_dirty",
        "unexpected_open",
        "read_clean",
        "read_dirty",
        "close_only",
    ],
)
@pytest.mark.asyncio
async def test_t017_terminal_failures_preserve_primary_and_latch_only_uncertain_cleanup(
    terminal_case: tuple[LiveCase, _T017TerminalSource], kind: QueryKind, fault: str
) -> None:
    case, source = terminal_case
    await _await(case.attach(override=source.access(case)))
    terminal = await _await(case.runtime.detach())
    primary = JournalFailure(JournalOperation.OPEN, JournalFailureKind.SESSION_MISMATCH)
    if fault.startswith("partial"):
        source.open_error = access.EvidenceSourceOpenFailure(
            primary, fault == "partial_clean"
        )
    elif fault == "unexpected_open":
        source.open_error = RuntimeError("private test-only open detail")
    elif fault.startswith("read"):
        primary = JournalFailure(
            JournalOperation.RETRIEVE, JournalFailureKind.IO_FAILURE
        )
        source.read_error = primary
    if fault in {"read_dirty", "close_only"}:
        source.close_error = JournalFailure(
            JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE
        )
        if fault == "close_only":
            primary = source.close_error
    expected = RuntimeError if fault == "unexpected_open" else JournalFailure
    with pytest.raises(expected) as caught:
        await _query(case.runtime, kind, case.session_id)
    if fault == "unexpected_open":
        assert not isinstance(caught.value, access.EvidenceReadRejected)
    else:
        assert isinstance(caught.value, JournalFailure)
        assert caught.value.operation is (
            JournalOperation.OPEN
            if fault.startswith("partial")
            else JournalOperation.CLOSE
            if fault == "close_only"
            else JournalOperation.RETRIEVE
        )
        assert caught.value.kind is (
            JournalFailureKind.SESSION_MISMATCH
            if fault.startswith("partial")
            else JournalFailureKind.IO_FAILURE
        )
        assert caught.value.detail is None
    dirty = fault in {"partial_dirty", "unexpected_open", "read_dirty", "close_only"}
    assert _t017_cleanup(case.runtime) is (not dirty)
    assert case.runtime.status() == terminal and terminal.attach_admissible
    if source.readers:
        assert source.closed == 1 and source.readers[0].close_calls == 1
    source.open_error = source.read_error = source.close_error = None
    if dirty:
        with pytest.raises(access.EvidenceReadRejected) as unavailable:
            await _query(case.runtime, kind, case.session_id)
        assert unavailable.value.kind == "read_unavailable" and source.open_calls == 1
        assert await _await(case.runtime.detach()) == terminal
        assert not _t017_cleanup(case.runtime), (
            "detach must not reset read cleanup uncertainty"
        )
    else:
        report = await _query(case.runtime, kind, case.session_id)
        assert report.run_id == terminal.run_id and source.open_calls == 2


@pytest.mark.asyncio
async def test_t017_cleanup_latch_starts_confirmed_without_changing_capture_status(
    backend: BackendFixture,
) -> None:
    runtime = cast("ReadRuntime", rt.ObservationRuntime())
    before = runtime.status()
    assert _t017_cleanup(runtime)
    assert runtime.status() == before and before.attach_admissible


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_t017_pinned_old_terminal_read_finishes_after_new_attach_replaces_selection(
    terminal_case: tuple[LiveCase, _T017TerminalSource],
    kind: QueryKind,
    tmp_path: Path,
    backend_factory: BackendFixtureFactory,
) -> None:
    case, source = terminal_case
    old = await _await(case.attach(override=source.access(case)))
    await _await(case.runtime.detach())
    source.open_gate.allow.clear()
    pinned = case.read(kind)
    next_case: LiveCase | None = None
    try:
        await _t017_reached(source.open_gate.entered, pinned)
        journal = await SqliteEvidenceJournal.create(
            tmp_path / "next-terminal.sqlite3", _profile().session_policy
        )
        next_case = LiveCase(journal, backend_factory(), runtime=case.runtime)
        next_case.preparation.allow.clear()
        attached = next_case.attach()
        await _await(next_case.preparation.entered.wait())
        pending = case.runtime.status()
        assert pending.run_id != old.run_id and pending.session_id is None
        with pytest.raises(access.EvidenceReadRejected) as caught:
            await _query(case.runtime, kind, case.session_id)
        assert caught.value.kind == "no_associated_session"
        source.open_gate.allow.set()
        report = await _await(pinned)
        assert report.run_id == old.run_id and report.session_id == old.session_id
        assert source.closed == 1 and case.runtime.status() == pending
        next_case.preparation.allow.set()
        new = await _await(attached)
        with pytest.raises(access.EvidenceReadRejected) as caught:
            await _query(case.runtime, kind, case.session_id)
        assert caught.value.kind == "session_not_associated" and source.open_calls == 1
        assert (
            await _query(case.runtime, kind, next_case.session_id)
        ).run_id == new.run_id
    finally:
        source.open_gate.allow.set()
        if next_case is not None:
            await next_case.finish()


@pytest.mark.asyncio
async def test_t017_uncertain_close_seals_admission_before_released_slot_can_be_reused(
    terminal_case: tuple[LiveCase, _T017TerminalSource],
) -> None:
    case, source = terminal_case
    await _await(case.attach(override=source.access(case)))
    terminal = await _await(case.runtime.detach())
    source.close_gate.allow.clear()
    readers = [case.read("page") for _ in range(8)]
    try:
        # Every request must reach its real reader's held close before selecting
        # one failure; independent pinned reads may settle after the latch seals.
        async with asyncio.timeout(3):
            while len(source.readers) < 8 or any(
                r.close_calls != 1 for r in source.readers
            ):
                if any(task.done() for task in readers):
                    for task in readers:
                        if task.done():
                            await task
                    pytest.fail("terminal read returned before reader close")
                await _checkpoint()
        with pytest.raises(access.EvidenceReadRejected) as caught:
            await _query(case.runtime, "page", case.session_id)
        assert caught.value.kind == "read_capacity" and source.open_calls == 8
        close_failure = JournalFailure(
            JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE
        )
        source.readers[0].close_error = close_failure
        for reader in source.readers[1:]:
            reader.close_gate.allow.clear()
        source.close_gate.allow.set()
        done, pending = await asyncio.wait(
            readers, timeout=3, return_when=asyncio.FIRST_COMPLETED
        )
        assert len(done) == 1 and len(pending) == 7
        with pytest.raises(JournalFailure) as failed:
            await next(iter(done))
        assert failed.value.operation is JournalOperation.CLOSE
        assert failed.value.kind is JournalFailureKind.IO_FAILURE
        assert not _t017_cleanup(case.runtime)
        with pytest.raises(access.EvidenceReadRejected) as caught:
            await _query(case.runtime, "page", case.session_id)
        assert caught.value.kind == "read_unavailable" and source.open_calls == 8
        assert case.runtime.status() == terminal
        for reader in source.readers[1:]:
            reader.close_gate.allow.set()
        results = await _await(asyncio.gather(*pending))
        assert all(isinstance(result, access.RunEvidencePage) for result in results)
        assert not _t017_cleanup(case.runtime)
    finally:
        source.close_gate.allow.set()
        for reader in source.readers:
            reader.close_gate.allow.set()


@pytest.mark.asyncio
async def test_t017_dirty_read_cleanup_never_rewrites_attach_eligibility_or_resets_on_new_run(
    terminal_case: tuple[LiveCase, _T017TerminalSource],
    tmp_path: Path,
    backend_factory: BackendFixtureFactory,
) -> None:
    case, source = terminal_case
    await _await(case.attach(override=source.access(case)))
    terminal = await _await(case.runtime.detach())
    source.close_error = JournalFailure(
        JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE
    )
    with pytest.raises(JournalFailure):
        await _query(case.runtime, "page", case.session_id)
    assert not _t017_cleanup(case.runtime)
    assert case.runtime.status() == terminal and terminal.attach_admissible
    journal = await SqliteEvidenceJournal.create(
        tmp_path / "after-read-fault.sqlite3", _profile().session_policy
    )
    next_case = LiveCase(journal, backend_factory(), runtime=case.runtime)
    try:
        active = await _await(next_case.attach())
        assert (
            active.state is rt.RuntimeState.ACTIVE and active.run_id != terminal.run_id
        )
        assert not _t017_cleanup(case.runtime), (
            "new attach cannot reset the incarnation's dirty read latch"
        )
        with pytest.raises(access.EvidenceReadRejected) as caught:
            await _query(case.runtime, "page", next_case.session_id)
        assert caught.value.kind == "read_unavailable" and next_case.reader.calls == []
        assert case.runtime.status() == active and source.open_calls == 1
    finally:
        await next_case.finish()


# T020: existing003 semantic pages/failures must pass through Core unchanged.


@pytest.mark.asyncio
async def test_t020_max_reference_not_found_never_overflows_or_rewrites_page(
    case: LiveCase,
) -> None:
    active = await _await(case.attach())
    before = case.runtime.status()
    reference = model.EvidenceReference(case.session_id, model.SQLITE_INTEGER_MAX)
    expected = await case.recorder.journal.resolve_record(reference)
    actual = await _await(case.runtime.read_record(reference))
    assert actual.page == expected and actual.run_id == active.run_id
    assert actual.page.outcome is EvidencePageOutcome.NOT_FOUND
    assert actual.page.records == () and actual.page.never_existed_range is None
    assert actual.page.snapshot_end_exclusive == 1
    assert case.reader.calls == [reference] and case.runtime.status() == before


@pytest.mark.parametrize(
    "position,outcome", [(0, "complete"), (1, "complete"), (2, "not_found")]
)
@pytest.mark.asyncio
async def test_t020_empty_range_at_or_beyond_next_sequence_keeps003_outcome(
    case: LiveCase, position: int, outcome: str
) -> None:
    await _await(case.attach())
    before = case.runtime.status()
    reference = model.EvidenceRangeReference(case.session_id, position, position)
    request = EvidenceRetrievalRequest(reference, 10, 16384)
    expected = await case.recorder.journal.retrieve(request)
    actual = await _await(case.runtime.read_page(request))
    assert actual.page == expected and actual.page.outcome.value == outcome
    assert actual.page.records == () and actual.page.charged_bytes == 0
    assert actual.page.expired_range is actual.page.never_existed_range is None
    assert actual.page.retention_marker is None and actual.page.continuation is None
    assert not actual.page.truncated
    assert case.reader.calls == [request] and case.runtime.status() == before


@pytest.mark.parametrize("ceiling", ["records", "charged_bytes"])
@pytest.mark.asyncio
async def test_t020_policy_ceiling_rejection_preserves003_failure_and_releases_read_lease(
    case: LiveCase, ceiling: str
) -> None:
    await _await(case.attach())
    before = case.runtime.status()
    policy = case.recorder.policy
    request = EvidenceRetrievalRequest(
        case.session_id,
        policy.max_retrieval_page_records + (ceiling == "records"),
        policy.max_retrieval_page_charged_bytes + (ceiling == "charged_bytes"),
    )
    with pytest.raises(JournalFailure) as oracle:
        await case.recorder.journal.retrieve(request)
    with pytest.raises(JournalFailure) as actual:
        await _await(case.runtime.read_page(request))
    assert actual.value.operation is oracle.value.operation is JournalOperation.RETRIEVE
    assert actual.value.kind is oracle.value.kind is JournalFailureKind.INVALID_INPUT
    assert case.runtime.status() == before and case.recorder.close_calls == 0
    legal = EvidenceRetrievalRequest(
        case.session_id, 1, policy.max_retrieval_page_charged_bytes
    )
    expected = await case.recorder.journal.retrieve(legal)
    assert (await _await(case.runtime.read_page(legal))).page == expected
    assert case.reader.calls == [request, legal]


@pytest.mark.asyncio
async def test_t020_zero_record_shortage_preserves_next_position_and_required_charge(
    case: LiveCase,
) -> None:
    await _await(case.attach())
    request = EvidenceRetrievalRequest(case.session_id, 1, 1)
    expected = await case.recorder.journal.retrieve(request)
    zero = (await _await(case.runtime.read_page(request))).page
    assert zero == expected and zero.outcome is EvidencePageOutcome.COMPLETE
    assert zero.records == () and zero.charged_bytes == 0 and zero.truncated
    assert zero.continuation is not None and zero.continuation.next_sequence == 0
    assert (
        zero.next_record_required_bytes is not None
        and zero.next_record_required_bytes > 1
    )
    again_request = EvidenceRetrievalRequest(case.session_id, 1, 1, zero.continuation)
    again = (await _await(case.runtime.read_page(again_request))).page
    assert again == await case.recorder.journal.retrieve(again_request)
    assert again.continuation == zero.continuation
    assert again.next_record_required_bytes == zero.next_record_required_bytes
    larger = EvidenceRetrievalRequest(
        case.session_id, 1, zero.next_record_required_bytes, again.continuation
    )
    page = (await _await(case.runtime.read_page(larger))).page
    assert page == await case.recorder.journal.retrieve(larger)
    assert [record.sequence for record in page.records] == [0]
    assert page.charged_bytes == zero.next_record_required_bytes
    assert not page.truncated and page.continuation is None


# T026: independent generations, submitted workers and repeated waiter loss.
# Gates hold actual external work; no ownership/admission/cleanup policy is faked.


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.parametrize("stage", ["open", "read", "close"])
@pytest.mark.parametrize("uncertain", [False, True])
@pytest.mark.asyncio
async def test_t026_repeated_terminal_waiter_loss_joins_close_and_preserves_uncertainty(
    terminal_case: tuple[LiveCase, _T017TerminalSource],
    kind: QueryKind,
    stage: str,
    uncertain: bool,
) -> None:
    case, source = terminal_case
    await _await(case.attach(override=source.access(case)))
    terminal = await _await(case.runtime.detach())
    assert _t017_cleanup(case.runtime)
    gate = getattr(source, stage + "_gate")
    gate.allow.clear()
    if uncertain:
        source.close_error = JournalFailure(
            JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE
        )
    task = case.read(kind)
    try:
        await _t017_reached(gate.entered, task)
        for _ in range(3):
            task.cancel()
            await _checkpoint()
            assert not task.done(), "cancelled waiter abandoned submitted reader work"
        assert source.closed == 0 and case.runtime.status() == terminal
        assert _t017_cleanup(case.runtime)
        gate.allow.set()
        with pytest.raises(asyncio.CancelledError):
            await _await(task)
        assert source.closed == 1 and source.open_calls == 1
        assert _t017_cleanup(case.runtime) is (not uncertain)
        assert case.runtime.status() == terminal
        if uncertain:
            with pytest.raises(access.EvidenceReadRejected) as rejected:
                await _query(case.runtime, kind, case.session_id)
            assert rejected.value.kind == "read_unavailable"
            assert source.open_calls == 1
        else:
            report = await _query(case.runtime, kind, case.session_id)
            assert report.run_id == terminal.run_id and source.closed == 2
    finally:
        gate.allow.set()


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.parametrize("uncertain", [False, True])
@pytest.mark.asyncio
async def test_t026_global_eight_lease_bound_and_dirty_seal_span_old_and_new_associations(
    terminal_case: tuple[LiveCase, _T017TerminalSource],
    tmp_path: Path,
    backend_factory: BackendFixtureFactory,
    kind: QueryKind,
    uncertain: bool,
) -> None:
    case, source = terminal_case
    old = await _await(case.attach(override=source.access(case)))
    await _await(case.runtime.detach())
    source.close_gate.allow.clear()
    old_reads = [case.read(kind) for _ in range(7)]
    new: LiveCase | None = None
    try:
        async with asyncio.timeout(3):
            while len(source.readers) != 7 or any(
                r.close_calls != 1 for r in source.readers
            ):
                assert not any(task.done() for task in old_reads)
                await _checkpoint()
        journal = await SqliteEvidenceJournal.create(
            tmp_path / "t026-next.sqlite3", _profile().session_policy
        )
        new = LiveCase(journal, backend_factory(), runtime=case.runtime)
        active = await _await(new.attach())
        assert active.run_id != old.run_id
        new.reader.gate.allow.clear()
        live = new.read(kind)
        await _await(new.reader.entered.get())
        with pytest.raises(access.EvidenceReadRejected) as rejected:
            await _query(new.runtime, kind, new.session_id)
        assert rejected.value.kind == "read_capacity"
        assert len(new.reader.calls) == 1 and source.open_calls == 7
        with pytest.raises(access.EvidenceReadRejected) as rejected:
            await _query(case.runtime, kind, case.session_id)
        assert rejected.value.kind == "session_not_associated"
        for reader in source.readers[1:]:
            reader.close_gate.allow.clear()
        if uncertain:
            source.readers[0].close_error = JournalFailure(
                JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE
            )
        source.close_gate.allow.set()
        done, pending = await asyncio.wait(
            old_reads, timeout=3, return_when=asyncio.FIRST_COMPLETED
        )
        assert len(done) == 1 and len(pending) == 6
        first = next(iter(done))
        if uncertain:
            with pytest.raises(JournalFailure):
                await first
            assert not _t017_cleanup(case.runtime)
            with pytest.raises(access.EvidenceReadRejected) as rejected:
                await _query(new.runtime, kind, new.session_id)
            assert rejected.value.kind == "read_unavailable"
            assert len(new.reader.calls) == 1
        else:
            assert (await first).run_id == old.run_id
            replacement = new.read(kind)
            await _await(new.reader.entered.get())
            assert not replacement.done()
            with pytest.raises(access.EvidenceReadRejected) as rejected:
                await _query(new.runtime, kind, new.session_id)
            assert rejected.value.kind == "read_capacity"
        for reader in source.readers[1:]:
            reader.close_gate.allow.set()
        new.reader.gate.allow.set()
        reports = await _await(asyncio.gather(*pending))
        assert all(report.run_id == old.run_id for report in reports)
        assert (await _await(live)).run_id == active.run_id
        assert case.runtime.status() == active
        assert _t017_cleanup(case.runtime) is (not uncertain)
    finally:
        source.close_gate.allow.set()
        for reader in source.readers:
            reader.close_gate.allow.set()
        if new is not None:
            await new.finish()


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.parametrize("stage", ["live", "open", "read", "close"])
@pytest.mark.asyncio
async def test_t026_submitted_native_worker_is_joined_despite_repeated_waiter_loss_and_detach(
    terminal_case: tuple[LiveCase, _T017TerminalSource],
    monkeypatch: pytest.MonkeyPatch,
    kind: QueryKind,
    stage: str,
) -> None:
    from threading import Event

    from dutchmate_core.adapters import sqlite_evidence, terminal_evidence

    case, source = terminal_case
    await _await(case.attach(override=source.access(case)))
    if stage != "live":
        await _await(case.runtime.detach())
    module = sqlite_evidence if stage == "live" else terminal_evidence
    function = (
        "_open_on_worker"
        if stage == "open"
        else "_close_reader_on_worker"
        if stage == "close"
        else "_resolve_record_on_worker"
        if kind == "record"
        else "_retrieve_page_on_worker"
    )
    original = getattr(module, function)
    loop = asyncio.get_running_loop()
    entered, allow = asyncio.Event(), Event()

    def held(*args: Any) -> Any:
        loop.call_soon_threadsafe(entered.set)
        assert allow.wait(5), "test watchdog: native worker was not released"
        return original(*args)

    monkeypatch.setattr(module, function, held)
    task = case.read(kind)
    detach: asyncio.Task[rt.RuntimeStatus] | None = None
    try:
        await _t017_reached(entered, task)
        for _ in range(3):
            task.cancel()
            await _checkpoint()
            assert not task.done()
        if stage == "live":
            detach = case.detach()
            await _checkpoint()
            assert not detach.done() and case.recorder.close_calls == 0
        else:
            assert source.closed == 0 and case.recorder.close_calls == 1
        allow.set()
        with pytest.raises(asyncio.CancelledError):
            await _await(task)
        if detach is not None:
            terminal = await _await(detach)
            assert terminal.owner_settled and terminal.recorder_close_confirmed
            assert case.reader.cancelled == 0 and case.recorder.close_calls == 1
        else:
            assert source.closed == 1 and len(source.readers) == 1
        assert _t017_cleanup(case.runtime)
    finally:
        allow.set()


@pytest.mark.asyncio
async def test_t026_retention_append_waits_for_submitted_read_then_detach_preserves_snapshot(
    tmp_path: Path,
    backend: BackendFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from threading import Event

    from dutchmate_core.adapters import sqlite_evidence
    from dutchmate_core.evidence import PendingRxBytesEvidence

    resolved = replace(
        _profile(),
        session_policy=replace(_profile().session_policy, max_retained_records=3),
    )
    journal = await SqliteEvidenceJournal.create(
        tmp_path / "t026-retention.sqlite3", resolved.session_policy
    )
    case = LiveCase(journal, backend)
    source = _T017TerminalSource(case, tmp_path / "t026-retention.sqlite3")
    allow = Event()
    try:

        async def prepare(
            value: profile.ResolvedDutProfile,
        ) -> rt.PreparedObservationRun:
            return rt.PreparedObservationRun(
                case.recorder, backend.backend, source.access(case)
            )

        await _await(case.runtime.attach(resolved, prepare))
        first_record = (
            await journal.resolve_record(model.EvidenceReference(journal.session_id, 0))
        ).records[0]
        assert isinstance(first_record, model.SegmentStartedEvidence)
        provenance = first_record.provenance
        for stamp in (1, 2):
            await journal.append(
                PendingRxBytesEvidence(
                    provenance.connection_id,
                    provenance.segment_id,
                    b"before",
                    model.BackendObservationTimestamp(
                        provenance.backend_observation_timestamp_domain.domain_id, stamp
                    ),
                )
            )
        original = sqlite_evidence._retrieve_page_on_worker
        entered = asyncio.Event()
        loop = asyncio.get_running_loop()

        def held(*args: Any) -> EvidencePage:
            loop.call_soon_threadsafe(entered.set)
            assert allow.wait(5), "test watchdog: retained read worker not released"
            return original(*args)

        monkeypatch.setattr(sqlite_evidence, "_retrieve_page_on_worker", held)
        request = EvidenceRetrievalRequest(journal.session_id, 1, 16384)
        read = asyncio.create_task(case.runtime.read_page(request))
        case.tasks.append(read)
        await _t017_reached(entered, read)
        appends = [
            asyncio.create_task(
                journal.append(
                    PendingRxBytesEvidence(
                        provenance.connection_id,
                        provenance.segment_id,
                        b"evict",
                        model.BackendObservationTimestamp(
                            provenance.backend_observation_timestamp_domain.domain_id,
                            stamp,
                        ),
                    )
                )
            )
            for stamp in (3, 4)
        ]
        case.tasks.extend(appends)
        await _checkpoint()
        assert all(not task.done() for task in appends), (
            "append bypassed the query worker gate"
        )
        allow.set()
        first = (await _await(read)).page
        assert first.snapshot_end_exclusive == 3 and first.continuation is not None
        assert [record.sequence for record in first.records] == [0]
        await _await(asyncio.gather(*appends))
        await _await(case.runtime.detach())
        page = (
            await _await(
                case.runtime.read_page(
                    EvidenceRetrievalRequest(
                        journal.session_id, 10, 16384, first.continuation
                    )
                )
            )
        ).page
        assert page.snapshot_end_exclusive == 3 and page.records == ()
        assert page.outcome is EvidencePageOutcome.EXPIRED
        assert page.expired_range == model.SequenceRange(1, 3)
        assert page.retention_marker is not None
        assert page.retention_marker.expired_range == model.SequenceRange(0, 3)
        assert page.continuation is None and not page.truncated
        assert source.closed == 1 and _t017_cleanup(case.runtime)
    finally:
        allow.set()
        await case.finish()
        await source.finish()
