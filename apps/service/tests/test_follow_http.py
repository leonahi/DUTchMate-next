"""011 T010 RED: real authenticated app/jobs/streaming, typed Core boundary.

No route, encoder, admission pool, heartbeat or deadline is implemented here.
Only immutable Core facts/failures and progress at its application boundary are
controlled. The last cases use actual guarded Uvicorn/numeric loopback because a
buffered ASGI exchange cannot establish incremental frames or idle heartbeats.
Missing service behavior fails inside each test, never collection/fixture setup.
"""

import asyncio
import base64
import json
import logging
import socket
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from dutchmate_core import annotation, evidence, follow, model
from dutchmate_core.adapters.sqlite_evidence import SqliteEvidenceJournal
from dutchmate_core.runtime import RuntimeRejectedError, RuntimeRejectedKind
from starlette.types import Message

from dutchmate_service.bootstrap import ServiceConfig
from dutchmate_service.http import _DeliveryFailure
from test_annotation_http import _BODY as ANNOTATION_BODY
from test_annotation_http import _receipt as annotation_receipt
from test_evidence_http import (
    ChunkedExchange,
    _domain,
    _domain_wire,
    _error,
    _json,
    _provenance,
)
from test_monitor_http import _BODY as MONITOR_BODY
from test_monitor_http import MonitorService
from test_monitor_http import _service as monitor_service
from test_monitor_lifetime import PendingCalls
from test_service_http import _CONFIGS, Exchange
from test_service_http import (
    forbid_profile_and_run_preparation as forbid_profile_and_run_preparation,
)
from test_service_http import process_credential as process_credential
from test_service_http import t011_composition as t011_composition
from test_service_runtime import Client

ROUTE = "/v1/observation/follow"
SESSION = model.SessionId("session-é")
BODY = {"session_id": SESSION.value}
PRIVATE = "private-011-T010-path-SQL-token-cause"
LIMIT = 1048576
ORIGIN = "abcdefab-1234-4234-8234-123456789abc"
OPERATION = "12345678-1234-4234-8234-123456789abc"

pytestmark = pytest.mark.asyncio


async def wait[T](work: Awaitable[T], seconds: float = 3) -> T:
    # Test watchdog only, never an implementation deadline/resource abandonment.
    async with asyncio.timeout(seconds):
        return await work


def start(
    device: bool = False, session: model.SessionId = SESSION
) -> follow.FollowStart:
    return follow.FollowStart("run-é", session, 3, _provenance(device)[0])


def started(device: bool = False, session: str = SESSION.value) -> dict[str, Any]:
    return {
        "type": "started",
        "run_id": "run-é",
        "session_id": session,
        "start_sequence": 3,
        "provenance": _provenance(device)[1],
    }


def terminal(
    reason: str = "source_ended", next_sequence: int = 3, cutoff: int | None = 3
) -> dict[str, Any]:
    return {
        "type": "terminal",
        "reason": reason,
        "next_sequence": next_sequence,
        "source_end_exclusive": cutoff,
    }


def wire_bytes(value: object) -> bytes:
    # Contract 008 §6 requires standard-library JSON escaping unchanged.
    return _json(value) + b"\n"


def frames(response: Exchange, expected: Sequence[dict[str, Any]]) -> None:
    assert response.status == 200, "T011 missing: authenticated Follow streaming route"
    assert response.headers[b"content-type"] == b"application/x-ndjson"
    assert response.headers[b"cache-control"] == b"no-store"
    assert (
        b"content-length" not in response.headers
        and b"content-encoding" not in response.headers
    )
    raw = response.payload
    assert raw == b"".join(wire_bytes(frame) for frame in expected)
    assert all(len(line) <= LIMIT for line in raw.splitlines())
    assert [json.loads(line) for line in raw.splitlines()] == list(expected)
    assert (
        len([m for m in response.messages if m["type"] == "http.response.start"]) == 1
    )


def rx(
    sequence: int = 3, payload: bytes = b"\0\xff\r\n", device: bool = False
) -> model.RxBytesEvidence:
    p = _provenance(device)[0]
    return model.RxBytesEvidence(
        sequence,
        p.connection_id,
        p.segment_id,
        payload,
        model.BackendObservationTimestamp(
            p.backend_observation_timestamp_domain.domain_id, sequence
        ),
    )


def rx_wire(record: model.RxBytesEvidence) -> dict[str, Any]:
    # No production projector/codec computes expected wire facts.
    return {
        "kind": "rx_bytes",
        "sequence": record.sequence,
        "connection_id": record.connection_id.value,
        "segment_id": record.segment_id.value,
        "observed_at": {
            "domain_id": record.observed_at.domain_id,
            "value": record.observed_at.value,
        },
        "payload_base64": base64.b64encode(record.payload).decode("ascii"),
    }


class Subscription:
    """Typed source results at the existing Core boundary, no service policy."""

    def __init__(self, captured: follow.FollowStart, items: Sequence[object]) -> None:
        self.start = captured
        self.items: asyncio.Queue[object] = asyncio.Queue()
        for item in items:
            self.items.put_nowait(item)
        self.entered = asyncio.Event()
        self.closed = asyncio.Event()
        self.pulls = self.active = self.maximum_active = self.cancelled = 0

    async def pull(self) -> follow.FollowBatch | follow.FollowEnd:
        assert not self.closed.is_set(), "service pulled after subscriber close"
        self.pulls += 1
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.entered.set()
        try:
            value = await self.items.get()
            if isinstance(value, Exception):
                raise value
            assert isinstance(value, (follow.FollowBatch, follow.FollowEnd))
            return value
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        finally:
            self.active -= 1

    async def close(self) -> None:
        self.closed.set()


@dataclass
class CoreBoundary:
    captured: follow.FollowStart = field(default_factory=start)
    items: list[object] = field(
        default_factory=lambda: [follow.FollowEnd("source_ended", 3)]
    )
    failure: Exception | None = None
    calls: list[follow.FollowRequest] = field(default_factory=list)
    subscriptions: list[Subscription] = field(default_factory=list)
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    gated: bool = False

    async def invoke(self, request: follow.FollowRequest) -> Subscription:
        self.calls.append(request)
        self.entered.set()
        if self.gated:
            await self.release.wait()
        if self.failure is not None:
            raise self.failure
        subscription = Subscription(self.captured, self.items)
        self.subscriptions.append(subscription)
        return subscription


@dataclass
class Delivery:
    service: MonitorService
    core: CoreBoundary
    tasks: list[asyncio.Task[None]] = field(default_factory=list)
    clients: list[Client] = field(default_factory=list)

    def submit(
        self, client: Client | None = None, path: str = ROUTE
    ) -> tuple[asyncio.Task[None], Client]:
        client = Client(body=_json(BODY)) if client is None else client
        self.clients.append(client)

        async def deliver() -> None:
            await self.service.app(
                self.service.scope(path), client.receive, client.send
            )

        task = asyncio.create_task(deliver())
        self.tasks.append(task)
        return task, client


