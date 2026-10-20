"""012 T020: real rolling journals, exact charges, counters and timestamp scopes.

SQL counter faults below are explicit test-only exhausted metadata, restored
before teardown; they are not asserted to be ordinary valid retained histories.
All matching/ordering/admission and retention behavior is the real implementation.
"""

import base64
import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from dutchmate_core import annotation, evidence, model, monitor
from dutchmate_core.adapters import sqlite_evidence as sqlite
from tests.contract.test_interact_recording import POLICY, recording_case
from tests.contract.test_interact_runtime import RuntimeCase, runtime_case
from tests.contract.test_monitor_recording import _await
from tests.contract.test_sqlite_evidence_journal import _database_state
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixtureFactory
from tests.integration.test_annotations import assert_single_rx_owner

MAX = 9223372036854775807
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced-shaped"]
    ),
]


@asynccontextmanager
async def _live(
    tmp: Path,
    patch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    policy: model.SessionPolicy,
) -> AsyncIterator[RuntimeCase]:
    path = tmp / "runtime.db"
    journal = await sqlite.SqliteEvidenceJournal.create_v4(path, policy)
    case = RuntimeCase(journal, factory, patch, path=path)
    case.profile = replace(case.profile, session_policy=policy)
    try:
        await case.attach()
        yield case
    finally:
        await case.finish()


def _oracle_charge(draft: Any) -> int:
    """Independent §5 key/BLOB mapping and003 byte formula, not the v4 codec."""
    if isinstance(draft, evidence.PendingInteractStartedEvidence):
        kind = "interact_started"
        # Only the existing003 provenance spelling is reused; all new fields,
        # canonical bytes and charges are calculated independently below.
        old = sqlite.encode_evidence_record_v3(
            model.SegmentStartedEvidence(0, draft.provenance)
        )
        metadata = dict(
            operation_id=draft.operation_id,
            provenance=json.loads(old.metadata_json),
            profile_version=2,
            authorization={"uart_tx_enabled": True},
            conditions_base64=[base64.b64encode(c).decode() for c in draft.conditions],
            timeout_ms=draft.timeout_ms,
            max_rx_bytes=draft.max_rx_bytes,
            write_timeout_ms=1000,
            clock_origin_id=draft.clock_origin_id,
        )
        blob = draft.payload
    elif isinstance(draft, evidence.PendingUartTxSettledEvidence):
        kind = "uart_tx_settled"
        metadata = {
            "operation_id": draft.operation_id,
            "start_sequence": draft.start_sequence,
            **asdict(draft.tx),
        }
        blob = b""
    else:
        assert isinstance(draft, evidence.PendingInteractEndedEvidence)
        kind = "interact_ended"
        metadata = dict(
            operation_id=draft.operation_id,
            start_sequence=draft.start_sequence,
            tx_settled_sequence=draft.tx_settled_sequence,
            tx=asdict(draft.tx),
            tx_audit_failure=None
            if draft.tx_audit_failure is None
            else asdict(draft.tx_audit_failure),
            outcome=draft.outcome.value,
            observation=asdict(draft.observation),
        )
        blob = b""
    raw = json.dumps(
        metadata,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return 16 + len(kind.encode()) + len(raw) + len(blob)


@pytest.mark.parametrize("payload_length", [1, 4096])
@pytest.mark.parametrize("condition_count", [1, 4])
@pytest.mark.parametrize("condition_length", [1, 256])
async def test_actual_preflight_shapes_have_exact_independent_charges_and_no_unreachable_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    payload_length: int,
    condition_count: int,
    condition_length: int,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        await c.rx(b"ambient before preflight", 1)
        request = c.request(
            payload=(bytes(range(256)) * 16)[:payload_length],
            conditions=tuple(
                bytes([n]) * condition_length for n in range(condition_count)
            ),
            timeout_ms=4000,
            max_rx_bytes=1,
        )
        provenance = c.coordinator.current_provenance
        assert provenance is not None
        observed: list[tuple[int, int, int]] = []

        def charge(start: Any, txs: Any, ends: Any) -> tuple[int, int, int]:
            expected = (
                _oracle_charge(start),
                max(map(_oracle_charge, txs)),
                max(map(_oracle_charge, ends)),
            )
            assert sqlite.charge_interact_markers(start, txs, ends) == expected
            assert (
                start.payload == request.payload
                and start.conditions == request.conditions
            )
            assert all(d.observation.outcome.value != "matched" for d in ends) == (
                condition_length > 1
            )
            assert {str(d.tx.status) for d in txs} == {
                "not_submitted",
                "acknowledged",
                "partial",
                "timeout",
                "disconnected",
                "failure",
            }
            assert any(d.tx_settled_sequence is None for d in ends)
            observed.append(expected)
            return expected

        c.coordinator.preflight_interact(request, provenance, charge)
        assert len(observed) == 1 and c.writer.calls == []
        assert "interact_started" not in c.recorder.attempts
        assert_single_rx_owner(c.fixture)


@pytest.mark.parametrize("delta", [-1, 0])
async def test_minimum_exact_charge_policy_has_no_extra_floor_or_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    delta: int,
) -> None:
    sizing, actual = tmp_path / "sizing", tmp_path / "actual"
    sizing.mkdir()
    actual.mkdir()
    async with recording_case(sizing, monkeypatch, factory) as c:
        captured: list[int] = []

        def charge(start: Any, txs: Any, ends: Any) -> tuple[int, int, int]:
            values = (
                _oracle_charge(start),
                max(map(_oracle_charge, txs)),
                max(map(_oracle_charge, ends)),
            )
            assert values == sqlite.charge_interact_markers(start, txs, ends)
            captured.extend(values)
            return values

        provenance = c.coordinator.current_provenance
        assert provenance is not None
        c.coordinator.preflight_interact(
            c.request(payload=b"x", conditions=(b"P",), timeout_ms=1, max_rx_bytes=1),
            provenance,
            charge,
        )
        minimum = max(captured)
    policy = replace(
        POLICY,
        max_retained_records=1,
        max_retrieval_page_records=1,
        max_record_charged_bytes=minimum + delta,
        max_retained_charged_bytes=minimum + delta,
        max_retrieval_page_charged_bytes=minimum + delta,
    )
    async with _live(actual, monkeypatch, factory, policy) as c:
        request = c.request(
            payload=b"x", conditions=(b"P",), timeout_ms=1, max_rx_bytes=1
        )
        if delta < 0:
            await c.rejected("evidence_policy_incompatible", request)
        else:
            task = await c.begin(request)
            await c.rx(b"P\0trailing", 11)
            c.writer.allow.set()
            report = await _await(task)
            assert (
                report.outcome.value == "matched"
                and report.tx.accepted_prefix_bytes == 1
            )
            assert report.durability == "complete" and report.audit_failures == ()
            assert (
                report.started_record is not None
                and report.tx_settled_record is not None
                and report.ended_record is not None
            )
            # Each ACK is positive, yet the one-record policy has already evicted
            # the earlier markers. Complete never promises simultaneous retention.
            for ref in (report.started_record, report.tx_settled_record):
                assert (
                    await c.owner.read_record(ref)
                ).page.outcome is evidence.EvidencePageOutcome.EXPIRED
            assert (await c.owner.read_record(report.ended_record)).page.records[
                0
            ].sequence == report.ended_record.sequence
            assert c.journal.policy == policy
        assert_single_rx_owner(c.fixture)


