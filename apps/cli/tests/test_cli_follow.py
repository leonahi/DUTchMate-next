"""011 T012 RED: real thin CLI over controlled external HTTPX byte streams.

Mutations caught: buffered/finite Follow delivery, permissive frames/sequence,
reset-on-byte deadlines, credential rereads/retries, and implicit capture cleanup.
Only external transport/time/output progress is controlled. No command, frame
validator, framing algorithm, Core policy or service implementation lives here.
"""

import asyncio
import base64
import importlib
import json
import socket
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Self, SupportsIndex

import httpx
import pytest
import typer

_commands = importlib.import_module("test_cli_commands")
_evidence = importlib.import_module("test_cli_evidence")
_monitor = importlib.import_module("test_cli_monitor")
_annotations = importlib.import_module("test_cli_annotations")
_api = _evidence._api
_json = _evidence._json
_TOKEN = _evidence._TOKEN
_PRIVATE = _evidence._PRIVATE
_SESSION = "session-é"
_LIMIT = 1048576
_MAX = 9223372036854775807
_ARGS = ["--port", "8765", "follow", "--session", _SESSION]
_REASONS = (
    "detached",
    "service_stopping",
    "source_ended",
    "source_failed",
    "read_capacity",
    "delivery_too_large",
)


def started(*, device: bool = False, sequence: int = 3) -> dict[str, Any]:
    return {
        "type": "started",
        "run_id": "run-é",
        "session_id": _SESSION,
        "start_sequence": sequence,
        "provenance": _evidence._full_report(device)["page"]["records"][0][
            "provenance"
        ],
    }


def terminal(
    reason: str = "source_ended",
    *,
    next_sequence: int = 3,
    cutoff: int | None = 3,
) -> dict[str, Any]:
    return {
        "type": "terminal",
        "reason": reason,
        "next_sequence": next_sequence,
        "source_end_exclusive": cutoff,
    }


def frame(value: object) -> bytes:
    # Contract008§6: unchanged stdlib compact UTF-8 escaping, then one LF.
    return bytes(_json(value)) + b"\n"


def wire(*values: object) -> bytes:
    return b"".join(frame(value) for value in values)


def records(device: bool = False) -> list[dict[str, Any]]:
    """Seven existing golden variants; no production projector supplies facts."""
    old = _evidence._full_report(device)["page"]["records"]
    start, end = _monitor._markers("timeout", device=device)
    end["start_sequence"] = 6
    end["window"] = {"start_inclusive": 7, "end_exclusive": 7}
    annotation = _annotations._receipt()["annotation"]
    values = [old[0], old[2], old[4], start, end, annotation, old[6]]
    for sequence, value in enumerate(values, 3):
        value["sequence"] = sequence
    return values


def gap() -> dict[str, Any]:
    # Subscriber misses only3..5; counts/endpoints describe unchanged whole0..5.
    marker = _evidence._with_marker()["page"]["retention_marker"]
    marker["expired_range"]["end_exclusive"] = 5
    marker["discarded_record_count"] = 5
    marker["discarded_rx_payload_byte_count"] = 33
    marker["discarded_charged_bytes"] = 1000
    return {
        "type": "gap",
        "missed_range": {"start_inclusive": 3, "end_exclusive": 5},
        "retention_marker": marker,
    }


class Stream(httpx.AsyncByteStream):
    """External peer chunks/progress only, never the product's frame parser."""

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.before: Callable[[int], Awaitable[None]] | None = None
        self.finish: Callable[[], Awaitable[None]] | None = None
        self.failure: BaseException | None = None
        self.yielded = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index, chunk in enumerate(self.chunks):
            if self.before is not None:
                await self.before(index)
            self.yielded += 1
            yield chunk
            await asyncio.sleep(0)
        if self.finish is not None:
            await self.finish()
        if self.failure is not None:
            raise self.failure

    async def aclose(self) -> None:
        self.closed = True


class Delivery:
    def __init__(
        self,
        home: Path,
        patch: pytest.MonkeyPatch,
        *,
        chunks: list[bytes] | None = None,
        headers: list[tuple[str, str]] | None = None,
        **options: Any,
    ) -> None:
        # Reuse actual isolated credential reads, real HTTPX, import/account/
        # socket guards and forbidden whole-response APIs from the old suite.
        base = _evidence.Delivery(
            home,
            patch,
            body=b"",
            headers=[("Content-Type", "application/x-ndjson")]
            if headers is None
            else headers,
            **options,
        )
        self.api, self.wire, self.reads, self.imports = (
            base.api,
            base.wire,
            base.reads,
            base.imports,
        )
        self.stream = Stream(
            [wire(started(), terminal())] if chunks is None else chunks
        )
        self.wire.stream = self.stream

    def invoke(self, args: list[str] | None = None) -> int:
        return int(_commands._console(self.api, _ARGS if args is None else args))

    def one_request(
        self, *, host: str = "127.0.0.1", port: int = 8765, session: str = _SESSION
    ) -> None:
        assert self.reads == ["credential"] and self.imports == []
        assert len(self.wire.requests) == 1, (
            "Follow must not poll, retry, detach or request status"
        )
        request = self.wire.requests[0]
        assert request.method == "POST" and request.url.scheme == "http"
        assert request.url.host == host
        assert (request.url.port if request.url.port is not None else 80) == port
        assert request.url.raw_path == b"/v1/observation/follow"
        assert request.url.query == b"" and request.url.fragment == ""
        assert json.loads(request.content) == {"session_id": session}
        authority = f"[::1]:{port}" if host == "::1" else f"127.0.0.1:{port}"
        for name, value in (
            ("host", authority),
            ("authorization", "Bearer " + _TOKEN),
            ("accept", "application/x-ndjson"),
            ("accept-encoding", "identity"),
            ("content-type", "application/json"),
        ):
            assert request.headers.get_list(name) == [value]
        assert not any(
            name in request.headers for name in ("origin", "cookie", "upgrade")
        )
        assert not any(name.startswith("sec-fetch-") for name in request.headers)
        assert _TOKEN not in str(request.url) and _TOKEN.encode() not in request.content
        assert len(self.wire.client_options) == len(self.wire.transport_options) == 1
        for options in (*self.wire.client_options, *self.wire.transport_options):
            assert options["trust_env"] is False and options["proxy"] is None
            assert options["http1"] is True and options["http2"] is False
            assert options["limits"].max_connections == 1
            assert options["limits"].max_keepalive_connections == 0
        options = self.wire.client_options[0]
        assert options["follow_redirects"] is False and options["mounts"] is None
        timeout = options["timeout"]
        assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (
            5.0,
        ) * 4
        assert self.wire.transport_options[0]["retries"] == 0
        assert self.stream.closed and all(item.closed for item in self.wire.transports)


