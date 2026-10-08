"""T020 RED contracts: actual controlled launcher, isolated accounts and loopback.

Mutations caught: framework defaults/overrides, dual-stack/fallback, admitting a
second or stale owner, token reload/reuse, input-bearing transport logs and a
startup signal forgotten before readiness. Joined shutdown races belong to T021.
The executable helper below installs its own account and hardware tripwires;
pytest's parent-process monkeypatches do not cross a subprocess boundary.
"""

import errno
import importlib
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from typing import Any

import pytest


def _api() -> Any:
    # Missing production is a per-test RED failure, not a collection/setup error.
    return importlib.import_module("dutchmate_service.server")


def _state(home: Path) -> Path:
    return home / ".local/state/dutchmate/service"


def _layout(home: Path, marker: bytes | None, token: bytes | None = None) -> None:
    root = _state(home)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, content in (("owner.json", marker), ("credential", token)):
        if content is not None:
            path = root / name
            path.write_bytes(content)
            path.chmod(0o600)


def _port(host: str = "127.0.0.1") -> int:
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            if family == socket.AF_INET6:
                probe.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            probe.bind((host, 0))  # Test allocation only; production gets this port.
            return int(probe.getsockname()[1])
    except OSError as exc:
        if host == "::1" and exc.errno in {
            errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT, errno.EADDRNOTAVAIL,
        }:
            pytest.skip("native IPv6 loopback unavailable; not IPv6 acceptance")
        raise


def _wire(host: str, port: int, request: bytes) -> tuple[int, dict[bytes, bytes], bytes]:
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect((host, port))
        connection.sendall(request)
        output = bytearray()
        while chunk := connection.recv(65536):
            output.extend(chunk)
            if len(output) > 1048576 + 16384:
                pytest.fail("unbounded HTTP response")
    head, body = bytes(output).split(b"\r\n\r\n", 1)
    lines = head.split(b"\r\n")
    headers = dict(line.lower().split(b": ", 1) for line in lines[1:])
    return int(lines[0].split()[1]), headers, body


def _status(
    host: str, port: int, token: bytes, extra_headers: bytes = b"",
) -> tuple[int, dict[bytes, bytes], bytes]:
    authority = f"[::1]:{port}" if host == "::1" else f"127.0.0.1:{port}"
    return _wire(host, port, (
        f"GET /v1/observation/status HTTP/1.1\r\nHost: {authority}\r\n"
        "Connection: close\r\nAuthorization: Bearer "
    ).encode() + token + b"\r\n" + extra_headers + b"\r\n")


class _Child:
    def __init__(self, home: Path, port: int, host: str, mode: str, stage: str) -> None:
        self.home, self.port, self.host = home, port, host
        self.audit_path = home / f"audit-{port}.json"
        # Only isolated paths/configuration, never a credential, enter argv/env.
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--t020-child",
             str(home), str(port), host, mode, stage],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.output: tuple[bytes, bytes] | None = None

    def audit(self) -> dict[str, Any]:
        if not self.audit_path.exists():
            return {}
        data = self.audit_path.read_bytes()
        if len(data) > 65536:
            pytest.fail("unbounded helper audit")
        return dict(json.loads(data))

    def ready(self) -> bytes:
        deadline = time.monotonic() + 10
        credential = _state(self.home) / "credential"
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                pytest.fail("controlled launcher exited before authenticated readiness")
            if credential.exists() and self.audit().get("ready"):
                token = credential.read_bytes()
                if len(token) != 65 or not token.endswith(b"\n"):
                    pytest.fail("invalid credential publication")
                if _status(self.host, self.port, token[:-1])[0] == 200:
                    return token[:-1]
            time.sleep(0.02)
        pytest.fail("controlled launcher did not become ready")

    def finish(self, signum: int | None = signal.SIGTERM) -> dict[str, Any]:
        if signum is not None and self.process.poll() is None:
            self.process.send_signal(signum)
        self.output = self.process.communicate(timeout=10)
        assert self.process.returncode == 0, "helper failed (input-free diagnostics)"
        return self.audit()

    def private_output(self, *secrets: bytes) -> None:
        assert self.output is not None
        output = b"".join(self.output)
        if any(secret and secret in output for secret in secrets):
            pytest.fail("supplied input leaked into supported process output")
        if b"Traceback (most recent call last)" in output:
            pytest.fail("supported launcher exposed a debug traceback")
        if b"Invalid HTTP request received." in output:
            pytest.fail("pre-ASGI transport diagnostics were not disabled")


