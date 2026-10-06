"""T006 RED contracts for normal observation ownership; no composition edge.

Only the documented public runtime surface is exercised. The small test-only
Protocol permits strict checking before the T008 implementation exists; a
missing constructor fails each test rather than breaking module collection.
"""

import asyncio
import builtins
import io
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from threading import get_ident
from typing import NoReturn, Protocol, cast

import pytest

from dutchmate_core import acquisition as aq
from dutchmate_core import model, profile
from dutchmate_core import runtime as rt
from dutchmate_core.adapters.sqlite_evidence import SqliteEvidenceJournal
from dutchmate_core.backend import (
    Backend,
    BackendConnection,
    BackendFailureKind,
    BackendFailureOperation,
    NormalizedBackendFailure,
)
from dutchmate_core.evidence import (
    EvidenceRecorder,
    JournalFailure,
    JournalFailureKind,
    JournalOperation,
    PendingEvidenceRecord,
    PendingRxBytesEvidence,
    PendingSegmentEndedEvidence,
    PendingSegmentStartedEvidence,
)
from tests.fakes import BasicShapedBackendConnection


class RuntimeContract(Protocol):
    async def attach(
        self,
        profile: profile.ResolvedDutProfile,
        prepare: rt.PrepareObservationRun,
    ) -> rt.RuntimeStatus: ...

    def status(self) -> rt.RuntimeStatus: ...

    async def detach(self) -> rt.RuntimeStatus: ...


def _factory() -> Callable[[], RuntimeContract]:
    constructor = getattr(rt, "ObservationRuntime", None)
    assert constructor is not None, (
        "ObservationRuntime lifecycle is not implemented (T008)"
    )
    return cast("Callable[[], RuntimeContract]", constructor)


