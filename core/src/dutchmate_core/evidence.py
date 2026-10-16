"""Append-only authoritative evidence recording boundary."""

import asyncio
from dataclasses import FrozenInstanceError, dataclass, field
from enum import StrEnum
from typing import Final, Literal, Protocol

from dutchmate_core.model import (
    SQLITE_INTEGER_MAX,
    BackendObservationTimestamp,
    ClientAnnotationEvidence,
    ConnectionInstanceId,
    EvidenceRangeReference,
    EvidenceRecord,
    MonitorClockFacts,
    MonitorMatch,
    MonitorMatchEnd,
    MonitorMatchStart,
    MonitorOutcome,
    ObserverLossCause,
    ObserverLossEvidence,
    OperationEndedEvidence,
    OperationStartedEvidence,
    RetentionMarker,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentEndReason,
    SegmentId,
    SegmentProvenance,
    SegmentStartedEvidence,
    SequenceRange,
    SessionId,
    SessionPolicy,
    validate_persisted_counter,
)


class JournalOperation(StrEnum):
    CREATE = "create"
    OPEN = "open"
    CLOSE = "close"
    ENCODE = "encode"
    DECODE = "decode"
    APPEND = "append"
    RETRIEVE = "retrieve"


class JournalFailureKind(StrEnum):
    INVALID_INPUT = "invalid_input"
    JOURNAL_EXISTS = "journal_exists"
    JOURNAL_MISSING = "journal_missing"
    SESSION_MISMATCH = "session_mismatch"
    INCOMPATIBLE_APPLICATION = "incompatible_application"
    INCOMPATIBLE_SCHEMA_VERSION = "incompatible_schema_version"
    INCOMPATIBLE_RECORD_VERSION = "incompatible_record_version"
    INCOMPATIBLE_PROVENANCE_ENVELOPE_VERSION = (
        "incompatible_provenance_envelope_version"
    )
    CORRUPT_JOURNAL = "corrupt_journal"
    INVARIANT_VIOLATION = "invariant_violation"
    BUSY = "busy"
    CAPACITY = "capacity"
    DATABASE_OVER_CEILING = "capacity/database_over_ceiling"
    PHYSICAL_CEILING_UNAVAILABLE = "capacity/physical_ceiling_unavailable"
    SEQUENCE_EXHAUSTED = "capacity/sequence_exhausted"
    COUNTER_EXHAUSTED = "capacity/counter_exhausted"
    READ_ONLY = "read_only"
    PERMISSION_DENIED = "permission_denied"
    IO_FAILURE = "io_failure"
    CLOSED = "closed"


_JOURNAL_FAILURE_FACT_FIELDS = frozenset({"operation", "kind", "detail"})


@dataclass(slots=True, unsafe_hash=True)
class JournalFailure(RuntimeError):
    """Read-only journal facts with normal RuntimeError transport fields."""

    operation: Final[JournalOperation] = field()
    kind: Final[JournalFailureKind] = field()
    detail: Final[str | None] = None

    def __setattr__(self, name: str, value: object) -> None:
        if name in _JOURNAL_FAILURE_FACT_FIELDS and hasattr(self, name):
            raise FrozenInstanceError(f"cannot assign to field {name!r}")
        RuntimeError.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in _JOURNAL_FAILURE_FACT_FIELDS:
            raise FrozenInstanceError(f"cannot delete field {name!r}")
        RuntimeError.__delattr__(self, name)

    def __post_init__(self) -> None:
        if not isinstance(self.operation, JournalOperation):
            raise TypeError("journal failure operation must be declared")
        if not isinstance(self.kind, JournalFailureKind):
            raise TypeError("journal failure kind must be declared")
        if self.detail is not None and not isinstance(self.detail, str):
            raise TypeError("journal failure detail must be text or absent")
        message = f"{self.operation.value}/{self.kind.value}"
        if self.detail:
            message = f"{message}: {self.detail}"
        RuntimeError.__init__(self, message)


@dataclass(frozen=True, slots=True)
class EvidenceCursor:
    session_id: SessionId
    range_start_inclusive: int
    range_end_exclusive: int | None
    snapshot_end_exclusive: int
    next_sequence: int

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, SessionId):
            raise TypeError("cursor requires a session ID")
        validate_persisted_counter(
            self.range_start_inclusive,
            name="cursor range start",
        )
        validate_persisted_counter(
            self.snapshot_end_exclusive,
            name="cursor snapshot end",
        )
        validate_persisted_counter(
            self.next_sequence,
            name="cursor next sequence",
        )
        if self.range_end_exclusive is not None:
            validate_persisted_counter(
                self.range_end_exclusive,
                name="cursor range end",
            )
            if self.snapshot_end_exclusive > self.range_end_exclusive:
                raise ValueError("cursor snapshot exceeds the requested range")
        if not (
            self.range_start_inclusive
            <= self.next_sequence
            <= self.snapshot_end_exclusive
        ):
            raise ValueError("cursor position must remain within its snapshot")


