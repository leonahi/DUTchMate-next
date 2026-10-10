"""T018: installed entry/process/privacy acceptance in guarded temporary environments.

UV builds and installs wheel/sdist artifacts without editable imports. Every CLI
child loads test-only sitecustomize tripwires before product imports; the existing
006 native service child has its own independent guards. No physical transport or
product external-program launcher is involved. Genuine product failures belong to T019.
"""

import importlib.util
import json
import os
import signal
import subprocess
import sys
import tarfile
import time
import tomllib
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path
from typing import Any

import pytest

_PRIVATE = "private-t018-argv-exception-local-sentinel"
_TOKEN = b"0123456789abcdef" * 4
_REPO = Path(__file__).resolve().parents[3]

# Only test control values enter environment; credentials stay in isolated files.
_GUARD = r'''
import atexit, asyncio, importlib, json, logging, os, pwd, socket, sys, threading, types
from pathlib import Path
home = Path(os.environ["DUTCHMATE_TEST_HOME"])
audit_path = Path(os.environ["DUTCHMATE_TEST_AUDIT"])
event_path = Path(os.environ["DUTCHMATE_TEST_EVENT"])
mode = os.environ["DUTCHMATE_TEST_MODE"]
private = "private-t018-argv-exception-local-sentinel"
uid = os.geteuid()
original_account = pwd.getpwuid(uid)
real_home = Path(original_account.pw_dir)
real_parent = real_home.parent.stat()
protected = real_home / ".local/state/dutchmate"
isolated = pwd.struct_passwd((*original_account[:5], str(home), original_account.pw_shell))
audit = {"guard_ready": False, "account_isolated": False, "hardware_blocked": False,
         "real_bootstrap_blocked": False, "credential_reads": 0, "requests": []}
def publish():
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
def forbidden(*args, **kwargs):
    raise AssertionError("test child boundary violated")
def account(requested_uid):
    if mode == "no_io":
        forbidden()
    return isolated
pwd.getpwuid = account
original_open, original_mkdir = os.open, os.mkdir
def check_path(path, dir_fd):
    candidate = Path(os.fsdecode(path))
    if candidate.is_absolute() and candidate.is_relative_to(protected):
        forbidden()
    if str(candidate).startswith("/dev/") and str(candidate) != "/dev/null":
        forbidden()
    if dir_fd is not None and str(candidate) == real_home.name:
        identity = os.fstat(dir_fd)
        if (identity.st_dev, identity.st_ino) == (real_parent.st_dev, real_parent.st_ino):
            forbidden()
def guarded_open(path, flags, mode_bits=0o777, *, dir_fd=None):
    check_path(path, dir_fd)
    if mode == "no_io":
        forbidden()
    return original_open(path, flags, mode_bits, dir_fd=dir_fd)
def guarded_mkdir(path, mode_bits=0o777, *, dir_fd=None):
    check_path(path, dir_fd)
    forbidden()
os.open, os.mkdir = guarded_open, guarded_mkdir
try:
    import serial, serial.tools.list_ports
except ImportError:
    serial = types.ModuleType("serial")
    tools = types.ModuleType("serial.tools")
    ports = types.ModuleType("serial.tools.list_ports")
    serial.tools, tools.list_ports = tools, ports
    sys.modules.update({"serial": serial, "serial.tools": tools, "serial.tools.list_ports": ports})
serial.Serial = serial.serial_for_url = serial.tools.list_ports.comports = forbidden
for operation in (serial.Serial, serial.serial_for_url, serial.tools.list_ports.comports):
    try:
        operation()
    except AssertionError:
        continue
    raise AssertionError("physical tripwire missing")
audit["hardware_blocked"] = True
try:
    os.open(protected / "service/credential", os.O_RDONLY)
except AssertionError:
    audit["real_bootstrap_blocked"] = True
else:
    raise AssertionError("real-account tripwire missing")
audit["account_isolated"] = str(isolated.pw_dir) == str(home)
socket.getaddrinfo = forbidden
if mode == "no_io":
    os.geteuid = forbidden
    socket.socket.connect = socket.socket.connect_ex = forbidden
from dutchmate_cli import context
if mode == "no_io":
    context._check_platform = forbidden
original_credential = context.read_credential
def credential():
    audit["credential_reads"] += 1
    if mode == "before_interrupt":
        event_path.write_text("before-request", encoding="utf-8")
        threading.Event().wait()
    token = original_credential()
    if mode == "credential_exception":
        private_local = token
        raise RuntimeError(private + private_local)
    return token
context.read_credential = credential
import httpx
for name in ("httpx", "httpcore", "httpcore.connection", "httpcore.http11"):
    logger = logging.getLogger(name)
    logger.disabled = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(sys.stderr))
original_send = httpx.AsyncClient.send
async def send(self, request, *args, **kwargs):
    audit["requests"].append({"method": request.method, "path": request.url.path,
        "host": request.headers.get("Host"),
        "authorization_count": len(request.headers.get_list("authorization"))})
    if mode == "host":
        request.headers["Host"] = "localhost:" + str(request.url.port)
    elif mode == "origin":
        request.headers["Origin"] = "https://" + private
    elif mode == "browser":
        request.headers["Sec-Fetch-Mode"] = "cors"
    logging.getLogger("httpcore.connection").debug(private)
    response = await original_send(self, request, *args, **kwargs)
    if mode in {"wait", "repeat_interrupt"}:
        event_path.write_text("waiting", encoding="utf-8")
        await asyncio.Event().wait()
    return response
httpx.AsyncClient.send = send
if mode == "repeat_interrupt":
    original_exit = httpx.AsyncClient.__aexit__
    async def close(self, *args):
        await original_exit(self, *args)
        event_path.write_text("cleanup", encoding="utf-8")
        await asyncio.Event().wait()
    httpx.AsyncClient.__aexit__ = close
if mode in {"returned_interrupt", "raised_abort", "framework_exception", "output_interrupt"}:
    import typer
    from dutchmate_cli import main
    if mode == "output_interrupt":
        original_write = main._write
        first = True
        def write(record, *, error):
            global first
            if first:
                first = False
                event_path.write_text("report-received", encoding="utf-8")
                threading.Event().wait()
            return original_write(record, error=error)
        main._write = write
    else:
        class ControlledTyper(typer.Typer):
            def __call__(self, *args, **kwargs):
                if mode == "returned_interrupt":
                    return 130
                if mode == "raised_abort":
                    raise typer.Abort()
                private_local = private
                raise RuntimeError(private_local)
        main.app = ControlledTyper()
def final():
    module = sys.modules.get("dutchmate_cli.main")
    audit["product_file"] = getattr(module, "__file__", None)
    audit["prefix"] = sys.prefix
    publish()
atexit.register(final)
audit["guard_ready"] = True
publish()
'''


