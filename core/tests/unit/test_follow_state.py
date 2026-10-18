"""Pure page consumption, bounded buffering and source-terminal decisions."""

from dataclasses import replace
from typing import Any

import pytest

from dutchmate_core import follow, model
from dutchmate_core.evidence import EvidenceCursor, EvidencePage, EvidencePageOutcome
from tests.unit.test_follow_values import marker, start
from tests.unit.test_sqlite_evidence_codec import _records

ORIGIN = "12345678-1234-1234-1234-123456789abc"
OPERATION = "abcdefab-1234-1234-1234-123456789abc"


def policy(records: int = 100, charge: int = 2_000_000) -> model.SessionPolicy:
    return model.SessionPolicy(100, 4_000_000, charge, 100, records, charge)


def page(
    records: tuple[model.EvidenceRecord, ...] = (),
    *,
    end: int = 4,
    expired: model.SequenceRange | None = None,
    whole: model.RetentionMarker | None = None,
    charged: int = 100,
    continuation: EvidenceCursor | None = None,
    required: int | None = None,
) -> EvidencePage:
    return EvidencePage(
        records,
        end,
        expired,
        whole,
        None,
        EvidencePageOutcome.PARTIAL if expired else EvidencePageOutcome.COMPLETE,
        continuation is not None,
        continuation,
        charged if records else 0,
        required,
    )


def seven_records() -> tuple[model.EvidenceRecord, ...]:
    first = _records()
    provenance = start().provenance
    return (
        first[0],
        first[1],
        first[2],
        model.OperationStartedEvidence(
            3, OPERATION, "monitor", provenance, 1, 1, ORIGIN, b"x"
        ),
        model.ClientAnnotationEvidence(4, "é\nassertion", "cli", ORIGIN, 5),
        model.OperationEndedEvidence(
            5,
            OPERATION,
            "monitor",
            3,
            model.SequenceRange(4, 5),
            model.MonitorOutcome.TIMEOUT,
            0,
            0,
            None,
            model.MonitorClockFacts(ORIGIN, 0, 1, 1),
        ),
        replace(first[3], sequence=6),
    )


@pytest.mark.parametrize(
    ("records", "charge", "want_records", "want_charge"),
    [
        (1, 1, 1, 1),
        (12, 1000, 12, 1000),
        (100, 2_000_000, 32, 1_048_576),
    ],
)
def test_requests_bound_fresh_ranges_without_historical_continuation(
    records: int,
    charge: int,
    want_records: int,
    want_charge: int,
) -> None:
    state = follow._FollowState(start(2), policy(records, charge))
    request = state.page_request(10)
    assert request.reference == model.EvidenceRangeReference(
        model.SessionId("session"), 2, 10
    )
    assert request.cursor is None
    assert (request.max_records, request.max_charged_bytes) == (
        want_records,
        want_charge,
    )


def test_one_pending_batch_advances_read_position_but_claims_no_delivery() -> None:
    state = follow._FollowState(start(0), policy())
    records = seven_records()
    state.stage_page(page(records, end=7))
    assert state.next_sequence == 7
    with pytest.raises(follow.FollowRejected, match="busy"):
        state.stage_page(page(records, end=7))
    with pytest.raises(follow.FollowRejected, match="busy"):
        state.page_request(8)
    batch = state.take_batch()
    assert batch is not None and batch.gap is None
    assert all(
        actual is expected
        for actual, expected in zip(batch.records, records, strict=True)
    )
    rx = batch.records[1]
    assert isinstance(rx, model.RxBytesEvidence) and rx.payload == bytes(range(256))
    assert state.take_batch() is None
    assert state.page_request(9).reference == model.EvidenceRangeReference(
        model.SessionId("session"), 7, 9
    )


def test_gap_precedes_later_records_and_keeps_whole_marker_unchanged() -> None:
    state = follow._FollowState(start(2), policy())
    whole = marker(5)
    record = replace(_records()[1], sequence=5)
    state.stage_page(
        page((record,), end=6, expired=model.SequenceRange(2, 5), whole=whole)
    )
    batch = state.take_batch()
    assert batch is not None and batch.gap is not None
    assert batch.gap.missed_range == model.SequenceRange(2, 5)
    assert batch.gap.retention_marker is whole
    assert (
        whole.discarded_record_count,
        whole.discarded_rx_payload_byte_count,
        whole.discarded_charged_bytes,
    ) == (5, 512, 900)
    assert batch.records == (record,) and state.next_sequence == 6


def test_expired_snapshot_clips_missed_range_to_head_not_whole_prefix() -> None:
    state = follow._FollowState(start(2), policy())
    whole = marker(9)
    state.stage_page(page(end=6, expired=model.SequenceRange(2, 6), whole=whole))
    batch = state.take_batch()
    assert batch is not None and batch.gap == follow.FollowGap(
        model.SequenceRange(2, 6), whole
    )
    assert batch.records == () and state.next_sequence == 6
    state.stage_page(page(end=9, expired=model.SequenceRange(6, 9), whole=whole))
    batch = state.take_batch()
    assert batch is not None and batch.gap is not None
    assert batch.gap.missed_range == model.SequenceRange(6, 9)


