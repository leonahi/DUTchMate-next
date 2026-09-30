"""Continuous acquisition tests over the normalized backend boundary."""

import asyncio

import pytest

from dutchmate_core.acquisition import (
    Acquisition,
    AcquisitionAlreadyActiveError,
    AcquisitionFailureKind,
    AcquisitionState,
    UnsupportedBackendCapabilityError,
)
from dutchmate_core.evidence import InMemoryEvidenceRecorder
from dutchmate_core.model import (
    BackendCapabilities,
    BackendConnectionProvenance,
    BackendObservationTimestampDomain,
    InvalidTimestampOriginResetError,
    ObserverLossCause,
    ObserverLossEvidence,
    ObserverLossProvenanceMismatchError,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentEndReason,
    SegmentStartedEvidence,
    TimestampDomainMismatchError,
    TimestampMeaning,
    TimestampObserver,
    TimestampRegressionError,
    TimestampUnit,
    UpstreamLossNotObservable,
)
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixtureFactory,
    BasicShapedBackend,
    BasicShapedBackendConnection,
    BlockingCloseBackendConnection,
    BlockingFailingCloseBackendConnection,
    EnhancedShapedBackend,
    EnhancedShapedBackendConnection,
    FailingCloseBackendConnection,
    FailingOpenBackend,
    FixtureBackendOpenFailure,
    FixtureConnectionCloseFailure,
    FixtureRecorderFailure,
    RejectingEvidenceRecorder,
)


async def _wait_for_termination(acquisition: Acquisition) -> AcquisitionState:
    return await asyncio.wait_for(acquisition.wait_terminated(), timeout=1.0)


def _host_timestamp_domain(
    domain_id: str,
    origin_id: str,
) -> BackendObservationTimestampDomain:
    return BackendObservationTimestampDomain(
        domain_id=domain_id,
        observer=TimestampObserver.HOST,
        meaning=TimestampMeaning.OBSERVATION,
        unit=TimestampUnit.NANOSECOND,
        origin_id=origin_id,
    )


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_acquisition_records_rx_on_both_sides_of_an_idle_period(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(fixture.backend)

    await connection.emit_rx(b"before idle", timestamp=1)
    await asyncio.sleep(0)
    assert acquisition.state is AcquisitionState.ACQUIRING
    await connection.emit_rx(b"after idle", timestamp=2)
    await connection.disconnect()
    await _wait_for_termination(acquisition)

    rx_records = [
        record for record in recorder.snapshot() if isinstance(record, RxBytesEvidence)
    ]
    assert [record.payload for record in rx_records] == [b"before idle", b"after idle"]


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_second_start_is_rejected_without_disturbing_active_rx(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    backend = fixture.backend
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(backend)

    with pytest.raises(AcquisitionAlreadyActiveError):
        await acquisition.start(backend)

    await connection.emit_rx(b"still authoritative", timestamp=3)
    await connection.disconnect()
    await _wait_for_termination(acquisition)
    rx_records = [
        record for record in recorder.snapshot() if isinstance(record, RxBytesEvidence)
    ]
    assert [record.payload for record in rx_records] == [b"still authoritative"]


@pytest.mark.asyncio
async def test_restart_is_rejected_until_previous_close_completes() -> None:
    first_connection = BlockingCloseBackendConnection()
    second_connection = BasicShapedBackendConnection()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(first_connection))

    await first_connection.disconnect("first complete")
    await asyncio.wait_for(first_connection.close_started.wait(), timeout=1.0)

    try:
        assert acquisition.state is AcquisitionState.STOPPING
        with pytest.raises(AcquisitionAlreadyActiveError):
            await acquisition.start(BasicShapedBackend(second_connection))
    finally:
        first_connection.allow_close.set()

    assert await _wait_for_termination(acquisition) is AcquisitionState.STOPPED

    await acquisition.start(BasicShapedBackend(second_connection))
    await second_connection.disconnect("second complete")
    assert await _wait_for_termination(acquisition) is AcquisitionState.STOPPED


@pytest.mark.asyncio
async def test_open_failure_terminates_without_evidence_and_allows_retry() -> None:
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    failing_backend = FailingOpenBackend()

    with pytest.raises(FixtureBackendOpenFailure) as raised:
        await acquisition.start(failing_backend)

    assert raised.value is failing_backend.failure
    assert acquisition.state is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.TRANSPORT_FAILURE
    assert acquisition.failure.cause is failing_backend.failure
    assert recorder.snapshot() == ()
    assert await _wait_for_termination(acquisition) is AcquisitionState.FAILED

    connection = BasicShapedBackendConnection()
    await acquisition.start(BasicShapedBackend(connection))
    await connection.disconnect("retry complete")
    assert await _wait_for_termination(acquisition) is AcquisitionState.STOPPED


@pytest.mark.asyncio
async def test_unexpected_stream_end_explicitly_closes_segment_as_failure() -> None:
    connection = BasicShapedBackendConnection()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))

    await connection.emit_rx(b"preserved", timestamp=1)
    await connection.end_stream_unexpectedly()
    state = await _wait_for_termination(acquisition)

    assert state is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.TRANSPORT_FAILURE
    records = recorder.snapshot()
    assert [record.sequence for record in records] == [0, 1, 2]
    assert [type(record) for record in records] == [
        SegmentStartedEvidence,
        RxBytesEvidence,
        SegmentEndedEvidence,
    ]
    preserved = records[1]
    assert isinstance(preserved, RxBytesEvidence)
    assert preserved.payload == b"preserved"
    segment_end = records[2]
    assert isinstance(segment_end, SegmentEndedEvidence)
    assert segment_end.reason is SegmentEndReason.TRANSPORT_FAILURE


