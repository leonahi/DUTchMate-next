"""012 T020: ambiguous ACKs and backend progress over real temporary journals.

Only normalized backend results and persistence acknowledgement boundaries are
controlled. A committed row never supplies a lost acknowledgement to the owner.
Both backend shapes execute the identical cases; no physical UART is accessed.
"""

from pathlib import Path
from typing import Any

import pytest

from dutchmate_core import evidence, model
from dutchmate_core.adapters import sqlite_evidence as sqlite
from dutchmate_core.backend import (
    BackendFailureKind,
    BackendWriteResult,
    BackendWriteStatus,
)
from tests.contract.test_interact_recording import recording_case
from tests.contract.test_interact_runtime import runtime_case
from tests.contract.test_monitor_recording import _await
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixtureFactory
from tests.integration.test_annotations import assert_single_rx_owner

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced-shaped"]
    ),
]


async def _reopen(
    path: Path, session: model.SessionId
) -> tuple[model.EvidenceRecord, ...]:
    journal = await sqlite.SqliteEvidenceJournal.open_v4(
        path, expected_session_id=session
    )
    try:
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(session, 100, 131072)
        )
        assert not page.truncated
        return page.records
    finally:
        await journal.close()


@pytest.mark.parametrize("ambiguous", [False, True], ids=["before-commit", "lost-ack"])
async def test_intent_ack_failure_suppresses_tx_but_does_not_claim_no_durable_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    ambiguous: bool,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        before = await c.rx(b"ambient before ambiguous intent\0\xff", 11)
        (c.recorder.fail_ack if ambiguous else c.recorder.fail_before).add(
            "interact_started"
        )
        with pytest.raises(evidence.JournalFailure) as caught:
            await c.start(c.request(payload=bytes(range(256))))
        assert caught.value.kind is evidence.JournalFailureKind.IO_FAILURE
        assert c.writer.calls == [] and "write.register" not in c.trace
        assert c.recorder.attempts.count("interact_started") == 1
        assert not {"uart_tx_settled", "interact_ended"}.intersection(
            c.recorder.attempts
        )
        rows = await c.records()
        intents = [r for r in rows if isinstance(r, model.InteractStartedEvidence)]
        assert len(intents) == int(ambiguous)
        if ambiguous:
            assert intents[0].sequence == before.sequence + 1
            assert intents[0].payload == bytes(range(256))
        session = c.journal.session_id
        assert_single_rx_owner(c.fixture)
    reopened = await _reopen(tmp_path / "recording.db", session)
    assert sum(isinstance(r, model.InteractStartedEvidence) for r in reopened) == int(
        ambiguous
    )
    assert not any(
        isinstance(r, (model.UartTxSettledEvidence, model.InteractEndedEvidence))
        for r in reopened
    )
    assert [r.payload for r in reopened if isinstance(r, model.RxBytesEvidence)] == [
        before.payload
    ]


_RESULTS = [
    "full",
    "zero",
    "short",
    "timeout",
    "disconnected",
    *[f.value for f in BackendFailureKind],
]


