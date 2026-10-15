"""009 T030: installed Monitor delivery with guarded native service/CLI children.

Reuse 007/008 package/account/physical guards. Only external RX, append faults and
deliberately invalid peer replies are controlled; runtime/HTTP/CLI remain real.
"""

import base64
import json
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from apps.cli.tests import test_cli_evidence_process as support
    from apps.cli.tests import test_cli_process as process
    from apps.cli.tests.test_cli_process import _Installed
else:
    from importlib import import_module

    support = import_module("test_cli_evidence_process")
    process = import_module("test_cli_process")
    _Installed = process._Installed

package_artifacts = process.package_artifacts
stack_artifacts = support.stack_artifacts
installed_stack = support.installed_stack
native_service_helper = process.native_service_helper

_PATTERN = b"\x00\xffM\xfe"
_PREFIX = b"noise\x00\xff"
_SUFFIX = b"M\xfeTAIL\x00\xff"

# Extend the existing child before run_service, retaining every account/physical
# tripwire, real backend fixture, SQLite worker and read-only terminal check.
_EXTENSION = r"""
from dutchmate_core import evidence, monitor
import dutchmate_service.monitor_http
audit.update(starts=0, start_attempts=0, ends=0, pending_end=False,
             monitor_reports=0, emissions=0, last_outcome=None, http_drained=False)
end_release = asyncio.Event()
async def monitor_control():
    while True:
        if control_path.exists():
            command = json.loads(control_path.read_bytes())
            control_path.unlink()
            if "fault" in command:
                audit["fault"] = command["fault"]
            if command.get("release_end"):
                end_release.set()
            if command.get("emit") or "emit_hex" in command:
                data = bytes.fromhex(command["emit_hex"]) if "emit_hex" in command else ambient
                await fixture.connection.emit_rx(data, timestamp=9)
                audit["emissions"] += 1
            publish()
        await asyncio.sleep(0.01)  # External fixture control only, not Monitor timing.
control = monitor_control
tracked_append = sqlite_evidence.SqliteEvidenceJournal.append
async def marker_append(journal, draft):
    fault = audit["fault"]
    if isinstance(draft, evidence.PendingOperationStartedEvidence):
        audit["start_attempts"] += 1
        publish()
        if fault == "start-journal":
            failure = evidence.JournalFailure(evidence.JournalOperation.APPEND,
                evidence.JournalFailureKind.BUSY, private)
            failure.add_note(private)
            raise failure from OSError(private)
        if fault == "start-unexpected":
            raise RuntimeError(private)
    record = await tracked_append(journal, draft)
    if isinstance(record, model.OperationStartedEvidence):
        audit["starts"] += 1
    if isinstance(record, model.OperationEndedEvidence):
        audit["ends"] += 1
        if fault == "hold-end":
            audit["pending_end"] = True
            publish()
            await end_release.wait()
            audit["pending_end"] = False
        if fault == "end-unconfirmed":
            publish()
            raise evidence.JournalFailure(evidence.JournalOperation.APPEND,
                evidence.JournalFailureKind.IO_FAILURE, private)
    publish()
    return record
sqlite_evidence.SqliteEvidenceJournal.append = marker_append
actual_monitor_response = app.monitor_response
def monitor_response(report):
    from starlette.responses import Response
    original = actual_monitor_response(report)
    audit["monitor_reports"] += 1
    audit["last_outcome"] = report.outcome.value
    publish()
    fault = audit["fault"]
    if fault not in {"bad-json", "extra-field", "wrong-error", "raw-overflow", "fitting-bound", "remote413"}:
        return original
    value, status = json.loads(original.body), 200
    if fault == "bad-json":
        body = ('{"private":"' + private).encode()
    elif fault == "extra-field":
        value["private"] = private
        body = encode(value)
    elif fault == "wrong-error":
        status, body = 500, encode({"error":{"source":"journal","code":private}})
    elif fault in {"raw-overflow", "fitting-bound"}:
        value["run_id"] = "é\n\\"
        value["run_id"] += "a" * (1048576 - len(encode(value)) + (fault == "raw-overflow"))
        body = encode(value)
        assert len(body) == 1048576 + (fault == "raw-overflow")
    else:
        status, body = 413, encode({"error":{"source":"monitor","code":"delivery_too_large"}})
    return Response(body, status_code=status, media_type="application/json", headers={"Cache-Control":"no-store"})
app.monitor_response = monitor_response
tracked_startup = uvicorn.Server.startup
async def monitor_startup(self, sockets=None):
    await tracked_startup(self, sockets=sockets)
    audit["product_files"].extend([monitor.__file__, dutchmate_service.monitor_http.__file__])
    publish()
uvicorn.Server.startup = monitor_startup
tracked_drain = server._ControlledServer._wait_tasks_to_complete
async def monitor_drain(self):
    await tracked_drain(self)
    audit["http_drained"] = True
    publish()
server._ControlledServer._wait_tasks_to_complete = monitor_drain
"""
_HOOK = "try:\n    server.run_service("
assert support._SERVICE_SCRIPT.count(_HOOK) == 1
_SERVICE_SCRIPT = support._SERVICE_SCRIPT.replace(_HOOK, _EXTENSION + "\n" + _HOOK)
_CLI_GUARD = (
    process._GUARD
    + r"""
def monitor_final():
    audit["core_imported"] = any(name == "dutchmate_core" or name.startswith("dutchmate_core.") for name in sys.modules)
    audit["monitor_file"] = getattr(sys.modules.get("dutchmate_cli.monitor"), "__file__", None)
atexit.register(monitor_final)
"""
)


