"""012 T010 RED: optional Basic writer, with serial-library fakes only.

The adapter construction seam is keyword-only write_enabled=False. It selects
physical capability, never human policy. Profile-v2 composition is T015; these
tests preserve the old three-argument constructor/translation path. Outcomes and
expected provenance are literal contract oracles, not implementation helpers.
"""

import asyncio
import errno
import inspect
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any, NoReturn, cast

import pytest
import serial

from dutchmate_core.adapters import basic_serial
from dutchmate_core.backend import (
    Backend,
    BackendConnection,
    BackendFailureKind,
    BackendFailureOperation,
    BackendWriteResult,
    BackendWriteStatus,
    EventStreamAlreadyConsumedError,
    NormalizedBackendFailure,
    UartWriteConnection,
)
from dutchmate_core.model import BackendCapability, BackendEvent, RxBytesObserved
from tests.contract.test_basic_serial_adapter import (
    FakeSerial,
    FakeSerialFactory,
    _open_request,
)

_DEFAULT_COUNT = object()


class WriteSerial(FakeSerial):
    """Only the external serial-library boundary is replaced.

    Gates bound the test harness, not the adapter's OS/join guarantee. Forbidden
    calls are retained for teardown assertions even if production catches them.
    """

    _TRACKED_SETTINGS = FakeSerial._TRACKED_SETTINGS | {"write_timeout", "timeout"}

    def __init__(
        self,
        *,
        write_result: object = _DEFAULT_COUNT,
        write_error: Exception | None = None,
        write_gate: threading.Event | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "write_timeout", None)
        self.write_result = write_result
        self.write_error = write_error
        self.write_gate = write_gate
        self.write_started = threading.Event()
        self.write_finished = threading.Event()
        self.writes: list[bytes] = []
        self.write_threads: list[int] = []
        self.write_timeline: list[str] = []
        self.forbidden_calls: list[str] = []
        self.post_open_settings: list[str] = []
        self.active_writes = 0
        self.max_active_writes = 0
        self.possibly_accepted_prefix = b""

    def __setattr__(self, name: str, value: object) -> None:
        if name in self._TRACKED_SETTINGS and getattr(self, "is_open", False):
            self.post_open_settings.append(name)
            raise AssertionError("adapter mutated an open serial handle")
        super().__setattr__(name, value)

    def write(self, payload: bytes) -> object:
        assert self.is_open
        assert type(payload) is bytes
        self.writes.append(payload)
        self.write_threads.append(threading.get_ident())
        self.active_writes += 1
        self.max_active_writes = max(self.max_active_writes, self.active_writes)
        self.write_timeline.append("write_begin")
        self.write_started.set()
        try:
            if self.write_gate is not None:
                assert self.write_gate.wait(5), "test did not release its fake write"
            if self.write_error is not None:
                # The fake knows progress occurred; the exception reports none.
                self.possibly_accepted_prefix = payload[:3]
                raise self.write_error
            return (
                len(payload)
                if self.write_result is _DEFAULT_COUNT
                else self.write_result
            )
        finally:
            self.active_writes -= 1
            self.write_timeline.append("write_end")
            self.write_finished.set()

    def close(self) -> None:
        self.write_timeline.append("close")
        super().close()

    def _forbidden(self, method: str) -> NoReturn:
        self.forbidden_calls.append(method)
        raise AssertionError(f"adapter must not call serial {method}")

    def flush(self) -> NoReturn:
        self._forbidden("flush")

    def reset_input_buffer(self) -> NoReturn:
        self._forbidden("reset_input_buffer")

    def reset_output_buffer(self) -> NoReturn:
        self._forbidden("reset_output_buffer")

    def cancel_write(self) -> NoReturn:
        self._forbidden("cancel_write")


