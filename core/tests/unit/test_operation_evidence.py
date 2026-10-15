"""Standalone immutable operation facts; no journal/runtime execution."""

from dataclasses import FrozenInstanceError, fields, replace

import pytest

from dutchmate_core import evidence, model
from tests.unit.test_monitor_values import OPERATION, ORIGIN
from tests.unit.test_sqlite_evidence_codec import _basic_provenance, _segment_started


def start_draft() -> evidence.PendingOperationStartedEvidence:
    return evidence.PendingOperationStartedEvidence(
        operation_id=OPERATION,
        operation_kind="monitor",
        provenance=_segment_started(_basic_provenance()).provenance,
        timeout_ms=4000,
        max_rx_bytes=1048576,
        clock_origin_id=ORIGIN,
        condition=bytes(range(256)),
    )


def end_draft() -> evidence.PendingOperationEndedEvidence:
    return evidence.PendingOperationEndedEvidence(
        operation_id=OPERATION,
        operation_kind="monitor",
        start_sequence=2,
        window=model.SequenceRange(3, 6),
        outcome=model.MonitorOutcome.MATCHED,
        examined_rx_bytes=256,
        observer_loss_records=0,
        match=model.MonitorMatch(
            model.MonitorMatchStart(3, 0), model.MonitorMatchEnd(5, 256)
        ),
        clock=model.MonitorClockFacts(ORIGIN, 100, 4000000100, 200),
    )


def test_pending_assignment_preserves_exact_fields_and_literal_condition() -> None:
    cases: tuple[
        tuple[
            evidence.PendingOperationStartedEvidence
            | evidence.PendingOperationEndedEvidence,
            type[model.OperationStartedEvidence] | type[model.OperationEndedEvidence],
            int,
        ],
        ...,
    ] = (
        (start_draft(), model.OperationStartedEvidence, 2),
        (end_draft(), model.OperationEndedEvidence, 6),
    )
    for draft, cls, sequence in cases:
        record = evidence._assign_sequence(draft, sequence)
        assert isinstance(record, cls)
        assert isinstance(record, (model.OperationStartedEvidence, model.OperationEndedEvidence))
        assert record.sequence == sequence
        assert {f.name for f in fields(record)} == {
            "sequence",
            *(f.name for f in fields(draft)),
        }
        for f in fields(draft):
            assert getattr(record, f.name) == getattr(draft, f.name)
        with pytest.raises(FrozenInstanceError):
            record.operation_kind = "interact"  # type: ignore[misc,assignment]
    started = evidence._assign_sequence(start_draft(), 2)
    assert isinstance(started, model.OperationStartedEvidence)
    assert started.condition == bytes(range(256))
    assert started.provenance.connection_provenance.to_snapshot().envelope_version == 1


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("operation_id", "not-a-uuid"),
        ("operation_id", OPERATION.upper()),
        ("operation_kind", "interact"),
        ("operation_kind", None),
        ("clock_origin_id", ORIGIN.upper()),
        ("provenance", None),
        ("condition", b""),
        ("condition", b"a" * 257),
        ("condition", bytearray(b"a")),
        ("timeout_ms", True),
        ("timeout_ms", 0),
        ("timeout_ms", 4001),
        ("max_rx_bytes", 1048577),
        ("max_rx_bytes", False),
    ],
)
def test_start_draft_and_value_validate_same_input(field: str, bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(start_draft(), **{field: bad})  # type: ignore[arg-type]
    record = evidence._assign_sequence(start_draft(), 2)
    with pytest.raises((TypeError, ValueError)):
        replace(record, **{field: bad})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("operation_kind", "other"),
        ("operation_id", OPERATION.upper()),
        ("start_sequence", True),
        ("start_sequence", -1),
        ("start_sequence", model.SQLITE_INTEGER_MAX),
        ("window", model.SequenceRange(2, 6)),
        ("window", model.SequenceRange(3, 5)),
        ("window", None),
        ("outcome", "matched"),
        ("match", None),
        ("examined_rx_bytes", True),
        ("examined_rx_bytes", 0),
        ("examined_rx_bytes", 1048577),
        ("observer_loss_records", True),
        ("observer_loss_records", model.SQLITE_INTEGER_MAX + 1),
        ("clock", model.MonitorClockFacts(ORIGIN, 0, 10, 10)),
        ("clock", None),
    ],
)
def test_end_draft_and_value_reject_invalid_structure(field: str, bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(end_draft(), **{field: bad})  # type: ignore[arg-type]
    record = evidence._assign_sequence(end_draft(), 6)
    with pytest.raises((TypeError, ValueError)):
        replace(record, **{field: bad})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("start_seq", "start_offset", "end_seq", "end_offset"),
    [
        (1, -1, 1, 1),
        (1, 0, 1, 0),
        (1, 1, 1, 1),
        (2, 0, 1, 1),
        (True, 0, 1, 1),
        (1, False, 1, 1),
        (1, 0, 1, True),
        (1, 0, model.SQLITE_INTEGER_MAX, 1),
        (1, 0, 1, model.SQLITE_INTEGER_MAX + 1),
    ],
)
def test_match_endpoints_require_ordered_nonempty_exact_positions(
    start_seq: int, start_offset: int, end_seq: int, end_offset: int
) -> None:
    with pytest.raises((TypeError, ValueError)):
        model.MonitorMatch(
            model.MonitorMatchStart(start_seq, start_offset),
            model.MonitorMatchEnd(end_seq, end_offset),
        )


