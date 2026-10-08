"""T007 RED tests for closed status projection and bounded request validation.

Pure internal helpers consume real immutable Core values and raw ASGI body
messages. No app, runtime/Acquisition instance, listener, persistence, auth bypass
or test implementation of the missing helpers is created.
"""

import importlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from itertools import product
from pathlib import Path
from typing import Any, cast

import pytest
from dutchmate_core.acquisition import (
    AcquisitionFailureKind,
    AcquisitionSnapshot,
    AcquisitionState,
    AcquisitionTerminalTrigger,
)
from dutchmate_core.adapters import basic_serial, observation_runtime, sqlite_evidence
from dutchmate_core.evidence import JournalFailureKind
from dutchmate_core.model import (
    BackendCapabilities,
    BackendCapability,
    BackendConnectionProvenance,
    BackendObservationTimestampDomain,
    ConnectionDescriptor,
    ConnectionInstanceId,
    ConnectionProvenanceSnapshot,
    ObserverReportsUartLoss,
    ProvenanceField,
    SegmentId,
    SegmentProvenance,
    SessionId,
    SessionPolicy,
    TimestampMeaning,
    TimestampObserver,
    TimestampUnit,
    UpstreamLossNotObservable,
)
from dutchmate_core.profile import (
    DutIdentity,
    ObservationPolicy,
    ProfileBackendSelection,
    ProfileFormatVersion,
    ProfileSerialOpenLineIntent,
    ProfileUartConfiguration,
    ResolvedDutProfile,
)
from dutchmate_core.runtime import (
    RunId,
    RuntimeIssue,
    RuntimeIssueSource,
    RuntimeState,
    RuntimeStatus,
    RuntimeStopIntent,
    RuntimeTerminalReason,
)
from starlette.responses import Response
from starlette.types import Message, Receive, Scope

type ValidationResult = tuple[str, str] | Response | None
_PROFILE_PATH = "/private/tmp/t007-profile.toml"
_JOURNAL_PATH = "/private/tmp/t007-journal.sqlite3"


def _helper(name: str) -> Callable[..., Any]:
    module = importlib.import_module("dutchmate_service.http")
    value = getattr(module, name, None)
    assert callable(value), f"T007 requires the planned {name} helper"
    return cast(Callable[..., Any], value)


def _response(status: RuntimeStatus, phase: str = "ready") -> Response:
    factory = cast(Callable[..., Response], _helper("status_response"))
    return factory(status, service_state=phase)


async def _validate(scope: Scope, receive: Receive) -> ValidationResult:
    validator = cast(
        Callable[[Scope, Receive], Awaitable[ValidationResult]],
        _helper("validate_request"),
    )
    return await validator(scope, receive)


def _document(response: Response) -> dict[str, Any]:
    assert response.headers["content-type"].split(";", 1)[0] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    payload = bytes(response.body)
    assert len(payload) <= 1048576
    result = json.loads(payload.decode("utf-8"))
    assert isinstance(result, dict)
    if "runtime" in result:
        assert set(result) == {"service_state", "runtime"}
        view = result["runtime"]
        assert set(view) == {
            "state",
            "run_id",
            "profile",
            "session_id",
            "acquisition",
            "stop_intent",
            "terminal_reason",
            "primary_issue",
            "cleanup_issues",
            "owner_settled",
            "physical_release_confirmed",
            "recorder_close_confirmed",
            "attach_admissible",
        }
        assert result["service_state"] in {"ready", "stopping"}
        assert (
            isinstance(view["cleanup_issues"], list)
            and len(view["cleanup_issues"]) <= 2
        )
        for issue in [view["primary_issue"], *view["cleanup_issues"]]:
            if issue is not None:
                assert set(issue) == {"source", "code"}
                assert type(issue["source"]) is str and type(issue["code"]) is str
        acquisition = view["acquisition"]
        if acquisition is not None:
            assert set(acquisition) == {
                "state",
                "descriptor",
                "provenance",
                "terminal_trigger",
                "primary_failure_kind",
                "close_failed",
                "physical_release_confirmed",
            }
            descriptor_keys = {
                "capabilities",
                "backend_observation_timestamp_domain",
                "loss_observability",
                "connection_provenance",
            }
            if acquisition["descriptor"] is not None:
                assert set(acquisition["descriptor"]) == descriptor_keys
            if acquisition["provenance"] is not None:
                assert set(acquisition["provenance"]) == descriptor_keys | {
                    "connection_id",
                    "segment_id",
                }
    return result