@pytest.mark.asyncio
async def test_primary_failure_survives_blocking_close_failure() -> None:
    connection = BlockingFailingCloseBackendConnection()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))

    await connection.emit_rx(
        b"wrong-domain",
        timestamp=1,
        domain_id="foreign-domain",
    )
    await asyncio.wait_for(connection.close_started.wait(), timeout=1.0)

    try:
        assert acquisition.state is AcquisitionState.STOPPING
    finally:
        connection.allow_close_failure.set()

    assert await _wait_for_termination(acquisition) is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.TRANSPORT_FAILURE
    assert isinstance(acquisition.failure.cause, TimestampDomainMismatchError)

    with pytest.raises(AcquisitionAlreadyActiveError):
        await acquisition.start(BasicShapedBackend())


@pytest.mark.asyncio
async def test_disconnect_close_failure_is_terminal_without_duplicate_end() -> None:
    connection = FailingCloseBackendConnection()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))

    await connection.disconnect("observed disconnect")
    assert await _wait_for_termination(acquisition) is AcquisitionState.FAILED

    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.TRANSPORT_FAILURE
    assert isinstance(acquisition.failure.cause, FixtureConnectionCloseFailure)
    records = recorder.snapshot()
    assert [type(record) for record in records] == [
        SegmentStartedEvidence,
        SegmentEndedEvidence,
    ]
    segment_end = records[1]
    assert isinstance(segment_end, SegmentEndedEvidence)
    assert segment_end.reason is SegmentEndReason.DISCONNECTED
    with pytest.raises(AcquisitionAlreadyActiveError):
        await acquisition.start(BasicShapedBackend())


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_arbitrary_chunking_reconstructs_every_byte_with_provenance(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    connection_id = await acquisition.start(fixture.backend)
    payload = bytes(range(256)) + b"\x00\x80\xfe\xff"
    chunks = [payload[:1], payload[1:31], payload[31:200], payload[200:]]

    for timestamp, chunk in enumerate(chunks, start=40):
        await connection.emit_rx(chunk, timestamp=timestamp)
    await connection.disconnect("fixture complete")
    await _wait_for_termination(acquisition)

    records = recorder.snapshot()
    rx_records = [record for record in records if isinstance(record, RxBytesEvidence)]
    assert b"".join(record.payload for record in rx_records) == payload
    assert [record.sequence for record in records] == list(range(len(records)))
    assert {record.connection_id for record in records} == {connection_id}
    assert len({record.segment_id for record in records}) == 1
    assert {record.observed_at.domain_id for record in rx_records} == {
        connection.descriptor.backend_observation_timestamp_domain.domain_id
    }
    assert isinstance(records[0], SegmentStartedEvidence)
    segment_end = records[-1]
    assert isinstance(segment_end, SegmentEndedEvidence)
    assert segment_end.reason is SegmentEndReason.DISCONNECTED


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_segment_preserves_reported_loss_observability_without_lossless_claim(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(fixture.backend)

    await fixture.connection.emit_rx(b"no loss report", timestamp=1)
    await fixture.connection.disconnect()
    await _wait_for_termination(acquisition)

    records = recorder.snapshot()
    segment_start = records[0]
    assert isinstance(segment_start, SegmentStartedEvidence)
    assert (
        segment_start.provenance.loss_observability
        == fixture.connection.descriptor.loss_observability
    )
    assert not any(isinstance(record, ObserverLossEvidence) for record in records)


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_segment_copies_connection_provenance_without_backend_branching(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(fixture.backend)

    await fixture.connection.disconnect()
    await _wait_for_termination(acquisition)

    segment_start = recorder.snapshot()[0]
    assert isinstance(segment_start, SegmentStartedEvidence)
    assert (
        segment_start.provenance.connection_provenance
        is fixture.connection.descriptor.connection_provenance
    )


@pytest.mark.asyncio
async def test_origin_reset_preserves_the_same_opaque_connection_provenance() -> None:
    connection_provenance = BackendConnectionProvenance()
    initial_domain = _host_timestamp_domain("host-domain-1", "host-origin-1")
    reset_domain = _host_timestamp_domain("host-domain-2", "host-origin-2")
    connection = BasicShapedBackendConnection(
        timestamp_domain=initial_domain,
        connection_provenance=connection_provenance,
    )
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))

    await connection.reset_timestamp_origin(reset_domain)
    await connection.disconnect()
    await _wait_for_termination(acquisition)

    segment_starts = [
        record
        for record in recorder.snapshot()
        if isinstance(record, SegmentStartedEvidence)
    ]
    assert len(segment_starts) == 2
    assert all(
        record.provenance.connection_provenance is connection_provenance
        for record in segment_starts
    )


@pytest.mark.asyncio
async def test_basic_absence_of_loss_reports_remains_explicitly_unobservable() -> None:
    connection = BasicShapedBackendConnection()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))

    await connection.emit_rx(b"observed bytes", timestamp=1)
    await connection.disconnect()
    await _wait_for_termination(acquisition)

    segment_start = recorder.snapshot()[0]
    assert isinstance(segment_start, SegmentStartedEvidence)
    assert isinstance(
        segment_start.provenance.loss_observability,
        UpstreamLossNotObservable,
    )


