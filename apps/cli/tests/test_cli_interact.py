"""012 T018 RED: real CLI over independent bounded Interact wire facts.

Only credential/HTTP/output/time boundaries are controlled. No Core matcher,
coordinator, service projector or future CLI validator supplies expectations.
"""

import asyncio
import base64
import importlib
import logging
import socket
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
import typer

_evidence = importlib.import_module("test_cli_evidence")
_commands = importlib.import_module("test_cli_commands")
_monitor = importlib.import_module("test_cli_monitor")
_json = _evidence._json
_SESSION = "session-é"
_OPERATION = "12345678-1234-4234-8234-123456789abc"
_ORIGIN = "abcdefab-1234-4234-8234-123456789abc"
_PRIVATE = _evidence._PRIVATE
_TOKEN = _evidence._TOKEN
_LIMIT = 1048576
_MAX = 9223372036854775807
_BODY = {
    "session_id": _SESSION,
    "payload_base64": "AP9TRU5E",
    "conditions_base64": ["UEFTUw==", "RkFJTA=="],
    "timeout_ms": 1000,
    "max_rx_bytes": 4,
}
_ARGS = [
    "--api-version",
    "2",
    "--port",
    "8765",
    "interact",
    "--session",
    _SESSION,
    "--payload-base64",
    "AP9TRU5E",
    "--condition-base64",
    "UEFTUw==",
    "--condition-base64",
    "RkFJTA==",
    "--timeout-ms",
    "1000",
    "--max-rx-bytes",
    "4",
]
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
    "cancelled",
    "write_timeout",
    "partial_write",
)
_MISSING = (
    (),
    ("uart_tx_settled",),
    ("interact_ended",),
    ("uart_tx_settled", "interact_ended"),
)


