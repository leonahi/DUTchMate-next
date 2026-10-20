"""012 T016 RED: authenticated bounded Interact delivery and joined ownership.

The real app, credential gate and service registries are always exercised. Pure
wire cases inject immutable Core facts; lifetime cases use the actual Core owner,
both normalized fixtures and temporary v4 journals. Gates control progress only,
never implement admission, matching, cancellation or version policy in test code.
"""

import asyncio
import base64
import importlib
import json
import logging
import socket
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from dutchmate_core import backend, evidence, interact, model, monitor
from dutchmate_core.runtime import ObservationRuntime
from starlette.types import Scope

from dutchmate_service.bootstrap import ServiceConfig
from test_evidence_http import (
    ChunkedExchange,
    ReadBoundary,
    Service,
    _error,
    _json,
    _provenance,
    _t014_core_helpers,
)
from test_service_http import (
    _CONFIGS,
    AppLifespan,
    Exchange,
    _t009_module,
    _t009_runtime_spy,
)
from test_service_http import process_credential as process_credential
from test_service_runtime import Client, flush

ROUTE = "/v2/observation/interact"
SESSION = model.SessionId("session-é")
OPERATION = "12345678-1234-4234-8234-123456789abc"
ORIGIN = "abcdefab-1234-4234-8234-123456789abc"
PRIVATE = "private-012-T016-token-path-SQL-cause"
LIMIT = 1048576
BODY: dict[str, Any] = {
    "session_id": SESSION.value,
    "payload_base64": "AP9TRU5E",
    "conditions_base64": ["UEFTUw==", "RkFJTA=="],
    "timeout_ms": 1000,
    "max_rx_bytes": 1024,
}
pytestmark = pytest.mark.asyncio


def report(
    outcome: model.InteractOutcome = model.InteractOutcome.MATCHED,
    *,
    device: bool = False,
    missing: tuple[str, ...] = (),
) -> interact.InteractReport:
    matched = outcome is model.InteractOutcome.MATCHED
    tx_status = {
        model.InteractOutcome.WRITE_TIMEOUT: backend.BackendWriteStatus.TIMEOUT,
        model.InteractOutcome.PARTIAL_WRITE: backend.BackendWriteStatus.PARTIAL,
    }.get(outcome, backend.BackendWriteStatus.ACKNOWLEDGED)
    failed = outcome in {
        model.InteractOutcome.WRITE_TIMEOUT,
        model.InteractOutcome.PARTIAL_WRITE,
    }
    observation_outcome = (
        model.InteractObservationOutcome.TX_FAILED
        if failed
        else model.InteractObservationOutcome(outcome.value)
    )
    return interact.InteractReport(
        "run-é",
        SESSION,
        OPERATION,
        _provenance(device)[0],
        b"\0\xffSEND",
        (b"PASS", b"FAIL"),
        outcome,
        model.EvidenceReference(SESSION, 3),
        None if "uart_tx_settled" in missing else model.EvidenceReference(SESSION, 6),
        None if "interact_ended" in missing else model.EvidenceReference(SESSION, 7),
        interact.InteractTxFacts(
            True,
            tx_status,
            None
            if outcome is model.InteractOutcome.WRITE_TIMEOUT
            else 3
            if failed
            else 6,
            None,
            "backend_acceptance",
            ORIGIN,
            103,
        ),
        model.InteractObservation(
            model.SequenceRange(
                4, 6 if matched or outcome.value == "byte_limit" else 4
            ),
            observation_outcome,
            4 if matched or outcome.value == "byte_limit" else 0,
            0,
            model.InteractMatch(
                0, model.MonitorMatchStart(4, 0), model.MonitorMatchEnd(4, 4)
            )
            if matched
            else None,
            model.MonitorClockFacts(
                ORIGIN,
                100,
                1000000100,
                1000000100 if outcome.value == "timeout" else 102,
            ),
        ),
        {
            (): "complete",
            ("uart_tx_settled",): "tx_unconfirmed",
            ("interact_ended",): "end_unconfirmed",
            ("uart_tx_settled", "interact_ended"): "both_unconfirmed",
        }[missing],  # type: ignore[arg-type]
        tuple(
            interact.InteractAuditFailure(
                "uart_tx_settled" if kind == "uart_tx_settled" else "interact_ended",
                "journal",
                "busy",
            )
            for kind in missing
        ),
    )


