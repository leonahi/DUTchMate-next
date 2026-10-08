"""Contract regressions for T003 bootstrap, without HTTP or DUT resources."""

import importlib
import json
import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest


def _api() -> Any:
    # Resolve inside each test so missing implementation produces actual RED cases.
    return importlib.import_module("dutchmate_service.bootstrap")


def _acquire(port: int = 8765) -> Any:
    api = _api()
    return api.PrivateBootstrap.acquire(api.ServiceConfig(port))


def _layout(
    home: Path, marker: bytes | None = None, token: bytes | None = None
) -> Path:
    root = home / ".local/state/dutchmate/service"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, data in (("owner.json", marker), ("credential", token)):
        if data is not None:
            (root / name).write_bytes(data)
            (root / name).chmod(0o600)
    return root


def _marker(confirmed: bool) -> bytes:
    return json.dumps({"version": 1, "cleanup_confirmed": confirmed}).encode()


def _confirm(owner: Any) -> None:
    owner.confirm_cleanup(
        owner_settled=True,
        physical_release_confirmed=True,
        recorder_close_confirmed=True,
    )


def _failure(kind: str) -> Any:
    return pytest.raises(_api().BootstrapFailure, match=f"^{kind}$")


@pytest.mark.parametrize("port", [1, 1024, 65535])
@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_explicit_config(port: int, host: str) -> None:
    config = _api().ServiceConfig(port, host)
    assert config.port == port and config.host == host
    with pytest.raises((AttributeError, TypeError)):
        config.port = 5
    assert _api().ServiceConfig(port).host == "127.0.0.1"


@pytest.mark.parametrize("port", [0, -1, 65536, True, False, 1.0, "8765", None])
def test_invalid_ports_are_normalized(port: object) -> None:
    with _failure("invalid_configuration"):
        _api().ServiceConfig(port)


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "0.0.0.0",
        "::",
        "::ffff:127.0.0.1",
        "127.0.0.2",
        "[::1]",
        " 127.0.0.1",
        None,
    ],
)
def test_invalid_hosts_are_normalized(host: object) -> None:
    with _failure("invalid_configuration"):
        _api().ServiceConfig(8765, host)


@pytest.mark.parametrize("platform", ["win32", "freebsd", "unknown"])
def test_unsupported_platform_rejects_before_account_lookup(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
) -> None:
    api = _api()

    def forbidden() -> Path:
        pytest.fail("unsupported platform must precede account/resources")

    monkeypatch.setattr(api, "_account_home", forbidden)
    with monkeypatch.context() as patch:
        patch.setattr(sys, "platform", platform)
        with _failure("unsupported_platform"):
            _acquire()


def test_exception_category_readonly_with_normal_transport() -> None:
    api = _api()
    error = api.BootstrapFailure(api.BootstrapFailureKind.UNSAFE_BOOTSTRAP)
    with pytest.raises(AttributeError):
        error.kind = api.BootstrapFailureKind.OWNER_ACTIVE

    @contextmanager
    def forward() -> Iterator[None]:
        yield

    with pytest.raises(api.BootstrapFailure) as caught:
        with forward():
            raise error
    assert caught.value is error and str(error) == "unsafe_bootstrap"
    assert error.__traceback__ is not None


def test_fixed_account_path_private_modes_and_stable_lock(account_home: Path) -> None:
    owner = _acquire()
    root = account_home / ".local/state/dutchmate/service"
    try:
        assert root.is_dir()
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        lock = root / "owner.lock"
        assert stat.S_IMODE(lock.stat().st_mode) == 0o600
        identity = (lock.stat().st_dev, lock.stat().st_ino)
        owner.mark_unconfirmed()
        owner.publish_credential()
        assert owner.credential is not None and len(owner.credential) == 64
        assert all(c in "0123456789abcdef" for c in owner.credential)
        assert (root / "credential").read_bytes() == owner.credential.encode() + b"\n"
        for name in ("credential", "owner.json"):
            assert stat.S_IMODE((root / name).stat().st_mode) == 0o600
        assert json.loads((root / "owner.json").read_bytes()) == {
            "version": 1,
            "cleanup_confirmed": False,
        }
        owner.invalidate_credential()
        _confirm(owner)
    finally:
        owner.release()
    assert not (root / "credential").exists()
    assert identity == (lock.stat().st_dev, lock.stat().st_ino)
    assert json.loads((root / "owner.json").read_bytes())["cleanup_confirmed"]


