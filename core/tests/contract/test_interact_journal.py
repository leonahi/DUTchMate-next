"""012 T008 RED: explicit v4 codecs and test-owned temporary journals only.

Literal encoded rows are the oracle. Pending counterparts are built from decoded
dataclass fields so these tests do not prescribe a second TX-facts representation.
The adapter-private charge seam follows the existing Monitor callback convention:
charge_interact_markers(start, maximum_txs, maximum_ends) -> three charges.
"""

import base64
import json
import sqlite3
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from typing import Any, NoReturn, cast
from urllib.parse import parse_qs, urlsplit

import pytest
import serial

from dutchmate_core import acquisition, evidence, evidence_access, model, runtime
from dutchmate_core.adapters import basic_serial, terminal_evidence
from dutchmate_core.adapters import sqlite_evidence as sqlite
from dutchmate_core.backend import BackendFailureKind
from tests.contract.test_monitor_journal import (
    _end,
    _files,
    _provenance,
    _rows,
    _rx,
    _sql,
    _start,
)
from tests.contract.test_sqlite_evidence_journal import _database_state, _policy
from tests.unit.test_annotation_values import draft as annotation_draft
from tests.unit.test_annotation_values import record as annotation_record
from tests.unit.test_operation_evidence import end_draft, start_draft
from tests.unit.test_sqlite_evidence_codec import _records

