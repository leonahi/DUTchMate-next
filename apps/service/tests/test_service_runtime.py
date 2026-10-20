"""T012 RED: service-owned mutations outlive delivery and release bounded references.

No operation registry or delivery policy is implemented here. Real bootstrap,
security, runtime and temporary Profile/Basic/SQLite composition remain in use.
Only client delivery and external-call progress are controlled by test gates.
"""

import asyncio
import errno
import gc
import importlib.util
import json
import os
import signal
import socket
import stat
import sys
import weakref
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from threading import Event
from typing import Any, cast

import pytest
from dutchmate_core.adapters import basic_serial, observation_runtime, sqlite_evidence
from dutchmate_core.adapters.toml_profile import resolve_profile
from dutchmate_core.evidence import (
    EvidencePageOutcome,
    EvidenceRetrievalRequest,
    JournalFailure,
    JournalFailureKind,
    JournalOperation,
    PendingEvidenceRecord,
    PendingRxBytesEvidence,
    PendingSegmentEndedEvidence,
    PendingSegmentStartedEvidence,
)
from dutchmate_core.model import (
    ConnectionProvenanceSnapshot,
    EvidenceRecord,
    ObserverLossEvidence,
    PersistedConnectionProvenance,
    ProvenanceField,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentEndReason,
    SegmentStartedEvidence,
    SessionId,
    SessionPolicy,
)
from dutchmate_core.profile import ResolvedDutProfile
from dutchmate_core.runtime import (
    ObservationRuntime,
    PreparedObservationRun,
    RuntimeRejectedError,
    RuntimeRejectedKind,
    RuntimeState,
    RuntimeStatus,
    RuntimeStopIntent,
)
from starlette.types import Message

from dutchmate_service.bootstrap import (
    BootstrapFailure,
    BootstrapFailureKind,
    PrivateBootstrap,
    ServiceConfig,
)
from test_service_http import (
    AppLifespan,
    Exchange,
    _headers,
    _scope,
    _t009_module,
    _t009_runtime_spy,
    _t011_body,
    _t011_error,
    _t011_service,
    _t011_view,
    _T011Composition,
    _T011Service,
)
from test_service_http import (
    t011_composition as t011_composition,
)

_ATTACH = "/v1/observation/attach"
_DETACH = "/v1/observation/detach"
_STATUS = "/v1/observation/status"
_T017_OPEN_JOURNAL = sqlite_evidence.SqliteEvidenceJournal.open
_T017_OPEN_JOURNAL_V3 = sqlite_evidence.SqliteEvidenceJournal.open_v3


# T021 tests below catch shutdown that merely ends lifespan, detaches before a
# registered attach, cancels owned work, or releases/attests bootstrap too early.
# All cleanup in the harness is test-only and occurs AFTER the tested assertions.
@asynccontextmanager
async def _t021_app(
    home: Path, patch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[_T011Service, AppLifespan]]:
    module = _t009_module()
    instances, _ = _t009_runtime_spy(module, patch)
    config = ServiceConfig(8765)
    owner = PrivateBootstrap.acquire(config)
    lifespan: AppLifespan | None = None
    try:
        owner.mark_unconfirmed()
        owner.publish_credential()
        token = (home / ".local/state/dutchmate/service/credential").read_bytes()[:-1]
        app = module.create_app(config, _launch_context=module._LaunchContext(config, owner))
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        yield _T011Service(app, instances[0], config, token), lifespan
    finally:
        # Release fake external gates in the test before entering this fallback.
        if instances:
            await asyncio.wait_for(instances[0].detach(), timeout=3)
        if lifespan is not None and lifespan.task is not None:
            if not lifespan.task.done():
                await lifespan.incoming.put({"type": "lifespan.shutdown"})
                done, _ = await asyncio.wait({lifespan.task}, timeout=3)
                assert lifespan.task in done, "test cleanup did not settle"
            await asyncio.gather(lifespan.task, return_exceptions=True)
        owner.release()  # Never writes a positive cleanup marker on behalf of service.


async def _t021_shutdown(lifespan: AppLifespan) -> None:
    await lifespan.incoming.put({"type": "lifespan.shutdown"})
    await flush()


def _t021_held(home: Path) -> None:
    root = home / ".local/state/dutchmate/service"
    assert json.loads((root / "owner.json").read_bytes()) == {
        "version": 1, "cleanup_confirmed": False,
    }
    with pytest.raises(BootstrapFailure) as rejected:
        PrivateBootstrap.acquire(ServiceConfig(8766))
    assert rejected.value.kind is BootstrapFailureKind.OWNER_ACTIVE


@pytest.mark.asyncio
async def test_t021_lifespan_shutdown_detaches_active_run_and_commits_final_evidence(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    c = t011_composition
    commits = _T017Commits()
    commits.install(monkeypatch)
    async with _t021_app(account_home, monkeypatch) as (service, lifespan):
        active = _t011_view(await service.request(
            _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path),
        ), "active")
        await lifespan.finish()
        terminal = service.runtime.status()
        assert terminal.state is RuntimeState.TERMINATED
        assert terminal.attach_admissible and terminal.stop_intent is RuntimeStopIntent.DETACH
        assert terminal.session_id is not None and terminal.session_id.value == active["session_id"]
        assert isinstance(commits.records[-1], SegmentEndedEvidence)
        assert commits.trace.index(f"committed:{commits.records[-1].sequence}") < commits.trace.index("recorder.close")
        assert c.serials[0].close_calls == commits.close_calls == 1


@pytest.mark.asyncio
async def test_t021_shutdown_joins_registered_attach_before_core_invocation_and_detach(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    c = t011_composition
    async with _t021_app(account_home, monkeypatch) as (service, lifespan):
        with monkeypatch.context() as patch:
            probe = CoreCalls(hold_attach=True)
            probe.install(patch)
            client = Client(body=_t011_body(c.profile_path, c.journal_path))
            delivery = submit(service, client, _ATTACH)
            try:
                call = await called(probe, 1, delivery, client)
                delivery.cancel()  # Delivery only; the registered operation survives.
                await finish_delivery(delivery)
                assert service.runtime.status().state is RuntimeState.INACTIVE
                assert c.reads == [] and c.destinations == []
                await _t021_shutdown(lifespan)
                _t021_held(account_home)
                assert lifespan.outgoing.empty(), "shutdown abandoned queued attach"
                assert [item.action for item in probe.calls] == ["attach"]
                _t011_error(await service.request(_ATTACH, "POST", _t011_body(
                    c.profile_path, c.journal_path.with_name("after-stop.sqlite3"),
                )), 503, "service", "stopping")
                assert c.reads == [] and c.destinations == []
                call.release()
                assert lifespan.task is not None
                done, _ = await asyncio.wait({lifespan.task}, timeout=3)
                assert lifespan.task in done
                await asyncio.gather(lifespan.task)
                assert service.runtime.status().state is RuntimeState.TERMINATED
                assert service.runtime.status().stop_intent is RuntimeStopIntent.DETACH
                assert [item.action for item in probe.calls] == ["attach", "detach"]
                assert c.serials[0].close_calls == 1
            finally:
                probe.release()
                delivery.cancel()
                await asyncio.gather(delivery, return_exceptions=True)
                await asyncio.wait_for(call.finished.wait(), timeout=3)


@pytest.mark.parametrize("stage", ["open", "initial-append"])
@pytest.mark.asyncio
async def test_t021_shutdown_keeps_hung_startup_owned_then_detaches_without_attach_cancelled(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition, stage: str,
) -> None:
    c = t011_composition
    entered, release = asyncio.Event(), asyncio.Event()
    async with _t021_app(account_home, monkeypatch) as (service, lifespan):
        original_open = basic_serial.BasicSerialBackend.open
        original_append = sqlite_evidence.SqliteEvidenceJournal.append

        async def opened(backend: basic_serial.BasicSerialBackend) -> Any:
            if stage == "open":
                entered.set()
                await release.wait()
            return await original_open(backend)

        async def append(journal: Any, pending: PendingEvidenceRecord) -> EvidenceRecord:
            if stage == "initial-append" and isinstance(pending, PendingSegmentStartedEvidence):
                entered.set()
                await release.wait()
            return await original_append(journal, pending)

        monkeypatch.setattr(basic_serial.BasicSerialBackend, "open", opened)
        monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "append", append)
        client = Client(body=_t011_body(c.profile_path, c.journal_path))
        delivery = submit(service, client, _ATTACH)
        try:
            await asyncio.wait_for(entered.wait(), timeout=3)
            assert service.runtime.status().state is RuntimeState.ATTACHING
            delivery.cancel()
            await finish_delivery(delivery)
            await _t021_shutdown(lifespan)
            _t021_held(account_home)
            assert lifespan.outgoing.empty(), "startup owner was abandoned"
            assert service.runtime.status().stop_intent is RuntimeStopIntent.NONE
            assert lifespan.task is not None
            for _ in range(3):
                lifespan.task.cancel()  # Cooperative lifecycle cancellation, never Core task cancellation.
                await flush()
                assert not lifespan.task.done()
                _t021_held(account_home)
            release.set()
            done, _ = await asyncio.wait({lifespan.task}, timeout=3)
            assert lifespan.task in done
            await asyncio.gather(lifespan.task, return_exceptions=True)
            terminal = service.runtime.status()
            assert terminal.state is RuntimeState.TERMINATED and terminal.attach_admissible
            assert terminal.stop_intent is RuntimeStopIntent.DETACH
            assert terminal.primary_issue is None and c.serials[0].close_calls == 1
        finally:
            release.set()
            delivery.cancel()
            await asyncio.gather(delivery, return_exceptions=True)
            await flush()


