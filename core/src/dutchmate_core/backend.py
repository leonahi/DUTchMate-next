"""Backend-neutral ownership boundary for normalized observations."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from dutchmate_core.model import BackendEvent, ConnectionDescriptor


class EventStreamAlreadyConsumedError(RuntimeError):
    """Raised when a connection's one authoritative stream is claimed twice."""


class BackendFailureOperation(StrEnum):
    """Backend operation that failed at the normalized boundary."""

    OPEN = "open"
    READ = "read"
    CLOSE = "close"


class BackendFailureKind(StrEnum):
    """Stable backend-neutral failure category."""

    INVALID_REQUEST = "invalid_request"
    DEVICE_NOT_FOUND = "device_not_found"
    PERMISSION_DENIED = "permission_denied"
    DEVICE_BUSY = "device_busy"
    CONFIGURATION_REJECTED = "configuration_rejected"
    LINE_STATE_SETUP_FAILED = "line_state_setup_failed"
    IO_FAILURE = "io_failure"
    INTERNAL_CONTRACT_FAILURE = "internal_contract_failure"


@dataclass(frozen=True, slots=True)
class NormalizedBackendFailure(RuntimeError):
    """Backend failure without adapter-library objects or platform handles."""

    operation: BackendFailureOperation
    kind: BackendFailureKind
    detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation, BackendFailureOperation):
            raise TypeError("backend failure operation must be declared")
        if not isinstance(self.kind, BackendFailureKind):
            raise TypeError("backend failure kind must be declared")
        if self.detail is not None and not isinstance(self.detail, str):
            raise TypeError("backend failure detail must be text or absent")
        message = f"{self.operation.value}/{self.kind.value}"
        if self.detail:
            message = f"{message}: {self.detail}"
        RuntimeError.__init__(self, message)


class BackendConnection(Protocol):
    """One owned connection with exactly one normalized event consumer."""

    @property
    def descriptor(self) -> ConnectionDescriptor: ...

    def events(self) -> AsyncIterator[BackendEvent]: ...

    async def close(self) -> None: ...


class Backend(Protocol):
    """External boundary that opens one owned backend connection."""

    async def open(self) -> BackendConnection: ...
