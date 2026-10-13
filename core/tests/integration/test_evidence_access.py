"""Real runtime/acquisition/SQLite retrieval on both normalized backend fixtures.

T007 supplies actual durable commit observations. T014 can bind the same source
helper to the service-owned runtime, without creating another owner or copying
admission/retrieval policy. No terminal reader or fallback is implemented here.
"""

import asyncio
import errno
import shutil
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast

import pytest
import pytest_asyncio

from dutchmate_core import acquisition as aq
from dutchmate_core import evidence_access as access
from dutchmate_core import model
from dutchmate_core import runtime as rt
from dutchmate_core.adapters import (
    observation_runtime,
    sqlite_evidence,
    terminal_evidence,
)
from dutchmate_core.adapters.sqlite_evidence import SqliteEvidenceJournal
from dutchmate_core.evidence import (
    EvidenceCursor,
    EvidencePageOutcome,
    EvidenceRetrievalRequest,
    JournalFailure,
    JournalFailureKind,
    JournalOperation,
    PendingEvidenceRecord,
)
from dutchmate_core.profile import ResolvedDutProfile
from tests.contract.test_evidence_access import ReadRuntime
from tests.contract.test_observation_composition import _PROFILE
from tests.contract.test_observation_runtime import _profile
from tests.contract.test_terminal_evidence_reader import ConnectionProbe
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixture,
    BackendFixtureFactory,
    FixtureLifecycleGate,
)
from tests.integration.test_observation_runtime import _run

_OPAQUE_FIELDS = (
    model.ProvenanceField("count", 7),
    model.ProvenanceField("flag", False),
    model.ProvenanceField("text", "opaque-é"),
    model.ProvenanceField("unknown", None),
)


async def _bounded[T](work: Awaitable[T]) -> T:
    # Test watchdog only. Acquisition/query/cleanup retain their product contracts.
    async with asyncio.timeout(3):
        return await work


class CommitObserver:
    """Capture lifecycle port over the real journal, with no read methods."""

    def __init__(self, journal: SqliteEvidenceJournal) -> None:
        self.journal = journal
        self.commits: asyncio.Queue[model.EvidenceRecord] = asyncio.Queue()
        self.close_calls = 0

    @property
    def session_id(self) -> model.SessionId:
        return self.journal.session_id

    @property
    def policy(self) -> model.SessionPolicy:
        return self.journal.policy

    async def append(self, draft: PendingEvidenceRecord) -> model.EvidenceRecord:
        record = await self.journal.append(draft)
        self.commits.put_nowait(record)
        return record

    async def close(self) -> None:
        self.close_calls += 1
        await self.journal.close()


class JournalRun:
    def __init__(
        self,
        journal: SqliteEvidenceJournal,
        fixture: BackendFixture,
        *,
        runtime: rt.ObservationRuntime | None = None,
        profile: ResolvedDutProfile | None = None,
    ) -> None:
        # T014 may hand in the actual service-owned runtime; never create a
        # second owner merely to reuse the real-journal commit observer.
        self.runtime = cast(
            "ReadRuntime", rt.ObservationRuntime() if runtime is None else runtime
        )
        self.profile = _profile() if profile is None else profile
        self.journal = journal
        self.fixture = fixture
        self.recorder = CommitObserver(journal)
        gate = getattr(fixture.backend, "open_gate", None)
        assert isinstance(gate, FixtureLifecycleGate)
        self.open_gate = gate
        self.tasks: list[asyncio.Task[rt.RuntimeStatus]] = []
        # Supply durable opaque fixture provenance, preserving capabilities,
        # timestamp observer/unit/origin and loss observability exactly as reported.
        fixture.connection.descriptor = replace(
            fixture.connection.descriptor,
            connection_provenance=model.PersistedConnectionProvenance(
                model.ConnectionProvenanceSnapshot(
                    envelope_version=1,
                    backend_kind="fixture/evidence-integration",
                    backend_schema_version=37,
                    fields=_OPAQUE_FIELDS,
                )
            ),
        )

    def attach(self) -> asyncio.Task[rt.RuntimeStatus]:
        constructor = cast(
            "Callable[..., rt.PreparedObservationRun]", rt.PreparedObservationRun
        )
        prepared = constructor(
            recorder=self.recorder,
            backend=self.fixture.backend,
            evidence_access=access.PreparedEvidenceAccess(
                self.journal.session_id,
                replace(self.journal.policy),
                live_reader=self.journal,
            ),
        )

        async def prepare(resolved: ResolvedDutProfile) -> rt.PreparedObservationRun:
            assert resolved.session_policy == self.journal.policy
            return prepared

        task = asyncio.create_task(self.runtime.attach(self.profile, prepare))
        self.tasks.append(task)
        return task

    async def active(self) -> tuple[rt.RuntimeStatus, model.SegmentStartedEvidence]:
        result = await _bounded(self.attach())
        assert result.state is rt.RuntimeState.ACTIVE
        start = await self.commit(0)
        assert isinstance(start, model.SegmentStartedEvidence)
        assert self.fixture.connection.consumer_calls == 1
        return result, start

    async def commit(self, sequence: int) -> model.EvidenceRecord:
        record = await _bounded(self.recorder.commits.get())
        assert record.sequence == sequence
        return record

    async def emit(self, payload: bytes, *, sequence: int, timestamp: int) -> None:
        await self.fixture.connection.emit_rx(payload, timestamp=timestamp)
        record = await self.commit(sequence)
        assert isinstance(record, model.RxBytesEvidence)
        assert record.payload == payload and record.observed_at.value == timestamp

    async def record(self, sequence: int) -> access.RunEvidencePage:
        method = getattr(self.runtime, "read_record", None)
        assert callable(method), (
            "T008 ObservationRuntime.read_record is not implemented"
        )
        return await _bounded(
            self.runtime.read_record(
                model.EvidenceReference(self.journal.session_id, sequence)
            )
        )

    async def page(
        self,
        *,
        reference: model.EvidenceRangeReference | None = None,
        max_records: int = 10,
        cursor: EvidenceCursor | None = None,
    ) -> access.RunEvidencePage:
        method = getattr(self.runtime, "read_page", None)
        assert callable(method), "T008 ObservationRuntime.read_page is not implemented"
        return await _bounded(
            self.runtime.read_page(
                EvidenceRetrievalRequest(
                    self.journal.session_id if reference is None else reference,
                    max_records,
                    16384,
                    cursor,
                )
            )
        )

    async def finish(self) -> None:
        for gate in (
            self.open_gate,
            self.fixture.connection.read_gate,
            self.fixture.connection.event_gate,
            self.fixture.connection.consumer_exit_gate,
            self.fixture.connection.close_gate,
        ):
            gate.allow.set()
        try:
            await _bounded(asyncio.gather(*self.tasks, return_exceptions=True))
            await _bounded(self.runtime.detach())
        finally:
            # Test-owned fallback is not a claim that runtime confirmed closure.
            await _bounded(self.journal.close())


