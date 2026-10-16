"""Annotation invariants, without runtime admission or delivery behavior."""

from dataclasses import FrozenInstanceError, replace

import pytest

from dutchmate_core import evidence, model, monitor

ORIGIN = "12345678-1234-1234-1234-123456789abc"


def draft() -> evidence.PendingClientAnnotationEvidence:
    return evidence.PendingClientAnnotationEvidence(
        text="  build e\u0301; 雪\nstep\t1  ",
        client_surface="cli",
        clock_origin_id=ORIGIN,
        received_at_ns=17,
    )


def record() -> model.ClientAnnotationEvidence:
    return model.ClientAnnotationEvidence(
        sequence=7,
        text=draft().text,
        client_surface="cli",
        clock_origin_id=ORIGIN,
        received_at_ns=17,
    )


@pytest.mark.parametrize("text", ["x", "é" * 512, "x" * 1024, " \n\r\t ", "e\u0301"])
@pytest.mark.parametrize("surface", ["cli", "http", "core"])
def test_request_preserves_exact_unicode_text_and_declared_surface(
    text: str, surface: str
) -> None:
    from dutchmate_core.annotation import AnnotationRequest

    request = AnnotationRequest(model.SessionId("opaque/session"), text, surface)
    assert request.text == text
    assert request.text.encode() == text.encode()
    assert request.client_surface == surface
    with pytest.raises(FrozenInstanceError):
        request.text = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("text", ""),
        ("text", "x" * 1025),
        ("text", "é" * 513),
        ("text", "a\x00b"),
        ("text", "\ud800"),
        ("text", "\udfff"),
        ("text", b"bytes"),
        ("text", None),
        ("text", True),
        ("client_surface", "CLI"),
        ("client_surface", " cli"),
        ("client_surface", "dut"),
        ("client_surface", None),
    ],
)
def test_request_and_both_record_forms_reject_invalid_content(
    field: str, bad: object
) -> None:
    from dutchmate_core.annotation import AnnotationRequest

    request = AnnotationRequest(model.SessionId("s"), "claim", "cli")
    for value in (request, draft(), record()):
        with pytest.raises((TypeError, ValueError)):
            replace(value, **{field: bad})  # type: ignore[arg-type]


def test_request_requires_explicit_typed_session() -> None:
    from dutchmate_core.annotation import AnnotationRequest

    with pytest.raises(TypeError):
        AnnotationRequest("s", "claim", "cli")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        AnnotationRequest(model.SessionId("s"), "claim")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("clock_origin_id", ORIGIN.upper()),
        ("clock_origin_id", "host"),
        ("clock_origin_id", ORIGIN.replace("-", "")),
        ("clock_origin_id", None),
        ("received_at_ns", -1),
        ("received_at_ns", model.SQLITE_INTEGER_MAX + 1),
        ("received_at_ns", True),
        ("received_at_ns", 1.0),
    ],
)
def test_annotation_time_requires_canonical_host_origin_and_finite_exact_integer(
    field: str, bad: object
) -> None:
    for value in (draft(), record()):
        with pytest.raises((TypeError, ValueError)):
            replace(value, **{field: bad})  # type: ignore[arg-type]


@pytest.mark.parametrize("time", [0, model.SQLITE_INTEGER_MAX])
@pytest.mark.parametrize("sequence", [0, model.SQLITE_INTEGER_MAX - 1])
def test_assignment_keeps_host_time_and_fixed_assertion_class(
    time: int, sequence: int
) -> None:
    pending = replace(draft(), received_at_ns=time)
    assigned = evidence._assign_sequence(pending, sequence)
    assert isinstance(assigned, model.ClientAnnotationEvidence)
    assert assigned.sequence == sequence
    assert assigned.text == "  build e\u0301; 雪\nstep\t1  "
    assert assigned.clock_origin_id == ORIGIN
    assert assigned.received_at_ns == time
    for value in (pending, assigned):
        assert value.assertion_class == "client_assertion"
        assert value.attribution_basis == "client_asserted"
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            value.assertion_class = "dut_observation"  # type: ignore[misc,assignment]


