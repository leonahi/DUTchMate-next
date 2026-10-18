"""011 T017: real-journal Core lifetime races, without delivery or hardware.

Gates wrap existing resource work; none implement Follow/lifecycle/read policy.
Expected sequence/cutoff facts come from the explicit append history. Native
worker gates prove submitted work is joined rather than relying only on mocks.
"""

import asyncio
import sqlite3
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    RunEvidencePage,
)
from tests.contract.test_follow_recording import ReadProbe
from tests.contract.test_follow_runtime import (
    RuntimeCase,
    UnacknowledgedReaderClose,
    case,
    entry,
    pending_idle,
    seal,
)
from tests.contract.test_monitor_recording import _await, _turn
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixtureFactory
from tests.integration.test_annotations import assert_single_rx_owner

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
    ),
]


async def settled(owner: rt.ObservationRuntime) -> rt.RuntimeStatus:
    async def observe() -> rt.RuntimeStatus:
        while not owner.status().owner_settled:
            await _turn()
        return owner.status()

    return await _await(observe())


async def draining(owner: rt.ObservationRuntime) -> None:
    async def observe() -> None:
        while owner.status().state is not rt.RuntimeState.DETACHING:
            await _turn()

    await _await(observe())


def released(c: RuntimeCase, status: rt.RuntimeStatus) -> None:
    assert status.owner_settled and status.physical_release_confirmed
    assert status.recorder_close_confirmed and status.attach_admissible
    assert c.probe.close_calls == c.fixture.connection.close_calls == 1
    assert c.queries.active == c.queries.cancelled == 0
    assert c.owner.evidence_read_cleanup_confirmed
    assert_single_rx_owner(c.fixture)


@dataclass
class WorkerGate:
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: threading.Event = field(default_factory=threading.Event)
    selected: list[evidence.EvidenceRetrievalRequest] = field(default_factory=list)
    threads: list[int] = field(default_factory=list)
    materialized: evidence.EvidencePage | None = None


@asynccontextmanager
async def worker_gate(
    patch: pytest.MonkeyPatch, *, head: bool, after_materialization: bool
) -> AsyncIterator[WorkerGate]:
    gate, loop = WorkerGate(), asyncio.get_running_loop()
    original = sqlite._retrieve_page_on_worker

    def query(
        connection: sqlite3.Connection,
        policy: model.SessionPolicy,
        request: evidence.EvidenceRetrievalRequest,
        *,
        schema_version: int = 1,
    ) -> evidence.EvidencePage:
        selected = not gate.selected and ReadProbe.is_head(request) == head
        if selected:
            gate.selected.append(request)
            gate.threads.append(threading.get_ident())
            if after_materialization:
                gate.materialized = original(
                    connection, policy, request, schema_version=schema_version
                )
            loop.call_soon_threadsafe(gate.entered.set)
            assert gate.release.wait(5), "test did not release native journal worker"
            if after_materialization:
                assert gate.materialized is not None
                return gate.materialized
        return original(connection, policy, request, schema_version=schema_version)

    with patch.context() as local:
        local.setattr(sqlite, "_retrieve_page_on_worker", query)
        try:
            yield gate
        finally:
            gate.release.set()


async def test_cancel_before_first_start_step_never_claims_a_slot_or_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: BackendFixtureFactory
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        await c.activate()
        before = await c.records()

        async def start() -> object:
            return await entry(c.owner)(c.request())

        task = asyncio.create_task(start())
        c.tasks.append(task)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await _await(task)
        assert c.queries.requests == [] and await c.records() == before
        sub = await c.start()
        assert sub.start.start_sequence == 1
        record = await c.emit(b"still owned", 1)
        value = await _await(sub.pull())
        assert isinstance(value, follow.FollowBatch) and value.records == (record,)
        assert c.probe.close_calls == c.fixture.connection.close_calls == 0
        assert_single_rx_owner(c.fixture)


