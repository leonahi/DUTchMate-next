"""012 T012 RED: connection-owned write registration and every-path joins.

Both existing fixture factories run every case identically. Optional writer and
close probes live on test-owned instances only; shared fixture defaults stay
unchanged. Probe close deliberately does not join writes, so backend defensiveness
cannot conceal a missing Acquisition join. No Profile/policy or audit coordinator.
"""

import asyncio
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import cast

import pytest

from dutchmate_core import acquisition as aq
from dutchmate_core.backend import (
    BackendFailureKind,
    BackendWriteResult,
    BackendWriteStatus,
)
from dutchmate_core.evidence import InMemoryEvidenceRecorder, PendingEvidenceRecord
from dutchmate_core.model import (
    BackendCapabilities,
    BackendCapability,
    EvidenceRecord,
    RxBytesEvidence,
    SegmentStartedEvidence,
)
from tests.fakes import (
    BACKEND_FIXTURE_FACTORIES,
    BackendFixture,
    BackendFixtureFactory,
    FixtureConnectionCloseFailure,
    FixtureRecorderFailure,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.parametrize(
        "fixture_factory",
        BACKEND_FIXTURE_FACTORIES,
        ids=["basic-shape", "enhanced-shape"],
    ),
]
PAYLOAD = bytes(range(256))


async def bounded[T](work: Awaitable[T]) -> T:
    # Test watchdog only; shielding avoids manufacturing product cancellation.
    return await asyncio.wait_for(asyncio.shield(work), 3)


async def until(predicate: Callable[[], bool]) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0)

    await bounded(poll())


def submitter(
    owner: aq.Acquisition,
) -> Callable[[bytes], Awaitable[BackendWriteResult]]:
    operation = getattr(owner, "submit_uart_write", None)
    assert callable(operation), (
        "T012: missing synchronous Acquisition.submit_uart_write"
    )
    assert not inspect.iscoroutinefunction(operation), (
        "write registration must not await backend I/O"
    )
    return cast("Callable[[bytes], Awaitable[BackendWriteResult]]", operation)


@dataclass
class Receipt:
    work: Awaitable[BackendWriteResult]
    waiter: asyncio.Future[BackendWriteResult] | None = None

    def observe(self) -> asyncio.Future[BackendWriteResult]:
        if self.waiter is None:
            self.waiter = asyncio.ensure_future(self.work)
        return self.waiter


class WriteProbe:
    def __init__(
        self,
        fixture: BackendFixture,
        *,
        result: BackendWriteResult | None = None,
        close_fails: bool = False,
    ) -> None:
        self.fixture = fixture
        self.result = result
        self.close_fails = close_fails
        self.entered = asyncio.Event()
        self.allow = asyncio.Event()
        self.finished = asyncio.Event()
        self.close_entered = asyncio.Event()
        self.calls: list[bytes] = []
        self.active = 0
        self.cancellation_signals = 0
        self.close_calls = 0
        self.active_at_close: list[int] = []
        self.timeline: list[str] = []
        self.original_close = fixture.connection.close

    async def write(self, payload: bytes) -> BackendWriteResult:
        self.calls.append(payload)
        self.active += 1
        self.timeline.append("write_entered")
        self.entered.set()
        cancelled = False
        try:
            while not self.allow.is_set():
                try:
                    await self.allow.wait()
                except asyncio.CancelledError:
                    # Respect the normalized backend's independent join promise,
                    # while exposing cancellation wrongly forwarded by its owner.
                    self.cancellation_signals += 1
                    cancelled = True
            if cancelled:
                raise asyncio.CancelledError
            return self.result or BackendWriteResult(
                BackendWriteStatus.ACKNOWLEDGED, len(payload), None
            )
        finally:
            self.active -= 1
            self.timeline.append("write_settled")
            self.finished.set()

    async def close(self) -> None:
        self.close_calls += 1
        self.active_at_close.append(self.active)
        self.timeline.append("close_entered")
        self.close_entered.set()
        if self.close_fails:
            await self.fixture.connection.close_gate.enter()
            raise FixtureConnectionCloseFailure("T012 controlled close failure")
        await self.original_close()


