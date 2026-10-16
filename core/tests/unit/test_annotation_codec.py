"""Strict annotation-v3 encoding and legacy compatibility, without journal I/O."""

import json
from dataclasses import replace

import pytest

from dutchmate_core import evidence, model
from dutchmate_core.adapters import sqlite_evidence as codec
from tests.unit.test_annotation_values import ORIGIN, draft, record
from tests.unit.test_operation_evidence import end_draft, start_draft
from tests.unit.test_sqlite_evidence_codec import _records


def test_annotation_canonical_metadata_utf8_blob_charge_and_roundtrip() -> None:
    value = record()
    encoded = codec.encode_evidence_record_v3(value)
    expected = (
        b'{"assertion_class":"client_assertion","attribution_basis":"client_asserted",'
        b'"client_surface":"cli","clock_origin_id":"12345678-1234-1234-1234-123456789abc",'
        b'"received_at_ns":17}'
    )
    payload = b"  build e\xcc\x81; \xe9\x9b\xaa\nstep\t1  "
    assert encoded.record_kind == "client_annotation"
    assert encoded.record_version == 3
    assert encoded.metadata_json == expected
    assert encoded.payload == payload
    assert encoded.rx_payload_bytes == 0
    assert encoded.charged_bytes == 16 + 17 + len(expected) + len(payload)
    assert codec._record_timestamp(value) is None
    assert codec.decode_evidence_record_v3(encoded) == value


@pytest.mark.parametrize("surface", ["cli", "http", "core"])
@pytest.mark.parametrize("text", ["a", "é" * 512, "x" * 1024, "\r\n\t"])
def test_maximum_shape_charge_is_codec_exact_not_an_rx_count(
    surface: str, text: str
) -> None:
    maximum = replace(
        draft(),
        text=text,
        client_surface=surface,
        received_at_ns=model.SQLITE_INTEGER_MAX,
    )
    encoded = codec.encode_evidence_record_v3(evidence._assign_sequence(maximum, 0))
    assert codec.charge_client_annotation(maximum) == encoded.charged_bytes
    narrow = codec.encode_evidence_record_v3(
        evidence._assign_sequence(replace(maximum, received_at_ns=0), 0)
    )
    assert encoded.charged_bytes - narrow.charged_bytes == 18
    assert (
        codec.encode_evidence_record_v3(
            evidence._assign_sequence(maximum, model.SQLITE_INTEGER_MAX - 1)
        ).charged_bytes
        == encoded.charged_bytes
    )


@pytest.mark.parametrize("index", range(6))
def test_all_six_legacy_encodings_and_decoders_remain_identical(index: int) -> None:
    values = (
        *_records(),
        evidence._assign_sequence(start_draft(), 2),
        evidence._assign_sequence(end_draft(), 6),
    )
    value = values[index]
    old = codec.encode_evidence_record_v2(value)
    assert codec.encode_evidence_record_v3(value) == old
    assert codec.decode_evidence_record_v3(old) == codec.decode_evidence_record_v2(old)


def changed_metadata(field: str, value: object) -> codec.EncodedEvidenceRecord:
    encoded = codec.encode_evidence_record_v3(record())
    metadata = json.loads(encoded.metadata_json)
    metadata[field] = value
    raw = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()
    return replace(
        encoded,
        metadata_json=raw,
        charged_bytes=encoded.charged_bytes + len(raw) - len(encoded.metadata_json),
    )


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("assertion_class", "dut_observation"),
        ("attribution_basis", "authenticated"),
        ("client_surface", "CLI"),
        ("client_surface", None),
        ("clock_origin_id", ORIGIN.upper()),
        ("received_at_ns", True),
        ("received_at_ns", -1),
        ("received_at_ns", model.SQLITE_INTEGER_MAX + 1),
        ("extra", "secret"),
    ],
)
def test_malformed_annotation_metadata_is_corrupt(field: str, bad: object) -> None:
    with pytest.raises(evidence.JournalFailure) as raised:
        codec.decode_evidence_record_v3(changed_metadata(field, bad))
    assert raised.value.operation is evidence.JournalOperation.DECODE
    assert raised.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


