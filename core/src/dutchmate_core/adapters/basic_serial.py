"""Validated values for the receive-only Basic serial backend adapter."""

import asyncio
import errno
import sys
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Protocol, cast
from uuid import uuid4

import serial

from dutchmate_core.backend import (
    BackendFailureKind,
    BackendFailureOperation,
    EventStreamAlreadyConsumedError,
    NormalizedBackendFailure,
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
    RxBytesObserved,
    TimestampMeaning,
    TimestampObserver,
    TimestampUnit,
    UpstreamLossNotObservable,
)


@dataclass(frozen=True, slots=True)
class SerialDeviceSelector:
    """One exact local serial device name selected by the user."""

    device_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.device_name, str):
            raise TypeError("serial device name must be text")
        candidate = self.device_name.strip()
        if not candidate:
            raise ValueError("serial device name must be non-empty")
        if candidate.isdecimal() or candidate.casefold() == "auto":
            raise ValueError("serial device name must be explicit")
        if candidate == "-" or "://" in candidate:
            raise ValueError("serial device name must name a local device")


class SerialDataBits(IntEnum):
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8


class SerialParity(StrEnum):
    NONE = "none"
    EVEN = "even"
    ODD = "odd"


class SerialStopBits(StrEnum):
    ONE = "one"
    TWO = "two"


@dataclass(frozen=True, slots=True)
class SerialConfiguration:
    """Supported requested or library-reported UART settings."""

    baud_rate: int
    data_bits: SerialDataBits
    parity: SerialParity
    stop_bits: SerialStopBits
    hardware_flow_control: bool
    software_flow_control: bool

    def __post_init__(self) -> None:
        if type(self.baud_rate) is not int:
            raise TypeError("serial baud rate must be an integer")
        if self.baud_rate <= 0:
            raise ValueError("serial baud rate must be positive")
        if not isinstance(self.data_bits, SerialDataBits):
            raise TypeError("serial data bits must be declared")
        if not isinstance(self.parity, SerialParity):
            raise TypeError("serial parity must be declared")
        if not isinstance(self.stop_bits, SerialStopBits):
            raise TypeError("serial stop bits must be declared")
        if type(self.hardware_flow_control) is not bool:
            raise TypeError("hardware flow control must be boolean")
        if type(self.software_flow_control) is not bool:
            raise TypeError("software flow control must be boolean")
        if self.hardware_flow_control and self.software_flow_control:
            raise ValueError("simultaneous hardware and software flow control")


class SerialLineState(StrEnum):
    ASSERTED = "asserted"
    DEASSERTED = "deasserted"
    DRIVER_MANAGED = "driver_managed"


@dataclass(frozen=True, slots=True)
class SerialOpenLineIntent:
    """DTR/RTS state requested while the serial handle is still closed."""

    dtr: SerialLineState
    rts: SerialLineState

    def __post_init__(self) -> None:
        if not isinstance(self.dtr, SerialLineState):
            raise TypeError("DTR intent must be declared")
        if not isinstance(self.rts, SerialLineState):
            raise TypeError("RTS intent must be declared")
        if self.dtr is SerialLineState.DRIVER_MANAGED:
            raise ValueError("DTR intent cannot be driver-managed")


@dataclass(frozen=True, slots=True)
class BasicSerialOpenRequest:
    """Validated selector, UART settings, and serial-open line intent."""

    selector: SerialDeviceSelector
    configuration: SerialConfiguration
    line_intent: SerialOpenLineIntent

    def __post_init__(self) -> None:
        if not isinstance(self.selector, SerialDeviceSelector):
            raise TypeError("serial selector must be validated")
        if not isinstance(self.configuration, SerialConfiguration):
            raise TypeError("serial configuration must be validated")
        if not isinstance(self.line_intent, SerialOpenLineIntent):
            raise TypeError("serial-open line intent must be validated")
        rts_is_driver_managed = (
            self.line_intent.rts is SerialLineState.DRIVER_MANAGED
        )
        if rts_is_driver_managed != self.configuration.hardware_flow_control:
            raise ValueError(
                "RTS must be driver-managed exactly when RTS/CTS is enabled"
            )


class SerialOpenApplyStrategy(StrEnum):
    PRECONFIGURED_WHILE_CLOSED = "preconfigured_while_closed"


