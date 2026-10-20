"""012 T023: owned cancellation, teardown and generation races over SQLite4.

Only scheduling, backend work and real persistence boundaries are gated. Runtime,
Acquisition, matching, admission, read leases and cleanup policy remain real.
Watchdogs bound tests; they never impose a product write/join timeout.
"""

import asyncio
import sqlite3
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from dutchmate_core import annotation, evidence, follow, model, monitor
from dutchmate_core import runtime as rt
from dutchmate_core.adapters import sqlite_evidence as sqlite
from dutchmate_core.adapters.terminal_evidence import open_terminal_reader
from dutchmate_core.evidence_access import EvidenceReadRejected
from tests.contract.test_interact_recording import POLICY
from tests.contract.test_interact_runtime import RuntimeCase, until
from tests.contract.test_monitor_recording import _await, _turn
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixtureFactory
from tests.integration.test_annotations import assert_single_rx_owner

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced-shaped"]
    ),
]


@asynccontextmanager
async def case(
    path: Path,
    patch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    *,
    owner: rt.ObservationRuntime | None = None,
    attach: bool = True,
) -> AsyncIterator[RuntimeCase]:
    path.mkdir(parents=True, exist_ok=True)
    journal = await sqlite.SqliteEvidenceJournal.create_v4(path / "runtime.db", POLICY)
    raw_close = journal.close
    c = RuntimeCase(journal, factory, patch, path=path / "runtime.db", owner=owner)
    try:
        if attach:
            await c.attach()
        yield c
    finally:
        c.recorder.release()
        c.writer.allow.set()
        c.fixture.connection.close_gate.allow.set()
        await _await(c.owner.detach())
        await _await(asyncio.gather(*c.tasks, return_exceptions=True))
        # Test resource cleanup after a deliberately unconfirmed close is not a
        # Core retry or a new acknowledgement; assertions precede this cleanup.
        if not c.fixture.connection.closed:
            await c.writer.original_close()
        await _await(raw_close())


async def settled(owner: rt.ObservationRuntime) -> rt.RuntimeStatus:
    await until(lambda: owner.status().owner_settled)
    return owner.status()


async def busy(c: RuntimeCase) -> None:
    before = list(c.recorder.attempts)
    with pytest.raises(monitor.InteractRejected) as rejected:
        await _await(c.owner.interact(c.request()))
    assert rejected.value.kind == "busy" and c.recorder.attempts == before


async def freeze(c: RuntimeCase, decision: str) -> None:
    if decision == "timeout":
        c.clock.advance(1_000_000_100)
        await until(lambda: not c.clock.waiters)
        await _turn()
    else:
        await c.rx(b"PASS-tail" if decision == "matched" else b"xxxx-tail", 11)


async def stop(c: RuntimeCase, trigger: str) -> asyncio.Task[rt.RuntimeStatus]:
    if trigger == "detach":
        task = c.spawn(c.owner.detach())
    else:
        if trigger == "disconnect":
            await c.fixture.connection.disconnect()
        elif trigger == "recording":
            c.recorder.fail_before.add("rx_bytes")
            await c.fixture.connection.emit_rx(b"uncommitted", timestamp=12)
        else:
            assert trigger == "transport"
            await c.fixture.connection.end_stream_unexpectedly()
        task = c.spawn(settled(c.owner))

    # Natural teardown must join the held write before Runtime can publish a
    # terminal lifecycle state. Observe Acquisition's actual stop checkpoint.
    def stopping() -> bool:
        snapshot = c.owner.status().acquisition
        return snapshot is not None and snapshot.state.value == "stopping"

    await until(stopping)
    return task


async def test_cancel_before_first_step_has_no_intent_write_or_stale_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        before = await c.records()

        async def invoke() -> Any:
            return await c.owner.interact(c.request())

        waiter = asyncio.create_task(invoke())
        c.tasks.append(waiter)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await _await(waiter)
        assert await c.records() == before and c.writer.calls == []
        assert c.recorder.attempts == ["segment_started"]
        current = await c.begin()
        await c.rx(b"PASS")
        c.writer.allow.set()
        assert (await _await(current)).outcome.value == "matched"
        assert_single_rx_owner(c.fixture)


