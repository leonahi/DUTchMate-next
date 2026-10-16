"""009 Monitor integration over actual acquisition and a temporary v2 journal.

T009/T010 use the coordinator seam; T011 exercises public runtime admission/lifetime.
Only backend/clock infrastructure is simulated. Acquisition, persistence, active
read association and post-close terminal retrieval are the existing real code.
"""

import asyncio
import sqlite3
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NoReturn, cast

import pytest

from dutchmate_core import evidence, model
from dutchmate_core import runtime as rt
from dutchmate_core.adapters import observation_runtime, sqlite_evidence
from dutchmate_core.adapters.terminal_evidence import (
    capture_terminal_target,
    open_terminal_reader,
)
from dutchmate_core.evidence_access import OwnedEvidenceReadPort, PreparedEvidenceAccess
from dutchmate_core.monitor import MonitorClock, MonitorReport, MonitorRequest
from tests.contract.test_monitor_journal import _provenance, _start
from tests.contract.test_monitor_recording import (
    CoordinatorPort,
    ManualClock,
    OperationPort,
    _await,
    _required,
    _turn,
)
from tests.contract.test_monitor_runtime import _monitor_entry
from tests.contract.test_observation_composition import _PROFILE, AdmissionProbe
from tests.contract.test_observation_runtime import _profile
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixture, BackendFixtureFactory


def _durable_fixture(factory: BackendFixtureFactory) -> BackendFixture:
    fixture = factory()
    # Shared fixtures intentionally default to opaque in-memory provenance. Supply
    # only their test-owned durable envelope, retaining all normalized shape facts.
    fixture.connection.descriptor = replace(
        fixture.connection.descriptor,
        connection_provenance=model.PersistedConnectionProvenance(
            model.ConnectionProvenanceSnapshot(
                envelope_version=1,
                backend_kind="fixture/monitor",
                backend_schema_version=1,
                fields=(model.ProvenanceField("transport", "simulated"),),
            )
        ),
    )
    return fixture


@dataclass
class LiveCase:
    runtime: rt.ObservationRuntime
    active: rt.RuntimeStatus
    fixture: BackendFixture
    journal: sqlite_evidence.SqliteEvidenceJournal
    coordinator: CoordinatorPort
    clock: ManualClock
    rx_commits: asyncio.Queue[model.RxBytesEvidence]
    writer_closed: asyncio.Event
    terminal_opened: asyncio.Event

    async def emit(self, payload: bytes, timestamp: int = 123) -> model.RxBytesEvidence:
        await self.fixture.connection.emit_rx(payload, timestamp=timestamp)
        return await _await(self.rx_commits.get())

    async def start(self, condition: bytes) -> OperationPort:
        provenance = self.coordinator.current_provenance
        assert provenance is not None
        assert self.active.run_id is not None
        return await _await(
            self.coordinator.start(
                MonitorRequest(self.journal.session_id, condition, 1000, 1024),
                run_id=self.active.run_id.value,
                expected_provenance=provenance,
                revalidate=lambda: None,  # Runtime admission belongs to T011/T012.
                charge_markers=sqlite_evidence.charge_monitor_markers,
            )
        )

    async def page(self) -> tuple[model.EvidenceRecord, ...]:
        result = await _await(
            self.runtime.read_page(
                evidence.EvidenceRetrievalRequest(self.journal.session_id, 10, 16384)
            )
        )
        assert result.run_id == self.active.run_id
        assert result.page.outcome is evidence.EvidencePageOutcome.COMPLETE
        assert not result.page.truncated
        return result.page.records


