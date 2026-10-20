"""Pure bounded Interact facts; no writer execution or live workflow wiring."""

from collections import deque
from dataclasses import dataclass
from typing import Literal

from dutchmate_core.backend import (
    BackendFailureKind,
    BackendWriteResult,
    BackendWriteStatus,
)
from dutchmate_core.evidence import (
    JournalFailureKind,
    PendingInteractEndedEvidence,
    PendingInteractStartedEvidence,
    PendingUartTxSettledEvidence,
)
from dutchmate_core.model import (
    SQLITE_INTEGER_MAX,
    ClientAnnotationEvidence,
    EvidenceRecord,
    EvidenceReference,
    InteractEndedEvidence,
    InteractMatch,
    InteractObservation,
    InteractObservationOutcome,
    InteractOutcome,
    InteractStartedEvidence,
    MonitorClockFacts,
    MonitorMatchEnd,
    MonitorMatchStart,
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
    UartTxSettledEvidence,
    checked_persisted_add,
    validate_monitor_bounds,
    validate_monitor_uuid,
    validate_persisted_counter,
    validate_record_sequence,
)


def _validate_bytes(payload: bytes, conditions: tuple[bytes, ...]) -> None:
    if type(payload) is not bytes:
        raise TypeError("payload must be exact bytes")
    if not 1 <= len(payload) <= 4096:
        raise ValueError("payload must contain1..4096 bytes")
    if type(conditions) is not tuple:
        raise TypeError("conditions must be an immutable exact tuple")
    if not 1 <= len(conditions) <= 4:
        raise ValueError("Interact requires1..4 conditions")
    for condition in conditions:
        validate_monitor_bounds(condition, 1, 1)


@dataclass(frozen=True, slots=True)
class InteractRequest:
    session_id: SessionId
    payload: bytes
    conditions: tuple[bytes, ...]
    timeout_ms: int
    max_rx_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, SessionId):
            raise TypeError("Interact requires a session ID")
        _validate_bytes(self.payload, self.conditions)
        validate_monitor_bounds(self.conditions[0], self.timeout_ms, self.max_rx_bytes)


@dataclass(frozen=True, slots=True)
class InteractTxFacts:
    submitted: bool
    status: BackendWriteStatus | Literal["not_submitted"]
    accepted_prefix_bytes: int | None
    failure_code: BackendFailureKind | None
    acknowledgement_scope: Literal["backend_acceptance"]
    clock_origin_id: str
    settled_at_ns: int

    def __post_init__(self) -> None:
        if type(self.submitted) is not bool:
            raise TypeError("write submission must be an exact boolean")
        if self.submitted:
            if not isinstance(self.status, BackendWriteStatus):
                raise TypeError("submitted write requires a declared result")
            BackendWriteResult(
                self.status, self.accepted_prefix_bytes, self.failure_code
            )
        elif (
            type(self.status) is not str
            or self.status != "not_submitted"
            or self.accepted_prefix_bytes is not None
            or self.failure_code is not None
        ):
            raise ValueError("suppressed write must have no acceptance/failure claim")
        if (
            type(self.acknowledgement_scope) is not str
            or self.acknowledgement_scope != "backend_acceptance"
        ):
            raise ValueError("write acknowledgement is backend acceptance only")
        validate_monitor_uuid(self.clock_origin_id)
        validate_persisted_counter(self.settled_at_ns, name="TX settlement time")


@dataclass(frozen=True, slots=True)
class InteractAuditFailure:
    record_kind: Literal["uart_tx_settled", "interact_ended"]
    source: Literal["journal", "service"]
    code: str

    def __post_init__(self) -> None:
        if type(self.record_kind) is not str or self.record_kind not in {
            "uart_tx_settled",
            "interact_ended",
        }:
            raise ValueError("audit failure must identify a settlement or end")
        if type(self.source) is not str or type(self.code) is not str:
            raise TypeError("audit failure must be normalized text")
        if self.source == "journal" and self.code in {
            k.value for k in JournalFailureKind
        }:
            return
        if self.source == "service" and self.code == "internal_failure":
            return
        raise ValueError("audit failure must be a declared journal/internal failure")


