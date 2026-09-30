"""Normalized backend and evidence values for authoritative UART RX."""

from dataclasses import dataclass
from enum import StrEnum


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
)


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
