"""Observation-run values, preparation boundary, and generation ownership."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import FrozenInstanceError, dataclass, field, replace
from enum import StrEnum
from threading import get_ident
from typing import Literal, Protocol
from uuid import uuid4

from dutchmate_core.acquisition import (
    Acquisition,
    AcquisitionFailureKind,
    AcquisitionSnapshot,
    AcquisitionState,
    AcquisitionTerminalTrigger,
)
from dutchmate_core.annotation import (
    AnnotationReceipt,
    AnnotationRejected,
    AnnotationRequest,
    PreparedAnnotationAccess,
    _AnnotationBudget,
    _preflight_annotation,
)
from dutchmate_core.backend import Backend, BackendFailureKind
from dutchmate_core.evidence import (
    EvidencePage,
    EvidenceRecorder,
    EvidenceRetrievalRequest,
    JournalFailure,
    JournalFailureKind,
)
from dutchmate_core.evidence_access import (
    EvidenceReadPort,
    EvidenceReadRejected,
    EvidenceSourceOpenFailure,
    OwnedEvidenceReadPort,
    PreparedEvidenceAccess,
    RunEvidencePage,
)
from dutchmate_core.follow import (
    FollowBatch,
    FollowEnd,
    FollowEndReason,
    FollowRejected,
    FollowRequest,
    FollowStart,
    _follow_head_request,
    _FollowSubscription,
)
from dutchmate_core.model import (
    BackendCapability,
    EvidenceReference,
    MonitorOutcome,
    SegmentProvenance,
    SessionId,
    SessionPolicy,
)
from dutchmate_core.monitor import (
    MonitorRecordingCoordinator,
    MonitorRejected,
    MonitorReport,
    MonitorRequest,
    PreparedMonitorAccess,
)
from dutchmate_core.profile import ProfileFailureKind, ResolvedDutProfile


@dataclass(frozen=True, slots=True)
class RunId:
    """Fresh opaque identity, distinct from durable session/segment identities."""

    value: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("run ID must be non-empty text")


class RuntimeState(StrEnum):
    INACTIVE = "inactive"
    ATTACHING = "attaching"
    ACTIVE = "active"
    DETACHING = "detaching"
    TERMINATED = "terminated"
    FAILED = "failed"


class RuntimeStopIntent(StrEnum):
    NONE = "none"
    DETACH = "detach"
    ATTACH_CANCELLED = "attach_cancelled"


class RuntimeTerminalReason(StrEnum):
    DETACHED = "detached"
    ATTACH_CANCELLED = "attach_cancelled"
    DISCONNECTED = "disconnected"
    STARTUP_FAILURE = "startup_failure"
    ACQUISITION_FAILURE = "acquisition_failure"
    CLEANUP_FAILURE = "cleanup_failure"


class RuntimeIssueSource(StrEnum):
    PREPARATION = "preparation"
    ACQUISITION_START = "acquisition_start"
    ACQUISITION = "acquisition"
    BACKEND_CLOSE = "backend_close"
    RECORDER_CLOSE = "recorder_close"
    INTERNAL_CONTRACT = "internal_contract"


type RuntimeIssueCode = (
    AcquisitionFailureKind
    | BackendFailureKind
    | JournalFailureKind
    | ProfileFailureKind
    | Literal["close_failed", "internal_contract_failure"]
)


@dataclass(frozen=True, slots=True)
class RuntimeIssue:
    """Bounded normalized fact without exception text or raw context."""

    source: RuntimeIssueSource
    code: RuntimeIssueCode

    def __post_init__(self) -> None:
        if not isinstance(self.source, RuntimeIssueSource):
            raise TypeError("runtime issue source must be declared")
        if not isinstance(
            self.code,
            (
                AcquisitionFailureKind,
                BackendFailureKind,
                JournalFailureKind,
                ProfileFailureKind,
            ),
        ) and not (
            type(self.code) is str
            and self.code in {"close_failed", "internal_contract_failure"}
        ):
            raise TypeError("runtime issue code must be normalized")


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    """One current or historical summary; eligibility follows ownership facts."""

    state: RuntimeState = RuntimeState.INACTIVE
    run_id: RunId | None = None
    profile: ResolvedDutProfile | None = None
    session_id: SessionId | None = None
    acquisition: AcquisitionSnapshot | None = None
    stop_intent: RuntimeStopIntent = RuntimeStopIntent.NONE
    terminal_reason: RuntimeTerminalReason | None = None
    primary_issue: RuntimeIssue | None = None
    cleanup_issues: tuple[RuntimeIssue, ...] = ()
    owner_settled: bool = True
    physical_release_confirmed: bool = True
    recorder_close_confirmed: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.state, RuntimeState):
            raise TypeError("runtime state must be declared")
        if not isinstance(self.stop_intent, RuntimeStopIntent):
            raise TypeError("runtime stop intent must be declared")
        for name, expected_type in (
            ("run_id", RunId),
            ("profile", ResolvedDutProfile),
            ("session_id", SessionId),
            ("acquisition", AcquisitionSnapshot),
            ("terminal_reason", RuntimeTerminalReason),
            ("primary_issue", RuntimeIssue),
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, expected_type):
                raise TypeError(f"{name} must be a validated immutable value")
        for name in (
            "owner_settled",
            "physical_release_confirmed",
            "recorder_close_confirmed",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be boolean")
        _validate_cleanup_issues(self.cleanup_issues)

        terminal = self.state in {RuntimeState.TERMINATED, RuntimeState.FAILED}
        if self.state is RuntimeState.INACTIVE:
            if (
                any(
                    value is not None
                    for value in (
                        self.run_id,
                        self.profile,
                        self.session_id,
                        self.acquisition,
                        self.terminal_reason,
                        self.primary_issue,
                    )
                )
                or self.cleanup_issues
                or self.stop_intent is not RuntimeStopIntent.NONE
            ):
                raise ValueError("inactive status cannot contain a run")
            if not (
                self.owner_settled
                and self.physical_release_confirmed
                and self.recorder_close_confirmed
            ):
                raise ValueError("inactive ownership and cleanup must be confirmed")
        else:
            if self.run_id is None or self.profile is None:
                raise ValueError("admitted status requires run ID and Profile")
            if self.owner_settled is not terminal:
                raise ValueError("owner settlement must agree with lifecycle state")
            if (self.terminal_reason is not None) is not terminal:
                raise ValueError("terminal reason requires terminal settlement")
        issues = self.primary_issue is not None or bool(self.cleanup_issues)
        if self.state is RuntimeState.TERMINATED and issues:
            raise ValueError("terminal issues require failed state")
        if self.state is RuntimeState.FAILED and not issues:
            raise ValueError("failed state requires a normalized issue")
        if self.acquisition is not None:
            if self.owner_settled and self.acquisition.state in {
                AcquisitionState.STARTING,
                AcquisitionState.ACQUIRING,
                AcquisitionState.STOPPING,
            }:
                raise ValueError("settled owner cannot contain live acquisition")
            if (
                self.physical_release_confirmed
                is not self.acquisition.physical_release_confirmed
            ):
                raise ValueError("release certainty must match Acquisition snapshot")
        for issue in self.cleanup_issues:
            if (
                issue.source is RuntimeIssueSource.BACKEND_CLOSE
                and self.physical_release_confirmed
            ):
                raise ValueError("failed backend close cannot confirm release")
            if (
                issue.source is RuntimeIssueSource.RECORDER_CLOSE
                and self.recorder_close_confirmed
            ):
                raise ValueError("failed recorder close cannot confirm closure")

    @property
    def attach_admissible(self) -> bool:
        return (
            self.state
            in {RuntimeState.INACTIVE, RuntimeState.TERMINATED, RuntimeState.FAILED}
            and self.owner_settled
            and self.physical_release_confirmed
            and self.recorder_close_confirmed
        )


def _validate_cleanup_issues(issues: tuple[RuntimeIssue, ...]) -> None:
    if not isinstance(issues, tuple) or any(
        not isinstance(issue, RuntimeIssue) for issue in issues
    ):
        raise TypeError("cleanup issues must be an immutable tuple of RuntimeIssue")
    order = {
        RuntimeIssueSource.ACQUISITION: 0,
        RuntimeIssueSource.BACKEND_CLOSE: 0,
        RuntimeIssueSource.RECORDER_CLOSE: 1,
    }
    if len(issues) > 2:
        raise ValueError("at most two cleanup issues are retained")
    prior = -1
    for issue in issues:
        position = order.get(issue.source, -1)
        if position <= prior:
            raise ValueError("cleanup issues must be unique and in resource order")
        prior = position


class RuntimeRejectedKind(StrEnum):
    INVALID_REQUEST = "invalid_request"
    BUSY = "busy"
    CLEANUP_UNCONFIRMED = "cleanup_unconfirmed"
    WRONG_EXECUTION_CONTEXT = "wrong_execution_context"


class RuntimeRejectedError(RuntimeError):
    """Read-only rejection category with normal exception transport fields."""

    def __init__(self, kind: RuntimeRejectedKind) -> None:
        if not isinstance(kind, RuntimeRejectedKind):
            raise TypeError("runtime rejection kind must be declared")
        self._kind = kind
        super().__init__(kind.value)

    @property
    def kind(self) -> RuntimeRejectedKind:
        return self._kind


_PREPARATION_FACT_FIELDS = frozenset(
    {
        "primary_issue",
        "session_id",
        "recorder_close_confirmed",
        "cleanup_issue",
        "terminal_evidence_access",
    }
)


@dataclass(slots=True, unsafe_hash=True)
class PreparationFailure(RuntimeError):
    """Read-only preparation facts with normal RuntimeError transport fields."""

    primary_issue: RuntimeIssue
    session_id: SessionId | None = None
    recorder_close_confirmed: bool = False
    cleanup_issue: RuntimeIssue | None = None
    terminal_evidence_access: PreparedEvidenceAccess | None = None

    def __setattr__(self, name: str, value: object) -> None:
        # Keep the normalized dataclass facts immutable (including their hash),
        # while allowing standard traceback/cause/context transport to work.
        if name in _PREPARATION_FACT_FIELDS and hasattr(self, name):
            raise FrozenInstanceError(f"cannot assign to field {name!r}")
        RuntimeError.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in _PREPARATION_FACT_FIELDS:
            raise FrozenInstanceError(f"cannot delete field {name!r}")
        RuntimeError.__delattr__(self, name)

    def __post_init__(self) -> None:
        if not isinstance(self.primary_issue, RuntimeIssue):
            raise TypeError("preparation primary issue must be normalized")
        if self.session_id is not None and not isinstance(self.session_id, SessionId):
            raise TypeError("preparation session ID must be validated")
        if type(self.recorder_close_confirmed) is not bool:
            raise TypeError("recorder closure certainty must be boolean")
        if self.cleanup_issue is not None:
            if not isinstance(self.cleanup_issue, RuntimeIssue):
                raise TypeError("recorder cleanup issue must be normalized")
            if self.cleanup_issue.source is not RuntimeIssueSource.RECORDER_CLOSE:
                raise ValueError("preparation cleanup issue must describe recorder")
            if self.recorder_close_confirmed:
                raise ValueError("failed recorder close cannot confirm closure")
        access = self.terminal_evidence_access
        if access is not None and (
            not isinstance(access, PreparedEvidenceAccess)
            or access.session_id != self.session_id
            or access.live_reader is not None
            or access.terminal_opener is None
        ):
            raise ValueError("preparation terminal access must match the known session")
        RuntimeError.__init__(self, "preparation_failed")


class ObservationRecorder(EvidenceRecorder, Protocol):
    """Only existing append and immutable identity/policy plus async close."""

    @property
    def session_id(self) -> SessionId: ...

    @property
    def policy(self) -> SessionPolicy: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PreparedFollowAccess:
    """Follow uses the transferred coordinator and its existing live journal."""

    session_id: SessionId
    policy: SessionPolicy
    coordinator: MonitorRecordingCoordinator
    live_reader: EvidenceReadPort

    def __post_init__(self) -> None:
        FollowRequest(self.session_id)
        if (
            not isinstance(self.policy, SessionPolicy)
            or not isinstance(self.coordinator, MonitorRecordingCoordinator)
            or self.coordinator.session_id != self.session_id
            or self.coordinator.policy != self.policy
            or self.live_reader.session_id != self.session_id
            or self.live_reader.policy != self.policy
            or not callable(self.live_reader.retrieve)
            or not callable(self.live_reader.resolve_record)
        ):
            raise ValueError("invalid Follow preparation")


@dataclass(frozen=True, slots=True)
class PreparedObservationRun:
    """One recorder and unopened backend; receiver checks Profile policy by value."""

    recorder: ObservationRecorder
    backend: Backend
    evidence_access: PreparedEvidenceAccess | None = None
    monitor_access: PreparedMonitorAccess | None = None
    annotation_access: PreparedAnnotationAccess | None = None
    follow_access: PreparedFollowAccess | None = None


def _prepared_values(candidate: object) -> tuple[SessionId, SessionPolicy] | None:
    """Validate the transferred lifecycle subset without opening any resource."""
    if not isinstance(candidate, PreparedObservationRun):
        return None
    try:
        session_id = candidate.recorder.session_id
        policy = candidate.recorder.policy
        if (
            isinstance(session_id, SessionId)
            and isinstance(policy, SessionPolicy)
            and callable(candidate.recorder.append)
            and callable(candidate.recorder.close)
            and callable(candidate.backend.open)
        ):
            return session_id, policy
    except Exception:
        pass
    return None


type PrepareObservationRun = Callable[
    [ResolvedDutProfile], Awaitable[PreparedObservationRun]
]


def _read_access_matches(
    access: PreparedEvidenceAccess | None, session_id: SessionId, policy: SessionPolicy
) -> bool:
    if access is None:
        return True
    if not isinstance(access, PreparedEvidenceAccess):
        return False
    if access.session_id != session_id or access.policy != policy:
        return False
    try:
        # Revalidate the live port's current facts/callables at transfer. The
        # immutable access value can reference a mutable infrastructure adapter.
        replace(access)
    except Exception:
        return False
    return True


def _monitor_access_matches(
    access: PreparedMonitorAccess | None,
    recorder: ObservationRecorder,
    session_id: SessionId,
    policy: SessionPolicy,
) -> bool:
    if access is None:
        return True
    if not isinstance(access, PreparedMonitorAccess):
        return False
    if (
        access.session_id != session_id
        or access.policy != policy
        or access.coordinator is not recorder
    ):
        return False
    try:
        # Revalidate mutable recorder/clock facts at ownership transfer, just
        # as for prepared evidence access. Invalid provided support is not absent.
        replace(access)
    except Exception:
        return False
    return True


def _annotation_access_matches(
    access: PreparedAnnotationAccess | None,
    recorder: ObservationRecorder,
    session_id: SessionId,
    policy: SessionPolicy,
) -> bool:
    if access is None:
        return True
    if not isinstance(access, PreparedAnnotationAccess):
        return False
    try:
        replace(access)
        return (
            access.coordinator is recorder
            and access.session_id == session_id
            and access.policy == policy
        )
    except Exception:
        return False


def _follow_access_matches(
    access: PreparedFollowAccess | None,
    recorder: ObservationRecorder,
    read_access: PreparedEvidenceAccess | None,
    session_id: SessionId,
    policy: SessionPolicy,
) -> bool:
    if access is None:
        return True
    if not isinstance(access, PreparedFollowAccess):
        return False
    try:
        replace(access)
        return (
            access.coordinator is recorder
            and read_access is not None
            and access.live_reader is read_access.live_reader
            and access.session_id == session_id
            and access.policy == policy
        )
    except Exception:
        return False


@dataclass(slots=True)
class _EvidenceAssociation:
    run_id: RunId
    session_id: SessionId | None = None
    policy: SessionPolicy | None = None
    live_reader: EvidenceReadPort | None = None
    terminal_opener: Callable[[], Awaitable[OwnedEvidenceReadPort]] | None = None
    live_reads_open: bool = False
    terminal_reads_open: bool = False
    reads: set[asyncio.Task[RunEvidencePage]] = field(default_factory=set)


@dataclass(slots=True)
class _MonitorRun:
    access: PreparedMonitorAccess
    request: MonitorRequest
    provenance: SegmentProvenance
    operation_id: str
    intent: MonitorOutcome | None = None
    owner: asyncio.Task[MonitorReport] | None = None


@dataclass(slots=True)
class _AnnotationRun:
    access: PreparedAnnotationAccess
    request: AnnotationRequest
    owner: asyncio.Task[AnnotationReceipt] | None = None


@dataclass(slots=True)
class _ObservationGeneration:
    ready: asyncio.Future[RuntimeStatus]
    evidence: _EvidenceAssociation
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    acquisition: Acquisition | None = None
    owner: asyncio.Task[RuntimeStatus] | None = None
    startup_succeeded: bool = False
    startup_failed: bool = False
    monitor_access: PreparedMonitorAccess | None = None
    monitor_sealed: bool = False
    monitor: _MonitorRun | None = None
    annotation_access: PreparedAnnotationAccess | None = None
    annotation_sealed: bool = False
    annotation: _AnnotationRun | None = None
    follow_access: PreparedFollowAccess | None = None
    follow_sealed: bool = False
    follow: FollowSubscription | None = None
    follow_start: asyncio.Task[FollowSubscription] | None = None


class _FollowSealed(Exception):
    """An internal wake/settlement signal; never a public rejection category."""


@dataclass(frozen=True, slots=True)
class _FollowQueries:
    """Bridge the coordinator's reader callback to captured runtime read leases."""

    session_id: SessionId
    policy: SessionPolicy
    retrieve: Callable[[EvidenceRetrievalRequest], Awaitable[EvidencePage]]


