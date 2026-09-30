"""Lifecycle integration tests for Basic serial acquisition using only fakes."""

import asyncio
import errno
import threading
from contextlib import suppress
from typing import cast

import pytest
import serial

from dutchmate_core.acquisition import (
    Acquisition,
    AcquisitionAlreadyActiveError,
    AcquisitionFailureKind,
    AcquisitionState,
)
from dutchmate_core.adapters.basic_serial import (
    BasicSerialBackend,
    SerialConfiguration,
    SerialDataBits,
    SerialDeviceSelector,
    SerialLineState,
    SerialOpenLineIntent,
    SerialParity,
    SerialStopBits,
)
from dutchmate_core.backend import (
    Backend,
    BackendConnection,
    BackendFailureKind,
    BackendFailureOperation,
    NormalizedBackendFailure,
)
from dutchmate_core.evidence import InMemoryEvidenceRecorder
from dutchmate_core.model import (
    BackendCapability,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentEndReason,
    SegmentStartedEvidence,
    TimestampMeaning,
    TimestampObserver,
    TimestampUnit,
)
from tests.contract.test_basic_serial_adapter import (
    FakeMonotonicClock,
    FakeSerial,
    FakeSerialFactory,
)


class _CapturingBackend:
    def __init__(self, delegate: Backend) -> None:
        self._delegate = delegate
        self.connection: BackendConnection | None = None

    async def open(self) -> BackendConnection:
        connection = await self._delegate.open()
        self.connection = connection
        return connection


def _backend(fake_serial: FakeSerial) -> tuple[Backend, FakeSerialFactory]:
    factory = FakeSerialFactory(fake_serial)
    backend = BasicSerialBackend(
        selector=SerialDeviceSelector("/dev/ttyUSB-selected"),
        configuration=SerialConfiguration(
            baud_rate=115_200,
            data_bits=SerialDataBits.EIGHT,
            parity=SerialParity.NONE,
            stop_bits=SerialStopBits.ONE,
            hardware_flow_control=False,
            software_flow_control=False,
        ),
        line_intent=SerialOpenLineIntent(
            dtr=SerialLineState.DEASSERTED,
            rts=SerialLineState.DEASSERTED,
        ),
        _serial_factory=factory,
    )
    return cast("Backend", backend), factory


def _capturing_backend(
    fake_serial: FakeSerial,
) -> tuple[_CapturingBackend, FakeSerialFactory]:
    backend, factory = _backend(fake_serial)
    return _CapturingBackend(backend), factory


async def _wait_for_thread_event(event: threading.Event) -> None:
    observed = await asyncio.wait_for(
        asyncio.to_thread(event.wait, 1.0),
        timeout=2.0,
    )
    assert observed


async def _wait_for_termination(acquisition: Acquisition) -> AcquisitionState:
    return await asyncio.wait_for(acquisition.wait_terminated(), timeout=2.0)


async def _stop_after_cancel(
    acquisition: Acquisition,
    fake_serial: FakeSerial,
    read_gate: threading.Event,
) -> AcquisitionState:
    stop_task = asyncio.create_task(acquisition.stop())
    try:
        await _wait_for_thread_event(fake_serial.cancel_read_called)
        read_gate.set()
        return await asyncio.wait_for(stop_task, timeout=2.0)
    finally:
        read_gate.set()
        if not stop_task.done():
            stop_task.cancel()
            with suppress(asyncio.CancelledError):
                await stop_task


@pytest.mark.asyncio
async def test_acquisition_stays_stopping_and_rejects_restart_until_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock((1,)))
    read_gate = threading.Event()
    fake_serial = FakeSerial(
        read_results=(b"",),
        read_gates=(read_gate,),
    )
    backend, _ = _backend(fake_serial)
    replacement_backend, replacement_factory = _backend(FakeSerial())
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    stop_task: asyncio.Task[AcquisitionState] | None = None

    try:
        await acquisition.start(backend)
        await _wait_for_thread_event(fake_serial.read_started[0])
        stop_task = asyncio.create_task(acquisition.stop())
        await _wait_for_thread_event(fake_serial.cancel_read_called)

        assert acquisition.state is AcquisitionState.STOPPING
        assert fake_serial.close_calls == 0
        assert not stop_task.done()
        with pytest.raises(AcquisitionAlreadyActiveError):
            await acquisition.start(replacement_backend)
        assert replacement_factory.calls == []

        read_gate.set()
        assert await asyncio.wait_for(stop_task, timeout=2.0) is (
            AcquisitionState.STOPPED
        )
        assert fake_serial.close_calls == 1

        assert await acquisition.stop() is AcquisitionState.STOPPED
        segment_ends = [
            record
            for record in recorder.snapshot()
            if isinstance(record, SegmentEndedEvidence)
        ]
        assert len(segment_ends) == 1
        assert segment_ends[0].reason is SegmentEndReason.EXPLICIT_STOP
    finally:
        read_gate.set()
        if stop_task is not None and not stop_task.done():
            stop_task.cancel()
            with suppress(asyncio.CancelledError):
                await stop_task


