"""Isolated bootstrap and fail-closed hardware guards for service tests."""

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import serial
import serial.tools.list_ports


@pytest.fixture(autouse=True)
def block_physical_service_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("service tests must not discover or open physical hardware")

    monkeypatch.setattr(serial, "Serial", forbidden)
    monkeypatch.setattr(serial, "serial_for_url", forbidden)
    monkeypatch.setattr(serial.tools.list_ports, "comports", forbidden)


@pytest.fixture(autouse=True)
def isolate_service_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    # Patch the actual account lookup rather than bypass filesystem validation.
    if sys.platform in {"linux", "darwin"}:
        import pwd

        original = pwd.getpwuid(os.geteuid())
        real_home = Path(original.pw_dir)
        protected = real_home / ".local/state/dutchmate"
        parent_identity = real_home.parent.stat()
        original_open = os.open
        original_mkdir = os.mkdir

        def check_real_bootstrap(path: Any, dir_fd: int | None) -> None:
            if isinstance(path, (str, bytes, os.PathLike)):
                candidate = Path(os.fsdecode(path))
                if candidate.is_absolute() and candidate.is_relative_to(protected):
                    pytest.fail("service tests must not touch real account bootstrap")
                if dir_fd is not None and str(candidate) == real_home.name:
                    parent = os.fstat(dir_fd)
                    if (parent.st_dev, parent.st_ino) == (
                        parent_identity.st_dev,
                        parent_identity.st_ino,
                    ):
                        pytest.fail("service tests must use the isolated account home")

        def guarded_open(
            path: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
        ) -> int:
            check_real_bootstrap(path, dir_fd)
            return original_open(path, flags, mode, dir_fd=dir_fd)

        def guarded_mkdir(
            path: Any, mode: int = 0o777, *, dir_fd: int | None = None
        ) -> None:
            check_real_bootstrap(path, dir_fd)
            original_mkdir(path, mode, dir_fd=dir_fd)

        monkeypatch.setattr(os, "open", guarded_open)
        monkeypatch.setattr(os, "mkdir", guarded_mkdir)
        home = tmp_path / "account-home"
        home.mkdir(mode=0o700)
        record = pwd.struct_passwd((*original[:5], str(home), original.pw_shell))
        monkeypatch.setattr(pwd, "getpwuid", lambda uid: record)
    yield


@pytest.fixture
def account_home() -> Path:
    if sys.platform not in {"linux", "darwin"}:
        pytest.skip("native POSIX service bootstrap requires Linux/macOS")
    import pwd

    return Path(pwd.getpwuid(os.geteuid()).pw_dir)
