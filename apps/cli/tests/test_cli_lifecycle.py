"""T011/T013 lifecycle delivery and reported facts over guarded 006 composition.

Reuse its real bootstrap/lifespan/runtime, strict fake Basic and temporary SQLite.
Only HTTPX's external transport is bridged to ASGI on the owning loop. This is
software composition, not native lifecycle/installed-process/hardware acceptance.
The provisional private attach seam adds paths=AttachPaths to exchange; only the
documented HTTP fields/methods/facts govern, not this internal Python signature.
"""

import asyncio
import importlib.util
import inspect
import json
import logging
import sys
from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from dutchmate_core.adapters import basic_serial, observation_runtime, sqlite_evidence
from dutchmate_core.adapters.toml_profile import resolve_profile
from dutchmate_core.evidence import (
    EvidencePageOutcome,
    EvidenceRetrievalRequest,
    JournalFailure,
    JournalFailureKind,
    JournalOperation,
    PendingEvidenceRecord,
    PendingRxBytesEvidence,
    PendingSegmentStartedEvidence,
)
from dutchmate_core.model import (
    ConnectionProvenanceSnapshot,
    EvidenceRecord,
    PersistedConnectionProvenance,
    ProvenanceField,
    RxBytesEvidence,
    SegmentEndedEvidence,
    SegmentEndReason,
    SegmentStartedEvidence,
    SessionId,
    SessionPolicy,
)
from dutchmate_core.profile import ProfileFailureKind, ResolvedDutProfile
from dutchmate_core.runtime import (
    ObservationRuntime,
    PreparationFailure,
    PreparedObservationRun,
    RunId,
    RuntimeIssue,
    RuntimeIssueSource,
    RuntimeRejectedError,
    RuntimeRejectedKind,
    RuntimeState,
    RuntimeStatus,
    RuntimeTerminalReason,
)

from dutchmate_cli import client, context
from dutchmate_cli import main as cli_main

_ATTACH = "/v1/observation/attach"
_DETACH = "/v1/observation/detach"


@dataclass
class _Harness:
    helper: Any
    composition: Any
    service: Any
    journal_open: Any
    requests: list[httpx.Request] = field(default_factory=list)
    responses: list[httpx.Response] = field(default_factory=list)
    serving: ContextVar[bool] = field(default_factory=lambda: ContextVar("t011_serving", default=False))

    @property
    def endpoint(self) -> context.Endpoint:
        return context.Endpoint(host=self.service.config.host, port=self.service.config.port)


@pytest_asyncio.fixture
async def lifecycle_service(
    tmp_path: Path, account_home: Path, monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[_Harness]:
    source = Path(__file__).resolve().parents[2] / "service/tests/test_service_http.py"
    name = "_dutchmate_cli_t011_service_contract"
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, helper)
    spec.loader.exec_module(helper)
    journal_open = sqlite_evidence.SqliteEvidenceJournal.open
    composition = inspect.unwrap(helper.t011_composition)(tmp_path, monkeypatch)
    async with helper._t011_service(account_home, monkeypatch, composition) as service:
        harness = _Harness(helper, composition, service, journal_open)
        yield harness


def _bridge(harness: _Harness, patch: pytest.MonkeyPatch, *, origin: bool = False) -> None:
    """Keep SDK/client real; distinguish server resource work from client work."""
    owning_loop = asyncio.get_running_loop()

    class Transport(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.asgi = httpx.ASGITransport(
                app=harness.service.app, client=(harness.service.config.host, 12345),
            )

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if asyncio.get_running_loop() is owning_loop:
                return await self.serve(request)
            # Direct console main owns its client loop in a joined test worker.
            # Actual service/runtime mutations still run on their original loop.
            return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
                self.serve(request), owning_loop,
            ))

        async def serve(self, request: httpx.Request) -> httpx.Response:
            harness.requests.append(request)
            if origin:
                request.headers["Origin"] = "https://private-browser-origin"
            token = harness.serving.set(True)
            try:
                response = await self.asgi.handle_async_request(request)
                harness.responses.append(response)
                return response
            finally:
                harness.serving.reset(token)

        async def aclose(self) -> None:
            await self.asgi.aclose()

    def transport(*args: Any, **kwargs: Any) -> Transport:
        return Transport()

    patch.setattr(httpx, "AsyncHTTPTransport", transport)
    original_resolve = resolve_profile
    original_construct = basic_serial.BasicSerialBackend.__init__
    original_create = sqlite_evidence.SqliteEvidenceJournal.create

    def require_service() -> None:
        assert harness.serving.get(), "CLI must not call Core/Profile/journal/backend resources"

    def resolve(*args: Any, **kwargs: Any) -> Any:
        require_service()
        return original_resolve(*args, **kwargs)

    def construct(*args: Any, **kwargs: Any) -> None:
        require_service()
        original_construct(*args, **kwargs)

    async def create(cls: Any, *args: Any, **kwargs: Any) -> Any:
        require_service()
        return await original_create(*args, **kwargs)

    patch.setattr(observation_runtime, "resolve_profile", resolve)
    patch.setattr(basic_serial.BasicSerialBackend, "__init__", construct)
    patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "create", classmethod(create))
    for method in ("open", "stat", "resolve"):
        original = getattr(Path, method)

        def access(path: Path, *args: Any, _original: Any = original, **kwargs: Any) -> Any:
            if path == harness.composition.profile_path or path.suffix in {".toml", ".sqlite3"}:
                require_service()
            return _original(path, *args, **kwargs)

        patch.setattr(Path, method, access)


