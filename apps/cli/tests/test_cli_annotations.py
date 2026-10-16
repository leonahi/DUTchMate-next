"""010 T012 RED: thin annotation grammar, wire facts and delivery outcomes.

Use the real console/Typer/HTTPX path and isolated credential/transport helpers.
No annotation command, validator, rate limiter or service policy lives here.
"""

import asyncio
import base64
import importlib
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import typer

_commands = importlib.import_module("test_cli_commands")
_evidence = importlib.import_module("test_cli_evidence")
_transport = importlib.import_module("test_cli_transport")
Delivery = _evidence.Delivery
_api = _evidence._api
_json = _evidence._json
_local = _evidence._local
_TOKEN = _evidence._TOKEN
_PRIVATE = _evidence._PRIVATE
_SESSION = "session-é"
_ORIGIN = "abcdefab-1234-4234-8234-123456789abc"
_MAX = 9223372036854775807
_LIMIT = 1048576
_TEXT = " build e\u0301; smoke\r\n\t "
_ARGS = ["--port", "8765", "annotate", "--session", _SESSION, "--text", _TEXT]
_BODY = {"session_id": _SESSION, "text": _TEXT, "client_surface": "cli"}


def _receipt() -> dict[str, Any]:
    """Independent contract fixture, never constructed with a production codec."""
    return {
        "run_id": "run-é",
        "session_id": _SESSION,
        "reference": {"session_id": _SESSION, "sequence": 3},
        "annotation": {
            "kind": "client_annotation",
            "sequence": 3,
            "assertion_class": "client_assertion",
            "client_surface": "cli",
            "attribution_basis": "client_asserted",
            "clock_origin_id": _ORIGIN,
            "received_at_ns": 100,
            "text": _TEXT,
        },
    }


def _delivery(
    home: Path, patch: pytest.MonkeyPatch, body: object | None = None, **options: Any
) -> Any:
    return Delivery(
        home, patch, body=_json(_receipt() if body is None else body), **options
    )


