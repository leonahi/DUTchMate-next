"""012 T014 RED: real commit ordering and independent Interact settlement.

The provisional *internal* coordinator seam is start_interact(request, *, run_id,
expected_provenance, revalidate, charge_markers, submit_uart_write, pending_stop)
returning an operation with wait(). It is not a public send API. Access-value
placement is deliberately unconstrained among the existing application modules.
Only backend, clock and persistence ACK boundaries are controlled by this harness;
Acquisition, coordinator, matching and temporary v4 SQLite storage remain real.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from dutchmate_core import acquisition, evidence, interact, model, monitor
from dutchmate_core import runtime as rt
from dutchmate_core.adapters import sqlite_evidence as sqlite
from dutchmate_core.backend import (
    BackendFailureKind,
    BackendWriteResult,
    BackendWriteStatus,
)
from tests.contract.test_acquisition_write import WriteProbe
from tests.contract.test_monitor_recording import (
    AppendGates,
    ManualClock,
    _await,
    _turn,
)
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixtureFactory
from tests.integration.test_annotations import assert_single_rx_owner

POLICY = model.SessionPolicy(100, 262144, 16384, 256, 100, 131072)
KINDS = (
    "segment_started",
    "segment_ended",
    "rx_bytes",
    "observer_loss",
    "client_annotation",
    "operation_started",
    "operation_ended",
    "interact_started",
    "uart_tx_settled",
    "interact_ended",
)
_DRAFT_KINDS = dict(
    zip(
        (
            evidence.PendingSegmentStartedEvidence,
            evidence.PendingSegmentEndedEvidence,
            evidence.PendingRxBytesEvidence,
            evidence.PendingObserverLossEvidence,
            evidence.PendingClientAnnotationEvidence,
            evidence.PendingOperationStartedEvidence,
            evidence.PendingOperationEndedEvidence,
            evidence.PendingInteractStartedEvidence,
            evidence.PendingUartTxSettledEvidence,
            evidence.PendingInteractEndedEvidence,
        ),
        KINDS,
        strict=True,
    )
)


def required_method(owner: object, name: str) -> Any:
    method = getattr(owner, name, None)
    assert callable(method), f"T014 missing: {type(owner).__name__}.{name}"
    return method


def prepared_access(**kwargs: Any) -> Any:
    for module in (monitor, interact, rt):
        factory = getattr(module, "PreparedInteractAccess", None)
        if callable(factory):
            return factory(**kwargs)
    pytest.fail("T014 missing: PreparedInteractAccess", pytrace=False)


class SampleClock(ManualClock):
    """Expose actual samples without advancing time merely because code samples."""

    def __init__(self, trace: list[str]) -> None:
        super().__init__()
        self.trace = trace
        self.samples: list[int] = []

    def now_ns(self) -> int:
        self.samples.append(self.value)
        self.trace.append(f"clock:{self.value}")
        return self.value


class JournalProbe:
    """Real journal appends, with independent precommit and postcommit ACK gates."""

    def __init__(self, journal: sqlite.SqliteEvidenceJournal, trace: list[str]) -> None:
        self.journal = journal
        self.session_id, self.policy = journal.session_id, journal.policy
        self.trace = trace
        self.gates = {kind: AppendGates() for kind in KINDS}
        self.acks: dict[str, asyncio.Queue[model.EvidenceRecord]] = {
            kind: asyncio.Queue() for kind in KINDS
        }
        self.attempts: list[str] = []
        self.committed: list[model.EvidenceRecord] = []
        self.fail_before: set[str] = set()
        self.fail_ack: set[str] = set()
        self.after_ack: dict[str, Callable[[], None]] = {}
        self.inflight = 0
        self.closed = asyncio.Event()
        self.close_during_append = False

    async def append(
        self, draft: evidence.PendingEvidenceRecord
    ) -> model.EvidenceRecord:
        kind = _DRAFT_KINDS[type(draft)]
        self.attempts.append(kind)
        self.trace.append(f"{kind}.attempt")
        self.inflight += 1
        try:
            await self.gates[kind].commit.enter()
            if kind in self.fail_before:
                raise evidence.JournalFailure(
                    evidence.JournalOperation.APPEND,
                    evidence.JournalFailureKind.IO_FAILURE,
                )
            record = await self.journal.append(draft)
            self.committed.append(record)
            self.trace.append(f"{kind}.commit")
            await self.gates[kind].acknowledgement.enter()
            if kind in self.fail_ack:
                raise evidence.JournalFailure(
                    evidence.JournalOperation.APPEND,
                    evidence.JournalFailureKind.IO_FAILURE,
                )
            self.trace.append(f"{kind}.ack")
            self.acks[kind].put_nowait(record)
            if callback := self.after_ack.get(kind):
                callback()
            return record
        finally:
            self.inflight -= 1

    async def close(self) -> None:
        self.close_during_append |= self.inflight != 0
        await self.journal.close()
        self.trace.append("journal.closed")
        self.closed.set()

    def release(self) -> None:
        self.fail_before.clear()
        self.fail_ack.clear()
        for gates in self.gates.values():
            gates.commit.allow.set()
            gates.acknowledgement.allow.set()


class RecordingCase:
    def __init__(
        self,
        journal: sqlite.SqliteEvidenceJournal,
        factory: BackendFixtureFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self.trace: list[str] = []
        self.clock = SampleClock(self.trace)
        self.recorder = JournalProbe(journal, self.trace)
        self.journal = journal
        self.coordinator = monitor.MonitorRecordingCoordinator(
            recorder=self.recorder, clock=self.clock
        )
        self.fixture = factory()
        self.writer = WriteProbe(self.fixture)
        self.fixture.connection.descriptor = replace(
            self.fixture.connection.descriptor,
            connection_provenance=model.PersistedConnectionProvenance(
                model.ConnectionProvenanceSnapshot(
                    envelope_version=1,
                    backend_kind="fixture/interact",
                    backend_schema_version=1,
                    fields=(model.ProvenanceField("transport", "simulated"),),
                )
            ),
            capabilities=model.BackendCapabilities(
                frozenset(
                    {
                        *self.fixture.connection.descriptor.capabilities.values,
                        model.BackendCapability.UART_SEND,
                    }
                )
            ),
        )
        monkeypatch.setattr(
            self.fixture.connection, "write", self.writer.write, raising=False
        )
        monkeypatch.setattr(self.fixture.connection, "close", self.writer.close)
        self.acquisition = acquisition.Acquisition(self.coordinator)
        self.tasks: list[asyncio.Task[Any]] = []
        self.pending_stop: tuple[model.InteractOutcome, ...] = ()

    def request(self, **changes: Any) -> interact.InteractRequest:
        return replace(
            interact.InteractRequest(
                self.journal.session_id, b"\x00\xffSEND", (b"PASS", b"FAIL"), 1000, 1024
            ),
            **changes,
        )

    def spawn[T](self, work: Awaitable[T]) -> asyncio.Task[T]:
        async def run() -> T:
            return await work

        task = asyncio.create_task(run())
        self.tasks.append(task)
        return task

    def submit(self, payload: bytes) -> Awaitable[BackendWriteResult]:
        self.trace.append("write.register")
        return self.acquisition.submit_uart_write(payload)

    async def start(
        self, request: interact.InteractRequest | None = None, **kwargs: Any
    ) -> Any:
        method = required_method(self.coordinator, "start_interact")
        provenance = self.coordinator.current_provenance
        assert provenance is not None
        options = dict(
            run_id="recording-run",
            expected_provenance=provenance,
            revalidate=lambda: None,
            charge_markers=sqlite.charge_interact_markers,
            submit_uart_write=self.submit,
            pending_stop=lambda: self.pending_stop,
        )
        options.update(kwargs)
        return await method(self.request() if request is None else request, **options)

    async def rx(self, payload: bytes, timestamp: int = 123) -> model.RxBytesEvidence:
        await self.fixture.connection.emit_rx(payload, timestamp=timestamp)
        return cast(
            model.RxBytesEvidence, await _await(self.recorder.acks["rx_bytes"].get())
        )

    async def records(self) -> tuple[model.EvidenceRecord, ...]:
        page = await self.journal.retrieve(
            evidence.EvidenceRetrievalRequest(self.journal.session_id, 100, 131072)
        )
        assert not page.truncated
        return page.records

    async def finish(self) -> None:
        self.recorder.release()
        self.writer.allow.set()
        self.fixture.connection.close_gate.allow.set()
        self.clock.advance(model.SQLITE_INTEGER_MAX)
        await _await(self.acquisition.stop())
        await _await(self.acquisition.join_terminated())
        await _await(self.coordinator.close())
        await _await(asyncio.gather(*self.tasks, return_exceptions=True))
        assert not self.recorder.close_during_append
        assert self.writer.active == 0
        assert all(active == 0 for active in self.writer.active_at_close)


@asynccontextmanager
async def recording_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    *,
    policy: model.SessionPolicy = POLICY,
) -> AsyncIterator[RecordingCase]:
    journal = await sqlite.SqliteEvidenceJournal.create_v4(
        tmp_path / "recording.db", policy
    )
    case = RecordingCase(journal, factory, monkeypatch)
    try:
        await case.acquisition.start(case.fixture.backend)
        yield case
    finally:
        await case.finish()


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic-shape", "enhanced-shape"]
    ),
]


@pytest.mark.parametrize("gate", ["commit", "acknowledgement"])
async def test_t014_intent_ack_precedes_registration_and_queued_rx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    gate: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        required_method(c.coordinator, "start_interact")
        checkpoint = getattr(c.recorder.gates["interact_started"], gate)
        checkpoint.allow.clear()
        start = c.spawn(c.start())
        await _await(checkpoint.entered.wait())
        await c.fixture.connection.emit_rx(b"PASS", timestamp=1)
        await _turn()
        assert c.writer.calls == [] and "write.register" not in c.trace
        assert c.recorder.acks["rx_bytes"].empty()
        checkpoint.allow.set()
        operation = await _await(start)
        await _await(c.writer.entered.wait())
        rx = await _await(c.recorder.acks["rx_bytes"].get())
        assert c.trace.index("interact_started.ack") < c.trace.index("write.register")
        assert c.trace.index("write.register") < c.trace.index("rx_bytes.ack")
        waiter = c.spawn(operation.wait())
        await _turn()
        assert not waiter.done()  # Match alone cannot finish a pending write.
        c.writer.allow.set()
        report = await _await(waiter)
        assert report.outcome is model.InteractOutcome.MATCHED
        assert report.observation.window == model.SequenceRange(2, rx.sequence + 1)
        assert c.writer.calls == [b"\x00\xffSEND"]
        assert_single_rx_owner(c.fixture)


@pytest.mark.parametrize("ambiguous", [False, True])
async def test_t014_failed_intent_never_submits_or_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    ambiguous: bool,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        (c.recorder.fail_ack if ambiguous else c.recorder.fail_before).add(
            "interact_started"
        )
        with pytest.raises(evidence.JournalFailure) as failure:
            await c.start()
        assert failure.value.kind is evidence.JournalFailureKind.IO_FAILURE
        assert c.writer.calls == [] and "write.register" not in c.trace
        assert c.recorder.attempts.count("interact_started") == 1
        assert "uart_tx_settled" not in c.recorder.attempts
        records = await c.records()
        assert len(records) == (2 if ambiguous else 1)


@pytest.mark.parametrize(
    "result,outcome",
    [
        (BackendWriteResult(BackendWriteStatus.ACKNOWLEDGED, 6, None), "matched"),
        (BackendWriteResult(BackendWriteStatus.PARTIAL, 0, None), "partial_write"),
        (BackendWriteResult(BackendWriteStatus.PARTIAL, 3, None), "partial_write"),
        (BackendWriteResult(BackendWriteStatus.TIMEOUT, None, None), "write_timeout"),
        (
            BackendWriteResult(BackendWriteStatus.DISCONNECTED, None, None),
            "disconnected",
        ),
        (
            BackendWriteResult(
                BackendWriteStatus.FAILURE, None, BackendFailureKind.IO_FAILURE
            ),
            "transport_failure",
        ),
    ],
)
async def test_t014_early_rx_fact_and_write_outcome_are_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    result: BackendWriteResult,
    outcome: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        c.writer.result = result
        operation = await c.start()
        await _await(c.writer.entered.wait())
        first = await c.rx(b"noisePA", 1)
        last = await c.rx(b"SS\x00\xfftrailing", 2)
        c.clock.advance(2_000_000_100)
        c.writer.allow.set()
        report = await _await(operation.wait())
        assert report.outcome.value == outcome
        assert report.observation.outcome is model.InteractObservationOutcome.MATCHED
        assert report.observation.match == model.InteractMatch(
            0,
            model.MonitorMatchStart(first.sequence, 5),
            model.MonitorMatchEnd(last.sequence, 2),
        )
        assert report.observation.examined_rx_bytes == 9
        assert report.observation.clock.decided_at_ns == 100
        assert report.tx.status == result.status
        assert report.tx.accepted_prefix_bytes == result.accepted_prefix_bytes
        assert report.tx.acknowledgement_scope == "backend_acceptance"
        assert report.tx.settled_at_ns == 2_000_000_100
        records = await c.records()
        assert [r.payload for r in records if isinstance(r, model.RxBytesEvidence)] == [
            b"noisePA",
            b"SS\x00\xfftrailing",
        ]


@pytest.mark.parametrize("failed", ["uart_tx_settled", "interact_ended", "both"])
async def test_t014_audit_ack_failures_preserve_actual_tx_and_independent_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    failed: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        c.recorder.fail_ack.update(
            ("uart_tx_settled", "interact_ended") if failed == "both" else (failed,)
        )
        operation = await c.start()
        await c.rx(b"PASS")
        c.writer.allow.set()
        report = await _await(operation.wait())
        missing_tx, missing_end = (
            failed != "interact_ended",
            failed != "uart_tx_settled",
        )
        assert (report.tx_settled_record is None) == missing_tx
        assert (report.ended_record is None) == missing_end
        assert (
            report.durability
            == {
                "uart_tx_settled": "tx_unconfirmed",
                "interact_ended": "end_unconfirmed",
                "both": "both_unconfirmed",
            }[failed]
        )
        assert report.tx.status is BackendWriteStatus.ACKNOWLEDGED
        assert (
            report.tx.accepted_prefix_bytes == 6 and report.outcome.value == "matched"
        )
        assert [f.record_kind for f in report.audit_failures] == [
            kind
            for kind in ("uart_tx_settled", "interact_ended")
            if failed in (kind, "both")
        ]
        assert all(
            f.source == "journal" and f.code == "io_failure"
            for f in report.audit_failures
        )
        records = await c.records()
        end = records[-1]
        assert isinstance(end, model.InteractEndedEvidence)
        assert (end.tx_settled_sequence is None) == missing_tx
        assert end.tx.accepted_prefix_bytes == 6
        assert c.recorder.attempts.count("uart_tx_settled") == 1
        assert c.recorder.attempts.count("interact_ended") == 1


async def test_t014_tx_audit_can_precede_observation_and_end_waits_for_both(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        operation = await c.start()
        c.writer.allow.set()
        await _await(c.recorder.acks["uart_tx_settled"].get())
        assert "interact_ended" not in c.recorder.attempts
        c.clock.advance(1_000_000_100)
        report = await _await(operation.wait())
        assert report.outcome.value == report.observation.outcome.value == "timeout"
        assert report.tx.status is BackendWriteStatus.ACKNOWLEDGED
        assert report.observation.window == model.SequenceRange(2, 3)
        assert report.observation.examined_rx_bytes == 0


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize(
    "result,outcome",
    [
        (BackendWriteResult(BackendWriteStatus.PARTIAL, 1, None), "partial_write"),
        (BackendWriteResult(BackendWriteStatus.TIMEOUT, None, None), "write_timeout"),
        (
            BackendWriteResult(BackendWriteStatus.DISCONNECTED, None, None),
            "disconnected",
        ),
        (
            BackendWriteResult(
                BackendWriteStatus.FAILURE, None, BackendFailureKind.IO_FAILURE
            ),
            "transport_failure",
        ),
    ],
)
async def test_t014_nonfull_tx_freezes_only_undecided_observation_with_deadline_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    late: bool,
    result: BackendWriteResult,
    outcome: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        c.writer.result = result
        operation = await c.start()
        await _await(c.writer.entered.wait())
        c.clock.advance(1_000_000_100 if late else 101)
        c.writer.allow.set()
        report = await _await(operation.wait())
        assert report.outcome.value == outcome
        assert report.observation.outcome.value == ("timeout" if late else "tx_failed")
        assert (
            report.observation.match is None
            and report.observation.examined_rx_bytes == 0
        )
        assert report.tx.status == result.status
        assert report.tx.accepted_prefix_bytes == result.accepted_prefix_bytes
        assert report.durability == "complete"
        assert c.clock.waiters == {}  # Deadline owner was cancelled/joined at decision.


@pytest.mark.parametrize(
    "bad",
    [
        None,
        True,
        6,
        {"status": "acknowledged"},
        BackendWriteResult(BackendWriteStatus.ACKNOWLEDGED, 5, None),
        BackendWriteResult(BackendWriteStatus.PARTIAL, 6, None),
    ],
)
async def test_t014_malformed_backend_return_is_audited_normalized_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    bad: object,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:

        async def malformed(payload: bytes) -> BackendWriteResult:
            c.writer.calls.append(payload)
            c.writer.entered.set()
            await c.writer.allow.wait()
            return cast(BackendWriteResult, bad)

        monkeypatch.setattr(c.fixture.connection, "write", malformed)
        operation = await c.start()
        await c.rx(b"PASS")
        c.writer.allow.set()
        report = await _await(operation.wait())
        assert report.outcome.value == "transport_failure"
        assert report.observation.outcome.value == "matched"
        assert report.tx.submitted and report.tx.status is BackendWriteStatus.FAILURE
        assert report.tx.accepted_prefix_bytes is None
        assert report.tx.failure_code is BackendFailureKind.INTERNAL_CONTRACT_FAILURE
        assert report.durability == "complete"
        assert isinstance((await c.records())[-1], model.InteractEndedEvidence)


@pytest.mark.parametrize("fault", ["clock", "report"])
async def test_t014_application_invariant_fault_joins_before_raising_without_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    fault: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        operation = await c.start()
        await _await(c.writer.entered.wait())
        if fault == "clock":
            c.clock.value = -1
        else:

            def invalid_report(self: interact.InteractReport) -> None:
                raise ValueError("T014 invalid application report")

            monkeypatch.setattr(
                interact.InteractReport, "__post_init__", invalid_report
            )
        await c.rx(b"PASS")
        waiter = c.spawn(operation.wait())
        await _turn()
        assert not waiter.done() and c.writer.active == 1
        c.writer.allow.set()
        with pytest.raises((RuntimeError, ValueError, TypeError)):
            await _await(waiter)
        assert c.writer.finished.is_set() and c.writer.cancellation_signals == 0
        if fault == "clock":
            assert "interact_ended" not in c.recorder.attempts
            c.clock.value = 100


async def test_t014_monitor_samples_are_unchanged_without_interact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        provenance = c.coordinator.current_provenance
        assert provenance is not None
        operation = await c.coordinator.start(
            monitor.MonitorRequest(c.journal.session_id, b"PASS", 1000, 1024),
            run_id="monitor-only",
            expected_provenance=provenance,
            revalidate=lambda: None,
            charge_markers=sqlite.charge_monitor_markers,
        )
        assert c.clock.samples == [100, 100]  # preflight, post-ACK start
        await c.rx(b"PASS")
        await operation.wait()
        assert c.clock.samples == [100, 100, 100]  # one RX, no end sample
        assert c.writer.calls == []


@pytest.mark.parametrize("interact_decided", [False, True])
async def test_t014_monitor_direct_markers_reuse_start_and_conditionally_sample_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    interact_decided: bool,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        interaction = await c.start()
        provenance = c.coordinator.current_provenance
        assert provenance is not None
        before = len(c.clock.samples)
        operation = await c.coordinator.start(
            monitor.MonitorRequest(c.journal.session_id, b"M", 1000, 1024),
            run_id="monitor-shared",
            expected_provenance=provenance,
            revalidate=lambda: None,
            charge_markers=sqlite.charge_monitor_markers,
        )
        assert len(c.clock.samples) - before == 2  # no third sample to notify Interact
        c.clock.advance(101)
        before = len(c.clock.samples)
        await c.rx(b"MPASS" if interact_decided else b"M")
        await operation.wait()
        assert len(c.clock.samples) - before == (1 if interact_decided else 2)
        # Shared ordinary RX sample; Monitor end samples only for undecided Interact.
        if not interact_decided:
            await c.rx(b"PASS", 124)
        c.writer.allow.set()
        report = await _await(interaction.wait())
        records = await c.records()
        marker = next(
            r for r in records if isinstance(r, model.OperationStartedEvidence)
        )
        assert report.observation.window.start_inclusive <= marker.sequence
        assert report.observation.outcome.value == "matched"


async def test_t014_interact_start_reuses_sample_and_new_audits_are_non_rx_to_monitor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        provenance = c.coordinator.current_provenance
        assert provenance is not None
        mon = await c.coordinator.start(
            monitor.MonitorRequest(c.journal.session_id, b"AB", 1000, 1024),
            run_id="monitor-first",
            expected_provenance=provenance,
            revalidate=lambda: None,
            charge_markers=sqlite.charge_monitor_markers,
        )
        first = await c.rx(b"A", 1)
        interaction = await c.start(c.request(timeout_ms=1))
        start_ack = c.trace.index("interact_started.ack")
        registration = c.trace.index("write.register")
        assert c.trace[start_ack + 1 : registration] == ["clock:100"]
        before = len(c.clock.samples)
        await c.coordinator.append_client_annotation("cli", "AB is only an assertion")
        assert (
            len(c.clock.samples) - before == 2
        )  # receipt plus one shared post-ACK sample
        c.writer.allow.set()
        await _await(c.recorder.acks["uart_tx_settled"].get())
        c.clock.advance(1_000_100)
        report = await _await(interaction.wait())
        assert report.observation.outcome.value == "timeout"
        assert not mon.decided
        last = await c.rx(b"B", 2)
        mon_report = await mon.wait()
        assert mon_report.outcome.value == "matched"
        assert (
            mon_report.examined_rx_bytes == 2 and mon_report.observer_loss_records == 0
        )
        assert mon_report.match == model.MonitorMatch(
            model.MonitorMatchStart(first.sequence, 0),
            model.MonitorMatchEnd(last.sequence, 1),
        )
        assert report.observation.examined_rx_bytes == 0


@pytest.mark.parametrize(
    "kind",
    [
        "client_annotation",
        "operation_started",
        "operation_ended",
        "uart_tx_settled",
        "interact_ended",
    ],
)
async def test_t014_every_direct_append_path_holds_order_until_ack_but_not_during_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    kind: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        operation = await c.start()
        gate = c.recorder.gates[kind].acknowledgement
        gate.allow.clear()
        if kind == "client_annotation":
            c.spawn(c.coordinator.append_client_annotation("cli", "non-RX"))
        elif kind in {"operation_started", "operation_ended"}:
            provenance = c.coordinator.current_provenance
            assert provenance is not None
            start = c.spawn(
                c.coordinator.start(
                    monitor.MonitorRequest(c.journal.session_id, b"M", 1000, 1024),
                    run_id="ordered-monitor",
                    expected_provenance=provenance,
                    revalidate=lambda: None,
                    charge_markers=sqlite.charge_monitor_markers,
                )
            )
            if kind == "operation_ended":
                await _await(start)
                await c.rx(b"M", 1)
        else:
            if kind == "interact_ended":
                await c.rx(b"PASS", 1)
            c.writer.allow.set()
        await _await(gate.entered.wait())
        marker = c.recorder.committed[-1]
        queued = c.spawn(c.rx(b"PASSM", 2))
        await _turn()
        assert not queued.done() and c.recorder.attempts[-1] == kind
        gate.allow.set()
        rx = await _await(queued)
        assert rx.sequence == marker.sequence + 1
        assert c.trace.index(f"{kind}.ack") < c.trace.index(
            "rx_bytes.attempt", c.trace.index(f"{kind}.ack")
        )
        c.writer.allow.set()
        assert (await _await(operation.wait())).outcome.value == "matched"


@pytest.mark.parametrize(
    "stop", [model.InteractOutcome.DETACHED, model.InteractOutcome.CANCELLED]
)
async def test_t014_post_intent_stop_recheck_owns_not_submitted_audits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    stop: model.InteractOutcome,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:

        def stopped() -> None:
            c.pending_stop = (stop,)

        c.recorder.after_ack["interact_started"] = stopped
        operation = await c.start()
        report = await _await(operation.wait())
        assert c.writer.calls == [] and "write.register" not in c.trace
        assert not report.tx.submitted and report.tx.status == "not_submitted"
        assert report.tx.accepted_prefix_bytes is report.tx.failure_code is None
        assert report.outcome is stop and report.observation.outcome.value == stop.value
        assert report.durability == "complete"
        assert c.recorder.attempts == [
            "segment_started",
            "interact_started",
            "uart_tx_settled",
            "interact_ended",
        ]


async def test_t014_revalidates_under_gate_before_committing_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        required_method(c.coordinator, "start_interact")
        gate = c.recorder.gates["client_annotation"].acknowledgement
        gate.allow.clear()
        annotation = c.spawn(
            c.coordinator.append_client_annotation("core", "blocks append gate")
        )
        await _await(gate.entered.wait())
        allowed = True

        def revalidate() -> None:
            if not allowed:
                raise RuntimeError("T014 captured run is no longer admissible")

        start = c.spawn(c.start(revalidate=revalidate))
        await _turn()
        allowed = False
        gate.allow.set()
        await _await(annotation)
        with pytest.raises(RuntimeError):
            await _await(start)
        assert c.writer.calls == [] and "interact_started" not in c.recorder.attempts
