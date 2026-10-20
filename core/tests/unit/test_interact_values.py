"""Pure Interact invariants; no writer, runtime, journal or Profile activation."""

import importlib
from dataclasses import FrozenInstanceError, replace
from typing import Any

import pytest

from dutchmate_core import backend, model
from dutchmate_core.evidence import JournalFailureKind
from tests.unit.test_sqlite_evidence_codec import _basic_provenance, _segment_started

ORIGIN = "12345678-1234-1234-1234-123456789abc"
OPERATION = "abcdefab-1234-1234-1234-123456789abc"
SESSION = model.SessionId("session")


class _PureApi:
    def __getattr__(self, name: str) -> Any:
        # Resolve in the test body, never during collection or fixture setup.
        try:
            module = importlib.import_module("dutchmate_core.interact")
        except ModuleNotFoundError as error:
            if error.name != "dutchmate_core.interact":
                raise
            pytest.fail("T002 requires the pure Interact values")
        return getattr(module, name)


@pytest.fixture
def api() -> Any:
    return _PureApi()


def request(api: Any, **changes: Any) -> Any:
    values = dict(
        session_id=SESSION,
        payload=b"\0\xff",
        conditions=(b"OK", b"FAIL"),
        timeout_ms=4,
        max_rx_bytes=100,
    )
    values.update(changes)
    return api.InteractRequest(**values)


def tx(api: Any, **changes: Any) -> Any:
    values = dict(
        submitted=True,
        status=backend.BackendWriteStatus.ACKNOWLEDGED,
        accepted_prefix_bytes=2,
        failure_code=None,
        acknowledgement_scope="backend_acceptance",
        clock_origin_id=ORIGIN,
        settled_at_ns=200,
    )
    values.update(changes)
    return api.InteractTxFacts(**values)


def observation(**changes: Any) -> Any:
    values: dict[str, Any] = dict(
        window=model.SequenceRange(3, 3),
        outcome=model.InteractObservationOutcome.TIMEOUT,
        examined_rx_bytes=0,
        observer_loss_records=0,
        match=None,
        clock=model.MonitorClockFacts(ORIGIN, 100, 4_000_100, 4_000_100),
    )
    values.update(changes)
    return model.InteractObservation(**values)


def report(api: Any, **changes: Any) -> Any:
    values = dict(
        run_id="opaque run",
        session_id=SESSION,
        operation_id=OPERATION,
        provenance=_segment_started(_basic_provenance()).provenance,
        payload=b"\0\xff",
        conditions=(b"OK", b"FAIL"),
        outcome=model.InteractOutcome.TIMEOUT,
        started_record=model.EvidenceReference(SESSION, 2),
        tx_settled_record=model.EvidenceReference(SESSION, 3),
        ended_record=model.EvidenceReference(SESSION, 4),
        tx=tx(api),
        observation=observation(),
        durability="complete",
        audit_failures=(),
    )
    values.update(changes)
    return api.InteractReport(**values)


@pytest.mark.parametrize("payload", [b"\0", bytes(range(256)), bytes(range(256)) * 16])
@pytest.mark.parametrize("conditions", [(b"a",), (bytes(range(256)),) * 4])
@pytest.mark.parametrize("timeout,limit", [(1, 1), (4000, 1048576)])
def test_request_preserves_binary_bytes_and_order_at_bounds(
    api: Any, payload: bytes, conditions: tuple[bytes, ...], timeout: int, limit: int
) -> None:
    value = request(
        api,
        payload=payload,
        conditions=conditions,
        timeout_ms=timeout,
        max_rx_bytes=limit,
    )
    assert value.payload == payload and value.conditions == conditions
    with pytest.raises(FrozenInstanceError):
        value.payload = b"replacement"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("session_id", "s"),
        ("session_id", None),
        ("payload", b""),
        ("payload", b"x" * 4097),
        ("payload", bytearray(b"x")),
        ("payload", memoryview(b"x")),
        ("payload", "x"),
        ("payload", None),
        ("conditions", []),
        ("conditions", ()),
        ("conditions", (b"x",) * 5),
        ("conditions", (b"",)),
        ("conditions", (b"x" * 257,)),
        ("conditions", (bytearray(b"x"),)),
        ("conditions", ("x",)),
        ("conditions", b"x"),
        ("conditions", None),
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
        ("max_rx_bytes", model.SQLITE_INTEGER_MAX + 1),
    ],
)
def test_request_rejects_coercion_empty_mutable_and_out_of_bound_inputs(
    api: Any, field: str, bad: Any
) -> None:
    with pytest.raises((TypeError, ValueError)):
        request(api, **{field: bad})