def test_partial_page_uses_fresh_head_next_time() -> None:
    state = follow._FollowState(start(1), policy(1))
    cursor = EvidenceCursor(model.SessionId("session"), 1, 5, 5, 2)
    state.stage_page(page(_records()[1:2], end=5, continuation=cursor))
    assert state.take_batch() == follow.FollowBatch(None, _records()[1:2])
    request = state.page_request(10)
    assert request.cursor is None
    assert request.reference == model.EvidenceRangeReference(
        model.SessionId("session"), 2, 10
    )


@pytest.mark.parametrize(("cap", "required"), [(2_000_000, 1_048_577), (100, 101)])
def test_zero_record_charge_shortage_terminates_at_same_sequence_with_unknown_final_end(
    cap: int, required: int
) -> None:
    state = follow._FollowState(start(2), policy(charge=cap))
    cursor = EvidenceCursor(model.SessionId("session"), 2, 4, 4, 2)
    state.stage_page(page(end=4, continuation=cursor, required=required))
    assert state.next_sequence == 2 and state.take_batch() is None
    assert state.end() == follow.FollowEnd("delivery_too_large", None)


def test_gap_is_still_available_before_oversized_first_retained_record() -> None:
    state = follow._FollowState(start(2), policy())
    cursor = EvidenceCursor(model.SessionId("session"), 2, 8, 8, 5)
    state.stage_page(
        page(
            end=8,
            expired=model.SequenceRange(2, 5),
            whole=marker(5),
            continuation=cursor,
            required=1_048_577,
        )
    )
    batch = state.take_batch()
    assert batch is not None and batch.gap is not None and batch.records == ()
    assert batch.gap.missed_range == model.SequenceRange(2, 5)
    assert state.next_sequence == 5
    assert state.end() == follow.FollowEnd("delivery_too_large", None)


@pytest.mark.parametrize("boundary", [0, model.SQLITE_INTEGER_MAX])
def test_empty_actual_tail_is_idle_including_max_without_overflow(
    boundary: int,
) -> None:
    state = follow._FollowState(start(boundary), policy())
    request = state.page_request(boundary)
    assert request.reference == model.EvidenceRangeReference(
        model.SessionId("session"), boundary, boundary
    )
    state.stage_page(page(end=boundary))
    assert (
        state.next_sequence == boundary
        and state.take_batch() is None
        and state.end() is None
    )


def test_last_legal_record_advances_to_max() -> None:
    maximum = model.SQLITE_INTEGER_MAX
    state = follow._FollowState(start(maximum - 1), policy())
    record = replace(_records()[1], sequence=maximum - 1)
    state.stage_page(page((record,), end=maximum))
    assert state.take_batch() == follow.FollowBatch(None, (record,))
    assert state.next_sequence == maximum


@pytest.mark.parametrize(
    "bad_page",
    [
        page(end=4),  # Nonempty eligible interval with no progress or shortage.
        page(_records()[2:3], end=4),  # Silently skipped unread sequence1.
        page(tuple(reversed(_records()[1:3])), end=4),
        page(_records()[1:3], end=2),  # Record beyond the captured head.
        page(end=0),  # Stale source snapshot.
        page(end=4, expired=model.SequenceRange(1, 3)),  # Missing marker.
        page(end=4, expired=model.SequenceRange(0, 3), whole=marker(3)),
        page(end=4, expired=model.SequenceRange(1, 3), whole=marker(5)),  # Inexact gap.
        page(end=4, required=100),  # Fits cap: not a legitimate shortage.
    ],
)
def test_invalid_or_no_progress_page_never_advances_state(
    bad_page: EvidencePage,
) -> None:
    state = follow._FollowState(start(1), policy())
    with pytest.raises(ValueError):
        state.stage_page(bad_page)
    assert (
        state.next_sequence == 1 and state.take_batch() is None and state.end() is None
    )


@pytest.mark.parametrize(
    ("records", "charge", "bad_page"),
    [
        (1, 1000, page(_records()[1:3], end=3)),
        (32, 1000, page(_records()[1:2], end=2, charged=1001)),
        (
            100,
            2_000_000,
            page(tuple(replace(_records()[1], sequence=n) for n in range(33)), end=33),
        ),
        (100, 2_000_000, page(_records()[1:2], end=2, charged=1_048_577)),
    ],
)
def test_page_cannot_exceed_policy_or_fixed_caps(
    records: int, charge: int, bad_page: EvidencePage
) -> None:
    state = follow._FollowState(
        start(0 if len(bad_page.records) == 33 else 1), policy(records, charge)
    )
    with pytest.raises(ValueError):
        state.stage_page(bad_page)


