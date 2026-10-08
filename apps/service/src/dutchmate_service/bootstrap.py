"""Private per-account POSIX ownership, credential and cleanup facts.

These helpers do not construct runtimes, read Profiles, open DUTs or bind sockets.
The later controlled launcher owns their ordering around its service lifespan.
"""

import errno
import json
import os
import re
import secrets
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class BootstrapFailureKind(StrEnum):
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    INVALID_CONFIGURATION = "invalid_configuration"
    UNSAFE_BOOTSTRAP = "unsafe_bootstrap"
    OWNER_ACTIVE = "owner_active"
    PREVIOUS_CLEANUP_UNCONFIRMED = "previous_cleanup_unconfirmed"
    BOOTSTRAP_IO_FAILED = "bootstrap_io_failed"
    LISTENER_UNAVAILABLE = "listener_unavailable"
    TEARDOWN_INCOMPLETE = "teardown_incomplete"


class BootstrapFailure(RuntimeError):
    """Read-only category; ordinary exception metadata remains transportable."""

    def __init__(self, kind: BootstrapFailureKind) -> None:
        if not isinstance(kind, BootstrapFailureKind):
            raise TypeError("bootstrap failure kind must be declared")
        self._kind = kind
        super().__init__(kind.value)

    @property
    def kind(self) -> BootstrapFailureKind:
        return self._kind


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    port: int
    host: str = "127.0.0.1"

    def __post_init__(self) -> None:
        if (
            type(self.port) is not int
            or not 1 <= self.port <= 65535
            or type(self.host) is not str
            or self.host not in {"127.0.0.1", "::1"}
        ):
            raise BootstrapFailure(BootstrapFailureKind.INVALID_CONFIGURATION)


def _normalized[T](
    work: Callable[[], T],
    fallback: BootstrapFailureKind = BootstrapFailureKind.BOOTSTRAP_IO_FAILED,
) -> T:
    # Raise outside handlers: no filesystem detail/cause/context crosses the API.
    try:
        return work()
    except BootstrapFailure as error:
        kind = error.kind
    except NotImplementedError:
        kind = BootstrapFailureKind.UNSUPPORTED_PLATFORM
    except OSError:
        kind = fallback
    raise BootstrapFailure(kind)


def _check_platform() -> None:
    if sys.platform not in {"linux", "darwin"} or any(
        not hasattr(os, name)
        for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC", "O_NONBLOCK")
    ):
        raise BootstrapFailure(BootstrapFailureKind.UNSUPPORTED_PLATFORM)


def _account_home() -> Path:
    import pwd

    return Path(pwd.getpwuid(os.geteuid()).pw_dir)


def _validate_directory(fd: int, *, private: bool, service: bool = False) -> None:
    info = os.fstat(fd)
    mode = stat.S_IMODE(info.st_mode)
    trusted_owner = info.st_uid == os.geteuid() or (not private and info.st_uid == 0)
    writable = bool(mode & 0o022)
    trusted_sticky_root = not private and info.st_uid == 0 and bool(mode & stat.S_ISVTX)
    if (
        not stat.S_ISDIR(info.st_mode)
        or not trusted_owner
        or (writable and not trusted_sticky_root)
        or (service and mode != 0o700)
    ):
        raise BootstrapFailure(BootstrapFailureKind.UNSAFE_BOOTSTRAP)


def _open_directory(home: Path) -> int:
    if not home.is_absolute() or ".." in home.parts or "\x00" in str(home):
        raise BootstrapFailure(BootstrapFailureKind.UNSAFE_BOOTSTRAP)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        _validate_directory(fd, private=home == Path("/"))
        descendants = (".local", "state", "dutchmate", "service")
        components = (*home.parts[1:], *descendants)
        home_depth = len(home.parts) - 1
        for depth, name in enumerate(components, 1):
            try:
                next_fd = os.open(name, flags, dir_fd=fd)
            except FileNotFoundError:
                if depth <= home_depth:
                    raise BootstrapFailure(
                        BootstrapFailureKind.UNSAFE_BOOTSTRAP
                    ) from None
                os.mkdir(name, mode=0o700, dir_fd=fd)
                next_fd = os.open(name, flags, dir_fd=fd)
            except OSError as error:
                if error.errno in {errno.ELOOP, errno.ENOTDIR, errno.EACCES}:
                    raise BootstrapFailure(
                        BootstrapFailureKind.UNSAFE_BOOTSTRAP
                    ) from None
                raise
            try:
                _validate_directory(
                    next_fd,
                    private=depth >= home_depth,
                    service=depth == len(components),
                )
            except BaseException:
                os.close(next_fd)
                raise
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _validate_file(fd: int) -> os.stat_result:
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise BootstrapFailure(BootstrapFailureKind.UNSAFE_BOOTSTRAP)
    return info


