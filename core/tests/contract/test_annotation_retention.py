"""010 T014: real v3 bounds, mixed rolling expiry and selected-codec reads.

Only test-owned journals are used. Expected suffixes and counters come from the
declared fixtures/quotas; no retention or runtime policy is implemented here.
"""

import sqlite3
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from dutchmate_core import annotation, evidence, model
from dutchmate_core.adapters import sqlite_evidence as sqlite
from dutchmate_core.adapters.terminal_evidence import (
    capture_terminal_target,
    open_terminal_reader,
)
from tests.contract.test_annotation_journal import create, reopen
from tests.contract.test_monitor_journal import _end, _provenance, _rx, _start
from tests.contract.test_sqlite_evidence_journal import _policy
from tests.unit.test_annotation_values import draft


def _mixed(index: int) -> tuple[evidence.PendingEvidenceRecord, ...]:
    provenance = _provenance(index)
    return (
        evidence.PendingSegmentStartedEvidence(provenance),
        _start(provenance),
        _rx(provenance, b"noise\0\xffPA", 11),
        replace(draft(), received_at_ns=model.SQLITE_INTEGER_MAX),
        _rx(provenance, b"SStrailing", 12),
        replace(
            _end(),
            window=model.SequenceRange(2, 5),
            match=model.MonitorMatch(
                model.MonitorMatchStart(2, 5), model.MonitorMatchEnd(4, 2)
            ),
        ),
        replace(draft(), text="last claim", received_at_ns=0),
    )


@pytest.mark.parametrize(
    "text,valid",
    [
        ("x", True),
        ("x" * 1024, True),
        ("é" * 512, True),
        ("😀" * 256, True),
        ("\x01" * 1024, True),
        ('"\\\r\n' * 256, True),
        ("e\u0301" * 341 + " ", True),
        ("x" * 1025, False),
        ("é" * 512 + "x", False),
        ("😀" * 256 + "x", False),
        ("\x01" * 1025, False),
        ("", False),
        ("x\0y", False),
        ("\ud800", False),
    ],
)
@pytest.mark.asyncio
async def test_exact_utf8_blob_edges_survive_v3_and_read_only_terminal_without_normalization(
    tmp_path: Path, text: str, valid: bool
) -> None:
    if not valid:
        with pytest.raises(ValueError):
            annotation.AnnotationRequest(model.SessionId("s"), text, "core")
        with pytest.raises(ValueError):
            replace(draft(), text=text)
        return
    path = tmp_path / "text.db"
    pending = replace(draft(), text=text)
    journal = await create(path)
    try:
        record = await journal.append(pending)
        assert isinstance(record, model.ClientAnnotationEvidence)
        assert record.text == text
        encoded = sqlite.encode_evidence_record_v3(record)
        assert encoded.payload == text.encode("utf-8")
        assert encoded.rx_payload_bytes == 0
        target = capture_terminal_target(
            path,
            session_id=journal.session_id,
            policy=journal.policy,
            expected_schema_version=3,
        )
        assert target is not None
        reference = model.EvidenceReference(journal.session_id, record.sequence)
    finally:
        await journal.close()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT timestamp_endpoint_json FROM evidence_records"
        ).fetchone() == (None,)
    reader = await open_terminal_reader(target)
    try:
        page = await reader.resolve_record(reference)
        assert page.records == (record,)
        assert page.charged_bytes == encoded.charged_bytes
    finally:
        await reader.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("retained", [1, 2, 3, 4, 5, 6, 7])
