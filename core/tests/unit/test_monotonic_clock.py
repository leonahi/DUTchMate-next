"""T010: infrastructure clock waits for a host deadline, including early wakeups."""

import asyncio
import importlib
import importlib.util
from typing import Any
from uuid import UUID

import pytest

from dutchmate_core import model


def _adapter() -> Any:
    name = "dutchmate_core.adapters.monotonic_clock"
    assert importlib.util.find_spec(name) is not None, (
        "T010 missing: host clock adapter"
    )
    return importlib.import_module(name)


def test_host_clock_has_a_canonical_distinct_origin_and_exact_ns_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter()
    monkeypatch.setattr(adapter, "monotonic_ns", lambda: 123456789)
    first, second = adapter.MonotonicMonitorClock(), adapter.MonotonicMonitorClock()
    assert first.origin_id == str(UUID(first.origin_id))
    assert first.origin_id != second.origin_id
    assert first.now_ns() == 123456789


@pytest.mark.asyncio
async def test_host_clock_wait_rechecks_early_wakeup_until_exact_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter()
    now = 100
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        nonlocal now
        sleeps.append(delay)
        now = 1000000099 if len(sleeps) == 1 else 1000000100

    monkeypatch.setattr(adapter, "monotonic_ns", lambda: now)
    monkeypatch.setattr(adapter.asyncio, "sleep", sleep)
    clock = adapter.MonotonicMonitorClock()
    await clock.wait_until(1000000100)
    assert sleeps == [1.0, 0.000000001]
    await clock.wait_until(1000000100)
    await clock.wait_until(0)
    assert len(sleeps) == 2


@pytest.mark.parametrize("bad", [True, -1, model.SQLITE_INTEGER_MAX + 1, 1.0])
@pytest.mark.asyncio
async def test_host_clock_rejects_invalid_deadline(bad: object) -> None:
    clock = _adapter().MonotonicMonitorClock()
    with pytest.raises((TypeError, ValueError)):
        await clock.wait_until(bad)


@pytest.mark.asyncio
async def test_host_clock_wait_remains_cancellable_without_elapsed_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter()
    entered = asyncio.Event()

    async def sleep(delay: float) -> None:
        entered.set()
        await asyncio.get_running_loop().create_future()

    monkeypatch.setattr(adapter, "monotonic_ns", lambda: 100)
    monkeypatch.setattr(adapter.asyncio, "sleep", sleep)
    waiter = asyncio.create_task(adapter.MonotonicMonitorClock().wait_until(200))
    await asyncio.wait_for(entered.wait(), 3)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
