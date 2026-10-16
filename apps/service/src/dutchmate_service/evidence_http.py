"""Strict bounded retrieval delivery; association and journal policy stay in Core."""

import base64
import json
import re
from collections.abc import Iterator

from dutchmate_core.evidence import (
    EvidenceCursor,
    EvidenceRetrievalRequest,
    JournalFailure,
    JournalFailureKind,
)
from dutchmate_core.evidence_access import EvidenceReadRejected, RunEvidencePage
from dutchmate_core.model import (
    SQLITE_INTEGER_MAX,
    BackendObservationTimestamp,
    ClientAnnotationEvidence,
    EvidenceRangeReference,
    EvidenceRecord,
    EvidenceReference,
    MonitorClockFacts,
    MonitorMatch,
    ObserverLossEvidence,
    OperationEndedEvidence,
    OperationStartedEvidence,
    RetentionMarker,
    RetentionTimestampEndpoint,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentStartedEvidence,
    SequenceRange,
    SessionId,
)
from dutchmate_core.runtime import RuntimeRejectedError
from starlette.responses import Response
from starlette.types import Receive, Scope

from dutchmate_service.http import (
    _MEDIA,
    _header_values,
    _observation_view,
    _read_body,
    _reject_constant,
    _unique_pairs,
    error_response,
    rejection_response,
)

_LIMIT = 1048576
_CURSOR_LIMIT = 1024
_TOKEN = re.compile(rf"[A-Za-z0-9_-]{{1,{_CURSOR_LIMIT}}}")
_CURSOR_KEYS = (
    "version",
    "session_id",
    "range_start_inclusive",
    "range_end_exclusive",
    "snapshot_end_exclusive",
    "next_sequence",
)
_READ_CODES = {
    "no_associated_session": 404,
    "session_not_associated": 409,
    "read_unavailable": 503,
    "source_changed": 409,
    "read_capacity": 503,
}
_JOURNAL_CODES = {
    JournalFailureKind.INVALID_INPUT: 422,
    JournalFailureKind.SESSION_MISMATCH: 409,
    JournalFailureKind.JOURNAL_MISSING: 404,
    JournalFailureKind.BUSY: 503,
    JournalFailureKind.CLOSED: 409,
}


class _DeliveryLimit(ValueError):
    """The whole report cannot be delivered; never rewrite its page facts."""


