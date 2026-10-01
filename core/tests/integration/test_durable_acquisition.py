"""Acquisition integration contracts for the durable evidence journal."""

import asyncio
import sqlite3
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import pytest

from dutchmate_core.acquisition import (
    Acquisition,
    AcquisitionFailureKind,
    AcquisitionState,
)
from dutchmate_core.adapters import sqlite_evidence
from dutchmate_core.adapters.basic_serial import (
    BasicSerialBackend,
    SerialConfiguration,
    SerialDataBits,
    SerialDeviceSelector,
    SerialLineState,
    SerialOpenLineIntent,
    SerialParity,
    SerialStopBits,
)
from dutchmate_core.backend import Backend, BackendConnection
from dutchmate_core.evidence import JournalFailure, JournalFailureKind, JournalOperation
from dutchmate_core.model import (
    BackendConnectionProvenance,
    ConnectionInstanceId,
    ConnectionProvenanceSnapshot,
    EvidenceRecord,
    PersistedConnectionProvenance,
    ProvenanceField,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentStartedEvidence,
    SessionPolicy,
)
from tests.contract.test_basic_serial_adapter import (
    FakeMonotonicClock,
    FakeSerial,
    FakeSerialFactory,
)
from tests.fakes import EnhancedShapedBackend, EnhancedShapedBackendConnection


@dataclass(frozen=True, slots=True)
class _EnhancedFixtureProvenance(BackendConnectionProvenance):
    def to_snapshot(self) -> ConnectionProvenanceSnapshot:
        return ConnectionProvenanceSnapshot(
            envelope_version=1,
            backend_kind="fixture/enhanced-shaped",
            backend_schema_version=37,
            fields=(ProvenanceField("transport", "simulated"),),
        )


class _DurableEnhancedConnection(EnhancedShapedBackendConnection):
    def __init__(self) -> None:
        super().__init__()
        self.descriptor = replace(
            self.descriptor,
            connection_provenance=_EnhancedFixtureProvenance(),
        )


class _CapturingBackend:
    def __init__(self, delegate: Backend) -> None:
        self._delegate = delegate
        self.connection: BackendConnection | None = None

    async def open(self) -> BackendConnection:
        connection = await self._delegate.open()
        self.connection = connection
        return connection


def _policy() -> SessionPolicy:
    return SessionPolicy(
        max_retained_records=100,
        max_retained_charged_bytes=100_000,
        max_record_charged_bytes=10_000,
        max_database_pages=64,
        max_retrieval_page_records=20,
        max_retrieval_page_charged_bytes=20_000,
    )


def _basic_backend(fake_serial: FakeSerial) -> _CapturingBackend:
    delegate = BasicSerialBackend(
        selector=SerialDeviceSelector("/dev/ttyUSB-durable-fixture"),
        configuration=SerialConfiguration(
            baud_rate=115_200,
            data_bits=SerialDataBits.EIGHT,
            parity=SerialParity.NONE,
            stop_bits=SerialStopBits.ONE,
            hardware_flow_control=False,
            software_flow_control=False,
        ),
        line_intent=SerialOpenLineIntent(
            dtr=SerialLineState.DEASSERTED,
            rts=SerialLineState.DEASSERTED,
        ),
        _serial_factory=FakeSerialFactory(fake_serial),
    )
    return _CapturingBackend(cast("Backend", delegate))


async def _wait_for_thread_event(event: threading.Event) -> None:
    observed = await asyncio.wait_for(
        asyncio.to_thread(event.wait, 1.0),
        timeout=2.0,
    )
    assert observed


async def _wait_for_termination(acquisition: Acquisition) -> AcquisitionState:
    return await asyncio.wait_for(acquisition.wait_terminated(), timeout=2.0)


def _read_records(path: Path) -> tuple[EvidenceRecord, ...]:
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


async def _record_enhanced_session(
    journal: sqlite_evidence.SqliteEvidenceJournal,
    payload: bytes,
) -> tuple[ConnectionInstanceId, ConnectionProvenanceSnapshot]:
    connection = _DurableEnhancedConnection()
    acquisition = Acquisition(journal)
    connection_id = await acquisition.start(EnhancedShapedBackend(connection))
    await connection.emit_rx(payload, timestamp=7)
    await connection.disconnect()
    assert await _wait_for_termination(acquisition) is AcquisitionState.STOPPED
    return connection_id, connection.descriptor.connection_provenance.to_snapshot()


