"""Explicit v3 persistence/compatibility without live annotation composition."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from dutchmate_core import evidence, model
from dutchmate_core.adapters import sqlite_evidence as sqlite
from tests.contract.test_monitor_journal import (
    _end,
    _files,
    _provenance,
    _rows,
    _rx,
    _sql,
    _start,
)
from tests.contract.test_sqlite_evidence_journal import (
    _database_state,
    _every_pending_variant,
    _policy,
)
from tests.unit.test_annotation_values import draft


async def create(
    path: Path, version: int = 3, policy: model.SessionPolicy | None = None
) -> sqlite.SqliteEvidenceJournal:
    chosen = _policy() if policy is None else policy
    if version == 1:
        return await sqlite.SqliteEvidenceJournal.create(path, chosen)
    if version == 2:
        return await sqlite.SqliteEvidenceJournal.create_v2(path, chosen)
    assert version == 3
    return await sqlite.SqliteEvidenceJournal.create_v3(path, chosen)


async def reopen(
    path: Path, version: int, session: model.SessionId | None = None
) -> sqlite.SqliteEvidenceJournal:
    if version == 1:
        return await sqlite.SqliteEvidenceJournal.open(path, session)
    if version == 2:
        return await sqlite.SqliteEvidenceJournal.open_v2(path, session)
    assert version == 3
    return await sqlite.SqliteEvidenceJournal.open_v3(path, session)


async def seed_match(
    path: Path, index: int, *, annotation: bool = True, version: int = 3
) -> model.SessionId:
    provenance = _provenance(index)
    journal = await create(path, version)
    end = _end()
    if annotation:
        end = replace(
            end,
            window=model.SequenceRange(2, 5),
            match=model.MonitorMatch(
                model.MonitorMatchStart(2, 5), model.MonitorMatchEnd(4, 2)
            ),
        )
    try:
        await journal.append(evidence.PendingSegmentStartedEvidence(provenance))
        await journal.append(_start(provenance))
        await journal.append(_rx(provenance, b"noise\0\xffPA", 11))
        if annotation:
            await journal.append(draft())
        await journal.append(_rx(provenance, b"SStrailing", 12))
        await journal.append(end)
        await journal.append(
            evidence.PendingObserverLossEvidence(
                provenance.connection_id,
                provenance.segment_id,
                "fixture",
                "uart",
                model.ObserverLossCause.OVERFLOW,
                3,
                model.BackendObservationTimestamp(
                    provenance.backend_observation_timestamp_domain.domain_id, 13
                ),
            )
        )
        await journal.append(
            evidence.PendingSegmentEndedEvidence(
                provenance.connection_id,
                provenance.segment_id,
                model.SegmentEndReason.EXPLICIT_STOP,
            )
        )
        return journal.session_id
    finally:
        await journal.close()


@pytest.mark.asyncio
async def test_explicit_v3_schema_and_annotation_cache_are_exact(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v3.db"
    journal = await create(path)
    try:
        accepted = await journal.append(draft())
        assert isinstance(accepted, model.ClientAnnotationEvidence)
        assert accepted.sequence == 0
        assert journal.physical_page_ceiling == _policy().max_database_pages
        session = journal.session_id
    finally:
        await journal.close()
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("PRAGMA user_version").fetchone() == (3,)
        assert conn.execute("PRAGMA application_id").fetchone() == (0x4455544D,)
        assert conn.execute("PRAGMA page_size").fetchone() == (4096,)
        assert conn.execute(
            "SELECT schema_version,session_id FROM session_metadata"
        ).fetchone() == (3, session.value)
        assert {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        } == {"session_metadata", "evidence_records", "retention_marker"}
        row = conn.execute(
            "SELECT record_version,rx_payload_bytes,timestamp_endpoint_json,payload FROM evidence_records"
        ).fetchone()
        assert row == (3, 0, None, draft().text.encode())


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.asyncio
async def test_old_writers_reject_annotation_without_mutation(
    tmp_path: Path, version: int
) -> None:
    path = tmp_path / "old.db"
    journal = await create(path, version)
    try:
        before = _database_state(path)
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(draft())
        assert caught.value.kind is evidence.JournalFailureKind.INVALID_INPUT
        assert _database_state(path) == before
    finally:
        await journal.close()


@pytest.mark.parametrize("stored", [1, 2, 3])
@pytest.mark.parametrize("expected", [1, 2, 3])
@pytest.mark.asyncio
async def test_explicit_factory_format_matrix_never_migrates(
    tmp_path: Path, stored: int, expected: int
) -> None:
    path = tmp_path / "format.db"
    journal = await create(path, stored)
    session = journal.session_id
    await journal.close()
    before = _files(path)
    if stored == expected:
        opened = await reopen(path, expected, session)
        await opened.close()
    else:
        with pytest.raises(evidence.JournalFailure) as caught:
            await reopen(path, expected, session)
        assert (
            caught.value.kind is evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION
        )
    assert _files(path) == before


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_annotations_between_rx_chunks_preserve_monitor_pair_reopen_and_retrieval(
    tmp_path: Path, index: int
) -> None:
    path = tmp_path / "mixed.db"
    session = await seed_match(path, index)
    journal = await reopen(path, 3, session)
    try:
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(session, 20, 20000)
        )
        assert len(page.records) == 8
        assert page.outcome is evidence.EvidencePageOutcome.COMPLETE
        annotation = page.records[3]
        assert isinstance(annotation, model.ClientAnnotationEvidence)
        assert annotation.text == draft().text
        ending = page.records[5]
        assert isinstance(ending, model.OperationEndedEvidence)
        assert ending.examined_rx_bytes == 11
        assert ending.match == model.MonitorMatch(
            model.MonitorMatchStart(2, 5), model.MonitorMatchEnd(4, 2)
        )
        assert (
            b"".join(
                r.payload for r in page.records if isinstance(r, model.RxBytesEvidence)
            )
            == b"noise\0\xffPASStrailing"
        )
        assert (
            await journal.resolve_record(model.EvidenceReference(session, 3))
        ).records == (annotation,)
    finally:
        await journal.close()


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.asyncio
async def test_legacy_rows_and_charges_are_identical_in_v3(
    tmp_path: Path, version: int
) -> None:
    old_path, new_path = tmp_path / "old.db", tmp_path / "new.db"
    if version == 2:
        await seed_match(old_path, 0, annotation=False, version=2)
        await seed_match(new_path, 0, annotation=False, version=3)
    else:
        for path, schema in ((old_path, 1), (new_path, 3)):
            journal = await create(path, schema)
            try:
                for item in _every_pending_variant():
                    await journal.append(item)
            finally:
                await journal.close()
    assert _rows(old_path) == _rows(new_path)


@pytest.mark.asyncio
async def test_annotation_rolling_retention_expiry_and_zero_rx_telemetry(
    tmp_path: Path,
) -> None:
    path = tmp_path / "retention.db"
    journal = await create(path, policy=_policy(max_retained_records=2))
    try:
        for i in range(4):
            await journal.append(replace(draft(), text=f"claim{i}"))
        session = journal.session_id
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(session, 20, 20000)
        )
        assert [r.sequence for r in page.records] == [2, 3]
        marker = page.retention_marker
        assert marker is not None
        assert marker.expired_range == model.SequenceRange(0, 2)
        assert marker.discarded_record_count == 2
        assert marker.discarded_rx_payload_byte_count == 0
        assert (
            marker.first_discarded_timestamp is marker.last_discarded_timestamp is None
        )
        assert (
            await journal.resolve_record(model.EvidenceReference(session, 0))
        ).outcome is evidence.EvidencePageOutcome.EXPIRED
        assert (
            await journal.resolve_record(model.EvidenceReference(session, 99))
        ).outcome is evidence.EvidencePageOutcome.NOT_FOUND
        empty = await journal.retrieve(evidence.EvidenceRetrievalRequest(session, 1, 1))
        assert (
            empty.records == () and empty.truncated and empty.continuation is not None
        )
        assert empty.next_record_required_bytes == sqlite.charge_client_annotation(
            replace(draft(), text="claim2")
        )
    finally:
        await journal.close()
    opened = await reopen(path, 3)
    await opened.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_mixed_retention_skips_host_annotations_in_backend_timestamp_scan(
    tmp_path: Path, index: int
) -> None:
    path = tmp_path / "timestamps.db"
    provenance = _provenance(index)
    journal = await create(path, policy=_policy(max_retained_records=3))
    try:
        for item in (
            evidence.PendingSegmentStartedEvidence(provenance),
            _rx(provenance, b"a", 11),
            draft(),
            _rx(provenance, b"b", 12),
            draft(),
            _rx(provenance, b"c", 13),
        ):
            await journal.append(item)
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(journal.session_id, 20, 20000)
        )
        marker = page.retention_marker
        assert marker is not None
        assert marker.discarded_rx_payload_byte_count == 1
        assert marker.first_discarded_timestamp is not None
        assert marker.first_discarded_timestamp.timestamp.value == 11
        assert marker.last_discarded_timestamp == marker.first_discarded_timestamp
    finally:
        await journal.close()
    opened = await reopen(path, 3)
    await opened.close()


@pytest.mark.asyncio
async def test_annotation_snapshot_cursor_does_not_expand_after_later_append(
    tmp_path: Path,
) -> None:
    journal = await create(tmp_path / "snapshot.db")
    try:
        for i in range(3):
            await journal.append(replace(draft(), text=str(i)))
        request = evidence.EvidenceRetrievalRequest(journal.session_id, 1, 20000)
        page = await journal.retrieve(request)
        assert page.snapshot_end_exclusive == 3 and page.continuation is not None
        await journal.append(replace(draft(), text="later"))
        seen = [*page.records]
        while page.continuation is not None:
            page = await journal.retrieve(replace(request, cursor=page.continuation))
            assert page.snapshot_end_exclusive == 3
            seen.extend(page.records)
        assert [r.sequence for r in seen] == [0, 1, 2]
    finally:
        await journal.close()


@pytest.mark.parametrize("adjustment", [-1, 0])
@pytest.mark.asyncio
async def test_annotation_record_charge_ceiling_has_no_silent_trimming_or_eviction(
    tmp_path: Path, adjustment: int
) -> None:
    charge = sqlite.charge_client_annotation(draft())
    path = tmp_path / "charge.db"
    journal = await create(
        path, policy=_policy(max_record_charged_bytes=charge + adjustment)
    )
    try:
        before = _database_state(path)
        if adjustment < 0:
            with pytest.raises(evidence.JournalFailure) as caught:
                await journal.append(draft())
            assert caught.value.kind is evidence.JournalFailureKind.CAPACITY
            assert _database_state(path) == before
        else:
            accepted = await journal.append(draft())
            assert isinstance(accepted, model.ClientAnnotationEvidence)
            assert accepted.text == draft().text
    finally:
        await journal.close()


@pytest.mark.parametrize(
    ("statement", "failure"),
    [
        (
            "UPDATE evidence_records SET record_version=2",
            evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION,
        ),
        (
            "UPDATE evidence_records SET record_kind='unknown'",
            evidence.JournalFailureKind.CORRUPT_JOURNAL,
        ),
        (
            "UPDATE evidence_records SET payload=x'ff'",
            evidence.JournalFailureKind.CORRUPT_JOURNAL,
        ),
        (
            "UPDATE evidence_records SET metadata_json=x'7b7d'",
            evidence.JournalFailureKind.CORRUPT_JOURNAL,
        ),
        (
            "CREATE INDEX unexpected ON evidence_records(record_kind)",
            evidence.JournalFailureKind.CORRUPT_JOURNAL,
        ),
        (
            "PRAGMA user_version=4",
            evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION,
        ),
    ],
)
@pytest.mark.asyncio
async def test_malformed_v3_artifacts_fail_closed_without_repair(
    tmp_path: Path, statement: str, failure: evidence.JournalFailureKind
) -> None:
    path = tmp_path / "malformed.db"
    journal = await create(path)
    await journal.append(draft())
    await journal.close()
    _sql(path, statement)
    before = _files(path)
    with pytest.raises(evidence.JournalFailure) as caught:
        await reopen(path, 3)
    assert caught.value.kind is failure
    assert _files(path) == before


@pytest.mark.asyncio
async def test_v3_retains_database_ceiling_and_annotation_sequence_exhaustion(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ceiling.db"
    journal = await create(path)
    maximum = model.SQLITE_INTEGER_MAX
    try:
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
            await journal.append(draft())
        assert caught.value.kind is evidence.JournalFailureKind.SEQUENCE_EXHAUSTED
        assert _database_state(path) == before
    finally:
        await journal.close()
    _sql(path, "UPDATE session_metadata SET max_database_pages=1")
    before_files = _files(path)
    with pytest.raises(evidence.JournalFailure) as caught:
        await reopen(path, 3)
    assert caught.value.kind is evidence.JournalFailureKind.DATABASE_OVER_CEILING
    assert _files(path) == before_files
