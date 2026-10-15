"""Host monotonic clock for one runtime incarnation's Monitor observations."""

import asyncio
from time import monotonic_ns
from uuid import uuid4

from dutchmate_core.model import validate_persisted_counter


class MonotonicMonitorClock:
    def __init__(self) -> None:
        self._origin_id = str(uuid4())

    @property
    def origin_id(self) -> str:
        return self._origin_id

    def now_ns(self) -> int:
        now = monotonic_ns()
        validate_persisted_counter(now, name="host clock sample")
        return now

    async def wait_until(self, deadline_ns: int) -> None:
        validate_persisted_counter(deadline_ns, name="host clock deadline")
        while (remaining := deadline_ns - self.now_ns()) > 0:
            await asyncio.sleep(remaining / 1000000000)