@pytest.fixture(autouse=True)
def block_unowned_serial_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        pytest.fail("T010 must use only its explicitly injected serial-library fake")

    monkeypatch.setattr(serial, "serial_for_url", forbidden)
    # String targets preserve002's ban on importing serial discovery namespaces.
    monkeypatch.setattr("serial.tools.list_ports.comports", forbidden)
    monkeypatch.setattr("serial.tools.list_ports.grep", forbidden)
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: False)


type HandleFactory = Callable[..., WriteSerial]


@pytest.fixture
def handles() -> Iterator[HandleFactory]:
    created: list[WriteSerial] = []

    def make(**kwargs: Any) -> WriteSerial:
        handle = WriteSerial(**kwargs)
        created.append(handle)
        return handle

    yield make
    for handle in created:
        assert handle.forbidden_calls == []
        assert handle.post_open_settings == []
        assert handle.active_writes == 0
        assert handle.active_reads == 0
        assert handle.events.count(("open",)) <= 1


def backend(
    handle: WriteSerial, *, enabled: bool | None = True
) -> tuple[Backend, FakeSerialFactory]:
    request = _open_request()
    factory = FakeSerialFactory(handle)
    kwargs: dict[str, object] = {
        "selector": request.selector,
        "configuration": request.configuration,
        "line_intent": request.line_intent,
        "_serial_factory": factory,
    }
    if enabled is not None:
        assert (
            "write_enabled"
            in inspect.signature(basic_serial.BasicSerialBackend).parameters
        ), "T010: BasicSerialBackend has no explicit write opt-in"
        kwargs["write_enabled"] = enabled
    return cast(
        "Backend", cast("Any", basic_serial.BasicSerialBackend)(**kwargs)
    ), factory


async def open_writer(handle: WriteSerial) -> UartWriteConnection:
    adapter, _ = backend(handle)
    connection = await adapter.open()
    assert callable(getattr(connection, "write", None)), (
        "T010: opted-in Basic connection lacks normalized write"
    )
    return cast("UartWriteConnection", connection)


async def signalled(event: threading.Event) -> None:
    async def poll() -> None:
        while not event.is_set():
            await asyncio.sleep(0.001)

    await asyncio.wait_for(poll(), 2)


async def next_event(stream: AsyncIterator[BackendEvent]) -> BackendEvent:
    return await anext(stream)


async def settled_task[T](task: asyncio.Task[T]) -> T:
    # Shield keeps a harness timeout from being mistaken for adapter cancellation.
    return await asyncio.wait_for(asyncio.shield(task), 2)


@pytest.mark.parametrize(
    "enabled", [None, False], ids=["legacy-default", "explicit-off"]
)
@pytest.mark.asyncio
async def test_t010_without_opt_in_preserves_rx_only_and_provenance_v1(
    handles: HandleFactory,
    enabled: bool | None,
) -> None:
    handle = handles()
    adapter, factory = backend(handle, enabled=enabled)
    connection: BackendConnection = await adapter.open()
    try:
        assert connection.descriptor.capabilities.values == frozenset(
            {BackendCapability.UART_RECEIVE}
        )
        snapshot = connection.descriptor.connection_provenance.to_snapshot()
        assert snapshot.backend_schema_version == 1
        assert {f.name for f in snapshot.fields}.isdisjoint(
            {"write_timeout_ms", "write_acknowledgement_scope"}
        )
        assert not any(event[:2] == ("set", "write_timeout") for event in handle.events)
        assert handle.writes == []
        assert factory.calls == [{"port": None}]
    finally:
        await connection.close()
    assert handle.close_calls == 1