@pytest.mark.asyncio
async def test_every_mixed_suffix_reopens_with_exact_expiry_and_host_only_annotations(
    tmp_path: Path, index: int, retained: int
) -> None:
    path = tmp_path / "mixed.db"
    journal = await create(path, policy=_policy(max_retained_records=retained))
    records: list[model.EvidenceRecord] = []
    try:
        for pending in _mixed(index):
            records.append(await journal.append(pending))
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(journal.session_id, 20, 20000)
        )
        cut = 7 - retained
        assert page.records == tuple(records[cut:])
        assert page.snapshot_end_exclusive == 7
        assert page.outcome is (
            evidence.EvidencePageOutcome.PARTIAL
            if cut
            else evidence.EvidencePageOutcome.COMPLETE
        )
        if cut:
            marker = page.retention_marker
            assert marker is not None
            assert marker.expired_range == model.SequenceRange(0, cut)
            assert marker.discarded_record_count == cut
            assert marker.discarded_charged_bytes == sum(
                sqlite.encode_evidence_record_v3(r).charged_bytes for r in records[:cut]
            )
            discarded_rx = [
                r for r in records[:cut] if isinstance(r, model.RxBytesEvidence)
            ]
            assert marker.discarded_rx_payload_byte_count == sum(
                len(r.payload) for r in discarded_rx
            )
            domain = _provenance(index).backend_observation_timestamp_domain
            endpoints = [
                model.RetentionTimestampEndpoint(r.observed_at, domain)
                for r in discarded_rx
            ]
            assert marker.first_discarded_timestamp == (
                endpoints[0] if endpoints else None
            )
            assert marker.last_discarded_timestamp == (
                endpoints[-1] if endpoints else None
            )
        else:
            assert page.retention_marker is None
        session = journal.session_id
    finally:
        await journal.close()
    # Reopen validates any retained operation pair through the selected v3 codec,
    # including annotation between matched RX endpoints and partially expired pairs.
    opened = await reopen(path, 3, session)
    try:
        assert (
            await opened.retrieve(evidence.EvidenceRetrievalRequest(session, 20, 20000))
        ) == page
        added = await opened.append(_rx(_provenance(index), b"following\0\xff", 13))
        assert added.sequence == 7
        assert (
            await opened.resolve_record(model.EvidenceReference(session, 7))
        ).records == (added,)
    finally:
        await opened.close()
    opened = await reopen(path, 3, session)
    await opened.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize(
    "annotation_first",
    [False, True],
    ids=["annotation-evicts-rx", "rx-evicts-annotation"],
)
@pytest.mark.asyncio
async def test_byte_quota_has_no_annotation_pinning_and_coalesces_mixed_expiry(
    tmp_path: Path, index: int, annotation_first: bool
) -> None:
    provenance = _provenance(index)
    claim = replace(
        draft(), text="\x01" * 1024, received_at_ns=model.SQLITE_INTEGER_MAX
    )
    rx = _rx(provenance, b"ambient\0\xff", 123)
    charge = sqlite.charge_client_annotation(claim)
    path = tmp_path / "byte-rolling.db"
    journal = await create(
        path,
        policy=_policy(
            max_record_charged_bytes=charge, max_retained_charged_bytes=charge
        ),
    )
    records: list[model.EvidenceRecord] = []
    try:
        records.append(
            await journal.append(evidence.PendingSegmentStartedEvidence(provenance))
        )
        first, second = (claim, rx) if annotation_first else (rx, claim)
        for pending in (first, second, first, second, first, second):
            accepted = await journal.append(pending)
            records.append(accepted)
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(journal.session_id, 20, 20000)
        )
        assert page.records == (records[-1],)
        marker = page.retention_marker
        assert marker is not None and marker.expired_range == model.SequenceRange(0, 6)
        assert marker.discarded_record_count == 6
        assert marker.discarded_charged_bytes == sum(
            sqlite.encode_evidence_record_v3(r).charged_bytes for r in records[:-1]
        )
        discarded_rx = [r for r in records[:-1] if isinstance(r, model.RxBytesEvidence)]
        assert marker.discarded_rx_payload_byte_count == len(discarded_rx) * len(
            rx.payload
        )
        endpoint = model.RetentionTimestampEndpoint(
            model.BackendObservationTimestamp(
                provenance.backend_observation_timestamp_domain.domain_id, 123
            ),
            provenance.backend_observation_timestamp_domain,
        )
        assert (
            marker.first_discarded_timestamp
            == marker.last_discarded_timestamp
            == endpoint
        )
        for sequence in range(6):
            expired = await journal.resolve_record(
                model.EvidenceReference(journal.session_id, sequence)
            )
            assert (
                expired.outcome is evidence.EvidencePageOutcome.EXPIRED
                and not expired.records
            )
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM retention_marker"
            ).fetchone() == (1,)
            assert connection.execute(
                "SELECT COUNT(*) FROM evidence_records"
            ).fetchone() == (1,)
    finally:
        await journal.close()
    opened = await reopen(path, 3)
    await opened.close()


