"""T026: real authenticated read ownership, cancellation and shutdown contracts.

Gates pause external read progress or entry into Core, never implement admission,
association, cleanup policy or shutdown. All resources/credentials are test-owned.
"""

import asyncio
import gc
import importlib
import json
import weakref
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from dutchmate_core.evidence import JournalFailure, JournalFailureKind, JournalOperation
from dutchmate_core.evidence_access import EvidenceSourceOpenFailure, RunEvidencePage
from dutchmate_core.runtime import ObservationRuntime, RuntimeState, RuntimeStopIntent

from dutchmate_service.bootstrap import (
    BootstrapFailure,
    PrivateBootstrap,
    ServiceConfig,
)
from test_evidence_http import _t014_core_helpers
from test_service_http import (
    AppLifespan,
    _headers,
    _scope,
    _t009_module,
    _t009_runtime_spy,
)
from test_service_runtime import Call, Client, CoreCalls, finish_delivery, flush

_RECORD = "/v1/evidence/record"
_PAGE = "/v1/evidence/page"
_DETACH = "/v1/observation/detach"


class _WeakReport(RunEvidencePage):
    """Field-identical report that lets the test observe completed-value release."""


class ReadCalls:
    """Weak observations over real application reads; no registry or policy copy."""

    def __init__(self) -> None:
        self.calls: list[Call] = []
        self.values: list[weakref.ReferenceType[Any]] = []
        self.entered: asyncio.Queue[Call] = asyncio.Queue()
        self.hold = True
        self.fail = False

    def install(self, patch: pytest.MonkeyPatch) -> None:
        for name in ("read_record", "read_page"):
            original = getattr(ObservationRuntime, name)

            async def read(
                runtime: ObservationRuntime,
                value: Any,
                *,
                method: Any = original,
                action: str = name,
            ) -> RunEvidencePage:
                task = asyncio.current_task()
                assert task is not None
                call = Call(action, weakref.ref(task))
                self.calls.append(call)
                self.entered.put_nowait(call)
                try:
                    if self.hold:
                        pending = asyncio.get_running_loop().create_future()
                        call.gate = weakref.ref(pending)
                        await pending
                    if self.fail:
                        error = JournalFailure(
                            JournalOperation.RETRIEVE,
                            JournalFailureKind.BUSY,
                            "private-T026-read-detail",
                        )
                        self.values.append(weakref.ref(error))
                        raise error
                    raw = await method(runtime, value)
                    report = _WeakReport(raw.run_id, raw.session_id, raw.page)
                    self.values.append(weakref.ref(report))
                    return report
                finally:
                    call.finished.set()

            patch.setattr(ObservationRuntime, name, read)

    def release(self) -> None:
        self.hold = False
        for call in self.calls:
            call.release()


@dataclass
class ReadService:
    app: Any
    runtime: ObservationRuntime
    config: ServiceConfig
    token: bytes
    context: Any
    lifespan: AppLifespan
    case: Any
    terminal: Any
    core: Any
    deliveries: list[asyncio.Task[Any]]

    def body(self, path: str, *, session: Any = None) -> bytes:
        identity = self.case.session_id if session is None else session
        value = {"session_id": identity.value, "sequence": 0}
        if path == _PAGE:
            value = {
                "session_id": identity.value,
                "start_inclusive": None,
                "end_exclusive": None,
                "max_records": 10,
                "max_charged_bytes": 16384,
                "cursor": None,
            }
        return json.dumps(value, separators=(",", ":")).encode()

    def submit(self, path: str, client: Client) -> asyncio.Task[None]:
        task = asyncio.create_task(
            self.app(
                _scope(
                    self.config,
                    _headers(self.config, self.token)
                    + [(b"content-type", b"application/json")],
                    path=path,
                    method="POST",
                ),
                client.receive,
                client.send,
            )
        )
        self.deliveries.append(task)
        return task

    async def request(self, path: str, *, session: Any = None) -> Client:
        client = Client(
            body=b"" if path == _DETACH else self.body(path, session=session)
        )
        task = self.submit(path, client)
        await self.core._await(task)
        return client


