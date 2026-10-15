"""009 T006 RED: explicit v2 persistence using the existing journal contract.

These tests deliberately fail until T007 supplies create_v2/open_v2 and versioned
execution. Helpers seed/mutate test-owned files only; they implement no adapter.
"""

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from dutchmate_core import evidence, model
from dutchmate_core.adapters import sqlite_evidence as sqlite
from tests.contract.test_sqlite_evidence_journal import (
    _database_state,
    _every_pending_variant,
    _policy,
    _segment_provenance,
)
from tests.fakes import BACKEND_FIXTURE_FACTORIES

_OPERATION = "abcdefab-1234-1234-1234-123456789abc"
_ORIGIN = "12345678-1234-1234-1234-123456789abc"


async def _create_v2(
    path: Path, policy: model.SessionPolicy
) -> sqlite.SqliteEvidenceJournal:
    create = getattr(sqlite.SqliteEvidenceJournal, "create_v2", None)
    assert callable(create), "T007 missing: explicit SqliteEvidenceJournal.create_v2"
    result = await create(path, policy)
    assert isinstance(result, sqlite.SqliteEvidenceJournal)
    return result


async def _open_v2(
    path: Path, session: model.SessionId | None = None
) -> sqlite.SqliteEvidenceJournal:
    operation = getattr(sqlite.SqliteEvidenceJournal, "open_v2", None)
    assert callable(operation), "T007 missing: explicit SqliteEvidenceJournal.open_v2"
    result = await operation(path, expected_session_id=session)
    assert isinstance(result, sqlite.SqliteEvidenceJournal)
    return result


def _provenance(index: int) -> model.SegmentProvenance:
    descriptor = BACKEND_FIXTURE_FACTORIES[index]().connection.descriptor
    return replace(
        _segment_provenance(),
        capabilities=descriptor.capabilities,
        backend_observation_timestamp_domain=descriptor.backend_observation_timestamp_domain,
        loss_observability=descriptor.loss_observability,
    )


def _start(
    provenance: model.SegmentProvenance,
) -> evidence.PendingOperationStartedEvidence:
    return evidence.PendingOperationStartedEvidence(
        operation_id=_OPERATION,
        operation_kind="monitor",
        provenance=provenance,
        timeout_ms=1000,
        max_rx_bytes=1024,
        clock_origin_id=_ORIGIN,
        condition=b"\0\xffPASS",
    )


def _rx(
    provenance: model.SegmentProvenance, payload: bytes, timestamp: int
) -> evidence.PendingRxBytesEvidence:
    return evidence.PendingRxBytesEvidence(
        provenance.connection_id,
        provenance.segment_id,
        payload,
        model.BackendObservationTimestamp(
            provenance.backend_observation_timestamp_domain.domain_id, timestamp
        ),
    )


def _end() -> evidence.PendingOperationEndedEvidence:
    return evidence.PendingOperationEndedEvidence(
        operation_id=_OPERATION,
        operation_kind="monitor",
        start_sequence=1,
        window=model.SequenceRange(2, 4),
        outcome=model.MonitorOutcome.MATCHED,
        examined_rx_bytes=11,
        observer_loss_records=0,
        match=model.MonitorMatch(
            model.MonitorMatchStart(2, 5), model.MonitorMatchEnd(3, 2)
        ),
        clock=model.MonitorClockFacts(_ORIGIN, 100, 1_000_000_100, 200),
    )


@dataclass(frozen=True)
class V2Seed:
    path: Path
    session: model.SessionId
    policy: model.SessionPolicy
    records: tuple[model.EvidenceRecord, ...]
    page: evidence.EvidencePage


async def _seed_v2(path: Path, index: int = 0, *, retained: int = 100) -> V2Seed:
    policy = _policy(max_retained_records=retained)
    provenance = _provenance(index)
    journal = await _create_v2(path, policy)
    records = []
    try:
        for draft in (
            evidence.PendingSegmentStartedEvidence(provenance),
            _start(provenance),
            _rx(provenance, b"noise\0\xffPA", 11),
            _rx(provenance, b"SStrailing", 12),
            _end(),
        ):
            records.append(await journal.append(draft))
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(journal.session_id, 20, 20000)
        )
        return V2Seed(path, journal.session_id, policy, tuple(records), page)
    finally:
        await journal.close()