@pytest.mark.parametrize("windows", [False, True], ids=["posix", "windows-shaped"])
@pytest.mark.asyncio
async def test_t010_opt_in_configures_closed_timeout_and_captures_provenance_v2(
    handles: HandleFactory,
    monkeypatch: pytest.MonkeyPatch,
    windows: bool,
) -> None:
    monkeypatch.setattr(basic_serial, "_running_on_windows", lambda: windows)
    legacy = handles()
    legacy_backend, _ = backend(legacy, enabled=None)
    old = await legacy_backend.open()
    try:
        old_snapshot = old.descriptor.connection_provenance.to_snapshot()
    finally:
        await old.close()
    handle = handles()
    adapter, factory = backend(handle)
    connection = await adapter.open()
    try:
        assert connection.descriptor.capabilities.values == frozenset(
            {BackendCapability.UART_RECEIVE, BackendCapability.UART_SEND}
        )
        assignments = [
            i
            for i, event in enumerate(handle.events)
            if event[:2] == ("set", "write_timeout")
        ]
        assert len(assignments) == 1
        assert handle.events[assignments[0]] == ("set", "write_timeout", 1.0)
        assert assignments[0] < handle.events.index(("open",))
        snapshot = connection.descriptor.connection_provenance.to_snapshot()
        assert (
            snapshot.envelope_version,
            snapshot.backend_kind,
            snapshot.backend_schema_version,
        ) == (1, "basic_serial", 2)
        values = {f.name: f.value for f in snapshot.fields}
        assert values == {
            **{f.name: f.value for f in old_snapshot.fields},
            "write_timeout_ms": 1000,
            "write_acknowledgement_scope": "backend_acceptance",
        }
        assert values["electrical_verification"] == "not_verified"
        assert values["open_transition_guarantee"] == "not_guaranteed"
        assert handle.writes == []
        assert factory.calls == [{"port": None}]
    finally:
        await connection.close()


@pytest.mark.parametrize(
    "effective", [None, 0, 0.5, 2.0, float("inf"), float("nan"), "1"]
)
@pytest.mark.asyncio
async def test_t010_effective_timeout_mismatch_closes_without_using_connection(
    handles: HandleFactory,
    effective: object,
) -> None:
    handle = handles(effective_settings={"write_timeout": effective})
    adapter, factory = backend(handle)
    with pytest.raises(NormalizedBackendFailure) as caught:
        await adapter.open()
    assert (caught.value.operation, caught.value.kind) == (
        BackendFailureOperation.OPEN,
        BackendFailureKind.CONFIGURATION_REJECTED,
    )
    assert handle.close_calls == 1 and not handle.is_open
    assert handle.read_calls == 0 and handle.writes == []
    assert factory.calls == [{"port": None}]


@pytest.mark.asyncio
async def test_t010_write_timeout_setter_failure_never_opens_or_writes(
    handles: HandleFactory,
) -> None:
    handle = handles(
        assignment_errors={
            "write_timeout": serial.SerialException("unsupported timeout")
        }
    )
    adapter, _ = backend(handle)
    with pytest.raises(NormalizedBackendFailure) as caught:
        await adapter.open()
    assert (caught.value.operation, caught.value.kind) == (
        BackendFailureOperation.OPEN,
        BackendFailureKind.CONFIGURATION_REJECTED,
    )
    assert ("open",) not in handle.events
    assert handle.close_calls == 1
    assert handle.writes == []


@pytest.mark.parametrize(
    ("payload", "returned", "status", "count"),
    [
        (bytes(range(256)), 256, BackendWriteStatus.ACKNOWLEDGED, 256),
        (bytes(range(256)), 255, BackendWriteStatus.PARTIAL, 255),
        (bytes(range(256)), 1, BackendWriteStatus.PARTIAL, 1),
        (bytes(range(256)), 0, BackendWriteStatus.PARTIAL, 0),
        (b"\0", 1, BackendWriteStatus.ACKNOWLEDGED, 1),
        (b"\xff", 0, BackendWriteStatus.PARTIAL, 0),
        (bytes(range(256)) * 16, 4096, BackendWriteStatus.ACKNOWLEDGED, 4096),
        (bytes(range(256)) * 16, 4095, BackendWriteStatus.PARTIAL, 4095),
    ],
)
@pytest.mark.asyncio
async def test_t010_one_binary_write_reports_only_backend_acknowledged_prefix(
    handles: HandleFactory,
    payload: bytes,
    returned: int,
    status: BackendWriteStatus,
    count: int,
) -> None:
    handle = handles(write_result=returned)
    connection = await open_writer(handle)
    try:
        result = await connection.write(payload)
        assert result == BackendWriteResult(status, count, None)
        assert handle.writes == [payload]
        assert handle.write_threads[0] != threading.get_ident()
        assert handle.max_active_writes == 1
        assert (
            handle.read_calls == 0
        )  # Writing creates neither an RX event nor a reader.
    finally:
        await connection.close()
    assert handle.close_calls == 1


