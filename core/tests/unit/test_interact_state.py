"""Bounded synchronous Interact matching/decisions over supplied record values."""

from dataclasses import replace
from typing import Any

import pytest

from dutchmate_core import backend, interact, model
from tests.unit.test_interact_values import ORIGIN, request
from tests.unit.test_sqlite_evidence_codec import _basic_provenance, _segment_started


@pytest.fixture
def api() -> Any:
    return interact


@pytest.fixture(params=["host", "device"])
def provenance(request: pytest.FixtureRequest) -> model.SegmentProvenance:
    base = _segment_started(_basic_provenance()).provenance
    if request.param == "host":
        return base
    return replace(
        base,
        backend_observation_timestamp_domain=model.BackendObservationTimestampDomain(
            "device-domain",
            model.TimestampObserver.DEVICE,
            model.TimestampMeaning.OBSERVATION,
            model.TimestampUnit.TICK,
            "device-origin",
        ),
        loss_observability=model.ObserverReportsUartLoss("observer", "uart-buffer"),
        connection_provenance=model.PersistedConnectionProvenance(
            model.ConnectionProvenanceSnapshot(
                envelope_version=1,
                backend_kind="fixture_enhanced",
                backend_schema_version=1,
                fields=(),
            )
        ),
    )


def state(api: Any, captured: model.SegmentProvenance, **changes: Any) -> Any:
    values = dict(
        request=request(api),
        start_sequence=2,
        provenance=captured,
        clock_origin_id=ORIGIN,
        started_at_ns=100,
    )
    values.update(changes)
    return api.InteractState(**values)


def rx(
    provenance: model.SegmentProvenance, sequence: int, payload: bytes
) -> model.RxBytesEvidence:
    return model.RxBytesEvidence(
        sequence,
        provenance.connection_id,
        provenance.segment_id,
        payload,
        model.BackendObservationTimestamp(
            provenance.backend_observation_timestamp_domain.domain_id, 1
        ),
    )


def loss(
    provenance: model.SegmentProvenance, sequence: int
) -> model.ObserverLossEvidence:
    return model.ObserverLossEvidence(
        sequence,
        provenance.connection_id,
        provenance.segment_id,
        "observer",
        "uart-buffer",
        model.ObserverLossCause.OVERFLOW,
        None,
        model.BackendObservationTimestamp(
            provenance.backend_observation_timestamp_domain.domain_id, 1
        ),
    )


def ack(count: int = 2) -> backend.BackendWriteResult:
    return backend.BackendWriteResult(
        backend.BackendWriteStatus.ACKNOWLEDGED, count, None
    )