@asynccontextmanager
async def service(
    credentials: Callable[[ServiceConfig], Any],
    patch: pytest.MonkeyPatch,
    config: ServiceConfig = _CONFIGS[0],
    *,
    stub: bool = True,
) -> AsyncIterator[Delivery]:
    def forbidden(*args: object, **kwargs: object) -> Any:
        pytest.fail("T010 delivery-only tests must not create/open journal resources")

    for name in ("create_v3", "open_v3"):
        patch.setattr(SqliteEvidenceJournal, name, forbidden)
    async with monitor_service(credentials, patch, config) as existing:
        core = CoreBoundary()
        if stub:
            patch.setattr(existing.runtime, "start_follow", core.invoke)
        delivery = Delivery(existing, core)
        try:
            yield delivery
        finally:
            core.release.set()
            for sub in core.subscriptions:
                sub.items.put_nowait(
                    follow.FollowEnd("source_ended", model.SQLITE_INTEGER_MAX)
                )
            for client in delivery.clients:
                client.publication_gate.set()
                client.disconnected.set()
            for task in delivery.tasks:
                if not task.done():
                    task.cancel()
            await wait(asyncio.gather(*delivery.tasks, return_exceptions=True))


async def reached(
    event: asyncio.Event, task: asyncio.Task[None], client: Client
) -> None:
    notification = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait(
            (notification, task), timeout=3, return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            await task
            assert client.status == 200, (
                "T011 missing: Follow route/stream never reached the boundary"
            )
            pytest.fail("Follow stream ended before the tested boundary")
        assert notification in done, "Follow boundary not reached"
    finally:
        notification.cancel()
        await asyncio.gather(notification, return_exceptions=True)


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
async def test_literal_route_returns_started_and_terminal_from_core_without_refetch(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    device: bool,
) -> None:
    async with service(process_credential, monkeypatch, config) as d:
        d.core.captured = start(device)
        response = await d.service.request(ROUTE, BODY)
        frames(response, [started(device), terminal()])
        assert d.core.calls == [follow.FollowRequest(SESSION)]
        assert d.core.subscriptions[0].closed.is_set()
        assert not d.service.boundary.calls and not d.service.monitor.calls


@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def test_only_literal_post_method_before_body(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        response = await d.service.request(
            ROUTE,
            {},
            scope=d.service.scope(ROUTE, method=method),
            exchange=Exchange(forbid_receive=True),
        )
        _error(response, 405, "request", "method_not_allowed")
        assert not d.core.calls


@pytest.mark.parametrize(
    "alias", ["slash", "case", "encoded", "missing_raw", "absolute"]
)
async def test_aliases_never_redirect_normalize_or_consume_body(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        scope = d.service.scope(ROUTE)
        if alias == "slash":
            scope = d.service.scope(ROUTE + "/")
        elif alias == "case":
            scope = d.service.scope(ROUTE.replace("follow", "Follow"))
        elif alias == "encoded":
            scope["raw_path"] = b"/v1/observation/%66ollow"
        elif alias == "missing_raw":
            scope.pop("raw_path")
        else:
            scope["raw_path"] = b"http://127.0.0.1" + ROUTE.encode()
        _error(
            await d.service.request(
                ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
            ),
            404,
            "request",
            "route_not_found",
        )
        assert not d.core.calls


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize(
    "case,status,code",
    [
        ("peer", 403, "peer_rejected"),
        ("host", 400, "host_rejected"),
        ("origin", 403, "origin_rejected"),
        ("fetch", 403, "origin_rejected"),
        ("missing_auth", 401, "authentication_required"),
        ("wrong_auth", 401, "authentication_required"),
        ("duplicate_auth", 401, "authentication_required"),
        ("query", 400, "query_not_allowed"),
        ("upgrade", 400, "upgrade_rejected"),
    ],
)
async def test_security_before_stop_body_and_source_stays_private(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    case: str,
    status: int,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with service(process_credential, monkeypatch, config) as d:
        d.service.launch_context.request_stop()
        scope = d.service.scope(ROUTE)
        headers = list(scope["headers"])
        if case == "peer":
            scope["client"] = ("192.0.2.1", 1234)
        elif case == "host":
            headers = [
                (k, b"localhost:8765" if k == b"host" else v) for k, v in headers
            ]
        elif case in {"origin", "fetch", "upgrade"}:
            headers.append(
                (
                    {
                        "origin": b"origin",
                        "fetch": b"sec-fetch-site",
                        "upgrade": b"upgrade",
                    }[case],
                    PRIVATE.encode(),
                )
            )
        elif case == "missing_auth":
            headers = [(k, v) for k, v in headers if k != b"authorization"]
        elif case == "wrong_auth":
            headers = [
                (k, b"Bearer " + b"0" * 64 if k == b"authorization" else v)
                for k, v in headers
            ]
        elif case == "duplicate_auth":
            headers.append((b"authorization", b"Bearer " + d.service.token))
        else:
            scope["query_string"] = b"token=" + PRIVATE.encode()
        scope["headers"] = headers
        response = await d.service.request(
            ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
        )
        _error(response, status, "request", code)
        assert not d.core.calls and d.service.token not in response.payload
        assert (
            PRIVATE not in caplog.text and d.service.token.decode() not in caplog.text
        )


async def test_stop_readiness_rejects_before_media_body_or_core(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        d.service.launch_context.request_stop()
        _error(
            await d.service.request(ROUTE, {}, exchange=Exchange(forbid_receive=True)),
            503,
            "service",
            "stopping",
        )
        assert not d.core.calls


async def test_inactive_runtime_returns_precise_follow_rejection_through_readiness_bypass(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with service(process_credential, monkeypatch, stub=False) as d:
        _error(
            await d.service.request(ROUTE, BODY), 404, "follow", "no_associated_session"
        )


async def test_request_stop_synchronously_seals_real_follow_before_lifespan_detach(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with service(process_credential, monkeypatch, stub=False) as d:
        before = d.service.runtime.status()
        d.service.launch_context.request_stop()
        with pytest.raises(follow.FollowRejected) as caught:
            await d.service.runtime.start_follow(follow.FollowRequest(SESSION))
        assert caught.value.kind == "not_active", (
            "T011 missing: request_stop must synchronously seal Follow"
        )
        assert d.service.runtime.status() == before


INVALID_SESSIONS: Sequence[object] = (
    "",
    "x\0y",
    "x" * 257,
    "é" * 129,
    None,
    True,
    1,
    [],
)
INVALID: list[object] = [
    None,
    [],
    {},
    True,
    1,
    "session",
    *[{"session_id": v} for v in INVALID_SESSIONS],
    *[
        {**BODY, k: PRIVATE}
        for k in (
            "run_id",
            "start_sequence",
            "cursor",
            "filter",
            "timeout_ms",
            "path",
            "extra",
        )
    ],
]


@pytest.mark.parametrize("body", INVALID)
async def test_closed_request_and_invalid_session_before_source(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    body: object,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        _error(await d.service.request(ROUTE, body), 422, "request", "invalid_request")
        assert not d.core.calls


@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b"[]",
        b"{} trailing",
        b"\xff",
        b'{"session_id":"x","session_id":"y"}',
        *[
            b'{"session_id":' + v + b"}"
            for v in (b"NaN", b"Infinity", b"-Infinity", b'"\\ud800"', b'"\\udfff"')
        ],
    ],
)
async def test_utf8_json_duplicates_nonfinite_and_surrogates_are_rejected(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    raw: bytes,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        _error(
            await d.service.request(ROUTE, {}, raw=raw),
            422,
            "request",
            "invalid_request",
        )
        assert not d.core.calls


@pytest.mark.parametrize("session", [" ", "x" * 256, "é" * 128, " /e\u0301 "])
async def test_legal_session_edges_are_exact_and_not_normalized(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    session: str,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        d.core.captured = start(session=model.SessionId(session))
        response = await d.service.request(ROUTE, {"session_id": session})
        frames(response, [started(session=session), terminal()])
        assert d.core.calls == [follow.FollowRequest(model.SessionId(session))]


@pytest.mark.parametrize(
    "media",
    [
        None,
        b"text/json",
        b"application/json; charset=latin-1",
        b"application/json; profile=x",
        b"application/json; charset=utf-8; charset=utf-8",
        b"\xff",
        b"duplicate",
    ],
)
async def test_bad_media_precedes_body_consumption(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    media: bytes | None,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        scope = d.service.scope(ROUTE)
        scope["headers"] = [(k, v) for k, v in scope["headers"] if k != b"content-type"]
        if media is not None:
            scope["headers"].append(
                (
                    b"content-type",
                    b"application/json" if media == b"duplicate" else media,
                )
            )
        if media == b"duplicate":
            scope["headers"].append((b"content-type", b"application/json"))
        _error(
            await d.service.request(
                ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
            ),
            415,
            "request",
            "unsupported_media_type",
        )
        assert not d.core.calls


@pytest.mark.parametrize(
    "media", [b"application/json", b' Application/JSON ; charset="UTF-8" ']
)
async def test_existing_utf8_json_media_conventions_are_preserved(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    media: bytes,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        scope = d.service.scope(ROUTE)
        scope["headers"] = [
            (k, media if k == b"content-type" else v) for k, v in scope["headers"]
        ]
        frames(
            await d.service.request(ROUTE, BODY, scope=scope), [started(), terminal()]
        )


@pytest.mark.parametrize("size", [16384, 16385])
@pytest.mark.parametrize("declared", [b"0", b"16384", b"999999"])
async def test_actual_chunked_body_cap_ignores_claimed_content_length(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    size: int,
    declared: bytes,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        raw = _json(BODY)
        raw += b" " * (size - len(raw))
        scope = d.service.scope(ROUTE)
        scope["headers"].append((b"content-length", declared))
        response = await d.service.request(
            ROUTE,
            {},
            scope=scope,
            exchange=ChunkedExchange(chunks=[raw[:8192], raw[8192:16384], raw[16384:]]),
        )
        if size == 16384:
            frames(response, [started(), terminal()])
            assert len(d.core.calls) == 1
        else:
            _error(response, 413, "request", "payload_too_large")
            assert not d.core.calls


REJECTIONS: tuple[tuple[follow.FollowRejectedKind, int], ...] = (
    ("no_associated_session", 404),
    ("session_not_associated", 409),
    ("not_active", 409),
    ("follow_unavailable", 503),
    ("busy", 409),
    ("read_capacity", 503),
    ("delivery_too_large", 413),
)
FAILURES: list[tuple[Exception, int, str, str]] = [
    (follow.FollowRejected(kind), status, "follow", kind) for kind, status in REJECTIONS
]
FAILURES += [
    (
        evidence.JournalFailure(evidence.JournalOperation.RETRIEVE, k, PRIVATE),
        {
            evidence.JournalFailureKind.INVALID_INPUT: 422,
            evidence.JournalFailureKind.SESSION_MISMATCH: 409,
            evidence.JournalFailureKind.JOURNAL_MISSING: 404,
            evidence.JournalFailureKind.BUSY: 503,
            evidence.JournalFailureKind.CLOSED: 409,
        }.get(k, 500),
        "journal",
        k.value,
    )
    for k in evidence.JournalFailureKind
]
FAILURES += [
    (RuntimeRejectedError(k), status, "runtime", k.value)
    for k, status in (
        (RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT, 500),
        (RuntimeRejectedKind.INVALID_REQUEST, 422),
    )
]
FAILURES += [(RuntimeError(PRIVATE), 500, "service", "internal_failure")]


@pytest.mark.parametrize(
    "failure,status,source,code", FAILURES, ids=[s + "-" + c for _, _, s, c in FAILURES]
)
async def test_all_follow_runtime_and_twenty_journal_errors_are_fixed_private_envelopes(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status: int,
    source: str,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with service(process_credential, monkeypatch) as d:
        d.core.failure = failure
        response = await d.service.request(ROUTE, BODY)
        _error(response, status, source, code)
        assert len(d.core.calls) == 1 and b"retry-after" not in response.headers
        assert PRIVATE.encode() not in response.payload
        assert (
            PRIVATE not in caplog.text and d.service.token.decode() not in caplog.text
        )


def seven_records(
    device: bool,
) -> tuple[tuple[model.EvidenceRecord, ...], list[dict[str, Any]]]:
    p, p_wire = _provenance(device)
    raw = rx(4, bytes(range(256)), device)
    timestamp = model.BackendObservationTimestamp(
        p.backend_observation_timestamp_domain.domain_id, 5
    )
    clock = model.MonitorClockFacts(ORIGIN, 100, 1000000100, 102)
    records: tuple[model.EvidenceRecord, ...] = (
        model.SegmentStartedEvidence(3, p),
        raw,
        model.ObserverLossEvidence(
            5,
            p.connection_id,
            p.segment_id,
            "observer",
            "upstream",
            model.ObserverLossCause.OVERFLOW,
            7,
            timestamp,
        ),
        model.OperationStartedEvidence(
            6, OPERATION, "monitor", p, 1000, 65536, ORIGIN, b"\0\xffA"
        ),
        model.OperationEndedEvidence(
            7,
            OPERATION,
            "monitor",
            6,
            model.SequenceRange(7, 7),
            model.MonitorOutcome.DETACHED,
            0,
            0,
            None,
            clock,
        ),
        model.ClientAnnotationEvidence(8, " build e\u0301\r\n\t ", "http", ORIGIN, 103),
        model.SegmentEndedEvidence(
            9, p.connection_id, p.segment_id, model.SegmentEndReason.EXPLICIT_STOP
        ),
    )
    views = [
        {"kind": "segment_started", "sequence": 3, "provenance": p_wire},
        rx_wire(raw),
        {
            "kind": "observer_loss",
            "sequence": 5,
            "connection_id": "connection-é",
            "segment_id": "segment-é",
            "observer_id": "observer",
            "scope": "upstream",
            "cause": "overflow",
            "lost_bytes": 7,
            "observed_at": {"domain_id": timestamp.domain_id, "value": 5},
        },
        {
            "kind": "operation_started",
            "sequence": 6,
            "operation_id": OPERATION,
            "operation_kind": "monitor",
            "provenance": p_wire,
            "timeout_ms": 1000,
            "max_rx_bytes": 65536,
            "clock_origin_id": ORIGIN,
            "condition_base64": "AP9B",
        },
        {
            "kind": "operation_ended",
            "sequence": 7,
            "operation_id": OPERATION,
            "operation_kind": "monitor",
            "start_sequence": 6,
            "window": {"start_inclusive": 7, "end_exclusive": 7},
            "outcome": "detached",
            "examined_rx_bytes": 0,
            "observer_loss_records": 0,
            "match": None,
            "clock": {
                "origin_id": ORIGIN,
                "started_at_ns": 100,
                "deadline_at_ns": 1000000100,
                "decided_at_ns": 102,
            },
        },
        {
            "kind": "client_annotation",
            "sequence": 8,
            "assertion_class": "client_assertion",
            "client_surface": "http",
            "attribution_basis": "client_asserted",
            "clock_origin_id": ORIGIN,
            "received_at_ns": 103,
            "text": " build e\u0301\r\n\t ",
        },
        {
            "kind": "segment_ended",
            "sequence": 9,
            "connection_id": "connection-é",
            "segment_id": "segment-é",
            "reason": "explicit_stop",
        },
    ]
    return records, views


@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
async def test_exact_seven_existing_record_projections_and_all_binary_values(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    records, views = seven_records(device)
    async with service(process_credential, monkeypatch) as d:
        d.core.captured = start(device)
        d.core.items = [
            follow.FollowBatch(None, records),
            follow.FollowEnd("source_ended", 10),
        ]
        response = await d.service.request(ROUTE, BODY)
        frames(
            response,
            [
                started(device),
                *[{"type": "record", "record": r} for r in views],
                terminal(next_sequence=10, cutoff=10),
            ],
        )
        sub = d.core.subscriptions[0]
        assert sub.maximum_active == 1 and sub.pulls == 2 and sub.closed.is_set()
        assert not d.service.boundary.calls and not d.service.monitor.calls
        assert views[1]["payload_base64"] not in caplog.text
        assert (
            "build e" not in caplog.text and d.service.token.decode() not in caplog.text
        )


@pytest.mark.parametrize("endpoints", [False, True])
async def test_gap_precedes_records_and_retains_whole_prefix_counts_and_clock_origins(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    endpoints: bool,
) -> None:
    first = (
        model.RetentionTimestampEndpoint(
            model.BackendObservationTimestamp("host-clock", 90), _domain(False)
        )
        if endpoints
        else None
    )
    last = (
        model.RetentionTimestampEndpoint(
            model.BackendObservationTimestamp("device-clock", 2), _domain(True)
        )
        if endpoints
        else None
    )
    marker = model.RetentionMarker(model.SequenceRange(0, 5), first, last, 5, 33, 1000)
    gap = follow.FollowGap(model.SequenceRange(3, 5), marker)
    marker_wire = {
        "expired_range": {"start_inclusive": 0, "end_exclusive": 5},
        "first_discarded_timestamp": {
            "timestamp": {"domain_id": "host-clock", "value": 90},
            "domain": _domain_wire(False),
        }
        if endpoints
        else None,
        "last_discarded_timestamp": {
            "timestamp": {"domain_id": "device-clock", "value": 2},
            "domain": _domain_wire(True),
        }
        if endpoints
        else None,
        "discarded_record_count": 5,
        "discarded_rx_payload_byte_count": 33,
        "discarded_charged_bytes": 1000,
    }
    record = rx(5)
    async with service(process_credential, monkeypatch) as d:
        d.core.items = [
            follow.FollowBatch(gap, (record,)),
            follow.FollowEnd("detached", 10),
        ]
        frames(
            await d.service.request(ROUTE, BODY),
            [
                started(),
                {
                    "type": "gap",
                    "missed_range": {"start_inclusive": 3, "end_exclusive": 5},
                    "retention_marker": marker_wire,
                },
                {"type": "record", "record": rx_wire(record)},
                terminal("detached", 6, 10),
            ],
        )


@pytest.mark.parametrize(
    "reason",
    [
        "detached",
        "service_stopping",
        "source_ended",
        "source_failed",
        "read_capacity",
        "delivery_too_large",
    ],
)
@pytest.mark.parametrize("cutoff", [None, 3, model.SQLITE_INTEGER_MAX])
async def test_terminal_reasons_and_unknown_or_known_cutoff_never_claim_delivery(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    reason: follow.FollowEndReason,
    cutoff: int | None,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        d.core.items = [follow.FollowEnd(reason, cutoff)]
        frames(
            await d.service.request(ROUTE, BODY),
            [started(), terminal(reason, 3, cutoff)],
        )


@pytest.mark.parametrize("size", [LIMIT, LIMIT + 1])
async def test_started_frame_bound_is_checked_before_http200_and_unregisters_overflow(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    size: int,
) -> None:
    expected = started()
    expected["provenance"]["connection_provenance"]["fields"] = [
        {"name": "padding", "value": ""}
    ]
    padding = "p" * (size - len(wire_bytes(expected)) + 1)
    expected["provenance"]["connection_provenance"]["fields"][0]["value"] = padding
    assert len(wire_bytes(expected)) == size + 1
    p = start().provenance
    envelope = p.connection_provenance.to_snapshot()
    p = replace(
        p,
        connection_provenance=model.PersistedConnectionProvenance(
            replace(envelope, fields=(model.ProvenanceField("padding", padding),))
        ),
    )
    async with service(process_credential, monkeypatch) as d:
        d.core.captured = replace(start(), provenance=p)
        response = await d.service.request(ROUTE, BODY)
        if size == LIMIT:
            frames(response, [expected, terminal()])
        else:
            _error(response, 413, "follow", "delivery_too_large")
        assert d.core.subscriptions[0].closed.is_set()
        assert d.core.subscriptions[0].pulls == (1 if size == LIMIT else 0)


class BrokenProvenance(model.BackendConnectionProvenance):
    def to_snapshot(self) -> model.ConnectionProvenanceSnapshot:
        raise RuntimeError(PRIVATE)


async def test_started_projection_failure_is_private_preheader_error_and_closes_admission(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with service(process_credential, monkeypatch) as d:
        d.core.captured = replace(
            start(),
            provenance=replace(
                start().provenance, connection_provenance=BrokenProvenance()
            ),
        )
        response = await d.service.request(ROUTE, BODY)
        _error(response, 500, "service", "internal_failure")
        assert (
            d.core.subscriptions[0].closed.is_set()
            and d.core.subscriptions[0].pulls == 0
        )
        assert PRIVATE not in caplog.text


@pytest.mark.parametrize("fault", ["journal", "unexpected", "projection", "oversize"])
async def test_post_header_failure_ends_at_emitted_prefix_without_second_http_error_or_skipping(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    good = rx()
    if fault == "journal":
        broken: object = evidence.JournalFailure(
            evidence.JournalOperation.RETRIEVE,
            evidence.JournalFailureKind.IO_FAILURE,
            PRIVATE,
        )
    elif fault == "unexpected":
        broken = RuntimeError(PRIVATE)
    elif fault == "projection":
        broken = follow.FollowBatch(
            None,
            (
                model.SegmentStartedEvidence(
                    4,
                    replace(
                        start().provenance, connection_provenance=BrokenProvenance()
                    ),
                ),
            ),
        )
    else:
        broken = follow.FollowBatch(None, (rx(4, b"\xff" * (LIMIT // 4 * 3)),))
    async with service(process_credential, monkeypatch) as d:
        d.core.items = [
            follow.FollowBatch(None, (good,)),
            broken,
            follow.FollowEnd("source_ended", 5),
        ]
        response = await d.service.request(ROUTE, BODY)
        frames(
            response,
            [
                started(),
                {"type": "record", "record": rx_wire(good)},
                terminal(
                    "delivery_too_large" if fault == "oversize" else "source_failed",
                    4,
                    None,
                ),
            ],
        )
        assert (
            d.core.subscriptions[0].closed.is_set()
            and d.core.subscriptions[0].pulls == 2
        )
        assert (
            PRIVATE not in caplog.text and d.service.token.decode() not in caplog.text
        )


@dataclass
class FrameClient(Client):
    hold_type: str = "record"
    blocked: asyncio.Event = field(default_factory=asyncio.Event)
    release_send: asyncio.Event = field(default_factory=asyncio.Event)
    send_cancelled: int = 0
    active_sends: int = 0
    maximum_sends: int = 0
    attempts: list[str] = field(default_factory=list)

    async def send(self, message: Message) -> None:
        self.active_sends += 1
        self.maximum_sends = max(self.maximum_sends, self.active_sends)
        try:
            body = message.get("body", b"")
            if message["type"] == "http.response.body" and body and self.status == 200:
                kind = json.loads(body)["type"]
                self.attempts.append(kind)
                if kind == self.hold_type:
                    self.blocked.set()
                    try:
                        await self.release_send.wait()
                    except asyncio.CancelledError:
                        self.send_cancelled += 1
                        raise
            await super().send(message)
        finally:
            self.active_sends -= 1


async def test_blocked_frame_has_only_one_page_pull_and_one_send_without_prefetch_chain(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        d.core.items = [
            follow.FollowBatch(None, (rx(3), rx(4))),
            follow.FollowEnd("source_ended", 5),
        ]
        client = FrameClient(body=_json(BODY))
        task, _ = d.submit(client)
        try:
            await reached(client.blocked, task, client)
            sub = d.core.subscriptions[0]
            assert sub.pulls == 1 and sub.maximum_active == 1
            assert client.maximum_sends == 1 and client.attempts == [
                "started",
                "record",
            ]
        finally:
            client.release_send.set()
        await wait(task)
        frames(
            client,
            [
                started(),
                {"type": "record", "record": rx_wire(rx(3))},
                {"type": "record", "record": rx_wire(rx(4))},
                terminal(next_sequence=5, cutoff=5),
            ],
        )


@pytest.mark.parametrize("kind", ["started", "record", "heartbeat", "terminal"])
async def test_each_stalled_frame_send_has_five_second_cooperative_deadline_and_no_retry(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        if kind == "record":
            d.core.items = [
                follow.FollowBatch(None, (rx(),)),
                follow.FollowEnd("source_ended", 4),
            ]
        elif kind == "heartbeat":
            d.core.items = []
        client = FrameClient(body=_json(BODY), hold_type=kind)
        task, _ = d.submit(client)
        try:
            await reached(client.blocked, task, client)
            began = asyncio.get_running_loop().time()
            try:
                await wait(asyncio.shield(task), 6.5)
            except asyncio.CancelledError, _DeliveryFailure:
                assert task.done()
            elapsed = asyncio.get_running_loop().time() - began
            assert 4.5 <= elapsed <= 6.5
            assert client.send_cancelled == 1 and client.maximum_sends == 1
            assert (
                client.attempts.count(kind) == 1
                and client.attempts[-1] == kind
                and d.core.subscriptions[0].closed.is_set()
            )
            assert client.status == 200
            assert not d.service.boundary.calls and not d.service.monitor.calls
        finally:
            client.release_send.set()


@pytest.mark.parametrize("phase", ["admission", "stream"])
async def test_one_follow_job_is_registered_before_core_and_independent_of_all_existing_pools(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        d.core.gated = phase == "admission"
        if phase == "stream":
            d.core.items = []
        first, client = d.submit()
        pending = PendingCalls()
        try:
            await reached(d.core.entered, first, client)
            if phase == "stream":
                await reached(client.publication, first, client)
                assert client.status == 200

            async def annotate(
                request: annotation.AnnotationRequest,
            ) -> annotation.AnnotationReceipt:
                await pending.wait("mutation")
                return annotation_receipt()

            read_result = d.service.boundary.result

            async def read(request: object) -> object:
                await pending.wait("read")
                return read_result

            monitor_result = d.service.monitor.result

            async def monitor(request: object) -> object:
                await pending.wait("monitor")
                return monitor_result

            monkeypatch.setattr(d.service.runtime, "annotate", annotate)
            monkeypatch.setattr(d.service.runtime, "read_record", read)
            monkeypatch.setattr(d.service.runtime, "monitor", monitor)
            old = []
            for path, body, count in (
                ("/v1/observation/annotations", ANNOTATION_BODY, 8),
                (
                    "/v1/evidence/record",
                    {"session_id": SESSION.value, "sequence": 0},
                    8,
                ),
                ("/v1/observation/monitor", MONITOR_BODY, 1),
            ):
                for _ in range(count):
                    task, c = d.submit(Client(body=_json(body)), path)
                    old.append((task, c))
                    await wait(pending.entered.get())
            assert len(pending.calls) == 17
            for path, body, code in (
                ("/v1/observation/annotations", ANNOTATION_BODY, "operation_capacity"),
                (
                    "/v1/evidence/record",
                    {"session_id": SESSION.value, "sequence": 0},
                    "operation_capacity",
                ),
                ("/v1/observation/monitor", MONITOR_BODY, "operation_capacity"),
                (ROUTE, BODY, "follow_capacity"),
            ):
                _error(await d.service.request(path, body), 503, "service", code)
            assert len(d.core.calls) == 1
            pending.release()
            d.core.release.set()
            if phase == "stream":
                d.core.subscriptions[0].items.put_nowait(
                    follow.FollowEnd("source_ended", 3)
                )
            await wait(asyncio.gather(first, *(task for task, _ in old)))
            assert all(c.status == 200 for _, c in old)
            frames(client, [started(), terminal()])
            d.core.items = [follow.FollowEnd("source_ended", 3)]
            frames(await d.service.request(ROUTE, BODY), [started(), terminal()])
            assert len(d.core.calls) == 2
        finally:
            pending.release()
            d.core.release.set()


@asynccontextmanager
async def loopback(
    credentials: Callable[[ServiceConfig], Any],
    patch: pytest.MonkeyPatch,
    host: str,
) -> AsyncIterator[tuple[Delivery, str]]:
    # Only a test-owned numeric loopback socket. No arbitrary service, proxy,
    # external address, real account, discovery or physical serial is used.
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        if family == socket.AF_INET6:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind((host, 0))
        listener.listen(128)
        listener.setblocking(False)
        config = ServiceConfig(listener.getsockname()[1], host)
        async with service(credentials, patch, config) as d:
            server = uvicorn.Server(
                uvicorn.Config(
                    d.service.app,
                    host=host,
                    port=config.port,
                    lifespan="off",
                    log_config=None,
                    access_log=False,
                    proxy_headers=False,
                    server_header=False,
                    date_header=False,
                )
            )
            # Match Server._serve's setup while the enclosing helper owns the
            # actual app lifespan; do not install signal handlers in pytest.
            server.config.load()
            server.lifespan = server.config.lifespan_class(server.config)
            await wait(server.startup(sockets=[listener]))
            assert server.started
            url = (
                f"http://[{host}]:{config.port}"
                if family == socket.AF_INET6
                else f"http://{host}:{config.port}"
            )
            try:
                yield d, url
            finally:
                d.core.release.set()
                for sub in d.core.subscriptions:
                    sub.items.put_nowait(
                        follow.FollowEnd("source_ended", model.SQLITE_INTEGER_MAX)
                    )
                await wait(server.shutdown(sockets=[listener]), 5)


def client_headers(d: Delivery) -> dict[str, str]:
    return {
        "Authorization": "Bearer " + d.service.token.decode(),
        "Content-Type": "application/json",
    }


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"], ids=["ipv4", "ipv6"])
@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
async def test_real_loopback_started_and_new_record_arrive_before_source_end(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    device: bool,
) -> None:
    async with loopback(process_credential, monkeypatch, host) as (d, url):
        d.core.captured = start(device)
        d.core.items = []
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=3
        ) as client:
            async with client.stream(
                "POST", url + ROUTE, headers=client_headers(d), content=_json(BODY)
            ) as response:
                assert response.status_code == 200, (
                    "T011 missing: real loopback Follow route"
                )
                assert response.headers["content-type"] == "application/x-ndjson"
                assert response.headers["cache-control"] == "no-store"
                assert (
                    "content-length" not in response.headers
                    and "content-encoding" not in response.headers
                )
                lines = response.aiter_lines()
                assert json.loads(await wait(anext(lines))) == started(device)
                sub = d.core.subscriptions[0]
                assert not sub.closed.is_set()
                record = rx(3, bytes(range(256)), device)
                sub.items.put_nowait(follow.FollowBatch(None, (record,)))
                assert json.loads(await wait(anext(lines))) == {
                    "type": "record",
                    "record": rx_wire(record),
                }
                assert not sub.closed.is_set()  # No full-response/source-end buffering.
                sub.items.put_nowait(follow.FollowEnd("detached", 4))
                assert json.loads(await wait(anext(lines))) == terminal(
                    "detached", 4, 4
                )
                with pytest.raises(StopAsyncIteration):
                    await wait(anext(lines))
        assert d.core.subscriptions[0].closed.is_set()


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"], ids=["ipv4", "ipv6"])
async def test_real_loopback_one_second_heartbeat_while_core_pull_pending_without_polling(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    host: str,
) -> None:
    async with loopback(process_credential, monkeypatch, host) as (d, url):
        d.core.items = []
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=3
        ) as client:
            async with client.stream(
                "POST", url + ROUTE, headers=client_headers(d), content=_json(BODY)
            ) as response:
                assert response.status_code == 200, (
                    "T011 missing: real loopback Follow heartbeat stream"
                )
                lines = response.aiter_lines()
                assert json.loads(await wait(anext(lines))) == started()
                sub = d.core.subscriptions[0]
                await wait(sub.entered.wait())
                began = asyncio.get_running_loop().time()
                heartbeat = asyncio.ensure_future(anext(lines))
                try:
                    with pytest.raises(TimeoutError):
                        await wait(asyncio.shield(heartbeat), 0.75)
                    assert (
                        await wait(asyncio.shield(heartbeat), 1.5)
                        == '{"type":"heartbeat"}'
                    )
                    elapsed = asyncio.get_running_loop().time() - began
                    assert 0.8 <= elapsed <= 2.25
                    assert (
                        sub.pulls == 1
                        and sub.active == sub.maximum_active == 1
                        and sub.cancelled == 0
                    )
                    assert not d.service.boundary.calls and not d.service.monitor.calls
                    sub.items.put_nowait(follow.FollowEnd("source_ended", 3))
                    assert json.loads(await wait(anext(lines))) == terminal()
                    with pytest.raises(StopAsyncIteration):
                        await wait(anext(lines))
                finally:
                    if not heartbeat.done():
                        heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)


class FailedFrameClient(Client):
    async def send(self, message: Message) -> None:
        await super().send(message)
        if message["type"] == "http.response.body" and self.status == 200:
            raise OSError(PRIVATE)


@pytest.mark.parametrize("loss", ["disconnect", "send_error"])
async def test_unusable_delivery_closes_subscription_without_detach_or_terminal_retry(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    loss: str,
) -> None:
    async with service(process_credential, monkeypatch) as d:
        d.core.items = []
        detach_calls: list[None] = []
        original = d.service.runtime.detach

        async def detached() -> object:
            detach_calls.append(None)
            return await original()

        monkeypatch.setattr(d.service.runtime, "detach", detached)
        client = (
            FailedFrameClient(body=_json(BODY))
            if loss == "send_error"
            else Client(body=_json(BODY))
        )
        task, _ = d.submit(client)
        try:
            await reached(client.publication, task, client)
            if loss == "disconnect":
                client.disconnected.set()
            try:
                await wait(task)
            except asyncio.CancelledError, _DeliveryFailure:
                pass
            assert d.core.subscriptions[0].closed.is_set() and not detach_calls
            assert (
                len([m for m in client.messages if m["type"] == "http.response.start"])
                == 1
            )
            body = b"".join(
                m.get("body", b"")
                for m in client.messages
                if m["type"] == "http.response.body"
            )
            assert b'"terminal"' not in body
            d.core.items = [follow.FollowEnd("source_ended", 3)]
            frames(await d.service.request(ROUTE, BODY), [started(), terminal()])
        finally:
            # This observation is only about the Follow exchange; normal
            # enclosing lifespan cleanup must still detach its runtime.
            monkeypatch.setattr(d.service.runtime, "detach", original)


# T015: delivery edges only. Existing T010 helpers/tests above are preserved.
def t015_padding(byte_count: int) -> str:
    unit = 'é😀\n\r\\"\x01'
    width = len(_json(unit)) - 2  # Independent stdlib escaping, excluding quotes.
    return unit * (byte_count // width) + "p" * (byte_count % width)


def t015_provenance(
    provenance: model.SegmentProvenance, padding: str
) -> model.SegmentProvenance:
    return replace(
        provenance,
        connection_provenance=model.PersistedConnectionProvenance(
            replace(
                provenance.connection_provenance.to_snapshot(),
                fields=(model.ProvenanceField("padding", padding),),
            )
        ),
    )


@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced"])
@pytest.mark.parametrize("size", [LIMIT - 1, LIMIT, LIMIT + 1])
@pytest.mark.parametrize(
    "index", [0, 1, 2, 3, 6], ids=["segment", "rx", "loss", "monitor", "end"]
)
async def test_t015_record_encoded_edges_use_escaped_bytes_and_preserve_offered_prefix(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
    size: int,
    index: int,
) -> None:
    source, views = seven_records(device)
    records = list(source)
    # Break aliases between the independently declared golden provenance views.
    views = json.loads(_json(views))
    value = views[index]
    record = records[index]
    if index in (0, 3):
        value["provenance"]["connection_provenance"]["fields"] = [
            {"name": "padding", "value": ""}
        ]
        padding = t015_padding(size - len(_json({"type": "record", "record": value})))
        value["provenance"]["connection_provenance"]["fields"][0]["value"] = padding
        assert isinstance(
            record, (model.SegmentStartedEvidence, model.OperationStartedEvidence)
        )
        records[index] = replace(
            record, provenance=t015_provenance(record.provenance, padding)
        )
    elif index == 1:
        assert isinstance(record, model.RxBytesEvidence)
        value["payload_base64"] = ""
        budget = size - len(_json({"type": "record", "record": value}))
        payload = b"\xff\0\n" * (budget // 4)
        connection = record.connection_id.value + "p" * (budget % 4)
        records[index] = replace(
            record,
            payload=payload,
            connection_id=model.ConnectionInstanceId(connection),
        )
        value["payload_base64"] = base64.b64encode(payload).decode()
        value["connection_id"] = connection
    elif index == 2:
        assert isinstance(record, model.ObserverLossEvidence)
        value["observer_id"] = ""
        padding = t015_padding(size - len(_json({"type": "record", "record": value})))
        records[index] = replace(record, observer_id=padding)
        value["observer_id"] = padding
    else:
        assert isinstance(record, model.SegmentEndedEvidence)
        value["connection_id"] = ""
        padding = t015_padding(size - len(_json({"type": "record", "record": value})))
        records[index] = replace(
            record, connection_id=model.ConnectionInstanceId(padding)
        )
        value["connection_id"] = padding
    assert len(wire_bytes({"type": "record", "record": value})) == size + 1
    async with service(process_credential, monkeypatch) as d:
        d.core.captured = start(device)
        d.core.items = [
            follow.FollowBatch(None, tuple(records)),
            follow.FollowEnd("source_ended", 10),
        ]
        response = await d.service.request(ROUTE, BODY)
        if size <= LIMIT:
            expected = [
                started(device),
                *({"type": "record", "record": r} for r in views),
                terminal(next_sequence=10, cutoff=10),
            ]
        else:
            expected = [
                started(device),
                *({"type": "record", "record": r} for r in views[:index]),
                terminal("delivery_too_large", 3 + index, None),
            ]
        frames(response, expected)
        sub = d.core.subscriptions[0]
        assert sub.closed.is_set() and sub.pulls == (2 if size <= LIMIT else 1)


@pytest.mark.parametrize("size", [LIMIT - 1, LIMIT, LIMIT + 1])
async def test_t015_escaped_started_cap_is_preheader_and_not_python_character_count(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    size: int,
) -> None:
    expected = started(True)
    expected["provenance"]["connection_provenance"]["fields"] = [
        {"name": "padding", "value": ""}
    ]
    padding = t015_padding(size - len(_json(expected)))
    expected["provenance"]["connection_provenance"]["fields"][0]["value"] = padding
    assert len(_json(expected)) == size and len(padding) < size // 2
    async with service(process_credential, monkeypatch) as d:
        d.core.captured = replace(
            start(True), provenance=t015_provenance(start(True).provenance, padding)
        )
        response = await d.service.request(ROUTE, BODY)
        if size <= LIMIT:
            frames(response, [expected, terminal()])
        else:
            _error(response, 413, "follow", "delivery_too_large")
        assert d.core.subscriptions[0].closed.is_set()
        assert d.core.subscriptions[0].pulls == (1 if size <= LIMIT else 0)


def t015_gap(size: int) -> tuple[follow.FollowGap, dict[str, Any]]:
    first_domain, last_domain = _domain(False), _domain(True)
    view: dict[str, Any] = {
        "type": "gap",
        "missed_range": {"start_inclusive": 4, "end_exclusive": 5},
        "retention_marker": {
            "expired_range": {"start_inclusive": 0, "end_exclusive": 5},
            "first_discarded_timestamp": {
                "timestamp": {"domain_id": "host-clock", "value": 90},
                "domain": _domain_wire(False),
            },
            "last_discarded_timestamp": {
                "timestamp": {"domain_id": "device-clock", "value": 2},
                "domain": _domain_wire(True),
            },
            "discarded_record_count": 5,
            "discarded_rx_payload_byte_count": 33,
            "discarded_charged_bytes": 1000,
        },
    }
    first_view = view["retention_marker"]["first_discarded_timestamp"]["domain"]
    first_view["origin_id"] = ""
    padding = t015_padding(size - len(_json(view)))
    first_view["origin_id"] = padding
    marker = model.RetentionMarker(
        model.SequenceRange(0, 5),
        model.RetentionTimestampEndpoint(
            model.BackendObservationTimestamp("host-clock", 90),
            replace(first_domain, origin_id=padding),
        ),
        model.RetentionTimestampEndpoint(
            model.BackendObservationTimestamp("device-clock", 2), last_domain
        ),
        5,
        33,
        1000,
    )
    assert len(_json(view)) == size
    return follow.FollowGap(model.SequenceRange(4, 5), marker), view


@pytest.mark.parametrize("size", [LIMIT - 1, LIMIT, LIMIT + 1])
async def test_t015_marker_wire_overflow_does_not_trim_endpoints_or_advance_gap_position(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    size: int,
) -> None:
    gap, view = t015_gap(size)
    async with service(process_credential, monkeypatch) as d:
        d.core.items = [
            follow.FollowBatch(None, (rx(3),)),
            follow.FollowBatch(gap, (rx(5),)),
            follow.FollowEnd("source_ended", 6),
        ]
        expected = [started(), {"type": "record", "record": rx_wire(rx(3))}]
        if size <= LIMIT:
            expected += [
                view,
                {"type": "record", "record": rx_wire(rx(5))},
                terminal(next_sequence=6, cutoff=6),
            ]
        else:
            expected += [terminal("delivery_too_large", 4, None)]
        frames(await d.service.request(ROUTE, BODY), expected)
        assert d.core.subscriptions[0].pulls == (3 if size <= LIMIT else 2)
        assert d.core.subscriptions[0].closed.is_set()


@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced"])
async def test_t015_all_variants_keep_maximum_escaped_annotation_and_binary_condition_exact(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
) -> None:
    records, views = seven_records(device)
    changed = list(records)
    assert isinstance(changed[3], model.OperationStartedEvidence)
    assert isinstance(changed[5], model.ClientAnnotationEvidence)
    text = '\x01\r\n\\"é😀' * 93 + "\t"  # Exactly1024 UTF-8 bytes.
    assert len(text.encode()) == 1024
    changed[3] = replace(changed[3], condition=b"\0\r\n\xff")
    changed[5] = replace(changed[5], text=text)
    views[3]["condition_base64"], views[5]["text"] = "AA0K/w==", text
    async with service(process_credential, monkeypatch) as d:
        d.core.captured = start(device)
        d.core.items = [
            follow.FollowBatch(None, tuple(changed)),
            follow.FollowEnd("source_ended", 10),
        ]
        response = await d.service.request(ROUTE, BODY)
        frames(
            response,
            [
                started(device),
                *({"type": "record", "record": r} for r in views),
                terminal(next_sequence=10, cutoff=10),
            ],
        )
        assert len(response.payload.split(b"\n")) == 10  # Nine complete frames only.


@pytest.mark.parametrize("where", ["started", "record", "gap"])
async def test_t015_service_encoder_accumulator_stops_at_limit_plus_one_for_escape_overflow(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    where: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from dutchmate_service import evidence_http

    maximum = 0

    class Buffer(bytearray):
        def extend(self, value: Any) -> None:
            nonlocal maximum
            super().extend(value)
            maximum = max(maximum, len(self))
            assert len(self) <= LIMIT + 1

    monkeypatch.setattr(evidence_http, "bytearray", Buffer, raising=False)
    caplog.set_level(logging.DEBUG)
    async with service(process_credential, monkeypatch) as d:
        if where == "started":
            d.core.captured = replace(
                start(),
                provenance=t015_provenance(
                    start().provenance, PRIVATE + "\x01" * LIMIT
                ),
            )
        elif where == "record":
            d.core.items = [
                follow.FollowBatch(
                    None,
                    (
                        replace(
                            rx(),
                            connection_id=model.ConnectionInstanceId(
                                PRIVATE + "\x01" * LIMIT
                            ),
                        ),
                    ),
                )
            ]
        else:
            gap, _ = t015_gap(LIMIT + 1)
            d.core.items = [
                follow.FollowBatch(None, (rx(),)),
                follow.FollowBatch(gap, ()),
            ]
        response = await d.service.request(ROUTE, BODY)
        assert maximum == LIMIT + 1
        if where == "started":
            _error(response, 413, "follow", "delivery_too_large")
        else:
            expected = [started()]
            if where == "gap":
                expected += [{"type": "record", "record": rx_wire(rx())}]
            frames(
                response,
                [
                    *expected,
                    terminal("delivery_too_large", 4 if where == "gap" else 3, None),
                ],
            )
        assert (
            PRIVATE not in caplog.text and d.service.token.decode() not in caplog.text
        )


@pytest.mark.parametrize(
    "trickle", [False, True], ids=["blocked", "cooperative-progress"]
)
async def test_t015_gap_send_expires_once_even_while_peer_makes_cooperative_progress(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    trickle: bool,
) -> None:
    gap, _ = t015_gap(4096)

    class GapClient(FrameClient):
        progress = 0

        async def send(self, message: Message) -> None:
            body = message.get("body", b"")
            if (
                trickle
                and body
                and message["type"] == "http.response.body"
                and json.loads(body)["type"] == "gap"
            ):
                self.blocked.set()
                self.attempts.append("gap")
                try:
                    while True:
                        await asyncio.sleep(0.1)
                        self.progress += 1
                except asyncio.CancelledError:
                    self.send_cancelled += 1
                    raise
            await super().send(message)

    async with service(process_credential, monkeypatch) as d:
        d.core.items = [
            follow.FollowBatch(None, (rx(),)),
            follow.FollowBatch(gap, (rx(5),)),
        ]
        client = GapClient(body=_json(BODY), hold_type="gap")
        task, _ = d.submit(client)
        try:
            await reached(client.blocked, task, client)
            began = asyncio.get_running_loop().time()
            await wait(asyncio.shield(task), 6.5)
            assert 4.5 <= asyncio.get_running_loop().time() - began <= 6.5
            assert client.send_cancelled == 1 and client.attempts == [
                "started",
                "record",
                "gap",
            ]
            assert client.progress >= 10 if trickle else client.progress == 0
            assert (
                d.core.subscriptions[0].closed.is_set()
                and d.core.subscriptions[0].pulls == 2
            )
            delivered = b"".join(
                m.get("body", b"")
                for m in client.messages
                if m["type"] == "http.response.body"
            )
            assert b'"terminal"' not in delivered
        finally:
            client.release_send.set()


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"], ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced"])
async def test_t015_real_loopback_heartbeat_during_real_submitted_journal_query(
    t011_composition: Any,
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    host: str,
    backend: int,
) -> None:
    from dutchmate_core.adapters import sqlite_evidence as sqlite
    from dutchmate_core.runtime import ObservationRuntime

    from test_evidence_http import _t014_core_helpers

    _t014_core_helpers(monkeypatch)
    from tests.contract.test_follow_runtime import RuntimeCase
    from tests.contract.test_observation_runtime import _profile
    from tests.fakes import BACKEND_FIXTURE_FACTORIES
    from tests.integration.test_annotations import assert_single_rx_owner

    journal = await SqliteEvidenceJournal.create_v3(
        tmp_path / "pending.db", _profile().session_policy
    )
    entered, release = threading.Event(), threading.Event()
    async with loopback(process_credential, monkeypatch, host) as (d, url):
        case = RuntimeCase(
            d.service.runtime,
            journal,
            BACKEND_FIXTURE_FACTORIES[backend],
            monkeypatch,
            3,
        )
        monkeypatch.setattr(
            d.service.runtime,
            "start_follow",
            ObservationRuntime.start_follow.__get__(d.service.runtime),
        )
        try:
            await case.activate()
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=3
            ) as client:
                async with client.stream(
                    "POST",
                    url + ROUTE,
                    headers=client_headers(d),
                    content=_json({"session_id": journal.session_id.value}),
                ) as response:
                    lines = response.aiter_lines()
                    first = json.loads(await wait(anext(lines)))
                    assert response.status_code == 200 and first["type"] == "started"
                    assert (
                        first["start_sequence"] == 1
                        and first["session_id"] == journal.session_id.value
                    )
                    original = sqlite._retrieve_page_on_worker

                    def query(
                        connection: Any,
                        policy: Any,
                        request: Any,
                        *,
                        schema_version: int = 1,
                    ) -> evidence.EvidencePage:
                        entered.set()
                        assert release.wait(5), (
                            "test failed to release actual journal worker"
                        )
                        return original(
                            connection, policy, request, schema_version=schema_version
                        )

                    with monkeypatch.context() as patch:
                        patch.setattr(sqlite, "_retrieve_page_on_worker", query)
                        record = await case.emit(b"\0\xff\r\n", 1)
                        assert await wait(asyncio.to_thread(entered.wait, 2))
                        queries = len(case.queries.requests)
                        samples = tuple(case.clock.samples)
                        try:
                            assert await wait(anext(lines), 2) == '{"type":"heartbeat"}'
                            assert not release.is_set() and case.queries.active == 1
                            assert (
                                len(case.queries.requests) == queries
                                and tuple(case.clock.samples) == samples
                            )
                        finally:
                            release.set()
                        value = json.loads(await wait(anext(lines)))
                        assert isinstance(record, model.RxBytesEvidence)
                        assert value == {"type": "record", "record": rx_wire(record)}
                    d.service.launch_context.request_stop()
                    assert json.loads(await wait(anext(lines))) == terminal(
                        "service_stopping", 2, None
                    )
                    with pytest.raises(StopAsyncIteration):
                        await wait(anext(lines))
                    assert response.headers["cache-control"] == "no-store"
                    assert "content-encoding" not in response.headers
                    assert_single_rx_owner(case.fixture)
        finally:
            release.set()
            await case.finish()