@dataclass
class _T021Launch:
    """Observe real bootstrap/app/Core/Uvicorn; replace only the network edge.

    Fake bound/listening sockets keep fault tests independent of sandbox network
    permissions. Uvicorn's actual startup, HTTP drain and lifespan shutdown run.
    Signals are delivered to installed callbacks, never to the pytest process.
    """

    home: Path
    composition: _T011Composition
    trace: list[str] = field(default_factory=list)
    owners: list[PrivateBootstrap] = field(default_factory=list)
    runtimes: list[ObservationRuntime] = field(default_factory=list)
    sockets: list[Any] = field(default_factory=list)
    listeners: list[Any] = field(default_factory=list)
    scenario: Callable[[Any, _T011Service], Awaitable[None]] | None = None
    at_drain: Callable[[Any, _T011Service], Awaitable[None]] | None = None
    failure_at: str = ""
    cleanup_fault: str = ""
    stop_at: str = ""
    stop_injected: bool = False
    handlers: dict[int, Any] = field(default_factory=dict)
    callbacks: dict[int, tuple[Any, tuple[Any, ...]]] = field(default_factory=dict)
    settled: dict[int, RuntimeStatus] = field(default_factory=dict)

    @property
    def root(self) -> Path:
        return self.home / ".local/state/dutchmate/service"

    def emit(self, signum: int = signal.SIGTERM) -> None:
        if signum in self.callbacks:
            callback, args = self.callbacks[signum]
            callback(*args)
        else:
            handler = self.handlers.get(signum)
            assert callable(handler), "shutdown latch was not installed before bootstrap"
            handler(signum, None)

    def boundary(self, name: str) -> None:
        if name == self.stop_at and not self.stop_injected:
            self.stop_injected = True
            self.emit()
            self.emit()

    def service(self, server: Any) -> _T011Service:
        assert len(self.runtimes) == len(self.owners) == 1
        token = self.owners[0].credential
        assert token is not None
        return _T011Service(server.config.app, self.runtimes[0], ServiceConfig(8765), token.encode())

    def install(self, patch: pytest.MonkeyPatch) -> None:
        import fcntl
        from asyncio import unix_events

        import uvicorn

        from dutchmate_service import bootstrap

        probe = self
        module = _t009_module()
        class Runtime(ObservationRuntime):
            def __init__(self) -> None:
                if probe.failure_at == "lifespan":
                    raise BootstrapFailure(BootstrapFailureKind.BOOTSTRAP_IO_FAILED)
                super().__init__()
                probe.runtimes.append(self)
                probe.trace.append("runtime.constructed")
                probe.boundary("lifespan")

            async def detach(self) -> RuntimeStatus:
                probe.trace.append("runtime.detach.enter")
                _t021_held(probe.home)
                result = await super().detach()
                probe.settled[id(self)] = result
                probe.trace.append("runtime.detach.done")
                return result

        patch.setattr(module, "ObservationRuntime", Runtime)
        original_acquire = PrivateBootstrap.acquire

        def acquire(cls: Any, config: ServiceConfig) -> PrivateBootstrap:
            del cls
            result = original_acquire(config)
            probe.owners.append(result)
            probe.trace.append("owner.acquired")
            return result

        patch.setattr(PrivateBootstrap, "acquire", classmethod(acquire))
        original_mkdir, original_flock = os.mkdir, fcntl.flock

        def mkdir(path: Any, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
            original_mkdir(path, mode, dir_fd=dir_fd)
            if os.fsdecode(path) == "service":
                probe.boundary("directory")

        def flock(fd: Any, operation: int) -> None:
            original_flock(fd, operation)
            if operation == fcntl.LOCK_EX | fcntl.LOCK_NB:
                probe.boundary("lock")

        patch.setattr(os, "mkdir", mkdir)
        patch.setattr(fcntl, "flock", flock)
        original_eligible = bootstrap._eligible

        def eligible(directory: int) -> None:
            if probe.failure_at == "eligibility":
                raise BootstrapFailure(BootstrapFailureKind.BOOTSTRAP_IO_FAILED)
            original_eligible(directory)

        patch.setattr(bootstrap, "_eligible", eligible)
        original_mark = PrivateBootstrap.mark_unconfirmed
        original_publish = PrivateBootstrap.publish_credential
        original_invalidate = PrivateBootstrap.invalidate_credential
        original_confirm = PrivateBootstrap.confirm_cleanup
        original_release = PrivateBootstrap.release

        def mark(owner: PrivateBootstrap) -> None:
            original_mark(owner)
            probe.trace.append("marker.false")
            probe.boundary("marker")
            if probe.failure_at == "marker":
                raise BootstrapFailure(BootstrapFailureKind.BOOTSTRAP_IO_FAILED)

        def publish(owner: PrivateBootstrap) -> None:
            original_publish(owner)
            probe.trace.append("token.published")
            probe.boundary("token")
            if probe.failure_at == "token":
                raise BootstrapFailure(BootstrapFailureKind.BOOTSTRAP_IO_FAILED)

        def invalidate(owner: PrivateBootstrap) -> None:
            try:
                original_invalidate(owner)
            finally:
                if owner.credential is not None:
                    pytest.fail("credential cache was not invalidated")
                probe.trace.append("token.invalidated")

        def confirm(owner: PrivateBootstrap, **facts: bool) -> None:
            if owner.credential is not None:
                pytest.fail("credential cache survived cleanup confirmation")
            assert not (probe.root / "credential").exists()
            assert all(sock.released for sock in probe.sockets)
            assert all(id(runtime) in probe.settled and probe.settled[id(runtime)].attach_admissible
                       for runtime in probe.runtimes)
            assert facts == {"owner_settled": True, "physical_release_confirmed": True,
                             "recorder_close_confirmed": True}
            if probe.cleanup_fault == "marker":
                raise BootstrapFailure(BootstrapFailureKind.TEARDOWN_INCOMPLETE)
            original_confirm(owner, **facts)
            probe.trace.append("marker.true")

        def release(owner: PrivateBootstrap) -> None:
            # Settled-but-uncertain is releasable, pending ownership is not.
            assert all(id(runtime) in probe.settled and probe.settled[id(runtime)].owner_settled
                       for runtime in probe.runtimes)
            assert all(sock.released for sock in probe.sockets)
            probe.trace.append("owner.release")
            original_release(owner)

        patch.setattr(PrivateBootstrap, "mark_unconfirmed", mark)
        patch.setattr(PrivateBootstrap, "publish_credential", publish)
        patch.setattr(PrivateBootstrap, "invalidate_credential", invalidate)
        patch.setattr(PrivateBootstrap, "confirm_cleanup", confirm)
        patch.setattr(PrivateBootstrap, "release", release)
        original_unlink = os.unlink

        def unlink(path: Any, *, dir_fd: int | None = None) -> None:
            if os.fsdecode(path) == "credential" and probe.cleanup_fault == "credential":
                raise OSError("private injected credential-removal error")
            original_unlink(path, dir_fd=dir_fd)

        patch.setattr(os, "unlink", unlink)

        class BoundSocket(socket.socket):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                self.released = False
                self.address: Any = None
                if self.family in {socket.AF_INET, socket.AF_INET6}:
                    probe.sockets.append(self)

            def bind(self, address: Any) -> None:
                assert address == ("127.0.0.1", 8765)
                if probe.failure_at == "socket":
                    raise OSError(errno.EADDRINUSE, "private injected bind error")
                self.address = address
                probe.trace.append("socket.bound")
                probe.boundary("socket")

            def getsockname(self) -> Any:
                return self.address if self.address is not None else super().getsockname()

            def close(self) -> None:
                if self.family not in {socket.AF_INET, socket.AF_INET6}:
                    super().close()
                    return
                if not self.released:
                    assert all(id(runtime) in probe.settled and probe.settled[id(runtime)].owner_settled
                               for runtime in probe.runtimes)
                    super().close()
                    self.released = True
                    probe.trace.append("socket.closed")
                    if probe.cleanup_fault == "socket":
                        raise BootstrapFailure(BootstrapFailureKind.TEARDOWN_INCOMPLETE)

        patch.setattr(socket, "socket", BoundSocket)

        class Listener:
            def __init__(self, sock: Any) -> None:
                self.sockets = (sock,)
                self.closed = False

            def close(self) -> None:
                self.closed = True
                probe.trace.append("http.acceptance.closed")

            async def wait_closed(self) -> None:
                assert self.closed

        async def create_server(loop: Any, *args: Any, **kwargs: Any) -> Any:
            del loop, args
            if probe.failure_at == "http-startup":
                raise BootstrapFailure(BootstrapFailureKind.BOOTSTRAP_IO_FAILED)
            assert not probe.stop_injected, "startup stop was followed by HTTP admission"
            assert len(probe.runtimes) == 1
            assert kwargs["sock"] in probe.sockets
            listener = Listener(kwargs["sock"])
            probe.listeners.append(listener)
            probe.trace.append("http.listening")
            return listener

        patch.setattr(asyncio.BaseEventLoop, "create_server", create_server)

        original_getsignal = signal.getsignal

        def signal_handler(signum: int, handler: Any) -> Any:
            previous = probe.handlers.get(signum, original_getsignal(signum))
            probe.handlers[signum] = handler
            return previous

        def get_signal(signum: int) -> Any:
            return probe.handlers.get(signum, original_getsignal(signum))

        def loop_signal(loop: Any, signum: int, callback: Any, *args: Any) -> None:
            del loop
            probe.callbacks[signum] = (callback, args)

        def remove_loop_signal(loop: Any, signum: int) -> bool:
            del loop
            return probe.callbacks.pop(signum, None) is not None

        patch.setattr(signal, "signal", signal_handler)
        patch.setattr(signal, "getsignal", get_signal)
        def no_signal_replay(signum: int) -> None:
            del signum
            raise AssertionError("supported shutdown must not replay process signals")

        patch.setattr(signal, "raise_signal", no_signal_replay)
        patch.setattr(unix_events._UnixSelectorEventLoop, "add_signal_handler", loop_signal)
        patch.setattr(unix_events._UnixSelectorEventLoop, "remove_signal_handler", remove_loop_signal)
        original_drain = uvicorn.Server._wait_tasks_to_complete

        async def main_loop(server: Any) -> None:
            probe.trace.append("http.ready")
            if probe.scenario is not None:
                await probe.scenario(server, probe.service(server))
            else:
                probe.emit()
            assert server.should_exit and not server.force_exit

        async def drain(server: Any) -> None:
            probe.trace.append("http.draining")
            assert not server.force_exit and server.config.timeout_graceful_shutdown is None
            _t021_held(probe.home)
            if probe.at_drain is not None:
                await probe.at_drain(server, probe.service(server))
            await original_drain(server)

        patch.setattr(uvicorn.Server, "main_loop", main_loop)
        patch.setattr(uvicorn.Server, "_wait_tasks_to_complete", drain)


def _t021_server() -> Any:
    return importlib.import_module("dutchmate_service.server")


def test_t022_signal_probe_preserves_registered_handler_through_asyncio_runner(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    launch = _T021Launch(account_home, t011_composition)
    launch.install(monkeypatch)
    calls: list[int] = []

    def handler(signum: int, frame: Any) -> None:
        del frame
        calls.append(signum)

    signal.signal(signal.SIGINT, handler)

    async def exercise() -> None:
        assert signal.getsignal(signal.SIGINT) is handler
        launch.emit(signal.SIGINT)
        launch.emit(signal.SIGINT)

    asyncio.run(exercise())
    assert calls == [signal.SIGINT, signal.SIGINT]
    assert launch.runtimes == [] and launch.owners == []


def test_t023_failed_http_drain_cannot_publish_a_clean_incarnation(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    import uvicorn

    launch = _T021Launch(account_home, t011_composition)
    launch.install(monkeypatch)
    original = uvicorn.Server._wait_tasks_to_complete

    async def failed(server: Any) -> None:
        await original(server)
        raise OSError("private HTTP drain failure")

    monkeypatch.setattr(uvicorn.Server, "_wait_tasks_to_complete", failed)
    with pytest.raises(BootstrapFailure) as failure:
        _t021_server().run_service(ServiceConfig(8765))
    assert failure.value.kind is BootstrapFailureKind.TEARDOWN_INCOMPLETE
    assert launch.settled[id(launch.runtimes[0])].attach_admissible
    assert "marker.true" not in launch.trace
    assert json.loads((launch.root / "owner.json").read_bytes())["cleanup_confirmed"] is False
    assert not (launch.root / "credential").exists()
    with pytest.raises(BootstrapFailure) as stale:
        PrivateBootstrap.acquire(ServiceConfig(8766))
    assert stale.value.kind is BootstrapFailureKind.PREVIOUS_CLEANUP_UNCONFIRMED


@pytest.mark.parametrize("phase", ["false", "credential", "true"])
@pytest.mark.parametrize("point", ["file-fsync", "replace", "directory-fsync"])
def test_t024_actual_publication_failure_preserves_cleanup_and_durability_facts(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition, phase: str, point: str,
) -> None:
    c = t011_composition
    launch = _T021Launch(account_home, c)
    launch.root.mkdir(mode=0o700, parents=True)
    previous = b'{"version":1,"cleanup_confirmed":true}\n'
    (launch.root / "owner.json").write_bytes(previous)
    (launch.root / "owner.json").chmod(0o600)
    journal = _T015Journal()
    journal.install(monkeypatch)

    async def active_then_stop(http: Any, service: _T011Service) -> None:
        del http
        _t011_view(await service.request(
            _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path),
        ), "active")
        launch.emit()

    if phase == "true":
        launch.scenario = active_then_stop
    launch.install(monkeypatch)
    original_publish = PrivateBootstrap._publish
    original_fsync, original_replace = os.fsync, os.replace
    current: str | None = None
    injected = False
    true_replaced = False

    def publication(owner: Any, name: str, data: bytes, replaced: Any) -> None:
        nonlocal current
        current = "credential" if name == "credential" else (
            "true" if json.loads(data)["cleanup_confirmed"] else "false"
        )
        try:
            original_publish(owner, name, data, replaced)
        finally:
            current = None  # Never retain credential bytes in the probe.

    def prove_cleanup_before_true() -> None:
        if launch.runtimes:
            assert len(launch.settled) == 1
            final = launch.settled[id(launch.runtimes[0])]
            assert final.owner_settled and final.physical_release_confirmed and final.recorder_close_confirmed
            assert c.serials[0].close_calls == journal.close_calls == 1
            assert c.serials[0].active_reads == 0
        else:
            assert c.serials == [] and c.journals == [] and journal.close_calls == 0
        assert all(sock.released and sock.fileno() == -1 for sock in launch.sockets)
        assert not (launch.root / "credential").exists()
        if launch.owners[0].credential is not None:
            pytest.fail("true publication preceded memory credential invalidation")
        with pytest.raises(BootstrapFailure) as duplicate:
            PrivateBootstrap.acquire(ServiceConfig(8766))
        assert duplicate.value.kind is BootstrapFailureKind.OWNER_ACTIVE

    def fsync(fd: int) -> None:
        nonlocal injected
        directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        wanted = (point == "directory-fsync" and directory) or (point == "file-fsync" and not directory)
        if current == phase and wanted and not injected:
            if current == "true":
                prove_cleanup_before_true()
            injected = True
            raise OSError("private publication fsync failure")
        original_fsync(fd)

    def replace_file(src: Any, dst: Any, **kwargs: Any) -> None:
        nonlocal injected, true_replaced
        if current == "true":
            prove_cleanup_before_true()
        if current == phase and point == "replace" and not injected:
            injected = True
            raise OSError("private publication replacement failure")
        original_replace(src, dst, **kwargs)
        if current == "true":
            true_replaced = True

    monkeypatch.setattr(PrivateBootstrap, "_publish", publication)
    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace_file)
    with pytest.raises(BootstrapFailure) as failure:
        _t021_server().run_service(ServiceConfig(8765))
    assert injected
    assert failure.value.kind is (
        BootstrapFailureKind.TEARDOWN_INCOMPLETE if phase == "true"
        else BootstrapFailureKind.BOOTSTRAP_IO_FAILED
    )
    assert all(sock.released for sock in launch.sockets)
    assert not (launch.root / "credential").exists()
    assert list(launch.root.glob(".bootstrap-*")) == []
    marker = json.loads((launch.root / "owner.json").read_bytes())
    expected_true = (phase == "credential" or point == "directory-fsync" and phase == "true"
                     or phase == "false" and point != "directory-fsync")
    assert marker == {"version": 1, "cleanup_confirmed": expected_true}
    if phase == "true":
        assert "marker.true" not in launch.trace  # No successful confirmation returned.
        assert true_replaced is (point == "directory-fsync")
        assert c.journal_path.exists() and journal.close_calls == 1
        assert launch.trace.index("runtime.detach.done") < launch.trace.index("token.invalidated")
        assert launch.trace.index("token.invalidated") < launch.trace.index("socket.closed")
    elif phase == "false":
        assert launch.runtimes == [] and launch.sockets == []
        if point != "directory-fsync":
            assert (launch.root / "owner.json").read_bytes() == previous
    else:
        assert launch.runtimes == [] and len(launch.sockets) == 1
        assert "marker.true" in launch.trace  # Empty startup resources were actually closed.
    if expected_true:
        owner = PrivateBootstrap.acquire(ServiceConfig(8766))
        owner.release()
    else:
        with pytest.raises(BootstrapFailure) as stale:
            PrivateBootstrap.acquire(ServiceConfig(8766))
        assert stale.value.kind is BootstrapFailureKind.PREVIOUS_CLEANUP_UNCONFIRMED


@pytest.mark.asyncio
async def test_t023_draining_status_projects_real_runtime_while_mutations_remain_closed(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    c = t011_composition
    entered, release = asyncio.Event(), asyncio.Event()
    original_close = sqlite_evidence.SqliteEvidenceJournal.close

    async def close(journal: sqlite_evidence.SqliteEvidenceJournal) -> None:
        entered.set()
        await release.wait()
        await original_close(journal)

    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "close", close)
    async with _t021_app(account_home, monkeypatch) as (service, lifespan):
        active = _t011_view(await service.request(
            _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path),
        ), "active")
        try:
            await _t021_shutdown(lifespan)
            await asyncio.wait_for(entered.wait(), timeout=3)
            response = await service.request(_STATUS, "GET")
            assert response.status == 200 and response.headers[b"cache-control"] == b"no-store"
            document = json.loads(response.payload)
            assert set(document) == {"service_state", "runtime"}
            assert document["service_state"] == "stopping"
            assert document["runtime"]["state"] == "detaching"
            assert document["runtime"]["run_id"] == active["run_id"]
            assert document["runtime"]["owner_settled"] is False
            assert document["runtime"]["recorder_close_confirmed"] is False
            reads = list(c.reads)
            _t011_error(await service.request(_ATTACH, "POST", _t011_body(
                c.profile_path, c.journal_path.with_name("after-stop.sqlite3"),
            )), 503, "service", "stopping")
            assert c.reads == reads and not c.journal_path.with_name("after-stop.sqlite3").exists()
            _t021_held(account_home)
        finally:
            release.set()


