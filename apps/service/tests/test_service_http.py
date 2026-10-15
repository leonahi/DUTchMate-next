"""Security, response mapping and controlled inactive app composition contracts.

Pure-gate cases use a downstream ASGI probe containing no security policy. T009
uses the real app/lifespan/runtime. Real isolated bootstrap supplies credentials;
no HTTP listener, serial transport, session or resource preparation occurs here.
"""

import asyncio
import importlib
import importlib.util
import json
import logging
import os
import secrets
from collections.abc import AsyncIterator, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, get_ident
from typing import Any, BinaryIO, cast

import pytest
from dutchmate_core.adapters import basic_serial, observation_runtime, sqlite_evidence
from dutchmate_core.adapters.toml_profile import resolve_profile
from dutchmate_core.model import SessionId, SessionPolicy
from dutchmate_core.profile import ProfileFailure, ProfileFailureKind
from dutchmate_core.runtime import (
    ObservationRuntime,
    RunId,
    RuntimeIssue,
    RuntimeIssueSource,
    RuntimeRejectedError,
    RuntimeRejectedKind,
    RuntimeState,
    RuntimeStatus,
    RuntimeTerminalReason,
)
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from dutchmate_service.bootstrap import (
    BootstrapFailure,
    BootstrapFailureKind,
    PrivateBootstrap,
    ServiceConfig,
)

_STATUS = "/v1/observation/status"
_ATTACH = "/v1/observation/attach"
_DETACH = "/v1/observation/detach"
_PAYLOAD = b'{"profile_path":"/private/tmp/private-profile.toml","journal_path":"/private/tmp/private-journal.sqlite3"}'
_PROBE_BODY = b'{"probe":"reached"}'
_CONFIGS = (ServiceConfig(8765), ServiceConfig(8765, "::1"))


@pytest.mark.parametrize(
    ("failure", "status", "source", "code"),
    [
        (RuntimeRejectedError(RuntimeRejectedKind.BUSY), 409, "runtime", "busy"),
        (
            RuntimeRejectedError(RuntimeRejectedKind.CLEANUP_UNCONFIRMED),
            409,
            "runtime",
            "cleanup_unconfirmed",
        ),
        (
            RuntimeRejectedError(RuntimeRejectedKind.INVALID_REQUEST),
            422,
            "runtime",
            "invalid_request",
        ),
        (
            RuntimeRejectedError(RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT),
            500,
            "runtime",
            "wrong_execution_context",
        ),
        (
            ProfileFailure(ProfileFailureKind.MISSING_FILE, "private-rejection-detail"),
            422,
            "profile",
            "missing_file",
        ),
        (
            ProfileFailure(
                ProfileFailureKind.INVALID_VALUE, "private-rejection-detail"
            ),
            422,
            "profile",
            "invalid_value",
        ),
    ],
    ids=["busy", "uncertain", "request", "context", "profile-missing", "profile-value"],
)
@pytest.mark.asyncio
async def test_t008_typed_downstream_rejection_preserves_normalized_http_mapping(
    process_credential: Callable[[ServiceConfig], Any],
    failure: Exception,
    status: int,
    source: str,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        gate = _gate(Downstream(fault=failure), config, owner)
        with caplog.at_level(logging.DEBUG):
            response = await _call(
                gate, _scope(config, _headers(config, token)), Exchange()
            )
        assert response.status == status
        assert json.loads(response.payload) == {
            "error": {"source": source, "code": code}
        }
        assert response.headers[b"cache-control"] == b"no-store"
        assert b"private-rejection-detail" not in response.payload
        assert "private-rejection-detail" not in caplog.text


@pytest.fixture
def process_credential(
    account_home: Path,
) -> Callable[[ServiceConfig], Any]:
    """Real bootstrap and client file read, never a permissive authentication stub."""

    @contextmanager
    def owned(config: ServiceConfig) -> Iterator[tuple[PrivateBootstrap, bytes]]:
        owner = PrivateBootstrap.acquire(config)
        try:
            owner.mark_unconfirmed()
            owner.publish_credential()
            value = (
                account_home / ".local/state/dutchmate/service/credential"
            ).read_bytes()
            assert len(value) == 65 and value.endswith(b"\n")
            yield owner, value[:-1]
        finally:
            try:
                owner.invalidate_credential()
                owner.confirm_cleanup(
                    owner_settled=True,
                    physical_release_confirmed=True,
                    recorder_close_confirmed=True,
                )
            finally:
                owner.release()

    return owned


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.asyncio
async def test_t008_validation_preserves_body_and_later_disconnect_for_downstream(
    process_credential: Callable[[ServiceConfig], Any], split: bool
) -> None:
    config = _CONFIGS[0]
    chunks = (_PAYLOAD[:17], _PAYLOAD[17:]) if split else (_PAYLOAD,)
    delivered = 0
    received: list[Message] = []

    async def source_receive() -> Message:
        nonlocal delivered
        if delivered == len(chunks):
            return {"type": "http.disconnect"}
        chunk = chunks[delivered]
        delivered += 1
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": delivered < len(chunks),
        }

    async def consumer(scope: Scope, receive: Receive, send: Send) -> None:
        received.append(await receive())
        received.append(await receive())
        await Downstream()(scope, receive, send)

    with process_credential(config) as (owner, token):
        gate = _gate(consumer, config, owner)
        headers = _headers(config, token) + [(b"content-type", b"application/json")]
        response = Exchange()
        await gate(
            _scope(config, headers, path=_ATTACH, method="POST"),
            source_receive,
            response.send,
        )
        assert response.status == 200
        assert received == [
            {"type": "http.request", "body": _PAYLOAD, "more_body": False},
            {"type": "http.disconnect"},
        ]


@pytest.fixture(autouse=True)
def forbid_profile_and_run_preparation(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    if "t011_composition" in request.fixturenames:
        # Only this fixture permits real temporary Profile/SQLite/Basic work.
        # The physical serial/discovery and real-account guards still apply.
        return

    def forbidden(*args: object, **kwargs: object) -> Any:
        del args, kwargs
        pytest.fail(
            "T006 security boundary must not read Profiles or prepare run resources"
        )

    monkeypatch.setattr(observation_runtime, "resolve_profile", forbidden)
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "create", forbidden)
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "create_v2", forbidden)
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "open", forbidden)
    monkeypatch.setattr(basic_serial.BasicSerialBackend, "__init__", forbidden)
    monkeypatch.setattr(basic_serial.BasicSerialBackend, "open", forbidden)


def _gate(app: ASGIApp, config: ServiceConfig, owner: PrivateBootstrap) -> ASGIApp:
    # Intended internal middleware seam; no product implementation in this task.
    module = importlib.import_module("dutchmate_service.http")
    factory = getattr(module, "SecurityGate", None)
    assert callable(factory), "T006 requires the planned pure ASGI SecurityGate"
    return cast(
        ASGIApp,
        factory(app, config=config, credential=lambda: owner.credential),
    )


def _headers(config: ServiceConfig, token: bytes) -> list[tuple[bytes, bytes]]:
    authority = b"127.0.0.1:8765" if config.host == "127.0.0.1" else b"[::1]:8765"
    return [(b"host", authority), (b"authorization", b"Bearer " + token)]


def _scope(
    config: ServiceConfig,
    headers: list[tuple[bytes, bytes]],
    *,
    path: str = _STATUS,
    method: str = "GET",
    query: bytes = b"",
    raw_path: bytes | None = None,
    client: tuple[str, int] | None | bool = True,
) -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "scheme": "http",
        "method": method,
        "root_path": "",
        "path": path,
        "raw_path": path.encode("ascii") if raw_path is None else raw_path,
        "query_string": query,
        "headers": headers,
        "client": (config.host, 12345) if client is True else client,
        "server": (config.host, config.port),
        "state": {},
    }