@asynccontextmanager
async def _live(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    *,
    runtime_support: bool = False,
    runtime: rt.ObservationRuntime | None = None,
    retained: int = 100,
) -> AsyncIterator[LiveCase]:
    profile = _profile()
    if retained != 100:
        profile = replace(
            profile,
            session_policy=replace(
                profile.session_policy, max_retained_records=retained
            ),
        )
    path = tmp_path / "monitor.sqlite3"
    # Create real v2 storage even while the coordinator is absent in RED.
    journal = await sqlite_evidence.SqliteEvidenceJournal.create_v2(
        path, profile.session_policy
    )
    owner: rt.ObservationRuntime | None = None
    writer_closed, terminal_opened = asyncio.Event(), asyncio.Event()
    original_close = journal.close

    async def close() -> None:
        await original_close()
        writer_closed.set()  # Positive close acknowledgement, not submission.

    monkeypatch.setattr(journal, "close", close)
    try:
        target = capture_terminal_target(
            path,
            session_id=journal.session_id,
            policy=journal.policy,
            expected_schema_version=2,
        )

        assert target is not None

        async def terminal_opener() -> OwnedEvidenceReadPort:
            assert writer_closed.is_set(), "terminal open preceded writer close ACK"
            terminal_opened.set()
            return await open_terminal_reader(target)

        clock, fixture = ManualClock(), _durable_fixture(factory)
        coordinator = cast(
            CoordinatorPort,
            _required("MonitorRecordingCoordinator")(recorder=journal, clock=clock),
        )
        rx_commits: asyncio.Queue[model.RxBytesEvidence] = asyncio.Queue()
        original_append = journal.append

        async def append(draft: evidence.PendingEvidenceRecord) -> model.EvidenceRecord:
            record = await original_append(draft)
            if isinstance(record, model.RxBytesEvidence):
                # A test notification after real commit; no matching/publication logic.
                rx_commits.put_nowait(record)
            return record

        monkeypatch.setattr(journal, "append", append)

        async def prepare(_selected: object) -> rt.PreparedObservationRun:
            # Preserve the old constructor; actual new composition is tested below.
            prepared = rt.PreparedObservationRun(
                recorder=coordinator,
                backend=fixture.backend,
                evidence_access=PreparedEvidenceAccess(
                    journal.session_id, journal.policy, journal, terminal_opener
                ),
            )
            if runtime_support:
                prepared = replace(
                    prepared,
                    monitor_access=_required("PreparedMonitorAccess")(
                        session_id=journal.session_id,
                        policy=journal.policy,
                        coordinator=coordinator,
                        clock=clock,
                        charge_markers=sqlite_evidence.charge_monitor_markers,
                    ),
                )
            return prepared

        owner = rt.ObservationRuntime() if runtime is None else runtime
        active = await _await(owner.attach(profile, prepare))
        assert active.state is rt.RuntimeState.ACTIVE
        yield LiveCase(
            owner,
            active,
            fixture,
            journal,
            coordinator,
            clock,
            rx_commits,
            writer_closed,
            terminal_opened,
        )
    finally:
        if owner is not None:
            await _await(owner.detach())
        if not writer_closed.is_set():
            await _await(journal.close())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize(
    ("condition", "first", "second", "offset", "end_offset", "examined"),
    (
        (b"\0\xffABA", b"noise\0\xffA", b"BAtrail\x80", 5, 2, 10),
        (b"ababa\0\xff", b"xxabab", b"aba\0\xffTAIL", 4, 5, 11),
    ),
    ids=("binary-span", "overlapping-prefix"),
)
async def test_literal_match_uses_original_chunk_positions_and_keeps_whole_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    condition: bytes,
    first: bytes,
    second: bytes,
    offset: int,
    end_offset: int,
    examined: int,
) -> None:
    async with _live(tmp_path, monkeypatch, factory) as case:
        operation = await case.start(condition)
        first_rx = await case.emit(first, 17)
        second_rx = await case.emit(second, 901)
        report = await _await(operation.wait())
        assert report.outcome is model.MonitorOutcome.MATCHED
        assert report.match == model.MonitorMatch(
            model.MonitorMatchStart(2, offset), model.MonitorMatchEnd(3, end_offset)
        )
        assert report.examined_rx_bytes == examined
        assert report.window == model.SequenceRange(2, 4)
        assert report.clock == model.MonitorClockFacts(
            case.clock.origin_id, 100, 1000000100, 100
        )
        records = await case.page()
        assert isinstance(records[0], model.SegmentStartedEvidence)
        assert report.provenance == records[0].provenance
        assert (first_rx.sequence, second_rx.sequence) == (2, 3)
        assert records[2:4] == (first_rx, second_rx)
        assert (first_rx.payload, second_rx.payload) == (first, second)
        assert (first_rx.observed_at.value, second_rx.observed_at.value) == (17, 901)
        assert isinstance(records[1], model.OperationStartedEvidence)
        assert isinstance(records[4], model.OperationEndedEvidence)
        assert records[1].condition == condition
        assert records[4].match == report.match
        assert records[4].window == report.window
        assert report.durability == "complete" and report.end_failure is None
        assert report.started_record == model.EvidenceReference(
            case.journal.session_id, 1
        )
        assert report.ended_record == model.EvidenceReference(
            case.journal.session_id, 4
        )
        assert case.fixture.connection.consumer_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
async def test_ambient_evidence_before_and_after_monitor_uses_one_continuous_rx_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with _live(tmp_path, monkeypatch, factory) as case:
        before = await case.emit(b"\0\xffPASS before")
        operation = await case.start(b"\0\xffPASS")
        during = await case.emit(b"\0\xffPASS trailing")
        report = await _await(operation.wait())
        after = await case.emit(b"ambient after\x80\0")
        records = await case.page()
        assert [r for r in records if isinstance(r, model.RxBytesEvidence)] == [
            before,
            during,
            after,
        ]
        assert report.started_record.sequence == 2
        assert report.window == model.SequenceRange(3, 4)
        assert report.match == model.MonitorMatch(
            model.MonitorMatchStart(3, 0), model.MonitorMatchEnd(3, 6)
        )
        assert report.examined_rx_bytes == 6 and after.sequence == 5
        assert case.runtime.status().state is rt.RuntimeState.ACTIVE
        assert case.fixture.connection.consumer_calls == 1
        assert case.fixture.connection.close_calls == 0


def _no_connection(*args: object, **kwargs: object) -> NoReturn:
    pytest.fail("active Monitor/read opened a second SQLite connection")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
async def test_old_active_read_api_and_marker_appends_share_actual_journal_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    append_calls: list[tuple[int, int]] = []
    read_calls: list[tuple[int, int]] = []
    original_append = sqlite_evidence._append_on_worker
    original_retrieve = sqlite_evidence._retrieve_page_on_worker

    def append(
        connection: sqlite3.Connection,
        policy: model.SessionPolicy,
        draft: evidence.PendingEvidenceRecord,
        *,
        schema_version: int = 1,
        timestamp_context: sqlite_evidence._WriterTimestampContext | None = None,
    ) -> model.EvidenceRecord:
        append_calls.append((threading.get_ident(), id(connection)))
        return original_append(
            connection,
            policy,
            draft,
            schema_version=schema_version,
            timestamp_context=timestamp_context,
        )

    def retrieve(
        connection: sqlite3.Connection,
        policy: model.SessionPolicy,
        request: evidence.EvidenceRetrievalRequest,
        *,
        schema_version: int = 1,
    ) -> evidence.EvidencePage:
        read_calls.append((threading.get_ident(), id(connection)))
        return original_retrieve(
            connection, policy, request, schema_version=schema_version
        )

    monkeypatch.setattr(sqlite_evidence, "_append_on_worker", append)
    monkeypatch.setattr(sqlite_evidence, "_retrieve_page_on_worker", retrieve)
    async with _live(tmp_path, monkeypatch, factory) as case:
        with monkeypatch.context() as active_patch:
            active_patch.setattr(sqlite3, "connect", _no_connection)
            operation = await case.start(b"\0\xff")
            rx = await case.emit(b"\0\xfftail")
            report = await _await(operation.wait())
            records = await case.page()
            start = await case.runtime.read_record(report.started_record)
            assert start.page.records == (records[1],)
            assert records[2] == rx
            assert isinstance(records[-1], model.OperationEndedEvidence)
            assert len(append_calls) == 4 and read_calls
            assert len(set(append_calls + read_calls)) == 1
            assert append_calls[0][0] != threading.get_ident()
            assert case.fixture.connection.consumer_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