@contextmanager
def _child(
    home: Path, port: int, host: str = "127.0.0.1", *,
    mode: str = "serve", stage: str = "",
) -> Iterator[_Child]:
    child = _Child(home, port, host, mode, stage)
    try:
        yield child
    finally:
        if child.process.poll() is None:
            child.process.send_signal(signal.SIGTERM)
            try:
                child.process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                # Harness-only cleanup of our hardware-blocked helper, never an
                # owner takeover/forced-abandon policy in the production service.
                child.process.kill()
                child.process.communicate(timeout=3)


def test_t020_helper_installs_independent_account_and_hardware_guards(
    account_home: Path,
) -> None:
    with _child(account_home, 8765, mode="probe") as child:
        audit = child.finish(None)
        assert audit == {
            "account_isolated": True, "hardware_blocked": True,
            "real_bootstrap_blocked": True,
        }
        child.private_output()
    assert not _state(account_home).exists()


def test_t020_import_has_no_bootstrap_runtime_or_socket_effects(account_home: Path) -> None:
    _api()
    with _child(account_home, _port(), mode="import") as child:
        audit = child.finish(None)
        assert audit["bound"] == [] and audit["runtime"] == []
        assert audit["outcome"] == "imported"
        child.private_output()
    assert not _state(account_home).exists()


def test_t022_fresh_helper_bootstrap_uses_real_os_keyword_contracts(account_home: Path) -> None:
    with _child(account_home, 8765, mode="bootstrap-probe") as child:
        audit = child.finish(None)
        assert audit == {"outcome": "guard-acquired-released"}
        child.private_output()
    assert (_state(account_home) / "owner.lock").is_file()
    assert not (_state(account_home) / "credential").exists()


@pytest.mark.asyncio
async def test_t022_launcher_rejects_existing_loop_before_bootstrap(account_home: Path) -> None:
    from dutchmate_service.bootstrap import (
        BootstrapFailure,
        BootstrapFailureKind,
        ServiceConfig,
    )

    with pytest.raises(BootstrapFailure) as failure:
        _api().run_service(ServiceConfig(8765))
    assert failure.value.kind is BootstrapFailureKind.INVALID_CONFIGURATION
    assert not _state(account_home).exists()


def test_t022_launcher_rejects_foreign_thread_before_bootstrap(account_home: Path) -> None:
    from dutchmate_service.bootstrap import (
        BootstrapFailure,
        BootstrapFailureKind,
        ServiceConfig,
    )

    api = _api()
    failures: list[Exception] = []

    def foreign() -> None:
        try:
            api.run_service(ServiceConfig(8765))
        except Exception as failure:
            failures.append(failure)

    worker = Thread(target=foreign)
    worker.start()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert len(failures) == 1 and isinstance(failures[0], BootstrapFailure)
    assert failures[0].kind is BootstrapFailureKind.INVALID_CONFIGURATION
    assert not _state(account_home).exists()


