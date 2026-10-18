"""Owned receive-only Follow delivery over the existing Core subscription."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import replace

from dutchmate_core.evidence import JournalFailure
from dutchmate_core.follow import (
    FollowBatch,
    FollowEnd,
    FollowRejected,
    FollowRequest,
    FollowStart,
)
from dutchmate_core.runtime import (
    FollowSubscription,
    ObservationRuntime,
    RuntimeRejectedError,
)
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from dutchmate_service.evidence_http import (
    _DeliveryLimit,
    _encode,
    _marker,
    _range,
    _record,
    _session,
    evidence_rejection_response,
)
from dutchmate_service.http import (
    _MEDIA,
    _header_values,
    _observation_view,
    _read_body,
    _reject_constant,
    _unique_pairs,
    error_response,
)

_REJECTIONS = {
    "no_associated_session": 404,
    "session_not_associated": 409,
    "not_active": 409,
    "follow_unavailable": 503,
    "busy": 409,
    "read_capacity": 503,
    "delivery_too_large": 413,
}


def follow_error(status: int, source: str, code: str) -> Response:
    """Only private, fixed Follow categories reach this boundary."""
    return Response(
        _encode({"error": {"source": source, "code": code}}),
        status_code=status,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


def follow_rejection_response(error: Exception) -> Response:
    if isinstance(error, FollowRejected):
        return follow_error(_REJECTIONS[error.kind], "follow", error.kind)
    if isinstance(error, (JournalFailure, RuntimeRejectedError)):
        return evidence_rejection_response(error)
    return error_response(500, "service", "internal_failure")


async def validate_follow_request(
    scope: Scope, receive: Receive
) -> FollowRequest | Response:
    media = _header_values(scope, b"content-type")
    try:
        valid = (
            len(media) == 1
            and _MEDIA.fullmatch(media[0].decode("ascii").strip(" \t")) is not None
        )
    except UnicodeError:
        valid = False
    if not valid:
        return error_response(415, "request", "unsupported_media_type")
    body = await _read_body(receive, zero=False)
    if isinstance(body, Response):
        return body
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
        if type(value) is not dict or set(value) != {"session_id"}:
            raise ValueError("invalid_request")
        return FollowRequest(_session(value["session_id"]))
    except ValueError, TypeError, RecursionError:
        return error_response(422, "request", "invalid_request")


def _frame(value: object) -> bytes:
    # Reuse the existing canonical encoder and its limit+1 overflow accumulator.
    return _encode(value) + b"\n"


def _started(start: FollowStart, request: FollowRequest) -> bytes:
    if not isinstance(start, FollowStart) or start.session_id != request.session_id:
        raise TypeError("invalid Follow start")
    replace(start)
    provenance = start.provenance
    return _frame(
        {
            "type": "started",
            "run_id": start.run_id,
            "session_id": start.session_id.value,
            "start_sequence": start.start_sequence,
            "provenance": {
                "connection_id": provenance.connection_id.value,
                "segment_id": provenance.segment_id.value,
                **_observation_view(provenance),
            },
        }
    )


def _terminal(end: FollowEnd, offered: int) -> bytes:
    replace(end)
    if end.source_end_exclusive is not None and end.source_end_exclusive < offered:
        raise ValueError("source end precedes offered position")
    return _frame(
        {
            "type": "terminal",
            "reason": end.reason,
            "next_sequence": offered,
            "source_end_exclusive": end.source_end_exclusive,
        }
    )


class _UnusableDelivery(Exception):
    """No further response/frame may be attempted on this transport."""


async def _join(owner: asyncio.Task[None]) -> None:
    while not owner.done():
        try:
            await asyncio.shield(owner)
        except asyncio.CancelledError:
            continue
    owner.result()


class FollowStream:
    """One strongly retained admission/delivery/cleanup owner, independent of capture.

    Construction schedules work without awaiting it. The app registers this job
    before its first await, and retains it until subscriber cleanup has joined.
    """

    def __init__(
        self,
        runtime: ObservationRuntime,
        request: FollowRequest,
        receive: Receive,
        accepting: Callable[[], bool],
    ) -> None:
        loop = asyncio.get_running_loop()
        self._ready: asyncio.Future[Response] = loop.create_future()
        self._delivery: asyncio.Future[Send] = loop.create_future()
        self._pull: asyncio.Task[FollowBatch | FollowEnd] | None = None
        self._cancelled = False
        self._entered = False
        self._settling = False
        self._last_frame = 0.0
        self._initial_frame: bytes | None = None
        self.task = asyncio.create_task(self._own(runtime, request, accepting))
        self.task.add_done_callback(self._completed)
        self._observer = asyncio.create_task(self._disconnected(receive))

    @staticmethod
    def _completed(task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            task.exception()

    def cancel(self) -> None:
        # Exactly one cancellation enters the owner. Later client/lifespan loss
        # joins cleanup instead of interrupting it at another resource await.
        if not self._cancelled and not self._settling and not self.task.done():
            self._cancelled = True
            # A task cancelled before its first step never enters finally.
            # Let this owner bootstrap cleanup without admitting Core work.
            if self._entered:
                self.task.cancel()

    async def _disconnected(self, receive: Receive) -> None:
        try:
            while (await receive())["type"] != "http.disconnect":
                pass
        except asyncio.CancelledError:
            return
        except Exception:
            pass
        self.cancel()

    async def response(self) -> Response:
        try:
            return await asyncio.shield(self._ready)
        except asyncio.CancelledError:
            self.cancel()
            await _join(self.task)
            raise

    async def deliver(self, send: Send) -> None:
        if not self._delivery.done():
            self._delivery.set_result(send)
        try:
            await asyncio.shield(self.task)
        except asyncio.CancelledError:
            self.cancel()
            await _join(self.task)
            raise

    async def _own(
        self,
        runtime: ObservationRuntime,
        request: FollowRequest,
        accepting: Callable[[], bool],
    ) -> None:
        source: FollowSubscription | None = None
        rejection: Response | None = None
        self._entered = True
        try:
            if self._cancelled:
                raise asyncio.CancelledError()
            if not accepting():
                rejection = error_response(503, "service", "stopping")
            else:
                source = await runtime.start_follow(request)
                self._initial_frame = _started(source.start, request)
                response = _FollowResponse(self)
                self._ready.set_result(response)
                send = await self._delivery
                await self._stream(source, send, response.raw_headers)
        except asyncio.CancelledError:
            pass
        except _UnusableDelivery:
            pass
        except _DeliveryLimit:
            rejection = follow_error(413, "follow", "delivery_too_large")
        except Exception as error:
            rejection = follow_rejection_response(error)
        finally:
            self._settling = True
            self._initial_frame = None
            # Cancelling the public Core pull only cancels its waiter: Core owns
            # and joins any submitted query before returning from cancellation.
            if self._pull is not None:
                if not self._pull.done():
                    self._pull.cancel()
                await asyncio.gather(self._pull, return_exceptions=True)
                self._pull = None
            if source is not None:
                try:
                    await source.close()
                except Exception:
                    pass  # No raw resource/cleanup exception escapes delivery.
            self._observer.cancel()
            await asyncio.gather(self._observer, return_exceptions=True)
            if not self._ready.done():
                if rejection is None:
                    self._ready.cancel()
                else:
                    self._ready.set_result(rejection)

    async def _send(self, send: Send, message: dict[str, object]) -> None:
        try:
            async with asyncio.timeout(5):
                await send(message)
        except Exception:
            raise _UnusableDelivery() from None

    async def _send_frame(self, send: Send, frame: bytes) -> None:
        await self._send(
            send, {"type": "http.response.body", "body": frame, "more_body": True}
        )
        self._last_frame = asyncio.get_running_loop().time()

    async def _next(
        self, source: FollowSubscription, send: Send
    ) -> FollowBatch | FollowEnd:
        assert self._pull is None
        self._pull = asyncio.create_task(source.pull())
        while True:
            remaining = max(
                0.0, self._last_frame + 1 - asyncio.get_running_loop().time()
            )
            done, _ = await asyncio.wait((self._pull,), timeout=remaining)
            if done:
                pending, self._pull = self._pull, None
                return pending.result()
            await self._send_frame(send, _frame({"type": "heartbeat"}))

    async def _end(self, end: FollowEnd, offered: int, send: Send) -> None:
        await self._send_frame(send, _terminal(end, offered))
        await self._send(
            send, {"type": "http.response.body", "body": b"", "more_body": False}
        )

    async def _stream(
        self,
        source: FollowSubscription,
        send: Send,
        headers: list[tuple[bytes, bytes]],
    ) -> None:
        offered = source.start.start_sequence
        await self._send(
            send, {"type": "http.response.start", "status": 200, "headers": headers}
        )
        try:
            first, self._initial_frame = self._initial_frame, None
            assert first is not None
            await self._send_frame(send, first)
            del first
            while True:
                result = await self._next(source, send)
                if isinstance(result, FollowEnd):
                    await self._end(result, offered, send)
                    return
                if not isinstance(result, FollowBatch):
                    raise TypeError("invalid Follow result")
                # A bounded page of references only. Drop each payload as it is
                # consumed, without a retained tuple/page/prefetch chain.
                gap, records = result.gap, list(result.records)
                del result
                if gap is not None:
                    if gap.missed_range.start_inclusive != offered:
                        raise ValueError("noncontiguous Follow gap")
                    await self._send_frame(
                        send,
                        _frame(
                            {
                                "type": "gap",
                                "missed_range": _range(gap.missed_range),
                                "retention_marker": _marker(gap.retention_marker),
                            }
                        ),
                    )
                    offered = gap.missed_range.end_exclusive
                    gap = None
                while records:
                    record = records.pop(0)
                    if record.sequence != offered:
                        raise ValueError("noncontiguous Follow record")
                    await self._send_frame(
                        send, _frame({"type": "record", "record": _record(record)})
                    )
                    offered += 1
                    del record
        except _UnusableDelivery:
            raise
        except _DeliveryLimit:
            await self._end(FollowEnd("delivery_too_large", None), offered, send)
        except Exception:
            await self._end(FollowEnd("source_failed", None), offered, send)


class _FollowResponse(Response):
    def __init__(self, job: FollowStream) -> None:
        super().__init__(
            status_code=200,
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store"},
        )
        self.raw_headers = [
            (k, v) for k, v in self.raw_headers if k != b"content-length"
        ]
        self._job = job

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._job.deliver(send)