_EXTERNAL_OUTCOMES = frozenset(
    {
        InteractOutcome.SERVICE_STOPPING,
        InteractOutcome.DETACHED,
        InteractOutcome.CANCELLED,
        InteractOutcome.DISCONNECTED,
        InteractOutcome.TIMESTAMP_ORIGIN_RESET,
        InteractOutcome.RECORDING_FAILURE,
        InteractOutcome.TRANSPORT_FAILURE,
    }
)
_WRITE_FAILURE_OUTCOMES = {
    BackendWriteStatus.PARTIAL: InteractOutcome.PARTIAL_WRITE,
    BackendWriteStatus.TIMEOUT: InteractOutcome.WRITE_TIMEOUT,
    BackendWriteStatus.DISCONNECTED: InteractOutcome.DISCONNECTED,
    BackendWriteStatus.FAILURE: InteractOutcome.TRANSPORT_FAILURE,
}


def _validate_tx_payload(tx: InteractTxFacts, payload: bytes) -> None:
    if tx.status is BackendWriteStatus.ACKNOWLEDGED:
        if tx.accepted_prefix_bytes != len(payload):
            raise ValueError("full acknowledgement must equal requested payload length")
    elif tx.status is BackendWriteStatus.PARTIAL:
        assert tx.accepted_prefix_bytes is not None
        if tx.accepted_prefix_bytes >= len(payload):
            raise ValueError("partial acknowledgement must be shorter than payload")


def _validate_overall(
    outcome: InteractOutcome, tx: InteractTxFacts, observation: InteractObservation
) -> None:
    if not isinstance(outcome, InteractOutcome):
        raise TypeError("overall Interact outcome must be declared")
    if (
        tx.status is BackendWriteStatus.ACKNOWLEDGED
        and observation.outcome is InteractObservationOutcome.TX_FAILED
    ):
        raise ValueError("full acknowledgement cannot freeze TX failure")
    if outcome in _EXTERNAL_OUTCOMES:
        return  # An external latch can outlive an already-frozen observation.
    if not tx.submitted:
        raise ValueError("suppressed writes require an external termination")
    assert isinstance(tx.status, BackendWriteStatus)
    if tx.status is BackendWriteStatus.ACKNOWLEDGED:
        if outcome.value != observation.outcome.value:
            raise ValueError("acknowledged overall decision must match observation")
    elif _WRITE_FAILURE_OUTCOMES.get(tx.status) is not outcome:
        raise ValueError("overall decision must preserve write failure")