@pytest.mark.parametrize("adjustment,retained", [(-1, 1), (0, 2), (1, 2)])
@pytest.mark.asyncio
async def test_annotation_retained_charge_equality_and_one_byte_short_are_exact(
    tmp_path: Path, adjustment: int, retained: int
) -> None:
    pending = replace(draft(), text="é" * 512, received_at_ns=model.SQLITE_INTEGER_MAX)
    charge = sqlite.charge_client_annotation(pending)
    journal = await create(
        tmp_path / "exact.db",
        policy=_policy(
            max_record_charged_bytes=charge,
            max_retained_charged_bytes=2 * charge + adjustment,
        ),
    )
    try:
        records = [await journal.append(pending) for _ in range(3)]
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(journal.session_id, 20, 20000)
        )
        assert page.records == tuple(records[3 - retained :])
        assert page.charged_bytes == retained * charge
        assert page.retention_marker is not None
        assert page.retention_marker.discarded_charged_bytes == (3 - retained) * charge
        assert page.retention_marker.discarded_rx_payload_byte_count == 0
        assert page.retention_marker.first_discarded_timestamp is None
        assert page.retention_marker.last_discarded_timestamp is None
    finally:
        await journal.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize(
    "bounds,outcome,next_sequence",
    [
        ((0, 3), evidence.EvidencePageOutcome.EXPIRED, None),
        ((2, 6), evidence.EvidencePageOutcome.PARTIAL, 3),
        ((3, 6), evidence.EvidencePageOutcome.COMPLETE, 3),
        ((6, 8), evidence.EvidencePageOutcome.NOT_FOUND, None),
    ],
)
@pytest.mark.asyncio
async def test_zero_shortage_pages_keep_expiry_outcome_and_exact_annotation_charge(
    tmp_path: Path,
    index: int,
    bounds: tuple[int, int],
    outcome: evidence.EvidencePageOutcome,
    next_sequence: int | None,
) -> None:
    journal = await create(
        tmp_path / "shortage.db", policy=_policy(max_retained_records=3)
    )
    records: list[model.EvidenceRecord] = []
    try:
        for pending in _mixed(index)[:6]:
            records.append(await journal.append(pending))
        request = evidence.EvidenceRetrievalRequest(
            model.EvidenceRangeReference(journal.session_id, *bounds), 20, 1
        )
        page = await journal.retrieve(request)
        assert page.records == () and page.charged_bytes == 0
        assert page.outcome is outcome
        assert page.snapshot_end_exclusive == min(bounds[1], 6)
        assert page.never_existed_range == (
            model.SequenceRange(6, 8) if bounds[0] == 6 else None
        )
        assert page.expired_range == (
            model.SequenceRange(bounds[0], 3) if bounds[0] < 3 else None
        )
        if next_sequence is None:
            assert not page.truncated and page.continuation is None
            assert page.next_record_required_bytes is None
        else:
            assert page.truncated and page.continuation is not None
            assert page.continuation.next_sequence == next_sequence
            assert page.continuation.range_start_inclusive == bounds[0]
            assert page.continuation.range_end_exclusive == bounds[1]
            assert (
                page.next_record_required_bytes
                == sqlite.encode_evidence_record_v3(
                    records[next_sequence]
                ).charged_bytes
            )
            resumed = await journal.retrieve(
                replace(
                    request,
                    max_charged_bytes=page.next_record_required_bytes,
                    cursor=page.continuation,
                )
            )
            assert resumed.records == (records[next_sequence],)
            assert resumed.snapshot_end_exclusive == page.snapshot_end_exclusive
    finally:
        await journal.close()


