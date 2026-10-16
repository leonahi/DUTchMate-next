"""010 T017: owned annotation races over real v3 journals, without hardware.

Scheduling/fault seams delegate to the existing coordinator, journal and reader.
No admission, lifecycle, retention or Monitor policy is implemented by this file.
"""

import asyncio
import sqlite3
import threading
from pathlib import Path

import pytest

from dutchmate_core import evidence, model, monitor
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
from tests.contract.test_annotation_runtime import Case, case, entry, seal
from tests.contract.test_monitor_recording import _await, _turn
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixtureFactory
from tests.integration.test_annotations import assert_single_rx_owner


def _terminal_access(
    c: Case,
    path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    uncertain_reader: bool = False,
) -> list[str]:
    target = capture_terminal_target(
        path / "runtime.db",
        session_id=c.probe.session_id,
        policy=c.probe.policy,
        expected_schema_version=3,
    )
    assert target is not None
    opened: list[str] = []

    async def opener() -> OwnedEvidenceReadPort:
        assert c.probe.closed.is_set(), "terminal open preceded writer close ACK"
        reader = await open_terminal_reader(target)
        opened.append("open")
        if uncertain_reader:
            original_close = reader.close

            async def close() -> None:
                await original_close()
                raise evidence.JournalFailure(
                    evidence.JournalOperation.CLOSE,
                    evidence.JournalFailureKind.IO_FAILURE,
                )

            monkeypatch.setattr(reader, "close", close)
        return reader

    c.terminal_opener = opener
    return opened


async def _settled(owner: rt.ObservationRuntime) -> rt.RuntimeStatus:
    # Only a test watchdog bounds waiting; production stop has no forced timeout.
    async def wait() -> rt.RuntimeStatus:
        while not owner.status().owner_settled:
            await _turn()
        return owner.status()

    return await _await(wait())


async def _stop(c: Case, kind: str) -> asyncio.Task[rt.RuntimeStatus]:
    if kind == "disconnect":
        await c.fixture.connection.disconnect()
        # Observe autonomous cleanup without issuing detach to trigger it.
        return c.spawn(_settled(c.owner))
    assert kind == "detach"
    return c.spawn(c.owner.detach())


async def _page(c: Case) -> RunEvidencePage:
    return await _await(
        c.owner.read_page(
            evidence.EvidenceRetrievalRequest(
                c.probe.session_id,
                c.probe.policy.max_retrieval_page_records,
                c.probe.policy.max_retrieval_page_charged_bytes,
            )
        )
    )


