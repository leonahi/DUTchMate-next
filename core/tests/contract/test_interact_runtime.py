"""012 T014 RED: runtime admission, frozen observations and joined owners.

Only real infrastructure boundaries are gated. _seal_interacts() is a provisional
internal incarnation seal, following the existing Monitor seal convention; it is
not an operation-cancellation API. HTTP500 mapping belongs to T016: here invalid
application facts must raise after resource joining, rather than return a report.
"""

import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from dutchmate_core import annotation, interact, model, monitor, profile
from dutchmate_core import runtime as rt
from dutchmate_core.adapters import sqlite_evidence as sqlite
from dutchmate_core.adapters.terminal_evidence import (
    capture_terminal_target,
    open_terminal_reader,
)
from dutchmate_core.evidence_access import PreparedEvidenceAccess
from tests.contract.test_interact_recording import (
    POLICY,
    RecordingCase,
    prepared_access,
    required_method,
)
from tests.contract.test_monitor_recording import _await, _turn
from tests.contract.test_observation_runtime import _profile
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixtureFactory


def selected_profile(*, enabled: bool = True) -> profile.ResolvedInteractionProfile:
    old = _profile()
    return profile.ResolvedInteractionProfile(
        profile.InteractionProfileFormatVersion(2),
        old.dut,
        old.backend,
        old.uart,
        old.open_lines,
        profile.InteractionPolicy(uart_tx_enabled=enabled),
        POLICY,
    )


async def until(predicate: Any) -> None:
    async def poll() -> None:
        while not predicate():
            await _turn()

    await _await(poll())


class RuntimeCase(RecordingCase):
    def __init__(
        self,
        journal: sqlite.SqliteEvidenceJournal,
        factory: BackendFixtureFactory,
        monkeypatch: pytest.MonkeyPatch,
        *,
        path: Path,
        enabled: bool = True,
        access: bool = True,
        owner: rt.ObservationRuntime | None = None,
    ) -> None:
        super().__init__(journal, factory, monkeypatch)
        self.path = path
        self.owner = rt.ObservationRuntime() if owner is None else owner
        self.profile = selected_profile(enabled=enabled)
        self.access_present = access
        self.active: rt.RuntimeStatus | None = None
        self.charge_override: tuple[int, int, int] | None = None
        self.charge_calls: list[tuple[Any, Any, Any]] = []
        self.terminal_opened = asyncio.Event()

    def charge(self, start: Any, txs: Any, ends: Any) -> tuple[int, int, int]:
        self.charge_calls.append((start, txs, ends))
        return self.charge_override or sqlite.charge_interact_markers(start, txs, ends)

    async def prepare(
        self, selected: profile.ResolvedInteractionProfile
    ) -> rt.PreparedObservationRun:
        assert selected == self.profile
        target = capture_terminal_target(
            self.path,
            session_id=self.journal.session_id,
            policy=self.journal.policy,
            expected_schema_version=4,
        )
        assert target is not None

        async def terminal() -> Any:
            assert self.recorder.closed.is_set(), (
                "terminal read preceded confirmed writer close"
            )
            self.terminal_opened.set()
            return await open_terminal_reader(target)

        args: dict[str, Any] = {}
        if self.access_present:
            args["interact_access"] = prepared_access(
                session_id=self.journal.session_id,
                policy=self.journal.policy,
                coordinator=self.coordinator,
                clock=self.clock,
                charge_markers=self.charge,
            )
        return rt.PreparedObservationRun(
            self.coordinator,
            self.fixture.backend,
            evidence_access=PreparedEvidenceAccess(
                self.journal.session_id, self.journal.policy, self.journal, terminal
            ),
            monitor_access=monitor.PreparedMonitorAccess(
                self.journal.session_id,
                self.journal.policy,
                self.coordinator,
                self.clock,
                sqlite.charge_monitor_markers,
            ),
            annotation_access=annotation.PreparedAnnotationAccess(
                self.journal.session_id,
                self.journal.policy,
                self.coordinator,
                self.clock,
                sqlite.charge_client_annotation,
            ),
            follow_access=rt.PreparedFollowAccess(
                self.journal.session_id,
                self.journal.policy,
                self.coordinator,
                self.journal,
            ),
            **args,
        )

    async def attach(self) -> None:
        self.active = await _await(self.owner.attach(self.profile, self.prepare))
        assert self.active.state is rt.RuntimeState.ACTIVE
        await _await(self.recorder.acks["segment_started"].get())

    def entry(self) -> Any:
        return required_method(self.owner, "interact")

    async def begin(
        self, request: interact.InteractRequest | None = None
    ) -> asyncio.Task[Any]:
        entry = self.entry()
        task = self.spawn(entry(self.request() if request is None else request))
        await _await(self.recorder.acks["interact_started"].get())
        await _turn()
        return task

    async def rejected(
        self, kind: str, request: interact.InteractRequest | None = None
    ) -> None:
        before = list(self.recorder.attempts)
        entry = self.entry()
        with pytest.raises(RuntimeError) as rejected:
            await _await(entry(self.request() if request is None else request))
        assert getattr(rejected.value, "kind", None) == kind
        assert self.recorder.attempts == before and self.writer.calls == []

    async def finish(self) -> None:
        self.recorder.release()
        self.writer.allow.set()
        self.fixture.connection.close_gate.allow.set()
        self.clock.advance(model.SQLITE_INTEGER_MAX)
        await _await(self.owner.detach())
        await _await(asyncio.gather(*self.tasks, return_exceptions=True))
        await _await(self.coordinator.close())
        assert not self.recorder.close_during_append
        assert self.writer.active == 0 and all(
            n == 0 for n in self.writer.active_at_close
        )


