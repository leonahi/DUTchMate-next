"""Hardware-free contract tests for the Basic serial adapter."""

import ast
import asyncio
import errno
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol, cast

import pytest
import serial

from dutchmate_core.adapters import basic_serial
from dutchmate_core.adapters.basic_serial import (
    BasicSerialConnectionProvenance,
    BasicSerialOpenRequest,
    SerialConfiguration,
    SerialDataBits,
    SerialDeviceSelector,
    SerialElectricalVerification,
    SerialExclusivityMechanism,
    SerialExclusivityResult,
    SerialLineState,
    SerialOpenApplyStrategy,
    SerialOpenLineIntent,
    SerialOpenTransitionGuarantee,
    SerialParity,
    SerialStopBits,
)
from dutchmate_core.backend import (
    BackendFailureKind,
    BackendFailureOperation,
    EventStreamAlreadyConsumedError,
    NormalizedBackendFailure,
)
from dutchmate_core.model import (
    BackendCapability,
    BackendEvent,
    ConnectionDescriptor,
    Disconnected,
    RxBytesObserved,
    TimestampMeaning,
    TimestampObserver,
    TimestampUnit,
    UpstreamLossNotObservable,
)

type SerialEvent = tuple[object, ...]
type FakeReadOutcome = bytes | Exception

_PROJECT_ROOT = Path(__file__).parents[3]
_PRODUCTION_ROOT = _PROJECT_ROOT / "core" / "src"
_TEST_ROOT = _PROJECT_ROOT / "core" / "tests"
_FORBIDDEN_SERIAL_APIS = (
    "serial.serial_for_url",
    "serial.tools",
    "serial.urlhandler",
)


class FakeSerial:
    """Strict in-memory observation point for adapter-to-pySerial calls."""

    _TRACKED_SETTINGS = frozenset(
        {
            "port",
            "baudrate",
            "bytesize",
            "parity",
            "stopbits",
            "rtscts",
            "xonxoff",
            "dsrdtr",
            "exclusive",
            "dtr",
            "rts",
        }
    )

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
    is_open: bool
    events: list[SerialEvent]
    _record_assignments: bool
    _opened_device_name: str | None
    _assignment_errors: dict[str, Exception]
    _open_error: Exception | None
    _cancel_read_error: Exception | None
    _close_error: Exception | None
    _effective_settings: dict[str, object]
    _read_results: tuple[FakeReadOutcome, ...]
    _read_gates: tuple[threading.Event | None, ...]
    _read_lock: threading.Lock
    _observation_timeline: list[SerialEvent]
    read_started: tuple[threading.Event, ...]
    read_calls: int
    active_reads: int
    max_active_reads: int
    cancel_read_called: threading.Event
    cancel_read_calls: int
    close_started: threading.Event
    close_calls: int

    def __init__(
        self,
        *,
        opened_device_name: str | None = None,
        assignment_errors: dict[str, Exception] | None = None,
        open_error: Exception | None = None,
        cancel_read_error: Exception | None = None,
        close_error: Exception | None = None,
        effective_settings: dict[str, object] | None = None,
        read_results: tuple[FakeReadOutcome, ...] = (),
        read_gates: tuple[threading.Event | None, ...] | None = None,
        observation_timeline: list[SerialEvent] | None = None,
    ) -> None:
        object.__setattr__(self, "events", [])
        object.__setattr__(self, "_opened_device_name", opened_device_name)
        object.__setattr__(self, "_assignment_errors", assignment_errors or {})
        object.__setattr__(self, "_open_error", open_error)
        object.__setattr__(self, "_cancel_read_error", cancel_read_error)
        object.__setattr__(self, "_close_error", close_error)
        object.__setattr__(self, "_effective_settings", effective_settings or {})
        object.__setattr__(self, "_read_results", read_results)
        object.__setattr__(
            self,
            "_read_gates",
            read_gates or tuple(None for _ in read_results),
        )
        if len(self._read_gates) != len(read_results):
            raise ValueError("one read gate is required for each scripted result")
        object.__setattr__(self, "_read_lock", threading.Lock())
        object.__setattr__(
            self,
            "_observation_timeline",
            observation_timeline if observation_timeline is not None else [],
        )
        object.__setattr__(
            self,
            "read_started",
            tuple(threading.Event() for _ in read_results),
        )
        object.__setattr__(self, "read_calls", 0)
        object.__setattr__(self, "active_reads", 0)
        object.__setattr__(self, "max_active_reads", 0)
        object.__setattr__(self, "cancel_read_called", threading.Event())
        object.__setattr__(self, "cancel_read_calls", 0)
        object.__setattr__(self, "close_started", threading.Event())
        object.__setattr__(self, "close_calls", 0)
        object.__setattr__(self, "_record_assignments", False)
        object.__setattr__(self, "port", None)
        object.__setattr__(self, "baudrate", 9_600)
        object.__setattr__(self, "bytesize", serial.EIGHTBITS)
        object.__setattr__(self, "parity", serial.PARITY_NONE)
        object.__setattr__(self, "stopbits", serial.STOPBITS_ONE)
        object.__setattr__(self, "rtscts", False)
        object.__setattr__(self, "xonxoff", False)
        object.__setattr__(self, "dsrdtr", False)
        object.__setattr__(self, "exclusive", None)
        object.__setattr__(self, "dtr", True)
        object.__setattr__(self, "rts", True)
        object.__setattr__(self, "is_open", False)
        object.__setattr__(self, "_record_assignments", True)

    def __setattr__(self, name: str, value: object) -> None:
        if name in self._TRACKED_SETTINGS and self._record_assignments:
            self.events.append(("set", name, value))
            assignment_error = self._assignment_errors.get(name)
            if assignment_error is not None:
                raise assignment_error
        object.__setattr__(self, name, value)

    @property
    def portstr(self) -> str | None:
        return self._opened_device_name or self.port

    def open(self) -> None:
        self.events.append(("open",))
        if self._open_error is not None:
            raise self._open_error
        self.is_open = True
        for name, value in self._effective_settings.items():
            object.__setattr__(self, name, value)

    def close(self) -> None:
        self.close_calls += 1
        self.close_started.set()
        self.events.append(("close",))
        self._observation_timeline.append(
            ("serial_close", threading.get_ident())
        )
        if self._close_error is not None:
            raise self._close_error
        self.is_open = False

    def cancel_read(self) -> None:
        self.cancel_read_calls += 1
        self.events.append(("cancel_read",))
        with self._read_lock:
            active_reads = self.active_reads
        self._observation_timeline.append(
            ("cancel_read", threading.get_ident(), active_reads)
        )
        self.cancel_read_called.set()
        if self._cancel_read_error is not None:
            raise self._cancel_read_error

    def read(self, size: int = -1) -> bytes:
        del size
        with self._read_lock:
            read_index = self.read_calls
            if read_index >= len(self._read_results):
                raise AssertionError("adapter performed an unscripted serial read")
            self.read_calls += 1
            self.active_reads += 1
            self.max_active_reads = max(self.max_active_reads, self.active_reads)
            outcome = self._read_results[read_index]
            gate = self._read_gates[read_index]
            worker_thread = threading.get_ident()
            self._observation_timeline.append(
                ("read_begin", read_index, worker_thread)
            )
            self.read_started[read_index].set()
        try:
            if gate is not None and not gate.wait(timeout=2.0):
                raise AssertionError("scripted serial read was not released")
            if isinstance(outcome, Exception):
                self._observation_timeline.append(
                    ("read_raise", read_index, type(outcome), worker_thread)
                )
                raise outcome
            self._observation_timeline.append(
                ("read_return", read_index, outcome, worker_thread)
            )
            return outcome
        finally:
            with self._read_lock:
                self.active_reads -= 1


