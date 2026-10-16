"""Normalized backend and evidence values for authoritative UART RX."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

SQLITE_INTEGER_MAX = 2**63 - 1
GENERIC_PROVENANCE_ENVELOPE_VERSION = 1


class PersistedCounterOverflowError(OverflowError):
    """Raised before a persisted signed-64-bit sum would overflow."""


def validate_persisted_counter(value: int, *, name: str) -> int:
    """Validate a non-negative integer representable by SQLite INTEGER."""

    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if not 0 <= value <= SQLITE_INTEGER_MAX:
        raise ValueError(f"{name} must be in 0..{SQLITE_INTEGER_MAX}")
    return value


def _validate_positive_persisted_integer(value: int, *, name: str) -> int:
    validate_persisted_counter(value, name=name)
    if value == 0:
        raise ValueError(f"{name} must be positive")
    return value


def validate_record_sequence(value: int) -> int:
    """Validate a sequence that can identify an existing evidence record."""

    validate_persisted_counter(value, name="record sequence")
    if value == SQLITE_INTEGER_MAX:
        raise ValueError("record sequence must leave room for next_sequence")
    return value


def checked_persisted_add(left: int, right: int, *, name: str) -> int:
    """Add persisted counters without escaping the SQLite integer domain."""

    validate_persisted_counter(left, name=name)
    validate_persisted_counter(right, name=name)
    result = left + right
    if result > SQLITE_INTEGER_MAX:
        raise PersistedCounterOverflowError(
            f"{name} would exceed {SQLITE_INTEGER_MAX}"
        )
    return result


@dataclass(frozen=True, slots=True)
class SessionId:
    """Opaque identity for the one durable session in a journal."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("session ID must be non-empty")


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    """Finite immutable retention, record, database, and retrieval ceilings."""

    max_retained_records: int
    max_retained_charged_bytes: int
    max_record_charged_bytes: int
    max_database_pages: int
    max_retrieval_page_records: int
    max_retrieval_page_charged_bytes: int

    def __post_init__(self) -> None:
        for field_name in (
            "max_retained_records",
            "max_retained_charged_bytes",
            "max_record_charged_bytes",
            "max_database_pages",
            "max_retrieval_page_records",
            "max_retrieval_page_charged_bytes",
        ):
            _validate_positive_persisted_integer(
                getattr(self, field_name),
                name=field_name.replace("_", " "),
            )
        if self.max_record_charged_bytes > self.max_retained_charged_bytes:
            raise ValueError(
                "maximum record charge must fit the retained charged-byte limit"
            )
        if (
            self.max_record_charged_bytes
            > self.max_retrieval_page_charged_bytes
        ):
            raise ValueError(
                "maximum record charge must fit the retrieval charged-byte ceiling"
            )


type ProvenanceScalar = None | bool | int | str


@dataclass(frozen=True, slots=True)
class ProvenanceField:
    """One scalar member of a backend-owned provenance snapshot."""

    name: str
    value: ProvenanceScalar

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("provenance field name must be non-empty")
        if self.value is not None and type(self.value) not in (bool, int, str):
            raise TypeError("provenance field value must be a supported scalar")


@dataclass(frozen=True, slots=True)
class ConnectionProvenanceSnapshot:
    """Generic envelope around opaque backend provenance data."""

    envelope_version: int
    backend_kind: str
    backend_schema_version: int
    fields: tuple[ProvenanceField, ...]

    def __post_init__(self) -> None:
        if type(self.envelope_version) is not int:
            raise TypeError("generic provenance envelope version must be an integer")
        if self.envelope_version != GENERIC_PROVENANCE_ENVELOPE_VERSION:
            raise ValueError("unsupported generic provenance envelope version")
        if not isinstance(self.backend_kind, str) or not self.backend_kind:
            raise ValueError("backend kind must be non-empty")
        _validate_positive_persisted_integer(
            self.backend_schema_version,
            name="backend schema version",
        )
        if not isinstance(self.fields, tuple) or not all(
            isinstance(field, ProvenanceField) for field in self.fields
        ):
            raise TypeError("provenance fields must be a tuple of ProvenanceField")
        names = tuple(field.name for field in self.fields)
        if names != tuple(sorted(set(names))):
            raise ValueError("provenance field names must be sorted unique values")


