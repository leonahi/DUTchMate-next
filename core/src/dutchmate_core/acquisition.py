"""Exclusive continuous acquisition into authoritative evidence."""

import asyncio
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import cast
from uuid import uuid4

from dutchmate_core.backend import (
    Backend,
    BackendConnection,
    BackendWriteResult,
    UartWriteConnection,
)
from dutchmate_core.evidence import (
    EvidenceRecorder,
    PendingObserverLossEvidence,
    PendingRxBytesEvidence,
    PendingSegmentEndedEvidence,
    PendingSegmentStartedEvidence,
)
from dutchmate_core.model import (
    BackendCapability,
    BackendObservationTimestamp,
    ConnectionDescriptor,
    ConnectionInstanceId,
    Disconnected,
    InvalidTimestampOriginResetError,
    ObserverLossObserved,
    ObserverLossProvenanceMismatchError,
    ObserverReportsUartLoss,
    RxBytesObserved,
    SegmentEndReason,
    SegmentId,
    SegmentProvenance,
    TimestampOriginReset,
    TimestampRegressionError,
    compare_backend_observation_timestamps,
    validate_backend_observation_timestamp,
)


class AcquisitionState(StrEnum):
    IDLE = "idle"
    STARTING = "starting"
    ACQUIRING = "acquiring"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class AcquisitionFailureKind(StrEnum):
    CAPABILITY_REJECTION = "capability_rejection"
    RECORDING_FAILURE = "recording_failure"
    TRANSPORT_FAILURE = "transport_failure"


@dataclass(frozen=True, slots=True)
class AcquisitionFailure:
    kind: AcquisitionFailureKind
    cause: Exception


class AcquisitionTerminalTrigger(StrEnum):
    EXPLICIT_STOP = "explicit_stop"
    DISCONNECTED = "disconnected"
    CAPABILITY_REJECTION = "capability_rejection"
    RECORDING_FAILURE = "recording_failure"
    TRANSPORT_FAILURE = "transport_failure"


