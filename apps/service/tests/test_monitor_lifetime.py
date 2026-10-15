"""009 T027: authenticated service ownership, shutdown and honest cleanup.

Only client delivery and external/Core-entry progress are gated. Real app
registries, security, Core policy, v2 recording and launcher cleanup are exercised.
All credentials, journals and backends are isolated test-owned resources.
"""

import asyncio
import gc
import importlib
import json
import logging
import weakref
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from dutchmate_core import evidence, model, monitor
from dutchmate_core.adapters.sqlite_evidence import SqliteEvidenceJournal
from dutchmate_core.evidence_access import RunEvidencePage
from dutchmate_core.runtime import ObservationRuntime, RuntimeStatus

from dutchmate_service.bootstrap import (
    BootstrapFailure,
    BootstrapFailureKind,
    PrivateBootstrap,
    ServiceConfig,
)
from test_evidence_http import (
    ReadBoundary,
    Service,
    _error,
    _json,
    _t014_core_helpers,
)
from test_monitor_http import _BODY, _ROUTE, _SESSION, _report
from test_service_http import (
    _CONFIGS,
    AppLifespan,
    Exchange,
    _t009_module,
    _t009_runtime_spy,
    _t011_body,
    _T011Composition,
    _T011Service,
)
from test_service_http import t011_composition as t011_composition
from test_service_runtime import (
    Call,
    Client,
    _t021_held,
    _t021_server,
    _T021Launch,
    flush,
)

_READ = "/v1/evidence/record"
_DETACH = "/v1/observation/detach"
_ATTACH = "/v1/observation/attach"
_PRIVATE = "private-T027-condition-path-SQL-cause-sentinel"


async def _await[T](work: Awaitable[T]) -> T:
    # Test watchdog only; it never bounds or cancels the service's owned work.
    async with asyncio.timeout(3):
        return await work


@dataclass
class LifetimeService(Service):
    runtime: ObservationRuntime
    lifespan: AppLifespan
    deliveries: list[asyncio.Task[None]] = field(default_factory=list)

    def submit(self, path: str, client: Client) -> asyncio.Task[None]:
        async def deliver() -> None:
            await self.app(self.scope(path), client.receive, client.send)

        task = asyncio.create_task(deliver())
        self.deliveries.append(task)
        return task


@asynccontextmanager
async def _app(
    home: Path, patch: pytest.MonkeyPatch, config: ServiceConfig
) -> AsyncIterator[LifetimeService]:
    module = _t009_module()
    created, _ = _t009_runtime_spy(module, patch)
    owner = PrivateBootstrap.acquire(config)
    lifespan: AppLifespan | None = None
    service: LifetimeService | None = None
    try:
        owner.mark_unconfirmed()
        owner.publish_credential()
        assert owner.credential is not None
        context = module._LaunchContext(config, owner)
        app = module.create_app(config, _launch_context=context)
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        service = LifetimeService(
            app,
            config,
            owner.credential.encode(),
            ReadBoundary(),
            context,
            created[0],
            lifespan,
        )
        yield service
    finally:
        if service is not None:
            service.launch_context.request_stop()
            for delivery in service.deliveries:
                if not delivery.done():
                    delivery.cancel()
            await asyncio.gather(*service.deliveries, return_exceptions=True)
        if lifespan is not None:
            await lifespan.finish()
        owner.invalidate_credential()
        owner.release()
        # App-only tests cannot certify launcher cleanup by writing a true marker.
        assert json.loads(
            (home / ".local/state/dutchmate/service/owner.json").read_bytes()
        ) == {
            "version": 1,
            "cleanup_confirmed": False,
        }


class PendingCalls:
    """Weak gates at the external/Core-call boundary, with no capacity policy."""

    def __init__(self) -> None:
        self.calls: list[Call] = []
        self.entered: asyncio.Queue[Call] = asyncio.Queue()
        self.open_actions: set[str] = set()

    async def wait(self, action: str) -> None:
        task = asyncio.current_task()
        assert task is not None
        call = Call(action, weakref.ref(task))
        self.calls.append(call)
        self.entered.put_nowait(call)
        try:
            if action not in self.open_actions:
                pending: asyncio.Future[None] = (
                    asyncio.get_running_loop().create_future()
                )
                call.gate = weakref.ref(pending)
                await pending
        finally:
            call.finished.set()

    def release(self, action: str | None = None) -> None:
        self.open_actions.update(
            {"read", "mutation", "monitor"} if action is None else {action}
        )
        for call in self.calls:
            if action is None or call.action == action:
                call.release()


