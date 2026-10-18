"""011 T020: guarded installed Follow flows, never checkout product imports.

Existing non-editable builders/child guards are reused unchanged. Local child
extensions control external RX, submitted-read progress and deliberate peer loss;
no Follow, admission, retention, security or lifetime policy is implemented here.
"""

import ast
import base64
import json
import os
import select
import signal
import time
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

_NEW = bytes(range(256)) + b"\0\xffPASS\r\n"
_TEXT = "installed follow e\u0301\r\n\t"
_LIMIT = 1048576

_EXTENSION = r"""
from dutchmate_core import evidence, follow
import dutchmate_core.follow, dutchmate_service.follow_http
from dutchmate_service.follow_http import FollowStream
audit.update(follow_starts=0, follow_closes=0, follow_jobs=0, follow_pulls=0,
             pending_pull=False, pause_pull=False, held_reads=0, read_slots=0,
             emissions=0, http_drained=False, last_rx_bytes=0)
pull_release, read_release = asyncio.Event(), asyncio.Event()
pull_release.set()
read_jobs, stream_jobs = [], []
tracked_retrieve = sqlite_evidence.SqliteEvidenceJournal.retrieve
async def retrieve(journal, request):
    if audit["fault"] == "follow-query":
        failure = evidence.JournalFailure(evidence.JournalOperation.RETRIEVE,
            evidence.JournalFailureKind.IO_FAILURE, private)
        failure.add_note(private)
        raise failure from OSError(private)
    return await tracked_retrieve(journal, request)
sqlite_evidence.SqliteEvidenceJournal.retrieve = retrieve
tracked_resolve = sqlite_evidence.SqliteEvidenceJournal.resolve_record
async def resolve(journal, request):
    if audit.get("hold_reads"):
        audit["held_reads"] += 1
        audit["read_slots"] = len(runtime_owner._reads)
        publish()
        try:
            await read_release.wait()
        finally:
            audit["held_reads"] -= 1
            publish()
    return await tracked_resolve(journal, request)
sqlite_evidence.SqliteEvidenceJournal.resolve_record = resolve
tracked_append = sqlite_evidence.SqliteEvidenceJournal.append
async def follow_append(journal, draft):
    record = await tracked_append(journal, draft)
    if isinstance(record, model.RxBytesEvidence):
        audit["last_rx_bytes"] = len(record.payload)
    publish()
    return record
sqlite_evidence.SqliteEvidenceJournal.append = follow_append
tracked_start = actual_runtime.start_follow
async def start_follow(owner, request):
    sub = await tracked_start(owner, request)
    audit["follow_starts"] += 1
    pull, close = sub.pull, sub.close
    closed = False
    async def observed_pull():
        audit["follow_pulls"] += 1
        if audit["pause_pull"]:
            audit["pending_pull"] = True
            publish()
            try:
                await pull_release.wait()
            finally:
                audit["pending_pull"] = False
        publish()
        return await pull()
    async def observed_close():
        nonlocal closed
        await close()
        if not closed:
            closed = True
            audit["follow_closes"] += 1
        publish()
    sub.pull, sub.close = observed_pull, observed_close
    publish()
    return sub
actual_runtime.start_follow = start_follow
tracked_job = FollowStream._own
async def job(self, *args, **kwargs):
    stream_jobs.append(self)
    audit["follow_jobs"] += 1
    publish()
    try:
        await tracked_job(self, *args, **kwargs)
    finally:
        stream_jobs.remove(self)
        audit["follow_jobs"] -= 1
        publish()
FollowStream._own = job
async def follow_control():
    while True:
        if control_path.exists():
            command = json.loads(control_path.read_bytes())
            control_path.unlink()
            if "fault" in command:
                audit["fault"] = command["fault"]
            if "pause_pull" in command:
                audit["pause_pull"] = command["pause_pull"]
                if command["pause_pull"]:
                    pull_release.clear()
                else:
                    pull_release.set()
            if command.get("hold_reads"):
                # Wait for the existing initial Follow head to settle; acquire
                # eight real public reads, never manufacture lease/slot state.
                while runtime_owner._reads:
                    await asyncio.sleep(0)
                audit["hold_reads"] = True
                read_release.clear()
                read_jobs[:] = [asyncio.create_task(runtime_owner.read_record(
                    model.EvidenceReference(runtime_owner.status().session_id, 0)))
                    for _ in range(8)]
            if command.get("release_reads"):
                audit["hold_reads"] = False
                read_release.set()
                await asyncio.gather(*read_jobs)
                read_jobs.clear()
                audit["read_slots"] = len(runtime_owner._reads)
            for _ in range(command.get("emit_count", 1 if "emit_hex" in command else 0)):
                data = bytes.fromhex(command["emit_hex"]) if "emit_hex" in command else ambient
                if command.get("oversize"):
                    data = b"\x00\xff" * 524288
                await fixture.connection.emit_rx(data, timestamp=9)
                audit["emissions"] += 1
            if command.get("disconnect"):
                await fixture.connection.disconnect()
            if command.get("abort_peer"):
                # Deliberate delivery loss; real owner cleanup and HTTP abnormal
                # EOF run. No synthetic terminal, alternate route or Core stop.
                for stream in tuple(stream_jobs):
                    stream.cancel()
            publish()
        await asyncio.sleep(0.01)  # External test control only, no product polling.
control = follow_control
tracked_startup = uvicorn.Server.startup
async def follow_startup(self, sockets=None):
    await tracked_startup(self, sockets=sockets)
    audit["product_files"].extend([dutchmate_core.follow.__file__,
        dutchmate_service.follow_http.__file__])
    publish()
uvicorn.Server.startup = follow_startup
tracked_drain = server._ControlledServer._wait_tasks_to_complete
async def follow_drain(self):
    await tracked_drain(self)
    audit["http_drained"] = True
    publish()
server._ControlledServer._wait_tasks_to_complete = follow_drain
"""
_HOOK = "try:\n    server.run_service("
assert support._SERVICE_SCRIPT.count(_HOOK) == 1
_SERVICE_SCRIPT = support._SERVICE_SCRIPT.replace(_HOOK, _EXTENSION + "\n" + _HOOK)
_CLI_GUARD = (
    process._GUARD
    + r"""
tracked_follow_send = httpx.AsyncClient.send
async def follow_send(self, request, *args, **kwargs):
    response = await tracked_follow_send(self, request, *args, **kwargs)
    audit["http_status"] = response.status_code
    audit["cache_control"] = response.headers.get("cache-control")
    audit["content_type"] = response.headers.get("content-type")
    audit["content_encoding"] = response.headers.get("content-encoding")
    return response
httpx.AsyncClient.send = follow_send
def follow_final():
    audit["core_imported"] = any(n == "dutchmate_core" or n.startswith("dutchmate_core.") for n in sys.modules)
    audit["follow_file"] = getattr(sys.modules.get("dutchmate_cli.follow"), "__file__", None)
    audit["cwd"] = os.getcwd()
atexit.register(follow_final)
"""
)


