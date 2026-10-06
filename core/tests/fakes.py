"""Hardware-free test doubles for the normalized backend boundary."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from dutchmate_core.backend import Backend, EventStreamAlreadyConsumedError
from dutchmate_core.evidence import (
    InMemoryEvidenceRecorder,
    PendingEvidenceRecord,
)
from dutchmate_core.model import (
    BackendCapabilities,
    BackendCapability,
    BackendConnectionProvenance,
    BackendEvent,
    BackendObservationTimestamp,
    BackendObservationTimestampDomain,
    ConnectionDescriptor,
    Disconnected,
    EvidenceRecord,
    LossObservability,
    ObserverLossCause,
    ObserverLossObserved,
    ObserverReportsUartLoss,
    RxBytesObserved,
    TimestampMeaning,
    TimestampObserver,
    TimestampOriginReset,
    TimestampUnit,
    UpstreamLossNotObservable,
)


class _EndOfStream:
    pass


_END_OF_STREAM = _EndOfStream()


class FixtureLifecycleGate:
    """Default-open, test-owned checkpoint with no elapsed-time behavior."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.allow = asyncio.Event()
        self.allow.set()

    async def enter(self) -> None:
        self.entered.set()
        await self.allow.wait()


class BasicShapedBackendConnection:
    """Small host-timestamped, loss-unobservable backend connection fake."""

    def __init__(
        self,
        *,
        timestamp_domain: BackendObservationTimestampDomain | None = None,
        capabilities: BackendCapabilities | None = None,
        loss_observability: LossObservability | None = None,
        connection_provenance: BackendConnectionProvenance | None = None,
    ) -> None:
        initial_timestamp_domain = timestamp_domain or (
            BackendObservationTimestampDomain(
                domain_id="host-observer-1",
                observer=TimestampObserver.HOST,
                meaning=TimestampMeaning.OBSERVATION,
                unit=TimestampUnit.NANOSECOND,
                origin_id="host-process-1",
            )
        )
        self.descriptor = ConnectionDescriptor(
            capabilities=capabilities
            or BackendCapabilities(frozenset({BackendCapability.UART_RECEIVE})),
            backend_observation_timestamp_domain=initial_timestamp_domain,
            loss_observability=loss_observability or UpstreamLossNotObservable(),
            connection_provenance=(
                connection_provenance or BackendConnectionProvenance()
            ),
        )
        self._current_timestamp_domain = initial_timestamp_domain
        self._events: asyncio.Queue[BackendEvent | _EndOfStream] = asyncio.Queue()
        self._stream_claimed = False
        self._terminal_enqueued = False
        self.closed = False
        self.read_gate = FixtureLifecycleGate()
        self.event_gate = FixtureLifecycleGate()
        self.consumer_exit_gate = FixtureLifecycleGate()
        self.close_gate = FixtureLifecycleGate()
        self.consumer_calls = 0
        self.close_calls = 0

    def events(self) -> AsyncIterator[BackendEvent]:
        if self._stream_claimed:
            raise EventStreamAlreadyConsumedError
        self._stream_claimed = True
        self.consumer_calls += 1
        return self._iterate_events()

    async def _iterate_events(self) -> AsyncIterator[BackendEvent]:
        try:
            while True:
                await self.read_gate.enter()
                event = await self._events.get()
                await self.event_gate.enter()
                if isinstance(event, _EndOfStream):
                    return
                yield event
                if isinstance(event, Disconnected):
                    return
        finally:
            await self.consumer_exit_gate.enter()

    async def emit_rx(
        self,
        payload: bytes,
        *,
        timestamp: int,
        domain_id: str | None = None,
    ) -> None:
        if self._terminal_enqueued:
            raise RuntimeError("connection stream is terminal")
        await self._events.put(
            RxBytesObserved(
                payload=payload,
                observed_at=BackendObservationTimestamp(
                    domain_id=domain_id or self._current_timestamp_domain.domain_id,
                    value=timestamp,
                ),
            )
        )

    async def reset_timestamp_origin(
        self,
        new_domain: BackendObservationTimestampDomain,
    ) -> None:
        if self._terminal_enqueued:
            raise RuntimeError("connection stream is terminal")
        await self._events.put(
            TimestampOriginReset(new_backend_observation_timestamp_domain=new_domain)
        )
        self._current_timestamp_domain = new_domain

    async def disconnect(self, reason: str = "fixture disconnected") -> None:
        if self._terminal_enqueued:
            raise RuntimeError("connection stream is terminal")
        self._terminal_enqueued = True
        await self._events.put(Disconnected(reason=reason))

    async def end_stream_unexpectedly(self) -> None:
        if self._terminal_enqueued:
            raise RuntimeError("connection stream is terminal")
        self._terminal_enqueued = True
        await self._events.put(_END_OF_STREAM)

    async def close(self) -> None:
        self.close_calls += 1
        if self.closed:
            return
        await self.close_gate.enter()
        self.closed = True
        if not self._terminal_enqueued:
            self._terminal_enqueued = True
            await self._events.put(_END_OF_STREAM)