class BackendCapability(StrEnum):
    """Physical abilities reported by a backend connection."""

    UART_RECEIVE = "uart_receive"
    UART_SEND = "uart_send"
    SERIAL_LINE_CONTROL = "serial_line_control"
    GPIO_CONTROL = "gpio_control"
    GPIO_EVENTS = "gpio_events"


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    """Immutable capability snapshot for one connection segment."""

    values: frozenset[BackendCapability]

    def supports(self, capability: BackendCapability) -> bool:
        return capability in self.values


@dataclass(frozen=True, slots=True)
class ConnectionInstanceId:
    """Opaque Core-owned identity for one successful ownership acquisition."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("connection instance ID must be non-empty")


@dataclass(frozen=True, slots=True)
class SegmentId:
    """Opaque Core-owned identity for one provenance interval."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("segment ID must be non-empty")


class TimestampObserver(StrEnum):
    HOST = "host"
    DEVICE = "device"


class TimestampMeaning(StrEnum):
    OBSERVATION = "observation"


class TimestampUnit(StrEnum):
    NANOSECOND = "nanosecond"
    MICROSECOND = "microsecond"
    TICK = "tick"


class TimestampDomainMismatchError(ValueError):
    """Raised when a timestamp does not resolve to its claimed descriptor."""


class TimestampRegressionError(ValueError):
    """Raised when an observation timestamp decreases within one clock scope."""


class IncomparableTimestampsError(ValueError):
    """Raised when timestamps do not share one comparison scope."""


class InvalidTimestampOriginResetError(ValueError):
    """Raised when a reset does not establish a new domain and origin."""


class ObserverLossProvenanceMismatchError(ValueError):
    """Raised when reported loss does not match current observer provenance."""


@dataclass(frozen=True, slots=True)
class BackendObservationTimestampDomain:
    """Meaning and continuity scope for normalized RX/loss timestamps."""

    domain_id: str
    observer: TimestampObserver
    meaning: TimestampMeaning
    unit: TimestampUnit
    origin_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.domain_id, str) or not self.domain_id:
            raise ValueError("timestamp domain ID must be non-empty")
        if not isinstance(self.observer, TimestampObserver):
            raise TypeError("timestamp observer must be host or device")
        if not isinstance(self.meaning, TimestampMeaning):
            raise TypeError("timestamp meaning must be observation")
        if not isinstance(self.unit, TimestampUnit):
            raise TypeError("timestamp unit must be declared")
        if not isinstance(self.origin_id, str) or not self.origin_id:
            raise ValueError("timestamp origin ID must be non-empty")


@dataclass(frozen=True, slots=True)
class BackendObservationTimestamp:
    """Raw observation value in a declared backend timestamp domain."""

    domain_id: str
    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.domain_id, str) or not self.domain_id:
            raise ValueError("timestamp domain ID must be non-empty")
        if type(self.value) is not int:
            raise TypeError("timestamp value must be an integer")
        if self.value < 0:
            raise ValueError("timestamp value must be non-negative")


def validate_backend_observation_timestamp(
    timestamp: BackendObservationTimestamp,
    domain: BackendObservationTimestampDomain,
) -> None:
    """Require a timestamp to resolve to the supplied domain descriptor."""

    if timestamp.domain_id != domain.domain_id:
        raise TimestampDomainMismatchError(
            f"timestamp domain {timestamp.domain_id!r} does not match "
            f"current domain {domain.domain_id!r}"
        )


def compare_backend_observation_timestamps(
    left: BackendObservationTimestamp,
    left_domain: BackendObservationTimestampDomain,
    right: BackendObservationTimestamp,
    right_domain: BackendObservationTimestampDomain,
) -> int:
    """Compare values only when both descriptors define one clock scope."""

    validate_backend_observation_timestamp(left, left_domain)
    validate_backend_observation_timestamp(right, right_domain)
    if left_domain.domain_id != right_domain.domain_id:
        raise IncomparableTimestampsError(
            "timestamps from different domains cannot be compared"
        )
    if left_domain.origin_id != right_domain.origin_id:
        raise IncomparableTimestampsError(
            "timestamps from different origins cannot be compared"
        )
    if left_domain != right_domain:
        raise IncomparableTimestampsError(
            "timestamp domain descriptors disagree within one identity"
        )
    return (left.value > right.value) - (left.value < right.value)