OPERATION = "abcdefab-1234-1234-1234-123456789abc"
ORIGIN = "12345678-1234-1234-1234-123456789abc"
MAX = 9_223_372_036_854_775_807
KINDS = ("interact_started", "uart_tx_settled", "interact_ended")
CLASS_NAMES = (
    "InteractStartedEvidence",
    "UartTxSettledEvidence",
    "InteractEndedEvidence",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _encoded(
    kind: str, sequence: int, metadata: dict[str, Any], payload: bytes | None = b""
) -> sqlite.EncodedEvidenceRecord:
    raw = _canonical(metadata)
    return sqlite.EncodedEvidenceRecord(
        sequence,
        kind,
        4,
        raw,
        payload,
        16 + len(kind.encode()) + len(raw) + len(payload or b""),
        0,
    )


def _provenance_json(index: int = 0) -> dict[str, Any]:
    # Existing v3 codec supplies ONLY the unchanged private provenance envelope;
    # all new v4 keys, values, BLOBs and charges below are independent literals.
    value = sqlite.encode_evidence_record_v3(
        model.SegmentStartedEvidence(0, _provenance(index))
    )
    return cast("dict[str, Any]", json.loads(value.metadata_json))


def start_row(index: int = 0, *, sequence: int = 1) -> sqlite.EncodedEvidenceRecord:
    return _encoded(
        "interact_started",
        sequence,
        {
            "operation_id": OPERATION,
            "provenance": _provenance_json(index),
            "profile_version": 2,
            "authorization": {"uart_tx_enabled": True},
            "conditions_base64": ["UEFTUw==", "AP8="],
            "timeout_ms": 1000,
            "max_rx_bytes": 1024,
            "write_timeout_ms": 1000,
            "clock_origin_id": ORIGIN,
        },
        bytes(range(256)),
    )


def tx_facts(
    *,
    status: str = "acknowledged",
    count: int | None = 256,
    submitted: bool = True,
    failure: str | None = None,
    settled: int = 300,
) -> dict[str, Any]:
    return {
        "submitted": submitted,
        "status": status,
        "accepted_prefix_bytes": count,
        "failure_code": failure,
        "acknowledgement_scope": "backend_acceptance",
        "clock_origin_id": ORIGIN,
        "settled_at_ns": settled,
    }


def tx_row(
    *, sequence: int = 3, start: int = 1, tx: dict[str, Any] | None = None
) -> sqlite.EncodedEvidenceRecord:
    return _encoded(
        "uart_tx_settled",
        sequence,
        {
            "operation_id": OPERATION,
            "start_sequence": start,
            **(tx_facts() if tx is None else tx),
        },
    )


def end_row(
    *,
    sequence: int = 4,
    start: int = 1,
    tx_sequence: int | None = 3,
    tx: dict[str, Any] | None = None,
    outcome: str = "matched",
    observation: dict[str, Any] | None = None,
    audit: dict[str, str] | None = None,
) -> sqlite.EncodedEvidenceRecord:
    window = {
        "window": {"start_inclusive": start + 1, "end_exclusive": start + 2},
        "outcome": "matched",
        "examined_rx_bytes": 4,
        "observer_loss_records": 0,
        "match": {
            "condition_index": 0,
            "start": {"sequence": start + 1, "byte_offset": 0},
            "end": {"sequence": start + 1, "byte_offset_exclusive": 4},
        },
        "clock": {
            "origin_id": ORIGIN,
            "started_at_ns": 100,
            "deadline_at_ns": 1_000_000_100,
            "decided_at_ns": 200,
        },
    }
    return _encoded(
        "interact_ended",
        sequence,
        {
            "operation_id": OPERATION,
            "start_sequence": start,
            "tx_settled_sequence": tx_sequence,
            "tx": tx_facts() if tx is None else tx,
            "tx_audit_failure": audit,
            "outcome": outcome,
            "observation": window if observation is None else observation,
        },
    )


def _api(name: str) -> Any:
    operation = getattr(sqlite, name, None)
    assert callable(operation), f"T008: missing v4 codec support: {name}"
    return operation


def _decode(row: sqlite.EncodedEvidenceRecord) -> Any:
    return _api("decode_evidence_record_v4")(row)


def pending(row: sqlite.EncodedEvidenceRecord) -> Any:
    record = _decode(row)
    factory = getattr(evidence, "Pending" + type(record).__name__, None)
    assert callable(factory), (
        f"T008: missing pending counterpart for {type(record).__name__}"
    )
    return factory(
        **{
            field.name: getattr(record, field.name)
            for field in fields(record)
            if field.name != "sequence"
        }
    )


async def create_v4(
    path: Path, policy: model.SessionPolicy | None = None
) -> sqlite.SqliteEvidenceJournal:
    factory = getattr(sqlite.SqliteEvidenceJournal, "create_v4", None)
    assert callable(factory), "T008: missing explicit SqliteEvidenceJournal.create_v4"
    journal = await factory(path, _policy() if policy is None else policy)
    assert isinstance(journal, sqlite.SqliteEvidenceJournal)
    return journal


async def open_v4(
    path: Path, session: model.SessionId | None = None
) -> sqlite.SqliteEvidenceJournal:
    factory = getattr(sqlite.SqliteEvidenceJournal, "open_v4", None)
    assert callable(factory), "T008: missing explicit SqliteEvidenceJournal.open_v4"
    journal = await factory(path, expected_session_id=session)
    assert isinstance(journal, sqlite.SqliteEvidenceJournal)
    return journal


def changed(
    row: sqlite.EncodedEvidenceRecord, key: str, value: Any
) -> sqlite.EncodedEvidenceRecord:
    metadata = json.loads(row.metadata_json)
    keys = key.split(".")
    parent = metadata
    for part in keys[:-1]:
        parent = parent[part]
    parent[keys[-1]] = value
    return _encoded(row.record_kind, row.sequence, metadata, row.payload)


def _forbid_resources(*args: object, **kwargs: object) -> NoReturn:
    pytest.fail("journal tests must not open hardware, acquire RX or attach a runtime")


@pytest.fixture(autouse=True)
def journal_resources_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for target, attribute in (
        (serial, "Serial"),
        (serial, "serial_for_url"),
        (basic_serial, "BasicSerialBackend"),
        (acquisition.Acquisition, "start"),
        (runtime.ObservationRuntime, "attach"),
    ):
        monkeypatch.setattr(target, attribute, _forbid_resources)
    monkeypatch.setattr("serial.tools.list_ports.comports", _forbid_resources)
    monkeypatch.setattr("serial.tools.list_ports.grep", _forbid_resources)


def legacy_records() -> tuple[model.EvidenceRecord, ...]:
    return (
        *_records(),
        evidence._assign_sequence(start_draft(), 2),
        evidence._assign_sequence(end_draft(), 6),
        annotation_record(),
    )


@pytest.mark.parametrize("index", range(7))
def test_t008_all_seven_legacy_codec_bytes_versions_blobs_and_charges_are_identical(
    index: int,
) -> None:
    record = legacy_records()[index]
    old = sqlite.encode_evidence_record_v3(record)
    assert _api("encode_evidence_record_v4")(record) == old
    assert _decode(old) == sqlite.decode_evidence_record_v3(old)


@pytest.mark.parametrize("index", range(7))
def test_t008_v4_does_not_upgrade_any_legacy_record_version(index: int) -> None:
    row = sqlite.encode_evidence_record_v3(legacy_records()[index])
    with pytest.raises(evidence.JournalFailure) as caught:
        _decode(replace(row, record_version=4))
    assert caught.value.kind is evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION


def test_t008_start_preserves_opaque_unicode_provenance_without_ascii_escaping() -> (
    None
):
    row = changed(
        start_row(), "provenance.connection_provenance.backend_kind", "opaque/雪"
    )
    row = changed(row, "provenance.connection_provenance.backend_schema_version", 812)
    row = changed(
        row,
        "provenance.connection_provenance.fields",
        {"text": "café 雪", "count": 7, "flag": False, "unknown": None},
    )
    assert "雪".encode() in row.metadata_json
    assert _api("encode_evidence_record_v4")(_decode(row)) == row


@pytest.mark.parametrize("version", [1, 2, 3])
@pytest.mark.parametrize("kind_index", range(3), ids=KINDS)
def test_t008_existing_codecs_still_reject_all_new_record_versions(
    version: int, kind_index: int
) -> None:
    decoder = (
        sqlite.decode_evidence_record,
        sqlite.decode_evidence_record_v2,
        sqlite.decode_evidence_record_v3,
    )[version - 1]
    with pytest.raises(evidence.JournalFailure) as caught:
        decoder((start_row(), tx_row(), end_row())[kind_index])
    expected = (
        evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION
        if version == 1
        else evidence.JournalFailureKind.CORRUPT_JOURNAL
    )
    assert caught.value.kind is expected


@pytest.mark.parametrize("kind_index", range(3), ids=KINDS)
def test_t008_bad_new_model_input_is_normalized_invalid_input(kind_index: int) -> None:
    record = _decode((start_row(), tx_row(), end_row())[kind_index])
    object.__setattr__(record, "sequence", True)
    with pytest.raises(evidence.JournalFailure) as caught:
        _api("encode_evidence_record_v4")(record)
    assert caught.value.kind is evidence.JournalFailureKind.INVALID_INPUT


@pytest.mark.parametrize("index", [0, 1], ids=["basic-shape", "enhanced-shape"])
@pytest.mark.parametrize("kind_index", range(3), ids=KINDS)
def test_t008_v4_exact_metadata_blob_charge_and_immutable_roundtrip(
    index: int, kind_index: int
) -> None:
    expected = (start_row(index), tx_row(), end_row())[kind_index]
    record = _decode(expected)
    assert type(record).__name__ == CLASS_NAMES[kind_index]
    assert record.sequence == expected.sequence
    assert _api("encode_evidence_record_v4")(record) == expected
    if kind_index == 0:
        assert record.payload == bytes(range(256))
        assert record.conditions == (b"PASS", b"\x00\xff")
        assert record.provenance == _provenance(index)
    with pytest.raises(FrozenInstanceError):
        record.sequence = 7
    assert sqlite._record_timestamp(record) is None


@pytest.mark.parametrize("kind_index", range(3), ids=KINDS)
@pytest.mark.parametrize(
    "field",
    [
        "record_version",
        "sequence",
        "charged_bytes",
        "rx_payload_bytes",
        "payload",
        "metadata_json",
    ],
)
def test_t008_encoded_envelope_is_strict(kind_index: int, field: str) -> None:
    row = (start_row(), tx_row(), end_row())[kind_index]
    value = {
        "record_version": 99,
        "sequence": MAX,
        "charged_bytes": row.charged_bytes + 1,
        "rx_payload_bytes": 1,
        "payload": None,
        "metadata_json": b"not-json",
    }[field]
    # payload=None is an illegal v4 BLOB for all three kinds, including empty facts.
    with pytest.raises(evidence.JournalFailure) as caught:
        changes: dict[str, Any] = {field: value}
        _decode(replace(row, **changes))
    expected = (
        evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION
        if field == "record_version"
        else evidence.JournalFailureKind.CORRUPT_JOURNAL
    )
    assert caught.value.kind is expected


@pytest.mark.parametrize("kind_index", range(3), ids=KINDS)
def test_t008_unknown_kind_noncanonical_json_and_missing_keys_are_corrupt(
    kind_index: int,
) -> None:
    row = (start_row(), tx_row(), end_row())[kind_index]
    cases = [replace(row, record_kind="future_unknown")]
    metadata = json.loads(row.metadata_json)
    for key in metadata:
        omitted = dict(metadata)
        del omitted[key]
        cases.append(_encoded(row.record_kind, row.sequence, omitted, row.payload))
    raw = json.dumps(metadata, sort_keys=True, indent=1).encode()
    cases.append(
        replace(
            row,
            metadata_json=raw,
            charged_bytes=row.charged_bytes + len(raw) - len(row.metadata_json),
        )
    )
    cases.append(changed(row, "extra", True))
    for bad in cases:
        with pytest.raises(evidence.JournalFailure) as caught:
            _decode(bad)
        assert caught.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation_id", OPERATION.upper()),
        ("clock_origin_id", "not-uuid"),
        ("profile_version", 1),
        ("profile_version", True),
        ("authorization", {"uart_tx_enabled": False}),
        ("authorization", {"uart_tx_enabled": 1}),
        ("authorization", {"uart_tx_enabled": True, "extra": 1}),
        ("conditions_base64", []),
        ("conditions_base64", ["QQ=="] * 5),
        ("conditions_base64", [""]),
        ("conditions_base64", ["UEFTUw"]),
        ("conditions_base64", ["AB=="]),
        ("conditions_base64", [base64.b64encode(b"a" * 257).decode()]),
        ("conditions_base64", [False]),
        ("timeout_ms", True),
        ("timeout_ms", 0),
        ("timeout_ms", 4001),
        ("max_rx_bytes", 0),
        ("max_rx_bytes", 1048577),
        ("write_timeout_ms", 999),
        ("write_timeout_ms", True),
    ],
)
def test_t008_start_schema_and_native_bounds_are_closed(field: str, value: Any) -> None:
    with pytest.raises(evidence.JournalFailure) as caught:
        _decode(changed(start_row(), field, value))
    assert caught.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