@dataclass(frozen=True, slots=True)
class InteractReport:
    run_id: str
    session_id: SessionId
    operation_id: str
    provenance: SegmentProvenance
    payload: bytes
    conditions: tuple[bytes, ...]
    outcome: InteractOutcome
    started_record: EvidenceReference
    tx_settled_record: EvidenceReference | None
    ended_record: EvidenceReference | None
    tx: InteractTxFacts
    observation: InteractObservation
    durability: Literal[
        "complete", "tx_unconfirmed", "end_unconfirmed", "both_unconfirmed"
    ]
    audit_failures: tuple[InteractAuditFailure, ...]

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or not self.run_id:
            raise ValueError("Interact report requires an opaque run identity")
        if not isinstance(self.session_id, SessionId):
            raise TypeError("Interact report requires a session ID")
        validate_monitor_uuid(self.operation_id)
        if not isinstance(self.provenance, SegmentProvenance):
            raise TypeError("Interact report requires captured segment provenance")
        _validate_bytes(self.payload, self.conditions)
        if not isinstance(self.tx, InteractTxFacts) or not isinstance(
            self.observation, InteractObservation
        ):
            raise TypeError("Interact report requires validated TX/observation facts")
        _validate_tx_payload(self.tx, self.payload)
        _validate_overall(self.outcome, self.tx, self.observation)
        self._validate_observation()
        self._validate_references()
        self._validate_audit()

    def _validate_observation(self) -> None:
        observation = self.observation
        clock = observation.clock
        duration = clock.deadline_at_ns - clock.started_at_ns
        if duration % 1_000_000 or not 1_000_000 <= duration <= 4_000_000_000:
            raise ValueError("observation duration must be1..4000 whole milliseconds")
        if (
            self.tx.clock_origin_id != clock.origin_id
            or self.tx.settled_at_ns < clock.started_at_ns
        ):
            raise ValueError("TX settlement must use the captured clock after start")
        match = observation.match
        if match is not None:
            if match.condition_index >= len(self.conditions):
                raise ValueError("match must select a requested condition")
            length = len(self.conditions[match.condition_index])
            if observation.examined_rx_bytes < length or (
                match.start.sequence == match.end.sequence
                and match.end.byte_offset_exclusive - match.start.byte_offset != length
            ):
                raise ValueError("match length disagrees with the selected condition")
        if (
            self.tx.status is BackendWriteStatus.ACKNOWLEDGED
            and observation.outcome is InteractObservationOutcome.TX_FAILED
        ):
            raise ValueError("full acknowledgement cannot freeze TX failure")

    def _validate_references(self) -> None:
        if not isinstance(self.started_record, EvidenceReference):
            raise TypeError("Interact report requires an acknowledged start")
        for reference in (
            self.started_record,
            self.tx_settled_record,
            self.ended_record,
        ):
            if reference is None:
                continue
            if not isinstance(reference, EvidenceReference):
                raise TypeError("audit references must be validated")
            validate_record_sequence(reference.sequence)
            if reference.session_id != self.session_id:
                raise ValueError("audit references must use the captured session")
        start = self.started_record.sequence
        if self.observation.window.start_inclusive != start + 1:
            raise ValueError("observation window must follow acknowledged intent")
        if (
            self.tx_settled_record is not None
            and self.tx_settled_record.sequence <= start
        ):
            raise ValueError("TX settlement must follow intent")
        if self.ended_record is not None and (
            self.ended_record.sequence <= start
            or self.ended_record.sequence < self.observation.window.end_exclusive
            or (
                self.tx_settled_record is not None
                and self.ended_record.sequence <= self.tx_settled_record.sequence
            )
        ):
            raise ValueError("end must follow intent, TX settlement and the window")

    def _validate_audit(self) -> None:
        if type(self.audit_failures) is not tuple or len(self.audit_failures) > 2:
            raise TypeError("audit failures must be an immutable bounded tuple")
        if any(not isinstance(f, InteractAuditFailure) for f in self.audit_failures):
            raise TypeError("audit failures must be normalized")
        missing = tuple(
            kind
            for kind, reference in (
                ("uart_tx_settled", self.tx_settled_record),
                ("interact_ended", self.ended_record),
            )
            if reference is None
        )
        if tuple(f.record_kind for f in self.audit_failures) != missing:
            raise ValueError("each unconfirmed audit needs exactly one ordered failure")
        expected = {
            (): "complete",
            ("uart_tx_settled",): "tx_unconfirmed",
            ("interact_ended",): "end_unconfirmed",
            ("uart_tx_settled", "interact_ended"): "both_unconfirmed",
        }[missing]
        if type(self.durability) is not str or self.durability != expected:
            raise ValueError("durability must agree with acknowledged audit references")


class _LiteralMatchers:
    """Up to four KMP prefixes and one bounded deque of original byte positions."""

    def __init__(self, request: InteractRequest) -> None:
        self._conditions = request.conditions
        self._limit = request.max_rx_bytes
        self._prefixes: list[tuple[int, ...]] = []
        for condition in self._conditions:
            prefix = [0] * len(condition)
            length = 0
            for index in range(1, len(condition)):
                while length and condition[index] != condition[length]:
                    length = prefix[length - 1]
                if condition[index] == condition[length]:
                    length += 1
                prefix[index] = length
            self._prefixes.append(tuple(prefix))
        self._lengths = [0] * len(self._conditions)
        self._positions: deque[MonitorMatchStart] = deque(
            maxlen=max(map(len, self._conditions))
        )
        self.examined_rx_bytes = 0
        self.match: InteractMatch | None = None

    def reset(self) -> None:
        self._lengths = [0] * len(self._conditions)
        self._positions.clear()

    def feed(self, sequence: int, payload: bytes) -> InteractObservationOutcome | None:
        for offset, byte in enumerate(payload):
            self.examined_rx_bytes += 1
            self._positions.append(MonitorMatchStart(sequence, offset))
            for index, condition in enumerate(self._conditions):
                length = self._lengths[index]
                prefix = self._prefixes[index]
                while length and byte != condition[length]:
                    length = prefix[length - 1]
                if byte == condition[length]:
                    length += 1
                self._lengths[index] = length
                if length == len(condition):
                    self.match = InteractMatch(
                        index,
                        self._positions[-length],
                        MonitorMatchEnd(sequence, offset + 1),
                    )
                    return InteractObservationOutcome.MATCHED
            if self.examined_rx_bytes == self._limit:
                return InteractObservationOutcome.BYTE_LIMIT
        return None


