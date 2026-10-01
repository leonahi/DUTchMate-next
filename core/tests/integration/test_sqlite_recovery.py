"""Subprocess recovery contracts for the durable SQLite evidence journal."""

import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from dutchmate_core import evidence
from dutchmate_core.adapters import sqlite_evidence

_WORKER = Path(__file__).parent / "fixtures" / "sqlite_recovery_worker.py"
_PAYLOAD = b"\x00durable-after-crash\xff"

type _RecoveredState = tuple[
    int,
    int,
    int,
    tuple[tuple[int, str, bytes | None], ...],
    int,
]

_PREVIOUS_STATE: _RecoveredState = (0, 0, 0, (), 0)
_COMPLETE_STATE: _RecoveredState = (
    1,
    0,
    1,
    ((0, "rx_bytes", _PAYLOAD),),
    0,
)


def _worker_command(
    command: str,
    journal: Path,
    signal: Path,
) -> list[str]:
    return [
        sys.executable,
        str(_WORKER),
        command,
        str(journal),
        str(signal),
        _PAYLOAD.hex(),
    ]


def _wait_for_barrier(process: subprocess.Popen[str], signal: Path) -> str:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if signal.exists():
            return signal.read_text(encoding="utf-8")
        if process.poll() is not None:
            _, stderr = process.communicate()
            pytest.fail(
                "recovery worker exited before reaching its barrier: "
                f"{stderr.strip()}"
            )
        time.sleep(0.01)
    process.kill()
    _, stderr = process.communicate(timeout=5)
    pytest.fail(f"recovery worker did not reach its barrier: {stderr.strip()}")


def _kill_at_barrier(
    command: str,
    journal: Path,
    signal: Path,
) -> str:
    process = subprocess.Popen(
        _worker_command(command, journal, signal),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        observed_barrier = _wait_for_barrier(process, signal)
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
    return observed_barrier


def _read_recovered_state(journal: Path) -> _RecoveredState:
    connection = sqlite3.connect(journal)
    try:
        metadata = connection.execute(
            """
            SELECT next_sequence, low_water_sequence, retained_record_count
            FROM session_metadata WHERE singleton = 1
            """
        ).fetchone()
        rows = connection.execute(
            """
            SELECT sequence, record_kind, payload
            FROM evidence_records ORDER BY sequence
            """
        ).fetchall()
        marker_count = connection.execute(
            "SELECT COUNT(*) FROM retention_marker"
        ).fetchone()[0]
    finally:
        connection.close()
    assert metadata is not None
    return (
        int(metadata[0]),
        int(metadata[1]),
        int(metadata[2]),
        tuple((int(row[0]), str(row[1]), row[2]) for row in rows),
        int(marker_count),
    )


async def _recover(journal: Path) -> _RecoveredState:
    opened = await sqlite_evidence.SqliteEvidenceJournal.open(journal)
    await opened.close()
    state = _read_recovered_state(journal)
    assert state in (_PREVIOUS_STATE, _COMPLETE_STATE)
    return state


@pytest.mark.asyncio
async def test_abrupt_exit_after_acknowledgment_recovers_complete_append(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "acknowledged.sqlite3"
    signal = tmp_path / "acknowledged.signal"

    completed = subprocess.run(
        _worker_command("exit-after-acknowledgment", journal, signal),
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert signal.read_text(encoding="utf-8") == "0"
    assert await _recover(journal) == _COMPLETE_STATE


@pytest.mark.asyncio
async def test_interruption_before_commit_recovers_only_previous_state(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "before-commit.sqlite3"
    signal = tmp_path / "before-commit.signal"

    observed = _kill_at_barrier(
        "interrupt-before-commit",
        journal,
        signal,
    )

    assert observed == "before"
    assert await _recover(journal) == _PREVIOUS_STATE


@pytest.mark.asyncio
async def test_commit_before_return_ambiguity_recovers_complete_transaction(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "after-commit.sqlite3"
    signal = tmp_path / "after-commit.signal"

    observed = _kill_at_barrier(
        "interrupt-after-commit-before-return",
        journal,
        signal,
    )

    assert observed == "after"
    assert await _recover(journal) == _COMPLETE_STATE


@pytest.mark.asyncio
async def test_rollback_recovery_precedes_incompatible_application_validation(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "recovery-before-validation.sqlite3"
    signal = tmp_path / "recovery-before-validation.signal"

    observed = _kill_at_barrier(
        "hot-journal-before-invalid-application",
        journal,
        signal,
    )
    rollback_journal = journal.with_name(f"{journal.name}-journal")
    assert observed == "hot"
    assert rollback_journal.exists()

    with pytest.raises(evidence.JournalFailure) as first_failure:
        await sqlite_evidence.SqliteEvidenceJournal.open(journal)

    assert first_failure.value.operation is evidence.JournalOperation.OPEN
    assert first_failure.value.kind is (
        evidence.JournalFailureKind.INCOMPATIBLE_APPLICATION
    )
    assert not rollback_journal.exists()
    connection = sqlite3.connect(journal)
    try:
        application_id = connection.execute("PRAGMA application_id").fetchone()
        session_id = connection.execute(
            "SELECT session_id FROM session_metadata WHERE singleton = 1"
        ).fetchone()
    finally:
        connection.close()
    assert application_id == (1,)
    assert session_id is not None
    assert session_id != ("uncommitted-session",)

    recovered_invalid_source = journal.read_bytes()
    with pytest.raises(evidence.JournalFailure) as second_failure:
        await sqlite_evidence.SqliteEvidenceJournal.open(journal)

    assert second_failure.value.operation is evidence.JournalOperation.OPEN
    assert second_failure.value.kind is (
        evidence.JournalFailureKind.INCOMPATIBLE_APPLICATION
    )
    assert journal.read_bytes() == recovered_invalid_source