def _profile() -> profile.ResolvedDutProfile:
    return profile.ResolvedDutProfile(
        format_version=profile.ProfileFormatVersion(1),
        dut=profile.DutIdentity(id="runtime-fixture", name="Observation fixture"),
        backend=profile.ProfileBackendSelection(
            kind="basic_serial",
            expected_device="explicit-test-device",
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


async def _await[T](work: Awaitable[T]) -> T:
    # A test watchdog, never a timeout added to the product lifecycle contract.
    async with asyncio.timeout(3.0):
        return await work


class Gate:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.allow = asyncio.Event()
        self.allow.set()

    async def enter(self) -> None:
        self.entered.set()
        await self.allow.wait()


class GatedConnection(BasicShapedBackendConnection):
    def __init__(self, harness: RunHarness) -> None:
        super().__init__(
            connection_provenance=model.PersistedConnectionProvenance(
                model.ConnectionProvenanceSnapshot(
                    envelope_version=1,
                    backend_kind="fixture/observation",
                    backend_schema_version=1,
                    fields=(model.ProvenanceField("transport", "simulated"),),
                )
            )
        )
        self.harness = harness

    async def _iterate_events(self) -> AsyncIterator[model.BackendEvent]:
        self.harness.consumer_calls += 1
        try:
            async for event in super()._iterate_events():
                yield event
        finally:
            await self.harness.consumer_exit.enter()
            self.harness.trace.append("consumer.finished")

    async def close(self) -> None:
        self.harness.backend_close_calls += 1
        await self.harness.backend_close.enter()
        await super().close()
        self.harness.trace.append("backend.closed")


class GatedBackend:
    def __init__(self, harness: RunHarness, connection: GatedConnection) -> None:
        self.harness = harness
        self.connection = connection

    async def open(self) -> GatedConnection:
        self.harness.open_calls += 1
        self.harness.trace.append("backend.open_attempt")
        await self.harness.backend_open.enter()
        return self.connection


class GatedRecorder:
    def __init__(self, harness: RunHarness, journal: SqliteEvidenceJournal) -> None:
        self.harness = harness
        self.journal = journal

    @property
    def session_id(self) -> model.SessionId:
        return self.journal.session_id

    @property
    def policy(self) -> model.SessionPolicy:
        return self.journal.policy

    async def append(self, draft: PendingEvidenceRecord) -> model.EvidenceRecord:
        if (
            isinstance(draft, PendingSegmentStartedEvidence)
            and not self.harness.records
        ):
            await self.harness.first_append.enter()
        if isinstance(draft, PendingSegmentEndedEvidence):
            await self.harness.final_append.enter()
        record = await self.journal.append(draft)
        self.harness.records.append(record)
        if isinstance(draft, PendingSegmentEndedEvidence):
            self.harness.trace.append("final_append.committed")
        return record

    async def close(self) -> None:
        self.harness.recorder_close_calls += 1
        self.harness.trace.append("recorder.close_entered")
        await self.harness.recorder_close.enter()
        await self.journal.close()
        self.harness.trace.append("recorder.closed")


class RunHarness:
    """Control normalized resource work; use an actual temporary durable journal."""

    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.preparation = Gate()
        self.backend_open = Gate()
        self.first_append = Gate()
        self.backend_close = Gate()
        self.consumer_exit = Gate()
        self.final_append = Gate()
        self.recorder_close = Gate()
        self.gates = (
            self.preparation,
            self.backend_open,
            self.first_append,
            self.backend_close,
            self.consumer_exit,
            self.final_append,
            self.recorder_close,
        )
        self.trace: list[str] = []
        self.received_profiles: list[profile.ResolvedDutProfile] = []
        self.records: list[model.EvidenceRecord] = []
        self.journal: SqliteEvidenceJournal | None = None
        self.connection: GatedConnection | None = None
        self.open_calls = 0
        self.consumer_calls = 0
        self.backend_close_calls = 0
        self.recorder_close_calls = 0
        self.tasks: list[asyncio.Task[rt.RuntimeStatus]] = []

    async def prepare(
        self, resolved: profile.ResolvedDutProfile
    ) -> rt.PreparedObservationRun:
        self.received_profiles.append(resolved)
        await self.preparation.enter()
        # A separate equal policy instance catches accidental identity checks.
        self.journal = await SqliteEvidenceJournal.create(
            self.destination,
            replace(resolved.session_policy),
        )
        self.trace.append("journal.created")
        self.connection = GatedConnection(self)
        backend = GatedBackend(self, self.connection)
        self.trace.append("backend.constructed")
        return rt.PreparedObservationRun(GatedRecorder(self, self.journal), backend)

    def attach(self, runtime: RuntimeContract) -> asyncio.Task[rt.RuntimeStatus]:
        task = asyncio.create_task(runtime.attach(_profile(), self.prepare))
        self.tasks.append(task)
        return task

    def detach(self, runtime: RuntimeContract) -> asyncio.Task[rt.RuntimeStatus]:
        task = asyncio.create_task(runtime.detach())
        self.tasks.append(task)
        return task

    async def finish(self, runtime: RuntimeContract) -> None:
        for gate in self.gates:
            gate.allow.set()
        try:
            await _await(runtime.detach())
            for task in self.tasks:
                await _await(task)
        finally:
            # Test-owned fallback avoids leaking the journal worker if an
            # assertion exposed an implementation defect; it is not evidence
            # that runtime closed anything. Checks occur before this cleanup.
            if self.journal is not None:
                await _await(self.journal.close())


@asynccontextmanager
async def _case(runtime: RuntimeContract, harness: RunHarness) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await harness.finish(runtime)


def _forbid(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    pytest.fail("forbidden preparation, Profile I/O, or scheduling was attempted")


def test_construction_without_running_loop_rejects_before_lock_or_task_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = _factory()
    with monkeypatch.context() as patch:
        patch.setattr(asyncio, "Lock", _forbid)
        patch.setattr(asyncio, "create_task", _forbid)
        with pytest.raises(rt.RuntimeRejectedError) as rejected:
            constructor()
    assert rejected.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT


@pytest.mark.asyncio
async def test_construction_on_running_loop_is_inactive_without_resource_owner() -> (
    None
):
    constructor = _factory()
    existing_tasks = asyncio.all_tasks()
    runtime = constructor()
    status = runtime.status()
    assert status == rt.RuntimeStatus()
    assert asyncio.all_tasks() == existing_tasks
    assert await runtime.detach() == status


@pytest.mark.parametrize("stage", ["prepare", "open", "first_append"])
@pytest.mark.asyncio
async def test_attaching_status_reports_only_acknowledged_resource_facts(
    tmp_path: Path,
    stage: str,
) -> None:
    runtime = _factory()()
    harness = RunHarness(tmp_path / "session.sqlite")
    gate = {
        "prepare": harness.preparation,
        "open": harness.backend_open,
        "first_append": harness.first_append,
    }[stage]
    gate.allow.clear()
    async with _case(runtime, harness):
        attach = harness.attach(runtime)
        await _await(gate.entered.wait())
        status = runtime.status()
        assert status.state is rt.RuntimeState.ATTACHING
        assert status.run_id is not None
        assert status.profile == _profile()
        assert not status.owner_settled
        assert not status.attach_admissible
        assert not status.recorder_close_confirmed
        assert not attach.done()
        if stage == "prepare":
            assert status.session_id is None
            assert status.acquisition is None
            assert status.physical_release_confirmed
            assert not harness.destination.exists()
        else:
            assert harness.journal is not None
            assert status.session_id == harness.journal.session_id
            assert status.acquisition is not None
            assert status.acquisition.state is aq.AcquisitionState.STARTING
            assert status.acquisition.provenance is None
            assert not status.physical_release_confirmed
            if stage == "open":
                assert status.acquisition.descriptor is None
            else:
                assert harness.connection is not None
                assert status.acquisition.descriptor == harness.connection.descriptor
        gate.allow.set()
        active = await _await(attach)
        assert active.state is rt.RuntimeState.ACTIVE
        assert active.acquisition is not None
        assert active.acquisition.state is aq.AcquisitionState.ACQUIRING
        assert active.acquisition.provenance is not None
        assert status.state is rt.RuntimeState.ATTACHING  # Earlier value stays frozen.


@pytest.mark.parametrize("stage", ["prepare", "open", "active", "close"])
@pytest.mark.asyncio
async def test_resolved_profile_busy_attach_rejects_without_io_or_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    runtime = _factory()()
    resolved = _profile()  # Caller already resolved it, before the guarded call.
    harness = RunHarness(tmp_path / "session.sqlite")
    gate = {
        "prepare": harness.preparation,
        "open": harness.backend_open,
        "active": None,
        "close": harness.backend_close,
    }[stage]
    if gate is not None:
        gate.allow.clear()
    async with _case(runtime, harness):
        attach = harness.attach(runtime)
        if stage in {"active", "close"}:
            await _await(attach)
            if stage == "close":
                harness.detach(runtime)
        if gate is not None:
            await _await(gate.entered.wait())
        before = runtime.status()
        trace = tuple(harness.trace)

        async def forbidden_preparation(
            p: profile.ResolvedDutProfile,
        ) -> rt.PreparedObservationRun:
            del p
            pytest.fail("busy runtime must not call preparation")

        with monkeypatch.context() as patch:
            patch.setattr(builtins, "open", _forbid)
            patch.setattr(io, "open", _forbid)
            patch.setattr(Path, "open", _forbid)
            patch.setattr(Path, "read_bytes", _forbid)
            patch.setattr(Path, "read_text", _forbid)
            with pytest.raises(rt.RuntimeRejectedError) as rejected:
                await _await(runtime.attach(resolved, forbidden_preparation))
        assert rejected.value.kind is rt.RuntimeRejectedKind.BUSY
        assert runtime.status() == before
        assert tuple(harness.trace) == trace
        assert len(harness.received_profiles) == 1


@pytest.mark.parametrize(
    "state", ["inactive", "attaching", "active", "detaching", "terminated"]
)
@pytest.mark.asyncio
async def test_synchronous_status_does_not_mutate_or_schedule_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    runtime = _factory()()
    harness = RunHarness(tmp_path / "session.sqlite")
    async with _case(runtime, harness):
        if state == "attaching":
            harness.preparation.allow.clear()
            harness.attach(runtime)
            await _await(harness.preparation.entered.wait())
        elif state in {"active", "detaching", "terminated"}:
            await _await(harness.attach(runtime))
            if state == "detaching":
                harness.backend_close.allow.clear()
                harness.detach(runtime)
                await _await(harness.backend_close.entered.wait())
            elif state == "terminated":
                await _await(runtime.detach())
        before = runtime.status()
        assert before.state.value == state
        trace = tuple(harness.trace)
        loop = asyncio.get_running_loop()
        with monkeypatch.context() as patch:
            patch.setattr(asyncio, "create_task", _forbid)
            patch.setattr(loop, "create_task", _forbid)
            patch.setattr(loop, "call_soon", _forbid)
            patch.setattr(loop, "call_later", _forbid)
            assert runtime.status() == before
            assert runtime.status() == before
        assert tuple(harness.trace) == trace
        field = "state"
        with pytest.raises(FrozenInstanceError):
            setattr(before, field, rt.RuntimeState.INACTIVE)


@pytest.mark.asyncio
async def test_each_explicit_attach_has_fresh_identity_and_exact_profile_policy(
    tmp_path: Path,
) -> None:
    runtime = _factory()()
    first = RunHarness(tmp_path / "first.sqlite")
    second = RunHarness(tmp_path / "second.sqlite")
    async with _case(runtime, first), _case(runtime, second):
        active = await _await(first.attach(runtime))
        assert active.state is rt.RuntimeState.ACTIVE
        assert active.profile == _profile()
        assert first.received_profiles == [_profile()]
        assert first.journal is not None
        assert active.session_id == first.journal.session_id
        assert active.profile is not None
        assert first.journal.policy == active.profile.session_policy
        assert first.journal.policy is not active.profile.session_policy
        assert active.acquisition is not None
        assert active.acquisition.provenance is not None
        assert [type(record) for record in first.records] == [
            model.SegmentStartedEvidence
        ]
        assert first.trace[:3] == [
            "journal.created",
            "backend.constructed",
            "backend.open_attempt",
        ]
        assert first.open_calls == 1
        terminal = await _await(runtime.detach())
        assert terminal.state is rt.RuntimeState.TERMINATED
        again = await _await(second.attach(runtime))
        assert again.state is rt.RuntimeState.ACTIVE
        assert again.run_id != active.run_id
        assert again.session_id != active.session_id
        assert again.acquisition is not None
        assert again.acquisition.provenance is not None
        assert (
            again.acquisition.provenance.connection_id
            != active.acquisition.provenance.connection_id
        )
        assert runtime.status() == again
        assert terminal.run_id == active.run_id
        assert terminal.session_id == active.session_id
        assert terminal.acquisition is not None
        assert terminal.acquisition.state is aq.AcquisitionState.STOPPED


@pytest.mark.asyncio
async def test_inactive_and_settled_detach_are_idempotent(tmp_path: Path) -> None:
    runtime = _factory()()
    assert await runtime.detach() == rt.RuntimeStatus()
    assert await runtime.detach() == rt.RuntimeStatus()
    harness = RunHarness(tmp_path / "session.sqlite")
    async with _case(runtime, harness):
        active = await _await(harness.attach(runtime))
        terminal = await _await(runtime.detach())
        assert terminal.state is rt.RuntimeState.TERMINATED
        assert terminal.run_id == active.run_id
        assert terminal.terminal_reason is rt.RuntimeTerminalReason.DETACHED
        assert terminal.stop_intent is rt.RuntimeStopIntent.DETACH
        assert terminal.owner_settled and terminal.attach_admissible
        assert terminal.physical_release_confirmed and terminal.recorder_close_confirmed
        assert terminal.primary_issue is None and terminal.cleanup_issues == ()
        trace = tuple(harness.trace)
        records = tuple(harness.records)
        assert await runtime.detach() == terminal
        assert await runtime.detach() == terminal
        assert runtime.status() == terminal
        assert tuple(harness.trace) == trace
        assert tuple(harness.records) == records
        assert harness.open_calls == harness.consumer_calls == 1
        assert harness.backend_close_calls == harness.recorder_close_calls == 1


@pytest.mark.asyncio
async def test_detach_joins_final_append_consumer_and_physical_close_before_recorder(
    tmp_path: Path,
) -> None:
    runtime = _factory()()
    harness = RunHarness(tmp_path / "session.sqlite")
    for gate in (
        harness.backend_close,
        harness.consumer_exit,
        harness.final_append,
        harness.recorder_close,
    ):
        gate.allow.clear()
    async with _case(runtime, harness):
        await _await(harness.attach(runtime))
        detach = harness.detach(runtime)
        await _await(harness.backend_close.entered.wait())
        status = runtime.status()
        assert status.state is rt.RuntimeState.DETACHING
        assert not status.owner_settled and not status.attach_admissible
        assert not status.physical_release_confirmed
        assert not harness.recorder_close.entered.is_set()
        assert not detach.done()
        harness.backend_close.allow.set()
        await _await(harness.consumer_exit.entered.wait())
        assert not harness.recorder_close.entered.is_set()
        assert not detach.done()
        harness.consumer_exit.allow.set()
        await _await(harness.final_append.entered.wait())
        assert not harness.recorder_close.entered.is_set()
        assert not detach.done()
        harness.final_append.allow.set()
        await _await(harness.recorder_close.entered.wait())
        status = runtime.status()
        assert status.state is rt.RuntimeState.DETACHING
        assert not status.owner_settled and not status.attach_admissible
        assert status.physical_release_confirmed
        assert not status.recorder_close_confirmed
        assert status.acquisition is not None
        assert status.acquisition.state is aq.AcquisitionState.STOPPED
        assert (
            status.acquisition.terminal_trigger
            is aq.AcquisitionTerminalTrigger.EXPLICIT_STOP
        )
        for completed in (
            "backend.closed",
            "consumer.finished",
            "final_append.committed",
        ):
            assert harness.trace.index(completed) < harness.trace.index(
                "recorder.close_entered"
            )
        end = harness.records[-1]
        assert isinstance(end, model.SegmentEndedEvidence)
        assert end.reason is model.SegmentEndReason.EXPLICIT_STOP
        assert not detach.done()
        harness.recorder_close.allow.set()
        terminal = await _await(detach)
        assert terminal.state is rt.RuntimeState.TERMINATED
        assert terminal.owner_settled and terminal.attach_admissible
        assert harness.trace[-1] == "recorder.closed"


def _reject_without_loop(
    runtime: RuntimeContract,
    api: str,
    prepare: rt.PrepareObservationRun,
) -> None:
    if api == "status":
        with pytest.raises(rt.RuntimeRejectedError) as rejected:
            runtime.status()
    else:
        work = (
            runtime.attach(_profile(), prepare) if api == "attach" else runtime.detach()
        )
        try:
            with pytest.raises(rt.RuntimeRejectedError) as rejected:
                work.send(None)  # Execute API entry with no running event loop.
        finally:
            work.close()
    assert rejected.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT


async def _reject_on_loop(
    runtime: RuntimeContract,
    api: str,
    prepare: rt.PrepareObservationRun,
) -> None:
    with pytest.raises(rt.RuntimeRejectedError) as rejected:
        if api == "status":
            runtime.status()
        elif api == "attach":
            await runtime.attach(_profile(), prepare)
        else:
            await runtime.detach()
    assert rejected.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT


@pytest.mark.parametrize("state", ["inactive", "active", "terminated"])
@pytest.mark.parametrize("api", ["attach", "detach", "status"])
@pytest.mark.parametrize(
    "context",
    [
        "foreign_loop_same_thread",
        "foreign_loop_other_thread",
        "owning_loop_other_thread",
        "no_loop_same_thread",
        "no_loop_other_thread",
    ],
)
def test_wrong_context_rejects_before_locks_mutation_or_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    api: str,
    context: str,
) -> None:
    constructor = _factory()
    harness = RunHarness(tmp_path / "session.sqlite")
    attempts: list[profile.ResolvedDutProfile] = []

    async def forbidden_prepare(
        p: profile.ResolvedDutProfile,
    ) -> rt.PreparedObservationRun:
        attempts.append(p)
        pytest.fail("wrong-context API must not prepare run resources")

    with asyncio.Runner() as owner:

        async def establish() -> tuple[RuntimeContract, rt.RuntimeStatus]:
            runtime = constructor()
            if state != "inactive":
                await _await(harness.attach(runtime))
            if state == "terminated":
                await _await(runtime.detach())
            return runtime, runtime.status()

        runtime, before = owner.run(establish())
        owner_loop = owner.get_loop()
        owner_thread = get_ident()
        original_acquire = asyncio.Lock.acquire

        async def guarded_acquire(lock: asyncio.Lock) -> bool:
            assert get_ident() == owner_thread, "context rejection must precede locks"
            assert asyncio.get_running_loop() is owner_loop, (
                "context rejection must precede locks"
            )
            return await original_acquire(lock)

        try:
            with monkeypatch.context() as patch:
                patch.setattr(asyncio.Lock, "acquire", guarded_acquire)
                if context == "foreign_loop_same_thread":
                    with asyncio.Runner() as foreign:
                        foreign.run(_reject_on_loop(runtime, api, forbidden_prepare))
                elif context == "no_loop_same_thread":
                    _reject_without_loop(runtime, api, forbidden_prepare)
                else:

                    def on_thread() -> None:
                        if context == "no_loop_other_thread":
                            _reject_without_loop(runtime, api, forbidden_prepare)
                        elif context == "owning_loop_other_thread":
                            owner_loop.run_until_complete(
                                _reject_on_loop(runtime, api, forbidden_prepare)
                            )
                        else:
                            asyncio.run(
                                _reject_on_loop(runtime, api, forbidden_prepare)
                            )

                    with ThreadPoolExecutor(max_workers=1) as worker:
                        worker.submit(on_thread).result(timeout=5.0)

            async def unchanged() -> None:
                assert runtime.status() == before
                assert attempts == []
                assert len(harness.received_profiles) == (
                    0 if state == "inactive" else 1
                )
                assert harness.open_calls == (0 if state == "inactive" else 1)

            owner.run(unchanged())
        finally:
            owner.run(harness.finish(runtime))


def test_wrong_context_precedes_invalid_attach_argument_validation() -> None:
    constructor = _factory()
    with asyncio.Runner() as owner:

        async def create() -> RuntimeContract:
            return constructor()

        runtime = owner.run(create())

        async def invalid_request_on_foreign_loop() -> None:
            with pytest.raises(rt.RuntimeRejectedError) as rejected:
                await runtime.attach(
                    cast("profile.ResolvedDutProfile", object()),
                    cast("rt.PrepareObservationRun", object()),
                )
            assert rejected.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT

        with asyncio.Runner() as foreign:
            foreign.run(invalid_request_on_foreign_loop())

        async def unchanged() -> None:
            assert runtime.status() == rt.RuntimeStatus()

        owner.run(unchanged())


@pytest.mark.asyncio
async def test_returned_immutable_status_can_be_read_elsewhere_without_runtime_access(
    tmp_path: Path,
) -> None:
    runtime = _factory()()
    harness = RunHarness(tmp_path / "session.sqlite")
    async with _case(runtime, harness):
        snapshot = await _await(harness.attach(runtime))

        def inspect_on_thread() -> tuple[rt.RunId | None, model.SessionId | None]:
            assert snapshot.state is rt.RuntimeState.ACTIVE
            assert snapshot.profile == _profile()
            _reject_without_loop(runtime, "status", harness.prepare)
            return snapshot.run_id, snapshot.session_id

        assert await asyncio.to_thread(inspect_on_thread) == (
            snapshot.run_id,
            snapshot.session_id,
        )
        assert runtime.status() == snapshot


def test_closed_owner_loop_cannot_be_rebound_after_termination(tmp_path: Path) -> None:
    constructor = _factory()
    harness = RunHarness(tmp_path / "session.sqlite")

    async def settle() -> tuple[RuntimeContract, rt.RuntimeStatus]:
        runtime = constructor()
        async with _case(runtime, harness):
            await _await(harness.attach(runtime))
            terminal = await _await(runtime.detach())
            return runtime, terminal

    runtime, terminal = asyncio.run(settle())
    trace = tuple(harness.trace)
    with asyncio.Runner() as foreign:
        for api in ("attach", "detach", "status"):
            foreign.run(_reject_on_loop(runtime, api, harness.prepare))
    assert terminal.state is rt.RuntimeState.TERMINATED
    assert terminal.attach_admissible
    assert tuple(harness.trace) == trace


# T012: request/cancellation races. These add no runtime substitute and no
# failure/ownership-transfer behavior from T013/T014. All gates are test-owned.


class RaceConnection(GatedConnection):
    def __init__(self, harness: RaceHarness) -> None:
        super().__init__(harness)
        self.race = harness

    async def _iterate_events(self) -> AsyncIterator[model.BackendEvent]:
        await self.race.rx_read.enter()
        async for event in super()._iterate_events():
            yield event


class RaceRecorder(GatedRecorder):
    def __init__(self, harness: RaceHarness, journal: SqliteEvidenceJournal) -> None:
        super().__init__(harness, journal)
        self.race = harness

    async def append(self, draft: PendingEvidenceRecord) -> model.EvidenceRecord:
        if isinstance(draft, PendingRxBytesEvidence):
            await self.race.rx_append.enter()
        record = await super().append(draft)
        if isinstance(record, model.SegmentStartedEvidence):
            callback = self.race.on_first_commit
            if callback is not None:
                callback()
        return record

    async def close(self) -> None:
        await super().close()
        callback = self.race.on_recorder_closed
        if callback is not None:
            callback()


class RaceHarness(RunHarness):
    def __init__(self, destination: Path) -> None:
        super().__init__(destination)
        self.rx_read = Gate()
        self.rx_append = Gate()
        self.race_gates = (*self.gates, self.rx_read, self.rx_append)
        self.on_first_commit: Callable[[], None] | None = None
        self.on_recorder_closed: Callable[[], None] | None = None

    async def prepare(
        self, resolved: profile.ResolvedDutProfile
    ) -> rt.PreparedObservationRun:
        self.received_profiles.append(resolved)
        await self.preparation.enter()
        self.journal = await SqliteEvidenceJournal.create(
            self.destination, replace(resolved.session_policy)
        )
        self.trace.append("journal.created")
        self.connection = RaceConnection(self)
        self.trace.append("backend.constructed")
        return rt.PreparedObservationRun(
            RaceRecorder(self, self.journal), GatedBackend(self, self.connection)
        )


async def _checkpoint() -> None:
    """Let already scheduled requests run; no elapsed-time sleep or deadline."""
    loop = asyncio.get_running_loop()
    marker: asyncio.Future[None] = loop.create_future()
    loop.call_soon(marker.set_result, None)
    await marker


def _release(harness: RaceHarness) -> None:
    for gate in harness.race_gates:
        gate.allow.set()


@asynccontextmanager
async def _race_case(
    runtime: RuntimeContract, *harnesses: RaceHarness
) -> AsyncIterator[None]:
    try:
        yield
    finally:
        for harness in harnesses:
            _release(harness)
        try:
            await _await(runtime.detach())
            await _await(
                asyncio.gather(
                    *(task for harness in harnesses for task in harness.tasks),
                    return_exceptions=True,
                )
            )
            # A test callback may have admitted the next explicit generation
            # during old-owner completion. Join that run as well.
            await _await(runtime.detach())
        finally:
            for harness in harnesses:
                if harness.journal is not None:
                    await _await(harness.journal.close())


def _stage(harness: RaceHarness, name: str) -> Gate:
    return {
        "prepare": harness.preparation,
        "open": harness.backend_open,
        "first_append": harness.first_append,
        "read": harness.rx_read,
        "rx_append": harness.rx_append,
        "backend_close": harness.backend_close,
        "consumer_exit": harness.consumer_exit,
        "final_append": harness.final_append,
        "recorder_close": harness.recorder_close,
    }[name]


async def _cancel_pending(
    runtime: RuntimeContract,
    waiter: asyncio.Task[rt.RuntimeStatus],
    intent: rt.RuntimeStopIntent,
    repetitions: int = 1,
) -> None:
    for _ in range(repetitions):
        assert waiter.cancel()
        await _checkpoint()

        # Wait for the observable cancellation handler, or detect an early
        # escape. A watchdog bounds only this test, never runtime cleanup.
        async def requested_or_escaped() -> None:
            while (
                runtime.status().stop_intent is rt.RuntimeStopIntent.NONE
                and not waiter.done()
            ):
                await _checkpoint()

        await _await(requested_or_escaped())
        assert not waiter.done(), (
            "cancelled lifecycle waiter escaped before owned work settled"
        )
        status = runtime.status()
        assert status.stop_intent is intent
        assert not status.owner_settled and not status.attach_admissible


async def _expect_cancelled(waiter: asyncio.Task[rt.RuntimeStatus]) -> None:
    with pytest.raises(asyncio.CancelledError):
        await _await(waiter)


def _assert_cleanup(
    harness: RaceHarness, terminal: rt.RuntimeStatus, *, opened: bool
) -> None:
    assert terminal.state is rt.RuntimeState.TERMINATED
    assert terminal.owner_settled and terminal.attach_admissible
    assert terminal.physical_release_confirmed and terminal.recorder_close_confirmed
    assert terminal.primary_issue is None and terminal.cleanup_issues == ()
    assert harness.destination.exists()  # Cancelled runs keep their journals.
    assert harness.journal is not None
    assert terminal.session_id == harness.journal.session_id
    assert harness.open_calls == int(opened)
    assert harness.backend_close_calls == int(opened)
    assert harness.recorder_close_calls == 1
    if opened:
        assert harness.consumer_calls == 1
        ends = [
            record
            for record in harness.records
            if isinstance(record, model.SegmentEndedEvidence)
        ]
        assert len(ends) == 1
        assert ends[0].reason is model.SegmentEndReason.EXPLICIT_STOP
        for step in ("backend.closed", "consumer.finished", "final_append.committed"):
            assert harness.trace.index(step) < harness.trace.index(
                "recorder.close_entered"
            )
    else:
        assert harness.records == []


@pytest.mark.parametrize("stage", ["prepare", "open", "first_append", "active"])
@pytest.mark.asyncio
async def test_t012_concurrent_busy_requests_never_read_profile_or_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    runtime = _factory()()
    resolved = _profile()
    harness = RaceHarness(tmp_path / "winner.sqlite")
    gate = None if stage == "active" else _stage(harness, stage)
    if gate is not None:
        gate.allow.clear()
    async with _race_case(runtime, harness):
        accepted = harness.attach(runtime)
        if gate is None:
            await _await(accepted)
        else:
            await _await(gate.entered.wait())
        before = runtime.status()

        async def forbidden_prepare(
            _: profile.ResolvedDutProfile,
        ) -> rt.PreparedObservationRun:
            pytest.fail("competing attach must not prepare run resources")

        with monkeypatch.context() as patch:
            for target, attribute in (
                (builtins, "open"),
                (io, "open"),
                (Path, "open"),
                (Path, "read_bytes"),
                (Path, "read_text"),
            ):
                patch.setattr(target, attribute, _forbid)
            outcomes = await _await(
                asyncio.gather(
                    *(runtime.attach(resolved, forbidden_prepare) for _ in range(3)),
                    return_exceptions=True,
                )
            )
        assert all(
            isinstance(outcome, rt.RuntimeRejectedError)
            and outcome.kind is rt.RuntimeRejectedKind.BUSY
            for outcome in outcomes
        )
        assert runtime.status() == before
        assert harness.received_profiles == [resolved]
        assert harness.open_calls == (0 if stage == "prepare" else 1)
        _release(harness)
        assert (await _await(accepted)).run_id == before.run_id


@pytest.mark.parametrize("api", ["attach", "detach"])
@pytest.mark.asyncio
async def test_t012_wrong_context_during_startup_rejects_before_lock_or_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    api: str,
) -> None:
    runtime = _factory()()
    harness = RaceHarness(tmp_path / "session.sqlite")
    harness.backend_open.allow.clear()
    async with _race_case(runtime, harness):
        harness.attach(runtime)
        await _await(harness.backend_open.entered.wait())
        before = runtime.status()
        owner_loop = asyncio.get_running_loop()
        owner_thread = get_ident()
        original_acquire = asyncio.Lock.acquire

        async def guarded_acquire(lock: asyncio.Lock) -> bool:
            assert get_ident() == owner_thread
            assert asyncio.get_running_loop() is owner_loop
            return await original_acquire(lock)

        def foreign_request() -> None:
            asyncio.run(_reject_on_loop(runtime, api, harness.prepare))

        with monkeypatch.context() as patch:
            patch.setattr(asyncio.Lock, "acquire", guarded_acquire)
            await _await(asyncio.to_thread(foreign_request))
        assert runtime.status() == before
        assert harness.received_profiles == [_profile()]
        assert harness.backend_close_calls == harness.recorder_close_calls == 0


@pytest.mark.parametrize("stage", ["prepare", "open", "first_append"])
@pytest.mark.asyncio
async def test_t012_detach_during_attach_waits_for_safe_startup_checkpoint(
    tmp_path: Path,
    stage: str,
) -> None:
    runtime = _factory()()
    harness = RaceHarness(tmp_path / "session.sqlite")
    gate = _stage(harness, stage)
    gate.allow.clear()
    async with _race_case(runtime, harness):
        attach = harness.attach(runtime)
        await _await(gate.entered.wait())
        before = runtime.status()
        detach = harness.detach(runtime)
        await _checkpoint()
        status = runtime.status()
        assert status.state is rt.RuntimeState.DETACHING
        assert status.stop_intent is rt.RuntimeStopIntent.DETACH
        assert not status.owner_settled and not status.attach_admissible
        assert not attach.done() and not detach.done()
        assert harness.backend_close_calls == harness.recorder_close_calls == 0
        _release(harness)
        terminal = await _await(detach)
        assert await _await(attach) == terminal
        assert terminal.run_id == before.run_id
        assert terminal.terminal_reason is rt.RuntimeTerminalReason.DETACHED
        _assert_cleanup(harness, terminal, opened=stage != "prepare")


@pytest.mark.asyncio
async def test_t012_simultaneous_detach_waiters_share_one_cleanup(
    tmp_path: Path,
) -> None:
    runtime = _factory()()
    harness = RaceHarness(tmp_path / "session.sqlite")
    harness.backend_close.allow.clear()
    async with _race_case(runtime, harness):
        active = await _await(harness.attach(runtime))
        waiters = [harness.detach(runtime) for _ in range(3)]
        await _await(harness.backend_close.entered.wait())
        await _checkpoint()
        assert all(not waiter.done() for waiter in waiters)
        assert harness.backend_close_calls == 1
        assert harness.recorder_close_calls == 0
        _release(harness)
        results = await _await(asyncio.gather(*waiters))
        assert results == [results[0]] * 3
        assert results[0].run_id == active.run_id
        _assert_cleanup(harness, results[0], opened=True)


@pytest.mark.parametrize("checkpoint", ["not_started", "admission_wait"])
@pytest.mark.asyncio
async def test_t012_cancel_before_admission_has_no_state_or_resource_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checkpoint: str,
) -> None:
    runtime = _factory()()
    harness = RaceHarness(tmp_path / "never-created.sqlite")
    before = runtime.status()
    gate = Gate()
    gate.allow.clear()
    original_acquire = asyncio.Lock.acquire
    waiter: asyncio.Task[rt.RuntimeStatus] | None = None

    async def gated_acquire(lock: asyncio.Lock) -> bool:
        if asyncio.current_task() is waiter:
            await gate.enter()
        return await original_acquire(lock)

    with monkeypatch.context() as patch:
        if checkpoint == "admission_wait":
            patch.setattr(asyncio.Lock, "acquire", gated_acquire)
        waiter = harness.attach(runtime)
        if checkpoint == "admission_wait":
            await _await(gate.entered.wait())
        assert waiter.cancel()
        await _expect_cancelled(waiter)
    assert runtime.status() == before
    assert harness.received_profiles == []
    assert not harness.destination.exists()
    assert (
        harness.open_calls
        == harness.backend_close_calls
        == harness.recorder_close_calls
        == 0
    )


