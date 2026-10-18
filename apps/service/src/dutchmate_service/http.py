"""Pure ASGI access gate and bounded observation wire values.

No app, runtime owner, listener, request-operation registry or DUT resource is
constructed here. The later delivery composition supplies the downstream app.
"""

import ipaddress
import json
import re
import secrets
from collections.abc import Callable, Iterator
from enum import Enum
from pathlib import PurePosixPath
from typing import NoReturn

from dutchmate_core.acquisition import AcquisitionSnapshot
from dutchmate_core.model import (
    ConnectionDescriptor,
    ObserverReportsUartLoss,
    SegmentProvenance,
    UpstreamLossNotObservable,
)
from dutchmate_core.profile import (
    ProfileFailure,
    ProfileFailureKind,
    ResolvedDutProfile,
)
from dutchmate_core.runtime import (
    RuntimeIssue,
    RuntimeRejectedError,
    RuntimeRejectedKind,
    RuntimeStatus,
)
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from dutchmate_service.bootstrap import ServiceConfig

_BODY_LIMIT = 16384
_RESPONSE_LIMIT = 1048576
_ROUTES = {
    b"/v1/observation/attach": "POST",
    b"/v1/observation/status": "GET",
    b"/v1/observation/detach": "POST",
    b"/v1/observation/monitor": "POST",
    b"/v1/observation/annotations": "POST",
    b"/v1/observation/follow": "POST",
    b"/v1/evidence/record": "POST",
    b"/v1/evidence/page": "POST",
}
_BEARER = re.compile(rb"Bearer [0-9a-f]{64}")
_TOKEN = re.compile(r"[0-9a-f]{64}")
_MEDIA = re.compile(
    r'application/json(?:[ \t]*;[ \t]*charset[ \t]*=[ \t]*(?:utf-8|"utf-8"))?',
    re.IGNORECASE,
)
_REQUEST_CODES = {
    400: {"host_rejected", "query_not_allowed", "upgrade_rejected"},
    403: {"peer_rejected", "origin_rejected"},
    401: {"authentication_required"},
    404: {"route_not_found"},
    405: {"method_not_allowed"},
    413: {"payload_too_large"},
    415: {"unsupported_media_type"},
    422: {"invalid_request"},
}
_RUNTIME_CODES = {
    RuntimeRejectedKind.BUSY: 409,
    RuntimeRejectedKind.CLEANUP_UNCONFIRMED: 409,
    RuntimeRejectedKind.INVALID_REQUEST: 422,
    RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT: 500,
}