async def _exchange(
    harness: _Harness, command: str, *, profile: str | None = None, journal: str | None = None,
) -> tuple[int, dict[str, Any]]:
    options: dict[str, Any] = {}
    if command == "attach":
        if "paths" not in inspect.signature(client.exchange).parameters:
            pytest.fail("T012 attach HTTP mapping is absent", pytrace=False)
        options["paths"] = context.AttachPaths(
            profile_path=profile if profile is not None else str(harness.composition.profile_path),
            journal_path=journal if journal is not None else str(harness.composition.journal_path),
        )
    delivery = client.DeliveryState()
    credential = context.read_credential()
    code, record = await client.exchange(
        endpoint=harness.endpoint, command=command, credential=credential, delivery=delivery,
        **options,
    )
    assert record.endswith(b"\n") and record.count(b"\n") == 1
    assert len(record[:-1]) <= 1048576
    return code, dict(json.loads(record))


def _wire(harness: _Harness, command: str, expected: dict[str, str] | None = None) -> None:
    request = harness.requests[-1]
    assert request.method == "POST"
    assert request.url.raw_path == (_ATTACH if command == "attach" else _DETACH).encode()
    assert request.headers.get_list("authorization") == ["Bearer " + harness.service.token.decode()]
    assert "origin" not in request.headers
    if command == "attach":
        assert request.headers.get_list("content-type") == ["application/json"]
        assert json.loads(request.content) == (expected if expected is not None else {
            "profile_path": str(harness.composition.profile_path),
            "journal_path": str(harness.composition.journal_path),
        })
    else:
        assert request.content == b""
    assert harness.responses[-1].is_closed


@pytest.mark.asyncio
async def test_t011_harness_uses_actual_security_and_inactive_lifespan(lifecycle_service: _Harness) -> None:
    h = lifecycle_service
    authority = f"127.0.0.1:{h.service.config.port}"
    transport = httpx.ASGITransport(app=h.service.app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, trust_env=False) as requester:
        rejected = await requester.get(f"http://{authority}/v1/observation/status", headers={"Host": authority})
        assert rejected.status_code == 401
        accepted = await requester.get(f"http://{authority}/v1/observation/status", headers={
            "Host": authority, "Authorization": "Bearer " + h.service.token.decode(),
        })
        assert accepted.status_code == 200 and accepted.json()["runtime"]["state"] == "inactive"
    assert h.composition.reads == h.composition.destinations == h.composition.serials == []