@dataclass
class Exchange:
    body: bytes = b""
    forbid_receive: bool = False
    receives: int = 0
    messages: list[Message] = field(default_factory=list)

    async def receive(self) -> Message:
        self.receives += 1
        if self.forbid_receive:
            pytest.fail("security rejection must precede receive/body consumption")
        if self.receives == 1:
            return {"type": "http.request", "body": self.body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(self, message: Message) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int:
        starts = [m for m in self.messages if m["type"] == "http.response.start"]
        assert len(starts) == 1, "one response start required"
        return cast(int, starts[0]["status"])

    @property
    def headers(self) -> dict[bytes, bytes]:
        start = next(m for m in self.messages if m["type"] == "http.response.start")
        pairs = cast(list[tuple[bytes, bytes]], start["headers"])
        return {name.lower(): value for name, value in pairs}

    @property
    def payload(self) -> bytes:
        bodies = [m for m in self.messages if m["type"] == "http.response.body"]
        assert bodies and not bodies[-1].get("more_body", False)
        return b"".join(cast(bytes, m.get("body", b"")) for m in bodies)


@dataclass
class Downstream:
    forbidden: bool = False
    calls: int = 0
    fault: Exception | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive
        self.calls += 1
        if self.forbidden:
            pytest.fail("security/routing rejection must precede downstream work")
        if self.fault is not None:
            raise self.fault
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": _PROBE_BODY})


async def _call(gate: ASGIApp, scope: Scope, exchange: Exchange) -> Exchange:
    await gate(scope, exchange.receive, exchange.send)
    return exchange


def _error(exchange: Exchange, status: int, code: str, token: bytes) -> None:
    assert exchange.status == status
    assert json.loads(exchange.payload) == {
        "error": {"source": "request", "code": code}
    }
    assert exchange.headers[b"content-type"].split(b";", 1)[0] == b"application/json"
    assert exchange.headers[b"cache-control"] == b"no-store"
    if status == 401:
        assert exchange.headers[b"www-authenticate"] == b"Bearer"
    assert token not in exchange.payload
    assert (
        b"private-profile" not in exchange.payload
        and b"private-journal" not in exchange.payload
    )


@pytest.mark.parametrize("client", [("127.0.0.2", 1234), ("127.255.255.254", 4321)])
@pytest.mark.asyncio
async def test_selected_ipv4_family_accepts_other_loopback_peers(
    process_credential: Callable[[ServiceConfig], Any], client: tuple[str, int]
) -> None:
    # The contract permits loopback peers of the selected family, not only one IP.
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        downstream = Downstream()
        response = await _call(
            _gate(downstream, config, owner),
            _scope(config, _headers(config, token), client=client),
            Exchange(),
        )
        assert response.status == 200 and downstream.calls == 1


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize(
    "extra",
    [
        [],
        [(b"forwarded", b"host=attacker.example")],
        [
            (b"x-forwarded-host", b"attacker.example"),
            (b"x-forwarded-for", b"198.51.100.1"),
        ],
    ],
    ids=["plain", "forwarded-ignored", "x-forwarded-ignored"],
)
@pytest.mark.asyncio
async def test_no_origin_valid_authority_and_token_reaches_boundary_once(
    process_credential: Callable[[ServiceConfig], Any],
    config: ServiceConfig,
    extra: list[tuple[bytes, bytes]],
) -> None:
    # Break caught: rejecting absent Origin, trusting proxy headers, or duplicating dispatch.
    with process_credential(config) as (owner, token):
        downstream = Downstream()
        gate = _gate(downstream, config, owner)
        response = await _call(
            gate, _scope(config, _headers(config, token) + extra), Exchange()
        )
        assert response.status == 200 and response.payload == _PROBE_BODY
        assert response.headers[b"cache-control"] == b"no-store"
        assert downstream.calls == 1


_BAD_HOSTS = [
    [],
    [(b"host", b"")],
    [(b"host", b"localhost:8765")],
    [(b"host", b"attacker.example:8765")],
    [(b"host", b"127.0.0.1")],
    [(b"host", b"127.0.0.1:8766")],
    [(b"host", b"127.0.0.1:08765")],
    [(b"host", b"127.0.0.1.:8765")],
    [(b"host", b"127.0.0.1:8765 ")],
    [(b"host", b" 127.0.0.1:8765")],
    [(b"host", b"user@127.0.0.1:8765")],
    [(b"host", b"127.0.0.1:8765,attacker.example")],
    [(b"host", b"127.0.0.1:8765.evil")],
    [(b"host", b"::1:8765")],
    [(b"host", b"[::1]")],
    [(b"host", b"[::1]:08765")],
    [(b"host", b"[::ffff:127.0.0.1]:8765")],
    [(b"host", b"[0:0:0:0:0:0:0:1]:8765")],
    [(b"host", b"\xff")],
    [(b"host", b"127.0.0.1:8765"), (b"HOST", b"127.0.0.1:8765")],
    [(b"host", b"attacker.example"), (b"host", b"127.0.0.1:8765")],
]


@pytest.mark.parametrize("host_headers", _BAD_HOSTS)
@pytest.mark.asyncio
async def test_host_rejection_precedes_origin_auth_body_and_preparation(
    process_credential: Callable[[ServiceConfig], Any],
    host_headers: list[tuple[bytes, bytes]],
) -> None:
    # Break caught: weak authority parsing, duplicate collapse or wrong validation order.
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        downstream = Downstream(forbidden=True)
        gate = _gate(downstream, config, owner)
        headers = host_headers + [(b"origin", b"null"), (b"authorization", b"bad")]
        exchange = Exchange(body=_PAYLOAD, forbid_receive=True)
        response = await _call(
            gate, _scope(config, headers, path=_ATTACH, method="POST"), exchange
        )
        _error(response, 400, "host_rejected", token)
        assert downstream.calls == 0 and response.receives == 0


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.asyncio
async def test_opposite_family_host_is_rejected_without_address_fallback(
    process_credential: Callable[[ServiceConfig], Any],
    config: ServiceConfig,
) -> None:
    with process_credential(config) as (owner, token):
        other = b"[::1]:8765" if config.host == "127.0.0.1" else b"127.0.0.1:8765"
        gate = _gate(Downstream(forbidden=True), config, owner)
        response = await _call(
            gate, _scope(config, [(b"host", other)]), Exchange(forbid_receive=True)
        )
        _error(response, 400, "host_rejected", token)


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("name", [b"host", b"HOST", b"HoSt"])
@pytest.mark.asyncio
async def test_header_names_are_case_insensitive_but_values_remain_exact(
    process_credential: Callable[[ServiceConfig], Any],
    config: ServiceConfig,
    name: bytes,
) -> None:
    with process_credential(config) as (owner, token):
        headers = _headers(config, token)
        headers[0] = (name, headers[0][1])
        headers[1] = (b"aUtHoRiZaTiOn", headers[1][1])
        downstream = Downstream()
        response = await _call(
            _gate(downstream, config, owner), _scope(config, headers), Exchange()
        )
        assert response.status == 200 and downstream.calls == 1


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize(
    "client",
    [
        None,
        ("198.51.100.1", 1234),
        ("0.0.0.0", 1234),
        ("::", 1234),
        ("::ffff:127.0.0.1", 1234),
    ],
)
@pytest.mark.asyncio
async def test_peer_rejection_precedes_even_bad_host_and_authorization(
    process_credential: Callable[[ServiceConfig], Any],
    config: ServiceConfig,
    client: tuple[str, int] | None,
) -> None:
    with process_credential(config) as (owner, token):
        gate = _gate(Downstream(forbidden=True), config, owner)
        response = await _call(
            gate, _scope(config, [], client=client), Exchange(forbid_receive=True)
        )
        _error(response, 403, "peer_rejected", token)


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.asyncio
async def test_other_loopback_family_peer_is_rejected(
    process_credential: Callable[[ServiceConfig], Any],
    config: ServiceConfig,
) -> None:
    with process_credential(config) as (owner, token):
        other = "::1" if config.host == "127.0.0.1" else "127.0.0.1"
        gate = _gate(Downstream(forbidden=True), config, owner)
        response = await _call(
            gate,
            _scope(config, _headers(config, token), client=(other, 1234)),
            Exchange(forbid_receive=True),
        )
        _error(response, 403, "peer_rejected", token)


_ORIGINS = [
    [(b"origin", b"")],
    [(b"origin", b"null")],
    [(b"origin", b"http://127.0.0.1:8765")],
    [(b"origin", b"http://[::1]:8765")],
    [(b"origin", b"https://attacker.example")],
    [(b"ORIGIN", b"http://localhost:8765")],
    [(b"origin", b"null"), (b"Origin", b"null")],
    [(b"origin", b"\xff")],
    [(b"sec-fetch-site", b"none")],
    [(b"Sec-Fetch-Mode", b"navigate")],
    [(b"sec-fetch-dest", b"")],
    [(b"SEC-FETCH-custom", b"anything")],
]


@pytest.mark.parametrize("origin_headers", _ORIGINS)
@pytest.mark.parametrize("valid_auth", [False, True])
@pytest.mark.asyncio
async def test_every_origin_or_browser_provenance_rejects_before_auth_and_body(
    process_credential: Callable[[ServiceConfig], Any],
    origin_headers: list[tuple[bytes, bytes]],
    valid_auth: bool,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        headers = _headers(config, token)
        if not valid_auth:
            headers = headers[:1]
        headers += origin_headers
        gate = _gate(Downstream(forbidden=True), config, owner)
        response = await _call(
            gate,
            _scope(config, headers, path=_ATTACH, method="POST"),
            Exchange(body=_PAYLOAD, forbid_receive=True),
        )
        _error(response, 403, "origin_rejected", token)
        assert response.receives == 0


_AUTH_CASES = [
    "missing",
    "empty",
    "lowercase_scheme",
    "other_scheme",
    "two_spaces",
    "leading_space",
    "trailing_space",
    "short",
    "long",
    "uppercase_token",
    "nonhex",
    "nonascii",
    "comma_joined",
    "duplicate_same",
    "duplicate_different",
    "wrong",
]


def _bad_authorization(case: str, token: bytes) -> list[tuple[bytes, bytes]]:
    wrong = (b"0" if token[:1] != b"0" else b"1") + token[1:]
    value = {
        "empty": b"",
        "lowercase_scheme": b"bearer " + token,
        "other_scheme": b"Basic " + token,
        "two_spaces": b"Bearer  " + token,
        "leading_space": b" Bearer " + token,
        "trailing_space": b"Bearer " + token + b" ",
        "short": b"Bearer " + token[:-1],
        "long": b"Bearer " + token + b"0",
        "uppercase_token": b"Bearer " + b"A" * 64,
        "nonhex": b"Bearer " + b"g" * 64,
        "nonascii": b"Bearer " + b"\xff" * 64,
        "comma_joined": b"Bearer " + token + b",Bearer " + token,
        "wrong": b"Bearer " + wrong,
    }
    if case == "missing":
        return []
    if case.startswith("duplicate"):
        second = token if case == "duplicate_same" else wrong
        return [
            (b"authorization", b"Bearer " + token),
            (b"Authorization", b"Bearer " + second),
        ]
    return [(b"authorization", value[case])]


@pytest.mark.parametrize("case", _AUTH_CASES)
@pytest.mark.asyncio
async def test_absent_origin_never_bypasses_exact_bearer_authentication(
    process_credential: Callable[[ServiceConfig], Any],
    case: str,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        headers = _headers(config, token)[:1] + _bad_authorization(case, token)
        gate = _gate(Downstream(forbidden=True), config, owner)
        response = await _call(
            gate,
            _scope(config, headers, path=_ATTACH, method="POST"),
            Exchange(body=_PAYLOAD, forbid_receive=True),
        )
        _error(response, 401, "authentication_required", token)
        assert response.receives == 0


@pytest.mark.parametrize("correct", [False, True])
@pytest.mark.asyncio
async def test_well_formed_tokens_use_constant_time_comparison(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    correct: bool,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        compared: list[tuple[Any, Any]] = []
        original = secrets.compare_digest

        def observed(left: Any, right: Any) -> bool:
            compared.append((left, right))
            return original(left, right)

        headers = _headers(config, token)
        if not correct:
            headers[1:] = _bad_authorization("wrong", token)
        downstream = Downstream(forbidden=not correct)
        gate = _gate(downstream, config, owner)
        with monkeypatch.context() as patch:
            patch.setattr(secrets, "compare_digest", observed)
            response = await _call(
                gate, _scope(config, headers), Exchange(forbid_receive=not correct)
            )
        assert compared, "authentication must use compare_digest, not ordinary equality"
        submitted = headers[1][1][7:]
        pair = compared[-1]

        def encode(value: object) -> bytes:
            if isinstance(value, str):
                return value.encode("ascii")
            assert isinstance(value, (bytes, bytearray, memoryview))
            return bytes(value)

        assert {encode(pair[0]), encode(pair[1])} == {token, submitted}
        if correct:
            assert response.status == 200 and downstream.calls == 1
        else:
            _error(response, 401, "authentication_required", token)


@pytest.mark.parametrize(
    ("path", "method"),
    [
        (_STATUS, "GET"),
        (_ATTACH, "POST"),
        (_DETACH, "POST"),
        ("/docs", "GET"),
        ("/openapi.json", "GET"),
        ("/unknown", "GET"),
        (_STATUS, "HEAD"),
        (_ATTACH, "OPTIONS"),
        (_DETACH, "GET"),
    ],
)
@pytest.mark.parametrize(
    ("gate_fault", "want_status", "want_code"),
    [
        ("host", 400, "host_rejected"),
        ("origin", 403, "origin_rejected"),
        ("auth", 401, "authentication_required"),
    ],
)
@pytest.mark.asyncio
async def test_security_order_applies_to_all_paths_and_methods(
    process_credential: Callable[[ServiceConfig], Any],
    path: str,
    method: str,
    gate_fault: str,
    want_status: int,
    want_code: str,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        headers = _headers(config, token)[:1]
        if gate_fault == "host":
            headers[0] = (b"host", b"attacker.example")
            headers += [(b"origin", b"null")]
        elif gate_fault == "origin":
            headers += [(b"origin", b"null")]
        response = await _call(
            _gate(Downstream(forbidden=True), config, owner),
            _scope(config, headers, path=path, method=method),
            Exchange(body=_PAYLOAD, forbid_receive=True),
        )
        _error(response, want_status, want_code, token)
        assert response.receives == 0


@pytest.mark.parametrize("transport", ["query", "cookie", "body", "environment"])
@pytest.mark.asyncio
async def test_other_credential_transports_cannot_authenticate(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    transport: str,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        headers = _headers(config, token)[:1]
        query = b"token=" + token if transport == "query" else b""
        if transport == "cookie":
            headers += [(b"cookie", b"token=" + token)]
        body = b'{"token":"' + token + b'"}' if transport == "body" else b""
        if transport == "environment":
            monkeypatch.setenv("DUTCHMATE_TOKEN", token.decode("ascii"))
        response = await _call(
            _gate(Downstream(forbidden=True), config, owner),
            _scope(config, headers, path=_ATTACH, method="POST", query=query),
            Exchange(body=body, forbid_receive=True),
        )
        _error(response, 401, "authentication_required", token)


@pytest.mark.asyncio
async def test_authenticated_query_credentials_reject_without_echo_or_preparation(
    process_credential: Callable[[ServiceConfig], Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        gate = _gate(Downstream(forbidden=True), config, owner)
        with caplog.at_level(logging.DEBUG):
            response = await _call(
                gate,
                _scope(config, _headers(config, token), query=b"credential=" + token),
                Exchange(forbid_receive=True),
            )
        _error(response, 400, "query_not_allowed", token)
        assert token.decode("ascii") not in caplog.text
        assert "credential=" not in caplog.text


@pytest.mark.parametrize(
    ("path", "raw_path"),
    [
        ("/docs", b"/docs"),
        ("/redoc", b"/redoc"),
        ("/openapi.json", b"/openapi.json"),
        (_STATUS + "/", (_STATUS + "/").encode()),
        (_ATTACH + "/", (_ATTACH + "/").encode()),
        (_STATUS, b"/v1/%6fbservation/status"),
        (_STATUS, b"http://127.0.0.1:8765/v1/observation/status"),
        (_STATUS, b"/different"),
        ("/different", _STATUS.encode()),
    ],
)
@pytest.mark.asyncio
async def test_exact_routes_exclude_docs_redirects_encoded_aliases_and_absolute_targets(
    process_credential: Callable[[ServiceConfig], Any],
    path: str,
    raw_path: bytes,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        gate = _gate(Downstream(forbidden=True), config, owner)
        response = await _call(
            gate,
            _scope(config, _headers(config, token), path=path, raw_path=raw_path),
            Exchange(forbid_receive=True),
        )
        _error(response, 404, "route_not_found", token)
        assert b"location" not in response.headers


@pytest.mark.parametrize(
    ("path", "method"),
    [
        (_STATUS, "POST"),
        (_STATUS, "HEAD"),
        (_STATUS, "OPTIONS"),
        (_ATTACH, "GET"),
        (_ATTACH, "OPTIONS"),
        (_DETACH, "GET"),
        (_DETACH, "DELETE"),
    ],
)
@pytest.mark.asyncio
async def test_known_route_wrong_method_has_no_head_or_options_bypass(
    process_credential: Callable[[ServiceConfig], Any],
    path: str,
    method: str,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        response = await _call(
            _gate(Downstream(forbidden=True), config, owner),
            _scope(config, _headers(config, token), path=path, method=method),
            Exchange(forbid_receive=True),
        )
        _error(response, 405, "method_not_allowed", token)


@pytest.mark.parametrize("value", [b"websocket", b"", b"h2c"])
@pytest.mark.asyncio
async def test_authenticated_upgrade_rejects_without_bypassing_gate(
    process_credential: Callable[[ServiceConfig], Any],
    value: bytes,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        headers = _headers(config, token) + [
            (b"connection", b"upgrade"),
            (b"Upgrade", value),
        ]
        response = await _call(
            _gate(Downstream(forbidden=True), config, owner),
            _scope(config, headers),
            Exchange(forbid_receive=True),
        )
        _error(response, 400, "upgrade_rejected", token)


@pytest.mark.asyncio
async def test_live_token_is_cached_without_per_request_credential_file_reads(
    process_credential: Callable[[ServiceConfig], Any],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        gate = _gate(Downstream(), config, owner)
        different = (b"0" if token[:1] != b"0" else b"1") + token[1:]
        path = account_home / ".local/state/dutchmate/service/credential"
        path.write_bytes(different + b"\n")

        def no_open(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            pytest.fail("security gate must use the cached process credential")

        with monkeypatch.context() as patch:
            patch.setattr(Path, "open", no_open)
            patch.setattr(os, "open", no_open)
            accepted = await _call(
                gate, _scope(config, _headers(config, token)), Exchange()
            )
            rejected = await _call(
                gate,
                _scope(config, _headers(config, different)),
                Exchange(forbid_receive=True),
            )
        assert accepted.status == 200
        _error(rejected, 401, "authentication_required", token)


@pytest.mark.asyncio
async def test_invalidated_memory_credential_rejects_previous_bearer_token(
    process_credential: Callable[[ServiceConfig], Any],
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        gate = _gate(Downstream(forbidden=True), config, owner)
        owner.invalidate_credential()
        response = await _call(
            gate,
            _scope(config, _headers(config, token)),
            Exchange(forbid_receive=True),
        )
        _error(response, 401, "authentication_required", token)


@pytest.mark.parametrize("fault", ["host", "origin", "auth"])
@pytest.mark.asyncio
async def test_rejection_does_not_log_credential_headers_body_or_url(
    process_credential: Callable[[ServiceConfig], Any],
    caplog: pytest.LogCaptureFixture,
    fault: str,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        headers = _headers(config, token)
        if fault == "host":
            headers[0] = (b"host", b"attacker.example-" + token)
            wanted = (400, "host_rejected")
        elif fault == "origin":
            headers += [(b"origin", b"http://private-origin.example/" + token)]
            wanted = (403, "origin_rejected")
        else:
            headers[1] = (b"authorization", b"Bearer private-invalid-" + token)
            wanted = (401, "authentication_required")
        gate = _gate(Downstream(forbidden=True), config, owner)
        with caplog.at_level(logging.DEBUG):
            response = await _call(
                gate,
                _scope(
                    config,
                    headers,
                    path=_ATTACH,
                    method="POST",
                    query=b"token=" + token,
                ),
                Exchange(body=_PAYLOAD + token, forbid_receive=True),
            )
        _error(response, *wanted, token)
        for private in (
            token.decode("ascii"),
            "attacker.example",
            "private-origin",
            "private-invalid",
            "private-profile",
            "private-journal",
            "token=",
        ):
            assert private not in caplog.text


@pytest.mark.asyncio
async def test_unexpected_downstream_fault_is_normalized_without_traceback_or_input_echo(
    process_credential: Callable[[ServiceConfig], Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        fault = RuntimeError(
            "private-exception " + token.decode("ascii") + " /private/source.toml"
        )
        gate = _gate(Downstream(fault=fault), config, owner)
        with caplog.at_level(logging.DEBUG):
            response = await _call(
                gate, _scope(config, _headers(config, token)), Exchange()
            )
        assert response.status == 500
        assert json.loads(response.payload) == {
            "error": {"source": "service", "code": "internal_failure"}
        }
        assert response.headers[b"cache-control"] == b"no-store"
        for private in (
            token.decode("ascii"),
            "private-exception",
            "/private/source.toml",
            "Traceback",
        ):
            assert (
                private not in response.payload.decode("utf-8")
                and private not in caplog.text
            )


# T009 app/lifespan checks: no attach/detach endpoints, listener or run resources.


def _t009_module() -> Any:
    return importlib.import_module("dutchmate_service.app")


@pytest.mark.asyncio
async def test_t026_framework_telemetry_cannot_emit_input_bearing_delivery_errors(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opentelemetry import _logs
    from opentelemetry._logs import _internal

    emitted: list[dict[str, Any]] = []

    class RecordingLogger(_logs.Logger):
        def enabled(self, *, context: Any = None, severity_number: Any = None,
                    event_name: str | None = None) -> bool:
            return True

        def emit(self, record: Any = None, **kwargs: Any) -> None:
            del record
            emitted.append(kwargs)

    class RecordingProvider(_logs.LoggerProvider):
        def get_logger(
            self, name: str, version: str | None = None,
            schema_url: str | None = None, attributes: Any = None,
        ) -> _logs.Logger:
            return RecordingLogger(name, version, schema_url, attributes)

    provider = RecordingProvider()
    # Install the API's actual ambient provider slot, as a configured process
    # does. Patching only the re-exported getter would leave get_logger() using
    # the internal no-op provider and conceal the input-bearing emission.
    monkeypatch.setattr(_internal, "_LOGGER_PROVIDER", provider)
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        app = _t009_app(config, owner)
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        exchange = Exchange()

        async def failed_send(message: Message) -> None:
            del message
            raise OSError("supplied-private-path-and-credential-detail")

        try:
            with pytest.raises(RuntimeError, match="^service/internal_failure$"):
                await app(_scope(config, _headers(config, token)), exchange.receive, failed_send)
            assert emitted == [], "framework logger inherited ambient input-bearing telemetry"
        finally:
            await lifespan.finish()


def _t009_app(config: ServiceConfig, owner: PrivateBootstrap | None = None) -> ASGIApp:
    module = _t009_module()
    context = None if owner is None else module._LaunchContext(config, owner)
    return cast(ASGIApp, module.create_app(config, _launch_context=context))


@dataclass
class AppLifespan:
    app: ASGIApp
    incoming: asyncio.Queue[Message] = field(default_factory=asyncio.Queue)
    outgoing: asyncio.Queue[Message] = field(default_factory=asyncio.Queue)
    task: asyncio.Task[None] | None = None

    async def start(self) -> Message:
        async def serve() -> None:
            await self.app(
                {
                    "type": "lifespan",
                    "asgi": {"version": "3.0", "spec_version": "2.0"},
                    "state": {},
                },
                self.incoming.get,
                self.outgoing.put,
            )

        self.task = asyncio.create_task(serve())
        await self.incoming.put({"type": "lifespan.startup"})
        return await asyncio.wait_for(self.outgoing.get(), timeout=3.0)

    async def finish(self) -> None:
        assert self.task is not None
        if not self.task.done():
            await self.incoming.put({"type": "lifespan.shutdown"})
            message = await asyncio.wait_for(self.outgoing.get(), timeout=3.0)
            assert message["type"] == "lifespan.shutdown.complete"
        await asyncio.wait_for(self.task, timeout=3.0)


def _t009_runtime_spy(
    module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[ObservationRuntime], list[tuple[asyncio.AbstractEventLoop, int]]]:
    instances: list[ObservationRuntime] = []
    contexts: list[tuple[asyncio.AbstractEventLoop, int]] = []

    class RecordedRuntime(ObservationRuntime):
        def __init__(self) -> None:
            contexts.append((asyncio.get_running_loop(), get_ident()))
            super().__init__()
            instances.append(self)

    monkeypatch.setattr(module, "ObservationRuntime", RecordedRuntime)
    return instances, contexts


@pytest.mark.parametrize("path", ["/v1/observation/attach", "/v1/observation/detach"])
@pytest.mark.asyncio
async def test_t022_latched_stop_closes_mutations_before_profile_or_preparation(
    process_credential: Callable[[ServiceConfig], Any],
    path: str,
) -> None:
    module = _t009_module()
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        context = module._LaunchContext(config, owner)
        app = module.create_app(config, _launch_context=context)
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        try:
            for _ in range(3):
                context.request_stop()
            response = Exchange(body=(
                b'{"profile_path":"/explicit/test-profile.toml",'
                b'"journal_path":"/explicit/test-journal.sqlite3"}'
                if path.endswith("attach") else b""
            ))
            # The outer gate retains security/route/body validation precedence.
            await app(_scope(config, _headers(config, token) + [(b"content-type", b"application/json")], path=path, method="POST"),
                      response.receive, response.send)
            assert response.status == 503 and response.receives == 1
            assert json.loads(response.payload) == {"error": {"source": "service", "code": "stopping"}}
            assert context.stopping is True
        finally:
            await lifespan.finish()


@pytest.mark.parametrize("with_context", [False, True])
@pytest.mark.asyncio
async def test_t009_factory_has_no_runtime_bootstrap_or_listener_side_effects(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    with_context: bool,
) -> None:
    import socket

    module = _t009_module()
    created, _ = _t009_runtime_spy(module, monkeypatch)
    config = _CONFIGS[0]
    with process_credential(config) as (owner, _):
        context = module._LaunchContext(config, owner) if with_context else None

        def forbidden(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            pytest.fail(
                "T009 factory cannot bootstrap resources or construct a listener"
            )

        with monkeypatch.context() as patch:
            patch.setattr(PrivateBootstrap, "acquire", forbidden)
            patch.setattr(os, "open", forbidden)
            patch.setattr(socket, "socket", forbidden)
            result = module.create_app(config, _launch_context=context)
        assert callable(result) and created == []


@pytest.mark.asyncio
async def test_t009_uncontrolled_lifespan_rejects_before_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _t009_module()
    created, _ = _t009_runtime_spy(module, monkeypatch)
    lifespan = AppLifespan(_t009_app(_CONFIGS[0]))
    message = await lifespan.start()
    assert message["type"] == "lifespan.startup.failed"
    assert "invalid_configuration" in message["message"]
    assert lifespan.task is not None
    result = await asyncio.gather(lifespan.task, return_exceptions=True)
    assert isinstance(result[0], BootstrapFailure)
    assert result[0].kind == BootstrapFailureKind.INVALID_CONFIGURATION
    assert created == []


@pytest.mark.parametrize("stage", ["acquired", "marked", "invalidated"])
@pytest.mark.asyncio
async def test_t009_unprepared_credential_rejects_before_runtime(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    del account_home
    module = _t009_module()
    created, _ = _t009_runtime_spy(module, monkeypatch)
    config = _CONFIGS[0]
    owner = PrivateBootstrap.acquire(config)
    try:
        if stage != "acquired":
            owner.mark_unconfirmed()
        if stage == "invalidated":
            owner.publish_credential()
            owner.invalidate_credential()
        app = _t009_app(config, owner)
        lifespan = AppLifespan(app)
        message = await lifespan.start()
        assert message["type"] == "lifespan.startup.failed"
        assert "invalid_configuration" in message["message"]
        assert lifespan.task is not None
        result = await asyncio.gather(lifespan.task, return_exceptions=True)
        assert isinstance(result[0], BootstrapFailure) and created == []
        if stage != "acquired":
            owner.confirm_cleanup(
                owner_settled=True,
                physical_release_confirmed=True,
                recorder_close_confirmed=True,
            )
    finally:
        owner.release()


@pytest.mark.parametrize("different", [ServiceConfig(8766), ServiceConfig(8765, "::1")])
@pytest.mark.asyncio
async def test_t009_launch_config_mismatch_rejects_before_runtime(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    different: ServiceConfig,
) -> None:
    module = _t009_module()
    created, _ = _t009_runtime_spy(module, monkeypatch)
    config = _CONFIGS[0]
    with process_credential(config) as (owner, _):
        context = module._LaunchContext(config, owner)
        app = cast(ASGIApp, module.create_app(different, _launch_context=context))
        lifespan = AppLifespan(app)
        message = await lifespan.start()
        assert message["type"] == "lifespan.startup.failed"
        assert lifespan.task is not None
        result = await asyncio.gather(lifespan.task, return_exceptions=True)
        assert isinstance(result[0], BootstrapFailure) and created == []


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.asyncio
async def test_t009_async_lifespan_creates_one_runtime_after_prepared_bootstrap(
    process_credential: Callable[[ServiceConfig], Any],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
) -> None:
    module = _t009_module()
    created, contexts = _t009_runtime_spy(module, monkeypatch)
    with process_credential(config) as (owner, token):
        root = account_home / ".local/state/dutchmate/service"
        assert (
            json.loads((root / "owner.json").read_bytes())["cleanup_confirmed"] is False
        )
        app = _t009_app(config, owner)
        assert created == []
        lifespan = AppLifespan(app)
        try:
            assert (await lifespan.start())["type"] == "lifespan.startup.complete"
            assert len(created) == 1
            assert contexts == [(asyncio.get_running_loop(), get_ident())]
            for _ in range(3):
                response = await _call(
                    app, _scope(config, _headers(config, token)), Exchange()
                )
                assert response.status == 200
                assert json.loads(response.payload) == {
                    "service_state": "ready",
                    "runtime": {
                        "state": "inactive",
                        "run_id": None,
                        "profile": None,
                        "session_id": None,
                        "acquisition": None,
                        "stop_intent": "none",
                        "terminal_reason": None,
                        "primary_issue": None,
                        "cleanup_issues": [],
                        "owner_settled": True,
                        "physical_release_confirmed": True,
                        "recorder_close_confirmed": True,
                        "attach_admissible": True,
                    },
                }
                assert response.headers[b"cache-control"] == b"no-store"
            assert len(created) == 1
        finally:
            await lifespan.finish()
        assert owner.credential is not None
        assert (
            json.loads((root / "owner.json").read_bytes())["cleanup_confirmed"] is False
        )


# T011: lifecycle wiring RED; no service operation registry/cancellation tests.

_T011_PROFILE = """profile_version = 1
[dut]
id = "fixture/t011"
name = "HTTP observation fixture"
[backend]
kind = "basic_serial"
expected_device = "/dev/t011-fixture-only"
[uart]
baud_rate = 19200
data_bits = 7
parity = "even"
stop_bits = 2
hardware_flow_control = false
software_flow_control = true
[uart.open_lines]
dtr = "deasserted"
rts = "deasserted"
[persistence]
max_retained_records = 100
max_retained_charged_bytes = 65536
max_record_charged_bytes = 8192
max_database_pages = 128
max_retrieval_page_records = 11
max_retrieval_page_charged_bytes = 16384
"""


@dataclass
class _T011Read:
    stream: BinaryIO
    path: Path
    reads: list[tuple[Path, int]]

    def __enter__(self) -> _T011Read:
        return self

    def __exit__(self, *args: object) -> None:
        self.stream.close()

    def read(self, size: int = -1) -> bytes:
        self.reads.append((self.path, size))
        return self.stream.read(size)


@dataclass
class _T011Composition:
    profile_path: Path
    journal_path: Path
    reads: list[tuple[Path, int]] = field(default_factory=list)
    destinations: list[Path] = field(default_factory=list)
    journals: list[sqlite_evidence.SqliteEvidenceJournal] = field(default_factory=list)
    serials: list[Any] = field(default_factory=list)
    close_error: OSError | None = None
    open_error: OSError | None = None


@pytest.fixture
def t011_composition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _T011Composition:
    # Reuse the existing strict serial dependency fixture without adding an
    # undeclared import path or relying on Core test collection happening first.
    source = (
        Path(__file__).parents[3] / "core/tests/contract/test_basic_serial_adapter.py"
    )
    spec = importlib.util.spec_from_file_location("_t011_serial_fixtures", source)
    assert spec is not None and spec.loader is not None
    serial_fixtures = cast(Any, importlib.util.module_from_spec(spec))
    spec.loader.exec_module(serial_fixtures)
    state = _T011Composition(
        tmp_path / "explicit-profile.toml", tmp_path / "fresh.sqlite3"
    )
    state.profile_path.write_text(_T011_PROFILE, encoding="utf-8")
    original_init = basic_serial.BasicSerialBackend.__init__
    original_create = sqlite_evidence.SqliteEvidenceJournal.create_v2
    original_create_v1 = sqlite_evidence.SqliteEvidenceJournal.create
    original_path_open = Path.open

    def construct(
        self: basic_serial.BasicSerialBackend,
        selector: basic_serial.SerialDeviceSelector,
        configuration: basic_serial.SerialConfiguration,
        line_intent: basic_serial.SerialOpenLineIntent,
    ) -> None:
        gate = Event()
        fake = serial_fixtures.FakeSerial(
            read_results=(b"",),
            read_gates=(gate,),
            open_error=state.open_error,
            close_error=state.close_error,
        )
        original_cancel = fake.cancel_read

        def cancel() -> None:
            original_cancel()
            gate.set()

        fake.cancel_read = cancel
        factory = serial_fixtures.FakeSerialFactory(fake)
        state.serials.append(fake)
        original_init(
            self, selector, configuration, line_intent, _serial_factory=factory
        )

    async def create(
        cls: type[sqlite_evidence.SqliteEvidenceJournal],
        path: str | Path,
        session_policy: SessionPolicy,
    ) -> sqlite_evidence.SqliteEvidenceJournal:
        del cls
        state.destinations.append(Path(path))
        journal = await original_create(path, session_policy)
        state.journals.append(journal)
        return journal

    async def create_v1(
        cls: type[sqlite_evidence.SqliteEvidenceJournal],
        path: str | Path,
        session_policy: SessionPolicy,
    ) -> sqlite_evidence.SqliteEvidenceJournal:
        # Explicit custom preparations below still exercise the unchanged v1 API.
        del cls
        state.destinations.append(Path(path))
        journal = await original_create_v1(path, session_policy)
        state.journals.append(journal)
        return journal

    def opened(path: Path, *args: Any, **kwargs: Any) -> Any:
        stream = original_path_open(path, *args, **kwargs)
        if path.suffix == ".toml" and args and args[0] == "rb":
            return _T011Read(cast(BinaryIO, stream), path, state.reads)
        return stream

    def no_reopen(*args: object, **kwargs: object) -> Any:
        del args, kwargs
        pytest.fail(
            "HTTP attach must create fresh journals, never reopen existing ones"
        )

    monkeypatch.setattr(basic_serial.BasicSerialBackend, "__init__", construct)
    monkeypatch.setattr(
        sqlite_evidence.SqliteEvidenceJournal, "create_v2", classmethod(create)
    )
    monkeypatch.setattr(
        sqlite_evidence.SqliteEvidenceJournal, "create", classmethod(create_v1)
    )
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "open", no_reopen)
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "open_v2", no_reopen)
    monkeypatch.setattr(Path, "open", opened)
    return state


@dataclass
class _T011Service:
    app: ASGIApp
    runtime: ObservationRuntime
    config: ServiceConfig
    token: bytes = field(repr=False)

    async def request(
        self, path: str, method: str, body: bytes = b"", *, query: bytes = b""
    ) -> Exchange:
        return await _call(
            self.app,
            _scope(
                self.config,
                _headers(self.config, self.token)
                + [(b"content-type", b"application/json")],
                path=path,
                method=method,
                query=query,
            ),
            _T011ConnectedExchange(body=body),
        )


class _T011ConnectedExchange(Exchange):
    """Normal request remains connected after its body, without a fake disconnect."""

    async def receive(self) -> Message:
        if self.receives == 0:
            return await super().receive()
        pending: asyncio.Future[Message] = asyncio.get_running_loop().create_future()
        return await pending


@asynccontextmanager
async def _t011_service(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    composition: _T011Composition,
    config: ServiceConfig = _CONFIGS[0],
) -> AsyncIterator[_T011Service]:
    created, _ = _t009_runtime_spy(_t009_module(), monkeypatch)
    owner = PrivateBootstrap.acquire(config)
    lifespan: AppLifespan | None = None
    try:
        owner.mark_unconfirmed()
        owner.publish_credential()
        token = (
            account_home / ".local/state/dutchmate/service/credential"
        ).read_bytes()[:-1]
        app = _t009_app(config, owner)
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        assert len(created) == 1
        yield _T011Service(app, created[0], config, token)
    finally:
        if created:
            # Test-only fallback cleanup when a RED assertion skips HTTP detach.
            # Keep each gated fake read blocked until the real close cancels it.
            settled = await asyncio.wait_for(created[0].detach(), timeout=3.0)
        else:
            settled = RuntimeStatus()
        if lifespan is not None:
            await lifespan.finish()
        owner.invalidate_credential()
        if settled.attach_admissible:
            owner.confirm_cleanup(
                owner_settled=settled.owner_settled,
                physical_release_confirmed=settled.physical_release_confirmed,
                recorder_close_confirmed=settled.recorder_close_confirmed,
            )
        owner.release()
        assert len(created) <= 1
        assert all(fake.active_reads == 0 for fake in composition.serials)


def _t011_body(profile: Path, journal: Path) -> bytes:
    return json.dumps(
        {"profile_path": str(profile), "journal_path": str(journal)}
    ).encode()


def _t011_view(response: Exchange, state: str) -> dict[str, Any]:
    assert response.status == 200
    assert response.headers[b"cache-control"] == b"no-store"
    assert response.headers[b"content-type"].split(b";")[0] == b"application/json"
    document = json.loads(response.payload)
    assert set(document) == {"service_state", "runtime"}
    assert document["service_state"] == "ready"
    runtime = cast(dict[str, Any], document["runtime"])
    assert set(runtime) == {
        "state",
        "run_id",
        "profile",
        "session_id",
        "acquisition",
        "stop_intent",
        "terminal_reason",
        "primary_issue",
        "cleanup_issues",
        "owner_settled",
        "physical_release_confirmed",
        "recorder_close_confirmed",
        "attach_admissible",
    }
    assert runtime["state"] == state
    return runtime


def _t011_error(response: Exchange, code: int, source: str, kind: str) -> None:
    assert response.status == code
    assert json.loads(response.payload) == {"error": {"source": source, "code": kind}}
    assert response.headers[b"cache-control"] == b"no-store"
    assert response.headers[b"content-type"].split(b";")[0] == b"application/json"


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.asyncio
async def test_t011_http_attach_status_detach_preserves_one_runtime_and_captured_profile(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    config: ServiceConfig,
) -> None:
    c = t011_composition
    async with _t011_service(account_home, monkeypatch, c, config) as service:
        response = await service.request(
            _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
        )
        active = _t011_view(response, "active")
        actual = service.runtime.status()
        assert actual.run_id is not None and actual.session_id is not None
        assert active["run_id"] == actual.run_id.value
        assert (
            active["session_id"]
            == actual.session_id.value
            == c.journals[0].session_id.value
        )
        assert active["profile"]["dut"] == {
            "id": "fixture/t011",
            "name": "HTTP observation fixture",
        }
        assert active["primary_issue"] is None and active["cleanup_issues"] == []
        assert active["owner_settled"] is False and active["attach_admissible"] is False
        assert c.destinations == [c.journal_path] and len(c.serials) == 1
        fake = c.serials[0]
        assert fake.port == "/dev/t011-fixture-only"
        assert (fake.baudrate, fake.bytesize, fake.parity, fake.stopbits) == (
            19200,
            7,
            "E",
            2,
        )
        assert fake.rtscts is False and fake.xonxoff is True
        assert c.reads == [(c.profile_path, 65537)]
        c.profile_path.write_text("invalid changed Profile", encoding="utf-8")
        assert _t011_view(await service.request(_STATUS, "GET"), "active") == active
        terminal = _t011_view(await service.request(_DETACH, "POST"), "terminated")
        assert (
            terminal["run_id"] == active["run_id"]
            and terminal["session_id"] == active["session_id"]
        )
        assert terminal["profile"] == active["profile"]
        assert (
            terminal["terminal_reason"] == "detached"
            and terminal["stop_intent"] == "detach"
        )
        assert terminal["owner_settled"] and terminal["physical_release_confirmed"]
        assert terminal["recorder_close_confirmed"] and terminal["attach_admissible"]
        assert fake.close_calls == 1 and fake.active_reads == 0
        assert (
            _t011_view(await service.request(_DETACH, "POST"), "terminated") == terminal
        )
        assert (
            _t011_view(await service.request(_STATUS, "GET"), "terminated") == terminal
        )
        assert fake.close_calls == 1 and c.reads == [(c.profile_path, 65537)]
        assert c.journal_path.is_file()


@pytest.mark.asyncio
async def test_t011_detach_inactive_is_idempotent_without_profile_or_resource_work(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    async with _t011_service(account_home, monkeypatch, t011_composition) as service:
        for _ in range(2):
            view = _t011_view(await service.request(_DETACH, "POST"), "inactive")
            assert (
                view["run_id"] is None
                and view["session_id"] is None
                and view["profile"] is None
            )
            assert view["attach_admissible"] is True
        assert t011_composition.reads == [] and t011_composition.destinations == []
        assert t011_composition.serials == []


@pytest.mark.parametrize("kind", list(ProfileFailureKind), ids=lambda kind: kind.value)
@pytest.mark.asyncio
async def test_t011_profile_failures_map_422_before_runtime_admission_or_preparation(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    kind: ProfileFailureKind,
    caplog: pytest.LogCaptureFixture,
) -> None:
    c = t011_composition
    if kind is ProfileFailureKind.MISSING_FILE:
        c.profile_path.unlink()
    elif kind is ProfileFailureKind.NOT_A_FILE:
        c.profile_path.unlink()
        c.profile_path.mkdir()
    elif kind is ProfileFailureKind.UNREADABLE:
        original_stat = Path.stat

        def unreadable(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
            if path == c.profile_path:
                raise PermissionError("private permission detail")
            return original_stat(path, follow_symlinks=follow_symlinks)

        monkeypatch.setattr(Path, "stat", unreadable)
    else:
        contents = {
            ProfileFailureKind.INPUT_TOO_LARGE: "#" + "x" * 65536,
            ProfileFailureKind.INVALID_SYNTAX: "private malformed = [",
            ProfileFailureKind.INCOMPATIBLE_VERSION: _T011_PROFILE.replace(
                "profile_version = 1", "profile_version = 2"
            ),
            ProfileFailureKind.MISSING_FIELD: _T011_PROFILE.replace(
                'name = "HTTP observation fixture"\n', ""
            ),
            ProfileFailureKind.UNKNOWN_FIELD: _T011_PROFILE + "private_unknown = 1\n",
            ProfileFailureKind.INVALID_VALUE: _T011_PROFILE.replace(
                "baud_rate = 19200", "baud_rate = -1"
            ),
            ProfileFailureKind.UNSUPPORTED_BACKEND: _T011_PROFILE.replace(
                'kind = "basic_serial"', 'kind = "enhanced"'
            ),
            ProfileFailureKind.UNSUPPORTED_BEHAVIOR: _T011_PROFILE
            + "[tx]\nenabled = true\n",
        }[kind]
        c.profile_path.write_text(contents, encoding="utf-8")
    # Check the fixture against the actual resolver, so a missing HTTP route
    # cannot conceal a typo in the intended Profile failure precondition.
    with pytest.raises(ProfileFailure) as precondition:
        resolve_profile(c.profile_path)
    assert precondition.value.kind is kind
    c.reads.clear()
    async with _t011_service(account_home, monkeypatch, c) as service:
        before = service.runtime.status()
        with caplog.at_level(logging.DEBUG):
            response = await service.request(
                _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
            )
        _t011_error(response, 422, "profile", kind.value)
        assert service.runtime.status() == before
        assert c.destinations == [] and c.serials == [] and not c.journal_path.exists()
        assert str(c.profile_path) not in response.payload.decode() + caplog.text
        assert "private permission detail" not in caplog.text


@pytest.mark.parametrize(
    "invalid_profile", [False, True], ids=["busy", "profile-before-busy"]
)
@pytest.mark.asyncio
async def test_t011_busy_basic_edge_reads_only_bounded_explicit_profile_without_preparation(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    invalid_profile: bool,
) -> None:
    c = t011_composition
    async with _t011_service(account_home, monkeypatch, c) as service:
        before = await observation_runtime.attach_basic_observation(
            service.runtime, c.profile_path, c.journal_path
        )
        assert before.state is RuntimeState.ACTIVE
        destination = c.journal_path.with_name("busy-no-preparation.sqlite3")
        c.reads.clear()
        if invalid_profile:
            c.profile_path.write_text("bad = [", encoding="utf-8")

        def forbidden(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            pytest.fail("busy attach must not prepare or probe run resources")

        original_stat = Path.stat

        def stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
            if path == destination:
                forbidden()
            return original_stat(path, follow_symlinks=follow_symlinks)

        with monkeypatch.context() as patch:
            patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "create", forbidden)
            patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "create_v2", forbidden)
            patch.setattr(basic_serial.BasicSerialBackend, "__init__", forbidden)
            patch.setattr(basic_serial.BasicSerialBackend, "open", forbidden)
            patch.setattr(Path, "stat", stat)
            response = await service.request(
                _ATTACH, "POST", _t011_body(c.profile_path, destination)
            )
        _t011_error(
            response,
            422 if invalid_profile else 409,
            "profile" if invalid_profile else "runtime",
            "invalid_syntax" if invalid_profile else "busy",
        )
        assert c.reads == [(c.profile_path, 65537)]
        assert c.destinations == [c.journal_path] and len(c.serials) == 1
        assert service.runtime.status() == before and not destination.exists()


@pytest.mark.asyncio
async def test_t011_uncertain_runtime_cleanup_blocks_attach_409_without_second_open_or_close(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    c = t011_composition
    c.close_error = OSError("private simulated physical-close failure")
    async with _t011_service(account_home, monkeypatch, c) as service:
        await observation_runtime.attach_basic_observation(
            service.runtime, c.profile_path, c.journal_path
        )
        failed = await service.runtime.detach()
        assert (
            failed.state is RuntimeState.FAILED
            and not failed.physical_release_confirmed
        )
        destination = c.journal_path.with_name("uncertain-no-preparation.sqlite3")
        response = await service.request(
            _ATTACH, "POST", _t011_body(c.profile_path, destination)
        )
        _t011_error(response, 409, "runtime", "cleanup_unconfirmed")
        assert service.runtime.status() == failed
        assert c.destinations == [c.journal_path] and len(c.serials) == 1
        assert c.serials[0].close_calls == 1 and not destination.exists()
    assert (
        json.loads(
            (account_home / ".local/state/dutchmate/service/owner.json").read_bytes()
        )["cleanup_confirmed"]
        is False
    )


@pytest.mark.asyncio
async def test_t011_backend_start_failure_is_http_200_failed_with_retained_journal(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    c = t011_composition
    c.open_error = OSError("private simulated open failure")
    async with _t011_service(account_home, monkeypatch, c) as service:
        failed = _t011_view(
            await service.request(
                _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
            ),
            "failed",
        )
        assert failed["terminal_reason"] == "startup_failure"
        assert failed["primary_issue"] == {
            "source": "acquisition_start",
            "code": "transport_failure",
        }
        assert failed["cleanup_issues"] == [] and failed["attach_admissible"] is False
        # Feature-005's failed-open contract leaves physical release unconfirmed
        # even when recorder close succeeded and no close failure is reported.
        assert failed["owner_settled"] is True
        assert failed["physical_release_confirmed"] is False
        assert failed["recorder_close_confirmed"] is True
        assert failed["acquisition"]["primary_failure_kind"] == "transport_failure"
        assert failed["acquisition"]["close_failed"] is False
        assert failed["session_id"] == c.journals[0].session_id.value
        assert c.journal_path.exists()
        assert _t011_view(await service.request(_STATUS, "GET"), "failed") == failed


@pytest.mark.asyncio
async def test_t011_reattach_uses_fresh_destination_session_and_run_without_reopen_or_overwrite(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
) -> None:
    c = t011_composition
    async with _t011_service(account_home, monkeypatch, c) as service:
        first = _t011_view(
            await service.request(
                _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
            ),
            "active",
        )
        _t011_view(await service.request(_DETACH, "POST"), "terminated")
        previous_bytes = c.journal_path.read_bytes()
        collision = _t011_view(
            await service.request(
                _ATTACH, "POST", _t011_body(c.profile_path, c.journal_path)
            ),
            "failed",
        )
        assert collision["primary_issue"] == {
            "source": "preparation",
            "code": "journal_exists",
        }
        assert (
            collision["session_id"] is None and collision["attach_admissible"] is True
        )
        assert c.journal_path.read_bytes() == previous_bytes
        assert len(c.serials) == 1 and len(c.journals) == 1
        fresh = c.journal_path.with_name("second-fresh.sqlite3")
        second = _t011_view(
            await service.request(_ATTACH, "POST", _t011_body(c.profile_path, fresh)),
            "active",
        )
        assert (
            second["run_id"] != first["run_id"]
            and second["session_id"] != first["session_id"]
        )
        assert c.destinations == [c.journal_path, c.journal_path, fresh]
        assert len(c.serials) == len(c.journals) == 2
        _t011_view(await service.request(_DETACH, "POST"), "terminated")
        assert c.journal_path.read_bytes() == previous_bytes and fresh.is_file()


@pytest.mark.parametrize("literal", ["trailing space ", "~/${T011_PROFILE}"])
@pytest.mark.asyncio
async def test_t011_explicit_profile_and_destination_paths_are_not_expanded_or_stripped(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    literal: str,
) -> None:
    c = t011_composition
    selected = c.profile_path.parent / literal / "selected.toml"
    selected.parent.mkdir(parents=True)
    selected.write_text(_T011_PROFILE, encoding="utf-8")
    destination = selected.with_name("fresh journal.sqlite3")
    monkeypatch.setenv("T011_PROFILE", "must-not-expand")
    async with _t011_service(account_home, monkeypatch, c) as service:
        view = _t011_view(
            await service.request(_ATTACH, "POST", _t011_body(selected, destination)),
            "active",
        )
        assert view["profile"]["dut"]["id"] == "fixture/t011"
        assert c.reads == [(selected, 65537)] and c.destinations == [destination]
        _t011_view(await service.request(_DETACH, "POST"), "terminated")
        assert destination.exists() and not c.journal_path.exists()


@pytest.mark.parametrize("state", list(RuntimeState), ids=lambda state: state.value)
@pytest.mark.asyncio
async def test_t011_every_returned_core_status_maps_200_without_assuming_active_capture(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    state: RuntimeState,
) -> None:
    resolved = resolve_profile(t011_composition.profile_path)
    if state is RuntimeState.INACTIVE:
        returned = RuntimeStatus()
    else:
        terminal = state in {RuntimeState.FAILED, RuntimeState.TERMINATED}
        returned = RuntimeStatus(
            state=state,
            run_id=RunId("returned-run"),
            profile=resolved,
            session_id=SessionId("returned-session"),
            owner_settled=terminal,
            physical_release_confirmed=terminal,
            recorder_close_confirmed=terminal,
            terminal_reason=(
                RuntimeTerminalReason.STARTUP_FAILURE
                if state is RuntimeState.FAILED
                else RuntimeTerminalReason.DISCONNECTED
                if terminal
                else None
            ),
            primary_issue=RuntimeIssue(
                RuntimeIssueSource.PREPARATION, ProfileFailureKind.INVALID_VALUE
            )
            if state is RuntimeState.FAILED
            else None,
        )
    calls: list[tuple[ObservationRuntime, str | Path, str | Path]] = []

    async def returned_call(
        runtime: ObservationRuntime, profile: str | Path, journal: str | Path
    ) -> RuntimeStatus:
        calls.append((runtime, profile, journal))
        return returned

    monkeypatch.setattr(observation_runtime, "attach_basic_observation", returned_call)
    module = _t009_module()
    if hasattr(module, "attach_basic_observation"):
        monkeypatch.setattr(module, "attach_basic_observation", returned_call)
    async with _t011_service(account_home, monkeypatch, t011_composition) as service:
        response = await service.request(
            _ATTACH,
            "POST",
            _t011_body(t011_composition.profile_path, t011_composition.journal_path),
        )
        view = _t011_view(response, state.value)
        assert len(calls) == 1 and calls[0][0] is service.runtime
        assert Path(calls[0][1]) == t011_composition.profile_path
        assert Path(calls[0][2]) == t011_composition.journal_path
        assert view["run_id"] == (
            None if returned.run_id is None else returned.run_id.value
        )
        assert view["session_id"] == (
            None if returned.session_id is None else returned.session_id.value
        )
        assert view["owner_settled"] is returned.owner_settled
        assert view["physical_release_confirmed"] is returned.physical_release_confirmed
        assert view["recorder_close_confirmed"] is returned.recorder_close_confirmed
        assert view["attach_admissible"] is returned.attach_admissible
        assert view["terminal_reason"] == (
            None if returned.terminal_reason is None else returned.terminal_reason.value
        )
        assert view["primary_issue"] == (
            {"source": "preparation", "code": "invalid_value"}
            if state is RuntimeState.FAILED
            else None
        )


@pytest.mark.parametrize(
    ("path", "method"),
    [
        (_ATTACH, "GET"),
        (_DETACH, "GET"),
        (_STATUS, "POST"),
        (_ATTACH + "/", "POST"),
        (_DETACH + "/", "POST"),
    ],
)
@pytest.mark.asyncio
async def test_t011_actual_http_surface_rejects_method_and_path_aliases_before_profile(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    path: str,
    method: str,
) -> None:
    async with _t011_service(account_home, monkeypatch, t011_composition) as service:
        response = await service.request(path, method)
        alias = path.endswith("/")
        _t011_error(
            response,
            404 if alias else 405,
            "request",
            "route_not_found" if alias else "method_not_allowed",
        )
        assert t011_composition.reads == [] and t011_composition.destinations == []
        assert t011_composition.serials == []


@pytest.mark.parametrize("missing", ["profile_path", "journal_path", "both"])
@pytest.mark.asyncio
async def test_t011_attach_requires_both_explicit_paths_without_defaults(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    missing: str,
) -> None:
    body = {
        "profile_path": str(t011_composition.profile_path),
        "journal_path": str(t011_composition.journal_path),
    }
    if missing == "both":
        body.clear()
    else:
        del body[missing]
    async with _t011_service(account_home, monkeypatch, t011_composition) as service:
        _t011_error(
            await service.request(_ATTACH, "POST", json.dumps(body).encode()),
            422,
            "request",
            "invalid_request",
        )
        assert t011_composition.reads == [] and t011_composition.destinations == []
        assert t011_composition.serials == []


@pytest.mark.parametrize(
    ("path", "method"), [(_ATTACH, "POST"), (_STATUS, "GET"), (_DETACH, "POST")]
)
@pytest.mark.asyncio
async def test_t011_lifecycle_routes_reject_query_before_profile_or_run_preparation(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    path: str,
    method: str,
) -> None:
    async with _t011_service(account_home, monkeypatch, t011_composition) as service:
        response = await service.request(
            path, method, query=b"profile_path=/must-not-read"
        )
        _t011_error(response, 400, "request", "query_not_allowed")
        assert t011_composition.reads == [] and t011_composition.destinations == []
        assert t011_composition.serials == []


@pytest.mark.parametrize("path", [_ATTACH, _DETACH], ids=["attach", "detach"])
@pytest.mark.parametrize(
    "other_thread", [False, True], ids=["foreign-loop", "foreign-thread"]
)
def test_t011_mutation_wrong_context_maps_500_before_profile_or_resource_work(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    path: str,
    other_thread: bool,
) -> None:
    with asyncio.Runner() as owner_runner:
        context = _t011_service(account_home, monkeypatch, t011_composition)
        service = owner_runner.run(context.__aenter__())

        async def snapshot() -> RuntimeStatus:
            return service.runtime.status()

        before = owner_runner.run(snapshot())
        body = (
            _t011_body(t011_composition.profile_path, t011_composition.journal_path)
            if path == _ATTACH
            else b""
        )

        async def query() -> Exchange:
            return await service.request(path, "POST", body)

        try:
            if other_thread:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    response = executor.submit(lambda: asyncio.run(query())).result(
                        timeout=3.0
                    )
            else:
                with asyncio.Runner() as foreign_runner:
                    response = foreign_runner.run(query())
            _t011_error(response, 500, "runtime", "wrong_execution_context")
            assert owner_runner.run(snapshot()) == before
            assert t011_composition.reads == [] and t011_composition.destinations == []
            assert t011_composition.serials == []
        finally:
            owner_runner.run(context.__aexit__(None, None, None))


@pytest.mark.parametrize(
    "unexpected",
    [False, True],
    ids=["invalid-runtime-request", "unexpected-wrapper-fault"],
)
@pytest.mark.asyncio
async def test_t011_attach_boundary_rejections_use_closed_mapping_without_input_echo(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    t011_composition: _T011Composition,
    caplog: pytest.LogCaptureFixture,
    unexpected: bool,
) -> None:
    async def rejected(
        runtime: ObservationRuntime, profile: str | Path, journal: str | Path
    ) -> RuntimeStatus:
        del runtime, profile, journal
        if unexpected:
            raise RuntimeError("private wrapper detail /private/source.toml")
        raise RuntimeRejectedError(RuntimeRejectedKind.INVALID_REQUEST)

    monkeypatch.setattr(observation_runtime, "attach_basic_observation", rejected)
    module = _t009_module()
    if hasattr(module, "attach_basic_observation"):
        monkeypatch.setattr(module, "attach_basic_observation", rejected)
    async with _t011_service(account_home, monkeypatch, t011_composition) as service:
        with caplog.at_level(logging.DEBUG):
            response = await service.request(
                _ATTACH,
                "POST",
                _t011_body(
                    t011_composition.profile_path, t011_composition.journal_path
                ),
            )
        _t011_error(
            response,
            500 if unexpected else 422,
            "service" if unexpected else "runtime",
            "internal_failure" if unexpected else "invalid_request",
        )
        assert "private wrapper detail" not in caplog.text + response.payload.decode()
        assert "/private/source.toml" not in caplog.text + response.payload.decode()
        assert t011_composition.destinations == [] and t011_composition.serials == []


@pytest.mark.asyncio
async def test_t009_context_cannot_construct_another_runtime_on_reentered_lifespan(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _t009_module()
    created, _ = _t009_runtime_spy(module, monkeypatch)
    config = _CONFIGS[0]
    with process_credential(config) as (owner, _):
        app = _t009_app(config, owner)
        first = AppLifespan(app)
        assert (await first.start())["type"] == "lifespan.startup.complete"
        await first.finish()
        second = AppLifespan(app)
        assert (await second.start())["type"] == "lifespan.startup.failed"
        assert second.task is not None
        result = await asyncio.gather(second.task, return_exceptions=True)
        assert isinstance(result[0], BootstrapFailure) and len(created) == 1


@pytest.mark.parametrize(
    "other_thread", [False, True], ids=["foreign-loop", "foreign-loop-thread"]
)
def test_t009_status_on_foreign_context_fails_without_runtime_rebinding(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    other_thread: bool,
) -> None:
    module = _t009_module()
    created, _ = _t009_runtime_spy(module, monkeypatch)
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token), asyncio.Runner() as owner_runner:
        app = _t009_app(config, owner)
        lifespan = AppLifespan(app)
        assert owner_runner.run(lifespan.start())["type"] == "lifespan.startup.complete"

        async def snapshot() -> object:
            return created[0].status()

        before = owner_runner.run(snapshot())
        try:

            async def query() -> Exchange:
                return await _call(
                    app, _scope(config, _headers(config, token)), Exchange()
                )

            if other_thread:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    response = executor.submit(lambda: asyncio.run(query())).result(
                        timeout=3.0
                    )
            else:
                with asyncio.Runner() as foreign_runner:
                    response = foreign_runner.run(query())
            assert response.status == 500
            assert json.loads(response.payload) == {
                "error": {"source": "runtime", "code": "wrong_execution_context"},
            }
            assert len(created) == 1 and owner_runner.run(snapshot()) == before
            assert owner_runner.run(query()).status == 200
        finally:
            owner_runner.run(lifespan.finish())


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", _STATUS + "/"])
@pytest.mark.parametrize("authenticated", [False, True])
@pytest.mark.asyncio
async def test_t009_actual_app_has_outer_security_no_docs_or_redirects(
    process_credential: Callable[[ServiceConfig], Any],
    path: str,
    authenticated: bool,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        app = _t009_app(config, owner)
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        try:
            headers = _headers(config, token)
            if not authenticated:
                headers = headers[:1]
            response = await _call(
                app,
                _scope(config, headers, path=path),
                Exchange(forbid_receive=True),
            )
            _error(
                response,
                404 if authenticated else 401,
                "route_not_found" if authenticated else "authentication_required",
                token,
            )
            assert b"location" not in response.headers
        finally:
            await lifespan.finish()


@pytest.mark.parametrize(
    ("path", "method", "body"),
    [
        (_ATTACH, "POST", _PAYLOAD),
        (_DETACH, "POST", b""),
    ],
)
@pytest.mark.asyncio
async def test_t013_mutation_routes_require_auth_before_body_or_run_preparation(
    process_credential: Callable[[ServiceConfig], Any],
    path: str,
    method: str,
    body: bytes,
) -> None:
    config = _CONFIGS[0]
    with process_credential(config) as (owner, token):
        app = _t009_app(config, owner)
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        try:
            headers = _headers(config, token)[:1] + [
                (b"content-type", b"application/json")
            ]
            response = await _call(
                app,
                _scope(config, headers, path=path, method=method),
                Exchange(body=body, forbid_receive=True),
            )
            _error(response, 401, "authentication_required", token)
        finally:
            await lifespan.finish()
