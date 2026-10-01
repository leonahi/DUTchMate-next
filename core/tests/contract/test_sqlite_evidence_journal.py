"""Create/open contracts for the SQLite evidence journal."""

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import cast

import pytest

from dutchmate_core import evidence, model
from dutchmate_core.adapters import sqlite_evidence


def _policy(
    *,
    max_database_pages: int = 64,
    max_retained_records: int = 100,
    max_retained_charged_bytes: int = 100_000,
    max_record_charged_bytes: int = 10_000,
    max_retrieval_page_records: int = 20,
    max_retrieval_page_charged_bytes: int = 20_000,
) -> model.SessionPolicy:
    return model.SessionPolicy(
        max_retained_records=max_retained_records,
        max_retained_charged_bytes=max_retained_charged_bytes,
        max_record_charged_bytes=max_record_charged_bytes,
        max_database_pages=max_database_pages,
        max_retrieval_page_records=max_retrieval_page_records,
        max_retrieval_page_charged_bytes=max_retrieval_page_charged_bytes,
    )


@pytest.mark.asyncio
async def test_create_persists_one_immutable_session_and_fixed_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.sqlite3"
    policy = _policy()

    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, policy)
    session_id = journal.session_id
    assert journal.policy == policy
    await journal.close()

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA application_id").fetchone() == (
            0x4455544D,
        )
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        assert tables == {
            "evidence_records",
            "retention_marker",
            "session_metadata",
        }
        row = connection.execute(
            """
            SELECT session_id, schema_version,
                   max_retained_records, max_retained_charged_bytes,
                   max_record_charged_bytes, max_database_pages,
                   max_retrieval_page_records,
                   max_retrieval_page_charged_bytes,
                   next_sequence, low_water_sequence,
                   retained_record_count, retained_charged_bytes
            FROM session_metadata
            """
        ).fetchone()
        assert row == (
            session_id.value,
            1,
            policy.max_retained_records,
            policy.max_retained_charged_bytes,
            policy.max_record_charged_bytes,
            policy.max_database_pages,
            policy.max_retrieval_page_records,
            policy.max_retrieval_page_charged_bytes,
            0,
            0,
            0,
            0,
        )
        assert connection.execute("SELECT COUNT(*) FROM session_metadata").fetchone() == (
            1,
        )
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_open_restores_persisted_identity_and_policy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.sqlite3"
    created = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    session_id = created.session_id
    policy = created.policy
    await created.close()

    opened = await sqlite_evidence.SqliteEvidenceJournal.open(
        path,
        expected_session_id=session_id,
    )

    assert opened.session_id == session_id
    assert opened.policy == policy
    assert opened.physical_page_ceiling == policy.max_database_pages
    await opened.close()


@pytest.mark.asyncio
async def test_create_and_open_report_exists_missing_and_session_mismatch(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.close()

    with pytest.raises(evidence.JournalFailure) as exists:
        await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    assert exists.value.kind is evidence.JournalFailureKind.JOURNAL_EXISTS

    with pytest.raises(evidence.JournalFailure) as missing:
        await sqlite_evidence.SqliteEvidenceJournal.open(tmp_path / "missing.sqlite3")
    assert missing.value.kind is evidence.JournalFailureKind.JOURNAL_MISSING

    with pytest.raises(evidence.JournalFailure) as mismatch:
        await sqlite_evidence.SqliteEvidenceJournal.open(
            path,
            expected_session_id=model.SessionId("different-session"),
        )
    assert mismatch.value.kind is evidence.JournalFailureKind.SESSION_MISMATCH


@pytest.mark.asyncio
async def test_open_rejects_a_database_already_over_its_persisted_ceiling(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.close()
    connection = sqlite3.connect(path)
    try:
        page_count = cast(
            "int",
            connection.execute("PRAGMA page_count").fetchone()[0],
        )
        assert page_count > 1
        connection.execute(
            "UPDATE session_metadata SET max_database_pages = 1 WHERE singleton = 1"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(evidence.JournalFailure) as caught:
        await sqlite_evidence.SqliteEvidenceJournal.open(path)

    assert caught.value.operation is evidence.JournalOperation.OPEN
    assert caught.value.kind is evidence.JournalFailureKind.DATABASE_OVER_CEILING


@pytest.mark.asyncio
async def test_create_reports_inability_to_establish_the_requested_ceiling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_requested_ceiling(
        connection: sqlite3.Connection,
        requested_pages: int,
    ) -> int:
        del connection
        return requested_pages + 1

    monkeypatch.setattr(
        sqlite_evidence,
        "_apply_max_page_count",
        refuse_requested_ceiling,
    )

    with pytest.raises(evidence.JournalFailure) as caught:
        await sqlite_evidence.SqliteEvidenceJournal.create(
            tmp_path / "journal.sqlite3",
            _policy(),
        )

    assert caught.value.operation is evidence.JournalOperation.CREATE
    assert caught.value.kind is (
        evidence.JournalFailureKind.PHYSICAL_CEILING_UNAVAILABLE
    )


class _ThreadRecordingConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        thread_ids: list[int],
        statements: list[str],
    ) -> None:
        self._connection = connection
        self._thread_ids = thread_ids
        self._statements = statements

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> sqlite3.Cursor:
        self._thread_ids.append(threading.get_ident())
        self._statements.append(sql)
        return self._connection.execute(sql, parameters)

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        self._thread_ids.append(threading.get_ident())
        self._statements.append(sql_script)
        return self._connection.executescript(sql_script)

    def commit(self) -> None:
        self._thread_ids.append(threading.get_ident())
        self._connection.commit()

    def rollback(self) -> None:
        self._thread_ids.append(threading.get_ident())
        self._connection.rollback()

    def close(self) -> None:
        self._thread_ids.append(threading.get_ident())
        self._connection.close()


@pytest.mark.asyncio
async def test_each_journal_creates_uses_and_closes_sqlite_on_one_worker_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_connect = sqlite3.connect
    thread_ids: list[int] = []
    statements: list[str] = []

    def recording_connect(
        database: str,
        *,
        uri: bool = False,
    ) -> sqlite3.Connection:
        thread_ids.append(threading.get_ident())
        connection = real_connect(database, uri=uri)
        return cast(
            "sqlite3.Connection",
            _ThreadRecordingConnection(connection, thread_ids, statements),
        )

    monkeypatch.setattr(sqlite_evidence, "_connect_sqlite", recording_connect)
    main_thread = threading.get_ident()
    path = tmp_path / "journal.sqlite3"

    created = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    assert isinstance(created._gate, asyncio.Lock)
    assert created._executor._max_workers == 1
    await created.close()
    assert len(set(thread_ids)) == 1
    assert thread_ids[0] != main_thread
    assert any("max_page_count" in statement for statement in statements)

    thread_ids.clear()
    statements.clear()
    opened = await sqlite_evidence.SqliteEvidenceJournal.open(path)
    await opened.close()
    assert len(set(thread_ids)) == 1
    assert thread_ids[0] != main_thread
    assert any("max_page_count" in statement for statement in statements)


def _segment_provenance(
    *,
    segment_id: str = "segment-1",
    domain_id: str = "host-domain",
    observer: model.TimestampObserver = model.TimestampObserver.HOST,
    unit: model.TimestampUnit = model.TimestampUnit.NANOSECOND,
    origin_id: str = "host-origin",
) -> model.SegmentProvenance:
    snapshot = model.ConnectionProvenanceSnapshot(
        envelope_version=1,
        backend_kind="contract-fixture",
        backend_schema_version=7,
        fields=(
            model.ProvenanceField("mode", "opaque"),
            model.ProvenanceField("verified", False),
        ),
    )
    return model.SegmentProvenance(
        connection_id=model.ConnectionInstanceId("connection-1"),
        segment_id=model.SegmentId(segment_id),
        capabilities=model.BackendCapabilities(
            frozenset({model.BackendCapability.UART_RECEIVE})
        ),
        backend_observation_timestamp_domain=model.BackendObservationTimestampDomain(
            domain_id=domain_id,
            observer=observer,
            meaning=model.TimestampMeaning.OBSERVATION,
            unit=unit,
            origin_id=origin_id,
        ),
        loss_observability=model.UpstreamLossNotObservable(),
        connection_provenance=model.PersistedConnectionProvenance(snapshot),
    )


def _rx_draft(payload: bytes = b"next") -> evidence.PendingRxBytesEvidence:
    return evidence.PendingRxBytesEvidence(
        connection_id=model.ConnectionInstanceId("connection-1"),
        segment_id=model.SegmentId("segment-1"),
        payload=payload,
        observed_at=model.BackendObservationTimestamp("host-domain", 42),
    )


def _rx_draft_at(
    payload: bytes,
    *,
    segment_id: str,
    domain_id: str,
    value: int,
) -> evidence.PendingRxBytesEvidence:
    return evidence.PendingRxBytesEvidence(
        connection_id=model.ConnectionInstanceId("connection-1"),
        segment_id=model.SegmentId(segment_id),
        payload=payload,
        observed_at=model.BackendObservationTimestamp(domain_id, value),
    )


def _segment_end_draft(
    segment_id: str = "segment-1",
) -> evidence.PendingSegmentEndedEvidence:
    return evidence.PendingSegmentEndedEvidence(
        connection_id=model.ConnectionInstanceId("connection-1"),
        segment_id=model.SegmentId(segment_id),
        reason=model.SegmentEndReason.EXPLICIT_STOP,
    )


def _rx_charge(payload: bytes) -> int:
    return sqlite_evidence.encode_evidence_record(
        model.RxBytesEvidence(
            sequence=0,
            connection_id=model.ConnectionInstanceId("connection-1"),
            segment_id=model.SegmentId("segment-1"),
            payload=payload,
            observed_at=model.BackendObservationTimestamp("host-domain", 42),
        )
    ).charged_bytes


def _segment_end_charge(segment_id: str = "segment-1") -> int:
    return sqlite_evidence.encode_evidence_record(
        model.SegmentEndedEvidence(
            sequence=0,
            connection_id=model.ConnectionInstanceId("connection-1"),
            segment_id=model.SegmentId(segment_id),
            reason=model.SegmentEndReason.EXPLICIT_STOP,
        )
    ).charged_bytes


def _every_pending_variant() -> tuple[evidence.PendingEvidenceRecord, ...]:
    return (
        evidence.PendingSegmentStartedEvidence(_segment_provenance()),
        _rx_draft(bytes(range(256))),
        evidence.PendingObserverLossEvidence(
            connection_id=model.ConnectionInstanceId("connection-1"),
            segment_id=model.SegmentId("segment-1"),
            observer_id="observer-1",
            scope="uart-buffer",
            cause=model.ObserverLossCause.OVERFLOW,
            lost_bytes=17,
            observed_at=model.BackendObservationTimestamp("host-domain", 43),
        ),
        evidence.PendingSegmentEndedEvidence(
            connection_id=model.ConnectionInstanceId("connection-1"),
            segment_id=model.SegmentId("segment-1"),
            reason=model.SegmentEndReason.DISCONNECTED,
        ),
    )


def _read_durable_records(path: Path) -> tuple[model.EvidenceRecord, ...]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            """
            SELECT sequence, record_kind, record_version, metadata_json,
                   payload, charged_bytes, rx_payload_bytes
            FROM evidence_records ORDER BY sequence
            """
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        sqlite_evidence.decode_evidence_record(
            sqlite_evidence.EncodedEvidenceRecord(
                sequence=cast("int", row[0]),
                record_kind=cast("str", row[1]),
                record_version=cast("int", row[2]),
                metadata_json=cast("bytes", row[3]),
                payload=cast("bytes | None", row[4]),
                charged_bytes=cast("int", row[5]),
                rx_payload_bytes=cast("int", row[6]),
            )
        )
        for row in rows
    )


def _database_state(path: Path) -> tuple[object, ...]:
    connection = sqlite3.connect(path)
    try:
        session = connection.execute(
            """
            SELECT next_sequence, low_water_sequence,
                   retained_record_count, retained_charged_bytes
            FROM session_metadata WHERE singleton = 1
            """
        ).fetchone()
        records = connection.execute(
            """
            SELECT sequence, record_kind, record_version, metadata_json,
                   payload, charged_bytes, rx_payload_bytes
            FROM evidence_records ORDER BY sequence
            """
        ).fetchall()
        marker = connection.execute(
            "SELECT * FROM retention_marker ORDER BY singleton"
        ).fetchall()
        return (session, tuple(records), tuple(marker))
    finally:
        connection.close()


async def _assert_open_failure_preserves_source(
    path: Path,
    expected_kind: evidence.JournalFailureKind,
) -> None:
    before = path.read_bytes()

    with pytest.raises(evidence.JournalFailure) as caught:
        await sqlite_evidence.SqliteEvidenceJournal.open(path)

    assert path.read_bytes() == before
    assert caught.value.operation is evidence.JournalOperation.OPEN
    assert caught.value.kind is expected_kind
    assert not isinstance(caught.value.__cause__, (sqlite3.Error, OSError))


async def _create_closed_journal_with_record(
    path: Path,
    draft: evidence.PendingEvidenceRecord,
) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.append(draft)
    await journal.close()


class _FailedQuickCheckConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> sqlite3.Cursor:
        if sql.strip().casefold() == "pragma quick_check":
            return self._connection.execute("SELECT 'integrity failure'")
        return self._connection.execute(sql, parameters)

    def close(self) -> None:
        self._connection.close()


def _retention_state(
    path: Path,
) -> tuple[tuple[int, int, int, int], tuple[int, ...]]:
    connection = sqlite3.connect(path)
    try:
        session = connection.execute(
            """
            SELECT next_sequence, low_water_sequence,
                   retained_record_count, retained_charged_bytes
            FROM session_metadata WHERE singleton = 1
            """
        ).fetchone()
        assert session is not None
        sequences = tuple(
            cast("int", row[0])
            for row in connection.execute(
                "SELECT sequence FROM evidence_records ORDER BY sequence"
            )
        )
        return cast("tuple[int, int, int, int]", session), sequences
    finally:
        connection.close()


def _retention_marker_rows(path: Path) -> tuple[tuple[object, ...], ...]:
    connection = sqlite3.connect(path)
    try:
        return tuple(
            connection.execute(
                """
                SELECT singleton, expired_start_sequence,
                       expired_end_sequence, first_timestamp_json,
                       last_timestamp_json, discarded_record_count,
                       discarded_rx_payload_byte_count,
                       discarded_charged_bytes
                FROM retention_marker ORDER BY singleton
                """
            ).fetchall()
        )
    finally:
        connection.close()


def _decode_json_blob(value: object) -> object:
    assert isinstance(value, bytes)
    return cast("object", json.loads(value.decode("utf-8")))


async def _journal_with_expired_prefix(
    path: Path,
) -> tuple[
    sqlite_evidence.SqliteEvidenceJournal,
    tuple[model.EvidenceRecord, ...],
]:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(max_retained_records=2),
    )
    accepted = tuple(
        [
            await journal.append(_rx_draft(payload))
            for payload in (b"zero", b"one", b"two", b"three")
        ]
    )
    return journal, accepted