class SerialOpenTransitionGuarantee(StrEnum):
    NOT_GUARANTEED = "not_guaranteed"


class SerialElectricalVerification(StrEnum):
    NOT_VERIFIED = "not_verified"


@dataclass(frozen=True, slots=True)
class SerialOpenLineProvenance:
    """Requested and library-reported line state with explicit limitations."""

    requested: SerialOpenLineIntent
    apply_strategy: SerialOpenApplyStrategy
    library_reported_dtr: SerialLineState
    library_reported_rts: SerialLineState
    transition_guarantee: SerialOpenTransitionGuarantee
    electrical_verification: SerialElectricalVerification

    def __post_init__(self) -> None:
        if not isinstance(self.requested, SerialOpenLineIntent):
            raise TypeError("requested line intent must be validated")
        if not isinstance(self.apply_strategy, SerialOpenApplyStrategy):
            raise TypeError("serial-open apply strategy must be declared")
        if not isinstance(self.library_reported_dtr, SerialLineState):
            raise TypeError("library-reported DTR state must be declared")
        if self.library_reported_dtr is SerialLineState.DRIVER_MANAGED:
            raise ValueError("library-reported DTR cannot be driver-managed")
        if not isinstance(self.library_reported_rts, SerialLineState):
            raise TypeError("library-reported RTS state must be declared")
        if not isinstance(
            self.transition_guarantee,
            SerialOpenTransitionGuarantee,
        ):
            raise TypeError("serial-open transition guarantee must be declared")
        if not isinstance(
            self.electrical_verification,
            SerialElectricalVerification,
        ):
            raise TypeError("electrical verification must be declared")


class SerialExclusivityMechanism(StrEnum):
    POSIX_PYSERIAL_EXCLUSIVE = "posix_pyserial_exclusive"
    WINDOWS_EXCLUSIVE_HANDLE = "windows_exclusive_handle"


class SerialExclusivityResult(StrEnum):
    OPEN_SUCCEEDED_WITH_REQUESTED_MECHANISM = (
        "open_succeeded_with_requested_mechanism"
    )


@dataclass(frozen=True, slots=True)
class SerialExclusivityProvenance:
    """Platform exclusivity request and the bounded success claim."""

    requested: bool
    mechanism: SerialExclusivityMechanism
    result: SerialExclusivityResult

    def __post_init__(self) -> None:
        if self.requested is not True:
            raise ValueError("serial exclusivity must be requested")
        if not isinstance(self.mechanism, SerialExclusivityMechanism):
            raise TypeError("serial exclusivity mechanism must be declared")
        if not isinstance(self.result, SerialExclusivityResult):
            raise TypeError("serial exclusivity result must be declared")


@dataclass(frozen=True, slots=True)
class BasicSerialConnectionProvenance(BackendConnectionProvenance):
    """Immutable Basic-specific details carried opaquely by shared Core."""

    selected_device_name: str
    opened_device_name: str
    requested_configuration: SerialConfiguration
    effective_configuration: SerialConfiguration
    open_line_provenance: SerialOpenLineProvenance
    exclusivity: SerialExclusivityProvenance

    def __post_init__(self) -> None:
        SerialDeviceSelector(self.selected_device_name)
        if not isinstance(self.opened_device_name, str) or not (
            self.opened_device_name.strip()
        ):
            raise ValueError("opened serial device name must be non-empty")
        if not isinstance(self.requested_configuration, SerialConfiguration):
            raise TypeError("requested serial configuration must be validated")
        if not isinstance(self.effective_configuration, SerialConfiguration):
            raise TypeError("effective serial configuration must be validated")
        if self.effective_configuration != self.requested_configuration:
            raise ValueError("effective serial configuration must match requested")
        if not isinstance(self.open_line_provenance, SerialOpenLineProvenance):
            raise TypeError("serial-open line provenance must be validated")
        if not isinstance(self.exclusivity, SerialExclusivityProvenance):
            raise TypeError("serial exclusivity provenance must be validated")


class _SerialHandle(Protocol):
    port: str | None
    baudrate: int
    bytesize: int
    parity: str
    stopbits: float
    rtscts: bool
    xonxoff: bool
    dsrdtr: bool
    exclusive: bool | None
    dtr: bool
    rts: bool

    @property
    def portstr(self) -> str | None: ...

    def open(self) -> None: ...

    def read(self, size: int = -1) -> bytes: ...

    def cancel_read(self) -> None: ...

    def close(self) -> None: ...


