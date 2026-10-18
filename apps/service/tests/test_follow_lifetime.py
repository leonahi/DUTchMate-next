"""011 T018: real service lifetime/security, with no production policy in gates.

Observable failures include premature slot reuse/recorder close, cancelled native
queries, source work admitted after stop, false delivered prefixes, a reset send
deadline and security/body work in the wrong order. Gates delay external/Core
work or delivery only; actual app registries, runtime and journal remain intact.
"""

import asyncio
import gc
import json
import logging
import socket
import weakref
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from dutchmate_core import follow
from dutchmate_core.adapters.sqlite_evidence import SqliteEvidenceJournal
from dutchmate_core.runtime import FollowSubscription, RuntimeState
from starlette.types import Message
from uvicorn.lifespan.off import LifespanOff

from dutchmate_service.bootstrap import ServiceConfig
from dutchmate_service.follow_http import FollowStream
from dutchmate_service.server import _ControlledServer
from test_evidence_http import _error, _json, _t014_core_helpers
from test_follow_http import (
    BODY,
    PRIVATE,
    ROUTE,
    FrameClient,
    Subscription,
    frames,
    reached,
    rx,
    rx_wire,
    service,
    start,
    started,
    terminal,
    wait,
    wire_bytes,
)
from test_monitor_lifetime import LifetimeService, _app
from test_service_http import _CONFIGS, Exchange
from test_service_http import process_credential as process_credential
from test_service_runtime import Client, _t021_held, flush

pytestmark = pytest.mark.asyncio


def emitted(client: Exchange) -> bytes:
    # Exchange.payload intentionally requires a completed finite HTTP response.
    return b"".join(
        m.get("body", b"") for m in client.messages if m["type"] == "http.response.body"
    )


async def until(predicate: Callable[[], bool]) -> None:
    async def observe() -> None:
        while not predicate():
            await flush()

    await wait(observe())


@dataclass
class Live:
    service: LifetimeService
    case: Any
    sources: list[FollowSubscription] = field(default_factory=list)
    closed: dict[int, asyncio.Event] = field(default_factory=dict)
    clients: list[Client] = field(default_factory=list)

    def submit(self, client: Client | None = None) -> tuple[asyncio.Task[None], Client]:
        client = client or Client(
            body=_json({"session_id": self.case.journal.session_id.value})
        )
        self.clients.append(client)
        return self.service.submit(ROUTE, client), client


@asynccontextmanager
async def live(
    home: Path,
    path: Path,
    patch: pytest.MonkeyPatch,
    backend: int,
    config: ServiceConfig = _CONFIGS[0],
) -> AsyncIterator[Live]:
    _t014_core_helpers(patch)
    from tests.contract.test_follow_runtime import RuntimeCase
    from tests.contract.test_observation_runtime import _profile
    from tests.fakes import BACKEND_FIXTURE_FACTORIES

    journal = await SqliteEvidenceJournal.create_v3(
        path / "lifetime.db", _profile().session_policy
    )
    async with _app(home, patch, config) as s:
        c = RuntimeCase(
            s.runtime, journal, BACKEND_FIXTURE_FACTORIES[backend], patch, 3
        )
        value = Live(s, c)
        original = s.runtime.start_follow

        async def capture(request: follow.FollowRequest) -> FollowSubscription:
            sub = await original(request)
            value.sources.append(sub)
            closed = value.closed[id(sub)] = asyncio.Event()
            close = sub.close

            async def observed_close() -> None:
                await close()
                closed.set()

            patch.setattr(sub, "close", observed_close)
            return sub

        patch.setattr(s.runtime, "start_follow", capture)
        try:
            await c.activate()
            yield value
        finally:
            c.queries.release()
            for client in value.clients:
                client.disconnected.set()
                client.publication_gate.set()
                if isinstance(client, FrameClient):
                    client.release_send.set()
            for task in s.deliveries:
                if not task.done():
                    task.cancel()
            await wait(asyncio.gather(*s.deliveries, return_exceptions=True))
            await c.finish()


