"""010 T010 RED: authenticated annotation delivery and evidence projections.

The app, authentication, body reader, serializers and job registries are real.
Only acknowledged Core facts/failures are supplied at the runtime boundary.
"""

import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractContextManager, asynccontextmanager
from dataclasses import dataclass, field, replace

import pytest
from dutchmate_core import annotation, evidence, model
from dutchmate_core.adapters.sqlite_evidence import SqliteEvidenceJournal
from dutchmate_core.runtime import RunId, RuntimeRejectedError, RuntimeRejectedKind

from dutchmate_service.bootstrap import PrivateBootstrap, ServiceConfig
from test_evidence_http import (
    ChunkedExchange,
    _envelope,
    _error,
    _json,
    _page,
    _report,
    _success,
)
from test_monitor_http import MonitorService
from test_monitor_http import _service as _monitor_service
from test_service_http import _CONFIGS, Exchange
from test_service_http import (
    forbid_profile_and_run_preparation as forbid_profile_and_run_preparation,
)
from test_service_http import process_credential as process_credential

type Credentials = Callable[
    [ServiceConfig], AbstractContextManager[tuple[PrivateBootstrap, bytes]]
]
_ROUTE = "/v1/observation/annotations"
_SESSION = model.SessionId("session-é")
_ORIGIN = "abcdefab-1234-4234-8234-123456789abc"
_PRIVATE = "private-T010-text-path-SQL-token-cause"
_BODY: dict[str, object] = {
    "session_id": _SESSION.value,
    "text": " build e\u0301; smoke\r\n\t ",
    "client_surface": "cli",
}
_LIMIT = 1048576


def _record(surface: str = "cli") -> model.ClientAnnotationEvidence:
    return model.ClientAnnotationEvidence(3, str(_BODY["text"]), surface, _ORIGIN, 100)


def _receipt() -> annotation.AnnotationReceipt:
    return annotation.AnnotationReceipt(
        "run-é", _SESSION, model.EvidenceReference(_SESSION, 3), _record()
    )


def _variant(surface: str = "cli") -> dict[str, object]:
    # Deliberately independent of the production projection/codec.
    return {
        "kind": "client_annotation",
        "sequence": 3,
        "assertion_class": "client_assertion",
        "client_surface": surface,
        "attribution_basis": "client_asserted",
        "clock_origin_id": _ORIGIN,
        "received_at_ns": 100,
        "text": _BODY["text"],
    }


def _wire() -> dict[str, object]:
    return {
        "run_id": "run-é",
        "session_id": _SESSION.value,
        "reference": {"session_id": _SESSION.value, "sequence": 3},
        "annotation": _variant(),
    }


@dataclass
class AnnotationBoundary:
    result: object = field(default_factory=_receipt)
    failure: Exception | None = None
    calls: list[annotation.AnnotationRequest] = field(default_factory=list)

    async def invoke(self, request: annotation.AnnotationRequest) -> object:
        self.calls.append(request)
        if self.failure is not None:
            raise self.failure
        return self.result


@asynccontextmanager
async def _service(
    credentials: Credentials,
    patch: pytest.MonkeyPatch,
    config: ServiceConfig = _CONFIGS[0],
) -> AsyncIterator[tuple[MonitorService, AnnotationBoundary]]:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("delivery-only tests must not open/create v3 journals")

    for name in ("create_v3", "open_v3"):
        patch.setattr(SqliteEvidenceJournal, name, forbidden)
    async with _monitor_service(credentials, patch, config) as service:
        boundary = AnnotationBoundary()
        patch.setattr(service.runtime, "annotate", boundary.invoke)
        yield service, boundary


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("surface", ["cli", "http"])
@pytest.mark.asyncio
async def test_literal_post_projects_acknowledged_facts_without_refetch(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    surface: str,
) -> None:
    async with _service(process_credential, monkeypatch, config) as (service, core):
        # Return different text from the request: receipt must use Core facts.
        core.result = replace(
            _receipt(), annotation=replace(_record(surface), text="ACK")
        )
        expected = _wire()
        expected["annotation"] = {**_variant(surface), "text": "ACK"}
        _success(
            await service.request(_ROUTE, {**_BODY, "client_surface": surface}),
            expected,
        )
        assert core.calls == [
            annotation.AnnotationRequest(_SESSION, str(_BODY["text"]), surface)
        ]
        assert service.boundary.calls == []
        assert service.monitor.calls == []