def test_t021_launcher_closes_admission_before_draining_existing_http_delivery(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    server = _t021_server()
    c = t011_composition
    launch = _T021Launch(account_home, c)
    client = Client(body=_t011_body(c.profile_path, c.journal_path), hold_publication=True)
    deliveries: list[asyncio.Task[None]] = []

    async def scenario(http: Any, service: _T011Service) -> None:
        delivery = submit(service, client, _ATTACH)
        deliveries.append(delivery)
        http.server_state.tasks.add(delivery)
        delivery.add_done_callback(http.server_state.tasks.discard)
        await asyncio.wait_for(client.publication.wait(), timeout=3)
        assert service.runtime.status().state is RuntimeState.ACTIVE
        launch.emit(signal.SIGINT)
        launch.emit(signal.SIGINT)
        launch.emit(signal.SIGTERM)

    async def draining(http: Any, service: _T011Service) -> None:
        del http
        reads = list(c.reads)
        try:
            assert not deliveries[0].done()
            _t011_error(await service.request(_ATTACH, "POST", _t011_body(
                c.profile_path, c.journal_path.with_name("draining-not-created.sqlite3"),
            )), 503, "service", "stopping")
            assert c.reads == reads and not (c.journal_path.parent / "draining-not-created.sqlite3").exists()
        finally:
            client.publication_gate.set()

    launch.scenario, launch.at_drain = scenario, draining
    launch.install(monkeypatch)
    server.run_service(ServiceConfig(8765))
    assert launch.trace.index("http.draining") < launch.trace.index("runtime.detach.enter")
    assert launch.trace.index("runtime.detach.done") < launch.trace.index("token.invalidated")
    assert launch.trace.index("token.invalidated") < launch.trace.index("socket.closed")
    assert launch.trace.index("socket.closed") < launch.trace.index("marker.true") < launch.trace.index("owner.release")
    assert launch.settled[id(launch.runtimes[0])].attach_admissible
    assert c.serials[0].close_calls == 1 and all(delivery.done() for delivery in deliveries)
    assert not (launch.root / "credential").exists()


@pytest.mark.parametrize("backend_fails,recorder_fails", [(True, False), (False, True), (True, True)])
@pytest.mark.parametrize("already_settled", [False, True], ids=["active", "terminal-uncertain"])
def test_t021_launcher_preserves_original_cleanup_uncertainty_and_blocks_restart(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition, backend_fails: bool, recorder_fails: bool,
    already_settled: bool,
) -> None:
    server = _t021_server()
    c = t011_composition
    c.close_error = OSError("private backend close error") if backend_fails else None
    journal = _T015Journal(fail_close=recorder_fails)
    journal.install(monkeypatch)
    launch = _T021Launch(account_home, c)
    final: list[RuntimeStatus] = []

    async def scenario(http: Any, service: _T011Service) -> None:
        del http
        _t011_view(await service.request(_ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)), "active")
        if already_settled:
            _t011_view(await service.request(_DETACH, "POST"), "failed")
        launch.emit()

    original_detach = ObservationRuntime.detach

    async def detach(owner: ObservationRuntime) -> RuntimeStatus:
        status = await original_detach(owner)
        final.append(status)
        return status

    monkeypatch.setattr(ObservationRuntime, "detach", detach)
    launch.scenario = scenario
    launch.install(monkeypatch)
    with pytest.raises(BootstrapFailure) as failure:
        server.run_service(ServiceConfig(8765))
    assert failure.value.kind is BootstrapFailureKind.TEARDOWN_INCOMPLETE
    assert len(final) == (2 if already_settled else 1)
    status = final[-1]
    if already_settled:
        assert final[0] == status  # No reclassification/reset/retry of old uncertainty.
    assert status.state is RuntimeState.FAILED and status.owner_settled
    assert status.stop_intent is RuntimeStopIntent.DETACH and status.primary_issue is None
    assert status.physical_release_confirmed is (not backend_fails)
    assert status.recorder_close_confirmed is (not recorder_fails)
    assert not status.attach_admissible and len(status.cleanup_issues) == int(backend_fails) + int(recorder_fails)
    assert status.acquisition is not None and status.acquisition.primary_failure_kind is None
    assert status.acquisition.close_failed is backend_fails
    assert c.serials[0].close_calls == journal.close_calls == 1
    assert c.journal_path.exists() and "marker.true" not in launch.trace
    assert json.loads((launch.root / "owner.json").read_bytes())["cleanup_confirmed"] is False
    assert not (launch.root / "credential").exists()
    if launch.owners[0].credential is not None:
        pytest.fail("uncertain teardown retained a cached credential")
    with pytest.raises(BootstrapFailure) as stale:
        PrivateBootstrap.acquire(ServiceConfig(8766))
    assert stale.value.kind is BootstrapFailureKind.PREVIOUS_CLEANUP_UNCONFIRMED


def test_t021_failed_runtime_with_confirmed_cleanup_can_attest_clean_service_shutdown(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    server = _t021_server()
    c = t011_composition
    journal = _T015Journal(fail_append="start")
    journal.install(monkeypatch)
    launch = _T021Launch(account_home, c)
    prior: list[RuntimeStatus] = []

    async def scenario(http: Any, service: _T011Service) -> None:
        del http
        _t011_view(await service.request(_ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)), "failed")
        status = service.runtime.status()
        assert status.attach_admissible and status.primary_issue is not None
        prior.append(status)
        launch.emit()

    launch.scenario = scenario
    launch.install(monkeypatch)
    server.run_service(ServiceConfig(8765))
    assert launch.settled[id(launch.runtimes[0])] == prior[0]
    assert c.serials[0].close_calls == journal.close_calls == 1
    assert c.journal_path.exists() and not (launch.root / "credential").exists()
    assert json.loads((launch.root / "owner.json").read_bytes())["cleanup_confirmed"] is True
    assert launch.trace.index("marker.true") < launch.trace.index("owner.release")


@pytest.mark.parametrize("fault", ["credential", "socket", "marker"])
def test_t021_launcher_cleanup_error_never_attests_success_or_releases_pending_owner(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition, fault: str,
) -> None:
    server = _t021_server()
    launch = _T021Launch(account_home, t011_composition, cleanup_fault=fault)
    launch.install(monkeypatch)
    with pytest.raises(BootstrapFailure) as failure:
        server.run_service(ServiceConfig(8765))
    assert failure.value.kind is BootstrapFailureKind.TEARDOWN_INCOMPLETE
    if launch.owners[0].credential is not None:
        pytest.fail("failed teardown retained a cached credential")
    assert "marker.true" not in launch.trace and "owner.release" in launch.trace
    assert all(sock.released for sock in launch.sockets)
    assert json.loads((launch.root / "owner.json").read_bytes())["cleanup_confirmed"] is False
    assert (launch.root / "credential").exists() is (fault == "credential")
    assert launch.trace.index("runtime.detach.done") < launch.trace.index("owner.release")
    with pytest.raises(BootstrapFailure) as stale:
        PrivateBootstrap.acquire(ServiceConfig(8766))
    assert stale.value.kind is BootstrapFailureKind.PREVIOUS_CLEANUP_UNCONFIRMED


@pytest.mark.parametrize("stage", ["eligibility", "marker", "socket", "token", "lifespan", "http-startup"])
def test_t021_partial_startup_unwinds_only_acquired_resources_before_guard_release(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition, stage: str,
) -> None:
    server = _t021_server()
    launch = _T021Launch(account_home, t011_composition, failure_at=stage)
    launch.root.mkdir(mode=0o700, parents=True)
    previous = b'{"version":1,"cleanup_confirmed":true}\n'
    (launch.root / "owner.json").write_bytes(previous)
    (launch.root / "owner.json").chmod(0o600)
    launch.install(monkeypatch)
    with pytest.raises(BootstrapFailure):
        server.run_service(ServiceConfig(8765))
    assert "http.ready" not in launch.trace
    assert all(sock.released for sock in launch.sockets)
    assert not (launch.root / "credential").exists()
    assert t011_composition.reads == [] and t011_composition.destinations == []
    if stage == "eligibility":
        assert (launch.root / "owner.json").read_bytes() == previous
        assert "marker.false" not in launch.trace and launch.sockets == []
    else:
        assert "owner.release" in launch.trace
        if launch.runtimes:
            assert launch.trace.index("runtime.detach.done") < launch.trace.index("token.invalidated")
        if launch.sockets:
            assert launch.trace.index("socket.closed") < launch.trace.index("owner.release")
            if "token.published" in launch.trace:
                assert launch.trace.index("token.invalidated") < launch.trace.index("socket.closed")
        assert json.loads((launch.root / "owner.json").read_bytes())["cleanup_confirmed"] is True
    # Neither retained uncertainty nor an early guard release is hidden by the test.
    launch.failure_at = ""
    owner = PrivateBootstrap.acquire(ServiceConfig(8766))
    owner.release()


