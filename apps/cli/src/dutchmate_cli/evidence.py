"""Evidence inputs and closed delivery projections; no Core or journal policy."""

import base64
import json
import re
from typing import cast
from uuid import UUID

from dutchmate_cli import context

_MAX = 9223372036854775807
_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,1024}")
_CURSOR_KEYS = (
    "version",
    "session_id",
    "range_start_inclusive",
    "range_end_exclusive",
    "snapshot_end_exclusive",
    "next_sequence",
)
_EVIDENCE_ERRORS = {
    (404, "no_associated_session"),
    (409, "session_not_associated"),
    (503, "read_unavailable"),
    (409, "source_changed"),
    (503, "read_capacity"),
    (413, "delivery_too_large"),
}
_JOURNAL_ERRORS = {
    (422, "invalid_input"),
    (409, "session_mismatch"),
    (404, "journal_missing"),
    (503, "busy"),
    (409, "closed"),
    *(
        (500, kind)
        for kind in (
            "journal_exists",
            "incompatible_application",
            "incompatible_schema_version",
            "incompatible_record_version",
            "incompatible_provenance_envelope_version",
            "corrupt_journal",
            "invariant_violation",
            "capacity",
            "capacity/database_over_ceiling",
            "capacity/physical_ceiling_unavailable",
            "capacity/sequence_exhausted",
            "capacity/counter_exhausted",
            "read_only",
            "permission_denied",
            "io_failure",
        )
    ),
}


def _view(value: object, keys: tuple[str, ...]) -> dict[str, object]:
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("invalid_response")
    return {key: value[key] for key in keys}


def _text(value: object, *, empty: bool = False) -> str:
    if type(value) is not str or (not empty and not value):
        raise ValueError("invalid_response")
    value.encode("utf-8")
    return value


def _counter(value: object, *, minimum: int = 0, maximum: int = _MAX) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("invalid_response")
    return value


def _choice(value: object, choices: set[str]) -> str:
    text = _text(value)
    if text not in choices:
        raise ValueError("invalid_response")
    return text


def _array(value: object) -> list[object]:
    if type(value) is not list:
        raise ValueError("invalid_response")
    return cast(list[object], value)


def _input_session(value: str) -> str:
    _text(value)
    if "\0" in value or len(value.encode()) > 256:
        raise ValueError("invalid_arguments")
    return value


def _input_cursor(value: str | None) -> str | None:
    if value is not None and (
        type(value) is not str or _TOKEN.fullmatch(value) is None
    ):
        raise ValueError("invalid_arguments")
    return value


def record_request(session: str, sequence: int) -> dict[str, object]:
    try:
        return {"session_id": _input_session(session), "sequence": _counter(sequence)}
    except ValueError, TypeError:
        pass
    raise context.CliFailure(context.CliFailureKind.INVALID_ARGUMENTS)


def page_request(
    session: str,
    max_records: int,
    max_charged_bytes: int,
    start: int | None,
    end: int | None,
    cursor: str | None,
) -> dict[str, object]:
    try:
        session = _input_session(session)
        if start is not None or end is not None:
            start, end = _counter(start), _counter(end)
            if start > end:
                raise ValueError("invalid_arguments")
        return {
            "session_id": session,
            "start_inclusive": start,
            "end_exclusive": end,
            "max_records": _counter(max_records, minimum=1, maximum=4096),
            "max_charged_bytes": _counter(
                max_charged_bytes, minimum=1, maximum=1048576
            ),
            "cursor": _input_cursor(cursor),
        }
    except ValueError, TypeError:
        pass
    raise context.CliFailure(context.CliFailureKind.INVALID_ARGUMENTS)


def _timestamp(value: object) -> dict[str, object]:
    view = _view(value, ("domain_id", "value"))
    _text(view["domain_id"])
    _counter(view["value"])
    return view


def _domain(value: object) -> dict[str, object]:
    view = _view(value, ("domain_id", "observer", "meaning", "unit", "origin_id"))
    _text(view["domain_id"])
    _text(view["origin_id"])
    _choice(view["observer"], {"host", "device"})
    _choice(view["meaning"], {"observation"})
    _choice(view["unit"], {"nanosecond", "microsecond", "tick"})
    return view


