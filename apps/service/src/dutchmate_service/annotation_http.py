"""Closed annotation delivery; insertion, attribution and rate policy stay in Core."""

import json

from dutchmate_core.annotation import (
    AnnotationReceipt,
    AnnotationRejected,
    AnnotationRequest,
)
from dutchmate_core.evidence import JournalFailure
from dutchmate_core.runtime import RuntimeRejectedError
from starlette.responses import Response
from starlette.types import Receive, Scope

from dutchmate_service.evidence_http import (
    _DeliveryLimit,
    _encode,
    _record,
    _session,
    evidence_rejection_response,
)
from dutchmate_service.http import (
    _MEDIA,
    _header_values,
    _read_body,
    _reject_constant,
    _unique_pairs,
    error_response,
)

_REJECTIONS = {
    "no_associated_session": 404,
    "session_not_associated": 409,
    "not_active": 409,
    "annotation_unavailable": 503,
    "evidence_policy_incompatible": 422,
    "busy": 409,
    "rate_limited": 429,
}


def _annotation_error(status: int, code: str) -> Response:
    return Response(
        _encode({"error": {"source": "annotation", "code": code}}),
        status_code=status,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


def annotation_rejection_response(error: Exception) -> Response:
    if isinstance(error, AnnotationRejected):
        return _annotation_error(_REJECTIONS[error.kind], error.kind)
    if isinstance(error, (JournalFailure, RuntimeRejectedError)):
        return evidence_rejection_response(error)
    return error_response(500, "service", "internal_failure")


async def validate_annotation_request(
    scope: Scope, receive: Receive
) -> AnnotationRequest | Response:
    """After security/readiness, accept only the three bounded wire inputs."""
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
            "text",
            "client_surface",
        }:
            raise ValueError("invalid_request")
        surface = value["client_surface"]
        if type(surface) is not str or surface not in {"cli", "http"}:
            raise ValueError("invalid_request")
        return AnnotationRequest(_session(value["session_id"]), value["text"], surface)
    except ValueError, TypeError, RecursionError:
        return error_response(422, "request", "invalid_request")


def annotation_response(receipt: AnnotationReceipt) -> Response:
    """Project acknowledged immutable facts with the independent whole JSON cap."""
    try:
        if not isinstance(receipt, AnnotationReceipt):
            raise TypeError("unknown annotation receipt")
        body = _encode(
            {
                "run_id": receipt.run_id,
                "session_id": receipt.session_id.value,
                "reference": {
                    "session_id": receipt.reference.session_id.value,
                    "sequence": receipt.reference.sequence,
                },
                "annotation": _record(receipt.annotation),
            }
        )
    except _DeliveryLimit:
        return _annotation_error(413, "delivery_too_large")
    except Exception:
        return error_response(500, "service", "internal_failure")
    return Response(
        body, media_type="application/json", headers={"Cache-Control": "no-store"}
    )
