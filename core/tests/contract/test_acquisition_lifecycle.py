"""Additive lifecycle facts without changing legacy Acquisition outcomes."""

import asyncio
from dataclasses import FrozenInstanceError, replace
from typing import Any, cast

import pytest

from dutchmate_core import acquisition as aq
from dutchmate_core.backend import BackendConnection
from dutchmate_core.evidence import InMemoryEvidenceRecorder, PendingEvidenceRecord
from dutchmate_core.model import (
    BackendCapabilities,
    EvidenceRecord,
    SegmentProvenance,
)
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixtureFactory,
    BasicShapedBackend,
    BasicShapedBackendConnection,
    BlockingCloseBackendConnection,
    FailingCloseBackendConnection,
    FailingOpenBackend,
    FixtureBackendOpenFailure,
    FixtureRecorderFailure,
    RejectingEvidenceRecorder,
)


class GatedRecorder(InMemoryEvidenceRecorder):
    def __init__(self, gated_append: int) -> None:
        super().__init__()
        self.gated_append = gated_append
        self.append_count = 0
        self.append_entered = asyncio.Event()
        self.allow_append = asyncio.Event()

    async def append(self, draft: PendingEvidenceRecord) -> EvidenceRecord:
        self.append_count += 1
        if self.append_count == self.gated_append:
            self.append_entered.set()
            await self.allow_append.wait()
        return await super().append(draft)


class DelayedConsumerAcquisition(aq.Acquisition):
    """Hold the actual consumer task after its legacy terminal notification."""

    def __init__(self, recorder: InMemoryEvidenceRecorder) -> None:
        super().__init__(recorder)
        self.consumer_finishing = asyncio.Event()
        self.allow_consumer_finish = asyncio.Event()

    async def _consume(
        self,
        connection: BackendConnection,
        provenance: SegmentProvenance,
        termination_event: asyncio.Event,
    ) -> None:
        await super()._consume(connection, provenance, termination_event)
        self.consumer_finishing.set()
        await self.allow_consumer_finish.wait()


@pytest.mark.asyncio
async def test_initial_snapshot_is_immutable_and_has_no_candidate_identity() -> None:
    acquisition = aq.Acquisition(InMemoryEvidenceRecorder())
    snapshot = acquisition.snapshot()
    assert snapshot.state is aq.AcquisitionState.IDLE
    assert snapshot.descriptor is None
    assert snapshot.provenance is None
    assert snapshot.terminal_trigger is None
    assert snapshot.primary_failure_kind is None
    assert not snapshot.close_failed
    assert snapshot.physical_release_confirmed
    frozen_field = "close_failed"
    with pytest.raises(FrozenInstanceError):
        setattr(snapshot, frozen_field, True)
    assert await acquisition.stop() is aq.AcquisitionState.STOPPED
    assert (await acquisition.join_terminated()).terminal_trigger == "explicit_stop"


@pytest.mark.asyncio
async def test_returned_descriptor_precedes_committed_provenance() -> None:
    recorder = GatedRecorder(1)
    connection = BasicShapedBackendConnection()
    acquisition = aq.Acquisition(recorder)
    start = asyncio.create_task(acquisition.start(BasicShapedBackend(connection)))
    await recorder.append_entered.wait()
    snapshot = acquisition.snapshot()
    assert snapshot.state is aq.AcquisitionState.STARTING
    assert snapshot.descriptor == connection.descriptor
    assert snapshot.provenance is None
    assert not snapshot.physical_release_confirmed
    recorder.allow_append.set()
    connection_id = await start
    committed = acquisition.snapshot().provenance
    assert committed is not None
    assert committed.connection_id == connection_id
    await acquisition.stop()
    await acquisition.join_terminated()
    assert snapshot.provenance is None


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_origin_reset_is_published_only_after_start_acknowledgement(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    recorder = GatedRecorder(3)
    acquisition = aq.Acquisition(recorder)
    await acquisition.start(fixture.backend)
    before = acquisition.snapshot().provenance
    assert before is not None
    new_domain = replace(
        before.backend_observation_timestamp_domain,
        domain_id="next-domain",
        origin_id="next-origin",
    )
    await fixture.connection.reset_timestamp_origin(new_domain)
    await recorder.append_entered.wait()
    assert acquisition.snapshot().provenance == before
    recorder.allow_append.set()
    await fixture.connection.disconnect()
    terminal = await acquisition.join_terminated()
    assert terminal.provenance is not None
    assert terminal.provenance.connection_id == before.connection_id
    assert terminal.provenance.segment_id != before.segment_id
    assert terminal.provenance.backend_observation_timestamp_domain == new_domain


@pytest.mark.asyncio
async def test_failed_origin_reset_keeps_last_committed_provenance() -> None:
    recorder = RejectingEvidenceRecorder(reject_append_number=3)
    connection = BasicShapedBackendConnection()
    acquisition = aq.Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))
    before = acquisition.snapshot().provenance
    assert before is not None
    await connection.reset_timestamp_origin(
        replace(
            before.backend_observation_timestamp_domain,
            domain_id="uncommitted-domain",
            origin_id="uncommitted-origin",
        )
    )
    terminal = await acquisition.join_terminated()
    assert terminal.provenance == before
    assert terminal.primary_failure_kind is aq.AcquisitionFailureKind.RECORDING_FAILURE