class FakeSerialFactory:
    def __init__(
        self,
        *serial_instances: FakeSerial,
        construction_error: Exception | None = None,
    ) -> None:
        self._serial_instances = list(serial_instances) or [FakeSerial()]
        self._construction_error = construction_error
        self.calls: list[dict[str, object]] = []

    def __call__(self, *, port: str | None) -> FakeSerial:
        self.calls.append({"port": port})
        if self._construction_error is not None:
            raise self._construction_error
        serial_instance = self._serial_instances.pop(0)
        serial_instance.events.append(("construct", "port", port))
        return serial_instance


class _OpenedConnection(Protocol):
    @property
    def descriptor(self) -> ConnectionDescriptor: ...

    def events(self) -> AsyncIterator[BackendEvent]: ...

    async def close(self) -> None: ...


class _BackendUnderTest(Protocol):
    async def open(self) -> _OpenedConnection: ...


class FakeMonotonicClock:
    def __init__(
        self,
        values: tuple[int, ...],
        timeline: list[SerialEvent] | None = None,
    ) -> None:
        self._values = values
        self._timeline = timeline
        self.calls = 0

    def __call__(self) -> int:
        if self.calls >= len(self._values):
            raise AssertionError("adapter requested an unscripted timestamp")
        value = self._values[self.calls]
        self.calls += 1
        if self._timeline is not None:
            self._timeline.append(("timestamp", value, threading.get_ident()))
        return value


def _configuration(
    *,
    baud_rate: int = 115_200,
    data_bits: SerialDataBits = SerialDataBits.EIGHT,
    parity: SerialParity = SerialParity.NONE,
    stop_bits: SerialStopBits = SerialStopBits.ONE,
    hardware_flow_control: bool = False,
    software_flow_control: bool = False,
) -> SerialConfiguration:
    return SerialConfiguration(
        baud_rate=baud_rate,
        data_bits=data_bits,
        parity=parity,
        stop_bits=stop_bits,
        hardware_flow_control=hardware_flow_control,
        software_flow_control=software_flow_control,
    )


def _open_request(
    *,
    device_name: str = "/dev/ttyUSB-selected",
    configuration: SerialConfiguration | None = None,
    dtr: SerialLineState = SerialLineState.DEASSERTED,
    rts: SerialLineState = SerialLineState.ASSERTED,
) -> BasicSerialOpenRequest:
    return BasicSerialOpenRequest(
        selector=SerialDeviceSelector(device_name),
        configuration=configuration or _configuration(),
        line_intent=SerialOpenLineIntent(dtr=dtr, rts=rts),
    )


