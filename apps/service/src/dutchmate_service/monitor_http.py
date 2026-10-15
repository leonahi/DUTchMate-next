"""Bounded Monitor wire delivery; observation and durability policy stay in Core."""

import base64
import json

from dutchmate_core.evidence import JournalFailure
from dutchmate_core.model import EvidenceReference
from dutchmate_core.monitor import MonitorRejected, MonitorReport, MonitorRequest
from dutchmate_core.runtime import RuntimeRejectedError
from starlette.responses import Response
from starlette.types import Receive, Scope

from dutchmate_service.evidence_http import (
    _clock_view,
    _DeliveryLimit,
    _encode,
    _integer,
    _match_view,
    _range,
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
    "monitor_unavailable": 503,
    "capability_unavailable": 409,
    "busy": 409,
    "evidence_policy_incompatible": 422,
}


def _monitor_error(status: int, code: str) -> Response:
    return Response(
        _encode({"error": {"source": "monitor", "code": code}}),
        status_code=status,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


def monitor_rejection_response(error: Exception) -> Response:
    if isinstance(error, MonitorRejected):
        return _monitor_error(_REJECTIONS[error.kind], error.kind)
    if isinstance(error, (JournalFailure, RuntimeRejectedError)):
        return evidence_rejection_response(error)
    return error_response(500, "service", "internal_failure")


def _condition(value: object) -> bytes:
    if type(value) is not str or not 1 <= len(value) <= 344:
        raise ValueError("invalid_request")
    decoded = base64.b64decode(value, validate=True)
    if (
        not 1 <= len(decoded) <= 256
        or base64.b64encode(decoded).decode("ascii") != value
    ):
        raise ValueError("invalid_request")
    return decoded


async def validate_monitor_request(
    scope: Scope, receive: Receive
) -> MonitorRequest | Response:
    """After security/readiness, validate only the four closed wire inputs."""
    media = _header_values(scope, b"content-type")
    try:
        valid_media = (
            len(media) == 1
            and _MEDIA.fullmatch(media[0].decode("ascii").strip(" \t")) is not None
        )
    except UnicodeError:
        valid_media = False
    if not valid_media:
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
            "condition_base64",
            "timeout_ms",
            "max_rx_bytes",
        }:
            raise ValueError("invalid_request")
        return MonitorRequest(
            _session(value["session_id"]),
            _condition(value["condition_base64"]),
            _integer(value["timeout_ms"], minimum=1, maximum=4000),
            _integer(value["max_rx_bytes"], minimum=1, maximum=1048576),
        )
    except ValueError, TypeError, RecursionError:
        return error_response(422, "request", "invalid_request")


def _reference(value: EvidenceReference | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {"session_id": value.session_id.value, "sequence": value.sequence}


def monitor_response(report: MonitorReport) -> Response:
    """Project settled immutable facts with an independent whole JSON bound."""
    try:
        if not isinstance(report, MonitorReport):
            raise TypeError("unknown Monitor report")
        body = _encode(
            {
                "run_id": report.run_id,
                "session_id": report.session_id.value,
                "operation_id": report.operation_id,
                "provenance": {
                    "connection_id": report.provenance.connection_id.value,
                    "segment_id": report.provenance.segment_id.value,
                    **_observation_view(report.provenance),
                },
                "outcome": report.outcome.value,
                "started_record": _reference(report.started_record),
                "ended_record": _reference(report.ended_record),
                "window": _range(report.window),
                "examined_rx_bytes": report.examined_rx_bytes,
                "observer_loss_records": report.observer_loss_records,
                "match": _match_view(report.match),
                "clock": _clock_view(report.clock),
                "durability": report.durability,
                "end_failure": None
                if report.end_failure is None
                else {
                    "source": report.end_failure.source,
                    "code": report.end_failure.code,
                },
            }
        )
    except _DeliveryLimit:
        return _monitor_error(413, "delivery_too_large")
    except Exception:
        return error_response(500, "service", "internal_failure")
    return Response(
        body, media_type="application/json", headers={"Cache-Control": "no-store"}
    )
