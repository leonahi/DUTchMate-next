"""Pure annotation requests, acknowledged facts and preparation capability."""

from collections import deque
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, field
from typing import Final, Literal

from dutchmate_core.evidence import PendingClientAnnotationEvidence
from dutchmate_core.model import (
    SQLITE_INTEGER_MAX,
    ClientAnnotationEvidence,
    EvidenceReference,
    SessionId,
    SessionPolicy,
    validate_annotation_content,
    validate_monitor_uuid,
)
from dutchmate_core.monitor import MonitorClock, MonitorRecordingCoordinator


@dataclass(frozen=True, slots=True)
class AnnotationRequest:
    session_id: SessionId
    text: str
    client_surface: str

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, SessionId):
            raise TypeError("annotation requires a session ID")
        validate_annotation_content(self.text, self.client_surface)


@dataclass(frozen=True, slots=True)
class AnnotationReceipt:
    run_id: str
    session_id: SessionId
    reference: EvidenceReference
    annotation: ClientAnnotationEvidence

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or not self.run_id:
            raise ValueError("annotation receipt requires a run identity")
        if not isinstance(self.session_id, SessionId):
            raise TypeError("annotation receipt requires a session ID")
        if not isinstance(self.reference, EvidenceReference) or not isinstance(
            self.annotation, ClientAnnotationEvidence
        ):
            raise TypeError("annotation receipt requires acknowledged annotation facts")
        if (
            self.reference.session_id != self.session_id
            or self.reference.sequence != self.annotation.sequence
        ):
            raise ValueError(
                "annotation reference must identify the recorded assertion"
            )


type AnnotationRejectedKind = Literal[
    "no_associated_session",
    "session_not_associated",
    "not_active",
    "annotation_unavailable",
    "evidence_policy_incompatible",
    "busy",
    "rate_limited",
]
_REJECTION_KINDS = frozenset(
    {
        "no_associated_session",
        "session_not_associated",
        "not_active",
        "annotation_unavailable",
        "evidence_policy_incompatible",
        "busy",
        "rate_limited",
    }
)


@dataclass(slots=True, unsafe_hash=True)
class AnnotationRejected(RuntimeError):
    """Sealed classification with ordinary mutable exception transport metadata."""

    kind: Final[AnnotationRejectedKind] = field()

    def __setattr__(self, name: str, value: object) -> None:
        if name == "kind" and hasattr(self, name):
            raise FrozenInstanceError("cannot assign to field 'kind'")
        RuntimeError.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name == "kind":
            raise FrozenInstanceError("cannot delete field 'kind'")
        RuntimeError.__delattr__(self, name)

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in _REJECTION_KINDS:
            raise TypeError("annotation rejection kind must be declared")
        RuntimeError.__init__(self, self.kind)


@dataclass(frozen=True, slots=True)
class PreparedAnnotationAccess:
    session_id: SessionId
    policy: SessionPolicy
    coordinator: MonitorRecordingCoordinator
    clock: MonitorClock
    charge_annotation: Callable[[PendingClientAnnotationEvidence], int]

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, SessionId) or not isinstance(
            self.policy, SessionPolicy
        ):
            raise TypeError("annotation access requires validated session and policy")
        if not isinstance(self.coordinator, MonitorRecordingCoordinator):
            raise TypeError("annotation access requires the committed coordinator")
        if (
            self.session_id != self.coordinator.session_id
            or self.policy != self.coordinator.policy
        ):
            raise ValueError("annotation access must identify the transferred recorder")
        if self.clock is not self.coordinator.clock or not callable(
            self.charge_annotation
        ):
            raise ValueError(
                "annotation access requires the same clock and charge callback"
            )


def _preflight_annotation(
    access: PreparedAnnotationAccess, request: AnnotationRequest, origin_id: str
) -> None:
    """Check conservative codec charge without sampling time or reserving space."""
    try:
        maximum = PendingClientAnnotationEvidence(
            request.text, request.client_surface, origin_id, SQLITE_INTEGER_MAX
        )
        charge = access.charge_annotation(maximum)
        if type(charge) is not int or not 0 < charge <= SQLITE_INTEGER_MAX:
            raise ValueError("invalid annotation charge")
    except Exception:
        raise AnnotationRejected("annotation_unavailable") from None
    policy = access.policy
    if charge > min(
        policy.max_record_charged_bytes,
        policy.max_retained_charged_bytes,
        policy.max_retrieval_page_charged_bytes,
    ):
        raise AnnotationRejected("evidence_policy_incompatible")


class _AnnotationBudget:
    """Incarnation accounting: at most ten admissions plus last check and origin."""

    def __init__(self) -> None:
        self._samples: deque[int] = deque()
        self._last_check: int | None = None
        self._origin_id: str | None = None

    def check_origin(self, origin_id: str) -> None:
        validate_monitor_uuid(origin_id)
        if self._origin_id is not None and origin_id != self._origin_id:
            raise ValueError("annotation clock origin changed")

    def admit(self, clock: MonitorClock, origin_id: str) -> None:
        try:
            now = clock.now_ns()
            if (
                type(now) is not int
                or not 0 <= now <= SQLITE_INTEGER_MAX
                or (self._last_check is not None and now < self._last_check)
            ):
                raise ValueError("invalid annotation admission time")
        except Exception:
            raise AnnotationRejected("annotation_unavailable") from None
        self._last_check = now
        while self._samples and self._samples[0] <= now - 1_000_000_000:
            self._samples.popleft()
        if len(self._samples) == 10:
            raise AnnotationRejected("rate_limited")
        self._origin_id = origin_id
        self._samples.append(now)