class InteractState:
    """Synchronous decisions over supplied facts; no scheduling or I/O.

    Submission/settlement methods only update state. They neither authorize nor
    perform a write. Later owners must supply admitted facts and post-ACK times.
    """

    def __init__(
        self,
        *,
        request: InteractRequest,
        start_sequence: int,
        provenance: SegmentProvenance,
        clock_origin_id: str,
        started_at_ns: int,
    ) -> None:
        if not isinstance(request, InteractRequest):
            raise TypeError("Interact state requires a validated request")
        validate_record_sequence(start_sequence)
        if not isinstance(provenance, SegmentProvenance):
            raise TypeError("Interact state requires captured segment provenance")
        validate_monitor_uuid(clock_origin_id)
        self._deadline = checked_persisted_add(
            started_at_ns, request.timeout_ms * 1_000_000, name="Interact deadline"
        )
        self._request = request
        self._start_sequence = start_sequence
        self._seen_sequence = start_sequence
        self._last_included = start_sequence
        self._provenance = provenance
        self._origin = clock_origin_id
        self._started_at = started_at_ns
        self._last_time = started_at_ns
        self._matcher = _LiteralMatchers(request)
        self._losses = 0
        self._submitted = False
        self._tx: InteractTxFacts | None = None
        self._observation: InteractObservation | None = None
        self._termination: InteractOutcome | None = None
        self._outcome: InteractOutcome | None = None

    @property
    def observation(self) -> InteractObservation | None:
        return self._observation

    @property
    def tx(self) -> InteractTxFacts | None:
        return self._tx

    @property
    def outcome(self) -> InteractOutcome | None:
        return self._outcome

    def _time(self, now_ns: int) -> None:
        validate_persisted_counter(now_ns, name="Interact host decision time")
        if now_ns < self._last_time:
            raise ValueError("Interact host clock must not regress")
        self._last_time = now_ns

    def _freeze(self, outcome: InteractObservationOutcome, now_ns: int) -> None:
        if self._observation is not None:
            return
        if now_ns >= self._deadline:
            outcome = InteractObservationOutcome.TIMEOUT
        self._observation = InteractObservation(
            window=SequenceRange(self._start_sequence + 1, self._last_included + 1),
            outcome=outcome,
            examined_rx_bytes=self._matcher.examined_rx_bytes,
            observer_loss_records=self._losses,
            match=self._matcher.match
            if outcome is InteractObservationOutcome.MATCHED
            else None,
            clock=MonitorClockFacts(
                self._origin, self._started_at, self._deadline, now_ns
            ),
        )

    def _deadline_check(self, now_ns: int) -> None:
        if now_ns >= self._deadline:
            self._freeze(InteractObservationOutcome.TIMEOUT, now_ns)

    def _latch(self, outcome: InteractOutcome, now_ns: int) -> None:
        if self._termination is None:
            self._termination = outcome
        self._freeze(InteractObservationOutcome(self._termination.value), now_ns)

    def _decide(self) -> None:
        if self._outcome is not None or self._tx is None:
            return
        if self._termination is not None:
            self._outcome = self._termination
        elif self._tx.status is BackendWriteStatus.ACKNOWLEDGED:
            if self._observation is not None:
                self._outcome = InteractOutcome(self._observation.outcome.value)
        else:
            assert isinstance(self._tx.status, BackendWriteStatus)
            self._outcome = _WRITE_FAILURE_OUTCOMES[self._tx.status]

    def mark_submitted(self) -> bool:
        if self._submitted or self._tx is not None:
            raise RuntimeError("Interact already submitted or settled")
        if self._termination is not None:
            return False
        self._submitted = True
        return True

    def suppress_write(self, now_ns: int) -> None:
        if self._submitted or self._tx is not None or self._termination is None:
            raise RuntimeError("suppression requires a pre-submission termination")
        self._time(now_ns)
        self._tx = InteractTxFacts(
            False,
            "not_submitted",
            None,
            None,
            "backend_acceptance",
            self._origin,
            now_ns,
        )
        self._decide()

    def settle_write(self, result: object, now_ns: int) -> None:
        if not self._submitted or self._tx is not None:
            raise RuntimeError("only a pending submitted write can settle")
        self._time(now_ns)
        self._deadline_check(now_ns)
        try:
            if not isinstance(result, BackendWriteResult):
                raise TypeError("backend write result is not normalized")
            tx = InteractTxFacts(
                True,
                result.status,
                result.accepted_prefix_bytes,
                result.failure_code,
                "backend_acceptance",
                self._origin,
                now_ns,
            )
            _validate_tx_payload(tx, self._request.payload)
        except TypeError, ValueError:
            tx = InteractTxFacts(
                True,
                BackendWriteStatus.FAILURE,
                None,
                BackendFailureKind.INTERNAL_CONTRACT_FAILURE,
                "backend_acceptance",
                self._origin,
                now_ns,
            )
        self._tx = tx
        if tx.status is not BackendWriteStatus.ACKNOWLEDGED:
            self._freeze(InteractObservationOutcome.TX_FAILED, now_ns)
        self._decide()

    def advance_time(self, now_ns: int) -> None:
        if self._outcome is not None:
            return
        self._time(now_ns)
        self._deadline_check(now_ns)
        self._decide()

    def stop(self, outcomes: tuple[InteractOutcome, ...], now_ns: int) -> None:
        """Latch one external event, or simultaneous service/detach/cancel seals."""
        if self._outcome is not None:
            return
        if type(outcomes) is not tuple or not 1 <= len(outcomes) <= 7:
            raise ValueError("stop requires a bounded tuple of external outcomes")
        if any(
            not isinstance(o, InteractOutcome) or o not in _EXTERNAL_OUTCOMES
            for o in outcomes
        ):
            raise ValueError("stop requires declared external termination")
        priority = (
            InteractOutcome.SERVICE_STOPPING,
            InteractOutcome.DETACHED,
            InteractOutcome.CANCELLED,
        )
        if len(outcomes) > 1 and any(o not in priority for o in outcomes):
            raise ValueError("only seal intents can share one checkpoint")
        self._time(now_ns)
        chosen = next((o for o in priority if o in outcomes), outcomes[0])
        self._latch(chosen, now_ns)
        self._decide()

    def publish(self, record: EvidenceRecord, now_ns: int) -> None:
        if self._outcome is not None:
            return
        if not isinstance(
            record,
            (
                SegmentStartedEvidence,
                RxBytesEvidence,
                ObserverLossEvidence,
                SegmentEndedEvidence,
                OperationStartedEvidence,
                OperationEndedEvidence,
                ClientAnnotationEvidence,
                InteractStartedEvidence,
                UartTxSettledEvidence,
                InteractEndedEvidence,
            ),
        ):
            raise TypeError("Interact consumes committed normalized record values")
        validate_record_sequence(record.sequence)
        if record.sequence <= self._start_sequence:
            return
        if record.sequence <= self._seen_sequence:
            raise ValueError("committed records must be supplied in observation order")
        if isinstance(record, RxBytesEvidence) and (
            type(record.payload) is not bytes or not record.payload
        ):
            raise ValueError("RX must contain nonempty exact bytes")
        self._time(now_ns)
        self._seen_sequence = record.sequence
        self._deadline_check(now_ns)
        if self._observation is None:
            self._last_included = record.sequence
        terminal: InteractOutcome | None = None
        if isinstance(record, SegmentStartedEvidence):
            terminal = InteractOutcome.TIMESTAMP_ORIGIN_RESET
        elif isinstance(
            record, (RxBytesEvidence, ObserverLossEvidence, SegmentEndedEvidence)
        ):
            if (record.connection_id, record.segment_id) != (
                self._provenance.connection_id,
                self._provenance.segment_id,
            ):
                terminal = InteractOutcome.TIMESTAMP_ORIGIN_RESET
            elif isinstance(record, SegmentEndedEvidence):
                terminal = (
                    InteractOutcome.DETACHED
                    if record.reason is SegmentEndReason.EXPLICIT_STOP
                    else InteractOutcome(record.reason.value)
                )
            elif (
                record.observed_at.domain_id
                != self._provenance.backend_observation_timestamp_domain.domain_id
            ):
                terminal = InteractOutcome.TIMESTAMP_ORIGIN_RESET
        if terminal is not None:
            self._latch(terminal, now_ns)
        elif self._observation is None:
            if isinstance(record, RxBytesEvidence):
                outcome = self._matcher.feed(record.sequence, record.payload)
                if outcome is not None:
                    self._freeze(outcome, now_ns)
            elif isinstance(record, ObserverLossEvidence):
                self._losses = checked_persisted_add(
                    self._losses, 1, name="loss records"
                )
                self._matcher.reset()
        self._decide()


