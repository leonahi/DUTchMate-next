"""009 Monitor CLI contracts and joined T017 active-MVP acceptance.

T015 wire cases use the existing isolated credential/HTTPX transport fixtures
and independent golden data, without reproducing matching or journal policy.
T017 additionally joins the actual CLI, authenticated app, runtime and v2 journal.
Installed-process acceptance belongs to its later task.
"""

import asyncio
import base64
import importlib
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
import typer

# Follow the established CLI helper import convention: these test modules are
# unpackaged and intentionally outside mypy_path; no source-path/config edit.
_commands = importlib.import_module("test_cli_commands")
_evidence = importlib.import_module("test_cli_evidence")
_block_preparation = _commands._block_preparation
_grammar_rejected = _commands._grammar_rejected
_runner = _commands._runner
_PAGE_ARGS = _evidence._PAGE_ARGS
_PRIVATE = _evidence._PRIVATE
_RECORD_ARGS = _evidence._RECORD_ARGS
_TOKEN = _evidence._TOKEN
Delivery = _evidence.Delivery
_api = _evidence._api
_at = _evidence._at
_command = _evidence._command
_full_report = _evidence._full_report
_helpers = _evidence._helpers
_json = _evidence._json
_local = _evidence._local
_page_report = _evidence._report

_LIMIT = 1048576
_MAX = 9223372036854775807
_SESSION = "session-é"
_OPERATION = "12345678-1234-4234-8234-123456789abc"
_ORIGIN = "abcdefab-1234-4234-8234-123456789abc"
_OUTCOMES = (
    "matched",
    "timeout",
    "byte_limit",
    "disconnected",
    "detached",
    "timestamp_origin_reset",
    "recording_failure",
    "transport_failure",
    "service_stopping",
)
_BODY = {
    "session_id": _SESSION,
    "condition_base64": "AP9B",
    "timeout_ms": 1000,
    "max_rx_bytes": 65536,
}
_ARGS = [
    "--port",
    "8765",
    "monitor",
    "--session",
    _SESSION,
    "--condition-base64",
    "AP9B",
    "--timeout-ms",
    "1000",
    "--max-rx-bytes",
    "65536",
]
_JOURNAL_CODES = (
    "invalid_input",
    "session_mismatch",
    "journal_missing",
    "busy",
    "closed",
    "journal_exists",
    "incompatible_application",
    "incompatible_schema_version",
    "incompatible_record_version",
    "incompatible_provenance_envelope_version",
    "corrupt_journal",
    "invariant_violation",
    "capacity",
    "capacity/database_over_ceiling",
    "capacity/physical_ceiling_unavailable",
    "capacity/sequence_exhausted",
    "capacity/counter_exhausted",
    "read_only",
    "permission_denied",
    "io_failure",
)


@asynccontextmanager
async def _t017_active_service(
    tmp_path: Path,
    account_home: Path,
    patch: pytest.MonkeyPatch,
    backend_index: int,
    family_index: int,
) -> AsyncIterator[tuple[Any, Any, list[str]]]:
    helper = _evidence._t014_service_helpers(patch)
    helper._t014_core_helpers(patch)
    core = importlib.import_module("tests.integration.test_monitor")
    module = helper._t009_module()
    config = helper._CONFIGS[family_index]
    created, _ = helper._t009_runtime_spy(module, patch)
    owner = helper.PrivateBootstrap.acquire(config)
    lifespan = None
    try:
        owner.mark_unconfirmed()
        owner.publish_credential()
        token = (
            account_home / ".local/state/dutchmate/service/credential"
        ).read_bytes()[:-1]
        app = module.create_app(
            config, _launch_context=module._LaunchContext(config, owner)
        )
        lifespan = helper.AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        assert len(created) == 1
        # Transfer test infrastructure to the runtime actually owned by this app.
        async with core._live(
            tmp_path,
            patch,
            core.BACKEND_FIXTURE_FACTORIES[backend_index],
            runtime_support=True,
            runtime=created[0],
        ) as case:
            service = helper.ActiveEvidenceService(
                app, config, token, case, tmp_path / "monitor.sqlite3"
            )
            for name in ("retrieve", "resolve_record"):
                original = getattr(case.journal, name)

                async def observed(
                    value: object, *, call: Any = original, kind: str = name
                ) -> Any:
                    assert service.serving.get(), "CLI evidence must pass through HTTP"
                    service.queries.append(kind)
                    return await call(value)

                patch.setattr(case.journal, name, observed)

            sqlite = core.sqlite3
            original_connect = sqlite.connect
            terminal_connections: list[str] = []

            def connect(database: str, *args: Any, **kwargs: Any) -> Any:
                assert case.writer_closed.is_set(), (
                    "active reads opened another database"
                )
                assert kwargs.get("uri") is True
                assert database.endswith("?mode=ro&cache=private")
                terminal_connections.append(database)
                return original_connect(database, *args, **kwargs)

            patch.setattr(sqlite, "connect", connect)
            yield service, case, terminal_connections
    finally:
        try:
            if lifespan is not None:
                await lifespan.finish()
        finally:
            owner.invalidate_credential()
            if created:
                status = created[0].status()
                owner.confirm_cleanup(
                    owner_settled=status.owner_settled,
                    physical_release_confirmed=status.physical_release_confirmed,
                    recorder_close_confirmed=status.recorder_close_confirmed,
                )
            owner.release()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("family_index", [0, 1], ids=["ipv4", "ipv6"])
