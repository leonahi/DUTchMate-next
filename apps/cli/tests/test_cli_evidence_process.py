"""T028: installed evidence delivery through guarded native service/CLI children.

Only the DUT boundary and deliberate malformed peer replies are substituted.
Profile/journal/runtime/authentication/HTTP/CLI/entry/cleanup remain production code.
"""

import ast
import base64
import importlib.util
import json
import os
import signal
import subprocess
import tarfile
import time
import tomllib
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from apps.cli.tests.test_cli_process import (
        _GUARD,
        _PRIVATE,
        _REPO,
        _cli,
        _failure,
        _Installed,
        _private,
        _uv,
    )
    from apps.cli.tests.test_cli_process import (
        native_service_helper as native_service_helper,
    )
    from apps.cli.tests.test_cli_process import package_artifacts as package_artifacts
    from apps.cli.tests.test_cli_process import (
        test_t018_parent_physical_and_real_account_tripwires_are_active as _parent_guards,
    )
    from test_service_process import _Child
else:
    from importlib import import_module

    _support = import_module("test_cli_process")
    _GUARD, _PRIVATE, _REPO = _support._GUARD, _support._PRIVATE, _support._REPO
    _Installed, _cli = _support._Installed, _support._cli
    _failure, _private, _uv = _support._failure, _support._private, _support._uv
    native_service_helper = _support.native_service_helper
    package_artifacts = _support.package_artifacts
    _parent_guards = (
        _support.test_t018_parent_physical_and_real_account_tripwires_are_active
    )
    _spec = importlib.util.spec_from_file_location(
        "_t028_native_service_helper", _REPO / "apps/service/tests/test_service_process.py"
    )
    assert _spec is not None and _spec.loader is not None
    _native = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_native)
    _Child = _native._Child

_PAYLOAD = bytes(range(256)) + b"\x00\xff\xfe\r\n\r\n"
_AMBIENT = b"after-client\x00\xfe\r\n"
_BOUND = 1048576