@dataclass(frozen=True, slots=True)
class EvidenceRetrievalRequest:
    reference: SessionId | EvidenceRangeReference
    max_records: int
    max_charged_bytes: int
    cursor: EvidenceCursor | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reference, (SessionId, EvidenceRangeReference)):
            raise TypeError("retrieval requires a session or range reference")
        _validate_positive_persisted_integer(
            self.max_records,
            name="max records",
        )
        _validate_positive_persisted_integer(
            self.max_charged_bytes,
            name="max charged bytes",
        )
        if self.cursor is not None and not isinstance(self.cursor, EvidenceCursor):
            raise TypeError("retrieval cursor must be validated")


class EvidencePageOutcome(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    EXPIRED = "expired"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class EvidencePage:
    records: tuple[EvidenceRecord, ...]
    snapshot_end_exclusive: int
    expired_range: SequenceRange | None
    retention_marker: RetentionMarker | None
    never_existed_range: SequenceRange | None
    outcome: EvidencePageOutcome
    truncated: bool
    continuation: EvidenceCursor | None
    charged_bytes: int
    next_record_required_bytes: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple):
            raise TypeError("evidence page records must be a tuple")
        validate_persisted_counter(
            self.snapshot_end_exclusive,
            name="page snapshot end",
        )
        if not isinstance(self.outcome, EvidencePageOutcome):
            raise TypeError("evidence page outcome must be declared")
        if type(self.truncated) is not bool:
            raise TypeError("evidence page truncation must be boolean")
        validate_persisted_counter(self.charged_bytes, name="page charged bytes")
        if self.next_record_required_bytes is not None:
            _validate_positive_persisted_integer(
                self.next_record_required_bytes,
                name="next record required bytes",
            )


def _validate_positive_persisted_integer(value: int, *, name: str) -> int:
    validate_persisted_counter(value, name=name)
    if value == 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class PendingSegmentStartedEvidence:
    provenance: SegmentProvenance


@dataclass(frozen=True, slots=True)
class PendingRxBytesEvidence:
    connection_id: ConnectionInstanceId
    segment_id: SegmentId
    payload: bytes
    observed_at: BackendObservationTimestamp


@dataclass(frozen=True, slots=True)
class PendingObserverLossEvidence:
    connection_id: ConnectionInstanceId
    segment_id: SegmentId
    observer_id: str
    scope: str
    cause: ObserverLossCause
    lost_bytes: int | None
    observed_at: BackendObservationTimestamp


@dataclass(frozen=True, slots=True)
class PendingSegmentEndedEvidence:
    connection_id: ConnectionInstanceId
    segment_id: SegmentId
    reason: SegmentEndReason


type PendingEvidenceRecord = (
    PendingSegmentStartedEvidence
    | PendingRxBytesEvidence
    | PendingObserverLossEvidence
    | PendingSegmentEndedEvidence
    | PendingOperationStartedEvidence
    | PendingOperationEndedEvidence
    | PendingClientAnnotationEvidence
)


class EvidenceRecorder(Protocol):
    """Atomic append boundary for the active evidence journal."""

    async def append(self, draft: PendingEvidenceRecord) -> EvidenceRecord: ...


class InMemoryEvidenceRecorder:
    """Finite in-memory journal used by this software-only foundation."""

    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []
        self._append_lock = asyncio.Lock()

    async def append(self, draft: PendingEvidenceRecord) -> EvidenceRecord:
        async with self._append_lock:
            sequence = len(self._records)
            record = _assign_sequence(draft, sequence)
            self._records.append(record)
            return record

    def snapshot(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records)


