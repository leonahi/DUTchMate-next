"""Private, request-owned read-only access to a captured SQLite evidence source."""

import asyncio
import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from dutchmate_core.adapters.sqlite_evidence import (
    _await_submitted_worker,
    _connect_sqlite,
    _normalize_storage_failure,
    _resolve_record_on_worker,
    _retrieve_page_on_worker,
    _validate_existing_journal,
)
from dutchmate_core.evidence import (
    EvidencePage,
    EvidenceRetrievalRequest,
    JournalFailure,
    JournalFailureKind,
    JournalOperation,
)
from dutchmate_core.evidence_access import (
    EvidenceReadRejected,
    EvidenceSourceOpenFailure,
    OwnedEvidenceReadPort,
)
from dutchmate_core.model import EvidenceReference, SessionId, SessionPolicy


@dataclass(frozen=True, slots=True)
class _TerminalTarget:
    path: Path
    device: int
    inode: int
    session_id: SessionId
    policy: SessionPolicy
    expected_schema_version: int = 1


def capture_terminal_target(
    path: str | Path,
    *,
    session_id: SessionId,
    policy: SessionPolicy,
    expected_schema_version: int = 1,
) -> _TerminalTarget | None:
    """Capture metadata only; inability to capture must not invalidate live RX."""
    try:
        resolved = Path(path).resolve(strict=True)
        identity = resolved.stat()
        if not stat.S_ISREG(identity.st_mode):
            return None
    except OSError:
        return None
    return _TerminalTarget(
        resolved,
        identity.st_dev,
        identity.st_ino,
        session_id,
        policy,
        expected_schema_version,
    )


def _check_identity(target: _TerminalTarget) -> None:
    try:
        identity = target.path.stat()
    except FileNotFoundError:
        raise JournalFailure(
            JournalOperation.OPEN, JournalFailureKind.JOURNAL_MISSING
        ) from None
    if (
        not stat.S_ISREG(identity.st_mode)
        or identity.st_dev != target.device
        or identity.st_ino != target.inode
    ):
        raise EvidenceReadRejected("source_changed")


def _close_reader_on_worker(connection: sqlite3.Connection) -> None:
    # Attempt native close even if ending the transaction fails. Neither failure
    # supplies a positive cleanup acknowledgment to the owning request.
    failure: JournalFailure | None = None
    try:
        connection.rollback()
    except Exception as error:
        failure = _close_failure(error)
    finally:
        try:
            connection.close()
        except Exception as error:
            if failure is None:
                failure = _close_failure(error)
    if failure is not None:
        raise failure


def _close_failure(error: Exception) -> JournalFailure:
    if isinstance(error, (sqlite3.Error, OSError)):
        return _normalize_storage_failure(JournalOperation.CLOSE, error)
    return JournalFailure(JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE)


def _open_on_worker(target: _TerminalTarget) -> sqlite3.Connection:
    connection: sqlite3.Connection | None = None
    try:
        _check_identity(target)
        connection = _connect_sqlite(
            target.path.as_uri() + "?mode=ro&cache=private", uri=True
        )
        _check_identity(target)
        connection.execute("PRAGMA query_only=ON")
        row = connection.execute("PRAGMA query_only").fetchone()
        if row != (1,):
            raise JournalFailure(JournalOperation.OPEN, JournalFailureKind.READ_ONLY)
        connection.execute("BEGIN")
        session_id, policy = _validate_existing_journal(
            connection,
            schema_version=target.expected_schema_version,
        )
        if session_id != target.session_id:
            raise JournalFailure(
                JournalOperation.OPEN, JournalFailureKind.SESSION_MISMATCH
            )
        if policy != target.policy:
            raise EvidenceReadRejected("source_changed")
        return connection
    except BaseException as error:
        if isinstance(error, (JournalFailure, EvidenceReadRejected)):
            primary = error
        elif isinstance(error, (sqlite3.Error, OSError)):
            primary = _normalize_storage_failure(JournalOperation.OPEN, error)
        else:
            primary = JournalFailure(
                JournalOperation.OPEN, JournalFailureKind.IO_FAILURE
            )
        confirmed = isinstance(
            error, (JournalFailure, EvidenceReadRejected, sqlite3.Error, OSError)
        )
        if connection is not None:
            try:
                _close_reader_on_worker(connection)
                confirmed = True
            except BaseException:
                confirmed = False
        raise EvidenceSourceOpenFailure(primary, confirmed) from None