# Reuse the actual CLI child's independent account/physical guards, before any
# service imports. Permit only service's safe directory creation in isolated home.
_SERVICE_SCRIPT = (
    _GUARD.split("socket.getaddrinfo = forbidden")[0]
    + r"""
import dataclasses, signal, urllib.parse
def service_mkdir(path, mode=0o777, *, dir_fd=None):
    check_path(path, dir_fd)
    return original_mkdir(path, mode, dir_fd=dir_fd)
os.mkdir = service_mkdir
os.fork = forbidden
socket.getaddrinfo = forbidden
audit["guard_ready"] = True
audit.update(ready=False, runtime_count=0, opens=0, consumers=0, closes=0,
             recorder_closes=0, terminal_opens=0, terminal_closes=0,
             rx_commits=0, reports=0, fault="normal", uris=[],
             query_only_set=0, query_only_read=0, begins=0, rollbacks=0,
             validation_in_transaction=True)
def publish():
    temporary = audit_path.with_suffix(".new")
    temporary.write_text(json.dumps(audit), encoding="utf-8")
    temporary.replace(audit_path)
publish()
from dutchmate_core.adapters import observation_runtime as composition, sqlite_evidence, terminal_evidence
from dutchmate_core import model
from dutchmate_service import server, bootstrap
import dutchmate_core, dutchmate_service, importlib, uvicorn
app = importlib.import_module("dutchmate_service.app")
from t028_backend_fixtures import BACKEND_FIXTURE_FACTORIES
uvicorn.run = forbidden
fixture = None
runtime_owner = None
background = None
control_path = home / "t028-control.json"
payload = bytes(range(256)) + b"\x00\xff\xfe\r\n\r\n"
ambient = b"after-client\x00\xfe\r\n"
async def control():
    while True:
        if control_path.exists():
            command = json.loads(control_path.read_bytes())
            control_path.unlink()
            if "fault" in command:
                audit["fault"] = command["fault"]
            if command.get("emit"):
                assert fixture is not None and not fixture.connection.closed
                await fixture.connection.emit_rx(ambient, timestamp=9)
            publish()
        await asyncio.sleep(0.01)  # Test control polling, never a Core deadline.
actual_runtime = app.ObservationRuntime
def runtime():
    global runtime_owner, background
    runtime_owner = actual_runtime()
    audit["runtime_count"] += 1
    background = asyncio.create_task(control())
    publish()
    return runtime_owner
app.ObservationRuntime = runtime
def backend(selector, configuration, line_intent):
    global fixture
    assert fixture is None
    assert selector.device_name == "/dev/fixture-only"
    fixture = BACKEND_FIXTURE_FACTORIES[int(os.environ["DUTCHMATE_TEST_BACKEND"])]()
    descriptor = fixture.connection.descriptor
    fixture.connection.descriptor = dataclasses.replace(descriptor,
        connection_provenance=model.PersistedConnectionProvenance(
            model.ConnectionProvenanceSnapshot(1, "fixture/installed-evidence", 1,
                (model.ProvenanceField("transport", "simulated"),))))
    actual_open = fixture.backend.open
    async def opened():
        connection = await actual_open()
        audit["opens"] += 1
        await connection.emit_rx(payload, timestamp=7)
        publish()
        return connection
    fixture.backend.open = opened
    return fixture.backend
composition.BasicSerialBackend = backend
actual_append, actual_close = sqlite_evidence.SqliteEvidenceJournal.append, sqlite_evidence.SqliteEvidenceJournal.close
async def append(journal, draft):
    record = await actual_append(journal, draft)
    if isinstance(record, model.RxBytesEvidence):
        audit["rx_commits"] += 1
    if fixture is not None:
        audit["consumers"] = fixture.connection.consumer_calls
    publish()
    return record
async def close(journal):
    await actual_close(journal)
    audit["recorder_closes"] += 1
    if fixture is not None:
        audit["closes"] = fixture.connection.close_calls
    publish()
sqlite_evidence.SqliteEvidenceJournal.append = append
sqlite_evidence.SqliteEvidenceJournal.close = close
actual_connect = sqlite3_connect = __import__("sqlite3").connect
def connect(destination, *args, **kwargs):
    read_only = False
    if isinstance(destination, str) and destination.startswith("file:"):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(destination).query)
        assert query == {"mode": ["ro"], "cache": ["private"]}
        assert audit["recorder_closes"] == 1
        audit["uris"].append(query)
        read_only = True
        publish()
    connection = actual_connect(destination, *args, **kwargs)
    if read_only:
        def trace(sql):
            statement = " ".join(sql.upper().split())
            for wanted, key in (("PRAGMA QUERY_ONLY=ON", "query_only_set"),
                                ("PRAGMA QUERY_ONLY", "query_only_read"),
                                ("BEGIN", "begins"), ("ROLLBACK", "rollbacks")):
                if statement == wanted:
                    audit[key] += 1
            if statement.startswith("SELECT") or "QUICK_CHECK" in statement:
                audit["validation_in_transaction"] &= connection.in_transaction
            publish()
        connection.set_trace_callback(trace)
    return connection
__import__("sqlite3").connect = connect
actual_terminal = composition.open_terminal_reader
class Reader:
    def __init__(self, raw):
        self.raw, self.session_id, self.policy = raw, raw.session_id, raw.policy
    async def resolve_record(self, value):
        return await self.raw.resolve_record(value)
    async def retrieve(self, value):
        return await self.raw.retrieve(value)
    async def close(self):
        await self.raw.close()
        audit["terminal_closes"] += 1
        publish()
async def terminal(target):
    assert runtime_owner.status().owner_settled and runtime_owner.status().recorder_close_confirmed
    audit["terminal_opens"] += 1
    publish()
    return Reader(await actual_terminal(target))
composition.open_terminal_reader = terminal
actual_response = app.evidence_response
def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
def response(report):
    from starlette.responses import Response
    original = actual_response(report)
    audit["reports"] += 1
    fault = audit["fault"]
    publish()
    if fault == "normal":
        return original
    value = json.loads(original.body)
    status = 200
    if fault == "bad-json":
        body = b'{"private":"private-t018-argv-exception-local-sentinel"'
    elif fault == "extra-field":
        value["private"] = private
        body = encode(value)
    elif fault == "bad-binary":
        value["page"]["records"] = [{"kind":"rx_bytes","sequence":1,
            "connection_id":"connection","segment_id":"segment",
            "observed_at":{"domain_id":"host","value":1},"payload_base64":"Zh=="}]
        body = encode(value)
    elif fault == "bad-cursor":
        value["page"]["continuation"] = "Zh"
        body = encode(value)
    elif fault == "wrong-error":
        status, body = 500, encode({"error":{"source":"journal","code":private}})
    elif fault in {"raw-overflow", "fitting-bound"}:
        value["run_id"] = "é\n\\"
        gap = 1048576 - len(encode(value))
        value["run_id"] += "a" * (gap + (fault == "raw-overflow"))
        body = encode(value)
        assert len(body) == 1048576 + (fault == "raw-overflow")
    elif fault == "remote413":
        status, body = 413, encode({"error":{"source":"evidence","code":"delivery_too_large"}})
    else:
        raise AssertionError("unknown controlled peer response")
    return Response(body, status_code=status, media_type="application/json", headers={"Cache-Control":"no-store"})
app.evidence_response = response
actual_startup = uvicorn.Server.startup
async def startup(self, sockets=None):
    await actual_startup(self, sockets=sockets)
    audit["ready"] = self.started
    audit["force_exit"] = self.force_exit
    audit["product_files"] = [dutchmate_core.__file__, dutchmate_service.__file__, composition.__file__]
    audit["prefix"] = sys.prefix
    publish()
uvicorn.Server.startup = startup
try:
    server.run_service(bootstrap.ServiceConfig(int(os.environ["DUTCHMATE_TEST_PORT"]), os.environ["DUTCHMATE_TEST_HOST"]))
except bootstrap.BootstrapFailure as error:
    audit["outcome"] = error.kind.value
except Exception:
    audit["outcome"] = "test-helper-failed"
    publish()
    sys.exit(2)
else:
    audit["outcome"] = "returned"
publish()
"""
)


