"""012 T024: service ownership and client loss, with real Core/SQLite evidence.

Gates delay actual write/append work; they never implement cancellation or stop
policy. Socket/drain cases use guarded numeric loopback and the real controlled
server. Bootstrap fault cases use the established 006 process-lifetime harness.
"""

import asyncio
import importlib
import json
import signal
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from dutchmate_core import evidence, model
from uvicorn.lifespan.off import LifespanOff

from dutchmate_service.bootstrap import (
    BootstrapFailure,
    PrivateBootstrap,
    ServiceConfig,
)
from dutchmate_service.server import _ControlledServer
from test_evidence_http import _error, _json
from test_interact_http import (
    BODY,
    ROUTE,
    active_service,
    core_helpers,
    hold_service_owner,
    reached,
    wait,
)
from test_service_http import _T011Composition
from test_service_http import process_credential as process_credential
from test_service_http import t011_composition as t011_composition
from test_service_runtime import Client, _t021_held, _t021_server, _T021Launch, flush


@pytest.mark.asyncio
@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("loss", ["disconnect", "cancel"])
@pytest.mark.parametrize(
    "phase",
    [
        "intent-commit",
        "intent-ack",
        "write",
        "tx-commit",
        "tx-ack",
        "end-commit",
        "end-ack",
    ],
)
async def test_repeated_delivery_loss_retains_slot_and_joins_every_resource_boundary(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
    loss: str,
    phase: str,
) -> None:
    async with active_service(process_credential, monkeypatch, tmp_path, device) as (
        s,
        c,
    ):
        gate = None
        if phase != "write":
            kind, point = phase.split("-")
            record_kind = {
                "intent": "interact_started",
                "tx": "uart_tx_settled",
                "end": "interact_ended",
            }[kind]
            boundary = c.recorder.gates[record_kind]
            gate = boundary.commit if point == "commit" else boundary.acknowledgement
            gate.allow.clear()
        body = {**BODY, "session_id": c.journal.session_id.value}
        delivery, client = s.submit(Client(body=_json(body)))
        if phase.startswith("intent"):
            assert gate is not None
            await reached(gate.entered, delivery, client)
        else:
            await reached(c.writer.entered, delivery, client)
            if phase != "write":
                assert gate is not None
                await c.rx(b"PASS")
                c.writer.allow.set()
                await reached(gate.entered, delivery, client)
        for _ in range(3):
            if loss == "disconnect":
                client.disconnected.set()
            else:
                delivery.cancel()
            await flush()
            assert not delivery.done()
            _error(await s.request(ROUTE, body), 503, "service", "interact_capacity")
            assert (
                not c.writer.close_entered.is_set() and not c.recorder.closed.is_set()
            )
            assert s.runtime.status().state.value == "active"
        if gate is not None:
            gate.allow.set()
        c.writer.allow.set()
        with pytest.raises(asyncio.CancelledError):
            await wait(delivery)
        await flush()
        records = await c.records()
        starts = [r for r in records if isinstance(r, model.InteractStartedEvidence)]
        txs = [r for r in records if isinstance(r, model.UartTxSettledEvidence)]
        ends = [r for r in records if isinstance(r, model.InteractEndedEvidence)]
        assert len(starts) == len(txs) == len(ends) == 1
        suppressed = phase.startswith("intent")
        assert len(c.writer.calls) == int(not suppressed)
        assert txs[0].tx.submitted is (not suppressed)
        assert ends[0].outcome.value == (
            "cancelled" if suppressed or phase == "write" else "matched"
        )
        assert c.writer.cancellation_signals == 0
        assert c.fixture.connection.consumer_calls == 1
        # A completed owner releases its slot without detaching/replaying the first job.
        next_delivery, next_client = s.submit(Client(body=_json(body)))
        await wait(c.recorder.acks["interact_started"].get())  # first operation
        await wait(c.recorder.acks["interact_started"].get())  # next operation
        next_client.disconnected.set()
        with pytest.raises(asyncio.CancelledError):
            await wait(next_delivery)
        assert s.runtime.status().state.value == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("loss", ["none", "disconnect", "cancel"])