@pytest.mark.parametrize("phase", ["append_gate", "registered_result"])
async def test_repeated_cancelled_start_joins_gate_and_discards_late_registration_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    phase: str,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        await c.activate()
        entered, release = asyncio.Event(), asyncio.Event()
        captured: list[Any] = []
        writing = None
        if phase == "append_gate":
            ack = c.probe.gates["annotation"].acknowledgement
            ack.allow.clear()
            writing = c.spawn(
                c.owner.annotate(
                    annotation.AnnotationRequest(
                        c.journal.session_id, "in-flight claim", "core"
                    )
                )
            )
            await _await(ack.entered.wait())
        else:
            original = c.coordinator.start_follow

            async def registration(*args: Any, **kwargs: Any) -> Any:
                result = await original(*args, **kwargs)
                captured.append(result)
                entered.set()
                await release.wait()
                return result

            monkeypatch.setattr(c.coordinator, "start_follow", registration)
        task = c.spawn(entry(c.owner)(c.request()))
        if phase == "registered_result":
            await _await(entered.wait())
            await c.emit(b"commits after captured start", 1)
        else:
            await _turn()
            assert c.queries.requests == []
        for _ in range(3):
            task.cancel()
            await _turn()
            assert not task.done()
            await c.reject("busy")
        if phase == "append_gate":
            ack.allow.set()
        release.set()
        if writing is not None:
            receipt = await _await(writing)
            assert receipt.annotation.sequence == 1
        with pytest.raises(asyncio.CancelledError):
            await _await(task)
        for registered in captured:
            with pytest.raises(follow.FollowRejected, match="not_active"):
                await registered.pull()
        replacement = await c.start()
        assert replacement.start.start_sequence == 2
        assert c.owner.status().state is rt.RuntimeState.ACTIVE
        assert c.probe.close_calls == c.fixture.connection.close_calls == 0
        assert c.queries.active == c.queries.cancelled == 0


@pytest.mark.parametrize("phase", ["start_head", "pull_head", "pull_page"])
@pytest.mark.parametrize(
    "materialized", [False, True], ids=["submitted", "materialized"]
)
@pytest.mark.parametrize("stop", ["detach", "disconnect"])
async def test_native_read_survives_repeated_waiter_loss_and_joins_with_other_read_before_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    phase: str,
    materialized: bool,
    stop: str,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        await c.activate()
        await c.emit(b"before start", 1)
        sub = None
        if phase != "start_head":
            sub = await c.start()
            await c.emit(b"eligible\0\xff", 2)
        expected = await c.records()
        async with worker_gate(
            monkeypatch, head=phase != "pull_page", after_materialization=materialized
        ) as gate:
            pending = c.spawn(
                entry(c.owner)(c.request()) if sub is None else sub.pull()
            )
            await _await(gate.entered.wait())
            assert len(gate.threads) == 1 and gate.threads[0] != threading.get_ident()
            assert (gate.materialized is not None) == materialized
            c.queries.drain_entered()
            reading = c.spawn(c.ordinary_read())
            await _await(c.queries.entered.get())
            for _ in range(3):
                pending.cancel()
                await _turn()
                assert not pending.done() and not reading.done()
                assert c.queries.active == 2 and c.queries.cancelled == 0
            if stop == "disconnect":
                await c.fixture.connection.disconnect()
                stopping = c.spawn(settled(c.owner))
            else:
                stopping = c.spawn(c.owner.detach())
            await _turn()
            assert not stopping.done() and c.probe.close_calls == 0
            assert not c.owner.status().owner_settled
            gate.release.set()
            with pytest.raises(asyncio.CancelledError):
                await _await(pending)
            report = await _await(reading)
            assert isinstance(report, RunEvidencePage)
            assert report.page.records == expected
            assert report.page.snapshot_end_exclusive == (2 if sub is None else 3)
            released(c, await _await(stopping))
            assert c.probe.trace[-1] == "recorder.close"
            assert c.probe.trace.index("query.finished") < c.probe.trace.index(
                "recorder.close"
            )


