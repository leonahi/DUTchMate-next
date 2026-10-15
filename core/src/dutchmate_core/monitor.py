"""Receive-only Monitor values, bounded matching and committed publication."""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, field
from typing import Final, Literal, Protocol
from uuid import uuid4

from dutchmate_core.evidence import (
    EvidenceRecorder,
    JournalFailure,
    JournalFailureKind,
    PendingEvidenceRecord,
    PendingOperationEndedEvidence,
    PendingOperationStartedEvidence,
    maximum_monitor_end_drafts,
    monitor_marker_charges_fit,
)
from dutchmate_core.model import (
    SQLITE_INTEGER_MAX,
    EvidenceRecord,
    EvidenceReference,
    MonitorClockFacts,
    MonitorMatch,
    MonitorMatchEnd,
    MonitorMatchStart,
    MonitorOutcome,
    ObserverLossEvidence,
    OperationEndedEvidence,
    OperationStartedEvidence,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentEndReason,
    SegmentProvenance,
    SegmentStartedEvidence,
    SequenceRange,
    SessionId,
    SessionPolicy,
    validate_monitor_bounds,
    validate_monitor_decision,
    validate_monitor_uuid,
    validate_record_sequence,
)


class MonitorClock(Protocol):
    @property
    def origin_id(self) -> str: ...

    def now_ns(self) -> int: ...

    async def wait_until(self, deadline_ns: int) -> None: ...


@dataclass(frozen=True, slots=True)
class MonitorRequest:
    session_id: SessionId
    condition: bytes
    timeout_ms: int
    max_rx_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, SessionId):
            raise TypeError("Monitor requires a session ID")
        validate_monitor_bounds(self.condition, self.timeout_ms, self.max_rx_bytes)


type MonitorRejectedKind = Literal[
    "no_associated_session",
    "session_not_associated",
    "not_active",
    "monitor_unavailable",
    "capability_unavailable",
    "busy",
    "evidence_policy_incompatible",
]
_REJECTION_KINDS = frozenset(
    {
        "no_associated_session",
        "session_not_associated",
        "not_active",
        "monitor_unavailable",
        "capability_unavailable",
        "busy",
        "evidence_policy_incompatible",
    }
)


@dataclass(slots=True, unsafe_hash=True)
class MonitorRejected(RuntimeError):
    """Sealed rejection facts with ordinary exception transport metadata."""

    kind: Final[MonitorRejectedKind] = field()

    def __setattr__(self, name: str, value: object) -> None:
        if name == "kind" and hasattr(self, name):
            raise FrozenInstanceError("cannot assign to field 'kind'")
        RuntimeError.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name == "kind":
            raise FrozenInstanceError("cannot delete field 'kind'")
        RuntimeError.__delattr__(self, name)

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in _REJECTION_KINDS:
            raise TypeError("Monitor rejection kind must be declared")
        RuntimeError.__init__(self, self.kind)


type MonitorFailureSource = Literal["journal", "service"]


@dataclass(frozen=True, slots=True)
class MonitorEndFailure:
    source: MonitorFailureSource
    code: str

    def __post_init__(self) -> None:
        if type(self.source) is not str or type(self.code) is not str:
            raise TypeError("end failure must be normalized text")
        if self.source == "journal" and self.code in {
            k.value for k in JournalFailureKind
        }:
            return
        if self.source == "service" and self.code == "internal_failure":
            return
        raise ValueError("end failure must be a declared journal or internal failure")


@dataclass(frozen=True, slots=True)
class MonitorReport:
    run_id: str
    session_id: SessionId
    operation_id: str
    provenance: SegmentProvenance
    outcome: MonitorOutcome
    started_record: EvidenceReference
    ended_record: EvidenceReference | None
    window: SequenceRange
    examined_rx_bytes: int
    observer_loss_records: int
    match: MonitorMatch | None
    clock: MonitorClockFacts
    durability: Literal["complete", "end_unconfirmed"]
    end_failure: MonitorEndFailure | None

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or not self.run_id:
            raise ValueError("Monitor report requires an opaque run identity")
        if not isinstance(self.session_id, SessionId):
            raise TypeError("Monitor report requires a session ID")
        validate_monitor_uuid(self.operation_id)
        if not isinstance(self.provenance, SegmentProvenance):
            raise TypeError("Monitor report requires actual segment provenance")
        if not isinstance(self.started_record, EvidenceReference):
            raise TypeError("Monitor report requires an acknowledged start reference")
        validate_record_sequence(self.started_record.sequence)
        if self.started_record.session_id != self.session_id:
            raise ValueError("start reference must belong to the captured session")
        validate_monitor_decision(
            self.started_record.sequence,
            self.window,
            self.outcome,
            self.examined_rx_bytes,
            self.observer_loss_records,
            self.match,
            self.clock,
        )
        if type(self.durability) is not str:
            raise TypeError("durability must be declared")
        if self.durability == "complete":
            if (
                not isinstance(self.ended_record, EvidenceReference)
                or self.end_failure is not None
            ):
                raise ValueError("complete durability requires an end reference only")
            validate_record_sequence(self.ended_record.sequence)
            if (
                self.ended_record.session_id != self.session_id
                or self.ended_record.sequence < self.window.end_exclusive
            ):
                raise ValueError(
                    "end reference must follow the window in the same session"
                )
        elif self.durability == "end_unconfirmed":
            if self.ended_record is not None or not isinstance(
                self.end_failure, MonitorEndFailure
            ):
                raise ValueError("unconfirmed end requires a normalized failure only")
        else:
            raise ValueError("durability must be declared")