def _request_error(result: ValidationResult, status: int, code: str) -> Response:
    assert isinstance(result, Response)
    assert result.status_code == status
    assert _document(result) == {"error": {"source": "request", "code": code}}
    return result


def _profile(name: str = "Board α") -> ResolvedDutProfile:
    return ResolvedDutProfile(
        ProfileFormatVersion(1),
        DutIdentity("fixture/board", name),
        ProfileBackendSelection("basic_serial", "fixture-explicit-device"),
        ProfileUartConfiguration(57600, 7, "even", 2, True, False),
        ProfileSerialOpenLineIntent("deasserted", "driver_managed"),
        ObservationPolicy(),
        SessionPolicy(100, 65536, 8192, 128, 11, 16384),
    )


def _profile_view(name: str = "Board α") -> dict[str, Any]:
    # Literal contract fields, deliberately not dataclasses.asdict or service helpers.
    return {
        "format_version": 1,
        "dut": {"id": "fixture/board", "name": name},
        "backend": {
            "kind": "basic_serial",
            "expected_device": "fixture-explicit-device",
        },
        "uart": {
            "baud_rate": 57600,
            "data_bits": 7,
            "parity": "even",
            "stop_bits": 2,
            "hardware_flow_control": True,
            "software_flow_control": False,
        },
        "open_lines": {"dtr": "deasserted", "rts": "driver_managed"},
        "policy": {
            "uart_rx_enabled": True,
            "evidence_recording_enabled": True,
            "uart_tx_enabled": False,
            "semantic_control_enabled": False,
            "automatic_reconnect_enabled": False,
        },
        "session_policy": {
            "max_retained_records": 100,
            "max_retained_charged_bytes": 65536,
            "max_record_charged_bytes": 8192,
            "max_database_pages": 128,
            "max_retrieval_page_records": 11,
            "max_retrieval_page_charged_bytes": 16384,
        },
    }


@dataclass(frozen=True, slots=True)
class OpaqueProvenance(BackendConnectionProvenance):
    """Real normalized provenance contract with an unexposed private object."""

    envelope: ConnectionProvenanceSnapshot
    private_handle: object = field(default_factory=object, repr=False)

    def to_snapshot(self) -> ConnectionProvenanceSnapshot:
        return self.envelope

    def __str__(self) -> str:
        raise AssertionError(
            "provenance must use its generic snapshot, not stringification"
        )


def _descriptor(
    device: bool = False, kind: str = "unregistered-vendor"
) -> ConnectionDescriptor:
    return ConnectionDescriptor(
        BackendCapabilities(
            frozenset(
                {
                    BackendCapability.UART_SEND,
                    BackendCapability.SERIAL_LINE_CONTROL,
                    BackendCapability.UART_RECEIVE,
                }
            )
        ),
        BackendObservationTimestampDomain(
            "device-domain" if device else "host-domain",
            TimestampObserver.DEVICE if device else TimestampObserver.HOST,
            TimestampMeaning.OBSERVATION,
            TimestampUnit.TICK if device else TimestampUnit.NANOSECOND,
            "device-origin" if device else "host-origin",
        ),
        ObserverReportsUartLoss("observer-7", "receive-fifo")
        if device
        else UpstreamLossNotObservable(),
        OpaqueProvenance(
            ConnectionProvenanceSnapshot(
                1,
                kind,
                37,
                (
                    ProvenanceField("a_bool", True),
                    ProvenanceField("b_int", 7),
                    ProvenanceField("c_null", None),
                    ProvenanceField("d_text", "opaque-é\x00"),
                ),
            )
        ),
    )


