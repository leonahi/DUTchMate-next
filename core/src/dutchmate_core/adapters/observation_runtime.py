"""Explicit Profile/SQLite/Basic composition and owned preparation cleanup."""

from pathlib import Path

from dutchmate_core.adapters.basic_profile import to_basic_serial_open_request
from dutchmate_core.adapters.basic_serial import BasicSerialBackend
from dutchmate_core.adapters.sqlite_evidence import SqliteEvidenceJournal
from dutchmate_core.adapters.toml_profile import resolve_profile
from dutchmate_core.backend import NormalizedBackendFailure
from dutchmate_core.evidence import JournalFailure, JournalFailureKind, JournalOperation
from dutchmate_core.profile import ProfileFailure, ResolvedDutProfile
from dutchmate_core.runtime import (
    ObservationRuntime,
    PreparationFailure,
    PreparedObservationRun,
    RuntimeIssue,
    RuntimeIssueSource,
    RuntimeStatus,
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
            journal = await SqliteEvidenceJournal.create(
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
            try:
                request = to_basic_serial_open_request(profile)
                backend = BasicSerialBackend(
                    request.selector, request.configuration, request.line_intent
                )
                return PreparedObservationRun(recorder=journal, backend=backend)
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
            )
        # Raise outside exception handlers so raw cause/context cannot cross
        # preparation. Kept artifacts are never probed, reopened, or deleted.
        raise failure

    return await runtime.attach(resolved, prepare)