async def test_idle_cancellation_ignores_eight_unrelated_reads_and_frees_only_follow_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: BackendFixtureFactory
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        await c.activate()
        sub = await c.start()
        pending = await pending_idle(c, sub)
        c.queries.drain_entered()
        c.queries.page.commit.allow.clear()
        readers = [c.spawn(c.ordinary_read()) for _ in range(8)]
        for _ in readers:
            await _await(c.queries.entered.get())
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await _await(pending)
        assert c.queries.active == 8 and not any(t.done() for t in readers)
        await c.reject("read_capacity")  # Freed Follow slot, unchanged read leases.
        record = await c.emit(b"ambient while unrelated reads wait", 1)
        assert record.sequence == 1 and c.probe.close_calls == 0
        c.queries.release()
        await _await(asyncio.gather(*readers))
        replacement = await c.start()
        assert replacement.start.start_sequence == 2
        assert c.owner.status().state is rt.RuntimeState.ACTIVE


@pytest.mark.parametrize("query", ["head", "page"])
async def test_reentrant_pull_and_repeated_close_waiter_loss_preserve_strong_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    query: str,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        await c.activate()
        sub = await c.start()
        await c.emit(b"undelivered", 1)
        gate = getattr(c.queries, query).acknowledgement
        gate.entered.clear()
        gate.allow.clear()
        pending = c.spawn(sub.pull())
        await _await(gate.entered.wait())
        before = len(c.queries.requests)
        with pytest.raises(follow.FollowRejected, match="busy"):
            await sub.pull()
        assert len(c.queries.requests) == before
        closer = c.spawn(sub.close())
        second = c.spawn(sub.close())
        await _turn()
        for _ in range(3):
            closer.cancel()
            await _turn()
            assert not closer.done() and not second.done() and not pending.done()
        gate.allow.set()
        with pytest.raises(follow.FollowRejected, match="not_active"):
            await _await(pending)
        with pytest.raises(asyncio.CancelledError):
            await _await(closer)
        await _await(second)
        await sub.close()
        assert c.queries.active == c.queries.cancelled == 0
        assert c.probe.close_calls == c.fixture.connection.close_calls == 0
        replacement = await c.start()
        assert replacement.start.start_sequence == 2
        assert_single_rx_owner(c.fixture)


async def test_close_wakes_idle_pull_without_record_or_shutdown_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: BackendFixtureFactory
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        await c.activate()
        sub = await c.start()
        pending = await pending_idle(c, sub)
        before = len(c.queries.requests)
        await _await(asyncio.gather(sub.close(), sub.close()))
        with pytest.raises(follow.FollowRejected, match="not_active"):
            await _await(pending)
        assert len(c.queries.requests) == before
        assert (await c.start()).start.start_sequence == 1
        assert c.probe.close_calls == c.fixture.connection.close_calls == 0


