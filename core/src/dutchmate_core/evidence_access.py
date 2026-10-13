"""Normalized read capabilities and immutable reports; no resource acquisition."""

from collections.abc import Awaitable, Callable
from dataclasses import FrozenInstanceError, dataclass, field
from typing import TYPE_CHECKING, Final, Literal, Protocol

from dutchmate_core.evidence import (
    EvidencePage,
    EvidenceRetrievalRequest,
    JournalFailure,
)
from dutchmate_core.model import EvidenceReference, SessionId, SessionPolicy

if TYPE_CHECKING:
    from dutchmate_core.runtime import RunId


class EvidenceReadPort(Protocol):
    """Bounded persistence queries without capture or resource-ownership methods."""

    @property
    def session_id(self) -> SessionId: ...

    @property
    def policy(self) -> SessionPolicy: ...

    async def resolve_record(self, reference: EvidenceReference) -> EvidencePage: ...

    async def retrieve(self, request: EvidenceRetrievalRequest) -> EvidencePage: ...


class OwnedEvidenceReadPort(EvidenceReadPort, Protocol):
    """A terminal query's reader, whose request owner must confirm closure."""

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PreparedEvidenceAccess:
    """Composition-supplied capabilities for one immutable session and policy."""

    session_id: SessionId
    policy: SessionPolicy
    live_reader: EvidenceReadPort | None = None
    terminal_opener: Callable[[], Awaitable[OwnedEvidenceReadPort]] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, SessionId):
            raise TypeError("read access session_id must be validated")
        if not isinstance(self.policy, SessionPolicy):
            raise TypeError("read access policy must be validated")
        if self.live_reader is None and self.terminal_opener is None:
            raise ValueError("read access requires at least one capability")
        if self.terminal_opener is not None and not callable(self.terminal_opener):
            raise TypeError("terminal_opener must be callable")
        if self.live_reader is not None:
            if not all(
                callable(getattr(self.live_reader, name, None))
                for name in ("resolve_record", "retrieve")
            ):
                raise TypeError("live_reader must provide the read callables")
            if self.live_reader.session_id != self.session_id:
                raise ValueError("live_reader session_id must match read access")
            if self.live_reader.policy != self.policy:
                raise ValueError("live_reader policy must match read access")


@dataclass(frozen=True, slots=True)
class RunEvidencePage:
    """Unmodified page facts associated with the run pinned by the read owner."""

    run_id: RunId
    session_id: SessionId
    page: EvidencePage

    def __post_init__(self) -> None:
        # RunId remains the existing application value. Defer its import so runtime
        # can consume these read values without a module-initialization cycle.
        from dutchmate_core.runtime import RunId

        if not isinstance(self.run_id, RunId):
            raise TypeError("run_id must be validated")
        if not isinstance(self.session_id, SessionId):
            raise TypeError("session_id must be validated")
        if not isinstance(self.page, EvidencePage):
            raise TypeError("page must be a normalized EvidencePage")


type EvidenceReadRejectedKind = Literal[
    "no_associated_session",
    "session_not_associated",
    "read_unavailable",
    "source_changed",
    "read_capacity",
]

_READ_REJECTED_KINDS = frozenset(
    {
        "no_associated_session",
        "session_not_associated",
        "read_unavailable",
        "source_changed",
        "read_capacity",
    }
)


@dataclass(slots=True, unsafe_hash=True)
class EvidenceReadRejected(RuntimeError):
    """Sealed normalized rejection with ordinary exception transport metadata."""

    kind: Final[EvidenceReadRejectedKind] = field()

    def __setattr__(self, name: str, value: object) -> None:
        if name == "kind" and hasattr(self, name):
            raise FrozenInstanceError("cannot assign to field 'kind'")
        RuntimeError.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name == "kind":
            raise FrozenInstanceError("cannot delete field 'kind'")
        RuntimeError.__delattr__(self, name)

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in _READ_REJECTED_KINDS:
            raise TypeError("evidence read rejection kind must be declared")
        RuntimeError.__init__(self, self.kind)


_SOURCE_OPEN_FACT_FIELDS = frozenset({"primary", "reader_close_confirmed"})


@dataclass(slots=True, unsafe_hash=True)
class EvidenceSourceOpenFailure(RuntimeError):
    """Primary failure and close certainty without a resource handle or detail."""

    primary: Final[JournalFailure | EvidenceReadRejected] = field()
    reader_close_confirmed: Final[bool] = field()

    def __setattr__(self, name: str, value: object) -> None:
        if name in _SOURCE_OPEN_FACT_FIELDS and hasattr(self, name):
            raise FrozenInstanceError(f"cannot assign to field {name!r}")
        RuntimeError.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in _SOURCE_OPEN_FACT_FIELDS:
            raise FrozenInstanceError(f"cannot delete field {name!r}")
        RuntimeError.__delattr__(self, name)

    def __post_init__(self) -> None:
        if not isinstance(self.primary, (JournalFailure, EvidenceReadRejected)):
            raise TypeError("source-open primary must be normalized")
        if type(self.reader_close_confirmed) is not bool:
            raise TypeError("reader_close_confirmed must be boolean")
        RuntimeError.__init__(self, "evidence_source_open_failed")
