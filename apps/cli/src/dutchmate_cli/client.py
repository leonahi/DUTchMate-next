"""One finite HTTP exchange; validate delivery data without reconstructing Core."""

import asyncio
import json
import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, NoReturn, cast

import httpx
import typer

from dutchmate_cli import annotation, evidence, interact, monitor
from dutchmate_cli import follow as follow_wire
from dutchmate_cli.context import AttachPaths, CliFailure, CliFailureKind, Endpoint

type RequestOutcome = Literal["not_submitted", "unknown", "report_received"]

_LIMIT = 1048576
_MEDIA = re.compile(
    r'application/json(?:[ \t]*;[ \t]*charset[ \t]*=[ \t]*(?:utf-8|"utf-8"))?',
    re.IGNORECASE,
)
_EXITS = {
    CliFailureKind.INVALID_ARGUMENTS: 2,
    CliFailureKind.UNSUPPORTED_PLATFORM: 3,
    CliFailureKind.CREDENTIAL_UNAVAILABLE: 3,
    CliFailureKind.UNSAFE_CREDENTIAL: 3,
    CliFailureKind.REQUEST_TIMEOUT: 5,
    CliFailureKind.TRANSPORT_FAILED: 5,
    CliFailureKind.INVALID_RESPONSE: 5,
    CliFailureKind.INTERRUPTED: 130,
    CliFailureKind.OUTPUT_FAILED: 1,
    CliFailureKind.INTERNAL_FAILURE: 1,
}
_PROFILE_CODES = {
    "missing_file", "not_a_file", "unreadable", "input_too_large", "invalid_syntax",
    "incompatible_version", "missing_field", "unknown_field", "invalid_value",
    "unsupported_backend", "unsupported_behavior",
}
_REQUEST_CODES = {
    400: {"host_rejected", "query_not_allowed", "upgrade_rejected"},
    403: {"peer_rejected", "origin_rejected"},
    401: {"authentication_required"}, 404: {"route_not_found"},
    405: {"method_not_allowed"}, 413: {"payload_too_large"},
    415: {"unsupported_media_type"}, 422: {"invalid_request"},
    409: {"unsupported_api_version"},
}
_ACQUISITION_CODES = {"capability_rejection", "recording_failure", "transport_failure"}
_ISSUE_CODES = _PROFILE_CODES | _ACQUISITION_CODES | {
    "invalid_request", "device_not_found", "permission_denied", "device_busy",
    "configuration_rejected", "line_state_setup_failed", "io_failure",
    "internal_contract_failure", "close_failed", "invalid_input", "journal_exists",
    "journal_missing", "session_mismatch", "incompatible_application",
    "incompatible_schema_version", "incompatible_record_version",
    "incompatible_provenance_envelope_version", "corrupt_journal", "invariant_violation",
    "busy", "capacity", "capacity/database_over_ceiling",
    "capacity/physical_ceiling_unavailable", "capacity/sequence_exhausted",
    "capacity/counter_exhausted", "read_only", "closed",
}


@dataclass(slots=True)
class DeliveryState:
    """Invocation-local receipt phase, independent of service admission/outcome."""

    request_outcome: RequestOutcome = "not_submitted"


def _invalid() -> NoReturn:
    raise CliFailure(CliFailureKind.INVALID_RESPONSE)