@pytest.fixture(params=BACKEND_FIXTURE_FACTORIES, ids=("basic", "enhanced-shaped"))
def backend(request: pytest.FixtureRequest) -> BackendFixture:
    # The established Core autouse Serial tripwire applies; use only these explicit
    # normalized fixtures, with no URL/discovery reference or physical selection.
    return cast("BackendFixtureFactory", request.param)()


@pytest_asyncio.fixture
async def run(tmp_path: Path, backend: BackendFixture) -> AsyncIterator[JournalRun]:
    journal = await SqliteEvidenceJournal.create(
        tmp_path / "evidence.sqlite3", _profile().session_policy
    )
    source = JournalRun(journal, backend)
    try:
        yield source
    finally:
        await source.finish()


@pytest.mark.parametrize(
    "payload",
    [
        bytes(range(256)),
        b"\x00\x80\xfe\xffinvalid-utf8:\xf5",
        b"first\r\nsecond\nthird\rlast\x00",
    ],
    ids=("all256", "nul-non-utf8", "crlf-lf-cr"),
)
@pytest.mark.asyncio
async def test_idle_ambient_rx_is_exact_and_retrievable_without_starting_another_reader(
    run: JournalRun,
    payload: bytes,
) -> None:
    active, start = await run.active()
    # There is no read/operation running when this unsolicited output is committed.
    await run.emit(payload, sequence=1, timestamp=11)
    report = await run.record(1)
    assert (
        report.run_id == active.run_id and report.session_id == run.journal.session_id
    )
    assert report.page.outcome is EvidencePageOutcome.COMPLETE
    assert not report.page.truncated and report.page.continuation is None
    assert len(report.page.records) == 1
    rx = report.page.records[0]
    assert isinstance(rx, model.RxBytesEvidence)
    assert type(rx.payload) is bytes and rx.payload == payload
    assert rx.sequence == 1 and rx.observed_at.value == 11
    assert (
        rx.observed_at.domain_id
        == run.fixture.connection.descriptor.backend_observation_timestamp_domain.domain_id
    )
    assert rx.connection_id == start.connection_id and rx.segment_id == start.segment_id
    assert run.runtime.status().state is rt.RuntimeState.ACTIVE
    assert (
        run.fixture.connection.consumer_calls == 1 and not run.fixture.connection.closed
    )
    assert run.recorder.close_calls == 0


@pytest.mark.asyncio
async def test_output_between_completed_reads_remains_durable_ambient_evidence(
    run: JournalRun,
) -> None:
    active, _ = await run.active()
    await run.emit(b"before\x00", sequence=1, timestamp=10)
    first = await run.page()
    assert [r.sequence for r in first.page.records] == [0, 1]
    assert first.page.snapshot_end_exclusive == 2
    # The previous read has returned; acquisition still owns the only RX stream.
    await run.emit(b"later\xff\r\n", sequence=2, timestamp=20)
    second = await run.page()
    assert [r.sequence for r in second.page.records] == [0, 1, 2]
    assert second.page.snapshot_end_exclusive == 3
    assert [
        r.payload for r in second.page.records if isinstance(r, model.RxBytesEvidence)
    ] == [b"before\x00", b"later\xff\r\n"]
    assert (await run.record(2)).page.records == (second.page.records[2],)
    assert first.page.snapshot_end_exclusive == 2 and len(first.page.records) == 2
    assert first.run_id == second.run_id == active.run_id
    assert run.fixture.connection.consumer_calls == 1 and run.recorder.close_calls == 0


@pytest.mark.asyncio
async def test_range_and_individual_references_preserve_half_open_order_and_rx_chunks(
    run: JournalRun,
) -> None:
    active, start = await run.active()
    for sequence, (payload, timestamp) in enumerate(
        ((b"\x00A", 10), (b"\xff\r\n", 20), (b"C\n", 30)),
        start=1,
    ):
        await run.emit(payload, sequence=sequence, timestamp=timestamp)
    reference = model.EvidenceRangeReference(run.journal.session_id, 1, 3)
    report = await run.page(reference=reference)
    assert report.run_id == active.run_id
    assert [r.sequence for r in report.page.records] == [1, 2]
    assert (
        report.page.outcome is EvidencePageOutcome.COMPLETE
        and not report.page.truncated
    )
    assert report.page.continuation is None and report.page.snapshot_end_exclusive == 3
    rx = tuple(r for r in report.page.records if isinstance(r, model.RxBytesEvidence))
    assert len(rx) == 2 and [r.payload for r in rx] == [b"\x00A", b"\xff\r\n"]
    assert [r.observed_at.value for r in rx] == [10, 20]
    assert all(
        r.connection_id == start.connection_id and r.segment_id == start.segment_id
        for r in rx
    )
    single = await run.record(2)
    assert len(single.page.records) == 1 and single.page.records[0] == rx[1]
    whole = await run.page()
    assert [r.sequence for r in whole.page.records] == [0, 1, 2, 3]
    last = whole.page.records[3]
    assert isinstance(last, model.RxBytesEvidence) and last.payload == b"C\n"


@pytest.mark.asyncio
async def test_bounded_record_pages_continue_in_order_without_splitting_payloads(
    run: JournalRun,
) -> None:
    await run.active()
    for sequence, payload in enumerate((b"one\x00", b"two\xff", b"three\r\n"), start=1):
        await run.emit(payload, sequence=sequence, timestamp=sequence * 10)
    first = await run.page(max_records=2)
    assert [r.sequence for r in first.page.records] == [0, 1]
    assert first.page.outcome is EvidencePageOutcome.COMPLETE and first.page.truncated
    assert first.page.snapshot_end_exclusive == 4
    assert first.page.continuation == EvidenceCursor(
        run.journal.session_id, 0, None, 4, 2
    )
    second = await run.page(max_records=2, cursor=first.page.continuation)
    assert [r.sequence for r in second.page.records] == [2, 3]
    assert second.page.snapshot_end_exclusive == 4 and not second.page.truncated
    assert second.page.continuation is None and second.run_id == first.run_id
    rx = tuple(
        r
        for r in (*first.page.records, *second.page.records)
        if isinstance(r, model.RxBytesEvidence)
    )
    assert [r.payload for r in rx] == [b"one\x00", b"two\xff", b"three\r\n"]
    assert run.fixture.connection.consumer_calls == 1