@pytest.mark.parametrize(
    "returned", [True, False, None, -1, 257, 2**63, 256.0, "256", b"256", object()]
)
@pytest.mark.asyncio
async def test_t010_malformed_count_is_failure_with_unknown_progress(
    handles: HandleFactory,
    returned: object,
) -> None:
    handle = handles(write_result=returned)
    connection = await open_writer(handle)
    try:
        result = await connection.write(bytes(range(256)))
        assert result == BackendWriteResult(
            BackendWriteStatus.FAILURE,
            None,
            BackendFailureKind.INTERNAL_CONTRACT_FAILURE,
        )
        assert handle.writes == [bytes(range(256))]
        assert handle.read_calls == 0
    finally:
        await connection.close()


class WindowsLoss(OSError):
    def __init__(self) -> None:
        super().__init__("unrelated diagnostic")
        self.winerror = 1167


@pytest.mark.parametrize(
    ("error", "status", "failure"),
    [
        (
            serial.SerialTimeoutException("possibly accepted a prefix"),
            BackendWriteStatus.TIMEOUT,
            None,
        ),
        (
            serial.SerialException(errno.ENODEV, "unrelated diagnostic"),
            BackendWriteStatus.DISCONNECTED,
            None,
        ),
        (
            OSError(errno.ENXIO, "unrelated diagnostic"),
            BackendWriteStatus.DISCONNECTED,
            None,
        ),
        (WindowsLoss(), BackendWriteStatus.DISCONNECTED, None),
        (
            serial.SerialException(
                errno.EIO, "ENODEV device disconnected winerror1167"
            ),
            BackendWriteStatus.FAILURE,
            BackendFailureKind.IO_FAILURE,
        ),
        (
            OSError(errno.EBADF, "unrelated diagnostic"),
            BackendWriteStatus.FAILURE,
            BackendFailureKind.IO_FAILURE,
        ),
        (
            serial.SerialException("device disconnected ENODEV no such device"),
            BackendWriteStatus.FAILURE,
            BackendFailureKind.IO_FAILURE,
        ),
        (
            RuntimeError("unknown library failure"),
            BackendWriteStatus.FAILURE,
            BackendFailureKind.IO_FAILURE,
        ),
    ],
)
@pytest.mark.asyncio
async def test_t010_exception_after_possible_progress_never_fabricates_count_or_retries(
    handles: HandleFactory,
    error: Exception,
    status: BackendWriteStatus,
    failure: BackendFailureKind | None,
) -> None:
    handle = handles(write_error=error)
    connection = await open_writer(handle)
    try:
        result = await connection.write(bytes(range(256)))
        assert result == BackendWriteResult(status, None, failure)
        assert handle.possibly_accepted_prefix == b"\0\1\2"
        assert handle.writes == [bytes(range(256))]
        assert (
            handle.read_calls == 0
        )  # TX failures do not manufacture RX disconnection events.
    finally:
        await connection.close()


