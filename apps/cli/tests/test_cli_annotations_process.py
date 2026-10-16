"""010 T020: installed annotation flows with independent child safety guards.

Reuse non-editable 007/008 installs and account/physical guards. Only the DUT,
clock, durable-ACK gates and deliberate delivery faults are test controlled.
"""

import base64
import json
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

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

# Exactly1024 UTF-8 bytes, including a decomposed accent and untouched CR/LF/tab.
_TEXT = "é" * 508 + "e\u0301\r\n\t !"
_TIME = 5_000_000_000

_EXTENSION = r"""
from dutchmate_core import evidence, annotation
import dutchmate_service.annotation_http
audit.update(annotation_attempts=0, annotations=0, pending_annotation=False,
             annotation_reports=0, emissions=0, clock_ns=5000000000,
             http_drained=False)
ack_release = asyncio.Event()
class Clock(composition.MonotonicMonitorClock):
    def now_ns(self):
        return audit["clock_ns"]
composition.MonotonicMonitorClock = Clock
async def annotation_control():
    while True:
        if control_path.exists():
            command = json.loads(control_path.read_bytes())
            control_path.unlink()
            if "fault" in command:
                audit["fault"] = command["fault"]
            if command.get("release_annotation"):
                ack_release.set()
            if "advance_ns" in command:
                audit["clock_ns"] += command["advance_ns"]
            for _ in range(command.get("emit_count", 1 if command.get("emit") else 0)):
                await fixture.connection.emit_rx(ambient, timestamp=9)
                audit["emissions"] += 1
            publish()
        await asyncio.sleep(0.01)  # Test external control, never application timing.
control = annotation_control
tracked_append = sqlite_evidence.SqliteEvidenceJournal.append
async def annotation_append(journal, draft):
    fault = audit["fault"]
    if isinstance(draft, evidence.PendingClientAnnotationEvidence):
        audit["annotation_attempts"] += 1
        publish()
        if fault == "journal-busy":
            failure = evidence.JournalFailure(evidence.JournalOperation.APPEND,
                evidence.JournalFailureKind.BUSY, private)
            failure.add_note(private)
            raise failure from OSError(private)
        if fault == "unexpected":
            raise RuntimeError(private)
    record = await tracked_append(journal, draft)
    if isinstance(record, model.ClientAnnotationEvidence):
        audit["annotations"] += 1
        if fault == "hold-ack":
            audit["pending_annotation"] = True
            publish()
            await ack_release.wait()
            audit["pending_annotation"] = False
        if fault == "ambiguous-ack":
            publish()
            raise evidence.JournalFailure(evidence.JournalOperation.APPEND,
                evidence.JournalFailureKind.IO_FAILURE, private)
    publish()
    return record
sqlite_evidence.SqliteEvidenceJournal.append = annotation_append
actual_annotation_response = app.annotation_response
def annotation_response(receipt):
    from starlette.responses import Response
    original = actual_annotation_response(receipt)
    audit["annotation_reports"] += 1
    publish()
    fault = audit["fault"]
    if fault not in {"bad-json", "extra-field", "raw-overflow", "fitting-bound", "remote413"}:
        return original
    value, status = json.loads(original.body), 200
    if fault == "bad-json":
        body = ('{"private":"' + private).encode()
    elif fault == "extra-field":
        value["private"] = private
        body = encode(value)
    elif fault in {"raw-overflow", "fitting-bound"}:
        value["run_id"] = "é\n\\"
        value["run_id"] += "a" * (1048576 - len(encode(value)) + (fault == "raw-overflow"))
        body = encode(value)
        assert len(body) == 1048576 + (fault == "raw-overflow")
    else:
        status, body = 413, encode({"error":{"source":"annotation","code":"delivery_too_large"}})
    return Response(body, status_code=status, media_type="application/json", headers={"Cache-Control":"no-store"})
app.annotation_response = annotation_response
tracked_startup = uvicorn.Server.startup
async def annotation_startup(self, sockets=None):
    await tracked_startup(self, sockets=sockets)
    audit["product_files"].extend([annotation.__file__, dutchmate_service.annotation_http.__file__])
    publish()
uvicorn.Server.startup = annotation_startup
tracked_drain = server._ControlledServer._wait_tasks_to_complete
async def annotation_drain(self):
    await tracked_drain(self)
    audit["http_drained"] = True
    publish()
server._ControlledServer._wait_tasks_to_complete = annotation_drain
"""
_HOOK = "try:\n    server.run_service("
assert support._SERVICE_SCRIPT.count(_HOOK) == 1
_SERVICE_SCRIPT = support._SERVICE_SCRIPT.replace(_HOOK, _EXTENSION + "\n" + _HOOK)
_CLI_GUARD = (
    process._GUARD
    + r"""
tracked_send = httpx.AsyncClient.send
async def annotation_send(self, request, *args, **kwargs):
    if request.url.path == "/v1/observation/annotations":
        audit["annotation_request"] = json.loads(request.content)
    response = await tracked_send(self, request, *args, **kwargs)
    audit["http_status"] = response.status_code
    audit["cache_control"] = response.headers.get("cache-control")
    if mode == "response_lost":
        await response.aclose()
        raise httpx.ReadError(private, request=request)
    return response
httpx.AsyncClient.send = annotation_send
def annotation_final():
    audit["core_imported"] = any(name == "dutchmate_core" or name.startswith("dutchmate_core.") for name in sys.modules)
    audit["annotation_file"] = getattr(sys.modules.get("dutchmate_cli.annotation"), "__file__", None)
    audit["cwd"] = os.getcwd()
atexit.register(annotation_final)
"""
)


