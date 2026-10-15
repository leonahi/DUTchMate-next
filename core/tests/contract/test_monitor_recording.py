"""009 T008 RED: prepared capability and positively acknowledged publication.

Provisional internal application seam for T010, not a delivery API:
 MonitorRecordingCoordinator(recorder=..., clock=...): existing recorder port plus
 current_provenance and async start(request, *, run_id, expected_provenance,
 revalidate, charge_markers) -> private operation with async wait()->MonitorReport.
 PreparedMonitorAccess(session_id, policy, coordinator, clock, charge_markers).

Only test-owned append/ack gates and a manual clock are implemented here. The
existing in-memory recorder assigns actual sequences; no coordinator, admission,
matching, runtime lifecycle or composition logic is reproduced in test helpers.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError, dataclass, field, replace
from typing import Any, Protocol, cast
from uuid import UUID

import pytest

from dutchmate_core import evidence, model, monitor
from dutchmate_core import runtime as rt
from dutchmate_core.adapters.sqlite_evidence import charge_monitor_markers
from tests.contract.test_monitor_journal import _provenance
from tests.fakes import BACKEND_FIXTURE_FACTORIES

_ORIGIN = "12345678-1234-1234-1234-123456789abc"
_RUN = "opaque-recording-test-run"
_UNSET = object()
_POLICY = model.SessionPolicy(100, 100000, 10000, 64, 20, 20000)


type ChargeMarkers = Callable[
    [
        evidence.PendingOperationStartedEvidence,
        tuple[evidence.PendingOperationEndedEvidence, ...],
    ],
    tuple[int, int],
]


class OperationPort(Protocol):
    async def wait(self) -> monitor.MonitorReport: ...


class CoordinatorPort(Protocol):
    @property
    def session_id(self) -> model.SessionId: ...

    @property
    def policy(self) -> model.SessionPolicy: ...

    @property
    def clock(self) -> monitor.MonitorClock: ...

    @property
    def current_provenance(self) -> model.SegmentProvenance | None: ...

    async def append(
        self, draft: evidence.PendingEvidenceRecord
    ) -> model.EvidenceRecord: ...

    async def close(self) -> None: ...

    async def start(
        self,
        request: monitor.MonitorRequest,
        *,
        run_id: str,
        expected_provenance: model.SegmentProvenance,
        revalidate: Callable[[], None],
        charge_markers: ChargeMarkers,
    ) -> OperationPort: ...


async def _await[T](work: Awaitable[T]) -> T:
    # A harness watchdog, never a Monitor deadline or delivery timeout.
    async with asyncio.timeout(3):
        return await work


async def _turn() -> None:
    loop = asyncio.get_running_loop()
    reached = loop.create_future()
    loop.call_soon(reached.set_result, None)
    await reached


class ManualClock:
    def __init__(self) -> None:
        self.origin_id = _ORIGIN
        self.value = 100
        self.wait_started = asyncio.Event()
        self.waiters: dict[asyncio.Future[None], int] = {}

    def now_ns(self) -> int:
        return self.value

    async def wait_until(self, deadline_ns: int) -> None:
        self.wait_started.set()
        if self.value >= deadline_ns:
            return
        waiter = asyncio.get_running_loop().create_future()
        self.waiters[waiter] = deadline_ns
        try:
            await waiter
        finally:
            self.waiters.pop(waiter, None)

    def advance(self, value: int) -> None:
        assert self.value <= value <= model.SQLITE_INTEGER_MAX
        self.value = value
        for waiter, deadline in tuple(self.waiters.items()):
            if value >= deadline and not waiter.done():
                waiter.set_result(None)


class Gate:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.allow = asyncio.Event()
        self.allow.set()

    async def enter(self) -> None:
        self.entered.set()
        await self.allow.wait()


@dataclass
class AppendGates:
    commit: Gate = field(default_factory=Gate)
    acknowledgement: Gate = field(default_factory=Gate)


def _kind(draft: evidence.PendingEvidenceRecord) -> str:
    if isinstance(draft, evidence.PendingOperationStartedEvidence):
        return "start"
    if isinstance(draft, evidence.PendingOperationEndedEvidence):
        return "end"
    if isinstance(draft, evidence.PendingSegmentStartedEvidence):
        return "segment"
    return "rx"  # Tests emit only RX for remaining controlled acquisition drafts.


class RecorderProbe:
    """Only the supplied persistence boundary: append, identity/policy and close.

    No read/select/snapshot/subscription API is offered to the coordinator. The
    test alone inspects the finite authoritative in-memory recorder directly.
    """

    def __init__(self, policy: model.SessionPolicy = _POLICY) -> None:
        self.session_id = model.SessionId("recording-session")
        self.policy = policy
        self.journal = evidence.InMemoryEvidenceRecorder()
        self.gates = {kind: AppendGates() for kind in ("segment", "rx", "start", "end")}
        self.submitted: list[evidence.PendingEvidenceRecord] = []
        self.acknowledged: list[model.EvidenceRecord] = []
        self.close_calls = 0
        self.ack_failure: str | None = None

    async def append(
        self, draft: evidence.PendingEvidenceRecord
    ) -> model.EvidenceRecord:
        kind = _kind(draft)
        self.submitted.append(draft)
        gates = self.gates[kind]
        await gates.commit.enter()
        record = await self.journal.append(draft)
        await gates.acknowledgement.enter()
        if self.ack_failure == kind:
            raise evidence.JournalFailure(
                evidence.JournalOperation.APPEND, evidence.JournalFailureKind.IO_FAILURE
            )
        self.acknowledged.append(record)
        return record

    async def close(self) -> None:
        self.close_calls += 1

    def release(self) -> None:
        for gates in self.gates.values():
            gates.commit.allow.set()
            gates.acknowledgement.allow.set()


class ChargeProbe:
    def __init__(self) -> None:
        self.calls: list[
            tuple[
                evidence.PendingOperationStartedEvidence,
                tuple[evidence.PendingOperationEndedEvidence, ...],
            ]
        ] = []
        self.override: object = _UNSET

    def __call__(
        self,
        start: evidence.PendingOperationStartedEvidence,
        ends: tuple[evidence.PendingOperationEndedEvidence, ...],
    ) -> tuple[int, int]:
        self.calls.append((start, ends))
        if self.override is not _UNSET:
            return cast(tuple[int, int], self.override)
        return charge_monitor_markers(start, ends)


def _required(name: str) -> Any:
    value = getattr(monitor, name, None)
    assert callable(value), f"T010 missing: monitor.{name}"
    return value


def _coordinator(recorder: RecorderProbe, clock: ManualClock) -> CoordinatorPort:
    factory = _required("MonitorRecordingCoordinator")
    return cast(CoordinatorPort, factory(recorder=recorder, clock=clock))


@dataclass
class Case:
    recorder: RecorderProbe
    clock: ManualClock
    coordinator: CoordinatorPort
    provenance: model.SegmentProvenance
    charge: ChargeProbe = field(default_factory=ChargeProbe)
    tasks: list[asyncio.Task[Any]] = field(default_factory=list)

    def spawn[T](self, work: Awaitable[T]) -> asyncio.Task[T]:
        async def run() -> T:
            return await work

        task = asyncio.create_task(run())
        self.tasks.append(task)
        return task

    async def start(
        self,
        request: monitor.MonitorRequest | None = None,
        *,
        revalidate: Callable[[], None] = lambda: None,
    ) -> OperationPort:
        if request is None:
            request = monitor.MonitorRequest(
                self.recorder.session_id, b"\0\xffA", 1000, 1024
            )
        return await self.coordinator.start(
            request,
            run_id=_RUN,
            expected_provenance=self.provenance,
            revalidate=revalidate,
            charge_markers=self.charge,
        )

    async def rx(self, payload: bytes) -> model.EvidenceRecord:
        return await self.coordinator.append(
            evidence.PendingRxBytesEvidence(
                self.provenance.connection_id,
                self.provenance.segment_id,
                payload,
                model.BackendObservationTimestamp(
                    self.provenance.backend_observation_timestamp_domain.domain_id, 123
                ),
            )
        )


@asynccontextmanager
async def _case(
    index: int = 0, *, policy: model.SessionPolicy = _POLICY
) -> AsyncIterator[Case]:
    recorder, clock = RecorderProbe(policy), ManualClock()
    coordinator = _coordinator(recorder, clock)
    case = Case(recorder, clock, coordinator, _provenance(index))
    try:
        await _await(
            coordinator.append(evidence.PendingSegmentStartedEvidence(case.provenance))
        )
        yield case
    finally:
        recorder.release()
        clock.advance(model.SQLITE_INTEGER_MAX)
        await _await(asyncio.gather(*case.tasks, return_exceptions=True))
        await _await(coordinator.close())


def _markers(
    recorder: RecorderProbe,
) -> list[model.OperationStartedEvidence | model.OperationEndedEvidence]:
    return [
        r
        for r in recorder.journal.snapshot()
        if isinstance(r, (model.OperationStartedEvidence, model.OperationEndedEvidence))
    ]


@pytest.mark.parametrize("positional_read_access", [False, True])
@pytest.mark.asyncio
async def test_t008_old_preparation_constructors_default_to_absent_monitor_access(
    positional_read_access: bool,
) -> None:
    recorder = RecorderProbe()
    backend = BACKEND_FIXTURE_FACTORIES[0]().backend
    prepared = (
        rt.PreparedObservationRun(recorder, backend, None)
        if positional_read_access
        else rt.PreparedObservationRun(recorder, backend)
    )
    assert getattr(prepared, "monitor_access", object()) is None, (
        "T010 missing: optional PreparedObservationRun.monitor_access=None"
    )
    assert prepared.recorder is recorder and prepared.backend is backend


@pytest.mark.asyncio
async def test_t008_prepared_capability_is_immutable_and_identifies_the_same_coordinator_clock_and_callback() -> (
    None
):
    factory = _required("PreparedMonitorAccess")
    async with _case() as case:
        access = factory(
            session_id=case.recorder.session_id,
            policy=case.recorder.policy,
            coordinator=case.coordinator,
            clock=case.clock,
            charge_markers=case.charge,
        )
        assert access.session_id == case.coordinator.session_id
        assert access.policy == case.coordinator.policy
        assert access.coordinator is case.coordinator and access.clock is case.clock
        assert access.charge_markers is case.charge
        with pytest.raises(FrozenInstanceError):
            access.clock = ManualClock()
        constructor: Any = rt.PreparedObservationRun
        backend = BACKEND_FIXTURE_FACTORIES[0]().backend
        prepared = constructor(
            recorder=case.coordinator, backend=backend, monitor_access=access
        )
        assert prepared.recorder is access.coordinator
        assert prepared.monitor_access is access


@pytest.mark.parametrize(
    "bad_field", ["session_id", "policy", "clock", "charge_markers"]
)
@pytest.mark.asyncio
async def test_t008_prepared_capability_rejects_mismatched_identity_or_unusable_callback(
    bad_field: str,
) -> None:
    factory = _required("PreparedMonitorAccess")
    async with _case() as case:
        values: dict[str, object] = dict(
            session_id=case.recorder.session_id,
            policy=case.recorder.policy,
            coordinator=case.coordinator,
            clock=case.clock,
            charge_markers=case.charge,
        )
        values[bad_field] = {
            "session_id": model.SessionId("other"),
            "policy": replace(_POLICY, max_retained_records=101),
            "clock": ManualClock(),
            "charge_markers": None,
        }[bad_field]
        with pytest.raises((TypeError, ValueError)):
            factory(**values)


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t008_segment_provenance_is_published_only_at_positive_ack_and_append_returns_authoritative_record(
    index: int,
) -> None:
    recorder, clock = RecorderProbe(), ManualClock()
    coordinator = _coordinator(recorder, clock)
    gates = recorder.gates["segment"]
    gates.acknowledgement.allow.clear()
    provenance = _provenance(index)
    task = asyncio.create_task(
        coordinator.append(evidence.PendingSegmentStartedEvidence(provenance))
    )
    try:
        await _await(gates.acknowledgement.entered.wait())
        assert len(recorder.journal.snapshot()) == 1  # Committed, not acknowledged.
        assert coordinator.current_provenance is None
        gates.acknowledgement.allow.set()
        accepted = await _await(task)
        assert accepted is recorder.acknowledged[0]
        assert coordinator.current_provenance == provenance  # No queued publisher turn.
    finally:
        recorder.release()
        await _await(asyncio.gather(task, return_exceptions=True))
        await _await(coordinator.close())
    assert recorder.close_calls == 1


@pytest.mark.asyncio
async def test_t008_failed_segment_ack_does_not_publish_a_provenance_fact() -> None:
    recorder, clock = RecorderProbe(), ManualClock()
    recorder.ack_failure = "segment"
    coordinator = _coordinator(recorder, clock)
    try:
        with pytest.raises(evidence.JournalFailure):
            await coordinator.append(
                evidence.PendingSegmentStartedEvidence(_provenance(0))
            )
        assert coordinator.current_provenance is None
        assert len(recorder.journal.snapshot()) == 1  # Ambiguous commit is not erased.
    finally:
        await _await(coordinator.close())


@pytest.mark.asyncio
async def test_t008_preflight_receives_actual_start_and_nine_legal_maximum_end_drafts_before_submission() -> (
    None
):
    async with _case() as case:
        case.recorder.gates["start"].commit.allow.clear()
        starting = case.spawn(case.start())
        await _await(case.recorder.gates["start"].commit.entered.wait())
        assert case.charge.calls
        start, ends = case.charge.calls[-1]
        assert start.provenance == case.provenance
        assert start.condition == b"\0\xffA" and start.clock_origin_id == _ORIGIN
        assert len(ends) == 9 and {d.outcome for d in ends} == set(model.MonitorOutcome)
        assert all(d.operation_id == start.operation_id for d in ends)
        assert all(d.clock.origin_id == _ORIGIN for d in ends)
        assert all(d.examined_rx_bytes == 1048576 for d in ends)
        assert all(
            (d.match is not None) == (d.outcome is model.MonitorOutcome.MATCHED)
            for d in ends
        )
        assert all(d.observer_loss_records == model.SQLITE_INTEGER_MAX for d in ends)
        assert _markers(case.recorder) == []
        case.recorder.gates["start"].commit.allow.set()
        operation = await _await(starting)
        await case.rx(b"\0\xffA")
        assert (await _await(operation.wait())).outcome is model.MonitorOutcome.MATCHED


@pytest.mark.parametrize(
    "bad",
    [
        None,
        (None, 1),
        (1, None),
        (True, 1),
        (1, False),
        (0, 1),
        (1, 0),
        (-1, 1),
        (model.SQLITE_INTEGER_MAX + 1, 1),
        (1, model.SQLITE_INTEGER_MAX + 1),
        (1.0, 1),
        (1, 1.0),
        ("1", 1),
        [1, 1],
        (1,),
        (1, 1, 1),
    ],
)
@pytest.mark.asyncio
async def test_t008_charge_callback_requires_an_exact_positive_signed64_pair_before_start(
    bad: object,
) -> None:
    async with _case() as case:
        case.charge.override = bad
        with pytest.raises(monitor.MonitorRejected) as caught:
            await case.start()
        assert caught.value.kind == "monitor_unavailable"
        assert _markers(case.recorder) == []
        assert not any(
            isinstance(d, evidence.PendingOperationStartedEvidence)
            for d in case.recorder.submitted
        )


@pytest.mark.asyncio
async def test_t008_charge_callback_result_is_synchronous_not_an_awaitable() -> None:
    async with _case() as case:
        result = asyncio.get_running_loop().create_future()
        result.set_result((1, 1))
        case.charge.override = result
        with pytest.raises(monitor.MonitorRejected) as caught:
            await case.start()
        assert (
            caught.value.kind == "monitor_unavailable" and _markers(case.recorder) == []
        )


@pytest.mark.parametrize(
    "charges", [(model.SQLITE_INTEGER_MAX, 1), (1, model.SQLITE_INTEGER_MAX)]
)
@pytest.mark.asyncio
async def test_t008_maximum_exact_charge_is_legal_when_each_policy_ceiling_fits(
    charges: tuple[int, int],
) -> None:
    maximum = model.SQLITE_INTEGER_MAX
    policy = model.SessionPolicy(100, maximum, maximum, 64, 20, maximum)
    async with _case(policy=policy) as case:
        case.charge.override = charges
        operation = await _await(case.start())
        await case.rx(b"\0\xffA")
        assert (await _await(operation.wait())).durability == "complete"


@pytest.mark.parametrize("charges", [(10000, 10000), (10001, 1), (1, 10001)])
@pytest.mark.asyncio
async def test_t008_policy_preflight_accepts_equality_and_rejects_either_marker_one_over(
    charges: tuple[int, int],
) -> None:
    async with _case() as case:
        case.charge.override = charges
        if max(charges) > 10000:
            with pytest.raises(monitor.MonitorRejected) as caught:
                await case.start()
            assert caught.value.kind == "evidence_policy_incompatible"
            assert _markers(case.recorder) == []
        else:
            operation = await _await(case.start())
            await case.rx(b"\0\xffA")
            assert (
                await _await(operation.wait())
            ).outcome is model.MonitorOutcome.MATCHED


@pytest.mark.parametrize("change", ["sealed", "segment", "charge"])
@pytest.mark.asyncio
async def test_t008_waiting_start_revalidates_seal_current_provenance_and_policy_inside_recording_gate(
    change: str,
) -> None:
    async with _case() as case:
        ack = case.recorder.gates["rx"].acknowledgement
        ack.allow.clear()
        raw = case.spawn(case.rx(b"ambient"))
        await _await(ack.entered.wait())
        sealed = False

        def revalidate() -> None:
            if sealed:
                raise monitor.MonitorRejected("not_active")

        transition: asyncio.Task[model.EvidenceRecord] | None = None
        if change == "segment":
            changed = replace(
                case.provenance, segment_id=model.SegmentId("new-segment")
            )
            transition = case.spawn(
                case.coordinator.append(evidence.PendingSegmentStartedEvidence(changed))
            )
        starting = case.spawn(case.start(revalidate=revalidate))
        await _turn()
        assert not any(
            isinstance(d, evidence.PendingOperationStartedEvidence)
            for d in case.recorder.submitted
        )
        if change == "sealed":
            sealed = True
        elif change == "charge":
            case.charge.override = (10001, 1)
        ack.allow.set()
        await _await(raw)
        if transition is not None:
            await _await(transition)
        with pytest.raises(monitor.MonitorRejected) as caught:
            await _await(starting)
        assert (
            caught.value.kind
            == {
                "sealed": "not_active",
                "segment": "monitor_unavailable",
                "charge": "evidence_policy_incompatible",
            }[change]
        )
        assert _markers(case.recorder) == []


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t008_start_ack_atomically_installs_boundary_matcher_and_host_deadline_before_queued_rx(
    index: int,
) -> None:
    async with _case(index) as case:
        ack = case.recorder.gates["start"].acknowledgement
        ack.allow.clear()
        starting = case.spawn(case.start())
        await _await(ack.entered.wait())
        marker = case.recorder.journal.snapshot()[-1]
        assert isinstance(marker, model.OperationStartedEvidence)
        assert not any(
            isinstance(r, model.OperationStartedEvidence)
            for r in case.recorder.acknowledged
        )
        queued_rx = case.spawn(case.rx(b"\0\xffATRAIL"))
        await _turn()
        assert not any(
            isinstance(d, evidence.PendingRxBytesEvidence)
            for d in case.recorder.submitted
        )
        case.clock.advance(10000)
        ack.allow.set()
        operation = await _await(starting)
        rx = await _await(queued_rx)
        report = await _await(operation.wait())
        assert report.outcome is model.MonitorOutcome.MATCHED
        assert report.started_record.sequence == 1 and rx.sequence == 2
        assert report.window == model.SequenceRange(2, 3)
        assert report.clock == model.MonitorClockFacts(
            _ORIGIN, 10000, 1_000_010_000, 10000
        )
        assert report.match == model.MonitorMatch(
            model.MonitorMatchStart(2, 0), model.MonitorMatchEnd(2, 3)
        )
        assert report.examined_rx_bytes == 3


@pytest.mark.asyncio
async def test_t008_committed_but_unacknowledged_rx_cannot_match_before_timeout_publication() -> (
    None
):
    async with _case() as case:
        operation = await _await(case.start())
        await _await(case.clock.wait_started.wait())
        ack = case.recorder.gates["rx"].acknowledgement
        ack.allow.clear()
        rx = case.spawn(case.rx(b"\0\xffA"))
        await _await(ack.entered.wait())
        waiter = case.spawn(operation.wait())
        case.clock.advance(1_000_000_100)
        await _turn()
        assert not waiter.done()  # End append cannot overtake submitted RX settlement.
        ack.allow.set()
        await _await(rx)
        report = await _await(waiter)
        assert report.outcome is model.MonitorOutcome.TIMEOUT and report.match is None
        assert report.window == model.SequenceRange(2, 2)
        assert report.examined_rx_bytes == 0
        assert case.recorder.journal.snapshot()[2].sequence == 2


@pytest.mark.asyncio
async def test_t008_matching_bytes_before_start_do_not_satisfy_the_new_operation() -> (
    None
):
    async with _case() as case:
        await case.rx(b"\0\xffA")
        operation = await _await(case.start())
        await _await(case.clock.wait_started.wait())
        case.clock.advance(1_000_000_100)
        report = await _await(operation.wait())
        assert report.outcome is model.MonitorOutcome.TIMEOUT
        assert report.started_record.sequence == 2
        assert report.window == model.SequenceRange(3, 3)
        assert report.examined_rx_bytes == 0 and report.match is None


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t008_chunk_spanning_publication_keeps_whole_rx_without_any_read_queue_or_window_retrieval(
    index: int,
) -> None:
    async with _case(index) as case:
        operation = await _await(case.start())
        first_payload, last_payload = b"x\0", b"\xffATRAIL"
        first = await case.rx(first_payload)
        last = await case.rx(last_payload)
        report = await _await(operation.wait())
        assert report.outcome is model.MonitorOutcome.MATCHED
        assert report.provenance == case.provenance
        assert report.window == model.SequenceRange(2, 4)
        assert report.match == model.MonitorMatch(
            model.MonitorMatchStart(2, 1), model.MonitorMatchEnd(3, 2)
        )
        assert report.examined_rx_bytes == 4
        assert (
            isinstance(first, model.RxBytesEvidence) and first.payload is first_payload
        )
        assert isinstance(last, model.RxBytesEvidence) and last.payload is last_payload
        assert case.recorder.journal.snapshot()[2:4] == (first, last)
        assert case.clock.waiters == {}  # An early match joins its internal timer.


@pytest.mark.asyncio
async def test_t008_delayed_end_ack_and_later_ambient_bytes_cannot_extend_frozen_decision_watermark() -> (
    None
):
    async with _case() as case:
        operation = await _await(case.start())
        end_ack = case.recorder.gates["end"].acknowledgement
        end_ack.allow.clear()
        case.clock.advance(200)
        await case.rx(b"\0\xffATRAIL")
        await _await(end_ack.entered.wait())
        ending = case.recorder.journal.snapshot()[-1]
        assert isinstance(ending, model.OperationEndedEvidence)
        assert (
            ending.window == model.SequenceRange(2, 3)
            and ending.clock.decided_at_ns == 200
        )
        waiter = case.spawn(operation.wait())
        ambient = case.spawn(case.rx(b"ambient after decision"))
        case.clock.advance(5_000_000_000)
        await _turn()
        assert not waiter.done()
        end_ack.allow.set()
        report = await _await(waiter)
        later = await _await(ambient)
        assert later.sequence > report.window.end_exclusive
        assert report.outcome is model.MonitorOutcome.MATCHED
        assert report.window == ending.window and report.clock == ending.clock
        assert report.examined_rx_bytes == 3


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t008_normal_report_refs_identify_actual_positive_start_and_end_acknowledgements(
    index: int,
) -> None:
    async with _case(index) as case:
        operation = await _await(case.start())
        await case.rx(b"\0\xffA")
        report = await _await(operation.wait())
        markers = _markers(case.recorder)
        assert len(markers) == 2
        start, end = markers
        assert isinstance(start, model.OperationStartedEvidence) and isinstance(
            end, model.OperationEndedEvidence
        )
        assert report.run_id == _RUN and report.session_id == case.recorder.session_id
        assert (
            report.operation_id
            == str(UUID(report.operation_id))
            == start.operation_id
            == end.operation_id
        )
        assert report.provenance == start.provenance == case.provenance
        assert report.started_record == model.EvidenceReference(
            case.recorder.session_id, start.sequence
        )
        assert report.ended_record == model.EvidenceReference(
            case.recorder.session_id, end.sequence
        )
        assert start in case.recorder.acknowledged and end in case.recorder.acknowledged
        assert end.start_sequence == start.sequence
        assert report.window == end.window and report.clock == end.clock
        assert report.match == end.match and report.outcome is end.outcome
        assert report.examined_rx_bytes == end.examined_rx_bytes
        assert report.durability == "complete" and report.end_failure is None


@pytest.mark.asyncio
async def test_t008_unconfirmed_start_ack_returns_no_operation_or_positive_reference() -> (
    None
):
    async with _case() as case:
        case.recorder.ack_failure = "start"
        with pytest.raises(evidence.JournalFailure) as caught:
            await case.start()
        assert caught.value.operation is evidence.JournalOperation.APPEND
        assert caught.value.kind is evidence.JournalFailureKind.IO_FAILURE
        markers = _markers(case.recorder)
        assert len(markers) == 1 and isinstance(
            markers[0], model.OperationStartedEvidence
        )
        assert markers[0] not in case.recorder.acknowledged
        assert case.clock.waiters == {}
        assert not any(
            isinstance(d, evidence.PendingOperationEndedEvidence)
            for d in case.recorder.submitted
        )


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("delta", [-1, 0, 1], ids=["before", "at", "after"])
@pytest.mark.asyncio
async def test_t018_publication_sample_wins_even_when_deadline_timer_is_late(
    index: int, delta: int
) -> None:
    async with _case(index) as case:
        operation = await _await(case.start())
        await _await(case.clock.wait_started.wait())
        # Move the infrastructure sample without waking its timer. The real
        # publication path must enforce the deadline independently of scheduling.
        case.clock.value = 1_000_000_100 + delta
        raw = await case.rx(b"\0\xffATRAIL")
        report = await _await(operation.wait())
        assert report.outcome is (
            model.MonitorOutcome.MATCHED if delta < 0 else model.MonitorOutcome.TIMEOUT
        )
        assert report.clock.decided_at_ns == 1_000_000_100 + delta
        assert report.window == model.SequenceRange(2, 3 if delta < 0 else 2)
        assert report.examined_rx_bytes == (3 if delta < 0 else 0)
        assert (report.match is not None) is (delta < 0)
        assert isinstance(raw, model.RxBytesEvidence) and raw.payload == b"\0\xffATRAIL"
        assert raw in case.recorder.journal.snapshot()
        assert case.clock.waiters == {}


@pytest.mark.asyncio
async def test_t018_eligible_chunk_uses_one_sample_when_processing_crosses_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _case() as case:
        operation = await _await(case.start())
        await _await(case.clock.wait_started.wait())
        original = monitor.LiteralMonitorMatcher.feed

        def feed(
            matcher: monitor.LiteralMonitorMatcher, sequence: int, payload: bytes
        ) -> model.MonitorOutcome | None:
            case.clock.value = 1_000_000_101  # Simulated CPU time inside one chunk.
            return original(matcher, sequence, payload)

        monkeypatch.setattr(monitor.LiteralMonitorMatcher, "feed", feed)
        case.clock.value = 1_000_000_099
        await case.rx(b"noise\0\xffATRAIL")
        report = await _await(operation.wait())
        assert report.outcome is model.MonitorOutcome.MATCHED
        assert report.clock.decided_at_ns == 1_000_000_099
        assert report.examined_rx_bytes == 8
        assert report.window == model.SequenceRange(2, 3)


@pytest.mark.parametrize("lost_bytes", [None, 1, 7])
@pytest.mark.asyncio
async def test_t018_observed_loss_counts_records_resets_prefix_and_preserves_budget(
    lost_bytes: int | None,
) -> None:
    # Only the existing fixture that reports observer loss supplies loss evidence.
    async with _case(1) as case:
        operation = await _await(case.start())
        await case.rx(b"\0\xff")
        provenance = case.provenance
        loss = await case.coordinator.append(
            evidence.PendingObserverLossEvidence(
                provenance.connection_id,
                provenance.segment_id,
                "fixture-device-uart-observer",
                "fixture-uart-rx-buffer",
                model.ObserverLossCause.OVERFLOW,
                lost_bytes,
                model.BackendObservationTimestamp(
                    provenance.backend_observation_timestamp_domain.domain_id, 9
                ),
            )
        )
        await case.rx(b"A")  # Cannot complete the prefix preceding the loss.
        await case.rx(b"\0\xffATRAIL")
        report = await _await(operation.wait())
        assert report.examined_rx_bytes == 6 and report.observer_loss_records == 1
        assert report.match == model.MonitorMatch(
            model.MonitorMatchStart(5, 0), model.MonitorMatchEnd(5, 3)
        )
        assert report.window == model.SequenceRange(2, 6)
        assert loss in case.recorder.journal.snapshot()


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("reason", list(model.SegmentEndReason))
@pytest.mark.asyncio
async def test_t018_every_committed_segment_end_includes_boundary_and_never_spans_prefix(
    index: int, reason: model.SegmentEndReason
) -> None:
    async with _case(index) as case:
        operation = await _await(case.start())
        await case.rx(b"\0\xff")
        boundary = await case.coordinator.append(
            evidence.PendingSegmentEndedEvidence(
                case.provenance.connection_id, case.provenance.segment_id, reason
            )
        )
        report = await _await(operation.wait())
        expected = (
            model.MonitorOutcome.DETACHED
            if reason is model.SegmentEndReason.EXPLICIT_STOP
            else model.MonitorOutcome(reason.value)
        )
        assert report.outcome is expected and report.match is None
        assert report.examined_rx_bytes == 2 and report.window == model.SequenceRange(
            2, 4
        )
        assert (
            report.provenance == case.provenance and report.observer_loss_records == 0
        )
        assert boundary.sequence == 3 and case.coordinator.current_provenance is None


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t018_unexpected_new_segment_terminates_without_replacing_captured_origin(
    index: int,
) -> None:
    async with _case(index) as case:
        operation = await _await(case.start())
        await case.rx(b"\0\xff")
        changed = replace(
            case.provenance,
            segment_id=model.SegmentId("next"),
            backend_observation_timestamp_domain=replace(
                case.provenance.backend_observation_timestamp_domain,
                domain_id="next-domain",
                origin_id="next-origin",
            ),
        )
        boundary = await case.coordinator.append(
            evidence.PendingSegmentStartedEvidence(changed)
        )
        report = await _await(operation.wait())
        assert report.outcome is model.MonitorOutcome.TIMESTAMP_ORIGIN_RESET
        assert report.match is None and report.provenance == case.provenance
        assert case.coordinator.current_provenance == changed and boundary.sequence == 3
        assert (
            report.window == model.SequenceRange(2, 4) and report.examined_rx_bytes == 2
        )
        assert report.clock.origin_id == _ORIGIN


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("committed", [False, True], ids=["before-commit", "lost-ack"])
@pytest.mark.parametrize(
    "failure_code",
    [kind.value for kind in evidence.JournalFailureKind] + ["unexpected"],
)
@pytest.mark.asyncio
async def test_t026_end_failure_settles_once_after_waiter_loss_with_frozen_facts(
    index: int,
    committed: bool,
    failure_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches retrying ambiguous ends, overwriting first facts or losing the owner.
    async with _case(index) as case:
        original_append = case.recorder.append
        entered, release = asyncio.Event(), asyncio.Event()
        attempts: list[evidence.PendingOperationEndedEvidence] = []

        async def append(
            draft: evidence.PendingEvidenceRecord,
        ) -> model.EvidenceRecord:
            if not isinstance(draft, evidence.PendingOperationEndedEvidence):
                return await original_append(draft)
            attempts.append(draft)
            if committed:
                await original_append(draft)
            entered.set()
            await release.wait()
            if failure_code == "unexpected":
                raise OSError("private end failure")
            raise evidence.JournalFailure(
                evidence.JournalOperation.APPEND,
                evidence.JournalFailureKind(failure_code),
                "private end failure",
            )

        monkeypatch.setattr(case.recorder, "append", append)
        try:
            operation = await _await(case.start())
            abandoned = case.spawn(operation.wait())
            await _turn()
            abandoned.cancel()
            with pytest.raises(asyncio.CancelledError):
                await _await(abandoned)
            case.clock.advance(200)
            await case.rx(b"\0\xffA trailing")
            await _await(entered.wait())
            surviving = case.spawn(operation.wait())
            await _turn()
            assert not surviving.done() and case.recorder.close_calls == 0
            assert len(attempts) == 1
            case.clock.advance(5_000_000_000)
            release.set()
            report = await _await(surviving)
            assert report.outcome is model.MonitorOutcome.MATCHED
            assert report.window == model.SequenceRange(2, 3)
            assert report.examined_rx_bytes == 3 and report.observer_loss_records == 0
            assert report.match == model.MonitorMatch(
                model.MonitorMatchStart(2, 0), model.MonitorMatchEnd(2, 3)
            )
            assert report.clock == model.MonitorClockFacts(
                _ORIGIN, 100, 1_000_000_100, 200
            )
            assert (
                report.durability == "end_unconfirmed" and report.ended_record is None
            )
            assert report.end_failure == monitor.MonitorEndFailure(
                "service" if failure_code == "unexpected" else "journal",
                "internal_failure" if failure_code == "unexpected" else failure_code,
            )
            markers = _markers(case.recorder)
            assert len(markers) == (2 if committed else 1)
            assert isinstance(markers[0], model.OperationStartedEvidence)
            if committed:
                assert isinstance(markers[1], model.OperationEndedEvidence)
                assert markers[1].clock.decided_at_ns == 200
            assert len(attempts) == 1 and case.clock.waiters == {}
            later = await case.rx(b"ambient after unconfirmed end\0\xff")
            assert later.sequence >= report.window.end_exclusive
        finally:
            release.set()
