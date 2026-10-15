"""Pure Monitor bounds, decision facts and ordinary exception transport."""

from dataclasses import FrozenInstanceError, fields, replace
from typing import cast

import pytest

from dutchmate_core import model, monitor
from dutchmate_core.evidence import JournalFailureKind
from tests.unit.test_sqlite_evidence_codec import _basic_provenance, _segment_started

ORIGIN = "12345678-1234-1234-1234-123456789abc"
OPERATION = "abcdefab-1234-1234-1234-123456789abc"


def report() -> monitor.MonitorReport:
    return monitor.MonitorReport(
        run_id="opaque run",
        session_id=model.SessionId("session"),
        operation_id=OPERATION,
        provenance=_segment_started(_basic_provenance()).provenance,
        outcome=model.MonitorOutcome.TIMEOUT,
        started_record=model.EvidenceReference(model.SessionId("session"), 2),
        ended_record=model.EvidenceReference(model.SessionId("session"), 3),
        window=model.SequenceRange(3, 3),
        examined_rx_bytes=0,
        observer_loss_records=0,
        match=None,
        clock=model.MonitorClockFacts(ORIGIN, 0, 1_000_000, 1_000_000),
        durability="complete",
        end_failure=None,
    )


@pytest.mark.parametrize("condition", [b"a", bytes(range(256))])
@pytest.mark.parametrize("timeout", [1, 4000])
@pytest.mark.parametrize("limit", [1, 1048576])
def test_request_accepts_exact_bounds(
    condition: bytes, timeout: int, limit: int
) -> None:
    request = monitor.MonitorRequest(model.SessionId("s"), condition, timeout, limit)
    assert request.condition is condition


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("session_id", "s"),
        ("condition", b""),
        ("condition", b"x" * 257),
        ("condition", bytearray(b"x")),
        ("condition", "x"),
        ("condition", None),
        ("timeout_ms", 0),
        ("timeout_ms", 4001),
        ("timeout_ms", True),
        ("timeout_ms", 1.0),
        ("timeout_ms", "1"),
        ("timeout_ms", None),
        ("max_rx_bytes", 0),
        ("max_rx_bytes", 1048577),
        ("max_rx_bytes", False),
        ("max_rx_bytes", 1.0),
        ("max_rx_bytes", None),
    ],
)
def test_request_rejects_coercions_and_invalid_bounds(field: str, bad: object) -> None:
    good = monitor.MonitorRequest(model.SessionId("s"), b"x", 1, 1)
    with pytest.raises((TypeError, ValueError)):
        replace(good, **{field: bad})  # type: ignore[arg-type]


def test_request_has_no_defaults_or_client_cursor() -> None:
    with pytest.raises(TypeError):
        monitor.MonitorRequest(model.SessionId("s"), b"x", 1)  # type: ignore[call-arg]
    assert [f.name for f in fields(monitor.MonitorRequest)] == [
        "session_id",
        "condition",
        "timeout_ms",
        "max_rx_bytes",
    ]