def _rows(path: Path) -> list[tuple[Any, ...]]:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(
            "SELECT sequence, record_kind, record_version, metadata_json, payload, "
            "charged_bytes, rx_payload_bytes, timestamp_endpoint_json "
            "FROM evidence_records ORDER BY sequence"
        ).fetchall()


def _sql(path: Path, statement: str, parameters: tuple[object, ...] = ()) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(statement, parameters)
        connection.commit()


def _files(path: Path) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.parent.iterdir()
        if p.is_file()
    }


@pytest.mark.asyncio
async def test_t006_v2_schema_keeps_application_id_three_tables_and_captured_policy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "explicit-v2.sqlite3"
    policy = _policy()
    journal = await _create_v2(path, policy)
    try:
        session = journal.session_id
        assert (
            journal.policy == policy
            and journal.physical_page_ceiling == policy.max_database_pages
        )
    finally:
        await journal.close()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA application_id").fetchone() == (0x4455544D,)
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert connection.execute(
            "SELECT schema_version, session_id FROM session_metadata"
        ).fetchall() == [(2, session.value)]
        assert {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        } == {"session_metadata", "evidence_records", "retention_marker"}
        assert connection.execute("PRAGMA page_size").fetchone() == (4096,)


@pytest.mark.asyncio
async def test_t006_default_factory_remains_v1_and_rejects_both_operation_drafts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.sqlite3"
    journal = await sqlite.SqliteEvidenceJournal.create(path, _policy())
    try:
        await journal.append(evidence.PendingSegmentStartedEvidence(_provenance(0)))
        before = _database_state(path)
        for draft in (_start(_provenance(0)), _end()):
            with pytest.raises(evidence.JournalFailure) as caught:
                await journal.append(draft)
            assert caught.value.kind is evidence.JournalFailureKind.INVALID_INPUT
            assert _database_state(path) == before
        session = journal.session_id
    finally:
        await journal.close()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute(
            "SELECT schema_version FROM session_metadata"
        ).fetchone() == (1,)
    reopened = await sqlite.SqliteEvidenceJournal.open(
        path, expected_session_id=session
    )
    await reopened.close()


@pytest.mark.asyncio
async def test_t006_old_four_rows_and_charges_are_byte_identical_under_v2(
    tmp_path: Path,
) -> None:
    legacy_path, new_path = tmp_path / "legacy.sqlite3", tmp_path / "new.sqlite3"
    old = await sqlite.SqliteEvidenceJournal.create(legacy_path, _policy())
    try:
        for draft in _every_pending_variant():
            await old.append(draft)
    finally:
        await old.close()
    new = await _create_v2(new_path, _policy())
    try:
        for draft in _every_pending_variant():
            await new.append(draft)
    finally:
        await new.close()
    assert _rows(new_path) == _rows(legacy_path)
    assert [r[2] for r in _rows(new_path)] == [1, 1, 1, 1]


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t006_marker_rows_reopen_and_point_page_readback_preserve_binary_provenance_and_charge(
    tmp_path: Path, index: int
) -> None:
    seed = await _seed_v2(tmp_path / "v2.sqlite3", index)
    rows = _rows(seed.path)
    assert [row[2] for row in rows] == [1, 2, 1, 1, 2]
    assert rows[1][4] == b"\0\xffPASS" and rows[4][4] == b""
    assert rows[2][4] == b"noise\0\xffPA" and rows[3][4] == b"SStrailing"
    for row in rows:
        assert row[5] == 16 + len(row[1].encode("utf-8")) + len(row[3]) + len(
            row[4] or b""
        )
    for row in (rows[1], rows[4]):
        assert row[6] == 0 and row[7] is None
    metadata = json.loads(rows[1][3])
    assert metadata["provenance"]["connection_provenance"]["envelope_version"] == 1
    assert seed.page.records == seed.records
    assert seed.page.charged_bytes == sum(row[5] for row in rows)
    reopened = await _open_v2(seed.path, seed.session)
    try:
        assert reopened.policy == seed.policy
        page = await reopened.retrieve(
            evidence.EvidenceRetrievalRequest(seed.session, 20, 20000)
        )
        assert page == seed.page
        for sequence in (1, 4):
            single = await reopened.resolve_record(
                model.EvidenceReference(seed.session, sequence)
            )
            assert single.records == (seed.records[sequence],)
        following = await reopened.append(_rx(_provenance(index), b"ambient", 13))
        assert following.sequence == 5
    finally:
        await reopened.close()


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.asyncio
async def test_t006_open_variants_require_explicit_matching_schema_without_migration(
    tmp_path: Path, version: int
) -> None:
    path = tmp_path / "journal.sqlite3"
    journal = await (
        sqlite.SqliteEvidenceJournal.create(path, _policy())
        if version == 1
        else _create_v2(path, _policy())
    )
    await journal.close()
    before = _files(path)
    with pytest.raises(evidence.JournalFailure) as caught:
        wrong = await (
            _open_v2(path) if version == 1 else sqlite.SqliteEvidenceJournal.open(path)
        )
        await wrong.close()
    assert caught.value.operation is evidence.JournalOperation.OPEN
    assert caught.value.kind is evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION
    assert _files(path) == before