def error_response(status_code: int, source: str, code: str) -> Response:
    """Render only the contract's fixed categories, never arbitrary diagnostics."""
    valid = (
        type(status_code) is int
        and type(source) is str
        and type(code) is str
        and (
            (source == "request" and code in _REQUEST_CODES.get(status_code, set()))
            or (
                source == "profile"
                and status_code == 422
                and code in {kind.value for kind in ProfileFailureKind}
            )
            or (
                source == "runtime"
                and any(
                    code == kind.value and status_code == number
                    for kind, number in _RUNTIME_CODES.items()
                )
            )
            or (
                source == "service"
                and (status_code, code)
                in {
                    (500, "internal_failure"),
                    (503, "stopping"),
                    (503, "operation_capacity"),
                }
            )
        )
    )
    if not valid:
        status_code, source, code = 500, "service", "internal_failure"
    headers = {"Cache-Control": "no-store"}
    if status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    body = json.dumps(
        {"error": {"source": source, "code": code}},
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return Response(
        body, status_code=status_code, media_type="application/json", headers=headers
    )


def rejection_response(error: Exception) -> Response:
    """Map existing normalized rejection facts without reading cause/detail."""
    if isinstance(error, RuntimeRejectedError):
        return error_response(_RUNTIME_CODES[error.kind], "runtime", error.kind.value)
    if isinstance(error, ProfileFailure):
        return error_response(422, "profile", error.kind.value)
    return error_response(500, "service", "internal_failure")


class _EncodingLimit(ValueError):
    pass


def _encode_bounded(value: object) -> bytes:
    """Encode projected JSON primitives, retaining at most limit+1 bytes.

    Strings are escaped one scalar at a time, so a huge field is never encoded
    or copied in full before overflow is detected. Iterators below are private
    projected arrays, not arbitrary backend/task serialization.
    """
    output = bytearray()

    def add(part: bytes) -> None:
        output.extend(part[: _RESPONSE_LIMIT + 1 - len(output)])
        if len(output) > _RESPONSE_LIMIT:
            raise _EncodingLimit()

    def text(item: str) -> None:
        add(b'"')
        for char in item:
            if char == '"':
                add(b'\\"')
            elif char == "\\":
                add(b"\\\\")
            elif ord(char) < 32:
                add(f"\\u{ord(char):04x}".encode("ascii"))
            else:
                add(char.encode("utf-8"))
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
                if not isinstance(key, str):
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


def _profile_view(profile: ResolvedDutProfile) -> dict[str, object]:
    return {
        "format_version": profile.format_version.value,
        "dut": {"id": profile.dut.id, "name": profile.dut.name},
        "backend": {
            "kind": profile.backend.kind,
            "expected_device": profile.backend.expected_device,
        },
        "uart": {
            name: getattr(profile.uart, name)
            for name in (
                "baud_rate",
                "data_bits",
                "parity",
                "stop_bits",
                "hardware_flow_control",
                "software_flow_control",
            )
        },
        "open_lines": {"dtr": profile.open_lines.dtr, "rts": profile.open_lines.rts},
        "policy": {
            name: getattr(profile.policy, name)
            for name in (
                "uart_rx_enabled",
                "evidence_recording_enabled",
                "uart_tx_enabled",
                "semantic_control_enabled",
                "automatic_reconnect_enabled",
            )
        },
        "session_policy": {
            name: getattr(profile.session_policy, name)
            for name in (
                "max_retained_records",
                "max_retained_charged_bytes",
                "max_record_charged_bytes",
                "max_database_pages",
                "max_retrieval_page_records",
                "max_retrieval_page_charged_bytes",
            )
        },
    }


def _observation_view(
    value: ConnectionDescriptor | SegmentProvenance,
) -> dict[str, object]:
    domain = value.backend_observation_timestamp_domain
    loss = value.loss_observability
    if isinstance(loss, UpstreamLossNotObservable):
        loss_view: dict[str, object] = {"kind": "upstream_loss_not_observable"}
    elif isinstance(loss, ObserverReportsUartLoss):
        loss_view = {
            "kind": "observer_reports_uart_loss",
            "observer_id": loss.observer_id,
            "scope": loss.scope,
        }
    else:
        raise TypeError("unknown normalized loss variant")
    envelope = value.connection_provenance.to_snapshot()
    return {
        "capabilities": sorted(
            capability.value for capability in value.capabilities.values
        ),
        "backend_observation_timestamp_domain": {
            "domain_id": domain.domain_id,
            "observer": domain.observer.value,
            "meaning": domain.meaning.value,
            "unit": domain.unit.value,
            "origin_id": domain.origin_id,
        },
        "loss_observability": loss_view,
        "connection_provenance": {
            "envelope_version": envelope.envelope_version,
            "backend_kind": envelope.backend_kind,
            "backend_schema_version": envelope.backend_schema_version,
            "fields": (
                {"name": field.name, "value": field.value} for field in envelope.fields
            ),
        },
    }


def _acquisition_view(value: AcquisitionSnapshot) -> dict[str, object]:
    provenance = None
    if value.provenance is not None:
        provenance = _observation_view(value.provenance)
        provenance["connection_id"] = value.provenance.connection_id.value
        provenance["segment_id"] = value.provenance.segment_id.value
    return {
        "state": value.state.value,
        "descriptor": None
        if value.descriptor is None
        else _observation_view(value.descriptor),
        "provenance": provenance,
        "terminal_trigger": None
        if value.terminal_trigger is None
        else value.terminal_trigger.value,
        "primary_failure_kind": None
        if value.primary_failure_kind is None
        else value.primary_failure_kind.value,
        "close_failed": value.close_failed,
        "physical_release_confirmed": value.physical_release_confirmed,
    }


def _issue_view(issue: RuntimeIssue) -> dict[str, str]:
    return {
        "source": issue.source.value,
        "code": issue.code.value if isinstance(issue.code, Enum) else issue.code,
    }


def status_response(status: RuntimeStatus, *, service_state: str = "ready") -> Response:
    """Project immutable current/last facts, including failed status, as HTTP200."""
    try:
        if service_state not in {"ready", "stopping"}:
            raise ValueError("unserved service phase")
        body = _encode_bounded(
            {
                "service_state": service_state,
                "runtime": {
                    "state": status.state.value,
                    "run_id": None if status.run_id is None else status.run_id.value,
                    "profile": None
                    if status.profile is None
                    else _profile_view(status.profile),
                    "session_id": None
                    if status.session_id is None
                    else status.session_id.value,
                    "acquisition": None
                    if status.acquisition is None
                    else _acquisition_view(status.acquisition),
                    "stop_intent": status.stop_intent.value,
                    "terminal_reason": None
                    if status.terminal_reason is None
                    else status.terminal_reason.value,
                    "primary_issue": None
                    if status.primary_issue is None
                    else _issue_view(status.primary_issue),
                    "cleanup_issues": [
                        _issue_view(issue) for issue in status.cleanup_issues
                    ],
                    "owner_settled": status.owner_settled,
                    "physical_release_confirmed": status.physical_release_confirmed,
                    "recorder_close_confirmed": status.recorder_close_confirmed,
                    "attach_admissible": status.attach_admissible,
                },
            }
        )
    except Exception:
        return error_response(500, "service", "internal_failure")
    return Response(
        body, media_type="application/json", headers={"Cache-Control": "no-store"}
    )


def _header_values(scope: Scope, name: bytes) -> list[bytes]:
    return [value for key, value in scope.get("headers", []) if key.lower() == name]


def _route_error(scope: Scope) -> Response | None:
    raw = scope.get("raw_path")
    if not isinstance(raw, bytes):
        return error_response(404, "request", "route_not_found")
    method = _ROUTES.get(raw)
    if method is None or scope.get("path") != raw.decode("ascii"):
        return error_response(404, "request", "route_not_found")
    if scope.get("method") != method:
        return error_response(405, "request", "method_not_allowed")
    return None


class _Disconnected(Exception):
    """No response/admission is promised after an observed delivery disconnect."""


async def _read_body(receive: Receive, *, zero: bool) -> bytes | Response:
    data = bytearray()
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            raise _Disconnected()
        if (
            message["type"] != "http.request"
            or type(message.get("body", b"")) is not bytes
        ):
            return error_response(422, "request", "invalid_request")
        chunk = message.get("body", b"")
        if zero and chunk:
            return error_response(422, "request", "invalid_request")
        data.extend(chunk[: _BODY_LIMIT + 1 - len(data)])
        if len(data) > _BODY_LIMIT:
            return error_response(413, "request", "payload_too_large")
        if not message.get("more_body", False):
            return bytes(data)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("invalid_request")
        result[name] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise ValueError("invalid_request")


def _path(value: object) -> bool:
    return (
        type(value) is str
        and "\x00" not in value
        and 1 <= len(value.encode("utf-8")) <= 4096
        and PurePosixPath(value).is_absolute()
    )


async def validate_request(
    scope: Scope,
    receive: Receive,
) -> tuple[str, str] | Response | None:
    """Validate only wire input; never resolve/open Profile or run resources."""
    route_error = _route_error(scope)
    if route_error is not None:
        return route_error
    attach = scope["raw_path"] == b"/v1/observation/attach"
    if attach:
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
    body = await _read_body(receive, zero=not attach)
    if isinstance(body, Response):
        return body
    if not attach:
        return None
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
        if type(value) is not dict or set(value) != {"profile_path", "journal_path"}:
            raise ValueError("invalid_request")
        profile, journal = value["profile_path"], value["journal_path"]
        if not _path(profile) or not _path(journal):
            raise ValueError("invalid_request")
    except ValueError, TypeError, RecursionError:
        return error_response(422, "request", "invalid_request")
    return profile, journal


class _DeliveryFailure(RuntimeError):
    """Fixed transport diagnostic without the original exception or request."""


class SecurityGate:
    """Outer pure ASGI gate: raw security first, bounded validation afterward."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        config: ServiceConfig,
        credential: Callable[[], str | None],
    ) -> None:
        self._app = app
        self._config = config
        self._credential = credential
        host = "[::1]" if config.host == "::1" else "127.0.0.1"
        self._authority = f"{host}:{config.port}".encode("ascii")
        self._family = 6 if config.host == "::1" else 4

    def _security_error(self, scope: Scope) -> Response | None:
        client = scope.get("client")
        try:
            if not isinstance(client, tuple) or not isinstance(client[0], str):
                raise ValueError("missing peer")
            peer = ipaddress.ip_address(client[0])
            allowed_peer = (
                peer.is_loopback
                and peer.version == self._family
                and not (
                    isinstance(peer, ipaddress.IPv6Address)
                    and peer.ipv4_mapped is not None
                )
            )
        except ValueError, TypeError, IndexError:
            allowed_peer = False
        if not allowed_peer:
            return error_response(403, "request", "peer_rejected")
        if _header_values(scope, b"host") != [self._authority]:
            return error_response(400, "request", "host_rejected")
        if any(
            name.lower() == b"origin" or name.lower().startswith(b"sec-fetch-")
            for name, _ in scope.get("headers", [])
        ):
            return error_response(403, "request", "origin_rejected")
        authorization = _header_values(scope, b"authorization")
        if len(authorization) != 1 or _BEARER.fullmatch(authorization[0]) is None:
            return error_response(401, "request", "authentication_required")
        current = self._credential()
        if (
            current is None
            or _TOKEN.fullmatch(current) is None
            or not secrets.compare_digest(authorization[0][7:], current.encode("ascii"))
        ):
            return error_response(401, "request", "authentication_required")
        if scope.get("query_string", b""):
            return error_response(400, "request", "query_not_allowed")
        if _header_values(scope, b"upgrade"):
            return error_response(400, "request", "upgrade_rejected")
        return _route_error(scope)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        started = False

        async def safe_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message = {
                    **message,
                    "headers": [
                        (key, value)
                        for key, value in message.get("headers", [])
                        if key.lower() != b"cache-control"
                    ]
                    + [(b"cache-control", b"no-store")],
                }
            await send(message)

        try:
            error = self._security_error(scope)
            if error is not None:
                await error(scope, receive, safe_send)
                return
            if scope["raw_path"] in {
                b"/v1/evidence/record",
                b"/v1/evidence/page",
                b"/v1/observation/monitor",
                b"/v1/observation/annotations",
                b"/v1/observation/follow",
            }:
                # Reads/Monitor/annotations/Follow check readiness before body validation. The
                # existing observation validation/replay path stays unchanged.
                await self._app(scope, receive, safe_send)
                return
            captured = bytearray()

            async def capture_receive() -> Message:
                message = await receive()
                if (
                    message["type"] == "http.request"
                    and type(message.get("body", b"")) is bytes
                ):
                    captured.extend(
                        message.get("body", b"")[: _BODY_LIMIT + 1 - len(captured)]
                    )
                return message

            result = await validate_request(scope, capture_receive)
            if isinstance(result, Response):
                await result(scope, receive, safe_send)
                return
            replayed = False

            async def replay_receive() -> Message:
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {
                        "type": "http.request",
                        "body": bytes(captured),
                        "more_body": False,
                    }
                return await receive()

            await self._app(scope, replay_receive, safe_send)
            return
        except _Disconnected:
            return
        except Exception as error:
            if not started:
                await rejection_response(error)(scope, receive, safe_send)
                return
        # HTTP headers cannot be replaced after sending starts. Fail delivery with
        # a fresh fixed exception, raised outside handlers to drop raw context.
        raise _DeliveryFailure("service/internal_failure")