@pytest.mark.parametrize("payload", [b"", b"x" * 4097])
def test_t008_start_payload_is_bounded_exact_requested_bytes(payload: bytes) -> None:
    row = start_row()
    row = replace(
        row, payload=payload, charged_bytes=row.charged_bytes - 256 + len(payload)
    )
    with pytest.raises(evidence.JournalFailure) as caught:
        _decode(row)
    assert caught.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("submitted", 1),
        ("status", "wire_transmitted"),
        ("status", "not_submitted"),
        ("accepted_prefix_bytes", True),
        ("accepted_prefix_bytes", 0),
        ("accepted_prefix_bytes", 4097),
        ("failure_code", "io_failure"),
        ("acknowledgement_scope", "dut_received"),
        ("settled_at_ns", True),
        ("settled_at_ns", -1),
        ("settled_at_ns", MAX + 1),
        ("clock_origin_id", ORIGIN.upper()),
        ("start_sequence", 3),
        ("start_sequence", True),
    ],
)
def test_t008_tx_schema_cannot_invent_progress_or_wire_receipt(
    field: str, value: Any
) -> None:
    with pytest.raises(evidence.JournalFailure) as caught:
        _decode(changed(tx_row(), field, value))
    assert caught.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


@pytest.mark.parametrize(
    "tx",
    [
        tx_facts(status="partial", count=0),
        tx_facts(status="partial", count=4095),
        tx_facts(status="timeout", count=None),
        tx_facts(status="disconnected", count=None),
        *(
            tx_facts(status="failure", count=None, failure=kind.value)
            for kind in BackendFailureKind
        ),
        tx_facts(status="not_submitted", count=None, submitted=False),
    ],
)
def test_t008_tx_full_partial_unknown_and_suppressed_facts_roundtrip(
    tx: dict[str, Any],
) -> None:
    row = tx_row(tx=tx)
    assert _api("encode_evidence_record_v4")(_decode(row)) == row


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("start_sequence", 4),
        ("tx_settled_sequence", 1),
        ("tx_settled_sequence", 4),
        ("tx_settled_sequence", True),
        ("outcome", "success"),
        ("observation.examined_rx_bytes", 1048577),
        ("observation.observer_loss_records", True),
        ("observation.match.condition_index", 4),
        ("observation.match.condition_index", True),
        ("observation.match.start.byte_offset", -1),
        ("observation.match.end.byte_offset_exclusive", 5),
        ("observation.clock.deadline_at_ns", 100),
        ("observation.clock.decided_at_ns", 99),
        ("observation.window", {"start_inclusive": 1, "end_exclusive": 3}),
        ("tx_audit_failure", {"source": "journal", "code": "invented"}),
        ("tx_audit_failure", {"source": "service", "code": "io_failure"}),
        (
            "tx_audit_failure",
            {"source": "journal", "code": "io_failure", "detail": "private"},
        ),
    ],
)
def test_t008_end_nested_shapes_and_counter_bounds_are_closed(
    field: str, value: Any
) -> None:
    with pytest.raises(evidence.JournalFailure) as caught:
        _decode(changed(end_row(), field, value))
    assert caught.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL


