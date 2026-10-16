"""US1 readback through real runtime/Basic/SQLite composition, without hardware."""

import asyncio
import sqlite3
import threading
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager, closing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import pytest

from dutchmate_core import acquisition as aq
from dutchmate_core import model, profile
from dutchmate_core import runtime as rt
from dutchmate_core.adapters import basic_serial, sqlite_evidence
from dutchmate_core.adapters.observation_runtime import attach_basic_observation
from dutchmate_core.adapters.toml_profile import resolve_profile
from dutchmate_core.backend import Backend
from dutchmate_core.evidence import (
    EvidencePageOutcome,
    EvidenceRecorder,
    EvidenceRetrievalRequest,
    JournalFailure,
    JournalFailureKind,
    JournalOperation,
    PendingEvidenceRecord,
    PendingRxBytesEvidence,
    PendingSegmentEndedEvidence,
    PendingSegmentStartedEvidence,
)
from dutchmate_core.model import (
    EvidenceRangeReference,
    EvidenceRecord,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentEndReason,
    SegmentStartedEvidence,
    SequenceRange,
    SessionPolicy,
)
from dutchmate_core.runtime import ObservationRuntime, RuntimeState, RuntimeStatus
from tests.contract.test_basic_serial_adapter import FakeSerial, FakeSerialFactory
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixture,
    BackendFixtureFactory,
    BasicShapedBackend,
    EnhancedShapedBackend,
    EnhancedShapedBackendConnection,
    FixtureLifecycleGate,
    ShapedBackendConnection,
)

_POLICY = SessionPolicy(100, 65536, 8192, 128, 11, 16384)


def _profile_text(policy: SessionPolicy) -> str:
    return f"""profile_version = 1
[dut]
id = "fixture/ephemeral-profile-identity"
name = "Ephemeral Profile display name"
[backend]
kind = "basic_serial"
expected_device = "/dev/fixture-only"
[uart]
baud_rate = 19200
data_bits = 7
parity = "even"
stop_bits = 2
hardware_flow_control = false
software_flow_control = true
[uart.open_lines]
dtr = "deasserted"
rts = "deasserted"
[persistence]
max_retained_records = {policy.max_retained_records}
max_retained_charged_bytes = {policy.max_retained_charged_bytes}
max_record_charged_bytes = {policy.max_record_charged_bytes}
max_database_pages = {policy.max_database_pages}
max_retrieval_page_records = {policy.max_retrieval_page_records}
max_retrieval_page_charged_bytes = {policy.max_retrieval_page_charged_bytes}
"""


class _GatedSerial(FakeSerial):
    """Release each RX explicitly; cancel_read unblocks the final empty read."""

    def __init__(self, payloads: tuple[bytes, ...]) -> None:
        self.gates = tuple(threading.Event() for _ in range(len(payloads) + 1))
        super().__init__(read_results=(*payloads, b""), read_gates=self.gates)

    def cancel_read(self) -> None:
        super().cancel_read()
        for gate in self.gates:
            gate.set()


type _CommitQueue = asyncio.Queue[
    tuple[sqlite_evidence.SqliteEvidenceJournal, EvidenceRecord]
]


async def _commit(queue: _CommitQueue, sequence: int) -> EvidenceRecord:
    _, record = await asyncio.wait_for(queue.get(), timeout=2.0)
    assert record.sequence == sequence
    return record


@dataclass
class _Run:
    runtime: ObservationRuntime
    active: RuntimeStatus
    profile_path: Path
    journal_path: Path
    journal: sqlite_evidence.SqliteEvidenceJournal
    serial: _GatedSerial
    commits: _CommitQueue
    start: SegmentStartedEvidence

    async def emit(self, index: int) -> RxBytesEvidence:
        self.serial.gates[index].set()
        record = await _commit(self.commits, index + 1)
        assert isinstance(record, RxBytesEvidence)
        return record


@asynccontextmanager
async def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payloads: tuple[bytes, ...],
    policy: SessionPolicy = _POLICY,
) -> AsyncIterator[_Run]:
    # The physical serial factory is the only substituted dependency. The
    # append spy acknowledges the real durable commit, without changing it.
    fake = _GatedSerial(payloads)
    factory = FakeSerialFactory(fake)
    original_init = basic_serial.BasicSerialBackend.__init__
    original_append = sqlite_evidence.SqliteEvidenceJournal.append
    commits: _CommitQueue = asyncio.Queue()

    def construct(
        self: basic_serial.BasicSerialBackend,
        selector: basic_serial.SerialDeviceSelector,
        configuration: basic_serial.SerialConfiguration,
        line_intent: basic_serial.SerialOpenLineIntent,
    ) -> None:
        original_init(
            self, selector, configuration, line_intent, _serial_factory=factory
        )

    async def append(
        self: sqlite_evidence.SqliteEvidenceJournal, pending: PendingEvidenceRecord
    ) -> EvidenceRecord:
        record = await original_append(self, pending)
        commits.put_nowait((self, record))
        return record

    monkeypatch.setattr(basic_serial.BasicSerialBackend, "__init__", construct)
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "append", append)
    profile_path = tmp_path / "explicit-observation-profile.toml"
    profile_path.write_text(_profile_text(policy), encoding="utf-8")
    journal_path = tmp_path / "observation.sqlite3"
    runtime = ObservationRuntime()
    try:
        active = await asyncio.wait_for(
            attach_basic_observation(runtime, profile_path, journal_path),
            timeout=2.0,
        )
        assert active.state is RuntimeState.ACTIVE
        journal, start = await asyncio.wait_for(commits.get(), timeout=2.0)
        assert isinstance(start, SegmentStartedEvidence)
        assert start.sequence == 0
        assert active.session_id == journal.session_id
        assert journal.policy == policy
        yield _Run(
            runtime, active, profile_path, journal_path, journal, fake, commits, start
        )
    finally:
        for gate in fake.gates:
            gate.set()
        await asyncio.wait_for(runtime.detach(), timeout=2.0)


