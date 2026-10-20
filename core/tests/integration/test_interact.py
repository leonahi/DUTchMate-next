"""012 T014 RED: one RX owner, real v4 journals and existing concurrent workflows."""

from pathlib import Path

import pytest

from dutchmate_core import annotation, evidence, follow, model, monitor
from tests.contract.test_interact_recording import recording_case
from tests.contract.test_interact_runtime import runtime_case
from tests.contract.test_monitor_recording import _await, _turn
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixtureFactory,
    EnhancedShapedBackendConnection,
)
from tests.integration.test_annotations import assert_single_rx_owner

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic-shape", "enhanced-shape"]
    ),
]


async def test_t014_real_commit_is_visible_before_gated_ack_without_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    # GREEN infrastructure control: a genuine committed SQLite row, not a fake
    # recorder's copied state, remains readable while its ACK is withheld.
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        gate = c.recorder.gates["client_annotation"].acknowledgement
        gate.allow.clear()
        insertion = c.spawn(
            c.coordinator.append_client_annotation("cli", "literal assertion")
        )
        await _await(gate.entered.wait())
        rows = await c.records()
        assert isinstance(rows[-1], model.ClientAnnotationEvidence)
        assert rows[-1].text == "literal assertion"
        assert c.recorder.acks["client_annotation"].empty()
        queued = c.spawn(c.rx(b"queued\x00\xff"))
        await _turn()
        assert not queued.done()
        gate.allow.set()
        assert await _await(insertion) == rows[-1]
        assert (await _await(queued)).sequence == 2
        assert c.writer.calls == []


async def test_t014_binary_transaction_matches_early_and_survives_terminal_retrieval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        old = await c.rx(b"\x00\xffPASS before intent", 1)
        task = await c.begin(c.request(conditions=(b"FAIL", b"\x00\xffPASS")))
        await _await(c.writer.entered.wait())
        first = await c.rx(b"ambient\x00\xffPA", 2)
        last = await c.rx(b"SSextra\x80", 3)
        await c.rx(b"later ambient\xff", 4)
        assert not task.done() and c.writer.active == 1
        c.clock.advance(2_000_000_100)
        c.writer.allow.set()
        report = await _await(task)
        assert report.outcome.value == "matched" and report.payload == b"\x00\xffSEND"
        assert report.observation.window == model.SequenceRange(
            first.sequence, last.sequence + 1
        )
        assert report.observation.match == model.InteractMatch(
            1,
            model.MonitorMatchStart(first.sequence, 7),
            model.MonitorMatchEnd(last.sequence, 2),
        )
        assert report.observation.examined_rx_bytes == 13
        assert (
            report.observation.clock.started_at_ns
            == report.observation.clock.decided_at_ns
            == 100
        )
        assert report.tx.settled_at_ns == 2_000_000_100
        assert report.tx.accepted_prefix_bytes == 6
        assert report.started_record.sequence == old.sequence + 1
        assert report.tx_settled_record is not None and report.ended_record is not None
        live = await c.owner.read_record(report.ended_record)
        ended = live.page.records[0]
        assert isinstance(ended, model.InteractEndedEvidence)
        assert ended.tx.accepted_prefix_bytes == 6
        await c.owner.detach()
        terminal = await c.owner.read_record(report.ended_record)
        assert c.terminal_opened.is_set()
        assert terminal.page.records == live.page.records
        raw = await c.owner.read_record(
            model.EvidenceReference(c.journal.session_id, last.sequence)
        )
        assert raw.page.records == (last,)
        assert_single_rx_owner(c.fixture)
        assert c.writer.calls == [b"\x00\xffSEND"] and c.writer.active_at_close == [0]