@pytest.fixture(scope="session")
def stack_artifacts(
    package_artifacts: tuple[Path, Path, list[str]],
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, tuple[Path, Path]], list[str]]:
    root = tmp_path_factory.mktemp("t028-stack-artifacts")
    artifacts = {"dutchmate-cli": package_artifacts[:2]}
    for package in ("dutchmate-core", "dutchmate-service"):
        _uv(["build", "--offline", "--package", package, "--out-dir", str(root)], _REPO)
        stem = package.replace("-", "_")
        artifacts[package] = (
            next(root.glob(stem + "-*.whl")),
            next(root.glob(stem + "-*.tar.gz")),
        )
    packages = {
        p["name"]: p for p in tomllib.loads((_REPO / "uv.lock").read_text())["package"]
    }
    names: set[str] = set()

    def include(name: str) -> None:
        if name in names:
            return
        names.add(name)
        for dependency in packages[name].get("dependencies", []):
            include(dependency["name"])

    for name in artifacts:
        include(name)
    pins = [
        f"{name}=={packages[name]['version']}"
        for name in sorted(names - artifacts.keys())
    ]
    return artifacts, pins


@pytest.fixture(scope="session", params=["wheel", "sdist"])
def installed_stack(
    request: pytest.FixtureRequest,
    stack_artifacts: tuple[dict[str, tuple[Path, Path]], list[str]],
    tmp_path_factory: pytest.TempPathFactory,
) -> _Installed:
    artifacts, pins = stack_artifacts
    root = tmp_path_factory.mktemp("t028-installed-" + request.param)
    environment = root / "environment"
    _uv(
        [
            "venv",
            "--offline",
            "--python",
            __import__("sys").executable,
            str(environment),
        ],
        root,
    )
    python = environment / "bin/python"
    selection = 0 if request.param == "wheel" else 1
    _uv(
        [
            "pip",
            "install",
            "--python",
            str(python),
            *(str(pair[selection]) for pair in artifacts.values()),
            *pins,
        ],
        root,
    )
    wheel, sdist = artifacts["dutchmate-cli"]
    return _Installed(root, python, environment / "bin/dutchmate", wheel, sdist)


def _args(host: str, port: int, command: str, session: str) -> list[str]:
    args = [
        "--host",
        host,
        "--port",
        str(port),
        "evidence",
        command,
        "--session",
        session,
    ]
    return args + (
        ["--sequence", "1"]
        if command == "record"
        else ["--max-records", "11", "--max-charged-bytes", "16384"]
    )