def _descriptor_view(
    device: bool = False, kind: str = "unregistered-vendor"
) -> dict[str, Any]:
    return {
        "capabilities": ["serial_line_control", "uart_receive", "uart_send"],
        "backend_observation_timestamp_domain": {
            "domain_id": "device-domain" if device else "host-domain",
            "observer": "device" if device else "host",
            "meaning": "observation",
            "unit": "tick" if device else "nanosecond",
            "origin_id": "device-origin" if device else "host-origin",
        },
        "loss_observability": {
            "kind": "observer_reports_uart_loss",
            "observer_id": "observer-7",
            "scope": "receive-fifo",
        }
        if device
        else {"kind": "upstream_loss_not_observable"},
        "connection_provenance": {
            "envelope_version": 1,
            "backend_kind": kind,
            "backend_schema_version": 37,
            "fields": [
                {"name": "a_bool", "value": True},
                {"name": "b_int", "value": 7},
                {"name": "c_null", "value": None},
                {"name": "d_text", "value": "opaque-é\x00"},
            ],
        },
    }


def _provenance(descriptor: ConnectionDescriptor) -> SegmentProvenance:
    return SegmentProvenance(
        ConnectionInstanceId("connection-committed"),
        SegmentId("segment-committed"),
        descriptor.capabilities,
        descriptor.backend_observation_timestamp_domain,
        descriptor.loss_observability,
        descriptor.connection_provenance,
    )


def _status(
    state: RuntimeState = RuntimeState.ACTIVE,
    *,
    acquisition: AcquisitionSnapshot | None = None,
    primary: RuntimeIssue | None = None,
    cleanup: tuple[RuntimeIssue, ...] = (),
    physical: bool = False,
    recorder: bool = False,
    reason: RuntimeTerminalReason | None = None,
    intent: RuntimeStopIntent = RuntimeStopIntent.NONE,
    profile: ResolvedDutProfile | None = None,
) -> RuntimeStatus:
    return RuntimeStatus(
        state=state,
        run_id=RunId("run-fixture"),
        profile=profile or _profile(),
        session_id=SessionId("session-fixture"),
        acquisition=acquisition,
        stop_intent=intent,
        terminal_reason=reason,
        primary_issue=primary,
        cleanup_issues=cleanup,
        owner_settled=state in {RuntimeState.TERMINATED, RuntimeState.FAILED},
        physical_release_confirmed=physical,
        recorder_close_confirmed=recorder,
    )


@pytest.fixture(autouse=True)
def forbid_file_and_run_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> Any:
        del args, kwargs
        pytest.fail(
            "T007 pure projection/validation must not access files or run resources"
        )

    monkeypatch.setattr(observation_runtime, "resolve_profile", forbidden)
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "create", forbidden)
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "open", forbidden)
    monkeypatch.setattr(basic_serial.BasicSerialBackend, "__init__", forbidden)
    monkeypatch.setattr(basic_serial.BasicSerialBackend, "open", forbidden)
    # Importlib uses its own low-level loader; these tripwires target helper filesystem work.
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "stat", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)


@pytest.mark.parametrize("phase", ["ready", "stopping"])
def test_inactive_projection_has_exact_closed_fields_and_null_unknowns(
    phase: str,
) -> None:
    response = _response(RuntimeStatus(), phase)
    assert response.status_code == 200
    assert _document(response) == {
        "service_state": phase,
        "runtime": {
            "state": "inactive",
            "run_id": None,
            "profile": None,
            "session_id": None,
            "acquisition": None,
            "stop_intent": "none",
            "terminal_reason": None,
            "primary_issue": None,
            "cleanup_issues": [],
            "owner_settled": True,
            "physical_release_confirmed": True,
            "recorder_close_confirmed": True,
            "attach_admissible": True,
        },
    }