def test_maximum_end_tuple_has_exactly_nine_legal_standalone_variants() -> None:
    drafts = evidence.maximum_monitor_end_drafts(OPERATION, ORIGIN)
    assert type(drafts) is tuple and len(drafts) == 9
    assert {d.outcome for d in drafts} == set(model.MonitorOutcome)
    for draft in drafts:
        record = evidence._assign_sequence(draft, model.SQLITE_INTEGER_MAX - 1)
        assert isinstance(record, model.OperationEndedEvidence)
        assert record.examined_rx_bytes == 1048576
        assert record.observer_loss_records == model.SQLITE_INTEGER_MAX
        assert record.window == model.SequenceRange(
            model.SQLITE_INTEGER_MAX - 1, model.SQLITE_INTEGER_MAX
        )
        assert (record.match is not None) == (
            record.outcome is model.MonitorOutcome.MATCHED
        )
        assert (record.clock.decided_at_ns >= record.clock.deadline_at_ns) == (
            record.outcome is model.MonitorOutcome.TIMEOUT
        )
        if record.match:
            assert record.match.start.byte_offset == model.SQLITE_INTEGER_MAX - 1
            assert record.match.end.byte_offset_exclusive == model.SQLITE_INTEGER_MAX


@pytest.mark.parametrize(
    "ceiling",
    [
        "max_record_charged_bytes",
        "max_retained_charged_bytes",
        "max_retrieval_page_charged_bytes",
    ],
)
def test_policy_charge_fit_equality_and_one_over(ceiling: str) -> None:
    # Retained/page ceilings may exceed the single-record ceiling, never enlarge it.
    policy = model.SessionPolicy(10, 2000, 1000, 10, 10, 2000)
    assert evidence.monitor_marker_charges_fit(policy, (1000, 1000))
    assert not evidence.monitor_marker_charges_fit(policy, (1001, 1000))
    assert not evidence.monitor_marker_charges_fit(policy, (1000, 1001))
    assert evidence.monitor_marker_charges_fit(
        replace(policy, **{ceiling: 1001}), (1000, 1000)
    )


@pytest.mark.parametrize(
    "charges", [(0, 1), (True, 1), (1, -1), (1, model.SQLITE_INTEGER_MAX + 1), (1, 1.0)]
)
def test_policy_fit_rejects_invalid_callback_charge(charges: tuple[int, int]) -> None:
    with pytest.raises((TypeError, ValueError)):
        evidence.monitor_marker_charges_fit(
            model.SessionPolicy(10, 1000, 1000, 10, 10, 1000), charges
        )