@asynccontextmanager
async def network(
    home: Path, path: Path, patch: pytest.MonkeyPatch, backend: int, host: str
) -> AsyncIterator[tuple[Live, str, _ControlledServer]]:
    # Numeric test-owned loopback only; actual controlled-server HTTP drain runs.
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        if family == socket.AF_INET6:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind((host, 0))
        listener.listen(128)
        listener.setblocking(False)
        config = ServiceConfig(listener.getsockname()[1], host)
        async with live(home, path, patch, backend, config) as d:
            server = _ControlledServer(
                uvicorn.Config(
                    d.service.app,
                    host=host,
                    port=config.port,
                    lifespan="off",
                    log_config=None,
                    access_log=False,
                    proxy_headers=False,
                    server_header=False,
                    date_header=False,
                ),
                d.service.launch_context,
            )
            # The enclosing helper owns the real app lifespan. Keep Uvicorn's
            # listener/protocol/drain and ControlledServer stop ordering real.
            server.config.load()

            class BorrowedLifespan(LifespanOff):
                # ControlledServer normally uses LifespanOn's failure fact.
                # The enclosing _app owns/validates real lifespan settlement.
                shutdown_failed = False

            server.lifespan = BorrowedLifespan(server.config)
            await wait(server.startup(sockets=[listener]))
            assert server.started
            authority = f"[{host}]" if family == socket.AF_INET6 else host
            try:
                yield d, f"http://{authority}:{config.port}", server
            finally:
                if not server._lifespan_closed:
                    await wait(server.shutdown(), 6)


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect", "pending-cancel"])
async def test_loss_before_body_admission_submits_nothing_and_leaves_slot_reusable(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    loss: str,
) -> None:
    async with service(process_credential, monkeypatch, config) as d:
        client = Client(body=_json(BODY), before_body=loss)
        task, _ = d.submit(client)
        if loss == "cancel":
            await reached(client.body_entered, task, client)
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await wait(task)
        assert not d.core.calls and not client.messages
        frames(await d.service.request(ROUTE, BODY), [started(), terminal()])


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect", "stop"])
async def test_registered_job_lost_before_first_owner_step_cannot_admit_late_source(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    loss: str,
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    owners: list[weakref.ReferenceType[asyncio.Task[Any]]] = []
    original = FollowStream._own

    async def delayed(self: FollowStream, *args: Any, **kwargs: Any) -> None:
        owner = asyncio.current_task()
        assert owner is not None
        owners.append(weakref.ref(owner))
        entered.set()
        await release.wait()
        await original(self, *args, **kwargs)

    async with service(process_credential, monkeypatch, config) as d:
        with monkeypatch.context() as local:
            local.setattr(FollowStream, "_own", delayed)
            task, client = d.submit()
            try:
                await reached(entered, task, client)
                if loss == "cancel":
                    task.cancel()
                elif loss == "disconnect":
                    client.disconnected.set()
                else:
                    d.service.launch_context.request_stop()
                await flush()
                gc.collect()
                owner = owners[0]()
                assert owner is not None and not owner.done()
                assert not d.core.calls and not task.done()
                if loss != "stop":
                    _error(
                        await d.service.request(ROUTE, BODY),
                        503,
                        "service",
                        "follow_capacity",
                    )
                release.set()
                await wait(asyncio.gather(task, return_exceptions=True))
                assert not d.core.calls
            finally:
                release.set()
        if loss == "stop":
            _error(await d.service.request(ROUTE, BODY), 503, "service", "stopping")
        else:
            frames(await d.service.request(ROUTE, BODY), [started(), terminal()])


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("phase", ["pull", "send"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
async def test_lost_delivery_retains_job_until_close_ack_despite_repeated_waiter_loss(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    phase: str,
    loss: str,
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    closes: list[weakref.ReferenceType[asyncio.Task[Any]]] = []

    class ClosingSource(Subscription):
        async def close(self) -> None:
            owner = asyncio.current_task()
            assert owner is not None
            closes.append(weakref.ref(owner))
            entered.set()
            await release.wait()
            await super().close()

    async with service(process_credential, monkeypatch, config) as d:
        source = ClosingSource(
            start(), [] if phase == "pull" else [follow.FollowBatch(None, (rx(),))]
        )
        original = d.service.runtime.start_follow

        async def admit(request: follow.FollowRequest) -> Any:
            assert request.session_id.value == BODY["session_id"]
            return source

        monkeypatch.setattr(d.service.runtime, "start_follow", admit)
        client = (
            FrameClient(body=_json(BODY))
            if phase == "send"
            else Client(body=_json(BODY))
        )
        task, _ = d.submit(client)
        try:
            await reached(
                client.blocked if isinstance(client, FrameClient) else source.entered,
                task,
                client,
            )
            if loss == "cancel":
                task.cancel()
            else:
                client.disconnected.set()
            await wait(entered.wait())
            for _ in range(3):
                task.cancel()
                await flush()
                gc.collect()
                owner = closes[0]()
                assert owner is not None and not owner.done()
                assert not source.closed.is_set() and not task.done()
                _error(
                    await d.service.request(ROUTE, BODY),
                    503,
                    "service",
                    "follow_capacity",
                )
            release.set()
            await wait(asyncio.gather(task, return_exceptions=True))
            assert source.closed.is_set() and len(closes) == 1 and source.active == 0
            assert client.headers[b"cache-control"] == b"no-store"
            assert b'"terminal"' not in emitted(client)
            assert not any(m.get("more_body") is False for m in client.messages)
            monkeypatch.setattr(d.service.runtime, "start_follow", original)
            frames(await d.service.request(ROUTE, BODY), [started(), terminal()])
        finally:
            release.set()
            if isinstance(client, FrameClient):
                client.release_send.set()


@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced"])
@pytest.mark.parametrize("phase", ["admission", "head", "page"])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.parametrize("shutdown", [False, True])
async def test_native_query_lost_client_owns_slot_and_joins_before_lifespan_detach(
    account_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend: int,
    phase: str,
    loss: str,
    shutdown: bool,
) -> None:
    async with live(account_home, tmp_path, monkeypatch, backend) as d:
        from tests.contract.test_follow_lifetime import worker_gate

        c, s = d.case, d.service
        task = None
        if phase != "admission":
            task, client = d.submit()
            await reached(client.publication, task, client)
            await until(lambda: len(c.queries.requests) >= 2 and c.queries.active == 0)
        async with worker_gate(
            monkeypatch, head=phase != "page", after_materialization=phase == "page"
        ) as gate:
            if phase == "admission":
                task, client = d.submit()
            else:
                await c.emit(b"eligible\0\xff", 1)
            assert task is not None
            await wait(gate.entered.wait())
            assert c.queries.active == 1
            if loss == "disconnect":
                client.disconnected.set()
            else:
                task.cancel()
            await flush()
            assert not task.done() and c.queries.cancelled == 0
            _error(
                await s.request(ROUTE, {"session_id": c.journal.session_id.value}),
                503,
                "service",
                "follow_capacity",
            )
            if shutdown:
                s.launch_context.request_stop()
                await s.lifespan.incoming.put({"type": "lifespan.shutdown"})
                await flush()
            for _ in range(3):
                task.cancel()
                if shutdown:
                    assert s.lifespan.task is not None
                    s.lifespan.task.cancel()
                await flush()
                assert not task.done() and c.probe.close_calls == 0
                assert c.queries.active == 1 and c.queries.cancelled == 0
                assert s.launch_context.final_status is None
                _t021_held(account_home)
            gate.release.set()
            await wait(asyncio.gather(task, return_exceptions=True))
        assert c.queries.active == c.queries.cancelled == 0
        if shutdown:
            assert (await wait(s.lifespan.outgoing.get()))[
                "type"
            ] == "lifespan.shutdown.complete"
            assert s.lifespan.task is not None
            await wait(s.lifespan.task)
            assert c.probe.close_calls == c.fixture.connection.close_calls == 1
            assert c.probe.trace.index("query.finished") < c.probe.trace.index(
                "recorder.close"
            )
            assert s.launch_context.final_status.owner_settled
        else:
            assert s.runtime.status().state is RuntimeState.ACTIVE
            assert c.probe.close_calls == c.fixture.connection.close_calls == 0
            replacement, peer = d.submit()
            await reached(peer.publication, replacement, peer)
            assert peer.status == 200
            peer.disconnected.set()
            await wait(asyncio.gather(replacement, return_exceptions=True))


@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced"])
@pytest.mark.parametrize("trickle", [False, True], ids=["stalled", "progress"])
async def test_stalled_record_deadline_releases_only_follow_while_real_workflows_continue(
    account_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend: int,
    trickle: bool,
) -> None:
    class SlowClient(FrameClient):
        progress = 0

        async def send(self, message: Message) -> None:
            body = message.get("body", b"")
            if trickle and body and json.loads(body).get("type") == "record":
                self.blocked.set()
                self.attempts.append("record")
                try:
                    while True:
                        await asyncio.sleep(0.05)
                        self.progress += 1
                except asyncio.CancelledError:
                    self.send_cancelled += 1
                    raise
            await super().send(message)

    async with live(account_home, tmp_path, monkeypatch, backend) as d:
        c, s = d.case, d.service
        session = c.journal.session_id.value
        report = asyncio.create_task(
            s.request(
                "/v1/observation/monitor",
                {
                    "session_id": session,
                    "condition_base64": "UEFTUw==",
                    "timeout_ms": 1000,
                    "max_rx_bytes": 1024,
                },
            )
        )
        try:
            await wait(c.clock.wait_started.wait())
            client = SlowClient(body=_json({"session_id": session}))
            task, _ = d.submit(client)
            await reached(client.publication, task, client)
            record = await c.emit(b"pending\0\xff", 1)
            await reached(client.blocked, task, client)
            began = asyncio.get_running_loop().time()
            receipt = await s.request(
                "/v1/observation/annotations",
                {
                    "session_id": session,
                    "text": "while send is blocked",
                    "client_surface": "http",
                },
            )
            assert receipt.status == 200
            retrieved = await s.request(
                "/v1/evidence/record",
                {"session_id": session, "sequence": record.sequence},
            )
            assert retrieved.status == 200 and b"cGVuZGluZwD/" in retrieved.payload
            await c.emit(b"PASS", 2)
            assert json.loads((await wait(report)).payload)["outcome"] == "matched"
            assert not task.done() and c.probe.close_calls == 0
            await wait(task, 6.5)
            assert 4.5 <= asyncio.get_running_loop().time() - began <= 6.5
            assert client.send_cancelled == 1 and client.attempts == [
                "started",
                "record",
            ]
            assert client.progress >= 10 if trickle else client.progress == 0
            assert json.loads(emitted(client))["type"] == "started"
            assert client.headers[b"cache-control"] == b"no-store"
            assert not any(m.get("more_body") is False for m in client.messages)
            assert s.runtime.status().state is RuntimeState.ACTIVE
            assert c.fixture.connection.close_calls == c.probe.close_calls == 0
            replacement, peer = d.submit()
            await reached(peer.publication, replacement, peer)
            assert peer.status == 200
            peer.disconnected.set()
            await wait(asyncio.gather(replacement, return_exceptions=True))
        finally:
            if not report.done():
                report.cancel()
            await asyncio.gather(report, return_exceptions=True)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"], ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced"])
async def test_actual_loopback_peer_exit_leaves_monitor_annotation_reads_and_rx_independent(
    account_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    backend: int,
) -> None:
    async with network(account_home, tmp_path, monkeypatch, backend, host) as (
        d,
        url,
        _,
    ):
        c = d.case
        headers = {
            "Authorization": "Bearer " + d.service.token.decode(),
            "Content-Type": "application/json",
        }
        session = c.journal.session_id.value
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=3
        ) as client:
            report = asyncio.create_task(
                client.post(
                    url + "/v1/observation/monitor",
                    headers=headers,
                    json={
                        "session_id": session,
                        "condition_base64": "UEFTUw==",
                        "timeout_ms": 1000,
                        "max_rx_bytes": 1024,
                    },
                )
            )
            try:
                await wait(c.clock.wait_started.wait())
                async with client.stream(
                    "POST", url + ROUTE, headers=headers, json={"session_id": session}
                ) as response:
                    assert (
                        response.status_code == 200
                        and response.headers["cache-control"] == "no-store"
                    )
                    lines = response.aiter_lines()
                    first = json.loads(await wait(anext(lines)))
                    assert first["type"] == "started" and first["start_sequence"] == 2
                    receipt = await client.post(
                        url + "/v1/observation/annotations",
                        headers=headers,
                        json={
                            "session_id": session,
                            "text": "ambient assertion",
                            "client_surface": "http",
                        },
                    )
                    assert receipt.status_code == 200
                    value = json.loads(await wait(anext(lines)))
                    assert (
                        value["type"] == "record"
                        and value["record"]["kind"] == "client_annotation"
                        and value["record"]["sequence"] == 2
                    )
                    source = d.sources[0]
                await wait(d.closed[id(source)].wait())
                assert not report.done() and c.probe.close_calls == 0
                record = await c.emit(b"PASS\0\xff", 1)
                result = await wait(report)
                assert (
                    result.status_code == 200 and result.json()["outcome"] == "matched"
                )
                retrieved = await client.post(
                    url + "/v1/evidence/record",
                    headers=headers,
                    json={"session_id": session, "sequence": record.sequence},
                )
                assert retrieved.status_code == 200 and b"UEFTUwD/" in retrieved.content
                assert (
                    c.fixture.connection.consumer_calls == 1
                    and c.fixture.connection.close_calls == 0
                )
                assert c.probe.close_calls == 0 and c.queries.active == 0
                async with client.stream(
                    "POST", url + ROUTE, headers=headers, json={"session_id": session}
                ) as replacement:
                    assert replacement.status_code == 200
                    again = json.loads(await wait(anext(replacement.aiter_lines())))
                    assert again["type"] == "started" and again["start_sequence"] == 5
            finally:
                if not report.done():
                    report.cancel()
                await asyncio.gather(report, return_exceptions=True)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"], ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced"])
