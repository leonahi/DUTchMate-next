"""Value-model contracts for the durable evidence journal."""

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from dutchmate_core import evidence, model


def _policy(**overrides: int) -> model.SessionPolicy:
    values = {
        "max_retained_records": 100,
        "max_retained_charged_bytes": 10_000,
        "max_record_charged_bytes": 1_000,
        "max_database_pages": 100,
        "max_retrieval_page_records": 25,
        "max_retrieval_page_charged_bytes": 2_000,
    }
    values.update(overrides)
    return model.SessionPolicy(**values)


def _session_id(value: str = "session/opaque:17") -> model.SessionId:
    return model.SessionId(value)


def _timestamp_endpoint(value: int = 41) -> model.RetentionTimestampEndpoint:
    return model.RetentionTimestampEndpoint(
        timestamp=model.BackendObservationTimestamp("domain-1", value),
        domain=model.BackendObservationTimestampDomain(
            domain_id="domain-1",
            observer=model.TimestampObserver.HOST,
            meaning=model.TimestampMeaning.OBSERVATION,
            unit=model.TimestampUnit.NANOSECOND,
            origin_id="origin-1",
        ),
    )


def test_session_id_is_non_empty_opaque_and_immutable() -> None:
    session_id = _session_id()

    assert session_id.value == "session/opaque:17"
    with pytest.raises(FrozenInstanceError):
        session_id.value = "replacement"  # type: ignore[misc]
    with pytest.raises(ValueError, match="non-empty"):
        model.SessionId("")


@pytest.mark.parametrize(
    "field_name",
    [
        "max_retained_records",
        "max_retained_charged_bytes",
        "max_record_charged_bytes",
        "max_database_pages",
        "max_retrieval_page_records",
        "max_retrieval_page_charged_bytes",
    ],
)
@pytest.mark.parametrize("value", [0, -1, 2**63])
def test_session_policy_requires_positive_signed_64_bit_values(
    field_name: str,
    value: int,
) -> None:
    with pytest.raises(ValueError):
        _policy(**{field_name: value})


def test_session_policy_rejects_boolean_limits() -> None:
    with pytest.raises(TypeError, match="integer"):
        _policy(max_retained_records=cast("int", True))