async def test_registered_before_stop_owner_is_joined_without_core_admission(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
    loss: str,
) -> None:
    async with active_service(process_credential, monkeypatch, tmp_path, device) as (
        s,
        c,
    ):
        body = {**BODY, "session_id": c.journal.session_id.value}
        with hold_service_owner() as (entered, release):
            delivery, client = s.submit(Client(body=_json(body)))
            await reached(entered, delivery, client)
            _error(await s.request(ROUTE, body), 503, "service", "interact_capacity")
            if loss == "disconnect":
                client.disconnected.set()
            elif loss == "cancel":
                delivery.cancel()
            await flush()
            s.launch_context.request_stop()
            shutdown = asyncio.create_task(s.lifespan.finish())
            try:
                await flush()
                assert not shutdown.done() and not delivery.done()
                assert c.writer.calls == []
                assert c.recorder.attempts == ["segment_started"]
            finally:
                release.set()
            result = await wait(asyncio.gather(delivery, return_exceptions=True))
            if loss == "none":
                assert len(result) == 1 and result[0] is None
                _error(client, 503, "service", "stopping")
            else:
                assert isinstance(result[0], asyncio.CancelledError)
            await wait(shutdown)
            assert c.writer.calls == []
            assert not any(
                isinstance(r, model.InteractStartedEvidence)
                for r in c.recorder.committed
            )
            assert s.launch_context.final_status.owner_settled


