"""Authenticated evidence delivery: typed wire cases and real active acceptance.

T010 controls only typed Core result facts for deterministic projection checks.
T014 uses the actual app-owned runtime, SQLite and normalized backend fixtures;
association/admission/retention/cleanup remain real Core behavior in both suites.
"""

import asyncio
import base64
import importlib
import importlib.util
import json
import logging
import shutil
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest
from dutchmate_core.adapters import sqlite_evidence, terminal_evidence
from dutchmate_core.evidence import (
    EvidenceCursor,
    EvidencePage,
    EvidencePageOutcome,
    EvidenceRetrievalRequest,
    JournalFailure,
    JournalFailureKind,
    JournalOperation,
)
from dutchmate_core.evidence_access import (
    EvidenceReadRejected,
    EvidenceReadRejectedKind,
    EvidenceSourceOpenFailure,
    OwnedEvidenceReadPort,
    PreparedEvidenceAccess,
    RunEvidencePage,
)
from dutchmate_core.model import (
    BackendCapabilities,
    BackendCapability,
    BackendConnectionProvenance,
    BackendObservationTimestamp,
    BackendObservationTimestampDomain,
    ConnectionInstanceId,
    ConnectionProvenanceSnapshot,
    EvidenceRangeReference,
    EvidenceReference,
    ObserverLossCause,
    ObserverLossEvidence,
    ObserverReportsUartLoss,
    PersistedConnectionProvenance,
    ProvenanceField,
    RetentionMarker,
    RetentionTimestampEndpoint,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentEndReason,
    SegmentId,
    SegmentProvenance,
    SegmentStartedEvidence,
    SequenceRange,
    SessionId,
    TimestampMeaning,
    TimestampObserver,
    TimestampUnit,
    UpstreamLossNotObservable,
)
from dutchmate_core.runtime import (
    PreparationFailure,
    PreparedObservationRun,
    RunId,
    RuntimeIssue,
    RuntimeIssueSource,
    RuntimeRejectedError,
    RuntimeRejectedKind,
)
from starlette.types import ASGIApp, Message, Scope

from dutchmate_service.bootstrap import PrivateBootstrap, ServiceConfig
from test_service_http import (
    _CONFIGS,
    AppLifespan,
    Exchange,
    _headers,
    _scope,
    _t009_module,
    _t009_runtime_spy,
    _T011ConnectedExchange,
)
from test_service_http import (
    process_credential as process_credential,
)

_RECORD = "/v1/evidence/record"
_PAGE = "/v1/evidence/page"
_MAX = 9223372036854775807
_BOUND = 1048576
_SESSION = SessionId("session-é")
_SECRET = "private-detail-token-path-SQL-sentinel"
_PAGE_BODY: dict[str, Any] = {
    "session_id": _SESSION.value,
    "start_inclusive": None,
    "end_exclusive": None,
    "max_records": 32,
    "max_charged_bytes": 65536,
    "cursor": None,
}
_RECORD_BODY = {"session_id": _SESSION.value, "sequence": 0}


def _json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")


def _token(document: object) -> str:
    return base64.urlsafe_b64encode(_json(document)).decode("ascii").rstrip("=")


def _cursor_document() -> dict[str, Any]:
    return {
        "version": 1,
        "session_id": _SESSION.value,
        "range_start_inclusive": 0,
        "range_end_exclusive": None,
        "snapshot_end_exclusive": 9,
        "next_sequence": 3,
    }


def _page(**changes: Any) -> EvidencePage:
    return replace(
        EvidencePage(
            (), 0, None, None, None, EvidencePageOutcome.COMPLETE, False, None, 0, None
        ),
        **changes,
    )


def _report(page: EvidencePage) -> RunEvidencePage:
    return RunEvidencePage(RunId("run-é"), _SESSION, page)


def _envelope(**changes: Any) -> dict[str, Any]:
    page: dict[str, Any] = {
        "records": [],
        "snapshot_end_exclusive": 0,
        "expired_range": None,
        "retention_marker": None,
        "never_existed_range": None,
        "outcome": "complete",
        "truncated": False,
        "continuation": None,
        "charged_bytes": 0,
        "next_record_required_bytes": None,
    }
    page.update(changes)
    return {"run_id": "run-é", "session_id": _SESSION.value, "page": page}


@dataclass
class ReadBoundary:
    result: RunEvidencePage = field(default_factory=lambda: _report(_page()))
    failure: Exception | None = None
    calls: list[EvidenceReference | EvidenceRetrievalRequest] = field(
        default_factory=list
    )

    async def read(
        self, value: EvidenceReference | EvidenceRetrievalRequest
    ) -> RunEvidencePage:
        self.calls.append(value)
        if self.failure is not None:
            raise self.failure
        return self.result


@dataclass
class Service:
    app: ASGIApp
    config: ServiceConfig
    token: bytes = field(repr=False)
    boundary: ReadBoundary
    launch_context: Any

    def scope(self, path: str, *, method: str = "POST") -> Scope:
        return _scope(
            self.config,
            _headers(self.config, self.token)
            + [(b"content-type", b"application/json")],
            path=path,
            method=method,
        )

    async def request(
        self,
        path: str,
        body: object,
        *,
        raw: bytes | None = None,
        scope: Scope | None = None,
        exchange: Exchange | None = None,
    ) -> Exchange:
        response = exchange or _T011ConnectedExchange(
            body=_json(body) if raw is None else raw
        )
        await asyncio.wait_for(
            self.app(scope or self.scope(path), response.receive, response.send),
            timeout=3.0,
        )
        return response


@asynccontextmanager
async def _service(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig = _CONFIGS[0],
    *,
    stub_read: bool = True,
) -> AsyncIterator[Service]:
    boundary = ReadBoundary()
    created, _ = _t009_runtime_spy(_t009_module(), monkeypatch)

    def forbidden(*args: object, **kwargs: object) -> Any:
        del args, kwargs
        pytest.fail("delivery test cannot create/open a journal or terminal reader")

    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "open", forbidden)
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "create", forbidden)
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "create_v2", forbidden)
    with process_credential(config) as (owner, token):
        context = _t009_module()._LaunchContext(config, owner)
        app = _t009_module().create_app(config, _launch_context=context)
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        assert len(created) == 1
        if stub_read:
            monkeypatch.setattr(created[0], "read_record", boundary.read)
            monkeypatch.setattr(created[0], "read_page", boundary.read)
        try:
            yield Service(app, config, token, boundary, context)
        finally:
            await lifespan.finish()


def _error(response: Exchange, status: int, source: str, code: str) -> None:
    assert response.status == status, response.payload
    assert json.loads(response.payload) == {"error": {"source": source, "code": code}}
    assert response.headers[b"cache-control"] == b"no-store"
    assert response.headers[b"content-type"].split(b";")[0] == b"application/json"
    assert _SECRET.encode() not in response.payload


def _success(response: Exchange, expected: object) -> None:
    assert response.status == 200, response.payload
    assert response.payload == _json(expected)
    assert len(response.payload) <= _BOUND
    assert response.headers[b"cache-control"] == b"no-store"
    assert response.headers[b"content-type"].split(b";")[0] == b"application/json"


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("path,body", [(_RECORD, _RECORD_BODY), (_PAGE, _PAGE_BODY)])
@pytest.mark.asyncio
async def test_literal_post_routes_deliver_exact_closed_envelope(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    path: str,
    body: dict[str, Any],
) -> None:
    async with _service(process_credential, monkeypatch, config) as service:
        _success(await service.request(path, body), _envelope())
        expected = (
            EvidenceReference(_SESSION, 0)
            if path == _RECORD
            else EvidenceRetrievalRequest(_SESSION, 32, 65536)
        )
        assert service.boundary.calls == [expected]


