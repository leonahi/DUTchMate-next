"""011 T014: real-v3 Follow retention/page boundaries, with both backend shapes.

Only test-owned SQLite observations, existing submission/ACK gates and backend
fixtures are used. Expected ranges/counts come from explicit append sequences;
charge expectations use003's stored-component formula, not its codec helpers.
The final two tests inject exhausted-counter / malformed-read faults explicitly;
they do not claim those faults are ordinary retained journal histories.
"""

import asyncio
import sqlite3
import threading
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

import pytest

from dutchmate_core import evidence, follow, model
from dutchmate_core.adapters import sqlite_evidence as sqlite
from tests.contract.test_follow_recording import (
    POLICY,
    ReadProbe,
    RecordingCase,
    batch,
    recording_case,
)
from tests.contract.test_follow_runtime import case as runtime_case
from tests.contract.test_monitor_recording import _await, _turn
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixtureFactory
from tests.integration.test_annotations import assert_single_rx_owner

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
    ),
]


def charges(tmp_path: Path) -> dict[int, int]:
    """Read immutable stored components; independently apply003's quota formula."""
    with closing(sqlite3.connect(tmp_path / "follow-v3.db")) as connection:
        return dict(
            connection.execute(
                """
                SELECT sequence, 16 + length(CAST(record_kind AS BLOB))
                     + length(metadata_json) + coalesce(length(payload), 0)
                FROM evidence_records ORDER BY sequence
                """
            ).fetchall()
        )


async def ordinary(case: RecordingCase, start: int, end: int) -> evidence.EvidencePage:
    return await case.reads.original(
        evidence.EvidenceRetrievalRequest(
            model.EvidenceRangeReference(case.journal.session_id, start, end),
            case.journal.policy.max_retrieval_page_records,
            case.journal.policy.max_retrieval_page_charged_bytes,
        )
    )


def assert_gap(
    result: follow.FollowBatch,
    missed: tuple[int, int],
    prefix: int,
    page: evidence.EvidencePage,
) -> model.RetentionMarker:
    assert result.gap is not None
    assert result.gap.missed_range == model.SequenceRange(*missed)
    marker = result.gap.retention_marker
    assert marker == page.retention_marker
    assert marker.expired_range == model.SequenceRange(0, prefix)
    assert marker.discarded_record_count == prefix
    return marker


@pytest.mark.parametrize("page_records", [1, 31, 32, 33])
async def test_record_ceiling_edges_drain_without_replaying_or_holding_a_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    page_records: int,
) -> None:
    policy = replace(POLICY, max_retrieval_page_records=page_records)
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as case:
        subscription = await case.start_follow()
        records = tuple([await case.emit(bytes([n]), n) for n in range(35)])
        received: list[model.EvidenceRecord] = []
        while len(received) < 35:
            result = await batch(subscription)
            assert result.gap is None
            count = min(32, page_records, 35 - len(received))
            assert result.records == records[len(received) : len(received) + count]
            received.extend(result.records)
        assert tuple(received) == records
        pages = [r for r in case.reads.requests if not ReadProbe.is_head(r)]
        assert all(r.max_records == min(32, page_records) for r in pages)
        assert all(r.cursor is None for r in pages)
        assert all(isinstance(r.reference, model.EvidenceRangeReference) for r in pages)
        assert [
            r.reference.start_inclusive
            for r in pages
            if isinstance(r.reference, model.EvidenceRangeReference)
        ] == list(range(1, 36, min(32, page_records)))
        assert_single_rx_owner(case.fixture)


async def test_minimum_active_policy_accepts_follow_without_a_larger_charge_or_count_floor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    # The smallest usable record/retained/page charge must admit the backend's
    # actual current segment descriptor. Measure its003 component lengths on a
    # separate real journal; regenerated IDs have the same fixed byte widths.
    sizing, minimum = tmp_path / "sizing", tmp_path / "minimum"
    sizing.mkdir()
    minimum.mkdir()
    async with recording_case(sizing, monkeypatch, factory):
        segment_charge = charges(sizing)[0]
        with closing(sqlite3.connect(sizing / "follow-v3.db")) as connection:
            database_pages = connection.execute("PRAGMA page_count").fetchone()[0]
    policy = model.SessionPolicy(
        1, segment_charge, segment_charge, database_pages, 1, segment_charge
    )
    async with recording_case(minimum, monkeypatch, factory, policy=policy) as case:
        assert charges(minimum) == {0: segment_charge}
        subscription = await case.start_follow()
        assert subscription.start.start_sequence == 1
        rx = await case.emit(b"\0\xff", 0)
        result = await batch(subscription)
        # The segment descriptor expired, but predates this subscriber's start.
        assert result.gap is None and result.records == (rx,)
        stored = await ordinary(case, 0, 2)
        assert stored.expired_range == model.SequenceRange(0, 1)
        assert stored.retention_marker is not None
        assert stored.retention_marker.discarded_charged_bytes == segment_charge
        assert case.journal.policy == policy
        assert all(
            r.max_records == 1 and r.max_charged_bytes == segment_charge
            for r in case.reads.requests
        )
        assert_single_rx_owner(case.fixture)


