"""CLI evidence grammar/wire tests and active end-to-end software acceptance.

T012 substitutes only external HTTP transport over real Typer/HTTPX delivery.
T014 bridges that transport to the actual authenticated service/Core/SQLite and
normalized fake physical backends. Test-side composition introduces no client
Core coupling, fake command/validator, or duplicate journal/lifecycle algorithm.
"""

import asyncio
import base64
import builtins
import importlib
import importlib.util
import inspect
import json
import logging
import sys
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio

from dutchmate_cli import client, context

_LIMIT = 1048576
_MAX = 9223372036854775807
_TOKEN = "0123456789abcdef" * 4
_PRIVATE = "private-evidence-argv-body-SQL-exception-sentinel"
_SESSION = "session-é"
_RECORD_ARGS = [
    "--port",
    "8765",
    "evidence",
    "record",
    "--session",
    _SESSION,
    "--sequence",
    "0",
]
_PAGE_ARGS = [
    "--port",
    "8765",
    "evidence",
    "page",
    "--session",
    _SESSION,
    "--max-records",
    "32",
    "--max-charged-bytes",
    "65536",
]


def _helpers(name: str) -> Any:
    # Established test modules are on pytest's import path; no package/source
    # path injection or new production test seam is needed.
    return importlib.import_module(name)


def _api() -> Any:
    return importlib.import_module("dutchmate_cli.main")


def _json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()


def _cursor(**changes: Any) -> str:
    value: dict[str, Any] = {
        "version": 1,
        "session_id": _SESSION,
        "range_start_inclusive": 0,
        "range_end_exclusive": None,
        "snapshot_end_exclusive": 9,
        "next_sequence": 3,
    }
    value.update(changes)
    return base64.urlsafe_b64encode(_json(value)).decode("ascii").rstrip("=")


def _rx(payload: bytes = b"\x00\xff\r\n", *, sequence: int = 0) -> dict[str, Any]:
    return {
        "kind": "rx_bytes",
        "sequence": sequence,
        "connection_id": "connection-é",
        "segment_id": "segment-é",
        "observed_at": {"domain_id": "host-domain", "value": 0},
        "payload_base64": base64.b64encode(payload).decode("ascii"),
    }


def _report(**changes: Any) -> dict[str, Any]:
    page: dict[str, Any] = {
        "records": [_rx()],
        "snapshot_end_exclusive": 1,
        "expired_range": None,
        "retention_marker": None,
        "never_existed_range": None,
        "outcome": "complete",
        "truncated": False,
        "continuation": None,
        "charged_bytes": 4242,
        "next_record_required_bytes": None,
    }
    page.update(changes)
    return {"run_id": "run-é", "session_id": _SESSION, "page": page}


def _domain(device: bool) -> dict[str, Any]:
    return {
        "domain_id": "device-domain" if device else "host-domain",
        "observer": "device" if device else "host",
        "meaning": "observation",
        "unit": "tick" if device else "nanosecond",
        "origin_id": "device-origin" if device else "host-origin",
    }


def _full_report(device: bool = False) -> dict[str, Any]:
    provenance = {
        "connection_id": "connection-é",
        "segment_id": "segment-é",
        "capabilities": ["gpio_control", "uart_receive"]
        if device
        else ["uart_receive"],
        "backend_observation_timestamp_domain": _domain(device),
        "loss_observability": {
            "kind": "observer_reports_uart_loss",
            "observer_id": "observer",
            "scope": "fifo",
        }
        if device
        else {"kind": "upstream_loss_not_observable"},
        "connection_provenance": {
            "envelope_version": 1,
            "backend_kind": "opaque-backend",
            "backend_schema_version": 7,
            "fields": [
                {"name": "a-null", "value": None},
                {"name": "b-bool", "value": True},
                {"name": "c-int", "value": 7},
                {"name": "d-text", "value": 'é/\\"\n\0'},
            ],
        },
    }
    records: list[dict[str, Any]] = [
        {"kind": "segment_started", "sequence": 0, "provenance": provenance}
    ]
    for payload in (b"", bytes(range(256)), b"\x00\xff\xfe\r\n\r\n"):
        item = _rx(payload, sequence=len(records))
        item["observed_at"]["domain_id"] = _domain(device)["domain_id"]
        records.append(item)
    for cause, lost in (("overflow", 7), ("other_observed_loss", None)):
        records.append(
            {
                "kind": "observer_loss",
                "sequence": len(records),
                "connection_id": "connection-é",
                "segment_id": "segment-é",
                "observer_id": "observer",
                "scope": "fifo",
                "cause": cause,
                "lost_bytes": lost,
                "observed_at": {"domain_id": _domain(device)["domain_id"], "value": 0},
            }
        )
    for reason in (
        "explicit_stop",
        "disconnected",
        "timestamp_origin_reset",
        "recording_failure",
        "transport_failure",
    ):
        records.append(
            {
                "kind": "segment_ended",
                "sequence": len(records),
                "connection_id": "connection-é",
                "segment_id": "segment-é",
                "reason": reason,
            }
        )
    return _report(records=records, snapshot_end_exclusive=len(records))


def _with_marker() -> dict[str, Any]:
    return _report(
        expired_range={"start_inclusive": 1, "end_exclusive": 3},
        retention_marker={
            "expired_range": {"start_inclusive": 0, "end_exclusive": 3},
            "first_discarded_timestamp": {
                "timestamp": {"domain_id": "host-domain", "value": 90},
                "domain": _domain(False),
            },
            "last_discarded_timestamp": {
                "timestamp": {"domain_id": "device-domain", "value": 2},
                "domain": _domain(True),
            },
            "discarded_record_count": 3,
            "discarded_rx_payload_byte_count": 5,
            "discarded_charged_bytes": 700,
        },
        never_existed_range={"start_inclusive": 9, "end_exclusive": 12},
        outcome="partial",
        snapshot_end_exclusive=9,
    )


def _command(api: Any, args: list[str]) -> int:
    return int(_helpers("test_cli_commands")._console(api, args))


def _local(output: tuple[str, str], code: str, *, phase: str = "not_submitted") -> None:
    stdout, stderr = output
    assert stdout == ""
    assert (
        stderr.encode()
        == _json({"error": {"source": "cli", "code": code}, "request_outcome": phase})
        + b"\n"
    )
    assert _PRIVATE not in stderr and _TOKEN not in stderr and "\x1b" not in stderr