@pytest.mark.parametrize(
    ("error", "status", "failure"),
    [
        (
            serial.SerialTimeoutException("possible progress"),
            BackendWriteStatus.TIMEOUT,
            None,
        ),
        (
            serial.SerialException(errno.ENODEV, "device lost during write"),
            BackendWriteStatus.DISCONNECTED,
            None,
        ),
        (
            serial.SerialException(errno.EIO, "unknown progress"),
            BackendWriteStatus.FAILURE,
            BackendFailureKind.IO_FAILURE,
        ),
    ],
)
@pytest.mark.asyncio
async def test_t010_tx_failure_does_not_replace_or_invent_authoritative_rx(
    handles: HandleFactory,
    error: Exception,
    status: BackendWriteStatus,
    failure: BackendFailureKind | None,
) -> None:
    handle = handles(write_error=error, read_results=(b"\0\xffstill RX",))
    connection = await open_writer(handle)
    try:
        result = await connection.write(b"request")
        assert result == BackendWriteResult(status, None, failure)
        event = await next_event(connection.events())
        assert isinstance(event, RxBytesObserved)
        assert event.payload == b"\0\xffstill RX"
        assert handle.read_calls == handle.max_active_reads == 1
        assert handle.writes == [b"request"]
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_t010_pending_rx_does_not_starve_write_worker(
    handles: HandleFactory,
) -> None:
    # Existing002 read uses the default pool. One blocked reader must not occupy
    # the writer's only execution capacity. Polling signals consumes no worker.
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1))
    gate = threading.Event()
    handle = handles(read_results=(b"\0\xffearly RX",), read_gates=(gate,))
    connection = await open_writer(handle)
    stream = connection.events()
    rx = asyncio.create_task(next_event(stream))
    tx: asyncio.Task[BackendWriteResult] | None = None
    try:
        await signalled(handle.read_started[0])
        with pytest.raises(EventStreamAlreadyConsumedError):
            connection.events()
        tx = asyncio.create_task(connection.write(bytes(range(256))))
        result = await settled_task(tx)
        assert result == BackendWriteResult(BackendWriteStatus.ACKNOWLEDGED, 256, None)
        assert not rx.done() and not gate.is_set()
        gate.set()
        event = await settled_task(rx)
        assert isinstance(event, RxBytesObserved) and event.payload == b"\0\xffearly RX"
        assert handle.read_calls == handle.max_active_reads == 1
        assert handle.writes == [bytes(range(256))]
    finally:
        gate.set()
        await asyncio.gather(rx, *([] if tx is None else [tx]), return_exceptions=True)
        await connection.close()


@pytest.mark.asyncio
async def test_t010_pending_write_does_not_stop_authoritative_rx(
    handles: HandleFactory,
) -> None:
    gate = threading.Event()
    handle = handles(write_gate=gate, read_results=(b"\0\xffduring TX",))
    connection = await open_writer(handle)
    tx = asyncio.create_task(connection.write(bytes(range(256))))
    rx: asyncio.Task[BackendEvent] | None = None
    try:
        await signalled(handle.write_started)
        stream = connection.events()
        rx = asyncio.create_task(next_event(stream))
        event = await settled_task(rx)
        assert (
            isinstance(event, RxBytesObserved) and event.payload == b"\0\xffduring TX"
        )
        assert not tx.done() and handle.active_writes == 1
        assert handle.read_calls == handle.max_active_reads == 1
        with pytest.raises(EventStreamAlreadyConsumedError):
            connection.events()
        gate.set()
        assert await settled_task(tx) == BackendWriteResult(
            BackendWriteStatus.ACKNOWLEDGED, 256, None
        )
        assert handle.writes == [bytes(range(256))]
    finally:
        gate.set()
        await asyncio.gather(tx, *([] if rx is None else [rx]), return_exceptions=True)
        await connection.close()