@pytest.mark.asyncio
@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("host", ["127.0.0.1", "::1"], ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("peer_loss", [False, True], ids=["connected", "peer-lost"])
async def test_controlled_loopback_drain_seals_synchronously_and_waits_for_write_and_both_audits(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    account_home: Path,
    device: bool,
    host: str,
    peer_loss: bool,
) -> None:
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        if family == socket.AF_INET6:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind((host, 0))
        listener.listen(128)
        listener.setblocking(False)
        config = ServiceConfig(listener.getsockname()[1], host)
        async with active_service(
            process_credential, monkeypatch, tmp_path, device, config
        ) as (s, c):
            server = _ControlledServer(
                uvicorn.Config(
                    s.app,
                    host=host,
                    port=config.port,
                    lifespan="off",
                    log_config=None,
                    access_log=False,
                    proxy_headers=False,
                ),
                s.launch_context,
            )
            server.config.load()

            class Lifespan(LifespanOff):
                shutdown_failed = False

                async def shutdown(self) -> None:
                    await s.lifespan.finish()

            server.lifespan = Lifespan(server.config)
            await wait(server.startup(sockets=[listener]))
            reader, peer = await asyncio.open_connection(host, config.port)
            body = _json({**BODY, "session_id": c.journal.session_id.value})
            authority = (
                f"[{host}]:{config.port}" if host == "::1" else f"{host}:{config.port}"
            )
            peer.write(
                (
                    f"POST {ROUTE} HTTP/1.1\r\nHost: {authority}\r\nAuthorization: Bearer {s.token.decode()}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
                ).encode()
                + body
            )
            await peer.drain()
            shutdown = None
            tx_gate = c.recorder.gates["uart_tx_settled"].acknowledgement
            end_gate = c.recorder.gates["interact_ended"].acknowledgement
            tx_gate.allow.clear()
            end_gate.allow.clear()
            original_seal = s.launch_context._seal_interacts
            seals: list[str] = []

            def sealed() -> None:
                assert original_seal is not None
                original_seal()
                seals.append("sealed")

            monkeypatch.setattr(s.launch_context, "_seal_interacts", sealed)
            try:
                await wait(c.writer.entered.wait())
                if peer_loss:
                    peer.close()
                    await peer.wait_closed()
                    await flush()
                for connection in tuple(server.server_state.connections):
                    original = connection.shutdown

                    def drain_connection(original: Any = original) -> None:
                        assert seals and s.launch_context.stopping
                        assert not c.writer.allow.is_set()
                        original()

                    monkeypatch.setattr(connection, "shutdown", drain_connection)
                shutdown = asyncio.create_task(server.shutdown())
                await flush()
                assert seals and s.launch_context.stopping
                assert not shutdown.done() and not c.writer.close_entered.is_set()
                root = account_home / ".local/state/dutchmate/service"
                assert (root / "credential").read_bytes() == s.token + b"\n"
                assert (
                    json.loads((root / "owner.json").read_bytes())["cleanup_confirmed"]
                    is False
                )
                c.writer.allow.set()
                await wait(tx_gate.entered.wait())
                assert not shutdown.done() and not c.recorder.closed.is_set()
                assert server.server_state.tasks
                tx_gate.allow.set()
                await wait(end_gate.entered.wait())
                assert not shutdown.done() and not c.recorder.closed.is_set()
                assert (root / "credential").exists()
                end_gate.allow.set()
                await wait(shutdown)
                assert not server.server_state.tasks
                assert c.writer.active_at_close == [0]
                assert c.writer.cancellation_signals == 0 and len(c.writer.calls) == 1
                assert c.recorder.closed.is_set() and not c.recorder.close_during_append
                assert s.launch_context.final_status.owner_settled
                ends = [
                    r
                    for r in c.recorder.committed
                    if isinstance(r, model.InteractEndedEvidence)
                ]
                assert len(ends) == 1 and ends[0].outcome.value in {
                    "cancelled",
                    "service_stopping",
                }
                if not peer_loss:
                    raw = await wait(reader.read())
                    assert (
                        raw.count(b"HTTP/1.1") == 1
                        and b'"outcome":"service_stopping"' in raw
                    )
            finally:
                c.recorder.release()
                c.writer.allow.set()
                peer.close()
                await peer.wait_closed()
                if shutdown is not None:
                    await wait(shutdown)
                else:
                    await wait(server.shutdown())


@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("uncertain", ["none", "journal", "transport"])
def test_process_guard_keeps_marker_false_until_join_and_never_repairs_cleanup_uncertainty(
    account_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    device: bool,
    uncertain: str,
) -> None:
    core = core_helpers(monkeypatch)
    recording = importlib.import_module("tests.contract.test_interact_recording")
    sqlite = importlib.import_module("dutchmate_core.adapters.sqlite_evidence")
    launch = _T021Launch(account_home, t011_composition)
    state: dict[str, Any] = {}

    async def scenario(http: Any, s: Any) -> None:
        journal = await sqlite.SqliteEvidenceJournal.create_v4(
            tmp_path / "owned.sqlite3", recording.POLICY
        )
        c = core.RuntimeCase(
            journal,
            core.BACKEND_FIXTURE_FACTORIES[int(device)],
            monkeypatch,
            path=tmp_path / "owned.sqlite3",
            owner=s.runtime,
        )
        state["case"] = c
        await c.attach()
        if uncertain != "none":
            target = c.recorder if uncertain == "journal" else c.fixture.connection
            original = target.close

            async def close_uncertain() -> None:
                await original()
                if uncertain == "journal":
                    raise evidence.JournalFailure(
                        evidence.JournalOperation.CLOSE,
                        evidence.JournalFailureKind.IO_FAILURE,
                    )
                raise RuntimeError(
                    "test-only unconfirmed transport close acknowledgement"
                )

            monkeypatch.setattr(target, "close", close_uncertain)
        from test_evidence_http import ReadBoundary, Service

        gateway = Service(s.app, s.config, s.token, ReadBoundary(), http._context)
        client = Client(body=_json({**BODY, "session_id": journal.session_id.value}))

        async def deliver() -> None:
            await gateway.app(gateway.scope(ROUTE), client.receive, client.send)

        delivery = asyncio.create_task(deliver())
        state["delivery"], state["client"] = delivery, client
        await reached(c.writer.entered, delivery, client)
        c.recorder.gates["interact_ended"].acknowledgement.allow.clear()
        client.disconnected.set()
        await flush()
        launch.emit(signal.SIGINT)
        launch.emit(signal.SIGINT)
        assert http.should_exit and not http.force_exit

    async def drain(http: Any, s: Any) -> None:
        c = state["case"]
        _t021_held(account_home)
        assert http._context.stopping
        assert not c.writer.allow.is_set() and not c.recorder.closed.is_set()
        assert (
            "marker.true" not in launch.trace
            and "token.invalidated" not in launch.trace
        )
        assert launch.owners[0].credential is not None
        c.writer.allow.set()
        gate = c.recorder.gates["interact_ended"].acknowledgement
        await wait(gate.entered.wait())
        assert not state["delivery"].done()
        assert not c.writer.close_entered.is_set() and not c.recorder.closed.is_set()
        gate.allow.set()
        with pytest.raises(asyncio.CancelledError):
            await wait(state["delivery"])
        launch.trace.append("interact.joined")

    launch.scenario, launch.at_drain = scenario, drain
    launch.install(monkeypatch)
    if uncertain == "none":
        _t021_server().run_service(ServiceConfig(8765))
    else:
        with pytest.raises(BootstrapFailure) as failed:
            _t021_server().run_service(ServiceConfig(8765))
        assert failed.value.kind.value == "teardown_incomplete"
    c = state["case"]
    final = launch.settled[id(launch.runtimes[0])]
    assert final.owner_settled and c.recorder.closed.is_set()
    assert final.recorder_close_confirmed is (uncertain != "journal")
    assert final.physical_release_confirmed is (uncertain != "transport")
    assert c.writer.active_at_close == [0] and c.writer.cancellation_signals == 0
    assert state["delivery"].done() and c.fixture.connection.closed
    assert (
        launch.trace.index("interact.joined")
        < launch.trace.index("token.invalidated")
        < launch.trace.index("owner.release")
    )
    assert ("marker.true" in launch.trace) is (uncertain == "none")
    assert json.loads((launch.root / "owner.json").read_bytes())[
        "cleanup_confirmed"
    ] is (uncertain == "none")
    assert not (launch.root / "credential").exists()
    if uncertain != "none":
        with pytest.raises(BootstrapFailure) as refused:
            PrivateBootstrap.acquire(ServiceConfig(8766))
        assert refused.value.kind.value == "previous_cleanup_unconfirmed"


@pytest.mark.asyncio
@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("message_type", ["http.response.start", "http.response.body"])
async def test_response_send_failure_after_final_decision_never_rewrites_or_replays_audit(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
    message_type: str,
) -> None:
    async with active_service(process_credential, monkeypatch, tmp_path, device) as (
        s,
        c,
    ):

        class FailedSend(Client):
            async def send(self, message: Any) -> None:
                if message["type"] == message_type:
                    raise BrokenPipeError("test-only lost response peer")
                await super().send(message)

        client = FailedSend(
            body=_json({**BODY, "session_id": c.journal.session_id.value})
        )
        delivery, _ = s.submit(client)
        await reached(c.writer.entered, delivery, client)
        await c.rx(b"PASS")
        c.writer.allow.set()
        with pytest.raises(RuntimeError, match="^service/internal_failure$") as failed:
            await wait(delivery)
        assert failed.value.__context__ is None
        records = await c.records()
        ends = [r for r in records if isinstance(r, model.InteractEndedEvidence)]
        assert len(ends) == 1 and ends[0].outcome.value == "matched"
        assert ends[0].tx.submitted and ends[0].tx.status == "acknowledged"
        assert len(c.writer.calls) == 1 and c.writer.cancellation_signals == 0
        assert s.runtime.status().state.value == "active"
        assert not c.writer.close_entered.is_set() and not c.recorder.closed.is_set()
        # A failed send cannot retain a settled slot or create a replacement job.
        assert await c.records() == records
        _error(
            await s.request(ROUTE, {**BODY, "session_id": "other-session"}),
            409,
            "interact",
            "session_not_associated",
        )
        s.launch_context.request_stop()
        await s.lifespan.finish()
        assert s.launch_context.final_status.owner_settled
        assert (
            len(
                [
                    r
                    for r in c.recorder.committed
                    if isinstance(r, model.InteractEndedEvidence)
                ]
            )
            == 1
        )