@pytest.mark.parametrize("length", [1, 256, 4096])
@pytest.mark.parametrize("result", _RESULTS)
@pytest.mark.parametrize("early", [False, True], ids=["write-first", "rx-first"])
async def test_exact_prefix_edges_and_unknown_progress_remain_independent_of_rx_and_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    length: int,
    result: str,
    early: bool,
) -> None:
    payload = (bytes(range(256)) * 16)[:length]
    status, count, failure, overall = {
        "full": (BackendWriteStatus.ACKNOWLEDGED, length, None, "matched"),
        "zero": (BackendWriteStatus.PARTIAL, 0, None, "partial_write"),
        "short": (BackendWriteStatus.PARTIAL, length - 1, None, "partial_write"),
        "timeout": (BackendWriteStatus.TIMEOUT, None, None, "write_timeout"),
        "disconnected": (BackendWriteStatus.DISCONNECTED, None, None, "disconnected"),
    }.get(
        result,
        (
            BackendWriteStatus.FAILURE,
            None,
            BackendFailureKind(result)
            if result not in {"full", "zero", "short", "timeout", "disconnected"}
            else None,
            "transport_failure",
        ),
    )
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        c.writer.result = BackendWriteResult(status, count, failure)
        # A simulated backend may have progressed internally before returning an
        # unknown result. Neither an RX echo nor this private test fact is a count
        # available to Core. Normalized results alone govern acceptance evidence.
        progressed: list[bytes] = []
        write = c.writer.write

        async def backend_write(raw: bytes) -> BackendWriteResult:
            answer = await write(raw)
            progressed.append(raw)
            return answer

        monkeypatch.setattr(c.fixture.connection, "write", backend_write)
        operation = await c.start(c.request(payload=payload))
        await _await(c.writer.entered.wait())
        rx = None
        if early:
            rx = await c.rx(b"PASS\0echo:" + payload, 11)
        c.writer.allow.set()
        await _await(c.recorder.acks["uart_tx_settled"].get())
        if not early and result == "full":
            rx = await c.rx(b"PASS\0echo:" + payload, 11)
        report = await _await(operation.wait())
        assert report.payload == payload and c.writer.calls == progressed == [payload]
        assert report.outcome.value == overall
        assert report.tx.status is status and report.tx.accepted_prefix_bytes == count
        assert report.tx.failure_code is failure
        assert report.tx.acknowledgement_scope == "backend_acceptance"
        assert report.observation.outcome.value == (
            "matched" if early or result == "full" else "tx_failed"
        )
        assert report.observation.examined_rx_bytes == (4 if rx is not None else 0)
        assert report.durability == "complete" and report.audit_failures == ()
        rows = await c.records()
        start = next(r for r in rows if isinstance(r, model.InteractStartedEvidence))
        settled = next(r for r in rows if isinstance(r, model.UartTxSettledEvidence))
        end = next(r for r in rows if isinstance(r, model.InteractEndedEvidence))
        assert start.payload == payload
        assert settled.tx == end.tx
        assert end.tx.accepted_prefix_bytes == count and end.tx.failure_code == (
            failure.value if failure else None
        )
        assert end.tx_settled_sequence == settled.sequence
        assert (
            c.recorder.attempts.count("uart_tx_settled")
            == c.recorder.attempts.count("interact_ended")
            == 1
        )
        session = c.journal.session_id
        assert_single_rx_owner(c.fixture)
    reopened = await _reopen(tmp_path / "recording.db", session)
    assert start in reopened and settled in reopened and end in reopened
    assert [r.payload for r in reopened if isinstance(r, model.RxBytesEvidence)] == (
        [] if rx is None else [rx.payload]
    )


