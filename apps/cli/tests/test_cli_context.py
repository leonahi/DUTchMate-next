"""Foundation contracts: lexical inputs and bounded read-only credential hygiene.

Catch permissive targets/path coercion, environment fallback, following links,
unsafe file acceptance, over-reading, resource leaks and bootstrap side effects.
Only account lookup/syscall failures are substituted; credential files are real.
"""

import errno
import importlib
import os
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest


def _api() -> Any:
    try:
        return importlib.import_module("dutchmate_cli.context")
    except ModuleNotFoundError as error:
        if error.name == "dutchmate_cli.context":
            pytest.fail("T004 context implementation is absent")
        raise


def _credential(home: Path, content: bytes = b"0123456789abcdef" * 4 + b"\n") -> Path:
    path = home / ".local/state/dutchmate/service/credential"
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o600)
    return path


def _failure(kind: str, work: Any) -> None:
    api = _api()
    with pytest.raises(api.CliFailure) as caught:
        work()
    assert caught.value.kind.value == kind
    assert caught.value.args == (kind,)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("port", [1, 80, 65535])
def test_exact_numeric_target(host: str, port: int) -> None:
    target = _api().InvocationOptions(host=host, port=port).target()
    assert (target.host, target.port) == (host, port)


def test_passive_options_and_default_host_need_no_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("passive options/lexical validation must not perform I/O")

    monkeypatch.setattr(os, "open", forbidden)
    if sys.platform in {"linux", "darwin"}:
        import pwd

        monkeypatch.setattr(pwd, "getpwuid", forbidden)
    options = api.InvocationOptions()
    assert options.host == "127.0.0.1" and options.port is None
    _failure("invalid_arguments", options.target)
    invalid = api.InvocationOptions(host="private-input", port=-1)
    _failure("invalid_arguments", invalid.target)
    assert api.InvocationOptions(port=80).target().host == "127.0.0.1"


@pytest.mark.parametrize("host", [
    "localhost", "0.0.0.0", "::", "::ffff:127.0.0.1", "127.0.0.2",
    "192.0.2.1", " 127.0.0.1", "127.0.0.1\n", "[::1]", "http://127.0.0.1",
    "", None, 127, b"127.0.0.1", [],
])
def test_other_hosts_reject_without_input_diagnostics(host: Any) -> None:
    _failure("invalid_arguments", lambda: _api().Endpoint(host=host, port=80))


@pytest.mark.parametrize("port", [None, False, True, 0, -1, 65536, 80.0, "80", []])
def test_port_requires_exact_bounded_integer(port: Any) -> None:
    _failure("invalid_arguments", lambda: _api().Endpoint(port=port))