def _provenance(value: object) -> dict[str, object]:
    view = _view(
        value,
        (
            "connection_id",
            "segment_id",
            "capabilities",
            "backend_observation_timestamp_domain",
            "loss_observability",
            "connection_provenance",
        ),
    )
    _text(view["connection_id"])
    _text(view["segment_id"])
    for capability in _array(view["capabilities"]):
        _choice(
            capability,
            {
                "uart_receive",
                "uart_send",
                "serial_line_control",
                "gpio_control",
                "gpio_events",
            },
        )
    view["backend_observation_timestamp_domain"] = _domain(
        view["backend_observation_timestamp_domain"]
    )
    loss = view["loss_observability"]
    if type(loss) is not dict:
        raise ValueError("invalid_response")
    if loss.get("kind") == "upstream_loss_not_observable":
        view["loss_observability"] = _view(loss, ("kind",))
    else:
        loss_view = _view(loss, ("kind", "observer_id", "scope"))
        _choice(loss_view["kind"], {"observer_reports_uart_loss"})
        _text(loss_view["observer_id"])
        _text(loss_view["scope"])
        view["loss_observability"] = loss_view
    envelope = _view(
        view["connection_provenance"],
        ("envelope_version", "backend_kind", "backend_schema_version", "fields"),
    )
    _counter(envelope["envelope_version"], minimum=1, maximum=1)
    _text(envelope["backend_kind"])
    _counter(envelope["backend_schema_version"], minimum=1)
    fields: list[dict[str, object]] = []
    for item in _array(envelope["fields"]):
        field = _view(item, ("name", "value"))
        _text(field["name"])
        scalar = field["value"]
        if scalar is not None and type(scalar) not in {str, int, bool}:
            raise ValueError("invalid_response")
        if type(scalar) is str:
            _text(scalar, empty=True)
        fields.append(field)
    envelope["fields"] = fields
    view["connection_provenance"] = envelope
    return view


