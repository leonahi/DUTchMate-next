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


def _record(value: object, *, api_version: int = 1) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("invalid_response")
    if api_version == 2:
        if value.get("kind") == "interact_started":
            return _interact_started(value)
        if value.get("kind") == "uart_tx_settled":
            return _uart_tx_settled(value)
        if value.get("kind") == "interact_ended":
            return _interact_ended(value)
    if value.get("kind") == "operation_started":
        return _operation_started(value)
    if value.get("kind") == "operation_ended":
        return _operation_ended(value)
    if value.get("kind") == "client_annotation":
        return _client_annotation(value)
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


def _annotation_text(value: object) -> str:
    text = _text(value)
    if "\0" in text or len(text.encode("utf-8")) > 1024:
        raise ValueError("invalid_response")
    return text


def _client_annotation(value: object) -> dict[str, object]:
    view = _view(
        value,
        (
            "kind", "sequence", "assertion_class", "client_surface",
            "attribution_basis", "clock_origin_id", "received_at_ns", "text",
        ),
    )
    _choice(view["kind"], {"client_annotation"})
    _counter(view["sequence"], maximum=_MAX - 1)
    _choice(view["assertion_class"], {"client_assertion"})
    _choice(view["client_surface"], {"cli", "http", "core"})
    _choice(view["attribution_basis"], {"client_asserted"})
    _uuid(view["clock_origin_id"])
    _counter(view["received_at_ns"])
    _annotation_text(view["text"])
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


_INTERACT_OBSERVATION_OUTCOMES = _MONITOR_OUTCOMES | {"cancelled", "tx_failed"}
_INTERACT_EXTERNAL_OUTCOMES = {
    "disconnected", "detached", "timestamp_origin_reset", "recording_failure",
    "transport_failure", "service_stopping", "cancelled",
}
_INTERACT_OUTCOMES = _MONITOR_OUTCOMES | {"cancelled", "write_timeout", "partial_write"}
_TX_KEYS = (
    "submitted", "status", "accepted_prefix_bytes", "failure_code",
    "acknowledgement_scope", "clock_origin_id", "settled_at_ns",
)
_BACKEND_FAILURE_CODES = {
    "invalid_request", "device_not_found", "permission_denied", "device_busy",
    "configuration_rejected", "line_state_setup_failed", "io_failure",
    "internal_contract_failure",
}


def _payload_base64(value: object) -> str:
    text = _text(value)
    if len(text) > 5464:
        raise ValueError("invalid_response")
    raw = base64.b64decode(text, validate=True)
    if not 1 <= len(raw) <= 4096 or base64.b64encode(raw).decode("ascii") != text:
        raise ValueError("invalid_response")
    return text


def _conditions(value: object) -> list[str]:
    items = _array(value)
    if not 1 <= len(items) <= 4:
        raise ValueError("invalid_response")
    return [_condition_base64(item) for item in items]


def _tx_facts(value: object) -> dict[str, object]:
    view = _view(value, _TX_KEYS)
    submitted = view["submitted"]
    if type(submitted) is not bool:
        raise ValueError("invalid_response")
    status = _choice(view["status"], {
        "acknowledged", "partial", "timeout", "disconnected", "failure", "not_submitted",
    })
    if submitted == (status == "not_submitted"):
        raise ValueError("invalid_response")
    if status in {"acknowledged", "partial"}:
        _counter(view["accepted_prefix_bytes"], minimum=1 if status == "acknowledged" else 0,
                 maximum=4096 if status == "acknowledged" else 4095)
    elif view["accepted_prefix_bytes"] is not None:
        raise ValueError("invalid_response")
    if status == "failure":
        _choice(view["failure_code"], _BACKEND_FAILURE_CODES)
    elif view["failure_code"] is not None:
        raise ValueError("invalid_response")
    _choice(view["acknowledgement_scope"], {"backend_acceptance"})
    _uuid(view["clock_origin_id"])
    _counter(view["settled_at_ns"])
    return view


def _tx_audit_failure(value: object) -> dict[str, object]:
    view = _view(value, ("source", "code"))
    source, code = _text(view["source"]), _text(view["code"])
    if ((source == "journal" and code in {c for _, c in _JOURNAL_ERRORS})
            or (source == "service" and code == "internal_failure")):
        return view
    raise ValueError("invalid_response")


