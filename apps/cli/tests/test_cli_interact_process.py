"""012 T026/T027: guarded installed Interact and source/artifact audits.

007/008 builders and independent child account/device guards stay unchanged.
Only fake backend work, clock progress and durable append acknowledgements are
controlled. Product admission, matching, arbitration, persistence, delivery and
shutdown are real installed code. No checkout product paths enter child imports.
"""

import ast
import base64
import csv
import hashlib
import io
import json
import re
import signal
import tarfile
import tomllib
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from email.parser import BytesParser
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from apps.cli.tests import test_cli_evidence_process as support
    from apps.cli.tests import test_cli_follow_process as streams
    from apps.cli.tests import test_cli_process as process
    from apps.cli.tests.test_cli_process import _Installed
else:
    from importlib import import_module

    support = import_module("test_cli_evidence_process")
    streams = import_module("test_cli_follow_process")
    process = import_module("test_cli_process")
    _Installed = process._Installed

package_artifacts = process.package_artifacts
stack_artifacts = support.stack_artifacts
installed_stack = support.installed_stack
native_service_helper = process.native_service_helper

_PACKAGE_ROOTS = {
    "dutchmate-core": process._REPO / "core",
    "dutchmate-service": process._REPO / "apps/service",
    "dutchmate-cli": process._REPO / "apps/cli",
}

_PAYLOAD = bytes(range(256)) + b"\0\xffSEND\r\n"
_CONDITIONS = (b"PASS", b"\0\xffOK")
_RX = b"unrelated\xff\0\xffOK-tail\r\n"
_TIME = 5_000_000_000

_EXTENSION = r"""
from dutchmate_core import evidence, backend as backend_contract, interact, monitor
import dutchmate_service.interact_http, dutchmate_core.runtime
# Restore the production projection: the inherited evidence fault wrapper is v1-only.
app.evidence_response = actual_response
audit.update(write_calls=[], write_pending=False, write_finished=0, write_cancelled=0,
    write_status="full", intents=0, txs=0, ends=0, pending_intent=False, pending_tx=False,
    pending_end=False, audit_faults=[], hold_intent=False, hold_tx=False, hold_end=False,
    released=False, clock_ns=5000000000, trace=[], record_heads=[], last_end=None,
    interact_reports=0, last_report=None, emissions=0, http_drained=False,
    monitor_starts=0, annotations=0, interact_waiters=0)
write_release = asyncio.Event()
intent_release, tx_release, end_release = asyncio.Event(), asyncio.Event(), asyncio.Event()
for gate in (intent_release, tx_release, end_release): gate.set()
clock_tick = asyncio.Event()
class Clock(composition.MonotonicMonitorClock):
    def now_ns(self): return audit["clock_ns"]
    async def wait_until(self, deadline):
        while self.now_ns() < deadline:
            await clock_tick.wait()
            clock_tick.clear()
composition.MonotonicMonitorClock = Clock
original_backend = backend
def backend(selector, configuration, line_intent, *, write_enabled=False):
    value = original_backend(selector, configuration, line_intent)
    connection = value.connection
    if write_enabled:
        connection.descriptor = dataclasses.replace(connection.descriptor,
            capabilities=model.BackendCapabilities(frozenset({
                *connection.descriptor.capabilities.values, model.BackendCapability.UART_SEND})))
        async def write(data):
            audit["write_calls"].append(data.hex())
            audit["write_pending"] = True
            audit["trace"].append("write.enter")
            publish()
            try:
                await write_release.wait()
                kind = audit["write_status"]
                if kind == "malformed": return object()
                status, count, failure = {
                    "full": (backend_contract.BackendWriteStatus.ACKNOWLEDGED, len(data), None),
                    "partial": (backend_contract.BackendWriteStatus.PARTIAL, len(data)//2, None),
                    "zero": (backend_contract.BackendWriteStatus.PARTIAL, 0, None),
                    "timeout": (backend_contract.BackendWriteStatus.TIMEOUT, None, None),
                    "disconnected": (backend_contract.BackendWriteStatus.DISCONNECTED, None, None),
                    "failure": (backend_contract.BackendWriteStatus.FAILURE, None, backend_contract.BackendFailureKind.IO_FAILURE),
                }[kind]
                return backend_contract.BackendWriteResult(status, count, failure)
            except asyncio.CancelledError:
                audit["write_cancelled"] += 1
                raise
            finally:
                audit["write_pending"] = False
                audit["write_finished"] += 1
                audit["trace"].append("write.settled")
                publish()
        connection.write = write
    original_close = connection.close
    async def physical_close():
        assert not audit["write_pending"]
        await original_close()
        audit["trace"].append("physical.close")
        publish()
    connection.close = physical_close
    return value
composition.BasicSerialBackend = backend
tracked_append = sqlite_evidence.SqliteEvidenceJournal.append
async def append(journal, draft):
    kind = {
        evidence.PendingInteractStartedEvidence: "intent",
        evidence.PendingUartTxSettledEvidence: "tx",
        evidence.PendingInteractEndedEvidence: "end",
    }.get(type(draft))
    if kind and kind+"-before" in audit["audit_faults"]:
        raise evidence.JournalFailure(evidence.JournalOperation.APPEND,
            evidence.JournalFailureKind.IO_FAILURE, private)
    record = await tracked_append(journal, draft)
    audit["record_heads"].append([type(record).__name__, record.sequence])
    if isinstance(record, model.OperationStartedEvidence): audit["monitor_starts"] += 1
    if isinstance(record, model.ClientAnnotationEvidence): audit["annotations"] += 1
    if kind:
        audit[{"intent":"intents", "tx":"txs", "end":"ends"}[kind]] += 1
        audit["trace"].append(kind+".commit")
        if kind == "end":
            audit["last_end"] = dict(outcome=record.outcome.value,
                observation=record.observation.outcome.value,
                submitted=record.tx.submitted, status=record.tx.status,
                accepted_prefix_bytes=record.tx.accepted_prefix_bytes)
        if audit["hold_"+kind]:
            audit["pending_"+kind] = True
            publish()
            await {"intent":intent_release,"tx":tx_release,"end":end_release}[kind].wait()
            audit["pending_"+kind] = False
        if kind+"-after" in audit["audit_faults"]:
            publish()
            raise evidence.JournalFailure(evidence.JournalOperation.APPEND,
                evidence.JournalFailureKind.IO_FAILURE, private)
        audit["trace"].append(kind+".ack")
    publish()
    return record
sqlite_evidence.SqliteEvidenceJournal.append = append
tracked_close = sqlite_evidence.SqliteEvidenceJournal.close
async def close(journal):
    assert not audit["write_pending"] and not any(audit["pending_"+k] for k in ("intent","tx","end"))
    await tracked_close(journal)
    audit["trace"].append("journal.close")
    publish()
sqlite_evidence.SqliteEvidenceJournal.close = close
tracked_interact = actual_runtime.interact
async def owned_interact(owner, request):
    audit["interact_waiters"] += 1
    publish()
    try:
        return await tracked_interact(owner, request)
    finally:
        audit["interact_waiters"] -= 1
        publish()
actual_runtime.interact = owned_interact
tracked_response = app.interact_response if hasattr(app, "interact_response") else dutchmate_service.interact_http.interact_response
def response(report):
    value = tracked_response(report)
    audit["interact_reports"] += 1
    audit["last_report"] = json.loads(value.body)
    publish()
    return value
dutchmate_service.interact_http.interact_response = response
async def control():
    while True:
        if control_path.exists():
            command = json.loads(control_path.read_bytes())
            control_path.unlink()
            for key in ("write_status", "audit_faults"):
                if key in command: audit[key] = command[key]
            for key, gate in (("intent",intent_release),("tx",tx_release),("end",end_release)):
                if "hold_"+key in command:
                    audit["hold_"+key] = command["hold_"+key]
                    if audit["hold_"+key]: gate.clear()
                    else: gate.set()
            if command.get("release_write"): write_release.set()
            if command.get("release_all"):
                for gate in (intent_release, tx_release, end_release, write_release): gate.set()
                audit["released"] = True
            if "advance_ns" in command:
                audit["clock_ns"] += command["advance_ns"]
                clock_tick.set()
            for _ in range(command.get("emit_count", 1 if "emit_hex" in command else 0)):
                await fixture.connection.emit_rx(bytes.fromhex(command.get("emit_hex", "00ff")), timestamp=9)
                audit["emissions"] += 1
            if command.get("disconnect"): await fixture.connection.disconnect()
            publish()
        await asyncio.sleep(0.01)  # External test control only, never client/Core polling.
tracked_startup = uvicorn.Server.startup
async def startup(self, sockets=None):
    await tracked_startup(self, sockets=sockets)
    audit["product_files"].extend([interact.__file__, monitor.__file__, dutchmate_core.runtime.__file__,
        dutchmate_service.interact_http.__file__])
    audit["cwd"] = os.getcwd()
    publish()
uvicorn.Server.startup = startup
tracked_drain = server._ControlledServer._wait_tasks_to_complete
async def drain(self):
    assert self._context.stopping and not self.force_exit
    audit["http_drained"] = False
    audit["drain_entered"] = True
    publish()
    await tracked_drain(self)
    assert not self.force_exit
    audit["http_drained"] = True
    publish()
server._ControlledServer._wait_tasks_to_complete = drain
"""
_HOOK = "try:\n    server.run_service("
assert support._SERVICE_SCRIPT.count(_HOOK) == 1
_SERVICE_SCRIPT = support._SERVICE_SCRIPT.replace(_HOOK, _EXTENSION + "\n" + _HOOK)
_CLI_GUARD = (
    process._GUARD
    + r"""
tracked_send = httpx.AsyncClient.send
async def interact_send(self, request, *args, **kwargs):
    if request.url.path == "/v2/observation/interact":
        audit["interact_request"] = json.loads(request.content)
    response = await tracked_send(self, request, *args, **kwargs)
    audit["http_status"] = response.status_code
    audit["cache_control"] = response.headers.get("cache-control")
    return response
httpx.AsyncClient.send = interact_send
if mode == "interact-deadline":
    original_timeout = asyncio.timeout_at
    def elapsed(when):
        loop = asyncio.get_running_loop()
        assert 9 < when - loop.time() <= 10
        audit["whole_budget"] = 10
        return original_timeout(loop.time()+0.5)
    asyncio.timeout_at = elapsed
def final_interact():
    audit["core_imported"] = any(n == "dutchmate_core" or n.startswith("dutchmate_core.") for n in sys.modules)
    audit["service_imported"] = any(n == "dutchmate_service" or n.startswith("dutchmate_service.") for n in sys.modules)
    audit["cwd"] = os.getcwd()
    audit["interact_file"] = getattr(sys.modules.get("dutchmate_cli.interact"), "__file__", None)
atexit.register(final_interact)
"""
)