@pytest.mark.asyncio
async def test_t006_v2_factories_preserve_exists_missing_and_session_mismatch_errors(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.sqlite3"
    journal = await _create_v2(path, _policy())
    await journal.close()
    before = _files(path)
    for action, kind in (
        ("create", evidence.JournalFailureKind.JOURNAL_EXISTS),
        ("missing", evidence.JournalFailureKind.JOURNAL_MISSING),
        ("session", evidence.JournalFailureKind.SESSION_MISMATCH),
    ):
        with pytest.raises(evidence.JournalFailure) as caught:
            if action == "create":
                opened = await _create_v2(path, _policy())
            elif action == "missing":
                opened = await _open_v2(tmp_path / "missing.sqlite3")
            else:
                opened = await _open_v2(path, model.SessionId("wrong"))
            await opened.close()
        assert caught.value.kind is kind
    assert _files(path) == before


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t006_rolling_markers_expire_normally_and_do_not_inflate_rx_or_host_timestamp_telemetry(
    tmp_path: Path, index: int
) -> None:
    seed = await _seed_v2(tmp_path / "rolling.sqlite3", index, retained=2)
    journal = await _open_v2(seed.path)
    try:
        assert seed.page.outcome is evidence.EvidencePageOutcome.PARTIAL
        assert [r.sequence for r in seed.page.records] == [3, 4]
        assert seed.page.expired_range == model.SequenceRange(0, 3)
        marker = seed.page.retention_marker
        assert marker is not None
        assert marker.discarded_record_count == 3
        assert marker.discarded_rx_payload_byte_count == 9
        assert marker.first_discarded_timestamp is not None
        assert marker.first_discarded_timestamp == marker.last_discarded_timestamp
        assert marker.first_discarded_timestamp.timestamp.value == 11
        assert (
            marker.first_discarded_timestamp.domain
            == _provenance(index).backend_observation_timestamp_domain
        )
        for seq in (0, 1, 2):
            expired = await journal.resolve_record(
                model.EvidenceReference(seed.session, seq)
            )
            assert expired.outcome is evidence.EvidencePageOutcome.EXPIRED
        missing = await journal.resolve_record(model.EvidenceReference(seed.session, 5))
        assert missing.outcome is evidence.EvidencePageOutcome.NOT_FOUND
        await journal.append(_rx(_provenance(index), b"later", 13))
        expired = await journal.resolve_record(model.EvidenceReference(seed.session, 3))
        assert expired.retention_marker is not None
        assert expired.retention_marker.expired_range == model.SequenceRange(0, 4)
        assert expired.retention_marker.discarded_rx_payload_byte_count == 19
    finally:
        await journal.close()


@pytest.mark.asyncio
async def test_t006_marker_pages_keep_fixed_snapshots_and_zero_byte_shortage_positions(
    tmp_path: Path,
) -> None:
    seed = await _seed_v2(tmp_path / "snapshot.sqlite3")
    journal = await _open_v2(seed.path)
    try:
        shortage = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                model.EvidenceRangeReference(seed.session, 1, 5),
                20,
                1,
            )
        )
        assert shortage.records == () and shortage.truncated
        assert shortage.next_record_required_bytes == _rows(seed.path)[1][5]
        assert shortage.continuation is not None
        assert shortage.continuation.next_sequence == 1
        assert shortage.snapshot_end_exclusive == 5
        await journal.append(_rx(_provenance(0), b"outside snapshot", 13))
        resumed = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                model.EvidenceRangeReference(seed.session, 1, 5),
                20,
                20000,
                shortage.continuation,
            )
        )
        assert [r.sequence for r in resumed.records] == [1, 2, 3, 4]
        assert resumed.snapshot_end_exclusive == 5 and not resumed.truncated
    finally:
        await journal.close()