@pytest.mark.parametrize("page_bytes", [8192, 1_048_575, 1_048_576, 1_048_577])
async def test_exact_single_record_charge_fits_policy_or_fixed_cap_then_stops_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    page_bytes: int,
) -> None:
    policy = replace(
        POLICY,
        max_record_charged_bytes=page_bytes,
        max_retrieval_page_charged_bytes=page_bytes,
    )
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as case:
        sample = await case.emit(b"x", 0)
        overhead = charges(tmp_path)[sample.sequence] - 1
        subscription = await case.start_follow()
        cap = min(page_bytes, 1_048_576)
        exact = await case.emit(b"\0" * (cap - overhead), 0)
        later = await case.emit(b"\xff", 0)
        result = await batch(subscription)
        assert result.gap is None and result.records == (exact,)
        request, page = case.reads.completed[-1]
        assert request.max_charged_bytes == cap
        assert page.charged_bytes == cap and page.truncated
        assert page.continuation is not None
        assert page.continuation.next_sequence == exact.sequence + 1
        assert (await batch(subscription)).records == (later,)


@pytest.mark.parametrize("delta", [-1, 0, 1])
async def test_total_page_charge_at_fixed_cap_is_inclusive_without_splitting_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    delta: int,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        sample = await case.emit(b"x", 0)
        overhead = charges(tmp_path)[sample.sequence] - 1
        subscription = await case.start_follow()
        first = await case.emit(b"a" * (524_288 - overhead), 0)
        second = await case.emit(b"b" * (524_288 + delta - overhead), 0)
        result = await batch(subscription)
        assert result.gap is None
        _, page = case.reads.completed[-1]
        if delta <= 0:
            assert result.records == (first, second)
            assert page.charged_bytes == 1_048_576 + delta
            assert not page.truncated
        else:
            assert result.records == (first,)
            assert page.charged_bytes == 524_288 and page.truncated
            assert (await batch(subscription)).records == (second,)


@pytest.mark.parametrize("preceding_gap", [False, True])
async def test_oversized_first_eligible_record_terminates_without_spin_skip_or_policy_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    preceding_gap: bool,
) -> None:
    policy = replace(POLICY, max_retained_records=1 if preceding_gap else 200)
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as case:
        sample = await case.emit(b"x", 0)
        overhead = charges(tmp_path)[sample.sequence] - 1
        subscription = await case.start_follow()
        if preceding_gap:
            await case.emit(b"will expire", 0)
        large = await case.emit(b"\0" * (1_048_577 - overhead), 0)
        # The unchanged003 policy accepts and retrieves the complete candidate.
        stored = await ordinary(case, large.sequence, large.sequence + 1)
        assert stored.records == (large,) and stored.charged_bytes == 1_048_577
        if preceding_gap:
            result = await batch(subscription)
            assert result.records == ()
            assert_gap(result, (2, 3), 3, await ordinary(case, 2, 4))
        end = await _await(subscription.pull())
        assert end == follow.FollowEnd("delivery_too_large", None)
        _, page = case.reads.completed[-1]
        assert page.records == () and page.charged_bytes == 0
        assert page.next_record_required_bytes == 1_048_577
        assert page.continuation is not None
        assert page.continuation.next_sequence == large.sequence
        submitted = len(case.reads.requests)
        assert await _await(subscription.pull()) is end
        assert len(case.reads.requests) == submitted
        await subscription.close()
        following = await case.emit(b"capture continues", 1)
        replacement = await case.start_follow()
        assert replacement.start.start_sequence == following.sequence + 1
        assert case.journal.policy == policy
        assert_single_rx_owner(case.fixture)