@pytest.mark.parametrize(
    "path", ["rx", "annotation", "monitor_start", "monitor_end", "read"]
)
@pytest.mark.parametrize("phase", ["commit", "acknowledgement"])
async def test_detach_seals_follow_while_admitted_append_monitor_annotation_or_read_joins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    path: str,
    phase: str,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        await c.activate()
        operation: asyncio.Task[Any] | None = None
        if path == "monitor_end":
            operation = c.spawn(
                c.owner.monitor(
                    monitor.MonitorRequest(c.journal.session_id, b"PASS", 1000, 1024)
                )
            )
            await _await(c.probe.committed["monitor_start"].get())
        sub = await c.start()
        pending = await pending_idle(c, sub)
        gates = c.queries.page if path == "read" else c.probe.gates[path]
        gate = getattr(gates, phase)
        gate.entered.clear()
        gate.allow.clear()
        if path == "rx":
            operation = c.spawn(c.emit(b"in-flight RX\0\xff", 1))
        elif path == "annotation":
            operation = c.spawn(
                c.owner.annotate(
                    annotation.AnnotationRequest(
                        c.journal.session_id, "in-flight assertion", "core"
                    )
                )
            )
        elif path == "monitor_start":
            operation = c.spawn(
                c.owner.monitor(
                    monitor.MonitorRequest(c.journal.session_id, b"PASS", 1000, 1024)
                )
            )
        elif path == "monitor_end":
            c.clock.advance(1_000_000_100)
        else:
            operation = c.spawn(c.ordinary_read())
        await _await(gate.entered.wait())
        stopping = c.spawn(c.owner.detach())
        await draining(c.owner)
        before = len(c.queries.requests)
        await c.reject("not_active")
        assert len(c.queries.requests) == before
        end = await _await(pending)
        assert isinstance(end, follow.FollowEnd) and end.reason == "detached"
        assert not hasattr(end, "next_sequence")
        assert not stopping.done() and c.probe.close_calls == 0
        gate.allow.set()
        assert operation is not None
        result = await _await(operation)
        if path.startswith("monitor"):
            assert isinstance(result, monitor.MonitorReport)
            assert result.outcome is (
                model.MonitorOutcome.TIMEOUT
                if path == "monitor_end"
                else model.MonitorOutcome.DETACHED
            )
        elif path == "annotation":
            assert result.annotation.text == "in-flight assertion"
        elif path == "read":
            assert result.page.records[0].sequence == 0
        released(c, await _await(stopping))
        assert await sub.pull() is end
        assert c.probe.trace[-1] == "recorder.close"


@pytest.mark.parametrize("trigger", ["disconnect", "recording_failure"])
@pytest.mark.parametrize(
    "intent",
    ["natural", "detach", "service_stop", "detach_then_stop", "stop_then_detach"],
)
@pytest.mark.parametrize(
    "early", [False, True], ids=["final-cutoff", "unknown-before-query-ack"]
)
async def test_source_and_stop_precedence_freezes_only_available_final_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    trigger: str,
    intent: str,
    early: bool,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        await c.activate()
        sub = await c.start()
        await c.emit(b"unoffered tail", 1)
        final = c.queries.head.acknowledgement
        final.entered.clear()
        final.allow.clear()
        if trigger == "disconnect":
            await c.fixture.connection.disconnect()
        else:
            c.probe.failure = ("rx", "before_commit")
            await c.fixture.connection.emit_rx(b"uncommitted", timestamp=2)
        await _await(final.entered.wait())
        detach = None
        if intent in ("service_stop", "stop_then_detach"):
            seal(c.owner)
        if intent in ("detach", "detach_then_stop", "stop_then_detach"):
            detach = c.spawn(c.owner.detach())
            await _turn()
        if intent == "detach_then_stop":
            seal(c.owner)
        reason: follow.FollowEndReason = (
            "service_stopping"
            if "stop" in intent
            else "detached"
            if intent == "detach"
            else "source_failed"
            if trigger == "recording_failure"
            else "source_ended"
        )
        head = 3 if trigger == "disconnect" else 2
        before = len(c.queries.requests)
        end = await _await(sub.pull()) if early else None
        if early:
            assert end == follow.FollowEnd(reason, None)
            assert c.probe.close_calls == 0
            assert len(c.queries.requests) == before  # No public reporting query.
        final.allow.set()
        terminal = (
            await _await(detach) if detach is not None else await settled(c.owner)
        )
        released(c, terminal)
        value = await _await(sub.pull())
        assert value == follow.FollowEnd(reason, None if early else head)
        if early:
            assert value is end
        assert not hasattr(value, "next_sequence")
        assert len(c.queries.requests) == before
        if trigger == "recording_failure":
            assert (
                terminal.primary_issue is not None
                and terminal.primary_issue.code == "recording_failure"
            )
        else:
            assert terminal.primary_issue is None


