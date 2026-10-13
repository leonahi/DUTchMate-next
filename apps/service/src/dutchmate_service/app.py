"""Controlled async composition for authenticated observation lifecycle delivery.

The bootstrap owner lives outside this app. Only a prepared, single-use private
launch context may enter lifespan; importing or building an app owns no resources.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dutchmate_core.adapters.observation_runtime import attach_basic_observation
from dutchmate_core.evidence import EvidenceRetrievalRequest
from dutchmate_core.model import EvidenceReference
from dutchmate_core.runtime import ObservationRuntime, RuntimeStatus
from fastapi import FastAPI, Request
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import ASGIApp

from dutchmate_service.bootstrap import (
    BootstrapFailure,
    BootstrapFailureKind,
    PrivateBootstrap,
    ServiceConfig,
)
from dutchmate_service.evidence_http import (
    evidence_rejection_response,
    evidence_response,
    validate_evidence_request,
)
from dutchmate_service.http import (
    SecurityGate,
    _Disconnected,
    error_response,
    rejection_response,
    status_response,
    validate_request,
)


class _LaunchContext:
    """Prepared bootstrap handoff from the controlled launcher or isolated tests."""

    def __init__(self, config: ServiceConfig, bootstrap: PrivateBootstrap) -> None:
        self.config = config
        self.bootstrap = bootstrap
        self._process = os.getpid()
        self._claimed = False
        self.stopping = False
        self.runtime_started = False
        # Captured on the owning loop after joined cleanup, safe to inspect later.
        # No runtime/task/resource handle crosses the bootstrap handoff.
        self.final_status: RuntimeStatus | None = None
        self.final_evidence_read_cleanup_confirmed = False

    def request_stop(self) -> None:
        self.stopping = True

    def claim(self, config: ServiceConfig) -> None:
        if (
            self._claimed
            or os.getpid() != self._process
            or config != self.config
            or self.bootstrap.credential is None
        ):
            raise BootstrapFailure(BootstrapFailureKind.INVALID_CONFIGURATION)
        # Cached publication is available only after the false marker and token
        # have been published under the real bootstrap guard. Never reread files.
        self._claimed = True


async def _settle_task[T](task: asyncio.Task[T]) -> T:
    """Join strongly owned lifecycle work despite repeated waiter cancellation."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # Cancelling the waiter never cancels the owned lifecycle task.
            continue
    return task.result()


