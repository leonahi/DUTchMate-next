"""Closed Interact delivery and one strongly owned service transaction job."""

import asyncio
import base64
import json
from collections.abc import Callable
from dataclasses import replace

from dutchmate_core.evidence import JournalFailure
from dutchmate_core.interact import InteractReport, InteractRequest
from dutchmate_core.model import EvidenceReference
from dutchmate_core.monitor import InteractRejected
from dutchmate_core.runtime import ObservationRuntime, RuntimeRejectedError
from starlette.responses import Response
from starlette.types import Receive, Scope

from dutchmate_service.evidence_http import (
    _DeliveryLimit,
    _encode,
    _integer,
    _interact_observation_view,
    _session,
    _tx_view,
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
    "busy": 409,
    "policy_denied": 409,
    "capability_unavailable": 409,
    "interact_unavailable": 503,
    "evidence_policy_incompatible": 422,
}


def interact_error(status: int, source: str, code: str) -> Response:
    return Response(
        _encode({"error": {"source": source, "code": code}}),
        status_code=status,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


def interact_rejection_response(error: Exception) -> Response:
    if isinstance(error, InteractRejected):
        return interact_error(_REJECTIONS[error.kind], "interact", error.kind)
    if isinstance(error, (JournalFailure, RuntimeRejectedError)):
        return evidence_rejection_response(error)
    return error_response(500, "service", "internal_failure")


def _bytes(value: object, *, maximum: int, encoded_maximum: int) -> bytes:
    if type(value) is not str or not 1 <= len(value) <= encoded_maximum:
        raise ValueError("invalid_request")
    decoded = base64.b64decode(value, validate=True)
    if (
        not 1 <= len(decoded) <= maximum
        or base64.b64encode(decoded).decode("ascii") != value
    ):
        raise ValueError("invalid_request")
    return decoded


async def validate_interact_request(
    scope: Scope, receive: Receive
) -> InteractRequest | Response:
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
        if type(value) is not dict or set(value) != {
            "session_id",
            "payload_base64",
            "conditions_base64",
            "timeout_ms",
            "max_rx_bytes",
        }:
            raise ValueError("invalid_request")
        conditions = value["conditions_base64"]
        if type(conditions) is not list or not 1 <= len(conditions) <= 4:
            raise ValueError("invalid_request")
        return InteractRequest(
            _session(value["session_id"]),
            _bytes(value["payload_base64"], maximum=4096, encoded_maximum=5464),
            tuple(_bytes(c, maximum=256, encoded_maximum=344) for c in conditions),
            _integer(value["timeout_ms"], minimum=1, maximum=4000),
            _integer(value["max_rx_bytes"], minimum=1, maximum=1048576),
        )
    except ValueError, TypeError, RecursionError:
        return error_response(422, "request", "invalid_request")


def _reference(value: EvidenceReference | None) -> dict[str, object] | None:
    return (
        None
        if value is None
        else {"session_id": value.session_id.value, "sequence": value.sequence}
    )


def interact_response(report: InteractReport) -> Response:
    try:
        if not isinstance(report, InteractReport):
            raise TypeError("unknown Interact report")
        # Revalidate application invariants before projecting externally supplied
        # facts. Invalid facts are an internal failure, never a backend report.
        replace(report)
        body = _encode(
            {
                "run_id": report.run_id,
                "session_id": report.session_id.value,
                "operation_id": report.operation_id,
                "provenance": {
                    "connection_id": report.provenance.connection_id.value,
                    "segment_id": report.provenance.segment_id.value,
                    **_observation_view(report.provenance),
                    "boundary_basis": "core_observation_order",
                    "causation": "not_established",
                },
                "payload_base64": base64.b64encode(report.payload).decode("ascii"),
                "conditions_base64": [
                    base64.b64encode(c).decode("ascii") for c in report.conditions
                ],
                "outcome": report.outcome.value,
                "started_record": _reference(report.started_record),
                "tx_settled_record": _reference(report.tx_settled_record),
                "ended_record": _reference(report.ended_record),
                "tx": _tx_view(report.tx),
                "observation": _interact_observation_view(report.observation),
                "durability": report.durability,
                "audit_failures": [
                    {"record_kind": f.record_kind, "source": f.source, "code": f.code}
                    for f in report.audit_failures
                ],
            }
        )
    except _DeliveryLimit:
        return interact_error(413, "interact", "delivery_too_large")
    except Exception:
        return error_response(500, "service", "internal_failure")
    return Response(
        body, media_type="application/json", headers={"Cache-Control": "no-store"}
    )


class InteractJob:
    """Retain the Core waiter through cancellation, write and audit settlement.

    The app registers this concrete job before yielding and removes it only on
    task completion. Cancellation enters the Core waiter once; its existing owner
    latches operation-local cancellation and joins all admitted work.
    """

    def __init__(
        self,
        owner: ObservationRuntime,
        request: InteractRequest,
        accepting: Callable[[], bool],
    ) -> None:
        self._entered = False
        self._cancelled = False
        self.task = asyncio.create_task(self.invoke(owner, request, accepting))
        self.task.add_done_callback(self._completed)

    @staticmethod
    def _completed(task: asyncio.Task[Response]) -> None:
        if not task.cancelled():
            task.exception()

    def cancel(self) -> None:
        if not self._cancelled and not self.task.done():
            self._cancelled = True
            if self._entered:
                self.task.cancel()

    async def invoke(
        self,
        owner: ObservationRuntime,
        request: InteractRequest,
        accepting: Callable[[], bool],
    ) -> Response:
        self._entered = True
        if self._cancelled:
            raise asyncio.CancelledError()
        if not accepting():
            return error_response(503, "service", "stopping")
        try:
            return interact_response(await owner.interact(request))
        except Exception as error:
            return interact_rejection_response(error)

    async def _join(self) -> None:
        while not self.task.done():
            try:
                await asyncio.shield(self.task)
            except asyncio.CancelledError:
                continue
        if not self.task.cancelled():
            self.task.exception()

    async def _disconnected(self, receive: Receive) -> None:
        while (await receive())["type"] != "http.disconnect":
            pass

    async def response(self, receive: Receive) -> Response:
        shielded = asyncio.shield(self.task)
        observer = asyncio.create_task(self._disconnected(receive))
        try:
            done, _ = await asyncio.wait(
                (shielded, observer), return_when=asyncio.FIRST_COMPLETED
            )
            if observer in done:
                # A failed/lost receive is unusable delivery too. Never forward
                # transport exception text or detach the continuously owned run.
                if not observer.cancelled():
                    observer.exception()
                raise asyncio.CancelledError()
            return shielded.result()
        except asyncio.CancelledError:
            self.cancel()
            await self._join()
            raise
        finally:
            shielded.cancel()
            observer.cancel()
            await asyncio.gather(observer, return_exceptions=True)
