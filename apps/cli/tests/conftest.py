"""Temporary account and physical-device tripwires for CLI tests."""

import os
import sys
from pathlib import Path
from typing import Any

import pytest
import serial
import serial.tools.list_ports


@pytest.fixture(autouse=True)
def block_physical_cli_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("CLI tests must not discover or open physical hardware")

    monkeypatch.setattr(serial, "Serial", forbidden)
    monkeypatch.setattr(serial, "serial_for_url", forbidden)
    monkeypatch.setattr(serial.tools.list_ports, "comports", forbidden)


@pytest.fixture(autouse=True)
def isolate_cli_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform not in {"linux", "darwin"}:
        return
    import pwd

    original = pwd.getpwuid(os.geteuid())
    real_home = Path(original.pw_dir)
    protected = real_home / ".local/state/dutchmate"
    parent_identity = real_home.parent.stat()
    original_open, original_mkdir = os.open, os.mkdir

    def check_real_account(path: Any, dir_fd: int | None) -> None:
        candidate = Path(os.fsdecode(path))
        if candidate.is_absolute() and candidate.is_relative_to(protected):
            pytest.fail("CLI tests must not touch real account service state")
        if dir_fd is not None and str(candidate) == real_home.name:
            parent = os.fstat(dir_fd)
            if (parent.st_dev, parent.st_ino) == (
                parent_identity.st_dev, parent_identity.st_ino,
            ):
                pytest.fail("CLI tests must use the isolated account home")

    def guarded_open(
        path: Any, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        check_real_account(path, dir_fd)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    def guarded_mkdir(
        path: Any, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> None:
        check_real_account(path, dir_fd)
        original_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", guarded_open)
    monkeypatch.setattr(os, "mkdir", guarded_mkdir)
    home = tmp_path / "account-home"
    home.mkdir(mode=0o700)
    record = pwd.struct_passwd((*original[:5], str(home), original.pw_shell))
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: record)


@pytest.fixture
def account_home() -> Path:
    if sys.platform not in {"linux", "darwin"}:
        pytest.skip("native credential filesystem tests require Linux/macOS")
    import pwd

    return Path(pwd.getpwuid(os.geteuid()).pw_dir)