@pytest.mark.asyncio
async def test_binary_and_ambient_rx_round_trip_with_final_segment_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catch dropped/transformed chunks or recorder close before the final append.
    payloads = (bytes(range(256)) + b"\x00\xff\xf5", b"ambient\r\n\x80\x00")
    async with _run(tmp_path, monkeypatch, payloads) as run:
        accepted = [run.start, await run.emit(0), await run.emit(1)]
        terminal = await run.runtime.detach()
        end = await _commit(run.commits, 3)
        assert isinstance(end, SegmentEndedEvidence)
        assert end.reason is SegmentEndReason.EXPLICIT_STOP
        assert terminal.state is RuntimeState.TERMINATED
        assert terminal.session_id == run.active.session_id
        assert terminal.attach_admissible
        with pytest.raises(JournalFailure) as closed:
            await run.journal.retrieve(
                EvidenceRetrievalRequest(
                    run.journal.session_id,
                    11,
                    16384,
                )
            )
        assert closed.value.kind is JournalFailureKind.CLOSED

        reopened = await sqlite_evidence.SqliteEvidenceJournal.open_v3(
            run.journal_path,
            expected_session_id=run.active.session_id,
        )
        try:
            page = await reopened.retrieve(
                EvidenceRetrievalRequest(
                    reopened.session_id,
                    11,
                    16384,
                )
            )
            assert reopened.policy == _POLICY
        finally:
            await reopened.close()

        assert page.outcome is EvidencePageOutcome.COMPLETE
        assert page.records == (*accepted, end)
        assert [record.sequence for record in page.records] == [0, 1, 2, 3]
        assert [
            record.payload
            for record in page.records
            if isinstance(record, RxBytesEvidence)
        ] == list(payloads)
        assert all(
            isinstance(
                record,
                (
                    SegmentStartedEvidence,
                    RxBytesEvidence,
                    model.ObserverLossEvidence,
                    SegmentEndedEvidence,
                ),
            )
            and record.connection_id == run.start.connection_id
            and record.segment_id == run.start.segment_id
            for record in page.records
        )
        assert page.retention_marker is None
        assert not page.truncated
        assert page.continuation is None
        assert run.serial.max_active_reads == 1
        assert run.serial.active_reads == 0
        assert run.serial.close_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("quota,expired_end", [("records", 2), ("bytes", 3)])
async def test_small_retention_quota_reports_expired_prefix_after_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    quota: str,
    expired_end: int,
) -> None:
    # Three retained records keep RX2/RX3/end. An 8192-byte ceiling cannot
    # retain two 4096-byte RX payloads plus their charged metadata: RX3/end fit.
    policy = (
        replace(_POLICY, max_retained_records=3)
        if quota == "records"
        else (replace(_POLICY, max_retained_charged_bytes=8192))
    )
    payloads = (b"a" * 4096, b"b" * 4096, b"c" * 4096)
    async with _run(tmp_path, monkeypatch, payloads, policy) as run:
        for index in range(3):
            await run.emit(index)
        await run.runtime.detach()
        reopened = await sqlite_evidence.SqliteEvidenceJournal.open_v3(run.journal_path)
        try:
            page = await reopened.retrieve(
                EvidenceRetrievalRequest(
                    EvidenceRangeReference(reopened.session_id, 0, 5),
                    11,
                    16384,
                )
            )
            expired = await reopened.retrieve(
                EvidenceRetrievalRequest(
                    EvidenceRangeReference(reopened.session_id, 0, expired_end),
                    11,
                    16384,
                )
            )
        finally:
            await reopened.close()

        assert page.outcome is EvidencePageOutcome.PARTIAL
        assert page.expired_range == SequenceRange(0, expired_end)
        assert page.never_existed_range is None
        assert [record.sequence for record in page.records] == list(
            range(expired_end, 5)
        )
        assert len(page.records) <= policy.max_retained_records
        assert page.charged_bytes <= policy.max_retained_charged_bytes
        assert isinstance(page.records[-1], SegmentEndedEvidence)
        assert page.records[-1].reason is SegmentEndReason.EXPLICIT_STOP
        assert [
            record.payload
            for record in page.records
            if isinstance(record, RxBytesEvidence)
        ] == list(payloads[expired_end - 1 :])
        marker = page.retention_marker
        assert marker is not None
        assert marker.expired_range == SequenceRange(0, expired_end)
        assert marker.discarded_record_count == expired_end
        assert marker.discarded_rx_payload_byte_count == 4096 * (expired_end - 1)
        assert marker.first_discarded_timestamp is not None
        assert marker.last_discarded_timestamp is not None
        assert expired.outcome is EvidencePageOutcome.EXPIRED
        assert expired.records == ()
        assert expired.expired_range == SequenceRange(0, expired_end)
        assert expired.retention_marker == marker
        assert not expired.truncated
        assert expired.continuation is None


@pytest.mark.asyncio
async def test_fixed_snapshot_pages_exclude_later_ambient_rx_and_detach_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catch runtime composition changing the journal's page cap/snapshot fence.
    policy = replace(_POLICY, max_retrieval_page_records=1)
    async with _run(tmp_path, monkeypatch, (b"first", b"later"), policy) as run:
        first_rx = await run.emit(0)
        first = await run.journal.retrieve(
            EvidenceRetrievalRequest(
                run.journal.session_id,
                1,
                16384,
            )
        )
        assert first.records == (run.start,)
        assert first.snapshot_end_exclusive == 2
        assert first.truncated
        assert first.continuation is not None
        await run.emit(1)
        await run.runtime.detach()

        reopened = await sqlite_evidence.SqliteEvidenceJournal.open_v3(run.journal_path)
        try:
            second = await reopened.retrieve(
                EvidenceRetrievalRequest(
                    reopened.session_id,
                    1,
                    16384,
                    cursor=first.continuation,
                )
            )
            fresh = await reopened.retrieve(
                EvidenceRetrievalRequest(
                    EvidenceRangeReference(reopened.session_id, 2, 4),
                    1,
                    16384,
                )
            )
            assert fresh.continuation is not None
            final = await reopened.retrieve(
                EvidenceRetrievalRequest(
                    EvidenceRangeReference(reopened.session_id, 2, 4),
                    1,
                    16384,
                    cursor=fresh.continuation,
                )
            )
        finally:
            await reopened.close()

        assert second.records == (first_rx,)
        assert second.snapshot_end_exclusive == 2
        assert second.outcome is EvidencePageOutcome.COMPLETE
        assert not second.truncated
        assert second.continuation is None
        assert fresh.snapshot_end_exclusive == 4
        assert len(fresh.records) == 1
        assert isinstance(fresh.records[0], RxBytesEvidence)
        assert fresh.records[0].payload == b"later"
        assert isinstance(final.records[0], SegmentEndedEvidence)
        assert final.records[0].reason is SegmentEndReason.EXPLICIT_STOP
        assert final.continuation is None