@dataclass(frozen=True, slots=True)
class LossObservability:
    """Base for normalized loss-observability variants."""


@dataclass(frozen=True, slots=True)
class UpstreamLossNotObservable(LossObservability):
    """States that this observer cannot report upstream UART loss."""


@dataclass(frozen=True, slots=True)
class ObserverReportsUartLoss(LossObservability):
    """Declares the observer and scope capable of reporting UART loss."""

    observer_id: str
    scope: str

    def __post_init__(self) -> None:
        _validate_observer_scope(self.observer_id, self.scope)


@dataclass(frozen=True, slots=True)
class BackendConnectionProvenance:
    """Opaque immutable connection details supplied by a backend adapter."""

    def to_snapshot(self) -> ConnectionProvenanceSnapshot:
        """Return the generic durable envelope supplied by the owning backend."""

        raise TypeError(
            f"{type(self).__name__} does not supply durable provenance"
        )


@dataclass(frozen=True, slots=True)
class PersistedConnectionProvenance(BackendConnectionProvenance):
    """Opaque provenance reconstructed from a supported durable envelope."""

    snapshot: ConnectionProvenanceSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, ConnectionProvenanceSnapshot):
            raise TypeError("persisted provenance requires a validated snapshot")

    def to_snapshot(self) -> ConnectionProvenanceSnapshot:
        return self.snapshot


@dataclass(frozen=True, slots=True)
class ConnectionDescriptor:
    capabilities: BackendCapabilities
    backend_observation_timestamp_domain: BackendObservationTimestampDomain
    loss_observability: LossObservability
    connection_provenance: BackendConnectionProvenance


@dataclass(frozen=True, slots=True)
class RxBytesObserved:
    payload: bytes
    observed_at: BackendObservationTimestamp

    def __post_init__(self) -> None:
        if not self.payload:
            raise ValueError("RX payload must be non-empty")


class ObserverLossCause(StrEnum):
    OVERFLOW = "overflow"
    OTHER_OBSERVED_LOSS = "other_observed_loss"


@dataclass(frozen=True, slots=True)
class ObserverLossObserved:
    observer_id: str
    scope: str
    cause: ObserverLossCause
    lost_bytes: int | None
    observed_at: BackendObservationTimestamp

    def __post_init__(self) -> None:
        _validate_observer_loss(
            self.observer_id,
            self.scope,
            self.cause,
            self.lost_bytes,
        )


@dataclass(frozen=True, slots=True)
class TimestampOriginReset:
    new_backend_observation_timestamp_domain: BackendObservationTimestampDomain


@dataclass(frozen=True, slots=True)
class Disconnected:
    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("disconnect reason must be non-empty")


type BackendEvent = (
    RxBytesObserved | ObserverLossObserved | TimestampOriginReset | Disconnected
)


@dataclass(frozen=True, slots=True)
class SegmentProvenance:
    connection_id: ConnectionInstanceId
    segment_id: SegmentId
    capabilities: BackendCapabilities
    backend_observation_timestamp_domain: BackendObservationTimestampDomain
    loss_observability: LossObservability
    connection_provenance: BackendConnectionProvenance


class SegmentEndReason(StrEnum):
    TIMESTAMP_ORIGIN_RESET = "timestamp_origin_reset"
    DISCONNECTED = "disconnected"
    EXPLICIT_STOP = "explicit_stop"
    RECORDING_FAILURE = "recording_failure"
    TRANSPORT_FAILURE = "transport_failure"


@dataclass(frozen=True, slots=True)
class SegmentStartedEvidence:
    sequence: int
    provenance: SegmentProvenance

    @property
    def connection_id(self) -> ConnectionInstanceId:
        return self.provenance.connection_id

    @property
    def segment_id(self) -> SegmentId:
        return self.provenance.segment_id


@dataclass(frozen=True, slots=True)
class RxBytesEvidence:
    sequence: int
    connection_id: ConnectionInstanceId
    segment_id: SegmentId
    payload: bytes
    observed_at: BackendObservationTimestamp