@pytest.mark.parametrize("kind", list(evidence.JournalFailureKind))
def test_t008_end_can_preserve_actual_tx_when_its_audit_ack_is_missing(
    kind: evidence.JournalFailureKind,
) -> None:
    row = end_row(tx_sequence=None, audit={"source": "journal", "code": kind.value})
    assert _api("encode_evidence_record_v4")(_decode(row)) == row


def test_t008_frozen_observation_and_overall_connection_outcome_are_independent() -> (
    None
):
    row = end_row(outcome="disconnected")
    assert _api("encode_evidence_record_v4")(_decode(row)) == row


@pytest.mark.parametrize("direction", ["encode", "decode"])
def test_t027_full_ack_cannot_preserve_tx_failed_under_external_outcome(
    direction: str,
) -> None:
    # An external overall termination preserves real frozen observations; it
    # cannot make TX-failure observation compatible with a full write ACK.
    row = changed(end_row(outcome="disconnected"), "observation.outcome", "tx_failed")
    row = changed(row, "observation.match", None)
    valid = _decode(end_row(outcome="disconnected"))
    invalid = replace(
        valid,
        observation=replace(
            valid.observation,
            outcome=model.InteractObservationOutcome.TX_FAILED,
            match=None,
        ),
    )
    with pytest.raises(evidence.JournalFailure) as caught:
        if direction == "decode":
            _decode(row)
        else:
            _api("encode_evidence_record_v4")(invalid)
    assert caught.value.kind is (
        evidence.JournalFailureKind.CORRUPT_JOURNAL
        if direction == "decode"
        else evidence.JournalFailureKind.INVALID_INPUT
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [0, 1], ids=["basic-shape", "enhanced-shape"])
async def test_t027_full_ack_tx_failed_append_rejects_without_mutation(
    tmp_path: Path, index: int
) -> None:
    path = tmp_path / "contradictory-end.sqlite3"
    valid = pending(end_row(outcome="disconnected"))
    invalid = replace(
        valid,
        observation=replace(
            valid.observation,
            outcome=model.InteractObservationOutcome.TX_FAILED,
            match=None,
        ),
    )
    journal = await create_v4(path)
    try:
        await journal.append(evidence.PendingSegmentStartedEvidence(_provenance(index)))
        await journal.append(pending(start_row(index)))
        await journal.append(_rx(_provenance(index), b"PASS", 11))
        await journal.append(pending(tx_row()))
        before = _database_state(path)
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(invalid)
        assert caught.value.kind is evidence.JournalFailureKind.INVALID_INPUT
        assert _database_state(path) == before
    finally:
        await journal.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic-shape", "enhanced-shape"])