@pytest.mark.asyncio
async def test_continuation_reports_rx_expired_during_active_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catch silently omitted expiry or a cursor accidentally following new RX.
    policy = replace(_POLICY, max_retained_records=2, max_retrieval_page_records=1)
    async with _run(
        tmp_path, monkeypatch, (b"first", b"second", b"third"), policy
    ) as run:
        await run.emit(0)
        first = await run.journal.retrieve(
            EvidenceRetrievalRequest(
                run.journal.session_id,
                1,
                16384,
            )
        )
        assert first.records == (run.start,)
        assert first.continuation is not None
        await run.emit(1)
        await run.emit(2)
        continued = await run.journal.retrieve(
            EvidenceRetrievalRequest(
                run.journal.session_id,
                1,
                16384,
                cursor=first.continuation,
            )
        )
        assert run.runtime.status().state is RuntimeState.ACTIVE
        assert continued.outcome is EvidencePageOutcome.EXPIRED
        assert continued.records == ()
        assert continued.snapshot_end_exclusive == 2
        assert continued.expired_range == SequenceRange(1, 2)
        assert continued.retention_marker is not None
        assert continued.retention_marker.expired_range == SequenceRange(0, 2)
        assert not continued.truncated
        assert continued.continuation is None


@pytest.mark.asyncio
async def test_reopen_preserves_policy_and_effective_provenance_without_full_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catch implicit durable DUT/Profile association or unrequested schema additions.
    async with _run(tmp_path, monkeypatch, ()) as run:
        profile = run.active.profile
        assert profile is not None
        run.profile_path.unlink()
        terminal = await run.runtime.detach()
        assert terminal.profile == profile  # Only the in-memory summary retains it.
        reopened = await sqlite_evidence.SqliteEvidenceJournal.open_v3(run.journal_path)
        try:
            page = await reopened.retrieve(
                EvidenceRetrievalRequest(
                    reopened.session_id,
                    11,
                    16384,
                )
            )
            assert reopened.session_id == run.active.session_id
            assert reopened.policy == profile.session_policy
        finally:
            await reopened.close()

        assert page.outcome is EvidencePageOutcome.COMPLETE
        assert isinstance(page.records[0], SegmentStartedEvidence)
        snapshot = page.records[0].provenance.connection_provenance.to_snapshot()
        assert snapshot == run.start.provenance.connection_provenance.to_snapshot()
        fields = {field.name: field.value for field in snapshot.fields}
        assert fields["effective_baud_rate"] == 19200
        assert fields["effective_data_bits"] == 7
        assert fields["effective_parity"] == "even"

        # Inspect all schema-v3 persisted values, including opaque JSON blobs;
        # nothing outside the bounded public readback can recover DUT identity,
        # display name, or the explicit source Profile path either.
        with closing(sqlite3.connect(run.journal_path)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone() == (3,)
            values = [
                value
                for table in (
                    "session_metadata",
                    "evidence_records",
                    "retention_marker",
                )
                for row in connection.execute(f"SELECT * FROM {table}")
                for value in row
            ]
        persisted = "\n".join(
            value.decode("utf-8") if isinstance(value, bytes) else str(value)
            for value in values
        )
        assert profile.dut.id not in persisted
        assert profile.dut.name not in persisted
        assert str(run.profile_path) not in persisted
        assert run.profile_path.name not in persisted


# T021: identical shared workflows on normalized fixtures, with real SQLite.
# The original six Basic composition cases above deliberately remain intact.
@pytest.fixture(params=BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced-shaped"))
def observation_fixture_factory(
    request: pytest.FixtureRequest,
) -> BackendFixtureFactory:
    return cast("BackendFixtureFactory", request.param)


async def _bounded[T](work: Awaitable[T]) -> T:
    # Test watchdog only; runtime cleanup still has no deadline/abandonment.
    async with asyncio.timeout(3.0):
        return await work


async def _checkpoint() -> None:
    marker = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(marker.set_result, None)
    await marker


class _NeutralRecorder:
    def __init__(self, run: _NeutralRun) -> None:
        self.run = run
        self.session_id = run.journal.session_id
        self.policy = run.journal.policy

    async def append(self, draft: PendingEvidenceRecord) -> EvidenceRecord:
        if isinstance(draft, PendingSegmentStartedEvidence):
            await self.run.segment_start.enter()
        elif isinstance(draft, PendingSegmentEndedEvidence):
            await self.run.segment_end.enter()
        elif isinstance(draft, PendingRxBytesEvidence) and self.run.reject_rx_append:
            raise JournalFailure(JournalOperation.APPEND, JournalFailureKind.IO_FAILURE)
        record = await self.run.journal.append(draft)
        self.run.trace.append(f"committed:{record.sequence}")
        self.run.commits.put_nowait(record)
        return record

    async def close(self) -> None:
        self.run.recorder_close_calls += 1
        self.run.trace.append("recorder.close_entered")
        await self.run.recorder_close.enter()
        await self.run.journal.close()
        self.run.trace.append("recorder.closed")


class _NeutralRun:
    def __init__(
        self,
        root: Path,
        factory: BackendFixtureFactory,
        policy: SessionPolicy = _POLICY,
    ) -> None:
        root.mkdir()
        self.profile_path = root / "explicit-profile.toml"
        self.profile_path.write_text(_profile_text(policy), encoding="utf-8")
        self.profile = resolve_profile(self.profile_path)
        self.destination = root / "observation.sqlite3"
        self.factory = factory
        self.fixture: BackendFixture | None = None
        self._journal: sqlite_evidence.SqliteEvidenceJournal | None = None
        self.prepared = asyncio.Event()
        self.open_gate = FixtureLifecycleGate()
        self.start_return = FixtureLifecycleGate()
        self.segment_start = FixtureLifecycleGate()
        self.segment_end = FixtureLifecycleGate()
        self.recorder_close = FixtureLifecycleGate()
        self.reject_receive = False
        self.reject_rx_append = False
        self.immediate_disconnect = False
        self.trace: list[str] = []
        self.commits: asyncio.Queue[EvidenceRecord] = asyncio.Queue()
        self.acquisitions: list[aq.Acquisition] = []
        self.tasks: list[asyncio.Task[RuntimeStatus]] = []
        self.prepare_calls = 0
        self.recorder_close_calls = 0

    @property
    def journal(self) -> sqlite_evidence.SqliteEvidenceJournal:
        assert self._journal is not None
        return self._journal

    @property
    def connection(self) -> ShapedBackendConnection:
        assert self.fixture is not None
        return self.fixture.connection

    @property
    def backend(self) -> BasicShapedBackend | EnhancedShapedBackend:
        assert self.fixture is not None
        backend = self.fixture.backend
        assert isinstance(backend, (BasicShapedBackend, EnhancedShapedBackend))
        return backend

    async def prepare(
        self, resolved: profile.ResolvedDutProfile
    ) -> rt.PreparedObservationRun:
        self.prepare_calls += 1
        assert resolved == self.profile
        self._journal = await sqlite_evidence.SqliteEvidenceJournal.create(
            self.destination, resolved.session_policy
        )
        self.trace.append("journal.created")
        self.fixture = self.factory()
        self.trace.append("backend.constructed")
        # Serialization belongs to this test composition edge. Timestamp/loss/
        # capability facts stay as reported; no Profile identity is persisted.
        self.connection.descriptor = replace(
            self.connection.descriptor,
            connection_provenance=model.PersistedConnectionProvenance(
                model.ConnectionProvenanceSnapshot(
                    envelope_version=1,
                    backend_kind="fixture/normalized-observation",
                    backend_schema_version=37,
                    fields=(model.ProvenanceField("transport", "simulated"),),
                )
            ),
        )
        if self.reject_receive:
            self.connection.descriptor = replace(
                self.connection.descriptor,
                capabilities=model.BackendCapabilities(frozenset()),
            )
        self.backend.open_gate = self.open_gate
        if self.immediate_disconnect:
            self.connection.event_gate.allow.clear()
            await self.connection.disconnect()
        self.prepared.set()
        return rt.PreparedObservationRun(_NeutralRecorder(self), self.fixture.backend)

    def attach(self, runtime: ObservationRuntime) -> asyncio.Task[RuntimeStatus]:
        task = asyncio.create_task(runtime.attach(self.profile, self.prepare))
        self.tasks.append(task)
        return task

    def detach(self, runtime: ObservationRuntime) -> asyncio.Task[RuntimeStatus]:
        task = asyncio.create_task(runtime.detach())
        self.tasks.append(task)
        return task

    async def commit(self, sequence: int) -> EvidenceRecord:
        record = await _bounded(self.commits.get())
        assert record.sequence == sequence
        return record


def _capture_neutral_acquisitions(monkeypatch: pytest.MonkeyPatch) -> None:
    class CapturedAcquisition(aq.Acquisition):
        def __init__(self, recorder: EvidenceRecorder) -> None:
            assert isinstance(recorder, _NeutralRecorder)
            super().__init__(recorder)
            self.run = recorder.run
            self.run.acquisitions.append(self)

        async def start(self, backend: Backend) -> model.ConnectionInstanceId:
            identity = await super().start(backend)
            await self.run.start_return.enter()
            return identity

    monkeypatch.setattr(rt, "Acquisition", CapturedAcquisition)


async def _neutral_cleanup(runtime: ObservationRuntime, *runs: _NeutralRun) -> None:
    for run in runs:
        for gate in (
            run.open_gate,
            run.start_return,
            run.segment_start,
            run.segment_end,
            run.recorder_close,
        ):
            gate.allow.set()
        if run.fixture is not None:
            for gate in (
                run.connection.read_gate,
                run.connection.event_gate,
                run.connection.consumer_exit_gate,
                run.connection.close_gate,
            ):
                gate.allow.set()
    try:
        await _bounded(runtime.detach())
        await _bounded(
            asyncio.gather(
                *(task for run in runs for task in run.tasks), return_exceptions=True
            )
        )
        for run in runs:
            for acquisition in run.acquisitions:
                await _bounded(acquisition.stop())
                await _bounded(acquisition.join_terminated())
    finally:
        for run in runs:
            if run._journal is not None:
                await _bounded(run.journal.close())


async def _neutral_active(
    runtime: ObservationRuntime,
    run: _NeutralRun,
    pending: asyncio.Task[RuntimeStatus] | None = None,
) -> tuple[RuntimeStatus, SegmentStartedEvidence]:
    active = await _bounded(pending if pending is not None else run.attach(runtime))
    start = await run.commit(0)
    assert isinstance(start, SegmentStartedEvidence)
    assert active.state is RuntimeState.ACTIVE and not active.owner_settled
    assert not active.attach_admissible
    assert active.profile == run.profile
    assert active.session_id == run.journal.session_id
    assert active.acquisition is not None
    assert active.acquisition.state is aq.AcquisitionState.ACQUIRING
    assert active.acquisition.descriptor == run.connection.descriptor
    assert active.acquisition.provenance == start.provenance
    assert active.primary_issue is None and active.cleanup_issues == ()
    assert not active.physical_release_confirmed and not active.recorder_close_confirmed
    assert (
        run.prepare_calls
        == run.backend.open_calls
        == run.connection.consumer_calls
        == 1
    )
    assert run.trace[:3] == ["journal.created", "backend.constructed", "committed:0"]
    return active, start


def _neutral_terminal(
    runtime: ObservationRuntime,
    run: _NeutralRun,
    result: RuntimeStatus,
    reason: rt.RuntimeTerminalReason = rt.RuntimeTerminalReason.DETACHED,
) -> None:
    assert result == runtime.status()
    assert result.state is RuntimeState.TERMINATED and result.owner_settled
    assert result.terminal_reason is reason
    assert result.attach_admissible
    assert result.physical_release_confirmed and result.recorder_close_confirmed
    assert result.primary_issue is None and result.cleanup_issues == ()
    assert result.profile == run.profile and result.session_id == run.journal.session_id
    assert result.acquisition is not None
    assert result.acquisition.state is aq.AcquisitionState.STOPPED
    assert result.acquisition.provenance is not None
    assert result.acquisition.descriptor == run.connection.descriptor
    assert (
        run.backend.open_calls
        == run.connection.close_calls
        == run.recorder_close_calls
        == 1
    )
    assert run.connection.consumer_calls == 1 and run.connection.closed
    assert run.trace[-1] == "recorder.closed"


async def _neutral_readback(
    run: _NeutralRun,
    expected_outcome: EvidencePageOutcome = EvidencePageOutcome.COMPLETE,
) -> tuple[EvidenceRecord, ...]:
    reopened = await sqlite_evidence.SqliteEvidenceJournal.open(
        run.destination, expected_session_id=run.journal.session_id
    )
    records: list[EvidenceRecord] = []
    try:
        assert reopened.policy == run.profile.session_policy
        policy = reopened.policy
        cursor = None
        while True:
            page = await reopened.retrieve(
                EvidenceRetrievalRequest(
                    reopened.session_id,
                    policy.max_retrieval_page_records,
                    policy.max_retrieval_page_charged_bytes,
                    cursor=cursor,
                )
            )
            assert page.outcome is expected_outcome
            assert len(page.records) <= policy.max_retrieval_page_records
            assert page.charged_bytes <= policy.max_retrieval_page_charged_bytes
            records.extend(page.records)
            if page.continuation is None:
                assert not page.truncated
                break
            assert page.truncated
            cursor = page.continuation
    finally:
        await reopened.close()
    # Feature-003 schema-v1 compatibility, including no implicit Profile column.
    with closing(sqlite3.connect(run.destination)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute(
            "SELECT schema_version FROM session_metadata"
        ).fetchone() == (1,)
        assert {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        } == {"session_metadata", "evidence_records", "retention_marker"}
        metadata_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(session_metadata)")
        }
        assert metadata_columns == {
            "singleton",
            "session_id",
            "schema_version",
            "max_retained_records",
            "max_retained_charged_bytes",
            "max_record_charged_bytes",
            "max_database_pages",
            "max_retrieval_page_records",
            "max_retrieval_page_charged_bytes",
            "next_sequence",
            "low_water_sequence",
            "retained_record_count",
            "retained_charged_bytes",
        }
        for table, columns in {
            "evidence_records": {
                "sequence",
                "record_kind",
                "record_version",
                "metadata_json",
                "payload",
                "charged_bytes",
                "rx_payload_bytes",
                "timestamp_endpoint_json",
            },
            "retention_marker": {
                "singleton",
                "expired_start_sequence",
                "expired_end_sequence",
                "first_timestamp_json",
                "last_timestamp_json",
                "discarded_record_count",
                "discarded_rx_payload_byte_count",
                "discarded_charged_bytes",
            },
        }.items():
            assert {
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            } == columns
        values = [
            value
            for table in ("session_metadata", "evidence_records", "retention_marker")
            for row in connection.execute(f"SELECT * FROM {table}")
            for value in row
        ]
    persisted = b"\n".join(
        value if isinstance(value, bytes) else str(value).encode("utf-8")
        for value in values
    )
    assert run.profile.dut.id.encode("utf-8") not in persisted
    assert run.profile.dut.name.encode("utf-8") not in persisted
    assert str(run.profile_path).encode("utf-8") not in persisted
    return tuple(records)


@pytest.mark.asyncio
async def test_t021_binary_ambient_capture_preserves_reported_provenance_and_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_fixture_factory: BackendFixtureFactory,
) -> None:
    # Catch timestamp coercion, dropped/transformed ambient chunks, or early close.
    runtime = ObservationRuntime()
    run = _NeutralRun(tmp_path / "run", observation_fixture_factory)
    run.open_gate.allow.clear()
    _capture_neutral_acquisitions(monkeypatch)
    payloads = (bytes(range(256)) + b"\x00\xff", b"ambient\r\n\x80\x00")
    try:
        attach = run.attach(runtime)
        await _bounded(run.open_gate.entered.wait())
        waiting = runtime.status()
        assert waiting.state is RuntimeState.ATTACHING and not waiting.owner_settled
        assert (
            waiting.profile == run.profile
            and waiting.session_id == run.journal.session_id
        )
        assert waiting.acquisition is not None
        assert (
            waiting.acquisition.descriptor is None
            and waiting.acquisition.provenance is None
        )
        assert (
            not waiting.physical_release_confirmed
            and not waiting.recorder_close_confirmed
        )
        assert not waiting.attach_admissible
        with pytest.raises(rt.RuntimeRejectedError) as busy:
            await runtime.attach(run.profile, run.prepare)
        assert busy.value.kind is rt.RuntimeRejectedKind.BUSY
        assert run.prepare_calls == 1 and runtime.status() == waiting
        run.open_gate.allow.set()
        active, start = await _neutral_active(runtime, run, attach)
        with pytest.raises(rt.RuntimeRejectedError) as busy:
            await runtime.attach(run.profile, run.prepare)
        assert busy.value.kind is rt.RuntimeRejectedKind.BUSY
        assert run.prepare_calls == 1 and runtime.status() == active
        accepted: list[EvidenceRecord] = [start]
        domain = start.provenance.backend_observation_timestamp_domain
        for sequence, payload in enumerate(payloads, start=1):
            await run.connection.emit_rx(payload, timestamp=sequence * 10)
            record = await run.commit(sequence)
            assert isinstance(record, RxBytesEvidence)
            assert record.payload == payload
            assert record.observed_at == model.BackendObservationTimestamp(
                domain.domain_id, sequence * 10
            )
            accepted.append(record)
        terminal = await _bounded(runtime.detach())
        end = await run.commit(3)
        assert isinstance(end, SegmentEndedEvidence)
        assert end.reason is SegmentEndReason.EXPLICIT_STOP
        _neutral_terminal(runtime, run, terminal)
        assert terminal.acquisition is not None
        assert terminal.acquisition.provenance == start.provenance
        assert terminal.run_id == active.run_id
        assert (
            terminal.acquisition.terminal_trigger
            is aq.AcquisitionTerminalTrigger.EXPLICIT_STOP
        )
        assert run.trace.index("committed:3") < run.trace.index(
            "recorder.close_entered"
        )
        records = await _neutral_readback(run)
        assert records == (*accepted, end)
        assert [record.sequence for record in records] == [0, 1, 2, 3]
        assert all(
            isinstance(
                record,
                (
                    SegmentStartedEvidence,
                    RxBytesEvidence,
                    model.ObserverLossEvidence,
                    SegmentEndedEvidence,
                ),
            )
            and record.connection_id == start.connection_id
            and record.segment_id == start.segment_id
            for record in records
        )
        assert isinstance(records[0], SegmentStartedEvidence)
        envelope = records[0].provenance.connection_provenance.to_snapshot()
        assert (envelope.envelope_version, envelope.backend_schema_version) == (1, 37)
        assert envelope.fields == (model.ProvenanceField("transport", "simulated"),)
    finally:
        await _neutral_cleanup(runtime, run)


@pytest.mark.asyncio
async def test_t021_origin_reset_publishes_only_committed_segment_and_allows_new_clock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_fixture_factory: BackendFixtureFactory,
) -> None:
    # Catch candidate-provenance publication or comparing across reset origins.
    runtime = ObservationRuntime()
    run = _NeutralRun(tmp_path / "run", observation_fixture_factory)
    _capture_neutral_acquisitions(monkeypatch)
    try:
        _, start = await _neutral_active(runtime, run)
        await run.connection.emit_rx(b"before", timestamp=900)
        before = await run.commit(1)
        domain = start.provenance.backend_observation_timestamp_domain
        reset_domain = replace(
            domain, domain_id="reset-domain", origin_id="reset-origin"
        )
        run.segment_start.entered.clear()
        run.segment_start.allow.clear()
        await run.connection.reset_timestamp_origin(reset_domain)
        boundary = await run.commit(2)
        assert isinstance(boundary, SegmentEndedEvidence)
        assert boundary.reason is SegmentEndReason.TIMESTAMP_ORIGIN_RESET
        await _bounded(run.segment_start.entered.wait())
        waiting = runtime.status()
        assert waiting.state is RuntimeState.ACTIVE and waiting.acquisition is not None
        assert waiting.acquisition.provenance == start.provenance
        run.segment_start.allow.set()
        reset = await run.commit(3)
        assert isinstance(reset, SegmentStartedEvidence)
        current = runtime.status().acquisition
        assert current is not None and current.provenance == reset.provenance
        assert (
            reset.connection_id == start.connection_id
            and reset.segment_id != start.segment_id
        )
        assert reset.provenance.backend_observation_timestamp_domain == reset_domain
        assert reset.provenance.capabilities == start.provenance.capabilities
        assert (
            reset.provenance.loss_observability == start.provenance.loss_observability
        )
        await run.connection.emit_rx(b"after\x00\xff", timestamp=1)
        after = await run.commit(4)
        assert isinstance(after, RxBytesEvidence)
        assert after.segment_id == reset.segment_id
        assert after.observed_at == model.BackendObservationTimestamp("reset-domain", 1)
        terminal = await _bounded(runtime.detach())
        end = await run.commit(5)
        _neutral_terminal(runtime, run, terminal)
        assert terminal.acquisition is not None
        assert terminal.acquisition.provenance == reset.provenance
        assert await _neutral_readback(run) == (
            start,
            before,
            boundary,
            reset,
            after,
            end,
        )
    finally:
        await _neutral_cleanup(runtime, run)


