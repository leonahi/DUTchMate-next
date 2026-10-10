"""T007–T016: bounded delivery, native status/limits and admitted-work lifetime.

Pure wire cases use test-owned HTTPX transport/streams and literal independent
reports. T010 native cases use an independently guarded 006 service child and
temporary credentials. No DUT or Profile/lifecycle predicates are introduced.

The private T008 calling seam is exchange(endpoint, command, credential,
delivery=DeliveryState()) -> (exit_code, encoded_record), plus local_failure(kind,
delivery) for fixed diagnostics. It is an internal test seam, not a public CLI/API
contract or a new client/DTO framework. Only the external wire assertions govern.
T016 adds real-clock loopback limits and guarded ASGI mutation-loss cases;
installed-process output/SIGINT acceptance remains in later tasks.
"""

import asyncio
import copy
import errno
import importlib
import importlib.util
import inspect
import io
import json
import logging
import socket
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import pytest_asyncio

from dutchmate_cli.context import AttachPaths, CliFailureKind, Endpoint

_TOKEN = "0123456789abcdef" * 4  # Test-only, never a real account credential.
_PRIVATE = "private-response-exception-header-sentinel"
_LIMIT = 1048576
_STATES = ["inactive", "attaching", "active", "detaching", "terminated", "failed"]
_REMOTE_ERRORS = [
    (400, "request", "host_rejected"), (400, "request", "query_not_allowed"),
    (400, "request", "upgrade_rejected"), (403, "request", "peer_rejected"),
    (403, "request", "origin_rejected"), (401, "request", "authentication_required"),
    (404, "request", "route_not_found"), (405, "request", "method_not_allowed"),
    (413, "request", "payload_too_large"), (415, "request", "unsupported_media_type"),
    (422, "request", "invalid_request"),
    *[(422, "profile", code) for code in [
        "missing_file", "not_a_file", "unreadable", "input_too_large", "invalid_syntax",
        "incompatible_version", "missing_field", "unknown_field", "invalid_value",
        "unsupported_backend", "unsupported_behavior",
    ]],
    (409, "runtime", "busy"), (409, "runtime", "cleanup_unconfirmed"),
    (422, "runtime", "invalid_request"), (500, "runtime", "wrong_execution_context"),
    (503, "service", "stopping"), (503, "service", "operation_capacity"),
    (500, "service", "internal_failure"),
]


def _api() -> Any:
    try:
        return importlib.import_module("dutchmate_cli.client")
    except ModuleNotFoundError as error:
        if error.name == "dutchmate_cli.client":
            pytest.fail("T008 HTTP exchange implementation is absent", pytrace=False)
        raise


def _report(state: str = "active", *, device: bool = False) -> dict[str, Any]:
    observation = {
        "capabilities": ["gpio_control", "uart_receive"] if device else ["uart_receive"],
        "backend_observation_timestamp_domain": {
            "domain_id": "device-domain" if device else "host-domain",
            "observer": "device" if device else "host", "meaning": "observation",
            "unit": "tick" if device else "nanosecond", "origin_id": "origin-1",
        },
        "loss_observability": {
            "kind": "observer_reports_uart_loss", "observer_id": "observer-1",
            "scope": "receive-fifo",
        } if device else {"kind": "upstream_loss_not_observable"},
        "connection_provenance": {
            "envelope_version": 1, "backend_kind": "opaque-vendor",
            "backend_schema_version": 37,
            "fields": [
                {"name": "z_null", "value": None}, {"name": "a_bool", "value": True},
                {"name": "n_int", "value": 7}, {"name": "text", "value": "opaque-é\x00"},
            ],
        },
    }
    profile = {
        "format_version": 1, "dut": {"id": "fixture/board", "name": "Board α"},
        "backend": {"kind": "basic_serial", "expected_device": "fixture-explicit-device"},
        "uart": {
            "baud_rate": 57600, "data_bits": 7, "parity": "even", "stop_bits": 2,
            "hardware_flow_control": True, "software_flow_control": False,
        },
        "open_lines": {"dtr": "deasserted", "rts": "driver_managed"},
        "policy": {
            "uart_rx_enabled": True, "evidence_recording_enabled": True,
            "uart_tx_enabled": False, "semantic_control_enabled": False,
            "automatic_reconnect_enabled": False,
        },
        "session_policy": {
            "max_retained_records": 100, "max_retained_charged_bytes": 65536,
            "max_record_charged_bytes": 8192, "max_database_pages": 128,
            "max_retrieval_page_records": 11, "max_retrieval_page_charged_bytes": 16384,
        },
    }
    terminal = state in {"terminated", "failed"}
    runtime: dict[str, Any] = {
        "state": state, "run_id": "run-1", "profile": profile, "session_id": "session-1",
        "acquisition": {
            "state": "failed" if state == "failed" else "stopped" if terminal else "acquiring",
            "descriptor": observation,
            "provenance": {**copy.deepcopy(observation), "connection_id": "connection-1",
                           "segment_id": "segment-1"},
            "terminal_trigger": "disconnected" if terminal else None,
            "primary_failure_kind": "transport_failure" if state == "failed" else None,
            "close_failed": state == "failed", "physical_release_confirmed": terminal,
        },
        "stop_intent": "detach" if state == "detaching" else "none",
        "terminal_reason": "acquisition_failure" if state == "failed" else
                           "disconnected" if terminal else None,
        "primary_issue": {"source": "acquisition", "code": "transport_failure"}
                         if state == "failed" else None,
        "cleanup_issues": [{"source": "backend_close", "code": "close_failed"}]
                          if state == "failed" else [],
        "owner_settled": terminal, "physical_release_confirmed": terminal,
        "recorder_close_confirmed": terminal, "attach_admissible": terminal,
    }
    if state == "inactive":
        runtime.update(
            run_id=None, profile=None, session_id=None, acquisition=None,
            owner_settled=True, physical_release_confirmed=True,
            recorder_close_confirmed=True, attach_admissible=True,
        )
    return {"service_state": "ready", "runtime": runtime}


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


class _Stream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], failure: Exception | None = None) -> None:
        self.chunks, self.failure = chunks, failure
        self.yielded = 0
        self.closed = False
        self.on_chunk: Callable[[], None] | None = None

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            if self.on_chunk is not None:
                self.on_chunk()
            self.yielded += 1
            yield chunk
            await asyncio.sleep(0)
        if self.failure is not None:
            raise self.failure

    async def aclose(self) -> None:
        self.closed = True


class _Transport(httpx.AsyncBaseTransport):
    def __init__(self, wire: _Wire) -> None:
        self.wire = wire
        self.closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.wire.requests.append(request)
        if self.wire.on_request is not None:
            self.wire.on_request(request)
        if self.wire.failure is not None:
            raise self.wire.failure
        return httpx.Response(self.wire.status, headers=self.wire.headers,
                              stream=self.wire.stream, request=request)

    async def aclose(self) -> None:
        self.closed = True