@pytest.mark.parametrize("stop", ["detach", "service_stop"])
async def test_prefetched_tail_is_discarded_without_waiting_for_consumer_or_claiming_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    stop: str,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        await c.activate()
        sub = await c.start()
        first = await c.emit(b"offered prefix", 1)
        offered = await _await(sub.pull())
        assert isinstance(offered, follow.FollowBatch) and offered.records == (first,)
        offered_position = 2  # A test caller fact, never a Core delivery field.
        tail = [await c.emit(bytes([n]), n) for n in range(2, 5)]
        entered, release = asyncio.Event(), asyncio.Event()
        captured: list[follow.FollowBatch | follow.FollowEnd] = []
        # Gate only return of an actual coordinator batch to its runtime caller.
        assert isinstance(sub, rt.FollowSubscription) and sub._registration is not None
        registration = sub._registration
        pull = registration.pull

        async def materialize() -> follow.FollowBatch | follow.FollowEnd:
            value = await pull()
            captured.append(value)
            entered.set()
            await release.wait()
            return value

        monkeypatch.setattr(registration, "pull", materialize)
        pending = c.spawn(sub.pull())
        try:
            await _await(entered.wait())
            assert isinstance(captured[0], follow.FollowBatch) and captured[
                0
            ].records == tuple(tail)
            assert c.queries.active == 0
            if stop == "service_stop":
                seal(c.owner)
            terminal = await _await(c.owner.detach())
            released(c, terminal)
            assert not pending.done()  # Teardown did not await a consumer/socket.
            release.set()
            end = await _await(pending)
            assert end == follow.FollowEnd(
                "service_stopping" if stop == "service_stop" else "detached", 6
            )
            assert offered_position == 2 and not hasattr(end, "next_sequence")
            assert await sub.pull() is end
        finally:
            release.set()


@pytest.mark.parametrize(
    "after_close", [False, True], ids=["close-failed", "close-ack-lost"]
)
@pytest.mark.parametrize("head_failure", [False, True])
async def test_recorder_close_uncertainty_keeps_follow_cutoff_separate_from_release_and_read_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    after_close: bool,
    head_failure: bool,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        raw_close = c.journal.close
        try:
            opened: list[str] = []

            async def forbidden_opener() -> OwnedEvidenceReadPort:
                opened.append("open")
                pytest.fail("uncertain writer close admitted a terminal reader")

            c.terminal_opener = forbidden_opener
            await c.activate()
            sub = await c.start()
            await c.emit(b"real source tail", 1)
            c.queries.head_failure = head_failure

            async def uncertain() -> None:
                if after_close:
                    await raw_close()
                raise evidence.JournalFailure(
                    evidence.JournalOperation.CLOSE,
                    evidence.JournalFailureKind.IO_FAILURE,
                )

            monkeypatch.setattr(c.journal, "close", uncertain)
            terminal = await _await(c.owner.detach())
            assert terminal.owner_settled and terminal.physical_release_confirmed
            assert (
                not terminal.recorder_close_confirmed and not terminal.attach_admissible
            )
            assert terminal.cleanup_issues == (
                rt.RuntimeIssue(
                    rt.RuntimeIssueSource.RECORDER_CLOSE,
                    evidence.JournalFailureKind.IO_FAILURE,
                ),
            )
            end = await sub.pull()
            assert end == follow.FollowEnd("detached", None if head_failure else 3)
            for _ in range(3):
                await sub.close()
            assert c.probe.close_calls == c.fixture.connection.close_calls == 1
            assert c.owner.evidence_read_cleanup_confirmed  # Independent008 latch.
            with pytest.raises(EvidenceReadRejected, match="read_unavailable"):
                await c.owner.read_record(
                    model.EvidenceReference(c.journal.session_id, 0)
                )
            assert opened == []
            assert_single_rx_owner(c.fixture)
        finally:
            monkeypatch.setattr(c.journal, "close", raw_close)
            await raw_close()  # Test resource cleanup, never a Core retry/ACK.
            c.probe.closed.set()  # Suppress the generic fixture's cleanup retry.