class LiteralMonitorMatcher:
    """Linear KMP matching with bounded original-byte positions; no RX history."""

    def __init__(self, condition: bytes, max_rx_bytes: int) -> None:
        validate_monitor_bounds(condition, 1, max_rx_bytes)
        self._condition = condition
        self._limit = max_rx_bytes
        prefix = [0] * len(condition)
        length = 0
        for index in range(1, len(condition)):
            while length and condition[index] != condition[length]:
                length = prefix[length - 1]
            if condition[index] == condition[length]:
                length += 1
            prefix[index] = length
        self._prefix = tuple(prefix)
        self._positions: deque[MonitorMatchStart] = deque(maxlen=len(condition))
        self._length = 0
        self.examined_rx_bytes = 0
        self.match: MonitorMatch | None = None
        self._outcome: MonitorOutcome | None = None

    def reset_prefix(self) -> None:
        self._length = 0
        self._positions.clear()

    def feed(self, sequence: int, payload: bytes) -> MonitorOutcome | None:
        validate_record_sequence(sequence)
        if type(payload) is not bytes:
            raise TypeError("matcher payload must be exact bytes")
        if self._outcome is not None:
            return self._outcome
        for offset, byte in enumerate(payload):
            self.examined_rx_bytes += 1
            self._positions.append(MonitorMatchStart(sequence, offset))
            while self._length and byte != self._condition[self._length]:
                self._length = self._prefix[self._length - 1]
            if byte == self._condition[self._length]:
                self._length += 1
            if self._length == len(self._condition):
                self.match = MonitorMatch(
                    self._positions[0], MonitorMatchEnd(sequence, offset + 1)
                )
                self._outcome = MonitorOutcome.MATCHED
            elif self.examined_rx_bytes == self._limit:
                self._outcome = MonitorOutcome.BYTE_LIMIT
            if self._outcome is not None:
                return self._outcome
        return None


type ChargeMonitorMarkers = Callable[
    [PendingOperationStartedEvidence, tuple[PendingOperationEndedEvidence, ...]],
    tuple[int, int],
]


class _MonitorRecorder(EvidenceRecorder, Protocol):
    """The existing recorder's persistence subset, without an outward runtime import."""

    @property
    def session_id(self) -> SessionId: ...

    @property
    def policy(self) -> SessionPolicy: ...

    async def close(self) -> None: ...