@pytest.mark.asyncio
async def test_t021_loss_readback_follows_reported_scope_without_emulation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_fixture_factory: BackendFixtureFactory,
) -> None:
    # Catch unobservable-loss assumptions or widening an observer's loss claim.
    runtime = ObservationRuntime()
    run = _NeutralRun(tmp_path / "run", observation_fixture_factory)
    _capture_neutral_acquisitions(monkeypatch)
    try:
        _, start = await _neutral_active(runtime, run)
        reported = start.provenance.loss_observability
        accepted: list[EvidenceRecord] = [start]
        if isinstance(reported, model.ObserverReportsUartLoss):
            # Fixture event emission only; shared runtime sees normalized facts.
            assert isinstance(run.connection, EnhancedShapedBackendConnection)
            await run.connection.emit_observer_loss(
                cause="overflow", lost_bytes=7, timestamp=10
            )
            loss = await run.commit(1)
            assert isinstance(loss, model.ObserverLossEvidence)
            assert loss.observer_id == reported.observer_id
            assert loss.scope == reported.scope
            assert (
                loss.cause == model.ObserverLossCause("overflow")
                and loss.lost_bytes == 7
            )
            assert (
                loss.observed_at.domain_id
                == start.provenance.backend_observation_timestamp_domain.domain_id
            )
            accepted.append(loss)
        else:
            assert isinstance(reported, model.UpstreamLossNotObservable)
        await run.connection.emit_rx(b"ambient-after-loss\x00", timestamp=20)
        accepted.append(await run.commit(len(accepted)))
        terminal = await _bounded(runtime.detach())
        end = await run.commit(len(accepted))
        _neutral_terminal(runtime, run, terminal)
        records = await _neutral_readback(run)
        assert records == (*accepted, end)
        losses = [
            record
            for record in records
            if isinstance(record, model.ObserverLossEvidence)
        ]
        assert len(losses) == (
            1 if isinstance(reported, model.ObserverReportsUartLoss) else 0
        )
        assert isinstance(records[0], SegmentStartedEvidence)
        assert records[0].provenance.loss_observability == reported
    finally:
        await _neutral_cleanup(runtime, run)