@pytest.mark.parametrize("stage", ["directory", "lock", "marker", "socket", "token", "lifespan"])
def test_t021_startup_signal_latch_never_reopens_admission_and_unwinds_owned_resources(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition, stage: str,
) -> None:
    server = _t021_server()
    launch = _T021Launch(account_home, t011_composition, stop_at=stage)
    launch.install(monkeypatch)
    server.run_service(ServiceConfig(8765))
    assert launch.stop_injected
    assert "http.ready" not in launch.trace and "http.listening" not in launch.trace
    assert all(sock.released for sock in launch.sockets)
    assert not (launch.root / "credential").exists()
    assert t011_composition.reads == [] and t011_composition.destinations == []
    if launch.runtimes:
        assert launch.trace.index("runtime.detach.done") < launch.trace.index("owner.release")
    owner = PrivateBootstrap.acquire(ServiceConfig(8766))
    owner.release()


@pytest.mark.parametrize("stage", ["backend-close", "recorder-close"])
@pytest.mark.parametrize("cancel_count", [0, 3])
@pytest.mark.asyncio
async def test_t021_shutdown_keeps_hung_cleanup_pending_under_repeated_cancellation(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition, stage: str, cancel_count: int,
) -> None:
    c = t011_composition
    entered, release = asyncio.Event(), asyncio.Event()
    async with _t021_app(account_home, monkeypatch) as (service, lifespan):
        original_backend = basic_serial._BasicSerialConnection.close
        original_recorder = sqlite_evidence.SqliteEvidenceJournal.close

        async def backend_close(connection: Any) -> None:
            if stage == "backend-close":
                entered.set()
                await release.wait()
            await original_backend(connection)

        async def recorder_close(journal: Any) -> None:
            if stage == "recorder-close":
                entered.set()
                await release.wait()
            await original_recorder(journal)

        monkeypatch.setattr(basic_serial._BasicSerialConnection, "close", backend_close)
        monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "close", recorder_close)
        await service.request(_ATTACH, "POST", _t011_body(c.profile_path, c.journal_path))
        try:
            await _t021_shutdown(lifespan)
            assert service.runtime.status().state is RuntimeState.DETACHING
            await asyncio.wait_for(entered.wait(), timeout=3)
            _t021_held(account_home)
            assert lifespan.task is not None and not lifespan.task.done()
            for _ in range(cancel_count):
                lifespan.task.cancel()
                await flush()
                assert not lifespan.task.done() and lifespan.outgoing.empty()
                assert not service.runtime.status().owner_settled
                _t021_held(account_home)
            release.set()
            done, _ = await asyncio.wait({lifespan.task}, timeout=3)
            assert lifespan.task in done
            await asyncio.gather(lifespan.task, return_exceptions=True)
            terminal = service.runtime.status()
            assert terminal.state is RuntimeState.TERMINATED and terminal.attach_admissible
            assert terminal.stop_intent is RuntimeStopIntent.DETACH
            assert c.serials[0].close_calls == 1
        finally:
            release.set()


@dataclass
class _T017Commits:
    records: list[EvidenceRecord] = field(default_factory=list)
    queue: asyncio.Queue[EvidenceRecord] = field(default_factory=asyncio.Queue)
    trace: list[str] = field(default_factory=list)
    close_calls: int = 0
    closed: asyncio.Event = field(default_factory=asyncio.Event)

    def install(self, patch: pytest.MonkeyPatch) -> None:
        original_append = sqlite_evidence.SqliteEvidenceJournal.append
        original_close = sqlite_evidence.SqliteEvidenceJournal.close

        async def append(
            journal: sqlite_evidence.SqliteEvidenceJournal,
            pending: PendingEvidenceRecord,
        ) -> EvidenceRecord:
            record = await original_append(journal, pending)
            self.records.append(record)
            self.trace.append(f"committed:{record.sequence}")
            self.queue.put_nowait(record)
            return record

        async def close(journal: sqlite_evidence.SqliteEvidenceJournal) -> None:
            self.close_calls += 1
            self.trace.append("recorder.close")
            await original_close(journal)
            self.closed.set()

        patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "append", append)
        patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "close", close)

    async def next(self, sequence: int) -> EvidenceRecord:
        record = await asyncio.wait_for(self.queue.get(), timeout=3.0)
        assert record.sequence == sequence
        return record


async def _t017_readback(
    path: Path, session_id: SessionId, expected: list[EvidenceRecord], *, v3: bool = False
) -> None:
    # Capture the real reopen API before fixture guards: this call is test-only
    # after HTTP detach/confirmed close, never part of service composition.
    opener = _T017_OPEN_JOURNAL_V3 if v3 else _T017_OPEN_JOURNAL
    reopened = await opener(path, expected_session_id=session_id)
    retrieved: list[EvidenceRecord] = []
    cursor = None
    pages = 0
    try:
        while True:
            page = await reopened.retrieve(
                EvidenceRetrievalRequest(session_id, 2, 16384, cursor)
            )
            pages += 1
            assert page.outcome is EvidencePageOutcome.COMPLETE
            assert page.retention_marker is None and page.expired_range is None
            assert page.snapshot_end_exclusive == len(expected)
            assert len(page.records) <= 2
            retrieved.extend(page.records)
            if page.continuation is None:
                assert not page.truncated
                break
            assert page.truncated and pages < 10
            cursor = page.continuation
    finally:
        await reopened.close()
    assert pages >= 2 and retrieved == expected
    assert [record.sequence for record in retrieved] == list(range(len(expected)))


@pytest.mark.parametrize(
    "lose_attach_response", [False, True], ids=["idle", "lost-attach-response"]
)
@pytest.mark.asyncio
async def test_t017_http_basic_captures_exact_binary_between_clients_and_reopens_after_detach(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    lose_attach_response: bool,
) -> None:
    c = t011_composition
    payloads = (
        bytes(range(256)) + b"\x00\xff\x80",
        b"ambient before status\r\n\x00\xfe",
        b"after status\x80\xff",
    )
    gates = tuple(Event() for _ in range(len(payloads) + 1))
    commits = _T017Commits()
    delivery: asyncio.Task[None] | None = None
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            commits.install(patch)
            original_init = basic_serial.BasicSerialBackend.__init__

            def construct(
                self: basic_serial.BasicSerialBackend,
                selector: basic_serial.SerialDeviceSelector,
                configuration: basic_serial.SerialConfiguration,
                line_intent: basic_serial.SerialOpenLineIntent,
            ) -> None:
                original_init(self, selector, configuration, line_intent)
                fake = c.serials[-1]
                # Configure only the existing external serial test double before
                # open/first read. Its strict read counters and adapter stay real.
                fake._read_results = (*payloads, b"")
                fake._read_gates = gates
                fake.read_started = tuple(Event() for _ in gates)
                original_cancel = fake.cancel_read

                def cancel_read() -> None:
                    original_cancel()
                    for gate in gates:
                        gate.set()

                fake.cancel_read = cancel_read

            patch.setattr(basic_serial.BasicSerialBackend, "__init__", construct)
            try:
                if lose_attach_response:
                    client = Client(
                        body=_t011_body(c.profile_path, c.journal_path),
                        hold_publication=True,
                    )
                    delivery = submit(service, client, _ATTACH)
                    await asyncio.wait_for(client.publication.wait(), timeout=3.0)
                    assert client.status == 200
                    delivery.cancel()
                    await finish_delivery(delivery)
                    active = _t011_view(await service.request(_STATUS, "GET"), "active")
                else:
                    active = _t011_view(
                        await service.request(
                            _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
                        ),
                        "active",
                    )
                start = await commits.next(0)
                assert isinstance(start, SegmentStartedEvidence)
                assert active["session_id"] == c.journals[0].session_id.value
                assert (
                    active["acquisition"]["provenance"]["connection_id"]
                    == start.connection_id.value
                )
                assert (
                    active["acquisition"]["provenance"]["segment_id"]
                    == start.segment_id.value
                )
                assert (
                    active["acquisition"]["descriptor"][
                        "backend_observation_timestamp_domain"
                    ]["observer"]
                    == "host"
                )
                assert active["acquisition"]["descriptor"]["loss_observability"] == {
                    "kind": "upstream_loss_not_observable"
                }
                for index, payload in enumerate(payloads):
                    # Commit notification is not a client/reader. The service
                    # has no outstanding HTTP request during these releases.
                    gates[index].set()
                    record = await commits.next(index + 1)
                    assert (
                        isinstance(record, RxBytesEvidence)
                        and record.payload == payload
                    )
                    assert (
                        record.observed_at.domain_id
                        == start.provenance.backend_observation_timestamp_domain.domain_id
                    )
                    if index == 1:
                        assert (
                            _t011_view(await service.request(_STATUS, "GET"), "active")
                            == active
                        )
                terminal = _t011_view(
                    await service.request(_DETACH, "POST"), "terminated"
                )
                end = await commits.next(4)
                assert (
                    isinstance(end, SegmentEndedEvidence)
                    and end.reason is SegmentEndReason.EXPLICIT_STOP
                )
                assert (
                    terminal["run_id"] == active["run_id"]
                    and terminal["session_id"] == active["session_id"]
                )
                assert terminal["profile"] == active["profile"]
                assert (
                    terminal["terminal_reason"] == "detached"
                    and terminal["stop_intent"] == "detach"
                )
                assert terminal["attach_admissible"] and terminal["owner_settled"]
                assert (
                    terminal["physical_release_confirmed"]
                    and terminal["recorder_close_confirmed"]
                )
                assert (
                    terminal["acquisition"]["provenance"]
                    == active["acquisition"]["provenance"]
                )
                assert commits.trace.index("committed:4") < commits.trace.index(
                    "recorder.close"
                )
                assert commits.close_calls == c.serials[0].close_calls == 1
                assert (
                    c.serials[0].max_active_reads == 1
                    and c.serials[0].active_reads == 0
                )
                assert len(c.serials) == len(c.journals) == 1 and c.reads == [
                    (c.profile_path, 65537)
                ]
                assert [
                    record.payload
                    for record in commits.records
                    if isinstance(record, RxBytesEvidence)
                ] == list(payloads)
            finally:
                for gate in gates:
                    gate.set()
                if delivery is not None:
                    delivery.cancel()
                    await asyncio.gather(delivery, return_exceptions=True)
        await _t017_readback(c.journal_path, c.journals[0].session_id, commits.records, v3=True)


