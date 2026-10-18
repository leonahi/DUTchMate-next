"""011 T006 RED: coordinator admission/wakeups over the actual v3 journal.

Provisional private seam for T007, not a public delivery/preparation contract:
coordinator.start_follow(request, *, run_id, reader, revalidate) returns an object
with immutable start, async pull()->FollowBatch|FollowEnd and async close().
Runtime admission, leases, seals and composition belong to T008/T009. The seam is
isolated in follow_entry so those later owners need not be implemented here.

Helpers gate real journal submission/ACKs only. No fake Follow registration,
notification, cursor, page consumption or result construction lives in this file.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

import pytest

from dutchmate_core import evidence, follow, model, monitor
from dutchmate_core.acquisition import Acquisition
from dutchmate_core.adapters import sqlite_evidence as sqlite
from dutchmate_core.evidence_access import EvidenceReadPort
from tests.contract.test_annotation_recording import MonitorOperation, SampledClock
from tests.contract.test_monitor_recording import AppendGates, _await, _turn
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixture, BackendFixtureFactory
from tests.integration.test_monitor import _durable_fixture

RUN = "follow-coordinator-run"
POLICY = model.SessionPolicy(200, 8_000_000, 2_000_000, 4096, 100, 2_000_000)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
    ),
]


class RecordingSubscription(Protocol):
    @property
    def start(self) -> follow.FollowStart: ...

    async def pull(self) -> follow.FollowBatch | follow.FollowEnd: ...

    async def close(self) -> None: ...


@runtime_checkable
class FollowEntry(Protocol):
    async def start_follow(
        self,
        request: follow.FollowRequest,
        *,
        run_id: str,
        reader: EvidenceReadPort,
        revalidate: Callable[[], None],
    ) -> RecordingSubscription: ...


def follow_entry(coordinator: monitor.MonitorRecordingCoordinator) -> FollowEntry:
    # A missing feature fails each test, never collection or fixture setup.
    assert isinstance(coordinator, FollowEntry), (
        "T007 missing: MonitorRecordingCoordinator.start_follow coordinator integration"
    )
    return coordinator


def kind(draft: evidence.PendingEvidenceRecord) -> str:
    if isinstance(draft, evidence.PendingOperationStartedEvidence):
        return "monitor_start"
    if isinstance(draft, evidence.PendingOperationEndedEvidence):
        return "monitor_end"
    if isinstance(draft, evidence.PendingClientAnnotationEvidence):
        return "annotation"
    if isinstance(draft, evidence.PendingSegmentStartedEvidence):
        return "segment_start"
    if isinstance(draft, evidence.PendingSegmentEndedEvidence):
        return "segment_end"
    if isinstance(draft, evidence.PendingObserverLossEvidence):
        return "loss"
    return "rx"


class JournalProbe:
    """Finite test observations around one actual journal, not a replacement."""

    def __init__(self, journal: sqlite.SqliteEvidenceJournal) -> None:
        self.journal = journal
        self.session_id, self.policy = journal.session_id, journal.policy
        self.gates = {
            name: AppendGates()
            for name in (
                "rx",
                "loss",
                "annotation",
                "monitor_start",
                "monitor_end",
                "segment_start",
                "segment_end",
            )
        }
        self.submitted: list[evidence.PendingEvidenceRecord] = []
        self.committed: dict[str, asyncio.Queue[model.EvidenceRecord]] = {
            name: asyncio.Queue() for name in self.gates
        }
        self.acknowledged: list[model.EvidenceRecord] = []
        self.failure: tuple[str, str] | None = None
        self.close_calls = 0

    async def append(
        self, draft: evidence.PendingEvidenceRecord
    ) -> model.EvidenceRecord:
        name = kind(draft)
        gates = self.gates[name]
        self.submitted.append(draft)
        await gates.commit.enter()
        if self.failure == (name, "before_commit"):
            self.failure = None
            raise evidence.JournalFailure(
                evidence.JournalOperation.APPEND, evidence.JournalFailureKind.IO_FAILURE
            )
        record = await self.journal.append(draft)
        self.committed[name].put_nowait(record)
        await gates.acknowledgement.enter()
        if self.failure == (name, "after_commit"):
            self.failure = None
            raise evidence.JournalFailure(
                evidence.JournalOperation.APPEND, evidence.JournalFailureKind.IO_FAILURE
            )
        self.acknowledged.append(record)
        return record

    async def close(self) -> None:
        self.close_calls += 1
        await self.journal.close()

    def release(self) -> None:
        for gates in self.gates.values():
            gates.commit.allow.set()
            gates.acknowledgement.allow.set()


class ReadProbe:
    """Observe/gate real reads while retaining the actual journal as reader."""

    def __init__(self, journal: sqlite.SqliteEvidenceJournal) -> None:
        self.original = journal.retrieve
        self.head = AppendGates()
        self.page = AppendGates()
        self.requests: list[evidence.EvidenceRetrievalRequest] = []
        self.completed: list[
            tuple[evidence.EvidenceRetrievalRequest, evidence.EvidencePage]
        ] = []

    @staticmethod
    def is_head(request: evidence.EvidenceRetrievalRequest) -> bool:
        ref = request.reference
        maximum = model.SQLITE_INTEGER_MAX
        return isinstance(ref, model.EvidenceRangeReference) and (
            ref.start_inclusive == ref.end_exclusive == maximum
        )

    async def retrieve(
        self, request: evidence.EvidenceRetrievalRequest
    ) -> evidence.EvidencePage:
        self.requests.append(request)
        gates = self.head if self.is_head(request) else self.page
        await gates.commit.enter()
        page = await self.original(request)
        self.completed.append((request, page))
        await gates.acknowledgement.enter()
        return page

    def release(self) -> None:
        for gates in (self.head, self.page):
            gates.commit.allow.set()
            gates.acknowledgement.allow.set()


@dataclass
class RecordingCase:
    journal: sqlite.SqliteEvidenceJournal
    probe: JournalProbe
    reads: ReadProbe
    clock: SampledClock
    coordinator: monitor.MonitorRecordingCoordinator
    fixture: BackendFixture
    acquisition: Acquisition
    tasks: list[asyncio.Task[Any]] = field(default_factory=list)
    subscriptions: list[RecordingSubscription] = field(default_factory=list)

    @property
    def provenance(self) -> model.SegmentProvenance:
        value = self.coordinator.current_provenance
        assert value is not None
        return value

    def spawn[T](self, work: Awaitable[T]) -> asyncio.Task[T]:
        async def run() -> T:
            return await work

        task = asyncio.create_task(run())
        self.tasks.append(task)
        return task

    async def start_follow(
        self, revalidate: Callable[[], None] = lambda: None
    ) -> RecordingSubscription:
        entry = follow_entry(self.coordinator)
        subscription = await entry.start_follow(
            follow.FollowRequest(self.journal.session_id),
            run_id=RUN,
            reader=self.journal,
            revalidate=revalidate,
        )
        self.subscriptions.append(subscription)
        return subscription

    async def rx(self, payload: bytes, timestamp: int = 100) -> model.EvidenceRecord:
        p = self.provenance
        return await self.coordinator.append(
            evidence.PendingRxBytesEvidence(
                p.connection_id,
                p.segment_id,
                payload,
                model.BackendObservationTimestamp(
                    p.backend_observation_timestamp_domain.domain_id, timestamp
                ),
            )
        )

    async def emit(self, payload: bytes, timestamp: int = 100) -> model.EvidenceRecord:
        await self.fixture.connection.emit_rx(payload, timestamp=timestamp)
        return await _await(self.probe.committed["rx"].get())

    async def start_monitor(self) -> MonitorOperation:
        return await self.coordinator.start(
            monitor.MonitorRequest(self.journal.session_id, b"\0\xffPASS", 1000, 1024),
            run_id=RUN,
            expected_provenance=self.provenance,
            revalidate=lambda: None,
            charge_markers=sqlite.charge_monitor_markers,
        )

    async def all_records(self) -> tuple[model.EvidenceRecord, ...]:
        result = await self.reads.original(
            evidence.EvidenceRetrievalRequest(
                self.journal.session_id,
                self.journal.policy.max_retrieval_page_records,
                self.journal.policy.max_retrieval_page_charged_bytes,
            )
        )
        assert not result.truncated
        return result.records


@asynccontextmanager
async def recording_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    *,
    policy: model.SessionPolicy = POLICY,
) -> AsyncIterator[RecordingCase]:
    journal = await sqlite.SqliteEvidenceJournal.create_v3(
        tmp_path / "follow-v3.db", policy
    )
    probe, reads, clock = JournalProbe(journal), ReadProbe(journal), SampledClock()
    coordinator = monitor.MonitorRecordingCoordinator(recorder=probe, clock=clock)
    acquisition = Acquisition(coordinator)
    fixture = _durable_fixture(factory)
    case = RecordingCase(
        journal, probe, reads, clock, coordinator, fixture, acquisition
    )
    monkeypatch.setattr(journal, "retrieve", reads.retrieve)
    try:
        await _await(acquisition.start(fixture.backend))
        assert coordinator.current_provenance is not None
        yield case
    finally:
        probe.release()
        reads.release()
        clock.advance(model.SQLITE_INTEGER_MAX)
        for subscription in case.subscriptions:
            await _await(subscription.close())
        for task in case.tasks:
            if not task.done():
                task.cancel()
        await _await(asyncio.gather(*case.tasks, return_exceptions=True))
        await _await(acquisition.stop())
        await _await(coordinator.close())


async def batch(subscription: RecordingSubscription) -> follow.FollowBatch:
    value = await _await(subscription.pull())
    assert isinstance(value, follow.FollowBatch), (
        "live pull must return evidence progress"
    )
    return value


async def idle_pull(
    case: RecordingCase, subscription: RecordingSubscription
) -> asyncio.Task[follow.FollowBatch | follow.FollowEnd]:
    case.reads.head.acknowledgement.entered.clear()
    pending = case.spawn(subscription.pull())
    await _await(case.reads.head.acknowledgement.entered.wait())
    await _turn()
    assert not pending.done(), "idle pull returned empty progress/heartbeat"
    return pending


async def test_start_uses_actual_committed_tail_current_provenance_and_no_replayed_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        old = await case.rx(b"old\0\xff")
        before = await case.all_records()
        captured = case.provenance
        subscription = await case.start_follow()
        assert subscription.start == follow.FollowStart(
            RUN, case.journal.session_id, 2, captured
        )
        assert await case.all_records() == before  # No durable Follow markers.
        assert len(case.reads.requests) == 1 and ReadProbe.is_head(
            case.reads.requests[0]
        )
        assert case.reads.completed[0][1].records == ()
        new = await case.rx(bytes(range(256)), 101)
        result = await batch(subscription)
        assert (
            result.gap is None
            and result.records == (new,)
            and old not in result.records
        )
        assert len(case.clock.samples) == 0  # Follow adds no evidence clock samples.


async def test_registration_head_probe_selects_no_payload_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        await case.rx(bytes(range(256)))

        def forbidden(*args: object, **kwargs: object) -> object:
            pytest.fail("metadata-only Follow start selected payload rows")

        with monkeypatch.context() as patch:
            patch.setattr(sqlite, "_read_bounded_evidence_page", forbidden)
            subscription = await case.start_follow()
        assert subscription.start.start_sequence == 2
        request, response = case.reads.completed[-1]
        assert request.reference == model.EvidenceRangeReference(
            case.journal.session_id, model.SQLITE_INTEGER_MAX, model.SQLITE_INTEGER_MAX
        )
        assert request.cursor is None and response.records == ()
        assert response.snapshot_end_exclusive == 2


async def test_append_ack_before_queued_start_is_excluded_from_start_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        follow_entry(case.coordinator)
        ack = case.probe.gates["rx"].acknowledgement
        ack.allow.clear()
        writing = case.spawn(case.rx(b"before admission"))
        await _await(ack.entered.wait())
        starting = case.spawn(case.start_follow())
        await _turn()
        assert case.reads.requests == [] and not starting.done()
        ack.allow.set()
        old = await _await(writing)
        subscription = await _await(starting)
        assert subscription.start.start_sequence == old.sequence + 1 == 2
        newer = await case.rx(b"after admission", 101)
        assert (await batch(subscription)).records == (newer,)


async def test_head_snapshot_and_registration_share_gate_with_queued_provenance_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        follow_entry(case.coordinator)
        original = case.provenance
        head_ack = case.reads.head.acknowledgement
        head_ack.allow.clear()
        starting = case.spawn(case.start_follow())
        await _await(head_ack.entered.wait())
        changed = replace(original, segment_id=model.SegmentId("next-segment"))
        changing = case.spawn(
            case.coordinator.append(evidence.PendingSegmentStartedEvidence(changed))
        )
        await _turn()
        assert not changing.done() and len(case.probe.submitted) == 1
        head_ack.allow.set()
        subscription = await _await(starting)
        boundary = await _await(changing)
        assert (
            subscription.start.provenance == original
            and subscription.start.start_sequence == 1
        )
        assert (await batch(subscription)).records == (boundary,)
        assert case.provenance == changed


async def test_head_read_is_revalidated_before_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        follow_entry(case.coordinator)
        sealed = False

        def revalidate() -> None:
            if sealed:
                raise follow.FollowRejected("not_active")

        ack = case.reads.head.acknowledgement
        ack.allow.clear()
        starting = case.spawn(case.start_follow(revalidate))
        await _await(ack.entered.wait())
        sealed = True
        ack.allow.set()
        with pytest.raises(follow.FollowRejected, match="not_active"):
            await _await(starting)
        replacement = await case.start_follow()
        assert replacement.start.start_sequence == 1


@pytest.mark.parametrize("phase", ["append_gate", "head_query"])
async def test_cancelled_admission_leaves_no_registration_and_does_not_cancel_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    phase: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        follow_entry(case.coordinator)
        writing = None
        if phase == "append_gate":
            ack = case.probe.gates["rx"].acknowledgement
            ack.allow.clear()
            writing = case.spawn(case.rx(b"committing"))
            await _await(ack.entered.wait())
        else:
            case.reads.head.acknowledgement.allow.clear()
        starting = case.spawn(case.start_follow())
        if phase == "head_query":
            await _await(case.reads.head.acknowledgement.entered.wait())
        else:
            await _turn()
        starting.cancel()
        case.probe.release()
        case.reads.release()
        with pytest.raises(asyncio.CancelledError):
            await _await(starting)
        if writing is not None:
            assert (await _await(writing)).sequence == 1
        replacement = await case.start_follow()
        assert replacement.start.start_sequence == (2 if writing is not None else 1)
        record = await case.rx(b"replacement only", 101)
        assert (await batch(replacement)).records == (record,)


@pytest.mark.parametrize("path", ["rx", "annotation", "monitor_start", "monitor_end"])
async def test_each_ack_path_wakes_idle_follow_without_changing_monitor_times(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    path: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        operation = await case.start_monitor() if path == "monitor_end" else None
        subscription = await case.start_follow()
        pending = await idle_pull(case, subscription)
        ack = case.probe.gates[path].acknowledgement
        ack.allow.clear()
        writing: asyncio.Task[object]
        if path == "rx":
            writing = case.spawn(case.rx(b"ambient\0\xff"))
        elif path == "annotation":
            writing = case.spawn(
                case.coordinator.append_client_annotation("cli", "exact\r\nassertion")
            )
        elif path == "monitor_start":
            writing = case.spawn(case.start_monitor())
        else:
            assert operation is not None
            case.clock.advance(1_000_000_100)
            writing = case.spawn(operation.wait())
        await _await(ack.entered.wait())
        expected = (await case.all_records())[-1]
        assert expected not in case.probe.acknowledged
        await _turn()
        assert not pending.done(), "an idle subscriber woke on an unacknowledged append"
        if path != "monitor_end":
            case.clock.advance(200)
        ack.allow.set()
        completed = await _await(writing)
        if path == "monitor_end":
            assert isinstance(completed, monitor.MonitorReport)
            report = completed
            assert report.clock == model.MonitorClockFacts(
                case.clock.origin_id, 100, 1_000_000_100, 1_000_000_100
            )
        result = await _await(pending)
        assert isinstance(result, follow.FollowBatch)
        assert result.gap is None and result.records == (expected,)
        if path == "monitor_start":
            operation = cast(MonitorOperation, completed)
            case.clock.advance(1_000_000_200)
            report = await _await(operation.wait())
            assert (
                report.clock.started_at_ns == 200
                and report.clock.deadline_at_ns == 1_000_000_200
            )


@pytest.mark.parametrize("path", ["rx", "annotation", "monitor_start", "monitor_end"])
async def test_ambiguous_commit_wake_is_a_hint_and_journal_supplies_the_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    path: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        operation = await case.start_monitor() if path == "monitor_end" else None
        subscription = await case.start_follow()
        pending = await idle_pull(case, subscription)
        case.probe.failure = (path, "after_commit")
        if path == "monitor_end":
            assert operation is not None
            case.clock.advance(1_000_000_100)
            report = await _await(operation.wait())
            assert report.durability == "end_unconfirmed"
        else:
            with pytest.raises(evidence.JournalFailure):
                if path == "rx":
                    await case.rx(b"committed without ACK")
                elif path == "annotation":
                    await case.coordinator.append_client_annotation(
                        "core", "commit uncertain"
                    )
                else:
                    await case.start_monitor()
        actual = (await case.all_records())[-1]
        assert actual not in case.probe.acknowledged
        result = await _await(pending)
        assert isinstance(result, follow.FollowBatch) and result.records == (actual,)
        later = await case.rx(b"later", 101)
        assert (await batch(subscription)).records == (later,)


async def test_start_after_ambiguous_ack_uses_actual_tail_not_last_published_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        case.probe.failure = ("annotation", "after_commit")
        with pytest.raises(evidence.JournalFailure):
            await case.coordinator.append_client_annotation(
                "core", "uncertain old record"
            )
        assert len(await case.all_records()) == 2 and len(case.probe.acknowledged) == 1
        subscription = await case.start_follow()
        assert subscription.start.start_sequence == 2
        record = await case.rx(b"new only")
        assert (await batch(subscription)).records == (record,)


@pytest.mark.parametrize("snapshot", ["head", "page"])
async def test_append_racing_empty_snapshot_and_wait_is_not_lost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    snapshot: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        subscription = await case.start_follow()
        if snapshot == "page":
            first = await case.rx(b"eligible")
        gates = case.reads.head if snapshot == "head" else case.reads.page
        gates.acknowledgement.entered.clear()
        gates.acknowledgement.allow.clear()
        pending = case.spawn(subscription.pull())
        await _await(gates.acknowledgement.entered.wait())
        case.probe.gates["rx"].commit.entered.clear()
        writing = case.spawn(case.rx(b"racing wake", 101))
        await _turn()
        # If a pull's head probe also uses the append gate, append is queued.
        # Otherwise force its ACK before returning the stale query snapshot.
        # Both valid gate choices must retain the hint across read/arm/wait.
        if case.probe.gates["rx"].commit.entered.is_set():
            await _await(writing)
        gates.acknowledgement.allow.set()
        newer = await _await(writing)
        result = await _await(pending)
        assert isinstance(result, follow.FollowBatch) and result.gap is None
        if snapshot == "page":
            assert result.records == (first,)
            assert (await batch(subscription)).records == (newer,)
        else:
            assert result.records == (newer,)


async def test_many_notifications_coalesce_and_every_next_page_uses_a_fresh_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        subscription = await case.start_follow()
        records = [await case.rx(bytes([n]), n) for n in range(65)]
        first = await batch(subscription)
        assert first.records == tuple(records[:32])
        extra = await case.rx(b"fresh head", 100)
        second, third = await batch(subscription), await batch(subscription)
        assert second.records == tuple(records[32:64])
        assert third.records == (records[64], extra)
        assert (
            len(case.reads.requests) == 7
        )  # Admission plus head/page per pull, no notification queue.
        pages = [r for r in case.reads.requests if not ReadProbe.is_head(r)]
        assert [r.reference for r in pages] == [
            model.EvidenceRangeReference(case.journal.session_id, 1, 66),
            model.EvidenceRangeReference(case.journal.session_id, 33, 67),
            model.EvidenceRangeReference(case.journal.session_id, 65, 67),
        ]
        assert all(
            r.cursor is None
            and r.max_records == 32
            and r.max_charged_bytes == 1_048_576
            for r in pages
        )


@pytest.mark.parametrize(
    ("record_cap", "charge_cap", "payload", "first_count"),
    [
        (2, 8192, b"small", 2),
        (4, 1800, b"x" * 1100, 1),
    ],
    ids=["record-policy", "charge-policy"],
)
async def test_pulls_respect_smaller_actual_journal_record_and_charge_policies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    record_cap: int,
    charge_cap: int,
    payload: bytes,
    first_count: int,
) -> None:
    policy = replace(
        POLICY,
        max_record_charged_bytes=charge_cap,
        max_retrieval_page_records=record_cap,
        max_retrieval_page_charged_bytes=charge_cap,
    )
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as case:
        subscription = await case.start_follow()
        records = tuple([await case.rx(payload, n) for n in range(3)])
        first = await batch(subscription)
        assert first.records == records[:first_count]
        request, response = case.reads.completed[-1]
        assert (
            request.max_records == record_cap
            and request.max_charged_bytes == charge_cap
        )
        assert response.charged_bytes <= charge_cap
        assert response.truncated and response.continuation is not None


async def test_failed_precommit_hint_never_fabricates_progress_or_consumes_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        subscription = await case.start_follow()
        pending = await idle_pull(case, subscription)
        case.probe.failure = ("annotation", "before_commit")
        with pytest.raises(evidence.JournalFailure):
            await case.coordinator.append_client_annotation("core", "never committed")
        for _ in range(3):
            await _turn()
        assert not pending.done()  # Optional false hint must only recheck the journal.
        assert len(await case.all_records()) == 1
        actual = await case.rx(b"first real progress")
        result = await _await(pending)
        assert isinstance(result, follow.FollowBatch)
        assert (
            result.gap is None and result.records == (actual,) and actual.sequence == 1
        )