@pytest.fixture(autouse=True)
def annotation_children(monkeypatch: pytest.MonkeyPatch) -> None:
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
            if service.process.poll() is None and service.audit().get(
                "pending_annotation"
            ):
                service.control(release_annotation=True)


def _args(service: Any, session: str, text: str = _TEXT) -> list[str]:
    return [
        "--host",
        service.host,
        "--port",
        str(service.port),
        "annotate",
        "--session",
        session,
        "--text",
        text,
    ]


def _one_request(audit: dict[str, Any], service: Any, session: str, text: str) -> None:
    authority = (
        f"[::1]:{service.port}"
        if service.host == "::1"
        else f"127.0.0.1:{service.port}"
    )
    assert audit["credential_reads"] == 1
    assert audit["requests"] == [
        {
            "method": "POST",
            "path": "/v1/observation/annotations",
            "host": authority,
            "authorization_count": 1,
        }
    ]
    assert audit["annotation_request"] == {
        "session_id": session,
        "text": text,
        "client_surface": "cli",
    }
    assert audit["core_imported"] is False
    assert not Path(audit["cwd"]).is_relative_to(process._REPO)


def _receipt(
    result: tuple[int, bytes, bytes, dict[str, Any]],
    service: Any,
    installed: _Installed,
    session: str,
    text: str = _TEXT,
) -> dict[str, Any]:
    code, out, err, audit = result
    assert code == 0 and err == b"", (code, err)
    _one_request(audit, service, session, text)
    assert audit["http_status"] == 200 and audit["cache_control"] == "no-store"
    assert out.endswith(b"\n") and out.count(b"\n") == 1 and len(out) <= 1048577
    value: dict[str, Any] = json.loads(out)
    assert list(value) == ["run_id", "session_id", "reference", "annotation"]
    assert type(value["run_id"]) is str and value["run_id"]
    assert value["session_id"] == session
    annotation = value["annotation"]
    assert list(annotation) == [
        "kind",
        "sequence",
        "assertion_class",
        "client_surface",
        "attribution_basis",
        "clock_origin_id",
        "received_at_ns",
        "text",
    ]
    assert annotation == {
        "kind": "client_annotation",
        "sequence": annotation["sequence"],
        "assertion_class": "client_assertion",
        "client_surface": "cli",
        "attribution_basis": "client_asserted",
        "clock_origin_id": annotation["clock_origin_id"],
        "received_at_ns": service.audit()["clock_ns"],
        "text": text,
    }
    assert (
        type(annotation["sequence"]) is int
        and 0 <= annotation["sequence"] <= 9223372036854775806
    )
    assert type(annotation["received_at_ns"]) is int
    assert str(UUID(annotation["clock_origin_id"])) == annotation["clock_origin_id"]
    assert value["reference"] == {
        "session_id": session,
        "sequence": annotation["sequence"],
    }
    assert (
        out
        == json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
        + b"\n"
    )
    assert Path(audit["annotation_file"]).is_relative_to(installed.python.parent.parent)
    assert not Path(audit["annotation_file"]).is_relative_to(process._REPO)
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
    assert audit["core_imported"] is False
    return support._delivered(out, command, service.host, service.port, audit)