@pytest.mark.asyncio
async def test_t006_charge_ceiling_rejects_whole_marker_before_retention_and_accepts_equality(
    tmp_path: Path,
) -> None:
    draft = _start(_provenance(0))
    charge = sqlite.encode_evidence_record_v2(
        evidence._assign_sequence(draft, 0)
    ).charged_bytes
    for limit in (charge - 1, charge):
        policy = _policy(
            max_retained_charged_bytes=charge,
            max_record_charged_bytes=limit,
            max_retrieval_page_charged_bytes=charge,
        )
        path = tmp_path / f"charge-{limit}.sqlite3"
        journal = await _create_v2(path, policy)
        try:
            before = _database_state(path)
            if limit < charge:
                with pytest.raises(evidence.JournalFailure) as caught:
                    await journal.append(draft)
                assert caught.value.kind is evidence.JournalFailureKind.CAPACITY
                assert _database_state(path) == before
            else:
                recorded = await journal.append(draft)
                assert recorded.sequence == 0
                assert _rows(path)[0][5] == charge
        finally:
            await journal.close()


@pytest.mark.asyncio
async def test_t006_sequence_exhaustion_fails_before_insertion(tmp_path: Path) -> None:
    path = tmp_path / "exhausted.sqlite3"
    journal = await _create_v2(path, _policy())
    try:
        maximum = model.SQLITE_INTEGER_MAX
        # A consistent empty retained suffix and coalesced expired prefix.
        _sql(
            path,
            "UPDATE session_metadata SET next_sequence=?,low_water_sequence=?",
            (maximum, maximum),
        )
        _sql(
            path,
            "INSERT INTO retention_marker VALUES (1,0,?,NULL,NULL,?,0,0)",
            (maximum, maximum),
        )
        before = _database_state(path)
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(_start(_provenance(0)))
        assert caught.value.kind is evidence.JournalFailureKind.SEQUENCE_EXHAUSTED
        assert _database_state(path) == before
    finally:
        await journal.close()