@pytest.mark.parametrize(
    "evict", [False, True], ids=["append-within-snapshot", "snapshot-fully-expired"]
)
@pytest.mark.asyncio
async def test_shortage_cursor_never_expands_after_new_annotations_or_expiry(
    tmp_path: Path, evict: bool
) -> None:
    journal = await create(
        tmp_path / "cursor.db", policy=_policy(max_retained_records=3)
    )
    try:
        records = [
            await journal.append(replace(draft(), text=f"claim{i}")) for i in range(3)
        ]
        request = evidence.EvidenceRetrievalRequest(journal.session_id, 1, 1)
        first = await journal.retrieve(request)
        assert first.continuation is not None and first.continuation.next_sequence == 0
        assert first.snapshot_end_exclusive == 3 and first.records == ()
        for i in range(3 if evict else 1):
            await journal.append(replace(draft(), text=f"later{i}"))
        resumed = await journal.retrieve(
            replace(request, max_charged_bytes=20000, cursor=first.continuation)
        )
        assert resumed.snapshot_end_exclusive == 3
        if evict:
            assert resumed.outcome is evidence.EvidencePageOutcome.EXPIRED
            assert (
                resumed.records == ()
                and resumed.expired_range == model.SequenceRange(0, 3)
            )
            assert not resumed.truncated and resumed.continuation is None
        else:
            assert resumed.outcome is evidence.EvidencePageOutcome.PARTIAL
            assert resumed.expired_range == model.SequenceRange(0, 1)
            assert resumed.records == (records[1],)
            assert (
                resumed.continuation is not None
                and resumed.continuation.next_sequence == 2
            )
            last = await journal.retrieve(
                replace(request, max_charged_bytes=20000, cursor=resumed.continuation)
            )
            assert last.records == (records[2],)
            assert last.snapshot_end_exclusive == 3 and last.continuation is None
        bad_cursor = replace(first.continuation, session_id=model.SessionId("other"))
        with pytest.raises(evidence.JournalFailure) as caught:
            await journal.retrieve(replace(request, cursor=bad_cursor))
        assert caught.value.kind is evidence.JournalFailureKind.SESSION_MISMATCH
    finally:
        await journal.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("reopen_before_eviction", [False, True])
