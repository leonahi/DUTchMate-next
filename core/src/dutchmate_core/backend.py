"""Backend-neutral ownership boundary for normalized observations."""

from collections.abc import AsyncIterator
from typing import Protocol

from dutchmate_core.model import BackendEvent, ConnectionDescriptor


class EventStreamAlreadyConsumedError(RuntimeError):
    """Raised when a connection's one authoritative stream is claimed twice."""


class BackendConnection(Protocol):
    """One owned connection with exactly one normalized event consumer."""

    @property
    def descriptor(self) -> ConnectionDescriptor: ...

    def events(self) -> AsyncIterator[BackendEvent]: ...

    async def close(self) -> None: ...


class Backend(Protocol):
    """External boundary that opens one owned backend connection."""

    async def open(self) -> BackendConnection: ...