class MonitorRecordingCoordinator:
    """Publish acknowledged records under one gate, without reading the journal."""

    def __init__(self, *, recorder: _MonitorRecorder, clock: MonitorClock) -> None:
        self._recorder = recorder
        self._clock = clock
        self._gate = asyncio.Lock()
        self._current_provenance: SegmentProvenance | None = None
        self._operation: _MonitorOperation | None = None
        self._last_now = 0
        self._close_task: asyncio.Task[None] | None = None

    @property
    def session_id(self) -> SessionId:
        return self._recorder.session_id

    @property
    def policy(self) -> SessionPolicy:
        return self._recorder.policy

    @property
    def clock(self) -> MonitorClock:
        return self._clock

    @property
    def current_provenance(self) -> SegmentProvenance | None:
        return self._current_provenance

    def _now(self) -> int:
        now = self.clock.now_ns()
        if type(now) is not int or not self._last_now <= now <= SQLITE_INTEGER_MAX:
            raise ValueError("invalid Monitor clock sample")
        self._last_now = now
        return now

    def preflight(
        self,
        request: MonitorRequest,
        provenance: SegmentProvenance,
        charge_markers: ChargeMonitorMarkers,
        *,
        operation_id: str | None = None,
    ) -> PendingOperationStartedEvidence:
        """Check actual marker charges without submission or quota reservation."""
        try:
            validate_monitor_uuid(self.clock.origin_id)
            if self._now() > SQLITE_INTEGER_MAX - request.timeout_ms * 1000000:
                raise ValueError("Monitor deadline would overflow")
            draft = PendingOperationStartedEvidence(
                operation_id=str(uuid4()) if operation_id is None else operation_id,
                operation_kind="monitor",
                provenance=provenance,
                timeout_ms=request.timeout_ms,
                max_rx_bytes=request.max_rx_bytes,
                clock_origin_id=self.clock.origin_id,
                condition=request.condition,
            )
            charges = charge_markers(
                draft,
                maximum_monitor_end_drafts(draft.operation_id, draft.clock_origin_id),
            )
            fits = monitor_marker_charges_fit(self.policy, charges)
        except Exception:
            raise MonitorRejected("monitor_unavailable") from None
        if not fits:
            raise MonitorRejected("evidence_policy_incompatible")
        return draft

    def _stop(self, outcome: MonitorOutcome) -> None:
        """Latch a decision synchronously; end persistence still waits for the gate."""
        operation = self._operation
        if operation is not None and not operation.decided:
            try:
                now = self._now()
                operation._decide(
                    MonitorOutcome.TIMEOUT if now >= operation._deadline else outcome,
                    now,
                )
            except Exception:
                operation.fail()

    async def append(self, draft: PendingEvidenceRecord) -> EvidenceRecord:
        async with self._gate:
            record = await self._recorder.append(draft)
            # No await between positive ACK, publication and gate release.
            if isinstance(record, SegmentStartedEvidence):
                self._current_provenance = record.provenance
            elif isinstance(record, SegmentEndedEvidence):
                self._current_provenance = None
            operation = self._operation
            if operation is not None and not operation.decided:
                try:
                    operation.publish(record, self._now())
                except Exception:
                    # An operation infrastructure fault must not reclassify capture.
                    operation.fail()
            return record

    async def start(
        self,
        request: MonitorRequest,
        *,
        run_id: str,
        expected_provenance: SegmentProvenance,
        revalidate: Callable[[], None],
        charge_markers: ChargeMonitorMarkers,
        operation_id: str | None = None,
        pending_stop: Callable[[], MonitorOutcome | None] | None = None,
    ) -> _MonitorOperation:
        async with self._gate:
            revalidate()
            if self._close_task is not None or (
                self.current_provenance is None
                or self.current_provenance != expected_provenance
            ):
                raise MonitorRejected("monitor_unavailable")
            if self._operation is not None:
                raise MonitorRejected("busy")
            if request.session_id != self.session_id:
                raise MonitorRejected("session_not_associated")
            draft = self.preflight(
                request, expected_provenance, charge_markers, operation_id=operation_id
            )
            record = await self._recorder.append(draft)
            if not isinstance(record, OperationStartedEvidence):
                raise RuntimeError("invalid Monitor start acknowledgement")
            # This sample and installation are atomic with respect to acquisition.
            started_at = self._now()
            operation = _MonitorOperation(self, record, run_id, started_at)
            self._operation = operation
            intent = None if pending_stop is None else pending_stop()
            if intent is not None:
                self._stop(intent)
            return operation

    async def close(self) -> None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(self._close_task)

    async def _close(self) -> None:
        # The caller has joined acquisition. Join marker settlement before the
        # original journal's authoritative close, without holding the gate.
        operation = self._operation
        if operation is not None:
            await asyncio.gather(operation._owner, return_exceptions=True)
        async with self._gate:
            await self._recorder.close()