@pytest.mark.asyncio
async def test_enhanced_shaped_counted_overflow_is_ordered_scoped_evidence() -> None:
    connection = EnhancedShapedBackendConnection()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(EnhancedShapedBackend(connection))

    await connection.emit_rx(b"before", timestamp=40)
    await connection.emit_observer_loss(
        cause="overflow",
        lost_bytes=23,
        timestamp=41,
    )
    await connection.emit_rx(b"after", timestamp=42)
    await connection.disconnect()
    await _wait_for_termination(acquisition)

    records = recorder.snapshot()
    assert [type(record) for record in records] == [
        SegmentStartedEvidence,
        RxBytesEvidence,
        ObserverLossEvidence,
        RxBytesEvidence,
        SegmentEndedEvidence,
    ]
    loss_record = records[2]
    assert isinstance(loss_record, ObserverLossEvidence)
    assert loss_record.sequence == 2
    assert loss_record.observer_id == connection.OBSERVER_ID
    assert loss_record.scope == connection.LOSS_SCOPE
    assert loss_record.cause is ObserverLossCause.OVERFLOW
    assert loss_record.lost_bytes == 23
    assert loss_record.observed_at.value == 41
    assert (
        loss_record.observed_at.domain_id
        == connection.descriptor.backend_observation_timestamp_domain.domain_id
    )
    assert (
        connection.descriptor.backend_observation_timestamp_domain.observer
        is TimestampObserver.DEVICE
    )


