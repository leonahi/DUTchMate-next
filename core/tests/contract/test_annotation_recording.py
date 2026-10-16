"""010 T006 RED: sole coordinator insertion, real v3 ACKs and Monitor clocks.

Only persistence checkpoints and the existing host clock are controlled here.
The future append entry is invoked through a test-only structural assertion;
there is no fallback insertion implementation or runtime annotation capability.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import pytest

from dutchmate_core import evidence, model, monitor
from dutchmate_core.adapters import sqlite_evidence as sqlite
from tests.contract.test_monitor_journal import _provenance
from tests.contract.test_monitor_recording import (
    AppendGates,
    ManualClock,
    _await,
    _turn,
)
from tests.contract.test_sqlite_evidence_journal import _policy


@runtime_checkable
class AnnotationAppend(Protocol):
    async def append_client_annotation(
        self, client_surface: str, text: str
    ) -> model.ClientAnnotationEvidence: ...


def annotation_entry(
    coordinator: monitor.MonitorRecordingCoordinator,
) -> Callable[[str, str], Awaitable[model.ClientAnnotationEvidence]]:
    assert isinstance(coordinator, AnnotationAppend), (
        "T007 missing: MonitorRecordingCoordinator.append_client_annotation"
    )
    return coordinator.append_client_annotation


class MonitorOperation(Protocol):
    @property
    def decided(self) -> bool: ...

    async def wait(self) -> monitor.MonitorReport: ...


def spawn[T](work: Awaitable[T]) -> asyncio.Task[T]:
    async def run() -> T:
        return await work

    return asyncio.create_task(run())


class SampledClock(ManualClock):
    def __init__(self) -> None:
        super().__init__()
        self.samples: list[int] = []

    def now_ns(self) -> int:
        self.samples.append(self.value)
        return super().now_ns()


class JournalProbe:
    """Delegate every write/close to one real journal, exposing only ACK gates."""

    def __init__(self, journal: sqlite.SqliteEvidenceJournal) -> None:
        self.journal = journal
        self.session_id, self.policy = journal.session_id, journal.policy
        self.rx = AppendGates()
        self.annotation = AppendGates()
        self.submitted: list[evidence.PendingEvidenceRecord] = []
        self.acknowledged: list[model.EvidenceRecord] = []
        self.rx_commits: asyncio.Queue[model.RxBytesEvidence] = asyncio.Queue()
        self.failure: str | None = None
        self.error = evidence.JournalFailure(
            evidence.JournalOperation.APPEND, evidence.JournalFailureKind.IO_FAILURE
        )
        self.close_calls = 0
        self.closed = asyncio.Event()

    async def append(
        self, draft: evidence.PendingEvidenceRecord
    ) -> model.EvidenceRecord:
        self.submitted.append(draft)
        annotation = isinstance(draft, evidence.PendingClientAnnotationEvidence)
        gates = (
            self.annotation
            if annotation
            else self.rx
            if isinstance(draft, evidence.PendingRxBytesEvidence)
            else None
        )
        if gates is not None:
            await gates.commit.enter()
        if annotation and self.failure == "before_commit":
            raise self.error
        record = await self.journal.append(draft)
        if gates is not None:
            await gates.acknowledgement.enter()
        if annotation and self.failure == "after_commit":
            raise self.error
        self.acknowledged.append(record)
        if isinstance(record, model.RxBytesEvidence):
            self.rx_commits.put_nowait(record)
        return record

    async def close(self) -> None:
        self.close_calls += 1
        await self.journal.close()
        self.closed.set()

    def release(self) -> None:
        for gates in (self.rx, self.annotation):
            gates.commit.allow.set()
            gates.acknowledgement.allow.set()


@dataclass
class RecordingCase:
    journal: sqlite.SqliteEvidenceJournal
    probe: JournalProbe
    clock: SampledClock
    coordinator: monitor.MonitorRecordingCoordinator
    provenance: model.SegmentProvenance

    async def rx(self, payload: bytes, timestamp: int = 123) -> model.EvidenceRecord:
        return await self.coordinator.append(
            evidence.PendingRxBytesEvidence(
                self.provenance.connection_id,
                self.provenance.segment_id,
                payload,
                model.BackendObservationTimestamp(
                    self.provenance.backend_observation_timestamp_domain.domain_id,
                    timestamp,
                ),
            )
        )

    async def start(self, condition: bytes, maximum: int = 1024) -> MonitorOperation:
        return await self.coordinator.start(
            monitor.MonitorRequest(self.journal.session_id, condition, 1000, maximum),
            run_id="annotation-recording-run",
            expected_provenance=self.provenance,
            revalidate=lambda: None,
            charge_markers=sqlite.charge_monitor_markers,
        )

    async def page(self) -> tuple[model.EvidenceRecord, ...]:
        page = await self.journal.retrieve(
            evidence.EvidenceRetrievalRequest(self.journal.session_id, 20, 20000)
        )
        assert page.outcome is evidence.EvidencePageOutcome.COMPLETE
        assert not page.truncated
        return page.records


@asynccontextmanager
async def recording_case(
    tmp_path: Path, index: int = 0
) -> AsyncIterator[RecordingCase]:
    journal = await sqlite.SqliteEvidenceJournal.create_v3(
        tmp_path / "v3.db", _policy()
    )
    probe, clock = JournalProbe(journal), SampledClock()
    coordinator = monitor.MonitorRecordingCoordinator(recorder=probe, clock=clock)
    case = RecordingCase(journal, probe, clock, coordinator, _provenance(index))
    try:
        await coordinator.append(
            evidence.PendingSegmentStartedEvidence(case.provenance)
        )
        yield case
    finally:
        probe.release()
        clock.advance(model.SQLITE_INTEGER_MAX)
        await _await(coordinator.close())


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["cli", "http", "core"])
@pytest.mark.parametrize("received", [0, 100, model.SQLITE_INTEGER_MAX])
async def test_insertion_returns_exact_attributed_record_from_same_writer(
    tmp_path: Path, surface: str, received: int
) -> None:
    async with recording_case(tmp_path) as case:
        append = annotation_entry(case.coordinator)
        case.clock.value = received
        text = " \tbuild e\u0301; 温度\r\n"
        accepted = await append(surface, text)
        assert accepted == model.ClientAnnotationEvidence(
            1, text, surface, case.clock.origin_id, received
        )
        assert accepted is case.probe.acknowledged[-1]
        assert accepted.assertion_class == "client_assertion"
        assert accepted.attribution_basis == "client_asserted"
        assert (await case.page()) == (case.probe.acknowledged[0], accepted)
        assert case.clock.samples == [received]
    assert case.probe.close_calls == 1


@pytest.mark.asyncio
async def test_receipt_sample_waits_for_same_gate_and_ack_precedes_next_rx(
    tmp_path: Path,
) -> None:
    async with recording_case(tmp_path) as case:
        append = annotation_entry(case.coordinator)
        case.probe.rx.acknowledgement.allow.clear()
        case.probe.annotation.acknowledgement.allow.clear()
        first = asyncio.create_task(case.rx(b"before", 11))
        queued = spawn(append("core", "queued assertion"))
        following: asyncio.Task[model.EvidenceRecord] | None = None
        try:
            await _await(case.probe.rx.acknowledgement.entered.wait())
            await _turn()
            assert not queued.done() and case.clock.samples == []
            assert len(case.probe.submitted) == 2  # Segment and preceding RX only.
            case.clock.advance(250)
            case.probe.rx.acknowledgement.allow.set()
            await _await(case.probe.annotation.acknowledgement.entered.wait())
            pending = case.probe.submitted[-1]
            assert isinstance(pending, evidence.PendingClientAnnotationEvidence)
            assert pending.received_at_ns == 250
            assert pending.clock_origin_id == case.clock.origin_id
            assert not queued.done()
            assert not any(
                isinstance(r, model.ClientAnnotationEvidence)
                for r in case.probe.acknowledged
            )
            following = asyncio.create_task(case.rx(b"after", 12))
            await _turn()
            assert len(case.probe.submitted) == 3 and not following.done()
            case.clock.advance(300)
            case.probe.annotation.acknowledgement.allow.set()
            before = await _await(first)
            annotation = await _await(queued)
            after = await _await(following)
            assert [r.sequence for r in (before, annotation, after)] == [1, 2, 3]
            assert isinstance(annotation, model.ClientAnnotationEvidence)
            assert annotation.received_at_ns == 250  # Not admission or ACK time.
            assert annotation is case.probe.acknowledged[2]
            assert (await case.page())[1:] == (before, annotation, after)
        finally:
            case.probe.release()
            await _await(asyncio.gather(first, queued, return_exceptions=True))
            if following is not None:
                await _await(asyncio.gather(following, return_exceptions=True))


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [-1, True, 1.5, model.SQLITE_INTEGER_MAX + 1])
async def test_invalid_insertion_clock_submits_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    async with recording_case(tmp_path) as case:
        append = annotation_entry(case.coordinator)
        monkeypatch.setattr(case.clock, "now_ns", lambda: bad)
        with pytest.raises((TypeError, ValueError)):
            await append("core", "not inserted")
        assert len(case.probe.submitted) == 1
        assert len(await case.page()) == 1


@pytest.mark.asyncio
async def test_backwards_insertion_clock_does_not_append_a_second_assertion(
    tmp_path: Path,
) -> None:
    async with recording_case(tmp_path) as case:
        append = annotation_entry(case.coordinator)
        await append("core", "first")
        case.clock.value = 99
        with pytest.raises(ValueError):
            await append("core", "backwards")
        assert len(case.probe.submitted) == 2
        assert len(await case.page()) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["before_commit", "after_commit"])
async def test_failed_append_propagates_without_success_reference_or_retry(
    tmp_path: Path, failure: str
) -> None:
    async with recording_case(tmp_path) as case:
        append = annotation_entry(case.coordinator)
        case.probe.failure = failure
        with pytest.raises(evidence.JournalFailure) as caught:
            await append("http", "possibly committed")
        assert caught.value is case.probe.error
        assert len(case.probe.submitted) == 2
        assert len(case.probe.acknowledged) == 1
        assert len(await case.page()) == (2 if failure == "after_commit" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
async def test_annotation_neither_matches_nor_resets_rx_prefix_or_byte_budget(
    tmp_path: Path, index: int
) -> None:
    async with recording_case(tmp_path, index) as case:
        append = annotation_entry(case.coordinator)
        operation = await case.start(b"PASS", maximum=4)
        await case.rx(b"PA", 11)
        accepted = await append("cli", "SS PASS " * 100)
        assert not operation.decided
        await case.rx(b"SS\0\xfftrailing", 12)
        report = await _await(operation.wait())
        assert report.outcome is model.MonitorOutcome.MATCHED
        assert report.examined_rx_bytes == 4 and report.observer_loss_records == 0
        assert report.match == model.MonitorMatch(
            model.MonitorMatchStart(2, 0), model.MonitorMatchEnd(4, 2)
        )
        assert report.window == model.SequenceRange(2, 5)
        assert accepted.sequence == 3 and report.durability == "complete"
        assert len(await case.page()) == 6


@pytest.mark.asyncio
async def test_annotation_advances_window_without_rx_match_or_loss(
    tmp_path: Path,
) -> None:
    async with recording_case(tmp_path) as case:
        append = annotation_entry(case.coordinator)
        operation = await case.start(b"PASS", maximum=4)
        await append("core", "PASS")
        assert not operation.decided
        case.clock.advance(1_000_000_100)
        report = await _await(operation.wait())
        assert report.outcome is model.MonitorOutcome.TIMEOUT
        assert report.window == model.SequenceRange(2, 3)
        assert report.examined_rx_bytes == report.observer_loss_records == 0
        assert report.match is None


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
async def test_delayed_annotation_uses_fresh_post_ack_monitor_time(
    tmp_path: Path, index: int
) -> None:
    async with recording_case(tmp_path, index) as case:
        append = annotation_entry(case.coordinator)
        operation = await case.start(b"PASS")
        await _await(case.clock.wait_started.wait())
        case.probe.annotation.acknowledgement.allow.clear()
        insertion = spawn(append("core", "PASS"))
        try:
            await _await(case.probe.annotation.acknowledgement.entered.wait())
            assert not insertion.done() and not operation.decided
            # Advance the hardware-free clock without waking the timer: publication
            # itself must notice expiry synchronously after the writer's ACK.
            case.clock.value = 1_000_000_107
            case.probe.annotation.acknowledgement.allow.set()
            accepted = await _await(insertion)
            assert accepted.received_at_ns == 100
            assert operation.decided, "publication reused the pre-ACK receipt sample"
            assert case.clock.samples[-1] == 1_000_000_107
            report = await _await(operation.wait())
            assert report.outcome is model.MonitorOutcome.TIMEOUT
            assert report.clock.decided_at_ns == 1_000_000_107
            assert report.clock.deadline_at_ns == 1_000_000_100
            assert report.window == model.SequenceRange(2, 2)
            assert report.examined_rx_bytes == report.observer_loss_records == 0
            assert report.match is None and report.durability == "complete"
            assert (await case.page())[accepted.sequence] == accepted
        finally:
            case.probe.release()
            await _await(asyncio.gather(insertion, return_exceptions=True))


@pytest.mark.asyncio
async def test_committed_but_unacknowledged_annotation_is_not_published_to_monitor(
    tmp_path: Path,
) -> None:
    async with recording_case(tmp_path) as case:
        append = annotation_entry(case.coordinator)
        operation = await case.start(b"PASS")
        await _await(case.clock.wait_started.wait())
        case.probe.annotation.acknowledgement.allow.clear()
        insertion = spawn(append("core", "not acknowledged yet"))
        try:
            await _await(case.probe.annotation.acknowledgement.entered.wait())
            assert not insertion.done()
            assert isinstance((await case.page())[-1], model.ClientAnnotationEvidence)
            case.clock.advance(1_000_000_100)
            await _turn()
            assert operation.decided
            case.probe.annotation.acknowledgement.allow.set()
            await _await(insertion)
            report = await _await(operation.wait())
            assert report.outcome is model.MonitorOutcome.TIMEOUT
            assert report.window == model.SequenceRange(2, 2)
            assert report.examined_rx_bytes == report.observer_loss_records == 0
        finally:
            case.probe.release()
            await _await(asyncio.gather(insertion, return_exceptions=True))