@pytest.mark.parametrize(
    ("factory_name", "domain", "loss"),
    [
        (
            "basic_backend_fixture",
            {
                "domain_id": "host-observer-1",
                "observer": "host",
                "meaning": "observation",
                "unit": "nanosecond",
                "origin_id": "host-process-1",
            },
            {"kind": "upstream_loss_not_observable"},
        ),
        (
            "enhanced_backend_fixture",
            {
                "domain_id": "fixture-device-domain-1",
                "observer": "device",
                "meaning": "observation",
                "unit": "tick",
                "origin_id": "fixture-device-origin-1",
            },
            {
                "kind": "observer_reports_uart_loss",
                "observer_id": "fixture-device-uart-observer",
                "scope": "fixture-uart-rx-buffer",
            },
        ),
    ],
    ids=["basic-shaped", "enhanced-shaped"],
)
@pytest.mark.parametrize("ending", ["detach", "disconnect"])
@pytest.mark.asyncio
async def test_t017_identical_http_lifecycle_and_durable_binary_assertions_preserve_normalized_facts(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    factory_name: str,
    domain: dict[str, str],
    loss: dict[str, str],
    ending: str,
) -> None:
    c = t011_composition
    source = Path(__file__).parents[3] / "core/tests/fakes.py"
    spec = importlib.util.spec_from_file_location(
        "_t017_existing_backend_fixtures", source
    )
    assert spec is not None and spec.loader is not None
    module = cast(Any, importlib.util.module_from_spec(spec))
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    factory = getattr(module, factory_name)
    prepared = asyncio.Event()
    fixture: Any = None
    prepare_calls = 0
    commits = _T017Commits()
    envelope = ConnectionProvenanceSnapshot(
        1,
        "fixture/t017-opaque",
        37,
        (
            ProvenanceField("flag", True),
            ProvenanceField("nullable", None),
            ProvenanceField("number", 123),
            ProvenanceField("text", "opaque\x00é"),
        ),
    )

    async def edge(
        owner: ObservationRuntime, explicit_profile: str | Path, destination: str | Path
    ) -> RuntimeStatus:
        owner.status()
        resolved = resolve_profile(explicit_profile)
        assert isinstance(resolved, ResolvedDutProfile)

        async def prepare(profile: ResolvedDutProfile) -> PreparedObservationRun:
            nonlocal fixture, prepare_calls
            prepare_calls += 1
            journal = await sqlite_evidence.SqliteEvidenceJournal.create(
                destination, profile.session_policy
            )
            commits.trace.append("journal.created")
            fixture = factory()
            commits.trace.append("backend.constructed")
            original = fixture.connection.descriptor
            fixture.connection.descriptor = replace(
                original, connection_provenance=PersistedConnectionProvenance(envelope)
            )
            assert fixture.connection.descriptor.capabilities == original.capabilities
            assert (
                fixture.connection.descriptor.backend_observation_timestamp_domain
                == original.backend_observation_timestamp_domain
            )
            assert (
                fixture.connection.descriptor.loss_observability
                == original.loss_observability
            )
            fixture.backend.open_gate.allow.clear()
            prepared.set()
            return PreparedObservationRun(journal, fixture.backend)

        return await owner.attach(resolved, prepare)

    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            commits.install(patch)
            # Test composition substitution only: no Enhanced Profile selection
            # or lifecycle algorithm. Real resolution/runtime/Acquisition/journal.
            patch.setattr(observation_runtime, "attach_basic_observation", edge)
            patch.setattr(_t009_module(), "attach_basic_observation", edge)
            client = Client(body=_t011_body(c.profile_path, c.journal_path))
            delivery = submit(service, client, _ATTACH)
            try:
                await asyncio.wait_for(prepared.wait(), timeout=3.0)
                waiting = _t011_view(await service.request(_STATUS, "GET"), "attaching")
                assert waiting["session_id"] == c.journals[0].session_id.value
                assert (
                    waiting["acquisition"]["descriptor"] is None
                    and waiting["acquisition"]["provenance"] is None
                )
                assert not waiting["attach_admissible"] and not waiting["owner_settled"]
                busy_destination = c.journal_path.with_name("busy-not-created.sqlite3")
                _t011_error(
                    await service.request(
                        _ATTACH, "POST", _t011_body(c.profile_path, busy_destination)
                    ),
                    409,
                    "runtime",
                    "busy",
                )
                assert prepare_calls == 1 and not busy_destination.exists()
                fixture.backend.open_gate.allow.set()
                await finish_delivery(delivery)
                active = _t011_view(client, "active")
                start = await commits.next(0)
                assert isinstance(start, SegmentStartedEvidence)
                descriptor = active["acquisition"]["descriptor"]
                assert descriptor["capabilities"] == ["uart_receive"]
                assert descriptor["backend_observation_timestamp_domain"] == domain
                assert descriptor["loss_observability"] == loss
                assert descriptor["connection_provenance"] == {
                    "envelope_version": 1,
                    "backend_kind": "fixture/t017-opaque",
                    "backend_schema_version": 37,
                    "fields": [
                        {"name": "flag", "value": True},
                        {"name": "nullable", "value": None},
                        {"name": "number", "value": 123},
                        {"name": "text", "value": "opaque\x00é"},
                    ],
                }
                payloads = (bytes(range(256)) + b"\x00\xff", b"ambient\r\n\x80\x00")
                for sequence, payload in enumerate(payloads, start=1):
                    await fixture.connection.emit_rx(payload, timestamp=sequence * 10)
                    record = await commits.next(sequence)
                    assert (
                        isinstance(record, RxBytesEvidence)
                        and record.payload == payload
                    )
                    assert (
                        record.observed_at.domain_id == domain["domain_id"]
                        and record.observed_at.value == sequence * 10
                    )
                assert (
                    _t011_view(await service.request(_STATUS, "GET"), "active")
                    == active
                )
                if ending == "detach":
                    terminal = _t011_view(
                        await service.request(_DETACH, "POST"), "terminated"
                    )
                else:
                    await fixture.connection.disconnect("fixture observer link ended")
                    await asyncio.wait_for(commits.closed.wait(), timeout=3.0)
                    await flush()
                    terminal = _t011_view(
                        await service.request(_STATUS, "GET"), "terminated"
                    )
                end = await commits.next(3)
                assert isinstance(end, SegmentEndedEvidence)
                assert end.reason is (
                    SegmentEndReason.EXPLICIT_STOP
                    if ending == "detach"
                    else SegmentEndReason.DISCONNECTED
                )
                assert terminal["terminal_reason"] == (
                    "detached" if ending == "detach" else "disconnected"
                )
                assert terminal["stop_intent"] == (
                    "detach" if ending == "detach" else "none"
                )
                assert (
                    terminal["owner_settled"]
                    and terminal["physical_release_confirmed"]
                    and terminal["recorder_close_confirmed"]
                    and terminal["attach_admissible"]
                )
                assert (
                    terminal["primary_issue"] is None
                    and terminal["cleanup_issues"] == []
                )
                assert terminal["run_id"] == active["run_id"] == waiting["run_id"]
                assert (
                    terminal["session_id"]
                    == active["session_id"]
                    == waiting["session_id"]
                )
                assert terminal["profile"] == active["profile"] == waiting["profile"]
                assert (
                    terminal["acquisition"]["provenance"]
                    == active["acquisition"]["provenance"]
                )
                assert terminal["acquisition"]["descriptor"] == descriptor
                assert start.provenance.connection_provenance.to_snapshot() == envelope
                assert (
                    start.provenance.backend_observation_timestamp_domain
                    == fixture.connection.descriptor.backend_observation_timestamp_domain
                )
                assert (
                    start.provenance.loss_observability
                    == fixture.connection.descriptor.loss_observability
                )
                assert (
                    start.provenance.capabilities
                    == fixture.connection.descriptor.capabilities
                )
                assert all(
                    isinstance(
                        record,
                        (
                            SegmentStartedEvidence,
                            RxBytesEvidence,
                            ObserverLossEvidence,
                            SegmentEndedEvidence,
                        ),
                    )
                    and record.connection_id == start.connection_id
                    and record.segment_id == start.segment_id
                    for record in commits.records
                )
                assert (
                    commits.trace.index("journal.created")
                    < commits.trace.index("backend.constructed")
                    < commits.trace.index("committed:0")
                )
                assert commits.trace.index("committed:3") < commits.trace.index(
                    "recorder.close"
                )
                assert (
                    fixture.backend.open_calls
                    == fixture.connection.consumer_calls
                    == fixture.connection.close_calls
                    == commits.close_calls
                    == 1
                )
                assert (
                    _t011_view(await service.request(_DETACH, "POST"), "terminated")
                    == terminal
                )
                assert (
                    _t011_view(await service.request(_STATUS, "GET"), "terminated")
                    == terminal
                )
                assert fixture.backend.open_calls == fixture.connection.close_calls == 1
                assert c.serials == [] and prepare_calls == 1
            finally:
                if fixture is not None:
                    fixture.backend.open_gate.allow.set()
                delivery.cancel()
                await asyncio.gather(delivery, return_exceptions=True)
        await _t017_readback(c.journal_path, c.journals[0].session_id, commits.records)


@dataclass
class _T015Journal:
    fail_append: str | None = None
    fail_close: bool = False
    attempts: list[str] = field(default_factory=list)
    committed: list[EvidenceRecord] = field(default_factory=list)
    close_calls: int = 0
    closed: asyncio.Event = field(default_factory=asyncio.Event)

    def install(self, patch: pytest.MonkeyPatch) -> None:
        original_append = sqlite_evidence.SqliteEvidenceJournal.append
        original_close = sqlite_evidence.SqliteEvidenceJournal.close

        async def append(
            journal: sqlite_evidence.SqliteEvidenceJournal,
            pending: PendingEvidenceRecord,
        ) -> EvidenceRecord:
            kind = (
                "start"
                if isinstance(pending, PendingSegmentStartedEvidence)
                else "rx"
                if isinstance(pending, PendingRxBytesEvidence)
                else "end"
                if isinstance(pending, PendingSegmentEndedEvidence)
                else "other"
            )
            self.attempts.append(kind)
            if kind == self.fail_append:
                raise JournalFailure(
                    JournalOperation.APPEND,
                    JournalFailureKind.IO_FAILURE,
                    "private t015 append detail",
                )
            recorded = await original_append(journal, pending)
            self.committed.append(recorded)
            return recorded

        async def close(journal: sqlite_evidence.SqliteEvidenceJournal) -> None:
            self.close_calls += 1
            try:
                await original_close(journal)
                if self.fail_close:
                    # A failure returned after actual closure still supplies no
                    # positive recorder certainty to the normalized lifecycle.
                    raise JournalFailure(
                        JournalOperation.CLOSE,
                        JournalFailureKind.IO_FAILURE,
                        "private t015 close detail",
                    )
            finally:
                self.closed.set()

        patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "append", append)
        patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "close", close)


def _t015_cleanup(backend: bool, recorder: bool) -> list[dict[str, str]]:
    # Literal ordered normalized facts, never decoded from legacy failure kind.
    return {
        (False, False): [],
        (True, False): [{"source": "backend_close", "code": "close_failed"}],
        (False, True): [{"source": "recorder_close", "code": "io_failure"}],
        (True, True): [
            {"source": "backend_close", "code": "close_failed"},
            {"source": "recorder_close", "code": "io_failure"},
        ],
    }[(backend, recorder)]


async def _t015_stable_terminal(
    service: _T011Service,
    c: _T011Composition,
    journal: _T015Journal,
    expected: dict[str, Any],
) -> None:
    image = c.journal_path.read_bytes()
    before = (
        journal.close_calls,
        len(c.destinations),
        len(c.serials),
        tuple(fake.close_calls for fake in c.serials),
        tuple(journal.attempts),
    )
    for _ in range(3):
        assert (
            _t011_view(await service.request(_STATUS, "GET"), expected["state"])
            == expected
        )
        assert (
            _t011_view(await service.request(_DETACH, "POST"), expected["state"])
            == expected
        )
    if not expected["attach_admissible"]:
        destination = c.journal_path.with_name("blocked-after-failure.sqlite3")
        _t011_error(
            await service.request(
                _ATTACH, "POST", _t011_body(c.profile_path, destination)
            ),
            409,
            "runtime",
            "cleanup_unconfirmed",
        )
        assert not destination.exists()
    assert (
        journal.close_calls,
        len(c.destinations),
        len(c.serials),
        tuple(fake.close_calls for fake in c.serials),
        tuple(journal.attempts),
    ) == before
    assert c.journal_path.read_bytes() == image
    assert all(fake.active_reads == 0 for fake in c.serials)
    assert "private t015" not in str(expected)


@pytest.mark.parametrize(
    ("stage", "recorder_fails"),
    [
        ("create_io", False),
        ("existing", False),
        ("construct", False),
        ("construct", True),
    ],
)
@pytest.mark.asyncio
async def test_t015_preparation_failure_preserves_known_session_and_cleanup_uncertainty(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    stage: str,
    recorder_fails: bool,
) -> None:
    c = t011_composition
    journal = _T015Journal(fail_close=recorder_fails)
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            journal.install(patch)
            attempts: list[Path] = []
            if stage == "create_io":

                async def create(
                    cls: type[sqlite_evidence.SqliteEvidenceJournal],
                    path: str | Path,
                    policy: SessionPolicy,
                ) -> sqlite_evidence.SqliteEvidenceJournal:
                    del cls, policy
                    attempts.append(Path(path))
                    Path(path).write_bytes(b"retained failed-create artifact")
                    raise JournalFailure(
                        JournalOperation.CREATE,
                        JournalFailureKind.IO_FAILURE,
                        "private t015 create detail",
                    )

                patch.setattr(
                    sqlite_evidence.SqliteEvidenceJournal, "create_v3", classmethod(create)
                )
            elif stage == "existing":
                c.journal_path.write_bytes(b"existing destination must stay unchanged")
            else:

                def construct(*args: object, **kwargs: object) -> None:
                    del args, kwargs
                    raise RuntimeError("private t015 constructor detail")

                patch.setattr(basic_serial.BasicSerialBackend, "__init__", construct)
            view = _t011_view(
                await service.request(
                    _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
                ),
                "failed",
            )
            assert (
                view["terminal_reason"] == "startup_failure"
                and view["stop_intent"] == "none"
            )
            assert view["primary_issue"] == {
                "source": "preparation",
                "code": "journal_exists"
                if stage == "existing"
                else "io_failure"
                if stage == "create_io"
                else "internal_contract_failure",
            }
            assert view["cleanup_issues"] == _t015_cleanup(False, recorder_fails)
            assert (
                view["owner_settled"] is True
                and view["physical_release_confirmed"] is True
            )
            assert view["recorder_close_confirmed"] is (
                stage != "create_io" and not recorder_fails
            )
            assert view["attach_admissible"] is (
                stage != "create_io" and not recorder_fails
            )
            assert view["acquisition"] is None and c.serials == []
            if stage == "construct":
                assert (
                    view["session_id"] == c.journals[0].session_id.value
                    and journal.close_calls == 1
                )
            else:
                assert (
                    view["session_id"] is None
                    and c.journals == []
                    and journal.close_calls == 0
                )
            if stage == "create_io":
                assert attempts == [c.journal_path]
            await _t015_stable_terminal(service, c, journal, view)


