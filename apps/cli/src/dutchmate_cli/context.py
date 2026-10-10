"""Passive invocation values, lexical validation and read-only credential access."""

import errno
import os
import stat
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath


class CliFailureKind(StrEnum):
    INVALID_ARGUMENTS = "invalid_arguments"
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    CREDENTIAL_UNAVAILABLE = "credential_unavailable"
    UNSAFE_CREDENTIAL = "unsafe_credential"
    REQUEST_TIMEOUT = "request_timeout"
    TRANSPORT_FAILED = "transport_failed"
    INVALID_RESPONSE = "invalid_response"
    INTERRUPTED = "interrupted"
    OUTPUT_FAILED = "output_failed"
    INTERNAL_FAILURE = "internal_failure"


class CliFailure(RuntimeError):
    """Fixed category only; ordinary exception metadata remains transportable."""

    def __init__(self, kind: CliFailureKind) -> None:
        if not isinstance(kind, CliFailureKind):
            raise TypeError("CLI failure kind must be declared")
        self._kind = kind
        super().__init__(kind.value)

    @property
    def kind(self) -> CliFailureKind:
        return self._kind


@dataclass(frozen=True, slots=True)
class Endpoint:
    port: int
    host: str = "127.0.0.1"

    def __post_init__(self) -> None:
        if (
            type(self.host) is not str
            or self.host not in {"127.0.0.1", "::1"}
            or type(self.port) is not int
            or not 1 <= self.port <= 65535
        ):
            raise CliFailure(CliFailureKind.INVALID_ARGUMENTS)


@dataclass(frozen=True, slots=True)
class InvocationOptions:
    """Parser storage only, so constructing help context needs no valid target."""

    host: str = "127.0.0.1"
    port: int | None = None

    def target(self) -> Endpoint:
        if self.port is None:
            raise CliFailure(CliFailureKind.INVALID_ARGUMENTS)
        return Endpoint(port=self.port, host=self.host)


def _valid_path(value: str) -> bool:
    if type(value) is not str or not value.startswith("/") or "\x00" in value:
        return False
    try:
        return 1 <= len(value.encode("utf-8")) <= 4096
    except UnicodeEncodeError:
        return False


@dataclass(frozen=True, slots=True)
class AttachPaths:
    """Unexpanded wire strings; actual Profile/journal decisions belong remotely."""

    profile_path: str
    journal_path: str

    def __post_init__(self) -> None:
        if not _valid_path(self.profile_path) or not _valid_path(self.journal_path):
            raise CliFailure(CliFailureKind.INVALID_ARGUMENTS)


def _check_platform() -> None:
    if sys.platform not in {"linux", "darwin"} or any(
        not hasattr(os, name)
        for name in ("geteuid", "O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK")
    ):
        raise CliFailure(CliFailureKind.UNSUPPORTED_PLATFORM)


def _open_readonly(name: str, flags: int, *, dir_fd: int | None = None) -> int:
    try:
        return os.open(name, flags, dir_fd=dir_fd)
    except OSError as error:
        kind = (
            CliFailureKind.UNSAFE_CREDENTIAL
            if error.errno in {errno.ELOOP, errno.ENOTDIR}
            else CliFailureKind.CREDENTIAL_UNAVAILABLE
        )
    raise CliFailure(kind)


def _read_credential() -> str:
    import pwd

    uid = os.geteuid()
    home = pwd.getpwuid(uid).pw_dir
    if type(home) is not str or not home.startswith("/") or "\x00" in home:
        raise CliFailure(CliFailureKind.CREDENTIAL_UNAVAILABLE)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    # Descriptors own traversal and cleanup, with no check/open race or bootstrap
    # eligibility policy. No ancestor permissions are repaired or attested here.
    with ExitStack() as cleanup:
        directory = _open_readonly("/", directory_flags)
        cleanup.callback(os.close, directory)
        for component in (
            *PurePosixPath(home).parts[1:], ".local", "state", "dutchmate", "service",
        ):
            directory = _open_readonly(component, directory_flags, dir_fd=directory)
            cleanup.callback(os.close, directory)
        credential = _open_readonly("credential", file_flags, dir_fd=directory)
        cleanup.callback(os.close, credential)
        info = os.fstat(credential)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != uid
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
        ):
            raise CliFailure(CliFailureKind.UNSAFE_CREDENTIAL)
        content = bytearray()
        while len(content) < 66:
            chunk = os.read(credential, 66 - len(content))
            if not chunk:
                break
            content.extend(chunk)
        if (
            len(content) != 65
            or content[-1] != 10
            or any(byte not in b"0123456789abcdef" for byte in content[:-1])
        ):
            raise CliFailure(CliFailureKind.UNSAFE_CREDENTIAL)
        return content[:-1].decode("ascii")


def read_credential() -> str:
    """Read the fixed passwd-home token once and close every acquired descriptor."""
    _check_platform()
    try:
        return _read_credential()
    except CliFailure as error:
        kind = error.kind
    except (ImportError, NotImplementedError):
        kind = CliFailureKind.UNSUPPORTED_PLATFORM
    except (KeyError, OSError):
        kind = CliFailureKind.CREDENTIAL_UNAVAILABLE
    # Raised outside handlers: syscall paths/content/causes do not cross this API.
    raise CliFailure(kind)