@pytest.mark.parametrize("path", [
    "/", "/not-present/profile.toml", "/a/../b", "/~/literal/$HOME",
    "/spaces here/\n", "/" + "a" * 4095, "/" + "é" * 2047 + "a",
])
def test_attach_paths_are_lexical_and_preserved(
    path: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("attach lexical validation must not access Profile/journal")

    for name in ("open", "stat", "lstat", "mkdir"):
        monkeypatch.setattr(os, name, forbidden)
    for name in ("resolve", "exists", "stat", "read_bytes", "read_text"):
        monkeypatch.setattr(Path, name, forbidden)
    paths = api.AttachPaths(profile_path=path, journal_path=path)
    assert paths.profile_path == path and paths.journal_path == path


@pytest.mark.parametrize("field", ["profile_path", "journal_path"])
@pytest.mark.parametrize("bad", [
    "", "relative", "~/profile", "$HOME/profile", " /absolute", "\x00/absolute",
    "/a\x00b", "/" + "a" * 4096, "/" + "é" * 2048, "/\ud800",
    None, b"/absolute", Path("/absolute"), 1,
])
def test_invalid_attach_paths_fail_with_fixed_category(field: str, bad: Any) -> None:
    values = {"profile_path": "/profile", "journal_path": "/journal", field: bad}
    _failure("invalid_arguments", lambda: _api().AttachPaths(**values))


@pytest.mark.parametrize("kind", [
    "invalid_arguments", "unsupported_platform", "credential_unavailable",
    "unsafe_credential", "request_timeout", "transport_failed", "invalid_response",
    "interrupted", "output_failed", "internal_failure",
])
def test_failures_are_ordinary_fixed_category_exceptions(kind: str) -> None:
    api = _api()
    error = api.CliFailure(api.CliFailureKind(kind))
    assert error.kind.value == kind and error.args == (kind,)
    # Ordinary exceptions support context-manager/traceback transport.
    error.__traceback__ = None
    error.add_note("test-only metadata")
    with pytest.raises(api.CliFailure):
        raise error


def test_credential_uses_effective_uid_passwd_and_ignores_environment(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pwd

    _credential(account_home)
    record = pwd.getpwuid(os.geteuid())
    looked_up: list[int] = []

    def lookup(uid: int) -> Any:
        looked_up.append(uid)
        return record

    monkeypatch.setattr(pwd, "getpwuid", lookup)
    for name in ("HOME", "XDG_STATE_HOME", "DUTCHMATE_TOKEN", "DUTCHMATE_CREDENTIAL",
                 "DUTCHMATE_CREDENTIAL_PATH"):
        monkeypatch.setenv(name, "/private-input/environment-fallback")
    assert _api().read_credential() == "0123456789abcdef" * 4
    assert looked_up == [os.geteuid()]


@pytest.mark.parametrize("failure", [None, "content", "open", "read", "fstat"])
def test_descriptor_flags_readonly_scope_and_cleanup(
    account_home: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None,
) -> None:
    path = _credential(account_home, b"bad" if failure == "content" else b"a" * 64 + b"\n")
    api = _api()
    original_open, original_close = os.open, os.close
    original_read, original_fstat = os.read, os.fstat
    acquired: set[int] = set()
    closed: list[int] = []
    opened: list[str] = []
    remaining = 66
    file_fd: int | None = None

    def open_readonly(
        name: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None,
    ) -> int:
        nonlocal file_fd
        text = os.fsdecode(name)
        opened.append(text)
        assert flags & os.O_ACCMODE == os.O_RDONLY
        assert flags & (os.O_CREAT | os.O_TRUNC | os.O_APPEND) == 0
        assert flags & os.O_NOFOLLOW and flags & os.O_CLOEXEC
        if text != "/":
            assert "/" not in text and dir_fd in acquired
        if text == "credential":
            assert flags & os.O_NONBLOCK
            if failure == "open":
                raise OSError(errno.EIO, "private-open-diagnostic")
        else:
            assert flags & os.O_DIRECTORY
        descriptor = original_open(name, flags, mode, dir_fd=dir_fd)
        acquired.add(descriptor)
        if text == "credential":
            file_fd = descriptor
        assert not os.get_inheritable(descriptor)
        return descriptor

    def read_bounded(descriptor: int, size: int) -> bytes:
        nonlocal remaining
        assert descriptor == file_fd and 0 < size <= remaining
        if failure == "read":
            raise OSError(errno.EIO, "private-read-diagnostic")
        content = original_read(descriptor, size)
        remaining -= len(content)
        return content

    def checked_fstat(descriptor: int) -> os.stat_result:
        if descriptor == file_fd and failure == "fstat":
            raise OSError(errno.EIO, "private-fstat-diagnostic")
        return original_fstat(descriptor)

    def close(descriptor: int) -> None:
        assert descriptor in acquired and descriptor not in closed
        closed.append(descriptor)
        original_close(descriptor)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("credential helper must not mutate/bootstrap/inspect run resources")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", open_readonly)
        patch.setattr(os, "read", read_bounded)
        patch.setattr(os, "fstat", checked_fstat)
        patch.setattr(os, "close", close)
        for name in ("write", "mkdir", "chmod", "fchmod", "unlink", "rename",
                     "replace", "stat", "lstat"):
            patch.setattr(os, name, forbidden)
        if failure is None:
            assert api.read_credential() == "a" * 64
        else:
            _failure("unsafe_credential" if failure == "content" else
                     "credential_unavailable", api.read_credential)
    assert opened == ["/", *account_home.parts[1:], ".local", "state", "dutchmate",
                      "service", "credential"]
    assert acquired == set(closed)
    assert path.exists() and not (path.parent / "owner.lock").exists()
    assert not (path.parent / "owner.json").exists()


@pytest.mark.parametrize("content", [
    b"", b"a" * 64, b"a" * 63 + b"\n", b"a" * 65 + b"\n", b"A" * 64 + b"\n",
    b"g" * 64 + b"\n", b"a" * 64 + b"\r", b"a" * 64 + b"\r\n",
    b"a" * 64 + b"\nX", b"a" * 64 + b"\n" + b"x" * 200000,
    b"\xff" + b"a" * 63 + b"\n", b"a" * 63 + b"\x00\n",
])
def test_rejects_nonexact_credential_content(account_home: Path, content: bytes) -> None:
    _credential(account_home, content)
    _failure("unsafe_credential", _api().read_credential)


@pytest.mark.parametrize("chunk_size", [1, 7, 66])
@pytest.mark.parametrize("overflow", [False, True])
def test_bounded_partial_reads_and_detection_byte(
    account_home: Path, monkeypatch: pytest.MonkeyPatch, chunk_size: int, overflow: bool,
) -> None:
    _credential(account_home, b"a" * 64 + b"\n" + (b"x" * 100000 if overflow else b""))
    api = _api()
    original = os.read
    consumed = 0

    def partial(descriptor: int, size: int) -> bytes:
        nonlocal consumed
        assert size <= 66 - consumed
        content = original(descriptor, min(chunk_size, size))
        consumed += len(content)
        return content

    monkeypatch.setattr(os, "read", partial)
    if overflow:
        _failure("unsafe_credential", api.read_credential)
        assert consumed == 66
    else:
        assert api.read_credential() == "a" * 64
        assert consumed == 65


@pytest.mark.parametrize("mode", [0o400, 0o640, 0o644, 0o700, 0o1600])
def test_rejects_unsafe_mode_without_repair(account_home: Path, mode: int) -> None:
    path = _credential(account_home)
    path.chmod(mode)
    _failure("unsafe_credential", _api().read_credential)
    assert path.stat().st_mode & 0o7777 == mode


def test_rejects_wrong_owner(account_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _credential(account_home)
    uid = path.stat().st_uid
    monkeypatch.setattr(os, "geteuid", lambda: uid + 1)
    _failure("unsafe_credential", _api().read_credential)


def test_rejects_hard_link(account_home: Path) -> None:
    path = _credential(account_home)
    os.link(path, account_home / "other-link")
    _failure("unsafe_credential", _api().read_credential)
    assert path.stat().st_nlink == 2


@pytest.mark.parametrize("kind", ["directory", "fifo", "symlink"])
def test_rejects_nonregular_file_without_blocking(account_home: Path, kind: str) -> None:
    path = _credential(account_home)
    path.unlink()
    if kind == "directory":
        path.mkdir(mode=0o600)
    elif kind == "fifo":
        os.mkfifo(path, mode=0o600)
    else:
        target = account_home / "other-credential"
        target.write_bytes(b"a" * 64 + b"\n")
        target.chmod(0o600)
        path.symlink_to(target)
    _failure("unsafe_credential", _api().read_credential)


@pytest.mark.parametrize("depth", range(5))
@pytest.mark.parametrize("symlink", [False, True])
def test_rejects_unsafe_ancestor_traversal(
    account_home: Path, depth: int, symlink: bool,
) -> None:
    _credential(account_home)
    ancestor = account_home.joinpath(*(".local", "state", "dutchmate", "service")[:depth])
    moved = ancestor.with_name(ancestor.name + "-moved")
    ancestor.rename(moved)
    if symlink:
        ancestor.symlink_to(moved, target_is_directory=True)
    else:
        ancestor.write_bytes(b"not-directory")
    _failure("unsafe_credential", _api().read_credential)


@pytest.mark.parametrize("layout", ["absent", "missing_file"])
def test_missing_credential_does_not_create_state(account_home: Path, layout: str) -> None:
    if layout == "missing_file":
        _credential(account_home).unlink()
    before = set(account_home.rglob("*"))
    _failure("credential_unavailable", _api().read_credential)
    assert set(account_home.rglob("*")) == before


@pytest.mark.parametrize("failure", [KeyError("private-account"),
                                     OSError(errno.EIO, "private-account")])
def test_account_lookup_failure_is_fixed(
    account_home: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception,
) -> None:
    import pwd

    def lookup(uid: int) -> Any:
        raise failure

    monkeypatch.setattr(pwd, "getpwuid", lookup)
    _failure("credential_unavailable", _api().read_credential)


@pytest.mark.parametrize("number,kind", [
    (errno.ELOOP, "unsafe_credential"), (errno.ENOTDIR, "unsafe_credential"),
    (errno.EACCES, "credential_unavailable"), (errno.ENOENT, "credential_unavailable"),
    (errno.EIO, "credential_unavailable"),
])
def test_open_error_classification(
    monkeypatch: pytest.MonkeyPatch, number: int, kind: str,
) -> None:
    api = _api()

    def fail(*args: object, **kwargs: object) -> int:
        raise OSError(number, "private-filesystem-diagnostic")

    monkeypatch.setattr(os, "open", fail)
    _failure(kind, api.read_credential)


@pytest.mark.parametrize("platform", ["win32", "freebsd14"])
def test_unsupported_platform_precedes_account_or_file_work(
    monkeypatch: pytest.MonkeyPatch, platform: str,
) -> None:
    api = _api()

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("unsupported platform must fail before account/file work")

    if sys.platform in {"linux", "darwin"}:
        import pwd

        monkeypatch.setattr(pwd, "getpwuid", forbidden)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(os, "open", forbidden)
    _failure("unsupported_platform", api.read_credential)


@pytest.mark.parametrize("primitive", ["O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC",
                                       "O_NONBLOCK"])
def test_missing_platform_primitive_fails_closed(
    monkeypatch: pytest.MonkeyPatch, primitive: str,
) -> None:
    api = _api()
    monkeypatch.delattr(os, primitive)
    _failure("unsupported_platform", api.read_credential)


def test_unimplemented_descriptor_access_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _api()

    def fail(*args: object, **kwargs: object) -> int:
        raise NotImplementedError("private-platform-detail")

    monkeypatch.setattr(os, "open", fail)
    _failure("unsupported_platform", api.read_credential)


def test_close_error_still_attempts_every_descriptor_cleanup(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _credential(account_home)
    api = _api()
    original_open, original_close = os.open, os.close
    opened: list[int] = []
    closed: list[int] = []

    def open_file(
        path: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None,
    ) -> int:
        descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(descriptor)
        return descriptor

    def close(descriptor: int) -> None:
        original_close(descriptor)
        closed.append(descriptor)
        if len(closed) == 1:
            raise OSError(errno.EIO, "private-close-diagnostic")

    monkeypatch.setattr(os, "open", open_file)
    monkeypatch.setattr(os, "close", close)
    _failure("credential_unavailable", api.read_credential)
    assert closed == opened[::-1]


def test_client_does_not_apply_service_directory_or_marker_eligibility_policy(
    account_home: Path,
) -> None:
    path = _credential(account_home)
    # Client verifies traversal/file hygiene only. Startup's directory and dirty
    # incarnation eligibility rules remain exclusively with the service.
    path.parent.chmod(0o755)
    (path.parent / "owner.json").write_bytes(b"invalid-marker")
    (path.parent / "owner.lock").write_bytes(b"unrelated-lock")
    assert _api().read_credential() == "0123456789abcdef" * 4
    assert path.parent.stat().st_mode & 0o7777 == 0o755


def test_import_does_not_lookup_account_or_open_files(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _api()

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("context import must not prepare account/file resources")

    monkeypatch.setattr(os, "open", forbidden)
    if sys.platform in {"linux", "darwin"}:
        import pwd

        monkeypatch.setattr(pwd, "getpwuid", forbidden)
    # Execute the source afresh without replacing canonical exception/enum
    # definitions held by modules imported earlier in the full suite.
    runpy.run_path(api.__file__, run_name="dutchmate_cli._context_import_probe")
