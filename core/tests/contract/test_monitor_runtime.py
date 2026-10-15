"""009 T011 RED: public Monitor admission/lifetime on the real runtime.

Only persistence/backend/clock boundaries are controlled here. No admission,
matching, stop policy or runtime owner is implemented in the harness. T012's
provisional internal synchronous `_seal_monitors()` seam models the specified
incarnation-wide Core seal; it is not a delivery or operation-cancellation API.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any, NoReturn, cast
from uuid import uuid4

import pytest

from dutchmate_core import evidence, model, monitor, profile
from dutchmate_core import runtime as rt
from dutchmate_core.acquisition import AcquisitionFailureKind
from tests.contract.test_monitor_recording import (
    AppendGates,
    ChargeProbe,
    ManualClock,
    _await,
    _turn,
)
from tests.contract.test_observation_runtime import _profile
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixtureFactory,
    FixtureLifecycleGate,
)

type MonitorEntry = Callable[[monitor.MonitorRequest], Awaitable[monitor.MonitorReport]]


def _monitor_entry(owner: rt.ObservationRuntime) -> MonitorEntry:
    method = getattr(owner, "monitor", None)
    assert callable(method), "T012 missing: ObservationRuntime.monitor"
    return cast(MonitorEntry, method)


def _seal(owner: rt.ObservationRuntime) -> None:
    method = getattr(owner, "_seal_monitors", None)
    assert callable(method), "T012 missing: internal incarnation Monitor seal"
    assert method() is None, "Core seal must be synchronous and resource-free"


def _kind(draft: evidence.PendingEvidenceRecord) -> str:
    if isinstance(draft, evidence.PendingOperationStartedEvidence):
        return "start"
    if isinstance(draft, evidence.PendingOperationEndedEvidence):
        return "end"
    if isinstance(draft, evidence.PendingSegmentStartedEvidence):
        return "segment_start"
    if isinstance(draft, evidence.PendingSegmentEndedEvidence):
        return "segment_end"
    if isinstance(draft, evidence.PendingObserverLossEvidence):
        return "loss"
    return "rx"


class RuntimeRecorder:
    """Gate actual sequence assignment/ACK; never implement runtime policy."""

    def __init__(self, policy: model.SessionPolicy) -> None:
        self.policy = policy
        self.session_id = model.SessionId(f"monitor-runtime-{uuid4()}")
        self.journal = evidence.InMemoryEvidenceRecorder()
        self.gates = {
            name: AppendGates()
            for name in ("start", "end", "rx", "loss", "segment_start", "segment_end")
        }
        self.acks: dict[str, asyncio.Queue[model.EvidenceRecord]] = {
            name: asyncio.Queue() for name in self.gates
        }
        self.fail_before: set[str] = set()
        self.fail_ack: set[str] = set()
        self.submitted: list[evidence.PendingEvidenceRecord] = []
        self.trace: list[str] = []
        self.inflight = 0
        self.close_calls = 0
        self.close_during_append = False

    async def append(
        self, draft: evidence.PendingEvidenceRecord
    ) -> model.EvidenceRecord:
        kind = _kind(draft)
        self.submitted.append(draft)
        self.inflight += 1
        try:
            await self.gates[kind].commit.enter()
            if kind in self.fail_before:
                raise evidence.JournalFailure(
                    evidence.JournalOperation.APPEND,
                    evidence.JournalFailureKind.IO_FAILURE,
                )
            record = await self.journal.append(draft)
            await self.gates[kind].acknowledgement.enter()
            if kind in self.fail_ack:
                raise evidence.JournalFailure(
                    evidence.JournalOperation.APPEND,
                    evidence.JournalFailureKind.IO_FAILURE,
                )
            self.trace.append(f"{kind}.ack")
            self.acks[kind].put_nowait(record)
            return record
        finally:
            self.inflight -= 1

    async def close(self) -> None:
        self.close_calls += 1
        self.close_during_append |= self.inflight != 0
        self.trace.append("recorder.closed")

    def release(self) -> None:
        self.fail_before.clear()
        self.fail_ack.clear()
        for gates in self.gates.values():
            gates.commit.allow.set()
            gates.acknowledgement.allow.set()

    def markers(
        self,
    ) -> list[model.OperationStartedEvidence | model.OperationEndedEvidence]:
        return [
            record
            for record in self.journal.snapshot()
            if isinstance(
                record, (model.OperationStartedEvidence, model.OperationEndedEvidence)
            )
        ]


class RuntimeCase:
    def __init__(
        self,
        factory: BackendFixtureFactory = BACKEND_FIXTURE_FACTORIES[0],
        *,
        owner: rt.ObservationRuntime | None = None,
        access_mode: str = "present",
    ) -> None:
        self.owner = rt.ObservationRuntime() if owner is None else owner
        self.profile = _profile()
        self.recorder = RuntimeRecorder(self.profile.session_policy)
        self.fixture = factory()
        # ChargeProbe uses the actual durable codec, so supply the fixture-owned
        # envelope just as the real-journal integration cases do.
        self.fixture.connection.descriptor = replace(
            self.fixture.connection.descriptor,
            connection_provenance=model.PersistedConnectionProvenance(
                model.ConnectionProvenanceSnapshot(
                    envelope_version=1,
                    backend_kind="fixture/monitor",
                    backend_schema_version=1,
                    fields=(model.ProvenanceField("transport", "simulated"),),
                )
            ),
        )
        self.clock = ManualClock()
        self.coordinator = monitor.MonitorRecordingCoordinator(
            recorder=self.recorder, clock=self.clock
        )
        self.charge = ChargeProbe()
        self.access = monitor.PreparedMonitorAccess(
            self.recorder.session_id,
            self.recorder.policy,
            self.coordinator,
            self.clock,
            self.charge,
        )
        self.access_mode = access_mode
        self.preparation = FixtureLifecycleGate()
        gate = getattr(self.fixture.backend, "open_gate", None)
        assert isinstance(gate, FixtureLifecycleGate)
        self.backend_open = gate
        self.active: rt.RuntimeStatus | None = None
        self.tasks: list[asyncio.Task[Any]] = []

    def request(
        self, *, condition: bytes = b"PASS", max_rx: int = 1024
    ) -> monitor.MonitorRequest:
        return monitor.MonitorRequest(self.recorder.session_id, condition, 1000, max_rx)

    def spawn[T](self, work: Awaitable[T]) -> asyncio.Task[T]:
        async def run() -> T:
            return await work

        task = asyncio.create_task(run())
        self.tasks.append(task)
        return task

    async def prepare(
        self, selected: profile.ResolvedDutProfile
    ) -> rt.PreparedObservationRun:
        assert selected == self.profile
        await self.preparation.enter()
        return rt.PreparedObservationRun(
            self.coordinator,
            self.fixture.backend,
            monitor_access=self.access if self.access_mode == "present" else None,
        )

    async def attach(self) -> rt.RuntimeStatus:
        self.active = await _await(self.owner.attach(self.profile, self.prepare))
        assert self.active.state is rt.RuntimeState.ACTIVE
        return self.active

    async def begin(
        self, request: monitor.MonitorRequest | None = None
    ) -> asyncio.Task[monitor.MonitorReport]:
        method = _monitor_entry(self.owner)  # Fail explicitly before starting waiters.
        task = self.spawn(method(self.request() if request is None else request))
        await _await(self.recorder.acks["start"].get())
        await _turn()  # Positive ACK publication/install is synchronous in production.
        return task

    async def rx(self, payload: bytes) -> model.EvidenceRecord:
        await self.fixture.connection.emit_rx(payload, timestamp=123)
        return await _await(self.recorder.acks["rx"].get())

    async def finish(self) -> None:
        self.recorder.release()
        self.preparation.allow.set()
        self.backend_open.allow.set()
        for gate in (
            self.fixture.connection.read_gate,
            self.fixture.connection.event_gate,
            self.fixture.connection.close_gate,
            self.fixture.connection.consumer_exit_gate,
        ):
            gate.allow.set()
        self.clock.advance(model.SQLITE_INTEGER_MAX)
        await _await(
            asyncio.gather(self.owner.detach(), *self.tasks, return_exceptions=True)
        )


@asynccontextmanager
async def _case(
    factory: BackendFixtureFactory = BACKEND_FIXTURE_FACTORIES[0],
    *,
    attach: bool = True,
    access_mode: str = "present",
) -> AsyncIterator[RuntimeCase]:
    case = RuntimeCase(factory, access_mode=access_mode)
    try:
        if attach:
            await case.attach()
        yield case
    finally:
        await case.finish()


async def _rejected(
    case: RuntimeCase, request: monitor.MonitorRequest, kind: str
) -> None:
    method = _monitor_entry(case.owner)
    before = len(case.recorder.markers())
    with pytest.raises(monitor.MonitorRejected) as rejected:
        await _await(method(request))
    assert rejected.value.kind == kind
    assert len(case.recorder.markers()) == before


@pytest.mark.parametrize("bad", [None, object(), {}, "session"])
@pytest.mark.asyncio
async def test_t011_request_type_guard_precedes_association(bad: object) -> None:
    owner = rt.ObservationRuntime()
    method = _monitor_entry(owner)
    before = owner.status()
    with pytest.raises(rt.RuntimeRejectedError) as rejected:
        await method(cast(monitor.MonitorRequest, bad))
    assert rejected.value.kind is rt.RuntimeRejectedKind.INVALID_REQUEST
    assert owner.status() == before


@pytest.mark.parametrize(
    "context", ["other-loop", "other-thread", "no-running-loop", "closed-owner"]
)
def test_t011_owner_context_precedes_type_lock_or_scheduling(
    context: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.new_event_loop()

    async def construct() -> rt.ObservationRuntime:
        return rt.ObservationRuntime()

    owner = loop.run_until_complete(construct())

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        pytest.fail("wrong context reached locking/scheduling")

    try:
        method = _monitor_entry(owner)
        if context == "closed-owner":
            loop.close()

        async def invoke() -> monitor.MonitorReport:
            return await method(cast(monitor.MonitorRequest, None))

        with monkeypatch.context() as patch:
            patch.setattr(asyncio.Lock, "acquire", forbidden)
            patch.setattr(asyncio, "create_task", forbidden)
            with pytest.raises(rt.RuntimeRejectedError) as rejected:
                if context == "no-running-loop":
                    work = invoke()
                    try:
                        work.send(None)
                        pytest.fail("guard did not reject before await")
                    finally:
                        work.close()
                elif context == "other-thread":
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(lambda: asyncio.run(invoke())).result(timeout=3)
                else:
                    asyncio.run(invoke())
            assert rejected.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_t011_no_association_rejects_without_preparation() -> None:
    async with _case(attach=False) as case:
        await _rejected(case, case.request(), "no_associated_session")
        assert case.recorder.submitted == []
        assert case.fixture.connection.consumer_calls == 0


@pytest.mark.parametrize("access_mode", ["present", "absent"])
@pytest.mark.asyncio
async def test_t011_explicit_session_mismatch_precedes_support(
    access_mode: str,
) -> None:
    async with _case(access_mode=access_mode) as case:
        await _rejected(
            case,
            replace(case.request(), session_id=model.SessionId("other")),
            "session_not_associated",
        )
        assert case.owner.status().state is rt.RuntimeState.ACTIVE


@pytest.mark.asyncio
async def test_t011_legacy_preparation_attaches_without_monitor_support() -> None:
    async with _case(access_mode="absent") as case:
        await _rejected(case, case.request(), "monitor_unavailable")
        assert case.owner.status().state is rt.RuntimeState.ACTIVE
        assert case.fixture.connection.consumer_calls == 1


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize("mismatch", ["coordinator", "session", "clock"])
@pytest.mark.asyncio
async def test_t033_invalid_present_monitor_access_fails_preparation_before_open(
    factory: BackendFixtureFactory,
    mismatch: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _case(factory, attach=False) as case:
        if mismatch == "coordinator":
            other = monitor.MonitorRecordingCoordinator(
                recorder=case.recorder, clock=case.clock
            )
            case.access = replace(case.access, coordinator=other)
        elif mismatch == "session":
            # Immutable access can become stale when its infrastructure changes
            # between construction and transfer to the runtime owner.
            case.recorder.session_id = model.SessionId("changed-before-transfer")
        else:
            monkeypatch.setattr(case.coordinator, "_clock", ManualClock())

        result = await _await(case.owner.attach(case.profile, case.prepare))

        assert result.state is rt.RuntimeState.FAILED
        assert result.terminal_reason is rt.RuntimeTerminalReason.STARTUP_FAILURE
        assert result.primary_issue == rt.RuntimeIssue(
            rt.RuntimeIssueSource.INTERNAL_CONTRACT, "internal_contract_failure"
        )
        assert result.session_id == case.recorder.session_id
        assert result.owner_settled and result.attach_admissible
        assert result.physical_release_confirmed and result.recorder_close_confirmed
        assert result.cleanup_issues == () and result.acquisition is None
        assert not case.backend_open.entered.is_set()
        assert case.fixture.connection.consumer_calls == 0
        assert case.recorder.submitted == []
        assert case.recorder.close_calls == 1


@pytest.mark.parametrize("stage", ["attaching-known-session", "draining", "terminal"])
@pytest.mark.asyncio
async def test_t011_only_active_run_can_monitor(stage: str) -> None:
    async with _case(attach=False) as case:
        if stage == "attaching-known-session":
            case.backend_open.allow.clear()
            case.spawn(case.attach())
            await _await(case.backend_open.entered.wait())
            assert case.owner.status().session_id == case.recorder.session_id
        else:
            await case.attach()
            if stage == "draining":
                case.fixture.connection.close_gate.allow.clear()
                case.spawn(case.owner.detach())
                await _await(case.fixture.connection.close_gate.entered.wait())
            else:
                await _await(case.owner.detach())
        await _rejected(case, case.request(), "not_active")


@pytest.mark.asyncio
async def test_t011_new_attach_immediately_removes_previous_session_selection() -> None:
    async with _case() as first:
        await first.owner.detach()
        next_case = RuntimeCase(owner=first.owner)
        next_case.preparation.allow.clear()
        try:
            next_case.spawn(next_case.attach())
            await _await(next_case.preparation.entered.wait())
            await _rejected(first, first.request(), "no_associated_session")
        finally:
            await next_case.finish()


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.asyncio
async def test_t011_admission_checks_reported_committed_rx_capability(
    factory: BackendFixtureFactory,
) -> None:
    async with _case(factory) as case:
        provenance = case.coordinator.current_provenance
        assert provenance is not None
        # Controlled committed-boundary injection: the acquisition status may lag
        # publication. No new physical backend capability is emulated.
        without_rx = replace(
            provenance, capabilities=model.BackendCapabilities(frozenset())
        )
        await case.coordinator.append(
            evidence.PendingSegmentStartedEvidence(without_rx)
        )
        await _rejected(case, case.request(), "capability_unavailable")


@pytest.mark.asyncio
async def test_t011_missing_committed_segment_is_unavailable() -> None:
    async with _case() as case:
        provenance = case.coordinator.current_provenance
        assert provenance is not None
        await case.coordinator.append(
            evidence.PendingSegmentEndedEvidence(
                provenance.connection_id,
                provenance.segment_id,
                model.SegmentEndReason.DISCONNECTED,
            )
        )
        await _rejected(case, case.request(), "monitor_unavailable")


@pytest.mark.parametrize("bad_charge", [(8193, 1), (1, 8193)])
@pytest.mark.asyncio
async def test_t011_marker_preflight_rejects_either_charge_before_start(
    bad_charge: tuple[int, int],
) -> None:
    async with _case() as case:
        case.charge.override = bad_charge
        await _rejected(case, case.request(), "evidence_policy_incompatible")


@pytest.mark.asyncio
async def test_t011_policy_check_precedes_busy_slot() -> None:
    async with _case() as case:
        pending = await case.begin()
        case.charge.override = (8193, 1)
        await _rejected(case, case.request(), "evidence_policy_incompatible")
        await case.rx(b"PASS")
        await _await(pending)


@pytest.mark.asyncio
async def test_t011_busy_spans_end_acknowledgement_and_then_releases() -> None:
    async with _case() as case:
        case.recorder.gates["end"].acknowledgement.allow.clear()
        first = await case.begin()
        await case.rx(b"PASS trailing")
        await _await(case.recorder.gates["end"].acknowledgement.entered.wait())
        await _rejected(case, case.request(), "busy")
        assert not first.done()
        case.recorder.gates["end"].acknowledgement.allow.set()
        first_report = await _await(first)
        second = await case.begin()
        await case.rx(b"PASS")
        second_report = await _await(second)
        assert second_report.operation_id != first_report.operation_id
        assert len(case.recorder.markers()) == 4


@pytest.mark.asyncio
async def test_t011_clock_fault_before_start_rejects_without_marker() -> None:
    async with _case() as case:
        case.clock.advance(model.SQLITE_INTEGER_MAX)
        await _rejected(case, case.request(), "monitor_unavailable")


@pytest.mark.asyncio
async def test_t011_global_seal_precedes_absent_association_and_is_permanent() -> None:
    async with _case(attach=False) as case:
        _seal(case.owner)
        _seal(case.owner)
        await _rejected(case, case.request(), "monitor_unavailable")
        await case.attach()
        await _rejected(case, case.request(), "monitor_unavailable")
        assert case.recorder.markers() == []


@pytest.mark.asyncio
async def test_t011_seal_context_guard_rejects_wrong_loop() -> None:
    owner = rt.ObservationRuntime()
    with pytest.raises(rt.RuntimeRejectedError) as rejected:
        await asyncio.to_thread(lambda: asyncio.run(_invoke_seal(owner)))
    assert rejected.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT


async def _invoke_seal(owner: rt.ObservationRuntime) -> None:
    _seal(owner)


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize("outcome", list(model.MonitorOutcome))
@pytest.mark.asyncio
async def test_t011_all_normal_outcomes_keep_run_refs_and_capture_facts(
    factory: BackendFixtureFactory,
    outcome: model.MonitorOutcome,
) -> None:
    async with _case(factory) as case:
        pending = await case.begin(
            case.request(
                max_rx=2 if outcome is model.MonitorOutcome.BYTE_LIMIT else 1024
            )
        )
        assert case.active is not None and case.active.run_id is not None
        if outcome is model.MonitorOutcome.MATCHED:
            await case.rx(b"PASS trailing")
        elif outcome is model.MonitorOutcome.BYTE_LIMIT:
            await case.rx(b"xxPASS")
        elif outcome is model.MonitorOutcome.TIMEOUT:
            case.clock.advance(1000000100)
        elif outcome is model.MonitorOutcome.DETACHED:
            case.spawn(case.owner.detach())
        elif outcome is model.MonitorOutcome.DISCONNECTED:
            await case.fixture.connection.disconnect()
        elif outcome is model.MonitorOutcome.TIMESTAMP_ORIGIN_RESET:
            domain = (
                case.fixture.connection.descriptor.backend_observation_timestamp_domain
            )
            await case.fixture.connection.reset_timestamp_origin(
                replace(domain, origin_id="next-origin", domain_id="next-domain")
            )
        elif outcome is model.MonitorOutcome.RECORDING_FAILURE:
            case.recorder.fail_before.add("rx")
            await case.fixture.connection.emit_rx(b"unrecorded", timestamp=123)
        elif outcome is model.MonitorOutcome.TRANSPORT_FAILURE:
            await case.fixture.connection.end_stream_unexpectedly()
        else:
            _seal(case.owner)
        report = await _await(pending)
        assert report.outcome is outcome
        assert report.run_id == case.active.run_id.value
        assert report.session_id == case.active.session_id == case.recorder.session_id
        assert case.active.acquisition is not None
        assert report.provenance == case.active.acquisition.provenance
        assert report.started_record.sequence == 1
        assert report.ended_record is not None and report.durability == "complete"
        assert report.end_failure is None
        assert report.window.start_inclusive == 2
        assert (report.match is not None) == (outcome is model.MonitorOutcome.MATCHED)
        assert case.fixture.connection.consumer_calls == 1
        assert not case.recorder.close_during_append
        if outcome is model.MonitorOutcome.RECORDING_FAILURE:
            snapshot = case.owner.status().acquisition
            assert snapshot is not None
            assert (
                snapshot.primary_failure_kind
                is AcquisitionFailureKind.RECORDING_FAILURE
            )
            assert not any(
                isinstance(r, model.SegmentEndedEvidence)
                for r in case.recorder.journal.snapshot()
            )
        if outcome in {
            model.MonitorOutcome.MATCHED,
            model.MonitorOutcome.BYTE_LIMIT,
            model.MonitorOutcome.TIMEOUT,
            model.MonitorOutcome.SERVICE_STOPPING,
        }:
            assert case.owner.status().state is rt.RuntimeState.ACTIVE


@pytest.mark.parametrize("offset", [-1, 0, 1])
@pytest.mark.parametrize("stop", ["detach", "service"])
@pytest.mark.asyncio
async def test_t011_timeout_wins_stop_equality_without_rx(
    offset: int, stop: str
) -> None:
    async with _case() as case:
        pending = await case.begin()
        case.clock.advance(1000000100 + offset)
        if stop == "detach":
            case.spawn(case.owner.detach())
        else:
            _seal(case.owner)
        report = await _await(pending)
        expected = (
            model.MonitorOutcome.TIMEOUT
            if offset >= 0
            else (
                model.MonitorOutcome.DETACHED
                if stop == "detach"
                else model.MonitorOutcome.SERVICE_STOPPING
            )
        )
        assert report.outcome is expected and report.window == model.SequenceRange(2, 2)
        assert report.clock.decided_at_ns == 1000000100 + offset


@pytest.mark.parametrize("phase", ["start", "end"])
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.asyncio
async def test_t011_detach_joins_submitted_marker_ack_before_writer_close(
    phase: str,
    factory: BackendFixtureFactory,
) -> None:
    async with _case(factory) as case:
        method = _monitor_entry(case.owner)
        gate = case.recorder.gates[phase].acknowledgement
        gate.allow.clear()
        pending = case.spawn(method(case.request()))
        await _await(case.recorder.gates["start"].acknowledgement.entered.wait())
        if phase == "end":
            await case.rx(b"PASS")
        await _await(gate.entered.wait())
        stopping = case.spawn(case.owner.detach())
        await _turn()
        assert not stopping.done() and case.recorder.close_calls == 0
        assert not case.owner.status().recorder_close_confirmed
        await _rejected(case, case.request(), "not_active")
        gate.allow.set()
        report = await _await(pending)
        terminal = await _await(stopping)
        assert report.outcome is (
            model.MonitorOutcome.DETACHED
            if phase == "start"
            else model.MonitorOutcome.MATCHED
        )
        assert terminal.recorder_close_confirmed and terminal.physical_release_confirmed
        assert case.recorder.trace.index("end.ack") < case.recorder.trace.index(
            "recorder.closed"
        )
        assert case.recorder.close_calls == 1 and not case.recorder.close_during_append


@pytest.mark.asyncio
async def test_t011_report_stays_pinned_until_settlement_before_reattach() -> None:
    async with _case() as first:
        first.recorder.gates["end"].acknowledgement.allow.clear()
        pending = await first.begin()
        await first.rx(b"PASS")
        await _await(first.recorder.gates["end"].acknowledgement.entered.wait())
        stopping = first.spawn(first.owner.detach())
        await _turn()
        with pytest.raises(rt.RuntimeRejectedError) as rejected:
            await first.owner.attach(first.profile, first.prepare)
        assert rejected.value.kind is rt.RuntimeRejectedKind.BUSY
        first.recorder.gates["end"].acknowledgement.allow.set()
        report = await _await(pending)
        await _await(stopping)
        next_case = RuntimeCase(owner=first.owner)
        try:
            next_active = await next_case.attach()
            assert first.active is not None and first.active.run_id is not None
            assert next_active.run_id is not None
            assert (
                report.run_id == first.active.run_id.value != next_active.run_id.value
            )
            await _rejected(next_case, first.request(), "session_not_associated")
        finally:
            await next_case.finish()


@pytest.mark.asyncio
async def test_t011_end_failure_preserves_match_and_active_capture() -> None:
    async with _case() as case:
        case.recorder.fail_ack.add("end")
        pending = await case.begin()
        await case.rx(b"PASS trailing")
        report = await _await(pending)
        assert report.outcome is model.MonitorOutcome.MATCHED
        assert report.durability == "end_unconfirmed" and report.ended_record is None
        assert report.end_failure == monitor.MonitorEndFailure("journal", "io_failure")
        assert case.owner.status().state is rt.RuntimeState.ACTIVE
        assert case.owner.status().primary_issue is None
        assert case.owner.evidence_read_cleanup_confirmed
        await case.rx(b"ambient after end failure")
        assert case.fixture.connection.consumer_calls == 1


@pytest.mark.asyncio
async def test_t011_busy_begins_before_start_marker_acknowledgement() -> None:
    async with _case() as case:
        method = _monitor_entry(case.owner)
        gate = case.recorder.gates["start"].commit
        gate.allow.clear()
        first = case.spawn(method(case.request()))
        await _await(gate.entered.wait())
        await _rejected(case, case.request(), "busy")
        gate.allow.set()
        await _await(case.recorder.acks["start"].get())
        await case.rx(b"PASS")
        assert (await _await(first)).outcome is model.MonitorOutcome.MATCHED


@pytest.mark.asyncio
async def test_t011_detach_revalidates_waiting_start_before_marker_submission() -> None:
    async with _case() as case:
        method = _monitor_entry(case.owner)
        ack = case.recorder.gates["rx"].acknowledgement
        ack.allow.clear()
        await case.fixture.connection.emit_rx(b"ambient", timestamp=123)
        await _await(ack.entered.wait())
        waiting = case.spawn(method(case.request()))
        await _turn()
        stopping = case.spawn(case.owner.detach())
        await _turn()
        assert case.recorder.markers() == [] and case.recorder.close_calls == 0
        ack.allow.set()
        with pytest.raises(monitor.MonitorRejected) as rejected:
            await _await(waiting)
        assert rejected.value.kind == "not_active"
        terminal = await _await(stopping)
        assert terminal.recorder_close_confirmed
        assert case.recorder.markers() == []


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.asyncio
async def test_t011_start_pins_published_segment_even_when_acquisition_snapshot_lags(
    factory: BackendFixtureFactory,
) -> None:
    async with _case(factory) as case:
        provenance = case.coordinator.current_provenance
        assert provenance is not None
        published = replace(provenance, segment_id=model.SegmentId("published-segment"))
        await case.coordinator.append(evidence.PendingSegmentStartedEvidence(published))
        pending = await case.begin()
        case.clock.advance(1000000100)
        report = await _await(pending)
        assert report.provenance == published
        assert report.started_record.sequence == 2
        assert report.window == model.SequenceRange(3, 3)
        assert case.active is not None and case.active.acquisition is not None
        assert case.active.acquisition.provenance == provenance


@pytest.mark.asyncio
async def test_t011_cancelled_delivery_keeps_the_single_owner_until_end_settles() -> (
    None
):
    async with _case() as case:
        end_ack = case.recorder.gates["end"].acknowledgement
        end_ack.allow.clear()
        delivery = await case.begin()
        delivery.cancel()
        await _turn()
        await case.rx(b"PASS")
        await _await(end_ack.entered.wait())
        await _rejected(case, case.request(), "busy")
        end_ack.allow.set()
        await _await(case.recorder.acks["end"].get())
        await _turn()
        with pytest.raises(asyncio.CancelledError):
            await delivery
        assert len(case.recorder.markers()) == 2
        assert case.owner.status().state is rt.RuntimeState.ACTIVE
        next_delivery = await case.begin()
        await case.rx(b"PASS")
        assert (await _await(next_delivery)).durability == "complete"


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize("first", ["detach", "service"])
@pytest.mark.parametrize("offset", [-1, 0, 1], ids=["before", "at", "after"])
@pytest.mark.asyncio
async def test_t026_first_stop_intent_and_deadline_survive_later_stop_and_end_latency(
    factory: BackendFixtureFactory, first: str, offset: int
) -> None:
    # Catches later stop overwriting the first decision, or stop winning equality.
    async with _case(factory) as case:
        ack = case.recorder.gates["end"].acknowledgement
        ack.allow.clear()
        delivery = await case.begin()
        # Keep the timer asleep so the stop path must apply the equality rule.
        case.clock.value = 1_000_000_100 + offset
        if first == "service":
            _seal(case.owner)
            await _await(ack.entered.wait())
            stopping = case.spawn(case.owner.detach())
        else:
            stopping = case.spawn(case.owner.detach())
            await _await(ack.entered.wait())
            _seal(case.owner)
        case.clock.advance(5_000_000_000)
        await _turn()
        assert not delivery.done() and not stopping.done()
        assert case.recorder.close_calls == 0
        ack.allow.set()
        report = await _await(delivery)
        terminal = await _await(stopping)
        assert report.outcome is (
            model.MonitorOutcome.TIMEOUT
            if offset >= 0
            else model.MonitorOutcome.DETACHED
            if first == "detach"
            else model.MonitorOutcome.SERVICE_STOPPING
        )
        assert report.clock.decided_at_ns == 1_000_000_100 + offset
        assert report.window == model.SequenceRange(2, 2) and report.match is None
        assert report.examined_rx_bytes == 0 and report.durability == "complete"
        assert terminal.primary_issue is None and terminal.recorder_close_confirmed
        assert case.owner.evidence_read_cleanup_confirmed and case.clock.waiters == {}


async def _t026_pause_runtime(
    case: RuntimeCase, phase: str
) -> tuple[asyncio.Task[monitor.MonitorReport], Callable[[], None]]:
    """Pause only external append/ACK work; runtime admission remains real."""
    if phase == "waiting-gate":
        gate = case.recorder.gates["rx"].acknowledgement
        gate.allow.clear()
        await case.fixture.connection.emit_rx(b"ambient", timestamp=123)
        await _await(gate.entered.wait())
        delivery = case.spawn(_monitor_entry(case.owner)(case.request()))
        await _turn()
        return delivery, gate.allow.set
    if phase.startswith("start-"):
        gates = case.recorder.gates["start"]
        gate = gates.commit if phase == "start-commit" else gates.acknowledgement
        gate.allow.clear()
        delivery = case.spawn(_monitor_entry(case.owner)(case.request()))
        await _await(gate.entered.wait())
        return delivery, gate.allow.set
    if phase == "active":
        return await case.begin(), lambda: None
    gates = case.recorder.gates["end"]
    gate = gates.commit if phase == "end-commit" else gates.acknowledgement
    gate.allow.clear()
    delivery = await case.begin()
    await case.rx(b"PASS trailing\0\xff")
    await _await(gate.entered.wait())
    return delivery, gate.allow.set


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.asyncio
async def test_t026_cancellation_before_admission_creates_no_owner_or_marker(
    factory: BackendFixtureFactory,
) -> None:
    # Catches scheduling owned work before the public coroutine is admitted.
    async with _case(factory) as case:
        before = case.owner.status()

        async def invoke() -> monitor.MonitorReport:
            return await _monitor_entry(case.owner)(case.request())

        delivery = asyncio.create_task(invoke())
        case.tasks.append(delivery)
        delivery.cancel()
        with pytest.raises(asyncio.CancelledError):
            await _await(delivery)
        assert case.recorder.markers() == [] and case.owner.status() == before
        next_delivery = await case.begin()
        await case.rx(b"PASS")
        assert (await _await(next_delivery)).durability == "complete"


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize(
    "phase",
    ["waiting-gate", "start-commit", "start-ack", "active", "end-commit", "end-ack"],
)
@pytest.mark.asyncio
async def test_t026_repeated_delivery_cancellation_keeps_busy_and_submitted_work(
    factory: BackendFixtureFactory, phase: str
) -> None:
    # Catches unshielded owners, premature slot release or cancellation of a write.
    async with _case(factory) as case:
        delivery, release = await _t026_pause_runtime(case, phase)
        before = case.owner.status()
        for _ in range(3):
            delivery.cancel()
            await _turn()
            assert not delivery.done()
            await _rejected(case, case.request(), "busy")
        assert case.recorder.close_calls == 0 and case.owner.status() == before
        release()
        if not phase.startswith("end-"):
            await _await(case.clock.wait_started.wait())
            await case.rx(b"PASS trailing\0\xff")
        await _await(case.recorder.acks["end"].get())
        with pytest.raises(asyncio.CancelledError):
            await _await(delivery)
        markers = case.recorder.markers()
        assert len(markers) == 2
        start, end = markers
        assert isinstance(start, model.OperationStartedEvidence)
        assert isinstance(end, model.OperationEndedEvidence)
        assert start.sequence == (2 if phase == "waiting-gate" else 1)
        assert end.outcome is model.MonitorOutcome.MATCHED
        assert end.examined_rx_bytes == 4 and end.match is not None
        assert case.clock.waiters == {} and case.owner.status() == before
        assert case.fixture.connection.consumer_calls == 1
        # Discard test notifications, not evidence, before checking slot reuse.
        while not case.recorder.acks["start"].empty():
            case.recorder.acks["start"].get_nowait()
        next_delivery = await case.begin()
        await case.rx(b"PASS")
        assert (await _await(next_delivery)).operation_id != start.operation_id


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize(
    "phase",
    ["waiting-gate", "start-commit", "start-ack", "active", "end-commit", "end-ack"],
)
@pytest.mark.asyncio
async def test_t026_detach_settles_every_marker_phase_without_holding_lifecycle_lock(
    factory: BackendFixtureFactory, phase: str
) -> None:
    # Catches close-under-write, lost pending intent and joins under the short lock.
    async with _case(factory) as case:
        delivery, release = await _t026_pause_runtime(case, phase)
        end_ack = case.recorder.gates["end"].acknowledgement
        if phase == "active":
            end_ack.allow.clear()
        stopping = case.spawn(case.owner.detach())
        await _turn()
        if phase == "active":
            await _await(end_ack.entered.wait())
        assert not stopping.done() and case.recorder.close_calls == 0
        assert not case.recorder.close_during_append
        # attach takes the actual lifecycle lock: BUSY must arrive while I/O waits.
        with pytest.raises(rt.RuntimeRejectedError) as busy:
            await _await(case.owner.attach(case.profile, case.prepare))
        assert busy.value.kind is rt.RuntimeRejectedKind.BUSY
        await _rejected(case, case.request(), "not_active")
        release()
        end_ack.allow.set()
        if phase == "waiting-gate":
            with pytest.raises(monitor.MonitorRejected) as rejected:
                await _await(delivery)
            assert rejected.value.kind == "not_active"
            assert case.recorder.markers() == []
        else:
            report = await _await(delivery)
            assert report.outcome is (
                model.MonitorOutcome.MATCHED
                if phase.startswith("end-")
                else model.MonitorOutcome.DETACHED
            )
            assert report.durability == "complete" and report.ended_record is not None
        terminal = await _await(stopping)
        assert terminal.recorder_close_confirmed and terminal.physical_release_confirmed
        assert case.recorder.close_calls == 1 and not case.recorder.close_during_append
        if phase != "waiting-gate":
            assert case.recorder.trace.index("end.ack") < case.recorder.trace.index(
                "recorder.closed"
            )
        assert case.clock.waiters == {} and case.owner.evidence_read_cleanup_confirmed


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize("committed", [False, True], ids=["before-commit", "lost-ack"])
@pytest.mark.asyncio
async def test_t026_start_failure_releases_owner_without_inventing_end_or_stopping_capture(
    factory: BackendFixtureFactory, committed: bool
) -> None:
    # Catches retries/synthetic ends and a failed start poisoning the next request.
    async with _case(factory) as case:
        before = case.owner.status()
        failures = case.recorder.fail_ack if committed else case.recorder.fail_before
        failures.add("start")
        with pytest.raises(evidence.JournalFailure) as failure:
            await _await(_monitor_entry(case.owner)(case.request()))
        assert failure.value.kind is evidence.JournalFailureKind.IO_FAILURE
        markers = case.recorder.markers()
        assert len(markers) == (1 if committed else 0)
        assert all(
            isinstance(marker, model.OperationStartedEvidence) for marker in markers
        )
        assert sum(_kind(draft) == "start" for draft in case.recorder.submitted) == 1
        assert not any(_kind(draft) == "end" for draft in case.recorder.submitted)
        assert case.owner.status() == before and case.recorder.close_calls == 0
        failures.clear()
        await case.rx(b"ambient after ambiguous start\0\xff")
        next_delivery = await case.begin()
        await case.rx(b"PASS")
        report = await _await(next_delivery)
        assert report.durability == "complete"
        assert len(case.recorder.markers()) == (3 if committed else 2)


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize("site", ["start-ack", "publication", "timer"])
@pytest.mark.parametrize("bad_sample", [True, -1, 99, model.SQLITE_INTEGER_MAX + 1])
@pytest.mark.asyncio
async def test_t026_post_start_clock_fault_leaves_honest_unmatched_start_and_live_capture(
    factory: BackendFixtureFactory,
    site: str,
    bad_sample: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches fabricated decision timestamps/ends or reclassifying acquisition.
    async with _case(factory) as case:
        before = case.owner.status()
        if site == "start-ack":
            delivery, release = await _t026_pause_runtime(case, "start-ack")
        else:
            delivery, release = await _t026_pause_runtime(case, "active")
            await _await(case.clock.wait_started.wait())
        with monkeypatch.context() as patch:
            patch.setattr(case.clock, "now_ns", lambda: bad_sample)
            if site == "start-ack":
                release()
            elif site == "publication":
                await case.rx(b"PASS")
            else:
                case.clock.advance(1_000_000_100)
            with pytest.raises((ValueError, RuntimeError)):
                await _await(delivery)
        markers = case.recorder.markers()
        assert len(markers) == 1 and isinstance(
            markers[0], model.OperationStartedEvidence
        )
        assert not any(_kind(draft) == "end" for draft in case.recorder.submitted)
        assert case.owner.status() == before and case.recorder.close_calls == 0
        assert case.clock.waiters == {} and case.owner.evidence_read_cleanup_confirmed
        while not case.recorder.acks["start"].empty():
            case.recorder.acks["start"].get_nowait()
        next_delivery = await case.begin()
        await case.rx(b"PASS")
        assert (await _await(next_delivery)).durability == "complete"