@pytest.mark.parametrize("stage", ["prepare", "open", "first_append"])
@pytest.mark.parametrize("repetitions", [1, 3])
@pytest.mark.asyncio
async def test_t012_cancel_attach_drains_submitted_startup_before_raising(
    tmp_path: Path,
    stage: str,
    repetitions: int,
) -> None:
    runtime = _factory()()
    harness = RaceHarness(tmp_path / "cancelled.sqlite")
    gate = _stage(harness, stage)
    gate.allow.clear()
    async with _race_case(runtime, harness):
        waiter = harness.attach(runtime)
        await _await(gate.entered.wait())
        run_id = runtime.status().run_id
        await _cancel_pending(
            runtime, waiter, rt.RuntimeStopIntent.ATTACH_CANCELLED, repetitions
        )
        assert harness.backend_close_calls == harness.recorder_close_calls == 0
        _release(harness)
        terminal = await _await(harness.detach(runtime))
        await _expect_cancelled(waiter)
        assert terminal.run_id == run_id
        assert terminal.stop_intent is rt.RuntimeStopIntent.ATTACH_CANCELLED
        assert terminal.terminal_reason is rt.RuntimeTerminalReason.ATTACH_CANCELLED
        _assert_cleanup(harness, terminal, opened=stage != "prepare")