@asynccontextmanager
async def _service(
    tmp_path: Path,
    home: Path,
    patch: pytest.MonkeyPatch,
    backend_index: int,
) -> AsyncIterator[ReadService]:
    _t014_core_helpers(patch)
    core = importlib.import_module("tests.contract.test_evidence_access")
    created, _ = _t009_runtime_spy(_t009_module(), patch)
    config = ServiceConfig(8765)
    owner = PrivateBootstrap.acquire(config)
    service: ReadService | None = None
    lifespan: AppLifespan | None = None
    try:
        owner.mark_unconfirmed()
        owner.publish_credential()
        assert owner.credential is not None
        context = _t009_module()._LaunchContext(config, owner)
        app = _t009_module().create_app(config, _launch_context=context)
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        path = tmp_path / "ownership.sqlite3"
        journal = await core.SqliteEvidenceJournal.create(
            path, core._profile().session_policy
        )
        case = core.LiveCase(
            journal, core.BACKEND_FIXTURE_FACTORIES[backend_index](), created[0]
        )
        terminal = core._T017TerminalSource(case, path)
        service = ReadService(
            app,
            created[0],
            config,
            owner.credential.encode(),
            context,
            lifespan,
            case,
            terminal,
            core,
            [],
        )
        await core._await(case.attach(override=terminal.access(case)))
        yield service
    finally:
        if service is not None:
            service.terminal.open_gate.allow.set()
            service.terminal.read_gate.allow.set()
            service.terminal.close_gate.allow.set()
            for reader in service.terminal.readers:
                reader.close_gate.allow.set()
            await service.case.finish()
            for task in service.deliveries:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*service.deliveries, return_exceptions=True)
            await service.terminal.finish()
        if lifespan is not None:
            await lifespan.finish()
        owner.invalidate_credential()
        # No harness writes a positive service marker on production's behalf.
        owner.release()
        assert (
            json.loads(
                (home / ".local/state/dutchmate/service/owner.json").read_bytes()
            )["cleanup_confirmed"]
            is False
        )


def _error(client: Client, status: int, source: str, code: str) -> None:
    assert client.status == status, client.payload
    assert json.loads(client.payload) == {"error": {"source": source, "code": code}}
    assert client.headers[b"cache-control"] == b"no-store"
    assert b"private-T026" not in client.payload