def _backend(
    request: BasicSerialOpenRequest,
    factory: FakeSerialFactory,
) -> _BackendUnderTest:
    return _backend_from_values(
        selector=request.selector,
        configuration=request.configuration,
        line_intent=request.line_intent,
        factory=factory,
    )


def _backend_from_values(
    *,
    selector: SerialDeviceSelector,
    configuration: SerialConfiguration,
    line_intent: SerialOpenLineIntent,
    factory: FakeSerialFactory,
) -> _BackendUnderTest:
    backend_type = getattr(basic_serial, "BasicSerialBackend", None)
    assert backend_type is not None, "BasicSerialBackend is not implemented"
    return cast(
        "_BackendUnderTest",
        backend_type(
            selector=selector,
            configuration=configuration,
            line_intent=line_intent,
            _serial_factory=factory,
        ),
    )


async def _open_backend(backend: _BackendUnderTest) -> _OpenedConnection:
    return await backend.open()


async def _open_descriptor(
    request: BasicSerialOpenRequest,
    factory: FakeSerialFactory,
) -> ConnectionDescriptor:
    connection = await _open_backend(_backend(request, factory))
    return connection.descriptor


async def _open_failure(backend: _BackendUnderTest) -> NormalizedBackendFailure:
    with pytest.raises(NormalizedBackendFailure) as raised:
        await _open_backend(backend)
    failure = raised.value
    assert failure.__cause__ is None
    assert failure.__context__ is None
    assert not hasattr(failure, "serial_exception")
    assert not hasattr(failure, "serial_handle")
    return failure


async def _wait_for_thread_event(event: threading.Event) -> None:
    observed = await asyncio.wait_for(
        asyncio.to_thread(event.wait, 1.0),
        timeout=2.0,
    )
    assert observed


def _qualified_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _qualified_name(node.value)
        if owner is not None:
            return f"{owner}.{node.attr}"
    return None


def _forbidden_serial_references(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases: dict[str, str] = {}
    references: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".", maxsplit=1)[0]] = (
                    alias.name
                )
                references.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                qualified = f"{node.module}.{alias.name}"
                aliases[alias.asname or alias.name] = qualified
                references.append((node.lineno, qualified))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        attribute_name = _qualified_name(node)
        if attribute_name is None:
            continue
        root, separator, remainder = attribute_name.partition(".")
        resolved_root = aliases.get(root, root)
        resolved = (
            f"{resolved_root}.{remainder}" if separator else resolved_root
        )
        references.append((node.lineno, resolved))

    return [
        f"{path.relative_to(_PROJECT_ROOT)}:{line}:{reference}"
        for line, reference in references
        if any(
            reference == forbidden or reference.startswith(f"{forbidden}.")
            for forbidden in _FORBIDDEN_SERIAL_APIS
        )
    ]


async def _next_event(stream: AsyncIterator[BackendEvent]) -> BackendEvent:
    return await anext(stream)


@pytest.mark.asyncio
async def test_default_test_path_cannot_reach_physical_serial_factory() -> None:
    backend = basic_serial.BasicSerialBackend(
        selector=SerialDeviceSelector("/dev/explicit-test-target"),
        configuration=_configuration(),
        line_intent=SerialOpenLineIntent(
            dtr=SerialLineState.DEASSERTED,
            rts=SerialLineState.ASSERTED,
        ),
    )

    with pytest.raises(
        pytest.fail.Exception,
        match="physical serial access is forbidden",
    ):
        await backend.open()


def test_repository_serial_surfaces_exclude_discovery_and_url_handlers() -> None:
    source_paths = sorted(_PRODUCTION_ROOT.rglob("*.py"))
    test_paths = sorted(_TEST_ROOT.rglob("*.py"))

    violations = [
        violation
        for path in (*source_paths, *test_paths)
        for violation in _forbidden_serial_references(path)
    ]

    assert violations == []


@pytest.mark.parametrize(
    "device_name",
    [
        "loop://",
        "socket://host:23",
        "rfc2217://host:2217",
        "spy:///dev/ttyUSB0",
        "hwgrep://USB",
        "alt:///dev/ttyUSB0",
    ],
)
def test_basic_adapter_rejects_pyserial_url_handler_targets(
    device_name: str,
) -> None:
    with pytest.raises(ValueError, match="local device"):
        SerialDeviceSelector(device_name)


@pytest.mark.asyncio
async def test_configure_before_open_uses_exact_device_and_complete_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial()
    factory = FakeSerialFactory(fake_serial)
    request = _open_request(
        device_name=" tty device ",
        configuration=_configuration(
            baud_rate=230_400,
            data_bits=SerialDataBits.SEVEN,
            parity=SerialParity.EVEN,
            stop_bits=SerialStopBits.TWO,
        ),
        dtr=SerialLineState.DEASSERTED,
        rts=SerialLineState.ASSERTED,
    )

    await _open_backend(_backend(request, factory))

    assert factory.calls == [{"port": None}]
    assert fake_serial.events == [
        ("construct", "port", None),
        ("set", "port", " tty device "),
        ("set", "baudrate", 230_400),
        ("set", "bytesize", serial.SEVENBITS),
        ("set", "parity", serial.PARITY_EVEN),
        ("set", "stopbits", serial.STOPBITS_TWO),
        ("set", "rtscts", False),
        ("set", "xonxoff", False),
        ("set", "dsrdtr", False),
        ("set", "exclusive", True),
        ("set", "dtr", False),
        ("set", "rts", True),
        ("open",),
    ]