@pytest.mark.parametrize("recorder_fails", [False, True])
@pytest.mark.asyncio
async def test_t015_failed_open_is_200_with_primary_separate_from_release_and_recorder_close(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    recorder_fails: bool,
) -> None:
    c = t011_composition
    c.open_error = OSError("private t015 open detail")
    journal = _T015Journal(fail_close=recorder_fails)
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            journal.install(patch)
            view = _t011_view(
                await service.request(
                    _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
                ),
                "failed",
            )
            assert (
                view["terminal_reason"] == "startup_failure"
                and view["stop_intent"] == "none"
            )
            assert view["primary_issue"] == {
                "source": "acquisition_start",
                "code": "transport_failure",
            }
            assert view["cleanup_issues"] == _t015_cleanup(False, recorder_fails)
            snapshot = view["acquisition"]
            assert (
                snapshot["terminal_trigger"]
                == snapshot["primary_failure_kind"]
                == "transport_failure"
            )
            assert snapshot["descriptor"] is None and snapshot["provenance"] is None
            assert snapshot["close_failed"] is False
            assert (
                snapshot["physical_release_confirmed"]
                is view["physical_release_confirmed"]
                is False
            )
            assert view["recorder_close_confirmed"] is not recorder_fails
            assert view["owner_settled"] is True and view["attach_admissible"] is False
            assert view["session_id"] == c.journals[0].session_id.value
            assert journal.attempts == [] and journal.close_calls == 1
            assert c.serials[0].close_calls == 1
            await _t015_stable_terminal(service, c, journal, view)


@pytest.mark.parametrize("backend_fails", [False, True])
@pytest.mark.parametrize("recorder_fails", [False, True])
@pytest.mark.asyncio
async def test_t015_initial_append_failure_keeps_descriptor_without_fabricated_committed_provenance(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    backend_fails: bool,
    recorder_fails: bool,
) -> None:
    c = t011_composition
    c.close_error = (
        OSError("private t015 backend close detail") if backend_fails else None
    )
    journal = _T015Journal(fail_append="start", fail_close=recorder_fails)
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            journal.install(patch)
            view = _t011_view(
                await service.request(
                    _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
                ),
                "failed",
            )
            assert (
                view["terminal_reason"] == "startup_failure"
                and view["stop_intent"] == "none"
            )
            assert view["primary_issue"] == {
                "source": "acquisition_start",
                "code": "recording_failure",
            }
            assert view["cleanup_issues"] == _t015_cleanup(
                backend_fails, recorder_fails
            )
            snapshot = view["acquisition"]
            assert (
                snapshot["terminal_trigger"]
                == snapshot["primary_failure_kind"]
                == "recording_failure"
            )
            assert snapshot["descriptor"]["capabilities"] == ["uart_receive"]
            assert snapshot["provenance"] is None
            assert snapshot["close_failed"] is backend_fails
            assert view["physical_release_confirmed"] is not backend_fails
            assert view["recorder_close_confirmed"] is not recorder_fails
            assert view["attach_admissible"] is (
                not backend_fails and not recorder_fails
            )
            assert (
                view["owner_settled"] is True
                and view["session_id"] == c.journals[0].session_id.value
            )
            assert journal.attempts == ["start"] and journal.committed == []
            assert journal.close_calls == c.serials[0].close_calls == 1
            await _t015_stable_terminal(service, c, journal, view)


@pytest.mark.parametrize(
    ("scenario", "backend_fails", "recorder_fails", "primary", "trigger", "reason"),
    [
        (
            "rx_append",
            False,
            False,
            "recording_failure",
            "recording_failure",
            "acquisition_failure",
        ),
        (
            "rx_append",
            True,
            True,
            "recording_failure",
            "recording_failure",
            "acquisition_failure",
        ),
        (
            "read_failure",
            False,
            False,
            "transport_failure",
            "transport_failure",
            "acquisition_failure",
        ),
        (
            "transport_then_append",
            False,
            False,
            "transport_failure",
            "transport_failure",
            "acquisition_failure",
        ),
        (
            "transport_then_append",
            True,
            True,
            "transport_failure",
            "transport_failure",
            "acquisition_failure",
        ),
        ("disconnect", False, False, None, "disconnected", "disconnected"),
        (
            "disconnect_then_append",
            True,
            True,
            "recording_failure",
            "disconnected",
            "disconnected",
        ),
        (
            "final_append",
            False,
            False,
            "recording_failure",
            "recording_failure",
            "acquisition_failure",
        ),
    ],
)
@pytest.mark.asyncio
async def test_t015_autonomous_or_final_failure_preserves_cause_primary_and_cleanup_without_reconnect(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    scenario: str,
    backend_fails: bool,
    recorder_fails: bool,
    primary: str | None,
    trigger: str,
    reason: str,
) -> None:
    c = t011_composition
    c.close_error = (
        OSError("private t015 backend close detail") if backend_fails else None
    )
    journal = _T015Journal(
        fail_append="rx"
        if scenario == "rx_append"
        else "end"
        if scenario
        in {"transport_then_append", "disconnect_then_append", "final_append"}
        else None,
        fail_close=recorder_fails,
    )
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            journal.install(patch)
            if scenario != "final_append":
                original_init = basic_serial.BasicSerialBackend.__init__

                def construct(
                    self: basic_serial.BasicSerialBackend,
                    selector: basic_serial.SerialDeviceSelector,
                    configuration: basic_serial.SerialConfiguration,
                    line_intent: basic_serial.SerialOpenLineIntent,
                ) -> None:
                    original_init(self, selector, configuration, line_intent)
                    fake = c.serials[-1]
                    original_read = fake.read

                    def read(size: int = -1) -> bytes:
                        original_read(size)  # Retain the existing fake's gate/counters.
                        if scenario == "rx_append":
                            return b"\x00\xfftrigger failed append"
                        raise OSError(
                            errno.ENODEV
                            if scenario.startswith("disconnect")
                            else errno.EINVAL,
                            "private t015 read detail",
                        )

                    fake.read = read

                patch.setattr(basic_serial.BasicSerialBackend, "__init__", construct)
            active = _t011_view(
                await service.request(
                    _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
                ),
                "active",
            )
            assert [record.sequence for record in journal.committed] == [0]
            if scenario == "final_append":
                response = await service.request(_DETACH, "POST")
            else:
                c.serials[0]._read_gates[
                    0
                ].set()  # Test dependency only, no physical I/O.
                await asyncio.wait_for(journal.closed.wait(), timeout=3.0)
                await flush()
                response = await service.request(_STATUS, "GET")
            failed = primary is not None or backend_fails or recorder_fails
            view = _t011_view(response, "failed" if failed else "terminated")
            assert (
                view["run_id"] == active["run_id"]
                and view["session_id"] == active["session_id"]
            )
            assert view["profile"] == active["profile"]
            assert view["terminal_reason"] == reason
            assert view["stop_intent"] == (
                "detach" if scenario == "final_append" else "none"
            )
            assert view["primary_issue"] == (
                None if primary is None else {"source": "acquisition", "code": primary}
            )
            assert view["cleanup_issues"] == _t015_cleanup(
                backend_fails, recorder_fails
            )
            snapshot = view["acquisition"]
            assert (
                snapshot["terminal_trigger"] == trigger
                and snapshot["primary_failure_kind"] == primary
            )
            assert snapshot["close_failed"] is backend_fails
            assert snapshot["provenance"] == active["acquisition"]["provenance"]
            assert (
                view["physical_release_confirmed"]
                is snapshot["physical_release_confirmed"]
                is (not backend_fails)
            )
            assert view["recorder_close_confirmed"] is not recorder_fails
            assert view["attach_admissible"] is (
                not backend_fails and not recorder_fails
            )
            assert view["owner_settled"] is True
            assert journal.close_calls == c.serials[0].close_calls == 1
            assert c.serials[0].max_active_reads == 1
            assert [record.sequence for record in journal.committed] == (
                [0, 1] if scenario in {"disconnect", "read_failure"} else [0]
            )
            await _t015_stable_terminal(service, c, journal, view)


@pytest.mark.parametrize("backend_fails", [False, True])
@pytest.mark.parametrize("recorder_fails", [False, True])
@pytest.mark.asyncio
async def test_t015_close_only_failure_never_becomes_primary_transport_failure_or_cleanup_retry(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    backend_fails: bool,
    recorder_fails: bool,
) -> None:
    c = t011_composition
    c.close_error = (
        OSError("private t015 backend close detail") if backend_fails else None
    )
    journal = _T015Journal(fail_close=recorder_fails)
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            journal.install(patch)
            active = _t011_view(
                await service.request(
                    _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
                ),
                "active",
            )
            view = _t011_view(
                await service.request(_DETACH, "POST"),
                "failed" if backend_fails or recorder_fails else "terminated",
            )
            assert (
                view["terminal_reason"] == "detached"
                and view["stop_intent"] == "detach"
            )
            assert view["primary_issue"] is None
            assert view["cleanup_issues"] == _t015_cleanup(
                backend_fails, recorder_fails
            )
            assert view["acquisition"]["primary_failure_kind"] is None
            assert view["acquisition"]["terminal_trigger"] == "explicit_stop"
            assert view["acquisition"]["close_failed"] is backend_fails
            assert (
                view["acquisition"]["provenance"] == active["acquisition"]["provenance"]
            )
            assert view["physical_release_confirmed"] is not backend_fails
            assert view["recorder_close_confirmed"] is not recorder_fails
            assert view["attach_admissible"] is (
                not backend_fails and not recorder_fails
            )
            assert view["session_id"] == active["session_id"]
            assert journal.close_calls == c.serials[0].close_calls == 1
            await _t015_stable_terminal(service, c, journal, view)


@pytest.mark.parametrize("stage", ["open", "start_append"])
@pytest.mark.asyncio
async def test_t015_repeated_client_cancellation_preserves_later_startup_failure_and_retained_journal(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    stage: str,
) -> None:
    c = t011_composition
    c.open_error = OSError("private t015 open detail") if stage == "open" else None
    journal = _T015Journal(fail_append="start" if stage == "start_append" else None)
    entered, release = asyncio.Event(), asyncio.Event()
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            journal.install(patch)
            probe = CoreCalls()
            probe.install(patch)
            if stage == "open":
                original_open = basic_serial.BasicSerialBackend.open

                async def opened(backend: basic_serial.BasicSerialBackend) -> Any:
                    entered.set()
                    await release.wait()
                    return await original_open(backend)

                patch.setattr(basic_serial.BasicSerialBackend, "open", opened)
            else:
                original_append = sqlite_evidence.SqliteEvidenceJournal.append

                async def append(
                    recorder: sqlite_evidence.SqliteEvidenceJournal,
                    pending: PendingEvidenceRecord,
                ) -> EvidenceRecord:
                    entered.set()
                    await release.wait()
                    return await original_append(recorder, pending)

                patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "append", append)
            client = Client(body=_t011_body(c.profile_path, c.journal_path))
            delivery = submit(service, client, _ATTACH)
            try:
                call = await called(probe, 1, delivery, client)
                await asyncio.wait_for(entered.wait(), timeout=3.0)
                assert service.runtime.status().state is RuntimeState.ATTACHING
                for _ in range(3):
                    delivery.cancel()
                await finish_delivery(delivery)
                assert delivery.cancelled() and client.messages == []
                assert service.runtime.status().stop_intent is RuntimeStopIntent.NONE
                release.set()
                await asyncio.wait_for(call.finished.wait(), timeout=3.0)
                view = _t011_view(await service.request(_STATUS, "GET"), "failed")
                assert (
                    view["terminal_reason"] == "startup_failure"
                    and view["stop_intent"] == "none"
                )
                assert view["primary_issue"] == {
                    "source": "acquisition_start",
                    "code": "transport_failure"
                    if stage == "open"
                    else "recording_failure",
                }
                assert view["cleanup_issues"] == [] and view["owner_settled"] is True
                assert view["physical_release_confirmed"] is (stage != "open")
                assert view["recorder_close_confirmed"] is True
                assert view["session_id"] == c.journals[0].session_id.value
                assert len(probe.calls) == 1
                await _t015_stable_terminal(service, c, journal, view)
            finally:
                release.set()
                delivery.cancel()
                await asyncio.gather(delivery, return_exceptions=True)
                for completed in probe.calls:
                    await asyncio.wait_for(completed.finished.wait(), timeout=3.0)


