"""010 T006 RED: manual v3 composition, existing acquisition and active/terminal reads.

Both receive-only backend shapes run identical tests. They have no TX/control
entry points. No future runtime annotation method or prepared capability is used.
"""

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import pytest

from dutchmate_core import evidence, model, monitor
from dutchmate_core import runtime as rt
from dutchmate_core.adapters import sqlite_evidence as sqlite
from dutchmate_core.adapters.terminal_evidence import (
    capture_terminal_target,
    open_terminal_reader,
)
from dutchmate_core.evidence_access import OwnedEvidenceReadPort, PreparedEvidenceAccess
from tests.contract.test_annotation_recording import (
    JournalProbe,
    MonitorOperation,
    SampledClock,
    annotation_entry,
    spawn,
)
from tests.contract.test_monitor_recording import _await
from tests.contract.test_observation_runtime import _profile
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixture,
    BackendFixtureFactory,
    BasicShapedBackend,
    EnhancedShapedBackend,
)
from tests.integration.test_monitor import _durable_fixture


def assert_single_rx_owner(fixture: BackendFixture) -> None:
    backend = fixture.backend
    assert isinstance(backend, (BasicShapedBackend, EnhancedShapedBackend))
    assert backend.open_calls == fixture.connection.consumer_calls == 1


@dataclass
class LiveCase:
    runtime: rt.ObservationRuntime
    active: rt.RuntimeStatus
    fixture: BackendFixture
    journal: sqlite.SqliteEvidenceJournal
    probe: JournalProbe
    coordinator: monitor.MonitorRecordingCoordinator
    clock: SampledClock
    terminal_opened: asyncio.Event

    async def emit(self, payload: bytes, timestamp: int) -> model.RxBytesEvidence:
        await self.fixture.connection.emit_rx(payload, timestamp=timestamp)
        return await _await(self.probe.rx_commits.get())

    async def page(self) -> tuple[model.EvidenceRecord, ...]:
        result = await _await(
            self.runtime.read_page(
                evidence.EvidenceRetrievalRequest(
                    self.journal.session_id,
                    self.journal.policy.max_retrieval_page_records,
                    self.journal.policy.max_retrieval_page_charged_bytes,
                )
            )
        )
        assert result.run_id == self.active.run_id
        assert result.page.outcome is evidence.EvidencePageOutcome.COMPLETE
        assert not result.page.truncated
        return result.page.records

    async def start(self) -> MonitorOperation:
        provenance = self.coordinator.current_provenance
        assert provenance is not None and self.active.run_id is not None
        return await self.coordinator.start(
            monitor.MonitorRequest(self.journal.session_id, b"\0\xffPASS", 1000, 6),
            run_id=self.active.run_id.value,
            expected_provenance=provenance,
            revalidate=lambda: None,
            charge_markers=sqlite.charge_monitor_markers,
        )


@asynccontextmanager
async def live_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: BackendFixtureFactory
) -> AsyncIterator[LiveCase]:
    profile = _profile()
    path = tmp_path / "live-v3.db"
    journal = await sqlite.SqliteEvidenceJournal.create_v3(path, profile.session_policy)
    probe, clock = JournalProbe(journal), SampledClock()
    coordinator = monitor.MonitorRecordingCoordinator(recorder=probe, clock=clock)
    owner = rt.ObservationRuntime()
    terminal_opened = asyncio.Event()
    fixture = _durable_fixture(factory)
    try:
        target = capture_terminal_target(
            path,
            session_id=journal.session_id,
            policy=journal.policy,
            expected_schema_version=3,
        )
        assert target is not None

        async def terminal_opener() -> OwnedEvidenceReadPort:
            assert probe.closed.is_set(), "terminal read preceded writer close ACK"
            terminal_opened.set()
            return await open_terminal_reader(target)

        async def prepare(_selected: object) -> rt.PreparedObservationRun:
            # Old preparation plus existing evidence access only. Annotation and
            # Monitor admission/composition are deliberately outside T006.
            return rt.PreparedObservationRun(
                recorder=coordinator,
                backend=fixture.backend,
                evidence_access=PreparedEvidenceAccess(
                    journal.session_id, journal.policy, journal, terminal_opener
                ),
            )

        active = await _await(owner.attach(profile, prepare))
        assert active.state is rt.RuntimeState.ACTIVE

        def forbidden(*args: object, **kwargs: object) -> NoReturn:
            pytest.fail("annotation attempted another backend open or RX consumer")

        monkeypatch.setattr(fixture.backend, "open", forbidden)
        monkeypatch.setattr(fixture.connection, "events", forbidden)
        yield LiveCase(
            owner, active, fixture, journal, probe, coordinator, clock, terminal_opened
        )
    finally:
        probe.release()
        clock.advance(model.SQLITE_INTEGER_MAX)
        await _await(owner.detach())
        if not probe.closed.is_set():
            await _await(coordinator.close())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