@pytest.mark.parametrize(
    "phase",
    [
        "intent-commit",
        "intent-ack",
        "after-intent-ack",
        "registered",
        "write",
        "observation",
        "tx-commit",
        "tx-ack",
        "end-commit",
        "end-ack",
    ],
)
async def test_repeated_waiter_cancellation_joins_every_boundary_and_preserves_submission_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    phase: str,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        boundary = asyncio.Event()
        gate = None
        if (
            phase.split("-")[0] in {"intent", "tx", "end"}
            and phase != "after-intent-ack"
        ):
            name, edge = phase.split("-")
            kind = {
                "intent": "interact_started",
                "tx": "uart_tx_settled",
                "end": "interact_ended",
            }[name]
            gate = getattr(
                c.recorder.gates[kind],
                "commit" if edge == "commit" else "acknowledgement",
            )
            gate.allow.clear()
        waiter: asyncio.Task[Any]
        registrations: list[int] = []
        if phase == "observation":
            gate = c.recorder.gates["interact_ended"].acknowledgement
            gate.allow.clear()
        if phase == "after-intent-ack":

            def cancelled_after_ack() -> None:
                assert not c.writer.calls and registrations == []
                assert c.trace[-1] == "interact_started.ack"
                waiter.cancel()
                boundary.set()

            c.recorder.after_ack["interact_started"] = cancelled_after_ack
        if phase in {"after-intent-ack", "registered"}:
            from dutchmate_core.acquisition import Acquisition

            original_submit = Acquisition.submit_uart_write

            def registered(acquisition: Acquisition, payload: bytes) -> Any:
                registrations.append(waiter.cancelling())
                work = original_submit(acquisition, payload)
                assert not c.writer.calls  # Strong registration precedes invocation.
                if phase == "registered":
                    waiter.cancel()
                    boundary.set()
                return work

            monkeypatch.setattr(Acquisition, "submit_uart_write", registered)
        waiter = c.spawn(c.owner.interact(c.request()))
        try:
            if phase in {"after-intent-ack", "registered"}:
                await _await(boundary.wait())
            elif phase.startswith("intent"):
                assert gate is not None
                await _await(gate.entered.wait())
                assert c.writer.calls == []
            else:
                await _await(c.writer.entered.wait())
                if phase == "write" or phase.startswith("end"):
                    await c.rx(b"PASS")
                if phase == "observation":
                    c.writer.allow.set()
                    await _await(c.recorder.acks["uart_tx_settled"].get())
                    assert c.clock.waiters
                elif phase != "write":
                    c.writer.allow.set()
                    assert gate is not None
                    await _await(gate.entered.wait())
            for _ in range(3):
                waiter.cancel()
                await _turn()
                assert not waiter.done()
                await busy(c)
            assert c.writer.close_calls == 0 and not c.recorder.closed.is_set()
        finally:
            c.recorder.release()
            c.writer.allow.set()
        with pytest.raises(asyncio.CancelledError):
            await _await(waiter)
        rows = await c.records()
        intents = [r for r in rows if isinstance(r, model.InteractStartedEvidence)]
        txs = [r for r in rows if isinstance(r, model.UartTxSettledEvidence)]
        ends = [r for r in rows if isinstance(r, model.InteractEndedEvidence)]
        assert len(intents) == len(txs) == len(ends) == 1
        end = ends[0]
        if phase == "after-intent-ack":
            # Contract§3 requires the post-ACK cancellation recheck before
            # registration. The spy records the public waiter's pending request;
            # it never latches a stop or changes the production admission branch.
            assert registrations == [], (
                f"write admitted with cancellation counts {registrations}"
            )
        submitted = phase not in {"intent-commit", "intent-ack", "after-intent-ack"}
        assert end.tx.submitted is submitted
        assert c.writer.calls == ([b"\0\xffSEND"] if submitted else [])
        assert end.tx.status == ("acknowledged" if submitted else "not_submitted")
        assert end.tx.accepted_prefix_bytes == (6 if submitted else None)
        assert end.outcome.value == (
            "matched" if phase.startswith("end") else "cancelled"
        )
        assert end.observation.outcome.value == (
            "matched" if phase == "write" or phase.startswith("end") else "cancelled"
        )
        assert end.tx == txs[0].tx and end.tx_settled_sequence == txs[0].sequence
        assert end.tx_audit_failure is None and c.writer.cancellation_signals == 0
        assert c.owner.status().state is rt.RuntimeState.ACTIVE
        assert c.clock.waiters == {}
        c.recorder.after_ack.clear()
        if phase in {"after-intent-ack", "registered"}:
            monkeypatch.setattr(Acquisition, "submit_uart_write", original_submit)
        for kind in ("interact_started", "uart_tx_settled", "interact_ended"):
            assert c.recorder.attempts.count(kind) == 1
        assert_single_rx_owner(c.fixture)