def test_request_rejects_hidden_policy_cursor_defaults_and_unknown_fields(
    api: Any,
) -> None:
    with pytest.raises(TypeError):
        api.InteractRequest(SESSION, b"x", (b"x",), 1)
    for field in ("uart_tx_enabled", "start_sequence", "write_timeout_ms", "extra"):
        with pytest.raises(TypeError):
            request(api, **{field: True})


def test_core_session_identity_is_opaque_not_a_wire_validation_rule(api: Any) -> None:
    value = request(api, session_id=model.SessionId("opaque\0" + "é" * 257))
    assert value.session_id.value == "opaque\0" + "é" * 257


@pytest.mark.parametrize(
    "status,count,code",
    [
        ("acknowledged", 1, None),
        ("acknowledged", 4096, None),
        ("partial", 0, None),
        ("partial", 4095, None),
        ("timeout", None, None),
        ("disconnected", None, None),
        *[("failure", None, kind) for kind in backend.BackendFailureKind],
    ],
)
def test_backend_result_distinguishes_known_prefix_and_unknown_progress(
    api: Any, status: str, count: int | None, code: backend.BackendFailureKind | None
) -> None:
    value = backend.BackendWriteResult(backend.BackendWriteStatus(status), count, code)
    assert value.accepted_prefix_bytes == count
    with pytest.raises(FrozenInstanceError):
        value.accepted_prefix_bytes = 0  # type: ignore[misc]


@pytest.mark.parametrize(
    "status,count,code",
    [
        ("acknowledged", 0, None),
        ("acknowledged", 4097, None),
        ("acknowledged", None, None),
        ("partial", 4096, None),
        ("partial", -1, None),
        ("partial", True, None),
        ("partial", 1.0, None),
        ("timeout", 0, None),
        ("timeout", 2, None),
        ("disconnected", 0, None),
        ("failure", 0, backend.BackendFailureKind.IO_FAILURE),
        ("failure", None, None),
        ("failure", None, "io_failure"),
        ("acknowledged", 2, backend.BackendFailureKind.IO_FAILURE),
        ("timeout", None, backend.BackendFailureKind.IO_FAILURE),
    ],
)
def test_backend_result_rejects_invented_progress_and_inconsistent_failure(
    api: Any, status: str, count: Any, code: Any
) -> None:
    with pytest.raises((TypeError, ValueError)):
        backend.BackendWriteResult(backend.BackendWriteStatus(status), count, code)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("submitted", 1),
        ("submitted", None),
        ("status", "acknowledged"),
        ("accepted_prefix_bytes", True),
        ("accepted_prefix_bytes", 4097),
        ("acknowledgement_scope", "dut_receipt"),
        ("acknowledgement_scope", "wire_transmission"),
        ("clock_origin_id", ORIGIN.upper()),
        ("clock_origin_id", None),
        ("settled_at_ns", -1),
        ("settled_at_ns", True),
        ("settled_at_ns", model.SQLITE_INTEGER_MAX + 1),
    ],
)
def test_tx_facts_reject_unsafe_ack_claims_and_invalid_clock(
    api: Any, field: str, bad: Any
) -> None:
    with pytest.raises((TypeError, ValueError)):
        tx(api, **{field: bad})