async def test_t017_joined_active_monitor_and_active_terminal_marker_retrieval(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend_index: int,
    family_index: int,
) -> None:
    async with _t017_active_service(
        tmp_path, account_home, monkeypatch, backend_index, family_index
    ) as (service, case, terminal_connections):
        bridge = _evidence.ActiveBridge(service, monkeypatch)
        status = await bridge.console(capsys, "status")
        session = status["runtime"]["session_id"]
        assert session == case.journal.session_id.value
        assert status["runtime"]["run_id"] == case.active.run_id.value
        before = b"\0\xffPASS before admission"
        await case.emit(before, 11)
        delivery = asyncio.create_task(
            bridge.console(
                capsys,
                "monitor",
                "--session",
                session,
                "--condition-base64",
                base64.b64encode(b"\0\xffPASS").decode(),
                "--timeout-ms",
                "1000",
                "--max-rx-bytes",
                "1024",
            )
        )
        try:
            await asyncio.wait_for(case.clock.wait_started.wait(), timeout=3)
            first, second = b"noise\0\xffP", b"ASStrailing\x80"
            await case.emit(first, 17)
            await case.emit(second, 901)
            report = await asyncio.wait_for(asyncio.shield(delivery), timeout=3)
        finally:
            if not delivery.done():
                await case.runtime.detach()
            await asyncio.gather(delivery, return_exceptions=True)
        assert report["session_id"] == session
        assert report["run_id"] == status["runtime"]["run_id"]
        assert report["outcome"] == "matched"
        assert report["durability"] == "complete" and report["end_failure"] is None
        assert report["examined_rx_bytes"] == 11
        assert report["observer_loss_records"] == 0
        assert report["started_record"] == {"session_id": session, "sequence": 2}
        assert report["ended_record"] == {"session_id": session, "sequence": 5}
        assert report["window"] == {"start_inclusive": 3, "end_exclusive": 5}
        assert report["match"] == {
            "start": {"sequence": 3, "byte_offset": 5},
            "end": {"sequence": 4, "byte_offset_exclusive": 3},
        }
        assert report["clock"] == {
            "origin_id": case.clock.origin_id,
            "started_at_ns": 100,
            "deadline_at_ns": 1000000100,
            "decided_at_ns": 100,
        }
        after = b"ambient after match\0\xff"
        await case.emit(after, 1001)
        page = await bridge.page(capsys)
        records = page["page"]["records"]
        assert page["page"]["outcome"] == "complete"
        assert [item["sequence"] for item in records] == list(range(7))
        assert [
            base64.b64decode(item["payload_base64"], validate=True)
            for item in records
            if item["kind"] == "rx_bytes"
        ] == [before, first, second, after]
        assert report["provenance"] == records[0]["provenance"]
        start, end = records[2], records[5]
        assert start["kind"] == "operation_started"
        assert start["condition_base64"] == base64.b64encode(b"\0\xffPASS").decode()
        assert start["operation_id"] == end["operation_id"] == report["operation_id"]
        assert start["provenance"] == report["provenance"]
        assert end["kind"] == "operation_ended" and end["start_sequence"] == 2
        for key in (
            "window",
            "outcome",
            "examined_rx_bytes",
            "observer_loss_records",
            "match",
            "clock",
        ):
            assert end[key] == report[key]
        for marker in (start, end):
            active = await bridge.console(
                capsys,
                "evidence record",
                "--session",
                session,
                "--sequence",
                str(marker["sequence"]),
            )
            assert active["page"]["records"] == [marker]
        assert service.queries == ["retrieve", "resolve_record", "resolve_record"]
        assert terminal_connections == [] and not case.terminal_opened.is_set()
        assert case.fixture.connection.consumer_calls == 1
        assert case.fixture.connection.close_calls == 0

        await bridge.console(capsys, "detach")
        assert case.writer_closed.is_set()
        assert case.runtime.status().owner_settled
        for marker in (start, end):
            terminal = await bridge.console(
                capsys,
                "evidence record",
                "--session",
                session,
                "--sequence",
                str(marker["sequence"]),
            )
            assert terminal["run_id"] == report["run_id"]
            assert terminal["page"]["records"] == [marker]
        assert len(terminal_connections) == 2 and case.terminal_opened.is_set()
        assert service.queries == ["retrieve", "resolve_record", "resolve_record"]
        assert case.fixture.connection.consumer_calls == 1
        assert case.fixture.connection.close_calls == 1
        assert case.runtime.evidence_read_cleanup_confirmed


def _report(
    outcome: str = "matched",
    *,
    device: bool = False,
    failure: dict[str, str] | None = None,
) -> dict[str, Any]:
    examined = 5 if outcome in {"matched", "byte_limit"} else 0
    return {
        "run_id": "run-é",
        "session_id": _SESSION,
        "operation_id": _OPERATION,
        "provenance": _full_report(device)["page"]["records"][0]["provenance"],
        "outcome": outcome,
        "started_record": {"session_id": _SESSION, "sequence": 3},
        "ended_record": {"session_id": _SESSION, "sequence": 8}
        if failure is None
        else None,
        "window": {"start_inclusive": 4, "end_exclusive": 6 if examined else 4},
        "examined_rx_bytes": examined,
        "observer_loss_records": 0,
        "match": {
            "start": {"sequence": 4, "byte_offset": 1},
            "end": {"sequence": 5, "byte_offset_exclusive": 2},
        }
        if outcome == "matched"
        else None,
        "clock": {
            "origin_id": _ORIGIN,
            "started_at_ns": 100,
            "deadline_at_ns": 1000000100,
            "decided_at_ns": 1000000100 if outcome == "timeout" else 102,
        },
        "durability": "complete" if failure is None else "end_unconfirmed",
        "end_failure": failure,
    }


def _markers(outcome: str = "matched", *, device: bool = False) -> list[dict[str, Any]]:
    report = _report(outcome, device=device)
    return [
        {
            "kind": "operation_started",
            "sequence": 3,
            "operation_id": _OPERATION,
            "operation_kind": "monitor",
            "provenance": report["provenance"],
            "timeout_ms": 1000,
            "max_rx_bytes": 65536,
            "clock_origin_id": _ORIGIN,
            "condition_base64": "AP9B",
        },
        {
            "kind": "operation_ended",
            "sequence": 8,
            "operation_id": _OPERATION,
            "operation_kind": "monitor",
            "start_sequence": 3,
            "window": report["window"],
            "outcome": outcome,
            "examined_rx_bytes": report["examined_rx_bytes"],
            "observer_loss_records": 0,
            "match": report["match"],
            "clock": report["clock"],
        },
    ]