class _Wire:
    """Substitute only the external transport; keep the actual HTTPX client."""

    def __init__(
        self, api: Any, patch: pytest.MonkeyPatch, body: bytes | None = None, *,
        status: int = 200, headers: list[tuple[str, str]] | None = None,
        chunks: list[bytes] | None = None, failure: Exception | None = None,
        stream_failure: Exception | None = None,
    ) -> None:
        self.status = status
        self.headers = [("Content-Type", "application/json")] if headers is None else headers
        self.stream = _Stream(chunks if chunks is not None else
                              [_json(_report()) if body is None else body], stream_failure)
        self.failure = failure
        self.requests: list[httpx.Request] = []
        self.transports: list[_Transport] = []
        self.transport_options: list[dict[str, Any]] = []
        self.client_options: list[dict[str, Any]] = []
        self.on_request: Callable[[httpx.Request], None] | None = None
        original_client = httpx.AsyncClient
        client_signature = inspect.signature(original_client)
        transport_signature = inspect.signature(httpx.AsyncHTTPTransport)

        def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
            bound = client_signature.bind(*args, **kwargs)
            bound.apply_defaults()
            self.client_options.append(dict(bound.arguments))
            return original_client(*args, **kwargs)

        def transport(*args: Any, **kwargs: Any) -> _Transport:
            bound = transport_signature.bind(*args, **kwargs)
            bound.apply_defaults()
            self.transport_options.append(dict(bound.arguments))
            value = _Transport(self)
            self.transports.append(value)
            return value

        patch.setattr(httpx, "AsyncClient", client)
        patch.setattr(httpx, "AsyncHTTPTransport", transport)
        # Support ordinary public SDK aliases without a production test port.
        if hasattr(api, "AsyncClient"):
            patch.setattr(api, "AsyncClient", client)
        if hasattr(api, "AsyncHTTPTransport"):
            patch.setattr(api, "AsyncHTTPTransport", transport)

        def forbidden(*args: Any, **kwargs: Any) -> Any:
            pytest.fail("T007 must not resolve or connect a real network target")

        patch.setattr(socket, "getaddrinfo", forbidden)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(socket.socket, "connect_ex", forbidden)

        def buffered(*args: Any, **kwargs: Any) -> Any:
            pytest.fail("exchange must stream raw bytes without whole-response buffering")

        for method in ("read", "aread", "json"):
            patch.setattr(httpx.Response, method, buffered)
        for attribute in ("text", "content"):
            patch.setattr(httpx.Response, attribute, property(buffered))


async def _status(
    api: Any, *, host: str = "127.0.0.1", port: int = 80, delivery: Any = None,
) -> tuple[int, bytes, Any]:
    if delivery is None:
        delivery = api.DeliveryState()
    assert delivery.request_outcome == "not_submitted"
    result = await api.exchange(endpoint=Endpoint(port=port, host=host), command="status",
                                credential=_TOKEN, delivery=delivery)
    code, record = cast(tuple[int, bytes], result)
    assert type(code) is int and type(record) is bytes
    return code, record, delivery


def _local(code: int, record: bytes, kind: str, *, phase: str = "unknown") -> None:
    assert code == 5
    _record(record, {"error": {"source": "cli", "code": kind}, "request_outcome": phase})
    assert _PRIVATE.encode() not in record and _TOKEN.encode() not in record


def _record(record: bytes, expected: Any) -> None:
    assert record.endswith(b"\n") and record.count(b"\n") == 1
    assert len(record[:-1]) <= 1048576
    decoded = json.loads(record.decode("utf-8"))
    # Object key order is immaterial, while bool/int/null/scalar distinctions and
    # array order remain intact. Re-encoding also checks compact UTF-8 plus LF.
    assert json.dumps(decoded, sort_keys=True, ensure_ascii=False, allow_nan=False) == \
        json.dumps(expected, sort_keys=True, ensure_ascii=False, allow_nan=False)
    assert record == _json(decoded) + b"\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("host,port,authority", [
    ("127.0.0.1", 1, "127.0.0.1:1"), ("127.0.0.1", 80, "127.0.0.1:80"),
    ("::1", 80, "[::1]:80"), ("::1", 65535, "[::1]:65535"),
])
async def test_one_exact_numeric_status_request(
    host: str, port: int, authority: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    wire = _Wire(api, monkeypatch)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                 "NETRC", "SSL_CERT_FILE", "SSL_CERT_DIR", "DUTCHMATE_TOKEN"):
        monkeypatch.setenv(name, _PRIVATE)
    delivery = api.DeliveryState()

    def submitted(request: httpx.Request) -> None:
        assert delivery.request_outcome == "unknown"

    def receiving() -> None:
        assert delivery.request_outcome == "unknown"

    wire.on_request = submitted
    wire.stream.on_chunk = receiving
    code, record, state = await _status(api, host=host, port=port, delivery=delivery)
    assert code == 0 and json.loads(record) == _report()
    assert state.request_outcome == "report_received"
    assert len(wire.requests) == 1
    request = wire.requests[0]
    assert request.method == "GET" and request.url.host == host
    assert (request.url.port if request.url.port is not None else 80) == port
    assert request.url.scheme == "http" and request.url.raw_path == b"/v1/observation/status"
    assert request.url.query == b"" and request.url.fragment == ""
    assert request.content == b""
    assert request.headers.get_list("host") == [authority]
    assert request.headers.get_list("authorization") == ["Bearer " + _TOKEN]
    assert request.headers.get_list("accept") == ["application/json"]
    assert request.headers.get_list("accept-encoding") == ["identity"]
    assert "cookie" not in request.headers and "upgrade" not in request.headers
    assert "origin" not in request.headers
    assert not any(name.lower().startswith("sec-fetch-") for name in request.headers)
    assert _TOKEN not in str(request.url) and _TOKEN.encode() not in request.content
    assert len(wire.client_options) == len(wire.transport_options) == 1
    for options in (*wire.client_options, *wire.transport_options):
        assert options["trust_env"] is False and options["proxy"] is None
        assert options["http1"] is True and options["http2"] is False
        assert options["limits"].max_connections == 1
        assert options["limits"].max_keepalive_connections == 0
    assert wire.client_options[0]["follow_redirects"] is False
    assert wire.client_options[0]["mounts"] is None
    assert wire.transport_options[0]["retries"] == 0
    assert all(transport.closed for transport in wire.transports) and wire.stream.closed