@pytest.mark.parametrize(
    ("data_bits", "expected"),
    [
        (SerialDataBits.FIVE, serial.FIVEBITS),
        (SerialDataBits.SIX, serial.SIXBITS),
        (SerialDataBits.SEVEN, serial.SEVENBITS),
        (SerialDataBits.EIGHT, serial.EIGHTBITS),
    ],
)
@pytest.mark.asyncio
async def test_configure_before_open_maps_every_supported_data_bits_value(
    monkeypatch: pytest.MonkeyPatch,
    data_bits: SerialDataBits,
    expected: int,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial()
    request = _open_request(configuration=_configuration(data_bits=data_bits))

    await _open_backend(_backend(request, FakeSerialFactory(fake_serial)))

    assert ("set", "bytesize", expected) in fake_serial.events


@pytest.mark.parametrize(
    ("parity", "expected"),
    [
        (SerialParity.NONE, serial.PARITY_NONE),
        (SerialParity.EVEN, serial.PARITY_EVEN),
        (SerialParity.ODD, serial.PARITY_ODD),
    ],
)
@pytest.mark.asyncio
async def test_configure_before_open_maps_every_supported_parity(
    monkeypatch: pytest.MonkeyPatch,
    parity: SerialParity,
    expected: str,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial()
    request = _open_request(configuration=_configuration(parity=parity))

    await _open_backend(_backend(request, FakeSerialFactory(fake_serial)))

    assert ("set", "parity", expected) in fake_serial.events


@pytest.mark.parametrize(
    ("stop_bits", "expected"),
    [
        (SerialStopBits.ONE, serial.STOPBITS_ONE),
        (SerialStopBits.TWO, serial.STOPBITS_TWO),
    ],
)
@pytest.mark.asyncio
async def test_configure_before_open_maps_every_supported_stop_bits_value(
    monkeypatch: pytest.MonkeyPatch,
    stop_bits: SerialStopBits,
    expected: float,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial()
    request = _open_request(configuration=_configuration(stop_bits=stop_bits))

    await _open_backend(_backend(request, FakeSerialFactory(fake_serial)))

    assert ("set", "stopbits", expected) in fake_serial.events


@pytest.mark.asyncio
async def test_rts_is_driver_managed_when_hardware_flow_control_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial()
    request = _open_request(
        configuration=_configuration(hardware_flow_control=True),
        rts=SerialLineState.DRIVER_MANAGED,
    )

    await _open_backend(_backend(request, FakeSerialFactory(fake_serial)))

    assert ("set", "rtscts", True) in fake_serial.events
    assert not any(
        event[:2] == ("set", "rts") for event in fake_serial.events
    )
    assert fake_serial.events[-1] == ("open",)


@pytest.mark.asyncio
async def test_software_flow_control_keeps_static_rts_and_disables_dsrdtr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial()
    request = _open_request(
        configuration=_configuration(software_flow_control=True),
        dtr=SerialLineState.ASSERTED,
        rts=SerialLineState.DEASSERTED,
    )

    await _open_backend(_backend(request, FakeSerialFactory(fake_serial)))

    assert ("set", "rtscts", False) in fake_serial.events
    assert ("set", "xonxoff", True) in fake_serial.events
    assert ("set", "dsrdtr", False) in fake_serial.events
    assert ("set", "dtr", True) in fake_serial.events
    assert ("set", "rts", False) in fake_serial.events


@pytest.mark.asyncio
async def test_windows_relies_on_the_exclusive_handle_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: True)
    fake_serial = FakeSerial()
    request = _open_request()

    await _open_backend(_backend(request, FakeSerialFactory(fake_serial)))

    assert not any(
        event[:2] == ("set", "exclusive") for event in fake_serial.events
    )
    assert fake_serial.events[-1] == ("open",)


@pytest.mark.asyncio
async def test_successful_open_reports_receive_only_host_observation_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    descriptor = await _open_descriptor(
        _open_request(),
        FakeSerialFactory(FakeSerial()),
    )

    assert descriptor.capabilities.values == frozenset(
        {BackendCapability.UART_RECEIVE}
    )
    assert (
        descriptor.backend_observation_timestamp_domain.observer
        is TimestampObserver.HOST
    )
    assert (
        descriptor.backend_observation_timestamp_domain.meaning
        is TimestampMeaning.OBSERVATION
    )
    assert (
        descriptor.backend_observation_timestamp_domain.unit
        is TimestampUnit.NANOSECOND
    )
    assert descriptor.backend_observation_timestamp_domain.domain_id
    assert descriptor.backend_observation_timestamp_domain.origin_id
    assert isinstance(descriptor.loss_observability, UpstreamLossNotObservable)


@pytest.mark.asyncio
async def test_each_successful_open_has_a_fresh_timestamp_domain_and_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    factory = FakeSerialFactory(FakeSerial(), FakeSerial())
    backend = _backend(_open_request(), factory)

    first = (await _open_backend(backend)).descriptor
    second = (await _open_backend(backend)).descriptor

    first_domain = first.backend_observation_timestamp_domain
    second_domain = second.backend_observation_timestamp_domain
    assert first_domain.domain_id != second_domain.domain_id
    assert first_domain.origin_id != second_domain.origin_id


@pytest.mark.asyncio
async def test_successful_open_reports_exact_configuration_and_line_limitations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    configuration = _configuration(
        baud_rate=230_400,
        data_bits=SerialDataBits.SEVEN,
        parity=SerialParity.ODD,
        stop_bits=SerialStopBits.TWO,
        software_flow_control=True,
    )
    request = _open_request(
        device_name="/dev/selected-device",
        configuration=configuration,
        dtr=SerialLineState.ASSERTED,
        rts=SerialLineState.DEASSERTED,
    )
    descriptor = await _open_descriptor(
        request,
        FakeSerialFactory(FakeSerial(opened_device_name="/dev/opened-device")),
    )

    provenance = descriptor.connection_provenance
    assert isinstance(provenance, BasicSerialConnectionProvenance)
    assert provenance.selected_device_name == "/dev/selected-device"
    assert provenance.opened_device_name == "/dev/opened-device"
    assert provenance.requested_configuration is configuration
    assert provenance.effective_configuration == configuration
    assert provenance.open_line_provenance.requested is request.line_intent
    assert (
        provenance.open_line_provenance.apply_strategy
        is SerialOpenApplyStrategy.PRECONFIGURED_WHILE_CLOSED
    )
    assert (
        provenance.open_line_provenance.library_reported_dtr
        is SerialLineState.ASSERTED
    )
    assert (
        provenance.open_line_provenance.library_reported_rts
        is SerialLineState.DEASSERTED
    )
    assert (
        provenance.open_line_provenance.transition_guarantee
        is SerialOpenTransitionGuarantee.NOT_GUARANTEED
    )
    assert (
        provenance.open_line_provenance.electrical_verification
        is SerialElectricalVerification.NOT_VERIFIED
    )
    assert provenance.exclusivity.requested is True
    assert (
        provenance.exclusivity.mechanism
        is SerialExclusivityMechanism.POSIX_PYSERIAL_EXCLUSIVE
    )
    assert (
        provenance.exclusivity.result
        is SerialExclusivityResult.OPEN_SUCCEEDED_WITH_REQUESTED_MECHANISM
    )


@pytest.mark.asyncio
async def test_hardware_flow_reports_driver_managed_rts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    request = _open_request(
        configuration=_configuration(hardware_flow_control=True),
        dtr=SerialLineState.DEASSERTED,
        rts=SerialLineState.DRIVER_MANAGED,
    )
    descriptor = await _open_descriptor(
        request,
        FakeSerialFactory(FakeSerial()),
    )

    provenance = cast(
        "BasicSerialConnectionProvenance",
        descriptor.connection_provenance,
    )
    assert (
        provenance.open_line_provenance.library_reported_rts
        is SerialLineState.DRIVER_MANAGED
    )


@pytest.mark.asyncio
async def test_windows_open_reports_exclusive_handle_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: True)
    descriptor = await _open_descriptor(
        _open_request(),
        FakeSerialFactory(FakeSerial()),
    )

    provenance = cast(
        "BasicSerialConnectionProvenance",
        descriptor.connection_provenance,
    )
    assert (
        provenance.exclusivity.mechanism
        is SerialExclusivityMechanism.WINDOWS_EXCLUSIVE_HANDLE
    )


@pytest.mark.asyncio
async def test_invalid_cross_field_request_fails_before_serial_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    factory = FakeSerialFactory()
    backend = _backend_from_values(
        selector=SerialDeviceSelector("/dev/ttyUSB-selected"),
        configuration=_configuration(hardware_flow_control=True),
        line_intent=SerialOpenLineIntent(
            dtr=SerialLineState.DEASSERTED,
            rts=SerialLineState.ASSERTED,
        ),
        factory=factory,
    )

    failure = await _open_failure(backend)

    assert failure.operation is BackendFailureOperation.OPEN
    assert failure.kind is BackendFailureKind.INVALID_REQUEST
    assert factory.calls == []


@pytest.mark.parametrize(
    ("stable_error", "expected_kind"),
    [
        (
            serial.SerialException(errno.ENOENT, "missing diagnostic"),
            BackendFailureKind.DEVICE_NOT_FOUND,
        ),
        (
            serial.SerialException(errno.EACCES, "permission diagnostic"),
            BackendFailureKind.PERMISSION_DENIED,
        ),
        (
            serial.SerialException(errno.EBUSY, "busy diagnostic"),
            BackendFailureKind.DEVICE_BUSY,
        ),
        (
            serial.SerialException("generic diagnostic"),
            BackendFailureKind.IO_FAILURE,
        ),
    ],
)
@pytest.mark.asyncio
async def test_open_failure_uses_stable_error_attributes_only(
    monkeypatch: pytest.MonkeyPatch,
    stable_error: Exception,
    expected_kind: BackendFailureKind,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial(open_error=stable_error)

    failure = await _open_failure(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )

    assert failure.operation is BackendFailureOperation.OPEN
    assert failure.kind is expected_kind
    assert fake_serial.events[-1] == ("close",)


class _StableWindowsOpenError(Exception):
    def __init__(self, winerror: int) -> None:
        super().__init__("diagnostic text must not classify this error")
        self.winerror = winerror


class _StableWindowsReadError(Exception):
    def __init__(self, winerror: int) -> None:
        super().__init__("diagnostic text must not classify this error")
        self.winerror = winerror


@pytest.mark.parametrize(
    ("winerror", "expected_kind"),
    [
        (2, BackendFailureKind.DEVICE_NOT_FOUND),
        (5, BackendFailureKind.PERMISSION_DENIED),
        (32, BackendFailureKind.DEVICE_BUSY),
    ],
)
@pytest.mark.asyncio
async def test_windows_open_failure_uses_stable_winerror(
    monkeypatch: pytest.MonkeyPatch,
    winerror: int,
    expected_kind: BackendFailureKind,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: True)
    fake_serial = FakeSerial(open_error=_StableWindowsOpenError(winerror))

    failure = await _open_failure(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )

    assert failure.kind is expected_kind


@pytest.mark.asyncio
async def test_serial_configuration_assignment_failure_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial(
        assignment_errors={"baudrate": ValueError("unsupported diagnostic")}
    )

    failure = await _open_failure(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )

    assert failure.kind is BackendFailureKind.CONFIGURATION_REJECTED
    assert fake_serial.events[-1] == ("close",)


@pytest.mark.asyncio
async def test_serial_line_assignment_failure_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial(
        assignment_errors={"dtr": serial.SerialException("line diagnostic")}
    )

    failure = await _open_failure(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )

    assert failure.kind is BackendFailureKind.LINE_STATE_SETUP_FAILED
    assert fake_serial.events[-1] == ("close",)


@pytest.mark.asyncio
async def test_open_rejection_of_configuration_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial(open_error=ValueError("unsupported diagnostic"))

    failure = await _open_failure(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )

    assert failure.kind is BackendFailureKind.CONFIGURATION_REJECTED
    assert fake_serial.events[-1] == ("close",)


@pytest.mark.asyncio
async def test_effective_configuration_mismatch_closes_and_fails_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial(effective_settings={"baudrate": 9_600})

    failure = await _open_failure(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )

    assert failure.kind is BackendFailureKind.CONFIGURATION_REJECTED
    assert fake_serial.events[-1] == ("close",)


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_replace_primary_open_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    primary_error = serial.SerialException(errno.ENOENT, "primary diagnostic")
    fake_serial = FakeSerial(
        open_error=primary_error,
        close_error=serial.SerialException("cleanup diagnostic"),
    )

    failure = await _open_failure(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )

    assert failure.kind is BackendFailureKind.DEVICE_NOT_FOUND
    assert fake_serial.events[-1] == ("close",)


@pytest.mark.asyncio
async def test_serial_construction_failure_is_normalized_without_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    factory = FakeSerialFactory(
        construction_error=serial.SerialException("construction diagnostic")
    )

    failure = await _open_failure(_backend(_open_request(), factory))

    assert failure.kind is BackendFailureKind.IO_FAILURE
    assert factory.calls == [{"port": None}]


@pytest.mark.asyncio
async def test_rx_event_preserves_exact_binary_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock((101,)))
    payload = bytes(range(256)) + b"\x00\x80\xfe\xffinvalid-utf8:\xf5"
    connection = await _open_backend(
        _backend(
            _open_request(),
            FakeSerialFactory(FakeSerial(read_results=(payload,))),
        )
    )

    event = await anext(connection.events())

    assert isinstance(event, RxBytesObserved)
    assert event.payload == payload


@pytest.mark.asyncio
async def test_host_timestamp_is_captured_after_read_in_blocking_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    timeline: list[SerialEvent] = []
    clock = FakeMonotonicClock((7_000_000_123,), timeline)
    monkeypatch.setattr("time.monotonic_ns", clock)
    fake_serial = FakeSerial(
        read_results=(b"timestamped",),
        observation_timeline=timeline,
    )
    connection = await _open_backend(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )
    event_loop_thread = threading.get_ident()

    event = await anext(connection.events())

    assert isinstance(event, RxBytesObserved)
    worker_thread = timeline[0][2]
    assert timeline == [
        ("read_begin", 0, worker_thread),
        ("read_return", 0, b"timestamped", worker_thread),
        ("timestamp", 7_000_000_123, worker_thread),
    ]
    assert worker_thread != event_loop_thread
    assert clock.calls == 1
    assert event.observed_at.value == 7_000_000_123
    assert (
        event.observed_at.domain_id
        == connection.descriptor.backend_observation_timestamp_domain.domain_id
    )


@pytest.mark.asyncio
async def test_empty_reads_emit_no_event_and_discard_their_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    timeline: list[SerialEvent] = []
    clock = FakeMonotonicClock((10, 11, 12), timeline)
    monkeypatch.setattr("time.monotonic_ns", clock)
    fake_serial = FakeSerial(
        read_results=(b"", b"", b"observed"),
        observation_timeline=timeline,
    )
    connection = await _open_backend(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )

    event = await anext(connection.events())

    assert isinstance(event, RxBytesObserved)
    assert event.payload == b"observed"
    assert event.observed_at.value == 12
    assert fake_serial.read_calls == 3
    assert clock.calls == 3


@pytest.mark.asyncio
async def test_rx_events_preserve_serial_read_return_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock((20, 21, 22)))
    fake_serial = FakeSerial(read_results=(b"first", b"second", b"third"))
    connection = await _open_backend(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )
    stream = connection.events()

    events = [await anext(stream) for _ in range(3)]

    assert all(isinstance(event, RxBytesObserved) for event in events)
    rx_events = cast("list[RxBytesObserved]", events)
    assert [event.payload for event in rx_events] == [
        b"first",
        b"second",
        b"third",
    ]