async def test_evicted_rx_prefix_and_intent_still_support_matching_across_concurrent_claims(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    policy = replace(POLICY, max_retained_records=1)
    async with _live(tmp_path, monkeypatch, factory, policy) as c:
        task = await c.begin()
        monitored = c.spawn(
            c.owner.monitor(
                monitor.MonitorRequest(c.journal.session_id, b"M", 1000, 1024)
            )
        )
        await _await(c.recorder.acks["operation_started"].get())
        first = await c.rx(b"PA", 11)
        accepted = await c.owner.annotate(
            annotation.AnnotationRequest(
                c.journal.session_id, "SSM is a client assertion", "cli"
            )
        )
        expired = await c.owner.read_record(
            model.EvidenceReference(c.journal.session_id, first.sequence)
        )
        assert expired.page.outcome is evidence.EvidencePageOutcome.EXPIRED
        assert not task.done() and not monitored.done() and c.writer.active == 1
        last = await c.rx(b"SSM", 12)
        assert (await _await(monitored)).examined_rx_bytes == 5
        c.writer.allow.set()
        report = await _await(task)
        assert report.observation.match == model.InteractMatch(
            0,
            model.MonitorMatchStart(first.sequence, 0),
            model.MonitorMatchEnd(last.sequence, 2),
        )
        assert (
            report.observation.examined_rx_bytes == 4
            and report.durability == "complete"
        )
        assert report.tx_settled_record is not None and report.ended_record is not None
        for reference in (
            report.started_record,
            report.tx_settled_record,
            accepted.reference,
        ):
            result = await c.owner.read_record(reference)
            assert result.page.outcome is evidence.EvidencePageOutcome.EXPIRED
            assert result.page.records == ()
        live = await c.owner.read_record(report.ended_record)
        ended = live.page.records[0]
        assert (
            isinstance(ended, model.InteractEndedEvidence)
            and ended.tx.accepted_prefix_bytes == 6
        )
        assert_single_rx_owner(c.fixture)


async def test_tx_payload_and_host_times_never_inflate_rx_loss_or_backend_timestamp_endpoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    path = tmp_path / "recording.db"
    policy = replace(POLICY, max_retained_records=2)
    expected_charges: dict[int, int] = {}
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as c:
        with closing(sqlite3.connect(path)) as connection:
            expected_charges.update(
                connection.execute(
                    "SELECT sequence,16+length(CAST(record_kind AS BLOB))+length(metadata_json)+coalesce(length(payload),0) FROM evidence_records"
                ).fetchall()
            )
        original = c.journal.append

        async def observed(draft: Any) -> Any:
            record = await original(draft)
            with closing(sqlite3.connect(path)) as connection:
                row = connection.execute(
                    "SELECT record_kind,metadata_json,payload,charged_bytes,rx_payload_bytes,timestamp_endpoint_json FROM evidence_records WHERE sequence=?",
                    (record.sequence,),
                ).fetchone()
            kind, metadata, blob, charged, rx, timestamp = row
            expected_charges[record.sequence] = (
                16 + len(kind.encode()) + len(metadata) + len(blob or b"")
            )
            assert charged == expected_charges[record.sequence]
            if kind in {"interact_started", "uart_tx_settled", "interact_ended"}:
                assert rx == 0 and timestamp is None
            return record

        monkeypatch.setattr(c.journal, "append", observed)
        operation = await c.start(c.request(payload=bytes(range(256)) * 16))
        first = await c.rx(b"PA", 11)
        last = await c.rx(b"SS\xff", 12)
        c.clock.advance(MAX)
        c.writer.allow.set()
        report = await _await(operation.wait())
        assert (
            report.tx.settled_at_ns == MAX
            and report.observation.clock.decided_at_ns == 100
        )
        assert report.observation.clock.origin_id != first.observed_at.domain_id
        page = await c.journal.retrieve(
            evidence.EvidenceRetrievalRequest(c.journal.session_id, 100, 131072)
        )
        marker = page.retention_marker
        assert marker is not None and marker.expired_range == model.SequenceRange(0, 4)
        assert (
            marker.discarded_record_count == 4
            and marker.discarded_rx_payload_byte_count == 5
        )
        assert marker.discarded_charged_bytes == sum(
            expected_charges[n] for n in range(4)
        )
        assert (
            marker.first_discarded_timestamp is not None
            and marker.last_discarded_timestamp is not None
        )
        assert marker.first_discarded_timestamp.timestamp == first.observed_at
        assert marker.last_discarded_timestamp.timestamp == last.observed_at
        assert (
            marker.first_discarded_timestamp.domain
            == report.provenance.backend_observation_timestamp_domain
        )
        assert (
            marker.last_discarded_timestamp.domain
            == report.provenance.backend_observation_timestamp_domain
        )
        assert report.tx.accepted_prefix_bytes == 4096
        session = c.journal.session_id
    reopened = await sqlite.SqliteEvidenceJournal.open_v4(
        path, expected_session_id=session
    )
    try:
        page = await reopened.retrieve(
            evidence.EvidenceRetrievalRequest(session, 100, 131072)
        )
        assert (
            page.retention_marker is not None
            and page.retention_marker.discarded_rx_payload_byte_count == 5
        )
        assert (
            page.retention_marker.last_discarded_timestamp
            == marker.last_discarded_timestamp
        )
    finally:
        await reopened.close()


@pytest.mark.parametrize("survivor", ["intent", "tx", "end"])
async def test_reopen_accepts_real_unpaired_markers_without_inventing_evicted_or_unacknowledged_pairs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    survivor: str,
) -> None:
    policy = replace(POLICY, max_retained_records=2)
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as c:
        wanted: (
            type[model.InteractStartedEvidence]
            | type[model.UartTxSettledEvidence]
            | type[model.InteractEndedEvidence]
        )
        if survivor == "intent":
            c.recorder.fail_ack.add("interact_started")
            with pytest.raises(evidence.JournalFailure):
                await c.start()
            assert c.writer.calls == []
            wanted = model.InteractStartedEvidence
        else:
            if survivor == "tx":
                c.recorder.fail_before.add("interact_ended")
            operation = await c.start()
            await c.rx(b"PASS", 11)
            c.writer.allow.set()
            report = await _await(operation.wait())
            assert report.tx_settled_record is not None
            assert (report.ended_record is None) == (survivor == "tx")
            wanted = (
                model.UartTxSettledEvidence
                if survivor == "tx"
                else model.InteractEndedEvidence
            )
        session = c.journal.session_id
    reopened = await sqlite.SqliteEvidenceJournal.open_v4(
        tmp_path / "recording.db", expected_session_id=session
    )
    try:
        page = await reopened.retrieve(
            evidence.EvidenceRetrievalRequest(session, 100, 131072)
        )
        assert len(page.records) == 2 and isinstance(page.records[0], wanted)
        assert isinstance(page.records[1], model.SegmentEndedEvidence)
        assert page.retention_marker is not None
        if survivor != "intent":
            assert not any(
                isinstance(r, model.InteractStartedEvidence) for r in page.records
            )
    finally:
        await reopened.close()