async def test_actual_loopback_stop_seals_before_drain_but_heartbeats_while_native_query_joins(
    account_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    backend: int,
) -> None:
    async with network(account_home, tmp_path, monkeypatch, backend, host) as (
        d,
        url,
        server,
    ):
        from tests.contract.test_follow_lifetime import worker_gate

        c, s = d.case, d.service
        headers = {
            "Authorization": "Bearer " + s.token.decode(),
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=3
        ) as client:
            async with client.stream(
                "POST",
                url + ROUTE,
                headers=headers,
                json={"session_id": c.journal.session_id.value},
            ) as response:
                assert (
                    response.status_code == 200
                    and response.headers["cache-control"] == "no-store"
                )
                lines = response.aiter_lines()
                first = json.loads(await wait(anext(lines)))
                assert first["start_sequence"] == 1
                await until(
                    lambda: len(c.queries.requests) >= 2 and c.queries.active == 0
                )
                async with worker_gate(
                    monkeypatch, head=False, after_materialization=True
                ) as gate:
                    await c.emit(b"materialized but never offered", 1)
                    await wait(gate.entered.wait())
                    entered = asyncio.Event()
                    original = server._wait_tasks_to_complete

                    async def drain() -> None:
                        assert s.launch_context.stopping
                        with pytest.raises(follow.FollowRejected, match="not_active"):
                            await s.runtime.start_follow(c.request())
                        entered.set()
                        await original()

                    monkeypatch.setattr(server, "_wait_tasks_to_complete", drain)
                    stopping = asyncio.create_task(server.shutdown())
                    try:
                        await wait(entered.wait())
                        queries, samples = (
                            len(c.queries.requests),
                            tuple(c.clock.samples),
                        )
                        assert await wait(anext(lines), 2) == '{"type":"heartbeat"}'
                        assert not stopping.done() and not gate.release.is_set()
                        assert c.queries.active == 1 and c.queries.cancelled == 0
                        assert (
                            len(c.queries.requests) == queries
                            and tuple(c.clock.samples) == samples
                        )
                        assert (
                            c.probe.close_calls == 0
                            and s.launch_context.final_status is None
                        )
                        _t021_held(account_home)
                        gate.release.set()
                        assert json.loads(await wait(anext(lines))) == terminal(
                            "service_stopping", 1, None
                        )
                        with pytest.raises(StopAsyncIteration):
                            await wait(anext(lines))
                        await wait(stopping)
                        assert (
                            c.probe.close_calls == 0
                            and c.queries.active == c.queries.cancelled == 0
                        )
                        await s.lifespan.finish()
                        assert (
                            c.probe.close_calls == c.fixture.connection.close_calls == 1
                        )
                    finally:
                        gate.release.set()
                        await wait(asyncio.gather(stopping, return_exceptions=True))


