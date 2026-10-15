"""Additive pure v2 operation codec/charge; legacy codec remains strict."""

import json
import sqlite3
from dataclasses import replace
from typing import cast

import pytest

from dutchmate_core import evidence, model
from dutchmate_core.adapters import sqlite_evidence as codec
from tests.unit.test_monitor_values import ORIGIN
from tests.unit.test_operation_evidence import end_draft, start_draft
from tests.unit.test_sqlite_evidence_codec import _records


@pytest.mark.parametrize("ended", [False, True])
def test_marker_round_trip_charge_blob_and_exact_metadata(ended: bool) -> None:
    record = evidence._assign_sequence(
        end_draft() if ended else start_draft(), 6 if ended else 2
    )
    encoded = codec.encode_evidence_record_v2(record)
    assert encoded.record_version == 2
    assert encoded.record_kind == ("operation_ended" if ended else "operation_started")
    assert encoded.payload == (b"" if ended else bytes(range(256)))
    assert encoded.rx_payload_bytes == 0
    assert codec._record_timestamp(record) is None
    assert (
        codec._timestamp_endpoint_for_candidate(
            cast(sqlite3.Connection, object()), record
        )
        is None
    )
    assert encoded.charged_bytes == 16 + len(encoded.record_kind.encode("utf-8")) + len(
        encoded.metadata_json
    ) + len(encoded.payload or b"")
    metadata = json.loads(encoded.metadata_json)
    assert set(metadata) == (
        {
            "operation_id",
            "operation_kind",
            "start_sequence",
            "window",
            "outcome",
            "examined_rx_bytes",
            "observer_loss_records",
            "match",
            "clock",
        }
        if ended
        else {
            "operation_id",
            "operation_kind",
            "provenance",
            "timeout_ms",
            "max_rx_bytes",
            "clock_origin_id",
        }
    )
    assert encoded.metadata_json == json.dumps(
        metadata,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    decoded = codec.decode_evidence_record_v2(encoded)
    if isinstance(record, model.OperationStartedEvidence):
        assert isinstance(decoded, model.OperationStartedEvidence)
        assert decoded.condition == record.condition
        assert (
            decoded.provenance.connection_provenance.to_snapshot()
            == record.provenance.connection_provenance.to_snapshot()
        )
        assert metadata["provenance"]["connection_provenance"]["envelope_version"] == 1
    else:
        assert decoded == record
    with pytest.raises(evidence.JournalFailure) as failure:
        codec.encode_evidence_record(record)
    assert failure.value.kind is evidence.JournalFailureKind.INVALID_INPUT
    with pytest.raises(evidence.JournalFailure) as failure:
        codec.decode_evidence_record(encoded)
    assert failure.value.kind is evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION


@pytest.mark.parametrize("index", range(4))
def test_old_four_encodings_are_identical_in_both_helpers(index: int) -> None:
    record = _records()[index]
    old = codec.encode_evidence_record(record)
    assert codec.encode_evidence_record_v2(record) == old
    assert old.record_version == 1
    assert codec.decode_evidence_record_v2(old) == codec.decode_evidence_record(old)


def _changed_metadata(
    encoded: codec.EncodedEvidenceRecord, field: str, value: object
) -> codec.EncodedEvidenceRecord:
    metadata = json.loads(encoded.metadata_json)
    metadata[field] = value
    payload = json.dumps(
        metadata,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return replace(
        encoded,
        metadata_json=payload,
        charged_bytes=encoded.charged_bytes - len(encoded.metadata_json) + len(payload),
    )


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("operation_id", "bad"),
        ("operation_kind", "interact"),
        ("timeout_ms", True),
        ("timeout_ms", 4001),
        ("max_rx_bytes", 1048577),
        ("clock_origin_id", None),
        ("provenance", {}),
        ("extra", 1),
    ],
)
def test_malformed_start_is_corrupt(field: str, bad: object) -> None:
    encoded = codec.encode_evidence_record_v2(
        evidence._assign_sequence(start_draft(), 2)
    )
    with pytest.raises(evidence.JournalFailure) as failure:
        codec.decode_evidence_record_v2(_changed_metadata(encoded, field, bad))
    assert failure.value.operation is evidence.JournalOperation.DECODE
    assert failure.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("outcome", "timeout"),
        ("match", None),
        ("examined_rx_bytes", 0),
        ("examined_rx_bytes", 1048577),
        ("observer_loss_records", True),
        ("window", {"start_inclusive": 2, "end_exclusive": 6}),
        ("window", {"start_inclusive": 3, "end_exclusive": 5}),
        (
            "clock",
            {
                "origin_id": ORIGIN,
                "started_at_ns": 1,
                "deadline_at_ns": 1,
                "decided_at_ns": 1,
            },
        ),
        (
            "match",
            {
                "start": {"sequence": 3, "byte_offset": 0, "extra": 1},
                "end": {"sequence": 5, "byte_offset_exclusive": 256},
            },
        ),
        ("extra", 1),
    ],
)
def test_malformed_end_is_corrupt(field: str, bad: object) -> None:
    encoded = codec.encode_evidence_record_v2(evidence._assign_sequence(end_draft(), 6))
    with pytest.raises(evidence.JournalFailure) as failure:
        codec.decode_evidence_record_v2(_changed_metadata(encoded, field, bad))
    assert failure.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("payload", None),
        ("payload", b"x"),
        ("payload", bytearray()),
        ("rx_payload_bytes", 1),
        ("rx_payload_bytes", False),
        ("charged_bytes", 1),
        ("sequence", True),
        ("metadata_json", b"{}"),
    ],
)
def test_marker_envelope_is_strict(field: str, bad: object) -> None:
    encoded = codec.encode_evidence_record_v2(evidence._assign_sequence(end_draft(), 6))
    with pytest.raises(evidence.JournalFailure) as failure:
        codec.decode_evidence_record_v2(replace(encoded, **{field: bad}))  # type: ignore[arg-type]
    assert failure.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


