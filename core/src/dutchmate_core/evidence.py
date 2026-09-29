"""Append-only authoritative evidence recording boundary."""

import asyncio
from dataclasses import dataclass
from typing import Protocol

from dutchmate_core.model import (
    BackendObservationTimestamp,
    ConnectionInstanceId,
    EvidenceRecord,
    ObserverLossCause,
    ObserverLossEvidence,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentEndReason,
    SegmentId,
    SegmentProvenance,
    SegmentStartedEvidence,
)


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
)


class EvidenceRecorder(Protocol):
    """Atomic append boundary for the active evidence journal."""

    async def append(self, draft: PendingEvidenceRecord) -> EvidenceRecord: ...

    def snapshot(self) -> tuple[EvidenceRecord, ...]: ...


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
        case _:
            raise TypeError(f"unsupported evidence draft: {type(draft).__name__}")