@pytest.mark.parametrize(
    ("observer_id", "scope"),
    [
        ("wrong-observer", EnhancedShapedBackendConnection.LOSS_SCOPE),
        (EnhancedShapedBackendConnection.OBSERVER_ID, "wrong-scope"),
    ],
)
@pytest.mark.asyncio
async def test_observer_loss_must_match_current_observer_scope(
    observer_id: str,
    scope: str,
) -> None:
    connection = EnhancedShapedBackendConnection()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(EnhancedShapedBackend(connection))

    await connection.emit_observer_loss(
        cause="overflow",
        lost_bytes=5,
        timestamp=7,
        observer_id=observer_id,
        scope=scope,
    )
    state = await _wait_for_termination(acquisition)

    assert state is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.TRANSPORT_FAILURE
    assert isinstance(acquisition.failure.cause, ObserverLossProvenanceMismatchError)
    assert [type(record) for record in recorder.snapshot()] == [
        SegmentStartedEvidence,
        SegmentEndedEvidence,
    ]


@pytest.mark.asyncio
async def test_observer_loss_must_use_the_current_timestamp_domain() -> None:
    connection = EnhancedShapedBackendConnection()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(EnhancedShapedBackend(connection))

    await connection.emit_observer_loss(
        cause="overflow",
        lost_bytes=None,
        timestamp=7,
        domain_id="stale-device-domain",
    )
    state = await _wait_for_termination(acquisition)

    assert state is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.TRANSPORT_FAILURE
    assert isinstance(acquisition.failure.cause, TimestampDomainMismatchError)
    assert [type(record) for record in recorder.snapshot()] == [
        SegmentStartedEvidence,
        SegmentEndedEvidence,
    ]


@pytest.mark.asyncio
async def test_acquisition_rejects_backend_without_uart_receive_capability() -> None:
    connection = BasicShapedBackendConnection(
        capabilities=BackendCapabilities(frozenset())
    )
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    try:
        with pytest.raises(UnsupportedBackendCapabilityError):
            await acquisition.start(BasicShapedBackend(connection))
    finally:
        await acquisition.stop()

    assert acquisition.state is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert (
        acquisition.failure.kind is AcquisitionFailureKind.CAPABILITY_REJECTION
    )
    assert recorder.snapshot() == ()
    assert connection.closed


@pytest.mark.asyncio
async def test_recorder_failure_is_explicit_and_stops_acquisition() -> None:
    connection = BasicShapedBackendConnection()
    recorder = RejectingEvidenceRecorder(reject_append_number=2)
    acquisition = Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))

    await connection.emit_rx(b"cannot record", timestamp=50)
    state = await _wait_for_termination(acquisition)

    assert state is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.RECORDING_FAILURE
    assert isinstance(acquisition.failure.cause, FixtureRecorderFailure)
    assert connection.closed
    assert len(recorder.snapshot()) == 1
    assert isinstance(recorder.snapshot()[0], SegmentStartedEvidence)


@pytest.mark.asyncio
async def test_initial_segment_record_failure_closes_the_connection() -> None:
    connection = BasicShapedBackendConnection()
    recorder = RejectingEvidenceRecorder(reject_append_number=1)
    acquisition = Acquisition(recorder)

    with pytest.raises(FixtureRecorderFailure):
        await acquisition.start(BasicShapedBackend(connection))

    assert acquisition.state is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.RECORDING_FAILURE
    assert connection.closed
    assert recorder.snapshot() == ()


@pytest.mark.asyncio
async def test_stop_is_idempotent_and_records_an_explicit_segment_end() -> None:
    connection = BasicShapedBackendConnection()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))

    first_result = await acquisition.stop()
    second_result = await acquisition.stop()

    assert first_result is AcquisitionState.STOPPED
    assert second_result is AcquisitionState.STOPPED
    assert connection.closed
    segment_end = recorder.snapshot()[-1]
    assert isinstance(segment_end, SegmentEndedEvidence)
    assert segment_end.reason is SegmentEndReason.EXPLICIT_STOP