@pytest.mark.parametrize(
    "eviction", ["before_pull", "after_head", "after_materialization", "after_return"]
)
async def test_eviction_races_preserve_materialized_copies_and_clip_gaps_to_read_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    eviction: str,
) -> None:
    policy = replace(POLICY, max_retained_records=2)
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as case:
        subscription = await case.start_follow()
        first, second = await case.emit(b"one", 1), await case.emit(b"two", 2)
        pending = None
        result = None
        gate = None
        if eviction in ("after_head", "after_materialization"):
            gate = (
                case.reads.page.commit
                if eviction == "after_head"
                else case.reads.page.acknowledgement
            )
            gate.entered.clear()
            gate.allow.clear()
            pending = case.spawn(subscription.pull())
            await _await(gate.entered.wait())
        elif eviction == "after_return":
            result = await batch(subscription)
        third, fourth = await case.emit(b"three", 3), await case.emit(b"four", 4)
        if eviction == "after_head":
            fifth = await case.emit(b"five", 5)
        if gate is not None:
            gate.allow.set()
        if pending is not None:
            value = await _await(pending)
            assert isinstance(value, follow.FollowBatch)
            result = value
        if result is None:
            result = await batch(subscription)
        if eviction == "before_pull":
            assert_gap(result, (1, 3), 3, await ordinary(case, 1, 5))
            assert result.records == (third, fourth)
        elif eviction == "after_head":
            # Head3 was captured before low water advanced to4. Nothing in[3,4)
            # belongs to this first gap, although its unchanged marker includes it.
            assert_gap(result, (1, 3), 4, await ordinary(case, 1, 3))
            assert result.records == ()
            newer = await batch(subscription)
            assert_gap(newer, (3, 4), 4, await ordinary(case, 3, 6))
            assert newer.records == (fourth, fifth)
        else:
            assert result.gap is None and result.records == (first, second)
            expired = await ordinary(case, 1, 3)
            assert expired.outcome is evidence.EvidencePageOutcome.EXPIRED
            assert expired.records == ()
            newer = await batch(subscription)
            assert newer.gap is None and newer.records == (third, fourth)
        assert_single_rx_owner(case.fixture)


async def test_worker_materialization_serializes_only_query_not_subscriber_consumption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    policy = replace(POLICY, max_retained_records=2)
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as case:
        subscription = await case.start_follow()
        first, second = await case.emit(b"one", 1), await case.emit(b"two", 2)
        entered, release = threading.Event(), threading.Event()
        original = sqlite._read_bounded_evidence_page

        def materialize(
            connection: sqlite3.Connection,
            start: int,
            end: int,
            *,
            max_records: int,
            max_charged_bytes: int,
            schema_version: int = 1,
        ) -> tuple[tuple[model.EvidenceRecord, ...], int, int, int | None, bool]:
            page = original(
                connection,
                start,
                end,
                max_records=max_records,
                max_charged_bytes=max_charged_bytes,
                schema_version=schema_version,
            )
            entered.set()
            assert release.wait(3), "test failed to release real SQLite query"
            return page

        with monkeypatch.context() as patch:
            patch.setattr(sqlite, "_read_bounded_evidence_page", materialize)
            pending = case.spawn(subscription.pull())
            try:
                assert await _await(asyncio.to_thread(entered.wait, 3))
                writing = case.spawn(case.emit(b"queued during snapshot", 3))
                await _turn()
                assert not writing.done()
            finally:
                release.set()
            result = await _await(pending)
            assert isinstance(result, follow.FollowBatch)
            assert result.gap is None and result.records == (first, second)
            third = await _await(writing)
        fourth = await case.emit(b"evict retained copy", 4)
        assert (await ordinary(case, 1, 3)).records == ()
        assert result.records == (first, second)
        assert (await batch(subscription)).records == (third, fourth)


async def test_repeated_adjacent_gap_only_pages_advance_position_with_whole_prefix_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    policy = replace(POLICY, max_retained_records=1, max_retrieval_page_records=1)
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as case:
        subscription = await case.start_follow()
        await case.emit(b"one", 1)
        gate = case.reads.page.commit
        results = []
        # Each paused page retains its old head while two actual RX appends evict
        # everything below it. Expected missed intervals are adjacent, not[0,N).
        for payloads in ((b"two", b"three"), (b"four", b"five")):
            gate.entered.clear()
            gate.allow.clear()
            pending = case.spawn(subscription.pull())
            await _await(gate.entered.wait())
            for payload in payloads:
                await case.emit(payload, 10)
            gate.allow.set()
            result = await _await(pending)
            assert isinstance(result, follow.FollowBatch) and result.records == ()
            results.append(result)
        last = await batch(subscription)
        assert [r.gap.missed_range for r in results if r.gap] == [
            model.SequenceRange(1, 2),
            model.SequenceRange(2, 4),
        ]
        assert [
            r.gap.retention_marker.discarded_record_count for r in results if r.gap
        ] == [
            3,
            5,
        ]
        marker = assert_gap(last, (4, 5), 5, await ordinary(case, 4, 6))
        assert marker.discarded_rx_payload_byte_count == 15  # one/two/three/four
        assert len(last.records) == 1 and last.records[0].sequence == 5
        assert isinstance(last.records[0], model.RxBytesEvidence)
        assert last.records[0].payload == b"five"