def test_suppression_is_not_a_zero_byte_write_ack(api: Any) -> None:
    value = tx(api, submitted=False, status="not_submitted", accepted_prefix_bytes=None)
    assert value.accepted_prefix_bytes is None and not value.submitted
    for changes in (
        dict(accepted_prefix_bytes=0),
        dict(submitted=True),
        dict(failure_code=backend.BackendFailureKind.IO_FAILURE),
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(value, **changes)


@pytest.mark.parametrize(
    "outcome",
    [
        "matched",
        "timeout",
        "byte_limit",
        "disconnected",
        "detached",
        "timestamp_origin_reset",
        "recording_failure",
        "transport_failure",
        "service_stopping",
        "cancelled",
        "tx_failed",
    ],
)
def test_observation_match_and_deadline_are_independent_of_tx(
    api: Any, outcome: str
) -> None:
    match = model.InteractMatch(
        1, model.MonitorMatchStart(3, 0), model.MonitorMatchEnd(3, 2)
    )
    value = observation(
        outcome=model.InteractObservationOutcome(outcome),
        window=model.SequenceRange(3, 4),
        examined_rx_bytes=2,
        match=match if outcome == "matched" else None,
        clock=model.MonitorClockFacts(
            ORIGIN, 100, 4_000_100, 4_000_100 if outcome == "timeout" else 200
        ),
    )
    assert value.outcome.value == outcome
    with pytest.raises((TypeError, ValueError)):
        replace(value, match=None if outcome == "matched" else match)
    with pytest.raises(ValueError):
        replace(
            value,
            clock=model.MonitorClockFacts(
                ORIGIN, 100, 4_000_100, 200 if outcome == "timeout" else 4_000_100
            ),
        )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("window", None),
        ("window", model.SequenceRange(0, 1)),
        ("outcome", "timeout"),
        ("examined_rx_bytes", -1),
        ("examined_rx_bytes", True),
        ("examined_rx_bytes", 1048577),
        ("observer_loss_records", False),
        ("observer_loss_records", -1),
        ("observer_loss_records", model.SQLITE_INTEGER_MAX + 1),
        ("clock", None),
    ],
)
def test_observation_rejects_unvalidated_or_overflowed_facts(
    api: Any, field: str, bad: Any
) -> None:
    with pytest.raises((TypeError, ValueError)):
        observation(**{field: bad})


@pytest.mark.parametrize("index", [-1, 4, True, 0.0, None])
def test_match_requires_bounded_exact_condition_index(api: Any, index: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        model.InteractMatch(
            index, model.MonitorMatchStart(3, 0), model.MonitorMatchEnd(3, 1)
        )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("run_id", ""),
        ("run_id", 1),
        ("session_id", "session"),
        ("operation_id", OPERATION.upper()),
        ("provenance", None),
        ("payload", b""),
        ("conditions", ()),
        ("outcome", "timeout"),
        ("started_record", None),
        ("started_record", model.EvidenceReference(SESSION, model.SQLITE_INTEGER_MAX)),
        ("started_record", model.EvidenceReference(model.SessionId("other"), 2)),
        ("started_record", model.EvidenceReference(SESSION, 1)),
        ("tx_settled_record", model.EvidenceReference(SESSION, 2)),
        ("tx_settled_record", model.EvidenceReference(SESSION, 4)),
        ("tx_settled_record", model.EvidenceReference(model.SessionId("other"), 3)),
        ("ended_record", model.EvidenceReference(SESSION, 3)),
        ("ended_record", model.EvidenceReference(SESSION, model.SQLITE_INTEGER_MAX)),
        ("ended_record", model.EvidenceReference(model.SessionId("other"), 4)),
        ("tx", None),
        ("observation", None),
        ("durability", "unknown"),
        ("durability", "tx_unconfirmed"),
        ("audit_failures", []),
    ],
)
def test_report_rejects_identity_reference_and_durability_contradictions(
    api: Any, field: str, bad: Any
) -> None:
    with pytest.raises((TypeError, ValueError)):
        report(api, **{field: bad})


@pytest.mark.parametrize(
    "tx_bad,end_bad,label",
    [
        (False, False, "complete"),
        (True, False, "tx_unconfirmed"),
        (False, True, "end_unconfirmed"),
        (True, True, "both_unconfirmed"),
    ],
)
def test_audit_ack_failures_never_erase_actual_tx_or_observation(
    api: Any, tx_bad: bool, end_bad: bool, label: str
) -> None:
    failures = tuple(
        api.InteractAuditFailure(kind, "journal", "busy")
        for kind, bad in (("uart_tx_settled", tx_bad), ("interact_ended", end_bad))
        if bad
    )
    value = report(
        api,
        tx_settled_record=None if tx_bad else model.EvidenceReference(SESSION, 3),
        ended_record=None if end_bad else model.EvidenceReference(SESSION, 4),
        durability=label,
        audit_failures=failures,
    )
    assert value.tx.accepted_prefix_bytes == 2
    assert value.observation.outcome is model.InteractObservationOutcome.TIMEOUT
    with pytest.raises(FrozenInstanceError):
        value.durability = "complete"