@pytest.mark.parametrize("repetitions", [1, 3])
@pytest.mark.asyncio
async def test_t012_cancel_after_active_publication_before_attach_delivery_drains_read(
    tmp_path: Path,
    repetitions: int,
) -> None:
    runtime = _factory()()
    harness = RaceHarness(tmp_path / "published.sqlite")
    harness.rx_read.allow.clear()
    harness.backend_close.allow.clear()
    observed = asyncio.Event()
    loop = asyncio.get_running_loop()
    published: list[rt.RuntimeStatus] = []
    waiter: asyncio.Task[rt.RuntimeStatus]

    def cancel_at_publication() -> None:
        status = runtime.status()
        if status.state is rt.RuntimeState.ATTACHING:
            loop.call_soon(cancel_at_publication)
            return
        published.append(status)
        waiter.cancel()
        observed.set()

    def schedule_publication_check() -> None:
        loop.call_soon(cancel_at_publication)

    harness.on_first_commit = schedule_publication_check
    async with _race_case(runtime, harness):
        waiter = harness.attach(runtime)
        await _await(observed.wait())
        await _await(harness.rx_read.entered.wait())
        await _checkpoint()
        assert published[0].state is rt.RuntimeState.ACTIVE
        assert not waiter.done(), "attach cancellation escaped after active publication"
        assert runtime.status().stop_intent is rt.RuntimeStopIntent.ATTACH_CANCELLED
        if repetitions > 1:
            await _cancel_pending(
                runtime, waiter, rt.RuntimeStopIntent.ATTACH_CANCELLED, repetitions - 1
            )
        _release(harness)
        terminal = await _await(harness.detach(runtime))
        await _expect_cancelled(waiter)
        assert terminal.run_id == published[0].run_id
        assert terminal.terminal_reason is rt.RuntimeTerminalReason.ATTACH_CANCELLED
        _assert_cleanup(harness, terminal, opened=True)


@pytest.mark.asyncio
async def test_t012_cancelling_caller_after_successful_attach_does_not_detach(
    tmp_path: Path,
) -> None:
    runtime = _factory()()
    harness = RaceHarness(tmp_path / "active.sqlite")
    returned = asyncio.Event()
    later_work = Gate()
    later_work.allow.clear()

    async def caller() -> rt.RuntimeStatus:
        active = await runtime.attach(_profile(), harness.prepare)
        returned.set()
        await later_work.enter()
        return active

    async with _race_case(runtime, harness):
        task = asyncio.create_task(caller())
        harness.tasks.append(task)
        await _await(returned.wait())
        before = runtime.status()
        assert task.cancel()
        await _expect_cancelled(task)
        assert runtime.status() == before
        assert before.state is rt.RuntimeState.ACTIVE
        assert before.stop_intent is rt.RuntimeStopIntent.NONE
        assert harness.backend_close_calls == harness.recorder_close_calls == 0


@pytest.mark.parametrize(
    "stage",
    [
        "prepare",
        "open",
        "first_append",
        "read",
        "rx_append",
        "backend_close",
        "consumer_exit",
        "final_append",
        "recorder_close",
    ],
)
@pytest.mark.asyncio
async def test_t012_cancel_detach_waiter_repeatedly_joins_cleanup_and_other_waiter(
    tmp_path: Path,
    stage: str,
) -> None:
    runtime = _factory()()
    harness = RaceHarness(tmp_path / "session.sqlite")
    gate = _stage(harness, stage)
    gate.allow.clear()
    async with _race_case(runtime, harness):
        attach = harness.attach(runtime)
        startup = stage in {"prepare", "open", "first_append"}
        if startup:
            await _await(gate.entered.wait())
        else:
            await _await(attach)
            if stage == "rx_append":
                assert harness.connection is not None
                await harness.connection.emit_rx(b"in-flight\x00\xff", timestamp=10)
            if stage in {"read", "rx_append"}:
                await _await(gate.entered.wait())
        cancelled = harness.detach(runtime)
        observer = harness.detach(runtime)
        if not startup and stage not in {"read", "rx_append"}:
            await _await(gate.entered.wait())
        await _checkpoint()
        before = runtime.status()
        assert before.stop_intent is rt.RuntimeStopIntent.DETACH
        await _cancel_pending(runtime, cancelled, rt.RuntimeStopIntent.DETACH, 3)
        assert not observer.done()
        _release(harness)
        terminal = await _await(observer)
        await _expect_cancelled(cancelled)
        if startup:
            assert await _await(attach) == terminal
        assert terminal.run_id == before.run_id
        assert terminal.stop_intent is rt.RuntimeStopIntent.DETACH
        assert terminal.terminal_reason is rt.RuntimeTerminalReason.DETACHED
        _assert_cleanup(harness, terminal, opened=stage != "prepare")
        if stage == "rx_append":
            assert [
                record.payload
                for record in harness.records
                if isinstance(record, model.RxBytesEvidence)
            ] == [b"in-flight\x00\xff"]


@pytest.mark.parametrize("first", ["detach", "attach_cancelled"])
@pytest.mark.asyncio
async def test_t012_first_admitted_stop_intent_survives_competing_request(
    tmp_path: Path,
    first: str,
) -> None:
    runtime = _factory()()
    harness = RaceHarness(tmp_path / "session.sqlite")
    harness.preparation.allow.clear()
    async with _race_case(runtime, harness):
        attach = harness.attach(runtime)
        await _await(harness.preparation.entered.wait())
        expected = rt.RuntimeStopIntent(first)
        if first == "detach":
            detach = harness.detach(runtime)
            await _checkpoint()
            assert runtime.status().stop_intent is expected
            await _cancel_pending(runtime, attach, expected)
        else:
            await _cancel_pending(runtime, attach, expected)
            detach = harness.detach(runtime)
            await _checkpoint()
            assert runtime.status().stop_intent is expected
        assert not detach.done()
        _release(harness)
        terminal = await _await(detach)
        await _expect_cancelled(attach)
        assert terminal.stop_intent is expected
        assert terminal.terminal_reason is rt.RuntimeTerminalReason(
            first if first != "detach" else "detached"
        )
        _assert_cleanup(harness, terminal, opened=False)


@pytest.mark.parametrize("old_waiter", ["attach", "detach", "cancelled_detach"])
@pytest.mark.asyncio
async def test_t012_old_generation_waiters_do_not_return_or_mutate_new_summary(
    tmp_path: Path,
    old_waiter: str,
) -> None:
    runtime = _factory()()
    first = RaceHarness(tmp_path / "old.sqlite")
    second = RaceHarness(tmp_path / "new.sqlite")
    first.backend_close.allow.clear()
    second.preparation.allow.clear()
    if old_waiter == "attach":
        first.backend_open.allow.clear()
    new_tasks: list[asyncio.Task[rt.RuntimeStatus]] = []
    cancelled_old: asyncio.Task[rt.RuntimeStatus] | None = None

    def admit_next() -> None:
        # Scheduling at actual recorder-close completion places the new
        # explicit request before old caller-result delivery, without reading
        # a private generation/owner task or inventing runtime behavior.
        new_tasks.append(second.attach(runtime))

    first.on_recorder_closed = admit_next
    async with _race_case(runtime, first, second):
        old_attach = first.attach(runtime)
        if old_waiter == "attach":
            await _await(first.backend_open.entered.wait())
        else:
            await _await(old_attach)
        old_id = runtime.status().run_id
        old_detach = first.detach(runtime)
        if old_waiter == "attach":
            await _checkpoint()
            first.backend_open.allow.set()
        await _await(first.backend_close.entered.wait())
        if old_waiter == "cancelled_detach":
            await _cancel_pending(runtime, old_detach, rt.RuntimeStopIntent.DETACH)
            cancelled_old = old_detach
            old_detach = first.detach(runtime)
        first.backend_close.allow.set()
        await _await(second.preparation.entered.wait())
        new_summary = runtime.status()
        assert new_summary.state is rt.RuntimeState.ATTACHING
        assert new_summary.run_id != old_id
        result = await _await(old_attach if old_waiter == "attach" else old_detach)
        assert result.state is rt.RuntimeState.TERMINATED
        assert result.run_id == old_id
        assert first.journal is not None
        assert result.session_id == first.journal.session_id
        assert runtime.status() == new_summary
        assert len(new_tasks) == 1
        second.preparation.allow.set()
        active = await _await(new_tasks[0])
        assert active.run_id == new_summary.run_id
        assert active.session_id != result.session_id
        assert runtime.status() == active
        if cancelled_old is not None:
            await _expect_cancelled(cancelled_old)
            assert runtime.status() == active