@pytest.mark.parametrize("sequence", [-1, True, 1.0, model.SQLITE_INTEGER_MAX])
def test_annotation_record_sequence_uses_existing_persisted_bound(
    sequence: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(record(), sequence=sequence)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_in_memory_materialization_uses_ordinary_sequence_and_preserves_text() -> (
    None
):
    recorder = evidence.InMemoryEvidenceRecorder()
    accepted = await recorder.append(draft())
    assert isinstance(accepted, model.ClientAnnotationEvidence)
    assert accepted.sequence == 0
    assert accepted.text.encode() == b"  build e\xcc\x81; \xe9\x9b\xaa\nstep\t1  "
    assert recorder.snapshot() == (accepted,)


def test_receipt_binds_acknowledged_record_to_session_and_reference() -> None:
    from dutchmate_core.annotation import AnnotationReceipt

    session = model.SessionId("s")
    value = AnnotationReceipt(
        "run", session, model.EvidenceReference(session, 7), record()
    )
    assert value.annotation.text == record().text
    for changes in (
        {"run_id": ""},
        {"session_id": "s"},
        {"annotation": None},
        {"reference": model.EvidenceReference(model.SessionId("other"), 7)},
        {"reference": model.EvidenceReference(session, 8)},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(value, **changes)


@pytest.mark.parametrize(
    "kind",
    [
        "no_associated_session",
        "session_not_associated",
        "not_active",
        "annotation_unavailable",
        "evidence_policy_incompatible",
        "busy",
        "rate_limited",
    ],
)
def test_rejection_facts_are_sealed_but_exception_transport_is_writable(
    kind: str,
) -> None:
    from dutchmate_core.annotation import AnnotationRejected

    error = AnnotationRejected(kind)  # type: ignore[arg-type]
    with pytest.raises(AnnotationRejected) as raised:
        raise error
    assert raised.value.kind == kind
    error.add_note("transport note")
    error.__traceback__ = None
    error.__cause__ = RuntimeError("normalized elsewhere")
    with pytest.raises(FrozenInstanceError):
        error.kind = "busy"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        delattr(error, "kind")
    with pytest.raises(TypeError):
        AnnotationRejected("unknown")  # type: ignore[arg-type]


class Clock:
    origin_id = ORIGIN

    def now_ns(self) -> int:
        raise AssertionError("pure access values must not sample time")

    async def wait_until(self, deadline_ns: int) -> None:
        raise AssertionError("pure access values must not start a waiter")


class Recorder(evidence.InMemoryEvidenceRecorder):
    session_id = model.SessionId("s")
    policy = model.SessionPolicy(
        max_retained_records=100,
        max_retained_charged_bytes=100000,
        max_record_charged_bytes=10000,
        max_database_pages=100,
        max_retrieval_page_records=100,
        max_retrieval_page_charged_bytes=100000,
    )

    async def close(self) -> None:
        pass


def test_prepared_access_validates_identity_clock_and_callback_without_io() -> None:
    from dutchmate_core.annotation import PreparedAnnotationAccess

    recorder = Recorder()
    clock = Clock()
    coordinator = monitor.MonitorRecordingCoordinator(recorder=recorder, clock=clock)

    def charge(value: evidence.PendingClientAnnotationEvidence) -> int:
        raise AssertionError("pure access values must not encode/append")

    access = PreparedAnnotationAccess(
        recorder.session_id, recorder.policy, coordinator, clock, charge
    )
    for changes in (
        {"session_id": model.SessionId("other")},
        {"session_id": "s"},
        {"policy": None},
        {"coordinator": object()},
        {"clock": Clock()},
        {"charge_annotation": None},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(access, **changes)