@pytest.mark.asyncio
async def test_t016_evicted_segment_descriptor_keeps_identity_and_origin_through_reopen(
    tmp_path: Path, index: int, reopen_before_eviction: bool
) -> None:
    path = tmp_path / "descriptor.db"
    first = _provenance(index)
    second = replace(
        first,
        segment_id=model.SegmentId("next-segment"),
        backend_observation_timestamp_domain=replace(
            first.backend_observation_timestamp_domain, origin_id="next-origin"
        ),
    )
    journal = await create(path, policy=_policy(max_retained_records=1))
    try:
        await journal.append(evidence.PendingSegmentStartedEvidence(first))
        if reopen_before_eviction:
            session = journal.session_id
            await journal.close()
            journal = await reopen(path, 3, session)
        for pending in (
            draft(),
            _rx(first, b"first", 11),
            draft(),
            evidence.PendingSegmentStartedEvidence(second),
            draft(),
            _rx(first, b"old-identity", 12),
        ):
            await journal.append(pending)
        # A late old identity must not inherit the new segment's different
        # origin, even with the same domain ID. Unknown provenance stays absent;
        # a known descriptor must belong to the actual old stream.
        with closing(sqlite3.connect(path)) as connection:
            (cached,) = connection.execute(
                "SELECT timestamp_endpoint_json FROM evidence_records WHERE sequence=6"
            ).fetchone()
            if cached is not None:
                assert sqlite._decode_retention_timestamp_endpoint(
                    cached
                ) == model.RetentionTimestampEndpoint(
                    model.BackendObservationTimestamp(
                        first.backend_observation_timestamp_domain.domain_id, 12
                    ),
                    first.backend_observation_timestamp_domain,
                )
        await journal.append(_rx(second, b"second", 13))
        session, policy = journal.session_id, journal.policy
    finally:
        await journal.close()
    journal = await reopen(path, 3, session)
    try:
        # The RX cache is durable: no volatile writer context is needed to evict
        # this timestamp with its exact descriptor after an ordinary reopen.
        await journal.append(draft())
        page = await journal.retrieve(
            evidence.EvidenceRetrievalRequest(session, 20, 20000)
        )
        marker = page.retention_marker
        assert marker is not None
        assert marker.expired_range == model.SequenceRange(0, 8)
        assert marker.first_discarded_timestamp == model.RetentionTimestampEndpoint(
            model.BackendObservationTimestamp(
                first.backend_observation_timestamp_domain.domain_id, 11
            ),
            first.backend_observation_timestamp_domain,
        )
        assert marker.last_discarded_timestamp == model.RetentionTimestampEndpoint(
            model.BackendObservationTimestamp(
                second.backend_observation_timestamp_domain.domain_id, 13
            ),
            second.backend_observation_timestamp_domain,
        )
        assert marker.discarded_rx_payload_byte_count == 23
        target = capture_terminal_target(
            path, session_id=session, policy=policy, expected_schema_version=3
        )
        assert target is not None
    finally:
        await journal.close()
    reader = await open_terminal_reader(target)
    try:
        assert (
            await reader.retrieve(evidence.EvidenceRetrievalRequest(session, 20, 20000))
            == page
        )
    finally:
        await reader.close()


@pytest.mark.parametrize("index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t016_rolled_back_segment_does_not_replace_committed_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, index: int
) -> None:
    path = tmp_path / "rollback-descriptor.db"
    provenance = _provenance(index)
    journal = await create(path, policy=_policy(max_retained_records=1))
    try:
        await journal.append(evidence.PendingSegmentStartedEvidence(provenance))
        await journal.append(draft())
        request = evidence.EvidenceRetrievalRequest(journal.session_id, 20, 20000)
        before = await journal.retrieve(request)
        original = sqlite._read_retention_marker
        calls = 0

        def fail_postcondition(
            connection: sqlite3.Connection, operation: evidence.JournalOperation
        ) -> sqlite._StoredRetentionMarker | None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise evidence.JournalFailure(
                    operation, evidence.JournalFailureKind.CAPACITY
                )
            return original(connection, operation)

        with monkeypatch.context() as patch:
            patch.setattr(sqlite, "_read_retention_marker", fail_postcondition)
            with pytest.raises(evidence.JournalFailure) as caught:
                await journal.append(
                    evidence.PendingSegmentStartedEvidence(
                        replace(
                            provenance,
                            backend_observation_timestamp_domain=replace(
                                provenance.backend_observation_timestamp_domain,
                                origin_id="uncommitted-origin",
                            ),
                        )
                    )
                )
            assert caught.value.kind is evidence.JournalFailureKind.CAPACITY
        assert calls == 2 and await journal.retrieve(request) == before
        accepted = await journal.append(_rx(provenance, b"after rollback", 17))
        assert accepted.sequence == 2
        await journal.append(draft())
        marker = (await journal.retrieve(request)).retention_marker
        assert marker is not None
        endpoint = model.RetentionTimestampEndpoint(
            model.BackendObservationTimestamp(
                provenance.backend_observation_timestamp_domain.domain_id, 17
            ),
            provenance.backend_observation_timestamp_domain,
        )
        assert (
            marker.first_discarded_timestamp
            == marker.last_discarded_timestamp
            == endpoint
        )
    finally:
        await journal.close()
