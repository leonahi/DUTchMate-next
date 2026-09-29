"""Exclusive continuous acquisition into authoritative evidence."""

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from dutchmate_core.backend import Backend, BackendConnection
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


class AcquisitionAlreadyActiveError(RuntimeError):
    """Raised when a second owner attempts to start acquisition."""


class BackendStreamEndedError(RuntimeError):
    """Raised when a backend stream ends without disconnect or owner stop."""


class UnsupportedBackendCapabilityError(RuntimeError):
    """Raised when a connection cannot provide authoritative UART RX."""


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
        self._terminated = asyncio.Event()
        self._lifecycle_lock = asyncio.Lock()

    @property
    def state(self) -> AcquisitionState:
        return self._state

    @property
    def failure(self) -> AcquisitionFailure | None:
        return self._failure

    async def start(self, backend: Backend) -> ConnectionInstanceId:
        async with self._lifecycle_lock:
            if self._state in {
                AcquisitionState.STARTING,
                AcquisitionState.ACQUIRING,
                AcquisitionState.STOPPING,
            } or self._connection_close_unconfirmed:
                raise AcquisitionAlreadyActiveError(
                    "authoritative acquisition is already active"
                )

            self._state = AcquisitionState.STARTING
            self._failure = None
            termination_event = asyncio.Event()
            self._terminated = termination_event
            try:
                connection = await backend.open()
            except Exception as open_error:
                self._failure = AcquisitionFailure(
                    kind=AcquisitionFailureKind.TRANSPORT_FAILURE,
                    cause=open_error,
                )
                self._state = AcquisitionState.FAILED
                termination_event.set()
                raise
            self._connection = connection
            self._close_task = None
            self._connection_close_unconfirmed = True
            descriptor = connection.descriptor
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
            )
            try:
                await self._recorder.append(PendingSegmentStartedEvidence(provenance))
            except Exception as error:
                await self._fail(
                    AcquisitionFailureKind.RECORDING_FAILURE,
                    error,
                    connection,
                )
                termination_event.set()
                raise
            self._state = AcquisitionState.ACQUIRING
            self._consumer_task = asyncio.create_task(
                self._consume(connection, provenance, termination_event),
                name=f"dutchmate-rx-{connection_id.value}",
            )
            return connection_id

    async def stop(self) -> AcquisitionState:
        async with self._lifecycle_lock:
            if self._state in {AcquisitionState.STOPPED, AcquisitionState.FAILED}:
                return self._state
            if self._state is AcquisitionState.IDLE:
                self._state = AcquisitionState.STOPPED
                self._terminated.set()
                return self._state
            termination_event = self._terminated
            if self._state is AcquisitionState.STOPPING:
                wait_for_existing_teardown = True
                connection = None
                consumer_task = None
            else:
                wait_for_existing_teardown = False
                self._state = AcquisitionState.STOPPING
                connection = self._connection
                consumer_task = self._consumer_task

        if wait_for_existing_teardown:
            await termination_event.wait()
            return self._state

        if connection is not None:
            close_error = await self._close_connection(connection)
            if close_error is not None:
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
                self._state = AcquisitionState.FAILED
                termination_event.set()
                return self._state
        if consumer_task is not None:
            await consumer_task
        if self._state is AcquisitionState.STOPPING:
            self._state = AcquisitionState.STOPPED
        termination_event.set()
        return self._state

    async def wait_terminated(self) -> AcquisitionState:
        termination_event = self._terminated
        await termination_event.wait()
        return self._state

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
                    last_recorded_timestamp = None
                elif isinstance(event, Disconnected):
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
                    self._state = AcquisitionState.STOPPING
                    close_error = await self._close_connection(connection)
                    if close_error is not None:
                        self._failure = AcquisitionFailure(
                            kind=AcquisitionFailureKind.TRANSPORT_FAILURE,
                            cause=close_error,
                        )
                        self._state = AcquisitionState.FAILED
                    else:
                        self._state = AcquisitionState.STOPPED
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
        if self._failure is None:
            self._failure = AcquisitionFailure(kind=kind, cause=cause)
        self._state = AcquisitionState.STOPPING
        await self._close_connection(connection)
        self._state = AcquisitionState.FAILED

    async def _close_connection(
        self,
        connection: BackendConnection,
    ) -> Exception | None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(connection.close())
        try:
            await self._close_task
        except Exception as error:
            return error
        self._connection_close_unconfirmed = False
        return None

    async def _terminate_transport_failure(
        self,
        provenance: SegmentProvenance,
        cause: Exception,
        connection: BackendConnection,
    ) -> None:
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