# T014: explicit failure/teardown and reuse checks. No automatic terminal
# observer, cancellation orchestration, or replacement Acquisition is added.
class FailureConnection(GatedConnection):
    def __init__(self, harness: FailureHarness) -> None:
        super().__init__(harness)
        self.failure_harness = harness
        if harness.reject_rx:
            self.descriptor = replace(
                self.descriptor, capabilities=model.BackendCapabilities(frozenset())
            )

    async def close(self) -> None:
        await super().close()
        if self.failure_harness.backend_close_fails:
            self.harness.trace.append("backend.close_failed")
            # Even if a simulated handle closed, a failed result cannot attest
            # physical release. A later no-op close must not clear uncertainty.
            raise NormalizedBackendFailure(
                BackendFailureOperation.CLOSE, BackendFailureKind.IO_FAILURE
            )


class FailureRecorder(GatedRecorder):
    def __init__(self, harness: FailureHarness, journal: SqliteEvidenceJournal) -> None:
        super().__init__(harness, journal)
        self.failure_harness = harness

    async def append(self, draft: PendingEvidenceRecord) -> model.EvidenceRecord:
        if (
            isinstance(draft, PendingSegmentStartedEvidence)
            and self.failure_harness.first_fails
        ):
            await self.harness.first_append.enter()
            self.harness.trace.append("first_append.failed")
            raise JournalFailure(JournalOperation.APPEND, JournalFailureKind.IO_FAILURE)
        if (
            isinstance(draft, PendingSegmentEndedEvidence)
            and self.failure_harness.final_fails
        ):
            await self.harness.final_append.enter()
            self.harness.trace.append("final_append.failed")
            raise JournalFailure(JournalOperation.APPEND, JournalFailureKind.IO_FAILURE)
        return await super().append(draft)

    async def close(self) -> None:
        await super().close()
        if self.failure_harness.recorder_close_fails:
            self.harness.trace.append("recorder.close_failed")
            raise JournalFailure(JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE)


class FailureHarness(RunHarness):
    def __init__(
        self,
        destination: Path,
        *,
        first_fails: bool = False,
        final_fails: bool = False,
        backend_close_fails: bool = False,
        recorder_close_fails: bool = False,
        reject_rx: bool = False,
    ) -> None:
        super().__init__(destination)
        self.first_fails = first_fails
        self.final_fails = final_fails
        self.backend_close_fails = backend_close_fails
        self.recorder_close_fails = recorder_close_fails
        self.reject_rx = reject_rx

    async def prepare(
        self, resolved: profile.ResolvedDutProfile
    ) -> rt.PreparedObservationRun:
        self.received_profiles.append(resolved)
        await self.preparation.enter()
        self.journal = await SqliteEvidenceJournal.create(
            self.destination, replace(resolved.session_policy)
        )
        self.trace.append("journal.created")
        self.connection = FailureConnection(self)
        self.trace.append("backend.constructed")
        return rt.PreparedObservationRun(
            FailureRecorder(self, self.journal), GatedBackend(self, self.connection)
        )


class SnapshotOnlyAcquisition(aq.Acquisition):
    """Real Acquisition, with a legacy-access tripwire and consumer tail gate.

    All start/stop/snapshot/join methods are inherited. The tail holds the
    actual consumer after its normal body/notification, like the foundational
    join-barrier fixture; it never changes Acquisition's facts or outcomes.
    """

    def __init__(self, recorder: EvidenceRecorder, trace: list[str]) -> None:
        super().__init__(recorder)
        self.trace = trace
        self.consumer_tail = Gate()

    @property
    def failure(self) -> aq.AcquisitionFailure | None:
        raise AssertionError(
            "runtime must project snapshots, never read legacy failure"
        )

    async def _consume(
        self,
        connection: BackendConnection,
        provenance: model.SegmentProvenance,
        termination_event: asyncio.Event,
    ) -> None:
        try:
            await super()._consume(connection, provenance, termination_event)
        finally:
            # Acquisition may cancel its consumer after failed physical close.
            # The simulated consumer's already-started final resource work
            # remains pending until this test-owned gate is explicitly released.
            while True:
                try:
                    await self.consumer_tail.enter()
                    break
                except asyncio.CancelledError:
                    continue
            self.trace.append("consumer.joined")


def _t014_acquisitions(
    monkeypatch: pytest.MonkeyPatch,
) -> list[SnapshotOnlyAcquisition]:
    created: list[SnapshotOnlyAcquisition] = []

    class CapturedAcquisition(SnapshotOnlyAcquisition):
        def __init__(self, recorder: EvidenceRecorder) -> None:
            assert isinstance(recorder, FailureRecorder)
            super().__init__(recorder, recorder.harness.trace)
            created.append(self)

    monkeypatch.setattr(rt, "Acquisition", CapturedAcquisition)
    return created


async def _t014_result(work: Awaitable[rt.RuntimeStatus]) -> rt.RuntimeStatus:
    try:
        return await _await(work)
    except Exception as error:
        pytest.fail(
            f"runtime leaked {type(error).__name__} instead of settled RuntimeStatus"
        )


async def _t014_cleanup(
    runtime: RuntimeContract,
    harnesses: tuple[FailureHarness, ...],
    acquisitions: list[SnapshotOnlyAcquisition],
) -> None:
    for harness in harnesses:
        for gate in harness.gates:
            gate.allow.set()
    for acquisition in acquisitions:
        acquisition.consumer_tail.allow.set()
    try:
        try:
            await _await(runtime.detach())
        except Exception:
            pass  # The RED owner may have escaped; assertions precede cleanup.
        await _await(
            asyncio.gather(
                *(task for harness in harnesses for task in harness.tasks),
                return_exceptions=True,
            )
        )
        for acquisition in acquisitions:
            await _await(acquisition.stop())
            await _await(acquisition.join_terminated())
    finally:
        for harness in harnesses:
            if harness.journal is not None:
                await _await(harness.journal.close())


def _t014_cleanup_issues(
    backend_fails: bool, recorder_fails: bool
) -> tuple[rt.RuntimeIssue, ...]:
    # Hand-declared contract facts, not derived from runtime projection helpers.
    backend = rt.RuntimeIssue(rt.RuntimeIssueSource.BACKEND_CLOSE, "close_failed")
    recorder = rt.RuntimeIssue(
        rt.RuntimeIssueSource.RECORDER_CLOSE, JournalFailureKind.IO_FAILURE
    )
    return {
        (False, False): (),
        (True, False): (backend,),
        (False, True): (recorder,),
        (True, True): (backend, recorder),
    }[(backend_fails, recorder_fails)]


def _t014_terminal(
    runtime: RuntimeContract,
    harness: FailureHarness,
    result: rt.RuntimeStatus,
    expected_state: rt.RuntimeState,
) -> None:
    assert result.state is expected_state
    assert result.owner_settled
    assert result.physical_release_confirmed is not harness.backend_close_fails
    assert result.recorder_close_confirmed is not harness.recorder_close_fails
    assert result.attach_admissible is (
        not harness.backend_close_fails and not harness.recorder_close_fails
    )
    assert result == runtime.status()
    assert (
        harness.journal is not None and result.session_id == harness.journal.session_id
    )
    assert harness.destination.is_file()
    assert (
        harness.open_calls
        == harness.backend_close_calls
        == harness.recorder_close_calls
        == 1
    )


@pytest.mark.parametrize(
    ("scenario", "final_fails", "backend_fails", "primary"),
    [
        ("clean", False, False, None),
        ("close_only", False, True, None),
        ("recording", True, False, aq.AcquisitionFailureKind.RECORDING_FAILURE),
        (
            "recording_and_close",
            True,
            True,
            aq.AcquisitionFailureKind.RECORDING_FAILURE,
        ),
        (
            "transport_then_recording",
            True,
            False,
            aq.AcquisitionFailureKind.TRANSPORT_FAILURE,
        ),
        (
            "transport_then_recording_and_close",
            True,
            True,
            aq.AcquisitionFailureKind.TRANSPORT_FAILURE,
        ),
    ],
)
@pytest.mark.parametrize("recorder_fails", [False, True])
@pytest.mark.asyncio
async def test_t014_projects_primary_and_close_snapshot_facts_without_legacy_inference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    final_fails: bool,
    backend_fails: bool,
    primary: aq.AcquisitionFailureKind | None,
    recorder_fails: bool,
) -> None:
    runtime = _factory()()
    harness = FailureHarness(
        tmp_path / "projection.sqlite",
        final_fails=final_fails,
        backend_close_fails=backend_fails,
        recorder_close_fails=recorder_fails,
    )
    created = _t014_acquisitions(monkeypatch)
    try:
        active = await _await(harness.attach(runtime))
        if scenario.startswith("transport_then_recording"):
            # Observe transport failure before a later failed append. Explicit
            # detach drives cleanup; autonomous runtime observation is deferred.
            harness.final_append.allow.clear()
            assert harness.connection is not None
            await harness.connection.end_stream_unexpectedly()
            await _await(harness.final_append.entered.wait())
        detach = harness.detach(runtime)
        await _checkpoint()
        harness.final_append.allow.set()
        result = await _t014_result(detach)
        assert len(created) == 1
        snapshot = result.acquisition
        assert snapshot is not None
        assert snapshot.primary_failure_kind is primary
        assert snapshot.close_failed is backend_fails
        assert active.acquisition is not None
        assert snapshot.provenance == active.acquisition.provenance
        if scenario == "close_only" or scenario.startswith("transport_then_recording"):
            # Test-only access to the base's legacy API proves the counterexample
            # is real, while any runtime access hits the subclass's tripwire.
            legacy = super(SnapshotOnlyAcquisition, created[0]).failure
            assert legacy is not None
            assert legacy.kind is (
                aq.AcquisitionFailureKind.TRANSPORT_FAILURE
                if scenario == "close_only"
                else aq.AcquisitionFailureKind.RECORDING_FAILURE
            )
        assert result.primary_issue == (
            rt.RuntimeIssue(rt.RuntimeIssueSource.ACQUISITION, primary)
            if primary
            else None
        )
        assert result.cleanup_issues == _t014_cleanup_issues(
            backend_fails, recorder_fails
        )
        reason = (
            rt.RuntimeTerminalReason.ACQUISITION_FAILURE
            if primary
            else rt.RuntimeTerminalReason.DETACHED
        )
        assert result.terminal_reason is reason
        assert result.stop_intent is rt.RuntimeStopIntent.DETACH
        _t014_terminal(
            runtime,
            harness,
            result,
            rt.RuntimeState.FAILED
            if primary or backend_fails or recorder_fails
            else rt.RuntimeState.TERMINATED,
        )
        assert harness.consumer_calls == 1
        ends = sum(
            isinstance(record, model.SegmentEndedEvidence) for record in harness.records
        )
        if final_fails:
            assert ends == 0
        elif not backend_fails:
            assert ends == 1
        else:
            # Legacy failed-close cancellation need not commit a final boundary.
            assert ends <= 1
        assert harness.trace.index("consumer.joined") < harness.trace.index(
            "recorder.close_entered"
        )
    finally:
        await _t014_cleanup(runtime, (harness,), created)