@pytest.mark.parametrize("override", ["workers", "reload", "sockets", "proxy_headers"])
def test_t020_run_service_rejects_external_launch_overrides_before_bootstrap(
    account_home: Path, override: str,
) -> None:
    api = _api()
    from dutchmate_service.bootstrap import ServiceConfig

    with pytest.raises(TypeError):
        api.run_service(ServiceConfig(_port()), **{override: True})
    assert not _state(account_home).exists()


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_t020_controlled_single_worker_numeric_selected_family_only(
    account_home: Path, host: str,
) -> None:
    _api()
    port = _port(host)
    with _child(account_home, port, host) as child:
        token = child.ready()
        code, headers, body = _status(host, port, token)
        assert code == 200 and headers[b"cache-control"] == b"no-store"
        assert json.loads(body)["service_state"] == "ready"
        assert json.loads(body)["runtime"]["state"] == "inactive"
        assert _status(host, port, token, (
            b"X-Forwarded-For: 203.0.113.1\r\n"
            b"X-Forwarded-Host: supplied-private-host\r\n"
            b"Forwarded: for=203.0.113.1;host=supplied-private-host\r\n"
        ))[0] == 200
        audit = child.audit()
        assert audit["config"] == {
            "workers": 1, "reload": False, "proxy_headers": False,
            "access_log": False, "timeout_graceful_shutdown": None,
            "loop": "asyncio", "http": "h11", "lifespan": "on", "ws": "none",
        }
        assert audit["bound"] == [{
            "host": host, "port": port, "v6only": 1 if host == "::1" else None,
        }]
        assert audit["runtime"] == [{
            "same_process": True, "running_loop": True,
            "dirty_marker": True, "credential_present": True, "guard_held": True,
        }]
        assert audit["loggers_disabled"] is True
        # An explicit IPv6 listener must not expose IPv4 at the same port.
        if host == "::1":
            with pytest.raises(OSError), socket.socket() as probe:
                probe.settimeout(1)
                probe.connect(("127.0.0.1", port))
        child.finish()
        child.private_output(token)


@pytest.mark.parametrize("mode", ["ipv6-unavailable", "occupied-port"])
def test_t020_bind_failure_is_normalized_without_address_or_port_fallback(
    account_home: Path, mode: str,
) -> None:
    _api()
    host = "::1" if mode == "ipv6-unavailable" else "127.0.0.1"
    # Simulated unavailable IPv6 needs no native IPv6 support.
    port = _port()
    with socket.socket() as occupied:
        if mode == "occupied-port":
            occupied.bind(("127.0.0.1", port))
            occupied.listen()
        with _child(account_home, port, host, mode=mode) as child:
            audit = child.finish(None)
            assert audit["outcome"] == "listener_unavailable"
            assert audit["bound"] == [] and audit["runtime"] == []
            assert audit["bind_attempts"] == [{"host": host, "port": port}]
            child.private_output()


def test_t020_duplicate_process_different_port_does_not_replace_owner_state(
    account_home: Path,
) -> None:
    _api()
    first, second = _port(), _port()
    while second == first:
        second = _port()
    with _child(account_home, first) as owner:
        token = owner.ready()
        root = _state(account_home)
        original = {name: (root / name).read_bytes() for name in (
            "owner.json", "credential",
        )}
        lock = (root / "owner.lock").stat()
        with _child(account_home, second) as duplicate:
            audit = duplicate.finish(None)
            assert audit["outcome"] == "owner_active"
            assert audit["runtime"] == [] and audit["bind_attempts"] == []
            duplicate.private_output(token)
        for name, content in original.items():
            if (root / name).read_bytes() != content:
                pytest.fail("rejected duplicate changed owner's bootstrap state")
        assert (root / "owner.lock").stat().st_ino == lock.st_ino
        assert _status("127.0.0.1", first, token)[0] == 200
        owner.finish()
        owner.private_output(token)


@pytest.mark.parametrize("marker,credential", [
    (b'{"version":1,"cleanup_confirmed":false}', None),
    (b'{"version":1,"cleanup_confirmed":true,"extra":1}', None),
    (b'{"version":2,"cleanup_confirmed":true}', None),
    (b'{"version":1,"cleanup_confirmed":true,"cleanup_confirmed":false}', None),
    (b"malformed", None),
    (b"x" * 257, None),
    (None, b"a" * 64 + b"\n"),
])
def test_t020_stale_uncertain_state_is_preserved_without_listener_or_runtime(
    account_home: Path, marker: bytes | None, credential: bytes | None,
) -> None:
    _api()
    _layout(account_home, marker, credential)
    with _child(account_home, _port()) as child:
        audit = child.finish(None)
        assert audit["outcome"] == "previous_cleanup_unconfirmed"
        assert audit["runtime"] == [] and audit["bind_attempts"] == []
        child.private_output(b"a" * 64)
    for name, content in (("owner.json", marker), ("credential", credential)):
        path = _state(account_home) / name
        if content is None:
            assert not path.exists()
        elif path.read_bytes() != content:
            pytest.fail("uncertain state was automatically rewritten")


