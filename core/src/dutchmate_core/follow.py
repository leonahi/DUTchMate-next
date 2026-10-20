"""Follow values, bounded read state and captured-journal subscriber mechanics."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import FrozenInstanceError, dataclass, field
from typing import Final, Literal

from dutchmate_core.evidence import EvidencePage, EvidenceRetrievalRequest
from dutchmate_core.model import (
    ClientAnnotationEvidence,
    EvidenceRangeReference,
    EvidenceRecord,
    InteractEndedEvidence,
    InteractStartedEvidence,
    ObserverLossEvidence,
    OperationEndedEvidence,
    OperationStartedEvidence,
    RetentionMarker,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentProvenance,
    SegmentStartedEvidence,
    SequenceRange,
    SessionId,
    SessionPolicy,
    UartTxSettledEvidence,
    validate_persisted_counter,
    validate_record_sequence,
)


def _validate_session(session_id: SessionId) -> None:
    if not isinstance(session_id, SessionId):
        raise TypeError("Follow requires a session ID")
    value = session_id.value
    if type(value) is not str or "\0" in value or not 1 <= len(value.encode()) <= 256:
        raise ValueError("invalid Follow session ID")


@dataclass(frozen=True, slots=True)
class FollowRequest:
    session_id: SessionId

    def __post_init__(self) -> None:
        _validate_session(self.session_id)


@dataclass(frozen=True, slots=True)
class FollowStart:
    run_id: str
    session_id: SessionId
    start_sequence: int
    provenance: SegmentProvenance

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or not self.run_id.strip():
            raise ValueError("Follow requires a captured run identity")
        _validate_session(self.session_id)
        validate_persisted_counter(self.start_sequence, name="Follow start sequence")
        if not isinstance(self.provenance, SegmentProvenance):
            raise TypeError("Follow requires captured segment provenance")


@dataclass(frozen=True, slots=True)
class FollowGap:
    missed_range: SequenceRange
    retention_marker: RetentionMarker

    def __post_init__(self) -> None:
        if not isinstance(self.missed_range, SequenceRange) or not isinstance(
            self.retention_marker, RetentionMarker
        ):
            raise TypeError("Follow gap requires a range and retention marker")
        expired = self.retention_marker.expired_range
        if self.missed_range.is_empty or not (
            expired.start_inclusive
            <= self.missed_range.start_inclusive
            < self.missed_range.end_exclusive
            <= expired.end_exclusive
        ):
            raise ValueError("Follow missed range must be nonempty and covered")


@dataclass(frozen=True, slots=True)
class FollowBatch:
    """One bounded progress result; gap precedes the exact existing records."""

    gap: FollowGap | None
    records: tuple[EvidenceRecord, ...]

    def __post_init__(self) -> None:
        if self.gap is not None and not isinstance(self.gap, FollowGap):
            raise TypeError("Follow batch gap must be validated")
        if type(self.records) is not tuple:
            raise TypeError("Follow records must be an immutable tuple")
        if self.gap is None and not self.records:
            raise ValueError("Follow batch must make progress")
        next_sequence = (
            None if self.gap is None else self.gap.missed_range.end_exclusive
        )
        for record in self.records:
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
                raise TypeError("Follow requires existing evidence records")
            validate_record_sequence(record.sequence)
            if next_sequence is not None and record.sequence != next_sequence:
                raise ValueError("Follow records must be consecutive after the gap")
            next_sequence = record.sequence + 1


type FollowEndReason = Literal[
    "detached",
    "service_stopping",
    "source_ended",
    "source_failed",
    "read_capacity",
    "delivery_too_large",
]
_END_REASONS = frozenset(
    {
        "detached",
        "service_stopping",
        "source_ended",
        "source_failed",
        "read_capacity",
        "delivery_too_large",
    }
)


@dataclass(frozen=True, slots=True)
class FollowEnd:
    """Frozen source facts only; the delivery adapter owns its offered position."""

    reason: FollowEndReason
    source_end_exclusive: int | None

    def __post_init__(self) -> None:
        if type(self.reason) is not str or self.reason not in _END_REASONS:
            raise ValueError("Follow end reason must be declared")
        if self.source_end_exclusive is not None:
            validate_persisted_counter(
                self.source_end_exclusive, name="Follow source end"
            )


type FollowRejectedKind = Literal[
    "no_associated_session",
    "session_not_associated",
    "not_active",
    "follow_unavailable",
    "busy",
    "read_capacity",
    "delivery_too_large",
]
_REJECTION_KINDS = frozenset(
    {
        "no_associated_session",
        "session_not_associated",
        "not_active",
        "follow_unavailable",
        "busy",
        "read_capacity",
        "delivery_too_large",
    }
)


@dataclass(slots=True, unsafe_hash=True)
class FollowRejected(RuntimeError):
    """Sealed classification with ordinary exception transport metadata."""

    kind: Final[FollowRejectedKind] = field()

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
            raise TypeError("Follow rejection kind must be declared")
        RuntimeError.__init__(self, self.kind)


class _FollowState:
    """One materialized batch and a read position, without tasks or live handles.

    Staging advances only the internal read position. Taking a batch transfers
    its payload references to the caller; neither operation claims delivery.
    The runtime supplies final cutoff facts explicitly, never from a page head.
    """

    def __init__(self, start: FollowStart, policy: SessionPolicy) -> None:
        if not isinstance(start, FollowStart) or not isinstance(policy, SessionPolicy):
            raise TypeError("Follow state requires validated start and policy")
        self._start = start
        self._max_records = min(32, policy.max_retrieval_page_records)
        self._max_charged_bytes = min(1048576, policy.max_retrieval_page_charged_bytes)
        self._next_sequence = start.start_sequence
        self._pending: FollowBatch | None = None
        self._reason: FollowEndReason | None = None
        self._source_end: int | None = None
        self._end: FollowEnd | None = None
        self._closed = False

    @property
    def next_sequence(self) -> int:
        return self._next_sequence

    def _require_live(self) -> None:
        if self._closed or self._reason is not None:
            raise FollowRejected("not_active")
        if self._pending is not None:
            raise FollowRejected("busy")

    def page_request(self, head: int) -> EvidenceRetrievalRequest:
        self._require_live()
        validate_persisted_counter(head, name="Follow read head")
        if head < self.next_sequence:
            raise ValueError("Follow read head precedes the read position")
        return EvidenceRetrievalRequest(
            EvidenceRangeReference(self._start.session_id, self.next_sequence, head),
            self._max_records,
            self._max_charged_bytes,
        )

    def stage_page(self, page: EvidencePage) -> None:
        """Validate before mutating; retain at most one bounded progress batch."""
        self._require_live()
        if not isinstance(page, EvidencePage):
            raise TypeError("Follow requires an evidence page")
        if (
            page.snapshot_end_exclusive < self.next_sequence
            or page.never_existed_range is not None
            or len(page.records) > self._max_records
            or page.charged_bytes > self._max_charged_bytes
        ):
            raise ValueError("Follow page exceeds its range or bounds")
        gap: FollowGap | None = None
        position = self.next_sequence
        if page.expired_range is not None:
            if page.retention_marker is None:
                raise ValueError("expired Follow page requires retention facts")
            expected = SequenceRange(
                position,
                min(
                    page.retention_marker.expired_range.end_exclusive,
                    page.snapshot_end_exclusive,
                ),
            )
            if page.expired_range != expected:
                raise ValueError("Follow gap must be the exact unread expired interval")
            gap = FollowGap(expected, page.retention_marker)
            position = expected.end_exclusive
        elif page.retention_marker is not None:
            raise ValueError("Follow page marker requires an expired interval")

        batch = None
        if gap is not None or page.records:
            batch = FollowBatch(gap, page.records)
            if page.records:
                if page.records[0].sequence != position:
                    raise ValueError("Follow page skips the next unread record")
                position = page.records[-1].sequence + 1
            if position > page.snapshot_end_exclusive:
                raise ValueError("Follow records exceed the page snapshot")

        too_large = (
            not page.records
            and page.next_record_required_bytes is not None
            and page.next_record_required_bytes > self._max_charged_bytes
        )
        if position < page.snapshot_end_exclusive and batch is None and not too_large:
            raise ValueError("Follow page makes no progress")
        self._pending = batch
        self._next_sequence = position
        if too_large:
            # Keep a preceding gap available, but never skip the oversized row.
            # A nonterminal read head is not a final source cutoff.
            self._reason = "delivery_too_large"

    def take_batch(self) -> FollowBatch | None:
        batch, self._pending = self._pending, None
        return batch

    def seal(
        self, reason: FollowEndReason, source_end_exclusive: int | None = None
    ) -> None:
        """Discard prefetched data; freeze only when the end is actually taken."""
        facts = FollowEnd(reason, source_end_exclusive)
        if (
            source_end_exclusive is not None
            and source_end_exclusive < self.next_sequence
        ):
            raise ValueError("Follow source end precedes the read position")
        if self._closed or self._end is not None:
            return
        # Already fixed delivery/read failures win. Otherwise synchronous stop
        # intents may refine a source seal before any end facts escape.
        precedence = {
            "source_ended": 0,
            "source_failed": 1,
            "detached": 2,
            "service_stopping": 3,
            "read_capacity": 4,
            "delivery_too_large": 4,
        }
        if self._reason is None or precedence[reason] > precedence[self._reason]:
            self._reason = facts.reason
        if source_end_exclusive is not None:
            self._source_end = source_end_exclusive
        self._pending = None

    def end(self) -> FollowEnd | None:
        if self._end is None and self._reason is not None and self._pending is None:
            self._end = FollowEnd(self._reason, self._source_end)
        return self._end

    def close(self) -> None:
        """Subscriber-only discard; closing does not fabricate source facts."""
        self._closed = True
        self._pending = None


type _RetrieveFollowPage = Callable[[EvidenceRetrievalRequest], Awaitable[EvidencePage]]


def _follow_head_request(
    session_id: SessionId, policy: SessionPolicy
) -> EvidenceRetrievalRequest:
    """Existing metadata-only empty range, never a payload/history selection."""
    from dutchmate_core.model import SQLITE_INTEGER_MAX

    return EvidenceRetrievalRequest(
        EvidenceRangeReference(session_id, SQLITE_INTEGER_MAX, SQLITE_INTEGER_MAX),
        min(32, policy.max_retrieval_page_records),
        min(1048576, policy.max_retrieval_page_charged_bytes),
    )


class _FollowSubscription:
    """One coordinator registration; no worker, reader connection or RX queue.

    The captured retrieve callable uses the existing live journal. Runtime
    admission, generation ownership and read leases are outside this mechanism.
    """

    def __init__(
        self,
        start: FollowStart,
        policy: SessionPolicy,
        retrieve: _RetrieveFollowPage,
        unregister: Callable[[], None],
    ) -> None:
        self._start = start
        self._state = _FollowState(start, policy)
        self._head_request = _follow_head_request(start.session_id, policy)
        self._retrieve: _RetrieveFollowPage | None = retrieve
        self._unregister: Callable[[], None] | None = unregister
        self._changed = asyncio.Event()
        self._pulling = False
        self._closed = False

    @property
    def start(self) -> FollowStart:
        return self._start

    def notify(self) -> None:
        """A coalesced hint only; committed facts always come from the journal."""
        self._changed.set()

    async def pull(self) -> FollowBatch | FollowEnd:
        if self._closed:
            raise FollowRejected("not_active")
        if self._pulling:
            raise FollowRejected("busy")
        self._pulling = True
        try:
            while True:
                if self._closed:
                    raise FollowRejected("not_active")
                end = self._state.end()
                if end is not None:
                    return end
                # Clear before the head snapshot, never after a query that can
                # race a commit. Any subsequent wake remains visible to wait().
                self._changed.clear()
                retrieve = self._retrieve
                assert retrieve is not None
                head = await retrieve(self._head_request)
                if self._closed:
                    raise FollowRejected("not_active")
                if head.snapshot_end_exclusive > self._state.next_sequence:
                    page = await retrieve(
                        self._state.page_request(head.snapshot_end_exclusive)
                    )
                    if self._closed:
                        raise FollowRejected("not_active")
                    self._state.stage_page(page)
                    batch = self._state.take_batch()
                    if batch is not None:
                        return batch
                    end = self._state.end()
                    if end is not None:
                        return end
                await self._changed.wait()
        finally:
            self._pulling = False

    async def close(self) -> None:
        """Unregister this subscriber only, without touching the recorder."""
        if self._closed:
            return
        self._closed = True
        self._state.close()
        self._changed.set()
        self._retrieve = None
        unregister, self._unregister = self._unregister, None
        if unregister is not None:
            unregister()