@pytest.mark.parametrize("path", [_ATTACH, _DETACH], ids=["attach", "detach"])
@pytest.mark.asyncio
async def test_t014_observed_disconnect_stops_delivery_but_preserves_registered_pending_work(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    path: str,
) -> None:
    c = t011_composition
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            probe = CoreCalls(hold_attach=True, hold_detach=True)
            probe.install(patch)
            client = Client(
                body=_t011_body(c.profile_path, c.journal_path)
                if path == _ATTACH
                else b""
            )
            delivery = submit(service, client, path)
            try:
                call = await called(probe, 1, delivery, client)
                assert call.task() is not delivery
                client.disconnected.set()
                await finish_delivery(delivery)
                assert delivery.cancelled() and client.messages == []
                operation = call.task()
                assert operation is not None and not operation.done()
                assert operation.cancelling() == 0
                assert c.reads == [] and c.destinations == []
                assert service.runtime.status().stop_intent is RuntimeStopIntent.NONE
                call.release()
                await asyncio.wait_for(call.finished.wait(), timeout=3.0)
                expected = (
                    RuntimeState.ACTIVE if path == _ATTACH else RuntimeState.INACTIVE
                )
                assert service.runtime.status().state is expected
                assert service.runtime.status().stop_intent is RuntimeStopIntent.NONE
                assert len(probe.calls) == 1
            finally:
                probe.release()
                delivery.cancel()
                await asyncio.gather(delivery, return_exceptions=True)
                for completed in probe.calls:
                    await asyncio.wait_for(completed.finished.wait(), timeout=3.0)


class _WeakStatus(RuntimeStatus):
    """Same validated immutable fields, weak-referenceable for result retention."""


@dataclass
class Client(Exchange):
    before_body: str | None = None
    body_entered: asyncio.Event = field(default_factory=asyncio.Event)
    disconnected: asyncio.Event = field(default_factory=asyncio.Event)
    publication: asyncio.Event = field(default_factory=asyncio.Event)
    publication_gate: asyncio.Event = field(default_factory=asyncio.Event)
    hold_publication: bool = False
    send_fault: str | None = None

    async def receive(self) -> Message:
        if self.receives == 0:
            self.body_entered.set()
            if self.before_body == "cancel":
                pending: asyncio.Future[Message] = (
                    asyncio.get_running_loop().create_future()
                )
                return await pending
            if self.before_body == "disconnect":
                self.receives += 1
                return {"type": "http.disconnect"}
            if self.before_body == "pending-cancel":
                task = asyncio.current_task()
                assert task is not None
                task.cancel()
            return await super().receive()
        await self.disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(self, message: Message) -> None:
        await super().send(message)
        if message["type"] == "http.response.start":
            self.publication.set()
            if self.hold_publication and message["status"] == 200:
                await self.publication_gate.wait()
        if self.send_fault == message["type"]:
            raise OSError("private delivery failure")


def submit(service: _T011Service, client: Client, path: str) -> asyncio.Task[None]:
    async def deliver() -> None:
        await service.app(
            _scope(
                service.config,
                _headers(service.config, service.token)
                + [(b"content-type", b"application/json")],
                path=path,
                method="POST",
            ),
            client.receive,
            client.send,
        )

    return asyncio.create_task(deliver())


@dataclass
class Call:
    action: str
    task: weakref.ReferenceType[asyncio.Task[Any]]
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    gate: weakref.ReferenceType[asyncio.Future[None]] | None = None

    def release(self) -> None:
        future = None if self.gate is None else self.gate()
        if future is not None and not future.done():
            future.set_result(None)


@dataclass
class CoreCalls:
    """Passive boundary probe; holds no strong operation-task/result/path references."""

    hold_attach: bool = False
    hold_detach: bool = False
    reject_attach: bool = False
    track_values: bool = False
    calls: list[Call] = field(default_factory=list)
    values: list[weakref.ReferenceType[Any]] = field(default_factory=list)
    entered: asyncio.Event = field(default_factory=asyncio.Event)

    def begin(self, action: str) -> Call:
        task = asyncio.current_task()
        assert task is not None
        call = Call(action, weakref.ref(task))
        self.calls.append(call)
        self.entered.set()
        return call

    async def pause(self, call: Call) -> None:
        hold = self.hold_attach if call.action == "attach" else self.hold_detach
        if hold:
            # A future/task cycle with no external strong root. A registry must
            # retain it after delivery cancellation; an Event waiter could mask
            # an unowned task by accidentally supplying a strong reference.
            pending: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            call.gate = weakref.ref(pending)
            await pending

    def install(self, patch: pytest.MonkeyPatch) -> None:
        original_attach = observation_runtime.attach_basic_observation
        original_detach = ObservationRuntime.detach

        async def attach(
            runtime: ObservationRuntime, profile: str | Path, journal: str | Path
        ) -> RuntimeStatus:
            call = self.begin("attach")
            try:
                await self.pause(call)
                if self.reject_attach:
                    failure = RuntimeRejectedError(RuntimeRejectedKind.INVALID_REQUEST)
                    if self.track_values:
                        self.values.append(weakref.ref(failure))
                    raise failure
                return self.result(await original_attach(runtime, profile, journal))
            finally:
                call.finished.set()

        async def detach(runtime: ObservationRuntime) -> RuntimeStatus:
            call = self.begin("detach")
            try:
                await self.pause(call)
                return self.result(await original_detach(runtime))
            finally:
                call.finished.set()

        patch.setattr(observation_runtime, "attach_basic_observation", attach)
        module = _t009_module()
        if hasattr(module, "attach_basic_observation"):
            patch.setattr(module, "attach_basic_observation", attach)
        patch.setattr(ObservationRuntime, "detach", detach)

    def result(self, status: RuntimeStatus) -> RuntimeStatus:
        if not self.track_values:
            return status
        # Core legitimately keeps its own last status. A field-identical return
        # value lets this test detect delivery retaining completed results without
        # mistaking that authoritative Core snapshot for a service history.
        returned = _WeakStatus(
            **{item.name: getattr(status, item.name) for item in fields(RuntimeStatus)}
        )
        self.values.append(weakref.ref(returned))
        return returned

    def release(self) -> None:
        for call in self.calls:
            call.release()


async def called(
    probe: CoreCalls, count: int, delivery: asyncio.Task[None], client: Client
) -> Call:
    async def notice() -> None:
        while len(probe.calls) < count:
            probe.entered.clear()
            await probe.entered.wait()

    waiter = asyncio.create_task(notice())
    try:
        await asyncio.wait(
            {waiter, delivery}, timeout=3.0, return_when=asyncio.FIRST_COMPLETED
        )
        status = client.status if delivery.done() and client.messages else None
        assert len(probe.calls) >= count, (
            f"HTTP {status} ended before mutation submission"
        )
        return probe.calls[count - 1]
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


async def finish_delivery(delivery: asyncio.Task[None]) -> None:
    done, _ = await asyncio.wait({delivery}, timeout=3.0)
    assert delivery in done, "HTTP delivery remained tied to pending Core work"
    await asyncio.gather(delivery, return_exceptions=True)


async def flush() -> None:
    # Deterministic loop barriers allow done callbacks to consume/remove entries.
    for _ in range(3):
        barrier: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(barrier.set_result, None)
        await barrier


@pytest.mark.parametrize("path", [_ATTACH, _DETACH], ids=["attach", "detach"])
@pytest.mark.parametrize("mode", ["cancel", "disconnect", "pending-cancel"])
@pytest.mark.asyncio
async def test_t012_observed_pre_registration_cancel_or_disconnect_submits_nothing(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    path: str,
    mode: str,
) -> None:
    c = t011_composition
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            probe = CoreCalls()
            probe.install(patch)
            client = Client(
                body=_t011_body(c.profile_path, c.journal_path)
                if path == _ATTACH
                else b"",
                before_body=mode,
            )
            delivery = submit(service, client, path)
            try:
                await asyncio.wait_for(client.body_entered.wait(), timeout=3.0)
                if mode == "cancel":
                    delivery.cancel()
                await finish_delivery(delivery)
                assert probe.calls == []
                assert service.runtime.status().state is RuntimeState.INACTIVE
                assert c.reads == [] and c.destinations == [] and c.serials == []
                if mode == "disconnect":
                    assert client.messages == []
            finally:
                delivery.cancel()
                await asyncio.gather(delivery, return_exceptions=True)


@pytest.mark.parametrize("path", [_ATTACH, _DETACH], ids=["attach", "detach"])
@pytest.mark.asyncio
async def test_t012_registration_before_first_yield_keeps_uninvoked_work_owned_after_cancel_and_gc(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    path: str,
) -> None:
    c = t011_composition
    loop = asyncio.get_running_loop()
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            probe = CoreCalls(hold_attach=True, hold_detach=True)
            probe.install(patch)
            client = Client(
                body=_t011_body(c.profile_path, c.journal_path)
                if path == _ATTACH
                else b""
            )
            delivery: asyncio.Task[None] | None = submit(service, client, path)
            previous = loop.get_task_factory()
            cancelled = asyncio.Event()

            def factory(
                owner_loop: asyncio.AbstractEventLoop,
                coro: Coroutine[Any, Any, Any],
                **kwargs: Any,
            ) -> asyncio.Future[Any]:
                if asyncio.current_task() is delivery and not cancelled.is_set():

                    def cancel_http() -> None:
                        cancelled.set()
                        if delivery is not None:
                            delivery.cancel()

                    # Queued before the new child task's first execution. The
                    # request can finish atomic registration before yielding.
                    owner_loop.call_soon(cancel_http)
                return (
                    asyncio.Task(coro, loop=owner_loop, **kwargs)
                    if previous is None
                    else previous(owner_loop, coro, **kwargs)
                )

            loop.set_task_factory(factory)
            try:
                assert delivery is not None
                call = await called(probe, 1, delivery, client)
                assert cancelled.is_set()
                assert call.task() is not delivery, "mutation ran in HTTP delivery task"
                await finish_delivery(delivery)
                assert delivery.cancelled()
                loop.set_task_factory(previous)
                delivery = None
                await flush()
                gc.collect()
                assert call.task() is not None, (
                    "registered operation lost its strong owner"
                )
                assert c.reads == [] and c.destinations == []
                assert service.runtime.status().stop_intent is RuntimeStopIntent.NONE
                call.release()
                await asyncio.wait_for(call.finished.wait(), timeout=3.0)
                status = service.runtime.status()
                assert status.state is (
                    RuntimeState.ACTIVE if path == _ATTACH else RuntimeState.INACTIVE
                )
                assert status.stop_intent is RuntimeStopIntent.NONE
                assert len(probe.calls) == 1
            finally:
                loop.set_task_factory(previous)
                probe.release()
                if delivery is not None:
                    delivery.cancel()
                    await asyncio.gather(delivery, return_exceptions=True)
                for call in probe.calls:
                    await asyncio.wait_for(call.finished.wait(), timeout=3.0)


@pytest.mark.parametrize("cancel_count", [1, 3])
@pytest.mark.asyncio
async def test_t012_attach_delivery_cancel_during_startup_never_creates_runtime_stop_intent(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    cancel_count: int,
) -> None:
    c = t011_composition
    entered, release = asyncio.Event(), asyncio.Event()
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            probe = CoreCalls()
            probe.install(patch)
            original = sqlite_evidence.SqliteEvidenceJournal.create_v3

            async def create(
                cls: type[sqlite_evidence.SqliteEvidenceJournal],
                path: str | Path,
                policy: SessionPolicy,
            ) -> sqlite_evidence.SqliteEvidenceJournal:
                del cls
                entered.set()
                await release.wait()
                return await original(path, policy)

            patch.setattr(
                sqlite_evidence.SqliteEvidenceJournal, "create_v3", classmethod(create)
            )
            client = Client(body=_t011_body(c.profile_path, c.journal_path))
            delivery = submit(service, client, _ATTACH)
            try:
                call = await called(probe, 1, delivery, client)
                await asyncio.wait_for(entered.wait(), timeout=3.0)
                assert service.runtime.status().state is RuntimeState.ATTACHING
                for _ in range(cancel_count):
                    delivery.cancel()
                await finish_delivery(delivery)
                assert delivery.cancelled()
                assert service.runtime.status().stop_intent is RuntimeStopIntent.NONE
                release.set()
                await asyncio.wait_for(call.finished.wait(), timeout=3.0)
                assert service.runtime.status().state is RuntimeState.ACTIVE
                assert service.runtime.status().stop_intent is RuntimeStopIntent.NONE
                assert len(c.journals) == len(c.serials) == 1
            finally:
                release.set()
                probe.release()
                delivery.cancel()
                await asyncio.gather(delivery, return_exceptions=True)
                for completed in probe.calls:
                    await asyncio.wait_for(completed.finished.wait(), timeout=3.0)