class BasicShapedBackend:
    def __init__(self, connection: BasicShapedBackendConnection | None = None) -> None:
        self.connection = connection or BasicShapedBackendConnection()
        self.open_gate = FixtureLifecycleGate()
        self.open_calls = 0

    async def open(self) -> BasicShapedBackendConnection:
        self.open_calls += 1
        await self.open_gate.enter()
        return self.connection


class FixtureBackendOpenFailure(RuntimeError):
    """Controlled failure raised before a fixture connection is returned."""


class FailingOpenBackend:
    def __init__(self) -> None:
        self.failure = FixtureBackendOpenFailure("fixture backend open failed")

    async def open(self) -> BasicShapedBackendConnection:
        raise self.failure


class FixtureConnectionCloseFailure(RuntimeError):
    """Controlled failure raised by fixture connection teardown."""


class BlockingCloseBackendConnection(BasicShapedBackendConnection):
    def __init__(self) -> None:
        super().__init__()
        self.close_started = asyncio.Event()
        self.allow_close = asyncio.Event()

    async def close(self) -> None:
        if self.closed:
            return
        self.close_started.set()
        await self.allow_close.wait()
        await super().close()


class BlockingFailingCloseBackendConnection(BasicShapedBackendConnection):
    def __init__(self) -> None:
        super().__init__()
        self.close_started = asyncio.Event()
        self.allow_close_failure = asyncio.Event()

    async def close(self) -> None:
        self.close_started.set()
        await self.allow_close_failure.wait()
        raise FixtureConnectionCloseFailure("fixture connection close failed")


class FailingCloseBackendConnection(BasicShapedBackendConnection):
    async def close(self) -> None:
        raise FixtureConnectionCloseFailure("fixture connection close failed")


class EnhancedShapedBackendConnection(BasicShapedBackendConnection):
    """Minimal device-timestamped, observer-loss-reporting test fixture."""

    OBSERVER_ID = "fixture-device-uart-observer"
    LOSS_SCOPE = "fixture-uart-rx-buffer"

    def __init__(self) -> None:
        timestamp_domain = BackendObservationTimestampDomain(
            domain_id="fixture-device-domain-1",
            observer=TimestampObserver.DEVICE,
            meaning=TimestampMeaning.OBSERVATION,
            unit=TimestampUnit.TICK,
            origin_id="fixture-device-origin-1",
        )
        super().__init__(
            timestamp_domain=timestamp_domain,
            loss_observability=ObserverReportsUartLoss(
                observer_id=self.OBSERVER_ID,
                scope=self.LOSS_SCOPE,
            ),
        )

    async def emit_observer_loss(
        self,
        *,
        cause: str,
        lost_bytes: int | None,
        timestamp: int,
        observer_id: str | None = None,
        scope: str | None = None,
        domain_id: str | None = None,
    ) -> None:
        if self._terminal_enqueued:
            raise RuntimeError("connection stream is terminal")
        await self._events.put(
            ObserverLossObserved(
                observer_id=observer_id or self.OBSERVER_ID,
                scope=scope or self.LOSS_SCOPE,
                cause=ObserverLossCause(cause),
                lost_bytes=lost_bytes,
                observed_at=BackendObservationTimestamp(
                    domain_id=domain_id
                    or self._current_timestamp_domain.domain_id,
                    value=timestamp,
                ),
            )
        )

    async def disconnect(self, reason: str = "fixture observer link ended") -> None:
        await super().disconnect(reason)


class EnhancedShapedBackend:
    def __init__(self, connection: EnhancedShapedBackendConnection | None = None) -> None:
        self.connection = connection or EnhancedShapedBackendConnection()
        self.open_gate = FixtureLifecycleGate()
        self.open_calls = 0

    async def open(self) -> EnhancedShapedBackendConnection:
        self.open_calls += 1
        await self.open_gate.enter()
        return self.connection


type ShapedBackendConnection = (
    BasicShapedBackendConnection | EnhancedShapedBackendConnection
)


@dataclass(frozen=True, slots=True)
class BackendFixture:
    backend: Backend
    connection: ShapedBackendConnection


type BackendFixtureFactory = Callable[[], BackendFixture]


def basic_backend_fixture() -> BackendFixture:
    connection = BasicShapedBackendConnection()
    return BackendFixture(BasicShapedBackend(connection), connection)


def enhanced_backend_fixture() -> BackendFixture:
    connection = EnhancedShapedBackendConnection()
    return BackendFixture(EnhancedShapedBackend(connection), connection)


BACKEND_FIXTURE_FACTORIES: tuple[BackendFixtureFactory, ...] = (
    basic_backend_fixture,
    enhanced_backend_fixture,
)


class FixtureRecorderFailure(RuntimeError):
    """Explicit failure raised by the controlled recorder test double."""


class RejectingEvidenceRecorder:
    """Delegate to the real recorder until one configured append is rejected."""

    def __init__(self, *, reject_append_number: int) -> None:
        self._delegate = InMemoryEvidenceRecorder()
        self._reject_append_number = reject_append_number
        self._append_count = 0

    async def append(self, draft: PendingEvidenceRecord) -> EvidenceRecord:
        self._append_count += 1
        if self._append_count == self._reject_append_number:
            raise FixtureRecorderFailure("fixture recorder rejected append")
        return await self._delegate.append(draft)

    def snapshot(self) -> tuple[EvidenceRecord, ...]:
        return self._delegate.snapshot()