@pytest.mark.parametrize("fault", ["ack-count", "partial-count", "origin", "operation"])
async def test_bad_retained_tx_pair_rolls_back_without_eviction_or_sequence_consumption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    fault: str,
) -> None:
    policy = replace(POLICY, max_retained_records=3)
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as c:
        operation = await c.start()
        rx = await c.rx(b"PASS", 11)
        start = next(
            r for r in await c.records() if isinstance(r, model.InteractStartedEvidence)
        )
        tx = model.RecordedTxFacts(
            True,
            "partial" if fault == "partial-count" else "acknowledged",
            5 if fault == "ack-count" else 6,
            None,
            "backend_acceptance",
            "11111111-1111-4111-8111-111111111111"
            if fault == "origin"
            else c.clock.origin_id,
            100,
        )
        draft = evidence.PendingUartTxSettledEvidence(
            "11111111-1111-4111-8111-111111111111"
            if fault == "operation"
            else start.operation_id,
            start.sequence,
            tx,
        )
        before = _database_state(tmp_path / "recording.db")
        with pytest.raises(evidence.JournalFailure) as caught:
            await c.journal.append(draft)
        assert caught.value.kind is evidence.JournalFailureKind.INVARIANT_VIOLATION
        assert _database_state(tmp_path / "recording.db") == before
        assert not c.writer.finished.is_set()
        c.writer.allow.set()
        report = await _await(operation.wait())
        assert (
            report.tx_settled_record is not None
            and report.tx_settled_record.sequence == rx.sequence + 1
        )
        assert report.tx.accepted_prefix_bytes == 6