def _object(value: object, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        _invalid()
    return cast(dict[str, object], value)


def _array(value: object) -> list[object]:
    if type(value) is not list:
        _invalid()
    return cast(list[object], value)


def _string(value: object) -> None:
    if type(value) is not str:
        _invalid()


def _enum(value: object, choices: set[str]) -> None:
    if type(value) is not str or value not in choices:
        _invalid()


def _booleans(view: dict[str, object], keys: tuple[str, ...]) -> None:
    if any(type(view[key]) is not bool for key in keys):
        _invalid()


def _integers(view: dict[str, object], keys: tuple[str, ...]) -> None:
    if any(type(view[key]) is not int for key in keys):
        _invalid()


def _profile(value: object, *, api_version: int = 1) -> None:
    view = _object(value, {
        "format_version", "dut", "backend", "uart", "open_lines", "policy", "session_policy",
    })
    if type(view["format_version"]) is not int or view["format_version"] not in (
        {1, 2} if api_version == 2 else {1}
    ):
        _invalid()
    for field, keys in (("dut", {"id", "name"}), ("backend", {"kind", "expected_device"})):
        for item in _object(view[field], keys).values():
            _string(item)
    uart = _object(view["uart"], {
        "baud_rate", "data_bits", "parity", "stop_bits",
        "hardware_flow_control", "software_flow_control",
    })
    _integers(uart, ("baud_rate", "data_bits", "stop_bits"))
    _enum(uart["parity"], {"none", "even", "odd"})
    _booleans(uart, ("hardware_flow_control", "software_flow_control"))
    for item in _object(view["open_lines"], {"dtr", "rts"}).values():
        _enum(item, {"asserted", "deasserted", "driver_managed"})
    policy_keys = (
        "uart_rx_enabled", "evidence_recording_enabled", "uart_tx_enabled",
        "semantic_control_enabled", "automatic_reconnect_enabled",
    )
    _booleans(_object(view["policy"], set(policy_keys)), policy_keys)
    session_keys = (
        "max_retained_records", "max_retained_charged_bytes", "max_record_charged_bytes",
        "max_database_pages", "max_retrieval_page_records", "max_retrieval_page_charged_bytes",
    )
    _integers(_object(view["session_policy"], set(session_keys)), session_keys)


def _observation(value: object, *, provenance: bool = False) -> None:
    keys = {
        "capabilities", "backend_observation_timestamp_domain",
        "loss_observability", "connection_provenance",
    }
    if provenance:
        keys |= {"connection_id", "segment_id"}
    view = _object(value, keys)
    if provenance:
        _string(view["connection_id"])
        _string(view["segment_id"])
    for capability in _array(view["capabilities"]):
        _enum(capability, {"uart_receive", "uart_send", "serial_line_control", "gpio_control", "gpio_events"})
    domain = _object(view["backend_observation_timestamp_domain"], {
        "domain_id", "observer", "meaning", "unit", "origin_id",
    })
    _string(domain["domain_id"])
    _string(domain["origin_id"])
    _enum(domain["observer"], {"host", "device"})
    _enum(domain["meaning"], {"observation"})
    _enum(domain["unit"], {"nanosecond", "microsecond", "tick"})
    loss = view["loss_observability"]
    if type(loss) is not dict:
        _invalid()
    if loss.get("kind") == "upstream_loss_not_observable":
        _object(loss, {"kind"})
    elif loss.get("kind") == "observer_reports_uart_loss":
        loss_view = _object(loss, {"kind", "observer_id", "scope"})
        _string(loss_view["observer_id"])
        _string(loss_view["scope"])
    else:
        _invalid()
    envelope = _object(view["connection_provenance"], {
        "envelope_version", "backend_kind", "backend_schema_version", "fields",
    })
    if type(envelope["envelope_version"]) is not int or envelope["envelope_version"] != 1:
        _invalid()
    _string(envelope["backend_kind"])
    _integers(envelope, ("backend_schema_version",))
    for item in _array(envelope["fields"]):
        field = _object(item, {"name", "value"})
        _string(field["name"])
        if field["value"] is not None and type(field["value"]) not in {str, int, bool}:
            _invalid()


def _issue(value: object) -> None:
    view = _object(value, {"source", "code"})
    _enum(view["source"], {
        "preparation", "acquisition_start", "acquisition",
        "backend_close", "recorder_close", "internal_contract",
    })
    _enum(view["code"], _ISSUE_CODES)


def _acquisition(value: object) -> None:
    view = _object(value, {
        "state", "descriptor", "provenance", "terminal_trigger",
        "primary_failure_kind", "close_failed", "physical_release_confirmed",
    })
    _enum(view["state"], {"idle", "starting", "acquiring", "stopping", "stopped", "failed"})
    _booleans(view, ("close_failed", "physical_release_confirmed"))
    if view["descriptor"] is not None:
        _observation(view["descriptor"])
    if view["provenance"] is not None:
        _observation(view["provenance"], provenance=True)
    if view["terminal_trigger"] is not None:
        _enum(view["terminal_trigger"], _ACQUISITION_CODES | {"explicit_stop", "disconnected"})
    if view["primary_failure_kind"] is not None:
        _enum(view["primary_failure_kind"], _ACQUISITION_CODES)


def _status(value: object, *, api_version: int = 1) -> None:
    envelope = _object(value, {"service_state", "runtime"})
    _enum(envelope["service_state"], {"ready", "stopping"})
    view = _object(envelope["runtime"], {
        "state", "run_id", "profile", "session_id", "acquisition", "stop_intent",
        "terminal_reason", "primary_issue", "cleanup_issues", "owner_settled",
        "physical_release_confirmed", "recorder_close_confirmed", "attach_admissible",
    })
    _enum(view["state"], {"inactive", "attaching", "active", "detaching", "terminated", "failed"})
    _enum(view["stop_intent"], {"none", "detach", "attach_cancelled"})
    if view["terminal_reason"] is not None:
        _enum(view["terminal_reason"], {
            "detached", "attach_cancelled", "disconnected", "startup_failure",
            "acquisition_failure", "cleanup_failure",
        })
    for key in ("run_id", "session_id"):
        if view[key] is not None:
            _string(view[key])
    if view["profile"] is not None:
        _profile(view["profile"], api_version=api_version)
    if view["acquisition"] is not None:
        _acquisition(view["acquisition"])
    if view["primary_issue"] is not None:
        _issue(view["primary_issue"])
    issues = _array(view["cleanup_issues"])
    if len(issues) > 2:
        _invalid()
    for issue in issues:
        _issue(issue)
    _booleans(view, (
        "owner_settled", "physical_release_confirmed", "recorder_close_confirmed", "attach_admissible",
    ))


def _remote_error(value: object, status_code: int) -> None:
    envelope = _object(value, {"error"})
    error = _object(envelope["error"], {"source", "code"})
    source, code = error["source"], error["code"]
    _string(source)
    _string(code)
    valid = (
        (source == "request" and code in _REQUEST_CODES.get(status_code, set()))
        or (source == "profile" and status_code == 422 and code in _PROFILE_CODES)
        or (source == "runtime" and (status_code, code) in {
            (409, "busy"), (409, "cleanup_unconfirmed"), (422, "invalid_request"),
            (500, "wrong_execution_context"),
        })
        or (source == "service" and (status_code, code) in {
            (503, "stopping"), (503, "operation_capacity"), (500, "internal_failure"),
        })
    )
    if not valid:
        _invalid()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            _invalid()
        result[name] = value
    return result


def _nonfinite(value: str) -> NoReturn:
    _invalid()


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        _invalid()
    return result


def _decode(body: bytearray) -> object:
    try:
        return cast(object, json.loads(
            body.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_nonfinite, parse_float=_finite_float,
        ))
    except (UnicodeError, ValueError, RecursionError):
        pass
    _invalid()


def _encode_record(value: object) -> bytes:
    output = bytearray()
    try:
        encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        for part in encoder.iterencode(value):
            encoded = part.encode("utf-8")
            output.extend(encoded[: _LIMIT + 1 - len(output)])
            if len(output) > _LIMIT:
                _invalid()
        output.append(10)
        return bytes(output)
    except (UnicodeError, ValueError, RecursionError):
        pass
    _invalid()


def local_failure(kind: CliFailureKind, delivery: DeliveryState) -> tuple[int, bytes]:
    return _EXITS[kind], _encode_record({
        "error": {"source": "cli", "code": kind.value},
        "request_outcome": delivery.request_outcome,
    })


async def _raw(response: httpx.Response) -> bytearray:
    media = response.headers.get_list("content-type")
    encoding = response.headers.get_list("content-encoding")
    if len(media) != 1 or _MEDIA.fullmatch(media[0].strip()) is None:
        _invalid()
    if encoding and (len(encoding) != 1 or encoding[0].strip().lower() != "identity"):
        _invalid()
    body = bytearray()
    async for chunk in response.aiter_raw():
        body.extend(chunk[: _LIMIT + 1 - len(body)])
        if len(body) > _LIMIT:
            _invalid()
    return body


async def exchange(
    *, endpoint: Endpoint, command: str, credential: str, delivery: DeliveryState,
    paths: AttachPaths | None = None,
    api_version: int = 1,
) -> tuple[int, bytes]:
    """Deliver one existing observation request; no account/resources/terminal work."""
    _check_api_version(api_version)
    request_body: dict[str, str] | None = None
    if command == "attach" and paths is not None:
        method, route = "POST", "/v1/observation/attach" if api_version == 1 else "/v2/observation/attach"
        request_body = {"profile_path": paths.profile_path, "journal_path": paths.journal_path}
    elif command == "status" and paths is None:
        method, route = "GET", "/v1/observation/status" if api_version == 1 else "/v2/observation/status"
    elif command == "detach" and paths is None:
        method, route = "POST", "/v1/observation/detach" if api_version == 1 else "/v2/observation/detach"
    else:
        return local_failure(CliFailureKind.INVALID_ARGUMENTS, delivery)
    return await _deliver(
        endpoint=endpoint, method=method, route=route, request_body=request_body,
        credential=credential, delivery=delivery,
        validate=_status if api_version == 1 else lambda value: _status(value, api_version=2),
        reject=_remote_error,
    )


def _check_api_version(api_version: int) -> None:
    if type(api_version) is not int or api_version not in {1, 2}:
        raise CliFailure(CliFailureKind.INVALID_ARGUMENTS)


def _evidence_reply(value: object, *, api_version: int = 1) -> object:
    try:
        return evidence.reply(value) if api_version == 1 else evidence.reply(value, api_version=2)
    except ValueError, TypeError, RecursionError:
        pass
    _invalid()


def _evidence_error(value: object, status: int) -> object:
    try:
        if not evidence.recognized_error(value, status):
            _remote_error(value, status)
    except ValueError, TypeError, RecursionError:
        _invalid()
    envelope = cast(dict[str, object], value)
    error = cast(dict[str, object], envelope["error"])
    return {"error": {"source": error["source"], "code": error["code"]}}


async def exchange_evidence(
    *, endpoint: Endpoint, operation: str, request_body: dict[str, object],
    credential: str, delivery: DeliveryState,
    api_version: int = 1,
) -> tuple[int, bytes]:
    _check_api_version(api_version)
    if operation == "record":
        route = "/v1/evidence/record" if api_version == 1 else "/v2/evidence/record"
    elif operation == "page":
        route = "/v1/evidence/page" if api_version == 1 else "/v2/evidence/page"
    else:
        return local_failure(CliFailureKind.INVALID_ARGUMENTS, delivery)
    return await _deliver(
        endpoint=endpoint, method="POST", route=route, request_body=request_body,
        credential=credential, delivery=delivery,
        validate=_evidence_reply if api_version == 1 else lambda value: _evidence_reply(value, api_version=2),
        reject=_evidence_error,
    )


def _monitor_reply(value: object) -> object:
    try:
        return monitor.reply(value)
    except ValueError, TypeError, RecursionError:
        pass
    _invalid()


def _monitor_error(value: object, status: int) -> object:
    try:
        if not monitor.recognized_error(value, status):
            _remote_error(value, status)
    except ValueError, TypeError, RecursionError:
        _invalid()
    error = _object(_object(value, {"error"})["error"], {"source", "code"})
    return {"error": {"source": error["source"], "code": error["code"]}}


async def exchange_monitor(
    *,
    endpoint: Endpoint,
    request_body: dict[str, object],
    credential: str,
    delivery: DeliveryState,
    api_version: int = 1,
) -> tuple[int, bytes]:
    _check_api_version(api_version)
    return await _deliver(
        endpoint=endpoint,
        method="POST",
        route="/v1/observation/monitor" if api_version == 1 else "/v2/observation/monitor",
        request_body=request_body,
        credential=credential,
        delivery=delivery,
        validate=_monitor_reply,
        reject=_monitor_error,
    )


def _annotation_reply(value: object) -> object:
    try:
        return annotation.reply(value)
    except ValueError, TypeError, RecursionError:
        pass
    _invalid()


def _annotation_error(value: object, status: int) -> object:
    try:
        if not annotation.recognized_error(value, status):
            _remote_error(value, status)
    except ValueError, TypeError, RecursionError:
        _invalid()
    error = _object(_object(value, {"error"})["error"], {"source", "code"})
    return {"error": {"source": error["source"], "code": error["code"]}}


async def exchange_annotation(
    *,
    endpoint: Endpoint,
    request_body: dict[str, object],
    credential: str,
    delivery: DeliveryState,
    api_version: int = 1,
) -> tuple[int, bytes]:
    _check_api_version(api_version)
    return await _deliver(
        endpoint=endpoint,
        method="POST",
        route="/v1/observation/annotations" if api_version == 1 else "/v2/observation/annotations",
        request_body=request_body,
        credential=credential,
        delivery=delivery,
        validate=_annotation_reply,
        reject=_annotation_error,
    )


async def exchange_interact(
    *, endpoint: Endpoint, request_body: dict[str, object], credential: str,
    delivery: DeliveryState,
) -> tuple[int, bytes]:
    def validate(value: object) -> object:
        try:
            return interact.reply(value, request_body)
        except ValueError, TypeError, RecursionError:
            _invalid()

    def reject(value: object, status: int) -> object:
        try:
            if not interact.recognized_error(value, status):
                _remote_error(value, status)
        except ValueError, TypeError, RecursionError:
            _invalid()
        error = _object(_object(value, {"error"})["error"], {"source", "code"})
        return {"error": {"source": error["source"], "code": error["code"]}}

    return await _deliver(
        endpoint=endpoint, method="POST", route="/v2/observation/interact",
        request_body=request_body, credential=credential, delivery=delivery,
        validate=validate, reject=reject,
    )


def _follow_frame(position: follow_wire.Position, raw: bytearray | None) -> bytes:
    if raw is None:
        _invalid()
    try:
        value = position.accept(_decode(raw))
        return _encode_record(value)
    except ValueError, TypeError, RecursionError:
        pass
    _invalid()


async def exchange_follow(
    *, endpoint: Endpoint, request_body: dict[str, object], credential: str,
    delivery: DeliveryState, emit: Callable[[bytes], None],
    api_version: int = 1,
) -> tuple[int, bytes | None]:
    """One Follow HTTP exchange; finite delivery below retains its old budgets."""
    _check_api_version(api_version)
    route = "/v1/observation/follow" if api_version == 1 else "/v2/observation/follow"
    for name in (
        "httpx", "httpcore", "httpcore.connection", "httpcore.http11",
        "httpcore.http2", "httpcore.proxy", "httpcore.socks",
    ):
        logger = logging.getLogger(name)
        logger.disabled = True
        logger.propagate = False
    authority = (
        f"[::1]:{endpoint.port}" if endpoint.host == "::1"
        else f"127.0.0.1:{endpoint.port}"
    )
    try:
        limits = httpx.Limits(max_connections=1, max_keepalive_connections=0)
        transport = httpx.AsyncHTTPTransport(
            trust_env=False, http1=True, http2=False, retries=0, proxy=None, limits=limits,
        )
        async with httpx.AsyncClient(
            transport=transport, trust_env=False, follow_redirects=False,
            http1=True, http2=False, proxy=None, limits=limits,
            timeout=httpx.Timeout(5.0, connect=5.0, read=5.0, write=5.0, pool=5.0),
        ) as client:
            delivery.request_outcome = "unknown"
            loop = asyncio.get_running_loop()
            async with asyncio.timeout_at(loop.time() + 10) as handshake:
                async with client.stream(
                    "POST", f"http://{authority}{route}", json=request_body,
                    headers={
                        "Host": authority, "Authorization": f"Bearer {credential}",
                        "Accept": "application/x-ndjson", "Accept-Encoding": "identity",
                    },
                ) as response:
                    if response.status_code != 200:
                        value = _decode(await _raw(response))
                        try:
                            if not follow_wire.recognized_error(value, response.status_code):
                                _remote_error(value, response.status_code)
                        except ValueError, TypeError, RecursionError:
                            _invalid()
                        record = _encode_record(value)
                        delivery.request_outcome = "report_received"
                        return 4, record
                    media = response.headers.get_list("content-type")
                    encoding = response.headers.get_list("content-encoding")
                    transfer = response.headers.get_list("transfer-encoding")
                    if (
                        len(media) != 1 or follow_wire._MEDIA.fullmatch(media[0].strip()) is None
                        or (encoding and (len(encoding) != 1 or encoding[0].strip().lower() != "identity"))
                        or response.headers.get_list("content-length")
                        or (transfer and (len(transfer) != 1 or transfer[0].strip().lower() != "chunked"))
                    ):
                        _invalid()
                    frames = follow_wire.Frames(response.aiter_raw())
                    position = follow_wire.Position(
                        evidence._text(request_body["session_id"]), api_version=api_version,
                    )
                    first = _follow_frame(position, await frames.read())
                    # The first complete started frame ends the handshake. All
                    # later budgets start after the previous frame's output.
                    handshake.reschedule(None)
                    emit(first)
                    del first
                    while True:
                        async with asyncio.timeout_at(loop.time() + 5):
                            record = _follow_frame(position, await frames.read())
                            if position.terminal:
                                emit(record)
                                del record
                                try:
                                    await frames.require_eof()
                                except ValueError:
                                    _invalid()
                                delivery.request_outcome = "report_received"
                                return 0, None
                        emit(record)
                        del record
    except CliFailure as error:
        kind = error.kind
    except (TimeoutError, httpx.TimeoutException):
        kind = CliFailureKind.REQUEST_TIMEOUT
    except (httpx.ProtocolError, httpx.DecodingError, ValueError):
        kind = CliFailureKind.INVALID_RESPONSE
    except httpx.TransportError:
        kind = CliFailureKind.TRANSPORT_FAILED
    # The console normalizes unexpected exceptions and public interrupt forms;
    # context managers have already closed this HTTP subscriber before it does.
    return local_failure(kind, delivery)


async def _deliver(
    *, endpoint: Endpoint, method: str, route: str,
    request_body: dict[str, str] | dict[str, object] | None,
    credential: str, delivery: DeliveryState,
    validate: Callable[[object], object], reject: Callable[[object, int], object],
) -> tuple[int, bytes]:
    """Shared private007 transport; only reply validation varies by workflow."""
    # Parent.disabled does not suppress child records or handlers attached to
    # the parent. Disable the pinned SDK's emitting channels themselves too.
    for name in (
        "httpx", "httpcore", "httpcore.connection", "httpcore.http11",
        "httpcore.http2", "httpcore.proxy", "httpcore.socks",
    ):
        logger = logging.getLogger(name)
        logger.disabled = True
        logger.propagate = False
    authority = (
        f"[::1]:{endpoint.port}" if endpoint.host == "::1"
        else f"127.0.0.1:{endpoint.port}"
    )
    try:
        limits = httpx.Limits(max_connections=1, max_keepalive_connections=0)
        transport = httpx.AsyncHTTPTransport(
            trust_env=False, http1=True, http2=False, retries=0, proxy=None, limits=limits,
        )
        async with httpx.AsyncClient(
            transport=transport, trust_env=False, follow_redirects=False,
            http1=True, http2=False, proxy=None, limits=limits,
            timeout=httpx.Timeout(5.0, connect=5.0, read=5.0, write=5.0, pool=5.0),
        ) as client:
            delivery.request_outcome = "unknown"
            async with asyncio.timeout_at(asyncio.get_running_loop().time() + 10.0):
                async with client.stream(
                    method, f"http://{authority}{route}", json=request_body,
                    headers={
                        "Host": authority, "Authorization": f"Bearer {credential}",
                        "Accept": "application/json", "Accept-Encoding": "identity",
                    },
                ) as response:
                    body = await _raw(response)
                    status_code = response.status_code
        value = _decode(body)
        if status_code == 200:
            projected = validate(value)
            if projected is not None:
                value = projected
            exit_code = 0
        else:
            projected = reject(value, status_code)
            if projected is not None:
                value = projected
            exit_code = 4
        delivery.request_outcome = "report_received"
        return exit_code, _encode_record(value)
    except CliFailure as error:
        kind = error.kind
    except (TimeoutError, httpx.TimeoutException):
        kind = CliFailureKind.REQUEST_TIMEOUT
    except (httpx.ProtocolError, httpx.DecodingError):
        kind = CliFailureKind.INVALID_RESPONSE
    except httpx.TransportError:
        kind = CliFailureKind.TRANSPORT_FAILED
    except (KeyboardInterrupt, typer.Abort):
        raise
    except Exception:
        kind = CliFailureKind.INTERNAL_FAILURE
    return local_failure(kind, delivery)