@pytest.mark.asyncio
async def test_outer_absolute_budget_covers_request_and_raw_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    original = asyncio.timeout_at
    deadlines: list[tuple[float, float]] = []
    active: list[bool] = []

    class WatchedTimeout:
        def __init__(self, when: float) -> None:
            self.timer = original(when)

        async def __aenter__(self) -> asyncio.Timeout:
            active.append(True)
            return await self.timer.__aenter__()

        async def __aexit__(self, *args: Any) -> bool | None:
            try:
                await self.timer.__aexit__(*args)
                return None
            finally:
                active[-1] = False

    def timeout_at(when: float) -> WatchedTimeout:
        deadlines.append((when, asyncio.get_running_loop().time()))
        return WatchedTimeout(when)

    monkeypatch.setattr(asyncio, "timeout_at", timeout_at)
    if hasattr(api, "timeout_at"):
        monkeypatch.setattr(api, "timeout_at", timeout_at)
    wire = _Wire(api, monkeypatch, chunks=[b" ", _json(_report()), b" "])

    def requested(request: httpx.Request) -> None:
        assert active == [True]
        assert request.extensions["timeout"] == {
            "connect": 5.0, "read": 5.0, "write": 5.0, "pool": 5.0,
        }

    wire.on_request = requested

    def streamed() -> None:
        assert active == [True]

    wire.stream.on_chunk = streamed
    code, _, _ = await _status(api)
    assert code == 0 and wire.stream.yielded == 3
    assert len(deadlines) == 1 and 9.9 <= deadlines[0][0] - deadlines[0][1] <= 10.0
    assert active == [False]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", _STATES)
