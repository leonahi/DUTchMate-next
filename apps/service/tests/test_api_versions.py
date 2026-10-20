"""012 T016 RED: literal API2 selection and indivisible version admission.

No alternate API, codec or version policy is implemented here. Existing immutable
Core facts exercise real delivery projections; real temporary journals/backends
exercise Profile resolution, association and replacement-generation boundaries.
"""

import asyncio
import base64
import importlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from dutchmate_core import follow, model
from dutchmate_core.adapters import observation_runtime, sqlite_evidence
from dutchmate_core.adapters.toml_profile import resolve_profile
from dutchmate_core.evidence_access import PreparedEvidenceAccess, RunEvidencePage
from dutchmate_core.runtime import PreparedObservationRun
from starlette.types import Message

from test_annotation_http import _BODY as ANNOTATION_BODY
from test_annotation_http import _receipt as annotation_receipt
from test_evidence_http import _envelope, _error, _json, _page, _provenance
from test_follow_http import CoreBoundary, frames, seven_records, started, terminal
from test_interact_http import (
    BODY,
    OPERATION,
    ORIGIN,
    SESSION,
    InteractService,
    active_service,
    core_helpers,
    hold_service_owner,
    reached,
    service,
    wait,
)
from test_monitor_http import _BODY as MONITOR_BODY
from test_monitor_http import _report as monitor_report
from test_service_http import Exchange
from test_service_http import process_credential as process_credential
from test_service_runtime import Client

pytestmark = pytest.mark.asyncio
PAGE = {
    "session_id": SESSION.value,
    "start_inclusive": None,
    "end_exclusive": None,
    "max_records": 32,
    "max_charged_bytes": 65536,
    "cursor": None,
}
ROUTES = (
    ("observation/status", "GET", None),
    (
        "observation/attach",
        "POST",
        {
            "profile_path": "/test-owned/profile.toml",
            "journal_path": "/test-owned/journal.db",
        },
    ),
    ("observation/detach", "POST", None),
    ("observation/monitor", "POST", MONITOR_BODY),
    ("observation/annotations", "POST", ANNOTATION_BODY),
    ("observation/follow", "POST", {"session_id": SESSION.value}),
    ("evidence/record", "POST", {"session_id": SESSION.value, "sequence": 0}),
    ("evidence/page", "POST", PAGE),
)
ALL_ROUTES = (*ROUTES, ("observation/interact", "POST", BODY))


async def call(
    s: InteractService, version: int, suffix: str, method: str, body: object
) -> Exchange:
    path = f"/v{version}/{suffix}"
    return await s.request(
        path,
        body,
        scope=s.scope(path, method=method),
        raw=b"" if body is None else _json(body),
    )


async def attach_legacy(s: InteractService, core: Any, path: Path) -> Any:
    legacy = importlib.import_module(
        "tests.contract.test_observation_runtime"
    )._profile()
    journal = await sqlite_evidence.SqliteEvidenceJournal.create_v3(
        path, legacy.session_policy
    )
    fixture = core.BACKEND_FIXTURE_FACTORIES[0]()

    async def prepare(value: Any) -> PreparedObservationRun:
        return PreparedObservationRun(
            journal,
            fixture.backend,
            evidence_access=PreparedEvidenceAccess(
                journal.session_id, journal.policy, journal
            ),
        )

    await s.runtime.attach(legacy, prepare)
    return journal