def _read_error(status: int, source: str, code: str) -> Response:
    # Only fixed normalized categories reach this private encoder.
    return Response(
        json.dumps(
            {"error": {"source": source, "code": code}},
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode(),
        status_code=status,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


def evidence_rejection_response(error: Exception) -> Response:
    """Preserve normalized kinds without inspecting detail, operation or causes."""
    if isinstance(error, EvidenceReadRejected):
        return _read_error(_READ_CODES[error.kind], "evidence", error.kind)
    if isinstance(error, JournalFailure):
        return _read_error(
            _JOURNAL_CODES.get(error.kind, 500), "journal", error.kind.value
        )
    if isinstance(error, RuntimeRejectedError):
        return rejection_response(error)
    return error_response(500, "service", "internal_failure")


def _session(value: object) -> SessionId:
    if type(value) is not str or "\x00" in value or not 1 <= len(value.encode()) <= 256:
        raise ValueError("invalid_request")
    return SessionId(value)


def _integer(
    value: object, *, minimum: int = 0, maximum: int = SQLITE_INTEGER_MAX
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("invalid_request")
    return value


def _cursor_view(cursor: EvidenceCursor) -> dict[str, object]:
    return {
        "version": 1,
        "session_id": cursor.session_id.value,
        "range_start_inclusive": cursor.range_start_inclusive,
        "range_end_exclusive": cursor.range_end_exclusive,
        "snapshot_end_exclusive": cursor.snapshot_end_exclusive,
        "next_sequence": cursor.next_sequence,
    }


def _encode_cursor(cursor: EvidenceCursor) -> str:
    document = _encode(_cursor_view(cursor))
    if 4 * ((len(document) + 2) // 3) > _CURSOR_LIMIT:
        raise _DeliveryLimit()
    return base64.urlsafe_b64encode(document).decode("ascii").rstrip("=")


def _decode_cursor(token: object) -> EvidenceCursor | None:
    if token is None:
        return None
    if type(token) is not str or _TOKEN.fullmatch(token) is None:
        raise ValueError("invalid_request")
    raw = base64.b64decode(
        token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
    )
    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_pairs,
        parse_constant=_reject_constant,
    )
    if type(value) is not dict or tuple(value) != _CURSOR_KEYS:
        raise ValueError("invalid_request")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("invalid_request")
    cursor = EvidenceCursor(
        _session(value["session_id"]),
        _integer(value["range_start_inclusive"]),
        None
        if value["range_end_exclusive"] is None
        else _integer(value["range_end_exclusive"]),
        _integer(value["snapshot_end_exclusive"]),
        _integer(value["next_sequence"]),
    )
    if _encode_cursor(cursor) != token:
        raise ValueError("invalid_request")
    return cursor


async def validate_evidence_request(
    scope: Scope,
    receive: Receive,
) -> EvidenceReference | EvidenceRetrievalRequest | Response:
    """Wire validation only, after security/readiness and before job admission."""
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
        if type(value) is not dict:
            raise ValueError("invalid_request")
        if scope["raw_path"] == b"/v1/evidence/record":
            if set(value) != {"session_id", "sequence"}:
                raise ValueError("invalid_request")
            return EvidenceReference(
                _session(value["session_id"]), _integer(value["sequence"])
            )
        if set(value) != {
            "session_id",
            "start_inclusive",
            "end_exclusive",
            "max_records",
            "max_charged_bytes",
            "cursor",
        }:
            raise ValueError("invalid_request")
        session = _session(value["session_id"])
        start, end = value["start_inclusive"], value["end_exclusive"]
        reference: SessionId | EvidenceRangeReference
        if start is None and end is None:
            reference = session
        else:
            reference = EvidenceRangeReference(session, _integer(start), _integer(end))
        return EvidenceRetrievalRequest(
            reference,
            _integer(value["max_records"], minimum=1, maximum=4096),
            _integer(value["max_charged_bytes"], minimum=1, maximum=_LIMIT),
            _decode_cursor(value["cursor"]),
        )
    except ValueError, TypeError, RecursionError:
        return error_response(422, "request", "invalid_request")


def _range(value: SequenceRange | None) -> dict[str, object] | None:
    return (
        None
        if value is None
        else {
            "start_inclusive": value.start_inclusive,
            "end_exclusive": value.end_exclusive,
        }
    )


def _timestamp(value: BackendObservationTimestamp) -> dict[str, object]:
    return {"domain_id": value.domain_id, "value": value.value}


def _endpoint(value: RetentionTimestampEndpoint | None) -> dict[str, object] | None:
    if value is None:
        return None
    domain = value.domain
    return {
        "timestamp": _timestamp(value.timestamp),
        "domain": {
            "domain_id": domain.domain_id,
            "observer": domain.observer.value,
            "meaning": domain.meaning.value,
            "unit": domain.unit.value,
            "origin_id": domain.origin_id,
        },
    }


def _marker(value: RetentionMarker | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "expired_range": _range(value.expired_range),
        "first_discarded_timestamp": _endpoint(value.first_discarded_timestamp),
        "last_discarded_timestamp": _endpoint(value.last_discarded_timestamp),
        "discarded_record_count": value.discarded_record_count,
        "discarded_rx_payload_byte_count": value.discarded_rx_payload_byte_count,
        "discarded_charged_bytes": value.discarded_charged_bytes,
    }


def _record(value: EvidenceRecord) -> dict[str, object]:
    if isinstance(value, ClientAnnotationEvidence):
        return {
            "kind": "client_annotation",
            "sequence": value.sequence,
            "assertion_class": value.assertion_class,
            "client_surface": value.client_surface,
            "attribution_basis": value.attribution_basis,
            "clock_origin_id": value.clock_origin_id,
            "received_at_ns": value.received_at_ns,
            "text": value.text,
        }
    if isinstance(value, OperationStartedEvidence):
        return {
            "kind": "operation_started",
            "sequence": value.sequence,
            "operation_id": value.operation_id,
            "operation_kind": value.operation_kind,
            "provenance": {
                "connection_id": value.provenance.connection_id.value,
                "segment_id": value.provenance.segment_id.value,
                **_observation_view(value.provenance),
            },
            "timeout_ms": value.timeout_ms,
            "max_rx_bytes": value.max_rx_bytes,
            "clock_origin_id": value.clock_origin_id,
            "condition_base64": base64.b64encode(value.condition).decode("ascii"),
        }
    if isinstance(value, OperationEndedEvidence):
        return {
            "kind": "operation_ended",
            "sequence": value.sequence,
            "operation_id": value.operation_id,
            "operation_kind": value.operation_kind,
            "start_sequence": value.start_sequence,
            "window": _range(value.window),
            "outcome": value.outcome.value,
            "examined_rx_bytes": value.examined_rx_bytes,
            "observer_loss_records": value.observer_loss_records,
            "match": _match_view(value.match),
            "clock": _clock_view(value.clock),
        }
    if isinstance(value, SegmentStartedEvidence):
        return {
            "kind": "segment_started",
            "sequence": value.sequence,
            "provenance": {
                "connection_id": value.connection_id.value,
                "segment_id": value.segment_id.value,
                **_observation_view(value.provenance),
            },
        }
    if not isinstance(
        value, (RxBytesEvidence, ObserverLossEvidence, SegmentEndedEvidence)
    ):
        raise TypeError("unknown normalized evidence record")
    common = {
        "sequence": value.sequence,
        "connection_id": value.connection_id.value,
        "segment_id": value.segment_id.value,
    }
    if isinstance(value, RxBytesEvidence):
        if 4 * ((len(value.payload) + 2) // 3) > _LIMIT:
            raise _DeliveryLimit()
        return {
            "kind": "rx_bytes",
            **common,
            "observed_at": _timestamp(value.observed_at),
            "payload_base64": base64.b64encode(value.payload).decode("ascii"),
        }
    if isinstance(value, ObserverLossEvidence):
        return {
            "kind": "observer_loss",
            **common,
            "observer_id": value.observer_id,
            "scope": value.scope,
            "cause": value.cause.value,
            "lost_bytes": value.lost_bytes,
            "observed_at": _timestamp(value.observed_at),
        }
    if isinstance(value, SegmentEndedEvidence):
        return {"kind": "segment_ended", **common, "reason": value.reason.value}
    raise TypeError("unknown normalized evidence record")


def _match_view(value: MonitorMatch | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "start": {
            "sequence": value.start.sequence,
            "byte_offset": value.start.byte_offset,
        },
        "end": {
            "sequence": value.end.sequence,
            "byte_offset_exclusive": value.end.byte_offset_exclusive,
        },
    }


def _clock_view(value: MonitorClockFacts) -> dict[str, object]:
    return {
        "origin_id": value.origin_id,
        "started_at_ns": value.started_at_ns,
        "deadline_at_ns": value.deadline_at_ns,
        "decided_at_ns": value.decided_at_ns,
    }


def _encode(value: object) -> bytes:
    """Canonical stdlib JSON escaping with at most limit+1 accumulated bytes.

    Projected arrays are lazy; each string scalar is encoded independently so
    metadata cannot produce an oversized intermediate JSON string allocation.
    """
    output = bytearray()

    def add(part: bytes) -> None:
        output.extend(part[: _LIMIT + 1 - len(output)])
        if len(output) > _LIMIT:
            raise _DeliveryLimit()

    def text(item: str) -> None:
        add(b'"')
        for char in item:
            # Ask stdlib for its exact short/control escapes, never encode a
            # possibly oversized metadata value all at once.
            if char in {'"', "\\"} or ord(char) < 32:
                add(json.dumps(char, ensure_ascii=False)[1:-1].encode())
            else:
                add(char.encode())
        add(b'"')

    def write(item: object) -> None:
        if item is None:
            add(b"null")
        elif type(item) is bool:
            add(b"true" if item else b"false")
        elif type(item) is int:
            add(str(item).encode("ascii"))
        elif isinstance(item, str):
            text(item)
        elif isinstance(item, dict):
            add(b"{")
            for index, (key, member) in enumerate(item.items()):
                if type(key) is not str:
                    raise TypeError("JSON key must be text")
                if index:
                    add(b",")
                text(key)
                add(b":")
                write(member)
            add(b"}")
        elif isinstance(item, (list, tuple, Iterator)):
            add(b"[")
            for index, member in enumerate(item):
                if index:
                    add(b",")
                write(member)
            add(b"]")
        else:
            raise TypeError("value is not projected JSON")

    write(value)
    return bytes(output)


def evidence_response(report: RunEvidencePage) -> Response:
    """Project page facts unchanged; overflow rejects the entire canonical report."""
    try:
        page = report.page
        body = _encode(
            {
                "run_id": report.run_id.value,
                "session_id": report.session_id.value,
                "page": {
                    "records": (_record(record) for record in page.records),
                    "snapshot_end_exclusive": page.snapshot_end_exclusive,
                    "expired_range": _range(page.expired_range),
                    "retention_marker": _marker(page.retention_marker),
                    "never_existed_range": _range(page.never_existed_range),
                    "outcome": page.outcome.value,
                    "truncated": page.truncated,
                    "continuation": None
                    if page.continuation is None
                    else _encode_cursor(page.continuation),
                    "charged_bytes": page.charged_bytes,
                    "next_record_required_bytes": page.next_record_required_bytes,
                },
            }
        )
    except _DeliveryLimit:
        return _read_error(413, "evidence", "delivery_too_large")
    except Exception:
        return error_response(500, "service", "internal_failure")
    return Response(
        body, media_type="application/json", headers={"Cache-Control": "no-store"}
    )