def _retrieval_request(
    reference: model.EvidenceRangeReference,
) -> evidence.EvidenceRetrievalRequest:
    return evidence.EvidenceRetrievalRequest(
        reference=reference,
        max_records=20,
        max_charged_bytes=20_000,
    )


class _BlockingCommitConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self.commit_started = threading.Event()
        self.release_commit = threading.Event()
        self._block_next_commit = False

    def arm_next_commit(self) -> None:
        self.commit_started.clear()
        self.release_commit.clear()
        self._block_next_commit = True

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> sqlite3.Cursor:
        if sql.strip().upper() == "COMMIT":
            self._wait_if_armed()
        return self._connection.execute(sql, parameters)

    def commit(self) -> None:
        self._wait_if_armed()
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)

    def _wait_if_armed(self) -> None:
        if not self._block_next_commit:
            return
        self._block_next_commit = False
        self.commit_started.set()
        if not self.release_commit.wait(timeout=5):
            raise TimeoutError("test did not release the blocked commit")


async def _wait_for_thread_event(event: threading.Event) -> None:
    observed = await asyncio.wait_for(asyncio.to_thread(event.wait, 1), timeout=2)
    assert observed


def _install_blocking_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> list[_BlockingCommitConnection]:
    real_connect = sqlite3.connect
    connections: list[_BlockingCommitConnection] = []

    def blocking_connect(
        database: str,
        *,
        uri: bool = False,
    ) -> sqlite3.Connection:
        wrapped = _BlockingCommitConnection(real_connect(database, uri=uri))
        connections.append(wrapped)
        return cast("sqlite3.Connection", wrapped)

    monkeypatch.setattr(sqlite_evidence, "_connect_sqlite", blocking_connect)
    return connections


class _SqliteFullError(sqlite3.OperationalError):
    sqlite_errorcode = sqlite3.SQLITE_FULL


class _FullOnRecordInsertConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._fail_next_record_insert = False

    def arm_next_record_insert(self) -> None:
        self._fail_next_record_insert = True

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> sqlite3.Cursor:
        normalized = " ".join(sql.split()).casefold()
        if self._fail_next_record_insert and normalized.startswith(
            "insert into evidence_records"
        ):
            self._fail_next_record_insert = False
            raise _SqliteFullError("simulated database full")
        return self._connection.execute(sql, parameters)

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)


def _install_full_on_record_insert_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> list[_FullOnRecordInsertConnection]:
    real_connect = sqlite3.connect
    connections: list[_FullOnRecordInsertConnection] = []

    def full_connect(
        database: str,
        *,
        uri: bool = False,
    ) -> sqlite3.Connection:
        wrapped = _FullOnRecordInsertConnection(real_connect(database, uri=uri))
        connections.append(wrapped)
        return cast("sqlite3.Connection", wrapped)

    monkeypatch.setattr(sqlite_evidence, "_connect_sqlite", full_connect)
    return connections


class _BlockingRetrievalConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self.retrieval_started = threading.Event()
        self.release_retrieval = threading.Event()
        self._block_next_retrieval = False

    def arm_next_retrieval(self) -> None:
        self.retrieval_started.clear()
        self.release_retrieval.clear()
        self._block_next_retrieval = True

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> sqlite3.Cursor:
        normalized = " ".join(sql.split()).casefold()
        if (
            self._block_next_retrieval
            and normalized.startswith("select sequence")
            and "from evidence_records" in normalized
        ):
            self._block_next_retrieval = False
            self.retrieval_started.set()
            if not self.release_retrieval.wait(timeout=5):
                raise TimeoutError("test did not release the blocked retrieval")
        return self._connection.execute(sql, parameters)

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)