@pytest.mark.parametrize("state", [RuntimeState.ATTACHING, RuntimeState.DETACHING])
def test_unsettled_states_do_not_claim_admission_or_terminal_reason(
    state: RuntimeState,
) -> None:
    status = _status(
        state,
        physical=True,
        intent=RuntimeStopIntent.DETACH
        if state is RuntimeState.DETACHING
        else RuntimeStopIntent.NONE,
    )
    response = _response(status)
    actual = _document(response)["runtime"]
    assert actual == {
        "state": state.value,
        "run_id": "run-fixture",
        "profile": _profile_view(),
        "session_id": "session-fixture",
        "acquisition": None,
        "stop_intent": "detach" if state is RuntimeState.DETACHING else "none",
        "terminal_reason": None,
        "primary_issue": None,
        "cleanup_issues": [],
        "owner_settled": False,
        "physical_release_confirmed": True,
        "recorder_close_confirmed": False,
        "attach_admissible": False,
    }


@pytest.mark.parametrize(
    "device", [False, True], ids=["host-unobservable", "device-scoped"]
)
@pytest.mark.parametrize(
    "kind", ["basic_serial", "enhanced-shaped", "unregistered-vendor"]
)
def test_generic_descriptor_and_committed_provenance_have_no_backend_registry_or_private_fields(
    device: bool,
    kind: str,
) -> None:
    descriptor = _descriptor(device, kind)
    snapshot = AcquisitionSnapshot(
        AcquisitionState.ACQUIRING,
        descriptor,
        _provenance(descriptor),
        physical_release_confirmed=False,
    )
    response = _response(_status(acquisition=snapshot))
    runtime = _document(response)["runtime"]
    expected_descriptor = _descriptor_view(device, kind)
    assert runtime["profile"] == _profile_view()
    assert runtime["acquisition"] == {
        "state": "acquiring",
        "descriptor": expected_descriptor,
        "provenance": {
            "connection_id": "connection-committed",
            "segment_id": "segment-committed",
            **expected_descriptor,
        },
        "terminal_trigger": None,
        "primary_failure_kind": None,
        "close_failed": False,
        "physical_release_confirmed": False,
    }
    assert response.status_code == 200
    assert b"private_handle" not in bytes(response.body)
    assert b"OpaqueProvenance" not in bytes(response.body)


def test_returned_descriptor_without_commit_cannot_invent_connection_or_segment_ids() -> (
    None
):
    descriptor = _descriptor()
    snapshot = AcquisitionSnapshot(
        AcquisitionState.STARTING,
        descriptor=descriptor,
        physical_release_confirmed=False,
    )
    status = replace(
        _status(RuntimeState.ATTACHING, acquisition=snapshot), session_id=None
    )
    runtime = _document(_response(status))["runtime"]
    assert runtime["session_id"] is None
    assert runtime["acquisition"]["descriptor"] == _descriptor_view()
    assert runtime["acquisition"]["provenance"] is None
    assert b"connection-committed" not in bytes(_response(status).body)
    assert b"segment-committed" not in bytes(_response(status).body)


def test_terminal_provenance_remains_historical_with_exact_closed_acquisition_fields() -> (
    None
):
    descriptor = _descriptor(True)
    snapshot = AcquisitionSnapshot(
        AcquisitionState.STOPPED,
        descriptor,
        _provenance(descriptor),
        AcquisitionTerminalTrigger.DISCONNECTED,
        physical_release_confirmed=True,
    )
    status = _status(
        RuntimeState.TERMINATED,
        acquisition=snapshot,
        physical=True,
        recorder=True,
        reason=RuntimeTerminalReason.DISCONNECTED,
    )
    response = _response(status)
    runtime = _document(response)["runtime"]
    assert response.status_code == 200 and runtime["state"] == "terminated"
    assert runtime["terminal_reason"] == "disconnected" and runtime["attach_admissible"]
    assert runtime["acquisition"] == {
        "state": "stopped",
        "descriptor": _descriptor_view(True),
        "provenance": {
            "connection_id": "connection-committed",
            "segment_id": "segment-committed",
            **_descriptor_view(True),
        },
        "terminal_trigger": "disconnected",
        "primary_failure_kind": None,
        "close_failed": False,
        "physical_release_confirmed": True,
    }