async def test_charged_byte_ceiling_alone_evicts_the_minimum_prefix_and_never_counts_tx_as_rx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    sizing, actual = tmp_path / "sizing", tmp_path / "actual"
    sizing.mkdir()
    actual.mkdir()
    payload = bytes(range(256)) * 16
    async with recording_case(sizing, monkeypatch, factory) as c:
        maxima: list[int] = []

        def charge(start: Any, txs: Any, ends: Any) -> tuple[int, int, int]:
            charges = (
                _oracle_charge(start),
                max(map(_oracle_charge, txs)),
                max(map(_oracle_charge, ends)),
            )
            maxima.extend(charges)
            assert charges == sqlite.charge_interact_markers(start, txs, ends)
            return charges

        operation = await c.start(c.request(payload=payload), charge_markers=charge)
        await c.rx(b"PASS\0trailing", 11)
        c.writer.allow.set()
        await _await(operation.wait())
        with closing(sqlite3.connect(sizing / "recording.db")) as connection:
            charges = dict(
                connection.execute(
                    "SELECT sequence,16+length(CAST(record_kind AS BLOB))+length(metadata_json)+coalesce(length(payload),0) FROM evidence_records ORDER BY sequence"
                ).fetchall()
            )
    ceiling = max(maxima)
    assert sum(charges.values()) > ceiling
    first_retained = next(
        n for n in charges if sum(v for k, v in charges.items() if k >= n) <= ceiling
    )
    assert first_retained > 0
    policy = replace(
        POLICY, max_record_charged_bytes=ceiling, max_retained_charged_bytes=ceiling
    )
    async with recording_case(actual, monkeypatch, factory, policy=policy) as c:
        operation = await c.start(c.request(payload=payload))
        await c.rx(b"PASS\0trailing", 11)
        c.writer.allow.set()
        report = await _await(operation.wait())
        page = await c.journal.retrieve(
            evidence.EvidenceRetrievalRequest(c.journal.session_id, 100, 131072)
        )
        assert (
            report.durability == "complete" and report.tx.accepted_prefix_bytes == 4096
        )
        assert [r.sequence for r in page.records] == list(range(first_retained, 5))
        marker = page.retention_marker
        assert marker is not None and marker.expired_range == model.SequenceRange(
            0, first_retained
        )
        assert marker.discarded_charged_bytes == sum(
            v for k, v in charges.items() if k < first_retained
        )
        assert marker.discarded_rx_payload_byte_count == (
            13 if first_retained > 2 else 0
        )
        with closing(sqlite3.connect(actual / "recording.db")) as connection:
            count, retained = connection.execute(
                "SELECT retained_record_count,retained_charged_bytes FROM session_metadata"
            ).fetchone()
        assert count < 100 and retained == sum(
            v for k, v in charges.items() if k >= first_retained
        )
        assert retained <= ceiling < retained + charges[first_retained - 1]
        assert c.journal.policy == policy