def test_t020_idle_crash_releases_os_lock_but_never_grants_cleanup(
    account_home: Path,
) -> None:
    _api()
    port = _port()
    with _child(account_home, port) as owner:
        token = owner.ready()
        owner.process.kill()  # Only our isolated, hardware-blocked helper.
        owner.output = owner.process.communicate(timeout=3)
        assert owner.process.returncode == -signal.SIGKILL
        root = _state(account_home)
        before = (root / "owner.json").read_bytes()
        assert json.loads(before) == {"version": 1, "cleanup_confirmed": False}
        with _child(account_home, _port()) as restart:
            audit = restart.finish(None)
            assert audit["outcome"] == "previous_cleanup_unconfirmed"
            assert audit["runtime"] == [] and audit["bind_attempts"] == []
            restart.private_output(token)
        assert (root / "owner.json").read_bytes() == before


def test_t020_credential_cached_private_removed_and_rotated_on_clean_restart(
    account_home: Path,
) -> None:
    _api()
    _layout(account_home, b'{"version":1,"cleanup_confirmed":true}', b"a" * 64 + b"\n")
    root = _state(account_home)
    with _child(account_home, _port()) as first:
        token = first.ready()
        if token == b"a" * 64 or any(c not in b"0123456789abcdef" for c in token):
            pytest.fail("credential was reused or malformed")
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        credential = root / "credential"
        assert stat.S_IMODE(credential.stat().st_mode) == 0o600
        assert credential.stat().st_nlink == 1
        # In-place operator edits do not change the cached process token/identity.
        credential.write_bytes(b"b" * 64 + b"\n")
        assert _status(first.host, first.port, b"b" * 64)[0] == 401
        assert _status(first.host, first.port, token)[0] == 200
        first.finish()
        first.private_output(token, b"a" * 64, b"b" * 64)
        assert not credential.exists()
        assert json.loads((root / "owner.json").read_bytes()) == {
            "version": 1, "cleanup_confirmed": True,
        }
    lock_inode = (root / "owner.lock").stat().st_ino
    with _child(account_home, _port()) as second:
        replacement = second.ready()
        if replacement == token:
            pytest.fail("new incarnation did not rotate credential")
        assert _status(second.host, second.port, token)[0] == 401
        assert _status(second.host, second.port, replacement)[0] == 200
        assert (root / "owner.lock").stat().st_ino == lock_inode
        second.finish()
        second.private_output(token, replacement)


@pytest.mark.parametrize("fault", ["missing-host", "duplicate-host", "malformed-header"])
def test_t020_actual_h11_rejection_is_fixed_plain_text_without_input_logging(
    account_home: Path, fault: str,
) -> None:
    _api()
    with _child(account_home, _port()) as child:
        token = child.ready()
        authority = f"Host: 127.0.0.1:{child.port}\r\n".encode()
        host = b"" if fault == "missing-host" else authority
        if fault == "duplicate-host":
            host += b"Host: supplied-private-host\r\n"
        malformed = b"supplied-private-header\r\n" if fault == "malformed-header" else b""
        request = (b"POST /supplied-private-path HTTP/1.1\r\n" + host + malformed
                   + b"Authorization: Bearer " + token
                   + b"\r\nConnection: close\r\nContent-Length: 21\r\n\r\n"
                   + b"supplied-private-body")
        code, headers, body = _wire(child.host, child.port, request)
        assert code == 400 and headers[b"content-type"] == b"text/plain; charset=utf-8"
        assert body == b"Invalid HTTP request received."
        assert _status(child.host, child.port, token)[0] == 200
        child.finish()
        child.private_output(token, b"supplied-private")