def _assign_sequence(
    draft: PendingEvidenceRecord,
    sequence: int,
) -> EvidenceRecord:
    match draft:
        case PendingSegmentStartedEvidence(provenance=provenance):
            return SegmentStartedEvidence(sequence=sequence, provenance=provenance)
        case PendingRxBytesEvidence(
            connection_id=connection_id,
            segment_id=segment_id,
            payload=payload,
            observed_at=observed_at,
        ):
            return RxBytesEvidence(
                sequence=sequence,
                connection_id=connection_id,
                segment_id=segment_id,
                payload=payload,
                observed_at=observed_at,
            )
        case PendingObserverLossEvidence(
            connection_id=connection_id,
            segment_id=segment_id,
            observer_id=observer_id,
            scope=scope,
            cause=cause,
            lost_bytes=lost_bytes,
            observed_at=observed_at,
        ):
            return ObserverLossEvidence(
                sequence=sequence,
                connection_id=connection_id,
                segment_id=segment_id,
                observer_id=observer_id,
                scope=scope,
                cause=cause,
                lost_bytes=lost_bytes,
                observed_at=observed_at,
            )
        case PendingSegmentEndedEvidence(
            connection_id=connection_id,
            segment_id=segment_id,
            reason=reason,
        ):
            return SegmentEndedEvidence(
                sequence=sequence,
                connection_id=connection_id,
                segment_id=segment_id,
                reason=reason,
            )
        case PendingOperationStartedEvidence():
            return OperationStartedEvidence(
                sequence=sequence,
                operation_id=draft.operation_id,
                operation_kind=draft.operation_kind,
                provenance=draft.provenance,
                timeout_ms=draft.timeout_ms,
                max_rx_bytes=draft.max_rx_bytes,
                clock_origin_id=draft.clock_origin_id,
                condition=draft.condition,
            )
        case PendingOperationEndedEvidence():
            return OperationEndedEvidence(
                sequence=sequence,
                operation_id=draft.operation_id,
                operation_kind=draft.operation_kind,
                start_sequence=draft.start_sequence,
                window=draft.window,
                outcome=draft.outcome,
                examined_rx_bytes=draft.examined_rx_bytes,
                observer_loss_records=draft.observer_loss_records,
                match=draft.match,
                clock=draft.clock,
            )
        case PendingClientAnnotationEvidence():
            return ClientAnnotationEvidence(
                sequence=sequence,
                text=draft.text,
                client_surface=draft.client_surface,
                clock_origin_id=draft.clock_origin_id,
                received_at_ns=draft.received_at_ns,
            )
        case _:
            raise TypeError(f"unsupported evidence draft: {type(draft).__name__}")


@dataclass(frozen=True, slots=True)
class PendingOperationStartedEvidence:
    operation_id: str
    operation_kind: Literal["monitor"]
    provenance: SegmentProvenance
    timeout_ms: int
    max_rx_bytes: int
    clock_origin_id: str
    condition: bytes

    def __post_init__(self) -> None:
        OperationStartedEvidence(
            0,
            self.operation_id,
            self.operation_kind,
            self.provenance,
            self.timeout_ms,
            self.max_rx_bytes,
            self.clock_origin_id,
            self.condition,
        )


@dataclass(frozen=True, slots=True)
class PendingOperationEndedEvidence:
    operation_id: str
    operation_kind: Literal["monitor"]
    start_sequence: int
    window: SequenceRange
    outcome: MonitorOutcome
    examined_rx_bytes: int
    observer_loss_records: int
    match: MonitorMatch | None
    clock: MonitorClockFacts

    def __post_init__(self) -> None:
        OperationEndedEvidence(
            0,
            self.operation_id,
            self.operation_kind,
            self.start_sequence,
            self.window,
            self.outcome,
            self.examined_rx_bytes,
            self.observer_loss_records,
            self.match,
            self.clock,
        )


def maximum_monitor_end_drafts(
    operation_id: str,
    clock_origin_id: str,
) -> tuple[PendingOperationEndedEvidence, ...]:
    """Nine legal standalone upper shapes, without pairing/reachability claims."""
    maximum = SQLITE_INTEGER_MAX
    match = MonitorMatch(
        MonitorMatchStart(maximum - 1, maximum - 1),
        MonitorMatchEnd(maximum - 1, maximum),
    )
    return tuple(
        PendingOperationEndedEvidence(
            operation_id=operation_id,
            operation_kind="monitor",
            start_sequence=maximum - 2,
            window=SequenceRange(maximum - 1, maximum),
            outcome=outcome,
            examined_rx_bytes=1048576,
            observer_loss_records=maximum,
            match=match if outcome is MonitorOutcome.MATCHED else None,
            clock=MonitorClockFacts(
                clock_origin_id,
                maximum - 2,
                maximum - 1,
                maximum if outcome is MonitorOutcome.TIMEOUT else maximum - 2,
            ),
        )
        for outcome in MonitorOutcome
    )


def monitor_marker_charges_fit(policy: SessionPolicy, charges: tuple[int, int]) -> bool:
    """Pure preflight only: no quota reservation or later commit guarantee."""
    if not isinstance(policy, SessionPolicy):
        raise TypeError("marker policy must be validated")
    if type(charges) is not tuple or len(charges) != 2:
        raise TypeError("marker charges must be a pair")
    for charge in charges:
        _validate_positive_persisted_integer(charge, name="marker charge")
    return all(
        charge <= ceiling
        for charge in charges
        for ceiling in (
            policy.max_record_charged_bytes,
            policy.max_retained_charged_bytes,
            policy.max_retrieval_page_charged_bytes,
        )
    )


@dataclass(frozen=True, slots=True)
class PendingClientAnnotationEvidence:
    text: str
    client_surface: str
    clock_origin_id: str
    received_at_ns: int

    def __post_init__(self) -> None:
        ClientAnnotationEvidence(
            0, self.text, self.client_surface, self.clock_origin_id, self.received_at_ns
        )

    @property
    def assertion_class(self) -> Literal["client_assertion"]:
        return "client_assertion"

    @property
    def attribution_basis(self) -> Literal["client_asserted"]:
        return "client_asserted"