@pytest.mark.asyncio
async def test_t011_attach_and_bodyless_detach_use_existing_runtime_and_resources(
    lifecycle_service: _Harness, monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = lifecycle_service
    with monkeypatch.context() as patch:
        _bridge(h, patch)
        code, attached = await _exchange(h, "attach")
        assert code == 0, "T012 attach delivery is absent"
        _wire(h, "attach")
        assert attached["runtime"]["state"] == h.service.runtime.status().state.value == "active"
        assert len(h.composition.serials) == len(h.composition.journals) == 1
        code, detached = await _exchange(h, "detach")
        assert code == 0, "T012 detach delivery is absent"
        _wire(h, "detach")
        assert detached["runtime"]["state"] == "terminated"
        assert detached["runtime"]["terminal_reason"] == "detached"
        assert detached["runtime"]["run_id"] == attached["runtime"]["run_id"]
    assert len(h.requests) == 2 and h.composition.serials[0].close_calls == 1


@pytest.mark.asyncio
async def test_t011_detach_inactive_is_one_bodyless_request_without_file_work(
    lifecycle_service: _Harness, monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = lifecycle_service
    with monkeypatch.context() as patch:
        _bridge(h, patch)
        code, report = await _exchange(h, "detach")
        assert code == 0, "T012 detach delivery is absent"
        _wire(h, "detach")
        assert report["runtime"]["state"] == "inactive"
    assert len(h.requests) == 1 and h.composition.reads == h.composition.destinations == h.composition.serials == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["missing_file", "invalid_syntax"])
async def test_t011_profile_failure_is_authoritative_remote_error_not_cli_validation(
    lifecycle_service: _Harness, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    h = lifecycle_service
    if kind == "missing_file":
        h.composition.profile_path.unlink()
    else:
        h.composition.profile_path.write_text("private malformed = [", encoding="utf-8")
    with monkeypatch.context() as patch:
        _bridge(h, patch)
        code, error = await _exchange(h, "attach")
        assert code == 4
        assert error == {"error": {"source": "profile", "code": kind}}
        _wire(h, "attach")
    assert len(h.requests) == 1 and h.composition.destinations == h.composition.serials == []


@pytest.mark.asyncio
async def test_t011_busy_rejection_does_not_create_second_run_or_client_preflight(
    lifecycle_service: _Harness, monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = lifecycle_service
    seeded = await h.service.request(_ATTACH, "POST", h.helper._t011_body(h.composition.profile_path, h.composition.journal_path))
    assert seeded.status == 200 and h.service.runtime.status().state is RuntimeState.ACTIVE
    before = h.service.runtime.status()
    destination = h.composition.journal_path.with_name("busy-no-new-journal.sqlite3")
    with monkeypatch.context() as patch:
        _bridge(h, patch)
        code, error = await _exchange(h, "attach", journal=str(destination))
        assert code == 4 and error == {"error": {"source": "runtime", "code": "busy"}}
        _wire(h, "attach", {"profile_path": str(h.composition.profile_path), "journal_path": str(destination)})
    assert h.service.runtime.status() == before and len(h.requests) == 1
    assert h.composition.destinations == [h.composition.journal_path]
    assert len(h.composition.serials) == 1 and not destination.exists()


@pytest.mark.asyncio
async def test_t011_uncertain_cleanup_rejection_remains_remote_without_retry(
    lifecycle_service: _Harness, monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = lifecycle_service
    h.composition.close_error = OSError("private fake close failure")
    seeded = await h.service.request(_ATTACH, "POST", h.helper._t011_body(h.composition.profile_path, h.composition.journal_path))
    assert seeded.status == 200
    closed = await h.service.request(_DETACH, "POST")
    assert closed.status == 200 and not h.service.runtime.status().physical_release_confirmed
    destination = h.composition.journal_path.with_name("uncertain-no-new-journal.sqlite3")
    with monkeypatch.context() as patch:
        _bridge(h, patch)
        code, error = await _exchange(h, "attach", journal=str(destination))
        assert code == 4 and error == {"error": {"source": "runtime", "code": "cleanup_unconfirmed"}}
    assert len(h.requests) == 1 and len(h.composition.serials) == 1
    assert h.composition.serials[0].close_calls == 1 and not destination.exists()


@pytest.mark.asyncio
async def test_t011_failed_startup_report_still_delivers_exit_zero(
    lifecycle_service: _Harness, monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = lifecycle_service
    h.composition.open_error = OSError("private fake open failure")
    with monkeypatch.context() as patch:
        _bridge(h, patch)
        code, report = await _exchange(h, "attach")
        assert code == 0 and report["runtime"]["state"] == "failed"
        assert report["runtime"]["terminal_reason"] == "startup_failure"
        _wire(h, "attach")
    assert len(h.requests) == 1 and h.composition.journal_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "detach"])
@pytest.mark.parametrize("case,expected", [("stale", "authentication_required"), ("origin", "origin_rejected")])
async def test_t011_mutations_still_use_actual_auth_and_browser_gate(
    lifecycle_service: _Harness, account_home: Path, monkeypatch: pytest.MonkeyPatch,
    command: str, case: str, expected: str,
) -> None:
    h = lifecycle_service
    if case == "stale":
        token = h.service.token
        alternate = (b"0" if token[:1] != b"0" else b"1") + token[1:]
        (account_home / ".local/state/dutchmate/service/credential").write_bytes(alternate + b"\n")
    with monkeypatch.context() as patch:
        _bridge(h, patch, origin=case == "origin")
        code, error = await _exchange(h, command)
        assert code == 4 and error == {"error": {"source": "request", "code": expected}}
    assert len(h.requests) == 1 and h.composition.reads == h.composition.destinations == h.composition.serials == []


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "detach"])
@pytest.mark.parametrize("state", list(RuntimeState), ids=lambda state: state.value)
async def test_t011_every_valid_200_core_report_delivers_zero_including_failed(
    lifecycle_service: _Harness, monkeypatch: pytest.MonkeyPatch,
    command: str, state: RuntimeState,
) -> None:
    h = lifecycle_service
    resolved = resolve_profile(h.composition.profile_path)
    if state is RuntimeState.INACTIVE:
        returned = RuntimeStatus()
    else:
        terminal = state in {RuntimeState.FAILED, RuntimeState.TERMINATED}
        returned = RuntimeStatus(
            state=state, run_id=RunId("reported-run"), profile=resolved,
            session_id=SessionId("reported-session"), owner_settled=terminal,
            physical_release_confirmed=terminal, recorder_close_confirmed=terminal,
            terminal_reason=RuntimeTerminalReason.STARTUP_FAILURE if state is RuntimeState.FAILED
                            else RuntimeTerminalReason.DISCONNECTED if terminal else None,
            primary_issue=RuntimeIssue(RuntimeIssueSource.PREPARATION, ProfileFailureKind.INVALID_VALUE)
                          if state is RuntimeState.FAILED else None,
        )
    calls = 0

    async def result(*args: Any, **kwargs: Any) -> RuntimeStatus:
        nonlocal calls
        calls += 1
        return returned

    with monkeypatch.context() as patch:
        app_module = h.helper._t009_module()
        if command == "attach":
            patch.setattr(app_module, "attach_basic_observation", result)
        else:
            patch.setattr(h.service.runtime, "detach", result)
        _bridge(h, patch)
        code, report = await _exchange(h, command)
        assert code == 0, "HTTP200 is report delivery, never an active/cleanup success claim"
        _wire(h, command)
        view = report["runtime"]
        assert view["state"] == state.value
        assert view["owner_settled"] is returned.owner_settled
        assert view["attach_admissible"] is returned.attach_admissible
        assert view["terminal_reason"] == (returned.terminal_reason.value if returned.terminal_reason else None)
    assert calls == len(h.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "detach"])