async def test_t014_interact_monitor_follow_annotations_and_retrieval_share_one_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        subscription = await c.owner.start_follow(
            follow.FollowRequest(c.journal.session_id)
        )
        task = await c.begin()
        await _await(c.writer.entered.wait())
        monitored = c.spawn(
            c.owner.monitor(
                monitor.MonitorRequest(c.journal.session_id, b"M", 1000, 1024)
            )
        )
        await _await(c.recorder.acks["operation_started"].get())
        first = await c.rx(b"PA", 1)
        accepted = await c.owner.annotate(
            annotation.AnnotationRequest(
                c.journal.session_id, "SS is a client assertion, not RX", "cli"
            )
        )
        assert not task.done()
        observer = c.coordinator.current_provenance
        assert observer is not None
        reports_loss = isinstance(
            observer.loss_observability, model.ObserverReportsUartLoss
        )
        if reports_loss:
            connection = c.fixture.connection
            assert isinstance(connection, EnhancedShapedBackendConnection)
            before = len(c.clock.samples)
            await connection.emit_observer_loss(
                cause="overflow", lost_bytes=None, timestamp=2
            )
            await _await(c.recorder.acks["observer_loss"].get())
            assert len(c.clock.samples) - before == 1
        middle = await c.rx(b"SSM", 3)
        mon = await _await(monitored)
        assert mon.outcome.value == "matched"
        assert mon.examined_rx_bytes == 5 and mon.observer_loss_records == int(
            reports_loss
        )
        if reports_loss:
            matching = await c.rx(b"PASS", 4)
            expected_match = model.InteractMatch(
                0,
                model.MonitorMatchStart(matching.sequence, 0),
                model.MonitorMatchEnd(matching.sequence, 4),
            )
        else:
            expected_match = model.InteractMatch(
                0,
                model.MonitorMatchStart(first.sequence, 0),
                model.MonitorMatchEnd(middle.sequence, 2),
            )
        # Reader progress is independent of both write and observation ownership.
        page = await c.owner.read_page(
            evidence.EvidenceRetrievalRequest(c.journal.session_id, 100, 131072)
        )
        assert any(r == accepted.annotation for r in page.page.records)
        assert c.writer.active == 1 and not task.done()
        c.writer.allow.set()
        report = await _await(task)
        assert report.observation.match == expected_match
        assert report.observation.observer_loss_records == int(reports_loss)
        records = await c.records()
        batch = await _await(subscription.pull())
        assert isinstance(batch, follow.FollowBatch) and batch.gap is None
        assert batch.records == records[subscription.start.start_sequence :]
        assert {type(r) for r in batch.records} >= {
            model.InteractStartedEvidence,
            model.UartTxSettledEvidence,
            model.InteractEndedEvidence,
            model.RxBytesEvidence,
            model.ClientAnnotationEvidence,
            model.OperationStartedEvidence,
            model.OperationEndedEvidence,
        }
        assert accepted.annotation.assertion_class == "client_assertion"
        assert_single_rx_owner(c.fixture)
        await subscription.close()


@pytest.mark.parametrize(
    "kind", ["interact_started", "uart_tx_settled", "interact_ended"]
)
async def test_t014_each_ambiguous_new_append_wakes_follow_without_fabricating_ack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    kind: str,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        subscription = await c.owner.start_follow(
            follow.FollowRequest(c.journal.session_id)
        )
        c.recorder.fail_ack.add(kind)
        commit = c.recorder.gates[kind].commit
        commit.allow.clear()
        task = c.spawn(c.entry()(c.request()))
        if kind != "interact_started":
            await _await(c.writer.entered.wait())
            c.writer.allow.set()
            if kind == "interact_ended":
                await _await(c.recorder.acks["uart_tx_settled"].get())
                await c.rx(b"PASS")
            await _await(commit.entered.wait())
            drained = await _await(subscription.pull())
            assert isinstance(drained, follow.FollowBatch)
        else:
            await _await(commit.entered.wait())
        waiting = c.spawn(subscription.pull())
        await _turn()
        assert not waiting.done()
        commit.allow.set()
        batch = await _await(waiting)
        assert isinstance(batch, follow.FollowBatch)
        wanted = {
            "interact_started": model.InteractStartedEvidence,
            "uart_tx_settled": model.UartTxSettledEvidence,
            "interact_ended": model.InteractEndedEvidence,
        }[kind]
        assert len(batch.records) == 1 and isinstance(batch.records[0], wanted)
        if kind == "interact_started":
            with pytest.raises(evidence.JournalFailure):
                await _await(task)
            assert c.writer.calls == []
        else:
            if kind == "uart_tx_settled":
                await c.rx(b"PASS")
            report = await _await(task)
            reference = (
                report.tx_settled_record
                if kind == "uart_tx_settled"
                else report.ended_record
            )
            assert reference is None and report.tx.submitted
        await subscription.close()