async def _lost(task: asyncio.Task[None], client: Client, loss: str) -> None:
    if loss == "cancel":
        task.cancel()
    else:
        client.disconnected.set()
    with pytest.raises(asyncio.CancelledError):
        await _await(task)
    assert client.messages == []


def _monitor_body(session: model.SessionId) -> dict[str, object]:
    return {
        "session_id": session.value,
        "condition_base64": "UEFTUw==",
        "timeout_ms": 1000,
        "max_rx_bytes": 1024,
    }


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("released", ["read", "mutation", "monitor"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.asyncio
async def test_t027_all_seventeen_jobs_are_independent_owned_and_reusable(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    device: bool,
    released: str,
    loss: str,
) -> None:
    # Catches merged pools, queues, weak ownership and releasing the wrong pool.
    async with _app(account_home, monkeypatch, config) as service:
        calls = PendingCalls()

        async def read(value: model.EvidenceReference) -> RunEvidencePage:
            del value
            await calls.wait("read")
            return service.boundary.result

        async def detach() -> RuntimeStatus:
            await calls.wait("mutation")
            return service.runtime.status()

        async def observe(request: monitor.MonitorRequest) -> monitor.MonitorReport:
            del request
            await calls.wait("monitor")
            return _report(device=device)

        monkeypatch.setattr(service.runtime, "read_record", read)
        monkeypatch.setattr(service.runtime, "detach", detach)
        monkeypatch.setattr(service.runtime, "monitor", observe)
        specs = {
            "read": (_READ, {"session_id": _SESSION.value, "sequence": 0}, 8),
            "mutation": (_DETACH, {}, 8),
            "monitor": (_ROUTE, _BODY, 1),
        }
        try:
            for action, (path, body, count) in specs.items():
                for _ in range(count):
                    client = Client(body=b"" if action == "mutation" else _json(body))
                    task = service.submit(path, client)
                    call = await _await(calls.entered.get())
                    assert call.action == action
                    await _lost(task, client, loss)
            gc.collect()
            for call in calls.calls:
                owner = call.task()
                assert owner is not None and not owner.done()
            assert len(calls.calls) == 17
            for action, (path, body, _) in specs.items():
                _error(
                    await service.request(
                        path, body, raw=b"" if action == "mutation" else None
                    ),
                    503,
                    "service",
                    "operation_capacity",
                )
            assert len(calls.calls) == 17
            calls.release(released)
            await flush()
            for action, (path, body, _) in specs.items():
                response = await service.request(
                    path, body, raw=b"" if action == "mutation" else None
                )
                if action == released:
                    assert response.status == 200
                else:
                    _error(response, 503, "service", "operation_capacity")
            assert len(calls.calls) == 18
        finally:
            calls.release()


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("loss", ["none", "cancel", "disconnect"])
@pytest.mark.asyncio
async def test_t027_registered_monitor_cannot_enter_core_after_immediate_seal(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    backend_index: int,
    loss: str,
) -> None:
    # Catches registration-to-Core races that install a marker after the seal.
    _t014_core_helpers(monkeypatch)
    core = importlib.import_module("tests.integration.test_monitor")
    async with _app(account_home, monkeypatch, config) as service:
        async with core._live(
            tmp_path,
            monkeypatch,
            core.BACKEND_FIXTURE_FACTORIES[backend_index],
            runtime_support=True,
            runtime=service.runtime,
        ) as case:
            original = service.runtime.monitor
            calls = PendingCalls()

            async def observe(request: monitor.MonitorRequest) -> monitor.MonitorReport:
                await calls.wait("monitor")
                return await original(request)

            monkeypatch.setattr(service.runtime, "monitor", observe)
            client = Client(body=_json(_monitor_body(case.journal.session_id)))
            task = service.submit(_ROUTE, client)
            try:
                call = await _await(calls.entered.get())
                if loss != "none":
                    await _lost(task, client, loss)
                before = service.runtime.status()
                service.launch_context.request_stop()
                service.launch_context.request_stop()
                assert (
                    service.launch_context.stopping
                    and service.runtime.status() == before
                )
                with pytest.raises(monitor.MonitorRejected) as sealed:
                    await original(
                        monitor.MonitorRequest(
                            case.journal.session_id, b"PASS", 1000, 1024
                        )
                    )
                assert sealed.value.kind == "monitor_unavailable"
                _error(
                    await service.request(
                        _ROUTE, {}, exchange=Exchange(forbid_receive=True)
                    ),
                    503,
                    "service",
                    "stopping",
                )
                calls.release()
                await _await(call.finished.wait())
                if loss == "none":
                    await _await(task)
                    _error(client, 503, "monitor", "monitor_unavailable")
                await flush()
                records = await case.page()
                assert len(records) == 1 and isinstance(
                    records[0], model.SegmentStartedEvidence
                )
                assert not case.terminal_opened.is_set()
            finally:
                calls.release()


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.parametrize("fault", ["journal", "unexpected"])
@pytest.mark.asyncio
async def test_t027_late_private_failures_after_client_loss_are_consumed_and_slot_reused(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    device: bool,
    loss: str,
    fault: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Catches abandoned task errors, leaked diagnostics and retained service slots.
    caplog.set_level(logging.DEBUG)
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    unhandled: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
    try:
        async with _app(account_home, monkeypatch, config) as service:
            calls = PendingCalls()
            fail = True

            async def observe(request: monitor.MonitorRequest) -> monitor.MonitorReport:
                del request
                await calls.wait("monitor")
                if fail:
                    if fault == "unexpected":
                        raise RuntimeError(_PRIVATE)
                    error = evidence.JournalFailure(
                        evidence.JournalOperation.APPEND,
                        evidence.JournalFailureKind.BUSY,
                        _PRIVATE,
                    )
                    error.add_note(_PRIVATE)
                    raise error from OSError(_PRIVATE)
                return _report(device=device)

            monkeypatch.setattr(service.runtime, "monitor", observe)
            client = Client(body=_json(_BODY))
            task = service.submit(_ROUTE, client)
            try:
                call = await _await(calls.entered.get())
                await _lost(task, client, loss)
                _error(
                    await service.request(_ROUTE, _BODY),
                    503,
                    "service",
                    "operation_capacity",
                )
                calls.release()
                await _await(call.finished.wait())
                await flush()
                fail = False
                assert (await service.request(_ROUTE, _BODY)).status == 200
                gc.collect()
                await flush()
                assert not unhandled
                assert (
                    _PRIVATE not in caplog.text
                    and service.token.decode() not in caplog.text
                )
                assert client.messages == []
            finally:
                calls.release()
    finally:
        loop.set_exception_handler(previous)


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.parametrize(
    "phase", ["start-commit", "start-ack", "active", "end-commit", "end-ack"]
)
@pytest.mark.asyncio
async def test_t027_shutdown_keeps_marker_io_owned_and_joins_before_final_detach(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    backend_index: int,
    loss: str,
    phase: str,
) -> None:
    # Catches forced timeout/close, lost owners, late admission and premature detach.
    _t014_core_helpers(monkeypatch)
    core = importlib.import_module("tests.integration.test_monitor")
    async with _app(account_home, monkeypatch, config) as service:
        async with core._live(
            tmp_path,
            monkeypatch,
            core.BACKEND_FIXTURE_FACTORIES[backend_index],
            runtime_support=True,
            runtime=service.runtime,
        ) as case:
            entered, release = asyncio.Event(), asyncio.Event()
            journal: SqliteEvidenceJournal = case.journal
            original_append, original_close = journal.append, journal.close
            original_monitor, original_detach = (
                service.runtime.monitor,
                service.runtime.detach,
            )
            trace: list[str] = []

            async def append(
                draft: evidence.PendingEvidenceRecord,
            ) -> model.EvidenceRecord:
                selected = (
                    phase.startswith("start-")
                    and isinstance(draft, evidence.PendingOperationStartedEvidence)
                ) or (
                    (phase.startswith("end-") or phase == "active")
                    and isinstance(draft, evidence.PendingOperationEndedEvidence)
                )
                if selected and phase.endswith("commit"):
                    entered.set()
                    await release.wait()
                record = await original_append(draft)
                if selected and not phase.endswith("commit"):
                    entered.set()
                    await release.wait()
                return record

            async def close() -> None:
                assert "monitor.settled" in trace and release.is_set()
                await original_close()
                trace.append("journal.closed")

            async def observe(request: monitor.MonitorRequest) -> monitor.MonitorReport:
                try:
                    return await original_monitor(request)
                finally:
                    trace.append("monitor.settled")

            async def detach() -> RuntimeStatus:
                trace.append("final-detach")
                return await original_detach()

            monkeypatch.setattr(case.journal, "append", append)
            monkeypatch.setattr(case.journal, "close", close)
            monkeypatch.setattr(service.runtime, "monitor", observe)
            monkeypatch.setattr(service.runtime, "detach", detach)
            body = _monitor_body(case.journal.session_id)
            client = Client(body=_json(body))
            delivery = service.submit(_ROUTE, client)
            try:
                if phase == "active" or phase.startswith("end-"):
                    await _await(case.clock.wait_started.wait())
                if phase.startswith("end-"):
                    await case.emit(b"PASS trailing\0\xff")
                if phase != "active":
                    await _await(entered.wait())
                await _lost(delivery, client, loss)
                service.launch_context.request_stop()
                assert service.launch_context.stopping
                await _await(entered.wait())
                await service.lifespan.incoming.put({"type": "lifespan.shutdown"})
                await flush()
                assert service.lifespan.task is not None
                for _ in range(3):
                    service.lifespan.task.cancel()
                    await flush()
                    assert not service.lifespan.task.done()
                case.clock.advance(5_000_000_000)
                await flush()
                assert trace == [] and not case.writer_closed.is_set()
                assert not case.terminal_opened.is_set()
                assert service.lifespan.outgoing.empty()
                assert service.launch_context.final_status is None
                _t021_held(account_home)
                for path in (_ROUTE, _READ):
                    _error(
                        await service.request(
                            path, {}, exchange=Exchange(forbid_receive=True)
                        ),
                        503,
                        "service",
                        "stopping",
                    )
                # 006 keeps zero-body validation before mutation admission.
                _error(
                    await service.request(_DETACH, {}, raw=b""),
                    503,
                    "service",
                    "stopping",
                )
                # Authentication still wins before readiness and body access.
                scope = service.scope(_ROUTE)
                scope["headers"] = [
                    (key, value)
                    for key, value in scope["headers"]
                    if key != b"authorization"
                ]
                _error(
                    await service.request(
                        _ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
                    ),
                    401,
                    "request",
                    "authentication_required",
                )
                release.set()
                assert (await _await(service.lifespan.outgoing.get()))[
                    "type"
                ] == "lifespan.shutdown.complete"
                await _await(service.lifespan.task)
                assert trace == ["monitor.settled", "final-detach", "journal.closed"]
                final = service.launch_context.final_status
                assert final is not None and final.owner_settled
                assert (
                    final.recorder_close_confirmed and final.physical_release_confirmed
                )
                assert service.launch_context.final_evidence_read_cleanup_confirmed
                records = await case.page()
                ends = [
                    record
                    for record in records
                    if isinstance(record, model.OperationEndedEvidence)
                ]
                assert len(ends) == 1
                assert ends[0].outcome is (
                    model.MonitorOutcome.MATCHED
                    if phase.startswith("end-")
                    else model.MonitorOutcome.SERVICE_STOPPING
                )
                assert client.messages == []
                _t021_held(
                    account_home
                )  # Lifespan alone cannot release/confirm bootstrap.
            finally:
                release.set()


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize(
    "fault", ["none", "reader-close", "partial-open", "unexpected-open"]
)
@pytest.mark.parametrize("end_unconfirmed", [False, True])
def test_t027_launcher_keeps_reader_uncertainty_dirty_after_monitor_and_reattach(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    backend_index: int,
    fault: str,
    end_unconfirmed: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Catches false clean markers, read-latch resets and early token/lock release.
    from dutchmate_core.adapters import observation_runtime, terminal_evidence
    from dutchmate_core.evidence_access import EvidenceSourceOpenFailure

    caplog.set_level(logging.DEBUG)
    _t014_core_helpers(monkeypatch)
    core = importlib.import_module("tests.integration.test_monitor")
    launch = _T021Launch(account_home, t011_composition)
    entered, release, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    detach_count = 0
    tokens: list[str] = []
    report_facts: list[monitor.MonitorReport] = []
    deliveries: list[asyncio.Task[None]] = []
    scenario_errors: list[BaseException] = []

    async def scenario(http: Any, service: _T011Service) -> None:
        nonlocal detach_count
        tokens.append(service.token.decode())
        fixture = core._durable_fixture(core.BACKEND_FIXTURE_FACTORIES[backend_index])
        monkeypatch.setattr(
            observation_runtime, "BasicSerialBackend", lambda *args: fixture.backend
        )
        gateway = Service(
            service.app, service.config, service.token, ReadBoundary(), http._context
        )
        original_open = terminal_evidence.open_terminal_reader
        original_close = terminal_evidence._close_reader_on_worker

        def close_without_ack(connection: Any) -> None:
            original_close(connection)
            raise evidence.JournalFailure(
                evidence.JournalOperation.CLOSE,
                evidence.JournalFailureKind.IO_FAILURE,
                _PRIVATE,
            )

        async def open_without_ack(target: Any) -> Any:
            reader = await original_open(target)
            await reader.close()  # Avoid a test leak without inventing an ACK.
            if fault == "partial-open":
                raise EvidenceSourceOpenFailure(
                    evidence.JournalFailure(
                        evidence.JournalOperation.OPEN,
                        evidence.JournalFailureKind.IO_FAILURE,
                        _PRIVATE,
                    ),
                    False,
                )
            raise RuntimeError(_PRIVATE)

        with monkeypatch.context() as patch:
            if fault == "reader-close":
                patch.setattr(
                    terminal_evidence, "_close_reader_on_worker", close_without_ack
                )
            elif fault in {"partial-open", "unexpected-open"}:
                patch.setattr(
                    observation_runtime, "open_terminal_reader", open_without_ack
                )
            # Preparation captures the opener; install faults before that handoff.
            response = await service.request(
                _ATTACH,
                "POST",
                _t011_body(
                    t011_composition.profile_path, t011_composition.journal_path
                ),
            )
            assert (
                response.status == 200
                and json.loads(response.payload)["runtime"]["state"] == "active"
            )
            first = await service.runtime.detach()
            assert first.session_id is not None and first.attach_admissible
            read = await gateway.request(
                _READ, {"session_id": first.session_id.value, "sequence": 0}
            )
            if fault == "none":
                assert read.status == 200
            else:
                _error(
                    read,
                    500,
                    "service" if fault == "unexpected-open" else "journal",
                    "internal_failure" if fault == "unexpected-open" else "io_failure",
                )
        assert service.runtime.evidence_read_cleanup_confirmed is (fault == "none")
        assert service.runtime.status() == first

        fixture = core._durable_fixture(core.BACKEND_FIXTURE_FACTORIES[backend_index])
        monkeypatch.setattr(
            observation_runtime, "BasicSerialBackend", lambda *args: fixture.backend
        )
        response = await service.request(
            _ATTACH,
            "POST",
            _t011_body(
                t011_composition.profile_path,
                t011_composition.journal_path.with_name("after-read-fault.sqlite3"),
            ),
        )
        assert (
            response.status == 200
            and json.loads(response.payload)["runtime"]["state"] == "active"
        )
        active = service.runtime.status()
        assert active.session_id is not None and active.run_id != first.run_id
        assert service.runtime.evidence_read_cleanup_confirmed is (fault == "none")
        if fault != "none":
            _error(
                await gateway.request(
                    _READ, {"session_id": active.session_id.value, "sequence": 0}
                ),
                503,
                "evidence",
                "read_unavailable",
            )
        journal = t011_composition.journals[-1]
        original_append, journal_close = journal.append, journal.close
        original_monitor = service.runtime.monitor
        started = asyncio.Event()

        async def append(draft: evidence.PendingEvidenceRecord) -> model.EvidenceRecord:
            record = await original_append(draft)
            if isinstance(draft, evidence.PendingOperationStartedEvidence):
                started.set()
            if isinstance(draft, evidence.PendingOperationEndedEvidence):
                entered.set()
                await release.wait()
                if end_unconfirmed:
                    raise evidence.JournalFailure(
                        evidence.JournalOperation.APPEND,
                        evidence.JournalFailureKind.IO_FAILURE,
                        _PRIVATE,
                    )
            return record

        async def close() -> None:
            assert settled.is_set() and release.is_set()
            await journal_close()
            launch.trace.append("monitor.journal.closed")

        async def observe(request: monitor.MonitorRequest) -> monitor.MonitorReport:
            result = await original_monitor(request)
            report_facts.append(result)
            launch.trace.append("monitor.settled")
            settled.set()
            return result

        monkeypatch.setattr(journal, "append", append)
        monkeypatch.setattr(journal, "close", close)
        monkeypatch.setattr(service.runtime, "monitor", observe)
        client = Client(body=_json(_monitor_body(active.session_id)))

        async def deliver() -> None:
            await gateway.app(gateway.scope(_ROUTE), client.receive, client.send)

        delivery = asyncio.create_task(deliver())
        deliveries.append(delivery)
        # Positive append returns and Core publishes synchronously before a turn.
        await _await(started.wait())
        await fixture.connection.emit_rx(b"PASS trailing\0\xff", timestamp=17)
        await _await(entered.wait())
        await _lost(delivery, client, "disconnect")
        detach_count = launch.trace.count("runtime.detach.enter")
        launch.emit()
        launch.emit()
        assert http.should_exit and not http.force_exit
        assert service.runtime.evidence_read_cleanup_confirmed is (fault == "none")

    async def drain(http: Any, service: _T011Service) -> None:
        assert not http.force_exit and http.config.timeout_graceful_shutdown is None
        _t021_held(account_home)
        assert not settled.is_set() and not release.is_set()
        assert launch.trace.count("runtime.detach.enter") == detach_count
        assert (
            "marker.true" not in launch.trace
            and launch.owners[0].credential is not None
        )
        gateway = Service(
            service.app, service.config, service.token, ReadBoundary(), http._context
        )
        _error(
            await gateway.request(_ROUTE, {}, exchange=Exchange(forbid_receive=True)),
            503,
            "service",
            "stopping",
        )
        release.set()
        await _await(settled.wait())
        await flush()

    async def guarded_scenario(http: Any, service: _T011Service) -> None:
        try:
            await scenario(http, service)
        except BaseException as error:
            scenario_errors.append(error)
            release.set()
            raise

    async def guarded_drain(http: Any, service: _T011Service) -> None:
        try:
            await drain(http, service)
        except BaseException as error:
            scenario_errors.append(error)
            raise
        finally:
            release.set()

    launch.scenario, launch.at_drain = guarded_scenario, guarded_drain
    launch.install(monkeypatch)
    try:
        if fault == "none":
            _t021_server().run_service(ServiceConfig(8765))
        else:
            with pytest.raises(BootstrapFailure) as failure:
                _t021_server().run_service(ServiceConfig(8765))
            assert failure.value.kind is BootstrapFailureKind.TEARDOWN_INCOMPLETE
    finally:
        # Failure cleanup is test-owned and cannot write a positive marker.
        release.set()
    assert not scenario_errors, [repr(error) for error in scenario_errors]
    assert all(task.done() for task in deliveries)
    assert len(report_facts) == 1
    assert report_facts[0].outcome is model.MonitorOutcome.MATCHED
    assert report_facts[0].durability == (
        "end_unconfirmed" if end_unconfirmed else "complete"
    )
    final = launch.settled[id(launch.runtimes[0])]
    assert (
        final.owner_settled
        and final.recorder_close_confirmed
        and final.physical_release_confirmed
    )
    assert final.attach_admissible and final.primary_issue is None
    assert not (launch.root / "credential").exists() and all(
        sock.released for sock in launch.sockets
    )
    assert json.loads((launch.root / "owner.json").read_bytes()) == {
        "version": 1,
        "cleanup_confirmed": fault == "none",
    }
    assert ("marker.true" in launch.trace) is (fault == "none")
    final_detach = max(
        index
        for index, item in enumerate(launch.trace)
        if item == "runtime.detach.enter"
    )
    assert (
        launch.trace.index("monitor.settled")
        < final_detach
        < launch.trace.index("monitor.journal.closed")
    )
    assert (
        launch.trace.index("monitor.journal.closed")
        < launch.trace.index("socket.closed")
        < launch.trace.index("owner.release")
    )
    if fault == "none":
        assert (
            launch.trace.index("socket.closed")
            < launch.trace.index("marker.true")
            < launch.trace.index("owner.release")
        )
    assert _PRIVATE not in caplog.text and all(
        token not in caplog.text for token in tokens
    )


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.parametrize(
    "order",
    [
        ("read", "mutation", "monitor"),
        ("monitor", "read", "mutation"),
        ("mutation", "monitor", "read"),
    ],
)
@pytest.mark.asyncio
async def test_t027_shutdown_joins_all_three_full_pools_in_every_release_order(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    device: bool,
    loss: str,
    order: tuple[str, str, str],
) -> None:
    # Catches final detach after only one pool, or waiter cancellation abandoning work.
    async with _app(account_home, monkeypatch, config) as service:
        calls = PendingCalls()
        trace: list[str] = []
        original_detach = service.runtime.detach

        async def read(value: model.EvidenceReference) -> RunEvidencePage:
            del value
            await calls.wait("read")
            return service.boundary.result

        async def detach() -> RuntimeStatus:
            if service.launch_context.stopping:
                trace.append("final-detach")
                return await original_detach()
            await calls.wait("mutation")
            return service.runtime.status()

        async def observe(request: monitor.MonitorRequest) -> monitor.MonitorReport:
            del request
            await calls.wait("monitor")
            return _report(model.MonitorOutcome.SERVICE_STOPPING, device=device)

        monkeypatch.setattr(service.runtime, "read_record", read)
        monkeypatch.setattr(service.runtime, "detach", detach)
        monkeypatch.setattr(service.runtime, "monitor", observe)
        try:
            for action, path, body, count in [
                ("read", _READ, {"session_id": _SESSION.value, "sequence": 0}, 8),
                ("mutation", _DETACH, {}, 8),
                ("monitor", _ROUTE, _BODY, 1),
            ]:
                for _ in range(count):
                    client = Client(body=b"" if action == "mutation" else _json(body))
                    delivery = service.submit(path, client)
                    await _await(calls.entered.get())
                    await _lost(delivery, client, loss)
            await service.lifespan.incoming.put({"type": "lifespan.shutdown"})
            await flush()
            assert service.launch_context.stopping
            assert service.lifespan.task is not None
            for action in order:
                assert not service.lifespan.task.done()
                assert service.launch_context.final_status is None and trace == []
                _t021_held(account_home)
                calls.release(action)
                if action != order[-1]:
                    await flush()
                    service.lifespan.task.cancel()
                    await flush()
                    assert not service.lifespan.task.done() and trace == []
            assert (await _await(service.lifespan.outgoing.get()))[
                "type"
            ] == "lifespan.shutdown.complete"
            await _await(service.lifespan.task)
            assert trace == ["final-detach"] and len(calls.calls) == 17
            assert all(call.finished.is_set() for call in calls.calls)
            assert service.launch_context.final_status.owner_settled
            assert service.launch_context.final_evidence_read_cleanup_confirmed
            _t021_held(account_home)
        finally:
            calls.release()