@pytest.mark.parametrize("kind,status", [
    (RuntimeRejectedKind.BUSY, 409), (RuntimeRejectedKind.CLEANUP_UNCONFIRMED, 409),
    (RuntimeRejectedKind.INVALID_REQUEST, 422), (RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT, 500),
])
async def test_t011_runtime_categories_are_delivered_without_cli_policy_reconstruction(
    lifecycle_service: _Harness, monkeypatch: pytest.MonkeyPatch,
    command: str, kind: RuntimeRejectedKind, status: int,
) -> None:
    h = lifecycle_service

    async def rejected(*args: Any, **kwargs: Any) -> RuntimeStatus:
        raise RuntimeRejectedError(kind)

    with monkeypatch.context() as patch:
        if command == "attach":
            patch.setattr(h.helper._t009_module(), "attach_basic_observation", rejected)
        else:
            patch.setattr(h.service.runtime, "detach", rejected)
        _bridge(h, patch)
        code, error = await _exchange(h, command)
        assert code == 4 and error == {"error": {"source": "runtime", "code": kind.value}}
        assert len(h.requests) == 1 and h.responses[0].status_code == status


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "detach"])
async def test_t011_unexpected_service_fault_is_normalized_without_raw_diagnostics(
    lifecycle_service: _Harness, monkeypatch: pytest.MonkeyPatch, command: str,
) -> None:
    h = lifecycle_service

    async def rejected(*args: Any, **kwargs: Any) -> RuntimeStatus:
        raise RuntimeError("private service failure")

    with monkeypatch.context() as patch:
        if command == "attach":
            patch.setattr(h.helper._t009_module(), "attach_basic_observation", rejected)
        else:
            patch.setattr(h.service.runtime, "detach", rejected)
        _bridge(h, patch)
        code, error = await _exchange(h, command)
        assert code == 4 and error == {"error": {"source": "service", "code": "internal_failure"}}
        assert len(h.requests) == 1 and h.responses[0].status_code == 500


# T013: tests only. Fail on lost/relabelled facts, private diagnostics, invented
# IDs, reread Profile values, a second reader, or dropped/transformed idle bytes.
_T013_PRIVATE = "private-t013-path-cause-body-header-token-sentinel"
_T013_PROFILE = {
    "format_version": 1,
    "dut": {"id": "fixture/t011", "name": "HTTP observation fixture"},
    "backend": {"kind": "basic_serial", "expected_device": "/dev/t011-fixture-only"},
    "uart": {"baud_rate": 19200, "data_bits": 7, "parity": "even", "stop_bits": 2,
             "hardware_flow_control": False, "software_flow_control": True},
    "open_lines": {"dtr": "deasserted", "rts": "deasserted"},
    "policy": {"uart_rx_enabled": True, "evidence_recording_enabled": True,
               "uart_tx_enabled": False, "semantic_control_enabled": False,
               "automatic_reconnect_enabled": False},
    "session_policy": {"max_retained_records": 100, "max_retained_charged_bytes": 65536,
                       "max_record_charged_bytes": 8192, "max_database_pages": 128,
                       "max_retrieval_page_records": 11, "max_retrieval_page_charged_bytes": 16384},
}
_T013_OPAQUE = {
    "envelope_version": 1, "backend_kind": "fixture/opaque", "backend_schema_version": 37,
    "fields": [{"name": "count", "value": 7}, {"name": "flag", "value": False},
               {"name": "text", "value": "opaque-é"}, {"name": "unknown", "value": None}],
}
_T013_OBSERVATION = [
    {"capabilities": ["uart_receive"],
     "backend_observation_timestamp_domain": {
         "domain_id": "host-observer-1", "observer": "host", "meaning": "observation",
         "unit": "nanosecond", "origin_id": "host-process-1"},
     "loss_observability": {"kind": "upstream_loss_not_observable"},
     "connection_provenance": _T013_OPAQUE},
    {"capabilities": ["uart_receive"],
     "backend_observation_timestamp_domain": {
         "domain_id": "fixture-device-domain-1", "observer": "device", "meaning": "observation",
         "unit": "tick", "origin_id": "fixture-device-origin-1"},
     "loss_observability": {"kind": "observer_reports_uart_loss",
                            "observer_id": "fixture-device-uart-observer", "scope": "fixture-uart-rx-buffer"},
     "connection_provenance": _T013_OPAQUE},
]