@asynccontextmanager
async def runtime_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    *,
    attach: bool = True,
    **kwargs: Any,
) -> AsyncIterator[RuntimeCase]:
    journal = await sqlite.SqliteEvidenceJournal.create_v4(
        tmp_path / "runtime.db", POLICY
    )
    c = RuntimeCase(
        journal, factory, monkeypatch, path=tmp_path / "runtime.db", **kwargs
    )
    try:
        c.entry()  # Explicit missing-feature assertion before any gate wait.
        if attach:
            await c.attach()
        yield c
    finally:
        await c.finish()


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic-shape", "enhanced-shape"]
    ),
]


@pytest.mark.parametrize("bad", [None, {}, "session", object()])
async def test_t014_request_type_guard_precedes_association(
    factory: BackendFixtureFactory,
    bad: object,
) -> None:
    del factory
    owner = rt.ObservationRuntime()
    entry = required_method(owner, "interact")
    before = owner.status()
    with pytest.raises(rt.RuntimeRejectedError) as rejected:
        await entry(bad)
    assert rejected.value.kind is rt.RuntimeRejectedKind.INVALID_REQUEST
    assert owner.status() == before


@pytest.mark.parametrize("context", ["other-loop", "other-thread", "no-loop"])
async def test_t014_context_guard_precedes_bad_request(
    factory: BackendFixtureFactory,
    context: str,
) -> None:
    del factory
    owner = rt.ObservationRuntime()
    entry = required_method(owner, "interact")
    with ThreadPoolExecutor(max_workers=1) as pool:
        if context != "other-thread":

            async def construct() -> rt.ObservationRuntime:
                return rt.ObservationRuntime()

            owner = pool.submit(lambda: asyncio.run(construct())).result(timeout=3)
            entry = required_method(owner, "interact")

        def invoke() -> object:
            if context == "no-loop":
                coroutine = entry(None)
                try:
                    return coroutine.send(None)
                finally:
                    coroutine.close()
            return asyncio.run(entry(None))

        with pytest.raises(rt.RuntimeRejectedError) as rejected:
            pool.submit(invoke).result(timeout=3)
        assert rejected.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT


