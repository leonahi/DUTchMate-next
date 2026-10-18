"""Explicit Profile/SQLite/Basic composition and owned preparation cleanup."""

from functools import partial
from pathlib import Path
from weakref import WeakKeyDictionary

from dutchmate_core.adapters.basic_profile import to_basic_serial_open_request
from dutchmate_core.adapters.basic_serial import BasicSerialBackend
from dutchmate_core.adapters.monotonic_clock import MonotonicMonitorClock
from dutchmate_core.adapters.sqlite_evidence import (
    SqliteEvidenceJournal,
    charge_client_annotation,
    charge_monitor_markers,
)
from dutchmate_core.adapters.terminal_evidence import (
    capture_terminal_target,
    open_terminal_reader,
)
from dutchmate_core.adapters.toml_profile import resolve_profile
from dutchmate_core.annotation import PreparedAnnotationAccess
from dutchmate_core.backend import NormalizedBackendFailure
from dutchmate_core.evidence import JournalFailure, JournalFailureKind, JournalOperation
from dutchmate_core.evidence_access import PreparedEvidenceAccess
from dutchmate_core.monitor import MonitorRecordingCoordinator, PreparedMonitorAccess
from dutchmate_core.profile import ProfileFailure, ResolvedDutProfile
from dutchmate_core.runtime import (
    ObservationRuntime,
    PreparationFailure,
    PreparedFollowAccess,
    PreparedObservationRun,
    RuntimeIssue,
    RuntimeIssueSource,
    RuntimeStatus,
)

# Clock identity spans attaches, but this adapter does not retain runtime owners.
# No backend, journal, operation or result is kept in this association.
_clocks: WeakKeyDictionary[ObservationRuntime, MonotonicMonitorClock] = (
    WeakKeyDictionary()
)


def _issue(error: Exception, source: RuntimeIssueSource) -> RuntimeIssue:
    """Keep normalized categories only; no raw detail, cause, or adapter object."""
    if isinstance(error, (JournalFailure, ProfileFailure, NormalizedBackendFailure)):
        return RuntimeIssue(source, error.kind)
    return RuntimeIssue(source, "internal_contract_failure")


async def attach_basic_observation(
    runtime: ObservationRuntime,
    explicit_profile_path: str | Path,
    explicit_journal_path: str | Path,
) -> RuntimeStatus:
    """Resolve the selected Profile, then prepare resources only if admitted."""
    runtime.status()  # Context guard only; runtime.attach owns admission.
    resolved = resolve_profile(explicit_profile_path)

    async def prepare(profile: ResolvedDutProfile) -> PreparedObservationRun:
        try:
            journal = await SqliteEvidenceJournal.create_v3(
                explicit_journal_path, profile.session_policy
            )
        except Exception as error:
            failure = PreparationFailure(
                primary_issue=_issue(error, RuntimeIssueSource.PREPARATION),
                recorder_close_confirmed=(
                    isinstance(error, JournalFailure)
                    and error.operation is JournalOperation.CREATE
                    and error.kind
                    in {
                        JournalFailureKind.INVALID_INPUT,
                        JournalFailureKind.JOURNAL_EXISTS,
                    }
                ),
            )
        else:
            # Identity capture is optional; it never invalidates live capture.
            try:
                target = capture_terminal_target(
                    explicit_journal_path,
                    session_id=journal.session_id,
                    policy=journal.policy,
                    expected_schema_version=3,
                )
            except Exception:
                target = None
            terminal_opener = (
                None if target is None else partial(open_terminal_reader, target)
            )
            try:
                request = to_basic_serial_open_request(profile)
                backend = BasicSerialBackend(
                    request.selector, request.configuration, request.line_intent
                )
                clock = _clocks.get(runtime)
                if clock is None:
                    clock = MonotonicMonitorClock()
                    _clocks[runtime] = clock
                coordinator = MonitorRecordingCoordinator(recorder=journal, clock=clock)
                return PreparedObservationRun(
                    recorder=coordinator,
                    backend=backend,
                    evidence_access=PreparedEvidenceAccess(
                        session_id=journal.session_id,
                        policy=journal.policy,
                        live_reader=journal,
                        terminal_opener=terminal_opener,
                    ),
                    monitor_access=PreparedMonitorAccess(
                        session_id=journal.session_id,
                        policy=journal.policy,
                        coordinator=coordinator,
                        clock=clock,
                        charge_markers=charge_monitor_markers,
                    ),
                    annotation_access=PreparedAnnotationAccess(
                        session_id=journal.session_id,
                        policy=journal.policy,
                        coordinator=coordinator,
                        clock=clock,
                        charge_annotation=charge_client_annotation,
                    ),
                    follow_access=PreparedFollowAccess(
                        session_id=journal.session_id,
                        policy=journal.policy,
                        coordinator=coordinator,
                        live_reader=journal,
                    ),
                )
            except Exception as error:
                primary_issue = _issue(error, RuntimeIssueSource.PREPARATION)

            cleanup_issue = None
            try:
                await journal.close()
            except Exception as error:
                cleanup_issue = _issue(error, RuntimeIssueSource.RECORDER_CLOSE)
            failure = PreparationFailure(
                primary_issue=primary_issue,
                session_id=journal.session_id,
                recorder_close_confirmed=cleanup_issue is None,
                cleanup_issue=cleanup_issue,
                terminal_evidence_access=(
                    None
                    if terminal_opener is None
                    else PreparedEvidenceAccess(
                        session_id=journal.session_id,
                        policy=journal.policy,
                        terminal_opener=terminal_opener,
                    )
                ),
            )
        # Raise outside exception handlers so raw cause/context cannot cross
        # preparation. Kept artifacts are never probed, reopened, or deleted.
        raise failure

    return await runtime.attach(resolved, prepare)