@pytest.mark.asyncio
async def test_basic_ambient_exact_rx_and_provenance_round_trip_durably(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = bytes(range(256)) + b"\x00\x80\xfe\xffinvalid-utf8:\xf5"
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock((101, 102)))
    stop_gate = threading.Event()
    fake_serial = FakeSerial(
        read_results=(payload, b""),
        read_gates=(None, stop_gate),
    )
    backend = _basic_backend(fake_serial)
    path = tmp_path / "basic-durable.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    acquisition = Acquisition(journal)
    try:
        connection_id = await acquisition.start(backend)
        await _wait_for_thread_event(fake_serial.read_started[1])
        stop_task = asyncio.create_task(acquisition.stop())
        await _wait_for_thread_event(fake_serial.cancel_read_called)
        stop_gate.set()
        assert await asyncio.wait_for(stop_task, timeout=2.0) is (
            AcquisitionState.STOPPED
        ), acquisition.failure
        connection = backend.connection
        assert connection is not None
        expected_snapshot = connection.descriptor.connection_provenance.to_snapshot()
    finally:
        stop_gate.set()
        await acquisition.stop()
        await journal.close()

    records = _read_records(path)
    assert [record.sequence for record in records] == [0, 1, 2]
    assert [type(record) for record in records] == [
        SegmentStartedEvidence,
        RxBytesEvidence,
        SegmentEndedEvidence,
    ]
    segment_start = cast("SegmentStartedEvidence", records[0])
    recorded_rx = cast("RxBytesEvidence", records[1])
    assert segment_start.connection_id == connection_id
    assert isinstance(
        segment_start.provenance.connection_provenance,
        PersistedConnectionProvenance,
    )
    assert segment_start.provenance.connection_provenance.to_snapshot() == (
        expected_snapshot
    )
    assert recorded_rx.payload == payload
    assert recorded_rx.connection_id == connection_id
    assert recorded_rx.segment_id == segment_start.segment_id


@pytest.mark.asyncio
async def test_enhanced_shaped_restart_continues_journal_sequences_and_session(
    tmp_path: Path,
) -> None:
    path = tmp_path / "enhanced-durable.sqlite3"
    created = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    session_id = created.session_id
    first_connection_id, first_snapshot = await _record_enhanced_session(
        created,
        b"before-restart",
    )
    await created.close()

    reopened = await sqlite_evidence.SqliteEvidenceJournal.open(
        path,
        expected_session_id=session_id,
    )
    assert reopened.session_id == session_id
    second_connection_id, second_snapshot = await _record_enhanced_session(
        reopened,
        b"after-restart",
    )
    await reopened.close()

    records = _read_records(path)
    assert [record.sequence for record in records] == list(range(6))
    assert [type(record) for record in records] == [
        SegmentStartedEvidence,
        RxBytesEvidence,
        SegmentEndedEvidence,
        SegmentStartedEvidence,
        RxBytesEvidence,
        SegmentEndedEvidence,
    ]
    starts = cast(
        "tuple[SegmentStartedEvidence, SegmentStartedEvidence]",
        (records[0], records[3]),
    )
    assert [start.connection_id for start in starts] == [
        first_connection_id,
        second_connection_id,
    ]
    assert [
        start.provenance.connection_provenance.to_snapshot() for start in starts
    ] == [first_snapshot, second_snapshot]
    rx_records = cast("tuple[RxBytesEvidence, RxBytesEvidence]", (records[1], records[4]))
    assert [record.payload for record in rx_records] == [
        b"before-restart",
        b"after-restart",
    ]


@pytest.mark.asyncio
async def test_durable_recording_failure_terminates_acquisition(
    tmp_path: Path,
) -> None:
    path = tmp_path / "recording-failure.sqlite3"
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    connection = _DurableEnhancedConnection()
    acquisition = Acquisition(journal)
    await acquisition.start(EnhancedShapedBackend(connection))
    await journal.close()

    await connection.emit_rx(b"cannot-be-recorded", timestamp=9)
    assert await _wait_for_termination(acquisition) is AcquisitionState.FAILED

    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.RECORDING_FAILURE
    failure = acquisition.failure.cause
    assert isinstance(failure, JournalFailure)
    assert failure.operation is JournalOperation.APPEND
    assert failure.kind is JournalFailureKind.CLOSED
    assert connection.closed
    records = _read_records(path)
    assert len(records) == 1
    assert isinstance(records[0], SegmentStartedEvidence)