@pytest.mark.asyncio
async def test_t021_missing_rx_rejects_before_reader_or_segment_and_retains_empty_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_fixture_factory: BackendFixtureFactory,
) -> None:
    # Catch a fixed capability assumption or fabricated committed identities.
    runtime = ObservationRuntime()
    run = _NeutralRun(tmp_path / "run", observation_fixture_factory)
    run.reject_receive = True
    _capture_neutral_acquisitions(monkeypatch)
    try:
        result = await _bounded(run.attach(runtime))
        assert result.state is RuntimeState.FAILED and result.owner_settled
        assert result.terminal_reason is rt.RuntimeTerminalReason.STARTUP_FAILURE
        assert result.primary_issue == rt.RuntimeIssue(
            rt.RuntimeIssueSource.ACQUISITION_START,
            aq.AcquisitionFailureKind.CAPABILITY_REJECTION,
        )
        assert result.cleanup_issues == () and result.attach_admissible
        assert result.physical_release_confirmed and result.recorder_close_confirmed
        assert (
            result.session_id == run.journal.session_id
            and result.profile == run.profile
        )
        assert result.acquisition is not None
        assert result.acquisition.descriptor == run.connection.descriptor
        assert result.acquisition.provenance is None
        assert (
            result.acquisition.terminal_trigger
            is aq.AcquisitionTerminalTrigger.CAPABILITY_REJECTION
        )
        assert not run.connection.descriptor.capabilities.supports(
            model.BackendCapability.UART_RECEIVE
        )
        assert (
            run.backend.open_calls
            == run.connection.close_calls
            == run.recorder_close_calls
            == 1
        )
        assert run.connection.consumer_calls == 0 and run.commits.empty()
        assert run.destination.is_file() and await _neutral_readback(run) == ()
        assert await _bounded(runtime.detach()) == result
    finally:
        await _neutral_cleanup(runtime, run)