def _assert_terminal(c: Case, terminal: rt.RuntimeStatus, stop: str) -> None:
    assert terminal.state is rt.RuntimeState.TERMINATED
    assert terminal.terminal_reason is (
        rt.RuntimeTerminalReason.DISCONNECTED
        if stop == "disconnect"
        else rt.RuntimeTerminalReason.DETACHED
    )
    assert terminal.owner_settled and terminal.recorder_close_confirmed
    assert terminal.physical_release_confirmed and terminal.attach_admissible
    assert terminal.primary_issue is None and terminal.cleanup_issues == ()
    assert c.owner.evidence_read_cleanup_confirmed
    assert c.probe.close_calls == c.fixture.connection.close_calls == 1
    assert_single_rx_owner(c.fixture)


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
@pytest.mark.asyncio
async def test_cancel_before_admission_does_not_write_or_spend_budget_across_detach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, factory: BackendFixtureFactory
) -> None:
    async with case(tmp_path / "first", factory, attach=False) as c:
        _terminal_access(c, tmp_path / "first", monkeypatch)
        await c.attach()
        delivery = asyncio.create_task(c.owner.annotate(c.request("never admitted")))
        c.tasks.append(delivery)
        delivery.cancel()
        with pytest.raises(asyncio.CancelledError):
            await delivery
        assert c.charge.calls == [] and c.clock.samples == []
        _assert_terminal(c, await c.owner.detach(), "detach")
        records = (await _page(c)).page.records
        assert len(records) == 2
        assert isinstance(records[0], model.SegmentStartedEvidence)
        assert isinstance(records[1], model.SegmentEndedEvidence)
        async with case(
            tmp_path / "second", factory, owner=c.owner, clock=c.clock
        ) as next_run:
            await next_run.fill(10)
            await next_run.reject("rate_limited")


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
@pytest.mark.parametrize("stop", ["detach", "disconnect"])
@pytest.mark.parametrize("cancelled", [False, True])
@pytest.mark.parametrize(
    "phase,failure",
    [
        ("before_insert", None),
        ("before_insert", "before_commit"),
        ("before_insert", "after_commit"),
        ("after_ack", None),
    ],
)
@pytest.mark.asyncio
async def test_bound_owner_survives_seal_segment_end_and_waiter_loss_without_false_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    stop: str,
    cancelled: bool,
    phase: str,
    failure: str | None,
) -> None:
    async with case(tmp_path, factory, attach=False) as c:
        opened = _terminal_access(c, tmp_path, monkeypatch)
        await c.attach()
        entered, allow = asyncio.Event(), asyncio.Event()
        original = c.coordinator.append_client_annotation

        async def delayed(surface: str, text: str) -> model.ClientAnnotationEvidence:
            if phase == "before_insert":
                entered.set()
                await allow.wait()
            record = await original(surface, text)
            if phase == "after_ack":
                entered.set()
                await allow.wait()
            return record

        monkeypatch.setattr(c.coordinator, "append_client_annotation", delayed)
        c.probe.failure = failure
        delivery = c.spawn(entry(c.owner)(c.request("external claim", "http")))
        try:
            await _await(entered.wait())
            await c.reject("busy")
            if cancelled:
                for _ in range(3):
                    delivery.cancel()
                    await _turn()
                    assert not delivery.done()
            seal(c.owner)
            await c.reject("annotation_unavailable")
            stopping = await _stop(c, stop)
            await _await(c.probe.segment_ended.wait())
            assert not stopping.done() and not c.owner.status().owner_settled
            assert c.probe.close_calls == 0 and opened == []
            before = await _page(c)
            assert c.active is not None and before.run_id == c.active.run_id
            assert sum(
                isinstance(r, model.ClientAnnotationEvidence)
                for r in before.page.records
            ) == (phase == "after_ack")
            c.clock.advance(500)
            allow.set()
            if cancelled:
                with pytest.raises(asyncio.CancelledError):
                    await _await(delivery)
            elif failure is not None:
                with pytest.raises(evidence.JournalFailure) as caught:
                    await _await(delivery)
                assert caught.value is c.probe.error
            else:
                receipt = await _await(delivery)
                assert receipt.reference.sequence == (
                    2 if phase == "before_insert" else 1
                )
                assert receipt.annotation.received_at_ns == (
                    500 if phase == "before_insert" else 100
                )
                assert c.active is not None and c.active.run_id is not None
                assert receipt.run_id == c.active.run_id.value
                assert receipt.session_id == c.probe.session_id
            _assert_terminal(c, await _await(stopping), stop)
            page = await _page(c)
            claims = [
                r
                for r in page.page.records
                if isinstance(r, model.ClientAnnotationEvidence)
            ]
            assert len(claims) == (0 if failure == "before_commit" else 1)
            if claims:
                claim = claims[0]
                assert claim.text == "external claim" and claim.client_surface == "http"
                assert claim.sequence == (2 if phase == "before_insert" else 1)
                assert claim.clock_origin_id == c.clock.origin_id
                assert claim.received_at_ns == (
                    500 if phase == "before_insert" else 100
                )
                assert claim.assertion_class == "client_assertion"
                assert claim.attribution_basis == "client_asserted"
            assert (
                sum(
                    isinstance(d, evidence.PendingClientAnnotationEvidence)
                    for d in c.probe.submitted
                )
                == 1
            )
            assert opened == ["open"]
        finally:
            allow.set()


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
@pytest.mark.parametrize("stop", ["detach", "disconnect"])
@pytest.mark.parametrize(
    "committed", [False, True], ids=["before-commit", "after-commit"]
)
@pytest.mark.asyncio
async def test_submitted_native_annotation_and_same_journal_read_join_before_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    stop: str,
    committed: bool,
) -> None:
    async with case(tmp_path, factory, attach=False) as c:
        opened = _terminal_access(c, tmp_path, monkeypatch)
        await c.attach()
        entered, release = asyncio.Event(), threading.Event()
        loop = asyncio.get_running_loop()
        original = sqlite._append_on_worker
        threads: list[int] = []

        def pause() -> None:
            threads.append(threading.get_ident())
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(3), "test worker checkpoint was not released"

        def append(
            connection: sqlite3.Connection,
            policy: model.SessionPolicy,
            draft: evidence.PendingEvidenceRecord,
            *,
            schema_version: int = 1,
            timestamp_context: sqlite._WriterTimestampContext | None = None,
        ) -> model.EvidenceRecord:
            selected = isinstance(draft, evidence.PendingClientAnnotationEvidence)
            if selected and not committed:
                pause()
            record = original(
                connection,
                policy,
                draft,
                schema_version=schema_version,
                timestamp_context=timestamp_context,
            )
            if selected and committed:
                pause()
            return record

        monkeypatch.setattr(sqlite, "_append_on_worker", append)
        read_entered = asyncio.Event()
        retrieve = c.probe.journal.retrieve

        async def read(
            request: evidence.EvidenceRetrievalRequest,
        ) -> evidence.EvidencePage:
            read_entered.set()
            return await retrieve(request)

        monkeypatch.setattr(c.probe.journal, "retrieve", read)
        delivery = c.spawn(entry(c.owner)(c.request("native durable assertion")))
        try:
            await _await(entered.wait())
            assert len(threads) == 1 and threads[0] != threading.get_ident()
            reading = c.spawn(
                c.owner.read_page(
                    evidence.EvidenceRetrievalRequest(
                        model.EvidenceRangeReference(c.probe.session_id, 0, 2),
                        c.probe.policy.max_retrieval_page_records,
                        c.probe.policy.max_retrieval_page_charged_bytes,
                    )
                )
            )
            await _await(read_entered.wait())
            for _ in range(3):
                delivery.cancel()
                await _turn()
                assert not delivery.done() and not reading.done()
                await c.reject("busy")
            stopping = await _stop(c, stop)
            await _turn()
            assert not stopping.done() and c.probe.close_calls == 0 and opened == []
            assert not c.owner.status().owner_settled
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await _await(delivery)
            report = await _await(reading)
            assert len(report.page.records) == 2
            assert isinstance(report.page.records[0], model.SegmentStartedEvidence)
            assert isinstance(report.page.records[1], model.ClientAnnotationEvidence)
            assert report.page.snapshot_end_exclusive == 2
            claim = report.page.records[1]
            assert isinstance(claim, model.ClientAnnotationEvidence)
            assert claim.text == "native durable assertion" and claim.sequence == 1
            _assert_terminal(c, await _await(stopping), stop)
            terminal = await _page(c)
            assert terminal.page.records[:2] == report.page.records
            assert isinstance(terminal.page.records[-1], model.SegmentEndedEvidence)
            assert opened == ["open"]
        finally:
            release.set()


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
@pytest.mark.parametrize("cancelled_read", [False, True])
@pytest.mark.asyncio
async def test_settled_annotation_does_not_let_close_overtake_pinned_read_or_hold_lifecycle_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    cancelled_read: bool,
) -> None:
    async with case(tmp_path, factory) as c:
        read_entered, release = asyncio.Event(), asyncio.Event()
        retrieve = c.probe.journal.retrieve

        async def read(
            request: evidence.EvidenceRetrievalRequest,
        ) -> evidence.EvidencePage:
            read_entered.set()
            await release.wait()
            return await retrieve(request)

        monkeypatch.setattr(c.probe.journal, "retrieve", read)
        reading = c.spawn(_page(c))
        try:
            await _await(read_entered.wait())
            receipt = await c.insert("pinned read context")
            stopping = c.spawn(c.owner.detach())
            await _await(c.probe.segment_ended.wait())
            if cancelled_read:
                for _ in range(3):
                    reading.cancel()
                    await _turn()
                    assert not reading.done()

            # A read attempted after the admitted query's owner is sealed must
            # reject promptly; neither it nor attach may deadlock on cleanup.
            async def sealed() -> None:
                while True:
                    try:
                        await c.owner.read_record(receipt.reference)
                    except EvidenceReadRejected as rejected:
                        assert rejected.kind == "read_unavailable"
                        return
                    await _turn()

            await _await(sealed())
            await c.reject("not_active")

            async def forbidden_prepare(_: object) -> rt.PreparedObservationRun:
                pytest.fail("read join admitted another physical owner")

            with pytest.raises(rt.RuntimeRejectedError) as busy:
                await _await(c.owner.attach(c.profile, forbidden_prepare))
            assert busy.value.kind is rt.RuntimeRejectedKind.BUSY
            assert c.probe.close_calls == 0 and not stopping.done()
            release.set()
            if cancelled_read:
                with pytest.raises(asyncio.CancelledError):
                    await _await(reading)
            else:
                report = await _await(reading)
                assert receipt.annotation in report.page.records
            _assert_terminal(c, await _await(stopping), "detach")
        finally:
            release.set()


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
@pytest.mark.parametrize("fault", ["writer", "transport", "terminal_reader"])
@pytest.mark.asyncio
async def test_pending_annotation_preserves_independent_cleanup_and_terminal_read_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    fault: str,
) -> None:
    async with case(tmp_path, factory, attach=False) as c:
        opened = _terminal_access(
            c, tmp_path, monkeypatch, uncertain_reader=fault == "terminal_reader"
        )
        await c.attach()
        if fault == "writer":
            writer_close = c.probe.close

            async def failed_writer_close() -> None:
                await writer_close()
                raise evidence.JournalFailure(
                    evidence.JournalOperation.CLOSE,
                    evidence.JournalFailureKind.IO_FAILURE,
                )

            monkeypatch.setattr(c.probe, "close", failed_writer_close)
        elif fault == "transport":
            transport_close = c.fixture.connection.close

            async def failed_transport_close() -> None:
                await transport_close()
                raise RuntimeError("test-only unconfirmed transport release")

            monkeypatch.setattr(c.fixture.connection, "close", failed_transport_close)
        c.probe.annotation.acknowledgement.allow.clear()
        delivery = c.spawn(entry(c.owner)(c.request("accepted before cleanup")))
        await _await(c.probe.annotation.acknowledgement.entered.wait())
        stopping = c.spawn(c.owner.detach())
        try:
            await _turn()
            assert c.probe.close_calls == 0 and opened == []
            c.probe.annotation.acknowledgement.allow.set()
            receipt = await _await(delivery)
            terminal = await _await(stopping)
            assert terminal.owner_settled
            assert terminal.recorder_close_confirmed is (fault != "writer")
            assert terminal.physical_release_confirmed is (fault != "transport")
            assert terminal.attach_admissible is (fault == "terminal_reader")
            if fault == "writer":
                with pytest.raises(EvidenceReadRejected) as rejected:
                    await c.owner.read_record(receipt.reference)
                assert rejected.value.kind == "read_unavailable" and opened == []
                assert c.owner.evidence_read_cleanup_confirmed
            elif fault == "terminal_reader":
                with pytest.raises(evidence.JournalFailure) as failed:
                    await c.owner.read_record(receipt.reference)
                assert failed.value.operation is evidence.JournalOperation.CLOSE
                assert not c.owner.evidence_read_cleanup_confirmed
                with pytest.raises(EvidenceReadRejected) as rejected:
                    await c.owner.read_record(receipt.reference)
                assert rejected.value.kind == "read_unavailable" and opened == ["open"]
            else:
                report = await c.owner.read_record(receipt.reference)
                assert report.page.records == (receipt.annotation,)
                assert opened == ["open"] and c.owner.evidence_read_cleanup_confirmed
            assert c.owner.status() == terminal
            assert c.probe.close_calls == c.fixture.connection.close_calls == 1
        finally:
            c.probe.release()


