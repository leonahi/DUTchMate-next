"""011 T006 RED: actual acquisition/v3 journal and concurrent Monitor/annotations.

No runtime Follow admission or optional preparation transfer is used here.
The only simulated components are the existing backend fixtures and host clock;
all journal writes, reads, ordering and Monitor/annotation mechanics are real.
"""

import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

import pytest

from dutchmate_core import evidence, model
from dutchmate_core.adapters import sqlite_evidence as sqlite
from tests.contract.test_follow_recording import (
    batch,
    recording_case,
)
from tests.contract.test_monitor_recording import _await, _turn
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixtureFactory,
    EnhancedShapedBackendConnection,
)
from tests.integration.test_annotations import assert_single_rx_owner

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "factory", BACKEND_FIXTURE_FACTORIES, ids=["basic", "enhanced"]
    ),
]


async def test_actual_empty_max_probe_is_metadata_only_on_the_existing_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    # Existing003 prerequisite, intentionally GREEN before Follow exists. Catches
    # a harness/adapter assumption independently of missing coordinator admission.
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        old = await case.emit(bytes(range(256)), 17)

        def forbidden(*args: object, **kwargs: object) -> NoReturn:
            pytest.fail("empty[MAX,MAX) selected evidence payloads")

        with monkeypatch.context() as patch:
            patch.setattr(sqlite, "_read_bounded_evidence_page", forbidden)
            maximum = model.SQLITE_INTEGER_MAX
            result = await case.journal.retrieve(
                evidence.EvidenceRetrievalRequest(
                    model.EvidenceRangeReference(
                        case.journal.session_id, maximum, maximum
                    ),
                    32,
                    1_048_576,
                )
            )
        assert result.snapshot_end_exclusive == old.sequence + 1 == 2
        assert result.records == () and result.charged_bytes == 0
        assert result.outcome is evidence.EvidencePageOutcome.NOT_FOUND
        assert_single_rx_owner(case.fixture)


async def test_test_owned_ack_gate_preserves_real_committed_record_and_blocks_next_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    # Infrastructure characterization, not a replacement Follow implementation.
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        ack = case.probe.gates["annotation"].acknowledgement
        ack.allow.clear()
        insertion = case.spawn(
            case.coordinator.append_client_annotation("core", "gate probe")
        )
        await _await(ack.entered.wait())
        current = await case.all_records()
        assert isinstance(current[-1], model.ClientAnnotationEvidence)
        assert current[-1] not in case.probe.acknowledged
        queued = case.spawn(case.rx(b"queued"))
        await _turn()
        assert not queued.done() and len(case.probe.submitted) == 2
        ack.allow.set()
        assert await _await(insertion) == current[-1]
        assert (await _await(queued)).sequence == 2


async def test_live_binary_records_monitor_annotations_and_declared_loss_equal_ordinary_retrieval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        old = await case.emit(b"old ambient\0\xff", 1)
        captured = case.provenance
        subscription = await case.start_follow()
        assert subscription.start.start_sequence == old.sequence + 1 == 2
        assert subscription.start.provenance == captured
        assert subscription.start.provenance.backend_observation_timestamp_domain == (
            case.fixture.connection.descriptor.backend_observation_timestamp_domain
        )
        operation = await case.start_monitor()
        raw = await case.emit(bytes(range(256)), 2)
        assert isinstance(raw, model.RxBytesEvidence)
        first = await case.emit(b"\0\xffPA", 3)
        accepted = await case.coordinator.append_client_annotation(
            "cli", "SS\r\n e\u0301 assertion"
        )
        assert not operation.decided  # Annotation text is not UART input.
        loss = None
        if isinstance(captured.loss_observability, model.ObserverReportsUartLoss):
            connection = case.fixture.connection
            assert isinstance(connection, EnhancedShapedBackendConnection)
            await connection.emit_observer_loss(
                cause="overflow", lost_bytes=None, timestamp=4
            )
            loss = await _await(case.probe.committed["loss"].get())
            # A real reported loss resets Monitor's partial literal match.
            await case.emit(b"SS", 5)
            assert not operation.decided
            matching = await case.emit(b"\0\xffPASStrailing", 6)
            match_sequence, match_offset = matching.sequence, 6
        else:
            matching = await case.emit(b"SStrailing", 6)
            match_sequence, match_offset = first.sequence, 2
        report = await _await(operation.wait())
        assert (
            report.outcome is model.MonitorOutcome.MATCHED
            and report.durability == "complete"
        )
        assert report.match is not None
        assert report.match.start == model.MonitorMatchStart(match_sequence, 0)
        assert report.match.end == model.MonitorMatchEnd(
            matching.sequence, match_offset
        )
        assert report.observer_loss_records == (1 if loss is not None else 0)
        assert report.clock.started_at_ns == report.clock.decided_at_ns == 100
        assert (
            accepted.assertion_class == "client_assertion"
            and accepted.attribution_basis == "client_asserted"
        )
        # A genuine normalized origin boundary supplies a later segment-start
        # record; Follow must deliver it, not replay its initial descriptor.
        case.probe.committed["segment_start"].get_nowait()
        domain = replace(
            captured.backend_observation_timestamp_domain,
            domain_id="next-domain",
            origin_id="next-origin",
        )
        await case.fixture.connection.reset_timestamp_origin(domain)
        await _await(case.probe.committed["segment_start"].get())
        await _await(
            case.acquisition.stop()
        )  # Existing source stop; no runtime Follow teardown yet.
        ordinary = await case.all_records()
        assert isinstance(ordinary[-1], model.SegmentEndedEvidence)
        wanted = ordinary[2:]
        result = await batch(subscription)
        assert result.gap is None and result.records == wanted
        assert all(
            record.sequence == index + 2 for index, record in enumerate(result.records)
        )
        assert old not in result.records
        assert raw.payload == bytes(range(256))
        assert {type(record) for record in ordinary} == {
            model.SegmentStartedEvidence,
            model.SegmentEndedEvidence,
            model.RxBytesEvidence,
            model.OperationStartedEvidence,
            model.OperationEndedEvidence,
            model.ClientAnnotationEvidence,
        } | ({model.ObserverLossEvidence} if loss is not None else set())
        assert {type(record) for record in result.records} == {
            type(record) for record in ordinary
        }
        assert_single_rx_owner(case.fixture)
        assert case.fixture.connection.close_calls == 1