@dataclass(frozen=True, slots=True)
class ObserverLossEvidence:
    sequence: int
    connection_id: ConnectionInstanceId
    segment_id: SegmentId
    observer_id: str
    scope: str
    cause: ObserverLossCause
    lost_bytes: int | None
    observed_at: BackendObservationTimestamp

    def __post_init__(self) -> None:
        _validate_observer_loss(
            self.observer_id,
            self.scope,
            self.cause,
            self.lost_bytes,
        )


@dataclass(frozen=True, slots=True)
class SegmentEndedEvidence:
    sequence: int
    connection_id: ConnectionInstanceId
    segment_id: SegmentId
    reason: SegmentEndReason


type EvidenceRecord = (
    SegmentStartedEvidence
    | RxBytesEvidence
    | ObserverLossEvidence
    | SegmentEndedEvidence
    | OperationStartedEvidence
    | OperationEndedEvidence
    | ClientAnnotationEvidence
)


@dataclass(frozen=True, slots=True)
class SequenceRange:
    """A persisted half-open sequence interval."""

    start_inclusive: int
    end_exclusive: int

    def __post_init__(self) -> None:
        validate_persisted_counter(self.start_inclusive, name="range start")
        validate_persisted_counter(self.end_exclusive, name="range end")
        if self.start_inclusive > self.end_exclusive:
            raise ValueError("half-open range start must not exceed its end")

    @property
    def is_empty(self) -> bool:
        return self.start_inclusive == self.end_exclusive


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    session_id: SessionId
    sequence: int

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, SessionId):
            raise TypeError("evidence reference requires a session ID")
        validate_persisted_counter(self.sequence, name="evidence sequence")


@dataclass(frozen=True, slots=True)
class EvidenceRangeReference:
    session_id: SessionId
    start_inclusive: int
    end_exclusive: int

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, SessionId):
            raise TypeError("evidence range reference requires a session ID")
        SequenceRange(self.start_inclusive, self.end_exclusive)

    @property
    def is_empty(self) -> bool:
        return self.start_inclusive == self.end_exclusive


@dataclass(frozen=True, slots=True)
class RetentionTimestampEndpoint:
    """One discarded observation with its complete timestamp descriptor."""

    timestamp: BackendObservationTimestamp
    domain: BackendObservationTimestampDomain

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, BackendObservationTimestamp):
            raise TypeError("retention endpoint timestamp must be validated")
        if not isinstance(self.domain, BackendObservationTimestampDomain):
            raise TypeError("retention endpoint domain must be validated")
        validate_backend_observation_timestamp(self.timestamp, self.domain)


@dataclass(frozen=True, slots=True)
class RetentionMarker:
    expired_range: SequenceRange
    first_discarded_timestamp: RetentionTimestampEndpoint | None
    last_discarded_timestamp: RetentionTimestampEndpoint | None
    discarded_record_count: int
    discarded_rx_payload_byte_count: int
    discarded_charged_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.expired_range, SequenceRange):
            raise TypeError("retention marker requires a sequence range")
        if self.expired_range.start_inclusive != 0:
            raise ValueError("retention range must start at zero")
        if self.expired_range.is_empty:
            raise ValueError("retention range must contain discarded evidence")
        if self.discarded_record_count != self.expired_range.end_exclusive:
            raise ValueError("discarded record count must match the expired prefix")
        for endpoint in (
            self.first_discarded_timestamp,
            self.last_discarded_timestamp,
        ):
            if endpoint is not None and not isinstance(
                endpoint,
                RetentionTimestampEndpoint,
            ):
                raise TypeError("retention timestamp endpoint must be validated")
        if (self.first_discarded_timestamp is None) != (
            self.last_discarded_timestamp is None
        ):
            raise ValueError(
                "retention timestamp endpoints must both be present or absent"
            )
        for value, name in (
            (self.discarded_record_count, "discarded record count"),
            (
                self.discarded_rx_payload_byte_count,
                "discarded RX payload byte count",
            ),
            (self.discarded_charged_bytes, "discarded charged bytes"),
        ):
            validate_persisted_counter(value, name=name)