@pytest.mark.parametrize("failure", ["first_append", "capability"])
@pytest.mark.parametrize("backend_fails", [False, True])
@pytest.mark.parametrize("recorder_fails", [False, True])
@pytest.mark.asyncio
async def test_t014_startup_primary_survives_both_ordered_cleanup_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    backend_fails: bool,
    recorder_fails: bool,
) -> None:
    runtime = _factory()()
    harness = FailureHarness(
        tmp_path / "startup.sqlite",
        first_fails=failure == "first_append",
        reject_rx=failure == "capability",
        backend_close_fails=backend_fails,
        recorder_close_fails=recorder_fails,
    )
    created = _t014_acquisitions(monkeypatch)
    gate = harness.first_append if failure == "first_append" else harness.backend_close
    gate.allow.clear()
    try:
        attach = harness.attach(runtime)
        await _await(gate.entered.wait())
        detach = harness.detach(runtime)
        await _checkpoint()
        assert not runtime.status().attach_admissible
        gate.allow.set()
        result = await _t014_result(attach)
        assert await _t014_result(detach) == result
        primary = (
            aq.AcquisitionFailureKind.RECORDING_FAILURE
            if failure == "first_append"
            else aq.AcquisitionFailureKind.CAPABILITY_REJECTION
        )
        assert result.primary_issue == rt.RuntimeIssue(
            rt.RuntimeIssueSource.ACQUISITION_START, primary
        )
        assert result.cleanup_issues == _t014_cleanup_issues(
            backend_fails, recorder_fails
        )
        assert result.terminal_reason is rt.RuntimeTerminalReason.STARTUP_FAILURE
        assert result.stop_intent is rt.RuntimeStopIntent.DETACH
        assert result.acquisition is not None and harness.connection is not None
        assert result.acquisition.descriptor == harness.connection.descriptor
        assert result.acquisition.provenance is None
        assert result.acquisition.primary_failure_kind is primary
        assert result.acquisition.close_failed is backend_fails
        _t014_terminal(runtime, harness, result, rt.RuntimeState.FAILED)
        assert harness.records == [] and harness.consumer_calls == 0
    finally:
        await _t014_cleanup(runtime, (harness,), created)


@pytest.mark.parametrize("backend_fails", [False, True])
@pytest.mark.parametrize("append_fails", [False, True])
@pytest.mark.asyncio
async def test_t014_consumer_join_precedes_recorder_close_even_after_failure_notification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_fails: bool,
    append_fails: bool,
) -> None:
    runtime = _factory()()
    harness = FailureHarness(
        tmp_path / "join.sqlite",
        backend_close_fails=backend_fails,
        final_fails=append_fails,
    )
    created = _t014_acquisitions(monkeypatch)
    harness.recorder_close.allow.clear()
    try:
        await _await(harness.attach(runtime))
        assert len(created) == 1
        created[0].consumer_tail.allow.clear()
        detach = harness.detach(runtime)
        await _await(created[0].consumer_tail.entered.wait())
        await _checkpoint()
        pending = runtime.status()
        assert pending.state is rt.RuntimeState.DETACHING
        assert not pending.owner_settled and not pending.attach_admissible
        assert not pending.recorder_close_confirmed
        assert harness.recorder_close_calls == 0 and not detach.done()
        assert pending.acquisition is not None
        if append_fails:
            assert pending.acquisition.state is aq.AcquisitionState.FAILED
            assert pending.primary_issue == rt.RuntimeIssue(
                rt.RuntimeIssueSource.ACQUISITION,
                aq.AcquisitionFailureKind.RECORDING_FAILURE,
            )
        created[0].consumer_tail.allow.set()
        await _await(harness.recorder_close.entered.wait())
        draining = runtime.status()
        assert draining.state is rt.RuntimeState.DETACHING
        assert not draining.owner_settled and not draining.attach_admissible
        assert draining.physical_release_confirmed is not backend_fails
        assert not draining.recorder_close_confirmed and not detach.done()
        assert draining.cleanup_issues == _t014_cleanup_issues(backend_fails, False)
        assert harness.trace.index("consumer.joined") < harness.trace.index(
            "recorder.close_entered"
        )
        harness.recorder_close.allow.set()
        result = await _t014_result(detach)
        _t014_terminal(
            runtime,
            harness,
            result,
            rt.RuntimeState.FAILED
            if append_fails or backend_fails
            else rt.RuntimeState.TERMINATED,
        )
    finally:
        await _t014_cleanup(runtime, (harness,), created)


async def _t014_busy(runtime: RuntimeContract, harness: FailureHarness) -> None:
    before = runtime.status()
    with pytest.raises(rt.RuntimeRejectedError) as caught:
        await runtime.attach(_profile(), harness.prepare)
    assert caught.value.kind is rt.RuntimeRejectedKind.BUSY
    assert runtime.status() == before
    assert harness.received_profiles == [] and not harness.destination.exists()


@pytest.mark.parametrize(
    ("backend_fails", "recorder_fails"),
    [(False, False), (True, False), (False, True), (True, True)],
)
@pytest.mark.asyncio
async def test_t014_admissibility_stays_blocked_until_settled_and_uncertainty_latches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_fails: bool,
    recorder_fails: bool,
) -> None:
    runtime = _factory()()
    harness = FailureHarness(
        tmp_path / "certainty.sqlite",
        backend_close_fails=backend_fails,
        recorder_close_fails=recorder_fails,
    )
    next_run = FailureHarness(tmp_path / "new.sqlite")
    created = _t014_acquisitions(monkeypatch)
    harness.backend_close.allow.clear()
    harness.recorder_close.allow.clear()
    try:
        await _await(harness.attach(runtime))
        await _t014_busy(runtime, next_run)
        detach = harness.detach(runtime)
        await _await(harness.backend_close.entered.wait())
        assert not runtime.status().owner_settled
        await _t014_busy(runtime, next_run)
        harness.backend_close.allow.set()
        await _await(harness.recorder_close.entered.wait())
        pending = runtime.status()
        assert pending.physical_release_confirmed is not backend_fails
        assert not pending.recorder_close_confirmed and not pending.owner_settled
        assert not pending.attach_admissible
        await _t014_busy(runtime, next_run)
        harness.recorder_close.allow.set()
        result = await _t014_result(detach)
        _t014_terminal(
            runtime,
            harness,
            result,
            rt.RuntimeState.FAILED
            if backend_fails or recorder_fails
            else rt.RuntimeState.TERMINATED,
        )
        assert result.cleanup_issues == _t014_cleanup_issues(
            backend_fails, recorder_fails
        )
        assert harness.journal is not None
        # A real library no-op close cannot re-attest a failed close result.
        await harness.journal.close()
        for _ in range(3):
            assert await _t014_result(runtime.detach()) == result
        assert harness.backend_close_calls == harness.recorder_close_calls == 1
        if backend_fails or recorder_fails:
            for _ in range(2):
                with pytest.raises(rt.RuntimeRejectedError) as caught:
                    await runtime.attach(_profile(), next_run.prepare)
                assert caught.value.kind is rt.RuntimeRejectedKind.CLEANUP_UNCONFIRMED
                assert runtime.status() == result
            assert (
                next_run.received_profiles == [] and not next_run.destination.exists()
            )
        else:
            active = await _await(next_run.attach(runtime))
            assert (
                active.session_id != result.session_id
                and active.run_id != result.run_id
            )
    finally:
        await _t014_cleanup(runtime, (harness, next_run), created)


@pytest.mark.parametrize("phase", ["first_append", "final_append"])
@pytest.mark.asyncio
async def test_t014_confirmed_cleanup_after_primary_failure_allows_only_new_explicit_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    runtime = _factory()()
    harness = FailureHarness(
        tmp_path / "failed.sqlite",
        first_fails=phase == "first_append",
        final_fails=phase == "final_append",
    )
    next_run = FailureHarness(tmp_path / "fresh.sqlite")
    created = _t014_acquisitions(monkeypatch)
    try:
        attach = harness.attach(runtime)
        if phase == "first_append":
            result = await _t014_result(attach)
        else:
            await _await(attach)
            result = await _t014_result(harness.detach(runtime))
        _t014_terminal(runtime, harness, result, rt.RuntimeState.FAILED)
        assert result.primary_issue is not None and result.cleanup_issues == ()
        assert await _t014_result(runtime.detach()) == result
        assert harness.open_calls == 1 and next_run.received_profiles == []
        active = await _await(next_run.attach(runtime))
        assert active.state is rt.RuntimeState.ACTIVE
        assert active.run_id != result.run_id and active.session_id != result.session_id
        assert active.profile == result.profile == _profile()
        assert harness.destination.is_file() and next_run.destination.is_file()
        assert (
            harness.open_calls
            == harness.backend_close_calls
            == harness.recorder_close_calls
            == 1
        )
        assert len(harness.records) == (0 if phase == "first_append" else 1)
        assert result.state is rt.RuntimeState.FAILED and result.owner_settled
        assert (
            await _t014_result(next_run.detach(runtime))
        ).state is rt.RuntimeState.TERMINATED
    finally:
        await _t014_cleanup(runtime, (harness, next_run), created)


@pytest.mark.parametrize("cleanup_fails", [False, True])
@pytest.mark.asyncio
async def test_t014_preparation_primary_and_local_cleanup_facts_survive_without_reclose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_fails: bool
) -> None:
    runtime = _factory()()
    harness = FailureHarness(
        tmp_path / "preparation.sqlite", recorder_close_fails=cleanup_fails
    )
    created = _t014_acquisitions(monkeypatch)
    primary = rt.RuntimeIssue(
        rt.RuntimeIssueSource.PREPARATION, JournalFailureKind.CAPACITY
    )
    cleanup = rt.RuntimeIssue(
        rt.RuntimeIssueSource.RECORDER_CLOSE, JournalFailureKind.IO_FAILURE
    )

    async def failed_prepare(
        resolved: profile.ResolvedDutProfile,
    ) -> rt.PreparedObservationRun:
        harness.received_profiles.append(resolved)
        harness.journal = await SqliteEvidenceJournal.create(
            harness.destination, resolved.session_policy
        )
        recorder = FailureRecorder(harness, harness.journal)
        try:
            await recorder.close()
        except JournalFailure:
            assert cleanup_fails
        failure = rt.PreparationFailure(
            primary,
            harness.journal.session_id,
            not cleanup_fails,
            cleanup if cleanup_fails else None,
        )
        raise failure

    try:
        result = await _t014_result(runtime.attach(_profile(), failed_prepare))
        assert result.state is rt.RuntimeState.FAILED and result.owner_settled
        assert result.terminal_reason is rt.RuntimeTerminalReason.STARTUP_FAILURE
        assert result.primary_issue == primary
        assert result.cleanup_issues == ((cleanup,) if cleanup_fails else ())
        assert result.physical_release_confirmed
        assert result.recorder_close_confirmed is not cleanup_fails
        assert result.attach_admissible is not cleanup_fails
        assert result.acquisition is None and created == []
        assert (
            harness.journal is not None
            and result.session_id == harness.journal.session_id
        )
        assert harness.destination.is_file()
        assert await _t014_result(runtime.detach()) == result
        assert harness.recorder_close_calls == 1 and harness.open_calls == 0
    finally:
        await _t014_cleanup(runtime, (harness,), created)