class _SerialFactory(Protocol):
    def __call__(self, *, port: str | None) -> _SerialHandle: ...


@dataclass(frozen=True, slots=True)
class _ReadObservation:
    payload: bytes
    observed_at_ns: int


@dataclass(frozen=True, slots=True)
class _ReadFailure:
    device_lost: bool
    detail: str | None


@dataclass(frozen=True, slots=True)
class _CloseFailure:
    detail: str | None


def _read_and_timestamp_once(
    serial_handle: _SerialHandle,
) -> _ReadObservation | _ReadFailure:
    try:
        payload = serial_handle.read()
    except Exception as error:
        return _ReadFailure(
            device_lost=_is_device_loss(error),
            detail=str(error) or None,
        )
    return _ReadObservation(
        payload=payload,
        observed_at_ns=time.monotonic_ns(),
    )


def _is_device_loss(error: Exception) -> bool:
    error_number = getattr(error, "errno", None)
    windows_error = getattr(error, "winerror", None)
    return (
        error_number in _DEVICE_LOST_ERRNOS
        or windows_error in _WINDOWS_DEVICE_LOST_ERRORS
    )


def _cancel_serial_read(serial_handle: _SerialHandle) -> _CloseFailure | None:
    try:
        serial_handle.cancel_read()
    except Exception as error:
        return _CloseFailure(detail=str(error) or None)
    return None


def _close_serial_handle(serial_handle: _SerialHandle) -> _CloseFailure | None:
    try:
        serial_handle.close()
    except Exception as error:
        return _CloseFailure(detail=str(error) or None)
    return None


class _BasicSerialConnection:
    """Successfully opened serial resource with a normalized descriptor."""

    __slots__ = (
        "_close_task",
        "_closing",
        "_descriptor",
        "_read_task",
        "_serial_handle",
        "_stream_claimed",
    )

    def __init__(
        self,
        descriptor: ConnectionDescriptor,
        serial_handle: _SerialHandle,
    ) -> None:
        self._descriptor = descriptor
        self._serial_handle = serial_handle
        self._stream_claimed = False
        self._closing = False
        self._read_task: asyncio.Task[_ReadObservation | _ReadFailure] | None = (
            None
        )
        self._close_task: asyncio.Task[None] | None = None

    @property
    def descriptor(self) -> ConnectionDescriptor:
        return self._descriptor

    def events(self) -> AsyncIterator[BackendEvent]:
        if self._stream_claimed:
            raise EventStreamAlreadyConsumedError(
                "backend event stream already has an authoritative consumer"
            )
        self._stream_claimed = True
        return self._iterate_events()

    async def _iterate_events(self) -> AsyncIterator[BackendEvent]:
        timestamp_domain_id = (
            self._descriptor.backend_observation_timestamp_domain.domain_id
        )
        while True:
            if self._closing:
                return
            read_task = asyncio.create_task(
                asyncio.to_thread(
                    _read_and_timestamp_once,
                    self._serial_handle,
                )
            )
            self._read_task = read_task
            try:
                outcome = await read_task
            finally:
                if self._read_task is read_task:
                    self._read_task = None
            if self._closing:
                return
            if isinstance(outcome, _ReadFailure):
                if outcome.device_lost:
                    yield Disconnected(reason="device_lost")
                    return
                raise NormalizedBackendFailure(
                    operation=BackendFailureOperation.READ,
                    kind=BackendFailureKind.IO_FAILURE,
                    detail=outcome.detail,
                )
            if not outcome.payload:
                continue
            yield RxBytesObserved(
                payload=outcome.payload,
                observed_at=BackendObservationTimestamp(
                    domain_id=timestamp_domain_id,
                    value=outcome.observed_at_ns,
                ),
            )

    async def close(self) -> None:
        close_task = self._close_task
        if close_task is None:
            close_task = asyncio.create_task(self._close_once())
            self._close_task = close_task
        await close_task

    async def _close_once(self) -> None:
        self._closing = True
        read_task = self._read_task
        failure: _CloseFailure | None = None
        if read_task is not None and not read_task.done():
            failure = _cancel_serial_read(self._serial_handle)
            await read_task

        close_failure = _close_serial_handle(self._serial_handle)
        if failure is None:
            failure = close_failure
        if failure is not None:
            raise NormalizedBackendFailure(
                operation=BackendFailureOperation.CLOSE,
                kind=BackendFailureKind.IO_FAILURE,
                detail=failure.detail,
            )