def _run(
    installed: _Installed, root: Path, home: Path, args: list[str], **kwargs: Any
) -> tuple[int, bytes, bytes, dict[str, Any]]:
    with _cli(installed, root, home, args, **kwargs) as child:
        result = child.finish()
    code, stdout, stderr, audit = result
    _private(stdout, stderr, str(home).encode())
    assert Path(audit["product_file"]).is_relative_to(installed.python.parent.parent)
    assert not Path(audit["product_file"]).is_relative_to(_REPO)
    return result


@contextmanager
def _service(
    installed: _Installed,
    helper: Any,
    home: Path,
    root: Path,
    host: str = "127.0.0.1",
    backend: int = 0,
) -> Iterator[Any]:
    root.mkdir(parents=True)
    guard = root / "guard"
    guard.mkdir()
    script = guard / "service-helper.py"
    script.write_text(_SERVICE_SCRIPT)
    (guard / "t028_backend_fixtures.py").write_bytes(
        (_REPO / "core/tests/fakes.py").read_bytes()
    )
    port = helper._port(host)

    class InstalledService(_Child):
        def __init__(self) -> None:
            self.home, self.port, self.host = home, port, host
            self.token = b""
            self.audit_path = home / f"audit-{port}.json"
            env = dict(os.environ)
            env.pop("PYTHONHOME", None)
            env["PYTHONPATH"] = str(guard)  # Test fixture/guard code only.
            env.update(
                DUTCHMATE_TEST_HOME=str(home),
                DUTCHMATE_TEST_AUDIT=str(self.audit_path),
                DUTCHMATE_TEST_EVENT=str(home / "t028-event"),
                DUTCHMATE_TEST_MODE="normal",
                DUTCHMATE_TEST_PORT=str(port),
                DUTCHMATE_TEST_HOST=host,
                DUTCHMATE_TEST_BACKEND=str(backend),
            )
            self.process = subprocess.Popen(
                [str(installed.python), str(script)],
                cwd=root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.output: tuple[bytes, bytes] | None = None

        def wait(self, key: str, value: Any) -> dict[str, Any]:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                audit = self.audit()
                if audit.get(key) == value:
                    return audit
                assert self.process.poll() is None, (
                    "guarded service exited before checkpoint"
                )
                time.sleep(0.01)
            pytest.fail("guarded service checkpoint not reached")

        def control(self, **value: Any) -> None:
            temporary = home / "t028-control.new"
            temporary.write_text(json.dumps(value))
            temporary.replace(home / "t028-control.json")

        def fault(self, value: str) -> None:
            self.control(fault=value)
            self.wait("fault", value)

    child = InstalledService()
    try:
        child.token = child.ready()
        audit = child.audit()
        assert all(
            audit[k]
            for k in (
                "guard_ready",
                "account_isolated",
                "hardware_blocked",
                "real_bootstrap_blocked",
            )
        )
        assert audit["runtime_count"] == 1
        assert all(
            Path(p).is_relative_to(installed.python.parent.parent)
            for p in audit["product_files"]
        )
        yield child
    finally:
        if child.process.poll() is not None and child.output is None:
            child.output = child.process.communicate(timeout=3)
            (root / "t028-child-error.txt").write_bytes(child.output[1])
        if child.process.poll() is None:
            try:
                result = child.finish()
                assert result["outcome"] == "returned" and result["force_exit"] is False
                assert not (home / ".local/state/dutchmate/service/credential").exists()
                assert json.loads(
                    (home / ".local/state/dutchmate/service/owner.json").read_bytes()
                ) == {"version": 1, "cleanup_confirmed": True}
                child.private_output(child.token, _PRIVATE.encode())
            finally:
                if child.process.poll() is None:
                    child.process.kill()  # Test-owned guarded helper cleanup only.
                    child.process.communicate(timeout=3)


def _attach(
    installed: _Installed, child: Any, home: Path, root: Path
) -> tuple[str, Path]:
    profile_tree = ast.parse(
        (_REPO / "core/tests/contract/test_observation_composition.py").read_text()
    )
    text = next(
        ast.literal_eval(n.value)
        for n in profile_tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_PROFILE" for t in n.targets)
    )
    path, journal = home / "fixture.toml", home / "fixture.sqlite3"
    path.write_text(text)
    code, out, err, audit = _run(
        installed,
        root,
        home,
        [
            "--host",
            child.host,
            "--port",
            str(child.port),
            "attach",
            "--profile",
            str(path),
            "--journal",
            str(journal),
        ],
    )
    assert code == 0 and err == b"", (code, err)
    view = json.loads(out)["runtime"]
    assert view["state"] == "active"
    assert audit["credential_reads"] == len(audit["requests"]) == 1
    child.wait("rx_commits", 1)
    return view["session_id"], journal


def _delivered(
    out: bytes, command: str, host: str, port: int, audit: dict[str, Any]
) -> dict[str, Any]:
    assert out.endswith(b"\n") and out.count(b"\n") == 1 and len(out) <= _BOUND + 1
    assert audit["credential_reads"] == len(audit["requests"]) == 1
    authority = f"[::1]:{port}" if host == "::1" else f"127.0.0.1:{port}"
    assert audit["requests"] == [
        {
            "method": "POST",
            "path": "/v1/evidence/" + command,
            "host": authority,
            "authorization_count": 1,
        }
    ]
    value: dict[str, Any] = json.loads(out)
    assert (
        out
        == json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
        + b"\n"
    )
    return value


def test_t028_parent_has_independent_physical_and_account_guards() -> None:
    _parent_guards()


def test_t028_artifacts_include_evidence_and_all_installed_product_modules(
    installed_stack: _Installed,
    stack_artifacts: Any,
    account_home: Path,
    tmp_path: Path,
) -> None:
    modules = {
        "dutchmate-cli": ("dutchmate_cli", "evidence"),
        "dutchmate-service": ("dutchmate_service", "evidence_http"),
        "dutchmate-core": ("dutchmate_core", "evidence_access"),
    }
    for name, (package, module) in modules.items():
        wheel, sdist = stack_artifacts[0][name]
        with zipfile.ZipFile(wheel) as archive:
            assert f"{package}/{module}.py" in archive.namelist()
            if name == "dutchmate-core":
                assert f"{package}/adapters/terminal_evidence.py" in archive.namelist()
        with tarfile.open(sdist) as archive:
            assert any(
                p.endswith(f"/src/{package}/{module}.py") for p in archive.getnames()
            )
    code, out, err, audit = _run(
        installed_stack, tmp_path, account_home, ["evidence", "--help"], mode="no_io"
    )
    assert code == 0 and b"Usage:" in out and err == b""
    assert audit["requests"] == [] and audit["credential_reads"] == 0


@pytest.mark.parametrize("direct", [False, True])
@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--help"],
        ["evidence"],
        ["evidence", "--help"],
        ["evidence", "record", "--help"],
        ["evidence", "page", "--help"],
    ],
)
def test_t028_installed_help_and_no_command_do_no_account_or_network_work(
    installed_stack: _Installed,
    account_home: Path,
    tmp_path: Path,
    direct: bool,
    args: list[str],
) -> None:
    code, out, err, audit = _run(
        installed_stack, tmp_path, account_home, args, mode="no_io", direct=direct
    )
    assert code == 0 and b"Usage:" in out and err == b""
    assert audit["requests"] == [] and audit["credential_reads"] == 0


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
def test_t028_native_active_terminal_binary_snapshot_and_read_only_source(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
) -> None:
    with _service(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, journal = _attach(
            installed_stack, s, account_home, tmp_path / "attach"
        )
        args = _args(host, s.port, "page", session)
        first_args = list(args)
        first_args[first_args.index("--max-records") + 1] = "1"
        code, out, err, audit = _run(
            installed_stack, tmp_path / "first", account_home, first_args
        )
        assert code == 0 and err == b""
        first = _delivered(out, "page", host, s.port, audit)
        page = first["page"]
        assert page["snapshot_end_exclusive"] == 2 and page["truncated"]
        assert [r["sequence"] for r in page["records"]] == [0]
        provenance = page["records"][0]["provenance"]
        assert provenance["backend_observation_timestamp_domain"]["observer"] == (
            "host" if backend == 0 else "device"
        )
        s.control(emit=True)
        s.wait("rx_commits", 2)
        code, out, err, audit = _run(
            installed_stack,
            tmp_path / "continue",
            account_home,
            args + ["--cursor", page["continuation"]],
        )
        assert code == 0 and err == b""
        continued = _delivered(out, "page", host, s.port, audit)["page"]
        assert continued["snapshot_end_exclusive"] == 2
        assert [r["sequence"] for r in continued["records"]] == [1]
        assert (
            base64.b64decode(continued["records"][0]["payload_base64"], validate=True)
            == _PAYLOAD
        )
        code, out, err, audit = _run(
            installed_stack,
            tmp_path / "active-record",
            account_home,
            _args(host, s.port, "record", session),
        )
        assert code == 0 and err == b""
        assert (
            _delivered(out, "record", host, s.port, audit)["page"]["records"]
            == continued["records"]
        )
        assert s.audit()["terminal_opens"] == 0 and s.audit()["recorder_closes"] == 0
        code, out, err, audit = _run(
            installed_stack,
            tmp_path / "detach",
            account_home,
            ["--host", host, "--port", str(s.port), "detach"],
        )
        assert code == 0 and err == b""
        assert json.loads(out)["runtime"]["recorder_close_confirmed"] is True
        before = journal.read_bytes()
        for command in ("record", "page"):
            code, out, err, audit = _run(
                installed_stack,
                tmp_path / ("terminal-" + command),
                account_home,
                _args(host, s.port, command, session),
            )
            assert code == 0 and err == b""
            report = _delivered(out, command, host, s.port, audit)
            assert (
                report["run_id"] == first["run_id"] and report["session_id"] == session
            )
            if command == "record":
                assert report["page"]["records"] == continued["records"]
            else:
                records = report["page"]["records"]
                assert [r["sequence"] for r in records] == [0, 1, 2, 3]
                assert records[0]["provenance"] == provenance
                assert records[-1]["reason"] == "explicit_stop"
                assert (
                    base64.b64decode(records[1]["payload_base64"], validate=True)
                    == _PAYLOAD
                )
                assert (
                    base64.b64decode(records[2]["payload_base64"], validate=True)
                    == _AMBIENT
                )
                assert report["page"]["outcome"] == "complete"
            assert journal.read_bytes() == before
        final = s.wait("terminal_closes", 2)
        assert final["terminal_opens"] == 2 and len(final["uris"]) == 2
        assert all(
            final[key] == 2
            for key in ("query_only_set", "query_only_read", "begins", "rollbacks")
        )
        assert final["validation_in_transaction"]
        assert (
            final["opens"]
            == final["consumers"]
            == final["closes"]
            == final["recorder_closes"]
            == 1
        )
        unknown = _args(host, s.port, "record", "unassociated-session")
        code, out, err, audit = _run(
            installed_stack, tmp_path / "unknown", account_home, unknown
        )
        assert code == 4 and out == b""
        assert json.loads(err) == {
            "error": {"source": "evidence", "code": "session_not_associated"}
        }
        assert s.audit()["terminal_opens"] == 2


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize(
    "mode,expected,status",
    [
        ("stale", "authentication_required", 401),
        ("host", "host_rejected", 403),
        ("origin", "origin_rejected", 403),
        ("browser", "origin_rejected", 403),
    ],
)
def test_t028_native_security_precedes_terminal_reader_open(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    mode: str,
    expected: str,
    status: int,
) -> None:
    with _service(
        installed_stack, native_service_helper, account_home, tmp_path / "service", host
    ) as s:
        session, _ = _attach(installed_stack, s, account_home, tmp_path / "attach")
        _run(
            installed_stack,
            tmp_path / "detach",
            account_home,
            ["--host", host, "--port", str(s.port), "detach"],
        )
        alternate = s.token
        if mode == "stale":
            alternate = (b"0" if s.token[:1] != b"0" else b"1") + s.token[1:]
            (account_home / ".local/state/dutchmate/service/credential").write_bytes(
                alternate + b"\n"
            )
        code, out, err, audit = _run(
            installed_stack,
            tmp_path / "client",
            account_home,
            _args(host, s.port, "page", session),
            mode=mode if mode != "stale" else "normal",
        )
        assert code == 4 and out == b""
        assert json.loads(err) == {"error": {"source": "request", "code": expected}}
        _private(out, err, s.token, alternate)
        assert audit["credential_reads"] == len(audit["requests"]) == 1
        assert s.audit()["terminal_opens"] == s.audit()["reports"] == 0
        assert native_service_helper._status(host, s.port, s.token)[0] == 200


@pytest.mark.parametrize("command", ["record", "page"])
@pytest.mark.parametrize(
    "mode,event,phase",
    [
        ("before_interrupt", "before-request", "not_submitted"),
        ("wait", "waiting", "unknown"),
        ("repeat_interrupt", "waiting", "unknown"),
        ("output_interrupt", "report-received", "report_received"),
    ],
)
def test_t028_installed_sigint_ends_client_only_at_each_receipt_phase(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    command: str,
    mode: str,
    event: str,
    phase: str,
) -> None:
    with _service(
        installed_stack, native_service_helper, account_home, tmp_path / "service"
    ) as s:
        session, _ = _attach(installed_stack, s, account_home, tmp_path / "attach")
        with _cli(
            installed_stack,
            tmp_path / "client",
            account_home,
            _args(s.host, s.port, command, session),
            mode=mode,
        ) as child:
            child.wait_event(event)
            child.process.send_signal(signal.SIGINT)
            if mode == "repeat_interrupt":
                child.wait_event("cleanup")
                child.process.send_signal(signal.SIGINT)
            code, out, err, audit = child.finish()
        assert code == 130 and out == b""
        _failure(err, "interrupted", phase)
        _private(out, err, s.token, str(account_home).encode())
        assert audit["credential_reads"] == 1
        assert len(audit["requests"]) == (0 if mode == "before_interrupt" else 1)
        assert s.process.poll() is None and s.audit()["closes"] == 0
        s.control(emit=True)
        s.wait("rx_commits", 2)
        assert (
            json.loads(native_service_helper._status(s.host, s.port, s.token)[2])[
                "runtime"
            ]["state"]
            == "active"
        )


@pytest.mark.parametrize("command", ["record", "page"])
@pytest.mark.parametrize("case", ["stdout", "stderr", "both"])
def test_t028_installed_closed_evidence_pipes_preserve_exit_and_receipt(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    command: str,
    case: str,
) -> None:
    with _service(
        installed_stack, native_service_helper, account_home, tmp_path / "service"
    ) as s:
        session, _ = _attach(installed_stack, s, account_home, tmp_path / "attach")
        args = _args(
            s.host, s.port, command, session if case != "stderr" else "foreign-session"
        )
        code, out, err, audit = _run(
            installed_stack,
            tmp_path / "client",
            account_home,
            args,
            closed="stdout stderr" if case == "both" else case,
        )
        assert code == 1 and out == b""
        if case == "stdout":
            _failure(err, "output_failed", "report_received")
        else:
            assert err == b""
        assert audit["credential_reads"] == len(audit["requests"]) == 1
        assert s.process.poll() is None and s.audit()["closes"] == 0


@pytest.mark.parametrize("command", ["record", "page"])
@pytest.mark.parametrize(
    "fault",
    [
        "bad-json",
        "extra-field",
        "bad-binary",
        "bad-cursor",
        "wrong-error",
        "raw-overflow",
        "remote413",
        "fitting-bound",
    ],
)
def test_t028_installed_bad_peer_binary_cursor_and_delivery_bounds_are_private(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    command: str,
    fault: str,
) -> None:
    with _service(
        installed_stack, native_service_helper, account_home, tmp_path / "service"
    ) as s:
        session, _ = _attach(installed_stack, s, account_home, tmp_path / "attach")
        s.fault(fault)
        code, out, err, audit = _run(
            installed_stack,
            tmp_path / "client",
            account_home,
            _args(s.host, s.port, command, session),
        )
        if fault == "fitting-bound":
            assert code == 0 and err == b"" and len(out) == _BOUND + 1
            _delivered(out, command, s.host, s.port, audit)
        elif fault == "remote413":
            assert code == 4 and out == b""
            assert json.loads(err) == {
                "error": {"source": "evidence", "code": "delivery_too_large"}
            }
        else:
            assert code == 5 and out == b""
            _failure(err, "invalid_response", "unknown")
        _private(out, err, s.token, str(account_home).encode())
        assert audit["credential_reads"] == len(audit["requests"]) == 1
        assert s.audit()["reports"] == 1 and s.audit()["closes"] == 0
        assert s.process.poll() is None