@pytest.mark.parametrize("decision", ["matched", "timeout", "byte_limit"])
@pytest.mark.parametrize("trigger", ["cancel", "service"])
@pytest.mark.parametrize(
    "stop_first", [False, True], ids=["observation-first", "stop-first"]
)
async def test_stop_match_and_deadline_races_preserve_first_observation_until_write_join(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    decision: str,
    trigger: str,
    stop_first: bool,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        waiter = await c.begin(c.request(conditions=(b"PASS",), max_rx_bytes=4))
        await _await(c.writer.entered.wait())

        async def latch() -> None:
            if trigger == "service":
                c.owner._seal_interacts()
            else:
                waiter.cancel()
                await _turn()
                await _turn()

        if stop_first:
            await latch()
        await freeze(c, decision)
        if not stop_first:
            await latch()
        assert not waiter.done() and c.writer.active == 1
        c.writer.allow.set()
        if trigger == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await _await(waiter)
        else:
            assert (await _await(waiter)).outcome.value == "service_stopping"
        ends = [
            r for r in await c.records() if isinstance(r, model.InteractEndedEvidence)
        ]
        assert len(ends) == 1
        end = ends[0]
        expected_stop = "cancelled" if trigger == "cancel" else "service_stopping"
        assert end.outcome.value == expected_stop
        assert end.observation.outcome.value == (
            expected_stop if stop_first else decision
        )
        assert end.observation.clock.decided_at_ns == (
            1_000_000_100 if decision == "timeout" and not stop_first else 100
        )
        assert end.observation.examined_rx_bytes == (
            4 if decision != "timeout" and not stop_first else 0
        )
        assert (end.observation.match is not None) == (
            decision == "matched" and not stop_first
        )
        assert end.tx.status == "acknowledged" and end.tx.accepted_prefix_bytes == 6
        assert c.writer.cancellation_signals == 0 and c.clock.waiters == {}


@pytest.mark.parametrize("trigger", ["detach", "disconnect", "recording", "transport"])
@pytest.mark.parametrize("audit", ["uart_tx_settled", "interact_ended"])
@pytest.mark.parametrize("lost_ack", [False, True])
@pytest.mark.parametrize("frozen", ["matched", "timeout", "byte_limit"])
async def test_natural_and_explicit_teardown_close_physical_owner_while_audit_is_still_joining(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    trigger: str,
    audit: str,
    lost_ack: bool,
    frozen: str,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        gate = c.recorder.gates[audit].acknowledgement
        gate.allow.clear()
        if lost_ack:
            c.recorder.fail_ack.add(audit)
        original_close = c.fixture.connection.close

        async def physical_close() -> None:
            await original_close()
            c.trace.append("physical.closed")

        monkeypatch.setattr(c.fixture.connection, "close", physical_close)
        waiter = await c.begin(c.request(conditions=(b"PASS",), max_rx_bytes=4))
        await _await(c.writer.entered.wait())
        await freeze(c, frozen)
        closing = await stop(c, trigger)
        try:
            assert not waiter.done() and not closing.done()
            assert c.writer.close_calls == 0 and not c.recorder.closed.is_set()
            c.writer.allow.set()
            await _await(gate.entered.wait())
            await until(lambda: "physical.closed" in c.trace)
            assert (
                c.writer.active_at_close == [0] and c.writer.cancellation_signals == 0
            )
            assert c.writer.timeline.index("write_settled") < c.writer.timeline.index(
                "close_entered"
            )
            assert (
                not c.recorder.closed.is_set()
                and not closing.done()
                and not waiter.done()
            )
            if trigger == "detach":
                for _ in range(3):
                    closing.cancel()
                    await _turn()
                    assert not closing.done()
            with pytest.raises(rt.RuntimeRejectedError) as rejected:
                await _await(c.owner.attach(c.profile, c.prepare))
            assert rejected.value.kind is rt.RuntimeRejectedKind.BUSY
        finally:
            gate.allow.set()
        report = await _await(waiter)
        if trigger == "detach":
            with pytest.raises(asyncio.CancelledError):
                await _await(closing)
            terminal = await settled(c.owner)
        else:
            terminal = await _await(closing)
        assert (
            report.outcome.value
            == {
                "detach": "detached",
                "disconnect": "disconnected",
                "recording": "recording_failure",
                "transport": "transport_failure",
            }[trigger]
        )
        assert report.observation.outcome.value == frozen
        assert report.observation.examined_rx_bytes == (0 if frozen == "timeout" else 4)
        assert report.tx.accepted_prefix_bytes == 6
        expected_durability = (
            "complete"
            if not lost_ack
            else "tx_unconfirmed"
            if audit == "uart_tx_settled"
            else "end_unconfirmed"
        )
        assert report.durability == expected_durability
        assert [f.record_kind for f in report.audit_failures] == (
            [audit] if lost_ack else []
        )
        assert (
            terminal.owner_settled
            and terminal.physical_release_confirmed
            and terminal.recorder_close_confirmed
        )
        assert c.trace.index("physical.closed") < c.trace.index("journal.closed")
        assert c.recorder.attempts.count("interact_ended") == 1
        assert c.writer.close_calls == 1 and not c.recorder.close_during_append
        readback = await c.owner.read_page(
            evidence.EvidenceRetrievalRequest(c.journal.session_id, 100, 131072)
        )
        assert [
            r.payload
            for r in readback.page.records
            if isinstance(r, model.RxBytesEvidence)
        ] == (
            []
            if frozen == "timeout"
            else [b"PASS-tail" if frozen == "matched" else b"xxxx-tail"]
        )
        assert (
            sum(
                isinstance(r, model.InteractEndedEvidence)
                for r in readback.page.records
            )
            == 1
        )
        assert_single_rx_owner(c.fixture)


@pytest.mark.parametrize("frozen", ["matched", "timeout", "byte_limit"])
async def test_origin_reset_after_frozen_observation_never_reuses_prefix_or_relabels_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    frozen: str,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        original = c.coordinator.current_provenance
        assert original is not None
        waiter = await c.begin(c.request(conditions=(b"PASS",), max_rx_bytes=4))
        await _await(c.writer.entered.wait())
        await freeze(c, frozen)
        domain = original.backend_observation_timestamp_domain
        replacement = replace(
            domain,
            domain_id=domain.domain_id + "-new",
            origin_id=domain.origin_id + "-new",
        )
        await c.fixture.connection.reset_timestamp_origin(replacement)
        await _await(c.recorder.acks["segment_ended"].get())
        await _await(c.recorder.acks["segment_started"].get())
        await c.rx(b"PASS\0new-origin", 1)
        assert not waiter.done() and c.writer.close_calls == 0
        c.writer.allow.set()
        report = await _await(waiter)
        assert report.outcome.value == "timestamp_origin_reset"
        assert report.observation.outcome.value == frozen
        assert (
            report.provenance == original
            and report.tx.clock_origin_id == c.clock.origin_id
        )
        assert c.coordinator.current_provenance is not None
        assert (
            c.coordinator.current_provenance.backend_observation_timestamp_domain
            == replacement
        )
        assert report.observation.window.end_exclusive == (
            2 if frozen == "timeout" else 3
        )
        assert_single_rx_owner(c.fixture)


@pytest.mark.parametrize(
    "audit", ["interact_started", "uart_tx_settled", "interact_ended"]
)
@pytest.mark.parametrize("after_commit", [False, True])
async def test_native_audit_work_joins_repeated_cancellation_and_detach_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    audit: str,
    after_commit: bool,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        loop = asyncio.get_running_loop()
        entered, release = asyncio.Event(), threading.Event()
        threads: list[int] = []
        original = sqlite._append_on_worker
        wanted: (
            type[evidence.PendingInteractStartedEvidence]
            | type[evidence.PendingUartTxSettledEvidence]
            | type[evidence.PendingInteractEndedEvidence]
        ) = {
            "interact_started": evidence.PendingInteractStartedEvidence,
            "uart_tx_settled": evidence.PendingUartTxSettledEvidence,
            "interact_ended": evidence.PendingInteractEndedEvidence,
        }[audit]

        def append(
            connection: sqlite3.Connection,
            policy: model.SessionPolicy,
            draft: Any,
            **kwargs: Any,
        ) -> model.EvidenceRecord:
            if not isinstance(draft, wanted):
                return original(connection, policy, draft, **kwargs)
            threads.append(threading.get_ident())
            record = (
                original(connection, policy, draft, **kwargs) if after_commit else None
            )
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(5), "test did not release real SQLite worker"
            return (
                record
                if record is not None
                else original(connection, policy, draft, **kwargs)
            )

        monkeypatch.setattr(sqlite, "_append_on_worker", append)
        if audit == "interact_started":
            waiter = c.spawn(c.owner.interact(c.request()))
        else:
            waiter = await c.begin()
            await _await(c.writer.entered.wait())
            await c.rx(b"PASS")
            c.writer.allow.set()
        try:
            await _await(entered.wait())
            assert len(threads) == 1 and threads[0] != threading.get_ident()
            for _ in range(3):
                waiter.cancel()
                await _turn()
                assert not waiter.done()
                await busy(c)
            closing = c.spawn(c.owner.detach())
            await _await(c.writer.close_entered.wait())
            assert not closing.done() and not c.recorder.closed.is_set()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await _await(waiter)
        assert (await _await(closing)).recorder_close_confirmed
        assert c.recorder.attempts.count(audit) == len(threads) == 1
        readback = await c.owner.read_page(
            evidence.EvidenceRetrievalRequest(c.journal.session_id, 100, 131072)
        )
        end = next(
            r
            for r in readback.page.records
            if isinstance(r, model.InteractEndedEvidence)
        )
        # With intent ACK withheld, cancellation and detach are first observed
        # together at installation: contract§4 gives detach precedence there.
        assert (
            end.outcome.value
            == end.observation.outcome.value
            == ("detached" if audit == "interact_started" else "matched")
        )
        assert end.tx.submitted is (audit != "interact_started")
        assert end.tx.accepted_prefix_bytes == (
            None if audit == "interact_started" else 6
        )
        assert c.writer.calls == (
            [] if audit == "interact_started" else [b"\0\xffSEND"]
        )
        assert not c.recorder.close_during_append and c.writer.cancellation_signals == 0


@pytest.mark.parametrize("cancel_reads", [False, True])
async def test_held_write_coexists_with_monitor_follow_annotations_and_all_eight_read_leases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    cancel_reads: bool,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        sub = await c.owner.start_follow(follow.FollowRequest(c.journal.session_id))
        watched = c.spawn(
            c.owner.monitor(
                monitor.MonitorRequest(c.journal.session_id, b"PASS", 1000, 1024)
            )
        )
        await _await(c.recorder.acks["operation_started"].get())
        waiter = await c.begin()
        await _await(c.writer.entered.wait())
        await c.rx(b"PA", 11)
        claim = await c.owner.annotate(
            annotation.AnnotationRequest(
                c.journal.session_id, "SS is only a claim", "cli"
            )
        )
        offered = await _await(sub.pull())
        assert (
            isinstance(offered, follow.FollowBatch)
            and claim.annotation in offered.records
        )
        original = c.journal.resolve_record
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def query(ref: model.EvidenceReference) -> evidence.EvidencePage:
            nonlocal calls
            calls += 1
            if calls == 8:
                entered.set()
            await release.wait()
            return await original(ref)

        monkeypatch.setattr(c.journal, "resolve_record", query)
        ref = model.EvidenceReference(c.journal.session_id, 0)
        reads = [c.spawn(c.owner.read_record(ref)) for _ in range(8)]
        try:
            await _await(entered.wait())
            with pytest.raises(EvidenceReadRejected) as full:
                await c.owner.read_record(ref)
            assert full.value.kind == "read_capacity"
            await busy(c)
            await c.rx(b"SS\0ambient", 12)
            assert (await _await(watched)).outcome.value == "matched"
            assert not waiter.done() and c.writer.active == 1
            if cancel_reads:
                for _ in range(3):
                    for reading in reads:
                        reading.cancel()
                    await _turn()
                assert all(not reading.done() for reading in reads)
            c.writer.allow.set()
            report = await _await(waiter)
            assert (
                report.outcome.value == "matched"
                and report.observation.examined_rx_bytes == 4
            )
            closing = c.spawn(c.owner.detach())
            await _await(c.writer.close_entered.wait())
            await _turn()
            assert not closing.done() and not c.recorder.closed.is_set()
        finally:
            release.set()
        for reading in reads:
            if cancel_reads:
                with pytest.raises(asyncio.CancelledError):
                    await _await(reading)
            else:
                assert isinstance(
                    (await _await(reading)).page.records[0],
                    model.SegmentStartedEvidence,
                )
        assert (await _await(closing)).recorder_close_confirmed
        tail: list[model.EvidenceRecord] = []
        while True:
            batch = await _await(sub.pull())
            if isinstance(batch, follow.FollowEnd):
                assert batch.reason == "detached"
                break
            assert isinstance(batch, follow.FollowBatch)
            tail.extend(batch.records)
        # 011 seals without querying another payload page. Eight pinned leases
        # also make the final head unavailable: never invent a delivered tail.
        assert tail == [] and batch.source_end_exclusive is None
        assert report.ended_record is not None
        readback = await c.owner.read_record(report.ended_record)
        assert isinstance(readback.page.records[0], model.InteractEndedEvidence)
        await sub.close()
        assert c.owner.evidence_read_cleanup_confirmed and calls == 8
        assert_single_rx_owner(c.fixture)


async def test_old_completion_cancellation_and_stop_never_bind_to_a_replacement_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path / "old", monkeypatch, factory) as old:
        captured: list[Any] = []
        original = old.coordinator.start_interact

        async def start(*args: Any, **kwargs: Any) -> Any:
            operation = await original(*args, **kwargs)
            captured.append(operation)
            return operation

        monkeypatch.setattr(old.coordinator, "start_interact", start)
        first = await old.begin()
        await old.rx(b"PASS")
        old.writer.allow.set()
        report = await _await(first)
        assert len(captured) == 1
        await old.owner.detach()
        async with case(
            tmp_path / "new", monkeypatch, factory, owner=old.owner
        ) as current:
            pending = await current.begin()
            await _await(current.writer.entered.wait())
            with pytest.raises(monitor.InteractRejected) as stale:
                await current.owner.interact(old.request())
            assert stale.value.kind == "session_not_associated"
            for _ in range(3):
                assert first.cancel() is False
                captured[0].stop((model.InteractOutcome.CANCELLED,))
                assert await captured[0].wait() == report
            assert not pending.done() and current.writer.calls == [b"\0\xffSEND"]
            await current.rx(b"PASS", 1)
            current.writer.allow.set()
            fresh = await _await(pending)
            assert (
                fresh.run_id != report.run_id and fresh.session_id != report.session_id
            )
            assert fresh.outcome.value == "matched"
            assert (
                sum(
                    isinstance(r, model.InteractStartedEvidence)
                    for r in await current.records()
                )
                == 1
            )
            assert_single_rx_owner(current.fixture)


@pytest.mark.parametrize("resource", ["journal", "transport"])
@pytest.mark.parametrize("after_close", [False, True])
async def test_cleanup_uncertainty_after_interact_is_permanent_despite_local_resource_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    resource: str,
    after_close: bool,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        calls: list[str] = []
        target = c.recorder if resource == "journal" else c.fixture.connection
        original = target.close

        async def uncertain() -> None:
            calls.append(resource)
            if after_close:
                await original()
            if resource == "journal":
                raise evidence.JournalFailure(
                    evidence.JournalOperation.CLOSE,
                    evidence.JournalFailureKind.IO_FAILURE,
                )
            raise RuntimeError("test-only unconfirmed physical release")

        monkeypatch.setattr(target, "close", uncertain)
        gate = c.recorder.gates["interact_ended"].acknowledgement
        gate.allow.clear()
        waiter = await c.begin()
        await c.rx(b"PASS")
        c.writer.allow.set()
        try:
            await _await(gate.entered.wait())
            closing = c.spawn(c.owner.detach())
            await _turn()
            assert not closing.done() and not c.recorder.closed.is_set()
        finally:
            gate.allow.set()
        report = await _await(waiter)
        terminal = await _await(closing)
        assert report.outcome.value == "matched" and report.durability == "complete"
        assert terminal.owner_settled and not terminal.attach_admissible
        assert terminal.recorder_close_confirmed is (resource != "journal")
        assert terminal.physical_release_confirmed is (resource != "transport")
        assert calls == [resource]
        # Releasing only the test's fake resource cannot repair Core certainty.
        if resource == "transport" and not c.fixture.connection.closed:
            await c.writer.original_close()
        if resource == "journal":
            await c.journal.close()
        for _ in range(3):
            assert await c.owner.detach() == terminal
            with pytest.raises(rt.RuntimeRejectedError) as rejected:
                await c.owner.attach(c.profile, c.prepare)
            assert rejected.value.kind is rt.RuntimeRejectedKind.CLEANUP_UNCONFIRMED
        assert c.owner.status() == terminal and calls == [resource]
        assert c.writer.cancellation_signals == 0


async def test_uncertain_terminal_read_cleanup_survives_new_interact_and_old_operation_callbacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    from tests.contract import test_interact_runtime as fixture_module
    from tests.contract.test_follow_runtime import UnacknowledgedReaderClose

    async with case(tmp_path / "old", monkeypatch, factory) as old:
        first = await old.begin()
        await old.rx(b"PASS")
        old.writer.allow.set()
        report = await _await(first)
        await old.owner.detach()
        original = open_terminal_reader

        async def reader(target: Any) -> Any:
            return UnacknowledgedReaderClose(await original(target))

        with monkeypatch.context() as local:
            local.setattr(fixture_module, "open_terminal_reader", reader)
            with pytest.raises(evidence.JournalFailure) as failed:
                await old.owner.read_record(report.started_record)
            assert failed.value.operation is evidence.JournalOperation.CLOSE
        assert not old.owner.evidence_read_cleanup_confirmed
        async with case(
            tmp_path / "new", monkeypatch, factory, owner=old.owner
        ) as current:
            with pytest.raises(EvidenceReadRejected) as rejected:
                await current.owner.read_record(
                    model.EvidenceReference(current.journal.session_id, 0)
                )
            assert rejected.value.kind == "read_unavailable"
            with pytest.raises(follow.FollowRejected) as rejected_follow:
                await current.owner.start_follow(
                    follow.FollowRequest(current.journal.session_id)
                )
            assert rejected_follow.value.kind == "follow_unavailable"
            pending = await current.begin()
            claim = await current.owner.annotate(
                annotation.AnnotationRequest(
                    current.journal.session_id, "new generation claim", "core"
                )
            )
            assert claim.annotation.sequence >= 1
            assert first.cancel() is False
            await current.rx(b"PASS", 1)
            current.writer.allow.set()
            assert (await _await(pending)).outcome.value == "matched"
            assert not current.owner.evidence_read_cleanup_confirmed
            await current.owner.detach()
            assert not current.owner.evidence_read_cleanup_confirmed


async def test_cancelled_intent_waiting_for_annotation_gate_keeps_its_slot_and_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        gate = c.recorder.gates["client_annotation"].acknowledgement
        gate.allow.clear()
        claim = c.spawn(
            c.owner.annotate(
                annotation.AnnotationRequest(
                    c.journal.session_id, "held assertion", "core"
                )
            )
        )
        await _await(gate.entered.wait())
        waiter = c.spawn(c.owner.interact(c.request()))
        try:
            await _turn()
            for _ in range(3):
                waiter.cancel()
                await _turn()
                await busy(c)
            assert (
                c.writer.calls == [] and "interact_started" not in c.recorder.attempts
            )
            assert not waiter.done() and not claim.done()
        finally:
            gate.allow.set()
        assert (await _await(claim)).annotation.text == "held assertion"
        with pytest.raises(asyncio.CancelledError):
            await _await(waiter)
        end = next(
            r for r in await c.records() if isinstance(r, model.InteractEndedEvidence)
        )
        assert end.outcome.value == "cancelled" and end.tx.status == "not_submitted"
        assert not end.tx.submitted and c.writer.calls == []
        assert c.owner.status().state is rt.RuntimeState.ACTIVE


@pytest.mark.parametrize("lost_ack", [False, True], ids=["before-commit", "lost-ack"])
async def test_cancelled_failed_intent_never_submits_and_releases_only_after_failure_join(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    lost_ack: bool,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        gate = c.recorder.gates["interact_started"].commit
        gate.allow.clear()
        (c.recorder.fail_ack if lost_ack else c.recorder.fail_before).add(
            "interact_started"
        )
        waiter = c.spawn(c.owner.interact(c.request()))
        try:
            await _await(gate.entered.wait())
            for _ in range(3):
                waiter.cancel()
                await _turn()
                assert not waiter.done()
                await busy(c)
        finally:
            gate.allow.set()
        with pytest.raises(asyncio.CancelledError):
            await _await(waiter)
        rows = await c.records()
        assert sum(isinstance(r, model.InteractStartedEvidence) for r in rows) == int(
            lost_ack
        )
        assert not any(
            isinstance(r, (model.UartTxSettledEvidence, model.InteractEndedEvidence))
            for r in rows
        )
        assert (
            c.writer.calls == [] and c.recorder.attempts.count("interact_started") == 1
        )
        c.recorder.release()
        while not c.recorder.acks["interact_started"].empty():
            c.recorder.acks["interact_started"].get_nowait()
        replacement = await c.begin(c.request(payload=b"NEXT"))
        await c.rx(b"PASS")
        c.writer.allow.set()
        report = await _await(replacement)
        assert report.outcome.value == "matched" and c.writer.calls == [b"NEXT"]
        assert c.owner.status().state is rt.RuntimeState.ACTIVE


async def test_service_seal_at_positive_intent_ack_wins_over_simultaneous_waiter_cancel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with case(tmp_path, monkeypatch, factory) as c:
        waiter: asyncio.Task[Any]

        def stop_at_ack() -> None:
            c.owner._seal_interacts()
            waiter.cancel()

        c.recorder.after_ack["interact_started"] = stop_at_ack
        waiter = c.spawn(c.owner.interact(c.request()))
        with pytest.raises(asyncio.CancelledError):
            await _await(waiter)
        end = next(
            r for r in await c.records() if isinstance(r, model.InteractEndedEvidence)
        )
        assert end.outcome.value == end.observation.outcome.value == "service_stopping"
        assert not end.tx.submitted and end.tx.status == "not_submitted"
        assert c.writer.calls == []