@pytest.mark.parametrize(
    "scenario,want",
    [
        ("unknown", "no_associated_session"),
        ("wrong-session", "session_not_associated"),
        ("terminal", "not_active"),
        ("no-access", "interact_unavailable"),
        ("denied", "policy_denied"),
        ("no-capability", "capability_unavailable"),
        ("no-writer", "capability_unavailable"),
        ("sealed", "interact_unavailable"),
    ],
)
async def test_t014_exact_admission_rejects_before_intent_or_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    scenario: str,
    want: str,
) -> None:
    async with runtime_case(
        tmp_path,
        monkeypatch,
        factory,
        attach=False,
        enabled=scenario != "denied",
        access=scenario != "no-access",
    ) as c:
        if scenario == "no-capability":
            descriptor = c.fixture.connection.descriptor
            c.fixture.connection.descriptor = replace(
                descriptor,
                capabilities=model.BackendCapabilities(
                    descriptor.capabilities.values - {model.BackendCapability.UART_SEND}
                ),
            )
        if scenario == "no-writer":
            monkeypatch.setattr(c.fixture.connection, "write", None)
        if scenario != "unknown":
            await c.attach()
        request = c.request()
        if scenario == "wrong-session":
            request = replace(request, session_id=model.SessionId("wrong-session"))
        if scenario == "terminal":
            await c.owner.detach()
        if scenario == "sealed":
            assert required_method(c.owner, "_seal_interacts")() is None
        await c.rejected(want, request)


@pytest.mark.parametrize(
    "scenario,want",
    [
        ("session-before-access", "session_not_associated"),
        ("access-before-permission", "interact_unavailable"),
        ("permission-before-capability", "policy_denied"),
    ],
)
async def test_t014_admission_precedence_is_not_masked_by_later_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    scenario: str,
    want: str,
) -> None:
    async with runtime_case(
        tmp_path,
        monkeypatch,
        factory,
        attach=False,
        enabled=False,
        access=scenario == "permission-before-capability",
    ) as c:
        descriptor = c.fixture.connection.descriptor
        c.fixture.connection.descriptor = replace(
            descriptor,
            capabilities=model.BackendCapabilities(
                descriptor.capabilities.values - {model.BackendCapability.UART_SEND}
            ),
        )
        await c.attach()
        request = c.request()
        if scenario == "session-before-access":
            request = replace(request, session_id=model.SessionId("other"))
        await c.rejected(want, request)


@pytest.mark.parametrize("marker", [0, 1, 2], ids=["intent", "tx", "end"])
async def test_t014_each_charge_maximum_must_fit_before_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    marker: int,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        # Callback output is the external pure-codec contract; no SQL/head reserve.
        # Valid SessionPolicy requires record <= retention and retrieval ceilings;
        # exceed one independent marker maximum, preserving the other two.
        charges = [1, 1, 1]
        charges[marker] = 16385
        c.charge_override = (charges[0], charges[1], charges[2])
        await c.rejected("evidence_policy_incompatible")


async def test_t014_real_codec_preflight_gets_request_and_valid_conservative_variants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        task = await c.begin(
            c.request(payload=bytes(range(256)), conditions=(b"\x00", b"\xff"))
        )
        assert c.charge_calls
        for draft, txs, ends in c.charge_calls:
            assert draft.payload == bytes(range(256)) and draft.conditions == (
                b"\x00",
                b"\xff",
            )
            assert draft.profile_version == 2 and draft.uart_tx_enabled is True
            assert draft.write_timeout_ms == 1000
            assert txs and ends
            sqlite.charge_interact_markers(
                draft, txs, ends
            )  # All variants must be legal.
            assert {d.tx.submitted for d in txs} == {False, True}
            assert {str(d.tx.status) for d in txs} >= {
                "acknowledged",
                "partial",
                "timeout",
                "disconnected",
                "failure",
                "not_submitted",
            }
            assert any(d.tx_settled_sequence is None for d in ends)
        await c.rx(b"\xff")
        c.writer.allow.set()
        assert (await _await(task)).outcome.value == "matched"


@pytest.mark.parametrize("phase", ["intent", "write", "tx-audit", "end-audit"])
async def test_t014_busy_slot_covers_intent_write_and_all_audit_settlement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    phase: str,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        kind = {
            "intent": "interact_started",
            "tx-audit": "uart_tx_settled",
            "end-audit": "interact_ended",
        }.get(phase)
        gate = None if kind is None else c.recorder.gates[kind].acknowledgement
        if gate is not None:
            gate.allow.clear()
        first = c.spawn(c.entry()(c.request()))
        if phase == "intent":
            assert gate is not None
            await _await(gate.entered.wait())
        else:
            await _await(c.writer.entered.wait())
            await c.rx(b"PASS")
            if phase != "write":
                c.writer.allow.set()
                assert gate is not None
                await _await(gate.entered.wait())
        before = list(c.recorder.attempts)
        with pytest.raises(RuntimeError) as rejected:
            await _await(c.entry()(c.request()))
        assert getattr(rejected.value, "kind", None) == "busy"
        assert c.recorder.attempts == before
        assert not first.done()
        if gate is not None:
            gate.allow.set()
        if phase == "intent":
            await _await(c.writer.entered.wait())
            await c.rx(b"PASS")
        c.writer.allow.set()
        assert (await _await(first)).outcome.value == "matched"
        while not c.recorder.acks["interact_started"].empty():
            c.recorder.acks["interact_started"].get_nowait()
        second = await c.begin()
        await c.rx(b"PASS", 124)
        assert (await _await(second)).outcome.value == "matched"
        assert len(c.writer.calls) == 2