@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.parametrize("cutoff", [None, 9])
@pytest.mark.parametrize("fault", ["none", "record", "terminal", "eof"])
async def test_terminal_uses_only_completed_offered_prefix_and_failed_delivery_never_retries(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
    cutoff: int | None,
    fault: str,
) -> None:
    class LostSend(Client):
        attempts: list[str]

        async def send(self, message: Message) -> None:
            body = message.get("body", b"")
            if message["type"] == "http.response.body":
                kind = json.loads(body)["type"] if body else "eof"
                selected = kind == fault and (
                    kind != "record" or json.loads(body)["record"]["sequence"] == 4
                )
                self.attempts.append(kind)
                if selected:
                    raise OSError(PRIVATE)
            await super().send(message)

    async with service(process_credential, monkeypatch) as d:
        d.core.captured = start(device)
        records = tuple(rx(n, device=device) for n in range(3, 6))
        d.core.items = [
            follow.FollowBatch(None, records),
            follow.FollowEnd("detached", cutoff),
        ]
        client = LostSend(body=_json(BODY))
        client.attempts = []
        task, _ = d.submit(client)
        await wait(task)
        expected = [started(device)]
        expected += [
            {"type": "record", "record": rx_wire(r)}
            for r in records[: 1 if fault == "record" else 3]
        ]
        if fault in ("none", "eof"):
            expected.append(terminal("detached", 6, cutoff))
        assert client.status == 200
        assert client.headers[b"content-type"] == b"application/x-ndjson"
        assert client.headers[b"cache-control"] == b"no-store"
        assert (
            b"content-length" not in client.headers
            and b"content-encoding" not in client.headers
        )
        assert emitted(client) == b"".join(wire_bytes(frame) for frame in expected)
        assert d.core.subscriptions[0].closed.is_set()
        assert client.attempts.count("terminal") == (0 if fault == "record" else 1)
        assert any(m.get("more_body") is False for m in client.messages) == (
            fault == "none"
        )


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize(
    "case,status,code",
    [
        ("peer", 403, "peer_rejected"),
        ("host", 400, "host_rejected"),
        ("origin", 403, "origin_rejected"),
        ("fetch", 403, "origin_rejected"),
        ("missing_auth", 401, "authentication_required"),
        ("duplicate_auth", 401, "authentication_required"),
        ("query", 400, "query_not_allowed"),
        ("upgrade", 400, "upgrade_rejected"),
        ("authorized", 503, "stopping"),
    ],
)
async def test_security_and_no_store_precede_body_even_when_stopped_cleanup_owns_follow_slot(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    case: str,
    status: int,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    entered, release = asyncio.Event(), asyncio.Event()
    async with service(process_credential, monkeypatch, config) as d:
        d.core.items = []
        task, client = d.submit()
        try:
            await reached(client.publication, task, client)
            sub = d.core.subscriptions[0]
            original = sub.close

            async def close() -> None:
                entered.set()
                await release.wait()
                await original()

            monkeypatch.setattr(sub, "close", close)
            client.disconnected.set()
            await wait(entered.wait())
            d.service.launch_context.request_stop()
            scope = d.service.scope(ROUTE)
            headers = list(scope["headers"])
            if case == "peer":
                scope["client"] = ("192.0.2.1", 1234)
            elif case == "host":
                headers = [
                    (k, b"localhost:8765" if k == b"host" else v) for k, v in headers
                ]
            elif case in ("origin", "fetch", "upgrade"):
                headers.append(
                    (
                        {
                            "origin": b"origin",
                            "fetch": b"sec-fetch-site",
                            "upgrade": b"upgrade",
                        }[case],
                        PRIVATE.encode(),
                    )
                )
            elif case == "missing_auth":
                headers = [(k, v) for k, v in headers if k != b"authorization"]
            elif case == "duplicate_auth":
                headers.append((b"authorization", b"Bearer " + d.service.token))
            elif case == "query":
                scope["query_string"] = b"token=" + PRIVATE.encode()
            scope["headers"] = headers
            response = await d.service.request(
                ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
            )
            _error(
                response, status, "service" if case == "authorized" else "request", code
            )
            assert (
                not task.done() and not sub.closed.is_set() and len(d.core.calls) == 1
            )
            assert (
                PRIVATE not in caplog.text
                and d.service.token.decode() not in caplog.text
            )
            assert (
                PRIVATE.encode() not in response.payload
                and d.service.token not in response.payload
            )
        finally:
            release.set()
            await wait(asyncio.gather(task, return_exceptions=True))