class Recorder(InMemoryEvidenceRecorder):
    def __init__(
        self, reject_append: int | None = None, gate_start: bool = False
    ) -> None:
        super().__init__()
        self.append_count = 0
        self.reject_append = reject_append
        self.start_entered = asyncio.Event()
        self.allow_start = asyncio.Event()
        if not gate_start:
            self.allow_start.set()

    async def append(self, draft: PendingEvidenceRecord) -> EvidenceRecord:
        self.append_count += 1
        if self.append_count == 1:
            self.start_entered.set()
            await self.allow_start.wait()
        if self.append_count == self.reject_append:
            raise FixtureRecorderFailure("T012 controlled recording failure")
        return await super().append(draft)


@dataclass
class Scenario:
    fixture: BackendFixture
    probe: WriteProbe
    recorder: Recorder
    owner: aq.Acquisition
    receipts: list[Receipt] = field(default_factory=list)

    def submit(self, payload: bytes = PAYLOAD) -> Receipt:
        work = submitter(self.owner)(payload)
        assert inspect.isawaitable(work), "submission must expose normalized settlement"
        receipt = Receipt(work)
        self.receipts.append(receipt)
        return receipt


def install(
    fixture: BackendFixture,
    monkeypatch: pytest.MonkeyPatch,
    *,
    send_capability: bool = True,
    writer: bool = True,
    result: BackendWriteResult | None = None,
    close_fails: bool = False,
) -> WriteProbe:
    connection = fixture.connection
    if send_capability:
        connection.descriptor = replace(
            connection.descriptor,
            capabilities=BackendCapabilities(
                connection.descriptor.capabilities.values
                | {BackendCapability.UART_SEND}
            ),
        )
    probe = WriteProbe(fixture, result=result, close_fails=close_fails)
    if writer:
        monkeypatch.setattr(connection, "write", probe.write, raising=False)
    monkeypatch.setattr(connection, "close", probe.close)
    return probe


@asynccontextmanager
async def running(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
    *,
    send_capability: bool = True,
    writer: bool = True,
    result: BackendWriteResult | None = None,
    close_fails: bool = False,
    recorder: Recorder | None = None,
    owner: aq.Acquisition | None = None,
) -> AsyncIterator[Scenario]:
    fixture = fixture_factory()
    probe = install(
        fixture,
        monkeypatch,
        send_capability=send_capability,
        writer=writer,
        result=result,
        close_fails=close_fails,
    )
    recorder = recorder or Recorder()
    owner = owner or aq.Acquisition(recorder)
    scenario = Scenario(fixture, probe, recorder, owner)
    await bounded(owner.start(fixture.backend))
    await bounded(fixture.connection.read_gate.entered.wait())
    try:
        yield scenario
    finally:
        probe.allow.set()
        fixture.connection.close_gate.allow.set()
        recorder.allow_start.set()
        await bounded(owner.stop())
        await bounded(owner.join_terminated())
        if scenario.receipts:
            await bounded(
                asyncio.gather(
                    *(r.observe() for r in scenario.receipts), return_exceptions=True
                )
            )
        assert probe.active == 0
        assert all(active == 0 for active in probe.active_at_close)


def open_calls(fixture: BackendFixture) -> int:
    count = getattr(fixture.backend, "open_calls", None)
    assert type(count) is int
    return count


