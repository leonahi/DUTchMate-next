"""Follow value invariants, independent of live registration and delivery."""

from dataclasses import FrozenInstanceError, fields, replace
from typing import Any, cast

import pytest

from dutchmate_core import follow, model
from tests.unit.test_sqlite_evidence_codec import (
    _basic_provenance,
    _records,
    _segment_started,
)


def start(sequence: int = 1) -> follow.FollowStart:
    return follow.FollowStart(
        "opaque run",
        model.SessionId("session"),
        sequence,
        _segment_started(_basic_provenance()).provenance,
    )


def marker(end: int = 5) -> model.RetentionMarker:
    return model.RetentionMarker(model.SequenceRange(0, end), None, None, end, 512, 900)


@pytest.mark.parametrize("session", ["s", "é" * 128, " e\u0301 "])
def test_request_preserves_exact_session(session: str) -> None:
    request = follow.FollowRequest(model.SessionId(session))
    assert request.session_id.value == session
    with pytest.raises(FrozenInstanceError):
        request.session_id = model.SessionId("other")  # type: ignore[misc]


@pytest.mark.parametrize("session", ["é" * 129, "s\0x", "\ud800", "\udfff"])
def test_request_rejects_invalid_session_bytes(session: str) -> None:
    with pytest.raises(ValueError):
        follow.FollowRequest(model.SessionId(session))


@pytest.mark.parametrize("session", [None, "session", True, 1])
def test_request_requires_validated_session(session: Any) -> None:
    with pytest.raises(TypeError):
        follow.FollowRequest(session)


@pytest.mark.parametrize("sequence", [0, model.SQLITE_INTEGER_MAX])
def test_start_allows_empty_max_boundary_and_keeps_captured_provenance(
    sequence: int,
) -> None:
    captured = start(sequence)
    assert captured.start_sequence == sequence
    assert captured.provenance.connection_provenance.to_snapshot() == (
        _basic_provenance().to_snapshot()
    )
    for item in fields(captured):
        with pytest.raises(FrozenInstanceError):
            setattr(captured, item.name, None)
    with pytest.raises(FrozenInstanceError):
        captured.provenance.segment_id = model.SegmentId("later")  # type: ignore[misc]


@pytest.mark.parametrize(
    "value", [True, False, -1, model.SQLITE_INTEGER_MAX + 1, 1.0, None]
)
def test_start_and_end_reject_counter_coercion_or_overflow(value: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(start(), start_sequence=value)
    if value is not None:  # None is the required honest unknown source cutoff.
        with pytest.raises((TypeError, ValueError)):
            follow.FollowEnd("source_ended", value)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("run_id", ""),
        ("run_id", " "),
        ("run_id", 1),
        ("session_id", "session"),
        ("session_id", model.SessionId("x\0")),
        ("provenance", None),
    ],
)
def test_start_rejects_uncaptured_identity_or_provenance(
    field: str, bad: object
) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(start(), **{field: bad})  # type: ignore[arg-type]


def test_gap_preserves_whole_prefix_marker_for_a_smaller_missed_interval() -> None:
    whole = marker()
    gap = follow.FollowGap(model.SequenceRange(3, 5), whole)
    assert gap.retention_marker is whole
    assert gap.retention_marker.discarded_record_count == 5
    assert gap.missed_range == model.SequenceRange(3, 5)
    with pytest.raises(FrozenInstanceError):
        gap.missed_range = model.SequenceRange(0, 5)  # type: ignore[misc]


@pytest.mark.parametrize(
    "missed", [model.SequenceRange(3, 3), model.SequenceRange(4, 6)]
)
def test_gap_rejects_empty_or_uncovered_interval(missed: model.SequenceRange) -> None:
    with pytest.raises(ValueError):
        follow.FollowGap(missed, marker())


@pytest.mark.parametrize(
    ("missed", "whole"), [(None, marker()), (model.SequenceRange(0, 1), None)]
)
def test_gap_requires_normalized_nonnull_values(missed: Any, whole: Any) -> None:
    with pytest.raises(TypeError):
        follow.FollowGap(missed, whole)


def test_batch_keeps_exact_records_after_gap_without_empty_progress() -> None:
    records = _records()[1:3]
    gap = follow.FollowGap(model.SequenceRange(0, 1), marker())
    batch = follow.FollowBatch(gap, records)
    assert batch.records is records and batch.gap is gap
    assert follow.FollowBatch(gap, ()).records == ()
    with pytest.raises(FrozenInstanceError):
        batch.records = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("gap", "records"),
    [
        (None, ()),
        (None, []),
        (None, (object(),)),
        (None, tuple(reversed(_records()))),
        (None, (_records()[0], _records()[2])),
        (None, (replace(_records()[0], sequence=model.SQLITE_INTEGER_MAX),)),
    ],
)
def test_batch_rejects_empty_mutable_unknown_or_unordered_records(
    gap: Any, records: Any
) -> None:
    with pytest.raises((TypeError, ValueError)):
        follow.FollowBatch(gap, records)


def test_batch_cannot_skip_between_gap_and_first_record() -> None:
    with pytest.raises(ValueError):
        follow.FollowBatch(
            follow.FollowGap(model.SequenceRange(0, 2), marker()), _records()[3:]
        )


@pytest.mark.parametrize(
    "reason",
    [
        "detached",
        "service_stopping",
        "source_ended",
        "source_failed",
        "read_capacity",
        "delivery_too_large",
    ],
)
@pytest.mark.parametrize("cutoff", [None, 0, model.SQLITE_INTEGER_MAX])
def test_end_is_immutable_source_fact_without_delivery_position(
    reason: Any, cutoff: int | None
) -> None:
    end = follow.FollowEnd(reason, cutoff)
    assert end.source_end_exclusive == cutoff and end.reason == reason
    assert [item.name for item in fields(end)] == ["reason", "source_end_exclusive"]
    with pytest.raises(FrozenInstanceError):
        end.source_end_exclusive = 1  # type: ignore[misc]


@pytest.mark.parametrize("reason", [None, True, "closed", "timeout", "busy"])
def test_end_reasons_are_closed(reason: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        follow.FollowEnd(reason, None)


@pytest.mark.parametrize(
    "kind",
    [
        "no_associated_session",
        "session_not_associated",
        "not_active",
        "follow_unavailable",
        "busy",
        "read_capacity",
        "delivery_too_large",
    ],
)
def test_rejection_seals_kind_and_preserves_exception_transport(kind: Any) -> None:
    failure = follow.FollowRejected(kind)
    with pytest.raises(follow.FollowRejected) as caught:
        raise failure
    assert caught.value is failure and str(failure) == kind
    failure.add_note("transport")
    failure.__cause__ = ValueError()
    assert failure.__traceback__ is not None
    with pytest.raises(FrozenInstanceError):
        failure.kind = "busy"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        del failure.kind


@pytest.mark.parametrize("kind", [None, True, "source_failed", "other"])
def test_rejection_categories_are_closed(kind: object) -> None:
    with pytest.raises(TypeError):
        follow.FollowRejected(cast("follow.FollowRejectedKind", kind))
