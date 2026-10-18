"""011 T008 RED: actual runtime transfer, admission and submitted-read ownership.

Only existing backend/clock/journal boundaries are gated. No fake Follow runtime,
lease counter, generation selection, cancellation owner or lifecycle is supplied.
PreparedFollowAccess beside PreparedObservationRun and `_seal_follows()` describe
provisional internal transfer/shutdown seams, isolated below like existing Monitor
and annotation tests. Missing production fails inside tests, not at collection.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

import pytest

from dutchmate_core import annotation, evidence, follow, model, monitor
from dutchmate_core import runtime as rt
from dutchmate_core.adapters import sqlite_evidence as sqlite
from dutchmate_core.adapters.terminal_evidence import (
    capture_terminal_target,
    open_terminal_reader,
)
from dutchmate_core.evidence_access import (
    EvidenceReadRejected,
    OwnedEvidenceReadPort,
    PreparedEvidenceAccess,
)
from dutchmate_core.profile import ResolvedDutProfile
from tests.contract.test_annotation_recording import SampledClock
from tests.contract.test_follow_recording import (
    JournalProbe,
    ReadProbe,
    RecordingSubscription,
)
from tests.contract.test_monitor_recording import _await, _turn
from tests.contract.test_observation_runtime import _profile
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixtureFactory,
    FixtureLifecycleGate,
)
from tests.integration.test_annotations import assert_single_rx_owner
from tests.integration.test_monitor import _durable_fixture

_UNSET = object()

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
    ),
]


@runtime_checkable
class FollowRuntime(Protocol):
    async def start_follow(self, request: object) -> RecordingSubscription: ...


@runtime_checkable
class FollowSeal(Protocol):
    def _seal_follows(self) -> object: ...


class FollowTransfer(Protocol):
    @property
    def session_id(self) -> model.SessionId: ...

    @property
    def policy(self) -> model.SessionPolicy: ...

    @property
    def coordinator(self) -> monitor.MonitorRecordingCoordinator: ...

    @property
    def live_reader(self) -> OwnedEvidenceReadPort: ...


def entry(
    owner: rt.ObservationRuntime,
) -> Callable[[object], Awaitable[RecordingSubscription]]:
    assert isinstance(owner, FollowRuntime), (
        "T009 missing: ObservationRuntime.start_follow"
    )
    return owner.start_follow


def seal(owner: rt.ObservationRuntime) -> None:
    assert isinstance(owner, FollowSeal), (
        "T009 missing: synchronous ObservationRuntime._seal_follows"
    )
    assert cast(FollowSeal, owner)._seal_follows() is None, (
        "Follow seal must be synchronous"
    )


def access_factory() -> Callable[..., object]:
    value = getattr(rt, "PreparedFollowAccess", None)
    assert callable(value), "T009 missing: runtime.PreparedFollowAccess"
    return cast(Callable[..., object], value)


def with_follow(
    prepared: rt.PreparedObservationRun, access: object
) -> rt.PreparedObservationRun:
    assert "follow_access" in {f.name for f in fields(prepared)}, (
        "T009 missing: optional PreparedObservationRun.follow_access"
    )
    return cast(Callable[..., rt.PreparedObservationRun], replace)(
        prepared, follow_access=access
    )


class RuntimeJournal(JournalProbe):
    def __init__(self, journal: sqlite.SqliteEvidenceJournal) -> None:
        super().__init__(journal)
        self.trace: list[str] = []
        self.closed = asyncio.Event()

    async def append(
        self, draft: evidence.PendingEvidenceRecord
    ) -> model.EvidenceRecord:
        record = await super().append(draft)
        if isinstance(record, model.SegmentEndedEvidence):
            self.trace.append("segment_end.ack")
        return record

    async def close(self) -> None:
        self.trace.append("recorder.close")
        await super().close()
        self.closed.set()


class QueryProbe(ReadProbe):
    """Gate real journal queries, recording cancellation and settlement only."""

    def __init__(self, journal: sqlite.SqliteEvidenceJournal, trace: list[str]) -> None:
        super().__init__(journal)
        self.trace = trace
        self.entered: asyncio.Queue[evidence.EvidenceRetrievalRequest] = asyncio.Queue()
        self.active = 0
        self.cancelled = 0
        self.head_failure = False

    async def retrieve(
        self, request: evidence.EvidenceRetrievalRequest
    ) -> evidence.EvidencePage:
        self.active += 1
        self.entered.put_nowait(request)
        try:
            if self.is_head(request) and self.head_failure:
                self.requests.append(request)
                raise evidence.JournalFailure(
                    evidence.JournalOperation.RETRIEVE,
                    evidence.JournalFailureKind.IO_FAILURE,
                )
            return await super().retrieve(request)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.active -= 1
            self.trace.append("query.finished")

    def drain_entered(self) -> None:
        while not self.entered.empty():
            self.entered.get_nowait()


class RuntimeCase:
    def __init__(
        self,
        owner: rt.ObservationRuntime,
        journal: sqlite.SqliteEvidenceJournal,
        factory: BackendFixtureFactory,
        monkeypatch: pytest.MonkeyPatch,
        version: int,
    ) -> None:
        self.owner, self.journal, self.version = owner, journal, version
        self.profile = _profile()
        self.fixture = _durable_fixture(factory)
        self.clock = SampledClock()
        self.probe = RuntimeJournal(journal)
        self.queries = QueryProbe(journal, self.probe.trace)
        self.coordinator = monitor.MonitorRecordingCoordinator(
            recorder=self.probe, clock=self.clock
        )
        self.preparation = FixtureLifecycleGate()
        gate = getattr(self.fixture.backend, "open_gate", None)
        assert isinstance(gate, FixtureLifecycleGate)
        self.backend_open = gate
        self.tasks: list[asyncio.Task[Any]] = []
        self.subscriptions: list[RecordingSubscription] = []
        self.present = True
        self.access: object = _UNSET
        self.reader: object = journal
        self.terminal_opener: Callable[[], Awaitable[OwnedEvidenceReadPort]] | None = (
            None
        )
        self.prepared: rt.PreparedObservationRun | None = None
        self.active_status: rt.RuntimeStatus | None = None
        monkeypatch.setattr(journal, "retrieve", self.queries.retrieve)

    def request(self) -> follow.FollowRequest:
        return follow.FollowRequest(self.journal.session_id)

    def make_access(self) -> FollowTransfer:
        return cast(
            FollowTransfer,
            access_factory()(
                session_id=self.journal.session_id,
                policy=self.journal.policy,
                coordinator=self.coordinator,
                live_reader=self.journal,
            ),
        )

    def spawn[T](self, work: Awaitable[T]) -> asyncio.Task[T]:
        async def run() -> T:
            return await work

        task = asyncio.create_task(run())
        self.tasks.append(task)
        return task

    async def prepare(self, selected: ResolvedDutProfile) -> rt.PreparedObservationRun:
        assert selected == self.profile
        await self.preparation.enter()
        prepared = rt.PreparedObservationRun(
            recorder=self.coordinator,
            backend=self.fixture.backend,
            evidence_access=PreparedEvidenceAccess(
                self.journal.session_id,
                self.journal.policy,
                live_reader=cast(Any, self.reader),
                terminal_opener=self.terminal_opener,
            ),
            monitor_access=monitor.PreparedMonitorAccess(
                self.journal.session_id,
                self.journal.policy,
                self.coordinator,
                self.clock,
                sqlite.charge_monitor_markers,
            )
            if self.version >= 2
            else None,
            annotation_access=annotation.PreparedAnnotationAccess(
                self.journal.session_id,
                self.journal.policy,
                self.coordinator,
                self.clock,
                sqlite.charge_client_annotation,
            )
            if self.version == 3
            else None,
        )
        if self.present:
            prepared = with_follow(
                prepared, self.make_access() if self.access is _UNSET else self.access
            )
        self.prepared = prepared
        return prepared

    async def activate(self) -> rt.RuntimeStatus:
        result = await _await(self.owner.attach(self.profile, self.prepare))
        assert result.state is rt.RuntimeState.ACTIVE
        self.active_status = result
        await _await(self.fixture.connection.read_gate.entered.wait())
        return result

    async def start(self) -> RecordingSubscription:
        subscription = await _await(entry(self.owner)(self.request()))
        self.subscriptions.append(subscription)
        return subscription

    async def reject(self, kind: str, request: object = _UNSET) -> None:
        before = len(self.queries.requests)
        with pytest.raises(follow.FollowRejected) as caught:
            await entry(self.owner)(self.request() if request is _UNSET else request)
        assert caught.value.kind == kind
        assert len(self.queries.requests) == before

    async def emit(
        self, payload: bytes = b"\0\xffPASS", timestamp: int = 1
    ) -> model.EvidenceRecord:
        await self.fixture.connection.emit_rx(payload, timestamp=timestamp)
        return await _await(self.probe.committed["rx"].get())

    def ordinary_read(self) -> Awaitable[object]:
        return self.owner.read_page(
            evidence.EvidenceRetrievalRequest(
                self.journal.session_id,
                self.journal.policy.max_retrieval_page_records,
                self.journal.policy.max_retrieval_page_charged_bytes,
            )
        )

    async def records(self) -> tuple[model.EvidenceRecord, ...]:
        result = await self.queries.original(
            evidence.EvidenceRetrievalRequest(
                self.journal.session_id,
                self.journal.policy.max_retrieval_page_records,
                self.journal.policy.max_retrieval_page_charged_bytes,
            )
        )
        assert not result.truncated
        return result.records

    async def finish(self) -> None:
        self.probe.release()
        self.queries.release()
        self.preparation.allow.set()
        self.backend_open.allow.set()
        self.fixture.connection.close_gate.allow.set()
        self.clock.advance(model.SQLITE_INTEGER_MAX)
        for subscription in self.subscriptions:
            await _await(subscription.close())
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await _await(
            asyncio.gather(self.owner.detach(), *self.tasks, return_exceptions=True)
        )
        if not self.probe.closed.is_set():
            await _await(self.coordinator.close())


@asynccontextmanager
async def case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    *,
    owner: rt.ObservationRuntime | None = None,
    version: int = 3,
) -> AsyncIterator[RuntimeCase]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    create = {
        1: sqlite.SqliteEvidenceJournal.create,
        2: sqlite.SqliteEvidenceJournal.create_v2,
        3: sqlite.SqliteEvidenceJournal.create_v3,
    }[version]
    journal = await create(tmp_path / "follow-runtime.db", _profile().session_policy)
    c = RuntimeCase(
        rt.ObservationRuntime() if owner is None else owner,
        journal,
        factory,
        monkeypatch,
        version,
    )
    try:
        yield c
    finally:
        await c.finish()


async def pending_idle(
    c: RuntimeCase, subscription: RecordingSubscription
) -> asyncio.Task[follow.FollowBatch | follow.FollowEnd]:
    c.queries.head.acknowledgement.entered.clear()
    pending = c.spawn(subscription.pull())
    await _await(c.queries.head.acknowledgement.entered.wait())
    await _turn()
    assert not pending.done()
    return pending


@pytest.mark.parametrize("positional_count", [2, 3, 4, 5])
async def test_t008_follow_old_preparation_defaults_to_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    positional_count: int,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        args: list[object] = [c.coordinator, c.fixture.backend, None, None, None]
        constructor = cast(
            Callable[..., rt.PreparedObservationRun], rt.PreparedObservationRun
        )
        prepared = constructor(*args[:positional_count])
        assert getattr(prepared, "follow_access", _UNSET) is None, (
            "T009 missing: follow_access defaults to None"
        )
        assert (
            prepared.recorder is c.coordinator and prepared.backend is c.fixture.backend
        )


@pytest.mark.parametrize("version", [1, 2, 3])
async def test_t008_follow_existing_legacy_preparation_and_reads_remain_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    version: int,
) -> None:
    # Existing005/008 prerequisite, deliberately GREEN without Follow support.
    async with case(tmp_path, monkeypatch, factory, version=version) as c:
        c.present = False
        await c.activate()
        read = await c.owner.read_record(
            model.EvidenceReference(c.journal.session_id, 0)
        )
        assert isinstance(read.page.records[0], model.SegmentStartedEvidence)
        assert_single_rx_owner(c.fixture)


async def test_t008_follow_prepared_access_is_frozen_and_identifies_existing_coordinator_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        access = c.make_access()
        assert access.coordinator is c.coordinator
        assert access.live_reader is c.journal
        assert access.session_id == c.journal.session_id
        assert access.policy == c.journal.policy
        for field in ("session_id", "policy", "coordinator", "live_reader"):
            with pytest.raises(FrozenInstanceError):
                setattr(access, field, None)
        prepared = with_follow(
            rt.PreparedObservationRun(c.coordinator, c.fixture.backend), access
        )
        assert getattr(prepared, "follow_access", None) is access


@pytest.mark.parametrize(
    "mismatch", ["object", "session", "policy", "coordinator", "reader"]
)
async def test_t008_follow_malformed_present_transfer_fails_before_open_and_closes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    mismatch: str,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        if mismatch == "object":
            c.access = object()
        else:
            c.access = c.make_access()
            if mismatch == "session":
                object.__setattr__(c.access, "session_id", model.SessionId("foreign"))
            elif mismatch == "policy":
                object.__setattr__(
                    c.access,
                    "policy",
                    replace(c.journal.policy, max_retained_records=101),
                )
            elif mismatch == "coordinator":
                object.__setattr__(
                    c.access,
                    "coordinator",
                    monitor.MonitorRecordingCoordinator(
                        recorder=c.probe, clock=c.clock
                    ),
                )
            else:
                # A structurally valid existing read capability on the same
                # journal still differs by identity from the Follow transfer.
                from tests.contract.test_evidence_access import ReaderProbe

                c.reader = ReaderProbe(c.journal, c.probe.trace)
        # Check the new field before calling runtime.attach: a missing transfer
        # must be RED, not misclassified as an already-handled prepare exception.
        with_follow(
            rt.PreparedObservationRun(c.coordinator, c.fixture.backend), c.access
        )
        result = await _await(c.owner.attach(c.profile, c.prepare))
        assert result.state is rt.RuntimeState.FAILED
        assert result.primary_issue == rt.RuntimeIssue(
            rt.RuntimeIssueSource.INTERNAL_CONTRACT, "internal_contract_failure"
        )
        assert (
            result.owner_settled
            and result.physical_release_confirmed
            and result.recorder_close_confirmed
        )
        assert result.acquisition is None and result.attach_admissible
        assert c.probe.close_calls == 1 and not c.backend_open.entered.is_set()


@pytest.mark.parametrize("bad", [None, object(), {}, "session"])
async def test_t008_follow_request_validation_precedes_global_seal_and_association(
    factory: BackendFixtureFactory,
    bad: object,
) -> None:
    del factory
    owner = rt.ObservationRuntime()
    method = entry(owner)
    seal(owner)
    before = owner.status()
    with pytest.raises(rt.RuntimeRejectedError) as caught:
        await method(bad)
    assert (
        caught.value.kind is rt.RuntimeRejectedKind.INVALID_REQUEST
        and owner.status() == before
    )


async def test_t008_follow_global_seal_precedes_missing_association(
    factory: BackendFixtureFactory,
) -> None:
    del factory
    owner = rt.ObservationRuntime()
    method = entry(owner)
    seal(owner)
    with pytest.raises(follow.FollowRejected) as caught:
        await method(follow.FollowRequest(model.SessionId("explicit")))
    assert caught.value.kind == "not_active"


async def test_t008_follow_unassociated_runtime_rejects_without_query(
    factory: BackendFixtureFactory,
) -> None:
    del factory
    owner = rt.ObservationRuntime()
    with pytest.raises(follow.FollowRejected) as caught:
        await entry(owner)(follow.FollowRequest(model.SessionId("explicit")))
    assert caught.value.kind == "no_associated_session"


@pytest.mark.parametrize("present", [False, True])
async def test_t008_follow_session_rejection_precedes_missing_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    present: bool,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        c.present = present
        await c.activate()
        await c.reject(
            "session_not_associated",
            follow.FollowRequest(model.SessionId("wrong-session")),
        )
        assert c.queries.requests == []


@pytest.mark.parametrize("phase", ["attaching", "detaching", "terminal"])
async def test_t008_follow_only_active_generation_can_admit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    phase: str,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        if phase == "attaching":
            c.backend_open.allow.clear()
            c.spawn(c.owner.attach(c.profile, c.prepare))
            await _await(c.backend_open.entered.wait())
        else:
            await c.activate()
            if phase == "detaching":
                c.fixture.connection.close_gate.allow.clear()
                c.spawn(c.owner.detach())
                await _await(c.fixture.connection.close_gate.entered.wait())
            else:
                await c.owner.detach()
        await c.reject("not_active")


@pytest.mark.parametrize("version", [1, 2, 3])
async def test_t008_follow_absent_optional_support_rejects_without_reopening_legacy_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    version: int,
) -> None:
    async with case(tmp_path, monkeypatch, factory, version=version) as c:
        entry(c.owner)
        c.present = False
        await c.activate()
        await c.reject("follow_unavailable")
        assert c.owner.status().state is rt.RuntimeState.ACTIVE


async def test_t008_follow_start_captures_active_generation_and_exact_new_rx_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        active = await c.activate()
        await c.emit(b"old", 1)
        before = await c.records()
        subscription = await c.start()
        assert active.run_id is not None
        assert subscription.start.run_id == active.run_id.value
        assert (
            subscription.start.session_id == active.session_id == c.journal.session_id
        )
        assert subscription.start.start_sequence == 2
        assert subscription.start.provenance == c.coordinator.current_provenance
        assert await c.records() == before
        raw = await c.emit(bytes(range(256)), 2)
        result = await _await(subscription.pull())
        assert (
            isinstance(result, follow.FollowBatch)
            and result.gap is None
            and result.records == (raw,)
        )
        assert_single_rx_owner(c.fixture)


async def test_t008_follow_slot_is_independent_of_monitor_annotation_and_ordinary_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        subscription = await c.start()
        operation = c.spawn(
            c.owner.monitor(
                monitor.MonitorRequest(c.journal.session_id, b"\0\xffPASS", 1000, 1024)
            )
        )
        await _await(c.probe.committed["monitor_start"].get())
        receipt = await c.owner.annotate(
            annotation.AnnotationRequest(c.journal.session_id, "independent", "core")
        )
        await c.ordinary_read()
        await c.reject("busy")
        await c.emit()
        assert (await _await(operation)).outcome is model.MonitorOutcome.MATCHED
        result = await _await(subscription.pull())
        assert (
            isinstance(result, follow.FollowBatch)
            and receipt.annotation in result.records
        )
        assert c.owner.status().state is rt.RuntimeState.ACTIVE


async def test_t008_follow_one_pending_pull_rejects_reentrancy_without_extra_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        subscription = await c.start()
        pending = await pending_idle(c, subscription)
        before = len(c.queries.requests)
        with pytest.raises(follow.FollowRejected, match="busy"):
            await subscription.pull()
        assert len(c.queries.requests) == before
        record = await c.emit()
        result = await _await(pending)
        assert isinstance(result, follow.FollowBatch) and result.records == (record,)


async def test_t008_follow_idle_wait_uses_zero_of_eight_shared_read_leases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        subscription = await c.start()
        pending = await pending_idle(c, subscription)
        c.queries.drain_entered()
        c.queries.page.commit.allow.clear()
        readers = [c.spawn(c.ordinary_read()) for _ in range(8)]
        for _ in range(8):
            await _await(c.queries.entered.get())
        assert c.queries.active == 8 and not pending.done()
        with pytest.raises(EvidenceReadRejected, match="read_capacity"):
            await c.ordinary_read()
        await c.reject("busy")  # Follow owner precedence before read capacity.
        c.queries.page.commit.allow.set()
        await _await(asyncio.gather(*readers))
        assert not pending.done()


async def test_t008_follow_start_capacity_rejects_immediately_then_releases_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        c.queries.page.commit.allow.clear()
        readers = [c.spawn(c.ordinary_read()) for _ in range(8)]
        for _ in range(8):
            await _await(c.queries.entered.get())
        await c.reject("read_capacity")
        c.queries.page.commit.allow.set()
        await _await(asyncio.gather(*readers))
        assert (await c.start()).start.start_sequence == 1


async def test_t008_follow_submitted_head_shares_eight_leases_with_ordinary_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        c.queries.head.commit.allow.clear()
        pending = c.spawn(c.start())
        await _await(c.queries.head.commit.entered.wait())
        c.queries.drain_entered()
        c.queries.page.commit.allow.clear()
        readers = [c.spawn(c.ordinary_read()) for _ in range(7)]
        for _ in range(7):
            await _await(c.queries.entered.get())
        assert c.queries.active == 8
        with pytest.raises(EvidenceReadRejected, match="read_capacity"):
            await c.ordinary_read()
        await c.reject("busy")
        c.queries.release()
        await _await(asyncio.gather(pending, *readers))


async def test_t008_follow_pull_capacity_ends_subscription_without_stopping_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        subscription = await c.start()
        c.queries.drain_entered()
        c.queries.page.commit.allow.clear()
        readers = [c.spawn(c.ordinary_read()) for _ in range(8)]
        for _ in range(8):
            await _await(c.queries.entered.get())
        before = len(c.queries.requests)
        result = await _await(subscription.pull())
        assert result == follow.FollowEnd("read_capacity", None)
        assert len(c.queries.requests) == before and c.queries.active == 8
        c.queries.release()
        await _await(asyncio.gather(*readers))
        await subscription.close()
        assert (await c.start()).start.run_id == subscription.start.run_id
        assert isinstance(await c.emit(), model.RxBytesEvidence)


@pytest.mark.parametrize("phase", ["commit", "acknowledgement"])
async def test_t008_follow_cancelled_start_joins_query_and_unregisters_captured_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    phase: str,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        gate = getattr(c.queries.head, phase)
        gate.allow.clear()
        pending = c.spawn(entry(c.owner)(c.request()))
        await _await(gate.entered.wait())
        pending.cancel()
        await _turn()
        pending.cancel()
        await _turn()
        assert not pending.done() and c.queries.active == 1 and c.queries.cancelled == 0
        await c.reject("busy")
        gate.allow.set()
        with pytest.raises(asyncio.CancelledError):
            await _await(pending)
        assert c.queries.active == c.queries.cancelled == 0
        replacement = await c.start()
        assert replacement.start.start_sequence == 1
        assert c.owner.status().state is rt.RuntimeState.ACTIVE
        assert c.probe.close_calls == 0
        assert isinstance(await c.emit(), model.RxBytesEvidence)


@pytest.mark.parametrize("submitted", [False, True])
async def test_t008_follow_cancelled_pull_closes_only_captured_subscriber(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    submitted: bool,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        subscription = await c.start()
        if submitted:
            await c.emit()
            c.queries.page.acknowledgement.allow.clear()
            pending = c.spawn(subscription.pull())
            await _await(c.queries.page.acknowledgement.entered.wait())
        else:
            pending = await pending_idle(c, subscription)
        pending.cancel()
        await _turn()
        if submitted:
            assert not pending.done() and c.queries.active == 1
            await c.reject("busy")
            c.queries.page.acknowledgement.allow.set()
        with pytest.raises(asyncio.CancelledError):
            await _await(pending)
        assert c.queries.active == c.queries.cancelled == 0
        await subscription.close()
        await subscription.close()
        replacement = await c.start()
        assert replacement.start.run_id == subscription.start.run_id
        assert (
            c.owner.status().state is rt.RuntimeState.ACTIVE
            and c.probe.close_calls == 0
        )
        assert_single_rx_owner(c.fixture)


async def test_t008_follow_start_revalidates_after_head_and_cannot_escape_into_replacement_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    owner = rt.ObservationRuntime()
    async with case(tmp_path / "old", monkeypatch, factory, owner=owner) as c:
        entry(owner)
        active = await c.activate()
        c.queries.head.acknowledgement.allow.clear()
        pending = c.spawn(entry(owner)(c.request()))
        await _await(c.queries.head.acknowledgement.entered.wait())
        detach = c.spawn(owner.detach())
        await _turn()
        assert owner.status().state is rt.RuntimeState.DETACHING
        assert not pending.done() and not detach.done()
        c.queries.head.acknowledgement.allow.set()
        with pytest.raises(follow.FollowRejected, match="not_active"):
            await _await(pending)
        await _await(detach)
        async with case(tmp_path / "new", monkeypatch, factory, owner=owner) as new:
            current = await new.activate()
            subscription = await new.start()
            assert (
                current.run_id != active.run_id
                and current.session_id != active.session_id
            )
            assert current.run_id is not None
            assert subscription.start.run_id == current.run_id.value
            await new.reject("session_not_associated", c.request())
            assert c.probe.close_calls == 1


async def test_t008_follow_service_seal_wakes_idle_without_lifespan_detach_or_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        subscription = await c.start()
        pending = await pending_idle(c, subscription)
        before = len(c.queries.requests)
        seal(c.owner)
        seal(c.owner)
        result = await _await(pending)
        assert result == follow.FollowEnd("service_stopping", None)
        assert len(c.queries.requests) == before and c.probe.close_calls == 0
        assert c.owner.status().state is rt.RuntimeState.ACTIVE
        await c.reject("not_active", follow.FollowRequest(model.SessionId("wrong")))
        assert isinstance(await c.emit(), model.RxBytesEvidence)


async def test_t008_follow_detach_wakes_idle_before_blocked_cleanup_and_freezes_unknown_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        subscription = await c.start()
        pending = await pending_idle(c, subscription)
        c.fixture.connection.close_gate.allow.clear()
        detach = c.spawn(c.owner.detach())
        await _await(c.fixture.connection.close_gate.entered.wait())
        result = await _await(pending)
        assert result == follow.FollowEnd("detached", None)
        assert not detach.done() and c.probe.close_calls == 0
        await c.reject("not_active")
        before = len(c.queries.requests)
        assert await _await(subscription.pull()) == result
        assert len(c.queries.requests) == before
        c.fixture.connection.close_gate.allow.set()
        terminal = await _await(detach)
        assert terminal.recorder_close_confirmed and terminal.physical_release_confirmed
        assert result.source_end_exclusive is None
        assert await subscription.pull() == result


@pytest.mark.parametrize("head_failure", [False, True])
async def test_t008_follow_idle_subscriber_never_blocks_final_cutoff_and_recorder_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    head_failure: bool,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        subscription = await c.start()
        await c.emit()
        # No pull/socket/peer work exists during teardown. Only the teardown's
        # optional, single metadata probe can supply a final source cutoff.
        before = len(c.queries.requests)
        c.queries.head_failure = head_failure
        terminal = await _await(c.owner.detach())
        assert terminal.recorder_close_confirmed and terminal.physical_release_confirmed
        assert c.owner.evidence_read_cleanup_confirmed
        assert c.probe.closed.is_set() and c.probe.close_calls == 1
        final_queries = c.queries.requests[before:]
        assert len(final_queries) == 1 and all(
            c.queries.is_head(q) for q in final_queries
        )
        trace = c.probe.trace
        assert (
            trace.index("segment_end.ack")
            < len(trace) - 1 - trace[::-1].index("query.finished")
            < trace.index("recorder.close")
        )
        result = await _await(subscription.pull())
        assert result == follow.FollowEnd("detached", None if head_failure else 3)
        assert not hasattr(result, "next_sequence")
        assert len(c.queries.requests) == before + 1
        assert await subscription.pull() == result


async def test_t008_follow_detach_joins_materialized_query_before_close_and_discards_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        entry(c.owner)
        await c.activate()
        subscription = await c.start()
        await c.emit()
        c.queries.page.acknowledgement.allow.clear()
        pending = c.spawn(subscription.pull())
        await _await(c.queries.page.acknowledgement.entered.wait())
        assert c.queries.completed[-1][1].records  # Real SQLite materialization.
        before = len(c.queries.requests)
        detach = c.spawn(c.owner.detach())
        await _await(c.probe.committed["segment_end"].get())
        await _turn()
        assert not pending.done() and not detach.done() and c.probe.close_calls == 0
        c.queries.page.acknowledgement.allow.set()
        result = await _await(pending)
        assert isinstance(result, follow.FollowEnd) and result.reason == "detached"
        terminal = await _await(detach)
        assert (
            terminal.recorder_close_confirmed
            and c.queries.cancelled == c.queries.active == 0
        )
        assert len(c.queries.requests[before:]) <= 1
        assert all(c.queries.is_head(q) for q in c.queries.requests[before:])
        assert c.probe.trace[-1] == "recorder.close"


async def test_t008_follow_runtime_and_subscription_enforce_execution_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        method = entry(c.owner)
        await c.activate()
        subscription = await c.start()
        for operation in (
            lambda: method(c.request()),
            subscription.pull,
            subscription.close,
        ):

            async def foreign(
                operation: Callable[[], Awaitable[object]] = operation,
            ) -> None:
                with pytest.raises(rt.RuntimeRejectedError) as caught:
                    await operation()
                assert (
                    caught.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT
                )

            await _await(asyncio.to_thread(lambda: asyncio.run(foreign())))
        await c.reject("busy")
        record = await c.emit()
        result = await _await(subscription.pull())
        assert isinstance(result, follow.FollowBatch) and result.records == (record,)


class UnacknowledgedReaderClose:
    """Actual request-owned terminal reader; lose only the close acknowledgment."""

    def __init__(self, raw: OwnedEvidenceReadPort) -> None:
        self.raw = raw
        self.session_id, self.policy = raw.session_id, raw.policy

    async def retrieve(
        self, request: evidence.EvidenceRetrievalRequest
    ) -> evidence.EvidencePage:
        return await self.raw.retrieve(request)

    async def resolve_record(
        self, reference: model.EvidenceReference
    ) -> evidence.EvidencePage:
        return await self.raw.resolve_record(reference)

    async def close(self) -> None:
        await self.raw.close()
        raise evidence.JournalFailure(
            evidence.JournalOperation.CLOSE, evidence.JournalFailureKind.IO_FAILURE
        )


async def test_t008_follow_respects_permanent_read_cleanup_uncertainty_across_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    owner = rt.ObservationRuntime()
    async with case(tmp_path / "uncertain", monkeypatch, factory, owner=owner) as old:
        entry(owner)
        old.present = False
        target = capture_terminal_target(
            tmp_path / "uncertain" / "follow-runtime.db",
            session_id=old.journal.session_id,
            policy=old.journal.policy,
            expected_schema_version=3,
        )
        assert target is not None

        async def open_uncertain() -> OwnedEvidenceReadPort:
            return UnacknowledgedReaderClose(await open_terminal_reader(target))

        old.terminal_opener = open_uncertain
        await old.activate()
        await owner.detach()
        with pytest.raises(evidence.JournalFailure):
            await owner.read_record(model.EvidenceReference(old.journal.session_id, 0))
        assert not owner.evidence_read_cleanup_confirmed
        async with case(
            tmp_path / "replacement", monkeypatch, factory, owner=owner
        ) as new:
            active = await new.activate()
            assert active.state is rt.RuntimeState.ACTIVE
            await new.reject("follow_unavailable")
            terminal = await owner.detach()
            assert (
                terminal.recorder_close_confirmed
                and terminal.physical_release_confirmed
            )
            assert not owner.evidence_read_cleanup_confirmed