@pytest.mark.asyncio
async def test_t010_cancelled_write_waiter_joins_submitted_work_before_settling(
    handles: HandleFactory,
) -> None:
    gate = threading.Event()
    handle = handles(write_gate=gate)
    connection = await open_writer(handle)
    tx = asyncio.create_task(connection.write(bytes(range(256))))
    try:
        await signalled(handle.write_started)
        tx.cancel()
        await asyncio.sleep(0)
        tx.cancel()
        await asyncio.sleep(0)
        assert not tx.done()
        assert handle.active_writes == 1
        assert handle.close_calls == 0
        gate.set()
        with pytest.raises(asyncio.CancelledError):
            await settled_task(tx)
        assert handle.write_finished.is_set() and handle.active_writes == 0
        assert handle.writes == [bytes(range(256))]
    finally:
        gate.set()
        await asyncio.gather(tx, return_exceptions=True)
        await connection.close()


@pytest.mark.parametrize("close_error", [None, serial.SerialException("close failed")])
@pytest.mark.asyncio
async def test_t010_close_joins_write_before_one_physical_close(
    handles: HandleFactory,
    close_error: Exception | None,
) -> None:
    gate = threading.Event()
    handle = handles(write_gate=gate, close_error=close_error)
    connection = await open_writer(handle)
    tx = asyncio.create_task(connection.write(bytes(range(256))))
    close: asyncio.Task[None] | None = None
    try:
        await signalled(handle.write_started)
        close = asyncio.create_task(connection.close())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not close.done()
        assert handle.close_calls == 0
        gate.set()
        assert await settled_task(tx) == BackendWriteResult(
            BackendWriteStatus.ACKNOWLEDGED, 256, None
        )
        if close_error is None:
            await settled_task(close)
            await connection.close()
        else:
            with pytest.raises(NormalizedBackendFailure) as caught:
                await settled_task(close)
            assert (caught.value.operation, caught.value.kind) == (
                BackendFailureOperation.CLOSE,
                BackendFailureKind.IO_FAILURE,
            )
        assert handle.close_calls == 1
        assert handle.write_timeline == ["write_begin", "write_end", "close"]
    finally:
        gate.set()
        await asyncio.gather(
            tx, *([] if close is None else [close]), return_exceptions=True
        )


@pytest.mark.parametrize(
    "cancel_read_error", [None, serial.SerialException("cancel read failed")]
)
@pytest.mark.asyncio
async def test_t010_close_joins_both_workers_even_when_read_cancellation_fails(
    handles: HandleFactory,
    cancel_read_error: Exception | None,
) -> None:
    read_gate, write_gate = threading.Event(), threading.Event()
    handle = handles(
        write_gate=write_gate,
        read_results=(b"",),
        read_gates=(read_gate,),
        cancel_read_error=cancel_read_error,
    )
    connection = await open_writer(handle)
    rx = asyncio.create_task(next_event(connection.events()))
    tx = asyncio.create_task(connection.write(bytes(range(256))))
    close: asyncio.Task[None] | None = None
    try:
        await signalled(handle.read_started[0])
        await signalled(handle.write_started)
        close = asyncio.create_task(connection.close())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert handle.close_calls == 0 and not close.done()
        write_gate.set()
        await settled_task(tx)
        assert handle.close_calls == 0  # The read is still owned and blocked.
        await signalled(handle.cancel_read_called)
        read_gate.set()
        if cancel_read_error is None:
            await settled_task(close)
        else:
            with pytest.raises(NormalizedBackendFailure) as caught:
                await settled_task(close)
            assert (caught.value.operation, caught.value.kind) == (
                BackendFailureOperation.CLOSE,
                BackendFailureKind.IO_FAILURE,
            )
        with pytest.raises(StopAsyncIteration):
            await settled_task(rx)
        assert handle.close_calls == 1
        assert handle.write_timeline == ["write_begin", "write_end", "close"]
        assert handle.writes == [bytes(range(256))]
    finally:
        read_gate.set()
        write_gate.set()
        await asyncio.gather(
            rx, tx, *([] if close is None else [close]), return_exceptions=True
        )
