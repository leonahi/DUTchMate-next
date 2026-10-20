"""Receive-only Monitor values, bounded matching and committed publication."""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import FrozenInstanceError, dataclass, field
from typing import Final, Literal, Protocol, cast
from uuid import uuid4

from dutchmate_core.backend import (
    BackendFailureKind,
    BackendWriteResult,
    BackendWriteStatus,
)
from dutchmate_core.evidence import (
    EvidenceRecorder,
    JournalFailure,
    JournalFailureKind,
    PendingClientAnnotationEvidence,
    PendingEvidenceRecord,
    PendingInteractEndedEvidence,
    PendingInteractStartedEvidence,
    PendingOperationEndedEvidence,
    PendingOperationStartedEvidence,
    PendingUartTxSettledEvidence,
    maximum_monitor_end_drafts,
    monitor_marker_charges_fit,
)
from dutchmate_core.follow import (
    FollowRejected,
    FollowRequest,
    FollowStart,
    _follow_head_request,
    _FollowSubscription,
    _RetrieveFollowPage,
)
from dutchmate_core.interact import (
    InteractAuditFailure,
    InteractReport,
    InteractRequest,
    InteractState,
    _maximum_interact_drafts,
)
from dutchmate_core.model import (
    SQLITE_INTEGER_MAX,
    ClientAnnotationEvidence,
    EvidenceRecord,
    EvidenceReference,
    InteractEndedEvidence,
    InteractOutcome,
    InteractStartedEvidence,
    MonitorClockFacts,
    MonitorMatch,
    MonitorMatchEnd,
    MonitorMatchStart,
    MonitorOutcome,
    ObserverLossEvidence,
    OperationEndedEvidence,
    OperationStartedEvidence,
    RecordedTxAuditFailure,
    RecordedTxFacts,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentEndReason,
    SegmentProvenance,
    SegmentStartedEvidence,
    SequenceRange,
    SessionId,
    SessionPolicy,
    UartTxSettledEvidence,
    validate_monitor_bounds,
    validate_monitor_decision,
    validate_monitor_uuid,
    validate_persisted_counter,
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
    """Publish under one append gate; Follow alone probes live journal metadata."""

    def __init__(self, *, recorder: _MonitorRecorder, clock: MonitorClock) -> None:
        self._recorder = recorder
        self._clock = clock
        self._gate = asyncio.Lock()
        self._current_provenance: SegmentProvenance | None = None
        self._operation: _MonitorOperation | None = None
        self._last_now = 0
        self._close_task: asyncio.Task[None] | None = None
        self._follow: _FollowSubscription | None = None
        self._interact: _InteractOperation | None = None

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
            try:
                record = await self._recorder.append(draft)
                # No await between positive ACK, publication and gate release.
                self._publish(record)
                return record
            finally:
                # A failed ACK may still have committed. Signal possible change,
                # never a claimed record, sequence or observation timestamp.
                self._notify_follow()

    async def append_client_annotation(
        self, client_surface: str, text: str
    ) -> ClientAnnotationEvidence:
        """Sample the host receipt boundary under the ordinary recording gate."""
        async with self._gate:
            draft = PendingClientAnnotationEvidence(
                text=text,
                client_surface=client_surface,
                clock_origin_id=self.clock.origin_id,
                received_at_ns=self._now(),
            )
            try:
                record = await self._recorder.append(draft)
                if not isinstance(record, ClientAnnotationEvidence):
                    raise RuntimeError("invalid annotation acknowledgement")
                self._publish(record)
                return record
            finally:
                self._notify_follow()

    def _notify_follow(self) -> None:
        subscription = self._follow
        if subscription is not None:
            subscription.notify()

    async def start_follow(
        self,
        request: FollowRequest,
        *,
        run_id: str,
        reader: object,
        revalidate: Callable[[], None],
    ) -> _FollowSubscription:
        """Capture actual tail/provenance and register under the append gate."""
        retrieve = getattr(reader, "retrieve", None)
        if (
            not callable(retrieve)
            or getattr(reader, "session_id", None) != self.session_id
            or getattr(reader, "policy", None) != self.policy
        ):
            raise FollowRejected("follow_unavailable")
        query = cast(_RetrieveFollowPage, retrieve)
        async with self._gate:
            revalidate()
            if request.session_id != self.session_id:
                raise FollowRejected("session_not_associated")
            if self._close_task is not None or self.current_provenance is None:
                raise FollowRejected("follow_unavailable")
            if self._follow is not None:
                raise FollowRejected("busy")
            head = await query(_follow_head_request(self.session_id, self.policy))
            revalidate()
            if self._close_task is not None or self.current_provenance is None:
                raise FollowRejected("follow_unavailable")
            start = FollowStart(
                run_id,
                self.session_id,
                head.snapshot_end_exclusive,
                self.current_provenance,
            )

            def unregister() -> None:
                if self._follow is subscription:
                    self._follow = None

            subscription = _FollowSubscription(start, self.policy, query, unregister)
            self._follow = subscription
            return subscription

    def _publish(self, record: EvidenceRecord, *, now: int | None = None) -> None:
        """Publish under the append gate using fresh post-ACK Monitor time."""
        if isinstance(record, SegmentStartedEvidence):
            self._current_provenance = record.provenance
        elif isinstance(record, SegmentEndedEvidence):
            self._current_provenance = None
        operation = self._operation
        interaction = self._interact
        monitor_active = operation is not None and not operation.decided
        interact_active = interaction is not None and interaction.active
        if monitor_active or interact_active:
            try:
                sample = self._now() if now is None else now
            except Exception:
                if monitor_active:
                    assert operation is not None
                    operation.fail()
                if interact_active:
                    assert interaction is not None
                    interaction.fail()
                return
            if monitor_active:
                assert operation is not None
                try:
                    operation.publish(record, sample)
                except Exception:
                    operation.fail()
            if interact_active:
                assert interaction is not None
                interaction.publish(record, sample)

    def preflight_interact(
        self,
        request: InteractRequest,
        provenance: SegmentProvenance,
        charge_markers: ChargeInteractMarkers,
        *,
        operation_id: str | None = None,
    ) -> PendingInteractStartedEvidence:
        try:
            validate_monitor_uuid(self.clock.origin_id)
            if self._now() > SQLITE_INTEGER_MAX - request.timeout_ms * 1000000:
                raise ValueError("Interact deadline would overflow")
            draft = PendingInteractStartedEvidence(
                str(uuid4()) if operation_id is None else operation_id,
                provenance,
                2,
                True,
                request.conditions,
                request.timeout_ms,
                request.max_rx_bytes,
                1000,
                self.clock.origin_id,
                request.payload,
            )
            txs, ends = _maximum_interact_drafts(draft)
            charges = charge_markers(draft, txs, ends)
            if type(charges) is not tuple or len(charges) != 3:
                raise TypeError("Interact requires three marker charges")
            for charge in charges:
                validate_persisted_counter(charge, name="Interact marker charge")
                if charge == 0:
                    raise ValueError("Interact marker charge must be positive")
        except Exception:
            raise InteractRejected("interact_unavailable") from None
        if any(
            charge > ceiling
            for charge in charges
            for ceiling in (
                self.policy.max_record_charged_bytes,
                self.policy.max_retained_charged_bytes,
                self.policy.max_retrieval_page_charged_bytes,
            )
        ):
            raise InteractRejected("evidence_policy_incompatible")
        return draft

    async def start_interact(
        self,
        request: InteractRequest,
        *,
        run_id: str,
        expected_provenance: SegmentProvenance,
        revalidate: Callable[[], None],
        charge_markers: ChargeInteractMarkers,
        submit_uart_write: Callable[[bytes], Awaitable[BackendWriteResult]],
        pending_stop: Callable[[], tuple[InteractOutcome, ...]],
        operation_id: str | None = None,
    ) -> _InteractOperation:
        async with self._gate:
            revalidate()
            if (
                self._close_task is not None
                or self.current_provenance != expected_provenance
            ):
                raise InteractRejected("interact_unavailable")
            if request.session_id != self.session_id:
                raise InteractRejected("session_not_associated")
            draft = self.preflight_interact(
                request, expected_provenance, charge_markers, operation_id=operation_id
            )
            if self._interact is not None:
                raise InteractRejected("busy")
            try:
                record = await self._recorder.append(draft)
                if not isinstance(record, InteractStartedEvidence):
                    raise RuntimeError("invalid Interact intent acknowledgement")
                started_at = self._now()
                operation = _InteractOperation(
                    self, request, record, run_id, started_at, pending_stop
                )
                self._interact = operation
                self._publish(record, now=started_at)
                # No await from intent ACK through revalidation/strong registration.
                operation.refresh_stop(started_at)
                try:
                    revalidate()
                    if operation.state.observation is None:
                        operation.write = asyncio.ensure_future(
                            submit_uart_write(request.payload)
                        )
                        operation.state.mark_submitted()
                    else:
                        operation.state.suppress_write(started_at)
                except Exception:
                    operation.state.stop(
                        (InteractOutcome.TRANSPORT_FAILURE,), started_at
                    )
                    operation.state.suppress_write(started_at)
                operation.start_owner()
                return operation
            finally:
                self._notify_follow()

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
            try:
                record = await self._recorder.append(draft)
                if not isinstance(record, OperationStartedEvidence):
                    raise RuntimeError("invalid Monitor start acknowledgement")
                # This sample and installation are atomic with respect to acquisition.
                started_at = self._now()
                operation = _MonitorOperation(self, record, run_id, started_at)
                self._operation = operation
                if self._interact is not None:
                    self._interact.publish(record, started_at)
                intent = None if pending_stop is None else pending_stop()
                if intent is not None:
                    self._stop(intent)
                return operation
            finally:
                self._notify_follow()

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
        interaction = self._interact
        if interaction is not None:
            await asyncio.gather(interaction.owner, return_exceptions=True)
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
                    try:
                        record = await self._coordinator._recorder.append(draft)
                        if not isinstance(record, OperationEndedEvidence):
                            raise RuntimeError("invalid Monitor end acknowledgement")
                        ended = EvidenceReference(
                            self._coordinator.session_id, record.sequence
                        )
                        interaction = self._coordinator._interact
                        if interaction is not None and interaction.active:
                            try:
                                sample = (
                                    self._coordinator._now()
                                    if interaction.state.observation is None
                                    else self._coordinator._last_now
                                )
                            except Exception:
                                interaction.fail()
                            else:
                                self._coordinator._publish(record, now=sample)
                    finally:
                        self._coordinator._notify_follow()
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


class InteractRejected(RuntimeError):
    """Normalized pre-intent rejection, without backend or journal details."""

    def __init__(self, kind: str) -> None:
        if type(kind) is not str or kind not in {
            "no_associated_session",
            "session_not_associated",
            "not_active",
            "interact_unavailable",
            "policy_denied",
            "capability_unavailable",
            "evidence_policy_incompatible",
            "busy",
        }:
            raise ValueError("Interact rejection kind must be declared")
        self._kind = kind
        super().__init__(kind)

    @property
    def kind(self) -> str:
        return self._kind


type ChargeInteractMarkers = Callable[
    [
        PendingInteractStartedEvidence,
        tuple[PendingUartTxSettledEvidence, ...],
        tuple[PendingInteractEndedEvidence, ...],
    ],
    tuple[int, int, int],
]


@dataclass(frozen=True, slots=True)
class PreparedInteractAccess:
    session_id: SessionId
    policy: SessionPolicy
    coordinator: MonitorRecordingCoordinator
    clock: MonitorClock
    charge_markers: ChargeInteractMarkers

    def __post_init__(self) -> None:
        if not isinstance(self.coordinator, MonitorRecordingCoordinator):
            raise TypeError("Interact access requires the committed coordinator")
        if (
            self.session_id != self.coordinator.session_id
            or self.policy != self.coordinator.policy
            or self.clock is not self.coordinator.clock
            or not callable(self.charge_markers)
        ):
            raise ValueError("Interact access must match recorder, policy and clock")


class _InteractOperation:
    """Strong owner of one write, bounded observation and independent audits."""

    def __init__(
        self,
        coordinator: MonitorRecordingCoordinator,
        request: InteractRequest,
        start: InteractStartedEvidence,
        run_id: str,
        started_at: int,
        pending_stop: Callable[[], tuple[InteractOutcome, ...]],
    ) -> None:
        self.coordinator, self.request, self.start = coordinator, request, start
        self.run_id, self.pending_stop = run_id, pending_stop
        self._started_at = started_at
        self.state = InteractState(
            request=request,
            start_sequence=start.sequence,
            provenance=start.provenance,
            clock_origin_id=start.clock_origin_id,
            started_at_ns=started_at,
        )
        self.write: asyncio.Future[BackendWriteResult] | None = None
        self.error: Exception | None = None
        self.changed = asyncio.Event()
        self.timer: asyncio.Task[None] | None = None
        self._owner: asyncio.Task[InteractReport] | None = None

    @property
    def owner(self) -> asyncio.Task[InteractReport]:
        assert self._owner is not None
        return self._owner

    @property
    def active(self) -> bool:
        return self.error is None and self.state.outcome is None

    def start_owner(self) -> None:
        if self.state.observation is None:
            self.timer = asyncio.create_task(self._deadline())
        self._owner = asyncio.create_task(
            self._settle(), name="dutchmate-interact-settlement"
        )
        self._owner.add_done_callback(
            lambda task: None if task.cancelled() else task.exception()
        )

    def _changed(self) -> None:
        if self.state.observation is not None and self.timer is not None:
            self.timer.cancel()
        self.changed.set()

    def fail(self) -> None:
        self.error = self.error or RuntimeError("Interact infrastructure failure")
        self.changed.set()
        if self.timer is not None:
            self.timer.cancel()

    def refresh_stop(self, now: int) -> None:
        if outcomes := self.pending_stop():
            self.state.stop(outcomes, now)
            self._changed()

    def stop(self, outcomes: tuple[InteractOutcome, ...]) -> None:
        if not self.active:
            return
        try:
            self.state.stop(outcomes, self.coordinator._now())
            self._changed()
        except Exception:
            self.fail()

    def publish(self, record: EvidenceRecord, now: int) -> None:
        if not self.active:
            return
        try:
            # A committed boundary belongs to the window before it decides the
            # observation. Acquisition's matching snapshot is a fallback only;
            # applying it first would incorrectly exclude this boundary record.
            if not isinstance(record, (SegmentStartedEvidence, SegmentEndedEvidence)):
                self.refresh_stop(now)
            self.state.publish(record, now)
            self._changed()
        except Exception:
            self.fail()

    async def _deadline(self) -> None:
        try:
            while self.state.observation is None and self.error is None:
                deadline = self.start.timeout_ms * 1000000
                # The state has validated checked arithmetic at installation.
                await self.coordinator.clock.wait_until(self._started_at + deadline)
                now = self.coordinator._now()
                self.refresh_stop(now)
                self.state.advance_time(now)
                self._changed()
        except Exception:
            self.fail()

    async def _audit(
        self,
        draft: PendingUartTxSettledEvidence | PendingInteractEndedEvidence,
        expected: type[UartTxSettledEvidence] | type[InteractEndedEvidence],
        kind: Literal["uart_tx_settled", "interact_ended"],
    ) -> tuple[EvidenceReference | None, InteractAuditFailure | None]:
        try:
            async with self.coordinator._gate:
                try:
                    record = await self.coordinator._recorder.append(draft)
                    if not isinstance(record, expected):
                        raise RuntimeError("invalid Interact audit acknowledgement")
                    self.coordinator._publish(record)
                    return EvidenceReference(
                        self.coordinator.session_id, record.sequence
                    ), None
                finally:
                    self.coordinator._notify_follow()
        except JournalFailure as error:
            return None, InteractAuditFailure(kind, "journal", error.kind.value)
        except Exception:
            return None, InteractAuditFailure(kind, "service", "internal_failure")

    async def _settle(self) -> InteractReport:
        try:
            if self.write is not None:
                try:
                    result = await asyncio.shield(self.write)
                except Exception:
                    result = BackendWriteResult(
                        BackendWriteStatus.FAILURE,
                        None,
                        BackendFailureKind.INTERNAL_CONTRACT_FAILURE,
                    )
                if self.error is not None:
                    raise self.error
                now = self.coordinator._now()
                self.refresh_stop(now)
                self.state.settle_write(result, now)
                self._changed()
            if self.error is not None:
                raise self.error
            tx = self.state.tx
            assert tx is not None
            stored_tx = RecordedTxFacts(
                tx.submitted,
                str(tx.status),
                tx.accepted_prefix_bytes,
                None if tx.failure_code is None else tx.failure_code.value,
                tx.acknowledgement_scope,
                tx.clock_origin_id,
                tx.settled_at_ns,
            )
            tx_ref, tx_failure = await self._audit(
                PendingUartTxSettledEvidence(
                    self.start.operation_id, self.start.sequence, stored_tx
                ),
                UartTxSettledEvidence,
                "uart_tx_settled",
            )
            while self.state.outcome is None and self.error is None:
                self.changed.clear()
                await self.changed.wait()
            if self.error is not None:
                raise self.error
            observation, outcome = self.state.observation, self.state.outcome
            assert observation is not None and outcome is not None
            if self.timer is not None:
                self.timer.cancel()
                await asyncio.gather(self.timer, return_exceptions=True)
            end_ref, end_failure = await self._audit(
                PendingInteractEndedEvidence(
                    self.start.operation_id,
                    self.start.sequence,
                    None if tx_ref is None else tx_ref.sequence,
                    stored_tx,
                    None
                    if tx_failure is None
                    else RecordedTxAuditFailure(tx_failure.source, tx_failure.code),
                    outcome,
                    observation,
                ),
                InteractEndedEvidence,
                "interact_ended",
            )
            failures = tuple(f for f in (tx_failure, end_failure) if f is not None)
            durability: Literal[
                "complete", "tx_unconfirmed", "end_unconfirmed", "both_unconfirmed"
            ] = (
                "complete"
                if not failures
                else "both_unconfirmed"
                if len(failures) == 2
                else "tx_unconfirmed"
                if tx_failure is not None
                else "end_unconfirmed"
            )
            return InteractReport(
                self.run_id,
                self.coordinator.session_id,
                self.start.operation_id,
                self.start.provenance,
                self.request.payload,
                self.request.conditions,
                outcome,
                EvidenceReference(self.coordinator.session_id, self.start.sequence),
                tx_ref,
                end_ref,
                tx,
                observation,
                durability,
                failures,
            )
        finally:
            if self.timer is not None:
                self.timer.cancel()
                await asyncio.gather(self.timer, return_exceptions=True)
            if self.coordinator._interact is self:
                self.coordinator._interact = None

    async def wait(self) -> InteractReport:
        return await asyncio.shield(self.owner)