class Delivery:
    def __init__(
        self,
        account_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        body: bytes | None = None,
        credential_failure: BaseException | None = None,
        **wire_options: Any,
    ) -> None:
        _helpers("test_cli_context")._credential(account_home, _TOKEN.encode() + b"\n")
        self.api = _api()
        self.reads: list[str] = []
        read = context.read_credential

        def counted() -> str:
            self.reads.append("credential")
            if credential_failure is not None:
                raise credential_failure
            return read()

        # Cover existing context use and normal direct imports without defining
        # or requiring the future evidence adapter's private helper names.
        monkeypatch.setattr(context, "read_credential", counted)
        for name, module in tuple(sys.modules.items()):
            if name.startswith("dutchmate_cli") and module is not None:
                for attribute, imported in tuple(vars(module).items()):
                    if imported is read:
                        monkeypatch.setattr(module, attribute, counted)
        self.wire = _helpers("test_cli_transport")._Wire(
            client,
            monkeypatch,
            _json(_report()) if body is None else body,
            **wire_options,
        )
        self.imports: list[str] = []
        original_import = builtins.__import__

        def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name.startswith(("dutchmate_core", "dutchmate_service")):
                self.imports.append(name)
                pytest.fail(
                    "thin evidence CLI cannot import Core/service implementation"
                )
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", guarded_import)

    def invoke(self, args: list[str]) -> int:
        return _command(self.api, args)

    def one_request(
        self,
        route: str,
        expected: dict[str, Any],
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        assert self.reads == ["credential"] and self.imports == []
        assert len(self.wire.requests) == 1
        request = self.wire.requests[0]
        assert request.method == "POST"
        assert request.url.scheme == "http" and request.url.host == host
        assert (request.url.port if request.url.port is not None else 80) == port
        assert (
            request.url.raw_path == route.encode()
            and request.url.query == b""
            and request.url.fragment == ""
        )
        assert json.loads(request.content) == expected
        assert set(json.loads(request.content)) == set(expected)
        authority = f"[::1]:{port}" if host == "::1" else f"127.0.0.1:{port}"
        assert request.headers.get_list("host") == [authority]
        assert request.headers.get_list("authorization") == ["Bearer " + _TOKEN]
        assert request.headers.get_list("accept") == ["application/json"]
        assert request.headers.get_list("accept-encoding") == ["identity"]
        assert request.headers.get_list("content-type") == ["application/json"]
        assert not any(
            name in request.headers for name in ("cookie", "upgrade", "origin")
        )
        assert not any(name.startswith("sec-fetch-") for name in request.headers)
        assert _TOKEN.encode() not in request.content and _TOKEN not in str(request.url)
        assert len(self.wire.client_options) == len(self.wire.transport_options) == 1
        for options in (*self.wire.client_options, *self.wire.transport_options):
            assert options["trust_env"] is False and options["proxy"] is None
            assert options["http1"] is True and options["http2"] is False
            assert (
                options["limits"].max_connections == 1
                and options["limits"].max_keepalive_connections == 0
            )
        assert self.wire.client_options[0]["follow_redirects"] is False
        assert self.wire.client_options[0]["mounts"] is None
        timeout = self.wire.client_options[0]["timeout"]
        assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (
            5.0,
        ) * 4
        assert self.wire.transport_options[0]["retries"] == 0
        assert (
            all(item.closed for item in self.wire.transports)
            and self.wire.stream.closed
        )


_HELP = [
    [],
    ["--help"],
    ["evidence"],
    ["evidence", "--help"],
    ["evidence", "record", "--help"],
    ["evidence", "page", "--help"],
    ["--host", _PRIVATE, "--port", "0", "evidence", "--help"],
]


@pytest.mark.parametrize("args", _HELP)
@pytest.mark.parametrize("unsupported", [False, True])
def test_evidence_help_and_group_no_command_are_static_and_resource_free(
    args: list[str],
    unsupported: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _helpers("test_cli_commands")._block_preparation(api, monkeypatch)
    if unsupported:
        monkeypatch.setattr(sys, "platform", "win32")
    assert _command(api, args) == 0
    stdout, stderr = capsys.readouterr()
    assert stdout and stderr == "" and "--help" in stdout
    if "record" in args:
        assert "--session" in stdout and "--sequence" in stdout
    elif "page" in args:
        for option in (
            "--session",
            "--max-records",
            "--max-charged-bytes",
            "--start",
            "--end",
            "--cursor",
        ):
            assert option in stdout
    elif "evidence" in args:
        assert "record" in stdout and "page" in stdout
    else:
        assert (
            "evidence" in stdout
            and "attach" in stdout
            and "status" in stdout
            and "detach" in stdout
        )
    for forbidden in (
        "--journal",
        "--database",
        "--run-id",
        "--follow",
        "--format",
        "--raw-file",
        "--token-file",
        _PRIVATE,
    ):
        assert forbidden not in stdout
    assert attempts == []


_BAD_ARGS: list[list[str]] = [
    ["evidence", "record", "--session", _SESSION, "--sequence", "0"],
    ["--port", "8765", "evidence", "record"],
    ["--port", "8765", "evidence", "page"],
    ["--port", "8765", "evidence", _PRIVATE],
]
for template in (_RECORD_ARGS, _PAGE_ARGS):
    options = (
        ("--session", "--sequence")
        if template is _RECORD_ARGS
        else ("--session", "--max-records", "--max-charged-bytes")
    )
    for option in options:
        index = template.index(option)
        _BAD_ARGS.append(template[:index] + template[index + 2 :])
    for value in ("", "x\0y", "x" * 257, "é" * 129):
        bad = list(template)
        bad[bad.index("--session") + 1] = value
        _BAD_ARGS.append(bad)
    for option in (
        "--journal",
        "--database",
        "--run-id",
        "--url",
        "--token-file",
        "--json-input",
        "--output-format",
        "--raw-file",
        "--timeout",
        "--follow",
    ):
        _BAD_ARGS.append([*template, option, _PRIVATE])
    _BAD_ARGS.append([*template, _PRIVATE])
for option, maximum, template in (
    ("--sequence", _MAX, _RECORD_ARGS),
    ("--max-records", 4096, _PAGE_ARGS),
    ("--max-charged-bytes", _LIMIT, _PAGE_ARGS),
):
    for value in ("-1", str(maximum + 1), "true", "false", "1.0", "1e0", _PRIVATE):
        bad = list(template)
        bad[bad.index(option) + 1] = value
        _BAD_ARGS.append(bad)
    _BAD_ARGS.append([*template, option])
for option in ("--max-records", "--max-charged-bytes"):
    bad = list(_PAGE_ARGS)
    bad[bad.index(option) + 1] = "0"
    _BAD_ARGS.append(bad)
for suffix in (
    ["--start", "0"],
    ["--end", "1"],
    ["--start", "2", "--end", "1"],
    ["--start", "true", "--end", "1"],
    ["--start", "0", "--end", str(_MAX + 1)],
    ["--start", "-1", "--end", "1"],
):
    _BAD_ARGS.append([*_PAGE_ARGS, *suffix])
for value in ("", "A" * 1025, "é", "a=", "a+", "a/", "a ", "a\0b"):
    _BAD_ARGS.append([*_PAGE_ARGS, "--cursor", value])


@pytest.mark.parametrize("args", _BAD_ARGS)
def test_bad_evidence_grammar_and_lexical_domains_fail_privately_before_io(
    args: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = _api()
    attempts = _helpers("test_cli_commands")._block_preparation(api, monkeypatch)
    assert _command(api, args) == 2
    _local(capsys.readouterr(), "invalid_arguments")
    assert attempts == [] and _PRIVATE not in caplog.text
    result = _helpers("test_cli_commands")._runner(api, args)
    _helpers("test_cli_commands")._grammar_rejected(result)


@pytest.mark.parametrize(
    "session,sequence",
    [(" ", 0), ("x" * 256, _MAX), ("é" * 128, 0), ("e\u0301", 1), (" /opaque/id ", 3)],
)
@pytest.mark.parametrize("host,port", [("127.0.0.1", 1), ("::1", 65535)])
def test_record_lexical_edges_preserve_id_and_emit_one_literal_authenticated_request(
    session: str,
    sequence: int,
    host: str,
    port: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report(records=[], outcome="not_found", charged_bytes=0)
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NETRC", "DUTCHMATE_TOKEN"):
        monkeypatch.setenv(name, _PRIVATE)
    assert (
        delivery.invoke(
            [
                "--host",
                host,
                "--port",
                str(port),
                "evidence",
                "record",
                "--session",
                session,
                "--sequence",
                str(sequence),
            ]
        )
        == 0
    )
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    delivery.one_request(
        "/v1/evidence/record",
        {"session_id": session, "sequence": sequence},
        host=host,
        port=port,
    )


@pytest.mark.parametrize(
    "start,end,records,charged",
    [
        (None, None, 1, 1),
        (0, 0, 4096, _LIMIT),
        (0, _MAX, 32, 65536),
        (_MAX, _MAX, 1, 1),
    ],
)
def test_page_paired_ranges_budget_edges_and_explicit_null_fields(
    start: int | None,
    end: int | None,
    records: int,
    charged: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = Delivery(account_home, monkeypatch)
    args = [
        "--port",
        "8765",
        "evidence",
        "page",
        "--session",
        _SESSION,
        "--max-records",
        str(records),
        "--max-charged-bytes",
        str(charged),
    ]
    if start is not None:
        args += ["--start", str(start), "--end", str(end)]
    assert delivery.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((_json(_report()) + b"\n").decode(), "")
    delivery.one_request(
        "/v1/evidence/page",
        {
            "session_id": _SESSION,
            "start_inclusive": start,
            "end_exclusive": end,
            "max_records": records,
            "max_charged_bytes": charged,
            "cursor": None,
        },
    )


@pytest.mark.parametrize("token", ["A", "Zh", "A" * 1024])
def test_input_cursor_is_only_lexically_checked_and_sent_unchanged_to_service(
    token: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = {"error": {"source": "request", "code": "invalid_request"}}
    delivery = Delivery(account_home, monkeypatch, body=_json(error), status=422)
    assert delivery.invoke([*_PAGE_ARGS, "--cursor", token]) == 4
    assert tuple(capsys.readouterr()) == ("", (_json(error) + b"\n").decode())
    delivery.one_request(
        "/v1/evidence/page",
        {
            "session_id": _SESSION,
            "start_inclusive": None,
            "end_exclusive": None,
            "max_records": 32,
            "max_charged_bytes": 65536,
            "cursor": token,
        },
    )


@pytest.mark.parametrize(
    "option,bad,good",
    [
        ("--session", "x" * 257, _SESSION),
        ("--sequence", "-1", "0"),
        ("--max-records", "0", "32"),
        ("--max-charged-bytes", "0", "65536"),
        ("--cursor", "bad=", "A"),
    ],
)
@pytest.mark.parametrize("invalid_last", [False, True])
def test_repeated_valued_options_follow_existing_last_value_contract(
    option: str,
    bad: str,
    good: str,
    invalid_last: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = list(_RECORD_ARGS if option == "--sequence" else _PAGE_ARGS)
    values = [good, bad] if invalid_last else [bad, good]
    args += [option, values[0], option, values[1]]
    if invalid_last:
        attempts = _helpers("test_cli_commands")._block_preparation(_api(), monkeypatch)
        assert _command(_api(), args) == 2
        _local(capsys.readouterr(), "invalid_arguments")
        assert attempts == []
    else:
        delivery = Delivery(account_home, monkeypatch)
        assert delivery.invoke(args) == 0
        assert tuple(capsys.readouterr()) == ((_json(_report()) + b"\n").decode(), "")
        assert delivery.reads == ["credential"] and len(delivery.wire.requests) == 1
        expected = json.loads(delivery.wire.requests[0].content)
        assert expected[
            {
                "--session": "session_id",
                "--sequence": "sequence",
                "--max-records": "max_records",
                "--max-charged-bytes": "max_charged_bytes",
                "--cursor": "cursor",
            }[option]
        ] == (
            int(good)
            if option in {"--sequence", "--max-records", "--max-charged-bytes"}
            else good
        )


@pytest.mark.parametrize("outcome", ["complete", "partial", "expired", "not_found"])
@pytest.mark.parametrize("device", [False, True], ids=["host-facts", "device-facts"])
def test_binary_order_provenance_and_all_outcomes_are_delivered_without_core_recomputation(
    outcome: str,
    device: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _full_report(device)
    report["page"]["outcome"] = outcome
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 0
    stdout, stderr = capsys.readouterr()
    assert stderr == "" and stdout.encode() == _json(report) + b"\n"
    assert base64.b64decode(
        json.loads(stdout)["page"]["records"][2]["payload_base64"], validate=True
    ) == bytes(range(256))
    assert delivery.reads == ["credential"] and len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "report",
    [
        _report(records=[], charged_bytes=0),
        _with_marker(),
        _report(
            records=[],
            charged_bytes=0,
            snapshot_end_exclusive=9,
            truncated=True,
            continuation=_cursor(),
            next_record_required_bytes=2000000,
        ),
    ],
)
def test_optional_retention_and_byte_shortage_facts_do_not_trigger_more_requests(
    report: dict[str, Any],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 1 and delivery.reads == ["credential"]


_NEW_ERRORS = [
    (404, "evidence", "no_associated_session"),
    (409, "evidence", "session_not_associated"),
    (503, "evidence", "read_unavailable"),
    (409, "evidence", "source_changed"),
    (503, "evidence", "read_capacity"),
    (413, "evidence", "delivery_too_large"),
    (422, "journal", "invalid_input"),
    (409, "journal", "session_mismatch"),
    (404, "journal", "journal_missing"),
    (503, "journal", "busy"),
    (409, "journal", "closed"),
]
_NEW_ERRORS += [
    (500, "journal", kind)
    for kind in (
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
]
_ERRORS = [*_NEW_ERRORS, *_helpers("test_cli_transport")._REMOTE_ERRORS]


@pytest.mark.parametrize("status,source,code", _ERRORS)
def test_exact_remote_error_pairs_exit_four_without_local_receipt_or_replay(
    status: int,
    source: str,
    code: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = {"error": {"source": source, "code": code}}
    delivery = Delivery(account_home, monkeypatch, body=_json(error), status=status)
    assert delivery.invoke(_PAGE_ARGS) == 4
    assert tuple(capsys.readouterr()) == ("", (_json(error) + b"\n").decode())
    assert delivery.reads == ["credential"] and len(delivery.wire.requests) == 1
    assert delivery.wire.stream.closed and all(
        item.closed for item in delivery.wire.transports
    )


_CLOSED_PATHS = [
    (),
    ("page",),
    ("page", "records", 0),
    ("page", "records", 0, "provenance"),
    ("page", "records", 0, "provenance", "backend_observation_timestamp_domain"),
    ("page", "records", 0, "provenance", "loss_observability"),
    ("page", "records", 0, "provenance", "connection_provenance"),
    ("page", "records", 0, "provenance", "connection_provenance", "fields", 0),
    ("page", "records", 1),
    ("page", "records", 1, "observed_at"),
    ("page", "records", 4),
    ("page", "records", 6),
]


def _at(value: Any, path: tuple[Any, ...]) -> Any:
    for key in path:
        value = value[key]
    return value


@pytest.mark.parametrize("path", _CLOSED_PATHS)
@pytest.mark.parametrize("change", ["extra", "missing"])
def test_evidence_wire_objects_are_closed_and_required_fields_are_not_defaulted(
    path: tuple[Any, ...],
    change: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _full_report(True)
    view = _at(report, path)
    if change == "extra":
        view["private"] = _PRIVATE
    else:
        del view[next(iter(view))]
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


_BAD_FIELDS: list[tuple[tuple[Any, ...], Any]] = [
    (("run_id",), None),
    (("session_id",), ""),
    (("page", "records"), {}),
    (("page", "snapshot_end_exclusive"), True),
    (("page", "charged_bytes"), -1),
    (("page", "charged_bytes"), _MAX + 1),
    (("page", "outcome"), "success"),
    (("page", "truncated"), 1),
    (("page", "next_record_required_bytes"), 0),
    (("page", "next_record_required_bytes"), True),
    (("page", "records", 1, "sequence"), _MAX),
    (("page", "records", 1, "kind"), "text"),
    (("page", "records", 1, "connection_id"), ""),
    (("page", "records", 1, "observed_at", "value"), True),
    (("page", "records", 1, "observed_at", "value"), -1),
    (("page", "records", 4, "lost_bytes"), 0),
    (("page", "records", 4, "lost_bytes"), True),
    (("page", "records", 4, "cause"), "unknown"),
    (("page", "records", 6, "reason"), "reset"),
]


@pytest.mark.parametrize("path,bad", _BAD_FIELDS)
def test_wire_types_enums_and_counter_domains_never_coerce_or_leak_raw_reply(
    path: tuple[Any, ...],
    bad: Any,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _full_report(True)
    _at(report, path[:-1])[path[-1]] = bad
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "payload", ["/w", "/w=", "/w===", "/x==", "_w==", "-w==", "/w==\n", "é", 7, None]
)
def test_noncanonical_standard_base64_is_a_private_protocol_failure(
    payload: Any,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report()
    report["page"]["records"][0]["payload_base64"] = payload
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_RECORD_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize("token", [_cursor(), None])
def test_reply_continuation_shape_and_canonical_token_round_trip(
    token: str | None,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report(
        snapshot_end_exclusive=9, truncated=token is not None, continuation=token
    )
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "token",
    [_cursor() + "=", _cursor(version=True), _cursor(extra="private"), "é", "A"],
)
def test_reply_cursor_requires_canonical_document_while_input_is_opaque(
    token: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = Delivery(
        account_home, monkeypatch, body=_json(_report(continuation=token))
    )
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")


@pytest.mark.parametrize(
    "status,document",
    [
        (409, {"error": {"source": "evidence", "code": "no_associated_session"}}),
        (500, {"error": {"source": "journal", "code": "busy"}}),
        (503, {"error": {"source": "evidence", "code": "unknown"}}),
        (
            404,
            {
                "error": {
                    "source": "evidence",
                    "code": "no_associated_session",
                    "detail": _PRIVATE,
                }
            },
        ),
        (
            404,
            {
                "error": {"source": "evidence", "code": "no_associated_session"},
                "request_outcome": "report_received",
            },
        ),
    ],
)
def test_wrong_error_pair_or_nonclosed_error_is_private_invalid_response(
    status: int,
    document: dict[str, Any],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = Delivery(account_home, monkeypatch, body=_json(document), status=status)
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")


@pytest.mark.parametrize(
    "headers",
    [
        [("Content-Type", "text/plain")],
        [("Content-Type", "application/json"), ("Content-Type", "application/json")],
        [("Content-Type", "application/json"), ("Content-Encoding", "gzip")],
        [
            ("Content-Type", "application/json"),
            ("Content-Encoding", "identity"),
            ("Content-Encoding", "identity"),
        ],
    ],
)
def test_delivery_retains_existing_media_and_identity_encoding_checks(
    headers: list[tuple[str, str]],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = Delivery(account_home, monkeypatch, headers=headers)
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert delivery.wire.stream.yielded == 0 and len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        '{"run_id":"run-é",'.encode() + _json(_report())[1:],
        b'{"run_id":NaN}',
        b'{"run_id":Infinity}',
        b"null",
        b"[]",
        b"{} trailing",
    ],
)
def test_strict_raw_json_utf8_duplicates_and_nonfinite_are_private(
    raw: bytes,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    delivery = Delivery(account_home, monkeypatch, body=raw)
    caplog.set_level(logging.DEBUG)
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert _PRIVATE not in caplog.text and _TOKEN not in caplog.text


@pytest.mark.parametrize("difference", [-1, 0, 1])
def test_raw_http_cap_and_cli_json_plus_one_lf_are_independent_of_record_charges(
    difference: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _full_report()
    field = report["page"]["records"][0]["provenance"]["connection_provenance"][
        "fields"
    ][-1]
    field["value"] = ""
    field["value"] = "é" + "a" * (_LIMIT + difference - len(_json(report)) - 2)
    raw = _json(report)
    assert len(raw) == _LIMIT + difference
    delivery = Delivery(
        account_home,
        monkeypatch,
        chunks=[raw[:17], raw[17:]],
        headers=[("Content-Type", "application/json"), ("Content-Length", "0")],
    )
    code = delivery.invoke(_PAGE_ARGS)
    if difference <= 0:
        assert code == 0
        stdout, stderr = capsys.readouterr()
        assert (
            stdout.encode() == raw + b"\n"
            and len(stdout.encode()) <= _LIMIT + 1
            and stderr == ""
        )
    else:
        assert code == 5
        _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed


def test_existing_output_encoder_enforces_its_own_bound_on_evidence_primitives() -> (
    None
):
    report = _full_report()
    field = report["page"]["records"][0]["provenance"]["connection_provenance"][
        "fields"
    ][-1]
    field["value"] = ""
    field["value"] = "é" + "a" * (_LIMIT - len(_json(report)) - 2)
    expected = _json(report)
    assert len(expected) == _LIMIT
    assert client._encode_record(report) == expected + b"\n"
    field["value"] += "a"
    # Existing import-purity cases reload context's classes; observe the
    # ordinary exception class actually retained by the shared encoder.
    encoder_api = importlib.import_module("dutchmate_cli.client")
    with pytest.raises(encoder_api.CliFailure) as caught:
        client._encode_record(report)
    assert caught.value.kind.value == "invalid_response"
    state = client.DeliveryState(request_outcome="report_received")
    code, record = client.local_failure(caught.value.kind, state)
    assert code == 5
    assert (
        record
        == _json(
            {
                "error": {"source": "cli", "code": "invalid_response"},
                "request_outcome": "report_received",
            }
        )
        + b"\n"
    )


@pytest.mark.parametrize(
    "failure,exit_code,kind",
    [
        (httpx.ConnectError(_PRIVATE), 5, "transport_failed"),
        (httpx.ReadTimeout(_PRIVATE), 5, "request_timeout"),
        (httpx.RemoteProtocolError(_PRIVATE), 5, "invalid_response"),
        (RuntimeError(_PRIVATE), 1, "internal_failure"),
    ],
)
def test_transport_failures_keep_unknown_delivery_and_do_not_retry(
    failure: Exception,
    exit_code: int,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    delivery = Delivery(account_home, monkeypatch, failure=failure)
    caplog.set_level(logging.DEBUG)
    assert delivery.invoke(_PAGE_ARGS) == exit_code
    _local(capsys.readouterr(), kind, phase="unknown")
    assert (
        len(delivery.wire.requests) == 1
        and _PRIVATE not in caplog.text
        and _TOKEN not in caplog.text
    )


def test_one_absolute_ten_second_budget_surrounds_evidence_delivery(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = Delivery(account_home, monkeypatch)
    timeout_at = asyncio.timeout_at
    budgets: list[float] = []

    def observed(when: float | None) -> asyncio.Timeout:
        assert when is not None
        budgets.append(when - asyncio.get_running_loop().time())
        return timeout_at(when)

    monkeypatch.setattr(asyncio, "timeout_at", observed)
    assert delivery.invoke(_PAGE_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(_report()) + b"\n").decode(), "")
    assert len(budgets) == 1 and 9.9 <= budgets[0] <= 10.0
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "mode,exit_code,kind",
    [
        ("missing", 3, "credential_unavailable"),
        ("unsafe", 3, "unsafe_credential"),
        ("unsupported", 3, "unsupported_platform"),
    ],
)
def test_valid_evidence_arguments_preserve_pre_submission_private_context_failures(
    mode: str,
    exit_code: int,
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
    assert _command(api, _PAGE_ARGS) == exit_code
    _local(capsys.readouterr(), kind)


@pytest.mark.parametrize(
    "headers",
    [
        [("Content-Type", "application/json; charset=UTF-8")],
        [("Content-Type", "application/json"), ("Content-Encoding", "identity")],
    ],
)
def test_supported_utf8_media_and_single_identity_encoding_deliver_evidence(
    headers: list[tuple[str, str]],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = Delivery(account_home, monkeypatch, headers=headers)
    assert delivery.invoke(_PAGE_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(_report()) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed


@pytest.mark.parametrize(
    "failure,exit_code,kind",
    [
        (KeyboardInterrupt(_PRIVATE), 130, "interrupted"),
        (RuntimeError(_PRIVATE), 1, "internal_failure"),
    ],
)
def test_pre_request_interrupt_and_unexpected_failure_keep_private_not_submitted_receipt(
    failure: BaseException,
    exit_code: int,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = Delivery(account_home, monkeypatch, credential_failure=failure)
    assert delivery.invoke(_PAGE_ARGS) == exit_code
    _local(capsys.readouterr(), kind)
    assert delivery.reads == ["credential"] and delivery.wire.requests == []


def test_stdout_failure_keeps_report_received_without_service_cleanup_request(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = Delivery(account_home, monkeypatch)
    attempts: list[bytes] = []

    class FailedStdout:
        @property
        def buffer(self) -> FailedStdout:
            return self

        def write(self, record: bytes) -> int:
            attempts.append(record)
            raise OSError(_PRIVATE)

        def flush(self) -> None:
            raise OSError(_PRIVATE)

    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", FailedStdout())
        code = delivery.invoke(_PAGE_ARGS)
    assert code == 1
    _local(capsys.readouterr(), "output_failed", phase="report_received")
    assert attempts == [_json(_report()) + b"\n"]
    assert delivery.reads == ["credential"] and len(delivery.wire.requests) == 1


_MARKER_PATHS = [
    ("page", "expired_range"),
    ("page", "never_existed_range"),
    ("page", "retention_marker"),
    ("page", "retention_marker", "expired_range"),
    ("page", "retention_marker", "first_discarded_timestamp"),
    ("page", "retention_marker", "first_discarded_timestamp", "timestamp"),
    ("page", "retention_marker", "first_discarded_timestamp", "domain"),
    ("page", "retention_marker", "last_discarded_timestamp"),
    ("page", "retention_marker", "last_discarded_timestamp", "timestamp"),
    ("page", "retention_marker", "last_discarded_timestamp", "domain"),
]


@pytest.mark.parametrize("path", _MARKER_PATHS)
@pytest.mark.parametrize("change", ["extra", "missing"])
def test_range_marker_and_timestamp_endpoint_objects_are_closed(
    path: tuple[Any, ...],
    change: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _with_marker()
    view = _at(report, path)
    if change == "extra":
        view["detail"] = _PRIVATE
    else:
        del view[next(iter(view))]
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


def test_null_retention_timestamp_endpoints_remain_null_without_clock_inference(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _with_marker()
    report["page"]["retention_marker"]["first_discarded_timestamp"] = None
    report["page"]["retention_marker"]["last_discarded_timestamp"] = None
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "status,source,code",
    [
        (404, "evidence", "no_associated_session"),
        (503, "journal", "busy"),
        (503, "service", "stopping"),
    ],
)
def test_evidence_remote_errors_emit_declared_canonical_key_order(
    status: int,
    source: str,
    code: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Closed fields are valid regardless of incoming object order. Delivery must
    # emit the contract's source/code order, just as successful evidence does.
    delivery = Delivery(
        account_home,
        monkeypatch,
        body=_json({"error": {"code": code, "source": source}}),
        status=status,
    )
    assert delivery.invoke(_PAGE_ARGS) == 4
    assert tuple(capsys.readouterr()) == (
        "",
        (_json({"error": {"source": source, "code": code}}) + b"\n").decode(),
    )
    assert len(delivery.wire.requests) == 1 and delivery.reads == ["credential"]


def _t014_service_helpers(patch: pytest.MonkeyPatch) -> Any:
    root = Path(__file__).resolve().parents[2] / "service/tests"
    for name, filename in (
        ("test_service_http", "test_service_http.py"),
        ("_cli_t014_evidence_service", "test_evidence_http.py"),
    ):
        if name in sys.modules:
            continue
        spec = importlib.util.spec_from_file_location(name, root / filename)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        patch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
    return sys.modules["_cli_t014_evidence_service"]


@pytest_asyncio.fixture(
    params=[(0, 0), (0, 1), (1, 0), (1, 1)],
    ids=["basic-ipv4", "basic-ipv6", "enhanced-shaped-ipv4", "enhanced-shaped-ipv6"],
)
async def active_evidence_service(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Any]:
    helper = _t014_service_helpers(monkeypatch)
    backend_index, family_index = request.param
    async with helper.t014_active_service(
        tmp_path,
        account_home,
        monkeypatch,
        backend_index,
        helper._CONFIGS[family_index],
    ) as service:
        yield service


class ActiveBridge:
    """Only the external HTTP hop is bridged; server work stays on its owner loop."""

    def __init__(
        self, service: Any, patch: pytest.MonkeyPatch, *, fault: str | None = None
    ) -> None:
        self.service = service
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response] = []
        owner_loop = asyncio.get_running_loop()
        bridge = self

        class Transport(httpx.AsyncBaseTransport):
            def __init__(self) -> None:
                self.asgi = httpx.ASGITransport(
                    app=service.app, client=(service.config.host, 12345)
                )

            async def handle_async_request(
                self, request: httpx.Request
            ) -> httpx.Response:
                if asyncio.get_running_loop() is owner_loop:
                    return await self.serve(request)
                return await asyncio.wrap_future(
                    asyncio.run_coroutine_threadsafe(self.serve(request), owner_loop)
                )

            async def serve(self, request: httpx.Request) -> httpx.Response:
                bridge.requests.append(request)
                if fault == "origin":
                    request.headers["Origin"] = "https://browser.invalid"
                elif fault == "auth":
                    token = service.token.decode()
                    token = ("0" if token[0] != "0" else "1") + token[1:]
                    request.headers["Authorization"] = "Bearer " + token
                serving = service.serving.set(True)
                try:
                    response = await self.asgi.handle_async_request(request)
                    bridge.responses.append(response)
                    return response
                finally:
                    service.serving.reset(serving)

            async def aclose(self) -> None:
                await self.asgi.aclose()

        def transport(*args: Any, **kwargs: Any) -> Transport:
            return Transport()

        patch.setattr(httpx, "AsyncHTTPTransport", transport)

        import socket

        def forbidden(*args: object, **kwargs: object) -> None:
            pytest.fail("active acceptance must not open a real socket")

        patch.setattr(socket, "getaddrinfo", forbidden)
        patch.setattr(socket.socket, "connect", forbidden)
        patch.setattr(socket.socket, "connect_ex", forbidden)

    def args(self, command: str, *options: str) -> list[str]:
        return [
            "--host",
            self.service.config.host,
            "--port",
            str(self.service.config.port),
            *command.split(),
            *options,
        ]

    async def console(
        self,
        capsys: pytest.CaptureFixture[str],
        command: str,
        *options: str,
        code: int = 0,
    ) -> dict[str, Any]:
        count = len(self.requests)
        result = await asyncio.to_thread(_command, _api(), self.args(command, *options))
        stdout, stderr = capsys.readouterr()
        assert result == code, (stdout, stderr)
        record = stdout if code == 0 else stderr
        assert (stderr if code == 0 else stdout) == ""
        assert record.count("\n") == 1 and record.endswith("\n")
        assert len(record[:-1].encode()) <= _LIMIT
        assert len(self.requests) == count + 1 and self.responses[-1].is_closed
        assert self.responses[-1].headers["cache-control"] == "no-store"
        assert self.service.token.decode() not in stdout + stderr
        assert str(self.service.journal_path) not in stdout + stderr
        return dict(json.loads(record))

    async def page(
        self,
        capsys: pytest.CaptureFixture[str],
        *,
        records: int = 10,
        charged: int = 16384,
        cursor: str | None = None,
        code: int = 0,
    ) -> dict[str, Any]:
        options = [
            "--session",
            self.service.run.journal.session_id.value,
            "--max-records",
            str(records),
            "--max-charged-bytes",
            str(charged),
        ]
        if cursor is not None:
            options += ["--cursor", cursor]
        return await self.console(capsys, "evidence page", *options, code=code)


@pytest.mark.asyncio
async def test_t014_actual_auth_cli_preserves_idle_between_read_binary_and_reported_provenance(
    active_evidence_service: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = active_evidence_service
    before, start = await service.run.active()
    bridge = ActiveBridge(service, monkeypatch)
    explicit_status = await bridge.console(capsys, "status")
    session = explicit_status["runtime"]["session_id"]
    assert session == service.run.journal.session_id.value
    first = bytes(range(256)) + b"\0\xff\xfe\r\n"
    await service.run.emit(first, sequence=1, timestamp=11)
    one = await bridge.console(
        capsys, "evidence record", "--session", session, "--sequence", "1"
    )
    assert one["run_id"] == before.run_id.value
    assert one["page"]["outcome"] == "complete"
    assert (
        base64.b64decode(one["page"]["records"][0]["payload_base64"], validate=True)
        == first
    )
    later = b"between-read\0\xff\r\n"
    await service.run.emit(later, sequence=2, timestamp=20)
    page = await bridge.page(capsys)
    records = page["page"]["records"]
    assert [item["sequence"] for item in records] == [0, 1, 2]
    assert [
        base64.b64decode(item["payload_base64"], validate=True)
        for item in records
        if item["kind"] == "rx_bytes"
    ] == [first, later]
    provenance = records[0]["provenance"]
    reported = start.provenance
    assert provenance["connection_id"] == start.connection_id.value
    assert provenance["capabilities"] == sorted(
        v.value for v in reported.capabilities.values
    )
    assert provenance["backend_observation_timestamp_domain"] == {
        "domain_id": reported.backend_observation_timestamp_domain.domain_id,
        "observer": reported.backend_observation_timestamp_domain.observer.value,
        "meaning": "observation",
        "unit": reported.backend_observation_timestamp_domain.unit.value,
        "origin_id": reported.backend_observation_timestamp_domain.origin_id,
    }
    assert provenance["connection_provenance"]["fields"] == [
        {"name": "count", "value": 7},
        {"name": "flag", "value": False},
        {"name": "text", "value": "opaque-é"},
        {"name": "unknown", "value": None},
    ]
    assert (
        service.run.fixture.connection.consumer_calls == 1
        and service.run.recorder.close_calls == 0
    )
    assert service.run.runtime.status() == before
    assert [request.url.raw_path for request in bridge.requests] == [
        b"/v1/observation/status",
        b"/v1/evidence/record",
        b"/v1/evidence/page",
    ]
    for request in bridge.requests:
        assert request.headers["authorization"] == "Bearer " + service.token.decode()


@pytest.mark.asyncio
async def test_t014_manual_continuation_keeps_snapshot_and_capture_live(
    active_evidence_service: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = active_evidence_service
    await service.run.active()
    await service.run.emit(b"first\0", sequence=1, timestamp=11)
    bridge = ActiveBridge(service, monkeypatch)
    first = await bridge.page(capsys, records=1)
    assert first["page"]["truncated"] and first["page"]["snapshot_end_exclusive"] == 2
    await service.run.emit(b"appended-later\xff", sequence=2, timestamp=20)
    second = await bridge.page(capsys, cursor=first["page"]["continuation"])
    assert [r["sequence"] for r in second["page"]["records"]] == [1]
    assert (
        second["page"]["snapshot_end_exclusive"] == 2
        and second["page"]["continuation"] is None
    )
    assert not second["page"]["truncated"]
    newest = await bridge.page(capsys)
    assert [r["sequence"] for r in newest["page"]["records"]] == [0, 1, 2]
    assert len(bridge.requests) == 3 and service.run.recorder.close_calls == 0


@pytest.mark.asyncio
async def test_t014_policy_mismatch_shortage_and_not_found_are_honest_cli_outcomes(
    active_evidence_service: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = active_evidence_service
    before, _ = await service.run.active()
    bridge = ActiveBridge(service, monkeypatch)
    error = await bridge.page(capsys, records=11, code=4)
    assert error == {"error": {"source": "journal", "code": "invalid_input"}}
    error = await bridge.console(
        capsys, "evidence record", "--session", _PRIVATE, "--sequence", "0", code=4
    )
    assert error == {"error": {"source": "evidence", "code": "session_not_associated"}}
    short = await bridge.page(capsys, charged=1)
    assert short["page"]["records"] == [] and short["page"]["outcome"] == "complete"
    assert (
        short["page"]["truncated"] and short["page"]["next_record_required_bytes"] > 1
    )
    absent = await bridge.console(
        capsys,
        "evidence record",
        "--session",
        service.run.journal.session_id.value,
        "--sequence",
        str(_MAX),
    )
    assert absent["page"]["outcome"] == "not_found" and absent["page"]["records"] == []
    assert (
        service.run.runtime.status() == before and service.run.recorder.close_calls == 0
    )
    await service.run.emit(b"after-errors\0", sequence=1, timestamp=11)
    assert len((await bridge.page(capsys))["page"]["records"]) == 2


@pytest.mark.parametrize(
    "fault,source_code",
    [("origin", "origin_rejected"), ("auth", "authentication_required")],
)
@pytest.mark.asyncio
async def test_t014_browser_and_bad_bearer_are_rejected_before_real_source_reads(
    active_evidence_service: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault: str,
    source_code: str,
) -> None:
    service = active_evidence_service
    before, _ = await service.run.active()
    bridge = ActiveBridge(service, monkeypatch, fault=fault)
    response = await bridge.page(capsys, code=4)
    assert response == {"error": {"source": "request", "code": source_code}}
    assert service.queries == [] and service.run.runtime.status() == before
    assert service.run.fixture.connection.consumer_calls == 1


@pytest.mark.asyncio
async def test_t014_detach_retains_identity_but_cannot_reopen_live_only_source(
    active_evidence_service: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = active_evidence_service
    before, _ = await service.run.active()
    bridge = ActiveBridge(service, monkeypatch)
    assert (await bridge.page(capsys))["run_id"] == before.run_id.value
    terminal = await bridge.console(capsys, "detach")
    assert terminal["runtime"]["session_id"] == service.run.journal.session_id.value
    assert (
        terminal["runtime"]["owner_settled"]
        and terminal["runtime"]["recorder_close_confirmed"]
    )
    assert await bridge.page(capsys, code=4) == {
        "error": {"source": "evidence", "code": "read_unavailable"}
    }
    assert service.run.recorder.close_calls == 1 and len(bridge.requests) == 3


@pytest.mark.asyncio
async def test_t014_lost_client_query_does_not_cancel_capture_or_its_owned_read(
    active_evidence_service: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = active_evidence_service
    await service.run.active()
    bridge = ActiveBridge(service, monkeypatch)
    helper = importlib.import_module("tests.integration.test_live_evidence_composition")
    gate = helper.QueryWorkerGate(monkeypatch)
    state = client.DeliveryState()
    task = asyncio.create_task(
        client.exchange_evidence(
            endpoint=context.Endpoint(
                host=service.config.host, port=service.config.port
            ),
            operation="page",
            request_body={
                "session_id": service.run.journal.session_id.value,
                "start_inclusive": None,
                "end_exclusive": None,
                "max_records": 10,
                "max_charged_bytes": 16384,
                "cursor": None,
            },
            credential=context.read_credential(),
            delivery=state,
        )
    )
    try:
        await asyncio.wait_for(gate.entered.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert state.request_outcome == "unknown" and len(bridge.requests) == 1
        assert service.run.recorder.close_calls == 0
        await service.run.fixture.connection.emit_rx(
            b"after-lost-query\0", timestamp=11
        )
        gate.release.set()
        await service.run.commit(1)
        page = await bridge.page(capsys)
        assert [r["sequence"] for r in page["page"]["records"]] == [0, 1]
        assert (
            base64.b64decode(page["page"]["records"][1]["payload_base64"])
            == b"after-lost-query\0"
        )
        assert (
            service.run.fixture.connection.consumer_calls == 1
            and service.run.recorder.close_calls == 0
        )
    finally:
        gate.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.asyncio
async def test_t014_actual_retention_expired_and_partial_reports_survive_cli_delivery(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend_index: int,
) -> None:
    helper = _t014_service_helpers(monkeypatch)
    async with helper.t014_active_service(
        tmp_path, account_home, monkeypatch, backend_index, retained=3
    ) as service:
        await service.run.active()
        for sequence in range(1, 5):
            await service.run.emit(
                bytes([sequence, 0, 255]), sequence=sequence, timestamp=sequence * 10
            )
        bridge = ActiveBridge(service, monkeypatch)
        expired = await bridge.console(
            capsys,
            "evidence record",
            "--session",
            service.run.journal.session_id.value,
            "--sequence",
            "1",
        )
        assert (
            expired["page"]["outcome"] == "expired" and expired["page"]["records"] == []
        )
        partial = await bridge.page(capsys)
        assert partial["page"]["outcome"] == "partial"
        assert partial["page"]["expired_range"] == {
            "start_inclusive": 0,
            "end_exclusive": 2,
        }
        assert partial["page"]["retention_marker"]["discarded_record_count"] == 2
        assert [r["sequence"] for r in partial["page"]["records"]] == [2, 3, 4]
        assert service.run.recorder.close_calls == 0 and len(bridge.requests) == 2


@pytest.mark.asyncio
async def test_t014_reported_loss_and_timestamp_segment_boundaries_cross_actual_cli(
    active_evidence_service: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = active_evidence_service
    _, start = await service.run.active()
    core = _t014_service_helpers(monkeypatch)._t014_core_helpers(monkeypatch)
    loss = start.provenance.loss_observability
    sequence = 1
    if isinstance(loss, core.model.ObserverReportsUartLoss):
        await service.run.fixture.connection.emit_observer_loss(
            cause="overflow", lost_bytes=3, timestamp=7
        )
        await service.run.commit(sequence)
        sequence += 1
    await service.run.emit(b"before-origin\0", sequence=sequence, timestamp=11)
    sequence += 1
    original = start.provenance.backend_observation_timestamp_domain
    new = replace(
        original, domain_id="new-accepted-domain", origin_id="new-accepted-origin"
    )
    await service.run.fixture.connection.reset_timestamp_origin(new)
    await service.run.commit(sequence)
    await service.run.commit(sequence + 1)
    await service.run.emit(b"after-origin\xff", sequence=sequence + 2, timestamp=2)
    bridge = ActiveBridge(service, monkeypatch)
    page = await bridge.page(capsys)
    records = page["page"]["records"]
    losses = [r for r in records if r["kind"] == "observer_loss"]
    if isinstance(loss, core.model.ObserverReportsUartLoss):
        assert len(losses) == 1 and losses[0]["lost_bytes"] == 3
        assert (
            losses[0]["observer_id"] == loss.observer_id
            and losses[0]["scope"] == loss.scope
        )
    else:
        assert losses == []
    starts = [r for r in records if r["kind"] == "segment_started"]
    assert len(starts) == 2
    assert (
        starts[0]["provenance"]["connection_id"]
        == starts[1]["provenance"]["connection_id"]
    )
    assert (
        starts[0]["provenance"]["segment_id"] != starts[1]["provenance"]["segment_id"]
    )
    assert (
        starts[1]["provenance"]["backend_observation_timestamp_domain"]["origin_id"]
        == new.origin_id
    )
    rx = [r for r in records if r["kind"] == "rx_bytes"]
    assert [r["observed_at"] for r in rx] == [
        {"domain_id": original.domain_id, "value": 11},
        {"domain_id": new.domain_id, "value": 2},
    ]
    assert [r["reason"] for r in records if r["kind"] == "segment_ended"] == [
        "timestamp_origin_reset"
    ]
    assert (
        service.run.fixture.connection.consumer_calls == 1
        and service.run.recorder.close_calls == 0
    )


@pytest.mark.asyncio
async def test_t014_production_basic_attach_composition_delivers_active_binary_via_cli(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # This additional path uses the actual Basic preparation, Profile resolver,
    # backend adapter and created journal. Only the serial dependency is fake.
    helper = _t014_service_helpers(monkeypatch)
    helper._t014_core_helpers(monkeypatch)
    basic = importlib.import_module("dutchmate_core.adapters.basic_serial")
    storage = importlib.import_module("dutchmate_core.adapters.sqlite_evidence")
    serial_helpers = importlib.import_module(
        "tests.integration.test_observation_runtime"
    )
    lifecycle = _helpers("test_cli_lifecycle")
    original_init = basic.BasicSerialBackend.__init__
    original_append = storage.SqliteEvidenceJournal.append
    payloads = (bytes(range(256)) + b"\0\xff\r\n", b"after-console-return\0\xfe")
    serial = serial_helpers._GatedSerial(payloads)
    factory = serial_helpers.FakeSerialFactory(serial)
    commits: asyncio.Queue[Any] = asyncio.Queue()
    fixture = inspect.unwrap(lifecycle.lifecycle_service)(
        tmp_path, account_home, monkeypatch
    )
    harness = await anext(fixture)
    try:

        def construct(self: Any, *args: Any, **kwargs: Any) -> None:
            harness.composition.serials.append(serial)
            original_init(self, *args, _serial_factory=factory, **kwargs)

        async def append(self: Any, draft: Any) -> Any:
            record = await original_append(self, draft)
            commits.put_nowait(record)
            return record

        monkeypatch.setattr(basic.BasicSerialBackend, "__init__", construct)
        monkeypatch.setattr(storage.SqliteEvidenceJournal, "append", append)
        lifecycle._bridge(harness, monkeypatch)
        service = harness.service
        service.serving = harness.serving
        service.journal_path = harness.composition.journal_path
        service.run = SimpleNamespace(journal=None)
        bridge = ActiveBridge(service, monkeypatch)
        attached = await bridge.console(
            capsys,
            "attach",
            "--profile",
            str(harness.composition.profile_path),
            "--journal",
            str(harness.composition.journal_path),
        )
        assert attached["runtime"]["state"] == "active"
        assert (await asyncio.wait_for(commits.get(), 3)).sequence == 0
        assert (
            len(harness.composition.journals) == len(harness.composition.serials) == 1
        )
        journal = harness.composition.journals[0]
        service.run.journal = journal
        session = attached["runtime"]["session_id"]
        for index, payload in enumerate(payloads):
            serial.gates[index].set()
            record = await asyncio.wait_for(commits.get(), 3)
            assert record.sequence == index + 1 and record.payload == payload
            report = await bridge.console(
                capsys,
                "evidence record",
                "--session",
                session,
                "--sequence",
                str(index + 1),
            )
            assert (
                base64.b64decode(
                    report["page"]["records"][0]["payload_base64"], validate=True
                )
                == payload
            )
        assert [
            r["sequence"] for r in (await bridge.page(capsys))["page"]["records"]
        ] == [0, 1, 2]
        assert serial.max_active_reads == 1 and serial.close_calls == 0
        assert service.runtime.status().state.value == "active"
        assert len(bridge.requests) == 4
    finally:
        await fixture.aclose()
    assert serial.close_calls == 1 and serial.active_reads == 0


# T023: "Service UTF-8 JSON <=1048576 bytes; CLI JSON <=1048576 bytes plus one LF".
# "Accumulate at most1048577 raw/encoded bytes for overflow detection".


def _t023_token(document: object) -> str:
    return base64.urlsafe_b64encode(_json(document)).decode("ascii").rstrip("=")


def _t023_cursor_cases() -> list[tuple[str, str]]:
    document = {
        "version": 1,
        "session_id": _SESSION,
        "range_start_inclusive": 0,
        "range_end_exclusive": None,
        "snapshot_end_exclusive": 9,
        "next_sequence": 3,
    }
    raw = _json(document)
    cases = [
        ("non-json", "A"),
        ("bad-utf8", base64.urlsafe_b64encode(b"\xff").decode().rstrip("=")),
        ("leading-space", base64.urlsafe_b64encode(b" " + raw).decode().rstrip("=")),
        (
            "utf8-bom",
            base64.urlsafe_b64encode(b"\xef\xbb\xbf" + raw).decode().rstrip("="),
        ),
        (
            "escaped-unicode",
            base64.urlsafe_b64encode(raw.replace("é".encode(), b"\\u00e9"))
            .decode()
            .rstrip("="),
        ),
        ("reversed-keys", _t023_token(dict(reversed(list(document.items()))))),
        (
            "duplicate-key",
            base64.urlsafe_b64encode(raw[:-1] + b',"version":1}').decode().rstrip("="),
        ),
        (
            "nonfinite",
            base64.urlsafe_b64encode(
                raw.replace(b'"next_sequence":3', b'"next_sequence":NaN')
            )
            .decode()
            .rstrip("="),
        ),
        ("extra", _cursor(extra=_PRIVATE)),
        ("version-float", _cursor(version=1.0)),
        ("session-empty", _cursor(session_id="")),
        ("session-not-string", _cursor(session_id=True)),
        ("counter-bool", _cursor(next_sequence=True)),
        ("counter-negative", _cursor(range_start_inclusive=-1)),
        ("counter-overflow", _cursor(snapshot_end_exclusive=_MAX + 1)),
        ("counter-string", _cursor(range_end_exclusive="1")),
    ]
    for key in document:
        cases.append(
            (
                "missing-" + key,
                _t023_token({k: v for k, v in document.items() if k != key}),
            )
        )
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    for session in ("x", "xx", "xxx"):
        canonical = _cursor(session_id=session)
        if len(canonical) % 4 in (2, 3):
            changed = canonical[:-1] + alphabet[alphabet.index(canonical[-1]) + 1]
            assert base64.urlsafe_b64decode(
                changed + "=" * (-len(changed) % 4)
            ) == base64.urlsafe_b64decode(canonical + "=" * (-len(canonical) % 4))
            cases.append(("nonzero-pad-bits", changed))
            break
    return cases


@pytest.mark.parametrize("side", ["input", "response"])
@pytest.mark.parametrize(
    "label,token", _t023_cursor_cases(), ids=[case[0] for case in _t023_cursor_cases()]
)
def test_t023_cursor_input_stays_opaque_but_response_requires_canonical_wire_document(
    side: str,
    label: str,
    token: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if side == "input":
        delivery = Delivery(
            account_home,
            monkeypatch,
            status=422,
            body=_json({"error": {"source": "request", "code": "invalid_request"}}),
        )
        assert delivery.invoke([*_PAGE_ARGS, "--cursor", token]) == 4
        assert tuple(capsys.readouterr()) == (
            "",
            _json({"error": {"source": "request", "code": "invalid_request"}}).decode()
            + "\n",
        )
        assert json.loads(delivery.wire.requests[0].content)["cursor"] == token
    else:
        delivery = Delivery(
            account_home, monkeypatch, body=_json(_report(continuation=token))
        )
        assert delivery.invoke(_PAGE_ARGS) == 5
        output = capsys.readouterr()
        _local(output, "invalid_response", phase="unknown")
        assert _PRIVATE not in output.out + output.err
    assert delivery.reads == ["credential"] and len(delivery.wire.requests) == 1
    assert delivery.wire.stream.closed and delivery.imports == []


@pytest.mark.parametrize("raw_size,status", [(767, 0), (768, 0), (769, 5)])
def test_t023_reply_cursor1024_boundary_preserves_controls_or_rejects_privately(
    raw_size: int,
    status: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = {
        "version": 1,
        "session_id": "",
        "range_start_inclusive": 0,
        "range_end_exclusive": None,
        "snapshot_end_exclusive": 2,
        "next_sequence": 1,
    }
    fill = raw_size - len(_json(document))
    document["session_id"] = "\x01" * (fill // 6) + "x" * (fill % 6)
    assert len(_json(document)) == raw_size
    token = _t023_token(document)
    report = _report(snapshot_end_exclusive=2, continuation=token, truncated=True)
    report["session_id"] = document["session_id"]
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == status
    output = capsys.readouterr()
    if status == 0:
        assert tuple(output) == ((_json(report) + b"\n").decode(), "")
        assert len(token) <= 1024
    else:
        _local(output, "invalid_response", phase="unknown")
        assert len(token) == 1026
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize("device", [False, True], ids=["host-facts", "device-facts"])
@pytest.mark.parametrize("outcome", ["complete", "partial", "expired", "not_found"])
@pytest.mark.parametrize("truncated", [False, True])
def test_t023_binary_provenance_marker_order_and_outcome_are_preserved_without_policy_inference(
    device: bool,
    outcome: str,
    truncated: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _full_report(device)
    # Deliberately wire-valid facts need not satisfy predicates a thin CLI must
    # leave to Core: order, range/outcome, charge and cross-clock comparisons.
    report["page"]["records"] = list(reversed(report["page"]["records"]))
    marker = _with_marker()["page"]["retention_marker"]
    report["page"].update(
        outcome=outcome,
        truncated=truncated,
        continuation=_cursor() if truncated else None,
        retention_marker=marker,
        expired_range={"start_inclusive": 1, "end_exclusive": 3},
        never_existed_range={"start_inclusive": 9, "end_exclusive": 12},
        charged_bytes=1,
        next_record_required_bytes=_MAX,
        snapshot_end_exclusive=9,
    )
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 0
    output = capsys.readouterr()
    assert tuple(output) == ((_json(report) + b"\n").decode(), "")
    assert base64.b64decode(
        json.loads(output.out)["page"]["records"][-3]["payload_base64"], validate=True
    ) == bytes(range(256))
    assert len(delivery.wire.requests) == 1 and delivery.reads == ["credential"]
    assert delivery.imports == []


def _t020_sized_marker_page(size: int, kind: int, device: bool) -> dict[str, Any]:
    monitor_tests = _helpers("test_cli_monitor")
    record = monitor_tests._markers(device=device)[kind]
    if kind == 0:
        record.update(
            condition_base64=base64.b64encode(bytes(range(256))).decode(),
            timeout_ms=4000,
            max_rx_bytes=1048576,
        )
    report = _report(records=[record], snapshot_end_exclusive=9)
    if kind == 0:
        target = record["provenance"]["connection_provenance"]["fields"][-1]
        target["value"] = ""
        key = "value"
    else:
        target, key = report, "run_id"
        target[key] = ""
    fragment = 'é/\\"\n🚀'
    width = len(_json(fragment)) - 2
    remaining = size - len(_json(report))
    target[key] = fragment * (remaining // width) + "x" * (remaining % width)
    assert len(_json(report)) == size
    return report


@pytest.mark.parametrize("size", [_LIMIT, _LIMIT + 1])
@pytest.mark.parametrize("kind", [0, 1], ids=["start", "end"])
@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.parametrize("args", [_RECORD_ARGS, _PAGE_ARGS], ids=["record", "page"])
def test_009_t020_encoded_marker_envelope_limit_and_lf_are_independent_of_policy(
    size: int,
    kind: int,
    device: bool,
    args: list[str],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _t020_sized_marker_page(size, kind, device)
    raw = _json(report)
    cut = raw.index("é".encode()) + 1
    delivery = Delivery(
        account_home,
        monkeypatch,
        chunks=[raw[:cut], raw[cut:]],
        headers=[("Content-Type", "application/json"), ("Content-Length", "0")],
    )
    assert delivery.invoke(args) == (0 if size == _LIMIT else 5)
    if size == _LIMIT:
        stdout, stderr = capsys.readouterr()
        assert stdout.encode() == raw + b"\n" and stderr == ""
        assert len(stdout.encode()) == _LIMIT + 1
    else:
        _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed
    assert delivery.reads == ["credential"] and delivery.imports == []


_T020_BAD_MARKERS: list[tuple[int, tuple[str, ...], Any]] = [
    (0, ("condition_base64",), base64.b64encode(b"x" * 257).decode()),
    (0, ("condition_base64",), "/x=="),
    (0, ("condition_base64",), "//9="),
    (0, ("condition_base64",), False),
    (0, ("clock_origin_id",), None),
    (0, ("timeout_ms",), 0),
    (0, ("max_rx_bytes",), 1048577),
    (1, ("window",), None),
    (1, ("clock",), []),
    (1, ("clock", "decided_at_ns"), True),
    (1, ("clock", "origin_id"), "abcdefab123442348234123456789abc"),
    (1, ("match", "start"), None),
    (1, ("match", "end"), []),
    (1, ("match", "end", "byte_offset_exclusive"), True),
    (1, ("match", "start", "sequence"), _MAX),
    (1, ("observer_loss_records",), _MAX + 1),
    (1, ("operation_kind",), "follow"),
    (1, ("outcome",), False),
]


@pytest.mark.parametrize("index,path,bad", _T020_BAD_MARKERS)
@pytest.mark.parametrize("args", [_RECORD_ARGS, _PAGE_ARGS], ids=["record", "page"])
def test_009_t020_nested_marker_binary_nullability_and_enum_faults_are_private(
    index: int,
    path: tuple[str, ...],
    bad: Any,
    args: list[str],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monitor_tests = _helpers("test_cli_monitor")
    records = monitor_tests._markers()
    records[0]["provenance"]["connection_provenance"]["fields"][-1]["value"] = _PRIVATE
    _at(records[index], path[:-1])[path[-1]] = bad
    report = _report(records=records, snapshot_end_exclusive=9)
    caplog.set_level(logging.DEBUG)
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(args) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed
    assert _PRIVATE not in caplog.text and _TOKEN not in caplog.text


@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.parametrize("args", [_RECORD_ARGS, _PAGE_ARGS], ids=["record", "page"])
def test_009_t020_expired_start_and_rx_do_not_trigger_marker_reconstruction_or_fetch(
    device: bool,
    args: list[str],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    end = _helpers("test_cli_monitor")._markers(device=device)[1]
    report = _with_marker()
    report["page"].update(
        records=[end],
        expired_range={"start_inclusive": 0, "end_exclusive": 8},
        never_existed_range=None,
    )
    report["page"]["retention_marker"].update(
        expired_range={"start_inclusive": 0, "end_exclusive": 8},
        discarded_record_count=8,
    )
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 1
    assert delivery.imports == [] and delivery.reads == ["credential"]


@pytest.mark.parametrize("kind", [0, 1], ids=["start", "end"])
@pytest.mark.parametrize("mode", ["limit", "input-over", "reply-over"])
def test_009_t020_marker_continuations_preserve_cursor_byte_bounds_and_input_opacity(
    kind: int,
    mode: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monitor_tests = _helpers("test_cli_monitor")
    if mode == "input-over":
        api = _api()
        attempts = monitor_tests._block_preparation(api, monkeypatch)
        assert _command(api, [*_PAGE_ARGS, "--cursor", "A" * 1025]) == 2
        _local(capsys.readouterr(), "invalid_arguments")
        assert attempts == []
        return
    document = {
        "version": 1,
        "session_id": "",
        "range_start_inclusive": 0,
        "range_end_exclusive": None,
        "snapshot_end_exclusive": 10,
        "next_sequence": 4 if kind == 0 else 9,
    }
    remaining = 768 - len(_json(document))
    session = "\x01" * (remaining // 6) + "x" * (remaining % 6)
    assert 1 <= len(session.encode()) <= 256
    document["session_id"] = session
    token = base64.urlsafe_b64encode(_json(document)).decode().rstrip("=")
    assert len(token) == 1024
    report = _report(
        records=[monitor_tests._markers()[kind]],
        snapshot_end_exclusive=10,
        truncated=True,
        continuation=token if mode == "limit" else "A" * 1025,
    )
    report["session_id"] = session
    # Input tokens remain opaque: this alphabet/length-valid token is forwarded
    # even though the CLI cannot establish its server-side cursor semantics.
    incoming = "A" * 1024
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    args = [*_PAGE_ARGS, "--session", session, "--cursor", incoming]
    assert delivery.invoke(args) == (0 if mode == "limit" else 5)
    if mode == "limit":
        assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    else:
        _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1 and delivery.imports == []
    assert json.loads(delivery.wire.requests[0].content)["cursor"] == incoming


@pytest.mark.parametrize(
    "field,value",
    [
        ("lost_bytes", 0),
        ("lost_bytes", -1),
        ("lost_bytes", True),
        ("lost_bytes", 1.0),
        ("lost_bytes", "1"),
        ("timestamp", True),
        ("timestamp", -1),
        ("timestamp", _MAX + 1),
        ("timestamp", 1.0),
        ("timestamp", None),
        ("marker", True),
        ("marker", -1),
        ("required", 0),
        ("required", False),
    ],
)
def test_t023_corrupt_counter_or_nullable_positive_field_is_private_invalid_response(
    field: str,
    value: Any,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _full_report()
    if field == "lost_bytes":
        report["page"]["records"][4]["lost_bytes"] = value
    elif field == "timestamp":
        report["page"]["records"][1]["observed_at"]["value"] = value
    elif field == "marker":
        report["page"]["retention_marker"] = _with_marker()["page"]["retention_marker"]
        report["page"]["retention_marker"]["discarded_record_count"] = value
    else:
        report["page"]["next_record_required_bytes"] = value
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 5
    output = capsys.readouterr()
    _local(output, "invalid_response", phase="unknown")
    assert _TOKEN not in output.out + output.err and len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "payload,want",
    [
        (b"\xff", "/w=="),
        (b"\xfb\xff", "+/8="),
        (b"\xfb\xff\xfe", "+//+"),
        (b"\0\xff\xfe\r\n", "AP/+DQo="),
        (bytes(range(256)), None),
    ],
)
def test_t023_exact_binary_quanta_and_standard_pad_bits_round_trip_without_text_decoding(
    payload: bytes,
    want: str | None,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report(records=[_rx(payload)])
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_RECORD_ARGS) == 0
    stdout, stderr = capsys.readouterr()
    assert stderr == "" and stdout.encode() == _json(report) + b"\n"
    encoded = json.loads(stdout)["page"]["records"][0]["payload_base64"]
    assert encoded == (want if want is not None else base64.b64encode(payload).decode())
    assert base64.b64decode(encoded, validate=True) == payload
    assert len(delivery.wire.requests) == 1


def _t023_sized_report(size: int) -> dict[str, Any]:
    report = _full_report()
    field = report["page"]["records"][0]["provenance"]["connection_provenance"][
        "fields"
    ][-1]
    field["value"] = ""
    fragment = 'é/\\"\n😀'
    fill = size - len(_json(report))
    charge = len(_json(fragment)) - 2
    field["value"] = fragment * (fill // charge) + "x" * (fill % charge)
    assert len(_json(report)) == size
    return report


@pytest.mark.parametrize("size,code", [(1048575, 0), (1048576, 0), (1048577, 5)])
@pytest.mark.parametrize("declared", ["0", "9999999"])
def test_t023_raw_utf8_and_escaped_metadata_bound_is_independent_of_declared_length_and_charge(
    size: int,
    code: int,
    declared: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _t023_sized_report(size)
    report["page"]["charged_bytes"] = 1  # Charge is unrelated to wire length.
    raw = _json(report)
    # Replacing four-digit charge4242 with1 reduces by3; restore exact raw cap with
    # JSON whitespace (not output metadata) to keep transport/output independent.
    raw += b" " * (size - len(raw))
    delivery = Delivery(
        account_home,
        monkeypatch,
        chunks=[raw[:19], raw[19:]],
        headers=[("Content-Type", "application/json"), ("Content-Length", declared)],
    )
    assert delivery.invoke(_PAGE_ARGS) == code
    output = capsys.readouterr()
    if code == 0:
        assert tuple(output) == ((_json(report) + b"\n").decode(), "")
        assert len(output.out.encode()) <= 1048577
    else:
        _local(output, "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed


@pytest.mark.parametrize(
    "size,allowed", [(1048575, True), (1048576, True), (1048577, False)]
)
def test_t023_output_json_bound_plus_one_lf_is_checked_independently(
    size: int, allowed: bool
) -> None:
    report = _t023_sized_report(size)
    api = importlib.import_module("dutchmate_cli.client")
    if allowed:
        output = api._encode_record(report)
        assert output == _json(report) + b"\n"
        assert len(output) == size + 1
    else:
        with pytest.raises(api.CliFailure) as caught:
            api._encode_record(report)
        assert caught.value.kind.value == "invalid_response"
        code, error = api.local_failure(
            caught.value.kind, api.DeliveryState(request_outcome="report_received")
        )
        assert code == 5 and _PRIVATE.encode() not in error
        assert json.loads(error)["request_outcome"] == "report_received"


@pytest.mark.parametrize("encoded", ["Zh==", "Zm9=", "_w==", "/w==\n"])
def test_t023_corrupt_binary_representation_never_echoes_or_repairs_payload(
    encoded: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report()
    report["page"]["records"][0]["payload_base64"] = encoded
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_RECORD_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed


@pytest.mark.parametrize("lost,timestamp", [(None, 0), (1, _MAX), (_MAX, 0)])
def test_t023_positive_or_null_loss_and_nonnegative_timestamp_extremes_remain_wire_facts(
    lost: int | None,
    timestamp: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _full_report(True)
    report["page"]["records"][4]["lost_bytes"] = lost
    report["page"]["records"][4]["observed_at"]["value"] = timestamp
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 1


def test_t023_raw_overflow_accumulates_only_detection_byte_and_stops_before_later_chunks(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # "Accumulate at most1048577 raw/encoded bytes for overflow detection".
    high_water: list[int] = []

    class ObservedAccumulator(bytearray):
        def extend(self, part: Any) -> None:
            assert len(self) + len(part) <= 1048577
            super().extend(part)
            high_water.append(len(self))

    monkeypatch.setattr(client, "bytearray", ObservedAccumulator, raising=False)
    delivery = Delivery(
        account_home,
        monkeypatch,
        chunks=[b" " * 8, b" " * (_LIMIT * 3), _PRIVATE.encode()],
    )
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert max(high_water) == 1048577
    assert delivery.wire.stream.yielded == 2 and delivery.wire.stream.closed
    assert len(delivery.wire.requests) == 1


def test_t023_remote413_has_no_automatic_retry_and_user_smaller_budget_keeps_opaque_cursor(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    token = _cursor()
    first = _report(snapshot_end_exclusive=9, continuation=token, truncated=True)
    delivery = Delivery(account_home, monkeypatch, body=_json(first))
    assert delivery.invoke(_PAGE_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(first) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 1
    first_stream = delivery.wire.stream
    rejected = {"error": {"source": "evidence", "code": "delivery_too_large"}}
    stream_type = _helpers("test_cli_transport")._Stream
    delivery.wire.status = 413
    delivery.wire.stream = stream_type([_json(rejected)])
    assert delivery.invoke([*_PAGE_ARGS, "--cursor", token]) == 4
    assert tuple(capsys.readouterr()) == ("", (_json(rejected) + b"\n").decode())
    assert len(delivery.wire.requests) == 2 and delivery.wire.stream.closed
    second_stream = delivery.wire.stream
    delivered = _report(
        records=[_rx(b"manual continuation\0\xff", sequence=3)],
        snapshot_end_exclusive=9,
        continuation=_cursor(next_sequence=4),
        truncated=True,
        charged_bytes=511,
    )
    delivery.wire.status = 200
    delivery.wire.stream = stream_type([_json(delivered)])
    assert (
        delivery.invoke(
            [
                *_PAGE_ARGS,
                "--cursor",
                token,
                "--max-records",
                "1",
                "--max-charged-bytes",
                "512",
            ]
        )
        == 0
    )
    assert tuple(capsys.readouterr()) == ((_json(delivered) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 3 and delivery.reads == ["credential"] * 3
    assert all(
        stream.closed for stream in (first_stream, second_stream, delivery.wire.stream)
    )
    requests = [json.loads(request.content) for request in delivery.wire.requests]
    assert (
        requests[0]["cursor"] is None
        and requests[1]["cursor"] == requests[2]["cursor"] == token
    )
    assert (
        requests[1]["max_records"] == 32 and requests[1]["max_charged_bytes"] == 65536
    )
    assert requests[2] == {
        "session_id": _SESSION,
        "start_inclusive": None,
        "end_exclusive": None,
        "max_records": 1,
        "max_charged_bytes": 512,
        "cursor": token,
    }
    assert all(
        request.url.raw_path == b"/v1/evidence/page" and request.method == "POST"
        for request in delivery.wire.requests
    )
    assert delivery.imports == []


def _t012_annotation(**changes: Any) -> dict[str, Any]:
    """010's additive wire record; no Core or production validator dependency."""
    return {
        "kind": "client_annotation",
        "sequence": 0,
        "assertion_class": "client_assertion",
        "client_surface": "core",
        "attribution_basis": "client_asserted",
        "clock_origin_id": "abcdefab-1234-4234-8234-123456789abc",
        "received_at_ns": 100,
        "text": " external flash asserted; e\u0301\r\n\t ",
        **changes,
    }


@pytest.mark.parametrize("args", [_RECORD_ARGS, _PAGE_ARGS], ids=["record", "page"])
@pytest.mark.parametrize("surface", ["cli", "http", "core"])
@pytest.mark.parametrize(
    "sequence,received,text", [(0, 0, " "), (_MAX - 1, _MAX, "é" * 512)]
)
def test_010_t012_annotation_record_all_surfaces_and_counter_edges_are_wire_facts(
    args: list[str],
    surface: str,
    sequence: int,
    received: int,
    text: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record = _t012_annotation(
        sequence=sequence, client_surface=surface, received_at_ns=received, text=text
    )
    report = _report(
        records=[record], snapshot_end_exclusive=sequence + 1, charged_bytes=321
    )
    reversed_report = _helpers("test_cli_monitor")._reverse_objects(report)
    delivery = Delivery(account_home, monkeypatch, body=_json(reversed_report))
    assert delivery.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 1
    assert delivery.reads == ["credential"] and delivery.imports == []


@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced-shaped"])
def test_010_t012_annotation_and_old_six_variants_share_an_unchanged_page(
    device: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _full_report(device)
    records = report["page"]["records"]
    start, end = _helpers("test_cli_monitor")._markers("timeout", device=device)
    first = len(records)
    start["sequence"], end["sequence"], end["start_sequence"] = first, first + 1, first
    end["window"] = {"start_inclusive": first + 1, "end_exclusive": first + 1}
    records.extend((start, end, _t012_annotation(sequence=first + 2)))
    report["page"]["snapshot_end_exclusive"] = len(records)
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize("key", list(_t012_annotation()))
@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_010_t012_annotation_variant_is_closed_and_never_defaults_fields(
    key: str,
    mutation: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record = _t012_annotation()
    if mutation == "missing":
        del record[key]
    else:
        record["unexpected-" + key] = _PRIVATE
    delivery = Delivery(
        account_home, monkeypatch, body=_json(_report(records=[record]))
    )
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize(
    "key,bad",
    [
        ("assertion_class", "dut_observation"),
        ("attribution_basis", "verified"),
        ("client_surface", "CORE"),
        ("client_surface", None),
        ("clock_origin_id", "ABCDEFAB-1234-4234-8234-123456789ABC"),
        ("clock_origin_id", "abcdefab123442348234123456789abc"),
        ("clock_origin_id", "not-a-uuid"),
        ("received_at_ns", True),
        ("received_at_ns", -1),
        ("received_at_ns", _MAX + 1),
        ("sequence", True),
        ("sequence", _MAX),
        ("text", ""),
        ("text", "\0"),
        ("text", "é" * 513),
        ("text", True),
    ],
)
def test_010_t012_annotation_types_literals_host_uuid_and_bounds_are_strict(
    key: str,
    bad: object,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report(records=[_t012_annotation(**{key: bad})])
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1