@pytest.mark.asyncio
async def test_t008_real_v4_rows_point_page_reopen_and_host_only_telemetry(
    tmp_path: Path, index: int
) -> None:
    path = tmp_path / "v4.db"
    journal = await create_v4(path)
    expected = (start_row(index), tx_row(), end_row())
    try:
        await journal.append(evidence.PendingSegmentStartedEvidence(_provenance(index)))
        accepted = await journal.append(pending(expected[0]))
        await journal.append(_rx(_provenance(index), b"PASS", 11))
        await journal.append(pending(expected[1]))
        await journal.append(pending(expected[2]))
        session = journal.session_id
        point = await journal.resolve_record(model.EvidenceReference(session, 1))
        assert point.records == (accepted,)
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(session, 20, 20000)
        )
        assert len(page.records) == 5
        assert (
            tuple(_api("encode_evidence_record_v4")(page.records[i]) for i in (1, 3, 4))
            == expected
        )
    finally:
        await journal.close()
    rows = _rows(path)
    assert [rows[i][6:8] for i in (1, 3, 4)] == [(0, None)] * 3
    assert rows[2][6] == 4 and rows[2][7] is not None
    opened = await open_v4(path, session)
    try:
        assert (
            await opened.retrieve(evidence.EvidenceRetrievalRequest(session, 20, 20000))
            == page
        )
        await opened.append(_rx(_provenance(index), b"after", 12))
    finally:
        await opened.close()


@pytest.mark.parametrize("retained", [1, 2])
@pytest.mark.asyncio
async def test_t008_retention_counts_requested_tx_as_zero_rx_and_reports_expiry(
    tmp_path: Path,
    retained: int,
) -> None:
    path = tmp_path / "rolling.db"
    journal = await create_v4(path, _policy(max_retained_records=retained))
    try:
        start = await journal.append(pending(start_row(sequence=0)))
        await journal.append(pending(tx_row(sequence=1, start=0)))
        await journal.append(
            pending(
                end_row(
                    sequence=2,
                    start=0,
                    tx_sequence=1,
                    outcome="cancelled",
                    observation={
                        "window": {"start_inclusive": 1, "end_exclusive": 1},
                        "outcome": "cancelled",
                        "examined_rx_bytes": 0,
                        "observer_loss_records": 0,
                        "match": None,
                        "clock": {
                            "origin_id": ORIGIN,
                            "started_at_ns": 100,
                            "deadline_at_ns": 1000100,
                            "decided_at_ns": 200,
                        },
                    },
                )
            )
        )
        expired = await journal.resolve_record(
            model.EvidenceReference(journal.session_id, start.sequence)
        )
        assert expired.outcome is evidence.EvidencePageOutcome.EXPIRED
        marker = expired.retention_marker
        assert marker is not None
        assert marker.discarded_rx_payload_byte_count == 0
        assert marker.first_discarded_timestamp is None
        assert marker.last_discarded_timestamp is None
    finally:
        await journal.close()
    reopened = await open_v4(path)
    await reopened.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic-shape", "enhanced-shape"])
@pytest.mark.asyncio
async def test_t008_monitor_pair_and_timestamp_scans_traverse_all_three_host_only_kinds(
    tmp_path: Path, index: int
) -> None:
    path = tmp_path / "interleaved.db"
    journal = await create_v4(path)
    provenance = _provenance(index)
    try:
        await journal.append(evidence.PendingSegmentStartedEvidence(provenance))
        await journal.append(_start(provenance))
        await journal.append(_rx(provenance, b"noise\0\xffPA", 11))
        await journal.append(pending(start_row(index, sequence=3)))
        await journal.append(pending(tx_row(sequence=4, start=3)))
        await journal.append(
            pending(
                end_row(
                    sequence=5,
                    start=3,
                    tx_sequence=4,
                    outcome="cancelled",
                    observation={
                        "window": {"start_inclusive": 4, "end_exclusive": 4},
                        "outcome": "cancelled",
                        "examined_rx_bytes": 0,
                        "observer_loss_records": 0,
                        "match": None,
                        "clock": {
                            "origin_id": ORIGIN,
                            "started_at_ns": 100,
                            "deadline_at_ns": 1_000_000_100,
                            "decided_at_ns": 200,
                        },
                    },
                )
            )
        )
        await journal.append(annotation_draft())
        await journal.append(_rx(provenance, b"SStrailing", 12))
        await journal.append(
            replace(
                _end(),
                window=model.SequenceRange(2, 8),
                match=model.MonitorMatch(
                    model.MonitorMatchStart(2, 5), model.MonitorMatchEnd(7, 2)
                ),
            )
        )
    finally:
        await journal.close()
    reopened = await open_v4(path)
    try:
        page = await reopened.retrieve(
            evidence.EvidenceRetrievalRequest(reopened.session_id, 20, 20000)
        )
        assert len(page.records) == 9
        ended = page.records[-1]
        assert isinstance(ended, model.OperationEndedEvidence)
        assert ended.match is not None and ended.match.end.sequence == 7
    finally:
        await reopened.close()


@pytest.mark.parametrize(
    ("kind_index", "field", "value"),
    [
        (1, "operation_id", "99999999-1234-1234-1234-123456789abc"),
        (1, "accepted_prefix_bytes", 255),
        (1, "clock_origin_id", "99999999-1234-1234-1234-123456789abc"),
        (2, "tx.settled_at_ns", 99),
        (2, "tx.accepted_prefix_bytes", 255),
        (2, "observation.match.condition_index", 3),
        (2, "observation.match.end.byte_offset_exclusive", 3),
    ],
)
@pytest.mark.asyncio
async def test_t008_retained_pair_inconsistency_rolls_back_without_eviction(
    tmp_path: Path, kind_index: int, field: str, value: Any
) -> None:
    path = tmp_path / "pair.db"
    journal = await create_v4(path)
    try:
        await journal.append(evidence.PendingSegmentStartedEvidence(_provenance(0)))
        await journal.append(pending(start_row()))
        await journal.append(_rx(_provenance(0), b"PASS", 11))
        if kind_index == 2:
            await journal.append(
                pending(
                    tx_row(
                        tx=tx_facts(settled=99) if field == "tx.settled_at_ns" else None
                    )
                )
            )
        before = _database_state(path)
        invalid = changed((tx_row(), end_row())[kind_index - 1], field, value)
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(pending(invalid))
        assert caught.value.kind is evidence.JournalFailureKind.INVARIANT_VIOLATION
        assert _database_state(path) == before
    finally:
        await journal.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic-shape", "enhanced-shape"])
