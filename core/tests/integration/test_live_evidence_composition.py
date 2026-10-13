"""T009: live read composition shares capture's actual SQLite gate and worker."""

import asyncio
import sqlite3
import threading
from pathlib import Path
from typing import NoReturn, cast

import pytest

from dutchmate_core import model, runtime
from dutchmate_core.adapters import observation_runtime, sqlite_evidence
from dutchmate_core.evidence import (
    EvidencePage,
    EvidencePageOutcome,
    EvidenceRetrievalRequest,
    PendingEvidenceRecord,
    PendingRxBytesEvidence,
    PendingSegmentEndedEvidence,
)
from dutchmate_core.evidence_access import RunEvidencePage
from tests.contract.test_observation_composition import _PROFILE, AdmissionProbe
from tests.integration.test_observation_runtime import _commit, _run


def _no_connection(*args: object, **kwargs: object) -> NoReturn:
    pytest.fail("live composition must not open a second database connection")


class QueryWorkerGate:
    """Pause a real selected page on capture's existing worker, retaining its gate."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.entered = asyncio.Event()
        self.release = threading.Event()
        loop = asyncio.get_running_loop()
        original = sqlite_evidence._retrieve_page_on_worker

        def retrieve(
            connection: sqlite3.Connection,
            policy: model.SessionPolicy,
            request: EvidenceRetrievalRequest,
        ) -> EvidencePage:
            page = original(connection, policy, request)
            loop.call_soon_threadsafe(self.entered.set)
            # Harness watchdog only; release in every test's finally before cleanup.
            if not self.release.wait(3):
                raise AssertionError("test did not release its query worker gate")
            return page

        monkeypatch.setattr(sqlite_evidence, "_retrieve_page_on_worker", retrieve)


async def _entered(event: asyncio.Event, query: asyncio.Task[RunEvidencePage]) -> None:
    notification = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait(
            (notification, query), timeout=3, return_when=asyncio.FIRST_COMPLETED
        )
        if query in done:
            await query  # Preserve explicit missing-access rejection during RED.
            pytest.fail("query bypassed the capture journal worker")
        assert notification in done, "query never reached the existing worker"
    finally:
        if not notification.done():
            notification.cancel()
        await asyncio.gather(notification, return_exceptions=True)


@pytest.mark.asyncio
async def test_t009_handoff_uses_created_capture_journal_and_optional_terminal_opener(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = tmp_path / "profile.toml"
    selected.write_text(_PROFILE, encoding="utf-8")
    original_create = sqlite_evidence.SqliteEvidenceJournal.create
    journals: list[sqlite_evidence.SqliteEvidenceJournal] = []

    async def create(
        path: str | Path, policy: model.SessionPolicy
    ) -> sqlite_evidence.SqliteEvidenceJournal:
        journal = await original_create(path, policy)
        journals.append(journal)
        return journal

    monkeypatch.setattr(
        sqlite_evidence.SqliteEvidenceJournal, "create", staticmethod(create)
    )
    probe = AdmissionProbe([])
    await observation_runtime.attach_basic_observation(
        cast("runtime.ObservationRuntime", probe),
        selected,
        tmp_path / "journal.sqlite3",
    )
    prepared = await probe.captured_preparation()
    try:
        assert len(journals) == 1 and prepared.recorder is journals[0]
        read = prepared.evidence_access
        assert read is not None, "production preparation must supply live read access"
        assert read.live_reader is prepared.recorder
        assert read.session_id == prepared.recorder.session_id
        assert read.policy == prepared.recorder.policy
        # T018 supplies the optional native target; live identity is unchanged.
        assert callable(read.terminal_opener)
    finally:
        await prepared.recorder.close()


@pytest.mark.asyncio
async def test_t009_actual_basic_composition_reads_exact_idle_and_between_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = (bytes(range(256)) + b"\x00\xff\xf5\r\n", b"ambient\r\n\x80\x00")
    async with _run(tmp_path, monkeypatch, payloads) as run:
        first_rx = await run.emit(0)
        with monkeypatch.context() as patch:
            patch.setattr(sqlite3, "connect", _no_connection)
            reference = model.EvidenceReference(run.journal.session_id, 1)
            first = await run.runtime.read_record(reference)
            assert first.run_id == run.active.run_id and first.page.records == (
                first_rx,
            )
            assert first_rx.payload == payloads[0]
            later_rx = await run.emit(1)
            page = await run.runtime.read_page(
                EvidenceRetrievalRequest(run.journal.session_id, 11, 16384)
            )
            assert page.page.records == (run.start, first_rx, later_rx)
            assert [
                r.payload
                for r in page.page.records
                if isinstance(r, model.RxBytesEvidence)
            ] == list(payloads)
            assert (
                page.page.outcome is EvidencePageOutcome.COMPLETE
                and not page.page.truncated
            )
            assert run.runtime.status().state is runtime.RuntimeState.ACTIVE


@pytest.mark.asyncio
async def test_t009_rx_append_and_retention_wait_for_capture_query_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = model.SessionPolicy(2, 65536, 8192, 128, 11, 16384)
    async with _run(tmp_path, monkeypatch, (b"first\x00", b"later\xff"), policy) as run:
        first_rx = await run.emit(0)
        gate = QueryWorkerGate(monkeypatch)
        append_entered = asyncio.Event()
        original_append = run.journal.append

        async def append(draft: PendingEvidenceRecord) -> model.EvidenceRecord:
            if isinstance(draft, PendingRxBytesEvidence):
                append_entered.set()
            return await original_append(draft)

        monkeypatch.setattr(run.journal, "append", append)
        monkeypatch.setattr(sqlite3, "connect", _no_connection)
        query = asyncio.create_task(
            run.runtime.read_page(
                EvidenceRetrievalRequest(run.journal.session_id, 11, 16384)
            )
        )
        try:
            await _entered(gate.entered, query)
            run.serial.gates[1].set()
            await asyncio.wait_for(append_entered.wait(), timeout=3)
            assert not query.done() and run.commits.empty()
            gate.release.set()
            before_eviction = await asyncio.wait_for(query, timeout=3)
            later_rx = await _commit(run.commits, 2)
            assert before_eviction.page.records == (run.start, first_rx)
            assert before_eviction.page.snapshot_end_exclusive == 2
            assert before_eviction.page.expired_range is None
            after = await run.runtime.read_page(
                EvidenceRetrievalRequest(run.journal.session_id, 11, 16384)
            )
            assert after.page.records == (first_rx, later_rx)
            assert after.page.outcome is EvidencePageOutcome.PARTIAL
            assert after.page.expired_range == model.SequenceRange(0, 1)
            assert after.page.retention_marker is not None
            assert after.page.retention_marker.discarded_record_count == 1
        finally:
            gate.release.set()
            await asyncio.gather(query, return_exceptions=True)


@pytest.mark.asyncio
async def test_t009_final_append_and_recorder_close_follow_the_same_live_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _run(tmp_path, monkeypatch, ()) as run:
        gate = QueryWorkerGate(monkeypatch)
        final_append_entered, close_entered = asyncio.Event(), asyncio.Event()
        original_append, original_close = run.journal.append, run.journal.close

        async def append(draft: PendingEvidenceRecord) -> model.EvidenceRecord:
            if isinstance(draft, PendingSegmentEndedEvidence):
                final_append_entered.set()
            return await original_append(draft)

        async def close() -> None:
            close_entered.set()
            await original_close()

        monkeypatch.setattr(run.journal, "append", append)
        monkeypatch.setattr(run.journal, "close", close)
        monkeypatch.setattr(sqlite3, "connect", _no_connection)
        query = asyncio.create_task(
            run.runtime.read_page(
                EvidenceRetrievalRequest(run.journal.session_id, 11, 16384)
            )
        )
        detach: asyncio.Task[runtime.RuntimeStatus] | None = None
        try:
            await _entered(gate.entered, query)
            detach = asyncio.create_task(run.runtime.detach())
            await asyncio.wait_for(final_append_entered.wait(), timeout=3)
            assert (
                not detach.done() and not close_entered.is_set() and run.commits.empty()
            )
            gate.release.set()
            report = await asyncio.wait_for(query, timeout=3)
            terminal = await asyncio.wait_for(detach, timeout=3)
            assert report.page.records == (run.start,)
            assert terminal.owner_settled and terminal.recorder_close_confirmed
            assert close_entered.is_set()
            assert isinstance(await _commit(run.commits, 1), model.SegmentEndedEvidence)
            # T018 terminal acceptance is covered separately by T017; this
            # capture-only connection tripwire remains armed through close.
        finally:
            gate.release.set()
            await asyncio.gather(query, return_exceptions=True)
            if detach is not None:
                await asyncio.gather(detach, return_exceptions=True)