# T020: autonomous termination, cause precedence, and historical status.
# These fault/gate adapters keep real Acquisition and SQLite behavior. Holding
# its public start return distinguishes successful startup from active delivery.
class TerminationRecorder(FailureRecorder):
    def __init__(
        self, harness: TerminationHarness, journal: SqliteEvidenceJournal
    ) -> None:
        super().__init__(harness, journal)
        self.termination_harness = harness

    async def append(self, draft: PendingEvidenceRecord) -> model.EvidenceRecord:
        if (
            isinstance(draft, PendingRxBytesEvidence)
            and self.termination_harness.rx_fails
        ):
            self.harness.trace.append("rx_append.failed")
            raise JournalFailure(JournalOperation.APPEND, JournalFailureKind.IO_FAILURE)
        return await super().append(draft)

    async def close(self) -> None:
        await super().close()
        callback = self.termination_harness.on_recorder_closed
        if callback is not None:
            callback()


class TerminationHarness(FailureHarness):
    def __init__(
        self,
        destination: Path,
        *,
        rx_fails: bool = False,
        immediate_disconnect: bool = False,
        first_fails: bool = False,
        final_fails: bool = False,
        backend_close_fails: bool = False,
        recorder_close_fails: bool = False,
    ) -> None:
        super().__init__(
            destination,
            first_fails=first_fails,
            final_fails=final_fails,
            backend_close_fails=backend_close_fails,
            recorder_close_fails=recorder_close_fails,
        )
        self.rx_fails = rx_fails
        self.immediate_disconnect = immediate_disconnect
        self.on_recorder_closed: Callable[[], None] | None = None

    async def prepare(
        self, resolved: profile.ResolvedDutProfile
    ) -> rt.PreparedObservationRun:
        prepared = await super().prepare(resolved)
        assert self.journal is not None and self.connection is not None
        if self.immediate_disconnect:
            self.connection.event_gate.allow.clear()
            await self.connection.disconnect("normalized observer link ended")
        return rt.PreparedObservationRun(
            TerminationRecorder(self, self.journal), prepared.backend
        )


class PublicationHeldAcquisition(SnapshotOnlyAcquisition):
    def __init__(self, recorder: EvidenceRecorder, trace: list[str]) -> None:
        super().__init__(recorder, trace)
        self.start_return = Gate()

    async def start(self, backend: Backend) -> model.ConnectionInstanceId:
        identity = await super().start(backend)
        await self.start_return.enter()
        return identity


def _t020_acquisitions(
    monkeypatch: pytest.MonkeyPatch, *, hold_start: bool = False
) -> list[PublicationHeldAcquisition]:
    created: list[PublicationHeldAcquisition] = []

    class CapturedAcquisition(PublicationHeldAcquisition):
        def __init__(self, recorder: EvidenceRecorder) -> None:
            assert isinstance(recorder, TerminationRecorder)
            super().__init__(recorder, recorder.harness.trace)
            if hold_start:
                self.start_return.allow.clear()
            created.append(self)

    monkeypatch.setattr(rt, "Acquisition", CapturedAcquisition)
    return created


async def _t020_started(
    harness: TerminationHarness, created: list[PublicationHeldAcquisition]
) -> PublicationHeldAcquisition:
    await _await(harness.backend_open.entered.wait())
    assert len(created) == 1
    acquisition = created[0]
    await _await(acquisition.start_return.entered.wait())
    return acquisition


async def _t020_settled(runtime: RuntimeContract) -> rt.RuntimeStatus:
    async with asyncio.timeout(3.0):
        while not runtime.status().owner_settled:
            await _checkpoint()
    return runtime.status()


async def _t020_cleanup(
    runtime: RuntimeContract,
    harnesses: tuple[TerminationHarness, ...],
    created: list[PublicationHeldAcquisition],
) -> None:
    for harness in harnesses:
        if harness.connection is not None:
            harness.connection.event_gate.allow.set()
    for acquisition in created:
        acquisition.start_return.allow.set()
    await _t014_cleanup(runtime, harnesses, list(created))


def _t020_terminal(
    runtime: RuntimeContract,
    harness: TerminationHarness,
    result: rt.RuntimeStatus,
    provenance: model.SegmentProvenance,
    *,
    reason: rt.RuntimeTerminalReason,
    trigger: aq.AcquisitionTerminalTrigger,
    primary: aq.AcquisitionFailureKind | None = None,
    intent: rt.RuntimeStopIntent = rt.RuntimeStopIntent.NONE,
) -> None:
    failed = (
        primary is not None
        or harness.backend_close_fails
        or harness.recorder_close_fails
    )
    _t014_terminal(
        runtime,
        harness,
        result,
        rt.RuntimeState.FAILED if failed else rt.RuntimeState.TERMINATED,
    )
    assert result.terminal_reason is reason
    assert result.stop_intent is intent
    assert result.primary_issue == (
        rt.RuntimeIssue(rt.RuntimeIssueSource.ACQUISITION, primary)
        if primary is not None
        else None
    )
    assert result.cleanup_issues == _t014_cleanup_issues(
        harness.backend_close_fails, harness.recorder_close_fails
    )
    snapshot = result.acquisition
    assert snapshot is not None and harness.connection is not None
    assert snapshot.state is (
        aq.AcquisitionState.FAILED
        if primary is not None or harness.backend_close_fails
        else aq.AcquisitionState.STOPPED
    )
    assert snapshot.terminal_trigger is trigger
    assert snapshot.primary_failure_kind is primary
    assert snapshot.close_failed is harness.backend_close_fails
    # These identities describe the last committed segment, never live capture.
    assert snapshot.provenance == provenance
    assert snapshot.descriptor == harness.connection.descriptor
    assert harness.consumer_calls == harness.connection.consumer_calls == 1
    assert harness.trace.index("consumer.joined") < harness.trace.index(
        "recorder.close_entered"
    )


@pytest.mark.parametrize("final_fails", [False, True])
@pytest.mark.parametrize("backend_fails", [False, True])
@pytest.mark.parametrize("recorder_fails", [False, True])
@pytest.mark.asyncio
async def test_t020_active_disconnect_joins_and_closes_without_stop_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_fails: bool,
    backend_fails: bool,
    recorder_fails: bool,
) -> None:
    runtime = _factory()()
    harness = TerminationHarness(
        tmp_path / "disconnect.sqlite",
        final_fails=final_fails,
        backend_close_fails=backend_fails,
        recorder_close_fails=recorder_fails,
    )
    created = _t020_acquisitions(monkeypatch)
    try:
        active = await _await(harness.attach(runtime))
        assert active.acquisition is not None
        provenance = active.acquisition.provenance
        assert provenance is not None and harness.connection is not None
        acquisition = created[0]
        acquisition.consumer_tail.allow.clear()
        harness.recorder_close.allow.clear()
        await harness.connection.disconnect("normalized observer link ended")
        await _await(acquisition.consumer_tail.entered.wait())
        await _checkpoint()
        draining = runtime.status()
        assert draining.state is rt.RuntimeState.DETACHING
        assert not draining.owner_settled and not draining.attach_admissible
        assert draining.stop_intent is rt.RuntimeStopIntent.NONE
        assert draining.acquisition == acquisition.snapshot()
        assert draining.acquisition.terminal_trigger is (
            aq.AcquisitionTerminalTrigger.DISCONNECTED
        )
        assert harness.recorder_close_calls == 0
        acquisition.consumer_tail.allow.set()
        await _await(harness.recorder_close.entered.wait())
        assert runtime.status().state is rt.RuntimeState.DETACHING
        assert not runtime.status().owner_settled
        harness.recorder_close.allow.set()
        result = await _t020_settled(runtime)
        _t020_terminal(
            runtime,
            harness,
            result,
            provenance,
            reason=rt.RuntimeTerminalReason.DISCONNECTED,
            trigger=aq.AcquisitionTerminalTrigger.DISCONNECTED,
            primary=aq.AcquisitionFailureKind.RECORDING_FAILURE if final_fails else None,
        )
        assert len(harness.records) == (1 if final_fails else 2)
        assert await _await(runtime.detach()) == result
        await _checkpoint()
        assert runtime.status() == result and harness.open_calls == 1
    finally:
        await _t020_cleanup(runtime, (harness,), created)


@pytest.mark.parametrize("cause", ["rx_recording", "transport"])
@pytest.mark.parametrize("backend_fails", [False, True])
@pytest.mark.asyncio
async def test_t020_active_failure_drains_without_stop_and_preserves_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cause: str, backend_fails: bool
) -> None:
    runtime = _factory()()
    harness = TerminationHarness(
        tmp_path / "failure.sqlite",
        rx_fails=cause == "rx_recording",
        backend_close_fails=backend_fails,
    )
    created = _t020_acquisitions(monkeypatch)
    primary = (
        aq.AcquisitionFailureKind.RECORDING_FAILURE
        if cause == "rx_recording"
        else aq.AcquisitionFailureKind.TRANSPORT_FAILURE
    )
    try:
        active = await _await(harness.attach(runtime))
        assert active.acquisition is not None
        provenance = active.acquisition.provenance
        assert provenance is not None and harness.connection is not None
        acquisition = created[0]
        acquisition.consumer_tail.allow.clear()
        if cause == "rx_recording":
            await harness.connection.emit_rx(b"\x00\xffambient\r\n", timestamp=1)
        else:
            await harness.connection.end_stream_unexpectedly()
        await _await(acquisition.consumer_tail.entered.wait())
        await _checkpoint()
        draining = runtime.status()
        assert draining.state is rt.RuntimeState.DETACHING
        assert not draining.owner_settled and not draining.attach_admissible
        assert draining.acquisition == acquisition.snapshot()
        assert draining.primary_issue == rt.RuntimeIssue(
            rt.RuntimeIssueSource.ACQUISITION, primary
        )
        assert harness.recorder_close_calls == 0
        acquisition.consumer_tail.allow.set()
        result = await _t020_settled(runtime)
        _t020_terminal(
            runtime,
            harness,
            result,
            provenance,
            reason=rt.RuntimeTerminalReason.ACQUISITION_FAILURE,
            trigger=aq.AcquisitionTerminalTrigger(primary.value),
            primary=primary,
        )
        assert not any(isinstance(record, model.RxBytesEvidence) for record in harness.records)
        assert await _await(runtime.detach()) == result and harness.open_calls == 1
    finally:
        await _t020_cleanup(runtime, (harness,), created)


@pytest.mark.parametrize("final_fails", [False, True])
@pytest.mark.parametrize("backend_fails", [False, True])
@pytest.mark.asyncio
async def test_t020_immediate_observed_disconnect_never_returns_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, final_fails: bool, backend_fails: bool
) -> None:
    runtime = _factory()()
    harness = TerminationHarness(
        tmp_path / "immediate.sqlite",
        immediate_disconnect=True,
        final_fails=final_fails,
        backend_close_fails=backend_fails,
    )
    created = _t020_acquisitions(monkeypatch, hold_start=True)
    try:
        attach = harness.attach(runtime)
        acquisition = await _t020_started(harness, created)
        assert harness.connection is not None
        await _await(harness.connection.event_gate.entered.wait())
        waiting = runtime.status()
        assert waiting.state is rt.RuntimeState.ATTACHING
        assert waiting.acquisition is not None
        assert waiting.acquisition.terminal_trigger is None
        provenance = waiting.acquisition.provenance
        assert provenance is not None
        harness.connection.event_gate.allow.set()
        observed = await _await(acquisition.join_terminated())
        assert observed.terminal_trigger is aq.AcquisitionTerminalTrigger.DISCONNECTED
        acquisition.start_return.allow.set()
        result = await _await(attach)
        _t020_terminal(
            runtime,
            harness,
            result,
            provenance,
            reason=rt.RuntimeTerminalReason.DISCONNECTED,
            trigger=aq.AcquisitionTerminalTrigger.DISCONNECTED,
            primary=aq.AcquisitionFailureKind.RECORDING_FAILURE if final_fails else None,
        )
    finally:
        await _t020_cleanup(runtime, (harness,), created)