@pytest.mark.parametrize("origin", ["", ORIGIN.upper(), "{" + ORIGIN + "}", None, 1])
def test_clock_origin_is_canonical_uuid(origin: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        model.MonitorClockFacts(cast(str, origin), 0, 1, 1)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("started_at_ns", -1),
        ("started_at_ns", True),
        ("deadline_at_ns", model.SQLITE_INTEGER_MAX + 1),
        ("decided_at_ns", None),
        ("decided_at_ns", 1.0),
        ("deadline_at_ns", 0),
        ("decided_at_ns", -1),
    ],
)
def test_clock_bounds_and_order(field: str, bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(model.MonitorClockFacts(ORIGIN, 0, 1, 1), **{field: bad})  # type: ignore[arg-type]


def test_clock_accepts_maximum_signed_integer() -> None:
    assert (
        model.MonitorClockFacts(ORIGIN, 0, 1, model.SQLITE_INTEGER_MAX).decided_at_ns
        == model.SQLITE_INTEGER_MAX
    )


def test_report_fields_and_durability_are_closed() -> None:
    value = report()
    assert [f.name for f in fields(value)] == [
        "run_id",
        "session_id",
        "operation_id",
        "provenance",
        "outcome",
        "started_record",
        "ended_record",
        "window",
        "examined_rx_bytes",
        "observer_loss_records",
        "match",
        "clock",
        "durability",
        "end_failure",
    ]
    for kind in JournalFailureKind:
        failure = monitor.MonitorEndFailure("journal", kind.value)
        changed = replace(
            value, durability="end_unconfirmed", ended_record=None, end_failure=failure
        )
        assert changed.outcome is model.MonitorOutcome.TIMEOUT
    replace(
        value,
        durability="end_unconfirmed",
        ended_record=None,
        end_failure=monitor.MonitorEndFailure("service", "internal_failure"),
    )
    with pytest.raises(FrozenInstanceError):
        value.outcome = model.MonitorOutcome.MATCHED  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("run_id", ""),
        ("run_id", 1),
        ("operation_id", OPERATION.upper()),
        ("provenance", None),
        ("outcome", "timeout"),
        ("started_record", None),
        ("ended_record", None),
        ("durability", "unknown"),
        ("durability", "end_unconfirmed"),
        ("end_failure", "oops"),
        ("examined_rx_bytes", True),
        ("examined_rx_bytes", -1),
        ("examined_rx_bytes", 1048577),
        ("observer_loss_records", -1),
        ("observer_loss_records", model.SQLITE_INTEGER_MAX + 1),
        ("window", model.SequenceRange(2, 3)),
        ("outcome", model.MonitorOutcome.MATCHED),
        ("outcome", model.MonitorOutcome.BYTE_LIMIT),
        ("clock", model.MonitorClockFacts(ORIGIN, 0, 100, 99)),
        ("ended_record", model.EvidenceReference(model.SessionId("other"), 3)),
    ],
)
def test_report_rejects_inconsistent_facts(field: str, bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(report(), **{field: bad})  # type: ignore[arg-type]


@pytest.mark.parametrize("outcome", list(model.MonitorOutcome))
def test_outcome_match_and_deadline_relationships(
    outcome: model.MonitorOutcome,
) -> None:
    matched = model.MonitorMatch(
        model.MonitorMatchStart(3, 0), model.MonitorMatchEnd(3, 1)
    )
    value = replace(
        report(),
        outcome=outcome,
        window=model.SequenceRange(3, 4),
        ended_record=model.EvidenceReference(model.SessionId("session"), 4),
        examined_rx_bytes=1,
        match=matched if outcome is model.MonitorOutcome.MATCHED else None,
        clock=model.MonitorClockFacts(
            ORIGIN, 0, 10, 10 if outcome is model.MonitorOutcome.TIMEOUT else 9
        ),
    )
    assert value.outcome is outcome
    with pytest.raises(ValueError):
        replace(value, match=None if value.match else matched)
    with pytest.raises(ValueError):
        replace(
            value,
            clock=model.MonitorClockFacts(
                ORIGIN, 0, 10, 9 if outcome is model.MonitorOutcome.TIMEOUT else 10
            ),
        )


@pytest.mark.parametrize(
    ("source", "code"),
    [("journal", "unknown"), ("service", "busy"), ("x", "internal_failure")],
)
def test_end_failure_is_normalized(source: str, code: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        monitor.MonitorEndFailure(cast("monitor.MonitorFailureSource", source), code)


@pytest.mark.parametrize(
    "kind",
    [
        "no_associated_session",
        "session_not_associated",
        "not_active",
        "monitor_unavailable",
        "capability_unavailable",
        "busy",
        "evidence_policy_incompatible",
    ],
)
def test_rejections_seal_facts_but_allow_exception_transport(kind: str) -> None:
    error = monitor.MonitorRejected(cast("monitor.MonitorRejectedKind", kind))
    with pytest.raises(FrozenInstanceError):
        error.kind = "busy"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        del error.kind
    try:
        raise error
    except monitor.MonitorRejected as caught:
        assert caught.__traceback__ is not None
        caught.__cause__ = ValueError()
        caught.add_note("transport note")
    assert str(error) == kind
    with pytest.raises(TypeError):
        monitor.MonitorRejected(cast("monitor.MonitorRejectedKind", "other"))