@pytest.mark.parametrize("timeout_ms", [1, 4000])
@pytest.mark.parametrize("overflow", [False, True])
async def test_deadline_at_max_is_legal_and_one_nanosecond_over_rejects_before_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    timeout_ms: int,
    overflow: bool,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as c:
        c.clock.advance(MAX - timeout_ms * 1000000 + int(overflow))
        request = c.request(timeout_ms=timeout_ms)
        if overflow:
            await c.rejected("interact_unavailable", request)
        else:
            task = await c.begin(request)
            await c.rx(b"PASS", 11)
            c.writer.allow.set()
            report = await _await(task)
            assert report.observation.clock.deadline_at_ns == MAX
            assert report.tx.settled_at_ns == MAX - timeout_ms * 1000000
            assert report.outcome.value == "matched" and report.durability == "complete"


@pytest.mark.parametrize(
    "field,code",
    [
        ("next_sequence", evidence.JournalFailureKind.SEQUENCE_EXHAUSTED),
        ("retained_charged_bytes", evidence.JournalFailureKind.COUNTER_EXHAUSTED),
    ],
)
@pytest.mark.parametrize("phase", ["intent", "tx", "end"])
async def test_real_counter_exhaustion_has_no_reservation_or_invented_audit_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    field: str,
    code: evidence.JournalFailureKind,
    phase: str,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as c:
        path = tmp_path / "recording.db"
        saved: list[int] = []

        def exhaust() -> None:
            # Whitelisted column, test-owned file. Deliberately inject exhausted
            # metadata as003's boundary tests do, then restore it before close.
            with closing(sqlite3.connect(path)) as connection:
                saved.append(
                    connection.execute(
                        f"SELECT {field} FROM session_metadata"
                    ).fetchone()[0]
                )
                connection.execute(f"UPDATE session_metadata SET {field}=?", (MAX,))
                connection.commit()

        try:
            if phase == "intent":
                exhaust()
                with pytest.raises(evidence.JournalFailure) as caught:
                    await c.start()
                assert caught.value.kind is code and c.writer.calls == []
                assert "uart_tx_settled" not in c.recorder.attempts
            else:
                operation = await c.start()
                await c.rx(b"PASS", 11)
                if phase == "tx":
                    exhaust()
                else:
                    c.recorder.after_ack["uart_tx_settled"] = exhaust
                c.writer.allow.set()
                report = await _await(operation.wait())
                assert (
                    report.tx.accepted_prefix_bytes == 6
                    and report.outcome.value == "matched"
                )
                assert c.writer.calls == [b"\0\xffSEND"]
                assert report.ended_record is None
                assert (report.tx_settled_record is None) == (phase == "tx")
                assert report.durability == (
                    "both_unconfirmed" if phase == "tx" else "end_unconfirmed"
                )
                assert [f.code for f in report.audit_failures] == [code.value] * (
                    2 if phase == "tx" else 1
                )
                assert (
                    c.recorder.attempts.count("uart_tx_settled")
                    == c.recorder.attempts.count("interact_ended")
                    == 1
                )
        finally:
            if saved:
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute(
                        f"UPDATE session_metadata SET {field}=?", (saved[0],)
                    )
                    connection.commit()
        assert_single_rx_owner(c.fixture)