@pytest.mark.parametrize("kind", ["record", "page"])
@pytest.mark.asyncio
async def test_pre_segment_empty_journal_never_invents_connection_or_provenance(
    run: JournalRun,
    kind: Literal["record", "page"],
) -> None:
    run.open_gate.allow.clear()
    attach = run.attach()
    await _bounded(run.open_gate.entered.wait())
    before = run.runtime.status()
    assert (
        before.state is rt.RuntimeState.ATTACHING
        and before.session_id == run.journal.session_id
    )
    report = await (run.record(0) if kind == "record" else run.page())
    assert report.run_id == before.run_id and report.session_id == before.session_id
    assert report.page.records == () and report.page.snapshot_end_exclusive == 0
    assert report.page.outcome is (
        EvidencePageOutcome.NOT_FOUND
        if kind == "record"
        else EvidencePageOutcome.COMPLETE
    )
    assert not report.page.truncated and report.page.continuation is None
    assert report.page.retention_marker is None and report.page.expired_range is None
    assert report.page.charged_bytes == 0 and run.recorder.commits.empty()
    assert run.fixture.connection.consumer_calls == 0 and run.runtime.status() == before
    run.open_gate.allow.set()
    assert (await _bounded(attach)).state is rt.RuntimeState.ACTIVE


@pytest.mark.asyncio
async def test_reported_capabilities_timestamp_loss_and_opaque_provenance_survive_readback(
    run: JournalRun,
) -> None:
    await run.active()
    reported = run.fixture.connection.descriptor
    page = (await run.record(0)).page
    assert len(page.records) == 1
    start = page.records[0]
    assert isinstance(start, model.SegmentStartedEvidence)
    assert start.provenance.capabilities == reported.capabilities
    assert (
        start.provenance.backend_observation_timestamp_domain
        == reported.backend_observation_timestamp_domain
    )
    assert start.provenance.loss_observability == reported.loss_observability
    opaque = start.provenance.connection_provenance.to_snapshot()
    assert opaque.envelope_version == 1 and opaque.backend_schema_version == 37
    assert opaque.backend_kind == "fixture/evidence-integration"
    assert [(f.name, f.value) for f in opaque.fields] == [
        ("count", 7),
        ("flag", False),
        ("text", "opaque-é"),
        ("unknown", None),
    ]
    assert reported.capabilities.supports(model.BackendCapability.UART_RECEIVE)
    current = run.runtime.status()
    assert current.profile is not None and not current.profile.policy.uart_tx_enabled


@pytest.mark.asyncio
async def test_loss_evidence_matches_reported_observer_without_emulating_missing_telemetry(
    run: JournalRun,
) -> None:
    await run.active()
    loss = run.fixture.connection.descriptor.loss_observability
    if isinstance(loss, model.ObserverReportsUartLoss):
        emit = getattr(run.fixture.connection, "emit_observer_loss", None)
        assert callable(emit)
        await cast("Callable[..., Awaitable[None]]", emit)(
            cause="overflow", lost_bytes=3, timestamp=7
        )
        await run.commit(1)
        await run.emit(b"after-loss\xff", sequence=2, timestamp=11)
    else:
        assert isinstance(loss, model.UpstreamLossNotObservable)
        await run.emit(b"after-loss\xff", sequence=1, timestamp=11)
    report = await run.page()
    losses = tuple(
        r for r in report.page.records if isinstance(r, model.ObserverLossEvidence)
    )
    if isinstance(loss, model.ObserverReportsUartLoss):
        assert len(losses) == 1
        assert (
            losses[0].observer_id == loss.observer_id and losses[0].scope == loss.scope
        )
        assert (
            losses[0].cause is model.ObserverLossCause.OVERFLOW
            and losses[0].lost_bytes == 3
        )
        assert losses[0].observed_at.value == 7
        assert (
            losses[0].observed_at.domain_id
            == run.fixture.connection.descriptor.backend_observation_timestamp_domain.domain_id
        )
        assert [r.sequence for r in report.page.records] == [0, 1, 2]
    else:
        assert losses == () and [r.sequence for r in report.page.records] == [0, 1]
    rx = tuple(r for r in report.page.records if isinstance(r, model.RxBytesEvidence))
    assert len(rx) == 1 and rx[0].payload == b"after-loss\xff"


@pytest.mark.asyncio
async def test_origin_boundary_preserves_record_order_and_separate_provenance(
    run: JournalRun,
) -> None:
    await run.active()
    original = run.fixture.connection.descriptor.backend_observation_timestamp_domain
    await run.emit(b"old\x00", sequence=1, timestamp=11)
    new = replace(
        original, domain_id="new-fixture-domain", origin_id="new-fixture-origin"
    )
    await run.fixture.connection.reset_timestamp_origin(new)
    assert isinstance(await run.commit(2), model.SegmentEndedEvidence)
    assert isinstance(await run.commit(3), model.SegmentStartedEvidence)
    await run.emit(b"new\xff", sequence=4, timestamp=2)
    report = await run.page()
    assert [r.sequence for r in report.page.records] == [0, 1, 2, 3, 4]
    first, before, ended, second, after = report.page.records
    assert isinstance(first, model.SegmentStartedEvidence) and isinstance(
        second, model.SegmentStartedEvidence
    )
    assert isinstance(before, model.RxBytesEvidence) and isinstance(
        after, model.RxBytesEvidence
    )
    assert (
        isinstance(ended, model.SegmentEndedEvidence)
        and ended.reason is model.SegmentEndReason.TIMESTAMP_ORIGIN_RESET
    )
    assert (
        first.connection_id == second.connection_id
        and first.segment_id != second.segment_id
    )
    assert first.provenance.backend_observation_timestamp_domain == original
    assert second.provenance.backend_observation_timestamp_domain == new
    assert before.payload == b"old\x00" and after.payload == b"new\xff"
    assert before.observed_at == model.BackendObservationTimestamp(
        original.domain_id, 11
    )
    assert after.observed_at == model.BackendObservationTimestamp(new.domain_id, 2)
    assert (
        before.segment_id == first.segment_id and after.segment_id == second.segment_id
    )