async def _lost(task: asyncio.Task[Any], client: Client, loss: str) -> None:
    if loss == "cancel":
        task.cancel()
    else:
        client.disconnected.set()
    await finish_delivery(task)
    assert task.cancelled() and client.messages == []


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.asyncio
async def test_t026_eight_registered_reads_are_separate_from_eight_mutations_without_queue(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
    path: str,
) -> None:
    # A shared registry, early slot release or queued ninth request breaks this.
    async with _service(tmp_path, account_home, monkeypatch, backend_index) as s:
        with monkeypatch.context() as patch:
            reads, mutations = ReadCalls(), CoreCalls(hold_detach=True)
            reads.install(patch)
            mutations.install(patch)
            try:
                for _ in range(8):
                    s.submit(path, Client(body=s.body(path)))
                    await s.core._await(reads.entered.get())
                for _ in range(8):
                    s.submit(_DETACH, Client())
                await flush()
                assert len(mutations.calls) == 8
                _error(await s.request(path), 503, "service", "operation_capacity")
                _error(await s.request(_DETACH), 503, "service", "operation_capacity")
                assert len(reads.calls) == len(mutations.calls) == 8
                reads.calls[0].release()
                await s.core._await(reads.calls[0].finished.wait())
                await flush()
                ninth = s.submit(path, Client(body=s.body(path)))
                await s.core._await(reads.entered.get())
                assert len(reads.calls) == 9 and not ninth.done()
                _error(await s.request(path), 503, "service", "operation_capacity")
                assert len(reads.calls) == 9  # Denied calls never replay after release.
                assert s.runtime.status().state is RuntimeState.ACTIVE
            finally:
                reads.release()
                mutations.hold_detach = False
                mutations.release()
                await asyncio.gather(*s.deliveries, return_exceptions=True)


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.parametrize("loss", ["cancel", "disconnect", "pending-cancel"])
@pytest.mark.asyncio
async def test_t026_loss_before_registration_submits_no_read_or_capture_stop(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
    path: str,
    loss: str,
) -> None:
    async with _service(tmp_path, account_home, monkeypatch, backend_index) as s:
        with monkeypatch.context() as patch:
            probe = ReadCalls()
            probe.install(patch)
            before = s.runtime.status()
            client = Client(body=s.body(path), before_body=loss)
            task = s.submit(path, client)
            try:
                await s.core._await(client.body_entered.wait())
                if loss == "cancel":
                    task.cancel()
                await finish_delivery(task)
                assert probe.calls == [] and s.case.reader.calls == []
                assert s.runtime.status() == before
                assert s.case.backend.connection.consumer_calls == 1
            finally:
                probe.release()
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.parametrize("fail", [False, True], ids=["report", "failure"])
@pytest.mark.asyncio
async def test_t026_lost_registered_reads_remain_strongly_owned_then_release_all_history(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
    path: str,
    fail: bool,
) -> None:
    # Weak gates avoid the probe accidentally rooting the owned operation task.
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    unhandled: list[Any] = []
    loop.set_exception_handler(lambda owner, context: unhandled.append(context))
    try:
        async with _service(tmp_path, account_home, monkeypatch, backend_index) as s:
            with monkeypatch.context() as patch:
                probe = ReadCalls()
                probe.fail = fail
                probe.install(patch)
                try:
                    for _ in range(10):
                        probe.hold = True
                        client = Client(body=s.body(path))
                        task = s.submit(path, client)
                        call = await s.core._await(probe.entered.get())
                        assert call.task() is not task
                        await _lost(task, client, "cancel")
                        s.deliveries.remove(task)
                        del task
                        await flush()
                        gc.collect()
                        assert call.task() is not None, (
                            "service abandoned a registered read"
                        )
                        call.release()
                        await s.core._await(call.finished.wait())
                        await flush()
                        gc.collect()
                        assert all(c.task() is None for c in probe.calls), (
                            "read task history retained"
                        )
                        assert all(v() is None for v in probe.values), (
                            "report/failure history retained"
                        )
                        assert unhandled == []
                    assert len(probe.calls) == 10 and s.terminal.open_calls == 0
                    assert s.runtime.status().stop_intent is RuntimeStopIntent.NONE
                finally:
                    probe.release()
    finally:
        loop.set_exception_handler(previous)


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.parametrize("stage", ["live", "open", "read", "close"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.asyncio
async def test_t026_lost_waiter_never_cancels_pinned_live_or_terminal_resources(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
    path: str,
    stage: str,
    loss: str,
) -> None:
    async with _service(tmp_path, account_home, monkeypatch, backend_index) as s:
        if stage == "live":
            gate = s.case.reader.gate
        else:
            await s.core._await(s.runtime.detach())
            gate = getattr(s.terminal, stage + "_gate")
        gate.allow.clear()
        before = s.runtime.status()
        client = Client(body=s.body(path))
        task = s.submit(path, client)
        try:
            await s.core._await(gate.entered.wait())
            await _lost(task, client, loss)
            assert s.runtime.status() == before
            if stage == "live":
                assert s.case.reader.cancelled == 0 and s.case.recorder.close_calls == 0
                _error(
                    await s.request(_RECORD, session=s.core.model.SessionId("foreign")),
                    409,
                    "evidence",
                    "session_not_associated",
                )
            else:
                assert s.terminal.closed == 0
            gate.allow.set()
            await flush()
            if stage == "live":
                await s.core._await(s.case.reader.finished.get())
            else:
                async with asyncio.timeout(3):
                    while s.terminal.closed != 1:
                        await flush()
            assert s.runtime.evidence_read_cleanup_confirmed
            assert (await s.request(path)).status == 200
            assert s.runtime.status() == before
            assert len(s.case.reader.calls) == (2 if stage == "live" else 0)
            assert s.terminal.open_calls == (0 if stage == "live" else 2)
        finally:
            gate.allow.set()


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.asyncio
async def test_t026_registered_before_core_is_not_bound_when_a_new_attach_wins(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
    path: str,
) -> None:
    async with _service(tmp_path, account_home, monkeypatch, backend_index) as s:
        old = s.runtime.status()
        await s.core._await(s.runtime.detach())
        with monkeypatch.context() as patch:
            probe = ReadCalls()
            probe.install(patch)
            client = Client(body=s.body(path))
            task = s.submit(path, client)
            await s.core._await(probe.entered.get())
            journal = await s.core.SqliteEvidenceJournal.create(
                tmp_path / "replacement.sqlite3", s.core._profile().session_policy
            )
            new = s.core.LiveCase(
                journal, s.core.BACKEND_FIXTURE_FACTORIES[backend_index](), s.runtime
            )
            new.preparation.allow.clear()
            attach = new.attach()
            try:
                await s.core._await(new.preparation.entered.wait())
                assert s.runtime.status().run_id != old.run_id
                probe.release()
                await s.core._await(task)
                _error(client, 404, "evidence", "no_associated_session")
                assert s.terminal.open_calls == 0
                new.preparation.allow.set()
                await s.core._await(attach)
                _error(await s.request(path), 409, "evidence", "session_not_associated")
                assert (await s.request(path, session=new.session_id)).status == 200
            finally:
                probe.release()
                await new.finish()


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.parametrize("stage", ["registered", "live", "open", "read", "close"])
@pytest.mark.asyncio
async def test_t026_shutdown_seals_both_registries_and_joins_reads_before_final_detach(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
    path: str,
    stage: str,
) -> None:
    async with _service(tmp_path, account_home, monkeypatch, backend_index) as s:
        if stage != "live":
            await s.core._await(s.runtime.detach())
        with monkeypatch.context() as patch:
            probe = ReadCalls()
            probe.hold = stage == "registered"
            probe.install(patch)
            gate = (
                None
                if stage == "registered"
                else s.case.reader.gate
                if stage == "live"
                else getattr(s.terminal, stage + "_gate")
            )
            if gate is not None:
                gate.allow.clear()
            mutations = CoreCalls(hold_detach=True)
            mutations.install(patch)
            try:
                client = Client(body=s.body(path))
                task = s.submit(path, client)
                await s.core._await(probe.entered.get())
                if gate is not None:
                    await s.core._await(gate.entered.wait())
                await _lost(task, client, "cancel")
                mutation = s.submit(_DETACH, Client())
                await flush()
                assert len(mutations.calls) == 1
                assert s.lifespan.task is not None
                await s.lifespan.incoming.put({"type": "lifespan.shutdown"})
                await flush()
                assert s.context.stopping
                _error(await s.request(path), 503, "service", "stopping")
                _error(await s.request(_DETACH), 503, "service", "stopping")
                assert not s.lifespan.task.done() and s.lifespan.outgoing.empty()
                assert (
                    len(mutations.calls) == 1
                    and not s.context.final_evidence_read_cleanup_confirmed
                )
                # Repeated lifespan waiter loss cannot force abandonment.
                s.lifespan.task.cancel()
                await flush()
                s.lifespan.task.cancel()
                await flush()
                assert not s.lifespan.task.done()
                mutations.hold_detach = False
                mutations.release()
                await flush()
                assert len(mutations.calls) == 1, (
                    "final detach ran before read settlement"
                )
                probe.release()
                if gate is not None:
                    gate.allow.set()
                await s.core._await(mutation)
                await s.core._await(probe.calls[0].finished.wait())
                assert (await s.core._await(s.lifespan.outgoing.get()))[
                    "type"
                ] == "lifespan.shutdown.complete"
                await s.core._await(s.lifespan.task)
                assert len(mutations.calls) == 2
                assert s.context.final_evidence_read_cleanup_confirmed
                assert s.context.final_status.owner_settled
                assert s.context.final_status.recorder_close_confirmed
                assert s.terminal.closed == (0 if stage == "live" else 1)
                assert s.case.recorder.close_calls == 1
                assert (
                    account_home / ".local/state/dutchmate/service/credential"
                ).exists()
                with pytest.raises(BootstrapFailure):
                    PrivateBootstrap.acquire(ServiceConfig(8766))
            finally:
                probe.release()
                if gate is not None:
                    gate.allow.set()
                mutations.hold_detach = False
                mutations.release()


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.parametrize("fault", ["close", "partial", "unexpected"])
@pytest.mark.asyncio
async def test_t026_uncertain_cleanup_seals_before_service_slot_reuse_and_keeps_shutdown_dirty(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
    path: str,
    fault: str,
) -> None:
    async with _service(tmp_path, account_home, monkeypatch, backend_index) as s:
        await s.core._await(s.runtime.detach())
        before = s.runtime.status()
        assert s.runtime.evidence_read_cleanup_confirmed
        primary = JournalFailure(JournalOperation.OPEN, JournalFailureKind.BUSY)
        if fault == "close":
            s.terminal.close_error = JournalFailure(
                JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE
            )
        elif fault == "partial":
            s.terminal.open_error = EvidenceSourceOpenFailure(primary, False)
        else:
            s.terminal.open_error = RuntimeError("private-T026-opener-detail")
        client = await s.request(path)
        if fault == "close":
            _error(client, 500, "journal", "io_failure")
        elif fault == "partial":
            _error(client, 503, "journal", "busy")
        else:
            _error(client, 500, "service", "internal_failure")
        assert not s.runtime.evidence_read_cleanup_confirmed
        await flush()  # The failed service/Core slots have now been released.
        for _ in range(10):
            _error(await s.request(path), 503, "evidence", "read_unavailable")
        assert s.terminal.open_calls == 1 and s.runtime.status() == before
        assert before.attach_admissible and before.recorder_close_confirmed
        assert (await s.request(_DETACH)).status == 200
        await s.lifespan.finish()
        assert not s.context.final_evidence_read_cleanup_confirmed
        assert s.context.final_status.owner_settled
        assert s.context.final_status.physical_release_confirmed
        assert s.context.final_status.recorder_close_confirmed


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.asyncio
async def test_t026_registration_is_atomic_before_first_child_runs_or_waiter_is_cancelled(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
    path: str,
) -> None:
    # Missing synchronous registration abandons the child when cancellation is
    # queued before its first Core call.
    async with _service(tmp_path, account_home, monkeypatch, backend_index) as s:
        with monkeypatch.context() as patch:
            probe = ReadCalls()
            probe.install(patch)
            client = Client(body=s.body(path))
            delivery = s.submit(path, client)
            loop = asyncio.get_running_loop()
            previous = loop.get_task_factory()
            cancelled = asyncio.Event()

            def factory(
                owner_loop: asyncio.AbstractEventLoop,
                coro: Coroutine[Any, Any, Any],
                **kwargs: Any,
            ) -> asyncio.Future[Any]:
                if asyncio.current_task() is delivery and not cancelled.is_set():

                    def cancel_waiter() -> None:
                        cancelled.set()
                        delivery.cancel()

                    owner_loop.call_soon(cancel_waiter)
                return (
                    asyncio.Task(coro, loop=owner_loop, **kwargs)
                    if previous is None
                    else previous(owner_loop, coro, **kwargs)
                )

            loop.set_task_factory(factory)
            try:
                call = await s.core._await(probe.entered.get())
                await finish_delivery(delivery)
                loop.set_task_factory(previous)
                assert cancelled.is_set() and delivery.cancelled()
                owned = call.task()
                assert (
                    owned is not None
                    and owned is not delivery
                    and not owned.cancelling()
                )
                del owned
                gc.collect()
                assert call.task() is not None
                assert s.case.reader.calls == [] and s.case.recorder.close_calls == 0
                call.release()
                await s.core._await(call.finished.wait())
                await flush()
                assert len(s.case.reader.calls) == 1
                assert s.runtime.status().state is RuntimeState.ACTIVE
                assert s.runtime.status().stop_intent is RuntimeStopIntent.NONE
            finally:
                loop.set_task_factory(previous)
                probe.release()