def _delivery(
    account_home: Path,
    patch: pytest.MonkeyPatch,
    report: dict[str, Any] | None = None,
    **options: Any,
) -> Any:
    return Delivery(
        account_home,
        patch,
        body=_json(_report() if report is None else report),
        **options,
    )


def _reverse_objects(value: Any) -> Any:
    if type(value) is dict:
        return {
            key: _reverse_objects(member)
            for key, member in reversed(list(value.items()))
        }
    if type(value) is list:
        return [_reverse_objects(member) for member in value]
    return value


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--help"],
        ["monitor", "--help"],
        ["--host", _PRIVATE, "--port", "0", "monitor", "--help"],
    ],
)
@pytest.mark.parametrize("unsupported", [False, True])
def test_root_and_monitor_help_are_static_and_describe_only_required_grammar(
    args: list[str],
    unsupported: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    if unsupported:
        monkeypatch.setattr(sys, "platform", "win32")
    assert _command(api, args) == 0
    stdout, stderr = capsys.readouterr()
    assert stdout and not stderr and "--help" in stdout
    if "monitor" in args:
        for option in (
            "--session",
            "--condition-base64",
            "--timeout-ms",
            "--max-rx-bytes",
        ):
            assert option in stdout
        for option in (
            "--follow",
            "--text",
            "--regex",
            "--file",
            "--stdin",
            "--run-id",
            "--journal",
            "--profile",
            "--token",
            "--output",
        ):
            assert option not in stdout
    else:
        assert all(
            command in stdout
            for command in ("monitor", "attach", "status", "detach", "evidence")
        )
    assert _PRIVATE not in stdout and attempts == []


_BAD_ARGS: list[list[str]] = [
    _ARGS[2:],
    ["--port", "8765", "monitor"],
    [*_ARGS, _PRIVATE],
    ["--port", "8765", "Monitor", *_ARGS[3:]],
]
for option in ("--session", "--condition-base64", "--timeout-ms", "--max-rx-bytes"):
    index = _ARGS.index(option)
    _BAD_ARGS.append(_ARGS[:index] + _ARGS[index + 2 :])
    _BAD_ARGS.append([*_ARGS, option])
for option in (
    "--follow",
    "--text",
    "--regex",
    "--stdin",
    "--file",
    "--output",
    "--run-id",
    "--path",
    "--database",
    "--journal",
    "--profile",
    "--token",
    "--start",
    "--clock",
):
    _BAD_ARGS.append([*_ARGS, option, _PRIVATE])
for option, values in (
    ("--session", ("", "x\0y", "x" * 257, "é" * 129)),
    (
        "--condition-base64",
        (
            "",
            "AA",
            "AB==",
            "AA===",
            "AA==\n",
            "_w==",
            "-w==",
            "é",
            base64.b64encode(b"x" * 257).decode("ascii"),
        ),
    ),
    ("--timeout-ms", ("0", "-1", "4001", "true", "false", "1.0", "1e0", _PRIVATE)),
    ("--max-rx-bytes", ("0", "-1", "1048577", "true", "false", "1.0", "1e0", _PRIVATE)),
):
    for value in values:
        args = list(_ARGS)
        args[args.index(option) + 1] = value
        _BAD_ARGS.append(args)
for prefix in (
    ["--port", "0"],
    ["--port", "65536"],
    ["--host", "localhost", "--port", "8765"],
    ["--host", "::ffff:127.0.0.1", "--port", "8765"],
):
    _BAD_ARGS.append([*prefix, *_ARGS[2:]])
_BAD_ARGS.append([*_ARGS, "--port", "80"])


@pytest.mark.parametrize("args", _BAD_ARGS)
def test_invalid_grammar_and_inputs_are_private_before_account_platform_or_network(
    args: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    assert _command(api, args) == 2
    _local(capsys.readouterr(), "invalid_arguments")
    _grammar_rejected(_runner(api, args))
    assert attempts == [] and _PRIVATE not in caplog.text


@pytest.mark.parametrize(
    "session,condition,timeout,maximum",
    [
        (" ", "AA==", 1, 1),
        ("x" * 256, "AP9B", 4000, 1048576),
        ("é" * 128, "AP9B", 1000, 65536),
        ("e\u0301", "AP9B", 1, 1048576),
        (" /opaque/id ", "AP9B", 4000, 1),
    ],
)
@pytest.mark.parametrize("host,port", [("127.0.0.1", 1), ("::1", 65535)])
def test_valid_edges_send_one_exact_request_with_no_client_core_policy(
    session: str,
    condition: str,
    timeout: int,
    maximum: int,
    host: str,
    port: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A zero-byte examined detached report is valid for every request byte bound.
    report = _report("detached")
    delivery = _delivery(account_home, monkeypatch, report)
    args = [
        "--host",
        host,
        "--port",
        str(port),
        "monitor",
        "--session",
        session,
        "--condition-base64",
        condition,
        "--timeout-ms",
        str(timeout),
        "--max-rx-bytes",
        str(maximum),
    ]
    assert delivery.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    expected = {
        "session_id": session,
        "condition_base64": condition,
        "timeout_ms": timeout,
        "max_rx_bytes": maximum,
    }
    delivery.one_request("/v1/observation/monitor", expected, host=host, port=port)
    assert delivery.wire.requests[0].content == _json(expected)


def test_condition_all_256_binary_bytes_and_repeat_options_preserve_existing_last_value_rule(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    condition = base64.b64encode(bytes(range(256))).decode("ascii")
    delivery = _delivery(account_home, monkeypatch)
    args = [
        *_ARGS,
        "--session",
        "second-session",
        "--condition-base64",
        condition,
        "--timeout-ms",
        "4000",
        "--max-rx-bytes",
        "1048576",
    ]
    assert delivery.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((_json(_report()) + b"\n").decode(), "")
    delivery.one_request(
        "/v1/observation/monitor",
        {
            "session_id": "second-session",
            "condition_base64": condition,
            "timeout_ms": 4000,
            "max_rx_bytes": 1048576,
        },
    )


@pytest.mark.parametrize("outcome", _OUTCOMES)
@pytest.mark.parametrize(
    "device", [False, True], ids=["Basic-shaped", "Enhanced-shaped"]
)
@pytest.mark.parametrize("unconfirmed", [False, True])
def test_all_outcomes_and_both_durability_states_are_exit_zero_canonical_facts(
    outcome: str,
    device: bool,
    unconfirmed: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report(
        outcome,
        device=device,
        failure={"source": "journal", "code": "io_failure"} if unconfirmed else None,
    )
    delivery = Delivery(account_home, monkeypatch, body=_json(_reverse_objects(report)))
    assert delivery.invoke(_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    delivery.one_request("/v1/observation/monitor", _BODY)


@pytest.mark.parametrize(
    "source,code",
    [("journal", code) for code in _JOURNAL_CODES] + [("service", "internal_failure")],
)
def test_all_embedded_end_errors_are_facts_not_exit_four_or_retries(
    source: str,
    code: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report(failure={"source": source, "code": code})
    delivery = _delivery(account_home, monkeypatch, report)
    assert delivery.invoke(_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    delivery.one_request("/v1/observation/monitor", _BODY)


_MONITOR_ERRORS = [
    (404, "no_associated_session"),
    (409, "session_not_associated"),
    (409, "not_active"),
    (503, "monitor_unavailable"),
    (409, "capability_unavailable"),
    (409, "busy"),
    (422, "evidence_policy_incompatible"),
    (413, "delivery_too_large"),
]
_REMOTE_ERRORS = [(status, "monitor", code) for status, code in _MONITOR_ERRORS]
_REMOTE_ERRORS += [
    (
        {
            "invalid_input": 422,
            "session_mismatch": 409,
            "journal_missing": 404,
            "busy": 503,
            "closed": 409,
        }.get(code, 500),
        "journal",
        code,
    )
    for code in _JOURNAL_CODES
]
_REMOTE_ERRORS += _helpers("test_cli_transport")._REMOTE_ERRORS


@pytest.mark.parametrize("status,source,code", _REMOTE_ERRORS)
def test_exact_remote_errors_exit_four_without_local_receipts_or_input_leaks(
    status: int,
    source: str,
    code: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    report = {"error": {"source": source, "code": code}}
    delivery = _delivery(account_home, monkeypatch, report, status=status)
    caplog.set_level(logging.DEBUG)
    assert delivery.invoke(_ARGS) == 4
    assert tuple(capsys.readouterr()) == ("", (_json(report) + b"\n").decode())
    assert _PRIVATE not in caplog.text and _TOKEN not in caplog.text
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed


_CLOSED_PATHS = [
    (),
    ("provenance",),
    ("provenance", "backend_observation_timestamp_domain"),
    ("provenance", "loss_observability"),
    ("provenance", "connection_provenance"),
    ("provenance", "connection_provenance", "fields", 0),
    ("started_record",),
    ("ended_record",),
    ("window",),
    ("match",),
    ("match", "start"),
    ("match", "end"),
    ("clock",),
]


@pytest.mark.parametrize("path", _CLOSED_PATHS)
@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_report_and_all_nested_variants_are_closed_and_never_default_fields(
    path: tuple[Any, ...],
    mutation: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report(device=True)
    view = _at(report, path)
    if mutation == "extra":
        view["private"] = _PRIVATE
    else:
        del view[next(iter(view))]
    delivery = _delivery(account_home, monkeypatch, report)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


_BAD_FIELDS: list[tuple[tuple[Any, ...], Any]] = [
    (("run_id",), ""),
    (("session_id",), None),
    (("operation_id",), _OPERATION.upper()),
    (("operation_id",), "opaque-id"),
    (("outcome",), "success"),
    (("started_record",), None),
    (("started_record", "sequence"), True),
    (("started_record", "sequence"), -1),
    (("ended_record", "sequence"), _MAX),
    (("ended_record",), None),
    (("window", "start_inclusive"), -1),
    (("window", "end_exclusive"), True),
    (("examined_rx_bytes",), True),
    (("examined_rx_bytes",), 1048577),
    (("observer_loss_records",), -1),
    (("observer_loss_records",), _MAX + 1),
    (("match", "start", "sequence"), True),
    (("match", "start", "byte_offset"), -1),
    (("match", "end", "byte_offset_exclusive"), 0),
    (("clock", "origin_id"), "host-process"),
    (("clock", "started_at_ns"), 1.0),
    (("clock", "deadline_at_ns"), _MAX + 1),
    (("clock", "decided_at_ns"), -1),
    (("durability",), "durable"),
    (("end_failure",), {"source": "journal", "code": "io_failure"}),
    (("match",), None),
]


@pytest.mark.parametrize("path,bad", _BAD_FIELDS)
def test_wire_types_enums_bounds_and_nullability_are_strict_without_core_reconstruction(
    path: tuple[Any, ...],
    bad: Any,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report()
    _at(report, path[:-1])[path[-1]] = bad
    delivery = _delivery(account_home, monkeypatch, report)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "failure",
    [
        None,
        {},
        {"source": "journal", "code": "unknown"},
        {"source": "service", "code": "io_failure"},
        {"source": "journal", "code": "io_failure", "detail": _PRIVATE},
    ],
)
def test_end_unconfirmed_requires_only_declared_closed_failure_variant(
    failure: Any,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report(failure={"source": "journal", "code": "io_failure"})
    report["end_failure"] = failure
    delivery = _delivery(account_home, monkeypatch, report)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")


@pytest.mark.parametrize("outcome", _OUTCOMES)
@pytest.mark.parametrize(
    "device", [False, True], ids=["Basic-shaped", "Enhanced-shaped"]
)
@pytest.mark.parametrize("args", [_RECORD_ARGS, _PAGE_ARGS], ids=["record", "page"])
def test_evidence_commands_accept_only_the_two_additive_marker_shapes(
    outcome: str,
    device: bool,
    args: list[str],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _page_report(
        records=_markers(outcome, device=device), snapshot_end_exclusive=9
    )
    delivery = Delivery(account_home, monkeypatch, body=_json(_reverse_objects(report)))
    assert delivery.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 1
    assert delivery.wire.requests[0].url.path in {
        "/v1/evidence/record",
        "/v1/evidence/page",
    }
    assert delivery.reads == ["credential"] and delivery.imports == []


@pytest.mark.parametrize(
    "device", [False, True], ids=["Basic-shaped", "Enhanced-shaped"]
)
def test_old_four_and_new_two_evidence_variants_share_one_unchanged_page(
    device: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _full_report(device)
    records = report["page"]["records"]
    start, end = _markers("timeout", device=device)
    start["sequence"], end["sequence"], end["start_sequence"] = 11, 12, 11
    end["window"] = {"start_inclusive": 12, "end_exclusive": 12}
    records.extend((start, end))
    report["page"]["snapshot_end_exclusive"] = 13
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 1


_MARKER_PATHS = [
    ("page", "records", 0),
    ("page", "records", 0, "provenance"),
    ("page", "records", 1),
    ("page", "records", 1, "window"),
    ("page", "records", 1, "match"),
    ("page", "records", 1, "match", "start"),
    ("page", "records", 1, "match", "end"),
    ("page", "records", 1, "clock"),
]


@pytest.mark.parametrize("path", _MARKER_PATHS)
@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_marker_objects_are_closed_with_no_extra_record_version_or_defaults(
    path: tuple[Any, ...],
    mutation: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _page_report(records=_markers(), snapshot_end_exclusive=9)
    view = _at(report, path)
    if mutation == "extra":
        view["record_version"] = 2
    else:
        del view[next(iter(view))]
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "index,key,bad",
    [
        (0, "operation_kind", "interact"),
        (0, "operation_id", _OPERATION.upper()),
        (0, "condition_base64", ""),
        (0, "condition_base64", "AB=="),
        (0, "condition_base64", "_w=="),
        (0, "timeout_ms", True),
        (0, "timeout_ms", 4001),
        (0, "max_rx_bytes", 0),
        (1, "outcome", "success"),
        (1, "start_sequence", True),
        (1, "observer_loss_records", -1),
        (1, "examined_rx_bytes", 1048577),
        (1, "match", None),
    ],
)
def test_marker_variants_reject_bad_enums_binary_types_and_nullability(
    index: int,
    key: str,
    bad: Any,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _page_report(records=_markers(), snapshot_end_exclusive=9)
    report["page"]["records"][index][key] = bad
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "status,body",
    [
        (200, {"error": {"source": "monitor", "code": "busy"}}),
        (409, {"error": {"source": "monitor", "code": "monitor_unavailable"}}),
        (500, {"error": {"source": "monitor", "code": _PRIVATE}}),
        (409, {"error": {"source": "monitor", "code": "busy", "detail": _PRIVATE}}),
        (
            409,
            {
                "error": {"source": "monitor", "code": "busy"},
                "request_outcome": "unknown",
            },
        ),
        (409, {"error": {"source": "journal", "code": "busy"}}),
    ],
)
def test_wrong_remote_status_source_code_or_extra_fields_are_private_invalid_response(
    status: int,
    body: dict[str, Any],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(account_home, monkeypatch, body, status=status)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize("status,code", _MONITOR_ERRORS)
def test_new_monitor_errors_do_not_weaken_original_status_error_validator(
    status: int,
    code: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(
        account_home,
        monkeypatch,
        {"error": {"source": "monitor", "code": code}},
        status=status,
    )
    assert delivery.invoke(["--port", "8765", "status"]) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


def _sized_report(size: int) -> dict[str, Any]:
    report = _report()
    field = report["provenance"]["connection_provenance"]["fields"][-1]
    field["value"] = ""
    fragment = 'é/\\"\n😀'
    remaining = size - len(_json(report))
    charge = len(_json(fragment)) - 2
    field["value"] = fragment * (remaining // charge) + "x" * (remaining % charge)
    assert len(_json(report)) == size
    return report


@pytest.mark.parametrize("size,code", [(_LIMIT - 1, 0), (_LIMIT, 0), (_LIMIT + 1, 5)])
@pytest.mark.parametrize("declared", ["0", "9999999"])
def test_raw_reply_cap_and_json_plus_lf_are_independent_of_declared_length(
    size: int,
    code: int,
    declared: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _sized_report(size)
    raw = _json(report)
    delivery = Delivery(
        account_home,
        monkeypatch,
        chunks=[raw[:19], raw[19:]],
        headers=[("Content-Type", "application/json"), ("Content-Length", declared)],
    )
    assert delivery.invoke(_ARGS) == code
    output = capsys.readouterr()
    if code == 0:
        assert tuple(output) == ((raw + b"\n").decode(), "")
        assert len(output.out.encode()) == size + 1
    else:
        _local(output, "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed


@pytest.mark.parametrize(
    "size,allowed", [(_LIMIT - 1, True), (_LIMIT, True), (_LIMIT + 1, False)]
)
def test_existing_output_encoder_independently_bounds_monitor_primitives_plus_lf(
    size: int,
    allowed: bool,
) -> None:
    report = _sized_report(size)
    api = importlib.import_module("dutchmate_cli.client")
    if allowed:
        assert api._encode_record(report) == _json(report) + b"\n"
    else:
        with pytest.raises(api.CliFailure) as rejected:
            api._encode_record(report)
        assert rejected.value.kind.value == "invalid_response"


@pytest.mark.parametrize(
    "headers,valid",
    [
        ([("Content-Type", "application/json; charset=UTF-8")], True),
        (
            [("Content-Type", "application/json"), ("Content-Encoding", "identity")],
            True,
        ),
        ([("Content-Type", "text/plain")], False),
        ([("Content-Type", "application/json"), ("Content-Encoding", "gzip")], False),
        (
            [
                ("Content-Type", "application/json"),
                ("Content-Type", "application/json"),
            ],
            False,
        ),
        (
            [
                ("Content-Type", "application/json"),
                ("Content-Encoding", "identity"),
                ("Content-Encoding", "identity"),
            ],
            False,
        ),
    ],
)
def test_existing_media_and_identity_rules_apply_to_monitor_delivery(
    headers: list[tuple[str, str]],
    valid: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(account_home, monkeypatch, headers=headers)
    assert delivery.invoke(_ARGS) == (0 if valid else 5)
    if valid:
        assert tuple(capsys.readouterr()) == ((_json(_report()) + b"\n").decode(), "")
    else:
        _local(capsys.readouterr(), "invalid_response", phase="unknown")
        assert delivery.wire.stream.yielded == 0
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed


@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b"[]",
        b"\xff",
        b"{} trailing",
        _json(_report()).replace(b'"examined_rx_bytes":5', b'"examined_rx_bytes":NaN'),
        _json(_report())[:-1] + b',"outcome":"matched"}',
    ],
)
def test_strict_raw_json_failure_discards_entire_report_privately(
    raw: bytes,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = Delivery(account_home, monkeypatch, body=raw)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "failure,code,kind",
    [
        (httpx.ConnectError(_PRIVATE), 5, "transport_failed"),
        (httpx.ReadTimeout(_PRIVATE), 5, "request_timeout"),
        (httpx.RemoteProtocolError(_PRIVATE), 5, "invalid_response"),
        (RuntimeError(_PRIVATE), 1, "internal_failure"),
    ],
)
def test_transport_failures_preserve_unknown_receipt_and_never_retry(
    failure: Exception,
    code: int,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    delivery = _delivery(account_home, monkeypatch, failure=failure)
    caplog.set_level(logging.DEBUG)
    assert delivery.invoke(_ARGS) == code
    _local(capsys.readouterr(), kind, phase="unknown")
    assert len(delivery.wire.requests) == 1
    assert _PRIVATE not in caplog.text and _TOKEN not in caplog.text


@pytest.mark.parametrize(
    "mode,kind",
    [
        ("missing", "credential_unavailable"),
        ("unsafe", "unsafe_credential"),
        ("unsupported", "unsupported_platform"),
    ],
)
def test_valid_monitor_input_keeps_pre_submission_context_failures_private(
    mode: str,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    if mode == "unsafe":
        _helpers("test_cli_context")._credential(account_home, b"unsafe\n")
    elif mode == "unsupported":
        monkeypatch.setattr(sys, "platform", "win32")
    assert _command(api, _ARGS) == 3
    _local(capsys.readouterr(), kind)


@pytest.mark.parametrize(
    "failure,code,kind",
    [
        (KeyboardInterrupt(_PRIVATE), 130, "interrupted"),
        (typer.Abort(), 130, "interrupted"),
        (RuntimeError(_PRIVATE), 1, "internal_failure"),
    ],
)
def test_pre_submission_interrupts_and_unexpected_faults_keep_truthful_receipt(
    failure: BaseException,
    code: int,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(account_home, monkeypatch, credential_failure=failure)
    assert delivery.invoke(_ARGS) == code
    _local(capsys.readouterr(), kind)
    assert delivery.reads == ["credential"] and delivery.wire.requests == []


def test_interrupt_after_submission_is_exit130_unknown_without_remote_cleanup(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(account_home, monkeypatch)

    def interrupt(request: httpx.Request) -> None:
        del request
        raise KeyboardInterrupt(_PRIVATE)

    delivery.wire.on_request = interrupt
    assert delivery.invoke(_ARGS) == 130
    _local(capsys.readouterr(), "interrupted", phase="unknown")
    assert len(delivery.wire.requests) == 1
    assert all(transport.closed for transport in delivery.wire.transports)


@pytest.mark.parametrize("broken_pipe", [False, True])
def test_stdout_failure_retains_report_received_and_never_detaches(
    broken_pipe: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(account_home, monkeypatch)
    attempts: list[bytes] = []

    class FailedOutput:
        @property
        def buffer(self) -> FailedOutput:
            return self

        def write(self, record: bytes) -> int:
            attempts.append(record)
            if broken_pipe:
                raise BrokenPipeError(_PRIVATE)
            raise OSError(_PRIVATE)

        def flush(self) -> None:
            raise OSError(_PRIVATE)

        def close(self) -> None:
            pass

    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", FailedOutput())
        code = delivery.invoke(_ARGS)
    assert code == 1
    _local(capsys.readouterr(), "output_failed", phase="report_received")
    assert attempts == [_json(_report()) + b"\n"]
    assert len(delivery.wire.requests) == 1


def test_unusable_stderr_allows_exit_only_and_no_exception_fallback(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(
        account_home,
        monkeypatch,
        {"error": {"source": "monitor", "code": "busy"}},
        status=409,
    )
    writes: list[bytes] = []

    class FailedError:
        @property
        def buffer(self) -> FailedError:
            return self

        def write(self, record: bytes) -> int:
            writes.append(record)
            raise OSError(_PRIVATE)

        def flush(self) -> None:
            raise OSError(_PRIVATE)

    with monkeypatch.context() as patch:
        patch.setattr(sys, "stderr", FailedError())
        code = delivery.invoke(_ARGS)
    assert code == 1 and tuple(capsys.readouterr()) == ("", "")
    # Preserve 007's bounded fixed-category handling: the failed remote-error
    # write may be followed by one output_failed diagnostic, never raw exception
    # text or another fallback after that diagnostic also fails.
    assert writes == [
        _json({"error": {"source": "monitor", "code": "busy"}}) + b"\n",
        _json(
            {
                "error": {"source": "cli", "code": "output_failed"},
                "request_outcome": "report_received",
            }
        )
        + b"\n",
    ]
    assert len(delivery.wire.requests) == 1


def test_existing_ten_second_absolute_and_five_second_phase_budgets_are_not_monitor_bounds(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(account_home, monkeypatch)
    timeout_at = asyncio.timeout_at
    budgets: list[float] = []

    def observed(when: float | None) -> asyncio.Timeout:
        assert when is not None
        budgets.append(when - asyncio.get_running_loop().time())
        return timeout_at(when)

    monkeypatch.setattr(asyncio, "timeout_at", observed)
    assert delivery.invoke(_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(_report()) + b"\n").decode(), "")
    assert len(budgets) == 1 and 9.9 <= budgets[0] <= 10.0
    delivery.one_request("/v1/observation/monitor", _BODY)


@pytest.mark.parametrize("key", tuple(_report()))
def test_each_required_report_field_including_explicit_nulls_must_be_present(
    key: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report("timeout")
    del report[key]
    delivery = _delivery(account_home, monkeypatch, report)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "index,key",
    [(index, key) for index, marker in enumerate(_markers()) for key in marker],
)
def test_each_required_operation_marker_field_must_be_present(
    index: int,
    key: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _page_report(records=_markers(), snapshot_end_exclusive=9)
    del report["page"]["records"][index][key]
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize("mode", ["nonmatched_match", "unconfirmed_reference"])
def test_nullable_match_and_end_reference_follow_their_closed_variants(
    mode: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if mode == "nonmatched_match":
        report = _report("timeout")
        report["match"] = _report()["match"]
    else:
        report = _report(failure={"source": "journal", "code": "io_failure"})
        report["ended_record"] = {"session_id": _SESSION, "sequence": 8}
    delivery = _delivery(account_home, monkeypatch, report)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


_T020_INPUTS = [
    ("unicode-256", "--session", "🚀" * 64, True),
    ("unicode-257", "--session", "🚀" * 64 + "x", False),
    ("combining-256", "--session", "e\u0301" * 85 + "x", True),
    ("combining-257", "--session", "e\u0301" * 85 + "xx", False),
    (
        "condition-256",
        "--condition-base64",
        base64.b64encode(b"\xff" * 256).decode(),
        True,
    ),
    (
        "condition-257",
        "--condition-base64",
        base64.b64encode(b"\xff" * 257).decode(),
        False,
    ),
    ("pad-bits-one", "--condition-base64", "/x==", False),
    ("pad-bits-two", "--condition-base64", "//9=", False),
    (
        "pad-bits-maximum",
        "--condition-base64",
        base64.b64encode(b"\xff" * 256).decode()[:-3] + "x==",
        False,
    ),
    ("timeout-limit", "--timeout-ms", "4000", True),
    ("timeout-over", "--timeout-ms", "4001", False),
    ("rx-limit", "--max-rx-bytes", "1048576", True),
    ("rx-over", "--max-rx-bytes", "1048577", False),
]


@pytest.mark.parametrize(
    "label,option,value,accepted", _T020_INPUTS, ids=[case[0] for case in _T020_INPUTS]
)
def test_t020_input_byte_and_decoded_limits_precede_credentials_without_normalization(
    label: str,
    option: str,
    value: str,
    accepted: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del label
    args = list(_ARGS)
    args[args.index(option) + 1] = value
    if not accepted:
        api = _api()
        attempts = _block_preparation(api, monkeypatch)
        assert _command(api, args) == 2
        _local(capsys.readouterr(), "invalid_arguments")
        assert attempts == []
        return
    report = _report("detached")
    delivery = _delivery(account_home, monkeypatch, report)
    assert delivery.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    expected = dict(_BODY)
    field = option.removeprefix("--").replace("-", "_")
    expected["session_id" if field == "session" else field] = (
        int(value) if field in {"timeout_ms", "max_rx_bytes"} else value
    )
    delivery.one_request("/v1/observation/monitor", expected)


@pytest.mark.parametrize("outcome", _OUTCOMES)
@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.parametrize("unconfirmed", [False, True])
def test_t020_extreme_observation_facts_are_preserved_for_every_outcome_and_durability(
    outcome: str,
    device: bool,
    unconfirmed: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report(
        outcome,
        device=device,
        failure={"source": "journal", "code": "capacity/counter_exhausted"}
        if unconfirmed
        else None,
    )
    report["started_record"]["sequence"] = _MAX - 8
    report["window"] = {"start_inclusive": _MAX - 7, "end_exclusive": _MAX - 3}
    report["examined_rx_bytes"] = (
        1048576 if outcome in {"matched", "byte_limit"} else 1048575
    )
    report["observer_loss_records"] = 2 if device else 0
    if report["ended_record"] is not None:
        report["ended_record"]["sequence"] = _MAX - 1
    if outcome == "matched":
        last_chunk_size = 524288 if device else 262144
        report["match"] = {
            "start": {"sequence": _MAX - 4, "byte_offset": last_chunk_size - 3},
            "end": {"sequence": _MAX - 4, "byte_offset_exclusive": last_chunk_size},
        }
    started, deadline = _MAX - 1000000001, _MAX - 1
    report["clock"].update(
        started_at_ns=started,
        deadline_at_ns=deadline,
        decided_at_ns=deadline if outcome == "timeout" else started + 1,
    )
    delivery = Delivery(account_home, monkeypatch, body=_json(_reverse_objects(report)))
    args = [*_ARGS, "--max-rx-bytes", "1048576"]
    assert delivery.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    # No raw window is fetched and no Core clock, matcher, retention or policy is
    # imported to recompute these independently reported derived facts.
    delivery.one_request("/v1/observation/monitor", {**_BODY, "max_rx_bytes": 1048576})


_T020_BAD_REPORTS: list[tuple[bool, tuple[str, ...], Any]] = [
    (False, ("clock",), None),
    (False, ("window",), None),
    (False, ("operation_id",), _OPERATION.replace("-", "")),
    (False, ("outcome",), True),
    (False, ("durability",), None),
    (False, ("started_record", "session_id"), False),
    (False, ("match", "start"), None),
    (False, ("match", "end"), []),
    (False, ("match", "start", "sequence"), _MAX),
    (False, ("match", "start", "byte_offset"), True),
    (False, ("match", "end", "byte_offset_exclusive"), _MAX + 1),
    (False, ("clock", "origin_id"), _ORIGIN.upper()),
    (False, ("clock", "decided_at_ns"), False),
    (True, ("end_failure", "source"), None),
    (True, ("end_failure", "code"), []),
    (
        True,
        ("end_failure",),
        {"source": "journal", "code": "io_failure", "request_outcome": _PRIVATE},
    ),
    (True, ("end_failure",), {"source": "journal"}),
    (True, ("ended_record",), {"session_id": _SESSION, "sequence": 8}),
]


@pytest.mark.parametrize("unconfirmed,path,bad", _T020_BAD_REPORTS)
def test_t020_bad_nested_report_variants_discard_entire_remote_body_privately(
    unconfirmed: bool,
    path: tuple[str, ...],
    bad: Any,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    report = _report(
        failure={"source": "journal", "code": "io_failure"} if unconfirmed else None
    )
    report["provenance"]["connection_provenance"]["fields"][-1]["value"] = _PRIVATE
    _at(report, path[:-1])[path[-1]] = bad
    caplog.set_level(logging.DEBUG)
    delivery = _delivery(account_home, monkeypatch, report)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed
    assert _PRIVATE not in caplog.text and _TOKEN not in caplog.text


@pytest.mark.parametrize("size", [_LIMIT, _LIMIT + 1])
def test_t020_raw_whitespace_bound_is_independent_of_small_canonical_report(
    size: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report()
    raw = _json(report)
    raw += b" " * (size - len(raw))
    delivery = Delivery(
        account_home,
        monkeypatch,
        chunks=[raw[:13], raw[13:]],
        headers=[("Content-Type", "application/json"), ("Content-Length", "1")],
    )
    assert delivery.invoke(_ARGS) == (0 if size == _LIMIT else 5)
    if size == _LIMIT:
        assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    else:
        _local(capsys.readouterr(), "invalid_response", phase="unknown")
    delivery.one_request("/v1/observation/monitor", _BODY)


@pytest.mark.parametrize(
    "timeout,maximum", [(1, 1), (4000, 1), (1, 1048576), (4000, 1048576)]
)
def test_t020_monitor_observation_bounds_do_not_replace_http_delivery_budgets(
    timeout: int,
    maximum: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report("detached")
    report["clock"]["deadline_at_ns"] = 100 + timeout * 1000000
    delivery = _delivery(account_home, monkeypatch, report)
    original = asyncio.timeout_at
    budgets: list[float] = []

    def observed(when: float | None) -> asyncio.Timeout:
        assert when is not None
        budgets.append(when - asyncio.get_running_loop().time())
        return original(when)

    monkeypatch.setattr(asyncio, "timeout_at", observed)
    assert (
        delivery.invoke(
            [*_ARGS, "--timeout-ms", str(timeout), "--max-rx-bytes", str(maximum)]
        )
        == 0
    )
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    assert len(budgets) == 1 and 9.9 <= budgets[0] <= 10.0
    delivery.one_request(
        "/v1/observation/monitor",
        {**_BODY, "timeout_ms": timeout, "max_rx_bytes": maximum},
    )


@pytest.mark.parametrize("complete", [False, True], ids=["partial", "complete-bytes"])
@pytest.mark.parametrize(
    "failure,exit_code,kind",
    [
        (httpx.ReadTimeout(_PRIVATE), 5, "request_timeout"),
        (httpx.ReadError(_PRIVATE), 5, "transport_failed"),
        (httpx.RemoteProtocolError(_PRIVATE), 5, "invalid_response"),
    ],
)
def test_t020_stream_loss_never_upgrades_receipt_or_prints_partial_monitor_facts(
    complete: bool,
    failure: Exception,
    exit_code: int,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    report = _report(failure={"source": "journal", "code": "io_failure"})
    report["provenance"]["connection_provenance"]["fields"][-1]["value"] = _PRIVATE
    raw = _json(report)
    delivery = Delivery(
        account_home,
        monkeypatch,
        chunks=[raw if complete else raw[:40]],
        stream_failure=failure,
    )
    caplog.set_level(logging.DEBUG)
    assert delivery.invoke(_ARGS) == exit_code
    _local(capsys.readouterr(), kind, phase="unknown")
    delivery.one_request("/v1/observation/monitor", _BODY)
    assert _PRIVATE not in caplog.text and _TOKEN not in caplog.text


@pytest.mark.parametrize(
    "fault,code,kind",
    [
        ("invalid_response", 5, "invalid_response"),
        ("interrupt", 130, "interrupted"),
        ("unexpected", 1, "internal_failure"),
    ],
)
def test_t020_post_validation_encoding_failure_retains_report_received_without_cleanup(
    fault: str,
    code: int,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(account_home, monkeypatch)
    client = importlib.import_module("dutchmate_cli.client")
    original = client._encode_record
    calls: list[object] = []

    def encode(value: object) -> bytes:
        calls.append(value)
        if len(calls) == 1:
            if fault == "interrupt":
                raise KeyboardInterrupt(_PRIVATE)
            if fault == "invalid_response":
                raise client.CliFailure(client.CliFailureKind.INVALID_RESPONSE)
            raise RuntimeError(_PRIVATE)
        return bytes(original(value))

    monkeypatch.setattr(client, "_encode_record", encode)
    assert delivery.invoke(_ARGS) == code
    _local(capsys.readouterr(), kind, phase="report_received")
    assert len(calls) == 2
    delivery.one_request("/v1/observation/monitor", _BODY)