class BasicSerialBackend:
    """Open one explicitly selected local serial device without discovery."""

    def __init__(
        self,
        selector: SerialDeviceSelector,
        configuration: SerialConfiguration,
        line_intent: SerialOpenLineIntent,
        *,
        _serial_factory: _SerialFactory | None = None,
    ) -> None:
        self._selector = selector
        self._configuration = configuration
        self._line_intent = line_intent
        self._serial_factory = _serial_factory or cast(
            "_SerialFactory",
            serial.Serial,
        )

    async def open(self) -> _BasicSerialConnection:
        request, validation_failure = _validate_open_request(
            self._selector,
            self._configuration,
            self._line_intent,
        )
        if validation_failure is not None:
            raise validation_failure
        assert request is not None

        connection, open_failure = _open_serial_connection(
            request,
            self._serial_factory,
            windows=_running_on_windows(),
        )
        if open_failure is not None:
            raise open_failure
        assert connection is not None
        return connection


def _running_on_windows() -> bool:
    return sys.platform == "win32"


def _validate_open_request(
    selector: SerialDeviceSelector,
    configuration: SerialConfiguration,
    line_intent: SerialOpenLineIntent,
) -> tuple[BasicSerialOpenRequest | None, NormalizedBackendFailure | None]:
    try:
        request = BasicSerialOpenRequest(
            selector=selector,
            configuration=configuration,
            line_intent=line_intent,
        )
    except (TypeError, ValueError) as error:
        return None, _open_failure(
            BackendFailureKind.INVALID_REQUEST,
            error,
        )
    return request, None


def _open_serial_connection(
    request: BasicSerialOpenRequest,
    serial_factory: _SerialFactory,
    *,
    windows: bool,
) -> tuple[_BasicSerialConnection | None, NormalizedBackendFailure | None]:
    serial_handle, construction_failure = _construct_closed_handle(serial_factory)
    if construction_failure is not None:
        return None, construction_failure
    assert serial_handle is not None

    configuration_failure = _configure_closed_handle(
        serial_handle,
        request,
        windows=windows,
    )
    if configuration_failure is not None:
        _best_effort_close(serial_handle)
        return None, configuration_failure

    open_failure = _open_handle(serial_handle)
    if open_failure is not None:
        _best_effort_close(serial_handle)
        return None, open_failure

    descriptor, verification_failure = _build_descriptor(
        serial_handle,
        request,
        windows=windows,
    )
    if verification_failure is not None:
        _best_effort_close(serial_handle)
        return None, verification_failure
    assert descriptor is not None
    return _BasicSerialConnection(descriptor, serial_handle), None


def _construct_closed_handle(
    serial_factory: _SerialFactory,
) -> tuple[_SerialHandle | None, NormalizedBackendFailure | None]:
    try:
        serial_handle = serial_factory(port=None)
    except Exception as error:
        return None, _classify_open_error(error)
    return serial_handle, None


def _configure_closed_handle(
    serial_handle: _SerialHandle,
    request: BasicSerialOpenRequest,
    *,
    windows: bool,
) -> NormalizedBackendFailure | None:
    configuration = request.configuration
    try:
        serial_handle.port = request.selector.device_name
        serial_handle.baudrate = configuration.baud_rate
        serial_handle.bytesize = _SERIAL_DATA_BITS[configuration.data_bits]
        serial_handle.parity = _SERIAL_PARITY[configuration.parity]
        serial_handle.stopbits = _SERIAL_STOP_BITS[configuration.stop_bits]
        serial_handle.rtscts = configuration.hardware_flow_control
        serial_handle.xonxoff = configuration.software_flow_control
        serial_handle.dsrdtr = False
        if not windows:
            serial_handle.exclusive = True
    except Exception as error:
        return _open_failure(
            BackendFailureKind.CONFIGURATION_REJECTED,
            error,
        )

    try:
        serial_handle.dtr = _line_state_to_bool(request.line_intent.dtr)
        if request.line_intent.rts is not SerialLineState.DRIVER_MANAGED:
            serial_handle.rts = _line_state_to_bool(request.line_intent.rts)
    except Exception as error:
        return _open_failure(
            BackendFailureKind.LINE_STATE_SETUP_FAILED,
            error,
        )
    return None