def _interact_observation(value: object) -> dict[str, object]:
    view = _view(value, ("window", "outcome", "examined_rx_bytes", "observer_loss_records", "match", "clock"))
    window = _view(view["window"], ("start_inclusive", "end_exclusive"))
    start = _counter(window["start_inclusive"], minimum=1)
    end = _counter(window["end_exclusive"], minimum=start)
    outcome = _choice(view["outcome"], _INTERACT_OBSERVATION_OUTCOMES)
    examined = _counter(view["examined_rx_bytes"], maximum=1048576,
                        minimum=1 if outcome in {"matched", "byte_limit"} else 0)
    loss = _counter(view["observer_loss_records"])
    if start == end and (examined or loss):
        raise ValueError("invalid_response")
    match = None
    if outcome == "matched":
        match = _view(view["match"], ("condition_index", "start", "end"))
        _counter(match["condition_index"], maximum=3)
        first = _view(match["start"], ("sequence", "byte_offset"))
        last = _view(match["end"], ("sequence", "byte_offset_exclusive"))
        first_seq = _counter(first["sequence"], minimum=start, maximum=end - 1)
        _counter(last["sequence"], minimum=first_seq, maximum=end - 1)
        offset = _counter(first["byte_offset"], maximum=examined - 1)
        last_offset = _counter(last["byte_offset_exclusive"], minimum=1, maximum=examined)
        if first["sequence"] == last["sequence"] and last_offset <= offset:
            raise ValueError("invalid_response")
        match["start"], match["end"] = first, last
    elif view["match"] is not None:
        raise ValueError("invalid_response")
    clock = _operation_clock(view["clock"])
    started = _counter(clock["started_at_ns"])
    deadline = _counter(clock["deadline_at_ns"], minimum=started + 1)
    decided = _counter(clock["decided_at_ns"], minimum=started)
    duration = deadline - started
    if duration % 1000000 or not 1000000 <= duration <= 4000000000:
        raise ValueError("invalid_response")
    if (outcome == "timeout") != (decided >= deadline):
        raise ValueError("invalid_response")
    view.update(window=window, match=match, clock=clock)
    return view


def _interact_facts(
    start_sequence: int, tx: dict[str, object], observation: dict[str, object],
    outcome: object, *, end_sequence: int | None = None,
) -> str:
    """Validate declared wire relationships; never reproduce a Core decision."""
    overall = _choice(outcome, _INTERACT_OUTCOMES)
    window = cast(dict[str, object], observation["window"])
    clock = cast(dict[str, object], observation["clock"])
    if (window["start_inclusive"] != start_sequence + 1
            or (end_sequence is not None and _counter(window["end_exclusive"]) > end_sequence)
            or tx["clock_origin_id"] != clock["origin_id"]
            or _counter(tx["settled_at_ns"]) < _counter(clock["started_at_ns"])):
        raise ValueError("invalid_response")
    if tx["status"] == "acknowledged" and observation["outcome"] == "tx_failed":
        raise ValueError("invalid_response")
    if overall not in _INTERACT_EXTERNAL_OUTCOMES:
        expected = {"partial": "partial_write", "timeout": "write_timeout",
                    "disconnected": "disconnected", "failure": "transport_failure"}.get(_text(tx["status"]))
        if tx["status"] == "acknowledged":
            expected = _text(observation["outcome"])
        if not tx["submitted"] or overall != expected:
            raise ValueError("invalid_response")
    return overall


def _interact_started(value: object) -> dict[str, object]:
    view = _view(value, (
        "kind", "sequence", "operation_id", "provenance", "profile_version",
        "authorization", "conditions_base64", "timeout_ms", "max_rx_bytes",
        "write_timeout_ms", "clock_origin_id", "payload_base64",
    ))
    _counter(view["sequence"], maximum=_MAX - 1)
    _uuid(view["operation_id"])
    view["provenance"] = _provenance(view["provenance"])
    _counter(view["profile_version"], minimum=2, maximum=2)
    authorization = _view(view["authorization"], ("uart_tx_enabled",))
    if authorization["uart_tx_enabled"] is not True:
        raise ValueError("invalid_response")
    view["authorization"] = authorization
    view["conditions_base64"] = _conditions(view["conditions_base64"])
    _counter(view["timeout_ms"], minimum=1, maximum=4000)
    _counter(view["max_rx_bytes"], minimum=1, maximum=1048576)
    _counter(view["write_timeout_ms"], minimum=1000, maximum=1000)
    _uuid(view["clock_origin_id"])
    _payload_base64(view["payload_base64"])
    return view


def _uart_tx_settled(value: object) -> dict[str, object]:
    view = _view(value, ("kind", "sequence", "operation_id", "start_sequence", *_TX_KEYS))
    sequence = _counter(view["sequence"], maximum=_MAX - 1)
    _counter(view["start_sequence"], maximum=sequence - 1)
    _uuid(view["operation_id"])
    view.update(_tx_facts({key: view[key] for key in _TX_KEYS}))
    return view


def _interact_ended(value: object) -> dict[str, object]:
    view = _view(value, ("kind", "sequence", "operation_id", "start_sequence",
                         "tx_settled_sequence", "tx", "tx_audit_failure", "outcome", "observation"))
    sequence = _counter(view["sequence"], maximum=_MAX - 1)
    start = _counter(view["start_sequence"], maximum=sequence - 1)
    _uuid(view["operation_id"])
    if view["tx_settled_sequence"] is None:
        view["tx_audit_failure"] = _tx_audit_failure(view["tx_audit_failure"])
    elif view["tx_audit_failure"] is not None:
        raise ValueError("invalid_response")
    else:
        _counter(view["tx_settled_sequence"], minimum=start + 1, maximum=sequence - 1)
    tx = _tx_facts(view["tx"])
    observation = _interact_observation(view["observation"])
    _interact_facts(start, tx, observation, view["outcome"], end_sequence=sequence)
    view.update(tx=tx, observation=observation)
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


def reply(value: object, *, api_version: int = 1) -> dict[str, object]:
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
    page["records"] = [_record(record, api_version=api_version) for record in _array(page["records"])]
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