@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "OPTIONS"])
@pytest.mark.asyncio
async def test_recognized_route_rejects_other_verbs_without_body_or_read(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    method: str,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        response = await service.request(
            path,
            {},
            scope=service.scope(path, method=method),
            exchange=Exchange(forbid_receive=True),
        )
        _error(response, 405, "request", "method_not_allowed")
        assert service.boundary.calls == []


@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.parametrize("variant", ["slash", "encoded", "case"])
@pytest.mark.asyncio
async def test_no_route_aliases_or_path_normalization(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    variant: str,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        scope = service.scope(path)
        if variant == "encoded":
            scope["raw_path"] = path.replace("evidence", "%65vidence").encode()
        else:
            alias = (
                path + "/"
                if variant == "slash"
                else path.replace("evidence", "Evidence")
            )
            scope = service.scope(alias)
        response = await service.request(
            path, {}, scope=scope, exchange=Exchange(forbid_receive=True)
        )
        _error(response, 404, "request", "route_not_found")
        assert service.boundary.calls == []


@pytest.mark.parametrize("path", [_RECORD, _PAGE])
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
@pytest.mark.asyncio
async def test_existing_security_precedes_body_association_and_source(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    case: str,
    status: int,
    code: str,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        scope = service.scope(path)
        headers = list(scope["headers"])
        if case == "peer":
            scope["client"] = ("192.0.2.1", 12345)
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
                    b"private-browser",
                )
            )
        elif case == "query":
            scope["query_string"] = b"session_id=private"
        elif case == "missing_auth":
            headers = [(k, v) for k, v in headers if k != b"authorization"]
        elif case == "wrong_auth":
            headers = [
                (k, b"Bearer " + b"0" * 64 if k == b"authorization" else v)
                for k, v in headers
            ]
        elif case == "duplicate_auth":
            headers.append((b"authorization", b"Bearer " + service.token))
        scope["headers"] = headers
        response = await service.request(
            path, {}, scope=scope, exchange=Exchange(forbid_receive=True)
        )
        _error(response, status, "request", code)
        if status == 401:
            assert response.headers[b"www-authenticate"] == b"Bearer"
        assert service.token not in response.payload
        assert service.boundary.calls == []


_INVALID: list[tuple[str, dict[str, Any]]] = []
value: Any
for path, template in ((_RECORD, _RECORD_BODY), (_PAGE, _PAGE_BODY)):
    for key in template:
        _INVALID.append((path, {k: v for k, v in template.items() if k != key}))
    for key in ("journal_path", "database", "run_id", "extra"):
        _INVALID.append((path, {**template, key: _SECRET}))
    for value in ("", "\0", "x\0y", "é" * 129, "x" * 257, None, True, 42, []):
        _INVALID.append((path, {**template, "session_id": value}))
for value in (-1, _MAX + 1, True, False, 1.0, "1", None, []):
    _INVALID.append((_RECORD, {**_RECORD_BODY, "sequence": value}))
for key in ("start_inclusive", "end_exclusive"):
    for value in (-1, _MAX + 1, True, False, 1.0, "1", []):
        _INVALID.append(
            (
                _PAGE,
                {**_PAGE_BODY, "start_inclusive": 0, "end_exclusive": 2, key: value},
            )
        )
for start, end in ((None, 1), (0, None), (2, 1)):
    _INVALID.append(
        (_PAGE, {**_PAGE_BODY, "start_inclusive": start, "end_exclusive": end})
    )
for key, limit in (("max_records", 4096), ("max_charged_bytes", _BOUND)):
    for value in (0, -1, limit + 1, True, False, 1.0, "1", None, []):
        _INVALID.append((_PAGE, {**_PAGE_BODY, key: value}))
for value in ("", "é", "A" * 1025, True, 1, [], "a=", "a+", "a/", "a "):
    _INVALID.append((_PAGE, {**_PAGE_BODY, "cursor": value}))


@pytest.mark.parametrize("path,body", _INVALID)
@pytest.mark.asyncio
async def test_closed_body_and_exact_input_domains_reject_before_core(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: dict[str, Any],
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        _error(await service.request(path, body), 422, "request", "invalid_request")
        assert service.boundary.calls == []


@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b"[]",
        b"{} trailing",
        b"\xff",
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"session_id":"x","session_id":"x"}',
        b'{"session_id":"\\ud800"}',
    ],
)
@pytest.mark.asyncio
async def test_strict_json_utf8_duplicates_nonfinite_and_root_shape(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    raw: bytes,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        _error(
            await service.request(path, {}, raw=raw), 422, "request", "invalid_request"
        )
        assert service.boundary.calls == []


@pytest.mark.parametrize(
    "media,status",
    [
        (b"application/json", 200),
        (b"application/json; charset=UTF-8", 200),
        (b"text/json", 415),
        (b"application/json; charset=latin-1", 415),
        (b"application/json; charset=utf-8; charset=utf-8", 415),
        (b"application/json; profile=x", 415),
    ],
)
@pytest.mark.parametrize("path,body", [(_RECORD, _RECORD_BODY), (_PAGE, _PAGE_BODY)])
@pytest.mark.asyncio
async def test_existing_json_media_contract(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    media: bytes,
    status: int,
    path: str,
    body: dict[str, Any],
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        scope = service.scope(path)
        scope["headers"] = [
            (k, media if k == b"content-type" else v) for k, v in scope["headers"]
        ]
        response = await service.request(path, body, scope=scope)
        if status == 200:
            _success(response, _envelope())
        else:
            _error(response, status, "request", "unsupported_media_type")
            assert service.boundary.calls == []


@dataclass
class ChunkedExchange(_T011ConnectedExchange):
    chunks: list[bytes] = field(default_factory=list)

    async def receive(self) -> Message:
        if self.receives < len(self.chunks):
            index = self.receives
            self.receives += 1
            return {
                "type": "http.request",
                "body": self.chunks[index],
                "more_body": index + 1 < len(self.chunks),
            }
        return await super().receive()


@pytest.mark.parametrize("path,body", [(_RECORD, _RECORD_BODY), (_PAGE, _PAGE_BODY)])
@pytest.mark.parametrize("size", [16384, 16385])
@pytest.mark.parametrize("declared", [b"0", b"16384", b"999999"])
@pytest.mark.asyncio
async def test_actual_chunked_body_cap_ignores_declared_content_length(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: dict[str, Any],
    size: int,
    declared: bytes,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        raw = _json(body)
        raw += b" " * (size - len(raw))
        exchange = ChunkedExchange(chunks=[raw[:8192], raw[8192:16384], raw[16384:]])
        scope = service.scope(path)
        scope["headers"].append((b"content-length", declared))
        response = await service.request(path, {}, scope=scope, exchange=exchange)
        if size == 16384:
            _success(response, _envelope())
            assert len(service.boundary.calls) == 1
        else:
            _error(response, 413, "request", "payload_too_large")
            assert service.boundary.calls == []


@pytest.mark.parametrize(
    "session", [" ", "x" * 256, "é" * 128, "e\u0301", " /opaque/id "]
)
@pytest.mark.parametrize("sequence", [0, _MAX])
@pytest.mark.asyncio
async def test_session_byte_edges_preserved_exactly_and_max_reference_admitted(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    session: str,
    sequence: int,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        service.boundary.result = _report(_page(outcome=EvidencePageOutcome.NOT_FOUND))
        _success(
            await service.request(
                _RECORD, {"session_id": session, "sequence": sequence}
            ),
            _envelope(outcome="not_found"),
        )
        assert service.boundary.calls == [
            EvidenceReference(SessionId(session), sequence)
        ]


@pytest.mark.parametrize("start,end", [(None, None), (0, 0), (0, _MAX), (_MAX, _MAX)])
@pytest.mark.parametrize("records,charged", [(1, 1), (4096, _BOUND)])
@pytest.mark.asyncio
async def test_paired_range_and_budget_edges_construct_only_normalized_core_values(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    start: int | None,
    end: int | None,
    records: int,
    charged: int,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        body = {
            **_PAGE_BODY,
            "start_inclusive": start,
            "end_exclusive": end,
            "max_records": records,
            "max_charged_bytes": charged,
        }
        _success(await service.request(_PAGE, body), _envelope())
        if start is None:
            reference: SessionId | EvidenceRangeReference = _SESSION
        else:
            assert end is not None
            reference = EvidenceRangeReference(_SESSION, start, end)
        assert service.boundary.calls == [
            EvidenceRetrievalRequest(reference, records, charged)
        ]


@pytest.mark.asyncio
async def test_canonical_cursor_round_trip_preserves_snapshot_with_changed_budgets(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        cursor = EvidenceCursor(_SESSION, 0, None, 9, 3)
        token = _token(_cursor_document())
        service.boundary.result = _report(
            _page(
                snapshot_end_exclusive=9,
                truncated=True,
                continuation=cursor,
                next_record_required_bytes=2000000,
            )
        )
        _success(
            await service.request(
                _PAGE,
                {
                    **_PAGE_BODY,
                    "cursor": token,
                    "max_records": 1,
                    "max_charged_bytes": 1,
                },
            ),
            _envelope(
                snapshot_end_exclusive=9,
                truncated=True,
                continuation=token,
                next_record_required_bytes=2000000,
            ),
        )
        assert service.boundary.calls == [
            EvidenceRetrievalRequest(_SESSION, 1, 1, cursor)
        ]


_BAD_CURSORS = [
    _token({**_cursor_document(), key: value})
    for key, value in (
        ("version", True),
        ("version", 2),
        ("extra", 1),
        ("next_sequence", True),
        ("next_sequence", -1),
        ("next_sequence", 10),
        ("snapshot_end_exclusive", _MAX + 1),
    )
]
_BAD_CURSORS += [
    _token({k: v for k, v in _cursor_document().items() if k != "version"}),
    _token(dict(reversed(list(_cursor_document().items())))),
    base64.urlsafe_b64encode(json.dumps(_cursor_document()).encode())
    .decode()
    .rstrip("="),
    base64.urlsafe_b64encode(b'{"version":1,"version":1}').decode().rstrip("="),
    base64.urlsafe_b64encode(b'{"version":NaN}').decode().rstrip("="),
    base64.urlsafe_b64encode(b"\xff").decode().rstrip("="),
    _token(_cursor_document()) + "=",
    "A",
    "Zh",
]


@pytest.mark.parametrize("token", _BAD_CURSORS)
@pytest.mark.asyncio
async def test_cursor_requires_exact_canonical_closed_ordered_utf8_document(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    token: str,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        _error(
            await service.request(_PAGE, {**_PAGE_BODY, "cursor": token}),
            422,
            "request",
            "invalid_request",
        )
        assert service.boundary.calls == []


_FAILURES: list[tuple[Exception, int, str, str]] = [
    (
        EvidenceReadRejected(cast(EvidenceReadRejectedKind, kind)),
        status,
        "evidence",
        kind,
    )
    for kind, status in (
        ("no_associated_session", 404),
        ("session_not_associated", 409),
        ("read_unavailable", 503),
        ("source_changed", 409),
        ("read_capacity", 503),
    )
]
_FAILURES += [
    (
        JournalFailure(JournalOperation.RETRIEVE, kind, _SECRET),
        {
            JournalFailureKind.INVALID_INPUT: 422,
            JournalFailureKind.SESSION_MISMATCH: 409,
            JournalFailureKind.JOURNAL_MISSING: 404,
            JournalFailureKind.BUSY: 503,
            JournalFailureKind.CLOSED: 409,
        }.get(kind, 500),
        "journal",
        kind.value,
    )
    for kind in JournalFailureKind
]
_FAILURES += [
    (RuntimeRejectedError(kind), status, "runtime", kind.value)
    for kind, status in (
        (RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT, 500),
        (RuntimeRejectedKind.INVALID_REQUEST, 422),
    )
]
_FAILURES += [(RuntimeError(_SECRET), 500, "service", "internal_failure")]


@pytest.mark.parametrize(
    "failure,status,source,code",
    _FAILURES,
    ids=lambda value: (
        str(value) if not isinstance(value, Exception) else type(value).__name__
    ),
)
@pytest.mark.parametrize("path,body", [(_RECORD, _RECORD_BODY), (_PAGE, _PAGE_BODY)])
@pytest.mark.asyncio
async def test_all_declared_read_failures_map_without_detail_or_operation_leak(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status: int,
    source: str,
    code: str,
    path: str,
    body: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with _service(process_credential, monkeypatch) as service:
        service.boundary.failure = failure
        _error(await service.request(path, body), status, source, code)
        assert len(service.boundary.calls) == 1
        assert _SECRET not in caplog.text
        assert service.token.decode() not in caplog.text


@pytest.mark.parametrize(
    "key,value", [("max_records", 33), ("max_charged_bytes", 65537)]
)
@pytest.mark.asyncio
async def test_within_wire_above_policy_error_remains_journal_invalid_input(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: int,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        # Core enforces captured SessionPolicy; the adapter must not relabel it.
        service.boundary.failure = JournalFailure(
            JournalOperation.RETRIEVE, JournalFailureKind.INVALID_INPUT, _SECRET
        )
        _error(
            await service.request(_PAGE, {**_PAGE_BODY, key: value}),
            422,
            "journal",
            "invalid_input",
        )
        assert len(service.boundary.calls) == 1


@pytest.mark.parametrize("path,body", [(_RECORD, _RECORD_BODY), (_PAGE, _PAGE_BODY)])
@pytest.mark.asyncio
async def test_actual_inactive_runtime_has_no_associated_session_without_any_open(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: dict[str, Any],
) -> None:
    async with _service(process_credential, monkeypatch, stub_read=False) as service:
        _error(
            await service.request(path, body), 404, "evidence", "no_associated_session"
        )


def _domain(device: bool) -> BackendObservationTimestampDomain:
    return BackendObservationTimestampDomain(
        "device-clock" if device else "host-clock",
        TimestampObserver.DEVICE if device else TimestampObserver.HOST,
        TimestampMeaning.OBSERVATION,
        TimestampUnit.TICK if device else TimestampUnit.NANOSECOND,
        "device-origin" if device else "host-origin",
    )


def _domain_wire(device: bool) -> dict[str, Any]:
    return {
        "domain_id": "device-clock" if device else "host-clock",
        "observer": "device" if device else "host",
        "meaning": "observation",
        "unit": "tick" if device else "nanosecond",
        "origin_id": "device-origin" if device else "host-origin",
    }


def _provenance(device: bool) -> tuple[SegmentProvenance, dict[str, Any]]:
    # Basic/Enhanced-shaped public facts; no backend-name policy or emulation.
    capabilities = frozenset(
        {BackendCapability.UART_RECEIVE}
        | ({BackendCapability.GPIO_CONTROL} if device else set())
    )
    fields = (
        ProvenanceField("a-null", None),
        ProvenanceField("b-bool", True),
        ProvenanceField("c-int", 123),
        ProvenanceField("d-text", 'é/\\"\n'),
    )
    provenance = SegmentProvenance(
        ConnectionInstanceId("connection-é"),
        SegmentId("segment-é"),
        BackendCapabilities(capabilities),
        _domain(device),
        ObserverReportsUartLoss("observer", "upstream")
        if device
        else UpstreamLossNotObservable(),
        PersistedConnectionProvenance(
            ConnectionProvenanceSnapshot(
                1, "fixture-device" if device else "fixture-host", 3, fields
            )
        ),
    )
    wire = {
        "connection_id": "connection-é",
        "segment_id": "segment-é",
        "capabilities": ["gpio_control", "uart_receive"]
        if device
        else ["uart_receive"],
        "backend_observation_timestamp_domain": _domain_wire(device),
        "loss_observability": {
            "kind": "observer_reports_uart_loss",
            "observer_id": "observer",
            "scope": "upstream",
        }
        if device
        else {"kind": "upstream_loss_not_observable"},
        "connection_provenance": {
            "envelope_version": 1,
            "backend_kind": "fixture-device" if device else "fixture-host",
            "backend_schema_version": 3,
            "fields": [
                {"name": "a-null", "value": None},
                {"name": "b-bool", "value": True},
                {"name": "c-int", "value": 123},
                {"name": "d-text", "value": 'é/\\"\n'},
            ],
        },
    }
    return provenance, wire


@pytest.mark.parametrize(
    "device", [False, True], ids=["Basic-shaped", "Enhanced-shaped"]
)
@pytest.mark.asyncio
async def test_binary_records_all_variants_provenance_order_and_segment_boundaries(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        provenance, wire = _provenance(device)
        connection, segment = provenance.connection_id, provenance.segment_id
        records: list[Any] = [SegmentStartedEvidence(0, provenance)]
        expected: list[dict[str, Any]] = [
            {"kind": "segment_started", "sequence": 0, "provenance": wire}
        ]
        for payload in (b"", bytes(range(256)), b"\x00\xff\xfe\r\n\r\n"):
            sequence = len(records)
            observed = BackendObservationTimestamp(_domain(device).domain_id, sequence)
            records.append(
                RxBytesEvidence(sequence, connection, segment, payload, observed)
            )
            expected.append(
                {
                    "kind": "rx_bytes",
                    "sequence": sequence,
                    "connection_id": connection.value,
                    "segment_id": segment.value,
                    "observed_at": {"domain_id": observed.domain_id, "value": sequence},
                    "payload_base64": base64.b64encode(payload).decode("ascii"),
                }
            )
        for cause, lost in (
            (ObserverLossCause.OVERFLOW, 7),
            (ObserverLossCause.OTHER_OBSERVED_LOSS, None),
        ):
            sequence = len(records)
            observed = BackendObservationTimestamp(_domain(device).domain_id, sequence)
            records.append(
                ObserverLossEvidence(
                    sequence,
                    connection,
                    segment,
                    "observer",
                    "upstream",
                    cause,
                    lost,
                    observed,
                )
            )
            expected.append(
                {
                    "kind": "observer_loss",
                    "sequence": sequence,
                    "connection_id": connection.value,
                    "segment_id": segment.value,
                    "observer_id": "observer",
                    "scope": "upstream",
                    "cause": cause.value,
                    "lost_bytes": lost,
                    "observed_at": {"domain_id": observed.domain_id, "value": sequence},
                }
            )
        for reason in SegmentEndReason:
            sequence = len(records)
            records.append(SegmentEndedEvidence(sequence, connection, segment, reason))
            expected.append(
                {
                    "kind": "segment_ended",
                    "sequence": sequence,
                    "connection_id": connection.value,
                    "segment_id": segment.value,
                    "reason": reason.value,
                }
            )
        # A second interval must retain its independent timestamp and connection facts.
        other, other_wire = _provenance(not device)
        other = replace(
            other,
            connection_id=ConnectionInstanceId("second-connection"),
            segment_id=SegmentId("second-segment"),
        )
        other_wire.update(
            connection_id="second-connection", segment_id="second-segment"
        )
        records.append(SegmentStartedEvidence(len(records), other))
        expected.append(
            {
                "kind": "segment_started",
                "sequence": len(expected),
                "provenance": other_wire,
            }
        )
        service.boundary.result = _report(
            _page(
                records=tuple(records),
                snapshot_end_exclusive=len(records),
                charged_bytes=4242,
            )
        )
        response = await service.request(_PAGE, _PAGE_BODY)
        _success(
            response,
            _envelope(
                records=expected,
                snapshot_end_exclusive=len(records),
                charged_bytes=4242,
            ),
        )
        delivered = json.loads(response.payload)["page"]["records"]
        assert base64.b64decode(delivered[2]["payload_base64"], validate=True) == bytes(
            range(256)
        )
        assert len(service.boundary.calls) == 1


@pytest.mark.parametrize("outcome", list(EvidencePageOutcome))
@pytest.mark.parametrize("endpoints", [False, True])
@pytest.mark.asyncio
async def test_outcomes_and_retention_markers_preserve_independent_clock_origins(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    outcome: EvidencePageOutcome,
    endpoints: bool,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        first = (
            RetentionTimestampEndpoint(
                BackendObservationTimestamp("host-clock", 90), _domain(False)
            )
            if endpoints
            else None
        )
        last = (
            RetentionTimestampEndpoint(
                BackendObservationTimestamp("device-clock", 2), _domain(True)
            )
            if endpoints
            else None
        )
        marker = RetentionMarker(SequenceRange(0, 3), first, last, 3, 5, 700)
        service.boundary.result = _report(
            _page(
                snapshot_end_exclusive=9,
                expired_range=SequenceRange(1, 3),
                retention_marker=marker,
                never_existed_range=SequenceRange(9, 12),
                outcome=outcome,
                charged_bytes=123,
            )
        )
        expected_marker = {
            "expired_range": {"start_inclusive": 0, "end_exclusive": 3},
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
            "discarded_record_count": 3,
            "discarded_rx_payload_byte_count": 5,
            "discarded_charged_bytes": 700,
        }
        _success(
            await service.request(_PAGE, _PAGE_BODY),
            _envelope(
                snapshot_end_exclusive=9,
                expired_range={"start_inclusive": 1, "end_exclusive": 3},
                retention_marker=expected_marker,
                never_existed_range={"start_inclusive": 9, "end_exclusive": 12},
                outcome=outcome.value,
                charged_bytes=123,
            ),
        )


@pytest.mark.parametrize("path,body", [(_RECORD, _RECORD_BODY), (_PAGE, _PAGE_BODY)])
@pytest.mark.parametrize("size,status", [(780000, 200), (786432, 413), (1048576, 413)])
@pytest.mark.asyncio
async def test_binary_encoding_has_independent_whole_envelope_delivery_cap(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: dict[str, Any],
    size: int,
    status: int,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        payload = b"\xff" * size
        record = RxBytesEvidence(
            0,
            ConnectionInstanceId("c"),
            SegmentId("s"),
            payload,
            BackendObservationTimestamp("clock", 0),
        )
        service.boundary.result = _report(
            _page(records=(record,), snapshot_end_exclusive=1, charged_bytes=size)
        )
        original = service.boundary.result
        response = await service.request(path, body)
        if status == 200:
            _success(
                response,
                _envelope(
                    records=[
                        {
                            "kind": "rx_bytes",
                            "sequence": 0,
                            "connection_id": "c",
                            "segment_id": "s",
                            "observed_at": {"domain_id": "clock", "value": 0},
                            "payload_base64": base64.b64encode(payload).decode("ascii"),
                        }
                    ],
                    snapshot_end_exclusive=1,
                    charged_bytes=size,
                ),
            )
        else:
            _error(response, 413, "evidence", "delivery_too_large")
        assert service.boundary.result is original
        assert (
            len(service.boundary.calls) == 1
        )  # Never refetch or trim to manufacture a page.


@pytest.mark.asyncio
async def test_oversized_mandatory_provenance_rejects_whole_report_without_omission(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        provenance, _ = _provenance(False)
        provenance = replace(
            provenance,
            connection_provenance=PersistedConnectionProvenance(
                ConnectionProvenanceSnapshot(
                    1, "opaque", 1, (ProvenanceField("metadata", "é" * 524288),)
                )
            ),
        )
        service.boundary.result = _report(
            _page(
                records=(SegmentStartedEvidence(0, provenance),),
                snapshot_end_exclusive=1,
                charged_bytes=_BOUND,
            )
        )
        _error(
            await service.request(_PAGE, _PAGE_BODY),
            413,
            "evidence",
            "delivery_too_large",
        )
        assert len(service.boundary.calls) == 1


@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.asyncio
async def test_latched_service_stop_precedes_body_and_core_read(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        service.launch_context.request_stop()
        response = await service.request(
            path, {}, exchange=Exchange(forbid_receive=True)
        )
        _error(response, 503, "service", "stopping")
        assert service.boundary.calls == []


@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.asyncio
async def test_not_started_service_rejects_before_body_or_runtime_construction(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    config = _CONFIGS[0]
    created, _ = _t009_runtime_spy(_t009_module(), monkeypatch)
    with process_credential(config) as (owner, token):
        context = _t009_module()._LaunchContext(config, owner)
        app = _t009_module().create_app(config, _launch_context=context)
        service = Service(app, config, token, ReadBoundary(), context)
        response = await service.request(
            path, {}, exchange=Exchange(forbid_receive=True)
        )
        _error(response, 503, "service", "stopping")
        assert created == [] and service.boundary.calls == []


@pytest.mark.parametrize("path,body", [(_RECORD, _RECORD_BODY), (_PAGE, _PAGE_BODY)])
@pytest.mark.asyncio
async def test_duplicate_field_in_otherwise_valid_body_is_rejected(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: dict[str, Any],
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        raw = _json(body)
        raw = '{"session_id":"session-é",'.encode() + raw[1:]
        _error(
            await service.request(path, {}, raw=raw), 422, "request", "invalid_request"
        )
        assert service.boundary.calls == []


@pytest.mark.parametrize("difference", [-1, 0, 1])
@pytest.mark.asyncio
async def test_whole_canonical_response_exact_byte_boundary_including_metadata(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    difference: int,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        provenance, wire = _provenance(False)
        wire["connection_provenance"] = {
            "envelope_version": 1,
            "backend_kind": "opaque",
            "backend_schema_version": 1,
            "fields": [{"name": "metadata", "value": ""}],
        }
        expected = _envelope(
            records=[{"kind": "segment_started", "sequence": 0, "provenance": wire}],
            snapshot_end_exclusive=1,
            charged_bytes=1,
        )
        metadata = "x" * (_BOUND + difference - len(_json(expected)))
        wire["connection_provenance"]["fields"][0]["value"] = metadata
        assert len(_json(expected)) == _BOUND + difference
        provenance = replace(
            provenance,
            connection_provenance=PersistedConnectionProvenance(
                ConnectionProvenanceSnapshot(
                    1, "opaque", 1, (ProvenanceField("metadata", metadata),)
                )
            ),
        )
        service.boundary.result = _report(
            _page(
                records=(SegmentStartedEvidence(0, provenance),),
                snapshot_end_exclusive=1,
                charged_bytes=1,
            )
        )
        response = await service.request(_PAGE, _PAGE_BODY)
        if difference <= 0:
            _success(response, expected)
        else:
            _error(response, 413, "evidence", "delivery_too_large")
        assert len(service.boundary.calls) == 1


@pytest.mark.asyncio
async def test_base64_overflow_detected_before_an_oversized_encoded_allocation(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        encode = base64.b64encode

        def guarded_encode(data: Any, *args: Any, **kwargs: Any) -> bytes:
            assert 4 * ((len(data) + 2) // 3) <= _BOUND, "oversized base64 allocation"
            return encode(data, *args, **kwargs)

        monkeypatch.setattr(base64, "b64encode", guarded_encode)
        # Cover both module-qualified calls and direct stdlib imports, without
        # prescribing a future service encoder's private helper names.
        for module_name, module in tuple(sys.modules.items()):
            if module_name.startswith("dutchmate_service") and module is not None:
                for name, imported in tuple(vars(module).items()):
                    if imported is encode:
                        monkeypatch.setattr(module, name, guarded_encode)
        record = RxBytesEvidence(
            0,
            ConnectionInstanceId("c"),
            SegmentId("s"),
            b"\xff" * _BOUND,
            BackendObservationTimestamp("clock", 0),
        )
        service.boundary.result = _report(
            _page(records=(record,), snapshot_end_exclusive=1, charged_bytes=_BOUND)
        )
        _error(
            await service.request(_PAGE, _PAGE_BODY),
            413,
            "evidence",
            "delivery_too_large",
        )
        assert len(service.boundary.calls) == 1


@pytest.mark.asyncio
async def test_unexpected_provenance_projection_failure_is_private_internal_failure(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class UnprojectableProvenance(BackendConnectionProvenance):
        def to_snapshot(self) -> ConnectionProvenanceSnapshot:
            raise RuntimeError(_SECRET)

    caplog.set_level(logging.DEBUG)
    async with _service(process_credential, monkeypatch) as service:
        provenance, _ = _provenance(False)
        provenance = replace(
            provenance, connection_provenance=UnprojectableProvenance()
        )
        service.boundary.result = _report(
            _page(
                records=(SegmentStartedEvidence(0, provenance),),
                snapshot_end_exclusive=1,
            )
        )
        _error(
            await service.request(_PAGE, _PAGE_BODY), 500, "service", "internal_failure"
        )
        assert len(service.boundary.calls) == 1
        assert _SECRET not in caplog.text


@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.asyncio
async def test_body_disconnect_emits_no_response_and_submits_no_read(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    class DisconnectedBody(Exchange):
        async def receive(self) -> Message:
            self.receives += 1
            return {"type": "http.disconnect"}

    async with _service(process_credential, monkeypatch) as service:
        exchange = DisconnectedBody()
        # Both a silent gate return and aborted delivery are valid after loss.
        # Neither may emit a replacement response or admit a Core read.
        try:
            await service.request(path, {}, exchange=exchange)
        except asyncio.CancelledError:
            pass
        assert exchange.receives == 1
        assert exchange.messages == []
        assert service.boundary.calls == []


@dataclass
class ActiveEvidenceService:
    """T014 actual app/runtime/journal composition, shared with CLI acceptance."""

    app: ASGIApp
    config: ServiceConfig
    token: bytes = field(repr=False)
    run: Any
    journal_path: Path
    queries: list[str] = field(default_factory=list)
    serving: ContextVar[bool] = field(
        default_factory=lambda: ContextVar("t014_serving", default=False)
    )

    async def request(self, path: str, body: dict[str, Any]) -> Exchange:
        scope = _scope(
            self.config,
            _headers(self.config, self.token)
            + [(b"content-type", b"application/json")],
            path=path,
            method="POST",
        )
        response = _T011ConnectedExchange(body=_json(body))
        token = self.serving.set(True)
        try:
            await asyncio.wait_for(
                self.app(scope, response.receive, response.send), timeout=3
            )
        finally:
            self.serving.reset(token)
        return response


def _t014_core_helpers(patch: pytest.MonkeyPatch) -> Any:
    # Load the existing test support package explicitly when focused service/CLI
    # selection has not collected Core. Never alter production import paths.
    root = Path(__file__).resolve().parents[3] / "core/tests"
    if "tests" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "tests", root / "__init__.py", submodule_search_locations=[str(root)]
        )
        assert spec is not None and spec.loader is not None
        package = importlib.util.module_from_spec(spec)
        patch.setitem(sys.modules, "tests", package)
        spec.loader.exec_module(package)
    assert Path(sys.modules["tests"].__file__ or "").resolve() == root / "__init__.py"
    return importlib.import_module("tests.integration.test_evidence_access")


@asynccontextmanager
async def t014_active_service(
    tmp_path: Path,
    account_home: Path,
    patch: pytest.MonkeyPatch,
    backend_index: int,
    config: ServiceConfig = _CONFIGS[0],
    *,
    retained: int = 100,
) -> AsyncIterator[ActiveEvidenceService]:
    core = _t014_core_helpers(patch)
    created, _ = _t009_runtime_spy(_t009_module(), patch)
    owner = PrivateBootstrap.acquire(config)
    lifespan: AppLifespan | None = None
    run: Any = None
    try:
        owner.mark_unconfirmed()
        owner.publish_credential()
        token = (
            account_home / ".local/state/dutchmate/service/credential"
        ).read_bytes()[:-1]
        app = _t009_module().create_app(
            config, _launch_context=_t009_module()._LaunchContext(config, owner)
        )
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        assert len(created) == 1
        profile = core._profile()
        profile = replace(
            profile,
            session_policy=replace(
                profile.session_policy, max_retained_records=retained
            ),
        )
        journal = await sqlite_evidence.SqliteEvidenceJournal.create(
            tmp_path / "active.sqlite3", profile.session_policy
        )
        run = core.JournalRun(
            journal,
            core.BACKEND_FIXTURE_FACTORIES[backend_index](),
            runtime=created[0],
            profile=profile,
        )
        service = ActiveEvidenceService(app, config, token, run, tmp_path / "active.sqlite3")

        def forbidden(*args: object, **kwargs: object) -> None:
            pytest.fail(
                "active retrieval cannot open another or terminal database connection"
            )

        import sqlite3

        patch.setattr(sqlite3, "connect", forbidden)
        patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "open", forbidden)
        for name in ("retrieve", "resolve_record"):
            original = getattr(journal, name)

            async def observed(
                value: object, *, call: Any = original, kind: str = name
            ) -> Any:
                assert service.serving.get(), (
                    "CLI cannot bypass HTTP and query Core's journal"
                )
                service.queries.append(kind)
                return await call(value)

            patch.setattr(journal, name, observed)
        yield service
    finally:
        try:
            if run is not None:
                await run.finish()
        finally:
            if lifespan is not None:
                await lifespan.finish()
            owner.invalidate_credential()
            if created:
                status = created[0].status()
                owner.confirm_cleanup(
                    owner_settled=status.owner_settled,
                    physical_release_confirmed=status.physical_release_confirmed,
                    recorder_close_confirmed=status.recorder_close_confirmed,
                )
            owner.release()
        assert len(created) == 1
        if run is not None:
            assert run.recorder.close_calls == 1


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.asyncio
async def test_t014_real_active_journal_binary_and_provenance_pass_actual_auth_projection(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
    config: ServiceConfig,
) -> None:
    async with t014_active_service(
        tmp_path, account_home, monkeypatch, backend_index, config
    ) as service:
        _, start = await service.run.active()
        payload = bytes(range(256)) + b"\0\xff\xfe\r\n"
        await service.run.emit(payload, sequence=1, timestamp=11)
        session = service.run.journal.session_id.value
        response = await service.request(
            _RECORD, {"session_id": session, "sequence": 1}
        )
        assert (
            response.status == 200 and response.headers[b"cache-control"] == b"no-store"
        )
        record = json.loads(response.payload)["page"]["records"][0]
        assert base64.b64decode(record["payload_base64"], validate=True) == payload
        page = await service.request(
            _PAGE,
            {
                **_PAGE_BODY,
                "session_id": session,
                "max_records": 10,
                "max_charged_bytes": 16384,
            },
        )
        assert page.status == 200
        records = json.loads(page.payload)["page"]["records"]
        assert [item["sequence"] for item in records] == [0, 1]
        assert records[0]["provenance"]["connection_id"] == start.connection_id.value
        assert records[0]["provenance"]["capabilities"] == sorted(
            v.value for v in start.provenance.capabilities.values
        )
        assert (
            records[0]["provenance"]["backend_observation_timestamp_domain"]["observer"]
            == start.provenance.backend_observation_timestamp_domain.observer.value
        )
        assert service.queries == ["resolve_record", "retrieve"]
        assert (
            service.run.fixture.connection.consumer_calls == 1
            and service.run.recorder.close_calls == 0
        )


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t014_unrelated_session_and_policy_rejections_keep_current_capture_live(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
) -> None:
    async with t014_active_service(
        tmp_path, account_home, monkeypatch, backend_index
    ) as service:
        before, _ = await service.run.active()
        _error(
            await service.request(
                _RECORD, {"session_id": "unrelated-private-session", "sequence": 0}
            ),
            409,
            "evidence",
            "session_not_associated",
        )
        assert service.queries == []
        session = service.run.journal.session_id.value
        _error(
            await service.request(
                _PAGE,
                {
                    **_PAGE_BODY,
                    "session_id": session,
                    "max_records": 11,
                    "max_charged_bytes": 16384,
                },
            ),
            422,
            "journal",
            "invalid_input",
        )
        assert (
            service.run.runtime.status() == before
            and service.run.recorder.close_calls == 0
        )
        await service.run.emit(b"still-acquiring\0\xff", sequence=1, timestamp=11)
        response = await service.request(
            _RECORD, {"session_id": session, "sequence": 1}
        )
        assert response.status == 200


# T019 acceptance bridges the real CLI HTTP boundary to actual authenticated
# service-owned Core work. No association/selection/cleanup policy is in a fake.


def _t019_cli_helpers(patch: pytest.MonkeyPatch) -> Any:
    root = Path(__file__).resolve().parents[2] / "cli/tests"
    for name, filename in (
        ("test_cli_commands", "test_cli_commands.py"),
        ("test_cli_context", "test_cli_context.py"),
        ("test_cli_transport", "test_cli_transport.py"),
        ("_service_t019_cli_evidence", "test_cli_evidence.py"),
    ):
        if name in sys.modules:
            continue
        spec = importlib.util.spec_from_file_location(name, root / filename)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        patch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
    return sys.modules["_service_t019_cli_evidence"]


@dataclass
class TerminalEvidenceService(ActiveEvidenceService):
    context: Any = None
    native: Any = None
    open_calls: int = 0
    fault: str | None = None
    raw_reports: list[bytes] = field(default_factory=list)
    preparation_failure: bool = False

    def readers_closed_read_only(self) -> None:
        probe = self.native
        count = len(probe.connections)
        assert probe.close_calls == count and probe.closed == probe.connections
        assert len(probe.uris) == count
        for uri, enabled in probe.uris:
            assert enabled and urlsplit(uri).scheme == "file"
            assert parse_qs(urlsplit(uri).query) == {
                "mode": ["ro"],
                "cache": ["private"],
            }
        statements = [" ".join(sql.upper().split()) for sql, _, _ in probe.statements]
        assert statements.count("BEGIN") == count
        assert statements.count("PRAGMA QUERY_ONLY") == count
        assert statements.count("PRAGMA QUERY_ONLY=ON") == count
        validation = [
            (sql, tx)
            for sql, tx, _ in probe.statements
            if sql.lstrip().upper().startswith("SELECT") or "QUICK_CHECK" in sql.upper()
        ]
        assert count == 0 or validation and all(tx for _, tx in validation)


class _T019ObservedReader:
    def __init__(
        self, raw: OwnedEvidenceReadPort, service: TerminalEvidenceService
    ) -> None:
        self.raw = raw
        self.service = service
        self.session_id = raw.session_id
        self.policy = raw.policy

    async def resolve_record(self, reference: EvidenceReference) -> EvidencePage:
        assert self.service.serving.get(), "delivery bypassed authenticated service"
        self.service.queries.append("terminal.record")
        if self.service.fault == "read_then_close":
            raise JournalFailure(
                JournalOperation.RETRIEVE, JournalFailureKind.BUSY, _SECRET
            )
        return await self.raw.resolve_record(reference)

    async def retrieve(self, request: EvidenceRetrievalRequest) -> EvidencePage:
        assert self.service.serving.get(), "delivery bypassed authenticated service"
        self.service.queries.append("terminal.page")
        if self.service.fault == "read_then_close":
            raise JournalFailure(
                JournalOperation.RETRIEVE, JournalFailureKind.BUSY, _SECRET
            )
        return await self.raw.retrieve(request)

    async def close(self) -> None:
        await self.raw.close()
        # Keep the actual native resource closed while simulating lost certainty.
        if self.service.fault in {"close_only", "read_then_close"}:
            raise JournalFailure(
                JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE, _SECRET
            )


@asynccontextmanager
async def _t019_service(
    tmp_path: Path,
    account_home: Path,
    patch: pytest.MonkeyPatch,
    backend_index: int,
    config: ServiceConfig = _CONFIGS[0],
) -> AsyncIterator[TerminalEvidenceService]:
    core = _t014_core_helpers(patch)
    probe_api = importlib.import_module("tests.contract.test_terminal_evidence_reader")
    created, _ = _t009_runtime_spy(_t009_module(), patch)
    owner = PrivateBootstrap.acquire(config)
    lifespan: AppLifespan | None = None
    service: TerminalEvidenceService | None = None
    try:
        owner.mark_unconfirmed()
        owner.publish_credential()
        assert owner.credential is not None
        context = _t009_module()._LaunchContext(config, owner)
        app = _t009_module().create_app(config, _launch_context=context)
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        profile = core._profile()
        path = tmp_path / "terminal-evidence.sqlite3"
        journal = await sqlite_evidence.SqliteEvidenceJournal.create(
            path, profile.session_policy
        )
        run = core.JournalRun(
            journal,
            core.BACKEND_FIXTURE_FACTORIES[backend_index](),
            runtime=created[0],
            profile=profile,
        )
        service = TerminalEvidenceService(
            app, config, owner.credential.encode(), run, path, context=context
        )
        original_app = service.app

        async def observed_app(scope: Scope, receive: Any, send: Any) -> None:
            body = bytearray()

            async def observed_send(message: Message) -> None:
                if message["type"] == "http.response.body":
                    chunk = message.get("body", b"")
                    assert len(body) + len(chunk) <= _BOUND
                    body.extend(chunk)
                await send(message)

            await original_app(scope, receive, observed_send)
            assert service is not None
            service.raw_reports.append(bytes(body))

        service.app = observed_app
        target = terminal_evidence.capture_terminal_target(
            path, session_id=journal.session_id, policy=journal.policy
        )
        assert target is not None

        async def opener() -> Any:
            assert service is not None and service.serving.get()
            status = run.runtime.status()
            assert status.owner_settled and status.recorder_close_confirmed
            service.open_calls += 1
            raw = await terminal_evidence.open_terminal_reader(target)
            if service.fault in {"partial_dirty", "partial_clean", "unexpected_open"}:
                await raw.close()
                if service.fault == "unexpected_open":
                    raise RuntimeError(_SECRET)
                raise EvidenceSourceOpenFailure(
                    JournalFailure(
                        JournalOperation.OPEN, JournalFailureKind.BUSY, _SECRET
                    ),
                    service.fault == "partial_clean",
                )
            return _T019ObservedReader(raw, service)

        async def prepare(resolved: Any) -> PreparedObservationRun:
            assert service is not None
            if service.preparation_failure:
                await run.recorder.close()
                raise PreparationFailure(
                    RuntimeIssue(
                        RuntimeIssueSource.PREPARATION, JournalFailureKind.IO_FAILURE
                    ),
                    session_id=journal.session_id,
                    recorder_close_confirmed=True,
                    terminal_evidence_access=PreparedEvidenceAccess(
                        journal.session_id, journal.policy, terminal_opener=opener
                    ),
                )
            return PreparedObservationRun(
                run.recorder,
                run.fixture.backend,
                PreparedEvidenceAccess(
                    journal.session_id, journal.policy, journal, opener
                ),
            )

        def attach() -> Any:
            task = asyncio.create_task(run.runtime.attach(profile, prepare))
            run.tasks.append(task)
            return task

        run.attach = attach
        # Observed live selection still executes on the original capture journal.
        for name in ("retrieve", "resolve_record"):
            original = getattr(journal, name)

            async def observed(
                value: object, *, call: Any = original, kind: str = name
            ) -> Any:
                assert service is not None and service.serving.get()
                service.queries.append("live." + kind)
                return await call(value)

            patch.setattr(journal, name, observed)
        service.native = probe_api.ConnectionProbe(patch)
        import sqlite3

        read_only_connect = sqlite3.connect

        def guarded_connect(*args: Any, **kwargs: Any) -> Any:
            assert run.recorder.close_calls == 1, (
                "active capture opened a second SQLite connection"
            )
            return read_only_connect(*args, **kwargs)

        patch.setattr(sqlite3, "connect", guarded_connect)

        def forbidden(*args: object, **kwargs: object) -> None:
            pytest.fail(
                "terminal retrieval cannot writable-reopen/create/discover evidence"
            )

        patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "open", forbidden)
        patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "create", forbidden)
        patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "create_v2", forbidden)
        yield service
    finally:
        try:
            if service is not None:
                await service.run.finish()
        finally:
            if lifespan is not None:
                await lifespan.finish()
            owner.invalidate_credential()
            if service is not None and context.final_evidence_read_cleanup_confirmed:
                status = service.run.runtime.status()
                if (
                    status.owner_settled
                    and status.physical_release_confirmed
                    and status.recorder_close_confirmed
                ):
                    owner.confirm_cleanup(
                        owner_settled=status.owner_settled,
                        physical_release_confirmed=status.physical_release_confirmed,
                        recorder_close_confirmed=status.recorder_close_confirmed,
                    )
            owner.release()


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("stop", ["detach", "disconnect"])
@pytest.mark.asyncio
async def test_t019_cli_active_and_terminal_exact_binary_provenance_order_through_actual_auth(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend_index: int,
    config: ServiceConfig,
    stop: str,
) -> None:
    cli = _t019_cli_helpers(monkeypatch)
    async with _t019_service(
        tmp_path, account_home, monkeypatch, backend_index, config
    ) as service:
        active, start = await service.run.active()
        bridge = cli.ActiveBridge(service, monkeypatch)
        payload = bytes(range(256)) + b"\0\xff\xfe\r\n"
        await service.run.emit(payload, sequence=1, timestamp=11)
        session = service.run.journal.session_id.value
        live = await bridge.console(
            capsys, "evidence record", "--session", session, "--sequence", "1"
        )
        assert (
            base64.b64decode(
                live["page"]["records"][0]["payload_base64"], validate=True
            )
            == payload
        )
        assert service.open_calls == 0 and service.native.connections == []
        await service.run.emit(
            b"ambient-between-reads\0\xff\r\n", sequence=2, timestamp=20
        )
        live_page = await bridge.page(capsys)
        next_sequence = 3
        loss = start.provenance.loss_observability
        if isinstance(loss, ObserverReportsUartLoss):
            await service.run.fixture.connection.emit_observer_loss(
                cause="overflow", lost_bytes=3, timestamp=25
            )
            await service.run.commit(next_sequence)
            next_sequence += 1
        if stop == "detach":
            delivered = await bridge.console(capsys, "detach")
            assert delivered["runtime"]["recorder_close_confirmed"]
        else:
            await service.run.fixture.connection.disconnect()
            await service.run.commit(next_sequence)
            await (
                service.run.runtime.detach()
            )  # Join the simulated autonomous boundary.
        terminal = service.run.runtime.status()
        before = service.journal_path.read_bytes()
        record = await bridge.console(
            capsys, "evidence record", "--session", session, "--sequence", "1"
        )
        page = await bridge.page(capsys)
        assert record == live
        assert page["run_id"] == active.run_id.value and page["session_id"] == session
        records = page["page"]["records"]
        assert records[:3] == live_page["page"]["records"]
        assert [item["sequence"] for item in records] == list(range(next_sequence + 1))
        assert records[-1]["kind"] == "segment_ended"
        assert records[-1]["reason"] == (
            "explicit_stop" if stop == "detach" else "disconnected"
        )
        provenance = records[0]["provenance"]
        assert provenance["capabilities"] == sorted(
            value.value for value in start.provenance.capabilities.values
        )
        assert provenance["connection_provenance"]["fields"] == [
            {"name": "count", "value": 7},
            {"name": "flag", "value": False},
            {"name": "text", "value": "opaque-é"},
            {"name": "unknown", "value": None},
        ]
        assert (
            provenance["backend_observation_timestamp_domain"]["observer"]
            == start.provenance.backend_observation_timestamp_domain.observer.value
        )
        for item in records[1:]:
            assert item["connection_id"] == start.connection_id.value
            assert item["segment_id"] == start.segment_id.value
        if isinstance(loss, ObserverReportsUartLoss):
            assert (
                records[-2]["kind"] == "observer_loss"
                and records[-2]["cause"] == "overflow"
            )
            assert (
                records[-2]["observer_id"] == loss.observer_id
                and records[-2]["scope"] == loss.scope
            )
        else:
            assert not any(item["kind"] == "observer_loss" for item in records)
        assert service.open_calls == 2
        service.readers_closed_read_only()
        assert service.journal_path.read_bytes() == before
        assert service.run.runtime.status() == terminal
        assert (
            service.run.recorder.close_calls
            == service.run.fixture.connection.consumer_calls
            == 1
        )
        assert all(
            request.headers["authorization"] == "Bearer " + service.token.decode()
            for request in bridge.requests
        )
        assert all(len(body) <= _BOUND for body in service.raw_reports)
    assert service.context.final_evidence_read_cleanup_confirmed is True


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize(
    "fault,code", [("origin", "origin_rejected"), ("auth", "authentication_required")]
)
@pytest.mark.asyncio
async def test_t019_terminal_cli_security_rejection_precedes_native_reader_open(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend_index: int,
    fault: str,
    code: str,
) -> None:
    cli = _t019_cli_helpers(monkeypatch)
    async with _t019_service(
        tmp_path, account_home, monkeypatch, backend_index
    ) as service:
        await service.run.active()
        terminal = await service.run.runtime.detach()
        bridge = cli.ActiveBridge(service, monkeypatch, fault=fault)
        assert await bridge.page(capsys, code=4) == {
            "error": {"source": "request", "code": code}
        }
        assert service.open_calls == 0 and service.native.connections == []
        assert service.queries == [] and service.run.runtime.status() == terminal


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize(
    "fault,http,source,code,dirty",
    [
        ("close_only", 500, "journal", "io_failure", True),
        ("read_then_close", 503, "journal", "busy", True),
        ("partial_dirty", 503, "journal", "busy", True),
        ("unexpected_open", 500, "service", "internal_failure", True),
        ("partial_clean", 503, "journal", "busy", False),
    ],
)
@pytest.mark.asyncio
async def test_t019_terminal_cli_errors_preserve_primary_and_report_cleanup_uncertainty(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend_index: int,
    fault: str,
    http: int,
    source: str,
    code: str,
    dirty: bool,
) -> None:
    cli = _t019_cli_helpers(monkeypatch)
    async with _t019_service(
        tmp_path, account_home, monkeypatch, backend_index
    ) as service:
        await service.run.active()
        terminal = await service.run.runtime.detach()
        before = service.journal_path.read_bytes()
        service.fault = fault
        bridge = cli.ActiveBridge(service, monkeypatch)
        assert await bridge.page(capsys, code=4) == {
            "error": {"source": source, "code": code}
        }
        assert bridge.responses[-1].status_code == http
        assert _SECRET.encode() not in service.raw_reports[-1]
        assert service.run.runtime.evidence_read_cleanup_confirmed is (not dirty)
        assert service.run.runtime.status() == terminal and terminal.attach_admissible
        service.readers_closed_read_only()
        service.fault = None
        if dirty:
            assert await bridge.page(capsys, code=4) == {
                "error": {"source": "evidence", "code": "read_unavailable"}
            }
            assert bridge.responses[-1].status_code == 503 and service.open_calls == 1
        else:
            assert (await bridge.page(capsys))["run_id"] == terminal.run_id.value
            assert service.open_calls == 2
        assert service.journal_path.read_bytes() == before
    assert service.context.final_evidence_read_cleanup_confirmed is (not dirty)


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize(
    "fault,http,code",
    [("replacement", 409, "source_changed"), ("missing", 404, "journal_missing")],
)
@pytest.mark.asyncio
async def test_t019_closed_source_identity_errors_pass_actual_service_and_cli_without_fallback(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend_index: int,
    fault: str,
    http: int,
    code: str,
) -> None:
    cli = _t019_cli_helpers(monkeypatch)
    async with _t019_service(
        tmp_path, account_home, monkeypatch, backend_index
    ) as service:
        await service.run.active()
        terminal = await service.run.runtime.detach()
        if fault == "replacement":
            replacement = tmp_path / "replacement.sqlite3"
            shutil.copyfile(service.journal_path, replacement)
            replacement.replace(service.journal_path)
            before = service.journal_path.read_bytes()
        else:
            service.journal_path.unlink()
            before = None
        bridge = cli.ActiveBridge(service, monkeypatch)
        source = "evidence" if fault == "replacement" else "journal"
        assert await bridge.page(capsys, code=4) == {
            "error": {"source": source, "code": code}
        }
        assert bridge.responses[-1].status_code == http
        assert service.open_calls == 1 and service.native.connections == []
        assert service.run.runtime.evidence_read_cleanup_confirmed
        assert service.run.runtime.status() == terminal
        if before is None:
            assert not service.journal_path.exists()
        else:
            assert service.journal_path.read_bytes() == before


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t019_known_failed_preparation_empty_session_is_delivered_without_capture_reopen(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend_index: int,
) -> None:
    cli = _t019_cli_helpers(monkeypatch)
    async with _t019_service(
        tmp_path, account_home, monkeypatch, backend_index
    ) as service:
        service.preparation_failure = True
        terminal = await service.run.attach()
        assert terminal.session_id is not None and terminal.owner_settled
        assert terminal.recorder_close_confirmed and terminal.attach_admissible
        before = service.journal_path.read_bytes()
        bridge = cli.ActiveBridge(service, monkeypatch)
        page = await bridge.page(capsys)
        assert page["run_id"] == terminal.run_id.value
        assert page["session_id"] == terminal.session_id.value
        assert page["page"]["outcome"] == "complete" and page["page"]["records"] == []
        assert page["page"]["snapshot_end_exclusive"] == 0
        service.readers_closed_read_only()
        assert service.run.fixture.connection.consumer_calls == 0
        assert (
            service.journal_path.read_bytes() == before
            and service.run.runtime.status() == terminal
        )


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("uncertain", ["recorder", "physical"])
@pytest.mark.asyncio
async def test_t019_terminal_delivery_eligibility_preserves_recorder_and_physical_uncertainty(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend_index: int,
    uncertain: str,
) -> None:
    cli = _t019_cli_helpers(monkeypatch)
    async with _t019_service(
        tmp_path, account_home, monkeypatch, backend_index
    ) as service:
        await service.run.active()
        resource = (
            service.run.recorder
            if uncertain == "recorder"
            else service.run.fixture.connection
        )
        original_close = resource.close

        async def unconfirmed_close() -> None:
            await original_close()
            raise JournalFailure(
                JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE, _SECRET
            )

        monkeypatch.setattr(resource, "close", unconfirmed_close)
        terminal = await service.run.runtime.detach()
        assert terminal.owner_settled and not terminal.attach_admissible
        bridge = cli.ActiveBridge(service, monkeypatch)
        if uncertain == "recorder":
            assert not terminal.recorder_close_confirmed
            assert await bridge.page(capsys, code=4) == {
                "error": {"source": "evidence", "code": "read_unavailable"}
            }
            assert service.open_calls == 0 and service.native.connections == []
        else:
            assert (
                not terminal.physical_release_confirmed
                and terminal.recorder_close_confirmed
            )
            assert (await bridge.page(capsys))["run_id"] == terminal.run_id.value
            assert service.open_calls == 1
            service.readers_closed_read_only()
        assert service.run.runtime.status() == terminal
        assert service.run.runtime.evidence_read_cleanup_confirmed
    assert service.context.final_status == terminal
    assert service.context.final_evidence_read_cleanup_confirmed is True


# T021 transport contract: "Accumulate at most1048577 raw/encoded bytes for overflow detection".
# Typed Core facts drive projection-only checks; real journals drive consistency checks.


def _t021_raw_token(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@pytest.mark.parametrize("kind", ["start", "end"])
@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.parametrize("size", [_BOUND, _BOUND + 1])
@pytest.mark.parametrize("unit", ["é", '"', "🚀"], ids=["utf8", "escaped", "four-byte"])
@pytest.mark.asyncio
async def test_009_t019_marker_envelopes_keep_exact_encoded_limit_without_trimming_or_refetch(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    device: bool,
    path: str,
    size: int,
    unit: str,
) -> None:
    # Import test-only helpers after module initialization, avoiding the existing
    # Monitor test module's import of this evidence harness at collection time.
    from dutchmate_core import model

    from test_monitor_http import _t019_marker, _t019_padding

    record, wire = _t019_marker(device, kind)
    expected = _envelope(records=[wire], snapshot_end_exclusive=9, charged_bytes=_BOUND)
    run = "run-é"
    if isinstance(record, model.OperationStartedEvidence):
        wire["provenance"]["connection_provenance"]["fields"] = [
            {"name": "padding", "value": ""}
        ]
        padding = _t019_padding(expected, size, unit)
        wire["provenance"]["connection_provenance"]["fields"][0]["value"] = padding
        snapshot = record.provenance.connection_provenance.to_snapshot()
        record = replace(
            record,
            provenance=replace(
                record.provenance,
                connection_provenance=model.PersistedConnectionProvenance(
                    replace(
                        snapshot, fields=(model.ProvenanceField("padding", padding),)
                    )
                ),
            ),
        )
    else:
        # End fields are bounded facts. Grow only the opaque envelope ID, never
        # invent an invalid operation UUID, counter or clock to reach the cap.
        expected["run_id"] = ""
        run = _t019_padding(expected, size, unit)
        expected["run_id"] = run
    assert len(_json(expected)) == size
    async with _service(process_credential, monkeypatch) as service:
        original = RunEvidencePage(
            RunId(run),
            _SESSION,
            _page(records=(record,), snapshot_end_exclusive=9, charged_bytes=_BOUND),
        )
        service.boundary.result = original
        body = (
            {"session_id": _SESSION.value, "sequence": record.sequence}
            if path == _RECORD
            else {**_PAGE_BODY, "max_charged_bytes": _BOUND}
        )
        response = await service.request(path, body)
        if size == _BOUND:
            _success(response, expected)
        else:
            _error(response, 413, "evidence", "delivery_too_large")
            assert response.payload == _json(
                {"error": {"source": "evidence", "code": "delivery_too_large"}}
            )
        assert service.boundary.result is original and original.page.records == (
            record,
        )
        assert len(service.boundary.calls) == 1


@pytest.mark.parametrize("path", [_RECORD, _PAGE])
@pytest.mark.parametrize("size", [_BOUND, _BOUND + 1])
@pytest.mark.asyncio
async def test_009_t019_old_rx_envelope_still_uses_evidence_whole_report_overflow(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    size: int,
) -> None:
    from test_monitor_http import _t019_padding

    payload = bytes(range(256))
    record = RxBytesEvidence(
        0,
        ConnectionInstanceId("c"),
        SegmentId("s"),
        payload,
        BackendObservationTimestamp("clock", 0),
    )
    wire = {
        "kind": "rx_bytes",
        "sequence": 0,
        "connection_id": "c",
        "segment_id": "s",
        "observed_at": {"domain_id": "clock", "value": 0},
        "payload_base64": base64.b64encode(payload).decode(),
    }
    expected = _envelope(records=[wire], snapshot_end_exclusive=1, charged_bytes=512)
    expected["run_id"] = ""
    run = _t019_padding(expected, size, '"')
    expected["run_id"] = run
    assert len(_json(expected)) == size
    async with _service(process_credential, monkeypatch) as service:
        original = RunEvidencePage(
            RunId(run),
            _SESSION,
            _page(records=(record,), snapshot_end_exclusive=1, charged_bytes=512),
        )
        service.boundary.result = original
        response = await service.request(
            path, _RECORD_BODY if path == _RECORD else _PAGE_BODY
        )
        if size == _BOUND:
            _success(response, expected)
        else:
            _error(response, 413, "evidence", "delivery_too_large")
        assert service.boundary.result is original and record.payload == payload
        assert len(service.boundary.calls) == 1


@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.parametrize("raw_bytes", [768, 769], ids=["cursor-1024", "cursor-1026"])
@pytest.mark.asyncio
async def test_009_t019_marker_page_retains_old_cursor_limit_and_rejects1025_input(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
    raw_bytes: int,
) -> None:
    from test_monitor_http import _t019_marker

    document = {
        "version": 1,
        "session_id": "",
        "range_start_inclusive": 0,
        "range_end_exclusive": None,
        "snapshot_end_exclusive": 9,
        "next_sequence": 4,
    }
    remaining = raw_bytes - len(_json(document))
    session = "\x01" * (remaining // 6) + "x" * (remaining % 6)
    assert 1 <= len(session.encode()) <= 256 and "\0" not in session
    document["session_id"] = session
    assert len(_json(document)) == raw_bytes
    token = _token(document)
    assert len(token) == (1024 if raw_bytes == 768 else 1026)
    sid = SessionId(session)
    cursor = EvidenceCursor(sid, 0, None, 9, 4)
    marker, wire = _t019_marker(device, "start")
    async with _service(process_credential, monkeypatch) as service:
        original = RunEvidencePage(
            RunId("run-é"),
            sid,
            _page(
                records=(marker,),
                snapshot_end_exclusive=9,
                truncated=True,
                continuation=cursor,
                charged_bytes=800,
            ),
        )
        service.boundary.result = original
        response = await service.request(_PAGE, {**_PAGE_BODY, "session_id": session})
        if raw_bytes == 768:
            expected = _envelope(
                records=[wire],
                snapshot_end_exclusive=9,
                truncated=True,
                continuation=token,
                charged_bytes=800,
            )
            expected["session_id"] = session
            _success(response, expected)
            repeated = await service.request(
                _PAGE, {**_PAGE_BODY, "session_id": session, "cursor": token}
            )
            _success(repeated, expected)
            assert service.boundary.calls[-1] == EvidenceRetrievalRequest(
                sid, 32, 65536, cursor
            )
        else:
            _error(response, 413, "evidence", "delivery_too_large")
        before = len(service.boundary.calls)
        _error(
            await service.request(
                _PAGE, {**_PAGE_BODY, "session_id": session, "cursor": "A" * 1025}
            ),
            422,
            "request",
            "invalid_request",
        )
        assert len(service.boundary.calls) == before
        assert (
            service.boundary.result is original and original.page.continuation == cursor
        )


def _t021_bad_cursor_cases() -> list[tuple[str, str]]:
    document = _cursor_document()
    valid = _json(document)
    cases = [
        ("leading-space", _t021_raw_token(b" " + valid)),
        ("trailing-newline", _t021_raw_token(valid + b"\n")),
        ("utf8-bom", _t021_raw_token(b"\xef\xbb\xbf" + valid)),
        ("overlong-utf8", _t021_raw_token(valid.replace("é".encode(), b"\xc0\xaf"))),
        (
            "surrogate-utf8",
            _t021_raw_token(valid.replace("é".encode(), b"\xed\xa0\x80")),
        ),
        ("escaped-unicode", _t021_raw_token(valid.replace("é".encode(), b"\\u00e9"))),
        (
            "escaped-key",
            _t021_raw_token(valid.replace(b'"version"', b'"\\u0076ersion"')),
        ),
        ("outer-array", _token([document])),
        ("outer-null", _token(None)),
        ("explicit-padding", _token(document) + "=="),
        ("space-in-token", _token(document)[:8] + " " + _token(document)[8:]),
        ("token-limit", "A" * 1025),
        ("version-zero", _token({**document, "version": 0})),
        ("version-float", _token({**document, "version": 1.0})),
        ("empty-session", _token({**document, "session_id": ""})),
        ("nul-session", _token({**document, "session_id": "a\0b"})),
        ("oversized-session-utf8", _token({**document, "session_id": "é" * 129})),
        ("position-before-start", _token({**document, "range_start_inclusive": 4})),
        ("snapshot-after-range", _token({**document, "range_end_exclusive": 8})),
    ]
    for key in document:
        cases.append(
            ("missing-" + key, _token({k: v for k, v in document.items() if k != key}))
        )
        pairs = list(document.items())
        raw = (
            b"{"
            + b",".join(_json(k) + b":" + _json(v) for k, v in pairs)
            + b","
            + _json(key)
            + b":"
            + _json(document[key])
            + b"}"
        )
        cases.append(("duplicate-" + key, _t021_raw_token(raw)))
    for key in (
        "range_start_inclusive",
        "range_end_exclusive",
        "snapshot_end_exclusive",
        "next_sequence",
    ):
        for value in (-1, _MAX + 1, True, 1.0, "1"):
            cases.append((key + "-" + repr(value), _token({**document, key: value})))
    for constant in (b"NaN", b"Infinity", b"-Infinity"):
        raw = valid.replace(b'"next_sequence":3', b'"next_sequence":' + constant)
        cases.append(("nonfinite-" + constant.decode(), _t021_raw_token(raw)))
    # Alternate pad bits preserve decoded bytes but violate canonical token text.
    for suffix in ("x", "xx", "xxx"):
        canonical = _token({**document, "session_id": suffix})
        if len(canonical) % 4 in (2, 3):
            alphabet = (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            )
            final = alphabet.index(canonical[-1])
            altered = canonical[:-1] + alphabet[final + 1]
            assert base64.urlsafe_b64decode(
                altered + "=" * (-len(altered) % 4)
            ) == base64.urlsafe_b64decode(canonical + "=" * (-len(canonical) % 4))
            cases.append(("nonzero-pad-bits", altered))
            break
    for offset in range(3):
        canonical = _token({**document, "session_id": "x" * offset + "\uffff"})
        if "-" in canonical or "_" in canonical:
            cases.append(
                ("standard-alphabet", canonical.replace("-", "+").replace("_", "/"))
            )
            break
    return cases


@pytest.mark.parametrize(
    "label,token",
    _t021_bad_cursor_cases(),
    ids=[case[0] for case in _t021_bad_cursor_cases()],
)
@pytest.mark.asyncio
async def test_t021_noncanonical_cursor_is_private_request_rejection_before_core(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    token: str,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        _error(
            await service.request(_PAGE, {**_PAGE_BODY, "cursor": token}),
            422,
            "request",
            "invalid_request",
        )
        assert service.boundary.calls == []


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize(
    "field,value,code",
    [
        ("session_id", "other-session", "session_mismatch"),
        ("range_start_inclusive", 1, "invalid_input"),
        ("range_end_exclusive", 3, "invalid_input"),
        ("snapshot_end_exclusive", 4, "invalid_input"),
    ],
)
@pytest.mark.asyncio
async def test_t021_canonical_cursor_consistency_reaches003_and_preserves_journal_error(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
    field: str,
    value: object,
    code: str,
) -> None:
    async with t014_active_service(
        tmp_path, account_home, monkeypatch, backend_index
    ) as service:
        active, _ = await service.run.active()
        await service.run.emit(b"one", sequence=1, timestamp=11)
        await service.run.emit(b"two", sequence=2, timestamp=20)
        body = {
            **_PAGE_BODY,
            "session_id": active.session_id.value,
            "max_records": 1,
            "max_charged_bytes": 16384,
        }
        first = await service.request(_PAGE, body)
        assert first.status == 200
        token = json.loads(first.payload)["page"]["continuation"]
        document = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        assert list(document) == [
            "version",
            "session_id",
            "range_start_inclusive",
            "range_end_exclusive",
            "snapshot_end_exclusive",
            "next_sequence",
        ]
        altered = _token({**document, field: value})
        _error(
            await service.request(_PAGE, {**body, "cursor": altered}),
            409 if code == "session_mismatch" else 422,
            "journal",
            code,
        )
        assert service.queries == ["retrieve", "retrieve"]
        assert service.run.runtime.status() == active
        continued = await service.request(
            _PAGE, {**body, "max_records": 2, "cursor": token}
        )
        assert continued.status == 200
        assert [
            r["sequence"] for r in json.loads(continued.payload)["page"]["records"]
        ] == [1, 2]


@pytest.mark.parametrize("session", ['é/\\"\n', "e\u0301", "😀" * 64])
@pytest.mark.asyncio
async def test_t021_cursor_unicode_round_trip_and_authentication_independent_editing(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    session: str,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        sid = SessionId(session)
        cursor = EvidenceCursor(sid, 2, 10, 8, 4)
        document = {
            "version": 1,
            "session_id": session,
            "range_start_inclusive": 2,
            "range_end_exclusive": 10,
            "snapshot_end_exclusive": 8,
            "next_sequence": 4,
        }
        token = _token(document)
        service.boundary.result = RunEvidencePage(
            RunId("run-é"),
            sid,
            _page(snapshot_end_exclusive=8, truncated=True, continuation=cursor),
        )
        body = {
            **_PAGE_BODY,
            "session_id": session,
            "start_inclusive": 2,
            "end_exclusive": 10,
            "cursor": token,
        }
        response = await service.request(_PAGE, body)
        assert response.status == 200
        returned = json.loads(response.payload)["page"]["continuation"]
        assert returned == token and "=" not in returned and len(returned) <= 1024
        assert base64.urlsafe_b64decode(returned + "=" * (-len(returned) % 4)) == _json(
            document
        )
        assert service.boundary.calls == [
            EvidenceRetrievalRequest(
                EvidenceRangeReference(sid, 2, 10), 32, 65536, cursor
            )
        ]
        edited = _token({**document, "next_sequence": 5})
        await service.request(_PAGE, {**body, "cursor": edited})
        edited_request = service.boundary.calls[-1]
        assert isinstance(edited_request, EvidenceRetrievalRequest)
        assert edited_request.cursor == replace(cursor, next_sequence=5)


@pytest.mark.parametrize(
    "payload,want",
    [
        (b"", ""),
        (b"\xff", "/w=="),
        (b"\xfb\xff", "+/8="),
        (b"\xfb\xff\xfe", "+//+"),
        (b"\0\xff\xfe\r\n", "AP/+DQo="),
        (bytes(range(256)), None),
    ],
)
@pytest.mark.parametrize("path,body", [(_RECORD, _RECORD_BODY), (_PAGE, _PAGE_BODY)])
@pytest.mark.asyncio
async def test_t021_standard_base64_quantum_padding_pad_bits_and_all_bytes_are_exact(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    want: str | None,
    path: str,
    body: dict[str, Any],
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        record = RxBytesEvidence(
            0,
            ConnectionInstanceId("c"),
            SegmentId("s"),
            payload,
            BackendObservationTimestamp("clock", 7),
        )
        service.boundary.result = _report(
            _page(records=(record,), snapshot_end_exclusive=1, charged_bytes=123)
        )
        response = await service.request(path, body)
        assert response.status == 200
        encoded = json.loads(response.payload)["page"]["records"][0]["payload_base64"]
        assert encoded == (
            want if want is not None else base64.b64encode(payload).decode()
        )
        assert base64.b64decode(encoded, validate=True) == payload
        if payload:
            alphabet = (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
            )
            if len(payload) % 3 == 1:
                assert encoded.endswith("==") and alphabet.index(encoded[-3]) & 15 == 0
            elif len(payload) % 3 == 2:
                assert (
                    encoded.endswith("=")
                    and not encoded.endswith("==")
                    and alphabet.index(encoded[-2]) & 3 == 0
                )
        assert len(service.boundary.calls) == 1


@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.parametrize(
    "cause,lost", [("overflow", 11), ("other_observed_loss", None)]
)
@pytest.mark.parametrize(
    "reason",
    [
        "explicit_stop",
        "disconnected",
        "timestamp_origin_reset",
        "recording_failure",
        "transport_failure",
    ],
)
@pytest.mark.asyncio
async def test_t021_literal_loss_and_segment_enums_preserve_full_provenance_and_marker_fields(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
    cause: str,
    lost: int | None,
    reason: str,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        provenance, wire = _provenance(device)
        records = (
            SegmentStartedEvidence(3, provenance),
            ObserverLossEvidence(
                4,
                provenance.connection_id,
                provenance.segment_id,
                "observer-é",
                "scope/opaque",
                ObserverLossCause(cause),
                lost,
                BackendObservationTimestamp(_domain(device).domain_id, 2),
            ),
            SegmentEndedEvidence(
                5,
                provenance.connection_id,
                provenance.segment_id,
                SegmentEndReason(reason),
            ),
        )
        first = RetentionTimestampEndpoint(
            BackendObservationTimestamp("host-clock", 90), _domain(False)
        )
        last = RetentionTimestampEndpoint(
            BackendObservationTimestamp("device-clock", 2), _domain(True)
        )
        marker = RetentionMarker(SequenceRange(0, 3), first, last, 3, 11, 777)
        service.boundary.result = _report(
            _page(
                records=records,
                snapshot_end_exclusive=6,
                expired_range=SequenceRange(0, 3),
                retention_marker=marker,
                outcome=EvidencePageOutcome.PARTIAL,
                charged_bytes=999,
            )
        )
        expected_records = [
            {"kind": "segment_started", "sequence": 3, "provenance": wire},
            {
                "kind": "observer_loss",
                "sequence": 4,
                "connection_id": provenance.connection_id.value,
                "segment_id": provenance.segment_id.value,
                "observer_id": "observer-é",
                "scope": "scope/opaque",
                "cause": cause,
                "lost_bytes": lost,
                "observed_at": {"domain_id": _domain(device).domain_id, "value": 2},
            },
            {
                "kind": "segment_ended",
                "sequence": 5,
                "connection_id": provenance.connection_id.value,
                "segment_id": provenance.segment_id.value,
                "reason": reason,
            },
        ]
        expected_marker = {
            "expired_range": {"start_inclusive": 0, "end_exclusive": 3},
            "first_discarded_timestamp": {
                "timestamp": {"domain_id": "host-clock", "value": 90},
                "domain": _domain_wire(False),
            },
            "last_discarded_timestamp": {
                "timestamp": {"domain_id": "device-clock", "value": 2},
                "domain": _domain_wire(True),
            },
            "discarded_record_count": 3,
            "discarded_rx_payload_byte_count": 11,
            "discarded_charged_bytes": 777,
        }
        _success(
            await service.request(_PAGE, _PAGE_BODY),
            _envelope(
                records=expected_records,
                snapshot_end_exclusive=6,
                expired_range={"start_inclusive": 0, "end_exclusive": 3},
                retention_marker=expected_marker,
                outcome="partial",
                charged_bytes=999,
            ),
        )
        assert len(service.boundary.calls) == 1


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize(
    "key,value,source",
    [
        ("max_records", 4096, "journal"),
        ("max_records", 4097, "request"),
        ("max_charged_bytes", 1048576, "journal"),
        ("max_charged_bytes", 1048577, "request"),
    ],
)
@pytest.mark.asyncio
async def test_t021_wire_limits_and_captured_policy_ceiling_have_distinct_rejections(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend_index: int,
    key: str,
    value: int,
    source: str,
) -> None:
    async with t014_active_service(
        tmp_path, account_home, monkeypatch, backend_index
    ) as service:
        active, _ = await service.run.active()
        body = {
            **_PAGE_BODY,
            "session_id": active.session_id.value,
            "max_records": 10,
            "max_charged_bytes": 16384,
            key: value,
        }
        _error(
            await service.request(_PAGE, body),
            422,
            source,
            "invalid_input" if source == "journal" else "invalid_request",
        )
        assert service.queries == (["retrieve"] if source == "journal" else [])
        assert service.run.runtime.status() == active


@pytest.mark.parametrize("raw_size,status", [(16384, 200), (16385, 413)])
@pytest.mark.asyncio
async def test_t021_multibyte_utf8_chunk_split_preserves_actual_raw_body_bound(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    raw_size: int,
    status: int,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        raw = _json(_PAGE_BODY)
        split = raw.index("é".encode()) + 1
        raw += b" " * (raw_size - len(raw))
        exchange = ChunkedExchange(chunks=[raw[:split], raw[split:16384], raw[16384:]])
        response = await service.request(_PAGE, {}, exchange=exchange)
        if status == 200:
            _success(response, _envelope())
            assert len(service.boundary.calls) == 1
        else:
            _error(response, 413, "request", "payload_too_large")
            assert service.boundary.calls == []


@pytest.mark.parametrize(
    "wire_size,status", [(1048575, 200), (1048576, 200), (1048577, 413)]
)
@pytest.mark.asyncio
async def test_t021_utf8_and_control_escape_whole_envelope_boundary_preserves_original_facts(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    wire_size: int,
    status: int,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        provenance, wire = _provenance(True)
        fields = [{"name": "metadata", "value": ""}]
        wire["connection_provenance"]["fields"] = fields
        expected = _envelope(
            records=[{"kind": "segment_started", "sequence": 0, "provenance": wire}],
            snapshot_end_exclusive=2,
            truncated=True,
            continuation=_token(
                {**_cursor_document(), "snapshot_end_exclusive": 2, "next_sequence": 1}
            ),
            charged_bytes=1,
            next_record_required_bytes=1,
        )
        fragment = 'é/\\"\n😀'
        extra = wire_size - len(_json(expected))
        fragment_bytes = len(_json(fragment)) - 2
        metadata = fragment * (extra // fragment_bytes) + "x" * (extra % fragment_bytes)
        fields[0]["value"] = metadata
        assert len(_json(expected)) == wire_size
        provenance = replace(
            provenance,
            connection_provenance=PersistedConnectionProvenance(
                ConnectionProvenanceSnapshot(
                    1,
                    provenance.connection_provenance.to_snapshot().backend_kind,
                    3,
                    (ProvenanceField("metadata", metadata),),
                )
            ),
        )
        report = _report(
            _page(
                records=(SegmentStartedEvidence(0, provenance),),
                snapshot_end_exclusive=2,
                truncated=True,
                continuation=EvidenceCursor(_SESSION, 0, None, 2, 1),
                charged_bytes=1,
                next_record_required_bytes=1,
            )
        )
        service.boundary.result = report
        response = await service.request(_PAGE, _PAGE_BODY)
        if status == 200:
            _success(response, expected)
        else:
            _error(response, 413, "evidence", "delivery_too_large")
        assert service.boundary.result is report and len(service.boundary.calls) == 1


@pytest.mark.parametrize("kind", ["record", "provenance", "marker"])
@pytest.mark.asyncio
async def test_t021_irreducible_record_or_mandatory_metadata_overflow_never_rewrites_or_refetches(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        records: tuple[Any, ...] = ()
        marker = None
        if kind == "record":
            records = (
                RxBytesEvidence(
                    0,
                    ConnectionInstanceId("c"),
                    SegmentId("s"),
                    b"\xff" * 800000,
                    BackendObservationTimestamp("clock", 7),
                ),
            )
        elif kind == "provenance":
            provenance, _ = _provenance(False)
            provenance = replace(
                provenance,
                connection_provenance=PersistedConnectionProvenance(
                    ConnectionProvenanceSnapshot(
                        1, "opaque", 1, (ProvenanceField("metadata", "é" * _BOUND),)
                    )
                ),
            )
            records = (SegmentStartedEvidence(0, provenance),)
        else:
            domain = replace(_domain(False), origin_id="é" * _BOUND)
            endpoint = RetentionTimestampEndpoint(
                BackendObservationTimestamp(domain.domain_id, 11), domain
            )
            marker = RetentionMarker(SequenceRange(0, 1), endpoint, endpoint, 1, 1, 1)
        cursor = EvidenceCursor(_SESSION, 0, None, 2, 1)
        report = _report(
            _page(
                records=records,
                snapshot_end_exclusive=2,
                truncated=True,
                continuation=cursor,
                retention_marker=marker,
                charged_bytes=800000,
                next_record_required_bytes=900000,
            )
        )
        service.boundary.result = report
        _error(
            await service.request(
                _PAGE, {**_PAGE_BODY, "max_records": 1, "max_charged_bytes": _BOUND}
            ),
            413,
            "evidence",
            "delivery_too_large",
        )
        assert service.boundary.result is report and report.page.continuation == cursor
        assert report.page.records == records and report.page.retention_marker == marker
        assert len(service.boundary.calls) == 1


@pytest.mark.asyncio
async def test_t021_zero_record_shortage_remains_small200_even_if_required_charge_cannot_be_delivered(
    process_credential: Callable[[ServiceConfig], Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        cursor = EvidenceCursor(_SESSION, 0, None, 1, 0)
        service.boundary.result = _report(
            _page(
                snapshot_end_exclusive=1,
                truncated=True,
                continuation=cursor,
                next_record_required_bytes=_MAX,
            )
        )
        response = await service.request(
            _PAGE, {**_PAGE_BODY, "max_records": 1, "max_charged_bytes": 1}
        )
        assert response.status == 200
        page = json.loads(response.payload)["page"]
        assert (
            page["records"] == [] and page["charged_bytes"] == 0 and page["truncated"]
        )
        assert page["next_record_required_bytes"] == _MAX
        assert page["continuation"] == _token(
            {
                "version": 1,
                "session_id": _SESSION.value,
                "range_start_inclusive": 0,
                "range_end_exclusive": None,
                "snapshot_end_exclusive": 1,
                "next_sequence": 0,
            }
        )
        assert len(response.payload) < _BOUND and len(service.boundary.calls) == 1


@pytest.mark.parametrize("raw_bytes,status", [(767, 200), (768, 200), (769, 413)])
@pytest.mark.asyncio
async def test_t021_emitted_cursor_obeys1024_token_bound_or_rejects_whole_report(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    raw_bytes: int,
    status: int,
) -> None:
    document = {
        "version": 1,
        "session_id": "",
        "range_start_inclusive": 0,
        "range_end_exclusive": None,
        "snapshot_end_exclusive": 2,
        "next_sequence": 1,
    }
    fill = raw_bytes - len(_json(document))
    session = "\x01" * (fill // 6) + "x" * (fill % 6)
    document["session_id"] = session
    assert len(session.encode()) <= 256 and "\0" not in session
    assert len(_json(document)) == raw_bytes
    token = _token(document)
    assert (len(token) <= 1024) is (status == 200)
    async with _service(process_credential, monkeypatch) as service:
        sid = SessionId(session)
        cursor = EvidenceCursor(sid, 0, None, 2, 1)
        report = RunEvidencePage(
            RunId("run-é"),
            sid,
            _page(
                snapshot_end_exclusive=2,
                truncated=True,
                continuation=cursor,
                next_record_required_bytes=1,
            ),
        )
        service.boundary.result = report
        response = await service.request(_PAGE, {**_PAGE_BODY, "session_id": session})
        if status == 200:
            assert response.status == 200
            emitted = json.loads(response.payload)["page"]["continuation"]
            assert emitted == token and len(emitted) <= 1024
            again = await service.request(
                _PAGE, {**_PAGE_BODY, "session_id": session, "cursor": emitted}
            )
            assert again.status == 200
        else:
            if response.status == 200:
                # Pinpoint the delivery defect: canonical output cannot be used
                # as a continuation, even though its session is within wire cap.
                emitted = json.loads(response.payload)["page"]["continuation"]
                assert emitted == token and len(emitted) == 1026
                _error(
                    await service.request(
                        _PAGE, {**_PAGE_BODY, "session_id": session, "cursor": emitted}
                    ),
                    422, "request", "invalid_request",
                )
                assert len(service.boundary.calls) == 1
            _error(response, 413, "evidence", "delivery_too_large")
            assert len(service.boundary.calls) == 1
        assert service.boundary.result is report


@pytest.mark.asyncio
async def test_t021_encoder_stops_overflow_without_accumulating_more_than_detection_byte_or_projecting_tail(
    process_credential: Callable[[ServiceConfig], Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # "Accumulate at most1048577 raw/encoded bytes for overflow detection".
    # Observe the actual stdlib output accumulator, not total process/SQLite memory.
    high_water: list[int] = []

    class ObservedAccumulator(bytearray):
        def extend(self, part: Any) -> None:
            assert len(self) + len(part) <= 1048577
            super().extend(part)
            high_water.append(len(self))

    reads: list[int] = []

    class ObservedMetadata(str):
        def __iter__(self) -> Any:
            for index, char in enumerate(str(self)):
                reads.append(index)
                yield char

    tail_reads: list[None] = []

    class TailProvenance(BackendConnectionProvenance):
        def to_snapshot(self) -> ConnectionProvenanceSnapshot:
            tail_reads.append(None)
            raise AssertionError("overflow must stop before later record projection")

    async with _service(process_credential, monkeypatch) as service:
        projection = importlib.import_module("dutchmate_service.evidence_http")
        monkeypatch.setattr(projection, "bytearray", ObservedAccumulator, raising=False)
        provenance, _ = _provenance(False)
        huge = replace(
            provenance,
            connection_provenance=PersistedConnectionProvenance(
                ConnectionProvenanceSnapshot(1, ObservedMetadata("é" * _BOUND), 1, ())
            ),
        )
        tail = replace(provenance, connection_provenance=TailProvenance())
        report = _report(
            _page(
                records=(
                    SegmentStartedEvidence(0, huge),
                    SegmentStartedEvidence(1, tail),
                ),
                snapshot_end_exclusive=2,
                charged_bytes=2,
            )
        )
        service.boundary.result = report
        _error(
            await service.request(_PAGE, _PAGE_BODY),
            413,
            "evidence",
            "delivery_too_large",
        )
        assert all(size <= 1048577 for size in high_water)
        assert len(reads) < _BOUND and tail_reads == []
        assert service.boundary.result is report and len(service.boundary.calls) == 1