async def test_terminal_marker_retrieval_waits_for_confirmed_writer_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with _live(tmp_path, monkeypatch, factory) as case:
        operation = await case.start(b"\0\xff")
        rx = await case.emit(b"\0\xfftail")
        report: MonitorReport = await _await(operation.wait())
        active_records = await case.page()
        assert not case.writer_closed.is_set() and not case.terminal_opened.is_set()
        terminal = await _await(case.runtime.detach())
        assert terminal.recorder_close_confirmed and case.writer_closed.is_set()
        assert case.fixture.connection.consumer_calls == 1
        assert case.fixture.connection.close_calls == 1
        assert not case.terminal_opened.is_set()
        for reference, expected in (
            (report.started_record, active_records[1]),
            (report.ended_record, active_records[3]),
            (model.EvidenceReference(case.journal.session_id, 2), rx),
        ):
            assert reference is not None
            result = await _await(case.runtime.read_record(reference))
            assert result.run_id == case.active.run_id
            assert result.page.records == (expected,)
        assert case.terminal_opened.is_set()
        records = await case.page()
        assert records[:4] == active_records
        assert isinstance(records[-1], model.SegmentEndedEvidence)
        assert report.window == model.SequenceRange(2, 3)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
async def test_production_preparation_selects_v3_and_transfers_same_coordinator_and_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    selected = tmp_path / "profile.toml"
    selected.write_text(_PROFILE, encoding="utf-8")
    fixture = _durable_fixture(factory)
    # Replace only the physical backend construction; preparation/persistence stay real.
    monkeypatch.setattr(
        observation_runtime, "BasicSerialBackend", lambda *args: fixture.backend
    )
    probe = AdmissionProbe([])
    path = tmp_path / "prepared.sqlite3"
    await observation_runtime.attach_basic_observation(
        cast(rt.ObservationRuntime, probe), selected, path
    )
    prepared = await probe.captured_preparation()
    await _await(prepared.recorder.close())
    # Inspect only after confirmed writer close; never open an extra active reader.
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro&cache=private", uri=True)
    try:
        assert connection.execute("PRAGMA user_version").fetchone() == (3,), (
            "T010 missing: production preparation must explicitly create schema v3"
        )
        assert connection.execute(
            "SELECT schema_version FROM session_metadata"
        ).fetchone() == (3,)
    finally:
        connection.close()
    access = getattr(prepared, "monitor_access", None)
    assert access is not None, "T010 missing: prepared Monitor capability"
    coordinator = cast(CoordinatorPort, access.coordinator)
    assert coordinator is prepared.recorder
    assert access.clock is coordinator.clock
    assert access.session_id == prepared.recorder.session_id
    assert access.policy == prepared.recorder.policy
    read = prepared.evidence_access
    assert read is not None and isinstance(
        read.live_reader, sqlite_evidence.SqliteEvidenceJournal
    )
    assert read.live_reader.session_id == access.session_id
    assert read.live_reader.policy == access.policy
    start = _start(_provenance(0))
    ends = evidence.maximum_monitor_end_drafts(
        start.operation_id, start.clock_origin_id
    )
    assert access.charge_markers(start, ends) == sqlite_evidence.charge_monitor_markers(
        start, ends
    )
    assert read.terminal_opener is not None
    terminal_reader = await _await(read.terminal_opener())
    try:
        page = await terminal_reader.retrieve(
            evidence.EvidenceRetrievalRequest(access.session_id, 10, 16384)
        )
        assert page.records == ()  # Preparation never opens/acquires the backend.
    finally:
        await terminal_reader.close()
    assert fixture.connection.consumer_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
async def test_preparation_keeps_one_clock_origin_per_runtime_incarnation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    selected = tmp_path / "profile.toml"
    selected.write_text(_PROFILE, encoding="utf-8")
    fixture = _durable_fixture(factory)
    monkeypatch.setattr(
        observation_runtime, "BasicSerialBackend", lambda *args: fixture.backend
    )
    first, second = AdmissionProbe([]), AdmissionProbe([])
    clocks: list[MonitorClock] = []
    for index, probe in enumerate((first, first, second)):
        await observation_runtime.attach_basic_observation(
            cast(rt.ObservationRuntime, probe),
            selected,
            tmp_path / f"clock-{index}.sqlite3",
        )
        prepared = await probe.captured_preparation()
        try:
            access = getattr(prepared, "monitor_access", None)
            assert access is not None, "T010 missing: prepared clock capability"
            clocks.append(access.clock)
        finally:
            await prepared.recorder.close()
    assert clocks[0].origin_id == clocks[1].origin_id
    assert clocks[0].origin_id != clocks[2].origin_id


def _runtime_delivery(
    case: LiveCase,
    request: MonitorRequest,
) -> asyncio.Task[MonitorReport]:
    method = _monitor_entry(case.runtime)

    async def deliver() -> MonitorReport:
        return await method(request)

    return asyncio.create_task(deliver())


async def _join_runtime_delivery(
    case: LiveCase,
    delivery: asyncio.Task[MonitorReport],
) -> None:
    # Test-owned failure cleanup; assertions precede this. No production policy.
    case.clock.advance(model.SQLITE_INTEGER_MAX)
    await _await(asyncio.gather(delivery, return_exceptions=True))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