@pytest.mark.parametrize(
    "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
)
@pytest.mark.parametrize("failure", [None, "after_commit"], ids=["ack", "lost-ack"])
@pytest.mark.asyncio
async def test_lost_annotation_waiter_preserves_fresh_monitor_deadline_and_ambient_rx(
    tmp_path: Path,
    factory: BackendFixtureFactory,
    failure: str | None,
) -> None:
    async with case(tmp_path, factory) as c:
        watching = c.spawn(
            c.owner.monitor(
                monitor.MonitorRequest(c.probe.session_id, b"PASS", 1000, 4)
            )
        )
        await _await(c.probe.monitor_started.wait())
        await _await(c.clock.wait_started.wait())
        await c.fixture.connection.emit_rx(b"PA", timestamp=17)
        assert (await _await(c.probe.rx_commits.get())).sequence == 2
        c.probe.annotation.acknowledgement.allow.clear()
        c.probe.failure = failure
        delivery = c.spawn(entry(c.owner)(c.request("SS is only a client assertion")))
        try:
            await _await(c.probe.annotation.acknowledgement.entered.wait())
            for _ in range(3):
                delivery.cancel()
                await _turn()
                assert not delivery.done() and not watching.done()
            page = await _page(c)
            claim = page.page.records[-1]
            assert isinstance(claim, model.ClientAnnotationEvidence)
            assert claim.sequence == 3 and claim.received_at_ns == 100
            # Leave the deadline waiter asleep: only an actual post-ACK publish
            # may observe this time. Failed append delivery must publish nothing.
            c.clock.value = 1_000_000_107
            c.probe.annotation.acknowledgement.allow.set()
            with pytest.raises(asyncio.CancelledError):
                await _await(delivery)
            if failure is not None:
                assert not watching.done()
                c.clock.advance(1_000_000_107)
            report = await _await(watching)
            assert report.outcome is model.MonitorOutcome.TIMEOUT
            assert report.examined_rx_bytes == 2 and report.observer_loss_records == 0
            assert report.match is None and report.durability == "complete"
            assert report.clock.deadline_at_ns == 1_000_000_100
            assert report.clock.decided_at_ns == 1_000_000_107
            assert report.window == model.SequenceRange(2, 3)
            await c.fixture.connection.emit_rx(b"SS\0\xffambient", timestamp=19)
            await _await(c.probe.rx_commits.get())
            records = (await _page(c)).page.records
            assert [
                r.payload for r in records if isinstance(r, model.RxBytesEvidence)
            ] == [b"PA", b"SS\0\xffambient"]
            assert [
                r for r in records if isinstance(r, model.ClientAnnotationEvidence)
            ] == [claim]
            assert c.owner.status().state is rt.RuntimeState.ACTIVE
            assert c.owner.status().primary_issue is None
            assert_single_rx_owner(c.fixture)
        finally:
            c.probe.release()