def _validate_observer_scope(observer_id: str, scope: str) -> None:
    if not isinstance(observer_id, str) or not observer_id:
        raise ValueError("loss observer ID must be non-empty")
    if not isinstance(scope, str) or not scope:
        raise ValueError("loss observer scope must be non-empty")


def _validate_observer_loss(
    observer_id: str,
    scope: str,
    cause: ObserverLossCause,
    lost_bytes: int | None,
) -> None:
    _validate_observer_scope(observer_id, scope)
    if not isinstance(cause, ObserverLossCause):
        raise TypeError("observer loss cause must be declared")
    if lost_bytes is None:
        return
    if type(lost_bytes) is not int:
        raise TypeError("lost-byte count must be an integer or absent")
    if lost_bytes <= 0:
        raise ValueError("lost-byte count must be positive when present")


class MonitorOutcome(StrEnum):
    MATCHED = "matched"
    TIMEOUT = "timeout"
    BYTE_LIMIT = "byte_limit"
    DISCONNECTED = "disconnected"
    DETACHED = "detached"
    TIMESTAMP_ORIGIN_RESET = "timestamp_origin_reset"
    RECORDING_FAILURE = "recording_failure"
    TRANSPORT_FAILURE = "transport_failure"
    SERVICE_STOPPING = "service_stopping"


def validate_monitor_uuid(value: str) -> None:
    """New operation/host-origin identities use canonical UUID spelling."""
    from uuid import UUID

    if type(value) is not str:
        raise TypeError("Monitor identity must be a UUID string")
    if str(UUID(value)) != value:
        raise ValueError("Monitor identity must be a canonical UUID")


def validate_monitor_bounds(
    condition: bytes, timeout_ms: int, max_rx_bytes: int
) -> None:
    if type(condition) is not bytes:
        raise TypeError("condition must be exact bytes")
    if not 1 <= len(condition) <= 256:
        raise ValueError("condition must contain 1..256 bytes")
    for value, maximum, name in (
        (timeout_ms, 4000, "timeout_ms"),
        (max_rx_bytes, 1048576, "max_rx_bytes"),
    ):
        validate_persisted_counter(value, name=name)
        if not 1 <= value <= maximum:
            raise ValueError(f"{name} is outside Monitor bounds")


@dataclass(frozen=True, slots=True)
class MonitorMatchStart:
    sequence: int
    byte_offset: int

    def __post_init__(self) -> None:
        validate_record_sequence(self.sequence)
        validate_persisted_counter(self.byte_offset, name="match start offset")


@dataclass(frozen=True, slots=True)
class MonitorMatchEnd:
    sequence: int
    byte_offset_exclusive: int

    def __post_init__(self) -> None:
        validate_record_sequence(self.sequence)
        _validate_positive_persisted_integer(
            self.byte_offset_exclusive, name="match end offset"
        )


@dataclass(frozen=True, slots=True)
class MonitorMatch:
    start: MonitorMatchStart
    end: MonitorMatchEnd

    def __post_init__(self) -> None:
        if not isinstance(self.start, MonitorMatchStart) or not isinstance(
            self.end, MonitorMatchEnd
        ):
            raise TypeError("match endpoints must be validated")
        if self.start.sequence > self.end.sequence or (
            self.start.sequence == self.end.sequence
            and self.start.byte_offset >= self.end.byte_offset_exclusive
        ):
            raise ValueError("match must be ordered and nonempty")


@dataclass(frozen=True, slots=True)
class MonitorClockFacts:
    origin_id: str
    started_at_ns: int
    deadline_at_ns: int
    decided_at_ns: int

    def __post_init__(self) -> None:
        validate_monitor_uuid(self.origin_id)
        for value in (self.started_at_ns, self.deadline_at_ns, self.decided_at_ns):
            validate_persisted_counter(value, name="host monotonic nanoseconds")
        if not self.started_at_ns < self.deadline_at_ns:
            raise ValueError("host start must precede deadline")
        if self.decided_at_ns < self.started_at_ns:
            raise ValueError("host decision must not precede start")