@pytest.mark.parametrize("close_fails", [False, True])
@pytest.mark.asyncio
async def test_disconnect_trigger_survives_failed_final_append(
    close_fails: bool,
) -> None:
    recorder = RejectingEvidenceRecorder(reject_append_number=2)
    connection = (
        FailingCloseBackendConnection()
        if close_fails
        else BasicShapedBackendConnection()
    )
    acquisition = aq.Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))
    await connection.disconnect()
    terminal = await acquisition.join_terminated()
    assert terminal.terminal_trigger == "disconnected"
    assert terminal.primary_failure_kind is aq.AcquisitionFailureKind.RECORDING_FAILURE
    assert terminal.close_failed is close_fails
    assert terminal.physical_release_confirmed is not close_fails
    assert terminal.state is aq.AcquisitionState.FAILED
    assert len(recorder.snapshot()) == 1
    assert acquisition.failure is not None
    assert acquisition.failure.kind is aq.AcquisitionFailureKind.RECORDING_FAILURE
    assert await acquisition.stop() is aq.AcquisitionState.FAILED
    assert await acquisition.wait_terminated() is aq.AcquisitionState.FAILED


@pytest.mark.parametrize("close_fails", [False, True])
@pytest.mark.asyncio
async def test_stop_separates_close_only_failure_from_actual_primary(
    close_fails: bool,
) -> None:
    connection = (
        FailingCloseBackendConnection()
        if close_fails
        else BasicShapedBackendConnection()
    )
    recorder = InMemoryEvidenceRecorder()
    acquisition = aq.Acquisition(recorder)
    await acquisition.start(BasicShapedBackend(connection))
    result = await acquisition.stop()
    terminal = await acquisition.join_terminated()
    assert result is (
        aq.AcquisitionState.FAILED if close_fails else aq.AcquisitionState.STOPPED
    )
    assert await acquisition.wait_terminated() is result
    assert terminal.terminal_trigger == "explicit_stop"
    assert terminal.primary_failure_kind is None
    assert terminal.close_failed is close_fails
    assert terminal.physical_release_confirmed is not close_fails
    if close_fails:
        assert acquisition.failure is not None
        assert acquisition.failure.kind is aq.AcquisitionFailureKind.TRANSPORT_FAILURE
    else:
        assert acquisition.failure is None
    records = recorder.snapshot()
    await asyncio.sleep(0)
    assert recorder.snapshot() == records


@pytest.mark.asyncio
async def test_transport_failure_precedes_failed_failure_boundary_in_new_snapshot() -> (
    None
):
    recorder = RejectingEvidenceRecorder(reject_append_number=2)
    acquisition = aq.Acquisition(recorder)
    connection = FailingCloseBackendConnection()
    await acquisition.start(BasicShapedBackend(connection))
    await connection.end_stream_unexpectedly()
    terminal = await acquisition.join_terminated()
    assert terminal.terminal_trigger == "transport_failure"
    assert terminal.primary_failure_kind is aq.AcquisitionFailureKind.TRANSPORT_FAILURE
    assert terminal.close_failed
    assert not terminal.physical_release_confirmed
    # The old reporting boundary still reports the failed evidence append.
    assert acquisition.failure is not None
    assert acquisition.failure.kind is aq.AcquisitionFailureKind.RECORDING_FAILURE


@pytest.mark.asyncio
async def test_initial_append_failure_has_descriptor_but_no_committed_identity() -> (
    None
):
    recorder = RejectingEvidenceRecorder(reject_append_number=1)
    connection = FailingCloseBackendConnection()
    acquisition = aq.Acquisition(recorder)
    with pytest.raises(FixtureRecorderFailure):
        await acquisition.start(BasicShapedBackend(connection))
    terminal = await acquisition.join_terminated()
    assert terminal.descriptor == connection.descriptor
    assert terminal.provenance is None
    assert terminal.primary_failure_kind is aq.AcquisitionFailureKind.RECORDING_FAILURE
    assert terminal.terminal_trigger == "recording_failure"
    assert terminal.close_failed
    assert not terminal.physical_release_confirmed


