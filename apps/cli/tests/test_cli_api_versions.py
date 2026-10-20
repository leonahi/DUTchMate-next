"""012 T018 RED: literal version selection, closed v2 unions, unchanged v1.

Exercise actual console/HTTPX/framing with independent peer bytes. Shared old
goldens remain untouched; no production projector supplies a new expectation.
"""

import copy
import importlib
from pathlib import Path
from typing import Any

import pytest

_evidence = importlib.import_module("test_cli_evidence")
_commands = importlib.import_module("test_cli_commands")
_transport = importlib.import_module("test_cli_transport")
_monitor = importlib.import_module("test_cli_monitor")
_annotations = importlib.import_module("test_cli_annotations")
_follow = importlib.import_module("test_cli_follow")
_interact = importlib.import_module("test_cli_interact")
_json = _evidence._json
_SESSION = _interact._SESSION
_PRIVATE = _evidence._PRIVATE
_PAGE_BODY = {
    "session_id": _SESSION,
    "start_inclusive": None,
    "end_exclusive": None,
    "max_records": 32,
    "max_charged_bytes": 65536,
    "cursor": None,
}


def markers(device: bool = False) -> list[dict[str, Any]]:
    """The three additive public evidence variants, in canonical field order."""
    value = _interact.report("detached", device=device)
    provenance = copy.deepcopy(value["provenance"])
    del provenance["boundary_basis"], provenance["causation"]
    return [
        {
            "kind": "interact_started",
            "sequence": 3,
            "operation_id": _interact._OPERATION,
            "provenance": provenance,
            "profile_version": 2,
            "authorization": {"uart_tx_enabled": True},
            "conditions_base64": ["UEFTUw==", "RkFJTA=="],
            "timeout_ms": 1000,
            "max_rx_bytes": 4,
            "write_timeout_ms": 1000,
            "clock_origin_id": _interact._ORIGIN,
            "payload_base64": "AP9TRU5E",
        },
        {
            "kind": "uart_tx_settled",
            "sequence": 6,
            "operation_id": _interact._OPERATION,
            "start_sequence": 3,
            **value["tx"],
        },
        {
            "kind": "interact_ended",
            "sequence": 7,
            "operation_id": _interact._OPERATION,
            "start_sequence": 3,
            "tx_settled_sequence": 6,
            "tx": value["tx"],
            "tx_audit_failure": None,
            "outcome": "detached",
            "observation": value["observation"],
        },
    ]


def ten_records(device: bool = False) -> list[dict[str, Any]]:
    values = _follow.records(device)
    # Existing seven goldens keep their exact fields/values and sequence3..9.
    added = markers(device)
    added[0]["sequence"] = 10
    added[1].update(sequence=11, start_sequence=10)
    added[2].update(sequence=12, start_sequence=10, tx_settled_sequence=11)
    added[2]["observation"]["window"] = {"start_inclusive": 11, "end_exclusive": 11}
    return [*values, *added]


_COMMANDS: list[tuple[list[str], str, str, dict[str, Any] | None, Any]] = [
    (["status"], "GET", "/observation/status", None, _transport._report("inactive")),
    (
        ["attach", "--profile", "/missing/profile", "--journal", "/missing/journal"],
        "POST",
        "/observation/attach",
        {"profile_path": "/missing/profile", "journal_path": "/missing/journal"},
        _transport._report(),
    ),
    (["detach"], "POST", "/observation/detach", None, _transport._report("terminated")),
    (
        _monitor._ARGS[2:],
        "POST",
        "/observation/monitor",
        _monitor._BODY,
        _monitor._report(),
    ),
    (
        _annotations._ARGS[2:],
        "POST",
        "/observation/annotations",
        _annotations._BODY,
        _annotations._receipt(),
    ),
    (
        _evidence._RECORD_ARGS[2:],
        "POST",
        "/evidence/record",
        {"session_id": _SESSION, "sequence": 0},
        _evidence._report(),
    ),
    (
        _evidence._PAGE_ARGS[2:],
        "POST",
        "/evidence/page",
        _PAGE_BODY,
        _evidence._report(),
    ),
]