@dataclass(frozen=True, slots=True)
class AcquisitionSnapshot:
    """Normalized facts; primary failure excludes physical-close failures."""

    state: AcquisitionState
    descriptor: ConnectionDescriptor | None = None
    provenance: SegmentProvenance | None = None
    terminal_trigger: AcquisitionTerminalTrigger | None = None
    primary_failure_kind: AcquisitionFailureKind | None = None
    close_failed: bool = False
    physical_release_confirmed: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.state, AcquisitionState):
            raise TypeError("acquisition state must be declared")
        for name, expected_type in (
            ("descriptor", ConnectionDescriptor),
            ("provenance", SegmentProvenance),
            ("terminal_trigger", AcquisitionTerminalTrigger),
            ("primary_failure_kind", AcquisitionFailureKind),
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, expected_type):
                raise TypeError(f"{name} must be a normalized immutable value")
        for name in ("close_failed", "physical_release_confirmed"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be boolean")


@dataclass(slots=True)
class _AcquisitionGeneration:
    snapshot: AcquisitionSnapshot
    terminated: asyncio.Event = field(default_factory=asyncio.Event)
    startup_settled: asyncio.Event = field(default_factory=asyncio.Event)
    consumer_task: asyncio.Task[None] | None = None
    close_task: asyncio.Task[None] | None = None
    write_task: asyncio.Task[BackendWriteResult] | None = None
    write_sealed: bool = True


class AcquisitionAlreadyActiveError(RuntimeError):
    """Raised when a second owner attempts to start acquisition."""


class BackendStreamEndedError(RuntimeError):
    """Raised when a backend stream ends without disconnect or owner stop."""


class UnsupportedBackendCapabilityError(RuntimeError):
    """Raised when a connection cannot provide the requested UART capability."""


class Acquisition:
    """Own one backend connection and its sole continuous event consumer."""

    def __init__(self, recorder: EvidenceRecorder) -> None:
        self._recorder = recorder
        self._state = AcquisitionState.IDLE
        self._failure: AcquisitionFailure | None = None
        self._connection: BackendConnection | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._connection_close_unconfirmed = False
        self._generation = _AcquisitionGeneration(
            AcquisitionSnapshot(AcquisitionState.IDLE)
        )
        self._generation.startup_settled.set()
        self._terminated = self._generation.terminated
        self._lifecycle_lock = asyncio.Lock()

    @property
    def state(self) -> AcquisitionState:
        return self._state

    @property
    def failure(self) -> AcquisitionFailure | None:
        return self._failure

    def snapshot(self) -> AcquisitionSnapshot:
        """Return current or historical immutable acquisition facts."""
        return self._generation.snapshot

    def submit_uart_write(self, payload: bytes) -> asyncio.Future[BackendWriteResult]:
        """Admit one exact-byte write on the private, currently owned connection.

        Registration commits the invocation before yielding. The returned waiter
        can be cancelled without retracting that commitment or cancelling the
        generation's write owner. Profile/policy and audit belong to the caller.
        """
        generation = self._generation
        connection = self._connection
        if (
            self._state is not AcquisitionState.ACQUIRING
            or generation.write_sealed
            or connection is None
        ):
            raise RuntimeError("acquisition is not accepting UART writes")
        if type(payload) is not bytes:
            raise TypeError("UART payload must be exact bytes")
        if not 1 <= len(payload) <= 4096:
            raise ValueError("UART payload must contain 1 through 4096 bytes")
        if not connection.descriptor.capabilities.supports(BackendCapability.UART_SEND):
            raise UnsupportedBackendCapabilityError(
                "backend connection does not report uart_send"
            )
        if not callable(getattr(connection, "write", None)):
            raise TypeError("backend connection does not implement UART write")
        if generation.write_task is not None and not generation.write_task.done():
            raise RuntimeError("a UART write is already admitted")
        writer = cast(UartWriteConnection, connection)
        generation.write_task = asyncio.create_task(
            writer.write(payload), name="dutchmate-uart-write"
        )
        return asyncio.shield(generation.write_task)

    def _set_state(self, state: AcquisitionState) -> None:
        self._state = state
        self._generation.snapshot = replace(self._generation.snapshot, state=state)

    def _record_primary_failure(self, kind: AcquisitionFailureKind) -> None:
        snapshot = self._generation.snapshot
        trigger = snapshot.terminal_trigger
        if trigger is None or trigger is AcquisitionTerminalTrigger.EXPLICIT_STOP:
            trigger = AcquisitionTerminalTrigger(kind.value)
        self._generation.snapshot = replace(
            snapshot,
            primary_failure_kind=snapshot.primary_failure_kind or kind,
            terminal_trigger=trigger,
        )

    def _record_explicit_stop(self) -> None:
        if self._generation.snapshot.terminal_trigger is None:
            self._generation.snapshot = replace(
                self._generation.snapshot,
                terminal_trigger=AcquisitionTerminalTrigger.EXPLICIT_STOP,
            )

    async def start(self, backend: Backend) -> ConnectionInstanceId:
        async with self._lifecycle_lock:
            if (
                self._state
                in {
                    AcquisitionState.STARTING,
                    AcquisitionState.ACQUIRING,
                    AcquisitionState.STOPPING,
                }
                or self._connection_close_unconfirmed
            ):
                raise AcquisitionAlreadyActiveError(
                    "authoritative acquisition is already active"
                )

            generation = _AcquisitionGeneration(
                AcquisitionSnapshot(
                    AcquisitionState.STARTING, physical_release_confirmed=False
                )
            )
            self._generation = generation
            self._state = AcquisitionState.STARTING
            self._failure = None
            termination_event = generation.terminated
            self._terminated = termination_event
            try:
                return await self._start_generation(backend, termination_event)
            finally:
                generation.startup_settled.set()

    async def _start_generation(
        self, backend: Backend, termination_event: asyncio.Event
    ) -> ConnectionInstanceId:
        try:
            connection = await backend.open()
        except Exception as open_error:
            self._record_primary_failure(AcquisitionFailureKind.TRANSPORT_FAILURE)
            self._failure = AcquisitionFailure(
                kind=AcquisitionFailureKind.TRANSPORT_FAILURE, cause=open_error
            )
            self._set_state(AcquisitionState.FAILED)
            termination_event.set()
            raise
        self._connection = connection
        self._close_task = None
        self._connection_close_unconfirmed = True
        descriptor = connection.descriptor
        self._generation.snapshot = replace(
            self._generation.snapshot, descriptor=descriptor
        )
        if not descriptor.capabilities.supports(BackendCapability.UART_RECEIVE):
            capability_error = UnsupportedBackendCapabilityError(
                "backend connection does not report uart_receive"
            )
            await self._fail(
                AcquisitionFailureKind.CAPABILITY_REJECTION,
                capability_error,
                connection,
            )
            termination_event.set()
            raise capability_error
        connection_id = ConnectionInstanceId(uuid4().hex)
        segment_id = SegmentId(uuid4().hex)
        provenance = SegmentProvenance(
            connection_id=connection_id,
            segment_id=segment_id,
            capabilities=descriptor.capabilities,
            backend_observation_timestamp_domain=(
                descriptor.backend_observation_timestamp_domain
            ),
            loss_observability=descriptor.loss_observability,
            connection_provenance=descriptor.connection_provenance,
        )
        try:
            await self._recorder.append(PendingSegmentStartedEvidence(provenance))
        except Exception as error:
            await self._fail(
                AcquisitionFailureKind.RECORDING_FAILURE, error, connection
            )
            termination_event.set()
            raise
        self._generation.snapshot = replace(
            self._generation.snapshot, provenance=provenance
        )
        self._set_state(AcquisitionState.ACQUIRING)
        self._generation.write_sealed = False
        self._consumer_task = asyncio.create_task(
            self._consume(connection, provenance, termination_event),
            name=f"dutchmate-rx-{connection_id.value}",
        )
        self._generation.consumer_task = self._consumer_task
        return connection_id

    async def stop(self) -> AcquisitionState:
        async with self._lifecycle_lock:
            self._generation.write_sealed = True
            if self._state in {AcquisitionState.STOPPED, AcquisitionState.FAILED}:
                return self._state
            if self._state is AcquisitionState.IDLE:
                self._record_explicit_stop()
                self._set_state(AcquisitionState.STOPPED)
                self._terminated.set()
                return self._state
            termination_event = self._terminated
            if self._state is AcquisitionState.STOPPING:
                wait_for_existing_teardown = True
                connection = None
                consumer_task = None
            else:
                wait_for_existing_teardown = False
                self._set_state(AcquisitionState.STOPPING)
                connection = self._connection
                consumer_task = self._consumer_task

        if wait_for_existing_teardown:
            await termination_event.wait()
            return self._state

        if connection is not None:
            close_error = await self._close_connection(connection)
            if close_error is not None:
                self._record_explicit_stop()
                if consumer_task is not None and not consumer_task.done():
                    consumer_task.cancel()
                    try:
                        await consumer_task
                    except asyncio.CancelledError:
                        pass
                if self._failure is None:
                    self._failure = AcquisitionFailure(
                        kind=AcquisitionFailureKind.TRANSPORT_FAILURE,
                        cause=close_error,
                    )
                self._set_state(AcquisitionState.FAILED)
                termination_event.set()
                return self._state
        if consumer_task is not None:
            await consumer_task
        if self._state is AcquisitionState.STOPPING:
            self._record_explicit_stop()
            self._set_state(AcquisitionState.STOPPED)
        termination_event.set()
        return self._state

    async def wait_terminated(self) -> AcquisitionState:
        termination_event = self._terminated
        await termination_event.wait()
        return self._state

    async def join_terminated(self) -> AcquisitionSnapshot:
        """Join this generation's startup, consumer and close, not just its event.

        A later start cannot change the captured result. Shield task joins so a
        cancelled join waiter cannot cancel the authoritative consumer/close.
        Task failures are already represented by the normalized snapshot.
        """
        generation = self._generation
        await generation.startup_settled.wait()
        await generation.terminated.wait()
        tasks = tuple(
            task
            for task in (generation.consumer_task, generation.close_task)
            if task is not None
        )
        if tasks:
            await asyncio.shield(asyncio.gather(*tasks, return_exceptions=True))
        return generation.snapshot

    async def _consume(
        self,
        connection: BackendConnection,
        provenance: SegmentProvenance,
        termination_event: asyncio.Event,
    ) -> None:
        last_recorded_timestamp: BackendObservationTimestamp | None = None
        try:
            async for event in connection.events():
                if isinstance(event, RxBytesObserved):
                    try:
                        _validate_timestamp_progression(
                            event.observed_at,
                            last_recorded_timestamp,
                            provenance,
                        )
                    except Exception as error:
                        await self._terminate_transport_failure(
                            provenance,
                            error,
                            connection,
                        )
                        return
                    try:
                        await self._recorder.append(
                            PendingRxBytesEvidence(
                                connection_id=provenance.connection_id,
                                segment_id=provenance.segment_id,
                                payload=event.payload,
                                observed_at=event.observed_at,
                            )
                        )
                    except Exception as error:
                        await self._fail(
                            AcquisitionFailureKind.RECORDING_FAILURE,
                            error,
                            connection,
                        )
                        return
                    last_recorded_timestamp = event.observed_at
                elif isinstance(event, ObserverLossObserved):
                    try:
                        _validate_timestamp_progression(
                            event.observed_at,
                            last_recorded_timestamp,
                            provenance,
                        )
                        loss_observability = provenance.loss_observability
                        if not isinstance(
                            loss_observability,
                            ObserverReportsUartLoss,
                        ) or (
                            event.observer_id != loss_observability.observer_id
                            or event.scope != loss_observability.scope
                        ):
                            raise ObserverLossProvenanceMismatchError(
                                "observer loss does not match the current "
                                "observer and scope"
                            )
                    except Exception as error:
                        await self._terminate_transport_failure(
                            provenance,
                            error,
                            connection,
                        )
                        return
                    try:
                        await self._recorder.append(
                            PendingObserverLossEvidence(
                                connection_id=provenance.connection_id,
                                segment_id=provenance.segment_id,
                                observer_id=event.observer_id,
                                scope=event.scope,
                                cause=event.cause,
                                lost_bytes=event.lost_bytes,
                                observed_at=event.observed_at,
                            )
                        )
                    except Exception as error:
                        await self._fail(
                            AcquisitionFailureKind.RECORDING_FAILURE,
                            error,
                            connection,
                        )
                        return
                    last_recorded_timestamp = event.observed_at
                elif isinstance(event, TimestampOriginReset):
                    current_domain = provenance.backend_observation_timestamp_domain
                    new_domain = event.new_backend_observation_timestamp_domain
                    if (
                        new_domain.domain_id == current_domain.domain_id
                        or new_domain.origin_id == current_domain.origin_id
                    ):
                        await self._terminate_transport_failure(
                            provenance,
                            InvalidTimestampOriginResetError(
                                "timestamp origin reset must establish a new "
                                "domain and origin"
                            ),
                            connection,
                        )
                        return
                    new_provenance = SegmentProvenance(
                        connection_id=provenance.connection_id,
                        segment_id=SegmentId(uuid4().hex),
                        capabilities=provenance.capabilities,
                        backend_observation_timestamp_domain=new_domain,
                        loss_observability=provenance.loss_observability,
                        connection_provenance=provenance.connection_provenance,
                    )
                    try:
                        await self._append_segment_end(
                            provenance,
                            SegmentEndReason.TIMESTAMP_ORIGIN_RESET,
                        )
                        await self._recorder.append(
                            PendingSegmentStartedEvidence(new_provenance)
                        )
                    except Exception as error:
                        await self._fail(
                            AcquisitionFailureKind.RECORDING_FAILURE,
                            error,
                            connection,
                        )
                        return
                    provenance = new_provenance
                    self._generation.snapshot = replace(
                        self._generation.snapshot, provenance=provenance
                    )
                    last_recorded_timestamp = None
                elif isinstance(event, Disconnected):
                    self._generation.write_sealed = True
                    self._generation.snapshot = replace(
                        self._generation.snapshot,
                        terminal_trigger=AcquisitionTerminalTrigger.DISCONNECTED,
                    )
                    try:
                        await self._append_segment_end(
                            provenance,
                            SegmentEndReason.DISCONNECTED,
                        )
                    except Exception as error:
                        await self._fail(
                            AcquisitionFailureKind.RECORDING_FAILURE,
                            error,
                            connection,
                        )
                        return
                    self._set_state(AcquisitionState.STOPPING)
                    close_error = await self._close_connection(connection)
                    if close_error is not None:
                        self._failure = AcquisitionFailure(
                            kind=AcquisitionFailureKind.TRANSPORT_FAILURE,
                            cause=close_error,
                        )
                        self._set_state(AcquisitionState.FAILED)
                    else:
                        self._set_state(AcquisitionState.STOPPED)
                    return

            if self._state is AcquisitionState.STOPPING:
                try:
                    await self._append_segment_end(
                        provenance,
                        SegmentEndReason.EXPLICIT_STOP,
                    )
                except Exception as error:
                    await self._fail(
                        AcquisitionFailureKind.RECORDING_FAILURE,
                        error,
                        connection,
                    )
                    return
                self._record_explicit_stop()
                return

            transport_error = BackendStreamEndedError(
                "backend stream ended without disconnect or owner stop"
            )
            await self._terminate_transport_failure(
                provenance,
                transport_error,
                connection,
            )
        except Exception as error:
            await self._terminate_transport_failure(
                provenance,
                error,
                connection,
            )
        finally:
            if self._state in {AcquisitionState.STOPPED, AcquisitionState.FAILED}:
                termination_event.set()

    async def _append_segment_end(
        self,
        provenance: SegmentProvenance,
        reason: SegmentEndReason,
    ) -> None:
        await self._recorder.append(
            PendingSegmentEndedEvidence(
                connection_id=provenance.connection_id,
                segment_id=provenance.segment_id,
                reason=reason,
            )
        )

    async def _fail(
        self,
        kind: AcquisitionFailureKind,
        cause: Exception,
        connection: BackendConnection,
    ) -> None:
        self._generation.write_sealed = True
        self._record_primary_failure(kind)
        if self._failure is None:
            self._failure = AcquisitionFailure(kind=kind, cause=cause)
        self._set_state(AcquisitionState.STOPPING)
        await self._close_connection(connection)
        self._set_state(AcquisitionState.FAILED)

    async def _close_connection(
        self,
        connection: BackendConnection,
    ) -> Exception | None:
        generation = self._generation
        generation.write_sealed = True
        if self._close_task is None:
            self._close_task = asyncio.create_task(
                self._join_write_and_close(generation, connection)
            )
            generation.close_task = self._close_task
        try:
            await asyncio.shield(self._close_task)
        except Exception as error:
            return error
        return None

    async def _join_write_and_close(
        self,
        generation: _AcquisitionGeneration,
        connection: BackendConnection,
    ) -> None:
        # Only backend settlement belongs here: waiting for the caller's audit
        # would create a dependency cycle with acquisition teardown.
        if generation.write_task is not None:
            await asyncio.gather(generation.write_task, return_exceptions=True)
        try:
            await connection.close()
        except Exception:
            generation.snapshot = replace(generation.snapshot, close_failed=True)
            raise
        self._connection_close_unconfirmed = False
        generation.snapshot = replace(
            generation.snapshot, physical_release_confirmed=True
        )

    async def _terminate_transport_failure(
        self,
        provenance: SegmentProvenance,
        cause: Exception,
        connection: BackendConnection,
    ) -> None:
        self._generation.write_sealed = True
        self._record_primary_failure(AcquisitionFailureKind.TRANSPORT_FAILURE)
        try:
            await self._append_segment_end(
                provenance,
                SegmentEndReason.TRANSPORT_FAILURE,
            )
        except Exception as recording_error:
            await self._fail(
                AcquisitionFailureKind.RECORDING_FAILURE,
                recording_error,
                connection,
            )
            return
        await self._fail(
            AcquisitionFailureKind.TRANSPORT_FAILURE,
            cause,
            connection,
        )


def _validate_timestamp_progression(
    timestamp: BackendObservationTimestamp,
    last_recorded_timestamp: BackendObservationTimestamp | None,
    provenance: SegmentProvenance,
) -> None:
    domain = provenance.backend_observation_timestamp_domain
    validate_backend_observation_timestamp(timestamp, domain)
    if last_recorded_timestamp is None:
        return
    if (
        compare_backend_observation_timestamps(
            last_recorded_timestamp,
            domain,
            timestamp,
            domain,
        )
        > 0
    ):
        raise TimestampRegressionError(
            "backend observation timestamp decreased within the current "
            "domain and origin"
        )