def test_early_match_waits_for_full_ack_and_freezes_whole_chunk_window(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    value = state(api, provenance)
    assert value.mark_submitted() is True
    record = rx(provenance, 3, b"xOKasync")
    value.publish(record, 150)
    frozen = value.observation
    assert frozen.window == model.SequenceRange(3, 4)
    assert frozen.examined_rx_bytes == 3
    assert frozen.match == model.InteractMatch(
        0, model.MonitorMatchStart(3, 1), model.MonitorMatchEnd(3, 3)
    )
    assert value.outcome is None and record.payload == b"xOKasync"
    value.publish(rx(provenance, 4, b"ambient"), 160)
    assert value.observation is frozen
    value.settle_write(ack(), 170)
    assert value.outcome is model.InteractOutcome.MATCHED
    assert value.tx.accepted_prefix_bytes == 2


@pytest.mark.parametrize(
    "conditions,expected",
    [
        ((b"OK", b"K"), 0),
        ((b"K", b"OK"), 0),
        ((b"OK", b"OK"), 0),
        ((b"later", b"O"), 1),
    ],
)
def test_first_ending_byte_and_request_order_break_ties(
    api: Any,
    provenance: model.SegmentProvenance,
    conditions: tuple[bytes, ...],
    expected: int,
) -> None:
    value = state(api, provenance, request=request(api, conditions=conditions))
    value.publish(rx(provenance, 3, b"OKlater"), 150)
    assert value.observation.match.condition_index == expected
    assert value.observation.examined_rx_bytes == (1 if expected == 1 else 2)


@pytest.mark.parametrize("chunk_size", [1, 2, 7, 256, 4096])
@pytest.mark.parametrize(
    "conditions,payload,budget",
    [
        ((b"\0\xffaba", b"aba"), b"head\0\xffabaTAIL\x80", 9),
        ((b"ababa\0\xff", b"aba\0"), b"xabababa\0\xffTAIL", 100),
        ((b"z" * 255 + b"\xff", b"miss"), b"z" * 4096 + b"\xffTAIL", 1048576),
        ((b"\0\xff", b"miss"), b"x" * 4096 + b"\0\xffTAIL", 4096),
    ],
    ids=["binary", "overlap", "maximum-condition", "byte-limit"],
)
def test_chunking_matches_independent_finite_bytes_find_oracle(
    api: Any,
    provenance: model.SegmentProvenance,
    chunk_size: int,
    conditions: tuple[bytes, ...],
    payload: bytes,
    budget: int,
) -> None:
    candidates = [
        (offset + len(condition), index, offset)
        for index, condition in enumerate(conditions)
        if (offset := payload[:budget].find(condition)) >= 0
    ]
    expected = min(candidates) if candidates else None
    value = state(
        api,
        provenance,
        request=request(api, conditions=conditions, max_rx_bytes=budget),
    )
    for index, offset in enumerate(range(0, len(payload), chunk_size)):
        value.publish(
            rx(provenance, index + 3, payload[offset : offset + chunk_size]), 150
        )
    observed = value.observation
    if expected is None:
        assert observed.outcome is model.InteractObservationOutcome.BYTE_LIMIT
        assert observed.examined_rx_bytes == budget and observed.match is None
    else:
        end, index, start = expected
        assert observed.outcome is model.InteractObservationOutcome.MATCHED
        assert observed.examined_rx_bytes == end
        assert observed.match == model.InteractMatch(
            index,
            model.MonitorMatchStart(start // chunk_size + 3, start % chunk_size),
            model.MonitorMatchEnd(
                (end - 1) // chunk_size + 3, (end - 1) % chunk_size + 1
            ),
        )


def test_loss_resets_every_prefix_and_preserves_examined_budget(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    value = state(
        api,
        provenance,
        request=request(api, conditions=(b"abc", b"bc"), max_rx_bytes=6),
    )
    value.publish(rx(provenance, 3, b"ab"), 150)
    value.publish(loss(provenance, 4), 160)
    value.publish(rx(provenance, 5, b"c"), 170)
    assert value.observation is None
    value.publish(rx(provenance, 6, b"abcTAIL"), 180)
    observed = value.observation
    assert isinstance(observed, model.InteractObservation)
    assert observed.match is not None and observed.match.condition_index == 0
    assert observed.match.start == model.MonitorMatchStart(6, 0)
    assert observed.observer_loss_records == 1
    assert observed.examined_rx_bytes == 6


def test_annotations_advance_window_without_reset_or_byte_charge(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    value = state(api, provenance)
    value.publish(rx(provenance, 3, b"O"), 150)
    value.publish(model.ClientAnnotationEvidence(4, "assertion", "cli", ORIGIN, 5), 160)
    value.publish(rx(provenance, 5, b"K"), 170)
    assert value.observation.match.start == model.MonitorMatchStart(3, 0)
    assert value.observation.match.end == model.MonitorMatchEnd(5, 1)
    assert value.observation.window == model.SequenceRange(3, 6)
    assert value.observation.examined_rx_bytes == 2


@pytest.mark.parametrize(
    "now,expected,included",
    [
        (4_000_099, "matched", True),
        (4_000_100, "timeout", False),
        (4_000_101, "timeout", False),
    ],
)
def test_deadline_equality_excludes_new_rx_without_dut_time_comparison(
    api: Any,
    provenance: model.SegmentProvenance,
    now: int,
    expected: str,
    included: bool,
) -> None:
    value = state(api, provenance)
    value.publish(rx(provenance, 3, b"OK"), now)
    assert value.observation.outcome.value == expected
    assert value.observation.window == model.SequenceRange(3, 4 if included else 3)
    assert value.observation.examined_rx_bytes == (2 if included else 0)


def test_preboundary_rx_cannot_satisfy_completion_and_timer_needs_no_rx(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    value = state(api, provenance)
    value.publish(rx(provenance, 1, b"OK"), 100)
    value.publish(rx(provenance, 2, b"OK"), 100)
    value.advance_time(4_000_099)
    assert value.observation is None
    value.advance_time(4_000_100)
    observed = value.observation
    assert isinstance(observed, model.InteractObservation)
    assert observed.window == model.SequenceRange(3, 3)
    assert observed.examined_rx_bytes == 0
    assert observed.outcome is model.InteractObservationOutcome.TIMEOUT


@pytest.mark.parametrize(
    "payload,expected", [(b"OKTAIL", "matched"), (b"OXKTAIL", "byte_limit")]
)
def test_last_allowed_match_beats_byte_limit_without_slicing_evidence(
    api: Any, provenance: model.SegmentProvenance, payload: bytes, expected: str
) -> None:
    value = state(api, provenance, request=request(api, max_rx_bytes=2))
    record = rx(provenance, 3, payload)
    value.publish(record, 150)
    assert value.observation.outcome.value == expected
    assert value.observation.examined_rx_bytes == 2 and record.payload == payload


@pytest.mark.parametrize("reason", list(model.SegmentEndReason))
@pytest.mark.parametrize("early", ["matched", "timeout", "byte_limit"])
def test_boundaries_still_latch_after_observation_freezes_while_tx_pending(
    api: Any,
    provenance: model.SegmentProvenance,
    reason: model.SegmentEndReason,
    early: str,
) -> None:
    value = state(api, provenance, request=request(api, max_rx_bytes=2))
    value.mark_submitted()
    if early == "timeout":
        value.advance_time(4_000_100)
    else:
        value.publish(rx(provenance, 3, b"OK" if early == "matched" else b"xx"), 150)
    frozen = value.observation
    value.publish(
        model.SegmentEndedEvidence(
            4, provenance.connection_id, provenance.segment_id, reason
        ),
        4_000_101,
    )
    value.settle_write(ack(), 4_000_102)
    expected = (
        "detached" if reason is model.SegmentEndReason.EXPLICIT_STOP else reason.value
    )
    assert value.observation is frozen and frozen.outcome.value == early
    assert value.outcome.value == expected


def test_new_provenance_never_continues_a_literal_across_segments(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    value = state(api, provenance)
    value.mark_submitted()
    value.publish(rx(provenance, 3, b"O"), 150)
    changed = replace(provenance, segment_id=model.SegmentId("next"))
    value.publish(model.SegmentStartedEvidence(4, changed), 160)
    value.publish(rx(changed, 5, b"K"), 170)
    value.settle_write(ack(), 180)
    assert value.observation.match is None
    assert value.observation.window == model.SequenceRange(3, 5)
    assert value.outcome is model.InteractOutcome.TIMESTAMP_ORIGIN_RESET


@pytest.mark.parametrize(
    "status,count,code,overall",
    [
        ("partial", 0, None, "partial_write"),
        ("partial", 1, None, "partial_write"),
        ("timeout", None, None, "write_timeout"),
        ("disconnected", None, None, "disconnected"),
        ("failure", None, backend.BackendFailureKind.IO_FAILURE, "transport_failure"),
    ],
)
@pytest.mark.parametrize("early_match", [False, True])
def test_nonfull_write_never_becomes_success_but_preserves_early_observation(
    api: Any,
    provenance: model.SegmentProvenance,
    status: str,
    count: int | None,
    code: backend.BackendFailureKind | None,
    overall: str,
    early_match: bool,
) -> None:
    value = state(api, provenance)
    value.mark_submitted()
    if early_match:
        value.publish(rx(provenance, 3, b"OK"), 150)
    value.settle_write(
        backend.BackendWriteResult(backend.BackendWriteStatus(status), count, code), 160
    )
    assert value.outcome.value == overall
    assert value.observation.outcome.value == (
        "matched" if early_match else "tx_failed"
    )
    assert value.tx.accepted_prefix_bytes == count


@pytest.mark.parametrize("bad", [None, 2, "ack", object()])
def test_malformed_backend_return_normalizes_without_fabricated_progress(
    api: Any, provenance: model.SegmentProvenance, bad: object
) -> None:
    value = state(api, provenance)
    value.mark_submitted()
    value.settle_write(bad, 150)
    assert value.tx.status is backend.BackendWriteStatus.FAILURE
    assert value.tx.failure_code is backend.BackendFailureKind.INTERNAL_CONTRACT_FAILURE
    assert value.tx.accepted_prefix_bytes is None
    assert value.outcome is model.InteractOutcome.TRANSPORT_FAILURE


@pytest.mark.parametrize(
    "result",
    [ack(1), backend.BackendWriteResult(backend.BackendWriteStatus.PARTIAL, 2, None)],
)
def test_backend_count_must_be_coherent_with_this_exact_payload(
    api: Any, provenance: model.SegmentProvenance, result: backend.BackendWriteResult
) -> None:
    value = state(api, provenance)
    value.mark_submitted()
    value.settle_write(result, 150)
    assert value.tx.accepted_prefix_bytes is None
    assert value.tx.failure_code is backend.BackendFailureKind.INTERNAL_CONTRACT_FAILURE


def test_full_ack_can_precede_observation_and_never_overrules_timeout(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    value = state(api, provenance)
    value.mark_submitted()
    value.settle_write(ack(), 150)
    assert value.observation is None and value.outcome is None
    value.advance_time(4_000_100)
    assert value.outcome is model.InteractOutcome.TIMEOUT


@pytest.mark.parametrize("early,expected", [(True, "matched"), (False, "timeout")])
def test_late_full_ack_keeps_independent_early_match_or_timeout(
    api: Any, provenance: model.SegmentProvenance, early: bool, expected: str
) -> None:
    value = state(api, provenance)
    value.mark_submitted()
    if early:
        value.publish(rx(provenance, 3, b"OK"), 150)
    value.settle_write(ack(), 4_000_101)
    assert value.outcome.value == expected
    assert value.observation.clock.decided_at_ns == (150 if early else 4_000_101)


@pytest.mark.parametrize("submitted", [False, True])
def test_cancellation_suppresses_before_submission_and_waits_after(
    api: Any, provenance: model.SegmentProvenance, submitted: bool
) -> None:
    value = state(api, provenance)
    if submitted:
        value.mark_submitted()
    value.stop((model.InteractOutcome.CANCELLED,), 150)
    assert value.outcome is None
    if submitted:
        value.settle_write(ack(), 160)
    else:
        assert value.mark_submitted() is False
        value.suppress_write(160)
    assert value.outcome is model.InteractOutcome.CANCELLED
    assert value.tx.submitted is submitted
    assert value.tx.accepted_prefix_bytes == (2 if submitted else None)


@pytest.mark.parametrize(
    "outcomes,expected",
    [
        (("cancelled", "detached", "service_stopping"), "service_stopping"),
        (("cancelled", "detached"), "detached"),
        (("cancelled",), "cancelled"),
    ],
)
def test_simultaneous_seal_priority_and_first_latched_event(
    api: Any,
    provenance: model.SegmentProvenance,
    outcomes: tuple[str, ...],
    expected: str,
) -> None:
    value = state(api, provenance)
    value.mark_submitted()
    value.stop(tuple(model.InteractOutcome(o) for o in outcomes), 150)
    value.stop((model.InteractOutcome.TRANSPORT_FAILURE,), 160)
    value.settle_write(ack(), 170)
    assert value.outcome.value == expected


def test_fallback_failure_after_match_and_final_decision_immutability(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    value = state(api, provenance)
    value.mark_submitted()
    value.publish(rx(provenance, 3, b"OK"), 150)
    value.stop((model.InteractOutcome.RECORDING_FAILURE,), 160)
    value.settle_write(ack(), 170)
    frozen = value.observation
    value.stop((model.InteractOutcome.SERVICE_STOPPING,), 180)
    value.publish(rx(provenance, 4, b"ignored"), 190)
    value.advance_time(4_000_100)
    assert value.outcome is model.InteractOutcome.RECORDING_FAILURE
    assert value.observation is frozen and value.tx.accepted_prefix_bytes == 2


@pytest.mark.parametrize(
    "field,bad",
    [
        ("start_sequence", True),
        ("start_sequence", -1),
        ("start_sequence", model.SQLITE_INTEGER_MAX),
        ("provenance", None),
        ("clock_origin_id", ORIGIN.upper()),
        ("started_at_ns", True),
        ("started_at_ns", -1),
        ("started_at_ns", model.SQLITE_INTEGER_MAX),
    ],
)
def test_state_rejects_invalid_boundary_and_clock_before_consuming_records(
    api: Any, provenance: model.SegmentProvenance, field: str, bad: Any
) -> None:
    with pytest.raises((TypeError, ValueError, OverflowError)):
        state(api, provenance, **{field: bad})


def test_maximum_clock_and_empty_max_sequence_boundary_are_exact(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    value = state(
        api,
        provenance,
        start_sequence=model.SQLITE_INTEGER_MAX - 1,
        started_at_ns=model.SQLITE_INTEGER_MAX - 4_000_000,
    )
    value.mark_submitted()
    value.settle_write(ack(), model.SQLITE_INTEGER_MAX - 3_000_000)
    value.advance_time(model.SQLITE_INTEGER_MAX)
    assert value.observation.window == model.SequenceRange(
        model.SQLITE_INTEGER_MAX, model.SQLITE_INTEGER_MAX
    )
    assert value.outcome is model.InteractOutcome.TIMEOUT


def test_state_rejects_reentrant_submission_unowned_settlement_and_clock_regression(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    value = state(api, provenance)
    with pytest.raises(RuntimeError):
        value.settle_write(ack(), 150)
    with pytest.raises(RuntimeError):
        value.suppress_write(150)
    value.mark_submitted()
    with pytest.raises(RuntimeError):
        value.mark_submitted()
    value.publish(rx(provenance, 3, b"O"), 150)
    with pytest.raises(ValueError):
        value.advance_time(149)
    with pytest.raises((TypeError, ValueError)):
        value.advance_time(True)
    value.settle_write(ack(), 160)
    with pytest.raises(RuntimeError):
        value.settle_write(ack(), 170)


def test_monitor_markers_are_non_rx_records_without_resetting_a_prefix(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    from tests.unit.test_operation_evidence import end_draft, start_draft

    value = state(api, provenance)
    value.publish(rx(provenance, 3, b"O"), 150)
    # Construct immutable marker values only, without any append or coordinator.
    start = start_draft()
    value.publish(
        model.OperationStartedEvidence(
            4,
            start.operation_id,
            start.operation_kind,
            provenance,
            start.timeout_ms,
            start.max_rx_bytes,
            start.clock_origin_id,
            start.condition,
        ),
        160,
    )
    end = end_draft()
    value.publish(
        model.OperationEndedEvidence(
            6,
            end.operation_id,
            end.operation_kind,
            end.start_sequence,
            end.window,
            end.outcome,
            end.examined_rx_bytes,
            end.observer_loss_records,
            end.match,
            end.clock,
        ),
        170,
    )
    value.publish(rx(provenance, 7, b"K"), 180)
    assert value.observation.examined_rx_bytes == 2
    assert value.observation.match.start == model.MonitorMatchStart(3, 0)
    assert value.observation.match.end == model.MonitorMatchEnd(7, 1)


@pytest.mark.parametrize("changed", ["connection", "segment", "timestamp_domain"])
def test_mismatched_rx_context_terminates_without_matching_across_it(
    api: Any, provenance: model.SegmentProvenance, changed: str
) -> None:
    value = state(api, provenance)
    value.mark_submitted()
    value.publish(rx(provenance, 3, b"O"), 150)
    record = rx(provenance, 4, b"K")
    if changed == "connection":
        record = replace(record, connection_id=model.ConnectionInstanceId("other"))
    elif changed == "segment":
        record = replace(record, segment_id=model.SegmentId("other"))
    else:
        record = replace(
            record, observed_at=model.BackendObservationTimestamp("other", 1)
        )
    value.publish(record, 160)
    value.settle_write(ack(), 170)
    assert value.outcome is model.InteractOutcome.TIMESTAMP_ORIGIN_RESET
    assert value.observation.match is None
    assert value.observation.examined_rx_bytes == 1


def test_bad_rx_or_record_order_does_not_consume_a_match_prefix(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    value = state(api, provenance)
    value.publish(rx(provenance, 3, b"O"), 150)
    for record in (rx(provenance, 3, b"K"), rx(provenance, 4, b"")):
        with pytest.raises(ValueError):
            value.publish(record, 160)
    with pytest.raises(TypeError):
        value.publish(object(), 160)
    value.publish(rx(provenance, 4, b"K"), 170)
    assert value.observation.match == model.InteractMatch(
        0, model.MonitorMatchStart(3, 0), model.MonitorMatchEnd(4, 1)
    )


def test_full_four_conditions_and_all_byte_values_need_no_text_projection(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    condition = bytes(range(256))
    value = state(
        api,
        provenance,
        request=request(
            api,
            conditions=(b"z" * 256, condition, b"y" * 256, condition),
            max_rx_bytes=1048576,
        ),
    )
    value.publish(rx(provenance, 3, condition[:128]), 150)
    value.publish(rx(provenance, 4, condition[128:]), 160)
    assert value.observation.examined_rx_bytes == 256
    assert value.observation.match == model.InteractMatch(
        1, model.MonitorMatchStart(3, 0), model.MonitorMatchEnd(4, 128)
    )


def test_stop_after_deadline_keeps_observation_timeout_and_actual_write_facts(
    api: Any, provenance: model.SegmentProvenance
) -> None:
    value = state(api, provenance)
    value.mark_submitted()
    value.stop((model.InteractOutcome.DETACHED,), 4_000_100)
    value.settle_write(ack(), 4_000_101)
    assert value.observation.outcome is model.InteractObservationOutcome.TIMEOUT
    assert value.outcome is model.InteractOutcome.DETACHED
    assert value.tx.accepted_prefix_bytes == 2


@pytest.mark.parametrize(
    "bad",
    [
        (),
        [],
        ("cancelled",),
        (model.InteractOutcome.MATCHED,),
        (model.InteractOutcome.RECORDING_FAILURE, model.InteractOutcome.CANCELLED),
    ],
)
def test_external_stop_rejects_coercion_and_undeclared_multi_event_order(
    api: Any, provenance: model.SegmentProvenance, bad: Any
) -> None:
    value = state(api, provenance)
    with pytest.raises((TypeError, ValueError)):
        value.stop(bad, 150)
    assert value.mark_submitted() is True