def create_app(
    config: ServiceConfig, *, _launch_context: _LaunchContext | None = None
) -> ASGIApp:
    """Build delivery only; an uncontrolled factory launch fails during startup."""
    runtime: ObservationRuntime | None = None
    ready = False
    operations: set[asyncio.Task[Response]] = set()
    reads: set[asyncio.Task[Response]] = set()

    def accepting() -> bool:
        return ready and _launch_context is not None and not _launch_context.stopping

    def completed(task: asyncio.Task[Response]) -> None:
        operations.discard(task)
        if not task.cancelled():
            # Consume both successful completion and exceptions without storing
            # results/causes or logging input. Delivery may already have gone.
            task.exception()

    async def invoke(
        owner: ObservationRuntime, paths: tuple[str, str] | None
    ) -> Response:
        try:
            captured = (
                await owner.detach()
                if paths is None
                else await attach_basic_observation(owner, *paths)
            )
            return status_response(captured)
        except Exception as error:
            # Normalize inside the owner: Python 3.14 shield reports late raised
            # exceptions to the loop after delivery cancellation, even if read.
            return rejection_response(error)

    async def disconnected(request: Request) -> None:
        while (await request.receive())["type"] != "http.disconnect":
            pass

    async def mutation(
        request: Request, owner: ObservationRuntime, paths: tuple[str, str] | None
    ) -> Response:
        caller = asyncio.current_task()
        if caller is not None and caller.cancelling():
            raise asyncio.CancelledError()
        if not accepting():
            return error_response(503, "service", "stopping")
        # Done callbacks normally remove these first. Prune any already settled
        # tasks whose callbacks have not run, so the bound counts pending work.
        for previous in tuple(operations):
            if previous.done():
                completed(previous)
        if len(operations) >= 8:
            return error_response(503, "service", "operation_capacity")

        operation = asyncio.create_task(invoke(owner, paths))
        operations.add(operation)
        operation.add_done_callback(completed)
        # Registration is complete before any await or disconnect observation.
        # Cancelling these delivery futures/tasks never cancels the operation.
        shielded = asyncio.shield(operation)
        observer = asyncio.create_task(disconnected(request))
        try:
            done, _ = await asyncio.wait(
                (shielded, observer), return_when=asyncio.FIRST_COMPLETED
            )
            if observer in done:
                observer.result()
                raise asyncio.CancelledError()
            return shielded.result()
        finally:
            shielded.cancel()  # Only the shield's delivery future, not Core work.
            observer.cancel()
            await asyncio.gather(observer, return_exceptions=True)

    def read_completed(task: asyncio.Task[Response]) -> None:
        reads.discard(task)
        if not task.cancelled():
            task.exception()

    async def invoke_read(
        owner: ObservationRuntime, value: EvidenceReference | EvidenceRetrievalRequest
    ) -> Response:
        try:
            report = (
                await owner.read_record(value)
                if isinstance(value, EvidenceReference)
                else await owner.read_page(value)
            )
            return evidence_response(report)
        except Exception as error:
            # Normalize within the retained owner, including after client loss.
            return evidence_rejection_response(error)

    async def read_job(
        request: Request,
        owner: ObservationRuntime,
        value: EvidenceReference | EvidenceRetrievalRequest,
    ) -> Response:
        caller = asyncio.current_task()
        if caller is not None and caller.cancelling():
            raise asyncio.CancelledError()
        if not accepting():
            return error_response(503, "service", "stopping")
        for previous in tuple(reads):
            if previous.done():
                read_completed(previous)
        if len(reads) >= 8:
            return error_response(503, "service", "operation_capacity")
        operation = asyncio.create_task(invoke_read(owner, value))
        reads.add(operation)
        operation.add_done_callback(read_completed)
        # Separate registration is complete before Core admission or any await.
        shielded = asyncio.shield(operation)
        observer = asyncio.create_task(disconnected(request))
        try:
            done, _ = await asyncio.wait(
                (shielded, observer), return_when=asyncio.FIRST_COMPLETED
            )
            if observer in done:
                observer.result()
                raise asyncio.CancelledError()
            return shielded.result()
        finally:
            shielded.cancel()
            observer.cancel()
            await asyncio.gather(observer, return_exceptions=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        nonlocal runtime, ready
        if _launch_context is None:
            raise BootstrapFailure(BootstrapFailureKind.INVALID_CONFIGURATION)
        _launch_context.claim(config)
        runtime = ObservationRuntime()
        _launch_context.runtime_started = True
        ready = not _launch_context.stopping
        try:
            yield
        finally:
            ready = False
            _launch_context.request_stop()

            async def cleanup() -> None:
                # Admission is closed before taking this finite snapshot. Tasks
                # not yet inside Core must settle before the final detach.
                await asyncio.gather(
                    *tuple(operations), *tuple(reads), return_exceptions=True
                )
                try:
                    await runtime.detach()
                finally:
                    _launch_context.final_status = runtime.status()
                    _launch_context.final_evidence_read_cleanup_confirmed = (
                        runtime.evidence_read_cleanup_confirmed
                    )

            await _settle_task(asyncio.create_task(cleanup()))

    app = FastAPI(
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        debug=False,
        # FastAPI0.142 otherwise inherits ambient providers and can export raw
        # request exceptions independently of Uvicorn's disabled loggers.
        telemetry={
            "tracing": False,
            "metrics": False,
            "logs": False,
            "operation_spans": False,
            "auto_configure": False,
        },
    )

    @app.exception_handler(HTTPException)
    async def routing_error(request: Request, error: HTTPException) -> Response:
        del request
        if error.status_code == 404:
            return error_response(404, "request", "route_not_found")
        if error.status_code == 405:
            return error_response(405, "request", "method_not_allowed")
        return error_response(500, "service", "internal_failure")

    @app.get("/v1/observation/status")
    async def status() -> Response:
        if runtime is None:
            return error_response(503, "service", "stopping")
        try:
            return status_response(
                runtime.status(), service_state="ready" if accepting() else "stopping"
            )
        except Exception as error:
            return rejection_response(error)

    @app.post("/v1/observation/attach")
    async def attach(request: Request) -> Response:
        if not accepting() or runtime is None:
            return error_response(503, "service", "stopping")
        try:
            runtime.status()  # Guard loop/thread before Profile or run preparation.
            validated = await validate_request(request.scope, request.receive)
            if isinstance(validated, Response):
                return validated
            if validated is None:
                return error_response(422, "request", "invalid_request")
            return await mutation(request, runtime, validated)
        except Exception as error:
            return rejection_response(error)

    @app.post("/v1/observation/detach")
    async def detach(request: Request) -> Response:
        if not accepting() or runtime is None:
            return error_response(503, "service", "stopping")
        try:
            runtime.status()
            validated = await validate_request(request.scope, request.receive)
            if isinstance(validated, Response):
                return validated
            return await mutation(request, runtime, None)
        except Exception as error:
            return rejection_response(error)

    @app.post("/v1/evidence/record")
    @app.post("/v1/evidence/page")
    async def read_evidence(request: Request) -> Response:
        if not accepting() or runtime is None:
            return error_response(503, "service", "stopping")
        try:
            value = await validate_evidence_request(request.scope, request.receive)
            if isinstance(value, Response):
                return value
            return await read_job(request, runtime, value)
        except _Disconnected:
            # Abort lost delivery as the existing disconnect observer does.
            # Re-raising an Exception here lets framework middleware emit a 500.
            raise asyncio.CancelledError() from None
        except Exception as error:
            return evidence_rejection_response(error)

    def credential() -> str | None:
        return None if _launch_context is None else _launch_context.bootstrap.credential

    return SecurityGate(app, config=config, credential=credential)
