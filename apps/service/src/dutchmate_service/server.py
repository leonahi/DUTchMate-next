"""Controlled local listener and joined, conservative ownership teardown."""

import asyncio
import logging
import signal
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from threading import current_thread, main_thread
from types import FrameType

import uvicorn
from uvicorn.lifespan.on import LifespanOn

from dutchmate_service.app import _LaunchContext, _settle_task, create_app
from dutchmate_service.bootstrap import (
    BootstrapFailure,
    BootstrapFailureKind,
    PrivateBootstrap,
    ServiceConfig,
)


class _StartupStopped(Exception):
    """Internal control flow: lifespan entered but HTTP must never become ready."""


class _ControlledServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, context: _LaunchContext) -> None:
        super().__init__(config)
        self._context = context
        self._lifespan_entered = False
        self._lifespan_closed = False
        self.cleanup_failed = False
        # Uvicorn normally initializes this only after lifespan startup. A
        # latched startup stop still needs its listener-free shutdown drain.
        self.servers: list[asyncio.Server] = []

    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        # run_service owns handlers from before bootstrap through guard release.
        # Uvicorn's second-SIGINT force_exit/signal-replay path is unsupported.
        yield

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        del sig, frame
        self._context.request_stop()
        self.should_exit = True

    async def serve(self, sockets: list[socket.socket] | None = None) -> None:
        context = self._context
        server = self

        class CheckedLifespan(LifespanOn):
            async def startup(self) -> None:
                await super().startup()
                if self.should_exit:
                    raise BootstrapFailure(BootstrapFailureKind.BOOTSTRAP_IO_FAILED)
                server._lifespan_entered = True
                if context.stopping:
                    raise _StartupStopped()

        # Verified against locked Uvicorn0.54.0: load once, then replace only its
        # lifespan boundary. Keep the actual startup/protocol/listener machinery.
        self.config.load()
        self.config.lifespan_class = CheckedLifespan
        async def lifetime() -> None:
            try:
                await super(_ControlledServer, self).serve(sockets=sockets)
            except _StartupStopped:
                pass
            finally:
                if self._lifespan_entered and not self._lifespan_closed:
                    await self.shutdown()
                # An unexpected Core defect must not release a pending owner.
                # Normal detach returns only after settlement; hung work stays
                # inside the protected lifespan join above without a timeout.
                if context.runtime_started and (
                    context.final_status is None or not context.final_status.owner_settled
                ):
                    await asyncio.Future[None]()

        await _settle_task(asyncio.create_task(lifetime()))

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        del sockets
        self._context.request_stop()  # Before the framework drains HTTP tasks.
        # Uvicorn0.54's timeout/force-exit branches are deliberately absent. Keep
        # its connection and HTTP-task drain, then perform the joined lifespan.
        for listener in getattr(self, "servers", ()):
            try:
                listener.close()
            except Exception:
                self.cleanup_failed = True
        for connection in tuple(self.server_state.connections):
            try:
                connection.shutdown()
            except Exception:
                self.cleanup_failed = True
        try:
            await self._wait_tasks_to_complete()
        except Exception:
            self.cleanup_failed = True
        finally:
            try:
                await self.lifespan.shutdown()
                self.cleanup_failed |= self.lifespan.shutdown_failed
            finally:
                self._lifespan_closed = True
        if self.cleanup_failed:
            raise BootstrapFailure(BootstrapFailureKind.TEARDOWN_INCOMPLETE)


def _bind(config: ServiceConfig, listener: socket.socket) -> None:
    try:
        listener.set_inheritable(False)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if config.host == "::1":
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind((config.host, config.port))
    except OSError:
        raise BootstrapFailure(BootstrapFailureKind.LISTENER_UNAVAILABLE) from None


def run_service(config: ServiceConfig) -> None:
    """Run one explicit numeric loopback service on the main thread's new loop."""
    if current_thread() is not main_thread():
        raise BootstrapFailure(BootstrapFailureKind.INVALID_CONFIGURATION)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise BootstrapFailure(BootstrapFailureKind.INVALID_CONFIGURATION)

    requested = False
    owner: PrivateBootstrap | None = None
    listener: socket.socket | None = None
    context: _LaunchContext | None = None
    server: _ControlledServer | None = None

    def stop(sig: int, frame: FrameType | None) -> None:
        nonlocal requested
        requested = True
        if context is not None:
            context.request_stop()
        if server is not None:
            server.handle_exit(sig, frame)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.disabled = True
        logger.propagate = False
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    primary: BootstrapFailure | None = None
    cleanup_failed = False
    try:
        for sig in previous:
            signal.signal(sig, stop)
        owner = PrivateBootstrap.acquire(config)
        if requested:
            return
        owner.mark_unconfirmed()
        if requested:
            return
        try:
            family = socket.AF_INET6 if config.host == "::1" else socket.AF_INET
            listener = socket.socket(family, socket.SOCK_STREAM)
        except OSError:
            raise BootstrapFailure(BootstrapFailureKind.LISTENER_UNAVAILABLE) from None
        _bind(config, listener)
        if requested:
            return
        owner.publish_credential()
        if requested:
            return
        context = _LaunchContext(config, owner)
        context.stopping = requested
        app = create_app(config, _launch_context=context)
        settings = uvicorn.Config(
            app, host=config.host, port=config.port, workers=1, reload=False,
            loop="asyncio", http="h11", ws="none", lifespan="on",
            proxy_headers=False, access_log=False, log_config=None,
            timeout_graceful_shutdown=None,
        )
        server = _ControlledServer(settings, context)
        server.should_exit = requested

        async def serve() -> None:
            assert server is not None and listener is not None
            await server.serve(sockets=[listener])

        asyncio.run(serve())
    except BootstrapFailure as error:
        primary = error
    except Exception:
        primary = BootstrapFailure(BootstrapFailureKind.BOOTSTRAP_IO_FAILED)
    finally:
        try:
            if owner is not None:
                final = None if context is None else context.final_status
                runtime_absent = context is None or not context.runtime_started
                facts = {
                    "owner_settled": runtime_absent or (final is not None and final.owner_settled),
                    "physical_release_confirmed": runtime_absent or (final is not None and final.physical_release_confirmed),
                    "recorder_close_confirmed": runtime_absent or (final is not None and final.recorder_close_confirmed),
                }
                cleanup_failed |= not all(facts.values())
                cleanup_failed |= server is not None and server.cleanup_failed
                try:
                    owner.invalidate_credential()
                except Exception:
                    cleanup_failed = True
                if listener is not None:
                    try:
                        listener.close()
                        cleanup_failed |= listener.fileno() != -1
                    except Exception:
                        cleanup_failed = True
                if owner.unconfirmed_published and not cleanup_failed:
                    try:
                        owner.confirm_cleanup(**facts)
                    except Exception:
                        # Replacement can already be visible before failed fsync.
                        # Never claim rollback or durable publication success.
                        cleanup_failed = True
                try:
                    owner.release()
                except Exception:
                    cleanup_failed = True
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        if cleanup_failed:
            raise BootstrapFailure(BootstrapFailureKind.TEARDOWN_INCOMPLETE) from None
    if primary is not None:
        raise primary from None
