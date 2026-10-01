"""Child-process commands for durable SQLite recovery contract tests."""

import argparse
import asyncio
import os
import sqlite3
import threading
from enum import StrEnum
from pathlib import Path
from typing import cast

from dutchmate_core import evidence, model
from dutchmate_core.adapters import sqlite_evidence


class _CommitBarrier(StrEnum):
    BEFORE = "before"
    AFTER = "after"


class _BarrierConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        signal_path: Path,
    ) -> None:
        self._connection = connection
        self._signal_path = signal_path
        self._barrier: _CommitBarrier | None = None
        self._never_release = threading.Event()

    def arm(self, barrier: _CommitBarrier) -> None:
        self._barrier = barrier

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> sqlite3.Cursor:
        if sql.strip().upper() != "COMMIT":
            return self._connection.execute(sql, parameters)
        self._block_if_armed(_CommitBarrier.BEFORE)
        cursor = self._connection.execute(sql, parameters)
        self._block_if_armed(_CommitBarrier.AFTER)
        return cursor

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        return self._connection.executescript(sql_script)

    def commit(self) -> None:
        self._block_if_armed(_CommitBarrier.BEFORE)
        self._connection.commit()
        self._block_if_armed(_CommitBarrier.AFTER)

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)

    def _block_if_armed(self, barrier: _CommitBarrier) -> None:
        if self._barrier is not barrier:
            return
        self._barrier = None
        _publish_signal(self._signal_path, barrier.value)
        self._never_release.wait()


def _policy() -> model.SessionPolicy:
    return model.SessionPolicy(
        max_retained_records=100,
        max_retained_charged_bytes=100_000,
        max_record_charged_bytes=10_000,
        max_database_pages=64,
        max_retrieval_page_records=20,
        max_retrieval_page_charged_bytes=20_000,
    )


def _draft(payload: bytes) -> evidence.PendingRxBytesEvidence:
    return evidence.PendingRxBytesEvidence(
        connection_id=model.ConnectionInstanceId("recovery-connection"),
        segment_id=model.SegmentId("recovery-segment"),
        payload=payload,
        observed_at=model.BackendObservationTimestamp("recovery-clock", 7),
    )


def _publish_signal(path: Path, value: str) -> None:
    pending = path.with_suffix(f"{path.suffix}.pending")
    pending.write_text(value, encoding="utf-8")
    pending.replace(path)


async def _create_empty(path: Path) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    await journal.close()


async def _exit_after_acknowledgment(
    path: Path,
    signal_path: Path,
    payload: bytes,
) -> None:
    journal = await sqlite_evidence.SqliteEvidenceJournal.create(path, _policy())
    accepted = await journal.append(_draft(payload))
    _publish_signal(signal_path, str(accepted.sequence))
    os._exit(0)


async def _block_append_at_commit(
    path: Path,
    signal_path: Path,
    payload: bytes,
    barrier: _CommitBarrier,
) -> None:
    await _create_empty(path)
    real_connect = sqlite_evidence._connect_sqlite
    connections: list[_BarrierConnection] = []

    def barrier_connect(
        database: str,
        *,
        uri: bool = False,
    ) -> sqlite3.Connection:
        wrapped = _BarrierConnection(real_connect(database, uri=uri), signal_path)
        connections.append(wrapped)
        return cast("sqlite3.Connection", wrapped)

    sqlite_evidence._connect_sqlite = barrier_connect
    journal = await sqlite_evidence.SqliteEvidenceJournal.open(path)
    connections[0].arm(barrier)
    await journal.append(_draft(payload))
    raise AssertionError("append returned instead of waiting at the commit barrier")


async def _leave_hot_journal_before_invalid_application(
    path: Path,
    signal_path: Path,
) -> None:
    await _create_empty(path)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA application_id = 1")
    connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    connection.execute(
        "UPDATE session_metadata SET session_id = 'uncommitted-session'"
    )
    _publish_signal(signal_path, "hot")
    threading.Event().wait()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "exit-after-acknowledgment",
            "interrupt-before-commit",
            "interrupt-after-commit-before-return",
            "hot-journal-before-invalid-application",
        ),
    )
    parser.add_argument("journal", type=Path)
    parser.add_argument("signal", type=Path)
    parser.add_argument("payload_hex")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    payload = bytes.fromhex(cast("str", args.payload_hex))
    path = cast("Path", args.journal)
    signal_path = cast("Path", args.signal)
    match cast("str", args.command):
        case "exit-after-acknowledgment":
            await _exit_after_acknowledgment(path, signal_path, payload)
        case "interrupt-before-commit":
            await _block_append_at_commit(
                path,
                signal_path,
                payload,
                _CommitBarrier.BEFORE,
            )
        case "interrupt-after-commit-before-return":
            await _block_append_at_commit(
                path,
                signal_path,
                payload,
                _CommitBarrier.AFTER,
            )
        case "hot-journal-before-invalid-application":
            await _leave_hot_journal_before_invalid_application(
                path,
                signal_path,
            )
        case unreachable:
            raise AssertionError(f"unsupported worker command: {unreachable}")


if __name__ == "__main__":
    asyncio.run(_run(_parse_args()))
