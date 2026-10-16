"""010 T008 RED: real runtime admission, rate accounting and owned insertion.

Only journal/backend/clock boundaries are controlled. No annotation admission,
limiter or lifecycle policy is implemented here. `_seal_annotations()` follows
the existing Monitor seal as a provisional synchronous internal shutdown seam,
not a public delivery API. All assertions after missing-entry checks exercise
the actual runtime, T007 coordinator and temporary v3 journal.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import NoReturn, Protocol, runtime_checkable

import pytest

from dutchmate_core import annotation, evidence, model, monitor
from dutchmate_core import runtime as rt
from dutchmate_core.adapters import sqlite_evidence as sqlite
from dutchmate_core.adapters.terminal_evidence import (
    capture_terminal_target,
    open_terminal_reader,
)
from dutchmate_core.backend import Backend
from dutchmate_core.evidence_access import (
    EvidenceReadRejected,
    OwnedEvidenceReadPort,
    PreparedEvidenceAccess,
)
from dutchmate_core.profile import ResolvedDutProfile
from tests.contract.test_annotation_recording import JournalProbe, SampledClock, spawn
from tests.contract.test_monitor_recording import _await, _turn
from tests.contract.test_observation_runtime import _profile
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixture,
    BackendFixtureFactory,
    FixtureLifecycleGate,
)
from tests.integration.test_monitor import _durable_fixture


@runtime_checkable
class AnnotationRuntime(Protocol):
    # object deliberately admits malformed arguments to test the runtime guard.
    async def annotate(self, request: object) -> annotation.AnnotationReceipt: ...


@runtime_checkable
class AnnotationSeal(Protocol):
    def _seal_annotations(self) -> object: ...


@runtime_checkable
class PreparedConstructor(Protocol):
    def __call__(
        self,
        recorder: rt.ObservationRecorder,
        backend: Backend,
        evidence_access: PreparedEvidenceAccess | None,
        monitor_access: monitor.PreparedMonitorAccess | None,
        *,
        annotation_access: object,
    ) -> rt.PreparedObservationRun: ...


def prepared_constructor(candidate: object) -> PreparedConstructor:
    assert isinstance(candidate, PreparedConstructor)
    return candidate


def entry(
    owner: rt.ObservationRuntime,
) -> Callable[[object], Awaitable[annotation.AnnotationReceipt]]:
    assert isinstance(owner, AnnotationRuntime), (
        "T009 missing: ObservationRuntime.annotate"
    )
    return owner.annotate


def seal(owner: rt.ObservationRuntime) -> None:
    assert isinstance(owner, AnnotationSeal), (
        "T009 missing: synchronous annotation seal"
    )
    operation: Callable[[], object] = owner._seal_annotations
    assert operation() is None


def with_annotation(
    prepared: rt.PreparedObservationRun, access: object
) -> rt.PreparedObservationRun:
    assert "annotation_access" in {f.name for f in fields(prepared)}, (
        "T009 missing: PreparedObservationRun.annotation_access"
    )
    return prepared_constructor(type(prepared))(
        prepared.recorder,
        prepared.backend,
        prepared.evidence_access,
        prepared.monitor_access,
        annotation_access=access,
    )


class ChargeProbe:
    def __init__(self) -> None:
        self.calls: list[evidence.PendingClientAnnotationEvidence] = []
        self.result: object = None
        self.override = False

    def __call__(self, draft: evidence.PendingClientAnnotationEvidence) -> int:
        self.calls.append(draft)
        if self.override:
            # A malformed infrastructure callback, intentionally outside its
            # declared contract. setattr in the test supplies the bad callable.
            assert type(self.result) is int
            return self.result
        return sqlite.charge_client_annotation(draft)


class RuntimeJournal(JournalProbe):
    def __init__(self, journal: sqlite.SqliteEvidenceJournal) -> None:
        super().__init__(journal)
        self.segment_end = FixtureLifecycleGate()
        self.segment_ended = asyncio.Event()
        self.monitor_started = asyncio.Event()
        self.trace: list[str] = []

    async def append(
        self, draft: evidence.PendingEvidenceRecord
    ) -> model.EvidenceRecord:
        if isinstance(draft, evidence.PendingSegmentEndedEvidence):
            await self.segment_end.enter()
        record = await super().append(draft)
        if isinstance(record, model.ClientAnnotationEvidence):
            self.trace.append("annotation.ack")
        elif isinstance(record, model.SegmentEndedEvidence):
            self.trace.append("segment.ack")
            self.segment_ended.set()
        elif isinstance(record, model.OperationStartedEvidence):
            self.monitor_started.set()
        return record

    async def close(self) -> None:
        await super().close()
        self.trace.append("journal.closed")


@dataclass
class Case:
    owner: rt.ObservationRuntime
    profile: ResolvedDutProfile
    probe: RuntimeJournal
    fixture: BackendFixture
    coordinator: monitor.MonitorRecordingCoordinator
    clock: SampledClock
    charge: ChargeProbe
    access: object
    preparation: FixtureLifecycleGate
    backend_open: FixtureLifecycleGate
    tasks: list[Awaitable[object]]
    active: rt.RuntimeStatus | None = None
    monitor_support: bool = True
    evidence_support: bool = True
    terminal_opener: Callable[[], Awaitable[OwnedEvidenceReadPort]] | None = None
    present: bool = True

    def request(
        self, text: str = "build assertion", surface: str = "core"
    ) -> annotation.AnnotationRequest:
        return annotation.AnnotationRequest(self.probe.session_id, text, surface)

    def spawn[T](self, work: Awaitable[T]) -> asyncio.Task[T]:
        task = spawn(work)
        self.tasks.append(task)
        return task

    async def prepare(self, selected: ResolvedDutProfile) -> rt.PreparedObservationRun:
        assert selected == self.profile
        await self.preparation.enter()
        prepared = rt.PreparedObservationRun(
            self.coordinator,
            self.fixture.backend,
            PreparedEvidenceAccess(
                self.probe.session_id,
                self.probe.policy,
                self.probe.journal,
                self.terminal_opener,
            )
            if self.evidence_support
            else None,
            monitor.PreparedMonitorAccess(
                self.probe.session_id,
                self.probe.policy,
                self.coordinator,
                self.clock,
                sqlite.charge_monitor_markers,
            )
            if self.monitor_support
            else None,
        )
        return with_annotation(prepared, self.access) if self.present else prepared

    async def attach(self) -> rt.RuntimeStatus:
        self.active = await _await(self.owner.attach(self.profile, self.prepare))
        assert self.active.state is rt.RuntimeState.ACTIVE
        return self.active

    async def insert(
        self, text: str = "build assertion", surface: str = "core"
    ) -> annotation.AnnotationReceipt:
        return await _await(entry(self.owner)(self.request(text, surface)))

    async def reject(
        self, kind: str, request: annotation.AnnotationRequest | None = None
    ) -> None:
        before = sum(
            isinstance(d, evidence.PendingClientAnnotationEvidence)
            for d in self.probe.submitted
        )
        with pytest.raises(annotation.AnnotationRejected) as caught:
            await _await(
                entry(self.owner)(self.request() if request is None else request)
            )
        assert caught.value.kind == kind
        assert (
            sum(
                isinstance(d, evidence.PendingClientAnnotationEvidence)
                for d in self.probe.submitted
            )
            == before
        )

    async def fill(self, count: int = 10) -> None:
        for i in range(count):
            await self.insert(f"assertion {i}", ("cli", "http", "core")[i % 3])

    async def finish(self) -> None:
        self.probe.release()
        self.probe.segment_end.allow.set()
        self.preparation.allow.set()
        self.backend_open.allow.set()
        self.fixture.connection.close_gate.allow.set()
        self.clock.advance(model.SQLITE_INTEGER_MAX)
        await _await(
            asyncio.gather(self.owner.detach(), *self.tasks, return_exceptions=True)
        )
        if not self.probe.closed.is_set():
            await self.coordinator.close()


@asynccontextmanager
async def case(
    tmp_path: Path,
    factory: BackendFixtureFactory = BACKEND_FIXTURE_FACTORIES[0],
    *,
    attach: bool = True,
    present: bool = True,
    require_entry: bool = True,
    owner: rt.ObservationRuntime | None = None,
    clock: SampledClock | None = None,
    policy: model.SessionPolicy | None = None,
    version: int = 3,
) -> AsyncIterator[Case]:
    selected = _profile()
    if policy is not None:
        selected = replace(selected, session_policy=policy)
    tmp_path.mkdir(parents=True, exist_ok=True)
    create = {
        1: sqlite.SqliteEvidenceJournal.create,
        2: sqlite.SqliteEvidenceJournal.create_v2,
        3: sqlite.SqliteEvidenceJournal.create_v3,
    }[version]
    journal = await create(tmp_path / "runtime.db", selected.session_policy)
    probe, fixture = RuntimeJournal(journal), _durable_fixture(factory)
    clock = SampledClock() if clock is None else clock
    coordinator = monitor.MonitorRecordingCoordinator(recorder=probe, clock=clock)
    charge = ChargeProbe()
    open_gate = getattr(fixture.backend, "open_gate", None)
    assert isinstance(open_gate, FixtureLifecycleGate)
    instance = Case(
        rt.ObservationRuntime() if owner is None else owner,
        selected,
        probe,
        fixture,
        coordinator,
        clock,
        charge,
        annotation.PreparedAnnotationAccess(
            journal.session_id, journal.policy, coordinator, clock, charge
        ),
        FixtureLifecycleGate(),
        open_gate,
        [],
        present=present,
    )
    try:
        if require_entry:
            entry(instance.owner)
        if attach:
            await instance.attach()
        yield instance
    finally:
        await instance.finish()


@pytest.mark.asyncio
@pytest.mark.parametrize("positional_count", [2, 3, 4])
async def test_old_preparation_constructors_default_annotation_support_to_absent(
    tmp_path: Path, positional_count: int
) -> None:
    async with case(tmp_path, attach=False, require_entry=False) as c:
        if positional_count == 2:
            prepared = rt.PreparedObservationRun(c.coordinator, c.fixture.backend)
        elif positional_count == 3:
            prepared = rt.PreparedObservationRun(c.coordinator, c.fixture.backend, None)
        else:
            prepared = rt.PreparedObservationRun(
                c.coordinator, c.fixture.backend, None, None
            )
        assert getattr(prepared, "annotation_access", object()) is None, (
            "T009 missing: optional annotation_access=None on old constructors"
        )
        assert (
            prepared.recorder is c.coordinator and prepared.backend is c.fixture.backend
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [None, object(), {}, "session"])
async def test_request_type_guard_precedes_seal_and_association(bad: object) -> None:
    owner = rt.ObservationRuntime()
    method = entry(owner)
    seal(owner)
    before = owner.status()
    with pytest.raises(rt.RuntimeRejectedError) as caught:
        await method(bad)
    assert caught.value.kind is rt.RuntimeRejectedKind.INVALID_REQUEST
    assert owner.status() == before


@pytest.mark.parametrize(
    "context", ["other-loop", "other-thread", "no-loop", "closed-owner"]
)
def test_execution_context_guard_precedes_arguments_locks_and_scheduling(
    context: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop = asyncio.new_event_loop()

    async def construct() -> rt.ObservationRuntime:
        return rt.ObservationRuntime()

    owner = loop.run_until_complete(construct())
    try:
        method = entry(owner)
        if context == "closed-owner":
            loop.close()

        def forbidden(*args: object, **kwargs: object) -> NoReturn:
            pytest.fail("wrong-context annotation reached locking or scheduling")

        async def invoke() -> annotation.AnnotationReceipt:
            return await method(None)

        with monkeypatch.context() as patch:
            patch.setattr(asyncio.Lock, "acquire", forbidden)
            patch.setattr(asyncio, "create_task", forbidden)
            with pytest.raises(rt.RuntimeRejectedError) as caught:
                if context == "no-loop":
                    work = invoke()
                    try:
                        work.send(None)
                    finally:
                        work.close()
                elif context == "other-thread":
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(lambda: asyncio.run(invoke())).result(timeout=3)
                else:
                    asyncio.run(invoke())
            assert caught.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_global_seal_is_synchronous_permanent_and_precedes_association(
    tmp_path: Path,
) -> None:
    async with case(tmp_path, attach=False) as c:
        seal(c.owner)
        seal(c.owner)
        await c.reject("annotation_unavailable")
        await c.attach()
        await c.reject("annotation_unavailable")
        assert len(c.probe.submitted) == 1


@pytest.mark.asyncio
async def test_seal_checks_owner_execution_context() -> None:
    owner = rt.ObservationRuntime()
    entry(owner)

    async def invoke() -> None:
        seal(owner)

    with pytest.raises(rt.RuntimeRejectedError) as caught:
        await asyncio.to_thread(lambda: asyncio.run(invoke()))
    assert caught.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT


@pytest.mark.asyncio
async def test_no_association_submits_nothing(tmp_path: Path) -> None:
    async with case(tmp_path, attach=False) as c:
        await c.reject("no_associated_session")
        assert c.probe.submitted == [] and c.fixture.connection.consumer_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("present", [False, True])
async def test_session_mismatch_precedes_support_and_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, present: bool
) -> None:
    async with case(tmp_path, present=present) as c:

        def forbidden() -> NoReturn:
            pytest.fail("mismatched session sampled the admission clock")

        monkeypatch.setattr(c.clock, "now_ns", forbidden)
        await c.reject(
            "session_not_associated",
            replace(c.request(), session_id=model.SessionId("other")),
        )
        assert c.charge.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["attaching", "draining", "terminal"])
async def test_only_active_generation_can_admit(tmp_path: Path, stage: str) -> None:
    async with case(tmp_path, attach=False) as c:
        if stage == "attaching":
            c.backend_open.allow.clear()
            c.spawn(c.attach())
            await _await(c.backend_open.entered.wait())
        else:
            await c.attach()
            if stage == "draining":
                c.fixture.connection.close_gate.allow.clear()
                c.spawn(c.owner.detach())
                await _await(c.fixture.connection.close_gate.entered.wait())
            else:
                await c.owner.detach()
        await c.reject("not_active")
        assert c.charge.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [1, 2, 3])
async def test_old_preparation_attaches_and_reads_without_annotation_support(
    tmp_path: Path, version: int
) -> None:
    async with case(tmp_path, present=False, version=version) as c:
        await c.reject("annotation_unavailable")
        page = await c.owner.read_record(model.EvidenceReference(c.probe.session_id, 0))
        assert isinstance(page.page.records[0], model.SegmentStartedEvidence)
        assert c.owner.status().state is rt.RuntimeState.ACTIVE
        assert c.fixture.connection.consumer_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
@pytest.mark.parametrize("surface", ["cli", "http", "core"])
async def test_acknowledged_receipt_pins_exact_run_session_and_assertion(
    tmp_path: Path, factory: BackendFixtureFactory, surface: str
) -> None:
    async with case(tmp_path, factory) as c:
        text = " \tbuild e\u0301; 温度\r\n"
        receipt = await c.insert(text, surface)
        assert c.active is not None and c.active.run_id is not None
        assert receipt.run_id == c.active.run_id.value
        assert receipt.session_id == receipt.reference.session_id == c.probe.session_id
        assert receipt.reference.sequence == receipt.annotation.sequence == 1
        assert (
            receipt.annotation.text == text
            and receipt.annotation.client_surface == surface
        )
        assert receipt.annotation.received_at_ns == 100
        assert receipt.annotation.clock_origin_id == c.clock.origin_id
        assert receipt.annotation is c.probe.acknowledged[-1]
        assert receipt.annotation.assertion_class == "client_assertion"
        assert receipt.annotation.attribution_basis == "client_asserted"
        assert c.owner.status().state is rt.RuntimeState.ACTIVE
        assert c.owner.status().primary_issue is None
        assert c.fixture.connection.consumer_calls == 1
        assert c.fixture.connection.close_calls == 0
        assert c.owner.evidence_read_cleanup_confirmed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
@pytest.mark.parametrize("mismatch", ["object", "coordinator", "session", "clock"])
async def test_malformed_present_access_is_closed_before_any_backend_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    mismatch: str,
) -> None:
    async with case(tmp_path, factory, attach=False) as c:
        c.monitor_support = False  # Isolate annotation transfer validation.
        c.evidence_support = False
        assert isinstance(c.access, annotation.PreparedAnnotationAccess)
        if mismatch == "object":
            c.access = object()
        elif mismatch == "coordinator":
            other = monitor.MonitorRecordingCoordinator(recorder=c.probe, clock=c.clock)
            c.access = replace(c.access, coordinator=other)
        elif mismatch == "session":
            c.probe.session_id = model.SessionId("changed-before-transfer")
        else:
            monkeypatch.setattr(c.coordinator, "_clock", SampledClock())
        result = await _await(c.owner.attach(c.profile, c.prepare))
        assert result.state is rt.RuntimeState.FAILED
        assert result.terminal_reason is rt.RuntimeTerminalReason.STARTUP_FAILURE
        assert result.primary_issue == rt.RuntimeIssue(
            rt.RuntimeIssueSource.INTERNAL_CONTRACT, "internal_contract_failure"
        )
        assert result.owner_settled and result.attach_admissible
        assert result.physical_release_confirmed and result.recorder_close_confirmed
        assert result.acquisition is None and result.cleanup_issues == ()
        assert not c.backend_open.entered.is_set()
        assert c.fixture.connection.consumer_calls == 0 and c.probe.submitted == []
        assert c.probe.close_calls == 1


@pytest.mark.asyncio
async def test_missing_committed_segment_rejects_before_charge_or_time(
    tmp_path: Path,
) -> None:
    async with case(tmp_path) as c:
        provenance = c.coordinator.current_provenance
        assert provenance is not None
        await c.coordinator.append(
            evidence.PendingSegmentEndedEvidence(
                provenance.connection_id,
                provenance.segment_id,
                model.SegmentEndReason.DISCONNECTED,
            )
        )
        await c.reject("annotation_unavailable")
        assert c.charge.calls == [] and c.clock.samples == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
async def test_annotation_is_not_a_uart_capability(
    tmp_path: Path, factory: BackendFixtureFactory
) -> None:
    async with case(tmp_path, factory) as c:
        provenance = c.coordinator.current_provenance
        assert provenance is not None
        # Published session context, not a new backend capability or physical action.
        await c.coordinator.append(
            evidence.PendingSegmentStartedEvidence(
                replace(provenance, capabilities=model.BackendCapabilities(frozenset()))
            )
        )
        assert (await c.insert()).annotation.sequence == 2


@pytest.mark.asyncio
async def test_charge_preflight_uses_maximum_timestamp_with_exact_request(
    tmp_path: Path,
) -> None:
    async with case(tmp_path) as c:
        await c.insert("温度\r\n", "http")
        assert c.charge.calls == [
            evidence.PendingClientAnnotationEvidence(
                "温度\r\n", "http", c.clock.origin_id, model.SQLITE_INTEGER_MAX
            )
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ceiling",
    [
        "max_record_charged_bytes",
        "max_retained_charged_bytes",
        "max_retrieval_page_charged_bytes",
    ],
)
@pytest.mark.parametrize("charge", [2048, 2049])
async def test_each_charge_ceiling_accepts_equality_and_rejects_one_over(
    tmp_path: Path, ceiling: str, charge: int
) -> None:
    # SessionPolicy requires max_record to fit both other charge ceilings.
    policy = model.SessionPolicy(100, 100000, 2048, 128, 20, 100000)
    policy = replace(policy, **{ceiling: 2048})
    async with case(tmp_path, policy=policy) as c:
        c.charge.override, c.charge.result = True, charge
        if charge == 2049:
            await c.reject("evidence_policy_incompatible")
            assert c.clock.samples == []
        else:
            assert (await c.insert()).annotation.sequence == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [None, True, 0, -1, 1.5, model.SQLITE_INTEGER_MAX + 1])
async def test_malformed_charge_callback_is_unavailable_before_clock_or_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    async with case(tmp_path) as c:

        def invalid(
            _self: ChargeProbe, _draft: evidence.PendingClientAnnotationEvidence
        ) -> object:
            return bad

        monkeypatch.setattr(ChargeProbe, "__call__", invalid)
        await c.reject("annotation_unavailable")
        assert c.clock.samples == [] and len(c.probe.submitted) == 1


@pytest.mark.asyncio
async def test_policy_precedes_busy_and_busy_precedes_clock_and_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with case(tmp_path) as c:
        await c.fill(9)
        c.probe.annotation.acknowledgement.entered.clear()
        c.probe.annotation.acknowledgement.allow.clear()
        pending = c.spawn(entry(c.owner)(c.request()))
        await _await(c.probe.annotation.acknowledgement.entered.wait())
        c.charge.override, c.charge.result = True, model.SQLITE_INTEGER_MAX
        await c.reject("evidence_policy_incompatible")
        c.charge.override = False

        def forbidden() -> NoReturn:
            pytest.fail("busy annotation sampled the admission clock")

        with monkeypatch.context() as patch:
            patch.setattr(c.clock, "now_ns", forbidden)
            await c.reject("busy")
        c.probe.annotation.acknowledgement.allow.set()
        await _await(pending)
        await c.reject("rate_limited")


@pytest.mark.asyncio
async def test_pre_admission_rejections_consume_no_budget(tmp_path: Path) -> None:
    async with case(tmp_path) as c:
        for _ in range(12):
            await c.reject(
                "session_not_associated",
                replace(c.request(), session_id=model.SessionId("other")),
            )
            c.charge.override, c.charge.result = True, model.SQLITE_INTEGER_MAX
            await c.reject("evidence_policy_incompatible")
            c.charge.override = False
        await c.fill()
        await c.reject("rate_limited")


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [-1, 0, 1])
async def test_ten_attempt_window_excludes_exactly_one_second_old(
    tmp_path: Path, offset: int
) -> None:
    async with case(tmp_path) as c:
        await c.fill()
        await c.reject("rate_limited")
        c.clock.advance(1_000_000_100 + offset)
        if offset < 0:
            await c.reject("rate_limited")
        else:
            await c.fill()
            await c.reject("rate_limited")


@pytest.mark.asyncio
async def test_only_aged_samples_leave_the_window_across_many_rollovers(
    tmp_path: Path,
) -> None:
    async with case(tmp_path) as c:
        for round_number in range(4):
            base = 100 + round_number * 2_000_000_000
            c.clock.advance(base)
            await c.fill(5)
            c.clock.advance(base + 100)
            await c.fill(5)
            await c.reject("rate_limited")
            c.clock.advance(base + 1_000_000_000)
            await c.fill(5)
            await c.reject("rate_limited")


@pytest.mark.asyncio
async def test_rate_rejection_updates_last_check_without_admission_or_refund(
    tmp_path: Path,
) -> None:
    async with case(tmp_path) as c:
        await c.fill()
        c.clock.advance(999_999_999)
        await c.reject("rate_limited")
        c.clock.value = 999_999_998  # Still later than every insertion/admission.
        await c.reject("annotation_unavailable")
        c.clock.value = 1_000_000_100
        await c.fill()
        await c.reject("rate_limited")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [-1, True, 1.5, model.SQLITE_INTEGER_MAX + 1])
async def test_invalid_admission_sample_preserves_history_and_last_valid_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    async with case(tmp_path) as c:
        await c.fill(9)
        with monkeypatch.context() as patch:
            patch.setattr(c.clock, "now_ns", lambda: bad)
            await c.reject("annotation_unavailable")
        await c.insert()
        await c.reject("rate_limited")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin", ["not-a-uuid", "12345678-1234-1234-1234-123456789ABC"]
)
async def test_invalid_origin_is_annotation_only_unavailability_after_valid_attach(
    tmp_path: Path, origin: str
) -> None:
    async with case(tmp_path, attach=False) as c:
        c.clock.origin_id = origin
        await c.attach()
        await c.reject("annotation_unavailable")
        assert c.owner.status().state is rt.RuntimeState.ACTIVE
        assert c.charge.calls == [] and c.clock.samples == []


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_origin", [False, True])
async def test_reattach_and_surface_changes_do_not_reset_incarnation_budget(
    tmp_path: Path, changed_origin: bool
) -> None:
    owner, clock = rt.ObservationRuntime(), SampledClock()
    async with case(tmp_path / "first", owner=owner, clock=clock) as first:
        await first.fill()
        await owner.detach()
        if changed_origin:
            clock.origin_id = "87654321-4321-4321-4321-cba987654321"
            clock.advance(2_000_000_100)  # Even a fully aged window cannot rebind.
        async with case(tmp_path / "second", owner=owner, clock=clock) as second:
            await second.reject(
                "annotation_unavailable" if changed_origin else "rate_limited"
            )
            assert owner.status().state is rt.RuntimeState.ACTIVE
            if not changed_origin:
                clock.advance(1_000_000_100)
                await second.insert(surface="http")


@pytest.mark.asyncio
async def test_origin_binds_on_first_admission_not_on_attach_or_rejection(
    tmp_path: Path,
) -> None:
    owner, clock = rt.ObservationRuntime(), SampledClock()
    async with case(tmp_path / "first", owner=owner, clock=clock) as first:
        first.charge.override, first.charge.result = True, model.SQLITE_INTEGER_MAX
        await first.reject("evidence_policy_incompatible")
        await owner.detach()
        clock.origin_id = "87654321-4321-4321-4321-cba987654321"
        async with case(tmp_path / "second", owner=owner, clock=clock) as second:
            assert (await second.insert()).annotation.clock_origin_id == clock.origin_id


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["before_commit", "after_commit"])
async def test_admitted_journal_failures_consume_budget_without_changing_capture(
    tmp_path: Path, failure: str
) -> None:
    async with case(tmp_path) as c:
        await c.fill(9)
        before = len(c.probe.submitted)
        c.probe.failure = failure
        with pytest.raises(evidence.JournalFailure) as caught:
            await c.insert()
        assert caught.value is c.probe.error
        assert len(c.probe.submitted) == before + 1
        c.probe.failure = None
        await c.reject("rate_limited")
        assert c.owner.status().state is rt.RuntimeState.ACTIVE
        assert c.owner.status().primary_issue is None
        assert c.owner.evidence_read_cleanup_confirmed


@pytest.mark.asyncio
async def test_late_insertion_clock_fault_consumes_admission_without_fabricated_record(
    tmp_path: Path,
) -> None:
    async with case(tmp_path) as c:
        await c.fill(9)
        c.probe.rx.acknowledgement.allow.clear()
        await c.fixture.connection.emit_rx(b"ambient", timestamp=123)
        await _await(c.probe.rx.acknowledgement.entered.wait())
        delivery = c.spawn(entry(c.owner)(c.request()))
        await _turn()
        c.clock.value = -1
        c.probe.rx.acknowledgement.allow.set()
        with pytest.raises(Exception) as caught:
            await _await(delivery)
        assert not isinstance(caught.value, annotation.AnnotationRejected)
        assert (
            sum(
                isinstance(d, evidence.PendingClientAnnotationEvidence)
                for d in c.probe.submitted
            )
            == 9
        )
        c.clock.value = 100
        await c.reject("rate_limited")
        assert c.owner.status().primary_issue is None


@pytest.mark.asyncio
async def test_cancellation_observed_before_admission_submits_nothing(
    tmp_path: Path,
) -> None:
    async with case(tmp_path) as c:
        # Cancel the actual coroutine's Task before it starts; cancelling a
        # wrapper Task would strand an already-created inner coroutine.
        delivery = asyncio.create_task(c.owner.annotate(c.request()))
        c.tasks.append(delivery)
        delivery.cancel()  # The coroutine has not run its first step.
        with pytest.raises(asyncio.CancelledError):
            await delivery
        assert c.charge.calls == [] and c.clock.samples == []
        await c.fill()
        await c.reject("rate_limited")


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["gate_wait", "ack"])
@pytest.mark.parametrize("failed", [False, True])
async def test_repeated_waiter_cancellation_never_cancels_admitted_owner_or_consumes_twice(
    tmp_path: Path, phase: str, failed: bool
) -> None:
    async with case(tmp_path) as c:
        method = entry(c.owner)
        if phase == "gate_wait":
            c.probe.rx.acknowledgement.allow.clear()
            await c.fixture.connection.emit_rx(b"ambient", timestamp=123)
            await _await(c.probe.rx.acknowledgement.entered.wait())
        c.probe.annotation.acknowledgement.allow.clear()
        delivery = c.spawn(method(c.request()))
        await _turn()
        if phase == "ack":
            await _await(c.probe.annotation.acknowledgement.entered.wait())
        for _ in range(3):
            delivery.cancel()
            await _turn()
            assert not delivery.done()
            await c.reject("busy")
        if failed:
            c.probe.failure = "after_commit"
        c.probe.release()
        with pytest.raises(asyncio.CancelledError):
            await _await(delivery)
        c.probe.failure = None
        assert (
            sum(
                isinstance(d, evidence.PendingClientAnnotationEvidence)
                for d in c.probe.submitted
            )
            == 1
        )
        await c.fill(9)
        await c.reject("rate_limited")
        assert c.owner.status().state is rt.RuntimeState.ACTIVE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
@pytest.mark.parametrize("stop", ["detach", "disconnect", "seal"])
async def test_stop_seals_new_admission_and_joins_pending_ack_before_writer_close(
    tmp_path: Path, factory: BackendFixtureFactory, stop: str
) -> None:
    async with case(tmp_path, factory) as c:
        c.probe.annotation.acknowledgement.allow.clear()
        delivery = c.spawn(entry(c.owner)(c.request()))
        await _await(c.probe.annotation.acknowledgement.entered.wait())
        if stop == "seal":
            seal(c.owner)
            await c.reject("annotation_unavailable")
            stopping = c.spawn(c.owner.detach())
        elif stop == "disconnect":
            await c.fixture.connection.disconnect()
            await _turn()
            stopping = c.spawn(c.owner.detach())
        else:
            stopping = c.spawn(c.owner.detach())
        await _turn()
        assert not stopping.done() and c.probe.close_calls == 0
        if stop != "seal":
            await c.reject("not_active")
        c.probe.annotation.acknowledgement.allow.set()
        receipt = await _await(delivery)
        terminal = await _await(stopping)
        assert c.active is not None and c.active.run_id is not None
        assert receipt.run_id == c.active.run_id.value
        assert terminal.owner_settled and terminal.recorder_close_confirmed
        assert terminal.physical_release_confirmed and terminal.primary_issue is None
        assert terminal.terminal_reason is (
            rt.RuntimeTerminalReason.DISCONNECTED
            if stop == "disconnect"
            else rt.RuntimeTerminalReason.DETACHED
        )
        assert c.probe.trace.index("annotation.ack") < c.probe.trace.index(
            "journal.closed"
        )
        assert c.probe.close_calls == c.fixture.connection.close_calls == 1
        assert c.owner.evidence_read_cleanup_confirmed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
async def test_admitted_owner_can_insert_after_segment_end_without_active_revalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: BackendFixtureFactory
) -> None:
    async with case(tmp_path, factory) as c:
        entered, allow = asyncio.Event(), asyncio.Event()
        original = c.coordinator.append_client_annotation

        async def delayed(surface: str, text: str) -> model.ClientAnnotationEvidence:
            entered.set()
            await allow.wait()  # Test-only scheduling checkpoint before real insertion.
            return await original(surface, text)

        monkeypatch.setattr(c.coordinator, "append_client_annotation", delayed)
        delivery = c.spawn(entry(c.owner)(c.request()))
        try:
            await _await(entered.wait())
            stopping = c.spawn(c.owner.detach())
            await _await(c.probe.segment_ended.wait())
            assert c.probe.close_calls == 0 and not stopping.done()
            await c.reject("not_active")
            allow.set()
            receipt = await _await(delivery)
            terminal = await _await(stopping)
            assert receipt.annotation.sequence == 2
            assert c.probe.trace == ["segment.ack", "annotation.ack", "journal.closed"]
            assert (
                terminal.physical_release_confirmed
                and terminal.recorder_close_confirmed
            )
        finally:
            allow.set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
async def test_annotation_failure_leaves_monitor_reads_and_capture_facts_independent(
    tmp_path: Path, factory: BackendFixtureFactory
) -> None:
    async with case(tmp_path, factory) as c:
        watching = c.spawn(
            c.owner.monitor(
                monitor.MonitorRequest(c.probe.session_id, b"PASS", 1000, 1024)
            )
        )
        await _await(c.probe.monitor_started.wait())
        c.probe.annotation.acknowledgement.allow.clear()
        c.probe.failure = "after_commit"
        insertion = c.spawn(entry(c.owner)(c.request("PASS")))
        await _await(c.probe.annotation.acknowledgement.entered.wait())
        page = await c.owner.read_page(
            evidence.EvidenceRetrievalRequest(c.probe.session_id, 10, 16384)
        )
        assert isinstance(page.page.records[-1], model.ClientAnnotationEvidence)
        assert not watching.done()
        c.probe.annotation.acknowledgement.allow.set()
        with pytest.raises(evidence.JournalFailure):
            await _await(insertion)
        await c.fixture.connection.emit_rx(b"PASS\0\xffambient", timestamp=123)
        report = await _await(watching)
        assert report.outcome is model.MonitorOutcome.MATCHED
        assert report.examined_rx_bytes == 4 and report.observer_loss_records == 0
        assert report.durability == "complete"
        assert (
            c.owner.status().primary_issue is None
            and c.owner.evidence_read_cleanup_confirmed
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("interface", ["now_ns", "wait_until"])
async def test_unusable_clock_interface_precedes_charge_and_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interface: str
) -> None:
    async with case(tmp_path) as c:
        with monkeypatch.context() as patch:
            patch.setattr(c.clock, interface, None)
            await c.reject("annotation_unavailable")
        assert c.charge.calls == [] and c.clock.samples == []
        await c.fill()
        await c.reject("rate_limited")


@pytest.mark.asyncio
async def test_new_attach_clears_old_selection_before_preparation_finishes(
    tmp_path: Path,
) -> None:
    owner = rt.ObservationRuntime()
    async with case(tmp_path / "first", owner=owner) as first:
        await first.insert()
        await owner.detach()
        async with case(tmp_path / "next", owner=owner, attach=False) as second:
            second.preparation.allow.clear()
            attaching = second.spawn(second.attach())
            await _await(second.preparation.entered.wait())
            await second.reject("no_associated_session", first.request())
            second.preparation.allow.set()
            await _await(attaching)
            await second.reject("session_not_associated", first.request())


@pytest.mark.asyncio
async def test_changed_origin_does_not_disable_existing_monitor_or_attach(
    tmp_path: Path,
) -> None:
    owner, clock = rt.ObservationRuntime(), SampledClock()
    async with case(tmp_path / "first", owner=owner, clock=clock) as first:
        await first.insert()
        await owner.detach()
        clock.origin_id = "87654321-4321-4321-4321-cba987654321"
        async with case(tmp_path / "second", owner=owner, clock=clock) as second:
            await second.reject("annotation_unavailable")
            watching = second.spawn(
                owner.monitor(
                    monitor.MonitorRequest(second.probe.session_id, b"PASS", 1000, 1024)
                )
            )
            await _await(second.probe.monitor_started.wait())
            await second.fixture.connection.emit_rx(b"PASS", timestamp=123)
            assert (await _await(watching)).outcome is model.MonitorOutcome.MATCHED
            assert owner.status().state is rt.RuntimeState.ACTIVE


@pytest.mark.asyncio
async def test_dirty_terminal_reader_latch_survives_reattach_and_successful_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, clock = rt.ObservationRuntime(), SampledClock()
    async with case(
        tmp_path / "first", owner=owner, clock=clock, attach=False
    ) as first:
        target = capture_terminal_target(
            tmp_path / "first" / "runtime.db",
            session_id=first.probe.session_id,
            policy=first.probe.policy,
            expected_schema_version=3,
        )
        assert target is not None

        async def opener() -> OwnedEvidenceReadPort:
            assert first.probe.closed.is_set()
            reader = await open_terminal_reader(target)
            original_close = reader.close

            async def uncertain_close() -> None:
                await original_close()
                raise evidence.JournalFailure(
                    evidence.JournalOperation.CLOSE,
                    evidence.JournalFailureKind.IO_FAILURE,
                )

            monkeypatch.setattr(reader, "close", uncertain_close)
            return reader

        first.terminal_opener = opener
        await first.attach()
        receipt = await first.insert()
        terminal = await owner.detach()
        with pytest.raises(evidence.JournalFailure):
            await owner.read_record(receipt.reference)
        assert not owner.evidence_read_cleanup_confirmed
        assert owner.status() == terminal and terminal.attach_admissible
        async with case(tmp_path / "second", owner=owner, clock=clock) as second:
            active = owner.status()
            await second.insert()
            assert (
                owner.status() == active and not owner.evidence_read_cleanup_confirmed
            )
            with pytest.raises(EvidenceReadRejected) as caught:
                await owner.read_record(
                    model.EvidenceReference(second.probe.session_id, 0)
                )
            assert caught.value.kind == "read_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("sample", [0, model.SQLITE_INTEGER_MAX])
async def test_admission_and_insertion_accept_exact_signed64_endpoints(
    tmp_path: Path, sample: int
) -> None:
    async with case(tmp_path) as c:
        c.clock.value = sample
        receipt = await c.insert()
        assert receipt.annotation.received_at_ns == sample
        assert c.clock.samples == [sample, sample]  # Admission, then gated insertion.


@pytest.mark.asyncio
async def test_admission_sample_is_separate_from_gate_delayed_receipt_time(
    tmp_path: Path,
) -> None:
    async with case(tmp_path) as c:
        c.probe.rx.acknowledgement.allow.clear()
        await c.fixture.connection.emit_rx(b"ambient\0\xff", timestamp=123)
        await _await(c.probe.rx.acknowledgement.entered.wait())
        insertion = c.spawn(entry(c.owner)(c.request()))
        await _turn()
        assert c.clock.samples == [100] and not insertion.done()
        c.clock.advance(300)
        c.probe.rx.acknowledgement.allow.set()
        receipt = await _await(insertion)
        assert receipt.annotation.received_at_ns == 300
        assert c.clock.samples == [100, 300]
        assert receipt.annotation.sequence == 2


@pytest.mark.asyncio
async def test_access_validity_precedes_policy_busy_and_clock_sampling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with case(tmp_path) as c:
        c.probe.annotation.acknowledgement.allow.clear()
        pending = c.spawn(entry(c.owner)(c.request()))
        await _await(c.probe.annotation.acknowledgement.entered.wait())
        calls = len(c.charge.calls)
        c.charge.override, c.charge.result = True, model.SQLITE_INTEGER_MAX
        with monkeypatch.context() as patch:
            patch.setattr(c.clock, "wait_until", None)
            await c.reject("annotation_unavailable")
        assert len(c.charge.calls) == calls
        c.probe.annotation.acknowledgement.allow.set()
        await _await(pending)


@pytest.mark.asyncio
async def test_only_a_fresh_runtime_starts_a_fresh_budget(tmp_path: Path) -> None:
    async with case(tmp_path / "first") as first:
        await first.fill()
        await first.reject("rate_limited")
        async with case(tmp_path / "fresh") as fresh:
            await fresh.fill()
            await fresh.reject("rate_limited")
        await first.reject("rate_limited")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
async def test_concurrent_callers_register_one_owner_before_the_first_yield(
    tmp_path: Path, factory: BackendFixtureFactory
) -> None:
    async with case(tmp_path, factory) as c:
        c.probe.annotation.acknowledgement.allow.clear()
        first = c.spawn(entry(c.owner)(c.request("first", "cli")))
        second = c.spawn(entry(c.owner)(c.request("second", "http")))
        await _await(c.probe.annotation.acknowledgement.entered.wait())
        with pytest.raises(annotation.AnnotationRejected) as caught:
            await _await(second)
        assert caught.value.kind == "busy" and not first.done()
        assert (
            sum(
                isinstance(d, evidence.PendingClientAnnotationEvidence)
                for d in c.probe.submitted
            )
            == 1
        )
        c.probe.annotation.acknowledgement.allow.set()
        assert (await _await(first)).annotation.text == "first"
        await c.fill(9)
        await c.reject("rate_limited")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced-shaped"]
)
@pytest.mark.parametrize("adjustment", [-1, 0])
async def test_t014_real_max_width_charge_preflight_rejects_before_sampling_or_admission(
    tmp_path: Path, factory: BackendFixtureFactory, adjustment: int
) -> None:
    clock = SampledClock()
    text = "é" * 512
    maximum = evidence.PendingClientAnnotationEvidence(
        text, "http", clock.origin_id, model.SQLITE_INTEGER_MAX
    )
    conservative = sqlite.charge_client_annotation(maximum)
    actual = sqlite.charge_client_annotation(
        replace(maximum, received_at_ns=clock.value)
    )
    assert actual < conservative
    policy = model.SessionPolicy(
        100, 100000, conservative + adjustment, 128, 20, 100000
    )
    async with case(tmp_path, factory, clock=clock, policy=policy) as c:
        if adjustment < 0:
            await c.reject("evidence_policy_incompatible", c.request(text, "http"))
            assert c.clock.samples == []
            assert len(c.probe.submitted) == 1  # Only the committed segment start.
            assert c.charge.calls == [maximum]
            # Rejection consumed no admission; ten smaller legal claims still fit.
            await c.fill()
        else:
            receipt = await c.insert(text, "http")
            assert receipt.annotation.text.encode() == text.encode()
            assert receipt.annotation.received_at_ns == clock.value
            assert c.charge.calls == [maximum]
            await c.fill(9)
        await c.reject("rate_limited")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced-shaped"]
)
@pytest.mark.parametrize(
    "fault", ["backwards", "bool", "above-int64", "changed-origin"]
)
async def test_t014_staggered_partial_pruning_at_int64_max_preserves_history_after_bad_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    fault: str,
) -> None:
    maximum = model.SQLITE_INTEGER_MAX
    async with case(tmp_path, factory) as c:
        base = maximum - 1_000_000_000
        c.clock.advance(base)
        await c.fill(9)
        c.clock.advance(base + 1)
        await c.insert(surface="http")
        c.clock.advance(maximum - 1)
        await c.reject("rate_limited")
        with monkeypatch.context() as patch:
            if fault == "backwards":
                c.clock.value = maximum - 2
            elif fault == "changed-origin":
                patch.setattr(
                    c.clock, "origin_id", "87654321-4321-4321-4321-cba987654321"
                )
            else:
                patch.setattr(
                    c.clock, "now_ns", lambda: True if fault == "bool" else maximum + 1
                )
            await c.reject("annotation_unavailable")
        c.clock.value = maximum
        # Exactly the nine base samples age out; base+1 still occupies one slot.
        receipts = [
            await c.insert(f"edge-{i}", ("cli", "http", "core")[i % 3])
            for i in range(9)
        ]
        assert all(r.annotation.received_at_ns == maximum for r in receipts)
        await c.reject("rate_limited")
        assert c.owner.status().state is rt.RuntimeState.ACTIVE
        assert c.owner.status().primary_issue is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced-shaped"]
)
@pytest.mark.parametrize("failure", ["before_commit", "after_commit"])
async def test_t014_reattach_cannot_refund_a_failed_tenth_attempt_or_surface_budget(
    tmp_path: Path, factory: BackendFixtureFactory, failure: str
) -> None:
    owner, clock = rt.ObservationRuntime(), SampledClock()
    async with case(tmp_path / "first", factory, owner=owner, clock=clock) as first:
        await first.fill(9)
        first.probe.failure = failure
        with pytest.raises(evidence.JournalFailure):
            await first.insert(surface="http")
        first.probe.failure = None
        page = await owner.read_page(
            evidence.EvidenceRetrievalRequest(
                model.EvidenceRangeReference(first.probe.session_id, 1, 11),
                first.probe.policy.max_retrieval_page_records,
                first.probe.policy.max_retrieval_page_charged_bytes,
            )
        )
        claims = [
            r
            for r in page.page.records
            if isinstance(r, model.ClientAnnotationEvidence)
        ]
        assert len(claims) == (10 if failure == "after_commit" else 9)
        await owner.detach()
        async with case(
            tmp_path / "second", factory, owner=owner, clock=clock
        ) as second:
            for surface in ("cli", "http", "core"):
                await second.reject("rate_limited", second.request(surface=surface))
            clock.advance(1_000_000_100)
            await second.fill()
            await second.reject("rate_limited")
            assert owner.status().state is rt.RuntimeState.ACTIVE
            assert owner.status().primary_issue is None
            assert owner.evidence_read_cleanup_confirmed