def _open_file(directory: int, name: str, *, create: bool = False) -> int | None:
    flags = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    flags |= (os.O_RDWR | os.O_CREAT) if create else os.O_RDONLY
    try:
        fd = os.open(name, flags, 0o600, dir_fd=directory)
    except FileNotFoundError:
        if create:
            raise
        return None
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.EISDIR, errno.ENOTDIR, errno.EACCES}:
            raise BootstrapFailure(BootstrapFailureKind.UNSAFE_BOOTSTRAP) from None
        raise
    try:
        _validate_file(fd)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _read_file(directory: int, name: str, limit: int) -> bytes | None:
    fd = _open_file(directory, name)
    if fd is None:
        return None
    try:
        data = bytearray()
        while len(data) <= limit:
            chunk = os.read(fd, limit + 1 - len(data))
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)
    finally:
        os.close(fd)


def _marker_confirmed(data: bytes) -> bool:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
        return (
            len(data) <= 256
            and isinstance(value, dict)
            and set(value) == {"version", "cleanup_confirmed"}
            and type(value["version"]) is int
            and value["version"] == 1
            and value["cleanup_confirmed"] is True
        )
    except UnicodeError, ValueError, RecursionError:
        return False


def _eligible(directory: int) -> None:
    marker = _read_file(directory, "owner.json", 256)
    if marker is not None and not _marker_confirmed(marker):
        raise BootstrapFailure(BootstrapFailureKind.PREVIOUS_CLEANUP_UNCONFIRMED)
    credential = _read_file(directory, "credential", 65)
    if marker is None and credential is not None:
        raise BootstrapFailure(BootstrapFailureKind.PREVIOUS_CLEANUP_UNCONFIRMED)
    if credential is not None and not re.fullmatch(rb"[0-9a-f]{64}\n", credential):
        raise BootstrapFailure(BootstrapFailureKind.UNSAFE_BOOTSTRAP)


type _FileIdentity = tuple[int, int]