async def test_t011_public_runtime_binary_match_has_same_active_and_terminal_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with _live(tmp_path, monkeypatch, factory, runtime_support=True) as case:
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, b"\0\xffPASS", 1000, 1024)
        )
        try:
            await _await(case.clock.wait_started.wait())
            await case.emit(b"noise\0\xffP", 17)
            await case.emit(b"ASS trailing\x80", 901)
            report = await _await(delivery)
            assert case.active.run_id is not None
            assert report.run_id == case.active.run_id.value
            assert report.session_id == case.active.session_id
            assert report.match == model.MonitorMatch(
                model.MonitorMatchStart(2, 5), model.MonitorMatchEnd(3, 3)
            )
            assert report.examined_rx_bytes == 11
            assert report.window == model.SequenceRange(2, 4)
            assert report.durability == "complete" and report.end_failure is None
            records = await case.page()
            assert isinstance(records[1], model.OperationStartedEvidence)
            assert isinstance(records[4], model.OperationEndedEvidence)
            for reference, expected in (
                (report.started_record, records[1]),
                (report.ended_record, records[4]),
            ):
                assert reference is not None
                active = await case.runtime.read_record(reference)
                assert active.page.records == (expected,)
            await case.runtime.detach()
            assert case.writer_closed.is_set()
            for reference, expected in (
                (report.started_record, records[1]),
                (report.ended_record, records[4]),
            ):
                assert reference is not None
                terminal = await case.runtime.read_record(reference)
                assert terminal.run_id == case.active.run_id
                assert terminal.page.records == (expected,)
            assert case.terminal_opened.is_set()
            assert (
                case.fixture.connection.consumer_calls
                == case.fixture.connection.close_calls
                == 1
            )
        finally:
            await _join_runtime_delivery(case, delivery)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize(
    "outcome", [model.MonitorOutcome.TIMEOUT, model.MonitorOutcome.BYTE_LIMIT]
)
async def test_t011_public_runtime_bounds_keep_whole_raw_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    outcome: model.MonitorOutcome,
) -> None:
    async with _live(tmp_path, monkeypatch, factory, runtime_support=True) as case:
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, b"PASS", 1000, 2)
        )
        try:
            await _await(case.clock.wait_started.wait())
            if outcome is model.MonitorOutcome.TIMEOUT:
                case.clock.advance(1000000100)
            else:
                await case.emit(b"xxPASS trailing\0\xff")
            report = await _await(delivery)
            assert report.outcome is outcome and report.match is None
            records = await case.page()
            if outcome is model.MonitorOutcome.TIMEOUT:
                assert report.examined_rx_bytes == 0
                assert report.window == model.SequenceRange(2, 2)
                assert not any(isinstance(r, model.RxBytesEvidence) for r in records)
            else:
                assert report.examined_rx_bytes == 2
                assert report.window == model.SequenceRange(2, 3)
                raw = [r for r in records if isinstance(r, model.RxBytesEvidence)]
                assert len(raw) == 1 and raw[0].payload == b"xxPASS trailing\0\xff"
            assert case.runtime.status().state is rt.RuntimeState.ACTIVE
            assert case.fixture.connection.consumer_calls == 1
        finally:
            await _join_runtime_delivery(case, delivery)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize("phase", ["start", "end"])
async def test_t011_detach_waits_for_real_v2_marker_ack_before_terminal_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    phase: str,
) -> None:
    async with _live(tmp_path, monkeypatch, factory, runtime_support=True) as case:
        entered, release = asyncio.Event(), asyncio.Event()
        original_append = case.journal.append
        original_close = case.journal.close
        closed_during_pending = False
        marker_acknowledged = False

        async def append(draft: evidence.PendingEvidenceRecord) -> model.EvidenceRecord:
            nonlocal marker_acknowledged
            record = await original_append(draft)  # Actual SQLite commit/worker.
            if (
                phase == "start"
                and isinstance(draft, evidence.PendingOperationStartedEvidence)
            ) or (
                phase == "end"
                and isinstance(draft, evidence.PendingOperationEndedEvidence)
            ):
                entered.set()
                await release.wait()
                marker_acknowledged = True
            return record

        async def close() -> None:
            nonlocal closed_during_pending
            closed_during_pending |= not marker_acknowledged
            await original_close()

        monkeypatch.setattr(case.journal, "append", append)
        monkeypatch.setattr(case.journal, "close", close)
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, b"PASS", 1000, 1024)
        )
        stopping: asyncio.Task[rt.RuntimeStatus] | None = None
        try:
            if phase == "end":
                await _await(case.clock.wait_started.wait())
                await case.emit(b"PASS trailing")
            await _await(entered.wait())
            stopping = asyncio.create_task(case.runtime.detach())
            await _turn()
            assert not stopping.done() and not case.writer_closed.is_set()
            assert not case.terminal_opened.is_set()
            release.set()
            report = await _await(delivery)
            terminal = await _await(stopping)
            assert terminal.recorder_close_confirmed and not closed_during_pending
            assert report.outcome is (
                model.MonitorOutcome.DETACHED
                if phase == "start"
                else model.MonitorOutcome.MATCHED
            )
            assert report.ended_record is not None
            end = await case.runtime.read_record(report.ended_record)
            assert isinstance(end.page.records[0], model.OperationEndedEvidence)
            assert end.page.records[0].outcome is report.outcome
        finally:
            release.set()
            await _join_runtime_delivery(case, delivery)
            if stopping is not None:
                await _await(stopping)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize("budget", [2, 3], ids=["byte-limit", "match-on-limit"])
async def test_t018_large_whole_rx_survives_short_byte_budget_and_match_tie(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    budget: int,
) -> None:
    async with _live(tmp_path, monkeypatch, factory, runtime_support=True) as case:
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, b"\0\xffA", 1000, budget)
        )
        try:
            await _await(case.clock.wait_started.wait())
            payload = b"\0\xffA" + bytes(range(256)) * 16
            raw = await case.emit(payload, 1)
            report = await _await(delivery)
            assert report.outcome is (
                model.MonitorOutcome.MATCHED
                if budget == 3
                else model.MonitorOutcome.BYTE_LIMIT
            )
            assert (
                report.examined_rx_bytes == budget
                and report.window == model.SequenceRange(2, 3)
            )
            assert (report.match is not None) is (budget == 3)
            result = await case.runtime.read_record(
                model.EvidenceReference(case.journal.session_id, raw.sequence)
            )
            assert result.page.records == (raw,) and raw.payload == payload
            assert len(raw.payload) == 4099
            assert case.fixture.connection.consumer_calls == 1
        finally:
            await _join_runtime_delivery(case, delivery)