async def _await_reader_close(future: asyncio.Future[None]) -> None:
    # A close failure must remain observable even when its waiter is cancelled.
    # Successful close still propagates cancellation after submitted work joins.
    cancelled = False
    while True:
        try:
            await asyncio.shield(future)
            break
        except asyncio.CancelledError:
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError


async def open_terminal_reader(target: _TerminalTarget) -> OwnedEvidenceReadPort:
    """Open one private reader; cancellation joins opening and closes its result."""
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="evidence-read")
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(executor, _open_on_worker, target)
    cancelled = False
    try:
        while True:
            try:
                connection = await asyncio.shield(future)
                break
            except asyncio.CancelledError:
                cancelled = True
            except EvidenceSourceOpenFailure as error:
                if cancelled and error.reader_close_confirmed:
                    raise asyncio.CancelledError from None
                raise
        if not cancelled:
            return _TerminalReader(target, connection, executor)
        # A cancelled opener never loses a connection returned by submitted work.
        closing = loop.run_in_executor(executor, _close_reader_on_worker, connection)
        while True:
            try:
                await asyncio.shield(closing)
                break
            except asyncio.CancelledError:
                continue
            except BaseException:
                raise EvidenceSourceOpenFailure(
                    JournalFailure(
                        JournalOperation.OPEN, JournalFailureKind.IO_FAILURE
                    ),
                    False,
                ) from None
        raise asyncio.CancelledError
    except BaseException:
        executor.shutdown(wait=True, cancel_futures=True)
        raise


class _TerminalReader:
    """A single read snapshot, owned until close completes on its native worker."""

    def __init__(
        self,
        target: _TerminalTarget,
        connection: sqlite3.Connection,
        executor: ThreadPoolExecutor,
    ) -> None:
        self._target = target
        self._connection: sqlite3.Connection | None = connection
        self._executor = executor
        self._gate = asyncio.Lock()
        self._close_error: JournalFailure | None = None

    @property
    def session_id(self) -> SessionId:
        return self._target.session_id

    @property
    def policy(self) -> SessionPolicy:
        return self._target.policy

    def _open_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise JournalFailure(JournalOperation.RETRIEVE, JournalFailureKind.CLOSED)
        return self._connection

    async def resolve_record(self, reference: EvidenceReference) -> EvidencePage:
        if not isinstance(reference, EvidenceReference):
            raise JournalFailure(
                JournalOperation.RETRIEVE, JournalFailureKind.INVALID_INPUT
            )
        async with self._gate:
            future = asyncio.get_running_loop().run_in_executor(
                self._executor,
                _resolve_record_on_worker
                if self._target.expected_schema_version == 1
                else partial(
                    _resolve_record_on_worker,
                    schema_version=self._target.expected_schema_version,
                ),
                self._open_connection(),
                reference,
            )
            return await _await_submitted_worker(future)

    async def retrieve(self, request: EvidenceRetrievalRequest) -> EvidencePage:
        if not isinstance(request, EvidenceRetrievalRequest):
            raise JournalFailure(
                JournalOperation.RETRIEVE, JournalFailureKind.INVALID_INPUT
            )
        async with self._gate:
            future = asyncio.get_running_loop().run_in_executor(
                self._executor,
                _retrieve_page_on_worker
                if self._target.expected_schema_version == 1
                else partial(
                    _retrieve_page_on_worker,
                    schema_version=self._target.expected_schema_version,
                ),
                self._open_connection(),
                self.policy,
                request,
            )
            return await _await_submitted_worker(future)

    async def close(self) -> None:
        async with self._gate:
            if self._connection is None:
                if self._close_error is not None:
                    raise self._close_error
                return
            try:
                future = asyncio.get_running_loop().run_in_executor(
                    self._executor, _close_reader_on_worker, self._connection
                )
                await _await_reader_close(future)
            except JournalFailure as error:
                self._close_error = error
                raise
            finally:
                self._connection = None
                self._executor.shutdown(wait=True, cancel_futures=True)