@pytest.mark.asyncio
async def test_t006_retention_counter_overflow_rolls_back_marker_and_eviction(
    tmp_path: Path,
) -> None:
    seed = await _seed_v2(tmp_path / "counter.sqlite3", retained=2)
    journal = await _open_v2(seed.path)
    try:
        _sql(
            seed.path,
            "UPDATE retention_marker SET discarded_charged_bytes=?",
            (model.SQLITE_INTEGER_MAX,),
        )
        before = _database_state(seed.path)
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(_rx(_provenance(0), b"next", 13))
        assert caught.value.kind is evidence.JournalFailureKind.COUNTER_EXHAUSTED
        assert _database_state(seed.path) == before
    finally:
        await journal.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize(
    ("bounds", "outcome", "next_sequence"),
    [
        ((0, 2), evidence.EvidencePageOutcome.EXPIRED, None),
        ((1, 5), evidence.EvidencePageOutcome.PARTIAL, 3),
        ((3, 5), evidence.EvidencePageOutcome.COMPLETE, 3),
        ((6, 7), evidence.EvidencePageOutcome.NOT_FOUND, None),
    ],
    ids=["expired", "partial-shortage", "complete-shortage", "not-found"],
)
@pytest.mark.asyncio
async def test_t018_zero_record_pages_keep_outcome_cursor_and_exact_marker_counters(
    tmp_path: Path,
    index: int,
    bounds: tuple[int, int],
    outcome: evidence.EvidencePageOutcome,
    next_sequence: int | None,
) -> None:
    path = tmp_path / "zero-record.sqlite3"
    journal = await _create_v2(path, _policy(max_retained_records=3))
    provenance = _provenance(index)
    drafts = (
        evidence.PendingSegmentStartedEvidence(provenance),
        _start(provenance),
        _rx(provenance, b"noise\0\xffPA", 11),
        _rx(provenance, b"SStrailing", 12),
        _end(),
        _rx(provenance, b"later\0\xff", 13),
    )
    records = []
    try:
        for draft in drafts:
            records.append(await journal.append(draft))
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                model.EvidenceRangeReference(journal.session_id, *bounds), 20, 1
            )
        )
        assert page.outcome is outcome and page.records == ()
        assert page.charged_bytes == 0
        assert page.never_existed_range == (
            model.SequenceRange(6, 7)
            if outcome is evidence.EvidencePageOutcome.NOT_FOUND
            else None
        )
        assert page.truncated is (next_sequence is not None)
        if next_sequence is None:
            assert page.continuation is None and page.next_record_required_bytes is None
        else:
            assert page.continuation is not None
            assert page.continuation.next_sequence == next_sequence
            assert (
                page.next_record_required_bytes
                == sqlite.encode_evidence_record_v2(
                    records[next_sequence]
                ).charged_bytes
            )
        if outcome in {
            evidence.EvidencePageOutcome.EXPIRED,
            evidence.EvidencePageOutcome.PARTIAL,
        }:
            assert page.expired_range == model.SequenceRange(
                bounds[0], min(bounds[1], 3)
            )
        else:
            assert page.expired_range is None
        # A page exposes retention metadata only for its intersecting expiry.
        assert (page.retention_marker is not None) is (page.expired_range is not None)
        whole = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(journal.session_id, 20, 20000)
        )
        marker = whole.retention_marker
        assert marker is not None and marker.expired_range == model.SequenceRange(0, 3)
        assert marker.discarded_record_count == 3
        assert marker.discarded_rx_payload_byte_count == 9
        assert marker.discarded_charged_bytes == sum(
            sqlite.encode_evidence_record_v2(record).charged_bytes
            for record in records[:3]
        )
        assert (
            marker.first_discarded_timestamp
            == marker.last_discarded_timestamp
            == model.RetentionTimestampEndpoint(
                model.BackendObservationTimestamp(
                    provenance.backend_observation_timestamp_domain.domain_id, 11
                ),
                provenance.backend_observation_timestamp_domain,
            )
        )
        # Markers have zero RX charge and no cached host-clock timestamp endpoint.
        rows = _rows(path)
        assert [row[0] for row in rows] == [3, 4, 5]
        assert rows[1][6:] == (0, None)
        assert rows[0][4] == b"SStrailing" and rows[2][4] == b"later\0\xff"
    finally:
        await journal.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t018_eviction_of_remaining_snapshot_returns_expired_without_chasing_new_rows(
    tmp_path: Path,
    index: int,
) -> None:
    seed = await _seed_v2(tmp_path / "evict-snapshot.sqlite3", index, retained=2)
    journal = await _open_v2(seed.path)
    try:
        first = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(seed.session, 1, 20000)
        )
        assert first.outcome is evidence.EvidencePageOutcome.PARTIAL
        assert first.records == (seed.records[3],) and first.snapshot_end_exclusive == 5
        assert first.continuation is not None and first.continuation.next_sequence == 4
        await journal.append(_rx(_provenance(index), b"new-one", 13))
        await journal.append(_rx(_provenance(index), b"new-two", 14))
        resumed = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                seed.session, 1, 20000, first.continuation
            )
        )
        assert resumed.outcome is evidence.EvidencePageOutcome.EXPIRED
        assert resumed.records == () and resumed.snapshot_end_exclusive == 5
        assert resumed.expired_range == model.SequenceRange(4, 5)
        assert not resumed.truncated and resumed.continuation is None
        assert resumed.next_record_required_bytes is None
        for seq in (1, 2, 3, 4):
            point = await journal.resolve_record(
                model.EvidenceReference(seed.session, seq)
            )
            assert point.outcome is evidence.EvidencePageOutcome.EXPIRED
        latest = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(seed.session, 20, 20000)
        )
        assert [record.sequence for record in latest.records] == [5, 6]
        assert latest.retention_marker is not None
        assert latest.retention_marker.expired_range == model.SequenceRange(0, 5)
        assert latest.retention_marker.discarded_record_count == 5
        assert latest.retention_marker.discarded_rx_payload_byte_count == 19
        assert latest.retention_marker.discarded_charged_bytes == sum(
            sqlite.encode_evidence_record_v2(record).charged_bytes
            for record in seed.records
        )
    finally:
        await journal.close()