@pytest.mark.asyncio
async def test_t020_queued_unobserved_disconnect_does_not_override_failed_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _factory()()
    harness = TerminationHarness(
        tmp_path / "unobserved.sqlite", immediate_disconnect=True, first_fails=True
    )
    created = _t020_acquisitions(monkeypatch)
    try:
        result = await _await(harness.attach(runtime))
        _t014_terminal(runtime, harness, result, rt.RuntimeState.FAILED)
        assert result.terminal_reason is rt.RuntimeTerminalReason.STARTUP_FAILURE
        assert result.primary_issue == rt.RuntimeIssue(
            rt.RuntimeIssueSource.ACQUISITION_START,
            aq.AcquisitionFailureKind.RECORDING_FAILURE,
        )
        assert result.acquisition == created[0].snapshot()
        assert result.acquisition is not None
        assert result.acquisition.descriptor is not None
        assert result.acquisition.provenance is None
        assert result.acquisition.terminal_trigger is (
            aq.AcquisitionTerminalTrigger.RECORDING_FAILURE
        )
        assert harness.connection is not None
        assert not harness.connection.event_gate.entered.is_set()
        assert harness.consumer_calls == harness.connection.consumer_calls == 0
        assert harness.records == []
    finally:
        await _t020_cleanup(runtime, (harness,), created)


@pytest.mark.parametrize("cause", ["rx_recording", "transport"])
@pytest.mark.asyncio
async def test_t020_failure_before_active_delivery_is_acquisition_not_startup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cause: str
) -> None:
    runtime = _factory()()
    harness = TerminationHarness(
        tmp_path / "early-failure.sqlite", rx_fails=cause == "rx_recording"
    )
    created = _t020_acquisitions(monkeypatch, hold_start=True)
    primary = (
        aq.AcquisitionFailureKind.RECORDING_FAILURE
        if cause == "rx_recording"
        else aq.AcquisitionFailureKind.TRANSPORT_FAILURE
    )
    try:
        attach = harness.attach(runtime)
        acquisition = await _t020_started(harness, created)
        assert runtime.status().state is rt.RuntimeState.ATTACHING
        assert harness.connection is not None
        provenance = acquisition.snapshot().provenance
        assert provenance is not None
        if cause == "rx_recording":
            await harness.connection.emit_rx(b"\x00\xffambient", timestamp=1)
        else:
            await harness.connection.end_stream_unexpectedly()
        observed = await _await(acquisition.join_terminated())
        assert observed.primary_failure_kind is primary
        acquisition.start_return.allow.set()
        result = await _await(attach)
        _t020_terminal(
            runtime,
            harness,
            result,
            provenance,
            reason=rt.RuntimeTerminalReason.ACQUISITION_FAILURE,
            trigger=aq.AcquisitionTerminalTrigger(primary.value),
            primary=primary,
        )
    finally:
        await _t020_cleanup(runtime, (harness,), created)


@pytest.mark.parametrize("intent", ["detach", "attach_cancelled"])
@pytest.mark.parametrize("event_order", ["before_stop", "after_stop"])
@pytest.mark.asyncio
async def test_t020_observed_disconnect_beats_stop_intent_before_start_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, intent: str, event_order: str
) -> None:
    runtime = _factory()()
    harness = TerminationHarness(tmp_path / "stop-race.sqlite")
    harness.final_append.allow.clear()
    created = _t020_acquisitions(monkeypatch, hold_start=True)
    expected_intent = (
        rt.RuntimeStopIntent.DETACH
        if intent == "detach"
        else rt.RuntimeStopIntent.ATTACH_CANCELLED
    )
    try:
        attach = harness.attach(runtime)
        acquisition = await _t020_started(harness, created)
        assert harness.connection is not None
        provenance = acquisition.snapshot().provenance
        assert provenance is not None
        if event_order == "before_stop":
            await harness.connection.disconnect()
            await _await(harness.final_append.entered.wait())
        detach: asyncio.Task[rt.RuntimeStatus] | None = None
        if intent == "detach":
            detach = harness.detach(runtime)
            await _checkpoint()
            assert runtime.status().stop_intent is expected_intent
        else:
            await _cancel_pending(runtime, attach, expected_intent, repetitions=2)
        if event_order == "after_stop":
            await harness.connection.disconnect()
            await _await(harness.final_append.entered.wait())
        assert acquisition.snapshot().terminal_trigger is (
            aq.AcquisitionTerminalTrigger.DISCONNECTED
        )
        harness.final_append.allow.set()
        acquisition.start_return.allow.set()
        if detach is not None:
            result = await _await(detach)
            assert await _await(attach) == result
        else:
            await _expect_cancelled(attach)
            result = runtime.status()
        _t020_terminal(
            runtime,
            harness,
            result,
            provenance,
            reason=rt.RuntimeTerminalReason.DISCONNECTED,
            trigger=aq.AcquisitionTerminalTrigger.DISCONNECTED,
            intent=expected_intent,
        )
    finally:
        await _t020_cleanup(runtime, (harness,), created)


@pytest.mark.parametrize("final_fails", [False, True])
@pytest.mark.parametrize("backend_fails", [False, True])
@pytest.mark.parametrize("recorder_fails", [False, True])
@pytest.mark.asyncio
async def test_t020_disconnect_beats_detach_with_independent_failure_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_fails: bool,
    backend_fails: bool,
    recorder_fails: bool,
) -> None:
    runtime = _factory()()
    harness = TerminationHarness(
        tmp_path / "disconnect-race.sqlite",
        final_fails=final_fails,
        backend_close_fails=backend_fails,
        recorder_close_fails=recorder_fails,
    )
    harness.final_append.allow.clear()
    created = _t020_acquisitions(monkeypatch)
    try:
        active = await _await(harness.attach(runtime))
        assert active.acquisition is not None and harness.connection is not None
        provenance = active.acquisition.provenance
        assert provenance is not None
        await harness.connection.disconnect()
        await _await(harness.final_append.entered.wait())
        assert created[0].snapshot().terminal_trigger is (
            aq.AcquisitionTerminalTrigger.DISCONNECTED
        )
        detach = harness.detach(runtime)
        await _checkpoint()
        assert runtime.status().stop_intent is rt.RuntimeStopIntent.DETACH
        harness.final_append.allow.set()
        result = await _await(detach)
        _t020_terminal(
            runtime,
            harness,
            result,
            provenance,
            reason=rt.RuntimeTerminalReason.DISCONNECTED,
            trigger=aq.AcquisitionTerminalTrigger.DISCONNECTED,
            primary=aq.AcquisitionFailureKind.RECORDING_FAILURE if final_fails else None,
            intent=rt.RuntimeStopIntent.DETACH,
        )
        assert len(harness.records) == (1 if final_fails else 2)
    finally:
        await _t020_cleanup(runtime, (harness,), created)


@pytest.mark.parametrize("backend_fails", [False, True])
@pytest.mark.asyncio
async def test_t020_cancelled_detach_waiter_still_joins_observed_disconnect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend_fails: bool
) -> None:
    runtime = _factory()()
    harness = TerminationHarness(
        tmp_path / "cancelled-stop.sqlite", backend_close_fails=backend_fails
    )
    harness.final_append.allow.clear()
    created = _t020_acquisitions(monkeypatch)
    try:
        active = await _await(harness.attach(runtime))
        assert active.acquisition is not None and harness.connection is not None
        provenance = active.acquisition.provenance
        assert provenance is not None
        await harness.connection.disconnect()
        await _await(harness.final_append.entered.wait())
        cancelled = harness.detach(runtime)
        observer = harness.detach(runtime)
        await _checkpoint()
        assert runtime.status().stop_intent is rt.RuntimeStopIntent.DETACH
        await _cancel_pending(
            runtime, cancelled, rt.RuntimeStopIntent.DETACH, repetitions=2
        )
        harness.final_append.allow.set()
        result = await _await(observer)
        await _expect_cancelled(cancelled)
        _t020_terminal(
            runtime,
            harness,
            result,
            provenance,
            reason=rt.RuntimeTerminalReason.DISCONNECTED,
            trigger=aq.AcquisitionTerminalTrigger.DISCONNECTED,
            intent=rt.RuntimeStopIntent.DETACH,
        )
    finally:
        await _t020_cleanup(runtime, (harness,), created)


@pytest.mark.asyncio
async def test_t020_late_terminal_delivery_cannot_publish_into_new_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _factory()()
    first = TerminationHarness(tmp_path / "old.sqlite", immediate_disconnect=True)
    second = TerminationHarness(tmp_path / "new.sqlite")
    first.recorder_close.allow.clear()
    second.preparation.allow.clear()
    created = _t020_acquisitions(monkeypatch, hold_start=True)
    second_attach: list[asyncio.Task[rt.RuntimeStatus]] = []
    first.on_recorder_closed = lambda: second_attach.append(second.attach(runtime))
    try:
        old_attach = first.attach(runtime)
        acquisition = await _t020_started(first, created)
        assert first.connection is not None
        first.connection.event_gate.allow.set()
        historical = await _await(acquisition.join_terminated())
        assert historical.terminal_trigger is aq.AcquisitionTerminalTrigger.DISCONNECTED
        acquisition.start_return.allow.set()
        await _checkpoint()
        assert runtime.status().state is rt.RuntimeState.DETACHING
        await _await(first.recorder_close.entered.wait())
        assert not runtime.status().owner_settled
        with pytest.raises(rt.RuntimeRejectedError) as busy:
            await runtime.attach(_profile(), second.prepare)
        assert busy.value.kind is rt.RuntimeRejectedKind.BUSY
        assert second.received_profiles == []
        first.recorder_close.allow.set()
        await _await(second.preparation.entered.wait())
        current = runtime.status()
        assert current.state is rt.RuntimeState.ATTACHING
        old_result = await _await(old_attach)
        assert old_result.state is rt.RuntimeState.TERMINATED
        assert old_result.terminal_reason is rt.RuntimeTerminalReason.DISCONNECTED
        assert old_result.acquisition == historical and old_result.owner_settled
        assert current.run_id != old_result.run_id and current.session_id is None
        assert await _await(acquisition.join_terminated()) == historical
        await _checkpoint()
        assert runtime.status() == current
        second.preparation.allow.set()
        await _await(second.backend_open.entered.wait())
        assert len(created) == 2
        created[1].start_return.allow.set()
        active = await _await(second_attach[0])
        assert active.state is rt.RuntimeState.ACTIVE
        assert active.session_id != old_result.session_id
        assert active.acquisition is not None
        assert active.acquisition.terminal_trigger is None
        assert old_result.acquisition == historical
        assert first.open_calls == second.open_calls == 1
    finally:
        first.on_recorder_closed = None
        await _t020_cleanup(runtime, (first, second), created)