async def _wait_follow_owner[T](owner: asyncio.Task[T]) -> T:
    """Join strongly owned Follow admission/cleanup despite waiter cancellation."""
    try:
        return await asyncio.shield(owner)
    except asyncio.CancelledError:
        while not owner.done():
            try:
                await asyncio.shield(owner)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not owner.cancelled():
            owner.exception()
        raise


def _follow_owner_settled[T](owner: asyncio.Task[T]) -> None:
    if not owner.cancelled():
        owner.exception()


class FollowSubscription:
    """Generation-bound subscriber; only submitted queries hold read leases.

    The coordinator registration owns the existing bounded state and wake signal.
    This runtime owner supplies context guards, captured read ownership and seals.
    """

    def __init__(
        self,
        runtime: ObservationRuntime,
        generation: _ObservationGeneration,
        access: PreparedFollowAccess,
    ) -> None:
        self._runtime = runtime
        self._generation: _ObservationGeneration | None = generation
        self._access: PreparedFollowAccess | None = access
        self._registration: _FollowSubscription | None = None
        self._start: FollowStart | None = None
        self._end: FollowEnd | None = None
        self._sealed = False
        self._closed = False
        self._pull_settled: asyncio.Future[None] | None = None
        self._close_owner: asyncio.Task[None] | None = None

    @property
    def start(self) -> FollowStart:
        assert self._start is not None
        return self._start

    async def _retrieve(self, request: EvidenceRetrievalRequest) -> EvidencePage:
        if self._sealed or self._closed:
            raise _FollowSealed
        assert self._generation is not None and self._access is not None
        page = await self._runtime._follow_query(
            self._generation, self._access, request
        )
        # A submitted query must settle before a seal is observed. Its payload
        # may be discarded; never submit the next payload query after sealing.
        if self._sealed or self._closed:
            raise _FollowSealed
        return page

    def _seal(self, reason: FollowEndReason, cutoff: int | None = None) -> None:
        self._sealed = True
        if self._registration is not None:
            self._registration._state.seal(reason, cutoff)
            self._registration.notify()

    def _take_end(self) -> FollowEnd:
        if self._end is None and self._registration is not None:
            self._end = self._registration._state.end()
        if self._end is None:
            raise FollowRejected("not_active")
        return self._end

    async def pull(self) -> FollowBatch | FollowEnd:
        self._runtime._guard_context()
        if self._pull_settled is not None:
            raise FollowRejected("busy")
        if self._end is not None:
            return self._end
        if self._closed:
            raise FollowRejected("not_active")
        assert self._registration is not None
        settled = self._runtime._loop.create_future()
        self._pull_settled = settled
        cancelled = False
        try:
            result = await self._registration.pull()
            if self._sealed:
                return self._take_end()
            if isinstance(result, FollowEnd):
                self._end = result
            return result
        except asyncio.CancelledError:
            cancelled = True
            raise
        except _FollowSealed:
            return self._take_end()
        except FollowRejected as failure:
            if self._sealed or self._end is not None:
                return self._take_end()
            if failure.kind == "busy":
                raise
            self._seal(
                "read_capacity" if failure.kind == "read_capacity" else "source_failed"
            )
            return self._take_end()
        except Exception:
            self._seal("source_failed")
            return self._take_end()
        finally:
            self._pull_settled = None
            settled.set_result(None)
            if cancelled or self._end is not None:
                await self.close()

    async def close(self) -> None:
        self._runtime._guard_context()
        if self._close_owner is None:
            self._closed = True
            if self._registration is not None:
                self._registration.notify()
            self._close_owner = asyncio.create_task(self._own_close())
            self._close_owner.add_done_callback(_follow_owner_settled)
        await _wait_follow_owner(self._close_owner)

    async def _own_close(self) -> None:
        pending = self._pull_settled
        if pending is not None:
            await asyncio.shield(pending)
        await self._release()

    async def _release(self) -> None:
        """Release source references without waiting for an idle public pull."""
        self._closed = True
        registration, self._registration = self._registration, None
        if registration is not None:
            # End facts survive unregister/close, which discards live state.
            if self._sealed and self._end is None:
                self._end = registration._state.end()
            await registration.close()
        generation, self._generation = self._generation, None
        if generation is not None and generation.follow is self:
            generation.follow = None
        self._access = None