@pytest.mark.parametrize("code", [kind.value for kind in JournalFailureKind])
def test_audit_failure_accepts_only_normalized_declared_categories(
    api: Any, code: str
) -> None:
    value = api.InteractAuditFailure("uart_tx_settled", "journal", code)
    assert value.code == code
    with pytest.raises(ValueError):
        api.InteractAuditFailure("uart_tx_settled", "journal", "private traceback")


def test_report_validates_tx_against_payload_and_captured_clock(api: Any) -> None:
    for changes in (
        dict(accepted_prefix_bytes=1),
        dict(settled_at_ns=99),
        dict(clock_origin_id=OPERATION),
    ):
        with pytest.raises(ValueError):
            report(api, tx=tx(api, **changes))
    with pytest.raises(ValueError):
        report(api, tx=tx(api, status=backend.BackendWriteStatus.PARTIAL))


def test_frozen_observation_match_can_coexist_with_external_overall_outcome(
    api: Any,
) -> None:
    matched = observation(
        window=model.SequenceRange(3, 4),
        outcome=model.InteractObservationOutcome.MATCHED,
        examined_rx_bytes=2,
        match=model.InteractMatch(
            0, model.MonitorMatchStart(3, 0), model.MonitorMatchEnd(3, 2)
        ),
        clock=model.MonitorClockFacts(ORIGIN, 100, 4_000_100, 150),
    )
    value = report(
        api,
        observation=matched,
        outcome=model.InteractOutcome.DISCONNECTED,
        tx_settled_record=model.EvidenceReference(SESSION, 4),
        ended_record=model.EvidenceReference(SESSION, 5),
    )
    assert value.observation.match.condition_index == 0
    assert value.outcome is model.InteractOutcome.DISCONNECTED
    with pytest.raises(ValueError):
        report(
            api,
            observation=replace(
                matched, match=replace(matched.match, condition_index=2)
            ),
        )
    with pytest.raises(ValueError):
        report(
            api,
            observation=matched,
            outcome=model.InteractOutcome.MATCHED,
            tx=tx(
                api,
                status=backend.BackendWriteStatus.TIMEOUT,
                accepted_prefix_bytes=None,
            ),
        )


@pytest.mark.parametrize(
    "changes",
    [
        dict(outcome=model.InteractObservationOutcome.BYTE_LIMIT),
        dict(examined_rx_bytes=1),
        dict(observer_loss_records=1),
        dict(clock=model.MonitorClockFacts(ORIGIN, 100, 4_000_100, 200)),
    ],
)
def test_empty_observation_cannot_claim_rx_loss_or_early_timeout(
    api: Any, changes: Any
) -> None:
    with pytest.raises(ValueError):
        observation(**changes)


def test_unknown_progress_is_not_coerced_from_a_raw_status_string(api: Any) -> None:
    with pytest.raises(TypeError):
        backend.BackendWriteResult("timeout", None, None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "failures",
    [
        (("uart_tx_settled", "journal", "busy"),) * 2,
        (("interact_ended", "journal", "busy"), ("uart_tx_settled", "journal", "busy")),
        (("uart_tx_settled", "journal", "busy"),) * 3,
    ],
)
def test_unconfirmed_refs_require_one_ordered_failure_each(
    api: Any, failures: Any
) -> None:
    with pytest.raises((TypeError, ValueError)):
        report(
            api,
            tx_settled_record=None,
            ended_record=None,
            durability="both_unconfirmed",
            audit_failures=tuple(api.InteractAuditFailure(*f) for f in failures),
        )


@pytest.mark.parametrize(
    "kind,source,code",
    [
        ("rx", "journal", "busy"),
        ("interact_ended", "service", "busy"),
        ("uart_tx_settled", "backend", "io_failure"),
    ],
)
def test_audit_failure_cannot_embed_backend_or_unbounded_diagnostics(
    api: Any, kind: Any, source: Any, code: str
) -> None:
    with pytest.raises((TypeError, ValueError)):
        api.InteractAuditFailure(kind, source, code)


def test_internal_audit_failure_preserves_unknown_commit_without_ref(api: Any) -> None:
    value = report(
        api,
        ended_record=None,
        durability="end_unconfirmed",
        audit_failures=(
            api.InteractAuditFailure("interact_ended", "service", "internal_failure"),
        ),
    )
    assert value.tx.status is backend.BackendWriteStatus.ACKNOWLEDGED
    assert value.ended_record is None