@pytest.mark.parametrize(
    ("kind", "version", "expected"),
    [
        ("operation_ended", 1, evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION),
        ("operation_ended", 3, evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION),
        ("rx_bytes", 2, evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION),
        ("unknown", 2, evidence.JournalFailureKind.CORRUPT_JOURNAL),
    ],
)
def test_kind_version_dispatch_is_explicit(
    kind: str, version: int, expected: evidence.JournalFailureKind
) -> None:
    encoded = codec.encode_evidence_record_v2(evidence._assign_sequence(end_draft(), 6))
    with pytest.raises(evidence.JournalFailure) as failure:
        codec.decode_evidence_record_v2(
            replace(encoded, record_kind=kind, record_version=version)
        )
    assert failure.value.kind is expected


def test_preflight_uses_maximum_of_nine_valid_canonical_charges() -> None:
    started = start_draft()
    drafts = evidence.maximum_monitor_end_drafts(
        started.operation_id, started.clock_origin_id
    )
    actual, maximum = codec.charge_monitor_markers(started, drafts)
    assert (
        actual
        == codec.encode_evidence_record_v2(
            evidence._assign_sequence(started, 0)
        ).charged_bytes
    )
    charges = [
        codec.encode_evidence_record_v2(evidence._assign_sequence(d, 0)).charged_bytes
        for d in drafts
    ]
    assert maximum == max(charges)
    assert maximum > min(charges)
    for draft in drafts:
        if draft.outcome is not model.MonitorOutcome.MATCHED:
            with pytest.raises(ValueError):
                replace(draft, match=end_draft().match)
    for bad in (drafts[:8], (*drafts[:8], drafts[0])):
        with pytest.raises(evidence.JournalFailure) as failure:
            codec.charge_monitor_markers(started, bad)
        assert failure.value.kind is evidence.JournalFailureKind.INVALID_INPUT


def test_invalid_new_encoder_input_uses_standard_journal_failure() -> None:
    with pytest.raises(evidence.JournalFailure) as failure:
        codec.encode_evidence_record_v2(cast(model.EvidenceRecord, object()))
    assert failure.value.operation is evidence.JournalOperation.ENCODE
    assert failure.value.kind is evidence.JournalFailureKind.INVALID_INPUT
    failure.value.add_note("normal exception transport")
    assert failure.value.__traceback__ is not None


def test_end_metadata_has_exact_contract_values_and_recursive_sorting() -> None:
    encoded = codec.encode_evidence_record_v2(evidence._assign_sequence(end_draft(), 6))
    expected = (
        b'{"clock":{"deadline_at_ns":4000000100,"decided_at_ns":200,'
        b'"origin_id":"12345678-1234-1234-1234-123456789abc","started_at_ns":100},'
        b'"examined_rx_bytes":256,"match":{"end":{"byte_offset_exclusive":256,'
        b'"sequence":5},"start":{"byte_offset":0,"sequence":3}},'
        b'"observer_loss_records":0,"operation_id":"abcdefab-1234-1234-1234-123456789abc",'
        b'"operation_kind":"monitor","outcome":"matched","start_sequence":2,'
        b'"window":{"end_exclusive":6,"start_inclusive":3}}'
    )
    assert encoded.metadata_json == expected
    assert encoded.charged_bytes == 478
    # A semantically equal object with a nested order change is not canonical.
    unsorted = expected.replace(
        b'"byte_offset":0,"sequence":3', b'"sequence":3,"byte_offset":0'
    )
    with pytest.raises(evidence.JournalFailure) as failure:
        codec.decode_evidence_record_v2(replace(encoded, metadata_json=unsorted))
    assert failure.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


def test_start_preserves_nonascii_opaque_provenance_with_private_v1_envelope() -> None:
    draft = start_draft()
    opaque = model.PersistedConnectionProvenance(
        model.ConnectionProvenanceSnapshot(
            1,
            "fixture/opaque",
            37,
            (model.ProvenanceField("label", "\u00e9\u96ea"),),
        )
    )
    draft = replace(
        draft, provenance=replace(draft.provenance, connection_provenance=opaque)
    )
    encoded = codec.encode_evidence_record_v2(evidence._assign_sequence(draft, 0))
    assert "\u00e9\u96ea".encode() in encoded.metadata_json
    assert b"\\u00e9" not in encoded.metadata_json
    decoded = codec.decode_evidence_record_v2(encoded)
    assert isinstance(decoded, model.OperationStartedEvidence)
    assert decoded.provenance.connection_provenance.to_snapshot() == opaque.snapshot
