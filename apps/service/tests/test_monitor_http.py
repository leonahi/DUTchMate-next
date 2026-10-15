"""009 T013 RED: actual service routes, security and bounded Monitor delivery.

Only typed Core outcomes/failures are injected at the runtime boundary. The real
app, registries, wire codecs, projections and security gate remain under test.
No Monitor admission/matching/stop policy or HTTP implementation lives here.
"""

import asyncio
import base64
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Any

import pytest
from dutchmate_core import evidence, model, monitor
from dutchmate_core.adapters import sqlite_evidence
from dutchmate_core.evidence_access import RunEvidencePage
from dutchmate_core.runtime import (
    ObservationRuntime,
    RunId,
    RuntimeRejectedError,
    RuntimeRejectedKind,
)

from dutchmate_service.bootstrap import ServiceConfig
from test_evidence_http import (
    ChunkedExchange,
    ReadBoundary,
    Service,
    _envelope,
    _error,
    _json,
    _page,
    _provenance,
    _success,
)
from test_service_http import (
    _CONFIGS,
    AppLifespan,
    Exchange,
    _t009_module,
    _t009_runtime_spy,
)
from test_service_http import (
    forbid_profile_and_run_preparation as forbid_profile_and_run_preparation,
)
from test_service_http import (
    process_credential as process_credential,
)

_ROUTE = "/v1/observation/monitor"
_SESSION = model.SessionId("session-é")
_OPERATION = "12345678-1234-4234-8234-123456789abc"
_ORIGIN = "abcdefab-1234-4234-8234-123456789abc"
_SECRET = "private-detail-token-path-SQL-sentinel"
_LIMIT = 1048576
_BODY: dict[str, Any] = {
    "session_id": _SESSION.value,
    "condition_base64": "AP9B",
    "timeout_ms": 1000,
    "max_rx_bytes": 65536,
}


def _report(
    outcome: model.MonitorOutcome = model.MonitorOutcome.DETACHED,
    *,
    device: bool = False,
    failure: monitor.MonitorEndFailure | None = None,
) -> monitor.MonitorReport:
    matched = outcome is model.MonitorOutcome.MATCHED
    examined = 5 if matched or outcome is model.MonitorOutcome.BYTE_LIMIT else 0
    return monitor.MonitorReport(
        run_id="run-é",
        session_id=_SESSION,
        operation_id=_OPERATION,
        provenance=_provenance(device)[0],
        outcome=outcome,
        started_record=model.EvidenceReference(_SESSION, 3),
        ended_record=model.EvidenceReference(_SESSION, 8) if failure is None else None,
        window=model.SequenceRange(4, 6 if examined else 4),
        examined_rx_bytes=examined,
        observer_loss_records=0,
        match=model.MonitorMatch(
            model.MonitorMatchStart(4, 1), model.MonitorMatchEnd(5, 2)
        )
        if matched
        else None,
        clock=model.MonitorClockFacts(
            _ORIGIN,
            100,
            1000000100,
            1000000100 if outcome is model.MonitorOutcome.TIMEOUT else 102,
        ),
        durability="complete" if failure is None else "end_unconfirmed",
        end_failure=failure,
    )


