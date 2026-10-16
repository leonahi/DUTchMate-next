"""010 T010 RED: existing mutation ownership and annotation stop sealing.

No admission, capacity, delivery or stop policy is implemented by these gates.
The actual authenticated app owns every operation tested here.
"""

import asyncio
import gc
import importlib
import json
import logging
from pathlib import Path
from typing import Any

import pytest
from dutchmate_core import annotation, evidence, model, monitor
from dutchmate_core.evidence_access import RunEvidencePage
from dutchmate_core.runtime import RuntimeStatus

from dutchmate_service.bootstrap import (
    BootstrapFailure,
    PrivateBootstrap,
    ServiceConfig,
)
from test_annotation_http import _BODY, _PRIVATE, _ROUTE, _SESSION, _receipt, _wire
from test_evidence_http import (
    ActiveEvidenceService,
    ReadBoundary,
    Service,
    _error,
    _json,
    _success,
    _t014_core_helpers,
)
from test_monitor_http import _BODY as _MONITOR_BODY
from test_monitor_http import _ROUTE as _MONITOR_ROUTE
from test_monitor_http import _report as _monitor_report
from test_monitor_lifetime import PendingCalls, _app, _await, _lost
from test_service_http import (
    _CONFIGS,
    Exchange,
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


async def _entered(
    calls: PendingCalls, delivery: asyncio.Task[None], client: Client
) -> Call:
    """Fail immediately for absent routing, rather than timing out a policy gate."""
    notification = asyncio.create_task(calls.entered.get())
    try:
        done, _ = await _await(
            asyncio.wait((notification, delivery), return_when=asyncio.FIRST_COMPLETED)
        )
        assert notification in done, (
            f"delivery ended before Core entry: HTTP {client.status}, {client.payload!r}"
        )
        return notification.result()
    finally:
        if not notification.done():
            notification.cancel()
        await asyncio.gather(notification, return_exceptions=True)


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.parametrize("first", ["annotation", "mutation"])
@pytest.mark.asyncio
async def test_annotations_share_eight_mutation_jobs_with_attach_detach_and_survive_client_loss(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    loss: str,
    first: str,
) -> None:
    async with _app(account_home, monkeypatch, config) as service:
        calls = PendingCalls()

        async def annotate(
            request: annotation.AnnotationRequest,
        ) -> annotation.AnnotationReceipt:
            assert request.session_id == _SESSION
            await calls.wait("annotation")
            return _receipt()

        async def detach() -> RuntimeStatus:
            await calls.wait("mutation")
            return service.runtime.status()

        monkeypatch.setattr(service.runtime, "annotate", annotate)
        monkeypatch.setattr(service.runtime, "detach", detach)
        try:
            # Four of each exhaust exactly the same eight slots, in either order.
            for action in [first] * 4 + [
                "mutation" if first == "annotation" else "annotation"
            ] * 4:
                client = Client(body=_json(_BODY) if action == "annotation" else b"")
                delivery = service.submit(
                    _ROUTE if action == "annotation" else _DETACH, client
                )
                call = await _entered(calls, delivery, client)
                assert call.action == action
                await _lost(delivery, client, loss)
            gc.collect()
            assert len(calls.calls) == 8
            for call in calls.calls:
                owner = call.task()
                assert owner is not None and not owner.done()
            for path, body, raw in (
                (_ROUTE, _BODY, None),
                (_DETACH, {}, b""),
                (
                    _ATTACH,
                    {
                        "profile_path": str(account_home / "test-only-profile.toml"),
                        "journal_path": str(account_home / "test-only-journal.sqlite"),
                    },
                    None,
                ),
            ):
                _error(
                    await service.request(path, body, raw=raw),
                    503,
                    "service",
                    "operation_capacity",
                )
            assert len(calls.calls) == 8
            calls.release("annotation")
            await flush()
            _success(await service.request(_ROUTE, _BODY), _wire())
            # A newly registered detach can reuse the annotation's released slot.
            # The four original detach owners remain pending until final cleanup.
            calls.open_actions.add("mutation")
            assert (await service.request(_DETACH, {}, raw=b"")).status == 200
            assert len(calls.calls) == 10
        finally:
            calls.release("annotation")
            calls.release()


@pytest.mark.parametrize("released", ["annotation", "read", "monitor"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.asyncio
async def test_eight_mutations_eight_reads_and_one_monitor_remain_independent(
    account_home: Path, monkeypatch: pytest.MonkeyPatch, released: str, loss: str
) -> None:
    async with _app(account_home, monkeypatch, _CONFIGS[0]) as service:
        calls = PendingCalls()

        async def annotate(
            request: annotation.AnnotationRequest,
        ) -> annotation.AnnotationReceipt:
            del request
            await calls.wait("annotation")
            return _receipt()

        async def read(reference: model.EvidenceReference) -> RunEvidencePage:
            del reference
            await calls.wait("read")
            return service.boundary.result

        async def observe(request: monitor.MonitorRequest) -> monitor.MonitorReport:
            del request
            await calls.wait("monitor")
            return _monitor_report()

        monkeypatch.setattr(service.runtime, "annotate", annotate)
        monkeypatch.setattr(service.runtime, "read_record", read)
        monkeypatch.setattr(service.runtime, "monitor", observe)
        specs = {
            "read": (_READ, {"session_id": _SESSION.value, "sequence": 0}, 8),
            "monitor": (_MONITOR_ROUTE, _MONITOR_BODY, 1),
            "annotation": (_ROUTE, _BODY, 8),
        }
        try:
            for action, (path, body, count) in specs.items():
                for _ in range(count):
                    client = Client(body=_json(body))
                    delivery = service.submit(path, client)
                    assert (await _entered(calls, delivery, client)).action == action
                    await _lost(delivery, client, loss)
            gc.collect()
            assert len(calls.calls) == 17
            for call in calls.calls:
                owner = call.task()
                assert owner is not None and not owner.done()
            for path, body, _ in specs.values():
                _error(
                    await service.request(path, body),
                    503,
                    "service",
                    "operation_capacity",
                )
            calls.release(released)
            await flush()
            for action, (path, body, _) in specs.items():
                response = await service.request(path, body)
                if action == released:
                    assert response.status == 200
                else:
                    _error(response, 503, "service", "operation_capacity")
        finally:
            calls.release("annotation")
            calls.release()


@pytest.mark.parametrize("before", ["cancel", "disconnect", "pending-cancel"])
@pytest.mark.asyncio
async def test_lost_delivery_before_admission_submits_no_annotation(
    account_home: Path, monkeypatch: pytest.MonkeyPatch, before: str
) -> None:
    async with _app(account_home, monkeypatch, _CONFIGS[0]) as service:
        entered: list[annotation.AnnotationRequest] = []

        async def annotate(
            request: annotation.AnnotationRequest,
        ) -> annotation.AnnotationReceipt:
            entered.append(request)
            return _receipt()

        monkeypatch.setattr(service.runtime, "annotate", annotate)
        client = Client(body=_json(_BODY), before_body=before)
        delivery = service.submit(_ROUTE, client)
        try:
            if before == "cancel":
                notification = asyncio.create_task(client.body_entered.wait())
                try:
                    done, _ = await _await(
                        asyncio.wait(
                            (notification, delivery),
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    )
                    assert notification in done, (
                        "literal annotation route did not read body"
                    )
                finally:
                    notification.cancel()
                    await asyncio.gather(notification, return_exceptions=True)
                delivery.cancel()
            with pytest.raises(asyncio.CancelledError):
                await _await(delivery)
            assert not entered
            assert not client.messages
        finally:
            if not delivery.done():
                delivery.cancel()
            await asyncio.gather(delivery, return_exceptions=True)


@pytest.mark.asyncio
async def test_stop_synchronously_seals_annotation_incarnation_before_any_job_snapshot(
    account_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _app(account_home, monkeypatch, _CONFIGS[0]) as service:
        # Actual Core: without the service stop seal this is no_associated_session.
        request = annotation.AnnotationRequest(_SESSION, "late assertion", "http")
        service.launch_context.request_stop()
        with pytest.raises(annotation.AnnotationRejected) as rejected:
            await service.runtime.annotate(request)
        assert rejected.value.kind == "annotation_unavailable"
        _error(await service.request(_ROUTE, _BODY), 503, "service", "stopping")


@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.asyncio
async def test_registered_but_not_core_admitted_annotation_cannot_slip_past_stop(
    account_home: Path, monkeypatch: pytest.MonkeyPatch, loss: str
) -> None:
    async with _app(account_home, monkeypatch, _CONFIGS[0]) as service:
        original = service.runtime.annotate
        calls = PendingCalls()
        rejections: list[str] = []

        async def delayed(
            request: annotation.AnnotationRequest,
        ) -> annotation.AnnotationReceipt:
            await calls.wait("annotation")
            try:
                return await original(request)
            except annotation.AnnotationRejected as error:
                rejections.append(error.kind)
                raise

        monkeypatch.setattr(service.runtime, "annotate", delayed)
        client = Client(body=_json(_BODY))
        delivery = service.submit(_ROUTE, client)
        try:
            call = await _entered(calls, delivery, client)
            await _lost(delivery, client, loss)
            service.launch_context.request_stop()
            calls.release("annotation")
            owner = call.task()
            assert owner is not None
            await _await(asyncio.shield(owner))
            assert rejections == ["annotation_unavailable"]
        finally:
            calls.release("annotation")


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.asyncio
async def test_cancelled_client_owner_is_joined_before_final_detach_and_bootstrap_release(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with _app(account_home, monkeypatch, _CONFIGS[0]) as service:
        calls = PendingCalls()
        order: list[str] = []
        unhandled: list[dict[str, object]] = []
        loop = asyncio.get_running_loop()
        old_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
        original_detach = service.runtime.detach
        assert service.lifespan.task is not None

        async def annotate(
            request: annotation.AnnotationRequest,
        ) -> annotation.AnnotationReceipt:
            del request
            await calls.wait("annotation")
            order.append("annotation-settled")
            if failure:
                raise RuntimeError(_PRIVATE)
            return _receipt()

        async def detach() -> RuntimeStatus:
            order.append("detach")
            return await original_detach()

        monkeypatch.setattr(service.runtime, "annotate", annotate)
        monkeypatch.setattr(service.runtime, "detach", detach)
        client = Client(body=_json(_BODY))
        delivery = service.submit(_ROUTE, client)
        try:
            call = await _entered(calls, delivery, client)
            await _lost(delivery, client, "cancel")
            service.launch_context.request_stop()
            await service.lifespan.incoming.put({"type": "lifespan.shutdown"})
            await flush()
            assert not service.lifespan.task.done()
            assert not order
            with pytest.raises(BootstrapFailure):
                unexpected = PrivateBootstrap.acquire(service.config)
                unexpected.release()
            gc.collect()
            owner = call.task()
            assert owner is not None and not owner.done()
            calls.release("annotation")
            await _await(asyncio.shield(owner))
            assert (await _await(service.lifespan.outgoing.get()))[
                "type"
            ] == "lifespan.shutdown.complete"
            await _await(service.lifespan.task)
            assert order == ["annotation-settled", "detach"]
            assert not unhandled
            assert _PRIVATE not in caplog.text
            assert service.token.decode() not in caplog.text
            assert not client.messages
        finally:
            calls.release("annotation")
            loop.set_exception_handler(old_handler)


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.parametrize(
    "order",
    [
        ("annotation", "read", "mutation", "monitor"),
        ("monitor", "mutation", "read", "annotation"),
        ("read", "annotation", "monitor", "mutation"),
    ],
)
@pytest.mark.asyncio
async def test_t018_stop_joins_mixed_full_pools_in_each_release_order(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    loss: str,
    order: tuple[str, str, str, str],
) -> None:
    async with _app(account_home, monkeypatch, config) as service:
        calls, trace = PendingCalls(), []
        detach = service.runtime.detach

        async def annotate(
            request: annotation.AnnotationRequest,
        ) -> annotation.AnnotationReceipt:
            assert request.session_id == _SESSION
            await calls.wait("annotation")
            return _receipt()

        async def lifecycle() -> RuntimeStatus:
            if service.launch_context.stopping:
                trace.append("final-detach")
                return await detach()
            await calls.wait("mutation")
            return service.runtime.status()

        async def read(reference: model.EvidenceReference) -> RunEvidencePage:
            assert reference.session_id == _SESSION
            await calls.wait("read")
            return service.boundary.result

        async def observe(request: monitor.MonitorRequest) -> monitor.MonitorReport:
            assert request.session_id == _SESSION
            await calls.wait("monitor")
            return _monitor_report()

        monkeypatch.setattr(service.runtime, "annotate", annotate)
        monkeypatch.setattr(service.runtime, "detach", lifecycle)
        monkeypatch.setattr(service.runtime, "read_record", read)
        monkeypatch.setattr(service.runtime, "monitor", observe)
        try:
            for action, path, body, count in (
                ("annotation", _ROUTE, _BODY, 4),
                ("mutation", _DETACH, {}, 4),
                ("read", _READ, {"session_id": _SESSION.value, "sequence": 0}, 8),
                ("monitor", _MONITOR_ROUTE, _MONITOR_BODY, 1),
            ):
                for _ in range(count):
                    client = Client(body=b"" if action == "mutation" else _json(body))
                    delivery = service.submit(path, client)
                    assert (await _entered(calls, delivery, client)).action == action
                    await _lost(delivery, client, loss)
            for path, body, raw in (
                (_ROUTE, _BODY, None),
                (_DETACH, {}, b""),
                (_READ, {"session_id": _SESSION.value, "sequence": 0}, None),
                (_MONITOR_ROUTE, _MONITOR_BODY, None),
            ):
                _error(
                    await service.request(path, body, raw=raw),
                    503,
                    "service",
                    "operation_capacity",
                )
            assert len(calls.calls) == 17
            # Security remains first even when every operation pool is full.
            scope = service.scope(_ROUTE)
            scope["headers"] = [
                (k, v) for k, v in scope["headers"] if k != b"authorization"
            ]
            _error(
                await service.request(
                    _ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
                ),
                401,
                "request",
                "authentication_required",
            )
            service.launch_context.request_stop()
            await service.lifespan.incoming.put({"type": "lifespan.shutdown"})
            await flush()
            assert service.lifespan.task is not None
            for action in order:
                assert service.launch_context.final_status is None and trace == []
                assert not service.lifespan.task.done()
                _t021_held(account_home)
                for path in (_ROUTE, _READ, _MONITOR_ROUTE):
                    _error(
                        await service.request(
                            path, {}, exchange=Exchange(forbid_receive=True)
                        ),
                        503,
                        "service",
                        "stopping",
                    )
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
            assert service.launch_context.final_status is not None
            assert service.launch_context.final_status.owner_settled
            assert service.launch_context.final_evidence_read_cleanup_confirmed
            _t021_held(account_home)
        finally:
            calls.release("annotation")
            calls.release()


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.asyncio
async def test_t018_registered_annotation_on_real_active_runtime_is_sealed_before_core_entry(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    loss: str,
) -> None:
    _t014_core_helpers(monkeypatch)
    core = importlib.import_module("tests.contract.test_annotation_runtime")
    async with _app(account_home, monkeypatch, config) as service:
        async with core.case(tmp_path, owner=service.runtime) as c:
            calls = PendingCalls()
            original = service.runtime.annotate
            outcomes: list[str] = []

            async def delayed(
                request: annotation.AnnotationRequest,
            ) -> annotation.AnnotationReceipt:
                await calls.wait("annotation")
                try:
                    return await original(request)
                except annotation.AnnotationRejected as error:
                    outcomes.append(error.kind)
                    raise

            monkeypatch.setattr(service.runtime, "annotate", delayed)
            body = {**_BODY, "session_id": c.probe.session_id.value}
            client = Client(body=_json(body))
            delivery = service.submit(_ROUTE, client)
            try:
                call = await _entered(calls, delivery, client)
                await _lost(delivery, client, loss)
                service.launch_context.request_stop()
                # No await separates the stop request from the Core seal check.
                with pytest.raises(annotation.AnnotationRejected) as sealed:
                    await original(c.request())
                assert sealed.value.kind == "annotation_unavailable"
                await service.lifespan.incoming.put({"type": "lifespan.shutdown"})
                await flush()
                assert (
                    service.lifespan.task is not None
                    and not service.lifespan.task.done()
                )
                assert c.probe.close_calls == 0 and c.charge.calls == []
                assert c.clock.samples == [] and outcomes == []
                _t021_held(account_home)
                calls.release("annotation")
                owner = call.task()
                assert owner is not None
                await _await(asyncio.shield(owner))
                assert outcomes == ["annotation_unavailable"]
                assert (await _await(service.lifespan.outgoing.get()))[
                    "type"
                ] == "lifespan.shutdown.complete"
                await _await(service.lifespan.task)
                assert c.probe.close_calls == c.fixture.connection.close_calls == 1
                assert not any(
                    isinstance(d, evidence.PendingClientAnnotationEvidence)
                    for d in c.probe.submitted
                )
                assert not client.messages
            finally:
                calls.release("annotation")


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.parametrize("fault", ["journal", "unexpected"])
@pytest.mark.asyncio
async def test_t018_late_annotation_errors_remain_private_and_release_only_their_shared_slot(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    loss: str,
    fault: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    unhandled: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
    try:
        async with _app(account_home, monkeypatch, config) as service:
            calls = PendingCalls()
            fail = True
            secret = _PRIVATE + "/credential/path/SQL/" + service.token.decode()

            async def annotate(
                request: annotation.AnnotationRequest,
            ) -> annotation.AnnotationReceipt:
                assert request.text == secret
                await calls.wait("annotation")
                if fail:
                    error: Exception = (
                        RuntimeError(secret)
                        if fault == "unexpected"
                        else evidence.JournalFailure(
                            evidence.JournalOperation.APPEND,
                            evidence.JournalFailureKind.IO_FAILURE,
                            secret,
                        )
                    )
                    error.add_note(secret)
                    raise error from OSError(secret)
                return _receipt()

            async def detach() -> RuntimeStatus:
                await calls.wait("mutation")
                return service.runtime.status()

            monkeypatch.setattr(service.runtime, "annotate", annotate)
            monkeypatch.setattr(service.runtime, "detach", detach)
            body = {**_BODY, "text": secret}
            client = Client(body=_json(body))
            delivery = service.submit(_ROUTE, client)
            try:
                annotation_call = await _entered(calls, delivery, client)
                await _lost(delivery, client, loss)
                for _ in range(7):
                    other = Client(body=b"")
                    task = service.submit(_DETACH, other)
                    await _entered(calls, task, other)
                    await _lost(task, other, loss)
                _error(
                    await service.request(_ROUTE, body),
                    503,
                    "service",
                    "operation_capacity",
                )
                calls.release("annotation")
                owner = annotation_call.task()
                assert owner is not None
                await _await(asyncio.shield(owner))
                await flush()
                # An alive caller receives only the fixed projection; none of
                # the seven sibling lifecycle jobs is cancelled by the error.
                response = await service.request(_ROUTE, body)
                _error(
                    response,
                    500,
                    "service" if fault == "unexpected" else "journal",
                    "internal_failure" if fault == "unexpected" else "io_failure",
                )
                assert (
                    secret.encode() not in response.payload
                    and secret not in caplog.text
                )
                assert _PRIVATE not in caplog.text
                assert service.token.decode() not in caplog.text
                assert all(
                    not call.finished.is_set()
                    for call in calls.calls
                    if call.action == "mutation"
                )
                fail = False
                _success(await service.request(_ROUTE, body), _wire())
                gc.collect()
                await flush()
                assert not unhandled and not client.messages
            finally:
                calls.release("annotation")
                calls.release()
    finally:
        loop.set_exception_handler(previous)


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.parametrize("phase", ["commit", "ack"])
@pytest.mark.parametrize("dirty_reader", [False, True])
def test_t018_launcher_joins_real_v3_annotation_before_bootstrap_release_and_keeps_dirty_reads(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    backend_index: int,
    loss: str,
    phase: str,
    dirty_reader: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from dutchmate_core.adapters import observation_runtime, terminal_evidence

    caplog.set_level(logging.DEBUG)
    _t014_core_helpers(monkeypatch)
    core = importlib.import_module("tests.contract.test_annotation_runtime")
    launch = _T021Launch(account_home, t011_composition)
    entered, release, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    deliveries: list[asyncio.Task[None]] = []
    receipts: list[annotation.AnnotationReceipt] = []
    errors: list[BaseException] = []
    tokens: list[str] = []
    contexts: list[Any] = []
    detach_count = 0

    async def scenario(http: Any, service: _T011Service) -> None:
        nonlocal detach_count
        tokens.append(service.token.decode())
        contexts.append(http._context)
        gateway = Service(
            service.app, service.config, service.token, ReadBoundary(), http._context
        )

        async def attach(destination: Path) -> None:
            fixture = core._durable_fixture(
                core.BACKEND_FIXTURE_FACTORIES[backend_index]
            )
            monkeypatch.setattr(
                observation_runtime, "BasicSerialBackend", lambda *args: fixture.backend
            )
            result = await service.request(
                _ATTACH, "POST", _t011_body(t011_composition.profile_path, destination)
            )
            assert (
                result.status == 200
                and service.runtime.status().state.value == "active"
            )

        if dirty_reader:
            await attach(t011_composition.journal_path.with_name("prior.sqlite3"))
            prior = await service.runtime.detach()
            assert prior.session_id is not None and prior.attach_admissible
            original_close = terminal_evidence._close_reader_on_worker

            def uncertain_close(connection: Any) -> None:
                original_close(connection)
                raise evidence.JournalFailure(
                    evidence.JournalOperation.CLOSE,
                    evidence.JournalFailureKind.IO_FAILURE,
                    _PRIVATE,
                )

            with monkeypatch.context() as patch:
                patch.setattr(
                    terminal_evidence, "_close_reader_on_worker", uncertain_close
                )
                _error(
                    await gateway.request(
                        _READ, {"session_id": prior.session_id.value, "sequence": 0}
                    ),
                    500,
                    "journal",
                    "io_failure",
                )
            assert not service.runtime.evidence_read_cleanup_confirmed
            assert service.runtime.status() == prior
        await attach(t011_composition.journal_path)
        active = service.runtime.status()
        assert active.session_id is not None
        assert service.runtime.evidence_read_cleanup_confirmed is (not dirty_reader)
        journal = t011_composition.journals[-1]
        append, close, annotate = (
            journal.append,
            journal.close,
            service.runtime.annotate,
        )

        async def paused(draft: evidence.PendingEvidenceRecord) -> model.EvidenceRecord:
            selected = isinstance(draft, evidence.PendingClientAnnotationEvidence)
            if selected and phase == "commit":
                entered.set()
                await release.wait()
            record = await append(draft)
            if selected and phase == "ack":
                entered.set()
                await release.wait()
            return record

        async def observed(
            request: annotation.AnnotationRequest,
        ) -> annotation.AnnotationReceipt:
            try:
                receipt = await annotate(request)
                receipts.append(receipt)
                return receipt
            finally:
                launch.trace.append("annotation.settled")
                settled.set()

        async def closed() -> None:
            assert settled.is_set() and release.is_set()
            await close()
            launch.trace.append("annotation.journal.closed")

        monkeypatch.setattr(journal, "append", paused)
        monkeypatch.setattr(journal, "close", closed)
        monkeypatch.setattr(service.runtime, "annotate", observed)
        body = {**_BODY, "session_id": active.session_id.value, "text": _PRIVATE}
        client = Client(body=_json(body))

        async def deliver() -> None:
            await gateway.app(gateway.scope(_ROUTE), client.receive, client.send)

        delivery = asyncio.create_task(deliver())
        deliveries.append(delivery)
        await _await(entered.wait())
        await _lost(delivery, client, loss)
        detach_count = launch.trace.count("runtime.detach.enter")
        launch.emit()
        launch.emit()
        assert http.should_exit and not http.force_exit
        with pytest.raises(annotation.AnnotationRejected) as rejected:
            await annotate(
                annotation.AnnotationRequest(active.session_id, "late", "http")
            )
        assert rejected.value.kind == "annotation_unavailable"

    async def drain(http: Any, service: _T011Service) -> None:
        _t021_held(account_home)
        assert not release.is_set() and not settled.is_set()
        assert launch.trace.count("runtime.detach.enter") == detach_count
        assert (
            launch.owners[0].credential is not None
            and "marker.true" not in launch.trace
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
            errors.append(error)
            release.set()
            raise

    async def guarded_drain(http: Any, service: _T011Service) -> None:
        try:
            await drain(http, service)
        except BaseException as error:
            errors.append(error)
            raise
        finally:
            release.set()

    launch.scenario, launch.at_drain = guarded_scenario, guarded_drain
    launch.install(monkeypatch)
    try:
        if dirty_reader:
            with pytest.raises(BootstrapFailure) as failed:
                _t021_server().run_service(ServiceConfig(8765))
            assert failed.value.kind.value == "teardown_incomplete"
        else:
            _t021_server().run_service(ServiceConfig(8765))
    finally:
        release.set()
    assert not errors, [repr(error) for error in errors]
    assert all(delivery.done() for delivery in deliveries) and len(receipts) == 1
    receipt = receipts[0]
    assert (
        receipt.annotation.text == _PRIVATE
        and receipt.annotation.client_surface == "cli"
    )
    assert receipt.reference.sequence == receipt.annotation.sequence == 1
    final = launch.settled[id(launch.runtimes[0])]
    assert (
        final.owner_settled
        and final.recorder_close_confirmed
        and final.physical_release_confirmed
    )
    assert final.attach_admissible and final.primary_issue is None
    assert contexts[0].final_evidence_read_cleanup_confirmed is (not dirty_reader)
    last_detach = max(
        i for i, item in enumerate(launch.trace) if item == "runtime.detach.enter"
    )
    assert (
        launch.trace.index("annotation.settled")
        < last_detach
        < launch.trace.index("annotation.journal.closed")
    )
    assert launch.trace.index("annotation.journal.closed") < launch.trace.index(
        "token.invalidated"
    )
    assert (
        launch.trace.index("token.invalidated")
        < launch.trace.index("socket.closed")
        < launch.trace.index("owner.release")
    )
    assert ("marker.true" in launch.trace) is (not dirty_reader)
    assert json.loads((launch.root / "owner.json").read_bytes()) == {
        "version": 1,
        "cleanup_confirmed": not dirty_reader,
    }
    assert not (launch.root / "credential").exists() and all(
        sock.released for sock in launch.sockets
    )
    assert _PRIVATE not in caplog.text and all(
        token not in caplog.text for token in tokens
    )

    async def readback() -> None:
        target = terminal_evidence.capture_terminal_target(
            t011_composition.journal_path,
            session_id=receipt.session_id,
            policy=t011_composition.journals[-1].policy,
            expected_schema_version=3,
        )
        assert target is not None
        reader = await terminal_evidence.open_terminal_reader(target)
        try:
            assert (await reader.resolve_record(receipt.reference)).records == (
                receipt.annotation,
            )
        finally:
            await reader.close()

    asyncio.run(readback())


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("broken_pipe", [False, True])
@pytest.mark.asyncio
async def test_t018_real_cli_stdout_loss_keeps_the_service_annotation_committed_without_retry(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend_index: int,
    broken_pipe: bool,
) -> None:
    import sys
    from types import SimpleNamespace

    _t014_core_helpers(monkeypatch)
    core = importlib.import_module("tests.contract.test_annotation_runtime")
    # Reuse the existing real CLI/ASGI bridge, even in a service-only selection.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "cli/tests"))
    cli = importlib.import_module("test_cli_evidence")
    async with _app(account_home, monkeypatch, _CONFIGS[0]) as service:
        async with core.case(
            tmp_path,
            owner=service.runtime,
            factory=core.BACKEND_FIXTURE_FACTORIES[backend_index],
        ) as c:
            gateway = ActiveEvidenceService(
                service.app,
                service.config,
                service.token,
                SimpleNamespace(journal=c.probe.journal),
                tmp_path / "runtime.db",
            )
            bridge = cli.ActiveBridge(gateway, monkeypatch)
            attempts: list[bytes] = []

            class FailedOutput:
                @property
                def buffer(self) -> FailedOutput:
                    return self

                def write(self, record: bytes) -> int:
                    attempts.append(record)
                    if broken_pipe:
                        raise BrokenPipeError(_PRIVATE)
                    raise OSError(_PRIVATE)

                def flush(self) -> None:
                    raise OSError(_PRIVATE)

                def close(self) -> None:
                    pass

            with monkeypatch.context() as patch:
                patch.setattr(sys, "stdout", FailedOutput())
                code = await asyncio.to_thread(
                    cli._command,
                    cli._api(),
                    bridge.args(
                        "annotate",
                        "--session",
                        c.probe.session_id.value,
                        "--text",
                        "external claim",
                    ),
                )
            assert code == 1
            assert tuple(capsys.readouterr()) == (
                "",
                _json(
                    {
                        "error": {"source": "cli", "code": "output_failed"},
                        "request_outcome": "report_received",
                    }
                ).decode()
                + "\n",
            )
            assert len(attempts) == len(bridge.requests) == len(bridge.responses) == 1
            assert (
                bridge.responses[0].is_closed and bridge.responses[0].status_code == 200
            )
            assert bridge.responses[0].headers["cache-control"] == "no-store"
            document = json.loads(attempts[0])
            assert document["annotation"]["text"] == "external claim"
            assert document["annotation"]["assertion_class"] == "client_assertion"
            assert document["annotation"]["attribution_basis"] == "client_asserted"
            assert document["reference"]["sequence"] == 1
            report = await service.runtime.read_record(
                model.EvidenceReference(c.probe.session_id, 1)
            )
            assert len(report.page.records) == 1
            claim = report.page.records[0]
            assert isinstance(claim, model.ClientAnnotationEvidence)
            assert claim.text == "external claim" and claim.client_surface == "cli"
            assert service.runtime.status().state.value == "active"
            assert (
                c.fixture.backend.open_calls == c.fixture.connection.consumer_calls == 1
            )