def _active(helper: Any, service: Any) -> None:
    status, headers, body = helper._status(service.host, service.port, service.token)
    assert status == 200 and headers[b"cache-control"] == b"no-store"
    assert json.loads(body)["runtime"]["state"] == "active"
    audit = service.audit()
    assert audit["opens"] == audit["consumers"] == 1
    assert audit["closes"] == audit["recorder_closes"] == 0


def _error(
    result: tuple[int, bytes, bytes, dict[str, Any]],
    service: Any,
    session: str,
    text: str,
    source: str,
    code: str,
    status: int,
) -> None:
    exit_code, out, err, audit = result
    assert exit_code == 4 and out == b""
    assert (
        err
        == json.dumps(
            {"error": {"source": source, "code": code}}, separators=(",", ":")
        ).encode()
        + b"\n"
    )
    _one_request(audit, service, session, text)
    assert audit["http_status"] == status and audit["cache_control"] == "no-store"
    process._private(out, err, service.token, str(service.home).encode(), text.encode())


def test_t020_parent_guards_remain_active() -> None:
    process.test_t018_parent_physical_and_real_account_tripwires_are_active()


@pytest.mark.parametrize("direct", [False, True], ids=["entry", "main-args"])
@pytest.mark.parametrize(
    "case", ["root-help", "help", "missing", "empty", "1025-bytes", "surface"]
)
def test_t020_installed_help_and_invalid_annotation_do_no_io(
    installed_stack: _Installed,
    account_home: Path,
    tmp_path: Path,
    direct: bool,
    case: str,
) -> None:
    # Catches resource access before help/input validation or an attribution override.
    args = (
        ["--help"]
        if case == "root-help"
        else ["annotate", "--help"]
        if case == "help"
        else ["--port", "1", "annotate"]
    )
    if case in {"empty", "1025-bytes", "surface"}:
        args += [
            "--session",
            process._PRIVATE,
            "--text",
            ""
            if case == "empty"
            else "é" * 512 + "x"
            if case == "1025-bytes"
            else process._PRIVATE,
        ]
        if case == "surface":
            args += ["--client-surface", "core"]
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
    if case in {"help", "root-help"}:
        assert code == 0 and err == b""
        assert (b"--text" if case == "help" else b"annotate") in out
    else:
        assert code == 2 and out == b""
        process._failure(err, "invalid_arguments")


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("evict", [False, True], ids=["retained", "expired"])
def test_t020_installed_exact_annotations_and_ambient_rx_active_terminal(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    evict: bool,
) -> None:
    # Catches missing installed v3 composition/projection, normalization, a second
    # reader, lost binary RX, false retention success or writable terminal access.
    assert len(_TEXT.encode()) == 1024
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
        receipt = _receipt(
            support._run(
                installed_stack, tmp_path / "annotate", account_home, _args(s, session)
            ),
            s,
            installed_stack,
            session,
        )
        assert receipt["reference"] == {"session_id": session, "sequence": 2}
        s.control(emit=True)
        s.wait("rx_commits", 2)
        short = _receipt(
            support._run(
                installed_stack,
                tmp_path / "one-byte",
                account_home,
                _args(s, session, "\t"),
            ),
            s,
            installed_stack,
            session,
            "\t",
        )
        assert short["annotation"]["sequence"] == 4
        assert (
            short["annotation"]["clock_origin_id"]
            == receipt["annotation"]["clock_origin_id"]
        )
        active = _read(installed_stack, s, tmp_path / "active", session)
        records = active["page"]["records"]
        assert [r["kind"] for r in records] == [
            "segment_started",
            "rx_bytes",
            "client_annotation",
            "rx_bytes",
            "client_annotation",
        ]
        assert records[2] == receipt["annotation"] and records[4] == short["annotation"]
        assert [
            base64.b64decode(r["payload_base64"], validate=True)
            for r in records
            if r["kind"] == "rx_bytes"
        ] == [support._PAYLOAD, support._AMBIENT]
        assert _read(installed_stack, s, tmp_path / "active-record", session, 2)[
            "page"
        ]["records"] == [receipt["annotation"]]
        assert s.audit()["terminal_opens"] == 0
        _active(native_service_helper, s)
        if evict:
            s.control(emit_count=105)
            s.wait("rx_commits", 107)
            expired = _read(
                installed_stack, s, tmp_path / "expired-active", session, 2
            )["page"]
            assert expired["outcome"] == "expired" and expired["records"] == []
            assert expired["expired_range"] == {
                "start_inclusive": 2,
                "end_exclusive": 3,
            }
            assert expired["retention_marker"]["discarded_record_count"] == 10
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
        terminal = _read(installed_stack, s, tmp_path / "terminal", session, 2)
        assert terminal["run_id"] == active["run_id"] == receipt["run_id"]
        assert terminal["page"]["outcome"] == ("expired" if evict else "complete")
        assert terminal["page"]["records"] == ([] if evict else [receipt["annotation"]])
        page = _read(installed_stack, s, tmp_path / "terminal-page", session)["page"]
        if evict:
            assert page["outcome"] == "partial" and page["truncated"]
            assert page["retention_marker"]["discarded_record_count"] == 11
        else:
            assert (
                page["records"][:-1] == records
                and page["records"][-1]["kind"] == "segment_ended"
            )
        assert journal.read_bytes() == before
        audit = s.wait("terminal_closes", 2)
        assert audit["terminal_opens"] == 2 and audit["validation_in_transaction"]
        assert all(
            audit[k] == 2
            for k in ("query_only_set", "query_only_read", "begins", "rollbacks")
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
def test_t020_installed_rate_budget_is_core_owned_and_exactly_one_second(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
) -> None:
    # Catches a per-CLI/surface budget, delayed retry, wrong window edge or reset.
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
        for n in range(10):
            text = f"attempt {n}"
            _receipt(
                support._run(
                    installed_stack,
                    tmp_path / str(n),
                    account_home,
                    _args(s, session, text),
                ),
                s,
                installed_stack,
                session,
                text,
            )
        _error(
            support._run(
                installed_stack, tmp_path / "limited", account_home, _args(s, session)
            ),
            s,
            session,
            _TEXT,
            "annotation",
            "rate_limited",
            429,
        )
        assert s.audit()["annotation_attempts"] == s.audit()["annotations"] == 10
        s.control(advance_ns=1_000_000_000)
        s.wait("clock_ns", _TIME + 1_000_000_000)
        _receipt(
            support._run(
                installed_stack, tmp_path / "boundary", account_home, _args(s, session)
            ),
            s,
            installed_stack,
            session,
        )
        assert s.audit()["annotation_attempts"] == s.audit()["annotations"] == 11
        _active(native_service_helper, s)


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
def test_t020_installed_security_rejects_before_annotation_append(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    mode: str,
    expected: str,
) -> None:
    # Catches annotation admission preceding actual credential/Host/browser gates.
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
        if mode == "stale":
            alternate = (b"0" if s.token[:1] != b"0" else b"1") + s.token[1:]
            (account_home / ".local/state/dutchmate/service/credential").write_bytes(
                alternate + b"\n"
            )
        _error(
            support._run(
                installed_stack,
                tmp_path / "cli",
                account_home,
                _args(s, session),
                mode="normal" if mode == "stale" else mode,
            ),
            s,
            session,
            _TEXT,
            "request",
            expected,
            401 if mode == "stale" else 400 if mode == "host" else 403,
        )
        assert s.audit()["annotation_attempts"] == s.audit()["annotations"] == 0
        _active(native_service_helper, s)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
def test_t020_installed_private_failures_ambiguous_ack_and_closed_peer_receipts(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
) -> None:
    # Catches diagnostic leaks, fabricated absence/references, weakened closed reply
    # validation and truncation or retry after a committed but undelivered claim.
    with _stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        _error(
            support._run(
                installed_stack,
                tmp_path / "no-session",
                account_home,
                _args(s, "unknown"),
            ),
            s,
            "unknown",
            _TEXT,
            "annotation",
            "no_associated_session",
            404,
        )
        session, _ = support._attach(
            installed_stack, s, account_home, tmp_path / "attach"
        )
        _error(
            support._run(
                installed_stack, tmp_path / "foreign", account_home, _args(s, "foreign")
            ),
            s,
            "foreign",
            _TEXT,
            "annotation",
            "session_not_associated",
            409,
        )
        for fault, source, expected_code, status in [
            ("journal-busy", "journal", "busy", 503),
            ("unexpected", "service", "internal_failure", 500),
            ("ambiguous-ack", "journal", "io_failure", 500),
        ]:
            s.fault(fault)
            _error(
                support._run(
                    installed_stack, tmp_path / fault, account_home, _args(s, session)
                ),
                s,
                session,
                _TEXT,
                source,
                expected_code,
                status,
            )
        s.fault("normal")  # End annotation fault injection before evidence delivery.
        assert (
            _read(installed_stack, s, tmp_path / "ambiguous-record", session, 2)[
                "page"
            ]["records"][0]["text"]
            == _TEXT
        )
        for fault in (
            "bad-json",
            "extra-field",
            "raw-overflow",
            "remote413",
            "fitting-bound",
        ):
            s.fault(fault)
            result = support._run(
                installed_stack, tmp_path / fault, account_home, _args(s, session)
            )
            code, out, err, audit = result
            _one_request(audit, s, session, _TEXT)
            process._private(out, err, s.token, str(account_home).encode())
            if fault == "fitting-bound":
                _receipt(result, s, installed_stack, session)
                assert len(out) == 1048577
            elif fault == "remote413":
                _error(
                    result, s, session, _TEXT, "annotation", "delivery_too_large", 413
                )
            else:
                assert code == 5 and out == b""
                process._failure(err, "invalid_response", "unknown")
        assert s.audit()["annotation_attempts"] == 8 and s.audit()["annotations"] == 6
        s.fault("normal")
        _active(native_service_helper, s)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("phase", ["before", "pending", "repeated", "output"])
def test_t020_installed_sigint_keeps_admitted_annotation_owned_without_retry(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    phase: str,
) -> None:
    # Catches waiter cancellation reaching the writer, a false delivery phase or retry.
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
        if phase == "pending":
            s.fault("hold-ack")
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
            _args(s, session),
            mode=mode,
        ) as client:
            if phase == "pending":
                s.wait("pending_annotation", True)
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
        process._private(out, err, s.token, str(account_home).encode(), _TEXT.encode())
        if phase == "before":
            assert audit["credential_reads"] == 1 and audit["requests"] == []
            assert s.audit()["annotation_attempts"] == s.audit()["annotations"] == 0
        else:
            _one_request(audit, s, session, _TEXT)
            if phase == "pending":
                assert (
                    s.audit()["annotation_reports"] == s.audit()["recorder_closes"] == 0
                )
                _error(
                    support._run(
                        installed_stack,
                        tmp_path / "busy",
                        account_home,
                        _args(s, session),
                    ),
                    s,
                    session,
                    _TEXT,
                    "annotation",
                    "busy",
                    409,
                )
                s.control(release_annotation=True)
            s.wait("annotation_reports", 1)
            assert s.audit()["annotation_attempts"] == s.audit()["annotations"] == 1
            s.fault("normal")  # The inherited evidence peer accepts only its faults.
            assert (
                _read(installed_stack, s, tmp_path / "record", session, 2)["page"][
                    "records"
                ][0]["text"]
                == _TEXT
            )
        _active(native_service_helper, s)
        s.control(emit=True)
        s.wait("rx_commits", 2)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("loss", ["stdout", "stdout stderr", "response_lost"])