@pytest.mark.asyncio
async def test_missing_reported_receive_capability_rejects_without_emulated_evidence(
    run: JournalRun,
) -> None:
    run.fixture.connection.descriptor = replace(
        run.fixture.connection.descriptor,
        capabilities=model.BackendCapabilities(frozenset()),
    )
    result = await _bounded(run.attach())
    assert result.state is rt.RuntimeState.FAILED and result.owner_settled
    assert result.primary_issue == rt.RuntimeIssue(
        rt.RuntimeIssueSource.ACQUISITION_START,
        aq.AcquisitionFailureKind.CAPABILITY_REJECTION,
    )
    assert result.recorder_close_confirmed and result.physical_release_confirmed
    assert (
        result.session_id == run.journal.session_id and result.acquisition is not None
    )
    assert result.acquisition.provenance is None and run.recorder.commits.empty()
    assert run.fixture.connection.consumer_calls == 0 and run.recorder.close_calls == 1
    with pytest.raises(access.EvidenceReadRejected) as rejected:
        await run.page()
    assert rejected.value.kind == "read_unavailable"


@pytest.mark.asyncio
async def test_t014_active_mvp_never_reopens_the_journal_after_detach(
    run: JournalRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("US1 must not add terminal or writable journal reopening")

    monkeypatch.setattr(SqliteEvidenceJournal, "open", forbidden)
    await run.active()
    await run.emit(bytes(range(256)), sequence=1, timestamp=11)
    assert (await run.record(1)).page.records[0] == (await run.page()).page.records[1]
    terminal = await _bounded(run.runtime.detach())
    assert terminal.owner_settled and terminal.recorder_close_confirmed
    for query in (run.record(1), run.page()):
        with pytest.raises(access.EvidenceReadRejected) as caught:
            await query
        assert caught.value.kind == "read_unavailable"
    assert run.recorder.close_calls == 1 and run.fixture.connection.consumer_calls == 1


# T017: real journal association and composition handoff. No terminal runtime
# implementation is supplied by the tests; only the documented prepared port.


async def _t017_attach_terminal(run: JournalRun, path: Path) -> rt.RuntimeStatus:
    target = terminal_evidence.capture_terminal_target(
        path, session_id=run.journal.session_id, policy=run.journal.policy
    )
    assert target is not None

    async def opener() -> access.OwnedEvidenceReadPort:
        return await terminal_evidence.open_terminal_reader(target)

    async def prepare(resolved: ResolvedDutProfile) -> rt.PreparedObservationRun:
        return rt.PreparedObservationRun(
            run.recorder,
            run.fixture.backend,
            access.PreparedEvidenceAccess(
                run.journal.session_id, run.journal.policy, run.journal, opener
            ),
        )

    active = await _bounded(run.runtime.attach(run.profile, prepare))
    assert active.state is rt.RuntimeState.ACTIVE
    start = await run.commit(0)
    assert isinstance(start, model.SegmentStartedEvidence)
    return active


def _t017_forbid_writable(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail(
            "terminal association cannot reopen writable capture or discover a journal"
        )

    monkeypatch.setattr(SqliteEvidenceJournal, "open", forbidden)
    monkeypatch.setattr(SqliteEvidenceJournal, "create", forbidden)


@pytest.mark.parametrize("stop", ["detach", "disconnect", "stream_failure"])
@pytest.mark.asyncio
async def test_t017_real_closed_journal_keeps_last_run_binary_provenance_and_boundaries(
    run: JournalRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    active = await _t017_attach_terminal(run, tmp_path / "evidence.sqlite3")
    await run.emit(bytes(range(256)) + b"\0\xff\xfe\r\n", sequence=1, timestamp=11)
    if stop == "disconnect":
        await run.fixture.connection.disconnect()
    elif stop == "stream_failure":
        await run.fixture.connection.end_stream_unexpectedly()
    if stop != "detach":
        # The final committed record is the autonomous lifecycle boundary witness.
        end = await run.commit(2)
        assert isinstance(end, model.SegmentEndedEvidence)
    terminal = await _bounded(run.runtime.detach())
    assert terminal.owner_settled and terminal.recorder_close_confirmed
    with pytest.raises(JournalFailure) as writer_closed:
        await run.journal.retrieve(
            EvidenceRetrievalRequest(run.journal.session_id, 10, 16384)
        )
    assert writer_closed.value.kind is JournalFailureKind.CLOSED
    _t017_forbid_writable(monkeypatch)
    page = await run.page()
    record = await run.record(1)
    assert page.run_id == record.run_id == active.run_id
    assert page.session_id == record.session_id == active.session_id
    assert [r.sequence for r in page.page.records] == [0, 1, 2]
    start, rx, end = page.page.records
    assert isinstance(start, model.SegmentStartedEvidence)
    assert isinstance(rx, model.RxBytesEvidence)
    assert isinstance(end, model.SegmentEndedEvidence)
    assert rx.payload == bytes(range(256)) + b"\0\xff\xfe\r\n"
    assert record.page.records == (rx,)
    reported = run.fixture.connection.descriptor
    assert start.provenance.capabilities == reported.capabilities
    assert (
        start.provenance.backend_observation_timestamp_domain
        == reported.backend_observation_timestamp_domain
    )
    assert start.provenance.loss_observability == reported.loss_observability
    assert (
        start.provenance.connection_provenance.to_snapshot()
        == reported.connection_provenance.to_snapshot()
    )
    assert end.connection_id == rx.connection_id == start.provenance.connection_id
    assert end.segment_id == rx.segment_id == start.provenance.segment_id
    assert page.page.outcome is EvidencePageOutcome.COMPLETE and not page.page.truncated
    assert run.recorder.close_calls == 1 and run.fixture.connection.consumer_calls == 1
    assert run.runtime.status() == terminal


@pytest.mark.asyncio
async def test_t017_runtime_rejects_replaced_terminal_source_without_rewriting_status(
    run: JournalRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "evidence.sqlite3"
    await _t017_attach_terminal(run, path)
    await run.emit(b"original\0\xff", sequence=1, timestamp=11)
    terminal = await _bounded(run.runtime.detach())
    replacement = tmp_path / "replacement.sqlite3"
    shutil.copyfile(path, replacement)
    replacement.replace(path)
    before = path.read_bytes()
    _t017_forbid_writable(monkeypatch)
    with pytest.raises(access.EvidenceReadRejected) as caught:
        await run.page()
    assert caught.value.kind == "source_changed"
    assert path.read_bytes() == before and run.runtime.status() == terminal
    # Confirmed partial-open rejection is not a reader-cleanup failure.
    assert getattr(run.runtime, "evidence_read_cleanup_confirmed", None) is True


@pytest.mark.asyncio
async def test_t017_real_known_failed_preparation_retains_closed_empty_session(
    run: JournalRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = terminal_evidence.capture_terminal_target(
        tmp_path / "evidence.sqlite3",
        session_id=run.journal.session_id,
        policy=run.journal.policy,
    )
    assert target is not None
    await run.journal.close()
    assert "terminal_evidence_access" in rt.PreparationFailure.__dataclass_fields__, (
        "T018 PreparationFailure terminal handoff is not implemented"
    )

    async def opener() -> access.OwnedEvidenceReadPort:
        return await terminal_evidence.open_terminal_reader(target)

    constructor = cast("Callable[..., rt.PreparationFailure]", rt.PreparationFailure)
    failure = constructor(
        primary_issue=rt.RuntimeIssue(
            rt.RuntimeIssueSource.PREPARATION, JournalFailureKind.IO_FAILURE
        ),
        session_id=run.journal.session_id,
        recorder_close_confirmed=True,
        terminal_evidence_access=access.PreparedEvidenceAccess(
            run.journal.session_id, run.journal.policy, terminal_opener=opener
        ),
    )

    async def prepare(resolved: ResolvedDutProfile) -> rt.PreparedObservationRun:
        raise failure

    terminal = await _bounded(run.runtime.attach(run.profile, prepare))
    _t017_forbid_writable(monkeypatch)
    page = await run.page()
    assert page.run_id == terminal.run_id and page.session_id == run.journal.session_id
    assert page.page.records == () and page.page.snapshot_end_exclusive == 0
    assert page.page.outcome is EvidencePageOutcome.COMPLETE
    assert (
        terminal.primary_issue == failure.primary_issue and terminal.attach_admissible
    )
    assert (
        run.runtime.status() == terminal and run.fixture.connection.consumer_calls == 0
    )


@pytest.mark.asyncio
async def test_t017_actual_basic_composition_hands_off_terminal_source_after_detach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _run(tmp_path, monkeypatch, (bytes(range(256)) + b"\0\xff\r\n",)) as run:
        rx = await run.emit(0)
        terminal = await run.runtime.detach()
        before = run.journal_path.read_bytes()
        _t017_forbid_writable(monkeypatch)
        report = await run.runtime.read_record(
            model.EvidenceReference(run.journal.session_id, 1)
        )
        assert report.run_id == run.active.run_id and report.page.records == (rx,)
        assert run.journal_path.read_bytes() == before
        assert run.runtime.status() == terminal and run.serial.close_calls == 1


@pytest.mark.asyncio
async def test_t017_actual_composition_preserves_known_session_after_backend_construction_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "profile.toml"
    selected.write_text(_PROFILE, encoding="utf-8")
    destination = tmp_path / "failed-preparation.sqlite3"
    runtime = rt.ObservationRuntime()

    def fail_backend(*args: object, **kwargs: object) -> None:
        raise RuntimeError("private test-only constructor failure")

    monkeypatch.setattr(observation_runtime, "BasicSerialBackend", fail_backend)
    terminal = await _bounded(
        observation_runtime.attach_basic_observation(runtime, selected, destination)
    )
    assert terminal.state is rt.RuntimeState.FAILED and terminal.session_id is not None
    assert (
        terminal.owner_settled
        and terminal.recorder_close_confirmed
        and terminal.attach_admissible
    )
    before = destination.read_bytes()
    _t017_forbid_writable(monkeypatch)
    page = await runtime.read_page(
        EvidenceRetrievalRequest(terminal.session_id, 10, 16384)
    )
    assert page.run_id == terminal.run_id and page.page.records == ()
    assert destination.read_bytes() == before and runtime.status() == terminal


@pytest.mark.asyncio
async def test_t017_identity_capture_failure_keeps_production_live_access_without_terminal_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The optional native-metadata boundary alone fails; actual live capture works.
    captures: list[Path] = []

    def unavailable(path: str | Path, **kwargs: object) -> None:
        captures.append(Path(path))
        return None

    _t017_patch_capture(monkeypatch, unavailable)
    async with _run(tmp_path, monkeypatch, (b"live-only\0\xff",)) as run:
        rx = await run.emit(0)
        live = await run.runtime.read_record(
            model.EvidenceReference(run.journal.session_id, 1)
        )
        assert live.page.records == (rx,)
        terminal = await run.runtime.detach()
        _t017_forbid_writable(monkeypatch)
        with pytest.raises(access.EvidenceReadRejected) as caught:
            await run.runtime.read_record(
                model.EvidenceReference(run.journal.session_id, 1)
            )
        assert caught.value.kind == "read_unavailable"
        assert captures == [run.journal_path], (
            "T018 optional native target capture is not wired"
        )
        assert run.runtime.status() == terminal


@pytest.mark.asyncio
async def test_t017_unallocated_composition_failure_never_browses_partial_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "profile.toml"
    selected.write_text(_PROFILE, encoding="utf-8")
    destination = tmp_path / "partial.sqlite3"
    artifact = b"test-only incomplete artifact with no allocated session"
    destination.write_bytes(artifact)

    async def failed_create(
        path: str | Path, policy: model.SessionPolicy
    ) -> SqliteEvidenceJournal:
        raise JournalFailure(JournalOperation.CREATE, JournalFailureKind.IO_FAILURE)

    def forbidden_capture(*args: object, **kwargs: object) -> None:
        pytest.fail(
            "unallocated preparation must not capture identity from a partial artifact"
        )

    monkeypatch.setattr(SqliteEvidenceJournal, "create", failed_create)
    _t017_patch_capture(monkeypatch, forbidden_capture)
    runtime = rt.ObservationRuntime()
    terminal = await _bounded(
        observation_runtime.attach_basic_observation(runtime, selected, destination)
    )
    assert terminal.session_id is None and terminal.owner_settled
    with pytest.raises(access.EvidenceReadRejected) as caught:
        await runtime.read_page(
            EvidenceRetrievalRequest(model.SessionId("not-allocated"), 10, 16384)
        )
    assert caught.value.kind == "no_associated_session"
    assert destination.read_bytes() == artifact and runtime.status() == terminal


def _t017_patch_capture(
    monkeypatch: pytest.MonkeyPatch, replacement: Callable[..., object]
) -> None:
    original = terminal_evidence.capture_terminal_target
    monkeypatch.setattr(terminal_evidence, "capture_terminal_target", replacement)
    # Observe the native-metadata boundary equally through a module import or a
    # direct imported alias; no constraint on production's import spelling.
    for name, value in tuple(vars(observation_runtime).items()):
        if value is original:
            monkeypatch.setattr(observation_runtime, name, replacement)


@pytest.mark.asyncio
async def test_t019_terminal_record_delivery_uses_one_read_only_snapshot_and_closed_reader(
    run: JournalRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "evidence.sqlite3"
    active = await _t017_attach_terminal(run, path)
    await run.emit(bytes(range(256)) + b"\0\xff\r\n", sequence=1, timestamp=11)
    terminal = await _bounded(run.runtime.detach())
    before = path.read_bytes()
    _t017_forbid_writable(monkeypatch)
    probe = ConnectionProbe(monkeypatch)
    result = await run.record(1)
    assert result.run_id == active.run_id and result.session_id == active.session_id
    assert len(result.page.records) == 1
    record = result.page.records[0]
    assert isinstance(record, model.RxBytesEvidence)
    assert record.payload == bytes(range(256)) + b"\0\xff\r\n"
    probe.read_only(path)
    assert path.read_bytes() == before and run.runtime.status() == terminal
    assert run.recorder.close_calls == 1 and run.fixture.connection.consumer_calls == 1


@pytest.mark.asyncio
async def test_t019_native_reader_close_uncertainty_discards_page_and_preserves_capture_facts(
    run: JournalRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "evidence.sqlite3"
    await _t017_attach_terminal(run, path)
    await run.emit(b"private exact bytes\0\xff", sequence=1, timestamp=11)
    terminal = await _bounded(run.runtime.detach())
    before = path.read_bytes()
    _t017_forbid_writable(monkeypatch)
    probe = ConnectionProbe(monkeypatch)
    probe.close_failure = OSError(errno.EIO, "test-only private close detail")
    with pytest.raises(JournalFailure) as caught:
        await run.page()
    assert caught.value.operation is JournalOperation.CLOSE
    assert (
        caught.value.kind is JournalFailureKind.IO_FAILURE
        and caught.value.detail is None
    )
    assert not cast(
        "rt.ObservationRuntime", run.runtime
    ).evidence_read_cleanup_confirmed
    assert probe.close_calls == 1 and probe.closed == probe.connections
    assert run.runtime.status() == terminal and terminal.attach_admissible
    with pytest.raises(access.EvidenceReadRejected) as unavailable:
        await run.page()
    assert unavailable.value.kind == "read_unavailable" and len(probe.connections) == 1
    assert path.read_bytes() == before


# T020: Feature003 is the page/charge/marker authority. The terminal oracle is a
# separate copy of a positively closed source, never a writable runtime fallback.


@asynccontextmanager
async def _t020_source(
    tmp_path: Path, backend: BackendFixture, *, retained: int
) -> AsyncIterator[JournalRun]:
    profile = replace(
        _profile(),
        session_policy=replace(
            _profile().session_policy, max_retained_records=retained
        ),
    )
    path = tmp_path / "t020-source.sqlite3"
    journal = await SqliteEvidenceJournal.create(path, profile.session_policy)
    run = JournalRun(journal, backend, profile=profile)
    try:
        await _t017_attach_terminal(run, path)
        yield run
    finally:
        await run.finish()


@asynccontextmanager
async def _t020_oracle(
    run: JournalRun, tmp_path: Path, mode: str
) -> AsyncIterator[SqliteEvidenceJournal]:
    if mode == "active":
        yield run.journal
        return
    terminal = await _bounded(run.runtime.detach())
    assert terminal.owner_settled and terminal.recorder_close_confirmed
    source = tmp_path / "t020-source.sqlite3"
    before = source.read_bytes()
    copied = tmp_path / "t020-003-oracle.sqlite3"
    shutil.copyfile(source, copied)
    oracle = await SqliteEvidenceJournal.open(
        copied, expected_session_id=run.journal.session_id
    )
    try:
        yield oracle
    finally:
        await oracle.close()
        assert source.read_bytes() == before, (
            "oracle/runtime changed the terminal source"
        )


@pytest_asyncio.fixture(params=["active", "terminal"])
async def t020_retained(
    request: pytest.FixtureRequest, tmp_path: Path, backend: BackendFixture
) -> AsyncIterator[tuple[JournalRun, SqliteEvidenceJournal, int, int]]:
    mode = str(request.param)
    async with _t020_source(tmp_path, backend, retained=4) as run:
        for sequence in range(1, 6):
            await run.emit(
                b"chunk-" + bytes([sequence]) + b"\0\xff",
                sequence=sequence,
                timestamp=sequence * 10,
            )
        async with _t020_oracle(run, tmp_path, mode) as oracle:
            # Explicit append history: active [0,6), terminal adds final record6.
            low, next_sequence = (2, 6) if mode == "active" else (3, 7)
            yield run, oracle, low, next_sequence


@pytest.mark.parametrize(
    "kind",
    [
        "complete",
        "partial_prefix",
        "expired",
        "not_found",
        "partial_suffix",
        "mixed",
        "empty_below_low",
        "empty_at_low",
        "empty_retained",
        "empty_at_next",
        "empty_beyond_next",
    ],
)
@pytest.mark.asyncio
async def test_t020_range_outcomes_empty_intervals_and_never_existent_suffix_match003(
    t020_retained: tuple[JournalRun, SqliteEvidenceJournal, int, int], kind: str
) -> None:
    run, oracle, low, next_sequence = t020_retained
    ranges = {
        "complete": (low, low + 2),
        "partial_prefix": (0, low + 1),
        "expired": (0, low),
        "not_found": (next_sequence, next_sequence + 2),
        "partial_suffix": (low, next_sequence + 2),
        "mixed": (0, next_sequence + 2),
        "empty_below_low": (0, 0),
        "empty_at_low": (low, low),
        "empty_retained": (low + 1, low + 1),
        "empty_at_next": (next_sequence, next_sequence),
        "empty_beyond_next": (next_sequence + 1, next_sequence + 1),
    }
    start, end = ranges[kind]
    reference = model.EvidenceRangeReference(run.journal.session_id, start, end)
    request = EvidenceRetrievalRequest(reference, 10, 16384)
    expected = await oracle.retrieve(request)
    before = run.runtime.status()
    actual = await _bounded(run.runtime.read_page(request))
    assert actual.page == expected and actual.run_id == before.run_id
    assert (
        actual.session_id == run.journal.session_id and run.runtime.status() == before
    )
    outcomes = {
        "partial_prefix": EvidencePageOutcome.PARTIAL,
        "expired": EvidencePageOutcome.EXPIRED,
        "not_found": EvidencePageOutcome.NOT_FOUND,
        "partial_suffix": EvidencePageOutcome.PARTIAL,
        "mixed": EvidencePageOutcome.PARTIAL,
        "empty_beyond_next": EvidencePageOutcome.NOT_FOUND,
    }
    assert actual.page.outcome is outcomes.get(kind, EvidencePageOutcome.COMPLETE)
    if kind in {"partial_prefix", "expired", "mixed"}:
        assert actual.page.expired_range == model.SequenceRange(0, low)
        assert actual.page.retention_marker is not None
        assert actual.page.retention_marker.expired_range == model.SequenceRange(0, low)
    else:
        assert (
            actual.page.expired_range is None and actual.page.retention_marker is None
        )
    if kind in {"not_found", "partial_suffix", "mixed"}:
        assert actual.page.never_existed_range == model.SequenceRange(
            next_sequence, next_sequence + 2
        )
    else:
        assert actual.page.never_existed_range is None
    if kind.startswith("empty") or kind in {"expired", "not_found"}:
        assert actual.page.records == () and actual.page.charged_bytes == 0
    assert not actual.page.truncated and actual.page.continuation is None
    assert actual.page.snapshot_end_exclusive == min(end, next_sequence)


@pytest.mark.parametrize("kind", ["expired", "retained", "absent", "max"])
@pytest.mark.asyncio
async def test_t020_stable_references_distinguish_expired_retained_absent_and_max(
    t020_retained: tuple[JournalRun, SqliteEvidenceJournal, int, int], kind: str
) -> None:
    run, oracle, low, next_sequence = t020_retained
    sequence = {
        "expired": 0,
        "retained": low + 1,
        "absent": next_sequence + 3,
        "max": model.SQLITE_INTEGER_MAX,
    }[kind]
    reference = model.EvidenceReference(run.journal.session_id, sequence)
    expected = await oracle.resolve_record(reference)
    page = (await _bounded(run.runtime.read_record(reference))).page
    assert page == expected
    if kind == "expired":
        assert page.outcome is EvidencePageOutcome.EXPIRED
        assert (
            page.expired_range == model.SequenceRange(0, 1)
            and page.retention_marker is not None
        )
    elif kind == "retained":
        assert page.outcome is EvidencePageOutcome.COMPLETE
        assert [record.sequence for record in page.records] == [low + 1]
    else:
        assert page.outcome is EvidencePageOutcome.NOT_FOUND and page.records == ()
        assert page.snapshot_end_exclusive == next_sequence
        assert page.never_existed_range == (
            None if kind == "max" else model.SequenceRange(sequence, sequence + 1)
        )


@pytest.mark.asyncio
async def test_t020_zero_record_shortage_and_changing_page_budgets_preserve_positions_and_charges(
    t020_retained: tuple[JournalRun, SqliteEvidenceJournal, int, int],
) -> None:
    run, oracle, low, next_sequence = t020_retained
    reference = model.EvidenceRangeReference(run.journal.session_id, low, next_sequence)
    shortage = EvidenceRetrievalRequest(reference, 1, 1)
    zero = (await _bounded(run.runtime.read_page(shortage))).page
    assert zero == await oracle.retrieve(shortage)
    assert zero.records == () and zero.charged_bytes == 0
    assert zero.outcome is EvidencePageOutcome.COMPLETE and zero.truncated
    assert zero.continuation is not None and zero.continuation.next_sequence == low
    retained = await oracle.resolve_record(
        model.EvidenceReference(run.journal.session_id, low)
    )
    charge = sqlite_evidence.encode_evidence_record(retained.records[0]).charged_bytes
    assert zero.next_record_required_bytes == charge
    repeated = EvidenceRetrievalRequest(reference, 2, 1, zero.continuation)
    still_zero = (await _bounded(run.runtime.read_page(repeated))).page
    assert still_zero == await oracle.retrieve(repeated)
    assert still_zero.continuation == zero.continuation
    assert still_zero.next_record_required_bytes == charge
    cursor: EvidenceCursor | None = still_zero.continuation
    for records, charged, sequences in (
        (2, charge, [low]),
        (1, 16384, [low + 1]),
        (10, 16384, [low + 2, low + 3]),
    ):
        request = EvidenceRetrievalRequest(reference, records, charged, cursor)
        page = (await _bounded(run.runtime.read_page(request))).page
        assert page == await oracle.retrieve(request)
        assert [record.sequence for record in page.records] == sequences
        assert page.snapshot_end_exclusive == next_sequence
        if len(sequences) == 1:
            assert page.outcome is EvidencePageOutcome.COMPLETE and page.truncated
            assert (
                page.continuation is not None
                and page.continuation.next_sequence == sequences[-1] + 1
            )
        else:
            assert page.continuation is None and not page.truncated
        cursor = page.continuation


@pytest.mark.parametrize("mode", ["active", "terminal"])
@pytest.mark.asyncio
async def test_t020_append_and_terminal_boundary_stay_outside_original_snapshot(
    tmp_path: Path, backend: BackendFixture, mode: str
) -> None:
    async with _t020_source(tmp_path, backend, retained=100) as run:
        await run.emit(b"first\0", sequence=1, timestamp=11)
        await run.emit(b"second\xff", sequence=2, timestamp=20)
        first_request = EvidenceRetrievalRequest(run.journal.session_id, 1, 16384)
        first = (await _bounded(run.runtime.read_page(first_request))).page
        assert first == await run.journal.retrieve(first_request)
        assert first.snapshot_end_exclusive == 3 and first.continuation is not None
        await run.emit(b"later outside snapshot", sequence=3, timestamp=30)
        async with _t020_oracle(run, tmp_path, mode) as oracle:
            request = EvidenceRetrievalRequest(
                run.journal.session_id, 10, 16384, first.continuation
            )
            page = (await _bounded(run.runtime.read_page(request))).page
            assert page == await oracle.retrieve(request)
            assert page.snapshot_end_exclusive == 3
            assert [record.sequence for record in page.records] == [1, 2]
            assert page.continuation is None and not page.truncated
            fresh_request = EvidenceRetrievalRequest(run.journal.session_id, 10, 16384)
            fresh = (await _bounded(run.runtime.read_page(fresh_request))).page
            assert fresh == await oracle.retrieve(fresh_request)
            assert [record.sequence for record in fresh.records] == list(
                range(4 if mode == "active" else 5)
            )


@pytest.mark.parametrize("mode", ["active", "terminal"])
@pytest.mark.asyncio
async def test_t020_eviction_crossing_continuation_reports_partial_or_fully_expired_snapshot(
    tmp_path: Path, backend: BackendFixture, mode: str
) -> None:
    async with _t020_source(tmp_path, backend, retained=3) as run:
        await run.emit(b"one\0", sequence=1, timestamp=11)
        await run.emit(b"two\xff", sequence=2, timestamp=20)
        first_request = EvidenceRetrievalRequest(run.journal.session_id, 1, 16384)
        first = (await _bounded(run.runtime.read_page(first_request))).page
        assert (
            first == await run.journal.retrieve(first_request)
            and first.continuation is not None
        )
        assert (
            first.continuation.next_sequence == 1 and first.snapshot_end_exclusive == 3
        )
        await run.emit(b"three", sequence=3, timestamp=30)
        await run.emit(b"four", sequence=4, timestamp=40)
        async with _t020_oracle(run, tmp_path, mode) as oracle:
            request = EvidenceRetrievalRequest(
                run.journal.session_id, 10, 16384, first.continuation
            )
            page = (await _bounded(run.runtime.read_page(request))).page
            assert page == await oracle.retrieve(request)
            low = 2 if mode == "active" else 3
            assert page.expired_range == model.SequenceRange(1, low)
            assert page.retention_marker is not None
            assert page.retention_marker.expired_range == model.SequenceRange(0, low)
            assert page.snapshot_end_exclusive == 3 and page.never_existed_range is None
            assert page.outcome is (
                EvidencePageOutcome.PARTIAL
                if mode == "active"
                else EvidencePageOutcome.EXPIRED
            )
            assert [record.sequence for record in page.records] == (
                [2] if mode == "active" else []
            )
            assert page.continuation is None and not page.truncated


@pytest.mark.parametrize("mode", ["active", "terminal"])
@pytest.mark.asyncio
async def test_t020_retention_marker_preserves_distinct_timestamp_domains_across_origin_reset(
    tmp_path: Path, backend: BackendFixture, mode: str
) -> None:
    async with _t020_source(tmp_path, backend, retained=2) as run:
        original = (
            run.fixture.connection.descriptor.backend_observation_timestamp_domain
        )
        await run.emit(b"old clock", sequence=1, timestamp=11)
        new = replace(
            original, domain_id="t020-new-domain", origin_id="t020-new-origin"
        )
        await run.fixture.connection.reset_timestamp_origin(new)
        boundary = await run.commit(2)
        assert isinstance(boundary, model.SegmentEndedEvidence)
        start = await run.commit(3)
        assert isinstance(start, model.SegmentStartedEvidence)
        await run.emit(b"new clock two", sequence=4, timestamp=2)
        await run.emit(b"new clock seven", sequence=5, timestamp=7)
        await run.emit(b"new clock eight", sequence=6, timestamp=8)
        async with _t020_oracle(run, tmp_path, mode) as oracle:
            request = EvidenceRetrievalRequest(run.journal.session_id, 10, 16384)
            page = (await _bounded(run.runtime.read_page(request))).page
            assert (
                page == await oracle.retrieve(request)
                and page.outcome is EvidencePageOutcome.PARTIAL
            )
            marker = page.retention_marker
            assert marker is not None
            assert marker.expired_range == model.SequenceRange(
                0, 5 if mode == "active" else 6
            )
            assert marker.first_discarded_timestamp == model.RetentionTimestampEndpoint(
                model.BackendObservationTimestamp(original.domain_id, 11), original
            )
            assert marker.last_discarded_timestamp == model.RetentionTimestampEndpoint(
                model.BackendObservationTimestamp(
                    new.domain_id, 2 if mode == "active" else 7
                ),
                new,
            )
            assert (
                marker.first_discarded_timestamp.timestamp.value
                > marker.last_discarded_timestamp.timestamp.value
            )
            assert (
                marker.first_discarded_timestamp.domain
                != marker.last_discarded_timestamp.domain
            )


@pytest.mark.parametrize("ceiling", ["records", "charged_bytes"])
@pytest.mark.asyncio
async def test_t020_active_and_terminal_policy_failures_match003_without_dirtying_read_cleanup(
    t020_retained: tuple[JournalRun, SqliteEvidenceJournal, int, int], ceiling: str
) -> None:
    run, oracle, low, next_sequence = t020_retained
    policy = oracle.policy
    request = EvidenceRetrievalRequest(
        run.journal.session_id,
        policy.max_retrieval_page_records + (ceiling == "records"),
        policy.max_retrieval_page_charged_bytes + (ceiling == "charged_bytes"),
    )
    before = run.runtime.status()
    with pytest.raises(JournalFailure) as expected:
        await oracle.retrieve(request)
    with pytest.raises(JournalFailure) as actual:
        await _bounded(run.runtime.read_page(request))
    assert (
        actual.value.operation is expected.value.operation is JournalOperation.RETRIEVE
    )
    assert actual.value.kind is expected.value.kind is JournalFailureKind.INVALID_INPUT
    assert cast("rt.ObservationRuntime", run.runtime).evidence_read_cleanup_confirmed
    assert run.runtime.status() == before
    legal = EvidenceRetrievalRequest(
        model.EvidenceRangeReference(run.journal.session_id, low, next_sequence),
        policy.max_retrieval_page_records,
        policy.max_retrieval_page_charged_bytes,
    )
    assert (await _bounded(run.runtime.read_page(legal))).page == await oracle.retrieve(
        legal
    )