def test_seal_discards_prefetched_tail_and_never_infers_final_cutoff_from_read_head() -> (
    None
):
    state = follow._FollowState(start(1), policy())
    state.stage_page(page(_records()[1:3], end=3))
    state.seal("service_stopping")
    assert state.next_sequence == 3 and state.take_batch() is None
    assert state.end() == follow.FollowEnd("service_stopping", None)
    for action in (
        lambda: state.page_request(4),
        lambda: state.stage_page(page(end=3)),
    ):
        with pytest.raises(follow.FollowRejected, match="not_active"):
            action()


@pytest.mark.parametrize(
    "reasons",
    [
        ("source_ended", "source_failed", "detached", "service_stopping"),
        ("service_stopping", "detached", "source_failed", "source_ended"),
    ],
)
def test_seal_precedence_and_final_cutoff_before_end_is_frozen(
    reasons: tuple[Any, ...],
) -> None:
    state = follow._FollowState(start(2), policy())
    for reason in reasons:
        state.seal(reason)
    state.seal("source_ended", 8)
    end = state.end()
    assert end == follow.FollowEnd("service_stopping", 8)
    state.seal("source_failed", 10)
    assert state.end() is end


@pytest.mark.parametrize("reason", ["read_capacity", "delivery_too_large"])
def test_delivery_decisions_are_not_overwritten_by_later_source_seal(
    reason: Any,
) -> None:
    state = follow._FollowState(start(1), policy())
    state.seal(reason, 4)
    state.seal("service_stopping", 5)
    assert state.end() == follow.FollowEnd(reason, 5)


def test_returned_unknown_end_never_changes_when_teardown_later_knows_cutoff() -> None:
    state = follow._FollowState(start(2), policy())
    state.seal("detached")
    end = state.end()
    state.seal("service_stopping", 10)
    assert state.end() is end and end == follow.FollowEnd("detached", None)


@pytest.mark.parametrize("cutoff", [True, -1, 1, model.SQLITE_INTEGER_MAX + 1])
def test_cutoff_must_cover_read_position_and_be_exact_counter(cutoff: Any) -> None:
    state = follow._FollowState(start(2), policy())
    with pytest.raises((TypeError, ValueError)):
        state.seal("detached", cutoff)
    assert state.end() is None


@pytest.mark.parametrize("head", [True, -1, 1, model.SQLITE_INTEGER_MAX + 1])
def test_read_head_cannot_coerce_or_move_backwards(head: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        follow._FollowState(start(2), policy()).page_request(head)


def test_close_is_idempotent_subscriber_only_discard_without_invented_terminal() -> (
    None
):
    state = follow._FollowState(start(1), policy())
    state.stage_page(page(_records()[1:3], end=3))
    state.close()
    state.close()
    assert state.take_batch() is None and state.end() is None
    with pytest.raises(follow.FollowRejected, match="not_active"):
        state.page_request(4)
    with pytest.raises(follow.FollowRejected, match="not_active"):
        state.stage_page(page(end=3))


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("source_ended", "source_failed", "source_failed"),
        ("source_failed", "source_ended", "source_failed"),
        ("source_failed", "detached", "detached"),
        ("detached", "source_failed", "detached"),
        ("detached", "service_stopping", "service_stopping"),
        ("service_stopping", "detached", "service_stopping"),
        ("read_capacity", "delivery_too_large", "read_capacity"),
        ("delivery_too_large", "read_capacity", "delivery_too_large"),
    ],
)
def test_each_seal_precedence_and_first_delivery_failure(
    first: Any, second: Any, expected: Any
) -> None:
    state = follow._FollowState(start(2), policy())
    state.seal(first)
    state.seal(second)
    assert state.end() == follow.FollowEnd(expected, None)


def test_gap_keeps_different_timestamp_domains_without_recomputing_endpoints() -> None:
    host = start().provenance.backend_observation_timestamp_domain
    device = replace(
        host,
        domain_id="helper",
        origin_id="helper-origin",
        observer=model.TimestampObserver.DEVICE,
        unit=model.TimestampUnit.TICK,
    )
    whole = replace(
        marker(5),
        first_discarded_timestamp=model.RetentionTimestampEndpoint(
            model.BackendObservationTimestamp(host.domain_id, 500), host
        ),
        last_discarded_timestamp=model.RetentionTimestampEndpoint(
            model.BackendObservationTimestamp(device.domain_id, 1), device
        ),
    )
    state = follow._FollowState(start(3), policy())
    state.stage_page(page(end=5, expired=model.SequenceRange(3, 5), whole=whole))
    batch = state.take_batch()
    assert batch is not None and batch.gap is not None
    assert batch.gap.retention_marker is whole
    assert (
        batch.gap.retention_marker.first_discarded_timestamp
        is whole.first_discarded_timestamp
    )
    assert (
        batch.gap.retention_marker.last_discarded_timestamp
        is whole.last_discarded_timestamp
    )