@pytest.mark.asyncio
async def test_reads_follow_event_consumption_without_prefetch_or_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock((30, 31)))
    first_gate = threading.Event()
    second_gate = threading.Event()
    fake_serial = FakeSerial(
        read_results=(b"first", b"second"),
        read_gates=(first_gate, second_gate),
    )
    connection = await _open_backend(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )
    stream = connection.events()
    first_event_task = asyncio.create_task(_next_event(stream))
    second_event_task: asyncio.Task[BackendEvent] | None = None

    try:
        await _wait_for_thread_event(fake_serial.read_started[0])
        await asyncio.sleep(0)
        assert fake_serial.read_calls == 1
        assert fake_serial.active_reads == 1
        assert not fake_serial.read_started[1].is_set()

        first_gate.set()
        first_event = await asyncio.wait_for(first_event_task, timeout=2.0)
        assert isinstance(first_event, RxBytesObserved)
        await asyncio.sleep(0)
        assert fake_serial.read_calls == 1

        second_event_task = asyncio.create_task(_next_event(stream))
        await _wait_for_thread_event(fake_serial.read_started[1])
        assert fake_serial.read_calls == 2
        assert fake_serial.active_reads == 1
        second_gate.set()
        second_event = await asyncio.wait_for(second_event_task, timeout=2.0)
        assert isinstance(second_event, RxBytesObserved)
        assert [first_event.payload, second_event.payload] == [b"first", b"second"]
        assert fake_serial.max_active_reads == 1
    finally:
        first_gate.set()
        second_gate.set()
        if not first_event_task.done():
            first_event_task.cancel()
        if second_event_task is not None and not second_event_task.done():
            second_event_task.cancel()