async def test_t014_preflight_rejection_precedes_busy_and_does_not_disturb_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        first = await c.begin()
        await _await(c.writer.entered.wait())
        before = list(c.recorder.attempts)
        c.charge_override = (16385, 1, 1)
        with pytest.raises(RuntimeError) as rejected:
            await c.entry()(c.request())
        assert getattr(rejected.value, "kind", None) == "evidence_policy_incompatible"
        assert c.recorder.attempts == before and len(c.writer.calls) == 1
        c.charge_override = None
        await c.rx(b"PASS")
        c.writer.allow.set()
        assert (await _await(first)).outcome.value == "matched"


@pytest.mark.parametrize("frozen", ["matched", "timeout", "byte_limit"])
@pytest.mark.parametrize(
    "boundary,want",
    [
        ("disconnect", "disconnected"),
        ("origin", "timestamp_origin_reset"),
        ("fallback", "recording_failure"),
        ("transport-fallback", "transport_failure"),
    ],
)
async def test_t014_frozen_observation_keeps_latching_later_external_termination_before_ack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    frozen: str,
    boundary: str,
    want: str,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        request = c.request(max_rx_bytes=4, conditions=(b"PASS",))
        task = await c.begin(request)
        await _await(c.writer.entered.wait())
        if frozen == "timeout":
            c.clock.advance(1_000_000_100)
            await _turn()
            await _turn()
        else:
            await c.rx(b"PASSextra" if frozen == "matched" else b"xxxxextra", 1)
        await c.owner.annotate(
            annotation.AnnotationRequest(
                c.journal.session_id, "later client assertion", "cli"
            )
        )
        assert not task.done() and c.writer.active == 1
        if boundary == "disconnect":
            await c.fixture.connection.disconnect()
            await _await(c.recorder.acks["segment_ended"].get())
        elif boundary == "origin":
            domain = (
                c.fixture.connection.descriptor.backend_observation_timestamp_domain
            )
            await c.fixture.connection.reset_timestamp_origin(
                replace(
                    domain,
                    domain_id=domain.domain_id + "-next",
                    origin_id=domain.origin_id + "-next",
                )
            )
            await _await(c.recorder.acks["segment_ended"].get())
            await _await(c.recorder.acks["segment_started"].get())
            await until(
                lambda: (
                    c.coordinator.current_provenance is not None
                    and c.coordinator.current_provenance.backend_observation_timestamp_domain.domain_id.endswith(
                        "-next"
                    )
                )
            )
        else:
            if boundary == "fallback":
                c.recorder.fail_before.add("rx_bytes")
                await c.fixture.connection.emit_rx(b"not committed", timestamp=2)
            else:
                c.recorder.fail_before.add("segment_ended")
                await c.fixture.connection.end_stream_unexpectedly()

            def stopping() -> bool:
                snapshot = c.owner.status().acquisition
                return snapshot is not None and snapshot.state.value == "stopping"

            await until(stopping)
            assert not any(
                isinstance(r, model.SegmentEndedEvidence) for r in c.recorder.committed
            )
        assert not task.done()
        c.writer.allow.set()
        report = await _await(task)
        assert report.outcome.value == want
        observation = report.observation
        assert observation.outcome.value == frozen
        assert observation.window == model.SequenceRange(
            2, 2 if frozen == "timeout" else 3
        )
        assert observation.examined_rx_bytes == (0 if frozen == "timeout" else 4)
        assert observation.clock.decided_at_ns == (
            1_000_000_100 if frozen == "timeout" else 100
        )
        assert (observation.match is not None) == (frozen == "matched")
        assert (
            report.tx.status.value == "acknowledged" and report.durability == "complete"
        )