@pytest.mark.asyncio
async def test_t021_cleanup_waits_physical_close_and_consumer_before_recorder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_fixture_factory: BackendFixtureFactory,
) -> None:
    # Catch recorder close or attach admission before actual reader/close joining.
    runtime = ObservationRuntime()
    run = _NeutralRun(tmp_path / "run", observation_fixture_factory)
    _capture_neutral_acquisitions(monkeypatch)
    try:
        _, start = await _neutral_active(runtime, run)
        run.connection.close_gate.allow.clear()
        run.connection.consumer_exit_gate.allow.clear()
        run.recorder_close.allow.clear()
        detach = run.detach(runtime)
        await _bounded(run.connection.close_gate.entered.wait())
        closing = runtime.status()
        assert closing.state is RuntimeState.DETACHING and not closing.owner_settled
        assert not closing.attach_admissible and not closing.physical_release_confirmed
        assert run.recorder_close_calls == 0 and not detach.done()
        run.connection.close_gate.allow.set()
        await _bounded(run.connection.consumer_exit_gate.entered.wait())
        await _checkpoint()
        draining = runtime.status()
        assert draining.state is RuntimeState.DETACHING and not draining.owner_settled
        assert (
            draining.physical_release_confirmed
            and not draining.recorder_close_confirmed
        )
        assert run.recorder_close_calls == 0 and not detach.done()
        run.connection.consumer_exit_gate.allow.set()
        end = await run.commit(1)
        assert isinstance(end, SegmentEndedEvidence)
        await _bounded(run.recorder_close.entered.wait())
        assert runtime.status().state is RuntimeState.DETACHING
        assert (
            not runtime.status().owner_settled
            and not runtime.status().attach_admissible
        )
        assert not detach.done()
        assert run.trace.index("committed:1") < run.trace.index(
            "recorder.close_entered"
        )
        run.recorder_close.allow.set()
        result = await _bounded(detach)
        _neutral_terminal(runtime, run, result)
        assert await _neutral_readback(run) == (start, end)
    finally:
        await _neutral_cleanup(runtime, run)


