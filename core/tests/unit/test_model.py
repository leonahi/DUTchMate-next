"""Domain-model contracts for the continuous RX evidence foundation."""

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from dutchmate_core.model import (
    BackendCapabilities,
    BackendCapability,
    BackendConnectionProvenance,
    BackendObservationTimestamp,
    BackendObservationTimestampDomain,
    ConnectionDescriptor,
    ConnectionInstanceId,
    IncomparableTimestampsError,
    ObserverLossCause,
    ObserverLossObserved,
    ObserverReportsUartLoss,
    RxBytesObserved,
    SegmentId,
    TimestampMeaning,
    TimestampObserver,
    TimestampUnit,
    UpstreamLossNotObservable,
    compare_backend_observation_timestamps,
)

type OpaqueIdentifierType = type[ConnectionInstanceId] | type[SegmentId]


def _host_observation_timestamp() -> BackendObservationTimestamp:
    return BackendObservationTimestamp(
        domain_id="host-observer-1",
        value=17,
    )


def _timestamp_domain(
    *,
    domain_id: str = "host-observer-1",
    observer: TimestampObserver = TimestampObserver.HOST,
    meaning: TimestampMeaning = TimestampMeaning.OBSERVATION,
    unit: TimestampUnit = TimestampUnit.NANOSECOND,
    origin_id: str = "host-process-1",
) -> BackendObservationTimestampDomain:
    return BackendObservationTimestampDomain(
        domain_id=domain_id,
        observer=observer,
        meaning=meaning,
        unit=unit,
        origin_id=origin_id,
    )


def test_capabilities_are_an_immutable_reported_set() -> None:
    capabilities = BackendCapabilities(
        frozenset(
            {
                BackendCapability.UART_RECEIVE,
                BackendCapability.GPIO_EVENTS,
            }
        )
    )

    assert capabilities.values == frozenset(
        {
            BackendCapability.UART_RECEIVE,
            BackendCapability.GPIO_EVENTS,
        }
    )
    assert isinstance(hash(capabilities), int)
    assert capabilities.supports(BackendCapability.UART_RECEIVE)
    assert not capabilities.supports(BackendCapability.UART_SEND)


def test_connection_descriptor_stores_immutable_opaque_provenance() -> None:
    connection_provenance = BackendConnectionProvenance()
    descriptor = ConnectionDescriptor(
        capabilities=BackendCapabilities(
            frozenset({BackendCapability.UART_RECEIVE})
        ),
        backend_observation_timestamp_domain=_timestamp_domain(),
        loss_observability=UpstreamLossNotObservable(),
        connection_provenance=connection_provenance,
    )

    assert descriptor.connection_provenance is connection_provenance
    with pytest.raises(FrozenInstanceError):
        descriptor.connection_provenance = (  # type: ignore[misc]
            BackendConnectionProvenance()
        )


@pytest.mark.parametrize("identifier_type", [ConnectionInstanceId, SegmentId])
def test_opaque_identifier_rejects_an_empty_value(
    identifier_type: OpaqueIdentifierType,
) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        identifier_type("")


@pytest.mark.parametrize("identifier_type", [ConnectionInstanceId, SegmentId])
def test_opaque_identifier_preserves_its_value(
    identifier_type: OpaqueIdentifierType,
) -> None:
    identifier = identifier_type("opaque/value:17")

    assert identifier.value == "opaque/value:17"


def test_rx_observation_rejects_an_empty_payload() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        RxBytesObserved(
            payload=b"",
            observed_at=_host_observation_timestamp(),
        )


def test_rx_observation_preserves_every_byte_exactly() -> None:
    payload = bytes(range(256)) + b"\x00\x80\xfe\xff"

    observation = RxBytesObserved(
        payload=payload,
        observed_at=_host_observation_timestamp(),
    )

    assert observation.payload == payload
    assert observation.payload is payload


def _observer_loss_observation(*, lost_bytes: int | None) -> ObserverLossObserved:
    return ObserverLossObserved(
        observer_id="fixture-observer",
        scope="fixture-uart-buffer",
        cause=ObserverLossCause.OVERFLOW,
        lost_bytes=lost_bytes,
        observed_at=_host_observation_timestamp(),
    )


def test_observer_loss_distinguishes_unknown_from_a_positive_count() -> None:
    unknown = _observer_loss_observation(lost_bytes=None)
    counted = _observer_loss_observation(lost_bytes=23)

    assert unknown.lost_bytes is None
    assert counted.lost_bytes == 23