async def test_uncertain_terminal_read_cleanup_survives_old_follow_close_and_replacement_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: BackendFixtureFactory
) -> None:
    owner = rt.ObservationRuntime()
    async with case(tmp_path / "old", monkeypatch, factory, owner=owner) as old:
        target = capture_terminal_target(
            tmp_path / "old/follow-runtime.db",
            session_id=old.journal.session_id,
            policy=old.journal.policy,
            expected_schema_version=3,
        )
        assert target is not None

        async def uncertain() -> OwnedEvidenceReadPort:
            return UnacknowledgedReaderClose(await open_terminal_reader(target))

        old.terminal_opener = uncertain
        await old.activate()
        prior = await old.start()
        await owner.detach()
        end = await prior.pull()
        with pytest.raises(evidence.JournalFailure):
            await owner.read_record(model.EvidenceReference(old.journal.session_id, 0))
        assert not owner.evidence_read_cleanup_confirmed
        async with case(tmp_path / "new", monkeypatch, factory, owner=owner) as current:
            await current.activate()
            for _ in range(3):
                await prior.close()
                assert await prior.pull() is end
            await current.reject("follow_unavailable")
            claim = await owner.annotate(
                annotation.AnnotationRequest(
                    current.journal.session_id, "capture still admissible", "core"
                )
            )
            assert claim.annotation.sequence == 1
            assert (await current.emit(b"new capture", 1)).sequence == 2
            assert not owner.evidence_read_cleanup_confirmed
            released_status = await owner.detach()
            assert (
                released_status.recorder_close_confirmed
                and released_status.physical_release_confirmed
            )
            assert not owner.evidence_read_cleanup_confirmed
            assert_single_rx_owner(current.fixture)


@pytest.mark.parametrize("version", [1, 2, 3])
async def test_old_preparation_and_old_subscription_never_rebind_into_replacement_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    version: int,
) -> None:
    owner = rt.ObservationRuntime()
    async with case(
        tmp_path / "old", monkeypatch, factory, owner=owner, version=version
    ) as old:
        old.present = version == 3
        old_active = await old.activate()
        prior = await old.start() if version == 3 else None
        if version < 3:
            await old.reject("follow_unavailable")
        released(old, await owner.detach())
        old_end = await prior.pull() if prior is not None else None
        before = len(old.queries.requests)
        async with case(tmp_path / "new", monkeypatch, factory, owner=owner) as current:
            active = await current.activate()
            sub = await current.start()
            assert (
                active.run_id != old_active.run_id
                and active.session_id != old_active.session_id
            )
            pending = await pending_idle(current, sub)
            if prior is not None:
                await _await(asyncio.gather(prior.close(), prior.close()))
                assert await prior.pull() is old_end
            await current.reject("session_not_associated", old.request())
            assert len(old.queries.requests) == before
            record = await current.emit(b"new generation only\0\xff", 1)
            value = await _await(pending)
            assert isinstance(value, follow.FollowBatch) and value.records == (record,)
            assert current.probe.close_calls == 0 and old.probe.close_calls == 1
            assert_single_rx_owner(current.fixture)


async def test_fixed_read_capacity_end_is_not_relabelled_by_later_service_stop_or_detach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: BackendFixtureFactory
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        await c.activate()
        sub = await c.start()
        c.queries.drain_entered()
        c.queries.page.commit.allow.clear()
        readers = [c.spawn(c.ordinary_read()) for _ in range(8)]
        for _ in readers:
            await _await(c.queries.entered.get())
        end = await _await(sub.pull())
        assert end == follow.FollowEnd("read_capacity", None)
        seal(c.owner)
        stopping = c.spawn(c.owner.detach())
        await draining(c.owner)
        assert await sub.pull() is end and not stopping.done()
        c.queries.release()
        await _await(asyncio.gather(*readers))
        released(c, await _await(stopping))
        assert await sub.pull() is end