@pytest.mark.parametrize("tx_fault", ["ok", "before", "after", "unexpected-after"])
@pytest.mark.parametrize("end_fault", ["ok", "before", "after", "unexpected-after"])
async def test_tx_and_end_ack_failures_are_independent_and_end_keeps_self_contained_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    tx_fault: str,
    end_fault: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        append = c.recorder.append
        attempts: list[str] = []

        def fail(mode: str) -> None:
            if mode == "unexpected-after":
                raise RuntimeError("test-only private lost acknowledgement")
            raise evidence.JournalFailure(
                evidence.JournalOperation.APPEND, evidence.JournalFailureKind.IO_FAILURE
            )

        async def audit(draft: Any) -> Any:
            kind, mode = (
                ("uart_tx_settled", tx_fault)
                if isinstance(draft, evidence.PendingUartTxSettledEvidence)
                else ("interact_ended", end_fault)
                if isinstance(draft, evidence.PendingInteractEndedEvidence)
                else ("other", "ok")
            )
            if kind != "other":
                attempts.append(kind)
            if mode == "before":
                fail(mode)
            record = await append(draft)
            if mode in {"after", "unexpected-after"}:
                fail(mode)
            return record

        monkeypatch.setattr(c.recorder, "append", audit)
        operation = await c.start()
        await c.rx(b"PASS\0unexamined", 11)
        c.writer.allow.set()
        report = await _await(operation.wait())
        missing = [
            kind
            for kind, mode in (
                ("uart_tx_settled", tx_fault),
                ("interact_ended", end_fault),
            )
            if mode != "ok"
        ]
        assert (
            report.durability
            == {
                (): "complete",
                ("uart_tx_settled",): "tx_unconfirmed",
                ("interact_ended",): "end_unconfirmed",
                ("uart_tx_settled", "interact_ended"): "both_unconfirmed",
            }[tuple(missing)]
        )
        assert (report.tx_settled_record is None) == (tx_fault != "ok")
        assert (report.ended_record is None) == (end_fault != "ok")
        assert [(f.record_kind, f.source, f.code) for f in report.audit_failures] == [
            (
                kind,
                "service" if mode == "unexpected-after" else "journal",
                "internal_failure" if mode == "unexpected-after" else "io_failure",
            )
            for kind, mode in (
                ("uart_tx_settled", tx_fault),
                ("interact_ended", end_fault),
            )
            if mode != "ok"
        ]
        assert report.outcome.value == report.observation.outcome.value == "matched"
        assert report.tx.accepted_prefix_bytes == 6 and c.writer.calls == [
            b"\0\xffSEND"
        ]
        assert attempts == ["uart_tx_settled", "interact_ended"]
        rows = await c.records()
        tx_rows = [r for r in rows if isinstance(r, model.UartTxSettledEvidence)]
        end_rows = [r for r in rows if isinstance(r, model.InteractEndedEvidence)]
        assert len(tx_rows) == int(tx_fault != "before")
        assert len(end_rows) == int(end_fault != "before")
        if end_rows:
            ended = end_rows[0]
            assert ended.tx.accepted_prefix_bytes == 6 and ended.tx.submitted
            assert ended.observation == report.observation
            assert ended.tx_settled_sequence == (
                tx_rows[0].sequence if tx_fault == "ok" else None
            )
            if tx_fault == "ok":
                assert ended.tx_audit_failure is None
            else:
                assert ended.tx_audit_failure is not None
                assert ended.tx_audit_failure.code == (
                    "internal_failure"
                    if tx_fault == "unexpected-after"
                    else "io_failure"
                )
        session = c.journal.session_id
    reopened = await _reopen(tmp_path / "recording.db", session)
    assert tuple(
        r
        for r in reopened
        if isinstance(r, (model.UartTxSettledEvidence, model.InteractEndedEvidence))
    ) == (*tx_rows, *end_rows)


@pytest.mark.parametrize("fault", ["before", "after"])
async def test_concurrent_monitor_and_annotations_do_not_replace_a_lost_tx_ack_or_feed_matching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    fault: str,
) -> None:
    from dutchmate_core import annotation, monitor

    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        (c.recorder.fail_before if fault == "before" else c.recorder.fail_ack).add(
            "uart_tx_settled"
        )
        task = await c.begin()
        monitored = c.spawn(
            c.owner.monitor(
                monitor.MonitorRequest(c.journal.session_id, b"M", 1000, 1024)
            )
        )
        await _await(c.recorder.acks["operation_started"].get())
        first = await c.rx(b"PA", 11)
        receipt = await c.owner.annotate(
            annotation.AnnotationRequest(
                c.journal.session_id, "SSM is only a client claim", "cli"
            )
        )
        assert not task.done() and not monitored.done() and c.writer.active == 1
        last = await c.rx(b"SSM", 12)
        monitor_report = await _await(monitored)
        assert (
            monitor_report.outcome.value == "matched"
            and monitor_report.examined_rx_bytes == 5
        )
        c.writer.allow.set()
        report = await _await(task)
        assert report.observation.match == model.InteractMatch(
            0,
            model.MonitorMatchStart(first.sequence, 0),
            model.MonitorMatchEnd(last.sequence, 2),
        )
        assert report.tx_settled_record is None and report.ended_record is not None
        assert (
            report.durability == "tx_unconfirmed"
            and report.observation.examined_rx_bytes == 4
        )
        rows = await c.records()
        assert receipt.annotation in rows
        assert rows[-1].sequence == report.ended_record.sequence
        assert [r.payload for r in rows if isinstance(r, model.RxBytesEvidence)] == [
            b"PA",
            b"SSM",
        ]
        assert c.recorder.attempts.count("uart_tx_settled") == 1
        assert_single_rx_owner(c.fixture)