@pytest.mark.asyncio
async def test_primary_read_failure_survives_close_failure_and_blocks_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock(()))
    fake_serial = FakeSerial(
        read_results=(serial.SerialException(errno.EIO, "read diagnostic"),),
        close_error=serial.SerialException(errno.EIO, "close diagnostic"),
    )
    backend, _ = _backend(fake_serial)
    replacement_backend, replacement_factory = _backend(FakeSerial())
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)

    await acquisition.start(backend)
    assert await _wait_for_termination(acquisition) is AcquisitionState.FAILED

    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.TRANSPORT_FAILURE
    primary = acquisition.failure.cause
    assert isinstance(primary, NormalizedBackendFailure)
    assert primary.operation is BackendFailureOperation.READ
    assert primary.kind is BackendFailureKind.IO_FAILURE
    assert primary.__cause__ is None
    assert primary.__context__ is None
    assert fake_serial.close_calls == 1

    with pytest.raises(AcquisitionAlreadyActiveError):
        await acquisition.start(replacement_backend)
    assert replacement_factory.calls == []

    segment_ends = [
        record
        for record in recorder.snapshot()
        if isinstance(record, SegmentEndedEvidence)
    ]
    assert len(segment_ends) == 1
    assert segment_ends[0].reason is SegmentEndReason.TRANSPORT_FAILURE


@pytest.mark.asyncio
async def test_real_basic_adapter_records_ambient_exact_rx_with_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = (
        bytes(range(256)) + b"\x00\x80\xfe\xffinvalid-utf8:\xf5",
        b"ambient-after-first-read",
    )
    clock = FakeMonotonicClock((101, 102, 103))
    monkeypatch.setattr("time.monotonic_ns", clock)
    stop_gate = threading.Event()
    fake_serial = FakeSerial(
        read_results=(*payloads, b""),
        read_gates=(None, None, stop_gate),
    )
    backend, _ = _capturing_backend(fake_serial)
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)

    connection_id = await acquisition.start(backend)
    await _wait_for_thread_event(fake_serial.read_started[2])
    assert await _stop_after_cancel(
        acquisition,
        fake_serial,
        stop_gate,
    ) is AcquisitionState.STOPPED

    connection = backend.connection
    assert connection is not None
    records = recorder.snapshot()
    assert [record.sequence for record in records] == [0, 1, 2, 3]
    assert [type(record) for record in records] == [
        SegmentStartedEvidence,
        RxBytesEvidence,
        RxBytesEvidence,
        SegmentEndedEvidence,
    ]
    segment_start = records[0]
    assert isinstance(segment_start, SegmentStartedEvidence)
    descriptor = connection.descriptor
    assert segment_start.provenance.connection_id == connection_id
    assert (
        segment_start.provenance.connection_provenance
        is descriptor.connection_provenance
    )
    assert (
        segment_start.provenance.backend_observation_timestamp_domain
        is descriptor.backend_observation_timestamp_domain
    )
    assert segment_start.provenance.capabilities.values == frozenset(
        {BackendCapability.UART_RECEIVE}
    )
    domain = segment_start.provenance.backend_observation_timestamp_domain
    assert domain.observer is TimestampObserver.HOST
    assert domain.meaning is TimestampMeaning.OBSERVATION
    assert domain.unit is TimestampUnit.NANOSECOND

    rx_records = [
        record for record in records if isinstance(record, RxBytesEvidence)
    ]
    assert [record.payload for record in rx_records] == list(payloads)
    assert [record.observed_at.value for record in rx_records] == [101, 102]
    assert {record.observed_at.domain_id for record in rx_records} == {
        domain.domain_id
    }
    assert {record.connection_id for record in rx_records} == {connection_id}
    assert len({record.segment_id for record in rx_records}) == 1
    segment_end = records[-1]
    assert isinstance(segment_end, SegmentEndedEvidence)
    assert segment_end.reason is SegmentEndReason.EXPLICIT_STOP