@pytest.mark.asyncio
async def test_t021_fresh_explicit_run_keeps_prior_status_historical_and_profile_in_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_fixture_factory: BackendFixtureFactory,
) -> None:
    # Catch journal reuse, automatic reopen, or durable full-Profile association.
    runtime = ObservationRuntime()
    first = _NeutralRun(tmp_path / "first", observation_fixture_factory)
    second = _NeutralRun(tmp_path / "second", observation_fixture_factory)
    _capture_neutral_acquisitions(monkeypatch)
    try:
        _, old_start = await _neutral_active(runtime, first)
        first.profile_path.unlink()
        old_result = await _bounded(runtime.detach())
        old_end = await first.commit(1)
        _neutral_terminal(runtime, first, old_result)
        assert old_result.acquisition is not None
        assert old_result.acquisition.provenance == old_start.provenance
        assert await _bounded(runtime.detach()) == old_result
        assert second.prepare_calls == 0 and not second.destination.exists()
        active, new_start = await _neutral_active(runtime, second)
        assert (
            active.run_id != old_result.run_id
            and active.session_id != old_result.session_id
        )
        assert new_start.connection_id != old_start.connection_id
        assert new_start.segment_id != old_start.segment_id and new_start.sequence == 0
        assert active.profile == old_result.profile == first.profile == second.profile
        historical = await _bounded(first.acquisitions[0].join_terminated())
        assert historical == old_result.acquisition
        await _checkpoint()
        assert runtime.status() == active
        assert await _neutral_readback(first) == (old_start, old_end)
        assert runtime.status() == active and first.backend.open_calls == 1
        new_result = await _bounded(runtime.detach())
        new_end = await second.commit(1)
        _neutral_terminal(runtime, second, new_result)
        assert await _neutral_readback(second) == (new_start, new_end)
        assert old_result.acquisition == historical
        assert first.recorder_close_calls == 1
    finally:
        await _neutral_cleanup(runtime, first, second)


@pytest.mark.asyncio
async def test_t021_bounded_pages_keep_original_snapshot_across_ambient_rx_and_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_fixture_factory: BackendFixtureFactory,
) -> None:
    # Catch runtime composition adding live-follow semantics to fixed cursors.
    runtime = ObservationRuntime()
    policy = replace(_POLICY, max_retrieval_page_records=1)
    run = _NeutralRun(tmp_path / "run", observation_fixture_factory, policy)
    _capture_neutral_acquisitions(monkeypatch)
    try:
        _, start = await _neutral_active(runtime, run)
        await run.connection.emit_rx(b"first\x00\xff", timestamp=1)
        first_rx = await run.commit(1)
        page = await run.journal.retrieve(
            EvidenceRetrievalRequest(run.journal.session_id, 1, 16384)
        )
        assert page.records == (start,) and page.snapshot_end_exclusive == 2
        assert page.truncated and page.continuation is not None
        await run.connection.emit_rx(b"later ambient", timestamp=2)
        later = await run.commit(2)
        terminal = await _bounded(runtime.detach())
        end = await run.commit(3)
        _neutral_terminal(runtime, run, terminal)
        reopened = await sqlite_evidence.SqliteEvidenceJournal.open(run.destination)
        try:
            continued = await reopened.retrieve(
                EvidenceRetrievalRequest(
                    reopened.session_id, 1, 16384, cursor=page.continuation
                )
            )
        finally:
            await reopened.close()
        assert continued.outcome is EvidencePageOutcome.COMPLETE
        assert continued.records == (first_rx,)
        assert continued.snapshot_end_exclusive == 2
        assert not continued.truncated and continued.continuation is None
        assert await _neutral_readback(run) == (start, first_rx, later, end)
    finally:
        await _neutral_cleanup(runtime, run)


@pytest.mark.asyncio
async def test_t021_rolling_retention_reports_expiry_with_original_timestamp_domain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_fixture_factory: BackendFixtureFactory,
) -> None:
    # Catch silent expiry or host-domain substitution in retention provenance.
    runtime = ObservationRuntime()
    policy = replace(_POLICY, max_retained_records=3)
    run = _NeutralRun(tmp_path / "run", observation_fixture_factory, policy)
    _capture_neutral_acquisitions(monkeypatch)
    try:
        _, start = await _neutral_active(runtime, run)
        chunks: list[EvidenceRecord] = []
        for sequence, payload in enumerate((b"first", b"second", b"third"), start=1):
            await run.connection.emit_rx(payload, timestamp=sequence * 10)
            chunks.append(await run.commit(sequence))
        terminal = await _bounded(runtime.detach())
        end = await run.commit(4)
        _neutral_terminal(runtime, run, terminal)
        reopened = await sqlite_evidence.SqliteEvidenceJournal.open(run.destination)
        try:
            assert reopened.policy == policy
            partial = await reopened.retrieve(
                EvidenceRetrievalRequest(
                    EvidenceRangeReference(reopened.session_id, 0, 5), 11, 16384
                )
            )
            expired = await reopened.retrieve(
                EvidenceRetrievalRequest(
                    EvidenceRangeReference(reopened.session_id, 0, 2), 11, 16384
                )
            )
        finally:
            await reopened.close()
        assert partial.outcome is EvidencePageOutcome.PARTIAL
        assert partial.expired_range == SequenceRange(0, 2)
        assert partial.records == (*chunks[1:], end)
        assert partial.never_existed_range is None
        assert expired.outcome is EvidencePageOutcome.EXPIRED and expired.records == ()
        assert expired.expired_range == SequenceRange(0, 2)
        marker = partial.retention_marker
        assert marker is not None and expired.retention_marker == marker
        assert marker.discarded_record_count == 2
        assert marker.discarded_rx_payload_byte_count == 5
        assert marker.first_discarded_timestamp is not None
        assert marker.last_discarded_timestamp is not None
        assert (
            marker.first_discarded_timestamp.domain
            == start.provenance.backend_observation_timestamp_domain
        )
        assert (
            marker.last_discarded_timestamp.timestamp
            == model.BackendObservationTimestamp(
                start.provenance.backend_observation_timestamp_domain.domain_id, 10
            )
        )
        assert await _neutral_readback(run, EvidencePageOutcome.PARTIAL) == (
            *chunks[1:],
            end,
        )
    finally:
        await _neutral_cleanup(runtime, run)


