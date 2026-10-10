"""T006/T009: real Typer grammar and direct console-wrapper privacy contracts.

Catch eager callback preparation, permissive/global-option parsing, default port
or environment configuration, extra options, unsafe framework error rendering and
lost public Typer interrupts. No HTTP exchange or installed process is tested here.
"""

import importlib
import json
import os
import socket
import sys
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import typer
from typer.testing import CliRunner, Result

from dutchmate_cli import context

_PRIVATE = "private-argv-credential-exception-local-sentinel"
_HELP_ARGS = [
    [], ["--help"], ["status", "--help"],
    ["--host", _PRIVATE, "--port", "0"],
    ["--host", _PRIVATE, "--port", "0", "status", "--help"],
    ["--host=::1", "--port=65535", "status", "--help"],
]
_BAD_ARGS = [
    ["status"],
    ["--host", _PRIVATE, "--port", "80", "status"],
    ["--host", "localhost", "--port", "80", "status"],
    ["--host", "::ffff:127.0.0.1", "--port", "80", "status"],
    ["--port", "0", "status"], ["--port", "65536", "status"],
    ["--port", _PRIVATE, "status"], ["--port"], ["--host"],
    ["status", "--port", "80"],
    ["--port", "80", "status", "--host", "::1"],
    ["--port", "80", "status", "status"],
    ["--port", "80", "status", _PRIVATE],
    ["--port", "80", _PRIVATE], ["--port", "80", "statuz"],
    ["--private-option", _PRIVATE, "status"],
]
_EXTRA_OPTIONS = [
    ["--install-completion"], ["--show-completion"], ["--version"],
    ["--url", _PRIVATE], ["--token", _PRIVATE], ["--credential", _PRIVATE],
    ["--timeout", "10"], ["--json"], ["--output-mode", _PRIVATE],
    ["--env", _PRIVATE], ["-p", "80"],
]


def _api() -> Any:
    try:
        return importlib.import_module("dutchmate_cli.main")
    except ModuleNotFoundError as error:
        if error.name == "dutchmate_cli.main":
            pytest.fail("T009 command/console implementation is absent", pytrace=False)
        raise


def _block_preparation(
    api: Any, monkeypatch: pytest.MonkeyPatch, *, platform: bool = True,
) -> list[str]:
    attempted: list[str] = []

    def forbidden(boundary: str) -> Callable[..., Any]:
        def fail(*args: Any, **kwargs: Any) -> Any:
            attempted.append(boundary)
            raise AssertionError("unexpected client preparation")
        return fail

    # Tripwires also count attempts if a future broad exception handler catches
    # the failure. They never allow account/file/socket work to proceed.
    for name in ("open", "mkdir", "geteuid"):
        monkeypatch.setattr(os, name, forbidden(name))
    if sys.platform in {"linux", "darwin"}:
        import pwd

        monkeypatch.setattr(pwd, "getpwuid", forbidden("passwd"))
    monkeypatch.setattr(context, "read_credential", forbidden("credential"))
    if hasattr(api, "read_credential"):
        monkeypatch.setattr(api, "read_credential", forbidden("credential"))
    if platform:
        monkeypatch.setattr(context, "_check_platform", forbidden("platform"))
    monkeypatch.setattr(socket, "getaddrinfo", forbidden("resolver"))
    monkeypatch.setattr(socket.socket, "connect", forbidden("socket"))
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden("socket"))
    for client in (httpx.Client, httpx.AsyncClient):
        for method in ("request", "send"):
            monkeypatch.setattr(client, method, forbidden("HTTP"))
    return attempted


def _console(api: Any, args: list[str]) -> int:
    # Permit either ordinary console convention without prescribing a private
    # implementation: a returned code or SystemExit. Exceptions otherwise escape.
    previous_hook = sys.excepthook
    try:
        try:
            result = api.main(args)
        except SystemExit as error:
            result = error.code
    finally:
        # Typer.__call__ installs its global hook even for a caught exception.
        # Own that harness side effect so direct-console tests remain isolated.
        sys.excepthook = previous_hook
    if result is None:
        return 0
    assert type(result) is int
    return result