@dataclass
class _T013Run:
    harness: _Harness
    fixture: Any
    shape: int
    path_methods: dict[str, Any] = field(default_factory=dict)
    journal: sqlite_evidence.SqliteEvidenceJournal | None = None
    commits: asyncio.Queue[EvidenceRecord] = field(default_factory=asyncio.Queue)
    prepare_entered: asyncio.Event = field(default_factory=asyncio.Event)
    prepare_allow: asyncio.Event = field(default_factory=asyncio.Event)
    segment_entered: asyncio.Event = field(default_factory=asyncio.Event)
    segment_allow: asyncio.Event = field(default_factory=asyncio.Event)
    close_entered: asyncio.Event = field(default_factory=asyncio.Event)
    close_allow: asyncio.Event = field(default_factory=asyncio.Event)
    prepare_failure: bool = False
    recording_failure: bool = False
    recorder_close_failure: bool = False
    recorder_close_calls: int = 0

    @property
    def session_id(self) -> SessionId:
        assert self.journal is not None
        return self.journal.session_id

    @property
    def policy(self) -> SessionPolicy:
        assert self.journal is not None
        return self.journal.policy

    async def prepare(self, profile: ResolvedDutProfile) -> PreparedObservationRun:
        assert self.harness.serving.get(), "Only the service may prepare resources"
        self.prepare_entered.set()
        await self.prepare_allow.wait()
        if self.prepare_failure:
            raise PreparationFailure(
                RuntimeIssue(RuntimeIssueSource.PREPARATION, JournalFailureKind.IO_FAILURE),
                recorder_close_confirmed=True,
            )
        self.journal = await sqlite_evidence.SqliteEvidenceJournal.create(
            self.harness.composition.journal_path, profile.session_policy,
        )
        return PreparedObservationRun(self, self.fixture.backend)

    async def append(self, draft: PendingEvidenceRecord) -> EvidenceRecord:
        if isinstance(draft, PendingSegmentStartedEvidence):
            self.segment_entered.set()
            await self.segment_allow.wait()
        if self.recording_failure and isinstance(draft, PendingRxBytesEvidence):
            raise JournalFailure(JournalOperation.APPEND, JournalFailureKind.IO_FAILURE)
        assert self.journal is not None
        record = await self.journal.append(draft)
        self.commits.put_nowait(record)
        return record

    async def close(self) -> None:
        self.recorder_close_calls += 1
        self.close_entered.set()
        await self.close_allow.wait()
        assert self.journal is not None
        await self.journal.close()
        if self.recorder_close_failure:
            raise JournalFailure(JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE)

    async def commit(self) -> EvidenceRecord:
        return await asyncio.wait_for(self.commits.get(), 3.0)


@pytest_asyncio.fixture(params=[0, 1], ids=["basic", "enhanced-shaped"])
async def t013_run(
    request: pytest.FixtureRequest, lifecycle_service: _Harness, monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[_T013Run]:
    # Reuse the existing factories by file path, independent of Core test collection.
    source = Path(__file__).resolve().parents[3] / "core/tests/fakes.py"
    name = "_dutchmate_cli_t013_backend_fixtures"
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    run = _T013Run(lifecycle_service, module.BACKEND_FIXTURE_FACTORIES[request.param](), request.param)
    run.path_methods = {name: getattr(Path, name) for name in ("open", "stat", "resolve")}
    for gate in (run.prepare_allow, run.segment_allow, run.close_allow):
        gate.set()
    run.fixture.connection.descriptor = replace(
        run.fixture.connection.descriptor,
        connection_provenance=PersistedConnectionProvenance(ConnectionProvenanceSnapshot(
            envelope_version=1, backend_kind="fixture/opaque", backend_schema_version=37,
            fields=(ProvenanceField("count", 7), ProvenanceField("flag", False),
                    ProvenanceField("text", "opaque-é"), ProvenanceField("unknown", None)),
        )),
    )

    async def attach(runtime: ObservationRuntime, profile_path: str, journal_path: str) -> RuntimeStatus:
        assert Path(journal_path) == lifecycle_service.composition.journal_path
        profile = resolve_profile(Path(profile_path))
        assert isinstance(profile, ResolvedDutProfile)
        return await runtime.attach(profile, run.prepare)

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle_service.helper._t009_module(), "attach_basic_observation", attach)
        _bridge(lifecycle_service, patch)
        try:
            yield run
        finally:
            for gate in (run.prepare_allow, run.segment_allow, run.close_allow,
                         run.fixture.backend.open_gate.allow, run.fixture.connection.close_gate.allow):
                gate.set()
            await asyncio.wait_for(lifecycle_service.service.runtime.detach(), 3.0)
            if run.journal is not None:
                await run.journal.close()