def _wire(
    outcome: model.MonitorOutcome = model.MonitorOutcome.DETACHED,
    *,
    device: bool = False,
    failure: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Hand-declared expected wire facts, never the production projection."""
    examined = 5 if outcome.value in {"matched", "byte_limit"} else 0
    return {
        "run_id": "run-é",
        "session_id": "session-é",
        "operation_id": _OPERATION,
        "provenance": _provenance(device)[1],
        "outcome": outcome.value,
        "started_record": {"session_id": "session-é", "sequence": 3},
        "ended_record": {"session_id": "session-é", "sequence": 8}
        if failure is None
        else None,
        "window": {"start_inclusive": 4, "end_exclusive": 6 if examined else 4},
        "examined_rx_bytes": examined,
        "observer_loss_records": 0,
        "match": {
            "start": {"sequence": 4, "byte_offset": 1},
            "end": {"sequence": 5, "byte_offset_exclusive": 2},
        }
        if outcome.value == "matched"
        else None,
        "clock": {
            "origin_id": _ORIGIN,
            "started_at_ns": 100,
            "deadline_at_ns": 1000000100,
            "decided_at_ns": 1000000100 if outcome.value == "timeout" else 102,
        },
        "durability": "complete" if failure is None else "end_unconfirmed",
        "end_failure": failure,
    }


@dataclass
class MonitorBoundary:
    result: monitor.MonitorReport = field(default_factory=_report)
    failure: Exception | None = None
    calls: list[monitor.MonitorRequest] = field(default_factory=list)
    entered: asyncio.Queue[None] = field(default_factory=asyncio.Queue)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    gated: bool = False

    async def invoke(self, request: monitor.MonitorRequest) -> monitor.MonitorReport:
        self.calls.append(request)
        self.entered.put_nowait(None)
        if self.gated:
            await self.release.wait()
        if self.failure is not None:
            raise self.failure
        return self.result


@dataclass
class MonitorService(Service):
    monitor: MonitorBoundary
    runtime: ObservationRuntime
    tasks: list[asyncio.Task[Exchange]] = field(default_factory=list)

    def spawn(self, path: str, body: object, **kwargs: Any) -> asyncio.Task[Exchange]:
        task = asyncio.create_task(self.request(path, body, **kwargs))
        self.tasks.append(task)
        return task


@asynccontextmanager
async def _service(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig = _CONFIGS[0],
    *,
    stub_monitor: bool = True,
) -> AsyncIterator[MonitorService]:
    module = _t009_module()
    created, _ = _t009_runtime_spy(module, monkeypatch)
    boundary, reads = MonitorBoundary(), ReadBoundary()

    def forbidden(*args: object, **kwargs: object) -> Any:
        del args, kwargs
        pytest.fail("Monitor delivery tests must not create/open journal resources")

    for name in ("create", "open", "create_v2", "open_v2"):
        monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, name, forbidden)
    with process_credential(config) as (bootstrap, token):
        context = module._LaunchContext(config, bootstrap)
        app = module.create_app(config, _launch_context=context)
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        assert len(created) == 1
        runtime = created[0]
        if stub_monitor:
            monkeypatch.setattr(runtime, "monitor", boundary.invoke)
        monkeypatch.setattr(runtime, "read_record", reads.read)
        monkeypatch.setattr(runtime, "read_page", reads.read)
        service = MonitorService(app, config, token, reads, context, boundary, runtime)
        try:
            yield service
        finally:
            boundary.release.set()
            await asyncio.gather(*service.tasks, return_exceptions=True)
            await lifespan.finish()


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize(
    "device", [False, True], ids=["Basic-shaped", "Enhanced-shaped"]
)
@pytest.mark.asyncio
async def test_literal_post_delivers_exact_closed_ordered_report_and_binary_request(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    config: ServiceConfig,
    device: bool,
) -> None:
    async with _service(process_credential, monkeypatch, config) as service:
        service.monitor.result = _report(model.MonitorOutcome.MATCHED, device=device)
        _success(
            await service.request(_ROUTE, _BODY),
            _wire(model.MonitorOutcome.MATCHED, device=device),
        )
        assert service.monitor.calls == [
            monitor.MonitorRequest(_SESSION, b"\x00\xffA", 1000, 65536)
        ]
        assert service.boundary.calls == []  # No implicit evidence fetch.


@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"])
@pytest.mark.asyncio
async def test_literal_monitor_route_rejects_other_methods_before_body(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        response = await service.request(
            _ROUTE,
            {},
            scope=service.scope(_ROUTE, method=method),
            exchange=Exchange(forbid_receive=True),
        )
        _error(response, 405, "request", "method_not_allowed")
        assert service.monitor.calls == []


@pytest.mark.parametrize(
    "variant", ["slash", "case", "encoded", "missing_raw", "absolute"]
)
@pytest.mark.asyncio
async def test_route_aliases_are_not_normalized_or_redirected(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        scope = service.scope(_ROUTE)
        if variant == "slash":
            scope = service.scope(_ROUTE + "/")
        elif variant == "case":
            scope = service.scope(_ROUTE.replace("monitor", "Monitor"))
        elif variant == "encoded":
            scope["raw_path"] = b"/v1/observation/%6donitor"
        elif variant == "missing_raw":
            scope.pop("raw_path")
        else:
            scope["raw_path"] = b"http://127.0.0.1/v1/observation/monitor"
        _error(
            await service.request(
                _ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
            ),
            404,
            "request",
            "route_not_found",
        )
        assert service.monitor.calls == []


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
@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.asyncio
async def test_security_precedes_body_core_and_stopping_with_no_store(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    status: int,
    code: str,
    config: ServiceConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with _service(process_credential, monkeypatch, config) as service:
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
                    _SECRET.encode(),
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
            scope["query_string"] = b"condition_base64=" + _SECRET.encode()
        scope["headers"] = headers
        response = await service.request(
            _ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
        )
        _error(response, status, "request", code)
        if status == 401:
            assert response.headers[b"www-authenticate"] == b"Bearer"
        assert service.monitor.calls == []
        assert service.token not in response.payload
        assert service.token.decode() not in caplog.text
        assert _SECRET not in caplog.text


_INVALID: list[tuple[str, dict[str, Any]]] = []
value: Any
for key in _BODY:
    _INVALID.append((f"missing-{key}", {k: v for k, v in _BODY.items() if k != key}))
for key in (
    "run_id",
    "start_cursor",
    "profile_path",
    "journal_path",
    "clock",
    "output",
    "extra",
):
    _INVALID.append((f"extra-{key}", {**_BODY, key: _SECRET}))
for value in ("", "\0", "x\0y", "x" * 257, "é" * 129, None, True, 1, []):
    _INVALID.append((f"session-{value!r}", {**_BODY, "session_id": value}))
for value in (
    "",
    "AA",
    "AB==",
    "AA===",
    "AA==\n",
    " AA==",
    "_w==",
    "-w==",
    "é",
    "A===",
    "!!!!",
    base64.b64encode(b"x" * 257).decode(),
    None,
    True,
    1,
    [],
):
    _INVALID.append((f"condition-{value!r}", {**_BODY, "condition_base64": value}))
for key, limit in (("timeout_ms", 4000), ("max_rx_bytes", 1048576)):
    for value in (0, -1, limit + 1, True, False, 1.0, "1", None, []):
        _INVALID.append((f"{key}-{value!r}", {**_BODY, key: value}))


@pytest.mark.parametrize("label,body", _INVALID, ids=[item[0] for item in _INVALID])
@pytest.mark.asyncio
async def test_closed_fields_and_exact_domains_reject_before_core(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    body: dict[str, Any],
) -> None:
    del label
    async with _service(process_credential, monkeypatch) as service:
        _error(await service.request(_ROUTE, body), 422, "request", "invalid_request")
        assert service.monitor.calls == []


@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b"[]",
        b"{} trailing",
        b"\xff",
        b'{"session_id":"\\ud800"}',
        _json(_BODY).replace(b'"timeout_ms":1000', b'"timeout_ms":NaN'),
        _json(_BODY).replace(b'"timeout_ms":1000', b'"timeout_ms":Infinity'),
        *[_json(_BODY)[:-1] + b',"' + key.encode() + b'":null}' for key in _BODY],
    ],
)
@pytest.mark.asyncio
async def test_strict_utf8_json_duplicates_nonfinite_and_root_shape(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    raw: bytes,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        _error(
            await service.request(_ROUTE, {}, raw=raw),
            422,
            "request",
            "invalid_request",
        )
        assert service.monitor.calls == []


@pytest.mark.parametrize(
    "session,condition,timeout,maximum",
    [
        (" ", b"\x00", 1, 1),
        ("x" * 256, bytes(range(256)), 4000, 1048576),
        ("é" * 128, b"\xff", 1, 1048576),
        ("e\u0301", b"overlap", 4000, 1),
        (" /opaque/id ", b"\x00\r\n\xff", 1000, 65536),
    ],
)
@pytest.mark.asyncio
async def test_wire_edges_preserve_opaque_session_and_literal_bytes_without_defaults(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    session: str,
    condition: bytes,
    timeout: int,
    maximum: int,
) -> None:
    body = {
        "session_id": session,
        "condition_base64": base64.b64encode(condition).decode(),
        "timeout_ms": timeout,
        "max_rx_bytes": maximum,
    }
    async with _service(process_credential, monkeypatch) as service:
        _success(await service.request(_ROUTE, body), _wire())
        assert service.monitor.calls == [
            monitor.MonitorRequest(
                model.SessionId(session), condition, timeout, maximum
            )
        ]


@pytest.mark.parametrize(
    "media,status",
    [
        (b"application/json", 200),
        (b"application/json; charset=UTF-8", 200),
        (None, 415),
        (b"text/json", 415),
        (b"application/json; charset=latin-1", 415),
        (b"application/json; charset=utf-8; charset=utf-8", 415),
        (b"application/json; profile=x", 415),
    ],
)
@pytest.mark.asyncio
async def test_same_json_media_gate_precedes_body_and_core(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    media: bytes | None,
    status: int,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        scope = service.scope(_ROUTE)
        scope["headers"] = [(k, v) for k, v in scope["headers"] if k != b"content-type"]
        if media is not None:
            scope["headers"].append((b"content-type", media))
        response = await service.request(
            _ROUTE,
            _BODY,
            scope=scope,
            exchange=None if status == 200 else Exchange(forbid_receive=True),
        )
        if status == 200:
            _success(response, _wire())
        else:
            _error(response, 415, "request", "unsupported_media_type")
            assert service.monitor.calls == []


@pytest.mark.parametrize("size", [16384, 16385])
@pytest.mark.parametrize("declared", [b"0", b"16384", b"999999"])
@pytest.mark.asyncio
async def test_actual_chunked_body_bound_counts_bytes_independently_of_content_length(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    size: int,
    declared: bytes,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
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
            assert len(service.monitor.calls) == 1
        else:
            _error(response, 413, "request", "payload_too_large")
            assert service.monitor.calls == []


_MONITOR_REJECTIONS: tuple[tuple[monitor.MonitorRejectedKind, int], ...] = (
    ("no_associated_session", 404),
    ("session_not_associated", 409),
    ("not_active", 409),
    ("monitor_unavailable", 503),
    ("capability_unavailable", 409),
    ("busy", 409),
    ("evidence_policy_incompatible", 422),
)
_FAILURES: list[tuple[Exception, int, str, str]] = [
    (monitor.MonitorRejected(kind), status, "monitor", kind)
    for kind, status in _MONITOR_REJECTIONS
]
_FAILURES += [
    (
        evidence.JournalFailure(evidence.JournalOperation.APPEND, kind, _SECRET),
        {
            evidence.JournalFailureKind.INVALID_INPUT: 422,
            evidence.JournalFailureKind.SESSION_MISMATCH: 409,
            evidence.JournalFailureKind.JOURNAL_MISSING: 404,
            evidence.JournalFailureKind.BUSY: 503,
            evidence.JournalFailureKind.CLOSED: 409,
        }.get(kind, 500),
        "journal",
        kind.value,
    )
    for kind in evidence.JournalFailureKind
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
    ids=[f"{s}-{c}" for _, _, s, c in _FAILURES],
)
@pytest.mark.asyncio
async def test_all_core_and_twenty_start_journal_failures_have_exact_private_mapping(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status: int,
    source: str,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with _service(process_credential, monkeypatch) as service:
        service.monitor.failure = failure
        _error(await service.request(_ROUTE, _BODY), status, source, code)
        assert len(service.monitor.calls) == 1
        assert service.token.decode() not in caplog.text
        assert _SECRET not in caplog.text


@pytest.mark.parametrize("outcome", list(model.MonitorOutcome))
@pytest.mark.parametrize(
    "device", [False, True], ids=["Basic-shaped", "Enhanced-shaped"]
)
@pytest.mark.parametrize("unconfirmed", [False, True])
@pytest.mark.asyncio
async def test_every_outcome_and_durability_is200_with_exact_fact_projection(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    outcome: model.MonitorOutcome,
    device: bool,
    unconfirmed: bool,
) -> None:
    failure = (
        monitor.MonitorEndFailure("journal", "io_failure") if unconfirmed else None
    )
    async with _service(process_credential, monkeypatch) as service:
        service.monitor.result = _report(outcome, device=device, failure=failure)
        _success(
            await service.request(_ROUTE, _BODY),
            _wire(
                outcome,
                device=device,
                failure={"source": "journal", "code": "io_failure"}
                if unconfirmed
                else None,
            ),
        )
        assert len(service.monitor.calls) == 1
        assert service.boundary.calls == []


@pytest.mark.parametrize(
    "failure",
    [
        *[
            monitor.MonitorEndFailure("journal", kind.value)
            for kind in evidence.JournalFailureKind
        ],
        monitor.MonitorEndFailure("service", "internal_failure"),
    ],
    ids=lambda failure: f"{failure.source}-{failure.code}",
)
@pytest.mark.asyncio
async def test_all_end_failures_embed_only_source_code_without_changing_outcome(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    failure: monitor.MonitorEndFailure,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        service.monitor.result = _report(model.MonitorOutcome.MATCHED, failure=failure)
        _success(
            await service.request(_ROUTE, _BODY),
            _wire(
                model.MonitorOutcome.MATCHED,
                failure={"source": failure.source, "code": failure.code},
            ),
        )


@pytest.mark.asyncio
async def test_real_inactive_runtime_rejection_is_monitor_category_without_resources(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _service(process_credential, monkeypatch, stub_monitor=False) as service:
        _error(
            await service.request(_ROUTE, _BODY),
            404,
            "monitor",
            "no_associated_session",
        )


@pytest.mark.asyncio
async def test_stopping_precedes_even_invalid_body_and_core_admission(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        service.launch_context.request_stop()
        _error(
            await service.request(_ROUTE, {}, exchange=Exchange(forbid_receive=True)),
            503,
            "service",
            "stopping",
        )
        assert service.monitor.calls == []


@pytest.mark.asyncio
async def test_not_started_service_rejects_before_body_or_runtime_construction(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _t009_module()
    created, _ = _t009_runtime_spy(module, monkeypatch)
    config = _CONFIGS[0]
    with process_credential(config) as (bootstrap, token):
        context = module._LaunchContext(config, bootstrap)
        service = Service(
            module.create_app(config, _launch_context=context),
            config,
            token,
            ReadBoundary(),
            context,
        )
        _error(
            await service.request(_ROUTE, {}, exchange=Exchange(forbid_receive=True)),
            503,
            "service",
            "stopping",
        )
        assert created == []


@pytest.mark.parametrize(
    "device", [False, True], ids=["Basic-shaped", "Enhanced-shaped"]
)
@pytest.mark.parametrize("path", ["/v1/evidence/record", "/v1/evidence/page"])
@pytest.mark.parametrize(
    "kind,outcome",
    [("start", model.MonitorOutcome.MATCHED)]
    + [("end", outcome) for outcome in model.MonitorOutcome],
)
@pytest.mark.asyncio
async def test_both_operation_markers_extend_evidence_with_exact_closed_shapes(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
    path: str,
    kind: str,
    outcome: model.MonitorOutcome,
) -> None:
    report = _report(outcome, device=device)
    start = model.OperationStartedEvidence(
        3, _OPERATION, "monitor", report.provenance, 1000, 65536, _ORIGIN, b"\x00\xffA"
    )
    end = model.OperationEndedEvidence(
        8,
        _OPERATION,
        "monitor",
        3,
        report.window,
        report.outcome,
        report.examined_rx_bytes,
        0,
        report.match,
        report.clock,
    )
    expected = _wire(outcome, device=device)
    start_wire = {
        "kind": "operation_started",
        "sequence": 3,
        "operation_id": _OPERATION,
        "operation_kind": "monitor",
        "provenance": _provenance(device)[1],
        "timeout_ms": 1000,
        "max_rx_bytes": 65536,
        "clock_origin_id": _ORIGIN,
        "condition_base64": "AP9B",
    }
    end_wire = {
        "kind": "operation_ended",
        "sequence": 8,
        "operation_id": _OPERATION,
        "operation_kind": "monitor",
        "start_sequence": 3,
        "window": expected["window"],
        "outcome": outcome.value,
        "examined_rx_bytes": expected["examined_rx_bytes"],
        "observer_loss_records": 0,
        "match": expected["match"],
        "clock": expected["clock"],
    }
    async with _service(process_credential, monkeypatch) as service:
        record, wire = (start, start_wire) if kind == "start" else (end, end_wire)
        service.boundary.result = RunEvidencePage(
            RunId("run-é"),
            _SESSION,
            _page(records=(record,), snapshot_end_exclusive=9, charged_bytes=800),
        )
        body = (
            {"session_id": _SESSION.value, "sequence": record.sequence}
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
        _success(
            await service.request(path, body),
            _envelope(records=[wire], snapshot_end_exclusive=9, charged_bytes=800),
        )
        assert len(service.boundary.calls) == 1
        assert service.monitor.calls == []


@pytest.mark.parametrize("size", [_LIMIT, _LIMIT + 1])
@pytest.mark.asyncio
async def test_report_has_independent_whole_canonical_json_cap_after_core_settlement(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    size: int,
) -> None:
    expected = _wire()
    expected["provenance"]["connection_provenance"]["fields"] = [
        {"name": "padding", "value": ""}
    ]
    padding = "x" * (size - len(_json(expected)))
    expected["provenance"]["connection_provenance"]["fields"][0]["value"] = padding
    assert len(_json(expected)) == size
    report = _report()
    envelope = report.provenance.connection_provenance.to_snapshot()
    provenance = replace(
        report.provenance,
        connection_provenance=model.PersistedConnectionProvenance(
            replace(envelope, fields=(model.ProvenanceField("padding", padding),))
        ),
    )
    async with _service(process_credential, monkeypatch) as service:
        service.monitor.result = replace(report, provenance=provenance)
        response = await service.request(_ROUTE, _BODY)
        if size == _LIMIT:
            _success(response, expected)
        else:
            _error(response, 413, "monitor", "delivery_too_large")
        assert len(service.monitor.calls) == 1
        assert service.boundary.calls == []


@pytest.mark.asyncio
async def test_unprojectable_report_fails_privately_without_refetch_or_raw_exception(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BrokenProvenance(model.BackendConnectionProvenance):
        def to_snapshot(self) -> model.ConnectionProvenanceSnapshot:
            raise RuntimeError(_SECRET)

    caplog.set_level(logging.DEBUG)
    async with _service(process_credential, monkeypatch) as service:
        report = _report()
        service.monitor.result = replace(
            report,
            provenance=replace(
                report.provenance, connection_provenance=BrokenProvenance()
            ),
        )
        _error(await service.request(_ROUTE, _BODY), 500, "service", "internal_failure")
        assert _SECRET not in caplog.text
        assert service.boundary.calls == []


async def _entered_or_response(
    task: asyncio.Task[Exchange], entered: asyncio.Queue[None]
) -> None:
    """Fail promptly on a missing route; wait on actual Core-entry notification."""
    notification = asyncio.create_task(entered.get())
    try:
        done, _ = await asyncio.wait(
            (task, notification), timeout=3, return_when=asyncio.FIRST_COMPLETED
        )
        assert done, "service job did not enter Core or finish delivery"
        if task in done:
            response = task.result()
            assert response.status == 200, response.payload
            pytest.fail("gated Core boundary returned before release")
        await notification
    finally:
        notification.cancel()
        await asyncio.gather(notification, return_exceptions=True)


@pytest.mark.asyncio
async def test_single_registered_monitor_slot_rejects_second_and_releases_after_settlement(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        service.monitor.gated = True
        first = service.spawn(_ROUTE, _BODY)
        await _entered_or_response(first, service.monitor.entered)
        _error(
            await service.request(_ROUTE, _BODY), 503, "service", "operation_capacity"
        )
        assert len(service.monitor.calls) == 1
        # Validation still precedes service capacity; no second Core admission.
        _error(await service.request(_ROUTE, {}), 422, "request", "invalid_request")
        assert len(service.monitor.calls) == 1
        service.monitor.release.set()
        _success(await first, _wire())
        _success(await service.request(_ROUTE, _BODY), _wire())
        assert len(service.monitor.calls) == 2


@pytest.mark.parametrize("pool", ["read", "mutation"])
@pytest.mark.asyncio
async def test_one_monitor_is_independent_of_all_eight_read_or_mutation_service_slots(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    pool: str,
) -> None:
    entered: asyncio.Queue[None] = asyncio.Queue()
    release = asyncio.Event()
    async with _service(process_credential, monkeypatch) as service:

        async def read(value: model.EvidenceReference) -> RunEvidencePage:
            del value
            entered.put_nowait(None)
            await release.wait()
            return service.boundary.result

        async def detach() -> Any:
            entered.put_nowait(None)
            await release.wait()
            return service.runtime.status()

        if pool == "read":
            monkeypatch.setattr(service.runtime, "read_record", read)
            path, body = (
                "/v1/evidence/record",
                {"session_id": _SESSION.value, "sequence": 0},
            )
        else:
            monkeypatch.setattr(service.runtime, "detach", detach)
            path, body = "/v1/observation/detach", {}
        # Detach has a zero-byte request body; mutation timing is the boundary.
        kwargs: dict[str, Any] = {"raw": b""} if pool == "mutation" else {}
        try:
            pending = []
            for _ in range(8):
                task = service.spawn(path, body, **kwargs)
                pending.append(task)
                await _entered_or_response(task, entered)
            service.monitor.gated = True
            monitor_job = service.spawn(_ROUTE, _BODY)
            await _entered_or_response(monitor_job, service.monitor.entered)
            _error(
                await service.request(path, body, **kwargs),
                503,
                "service",
                "operation_capacity",
            )
            _error(
                await service.request(_ROUTE, _BODY),
                503,
                "service",
                "operation_capacity",
            )
            assert len(service.monitor.calls) == 1
            release.set()
            for task in pending:
                assert (await task).status == 200
            assert not monitor_job.done()  # Other pools settling cannot release it.
            service.monitor.release.set()
            _success(await monitor_job, _wire())
        finally:
            release.set()


@pytest.mark.asyncio
async def test_t014_service_stop_seals_core_synchronously_without_detaching(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _service(process_credential, monkeypatch, stub_monitor=False) as service:
        before = service.runtime.status()
        service.launch_context.request_stop()
        with pytest.raises(monitor.MonitorRejected) as rejected:
            await service.runtime.monitor(monitor.MonitorRequest(_SESSION, b"x", 1, 1))
        assert rejected.value.kind == "monitor_unavailable"
        assert service.runtime.status() == before
        service.launch_context.request_stop()  # Repeated stop keeps the same seal.


@pytest.mark.asyncio
async def test_t014_cancelled_delivery_keeps_monitor_service_slot_until_core_settles(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        service.monitor.gated = True
        settled = asyncio.Event()
        invoke = service.monitor.invoke

        async def owned(request: monitor.MonitorRequest) -> monitor.MonitorReport:
            try:
                return await invoke(request)
            finally:
                settled.set()

        monkeypatch.setattr(service.runtime, "monitor", owned)
        delivery = service.spawn(_ROUTE, _BODY)
        await _entered_or_response(delivery, service.monitor.entered)
        delivery.cancel()
        with pytest.raises(asyncio.CancelledError):
            await delivery
        assert not settled.is_set()
        _error(
            await service.request(_ROUTE, _BODY), 503, "service", "operation_capacity"
        )
        assert len(service.monitor.calls) == 1
        service.monitor.release.set()
        await asyncio.wait_for(settled.wait(), timeout=3)
        _success(await service.request(_ROUTE, _BODY), _wire())
        assert len(service.monitor.calls) == 2


@pytest.mark.asyncio
async def test_t014_shutdown_seals_immediately_and_joins_monitor_before_final_detach(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _t009_module()
    created, _ = _t009_runtime_spy(module, monkeypatch)
    config = _CONFIGS[0]
    entered: asyncio.Queue[None] = asyncio.Queue()
    release, sealed = asyncio.Event(), asyncio.Event()
    trace: list[str] = []
    with process_credential(config) as (bootstrap, token):
        context = module._LaunchContext(config, bootstrap)
        app = module.create_app(config, _launch_context=context)
        lifespan = AppLifespan(app)
        # Observe the actual Core seal, without replacing its behavior.
        original_seal = ObservationRuntime._seal_monitors

        def seal(owner: ObservationRuntime) -> None:
            original_seal(owner)
            sealed.set()

        monkeypatch.setattr(ObservationRuntime, "_seal_monitors", seal)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        runtime = created[0]
        detach = runtime.detach

        async def final_detach() -> Any:
            trace.append("final-detach")
            return await detach()

        async def pending(request: monitor.MonitorRequest) -> monitor.MonitorReport:
            del request
            entered.put_nowait(None)
            await release.wait()
            trace.append("monitor-settled")
            return _report(model.MonitorOutcome.SERVICE_STOPPING)

        monkeypatch.setattr(runtime, "monitor", pending)
        monkeypatch.setattr(runtime, "detach", final_detach)
        service = Service(app, config, token, ReadBoundary(), context)
        delivery = asyncio.create_task(service.request(_ROUTE, _BODY))
        shutdown: asyncio.Task[None] | None = None
        try:
            await _entered_or_response(delivery, entered)
            shutdown = asyncio.create_task(lifespan.finish())
            await asyncio.wait_for(sealed.wait(), timeout=3)
            assert context.stopping
            assert not shutdown.done()
            assert trace == []
            _error(
                await service.request(
                    _ROUTE, {}, exchange=Exchange(forbid_receive=True)
                ),
                503,
                "service",
                "stopping",
            )
            release.set()
            _success(await delivery, _wire(model.MonitorOutcome.SERVICE_STOPPING))
            await shutdown
            assert trace == ["monitor-settled", "final-detach"]
            assert (
                context.final_status is not None and context.final_status.owner_settled
            )
            assert context.final_evidence_read_cleanup_confirmed
        finally:
            release.set()
            await asyncio.gather(delivery, return_exceptions=True)
            if shutdown is None:
                await lifespan.finish()
            else:
                await shutdown


def _t019_padding(expected: object, size: int, unit: str) -> str:
    remaining = size - len(_json(expected))
    width = len(_json(unit)) - 2
    assert remaining >= 0 and width > 0
    return unit * (remaining // width) + "x" * (remaining % width)


def _t019_marker(
    device: bool, kind: str
) -> tuple[
    model.OperationStartedEvidence | model.OperationEndedEvidence, dict[str, Any]
]:
    report, wire = (
        _report(model.MonitorOutcome.MATCHED, device=device),
        _wire(model.MonitorOutcome.MATCHED, device=device),
    )
    if kind == "start":
        return model.OperationStartedEvidence(
            3,
            _OPERATION,
            "monitor",
            report.provenance,
            1000,
            65536,
            _ORIGIN,
            b"\0\xffA",
        ), {
            "kind": "operation_started",
            "sequence": 3,
            "operation_id": _OPERATION,
            "operation_kind": "monitor",
            "provenance": wire["provenance"],
            "timeout_ms": 1000,
            "max_rx_bytes": 65536,
            "clock_origin_id": _ORIGIN,
            "condition_base64": "AP9B",
        }
    assert kind == "end"
    return model.OperationEndedEvidence(
        8,
        _OPERATION,
        "monitor",
        3,
        report.window,
        report.outcome,
        report.examined_rx_bytes,
        0,
        report.match,
        report.clock,
    ), {
        "kind": "operation_ended",
        "sequence": 8,
        "operation_id": _OPERATION,
        "operation_kind": "monitor",
        "start_sequence": 3,
        "window": wire["window"],
        "outcome": "matched",
        "examined_rx_bytes": 5,
        "observer_loss_records": 0,
        "match": wire["match"],
        "clock": wire["clock"],
    }


@pytest.mark.parametrize("size", [16384, 16385])
@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.asyncio
async def test_t019_fragmented_maximum_unicode_and_binary_body_counts_actual_utf8_bytes(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    size: int,
    config: ServiceConfig,
) -> None:
    session, condition = "🚀" * 64, bytes(range(256))
    body = {
        "session_id": session,
        "condition_base64": base64.b64encode(condition).decode(),
        "timeout_ms": 4000,
        "max_rx_bytes": 1048576,
    }
    raw = _json(body)
    raw += b" " * (size - len(raw))
    cut = raw.index("🚀".encode()) + 1
    exchange = ChunkedExchange(
        chunks=[raw[:cut], raw[cut : cut + 1], raw[cut + 1 : 16383], raw[16383:]]
    )
    async with _service(process_credential, monkeypatch, config) as service:
        scope = service.scope(_ROUTE)
        scope["headers"].append((b"content-length", b"1"))
        response = await service.request(_ROUTE, {}, scope=scope, exchange=exchange)
        if size == 16384:
            _success(response, _wire())
            assert service.monitor.calls == [
                monitor.MonitorRequest(
                    model.SessionId(session), condition, 4000, 1048576
                )
            ]
        else:
            _error(response, 413, "request", "payload_too_large")
            assert service.monitor.calls == []
        assert exchange.receives == 4 and service.boundary.calls == []


_T019_REQUEST_EDGES: list[tuple[str, dict[str, Any], bool]] = [
    ("utf8-256", {**_BODY, "session_id": "🚀" * 64}, True),
    ("utf8-257", {**_BODY, "session_id": "🚀" * 64 + "x"}, False),
    ("combining-256", {**_BODY, "session_id": "e\u0301" * 85 + "x"}, True),
    ("combining-257", {**_BODY, "session_id": "e\u0301" * 85 + "xx"}, False),
    ("session-false", {**_BODY, "session_id": False}, False),
    ("condition-false", {**_BODY, "condition_base64": False}, False),
    (
        "condition-256",
        {**_BODY, "condition_base64": base64.b64encode(b"\xff" * 256).decode()},
        True,
    ),
    (
        "condition-257-same-encoded-length",
        {**_BODY, "condition_base64": base64.b64encode(b"\xff" * 257).decode()},
        False,
    ),
    ("pad-bits-one", {**_BODY, "condition_base64": "/x=="}, False),
    ("pad-bits-two", {**_BODY, "condition_base64": "//9="}, False),
    (
        "pad-bits-maximum",
        {
            **_BODY,
            "condition_base64": base64.b64encode(b"\xff" * 256).decode()[:-3] + "x==",
        },
        False,
    ),
]


@pytest.mark.parametrize(
    "label,body,accepted",
    _T019_REQUEST_EDGES,
    ids=[row[0] for row in _T019_REQUEST_EDGES],
)
@pytest.mark.asyncio
async def test_t019_decoded_request_edges_keep_utf8_and_base64_limits_independent(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    body: dict[str, Any],
    accepted: bool,
) -> None:
    del label
    async with _service(process_credential, monkeypatch) as service:
        response = await service.request(_ROUTE, body)
        if accepted:
            _success(response, _wire())
            assert service.monitor.calls == [
                monitor.MonitorRequest(
                    model.SessionId(body["session_id"]),
                    base64.b64decode(body["condition_base64"], validate=True),
                    body["timeout_ms"],
                    body["max_rx_bytes"],
                )
            ]
        else:
            _error(response, 422, "request", "invalid_request")
            assert service.monitor.calls == []


@pytest.mark.parametrize("key", tuple(_BODY))
@pytest.mark.asyncio
async def test_t019_escaped_duplicate_keys_with_equal_values_are_still_rejected(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    key: str,
) -> None:
    escaped = b'"\\u' + f"{ord(key[0]):04x}".encode() + key[1:].encode() + b'":'
    raw = _json(_BODY)[:-1] + b"," + escaped + _json(_BODY[key]) + b"}"
    async with _service(process_credential, monkeypatch) as service:
        _error(
            await service.request(_ROUTE, {}, raw=raw),
            422,
            "request",
            "invalid_request",
        )
        assert service.monitor.calls == []


@pytest.mark.parametrize(
    "raw",
    [
        _json(_BODY).replace(b'"timeout_ms":1000', b'"timeout_ms":1e0'),
        _json(_BODY).replace(b'"max_rx_bytes":65536', b'"max_rx_bytes":1.0'),
        _json(_BODY).replace(b'"timeout_ms":1000', b'"timeout_ms":-Infinity'),
        _json(_BODY).replace("session-é".encode(), b"\\udc00"),
    ],
)
@pytest.mark.asyncio
async def test_t019_numeric_and_unicode_lexical_forms_do_not_coerce_before_core(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    raw: bytes,
) -> None:
    async with _service(process_credential, monkeypatch) as service:
        _error(
            await service.request(_ROUTE, {}, raw=raw),
            422,
            "request",
            "invalid_request",
        )
        assert service.monitor.calls == []


@pytest.mark.parametrize("kind", list(evidence.JournalFailureKind))
@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.asyncio
async def test_t019_each_journal_start_error_and_embedded_end_error_have_distinct_http_meanings(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    kind: evidence.JournalFailureKind,
    device: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    statuses = {
        "invalid_input": 422,
        "session_mismatch": 409,
        "journal_missing": 404,
        "busy": 503,
        "closed": 409,
    }
    caplog.set_level(logging.DEBUG)
    error = evidence.JournalFailure(evidence.JournalOperation.APPEND, kind, _SECRET)
    error.add_note(_SECRET)
    error.__cause__ = OSError(_SECRET)
    async with _service(process_credential, monkeypatch) as service:
        service.monitor.failure = error
        _error(
            await service.request(_ROUTE, _BODY),
            statuses.get(kind.value, 500),
            "journal",
            kind.value,
        )
        assert len(service.monitor.calls) == 1
        service.monitor.failure = None
        service.monitor.result = _report(
            model.MonitorOutcome.MATCHED,
            device=device,
            failure=monitor.MonitorEndFailure("journal", kind.value),
        )
        expected = _wire(
            model.MonitorOutcome.MATCHED,
            device=device,
            failure={"source": "journal", "code": kind.value},
        )
        _success(await service.request(_ROUTE, _BODY), expected)
        assert len(service.monitor.calls) == 2 and service.boundary.calls == []
        service.monitor.result = _report()
        _success(await service.request(_ROUTE, _BODY), _wire())
        assert len(service.monitor.calls) == 3
        assert service.token.decode() not in caplog.text and _SECRET not in caplog.text


@pytest.mark.parametrize("unit", ["é", '"', "🚀"], ids=["utf8", "escaped", "four-byte"])
@pytest.mark.parametrize("size", [_LIMIT, _LIMIT + 1])
@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.asyncio
async def test_t019_report_bound_counts_encoded_provenance_after_owned_settlement(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    unit: str,
    size: int,
    device: bool,
) -> None:
    expected, report = (
        _wire(model.MonitorOutcome.MATCHED, device=device),
        _report(model.MonitorOutcome.MATCHED, device=device),
    )
    expected["provenance"]["connection_provenance"]["fields"] = [
        {"name": "padding", "value": ""}
    ]
    padding = _t019_padding(expected, size, unit)
    expected["provenance"]["connection_provenance"]["fields"][0]["value"] = padding
    assert len(_json(expected)) == size
    snapshot = report.provenance.connection_provenance.to_snapshot()
    report = replace(
        report,
        provenance=replace(
            report.provenance,
            connection_provenance=model.PersistedConnectionProvenance(
                replace(snapshot, fields=(model.ProvenanceField("padding", padding),))
            ),
        ),
    )
    async with _service(process_credential, monkeypatch) as service:
        service.monitor.result = report
        settled = asyncio.Event()

        async def invoke(request: monitor.MonitorRequest) -> monitor.MonitorReport:
            result = await service.monitor.invoke(request)
            settled.set()
            return result

        monkeypatch.setattr(service.runtime, "monitor", invoke)
        response = await service.request(_ROUTE, _BODY)
        assert settled.is_set() and service.monitor.result is report
        if size == _LIMIT:
            _success(response, expected)
        else:
            _error(response, 413, "monitor", "delivery_too_large")
            assert response.payload == _json(
                {"error": {"source": "monitor", "code": "delivery_too_large"}}
            )
            # Explicitly retrieve a retained end reference; no automatic read or retry.
            assert service.boundary.calls == []
            end, wire = _t019_marker(device, "end")
            service.boundary.result = RunEvidencePage(
                RunId("run-é"),
                _SESSION,
                _page(records=(end,), snapshot_end_exclusive=9, charged_bytes=800),
            )
            _success(
                await service.request(
                    "/v1/evidence/record", {"session_id": _SESSION.value, "sequence": 8}
                ),
                _envelope(records=[wire], snapshot_end_exclusive=9, charged_bytes=800),
            )
            assert len(service.boundary.calls) == 1
        assert len(service.monitor.calls) == 1


@pytest.mark.parametrize("state", ["busy", "stopping"])
@pytest.mark.parametrize("fault", ["origin", "auth", "query", "media"])
@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.asyncio
async def test_t019_security_readiness_media_precedence_over_body_and_monitor_capacity(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    fault: str,
    config: ServiceConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with _service(process_credential, monkeypatch, config) as service:
        service.monitor.gated = True
        pending = service.spawn(_ROUTE, _BODY)
        await _entered_or_response(pending, service.monitor.entered)
        if state == "stopping":
            service.launch_context.request_stop()
        scope = service.scope(_ROUTE)
        if fault == "origin":
            scope["headers"].append((b"origin", _SECRET.encode()))
            status, source, code = 403, "request", "origin_rejected"
        elif fault == "auth":
            scope["headers"] = [
                (key, value)
                for key, value in scope["headers"]
                if key != b"authorization"
            ]
            status, source, code = 401, "request", "authentication_required"
        elif fault == "query":
            scope["query_string"] = _SECRET.encode()
            status, source, code = 400, "request", "query_not_allowed"
        else:
            scope["headers"].append((b"content-type", b"application/json"))
            status, source, code = (
                (503, "service", "stopping")
                if state == "stopping"
                else (415, "request", "unsupported_media_type")
            )
        response = await service.request(
            _ROUTE, {}, scope=scope, exchange=Exchange(forbid_receive=True)
        )
        _error(response, status, source, code)
        assert len(service.monitor.calls) == 1 and service.boundary.calls == []
        assert service.token.decode() not in caplog.text and _SECRET not in caplog.text
        service.monitor.release.set()
        _success(await pending, _wire())