@pytest.mark.asyncio
async def test_precommit_unpaired_end_append_rejects_tx_before_its_own_observation(
    tmp_path: Path, index: int
) -> None:
    path = tmp_path / "unpaired-append.db"
    journal = await create_v4(path, replace(_policy(), max_retained_records=1))
    try:
        await journal.append(evidence.PendingSegmentStartedEvidence(_provenance(index)))
        await journal.append(pending(start_row(index)))
        await journal.append(_rx(_provenance(index), b"PASS", 11))
        await journal.append(pending(tx_row()))
        before = _database_state(path)
        # Appending the end would evict the only retained TX row. Both times
        # remain present in the end itself, without consulting an evicted start.
        invalid = pending(
            end_row(
                tx=tx_facts(settled=99),
                tx_sequence=None,
                audit={"source": "journal", "code": "io_failure"},
            )
        )
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(invalid)
        assert caught.value.kind is evidence.JournalFailureKind.INVARIANT_VIOLATION
        assert _database_state(path) == before
    finally:
        await journal.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic-shape", "enhanced-shape"])
@pytest.mark.parametrize("reader", ["writer", "terminal"])
@pytest.mark.asyncio
async def test_precommit_unpaired_end_open_rejects_tx_before_its_own_observation(
    tmp_path: Path, index: int, reader: str
) -> None:
    path = tmp_path / "unpaired-open.db"
    journal = await create_v4(path, replace(_policy(), max_retained_records=1))
    session, policy = journal.session_id, journal.policy
    try:
        await journal.append(evidence.PendingSegmentStartedEvidence(_provenance(index)))
        await journal.append(pending(start_row(index)))
        await journal.append(_rx(_provenance(index), b"PASS", 11))
        await journal.append(pending(tx_row()))
        observation = json.loads(end_row().metadata_json)["observation"]
        observation["clock"].update(
            started_at_ns=200, deadline_at_ns=1_000_000_200, decided_at_ns=200
        )
        await journal.append(pending(end_row(observation=observation)))
    finally:
        await journal.close()
    connection = sqlite3.connect(path)
    try:
        (raw,) = connection.execute(
            "SELECT metadata_json FROM evidence_records WHERE sequence=4"
        ).fetchone()
        metadata = json.loads(raw)
        metadata["tx"]["settled_at_ns"] = 199
        corrupt = _canonical(metadata)
        assert len(corrupt) == len(raw)  # All cached charges remain exact.
        connection.execute(
            "UPDATE evidence_records SET metadata_json=? WHERE sequence=4", (corrupt,)
        )
        connection.commit()
    finally:
        connection.close()
    target = terminal_evidence.capture_terminal_target(
        path, session_id=session, policy=policy, expected_schema_version=4
    )
    assert target is not None
    before = _files(path)
    expected = (
        evidence.JournalFailure
        if reader == "writer"
        else evidence_access.EvidenceSourceOpenFailure
    )
    with pytest.raises(expected) as caught:
        opened = (
            await open_v4(path, session)
            if reader == "writer"
            else await terminal_evidence.open_terminal_reader(target)
        )
        await opened.close()
    error = caught.value
    if isinstance(error, evidence_access.EvidenceSourceOpenFailure):
        assert error.reader_close_confirmed
        error = error.primary
    assert isinstance(error, evidence.JournalFailure)
    assert error.kind is evidence.JournalFailureKind.INVARIANT_VIOLATION
    assert _files(path) == before


@pytest.mark.parametrize(
    ("mutate", "kind"),
    [
        ("version", evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION),
        ("unknown", evidence.JournalFailureKind.CORRUPT_JOURNAL),
        ("shape", evidence.JournalFailureKind.CORRUPT_JOURNAL),
        (
            "envelope",
            evidence.JournalFailureKind.INCOMPATIBLE_PROVENANCE_ENVELOPE_VERSION,
        ),
        ("schema", evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION),
    ],
)
@pytest.mark.asyncio
async def test_t008_reopen_validates_unselected_v4_rows_without_repair(
    tmp_path: Path, mutate: str, kind: evidence.JournalFailureKind
) -> None:
    path = tmp_path / "corrupt.db"
    journal = await create_v4(path)
    await journal.append(pending(start_row(sequence=0)))
    await journal.close()
    if mutate == "schema":
        _sql(path, "PRAGMA user_version=3")
    elif mutate in {"version", "unknown"}:
        column, value = (
            ("record_version", 99)
            if mutate == "version"
            else ("record_kind", "future_unknown")
        )
        _sql(path, f"UPDATE evidence_records SET {column}=?", (value,))
    else:
        row = start_row(sequence=0)
        altered = changed(
            row,
            "extra"
            if mutate == "shape"
            else "provenance.connection_provenance.envelope_version",
            9,
        )
        _sql(
            path,
            "UPDATE evidence_records SET metadata_json=?,charged_bytes=?",
            (altered.metadata_json, altered.charged_bytes),
        )
        _sql(
            path,
            "UPDATE session_metadata SET retained_charged_bytes=?",
            (altered.charged_bytes,),
        )
    before = _files(path)
    with pytest.raises(evidence.JournalFailure) as caught:
        await open_v4(path)
    assert caught.value.kind is kind
    assert _files(path) == before