async def _t013_console(
    h: _Harness, command: str, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
    *, expected_code: int = 0,
) -> dict[str, Any]:
    caplog.set_level(logging.DEBUG)
    count = len(h.requests)
    args = ["--host", h.endpoint.host, "--port", str(h.endpoint.port), command]
    if command == "attach":
        args.extend(["--profile", str(h.composition.profile_path), "--journal", str(h.composition.journal_path)])
    code = await asyncio.to_thread(cli_main.main, args)
    stdout, stderr = capsys.readouterr()
    assert code == expected_code
    record = stdout if expected_code == 0 else stderr
    assert (stderr if expected_code == 0 else stdout) == ""
    assert record.endswith("\n") and record.count("\n") == 1
    assert len(record[:-1].encode("utf-8")) <= 1048576
    diagnostics = stdout + stderr + caplog.text
    for private in (_T013_PRIVATE, h.service.token.decode(), str(h.composition.profile_path),
                    str(h.composition.journal_path)):
        assert private not in diagnostics
    assert "Traceback" not in diagnostics and "\x1b" not in diagnostics
    assert len(h.requests) == count + 1 and h.responses[-1].is_closed
    return dict(json.loads(record))


def _t013_report(view: dict[str, Any], run: _T013Run, start: SegmentStartedEvidence) -> None:
    assert view["profile"] == _T013_PROFILE
    assert view["session_id"] == run.session_id.value
    acquisition = view["acquisition"]
    expected = _T013_OBSERVATION[run.shape]
    assert acquisition["descriptor"] == expected
    assert acquisition["provenance"] == {
        **expected, "connection_id": start.connection_id.value, "segment_id": start.segment_id.value,
    }
    values = acquisition["descriptor"]["connection_provenance"]["fields"]
    assert [type(item["value"]) for item in values] == [int, bool, str, type(None)]


@pytest.mark.asyncio
async def test_t013_idle_binary_survives_console_returns_and_profile_source_changes(
    t013_run: _T013Run, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
) -> None:
    run, h = t013_run, t013_run.harness
    attached = (await _t013_console(h, "attach", capsys, caplog))["runtime"]
    start = await run.commit()
    assert isinstance(start, SegmentStartedEvidence)
    _t013_report(attached, run, start)
    assert attached["state"] == "active" and attached["attach_admissible"] is False
    # No client exists while these ambient bytes arrive. No sleeps or new reader.
    payloads = (bytes(range(256)) + b"\x00\xff", b"ambient\r\n\x80\x00")
    for sequence, payload in enumerate(payloads, 1):
        await run.fixture.connection.emit_rx(payload, timestamp=sequence * 10)
        record = await run.commit()
        assert isinstance(record, RxBytesEvidence) and record.payload == payload
        assert record.sequence == sequence
        assert record.observed_at.domain_id == start.provenance.backend_observation_timestamp_domain.domain_id
        assert record.observed_at.value == sequence * 10
    # Test-side edit, using the captured pre-client-guard method. CLI still has
    # no permission to inspect this source on status or detach.
    with run.path_methods["open"](h.composition.profile_path, "w", encoding="utf-8") as source:
        source.write(_T013_PRIVATE + " = [")
    observed = (await _t013_console(h, "status", capsys, caplog))["runtime"]
    assert observed == attached
    h.composition.profile_path.unlink()
    terminal = (await _t013_console(h, "detach", capsys, caplog))["runtime"]
    _t013_report(terminal, run, start)
    assert terminal["run_id"] == attached["run_id"]
    assert terminal["state"] == "terminated" and terminal["terminal_reason"] == "detached"
    assert terminal["primary_issue"] is None and terminal["cleanup_issues"] == []
    assert terminal["attach_admissible"] is True
    assert terminal["acquisition"]["terminal_trigger"] == "explicit_stop"
    assert run.fixture.backend.open_calls == run.fixture.connection.consumer_calls == 1
    assert run.fixture.connection.close_calls == run.recorder_close_calls == 1
    assert h.service.runtime.status().owner_settled and len(h.requests) == 3
    # Persistence readback is exclusively test-side, outside client resource guards.
    assert run.journal is not None
    # No client runs during readback. Restore only Path helpers for this explicit
    # test-side window; physical/account tripwires and server no-reopen stay intact.
    with monkeypatch.context() as readback:
        for name, method in run.path_methods.items():
            readback.setattr(Path, name, method)
        reopened = await h.journal_open(h.composition.journal_path, expected_session_id=run.session_id)
        try:
            page = await reopened.retrieve(EvidenceRetrievalRequest(run.session_id, 11, 16384))
        finally:
            await reopened.close()
    assert page.outcome is EvidencePageOutcome.COMPLETE
    assert page.continuation is None and page.truncated is False
    assert [record.sequence for record in page.records] == [0, 1, 2, 3]
    assert isinstance(page.records[0], SegmentStartedEvidence)
    assert isinstance(page.records[-1], SegmentEndedEvidence)
    assert page.records[-1].reason is SegmentEndReason.EXPLICIT_STOP
    assert [record.payload for record in page.records if isinstance(record, RxBytesEvidence)] == list(payloads)
    assert all(record.connection_id == start.connection_id and record.segment_id == start.segment_id for record in page.records)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["preparation", "open"])