# Each mutation isolates a stored-version/shape/schema invariant, not a live Monitor.
_CORRUPTIONS = [
    ("PRAGMA application_id=1", evidence.JournalFailureKind.INCOMPATIBLE_APPLICATION),
    ("PRAGMA user_version=1", evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION),
    (
        "UPDATE session_metadata SET schema_version=1",
        evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION,
    ),
    (
        "UPDATE evidence_records SET record_version=1 WHERE sequence=1",
        evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION,
    ),
    (
        "UPDATE evidence_records SET record_version=2 WHERE sequence=2",
        evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION,
    ),
    (
        "UPDATE evidence_records SET record_version=3 WHERE sequence=4",
        evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION,
    ),
    (
        "UPDATE evidence_records SET record_kind='operation_other' WHERE sequence=4",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "UPDATE evidence_records SET metadata_json=X'7b7d' WHERE sequence=4",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "UPDATE evidence_records SET payload=NULL WHERE sequence=4",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "UPDATE evidence_records SET rx_payload_bytes=6 WHERE sequence=1",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "UPDATE evidence_records SET timestamp_endpoint_json=X'7b7d' WHERE sequence=4",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "UPDATE evidence_records SET charged_bytes=charged_bytes+1 WHERE sequence=1",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "ALTER TABLE evidence_records ADD COLUMN unexpected TEXT",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    ("CREATE TABLE operations (id TEXT)", evidence.JournalFailureKind.CORRUPT_JOURNAL),
    (
        "CREATE INDEX sqliteX_extra ON evidence_records(record_kind)",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "CREATE VIEW sqliteX_extra AS SELECT sequence FROM evidence_records",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
    (
        "CREATE TRIGGER sqliteX_extra AFTER INSERT ON evidence_records BEGIN SELECT 1; END",
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    ),
]


@pytest.mark.parametrize("statement,kind", _CORRUPTIONS)
@pytest.mark.asyncio
async def test_t006_v2_open_strictly_rejects_unknown_versions_shapes_and_schema_without_repair(
    tmp_path: Path, statement: str, kind: evidence.JournalFailureKind
) -> None:
    seed = await _seed_v2(tmp_path / "corrupt.sqlite3")
    # Test-owned mutation can bypass SQL CHECK only to isolate the decoder rule.
    with closing(sqlite3.connect(seed.path)) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(statement)
        connection.commit()
    before = _files(seed.path)
    with pytest.raises(evidence.JournalFailure) as caught:
        opened = await _open_v2(seed.path, seed.session)
        await opened.close()
    assert caught.value.operation is evidence.JournalOperation.OPEN
    assert caught.value.kind is kind
    assert _files(seed.path) == before


def _rewrite_end(path: Path, field: str, value: object) -> None:
    row = _rows(path)[4]
    metadata = json.loads(row[3])
    metadata[field] = value
    blob = json.dumps(
        metadata,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    charge = 16 + len("operation_ended") + len(blob)
    _sql(
        path,
        "UPDATE evidence_records SET metadata_json=?,charged_bytes=? WHERE sequence=4",
        (blob, charge),
    )
    _sql(
        path,
        "UPDATE session_metadata SET retained_charged_bytes=retained_charged_bytes+?",
        (charge - row[5],),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation_id", "00000000-0000-0000-0000-000000000000"),
        ("examined_rx_bytes", 1025),
        (
            "clock",
            {
                "origin_id": "00000000-0000-0000-0000-000000000000",
                "started_at_ns": 100,
                "deadline_at_ns": 1_000_000_100,
                "decided_at_ns": 200,
            },
        ),
        (
            "clock",
            {
                "origin_id": _ORIGIN,
                "started_at_ns": 100,
                "deadline_at_ns": 1_000_000_101,
                "decided_at_ns": 200,
            },
        ),
        (
            "match",
            {
                "start": {"sequence": 2, "byte_offset": 6},
                "end": {"sequence": 3, "byte_offset_exclusive": 2},
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_t006_retained_pair_inconsistency_rejects_without_requiring_evicted_pairs(
    tmp_path: Path, field: str, value: object
) -> None:
    seed = await _seed_v2(tmp_path / "pair.sqlite3")
    _rewrite_end(seed.path, field, value)
    before = _files(seed.path)
    with pytest.raises(evidence.JournalFailure) as caught:
        opened = await _open_v2(seed.path)
        await opened.close()
    assert caught.value.kind is evidence.JournalFailureKind.INVARIANT_VIOLATION
    assert _files(seed.path) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation_kind", "interact"),
        ("examined_rx_bytes", True),
        ("unexpected", 0),
        ("match", None),
    ],
)
@pytest.mark.asyncio
async def test_t006_malformed_persisted_marker_rejects_even_with_valid_charge_and_aggregates(
    tmp_path: Path, field: str, value: object
) -> None:
    seed = await _seed_v2(tmp_path / "marker-shape.sqlite3")
    _rewrite_end(seed.path, field, value)
    before = _files(seed.path)
    with pytest.raises(evidence.JournalFailure) as caught:
        opened = await _open_v2(seed.path)
        await opened.close()
    assert caught.value.kind is evidence.JournalFailureKind.CORRUPT_JOURNAL
    assert _files(seed.path) == before


@pytest.mark.asyncio
async def test_t006_operation_provenance_retains_strict_generic_envelope_v1(
    tmp_path: Path,
) -> None:
    seed = await _seed_v2(tmp_path / "envelope.sqlite3")
    row = _rows(seed.path)[1]
    changed = row[3].replace(b'"envelope_version":1', b'"envelope_version":2')
    assert changed != row[3] and len(changed) == len(row[3])
    _sql(
        seed.path,
        "UPDATE evidence_records SET metadata_json=? WHERE sequence=1",
        (changed,),
    )
    before = _files(seed.path)
    with pytest.raises(evidence.JournalFailure) as caught:
        opened = await _open_v2(seed.path)
        await opened.close()
    assert (
        caught.value.kind
        is evidence.JournalFailureKind.INCOMPATIBLE_PROVENANCE_ENVELOPE_VERSION
    )
    assert _files(seed.path) == before


@pytest.mark.asyncio
async def test_t006_v2_open_keeps_persisted_database_page_ceiling(
    tmp_path: Path,
) -> None:
    seed = await _seed_v2(tmp_path / "ceiling.sqlite3")
    with closing(sqlite3.connect(seed.path)) as connection:
        assert connection.execute("PRAGMA page_count").fetchone()[0] > 1
    _sql(seed.path, "UPDATE session_metadata SET max_database_pages=1")
    before = _files(seed.path)
    with pytest.raises(evidence.JournalFailure) as caught:
        opened = await _open_v2(seed.path)
        await opened.close()
    assert caught.value.kind is evidence.JournalFailureKind.DATABASE_OVER_CEILING
    assert _files(seed.path) == before


@pytest.mark.asyncio
async def test_t007_inconsistent_end_rolls_back_retention_before_a_valid_end_commits(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pair-rollback.sqlite3"
    provenance = _provenance(0)
    journal = await _create_v2(path, _policy(max_retained_records=4))
    try:
        for draft in (
            evidence.PendingSegmentStartedEvidence(provenance),
            _start(provenance),
            _rx(provenance, b"noise\0\xffPA", 11),
            _rx(provenance, b"SStrailing", 12),
        ):
            await journal.append(draft)
        before = _database_state(path)
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(replace(_end(), examined_rx_bytes=1025))
        assert caught.value.operation is evidence.JournalOperation.APPEND
        assert caught.value.kind is evidence.JournalFailureKind.INVARIANT_VIOLATION
        assert _database_state(path) == before
        accepted = await journal.append(_end())
        assert accepted.sequence == 4
        expired = await journal.resolve_record(
            model.EvidenceReference(journal.session_id, 0)
        )
        assert expired.outcome is evidence.EvidencePageOutcome.EXPIRED
        assert expired.retention_marker is not None
        assert expired.retention_marker.expired_range == model.SequenceRange(0, 1)
    finally:
        await journal.close()