@pytest.mark.parametrize(
    ("kind_index", "field", "value"),
    [
        (1, "accepted_prefix_bytes", 255),
        (2, "operation_id", "99999999-1234-1234-1234-123456789abc"),
        (2, "observation.match.condition_index", 3),
    ],
)
@pytest.mark.asyncio
async def test_t008_reopen_retained_pair_corruption_is_invariant_violation(
    tmp_path: Path, kind_index: int, field: str, value: Any
) -> None:
    path = tmp_path / "retained-pair.db"
    journal = await create_v4(path)
    try:
        await journal.append(evidence.PendingSegmentStartedEvidence(_provenance(0)))
        await journal.append(pending(start_row()))
        await journal.append(_rx(_provenance(0), b"PASS", 11))
        await journal.append(pending(tx_row()))
        await journal.append(pending(end_row()))
    finally:
        await journal.close()
    original = (tx_row(), end_row())[kind_index - 1]
    altered = changed(original, field, value)
    _sql(
        path,
        "UPDATE evidence_records SET metadata_json=?,charged_bytes=? WHERE sequence=?",
        (altered.metadata_json, altered.charged_bytes, altered.sequence),
    )
    _sql(
        path,
        "UPDATE session_metadata SET retained_charged_bytes=retained_charged_bytes+?",
        (altered.charged_bytes - original.charged_bytes,),
    )
    before = _files(path)
    with pytest.raises(evidence.JournalFailure) as caught:
        await open_v4(path)
    assert caught.value.kind is evidence.JournalFailureKind.INVARIANT_VIOLATION
    assert _files(path) == before