@pytest.mark.asyncio
@pytest.mark.parametrize("lost_bytes", [None, 7])
async def test_t018_reported_loss_uses_real_acquisition_and_preserves_derived_match_quality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lost_bytes: int | None,
) -> None:
    factory = BACKEND_FIXTURE_FACTORIES[1]
    async with _live(tmp_path, monkeypatch, factory, runtime_support=True) as case:
        # Capability-specific event remains on its existing Enhanced-shaped fixture.
        from tests.fakes import EnhancedShapedBackendConnection

        connection = case.fixture.connection
        assert isinstance(connection, EnhancedShapedBackendConnection)
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, b"\0\xffPASS", 1000, 1024)
        )
        try:
            await _await(case.clock.wait_started.wait())
            await case.emit(b"\0\xffP", 1)
            await connection.emit_observer_loss(
                cause="overflow", lost_bytes=lost_bytes, timestamp=2
            )
            await case.emit(b"ASS", 3)
            await case.emit(b"\0\xffPASS trailing\x80", 4)
            report = await _await(delivery)
            assert report.outcome is model.MonitorOutcome.MATCHED
            assert report.observer_loss_records == 1 and report.examined_rx_bytes == 12
            assert report.match == model.MonitorMatch(
                model.MonitorMatchStart(5, 0), model.MonitorMatchEnd(5, 6)
            )
            assert report.window == model.SequenceRange(2, 6)
            records = await case.page()
            loss = records[3]
            assert isinstance(loss, model.ObserverLossEvidence)
            assert (
                loss.lost_bytes == lost_bytes
                and loss.cause is model.ObserverLossCause.OVERFLOW
            )
            assert loss.observed_at.value == 2
            assert (
                loss.observer_id == connection.OBSERVER_ID
                and loss.scope == connection.LOSS_SCOPE
            )
            assert isinstance(records[5], model.RxBytesEvidence)
            assert records[5].payload == b"\0\xffPASS trailing\x80"
            assert case.fixture.connection.consumer_calls == 1
        finally:
            await _join_runtime_delivery(case, delivery)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
async def test_t011_runtime_end_ack_failure_keeps_actual_committed_rx_and_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with _live(tmp_path, monkeypatch, factory, runtime_support=True) as case:
        original_append = case.journal.append

        async def append(draft: evidence.PendingEvidenceRecord) -> model.EvidenceRecord:
            record = await original_append(draft)
            if isinstance(draft, evidence.PendingOperationEndedEvidence):
                raise evidence.JournalFailure(
                    evidence.JournalOperation.APPEND,
                    evidence.JournalFailureKind.IO_FAILURE,
                )
            return record

        monkeypatch.setattr(case.journal, "append", append)
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, b"PASS", 1000, 1024)
        )
        try:
            await _await(case.clock.wait_started.wait())
            await case.emit(b"PASS trailing\0\xff")
            report = await _await(delivery)
            assert report.outcome is model.MonitorOutcome.MATCHED
            assert (
                report.durability == "end_unconfirmed" and report.ended_record is None
            )
            assert (
                report.end_failure is not None
                and report.end_failure.code == "io_failure"
            )
            assert case.runtime.status().state is rt.RuntimeState.ACTIVE
            assert case.runtime.status().primary_issue is None
            after = await case.emit(b"ambient after failure\0\xff")
            records = await case.page()
            assert records[-1] == after
            assert any(isinstance(r, model.OperationEndedEvidence) for r in records)
            assert case.fixture.connection.consumer_calls == 1
        finally:
            await _join_runtime_delivery(case, delivery)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