def _reverse(value: Any) -> Any:
    if type(value) is dict:
        return {k: _reverse(v) for k, v in reversed(list(value.items()))}
    if type(value) is list:
        return [_reverse(v) for v in value]
    return value


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--help"],
        ["annotate", "--help"],
        ["--host", _PRIVATE, "--port", "0", "annotate", "--help"],
    ],
)
@pytest.mark.parametrize("unsupported", [False, True])
def test_help_is_static_and_exposes_only_the_bounded_annotation_grammar(
    args: list[str],
    unsupported: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _commands._block_preparation(api, monkeypatch)
    if unsupported:
        monkeypatch.setattr(sys, "platform", "win32")
    assert _evidence._command(api, args) == 0
    stdout, stderr = capsys.readouterr()
    assert stdout and not stderr
    if "annotate" in args:
        assert "--session" in stdout and "--text" in stdout
        for option in (
            "--client-surface",
            "--surface",
            "--author",
            "--time",
            "--file",
            "--stdin",
            "--follow",
            "--run-id",
            "--output",
            "--token",
            "--journal",
            "--profile",
        ):
            assert option not in stdout
    else:
        assert "annotate" in stdout
    assert attempts == [] and _PRIVATE not in stdout


_BAD_ARGS = [
    _ARGS[2:],
    ["--port", "8765", "annotate"],
    [*_ARGS, _PRIVATE],
    ["--port", "8765", "Annotate", *_ARGS[3:]],
]
for _option in ("--session", "--text"):
    _index = _ARGS.index(_option)
    _BAD_ARGS.extend((_ARGS[:_index] + _ARGS[_index + 2 :], [*_ARGS, _option]))
for _option in (
    "--client-surface",
    "--surface",
    "--author",
    "--time",
    "--clock-origin",
    "--sequence",
    "--metadata",
    "--file",
    "--stdin",
    "--follow",
    "--run-id",
    "--output",
    "--path",
    "--token",
    "--journal",
    "--profile",
):
    _BAD_ARGS.append([*_ARGS, _option, _PRIVATE])
for _option, _values in (
    ("--session", ("", "x\0y", "x" * 257, "é" * 129, "\ud800")),
    ("--text", ("", "x\0y", "x" * 1025, "é" * 513, "\ud800", "\udfff")),
):
    for _value in _values:
        _args = list(_ARGS)
        _args[_args.index(_option) + 1] = _value
        _BAD_ARGS.append(_args)
for _prefix in (
    ["--port", "0"],
    ["--port", "65536"],
    ["--host", "localhost", "--port", "8765"],
    ["--host", "::ffff:127.0.0.1", "--port", "8765"],
):
    _BAD_ARGS.append([*_prefix, *_ARGS[2:]])


@pytest.mark.parametrize("args", _BAD_ARGS)
def test_invalid_input_is_private_before_platform_account_credentials_or_network(
    args: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = _api()
    attempts = _commands._block_preparation(api, monkeypatch)
    assert _evidence._command(api, args) == 2
    _local(capsys.readouterr(), "invalid_arguments")
    _commands._grammar_rejected(_commands._runner(api, args))
    assert attempts == [] and _PRIVATE not in caplog.text


@pytest.mark.parametrize(
    "session,text",
    [
        (" ", " "),
        ("x" * 256, "x" * 1024),
        ("é" * 128, "é" * 512),
        ("emoji", "😀" * 256),
        ("escaped", "\x01" * 1024),
        (" /e\u0301/id ", " \r\n\t e\u0301 "),
    ],
)
@pytest.mark.parametrize("host,port", [("127.0.0.1", 1), ("::1", 65535)])
def test_legal_byte_edges_send_one_exact_request_and_preserve_acknowledged_facts(
    session: str,
    text: str,
    host: str,
    port: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The service receipt is authoritative; the CLI must not reconstruct it.
    receipt = _receipt()
    receipt["annotation"]["text"] = "acknowledged text"
    delivery = _delivery(account_home, monkeypatch, _reverse(receipt))
    args = [
        "--host",
        host,
        "--port",
        str(port),
        "annotate",
        "--session",
        session,
        "--text",
        text,
    ]
    assert delivery.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((_json(receipt) + b"\n").decode(), "")
    body = {"session_id": session, "text": text, "client_surface": "cli"}
    delivery.one_request("/v1/observation/annotations", body, host=host, port=port)
    assert delivery.wire.requests[0].content == _json(body)


def test_repeated_options_follow_existing_last_value_rule_without_extra_requests(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(account_home, monkeypatch)
    assert (
        delivery.invoke(
            [*_ARGS, "--session", "second-session", "--text", "second text"]
        )
        == 0
    )
    assert tuple(capsys.readouterr()) == ((_json(_receipt()) + b"\n").decode(), "")
    delivery.one_request(
        "/v1/observation/annotations",
        {
            "session_id": "second-session",
            "text": "second text",
            "client_surface": "cli",
        },
    )


_CLOSED_PATHS = [(), ("reference",), ("annotation",)]
_REQUIRED_FIELDS = [
    (path, key) for path in _CLOSED_PATHS for key in _evidence._at(_receipt(), path)
]


@pytest.mark.parametrize("path,key", _REQUIRED_FIELDS)
def test_each_receipt_reference_and_annotation_field_is_required(
    path: tuple[str, ...],
    key: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = _receipt()
    del _evidence._at(receipt, path)[key]
    delivery = _delivery(account_home, monkeypatch, receipt)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize("path", _CLOSED_PATHS)
@pytest.mark.parametrize(
    "key", ["record_version", "verified_author", "operation_id", "provenance", "extra"]
)
def test_wire_objects_are_closed_with_no_verified_identity_or_action_fields(
    path: tuple[str, ...],
    key: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = _receipt()
    _evidence._at(receipt, path)[key] = _PRIVATE
    delivery = _delivery(account_home, monkeypatch, receipt)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


_BAD_RECEIPTS: list[tuple[tuple[str, ...], object]] = [
    (("run_id",), ""),
    (("run_id",), None),
    (("session_id",), True),
    (("reference",), None),
    (("annotation",), []),
    (("reference", "session_id"), "different-session"),
    (("reference", "sequence"), 4),
    (("reference", "sequence"), True),
    (("annotation", "kind"), "rx_bytes"),
    (("annotation", "assertion_class"), "dut_observation"),
    (("annotation", "attribution_basis"), "verified"),
    (("annotation", "client_surface"), "core"),
    (("annotation", "client_surface"), "CLI"),
    (("annotation", "client_surface"), None),
    (("annotation", "clock_origin_id"), _ORIGIN.upper()),
    (("annotation", "clock_origin_id"), _ORIGIN.replace("-", "")),
    (("annotation", "clock_origin_id"), "not-a-uuid"),
    (("annotation", "clock_origin_id"), None),
]
_bad_values: tuple[object, ...]
_bad_value: object
for _field, _bad_values in (
    ("sequence", (-1, True, 1.0, "3", None, _MAX)),
    ("received_at_ns", (-1, True, 1.0, "100", None, _MAX + 1)),
    ("text", ("", "\0", "x" * 1025, "é" * 513, True, 1, None, [])),
):
    for _bad_value in _bad_values:
        _BAD_RECEIPTS.append((("annotation", _field), _bad_value))


@pytest.mark.parametrize("path,bad", _BAD_RECEIPTS)
def test_receipt_types_literals_uuid_bounds_and_reference_identity_are_strict(
    path: tuple[str, ...],
    bad: object,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = _receipt()
    _evidence._at(receipt, path[:-1])[path[-1]] = bad
    if path == ("annotation", "sequence"):
        # Isolate counter validation from a mere reference-equality rejection.
        receipt["reference"]["sequence"] = bad
    delivery = _delivery(account_home, monkeypatch, receipt)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize("sequence,received", [(0, 0), (_MAX - 1, _MAX)])
def test_receipt_integer_edges_are_wire_facts_without_clock_or_retention_inference(
    sequence: int,
    received: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = _receipt()
    receipt["reference"]["sequence"] = receipt["annotation"]["sequence"] = sequence
    receipt["annotation"]["received_at_ns"] = received
    receipt["annotation"]["text"] = " " if received == 0 else "é" * 512
    delivery = _delivery(account_home, monkeypatch, _reverse(receipt))
    assert delivery.invoke(_ARGS) == 0
    assert tuple(capsys.readouterr()) == ((_json(receipt) + b"\n").decode(), "")
    delivery.one_request("/v1/observation/annotations", _BODY)


_ANNOTATION_ERRORS = [
    (404, "no_associated_session"),
    (409, "session_not_associated"),
    (409, "not_active"),
    (503, "annotation_unavailable"),
    (422, "evidence_policy_incompatible"),
    (409, "busy"),
    (429, "rate_limited"),
    (413, "delivery_too_large"),
]
_JOURNAL_ERRORS = _evidence._helpers("test_cli_monitor")._JOURNAL_CODES
_REMOTE_ERRORS = [(s, "annotation", c) for s, c in _ANNOTATION_ERRORS]
_REMOTE_ERRORS += [
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
    for c in _JOURNAL_ERRORS
]
_REMOTE_ERRORS += _transport._REMOTE_ERRORS


@pytest.mark.parametrize("status,source,code", _REMOTE_ERRORS)
def test_recognized_annotation_journal_and_common_errors_exit_four_without_retry(
    status: int,
    source: str,
    code: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    body = {"error": {"source": source, "code": code}}
    delivery = _delivery(account_home, monkeypatch, _reverse(body), status=status)
    assert delivery.invoke(_ARGS) == 4
    assert tuple(capsys.readouterr()) == ("", (_json(body) + b"\n").decode())
    delivery.one_request("/v1/observation/annotations", _BODY)
    assert _PRIVATE not in caplog.text and _TOKEN not in caplog.text


@pytest.mark.parametrize(
    "status,body",
    [
        (200, {"error": {"source": "annotation", "code": "busy"}}),
        (409, {"error": {"source": "annotation", "code": "rate_limited"}}),
        (429, {"error": {"source": "annotation", "code": "busy"}}),
        (409, {"error": {"source": "journal", "code": "busy"}}),
        (500, {"error": {"source": "annotation", "code": _PRIVATE}}),
        (
            429,
            {
                "error": {
                    "source": "annotation",
                    "code": "rate_limited",
                    "detail": _PRIVATE,
                }
            },
        ),
        (
            429,
            {
                "error": {"source": "annotation", "code": "rate_limited"},
                "request_outcome": "unknown",
            },
        ),
        (200, {"run_id": "partial"}),
    ],
)
def test_wrong_error_pair_extra_field_or_partial_success_is_private_invalid_response(
    status: int,
    body: object,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(account_home, monkeypatch, body, status=status)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize("status,code", _ANNOTATION_ERRORS)
@pytest.mark.parametrize(
    "args",
    [
        ["--port", "8765", "status"],
        _evidence._PAGE_ARGS,
        [
            "--port",
            "8765",
            "monitor",
            "--session",
            _SESSION,
            "--condition-base64",
            "AA==",
            "--timeout-ms",
            "1",
            "--max-rx-bytes",
            "1",
        ],
    ],
)
def test_annotation_errors_do_not_broaden_existing_command_validators(
    status: int,
    code: str,
    args: list[str],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(
        account_home,
        monkeypatch,
        {"error": {"source": "annotation", "code": code}},
        status=status,
    )
    assert delivery.invoke(args) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


def _sized_receipt(size: int) -> dict[str, Any]:
    receipt = _receipt()
    receipt["run_id"] = ""
    fragment = 'é/\\"\n😀'
    available = size - len(_json(receipt))
    charged = len(_json(fragment)) - 2
    receipt["run_id"] = fragment * (available // charged) + "r" * (available % charged)
    assert len(_json(receipt)) == size
    return receipt


@pytest.mark.parametrize(
    "size,exit_code", [(_LIMIT - 1, 0), (_LIMIT, 0), (_LIMIT + 1, 5)]
)
@pytest.mark.parametrize("declared", ["0", "9999999"])
def test_independent_raw_utf8_receipt_cap_and_canonical_json_plus_one_lf(
    size: int,
    exit_code: int,
    declared: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = _json(_sized_receipt(size))
    delivery = Delivery(
        account_home,
        monkeypatch,
        chunks=[raw[:19], raw[19:]],
        headers=[("Content-Type", "application/json"), ("Content-Length", declared)],
    )
    assert delivery.invoke(_ARGS) == exit_code
    output = capsys.readouterr()
    if exit_code == 0:
        assert tuple(output) == ((raw + b"\n").decode(), "")
        assert len(output.out.encode()) == size + 1
    else:
        _local(output, "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed


@pytest.mark.parametrize(
    "size,allowed", [(_LIMIT - 1, True), (_LIMIT, True), (_LIMIT + 1, False)]
)
def test_output_encoder_cap_remains_independent_of_annotation_text_bound(
    size: int, allowed: bool
) -> None:
    client = importlib.import_module("dutchmate_cli.client")
    receipt = _sized_receipt(size)
    if allowed:
        assert client._encode_record(receipt) == _json(receipt) + b"\n"
    else:
        with pytest.raises(client.CliFailure) as rejected:
            client._encode_record(receipt)
        assert rejected.value.kind.value == "invalid_response"


@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b"[]",
        b"\xff",
        b"{} trailing",
        _json(_receipt()).replace(b'"received_at_ns":100', b'"received_at_ns":NaN'),
        _json(_receipt()).replace(_json(_TEXT), b'"\\ud800"'),
        _json(_receipt())[:-1] + b',"run_id":"duplicate"}',
    ],
)
def test_strict_response_json_never_prints_partial_or_repaired_assertions(
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
    ],
)
def test_existing_media_identity_and_no_redirect_rules_apply_to_annotation_delivery(
    headers: list[tuple[str, str]],
    valid: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(account_home, monkeypatch, headers=headers)
    assert delivery.invoke(_ARGS) == (0 if valid else 5)
    output = capsys.readouterr()
    if valid:
        assert tuple(output) == ((_json(_receipt()) + b"\n").decode(), "")
    else:
        _local(output, "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed


@pytest.mark.parametrize(
    "failure,exit_code,kind",
    [
        (httpx.ConnectError(_PRIVATE), 5, "transport_failed"),
        (httpx.ReadTimeout(_PRIVATE), 5, "request_timeout"),
        (httpx.RemoteProtocolError(_PRIVATE), 5, "invalid_response"),
        (RuntimeError(_PRIVATE), 1, "internal_failure"),
    ],
)
def test_transport_failure_never_retries_or_claims_a_recorded_assertion(
    failure: Exception,
    exit_code: int,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    delivery = _delivery(account_home, monkeypatch, failure=failure)
    assert delivery.invoke(_ARGS) == exit_code
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
def test_valid_input_keeps_existing_private_pre_submission_context_failures(
    mode: str,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if mode == "unsafe":
        _evidence._helpers("test_cli_context")._credential(account_home, b"unsafe\n")
    elif mode == "unsupported":
        monkeypatch.setattr(sys, "platform", "win32")
    assert _evidence._command(_api(), _ARGS) == 3
    _local(capsys.readouterr(), kind)


@pytest.mark.parametrize(
    "failure,exit_code,kind",
    [
        (KeyboardInterrupt(_PRIVATE), 130, "interrupted"),
        (typer.Abort(), 130, "interrupted"),
        (RuntimeError(_PRIVATE), 1, "internal_failure"),
    ],
)
def test_pre_submission_interrupt_or_fault_has_no_request_or_assertion_receipt(
    failure: BaseException,
    exit_code: int,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    delivery = _delivery(account_home, monkeypatch, credential_failure=failure)
    assert delivery.invoke(_ARGS) == exit_code
    _local(capsys.readouterr(), kind)
    assert delivery.reads == ["credential"] and not delivery.wire.requests


def test_sigint_after_submission_reports_unknown_and_sends_no_cleanup_request(
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
    assert all(t.closed for t in delivery.wire.transports)


@pytest.mark.parametrize("broken_pipe", [False, True])
def test_stdout_failure_keeps_report_received_without_remote_rollback_or_retry(
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
        exit_code = delivery.invoke(_ARGS)
    assert exit_code == 1
    _local(capsys.readouterr(), "output_failed", phase="report_received")
    assert attempts == [_json(_receipt()) + b"\n"]
    assert len(delivery.wire.requests) == 1


def test_unusable_stderr_has_only_the_existing_bounded_fixed_category_fallback(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = {"error": {"source": "annotation", "code": "rate_limited"}}
    delivery = _delivery(account_home, monkeypatch, body, status=429)
    attempts: list[bytes] = []

    class FailedError:
        @property
        def buffer(self) -> FailedError:
            return self

        def write(self, record: bytes) -> int:
            attempts.append(record)
            raise OSError(_PRIVATE)

        def flush(self) -> None:
            raise OSError(_PRIVATE)

    with monkeypatch.context() as patch:
        patch.setattr(sys, "stderr", FailedError())
        exit_code = delivery.invoke(_ARGS)
    assert exit_code == 1 and tuple(capsys.readouterr()) == ("", "")
    assert attempts == [
        _json(body) + b"\n",
        _json(
            {
                "error": {"source": "cli", "code": "output_failed"},
                "request_outcome": "report_received",
            }
        )
        + b"\n",
    ]
    assert len(delivery.wire.requests) == 1


def test_annotation_uses_one_existing_ten_second_budget_and_five_second_phases(
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
    assert tuple(capsys.readouterr()) == ((_json(_receipt()) + b"\n").decode(), "")
    assert len(budgets) == 1 and 9.9 <= budgets[0] <= 10.0
    delivery.one_request("/v1/observation/annotations", _BODY)


@asynccontextmanager
async def _t013_service(
    tmp_path: Path,
    account_home: Path,
    patch: pytest.MonkeyPatch,
    backend_index: int,
    family_index: int,
) -> AsyncIterator[tuple[Any, Any, list[str]]]:
    """Compose real Core/v3 and authenticated service, replacing physical I/O only."""
    helpers = _evidence._t014_service_helpers(patch)
    helpers._t014_core_helpers(patch)
    core = importlib.import_module("tests.contract.test_annotation_runtime")
    module = helpers._t009_module()
    config = helpers._CONFIGS[family_index]
    created, _ = helpers._t009_runtime_spy(module, patch)
    owner = helpers.PrivateBootstrap.acquire(config)
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
        lifespan = helpers.AppLifespan(app)
        assert (await lifespan.start())["type"] == "lifespan.startup.complete"
        assert len(created) == 1
        async with core.case(
            tmp_path,
            core.BACKEND_FIXTURE_FACTORIES[backend_index],
            attach=False,
            owner=created[0],
        ) as case:
            path = tmp_path / "runtime.db"
            target = core.capture_terminal_target(
                path,
                session_id=case.probe.session_id,
                policy=case.probe.policy,
                expected_schema_version=3,
            )
            assert target is not None

            async def terminal_opener() -> Any:
                assert case.probe.closed.is_set(), "terminal access preceded close ACK"
                return await core.open_terminal_reader(target)

            case.terminal_opener = terminal_opener
            await case.attach()
            service = helpers.ActiveEvidenceService(
                app, config, token, SimpleNamespace(journal=case.probe.journal), path
            )
            for name in ("retrieve", "resolve_record"):
                original = getattr(case.probe.journal, name)

                async def observed(
                    value: object, *, call: Any = original, kind: str = name
                ) -> Any:
                    assert service.serving.get(), (
                        "CLI retrieval bypassed authenticated HTTP"
                    )
                    service.queries.append(kind)
                    return await call(value)

                patch.setattr(case.probe.journal, name, observed)

            sqlite = importlib.import_module("sqlite3")
            original_connect = sqlite.connect
            terminal_connections: list[str] = []

            def connect(database: str, *args: Any, **kwargs: Any) -> Any:
                assert case.probe.closed.is_set(), (
                    "active retrieval opened another database"
                )
                assert kwargs.get("uri") is True
                assert database.endswith("?mode=ro&cache=private")
                terminal_connections.append(database)
                return original_connect(database, *args, **kwargs)

            patch.setattr(sqlite, "connect", connect)

            def forbidden(*args: object, **kwargs: object) -> None:
                pytest.fail("annotation opened another backend or RX reader")

            patch.setattr(case.fixture.backend, "open", forbidden)
            patch.setattr(case.fixture.connection, "events", forbidden)
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


@pytest.mark.parametrize("session", ["x\0y", "x" * 257, "é" * 129])
def test_t013_receipt_session_bounds_apply_even_when_reference_identity_matches(
    session: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = _receipt()
    receipt["session_id"] = receipt["reference"]["session_id"] = session
    delivery = _delivery(account_home, monkeypatch, receipt)
    assert delivery.invoke(_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("family_index", [0, 1], ids=["ipv4", "ipv6"])
async def test_t013_authenticated_annotation_active_and_closed_v3_retrieval(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend_index: int,
    family_index: int,
) -> None:
    async with _t013_service(
        tmp_path, account_home, monkeypatch, backend_index, family_index
    ) as (service, case, terminal_connections):
        bridge = _evidence.ActiveBridge(service, monkeypatch)
        session = case.probe.session_id.value
        before, after = bytes(range(256)), b"ambient\0\xffafter assertion"
        await case.fixture.connection.emit_rx(before, timestamp=17)
        first = await asyncio.wait_for(case.probe.rx_commits.get(), 3)
        assert first.sequence == 1
        case.clock.advance(700)
        text = " build e\u0301; external SWD flash asserted\r\n\t "
        receipt = await bridge.console(
            capsys, "annotate", "--session", session, "--text", text
        )
        expected_annotation = {
            "kind": "client_annotation",
            "sequence": 2,
            "assertion_class": "client_assertion",
            "client_surface": "cli",
            "attribution_basis": "client_asserted",
            "clock_origin_id": case.clock.origin_id,
            "received_at_ns": 700,
            "text": text,
        }
        assert receipt == {
            "run_id": case.active.run_id.value,
            "session_id": session,
            "reference": {"session_id": session, "sequence": 2},
            "annotation": expected_annotation,
        }
        assert len(bridge.requests) == 1 and service.queries == []
        assert bridge.requests[0].url.raw_path == b"/v1/observation/annotations"
        assert bridge.requests[0].content == _json(
            {"session_id": session, "text": text, "client_surface": "cli"}
        )
        await case.fixture.connection.emit_rx(after, timestamp=901)
        assert (await asyncio.wait_for(case.probe.rx_commits.get(), 3)).sequence == 3
        record = await bridge.console(
            capsys, "evidence record", "--session", session, "--sequence", "2"
        )
        assert record["page"]["records"] == [expected_annotation]
        page = await bridge.page(capsys)
        records = page["page"]["records"]
        assert [r["sequence"] for r in records] == [0, 1, 2, 3]
        assert records[2] == expected_annotation
        assert [
            base64.b64decode(r["payload_base64"])
            for r in records
            if r["kind"] == "rx_bytes"
        ] == [before, after]
        assert [
            r["observed_at"]["value"] for r in records if r["kind"] == "rx_bytes"
        ] == [17, 901]
        assert service.queries == ["resolve_record", "retrieve"]
        assert terminal_connections == [] and not case.probe.closed.is_set()
        assert (
            case.fixture.backend.open_calls
            == case.fixture.connection.consumer_calls
            == 1
        )
        detached = await bridge.console(capsys, "detach")
        assert detached["runtime"]["owner_settled"] is True
        assert detached["runtime"]["physical_release_confirmed"] is True
        assert detached["runtime"]["recorder_close_confirmed"] is True
        assert case.probe.closed.is_set()
        terminal_record = await bridge.console(
            capsys, "evidence record", "--session", session, "--sequence", "2"
        )
        assert terminal_record == record
        terminal_page = await bridge.page(capsys)
        assert terminal_page["page"]["records"][:-1] == records
        assert terminal_page["page"]["records"][-1]["kind"] == "segment_ended"
        assert len(terminal_connections) == 2
        assert service.queries == ["resolve_record", "retrieve"]
        assert case.owner.evidence_read_cleanup_confirmed


@pytest.mark.parametrize("surface", ["Cli", "Core", "ｃｌｉ", "http\0"])
def test_t015_retrieved_surface_declaration_is_not_case_folded_or_normalized(
    surface: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _evidence._report(
        records=[_evidence._t012_annotation(client_surface=surface)]
    )
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    assert delivery.invoke(_evidence._PAGE_ARGS) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1


@pytest.mark.parametrize("size", [_LIMIT - 1, _LIMIT, _LIMIT + 1])
def test_t015_maximum_escaped_text_and_independent_raw_response_bound(
    size: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    text = "\x1f" * 1024
    extra = len(_json(text)) - len(_json(_TEXT))
    receipt = _sized_receipt(size - extra)
    receipt["annotation"]["text"] = text
    assert len(_json(receipt)) == size
    delivery = _delivery(account_home, monkeypatch, receipt)
    assert delivery.invoke([*_ARGS, "--text", text]) == (0 if size <= _LIMIT else 5)
    if size <= _LIMIT:
        assert tuple(capsys.readouterr()) == ((_json(receipt) + b"\n").decode(), "")
    else:
        _local(capsys.readouterr(), "invalid_response", phase="unknown")
    delivery.one_request("/v1/observation/annotations", {**_BODY, "text": text})


@pytest.mark.parametrize(
    "text",
    [
        "é",
        "e\u0301",
        " \r\n\t ",
        ' {"verified":true,"author":"root","timestamp":-1} ',
        "external SWD flash succeeded; /private/build; $(never-execute)",
    ],
)
def test_t015_asserted_actions_and_identity_remain_unchanged_text_only(
    text: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = _receipt()
    receipt["annotation"]["text"] = text
    delivery = _delivery(account_home, monkeypatch, _reverse(receipt))
    assert delivery.invoke([*_ARGS, "--text", text]) == 0
    assert tuple(capsys.readouterr()) == ((_json(receipt) + b"\n").decode(), "")
    delivery.one_request("/v1/observation/annotations", {**_BODY, "text": text})
    assert delivery.wire.requests[0].content == _json({**_BODY, "text": text})


@pytest.mark.parametrize(
    "option",
    [
        "--client-surface",
        "--author",
        "--principal",
        "--pid",
        "--timestamp",
        "--received-at-ns",
        "--clock-origin-id",
    ],
)
def test_t015_cli_cannot_override_declared_identity_or_core_insertion_time(
    option: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _commands._block_preparation(api, monkeypatch)
    assert _evidence._command(api, [*_ARGS, option, _PRIVATE]) == 2
    _local(capsys.readouterr(), "invalid_arguments")
    assert attempts == []


@pytest.mark.parametrize(
    "key,value",
    [
        ("author", "root"),
        ("verified", True),
        ("pid", 1),
        ("timestamp", "2026-01-01T00:00:00Z"),
        ("client_time_ns", 0),
        ("record_version", 3),
        ("provenance", {}),
    ],
)
@pytest.mark.parametrize("command", ["record", "page"])
def test_t015_retrieved_core_assertion_cannot_promote_identity_or_client_time(
    key: str,
    value: object,
    command: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record = _evidence._t012_annotation(**{key: value})
    report = _evidence._report(records=[record])
    delivery = Delivery(account_home, monkeypatch, body=_json(report))
    args = _evidence._RECORD_ARGS if command == "record" else _evidence._PAGE_ARGS
    assert delivery.invoke(args) == 5
    _local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(delivery.wire.requests) == 1
    assert delivery.imports == [] and delivery.reads == ["credential"]


@pytest.mark.parametrize("raw_bytes", [768, 769], ids=["cursor1024", "cursor1026"])
def test_t015_core_assertion_page_retains_cursor_cap_and_opaque_manual_continuation(
    raw_bytes: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
    assert 1 <= len(session.encode()) <= 256
    document["session_id"] = session
    token = base64.urlsafe_b64encode(_json(document)).decode().rstrip("=")
    assert len(token) == (1024 if raw_bytes == 768 else 1026)
    report = _evidence._report(
        records=[_evidence._t012_annotation(sequence=3)],
        snapshot_end_exclusive=9,
        continuation=token,
        truncated=True,
        charged_bytes=333,
    )
    report["session_id"] = session
    delivery = Delivery(account_home, monkeypatch, body=_json(_reverse(report)))
    incoming = "A" * 1024  # lexical only: the service decides input semantics
    args = [*_evidence._PAGE_ARGS, "--session", session, "--cursor", incoming]
    assert delivery.invoke(args) == (0 if raw_bytes == 768 else 5)
    if raw_bytes == 768:
        assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    else:
        _local(capsys.readouterr(), "invalid_response", phase="unknown")
    delivery.one_request(
        "/v1/evidence/page",
        {
            "session_id": session,
            "start_inclusive": None,
            "end_exclusive": None,
            "max_records": 32,
            "max_charged_bytes": 65536,
            "cursor": incoming,
        },
    )


def test_t015_annotation_page413_preserves_cursor_for_explicit_smaller_request(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    token = _evidence._cursor()
    rejected = {"error": {"source": "evidence", "code": "delivery_too_large"}}
    delivery = Delivery(account_home, monkeypatch, body=_json(rejected), status=413)
    args = [*_evidence._PAGE_ARGS, "--cursor", token]
    assert delivery.invoke(args) == 4
    assert tuple(capsys.readouterr()) == ("", (_json(rejected) + b"\n").decode())
    assert len(delivery.wire.requests) == 1 and delivery.wire.stream.closed
    report = _evidence._report(
        records=[_evidence._t012_annotation(sequence=3)],
        snapshot_end_exclusive=9,
        continuation=_evidence._cursor(next_sequence=4),
        truncated=True,
        charged_bytes=333,
    )
    delivery.wire.status = 200
    delivery.wire.stream = _transport._Stream([_json(report)])
    assert (
        delivery.invoke([*args, "--max-records", "1", "--max-charged-bytes", "333"])
        == 0
    )
    assert tuple(capsys.readouterr()) == ((_json(report) + b"\n").decode(), "")
    assert len(delivery.wire.requests) == 2 and delivery.wire.stream.closed
    # Every request is attributable to a separate, explicit invocation.
    assert delivery.reads == ["credential", "credential"] and delivery.imports == []
    for request in delivery.wire.requests:
        assert request.url.raw_path == b"/v1/evidence/page"
    import json

    first, second = [json.loads(r.content) for r in delivery.wire.requests]
    assert first["cursor"] == second["cursor"] == token
    assert (first["max_records"], first["max_charged_bytes"]) == (32, 65536)
    assert (second["max_records"], second["max_charged_bytes"]) == (1, 333)


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_index", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("family_index", [0, 1], ids=["ipv4", "ipv6"])
async def test_t015_core_origin_assertion_retrieves_through_http_cli_active_and_terminal(
    tmp_path: Path,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend_index: int,
    family_index: int,
) -> None:
    async with _t013_service(
        tmp_path, account_home, monkeypatch, backend_index, family_index
    ) as (service, case, terminal_connections):
        bridge = _evidence.ActiveBridge(service, monkeypatch)
        case.clock.advance(123)
        text = ' e\u0301\r\n {"author":"root","verified":true,"received_at_ns":0} '
        receipt = await case.insert(text, "core")
        assert receipt.reference.sequence == 1
        expected = {
            "kind": "client_annotation",
            "sequence": 1,
            "assertion_class": "client_assertion",
            "client_surface": "core",
            "attribution_basis": "client_asserted",
            "clock_origin_id": case.clock.origin_id,
            "received_at_ns": 123,
            "text": text,
        }
        assert bridge.requests == [] and service.queries == []
        options = ("--session", case.probe.session_id.value, "--sequence", "1")
        record = await bridge.console(capsys, "evidence record", *options)
        assert record["page"]["records"] == [expected]
        page = await bridge.page(capsys)
        assert page["page"]["records"][1] == expected
        assert terminal_connections == [] and service.queries == [
            "resolve_record",
            "retrieve",
        ]
        await bridge.console(capsys, "detach")
        assert case.probe.closed.is_set()
        assert await bridge.console(capsys, "evidence record", *options) == record
        terminal_page = await bridge.page(capsys)
        assert terminal_page["page"]["records"][1] == expected
        assert len(terminal_connections) == 2
        assert service.queries == ["resolve_record", "retrieve"]
        assert all(
            r.url.raw_path != b"/v1/observation/annotations" for r in bridge.requests
        )
        assert (
            case.fixture.backend.open_calls
            == case.fixture.connection.consumer_calls
            == 1
        )
        assert case.owner.evidence_read_cleanup_confirmed