@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"])
@pytest.mark.asyncio
async def test_literal_route_rejects_other_methods_before_body(
    process_credential: Credentials, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        _error(
            await service.request(
                _ROUTE,
                {},
                scope=service.scope(_ROUTE, method=method),
                exchange=Exchange(forbid_receive=True),
            ),
            405,
            "request",
            "method_not_allowed",
        )
        assert not core.calls


@pytest.mark.parametrize(
    "alias", ["slash", "case", "encoded", "missing_raw", "absolute"]
)
@pytest.mark.asyncio
async def test_no_route_alias_redirect_or_normalization(
    process_credential: Credentials, monkeypatch: pytest.MonkeyPatch, alias: str
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        scope = service.scope(_ROUTE)
        if alias == "slash":
            scope = service.scope(_ROUTE + "/")
        elif alias == "case":
            scope = service.scope(_ROUTE.replace("annotations", "Annotations"))
        elif alias == "encoded":
            scope["raw_path"] = b"/v1/observation/%61nnotations"
        elif alias == "missing_raw":
            scope.pop("raw_path")
        else:
            scope["raw_path"] = b"http://127.0.0.1" + _ROUTE.encode()
        _error(
            await service.request(
                _ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
            ),
            404,
            "request",
            "route_not_found",
        )
        assert not core.calls


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
@pytest.mark.asyncio
async def test_security_before_stopping_body_and_core_is_private(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    case: str,
    status: int,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with _service(process_credential, monkeypatch, config) as (service, core):
        service.launch_context.request_stop()
        scope = service.scope(_ROUTE)
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
                    _PRIVATE.encode(),
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
            headers.append((b"authorization", b"Bearer " + service.token))
        else:
            scope["query_string"] = b"text=" + _PRIVATE.encode()
        scope["headers"] = headers
        response = await service.request(
            _ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
        )
        _error(response, status, "request", code)
        if status == 401:
            assert response.headers[b"www-authenticate"] == b"Bearer"
        assert not core.calls
        assert service.token not in response.payload
        assert service.token.decode() not in caplog.text
        assert _PRIVATE not in caplog.text


@pytest.mark.asyncio
async def test_readiness_before_body_and_core(
    process_credential: Credentials, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        service.launch_context.request_stop()
        _error(
            await service.request(_ROUTE, {}, exchange=Exchange(forbid_receive=True)),
            503,
            "service",
            "stopping",
        )
        assert not core.calls


_INVALID: list[tuple[str, dict[str, object]]] = []
for _key in _BODY:
    _INVALID.append((f"missing-{_key}", {k: v for k, v in _BODY.items() if k != _key}))
for _key in (
    "assertion_class",
    "attribution_basis",
    "author",
    "run_id",
    "reference",
    "sequence",
    "clock_origin_id",
    "received_at_ns",
    "operation_id",
    "metadata",
    "path",
    "extra",
):
    _INVALID.append((f"extra-{_key}", {**_BODY, _key: _PRIVATE}))
_values: Sequence[object]
_value: object
for _key, _values in (
    ("session_id", ["", "x\0y", "x" * 257, "é" * 129, None, True, 1, []]),
    ("text", ["", "\0", "x" * 1025, "é" * 513, None, True, 1, []]),
    ("client_surface", ["core", "CLI", " cli", "http ", "", None, True, 1, []]),
):
    for _index, _value in enumerate(_values):
        _INVALID.append((f"{_key}-{_index}", {**_BODY, _key: _value}))


@pytest.mark.parametrize("label,body", _INVALID, ids=[v[0] for v in _INVALID])
@pytest.mark.asyncio
async def test_closed_request_and_exact_domains_before_core(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    body: dict[str, object],
) -> None:
    del label
    async with _service(process_credential, monkeypatch) as (service, core):
        _error(await service.request(_ROUTE, body), 422, "request", "invalid_request")
        assert not core.calls


@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b"[]",
        b"{} trailing",
        b"\xff",
        *[
            _json({**_BODY, "text": "x"}).replace(b'"text":"x"', b'"text":' + v)
            for v in (b"NaN", b"Infinity", b'"\\ud800"', b'"\\udfff"')
        ],
        *[_json(_BODY)[:-1] + b',"' + key.encode() + b'":null}' for key in _BODY],
    ],
)
@pytest.mark.asyncio
async def test_strict_json_utf8_duplicates_nonfinite_and_surrogates(
    process_credential: Credentials, monkeypatch: pytest.MonkeyPatch, raw: bytes
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        _error(
            await service.request(_ROUTE, {}, raw=raw),
            422,
            "request",
            "invalid_request",
        )
        assert not core.calls


@pytest.mark.parametrize(
    "session,text",
    [
        (" ", " "),
        ("x" * 256, "x" * 1024),
        ("é" * 128, "é" * 512),
        (" /e\u0301 ", " \r\n\t e\u0301 "),
    ],
)
@pytest.mark.asyncio
async def test_legal_utf8_edges_preserve_exact_text_and_session(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    session: str,
    text: str,
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        _success(
            await service.request(
                _ROUTE, {"session_id": session, "text": text, "client_surface": "http"}
            ),
            _wire(),
        )
        assert core.calls == [
            annotation.AnnotationRequest(model.SessionId(session), text, "http")
        ]


@pytest.mark.parametrize(
    "media",
    [
        None,
        b"text/json",
        b"application/json; charset=latin-1",
        b"application/json; charset=utf-8; charset=utf-8",
        b"application/json; profile=x",
    ],
)
@pytest.mark.asyncio
async def test_unsupported_media_before_body(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    media: bytes | None,
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        scope = service.scope(_ROUTE)
        scope["headers"] = [(k, v) for k, v in scope["headers"] if k != b"content-type"]
        if media is not None:
            scope["headers"].append((b"content-type", media))
        _error(
            await service.request(
                _ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
            ),
            415,
            "request",
            "unsupported_media_type",
        )
        assert not core.calls


@pytest.mark.parametrize("size", [16384, 16385])
@pytest.mark.parametrize("declared", [b"0", b"16384", b"999999"])
@pytest.mark.asyncio
async def test_actual_chunked_body_limit_independent_of_content_length(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    size: int,
    declared: bytes,
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        raw = _json(_BODY)
        raw += b" " * (size - len(raw))
        scope = service.scope(_ROUTE)
        scope["headers"].append((b"content-length", declared))
        response = await service.request(
            _ROUTE,
            {},
            scope=scope,
            exchange=ChunkedExchange(chunks=[raw[:8192], raw[8192:16384], raw[16384:]]),
        )
        if size == 16384:
            _success(response, _wire())
            assert len(core.calls) == 1
        else:
            _error(response, 413, "request", "payload_too_large")
            assert not core.calls


_REJECTIONS: tuple[tuple[annotation.AnnotationRejectedKind, int], ...] = (
    ("no_associated_session", 404),
    ("session_not_associated", 409),
    ("not_active", 409),
    ("annotation_unavailable", 503),
    ("evidence_policy_incompatible", 422),
    ("busy", 409),
    ("rate_limited", 429),
)
_FAILURES: list[tuple[Exception, int, str, str]] = [
    (annotation.AnnotationRejected(k), s, "annotation", k) for k, s in _REJECTIONS
]
_FAILURES += [
    (
        evidence.JournalFailure(evidence.JournalOperation.APPEND, k, _PRIVATE),
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
_FAILURES += [
    (RuntimeRejectedError(k), s, "runtime", k.value)
    for k, s in (
        (RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT, 500),
        (RuntimeRejectedKind.INVALID_REQUEST, 422),
    )
]
_FAILURES += [(RuntimeError(_PRIVATE), 500, "service", "internal_failure")]


@pytest.mark.parametrize(
    "failure,status,source,code",
    _FAILURES,
    ids=[s + "-" + c for _, _, s, c in _FAILURES],
)
@pytest.mark.asyncio
async def test_all_new_runtime_and_twenty_journal_errors_are_fixed_and_private(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status: int,
    source: str,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with _service(process_credential, monkeypatch) as (service, core):
        core.failure = failure
        response = await service.request(_ROUTE, _BODY)
        _error(response, status, source, code)
        assert len(core.calls) == 1
        assert b"retry-after" not in response.headers
        assert not any(b"ratelimit" in key.lower() for key in response.headers)
        assert _PRIVATE.encode() not in response.payload
        assert _PRIVATE not in caplog.text
        assert service.token.decode() not in caplog.text


@pytest.mark.parametrize("broken", [None, {}, "not a receipt"])
@pytest.mark.asyncio
async def test_unexpected_receipt_is_private_internal_failure(
    process_credential: Credentials, monkeypatch: pytest.MonkeyPatch, broken: object
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        core.result = broken
        _error(await service.request(_ROUTE, _BODY), 500, "service", "internal_failure")
        assert len(core.calls) == 1


@pytest.mark.parametrize("size", [_LIMIT - 1, _LIMIT, _LIMIT + 1])
@pytest.mark.asyncio
async def test_whole_receipt_utf8_delivery_bound_is_independent_of_text_charge(
    process_credential: Credentials, monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        expected = _wire()
        expected["run_id"] = ""
        run_id = "é" + "r" * (size - len(_json(expected)) - 2)
        expected["run_id"] = run_id
        assert len(_json(expected)) == size
        core.result = replace(_receipt(), run_id=run_id)
        response = await service.request(_ROUTE, _BODY)
        if size <= _LIMIT:
            _success(response, expected)
        else:
            _error(response, 413, "annotation", "delivery_too_large")
        assert len(core.calls) == 1
        assert not service.boundary.calls


@pytest.mark.parametrize("path", ["/v1/evidence/record", "/v1/evidence/page"])
@pytest.mark.parametrize("surface", ["cli", "http", "core"])
@pytest.mark.parametrize(
    "sequence,received", [(0, 0), (3, 100), (9223372036854775806, 9223372036854775807)]
)
@pytest.mark.asyncio
async def test_exact_annotation_evidence_variant_in_existing_read_endpoints(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    surface: str,
    sequence: int,
    received: int,
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        record = replace(_record(surface), sequence=sequence, received_at_ns=received)
        service.boundary.result = _report(
            _page(
                records=(record,),
                snapshot_end_exclusive=sequence + 1,
                charged_bytes=333,
            )
        )
        expected = _envelope(
            records=[
                {**_variant(surface), "sequence": sequence, "received_at_ns": received}
            ],
            snapshot_end_exclusive=sequence + 1,
            charged_bytes=333,
        )
        body = (
            {"session_id": _SESSION.value, "sequence": sequence}
            if path.endswith("record")
            else {
                "session_id": _SESSION.value,
                "start_inclusive": None,
                "end_exclusive": None,
                "max_records": 32,
                "max_charged_bytes": 65536,
                "cursor": None,
            }
        )
        _success(await service.request(path, body), expected)
        assert len(service.boundary.calls) == 1
        assert not core.calls


@pytest.mark.parametrize("size", [_LIMIT - 1, _LIMIT, _LIMIT + 1])
@pytest.mark.asyncio
async def test_annotation_evidence_whole_json_bound_keeps_existing_error_source(
    process_credential: Credentials, monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        expected = _envelope(
            records=[_variant()], snapshot_end_exclusive=4, charged_bytes=333
        )
        expected["run_id"] = ""
        run_id = "é" + "r" * (size - len(_json(expected)) - 2)
        expected["run_id"] = run_id
        assert len(_json(expected)) == size
        service.boundary.result = replace(
            _report(
                _page(records=(_record(),), snapshot_end_exclusive=4, charged_bytes=333)
            ),
            run_id=RunId(run_id),
        )
        response = await service.request(
            "/v1/evidence/page",
            {
                "session_id": _SESSION.value,
                "start_inclusive": None,
                "end_exclusive": None,
                "max_records": 32,
                "max_charged_bytes": 65536,
                "cursor": None,
            },
        )
        if size <= _LIMIT:
            _success(response, expected)
        else:
            _error(response, 413, "evidence", "delivery_too_large")
        assert len(service.boundary.calls) == 1
        assert not core.calls


_T015_ASSERTIONS = [
    "é",
    "e\u0301",
    " \r\n\t ",
    ' {"verified":true,"author":"root","timestamp":-1} ',
    "external SWD flash succeeded; /private/build; $(never-execute)",
]


@pytest.mark.parametrize("text", _T015_ASSERTIONS)
@pytest.mark.parametrize("surface", ["cli", "http"])
@pytest.mark.asyncio
async def test_t015_assertions_remain_exact_text_with_declared_attribution_only(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    surface: str,
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        record = replace(_record(surface), text=text)
        core.result = replace(_receipt(), annotation=record)
        expected = _wire()
        expected["annotation"] = {**_variant(surface), "text": text}
        _success(
            await service.request(
                _ROUTE, {**_BODY, "text": text, "client_surface": surface}
            ),
            expected,
        )
        assert core.calls == [annotation.AnnotationRequest(_SESSION, text, surface)]
        assert not service.boundary.calls
        assert core.result.annotation is record


@pytest.mark.parametrize(
    "field,value",
    [
        ("timestamp", "2026-01-01T00:00:00Z"),
        ("client_time_ns", 0),
        ("received_at_ns", 9223372036854775807),
        ("clock_origin_id", _ORIGIN),
        ("verified", True),
        ("principal", "root"),
        ("pid", 1),
        ("record_version", 3),
        ("assertion_class", "client_assertion"),
        ("attribution_basis", "client_asserted"),
    ],
)
@pytest.mark.asyncio
async def test_t015_even_plausible_identity_and_time_overrides_never_reach_core(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        _error(
            await service.request(_ROUTE, {**_BODY, field: value}),
            422,
            "request",
            "invalid_request",
        )
        assert not core.calls and not service.boundary.calls


@pytest.mark.parametrize("size", [16384, 16385])
@pytest.mark.parametrize("declared", [b"0", b"16384", b"999999"])
@pytest.mark.asyncio
async def test_t015_maximum_escaped_legal_fields_use_actual_chunked_body_bound(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    size: int,
    declared: bytes,
) -> None:
    # Both fields fit their decoded UTF-8 limits despite six-byte JSON escapes.
    session, text = "\x01" * 256, "\x1f" * 1024
    body = {"session_id": session, "text": text, "client_surface": "http"}
    raw = _json(body)
    assert b"\\u0001" in raw and b"\\u001f" in raw
    raw += b" " * (size - len(raw))
    assert len(raw) == size
    split = raw.index(b"\\u001f") + 3
    async with _service(process_credential, monkeypatch) as (service, core):
        sid = model.SessionId(session)
        record = replace(_record("http"), text=text)
        receipt = replace(
            _receipt(),
            session_id=sid,
            reference=model.EvidenceReference(sid, 3),
            annotation=record,
        )
        core.result = receipt
        scope = service.scope(_ROUTE)
        scope["headers"].append((b"content-length", declared))
        response = await service.request(
            _ROUTE,
            {},
            scope=scope,
            exchange=ChunkedExchange(
                chunks=[raw[:split], raw[split:16384], raw[16384:]]
            ),
        )
        if size == 16384:
            expected = _wire()
            expected.update(
                session_id=session,
                reference={"session_id": session, "sequence": 3},
                annotation={**_variant("http"), "text": text},
            )
            _success(response, expected)
            assert core.calls == [annotation.AnnotationRequest(sid, text, "http")]
        else:
            _error(response, 413, "request", "payload_too_large")
            assert not core.calls
        assert not service.boundary.calls
        assert core.result is receipt


@pytest.mark.parametrize("raw_bytes", [768, 769], ids=["cursor1024", "cursor1026"])
@pytest.mark.parametrize("surface", ["cli", "http", "core"])
@pytest.mark.asyncio
async def test_t015_annotation_cursor_limit_rejects_whole_page_without_mutating_snapshot(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    raw_bytes: int,
    surface: str,
) -> None:
    from test_evidence_http import _cursor_document, _token

    document = {**_cursor_document(), "session_id": "", "next_sequence": 4}
    remaining = raw_bytes - len(_json(document))
    session = "\x01" * (remaining // 6) + "x" * (remaining % 6)
    assert 1 <= len(session.encode()) <= 256
    document["session_id"] = session
    assert len(_json(document)) == raw_bytes
    token = _token(document)
    assert len(token) == (1024 if raw_bytes == 768 else 1026)
    sid = model.SessionId(session)
    cursor = evidence.EvidenceCursor(sid, 0, None, 9, 4)
    body = {
        "session_id": session,
        "start_inclusive": None,
        "end_exclusive": None,
        "max_records": 32,
        "max_charged_bytes": 65536,
        "cursor": None,
    }
    async with _service(process_credential, monkeypatch) as (service, core):
        report = replace(
            _report(
                _page(
                    records=(_record(surface),),
                    snapshot_end_exclusive=9,
                    truncated=True,
                    continuation=cursor,
                    charged_bytes=333,
                )
            ),
            session_id=sid,
        )
        service.boundary.result = report
        response = await service.request("/v1/evidence/page", body)
        if raw_bytes == 768:
            expected = _envelope(
                records=[_variant(surface)],
                snapshot_end_exclusive=9,
                truncated=True,
                continuation=token,
                charged_bytes=333,
            )
            expected["session_id"] = session
            _success(response, expected)
            assert len(service.boundary.calls) == 1  # no automatic continuation
            _success(
                await service.request(
                    "/v1/evidence/page",
                    {
                        **body,
                        "max_records": 1,
                        "max_charged_bytes": 333,
                        "cursor": token,
                    },
                ),
                expected,
            )
            assert service.boundary.calls[-1] == evidence.EvidenceRetrievalRequest(
                sid, 1, 333, cursor
            )
        else:
            _error(response, 413, "evidence", "delivery_too_large")
        before = len(service.boundary.calls)
        _error(
            await service.request("/v1/evidence/page", {**body, "cursor": "A" * 1025}),
            422,
            "request",
            "invalid_request",
        )
        assert len(service.boundary.calls) == before
        assert service.boundary.result is report and report.page.continuation == cursor
        assert not core.calls


@pytest.mark.parametrize("surface", ["Cli", "Http", "ｃｌｉ", "http\0"])
@pytest.mark.asyncio
async def test_t015_surface_declaration_is_not_case_folded_or_normalized(
    process_credential: Credentials,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    async with _service(process_credential, monkeypatch) as (service, core):
        _error(
            await service.request(_ROUTE, {**_BODY, "client_surface": surface}),
            422,
            "request",
            "invalid_request",
        )
        assert not core.calls and not service.boundary.calls


@pytest.mark.parametrize("size", [_LIMIT - 1, _LIMIT, _LIMIT + 1])
@pytest.mark.asyncio
async def test_t015_maximum_escaped_text_does_not_relax_whole_receipt_bound(
    process_credential: Credentials, monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    text = "\x1f" * 1024
    expected = _wire()
    expected["annotation"] = {**_variant(), "text": text}
    expected["run_id"] = ""
    run_id = "é" + "r" * (size - len(_json(expected)) - 2)
    expected["run_id"] = run_id
    assert len(_json(expected)) == size
    async with _service(process_credential, monkeypatch) as (service, core):
        receipt = replace(
            _receipt(), run_id=run_id, annotation=replace(_record(), text=text)
        )
        core.result = receipt
        response = await service.request(_ROUTE, {**_BODY, "text": text})
        if size <= _LIMIT:
            _success(response, expected)
        else:
            _error(response, 413, "annotation", "delivery_too_large")
        assert len(core.calls) == 1 and not service.boundary.calls
        assert core.result is receipt and receipt.annotation.text == text