@pytest.mark.parametrize("cancel_count", [1, 3])
@pytest.mark.asyncio
async def test_t012_detach_delivery_cancel_leaves_explicit_stop_and_joined_cleanup_unchanged(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    cancel_count: int,
) -> None:
    c = t011_composition
    entered, release = asyncio.Event(), asyncio.Event()
    async with _t011_service(account_home, monkeypatch, c) as service:
        await observation_runtime.attach_basic_observation(
            service.runtime, c.profile_path, c.journal_path
        )
        with monkeypatch.context() as patch:
            probe = CoreCalls()
            probe.install(patch)
            original = sqlite_evidence.SqliteEvidenceJournal.close

            async def close(journal: sqlite_evidence.SqliteEvidenceJournal) -> None:
                entered.set()
                await release.wait()
                await original(journal)

            patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "close", close)
            client = Client()
            delivery = submit(service, client, _DETACH)
            try:
                call = await called(probe, 1, delivery, client)
                await asyncio.wait_for(entered.wait(), timeout=3.0)
                assert service.runtime.status().state is RuntimeState.DETACHING
                for _ in range(cancel_count):
                    delivery.cancel()
                await finish_delivery(delivery)
                assert delivery.cancelled()
                assert service.runtime.status().stop_intent is RuntimeStopIntent.DETACH
                assert service.runtime.status().owner_settled is False
                release.set()
                await asyncio.wait_for(call.finished.wait(), timeout=3.0)
                terminal = service.runtime.status()
                assert (
                    terminal.state is RuntimeState.TERMINATED
                    and terminal.attach_admissible
                )
                assert terminal.stop_intent is RuntimeStopIntent.DETACH
                assert c.serials[0].close_calls == 1
            finally:
                release.set()
                delivery.cancel()
                await asyncio.gather(delivery, return_exceptions=True)
                for completed in probe.calls:
                    await asyncio.wait_for(completed.finished.wait(), timeout=3.0)


@pytest.mark.parametrize("loss", ["cancel", "disconnect", "send-start", "send-body"])
@pytest.mark.asyncio
async def test_t012_lost_active_response_does_not_stop_or_rollback_observation(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    loss: str,
) -> None:
    c = t011_composition
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            probe = CoreCalls()
            probe.install(patch)
            client = Client(
                body=_t011_body(c.profile_path, c.journal_path),
                hold_publication=loss in {"cancel", "disconnect"},
                send_fault="http.response.start"
                if loss == "send-start"
                else "http.response.body"
                if loss == "send-body"
                else None,
            )
            delivery = submit(service, client, _ATTACH)
            try:
                call = await called(probe, 1, delivery, client)
                await asyncio.wait_for(client.publication.wait(), timeout=3.0)
                assert (
                    client.status == 200
                    and service.runtime.status().state is RuntimeState.ACTIVE
                )
                if loss == "cancel":
                    delivery.cancel()
                elif loss == "disconnect":
                    client.disconnected.set()
                    client.publication_gate.set()
                await finish_delivery(delivery)
                assert call.finished.is_set() and len(probe.calls) == 1
                active = _t011_view(await service.request(_STATUS, "GET"), "active")
                assert (
                    active["stop_intent"] == "none"
                    and active["terminal_reason"] is None
                )
                assert (
                    active["owner_settled"] is False and c.serials[0].close_calls == 0
                )
            finally:
                client.publication_gate.set()
                delivery.cancel()
                await asyncio.gather(delivery, return_exceptions=True)
                for completed in probe.calls:
                    await asyncio.wait_for(completed.finished.wait(), timeout=3.0)


@pytest.mark.parametrize("mixed", [False, True], ids=["attach-only", "mixed"])
@pytest.mark.asyncio
async def test_t012_eight_pending_mutations_reject_ninth_before_profile_and_reuse_completed_slot(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    mixed: bool,
) -> None:
    c = t011_composition
    deliveries: list[asyncio.Task[None]] = []
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            probe = CoreCalls(hold_attach=True, hold_detach=True)
            probe.install(patch)
            try:
                for index in range(8):
                    path = _DETACH if mixed and index % 2 == 0 else _ATTACH
                    client = Client(
                        body=_t011_body(
                            c.profile_path,
                            c.journal_path.with_name(f"pending-{index}.sqlite3"),
                        )
                        if path == _ATTACH
                        else b""
                    )
                    request = submit(service, client, path)
                    deliveries.append(request)
                    call = await called(probe, index + 1, request, client)
                    assert call.task() is not request
                assert c.reads == [] and c.destinations == []
                denied = await service.request(
                    _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
                )
                _t011_error(denied, 503, "service", "operation_capacity")
                assert len(probe.calls) == 8 and c.reads == [] and c.destinations == []
                probe.calls[0].release()
                await finish_delivery(deliveries[0])
                await flush()
                replacement = Client()
                request = submit(service, replacement, _DETACH)
                deliveries.append(request)
                await called(probe, 9, request, replacement)
                again = await service.request(
                    _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
                )
                _t011_error(again, 503, "service", "operation_capacity")
                assert len(probe.calls) == 9
            finally:
                probe.release()
                for request in deliveries:
                    request.cancel()
                await asyncio.gather(*deliveries, return_exceptions=True)
                for call in probe.calls:
                    await asyncio.wait_for(call.finished.wait(), timeout=3.0)


@pytest.mark.asyncio
async def test_t012_one_operation_error_does_not_cancel_sibling_work(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    c = t011_composition
    async with _t011_service(account_home, monkeypatch, c) as service:
        with monkeypatch.context() as patch:
            probe = CoreCalls(hold_detach=True, reject_attach=True)
            probe.install(patch)
            client = Client()
            sibling = submit(service, client, _DETACH)
            try:
                call = await called(probe, 1, sibling, client)
                rejected = await service.request(
                    _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
                )
                _t011_error(rejected, 422, "runtime", "invalid_request")
                assert len(probe.calls) == 2
                sibling_task = call.task()
                assert sibling_task is not None and not sibling_task.done()
                assert not sibling_task.cancelling()
                call.release()
                await finish_delivery(sibling)
                assert service.runtime.status().state is RuntimeState.INACTIVE
            finally:
                probe.release()
                sibling.cancel()
                await asyncio.gather(sibling, return_exceptions=True)
                for call in probe.calls:
                    await asyncio.wait_for(call.finished.wait(), timeout=3.0)


@pytest.mark.parametrize("reject", [False, True], ids=["result", "exception"])
@pytest.mark.asyncio
async def test_t012_lost_delivery_results_and_exceptions_are_consumed_without_task_history_or_replay(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    reject: bool,
) -> None:
    c = t011_composition
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    unhandled: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda owner, context: unhandled.append(context))
    try:
        async with _t011_service(account_home, monkeypatch, c) as service:
            with monkeypatch.context() as patch:
                probe = CoreCalls(
                    hold_attach=True,
                    hold_detach=True,
                    reject_attach=reject,
                    track_values=True,
                )
                probe.install(patch)
                path = _ATTACH if reject else _DETACH
                for index in range(12):
                    client = Client(
                        body=_t011_body(c.profile_path, c.journal_path)
                        if reject
                        else b""
                    )
                    delivery = submit(service, client, path)
                    try:
                        call = await called(probe, index + 1, delivery, client)
                        assert call.task() is not delivery
                        delivery.cancel()
                        await finish_delivery(delivery)
                        call.release()
                        await asyncio.wait_for(call.finished.wait(), timeout=3.0)
                    finally:
                        probe.release()
                        delivery.cancel()
                        await asyncio.gather(delivery, return_exceptions=True)
                    del delivery
                    await flush()
                    gc.collect()
                    assert all(
                        previous_call.task() is None for previous_call in probe.calls
                    ), "completed operation task references accumulated"
                    assert len(probe.values) == index + 1
                    assert all(value() is None for value in probe.values), (
                        "completed results/exceptions accumulated"
                    )
                    assert unhandled == [], (
                        "operation exceptions/results were not consumed"
                    )
                    assert len(probe.calls) == index + 1, (
                        "request was replayed or deduplicated"
                    )
                    view = _t011_view(await service.request(_STATUS, "GET"), "inactive")
                    assert view["run_id"] is None and view["profile"] is None
                assert c.reads == [] and c.destinations == []
    finally:
        loop.set_exception_handler(previous)


@pytest.mark.parametrize("fault", ["none", "close", "partial_open", "unexpected_open"])
def test_008_t018_read_cleanup_is_required_for_clean_marker_with_capture_facts_unchanged(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    fault: str,
) -> None:
    from dutchmate_core.adapters import terminal_evidence
    from dutchmate_core.evidence_access import EvidenceSourceOpenFailure

    c = t011_composition
    launch = _T021Launch(account_home, c)
    original_open = terminal_evidence.open_terminal_reader

    class CloseFault:
        def __init__(self, reader: Any) -> None:
            self.reader = reader
            self.session_id = reader.session_id
            self.policy = reader.policy

        async def resolve_record(self, reference: Any) -> Any:
            return await self.reader.resolve_record(reference)

        async def retrieve(self, request: Any) -> Any:
            return await self.reader.retrieve(request)

        async def close(self) -> None:
            await self.reader.close()
            raise JournalFailure(JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE)

    async def opener(target: Any) -> Any:
        reader = await original_open(target)
        if fault == "close":
            return CloseFault(reader)
        if fault in {"partial_open", "unexpected_open"}:
            # Native resources are cleaned to avoid harness leaks; the owner has
            # either an explicit uncertain acknowledgment or no acknowledgment.
            await reader.close()
            if fault == "partial_open":
                raise EvidenceSourceOpenFailure(
                    JournalFailure(
                        JournalOperation.OPEN, JournalFailureKind.IO_FAILURE
                    ),
                    False,
                )
            raise RuntimeError("test-only unexpected opener fault")
        return reader

    monkeypatch.setattr(observation_runtime, "open_terminal_reader", opener)

    async def terminal_read_then_stop(http: Any, service: _T011Service) -> None:
        del http
        _t011_view(
            await service.request(
                _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
            ),
            "active",
        )
        terminal = await service.runtime.detach()
        assert terminal.session_id is not None
        assert terminal.owner_settled and terminal.physical_release_confirmed
        assert terminal.recorder_close_confirmed and terminal.attach_admissible
        request = EvidenceRetrievalRequest(terminal.session_id, 10, 16384)
        if fault == "none":
            report = await service.runtime.read_page(request)
            assert report.run_id == terminal.run_id
        else:
            expected = RuntimeError if fault == "unexpected_open" else JournalFailure
            with pytest.raises(expected):
                await service.runtime.read_page(request)
        assert service.runtime.evidence_read_cleanup_confirmed is (fault == "none")
        assert service.runtime.status() == terminal
        launch.emit()

    launch.scenario = terminal_read_then_stop
    launch.install(monkeypatch)
    if fault == "none":
        _t021_server().run_service(ServiceConfig(8765))
    else:
        with pytest.raises(BootstrapFailure) as caught:
            _t021_server().run_service(ServiceConfig(8765))
        assert caught.value.kind is BootstrapFailureKind.TEARDOWN_INCOMPLETE
    marker = json.loads((launch.root / "owner.json").read_bytes())
    assert marker == {"version": 1, "cleanup_confirmed": fault == "none"}
    assert ("marker.true" in launch.trace) is (fault == "none")
    assert not (launch.root / "credential").exists()
    assert all(sock.released for sock in launch.sockets)
    final = launch.settled[id(launch.runtimes[0])]
    assert final.owner_settled and final.physical_release_confirmed
    assert final.recorder_close_confirmed and final.attach_admissible