@pytest.fixture(autouse=True)
def monitor_children(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(support, "_SERVICE_SCRIPT", _SERVICE_SCRIPT)
    monkeypatch.setattr(process, "_GUARD", _CLI_GUARD)


@contextmanager
def _stack(
    installed: _Installed, helper: Any, home: Path, root: Path, host: str, backend: int
) -> Iterator[Any]:
    with support._service(installed, helper, home, root, host, backend) as service:
        try:
            yield service
        finally:
            if service.process.poll() is None and service.audit().get("pending_end"):
                service.control(release_end=True)


def _args(service: Any, session: str, timeout: int = 4000) -> list[str]:
    return [
        "--host",
        service.host,
        "--port",
        str(service.port),
        "monitor",
        "--session",
        session,
        "--condition-base64",
        base64.b64encode(_PATTERN).decode(),
        "--timeout-ms",
        str(timeout),
        "--max-rx-bytes",
        "64",
    ]


def _one_request(audit: dict[str, Any], service: Any) -> None:
    assert audit["credential_reads"] == 1
    authority = (
        f"[::1]:{service.port}"
        if service.host == "::1"
        else f"127.0.0.1:{service.port}"
    )
    assert audit["requests"] == [
        {
            "method": "POST",
            "path": "/v1/observation/monitor",
            "host": authority,
            "authorization_count": 1,
        }
    ]
    assert audit["core_imported"] is False


def _report(
    result: tuple[int, bytes, bytes, dict[str, Any]],
    service: Any,
    installed: _Installed,
) -> dict[str, Any]:
    code, out, err, audit = result
    assert code == 0 and err == b"", (code, err)
    _one_request(audit, service)
    assert out.endswith(b"\n") and out.count(b"\n") == 1 and len(out) <= 1048577
    value: dict[str, Any] = json.loads(out)
    assert list(value) == [
        "run_id",
        "session_id",
        "operation_id",
        "provenance",
        "outcome",
        "started_record",
        "ended_record",
        "window",
        "examined_rx_bytes",
        "observer_loss_records",
        "match",
        "clock",
        "durability",
        "end_failure",
    ]
    assert (
        out
        == json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
        + b"\n"
    )
    assert Path(audit["monitor_file"]).is_relative_to(installed.python.parent.parent)
    assert not Path(audit["monitor_file"]).is_relative_to(process._REPO)
    process._private(out, err, service.token, str(service.home).encode())
    return value


def _read(
    installed: _Installed,
    service: Any,
    root: Path,
    session: str,
    sequence: int | None = None,
) -> dict[str, Any]:
    command = "page" if sequence is None else "record"
    args = support._args(service.host, service.port, command, session)
    if sequence is not None:
        args[args.index("--sequence") + 1] = str(sequence)
    code, out, err, audit = support._run(installed, root, service.home, args)
    assert code == 0 and err == b"", (code, err)
    return support._delivered(out, command, service.host, service.port, audit)


def _active(helper: Any, service: Any) -> None:
    status, headers, body = helper._status(service.host, service.port, service.token)
    assert status == 200 and headers[b"cache-control"] == b"no-store"
    assert json.loads(body)["runtime"]["state"] == "active"
    audit = service.audit()
    assert audit["opens"] == audit["consumers"] == 1
    assert audit["closes"] == audit["recorder_closes"] == 0


def test_t030_parent_guards_remain_active() -> None:
    process.test_t018_parent_physical_and_real_account_tripwires_are_active()


@pytest.mark.parametrize("direct", [False, True], ids=["entry", "main-args"])
@pytest.mark.parametrize("case", ["help", "missing", "bad-base64", "bad-timeout"])
def test_t030_installed_monitor_help_and_invalid_inputs_are_resource_free(
    installed_stack: _Installed,
    account_home: Path,
    tmp_path: Path,
    direct: bool,
    case: str,
) -> None:
    # Catches credential/network work before static help or lexical validation.
    args = ["monitor", "--help"] if case == "help" else ["monitor"]
    if case in {"bad-base64", "bad-timeout"}:
        args += [
            "--session",
            process._PRIVATE,
            "--condition-base64",
            "Zh==" if case == "bad-base64" else "AA==",
            "--timeout-ms",
            "true" if case == "bad-timeout" else "1",
            "--max-rx-bytes",
            "64",
        ]
    code, out, err, audit = support._run(
        installed_stack,
        tmp_path / "cli",
        account_home,
        args,
        mode="no_io",
        direct=direct,
    )
    assert audit["credential_reads"] == 0 and audit["requests"] == []
    assert audit["core_imported"] is False
    if case == "help":
        assert code == 0 and err == b"" and b"--condition-base64" in out
    else:
        assert code == 2 and out == b""
        process._failure(err, "invalid_arguments")


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("outcome", ["matched", "timeout", "end-unconfirmed"])
def test_t030_installed_binary_monitor_and_active_terminal_markers(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    outcome: str,
) -> None:
    # Catches missing installed composition, a second reader, lost binary/trailing
    # data, pre-boundary matching, fabricated end ACKs and marker projection loss.
    with _stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, journal = support._attach(
            installed_stack, s, account_home, tmp_path / "attach"
        )
        args = _args(s, session, 100 if outcome == "timeout" else 4000)
        if outcome == "timeout":
            args[args.index("--condition-base64") + 1] = (
                "AAECAw=="  # Already in initial RX only.
            )
        if outcome == "end-unconfirmed":
            s.fault("end-unconfirmed")
        with process._cli(
            installed_stack, tmp_path / "monitor", account_home, args
        ) as client:
            s.wait("starts", 1)
            if outcome != "timeout":
                s.control(emit_hex=_PREFIX.hex())
                s.wait("rx_commits", 2)
                s.control(emit_hex=_SUFFIX.hex())
            report = _report(client.finish(), s, installed_stack)
        assert report["session_id"] == session and report["started_record"] == {
            "session_id": session,
            "sequence": 2,
        }
        assert report["outcome"] == ("timeout" if outcome == "timeout" else "matched")
        assert report["observer_loss_records"] == 0
        assert report["provenance"]["backend_observation_timestamp_domain"][
            "observer"
        ] == ("host" if backend == 0 else "device")
        if outcome == "timeout":
            assert report["match"] is None and report["examined_rx_bytes"] == 0
            assert report["window"] == {"start_inclusive": 3, "end_exclusive": 3}
        else:
            assert report["match"] == {
                "start": {"sequence": 3, "byte_offset": 5},
                "end": {"sequence": 4, "byte_offset_exclusive": 2},
            }
            assert report["examined_rx_bytes"] == 9
            assert report["window"] == {"start_inclusive": 3, "end_exclusive": 5}
        assert report["durability"] == (
            "end_unconfirmed" if outcome == "end-unconfirmed" else "complete"
        )
        assert report["end_failure"] == (
            {"source": "journal", "code": "io_failure"}
            if outcome == "end-unconfirmed"
            else None
        )
        assert (report["ended_record"] is None) is (outcome == "end-unconfirmed")
        s.fault("normal")
        _active(native_service_helper, s)
        s.control(emit=True)
        s.wait("emissions", 1 if outcome == "timeout" else 3)
        s.wait("rx_commits", 2 if outcome == "timeout" else 4)
        active = _read(installed_stack, s, tmp_path / "active", session)
        records = active["page"]["records"]
        starts = [r for r in records if r["kind"] == "operation_started"]
        ends = [r for r in records if r["kind"] == "operation_ended"]
        assert len(starts) == len(ends) == 1
        start, end = starts[0], ends[0]
        assert start["operation_id"] == end["operation_id"] == report["operation_id"]
        assert base64.b64decode(start["condition_base64"], validate=True) == (
            b"\0\1\2\3" if outcome == "timeout" else _PATTERN
        )
        for key in (
            "outcome",
            "window",
            "match",
            "clock",
            "examined_rx_bytes",
            "observer_loss_records",
        ):
            assert end[key] == report[key]
        if outcome != "end-unconfirmed":
            assert report["ended_record"] == {
                "session_id": session,
                "sequence": end["sequence"],
            }
        assert _read(installed_stack, s, tmp_path / "start-record", session, 2)["page"][
            "records"
        ] == [start]
        payloads = [
            base64.b64decode(r["payload_base64"], validate=True)
            for r in records
            if r["kind"] == "rx_bytes"
        ]
        assert payloads == [
            support._PAYLOAD,
            *([] if outcome == "timeout" else [_PREFIX, _SUFFIX]),
            support._AMBIENT,
        ]
        code, out, err, _ = support._run(
            installed_stack,
            tmp_path / "detach",
            account_home,
            ["--host", host, "--port", str(s.port), "detach"],
        )
        assert (
            code == 0
            and err == b""
            and json.loads(out)["runtime"]["recorder_close_confirmed"]
        )
        before = journal.read_bytes()
        terminal = _read(installed_stack, s, tmp_path / "terminal", session)
        assert terminal["run_id"] == active["run_id"] == report["run_id"]
        assert terminal["page"]["records"][:-1] == records
        assert terminal["page"]["records"][-1]["kind"] == "segment_ended"
        assert _read(
            installed_stack, s, tmp_path / "end-record", session, end["sequence"]
        )["page"]["records"] == [end]
        assert journal.read_bytes() == before
        audit = s.wait("terminal_closes", 2)
        assert audit["terminal_opens"] == 2 and audit["validation_in_transaction"]
        assert all(
            audit[key] == 2
            for key in ("query_only_set", "query_only_read", "begins", "rollbacks")
        )
        assert (
            audit["opens"]
            == audit["consumers"]
            == audit["closes"]
            == audit["recorder_closes"]
            == 1
        )


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize(
    "mode,expected",
    [
        ("stale", "authentication_required"),
        ("host", "host_rejected"),
        ("origin", "origin_rejected"),
        ("browser", "origin_rejected"),
    ],
)
def test_t030_installed_monitor_security_precedes_marker_work(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    mode: str,
    expected: str,
) -> None:
    # Catches admission/marker work before authentication and browser rejection.
    with _stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = support._attach(
            installed_stack, s, account_home, tmp_path / "attach"
        )
        alternate = s.token
        if mode == "stale":
            alternate = (b"0" if s.token[:1] != b"0" else b"1") + s.token[1:]
            (account_home / ".local/state/dutchmate/service/credential").write_bytes(
                alternate + b"\n"
            )
        code, out, err, audit = support._run(
            installed_stack,
            tmp_path / "cli",
            account_home,
            _args(s, session),
            mode="normal" if mode == "stale" else mode,
        )
        assert code == 4 and out == b""
        assert json.loads(err) == {"error": {"source": "request", "code": expected}}
        _one_request(audit, s)
        process._private(
            out,
            err,
            s.token,
            alternate,
            str(account_home).encode(),
            base64.b64encode(_PATTERN),
        )
        assert (
            s.audit()["start_attempts"] == s.audit()["starts"] == s.audit()["ends"] == 0
        )
        _active(native_service_helper, s)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("phase", ["before", "pending", "repeated", "output"])
def test_t030_installed_sigint_receipts_do_not_cancel_monitor_or_capture(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    phase: str,
) -> None:
    # Catches cancelling owned Monitor with its client, false receipts or retries.
    with _stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = support._attach(
            installed_stack, s, account_home, tmp_path / "attach"
        )
        mode = {
            "before": "before_interrupt",
            "pending": "normal",
            "repeated": "repeat_interrupt",
            "output": "output_interrupt",
        }[phase]
        with process._cli(
            installed_stack,
            tmp_path / "cli",
            account_home,
            _args(s, session, 4000 if phase == "pending" else 50),
            mode=mode,
        ) as client:
            if phase == "pending":
                s.wait("starts", 1)
            else:
                client.wait_event(
                    {
                        "before": "before-request",
                        "repeated": "waiting",
                        "output": "report-received",
                    }[phase]
                )
            client.process.send_signal(signal.SIGINT)
            if phase == "repeated":
                client.wait_event("cleanup")
                client.process.send_signal(signal.SIGINT)
            code, out, err, audit = client.finish()
        assert code == 130 and out == b""
        process._failure(
            err,
            "interrupted",
            "not_submitted"
            if phase == "before"
            else "report_received"
            if phase == "output"
            else "unknown",
        )
        process._private(
            out, err, s.token, str(account_home).encode(), base64.b64encode(_PATTERN)
        )
        if phase == "before":
            assert audit["credential_reads"] == 1 and audit["requests"] == []
            assert s.audit()["starts"] == 0
        else:
            _one_request(audit, s)
        if phase == "pending":
            assert s.audit()["monitor_reports"] == 0
            s.control(emit_hex=_PATTERN.hex())
            assert s.wait("monitor_reports", 1)["last_outcome"] == "matched"
        _active(native_service_helper, s)
        s.control(emit=True)
        s.wait("emissions", 2 if phase == "pending" else 1)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("loss", ["cancel", "sigint"])
def test_t030_installed_client_loss_and_repeated_service_signals_join_pending_marker(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    loss: str,
) -> None:
    # Catches forced shutdown, early credential/marker release or abandoned append.
    with _stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = support._attach(
            installed_stack, s, account_home, tmp_path / "attach"
        )
        s.fault("hold-end")
        with process._cli(
            installed_stack, tmp_path / "cli", account_home, _args(s, session)
        ) as client:
            s.wait("starts", 1)
            s.control(emit_hex=_PATTERN.hex())
            s.wait("pending_end", True)
            client.process.send_signal(
                signal.SIGTERM if loss == "cancel" else signal.SIGINT
            )
            code, out, err, audit = client.finish()
        assert out == b""
        if loss == "cancel":
            assert code == -signal.SIGTERM and err == b""
        else:
            assert code == 130
            process._failure(err, "interrupted", "unknown")
            _one_request(audit, s)
        process._private(out, err, s.token, str(account_home).encode())
        s.process.send_signal(signal.SIGINT)
        # Wait for actual native HTTP drain. Lifespan must still join the owned
        # marker even though its client and HTTP task have already disappeared.
        s.wait("http_drained", True)
        s.process.send_signal(signal.SIGINT)
        state = account_home / ".local/state/dutchmate/service"
        assert s.process.poll() is None and s.audit()["pending_end"]
        assert s.audit()["recorder_closes"] == 0
        assert (state / "credential").read_bytes() == s.token + b"\n"
        assert (
            json.loads((state / "owner.json").read_bytes())["cleanup_confirmed"]
            is False
        )
        s.control(release_end=True)
        final = s.finish(None)
        assert final["outcome"] == "returned" and final["force_exit"] is False
        assert (
            final["monitor_reports"]
            == final["ends"]
            == final["recorder_closes"]
            == final["closes"]
            == 1
        )
        assert not (state / "credential").exists()
        assert json.loads((state / "owner.json").read_bytes()) == {
            "version": 1,
            "cleanup_confirmed": True,
        }
        s.private_output(s.token, process._PRIVATE.encode(), base64.b64encode(_PATTERN))


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("closed", ["stdout", "stderr", "stdout stderr"])
def test_t030_installed_closed_monitor_pipes_preserve_exit_receipts(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    closed: str,
) -> None:
    # Catches success/traceback after output loss or a pipe cancelling acquisition.
    with _stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = support._attach(
            installed_stack, s, account_home, tmp_path / "attach"
        )
        code, out, err, audit = support._run(
            installed_stack,
            tmp_path / "cli",
            account_home,
            _args(s, "foreign-session" if closed == "stderr" else session, 1),
            closed=closed,
        )
        assert code == 1 and out == b""
        if closed == "stdout":
            process._failure(err, "output_failed", "report_received")
        else:
            assert err == b""
        _one_request(audit, s)
        _active(native_service_helper, s)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
def test_t030_installed_private_start_faults_and_malformed_peer_reports(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
) -> None:
    # Catches private exception transport, loosening closed reply validation,
    # response overflow truncation, or treating complete delivery as operation success.
    with _stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session, _ = support._attach(
            installed_stack, s, account_home, tmp_path / "attach"
        )
        faults = [
            "start-journal",
            "start-unexpected",
            "bad-json",
            "extra-field",
            "wrong-error",
            "raw-overflow",
            "remote413",
            "fitting-bound",
        ]
        for fault in faults:
            s.fault(fault)
            result = support._run(
                installed_stack, tmp_path / fault, account_home, _args(s, session, 1)
            )
            code, out, err, audit = result
            _one_request(audit, s)
            process._private(
                out,
                err,
                s.token,
                str(account_home).encode(),
                base64.b64encode(_PATTERN),
            )
            if fault == "fitting-bound":
                _report(result, s, installed_stack)
                assert len(out) == 1048577
            elif fault in {"start-journal", "start-unexpected", "remote413"}:
                assert code == 4 and out == b""
                assert json.loads(err) == {
                    "error": {
                        "source": "journal"
                        if fault == "start-journal"
                        else "monitor"
                        if fault == "remote413"
                        else "service",
                        "code": "busy"
                        if fault == "start-journal"
                        else "delivery_too_large"
                        if fault == "remote413"
                        else "internal_failure",
                    }
                }
            else:
                assert code == 5 and out == b""
                process._failure(err, "invalid_response", "unknown")
        assert (
            s.audit()["start_attempts"] == 8
            and s.audit()["starts"] == s.audit()["ends"] == 6
        )
        s.fault("normal")
        _active(native_service_helper, s)