@pytest.mark.asyncio
async def test_connection_event_stream_rejects_a_second_consumer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    connection = await _open_backend(
        _backend(
            _open_request(),
            FakeSerialFactory(FakeSerial(read_results=(b"unused",))),
        )
    )
    first_stream = connection.events()

    with pytest.raises(EventStreamAlreadyConsumedError):
        connection.events()

    assert first_stream is not None


@pytest.mark.parametrize(
    ("read_error", "windows"),
    [
        (
            serial.SerialException(errno.ENODEV, "unrelated diagnostic"),
            False,
        ),
        (_StableWindowsReadError(1167), True),
    ],
    ids=["posix-enodev", "windows-device-not-connected"],
)
@pytest.mark.asyncio
async def test_stable_device_loss_read_error_emits_normalized_disconnect(
    monkeypatch: pytest.MonkeyPatch,
    read_error: Exception,
    windows: bool,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: windows)
    clock = FakeMonotonicClock(())
    monkeypatch.setattr("time.monotonic_ns", clock)
    fake_serial = FakeSerial(read_results=(read_error,))
    connection = await _open_backend(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )
    stream = connection.events()

    event = await anext(stream)

    assert event == Disconnected(reason="device_lost")
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert clock.calls == 0


@pytest.mark.parametrize(
    "read_error",
    [
        serial.SerialException(errno.EIO, "ambiguous diagnostic"),
        OSError(errno.EBADF, "ambiguous diagnostic"),
    ],
    ids=["serial-eio", "os-ebadf"],
)
@pytest.mark.asyncio
async def test_ambiguous_read_failure_is_normalized_instead_of_ending_stream(
    monkeypatch: pytest.MonkeyPatch,
    read_error: Exception,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    clock = FakeMonotonicClock(())
    monkeypatch.setattr("time.monotonic_ns", clock)
    connection = await _open_backend(
        _backend(
            _open_request(),
            FakeSerialFactory(FakeSerial(read_results=(read_error,))),
        )
    )

    with pytest.raises(NormalizedBackendFailure) as raised:
        await anext(connection.events())

    failure = raised.value
    assert failure.operation is BackendFailureOperation.READ
    assert failure.kind is BackendFailureKind.IO_FAILURE
    assert failure.__cause__ is None
    assert failure.__context__ is None
    assert not hasattr(failure, "serial_exception")
    assert not hasattr(failure, "os_error")
    assert clock.calls == 0


@pytest.mark.parametrize(
    "read_error",
    [
        serial.SerialException(
            "device disconnected: no such device; ENODEV; winerror 1167"
        ),
        serial.SerialException(
            errno.EACCES,
            "device disconnected: no such device; ENODEV; winerror 1167",
        ),
    ],
    ids=["message-only", "stable-non-loss-attribute"],
)
@pytest.mark.asyncio
async def test_read_error_message_never_classifies_device_loss(
    monkeypatch: pytest.MonkeyPatch,
    read_error: Exception,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock(()))
    connection = await _open_backend(
        _backend(
            _open_request(),
            FakeSerialFactory(FakeSerial(read_results=(read_error,))),
        )
    )

    with pytest.raises(NormalizedBackendFailure) as raised:
        await anext(connection.events())

    assert raised.value.operation is BackendFailureOperation.READ
    assert raised.value.kind is BackendFailureKind.IO_FAILURE


@pytest.mark.asyncio
async def test_close_cancels_outstanding_read_from_caller_thread_and_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock((101,)))
    read_gate = threading.Event()
    timeline: list[SerialEvent] = []
    fake_serial = FakeSerial(
        read_results=(b"",),
        read_gates=(read_gate,),
        observation_timeline=timeline,
    )
    connection = await _open_backend(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )
    stream = connection.events()
    read_task = asyncio.create_task(_next_event(stream))
    close_task: asyncio.Task[None] | None = None
    caller_thread = threading.get_ident()

    try:
        await _wait_for_thread_event(fake_serial.read_started[0])
        close_task = asyncio.create_task(connection.close())
        await _wait_for_thread_event(fake_serial.cancel_read_called)

        assert fake_serial.cancel_read_calls == 1
        cancel_event = next(
            event for event in timeline if event[0] == "cancel_read"
        )
        read_event = next(event for event in timeline if event[0] == "read_begin")
        assert cancel_event[1:] == (caller_thread, 1)
        assert read_event[2] != caller_thread
        assert not close_task.done()
        assert fake_serial.close_calls == 0

        read_gate.set()
        await asyncio.wait_for(close_task, timeout=2.0)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(read_task, timeout=2.0)

        assert fake_serial.close_calls == 1
        timeline_kinds = [event[0] for event in timeline]
        assert timeline_kinds.index("cancel_read") < timeline_kinds.index(
            "read_return"
        )
        assert timeline_kinds.index("read_return") < timeline_kinds.index(
            "serial_close"
        )
    finally:
        read_gate.set()
        if close_task is not None and not close_task.done():
            close_task.cancel()
        if not read_task.done():
            read_task.cancel()