@dataclass(frozen=True)
class _Installed:
    root: Path
    python: Path
    entry: Path
    wheel: Path
    sdist: Path


def _uv(args: list[str], cwd: Path) -> None:
    result = subprocess.run(["uv", *args], cwd=cwd, capture_output=True, timeout=60)
    if result.returncode != 0:
        (cwd / "t018-uv-error.txt").write_bytes(result.stderr)
        pytest.fail("temporary UV packaging command failed; no product acceptance established")


@pytest.fixture(scope="session")
def package_artifacts(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, list[str]]:
    if sys.platform not in {"linux", "darwin"}:
        pytest.skip("T018 native console/package process tests require Linux/macOS")
    root = tmp_path_factory.mktemp("t018-package-artifacts")
    _uv(["build", "--offline", "--package", "dutchmate-cli", "--out-dir", str(root)], _REPO)
    wheels, sdists = list(root.glob("*.whl")), list(root.glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1
    packages = {row["name"]: row for row in tomllib.loads((_REPO / "uv.lock").read_text())["package"]}
    names: set[str] = set()
    def include(name: str) -> None:
        if name in names:
            return
        names.add(name)
        for dependency in packages[name].get("dependencies", []):
            include(dependency["name"])
    for dependency in packages["dutchmate-cli"]["dependencies"]:
        include(dependency["name"])
    pins = [f"{name}=={packages[name]['version']}" for name in sorted(names)]
    return wheels[0], sdists[0], pins


@pytest.fixture(scope="session", params=["wheel", "sdist"])
def installed_cli(
    request: pytest.FixtureRequest, package_artifacts: tuple[Path, Path, list[str]],
    tmp_path_factory: pytest.TempPathFactory,
) -> _Installed:
    wheel, sdist, pins = package_artifacts
    root = tmp_path_factory.mktemp("t018-installed-" + request.param)
    environment = root / "environment"
    _uv(["venv", "--offline", "--python", sys.executable, str(environment)], root)
    python = environment / "bin/python"
    artifact = wheel if request.param == "wheel" else sdist
    _uv(["pip", "install", "--python", str(python), str(artifact), *pins], root)
    entry = environment / "bin/dutchmate"
    assert entry.is_file()
    return _Installed(root, python, entry, wheel, sdist)


class _CliChild:
    def __init__(
        self, installed: _Installed, root: Path, home: Path, args: list[str], *,
        mode: str = "normal", direct: bool = False, closed: str = "",
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        guard = root / "child-guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(_GUARD, encoding="utf-8")
        self.audit_path, self.event_path = root / "cli-audit.json", root / "cli-event"
        cwd = root / "outside-repository"
        cwd.mkdir()
        env = dict(os.environ)
        env.pop("PYTHONHOME", None)
        env["PYTHONPATH"] = str(guard)  # Test guards only, never a product/source import path.
        env.update(DUTCHMATE_TEST_HOME=str(home), DUTCHMATE_TEST_AUDIT=str(self.audit_path),
                   DUTCHMATE_TEST_EVENT=str(self.event_path), DUTCHMATE_TEST_MODE=mode)
        command = [str(installed.entry), *args]
        if direct:
            command = [str(installed.python), "-c",
                       "import json,sys; from dutchmate_cli.main import main; sys.exit(main(json.loads(sys.argv[1])))",
                       json.dumps(args)]
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if "stdout" in closed:
            assert self.process.stdout is not None
            self.process.stdout.close()
            self.process.stdout = None
        if "stderr" in closed:
            assert self.process.stderr is not None
            self.process.stderr.close()
            self.process.stderr = None

    def wait_event(self, value: str) -> None:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self.event_path.exists() and self.event_path.read_text() == value:
                return
            if self.process.poll() is not None:
                pytest.fail("CLI exited before test-owned signal checkpoint")
            time.sleep(0.01)
        pytest.fail("CLI signal checkpoint did not arrive")

    def finish(self) -> tuple[int, bytes, bytes, dict[str, Any]]:
        stdout, stderr = self.process.communicate(timeout=12)
        stdout, stderr = stdout or b"", stderr or b""
        assert len(stdout) <= 1048577 and len(stderr) <= 1048577
        assert self.audit_path.exists(), "independent child safety guard did not initialize"
        audit = dict(json.loads(self.audit_path.read_bytes()))
        assert all(audit[name] is True for name in (
            "guard_ready", "account_isolated", "hardware_blocked", "real_bootstrap_blocked",
        ))
        assert self.process.returncode is not None
        return self.process.returncode, stdout, stderr, audit


@contextmanager
def _cli(*args: Any, **kwargs: Any) -> Iterator[_CliChild]:
    child = _CliChild(*args, **kwargs)
    try:
        yield child
    finally:
        if child.process.poll() is None:
            child.process.kill()  # Test-owned guarded CLI only; never the service/DUT.
            child.process.communicate(timeout=3)


def _credential(home: Path) -> Path:
    root = home / ".local/state/dutchmate/service"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / "credential"
    path.write_bytes(_TOKEN + b"\n")
    path.chmod(0o600)
    return path


def _private(stdout: bytes, stderr: bytes, *secrets: bytes) -> None:
    output = stdout + stderr
    if any(value and value in output for value in (_PRIVATE.encode(), _TOKEN, *secrets)):
        pytest.fail("private input or credential leaked into supported CLI output")
    assert b"Traceback" not in output and b"\x1b" not in output
    assert b"Exception ignored" not in output


def _failure(stderr: bytes, kind: str, phase: str = "not_submitted") -> None:
    assert stderr.endswith(b"\n") and stderr.count(b"\n") == 1
    assert json.loads(stderr) == {"error": {"source": "cli", "code": kind}, "request_outcome": phase}


@pytest.fixture
def native_service_helper(monkeypatch: pytest.MonkeyPatch) -> Any:
    source = _REPO / "apps/service/tests/test_service_process.py"
    name = "_dutchmate_cli_t018_service_helper"
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def test_t018_parent_physical_and_real_account_tripwires_are_active() -> None:
    if sys.platform not in {"linux", "darwin"}:
        pytest.skip("T018 independent POSIX account guards require Linux/macOS")
    import pwd

    import serial
    import serial.tools.list_ports

    operations: tuple[Any, ...] = (serial.Serial, serial.serial_for_url, serial.tools.list_ports.comports)
    for operation in operations:
        with pytest.raises(pytest.fail.Exception):
            operation()
    original = next(record for record in pwd.getpwall() if record.pw_uid == os.geteuid())
    with pytest.raises(pytest.fail.Exception):
        os.open(Path(original.pw_dir) / ".local/state/dutchmate/service/credential", os.O_RDONLY)


def test_t018_built_artifacts_declare_modules_dependencies_and_real_installed_entry(
    installed_cli: _Installed, account_home: Path, tmp_path: Path,
) -> None:
    with zipfile.ZipFile(installed_cli.wheel) as wheel:
        members = set(wheel.namelist())
        assert {f"dutchmate_cli/{name}.py" for name in ("__init__", "context", "client", "main")} <= members
        metadata = BytesParser().parsebytes(wheel.read(next(name for name in members if name.endswith("/METADATA"))))
        assert metadata["Name"] == "dutchmate-cli"
        requires = metadata.get_all("Requires-Dist")
        assert requires is not None
        assert len(requires) == 2 and any(value.startswith("httpx") for value in requires)
        assert any(value.startswith("typer") for value in requires)
        assert b"dutchmate = dutchmate_cli.main:main" in wheel.read(next(name for name in members if name.endswith("/entry_points.txt")))
    with tarfile.open(installed_cli.sdist) as sdist:
        names = sdist.getnames()
        assert all(any(name.endswith(f"/src/dutchmate_cli/{module}.py") for name in names)
                   for module in ("__init__", "context", "client", "main"))
    with _cli(installed_cli, tmp_path, account_home, ["--help"], mode="no_io") as child:
        code, stdout, stderr, audit = child.finish()
    assert code == 0 and b"Usage:" in stdout and stderr == b""
    assert Path(audit["prefix"]) == installed_cli.python.parent.parent
    assert Path(audit["product_file"]).is_relative_to(Path(audit["prefix"]))
    assert not Path(audit["product_file"]).is_relative_to(_REPO)
    assert audit["credential_reads"] == 0 and audit["requests"] == []
    _private(stdout, stderr, str(account_home).encode())


@pytest.mark.parametrize("direct", [False, True], ids=["installed-entry", "main-args"])
@pytest.mark.parametrize("args", [[], ["--help"], ["status", "--help"], ["attach", "--help"], ["detach", "--help"]])
def test_t018_child_help_is_resource_free_and_entry_matches_direct_main(
    installed_cli: _Installed, account_home: Path, tmp_path: Path, direct: bool, args: list[str],
) -> None:
    with _cli(installed_cli, tmp_path, account_home, args, mode="no_io", direct=direct) as child:
        code, stdout, stderr, audit = child.finish()
    assert code == 0 and b"Usage:" in stdout and stderr == b""
    assert audit["credential_reads"] == 0 and audit["requests"] == []
    _private(stdout, stderr, str(account_home).encode())


@pytest.mark.parametrize("direct", [False, True], ids=["installed-entry", "main-args"])
@pytest.mark.parametrize("args", [
    ["status"], ["--private-option", _PRIVATE],
    ["--host", _PRIVATE, "--port", "80", "status"], ["--port", _PRIVATE, "status"],
    ["--port", "80", "attach", "--profile", _PRIVATE, "--journal", "/journal"],
    ["--port", "80", "detach", _PRIVATE], ["status", "--port", "80"],
    ["--port", "80", "attach", "/private-profile", "/private-journal"],
])
def test_t018_input_bearing_grammar_failure_has_fixed_private_process_diagnostics(
    installed_cli: _Installed, account_home: Path, tmp_path: Path, direct: bool, args: list[str],
) -> None:
    with _cli(installed_cli, tmp_path, account_home, args, mode="no_io", direct=direct) as child:
        code, stdout, stderr, audit = child.finish()
    assert code == 2 and stdout == b""
    _failure(stderr, "invalid_arguments")
    assert audit["credential_reads"] == 0 and audit["requests"] == []
    _private(stdout, stderr, str(account_home).encode())


@pytest.mark.parametrize("direct", [False, True], ids=["installed-entry", "main-args"])
@pytest.mark.parametrize("mode,code,kind", [
    ("returned_interrupt", 130, "interrupted"), ("raised_abort", 130, "interrupted"),
    ("framework_exception", 1, "internal_failure"),
])
def test_t018_public_framework_interrupt_and_private_exception_paths_are_normalized(
    installed_cli: _Installed, account_home: Path, tmp_path: Path,
    direct: bool, mode: str, code: int, kind: str,
) -> None:
    with _cli(installed_cli, tmp_path, account_home, [], mode=mode, direct=direct) as child:
        actual, stdout, stderr, audit = child.finish()
    assert actual == code and stdout == b""
    _failure(stderr, kind)
    assert audit["credential_reads"] == 0 and audit["requests"] == []
    _private(stdout, stderr, str(account_home).encode())


@pytest.mark.parametrize("direct", [False, True], ids=["installed-entry", "main-args"])
@pytest.mark.parametrize("case,code,kind", [("missing", 3, "credential_unavailable"), ("exception", 1, "internal_failure")])
def test_t018_credential_failures_never_echo_token_cause_or_locals(
    installed_cli: _Installed, account_home: Path, tmp_path: Path,
    direct: bool, case: str, code: int, kind: str,
) -> None:
    if case == "exception":
        _credential(account_home)
    with _cli(installed_cli, tmp_path, account_home, ["--port", "80", "status"],
              mode="credential_exception" if case == "exception" else "normal", direct=direct) as child:
        actual, stdout, stderr, audit = child.finish()
    assert actual == code and stdout == b""
    _failure(stderr, kind)
    assert audit["credential_reads"] == 1 and audit["requests"] == []
    _private(stdout, stderr, str(account_home).encode())


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("case,expected", [
    ("valid", None), ("stale", "authentication_required"), ("host", "host_rejected"),
    ("origin", "origin_rejected"), ("browser", "origin_rejected"),
])
def test_t018_installed_entry_uses_actual_native_006_authentication_and_browser_gate(
    installed_cli: _Installed, native_service_helper: Any, account_home: Path,
    tmp_path: Path, host: str, case: str, expected: str | None,
) -> None:
    port = native_service_helper._port(host)
    with native_service_helper._child(account_home, port, host) as service:
        token = service.ready()
        alternate = token
        if case == "stale":
            alternate = (b"0" if token[:1] != b"0" else b"1") + token[1:]
            (account_home / ".local/state/dutchmate/service/credential").write_bytes(alternate + b"\n")
        with _cli(installed_cli, tmp_path / "client", account_home,
                  ["--host", host, "--port", str(port), "status"],
                  mode=case if case in {"host", "origin", "browser"} else "normal") as child:
            code, stdout, stderr, audit = child.finish()
        if expected is None:
            assert code == 0 and stderr == b""
            assert json.loads(stdout)["runtime"]["state"] == "inactive"
        else:
            assert code == 4 and stdout == b""
            assert json.loads(stderr) == {"error": {"source": "request", "code": expected}}
        _private(stdout, stderr, token, alternate, str(account_home).encode())
        assert audit["credential_reads"] == len(audit["requests"]) == 1
        authority = f"[::1]:{port}" if host == "::1" else f"127.0.0.1:{port}"
        assert audit["requests"] == [{"method": "GET", "path": "/v1/observation/status",
                                      "host": authority, "authorization_count": 1}]
        assert service.process.poll() is None and len(service.audit()["runtime"]) == 1
        assert native_service_helper._status(host, port, token)[0] == 200
        result = service.finish()
        assert result["outcome"] == "returned" and result["force_exit"] is False
        service.private_output(token, alternate, _PRIVATE.encode())


def test_t018_native_service_child_has_independent_safety_guards(
    native_service_helper: Any, account_home: Path,
) -> None:
    with native_service_helper._child(account_home, 8765, mode="probe") as service:
        assert service.finish(None) == {"account_isolated": True, "hardware_blocked": True, "real_bootstrap_blocked": True}
        service.private_output()


def test_t018_native_sigint_before_request_has_not_submitted_receipt(
    installed_cli: _Installed, account_home: Path, tmp_path: Path,
) -> None:
    with _cli(installed_cli, tmp_path, account_home, ["--port", "80", "status"], mode="before_interrupt") as child:
        child.wait_event("before-request")
        child.process.send_signal(signal.SIGINT)
        code, stdout, stderr, audit = child.finish()
    assert code == 130 and stdout == b""
    _failure(stderr, "interrupted")
    assert audit["requests"] == []
    _private(stdout, stderr, str(account_home).encode())


@pytest.mark.parametrize("mode,event,phase", [
    ("wait", "waiting", "unknown"), ("output_interrupt", "report-received", "report_received"),
    ("repeat_interrupt", "waiting", "unknown"),
])
def test_t018_native_first_and_repeated_sigint_end_client_only(
    installed_cli: _Installed, native_service_helper: Any, account_home: Path,
    tmp_path: Path, mode: str, event: str, phase: str,
) -> None:
    port = native_service_helper._port()
    with native_service_helper._child(account_home, port) as service:
        token = service.ready()
        with _cli(installed_cli, tmp_path / "client", account_home,
                  ["--port", str(port), "status"], mode=mode) as child:
            child.wait_event(event)
            child.process.send_signal(signal.SIGINT)
            if mode == "repeat_interrupt":
                child.wait_event("cleanup")
                child.process.send_signal(signal.SIGINT)
            code, stdout, stderr, audit = child.finish()
        assert code == 130 and stdout == b""
        _failure(stderr, "interrupted", phase)
        _private(stdout, stderr, token, str(account_home).encode())
        assert audit["credential_reads"] == len(audit["requests"]) == 1
        assert service.process.poll() is None and len(service.audit()["runtime"]) == 1
        assert native_service_helper._status("127.0.0.1", port, token)[0] == 200
        service.finish()
        service.private_output(token, _PRIVATE.encode())


@pytest.mark.parametrize("case", ["help_stdout", "status_stdout", "error_stderr", "both"])
def test_t018_closed_process_pipes_have_fixed_output_failure_or_exit_only(
    installed_cli: _Installed, native_service_helper: Any, account_home: Path,
    tmp_path: Path, case: str,
) -> None:
    if case == "status_stdout":
        port = native_service_helper._port()
        with native_service_helper._child(account_home, port) as service:
            token = service.ready()
            with _cli(installed_cli, tmp_path / "client", account_home,
                      ["--port", str(port), "status"], closed="stdout") as child:
                code, stdout, stderr, audit = child.finish()
            _private(stdout, stderr, token, str(account_home).encode())
            assert code == 1 and stdout == b"", "T019: installed output failure must survive interpreter shutdown"
            _failure(stderr, "output_failed", "report_received")
            assert len(audit["requests"]) == 1 and service.process.poll() is None
            service.finish()
            service.private_output(token)
    else:
        args = ["--help"] if case != "error_stderr" else ["status", _PRIVATE]
        closed = "stdout stderr" if case == "both" else "stdout" if case == "help_stdout" else "stderr"
        with _cli(installed_cli, tmp_path, account_home, args, mode="no_io", closed=closed) as child:
            code, stdout, stderr, audit = child.finish()
        _private(stdout, stderr, str(account_home).encode())
        assert code == 1 and stdout == b"", "T019: unusable stderr must produce exit1 without shutdown diagnostics"
        if case == "help_stdout":
            _failure(stderr, "output_failed")
        assert audit["requests"] == [] and audit["credential_reads"] == 0