def wire(
    outcome: model.InteractOutcome = model.InteractOutcome.MATCHED,
    *,
    device: bool = False,
    missing: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Independent hand-declared contract, never the production projection."""
    matched = outcome.value == "matched"
    failed = outcome.value in {"write_timeout", "partial_write"}
    return {
        "run_id": "run-é",
        "session_id": SESSION.value,
        "operation_id": OPERATION,
        "provenance": {
            **_provenance(device)[1],
            "boundary_basis": "core_observation_order",
            "causation": "not_established",
        },
        "payload_base64": "AP9TRU5E",
        "conditions_base64": ["UEFTUw==", "RkFJTA=="],
        "outcome": outcome.value,
        "started_record": {"session_id": SESSION.value, "sequence": 3},
        "tx_settled_record": None
        if "uart_tx_settled" in missing
        else {"session_id": SESSION.value, "sequence": 6},
        "ended_record": None
        if "interact_ended" in missing
        else {"session_id": SESSION.value, "sequence": 7},
        "tx": {
            "submitted": True,
            "status": "timeout"
            if outcome.value == "write_timeout"
            else "partial"
            if failed
            else "acknowledged",
            "accepted_prefix_bytes": None
            if outcome.value == "write_timeout"
            else 3
            if failed
            else 6,
            "failure_code": None,
            "acknowledgement_scope": "backend_acceptance",
            "clock_origin_id": ORIGIN,
            "settled_at_ns": 103,
        },
        "observation": {
            "window": {
                "start_inclusive": 4,
                "end_exclusive": 6 if matched or outcome.value == "byte_limit" else 4,
            },
            "outcome": "tx_failed" if failed else outcome.value,
            "examined_rx_bytes": 4 if matched or outcome.value == "byte_limit" else 0,
            "observer_loss_records": 0,
            "match": {
                "condition_index": 0,
                "start": {"sequence": 4, "byte_offset": 0},
                "end": {"sequence": 4, "byte_offset_exclusive": 4},
            }
            if matched
            else None,
            "clock": {
                "origin_id": ORIGIN,
                "started_at_ns": 100,
                "deadline_at_ns": 1000000100,
                "decided_at_ns": 1000000100 if outcome.value == "timeout" else 102,
            },
        },
        "durability": {
            (): "complete",
            ("uart_tx_settled",): "tx_unconfirmed",
            ("interact_ended",): "end_unconfirmed",
            ("uart_tx_settled", "interact_ended"): "both_unconfirmed",
        }[missing],
        "audit_failures": [
            {"record_kind": kind, "source": "journal", "code": "busy"}
            for kind in missing
        ],
    }


@dataclass
class InteractBoundary:
    result: Any = field(default_factory=report)
    failure: Exception | None = None
    calls: list[interact.InteractRequest] = field(default_factory=list)
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    gated: bool = False

    async def invoke(self, request: interact.InteractRequest) -> Any:
        self.calls.append(request)
        self.entered.set()
        try:
            if self.gated:
                await self.release.wait()
            if self.failure is not None:
                raise self.failure
            return self.result
        finally:
            self.finished.set()


@dataclass
class InteractService(Service):
    runtime: ObservationRuntime
    interact: InteractBoundary
    lifespan: AppLifespan
    deliveries: list[asyncio.Task[None]] = field(default_factory=list)
    clients: list[Client] = field(default_factory=list)

    def submit(
        self,
        client: Client | None = None,
        *,
        path: str = ROUTE,
        scope: Scope | None = None,
    ) -> tuple[asyncio.Task[None], Client]:
        client = Client(body=_json(BODY)) if client is None else client
        self.clients.append(client)

        async def deliver() -> None:
            await self.app(scope or self.scope(path), client.receive, client.send)

        task = asyncio.create_task(deliver())
        self.deliveries.append(task)
        return task, client


@asynccontextmanager
async def service(
    credentials: Callable[[ServiceConfig], Any],
    patch: pytest.MonkeyPatch,
    config: ServiceConfig = _CONFIGS[0],
    *,
    stub: bool = True,
) -> AsyncIterator[InteractService]:
    module = _t009_module()
    created, _ = _t009_runtime_spy(module, patch)
    boundary = InteractBoundary()
    with credentials(config) as (bootstrap, token):
        context = module._LaunchContext(config, bootstrap)
        app = module.create_app(config, _launch_context=context)
        lifespan = AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        assert len(created) == 1
        runtime = created[0]
        if stub:
            patch.setattr(runtime, "interact", boundary.invoke)
        s = InteractService(
            app, config, token, ReadBoundary(), context, runtime, boundary, lifespan
        )
        try:
            yield s
        finally:
            boundary.release.set()
            for client in s.clients:
                client.publication_gate.set()
                client.disconnected.set()
            for task in s.deliveries:
                if not task.done():
                    task.cancel()
            await wait(asyncio.gather(*s.deliveries, return_exceptions=True))
            await lifespan.finish()


async def wait[T](work: Awaitable[T]) -> T:
    # Watchdog only. Never an implementation write, audit or shutdown timeout.
    async with asyncio.timeout(3):
        return await work


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
                "T016 missing: authenticated Interact route/admission"
            )
            pytest.fail("Interact delivery ended before the tested boundary")
        assert notification in done, "Interact progress boundary not reached"
    finally:
        notification.cancel()
        await asyncio.gather(notification, return_exceptions=True)


@contextmanager
def hold_service_owner() -> Iterator[tuple[asyncio.Event, asyncio.Event]]:
    """Pause a concrete service job before its first Core invocation.

    The existing app names these private coroutines invoke/invoke_read/
    invoke_monitor. Accept the same naming for the new concrete Interact owner;
    no production hook or public admission API is invented for these tests.
    """
    entered, release = asyncio.Event(), asyncio.Event()
    loop = asyncio.get_running_loop()
    previous = loop.get_task_factory()
    selected = False

    async def held(work: Coroutine[Any, Any, Any]) -> Any:
        entered.set()
        await release.wait()
        return await work

    def factory(
        loop: asyncio.AbstractEventLoop, work: Coroutine[Any, Any, Any], **kwargs: Any
    ) -> asyncio.Future[Any]:
        nonlocal selected
        code = getattr(work, "cr_code", None)
        if (
            not selected
            and code is not None
            and code.co_filename.endswith(
                ("dutchmate_service/app.py", "dutchmate_service/interact_http.py")
            )
            and code.co_name.lstrip("_").startswith("invoke")
        ):
            selected = True
            work = held(work)
        if previous is not None:
            return previous(loop, work, **kwargs)
        return asyncio.Task(work, loop=loop, **kwargs)

    loop.set_task_factory(factory)
    try:
        yield entered, release
    finally:
        loop.set_task_factory(previous)
        release.set()


def core_helpers(patch: pytest.MonkeyPatch) -> Any:
    _t014_core_helpers(patch)
    return importlib.import_module("tests.contract.test_interact_runtime")


@asynccontextmanager
async def active_service(
    credentials: Callable[[ServiceConfig], Any],
    patch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
    config: ServiceConfig = _CONFIGS[0],
    **kwargs: Any,
) -> AsyncIterator[tuple[InteractService, Any]]:
    core = core_helpers(patch)
    async with service(credentials, patch, config, stub=False) as s:
        async with core.runtime_case(
            tmp_path,
            patch,
            core.BACKEND_FIXTURE_FACTORIES[int(device)],
            owner=s.runtime,
            **kwargs,
        ) as c:
            yield s, c


@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.parametrize("outcome", list(model.InteractOutcome))
@pytest.mark.parametrize(
    "missing",
    [
        (),
        ("uart_tx_settled",),
        ("interact_ended",),
        ("uart_tx_settled", "interact_ended"),
    ],
)
async def test_exact_closed_report_keeps_independent_facts_and_honest_ack_scope(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
    outcome: model.InteractOutcome,
    missing: tuple[str, ...],
) -> None:
    async with service(process_credential, monkeypatch) as s:
        s.interact.result = report(outcome, device=device, missing=missing)
        response = await s.request(ROUTE, BODY)
        assert response.status == 200, "T016 missing: explicit API2 Interact delivery"
        assert response.payload == _json(wire(outcome, device=device, missing=missing))
        assert response.headers[b"cache-control"] == b"no-store"
        assert response.headers[b"content-type"].split(b";")[0] == b"application/json"
        assert s.interact.calls == [
            interact.InteractRequest(
                SESSION, b"\0\xffSEND", (b"PASS", b"FAIL"), 1000, 1024
            )
        ]
        assert (
            b"wire_transmitted" not in response.payload
            and b"dut_received" not in response.payload
        )


_INVALID: list[tuple[str, Any]] = []
for key in BODY:
    _INVALID.append((f"missing-{key}", {k: v for k, v in BODY.items() if k != key}))
_ROOT_INVALID: list[tuple[str, Any]] = [
    ("extra", {**BODY, "uart_tx_enabled": True}),
    ("null", None),
    ("list", []),
]
_INVALID.extend(_ROOT_INVALID)
for key, values in (
    ("session_id", ["", "\0", "é" * 129, 3, None, []]),
    (
        "payload_base64",
        [
            "",
            "AA",
            "AA=",
            "AB==",
            "AA===",
            "AA==\n",
            "-_8=",
            "é",
            "A" * 5465,
            base64.b64encode(b"x" * 4097).decode(),
            True,
            None,
            [],
        ],
    ),
    (
        "conditions_base64",
        [
            [],
            ["AA=="] * 5,
            [""],
            ["AB=="],
            ["AA"],
            ["AA==\n"],
            ["-_8="],
            ["A" * 345],
            [base64.b64encode(b"x" * 257).decode()],
            [None],
            [True],
            "AA==",
            None,
        ],
    ),
):
    for index, value in enumerate(values):
        _INVALID.append((f"{key}-{index}", {**BODY, key: value}))
for key, maximum in (("timeout_ms", 4000), ("max_rx_bytes", 1048576)):
    for index, value in enumerate(
        (0, -1, maximum + 1, True, False, 1.0, "1", None, [])
    ):
        _INVALID.append((f"{key}-{index}", {**BODY, key: value}))


@pytest.mark.parametrize("label,body", _INVALID, ids=[v[0] for v in _INVALID])
async def test_closed_request_exact_domains_and_canonical_base64_before_core(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    body: object,
) -> None:
    del label
    async with service(process_credential, monkeypatch) as s:
        _error(await s.request(ROUTE, body), 422, "request", "invalid_request")
        assert s.interact.calls == []


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        b"{} trailing",
        b'{"session_id":"\\ud800"}',
        _json(BODY).replace(b'"timeout_ms":1000', b'"timeout_ms":NaN'),
        _json(BODY).replace(b'"timeout_ms":1000', b'"timeout_ms":Infinity'),
        *[_json(BODY)[:-1] + b',"' + key.encode() + b'":null}' for key in BODY],
    ],
)
async def test_strict_utf8_json_duplicate_keys_and_nonfinite_reject_before_core(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    raw: bytes,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        _error(await s.request(ROUTE, {}, raw=raw), 422, "request", "invalid_request")
        assert not s.interact.calls


@pytest.mark.parametrize(
    "edge", ["minimum", "maximum", "escaped-session", "duplicates"]
)
async def test_legal_edges_preserve_exact_bytes_order_duplicates_and_session(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    edge: str,
) -> None:
    payload = bytes(range(256)) * 16 if edge == "maximum" else b"\0"
    conditions = (
        (bytes(range(256)),) * 4 if edge in {"maximum", "duplicates"} else (b"\0",)
    )
    session_id = "\x01" * 256 if edge == "escaped-session" else "é" * 128
    body: dict[str, Any] = {
        "session_id": session_id,
        "payload_base64": base64.b64encode(payload).decode(),
        "conditions_base64": [base64.b64encode(c).decode() for c in conditions],
        "timeout_ms": 4000 if edge == "maximum" else 1,
        "max_rx_bytes": LIMIT if edge == "maximum" else 1,
    }
    async with service(process_credential, monkeypatch) as s:
        captured = report(model.InteractOutcome.DETACHED)
        session = model.SessionId(session_id)
        s.interact.result = replace(
            captured,
            session_id=session,
            payload=payload,
            conditions=conditions,
            started_record=model.EvidenceReference(session, 3),
            tx_settled_record=model.EvidenceReference(session, 6),
            ended_record=model.EvidenceReference(session, 7),
            tx=replace(captured.tx, accepted_prefix_bytes=len(payload)),
        )
        response = await s.request(ROUTE, body)
        assert response.status == 200, "T016 missing: legal bounded Interact request"
        assert s.interact.calls == [
            interact.InteractRequest(
                model.SessionId(session_id),
                payload,
                conditions,
                body["timeout_ms"],
                body["max_rx_bytes"],
            )
        ]


@pytest.mark.parametrize("size", [16384, 16385])
@pytest.mark.parametrize("claimed", [None, b"0", b"1", b"16384", b"99999999"])
async def test_actual_chunked_utf8_cap_detects_first_excess_byte_without_trusting_length(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    size: int,
    claimed: bytes | None,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        raw = _json(BODY) + b" " * (size - len(_json(BODY)))
        exchange = ChunkedExchange(chunks=[raw[:16384], raw[16384:]])
        scope = s.scope(ROUTE)
        if claimed is not None:
            scope["headers"].append((b"content-length", claimed))
        response = await s.request(ROUTE, BODY, exchange=exchange, scope=scope)
        if size == 16384:
            assert response.status == 200, "T016 missing: request cap inclusive edge"
            assert len(s.interact.calls) == 1
        else:
            _error(response, 413, "request", "payload_too_large")
            assert not s.interact.calls


@pytest.mark.parametrize(
    "media",
    [
        None,
        b"text/plain",
        b"application/json; charset=latin-1",
        b"application/json, application/json",
    ],
)
async def test_media_rejection_precedes_body_and_core(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    media: bytes | None,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        scope = s.scope(ROUTE)
        scope["headers"] = [h for h in scope["headers"] if h[0] != b"content-type"]
        if media is not None:
            scope["headers"].append((b"content-type", media))
        response = await s.request(
            ROUTE, BODY, scope=scope, exchange=Exchange(forbid_receive=True)
        )
        _error(response, 415, "request", "unsupported_media_type")
        assert not s.interact.calls


@pytest.mark.parametrize(
    "kind,status,code",
    [
        ("peer", 403, "peer_rejected"),
        ("host", 400, "host_rejected"),
        ("origin", 403, "origin_rejected"),
        ("browser", 403, "origin_rejected"),
        ("bearer", 401, "authentication_required"),
        ("upgrade", 400, "upgrade_rejected"),
    ],
)
@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
async def test_security_precedes_body_stop_core_and_keeps_all_private_values_unlogged(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    status: int,
    code: str,
    config: ServiceConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with service(process_credential, monkeypatch, config) as s:
        scope = s.scope(ROUTE)
        if kind == "peer":
            scope["client"] = ("192.0.2.1", 1234)
        elif kind in {"host", "bearer"}:
            key = b"host" if kind == "host" else b"authorization"
            scope["headers"] = [
                (k, PRIVATE.encode() if k == key else v) for k, v in scope["headers"]
            ]
        else:
            scope["headers"].append(
                (
                    {
                        "origin": b"origin",
                        "browser": b"sec-fetch-mode",
                        "upgrade": b"upgrade",
                    }[kind],
                    PRIVATE.encode(),
                )
            )
        s.launch_context.request_stop()
        response = await s.request(
            ROUTE,
            BODY,
            scope=scope,
            exchange=Exchange(body=PRIVATE.encode(), forbid_receive=True),
        )
        _error(response, status, "request", code)
        assert s.interact.calls == []
        assert PRIVATE not in caplog.text and s.token.decode() not in caplog.text
        assert b"access-control-allow-origin" not in response.headers


_REJECTIONS = [
    ("no_associated_session", 404),
    ("session_not_associated", 409),
    ("not_active", 409),
    ("busy", 409),
    ("policy_denied", 409),
    ("capability_unavailable", 409),
    ("interact_unavailable", 503),
    ("evidence_policy_incompatible", 422),
]


@pytest.mark.parametrize("kind,status", _REJECTIONS)
async def test_core_admission_rejections_have_fixed_private_envelopes(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    status: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with service(process_credential, monkeypatch) as s:
        s.interact.failure = monitor.InteractRejected(kind)
        _error(await s.request(ROUTE, BODY), status, "interact", kind)
        assert len(s.interact.calls) == 1 and s.interact.finished.is_set()
        assert PRIVATE not in caplog.text and s.token.decode() not in caplog.text


@pytest.mark.parametrize("kind", list(evidence.JournalFailureKind))
async def test_start_failure_preserves_all_twenty_journal_categories_without_report(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    kind: evidence.JournalFailureKind,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        s.interact.failure = evidence.JournalFailure(
            evidence.JournalOperation.APPEND, kind
        )
        status = {
            "invalid_input": 422,
            "session_mismatch": 409,
            "journal_missing": 404,
            "busy": 503,
            "closed": 409,
        }.get(kind.value, 500)
        _error(await s.request(ROUTE, BODY), status, "journal", kind.value)
        assert s.interact.finished.is_set() and len(s.interact.calls) == 1


@pytest.mark.parametrize(
    "fault", ["exception", "wrong-type", "invalid-invariant", "projection"]
)
async def test_unexpected_application_fault_is_joined_private_500_not_backend_report(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    async with service(process_credential, monkeypatch) as s:
        if fault == "exception":
            s.interact.failure = ValueError(PRIVATE)
        elif fault == "wrong-type":
            s.interact.result = {"secret": PRIVATE}
        elif fault == "invalid-invariant":
            object.__setattr__(s.interact.result, "started_record", None)
        else:
            object.__setattr__(s.interact.result, "provenance", object())
        _error(await s.request(ROUTE, BODY), 500, "service", "internal_failure")
        assert s.interact.finished.is_set() and len(s.interact.calls) == 1
        assert PRIVATE not in caplog.text and s.token.decode() not in caplog.text


@pytest.mark.parametrize("size", [LIMIT, LIMIT + 1])
async def test_whole_escaped_report_limit_is_after_settlement_without_trim_retry_or_replay(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    size: int,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        expected = wire()
        prefix_size = len(_json(expected)) - len(_json(expected["run_id"])) + 2
        # Six-byte JSON escapes exercise encoded bytes, not Python character count.
        count, tail = divmod(size - prefix_size, 6)
        padding = "\x01" * count + "x" * tail
        s.interact.result = replace(report(), run_id=padding)
        expected["run_id"] = padding
        assert len(_json(expected)) == size
        response = await s.request(ROUTE, BODY)
        if size == LIMIT:
            assert response.status == 200, (
                "T016 missing: inclusive escaped report bound"
            )
            assert response.payload == _json(expected)
        else:
            _error(response, 413, "interact", "delivery_too_large")
        assert s.interact.finished.is_set() and len(s.interact.calls) == 1


@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced-shaped"])
async def test_real_transaction_early_rx_and_retrieval_use_same_authoritative_journal(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
) -> None:
    async with active_service(process_credential, monkeypatch, tmp_path, device) as (
        s,
        c,
    ):
        body = {**BODY, "session_id": c.journal.session_id.value}
        task, client = s.submit(Client(body=_json(body)))
        await reached(c.writer.entered, task, client)
        assert c.writer.calls == [b"\0\xffSEND"]
        await c.rx(b"ambient PASS tail")
        assert not task.done()
        # RX/intent retrieval must make progress while the independent write waits.
        page = await s.request(
            "/v2/evidence/page",
            {
                "session_id": c.journal.session_id.value,
                "start_inclusive": None,
                "end_exclusive": None,
                "max_records": 100,
                "max_charged_bytes": 131072,
                "cursor": None,
            },
        )
        assert page.status == 200
        before = json.loads(page.payload)["page"]["records"]
        assert [r["kind"] for r in before] == [
            "segment_started",
            "interact_started",
            "rx_bytes",
        ]
        assert base64.b64decode(before[2]["payload_base64"]) == b"ambient PASS tail"
        c.writer.allow.set()
        await wait(task)
        result = json.loads(client.payload)
        assert client.status == 200 and result["outcome"] == "matched"
        assert result["observation"]["match"]["condition_index"] == 0
        assert result["tx"]["acknowledgement_scope"] == "backend_acceptance"
        records = await c.records()
        assert [type(r) for r in records][-2:] == [
            model.UartTxSettledEvidence,
            model.InteractEndedEvidence,
        ]
        assert len(c.writer.calls) == 1 and c.fixture.backend.open_calls == 1


@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
@pytest.mark.parametrize(
    "phase", ["before-intent", "pending-write", "tx-audit", "end-audit"]
)
async def test_lost_delivery_latches_only_interact_and_retains_owner_slot_through_join(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
    loss: str,
    phase: str,
) -> None:
    async with active_service(process_credential, monkeypatch, tmp_path, device) as (
        s,
        c,
    ):
        gate = None
        if phase == "before-intent":
            gate = c.recorder.gates["interact_started"].acknowledgement
        elif phase in {"tx-audit", "end-audit"}:
            gate = c.recorder.gates[
                "uart_tx_settled" if phase == "tx-audit" else "interact_ended"
            ].acknowledgement
        if gate is not None:
            gate.allow.clear()
        body = {**BODY, "session_id": c.journal.session_id.value}
        task, client = s.submit(Client(body=_json(body)))
        if phase == "before-intent":
            assert gate is not None
            await reached(gate.entered, task, client)
        else:
            await reached(c.writer.entered, task, client)
            if phase in {"tx-audit", "end-audit"}:
                assert gate is not None
                await c.rx(b"PASS")
                c.writer.allow.set()
                await reached(gate.entered, task, client)
        if loss == "cancel":
            task.cancel()
        else:
            client.disconnected.set()
        await flush()
        assert s.runtime.status().state.value == "active"
        assert not c.recorder.closed.is_set() and not c.writer.close_entered.is_set()
        _error(await s.request(ROUTE, body), 503, "service", "interact_capacity")
        if gate is not None:
            gate.allow.set()
        c.writer.allow.set()
        # A cancellation must end observation without advancing its manual deadline.
        with pytest.raises(asyncio.CancelledError):
            await wait(task)
        await wait(c.recorder.acks["interact_ended"].get())
        await flush()
        records = await c.records()
        end = next(
            r for r in reversed(records) if isinstance(r, model.InteractEndedEvidence)
        )
        assert end.outcome.value == (
            "matched" if phase in {"tx-audit", "end-audit"} else "cancelled"
        )
        assert len(c.writer.calls) == (0 if phase == "before-intent" else 1)
        assert c.writer.cancellation_signals == 0
        assert s.runtime.status().state.value == "active"


@pytest.mark.parametrize("device", [False, True])
async def test_request_stop_synchronously_seals_before_drain_and_joins_write_and_audit_before_detach(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
) -> None:
    async with active_service(process_credential, monkeypatch, tmp_path, device) as (
        s,
        c,
    ):
        body = {**BODY, "session_id": c.journal.session_id.value}
        task, client = s.submit(Client(body=_json(body)))
        await reached(c.writer.entered, task, client)
        gate = c.recorder.gates["interact_ended"].acknowledgement
        gate.allow.clear()
        original = s.runtime._seal_interacts
        seals: list[str] = []

        def seal() -> None:
            original()
            seals.append("sealed")

        # Observe the callback installed at lifespan, not a substitute stop policy.
        callback = getattr(s.launch_context, "_seal_interacts", None)
        assert callable(callback), "T016 missing: synchronous Interact stop hook"
        assert callback == original
        monkeypatch.setattr(s.launch_context, "_seal_interacts", seal)
        s.launch_context.request_stop()
        assert seals == ["sealed"]
        _error(await s.request(ROUTE, body), 503, "service", "stopping")
        shutdown = asyncio.create_task(s.lifespan.finish())
        try:
            await flush()
            assert not shutdown.done() and not c.writer.close_entered.is_set()
            c.writer.allow.set()
            await reached(gate.entered, task, client)
            assert not shutdown.done() and not c.recorder.closed.is_set()
            gate.allow.set()
            await wait(task)
            await wait(shutdown)
            assert json.loads(client.payload)["outcome"] == "service_stopping"
            assert c.writer.active_at_close == [0] and c.recorder.closed.is_set()
            assert s.launch_context.final_status.owner_settled
        finally:
            c.recorder.release()
            c.writer.allow.set()
            await wait(shutdown)


async def test_registered_but_uninvoked_interact_rechecks_stop_and_never_enters_core(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        with hold_service_owner() as (entered, release):
            task, client = s.submit()
            await reached(entered, task, client)
            assert not s.interact.calls
            # Registration must already consume the sole independent slot.
            _error(await s.request(ROUTE, BODY), 503, "service", "interact_capacity")
            s.launch_context.request_stop()
            release.set()
            await wait(task)
            _error(client, 503, "service", "stopping")
            assert not s.interact.calls


@pytest.mark.parametrize(
    "status,prefix,failure",
    [
        ("acknowledged", 6, None),
        ("partial", 0, None),
        ("timeout", None, None),
        ("disconnected", None, None),
        ("failure", None, backend.BackendFailureKind.IO_FAILURE),
        ("not_submitted", None, None),
    ],
)
async def test_all_tx_variants_keep_unknown_counts_null_and_suppression_honest(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    prefix: int | None,
    failure: backend.BackendFailureKind | None,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        value = report(model.InteractOutcome.CANCELLED)
        tx = interact.InteractTxFacts(
            status != "not_submitted",
            "not_submitted"
            if status == "not_submitted"
            else backend.BackendWriteStatus(status),
            prefix,
            failure,
            "backend_acceptance",
            ORIGIN,
            103,
        )
        s.interact.result = replace(value, tx=tx)
        expected = wire(model.InteractOutcome.CANCELLED)
        expected["tx"] = {
            "submitted": status != "not_submitted",
            "status": status,
            "accepted_prefix_bytes": prefix,
            "failure_code": None if failure is None else failure.value,
            "acknowledgement_scope": "backend_acceptance",
            "clock_origin_id": ORIGIN,
            "settled_at_ns": 103,
        }
        response = await s.request(ROUTE, BODY)
        assert response.status == 200, "T016 missing: normalized TX wire variants"
        assert response.payload == _json(expected)


@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize("malformed", ["wrong-type", "full-count", "partial-count"])
async def test_malformed_backend_returns_stay_audited_failure_facts_in_http200(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
    malformed: str,
) -> None:
    async with active_service(process_credential, monkeypatch, tmp_path, device) as (
        s,
        c,
    ):
        c.writer.result = {
            "wrong-type": object(),
            "full-count": backend.BackendWriteResult(
                backend.BackendWriteStatus.ACKNOWLEDGED, 7, None
            ),
            "partial-count": backend.BackendWriteResult(
                backend.BackendWriteStatus.PARTIAL, 6, None
            ),
        }[malformed]
        body = {**BODY, "session_id": c.journal.session_id.value}
        task, client = s.submit(Client(body=_json(body)))
        await reached(c.writer.entered, task, client)
        c.writer.allow.set()
        await wait(task)
        assert client.status == 200
        result = json.loads(client.payload)
        assert result["outcome"] == "transport_failure"
        assert result["tx"]["status"] == "failure"
        assert result["tx"]["failure_code"] == "internal_contract_failure"
        assert result["tx"]["accepted_prefix_bytes"] is None
        assert result["durability"] == "complete"
        assert len(c.writer.calls) == 1
        assert [type(r) for r in await c.records()][-2:] == [
            model.UartTxSettledEvidence,
            model.InteractEndedEvidence,
        ]


@pytest.mark.parametrize("device", [False, True])
async def test_invalid_clock_after_submitted_write_is_joined_500_without_fabricated_report(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
) -> None:
    async with active_service(process_credential, monkeypatch, tmp_path, device) as (
        s,
        c,
    ):
        body = {**BODY, "session_id": c.journal.session_id.value}
        task, client = s.submit(Client(body=_json(body)))
        await reached(c.writer.entered, task, client)
        c.clock.value = -1
        await flush()
        assert not task.done()
        c.writer.allow.set()
        await wait(task)
        _error(client, 500, "service", "internal_failure")
        assert c.writer.finished.is_set() and c.writer.cancellation_signals == 0
        assert len(c.writer.calls) == 1


@pytest.mark.parametrize("loss", ["cancel", "disconnect"])
async def test_delivery_loss_before_complete_body_never_admits_interact(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    loss: str,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        client = Client(body=_json(BODY), before_body=loss)
        task, client = s.submit(client)
        if loss == "cancel":
            await reached(client.body_entered, task, client)
            task.cancel()
        try:
            await wait(task)
        except asyncio.CancelledError:
            pass
        else:
            assert not client.messages, (
                "T016 missing: disconnect before body was not observed"
            )
            pytest.fail("lost request delivery must terminate before Core admission")
        assert not s.interact.calls and not client.messages


@pytest.mark.parametrize("order", ["interact-first", "existing-first"])
async def test_interact_has_one_strong_independent_slot_and_preserves_all_eighteen_existing_slots(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    order: str,
) -> None:
    from test_annotation_http import _BODY as annotation_body
    from test_annotation_http import _receipt as annotation_receipt
    from test_follow_http import CoreBoundary
    from test_monitor_http import _BODY as monitor_body
    from test_monitor_http import _report as monitor_report
    from test_monitor_lifetime import PendingCalls

    async with service(process_credential, monkeypatch) as s:
        calls, source = PendingCalls(), CoreBoundary(gated=True)
        s.interact.gated = True

        async def annotate(request: object) -> Any:
            await calls.wait("mutation")
            return annotation_receipt()

        async def read(request: object) -> Any:
            await calls.wait("read")
            return s.boundary.result

        async def monitor(request: object) -> Any:
            await calls.wait("monitor")
            return monitor_report()

        monkeypatch.setattr(s.runtime, "annotate", annotate)
        monkeypatch.setattr(s.runtime, "read_record", read)
        monkeypatch.setattr(s.runtime, "monitor", monitor)
        monkeypatch.setattr(s.runtime, "start_follow", source.invoke)
        pending: list[tuple[asyncio.Task[None], Client]] = []
        old_pools = (
            ("/v1/observation/annotations", annotation_body, 8, "operation_capacity"),
            (
                "/v1/evidence/record",
                {"session_id": SESSION.value, "sequence": 0},
                8,
                "operation_capacity",
            ),
            ("/v1/observation/monitor", monitor_body, 1, "operation_capacity"),
            (
                "/v1/observation/follow",
                {"session_id": SESSION.value},
                1,
                "follow_capacity",
            ),
        )

        async def admit_interact() -> None:
            task, client = s.submit()
            pending.append((task, client))
            await reached(s.interact.entered, task, client)

        async def admit_existing() -> None:
            for path, body, count, _ in old_pools:
                for _ in range(count):
                    task, client = s.submit(Client(body=_json(body)), path=path)
                    pending.append((task, client))
                    if path.endswith("follow"):
                        await reached(source.entered, task, client)
                    else:
                        await wait(calls.entered.get())

        try:
            if order == "interact-first":
                await admit_interact()
                await admit_existing()
            else:
                await admit_existing()
                await admit_interact()
            assert len(calls.calls) == 17 and len(source.calls) == 1
            _error(await s.request(ROUTE, BODY), 503, "service", "interact_capacity")
            for path, body, _, code in old_pools:
                _error(await s.request(path, body), 503, "service", code)
            assert len(s.interact.calls) == 1
            calls.release()
            source.release.set()
            s.interact.release.set()
            await wait(asyncio.gather(*(task for task, _ in pending)))
            assert len(pending) == 19 and all(
                client.status == 200 for _, client in pending
            )
            await flush()
            assert (await s.request(ROUTE, BODY)).status == 200
            assert len(s.interact.calls) == 2
        finally:
            calls.release()
            source.release.set()
            s.interact.release.set()


@asynccontextmanager
async def loopback(s: InteractService) -> AsyncIterator[tuple[str, int]]:
    """Test-owned numeric loopback only; real security/bootstrap guards stay on."""
    host = s.config.host
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        if family == socket.AF_INET6:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind((host, s.config.port))
        listener.listen(128)
        listener.setblocking(False)
        server = uvicorn.Server(
            uvicorn.Config(
                s.app,
                host=host,
                port=s.config.port,
                lifespan="off",
                log_config=None,
                access_log=False,
                proxy_headers=False,
                server_header=False,
                date_header=False,
            )
        )
        server.config.load()
        server.lifespan = server.config.lifespan_class(server.config)
        await wait(server.startup(sockets=[listener]))
        try:
            yield host, s.config.port
        finally:
            await wait(server.shutdown(sockets=[listener]))


@pytest.mark.parametrize("config", _CONFIGS, ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("device", [False, True])
async def test_guarded_loopback_disconnect_cancels_observation_but_joins_single_write(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
    config: ServiceConfig,
) -> None:
    # Bind an ephemeral address first, then publish the matching authenticated Host.
    family = socket.AF_INET6 if config.host == "::1" else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as reservation:
        reservation.bind((config.host, 0))
        selected = ServiceConfig(reservation.getsockname()[1], config.host)
    async with active_service(
        process_credential, monkeypatch, tmp_path, device, selected
    ) as (s, c):
        async with loopback(s) as (host, port):
            reader, writer = await asyncio.open_connection(host, port)
            body = _json({**BODY, "session_id": c.journal.session_id.value})
            authority = (
                f"[{host}]:{port}" if family == socket.AF_INET6 else f"{host}:{port}"
            )
            writer.write(
                (
                    f"POST {ROUTE} HTTP/1.1\r\nHost: {authority}\r\nAuthorization: Bearer {s.token.decode()}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
                ).encode()
                + body
            )
            await writer.drain()
            notification = asyncio.create_task(c.writer.entered.wait())
            headers = asyncio.create_task(reader.readuntil(b"\r\n\r\n"))
            try:
                done, _ = await asyncio.wait(
                    (notification, headers),
                    timeout=3,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if headers in done:
                    assert b" 200 " in headers.result(), (
                        "T016 missing: real-loopback Interact route"
                    )
                assert notification in done, (
                    "Interact was not admitted on real loopback"
                )
            finally:
                notification.cancel()
                headers.cancel()
                await asyncio.gather(notification, headers, return_exceptions=True)
                writer.close()
                await writer.wait_closed()
                c.writer.allow.set()
            # This requires a real peer disconnect, which buffered ASGI hides.
            end = await wait(c.recorder.acks["interact_ended"].get())
            assert end.outcome.value == "cancelled"
            assert len(c.writer.calls) == 1 and c.writer.cancellation_signals == 0
            assert s.runtime.status().state.value == "active"
            assert not c.recorder.closed.is_set()


# T021: independent wire edges, with no application/coordinator corrections.
@pytest.mark.parametrize("key", list(BODY))
@pytest.mark.parametrize("value_kind", ["same", "boolean", "nan"])
async def test_t021_encoded_duplicate_keys_never_authorize_or_reach_core(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value_kind: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    escaped_key = f'"\\u{ord(key[0]):04x}{key[1:]}"'.encode()
    duplicate = {"same": _json(BODY[key]), "boolean": b"true", "nan": b"NaN"}[
        value_kind
    ]
    raw = _json(BODY)[:-1] + b"," + escaped_key + b":" + duplicate + b"}"
    async with service(process_credential, monkeypatch) as s:
        response = await s.request(ROUTE, BODY, raw=raw)
        _error(response, 422, "request", "invalid_request")
        assert (
            response.payload
            == b'{"error":{"source":"request","code":"invalid_request"}}'
        )
        assert not s.interact.calls
        assert s.token.decode() not in caplog.text and PRIVATE not in caplog.text


@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize("size", [LIMIT - 1, LIMIT, LIMIT + 1])
async def test_t021_report_provenance_escaping_all_bytes_and_whole_413(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
    size: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from test_follow_http import t015_padding, t015_provenance

    caplog.set_level(logging.DEBUG)
    session = model.SessionId('\x01"\\é' * 32)
    payload = bytes(range(256)) * 16
    conditions = (bytes(range(256)), b"\xff\0\r\n", bytes(range(256)), b"\0")
    body = {
        **BODY,
        "session_id": session.value,
        "payload_base64": base64.b64encode(payload).decode(),
        "conditions_base64": [base64.b64encode(c).decode() for c in conditions],
    }
    expected = wire(model.InteractOutcome.DETACHED, device=device)
    expected.update(
        session_id=session.value,
        payload_base64=body["payload_base64"],
        conditions_base64=body["conditions_base64"],
    )
    for name in ("started_record", "tx_settled_record", "ended_record"):
        expected[name]["session_id"] = session.value
    expected["tx"]["accepted_prefix_bytes"] = 4096
    expected["provenance"]["connection_provenance"]["fields"] = [
        {"name": "padding", "value": ""}
    ]
    padding = t015_padding(size - len(_json(expected)))
    expected["provenance"]["connection_provenance"]["fields"][0]["value"] = padding
    assert len(_json(expected)) == size and len(_json(body)) <= 16384
    captured = report(model.InteractOutcome.DETACHED, device=device)
    captured = replace(
        captured,
        session_id=session,
        payload=payload,
        conditions=conditions,
        provenance=t015_provenance(captured.provenance, padding),
        started_record=model.EvidenceReference(session, 3),
        tx_settled_record=model.EvidenceReference(session, 6),
        ended_record=model.EvidenceReference(session, 7),
        tx=replace(captured.tx, accepted_prefix_bytes=4096),
    )
    async with service(process_credential, monkeypatch) as s:
        s.interact.result = captured
        response = await s.request(ROUTE, body)
        if size <= LIMIT:
            assert response.status == 200 and response.payload == _json(expected)
            assert response.headers[b"cache-control"] == b"no-store"
        else:
            _error(response, 413, "interact", "delivery_too_large")
            assert (
                response.payload
                == b'{"error":{"source":"interact","code":"delivery_too_large"}}'
            )
            assert (
                b'"tx"' not in response.payload
                and b'"provenance"' not in response.payload
            )
        assert s.interact.finished.is_set()
        assert s.interact.calls == [
            interact.InteractRequest(session, payload, conditions, 1000, 1024)
        ]
        assert padding not in caplog.text and s.token.decode() not in caplog.text


@pytest.mark.parametrize(
    "raw",
    [
        b"\xef\xbb\xbf{}",
        b'{"session_id":"\\udfff"}',
        b"[]",
        _json(BODY).replace(b'"timeout_ms":1000', b'"timeout_ms":-Infinity'),
        _json(BODY).replace(b'"timeout_ms":1000', b'"timeout_ms":1e9999'),
        _json(BODY).replace(b'"max_rx_bytes":1024', b'"max_rx_bytes":true'),
        _json(BODY).replace(
            b'"conditions_base64":["UEFTUw==","RkFJTA=="]',
            b'"conditions_base64":[{"payload_base64":"AA=="}]',
        ),
        _json(BODY)[:-1] + b',"tx":{"submitted":true}}',
    ],
)
async def test_t021_other_json_domains_reject_whole_request_with_fixed_error(
    process_credential: Callable[[ServiceConfig], Any],
    monkeypatch: pytest.MonkeyPatch,
    raw: bytes,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        response = await s.request(ROUTE, BODY, raw=raw)
        _error(response, 422, "request", "invalid_request")
        assert not s.interact.calls