@pytest.mark.parametrize("stage", ["directory", "lock", "marker", "socket", "token", "lifespan"])
@pytest.mark.parametrize("mode", ["startup-sigint", "startup-sigterm"])
def test_t020_startup_stop_latches_before_ready_publication(
    account_home: Path, stage: str, mode: str,
) -> None:
    _api()
    with _child(account_home, _port(), mode=mode, stage=stage) as child:
        audit = child.finish(None)
        assert audit["signal_injected"] == stage
        assert audit["ready"] is False
        assert audit["force_exit"] is False
        assert audit["outcome"] == "returned"
        child.private_output()


def _helper_main() -> None:
    """Run real production composition; spies only observe external boundaries."""
    import asyncio
    import fcntl
    import logging
    import pwd

    import serial
    import serial.tools.list_ports
    import uvicorn

    _, home_text, port_text, host, mode, stage = sys.argv[1:]
    home, port = Path(home_text), int(port_text)
    patch = pytest.MonkeyPatch()
    original_account = pwd.getpwuid(os.geteuid())
    real_home = Path(original_account.pw_dir)
    isolated = pwd.struct_passwd((*original_account[:5], str(home), original_account.pw_shell))
    patch.setattr(pwd, "getpwuid", lambda uid: isolated)
    original_open, original_mkdir = os.open, os.mkdir
    protected = real_home / ".local/state/dutchmate"
    real_parent = real_home.parent.stat()

    def forbid(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("helper boundary violated")

    def check_path(path: Any, dir_fd: int | None) -> None:
        candidate = Path(os.fsdecode(path))
        if candidate.is_absolute() and candidate.is_relative_to(protected):
            forbid()
        if dir_fd is not None and str(candidate) == real_home.name:
            identity = os.fstat(dir_fd)
            if (identity.st_dev, identity.st_ino) == (real_parent.st_dev, real_parent.st_ino):
                forbid()

    def guarded_open(path: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
        check_path(path, dir_fd)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    audit: dict[str, Any] = {"bound": [], "bind_attempts": [], "runtime": [],
                             "ready": False, "force_exit": False}
    audit_path = home / f"audit-{port}.json"

    def publish() -> None:
        temporary = audit_path.with_suffix(".new")
        temporary.write_text(json.dumps(audit))
        temporary.replace(audit_path)

    def inject(boundary: str) -> None:
        if mode.startswith("startup-") and stage == boundary and "signal_injected" not in audit:
            audit["signal_injected"] = boundary
            publish()
            signum = signal.SIGINT if mode == "startup-sigint" else signal.SIGTERM
            os.kill(os.getpid(), signum)
            os.kill(os.getpid(), signum)  # Cooperative repeat, never Uvicorn force_exit.

    def guarded_mkdir(path: Any, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
        check_path(path, dir_fd)
        original_mkdir(path, mode, dir_fd=dir_fd)
        if os.fsdecode(path) == "service":
            inject("directory")

    patch.setattr(os, "open", guarded_open)
    patch.setattr(os, "mkdir", guarded_mkdir)
    patch.setattr(serial, "Serial", forbid)
    patch.setattr(serial, "serial_for_url", forbid)
    patch.setattr(serial.tools.list_ports, "comports", forbid)
    patch.setattr(os, "fork", forbid)
    patch.setattr(socket, "getaddrinfo", forbid)
    patch.setattr(uvicorn, "run", forbid)
    if mode == "probe":
        assert Path(pwd.getpwuid(os.geteuid()).pw_dir) == home
        operations: tuple[Any, ...] = (
            serial.Serial, serial.serial_for_url, serial.tools.list_ports.comports,
        )
        for operation in operations:
            try:
                operation()
            except AssertionError:
                continue
            raise AssertionError("hardware tripwire missing")
        try:
            os.open(protected / "service/credential", os.O_RDONLY)
        except AssertionError:
            pass
        else:
            raise AssertionError("real-account tripwire missing")
        audit_path.write_text(json.dumps({"account_isolated": True,
            "hardware_blocked": True, "real_bootstrap_blocked": True}))
        return

    if mode == "bootstrap-probe":
        from dutchmate_service.bootstrap import PrivateBootstrap, ServiceConfig

        owner = PrivateBootstrap.acquire(ServiceConfig(port))
        owner.release()
        audit_path.write_text(json.dumps({"outcome": "guard-acquired-released"}))
        return

    from dutchmate_service import bootstrap

    app: Any = importlib.import_module("dutchmate_service.app")

    # No test here is allowed to prepare a run.
    patch.setattr(app, "attach_basic_observation", forbid)
    actual_flock = fcntl.flock

    def flock(fd: int, operation: int) -> None:
        actual_flock(fd, operation)
        if operation == fcntl.LOCK_EX | fcntl.LOCK_NB:
            assert not os.get_inheritable(fd)
            inject("lock")

    patch.setattr(fcntl, "flock", flock)
    for name, boundary in (("mark_unconfirmed", "marker"), ("publish_credential", "token")):
        original = getattr(bootstrap.PrivateBootstrap, name)

        def observed(owner: Any, _method: Any = original, _boundary: str = boundary) -> Any:
            result = _method(owner)
            inject(_boundary)
            return result

        patch.setattr(bootstrap.PrivateBootstrap, name, observed)

    class ObservedSocket(socket.socket):
        def bind(self, address: Any) -> None:
            if self.family in {socket.AF_INET, socket.AF_INET6}:
                audit["bind_attempts"].append({"host": address[0], "port": address[1]})
                publish()
                if mode == "ipv6-unavailable" and self.family == socket.AF_INET6:
                    raise OSError(errno.EADDRNOTAVAIL, "bounded injected IPv6 failure")
            super().bind(address)
            if self.family in {socket.AF_INET, socket.AF_INET6}:
                audit["bound"].append({"host": address[0], "port": address[1], "v6only":
                    self.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY)
                    if self.family == socket.AF_INET6 else None})
                publish()
                inject("socket")

    patch.setattr(socket, "socket", ObservedSocket)
    original_runtime = app.ObservationRuntime
    initial_pid = os.getpid()

    def runtime() -> Any:
        root = _state(home)
        with (root / "owner.lock").open("rb") as lock:
            try:
                actual_flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                held = True
            else:
                held = False
        audit["runtime"].append({"same_process": os.getpid() == initial_pid,
            "running_loop": asyncio.get_running_loop().is_running(),
            "dirty_marker": json.loads((root / "owner.json").read_bytes()) ==
                {"version": 1, "cleanup_confirmed": False},
            "credential_present": (root / "credential").exists(), "guard_held": held})
        result = original_runtime()
        publish()
        inject("lifespan")
        return result

    patch.setattr(app, "ObservationRuntime", runtime)
    original_init, original_startup = uvicorn.Server.__init__, uvicorn.Server.startup

    def server_init(self: Any, config: Any) -> None:
        original_init(self, config)
        audit["config"] = {key: getattr(config, key) for key in (
            "workers", "reload", "proxy_headers", "access_log", "timeout_graceful_shutdown",
            "loop", "http", "lifespan", "ws",
        )}
        publish()

    async def startup(self: Any, sockets: Any = None) -> None:
        await original_startup(self, sockets=sockets)
        audit["ready"] = self.started
        audit["force_exit"] = self.force_exit
        audit["loggers_disabled"] = all(
            logging.getLogger(name).disabled and not logging.getLogger(name).propagate
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
        )
        publish()

    patch.setattr(uvicorn.Server, "__init__", server_init)
    patch.setattr(uvicorn.Server, "startup", startup)
    server = _api()
    if mode == "import":
        audit["outcome"] = "imported"
        publish()
        return
    try:
        config = bootstrap.ServiceConfig(port) if host == "127.0.0.1" else bootstrap.ServiceConfig(port, host)
        server.run_service(config)
    except bootstrap.BootstrapFailure as failure:
        audit["outcome"] = failure.kind.value
    else:
        audit["outcome"] = "returned"
    publish()


if __name__ == "__main__":
    try:
        _helper_main()
    except Exception:
        # Never echo input-bearing exception text/tracebacks from a helper.
        sys.exit(2)