async def test_t013_failed_startup_preserves_only_allocated_session_and_connection_facts(
    t013_run: _T013Run, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, failure: str,
) -> None:
    run, h = t013_run, t013_run.harness
    if failure == "preparation":
        run.prepare_failure = True
    else:
        async def failed_open() -> Any:
            raise RuntimeError(_T013_PRIVATE)
        monkeypatch.setattr(run.fixture.backend, "open", failed_open)
    report = (await _t013_console(h, "attach", capsys, caplog))["runtime"]
    assert report["state"] == "failed" and report["terminal_reason"] == "startup_failure"
    assert type(report["run_id"]) is str and report["profile"] == _T013_PROFILE
    assert report["owner_settled"] is report["recorder_close_confirmed"] is True
    assert report["physical_release_confirmed"] is (failure == "preparation")
    assert report["attach_admissible"] is (failure == "preparation")
    assert report["cleanup_issues"] == []
    if failure == "preparation":
        assert report["session_id"] is report["acquisition"] is None
        assert report["primary_issue"] == {"source": "preparation", "code": "io_failure"}
        assert h.composition.destinations == []
    else:
        assert report["session_id"] == run.session_id.value
        assert report["acquisition"]["descriptor"] is report["acquisition"]["provenance"] is None
        assert report["acquisition"]["primary_failure_kind"] == "transport_failure"
        assert report["primary_issue"] == {"source": "acquisition_start", "code": "transport_failure"}
    assert len(h.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["before_journal", "before_open", "before_segment_commit"])
async def test_t013_attaching_never_invents_uncommitted_identifiers(
    t013_run: _T013Run, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, phase: str,
) -> None:
    run, h = t013_run, t013_run.harness
    gates = {
        "before_journal": (run.prepare_allow, run.prepare_entered),
        "before_open": (run.fixture.backend.open_gate.allow, run.fixture.backend.open_gate.entered),
        "before_segment_commit": (run.segment_allow, run.segment_entered),
    }
    allow, entered = gates[phase]
    allow.clear()
    pending = asyncio.create_task(_exchange(h, "attach"))
    try:
        await asyncio.wait_for(entered.wait(), 3.0)
        report = (await _t013_console(h, "status", capsys, caplog))["runtime"]
        assert report["state"] == "attaching" and report["owner_settled"] is False
        assert type(report["run_id"]) is str and report["profile"] == _T013_PROFILE
        assert report["attach_admissible"] is False
        if phase == "before_journal":
            assert report["session_id"] is report["acquisition"] is None
        else:
            assert report["session_id"] == run.session_id.value
            acquisition = report["acquisition"]
            assert acquisition["provenance"] is None
            assert acquisition["descriptor"] == (
                None if phase == "before_open" else _T013_OBSERVATION[run.shape]
            )
            assert acquisition["terminal_trigger"] is acquisition["primary_failure_kind"] is None
        assert len(h.requests) == 2
    finally:
        allow.set()
        code, _ = await asyncio.wait_for(pending, 3.0)
        assert code == 0