@pytest.mark.parametrize(
    "payload",
    [None, b"", b"x" * 1025, b"\xff", b"a\x00b", b"\xed\xa0\x80", bytearray(b"claim")],
)
def test_malformed_annotation_blob_is_corrupt(payload: object) -> None:
    encoded = codec.encode_evidence_record_v3(record())
    charge = encoded.charged_bytes
    if type(payload) is bytes:
        charge = 16 + 17 + len(encoded.metadata_json) + len(payload)
    changed = replace(encoded, payload=payload, charged_bytes=charge)  # type: ignore[arg-type]
    with pytest.raises(evidence.JournalFailure) as raised:
        codec.decode_evidence_record_v3(changed)
    assert raised.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("sequence", True),
        ("sequence", -1),
        ("sequence", model.SQLITE_INTEGER_MAX),
        ("charged_bytes", 0),
        ("charged_bytes", True),
        ("rx_payload_bytes", 1),
        ("rx_payload_bytes", False),
        ("metadata_json", b"{}"),
    ],
)
def test_annotation_envelope_is_strict(field: str, bad: object) -> None:
    encoded = codec.encode_evidence_record_v3(record())
    with pytest.raises(evidence.JournalFailure) as raised:
        codec.decode_evidence_record_v3(replace(encoded, **{field: bad}))  # type: ignore[arg-type]
    assert raised.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


@pytest.mark.parametrize(
    ("kind", "version", "failure"),
    [
        (
            "client_annotation",
            1,
            evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION,
        ),
        (
            "client_annotation",
            2,
            evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION,
        ),
        (
            "client_annotation",
            True,
            evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION,
        ),
        ("rx_bytes", 3, evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION),
        ("operation_ended", 3, evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION),
        ("unknown", 3, evidence.JournalFailureKind.CORRUPT_JOURNAL),
    ],
)
def test_explicit_v3_kind_version_matrix(
    kind: str, version: int, failure: evidence.JournalFailureKind
) -> None:
    encoded = codec.encode_evidence_record_v3(record())
    with pytest.raises(evidence.JournalFailure) as raised:
        codec.decode_evidence_record_v3(
            replace(encoded, record_kind=kind, record_version=version)
        )
    assert raised.value.kind is failure


def test_old_codecs_reject_annotation_and_new_helpers_reject_invalid_input() -> None:
    value = record()
    encoded = codec.encode_evidence_record_v3(value)
    for encode in (codec.encode_evidence_record, codec.encode_evidence_record_v2):
        with pytest.raises(evidence.JournalFailure) as raised:
            encode(value)
        assert raised.value.kind is evidence.JournalFailureKind.INVALID_INPUT
    for decode in (codec.decode_evidence_record, codec.decode_evidence_record_v2):
        with pytest.raises(evidence.JournalFailure):
            decode(encoded)
    with pytest.raises(evidence.JournalFailure) as raised:
        codec.encode_evidence_record_v3(object())  # type: ignore[arg-type]
    assert raised.value.kind is evidence.JournalFailureKind.INVALID_INPUT
    with pytest.raises(evidence.JournalFailure) as raised:
        codec.charge_client_annotation(start_draft())  # type: ignore[arg-type]
    assert raised.value.kind is evidence.JournalFailureKind.INVALID_INPUT


def test_noncanonical_and_missing_annotation_metadata_are_rejected() -> None:
    encoded = codec.encode_evidence_record_v3(record())
    metadata = json.loads(encoded.metadata_json)
    del metadata["assertion_class"]
    alternatives = (
        json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode(),
        encoded.metadata_json.replace(b'"received_at_ns":17', b'"received_at_ns": 17'),
        encoded.metadata_json.replace(
            b'"received_at_ns":17', b'"received_at_ns":17,"received_at_ns":17'
        ),
    )
    for raw in alternatives:
        with pytest.raises(evidence.JournalFailure) as raised:
            codec.decode_evidence_record_v3(
                replace(
                    encoded,
                    metadata_json=raw,
                    charged_bytes=encoded.charged_bytes
                    + len(raw)
                    - len(encoded.metadata_json),
                )
            )
        assert raised.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


def test_encoder_and_charge_callback_revalidate_forged_values() -> None:
    invalid_record = record()
    object.__setattr__(invalid_record, "text", "\ud800")
    with pytest.raises(evidence.JournalFailure) as raised:
        codec.encode_evidence_record_v3(invalid_record)
    assert raised.value.kind is evidence.JournalFailureKind.INVALID_INPUT
    invalid_draft = draft()
    object.__setattr__(invalid_draft, "received_at_ns", True)
    with pytest.raises(evidence.JournalFailure) as raised:
        codec.charge_client_annotation(invalid_draft)
    assert raised.value.operation is evidence.JournalOperation.ENCODE
    assert raised.value.kind is evidence.JournalFailureKind.INVALID_INPUT