async def test_follow_reuses_exact_live_sqlite_worker_connection_and_never_opens_another_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    calls: list[tuple[int, int, int]] = []
    original_append, original_retrieve = (
        sqlite._append_on_worker,
        sqlite._retrieve_page_on_worker,
    )

    def append(
        connection: sqlite3.Connection,
        policy: model.SessionPolicy,
        draft: evidence.PendingEvidenceRecord,
        *,
        schema_version: int = 1,
        timestamp_context: sqlite._WriterTimestampContext | None = None,
    ) -> model.EvidenceRecord:
        calls.append((threading.get_ident(), id(connection), schema_version))
        return original_append(
            connection,
            policy,
            draft,
            schema_version=schema_version,
            timestamp_context=timestamp_context,
        )

    def retrieve(
        connection: sqlite3.Connection,
        policy: model.SessionPolicy,
        request: evidence.EvidenceRetrievalRequest,
        *,
        schema_version: int = 1,
    ) -> evidence.EvidencePage:
        calls.append((threading.get_ident(), id(connection), schema_version))
        return original_retrieve(
            connection, policy, request, schema_version=schema_version
        )

    monkeypatch.setattr(sqlite, "_append_on_worker", append)
    monkeypatch.setattr(sqlite, "_retrieve_page_on_worker", retrieve)
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        # Acquisition.start schedules the authoritative consumer. Wait for its
        # first read before forbidding any additional event-stream acquisition.
        await _await(case.fixture.connection.read_gate.entered.wait())
        assert_single_rx_owner(case.fixture)

        def forbidden(*args: object, **kwargs: object) -> NoReturn:
            pytest.fail("Follow opened another SQLite connection or RX reader")

        with monkeypatch.context() as patch:
            patch.setattr(sqlite3, "connect", forbidden)
            patch.setattr(case.fixture.backend, "open", forbidden)
            patch.setattr(case.fixture.connection, "events", forbidden)
            subscription = await case.start_follow()
            operation = await case.start_monitor()
            accepted = await case.coordinator.append_client_annotation(
                "http", "same live writer"
            )
            await case.emit(b"\0\xffPASS", 1)
            await _await(operation.wait())
            ordinary = await case.all_records()
            result = await batch(subscription)
            assert result.records == ordinary[1:] and accepted in result.records
            assert len(calls) >= 7 and len(set(calls)) == 1
            assert calls[0][0] != threading.get_ident() and calls[0][2] == 3
            assert_single_rx_owner(case.fixture)


async def test_follow_close_and_replacement_leave_acquisition_monitor_and_annotations_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory: BackendFixtureFactory,
) -> None:
    async with recording_case(tmp_path, monkeypatch, factory) as case:
        subscription = await case.start_follow()
        operation = await case.start_monitor()
        first = await case.emit(b"\0\xffPA", 1)
        accepted = await case.coordinator.append_client_annotation(
            "core", "independent assertion"
        )
        received = await batch(subscription)
        assert first in received.records and accepted in received.records
        await subscription.close()
        await subscription.close()
        assert case.probe.close_calls == case.fixture.connection.close_calls == 0
        assert not operation.decided
        last = await case.emit(b"SSambient", 2)
        report = await _await(operation.wait())
        assert report.outcome is model.MonitorOutcome.MATCHED
        assert report.match == model.MonitorMatch(
            model.MonitorMatchStart(first.sequence, 0),
            model.MonitorMatchEnd(last.sequence, 2),
        )
        ordinary = await case.all_records()
        replacement = await case.start_follow()
        assert replacement.start.start_sequence == len(ordinary)
        new = await case.emit(bytes(range(256)), 3)
        assert (await batch(replacement)).records == (new,)
        assert await case.all_records() == (*ordinary, new)
        assert_single_rx_owner(case.fixture)
        assert case.fixture.connection.close_calls == case.probe.close_calls == 0