def local(
    captured: tuple[str, str],
    code: str,
    *,
    prefix: bytes = b"",
    phase: str = "unknown",
) -> None:
    stdout, stderr = captured
    assert stdout.encode() == prefix
    assert stderr.encode() == frame(
        {
            "error": {"source": "cli", "code": code},
            "request_outcome": phase,
        }
    )
    assert _PRIVATE not in stderr and _TOKEN not in stderr and "\x1b" not in stderr


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--help"],
        ["follow", "--help"],
        ["--host", _PRIVATE, "--port", "0", "follow", "--help"],
    ],
)
@pytest.mark.parametrize("unsupported", [False, True])
def test_resource_free_help_explains_follow_terminal_delivery(
    args: list[str],
    unsupported: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _commands._block_preparation(api, monkeypatch)
    if unsupported:
        monkeypatch.setattr(sys, "platform", "win32")
    assert _commands._console(api, args) == 0
    stdout, stderr = capsys.readouterr()
    assert stdout and not stderr and "follow" in stdout.lower()
    if "follow" in args:
        assert "--session" in stdout and "terminal" in stdout.lower()
        for forbidden in (
            "--cursor",
            "--text",
            "--timeout",
            "--retry",
            "--reconnect",
            "--detach",
            "--token",
            "--profile",
            "--journal",
        ):
            assert forbidden not in stdout
    assert attempts == [] and _PRIVATE not in stdout


_BAD_ARGS = [
    _ARGS[2:],
    ["--port", "8765", "follow"],
    [*_ARGS, "--session"],
    [*_ARGS, _PRIVATE],
    ["--port", "8765", "Follow", *_ARGS[3:]],
]
for _option in (
    "--cursor",
    "--start",
    "--end",
    "--run-id",
    "--output",
    "--text",
    "--decode",
    "--path",
    "--file",
    "--token",
    "--timeout",
    "--timeout-ms",
    "--retry",
    "--reconnect",
    "--detach",
    "--profile",
    "--journal",
    "--filter",
):
    _BAD_ARGS.append([*_ARGS, _option, _PRIVATE])
for _session in ("", "x\0y", "x" * 257, "é" * 129, "\ud800"):
    _BAD_ARGS.append([*_ARGS[:-1], _session])
for _host in ("localhost", "192.0.2.1", "::ffff:127.0.0.1", _PRIVATE):
    _BAD_ARGS.append(["--host", _host, *_ARGS])
for _port in ("0", "65536", "-1", "1.0", "true", _PRIVATE):
    _BAD_ARGS.append(["--port", _port, *_ARGS[2:]])


@pytest.mark.parametrize("args", _BAD_ARGS)
def test_invalid_local_input_is_private_and_precedes_credentials(
    args: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    api = _api()
    attempts = _commands._block_preparation(api, monkeypatch)
    assert _commands._console(api, args) == 2
    local(capsys.readouterr(), "invalid_arguments", phase="not_submitted")
    assert attempts == []


@pytest.mark.parametrize(
    "option,value", [("--session", " /e\u0301 "), ("--host", "::1"), ("--port", "80")]
)
def test_existing_last_valued_option_rule_is_preserved(
    option: str,
    value: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = value if option == "--session" else _SESSION
    start = started()
    start["session_id"] = session
    d = Delivery(account_home, monkeypatch, chunks=[wire(start, terminal())])
    args = (
        [*_ARGS, option, value]
        if option == "--session"
        else [*_ARGS[:2], option, value, *_ARGS[2:]]
    )
    assert d.invoke(args) == 0
    assert tuple(capsys.readouterr()) == (wire(start, terminal()).decode(), "")
    d.one_request(
        host=value if option == "--host" else "127.0.0.1",
        port=80 if option == "--port" else 8765,
        session=session,
    )


@pytest.mark.parametrize("session", [" ", "x" * 256, "é" * 128, " /e\u0301 "])
def test_session_edges_are_exact_without_normalization(
    session: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    start = started()
    start["session_id"] = session
    d = Delivery(account_home, monkeypatch, chunks=[wire(start, terminal())])
    assert d.invoke([*_ARGS[:-1], session]) == 0
    assert tuple(capsys.readouterr()) == (wire(start, terminal()).decode(), "")
    d.one_request(session=session)


@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.parametrize("host,port", [("127.0.0.1", 1), ("::1", 65535)])
def test_one_credential_one_authenticated_request_and_exact_seven_records(
    device: bool,
    host: str,
    port: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = [
        started(device=device),
        *({"type": "record", "record": r} for r in records(device)),
        {"type": "heartbeat"},
        terminal(next_sequence=10, cutoff=10),
    ]
    raw = wire(*values)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.setenv(name, "http://" + _PRIVATE)
    d = Delivery(account_home, monkeypatch, chunks=[raw])
    assert d.invoke(["--host", host, "--port", str(port), *_ARGS[2:]]) == 0
    assert tuple(capsys.readouterr()) == (raw.decode(), "")
    decoded = json.loads(raw.splitlines()[2])["record"]["payload_base64"]
    assert base64.b64decode(decoded) == bytes(range(256))
    d.one_request(host=host, port=port)


@pytest.mark.parametrize("reason", _REASONS)
@pytest.mark.parametrize("cutoff", [None, 3, _MAX])
def test_valid_terminal_exits_zero_for_failure_unknown_and_unoffered_tail(
    reason: str,
    cutoff: int | None,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = wire(started(), terminal(reason, cutoff=cutoff))
    d = Delivery(account_home, monkeypatch, chunks=[raw])
    assert d.invoke() == 0
    assert tuple(capsys.readouterr()) == (raw.decode(), "")
    d.one_request()


@pytest.mark.parametrize("start", [0, _MAX])
def test_empty_zero_and_max_boundaries_do_not_advance_or_invent_records(
    start: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = wire(
        started(sequence=start),
        {"type": "heartbeat"},
        terminal(next_sequence=start, cutoff=start),
    )
    d = Delivery(account_home, monkeypatch, chunks=[raw])
    assert d.invoke() == 0
    assert tuple(capsys.readouterr()) == (raw.decode(), "")
    d.one_request()


def test_gap_preserves_whole_prefix_counts_and_distinct_timestamp_origins(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record = _evidence._rx(bytes(range(256)), sequence=5)
    raw = wire(
        started(),
        gap(),
        {"type": "record", "record": record},
        terminal("detached", next_sequence=6, cutoff=10),
    )
    d = Delivery(account_home, monkeypatch, chunks=[raw])
    assert d.invoke() == 0
    assert tuple(capsys.readouterr()) == (raw.decode(), "")
    d.one_request()


@pytest.mark.parametrize("chunk_size", [1, 2, 3, 7, 31, 1024, _LIMIT * 2])
def test_arbitrary_utf8_escape_and_lf_splits_and_multiple_frames_per_chunk(
    chunk_size: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = wire(
        started(device=True),
        *({"type": "record", "record": r} for r in records(True)),
        terminal(next_sequence=10, cutoff=10),
    )
    d = Delivery(
        account_home,
        monkeypatch,
        chunks=[raw[i : i + chunk_size] for i in range(0, len(raw), chunk_size)],
    )
    assert d.invoke() == 0
    assert tuple(capsys.readouterr()) == (raw.decode(), "")
    d.one_request()


@pytest.mark.parametrize(
    "media",
    [
        "application/x-ndjson",
        ' Application/X-NDJSON ; charset="UTF-8" ',
        "application/x-ndjson;charset=utf-8",
    ],
)
@pytest.mark.parametrize("encoding", [None, "identity", " Identity "])
def test_only_ndjson_media_and_identity_encoding_conventions_succeed(
    media: str,
    encoding: str | None,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    headers = [("Content-Type", media)]
    if encoding is not None:
        headers.append(("Content-Encoding", encoding))
    d = Delivery(account_home, monkeypatch, headers=headers)
    assert d.invoke() == 0
    assert tuple(capsys.readouterr()) == (wire(started(), terminal()).decode(), "")
    d.one_request()


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [("Content-Type", "application/json")],
        [("Content-Type", "text/event-stream")],
        [("Content-Type", "application/x-ndjson; charset=latin-1")],
        [("Content-Type", "application/x-ndjson; arbitrary=x")],
        [
            ("Content-Type", "application/x-ndjson"),
            ("Content-Type", "application/x-ndjson"),
        ],
        [("Content-Type", "application/x-ndjson"), ("Content-Encoding", "gzip")],
        [
            ("Content-Type", "application/x-ndjson"),
            ("Content-Encoding", "identity,identity"),
        ],
        [
            ("Content-Type", "application/x-ndjson"),
            ("Content-Encoding", "identity"),
            ("Content-Encoding", "identity"),
        ],
    ],
)
def test_bad_stream_media_or_encoding_is_private_without_output(
    headers: list[tuple[str, str]],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = Delivery(account_home, monkeypatch, headers=headers)
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response")
    d.one_request()


@pytest.mark.parametrize("size", [_LIMIT - 1, _LIMIT, _LIMIT + 1])
def test_raw_frame_cap_counts_utf8_json_bytes_and_excludes_the_lf(
    size: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = started()
    fields = value["provenance"]["connection_provenance"]["fields"]
    fields.append({"name": "padding", "value": "é"})
    fields[-1]["value"] += "x" * (size - len(_json(value)))
    raw = wire(value, terminal())
    assert len(frame(value)) == size + 1
    d = Delivery(account_home, monkeypatch, chunks=[raw[:size], raw[size:]])
    if size > _LIMIT:
        assert d.invoke() == 5
        local(capsys.readouterr(), "invalid_response")
    else:
        assert d.invoke() == 0
        assert tuple(capsys.readouterr()) == (raw.decode(), "")
    d.one_request()


_BAD_FIRST: list[bytes] = [
    b"",
    b"\n",
    b"null\n",
    b"[]\n",
    b"true\n",
    b"1\n",
    b"{}\n",
    b'{"type":"heartbeat"}\n',
    frame(terminal()),
    b'{"type":"started","type":"started"}\n',
    b'{"type":"started","run_id":NaN}\n',
    b'{"type":"started","run_id":Infinity}\n',
    b'{"type":"started","run_id":1e999}\n',
    b"\xff\n",
    frame(started()).rstrip(b"\n"),
]


def test_valid_noncanonical_key_order_and_unicode_escapes_emit_canonical_frames(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = [
        started(device=True),
        {"type": "record", "record": records(True)[1] | {"sequence": 3}},
        terminal(next_sequence=4, cutoff=4),
    ]
    raw = b"".join(
        json.dumps(
            _annotations._reverse(value), ensure_ascii=True, separators=(",", ":")
        ).encode()
        + b"\n"
        for value in values
    )
    assert raw != wire(*values)
    d = Delivery(account_home, monkeypatch, chunks=[raw])
    assert d.invoke() == 0
    assert tuple(capsys.readouterr()) == (wire(*values).decode(), "")
    d.one_request()


@pytest.mark.parametrize("body", _BAD_FIRST)
def test_invalid_first_json_frame_or_incomplete_started_is_never_printed(
    body: bytes,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = Delivery(account_home, monkeypatch, chunks=[body])
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response")
    d.one_request()


@pytest.mark.parametrize(
    "suffix",
    [
        b"",
        b"\n",
        b"{",
        b'{"type":"heartbeat"}',
        b"\xff\n",
        b'{"type":"heartbeat","extra":0}\n',
        b'{"type":"heartbeat","type":"heartbeat"}\n',
        frame(started()),
    ],
)
def test_later_malformed_frame_or_eof_preserves_only_the_valid_prefix(
    suffix: bytes,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prefix = frame(started())
    d = Delivery(account_home, monkeypatch, chunks=[prefix, suffix])
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response", prefix=prefix)
    d.one_request()


def set_path(value: Any, path: tuple[str | int, ...], replacement: object) -> None:
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = replacement


_BAD_START = [
    (("extra",), _PRIVATE),
    (("type",), "sse"),
    (("run_id",), ""),
    (("session_id",), "other-session"),
    (("session_id",), True),
    (("start_sequence",), True),
    (("start_sequence",), -1),
    (("start_sequence",), _MAX + 1),
    (("provenance", "capabilities"), ["arbitrary"]),
    (("provenance", "connection_id"), None),
    (("provenance", "backend_observation_timestamp_domain", "observer"), "wall"),
    (("provenance", "connection_provenance", "envelope_version"), True),
]


@pytest.mark.parametrize("path,value", _BAD_START)
def test_closed_started_identity_counters_and_provenance_precede_output(
    path: tuple[str | int, ...],
    value: object,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    start = started()
    set_path(start, path, value)
    # Use ASCII escapes here so malformed surrogate cases can reach the decoder.
    raw = json.dumps(start, separators=(",", ":")).encode() + b"\n"
    d = Delivery(account_home, monkeypatch, chunks=[raw, frame(terminal())])
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response")
    d.one_request()


_BAD_RECORD = [
    (0, ("extra",), 0),
    (0, ("provenance", "segment_id"), ""),
    (1, ("payload_base64",), "AB=="),
    (1, ("payload_base64",), "_w=="),
    (1, ("payload_base64",), "/w"),
    (1, ("observed_at", "value"), True),
    (1, ("sequence",), 2),
    (1, ("sequence",), 4),
    (1, ("sequence",), True),
    (2, ("lost_bytes",), -1),
    (2, ("cause",), _PRIVATE),
    (3, ("condition_base64",), "AB=="),
    (3, ("operation_id",), "invalid-uuid"),
    (4, ("clock", "origin_id"), "invalid-uuid"),
    (4, ("outcome",), "success"),
    (5, ("assertion_class",), "verified"),
    (5, ("attribution_basis",), "authenticated"),
    (5, ("client_surface",), "ai"),
    (5, ("received_at_ns",), True),
    (5, ("text",), "x" * 1025),
    (6, ("reason",), "detached"),
]


@pytest.mark.parametrize("index,path,value", _BAD_RECORD)
def test_each_existing_record_variant_remains_closed_binary_safe_and_ordered(
    index: int,
    path: tuple[str | int, ...],
    value: object,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record = records()[index]
    record["sequence"] = 3
    set_path(record, path, value)
    d = Delivery(
        account_home,
        monkeypatch,
        chunks=[
            frame(started()),
            wire(
                {"type": "record", "record": record},
                terminal(next_sequence=4, cutoff=4),
            ),
        ],
    )
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response", prefix=frame(started()))
    d.one_request()


_BAD_GAP = [
    (("extra",), 0),
    (("missed_range",), None),
    (("missed_range", "start_inclusive"), 2),
    (("missed_range", "start_inclusive"), 4),
    (("missed_range", "start_inclusive"), True),
    (("missed_range", "end_exclusive"), 3),
    (("missed_range", "end_exclusive"), 6),
    (("retention_marker",), None),
    (("retention_marker", "expired_range", "start_inclusive"), 4),
    (("retention_marker", "discarded_record_count"), True),
    (
        ("retention_marker", "first_discarded_timestamp", "domain", "observer"),
        "unknown",
    ),
]


@pytest.mark.parametrize("path,value", _BAD_GAP)
def test_gap_must_cover_exact_next_interval_inside_unchanged_valid_marker(
    path: tuple[str | int, ...],
    value: object,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value_gap = gap()
    set_path(value_gap, path, value)
    d = Delivery(account_home, monkeypatch, chunks=[frame(started()), frame(value_gap)])
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response", prefix=frame(started()))
    d.one_request()


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": "success"},
        {"extra": _PRIVATE},
        {"next_sequence": 4},
        {"next_sequence": True},
        {"source_end_exclusive": 2},
        {"source_end_exclusive": False},
        {"source_end_exclusive": _MAX + 1},
    ],
)
def test_terminal_must_be_closed_and_equal_the_validated_received_position(
    changes: dict[str, Any],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    end = terminal()
    end.update(changes)
    d = Delivery(account_home, monkeypatch, chunks=[frame(started()), frame(end)])
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response", prefix=frame(started()))
    d.one_request()


@pytest.mark.parametrize(
    "trailing", [b"x", b"\n", frame(terminal()), frame({"type": "heartbeat"})]
)
def test_terminal_requires_clean_eof_and_trailing_bytes_cannot_exit_zero(
    trailing: bytes,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prefix = wire(started(), terminal())
    d = Delivery(account_home, monkeypatch, chunks=[prefix, trailing])
    assert d.invoke() == 5
    stdout, stderr = capsys.readouterr()
    assert stdout.encode() == prefix
    diagnostic = json.loads(stderr)
    assert set(diagnostic) == {"error", "request_outcome"}
    assert diagnostic["error"] == {"source": "cli", "code": "invalid_response"}
    # Terminal is validated before EOF. Existing007 receipt categories are kept;
    # this contract does not define a new phase at that intervening byte boundary.
    assert diagnostic["request_outcome"] in {"unknown", "report_received"}
    assert _PRIVATE not in stderr and _TOKEN not in stderr
    d.one_request()


_ERRORS = [
    (404, "follow", "no_associated_session"),
    (409, "follow", "session_not_associated"),
    (409, "follow", "not_active"),
    (503, "follow", "follow_unavailable"),
    (409, "follow", "busy"),
    (503, "follow", "read_capacity"),
    (413, "follow", "delivery_too_large"),
    (503, "service", "follow_capacity"),
    (503, "service", "stopping"),
    (500, "service", "internal_failure"),
    (500, "runtime", "wrong_execution_context"),
    (422, "runtime", "invalid_request"),
    (422, "journal", "invalid_input"),
    (409, "journal", "session_mismatch"),
    (404, "journal", "journal_missing"),
    (503, "journal", "busy"),
    (409, "journal", "closed"),
    *((500, "journal", code) for code in _monitor._JOURNAL_CODES[5:]),
    *(
        row
        for row in importlib.import_module("test_cli_transport")._REMOTE_ERRORS
        if row[1] == "request"
    ),
]


@pytest.mark.parametrize("status,source,code", _ERRORS)
def test_recognized_preheader_rejections_use_finite_json_and_exit_four(
    status: int,
    source: str,
    code: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = {"error": {"source": source, "code": code}}
    d = Delivery(
        account_home,
        monkeypatch,
        status=status,
        chunks=[_json(value)],
        headers=[("Content-Type", "application/json; charset=utf-8")],
    )
    assert d.invoke() == 4
    assert tuple(capsys.readouterr()) == ("", frame(value).decode())
    d.one_request()


@pytest.mark.parametrize(
    "status,value",
    [
        (500, {"error": {"source": "follow", "code": "busy"}}),
        (409, {"error": {"source": "follow", "code": _PRIVATE}}),
        (409, {"error": {"source": _PRIVATE, "code": "busy"}}),
        (409, {"error": {"source": "follow", "code": "busy", "detail": _PRIVATE}}),
        (409, {"error": {"source": "follow", "code": "busy"}, "extra": _PRIVATE}),
        (302, {"error": {"source": "follow", "code": "busy"}}),
    ],
)
def test_wrong_status_unknown_or_extended_rejection_is_private_invalid_response(
    status: int,
    value: object,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = Delivery(
        account_home,
        monkeypatch,
        status=status,
        chunks=[_json(value)],
        headers=[
            ("Content-Type", "application/json"),
            ("Location", "http://" + _PRIVATE),
        ],
    )
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response")
    d.one_request()


@pytest.mark.parametrize("overflow", [False, True])
def test_admission_errors_keep_the_existing_one_mib_finite_body_cap(
    overflow: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = {"error": {"source": "follow", "code": "busy"}}
    raw = _json(value)
    raw += b" " * (_LIMIT - len(raw) + int(overflow))
    d = Delivery(
        account_home,
        monkeypatch,
        status=409,
        chunks=[raw],
        headers=[("Content-Type", "application/json")],
    )
    if overflow:
        assert d.invoke() == 5
        local(capsys.readouterr(), "invalid_response")
    else:
        assert d.invoke() == 4
        assert tuple(capsys.readouterr()) == ("", frame(value).decode())
    d.one_request()


class Output:
    """Test-owned cooperative stdout sink; count/flush without a transcript."""

    def __init__(self) -> None:
        self.writes = 0
        self.flushes = 0
        self.total = 0
        self.last = b""
        self.failure: BaseException | None = None
        self.on_flush: Callable[[], None] | None = None
        self.closed = False

    @property
    def buffer(self) -> Output:
        return self

    def write(self, value: bytes) -> int:
        self.writes += 1
        if self.failure is not None:
            raise self.failure
        self.last = bytes(value)
        self.total += len(value)
        return len(value)

    def flush(self) -> None:
        self.flushes += 1
        if self.on_flush is not None:
            self.on_flush()

    def close(self) -> None:
        self.closed = True


def test_each_complete_frame_is_flushed_before_requesting_another_chunk(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = [started(), *({"type": "heartbeat"} for _ in range(256)), terminal()]
    chunks = [frame(v) for v in values]
    d = Delivery(account_home, monkeypatch, chunks=chunks)
    output = Output()

    async def before(index: int) -> None:
        assert output.writes == output.flushes == index, (
            "Follow buffered/prefetched the live transcript"
        )
        if index:
            assert output.last == chunks[index - 1]

    d.stream.before = before
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", output)
        assert d.invoke() == 0
    assert output.writes == output.flushes == 258
    assert output.total == sum(map(len, chunks))
    assert tuple(capsys.readouterr()) == ("", "")
    d.one_request()


@pytest.mark.parametrize("overflow", [False, True])
def test_accumulator_is_bounded_for_huge_chunks_or_many_fitting_frames(
    overflow: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = Delivery(account_home, monkeypatch)
    try:
        follow = importlib.import_module("dutchmate_cli.follow")
    except ModuleNotFoundError as error:
        if error.name == "dutchmate_cli.follow":
            pytest.fail("T013 missing: thin Follow frame implementation", pytrace=False)
        raise
    retained: list[int] = []

    class WatchedBuffer(bytearray):
        def checked(self) -> None:
            retained.append(len(self))
            assert len(self) <= _LIMIT + 1, (
                "Follow retained beyond frame overflow-detection bound"
            )

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.checked()

        def extend(self, value: Any) -> None:
            super().extend(value)
            self.checked()

        def append(self, value: SupportsIndex) -> None:
            super().append(value)
            self.checked()

        def __iadd__(self, value: Any, /) -> Self:
            super().__iadd__(value)
            self.checked()
            return self

        def __add__(self, value: Any, /) -> Self:
            return type(self)(super().__add__(value))

    # Private accumulator instrumentation follows the established007 test. It
    # grants no product seam; keep the spy at that boundary if its container moves.
    monkeypatch.setattr(follow, "bytearray", WatchedBuffer, raising=False)
    monkeypatch.setattr(
        importlib.import_module("dutchmate_cli.client"),
        "bytearray",
        WatchedBuffer,
        raising=False,
    )
    output = Output()
    count = 70000
    if overflow:
        d.stream.chunks = [frame(started()), b" " * (_LIMIT * 2), frame(terminal())]
    else:
        body = (
            frame(started()) + frame({"type": "heartbeat"}) * count + frame(terminal())
        )
        assert len(body) > _LIMIT
        d.stream.chunks = [body]
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", output)
        status = d.invoke()
    if overflow:
        assert status == 5
        local(capsys.readouterr(), "invalid_response")
        assert output.writes == output.flushes == 1 and output.last == frame(started())
        assert d.stream.yielded == 2
    else:
        assert status == 0
        assert output.writes == output.flushes == count + 2
        assert output.last == frame(terminal()) and output.total == len(body)
        assert tuple(capsys.readouterr()) == ("", "")
    assert retained and max(retained) <= _LIMIT + 1
    d.one_request()


class Clock:
    """Advance only the test loop's monotonic source; asyncio deadlines are real.

    No fake timeout context, artificial TimeoutError or mirrored client budget.
    Ready-queue turns let the normal scheduled deadline cancel the real reader.
    """

    def __init__(self, patch: pytest.MonkeyPatch) -> None:
        self.now = 0.0
        original = asyncio.events.new_event_loop

        def create() -> asyncio.AbstractEventLoop:
            loop = original()
            self.now = loop.time()
            patch.setattr(loop, "time", lambda: self.now)
            return loop

        patch.setattr(asyncio.events, "new_event_loop", create)

    def elapse(self, seconds: float) -> None:
        self.now += seconds

    async def step(self, seconds: float) -> None:
        self.elapse(seconds)
        await asyncio.sleep(0)
        await asyncio.sleep(0)


@pytest.mark.parametrize("boundary", ["headers", "started", "split_started"])
def test_absolute_ten_second_handshake_includes_headers_and_first_complete_frame(
    boundary: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = Clock(monkeypatch)
    first = frame(started())
    chunks = [first, frame(terminal())]
    if boundary == "split_started":
        chunks = [first[:10], first[10:20], first[20:], frame(terminal())]
    d = Delivery(account_home, monkeypatch, chunks=chunks)
    if boundary == "headers":
        d.wire.on_request = lambda request: clock.elapse(8)

    async def before(index: int) -> None:
        delays = (
            [4, 4, 2.1]
            if boundary == "split_started"
            else [2.1 if boundary == "headers" else 10.1]
        )
        await clock.step(delays[index] if index < len(delays) else 0)

    d.stream.before = before
    assert d.invoke() == 5
    local(capsys.readouterr(), "request_timeout")
    d.one_request()


def test_trickle_bytes_do_not_reset_five_second_complete_frame_deadline(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = Clock(monkeypatch)
    heartbeat = frame({"type": "heartbeat"})
    d = Delivery(
        account_home,
        monkeypatch,
        chunks=[frame(started()), heartbeat[:8], heartbeat[8:], frame(terminal())],
    )

    async def before(index: int) -> None:
        await clock.step([0, 3, 2.1, 0][index])

    d.stream.before = before
    assert d.invoke() == 5
    local(capsys.readouterr(), "request_timeout", prefix=frame(started()))
    assert d.stream.yielded == 2
    d.one_request()


def test_fresh_frame_budgets_allow_session_far_beyond_ten_seconds(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = Clock(monkeypatch)
    values = [started(), *({"type": "heartbeat"} for _ in range(10)), terminal()]
    d = Delivery(account_home, monkeypatch, chunks=[frame(value) for value in values])

    async def before(index: int) -> None:
        await clock.step(4.9)

    d.stream.before = before
    assert d.invoke() == 0
    assert tuple(capsys.readouterr()) == (wire(*values).decode(), "")
    d.one_request()


def test_frame_budget_starts_after_cooperative_output_of_the_previous_frame(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = Clock(monkeypatch)
    d = Delivery(
        account_home,
        monkeypatch,
        chunks=[frame(started()), frame({"type": "heartbeat"}), frame(terminal())],
    )
    output = Output()

    # Slow synchronous output is allowed; do not fabricate a hard OS-write bound.
    def flushed() -> None:
        # Terminal EOF keeps the terminal's existing frame budget. Exercise
        # slow output of preceding frames without resetting that final budget.
        if output.flushes < 3:
            clock.elapse(30)

    output.on_flush = flushed

    async def before(index: int) -> None:
        await clock.step(4.9)

    d.stream.before = before
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", output)
        assert d.invoke() == 0
    assert output.writes == output.flushes == 3
    assert tuple(capsys.readouterr()) == ("", "")
    d.one_request()


def test_terminal_eof_uses_the_same_five_second_complete_frame_budget(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = Clock(monkeypatch)
    prefix = wire(started(), terminal())
    d = Delivery(
        account_home, monkeypatch, chunks=[frame(started()), frame(terminal())]
    )

    async def before(index: int) -> None:
        await clock.step(4.9 if index else 0)

    async def finish() -> None:
        await clock.step(0.2)

    d.stream.before, d.stream.finish = before, finish
    assert d.invoke() == 5
    stdout, stderr = capsys.readouterr()
    assert stdout.encode() == prefix
    value = json.loads(stderr)
    assert value["error"] == {"source": "cli", "code": "request_timeout"}
    assert set(value) == {"error", "request_outcome"}
    assert value["request_outcome"] in {"unknown", "report_received"}
    d.one_request()


@pytest.mark.parametrize(
    "failure,code",
    [
        (httpx.ConnectTimeout(_PRIVATE), "request_timeout"),
        (httpx.ReadTimeout(_PRIVATE), "request_timeout"),
        (httpx.WriteTimeout(_PRIVATE), "request_timeout"),
        (httpx.PoolTimeout(_PRIVATE), "request_timeout"),
        (httpx.ConnectError(_PRIVATE), "transport_failed"),
        (httpx.ReadError(_PRIVATE), "transport_failed"),
        (httpx.RemoteProtocolError(_PRIVATE), "invalid_response"),
        (RuntimeError(_PRIVATE), "internal_failure"),
    ],
)
@pytest.mark.parametrize("stage", ["request", "stream"])
def test_transport_faults_close_once_without_retry_and_preserve_valid_prefix(
    failure: Exception,
    code: str,
    stage: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prefix = b"" if stage == "request" else frame(started())
    d = Delivery(account_home, monkeypatch, chunks=[prefix])
    if stage == "request":
        d.wire.failure = failure
    else:
        d.stream.failure = failure
    assert d.invoke() == (1 if code == "internal_failure" else 5)
    local(capsys.readouterr(), code, prefix=prefix)
    # Before headers a transport is closed, but no response stream was acquired.
    if stage == "request":
        assert d.reads == ["credential"] and len(d.wire.requests) == 1
        assert all(t.closed for t in d.wire.transports)
    else:
        d.one_request()


@pytest.mark.parametrize("exception", [KeyboardInterrupt(_PRIVATE), typer.Abort()])
@pytest.mark.parametrize("stage", ["credential", "request", "stream"])
def test_interrupt_130_closes_only_http_and_keeps_already_printed_frames(
    exception: BaseException,
    stage: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = Delivery(
        account_home,
        monkeypatch,
        chunks=[frame(started())],
        credential_failure=exception if stage == "credential" else None,
    )
    if stage == "request":

        def interrupt(request: httpx.Request) -> None:
            raise exception

        d.wire.on_request = interrupt
    elif stage == "stream":
        d.stream.failure = exception
    assert d.invoke() == 130
    local(
        capsys.readouterr(),
        "interrupted",
        prefix=frame(started()) if stage == "stream" else b"",
        phase="not_submitted" if stage == "credential" else "unknown",
    )
    assert d.reads == ["credential"]
    assert len(d.wire.requests) == (0 if stage == "credential" else 1)
    if stage == "stream":
        d.one_request()
    assert all(t.closed for t in d.wire.transports)


@pytest.mark.parametrize("kind", ["credential_unavailable", "unsafe_credential"])
def test_credential_failure_prevents_any_network_work(
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    context = importlib.import_module("dutchmate_cli.context")
    failure = context.CliFailure(context.CliFailureKind(kind))
    d = Delivery(account_home, monkeypatch, credential_failure=failure)
    assert d.invoke() == 3
    local(capsys.readouterr(), kind, phase="not_submitted")
    assert d.reads == ["credential"] and d.wire.requests == []
    assert d.wire.transports == []


@pytest.mark.parametrize("failure", [BrokenPipeError(_PRIVATE), OSError(_PRIVATE)])
def test_stdout_failure_closes_the_exchange_without_detach_or_more_frames(
    failure: BaseException,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = Delivery(
        account_home, monkeypatch, chunks=[frame(started()), frame(terminal())]
    )
    output = Output()
    output.failure = failure
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", output)
        status = d.invoke()
    assert status == 1 and output.writes == 1
    local(capsys.readouterr(), "output_failed")
    assert d.stream.yielded == 1
    d.one_request()


def test_unusable_stderr_allows_exit_only_without_exception_fallback(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = Delivery(
        account_home, monkeypatch, chunks=[b"invalid-" + _PRIVATE.encode() + b"\n"]
    )
    output = Output()
    output.failure = OSError(_PRIVATE)
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stderr", output)
        code = d.invoke()
    assert code == 1
    assert tuple(capsys.readouterr()) == ("", "")
    assert 1 <= output.writes <= 2
    d.one_request()


@asynccontextmanager
async def us1_loopback(
    home: Path,
    tmp: Path,
    patch: pytest.MonkeyPatch,
    backend: int,
    host: str,
) -> AsyncIterator[tuple[Any, Any, Any, bytes, asyncio.Queue[None]]]:
    """Actual app/runtime/v3/HTTP; only physical I/O and host clock are fixtures."""
    helpers = _evidence._t014_service_helpers(patch)
    helpers._t014_core_helpers(patch)
    core = importlib.import_module("tests.contract.test_follow_runtime")
    service = helpers._t009_module()
    uvicorn = importlib.import_module("uvicorn")
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        if family == socket.AF_INET6:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        listener.bind((host, 0))
        listener.listen(128)
        listener.setblocking(False)
        config = helpers.ServiceConfig(listener.getsockname()[1], host)
        created, _ = helpers._t009_runtime_spy(service, patch)
        bootstrap = helpers.PrivateBootstrap.acquire(config)
        lifespan = None
        try:
            bootstrap.mark_unconfirmed()
            bootstrap.publish_credential()
            token = (home / ".local/state/dutchmate/service/credential").read_bytes()[
                :-1
            ]
            launch = service._LaunchContext(config, bootstrap)
            app = service.create_app(config, _launch_context=launch)
            lifespan = helpers.AppLifespan(app)
            assert (await lifespan.start())["type"] == "lifespan.startup.complete"
            async with core.case(
                tmp, patch, core.BACKEND_FIXTURE_FACTORIES[backend], owner=created[0]
            ) as case:
                await case.activate()
                finished: asyncio.Queue[None] = asyncio.Queue()

                async def observed(scope: Any, receive: Any, send: Any) -> None:
                    try:
                        await app(scope, receive, send)
                    finally:
                        if scope.get("path") == "/v1/observation/follow":
                            # Observe real response/job completion, no substitute
                            # service or Core ownership/lifecycle implementation.
                            finished.put_nowait(None)

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

                def forbidden(*args: Any, **kwargs: Any) -> Any:
                    pytest.fail(
                        "US1 opened an extra backend/RX reader/journal connection"
                    )

                patch.setattr(case.fixture.backend, "open", forbidden)
                patch.setattr(case.fixture.connection, "events", forbidden)
                patch.setattr(importlib.import_module("sqlite3"), "connect", forbidden)
                try:
                    yield case, launch, config, token, finished
                finally:
                    launch.request_stop()
                    await asyncio.wait_for(server.shutdown(sockets=[listener]), 8)
            core.assert_single_rx_owner(case.fixture)
            assert case.probe.close_calls == case.fixture.connection.close_calls == 1
        finally:
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
async def test_t013_us1_real_loopback_cli_journal_and_concurrent_workflows(
    backend: int,
    host: str,
    account_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with us1_loopback(account_home, tmp_path, monkeypatch, backend, host) as (
        case,
        launch,
        config,
        token,
        finished,
    ):
        api = _api()
        client = importlib.import_module("dutchmate_cli.client")
        context = importlib.import_module("dutchmate_cli.context")
        loop = asyncio.get_running_loop()
        output_frames: asyncio.Queue[bytes] = asyncio.Queue()

        class LiveOutput(Output):
            def flush(self) -> None:
                super().flush()
                loop.call_soon_threadsafe(output_frames.put_nowait, self.last)

        output = LiveOutput()
        args = [
            "--host",
            host,
            "--port",
            str(config.port),
            "follow",
            "--session",
            case.journal.session_id.value,
        ]
        endpoint = context.Endpoint(host=host, port=config.port)
        body = {
            "session_id": case.journal.session_id.value,
            "start_inclusive": None,
            "end_exclusive": None,
            "max_records": 10,
            "max_charged_bytes": 16384,
            "cursor": None,
        }

        async def page() -> dict[str, Any]:
            code, raw = await client.exchange_evidence(
                endpoint=endpoint,
                operation="page",
                request_body=body,
                credential=token.decode(),
                delivery=client.DeliveryState(),
            )
            assert code == 0
            return dict(json.loads(raw)["page"])

        async def receive_frame() -> dict[str, Any]:
            raw = await asyncio.wait_for(output_frames.get(), 3)
            assert raw.endswith(b"\n") and raw.count(b"\n") == 1
            return dict(json.loads(raw))

        old = await case.emit(b"before Follow\0\xff", 1)
        jobs: list[asyncio.Task[Any]] = []
        with monkeypatch.context() as patch:
            patch.setattr(sys, "stdout", output)
            first = asyncio.create_task(
                asyncio.to_thread(_commands._console, api, args)
            )
            jobs.append(first)
            try:
                start = await receive_frame()
                assert (
                    start["type"] == "started"
                    and start["start_sequence"] == old.sequence + 1 == 2
                )
                assert start["session_id"] == case.journal.session_id.value
                assert start["run_id"] == case.active_status.run_id.value
                assert start["provenance"]["backend_observation_timestamp_domain"][
                    "observer"
                ] == ("device" if backend else "host")
                assert (
                    not first.done()
                )  # Actual CLI output precedes source end/HTTP EOF.
                monitor = asyncio.create_task(
                    client.exchange_monitor(
                        endpoint=endpoint,
                        credential=token.decode(),
                        delivery=client.DeliveryState(),
                        request_body={
                            "session_id": body["session_id"],
                            "condition_base64": "AFBBU1M=",
                            "timeout_ms": 4000,
                            "max_rx_bytes": 65536,
                        },
                    )
                )
                jobs.append(monitor)
                await asyncio.wait_for(case.clock.wait_started.wait(), 3)
                annotation = asyncio.create_task(
                    client.exchange_annotation(
                        endpoint=endpoint,
                        credential=token.decode(),
                        delivery=client.DeliveryState(),
                        request_body={
                            "session_id": body["session_id"],
                            "text": "PASS is only a client assertion",
                            "client_surface": "cli",
                        },
                    )
                )
                reading = asyncio.create_task(page())
                jobs.extend((annotation, reading))
                (annotation_code, receipt_raw), active_page = await asyncio.wait_for(
                    asyncio.gather(annotation, reading), 3
                )
                assert annotation_code == 0 and not monitor.done() and not first.done()
                receipt = json.loads(receipt_raw)
                assert receipt["annotation"]["assertion_class"] == "client_assertion"
                assert receipt["annotation"]["attribution_basis"] == "client_asserted"
                assert active_page["records"] and not active_page["truncated"]
                binary = await case.emit(bytes(range(256)), 2)
                if backend:
                    await case.fixture.connection.emit_observer_loss(
                        cause="overflow", lost_bytes=None, timestamp=3
                    )
                    await asyncio.wait_for(case.probe.committed["loss"].get(), 3)
                matching = await case.emit(b"\0PASStrailing", 4)
                monitor_code, monitor_raw = await asyncio.wait_for(monitor, 3)
                report = json.loads(monitor_raw)
                assert monitor_code == 0 and report["outcome"] == "matched"
                assert report["observer_loss_records"] == backend
                assert report["match"]["start"]["sequence"] == matching.sequence
                # A genuine origin reset provides later segment end/start records;
                # the started descriptor is never replayed as evidence.
                case.probe.committed["segment_start"].get_nowait()
                domain = replace(
                    case.active_status.acquisition.provenance.backend_observation_timestamp_domain,
                    domain_id="next-domain",
                    origin_id="next-origin",
                )
                await case.fixture.connection.reset_timestamp_origin(domain)
                await asyncio.wait_for(case.probe.committed["segment_start"].get(), 3)
                snapshot = await page()
                assert not snapshot["truncated"]
                expected = [
                    r
                    for r in snapshot["records"]
                    if r["sequence"] >= start["start_sequence"]
                ]
                received: list[dict[str, Any]] = []
                while len(received) < len(expected):
                    value = await receive_frame()
                    if value["type"] == "heartbeat":
                        continue
                    assert value["type"] == "record"
                    received.append(value["record"])
                assert received == expected
                assert base64.b64decode(
                    next(
                        r["payload_base64"]
                        for r in received
                        if r["sequence"] == binary.sequence
                    )
                ) == bytes(range(256))
                assert receipt["annotation"] in received
                assert {r["kind"] for r in received} == {
                    "rx_bytes",
                    "segment_started",
                    "segment_ended",
                    "operation_started",
                    "operation_ended",
                    "client_annotation",
                } | ({"observer_loss"} if backend else set())
                samples = len(case.clock.samples)
                # Simulate the CLI's public Ctrl-C exception at cooperative output;
                # installed OS-signal validation belongs to T020.
                output.failure = KeyboardInterrupt(_PRIVATE)
                assert await asyncio.wait_for(asyncio.shield(first), 5) == 130
                await asyncio.wait_for(finished.get(), 3)
                assert (
                    len(case.clock.samples) == samples
                )  # Idle heartbeat sampled no evidence clock.
                local(capsys.readouterr(), "interrupted")
                assert case.owner.status().state.value == "active"
                assert (
                    case.probe.close_calls == case.fixture.connection.close_calls == 0
                )
                after = await case.emit(b"capture after client exit\0\xff", 13)
                output.failure = None
                second = asyncio.create_task(
                    asyncio.to_thread(_commands._console, api, args)
                )
                jobs.append(second)
                resumed = await receive_frame()
                assert (
                    resumed["type"] == "started"
                    and resumed["start_sequence"] == after.sequence + 1
                )
                launch.request_stop()  # Synchronous seal before server HTTP drain.
                end = await receive_frame()
                assert end == {
                    "type": "terminal",
                    "reason": "service_stopping",
                    "next_sequence": after.sequence + 1,
                    "source_end_exclusive": None,
                }
                assert await asyncio.wait_for(asyncio.shield(second), 3) == 0
                await asyncio.wait_for(finished.get(), 3)
                assert case.owner.status().state.value == "active"
                assert (
                    case.probe.close_calls == case.fixture.connection.close_calls == 0
                )
                assert tuple(capsys.readouterr()) == ("", "")
            finally:
                launch.request_stop()
                await asyncio.wait_for(asyncio.gather(*jobs, return_exceptions=True), 8)


# T015: external delivery edges only; original T012/T013 cases stay unchanged.
def t015_sized_frame(kind: str, size: int, device: bool) -> dict[str, Any]:
    unit = 'é😀\n\r\\"\x01'
    width = len(_json(unit)) - 2
    if kind == "started":
        value = started(device=device)
        value["provenance"]["connection_provenance"]["fields"] = [
            {"name": "padding", "value": ""}
        ]
        target = value["provenance"]["connection_provenance"]["fields"][0]
        key = "value"
    elif kind == "gap":
        value = gap()
        target = value["retention_marker"]["first_discarded_timestamp"]["domain"]
        key = "origin_id"
        target[key] = ""
    else:
        record = records(device)[1]
        record["sequence"], record["payload_base64"] = 3, ""
        value = {"type": "record", "record": record}
        remaining = size - len(_json(value))
        record["payload_base64"] = base64.b64encode(
            b"\xff\0\n" * (remaining // 4)
        ).decode()
        record["connection_id"] += "p" * (remaining % 4)
        assert len(_json(value)) == size
        return value
    remaining = size - len(_json(value))
    target[key] = unit * (remaining // width) + "p" * (remaining % width)
    assert len(_json(value)) == size
    return value


@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced"])
@pytest.mark.parametrize("size", [_LIMIT - 1, _LIMIT, _LIMIT + 1])
@pytest.mark.parametrize("kind", ["started", "record", "gap"])
def test_t015_encoded_frame_edges_after_escaping_and_base64_do_not_use_character_count(
    device: bool,
    size: int,
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = t015_sized_frame(kind, size, device)
    prefix = [] if kind == "started" else [started(device=device)]
    position = {"started": 3, "record": 4, "gap": 5}[kind]
    end = terminal(next_sequence=position, cutoff=position)
    raw = frame(value)
    # Split immediately before the final UTF-8 byte/closing delimiter and LF.
    chunks = [
        *(frame(v) for v in prefix),
        raw[:-2],
        raw[-2:-1],
        b"",
        raw[-1:],
        frame(end),
    ]
    d = Delivery(account_home, monkeypatch, chunks=chunks)
    if size <= _LIMIT:
        assert d.invoke() == 0
        assert tuple(capsys.readouterr()) == (wire(*prefix, value, end).decode(), "")
    else:
        assert d.invoke() == 5
        local(capsys.readouterr(), "invalid_response", prefix=wire(*prefix))
    d.one_request()


def t015_variants(device: bool) -> list[dict[str, Any]]:
    values = records(device)
    values[1]["payload_base64"] = base64.b64encode(bytes(range(256))).decode()
    values[3]["condition_base64"] = "AA0K/w=="
    values[5]["text"] = '\x01\r\n\\"é😀' * 93 + "\t"
    assert len(values[5]["text"].encode()) == 1024
    return values


@pytest.mark.parametrize("device", [False, True], ids=["basic", "enhanced"])
@pytest.mark.parametrize("index", range(7))
def test_t015_every_variant_accepts_nested_key_reordering_and_bytewise_utf8_escape_lf_splits(
    device: bool,
    index: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = t015_variants(device)
    prefix = [
        started(device=device),
        *({"type": "record", "record": r} for r in values[:index]),
    ]
    selected = {"type": "record", "record": values[index]}
    # JSON object key order is allowed to vary; evidence/frame sequence is not.
    raw = (
        json.dumps(
            _annotations._reverse(selected), ensure_ascii=False, separators=(",", ":")
        ).encode()
        + b"\n"
    )
    end = terminal(next_sequence=4 + index, cutoff=4 + index)
    chunks = [wire(*prefix), *(raw[n : n + 1] for n in range(len(raw))), frame(end)]
    d = Delivery(account_home, monkeypatch, chunks=chunks)
    assert d.invoke() == 0
    assert tuple(capsys.readouterr()) == (wire(*prefix, selected, end).decode(), "")
    d.one_request()


@pytest.mark.parametrize("index", range(7))
@pytest.mark.parametrize("fault", ["duplicate", "unknown", "nan", "bool", "sequence"])
def test_t015_each_variant_rejects_nested_malformed_or_out_of_sequence_frame_before_output(
    index: int,
    fault: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = t015_variants(True)
    prefix = [
        started(device=True),
        *({"type": "record", "record": r} for r in values[:index]),
    ]
    record = values[index]
    paths: list[tuple[str, ...]] = [
        ("provenance", "connection_provenance", "backend_schema_version"),
        ("observed_at", "value"),
        ("lost_bytes",),
        ("timeout_ms",),
        ("clock", "decided_at_ns"),
        ("received_at_ns",),
        ("sequence",),
    ]
    if fault == "unknown":
        target = record["provenance"] if index in (0, 3) else record
        target["private-T015"] = _PRIVATE
    elif fault in ("nan", "bool"):
        set_path(record, paths[index], float("nan") if fault == "nan" else True)
    elif fault == "sequence":
        record["sequence"] += 1
    raw = json.dumps(
        {"type": "record", "record": record}, ensure_ascii=False, separators=(",", ":")
    ).encode()
    if fault == "duplicate":
        sequence = str(3 + index).encode()
        raw = raw.replace(
            b'"sequence":' + sequence,
            b'"sequence":' + sequence + b',"sequence":' + sequence,
            1,
        )
    d = Delivery(
        account_home,
        monkeypatch,
        chunks=[wire(*prefix), raw + b"\n", frame(terminal())],
    )
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response", prefix=wire(*prefix))
    d.one_request()


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate-range",
        "duplicate-domain",
        "unknown-endpoint",
        "nan-count",
        "bool-bytes",
        "reversed-fields",
        "counter-mismatch",
        "domain-mismatch",
        "non-prefix",
        "first-only",
        "last-only",
        "zero-count",
    ],
)
def test_t015_nested_gap_coherence_and_opaque_array_order_preservation(
    fault: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prefix = frame(started())
    value = gap()
    marker = value["retention_marker"]
    if fault == "unknown-endpoint":
        marker["last_discarded_timestamp"]["private"] = _PRIVATE
    elif fault == "nan-count":
        marker["discarded_record_count"] = float("nan")
    elif fault == "bool-bytes":
        marker["discarded_rx_payload_byte_count"] = False
    elif fault == "counter-mismatch":
        marker["discarded_record_count"] = 4
    elif fault == "domain-mismatch":
        marker["first_discarded_timestamp"]["timestamp"]["domain_id"] = "other-domain"
    elif fault == "non-prefix":
        marker["expired_range"]["start_inclusive"] = 1
    elif fault == "first-only":
        marker["last_discarded_timestamp"] = None
    elif fault == "last-only":
        marker["first_discarded_timestamp"] = None
    elif fault == "zero-count":
        marker["discarded_record_count"] = 0
    elif fault == "reversed-fields":
        value = started()
        value["provenance"]["connection_provenance"]["fields"].reverse()
        prefix = b""
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    if fault == "duplicate-range":
        raw = raw.replace(
            b'"start_inclusive":3', b'"start_inclusive":3,"start_inclusive":3', 1
        )
    elif fault == "duplicate-domain":
        token = b'"origin_id":'
        point = raw.index(token)
        end = raw.index(b'"', point + len(token) + 1)
        original = raw[point : end + 1]
        raw = raw[:point] + original + b"," + original + raw[end + 1 :]
    if fault == "reversed-fields":
        # 008 preserves opaque array order; it is not out-of-sequence evidence.
        d = Delivery(account_home, monkeypatch, chunks=[raw + b"\n", frame(terminal())])
        assert d.invoke() == 0
        assert tuple(capsys.readouterr()) == (wire(value, terminal()).decode(), "")
        d.one_request()
        return
    d = Delivery(
        account_home,
        monkeypatch,
        chunks=[prefix, raw + b"\n", frame(terminal(next_sequence=5, cutoff=5))],
    )
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response", prefix=prefix)
    d.one_request()


@pytest.mark.parametrize("kind", ["started", "record", "gap", "terminal"])
@pytest.mark.parametrize("cut", ["missing-lf", "partial-utf8"])
def test_t015_partial_frame_eof_never_prints_an_unterminated_object(
    kind: str,
    cut: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = {
        "started": started(),
        "record": {"type": "record", "record": records()[5] | {"sequence": 3}},
        "gap": gap(),
        "terminal": terminal(),
    }[kind]
    prefix = b"" if kind == "started" else frame(started())
    raw = frame(value)[:-1]
    if cut == "partial-utf8":
        # A transport can end inside a Unicode scalar, even after valid JSON bytes.
        raw += b"\xf0\x9f"
    d = Delivery(account_home, monkeypatch, chunks=[prefix, raw[:-1], b"", raw[-1:]])
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response", prefix=prefix)
    d.one_request()


@pytest.mark.parametrize(
    "trailing", [b"\r", b" ", b"\0", b"\xff", b'{"type":"terminal"']
)
@pytest.mark.parametrize("layout", ["same-chunk", "later-chunk", "empty-chunks"])
def test_t015_terminal_rejects_every_trailing_byte_across_empty_transport_chunks(
    trailing: bytes,
    layout: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prefix = wire(started(), terminal())
    chunks = (
        [prefix + trailing]
        if layout == "same-chunk"
        else [prefix, *([b""] * 3 if layout == "empty-chunks" else []), trailing]
    )
    d = Delivery(account_home, monkeypatch, chunks=chunks)
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response", prefix=prefix)
    d.one_request()


@pytest.mark.parametrize(
    "extra",
    [
        [("Content-Encoding", "br")],
        [("Content-Encoding", "deflate")],
        [("Content-Encoding", "gzip, identity")],
        [("Content-Encoding", "identity; q=1")],
        [("Content-Length", "0")],
        [("Content-Length", "100")],
        [("Content-Length", "0"), ("Transfer-Encoding", "chunked")],
        [("Transfer-Encoding", "identity")],
        [("Transfer-Encoding", "gzip")],
        [("Transfer-Encoding", "chunked, chunked")],
        [("Transfer-Encoding", "chunked"), ("Transfer-Encoding", "chunked")],
    ],
)
def test_t015_identity_only_response_rejects_conflicting_framing_before_reading_bytes(
    extra: list[tuple[str, str]],
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = Delivery(
        account_home,
        monkeypatch,
        headers=[("Content-Type", "application/x-ndjson"), *extra],
    )
    assert d.invoke() == 5
    local(capsys.readouterr(), "invalid_response")
    assert d.stream.yielded == 0
    d.one_request()


@pytest.mark.parametrize("kind", ["record", "gap", "terminal"])
def test_t015_trickle_delimiter_cannot_extend_any_complete_frame_deadline(
    kind: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = Clock(monkeypatch)
    value = {
        "record": {"type": "record", "record": records()[1] | {"sequence": 3}},
        "gap": gap(),
        "terminal": terminal(),
    }[kind]
    body = frame(value)
    d = Delivery(
        account_home, monkeypatch, chunks=[frame(started()), body[:-1], b"", b"\n"]
    )

    async def before(index: int) -> None:
        await clock.step([0, 2, 2, 1.1][index])

    d.stream.before = before
    assert d.invoke() == 5
    local(capsys.readouterr(), "request_timeout", prefix=frame(started()))
    assert d.stream.yielded == 3
    d.one_request()