def _maximum_interact_drafts(
    start: PendingInteractStartedEvidence,
) -> tuple[
    tuple[PendingUartTxSettledEvidence, ...], tuple[PendingInteractEndedEvidence, ...]
]:
    """Legal standalone upper shapes, without a reservation/reachability claim."""
    maximum = SQLITE_INTEGER_MAX
    txs = [
        RecordedTxFacts(
            True,
            status.value,
            count,
            code,
            "backend_acceptance",
            start.clock_origin_id,
            maximum,
        )
        for status, count, code in (
            (BackendWriteStatus.ACKNOWLEDGED, len(start.payload), None),
            (BackendWriteStatus.PARTIAL, len(start.payload) - 1, None),
            (BackendWriteStatus.TIMEOUT, None, None),
            (BackendWriteStatus.DISCONNECTED, None, None),
            *(
                (BackendWriteStatus.FAILURE, None, code.value)
                for code in BackendFailureKind
            ),
        )
    ]
    txs.append(
        RecordedTxFacts(
            False,
            "not_submitted",
            None,
            None,
            "backend_acceptance",
            start.clock_origin_id,
            maximum,
        )
    )
    audit = RecordedTxAuditFailure(
        "journal",
        max(
            (k.value for k in JournalFailureKind), key=lambda s: len(s.encode("utf-8"))
        ),
    )
    longest_external = max(
        _EXTERNAL_OUTCOMES, key=lambda o: len(o.value.encode("utf-8"))
    )
    ends = []
    match_index = min(
        range(len(start.conditions)), key=lambda i: len(start.conditions[i])
    )
    match_length = len(start.conditions[match_index])
    for tx in txs:
        for outcome in InteractObservationOutcome:
            if (
                tx.status == "acknowledged"
                and outcome is InteractObservationOutcome.TX_FAILED
            ):
                continue
            if (
                outcome is InteractObservationOutcome.MATCHED
                and match_length > start.max_rx_bytes
            ):
                continue
            observation = InteractObservation(
                SequenceRange(maximum - 8, maximum - 4),
                outcome,
                start.max_rx_bytes,
                maximum,
                InteractMatch(
                    match_index,
                    MonitorMatchStart(maximum - 5, start.max_rx_bytes - match_length),
                    MonitorMatchEnd(maximum - 5, start.max_rx_bytes),
                )
                if outcome is InteractObservationOutcome.MATCHED
                else None,
                MonitorClockFacts(
                    start.clock_origin_id,
                    maximum - start.timeout_ms * 1000000,
                    maximum,
                    maximum
                    if outcome is InteractObservationOutcome.TIMEOUT
                    else maximum - 1,
                ),
            )
            natural = (
                InteractOutcome(outcome.value)
                if tx.status == "acknowledged"
                else _WRITE_FAILURE_OUTCOMES[BackendWriteStatus(tx.status)]
                if tx.submitted
                else longest_external
            )
            for overall in dict.fromkeys((natural, longest_external)):
                for lost_ack in (False, True):
                    ends.append(
                        PendingInteractEndedEvidence(
                            start.operation_id,
                            maximum - 9,
                            None if lost_ack else maximum - 3,
                            tx,
                            audit if lost_ack else None,
                            overall,
                            observation,
                        )
                    )
    return (
        tuple(
            PendingUartTxSettledEvidence(start.operation_id, maximum - 9, tx)
            for tx in txs
        ),
        tuple(ends),
    )