def _running_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        return loop
    raise RuntimeRejectedError(RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT)


class ObservationRuntime:
    """Own admitted startup and cancellation-resistant stop on one loop/thread.

    Only normalized acquisition and recorder contracts enter this application
    boundary. Stop and autonomous termination converge on the same owner,
    joining Acquisition before recorder close and terminal publication.
    """

    def __init__(self) -> None:
        self._loop = _running_loop()
        self._thread_id = get_ident()
        self._lock = asyncio.Lock()
        self._summary = RuntimeStatus()
        self._generation: _ObservationGeneration | None = None
        self._evidence_association: _EvidenceAssociation | None = None
        self._reads: set[asyncio.Task[RunEvidencePage]] = set()
        self._evidence_read_cleanup_confirmed = True
        self._monitors_sealed = False
        self._annotations_sealed = False
        self._follows_sealed = False
        self._annotation_budget = _AnnotationBudget()

    @property
    def evidence_read_cleanup_confirmed(self) -> bool:
        """Incarnation-wide read certainty, independent of capture/attach facts."""
        self._guard_context()
        return self._evidence_read_cleanup_confirmed

    def _guard_context(self) -> None:
        if _running_loop() is not self._loop or get_ident() != self._thread_id:
            raise RuntimeRejectedError(RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT)

    def status(self) -> RuntimeStatus:
        """Read current immutable facts without mutation, locking, or scheduling."""
        self._guard_context()
        generation = self._generation
        if generation is None or generation.acquisition is None:
            return self._summary
        snapshot = generation.acquisition.snapshot()
        primary = self._summary.primary_issue
        if primary is None and snapshot.primary_failure_kind is not None:
            primary = RuntimeIssue(
                RuntimeIssueSource.ACQUISITION
                if generation.startup_succeeded
                else RuntimeIssueSource.ACQUISITION_START,
                snapshot.primary_failure_kind,
            )
        acquisition_cleanup = next(
            (
                issue
                for issue in self._summary.cleanup_issues
                if issue.source is not RuntimeIssueSource.RECORDER_CLOSE
            ),
            None,
        )
        if snapshot.close_failed:
            acquisition_cleanup = RuntimeIssue(
                RuntimeIssueSource.BACKEND_CLOSE, "close_failed"
            )
        recorder_cleanup = tuple(
            issue
            for issue in self._summary.cleanup_issues
            if issue.source is RuntimeIssueSource.RECORDER_CLOSE
        )
        return replace(
            self._summary,
            acquisition=snapshot,
            physical_release_confirmed=snapshot.physical_release_confirmed,
            primary_issue=primary,
            cleanup_issues=((acquisition_cleanup,) if acquisition_cleanup else ())
            + recorder_cleanup,
        )

    def _follow_access(
        self, generation: _ObservationGeneration
    ) -> PreparedFollowAccess:
        access = generation.follow_access
        association = generation.evidence
        if not isinstance(access, PreparedFollowAccess):
            raise FollowRejected("follow_unavailable")
        try:
            replace(access)
            if (
                not self._evidence_read_cleanup_confirmed
                or not association.live_reads_open
                or access.live_reader is not association.live_reader
                or access.session_id != association.session_id
                or access.policy != association.policy
                or access.coordinator.current_provenance is None
            ):
                raise ValueError("unusable Follow access")
        except Exception:
            raise FollowRejected("follow_unavailable") from None
        return access

    async def start_follow(self, request: FollowRequest) -> FollowSubscription:
        self._guard_context()
        if not isinstance(request, FollowRequest):
            raise RuntimeRejectedError(RuntimeRejectedKind.INVALID_REQUEST)
        try:
            replace(request)
        except Exception:
            raise RuntimeRejectedError(RuntimeRejectedKind.INVALID_REQUEST) from None
        if self._follows_sealed:
            raise FollowRejected("not_active")
        association = self._evidence_association
        if association is None or association.session_id is None:
            raise FollowRejected("no_associated_session")
        if request.session_id != association.session_id:
            raise FollowRejected("session_not_associated")
        generation = self._generation
        if (
            generation is None
            or self._summary.state is not RuntimeState.ACTIVE
            or generation.follow_sealed
        ):
            raise FollowRejected("not_active")
        access = self._follow_access(generation)
        if generation.follow is not None:
            raise FollowRejected("busy")
        if len(self._reads) >= 8:
            raise FollowRejected("read_capacity")
        # No await before this generation, slot and strong admission owner bind.
        subscription = FollowSubscription(self, generation, access)
        generation.follow = subscription
        owner = asyncio.create_task(
            self._own_follow(generation, subscription, access, request)
        )
        generation.follow_start = owner
        owner.add_done_callback(_follow_owner_settled)
        try:
            return await _wait_follow_owner(owner)
        except asyncio.CancelledError:
            # A late result belongs to this captured registration, never a later
            # run. Joining the submitted head precedes slot release/unregister.
            await subscription.close()
            raise

    async def _own_follow(
        self,
        generation: _ObservationGeneration,
        subscription: FollowSubscription,
        access: PreparedFollowAccess,
        request: FollowRequest,
    ) -> FollowSubscription:
        def revalidate() -> None:
            self._guard_context()
            if (
                self._follows_sealed
                or self._generation is not generation
                or generation.follow_sealed
                or self._summary.state is not RuntimeState.ACTIVE
            ):
                raise FollowRejected("not_active")
            if self._follow_access(generation) is not access:
                raise FollowRejected("follow_unavailable")

        try:
            subscription._registration = await access.coordinator.start_follow(
                request,
                run_id=generation.evidence.run_id.value,
                reader=_FollowQueries(
                    access.session_id, access.policy, subscription._retrieve
                ),
                revalidate=revalidate,
            )
            subscription._start = subscription._registration.start
            return subscription
        except BaseException as failure:
            await subscription._release()
            if isinstance(failure, _FollowSealed):
                raise FollowRejected("not_active") from None
            raise
        finally:
            generation.follow_start = None

    async def _follow_query(
        self,
        generation: _ObservationGeneration,
        access: PreparedFollowAccess,
        query: EvidenceRetrievalRequest,
        *,
        final: bool = False,
    ) -> EvidencePage:
        if not final and (
            self._generation is not generation
            or generation.follow_sealed
            or self._follows_sealed
        ):
            raise _FollowSealed
        association = generation.evidence
        if not association.live_reads_open or not self._evidence_read_cleanup_confirmed:
            raise FollowRejected("follow_unavailable")
        if len(self._reads) >= 8:
            raise FollowRejected("read_capacity")
        owner = self._submit_read(association, access.live_reader, None, query)
        return (await self._wait_read(owner)).page

    def _seal_follow(
        self, generation: _ObservationGeneration, reason: FollowEndReason
    ) -> None:
        generation.follow_sealed = True
        if generation.follow is not None:
            generation.follow._seal(reason)

    def _seal_follows(self) -> None:
        """Synchronous service-stop latch, callable before HTTP drain/detach."""
        self._guard_context()
        self._follows_sealed = True
        if self._generation is not None:
            self._seal_follow(self._generation, "service_stopping")

    async def _final_follow_head(self, generation: _ObservationGeneration) -> None:
        # Join admission, not an idle subscriber or its delivery task. The source
        # is now final: acquisition/Monitor/annotation owners have all settled.
        if generation.follow_start is not None:
            await asyncio.gather(
                asyncio.shield(generation.follow_start), return_exceptions=True
            )
        subscription = generation.follow
        if subscription is not None and not subscription._closed:
            access = subscription._access
            assert access is not None
            try:
                page = await self._follow_query(
                    generation,
                    access,
                    _follow_head_request(access.session_id, access.policy),
                    final=True,
                )
            except Exception:
                pass  # Unknown cutoff; never change008 read/release certainty.
            else:
                subscription._seal("source_ended", page.snapshot_end_exclusive)
        generation.follow_access = None

    def _monitor_access(
        self, generation: _ObservationGeneration
    ) -> PreparedMonitorAccess:
        access = generation.monitor_access
        if not isinstance(access, PreparedMonitorAccess):
            raise MonitorRejected("monitor_unavailable")
        try:
            replace(access)  # Recheck current infrastructure identity and callables.
            if (
                access.session_id != generation.evidence.session_id
                or access.policy != generation.evidence.policy
            ):
                raise ValueError("Monitor access no longer matches the run")
        except Exception:
            raise MonitorRejected("monitor_unavailable") from None
        return access

    async def monitor(self, request: MonitorRequest) -> MonitorReport:
        self._guard_context()
        if not isinstance(request, MonitorRequest):
            raise RuntimeRejectedError(RuntimeRejectedKind.INVALID_REQUEST)
        if self._monitors_sealed:
            raise MonitorRejected("monitor_unavailable")
        association = self._evidence_association
        if association is None or association.session_id is None:
            raise MonitorRejected("no_associated_session")
        if request.session_id != association.session_id:
            raise MonitorRejected("session_not_associated")
        generation = self._generation
        if (
            generation is None
            or self._summary.state is not RuntimeState.ACTIVE
            or generation.monitor_sealed
        ):
            raise MonitorRejected("not_active")
        access = self._monitor_access(generation)
        provenance = access.coordinator.current_provenance
        if provenance is None:
            raise MonitorRejected("monitor_unavailable")
        if not provenance.capabilities.supports(BackendCapability.UART_RECEIVE):
            raise MonitorRejected("capability_unavailable")
        draft = access.coordinator.preflight(request, provenance, access.charge_markers)
        if generation.monitor is not None:
            raise MonitorRejected("busy")
        # Selection and registration are synchronous before the first await.
        pending = _MonitorRun(access, request, provenance, draft.operation_id)
        generation.monitor = pending
        owner = asyncio.create_task(
            self._own_monitor(generation, pending),
            name=f"dutchmate-monitor-{association.run_id.value}",
        )
        pending.owner = owner
        owner.add_done_callback(self._monitor_settled)
        try:
            return await asyncio.shield(owner)
        except asyncio.CancelledError:
            # Delivery loss never stops capture or cancels a submitted marker.
            while not owner.done():
                try:
                    await asyncio.shield(owner)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not owner.cancelled():
                owner.exception()
            raise

    def _monitor_settled(self, owner: asyncio.Task[MonitorReport]) -> None:
        self._guard_context()
        if not owner.cancelled():
            owner.exception()

    async def _own_monitor(
        self, generation: _ObservationGeneration, pending: _MonitorRun
    ) -> MonitorReport:
        def revalidate() -> None:
            self._guard_context()
            if self._monitors_sealed:
                raise MonitorRejected("monitor_unavailable")
            if (
                self._generation is not generation
                or generation.monitor_sealed
                or self._summary.state is not RuntimeState.ACTIVE
            ):
                raise MonitorRejected("not_active")
            if self._monitor_access(generation) is not pending.access:
                raise MonitorRejected("monitor_unavailable")

        try:
            operation = await pending.access.coordinator.start(
                pending.request,
                run_id=generation.evidence.run_id.value,
                expected_provenance=pending.provenance,
                revalidate=revalidate,
                charge_markers=pending.access.charge_markers,
                operation_id=pending.operation_id,
                pending_stop=lambda: pending.intent,
            )
            return await operation.wait()
        finally:
            if generation.monitor is pending:
                generation.monitor = None

    def _latch_monitor_stop(
        self, generation: _ObservationGeneration, outcome: MonitorOutcome
    ) -> None:
        pending = generation.monitor
        if pending is not None:
            if pending.intent is None:
                pending.intent = outcome
            pending.access.coordinator._stop(pending.intent)

    def _seal_monitors(self) -> None:
        """Seal this incarnation immediately, without backend or journal I/O."""
        self._guard_context()
        self._monitors_sealed = True
        generation = self._generation
        if generation is not None:
            self._latch_monitor_stop(generation, MonitorOutcome.SERVICE_STOPPING)

    async def _join_monitor(
        self, generation: _ObservationGeneration, snapshot: AcquisitionSnapshot | None
    ) -> None:
        pending = generation.monitor
        if pending is not None:
            # Only joined acquisition facts supply fallback when no end committed.
            # Existing capture status/failure facts are never rewritten.
            if pending.intent is not None:
                outcome = pending.intent
            elif (
                snapshot is not None
                and snapshot.terminal_trigger is AcquisitionTerminalTrigger.DISCONNECTED
            ):
                outcome = MonitorOutcome.DISCONNECTED
            elif (
                snapshot is not None
                and snapshot.primary_failure_kind
                is AcquisitionFailureKind.RECORDING_FAILURE
            ):
                outcome = MonitorOutcome.RECORDING_FAILURE
            elif (
                snapshot is not None
                and snapshot.primary_failure_kind
                is AcquisitionFailureKind.TRANSPORT_FAILURE
            ):
                outcome = MonitorOutcome.TRANSPORT_FAILURE
            else:
                outcome = MonitorOutcome.DETACHED
            self._latch_monitor_stop(generation, outcome)
            assert pending.owner is not None
            await asyncio.gather(asyncio.shield(pending.owner), return_exceptions=True)
        generation.monitor_access = None

    def _annotation_access(
        self, generation: _ObservationGeneration
    ) -> tuple[PreparedAnnotationAccess, str]:
        access = generation.annotation_access
        if not isinstance(access, PreparedAnnotationAccess):
            raise AnnotationRejected("annotation_unavailable")
        try:
            replace(access)
            if (
                access.session_id != generation.evidence.session_id
                or access.policy != generation.evidence.policy
                or access.coordinator.current_provenance is None
                or not callable(access.coordinator.append_client_annotation)
                or not callable(access.clock.now_ns)
                or not callable(access.clock.wait_until)
            ):
                raise ValueError("unusable annotation access")
            origin_id = access.clock.origin_id
            self._annotation_budget.check_origin(origin_id)
        except Exception:
            raise AnnotationRejected("annotation_unavailable") from None
        return access, origin_id

    async def annotate(self, request: AnnotationRequest) -> AnnotationReceipt:
        self._guard_context()
        if not isinstance(request, AnnotationRequest):
            raise RuntimeRejectedError(RuntimeRejectedKind.INVALID_REQUEST)
        if self._annotations_sealed:
            raise AnnotationRejected("annotation_unavailable")
        association = self._evidence_association
        if association is None or association.session_id is None:
            raise AnnotationRejected("no_associated_session")
        if request.session_id != association.session_id:
            raise AnnotationRejected("session_not_associated")
        generation = self._generation
        if (
            generation is None
            or self.status().state is not RuntimeState.ACTIVE
            or generation.annotation_sealed
        ):
            raise AnnotationRejected("not_active")
        access, origin_id = self._annotation_access(generation)
        _preflight_annotation(access, request, origin_id)
        if generation.annotation is not None:
            raise AnnotationRejected("busy")
        self._annotation_budget.admit(access.clock, origin_id)
        # No await separates admission accounting from strong owner registration.
        pending = _AnnotationRun(access, request)
        generation.annotation = pending
        owner = asyncio.create_task(
            self._own_annotation(generation, pending),
            name=f"dutchmate-annotation-{association.run_id.value}",
        )
        pending.owner = owner
        owner.add_done_callback(self._annotation_settled)
        try:
            return await asyncio.shield(owner)
        except asyncio.CancelledError:
            while not owner.done():
                try:
                    await asyncio.shield(owner)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not owner.cancelled():
                owner.exception()
            raise

    def _annotation_settled(self, owner: asyncio.Task[AnnotationReceipt]) -> None:
        self._guard_context()
        if not owner.cancelled():
            owner.exception()

    async def _own_annotation(
        self, generation: _ObservationGeneration, pending: _AnnotationRun
    ) -> AnnotationReceipt:
        try:
            # Already admitted session context survives ACTIVE/segment sealing.
            record = await pending.access.coordinator.append_client_annotation(
                pending.request.client_surface, pending.request.text
            )
            return AnnotationReceipt(
                generation.evidence.run_id.value,
                pending.request.session_id,
                EvidenceReference(pending.request.session_id, record.sequence),
                record,
            )
        except JournalFailure:
            raise
        except Exception:
            raise RuntimeError("annotation internal failure") from None
        finally:
            if generation.annotation is pending:
                generation.annotation = None

    def _seal_annotations(self) -> None:
        """Permanently seal new incarnation admission, without cancelling owners."""
        self._guard_context()
        self._annotations_sealed = True
        if self._generation is not None:
            self._generation.annotation_sealed = True

    async def _join_annotation(self, generation: _ObservationGeneration) -> None:
        pending = generation.annotation
        if pending is not None:
            assert pending.owner is not None
            await asyncio.gather(asyncio.shield(pending.owner), return_exceptions=True)
        generation.annotation_access = None

    async def read_record(self, reference: EvidenceReference) -> RunEvidencePage:
        self._guard_context()
        if not isinstance(reference, EvidenceReference):
            raise RuntimeRejectedError(RuntimeRejectedKind.INVALID_REQUEST)
        owner = self._admit_read(reference.session_id, reference)
        return await self._wait_read(owner)

    async def read_page(self, request: EvidenceRetrievalRequest) -> RunEvidencePage:
        self._guard_context()
        if not isinstance(request, EvidenceRetrievalRequest):
            raise RuntimeRejectedError(RuntimeRejectedKind.INVALID_REQUEST)
        reference = request.reference
        session_id = (
            reference if isinstance(reference, SessionId) else reference.session_id
        )
        owner = self._admit_read(session_id, request)
        return await self._wait_read(owner)

    def _admit_read(
        self, session_id: SessionId, query: EvidenceReference | EvidenceRetrievalRequest
    ) -> asyncio.Task[RunEvidencePage]:
        # No await: validation, source capture and lease registration form one
        # owner-loop admission point, independent of any caller's earlier work.
        association = self._evidence_association
        if association is None or association.session_id is None:
            raise EvidenceReadRejected("no_associated_session")
        if session_id != association.session_id:
            raise EvidenceReadRejected("session_not_associated")
        if not self._evidence_read_cleanup_confirmed:
            raise EvidenceReadRejected("read_unavailable")
        reader = association.live_reader if association.live_reads_open else None
        opener = (
            association.terminal_opener if association.terminal_reads_open else None
        )
        if reader is None and opener is None:
            raise EvidenceReadRejected("read_unavailable")
        if len(self._reads) >= 8:
            raise EvidenceReadRejected("read_capacity")
        return self._submit_read(association, reader, opener, query)

    def _submit_read(
        self,
        association: _EvidenceAssociation,
        reader: EvidenceReadPort | None,
        opener: Callable[[], Awaitable[OwnedEvidenceReadPort]] | None,
        query: EvidenceReference | EvidenceRetrievalRequest,
    ) -> asyncio.Task[RunEvidencePage]:
        session_id = association.session_id
        assert session_id is not None
        work = (
            self._own_read(association.run_id, session_id, reader, query)
            if reader is not None
            else self._own_terminal_read(association.run_id, session_id, opener, query)
        )
        owner = asyncio.create_task(
            work,
            name=f"dutchmate-evidence-{association.run_id.value}",
        )
        self._reads.add(owner)
        association.reads.add(owner)
        owner.add_done_callback(lambda task: self._read_settled(task, association))
        return owner

    async def _own_read(
        self,
        run_id: RunId,
        session_id: SessionId,
        reader: EvidenceReadPort,
        query: EvidenceReference | EvidenceRetrievalRequest,
    ) -> RunEvidencePage:
        if isinstance(query, EvidenceReference):
            page = await reader.resolve_record(query)
        else:
            page = await reader.retrieve(query)
        return RunEvidencePage(run_id, session_id, page)

    async def _own_terminal_read(
        self,
        run_id: RunId,
        session_id: SessionId,
        opener: Callable[[], Awaitable[OwnedEvidenceReadPort]] | None,
        query: EvidenceReference | EvidenceRetrievalRequest,
    ) -> RunEvidencePage:
        assert opener is not None
        try:
            reader = await opener()
        except EvidenceSourceOpenFailure as failure:
            if not failure.reader_close_confirmed:
                self._evidence_read_cleanup_confirmed = False
            raise failure.primary from None
        except BaseException:
            # No normalized positive acknowledgment: seal before lease release.
            self._evidence_read_cleanup_confirmed = False
            raise
        try:
            report = await self._own_read(run_id, session_id, reader, query)
        except BaseException:
            try:
                await reader.close()
            except BaseException:
                self._evidence_read_cleanup_confirmed = False
            raise
        try:
            await reader.close()
        except BaseException:
            self._evidence_read_cleanup_confirmed = False
            raise
        return report

    def _read_settled(
        self, owner: asyncio.Task[RunEvidencePage], association: _EvidenceAssociation
    ) -> None:
        self._guard_context()
        if not owner.cancelled():
            owner.exception()
        association.reads.discard(owner)
        self._reads.discard(owner)

    async def _wait_read(self, owner: asyncio.Task[RunEvidencePage]) -> RunEvidencePage:
        try:
            return await asyncio.shield(owner)
        except asyncio.CancelledError:
            # Caller loss never cancels the private read owner or submitted
            # persistence work. Join despite repeated cancellation, then preserve
            # the caller's cancellation rather than a secondary read failure.
            while not owner.done():
                try:
                    await asyncio.shield(owner)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not owner.cancelled():
                owner.exception()
            raise

    async def attach(
        self, profile: ResolvedDutProfile, prepare: PrepareObservationRun
    ) -> RuntimeStatus:
        self._guard_context()
        if not isinstance(profile, ResolvedDutProfile) or not callable(prepare):
            raise RuntimeRejectedError(RuntimeRejectedKind.INVALID_REQUEST)
        async with self._lock:
            if not self._summary.attach_admissible:
                kind = (
                    RuntimeRejectedKind.CLEANUP_UNCONFIRMED
                    if self._summary.owner_settled
                    else RuntimeRejectedKind.BUSY
                )
                raise RuntimeRejectedError(kind)
            run_id = RunId()
            association = _EvidenceAssociation(run_id)
            generation = _ObservationGeneration(self._loop.create_future(), association)
            self._evidence_association = association
            self._summary = RuntimeStatus(
                state=RuntimeState.ATTACHING,
                run_id=run_id,
                profile=profile,
                owner_settled=False,
            )
            self._generation = generation
            generation.owner = asyncio.create_task(
                self._own(generation, profile, prepare),
                name=f"dutchmate-observation-{run_id.value}",
            )
            owner = generation.owner
        # Caller waits do not own or cancel startup/Acquisition resource work.
        try:
            await asyncio.wait(
                (generation.ready, owner), return_when=asyncio.FIRST_COMPLETED
            )
            if generation.ready.done():
                return generation.ready.result()
            return await asyncio.shield(owner)
        except asyncio.CancelledError:
            await self._settle_cancelled_waiter(
                generation, RuntimeStopIntent.ATTACH_CANCELLED
            )
            raise

    async def detach(self) -> RuntimeStatus:
        self._guard_context()
        async with self._lock:
            if self._summary.owner_settled:
                return self._summary
            generation = self._generation
            assert generation is not None and generation.owner is not None
            self._request_stop(generation, RuntimeStopIntent.DETACH)
            owner = generation.owner
        try:
            return await asyncio.shield(owner)
        except asyncio.CancelledError:
            await self._settle_cancelled_waiter(generation, RuntimeStopIntent.DETACH)
            raise

    def _request_stop(
        self, generation: _ObservationGeneration, intent: RuntimeStopIntent
    ) -> None:
        """Caller holds the lifecycle lock; only this generation can mutate it."""
        if self._generation is not generation:
            return
        generation.monitor_sealed = True
        generation.annotation_sealed = True
        self._seal_follow(generation, "detached")
        self._latch_monitor_stop(generation, MonitorOutcome.DETACHED)
        if self._summary.stop_intent is RuntimeStopIntent.NONE:
            self._summary = replace(
                self._summary, state=RuntimeState.DETACHING, stop_intent=intent
            )
        generation.stop.set()

    async def _settle_cancelled_waiter(
        self, generation: _ObservationGeneration, intent: RuntimeStopIntent
    ) -> None:
        """Admit stop despite repeated cancellation, then join the captured owner."""
        owner = generation.owner
        assert owner is not None
        while True:
            self._guard_context()
            try:
                async with self._lock:
                    self._request_stop(generation, intent)
                break
            except asyncio.CancelledError:
                continue
        while True:
            try:
                await asyncio.shield(owner)
            except asyncio.CancelledError:
                if not owner.done():
                    continue
            except Exception:
                # Caller cancellation takes precedence over an owner failure.
                # Failure normalization/status belongs to the owner's lifecycle.
                pass
            return

    def _startup_failure(
        self, generation: _ObservationGeneration, issue: RuntimeIssue
    ) -> None:
        """Caller holds the lock; preserve any primary already in the snapshot."""
        generation.startup_failed = True
        current = self.status()
        self._summary = replace(
            current,
            state=RuntimeState.DETACHING,
            primary_issue=current.primary_issue or issue,
        )

    async def _wait_for_stop_or_termination(
        self, generation: _ObservationGeneration
    ) -> None:
        """Race notifications only; all cleanup/mutation stays in this owner."""
        self._guard_context()
        assert generation.acquisition is not None
        stop_waiter = self._loop.create_task(generation.stop.wait())
        terminal_waiter = self._loop.create_task(
            generation.acquisition.wait_terminated()
        )
        waiters = (stop_waiter, terminal_waiter)
        try:
            await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
            # Publish draining before joining the notification waiters. Neither
            # an Acquisition terminal event nor state proves actual consumer join.
            self._guard_context()
            async with self._lock:
                self._summary = replace(self.status(), state=RuntimeState.DETACHING)
                self._seal_follow(
                    generation,
                    "source_failed" if self._summary.primary_issue else "source_ended",
                )
        finally:
            # These are Event notification waits, never startup, RX, backend
            # close, or join work. Drain both before this generation can settle.
            for waiter in waiters:
                if not waiter.done():
                    waiter.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)

    async def _own(
        self,
        generation: _ObservationGeneration,
        profile: ResolvedDutProfile,
        prepare: PrepareObservationRun,
    ) -> RuntimeStatus:
        prepared: PreparedObservationRun | None = None
        if not generation.stop.is_set():
            self._guard_context()
            async with self._lock:
                self._summary = replace(self._summary, recorder_close_confirmed=False)
            try:
                candidate = await prepare(profile)
            except PreparationFailure as failure:
                self._guard_context()
                async with self._lock:
                    self._startup_failure(generation, failure.primary_issue)
                    self._summary = replace(
                        self._summary,
                        session_id=failure.session_id,
                        recorder_close_confirmed=failure.recorder_close_confirmed,
                        cleanup_issues=(failure.cleanup_issue,)
                        if failure.cleanup_issue
                        else (),
                    )
                    generation.evidence.session_id = failure.session_id
                    generation.evidence.policy = profile.session_policy
                    access = failure.terminal_evidence_access
                    if (
                        failure.session_id is not None
                        and _read_access_matches(
                            access, failure.session_id, profile.session_policy
                        )
                        and access is not None
                    ):
                        generation.evidence.terminal_opener = access.terminal_opener
            except Exception:
                self._guard_context()
                async with self._lock:
                    self._startup_failure(
                        generation,
                        RuntimeIssue(
                            RuntimeIssueSource.INTERNAL_CONTRACT,
                            "internal_contract_failure",
                        ),
                    )
            else:
                values = _prepared_values(candidate)
                self._guard_context()
                async with self._lock:
                    if values is None:
                        self._startup_failure(
                            generation,
                            RuntimeIssue(
                                RuntimeIssueSource.INTERNAL_CONTRACT,
                                "internal_contract_failure",
                            ),
                        )
                    else:
                        prepared = candidate
                        session_id, policy = values
                        self._summary = replace(self._summary, session_id=session_id)
                        association = generation.evidence
                        association.session_id = session_id
                        association.policy = policy
                        if (
                            policy != profile.session_policy
                            or not _read_access_matches(
                                prepared.evidence_access, session_id, policy
                            )
                            or not _monitor_access_matches(
                                prepared.monitor_access,
                                prepared.recorder,
                                session_id,
                                policy,
                            )
                            or not _annotation_access_matches(
                                prepared.annotation_access,
                                prepared.recorder,
                                session_id,
                                policy,
                            )
                            or not _follow_access_matches(
                                prepared.follow_access,
                                prepared.recorder,
                                prepared.evidence_access,
                                session_id,
                                policy,
                            )
                        ):
                            self._startup_failure(
                                generation,
                                RuntimeIssue(
                                    RuntimeIssueSource.INTERNAL_CONTRACT,
                                    "internal_contract_failure",
                                ),
                            )
                        else:
                            generation.monitor_access = prepared.monitor_access
                            generation.annotation_access = prepared.annotation_access
                            generation.follow_access = prepared.follow_access
                            if prepared.evidence_access is not None:
                                association.live_reader = (
                                    prepared.evidence_access.live_reader
                                )
                                association.terminal_opener = (
                                    prepared.evidence_access.terminal_opener
                                )
                            association.live_reads_open = True
                            if not generation.stop.is_set():
                                generation.acquisition = Acquisition(prepared.recorder)
            if generation.acquisition is not None:
                assert prepared is not None
                try:
                    await generation.acquisition.start(prepared.backend)
                except Exception:
                    self._guard_context()
                    async with self._lock:
                        self._startup_failure(
                            generation,
                            RuntimeIssue(
                                RuntimeIssueSource.ACQUISITION_START,
                                "internal_contract_failure",
                            ),
                        )
                else:
                    self._guard_context()
                    async with self._lock:
                        generation.startup_succeeded = True
                        snapshot = generation.acquisition.snapshot()
                        capturing = (
                            not generation.stop.is_set()
                            and snapshot.state is AcquisitionState.ACQUIRING
                            and snapshot.terminal_trigger is None
                        )
                        if capturing:
                            self._summary = replace(
                                self.status(), state=RuntimeState.ACTIVE
                            )
                            generation.ready.set_result(self._summary)
                    if capturing:
                        await self._wait_for_stop_or_termination(generation)

        self._guard_context()
        async with self._lock:
            self._summary = replace(self.status(), state=RuntimeState.DETACHING)
            generation.monitor_sealed = True
            generation.annotation_sealed = True
            self._seal_follow(
                generation,
                "source_failed" if self._summary.primary_issue else "source_ended",
            )
        joined_snapshot: AcquisitionSnapshot | None = None
        if generation.acquisition is not None:
            try:
                # Observed termination already owns its final append/close.
                # Join it without submitting stop or relabeling its cause.
                if generation.acquisition.snapshot().terminal_trigger is None:
                    await generation.acquisition.stop()
            except Exception:
                self._guard_context()
                async with self._lock:
                    current = self.status()
                    if not current.cleanup_issues:
                        self._summary = replace(
                            current,
                            cleanup_issues=(
                                RuntimeIssue(
                                    RuntimeIssueSource.ACQUISITION,
                                    "internal_contract_failure",
                                ),
                            ),
                        )
            # Even a failed stop/close must join actual consumer and close work
            # before the recorder is closed. No direct second backend close.
            joined_snapshot = await generation.acquisition.join_terminated()
        await self._join_monitor(generation, joined_snapshot)
        await self._join_annotation(generation)
        await self._final_follow_head(generation)
        # Acquisition, Monitor and annotations joined. Seal before pinned reads;
        # no lifecycle lock spans these joins or recorder close. Terminal access
        # retains only opaque target metadata for its separately planned reader.
        association = generation.evidence
        association.live_reads_open = False
        if association.reads:
            await asyncio.gather(
                *(asyncio.shield(owner) for owner in tuple(association.reads)),
                return_exceptions=True,
            )
        association.live_reader = None
        if generation.follow is not None:
            await generation.follow._release()
        if prepared is not None:
            try:
                await prepared.recorder.close()
            except Exception as error:
                issue = RuntimeIssue(
                    RuntimeIssueSource.RECORDER_CLOSE,
                    error.kind
                    if isinstance(error, JournalFailure)
                    else "internal_contract_failure",
                )
                self._guard_context()
                async with self._lock:
                    current = self.status()
                    self._summary = replace(
                        current,
                        cleanup_issues=(*current.cleanup_issues, issue),
                    )
            else:
                self._guard_context()
                async with self._lock:
                    self._summary = replace(
                        self.status(), recorder_close_confirmed=True
                    )
        # All resource work has joined. No await or further mutation follows
        # terminal publication; waiters then join the completed owner itself.
        self._guard_context()
        async with self._lock:
            current = self.status()
            if (
                current.acquisition is not None
                and current.acquisition.terminal_trigger
                is AcquisitionTerminalTrigger.DISCONNECTED
            ):
                reason = RuntimeTerminalReason.DISCONNECTED
            elif generation.startup_failed:
                reason = RuntimeTerminalReason.STARTUP_FAILURE
            elif current.primary_issue is not None:
                reason = RuntimeTerminalReason.ACQUISITION_FAILURE
            elif current.stop_intent is RuntimeStopIntent.ATTACH_CANCELLED:
                reason = RuntimeTerminalReason.ATTACH_CANCELLED
            elif current.stop_intent is RuntimeStopIntent.DETACH:
                reason = RuntimeTerminalReason.DETACHED
            else:
                reason = RuntimeTerminalReason.CLEANUP_FAILURE
            self._summary = replace(
                current,
                state=RuntimeState.FAILED
                if current.primary_issue or current.cleanup_issues
                else RuntimeState.TERMINATED,
                terminal_reason=reason,
                owner_settled=True,
            )
            generation.acquisition = None
            association.terminal_reads_open = (
                self._summary.owner_settled and self._summary.recorder_close_confirmed
            )
            self._generation = None
            if not generation.ready.done():
                generation.ready.set_result(self._summary)
            return self._summary