@pytest.mark.asyncio
async def test_t013_detaching_reports_release_before_recorder_settlement(
    t013_run: _T013Run, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
) -> None:
    run, h = t013_run, t013_run.harness
    await _t013_console(h, "attach", capsys, caplog)
    start = await run.commit()
    assert isinstance(start, SegmentStartedEvidence)
    run.close_allow.clear()
    pending = asyncio.create_task(_exchange(h, "detach"))
    try:
        await asyncio.wait_for(run.close_entered.wait(), 3.0)
        draining = (await _t013_console(h, "status", capsys, caplog))["runtime"]
        _t013_report(draining, run, start)
        assert draining["state"] == "detaching" and draining["stop_intent"] == "detach"
        assert draining["owner_settled"] is False and draining["attach_admissible"] is False
        assert draining["physical_release_confirmed"] is True
        assert draining["recorder_close_confirmed"] is False
        assert draining["primary_issue"] is draining["terminal_reason"] is None
        assert draining["cleanup_issues"] == []
        assert draining["acquisition"]["terminal_trigger"] == "explicit_stop"
        assert draining["acquisition"]["primary_failure_kind"] is None
        assert draining["acquisition"]["close_failed"] is False
        assert len(h.requests) == 3
    finally:
        run.close_allow.set()
        code, _ = await asyncio.wait_for(pending, 3.0)
        assert code == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger,primary,reason", [
    ("explicit_stop", None, "detached"), ("disconnected", None, "disconnected"),
    ("recording_failure", "recording_failure", "acquisition_failure"),
    ("transport_failure", "transport_failure", "acquisition_failure"),
])
@pytest.mark.parametrize("backend_close,recorder_close", [(False, False), (True, False), (False, True), (True, True)])
async def test_t013_primary_cleanup_trigger_and_certainty_remain_separate(
    t013_run: _T013Run, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
    trigger: str, primary: str | None, reason: str, backend_close: bool, recorder_close: bool,
) -> None:
    run, h = t013_run, t013_run.harness
    await _t013_console(h, "attach", capsys, caplog)
    start = await run.commit()
    assert isinstance(start, SegmentStartedEvidence)
    run.recorder_close_failure = recorder_close
    if backend_close:
        actual_close = run.fixture.connection.close
        async def close_failed() -> None:
            await actual_close()
            raise RuntimeError(_T013_PRIVATE)
        monkeypatch.setattr(run.fixture.connection, "close", close_failed)
    if trigger == "disconnected":
        await run.fixture.connection.disconnect(_T013_PRIVATE)
    elif trigger == "recording_failure":
        run.recording_failure = True
        await run.fixture.connection.emit_rx(b"private unrecorded bytes", timestamp=10)
    elif trigger == "transport_failure":
        await run.fixture.connection.end_stream_unexpectedly()
    if trigger != "explicit_stop":
        await asyncio.wait_for(run.close_entered.wait(), 3.0)
    terminal = (await _t013_console(h, "detach", capsys, caplog))["runtime"]
    _t013_report(terminal, run, start)
    assert terminal["state"] == ("failed" if primary or backend_close or recorder_close else "terminated")
    assert terminal["terminal_reason"] == reason
    assert terminal["primary_issue"] == (None if primary is None else {"source": "acquisition", "code": primary})
    expected_cleanup = []
    if backend_close:
        expected_cleanup.append({"source": "backend_close", "code": "close_failed"})
    if recorder_close:
        expected_cleanup.append({"source": "recorder_close", "code": "io_failure"})
    assert terminal["cleanup_issues"] == expected_cleanup
    assert terminal["owner_settled"] is True
    assert terminal["physical_release_confirmed"] is (not backend_close)
    assert terminal["recorder_close_confirmed"] is (not recorder_close)
    assert terminal["attach_admissible"] is (not backend_close and not recorder_close)
    acquisition = terminal["acquisition"]
    assert acquisition["terminal_trigger"] == trigger
    assert acquisition["primary_failure_kind"] == primary
    assert acquisition["close_failed"] is backend_close
    assert acquisition["physical_release_confirmed"] is (not backend_close)
    assert run.fixture.connection.consumer_calls == run.fixture.connection.close_calls == run.recorder_close_calls == 1


@pytest.mark.asyncio
async def test_t013_client_preserves_authoritative_wire_facts_without_domain_recomputation(
    t013_run: _T013Run, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
) -> None:
    # A closed typed wire report deliberately disagrees with today's Core
    # predicates. CLI delivery must validate shape, never reconstruct policy.
    from starlette.responses import JSONResponse

    h = t013_run.harness
    app_module = h.helper._t009_module()
    original = app_module.status_response
    def reported(status: RuntimeStatus, **kwargs: Any) -> Any:
        response = original(status, **kwargs)
        value = json.loads(response.body)
        value["runtime"]["attach_admissible"] = True
        value["runtime"]["acquisition"]["primary_failure_kind"] = "recording_failure"
        return JSONResponse(value)
    monkeypatch.setattr(app_module, "status_response", reported)
    view = (await _t013_console(h, "attach", capsys, caplog))["runtime"]
    assert view["state"] == "active" and view["owner_settled"] is False
    assert view["attach_admissible"] is True and view["primary_issue"] is None
    assert view["acquisition"]["primary_failure_kind"] == "recording_failure"
    assert h.service.runtime.status().attach_admissible is False


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["attach", "status", "detach"])
async def test_t013_unrecognized_remote_diagnostics_never_reach_console_or_logs(
    t013_run: _T013Run, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, command: str,
) -> None:
    from starlette.responses import JSONResponse

    h = t013_run.harness
    def private_response(*args: Any, **kwargs: Any) -> Any:
        return JSONResponse(
            {"error": {"source": "service", "code": _T013_PRIVATE, "detail": h.service.token.decode()}},
            status_code=500, headers={"X-Private": _T013_PRIVATE},
        )
    monkeypatch.setattr(h.helper._t009_module(), "status_response", private_response)
    assert await _t013_console(h, command, capsys, caplog, expected_code=5) == {
        "error": {"source": "cli", "code": "invalid_response"}, "request_outcome": "unknown",
    }
    assert h.service.runtime.status().state is (RuntimeState.ACTIVE if command == "attach" else RuntimeState.INACTIVE)