@pytest.mark.parametrize("quota", ["count", "charged_bytes"])
async def test_idle_subscriber_never_pins_retention_or_accumulates_per_record_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
    quota: str,
) -> None:
    policy = replace(
        POLICY,
        max_retained_records=1 if quota == "count" else 200,
        max_retained_charged_bytes=4096,
        max_record_charged_bytes=4096,
        max_retrieval_page_charged_bytes=4096,
    )
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as case:
        all_charges = charges(tmp_path)
        subscription = await case.start_follow()
        last = None
        for n in range(1, 41):
            last = await case.emit(b"\0\xff" * 1400, n)
            all_charges.update(charges(tmp_path))
        assert len(case.reads.requests) == 1  # No Follow polling while idle.
        assert case.clock.samples == []
        result = await batch(subscription)
        marker = assert_gap(result, (1, 40), 40, await ordinary(case, 1, 41))
        assert result.records == (last,)
        assert marker.discarded_rx_payload_byte_count == 39 * 2800
        assert marker.discarded_charged_bytes == sum(all_charges[n] for n in range(40))
        with closing(sqlite3.connect(tmp_path / "follow-v3.db")) as connection:
            assert connection.execute(
                "SELECT count(*) FROM evidence_records"
            ).fetchone() == (1,)
            assert connection.execute(
                "SELECT count(*) FROM retention_marker"
            ).fetchone() == (1,)
        assert_single_rx_owner(case.fixture)


async def test_missed_subset_preserves_prefix_counts_and_distinct_timestamp_origins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    policy = replace(POLICY, max_retained_records=2)
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as case:
        all_charges = charges(tmp_path)
        old_domain = case.provenance.backend_observation_timestamp_domain
        old = await case.emit(b"prior", 900)
        all_charges.update(charges(tmp_path))
        subscription = await case.start_follow()
        await case.coordinator.append_client_annotation("cli", "host-only prefix")
        all_charges.update(charges(tmp_path))
        new_domain = replace(old_domain, domain_id="new-domain", origin_id="new-origin")
        case.probe.committed["segment_start"].get_nowait()
        await case.fixture.connection.reset_timestamp_origin(new_domain)
        await _await(case.probe.committed["segment_start"].get())
        all_charges.update(charges(tmp_path))
        new = await case.emit(b"new", 1)
        all_charges.update(charges(tmp_path))
        claim = await case.coordinator.append_client_annotation(
            "core", "last host-only"
        )
        tail = await case.emit(b"tail", 2)
        result = await batch(subscription)
        marker = assert_gap(result, (2, 6), 6, await ordinary(case, 2, 8))
        assert result.records == (claim, tail)
        assert (
            marker.discarded_rx_payload_byte_count == 8
        )  # Includes old outside missed.
        assert marker.discarded_charged_bytes == sum(all_charges[n] for n in range(6))
        assert isinstance(old, model.RxBytesEvidence) and isinstance(
            new, model.RxBytesEvidence
        )
        assert marker.first_discarded_timestamp == model.RetentionTimestampEndpoint(
            old.observed_at, old_domain
        )
        assert marker.last_discarded_timestamp == model.RetentionTimestampEndpoint(
            new.observed_at, new_domain
        )
        assert (
            subscription.start.provenance.backend_observation_timestamp_domain
            == old_domain
        )
        assert not any(
            isinstance(r, model.ObserverLossEvidence) for r in result.records
        )
        assert_single_rx_owner(case.fixture)