@pytest.mark.parametrize(
    "primary_kind",
    [
        None,
        AcquisitionFailureKind.RECORDING_FAILURE,
        AcquisitionFailureKind.TRANSPORT_FAILURE,
    ],
)
@pytest.mark.parametrize("close_failed", [False, True])
def test_trigger_primary_and_close_failures_project_independently(
    primary_kind: AcquisitionFailureKind | None,
    close_failed: bool,
) -> None:
    descriptor = _descriptor()
    issue = (
        None
        if primary_kind is None
        else RuntimeIssue(RuntimeIssueSource.ACQUISITION, primary_kind)
    )
    cleanup = (
        (RuntimeIssue(RuntimeIssueSource.BACKEND_CLOSE, "close_failed"),)
        if close_failed
        else ()
    )
    snapshot = AcquisitionSnapshot(
        AcquisitionState.FAILED if issue or cleanup else AcquisitionState.STOPPED,
        descriptor,
        _provenance(descriptor),
        AcquisitionTerminalTrigger.DISCONNECTED,
        primary_kind,
        close_failed,
        not close_failed,
    )
    status = _status(
        RuntimeState.FAILED if issue or cleanup else RuntimeState.TERMINATED,
        acquisition=snapshot,
        primary=issue,
        cleanup=cleanup,
        physical=not close_failed,
        recorder=True,
        reason=RuntimeTerminalReason.DISCONNECTED,
    )
    response = _response(status)
    runtime = _document(response)["runtime"]
    assert (
        response.status_code == 200
    )  # Failed facts are still a completed HTTP exchange.
    assert runtime["terminal_reason"] == "disconnected"
    assert runtime["primary_issue"] == (
        None
        if primary_kind is None
        else {"source": "acquisition", "code": primary_kind.value}
    )
    assert runtime["cleanup_issues"] == (
        [{"source": "backend_close", "code": "close_failed"}] if close_failed else []
    )
    assert runtime["acquisition"]["primary_failure_kind"] == (
        None if primary_kind is None else primary_kind.value
    )
    assert runtime["acquisition"]["close_failed"] is close_failed
    assert runtime["physical_release_confirmed"] is not close_failed


@pytest.mark.parametrize(
    ("physical", "recorder"), list(product([False, True], repeat=2))
)
def test_failed_status_keeps_exact_derived_admissibility_despite_http_200(
    physical: bool,
    recorder: bool,
) -> None:
    issue = RuntimeIssue(RuntimeIssueSource.PREPARATION, JournalFailureKind.IO_FAILURE)
    status = _status(
        RuntimeState.FAILED,
        primary=issue,
        physical=physical,
        recorder=recorder,
        reason=RuntimeTerminalReason.STARTUP_FAILURE,
    )
    response = _response(status)
    actual = _document(response)["runtime"]
    assert response.status_code == 200
    assert actual["state"] == "failed" and actual["owner_settled"]
    assert actual["physical_release_confirmed"] is physical
    assert actual["recorder_close_confirmed"] is recorder
    assert actual["attach_admissible"] is (physical and recorder)
    assert actual["primary_issue"] == {"source": "preparation", "code": "io_failure"}