@pytest.mark.asyncio
async def test_decreasing_rx_timestamp_is_terminal_before_payload_is_recorded() -> None:
    connection = BasicShapedBackendConnection()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))

    await connection.emit_rx(b"recorded", timestamp=20)
    await connection.emit_rx(b"timestamp-regression", timestamp=19)
    await connection.disconnect("fixture complete")
    state = await _wait_for_termination(acquisition)

    assert state is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.TRANSPORT_FAILURE
    assert isinstance(acquisition.failure.cause, TimestampRegressionError)
    records = recorder.snapshot()
    assert [record.sequence for record in records] == [0, 1, 2]
    assert [type(record) for record in records] == [
        SegmentStartedEvidence,
        RxBytesEvidence,
        SegmentEndedEvidence,
    ]
    recorded_rx = records[1]
    assert isinstance(recorded_rx, RxBytesEvidence)
    assert recorded_rx.payload == b"recorded"
    segment_end = records[2]
    assert isinstance(segment_end, SegmentEndedEvidence)
    assert segment_end.reason is SegmentEndReason.TRANSPORT_FAILURE


@pytest.mark.asyncio
async def test_recorded_loss_timestamp_is_the_baseline_for_later_rx() -> None:
    connection = EnhancedShapedBackendConnection()
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(EnhancedShapedBackend(connection))

    await connection.emit_observer_loss(
        cause="overflow",
        lost_bytes=3,
        timestamp=20,
    )
    await connection.emit_rx(b"timestamp-regression", timestamp=19)
    await connection.disconnect("fixture complete")
    state = await _wait_for_termination(acquisition)

    assert state is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.TRANSPORT_FAILURE
    assert [type(record) for record in recorder.snapshot()] == [
        SegmentStartedEvidence,
        ObserverLossEvidence,
        SegmentEndedEvidence,
    ]


@pytest.mark.asyncio
async def test_origin_reset_orders_equal_timestamps_by_sequence_and_segments() -> None:
    initial_domain = _host_timestamp_domain("host-domain-1", "host-origin-1")
    reset_domain = _host_timestamp_domain("host-domain-2", "host-origin-2")
    connection = BasicShapedBackendConnection(timestamp_domain=initial_domain)
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    connection_id = await acquisition.start(BasicShapedBackend(connection))

    await connection.emit_rx(b"first", timestamp=7)
    await connection.emit_rx(b"second", timestamp=7)
    await connection.reset_timestamp_origin(reset_domain)
    await connection.emit_rx(b"after-reset", timestamp=1)
    await connection.disconnect("fixture complete")
    await _wait_for_termination(acquisition)

    records = recorder.snapshot()
    assert [record.sequence for record in records] == list(range(7))
    assert [type(record) for record in records] == [
        SegmentStartedEvidence,
        RxBytesEvidence,
        RxBytesEvidence,
        SegmentEndedEvidence,
        SegmentStartedEvidence,
        RxBytesEvidence,
        SegmentEndedEvidence,
    ]
    first_start = records[0]
    first_end = records[3]
    second_start = records[4]
    second_end = records[6]
    assert isinstance(first_start, SegmentStartedEvidence)
    assert isinstance(first_end, SegmentEndedEvidence)
    assert isinstance(second_start, SegmentStartedEvidence)
    assert isinstance(second_end, SegmentEndedEvidence)
    assert first_start.connection_id == connection_id
    assert second_start.connection_id == connection_id
    assert first_start.segment_id != second_start.segment_id
    assert first_start.provenance.backend_observation_timestamp_domain == initial_domain
    assert second_start.provenance.backend_observation_timestamp_domain == reset_domain
    assert first_end.reason is SegmentEndReason.TIMESTAMP_ORIGIN_RESET
    assert second_end.reason is SegmentEndReason.DISCONNECTED
    rx_records = [record for record in records if isinstance(record, RxBytesEvidence)]
    assert [record.payload for record in rx_records] == [
        b"first",
        b"second",
        b"after-reset",
    ]
    assert [record.observed_at.value for record in rx_records] == [7, 7, 1]