def _record(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("invalid_response")
    if value.get("kind") == "operation_started":
        return _operation_started(value)
    if value.get("kind") == "operation_ended":
        return _operation_ended(value)
    kind = _choice(
        value.get("kind"),
        {"segment_started", "rx_bytes", "observer_loss", "segment_ended"},
    )
    match kind:
        case "segment_started":
            view = _view(value, ("kind", "sequence", "provenance"))
            view["provenance"] = _provenance(view["provenance"])
        case "rx_bytes":
            view = _view(
                value,
                (
                    "kind",
                    "sequence",
                    "connection_id",
                    "segment_id",
                    "observed_at",
                    "payload_base64",
                ),
            )
            view["observed_at"] = _timestamp(view["observed_at"])
            payload = _text(view["payload_base64"], empty=True)
            if (
                base64.b64encode(base64.b64decode(payload, validate=True)).decode(
                    "ascii"
                )
                != payload
            ):
                raise ValueError("invalid_response")
        case "observer_loss":
            view = _view(
                value,
                (
                    "kind",
                    "sequence",
                    "connection_id",
                    "segment_id",
                    "observer_id",
                    "scope",
                    "cause",
                    "lost_bytes",
                    "observed_at",
                ),
            )
            _text(view["observer_id"])
            _text(view["scope"])
            _choice(view["cause"], {"overflow", "other_observed_loss"})
            if view["lost_bytes"] is not None:
                _counter(view["lost_bytes"], minimum=1)
            view["observed_at"] = _timestamp(view["observed_at"])
        case "segment_ended":
            view = _view(
                value, ("kind", "sequence", "connection_id", "segment_id", "reason")
            )
            _choice(
                view["reason"],
                {
                    "explicit_stop",
                    "disconnected",
                    "timestamp_origin_reset",
                    "recording_failure",
                    "transport_failure",
                },
            )
        case _:
            raise ValueError("invalid_response")
    _counter(view["sequence"], maximum=_MAX - 1)
    if kind != "segment_started":
        _text(view["connection_id"])
        _text(view["segment_id"])
    return view


_MONITOR_OUTCOMES = {
    "matched",
    "timeout",
    "byte_limit",
    "disconnected",
    "detached",
    "timestamp_origin_reset",
    "recording_failure",
    "transport_failure",
    "service_stopping",
}


def _uuid(value: object) -> str:
    text = _text(value)
    if str(UUID(text)) != text:
        raise ValueError("invalid_response")
    return text


def _condition_base64(value: object) -> str:
    text = _text(value)
    if len(text) > 344:
        raise ValueError("invalid_response")
    decoded = base64.b64decode(text, validate=True)
    if (
        not 1 <= len(decoded) <= 256
        or base64.b64encode(decoded).decode("ascii") != text
    ):
        raise ValueError("invalid_response")
    return text


def _operation_clock(value: object) -> dict[str, object]:
    view = _view(
        value, ("origin_id", "started_at_ns", "deadline_at_ns", "decided_at_ns")
    )
    _uuid(view["origin_id"])
    for name in ("started_at_ns", "deadline_at_ns", "decided_at_ns"):
        _counter(view[name])
    return view


def _operation_match(value: object, outcome: str) -> dict[str, object] | None:
    if outcome != "matched":
        if value is not None:
            raise ValueError("invalid_response")
        return None
    view = _view(value, ("start", "end"))
    for name, offset in (("start", "byte_offset"), ("end", "byte_offset_exclusive")):
        endpoint = _view(view[name], ("sequence", offset))
        _counter(endpoint["sequence"], maximum=_MAX - 1)
        _counter(endpoint[offset], minimum=0 if name == "start" else 1)
        view[name] = endpoint
    return view


def _operation_facts(view: dict[str, object]) -> None:
    """Validate wire variants only; do not reconstruct observation decisions."""
    outcome = _choice(view["outcome"], _MONITOR_OUTCOMES)
    if view["window"] is None:
        raise ValueError("invalid_response")
    view["window"] = _range(view["window"])
    _counter(
        view["examined_rx_bytes"],
        minimum=1 if outcome in {"matched", "byte_limit"} else 0,
        maximum=1048576,
    )
    _counter(view["observer_loss_records"])
    view["match"] = _operation_match(view["match"], outcome)
    view["clock"] = _operation_clock(view["clock"])


def _operation_started(value: object) -> dict[str, object]:
    view = _view(
        value,
        (
            "kind",
            "sequence",
            "operation_id",
            "operation_kind",
            "provenance",
            "timeout_ms",
            "max_rx_bytes",
            "clock_origin_id",
            "condition_base64",
        ),
    )
    _counter(view["sequence"], maximum=_MAX - 1)
    _uuid(view["operation_id"])
    _choice(view["operation_kind"], {"monitor"})
    view["provenance"] = _provenance(view["provenance"])
    _counter(view["timeout_ms"], minimum=1, maximum=4000)
    _counter(view["max_rx_bytes"], minimum=1, maximum=1048576)
    _uuid(view["clock_origin_id"])
    _condition_base64(view["condition_base64"])
    return view


def _operation_ended(value: object) -> dict[str, object]:
    view = _view(
        value,
        (
            "kind",
            "sequence",
            "operation_id",
            "operation_kind",
            "start_sequence",
            "window",
            "outcome",
            "examined_rx_bytes",
            "observer_loss_records",
            "match",
            "clock",
        ),
    )
    _counter(view["sequence"], maximum=_MAX - 1)
    _uuid(view["operation_id"])
    _choice(view["operation_kind"], {"monitor"})
    _counter(view["start_sequence"], maximum=_MAX - 1)
    _operation_facts(view)
    return view


def _range(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    view = _view(value, ("start_inclusive", "end_exclusive"))
    for counter in view.values():
        _counter(counter)
    return view


def _endpoint(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    view = _view(value, ("timestamp", "domain"))
    view["timestamp"] = _timestamp(view["timestamp"])
    view["domain"] = _domain(view["domain"])
    return view


def _marker(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    view = _view(
        value,
        (
            "expired_range",
            "first_discarded_timestamp",
            "last_discarded_timestamp",
            "discarded_record_count",
            "discarded_rx_payload_byte_count",
            "discarded_charged_bytes",
        ),
    )
    if view["expired_range"] is None:
        raise ValueError("invalid_response")
    view["expired_range"] = _range(view["expired_range"])
    for name in ("first_discarded_timestamp", "last_discarded_timestamp"):
        view[name] = _endpoint(view[name])
    for name in (
        "discarded_record_count",
        "discarded_rx_payload_byte_count",
        "discarded_charged_bytes",
    ):
        _counter(view[name])
    return view


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid_response")
        result[key] = value
    return result


def _nonfinite(value: str) -> object:
    raise ValueError("invalid_response")


def _reply_cursor(value: object) -> str | None:
    if value is None:
        return None
    token = _text(value)
    if _TOKEN.fullmatch(token) is None:
        raise ValueError("invalid_response")
    raw = base64.b64decode(
        token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
    )
    cursor = _view(
        json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite
        ),
        _CURSOR_KEYS,
    )
    _counter(cursor["version"], minimum=1, maximum=1)
    _text(cursor["session_id"])
    for name in ("range_start_inclusive", "snapshot_end_exclusive", "next_sequence"):
        _counter(cursor[name])
    if cursor["range_end_exclusive"] is not None:
        _counter(cursor["range_end_exclusive"])
    encoded = json.dumps(
        cursor, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()
    if base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=") != token:
        raise ValueError("invalid_response")
    return token


def reply(value: object) -> dict[str, object]:
    """Validate shape and representation, preserving all service-reported facts."""
    envelope = _view(value, ("run_id", "session_id", "page"))
    _text(envelope["run_id"])
    _text(envelope["session_id"])
    page = _view(
        envelope["page"],
        (
            "records",
            "snapshot_end_exclusive",
            "expired_range",
            "retention_marker",
            "never_existed_range",
            "outcome",
            "truncated",
            "continuation",
            "charged_bytes",
            "next_record_required_bytes",
        ),
    )
    page["records"] = [_record(record) for record in _array(page["records"])]
    _counter(page["snapshot_end_exclusive"])
    for name in ("expired_range", "never_existed_range"):
        page[name] = _range(page[name])
    page["retention_marker"] = _marker(page["retention_marker"])
    _choice(page["outcome"], {"complete", "partial", "expired", "not_found"})
    if type(page["truncated"]) is not bool:
        raise ValueError("invalid_response")
    page["continuation"] = _reply_cursor(page["continuation"])
    _counter(page["charged_bytes"])
    if page["next_record_required_bytes"] is not None:
        _counter(page["next_record_required_bytes"], minimum=1)
    envelope["page"] = page
    return envelope


def recognized_error(value: object, status: int) -> bool:
    error = _view(_view(value, ("error",))["error"], ("source", "code"))
    source, code = _text(error["source"]), _text(error["code"])
    return (source == "evidence" and (status, code) in _EVIDENCE_ERRORS) or (
        source == "journal" and (status, code) in _JOURNAL_ERRORS
    )