def test_first_primary_and_ordered_two_cleanup_facts_have_no_raw_diagnostic_fields() -> (
    None
):
    status = _status(
        RuntimeState.FAILED,
        primary=RuntimeIssue(
            RuntimeIssueSource.ACQUISITION_START,
            AcquisitionFailureKind.CAPABILITY_REJECTION,
        ),
        cleanup=(
            RuntimeIssue(RuntimeIssueSource.BACKEND_CLOSE, "close_failed"),
            RuntimeIssue(
                RuntimeIssueSource.RECORDER_CLOSE, JournalFailureKind.IO_FAILURE
            ),
        ),
        reason=RuntimeTerminalReason.STARTUP_FAILURE,
        intent=RuntimeStopIntent.ATTACH_CANCELLED,
    )
    actual = _document(_response(status))["runtime"]
    assert actual["stop_intent"] == "attach_cancelled"
    assert actual["terminal_reason"] == "startup_failure"
    assert actual["primary_issue"] == {
        "source": "acquisition_start",
        "code": "capability_rejection",
    }
    assert actual["cleanup_issues"] == [
        {"source": "backend_close", "code": "close_failed"},
        {"source": "recorder_close", "code": "io_failure"},
    ]


@pytest.mark.parametrize("name", ["Board α\x00\n", "é" * 100000])
def test_unicode_and_controls_round_trip_without_lossy_status_projection(
    name: str,
) -> None:
    status = _status(RuntimeState.ATTACHING, profile=_profile(name), physical=True)
    response = _response(status)
    assert response.status_code == 200
    assert _document(response)["runtime"]["profile"] == _profile_view(name)


def test_response_exact_one_mib_limit_and_one_more_byte_fail_without_truncating_or_mutating() -> (
    None
):
    base = _status(RuntimeState.ATTACHING, profile=_profile("x"), physical=True)
    response = _response(base)
    assert response.status_code == 200
    # Calibrate only serializer whitespace overhead, which the contract leaves free.
    # ASCII string growth is exact; the expected bound itself is the literal1MiB.
    count = 1048576 - len(bytes(response.body)) + 1
    assert count > 0
    at_bound = replace(base, profile=_profile("x" * count))
    accepted = _response(at_bound)
    assert accepted.status_code == 200 and len(bytes(accepted.body)) == 1048576
    assert _document(accepted)["runtime"]["profile"]["dut"]["name"] == "x" * count
    too_large = replace(base, profile=_profile("x" * (count + 1)))
    rejected = _response(too_large)
    assert rejected.status_code == 500
    assert _document(rejected) == {
        "error": {"source": "service", "code": "internal_failure"}
    }
    assert too_large.profile is not None
    assert too_large.profile.dut.name == "x" * (count + 1)
    assert too_large.state is RuntimeState.ATTACHING and not too_large.attach_admissible


@pytest.mark.parametrize("name", ["x" * 2097152, "é" * 1048576])
def test_oversized_status_never_returns_silently_partial_profile(
    name: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    status = _status(RuntimeState.ATTACHING, profile=_profile(name), physical=True)
    with caplog.at_level(logging.DEBUG):
        response = _response(status)
    assert response.status_code == 500
    assert _document(response) == {
        "error": {"source": "service", "code": "internal_failure"}
    }
    assert "Board" not in caplog.text and len(caplog.text.encode()) < 4096


@dataclass
class Body:
    chunks: tuple[bytes, ...]
    calls: int = 0
    received: int = 0
    stop_after: int | None = None

    async def receive(self) -> Message:
        if self.stop_after is not None and self.calls >= self.stop_after:
            pytest.fail("bounded validator requested bytes after limit+1")
        if self.calls >= len(self.chunks):
            pytest.fail("validator read again after final body frame")
        chunk = self.chunks[self.calls]
        self.calls += 1
        self.received += len(chunk)
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": self.calls < len(self.chunks),
        }


def _scope(
    path: str = "/v1/observation/attach",
    method: str = "POST",
    media: list[tuple[bytes, bytes]] | None = None,
) -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "scheme": "http",
        "method": method,
        "root_path": "",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")] if media is None else media,
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8765),
        "state": {},
    }