@pytest.fixture(autouse=True)
def interact_children(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(support, "_SERVICE_SCRIPT", _SERVICE_SCRIPT)
    monkeypatch.setattr(process, "_GUARD", _CLI_GUARD)


@pytest.fixture(params=["127.0.0.1", "::1"], ids=["ipv4", "ipv6"])
def host(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture(params=[0, 1], ids=["basic", "enhanced-shaped"])
def backend(request: pytest.FixtureRequest) -> int:
    return int(request.param)


@contextmanager
def stack(
    installed: _Installed, helper: Any, home: Path, root: Path, host: str, backend: int
) -> Iterator[Any]:
    with support._service(installed, helper, home, root, host, backend) as s:
        try:
            assert not Path(s.audit()["cwd"]).is_relative_to(process._REPO)
            yield s
        finally:
            if s.process.poll() is None:
                s.control(release_all=True)
                s.wait("released", True)


def args(s: Any, *command: str, version: int = 2) -> list[str]:
    return [
        *(["--api-version", "2"] if version == 2 else []),
        "--host",
        s.host,
        "--port",
        str(s.port),
        *command,
    ]


def command(
    s: Any,
    session: str,
    *,
    conditions: tuple[bytes, ...] = _CONDITIONS,
    maximum: int = 1024,
) -> list[str]:
    return args(
        s,
        "interact",
        "--session",
        session,
        "--payload-base64",
        base64.b64encode(_PAYLOAD).decode(),
        *[
            v
            for condition in conditions
            for v in ("--condition-base64", base64.b64encode(condition).decode())
        ],
        "--timeout-ms",
        "4000",
        "--max-rx-bytes",
        str(maximum),
    )


def one_request(
    audit: dict[str, Any], s: Any, route: str, *, status: int | None = 200
) -> None:
    authority = f"[{s.host}]:{s.port}" if s.host == "::1" else f"{s.host}:{s.port}"
    assert audit["credential_reads"] == 1
    assert audit["requests"] == [
        {
            "method": "POST" if not route.endswith("/status") else "GET",
            "path": route,
            "host": authority,
            "authorization_count": 1,
        }
    ]
    assert not audit["core_imported"] and not audit["service_imported"]
    assert not Path(audit["cwd"]).is_relative_to(process._REPO)
    if status is not None:
        assert audit["http_status"] == status and audit["cache_control"] == "no-store"


def run(
    installed: _Installed, s: Any, root: Path, *command: str, version: int = 2
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    code, out, err, audit = support._run(
        installed, root, s.home, args(s, *command, version=version)
    )
    assert out.endswith(b"\n") and out.count(b"\n") == 1 and err == b""
    assert Path(audit["interact_file"]).is_relative_to(installed.python.parent.parent)
    return code, dict(json.loads(out)), audit


def attach(
    installed: _Installed, s: Any, root: Path, *, version: int = 2, retained: int = 100
) -> tuple[str, Path]:
    tree = ast.parse(
        (
            process._REPO / "core/tests/contract/test_observation_composition.py"
        ).read_text()
    )
    text = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_PROFILE" for t in n.targets)
    )
    if version == 2:
        text = (
            text.replace("profile_version = 1", "profile_version = 2")
            + "\n[policy]\nuart_tx_enabled = true\n"
        )
    text = text.replace(
        "max_retained_records = 100", f"max_retained_records = {retained}"
    )
    profile, journal = s.home / "interact.toml", s.home / "interact.sqlite3"
    profile.write_text(text)
    code, view, audit = run(
        installed,
        s,
        root,
        "attach",
        "--profile",
        str(profile),
        "--journal",
        str(journal),
        version=version,
    )
    assert code == 0 and view["runtime"]["state"] == "active"
    assert view["runtime"]["profile"]["format_version"] == version
    one_request(audit, s, f"/v{version}/observation/attach")
    s.wait("rx_commits", 1)
    return str(view["runtime"]["session_id"]), journal


def page(
    installed: _Installed,
    s: Any,
    root: Path,
    session: str,
    sequence: int | None = None,
    *,
    version: int = 2,
) -> dict[str, Any]:
    cmd = ["evidence", "page" if sequence is None else "record", "--session", session]
    cmd += (
        ["--max-records", "11", "--max-charged-bytes", "16384"]
        if sequence is None
        else ["--sequence", str(sequence)]
    )
    code, view, audit = run(installed, s, root, *cmd, version=version)
    assert code == 0
    one_request(
        audit, s, f"/v{version}/evidence/{'page' if sequence is None else 'record'}"
    )
    return dict(view["page"])


def report(
    child: Any,
    installed: _Installed,
    s: Any,
    session: str,
    *,
    conditions: tuple[bytes, ...] = _CONDITIONS,
    maximum: int = 1024,
) -> dict[str, Any]:
    code, out, err, audit = child.finish()
    assert code == 0 and err == b"", (code, err)
    assert len(out) <= 1048577 and out.endswith(b"\n") and out.count(b"\n") == 1
    process._private(out, err, s.token)
    one_request(audit, s, "/v2/observation/interact")
    assert Path(audit["interact_file"]).is_relative_to(installed.python.parent.parent)
    expected = dict(
        session_id=session,
        payload_base64=base64.b64encode(_PAYLOAD).decode(),
        conditions_base64=[base64.b64encode(c).decode() for c in conditions],
        timeout_ms=4000,
        max_rx_bytes=maximum,
    )
    assert audit["interact_request"] == expected
    value = dict(json.loads(out))
    assert (
        value["session_id"] == session
        and value["payload_base64"] == expected["payload_base64"]
    )
    assert value["conditions_base64"] == expected["conditions_base64"]
    assert value["tx"]["acknowledgement_scope"] == "backend_acceptance"
    assert value["provenance"]["causation"] == "not_established"
    assert value["provenance"]["boundary_basis"] == "core_observation_order"
    assert (
        out
        == json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
        + b"\n"
    )
    assert (
        s.audit()["write_calls"] == [_PAYLOAD.hex()]
        and s.audit()["write_cancelled"] == 0
    )
    return value


def failed_request(
    installed: _Installed,
    s: Any,
    root: Path,
    arguments: list[str],
    code: int,
    source: str,
    kind: str,
    route: str,
    status: int,
) -> None:
    actual, out, err, audit = support._run(installed, root, s.home, arguments)
    assert actual == code and out == b""
    assert json.loads(err) == {"error": {"source": source, "code": kind}}
    one_request(audit, s, route, status=status)


def stop_follow(child: Any, stream: Any, s: Any) -> None:
    child.process.send_signal(signal.SIGINT)
    code, out, err, audit = child.finish()
    assert code == 130
    process._failure(err, "interrupted", "unknown")
    one_request(audit, s, "/v2/observation/follow")
    assert not any(v["type"] == "terminal" for v in stream.values)
    tail = bytes(stream.buffer) + out
    assert all(json.loads(line) == {"type": "heartbeat"} for line in tail.splitlines())
    process._private(b"".join(stream.raw) + out, err, s.token)


def test_installed_exact_binary_early_match_multiple_conditions_and_concurrent_workflows(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
) -> None:
    installed = installed_stack
    with stack(
        installed,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, journal = attach(installed, s, tmp_path / "attach")
        # API1 must reject the known v4 run before detach/query admission.
        for action in ("status", "detach"):
            failed_request(
                installed,
                s,
                tmp_path / ("v1-" + action),
                args(s, action, version=1),
                4,
                "request",
                "unsupported_api_version",
                f"/v1/observation/{action}",
                409,
            )
        failed_request(
            installed,
            s,
            tmp_path / "v1-read",
            args(
                s,
                "evidence",
                "record",
                "--session",
                session,
                "--sequence",
                "0",
                version=1,
            ),
            4,
            "request",
            "unsupported_api_version",
            "/v1/evidence/record",
            409,
        )
        assert s.audit()["closes"] == 0 and s.audit()["terminal_opens"] == 0
        with streams.cli(
            installed,
            tmp_path / "follow",
            account_home,
            args(s, "follow", "--session", session),
        ) as follow:
            stream = streams.Stream(follow)
            stream.started(session)
            monitor_args = args(
                s,
                "monitor",
                "--session",
                session,
                "--condition-base64",
                "T0s=",
                "--timeout-ms",
                "4000",
                "--max-rx-bytes",
                "1024",
            )
            with streams.cli(
                installed, tmp_path / "monitor", account_home, monitor_args
            ) as monitor:
                s.wait("monitor_starts", 1)
                with streams.cli(
                    installed, tmp_path / "interact", account_home, command(s, session)
                ) as child:
                    s.wait("write_pending", True)
                    assert child.process.poll() is None
                    code, claim, audit = run(
                        installed,
                        s,
                        tmp_path / "annotation",
                        "annotate",
                        "--session",
                        session,
                        "--text",
                        "client assertion é\r\n",
                    )
                    assert (
                        code == 0
                        and claim["annotation"]["text"] == "client assertion é\r\n"
                    )
                    one_request(audit, s, "/v2/observation/annotations")
                    failed_request(
                        installed,
                        s,
                        tmp_path / "busy",
                        command(s, session),
                        4,
                        "service",
                        "interact_capacity",
                        "/v2/observation/interact",
                        503,
                    )
                    s.control(emit_hex=_RX[:12].hex())
                    s.wait("rx_commits", 2)
                    s.control(emit_hex=_RX[12:].hex())
                    s.wait("rx_commits", 3)
                    mcode, mout, merr, maudit = monitor.finish()
                    assert (
                        mcode == 0
                        and merr == b""
                        and json.loads(mout)["outcome"] == "matched"
                    )
                    one_request(maudit, s, "/v2/observation/monitor")
                    assert child.process.poll() is None and s.audit()["write_pending"]
                    s.control(release_write=True)
                    value = report(child, installed, s, session)
                assert value["outcome"] == value["observation"]["outcome"] == "matched"
                assert value["observation"]["match"]["condition_index"] == 1
                assert value["observation"]["clock"]["decided_at_ns"] == _TIME
                assert value["tx"]["settled_at_ns"] == _TIME
                assert value["tx"]["accepted_prefix_bytes"] == len(_PAYLOAD)
                assert (
                    value["durability"] == "complete" and value["audit_failures"] == []
                )
            while True:
                frame = stream.data()
                assert frame["type"] == "record"
                if frame["record"]["kind"] == "interact_ended":
                    break
            readback = page(installed, s, tmp_path / "page", session)
            offered = [v["record"] for v in stream.values if v["type"] == "record"]
            assert offered == readback["records"][2:]
            rx = [
                base64.b64decode(r["payload_base64"], validate=True)
                for r in readback["records"]
                if r["kind"] == "rx_bytes"
            ]
            assert rx == [support._PAYLOAD, _RX[:12], _RX[12:]]
            for field, kind in [
                ("started_record", "interact_started"),
                ("tx_settled_record", "uart_tx_settled"),
                ("ended_record", "interact_ended"),
            ]:
                record = page(
                    installed, s, tmp_path / field, session, value[field]["sequence"]
                )["records"][0]
                assert (
                    record["kind"] == kind
                    and record["operation_id"] == value["operation_id"]
                )
                if kind == "interact_started":
                    assert base64.b64decode(record["payload_base64"]) == _PAYLOAD
                    assert record["conditions_base64"] == value["conditions_base64"]
            stop_follow(follow, stream, s)
        code, active, _ = run(installed, s, tmp_path / "active", "status")
        assert code == 0 and active["runtime"]["state"] == "active"
        code, terminal, _ = run(installed, s, tmp_path / "detach", "detach")
        assert code == 0 and terminal["runtime"]["owner_settled"]
        saved = page(installed, s, tmp_path / "terminal", session)
        assert saved["records"][:-1] == readback["records"]
        audit = s.audit()
        assert (
            audit["opens"]
            == audit["consumers"]
            == audit["closes"]
            == audit["recorder_closes"]
            == 1
        )
        assert audit["terminal_opens"] == audit["terminal_closes"] == 1
        assert (
            audit["trace"].index("write.settled")
            < audit["trace"].index("physical.close")
            < audit["trace"].index("journal.close")
        )
        assert (
            audit["query_only_set"]
            == audit["query_only_read"]
            == audit["begins"]
            == audit["rollbacks"]
            == 1
        )
        assert journal.exists() and audit["validation_in_transaction"]
        assert value["provenance"]["backend_observation_timestamp_domain"][
            "observer"
        ] == ("device" if backend else "host")


@pytest.mark.parametrize(
    "write_status,outcome,count",
    [
        ("partial", "partial_write", len(_PAYLOAD) // 2),
        ("zero", "partial_write", 0),
        ("timeout", "write_timeout", None),
        ("disconnected", "disconnected", None),
        ("failure", "transport_failure", None),
        ("malformed", "transport_failure", None),
    ],
)
def test_installed_write_failures_preserve_prefix_unknown_progress_and_exit_zero(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    write_status: str,
    outcome: str,
    count: int | None,
) -> None:
    installed = installed_stack
    with stack(
        installed,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = attach(installed, s, tmp_path / "attach")
        s.control(write_status=write_status)
        s.wait("write_status", write_status)
        with streams.cli(
            installed, tmp_path / "interact", account_home, command(s, session)
        ) as child:
            s.wait("write_pending", True)
            s.control(release_write=True)
            value = report(child, installed, s, session)
        assert (
            value["outcome"] == outcome
            and value["tx"]["accepted_prefix_bytes"] == count
        )
        assert (
            value["observation"]["outcome"] == "tx_failed"
            and value["observation"]["match"] is None
        )
        assert value["durability"] == "complete"
        assert value["tx"]["failure_code"] == (
            "io_failure"
            if write_status == "failure"
            else "internal_contract_failure"
            if write_status == "malformed"
            else None
        )
        rows = page(installed, s, tmp_path / "records", session)["records"]
        tx = next(r for r in rows if r["kind"] == "uart_tx_settled")
        end = next(r for r in rows if r["kind"] == "interact_ended")
        assert {key: tx[key] for key in value["tx"]} == end["tx"] == value["tx"]
        assert end["outcome"] == outcome


@pytest.mark.parametrize("fault", ["intent-before", "intent-after"])
def test_installed_failed_intent_ack_never_submits_or_claims_no_durable_intent(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    fault: str,
) -> None:
    installed = installed_stack
    with stack(
        installed,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = attach(installed, s, tmp_path / "attach")
        s.control(audit_faults=[fault])
        s.wait("audit_faults", [fault])
        failed_request(
            installed,
            s,
            tmp_path / "interact",
            command(s, session),
            4,
            "journal",
            "io_failure",
            "/v2/observation/interact",
            500,
        )
        assert s.audit()["write_calls"] == [] and s.audit()["interact_reports"] == 0
        rows = page(installed, s, tmp_path / "records", session)["records"]
        assert [r["kind"] for r in rows] == [
            "segment_started",
            "rx_bytes",
            *(["interact_started"] if fault.endswith("after") else []),
        ]
        assert s.audit()["txs"] == s.audit()["ends"] == 0


@pytest.mark.parametrize(
    "faults,durability",
    [
        (["tx-after"], "tx_unconfirmed"),
        (["end-before"], "end_unconfirmed"),
        (["tx-after", "end-after"], "both_unconfirmed"),
    ],
)
def test_installed_independent_audit_failures_keep_self_contained_facts_and_honest_refs(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    faults: list[str],
    durability: str,
) -> None:
    installed = installed_stack
    with stack(
        installed,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = attach(installed, s, tmp_path / "attach")
        s.control(audit_faults=faults)
        s.wait("audit_faults", faults)
        with streams.cli(
            installed, tmp_path / "interact", account_home, command(s, session)
        ) as child:
            s.wait("write_pending", True)
            s.control(emit_hex=_RX.hex())
            s.wait("rx_commits", 2)
            s.control(release_write=True)
            value = report(child, installed, s, session)
        assert value["outcome"] == "matched" and value["durability"] == durability
        assert (value["tx_settled_record"] is None) == ("tx-after" in faults)
        assert (value["ended_record"] is None) == any(
            f.startswith("end") for f in faults
        )
        assert [f["record_kind"] for f in value["audit_failures"]] == [
            kind
            for kind, prefix in [("uart_tx_settled", "tx"), ("interact_ended", "end")]
            if any(f.startswith(prefix) for f in faults)
        ]
        assert all(
            f["source"] == "journal" and f["code"] == "io_failure"
            for f in value["audit_failures"]
        )
        rows = page(installed, s, tmp_path / "records", session)["records"]
        assert len([r for r in rows if r["kind"] == "uart_tx_settled"]) == 1
        ends = [r for r in rows if r["kind"] == "interact_ended"]
        assert len(ends) == int("end-before" not in faults)
        if ends:
            assert (
                ends[0]["tx"] == value["tx"] and ends[0]["outcome"] == value["outcome"]
            )
            assert ends[0]["tx_settled_sequence"] is None
            assert ends[0]["tx_audit_failure"] == {
                "source": "journal",
                "code": "io_failure",
            }


def test_installed_rolling_expiry_keeps_delivered_report_without_refetch_or_pinning(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
) -> None:
    installed = installed_stack
    with stack(
        installed,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = attach(installed, s, tmp_path / "attach", retained=3)
        with streams.cli(
            installed, tmp_path / "interact", account_home, command(s, session)
        ) as child:
            s.wait("write_pending", True)
            s.control(emit_hex=_RX.hex())
            s.wait("rx_commits", 2)
            s.control(release_write=True)
            value = report(child, installed, s, session)
        start = page(
            installed,
            s,
            tmp_path / "expired-start",
            session,
            value["started_record"]["sequence"],
        )
        assert (
            start["outcome"] == "expired"
            and start["records"] == []
            and start["retention_marker"] is not None
        )
        end = page(
            installed,
            s,
            tmp_path / "retained-end",
            session,
            value["ended_record"]["sequence"],
        )["records"][0]
        assert end["tx"] == value["tx"]
        s.control(emit_hex="00ff", emit_count=4)
        s.wait("rx_commits", 6)
        for field in ("tx_settled_record", "ended_record"):
            expired = page(
                installed, s, tmp_path / field, session, value[field]["sequence"]
            )
            assert expired["outcome"] == "expired" and expired["records"] == []
        assert value["durability"] == "complete" and s.audit()["interact_reports"] == 1
        assert s.audit()["write_calls"] == [_PAYLOAD.hex()]


@pytest.mark.parametrize(
    "loss", ["intent-sigint", "write-sigint", "audit-sigint", "write-deadline", "pipe"]
)
def test_installed_client_loss_keeps_owned_work_slots_and_honest_receipt(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    loss: str,
) -> None:
    installed = installed_stack
    with stack(
        installed,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = attach(installed, s, tmp_path / "attach")
        if loss == "intent-sigint":
            s.control(hold_intent=True)
            s.wait("hold_intent", True)
        elif loss != "pipe":
            s.control(hold_end=True)
            s.wait("hold_end", True)
        with streams.cli(
            installed,
            tmp_path / "interact",
            account_home,
            command(s, session),
            mode="interact-deadline" if loss == "write-deadline" else "normal",
            closed="stdout" if loss == "pipe" else "",
        ) as child:
            s.wait(
                "pending_intent" if loss == "intent-sigint" else "write_pending", True
            )
            if loss in {"pipe", "audit-sigint"}:
                s.control(emit_hex=_RX.hex())
                s.wait("rx_commits", 2)
                s.control(release_write=True)
                if loss == "audit-sigint":
                    s.wait("pending_end", True)
            if loss.endswith("sigint"):
                child.process.send_signal(signal.SIGINT)
            code, out, err, audit = child.finish()
            assert out == b"" and code == (
                1 if loss == "pipe" else 5 if loss.endswith("deadline") else 130
            )
            kind = (
                "output_failed"
                if loss == "pipe"
                else "request_timeout"
                if loss.endswith("deadline")
                else "interrupted"
            )
            process._failure(
                err, kind, "report_received" if loss == "pipe" else "unknown"
            )
            process._private(out, err, s.token)
            one_request(
                audit,
                s,
                "/v2/observation/interact",
                status=200 if loss == "pipe" else None,
            )
            if loss.endswith("deadline"):
                assert audit["whole_budget"] == 10
        if loss != "pipe":
            assert s.audit()["interact_waiters"] == 1
            failed_request(
                installed,
                s,
                tmp_path / "busy",
                command(s, session),
                4,
                "service",
                "interact_capacity",
                "/v2/observation/interact",
                503,
            )
            assert (
                s.audit()["interact_reports"] == 0 and s.audit()["recorder_closes"] == 0
            )
            if loss in {"write-sigint", "write-deadline"}:
                assert s.audit()["write_pending"]
                s.control(release_write=True)
                s.wait("pending_end", True)
                failed_request(
                    installed,
                    s,
                    tmp_path / "busy-audit",
                    command(s, session),
                    4,
                    "service",
                    "interact_capacity",
                    "/v2/observation/interact",
                    503,
                )
            s.control(release_all=True)
            s.wait("released", True)
        s.wait("interact_waiters", 0)
        rows = page(installed, s, tmp_path / "readback", session)["records"]
        tx = next(r for r in rows if r["kind"] == "uart_tx_settled")
        end = next(r for r in rows if r["kind"] == "interact_ended")
        assert end["outcome"] == (
            "matched" if loss in {"audit-sigint", "pipe"} else "cancelled"
        )
        submitted = loss != "intent-sigint"
        assert tx["submitted"] is submitted
        assert tx["status"] == ("acknowledged" if submitted else "not_submitted")
        assert tx["accepted_prefix_bytes"] == (len(_PAYLOAD) if submitted else None)
        assert s.audit()["write_calls"] == ([_PAYLOAD.hex()] if submitted else [])
        assert s.audit()["write_cancelled"] == 0
        assert s.audit()["interact_reports"] == int(loss == "pipe")
        code, status, _ = run(installed, s, tmp_path / "active", "status")
        assert code == 0 and status["runtime"]["state"] == "active"
        assert (
            s.audit()["opens"] == s.audit()["consumers"] == 1
            and s.audit()["closes"] == 0
        )


@pytest.mark.parametrize("phase", ["write", "end-audit"])
def test_installed_service_stop_seals_before_http_drain_and_joins_write_and_audit(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    phase: str,
) -> None:
    installed = installed_stack
    with stack(
        installed,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = attach(installed, s, tmp_path / "attach")
        s.control(hold_end=True)
        s.wait("hold_end", True)
        with streams.cli(
            installed, tmp_path / "interact", account_home, command(s, session)
        ) as child:
            s.wait("write_pending", True)
            if phase == "end-audit":
                s.control(emit_hex=_RX.hex())
                s.wait("rx_commits", 2)
                s.control(release_write=True)
                s.wait("pending_end", True)
            s.process.send_signal(signal.SIGINT)
            s.wait("drain_entered", True)
            s.process.send_signal(signal.SIGINT)
            root = account_home / ".local/state/dutchmate/service"
            assert s.process.poll() is None and child.process.poll() is None
            assert (root / "credential").read_bytes() == s.token + b"\n"
            assert (
                json.loads((root / "owner.json").read_bytes())["cleanup_confirmed"]
                is False
            )
            assert not s.audit()["http_drained"] and s.audit()["recorder_closes"] == 0
            assert "physical.close" not in s.audit()["trace"]
            if phase == "write":
                s.control(release_write=True)
                s.wait("pending_end", True)
                assert s.process.poll() is None and not s.audit()["write_pending"]
            assert (
                s.audit()["write_finished"] == 1 and s.audit()["write_cancelled"] == 0
            )
            s.control(hold_end=False)
            s.wait("hold_end", False)
            value = report(child, installed, s, session)
            assert value["outcome"] == (
                "service_stopping" if phase == "write" else "matched"
            )
        final = s.finish(None)
        assert (
            final["outcome"] == "returned"
            and not final["force_exit"]
            and final["http_drained"]
        )
        assert (
            final["interact_waiters"] == 0
            and final["recorder_closes"] == final["closes"] == 1
        )
        assert (
            final["trace"].index("write.settled")
            < final["trace"].index("end.ack")
            < final["trace"].index("physical.close")
            < final["trace"].index("journal.close")
        )
        assert not (root / "credential").exists()
        assert json.loads((root / "owner.json").read_bytes()) == {
            "version": 1,
            "cleanup_confirmed": True,
        }
        s.private_output(s.token, process._PRIVATE.encode())


def test_installed_default_api1_profile_journal_and_receive_only_workflows_stay_compatible(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
) -> None:
    installed = installed_stack
    with stack(
        installed,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = attach(installed, s, tmp_path / "attach", version=1)
        # No --api-version flag must remain local-invalid for Interact, before credentials.
        code, out, err, audit = support._run(
            installed,
            tmp_path / "local",
            account_home,
            command(s, session)[2:],
            mode="no_io",
        )
        assert code == 2 and out == b""
        process._failure(err, "invalid_arguments")
        assert audit["credential_reads"] == 0 and audit["requests"] == []
        with streams.cli(
            installed,
            tmp_path / "follow",
            account_home,
            args(s, "follow", "--session", session, version=1),
        ) as follow:
            stream = streams.Stream(follow)
            stream.started(session)
            with streams.cli(
                installed,
                tmp_path / "monitor",
                account_home,
                args(
                    s,
                    "monitor",
                    "--session",
                    session,
                    "--condition-base64",
                    "UEFTUw==",
                    "--timeout-ms",
                    "4000",
                    "--max-rx-bytes",
                    "1024",
                    version=1,
                ),
            ) as monitor:
                s.wait("monitor_starts", 1)
                code, receipt, audit = run(
                    installed,
                    s,
                    tmp_path / "annotation",
                    "annotate",
                    "--session",
                    session,
                    "--text",
                    "legacy assertion",
                    version=1,
                )
                assert code == 0 and receipt["annotation"]["text"] == "legacy assertion"
                one_request(audit, s, "/v1/observation/annotations")
                s.control(emit_hex=b"PASS".hex())
                s.wait("rx_commits", 2)
                code, out, err, audit = monitor.finish()
                assert (
                    code == 0 and err == b"" and json.loads(out)["outcome"] == "matched"
                )
                one_request(audit, s, "/v1/observation/monitor")
            while True:
                frame = stream.data()
                assert frame["type"] == "record"
                if frame["record"]["kind"] == "operation_ended":
                    break
            follow.process.send_signal(signal.SIGINT)
            code, _, err, audit = follow.finish()
            assert code == 130
            process._failure(err, "interrupted", "unknown")
            one_request(audit, s, "/v1/observation/follow")
        v1 = page(installed, s, tmp_path / "v1", session, version=1)
        v2 = page(installed, s, tmp_path / "v2", session)
        assert v1 == v2 and all(
            not r["kind"].startswith("interact") and r["kind"] != "uart_tx_settled"
            for r in v1["records"]
        )
        code, status, audit = run(
            installed, s, tmp_path / "status", "status", version=1
        )
        assert code == 0 and status["runtime"]["profile"]["format_version"] == 1
        one_request(audit, s, "/v1/observation/status")
        code, terminal, audit = run(
            installed, s, tmp_path / "detach", "detach", version=1
        )
        assert code == 0 and terminal["runtime"]["owner_settled"]
        one_request(audit, s, "/v1/observation/detach")
        assert (
            page(installed, s, tmp_path / "terminal", session, version=1)["records"][
                :-1
            ]
            == v1["records"]
        )
        assert (
            s.audit()["write_calls"] == []
            and s.audit()["intents"] == s.audit()["txs"] == s.audit()["ends"] == 0
        )
        assert s.audit()["opens"] == s.audit()["consumers"] == s.audit()["closes"] == 1


@pytest.mark.parametrize("decision", ["timeout", "byte_limit", "same-ending-byte"])
def test_installed_observation_bounds_and_ordered_tie_preserve_full_rx_evidence(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    decision: str,
) -> None:
    installed = installed_stack
    conditions = (b"OK", b"\0\xffOK") if decision == "same-ending-byte" else _CONDITIONS
    maximum = 4 if decision == "byte_limit" else 1024
    with stack(
        installed,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = attach(installed, s, tmp_path / "attach")
        with streams.cli(
            installed,
            tmp_path / "interact",
            account_home,
            command(s, session, conditions=conditions, maximum=maximum),
        ) as child:
            s.wait("write_pending", True)
            incoming = b"xxxx-tail\x00\xff" if decision == "byte_limit" else _RX
            s.control(
                emit_hex=incoming.hex(),
                **({"advance_ns": 4_000_000_000} if decision == "timeout" else {}),
            )
            s.wait("rx_commits", 2)
            assert child.process.poll() is None and s.audit()["write_pending"]
            s.control(release_write=True)
            value = report(
                child, installed, s, session, conditions=conditions, maximum=maximum
            )
        expected = "matched" if decision == "same-ending-byte" else decision
        observation = value["observation"]
        assert value["outcome"] == observation["outcome"] == expected
        assert (
            observation["window"]["start_inclusive"]
            == value["started_record"]["sequence"] + 1
        )
        assert observation["examined_rx_bytes"] == (
            0 if decision == "timeout" else 4 if decision == "byte_limit" else 14
        )
        if decision == "timeout":
            assert observation["clock"]["decided_at_ns"] == _TIME + 4_000_000_000
            assert value["tx"]["settled_at_ns"] == observation["clock"]["decided_at_ns"]
            assert (
                observation["window"]["start_inclusive"]
                == observation["window"]["end_exclusive"]
            )
        elif decision == "same-ending-byte":
            assert observation["match"]["condition_index"] == 0
            assert observation["match"]["start"]["byte_offset"] == 12
            assert observation["match"]["end"]["byte_offset_exclusive"] == 14
        else:
            assert observation["match"] is None
        records = page(installed, s, tmp_path / "page", session)["records"]
        rx = [r for r in records if r["kind"] == "rx_bytes"]
        assert [base64.b64decode(r["payload_base64"], validate=True) for r in rx] == [
            support._PAYLOAD,
            incoming,
        ]
        if decision != "timeout":
            assert observation["window"]["end_exclusive"] == rx[-1]["sequence"] + 1


def _requirements(values: list[str]) -> dict[str, frozenset[str]]:
    """Compare the current simple declarations despite metadata specifier order."""
    result = {}
    for value in values:
        matched = re.fullmatch(r"([a-zA-Z0-9_-]+)(.*)", value.replace(" ", ""))
        assert matched is not None
        name, specifiers = matched.groups()
        assert name not in result
        result[name.replace("_", "-").lower()] = frozenset(
            filter(None, specifiers.split(","))
        )
    return result


@pytest.mark.parametrize("package", _PACKAGE_ROOTS)
def test_t027_archives_match_source_metadata_record_and_private_exclusions(
    stack_artifacts: tuple[dict[str, tuple[Path, Path]], list[str]], package: str
) -> None:
    root = _PACKAGE_ROOTS[package]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    module = package.replace("-", "_")
    source = {
        path.relative_to(root / "src").as_posix(): path.read_bytes()
        for path in (root / "src" / module).rglob("*.py")
    }
    wheel_path, sdist_path = stack_artifacts[0][package]
    with zipfile.ZipFile(wheel_path) as wheel:
        names = wheel.namelist()
        assert len(names) == len(set(names))
        distribution = f"{module}-{project['version']}.dist-info/"
        metadata_names = {
            distribution + name for name in ("METADATA", "WHEEL", "RECORD")
        }
        if project.get("scripts"):
            metadata_names.add(distribution + "entry_points.txt")
        # Exact allowlist also rejects credentials/journals, caches, fixtures,
        # checkout paths, agent/Graphify output and stale extra product modules.
        assert set(names) == source.keys() | metadata_names
        for name, expected in source.items():
            assert wheel.read(name) == expected
        records = list(
            csv.reader(io.StringIO(wheel.read(distribution + "RECORD").decode()))
        )
        assert len(records) == len(names)
        assert {row[0] for row in records} == set(names)
        for name, digest, size in records:
            if name == distribution + "RECORD":
                assert digest == size == ""
            else:
                data = wheel.read(name)
                assert (
                    digest
                    == "sha256="
                    + base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                    .rstrip(b"=")
                    .decode()
                )
                assert size == str(len(data))
        wheel_metadata = wheel.read(distribution + "METADATA")
        wheel_tags = BytesParser().parsebytes(wheel.read(distribution + "WHEEL"))
        assert wheel_tags["Root-Is-Purelib"] == "true"
        assert wheel_tags.get_all("Tag") == ["py3-none-any"]
        if project.get("scripts"):
            assert wheel.read(distribution + "entry_points.txt").decode() == (
                "[console_scripts]\n"
                + "".join(
                    f"{name} = {target}\n"
                    for name, target in project["scripts"].items()
                )
            )
    with tarfile.open(sdist_path) as sdist:
        entries = sdist.getmembers()
        names = [entry.name for entry in entries]
        assert len(names) == len(set(names))
        prefix = f"{module}-{project['version']}/"
        assert all(
            entry.isfile() and entry.name.startswith(prefix) for entry in entries
        )
        public = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for directory in (root / "src", root / "tests")
            for path in directory.rglob("*.py")
        }
        public["pyproject.toml"] = (root / "pyproject.toml").read_bytes()
        public[".gitignore"] = (process._REPO / ".gitignore").read_bytes()
        if (root / "ruff.toml").exists():
            public["ruff.toml"] = (root / "ruff.toml").read_bytes()
        assert set(names) == {prefix + name for name in (*public, "PKG-INFO")}
        for name, expected in public.items():
            stream = sdist.extractfile(prefix + name)
            assert stream is not None and stream.read() == expected
        stream = sdist.extractfile(prefix + "PKG-INFO")
        assert stream is not None
        sdist_metadata = stream.read()
    assert wheel_metadata == sdist_metadata
    metadata = BytesParser().parsebytes(wheel_metadata)
    assert metadata["Name"] == project["name"]
    assert metadata["Version"] == project["version"]
    assert metadata["Summary"] == project["description"]
    assert set(metadata["Requires-Python"].split(",")) == set(
        project["requires-python"].split(",")
    )
    assert _requirements(metadata.get_all("Requires-Dist", [])) == _requirements(
        project.get("dependencies", [])
    )
    # No personal source/build path or untracked private inputs in metadata.
    assert str(process._REPO).encode() not in wheel_metadata
    assert b"/Users/" not in wheel_metadata


def test_t027_installed_import_bytes_dependencies_record_and_noneditable_paths(
    request: pytest.FixtureRequest,
    installed_stack: _Installed,
    stack_artifacts: tuple[dict[str, tuple[Path, Path]], list[str]],
    account_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modules = {}
    for package, root in _PACKAGE_ROOTS.items():
        module = package.replace("-", "_")
        for path in (root / "src" / module).rglob("*.py"):
            name = (
                path.relative_to(root / "src")
                .with_suffix("")
                .as_posix()
                .replace("/", ".")
            )
            modules[name.removesuffix(".__init__")] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    # The unchanged harness starts sitecustomize's account/device/network guards
    # before these import-only probes. No product source paths enter the child.
    probe = r"""
import base64, csv, hashlib, importlib.metadata, io
audit["artifact_modules"] = {}
for name in MODULE_NAMES:
    imported = importlib.import_module(name)
    path = Path(imported.__file__)
    assert path.is_relative_to(Path(sys.prefix))
    audit["artifact_modules"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
audit["artifact_distributions"] = {}
for name in PACKAGE_NAMES:
    distribution = importlib.metadata.distribution(name)
    rows = list(csv.reader(io.StringIO(distribution.read_text("RECORD"))))
    assert len(rows) == len({row[0] for row in rows})
    assert {str(path) for path in distribution.files} == {row[0] for row in rows}
    for name_in_record, digest, size in rows:
        path = Path(distribution.locate_file(name_in_record)).resolve()
        assert path.is_relative_to(Path(sys.prefix)) and path.is_file()
        if digest:
            data = path.read_bytes()
            assert digest == "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            assert size == str(len(data))
        else:
            assert name_in_record.endswith("/RECORD") and size == ""
    direct = json.loads(distribution.read_text("direct_url.json"))
    assert "dir_info" not in direct and "archive_info" in direct
    audit["artifact_distributions"][name] = dict(
        version=distribution.version, requires=distribution.requires or [],
        python=distribution.metadata["Requires-Python"], direct_url=direct,
        record_entries=len(rows),
        entries={entry.name: entry.value for entry in distribution.entry_points})
audit["locked_versions"] = {pin: importlib.metadata.version(pin.split("==")[0]) for pin in LOCKED_PINS}
assert not any(Path(sys.prefix).rglob("*.egg-link"))
audit["artifact_sys_path"] = sys.path
publish()
"""
    probe = probe.replace("MODULE_NAMES", repr(sorted(modules)))
    probe = probe.replace("PACKAGE_NAMES", repr(list(_PACKAGE_ROOTS)))
    probe = probe.replace("LOCKED_PINS", repr(stack_artifacts[1]))
    monkeypatch.setattr(process, "_GUARD", _CLI_GUARD + probe)
    with process._cli(
        installed_stack, tmp_path, account_home, ["interact", "--help"], mode="no_io"
    ) as child:
        code, stdout, stderr, audit = child.finish()
    assert code == 0 and b"--payload-base64" in stdout and not stderr
    assert audit["credential_reads"] == 0 and audit["requests"] == []
    assert audit["artifact_modules"] == modules
    assert not Path(audit["cwd"]).is_relative_to(process._REPO)
    assert all(
        not Path(path).is_relative_to(process._REPO)
        for path in audit["artifact_sys_path"]
        if path
    )
    for package, root in _PACKAGE_ROOTS.items():
        project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
        found = audit["artifact_distributions"][package]
        assert found["version"] == project["version"]
        assert set(found["python"].split(",")) == set(
            project["requires-python"].split(",")
        )
        assert _requirements(found["requires"]) == _requirements(
            project.get("dependencies", [])
        )
        assert found["entries"] == project.get("scripts", {})
        selection = (
            0 if request.node.callspec.params["installed_stack"] == "wheel" else 1
        )
        artifact = stack_artifacts[0][package][selection]
        assert found["direct_url"]["url"] == artifact.as_uri()
    assert all(
        found == pin.split("==")[1] for pin, found in audit["locked_versions"].items()
    )