@pytest.mark.parametrize("suffix,method,body", ROUTES, ids=[r[0] for r in ROUTES])
async def test_existing_literal_v2_routes_reuse_one_core_entry_and_unchanged_v1_wire(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    method: str,
    body: object,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        calls: list[str] = []
        captured = s.runtime.status()
        source = CoreBoundary()

        async def attach(*args: Any) -> Any:
            calls.append("attach")
            return captured

        async def detach() -> Any:
            calls.append("detach")
            return captured

        async def monitor(request: object) -> Any:
            calls.append("monitor")
            return monitor_report()

        async def annotate(request: object) -> Any:
            calls.append("annotations")
            return annotation_receipt()

        async def read(request: object) -> Any:
            calls.append(suffix)
            return s.boundary.result

        monkeypatch.setattr(
            importlib.import_module("dutchmate_service.app"),
            "attach_basic_observation",
            attach,
        )
        monkeypatch.setattr(s.runtime, "detach", detach)
        monkeypatch.setattr(s.runtime, "monitor", monitor)
        monkeypatch.setattr(s.runtime, "annotate", annotate)
        monkeypatch.setattr(s.runtime, "read_record", read)
        monkeypatch.setattr(s.runtime, "read_page", read)
        monkeypatch.setattr(s.runtime, "start_follow", source.invoke)
        first = await call(s, 1, suffix, method, body)
        second = await call(s, 2, suffix, method, body)
        assert first.status == second.status == 200, "T016 missing: literal API2 reuse"
        assert first.payload == second.payload and first.headers == second.headers
        assert second.headers[b"cache-control"] == b"no-store"
        if suffix.endswith("follow"):
            assert len(source.calls) == 2 and all(
                sub.closed.is_set() for sub in source.subscriptions
            )
        elif not suffix.endswith("status"):
            assert len(calls) == 2


@pytest.mark.parametrize(
    "suffix,method,body", ALL_ROUTES, ids=[r[0] for r in ALL_ROUTES]
)
@pytest.mark.parametrize("wrong", ["GET", "POST", "HEAD", "OPTIONS", "PUT"])
async def test_literal_v2_methods_are_closed_before_body(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    method: str,
    body: object,
    wrong: str,
) -> None:
    # Parametrize actual wrong methods without skipping or silently sending a legal one.
    wrong = "DELETE" if wrong == method else wrong
    async with service(process_credential, monkeypatch) as s:
        path = f"/v2/{suffix}"
        response = await s.request(
            path,
            body,
            scope=s.scope(path, method=wrong),
            exchange=Exchange(forbid_receive=True),
        )
        _error(response, 405, "request", "method_not_allowed")
        assert not s.interact.calls


@pytest.mark.parametrize(
    "path",
    [
        "/v1/observation/interact",
        "/v3/observation/status",
        "/v2/observation/interact/",
        "/v2//observation/interact",
        "/v2/observation/Interact",
        "/V2/observation/interact",
        "/v2/observation/%69nteract",
        "/v2/observation/./interact",
        "/v2/interact",
        "/v2/docs",
        "/docs",
        "/openapi.json",
        "/v2/observation/console",
        "/v2/observation/tx",
        "/v2/observation/control",
        "/v2/observation/interact/cancel",
    ],
)
async def test_no_alias_negotiation_v1_interact_or_generic_command_surface(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        response = await s.request(path, BODY, exchange=Exchange(forbid_receive=True))
        _error(response, 404, "request", "route_not_found")
        assert b"location" not in response.headers and not s.interact.calls


@pytest.mark.parametrize(
    "suffix,method,body", ALL_ROUTES, ids=[r[0] for r in ALL_ROUTES]
)
async def test_v2_query_and_authentication_never_select_an_alternate_version(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    method: str,
    body: object,
) -> None:
    async with service(process_credential, monkeypatch) as s:
        path = f"/v2/{suffix}"
        scope = s.scope(path, method=method)
        scope["query_string"] = b"api_version=1"
        _error(
            await s.request(
                path, body, scope=scope, exchange=Exchange(forbid_receive=True)
            ),
            400,
            "request",
            "query_not_allowed",
        )
        scope["headers"] = [h for h in scope["headers"] if h[0] != b"authorization"]
        _error(
            await s.request(
                path, body, scope=scope, exchange=Exchange(forbid_receive=True)
            ),
            401,
            "request",
            "authentication_required",
        )
        assert not s.interact.calls


def ten_records(
    device: bool,
) -> tuple[tuple[model.EvidenceRecord, ...], list[dict[str, Any]]]:
    old, views = seven_records(device)
    provenance, provenance_wire = _provenance(device)
    tx = model.RecordedTxFacts(
        True, "acknowledged", 256, None, "backend_acceptance", ORIGIN, 105
    )
    observation = model.InteractObservation(
        model.SequenceRange(11, 11),
        model.InteractObservationOutcome.DETACHED,
        0,
        0,
        None,
        model.MonitorClockFacts(ORIGIN, 100, 1000000100, 106),
    )
    added = (
        model.InteractStartedEvidence(
            10,
            OPERATION,
            provenance,
            2,
            True,
            (b"\0\xff", b"FAIL"),
            1000,
            1024,
            1000,
            ORIGIN,
            bytes(range(256)),
        ),
        model.UartTxSettledEvidence(11, OPERATION, 10, tx),
        model.InteractEndedEvidence(
            12, OPERATION, 10, 11, tx, None, model.InteractOutcome.DETACHED, observation
        ),
    )
    tx_wire = {
        "submitted": True,
        "status": "acknowledged",
        "accepted_prefix_bytes": 256,
        "failure_code": None,
        "acknowledgement_scope": "backend_acceptance",
        "clock_origin_id": ORIGIN,
        "settled_at_ns": 105,
    }
    return (*old, *added), [
        *views,
        {
            "kind": "interact_started",
            "sequence": 10,
            "operation_id": OPERATION,
            "provenance": provenance_wire,
            "profile_version": 2,
            "authorization": {"uart_tx_enabled": True},
            "conditions_base64": ["AP8=", "RkFJTA=="],
            "timeout_ms": 1000,
            "max_rx_bytes": 1024,
            "write_timeout_ms": 1000,
            "clock_origin_id": ORIGIN,
            "payload_base64": base64.b64encode(bytes(range(256))).decode(),
        },
        {
            "kind": "uart_tx_settled",
            "sequence": 11,
            "operation_id": OPERATION,
            "start_sequence": 10,
            **tx_wire,
        },
        {
            "kind": "interact_ended",
            "sequence": 12,
            "operation_id": OPERATION,
            "start_sequence": 10,
            "tx_settled_sequence": 11,
            "tx": tx_wire,
            "tx_audit_failure": None,
            "outcome": "detached",
            "observation": {
                "window": {"start_inclusive": 11, "end_exclusive": 11},
                "outcome": "detached",
                "examined_rx_bytes": 0,
                "observer_loss_records": 0,
                "match": None,
                "clock": {
                    "origin_id": ORIGIN,
                    "started_at_ns": 100,
                    "deadline_at_ns": 1000000100,
                    "decided_at_ns": 106,
                },
            },
        },
    ]


@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.parametrize("index", range(10))
@pytest.mark.parametrize("kind", ["record", "page"])
async def test_api2_all_ten_exact_evidence_variants_keep_legacy_bytes_and_public_provenance(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
    index: int,
    kind: str,
) -> None:
    records, expected = ten_records(device)
    async with service(process_credential, monkeypatch) as s:
        page = _page(
            records=(records[index],), snapshot_end_exclusive=13, charged_bytes=4242
        )
        s.boundary.result = RunEvidencePage(s.boundary.result.run_id, SESSION, page)
        monkeypatch.setattr(s.runtime, f"read_{kind}", s.boundary.read)
        body = (
            {"session_id": SESSION.value, "sequence": records[index].sequence}
            if kind == "record"
            else PAGE
        )
        response = await s.request(f"/v2/evidence/{kind}", body)
        assert response.status == 200, "T016 missing: expanded API2 evidence union"
        assert response.payload == _json(
            _envelope(
                records=[expected[index]], snapshot_end_exclusive=13, charged_bytes=4242
            )
        )
        assert (
            response.headers[b"cache-control"] == b"no-store"
            and len(s.boundary.calls) == 1
        )
        if index < 7:
            old = await s.request(f"/v1/evidence/{kind}", body)
            assert old.payload == response.payload


@pytest.mark.parametrize("device", [False, True])
async def test_api2_follow_uses_same_five_frame_grammar_with_ten_unfiltered_variants(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
) -> None:
    records, views = ten_records(device)
    async with service(process_credential, monkeypatch) as s:
        source = CoreBoundary(
            captured=follow.FollowStart("run-é", SESSION, 3, _provenance(device)[0]),
            items=[
                follow.FollowBatch(None, records),
                follow.FollowEnd("source_ended", 13),
            ],
        )
        monkeypatch.setattr(s.runtime, "start_follow", source.invoke)
        response = await s.request(
            "/v2/observation/follow", {"session_id": SESSION.value}
        )
        frames(
            response,
            [
                started(device),
                *[{"type": "record", "record": v} for v in views],
                terminal(next_sequence=13, cutoff=13),
            ],
        )
        assert len(source.calls) == 1 and source.subscriptions[0].closed.is_set()


class EvidenceClient(Client):
    def __init__(self, session: str) -> None:
        super().__init__(body=_json({"session_id": session}))
        self.records: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def send(self, message: Message) -> None:
        await super().send(message)
        if message["type"] == "http.response.body" and message.get("body"):
            value = json.loads(message["body"])
            if value.get("type") == "record":
                self.records.put_nowait(value["record"])


@pytest.mark.parametrize("device", [False, True])
async def test_api2_follow_and_reads_observe_interact_without_new_reader_or_write_wait(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
) -> None:
    async with active_service(process_credential, monkeypatch, tmp_path, device) as (
        s,
        c,
    ):
        follower = EvidenceClient(c.journal.session_id.value)
        follow_task, _ = s.submit(follower, path="/v2/observation/follow")
        await reached(follower.publication, follow_task, follower)
        body = {**BODY, "session_id": c.journal.session_id.value}
        task, client = s.submit(Client(body=_json(body)))
        await reached(c.writer.entered, task, client)
        assert (await wait(follower.records.get()))["kind"] == "interact_started"
        await c.rx(b"PASS")
        rx_record = await wait(follower.records.get())
        assert (
            rx_record["kind"] == "rx_bytes"
            and base64.b64decode(rx_record["payload_base64"]) == b"PASS"
        )
        assert not task.done() and not follow_task.done()
        read = await s.request(
            "/v2/evidence/record",
            {
                "session_id": c.journal.session_id.value,
                "sequence": rx_record["sequence"],
            },
        )
        assert read.status == 200 and json.loads(read.payload)["page"]["records"] == [
            rx_record
        ]
        c.writer.allow.set()
        await wait(task)
        assert client.status == 200
        assert [(await wait(follower.records.get()))["kind"] for _ in range(2)] == [
            "uart_tx_settled",
            "interact_ended",
        ]
        follower.disconnected.set()
        await wait(asyncio.gather(follow_task, return_exceptions=True))
        assert c.fixture.connection.consumer_calls == c.fixture.backend.open_calls == 1
        assert (
            s.runtime.status().state.value == "active"
            and not c.recorder.closed.is_set()
        )


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("initial", [1, 2])
@pytest.mark.parametrize("device", [False, True])
async def test_attach_resolves_once_and_binds_guard_preparation_and_policy_to_that_value(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    version: int,
    initial: int,
    device: bool,
) -> None:
    core = core_helpers(monkeypatch)
    documents = importlib.import_module("tests.contract.test_interact_profile")
    path, journal_path = tmp_path / "profile.toml", tmp_path / "attached.db"
    old_document = documents._valid_profile()
    new_document = documents._v2_profile().replace(
        "uart_tx_enabled = false", "uart_tx_enabled = true"
    )
    path.write_text(old_document if initial == 1 else new_document, encoding="utf-8")
    original_resolve = resolve_profile
    resolutions: list[Any] = []
    constructions: list[dict[str, Any]] = []
    versions: list[int] = []
    selected = core.BACKEND_FIXTURE_FACTORIES[int(device)]()
    # These generic fixtures default to deliberately non-durable provenance.
    # The real composition/journal/public projection needs explicit test facts.
    selected.connection.descriptor = replace(
        selected.connection.descriptor,
        connection_provenance=model.PersistedConnectionProvenance(
            model.ConnectionProvenanceSnapshot(
                envelope_version=1,
                backend_kind="fixture/api-version",
                backend_schema_version=1,
                fields=(),
            )
        ),
    )

    def resolve(selected_path: Any) -> Any:
        result = original_resolve(selected_path)
        resolutions.append(result)
        # Edit immediately after the sole bounded read, before preparation.
        path.write_text(
            new_document if initial == 1 else old_document, encoding="utf-8"
        )
        return result

    def backend(*args: Any, **kwargs: Any) -> Any:
        constructions.append(kwargs)
        return selected.backend

    monkeypatch.setattr(observation_runtime, "resolve_profile", resolve)
    monkeypatch.setattr(observation_runtime, "BasicSerialBackend", backend)
    for number in (3, 4):
        original = getattr(sqlite_evidence.SqliteEvidenceJournal, f"create_v{number}")

        async def create(
            cls: Any,
            destination: Any,
            policy: Any,
            *,
            factory: Any = original,
            schema: int = number,
        ) -> Any:
            versions.append(schema)
            return await factory(destination, policy)

        monkeypatch.setattr(
            sqlite_evidence.SqliteEvidenceJournal,
            f"create_v{number}",
            classmethod(create),
        )
    async with service(process_credential, monkeypatch, stub=False) as s:
        response = await call(
            s,
            version,
            "observation/attach",
            "POST",
            {"profile_path": str(path), "journal_path": str(journal_path)},
        )
        assert len(resolutions) == 1, (
            "attach guard and preparation must share one immutable resolution"
        )
        if version == 1 and initial == 2:
            _error(response, 409, "request", "unsupported_api_version")
            assert not versions and not constructions and not journal_path.exists()
            assert selected.backend.open_calls == 0
        else:
            assert response.status == 200, "T016 missing: explicitly versioned attach"
            delivered = json.loads(response.payload)["runtime"]["profile"]
            assert delivered["format_version"] == initial
            assert delivered["policy"]["uart_tx_enabled"] is (initial == 2)
            assert s.runtime.status().profile is resolutions[0]
            assert versions == [3 if initial == 1 else 4]
            assert constructions == (
                [{}] if initial == 1 else [{"write_enabled": True}]
            )


@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize("terminal_run", [False, True], ids=["active", "terminal"])
@pytest.mark.parametrize(
    "suffix,method,template",
    [r for r in ROUTES if not r[0].endswith("attach")],
    ids=[r[0] for r in ROUTES if not r[0].endswith("attach")],
)
async def test_v1_known_v2_run_rejects_before_mutation_subscription_or_query(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
    terminal_run: bool,
    suffix: str,
    method: str,
    template: Any,
) -> None:
    async with active_service(process_credential, monkeypatch, tmp_path, device) as (
        s,
        c,
    ):
        if terminal_run:
            await s.runtime.detach()
        body = (
            None
            if template is None
            else {**template, "session_id": c.journal.session_id.value}
        )
        attempts: list[str] = []

        async def forbidden(*args: Any, **kwargs: Any) -> Any:
            attempts.append(suffix)
            raise AssertionError("API1 admitted a v2-only run")

        entry = {
            "observation/detach": "detach",
            "observation/monitor": "monitor",
            "observation/annotations": "annotate",
            "observation/follow": "start_follow",
            "evidence/record": "read_record",
            "evidence/page": "read_page",
        }.get(suffix)
        with monkeypatch.context() as patch:
            if entry is not None:
                patch.setattr(s.runtime, entry, forbidden)
            response = await call(s, 1, suffix, method, body)
        _error(response, 409, "request", "unsupported_api_version")
        assert not attempts and not c.writer.calls
        assert s.runtime.status().state.value == (
            "terminated" if terminal_run else "active"
        )
        if not terminal_run:
            assert [type(r) for r in await c.records()] == [
                model.SegmentStartedEvidence
            ]


@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize(
    "suffix,method,template",
    [
        r
        for r in ROUTES
        if r[0]
        not in {"observation/status", "observation/attach", "observation/detach"}
    ],
    ids=[
        r[0]
        for r in ROUTES
        if r[0]
        not in {"observation/status", "observation/attach", "observation/detach"}
    ],
)
async def test_v1_session_association_error_precedes_known_run_version_rejection(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
    suffix: str,
    method: str,
    template: Any,
) -> None:
    async with active_service(process_credential, monkeypatch, tmp_path, device) as (
        s,
        c,
    ):
        body = {**template, "session_id": "not-the-associated-session"}
        response = await call(s, 1, suffix, method, body)
        source = {
            "observation/monitor": "monitor",
            "observation/annotations": "annotation",
            "observation/follow": "follow",
        }.get(suffix, "evidence")
        _error(response, 409, source, "session_not_associated")
        assert not c.writer.calls


@pytest.mark.parametrize(
    "suffix,method,template",
    [
        r
        for r in ROUTES
        if r[0] in {"observation/status", "observation/detach", "evidence/page"}
    ],
    ids=["status", "detach", "page"],
)
async def test_stale_service_status_cannot_authorize_actual_v2_generation(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    suffix: str,
    method: str,
    template: Any,
) -> None:
    async with service(process_credential, monkeypatch, stub=False) as s:
        core = core_helpers(monkeypatch)
        await attach_legacy(s, core, tmp_path / "legacy.db")
        stale = s.runtime.status()
        await s.runtime.detach()
        async with core.runtime_case(
            tmp_path, monkeypatch, core.BACKEND_FIXTURE_FACTORIES[0], owner=s.runtime
        ) as c:
            actual_status = s.runtime.status
            samples = 0

            def stale_once() -> Any:
                nonlocal samples
                samples += 1
                return stale if samples == 1 else actual_status()

            with monkeypatch.context() as patch:
                patch.setattr(s.runtime, "status", stale_once)
                body = (
                    None
                    if template is None
                    else {**template, "session_id": c.journal.session_id.value}
                )
                response = await call(s, 1, suffix, method, body)
            _error(response, 409, "request", "unsupported_api_version")
            assert (
                actual_status().state.value == "active"
                and not c.recorder.closed.is_set()
            )


@pytest.mark.parametrize(
    "suffix",
    [
        "observation/detach",
        "evidence/page",
        "observation/monitor",
        "observation/annotations",
    ],
)
async def test_registered_but_uninvoked_v1_job_checks_replacement_generation_at_admission(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    suffix: str,
) -> None:
    # Delay only the already-existing concrete service owner coroutine before
    # its first instruction. This is a scheduling gate, not a new admission API.
    core = core_helpers(monkeypatch)
    async with service(process_credential, monkeypatch, stub=False) as s:
        journal = await attach_legacy(s, core, tmp_path / "legacy.db")
        template = next(r[2] for r in ROUTES if r[0] == suffix)
        body = (
            None
            if template is None
            else {**template, "session_id": journal.session_id.value}
        )
        client = Client(body=b"" if body is None else _json(body))
        with hold_service_owner() as (entered, release):
            task, client = s.submit(client, path=f"/v1/{suffix}")
            await reached(entered, task, client)
            await s.runtime.detach()
            replacement = tmp_path / "replacement"
            replacement.mkdir()
            async with core.runtime_case(
                replacement,
                monkeypatch,
                core.BACKEND_FIXTURE_FACTORIES[0],
                owner=s.runtime,
            ) as c:
                # Session-bearing requests retain their old association error;
                # sessionless detach must reject the newly captured v2 generation.
                release.set()
                await wait(task)
                if suffix.endswith("detach"):
                    _error(client, 409, "request", "unsupported_api_version")
                else:
                    source = {
                        "evidence/page": "evidence",
                        "observation/monitor": "monitor",
                        "observation/annotations": "annotation",
                    }[suffix]
                    _error(client, 409, source, "session_not_associated")
                assert s.runtime.status().state.value == "active"
                assert [type(r) for r in await c.records()] == [
                    model.SegmentStartedEvidence
                ]


# T021: adversarial delivery only; earlier T016 assertions remain unchanged.
@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize("stream", [False, True], ids=["page", "follow"])
async def test_t021_mixed_ten_kind_golden_keeps_all_bytes_and_follow_frames(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
    stream: bool,
) -> None:
    from test_follow_http import t015_padding, t015_provenance
    from test_service_http import _T011ConnectedExchange

    records, views = ten_records(device)
    views = json.loads(_json(views))  # Independent golden objects, without aliases.
    values = list(records)
    padding = t015_padding(8192)
    for index in (0, 3, 7):
        item = values[index]
        assert isinstance(
            item,
            (
                model.SegmentStartedEvidence,
                model.OperationStartedEvidence,
                model.InteractStartedEvidence,
            ),
        )
        values[index] = replace(
            item, provenance=t015_provenance(item.provenance, padding)
        )
        views[index]["provenance"]["connection_provenance"]["fields"] = [
            {"name": "padding", "value": padding}
        ]
    rx = values[1]
    assert isinstance(rx, model.RxBytesEvidence)
    values[1] = replace(rx, payload=bytes(range(256)))
    views[1]["payload_base64"] = base64.b64encode(bytes(range(256))).decode()
    async with service(process_credential, monkeypatch) as s:
        if stream:
            # Gap, heartbeat, records, started and terminal all retain011 grammar.
            marker = model.RetentionMarker(
                model.SequenceRange(0, 3), None, None, 3, 0, 99
            )
            gap = follow.FollowGap(model.SequenceRange(2, 3), marker)
            source = CoreBoundary(
                captured=follow.FollowStart(
                    "run-é", SESSION, 2, _provenance(device)[0]
                ),
                items=[
                    follow.FollowBatch(gap, tuple(values)),
                ],
            )

            class HeartbeatEnd(_T011ConnectedExchange):
                async def send(self, message: Message) -> None:
                    await super().send(message)
                    if message.get("body") == b'{"type":"heartbeat"}\n':
                        source.subscriptions[0].items.put_nowait(
                            follow.FollowEnd("source_ended", 13)
                        )

            monkeypatch.setattr(s.runtime, "start_follow", source.invoke)
            start_view = {**started(device), "start_sequence": 2}
            frames(
                await s.request(
                    "/v2/observation/follow",
                    {"session_id": SESSION.value},
                    exchange=HeartbeatEnd(body=_json({"session_id": SESSION.value})),
                ),
                [
                    start_view,
                    {
                        "type": "gap",
                        "missed_range": {"start_inclusive": 2, "end_exclusive": 3},
                        "retention_marker": {
                            "expired_range": {"start_inclusive": 0, "end_exclusive": 3},
                            "first_discarded_timestamp": None,
                            "last_discarded_timestamp": None,
                            "discarded_record_count": 3,
                            "discarded_rx_payload_byte_count": 0,
                            "discarded_charged_bytes": 99,
                        },
                    },
                    *[{"type": "record", "record": view} for view in views],
                    {"type": "heartbeat"},
                    terminal(next_sequence=13, cutoff=13),
                ],
            )
            assert len(source.calls) == 1 and source.subscriptions[0].closed.is_set()
        else:
            page = _page(
                records=tuple(values), snapshot_end_exclusive=13, charged_bytes=4242
            )
            s.boundary.result = RunEvidencePage(s.boundary.result.run_id, SESSION, page)
            monkeypatch.setattr(s.runtime, "read_page", s.boundary.read)
            response = await s.request("/v2/evidence/page", PAGE)
            assert response.status == 200 and response.payload == _json(
                _envelope(records=views, snapshot_end_exclusive=13, charged_bytes=4242)
            )
            assert (
                response.headers[b"cache-control"] == b"no-store"
                and len(s.boundary.calls) == 1
            )


@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize("size", [1048575, 1048576, 1048577])
@pytest.mark.parametrize("delivery", ["page", "record-frame", "started-frame"])
async def test_t021_v2_encoded_caps_count_escaped_provenance_without_trimming(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    device: bool,
    size: int,
    delivery: str,
) -> None:
    from test_follow_http import t015_padding, t015_provenance

    records, views = ten_records(device)
    item = records[7]
    assert isinstance(item, model.InteractStartedEvidence)
    view = json.loads(_json(views[7]))
    if delivery == "started-frame":
        expected = started(device)
        provenance_view = expected["provenance"]
        provenance = _provenance(device)[0]
    else:
        expected = (
            _envelope(records=[view], snapshot_end_exclusive=13, charged_bytes=1)
            if delivery == "page"
            else {"type": "record", "record": view}
        )
        provenance_view = view["provenance"]
        provenance = item.provenance
    provenance_view["connection_provenance"]["fields"] = [
        {"name": "padding", "value": ""}
    ]
    padding = t015_padding(size - len(_json(expected)))
    provenance_view["connection_provenance"]["fields"][0]["value"] = padding
    assert len(_json(expected)) == size and len(padding) < size // 2
    async with service(process_credential, monkeypatch) as s:
        if delivery == "page":
            page = _page(
                records=(
                    replace(item, provenance=t015_provenance(provenance, padding)),
                ),
                snapshot_end_exclusive=13,
                charged_bytes=1,
            )
            s.boundary.result = RunEvidencePage(s.boundary.result.run_id, SESSION, page)
            monkeypatch.setattr(s.runtime, "read_page", s.boundary.read)
            response = await s.request("/v2/evidence/page", PAGE)
            if size <= 1048576:
                assert response.status == 200 and response.payload == _json(expected)
            else:
                _error(response, 413, "evidence", "delivery_too_large")
            assert len(s.boundary.calls) == 1
        else:
            if delivery == "started-frame":
                source = CoreBoundary(
                    captured=follow.FollowStart(
                        "run-é", SESSION, 3, t015_provenance(provenance, padding)
                    )
                )
                expected_frames = [expected, terminal()]
            else:
                source = CoreBoundary(
                    captured=follow.FollowStart(
                        "run-é", SESSION, 3, _provenance(device)[0]
                    ),
                    items=[
                        follow.FollowBatch(
                            None,
                            (
                                *records[:7],
                                replace(
                                    item,
                                    provenance=t015_provenance(provenance, padding),
                                ),
                            ),
                        ),
                        follow.FollowEnd("source_ended", 11),
                    ],
                )
                expected_frames = [
                    started(device),
                    *[{"type": "record", "record": v} for v in views[:7]],
                ]
                expected_frames += (
                    [expected, terminal(next_sequence=11, cutoff=11)]
                    if size <= 1048576
                    else [terminal("delivery_too_large", 10, None)]
                )
            monkeypatch.setattr(s.runtime, "start_follow", source.invoke)
            response = await s.request(
                "/v2/observation/follow", {"session_id": SESSION.value}
            )
            if delivery == "started-frame" and size > 1048576:
                _error(response, 413, "follow", "delivery_too_large")
            else:
                frames(response, expected_frames)
            assert len(source.calls) == 1 and source.subscriptions[0].closed.is_set()
            assert source.subscriptions[0].pulls == (
                0
                if delivery == "started-frame" and size > 1048576
                else 1
                if size > 1048576
                else 1
                if delivery == "started-frame"
                else 2
            )


@pytest.mark.parametrize("suffix,method,body", [r for r in ROUTES if r[2] is not None])
@pytest.mark.parametrize(
    "fault", ["escaped-duplicate", "unknown", "boolean", "overflow"]
)
async def test_t021_v2_shared_request_validators_reject_wire_ambiguity_before_admission(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    method: str,
    body: dict[str, Any],
    fault: str,
) -> None:
    key = next(iter(body))
    raw = _json(body)
    if fault == "escaped-duplicate":
        encoded_key = f'"\\u{ord(key[0]):04x}{key[1:]}"'.encode()
        raw = raw[:-1] + b"," + encoded_key + b":" + _json(body[key]) + b"}"
    elif fault == "unknown":
        raw = raw[:-1] + b',"wire_received":true}'
    else:
        raw = raw.replace(
            _json(body[key]), b"true" if fault == "boolean" else b"1e9999", 1
        )
    async with service(process_credential, monkeypatch) as s:
        response = await s.request(
            f"/v2/{suffix}",
            body,
            raw=raw,
            scope=s.scope(f"/v2/{suffix}", method=method),
        )
        _error(response, 422, "request", "invalid_request")
        assert not s.boundary.calls and not s.interact.calls


@pytest.mark.parametrize("device", [False, True])
async def test_t021_registered_v1_record_read_rejects_replacement_session_before_query(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
) -> None:
    core = core_helpers(monkeypatch)
    async with service(process_credential, monkeypatch, stub=False) as s:
        journal = await attach_legacy(s, core, tmp_path / "legacy.db")
        client = Client(
            body=_json({"session_id": journal.session_id.value, "sequence": 0})
        )
        with hold_service_owner() as (entered, release):
            task, client = s.submit(client, path="/v1/evidence/record")
            await reached(entered, task, client)
            await s.runtime.detach()
            replacement = tmp_path / "replacement"
            replacement.mkdir()
            async with core.runtime_case(
                replacement,
                monkeypatch,
                core.BACKEND_FIXTURE_FACTORIES[int(device)],
                owner=s.runtime,
            ) as c:
                release.set()
                await wait(task)
                _error(client, 409, "evidence", "session_not_associated")
                assert s.runtime.status().state.value == "active"
                assert [type(r) for r in await c.records()] == [
                    model.SegmentStartedEvidence
                ]


@pytest.mark.parametrize("device", [False, True])
async def test_t021_same_version_profile_edit_cannot_upgrade_captured_tx_permission(
    process_credential: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    device: bool,
) -> None:
    core = core_helpers(monkeypatch)
    documents = importlib.import_module("tests.contract.test_interact_profile")
    path = tmp_path / "profile.toml"
    path.write_text(documents._v2_profile())
    selected = core.BACKEND_FIXTURE_FACTORIES[int(device)]()
    selected.connection.descriptor = replace(
        selected.connection.descriptor,
        connection_provenance=_provenance(device)[0].connection_provenance,
    )
    resolutions: list[Any] = []

    def resolve(selected_path: Any) -> Any:
        value = resolve_profile(selected_path)
        resolutions.append(value)
        path.write_text(
            documents._v2_profile().replace(
                "uart_tx_enabled = false", "uart_tx_enabled = true"
            )
        )
        return value

    monkeypatch.setattr(observation_runtime, "resolve_profile", resolve)
    monkeypatch.setattr(
        observation_runtime,
        "BasicSerialBackend",
        lambda *args, **kwargs: selected.backend,
    )
    async with service(process_credential, monkeypatch, stub=False) as s:
        response = await call(
            s,
            2,
            "observation/attach",
            "POST",
            {"profile_path": str(path), "journal_path": str(tmp_path / "journal.db")},
        )
        assert response.status == 200 and len(resolutions) == 1
        assert (
            json.loads(response.payload)["runtime"]["profile"]["policy"][
                "uart_tx_enabled"
            ]
            is False
        )
        assert s.runtime.status().profile is resolutions[0]
        assert s.runtime.status().state.value == "active"
        session = s.runtime.status().session_id
        assert session is not None
        _error(
            await s.request(
                "/v2/observation/interact", {**BODY, "session_id": session.value}
            ),
            409,
            "interact",
            "policy_denied",
        )
        assert selected.backend.open_calls == 1