def _runner(api: Any, args: list[str]) -> Result:
    assert isinstance(api.app, typer.Typer)
    # CliRunner bypasses the console wrapper. Public parser exceptions may escape
    # here, while the direct wrapper must translate them to fixed JSON diagnostics.
    return CliRunner().invoke(
        api.app, args, prog_name="dutchmate", standalone_mode=False,
    )


def _local_error(stdout: str, stderr: str, code: str) -> None:
    assert stdout == ""
    assert stderr.endswith("\n") and stderr.count("\n") == 1
    assert json.loads(stderr) == {
        "error": {"source": "cli", "code": code},
        "request_outcome": "not_submitted",
    }
    assert _PRIVATE not in stderr and "\x1b" not in stderr


def _grammar_rejected(result: Result) -> None:
    if result.exception is None or isinstance(result.exception, SystemExit):
        assert result.exit_code == 2 or (
            result.exception is None and result.return_value == 2
        )
        _local_error(result.stdout, result.stderr, "invalid_arguments")
    else:
        # Distinguish grammar/domain-argument rejection from an arbitrary failure.
        if isinstance(result.exception, typer.TyperException):
            assert result.exception.exit_code == 2
        else:
            assert isinstance(result.exception, context.CliFailure)
            assert result.exception.kind is context.CliFailureKind.INVALID_ARGUMENTS
        assert result.stdout == "" and result.stderr == ""