@pytest.mark.parametrize("index", [0, 1], ids=["basic-shape", "enhanced-shape"])
@pytest.mark.asyncio
async def test_t008_v4_terminal_reads_are_verified_read_only_with_no_writer_fallback(
    tmp_path: Path, index: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "terminal.db"
    journal = await create_v4(path)
    await journal.append(pending(start_row(index, sequence=0)))
    session, policy = journal.session_id, journal.policy
    await journal.close()
    target = terminal_evidence.capture_terminal_target(
        path, session_id=session, policy=policy, expected_schema_version=4
    )
    assert target is not None and target.expected_schema_version == 4
    before = _files(path)
    real_connect = sqlite._connect_sqlite
    statements: list[str] = []

    def read_only_connect(database: str, *, uri: bool = False) -> sqlite3.Connection:
        assert uri and parse_qs(urlsplit(database).query).get("mode") == ["ro"]
        conn = real_connect(database, uri=uri)
        assert isinstance(conn, sqlite3.Connection)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(terminal_evidence, "_connect_sqlite", read_only_connect)
    monkeypatch.setattr(sqlite, "_connect_sqlite", _forbid_resources)
    reader = await terminal_evidence.open_terminal_reader(target)
    try:
        point = await reader.resolve_record(model.EvidenceReference(session, 0))
        assert len(point.records) == 1
        assert _api("encode_evidence_record_v4")(point.records[0]) == start_row(
            index, sequence=0
        )
        assert (
            await reader.retrieve(evidence.EvidenceRetrievalRequest(session, 20, 20000))
        ).records == point.records
    finally:
        await reader.close()
    assert any(statement.upper() == "PRAGMA QUERY_ONLY" for statement in statements)
    assert _files(path) == before


@pytest.mark.parametrize("stored", [1, 2, 3, 4])
@pytest.mark.parametrize("expected", [1, 2, 3, 4])
@pytest.mark.asyncio
async def test_t008_terminal_selected_version_never_guesses_or_mutates(
    tmp_path: Path, stored: int, expected: int
) -> None:
    from tests.contract.test_annotation_journal import create

    path = tmp_path / "selected.db"
    journal = await create_v4(path) if stored == 4 else await create(path, stored)
    session, policy = journal.session_id, journal.policy
    await journal.close()
    target = terminal_evidence.capture_terminal_target(
        path, session_id=session, policy=policy, expected_schema_version=expected
    )
    assert target is not None
    before = _files(path)
    if expected == stored:
        reader = await terminal_evidence.open_terminal_reader(target)
        await reader.close()
    else:
        with pytest.raises(evidence_access.EvidenceSourceOpenFailure) as caught:
            await terminal_evidence.open_terminal_reader(target)
        assert isinstance(caught.value.primary, evidence.JournalFailure)
        assert (
            caught.value.primary.kind
            is evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION
        )
        assert caught.value.reader_close_confirmed
    assert _files(path) == before


def maximum_rows(
    payload_length: int,
) -> tuple[
    sqlite.EncodedEvidenceRecord,
    tuple[sqlite.EncodedEvidenceRecord, ...],
    tuple[sqlite.EncodedEvidenceRecord, ...],
]:
    # Counter/position widths are maximal while every standalone reference and
    # clock is legal. Start is the actual request, not a maximal replacement.
    tx_rows = [
        tx_row(
            sequence=MAX - 1,
            start=MAX // 2,
            tx=tx_facts(
                status=status,
                count=count,
                submitted=status != "not_submitted",
                failure=failure,
                settled=MAX,
            ),
        )
        for status, count, failure in [
            ("acknowledged", payload_length, None),
            ("partial", payload_length - 1, None),
            ("timeout", None, None),
            ("disconnected", None, None),
            ("not_submitted", None, None),
            *(("failure", None, k.value) for k in BackendFailureKind),
        ]
    ]
    end_rows = []
    for outcome in model.InteractOutcome:
        for missing_ack in (False, True):
            observation_outcome = (
                outcome.value
                if outcome.value in {o.value for o in model.InteractObservationOutcome}
                else "tx_failed"
            )
            obs = {
                "window": {"start_inclusive": MAX // 2 + 1, "end_exclusive": MAX - 2},
                "outcome": observation_outcome,
                "examined_rx_bytes": 1048576,
                "observer_loss_records": MAX // 2 - 6,
                "match": {
                    "condition_index": 3,
                    "start": {"sequence": MAX - 3, "byte_offset": 1048320},
                    "end": {"sequence": MAX - 3, "byte_offset_exclusive": 1048576},
                }
                if outcome is model.InteractOutcome.MATCHED
                else None,
                "clock": {
                    "origin_id": ORIGIN,
                    "started_at_ns": MAX - 4_000_000_000,
                    "deadline_at_ns": MAX,
                    "decided_at_ns": MAX
                    if outcome is model.InteractOutcome.TIMEOUT
                    else MAX - 1,
                },
            }
            facts = tx_facts(count=payload_length, settled=MAX)
            if outcome is model.InteractOutcome.WRITE_TIMEOUT:
                facts = tx_facts(status="timeout", count=None, settled=MAX)
            elif outcome is model.InteractOutcome.PARTIAL_WRITE:
                facts = tx_facts(
                    status="partial", count=payload_length - 1, settled=MAX
                )
            end_rows.append(
                end_row(
                    sequence=MAX - 1,
                    start=MAX // 2,
                    tx_sequence=None if missing_ack else MAX - 2,
                    tx=facts,
                    outcome=outcome.value,
                    observation=obs,
                    audit={
                        "source": "journal",
                        "code": "incompatible_provenance_envelope_version",
                    }
                    if missing_ack
                    else None,
                )
            )
    for tx in tx_rows:
        facts = json.loads(tx.metadata_json)
        del facts["operation_id"], facts["start_sequence"]
        overall = {
            "acknowledged": "matched",
            "partial": "partial_write",
            "timeout": "write_timeout",
            "disconnected": "disconnected",
            "failure": "transport_failure",
            "not_submitted": "cancelled",
        }[facts["status"]]
        for missing_ack in (False, True):
            template = next(
                row
                for row in end_rows
                if json.loads(row.metadata_json)["outcome"] == overall
            )
            metadata = json.loads(template.metadata_json)
            metadata["tx"] = facts
            metadata["tx_settled_sequence"] = None if missing_ack else MAX - 2
            metadata["tx_audit_failure"] = (
                {"source": "service", "code": "internal_failure"}
                if missing_ack
                else None
            )
            end_rows.append(_encoded("interact_ended", MAX - 1, metadata))
    metadata = json.loads(start_row().metadata_json)
    metadata.update(
        conditions_base64=[
            base64.b64encode(bytes([value]) * 256).decode() for value in range(4)
        ],
        timeout_ms=4000,
        max_rx_bytes=1048576,
    )
    start = _encoded("interact_started", 1, metadata, b"x" * payload_length)
    return start, tuple(tx_rows), tuple(end_rows)


@pytest.mark.parametrize("payload_length", [1, 256, 4096])
def test_t008_charge_callback_uses_only_legal_max_shapes_and_exact_codec_charges(
    monkeypatch: pytest.MonkeyPatch,
    payload_length: int,
) -> None:
    callback = _api("charge_interact_markers")
    encoder = _api("encode_evidence_record_v4")
    start, tx_rows, end_rows = maximum_rows(payload_length)
    observed: list[sqlite.EncodedEvidenceRecord] = []

    def traced_encoder(record: Any) -> sqlite.EncodedEvidenceRecord:
        encoded = encoder(record)
        assert isinstance(encoded, sqlite.EncodedEvidenceRecord)
        _decode(encoded)
        observed.append(encoded)
        return encoded

    txs, ends = (
        tuple(pending(row) for row in tx_rows),
        tuple(pending(row) for row in end_rows),
    )
    monkeypatch.setattr(sqlite, "encode_evidence_record_v4", traced_encoder)
    monkeypatch.setattr(sqlite, "_connect_sqlite", _forbid_resources)
    charges = callback(pending(start), txs, ends)
    assert type(charges) is tuple and len(charges) == 3
    assert all(type(charge) is int and charge > 0 for charge in charges)
    assert charges[0] == start.charged_bytes
    assert charges[1] >= max(row.charged_bytes for row in tx_rows)
    assert charges[2] >= max(row.charged_bytes for row in end_rows)
    for kind, charge in zip(KINDS, charges, strict=True):
        assert charge == max(
            row.charged_bytes for row in observed if row.record_kind == kind
        )