@pytest.mark.parametrize("stop", ["detach", "service"])
async def test_t014_teardown_joins_write_before_close_and_audits_before_journal_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    stop: str,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        c.recorder.gates["uart_tx_settled"].acknowledgement.allow.clear()
        task = await c.begin()
        await _await(c.writer.entered.wait())
        await c.rx(b"PASS")
        if stop == "service":
            assert required_method(c.owner, "_seal_interacts")() is None
        detach = c.spawn(c.owner.detach())
        await _turn()
        assert not detach.done() and c.writer.close_calls == 0
        assert not c.recorder.closed.is_set()
        with pytest.raises(rt.RuntimeRejectedError) as blocked:
            await c.owner.attach(c.profile, c.prepare)
        assert blocked.value.kind is rt.RuntimeRejectedKind.BUSY
        c.writer.allow.set()
        await _await(c.writer.close_entered.wait())
        await _await(c.recorder.gates["uart_tx_settled"].acknowledgement.entered.wait())
        assert not c.recorder.closed.is_set() and not detach.done()
        assert c.writer.active_at_close == [0]
        c.recorder.gates["uart_tx_settled"].acknowledgement.allow.set()
        report = await _await(task)
        terminal = await _await(detach)
        assert report.outcome.value == (
            "detached" if stop == "detach" else "service_stopping"
        )
        assert report.observation.outcome.value == "matched"
        assert terminal.owner_settled and terminal.recorder_close_confirmed
        assert c.trace.index("interact_ended.ack") < c.trace.index("journal.closed")


@pytest.mark.parametrize("fault", ["clock", "report"])
async def test_t014_runtime_application_fault_is_joined_exception_not_normalized_tx_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    fault: str,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        task = await c.begin()
        await _await(c.writer.entered.wait())
        if fault == "clock":
            c.clock.value = -1
        else:

            def invalid(self: interact.InteractReport) -> None:
                raise ValueError("T014 invalid application report")

            monkeypatch.setattr(interact.InteractReport, "__post_init__", invalid)
        await c.rx(b"PASS")
        await _turn()
        assert not task.done() and c.writer.active == 1
        c.writer.allow.set()
        with pytest.raises((ValueError, RuntimeError, TypeError)):
            await _await(task)
        assert c.writer.finished.is_set() and c.writer.cancellation_signals == 0
        if fault == "clock":
            assert "interact_ended" not in c.recorder.attempts
            c.clock.value = 100


@pytest.mark.parametrize(
    "submitted", [False, True], ids=["before-intent-ack", "after-write-registration"]
)
async def test_t014_cancelled_runtime_waiter_joins_owned_settlement_without_detaching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    submitted: bool,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        gate = c.recorder.gates["interact_started"].acknowledgement
        if not submitted:
            gate.allow.clear()
        task = c.spawn(c.entry()(c.request()))
        if submitted:
            await _await(c.writer.entered.wait())
            await c.rx(b"PASS")
        else:
            await _await(gate.entered.wait())
        task.cancel()
        await _turn()
        assert not task.done()
        assert c.writer.close_calls == 0 and not c.recorder.closed.is_set()
        with pytest.raises(RuntimeError) as busy:
            await c.entry()(c.request())
        assert getattr(busy.value, "kind", None) == "busy"
        gate.allow.set()
        c.writer.allow.set()
        with pytest.raises(asyncio.CancelledError):
            await _await(task)
        ends = [
            r for r in await c.records() if isinstance(r, model.InteractEndedEvidence)
        ]
        assert len(ends) == 1
        end = ends[0]
        assert end.outcome is model.InteractOutcome.CANCELLED
        assert end.tx.submitted is submitted
        assert str(end.tx.status) == ("acknowledged" if submitted else "not_submitted")
        assert end.observation.outcome.value == (
            "matched" if submitted else "cancelled"
        )
        assert c.writer.calls == ([b"\x00\xffSEND"] if submitted else [])
        assert c.writer.cancellation_signals == 0
        assert c.owner.status().state is rt.RuntimeState.ACTIVE