def test_session_policy_keeps_retrieval_ceilings_independent_from_retention() -> None:
    policy = _policy(
        max_retained_records=2,
        max_retained_charged_bytes=100_000,
        max_record_charged_bytes=500,
        max_retrieval_page_records=50,
        max_retrieval_page_charged_bytes=500,
    )

    assert policy.max_retained_records == 2
    assert policy.max_retrieval_page_records == 50
    assert policy.max_retained_charged_bytes == 100_000
    assert policy.max_retrieval_page_charged_bytes == 500


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"max_record_charged_bytes": 10_001}, "retained"),
        (
            {
                "max_record_charged_bytes": 2_001,
                "max_retained_charged_bytes": 10_000,
            },
            "retrieval",
        ),
    ],
)
def test_session_policy_requires_every_record_to_fit_retention_and_retrieval(
    override: dict[str, int],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        _policy(**override)


@pytest.mark.parametrize("value", [0, 2**63 - 1])
def test_persisted_counter_accepts_signed_64_bit_endpoints(value: int) -> None:
    assert model.validate_persisted_counter(value, name="counter") == value


@pytest.mark.parametrize("value", [-1, 2**63])
def test_persisted_counter_rejects_values_outside_signed_64_bit(value: int) -> None:
    with pytest.raises(ValueError, match="counter"):
        model.validate_persisted_counter(value, name="counter")


def test_checked_persisted_addition_rejects_overflow() -> None:
    with pytest.raises(model.PersistedCounterOverflowError):
        model.checked_persisted_add(
            model.SQLITE_INTEGER_MAX,
            1,
            name="discarded record count",
        )


def test_record_sequence_excludes_terminal_next_sequence_value() -> None:
    assert model.validate_record_sequence(
        model.SQLITE_INTEGER_MAX - 1
    ) == model.SQLITE_INTEGER_MAX - 1
    with pytest.raises(ValueError, match="record sequence"):
        model.validate_record_sequence(model.SQLITE_INTEGER_MAX)


def test_provenance_envelope_preserves_unknown_backend_kind_and_version() -> None:
    snapshot = model.ConnectionProvenanceSnapshot(
        envelope_version=1,
        backend_kind="future/vendor-backend",
        backend_schema_version=927,
        fields=(
            model.ProvenanceField("absent", None),
            model.ProvenanceField("enabled", True),
            model.ProvenanceField("revision", 23),
            model.ProvenanceField("transport", "opaque-value"),
        ),
    )

    assert snapshot.backend_kind == "future/vendor-backend"
    assert snapshot.backend_schema_version == 927
    assert tuple(field.value for field in snapshot.fields) == (
        None,
        True,
        23,
        "opaque-value",
    )
    assert model.PersistedConnectionProvenance(snapshot).to_snapshot() == snapshot


@pytest.mark.parametrize(
    "fields",
    [
        (("z", 1), ("a", 2)),
        (("same", 1), ("same", 2)),
    ],
)
def test_provenance_envelope_requires_sorted_unique_field_names(
    fields: tuple[tuple[str, int], ...],
) -> None:
    with pytest.raises(ValueError, match="sorted unique"):
        model.ConnectionProvenanceSnapshot(
            envelope_version=1,
            backend_kind="opaque",
            backend_schema_version=1,
            fields=tuple(model.ProvenanceField(*field) for field in fields),
        )


@pytest.mark.parametrize("value", [1.5, b"bytes", [], {}, object()])
def test_provenance_field_rejects_non_scalar_values(value: object) -> None:
    with pytest.raises(TypeError, match="scalar"):
        model.ProvenanceField(
            "field",
            cast("model.ProvenanceScalar", value),
        )


def test_provenance_envelope_rejects_only_unsupported_generic_version() -> None:
    with pytest.raises(ValueError, match="envelope version"):
        model.ConnectionProvenanceSnapshot(
            envelope_version=2,
            backend_kind="otherwise-unknown-is-fine",
            backend_schema_version=991,
            fields=(),
        )


def test_provenance_envelope_version_must_be_an_integer() -> None:
    with pytest.raises(TypeError, match="envelope version"):
        model.ConnectionProvenanceSnapshot(
            envelope_version=cast("int", True),
            backend_kind="opaque",
            backend_schema_version=1,
            fields=(),
        )


def test_stable_record_and_empty_range_references_are_valid() -> None:
    session_id = _session_id()
    record = model.EvidenceReference(session_id=session_id, sequence=17)
    empty = model.EvidenceRangeReference(
        session_id=session_id,
        start_inclusive=17,
        end_exclusive=17,
    )

    assert record.sequence == 17
    assert empty.is_empty


def test_range_reference_rejects_reversed_or_out_of_range_endpoints() -> None:
    with pytest.raises(ValueError, match="half-open"):
        model.EvidenceRangeReference(_session_id(), 4, 3)
    with pytest.raises(ValueError, match="start"):
        model.EvidenceRangeReference(_session_id(), -1, 3)
    with pytest.raises(ValueError, match="end"):
        model.EvidenceRangeReference(
            _session_id(),
            0,
            model.SQLITE_INTEGER_MAX + 1,
        )


def test_retention_marker_preserves_separate_timestamp_endpoints() -> None:
    first = _timestamp_endpoint(10)
    last = model.RetentionTimestampEndpoint(
        timestamp=model.BackendObservationTimestamp("device-domain", 2),
        domain=model.BackendObservationTimestampDomain(
            domain_id="device-domain",
            observer=model.TimestampObserver.DEVICE,
            meaning=model.TimestampMeaning.OBSERVATION,
            unit=model.TimestampUnit.TICK,
            origin_id="device-origin",
        ),
    )
    marker = model.RetentionMarker(
        expired_range=model.SequenceRange(0, 9),
        first_discarded_timestamp=first,
        last_discarded_timestamp=last,
        discarded_record_count=9,
        discarded_rx_payload_byte_count=256,
        discarded_charged_bytes=500,
    )

    assert marker.expired_range == model.SequenceRange(0, 9)
    assert marker.first_discarded_timestamp is first
    assert marker.last_discarded_timestamp is last


def test_retention_marker_requires_a_prefix_and_matching_count() -> None:
    with pytest.raises(ValueError, match="start at zero"):
        model.RetentionMarker(
            expired_range=model.SequenceRange(1, 2),
            first_discarded_timestamp=None,
            last_discarded_timestamp=None,
            discarded_record_count=1,
            discarded_rx_payload_byte_count=0,
            discarded_charged_bytes=1,
        )
    with pytest.raises(ValueError, match="record count"):
        model.RetentionMarker(
            expired_range=model.SequenceRange(0, 2),
            first_discarded_timestamp=None,
            last_discarded_timestamp=None,
            discarded_record_count=1,
            discarded_rx_payload_byte_count=0,
            discarded_charged_bytes=1,
        )


def test_retention_marker_timestamp_endpoints_are_both_present_or_absent() -> None:
    with pytest.raises(ValueError, match="both be present or absent"):
        model.RetentionMarker(
            expired_range=model.SequenceRange(0, 1),
            first_discarded_timestamp=_timestamp_endpoint(),
            last_discarded_timestamp=None,
            discarded_record_count=1,
            discarded_rx_payload_byte_count=0,
            discarded_charged_bytes=1,
        )


def test_retrieval_request_requires_positive_independent_bounds() -> None:
    reference = model.EvidenceRangeReference(_session_id(), 0, 5)
    request = evidence.EvidenceRetrievalRequest(
        reference=reference,
        max_records=2,
        max_charged_bytes=100,
    )

    assert request.max_records == 2
    assert request.max_charged_bytes == 100
    with pytest.raises(ValueError, match="max records"):
        evidence.EvidenceRetrievalRequest(reference, 0, 100)
    with pytest.raises(ValueError, match="max charged bytes"):
        evidence.EvidenceRetrievalRequest(reference, 2, 0)


def test_cursor_requires_one_coherent_snapshot_position() -> None:
    cursor = evidence.EvidenceCursor(
        session_id=_session_id(),
        range_start_inclusive=3,
        range_end_exclusive=20,
        snapshot_end_exclusive=15,
        next_sequence=8,
    )

    assert cursor.next_sequence == 8
    with pytest.raises(ValueError, match="snapshot"):
        evidence.EvidenceCursor(
            session_id=_session_id(),
            range_start_inclusive=3,
            range_end_exclusive=20,
            snapshot_end_exclusive=21,
            next_sequence=8,
        )


def test_retrieval_page_keeps_expiry_and_truncation_independent() -> None:
    expired_range = model.SequenceRange(0, 3)
    marker = model.RetentionMarker(
        expired_range=expired_range,
        first_discarded_timestamp=None,
        last_discarded_timestamp=None,
        discarded_record_count=3,
        discarded_rx_payload_byte_count=0,
        discarded_charged_bytes=90,
    )
    cursor = evidence.EvidenceCursor(
        session_id=_session_id(),
        range_start_inclusive=0,
        range_end_exclusive=10,
        snapshot_end_exclusive=10,
        next_sequence=5,
    )
    page = evidence.EvidencePage(
        records=(),
        snapshot_end_exclusive=10,
        expired_range=expired_range,
        retention_marker=marker,
        never_existed_range=None,
        outcome=evidence.EvidencePageOutcome.PARTIAL,
        truncated=True,
        continuation=cursor,
        charged_bytes=0,
        next_record_required_bytes=120,
    )

    assert page.outcome is evidence.EvidencePageOutcome.PARTIAL
    assert page.truncated
    assert page.expired_range == expired_range


def test_journal_failure_is_normalized_and_immutable() -> None:
    failure = evidence.JournalFailure(
        operation=evidence.JournalOperation.OPEN,
        kind=evidence.JournalFailureKind.DATABASE_OVER_CEILING,
        detail="page count exceeds policy",
    )

    assert str(failure).startswith("open/capacity/database_over_ceiling")
    with pytest.raises(FrozenInstanceError):
        failure.detail = "changed"  # type: ignore[misc]