def report(
    outcome: str = "matched",
    *,
    device: bool = False,
    missing: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Literal public contract; backend acceptance never means wire/DUT receipt."""
    failed = outcome in {"write_timeout", "partial_write"}
    provenance = _evidence._full_report(device)["page"]["records"][0]["provenance"]
    provenance["capabilities"] = (
        ["gpio_control", "uart_receive", "uart_send"]
        if device
        else ["uart_receive", "uart_send"]
    )
    return {
        "run_id": "run-é",
        "session_id": _SESSION,
        "operation_id": _OPERATION,
        "provenance": {
            **provenance,
            "boundary_basis": "core_observation_order",
            "causation": "not_established",
        },
        "payload_base64": "AP9TRU5E",
        "conditions_base64": ["UEFTUw==", "RkFJTA=="],
        "outcome": outcome,
        "started_record": {"session_id": _SESSION, "sequence": 3},
        "tx_settled_record": None
        if "uart_tx_settled" in missing
        else {
            "session_id": _SESSION,
            "sequence": 6,
        },
        "ended_record": None
        if "interact_ended" in missing
        else {
            "session_id": _SESSION,
            "sequence": 7,
        },
        "tx": {
            "submitted": True,
            "status": "timeout"
            if outcome == "write_timeout"
            else "partial"
            if failed
            else "acknowledged",
            "accepted_prefix_bytes": None
            if outcome == "write_timeout"
            else 3
            if failed
            else 6,
            "failure_code": None,
            "acknowledgement_scope": "backend_acceptance",
            "clock_origin_id": _ORIGIN,
            "settled_at_ns": 103,
        },
        "observation": {
            "window": {
                "start_inclusive": 4,
                "end_exclusive": 6 if outcome in {"matched", "byte_limit"} else 4,
            },
            "outcome": "tx_failed" if failed else outcome,
            "examined_rx_bytes": 4 if outcome in {"matched", "byte_limit"} else 0,
            "observer_loss_records": 0,
            "match": {
                "condition_index": 0,
                "start": {"sequence": 4, "byte_offset": 0},
                "end": {"sequence": 4, "byte_offset_exclusive": 4},
            }
            if outcome == "matched"
            else None,
            "clock": {
                "origin_id": _ORIGIN,
                "started_at_ns": 100,
                "deadline_at_ns": 1000000100,
                "decided_at_ns": 1000000100 if outcome == "timeout" else 102,
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


def delivery(
    home: Path, patch: pytest.MonkeyPatch, value: Any = None, **kw: Any
) -> Any:
    return _evidence.Delivery(
        home, patch, body=_json(report() if value is None else value), **kw
    )


def recognized(patch: pytest.MonkeyPatch) -> None:
    """An unknown command/option must not pass a negative-input assertion."""
    api = _evidence._api()
    attempts = _commands._block_preparation(api, patch)
    result = _commands._runner(api, ["--api-version", "2", "interact", "--help"])
    assert result.exit_code == 0, "T019 explicit-v2 Interact grammar is absent"
    assert result.exception is None and result.stderr == ""
    assert "--payload-base64" in result.stdout and attempts == []


@pytest.mark.parametrize(
    "args",
    [
        ["interact", "--help"],
        ["--api-version", "2", "interact", "--help"],
        ["--host", _PRIVATE, "--port", "0", "interact", "--help"],
    ],
)
@pytest.mark.parametrize("unsupported", [False, True])
def test_interact_help_is_resource_free_and_has_only_explicit_byte_grammar(
    args: list[str],
    unsupported: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _evidence._api()
    attempts = _commands._block_preparation(api, monkeypatch)
    if unsupported:
        monkeypatch.setattr(sys, "platform", "win32")
    result = _commands._runner(api, args)
    assert result.exit_code == 0 and result.exception is None and not result.stderr
    for option in (
        "--session",
        "--payload-base64",
        "--condition-base64",
        "--timeout-ms",
        "--max-rx-bytes",
    ):
        assert option in result.stdout
    for option in (
        "--file",
        "--stdin",
        "--text",
        "--regex",
        "--line-ending",
        "--write-timeout",
        "--token",
        "--retry",
        "--detach",
        _PRIVATE,
    ):
        assert option not in result.stdout
    assert attempts == []


_BAD_ARGS: list[list[str]] = []
for _option in (
    "--session",
    "--payload-base64",
    "--condition-base64",
    "--timeout-ms",
    "--max-rx-bytes",
):
    # Remove *all* condition occurrences; other scalar options occur once.
    _args = list(_ARGS)
    while _option in _args:
        _index = _args.index(_option)
        del _args[_index : _index + 2]
    _BAD_ARGS.append(_args)
for _option, _values in (
    ("--session", ("", "a\0b", "x" * 257, "é" * 129)),
    (
        "--payload-base64",
        (
            "",
            "AA",
            "AB==",
            "AA===",
            "AA==\n",
            "_w==",
            "-w==",
            "é",
            base64.b64encode(b"x" * 4097).decode(),
        ),
    ),
    (
        "--condition-base64",
        (
            "",
            "AA",
            "AB==",
            "//9=",
            "AA==\n",
            "_w==",
            base64.b64encode(b"x" * 257).decode(),
        ),
    ),
    ("--timeout-ms", ("0", "-1", "4001", "true", "1.0", "1e0", _PRIVATE)),
    ("--max-rx-bytes", ("0", "-1", "1048577", "false", "1.0", "1e0", _PRIVATE)),
):
    for _value in _values:
        _args = list(_ARGS)
        _args[_args.index(_option) + 1] = _value
        _BAD_ARGS.append(_args)
_BAD_ARGS += [
    [
        *_ARGS,
        "--condition-base64",
        "AA==",
        "--condition-base64",
        "AA==",
        "--condition-base64",
        "AA==",
    ],  # five conditions, duplicates still count
    _ARGS[2:],
    ["--api-version", "1", *_ARGS[2:]],
    ["--api-version", "2", *_ARGS[4:]],
]
for _option in (
    "--file",
    "--stdin",
    "--text",
    "--regex",
    "--line-ending",
    "--write-timeout",
    "--tx-only",
    "--start",
    "--retry",
    "--detach",
):
    _BAD_ARGS.append([*_ARGS, _option, _PRIVATE])


@pytest.mark.parametrize("args", _BAD_ARGS)
def test_bad_base64_bounds_missing_options_and_v1_fail_before_credentials(
    args: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    recognized(monkeypatch)
    api = _evidence._api()
    attempts = _commands._block_preparation(api, monkeypatch)
    assert _evidence._command(api, args) == 2
    _evidence._local(capsys.readouterr(), "invalid_arguments")
    assert attempts == [] and _PRIVATE not in caplog.text


@pytest.mark.parametrize("outcome", _OUTCOMES)
@pytest.mark.parametrize("missing", _MISSING)
@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
def test_each_delivered_outcome_and_audit_combination_is_exit_zero_without_wire_claims(
    outcome: str,
    missing: tuple[str, ...],
    device: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = report(outcome, device=device, missing=missing)
    d = delivery(account_home, monkeypatch, _monitor._reverse_objects(value))
    assert d.invoke(_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(value) + b"\n").decode(), "")
    d.one_request("/v2/observation/interact", _BODY)
    assert d.wire.requests[0].content == _json(_BODY)


@pytest.mark.parametrize("host,port", [("127.0.0.1", 1), ("::1", 65535)])
@pytest.mark.parametrize(
    "session,payload,conditions,timeout,maximum",
    [
        (" ", b"\0", [b"\xff"], 1, 1),
        ("é" * 128, bytes(range(256)) * 16, [bytes(range(256))] * 4, 4000, 1048576),
        ('"\\\n' * 85 + "x", b"\xff\r\n", [b"FAIL", b"PASS", b"FAIL"], 1, 1048576),
    ],
)
def test_legal_edges_preserve_binary_payload_order_duplicates_and_one_request(
    host: str,
    port: int,
    session: str,
    payload: bytes,
    conditions: list[bytes],
    timeout: int,
    maximum: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    encoded = base64.b64encode(payload).decode()
    literals = [base64.b64encode(item).decode() for item in conditions]
    value = report("detached")
    value.update(session_id=session, payload_base64=encoded, conditions_base64=literals)
    for key in ("started_record", "tx_settled_record", "ended_record"):
        value[key]["session_id"] = session
    value["tx"]["accepted_prefix_bytes"] = len(payload)
    value["observation"]["clock"]["deadline_at_ns"] = 100 + timeout * 1000000
    expected = dict(
        session_id=session,
        payload_base64=encoded,
        conditions_base64=literals,
        timeout_ms=timeout,
        max_rx_bytes=maximum,
    )
    args = [
        "--api-version",
        "2",
        "--host",
        host,
        "--port",
        str(port),
        "interact",
        "--session",
        session,
        "--payload-base64",
        encoded,
    ]
    for condition in literals:
        args += ["--condition-base64", condition]
    args += ["--timeout-ms", str(timeout), "--max-rx-bytes", str(maximum)]
    d = delivery(account_home, monkeypatch, value)
    assert d.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((_json(value) + b"\n").decode(), "")
    d.one_request("/v2/observation/interact", expected, host=host, port=port)
    assert d.wire.requests[0].content == _json(expected)
    assert len(d.wire.requests[0].content) <= 16384


@pytest.mark.parametrize(
    "overall",
    [
        "partial_write",
        "write_timeout",
        "disconnected",
        "transport_failure",
        "cancelled",
        "service_stopping",
    ],
)
def test_early_frozen_match_survives_a_later_write_or_external_failure(
    overall: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = report(overall)
    value["observation"] = report()["observation"]
    if overall == "transport_failure":
        value["tx"].update(
            status="failure",
            accepted_prefix_bytes=None,
            failure_code="internal_contract_failure",
        )
    d = delivery(account_home, monkeypatch, value)
    assert d.invoke(_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(value) + b"\n").decode(), "")
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize("condition_index", [0, 1])
def test_reported_condition_index_is_preserved_without_client_matching(
    condition_index: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = report()
    value["observation"]["match"]["condition_index"] = condition_index
    d = delivery(account_home, monkeypatch, value)
    assert d.invoke(_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(value) + b"\n").decode(), "")
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize("outcome", ["matched", "timeout"])
def test_late_ack_does_not_move_the_observation_boundary_or_rewrite_frozen_facts(
    outcome: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = report(outcome)
    value["tx"]["settled_at_ns"] = 1000000101
    d = delivery(account_home, monkeypatch, value)
    assert d.invoke(_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(value) + b"\n").decode(), "")
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize(
    "status,count,code,overall,observation",
    [
        ("not_submitted", None, None, "cancelled", "cancelled"),
        ("not_submitted", None, None, "service_stopping", "service_stopping"),
        ("partial", 0, None, "partial_write", "tx_failed"),
        ("partial", 5, None, "partial_write", "tx_failed"),
        ("timeout", None, None, "write_timeout", "timeout"),
        ("disconnected", None, None, "disconnected", "disconnected"),
        ("failure", None, "io_failure", "transport_failure", "tx_failed"),
        (
            "failure",
            None,
            "internal_contract_failure",
            "transport_failure",
            "tx_failed",
        ),
    ],
)
def test_suppressed_partial_and_unknown_counts_are_not_invented_or_retried(
    status: str,
    count: int | None,
    code: str | None,
    overall: str,
    observation: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = report("cancelled")
    value["outcome"] = overall
    value["tx"].update(
        submitted=status != "not_submitted",
        status=status,
        accepted_prefix_bytes=count,
        failure_code=code,
    )
    value["observation"]["outcome"] = observation
    if observation == "timeout":
        value["observation"]["clock"]["decided_at_ns"] = 1000000100
        value["tx"]["settled_at_ns"] = 1000000101
    d = delivery(account_home, monkeypatch, value)
    assert d.invoke(_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(value) + b"\n").decode(), "")
    d.one_request("/v2/observation/interact", _BODY)


_BAD_REPORTS: list[tuple[tuple[str, ...], Any]] = [
    (("run_id",), ""),
    (("session_id",), "other-session"),
    (("operation_id",), _OPERATION.upper()),
    (("payload_base64",), "QQ=="),
    (("conditions_base64",), ["RkFJTA==", "UEFTUw=="]),
    (("outcome",), "success"),
    (("outcome",), "tx_failed"),
    (("provenance", "boundary_basis"), "physical_wire"),
    (("provenance", "causation"), "established"),
    (("started_record",), None),
    (("started_record", "session_id"), "other"),
    (("started_record", "sequence"), True),
    (("started_record", "sequence"), _MAX),
    (("tx_settled_record", "sequence"), 3),
    (("ended_record", "sequence"), 6),
    (("tx_settled_record", "session_id"), "other"),
    (("ended_record", "session_id"), "other"),
    (("tx", "submitted"), 1),
    (("tx", "status"), "not_submitted"),
    (("tx", "accepted_prefix_bytes"), 5),
    (("tx", "accepted_prefix_bytes"), True),
    (("tx", "accepted_prefix_bytes"), None),
    (("tx", "failure_code"), "transport_failure"),
    (("tx", "acknowledgement_scope"), "wire_transmission"),
    (("tx", "clock_origin_id"), _OPERATION),
    (("tx", "settled_at_ns"), 99),
    (("tx", "settled_at_ns"), _MAX + 1),
    (("observation", "outcome"), "tx_failed"),
    (("observation", "window", "start_inclusive"), 3),
    (("observation", "window", "end_exclusive"), 8),
    (("observation", "examined_rx_bytes"), 3),
    (("observation", "examined_rx_bytes"), 5),
    (("observation", "observer_loss_records"), -1),
    (("observation", "match"), None),
    (("observation", "match", "condition_index"), 2),
    (("observation", "match", "condition_index"), True),
    (("observation", "match", "start", "sequence"), 3),
    (("observation", "match", "end", "byte_offset_exclusive"), 3),
    (("observation", "clock", "origin_id"), _OPERATION),
    (("observation", "clock", "started_at_ns"), True),
    (("observation", "clock", "deadline_at_ns"), 100),
    (("observation", "clock", "deadline_at_ns"), 1000000101),
    (("observation", "clock", "decided_at_ns"), 99),
    (("observation", "clock", "decided_at_ns"), 1000000100),
    (("durability",), "both_unconfirmed"),
    (
        ("audit_failures",),
        [{"record_kind": "uart_tx_settled", "source": "journal", "code": "busy"}],
    ),
]


@pytest.mark.parametrize("path,bad", _BAD_REPORTS)
def test_inconsistent_identities_refs_tx_observation_and_audit_discard_whole_report(
    path: tuple[str, ...],
    bad: Any,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    value = report()
    _evidence._at(value, path[:-1])[path[-1]] = bad
    value["provenance"]["connection_provenance"]["fields"][-1]["value"] = _PRIVATE
    d = delivery(account_home, monkeypatch, value)
    caplog.set_level(logging.DEBUG)
    assert d.invoke(_ARGS) == 5
    _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    d.one_request("/v2/observation/interact", _BODY)
    assert _PRIVATE not in caplog.text and _TOKEN not in caplog.text


_CLOSED_PATHS = [
    (),
    ("provenance",),
    ("started_record",),
    ("tx_settled_record",),
    ("ended_record",),
    ("tx",),
    ("observation",),
    ("observation", "window"),
    ("observation", "match"),
    ("observation", "match", "start"),
    ("observation", "match", "end"),
    ("observation", "clock"),
]
_REQUIRED_FIELDS = [
    (path, key) for path in _CLOSED_PATHS for key in _evidence._at(report(), path)
]


@pytest.mark.parametrize("path,key", _REQUIRED_FIELDS)
def test_every_required_report_field_is_required_even_when_null(
    path: tuple[str, ...],
    key: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = report()
    del _evidence._at(value, path)[key]
    d = delivery(account_home, monkeypatch, value)
    assert d.invoke(_ARGS) == 5
    _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize("path", _CLOSED_PATHS)
def test_unknown_fields_cannot_smuggle_wire_success_or_private_diagnostics(
    path: tuple[str, ...],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = report()
    _evidence._at(value, path)["dut_received"] = _PRIVATE
    d = delivery(account_home, monkeypatch, value)
    assert d.invoke(_ARGS) == 5
    _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_durability",
        "missing_failure",
        "reversed",
        "duplicate",
        "extra",
        "wrong_kind",
        "wrong_source",
        "wrong_code",
        "extra_field",
        "missing_code",
    ],
)
def test_missing_audit_acknowledgements_have_exact_ordered_closed_failures(
    fault: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = report(missing=_MISSING[-1])
    failures = value["audit_failures"]
    match fault:
        case "wrong_durability":
            value["durability"] = "complete"
        case "missing_failure":
            failures.pop()
        case "reversed":
            failures.reverse()
        case "duplicate":
            failures[1] = dict(failures[0])
        case "extra":
            failures.append(dict(failures[0]))
        case "wrong_kind":
            failures[0]["record_kind"] = "interact_started"
        case "wrong_source":
            failures[0]["source"] = "backend"
        case "wrong_code":
            failures[0]["code"] = "unknown"
        case "extra_field":
            failures[0]["detail"] = _PRIVATE
        case "missing_code":
            del failures[0]["code"]
    d = delivery(account_home, monkeypatch, value)
    assert d.invoke(_ARGS) == 5
    _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    d.one_request("/v2/observation/interact", _BODY)


_ERRORS = [
    (404, "interact", "no_associated_session"),
    *[
        (409, "interact", c)
        for c in (
            "session_not_associated",
            "not_active",
            "busy",
            "policy_denied",
            "capability_unavailable",
        )
    ],
    (503, "interact", "interact_unavailable"),
    (422, "interact", "evidence_policy_incompatible"),
    (503, "service", "interact_capacity"),
    (503, "service", "stopping"),
    (409, "request", "unsupported_api_version"),
    (413, "interact", "delivery_too_large"),
    *_evidence._helpers("test_cli_transport")._REMOTE_ERRORS,
]
_ERRORS += [
    (
        {
            "invalid_input": 422,
            "session_mismatch": 409,
            "journal_missing": 404,
            "busy": 503,
            "closed": 409,
        }.get(c, 500),
        "journal",
        c,
    )
    for c in _monitor._JOURNAL_CODES
]


@pytest.mark.parametrize("status,source,code", _ERRORS)
def test_known_remote_rejections_including_413_are_private_finite_and_never_retried(
    status: int,
    source: str,
    code: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = {"error": {"source": source, "code": code}}
    d = delivery(account_home, monkeypatch, value, status=status)
    assert d.invoke(_ARGS) == 4
    assert tuple(capsys.readouterr()) == ("", (_json(value) + b"\n").decode())
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize(
    "raw,status",
    [
        (b"null", 200),
        (b"\xff", 200),
        (b"{} trailing", 200),
        (_json(report())[:-1] + b',"outcome":"matched"}', 200),
        (_json(report()).replace(b'"settled_at_ns":103', b'"settled_at_ns":NaN'), 200),
        (b'{"error":{"source":"interact","code":"busy","detail":"private"}}', 409),
        (b'{"error":{"source":"interact","code":"busy"}}', 413),
        (b'{"error":{"source":"request","code":"unsupported_api_version"}}', 400),
        (b'{"error":{"source":"interact","code":"unknown"}}', 500),
    ],
)
def test_malformed_json_or_wrong_error_status_never_prints_partial_facts(
    raw: bytes,
    status: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = _evidence.Delivery(account_home, monkeypatch, body=raw, status=status)
    assert d.invoke(_ARGS) == 5
    _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize("size", [_LIMIT, _LIMIT + 1])
def test_raw_response_cap_counts_actual_chunks_instead_of_content_length(
    size: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = _json(report())
    raw += b" " * (size - len(raw))
    d = _evidence.Delivery(
        account_home,
        monkeypatch,
        chunks=[raw[:13], raw[13:]],
        headers=[("Content-Type", "application/json"), ("Content-Length", "1")],
    )
    assert d.invoke(_ARGS) == (0 if size == _LIMIT else 5)
    if size == _LIMIT:
        assert tuple(capsys.readouterr()) == ((_json(report()) + b"\n").decode(), "")
    else:
        _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize(
    "failure,exit_code,kind",
    [
        (httpx.ConnectError(_PRIVATE), 5, "transport_failed"),
        (httpx.ReadTimeout(_PRIVATE), 5, "request_timeout"),
        (httpx.RemoteProtocolError(_PRIVATE), 5, "invalid_response"),
        (RuntimeError(_PRIVATE), 1, "internal_failure"),
    ],
)
def test_transport_failure_has_unknown_receipt_and_no_poll_retry_or_detach(
    failure: Exception,
    exit_code: int,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    d = delivery(account_home, monkeypatch, failure=failure)
    caplog.set_level(logging.DEBUG)
    assert d.invoke(_ARGS) == exit_code
    _evidence._local(capsys.readouterr(), kind, phase="unknown")
    # The peer raised before returning a response; its unused stream was never
    # acquired by HTTPX. The client must close its transport, not an unknown peer
    # resource. Assert the actual authenticated request and ownership instead.
    assert d.reads == ["credential"] and d.imports == []
    assert len(d.wire.requests) == 1
    request = d.wire.requests[0]
    assert (
        request.method == "POST" and request.url.raw_path == b"/v2/observation/interact"
    )
    assert request.content == _json(_BODY)
    assert request.headers.get_list("authorization") == ["Bearer " + _TOKEN]
    assert request.headers.get_list("accept-encoding") == ["identity"]
    assert all(transport.closed for transport in d.wire.transports)
    assert d.wire.stream.yielded == 0
    assert _PRIVATE not in caplog.text and _TOKEN not in caplog.text


@pytest.mark.parametrize("submitted", [False, True])
@pytest.mark.parametrize("failure", [KeyboardInterrupt(_PRIVATE), typer.Abort()])
def test_interrupts_preserve_submission_uncertainty_without_fabricated_cancellation(
    submitted: bool,
    failure: BaseException,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = delivery(
        account_home, monkeypatch, credential_failure=None if submitted else failure
    )
    if submitted:

        def interrupt(request: httpx.Request) -> None:
            raise failure

        d.wire.on_request = interrupt
    assert d.invoke(_ARGS) == 130
    _evidence._local(
        capsys.readouterr(),
        "interrupted",
        phase="unknown" if submitted else "not_submitted",
    )
    assert d.reads == ["credential"] and len(d.wire.requests) == int(submitted)
    assert all(t.closed for t in d.wire.transports)


def test_interact_keeps_five_second_phases_and_one_ten_second_whole_deadline(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = delivery(account_home, monkeypatch)
    original = asyncio.timeout_at
    budgets: list[float] = []

    def observed(when: float | None) -> asyncio.Timeout:
        assert when is not None
        budgets.append(when - asyncio.get_running_loop().time())
        return original(when)

    monkeypatch.setattr(asyncio, "timeout_at", observed)
    assert d.invoke(_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(report()) + b"\n").decode(), "")
    assert len(budgets) == 1 and 9.9 <= budgets[0] <= 10.0
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize("complete", [False, True])
def test_whole_delivery_deadline_cancels_a_stalled_response_without_cleanup_requests(
    complete: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = delivery(account_home, monkeypatch)
    peer = _evidence._helpers("test_cli_follow").Stream(
        [_json(report()) if complete else _json(report())[:40]]
    )

    async def stalled_eof() -> None:
        await asyncio.Event().wait()

    peer.finish = stalled_eof
    d.wire.stream = peer
    original = asyncio.timeout_at
    budgets: list[float] = []

    def accelerated_clock(when: float | None) -> asyncio.Timeout:
        assert when is not None
        loop = asyncio.get_running_loop()
        budgets.append(when - loop.time())
        # Substitute only elapsed infrastructure time, retaining the real
        # cancellation/HTTPX cleanup/error path and requested ten-second budget.
        return original(loop.time() + 0.01)

    monkeypatch.setattr(asyncio, "timeout_at", accelerated_clock)
    assert d.invoke(_ARGS) == 5
    _evidence._local(capsys.readouterr(), "request_timeout", phase="unknown")
    assert len(budgets) == 1 and 9.9 <= budgets[0] <= 10.0
    assert peer.closed
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize("complete", [False, True])
def test_response_loss_after_some_or_all_bytes_does_not_claim_report_receipt(
    complete: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = _json(report())
    d = _evidence.Delivery(
        account_home,
        monkeypatch,
        chunks=[raw if complete else raw[:40]],
        stream_failure=httpx.ReadError(_PRIVATE),
    )
    assert d.invoke(_ARGS) == 5
    _evidence._local(capsys.readouterr(), "transport_failed", phase="unknown")
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize("broken_pipe", [False, True])
def test_output_failure_preserves_received_report_without_status_or_remote_cleanup(
    broken_pipe: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = delivery(account_home, monkeypatch)
    writes: list[bytes] = []

    class FailedOutput:
        @property
        def buffer(self) -> Any:
            return self

        def write(self, record: bytes) -> int:
            writes.append(record)
            if broken_pipe:
                raise BrokenPipeError(_PRIVATE)
            raise OSError(_PRIVATE)

        def flush(self) -> None:
            raise OSError(_PRIVATE)

        def close(self) -> None:
            pass

    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", FailedOutput())
        code = d.invoke(_ARGS)
    assert code == 1
    _evidence._local(capsys.readouterr(), "output_failed", phase="report_received")
    assert writes == [_json(report()) + b"\n"]
    d.one_request("/v2/observation/interact", _BODY)


@asynccontextmanager
async def _t019_service(
    home: Path,
    tmp: Path,
    patch: pytest.MonkeyPatch,
    backend: int,
    host: str,
) -> AsyncIterator[Any]:
    """Real composition/Profile2/SQLite4/auth/HTTP; only backend and clock are fake."""
    helper = _evidence._t014_service_helpers(patch)
    helper._t014_core_helpers(patch)
    fixtures = importlib.import_module("tests.fakes")
    probes = importlib.import_module("tests.contract.test_acquisition_write")
    clocks = importlib.import_module("tests.contract.test_monitor_recording")
    model = importlib.import_module("dutchmate_core.model")
    composition = importlib.import_module("dutchmate_core.adapters.observation_runtime")
    sqlite = importlib.import_module("dutchmate_core.adapters.sqlite_evidence")
    service = helper._t009_module()
    uvicorn = importlib.import_module("uvicorn")
    fixture = fixtures.BACKEND_FIXTURE_FACTORIES[backend]()
    writer = probes.WriteProbe(fixture)
    fixture.connection.descriptor = replace(
        fixture.connection.descriptor,
        capabilities=model.BackendCapabilities(
            frozenset(
                {
                    *fixture.connection.descriptor.capabilities.values,
                    model.BackendCapability.UART_SEND,
                }
            )
        ),
        connection_provenance=model.PersistedConnectionProvenance(
            model.ConnectionProvenanceSnapshot(
                1,
                "fixture/interact",
                1,
                (model.ProvenanceField("transport", "simulated"),),
            )
        ),
    )
    patch.setattr(fixture.connection, "write", writer.write, raising=False)
    patch.setattr(fixture.connection, "close", writer.close)
    prepared: list[object] = []

    def physical_backend(*args: Any, **kwargs: Any) -> Any:
        assert kwargs == {"write_enabled": True}
        prepared.append(args)
        return fixture.backend

    patch.setattr(composition, "BasicSerialBackend", physical_backend)
    clock = clocks.ManualClock()
    patch.setattr(composition, "MonotonicMonitorClock", lambda: clock)
    committed: dict[str, asyncio.Queue[Any]] = {}
    journals: list[Any] = []
    original_append = sqlite.SqliteEvidenceJournal.append

    async def append(journal: Any, draft: Any) -> Any:
        if not journals:
            journals.append(journal)
        assert journals == [journal]
        record = await original_append(journal, draft)
        committed.setdefault(type(record).__name__, asyncio.Queue()).put_nowait(record)
        return record

    patch.setattr(sqlite.SqliteEvidenceJournal, "append", append)
    profile_path, journal_path = tmp / "explicit.toml", tmp / "evidence.sqlite3"
    profile_path.write_text(
        """profile_version = 2
[dut]
id = "interact-cli-fixture"
name = "Explicit test DUT"
[backend]
kind = "basic_serial"
expected_device = "test-owned-fake-only"
[uart]
baud_rate = 115200
data_bits = 8
parity = "none"
stop_bits = 1
hardware_flow_control = false
software_flow_control = false
[uart.open_lines]
dtr = "deasserted"
rts = "deasserted"
[policy]
uart_tx_enabled = true
[persistence]
max_retained_records = 100
max_retained_charged_bytes = 262144
max_record_charged_bytes = 16384
max_database_pages = 256
max_retrieval_page_records = 100
max_retrieval_page_charged_bytes = 131072
""",
        encoding="utf-8",
    )
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        if family == socket.AF_INET6:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind((host, 0))
        listener.listen(128)
        listener.setblocking(False)
        config = helper.ServiceConfig(listener.getsockname()[1], host)
        created, _ = helper._t009_runtime_spy(service, patch)
        bootstrap = helper.PrivateBootstrap.acquire(config)
        lifespan = None
        server = None
        try:
            bootstrap.mark_unconfirmed()
            bootstrap.publish_credential()
            token = (home / ".local/state/dutchmate/service/credential").read_bytes()[
                :-1
            ]
            launch = service._LaunchContext(config, bootstrap)
            app = service.create_app(config, _launch_context=launch)
            lifespan = helper.AppLifespan(app)
            assert (await lifespan.start())["type"] == "lifespan.startup.complete"
            requests: list[tuple[str, str, bytes]] = []

            async def observed(scope: Any, receive: Any, send: Any) -> None:
                requests.append(
                    (
                        scope["method"],
                        scope["path"],
                        dict(scope["headers"])[b"authorization"],
                    )
                )
                await app(scope, receive, send)

            server = uvicorn.Server(
                uvicorn.Config(
                    observed,
                    host=host,
                    port=config.port,
                    lifespan="off",
                    log_config=None,
                    access_log=False,
                    log_level="critical",
                    proxy_headers=False,
                    server_header=False,
                    date_header=False,
                )
            )
            server.config.load()
            server.lifespan = server.config.lifespan_class(server.config)
            await asyncio.wait_for(server.startup(sockets=[listener]), 3)
            assert server.started
            yield (
                fixture,
                writer,
                clock,
                committed,
                config,
                token,
                requests,
                profile_path,
                journal_path,
                created[0],
                prepared,
            )
        finally:
            writer.allow.set()
            if server is not None:
                launch.request_stop()
                await asyncio.wait_for(server.shutdown(sockets=[listener]), 8)
            try:
                if lifespan is not None:
                    await lifespan.finish()
            finally:
                bootstrap.invalidate_credential()
                if created:
                    status = created[0].status()
                    bootstrap.confirm_cleanup(
                        owner_settled=status.owner_settled,
                        physical_release_confirmed=status.physical_release_confirmed,
                        recorder_close_confirmed=status.recorder_close_confirmed,
                    )
                bootstrap.release()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("host", ["127.0.0.1", "::1"], ids=["ipv4", "ipv6"])
async def test_t019_us1_real_cli_attach_interact_concurrent_workflows_and_terminal_readback(
    backend: int,
    host: str,
    account_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _t019_service(account_home, tmp_path, monkeypatch, backend, host) as env:
        (
            fixture,
            writer,
            clock,
            committed,
            config,
            token,
            requests,
            profile_path,
            journal_path,
            owner,
            prepared,
        ) = env
        api = _evidence._api()
        loop = asyncio.get_running_loop()
        frames: asyncio.Queue[bytes] = asyncio.Queue()
        outputs = threading.local()
        old_out, old_err = sys.stdout, sys.stderr

        class Output:
            def __init__(self, *, live: bool = False) -> None:
                self.records: list[bytes] = []
                self.live = live

            @property
            def buffer(self) -> Any:
                return self

            def write(self, raw: bytes) -> int:
                self.records.append(bytes(raw))
                return len(raw)

            def flush(self) -> None:
                if self.live:
                    loop.call_soon_threadsafe(frames.put_nowait, self.records[-1])

        class ThreadStream:
            def __init__(self, name: str, fallback: Any) -> None:
                self.name, self.fallback = name, fallback

            @property
            def buffer(self) -> Any:
                return getattr(outputs, self.name, self.fallback).buffer

            def flush(self) -> None:
                getattr(outputs, self.name, self.fallback).flush()

        reads: list[str] = []
        context = importlib.import_module("dutchmate_cli.context")
        read = context.read_credential

        def credential() -> str:
            reads.append("credential")
            return str(read())

        monkeypatch.setattr(context, "read_credential", credential)

        def console(
            command: list[str], live: bool, v2: bool
        ) -> tuple[int, bytes, bytes]:
            out, err = Output(live=live), Output()
            outputs.stdout, outputs.stderr = out, err
            try:
                args = [
                    *(["--api-version", "2"] if v2 else []),
                    "--host",
                    host,
                    "--port",
                    str(config.port),
                    *command,
                ]
                code = _commands._console(api, args)
                return code, b"".join(out.records), b"".join(err.records)
            finally:
                del outputs.stdout, outputs.stderr

        jobs: list[asyncio.Task[Any]] = []

        def submit(
            *command: str, live: bool = False, v2: bool = True
        ) -> asyncio.Task[Any]:
            task = asyncio.create_task(
                asyncio.to_thread(console, list(command), live, v2)
            )
            jobs.append(task)
            return task

        async def delivered(job: asyncio.Task[Any], code: int = 0) -> Any:
            actual, out, err = await asyncio.wait_for(asyncio.shield(job), 5)
            assert actual == code, (out, err)
            raw = out if code == 0 else err
            assert (err if code == 0 else out) == b"" and token not in raw
            assert (
                raw.endswith(b"\n") and raw.count(b"\n") == 1 and len(raw) <= _LIMIT + 1
            )
            return _evidence._helpers("json").loads(raw)

        async def ack(kind: str) -> Any:
            return await asyncio.wait_for(
                committed.setdefault(kind, asyncio.Queue()).get(), 3
            )

        async def emit(raw: bytes, stamp: int) -> Any:
            await fixture.connection.emit_rx(raw, timestamp=stamp)
            return await ack("RxBytesEvidence")

        async def frame() -> Any:
            return _evidence._helpers("json").loads(
                await asyncio.wait_for(frames.get(), 3)
            )

        def page(session: str) -> asyncio.Task[Any]:
            return submit(
                "evidence",
                "page",
                "--session",
                session,
                "--max-records",
                "100",
                "--max-charged-bytes",
                "131072",
            )

        with monkeypatch.context() as patch:
            patch.setattr(sys, "stdout", ThreadStream("stdout", old_out))
            patch.setattr(sys, "stderr", ThreadStream("stderr", old_err))
            try:
                inactive = await delivered(submit("status"))
                assert inactive["runtime"]["state"] == "inactive"
                attached = await delivered(
                    submit(
                        "attach",
                        "--profile",
                        str(profile_path),
                        "--journal",
                        str(journal_path),
                    )
                )
                assert attached["runtime"]["state"] == "active"
                assert attached["runtime"]["profile"]["format_version"] == 2
                assert (
                    attached["runtime"]["profile"]["policy"]["uart_tx_enabled"] is True
                )
                session = attached["runtime"]["session_id"]
                await ack("SegmentStartedEvidence")
                ambient = b"before operations\0\xff"
                before = await emit(ambient, 1)
                follow_job = submit("follow", "--session", session, live=True)
                started = await frame()
                assert (
                    started["type"] == "started"
                    and started["start_sequence"] == before.sequence + 1
                )
                monitor_job = submit(
                    "monitor",
                    "--session",
                    session,
                    "--condition-base64",
                    "TU9O",
                    "--timeout-ms",
                    "1000",
                    "--max-rx-bytes",
                    "1024",
                )
                await ack("OperationStartedEvidence")
                payload = bytes(range(256))
                encoded = base64.b64encode(payload).decode()
                interact_args = (
                    "interact",
                    "--session",
                    session,
                    "--payload-base64",
                    encoded,
                    "--condition-base64",
                    "RkFJTA==",
                    "--condition-base64",
                    "AP9QQVNT",
                    "--timeout-ms",
                    "1000",
                    "--max-rx-bytes",
                    "1024",
                )
                interact_job = submit(*interact_args)
                intent = await ack("InteractStartedEvidence")
                await asyncio.wait_for(writer.entered.wait(), 3)
                assert (
                    not interact_job.done()
                    and not monitor_job.done()
                    and writer.calls == [payload]
                )
                annotation = await delivered(
                    submit(
                        "annotate",
                        "--session",
                        session,
                        "--text",
                        "external fixture step",
                    )
                )
                assert annotation["annotation"]["assertion_class"] == "client_assertion"
                pending = await delivered(page(session))
                assert intent.sequence in [
                    r["sequence"] for r in pending["page"]["records"]
                ]
                busy = await delivered(submit(*interact_args), 4)
                assert busy == {
                    "error": {"source": "service", "code": "interact_capacity"}
                }
                first_bytes, last_bytes = b"ambient\0\xffPA", b"SS MON\0trailing\x80"
                first, last = await emit(first_bytes, 2), await emit(last_bytes, 3)
                monitor_report = await delivered(monitor_job)
                assert (
                    monitor_report["outcome"] == "matched" and not interact_job.done()
                )
                after_bytes = b"post-match ambient\xff"
                await emit(after_bytes, 4)
                writer.allow.set()
                value = await delivered(interact_job)
                assert value["run_id"] == attached["runtime"]["run_id"]
                assert (
                    value["session_id"] == session
                    and value["payload_base64"] == encoded
                )
                assert value["conditions_base64"] == ["RkFJTA==", "AP9QQVNT"]
                assert (
                    value["outcome"] == "matched" and value["durability"] == "complete"
                )
                assert (
                    value["tx"]["status"] == "acknowledged"
                    and value["tx"]["accepted_prefix_bytes"] == 256
                )
                assert value["tx"]["acknowledgement_scope"] == "backend_acceptance"
                assert value["provenance"]["causation"] == "not_established"
                assert value["observation"]["window"] == {
                    "start_inclusive": intent.sequence + 1,
                    "end_exclusive": last.sequence + 1,
                }
                assert value["observation"]["match"] == {
                    "condition_index": 1,
                    "start": {"sequence": first.sequence, "byte_offset": 7},
                    "end": {"sequence": last.sequence, "byte_offset_exclusive": 2},
                }
                assert value["observation"]["examined_rx_bytes"] == 13
                live = await delivered(page(session))
                followed: list[dict[str, Any]] = []
                while (
                    not followed or followed[-1]["record"]["kind"] != "interact_ended"
                ):
                    entry = await frame()
                    if entry["type"] == "record":
                        followed.append(entry)
                assert [f["record"] for f in followed] == [
                    r
                    for r in live["page"]["records"]
                    if r["sequence"] >= started["start_sequence"]
                ]
                rejected = await delivered(submit("status", v2=False), 4)
                assert rejected == {
                    "error": {"source": "request", "code": "unsupported_api_version"}
                }
                detached = await delivered(submit("detach"))
                assert detached["runtime"]["physical_release_confirmed"] is True
                code, raw, err = await asyncio.wait_for(asyncio.shield(follow_job), 5)
                assert code == 0 and err == b"" and token not in raw
                tail = [
                    _evidence._helpers("json").loads(line) for line in raw.splitlines()
                ]
                assert (
                    tail[-1]["type"] == "terminal" and tail[-1]["reason"] == "detached"
                )
                terminal = await delivered(page(session))
                assert terminal["page"]["records"][:-1] == live["page"]["records"]
                records = terminal["page"]["records"]
                assert [
                    base64.b64decode(r["payload_base64"])
                    for r in records
                    if r["kind"] == "rx_bytes"
                ] == [
                    ambient,
                    first_bytes,
                    last_bytes,
                    after_bytes,
                ]
                for key in ("started_record", "tx_settled_record", "ended_record"):
                    reference = value[key]
                    readback = await delivered(
                        submit(
                            "evidence",
                            "record",
                            "--session",
                            session,
                            "--sequence",
                            str(reference["sequence"]),
                        )
                    )
                    assert readback["page"]["records"] == [
                        records[reference["sequence"]]
                    ]
                assert (
                    fixture.backend.open_calls == fixture.connection.consumer_calls == 1
                )
                assert (
                    fixture.connection.close_calls == 1
                    and writer.active_at_close == [0]
                )
                assert writer.calls == [payload] and len(prepared) == 1
                assert (
                    owner.status().owner_settled
                    and owner.evidence_read_cleanup_confirmed
                )
                assert len(reads) == len(requests) == len(jobs)
                assert all(auth == b"Bearer " + token for _, _, auth in requests)
                assert all(
                    path.startswith("/v2/") or path == "/v1/observation/status"
                    for _, path, _ in requests
                )
            finally:
                writer.allow.set()
                await owner.detach()
                await asyncio.wait_for(asyncio.gather(*jobs, return_exceptions=True), 8)


# T021: strict delivery/version edges only, never local transaction mechanics.
@pytest.mark.parametrize("option", ["--payload-base64", "--condition-base64"])
@pytest.mark.parametrize("tail", list("BCDEFGHIJKLMNOP"))
def test_t021_every_nonzero_base64_pad_bit_is_rejected_before_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    option: str,
    tail: str,
) -> None:
    # All15 spellings decode to the same byte as AA==, but are not canonical.
    with monkeypatch.context() as patch:
        recognized(patch)
    api = _evidence._api()
    attempts = _commands._block_preparation(api, monkeypatch)
    args = list(_ARGS)
    args[args.index(option) + 1] = "A" + tail + "=="
    assert _evidence._command(api, args) == 2
    _evidence._local(capsys.readouterr(), "invalid_arguments")
    assert attempts == []


@pytest.mark.parametrize("path", _CLOSED_PATHS)
def test_t021_encoded_nested_duplicate_report_fields_discard_whole_report(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    path: tuple[str, ...],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    value = report()
    obj = _evidence._at(value, path)
    key = next(iter(obj))
    old = _json(obj)
    escaped_key = f'"\\u{ord(key[0]):04x}{key[1:]}"'.encode()
    damaged = old[:-1] + b"," + escaped_key + b":" + _json(obj[key]) + b"}"
    raw = _json(value).replace(old, damaged, 1)
    assert raw != _json(value)
    d = _evidence.Delivery(account_home, monkeypatch, body=raw)
    assert d.invoke(_ARGS) == 5
    _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    d.one_request("/v2/observation/interact", _BODY)
    assert _PRIVATE not in caplog.text and _TOKEN not in caplog.text


@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize("size", [_LIMIT - 1, _LIMIT, _LIMIT + 1])
def test_t021_exact_escaped_report_provenance_cap_preserves_partial_write_facts(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    device: bool,
    size: int,
) -> None:
    value = report("partial_write", device=device)
    value["provenance"]["connection_provenance"]["fields"] = [
        {"name": "padding", "value": ""}
    ]
    budget = size - len(_json(value))
    unit = 'é😀\n\r\\"\x01'
    width = len(_json(unit)) - 2
    value["provenance"]["connection_provenance"]["fields"][0]["value"] = unit * (
        budget // width
    ) + "p" * (budget % width)
    raw = _json(value)
    assert len(raw) == size
    d = _evidence.Delivery(
        account_home,
        monkeypatch,
        chunks=[raw[:17], raw[17:16384], raw[16384:]],
        headers=[("Content-Type", "application/json"), ("Content-Length", "1")],
    )
    assert d.invoke(_ARGS) == (0 if size <= _LIMIT else 5)
    if size <= _LIMIT:
        captured = capsys.readouterr()
        assert tuple(captured) == ((raw + b"\n").decode(), "")
        assert len(captured.out.encode()) == size + 1
    else:
        _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    d.one_request("/v2/observation/interact", _BODY)


@pytest.mark.parametrize("device", [False, True])
def test_t021_maximum_binary_request_and_escaped_session_are_echoed_without_transformation(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    device: bool,
) -> None:
    payload = bytes(range(256)) * 16
    conditions = (bytes(range(256)), b"\0\xff\r\n", bytes(range(256)), b"\xff")
    session = '\x01"\\é' * 32
    body: dict[str, Any] = {
        "session_id": session,
        "payload_base64": base64.b64encode(payload).decode(),
        "conditions_base64": [base64.b64encode(c).decode() for c in conditions],
        "timeout_ms": 4000,
        "max_rx_bytes": _LIMIT,
    }
    value = report("detached", device=device)
    value.update(
        session_id=session,
        payload_base64=body["payload_base64"],
        conditions_base64=body["conditions_base64"],
    )
    for name in ("started_record", "tx_settled_record", "ended_record"):
        value[name]["session_id"] = session
    value["tx"]["accepted_prefix_bytes"] = 4096
    value["observation"]["clock"]["deadline_at_ns"] = 4000000100
    args = [
        "--api-version",
        "2",
        "--port",
        "8765",
        "interact",
        "--session",
        session,
        "--payload-base64",
        body["payload_base64"],
        "--timeout-ms",
        "4000",
        "--max-rx-bytes",
        str(_LIMIT),
    ]
    for condition in body["conditions_base64"]:
        args += ["--condition-base64", condition]
    d = delivery(account_home, monkeypatch, value)
    assert d.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((_json(value) + b"\n").decode(), "")
    d.one_request("/v2/observation/interact", body)


@pytest.mark.parametrize(
    "raw,status",
    [
        (b'{"error":{"source":"interact","code":"busy","\\u0063ode":"busy"}}', 409),
        (b'{"error":{"source":"interact","code":NaN}}', 409),
        (b'{"error":{"source":true,"code":"busy"}}', 409),
        (
            b'{"error":{"source":"interact","code":"delivery_too_large"},"tx":{"submitted":false}}',
            413,
        ),
        (
            b'{"error":{"source":"service","code":"internal_failure","detail":"private-token-path-SQL"}}',
            500,
        ),
        (b'{"error":{"source":"request","code":"unsupported_api_version"}}', 200),
    ],
)
def test_t021_remote_error_ambiguity_never_leaks_diagnostics_or_invents_tx_facts(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
    status: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    d = _evidence.Delivery(account_home, monkeypatch, body=raw, status=status)
    assert d.invoke(_ARGS) == 5
    _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    d.one_request("/v2/observation/interact", _BODY)
    assert "private-token-path-SQL" not in caplog.text and _TOKEN not in caplog.text


# T024: real client-process loss against authenticated, fake-only loopback.
# This is source-tree lifetime coverage; installed wheel/sdist acceptance is T026.
_T024_CHILD = r"""
import asyncio, os, pwd, sys
home, mode, *args = sys.argv[1:]
# The child uses only the test account. HOME does not override POSIX account lookup.
entry = pwd.getpwuid(os.geteuid())
pwd.getpwuid = lambda uid: pwd.struct_passwd((*entry[:5], home, entry.pw_shell))
from dutchmate_cli import context
original_credential = context.read_credential
reads = []
def credential():
    reads.append(1)
    assert len(reads) == 1
    return original_credential()
context.read_credential = credential
if mode == "deadline":
    original_timeout = asyncio.timeout_at
    def elapsed(when):
        loop = asyncio.get_running_loop()
        assert 9.0 < when - loop.time() <= 10.0
        return original_timeout(loop.time() + 0.5)
    asyncio.timeout_at = elapsed
from dutchmate_cli.main import main
code = main(args)
assert len(reads) == 1
assert not any(name.startswith(("dutchmate_core", "dutchmate_service", "serial")) for name in sys.modules)
raise SystemExit(code)
"""


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("host", ["127.0.0.1", "::1"], ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("loss", ["sigint", "deadline", "pipe"])
async def test_t024_real_cli_loss_never_retries_detaches_synthesizes_or_abandons_server_owner(
    backend: int,
    host: str,
    loss: str,
    account_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    import signal

    async with _t019_service(account_home, tmp_path, monkeypatch, backend, host) as env:
        (
            fixture,
            writer,
            clock,
            committed,
            config,
            token,
            requests,
            profile_path,
            journal_path,
            owner,
            prepared,
        ) = env
        authority = (
            f"[{host}]:{config.port}" if host == "::1" else f"{host}:{config.port}"
        )
        async with httpx.AsyncClient(
            base_url=f"http://{authority}",
            trust_env=False,
            headers={"Authorization": "Bearer " + token.decode()},
        ) as peer:
            attached = await peer.post(
                "/v2/observation/attach",
                json={
                    "profile_path": str(profile_path),
                    "journal_path": str(journal_path),
                },
            )
            assert attached.status_code == 200
            session = owner.status().session_id.value
            await asyncio.wait_for(committed["SegmentStartedEvidence"].get(), 3)
            args = [
                "--api-version",
                "2",
                "--host",
                host,
                "--port",
                str(config.port),
                "interact",
                "--session",
                session,
                *_ARGS[7:],
            ]
            # Use a closed reader, not a fake Python stream, for actual EPIPE.
            pipe_write = None
            if loss == "pipe":
                pipe_read, pipe_write = os.pipe()
                os.close(pipe_read)
            child = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                _T024_CHILD,
                str(account_home),
                loss,
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE if pipe_write is None else pipe_write,
                stderr=asyncio.subprocess.PIPE,
            )
            if pipe_write is not None:
                os.close(pipe_write)
            communication = asyncio.create_task(child.communicate())
            try:
                notification = asyncio.create_task(writer.entered.wait())
                try:
                    done, _ = await asyncio.wait(
                        (notification, communication),
                        timeout=5,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    assert notification in done, (
                        await communication
                        if communication.done()
                        else "client did not submit"
                    )
                finally:
                    notification.cancel()
                    await asyncio.gather(notification, return_exceptions=True)
                assert owner.status().state.value == "active" and len(writer.calls) == 1
                if loss == "sigint":
                    # Send only to the isolated child after backend admission.
                    child.send_signal(signal.SIGINT)
                if loss == "pipe":
                    await fixture.connection.emit_rx(b"PASS", timestamp=123)
                    writer.allow.set()
                out, err = await asyncio.wait_for(asyncio.shield(communication), 5)
                assert (
                    child.returncode == {"sigint": 130, "deadline": 5, "pipe": 1}[loss]
                )
                assert out in (b"", None)
                expected = {
                    "error": {
                        "source": "cli",
                        "code": {
                            "sigint": "interrupted",
                            "deadline": "request_timeout",
                            "pipe": "output_failed",
                        }[loss],
                    },
                    "request_outcome": "report_received"
                    if loss == "pipe"
                    else "unknown",
                }
                assert err == _json(expected) + b"\n"
                assert owner.status().state.value == "active"
                if loss != "pipe":
                    assert writer.active == 1 and not writer.close_entered.is_set()
                    rejected = await peer.post(
                        "/v2/observation/interact",
                        json={**_BODY, "session_id": session},
                    )
                    assert rejected.status_code == 503 and rejected.json() == {
                        "error": {"source": "service", "code": "interact_capacity"}
                    }
                    writer.allow.set()
                # Wait for the durable result; no client follow-up is used to get it.
                async with asyncio.timeout(3):
                    while "InteractEndedEvidence" not in committed:
                        await asyncio.sleep(0.001)
                end = await asyncio.wait_for(
                    committed["InteractEndedEvidence"].get(), 3
                )
                tx = await asyncio.wait_for(committed["UartTxSettledEvidence"].get(), 3)
                assert end.outcome.value == (
                    "matched" if loss == "pipe" else "cancelled"
                )
                assert (
                    tx.tx.submitted
                    and tx.tx.acknowledgement_scope == "backend_acceptance"
                )
                assert len(writer.calls) == 1 and writer.cancellation_signals == 0
                assert (
                    fixture.connection.consumer_calls == 1
                    and not fixture.connection.closed
                )
                assert prepared and journal_path.exists()
                assert [(method, route) for method, route, auth in requests] == [
                    ("POST", "/v2/observation/attach"),
                    ("POST", "/v2/observation/interact"),
                    *([] if loss == "pipe" else [("POST", "/v2/observation/interact")]),
                ]
                assert all(auth == b"Bearer " + token for _, _, auth in requests)
                # Core readback confirms authoritative durable facts, no synthetic CLI report.
                from dutchmate_core.model import EvidenceReference

                saved = await owner.read_record(
                    EvidenceReference(owner.status().session_id, end.sequence)
                )
                assert saved.page.records == (end,)
            finally:
                writer.allow.set()
                if child.returncode is None:
                    child.terminate()
                await asyncio.wait_for(asyncio.shield(communication), 5)