async def test_retention_interleaves_monitor_annotations_and_rx_without_changing_window_times(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    policy = replace(POLICY, max_retained_records=3, max_retrieval_page_records=2)
    async with recording_case(tmp_path, monkeypatch, factory, policy=policy) as case:
        subscription = await case.start_follow()
        operation = await case.start_monitor()  # sequence1; window begins at2.
        await case.coordinator.append_client_annotation("cli", "not UART")  # 2
        rx = await case.emit(b"ambient\0\xff", 3)
        claim = await case.coordinator.append_client_annotation(
            "core", "assertion"
        )  # 4
        case.clock.advance(1_000_000_100)
        report = await _await(operation.wait())  # end marker5, evict through2.
        assert report.outcome is model.MonitorOutcome.TIMEOUT
        assert report.window == model.SequenceRange(2, 5)
        assert report.clock == model.MonitorClockFacts(
            case.clock.origin_id, 100, 1_000_000_100, 1_000_000_100
        )
        result = await batch(subscription)
        marker = assert_gap(result, (1, 3), 3, await ordinary(case, 1, 6))
        assert result.records == (rx, claim)
        assert marker.discarded_rx_payload_byte_count == 0
        assert (
            marker.first_discarded_timestamp is marker.last_discarded_timestamp is None
        )
        newer = await case.emit(b"still acquiring", 4)
        next_batch = await batch(subscription)
        assert next_batch.gap is None
        assert len(next_batch.records) == 2
        end, tail = next_batch.records
        assert isinstance(end, model.OperationEndedEvidence) and end.sequence == 5
        assert tail == newer and newer.sequence == 6
        assert (
            await ordinary(case, 3, 4)
        ).outcome is evidence.EvidencePageOutcome.EXPIRED
        assert_single_rx_owner(case.fixture)


async def test_exhausted_max_counter_is_legal_empty_follow_head_without_payload_or_overflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        # Same exhausted-counter injection as003: no billion-row synthetic
        # transcript, reopen-validity claim, or replacement journal implementation.
        with closing(sqlite3.connect(tmp_path / "follow-v3.db")) as connection:
            connection.execute(
                "UPDATE session_metadata SET next_sequence=? WHERE singleton=1",
                (model.SQLITE_INTEGER_MAX,),
            )
            connection.commit()

        def forbidden(*args: object, **kwargs: object) -> NoReturn:
            pytest.fail("empty MAX Follow selected payload rows")

        with monkeypatch.context() as patch:
            patch.setattr(sqlite, "_read_bounded_evidence_page", forbidden)
            subscription = await case.start_follow()
            assert subscription.start.start_sequence == model.SQLITE_INTEGER_MAX
            case.reads.head.acknowledgement.entered.clear()
            pending = case.spawn(subscription.pull())
            await _await(case.reads.head.acknowledgement.entered.wait())
            await _turn()
            assert not pending.done()
            assert all(ReadProbe.is_head(r) for r in case.reads.requests)
            assert all(
                p.snapshot_end_exclusive == model.SQLITE_INTEGER_MAX
                for _, p in case.reads.completed
            )
            with pytest.raises(evidence.JournalFailure) as caught:
                await case.rx(b"cannot insert past MAX")
            assert caught.value.kind is evidence.JournalFailureKind.SEQUENCE_EXHAUSTED
            await subscription.close()
            with pytest.raises(follow.FollowRejected, match="not_active"):
                await _await(pending)


async def test_malformed_zero_progress_read_terminates_runtime_without_spin_or_fake_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with runtime_case(tmp_path, monkeypatch, factory) as case:
        await case.activate()
        subscription = await case.start()
        first = await case.emit(b"authoritative record", 1)
        original = case.queries.original

        async def malformed(
            request: evidence.EvidenceRetrievalRequest,
        ) -> evidence.EvidencePage:
            page = await original(request)
            if not ReadProbe.is_head(request):
                # Fault at the read boundary only, after the real query. A page
                # claiming a nonempty snapshot but neither records nor shortage
                # must not become empty progress, a retry loop, or a false gap.
                assert page.records == (first,)
                return replace(page, records=(), charged_bytes=0)
            return page

        case.queries.original = malformed
        end = await _await(subscription.pull())
        assert end == follow.FollowEnd("source_failed", None)
        requests = len(case.queries.requests)
        assert await _await(subscription.pull()) is end
        assert len(case.queries.requests) == requests == 3  # admission/head/page
        case.queries.original = original
        later = await case.emit(b"capture survives bad consumer read", 2)
        replacement = await case.start()
        assert replacement.start.start_sequence == later.sequence + 1
        assert await case.records() == tuple(case.probe.acknowledged)
        assert_single_rx_owner(case.fixture)