async def test_same_rx_writer_preserves_exact_ambient_bytes_and_active_terminal_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: BackendFixtureFactory
) -> None:
    async with live_case(tmp_path, monkeypatch, factory) as case:
        append = annotation_entry(case.coordinator)
        before = await case.emit(bytes(range(256)), 17)
        case.clock.advance(700)
        accepted = await append("http", " \tbuild e\u0301; 温度\r\n")
        after = await case.emit(b"ambient\0\xffafter", 901)
        active = await case.page()
        assert active[1:] == (before, accepted, after)
        assert [r.sequence for r in active] == [0, 1, 2, 3]
        assert before.payload == bytes(range(256))
        assert after.payload == b"ambient\0\xffafter"
        assert accepted.received_at_ns == 700
        assert accepted.clock_origin_id == case.clock.origin_id
        assert before.observed_at.value == 17 and after.observed_at.value == 901
        assert before.observed_at.domain_id == after.observed_at.domain_id
        assert case.coordinator.current_provenance is not None
        assert before.observed_at.domain_id == (
            case.coordinator.current_provenance.backend_observation_timestamp_domain.domain_id
        )
        reference = model.EvidenceReference(case.journal.session_id, accepted.sequence)
        resolved = await case.runtime.read_record(reference)
        assert resolved.run_id == case.active.run_id
        assert resolved.page.records == (accepted,)
        assert not case.terminal_opened.is_set() and not case.probe.closed.is_set()
        assert_single_rx_owner(case.fixture)
        assert case.fixture.connection.close_calls == 0
        assert not any(
            isinstance(
                r, (model.OperationStartedEvidence, model.OperationEndedEvidence)
            )
            for r in active
        )
        await _await(case.runtime.detach())
        assert case.probe.close_calls == case.fixture.connection.close_calls == 1
        terminal = await case.page()
        assert case.terminal_opened.is_set() and terminal[:-1] == active
        assert isinstance(terminal[-1], model.SegmentEndedEvidence)
        assert (await case.runtime.read_record(reference)).page.records == (accepted,)
        with closing(sqlite3.connect(tmp_path / "live-v3.db")) as connection:
            assert connection.execute("PRAGMA user_version").fetchone() == (3,)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
async def test_live_monitor_matches_binary_rx_across_annotation_and_terminal_pair_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: BackendFixtureFactory
) -> None:
    async with live_case(tmp_path, monkeypatch, factory) as case:
        append = annotation_entry(case.coordinator)
        ambient = await case.emit(b"ambient before", 1)
        operation = await case.start()
        first = await case.emit(b"\0\xffPA", 2)
        accepted = await append("cli", "SS \u0001 PASS " * 100)
        assert not operation.decided
        second = await case.emit(b"SStrailing\0\x80", 3)
        report = await _await(operation.wait())
        assert report.outcome is model.MonitorOutcome.MATCHED
        assert report.match == model.MonitorMatch(
            model.MonitorMatchStart(first.sequence, 0),
            model.MonitorMatchEnd(second.sequence, 2),
        )
        assert report.window == model.SequenceRange(first.sequence, second.sequence + 1)
        assert report.examined_rx_bytes == 6 and report.observer_loss_records == 0
        assert report.durability == "complete"
        trailing = await case.emit(b"ambient after\xff", 4)
        records = await case.page()
        assert [r.payload for r in records if isinstance(r, model.RxBytesEvidence)] == [
            ambient.payload,
            first.payload,
            second.payload,
            trailing.payload,
        ]
        assert records[accepted.sequence] == accepted
        assert report.ended_record is not None
        assert isinstance(
            records[report.ended_record.sequence], model.OperationEndedEvidence
        )
        await _await(case.runtime.detach())
        assert (await case.page())[:-1] == records
        assert case.terminal_opened.is_set()
        assert_single_rx_owner(case.fixture)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
async def test_live_delayed_annotation_ack_expires_monitor_without_extending_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: BackendFixtureFactory
) -> None:
    async with live_case(tmp_path, monkeypatch, factory) as case:
        append = annotation_entry(case.coordinator)
        operation = await case.start()
        await _await(case.clock.wait_started.wait())
        case.probe.annotation.acknowledgement.allow.clear()
        insertion = spawn(append("core", "\u0001 client assertion"))
        try:
            await _await(case.probe.annotation.acknowledgement.entered.wait())
            case.clock.value = 1_000_000_107  # Leave the timer asleep deliberately.
            case.probe.annotation.acknowledgement.allow.set()
            accepted = await _await(insertion)
            assert operation.decided, (
                "post-ACK publication must independently see expiry"
            )
            report = await _await(operation.wait())
            assert accepted.received_at_ns == 100
            assert report.outcome is model.MonitorOutcome.TIMEOUT
            assert report.clock.deadline_at_ns == 1_000_000_100
            assert report.clock.decided_at_ns == 1_000_000_107
            assert report.window == model.SequenceRange(2, 2)
            assert report.examined_rx_bytes == report.observer_loss_records == 0
            ambient = await case.emit(b"still acquired\0\xff", 19)
            records = await case.page()
            assert records[accepted.sequence] == accepted
            assert records[ambient.sequence] == ambient
            await _await(case.runtime.detach())
            assert (await case.page())[:-1] == records
        finally:
            case.probe.release()
            await _await(asyncio.gather(insertion, return_exceptions=True))