@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize("service_state", ["ready", "stopping"])
async def test_all_reported_states_and_opaque_facts_deliver_exit_zero(
    state: str, device: bool, service_state: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    report = _report(state, device=device)
    report["service_state"] = service_state
    wire = _Wire(api, monkeypatch, _json(report))
    code, record, delivery = await _status(api)
    assert code == 0 and json.loads(record) == report
    _record(record, report)
    if state != "inactive":
        assert b"Board \xce\xb1" in record
    assert delivery.request_outcome == "report_received" and wire.stream.closed


@pytest.mark.asyncio
async def test_nullable_facts_and_admissibility_are_not_recomputed(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _api()
    report = _report("failed", device=True)
    runtime = report["runtime"]
    runtime.update(session_id=None, attach_admissible=True, physical_release_confirmed=False)
    runtime["acquisition"].update(provenance=None, close_failed=True,
                                   primary_failure_kind=None,
                                   terminal_trigger="recording_failure")
    _Wire(api, monkeypatch, _json(report))
    code, record, _ = await _status(api)
    # Wire types are valid. Client must not reconstruct Core invariants or
    # manufacture a primary cause/committed connection ID from these facts.
    assert code == 0 and json.loads(record) == report


@pytest.mark.asyncio
@pytest.mark.parametrize("status,source,kind", _REMOTE_ERRORS)
async def test_documented_http_error_pairs_deliver_exit_four_without_replay(
    status: int, source: str, kind: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    error = {"error": {"source": source, "code": kind}}
    wire = _Wire(api, monkeypatch, _json(error), status=status)
    code, record, delivery = await _status(api)
    assert code == 4
    _record(record, error)
    assert delivery.request_outcome == "report_received"
    assert len(wire.requests) == 1 and wire.stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_redirects_reject_without_followup(status: int, monkeypatch: pytest.MonkeyPatch) -> None:
    api = _api()
    wire = _Wire(api, monkeypatch, b"{}", status=status,
                 headers=[("Content-Type", "application/json"),
                          ("Location", "http://192.0.2.1/" + _PRIVATE)])
    code, record, delivery = await _status(api)
    _local(code, record, "invalid_response")
    assert delivery.request_outcome == "unknown" and len(wire.requests) == 1
    assert wire.stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("error,kind", [
    (httpx.ConnectTimeout, "request_timeout"), (httpx.ReadTimeout, "request_timeout"),
    (httpx.WriteTimeout, "request_timeout"), (httpx.PoolTimeout, "request_timeout"),
    (httpx.ConnectError, "transport_failed"), (httpx.ReadError, "transport_failed"),
    (httpx.WriteError, "transport_failed"), (httpx.RemoteProtocolError, "invalid_response"),
])
async def test_transport_and_protocol_errors_are_fixed_with_unknown_delivery(
    error: type[httpx.TransportError], kind: str, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
) -> None:
    api = _api()
    wire = _Wire(api, monkeypatch, failure=error(_PRIVATE + _TOKEN))
    code, record, state = await _status(api)
    _local(code, record, kind)
    assert state.request_outcome == "unknown" and len(wire.requests) == 1
    assert all(transport.closed for transport in wire.transports)
    assert capsys.readouterr() == ("", "") and _PRIVATE not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    [("Content-Type", "application/json")],
    [("Content-Type", "APPLICATION/JSON; charset=utf-8")],
    [("Content-Type", 'application/json; charset="UTF-8"')],
    [("Content-Type", "application/json"), ("Content-Encoding", "identity")],
])
async def test_supported_media_and_identity_encoding(
    headers: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    _Wire(api, monkeypatch, headers=headers)
    code, record, _ = await _status(api)
    assert code == 0 and json.loads(record) == _report()


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    [], [("Content-Type", "text/plain")], [("Content-Type", "application/problem+json")],
    [("Content-Type", "application/json; charset=latin-1")],
    [("Content-Type", "application/json; private=value")],
    [("Content-Type", "application/json; charset=utf-8; charset=utf-8")],
    [("Content-Type", "application/json"), ("content-type", "application/json")],
    [("Content-Type", "application/json"), ("Content-Encoding", "gzip")],
    [("Content-Type", "application/json"), ("Content-Encoding", "br")],
    [("Content-Type", "application/json"), ("Content-Encoding", "")],
    [("Content-Type", "application/json"), ("Content-Encoding", "identity,identity")],
    [("Content-Type", "application/json"), ("Content-Encoding", "identity"),
     ("content-encoding", "identity")],
])
async def test_unsupported_or_duplicate_headers_reject_before_raw_consumption(
    headers: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    wire = _Wire(api, monkeypatch, headers=headers)
    code, record, _ = await _status(api)
    _local(code, record, "invalid_response")
    assert wire.stream.yielded == 0 and wire.stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    b"", b"\xff", b"\xef\xbb\xbf" + _json(_report()), b"{}{}", b"[]", b"null", b"{",
    _json(_report()).replace(b'"service_state":"ready"',
                            b'"service_state":"ready","service_state":"stopping"'),
    _json(_report()).replace(b'"baud_rate":57600',
                            b'"baud_rate":57600,"baud_rate":57600'),
    *[_json(_report()).replace(b'"stop_bits":2', b'"stop_bits":' + number)
      for number in [b"NaN", b"Infinity", b"-Infinity", b"1e9999"]],
])
async def test_strict_utf8_json_duplicate_and_nonfinite_rejection(
    body: bytes, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    wire = _Wire(api, monkeypatch, body)
    code, record, _ = await _status(api)
    _local(code, record, "invalid_response")
    assert wire.stream.closed


@pytest.mark.asyncio
async def test_native_h11_plain_text_400_is_protocol_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _api()
    _Wire(api, monkeypatch, b"Invalid HTTP request received.", status=400,
          headers=[("Content-Type", "text/plain")])
    _local(*(await _status(api))[:2], "invalid_response")


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body", [
    (201, {"error": {"source": "service", "code": "internal_failure"}}),
    (200, {"error": {"source": "service", "code": "internal_failure"}}),
    (500, {"error": {"source": "runtime", "code": "busy"}}),
    (401, {"error": {"source": "profile", "code": "missing_file"}}),
    (503, {"error": {"source": "service", "code": _PRIVATE}}),
    (400, {"error": {"source": "request", "code": "host_rejected", "detail": _PRIVATE}}),
    (400, {"error": {"source": "request", "code": "host_rejected"}, "detail": _PRIVATE}),
    (400, {"error": {"source": "request"}}),
    (400, {"error": {"source": 3, "code": "host_rejected"}}),
    (400, {"error": {"source": "request", "code": None}}),
])
async def test_closed_error_envelope_and_status_pair_rejection(
    status: int, body: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    _Wire(api, monkeypatch, _json(body), status=status)
    _local(*(await _status(api))[:2], "invalid_response")


# Each mutation breaks one independent wire shape/type/enum boundary. Expectations
# are literal; this is not a second Core or client validator.
_BAD_FIELDS: list[tuple[tuple[Any, ...], Any]] = [
    (("service_state",), "starting"), (("runtime", "state"), "connected"),
    (("runtime", "run_id"), 1), (("runtime", "session_id"), False),
    (("runtime", "stop_intent"), "reset"), (("runtime", "terminal_reason"), "unknown"),
    (("runtime", "attach_admissible"), 1), (("runtime", "owner_settled"), "true"),
    (("runtime", "physical_release_confirmed"), None),
    (("runtime", "recorder_close_confirmed"), 0),
    (("runtime", "cleanup_issues"), {}),
    (("runtime", "cleanup_issues"), [{"source": "backend_close", "code": "close_failed"}] * 3),
    (("runtime", "primary_issue"), {"source": "unknown", "code": "close_failed"}),
    (("runtime", "primary_issue"), {"source": "backend_close", "code": _PRIVATE}),
    (("runtime", "profile", "format_version"), True),
    (("runtime", "profile", "format_version"), 2),
    (("runtime", "profile", "dut", "name"), None),
    (("runtime", "profile", "backend", "expected_device"), []),
    (("runtime", "profile", "uart", "baud_rate"), "57600"),
    (("runtime", "profile", "uart", "data_bits"), True),
    (("runtime", "profile", "uart", "parity"), "unknown"),
    (("runtime", "profile", "uart", "stop_bits"), "2"),
    (("runtime", "profile", "uart", "stop_bits"), 10.0),
    (("runtime", "profile", "open_lines", "dtr"), "toggle"),
    (("runtime", "profile", "policy", "uart_tx_enabled"), 0),
    (("runtime", "profile", "session_policy", "max_database_pages"), 128.0),
    (("runtime", "acquisition", "state"), "unknown"),
    (("runtime", "acquisition", "terminal_trigger"), "unknown"),
    (("runtime", "acquisition", "primary_failure_kind"), "unknown"),
    (("runtime", "acquisition", "close_failed"), 0),
    (("runtime", "acquisition", "descriptor", "capabilities"), ["unknown"]),
    (("runtime", "acquisition", "descriptor", "capabilities"), "uart_receive"),
    (("runtime", "acquisition", "descriptor", "backend_observation_timestamp_domain", "observer"), "unknown"),
    (("runtime", "acquisition", "descriptor", "backend_observation_timestamp_domain", "meaning"), "unknown"),
    (("runtime", "acquisition", "descriptor", "backend_observation_timestamp_domain", "unit"), "unknown"),
    (("runtime", "acquisition", "descriptor", "loss_observability"), {"kind": "unknown"}),
    (("runtime", "acquisition", "descriptor", "connection_provenance", "envelope_version"), True),
    (("runtime", "acquisition", "descriptor", "connection_provenance", "envelope_version"), 2),
    (("runtime", "acquisition", "descriptor", "connection_provenance", "backend_schema_version"), "37"),
    (("runtime", "acquisition", "descriptor", "connection_provenance", "fields", 0, "value"), {}),
    (("runtime", "acquisition", "descriptor", "connection_provenance", "fields", 0, "value"), 1.5),
]
_CLOSED_OBJECTS = [
    (), ("runtime",), ("runtime", "profile"), ("runtime", "profile", "dut"),
    ("runtime", "profile", "backend"), ("runtime", "profile", "uart"),
    ("runtime", "profile", "open_lines"), ("runtime", "profile", "policy"),
    ("runtime", "profile", "session_policy"), ("runtime", "primary_issue"),
    ("runtime", "cleanup_issues", 0), ("runtime", "acquisition"),
    ("runtime", "acquisition", "descriptor"), ("runtime", "acquisition", "provenance"),
    ("runtime", "acquisition", "descriptor", "backend_observation_timestamp_domain"),
    ("runtime", "acquisition", "descriptor", "loss_observability"),
    ("runtime", "acquisition", "descriptor", "connection_provenance"),
    ("runtime", "acquisition", "descriptor", "connection_provenance", "fields", 0),
]


def _at(value: Any, path: tuple[Any, ...]) -> Any:
    for key in path:
        value = value[key]
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize("path,value", _BAD_FIELDS)
async def test_wire_primitive_and_enum_types_are_not_coerced(
    path: tuple[Any, ...], value: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    report = _report("failed", device=True)
    _at(report, path[:-1])[path[-1]] = value
    _Wire(api, monkeypatch, _json(report))
    _local(*(await _status(api))[:2], "invalid_response")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _CLOSED_OBJECTS)
@pytest.mark.parametrize("mutation", ["extra", "missing"])
async def test_every_nested_wire_object_is_closed(
    path: tuple[Any, ...], mutation: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    report = _report("failed", device=True)
    target = _at(report, path)
    if mutation == "extra":
        target["private_extra"] = _PRIVATE
    else:
        target.pop(next(iter(target)))
    _Wire(api, monkeypatch, _json(report))
    _local(*(await _status(api))[:2], "invalid_response")


@pytest.mark.asyncio
@pytest.mark.parametrize("overflow", [False, True])
async def test_actual_body_limit_with_detection_byte_not_content_length(
    overflow: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    base = _json(_report())
    body = base + b" " * (_LIMIT - len(base) + int(overflow))
    headers = [("Content-Type", "application/json")]
    if overflow:
        headers.append(("Content-Length", "1"))
    wire = _Wire(api, monkeypatch, body, headers=headers)
    code, record, state = await _status(api)
    if overflow:
        _local(code, record, "invalid_response")
        assert state.request_outcome == "unknown"
    else:
        assert code == 0
        _record(record, _report())
    assert wire.stream.closed


@pytest.mark.asyncio
async def test_overflow_chunk_is_sliced_before_retention(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _api()
    retained: list[int] = []

    class WatchedBuffer(bytearray):
        def extend(self, value: Any) -> None:
            super().extend(value)
            retained.append(len(self))
            assert len(self) <= 1048577, "raw/output accumulator exceeded detection bound"

    # A private accumulator spy, not a product injection point or socket-read cap.
    # Keep this spy at the chosen buffer boundary if T008 changes its container.
    monkeypatch.setattr(api, "bytearray", WatchedBuffer, raising=False)
    wire = _Wire(api, monkeypatch, chunks=[b" " * 8, b" " * (_LIMIT * 2), b"unused"])
    code, record, _ = await _status(api)
    _local(code, record, "invalid_response")
    assert retained and max(retained) <= 1048577
    assert wire.stream.yielded == 2 and wire.stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("overflow", [False, True])
async def test_encoded_record_bound_counts_utf8_and_excludes_newline(
    overflow: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    report = _report()
    report["runtime"]["profile"]["dut"]["name"] = ""
    base_length = len(_json(report))
    report["runtime"]["profile"]["dut"]["name"] = "é" + "a" * (_LIMIT - base_length - 2)
    expected = _json(report)
    assert len(expected) == _LIMIT
    if overflow:
        # 006 stop_bits is integer, so a float cannot manufacture a valid wire
        # expansion. Verify the encoder's independent cap with a typed report
        # directly; its private seam makes no public protocol change.
        report["runtime"]["profile"]["dut"]["name"] += "a"
        expected = _json(report)
        assert len(expected) == _LIMIT + 1
        # Context import-purity tests reload its exception definitions; obtain
        # the helper's actual ordinary exception class rather than a stale alias.
        with pytest.raises(api.CliFailure) as caught:
            api._encode_record(report)
        assert caught.value.kind.value == "invalid_response"
        delivery = api.DeliveryState()
        delivery.request_outcome = "report_received"
        code, record = api.local_failure(caught.value.kind, delivery)
        _local(code, record, "invalid_response", phase="report_received")
        return
    _Wire(api, monkeypatch, expected)
    code, record, delivery = await _status(api)
    assert code == 0 and len(record) == _LIMIT + 1
    _record(record, report)
    assert delivery.request_outcome == "report_received"


@pytest.mark.asyncio
async def test_partial_response_read_failure_discards_report(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _api()
    wire = _Wire(api, monkeypatch, chunks=[b'{"service_state":"ready",'],
                 stream_failure=httpx.ReadError(_PRIVATE))
    _local(*(await _status(api))[:2], "transport_failed")
    assert wire.stream.closed and len(wire.requests) == 1


@pytest.mark.parametrize("kind,exit_code", [
    ("invalid_arguments", 2), ("unsupported_platform", 3), ("credential_unavailable", 3),
    ("unsafe_credential", 3), ("request_timeout", 5), ("transport_failed", 5),
    ("invalid_response", 5), ("interrupted", 130), ("output_failed", 1),
    ("internal_failure", 1),
])
@pytest.mark.parametrize("phase", ["not_submitted", "unknown", "report_received"])
def test_fixed_local_exit_envelopes_preserve_delivery_phase(
    kind: str, exit_code: int, phase: str,
) -> None:
    api = _api()
    delivery = api.DeliveryState()
    delivery.request_outcome = type(delivery.request_outcome)(phase)
    code, record = api.local_failure(CliFailureKind(kind), delivery)
    assert code == exit_code
    _record(record, {"error": {"source": "cli", "code": kind}, "request_outcome": phase})


@pytest.mark.asyncio
async def test_http_diagnostics_and_raw_response_never_leak(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "disabled", False)
        monkeypatch.setattr(logger, "propagate", True)
        monkeypatch.setattr(logger, "level", logging.DEBUG)
    caplog.set_level(logging.DEBUG)
    wire = _Wire(api, monkeypatch, _PRIVATE.encode())

    def requested(request: httpx.Request) -> None:
        logging.getLogger("httpcore.connection").debug(_PRIVATE + _TOKEN)

    wire.on_request = requested
    _local(*(await _status(api))[:2], "invalid_response")
    assert _PRIVATE not in caplog.text and _TOKEN not in caplog.text
    assert capsys.readouterr() == ("", "")
    for name in ("httpx", "httpcore"):
        assert logging.getLogger(name).disabled
        assert not logging.getLogger(name).propagate


@pytest.fixture
def native_service_helper(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Reuse 006's independently guarded real launcher child, unchanged."""
    source = Path(__file__).resolve().parents[2] / "service/tests/test_service_process.py"
    name = "_dutchmate_cli_t010_service_helper"
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def test_t010_native_service_helper_has_independent_safety_guards(
    native_service_helper: Any, account_home: Path,
) -> None:
    with native_service_helper._child(account_home, 8765, mode="probe") as child:
        assert child.finish(None) == {
            "account_isolated": True, "hardware_blocked": True,
            "real_bootstrap_blocked": True,
        }
        child.private_output()
    assert not (account_home / ".local/state/dutchmate/service").exists()


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("case,expected", [
    ("valid", None), ("stale", "authentication_required"),
    ("host", "host_rejected"), ("origin", "origin_rejected"),
    ("browser", "origin_rejected"),
])
def test_t010_native_status_uses_actual_006_authentication_and_lifespan(
    native_service_helper: Any, account_home: Path, host: str, case: str,
    expected: str | None, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
) -> None:
    from dutchmate_core.adapters import (
        basic_serial,
        observation_runtime,
        sqlite_evidence,
    )

    from dutchmate_cli import context, main

    # Only the existing guarded service child binds sockets/owns a runtime. No
    # new CLI subprocess/attach/lifecycle/installed-SIGINT scenario belongs here.
    port = native_service_helper._port(host)
    with native_service_helper._child(account_home, port, host) as child:
        token = child.ready()
        credential_path = account_home / ".local/state/dutchmate/service/credential"
        if case == "stale":
            alternate = (b"0" if token[:1] != b"0" else b"1") + token[1:]
            credential_path.write_bytes(alternate + b"\n")
        else:
            alternate = token
        original_read = context.read_credential
        original_send = httpx.AsyncClient.send
        reads = 0
        requests: list[httpx.Request] = []
        responses: list[httpx.Response] = []

        def credential() -> str:
            nonlocal reads
            reads += 1
            return original_read()

        async def send(
            owner: httpx.AsyncClient, request: httpx.Request, *args: Any, **kwargs: Any,
        ) -> httpx.Response:
            requests.append(request)
            assert request.method == "GET" and request.url.raw_path == b"/v1/observation/status"
            assert request.headers.get_list("authorization") == ["Bearer " + alternate.decode()]
            assert request.content == b"" and "trace" not in request.extensions
            if case == "host":
                request.headers["Host"] = f"localhost:{port}"
            elif case == "origin":
                request.headers["Origin"] = "https://" + _PRIVATE
            elif case == "browser":
                request.headers["Sec-Fetch-Mode"] = "cors"
            response = await original_send(owner, request, *args, **kwargs)
            responses.append(response)
            return response

        def forbidden(*args: Any, **kwargs: Any) -> Any:
            pytest.fail("status must not resolve DNS, read Profiles or prepare run resources")

        with monkeypatch.context() as patch:
            patch.setattr(context, "read_credential", credential)
            patch.setattr(httpx.AsyncClient, "send", send)
            patch.setattr(socket, "getaddrinfo", forbidden)
            patch.setattr(observation_runtime, "resolve_profile", forbidden)
            patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "create", forbidden)
            patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "open", forbidden)
            patch.setattr(basic_serial.BasicSerialBackend, "__init__", forbidden)
            patch.setattr(basic_serial.BasicSerialBackend, "open", forbidden)
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "SSL_CERT_FILE"):
                patch.setenv(name, _PRIVATE)
            with caplog.at_level(logging.DEBUG):
                code = main.main(["--host", host, "--port", str(port), "status"])
        stdout, stderr = capsys.readouterr()
        if expected is None:
            assert code == 0 and stderr == ""
            assert json.loads(stdout) == _report("inactive")
        else:
            assert code == 4 and stdout == ""
            assert json.loads(stderr) == {"error": {"source": "request", "code": expected}}
        assert reads == len(requests) == len(responses) == 1
        authority = f"[::1]:{port}" if host == "::1" else f"127.0.0.1:{port}"
        if case != "host":
            assert requests[0].headers.get_list("host") == [authority]
        assert responses[0].is_closed
        for private in (token.decode(), alternate.decode(), _PRIVATE, str(account_home)):
            assert private not in stdout + stderr + caplog.text
        audit = child.audit()
        assert len(audit["runtime"]) == 1 and audit["runtime"][0] == {
            "same_process": True, "running_loop": True, "dirty_marker": True,
            "credential_present": True, "guard_held": True,
        }
        assert audit["bound"] == [{"host": host, "port": port,
                                   "v6only": 1 if host == "::1" else None}]
        audit = child.finish()
        assert audit["outcome"] == "returned" and not audit["force_exit"]
        child.private_output(token, alternate, _PRIVATE.encode())
        assert not credential_path.exists()
        assert json.loads((credential_path.parent / "owner.json").read_bytes()) == {
            "version": 1, "cleanup_confirmed": True,
        }


@pytest.mark.parametrize("args", [[], ["--help"], ["status", "--help"]])
def test_t010_help_output_failure_has_fixed_output_category(
    args: list[str], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dutchmate_cli import main

    class BrokenBuffer(io.BytesIO):
        def write(self, data: Any) -> int:
            raise BrokenPipeError(errno.EPIPE, _PRIVATE)

    output = io.TextIOWrapper(BrokenBuffer(), encoding="utf-8", write_through=True)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(sys, "stdout", output)
            # Native Typer's EPIPE handling replaces both streams. Restore both
            # after the probe so it cannot corrupt pytest's output capture.
            patch.setattr(sys, "stderr", sys.stderr)
            assert main.main(args) == 1
    finally:
        output.close()
    stdout, stderr = capsys.readouterr()
    assert stdout == ""
    assert json.loads(stderr) == {
        "error": {"source": "cli", "code": "output_failed"},
        "request_outcome": "not_submitted",
    }
    assert _PRIVATE not in stderr and stderr.count("\n") == 1


@pytest.mark.parametrize("value", [1, _PRIVATE])
def test_t010_unexpected_framework_exit_remains_internal_failure(
    value: int | str, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import typer

    from dutchmate_cli import main

    class ExitingTyper(typer.Typer):
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            raise SystemExit(value)

    monkeypatch.setattr(main, "app", ExitingTyper())
    assert main.main([]) == 1
    stdout, stderr = capsys.readouterr()
    assert stdout == ""
    assert json.loads(stderr) == {
        "error": {"source": "cli", "code": "internal_failure"},
        "request_outcome": "not_submitted",
    }
    assert _PRIVATE not in stderr


# T016: exercise actual exchange lifetime, not a simulated operation result.
async def _t016_exchange(
    api: Any, command: str, delivery: Any, *, endpoint: Endpoint | None = None,
    credential: str = _TOKEN, paths: AttachPaths | None = None,
) -> tuple[int, bytes]:
    options: dict[str, Any] = {}
    if command == "attach":
        options["paths"] = paths or AttachPaths("/private-profile.toml", "/private-journal.sqlite3")
    result = await api.exchange(
        endpoint=endpoint or Endpoint(port=80), command=command, credential=credential,
        delivery=delivery, **options,
    )
    return cast(tuple[int, bytes], result)


def _t016_budget(patch: pytest.MonkeyPatch, seconds: float = 0.04) -> list[float]:
    """Shorten only the test clock boundary; verify the real requested10s budget."""
    original = asyncio.timeout_at
    budgets: list[float] = []

    def bounded(when: float) -> asyncio.Timeout:
        now = asyncio.get_running_loop().time()
        budgets.append(when - now)
        assert 9.9 <= when - now <= 10.0
        return original(now + seconds)

    patch.setattr(asyncio, "timeout_at", bounded)
    return budgets


def _t016_one_request(wire: _Wire, command: str) -> None:
    assert len(wire.requests) == 1
    request = wire.requests[0]
    assert request.method == ("GET" if command == "status" else "POST")
    assert request.url.raw_path == f"/v1/observation/{command}".encode()
    assert request.url.query == b""
    assert request.extensions["timeout"] == {"connect": 5.0, "read": 5.0, "write": 5.0, "pool": 5.0}
    assert all(transport.closed for transport in wire.transports)


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "status", "detach"])
@pytest.mark.parametrize("waiting", ["headers", "empty_body", "trickle", "headers_then_body"])
async def test_t016_absolute_wait_budget_never_restarts_at_headers_or_chunks(
    command: str, waiting: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, delivery = _api(), _api().DeliveryState()
    budgets = _t016_budget(monkeypatch)
    wire = _Wire(api, monkeypatch)

    class WaitingStream(_Stream):
        cancelled = False
        async def __aiter__(self) -> AsyncIterator[bytes]:
            try:
                while True:
                    assert delivery.request_outcome == "unknown"
                    await asyncio.sleep(0.005)
                    self.yielded += 1
                    yield b" " if waiting == "trickle" else b""
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    wire.stream = WaitingStream([])
    class WaitingTransport(_Transport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            assert delivery.request_outcome == "unknown"
            if waiting == "headers":
                self.wire.requests.append(request)
                await asyncio.Event().wait()
            elif waiting == "headers_then_body":
                await asyncio.sleep(0.025)
            return await super().handle_async_request(request)

    def transport(*args: Any, **kwargs: Any) -> WaitingTransport:
        value = WaitingTransport(wire)
        wire.transports.append(value)
        return value

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    result = await asyncio.wait_for(_t016_exchange(api, command, delivery), 0.5)
    _local(*result, "request_timeout")
    assert len(budgets) == 1 and delivery.request_outcome == "unknown"
    _t016_one_request(wire, command)
    if waiting != "headers":
        assert wire.stream.closed and wire.stream.cancelled
    if waiting == "trickle":
        assert wire.stream.yielded >= 3


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "status", "detach"])
async def test_t016_setup_failure_stays_not_submitted_without_any_operation_request(
    command: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, delivery = _api(), _api().DeliveryState()
    wire = _Wire(api, monkeypatch)
    def failed_transport(*args: Any, **kwargs: Any) -> Any:
        assert delivery.request_outcome == "not_submitted"
        raise RuntimeError(_PRIVATE)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", failed_transport)
    code, record = await _t016_exchange(api, command, delivery)
    assert code == 1 and wire.requests == [] and delivery.request_outcome == "not_submitted"
    _record(record, {"error": {"source": "cli", "code": "internal_failure"}, "request_outcome": "not_submitted"})
    assert _PRIVATE.encode() not in record


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "status", "detach"])
@pytest.mark.parametrize("case,expected_code,kind,phase", [
    ("report", 0, None, "report_received"), ("rejection", 4, None, "report_received"),
    ("unrecognized", 5, "invalid_response", "unknown"),
    ("truncated", 5, "invalid_response", "unknown"),
    ("partial_read_loss", 5, "transport_failed", "unknown"),
    ("complete_bytes_read_loss", 5, "transport_failed", "unknown"),
    ("partial_protocol_loss", 5, "invalid_response", "unknown"),
])
async def test_t016_receipt_phase_requires_complete_validated_delivery_not_admission(
    command: str, case: str, expected_code: int, kind: str | None, phase: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, delivery = _api(), _api().DeliveryState()
    report = _report("failed")
    rejection = {"error": {"source": "runtime", "code": "busy"}}
    body = _json(rejection if case == "rejection" else report)
    status = 409 if case == "rejection" else 200
    failure: Exception | None = None
    if case == "unrecognized":
        body = _json({"error": {"source": "service", "code": _PRIVATE}})
        status = 500
    elif case == "truncated":
        body = body[:-1]
    elif case == "partial_read_loss":
        body = body[:30]
        failure = httpx.ReadError(_PRIVATE)
    elif case == "complete_bytes_read_loss":
        failure = httpx.ReadError(_PRIVATE)
    elif case == "partial_protocol_loss":
        body = body[:30]
        failure = httpx.RemoteProtocolError(_PRIVATE)
    wire = _Wire(api, monkeypatch, body, status=status, stream_failure=failure)
    wire.on_request = lambda request: _t016_unknown(delivery)
    wire.stream.on_chunk = lambda: _t016_unknown(delivery)
    code, record = await _t016_exchange(api, command, delivery)
    assert code == expected_code and delivery.request_outcome == phase
    if kind is not None:
        _local(code, record, kind)
    else:
        _record(record, rejection if case == "rejection" else report)
    assert wire.stream.closed
    _t016_one_request(wire, command)


def _t016_unknown(delivery: Any) -> None:
    assert delivery.request_outcome == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "status", "detach"])
@pytest.mark.parametrize("ending", ["cancelled", "encoding_failure"])
async def test_t016_post_validation_failure_preserves_report_received(
    command: str, ending: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, delivery = _api(), _api().DeliveryState()
    wire = _Wire(api, monkeypatch)
    original = api._encode_record
    calls = 0
    def encoding(value: Any) -> bytes:
        nonlocal calls
        calls += 1
        assert delivery.request_outcome == "report_received"
        if calls == 1:
            if ending == "cancelled":
                raise asyncio.CancelledError
            raise api.CliFailure(CliFailureKind.INVALID_RESPONSE)
        return cast(bytes, original(value))
    monkeypatch.setattr(api, "_encode_record", encoding)
    if ending == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await _t016_exchange(api, command, delivery)
        assert calls == 1
    else:
        _local(*(await _t016_exchange(api, command, delivery)), "invalid_response", phase="report_received")
        assert calls == 2
    assert delivery.request_outcome == "report_received" and wire.stream.closed
    _t016_one_request(wire, command)


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "status", "detach"])
@pytest.mark.parametrize("prefix", [0, _LIMIT - 1])
async def test_t016_large_already_buffered_chunk_is_sliced_at_remaining_detection_bound(
    command: str, prefix: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, delivery = _api(), _api().DeliveryState()
    retained: list[int] = []
    class Accumulator(bytearray):
        def extend(self, value: Any) -> None:
            assert len(value) <= _LIMIT + 1 - len(self)
            super().extend(value)
            retained.append(len(self))
    monkeypatch.setattr(api, "bytearray", Accumulator, raising=False)
    wire = _Wire(api, monkeypatch, chunks=[b" " * prefix, b" " * (_LIMIT * 3), b"never-consumed"])
    _local(*(await _t016_exchange(api, command, delivery)), "invalid_response")
    assert max(retained) == _LIMIT + 1
    assert wire.stream.yielded == 2 and wire.stream.closed
    assert delivery.request_outcome == "unknown"
    _t016_one_request(wire, command)


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "status", "detach"])
@pytest.mark.parametrize("where", ["headers", "body"])
async def test_t016_cancelling_async_client_wait_joins_delivery_without_replay(
    command: str, where: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, delivery = _api(), _api().DeliveryState()
    wire, entered = _Wire(api, monkeypatch), asyncio.Event()
    cancelled = asyncio.Event()
    class BlockingStream(_Stream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            entered.set()
            try:
                await asyncio.Event().wait()
                yield b"unreachable"
            finally:
                cancelled.set()
    if where == "body":
        wire.stream = BlockingStream([])
    else:
        class BlockingTransport(_Transport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                wire.requests.append(request)
                entered.set()
                try:
                    await asyncio.Event().wait()
                    raise AssertionError("unreachable")
                finally:
                    cancelled.set()
        def transport(*args: Any, **kwargs: Any) -> BlockingTransport:
            value = BlockingTransport(wire)
            wire.transports.append(value)
            return value
        monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    pending = asyncio.create_task(_t016_exchange(api, command, delivery))
    try:
        await asyncio.wait_for(entered.wait(), 3.0)
        assert delivery.request_outcome == "unknown"
    finally:
        pending.cancel()  # Client delivery task only, never a service/Core owner.
        with pytest.raises(asyncio.CancelledError):
            await pending
    assert cancelled.is_set() and pending.done()
    _t016_one_request(wire, command)
    if where == "body":
        assert wire.stream.closed


@pytest_asyncio.fixture
async def t016_service(
    tmp_path: Path, account_home: Path, monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[Any, Any]]:
    source = Path(__file__).with_name("test_cli_lifecycle.py")
    name = "_dutchmate_cli_t016_lifecycle"
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    fixture = inspect.unwrap(module.lifecycle_service)(tmp_path, account_home, monkeypatch)
    h = await anext(fixture)
    try:
        yield module, h
    finally:
        await fixture.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "detach"])
@pytest.mark.parametrize("stage", ["before_core", "inside_core"])
@pytest.mark.parametrize("loss", ["deadline", "read_loss", "cancelled_wait"])
async def test_t016_actual_admitted_mutation_settles_after_client_delivery_loss(
    t016_service: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch,
    command: str, stage: str, loss: str,
) -> None:
    from dutchmate_core.adapters.basic_serial import BasicSerialBackend

    from dutchmate_cli import context

    module, h = t016_service
    if command == "detach":
        seeded = await h.service.request(
            "/v1/observation/attach", "POST",
            h.helper._t011_body(h.composition.profile_path, h.composition.journal_path),
        )
        assert seeded.status == 200
    entered, allow, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    app_module = h.helper._t009_module()
    actual = app_module.attach_basic_observation if command == "attach" else h.service.runtime.detach

    async def operation(*args: Any, **kwargs: Any) -> Any:
        try:
            if stage == "before_core":
                entered.set()
                await allow.wait()
            return await actual(*args, **kwargs)
        finally:
            settled.set()

    delivery = _api().DeliveryState()
    closed: list[bool] = []
    delivery_tasks: list[asyncio.Task[httpx.Response]] = []
    pending: asyncio.Task[tuple[int, bytes]] | None = None
    with monkeypatch.context() as patch:
        if command == "attach":
            patch.setattr(app_module, "attach_basic_observation", operation)
        else:
            patch.setattr(h.service.runtime, "detach", operation)
        if stage == "inside_core":
            if command == "attach":
                actual_open = BasicSerialBackend.open
                async def gated_open(backend: BasicSerialBackend) -> Any:
                    entered.set()
                    await allow.wait()
                    return await actual_open(backend)
                patch.setattr(BasicSerialBackend, "open", gated_open)
            else:
                journal = h.composition.journals[0]
                actual_close = journal.close
                async def gated_close() -> None:
                    entered.set()
                    await allow.wait()
                    await actual_close()
                patch.setattr(journal, "close", gated_close)
        module._bridge(h, patch)
        base_transport = httpx.AsyncHTTPTransport
        class LossTransport(httpx.AsyncBaseTransport):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.base = base_transport(*args, **kwargs)
                self.slot = len(closed)
                closed.append(False)
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                if loss == "read_loss" and request.url.path == f"/v1/observation/{command}":
                    task = asyncio.create_task(self.base.handle_async_request(request))
                    delivery_tasks.append(task)
                    await entered.wait()
                    task.cancel()  # ASGI delivery waiter only; registered operation is shielded.
                    await asyncio.gather(task, return_exceptions=True)
                    raise httpx.ReadError(_PRIVATE)
                return await self.base.handle_async_request(request)
            async def aclose(self) -> None:
                await self.base.aclose()
                closed[self.slot] = True
        patch.setattr(httpx, "AsyncHTTPTransport", LossTransport)
        budgets = _t016_budget(patch, 0.15) if loss == "deadline" else []
        paths = AttachPaths(str(h.composition.profile_path), str(h.composition.journal_path))
        credential = context.read_credential()
        assert delivery.request_outcome == "not_submitted"
        pending = asyncio.create_task(_t016_exchange(
            _api(), command, delivery, endpoint=h.endpoint, credential=credential, paths=paths,
        ))
        try:
            await asyncio.wait_for(entered.wait(), 3.0)
            before = h.service.runtime.status()
            assert delivery.request_outcome == "unknown"
            assert before.state.value == (
                "inactive" if command == "attach" and stage == "before_core" else
                "active" if command == "detach" and stage == "before_core" else
                "attaching" if command == "attach" else "detaching"
            )
            if loss == "cancelled_wait":
                pending.cancel()  # Actual client waiter, never the operation/Core owner.
                with pytest.raises(asyncio.CancelledError):
                    await pending
            else:
                code, record = await asyncio.wait_for(pending, 3.0)
                _local(code, record, "request_timeout" if loss == "deadline" else "transport_failed")
            assert not settled.is_set() and not allow.is_set()
            assert delivery.request_outcome == "unknown" and closed == [True]
            assert h.service.runtime.status() == before
            assert len(h.requests) == 1
            assert h.requests[0].headers.get_list("authorization") == ["Bearer " + credential]
            assert all(task.done() for task in delivery_tasks)
            allow.set()
            await asyncio.wait_for(settled.wait(), 3.0)
            current = h.service.runtime.status()
            assert current.state.value == ("active" if command == "attach" else "terminated")
            assert current.stop_intent.value == ("none" if command == "attach" else "detach")
            assert len(h.composition.serials) == len(h.composition.journals) == 1
            assert h.composition.serials[0].close_calls == (0 if command == "attach" else 1)
            assert len(h.requests) == 1  # No recovery/status/detach from lost invocation.
            # A new explicitly invoked status observes facts; it does not recover
            # the lost response or attribute the operation to this client.
            later = _api().DeliveryState()
            code, record = await _t016_exchange(
                _api(), "status", later, endpoint=h.endpoint, credential=context.read_credential(),
            )
            assert code == 0 and later.request_outcome == "report_received"
            assert json.loads(record)["runtime"]["state"] == current.state.value
            assert delivery.request_outcome == "unknown" and len(h.requests) == 2
            assert h.requests[-1].method == "GET" and closed == [True, True]
            if loss == "deadline":
                assert len(budgets) == 2
        finally:
            allow.set()
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            if entered.is_set():
                await asyncio.wait_for(settled.wait(), 3.0)


@asynccontextmanager
async def _t016_native_listener(
    mode: str,
) -> AsyncIterator[tuple[Endpoint, list[bytes], list[int]]]:
    """Scripted local HTTP only; no service/DUT/account or arbitrary child process."""
    stop = asyncio.Event()
    requests: list[bytes] = []
    chunks: list[int] = []
    tasks: set[asyncio.Task[Any]] = set()
    writers: list[asyncio.StreamWriter] = []
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        tasks.add(task)
        writers.append(writer)
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3.0)
            assert len(head) < 16384
            requests.append(head)
            if mode == "headers":
                await stop.wait()
            else:
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n")
                await writer.drain()
                while not stop.is_set():
                    writer.write(b"1\r\n \r\n")
                    await writer.drain()
                    chunks.append(1)
                    await asyncio.sleep(0.15)
        except ConnectionError:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass  # Expected peer close on client timeout; no diagnostic dump.
            tasks.discard(task)
    server = await asyncio.start_server(handle, host="127.0.0.1", port=0)
    endpoint = Endpoint(port=server.sockets[0].getsockname()[1])
    try:
        yield endpoint, requests, chunks
    finally:
        stop.set()
        server.close()
        await server.wait_closed()
        for writer in writers:
            writer.close()
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tuple(tasks)), 3.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,minimum,maximum", [("headers", 4.7, 8.0), ("trickle", 9.7, 13.0)])
async def test_t016_native_default_phase_and_total_limits_end_waiting(
    mode: str, minimum: float, maximum: float,
) -> None:
    # Native IPv4/software evidence with unmodified10s/5s settings. Timing
    # tolerance is a test watchdog, never a hard real-time Core guarantee.
    api, delivery = _api(), _api().DeliveryState()
    async with _t016_native_listener(mode) as (endpoint, requests, chunks):
        start = asyncio.get_running_loop().time()
        code, record = await asyncio.wait_for(_t016_exchange(api, "status", delivery, endpoint=endpoint), 14.0)
        elapsed = asyncio.get_running_loop().time() - start
        _local(code, record, "request_timeout")
        assert minimum <= elapsed < maximum
        assert len(requests) == 1 and delivery.request_outcome == "unknown"
        assert requests[0].startswith(b"GET /v1/observation/status HTTP/1.1\r\n")
        if mode == "trickle":
            assert len(chunks) >= 20