class PrivateBootstrap:
    """One private guard; the launcher must join lifecycle work before release."""

    def __init__(self, directory: int, lock: int) -> None:
        self._directory = directory
        self._lock = lock
        self._marked = False
        self._confirmed = False
        self._published = False
        self._released = False
        self._credential: str | None = None
        self._credential_identity: _FileIdentity | None = None
        self._invalidation_failed = False

    @classmethod
    def acquire(cls, config: ServiceConfig) -> PrivateBootstrap:
        def acquire_guard() -> PrivateBootstrap:
            _check_platform()
            if not isinstance(config, ServiceConfig):
                raise BootstrapFailure(BootstrapFailureKind.INVALID_CONFIGURATION)
            import fcntl

            directory = _open_directory(_account_home())
            lock: int | None = None
            try:
                lock = _open_file(directory, "owner.lock", create=True)
                assert lock is not None
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno in {errno.EACCES, errno.EAGAIN}:
                        raise BootstrapFailure(
                            BootstrapFailureKind.OWNER_ACTIVE
                        ) from None
                    raise
                _eligible(directory)
                return cls(directory, lock)
            except BaseException:
                try:
                    if lock is not None:
                        os.close(lock)
                finally:
                    os.close(directory)
                raise

        return _normalized(acquire_guard)

    @property
    def credential(self) -> str | None:
        return self._credential

    @property
    def unconfirmed_published(self) -> bool:
        """True only after this invocation durably completed false publication."""
        return self._marked

    def _require_open(self) -> None:
        if self._released:
            raise BootstrapFailure(BootstrapFailureKind.INVALID_CONFIGURATION)

    def _publish(
        self, name: str, data: bytes, replaced: Callable[[_FileIdentity], None]
    ) -> None:
        existing = _open_file(self._directory, name)
        if existing is not None:
            os.close(existing)
        temporary = f".bootstrap-{secrets.token_hex(16)}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open(temporary, flags, 0o600, dir_fd=self._directory)
        moved = False
        identity: _FileIdentity | None = None
        try:
            info = _validate_file(fd)
            identity = (info.st_dev, info.st_ino)
            offset = 0
            while offset < len(data):
                written = os.write(fd, data[offset:])
                if written <= 0:
                    raise OSError("publication did not advance")
                offset += written
            os.fsync(fd)
            os.replace(
                temporary,
                name,
                src_dir_fd=self._directory,
                dst_dir_fd=self._directory,
            )
            moved = True
            # Remember ownership even when the following durability step fails.
            replaced((info.st_dev, info.st_ino))
            os.fsync(self._directory)
        finally:
            try:
                os.close(fd)
            finally:
                if not moved and identity is not None:
                    remaining = _open_file(self._directory, temporary)
                    if remaining is not None:
                        try:
                            current = os.fstat(remaining)
                            if (current.st_dev, current.st_ino) != identity:
                                raise BootstrapFailure(
                                    BootstrapFailureKind.BOOTSTRAP_IO_FAILED
                                )
                            os.unlink(temporary, dir_fd=self._directory)
                        finally:
                            os.close(remaining)

    def mark_unconfirmed(self) -> None:
        def mark() -> None:
            self._require_open()
            if self._confirmed:
                raise BootstrapFailure(BootstrapFailureKind.INVALID_CONFIGURATION)
            if not self._marked:
                self._publish(
                    "owner.json",
                    b'{"version":1,"cleanup_confirmed":false}\n',
                    lambda identity: None,
                )
                self._marked = True

        _normalized(mark)

    def publish_credential(self) -> None:
        def publish() -> None:
            self._require_open()
            if not self._marked or self._confirmed or self._published:
                raise BootstrapFailure(BootstrapFailureKind.INVALID_CONFIGURATION)
            token = secrets.token_hex(32)

            def claimed(identity: _FileIdentity) -> None:
                self._credential = token
                self._credential_identity = identity
                self._published = True

            self._publish("credential", token.encode("ascii") + b"\n", claimed)

        _normalized(publish)

    def invalidate_credential(self) -> None:
        if self._invalidation_failed:
            raise BootstrapFailure(BootstrapFailureKind.TEARDOWN_INCOMPLETE)

        def invalidate() -> None:
            self._credential = None
            identity = self._credential_identity
            if identity is None:
                return
            self._require_open()
            fd = _open_file(self._directory, "credential")
            if fd is not None:
                try:
                    info = os.fstat(fd)
                    if (info.st_dev, info.st_ino) != identity:
                        raise BootstrapFailure(BootstrapFailureKind.TEARDOWN_INCOMPLETE)
                    os.unlink("credential", dir_fd=self._directory)
                finally:
                    os.close(fd)
                os.fsync(self._directory)
            self._credential_identity = None

        try:
            _normalized(invalidate, BootstrapFailureKind.TEARDOWN_INCOMPLETE)
        except BootstrapFailure:
            self._invalidation_failed = True
            raise

    def confirm_cleanup(
        self,
        *,
        owner_settled: bool,
        physical_release_confirmed: bool,
        recorder_close_confirmed: bool,
    ) -> None:
        def confirm() -> None:
            self._require_open()
            if (
                not self._marked
                or self._invalidation_failed
                or self._credential_identity is not None
                or any(
                    value is not True
                    for value in (
                        owner_settled,
                        physical_release_confirmed,
                        recorder_close_confirmed,
                    )
                )
            ):
                raise BootstrapFailure(BootstrapFailureKind.TEARDOWN_INCOMPLETE)

            def confirmed(identity: _FileIdentity) -> None:
                self._confirmed = True

            self._publish(
                "owner.json", b'{"version":1,"cleanup_confirmed":true}\n', confirmed
            )

        _normalized(confirm, BootstrapFailureKind.TEARDOWN_INCOMPLETE)

    def release(self) -> None:
        """Release bootstrap only; never attest runtime cleanup or unlink lock."""

        def release_guard() -> None:
            if self._released:
                return
            try:
                self.invalidate_credential()
            finally:
                self._released = True
                self._credential = None
                try:
                    os.close(self._lock)
                finally:
                    os.close(self._directory)

        _normalized(release_guard, BootstrapFailureKind.TEARDOWN_INCOMPLETE)