def test_t020_installed_lost_output_or_response_does_not_retry_or_undo_commit(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    loss: str,
) -> None:
    # Catches treating output/response loss as rollback, success or permission to retry.
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
            _args(s, session),
            mode=loss if loss == "response_lost" else "normal",
            closed="" if loss == "response_lost" else loss,
        )
        assert out == b"" and code == (5 if loss == "response_lost" else 1)
        if loss == "stdout stderr":
            assert err == b""
        else:
            process._failure(
                err,
                "transport_failed" if loss == "response_lost" else "output_failed",
                "unknown" if loss == "response_lost" else "report_received",
            )
        _one_request(audit, s, session, _TEXT)
        process._private(out, err, s.token, str(account_home).encode(), _TEXT.encode())
        assert s.wait("annotation_reports", 1)["annotations"] == 1
        assert s.audit()["annotation_attempts"] == 1
        record = _read(installed_stack, s, tmp_path / "record", session, 2)["page"][
            "records"
        ][0]
        assert record["text"] == _TEXT and record["client_surface"] == "cli"
        assert (
            record["assertion_class"] == "client_assertion"
            and record["attribution_basis"] == "client_asserted"
        )
        _active(native_service_helper, s)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
def test_t020_installed_disconnect_and_service_signals_join_pending_ack(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
) -> None:
    # Catches installed lifespan abandoning committed work or releasing bootstrap early.
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
        s.fault("hold-ack")
        with process._cli(
            installed_stack, tmp_path / "cli", account_home, _args(s, session)
        ) as client:
            s.wait("pending_annotation", True)
            client.process.send_signal(signal.SIGTERM)
            code, out, err, _ = client.finish()
        assert code == -signal.SIGTERM and out == err == b""
        s.process.send_signal(signal.SIGINT)
        s.wait("http_drained", True)
        s.process.send_signal(signal.SIGINT)
        state = account_home / ".local/state/dutchmate/service"
        assert s.process.poll() is None and s.audit()["pending_annotation"]
        assert s.audit()["recorder_closes"] == 0
        assert (state / "credential").read_bytes() == s.token + b"\n"
        assert (
            json.loads((state / "owner.json").read_bytes())["cleanup_confirmed"]
            is False
        )
        s.control(release_annotation=True)
        final = s.finish(None)
        assert final["outcome"] == "returned" and final["force_exit"] is False
        assert (
            final["annotation_attempts"]
            == final["annotations"]
            == final["annotation_reports"]
            == final["closes"]
            == final["recorder_closes"]
            == 1
        )
        assert not (state / "credential").exists()
        assert json.loads((state / "owner.json").read_bytes()) == {
            "version": 1,
            "cleanup_confirmed": True,
        }
        s.private_output(s.token, _TEXT.encode(), process._PRIVATE.encode())