def test_duplicate_on_different_port_preserves_existing_files(
    account_home: Path,
) -> None:
    owner = _acquire(1111)
    root = account_home / ".local/state/dutchmate/service"
    try:
        owner.mark_unconfirmed()
        owner.publish_credential()
        before = {p.name: p.read_bytes() for p in root.iterdir()}
        with _failure("owner_active"):
            _acquire(2222)
        assert {p.name: p.read_bytes() for p in root.iterdir()} == before
        owner.invalidate_credential()
        _confirm(owner)
    finally:
        owner.release()


def test_clean_restart_rotates_credential_and_never_truncates_lock(
    account_home: Path,
) -> None:
    root = _layout(account_home, _marker(True), b"0" * 64 + b"\n")
    lock = root / "owner.lock"
    lock.write_bytes(b"existing lock bytes")
    lock.chmod(0o600)
    identity = lock.stat().st_ino
    owner = _acquire()
    try:
        owner.mark_unconfirmed()
        owner.publish_credential()
        assert owner.credential != "0" * 64
        assert lock.read_bytes() == b"existing lock bytes"
        owner.invalidate_credential()
        _confirm(owner)
    finally:
        owner.release()
    assert lock.stat().st_ino == identity


@pytest.mark.parametrize(
    "marker",
    [
        b"",
        b"not json",
        b"\xff",
        _marker(False),
        b"{}",
        b'{"version":true,"cleanup_confirmed":true}',
        b'{"version":2,"cleanup_confirmed":true}',
        b'{"version":1,"cleanup_confirmed":1}',
        b'{"version":1,"cleanup_confirmed":true,"pid":42}',
        b'{"version":1,"version":1,"cleanup_confirmed":true}',
        b'{"version":1,"cleanup_confirmed":true,"cleanup_confirmed":true}',
        b"[" + b" " * 256 + b"]",
        b'{"version":NaN,"cleanup_confirmed":true}',
    ],
)
def test_stale_marker_rejects_without_rewriting_or_credential_access(
    account_home: Path,
    marker: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _layout(account_home, marker, b"private stale bytes")
    original = os.open

    def no_credential(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        assert path != "credential", "unclean marker must reject before credential"
        return original(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", no_credential)
        with _failure("previous_cleanup_unconfirmed"):
            _acquire()
    assert (root / "owner.json").read_bytes() == marker
    assert (root / "credential").read_bytes() == b"private stale bytes"
    # Rejection closes its guard rather than leaving a hidden owner_active state.
    with _failure("previous_cleanup_unconfirmed"):
        _acquire()


def test_token_without_marker_blocks_restart(account_home: Path) -> None:
    root = _layout(account_home, token=b"0" * 64 + b"\n")
    with _failure("previous_cleanup_unconfirmed"):
        _acquire()
    assert not (root / "owner.json").exists()


@pytest.mark.parametrize(
    "token",
    [b"", b"x" * 64 + b"\n", b"A" * 64 + b"\n", b"0" * 64, b"0" * 64 + b"\nextra"],
)
def test_malformed_stale_credentials_fail_closed(
    account_home: Path, token: bytes
) -> None:
    root = _layout(account_home, _marker(True), token)
    with _failure("unsafe_bootstrap"):
        _acquire()
    assert (root / "credential").read_bytes() == token
    assert (root / "owner.json").read_bytes() == _marker(True)


@pytest.mark.parametrize("name", ["owner.lock", "owner.json", "credential"])
@pytest.mark.parametrize("mode", [0o644, 0o400])
def test_existing_file_permissions_not_repaired(
    account_home: Path, name: str, mode: int
) -> None:
    root = _layout(account_home, _marker(True), b"0" * 64 + b"\n")
    target = root / name
    if not target.exists():
        target.write_bytes(b"lock")
    target.chmod(mode)
    with _failure("unsafe_bootstrap"):
        _acquire()
    assert stat.S_IMODE(target.stat().st_mode) == mode


@pytest.mark.parametrize("target", ["home", ".local", "service"])
def test_unsafe_directories_are_not_repaired(account_home: Path, target: str) -> None:
    root = _layout(account_home)
    directory = (
        account_home
        if target == "home"
        else (account_home / ".local" if target == ".local" else root)
    )
    directory.chmod(0o777 if target != "service" else 0o755)
    with _failure("unsafe_bootstrap"):
        _acquire()
    assert stat.S_IMODE(directory.stat().st_mode) == (
        0o755 if target == "service" else 0o777
    )


@pytest.mark.parametrize("name", ["owner.lock", "owner.json", "credential"])
def test_symlink_files_never_follow_or_modify_target(
    account_home: Path, name: str
) -> None:
    root = _layout(account_home, _marker(True), b"0" * 64 + b"\n")
    target = root / name
    target.unlink(missing_ok=True)
    outside = account_home / "outside"
    outside.write_bytes(b"untouched")
    outside.chmod(0o600)
    target.symlink_to(outside)
    with _failure("unsafe_bootstrap"):
        _acquire()
    assert outside.read_bytes() == b"untouched" and target.is_symlink()


def test_symlink_directory_is_rejected(account_home: Path) -> None:
    outside = account_home / "outside"
    outside.mkdir(mode=0o700)
    (account_home / ".local").symlink_to(outside, target_is_directory=True)
    with _failure("unsafe_bootstrap"):
        _acquire()
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("name", ["owner.lock", "owner.json", "credential"])
def test_hardlinked_files_reject_without_mutation(
    account_home: Path, name: str
) -> None:
    root = _layout(account_home, _marker(True), b"0" * 64 + b"\n")
    target = root / name
    if not target.exists():
        target.write_bytes(b"lock")
        target.chmod(0o600)
    alias = account_home / "alias"
    os.link(target, alias)
    before = target.read_bytes()
    with _failure("unsafe_bootstrap"):
        _acquire()
    assert target.read_bytes() == alias.read_bytes() == before


@pytest.mark.parametrize("name", ["owner.lock", "owner.json", "credential"])
def test_nonregular_files_reject_without_blocking(
    account_home: Path, name: str
) -> None:
    root = _layout(account_home, _marker(True), b"0" * 64 + b"\n")
    target = root / name
    target.unlink(missing_ok=True)
    os.mkfifo(target, mode=0o600)
    with _failure("unsafe_bootstrap"):
        _acquire()


@pytest.mark.parametrize("target", ["home", "owner.lock", "owner.json", "credential"])
def test_foreign_owner_fstat_is_rejected(
    account_home: Path,
    target: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _layout(account_home, _marker(True), b"0" * 64 + b"\n")
    selected = account_home if target == "home" else root / target
    if not selected.exists():
        selected.write_bytes(b"lock")
        selected.chmod(0o600)
    identity = (selected.stat().st_dev, selected.stat().st_ino)
    original = os.fstat

    def foreign(fd: int) -> os.stat_result:
        result = original(fd)
        if (result.st_dev, result.st_ino) == identity:
            fields = list(result)
            fields[4] = os.geteuid() + 1
            return os.stat_result(fields)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(os, "fstat", foreign)
        with _failure("unsafe_bootstrap"):
            _acquire()


def test_open_race_cannot_follow_replaced_lock(
    account_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _layout(account_home)
    outside = account_home / "outside"
    outside.write_bytes(b"untouched")
    original = os.open

    def raced(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if path == "owner.lock":
            (root / "owner.lock").symlink_to(outside)
        return original(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", raced)
        with _failure("unsafe_bootstrap"):
            _acquire()
    assert outside.read_bytes() == b"untouched"


def test_marker_read_is_bounded(
    account_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _layout(account_home, b" " * 10000)
    identity = (root / "owner.json").stat().st_ino
    original = os.read
    amounts: list[int] = []

    def bounded(fd: int, count: int) -> bytes:
        if os.fstat(fd).st_ino == identity:
            amounts.append(count)
        return original(fd, count)

    with monkeypatch.context() as patch:
        patch.setattr(os, "read", bounded)
        with _failure("previous_cleanup_unconfirmed"):
            _acquire()
    assert amounts and sum(amounts) <= 257


def test_partial_writes_publish_exact_private_credential(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _acquire()
    original = os.write

    def short_write(fd: int, data: bytes) -> int:
        return original(fd, data[: max(1, len(data) // 2)])

    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "write", short_write)
            owner.mark_unconfirmed()
            owner.publish_credential()
        root = account_home / ".local/state/dutchmate/service"
        assert (root / "credential").read_bytes() == owner.credential.encode() + b"\n"
        owner.invalidate_credential()
        _confirm(owner)
    finally:
        owner.release()


def test_failed_atomic_marker_publication_leaves_no_temp_file(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _acquire()

    def fail_replace(*args: Any, **kwargs: Any) -> None:
        raise OSError("untrusted diagnostic")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "replace", fail_replace)
            with _failure("bootstrap_io_failed") as failure:
                owner.mark_unconfirmed()
        assert failure.value.__context__ is None and failure.value.__cause__ is None
        root = account_home / ".local/state/dutchmate/service"
        assert {p.name for p in root.iterdir()} == {"owner.lock"}
    finally:
        owner.release()


def test_token_replacement_before_failed_fsync_remains_owned_for_cleanup(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _acquire()
    original = os.fsync

    def fail_directory(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("untrusted diagnostic")
        original(fd)

    try:
        owner.mark_unconfirmed()
        with monkeypatch.context() as patch:
            patch.setattr(os, "fsync", fail_directory)
            with _failure("bootstrap_io_failed"):
                owner.publish_credential()
        root = account_home / ".local/state/dutchmate/service"
        assert (root / "credential").is_file()
        owner.invalidate_credential()
        assert not (root / "credential").exists() and owner.credential is None
        _confirm(owner)
    finally:
        owner.release()


@pytest.mark.parametrize(
    "fact", ["owner_settled", "physical_release_confirmed", "recorder_close_confirmed"]
)
def test_uncertainty_cannot_confirm_marker(account_home: Path, fact: str) -> None:
    owner = _acquire()
    try:
        owner.mark_unconfirmed()
        facts = dict(
            owner_settled=True,
            physical_release_confirmed=True,
            recorder_close_confirmed=True,
        )
        facts[fact] = False
        with _failure("teardown_incomplete"):
            owner.confirm_cleanup(**facts)
        root = account_home / ".local/state/dutchmate/service"
        assert not json.loads((root / "owner.json").read_bytes())["cleanup_confirmed"]
    finally:
        owner.release()
    with _failure("previous_cleanup_unconfirmed"):
        _acquire()


def test_confirmation_requires_credential_invalidation(account_home: Path) -> None:
    owner = _acquire()
    try:
        owner.mark_unconfirmed()
        owner.publish_credential()
        with _failure("teardown_incomplete"):
            _confirm(owner)
        owner.invalidate_credential()
        _confirm(owner)
    finally:
        owner.release()


def test_removal_identity_mismatch_keeps_replacement(account_home: Path) -> None:
    owner = _acquire()
    try:
        owner.mark_unconfirmed()
        owner.publish_credential()
        root = account_home / ".local/state/dutchmate/service"
        replacement = root / "replacement"
        replacement.write_bytes(b"replacement")
        replacement.chmod(0o600)
        os.replace(replacement, root / "credential")
        with _failure("teardown_incomplete"):
            owner.invalidate_credential()
        assert (root / "credential").read_bytes() == b"replacement"
        with _failure("teardown_incomplete"):
            owner.release()
    finally:
        # release is idempotent and must not remove the substituted file.
        owner.release()


def test_after_replace_marker_fsync_failure_does_not_claim_rollback(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _acquire()
    original = os.fsync

    def fail_directory(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("untrusted diagnostic")
        original(fd)

    try:
        owner.mark_unconfirmed()
        with monkeypatch.context() as patch:
            patch.setattr(os, "fsync", fail_directory)
            with _failure("teardown_incomplete"):
                _confirm(owner)
        root = account_home / ".local/state/dutchmate/service"
        assert json.loads((root / "owner.json").read_bytes())["cleanup_confirmed"]
    finally:
        owner.release()


def test_release_keeps_dirty_marker_and_never_reuses_live_token(
    account_home: Path,
) -> None:
    owner = _acquire()
    owner.mark_unconfirmed()
    owner.publish_credential()
    owner.release()
    assert owner.credential is None
    root = account_home / ".local/state/dutchmate/service"
    assert not (root / "credential").exists()
    assert not json.loads((root / "owner.json").read_bytes())["cleanup_confirmed"]
    with _failure("previous_cleanup_unconfirmed"):
        _acquire()


def test_t023_release_preserves_failed_invalidation_without_retry(
    account_home: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _acquire()
    owner.mark_unconfirmed()
    owner.publish_credential()
    original = os.unlink
    attempts = 0

    def failed_once(path: Any, *, dir_fd: int | None = None) -> None:
        nonlocal attempts
        if path == "credential":
            attempts += 1
            if attempts == 1:
                raise OSError("private removal failure")
        original(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", failed_once)
    with _failure("teardown_incomplete"):
        owner.invalidate_credential()
    with _failure("teardown_incomplete"):
        owner.release()
    assert attempts == 1
    assert owner.credential is None
    root = account_home / ".local/state/dutchmate/service"
    assert (root / "credential").exists()
    assert json.loads((root / "owner.json").read_bytes())["cleanup_confirmed"] is False
    with _failure("previous_cleanup_unconfirmed"):
        _acquire()


def test_lock_descriptor_is_not_inheritable(
    account_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del account_home
    original = os.open
    lock_fds: list[int] = []

    def observed(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        fd = original(path, flags, *args, **kwargs)
        if path == "owner.lock":
            lock_fds.append(fd)
        return fd

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", observed)
        owner = _acquire()
    try:
        assert len(lock_fds) == 1 and not os.get_inheritable(lock_fds[0])
    finally:
        owner.release()


def test_account_lookup_does_not_use_environment_defaults(
    account_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = os.getenv

    def no_defaults(key: str, default: Any = None) -> Any:
        assert key not in {"HOME", "XDG_STATE_HOME"}
        return original(key, default)

    with monkeypatch.context() as patch:
        patch.setattr(os, "getenv", no_defaults)
        owner = _acquire()
    try:
        assert (account_home / ".local/state/dutchmate/service/owner.lock").exists()
    finally:
        owner.release()


def test_credential_read_is_bounded(
    account_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _layout(account_home, _marker(True), b"0" * 10000)
    identity = (root / "credential").stat().st_ino
    original = os.read
    amounts: list[int] = []

    def bounded(fd: int, count: int) -> bytes:
        if os.fstat(fd).st_ino == identity:
            amounts.append(count)
        return original(fd, count)

    with monkeypatch.context() as patch:
        patch.setattr(os, "read", bounded)
        with _failure("unsafe_bootstrap"):
            _acquire()
    assert amounts and sum(amounts) <= 66


def test_random_credential_uses_exactly_32_random_bytes(
    account_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del account_home
    import secrets

    original = secrets.token_hex
    sizes: list[int | None] = []

    def observed(nbytes: int | None = None) -> str:
        sizes.append(nbytes)
        return original(nbytes)

    owner = _acquire()
    try:
        owner.mark_unconfirmed()
        with monkeypatch.context() as patch:
            patch.setattr(secrets, "token_hex", observed)
            owner.publish_credential()
        assert sizes.count(32) == 1
        with _failure("invalid_configuration"):
            owner.publish_credential()
        owner.invalidate_credential()
        _confirm(owner)
    finally:
        owner.release()


def test_failed_lock_creation_is_normalized(
    account_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del account_home
    original = os.open

    def disappeared(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if path == "owner.lock":
            raise FileNotFoundError("directory entry became unavailable")
        return original(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", disappeared)
        with _failure("bootstrap_io_failed"):
            _acquire()


def test_publication_cleanup_keeps_replaced_temporary_file(
    account_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = _acquire()
    root = account_home / ".local/state/dutchmate/service"
    original = os.replace
    replaced_name: str | None = None

    def changed_entry(src: str, dst: str, **kwargs: Any) -> None:
        nonlocal replaced_name
        replaced_name = src
        original(src, "old-owned-file", **kwargs)
        substitute = root / "substitute"
        substitute.write_bytes(b"external replacement")
        substitute.chmod(0o600)
        original("substitute", src, **kwargs)
        raise OSError("publication failed after entry changed")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "replace", changed_entry)
            with _failure("bootstrap_io_failed"):
                owner.mark_unconfirmed()
        assert replaced_name is not None
        assert (root / replaced_name).read_bytes() == b"external replacement"
    finally:
        owner.release()