@pytest.mark.asyncio
async def test_real_basic_adapter_explicit_stop_closes_after_blocked_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeline: list[tuple[object, ...]] = []
    clock = FakeMonotonicClock((201,), timeline)
    monkeypatch.setattr("time.monotonic_ns", clock)
    read_gate = threading.Event()
    fake_serial = FakeSerial(
        read_results=(b"",),
        read_gates=(read_gate,),
        observation_timeline=timeline,
    )
    backend, _ = _backend(fake_serial)
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)
    stop_task: asyncio.Task[AcquisitionState] | None = None

    try:
        await acquisition.start(backend)
        await _wait_for_thread_event(fake_serial.read_started[0])
        stop_task = asyncio.create_task(acquisition.stop())
        await _wait_for_thread_event(fake_serial.cancel_read_called)

        assert acquisition.state is AcquisitionState.STOPPING
        assert fake_serial.close_calls == 0
        read_gate.set()
        assert await asyncio.wait_for(stop_task, timeout=2.0) is (
            AcquisitionState.STOPPED
        )
    finally:
        read_gate.set()
        if stop_task is not None and not stop_task.done():
            stop_task.cancel()
            with suppress(asyncio.CancelledError):
                await stop_task

    timeline_kinds = [event[0] for event in timeline]
    assert timeline_kinds.index("cancel_read") < timeline_kinds.index(
        "read_return"
    )
    assert timeline_kinds.index("read_return") < timeline_kinds.index(
        "serial_close"
    )
    assert fake_serial.close_calls == 1
    segment_ends = [
        record
        for record in recorder.snapshot()
        if isinstance(record, SegmentEndedEvidence)
    ]
    assert len(segment_ends) == 1
    assert segment_ends[0].reason is SegmentEndReason.EXPLICIT_STOP


@pytest.mark.asyncio
async def test_real_basic_adapter_device_loss_ends_segment_as_disconnected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock(()))
    fake_serial = FakeSerial(
        read_results=(
            serial.SerialException(errno.ENODEV, "unrelated diagnostic"),
        )
    )
    backend, _ = _backend(fake_serial)
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)

    await acquisition.start(backend)
    assert await _wait_for_termination(acquisition) is AcquisitionState.STOPPED

    assert acquisition.failure is None
    assert fake_serial.close_calls == 1
    records = recorder.snapshot()
    assert [record.sequence for record in records] == [0, 1]
    assert [type(record) for record in records] == [
        SegmentStartedEvidence,
        SegmentEndedEvidence,
    ]
    segment_end = records[1]
    assert isinstance(segment_end, SegmentEndedEvidence)
    assert segment_end.reason is SegmentEndReason.DISCONNECTED


@pytest.mark.asyncio
async def test_real_basic_adapter_ambiguous_read_is_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock(()))
    fake_serial = FakeSerial(
        read_results=(serial.SerialException(errno.EIO, "read diagnostic"),)
    )
    backend, _ = _backend(fake_serial)
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)

    await acquisition.start(backend)
    assert await _wait_for_termination(acquisition) is AcquisitionState.FAILED

    assert acquisition.failure is not None
    assert acquisition.failure.kind is AcquisitionFailureKind.TRANSPORT_FAILURE
    failure = acquisition.failure.cause
    assert isinstance(failure, NormalizedBackendFailure)
    assert failure.operation is BackendFailureOperation.READ
    assert failure.kind is BackendFailureKind.IO_FAILURE
    assert failure.__cause__ is None
    assert failure.__context__ is None
    assert not isinstance(failure, serial.SerialException)
    assert fake_serial.close_calls == 1
    records = recorder.snapshot()
    assert [record.sequence for record in records] == [0, 1]
    segment_end = records[1]
    assert isinstance(segment_end, SegmentEndedEvidence)
    assert segment_end.reason is SegmentEndReason.TRANSPORT_FAILURE


@pytest.mark.asyncio
async def test_real_basic_adapter_rejects_second_owner_while_acquiring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock((301,)))
    read_gate = threading.Event()
    fake_serial = FakeSerial(
        read_results=(b"",),
        read_gates=(read_gate,),
    )
    backend, _ = _backend(fake_serial)
    replacement_backend, replacement_factory = _backend(FakeSerial())
    recorder = InMemoryEvidenceRecorder()
    acquisition = Acquisition(recorder)

    await acquisition.start(backend)
    await _wait_for_thread_event(fake_serial.read_started[0])
    assert acquisition.state is AcquisitionState.ACQUIRING

    with pytest.raises(AcquisitionAlreadyActiveError):
        await acquisition.start(replacement_backend)
    assert replacement_factory.calls == []
    assert acquisition.state is AcquisitionState.ACQUIRING

    assert await _stop_after_cancel(
        acquisition,
        fake_serial,
        read_gate,
    ) is AcquisitionState.STOPPED