def _open_handle(
    serial_handle: _SerialHandle,
) -> NormalizedBackendFailure | None:
    try:
        serial_handle.open()
    except Exception as error:
        if isinstance(error, ValueError):
            return _open_failure(
                BackendFailureKind.CONFIGURATION_REJECTED,
                error,
            )
        return _classify_open_error(error)
    return None


def _build_descriptor(
    serial_handle: _SerialHandle,
    request: BasicSerialOpenRequest,
    *,
    windows: bool,
) -> tuple[ConnectionDescriptor | None, NormalizedBackendFailure | None]:
    effective_configuration, configuration_failure = _effective_configuration(
        serial_handle
    )
    if configuration_failure is not None:
        return None, configuration_failure
    assert effective_configuration is not None
    if effective_configuration != request.configuration:
        return None, NormalizedBackendFailure(
            operation=BackendFailureOperation.OPEN,
            kind=BackendFailureKind.CONFIGURATION_REJECTED,
            detail="library-reported serial configuration differs from requested",
        )

    line_provenance, line_failure = _line_provenance(serial_handle, request)
    if line_failure is not None:
        return None, line_failure
    assert line_provenance is not None

    opened_device_name = serial_handle.portstr
    if not isinstance(opened_device_name, str) or not opened_device_name.strip():
        return None, NormalizedBackendFailure(
            operation=BackendFailureOperation.OPEN,
            kind=BackendFailureKind.CONFIGURATION_REJECTED,
            detail="serial library did not report an opened device name",
        )

    connection_provenance = BasicSerialConnectionProvenance(
        selected_device_name=request.selector.device_name,
        opened_device_name=opened_device_name,
        requested_configuration=request.configuration,
        effective_configuration=effective_configuration,
        open_line_provenance=line_provenance,
        exclusivity=SerialExclusivityProvenance(
            requested=True,
            mechanism=(
                SerialExclusivityMechanism.WINDOWS_EXCLUSIVE_HANDLE
                if windows
                else SerialExclusivityMechanism.POSIX_PYSERIAL_EXCLUSIVE
            ),
            result=(
                SerialExclusivityResult.OPEN_SUCCEEDED_WITH_REQUESTED_MECHANISM
            ),
        ),
    )
    descriptor = ConnectionDescriptor(
        capabilities=BackendCapabilities(
            frozenset({BackendCapability.UART_RECEIVE})
        ),
        backend_observation_timestamp_domain=BackendObservationTimestampDomain(
            domain_id=uuid4().hex,
            observer=TimestampObserver.HOST,
            meaning=TimestampMeaning.OBSERVATION,
            unit=TimestampUnit.NANOSECOND,
            origin_id=uuid4().hex,
        ),
        loss_observability=UpstreamLossNotObservable(),
        connection_provenance=connection_provenance,
    )
    return descriptor, None


def _effective_configuration(
    serial_handle: _SerialHandle,
) -> tuple[SerialConfiguration | None, NormalizedBackendFailure | None]:
    try:
        effective_configuration = SerialConfiguration(
            baud_rate=serial_handle.baudrate,
            data_bits=_data_bits_from_serial(serial_handle.bytesize),
            parity=_parity_from_serial(serial_handle.parity),
            stop_bits=_stop_bits_from_serial(serial_handle.stopbits),
            hardware_flow_control=serial_handle.rtscts,
            software_flow_control=serial_handle.xonxoff,
        )
    except (TypeError, ValueError, KeyError) as error:
        return None, _open_failure(
            BackendFailureKind.CONFIGURATION_REJECTED,
            error,
        )
    return effective_configuration, None


def _line_provenance(
    serial_handle: _SerialHandle,
    request: BasicSerialOpenRequest,
) -> tuple[SerialOpenLineProvenance | None, NormalizedBackendFailure | None]:
    try:
        library_reported_dtr = _bool_to_line_state(serial_handle.dtr)
        library_reported_rts = (
            SerialLineState.DRIVER_MANAGED
            if request.configuration.hardware_flow_control
            else _bool_to_line_state(serial_handle.rts)
        )
    except (TypeError, ValueError) as error:
        return None, _open_failure(
            BackendFailureKind.LINE_STATE_SETUP_FAILED,
            error,
        )
    return (
        SerialOpenLineProvenance(
            requested=request.line_intent,
            apply_strategy=SerialOpenApplyStrategy.PRECONFIGURED_WHILE_CLOSED,
            library_reported_dtr=library_reported_dtr,
            library_reported_rts=library_reported_rts,
            transition_guarantee=SerialOpenTransitionGuarantee.NOT_GUARANTEED,
            electrical_verification=SerialElectricalVerification.NOT_VERIFIED,
        ),
        None,
    )