def _body(profile: object = _PROFILE_PATH, journal: object = _JOURNAL_PATH) -> bytes:
    return json.dumps(
        {"profile_path": profile, "journal_path": journal},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


@pytest.mark.parametrize(
    "media",
    [
        [(b"content-type", b"application/json")],
        [(b"Content-Type", b"APPLICATION/JSON")],
        [(b"content-type", b"application/json; charset=utf-8")],
        [(b"CONTENT-TYPE", b"application/json;charset=UTF-8")],
    ],
)
@pytest.mark.asyncio
async def test_valid_attach_preserves_explicit_paths_without_opening_resources(
    media: list[tuple[bytes, bytes]],
) -> None:
    source = Body((_body(),))
    result = await _validate(_scope(media=media), source.receive)
    assert result == (_PROFILE_PATH, _JOURNAL_PATH)
    assert source.calls == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_path", "/"),
        ("journal_path", "/"),
        ("profile_path", "/private/tmp/a/../literal "),
        ("journal_path", "/private/tmp/~/literal"),
        ("profile_path", "/private/tmp/${DUTCHMATE_T007}/profile.toml"),
    ],
)
@pytest.mark.asyncio
async def test_absolute_paths_are_not_stripped_expanded_or_resolved(
    field: str,
    value: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DUTCHMATE_T007", "must-not-expand")
    p = value if field == "profile_path" else _PROFILE_PATH
    j = value if field == "journal_path" else _JOURNAL_PATH
    assert await _validate(_scope(), Body((_body(p, j),)).receive) == (p, j)


@pytest.mark.parametrize("field", ["profile_path", "journal_path"])
@pytest.mark.parametrize("value", ["/" + "a" * 4095, "/" + "é" * 2047 + "a"])
@pytest.mark.asyncio
async def test_path_limit_counts_actual_utf8_bytes_and_accepts_4096(
    field: str,
    value: str,
) -> None:
    assert len(value.encode("utf-8")) == 4096
    p = value if field == "profile_path" else _PROFILE_PATH
    j = value if field == "journal_path" else _JOURNAL_PATH
    assert await _validate(_scope(), Body((_body(p, j),)).receive) == (p, j)


@pytest.mark.parametrize("field", ["profile_path", "journal_path"])
@pytest.mark.parametrize("value", ["/" + "a" * 4096, "/" + "é" * 2048])
@pytest.mark.asyncio
async def test_one_more_utf8_path_byte_rejects_without_coercion(
    field: str, value: str
) -> None:
    assert len(value.encode("utf-8")) == 4097
    p = value if field == "profile_path" else _PROFILE_PATH
    j = value if field == "journal_path" else _JOURNAL_PATH
    _request_error(
        await _validate(_scope(), Body((_body(p, j),)).receive), 422, "invalid_request"
    )


@pytest.mark.parametrize("field", ["profile_path", "journal_path"])
@pytest.mark.parametrize(
    "value",
    [
        "",
        "relative.toml",
        "~/.profile",
        " /absolute",
        "/private/tmp/nul\x00file",
        None,
        True,
        42,
        1.5,
        [],
        {},
    ],
)
@pytest.mark.asyncio
async def test_invalid_paths_reject_types_defaults_nul_and_relative_values(
    field: str,
    value: object,
) -> None:
    p = value if field == "profile_path" else _PROFILE_PATH
    j = value if field == "journal_path" else _JOURNAL_PATH
    _request_error(
        await _validate(_scope(), Body((_body(p, j),)).receive), 422, "invalid_request"
    )


_BAD_JSON = [
    b"",
    b"\xff",
    b"{",
    b"[]",
    b"null",
    b"true",
    b"42",
    b'"text"',
    b"{}",
    b'{"profile_path":"/a"}',
    b'{"journal_path":"/b"}',
    b'{"profile_path":"/a","journal_path":"/b","secret":"private-input-t007"}',
    b'{"profile_path":"/a","profile_path":"/a","journal_path":"/b"}',
    b'{"profile_path":"/a","journal_path":"/b","journal_path":"/b"}',
    b'{"profile_path":"/a","profile_\\u0070ath":"/a","journal_path":"/b"}',
    b'{"profile_path":NaN,"journal_path":"/b"}',
    b'{"profile_path":"/a","journal_path":Infinity}',
    b'{"profile_path":"/a","journal_path":-Infinity}',
    b'{"profile_path":"/a","journal_path":"/b"} trailing',
    b'{"profile_path":"/private/tmp/\\ud800","journal_path":"/b"}',
    b'{"profile_path":"/a","journal_path":"/private/tmp/\\udfff"}',
]


@pytest.mark.parametrize("payload", _BAD_JSON)
@pytest.mark.asyncio
async def test_strict_json_is_closed_and_errors_never_echo_input(
    payload: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        response = _request_error(
            await _validate(_scope(), Body((payload,)).receive), 422, "invalid_request"
        )
    assert b"private-input-t007" not in bytes(response.body)
    assert "private-input-t007" not in caplog.text
    assert "Traceback" not in bytes(response.body).decode("utf-8")


@pytest.mark.parametrize(
    "media",
    [
        [],
        [(b"content-type", b"")],
        [(b"content-type", b"text/plain")],
        [(b"content-type", b"application/problem+json")],
        [(b"content-type", b"application/json; charset=latin-1")],
        [(b"content-type", b"application/json; boundary=anything")],
        [(b"content-type", b"application/json; charset=utf-8; charset=utf-8")],
        [
            (b"content-type", b"application/json"),
            (b"Content-Type", b"application/json"),
        ],
        [(b"content-type", b"\xff")],
    ],
)
@pytest.mark.asyncio
async def test_media_requirement_rejects_missing_duplicate_or_unsupported_values(
    media: list[tuple[bytes, bytes]],
) -> None:
    _request_error(
        await _validate(_scope(media=media), Body((_body(),)).receive),
        415,
        "unsupported_media_type",
    )


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.asyncio
async def test_actual_body_limit_accepts_16384_bytes_including_json_whitespace(
    split: bool,
) -> None:
    payload = _body()
    payload += b" " * (16384 - len(payload))
    chunks = (payload[:8192], payload[8192:]) if split else (payload,)
    body = Body(chunks)
    assert await _validate(_scope(), body.receive) == (_PROFILE_PATH, _JOURNAL_PATH)
    assert body.received == 16384 and body.calls == len(chunks)


@pytest.mark.asyncio
async def test_byte_16385_rejects_before_decoder_or_another_receive() -> None:
    payload = _body()
    payload += b" " * (16384 - len(payload))
    body = Body((payload, b" ", b"must-not-be-read"), stop_after=2)
    result = await _validate(
        _scope(
            media=[(b"content-type", b"application/json"), (b"content-length", b"1")]
        ),
        body.receive,
    )
    _request_error(result, 413, "payload_too_large")
    assert body.received == 16385 and body.calls == 2


@pytest.mark.asyncio
async def test_oversized_single_asgi_frame_rejects_without_followup_receive() -> None:
    body = Body((b"x" * 65536, b"must-not-be-read"), stop_after=1)
    result = await _validate(_scope(), body.receive)
    _request_error(result, 413, "payload_too_large")
    assert body.calls == 1


@pytest.mark.parametrize(
    ("path", "method"),
    [("/v1/observation/status", "GET"), ("/v1/observation/detach", "POST")],
)
@pytest.mark.asyncio
async def test_status_and_detach_accept_only_zero_body(path: str, method: str) -> None:
    body = Body((b"",))
    assert await _validate(_scope(path, method, media=[]), body.receive) is None
    assert body.calls == 1


@pytest.mark.parametrize(
    ("path", "method"),
    [("/v1/observation/status", "GET"), ("/v1/observation/detach", "POST")],
)
@pytest.mark.parametrize("payload", [b" ", b"{}", b"x", b"\x00"])
@pytest.mark.asyncio
async def test_status_and_detach_nonzero_body_fail_with_input_free_envelope(
    path: str,
    method: str,
    payload: bytes,
) -> None:
    _request_error(
        await _validate(_scope(path, method), Body((payload,)).receive),
        422,
        "invalid_request",
    )
