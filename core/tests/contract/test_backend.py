"""Contract tests for one owned normalized backend connection."""

import asyncio
from collections.abc import AsyncIterator, Awaitable
from dataclasses import FrozenInstanceError, replace

import pytest

from dutchmate_core.acquisition import Acquisition, UnsupportedBackendCapabilityError
from dutchmate_core.backend import (
    BackendFailureKind,
    BackendFailureOperation,
    EventStreamAlreadyConsumedError,
    NormalizedBackendFailure,
)
from dutchmate_core.evidence import InMemoryEvidenceRecorder
from dutchmate_core.model import BackendCapabilities, Disconnected, RxBytesObserved
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixtureFactory


@pytest.mark.parametrize("operation", list(BackendFailureOperation))
@pytest.mark.parametrize("kind", list(BackendFailureKind))
def test_normalized_backend_failure_has_only_stable_boundary_values(
    operation: BackendFailureOperation,
    kind: BackendFailureKind,
) -> None:
    failure = NormalizedBackendFailure(
        operation=operation,
        kind=kind,
        detail="diagnostic only",
    )

    assert failure.operation is operation
    assert failure.kind is kind
    assert failure.detail == "diagnostic only"
    assert not hasattr(failure, "serial_exception")
    assert not hasattr(failure, "serial_handle")
    with pytest.raises(FrozenInstanceError):
        failure.kind = BackendFailureKind.IO_FAILURE  # type: ignore[misc]


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_connection_event_stream_has_exactly_one_consumer(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    first_stream = connection.events()

    with pytest.raises(EventStreamAlreadyConsumedError):
        connection.events()

    await connection.close()
    assert [event async for event in first_stream] == []


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_disconnect_is_the_last_observation_in_stream_order(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    await connection.emit_rx(b"before-disconnect", timestamp=10)
    await connection.disconnect("fixture unplugged")

    events = [event async for event in connection.events()]

    assert [type(event) for event in events] == [RxBytesObserved, Disconnected]
    disconnected = events[1]
    assert isinstance(disconnected, Disconnected)
    assert disconnected.reason == "fixture unplugged"


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_close_is_idempotent_and_terminates_the_stream(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    stream = connection.events()

    await connection.close()
    await connection.close()

    assert [event async for event in stream] == []


# T019 fixture checks only: no ObservationRuntime or future US3 behavior.
def _gate(target: object, name: str) -> tuple[asyncio.Event, asyncio.Event]:
    gate = getattr(target, name, None)
    assert gate is not None, f"T019 fixture lifecycle gate missing: {name}"
    entered = getattr(gate, "entered", None)
    allow = getattr(gate, "allow", None)
    assert isinstance(entered, asyncio.Event) and isinstance(allow, asyncio.Event)
    return entered, allow


def _count(target: object, name: str) -> int:
    count = getattr(target, name, None)
    assert isinstance(count, int)
    return count


async def _next[T](stream: AsyncIterator[T]) -> T | None:
    return await anext(stream, None)


async def _drain(stream: AsyncIterator[object]) -> None:
    async for _ in stream:
        pass


async def _bounded[T](work: Awaitable[T]) -> T:
    async with asyncio.timeout(3.0):  # Test watchdog, never a product deadline.
        return await work


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_t019_open_gate_delays_connection_return_without_reopening(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    entered, allow = _gate(fixture.backend, "open_gate")
    allow.clear()
    task = asyncio.create_task(fixture.backend.open())
    try:
        await _bounded(entered.wait())
        assert not task.done() and not fixture.connection.closed
        allow.set()
        assert await _bounded(task) is fixture.connection
        assert _count(fixture.backend, "open_calls") == 1
    finally:
        allow.set()
        await _bounded(asyncio.gather(task, return_exceptions=True))
        await fixture.connection.close()


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.parametrize("stage", ["read_gate", "event_gate"])
@pytest.mark.asyncio
async def test_t019_stream_gate_delays_exact_binary_event_without_another_consumer(
    fixture_factory: BackendFixtureFactory, stage: str
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    entered, allow = _gate(connection, stage)
    allow.clear()
    await connection.emit_rx(b"\x00\xff\r\n", timestamp=7)
    await connection.disconnect()
    stream = connection.events()
    task = asyncio.create_task(_next(stream))
    try:
        await _bounded(entered.wait())
        assert not task.done()
        with pytest.raises(EventStreamAlreadyConsumedError):
            connection.events()
        allow.set()
        event = await _bounded(task)
        assert isinstance(event, RxBytesObserved)
        assert event.payload == b"\x00\xff\r\n"
        assert (
            event.observed_at.domain_id
            == connection.descriptor.backend_observation_timestamp_domain.domain_id
        )
        assert event.observed_at.value == 7
        assert isinstance(await _bounded(anext(stream)), Disconnected)
        assert await _bounded(anext(stream, None)) is None
        assert connection.consumer_calls == 1
    finally:
        allow.set()
        await _bounded(asyncio.gather(task, return_exceptions=True))
        await connection.close()
        await _bounded(_drain(stream))


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_t019_close_and_consumer_exit_gates_preserve_idempotent_stream_end(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    close_entered, close_allow = _gate(connection, "close_gate")
    tail_entered, tail_allow = _gate(connection, "consumer_exit_gate")
    close_allow.clear()
    tail_allow.clear()
    stream = connection.events()
    consumer = asyncio.create_task(_next(stream))
    close = asyncio.create_task(connection.close())
    try:
        await _bounded(close_entered.wait())
        assert not connection.closed and not close.done() and not consumer.done()
        close_allow.set()
        await _bounded(close)
        await _bounded(tail_entered.wait())
        assert connection.closed and not consumer.done()
        # Reclose must not block at or re-enter the physical close checkpoint.
        close_entered.clear()
        close_allow.clear()
        await _bounded(connection.close())
        assert not close_entered.is_set()
        assert connection.close_calls == 2
        tail_allow.set()
        assert await _bounded(consumer) is None
        assert connection.consumer_calls == 1
    finally:
        close_allow.set()
        tail_allow.set()
        await _bounded(asyncio.gather(close, consumer, return_exceptions=True))
        await connection.close()
        await _bounded(_drain(stream))


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_t019_reported_rx_rejection_waits_for_close_gate_without_claiming_reader(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    entered, allow = _gate(connection, "close_gate")
    allow.clear()
    # Reuse the existing reported descriptor; never emulate RX on rejection.
    connection.descriptor = replace(
        connection.descriptor, capabilities=BackendCapabilities(frozenset())
    )
    recorder = InMemoryEvidenceRecorder()
    owner = Acquisition(recorder)
    task = asyncio.create_task(owner.start(fixture.backend))
    try:
        await _bounded(entered.wait())
        assert not task.done() and not connection.closed
        assert connection.consumer_calls == 0
        assert recorder.snapshot() == ()
        allow.set()
        with pytest.raises(UnsupportedBackendCapabilityError):
            await _bounded(task)
        snapshot = await _bounded(owner.join_terminated())
        assert snapshot.physical_release_confirmed and snapshot.provenance is None
        assert _count(fixture.backend, "open_calls") == 1
        assert connection.close_calls == 1
    finally:
        allow.set()
        await _bounded(asyncio.gather(task, return_exceptions=True))
        await owner.stop()
        await _bounded(owner.join_terminated())