def _line_state_to_bool(state: SerialLineState) -> bool:
    if state is SerialLineState.ASSERTED:
        return True
    if state is SerialLineState.DEASSERTED:
        return False
    raise ValueError("driver-managed line state has no static boolean value")


def _bool_to_line_state(value: bool) -> SerialLineState:
    if type(value) is not bool:
        raise TypeError("library-reported line state must be boolean")
    return SerialLineState.ASSERTED if value else SerialLineState.DEASSERTED


def _data_bits_from_serial(value: int) -> SerialDataBits:
    return _SERIAL_DATA_BITS_REVERSE[value]


def _parity_from_serial(value: str) -> SerialParity:
    return _SERIAL_PARITY_REVERSE[value]


def _stop_bits_from_serial(value: float) -> SerialStopBits:
    return _SERIAL_STOP_BITS_REVERSE[value]


def _classify_open_error(error: Exception) -> NormalizedBackendFailure:
    error_number = getattr(error, "errno", None)
    windows_error = getattr(error, "winerror", None)
    if error_number in _DEVICE_NOT_FOUND_ERRNOS or windows_error in {2, 3}:
        kind = BackendFailureKind.DEVICE_NOT_FOUND
    elif error_number in _PERMISSION_ERRNOS or windows_error == 5:
        kind = BackendFailureKind.PERMISSION_DENIED
    elif error_number in _DEVICE_BUSY_ERRNOS or windows_error in {32, 33}:
        kind = BackendFailureKind.DEVICE_BUSY
    else:
        kind = BackendFailureKind.IO_FAILURE
    return _open_failure(kind, error)


def _open_failure(
    kind: BackendFailureKind,
    error: Exception,
) -> NormalizedBackendFailure:
    return NormalizedBackendFailure(
        operation=BackendFailureOperation.OPEN,
        kind=kind,
        detail=str(error) or None,
    )


def _best_effort_close(serial_handle: _SerialHandle) -> None:
    try:
        serial_handle.close()
    except Exception:
        pass


_SERIAL_DATA_BITS = {
    SerialDataBits.FIVE: serial.FIVEBITS,
    SerialDataBits.SIX: serial.SIXBITS,
    SerialDataBits.SEVEN: serial.SEVENBITS,
    SerialDataBits.EIGHT: serial.EIGHTBITS,
}
_SERIAL_DATA_BITS_REVERSE = {
    value: key for key, value in _SERIAL_DATA_BITS.items()
}
_SERIAL_PARITY = {
    SerialParity.NONE: serial.PARITY_NONE,
    SerialParity.EVEN: serial.PARITY_EVEN,
    SerialParity.ODD: serial.PARITY_ODD,
}
_SERIAL_PARITY_REVERSE = {value: key for key, value in _SERIAL_PARITY.items()}
_SERIAL_STOP_BITS = {
    SerialStopBits.ONE: serial.STOPBITS_ONE,
    SerialStopBits.TWO: serial.STOPBITS_TWO,
}
_SERIAL_STOP_BITS_REVERSE: dict[float, SerialStopBits] = {
    float(value): key for key, value in _SERIAL_STOP_BITS.items()
}

_DEVICE_NOT_FOUND_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, "ENOENT", None),
        getattr(errno, "ENODEV", None),
        getattr(errno, "ENXIO", None),
    )
    if value is not None
)
_PERMISSION_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, "EACCES", None),
        getattr(errno, "EPERM", None),
    )
    if value is not None
)
_DEVICE_BUSY_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, "EBUSY", None),
        getattr(errno, "EAGAIN", None),
        getattr(errno, "EWOULDBLOCK", None),
    )
    if value is not None
)
_DEVICE_LOST_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, "ENODEV", None),
        getattr(errno, "ENXIO", None),
    )
    if value is not None
)
_WINDOWS_DEVICE_LOST_ERRORS = frozenset({1167})