async def _neutral_settled(runtime: ObservationRuntime) -> RuntimeStatus:
    async with asyncio.timeout(3.0):
        while not runtime.status().owner_settled:
            await _checkpoint()
    return runtime.status()


@pytest.mark.asyncio
async def test_t021_active_disconnect_autonomously_closes_and_retains_normalized_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_fixture_factory: BackendFixtureFactory,
) -> None:
    # Catch an explicit-stop-only owner or serial-only disconnect interpretation.
    runtime = ObservationRuntime()
    run = _NeutralRun(tmp_path / "run", observation_fixture_factory)
    run.recorder_close.allow.clear()
    _capture_neutral_acquisitions(monkeypatch)
    try:
        _, start = await _neutral_active(runtime, run)
        await run.connection.emit_rx(b"ambient before disconnect\x00", timestamp=1)
        rx = await run.commit(1)
        await run.connection.disconnect()
        end = await run.commit(2)
        assert isinstance(end, SegmentEndedEvidence)
        assert end.reason is SegmentEndReason.DISCONNECTED
        await _bounded(run.acquisitions[0].wait_terminated())
        await _checkpoint()
        draining = runtime.status()
        assert draining.state is RuntimeState.DETACHING
        assert not draining.owner_settled and not draining.attach_admissible
        assert draining.stop_intent is rt.RuntimeStopIntent.NONE
        assert draining.acquisition is not None
        assert (
            draining.acquisition.terminal_trigger
            is aq.AcquisitionTerminalTrigger.DISCONNECTED
        )
        await _bounded(run.recorder_close.entered.wait())
        run.recorder_close.allow.set()
        terminal = await _neutral_settled(runtime)
        _neutral_terminal(runtime, run, terminal, rt.RuntimeTerminalReason.DISCONNECTED)
        assert terminal.acquisition is not None
        assert terminal.acquisition.provenance == start.provenance
        assert run.trace.index("committed:2") < run.trace.index(
            "recorder.close_entered"
        )
        assert await _neutral_readback(run) == (start, rx, end)
        assert await _bounded(runtime.detach()) == terminal
        await _checkpoint()
        assert runtime.status() == terminal and run.backend.open_calls == 1
    finally:
        await _neutral_cleanup(runtime, run)


@pytest.mark.asyncio
async def test_t021_disconnect_before_start_delivery_returns_historical_terminal_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_fixture_factory: BackendFixtureFactory,
) -> None:
    # Catch active publication after the one authoritative reader already ended.
    runtime = ObservationRuntime()
    run = _NeutralRun(tmp_path / "run", observation_fixture_factory)
    run.immediate_disconnect = True
    run.start_return.allow.clear()
    _capture_neutral_acquisitions(monkeypatch)
    try:
        attach = run.attach(runtime)
        await _bounded(run.start_return.entered.wait())
        start = await run.commit(0)
        assert isinstance(start, SegmentStartedEvidence)
        await _bounded(run.connection.event_gate.entered.wait())
        waiting = runtime.status()
        assert (
            waiting.state is RuntimeState.ATTACHING and waiting.acquisition is not None
        )
        assert waiting.acquisition.terminal_trigger is None
        assert waiting.acquisition.provenance == start.provenance
        run.connection.event_gate.allow.set()
        end = await run.commit(1)
        assert (
            isinstance(end, SegmentEndedEvidence)
            and end.reason is SegmentEndReason.DISCONNECTED
        )
        historical = await _bounded(run.acquisitions[0].join_terminated())
        run.start_return.allow.set()
        result = await _bounded(attach)
        _neutral_terminal(runtime, run, result, rt.RuntimeTerminalReason.DISCONNECTED)
        assert result.acquisition == historical
        assert result.stop_intent is rt.RuntimeStopIntent.NONE
        assert await _neutral_readback(run) == (start, end)
    finally:
        await _neutral_cleanup(runtime, run)


@pytest.mark.parametrize("cause", ["rx_recording", "transport"])
@pytest.mark.asyncio
async def test_t021_active_failure_autonomously_drains_without_fabricated_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observation_fixture_factory: BackendFixtureFactory,
    cause: str,
) -> None:
    # Catch missing autonomous failure cleanup or an inferred/fabricated end.
    runtime = ObservationRuntime()
    run = _NeutralRun(tmp_path / "run", observation_fixture_factory)
    run.recorder_close.allow.clear()
    _capture_neutral_acquisitions(monkeypatch)
    primary = (
        aq.AcquisitionFailureKind.RECORDING_FAILURE
        if cause == "rx_recording"
        else aq.AcquisitionFailureKind.TRANSPORT_FAILURE
    )
    try:
        _, start = await _neutral_active(runtime, run)
        run.reject_rx_append = cause == "rx_recording"
        if cause == "rx_recording":
            await run.connection.emit_rx(b"rejected\x00\xff", timestamp=1)
        else:
            await run.connection.end_stream_unexpectedly()
        await _bounded(run.acquisitions[0].wait_terminated())
        observed = await _bounded(run.acquisitions[0].join_terminated())
        assert observed.primary_failure_kind is primary and not observed.close_failed
        await _checkpoint()
        assert runtime.status().state is RuntimeState.DETACHING
        assert not runtime.status().owner_settled
        await _bounded(run.recorder_close.entered.wait())
        run.recorder_close.allow.set()
        result = await _neutral_settled(runtime)
        assert result.state is RuntimeState.FAILED and result.owner_settled
        assert result.terminal_reason is rt.RuntimeTerminalReason.ACQUISITION_FAILURE
        assert result.stop_intent is rt.RuntimeStopIntent.NONE
        assert result.primary_issue == rt.RuntimeIssue(
            rt.RuntimeIssueSource.ACQUISITION, primary
        )
        assert result.cleanup_issues == () and result.attach_admissible
        assert (
            result.acquisition == observed and observed.provenance == start.provenance
        )
        assert result.physical_release_confirmed and result.recorder_close_confirmed
        records = await _neutral_readback(run)
        if cause == "rx_recording":
            assert records == (start,)  # Rejected append and end are not committed.
        else:
            end = await run.commit(1)
            assert isinstance(end, SegmentEndedEvidence)
            assert end.reason is SegmentEndReason.TRANSPORT_FAILURE
            assert records == (start, end)
        assert (
            run.backend.open_calls
            == run.connection.close_calls
            == run.recorder_close_calls
            == 1
        )
        assert run.connection.consumer_calls == 1
        assert await _bounded(runtime.detach()) == result
    finally:
        await _neutral_cleanup(runtime, run)