async def test_t018_live_prefix_survives_eviction_without_pinning_markers_or_rx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with _live(
        tmp_path, monkeypatch, factory, runtime_support=True, retained=2
    ) as case:
        condition = b"\0\xff" + b"P" * 20 + b"ASS"
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, condition, 1000, 1024)
        )
        try:
            await _await(case.clock.wait_started.wait())
            for index, byte in enumerate(condition):
                await case.emit(bytes([byte]), index + 1)
            report = await _await(delivery)
            assert report.outcome is model.MonitorOutcome.MATCHED
            assert report.examined_rx_bytes == len(condition)
            assert report.match == model.MonitorMatch(
                model.MonitorMatchStart(2, 0), model.MonitorMatchEnd(26, 1)
            )
            assert report.window == model.SequenceRange(2, 27)
            assert report.ended_record == model.EvidenceReference(
                case.journal.session_id, 27
            )
            assert report.durability == "complete"
            for reference in (
                report.started_record,
                model.EvidenceReference(case.journal.session_id, 2),
            ):
                expired = await case.runtime.read_record(reference)
                assert expired.page.outcome is evidence.EvidencePageOutcome.EXPIRED
            first = await case.runtime.read_page(
                evidence.EvidenceRetrievalRequest(case.journal.session_id, 1, 16384)
            )
            assert [r.sequence for r in first.page.records] == [26]
            assert first.page.retention_marker is not None
            assert first.page.retention_marker.discarded_rx_payload_byte_count == 24
            assert (
                first.page.continuation is not None
                and first.page.snapshot_end_exclusive == 28
            )
            await case.emit(b"ambient-one\0\xff", 50)
            await case.emit(b"ambient-two\x80", 51)
            resumed = await case.runtime.read_page(
                evidence.EvidenceRetrievalRequest(
                    case.journal.session_id, 1, 16384, first.page.continuation
                )
            )
            assert resumed.page.outcome is evidence.EvidencePageOutcome.EXPIRED
            assert (
                resumed.page.records == () and resumed.page.snapshot_end_exclusive == 28
            )
            assert resumed.page.expired_range == model.SequenceRange(27, 28)
            assert not resumed.page.truncated and resumed.page.continuation is None
            assert report.match == model.MonitorMatch(
                model.MonitorMatchStart(2, 0), model.MonitorMatchEnd(26, 1)
            )
            assert report.durability == "complete"  # Eviction does not revoke ACKs.
            await case.runtime.detach()
            assert case.writer_closed.is_set()
            terminal = await case.runtime.read_record(report.ended_record)
            assert terminal.page.outcome is evidence.EvidencePageOutcome.EXPIRED
            assert (
                case.fixture.connection.consumer_calls
                == case.fixture.connection.close_calls
                == 1
            )
        finally:
            await _join_runtime_delivery(case, delivery)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize(
    ("trigger", "missing_end", "late_cleanup"),
    [
        ("disconnected", False, False),
        ("transport_failure", False, False),
        ("timestamp_origin_reset", False, False),
        ("detached", False, False),
        ("service_stopping", False, False),
        ("recording_failure", True, False),
        ("disconnected", True, False),
        ("transport_failure", True, False),
        ("disconnected", True, True),
        ("transport_failure", True, True),
    ],
)
async def test_t018_real_journal_termination_and_joined_fallback_preserve_capture_and_origins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    trigger: str,
    missing_end: bool,
    late_cleanup: bool,
) -> None:
    async with _live(tmp_path, monkeypatch, factory, runtime_support=True) as case:
        original_append = case.journal.append

        async def append(draft: evidence.PendingEvidenceRecord) -> model.EvidenceRecord:
            if (
                missing_end and isinstance(draft, evidence.PendingSegmentEndedEvidence)
            ) or (
                trigger == "recording_failure"
                and isinstance(draft, evidence.PendingRxBytesEvidence)
                and draft.payload == b"unrecorded"
            ):
                raise evidence.JournalFailure(
                    evidence.JournalOperation.APPEND,
                    evidence.JournalFailureKind.IO_FAILURE,
                )
            return await original_append(draft)

        monkeypatch.setattr(case.journal, "append", append)
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, b"\0\xffPASS", 1000, 1024)
        )
        stopping: asyncio.Task[rt.RuntimeStatus] | None = None
        close_gate = case.fixture.connection.close_gate
        try:
            await _await(case.clock.wait_started.wait())
            await case.emit(b"\0\xffP", 123)
            if late_cleanup:
                close_gate.allow.clear()
            if trigger == "disconnected":
                await case.fixture.connection.disconnect()
            elif trigger == "transport_failure":
                await case.fixture.connection.end_stream_unexpectedly()
            elif trigger == "recording_failure":
                await case.fixture.connection.emit_rx(b"unrecorded", timestamp=124)
            elif trigger == "timestamp_origin_reset":
                domain = case.fixture.connection.descriptor.backend_observation_timestamp_domain
                await case.fixture.connection.reset_timestamp_origin(
                    replace(domain, domain_id="next-domain", origin_id="next-origin")
                )
            elif trigger == "detached":
                stopping = asyncio.create_task(case.runtime.detach())
            else:
                case.runtime._seal_monitors()
            if late_cleanup:
                await _await(close_gate.entered.wait())
                await _turn()
                assert not delivery.done() and not case.writer_closed.is_set()
                # Keep the timer asleep: the later joined fallback must check time.
                case.clock.value = 1_000_000_101
                close_gate.allow.set()
            report = await _await(delivery)
            assert report.outcome is (
                model.MonitorOutcome.TIMEOUT
                if late_cleanup
                else model.MonitorOutcome(trigger)
            )
            assert report.match is None and report.examined_rx_bytes == 3
            assert report.observer_loss_records == 0
            assert report.durability == "complete" and report.end_failure is None
            assert case.active.acquisition is not None
            assert report.provenance == case.active.acquisition.provenance
            assert report.clock.origin_id == case.clock.origin_id
            assert report.clock.decided_at_ns == (
                1_000_000_101 if late_cleanup else 100
            )
            included_end = not missing_end and trigger in {
                "disconnected",
                "transport_failure",
                "timestamp_origin_reset",
            }
            assert report.window == model.SequenceRange(2, 4 if included_end else 3)
            if trigger == "timestamp_origin_reset":
                suffix = await case.emit(b"ASS", 1)
                assert suffix.segment_id != report.provenance.segment_id
                assert suffix.observed_at.domain_id == "next-domain"
                assert case.runtime.status().state is rt.RuntimeState.ACTIVE
            if stopping is not None:
                await _await(stopping)
            await case.runtime.detach()
            records = await case.page()
            assert isinstance(records[0], model.SegmentStartedEvidence)
            assert records[0].provenance == report.provenance
            assert report.ended_record is not None
            end = await case.runtime.read_record(report.ended_record)
            assert isinstance(end.page.records[0], model.OperationEndedEvidence)
            assert end.page.records[0].window == report.window
            assert end.page.records[0].outcome is report.outcome
            if missing_end:
                assert not any(
                    isinstance(r, model.SegmentEndedEvidence) for r in records
                )
                snapshot = case.runtime.status().acquisition
                assert snapshot is not None
                if trigger == "disconnected":
                    assert (
                        snapshot.terminal_trigger is not None
                        and snapshot.terminal_trigger.value == "disconnected"
                    )
                    assert (
                        snapshot.primary_failure_kind is not None
                        and snapshot.primary_failure_kind.value == "recording_failure"
                    )
                else:
                    assert (
                        snapshot.primary_failure_kind is not None
                        and snapshot.primary_failure_kind.value == trigger
                    )
            assert (
                case.fixture.connection.consumer_calls
                == case.fixture.connection.close_calls
                == 1
            )
        finally:
            close_gate.allow.set()
            await _join_runtime_delivery(case, delivery)
            if stopping is not None:
                await _await(stopping)


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize("phase", ["start", "end"])
@pytest.mark.parametrize(
    "committed", [False, True], ids=["before-commit", "after-commit"]
)
@pytest.mark.asyncio
async def test_t026_native_marker_worker_survives_cancel_and_detach_until_ack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    phase: str,
    committed: bool,
) -> None:
    # Catches abandoned SQLite work or writer close while its native job is gated.
    from dutchmate_core.monitor import MonitorRejected

    async with _live(tmp_path, monkeypatch, factory, runtime_support=True) as case:
        original_append = sqlite_evidence._append_on_worker
        entered, release = asyncio.Event(), threading.Event()
        loop = asyncio.get_running_loop()
        worker_threads: list[int] = []

        def pause() -> None:
            worker_threads.append(threading.get_ident())
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(3), "test-owned worker gate was not released"

        def append(
            connection: sqlite3.Connection,
            policy: model.SessionPolicy,
            draft: evidence.PendingEvidenceRecord,
            *,
            schema_version: int = 1,
            timestamp_context: sqlite_evidence._WriterTimestampContext | None = None,
        ) -> model.EvidenceRecord:
            selected = (
                phase == "start"
                and isinstance(draft, evidence.PendingOperationStartedEvidence)
            ) or (
                phase == "end"
                and isinstance(draft, evidence.PendingOperationEndedEvidence)
            )
            if selected and not committed:
                pause()
            record = original_append(
                connection,
                policy,
                draft,
                schema_version=schema_version,
                timestamp_context=timestamp_context,
            )
            if selected and committed:
                pause()
            return record

        monkeypatch.setattr(sqlite_evidence, "_append_on_worker", append)
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, b"PASS", 1000, 1024)
        )
        stopping: asyncio.Task[rt.RuntimeStatus] | None = None
        try:
            if phase == "end":
                await _await(case.clock.wait_started.wait())
                await case.emit(b"PASS trailing\0\xff")
            await _await(entered.wait())
            assert (
                len(worker_threads) == 1 and worker_threads[0] != threading.get_ident()
            )
            for _ in range(3):
                delivery.cancel()
                await _turn()
                assert not delivery.done()
            with pytest.raises(MonitorRejected) as busy:
                await _monitor_entry(case.runtime)(
                    MonitorRequest(case.journal.session_id, b"PASS", 1000, 1024)
                )
            assert busy.value.kind == "busy"
            stopping = asyncio.create_task(case.runtime.detach())
            await _turn()
            assert not stopping.done() and not case.writer_closed.is_set()
            assert not case.terminal_opened.is_set()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await _await(delivery)
            terminal = await _await(stopping)
            assert (
                terminal.recorder_close_confirmed
                and terminal.physical_release_confirmed
            )
            records = await case.page()
            starts = [
                r for r in records if isinstance(r, model.OperationStartedEvidence)
            ]
            ends = [r for r in records if isinstance(r, model.OperationEndedEvidence)]
            assert len(starts) == len(ends) == 1
            assert ends[0].start_sequence == starts[0].sequence == 1
            assert ends[0].outcome is (
                model.MonitorOutcome.DETACHED
                if phase == "start"
                else model.MonitorOutcome.MATCHED
            )
            assert case.terminal_opened.is_set() and len(worker_threads) == 1
            assert (
                case.fixture.connection.consumer_calls
                == case.fixture.connection.close_calls
                == 1
            )
        finally:
            release.set()
            await _join_runtime_delivery(case, delivery)
            if stopping is not None:
                await _await(stopping)


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize("phase", ["start", "end"])
@pytest.mark.parametrize("committed", [False, True], ids=["before-commit", "lost-ack"])
@pytest.mark.asyncio
async def test_t026_real_marker_failure_preserves_actual_terminal_disk_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    phase: str,
    committed: bool,
) -> None:
    # Catches fabricated missing/present markers, synthetic ends and ambiguous retry.
    async with _live(tmp_path, monkeypatch, factory, runtime_support=True) as case:
        original_append = case.journal.append
        attempts: list[evidence.PendingEvidenceRecord] = []

        async def append(draft: evidence.PendingEvidenceRecord) -> model.EvidenceRecord:
            selected = (
                phase == "start"
                and isinstance(draft, evidence.PendingOperationStartedEvidence)
            ) or (
                phase == "end"
                and isinstance(draft, evidence.PendingOperationEndedEvidence)
            )
            if not selected:
                return await original_append(draft)
            attempts.append(draft)
            if committed:
                await original_append(draft)
            raise evidence.JournalFailure(
                evidence.JournalOperation.APPEND, evidence.JournalFailureKind.IO_FAILURE
            )

        monkeypatch.setattr(case.journal, "append", append)
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, b"PASS", 1000, 1024)
        )
        try:
            if phase == "start":
                with pytest.raises(evidence.JournalFailure) as failure:
                    await _await(delivery)
                assert failure.value.kind is evidence.JournalFailureKind.IO_FAILURE
            else:
                await _await(case.clock.wait_started.wait())
                await case.emit(b"PASS trailing\0\xff")
                report = await _await(delivery)
                assert report.outcome is model.MonitorOutcome.MATCHED
                assert (
                    report.durability == "end_unconfirmed"
                    and report.ended_record is None
                )
                assert (
                    report.end_failure is not None
                    and report.end_failure.code == "io_failure"
                )
                assert (
                    report.window == model.SequenceRange(2, 3)
                    and report.examined_rx_bytes == 4
                )
            assert len(attempts) == 1
            assert case.runtime.status().state is rt.RuntimeState.ACTIVE
            assert case.runtime.status().primary_issue is None
            await case.emit(b"ambient after marker failure\0\xff")
            terminal = await case.runtime.detach()
            assert (
                terminal.recorder_close_confirmed
                and terminal.physical_release_confirmed
            )
            records = await case.page()
            starts = [
                r for r in records if isinstance(r, model.OperationStartedEvidence)
            ]
            ends = [r for r in records if isinstance(r, model.OperationEndedEvidence)]
            assert len(starts) == (int(committed) if phase == "start" else 1)
            assert len(ends) == (int(committed) if phase == "end" else 0)
            assert any(
                isinstance(r, model.RxBytesEvidence)
                and r.payload == b"ambient after marker failure\0\xff"
                for r in records
            )
            assert len(attempts) == 1 and case.runtime.evidence_read_cleanup_confirmed
            assert (
                case.fixture.connection.consumer_calls
                == case.fixture.connection.close_calls
                == 1
            )
        finally:
            await _join_runtime_delivery(case, delivery)


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize("unconfirmed", [False, True])
@pytest.mark.asyncio
async def test_t026_monitor_and_reattach_never_reset_terminal_reader_cleanup_uncertainty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    unconfirmed: bool,
) -> None:
    # Catches resetting the incarnation read latch during Monitor or attach/detach.
    from dutchmate_core.adapters import terminal_evidence
    from dutchmate_core.evidence_access import EvidenceReadRejected

    async with _live(tmp_path, monkeypatch, factory, runtime_support=True) as first:
        owner = first.runtime
        terminal = await owner.detach()
        original_close = terminal_evidence._close_reader_on_worker

        def close_without_ack(connection: sqlite3.Connection) -> None:
            original_close(connection)  # Actually release this test-owned resource.
            raise evidence.JournalFailure(
                evidence.JournalOperation.CLOSE, evidence.JournalFailureKind.IO_FAILURE
            )

        with monkeypatch.context() as patch:
            patch.setattr(
                terminal_evidence, "_close_reader_on_worker", close_without_ack
            )
            with pytest.raises(evidence.JournalFailure) as failure:
                await owner.read_record(
                    model.EvidenceReference(first.journal.session_id, 0)
                )
            assert failure.value.operation is evidence.JournalOperation.CLOSE
        assert owner.status() == terminal and terminal.attach_admissible
        assert not owner.evidence_read_cleanup_confirmed

    next_root = tmp_path / "next-run"
    next_root.mkdir()
    async with _live(
        next_root, monkeypatch, factory, runtime_support=True, runtime=owner
    ) as case:
        assert not owner.evidence_read_cleanup_confirmed
        original_append = case.journal.append

        async def append(draft: evidence.PendingEvidenceRecord) -> model.EvidenceRecord:
            record = await original_append(draft)
            if unconfirmed and isinstance(
                draft, evidence.PendingOperationEndedEvidence
            ):
                raise evidence.JournalFailure(
                    evidence.JournalOperation.APPEND,
                    evidence.JournalFailureKind.IO_FAILURE,
                )
            return record

        monkeypatch.setattr(case.journal, "append", append)
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, b"PASS", 1000, 1024)
        )
        try:
            await _await(case.clock.wait_started.wait())
            await case.emit(b"PASS trailing")
            report = await _await(delivery)
            assert report.outcome is model.MonitorOutcome.MATCHED
            assert report.durability == (
                "end_unconfirmed" if unconfirmed else "complete"
            )
            assert (
                owner.status().state is rt.RuntimeState.ACTIVE
                and owner.status().primary_issue is None
            )
            assert not owner.evidence_read_cleanup_confirmed
            with pytest.raises(EvidenceReadRejected) as rejected:
                await owner.read_record(report.started_record)
            assert rejected.value.kind == "read_unavailable"
            terminal = await owner.detach()
            assert (
                terminal.recorder_close_confirmed
                and terminal.physical_release_confirmed
            )
            assert not owner.evidence_read_cleanup_confirmed
        finally:
            await _join_runtime_delivery(case, delivery)


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced")
)
@pytest.mark.parametrize("trigger", ["disconnected", "transport_failure"])
@pytest.mark.parametrize("offset", [-1, 0, 1], ids=["before", "at", "after"])
@pytest.mark.asyncio
async def test_t026_cancelled_delivery_waits_for_joined_fallback_without_relabeling_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    trigger: str,
    offset: int,
) -> None:
    # Catches snapshot polling, invented early fallback times and capture relabeling.
    async with _live(tmp_path, monkeypatch, factory, runtime_support=True) as case:
        original_append = case.journal.append

        async def append(draft: evidence.PendingEvidenceRecord) -> model.EvidenceRecord:
            if isinstance(draft, evidence.PendingSegmentEndedEvidence):
                raise evidence.JournalFailure(
                    evidence.JournalOperation.APPEND,
                    evidence.JournalFailureKind.IO_FAILURE,
                )
            return await original_append(draft)

        monkeypatch.setattr(case.journal, "append", append)
        close_gate = case.fixture.connection.close_gate
        close_gate.allow.clear()
        delivery = _runtime_delivery(
            case, MonitorRequest(case.journal.session_id, b"PASS", 1000, 1024)
        )
        try:
            await _await(case.clock.wait_started.wait())
            await case.emit(b"PA", timestamp=17)
            if trigger == "disconnected":
                await case.fixture.connection.disconnect()
            else:
                await case.fixture.connection.end_stream_unexpectedly()
            await _await(close_gate.entered.wait())
            for _ in range(3):
                delivery.cancel()
                await _turn()
                assert not delivery.done()
            assert not case.writer_closed.is_set()
            # Do not wake the timer: joined fallback must sample the current time.
            case.clock.value = 1_000_000_100 + offset
            close_gate.allow.set()
            with pytest.raises(asyncio.CancelledError):
                await _await(delivery)
            terminal = await case.runtime.detach()
            assert (
                terminal.recorder_close_confirmed
                and terminal.physical_release_confirmed
            )
            records = await case.page()
            ends = [r for r in records if isinstance(r, model.OperationEndedEvidence)]
            assert len(ends) == 1
            assert ends[0].outcome is (
                model.MonitorOutcome.TIMEOUT
                if offset >= 0
                else model.MonitorOutcome(trigger)
            )
            assert ends[0].clock.decided_at_ns == 1_000_000_100 + offset
            assert ends[0].window == model.SequenceRange(2, 3)
            assert ends[0].examined_rx_bytes == 2 and ends[0].match is None
            assert not any(isinstance(r, model.SegmentEndedEvidence) for r in records)
            assert terminal.acquisition is not None
            assert terminal.acquisition.primary_failure_kind is not None
            assert terminal.acquisition.primary_failure_kind.value == (
                "recording_failure"
                if trigger == "disconnected"
                else "transport_failure"
            )
            if trigger == "disconnected":
                assert terminal.acquisition.terminal_trigger is not None
                assert terminal.acquisition.terminal_trigger.value == "disconnected"
            assert case.runtime.evidence_read_cleanup_confirmed
            assert (
                case.fixture.connection.consumer_calls
                == case.fixture.connection.close_calls
                == 1
            )
        finally:
            close_gate.allow.set()
            await _join_runtime_delivery(case, delivery)