@pytest.mark.asyncio
async def test_cancel_failure_still_waits_for_read_before_physical_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    monkeypatch.setattr("time.monotonic_ns", FakeMonotonicClock((102,)))
    read_gate = threading.Event()
    timeline: list[SerialEvent] = []
    fake_serial = FakeSerial(
        read_results=(b"",),
        read_gates=(read_gate,),
        cancel_read_error=serial.SerialException(
            errno.EIO,
            "cancel diagnostic",
        ),
        observation_timeline=timeline,
    )
    connection = await _open_backend(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )
    read_task = asyncio.create_task(_next_event(connection.events()))
    close_task: asyncio.Task[None] | None = None

    try:
        await _wait_for_thread_event(fake_serial.read_started[0])
        close_task = asyncio.create_task(connection.close())
        await _wait_for_thread_event(fake_serial.cancel_read_called)
        await asyncio.sleep(0)

        assert fake_serial.active_reads == 1
        assert fake_serial.close_calls == 0
        assert not close_task.done()

        read_gate.set()
        with pytest.raises(NormalizedBackendFailure) as raised:
            await asyncio.wait_for(close_task, timeout=2.0)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(read_task, timeout=2.0)

        failure = raised.value
        assert failure.operation is BackendFailureOperation.CLOSE
        assert failure.kind is BackendFailureKind.IO_FAILURE
        assert fake_serial.close_calls == 1
        timeline_kinds = [event[0] for event in timeline]
        assert timeline_kinds.index("cancel_read") < timeline_kinds.index(
            "read_return"
        )
        assert timeline_kinds.index("read_return") < timeline_kinds.index(
            "serial_close"
        )
    finally:
        read_gate.set()
        if close_task is not None and not close_task.done():
            close_task.cancel()
        if not read_task.done():
            read_task.cancel()


@pytest.mark.asyncio
async def test_repeated_and_concurrent_close_perform_one_physical_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial()
    connection = await _open_backend(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )

    await asyncio.gather(connection.close(), connection.close())
    await connection.close()

    assert fake_serial.close_calls == 1
    assert [event for event in fake_serial.events if event == ("close",)] == [
        ("close",)
    ]


@pytest.mark.asyncio
async def test_physical_close_failure_is_normalized_without_raw_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)
    fake_serial = FakeSerial(
        close_error=serial.SerialException(errno.EIO, "close diagnostic")
    )
    connection = await _open_backend(
        _backend(_open_request(), FakeSerialFactory(fake_serial))
    )

    with pytest.raises(NormalizedBackendFailure) as raised:
        await connection.close()

    failure = raised.value
    assert failure.operation is BackendFailureOperation.CLOSE
    assert failure.kind is BackendFailureKind.IO_FAILURE
    assert failure.__cause__ is None
    assert failure.__context__ is None
    assert not hasattr(failure, "serial_exception")
    assert not hasattr(failure, "serial_handle")
    assert fake_serial.close_calls == 1