@pytest.mark.asyncio
async def test_capability_rejection_is_a_primary_failure_without_provenance() -> None:
    connection = BasicShapedBackendConnection(
        capabilities=BackendCapabilities(frozenset())
    )
    acquisition = aq.Acquisition(InMemoryEvidenceRecorder())
    with pytest.raises(aq.UnsupportedBackendCapabilityError):
        await acquisition.start(BasicShapedBackend(connection))
    terminal = await acquisition.join_terminated()
    assert (
        terminal.primary_failure_kind is aq.AcquisitionFailureKind.CAPABILITY_REJECTION
    )
    assert terminal.terminal_trigger == "capability_rejection"
    assert terminal.provenance is None
    assert terminal.physical_release_confirmed
    assert not terminal.close_failed


@pytest.mark.asyncio
async def test_failed_open_never_attests_physical_release() -> None:
    acquisition = aq.Acquisition(InMemoryEvidenceRecorder())
    with pytest.raises(FixtureBackendOpenFailure):
        await acquisition.start(FailingOpenBackend())
    terminal = await acquisition.join_terminated()
    assert terminal.state is aq.AcquisitionState.FAILED
    assert terminal.descriptor is None
    assert terminal.provenance is None
    assert terminal.terminal_trigger == "transport_failure"
    assert terminal.primary_failure_kind is aq.AcquisitionFailureKind.TRANSPORT_FAILURE
    assert not terminal.close_failed
    assert not terminal.physical_release_confirmed
    # Additive certainty does not tighten legacy restart admission.
    await acquisition.start(BasicShapedBackend())
    await acquisition.stop()
    await acquisition.join_terminated()


@pytest.mark.asyncio
async def test_join_waits_for_startup_physical_close_and_final_append() -> None:
    recorder = GatedRecorder(1)
    connection = BlockingCloseBackendConnection()
    acquisition = aq.Acquisition(recorder)
    start = asyncio.create_task(acquisition.start(BasicShapedBackend(connection)))
    await recorder.append_entered.wait()
    join = asyncio.create_task(acquisition.join_terminated())
    await asyncio.sleep(0)
    assert not join.done()
    recorder.allow_append.set()
    await start
    recorder.gated_append = 2
    recorder.allow_append.clear()
    recorder.append_entered.clear()
    stop = asyncio.create_task(acquisition.stop())
    await connection.close_started.wait()
    assert not join.done()
    assert acquisition.snapshot().terminal_trigger is None
    connection.allow_close.set()
    await recorder.append_entered.wait()
    assert not join.done()
    assert acquisition.snapshot().physical_release_confirmed
    recorder.allow_append.set()
    assert await stop is aq.AcquisitionState.STOPPED
    assert (await join).terminal_trigger == "explicit_stop"
    assert len(recorder.snapshot()) == 2


@pytest.mark.asyncio
async def test_join_joins_actual_consumer_and_returns_captured_generation() -> None:
    recorder = InMemoryEvidenceRecorder()
    acquisition = DelayedConsumerAcquisition(recorder)
    first = BasicShapedBackendConnection()
    first_id = await acquisition.start(BasicShapedBackend(first))
    join = asyncio.create_task(acquisition.join_terminated())
    await asyncio.sleep(0)
    await first.disconnect()
    await acquisition.consumer_finishing.wait()
    assert await acquisition.wait_terminated() is aq.AcquisitionState.STOPPED
    assert not join.done()
    second_id = await acquisition.start(BasicShapedBackend())
    acquisition.allow_consumer_finish.set()
    captured = await join
    assert captured.state is aq.AcquisitionState.STOPPED
    assert captured.terminal_trigger == "disconnected"
    assert captured.provenance is not None
    assert captured.provenance.connection_id == first_id
    current = acquisition.snapshot()
    assert current.state is aq.AcquisitionState.ACQUIRING
    assert current.provenance is not None
    assert current.provenance.connection_id == second_id
    await acquisition.stop()
    await acquisition.join_terminated()


@pytest.mark.parametrize(
    ("name", "invalid"),
    [
        ("state", "failed"),
        ("descriptor", RuntimeError("raw handle")),
        ("provenance", {"uncommitted": True}),
        ("terminal_trigger", RuntimeError("raw cause")),
        ("primary_failure_kind", "transport_failure"),
        ("close_failed", 1),
        ("physical_release_confirmed", 1),
    ],
)
def test_snapshot_rejects_raw_or_unvalidated_facts(name: str, invalid: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        aq.AcquisitionSnapshot(
            **cast("Any", {"state": aq.AcquisitionState.IDLE, name: invalid})
        )