def _install_blocking_retrieval_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> list[_BlockingRetrievalConnection]:
    real_connect = sqlite3.connect
    connections: list[_BlockingRetrievalConnection] = []

    def blocking_connect(
        database: str,
        *,
        uri: bool = False,
    ) -> sqlite3.Connection:
        wrapped = _BlockingRetrievalConnection(real_connect(database, uri=uri))
        connections.append(wrapped)
        return cast("sqlite3.Connection", wrapped)

    monkeypatch.setattr(sqlite_evidence, "_connect_sqlite", blocking_connect)
    return connections


class _CloseTrackingConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        close_thread_ids: list[int],
    ) -> None:
        self._connection = connection
        self._close_thread_ids = close_thread_ids
        self.closed = False

    def close(self) -> None:
        self._close_thread_ids.append(threading.get_ident())
        self.closed = True
        self._connection.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)


@pytest.mark.parametrize("operation", ("create", "open"))
@pytest.mark.asyncio
async def test_cancelled_bootstrap_closes_connection_on_its_worker_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    path = tmp_path / f"cancelled-{operation}.sqlite3"
    if operation == "open":
        seeded = await sqlite_evidence.SqliteEvidenceJournal.create(
            path,
            _policy(),
        )
        await seeded.close()

    worker_ready = threading.Event()
    release_worker = threading.Event()
    worker_thread_ids: list[int] = []
    close_thread_ids: list[int] = []
    connections: list[_CloseTrackingConnection] = []

    def tracking_connect(
        database: str,
        *,
        uri: bool = False,
    ) -> sqlite3.Connection:
        wrapped = _CloseTrackingConnection(
            sqlite3.connect(database, uri=uri, check_same_thread=False),
            close_thread_ids,
        )
        connections.append(wrapped)
        return cast("sqlite3.Connection", wrapped)

    def hold_result[
        T: tuple[sqlite3.Connection, model.SessionId, model.SessionPolicy, int]
    ](result: T) -> T:
        worker_thread_ids.append(threading.get_ident())
        worker_ready.set()
        if not release_worker.wait(timeout=5):
            raise TimeoutError("test did not release the bootstrap worker")
        return result

    real_create = sqlite_evidence._create_on_worker
    real_open = sqlite_evidence._open_on_worker

    def blocking_create(
        journal_path: Path,
        policy: model.SessionPolicy,
    ) -> tuple[sqlite3.Connection, model.SessionId, model.SessionPolicy, int]:
        return hold_result(real_create(journal_path, policy))

    def blocking_open(
        journal_path: Path,
        expected_session_id: model.SessionId | None,
    ) -> tuple[sqlite3.Connection, model.SessionId, model.SessionPolicy, int]:
        return hold_result(real_open(journal_path, expected_session_id))

    monkeypatch.setattr(sqlite_evidence, "_connect_sqlite", tracking_connect)
    if operation == "create":
        monkeypatch.setattr(sqlite_evidence, "_create_on_worker", blocking_create)
        bootstrap = asyncio.create_task(
            sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
        )
    else:
        monkeypatch.setattr(sqlite_evidence, "_open_on_worker", blocking_open)
        bootstrap = asyncio.create_task(
            sqlite_evidence.SqliteEvidenceJournal.open(path)
        )

    try:
        await _wait_for_thread_event(worker_ready)
        bootstrap.cancel()
        release_worker.set()
        with pytest.raises(asyncio.CancelledError):
            await bootstrap

        assert close_thread_ids == worker_thread_ids
        assert len(close_thread_ids) == 1
    finally:
        release_worker.set()
        for connection in connections:
            if not connection.closed:
                connection.close()