@pytest.fixture(autouse=True)
def follow_children(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(support, "_SERVICE_SCRIPT", _SERVICE_SCRIPT)
    monkeypatch.setattr(process, "_GUARD", _CLI_GUARD)


@contextmanager
def stack(
    installed: _Installed, helper: Any, home: Path, root: Path, host: str, backend: int
) -> Iterator[Any]:
    with support._service(installed, helper, home, root, host, backend) as s:
        try:
            yield s
        finally:
            if s.process.poll() is None:
                s.control(pause_pull=False, release_reads=True)
                s.wait("held_reads", 0)


def args(s: Any, session: str) -> list[str]:
    return ["--host", s.host, "--port", str(s.port), "follow", "--session", session]


@contextmanager
def cli(*arguments: Any, **options: Any) -> Iterator[Any]:
    with process._cli(*arguments, **options) as child:
        try:
            yield child
        finally:
            if child.process.poll() is not None:
                # Reap an already-exited child if an assertion precedes finish;
                # the shared builder already handles still-running children.
                child.process.communicate(timeout=3)


class Stream:
    """Read test-owned OS pipe frames before process/source exit, with watchdogs."""

    def __init__(self, child: Any) -> None:
        self.child = child
        self.buffer = bytearray()
        self.raw: list[bytes] = []
        self.values: list[dict[str, Any]] = []

    def next(self, timeout: float = 4) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        pipe = self.child.process.stdout
        assert pipe is not None
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "installed Follow frame did not arrive incrementally"
            ready, _, _ = select.select([pipe], [], [], remaining)
            assert ready, "installed Follow frame watchdog expired"
            chunk = os.read(pipe.fileno(), 65536)
            assert chunk, "installed Follow ended without expected frame"
            self.buffer.extend(chunk)
            assert len(self.buffer) <= _LIMIT + 1
        line, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        raw = bytes(line) + b"\n"
        value: dict[str, Any] = json.loads(line)
        assert (
            raw
            == json.dumps(
                value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode()
            + b"\n"
        )
        self.raw.append(raw)
        self.values.append(value)
        return value

    def data(self) -> dict[str, Any]:
        deadline = time.monotonic() + 4
        while True:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "expected progress, only heartbeats arrived"
            frame = self.next(remaining)
            if frame["type"] != "heartbeat":
                return frame

    def started(self, session: str, sequence: int = 2) -> dict[str, Any]:
        value = self.next()
        assert list(value) == [
            "type",
            "run_id",
            "session_id",
            "start_sequence",
            "provenance",
        ]
        assert value["type"] == "started" and value["session_id"] == session
        assert value["start_sequence"] == sequence
        assert self.child.process.poll() is None
        return value

    def finish(
        self, installed: _Installed, s: Any, code: int
    ) -> tuple[bytes, dict[str, Any]]:
        actual, out, err, audit = self.child.finish()
        assert actual == code, (actual, err)
        tail = bytes(self.buffer) + out
        if code == 0:
            assert not tail, "unexpected suffix after terminal"
        else:
            assert not tail or tail.endswith(b"\n")
            for line in tail.splitlines():
                assert json.loads(line) == {"type": "heartbeat"}
        assert audit["credential_reads"] == 1
        authority = f"[::1]:{s.port}" if s.host == "::1" else f"127.0.0.1:{s.port}"
        assert audit["requests"] == [
            {
                "method": "POST",
                "path": "/v1/observation/follow",
                "host": authority,
                "authorization_count": 1,
            }
        ]
        assert not audit["core_imported"] and not Path(audit["cwd"]).is_relative_to(
            process._REPO
        )
        assert Path(audit["follow_file"]).is_relative_to(installed.python.parent.parent)
        assert audit["http_status"] == 200 and audit["cache_control"] == "no-store"
        assert (
            audit["content_type"] == "application/x-ndjson"
            and audit["content_encoding"] is None
        )
        process._private(b"".join(self.raw), err, s.token)
        if code == 0:
            assert err == b"" and self.values[-1]["type"] == "terminal"
        elif code == 130:
            process._failure(err, "interrupted", "unknown")
            assert all(v["type"] != "terminal" for v in self.values)
        return err, audit


def active(helper: Any, s: Any) -> None:
    status, _, raw = helper._status(s.host, s.port, s.token)
    view = json.loads(raw)["runtime"]
    assert status == 200 and view["state"] == "active"
    assert s.audit()["consumers"] == s.audit()["opens"] == 1
    assert s.audit()["closes"] == s.audit()["recorder_closes"] == 0


def page(
    installed: _Installed, s: Any, path: Path, session: str, sequence: int | None = None
) -> dict[str, Any]:
    command = support._args(
        s.host, s.port, "page" if sequence is None else "record", session
    )
    if sequence is not None:
        command[-1] = str(sequence)
    code, out, err, audit = support._run(installed, path, s.home, command)
    assert code == 0 and err == b""
    assert audit["credential_reads"] == len(audit["requests"]) == 1
    return dict(json.loads(out))


def attach(
    installed: _Installed, s: Any, home: Path, root: Path, *, large: bool = False
) -> str:
    if not large:
        return str(support._attach(installed, s, home, root)[0])
    tree = ast.parse(
        (
            process._REPO / "core/tests/contract/test_observation_composition.py"
        ).read_text()
    )
    text = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_PROFILE" for t in n.targets)
    )
    for old, new in [
        ("65536", "4194304"),
        ("8192", "2097152"),
        ("128", "2048"),
        ("16384", "2097152"),
    ]:
        text = text.replace("= " + old + "\n", "= " + new + "\n")
    profile, journal = home / "follow-large.toml", home / "follow-large.sqlite3"
    profile.write_text(text)
    code, out, err, _ = support._run(
        installed,
        root,
        home,
        [
            "--host",
            s.host,
            "--port",
            str(s.port),
            "attach",
            "--profile",
            str(profile),
            "--journal",
            str(journal),
        ],
    )
    assert code == 0 and err == b"", (code, err)
    s.wait("rx_commits", 1)
    return str(json.loads(out)["runtime"]["session_id"])


@pytest.mark.parametrize("direct", [False, True])
@pytest.mark.parametrize(
    "command,code", [(["follow", "--help"], 0), (["follow", "--session", ""], 2)]
)
def test_installed_follow_help_and_lexical_errors_are_resource_free(
    installed_stack: _Installed,
    account_home: Path,
    tmp_path: Path,
    direct: bool,
    command: list[str],
    code: int,
) -> None:
    with cli(
        installed_stack,
        tmp_path / "cli",
        account_home,
        command,
        mode="no_io",
        direct=direct,
    ) as child:
        actual, out, err, audit = child.finish()
    assert actual == code and audit["credential_reads"] == 0 and audit["requests"] == []
    assert b"Traceback" not in out + err
    assert Path(audit["follow_file"]).is_relative_to(
        installed_stack.python.parent.parent
    )


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
def test_installed_incremental_exact_evidence_concurrent_workflows_heartbeat_and_ctrl_c(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
) -> None:
    with stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session = attach(installed_stack, s, account_home, tmp_path / "attach")
        with cli(
            installed_stack, tmp_path / "follow", account_home, args(s, session)
        ) as child:
            stream = Stream(child)
            stream.started(session)
            # Remain open beyond the10s handshake bound; real transport-only
            # heartbeats keep each independent complete-frame budget satisfied.
            began = time.monotonic()
            for _ in range(11):
                assert stream.next() == {"type": "heartbeat"}
            assert time.monotonic() - began >= 10
            pattern = [
                "--host",
                host,
                "--port",
                str(s.port),
                "monitor",
                "--session",
                session,
                "--condition-base64",
                "UEFTUw==",
                "--timeout-ms",
                "4000",
                "--max-rx-bytes",
                "2048",
            ]
            with cli(
                installed_stack, tmp_path / "monitor", account_home, pattern
            ) as monitor:
                marker = stream.data()
                assert (
                    marker["type"] == "record"
                    and marker["record"]["kind"] == "operation_started"
                    and marker["record"]["sequence"] == 2
                )
                code, out, err, _ = support._run(
                    installed_stack,
                    tmp_path / "annotate",
                    account_home,
                    [
                        "--host",
                        host,
                        "--port",
                        str(s.port),
                        "annotate",
                        "--session",
                        session,
                        "--text",
                        _TEXT,
                    ],
                )
                assert code == 0 and err == b""
                receipt = json.loads(out)
                annotation = stream.data()["record"]
                assert (
                    annotation == receipt["annotation"] and annotation["sequence"] == 3
                )
                assert (
                    annotation["text"] == _TEXT
                    and annotation["client_surface"] == "cli"
                )
                s.control(emit_hex=_NEW.hex())
                s.wait("rx_commits", 2)
                record = stream.data()["record"]
                assert (
                    record["sequence"] == 4
                    and base64.b64decode(record["payload_base64"], validate=True)
                    == _NEW
                )
                ended = stream.data()["record"]
                assert ended["sequence"] == 5 and ended["kind"] == "operation_ended"
                mcode, mout, merr, _ = monitor.finish()
                assert (
                    mcode == 0
                    and merr == b""
                    and json.loads(mout)["outcome"] == "matched"
                )
            ordinary = page(installed_stack, s, tmp_path / "page", session)
            offered = [v["record"] for v in stream.values if v["type"] == "record"]
            assert offered == ordinary["page"]["records"][2:]
            assert page(installed_stack, s, tmp_path / "record", session, 4)["page"][
                "records"
            ] == [record]
            assert child.process.poll() is None
            child.process.send_signal(signal.SIGINT)
            stream.finish(installed_stack, s, 130)
        s.wait("follow_jobs", 0)
        s.wait("follow_closes", 1)
        active(native_service_helper, s)
        s.control(emit_count=1)
        s.wait("rx_commits", 3)
        assert (
            base64.b64decode(
                page(installed_stack, s, tmp_path / "after-exit", session, 6)["page"][
                    "records"
                ][0]["payload_base64"],
                validate=True,
            )
            == support._AMBIENT
        )


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
def test_installed_retention_gap_preserves_prefix_marker_exact_later_bytes_and_service_stop(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
) -> None:
    with stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session = attach(installed_stack, s, account_home, tmp_path / "attach")
        s.control(pause_pull=True)
        s.wait("pause_pull", True)
        with cli(
            installed_stack, tmp_path / "follow", account_home, args(s, session)
        ) as child:
            stream = Stream(child)
            stream.started(session)
            s.wait("pending_pull", True)
            s.control(emit_count=105)
            s.wait("rx_commits", 106)
            expired = page(installed_stack, s, tmp_path / "expired", session, 2)["page"]
            assert expired["outcome"] == "expired"
            marker = expired["retention_marker"]
            assert marker["expired_range"] == {"start_inclusive": 0, "end_exclusive": 7}
            assert marker["discarded_record_count"] == 7
            s.control(pause_pull=False)
            gap = stream.data()
            assert gap == {
                "type": "gap",
                "missed_range": {"start_inclusive": 2, "end_exclusive": 7},
                "retention_marker": marker,
            }
            for sequence in range(7, 107):
                record = stream.data()
                assert (
                    record["type"] == "record"
                    and record["record"]["sequence"] == sequence
                )
                assert (
                    base64.b64decode(record["record"]["payload_base64"], validate=True)
                    == support._AMBIENT
                )
            assert page(installed_stack, s, tmp_path / "last", session, 106)["page"][
                "records"
            ] == [record["record"]]
            s.process.send_signal(signal.SIGTERM)
            end = stream.data()
            assert end == {
                "type": "terminal",
                "reason": "service_stopping",
                "next_sequence": 107,
                "source_end_exclusive": None,
            }
            stream.finish(installed_stack, s, 0)
        audit = s.finish(None)
        assert audit["http_drained"] and audit["follow_jobs"] == 0
        assert audit["recorder_closes"] == audit["closes"] == audit["consumers"] == 1


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("capacity", ["service", "reads"])
def test_installed_independent_follow_job_and_eight_real_read_leases_have_explicit_capacity(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    capacity: str,
) -> None:
    with stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session = attach(installed_stack, s, account_home, tmp_path / "attach")
        with cli(
            installed_stack, tmp_path / "first", account_home, args(s, session)
        ) as child:
            stream = Stream(child)
            stream.started(session)
            if capacity == "service":
                code, out, err, audit = support._run(
                    installed_stack, tmp_path / "second", account_home, args(s, session)
                )
                assert (
                    code == 4
                    and out == b""
                    and json.loads(err)
                    == {"error": {"source": "service", "code": "follow_capacity"}}
                )
                assert audit["credential_reads"] == len(audit["requests"]) == 1
                assert child.process.poll() is None
                child.process.send_signal(signal.SIGINT)
                stream.finish(installed_stack, s, 130)
            else:
                s.control(hold_reads=True)
                s.wait("held_reads", 8)
                s.control(emit_count=1)
                s.wait("rx_commits", 2)
                assert stream.data() == {
                    "type": "terminal",
                    "reason": "read_capacity",
                    "next_sequence": 2,
                    "source_end_exclusive": None,
                }
                stream.finish(installed_stack, s, 0)
                assert s.audit()["held_reads"] == 8
                s.control(release_reads=True)
                s.wait("held_reads", 0)
            s.wait("follow_jobs", 0)
        active(native_service_helper, s)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize("fault", ["preheader", "source", "oversize"])
def test_installed_preheader_error_source_failure_and_policy_legal_oversize_are_honest(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    fault: str,
) -> None:
    with stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session = attach(
            installed_stack,
            s,
            account_home,
            tmp_path / "attach",
            large=fault == "oversize",
        )
        if fault == "preheader":
            s.fault("follow-query")
            code, out, err, audit = support._run(
                installed_stack, tmp_path / "follow", account_home, args(s, session)
            )
            assert (
                code == 4
                and out == b""
                and json.loads(err)
                == {"error": {"source": "journal", "code": "io_failure"}}
            )
            assert audit["http_status"] == 500 and audit["cache_control"] == "no-store"
            assert audit["credential_reads"] == len(audit["requests"]) == 1
            s.fault("normal")
        else:
            with cli(
                installed_stack, tmp_path / "follow", account_home, args(s, session)
            ) as child:
                stream = Stream(child)
                stream.started(session)
                if fault == "source":
                    s.fault("follow-query")
                s.control(emit_count=1, oversize=fault == "oversize")
                s.wait("rx_commits", 2)
                end = stream.data()
                assert end == {
                    "type": "terminal",
                    "reason": "source_failed"
                    if fault == "source"
                    else "delivery_too_large",
                    "next_sequence": 2,
                    "source_end_exclusive": None,
                }
                stream.finish(installed_stack, s, 0)
                if fault == "oversize":
                    assert s.audit()["last_rx_bytes"] == 1048576
                s.fault("normal")
        s.wait("follow_jobs", 0)
        active(native_service_helper, s)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("backend", [0, 1], ids=["basic", "enhanced-shaped"])
@pytest.mark.parametrize(
    "ending", ["closed_pipe", "disconnect", "detach", "abnormal_eof"]
)
def test_installed_pipe_source_disconnect_detach_and_abnormal_eof_do_not_retry_or_invent_completion(
    installed_stack: _Installed,
    native_service_helper: Any,
    account_home: Path,
    tmp_path: Path,
    host: str,
    backend: int,
    ending: str,
) -> None:
    with stack(
        installed_stack,
        native_service_helper,
        account_home,
        tmp_path / "service",
        host,
        backend,
    ) as s:
        session = attach(installed_stack, s, account_home, tmp_path / "attach")
        with cli(
            installed_stack, tmp_path / "follow", account_home, args(s, session)
        ) as child:
            stream = Stream(child)
            stream.started(session)
            if ending == "closed_pipe":
                assert child.process.stdout is not None
                child.process.stdout.close()
                child.process.stdout = None
                s.control(emit_hex=_NEW.hex())
                s.wait("rx_commits", 2)
                err, _ = stream.finish(installed_stack, s, 1)
                process._failure(err, "output_failed", "unknown")
            elif ending == "abnormal_eof":
                s.control(abort_peer=True)
                err, _ = stream.finish(installed_stack, s, 5)
                process._failure(err, "invalid_response", "unknown")
                assert all(v["type"] != "terminal" for v in stream.values)
            else:
                if ending == "disconnect":
                    s.control(disconnect=True)
                else:
                    code, _, err, _ = support._run(
                        installed_stack,
                        tmp_path / "detach",
                        account_home,
                        ["--host", host, "--port", str(s.port), "detach"],
                    )
                    assert code == 0 and err == b""
                end = stream.data()
                while end["type"] == "record":
                    assert (
                        end["record"]["kind"] == "segment_ended"
                        and end["record"]["sequence"] == 2
                    )
                    end = stream.data()
                assert end["type"] == "terminal" and end["reason"] == (
                    "source_ended" if ending == "disconnect" else "detached"
                )
                assert end["next_sequence"] in (2, 3)
                assert (
                    end["source_end_exclusive"] is None
                    or end["source_end_exclusive"] >= end["next_sequence"]
                )
                stream.finish(installed_stack, s, 0)
            s.wait("follow_jobs", 0)
        if ending in ("closed_pipe", "abnormal_eof"):
            active(native_service_helper, s)
        else:
            s.wait("recorder_closes", 1)
            assert s.audit()["closes"] == s.audit()["consumers"] == 1