@pytest.mark.parametrize("entry", ["runner", "console"])
@pytest.mark.parametrize("args", _HELP_ARGS)
def test_help_and_no_command_are_pure_even_after_root_callback(
    args: list[str], entry: str, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    if entry == "runner":
        result = _runner(api, args)
        code, stdout, stderr = result.exit_code, result.stdout, result.stderr
        assert result.exception is None
    else:
        code = _console(api, args)
        stdout, stderr = capsys.readouterr()
    assert code == 0 and stderr == "" and stdout
    assert "status" in stdout and "--help" in stdout
    if "status" not in args:
        assert "--host" in stdout and "--port" in stdout
    for forbidden in ("--install-completion", "--show-completion", "--version",
                      "--url", "--token", "--credential", "--output-mode", _PRIVATE):
        assert forbidden not in stdout
    assert "\x1b" not in stdout
    assert attempts == []


@pytest.mark.parametrize("entry", ["runner", "console"])
@pytest.mark.parametrize("args", [[], ["--help"], ["status", "--help"]])
def test_help_remains_resource_free_on_unsupported_platform(
    args: list[str], entry: str, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    monkeypatch.setattr(sys, "platform", "win32")
    if entry == "runner":
        result = _runner(api, args)
        assert result.exit_code == 0 and result.stdout and result.stderr == ""
        assert result.exception is None
    else:
        assert _console(api, args) == 0
        stdout, stderr = capsys.readouterr()
        assert stdout and stderr == ""
    assert attempts == []


@pytest.mark.parametrize("args", _BAD_ARGS)
def test_cli_runner_rejects_invalid_target_and_input_without_preparation(
    args: list[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    _grammar_rejected(_runner(api, args))
    assert attempts == []


@pytest.mark.parametrize("args", _BAD_ARGS)
def test_console_invalid_arguments_are_fixed_private_json(
    args: list[str], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    assert _console(api, args) == 2
    stdout, stderr = capsys.readouterr()
    _local_error(stdout, stderr, "invalid_arguments")
    assert _PRIVATE not in caplog.text and attempts == []


@pytest.mark.parametrize("option", _EXTRA_OPTIONS)
@pytest.mark.parametrize("after_command", [False, True])
def test_unsupported_options_are_not_added_at_root_or_status(
    option: list[str], after_command: bool, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    args = (["--port", "80", "status", *option] if after_command else
            [*option, "--port", "80", "status"])
    _grammar_rejected(_runner(api, args))
    assert _console(api, args) == 2
    _local_error(*capsys.readouterr(), "invalid_arguments")
    assert attempts == []


@pytest.mark.parametrize("args", [
    ["--port", "1", "status"], ["--port=80", "status"],
    ["--host", "::1", "--port", "65535", "status"],
    ["--host=127.0.0.1", "--port=80", "status"],
    ["--host", _PRIVATE, "--host", "::1", "--port", "80", "status"],
    ["--port", "0", "--port", "80", "status"],
])
def test_valid_global_options_reach_credential_once_without_network(
    args: list[str], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch, platform=False)
    reads = 0

    def unavailable() -> str:
        nonlocal reads
        reads += 1
        raise context.CliFailure(context.CliFailureKind.CREDENTIAL_UNAVAILABLE)

    monkeypatch.setattr(context, "read_credential", unavailable)
    if hasattr(api, "read_credential"):
        monkeypatch.setattr(api, "read_credential", unavailable)
    assert _console(api, args) == 3
    _local_error(*capsys.readouterr(), "credential_unavailable")
    assert reads == 1 and attempts == []


def test_environment_never_supplies_required_target(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    for name, value in (("DUTCHMATE_PORT", "80"), ("PORT", "80"),
                        ("DUTCHMATE_HOST", "127.0.0.1"), ("DUTCHMATE_URL", _PRIVATE),
                        ("DUTCHMATE_TOKEN", _PRIVATE)):
        monkeypatch.setenv(name, value)
    assert _console(api, ["status"]) == 2
    _local_error(*capsys.readouterr(), "invalid_arguments")
    assert attempts == []


@pytest.mark.parametrize("case,code,exit_code", [
    ("usage", "invalid_arguments", 2), ("framework", "internal_failure", 1),
    ("abort", "interrupted", 130), ("returned_interrupt", "interrupted", 130),
    ("outer_interrupt", "interrupted", 130), ("unexpected", "internal_failure", 1),
])
def test_console_normalizes_public_framework_failures_and_interrupts_privately(
    case: str, code: str, exit_code: int, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    rendered: list[str] = []

    class PrivateError(typer.TyperException):
        def __str__(self) -> str:
            rendered.append("str")
            raise AssertionError("exception text must not be used")

        def format_message(self) -> str:
            rendered.append("format")
            raise AssertionError("exception text must not be formatted")

        def show(self, *args: Any, **kwargs: Any) -> None:
            rendered.append("show")
            raise AssertionError("exception display must not be called")

    probe = typer.Typer(
        add_completion=False, pretty_exceptions_enable=False,
        pretty_exceptions_show_locals=False, rich_markup_mode=None,
    )

    @probe.callback()
    def root() -> None:
        pass

    @probe.command("probe")
    def command() -> None:
        private_local = _PRIVATE
        if case in {"usage", "framework"}:
            failure = PrivateError(private_local)
            failure.exit_code = 2 if case == "usage" else 1
            raise failure
        if case == "abort":
            raise typer.Abort()
        if case == "returned_interrupt":
            # Real pinned Typer turns this into returned130 in non-standalone
            # mode; CliRunner alone does not exercise the console's translation.
            raise KeyboardInterrupt()
        raise RuntimeError(private_local)

    if case == "outer_interrupt":
        class InterruptedTyper(typer.Typer):
            def __call__(self, *args: Any, **kwargs: Any) -> Any:
                raise KeyboardInterrupt()
        probe = InterruptedTyper()
    monkeypatch.setattr(api, "app", probe)
    assert _console(api, ["probe"]) == exit_code
    _local_error(*capsys.readouterr(), code)
    assert rendered == [] and attempts == [] and _PRIVATE not in caplog.text


def test_entry_import_does_not_prepare_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    importlib.reload(api)
    assert attempts == []


@pytest.mark.parametrize("state,exit_code", [
    ("inactive", 0), ("failed", 0), ("remote_error", 4),
])
def test_status_routes_validated_client_record_without_reinterpreting_state(
    state: str, exit_code: int, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch, platform=False)
    reads = 0
    calls = 0
    profile = {
        "format_version": 1, "dut": {"id": "fixture/board", "name": "Board α"},
        "backend": {"kind": "basic_serial", "expected_device": "fixture-device"},
        "uart": {"baud_rate": 57600, "data_bits": 7, "parity": "even", "stop_bits": 2,
                 "hardware_flow_control": True, "software_flow_control": False},
        "open_lines": {"dtr": "deasserted", "rts": "driver_managed"},
        "policy": {"uart_rx_enabled": True, "evidence_recording_enabled": True,
                   "uart_tx_enabled": False, "semantic_control_enabled": False,
                   "automatic_reconnect_enabled": False},
        "session_policy": {"max_retained_records": 100, "max_retained_charged_bytes": 65536,
                           "max_record_charged_bytes": 8192, "max_database_pages": 128,
                           "max_retrieval_page_records": 11,
                           "max_retrieval_page_charged_bytes": 16384},
    }
    if state == "remote_error":
        payload: dict[str, Any] = {
            "error": {"source": "request", "code": "authentication_required"},
        }
    else:
        payload = {"service_state": "ready", "runtime": {
            "state": state, "run_id": "run-1" if state == "failed" else None,
            "profile": profile if state == "failed" else None,
            "session_id": None, "acquisition": None, "stop_intent": "none",
            "terminal_reason": "startup_failure" if state == "failed" else None,
            "primary_issue": {"source": "preparation", "code": "device_not_found"}
                             if state == "failed" else None,
            "cleanup_issues": [], "owner_settled": True,
            "physical_release_confirmed": True, "recorder_close_confirmed": True,
            "attach_admissible": True,
        }}
    record = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"

    def credential() -> str:
        nonlocal reads
        reads += 1
        return "a" * 64

    async def exchange(
        *, endpoint: context.Endpoint, command: str, credential: str, delivery: Any,
    ) -> tuple[int, bytes]:
        nonlocal calls
        calls += 1
        assert (endpoint.host, endpoint.port, command, credential) == (
            "::1", 80, "status", "a" * 64,
        )
        assert delivery.request_outcome == "not_submitted"
        delivery.request_outcome = "report_received"
        return exit_code, record

    monkeypatch.setattr(context, "read_credential", credential)
    monkeypatch.setattr(api.client, "exchange", exchange)
    assert _console(api, ["--host", "::1", "--port", "80", "status"]) == exit_code
    stdout, stderr = capsys.readouterr()
    assert (stdout, stderr) == (
        (record.decode("utf-8"), "") if exit_code == 0 else ("", record.decode("utf-8"))
    )
    assert reads == calls == 1 and attempts == []


def _lifecycle_help(api: Any, command: str) -> None:
    # Prove the real grammar recognizes the command before invalid-input cases:
    # an unknown command's exit2 must not masquerade as path validation.
    result = _runner(api, [command, "--help"])
    assert result.exit_code == 0, "T012 lifecycle command wiring is absent"
    assert result.exception is None and result.stderr == ""
    assert command in result.stdout


@pytest.mark.parametrize("command", ["attach", "detach"])
@pytest.mark.parametrize("entry", ["runner", "console"])
def test_t011_lifecycle_help_needs_no_target_paths_or_preparation(
    command: str, entry: str, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    if entry == "runner":
        _lifecycle_help(api, command)
    else:
        assert _console(api, [command, "--help"]) == 0
        stdout, stderr = capsys.readouterr()
        assert command in stdout and "--help" in stdout and stderr == ""
        if command == "attach":
            assert "--profile" in stdout and "--journal" in stdout
    assert attempts == []


_T011_BAD_ARGS = [
    ["attach"], ["detach"],
    ["--port", "80", "attach"],
    ["--port", "80", "attach", "--profile", "/profile"],
    ["--port", "80", "attach", "--journal", "/journal"],
    ["--port", "80", "attach", "/profile", "/journal"],
    ["--port", "80", "attach", "--profile", "relative", "--journal", "/journal"],
    ["--port", "80", "attach", "--profile", "/profile", "--journal", "~/journal"],
    ["--port", "80", "attach", "--profile", "/p\x00x", "--journal", "/journal"],
    ["--port", "80", "attach", "--profile", "/" + "é" * 2048, "--journal", "/journal"],
    ["--port", "80", "attach", "--profile", "/profile", "--journal", "/" + "a" * 4096],
    ["attach", "--port", "80", "--profile", "/profile", "--journal", "/journal"],
    ["--port", "80", "attach", "--profile", "/profile", "--journal", "/journal", _PRIVATE],
    ["--port", "80", "attach", "--profile", "/profile", "--journal", "/journal", "detach"],
    ["--port", "80", "attach", "--profile", "/profile", "--journal", "/journal", "--tx"],
    ["--port", "80", "detach", "--profile", "/profile"],
    ["--port", "80", "detach", "--journal", "/journal"],
    ["--port", "80", "detach", _PRIVATE],
    ["--port", "80", "detach", "detach"],
    ["--port", "80", "detach", "--reconnect"],
    ["--port", "80", "detach", "--autostart"],
]


@pytest.mark.parametrize("args", _T011_BAD_ARGS)
def test_t011_lifecycle_bad_arguments_are_private_and_precede_io(
    args: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    command = "attach" if "attach" in args else "detach"
    _lifecycle_help(api, command)
    _grammar_rejected(_runner(api, args))
    assert _console(api, args) == 2
    _local_error(*capsys.readouterr(), "invalid_arguments")
    assert attempts == []


@pytest.mark.parametrize("args", [
    ["--port=80", "attach", "--profile=/missing/profile", "--journal=/missing/journal"],
    ["--host", "::1", "--port", "80", "attach", "--profile", "/a/../profile",
     "--journal", "/literal/$HOME/~/journal"],
    ["--port", "80", "attach", "--profile", "/" + "a" * 4095, "--journal", "/journal"],
    ["--port", "80", "attach", "--profile", "/" + "é" * 2047 + "a", "--journal", "/journal"],
    ["--port", "80", "attach", "--profile", "relative", "--profile", "/last",
     "--journal", "/first", "--journal", "/last-journal"],
    ["--port", "80", "detach"],
])
def test_t011_valid_lifecycle_grammar_reads_credential_once_without_file_checks(
    args: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from pathlib import Path

    api = _api()
    attempts = _block_preparation(api, monkeypatch, platform=False)
    _lifecycle_help(api, "attach" if "attach" in args else "detach")
    reads = 0

    def unavailable() -> str:
        nonlocal reads
        reads += 1
        raise context.CliFailure(context.CliFailureKind.CREDENTIAL_UNAVAILABLE)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("CLI attach/detach must perform lexical validation only")

    monkeypatch.setattr(context, "read_credential", unavailable)
    for method in ("stat", "exists", "resolve", "open", "read_bytes", "read_text", "mkdir"):
        monkeypatch.setattr(Path, method, forbidden)
    assert _console(api, args) == 3
    _local_error(*capsys.readouterr(), "credential_unavailable")
    assert reads == 1 and attempts == []


@pytest.mark.parametrize("args", [
    ["--port", "80", "service"], ["--port", "80", "observation", "attach"],
    ["--port", "80", "monitor"], ["--port", "80", "handoff", _PRIVATE],
])
def test_t011_no_service_or_later_workflow_commands_are_added(
    args: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _block_preparation(api, monkeypatch)
    assert _console(api, args) == 2
    _local_error(*capsys.readouterr(), "invalid_arguments")
    assert attempts == []


@pytest.mark.parametrize("profile,journal", [
    ("/missing/Profile source.toml", "/missing/new journal.sqlite3"),
    ("/literal/$HOME/~/../profile", "/literal/$HOME/~/../journal"),
    ("/" + "é" * 2047 + "a", "/journal"),
])
def test_t011_attach_hands_exact_unexpanded_path_strings_to_http_client(
    profile: str, journal: str, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pathlib import Path

    api = _api()
    attempts = _block_preparation(api, monkeypatch, platform=False)
    _lifecycle_help(api, "attach")
    calls = 0

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("CLI must not inspect explicit Profile/journal paths")

    async def exchange(**kwargs: Any) -> tuple[int, bytes]:
        nonlocal calls
        calls += 1
        assert kwargs["command"] == "attach"
        assert kwargs["paths"].profile_path == profile and kwargs["paths"].journal_path == journal
        kwargs["delivery"].request_outcome = "report_received"
        return 4, b'{"error":{"source":"profile","code":"missing_file"}}\n'

    monkeypatch.setattr(context, "read_credential", lambda: "a" * 64)
    monkeypatch.setattr(api.client, "exchange", exchange)
    for method in ("stat", "exists", "resolve", "open", "read_bytes", "read_text"):
        monkeypatch.setattr(Path, method, forbidden)
    assert _console(api, ["--port", "80", "attach", "--profile", profile, "--journal", journal]) == 4
    stdout, stderr = capsys.readouterr()
    assert stdout == "" and json.loads(stderr) == {"error": {"source": "profile", "code": "missing_file"}}
    assert calls == 1 and attempts == []