async def test_t012_shared_fixture_defaults_remain_receive_only(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    assert fixture.connection.descriptor.capabilities.values == frozenset(
        {BackendCapability.UART_RECEIVE}
    )
    assert not callable(getattr(fixture.connection, "write", None))
    owner = aq.Acquisition(InMemoryEvidenceRecorder())
    await owner.start(fixture.backend)
    try:
        await bounded(fixture.connection.read_gate.entered.wait())
        assert fixture.connection.consumer_calls == open_calls(fixture) == 1
    finally:
        await bounded(owner.stop())
        await bounded(owner.join_terminated())
    assert fixture.connection.close_calls == 1


async def test_t012_registration_is_synchronous_one_slot_before_any_await(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with running(fixture_factory, monkeypatch) as s:
        submit = submitter(s.owner)
        receipt = s.submit()
        assert s.probe.calls == []  # No backend I/O within synchronous registration.
        with pytest.raises((RuntimeError, TypeError, ValueError)):
            submit(b"second")
        assert s.probe.calls == []
        await bounded(s.probe.entered.wait())
        assert s.probe.calls == [PAYLOAD]
        assert s.fixture.connection.consumer_calls == open_calls(s.fixture) == 1
        s.probe.allow.set()
        assert await bounded(receipt.observe()) == BackendWriteResult(
            BackendWriteStatus.ACKNOWLEDGED, 256, None
        )
        assert len(s.recorder.snapshot()) == 1
        assert isinstance(s.recorder.snapshot()[0], SegmentStartedEvidence)


@pytest.mark.parametrize(
    ("payload", "count"), [(b"\0", 1), (PAYLOAD, 256), (PAYLOAD * 16, 4096)]
)
async def test_t012_mechanical_write_needs_no_profile_policy_or_audit_and_preserves_bytes(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    count: int,
) -> None:
    async with running(fixture_factory, monkeypatch) as s:
        receipt = s.submit(payload)
        await bounded(s.probe.entered.wait())
        await s.fixture.connection.emit_rx(b"\0\xffwhile TX waits", timestamp=1)
        await until(lambda: len(s.recorder.snapshot()) == 2)
        rx = s.recorder.snapshot()[1]
        assert isinstance(rx, RxBytesEvidence) and rx.payload == b"\0\xffwhile TX waits"
        assert (
            rx.observed_at.domain_id
            == s.fixture.connection.descriptor.backend_observation_timestamp_domain.domain_id
        )
        assert s.probe.active == 1
        assert s.fixture.connection.consumer_calls == open_calls(s.fixture) == 1
        s.probe.allow.set()
        assert await bounded(receipt.observe()) == BackendWriteResult(
            BackendWriteStatus.ACKNOWLEDGED, count, None
        )
        assert s.probe.calls == [payload]
        assert (
            len(s.recorder.snapshot()) == 2
        )  # The owner records no Interact/TX audit.


@pytest.mark.parametrize(
    "expected",
    [
        BackendWriteResult(BackendWriteStatus.ACKNOWLEDGED, 256, None),
        BackendWriteResult(BackendWriteStatus.PARTIAL, 0, None),
        BackendWriteResult(BackendWriteStatus.PARTIAL, 7, None),
        BackendWriteResult(BackendWriteStatus.TIMEOUT, None, None),
        BackendWriteResult(BackendWriteStatus.DISCONNECTED, None, None),
        BackendWriteResult(
            BackendWriteStatus.FAILURE, None, BackendFailureKind.IO_FAILURE
        ),
    ],
)
async def test_t012_normalized_settlement_preserves_known_and_unknown_acceptance(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
    expected: BackendWriteResult,
) -> None:
    async with running(fixture_factory, monkeypatch, result=expected) as s:
        receipt = s.submit()
        await bounded(s.probe.entered.wait())
        await s.fixture.connection.emit_rx(b"still authoritative", timestamp=1)
        await until(lambda: len(s.recorder.snapshot()) == 2)
        assert isinstance(s.recorder.snapshot()[1], RxBytesEvidence)
        assert s.probe.active == 1
        s.probe.allow.set()
        assert await bounded(receipt.observe()) == expected
        assert s.probe.calls == [PAYLOAD]


@pytest.mark.parametrize(
    ("send_capability", "writer"), [(False, True), (True, False), (False, False)]
)
async def test_t012_missing_capability_or_optional_contract_rejects_before_submission(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
    send_capability: bool,
    writer: bool,
) -> None:
    async with running(
        fixture_factory, monkeypatch, send_capability=send_capability, writer=writer
    ) as s:
        submit = submitter(s.owner)
        with pytest.raises((RuntimeError, TypeError, ValueError)):
            submit(PAYLOAD)
        assert s.probe.calls == [] and s.probe.active == 0
        assert s.owner.state is aq.AcquisitionState.ACQUIRING
        await s.fixture.connection.emit_rx(b"RX unchanged", timestamp=1)
        await until(lambda: len(s.recorder.snapshot()) == 2)
        assert s.fixture.connection.consumer_calls == open_calls(s.fixture) == 1


@pytest.mark.parametrize("stop_first", [False, True], ids=["idle", "stopped"])
async def test_t012_not_connected_is_rejected_synchronously_without_open(
    fixture_factory: BackendFixtureFactory,
    stop_first: bool,
) -> None:
    fixture = fixture_factory()
    owner = aq.Acquisition(InMemoryEvidenceRecorder())
    if stop_first:
        await owner.stop()
    submit = submitter(owner)
    with pytest.raises((RuntimeError, TypeError, ValueError)):
        submit(PAYLOAD)
    assert open_calls(fixture) == 0
    assert fixture.connection.consumer_calls == fixture.connection.close_calls == 0


async def test_t012_settlement_releases_one_slot_without_reopening_or_new_reader(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with running(fixture_factory, monkeypatch) as s:
        first = s.submit()
        s.probe.allow.set()
        assert await bounded(first.observe()) == BackendWriteResult(
            BackendWriteStatus.ACKNOWLEDGED, 256, None
        )
        s.probe.allow.clear()
        second = s.submit(b"\0\xffsecond")
        submit = submitter(s.owner)
        with pytest.raises((RuntimeError, TypeError, ValueError)):
            submit(b"overlap")
        await until(lambda: len(s.probe.calls) == 2)
        s.probe.allow.set()
        assert await bounded(second.observe()) == BackendWriteResult(
            BackendWriteStatus.ACKNOWLEDGED, 8, None
        )
        assert s.probe.calls == [PAYLOAD, b"\0\xffsecond"]
        assert s.fixture.connection.consumer_calls == open_calls(s.fixture) == 1


@pytest.mark.parametrize("cancel_before_backend", [False, True])
async def test_t012_cancelled_waiter_cannot_retract_registered_write_or_its_join(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
    cancel_before_backend: bool,
) -> None:
    async with running(fixture_factory, monkeypatch) as s:
        receipt = s.submit()
        waiter = receipt.observe()
        if not cancel_before_backend:
            await bounded(s.probe.entered.wait())
        waiter.cancel()
        await asyncio.sleep(0)
        waiter.cancel()
        await bounded(s.probe.entered.wait())
        assert s.probe.calls == [PAYLOAD] and s.probe.active == 1
        assert s.probe.cancellation_signals == 0
        submit = submitter(s.owner)
        with pytest.raises((RuntimeError, TypeError, ValueError)):
            submit(b"slot still owned")
        stop = asyncio.create_task(s.owner.stop())
        try:
            await until(lambda: s.owner.state is not aq.AcquisitionState.ACQUIRING)
            assert not s.probe.close_entered.is_set()
            assert not stop.done()
            s.probe.allow.set()
            assert await bounded(stop) is aq.AcquisitionState.STOPPED
            with pytest.raises(asyncio.CancelledError):
                await bounded(waiter)
            assert s.probe.finished.is_set()
            assert s.probe.timeline == [
                "write_entered",
                "write_settled",
                "close_entered",
            ]
        finally:
            s.probe.allow.set()
            await bounded(asyncio.gather(stop, return_exceptions=True))


@pytest.mark.parametrize(
    "cause",
    [
        "stop",
        "disconnect",
        "stream_end",
        "bad_timestamp",
        "bad_origin_reset",
        "recording_failure",
    ],
)
@pytest.mark.parametrize("close_fails", [False, True])
async def test_t012_every_terminal_path_seals_joins_then_closes_without_audit_dependency(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
    cause: str,
    close_fails: bool,
) -> None:
    recorder = Recorder(reject_append=2 if cause == "recording_failure" else None)
    async with running(
        fixture_factory, monkeypatch, recorder=recorder, close_fails=close_fails
    ) as s:
        submit = submitter(s.owner)
        receipt = s.submit()
        await bounded(s.probe.entered.wait())
        s.fixture.connection.close_gate.allow.clear()
        stop: asyncio.Task[aq.AcquisitionState] | None = None
        try:
            if cause == "stop":
                stop = asyncio.create_task(s.owner.stop())
            elif cause == "disconnect":
                await s.fixture.connection.disconnect()
            elif cause == "stream_end":
                await s.fixture.connection.end_stream_unexpectedly()
            elif cause == "bad_timestamp":
                await s.fixture.connection.emit_rx(
                    b"invalid timestamp domain", timestamp=1, domain_id="wrong-domain"
                )
            elif cause == "bad_origin_reset":
                await s.fixture.connection.reset_timestamp_origin(
                    s.fixture.connection.descriptor.backend_observation_timestamp_domain
                )
            else:
                await s.fixture.connection.emit_rx(b"recording rejected", timestamp=1)
            await until(lambda: s.owner.state is not aq.AcquisitionState.ACQUIRING)
            assert s.owner.state is aq.AcquisitionState.STOPPING
            assert not s.owner.snapshot().physical_release_confirmed
            assert not s.probe.close_entered.is_set()
            assert s.probe.active == 1 and s.probe.cancellation_signals == 0
            with pytest.raises((RuntimeError, TypeError, ValueError)):
                submit(b"sealed while join pending")
            s.probe.allow.set()
            assert await bounded(receipt.observe()) == BackendWriteResult(
                BackendWriteStatus.ACKNOWLEDGED, 256, None
            )
            await bounded(s.probe.close_entered.wait())
            # A released slot must not reopen admission while close is gated.
            with pytest.raises((RuntimeError, TypeError, ValueError)):
                submit(b"sealed after write settled")
            assert s.probe.calls == [PAYLOAD]
            assert not s.owner.snapshot().physical_release_confirmed
            s.fixture.connection.close_gate.allow.set()
            terminal = await bounded(s.owner.join_terminated())
            if stop is not None:
                await bounded(stop)
            assert terminal.close_failed is close_fails
            assert terminal.physical_release_confirmed is not close_fails
            expected_trigger = {
                "stop": "explicit_stop",
                "disconnect": "disconnected",
                "recording_failure": "recording_failure",
            }.get(cause, "transport_failure")
            assert terminal.terminal_trigger == expected_trigger
            assert terminal.state is (
                aq.AcquisitionState.STOPPED
                if cause in {"stop", "disconnect"} and not close_fails
                else aq.AcquisitionState.FAILED
            )
            with pytest.raises((RuntimeError, TypeError, ValueError)):
                submit(b"terminal generation")
            assert s.probe.close_calls == 1
            assert s.probe.timeline == [
                "write_entered",
                "write_settled",
                "close_entered",
            ]
            assert s.fixture.connection.consumer_calls == open_calls(s.fixture) == 1
            if close_fails:
                replacement = fixture_factory()
                with pytest.raises(aq.AcquisitionAlreadyActiveError):
                    await s.owner.start(replacement.backend)
                assert open_calls(replacement) == 0
        finally:
            s.probe.allow.set()
            s.fixture.connection.close_gate.allow.set()
            if stop is not None:
                await bounded(asyncio.gather(stop, return_exceptions=True))


async def test_t012_cancelled_generation_join_waiter_cannot_cancel_owned_write(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with running(fixture_factory, monkeypatch) as s:
        receipt = s.submit()
        await bounded(s.probe.entered.wait())
        stop = asyncio.create_task(s.owner.stop())
        join = asyncio.create_task(s.owner.join_terminated())
        try:
            await until(lambda: s.owner.state is aq.AcquisitionState.STOPPING)
            join.cancel()
            with pytest.raises(asyncio.CancelledError):
                await bounded(join)
            assert s.probe.active == 1 and s.probe.cancellation_signals == 0
            assert not s.probe.close_entered.is_set()
            s.probe.allow.set()
            assert await bounded(receipt.observe()) == BackendWriteResult(
                BackendWriteStatus.ACKNOWLEDGED, 256, None
            )
            assert await bounded(stop) is aq.AcquisitionState.STOPPED
            assert (await bounded(s.owner.join_terminated())).physical_release_confirmed
        finally:
            s.probe.allow.set()
            await bounded(asyncio.gather(stop, join, return_exceptions=True))


async def test_t012_connection_close_does_not_join_the_external_audit_owner(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with running(fixture_factory, monkeypatch) as s:
        receipt = s.submit()
        audit_entered, allow_audit = asyncio.Event(), asyncio.Event()

        async def audit() -> None:
            assert await receipt.observe() == BackendWriteResult(
                BackendWriteStatus.ACKNOWLEDGED, 256, None
            )
            audit_entered.set()
            await allow_audit.wait()

        audit_owner = asyncio.create_task(audit())
        stop: asyncio.Task[aq.AcquisitionState] | None = None
        try:
            await bounded(s.probe.entered.wait())
            stop = asyncio.create_task(s.owner.stop())
            await until(lambda: s.owner.state is aq.AcquisitionState.STOPPING)
            s.probe.allow.set()
            await bounded(audit_entered.wait())
            assert await bounded(stop) is aq.AcquisitionState.STOPPED
            terminal = await bounded(s.owner.join_terminated())
            assert terminal.physical_release_confirmed
            assert not audit_owner.done()  # Physical close joins transport, not audit.
            assert s.probe.active_at_close == [0]
        finally:
            s.probe.allow.set()
            allow_audit.set()
            await bounded(
                asyncio.gather(
                    audit_owner,
                    *([] if stop is None else [stop]),
                    return_exceptions=True,
                )
            )


async def test_t012_late_old_receipt_cannot_clear_or_close_a_replacement_generation(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with running(fixture_factory, monkeypatch) as first:
        old_id = first.owner.snapshot().provenance
        old_receipt = first.submit(b"old")
        await bounded(first.probe.entered.wait())
        stop = asyncio.create_task(first.owner.stop())
        candidate = fixture_factory()
        try:
            await until(lambda: first.owner.state is aq.AcquisitionState.STOPPING)
            with pytest.raises(aq.AcquisitionAlreadyActiveError):
                await first.owner.start(candidate.backend)
            assert open_calls(candidate) == 0
            first.probe.allow.set()
            assert await bounded(stop) is aq.AcquisitionState.STOPPED
        finally:
            first.probe.allow.set()
            await bounded(asyncio.gather(stop, return_exceptions=True))
        async with running(
            fixture_factory, monkeypatch, owner=first.owner, recorder=first.recorder
        ) as second:
            new_id = second.owner.snapshot().provenance
            assert old_id is not None and new_id is not None
            assert old_id.connection_id != new_id.connection_id
            assert old_id.segment_id != new_id.segment_id
            new_receipt = second.submit(b"new-generation")
            await bounded(second.probe.entered.wait())
            # First observation of the old receipt is deliberately after restart.
            assert await bounded(old_receipt.observe()) == BackendWriteResult(
                BackendWriteStatus.ACKNOWLEDGED, 3, None
            )
            submit = submitter(second.owner)
            with pytest.raises((RuntimeError, TypeError, ValueError)):
                submit(b"new slot still occupied")
            assert not second.fixture.connection.closed and second.probe.active == 1
            assert first.probe.calls == [b"old"] and first.probe.close_calls == 1
            second.probe.allow.set()
            assert await bounded(new_receipt.observe()) == BackendWriteResult(
                BackendWriteStatus.ACKNOWLEDGED, 14, None
            )
            assert second.probe.calls == [b"new-generation"]
            assert (
                second.fixture.connection.consumer_calls
                == open_calls(second.fixture)
                == 1
            )


@pytest.mark.parametrize("reject_start", [False, True])
async def test_t012_startup_and_startup_failure_cannot_admit_a_write(
    fixture_factory: BackendFixtureFactory,
    monkeypatch: pytest.MonkeyPatch,
    reject_start: bool,
) -> None:
    fixture = fixture_factory()
    probe = install(fixture, monkeypatch)
    recorder = Recorder(reject_append=1 if reject_start else None, gate_start=True)
    owner = aq.Acquisition(recorder)
    submit = submitter(owner)
    start = asyncio.create_task(owner.start(fixture.backend))
    admitted: asyncio.Future[BackendWriteResult] | None = None
    try:
        await bounded(recorder.start_entered.wait())
        assert owner.state is aq.AcquisitionState.STARTING
        with pytest.raises((RuntimeError, TypeError, ValueError)):
            submit(PAYLOAD)
        assert probe.calls == []
        recorder.allow_start.set()
        if reject_start:
            with pytest.raises(FixtureRecorderFailure):
                await bounded(start)
            assert (
                await bounded(owner.join_terminated())
            ).state is aq.AcquisitionState.FAILED
            with pytest.raises((RuntimeError, TypeError, ValueError)):
                submit(PAYLOAD)
            assert probe.close_calls == 1 and probe.active_at_close == [0]
        else:
            await bounded(start)
            assert owner.snapshot().state is aq.AcquisitionState.ACQUIRING
            # The same callable must recheck current readiness rather than cache
            # its previous STARTING rejection or bypass the committed-start ACK.
            admitted = asyncio.ensure_future(submit(PAYLOAD))
            await bounded(probe.entered.wait())
            probe.allow.set()
            assert await bounded(admitted) == BackendWriteResult(
                BackendWriteStatus.ACKNOWLEDGED, 256, None
            )
        assert probe.calls == ([] if reject_start else [PAYLOAD])
        assert open_calls(fixture) == 1
    finally:
        probe.allow.set()
        recorder.allow_start.set()
        await bounded(asyncio.gather(start, return_exceptions=True))
        await bounded(owner.stop())
        await bounded(owner.join_terminated())
        if admitted is not None:
            await bounded(asyncio.gather(admitted, return_exceptions=True))