@pytest.mark.parametrize(
    ("reset_domain_id", "reset_origin_id"),
    [
        ("current-domain", "new-origin"),
        ("new-domain", "current-origin"),
    ],
)
@pytest.mark.asyncio
async def test_origin_reset_requires_a_new_domain_and_origin(
    reset_domain_id: str,
    reset_origin_id: str,
) -> None:
    current_domain = _host_timestamp_domain(
        "current-domain",
        "current-origin",
    )
    reset_domain = _host_timestamp_domain(reset_domain_id, reset_origin_id)
    connection = BasicShapedBackendConnection(timestamp_domain=current_domain)
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))

    await connection.reset_timestamp_origin(reset_domain)
    await connection.disconnect()
    state = await _wait_for_termination(acquisition)

    assert state is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert isinstance(
        acquisition.failure.cause,
        InvalidTimestampOriginResetError,
    )
    records = recorder.snapshot()
    assert [type(record) for record in records] == [
        SegmentStartedEvidence,
        SegmentEndedEvidence,
    ]
    segment_end = records[-1]
    assert isinstance(segment_end, SegmentEndedEvidence)
    assert segment_end.reason is SegmentEndReason.TRANSPORT_FAILURE


@pytest.mark.asyncio
async def test_rx_outside_current_timestamp_domain_is_terminal_failure() -> None:
    connection = BasicShapedBackendConnection(
        timestamp_domain=_host_timestamp_domain("current-domain", "origin-1")
    )
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))

    await connection.emit_rx(
        b"wrong-domain",
        timestamp=12,
        domain_id="unknown-domain",
    )
    await connection.disconnect()
    state = await _wait_for_termination(acquisition)

    assert state is AcquisitionState.FAILED
    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.TRANSPORT_FAILURE
    assert isinstance(acquisition.failure.cause, TimestampDomainMismatchError)
    assert connection.closed
    records = recorder.snapshot()
    assert [type(record) for record in records] == [
        SegmentStartedEvidence,
        SegmentEndedEvidence,
    ]
    segment_end = records[-1]
    assert isinstance(segment_end, SegmentEndedEvidence)
    assert segment_end.reason is SegmentEndReason.TRANSPORT_FAILURE


@pytest.mark.asyncio
async def test_stale_prior_connection_domain_is_not_retagged_to_current() -> None:
    first_domain = _host_timestamp_domain("first-domain", "first-origin")
    second_domain = _host_timestamp_domain("second-domain", "second-origin")
    first_connection = BasicShapedBackendConnection(timestamp_domain=first_domain)
    second_connection = BasicShapedBackendConnection(timestamp_domain=second_domain)
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)

    first_connection_id = await acquisition.start(BasicShapedBackend(first_connection))
    await first_connection.disconnect("first complete")
    await _wait_for_termination(acquisition)
    second_connection_id = await acquisition.start(
        BasicShapedBackend(second_connection)
    )
    await second_connection.emit_rx(
        b"stale-prior-connection",
        timestamp=3,
        domain_id=first_domain.domain_id,
    )
    await second_connection.disconnect("second complete")
    state = await _wait_for_termination(acquisition)

    assert state is AcquisitionState.FAILED
    assert first_connection_id != second_connection_id
    records = recorder.snapshot()
    assert not any(
        isinstance(record, RxBytesEvidence)
        and record.payload == b"stale-prior-connection"
        for record in records
    )
    starts = [
        record for record in records if isinstance(record, SegmentStartedEvidence)
    ]
    assert [record.connection_id for record in starts] == [
        first_connection_id,
        second_connection_id,
    ]
    final_record = records[-1]
    assert isinstance(final_record, SegmentEndedEvidence)
    assert final_record.connection_id == second_connection_id
    assert final_record.reason is SegmentEndReason.TRANSPORT_FAILURE