@pytest.mark.parametrize(
    "prefix,version",
    [([], 1), (["--api-version", "1"], 1), (["--api-version", "2"], 2)],
)
@pytest.mark.parametrize(
    "args,method,path,body,value",
    _COMMANDS,
    ids=[item[0][0] + item[2] for item in _COMMANDS],
)
def test_each_command_selects_one_literal_path_and_preserves_legacy_wire_bytes(
    prefix: list[str],
    version: int,
    args: list[str],
    method: str,
    path: str,
    body: dict[str, Any] | None,
    value: Any,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    d = _evidence.Delivery(account_home, monkeypatch, body=_json(value))
    assert d.invoke([*prefix, "--port", "8765", *args]) == 0
    assert tuple(capsys.readouterr()) == ((_json(value) + b"\n").decode(), "")
    assert d.reads == ["credential"] and d.imports == [] and len(d.wire.requests) == 1
    request = d.wire.requests[0]
    assert (
        request.method == method
        and request.url.raw_path == f"/v{version}{path}".encode()
    )
    assert request.content == (b"" if body is None else _json(body))
    assert request.headers.get_list("authorization") == ["Bearer " + _evidence._TOKEN]
    assert request.headers.get_list("accept-encoding") == ["identity"]
    assert all(t.closed for t in d.wire.transports)


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--help"],
        ["--api-version", "2", "--help"],
        ["--api-version", "2", "evidence", "page", "--help"],
    ],
)
def test_version_help_needs_no_credentials_target_or_network_and_advertises_default_one(
    args: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _evidence._api()
    attempts = _commands._block_preparation(api, monkeypatch)
    result = _commands._runner(api, args)
    assert result.exit_code == 0 and result.exception is None and not result.stderr
    if "evidence" not in args:
        assert "--api-version" in result.stdout and "1" in result.stdout
    assert attempts == []


@pytest.mark.parametrize("version", ["", "0", "3", "01", "1.0", "true", "v2", _PRIVATE])
def test_invalid_global_version_is_fixed_private_and_precedes_credentials(
    version: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with monkeypatch.context() as patch:
        _interact.recognized(patch)
    api = _evidence._api()
    attempts = _commands._block_preparation(api, monkeypatch)
    assert (
        _evidence._command(api, ["--api-version", version, "--port", "8765", "status"])
        == 2
    )
    _evidence._local(capsys.readouterr(), "invalid_arguments")
    assert attempts == []


@pytest.mark.parametrize("command", ["status", "attach", "detach"])
@pytest.mark.parametrize("version", [None, "1", "2"])
@pytest.mark.parametrize("tx_enabled", [False, True])
def test_profile_v2_is_accepted_only_by_explicit_v2_lifecycle_validator(
    command: str,
    version: str | None,
    tx_enabled: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args, _, path, _, original = next(
        item for item in _COMMANDS if item[0][0] == command
    )
    value = copy.deepcopy(original if command != "status" else _transport._report())
    value["runtime"]["profile"]["format_version"] = 2
    value["runtime"]["profile"]["policy"]["uart_tx_enabled"] = tx_enabled
    d = _evidence.Delivery(account_home, monkeypatch, body=_json(value))
    prefix = [] if version is None else ["--api-version", version]
    assert d.invoke([*prefix, "--port", "8765", *args]) == (0 if version == "2" else 5)
    if version == "2":
        assert tuple(capsys.readouterr()) == ((_json(value) + b"\n").decode(), "")
    else:
        _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert d.reads == ["credential"] and len(d.wire.requests) == 1
    assert d.wire.requests[0].url.path == f"/v{version or '1'}{path}"


@pytest.mark.parametrize("profile_version", [1, 2])
@pytest.mark.parametrize(
    "path,bad",
    [
        (("format_version",), 3),
        (("format_version",), True),
        (("policy", "uart_rx_enabled"), 0),
        (("policy", "evidence_recording_enabled"), None),
        (("policy", "uart_tx_enabled"), "true"),
        (("policy", "semantic_control_enabled"), "true"),
        (("policy", "automatic_reconnect_enabled"), 1),
        (("policy", "new_permission"), True),
        (("open_lines", "dtr"), "pulse"),
    ],
)
def test_v2_does_not_relax_profile_closed_fields_or_boolean_and_enum_validation(
    profile_version: int,
    path: tuple[str, ...],
    bad: Any,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = _transport._report()
    value["runtime"]["profile"]["format_version"] = profile_version
    _evidence._at(value["runtime"]["profile"], path[:-1])[path[-1]] = bad
    d = _evidence.Delivery(account_home, monkeypatch, body=_json(value))
    assert d.invoke(["--api-version", "2", "--port", "8765", "status"]) == 5
    _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert len(d.wire.requests) == 1 and d.reads == ["credential"]


@pytest.mark.parametrize(
    "device", [False, True], ids=["basic-shaped", "enhanced-shaped"]
)
@pytest.mark.parametrize("index", range(10))
@pytest.mark.parametrize("operation", ["record", "page"])
def test_v2_evidence_has_all_ten_closed_variants_with_legacy_canonical_bytes(
    device: bool,
    index: int,
    operation: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    item = ten_records(device)[index]
    value = _evidence._report(records=[item], snapshot_end_exclusive=13)
    args = _evidence._RECORD_ARGS if operation == "record" else _evidence._PAGE_ARGS
    args = list(args)
    if operation == "record":
        args[-1] = str(item["sequence"])
    d = _evidence.Delivery(
        account_home, monkeypatch, body=_json(_monitor._reverse_objects(value))
    )
    assert d.invoke(["--api-version", "2", *args]) == 0
    assert tuple(capsys.readouterr()) == ((_json(value) + b"\n").decode(), "")
    expected = (
        {"session_id": _SESSION, "sequence": item["sequence"]}
        if operation == "record"
        else _PAGE_BODY
    )
    d.one_request(f"/v2/evidence/{operation}", expected)


@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize("version", [None, "1", "2"])
def test_mixed_ten_kind_page_requires_explicit_v2_and_never_filters_new_records(
    device: bool,
    version: str | None,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = _evidence._report(records=ten_records(device), snapshot_end_exclusive=13)
    d = _evidence.Delivery(account_home, monkeypatch, body=_json(value))
    prefix = [] if version is None else ["--api-version", version]
    assert d.invoke([*prefix, *_evidence._PAGE_ARGS]) == (0 if version == "2" else 5)
    if version == "2":
        assert tuple(capsys.readouterr()) == ((_json(value) + b"\n").decode(), "")
    else:
        _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    d.one_request(
        f"/v{version or '1'}/evidence/page",
        _PAGE_BODY,
    )


_REQUIRED = [(i, key) for i, item in enumerate(markers()) for key in item]


@pytest.mark.parametrize("index,key", _REQUIRED)
def test_every_new_evidence_field_is_required_without_empty_blob_or_codec_leakage(
    index: int,
    key: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    item = markers()[index]
    del item[key]
    value = _evidence._report(records=[item], snapshot_end_exclusive=8)
    d = _evidence.Delivery(account_home, monkeypatch, body=_json(value))
    assert d.invoke(["--api-version", "2", *_evidence._PAGE_ARGS]) == 5
    _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    d.one_request(
        "/v2/evidence/page",
        _PAGE_BODY,
    )


_BAD_MARKERS = [
    (0, ("profile_version",), 1),
    (0, ("authorization", "uart_tx_enabled"), False),
    (0, ("authorization", "caller_authorized"), True),
    (0, ("write_timeout_ms",), 999),
    (0, ("conditions_base64",), []),
    (0, ("conditions_base64",), ["AB=="]),
    (0, ("payload_base64",), ""),
    (0, ("clock_origin_id",), "not-uuid"),
    (0, ("provenance", "boundary_basis"), "core_observation_order"),
    (1, ("start_sequence",), 6),
    (1, ("status",), "wire_transmitted"),
    (1, ("accepted_prefix_bytes",), True),
    (1, ("acknowledgement_scope",), "dut_receipt"),
    (2, ("tx_settled_sequence",), 7),
    (2, ("tx", "failure_code"), "unknown"),
    (2, ("tx_audit_failure",), {"source": "journal", "code": "busy"}),
    (2, ("observation", "window", "start_inclusive"), 3),
    (2, ("observation", "match"), {}),
    (2, ("outcome",), "success"),
    *[(i, ("payload",), _PRIVATE) for i in range(3)],
]


@pytest.mark.parametrize("index,path,bad", _BAD_MARKERS)
@pytest.mark.parametrize("follow", [False, True], ids=["page", "follow"])
def test_v2_retrieval_and_follow_share_strict_new_record_shapes(
    index: int,
    path: tuple[str, ...],
    bad: Any,
    follow: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    item = markers()[index]
    _evidence._at(item, path[:-1])[path[-1]] = bad
    if follow:
        start = _follow.started(sequence=item["sequence"])
        prefix = _follow.frame(start)
        d = _follow.Delivery(
            account_home,
            monkeypatch,
            chunks=[
                _follow.wire(
                    start,
                    {"type": "record", "record": item},
                    _follow.terminal(
                        next_sequence=item["sequence"] + 1, cutoff=item["sequence"] + 1
                    ),
                )
            ],
        )
        args = ["--api-version", "2", *_follow._ARGS]
    else:
        prefix = b""
        value = _evidence._report(records=[item], snapshot_end_exclusive=8)
        d = _evidence.Delivery(account_home, monkeypatch, body=_json(value))
        args = ["--api-version", "2", *_evidence._PAGE_ARGS]
    assert d.invoke(args) == 5
    _follow.local(capsys.readouterr(), "invalid_response", prefix=prefix)
    assert d.reads == ["credential"] and len(d.wire.requests) == 1
    assert d.wire.requests[0].url.path == (
        "/v2/observation/follow" if follow else "/v2/evidence/page"
    )


@pytest.mark.parametrize("index", range(7))
@pytest.mark.parametrize("follow", [False, True])
def test_v2_keeps_each_legacy_record_validator_closed_in_page_and_follow(
    index: int,
    follow: bool,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    item = _follow.records()[index]
    item["private_extension"] = _PRIVATE
    if follow:
        start = _follow.started(sequence=item["sequence"])
        d = _follow.Delivery(
            account_home,
            monkeypatch,
            chunks=[_follow.wire(start, {"type": "record", "record": item})],
        )
        args = ["--api-version", "2", *_follow._ARGS]
        prefix = _follow.frame(start)
    else:
        value = _evidence._report(records=[item], snapshot_end_exclusive=10)
        d = _evidence.Delivery(account_home, monkeypatch, body=_json(value))
        args = ["--api-version", "2", *_evidence._PAGE_ARGS]
        prefix = b""
    assert d.invoke(args) == 5
    _follow.local(capsys.readouterr(), "invalid_response", prefix=prefix)
    assert d.reads == ["credential"] and len(d.wire.requests) == 1


@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize(
    "prefix,version",
    [([], 1), (["--api-version", "1"], 1), (["--api-version", "2"], 2)],
)
def test_follow_keeps_five_frame_grammar_one_request_and_legacy_records(
    device: bool,
    prefix: list[str],
    version: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = ten_records(device) if version == 2 else _follow.records(device)
    start = _follow.started(device=device)
    end = 13 if version == 2 else 10
    frames = [
        start,
        *({"type": "record", "record": item} for item in values),
        {"type": "heartbeat"},
        _follow.terminal(next_sequence=end, cutoff=end),
    ]
    raw = _follow.wire(*frames)
    d = _follow.Delivery(account_home, monkeypatch, chunks=[raw[:5], raw[5:]])
    assert d.invoke([*prefix, *_follow._ARGS]) == 0
    assert tuple(capsys.readouterr()) == (raw.decode(), "")
    assert d.reads == ["credential"] and d.imports == [] and len(d.wire.requests) == 1
    request = d.wire.requests[0]
    assert request.url.raw_path == f"/v{version}/observation/follow".encode()
    assert request.content == _json({"session_id": _SESSION})
    assert request.headers.get_list("accept") == ["application/x-ndjson"]
    assert request.headers.get_list("accept-encoding") == ["identity"]
    assert d.stream.closed and all(t.closed for t in d.wire.transports)


def test_v2_follow_preserves_explicit_retention_gap_and_heartbeat_frames(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = _follow.wire(
        _follow.started(),
        _follow.gap(),
        {"type": "heartbeat"},
        _follow.terminal(next_sequence=5, cutoff=5),
    )
    d = _follow.Delivery(account_home, monkeypatch, chunks=[raw])
    assert d.invoke(["--api-version", "2", *_follow._ARGS]) == 0
    assert tuple(capsys.readouterr()) == (raw.decode(), "")
    assert d.reads == ["credential"] and len(d.wire.requests) == 1
    assert d.wire.requests[0].url.raw_path == b"/v2/observation/follow"
    assert d.stream.closed


@pytest.mark.parametrize("prefix", [[], ["--api-version", "1"]])
@pytest.mark.parametrize("index", range(3))
def test_v1_follow_rejects_each_new_record_without_filtering_or_silent_upgrade(
    prefix: list[str],
    index: int,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    item = markers()[index]
    start = _follow.started(sequence=item["sequence"])
    d = _follow.Delivery(
        account_home,
        monkeypatch,
        chunks=[
            _follow.wire(
                start,
                {"type": "record", "record": item},
                _follow.terminal(
                    next_sequence=item["sequence"] + 1, cutoff=item["sequence"] + 1
                ),
            )
        ],
    )
    assert d.invoke([*prefix, *_follow._ARGS]) == 5
    _follow.local(capsys.readouterr(), "invalid_response", prefix=_follow.frame(start))
    assert d.reads == ["credential"] and len(d.wire.requests) == 1
    assert d.wire.requests[0].url.raw_path == b"/v1/observation/follow"
    assert d.stream.closed


@pytest.mark.parametrize(
    "fault",
    [
        "unknown_type",
        "record_before_start",
        "duplicate_start",
        "sequence_gap",
        "bad_heartbeat",
        "no_terminal",
        "after_terminal",
    ],
)
def test_v2_follow_does_not_relax_ordering_or_terminate_by_silently_dropping_bad_frames(
    fault: str,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    start = _follow.started(sequence=10)
    item = ten_records()[7]
    frame = {"type": "record", "record": item}
    frames: list[dict[str, Any]] = [start]
    expected_prefix = _follow.frame(start)
    match fault:
        case "unknown_type":
            frames.append({"type": "interact", "value": _PRIVATE})
        case "record_before_start":
            frames = [frame]
            expected_prefix = b""
        case "duplicate_start":
            frames.append(start)
        case "sequence_gap":
            item["sequence"] = 11
            frames.append(frame)
        case "bad_heartbeat":
            frames.append({"type": "heartbeat", "next_sequence": 11})
        case "no_terminal":
            pass
        case "after_terminal":
            frames += [_follow.terminal(next_sequence=10, cutoff=10), frame]
            expected_prefix += _follow.frame(frames[1])
    d = _follow.Delivery(account_home, monkeypatch, chunks=[_follow.wire(*frames)])
    assert d.invoke(["--api-version", "2", *_follow._ARGS]) == 5
    _follow.local(capsys.readouterr(), "invalid_response", prefix=expected_prefix)
    assert d.reads == ["credential"] and len(d.wire.requests) == 1 and d.stream.closed


@pytest.mark.parametrize("version", ["1", "2"])
@pytest.mark.parametrize("args,method,path,body,value", _COMMANDS)
def test_explicit_version_error_is_remote_four_without_probe_fallback_or_retry(
    version: str,
    args: list[str],
    method: str,
    path: str,
    body: Any,
    value: Any,
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = {"error": {"source": "request", "code": "unsupported_api_version"}}
    d = _evidence.Delivery(account_home, monkeypatch, body=_json(error), status=409)
    assert d.invoke(["--api-version", version, "--port", "8765", *args]) == 4
    assert tuple(capsys.readouterr()) == ("", (_json(error) + b"\n").decode())
    assert d.reads == ["credential"] and len(d.wire.requests) == 1
    assert d.wire.requests[0].method == method
    assert d.wire.requests[0].url.path == f"/v{version}{path}"


# T021: independently authored peer bytes, retaining all earlier assertions.
@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize("stream", [False, True], ids=["page", "follow"])
@pytest.mark.parametrize("stride", [7, 1024])
def test_t021_all_ten_variants_preserve_binary_escaped_provenance_across_chunks(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    device: bool,
    stream: bool,
    stride: int,
) -> None:
    import base64

    values = ten_records(device)
    padding = 'é😀\n\r\\"\x01' * 128
    for index in (0, 3, 7):
        values[index]["provenance"]["connection_provenance"]["fields"] = [
            {"name": "opaque", "value": padding}
        ]
    values[1]["payload_base64"] = base64.b64encode(bytes(range(256))).decode()
    values[7]["payload_base64"] = base64.b64encode(bytes(range(256)) * 16).decode()
    values[7]["conditions_base64"] = [base64.b64encode(bytes(range(256))).decode()] * 4
    if stream:
        raw = _follow.wire(
            _follow.started(device=device),
            *[{"type": "record", "record": value} for value in values],
            {"type": "heartbeat"},
            _follow.terminal(next_sequence=13, cutoff=13),
        )
        d = _follow.Delivery(
            account_home,
            monkeypatch,
            chunks=[raw[i : i + stride] for i in range(0, len(raw), stride)],
        )
        args = ["--api-version", "2", *_follow._ARGS]
    else:
        raw = _json(_evidence._report(records=values, snapshot_end_exclusive=13))
        d = _evidence.Delivery(
            account_home,
            monkeypatch,
            chunks=[raw[i : i + stride] for i in range(0, len(raw), stride)],
        )
        args = ["--api-version", "2", *_evidence._PAGE_ARGS]
    assert d.invoke(args) == 0
    assert tuple(capsys.readouterr()) == ((raw if stream else raw + b"\n").decode(), "")
    assert len(d.wire.requests) == 1 and d.reads == ["credential"] and d.imports == []
    assert d.wire.requests[0].url.raw_path == (
        b"/v2/observation/follow" if stream else b"/v2/evidence/page"
    )
    assert all(t.closed for t in d.wire.transports)


@pytest.mark.parametrize("index", range(10))
@pytest.mark.parametrize("stream", [False, True], ids=["page", "follow"])
@pytest.mark.parametrize(
    "fault",
    [
        "duplicate-kind",
        "bool-sequence",
        "nan-sequence",
        "overflow-sequence",
        "unknown-field",
        "surrogate-kind",
    ],
)
def test_t021_every_evidence_variant_rejects_ambiguous_json_without_partial_record(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    index: int,
    stream: bool,
    fault: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.DEBUG)
    item = ten_records()[index]
    raw_item = _json(item)
    if fault == "duplicate-kind":
        raw_item = raw_item[:-1] + b',"\\u006bind":' + _json(item["kind"]) + b"}"
    elif fault == "unknown-field":
        raw_item = raw_item[:-1] + b',"private_diagnostic":' + _json(_PRIVATE) + b"}"
    elif fault == "surrogate-kind":
        raw_item = raw_item.replace(_json(item["kind"]), b'"\\udfff"', 1)
    else:
        token = {
            "bool-sequence": b"true",
            "nan-sequence": b"NaN",
            "overflow-sequence": b"1e9999",
        }[fault]
        raw_item = raw_item.replace(
            b'"sequence":' + str(item["sequence"]).encode(), b'"sequence":' + token, 1
        )
    if stream:
        prefix = _follow.frame(_follow.started(sequence=item["sequence"]))
        raw = prefix + b'{"type":"record","record":' + raw_item + b"}\n"
        d = _follow.Delivery(account_home, monkeypatch, chunks=[raw[:11], raw[11:]])
        args = ["--api-version", "2", *_follow._ARGS]
    else:
        prefix = b""
        raw = _json(
            _evidence._report(records=[item], snapshot_end_exclusive=13)
        ).replace(_json(item), raw_item, 1)
        d = _evidence.Delivery(account_home, monkeypatch, body=raw)
        args = ["--api-version", "2", *_evidence._PAGE_ARGS]
    assert d.invoke(args) == 5
    _follow.local(capsys.readouterr(), "invalid_response", prefix=prefix)
    assert len(d.wire.requests) == 1 and d.reads == ["credential"] and d.imports == []
    assert _PRIVATE not in caplog.text and _evidence._TOKEN not in caplog.text
    assert all(t.closed for t in d.wire.transports)


@pytest.mark.parametrize("stream", [False, True], ids=["page", "follow"])
@pytest.mark.parametrize("size", [1048575, 1048576, 1048577])
def test_t021_new_start_projection_has_exact_json_cap_and_follow_lf_is_excluded(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stream: bool,
    size: int,
) -> None:
    item = ten_records()[7]
    item["provenance"]["connection_provenance"]["fields"] = [
        {"name": "padding", "value": ""}
    ]
    value = (
        {"type": "record", "record": item}
        if stream
        else _evidence._report(records=[item], snapshot_end_exclusive=13)
    )
    budget = size - len(_json(value))
    unit = 'é😀\n\r\\"\x01'
    width = len(_json(unit)) - 2
    item["provenance"]["connection_provenance"]["fields"][0]["value"] = unit * (
        budget // width
    ) + "p" * (budget % width)
    raw = _json(value)
    assert len(raw) == size
    if stream:
        prefix = _follow.frame(_follow.started(sequence=10))
        suffix = _follow.frame(_follow.terminal(next_sequence=11, cutoff=11))
        d = _follow.Delivery(
            account_home,
            monkeypatch,
            chunks=[prefix, raw[:101], raw[101:] + b"\n", suffix],
        )
        args = ["--api-version", "2", *_follow._ARGS]
        want = prefix + raw + b"\n" + suffix
    else:
        prefix = b""
        d = _evidence.Delivery(
            account_home,
            monkeypatch,
            chunks=[raw[:101], raw[101:]],
            headers=[("Content-Type", "application/json"), ("Content-Length", "1")],
        )
        args = ["--api-version", "2", *_evidence._PAGE_ARGS]
        want = raw + b"\n"
    assert d.invoke(args) == (0 if size <= 1048576 else 5)
    if size <= 1048576:
        assert tuple(capsys.readouterr()) == (want.decode(), "")
    else:
        _follow.local(capsys.readouterr(), "invalid_response", prefix=prefix)
    assert len(d.wire.requests) == 1 and d.reads == ["credential"]
    assert all(t.closed for t in d.wire.transports)


@pytest.mark.parametrize(
    "command", [*[row[0] for row in _COMMANDS], _follow._ARGS[2:], _interact._ARGS[4:]]
)
@pytest.mark.parametrize("peer", ["old-service", "html", "redirect"])
def test_t021_unavailable_v2_on_old_service_never_probes_retries_or_downgrades(
    account_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
    peer: str,
) -> None:
    error = {"error": {"source": "request", "code": "route_not_found"}}
    status = 307 if peer == "redirect" else 404
    raw = ("<html>" + _PRIVATE + "</html>").encode() if peer == "html" else _json(error)
    d = _evidence.Delivery(
        account_home,
        monkeypatch,
        body=raw,
        status=status,
        headers=[
            ("Content-Type", "text/html" if peer == "html" else "application/json"),
            ("Location", "/v1/observation/status"),
        ],
    )
    assert d.invoke(["--api-version", "2", "--port", "8765", *command]) == (
        4 if peer == "old-service" else 5
    )
    if peer == "old-service":
        assert tuple(capsys.readouterr()) == ("", (_json(error) + b"\n").decode())
    else:
        _evidence._local(capsys.readouterr(), "invalid_response", phase="unknown")
    assert d.reads == ["credential"] and len(d.wire.requests) == 1 and d.imports == []
    assert d.wire.requests[0].url.raw_path.startswith(b"/v2/")
    assert all(t.closed for t in d.wire.transports)