class _MonitorOperation:
    """One private installed window; retains bounded matcher state, never RX."""

    def __init__(
        self,
        coordinator: MonitorRecordingCoordinator,
        start: OperationStartedEvidence,
        run_id: str,
        started_at: int,
    ) -> None:
        self._coordinator = coordinator
        self._start = start
        self._run_id = run_id
        self._started_at = started_at
        self._deadline = started_at + start.timeout_ms * 1000000
        if self._deadline > SQLITE_INTEGER_MAX:
            raise ValueError("Monitor deadline overflow after start acknowledgement")
        self._matcher = LiteralMonitorMatcher(start.condition, start.max_rx_bytes)
        self._last_sequence = start.sequence
        self._losses = 0
        self._decision: asyncio.Future[PendingOperationEndedEvidence] = (
            asyncio.get_running_loop().create_future()
        )
        self._timer = asyncio.create_task(self._wait_deadline())
        self._owner = asyncio.create_task(self._settle())
        self._owner.add_done_callback(self._consume_failure)

    @staticmethod
    def _consume_failure(task: asyncio.Task[MonitorReport]) -> None:
        if not task.cancelled():
            task.exception()  # Keep abandoned waiters from leaving unconsumed errors.

    @property
    def decided(self) -> bool:
        return self._decision.done()

    def fail(self) -> None:
        if not self.decided:
            self._decision.set_exception(RuntimeError("Monitor infrastructure failure"))

    def _decide(self, outcome: MonitorOutcome, now: int) -> None:
        if self.decided:
            return
        self._decision.set_result(
            PendingOperationEndedEvidence(
                operation_id=self._start.operation_id,
                operation_kind="monitor",
                start_sequence=self._start.sequence,
                window=SequenceRange(self._start.sequence + 1, self._last_sequence + 1),
                outcome=outcome,
                examined_rx_bytes=self._matcher.examined_rx_bytes,
                observer_loss_records=self._losses,
                match=self._matcher.match
                if outcome is MonitorOutcome.MATCHED
                else None,
                clock=MonitorClockFacts(
                    self._start.clock_origin_id, self._started_at, self._deadline, now
                ),
            )
        )

    def publish(self, record: EvidenceRecord, now: int) -> None:
        if now >= self._deadline:
            self._decide(MonitorOutcome.TIMEOUT, now)
            return
        self._last_sequence = record.sequence
        if isinstance(record, RxBytesEvidence):
            outcome = self._matcher.feed(record.sequence, record.payload)
            if outcome is not None:
                self._decide(outcome, now)
        elif isinstance(record, ObserverLossEvidence):
            self._losses += 1
            self._matcher.reset_prefix()
        elif isinstance(record, SegmentStartedEvidence):
            self._decide(MonitorOutcome.TIMESTAMP_ORIGIN_RESET, now)
        elif isinstance(record, SegmentEndedEvidence):
            outcome = (
                MonitorOutcome.DETACHED
                if record.reason is SegmentEndReason.EXPLICIT_STOP
                else MonitorOutcome(record.reason.value)
            )
            self._decide(outcome, now)

    async def _wait_deadline(self) -> None:
        try:
            while not self.decided:
                await self._coordinator.clock.wait_until(self._deadline)
                now = self._coordinator._now()
                if now >= self._deadline:
                    self._decide(MonitorOutcome.TIMEOUT, now)
        except Exception:
            self.fail()

    async def _settle(self) -> MonitorReport:
        try:
            try:
                draft = await self._decision
            finally:
                self._timer.cancel()
                await asyncio.gather(self._timer, return_exceptions=True)
            ended: EvidenceReference | None = None
            failure: MonitorEndFailure | None = None
            try:
                async with self._coordinator._gate:
                    record = await self._coordinator._recorder.append(draft)
                    if not isinstance(record, OperationEndedEvidence):
                        raise RuntimeError("invalid Monitor end acknowledgement")
                    ended = EvidenceReference(
                        self._coordinator.session_id, record.sequence
                    )
            except JournalFailure as error:
                failure = MonitorEndFailure("journal", error.kind.value)
            except Exception:
                failure = MonitorEndFailure("service", "internal_failure")
            return MonitorReport(
                run_id=self._run_id,
                session_id=self._coordinator.session_id,
                operation_id=self._start.operation_id,
                provenance=self._start.provenance,
                outcome=draft.outcome,
                started_record=EvidenceReference(
                    self._coordinator.session_id, self._start.sequence
                ),
                ended_record=ended,
                window=draft.window,
                examined_rx_bytes=draft.examined_rx_bytes,
                observer_loss_records=draft.observer_loss_records,
                match=draft.match,
                clock=draft.clock,
                durability="complete" if failure is None else "end_unconfirmed",
                end_failure=failure,
            )
        finally:
            self._coordinator._operation = None

    async def wait(self) -> MonitorReport:
        return await asyncio.shield(self._owner)


@dataclass(frozen=True, slots=True)
class PreparedMonitorAccess:
    session_id: SessionId
    policy: SessionPolicy
    coordinator: MonitorRecordingCoordinator
    clock: MonitorClock
    charge_markers: ChargeMonitorMarkers

    def __post_init__(self) -> None:
        if not isinstance(self.coordinator, MonitorRecordingCoordinator):
            raise TypeError("Monitor access requires the committed coordinator")
        if (
            self.session_id != self.coordinator.session_id
            or self.policy != self.coordinator.policy
        ):
            raise ValueError("Monitor access must identify the transferred recorder")
        if self.clock is not self.coordinator.clock or not callable(
            self.charge_markers
        ):
            raise ValueError(
                "Monitor access requires the same clock and a charge callback"
            )
