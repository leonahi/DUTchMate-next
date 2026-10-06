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
from dutchmate_core.backend import Backend, BackendFailureKind
from dutchmate_core.evidence import EvidenceRecorder, JournalFailure, JournalFailureKind
from dutchmate_core.model import SessionId, SessionPolicy
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
    {"primary_issue", "session_id", "recorder_close_confirmed", "cleanup_issue"}
)


@dataclass(slots=True, unsafe_hash=True)
class PreparationFailure(RuntimeError):
    """Read-only preparation facts with normal RuntimeError transport fields."""

    primary_issue: RuntimeIssue
    session_id: SessionId | None = None
    recorder_close_confirmed: bool = False
    cleanup_issue: RuntimeIssue | None = None

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
        RuntimeError.__init__(self, "preparation_failed")


class ObservationRecorder(EvidenceRecorder, Protocol):
    """Only existing append and immutable identity/policy plus async close."""

    @property
    def session_id(self) -> SessionId: ...

    @property
    def policy(self) -> SessionPolicy: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PreparedObservationRun:
    """One recorder and unopened backend; receiver checks Profile policy by value."""

    recorder: ObservationRecorder
    backend: Backend


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


@dataclass(slots=True)
class _ObservationGeneration:
    ready: asyncio.Future[RuntimeStatus]
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    acquisition: Acquisition | None = None
    owner: asyncio.Task[RuntimeStatus] | None = None
    startup_succeeded: bool = False
    startup_failed: bool = False


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
            generation = _ObservationGeneration(self._loop.create_future())
            run_id = RunId()
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
                        if policy != profile.session_policy:
                            self._startup_failure(
                                generation,
                                RuntimeIssue(
                                    RuntimeIssueSource.INTERNAL_CONTRACT,
                                    "internal_contract_failure",
                                ),
                            )
                        elif not generation.stop.is_set():
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
            await generation.acquisition.join_terminated()
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
            self._generation = None
            if not generation.ready.done():
                generation.ready.set_result(self._summary)
            return self._summary