@pytest.mark.asyncio
async def test_append_durably_records_every_variant_with_authoritative_sequences(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    try:
        accepted = tuple(
            [await journal.append(draft) for draft in _every_pending_variant()]
        )
    finally:
        await journal.close()

    assert [record.sequence for record in accepted] == [0, 1, 2, 3]
    assert isinstance(accepted[1], model.RxBytesEvidence)
    assert accepted[1].payload == bytes(range(256))
    assert _read_durable_records(path) == accepted
    connection = sqlite3.connect(path)
    try:
        stored_rx_blob = connection.execute(
            "SELECT payload FROM evidence_records WHERE sequence = 1"
        ).fetchone()
    finally:
        connection.close()
    assert stored_rx_blob == (bytes(range(256)),)


@pytest.mark.asyncio
async def test_reopen_continues_the_durable_sequence_without_reuse(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    try:
        first = await journal.append(_rx_draft(b"first"))
        second = await journal.append(_rx_draft(b"second"))
    finally:
        await journal.close()

    reopened = await sqlite_evidence.SqliteEvidenceJournal.open(path)
    try:
        third = await reopened.append(_rx_draft(b"third"))
    finally:
        await reopened.close()

    assert (first.sequence, second.sequence, third.sequence) == (0, 1, 2)


@pytest.mark.asyncio
async def test_append_returns_only_after_its_commit_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections = _install_blocking_connection(monkeypatch)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "journal.sqlite3",
        _policy(),
    )
    blocker = connections[0]
    blocker.arm_next_commit()
    try:
        append_task = asyncio.create_task(journal.append(_rx_draft()))
        await _wait_for_thread_event(blocker.commit_started)
        returned_before_commit = append_task.done()
        blocker.release_commit.set()
        accepted = await append_task
    finally:
        blocker.release_commit.set()
        await journal.close()

    assert not returned_before_commit
    assert accepted.sequence == 0


@pytest.mark.asyncio
async def test_sequence_exhaustion_is_rejected_before_insertion(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            UPDATE session_metadata
            SET next_sequence = ?
            WHERE singleton = 1
            """,
            (model.SQLITE_INTEGER_MAX,),
        )
        connection.commit()
    finally:
        connection.close()
    before = _database_state(path)

    try:
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(_rx_draft())
    finally:
        await journal.close()

    assert caught.value.operation is evidence.JournalOperation.APPEND
    assert caught.value.kind is evidence.JournalFailureKind.SEQUENCE_EXHAUSTED
    assert _database_state(path) == before


@pytest.mark.asyncio
async def test_counter_exhaustion_is_rejected_before_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(max_retained_charged_bytes=model.SQLITE_INTEGER_MAX),
    )
    try:
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                """
                UPDATE session_metadata
                SET retained_charged_bytes = ?
                WHERE singleton = 1
                """,
                (model.SQLITE_INTEGER_MAX,),
            )
            connection.commit()
        finally:
            connection.close()
        before = _database_state(path)

        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(_rx_draft(b"overflows-counter"))
    finally:
        await journal.close()

    assert caught.value.operation is evidence.JournalOperation.APPEND
    assert caught.value.kind is evidence.JournalFailureKind.COUNTER_EXHAUSTED
    assert _database_state(path) == before


@pytest.mark.asyncio
async def test_cancelled_append_holds_serialization_until_its_worker_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections = _install_blocking_connection(monkeypatch)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "journal.sqlite3",
        _policy(),
    )
    blocker = connections[0]
    blocker.arm_next_commit()
    try:
        cancelled_append = asyncio.create_task(journal.append(_rx_draft(b"first")))
        await _wait_for_thread_event(blocker.commit_started)
        cancelled_append.cancel()
        following_append = asyncio.create_task(journal.append(_rx_draft(b"second")))
        await asyncio.sleep(0)
        cancellation_returned_while_blocked = cancelled_append.done()
        following_started_while_blocked = following_append.done()
        blocker.release_commit.set()
        with pytest.raises(asyncio.CancelledError):
            await cancelled_append
        following = await following_append
    finally:
        blocker.release_commit.set()
        await journal.close()

    assert not cancellation_returned_while_blocked
    assert not following_started_while_blocked
    assert following.sequence == 1


@pytest.mark.asyncio
async def test_cancelled_caller_gets_no_record_and_reopen_exposes_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections = _install_blocking_connection(monkeypatch)
    path = tmp_path / "journal.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    blocker = connections[0]
    blocker.arm_next_commit()
    try:
        append_task = asyncio.create_task(journal.append(_rx_draft(b"ambiguous")))
        await _wait_for_thread_event(blocker.commit_started)
        append_task.cancel()
        blocker.release_commit.set()
        with pytest.raises(asyncio.CancelledError):
            await append_task
    finally:
        blocker.release_commit.set()
        await journal.close()

    reopened = await sqlite_evidence.SqliteEvidenceJournal.open(path)
    try:
        next_record = await reopened.append(_rx_draft(b"after-reopen"))
    finally:
        await reopened.close()

    assert next_record.sequence == 1


@pytest.mark.asyncio
async def test_close_waits_for_an_admitted_append_to_finish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections = _install_blocking_connection(monkeypatch)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "journal.sqlite3",
        _policy(),
    )
    blocker = connections[0]
    blocker.arm_next_commit()
    try:
        append_task = asyncio.create_task(journal.append(_rx_draft()))
        await _wait_for_thread_event(blocker.commit_started)
        close_task = asyncio.create_task(journal.close())
        await asyncio.sleep(0)
        close_returned_while_append_blocked = close_task.done()
        blocker.release_commit.set()
        accepted = await append_task
        await close_task
    finally:
        blocker.release_commit.set()
        await journal.close()

    assert not close_returned_while_append_blocked
    assert accepted.sequence == 0


@pytest.mark.asyncio
async def test_close_is_idempotent(tmp_path: Path) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "journal.sqlite3",
        _policy(),
    )

    await journal.close()
    await journal.close()


@pytest.mark.asyncio
async def test_append_after_close_is_rejected_with_a_normalized_failure(
    tmp_path: Path,
) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "journal.sqlite3",
        _policy(),
    )
    await journal.close()

    with pytest.raises(evidence.JournalFailure) as caught:
        await journal.append(_rx_draft())

    assert caught.value.operation is evidence.JournalOperation.APPEND
    assert caught.value.kind is evidence.JournalFailureKind.CLOSED


@pytest.mark.asyncio
async def test_locked_append_is_normalized_and_preserves_prior_durable_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    locker: sqlite3.Connection | None = None
    try:
        first = await journal.append(_rx_draft(b"first"))
        locker = sqlite3.connect(path)
        locker.execute("BEGIN IMMEDIATE")
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(_rx_draft(b"blocked"))
        assert not isinstance(caught.value.__cause__, sqlite3.Error)
        assert caught.value.operation is evidence.JournalOperation.APPEND
        assert caught.value.kind is evidence.JournalFailureKind.BUSY
        locker.rollback()
        locker.close()
        locker = None
        second = await journal.append(_rx_draft(b"second"))
    finally:
        if locker is not None:
            locker.rollback()
            locker.close()
        await journal.close()

    assert first.sequence == 0
    assert second.sequence == 1
    assert tuple(record.sequence for record in _read_durable_records(path)) == (0, 1)


@pytest.mark.asyncio
async def test_record_count_retention_discards_only_the_oldest_prefix(
    tmp_path: Path,
) -> None:
    path = tmp_path / "count-retention.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(max_retained_records=2),
    )
    try:
        accepted = [
            await journal.append(_rx_draft(payload))
            for payload in (b"zero", b"one", b"two", b"three")
        ]
    finally:
        await journal.close()

    session, retained_sequences = _retention_state(path)
    assert [record.sequence for record in accepted] == [0, 1, 2, 3]
    assert session[:3] == (4, 2, 2)
    assert retained_sequences == (2, 3)


@pytest.mark.asyncio
async def test_charged_byte_retention_selects_the_minimum_oldest_prefix(
    tmp_path: Path,
) -> None:
    path = tmp_path / "byte-retention.sqlite3"
    payloads = (b"a", b"b", b"c" * 2_000, b"d" * 2_000)
    charges = tuple(_rx_charge(payload) for payload in payloads)
    retained_byte_limit = charges[2] + charges[3]
    assert sum(charges[:3]) <= retained_byte_limit
    assert sum(charges[1:]) > retained_byte_limit
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(
            max_retained_charged_bytes=retained_byte_limit,
            max_record_charged_bytes=max(charges),
            max_retrieval_page_charged_bytes=max(charges),
        ),
    )
    try:
        for payload in payloads:
            await journal.append(_rx_draft(payload))
    finally:
        await journal.close()

    session, retained_sequences = _retention_state(path)
    assert session == (4, 2, 2, retained_byte_limit)
    assert retained_sequences == (2, 3)


@pytest.mark.asyncio
async def test_retention_never_reuses_discarded_sequences_after_reopen(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sequence-retention.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(max_retained_records=2),
    )
    try:
        first_sequences = tuple(
            [
                (await journal.append(_rx_draft(payload))).sequence
                for payload in (b"zero", b"one", b"two")
            ]
        )
    finally:
        await journal.close()

    reopened = await sqlite_evidence.SqliteEvidenceJournal.open(path)
    try:
        after_reopen = await reopened.append(_rx_draft(b"three"))
    finally:
        await reopened.close()

    session, retained_sequences = _retention_state(path)
    assert first_sequences == (0, 1, 2)
    assert after_reopen.sequence == 3
    assert session[:3] == (4, 2, 2)
    assert retained_sequences == (2, 3)


@pytest.mark.asyncio
async def test_append_and_retention_become_visible_as_one_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections = _install_blocking_connection(monkeypatch)
    path = tmp_path / "atomic-retention.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(max_retained_records=2),
    )
    await journal.append(_rx_draft(b"zero"))
    await journal.append(_rx_draft(b"one"))
    blocker = connections[0]
    before = _retention_state(path)
    blocker.arm_next_commit()
    try:
        append_task = asyncio.create_task(journal.append(_rx_draft(b"two")))
        await _wait_for_thread_event(blocker.commit_started)
        while_commit_is_blocked = _retention_state(path)
        blocker.release_commit.set()
        accepted = await append_task
    finally:
        blocker.release_commit.set()
        await journal.close()

    assert before[0][:3] == (2, 0, 2)
    assert before[1] == (0, 1)
    assert while_commit_is_blocked == before
    assert accepted.sequence == 2
    final_session, final_sequences = _retention_state(path)
    assert final_session[:3] == (3, 1, 2)
    assert final_sequences == (1, 2)


@pytest.mark.asyncio
async def test_open_reapplies_persisted_policy_over_effective_page_ceiling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "persisted-ceiling.sqlite3"
    policy = _policy(max_database_pages=64)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, policy)
    await journal.close()
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA max_page_count = 96").fetchone() == (96,)
        assert connection.execute(
            """
            SELECT max_database_pages
            FROM session_metadata WHERE singleton = 1
            """
        ).fetchone() == (64,)
    finally:
        connection.close()

    applied_ceilings: list[tuple[int, int]] = []
    real_apply_max_page_count = sqlite_evidence._apply_max_page_count

    def record_applied_ceiling(
        connection: sqlite3.Connection,
        requested_pages: int,
    ) -> int:
        effective_pages = real_apply_max_page_count(connection, requested_pages)
        applied_ceilings.append((requested_pages, effective_pages))
        return effective_pages

    monkeypatch.setattr(
        sqlite_evidence,
        "_apply_max_page_count",
        record_applied_ceiling,
    )

    reopened = await sqlite_evidence.SqliteEvidenceJournal.open(path)
    try:
        assert reopened.policy.max_database_pages == 64
        assert reopened.physical_page_ceiling == 64
    finally:
        await reopened.close()

    assert applied_ceilings == [(64, 64)]


@pytest.mark.asyncio
async def test_append_rejects_page_count_already_over_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy(max_database_pages=64)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "over-ceiling.sqlite3",
        policy,
    )
    real_pragma_integer = sqlite_evidence._pragma_integer

    def report_oversized_database(
        connection: sqlite3.Connection,
        name: str,
    ) -> int:
        if name == "page_count":
            return policy.max_database_pages + 1
        return real_pragma_integer(connection, name)

    monkeypatch.setattr(
        sqlite_evidence,
        "_pragma_integer",
        report_oversized_database,
    )
    try:
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(_rx_draft())
    finally:
        await journal.close()

    assert caught.value.operation is evidence.JournalOperation.APPEND
    assert caught.value.kind is evidence.JournalFailureKind.DATABASE_OVER_CEILING


@pytest.mark.asyncio
async def test_append_rejects_unavailable_effective_max_page_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy(max_database_pages=64)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "unavailable-ceiling.sqlite3",
        policy,
    )

    def refuse_requested_ceiling(
        connection: sqlite3.Connection,
        requested_pages: int,
    ) -> int:
        del connection
        return requested_pages + 1

    monkeypatch.setattr(
        sqlite_evidence,
        "_apply_max_page_count",
        refuse_requested_ceiling,
    )
    try:
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(_rx_draft())
    finally:
        await journal.close()

    assert caught.value.operation is evidence.JournalOperation.APPEND
    assert caught.value.kind is (
        evidence.JournalFailureKind.PHYSICAL_CEILING_UNAVAILABLE
    )


@pytest.mark.asyncio
async def test_retention_marker_stays_one_row_across_one_thousand_passes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "coalesced-marker.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(max_retained_records=1),
    )
    try:
        for _ in range(1_001):
            await journal.append(_segment_end_draft())
    finally:
        await journal.close()

    assert _retention_marker_rows(path) == (
        (
            1,
            0,
            1_000,
            None,
            None,
            1_000,
            0,
            1_000 * _segment_end_charge(),
        ),
    )


@pytest.mark.asyncio
async def test_retention_marker_accumulates_exact_rx_and_charged_byte_counts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "marker-counters.sqlite3"
    payloads = (b"a", b"bc", b"def")
    charges = tuple(_rx_charge(payload) for payload in payloads)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(max_retained_records=1),
    )
    try:
        for payload in payloads:
            await journal.append(_rx_draft(payload))
    finally:
        await journal.close()

    rows = _retention_marker_rows(path)
    assert len(rows) == 1
    marker = rows[0]
    assert marker[:3] == (1, 0, 2)
    assert marker[5:] == (2, 3, charges[0] + charges[1])


@pytest.mark.asyncio
async def test_retention_marker_has_no_redundant_discard_high_water_column(
    tmp_path: Path,
) -> None:
    path = tmp_path / "marker-schema.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.close()

    connection = sqlite3.connect(path)
    try:
        columns = tuple(
            cast("str", row[1])
            for row in connection.execute("PRAGMA table_info(retention_marker)")
        )
    finally:
        connection.close()

    assert columns == (
        "singleton",
        "expired_start_sequence",
        "expired_end_sequence",
        "first_timestamp_json",
        "last_timestamp_json",
        "discarded_record_count",
        "discarded_rx_payload_byte_count",
        "discarded_charged_bytes",
    )


@pytest.mark.asyncio
async def test_retention_marker_keeps_incomparable_timestamp_endpoints_separate(
    tmp_path: Path,
) -> None:
    path = tmp_path / "marker-endpoints.sqlite3"
    host_provenance = _segment_provenance(
        segment_id="host-segment",
        domain_id="host-domain",
        observer=model.TimestampObserver.HOST,
        unit=model.TimestampUnit.NANOSECOND,
        origin_id="host-origin",
    )
    device_provenance = _segment_provenance(
        segment_id="device-segment",
        domain_id="device-domain",
        observer=model.TimestampObserver.DEVICE,
        unit=model.TimestampUnit.TICK,
        origin_id="device-origin",
    )
    drafts: tuple[evidence.PendingEvidenceRecord, ...] = (
        evidence.PendingSegmentStartedEvidence(host_provenance),
        _rx_draft_at(
            b"host",
            segment_id="host-segment",
            domain_id="host-domain",
            value=900,
        ),
        _segment_end_draft("host-segment"),
        evidence.PendingSegmentStartedEvidence(device_provenance),
        _rx_draft_at(
            b"device",
            segment_id="device-segment",
            domain_id="device-domain",
            value=2,
        ),
        _segment_end_draft("device-segment"),
    )
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(max_retained_records=1),
    )
    try:
        for draft in drafts:
            await journal.append(draft)
    finally:
        await journal.close()

    rows = _retention_marker_rows(path)
    assert len(rows) == 1
    marker = rows[0]
    assert marker[1:3] == (0, 5)
    assert _decode_json_blob(marker[3]) == {
        "domain": {
            "domain_id": "host-domain",
            "meaning": "observation",
            "observer": "host",
            "origin_id": "host-origin",
            "unit": "nanosecond",
        },
        "timestamp": {"domain_id": "host-domain", "value": 900},
    }
    assert _decode_json_blob(marker[4]) == {
        "domain": {
            "domain_id": "device-domain",
            "meaning": "observation",
            "observer": "device",
            "origin_id": "device-origin",
            "unit": "tick",
        },
        "timestamp": {"domain_id": "device-domain", "value": 2},
    }


@pytest.mark.asyncio
async def test_individually_oversized_record_preserves_prior_retention_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "oversized-record.sqlite3"
    small_payload = b"x"
    max_record_charge = _rx_charge(small_payload)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(
            max_retained_records=2,
            max_retained_charged_bytes=max_record_charge * 3,
            max_record_charged_bytes=max_record_charge,
            max_retrieval_page_charged_bytes=max_record_charge,
        ),
    )
    try:
        for _ in range(3):
            await journal.append(_rx_draft(small_payload))
        before = _database_state(path)

        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(_rx_draft(b"oversized" * 200))
    finally:
        await journal.close()

    assert caught.value.operation is evidence.JournalOperation.APPEND
    assert caught.value.kind is evidence.JournalFailureKind.CAPACITY
    assert _retention_state(path)[0][:3] == (3, 1, 2)
    assert len(_retention_marker_rows(path)) == 1
    assert _database_state(path) == before


@pytest.mark.asyncio
async def test_cumulative_retention_counter_exhaustion_preserves_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "retention-counter-exhaustion.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(max_retained_records=1),
    )
    try:
        await journal.append(_rx_draft(b"first"))
        await journal.append(_rx_draft(b"second"))
        connection = sqlite3.connect(path)
        try:
            updated = connection.execute(
                """
                UPDATE retention_marker
                SET discarded_charged_bytes = ?
                WHERE singleton = 1
                """,
                (model.SQLITE_INTEGER_MAX,),
            )
            connection.commit()
        finally:
            connection.close()
        assert updated.rowcount == 1
        before = _database_state(path)

        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(_rx_draft(b"third"))
    finally:
        await journal.close()

    assert caught.value.operation is evidence.JournalOperation.APPEND
    assert caught.value.kind is evidence.JournalFailureKind.COUNTER_EXHAUSTED
    assert _database_state(path) == before


@pytest.mark.asyncio
async def test_sqlite_full_after_retention_rolls_back_the_whole_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections = _install_full_on_record_insert_connection(monkeypatch)
    path = tmp_path / "full-rollback.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(max_retained_records=2),
    )
    try:
        for payload in (b"zero", b"one", b"two"):
            await journal.append(_rx_draft(payload))
        before = _database_state(path)
        before_retention = _retention_state(path)
        before_marker = _retention_marker_rows(path)
        connections[0].arm_next_record_insert()

        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.append(_rx_draft(b"full"))
    finally:
        await journal.close()

    assert caught.value.operation is evidence.JournalOperation.APPEND
    assert caught.value.kind is evidence.JournalFailureKind.CAPACITY
    assert not isinstance(caught.value.__cause__, sqlite3.Error)
    assert before_retention[0][:3] == (3, 1, 2)
    assert before_retention[1] == (1, 2)
    assert len(before_marker) == 1
    assert _database_state(path) == before


@pytest.mark.asyncio
async def test_retained_record_reference_resolves_to_the_exact_record(
    tmp_path: Path,
) -> None:
    journal, accepted = await _journal_with_expired_prefix(
        tmp_path / "retained-reference.sqlite3"
    )
    reference = model.EvidenceReference(journal.session_id, 2)
    try:
        result = await journal.resolve_record(reference)
    finally:
        await journal.close()

    assert result.outcome is evidence.EvidencePageOutcome.COMPLETE
    assert result.records == (accepted[2],)
    assert result.expired_range is None
    assert result.retention_marker is None
    assert result.never_existed_range is None


@pytest.mark.asyncio
async def test_expired_record_reference_returns_the_current_marker(
    tmp_path: Path,
) -> None:
    journal, _ = await _journal_with_expired_prefix(
        tmp_path / "expired-reference.sqlite3"
    )
    reference = model.EvidenceReference(journal.session_id, 1)
    try:
        result = await journal.resolve_record(reference)
    finally:
        await journal.close()

    assert result.outcome is evidence.EvidencePageOutcome.EXPIRED
    assert result.records == ()
    assert result.expired_range == model.SequenceRange(1, 2)
    assert result.retention_marker is not None
    assert result.retention_marker.expired_range == model.SequenceRange(0, 2)
    assert result.never_existed_range is None


@pytest.mark.asyncio
async def test_wholly_expired_range_reports_no_retained_records(
    tmp_path: Path,
) -> None:
    journal, _ = await _journal_with_expired_prefix(
        tmp_path / "expired-range.sqlite3"
    )
    reference = model.EvidenceRangeReference(journal.session_id, 0, 2)
    try:
        result = await journal.retrieve(_retrieval_request(reference))
    finally:
        await journal.close()

    assert result.outcome is evidence.EvidencePageOutcome.EXPIRED
    assert result.records == ()
    assert result.expired_range == model.SequenceRange(0, 2)
    assert result.retention_marker is not None
    assert result.retention_marker.expired_range == model.SequenceRange(0, 2)
    assert result.never_existed_range is None


@pytest.mark.asyncio
async def test_partially_expired_range_reports_loss_and_retained_suffix(
    tmp_path: Path,
) -> None:
    journal, accepted = await _journal_with_expired_prefix(
        tmp_path / "partially-expired-range.sqlite3"
    )
    reference = model.EvidenceRangeReference(journal.session_id, 1, 4)
    try:
        result = await journal.retrieve(_retrieval_request(reference))
    finally:
        await journal.close()

    assert result.outcome is evidence.EvidencePageOutcome.PARTIAL
    assert result.records == accepted[2:4]
    assert result.expired_range == model.SequenceRange(1, 2)
    assert result.retention_marker is not None
    assert result.retention_marker.expired_range == model.SequenceRange(0, 2)
    assert result.never_existed_range is None


@pytest.mark.asyncio
async def test_empty_range_is_complete_at_every_position_through_next_sequence(
    tmp_path: Path,
) -> None:
    journal, _ = await _journal_with_expired_prefix(
        tmp_path / "complete-empty-ranges.sqlite3"
    )
    try:
        for position in range(5):
            reference = model.EvidenceRangeReference(
                journal.session_id,
                position,
                position,
            )
            result = await journal.retrieve(_retrieval_request(reference))

            assert result.outcome is evidence.EvidencePageOutcome.COMPLETE
            assert result.records == ()
            assert result.expired_range is None
            assert result.retention_marker is None
            assert result.never_existed_range is None
    finally:
        await journal.close()


@pytest.mark.asyncio
async def test_empty_range_is_not_found_only_beyond_next_sequence(
    tmp_path: Path,
) -> None:
    journal, _ = await _journal_with_expired_prefix(
        tmp_path / "missing-empty-range.sqlite3"
    )
    reference = model.EvidenceRangeReference(journal.session_id, 5, 5)
    try:
        result = await journal.retrieve(_retrieval_request(reference))
    finally:
        await journal.close()

    assert result.outcome is evidence.EvidencePageOutcome.NOT_FOUND
    assert result.records == ()
    assert result.expired_range is None


@pytest.mark.asyncio
async def test_never_existent_record_reference_is_not_found(
    tmp_path: Path,
) -> None:
    journal, _ = await _journal_with_expired_prefix(
        tmp_path / "missing-reference.sqlite3"
    )
    reference = model.EvidenceReference(journal.session_id, 4)
    try:
        result = await journal.resolve_record(reference)
    finally:
        await journal.close()

    assert result.outcome is evidence.EvidencePageOutcome.NOT_FOUND
    assert result.records == ()
    assert result.expired_range is None
    assert result.retention_marker is None
    assert result.never_existed_range == model.SequenceRange(4, 5)


@pytest.mark.asyncio
async def test_wholly_never_existent_range_is_not_found(
    tmp_path: Path,
) -> None:
    journal, _ = await _journal_with_expired_prefix(
        tmp_path / "missing-range.sqlite3"
    )
    reference = model.EvidenceRangeReference(journal.session_id, 4, 7)
    try:
        result = await journal.retrieve(_retrieval_request(reference))
    finally:
        await journal.close()

    assert result.outcome is evidence.EvidencePageOutcome.NOT_FOUND
    assert result.records == ()
    assert result.expired_range is None
    assert result.never_existed_range == model.SequenceRange(4, 7)


@pytest.mark.asyncio
async def test_range_with_never_existent_suffix_is_explicitly_partial(
    tmp_path: Path,
) -> None:
    journal, accepted = await _journal_with_expired_prefix(
        tmp_path / "partial-missing-suffix.sqlite3"
    )
    reference = model.EvidenceRangeReference(journal.session_id, 3, 7)
    try:
        result = await journal.retrieve(_retrieval_request(reference))
    finally:
        await journal.close()

    assert result.outcome is evidence.EvidencePageOutcome.PARTIAL
    assert result.records == accepted[3:4]
    assert result.expired_range is None
    assert result.never_existed_range == model.SequenceRange(4, 7)


@pytest.mark.asyncio
async def test_record_reference_rejects_another_session(
    tmp_path: Path,
) -> None:
    journal, _ = await _journal_with_expired_prefix(
        tmp_path / "record-session-mismatch.sqlite3"
    )
    other_session = model.SessionId("another-session")
    record_reference = model.EvidenceReference(other_session, 2)
    try:
        with pytest.raises(evidence.JournalFailure) as record_failure:
            await journal.resolve_record(record_reference)
    finally:
        await journal.close()

    assert record_failure.value.operation is evidence.JournalOperation.RETRIEVE
    assert record_failure.value.kind is evidence.JournalFailureKind.SESSION_MISMATCH


@pytest.mark.asyncio
async def test_range_reference_rejects_another_session(
    tmp_path: Path,
) -> None:
    journal, _ = await _journal_with_expired_prefix(
        tmp_path / "range-session-mismatch.sqlite3"
    )
    reference = model.EvidenceRangeReference(
        model.SessionId("another-session"),
        2,
        4,
    )
    try:
        with pytest.raises(evidence.JournalFailure) as range_failure:
            await journal.retrieve(_retrieval_request(reference))
    finally:
        await journal.close()

    assert range_failure.value.operation is evidence.JournalOperation.RETRIEVE
    assert range_failure.value.kind is evidence.JournalFailureKind.SESSION_MISMATCH


def test_page_request_requires_positive_caller_limits() -> None:
    reference = model.EvidenceRangeReference(model.SessionId("session"), 0, 1)

    with pytest.raises(ValueError, match="max records"):
        evidence.EvidenceRetrievalRequest(reference, 0, 1)
    with pytest.raises(ValueError, match="max charged bytes"):
        evidence.EvidenceRetrievalRequest(reference, 1, 0)


@pytest.mark.parametrize(
    ("max_records", "max_charged_bytes"),
    ((3, 5_000), (2, 5_001)),
)
@pytest.mark.asyncio
async def test_page_request_cannot_exceed_independent_policy_ceilings(
    tmp_path: Path,
    max_records: int,
    max_charged_bytes: int,
) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / f"page-policy-{max_records}-{max_charged_bytes}.sqlite3",
        _policy(
            max_record_charged_bytes=5_000,
            max_retrieval_page_records=2,
            max_retrieval_page_charged_bytes=5_000,
        ),
    )
    reference = model.EvidenceRangeReference(journal.session_id, 0, 1)
    try:
        await journal.append(_rx_draft(b"record"))
        with pytest.raises(evidence.JournalFailure) as failure:
            await journal.retrieve(
                evidence.EvidenceRetrievalRequest(
                    reference=reference,
                    max_records=max_records,
                    max_charged_bytes=max_charged_bytes,
                )
            )
    finally:
        await journal.close()

    assert failure.value.operation is evidence.JournalOperation.RETRIEVE
    assert failure.value.kind is evidence.JournalFailureKind.INVALID_INPUT


def test_policy_rejects_a_record_that_cannot_fit_the_page_byte_ceiling() -> None:
    with pytest.raises(ValueError, match="retrieval charged-byte ceiling"):
        _policy(
            max_record_charged_bytes=501,
            max_retrieval_page_charged_bytes=500,
        )


@pytest.mark.asyncio
async def test_large_retention_quota_does_not_enlarge_a_session_page(
    tmp_path: Path,
) -> None:
    payloads = (b"a", b"b", b"c")
    charge = _rx_charge(payloads[0])
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "independent-page-bytes.sqlite3",
        _policy(
            max_retained_charged_bytes=1_000_000,
            max_record_charged_bytes=charge,
            max_retrieval_page_records=10,
            max_retrieval_page_charged_bytes=charge * 2,
        ),
    )
    reference = model.EvidenceRangeReference(journal.session_id, 0, 3)
    try:
        accepted = tuple(
            [await journal.append(_rx_draft(payload)) for payload in payloads]
        )
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                reference=reference,
                max_records=10,
                max_charged_bytes=charge * 2,
            )
        )
    finally:
        await journal.close()

    assert page.records == accepted[:2]
    assert page.charged_bytes == charge * 2
    assert page.truncated
    assert page.continuation == evidence.EvidenceCursor(
        session_id=journal.session_id,
        range_start_inclusive=0,
        range_end_exclusive=3,
        snapshot_end_exclusive=3,
        next_sequence=2,
    )


@pytest.mark.asyncio
async def test_record_fitting_exact_page_boundaries_returns_a_complete_page(
    tmp_path: Path,
) -> None:
    payload = b"exact"
    charge = _rx_charge(payload)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "exact-page-boundary.sqlite3",
        _policy(
            max_record_charged_bytes=charge,
            max_retrieval_page_records=1,
            max_retrieval_page_charged_bytes=charge,
        ),
    )
    reference = model.EvidenceRangeReference(journal.session_id, 0, 1)
    try:
        accepted = await journal.append(_rx_draft(payload))
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                reference=reference,
                max_records=1,
                max_charged_bytes=charge,
            )
        )
    finally:
        await journal.close()

    assert page.records == (accepted,)
    assert page.outcome is evidence.EvidencePageOutcome.COMPLETE
    assert page.charged_bytes == charge
    assert not page.truncated
    assert page.continuation is None
    assert page.next_record_required_bytes is None


@pytest.mark.asyncio
async def test_page_truncates_at_record_count_with_a_sequence_cursor(
    tmp_path: Path,
) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "record-count-page.sqlite3",
        _policy(max_retrieval_page_records=3),
    )
    reference = model.EvidenceRangeReference(journal.session_id, 0, 3)
    try:
        accepted = tuple(
            [
                await journal.append(_rx_draft(payload))
                for payload in (b"zero", b"one", b"two")
            ]
        )
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                reference=reference,
                max_records=2,
                max_charged_bytes=20_000,
            )
        )
    finally:
        await journal.close()

    assert page.records == accepted[:2]
    assert page.truncated
    assert page.continuation == evidence.EvidenceCursor(
        session_id=journal.session_id,
        range_start_inclusive=0,
        range_end_exclusive=3,
        snapshot_end_exclusive=3,
        next_sequence=2,
    )
    assert page.next_record_required_bytes is None


@pytest.mark.asyncio
async def test_page_reports_the_whole_next_record_required_byte_count(
    tmp_path: Path,
) -> None:
    first_payload = b"small"
    next_payload = b"large" * 200
    first_charge = _rx_charge(first_payload)
    next_charge = _rx_charge(next_payload)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "oversized-next-record.sqlite3",
        _policy(
            max_record_charged_bytes=next_charge,
            max_retrieval_page_charged_bytes=next_charge,
        ),
    )
    reference = model.EvidenceRangeReference(journal.session_id, 0, 2)
    try:
        first = await journal.append(_rx_draft(first_payload))
        await journal.append(_rx_draft(next_payload))
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                reference=reference,
                max_records=2,
                max_charged_bytes=first_charge,
            )
        )
    finally:
        await journal.close()

    assert page.records == (first,)
    assert page.charged_bytes == first_charge
    assert page.truncated
    assert page.next_record_required_bytes == next_charge
    assert page.continuation == evidence.EvidenceCursor(
        session_id=journal.session_id,
        range_start_inclusive=0,
        range_end_exclusive=2,
        snapshot_end_exclusive=2,
        next_sequence=1,
    )


@pytest.mark.asyncio
async def test_cursor_progresses_by_sequence_not_timestamp_or_offset(
    tmp_path: Path,
) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "sequence-cursor.sqlite3",
        _policy(max_retrieval_page_records=1),
    )
    reference = model.EvidenceRangeReference(journal.session_id, 0, 3)
    try:
        accepted = tuple(
            [
                await journal.append(
                    _rx_draft_at(
                        payload,
                        segment_id="segment-1",
                        domain_id="host-domain",
                        value=timestamp,
                    )
                )
                for payload, timestamp in (
                    (b"first", 300),
                    (b"second", 100),
                    (b"third", 200),
                )
            ]
        )
        first_page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(reference, 1, 20_000)
        )
        assert first_page.continuation is not None
        second_page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                reference,
                1,
                20_000,
                cursor=first_page.continuation,
            )
        )
        assert second_page.continuation is not None
        third_page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                reference,
                1,
                20_000,
                cursor=second_page.continuation,
            )
        )
    finally:
        await journal.close()

    assert first_page.records == (accepted[0],)
    assert second_page.records == (accepted[1],)
    assert third_page.records == (accepted[2],)
    assert first_page.continuation.next_sequence == 1
    assert second_page.continuation.next_sequence == 2
    assert third_page.continuation is None
    assert not third_page.truncated


@pytest.mark.asyncio
async def test_page_snapshot_excludes_records_appended_after_the_first_page(
    tmp_path: Path,
) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "fixed-snapshot.sqlite3",
        _policy(max_retrieval_page_records=1),
    )
    reference = model.EvidenceRangeReference(
        journal.session_id,
        0,
        model.SQLITE_INTEGER_MAX,
    )
    try:
        first = await journal.append(_rx_draft(b"first"))
        second = await journal.append(_rx_draft(b"second"))
        first_page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(reference, 1, 20_000)
        )
        assert first_page.continuation is not None
        later = await journal.append(_rx_draft(b"later"))
        second_page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                reference,
                1,
                20_000,
                cursor=first_page.continuation,
            )
        )
    finally:
        await journal.close()

    assert first_page.records == (first,)
    assert first_page.snapshot_end_exclusive == 2
    assert second_page.records == (second,)
    assert second_page.snapshot_end_exclusive == 2
    assert second_page.continuation is None
    assert later.sequence == 2


@pytest.mark.asyncio
async def test_continuation_reports_evidence_expired_between_pages(
    tmp_path: Path,
) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "between-page-expiry.sqlite3",
        _policy(max_retained_records=2, max_retrieval_page_records=1),
    )
    reference = model.EvidenceRangeReference(journal.session_id, 0, 2)
    try:
        await journal.append(_rx_draft(b"zero"))
        await journal.append(_rx_draft(b"one"))
        first_page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(reference, 1, 20_000)
        )
        assert first_page.continuation is not None
        await journal.append(_rx_draft(b"two"))
        await journal.append(_rx_draft(b"three"))
        second_page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(
                reference,
                1,
                20_000,
                cursor=first_page.continuation,
            )
        )
    finally:
        await journal.close()

    assert second_page.records == ()
    assert second_page.outcome is evidence.EvidencePageOutcome.EXPIRED
    assert second_page.expired_range == model.SequenceRange(1, 2)
    assert second_page.retention_marker is not None
    assert second_page.retention_marker.expired_range == model.SequenceRange(0, 2)
    assert second_page.snapshot_end_exclusive == 2
    assert not second_page.truncated
    assert second_page.continuation is None


@pytest.mark.asyncio
async def test_cursor_from_another_session_is_rejected(
    tmp_path: Path,
) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "cursor-session-mismatch.sqlite3",
        _policy(),
    )
    reference = model.EvidenceRangeReference(journal.session_id, 0, 3)
    cursor = evidence.EvidenceCursor(
        session_id=model.SessionId("another-session"),
        range_start_inclusive=0,
        range_end_exclusive=3,
        snapshot_end_exclusive=3,
        next_sequence=1,
    )
    try:
        for payload in (b"zero", b"one", b"two"):
            await journal.append(_rx_draft(payload))
        with pytest.raises(evidence.JournalFailure) as failure:
            await journal.retrieve(
                evidence.EvidenceRetrievalRequest(
                    reference,
                    1,
                    20_000,
                    cursor=cursor,
                )
            )
    finally:
        await journal.close()

    assert failure.value.operation is evidence.JournalOperation.RETRIEVE
    assert failure.value.kind is evidence.JournalFailureKind.SESSION_MISMATCH


@pytest.mark.asyncio
async def test_cursor_reused_with_another_range_is_rejected(
    tmp_path: Path,
) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "cursor-range-mismatch.sqlite3",
        _policy(),
    )
    reference = model.EvidenceRangeReference(journal.session_id, 1, 3)
    cursor = evidence.EvidenceCursor(
        session_id=journal.session_id,
        range_start_inclusive=0,
        range_end_exclusive=3,
        snapshot_end_exclusive=3,
        next_sequence=1,
    )
    try:
        for payload in (b"zero", b"one", b"two"):
            await journal.append(_rx_draft(payload))
        with pytest.raises(evidence.JournalFailure) as failure:
            await journal.retrieve(
                evidence.EvidenceRetrievalRequest(
                    reference,
                    1,
                    20_000,
                    cursor=cursor,
                )
            )
    finally:
        await journal.close()

    assert failure.value.operation is evidence.JournalOperation.RETRIEVE
    assert failure.value.kind is evidence.JournalFailureKind.INVALID_INPUT


@pytest.mark.asyncio
async def test_returned_cursor_holds_no_live_sqlite_transaction_or_lock(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lock-free-cursor.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        path,
        _policy(max_retrieval_page_records=1),
    )
    locker: sqlite3.Connection | None = None
    reference = model.EvidenceRangeReference(journal.session_id, 0, 2)
    try:
        await journal.append(_rx_draft(b"zero"))
        await journal.append(_rx_draft(b"one"))
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(reference, 1, 20_000)
        )
        assert page.continuation is not None

        locker = sqlite3.connect(path, timeout=0)
        locker.execute("BEGIN EXCLUSIVE")
        locker.rollback()
        locker.close()
        locker = None
    finally:
        if locker is not None:
            locker.rollback()
            locker.close()
        await journal.close()


@pytest.mark.asyncio
async def test_cancelled_retrieval_holds_gate_until_worker_before_next_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections = _install_blocking_retrieval_connection(monkeypatch)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "cancelled-retrieval-next.sqlite3",
        _policy(),
    )
    reference = model.EvidenceRangeReference(journal.session_id, 0, 1)
    blocker = connections[0]
    try:
        await journal.append(_rx_draft(b"first"))
        blocker.arm_next_retrieval()
        retrieval = asyncio.create_task(
            journal.retrieve(_retrieval_request(reference))
        )
        await _wait_for_thread_event(blocker.retrieval_started)
        retrieval.cancel()
        following_append = asyncio.create_task(journal.append(_rx_draft(b"second")))
        await asyncio.sleep(0)
        cancellation_returned_while_blocked = retrieval.done()
        following_started_while_blocked = following_append.done()
        blocker.release_retrieval.set()
        with pytest.raises(asyncio.CancelledError):
            await retrieval
        following = await following_append
    finally:
        blocker.release_retrieval.set()
        await journal.close()

    assert not cancellation_returned_while_blocked
    assert not following_started_while_blocked
    assert following.sequence == 1


@pytest.mark.asyncio
async def test_cancelled_retrieval_holds_gate_until_worker_before_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections = _install_blocking_retrieval_connection(monkeypatch)
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(
        tmp_path / "cancelled-retrieval-close.sqlite3",
        _policy(),
    )
    reference = model.EvidenceRangeReference(journal.session_id, 0, 1)
    blocker = connections[0]
    try:
        await journal.append(_rx_draft(b"first"))
        blocker.arm_next_retrieval()
        retrieval = asyncio.create_task(
            journal.retrieve(_retrieval_request(reference))
        )
        await _wait_for_thread_event(blocker.retrieval_started)
        retrieval.cancel()
        close_task = asyncio.create_task(journal.close())
        await asyncio.sleep(0)
        cancellation_returned_while_blocked = retrieval.done()
        close_returned_while_blocked = close_task.done()
        blocker.release_retrieval.set()
        with pytest.raises(asyncio.CancelledError):
            await retrieval
        await close_task
    finally:
        blocker.release_retrieval.set()
        await journal.close()

    assert not cancellation_returned_while_blocked
    assert not close_returned_while_blocked


@pytest.mark.asyncio
async def test_open_rejects_wrong_application_identity_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wrong-application.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.close()
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA application_id = 1")
        connection.commit()
    finally:
        connection.close()

    await _assert_open_failure_preserves_source(
        path,
        evidence.JournalFailureKind.INCOMPATIBLE_APPLICATION,
    )


@pytest.mark.parametrize("schema_version", (0, 2))
@pytest.mark.asyncio
async def test_open_rejects_unsupported_store_version_without_writing(
    tmp_path: Path,
    schema_version: int,
) -> None:
    path = tmp_path / f"unsupported-store-{schema_version}.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.close()
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"PRAGMA user_version = {schema_version}")
        connection.commit()
    finally:
        connection.close()

    await _assert_open_failure_preserves_source(
        path,
        evidence.JournalFailureKind.INCOMPATIBLE_SCHEMA_VERSION,
    )


@pytest.mark.asyncio
async def test_open_rejects_unsupported_record_version_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unsupported-record.sqlite3"
    await _create_closed_journal_with_record(path, _rx_draft(b"versioned"))
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE evidence_records SET record_version = 2 WHERE sequence = 0"
        )
        connection.commit()
    finally:
        connection.close()

    await _assert_open_failure_preserves_source(
        path,
        evidence.JournalFailureKind.INCOMPATIBLE_RECORD_VERSION,
    )


@pytest.mark.asyncio
async def test_open_rejects_unsupported_provenance_envelope_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unsupported-envelope.sqlite3"
    await _create_closed_journal_with_record(
        path,
        evidence.PendingSegmentStartedEvidence(_segment_provenance()),
    )
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            """
            SELECT record_kind, metadata_json
            FROM evidence_records WHERE sequence = 0
            """
        ).fetchone()
        assert row is not None
        metadata = json.loads(cast("bytes", row[1]).decode("utf-8"))
        assert isinstance(metadata, dict)
        provenance = metadata["connection_provenance"]
        assert isinstance(provenance, dict)
        provenance["envelope_version"] = 2
        metadata_json = json.dumps(
            metadata,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        charged_bytes = 16 + len(cast("str", row[0]).encode()) + len(metadata_json)
        connection.execute(
            """
            UPDATE evidence_records
            SET metadata_json = ?, charged_bytes = ?
            WHERE sequence = 0
            """,
            (metadata_json, charged_bytes),
        )
        connection.execute(
            """
            UPDATE session_metadata SET retained_charged_bytes = ?
            WHERE singleton = 1
            """,
            (charged_bytes,),
        )
        connection.commit()
    finally:
        connection.close()

    await _assert_open_failure_preserves_source(
        path,
        evidence.JournalFailureKind.INCOMPATIBLE_PROVENANCE_ENVELOPE_VERSION,
    )


@pytest.mark.asyncio
async def test_unknown_backend_provenance_kind_and_version_round_trip_opaquely(
    tmp_path: Path,
) -> None:
    path = tmp_path / "opaque-future-backend.sqlite3"
    snapshot = model.ConnectionProvenanceSnapshot(
        envelope_version=1,
        backend_kind="future-backend-that-core-does-not-know",
        backend_schema_version=9_223_372_036_854_775_807,
        fields=(
            model.ProvenanceField("future_flag", True),
            model.ProvenanceField("future_name", "opaque"),
        ),
    )
    provenance = _segment_provenance()
    draft = evidence.PendingSegmentStartedEvidence(
        model.SegmentProvenance(
            connection_id=provenance.connection_id,
            segment_id=provenance.segment_id,
            capabilities=provenance.capabilities,
            backend_observation_timestamp_domain=(
                provenance.backend_observation_timestamp_domain
            ),
            loss_observability=provenance.loss_observability,
            connection_provenance=model.PersistedConnectionProvenance(snapshot),
        )
    )
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    accepted = await journal.append(draft)
    await journal.close()

    reopened = await sqlite_evidence.SqliteEvidenceJournal.open(path)
    try:
        page = await reopened.resolve_record(
            model.EvidenceReference(reopened.session_id, accepted.sequence)
        )
    finally:
        await reopened.close()

    assert len(page.records) == 1
    restored = page.records[0]
    assert isinstance(restored, model.SegmentStartedEvidence)
    assert restored.provenance.connection_provenance.to_snapshot() == snapshot


@pytest.mark.asyncio
async def test_open_rejects_missing_schema_object_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing-schema-object.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.close()
    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TABLE retention_marker")
        connection.commit()
    finally:
        connection.close()

    await _assert_open_failure_preserves_source(
        path,
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    )


@pytest.mark.parametrize(
    "corruption",
    ("noncanonical_metadata", "missing_rx_payload"),
)
@pytest.mark.asyncio
async def test_open_rejects_malformed_metadata_and_payload_without_writing(
    tmp_path: Path,
    corruption: str,
) -> None:
    path = tmp_path / f"malformed-{corruption}.sqlite3"
    await _create_closed_journal_with_record(path, _rx_draft(b"exact-payload"))
    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            """
            SELECT record_kind, metadata_json
            FROM evidence_records WHERE sequence = 0
            """
        ).fetchone()
        assert row is not None
        record_kind = cast("str", row[0])
        metadata_json = cast("bytes", row[1])
        payload: bytes | None = b"exact-payload"
        rx_payload_bytes = len(b"exact-payload")
        if corruption == "noncanonical_metadata":
            metadata_json = b'{ "connection_id": "connection-1" }'
        else:
            payload = None
            rx_payload_bytes = 0
        charged_bytes = (
            16
            + len(record_kind.encode())
            + len(metadata_json)
            + len(payload or b"")
        )
        connection.execute(
            """
            UPDATE evidence_records
            SET metadata_json = ?, payload = ?, charged_bytes = ?,
                rx_payload_bytes = ?
            WHERE sequence = 0
            """,
            (metadata_json, payload, charged_bytes, rx_payload_bytes),
        )
        connection.execute(
            """
            UPDATE session_metadata SET retained_charged_bytes = ?
            WHERE singleton = 1
            """,
            (charged_bytes,),
        )
        connection.commit()
    finally:
        connection.close()

    await _assert_open_failure_preserves_source(
        path,
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    )


@pytest.mark.parametrize("corruption", ("aggregate", "sequence"))
@pytest.mark.asyncio
async def test_open_rejects_aggregate_and_sequence_corruption_without_writing(
    tmp_path: Path,
    corruption: str,
) -> None:
    path = tmp_path / f"corrupt-{corruption}.sqlite3"
    await _create_closed_journal_with_record(path, _rx_draft(b"retained"))
    connection = sqlite3.connect(path)
    try:
        if corruption == "aggregate":
            connection.execute(
                """
                UPDATE session_metadata
                SET retained_charged_bytes = retained_charged_bytes + 1
                WHERE singleton = 1
                """
            )
        else:
            connection.execute(
                "UPDATE evidence_records SET sequence = 1 WHERE sequence = 0"
            )
        connection.commit()
    finally:
        connection.close()

    await _assert_open_failure_preserves_source(
        path,
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    )


@pytest.mark.asyncio
async def test_open_rejects_huge_corrupt_sequence_span_without_materializing_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "corrupt-huge-sequence-span.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.close()
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            UPDATE session_metadata
            SET next_sequence = ?, retained_record_count = ?
            WHERE singleton = 1
            """,
            (model.SQLITE_INTEGER_MAX, model.SQLITE_INTEGER_MAX),
        )
        connection.commit()
    finally:
        connection.close()

    real_range = range

    def reject_huge_materialization(*args: int) -> range:
        if args == (0, model.SQLITE_INTEGER_MAX):
            raise AssertionError("corrupt sequence span was materialized")
        return real_range(*args)

    monkeypatch.setattr(
        sqlite_evidence,
        "range",
        reject_huge_materialization,
        raising=False,
    )

    await _assert_open_failure_preserves_source(
        path,
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    )


@pytest.mark.asyncio
async def test_open_rejects_failed_quick_check_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "failed-quick-check.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.close()
    real_connect = sqlite_evidence._connect_sqlite

    def connect_with_failed_quick_check(
        database: str,
        *,
        uri: bool = False,
    ) -> sqlite3.Connection:
        return cast(
            "sqlite3.Connection",
            _FailedQuickCheckConnection(real_connect(database, uri=uri)),
        )

    monkeypatch.setattr(
        sqlite_evidence,
        "_connect_sqlite",
        connect_with_failed_quick_check,
    )

    await _assert_open_failure_preserves_source(
        path,
        evidence.JournalFailureKind.CORRUPT_JOURNAL,
    )


@pytest.mark.asyncio
async def test_locked_open_is_normalized_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "locked-open.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.close()
    locker = sqlite3.connect(path)
    locker.execute("BEGIN EXCLUSIVE")

    def connect_without_waiting(
        database: str,
        *,
        uri: bool = False,
    ) -> sqlite3.Connection:
        return sqlite3.connect(database, uri=uri, timeout=0)

    monkeypatch.setattr(
        sqlite_evidence,
        "_connect_sqlite",
        connect_without_waiting,
    )
    try:
        await _assert_open_failure_preserves_source(
            path,
            evidence.JournalFailureKind.BUSY,
        )
    finally:
        locker.rollback()
        locker.close()


@pytest.mark.asyncio
async def test_read_only_open_is_rejected_before_returning_a_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "read-only-open.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.close()

    def connect_read_only(
        database: str,
        *,
        uri: bool = False,
    ) -> sqlite3.Connection:
        del database, uri
        return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)

    monkeypatch.setattr(sqlite_evidence, "_connect_sqlite", connect_read_only)

    await _assert_open_failure_preserves_source(
        path,
        evidence.JournalFailureKind.READ_ONLY,
    )
