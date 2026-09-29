"""Evidence-journal contracts for authoritative ordering and exact bytes."""

import asyncio
from typing import cast

import pytest

from dutchmate_core.evidence import (
    InMemoryEvidenceRecorder,
    PendingEvidenceRecord,
    PendingObserverLossEvidence,
    PendingRxBytesEvidence,
    PendingSegmentStartedEvidence,
)
from dutchmate_core.model import (
    BackendCapabilities,
    BackendCapability,
    BackendObservationTimestamp,
    BackendObservationTimestampDomain,
    ConnectionInstanceId,
    ObserverLossCause,
    ObserverLossEvidence,
    RxBytesEvidence,
    SegmentId,
    SegmentProvenance,
    TimestampMeaning,
    TimestampObserver,
    TimestampUnit,
    UpstreamLossNotObservable,
)


def _provenance() -> SegmentProvenance:
    return SegmentProvenance(
        connection_id=ConnectionInstanceId("connection-1"),
        segment_id=SegmentId("segment-1"),
        capabilities=BackendCapabilities(frozenset({BackendCapability.UART_RECEIVE})),
        backend_observation_timestamp_domain=BackendObservationTimestampDomain(
            domain_id="host-observer-1",
            observer=TimestampObserver.HOST,
            meaning=TimestampMeaning.OBSERVATION,
            unit=TimestampUnit.NANOSECOND,
            origin_id="host-process-1",
        ),
        loss_observability=UpstreamLossNotObservable(),
    )


def _rx_draft(value: int) -> PendingRxBytesEvidence:
    return PendingRxBytesEvidence(
        connection_id=ConnectionInstanceId("connection-1"),
        segment_id=SegmentId("segment-1"),
        payload=bytes([value]),
        observed_at=BackendObservationTimestamp(
            domain_id="host-observer-1",
            value=value,
        ),
    )


@pytest.mark.asyncio
async def test_concurrent_appends_assign_one_consecutive_sequence() -> None:
    recorder = InMemoryEvidenceRecorder()

    records = await asyncio.gather(
        *(recorder.append(_rx_draft(value)) for value in range(16))
    )

    assert sorted(record.sequence for record in records) == list(range(16))
    assert [record.sequence for record in recorder.snapshot()] == list(range(16))


@pytest.mark.asyncio
async def test_snapshot_is_an_immutable_point_in_time() -> None:
    recorder = InMemoryEvidenceRecorder()

    await recorder.append(PendingSegmentStartedEvidence(_provenance()))
    first_snapshot = recorder.snapshot()
    await recorder.append(_rx_draft(23))

    assert isinstance(first_snapshot, tuple)
    assert len(first_snapshot) == 1
    assert len(recorder.snapshot()) == 2


@pytest.mark.asyncio
async def test_rx_evidence_preserves_exact_binary_payload() -> None:
    recorder = InMemoryEvidenceRecorder()
    payload = bytes(range(256)) + b"\x00\x80\xff"
    pending = PendingRxBytesEvidence(
        connection_id=ConnectionInstanceId("connection-1"),
        segment_id=SegmentId("segment-1"),
        payload=payload,
        observed_at=BackendObservationTimestamp(
            domain_id="host-observer-1",
            value=99,
        ),
    )

    recorded = await recorder.append(pending)

    assert isinstance(recorded, RxBytesEvidence)
    assert recorded.payload == payload
    assert recorded.payload is payload
    assert recorder.snapshot() == (recorded,)


@pytest.mark.asyncio
async def test_failed_append_adds_nothing_and_does_not_consume_a_sequence() -> None:
    recorder = InMemoryEvidenceRecorder()
    invalid_record = cast("PendingEvidenceRecord", object())

    with pytest.raises(TypeError, match="unsupported evidence draft"):
        await recorder.append(invalid_record)

    assert recorder.snapshot() == ()
    recorded = await recorder.append(_rx_draft(7))
    assert recorded.sequence == 0


@pytest.mark.asyncio
async def test_observer_loss_evidence_preserves_unknown_loss_amount() -> None:
    recorder = InMemoryEvidenceRecorder()
    recorded = await recorder.append(
        PendingObserverLossEvidence(
            connection_id=ConnectionInstanceId("connection-1"),
            segment_id=SegmentId("segment-1"),
            observer_id="observer-1",
            scope="uart-buffer",
            cause=ObserverLossCause.OTHER_OBSERVED_LOSS,
            lost_bytes=None,
            observed_at=BackendObservationTimestamp(
                domain_id="host-observer-1",
                value=101,
            ),
        )
    )

    assert isinstance(recorded, ObserverLossEvidence)
    assert recorded.lost_bytes is None


@pytest.mark.asyncio
async def test_invalid_zero_loss_evidence_is_not_appended() -> None:
    recorder = InMemoryEvidenceRecorder()
    with pytest.raises(ValueError, match="positive"):
        await recorder.append(
            PendingObserverLossEvidence(
                connection_id=ConnectionInstanceId("connection-1"),
                segment_id=SegmentId("segment-1"),
                observer_id="observer-1",
                scope="uart-buffer",
                cause=ObserverLossCause.OVERFLOW,
                lost_bytes=0,
                observed_at=BackendObservationTimestamp(
                    domain_id="host-observer-1",
                    value=101,
                ),
            )
        )

    assert recorder.snapshot() == ()