@pytest.mark.parametrize("lost_bytes", [0, -1])
def test_observer_loss_rejects_non_positive_counts(lost_bytes: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        _observer_loss_observation(lost_bytes=lost_bytes)


@pytest.mark.parametrize(
    ("observer_id", "scope"),
    [("", "fixture-uart-buffer"), ("fixture-observer", "")],
)
def test_reported_loss_observability_requires_observer_and_scope(
    observer_id: str,
    scope: str,
) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        ObserverReportsUartLoss(observer_id=observer_id, scope=scope)


@pytest.mark.parametrize(
    ("observer_id", "scope"),
    [("", "fixture-uart-buffer"), ("fixture-observer", "")],
)
def test_observer_loss_event_requires_observer_and_scope(
    observer_id: str,
    scope: str,
) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        ObserverLossObserved(
            observer_id=observer_id,
            scope=scope,
            cause=ObserverLossCause.OVERFLOW,
            lost_bytes=None,
            observed_at=_host_observation_timestamp(),
        )


@pytest.mark.parametrize(
    "observer",
    [TimestampObserver.HOST, TimestampObserver.DEVICE],
)
def test_timestamp_domain_accepts_only_declared_observers(
    observer: TimestampObserver,
) -> None:
    assert _timestamp_domain(observer=observer).observer is observer

    with pytest.raises(TypeError, match="observer"):
        _timestamp_domain(observer=cast("TimestampObserver", "backend"))


def test_timestamp_domain_accepts_only_observation_meaning() -> None:
    assert _timestamp_domain().meaning is TimestampMeaning.OBSERVATION

    with pytest.raises(TypeError, match="meaning"):
        _timestamp_domain(meaning=cast("TimestampMeaning", "emission"))


@pytest.mark.parametrize(
    "unit",
    [TimestampUnit.NANOSECOND, TimestampUnit.MICROSECOND, TimestampUnit.TICK],
)
def test_timestamp_domain_accepts_only_declared_units(unit: TimestampUnit) -> None:
    assert _timestamp_domain(unit=unit).unit is unit

    with pytest.raises(TypeError, match="unit"):
        _timestamp_domain(unit=cast("TimestampUnit", "second"))


def test_timestamp_domain_requires_opaque_non_empty_domain_and_origin_ids() -> None:
    domain = _timestamp_domain(
        domain_id="opaque/domain:17",
        origin_id="opaque/origin:23",
    )
    assert domain.domain_id == "opaque/domain:17"
    assert domain.origin_id == "opaque/origin:23"

    with pytest.raises(ValueError, match="domain ID.*non-empty"):
        _timestamp_domain(domain_id="")
    with pytest.raises(ValueError, match="origin ID.*non-empty"):
        _timestamp_domain(origin_id="")


def test_observation_timestamp_requires_a_non_negative_integer() -> None:
    assert BackendObservationTimestamp(domain_id="domain-1", value=0).value == 0

    with pytest.raises(ValueError, match="non-negative"):
        BackendObservationTimestamp(domain_id="domain-1", value=-1)


def test_same_domain_and_origin_timestamps_can_be_compared() -> None:
    domain = _timestamp_domain()
    earlier = BackendObservationTimestamp(domain_id=domain.domain_id, value=4)
    later = BackendObservationTimestamp(domain_id=domain.domain_id, value=9)
    equal = BackendObservationTimestamp(domain_id=domain.domain_id, value=4)

    assert compare_backend_observation_timestamps(earlier, domain, later, domain) == -1
    assert compare_backend_observation_timestamps(later, domain, earlier, domain) == 1
    assert compare_backend_observation_timestamps(earlier, domain, equal, domain) == 0


def test_cross_domain_timestamp_comparison_is_rejected() -> None:
    left_domain = _timestamp_domain(domain_id="domain-left")
    right_domain = _timestamp_domain(domain_id="domain-right")
    left = BackendObservationTimestamp(domain_id="domain-left", value=10)
    right = BackendObservationTimestamp(domain_id="domain-right", value=11)

    with pytest.raises(IncomparableTimestampsError, match="domain"):
        compare_backend_observation_timestamps(
            left,
            left_domain,
            right,
            right_domain,
        )


def test_cross_origin_timestamp_comparison_is_rejected() -> None:
    left_domain = _timestamp_domain(origin_id="origin-left")
    right_domain = _timestamp_domain(origin_id="origin-right")
    left = BackendObservationTimestamp(domain_id="host-observer-1", value=10)
    right = BackendObservationTimestamp(domain_id="host-observer-1", value=11)

    with pytest.raises(IncomparableTimestampsError, match="origin"):
        compare_backend_observation_timestamps(
            left,
            left_domain,
            right,
            right_domain,
        )