def validate_monitor_decision(
    start_sequence: int,
    window: SequenceRange,
    outcome: MonitorOutcome,
    examined_rx_bytes: int,
    observer_loss_records: int,
    match: MonitorMatch | None,
    clock: MonitorClockFacts,
) -> None:
    """Standalone structural facts, independent of retained paired records."""
    validate_record_sequence(start_sequence)
    if not isinstance(window, SequenceRange):
        raise TypeError("Monitor window must be validated")
    if window.start_inclusive != start_sequence + 1:
        raise ValueError("Monitor window must start after its start marker")
    if not isinstance(outcome, MonitorOutcome):
        raise TypeError("Monitor outcome must be declared")
    validate_persisted_counter(examined_rx_bytes, name="examined RX bytes")
    validate_persisted_counter(observer_loss_records, name="observed loss records")
    if examined_rx_bytes > 1048576:
        raise ValueError("examined RX exceeds Monitor bound")
    if (
        outcome in (MonitorOutcome.MATCHED, MonitorOutcome.BYTE_LIMIT)
        and not examined_rx_bytes
    ):
        raise ValueError("match/byte exhaustion requires examined RX")
    if not isinstance(clock, MonitorClockFacts):
        raise TypeError("Monitor clock facts must be validated")
    if (outcome is MonitorOutcome.TIMEOUT) != (
        clock.decided_at_ns >= clock.deadline_at_ns
    ):
        raise ValueError("Monitor decision disagrees with its deadline")
    if outcome is MonitorOutcome.MATCHED:
        if not isinstance(match, MonitorMatch):
            raise ValueError("matched outcome requires a match")
        if (
            not window.start_inclusive
            <= match.start.sequence
            <= match.end.sequence
            < window.end_exclusive
        ):
            raise ValueError("match endpoints must lie inside the frozen window")
    elif match is not None:
        raise ValueError("only matched outcome may contain a match")


@dataclass(frozen=True, slots=True)
class OperationStartedEvidence:
    sequence: int
    operation_id: str
    operation_kind: Literal["monitor"]
    provenance: SegmentProvenance
    timeout_ms: int
    max_rx_bytes: int
    clock_origin_id: str
    condition: bytes

    def __post_init__(self) -> None:
        validate_record_sequence(self.sequence)
        validate_monitor_uuid(self.operation_id)
        validate_monitor_uuid(self.clock_origin_id)
        if type(self.operation_kind) is not str or self.operation_kind != "monitor":
            raise ValueError("operation kind must be monitor")
        if not isinstance(self.provenance, SegmentProvenance):
            raise TypeError("operation requires actual segment provenance")
        validate_monitor_bounds(self.condition, self.timeout_ms, self.max_rx_bytes)


@dataclass(frozen=True, slots=True)
class OperationEndedEvidence:
    sequence: int
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
        validate_record_sequence(self.sequence)
        validate_monitor_uuid(self.operation_id)
        if type(self.operation_kind) is not str or self.operation_kind != "monitor":
            raise ValueError("operation kind must be monitor")
        validate_monitor_decision(
            self.start_sequence,
            self.window,
            self.outcome,
            self.examined_rx_bytes,
            self.observer_loss_records,
            self.match,
            self.clock,
        )


def validate_annotation_content(text: str, client_surface: str) -> None:
    """Bound exact client prose without interpreting or normalizing it."""
    if type(text) is not str or type(client_surface) is not str:
        raise TypeError("annotation text and surface must be exact strings")
    if client_surface not in {"cli", "http", "core"}:
        raise ValueError("annotation surface must be declared")
    if "\x00" in text or not 1 <= len(text.encode("utf-8")) <= 1024:
        raise ValueError("annotation text must be 1..1024 UTF-8 bytes without NUL")


@dataclass(frozen=True, slots=True)
class ClientAnnotationEvidence:
    """Session-level client assertion with host receipt time, never UART RX."""

    sequence: int
    text: str
    client_surface: str
    clock_origin_id: str
    received_at_ns: int

    def __post_init__(self) -> None:
        validate_record_sequence(self.sequence)
        validate_annotation_content(self.text, self.client_surface)
        validate_monitor_uuid(self.clock_origin_id)
        validate_persisted_counter(self.received_at_ns, name="annotation receipt time")

    @property
    def assertion_class(self) -> Literal["client_assertion"]:
        return "client_assertion"

    @property
    def attribution_basis(self) -> Literal["client_asserted"]:
        return "client_asserted"
