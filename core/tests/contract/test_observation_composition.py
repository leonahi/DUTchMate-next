"""RED contracts for the explicit Profile/SQLite/Basic composition edge.

The admission probe captures the edge's handoff only; it implements no run
ownership or Acquisition lifecycle. T006 separately tests that lifecycle.
Preparation uses real adapters with the existing private fake serial seam.
"""

import asyncio
import importlib
import importlib.util
import os
import threading
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO, NoReturn, Protocol, cast

import pytest
import serial

from dutchmate_core import acquisition, evidence, model, profile
from dutchmate_core import runtime as rt
from dutchmate_core.adapters import basic_serial, sqlite_evidence
from dutchmate_core.backend import (
    BackendFailureKind,
    BackendFailureOperation,
    NormalizedBackendFailure,
)
from tests.contract.test_basic_serial_adapter import FakeSerial, FakeSerialFactory

_EDGE_MODULE = "dutchmate_core.adapters.observation_runtime"
_MISSING_EDGE = "Basic observation composition is not implemented (T009)"
_PROFILE = """profile_version = 1
[dut]
id = "fixture/observation"
name = "Observation fixture"
[backend]
kind = "basic_serial"
expected_device = "/dev/fixture-only"
[uart]
baud_rate = 19200
data_bits = 7
parity = "even"
stop_bits = 2
hardware_flow_control = false
software_flow_control = true
[uart.open_lines]
dtr = "deasserted"
rts = "deasserted"
[persistence]
max_retained_records = 100
max_retained_charged_bytes = 65536
max_record_charged_bytes = 8192
max_database_pages = 128
max_retrieval_page_records = 11
max_retrieval_page_charged_bytes = 16384
"""


class AdmissionPort(Protocol):
    def status(self) -> rt.RuntimeStatus: ...

    async def attach(
        self, resolved: profile.ResolvedDutProfile, prepare: rt.PrepareObservationRun
    ) -> rt.RuntimeStatus: ...


type Edge = Callable[
    [AdmissionPort, str | Path, str | Path], Awaitable[rt.RuntimeStatus]
]


def _edge() -> Edge:
    assert importlib.util.find_spec(_EDGE_MODULE) is not None, _MISSING_EDGE
    module = importlib.import_module(_EDGE_MODULE)
    entry = getattr(module, "attach_basic_observation", None)
    assert callable(entry), _MISSING_EDGE
    return cast("Edge", entry)


class AdmissionProbe:
    """Only record guard/admission inputs, without preparing or owning a run."""

    def __init__(
        self,
        trace: list[str],
        *,
        reported: rt.RuntimeStatus | None = None,
        guard_error: rt.RuntimeRejectedKind | None = None,
        admission_error: rt.RuntimeRejectedKind | None = None,
    ) -> None:
        self.trace = trace
        self.reported = rt.RuntimeStatus() if reported is None else reported
        self.guard_error = guard_error
        self.admission_error = admission_error
        self.resolved: profile.ResolvedDutProfile | None = None
        self.prepare: rt.PrepareObservationRun | None = None

    def status(self) -> rt.RuntimeStatus:
        self.trace.append("context_guard")
        if self.guard_error is not None:
            raise rt.RuntimeRejectedError(self.guard_error)
        return self.reported

    async def attach(
        self, resolved: profile.ResolvedDutProfile, prepare: rt.PrepareObservationRun
    ) -> rt.RuntimeStatus:
        self.trace.append("admission")
        self.resolved = resolved
        self.prepare = prepare
        if self.admission_error is not None:
            raise rt.RuntimeRejectedError(self.admission_error)
        return self.reported

    async def captured_preparation(self) -> rt.PreparedObservationRun:
        assert self.resolved is not None and self.prepare is not None
        return await self.prepare(self.resolved)


class ProfileRead:
    def __init__(self, stream: BinaryIO, trace: list[str], sizes: list[int]) -> None:
        self.stream = stream
        self.trace = trace
        self.sizes = sizes

    def __enter__(self) -> ProfileRead:
        self.stream.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self.stream.close()

    def read(self, size: int = -1) -> bytes:
        self.trace.append("profile_read")
        self.sizes.append(size)
        return self.stream.read(size)


def _track_profile_read(
    monkeypatch: pytest.MonkeyPatch, selected: Path, trace: list[str]
) -> list[int]:
    original = cast("Callable[..., BinaryIO]", Path.open)
    sizes: list[int] = []

    def tracked(path: Path, mode: str = "r", *args: object, **kwargs: object) -> object:
        stream = original(path, mode, *args, **kwargs)
        if path == selected and "r" in mode:
            assert mode == "rb", "composition must use the bounded binary resolver"
            return ProfileRead(stream, trace, sizes)
        return stream

    monkeypatch.setattr(Path, "open", tracked)
    return sizes


def _forbidden(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    pytest.fail("rejected edge must not prepare resources or inspect hardware")


@pytest.fixture(autouse=True)
def block_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    # conftest's physical serial factory sentinel stays intact in every test.
    monkeypatch.setattr("serial.tools.list_ports.comports", _forbidden)
    monkeypatch.setattr(serial, "serial_for_url", _forbidden)


def _block_preparation(monkeypatch: pytest.MonkeyPatch, destination: Path) -> None:
    for target, name in (
        (sqlite_evidence.SqliteEvidenceJournal, "create"),
        (sqlite_evidence.SqliteEvidenceJournal, "open"),
        (basic_serial.BasicSerialBackend, "__init__"),
        (basic_serial.BasicSerialBackend, "open"),
        (acquisition.Acquisition, "__init__"),
    ):
        monkeypatch.setattr(target, name, _forbidden)
    original_stat = Path.stat

    def stat(path: Path, *, follow_symlinks: bool = True) -> object:
        if path == destination:
            _forbidden()
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", stat)


def _selected(tmp_path: Path, contents: str = _PROFILE) -> Path:
    selected = tmp_path / "explicit-profile.toml"
    selected.write_text(contents, encoding="utf-8")
    return selected


def _busy_status(state: rt.RuntimeState) -> rt.RuntimeStatus:
    # The outer edge must not use these facts to reject before resolving.
    # Avoid another file/read just to build the immutable status fixture.
    resolved = profile.ResolvedDutProfile(
        format_version=profile.ProfileFormatVersion(1),
        dut=profile.DutIdentity("existing/run", "Existing run"),
        backend=profile.ProfileBackendSelection(
            "basic_serial", "/dev/fixture-existing"
        ),
        uart=profile.ProfileUartConfiguration(19200, 7, "even", 2, False, True),
        open_lines=profile.ProfileSerialOpenLineIntent("deasserted", "deasserted"),
        policy=profile.ObservationPolicy(),
        session_policy=_expected_policy(),
    )
    return rt.RuntimeStatus(
        state=state,
        run_id=rt.RunId(),
        profile=resolved,
        owner_settled=False,
        recorder_close_confirmed=False,
    )


def _expected_policy() -> model.SessionPolicy:
    return model.SessionPolicy(100, 65536, 8192, 128, 11, 16384)


class CloseGatedSerial(FakeSerial):
    def __init__(self) -> None:
        self.read_gate = threading.Event()
        super().__init__(read_results=(b"",), read_gates=(self.read_gate,))

    def cancel_read(self) -> None:
        super().cancel_read()
        self.read_gate.set()


def _inject_fake_basic(
    monkeypatch: pytest.MonkeyPatch, destination: Path, trace: list[str]
) -> tuple[FakeSerial, FakeSerialFactory, list[sqlite_evidence.SqliteEvidenceJournal]]:
    fake = CloseGatedSerial()
    factory = FakeSerialFactory(fake)
    created: list[sqlite_evidence.SqliteEvidenceJournal] = []
    original_create = sqlite_evidence.SqliteEvidenceJournal.create
    original_init = basic_serial.BasicSerialBackend.__init__
    original_open = basic_serial.BasicSerialBackend.open

    async def create(
        cls: type[sqlite_evidence.SqliteEvidenceJournal],
        path: str | Path,
        policy: model.SessionPolicy,
    ) -> sqlite_evidence.SqliteEvidenceJournal:
        del cls
        assert Path(path) == destination
        assert policy == _expected_policy()
        trace.append("journal_create")
        journal = await original_create(path, policy)
        created.append(journal)
        trace.append("journal_created")
        return journal

    def construct(
        self: basic_serial.BasicSerialBackend,
        selector: basic_serial.SerialDeviceSelector,
        configuration: basic_serial.SerialConfiguration,
        line_intent: basic_serial.SerialOpenLineIntent,
    ) -> None:
        assert len(created) == 1 and destination.is_file()
        assert not factory.calls
        trace.append("backend_constructed")
        original_init(
            self, selector, configuration, line_intent, _serial_factory=factory
        )

    async def open_backend(self: basic_serial.BasicSerialBackend) -> object:
        assert len(created) == 1 and destination.is_file()
        trace.append("backend_open")
        return await original_open(self)

    monkeypatch.setattr(
        sqlite_evidence.SqliteEvidenceJournal, "create", classmethod(create)
    )
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "open", _forbidden)
    monkeypatch.setattr(basic_serial.BasicSerialBackend, "__init__", construct)
    monkeypatch.setattr(basic_serial.BasicSerialBackend, "open", open_backend)
    return fake, factory, created


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "contents",
    [_PROFILE, "invalid TOML", _PROFILE + "#" * 65537],
    ids=["valid", "invalid", "oversized"],
)
async def test_context_guard_precedes_profile_io_and_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str
) -> None:
    edge = _edge()
    selected = _selected(tmp_path, contents)
    destination = tmp_path / "unused.sqlite3"
    trace: list[str] = []
    probe = AdmissionProbe(
        trace, guard_error=rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT
    )
    sizes = _track_profile_read(monkeypatch, selected, trace)
    tasks = asyncio.all_tasks()
    with monkeypatch.context() as guard:
        _block_preparation(guard, destination)
        guard.setattr(Path, "stat", _forbidden)
        with pytest.raises(rt.RuntimeRejectedError) as caught:
            await edge(probe, selected, destination)
    assert caught.value.kind is rt.RuntimeRejectedKind.WRONG_EXECUTION_CONTEXT
    assert trace == ["context_guard"] and sizes == []
    assert probe.resolved is None and probe.prepare is None
    assert asyncio.all_tasks() == tasks
    assert not destination.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("as_text", [False, True], ids=["paths", "strings"])
@pytest.mark.parametrize(
    "state",
    [rt.RuntimeState.ATTACHING, rt.RuntimeState.ACTIVE, rt.RuntimeState.DETACHING],
)
async def test_busy_edge_resolves_profile_before_runtime_rejection_without_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: rt.RuntimeState,
    as_text: bool,
) -> None:
    edge = _edge()
    selected = _selected(tmp_path)
    destination = tmp_path / "unused.sqlite3"
    trace: list[str] = []
    reported = _busy_status(state)
    probe = AdmissionProbe(
        trace, reported=reported, admission_error=rt.RuntimeRejectedKind.BUSY
    )
    sizes = _track_profile_read(monkeypatch, selected, trace)
    with monkeypatch.context() as guard:
        _block_preparation(guard, destination)
        with pytest.raises(rt.RuntimeRejectedError) as caught:
            await edge(
                probe,
                str(selected) if as_text else selected,
                str(destination) if as_text else destination,
            )
    assert caught.value.kind is rt.RuntimeRejectedKind.BUSY
    assert trace == ["context_guard", "profile_read", "admission"]
    assert sizes == [65537]
    assert probe.resolved is not None and probe.resolved.dut.id == "fixture/observation"
    assert probe.reported is reported
    assert not destination.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("contents", "kind", "sizes"),
    [
        ("invalid TOML", profile.ProfileFailureKind.INVALID_SYNTAX, [65537]),
        (
            _PROFILE + "\n[policy]\nuart_tx_enabled = true\n",
            profile.ProfileFailureKind.UNSUPPORTED_BEHAVIOR,
            [65537],
        ),
        (_PROFILE + "#" * 65537, profile.ProfileFailureKind.INPUT_TOO_LARGE, [65537]),
        (None, profile.ProfileFailureKind.MISSING_FILE, []),
    ],
    ids=["invalid-syntax", "unsupported-tx", "oversized", "missing"],
)
async def test_invalid_profile_can_fail_before_busy_without_admission_or_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contents: str | None,
    kind: profile.ProfileFailureKind,
    sizes: list[int],
) -> None:
    edge = _edge()
    selected = _selected(tmp_path, contents or _PROFILE)
    if contents is None:
        selected.unlink()
    destination = tmp_path / "unused.sqlite3"
    trace: list[str] = []
    probe = AdmissionProbe(
        trace,
        reported=_busy_status(rt.RuntimeState.ACTIVE),
        admission_error=rt.RuntimeRejectedKind.BUSY,
    )
    read_sizes = _track_profile_read(monkeypatch, selected, trace)
    with monkeypatch.context() as guard:
        _block_preparation(guard, destination)
        with pytest.raises(profile.ProfileFailure) as caught:
            await edge(probe, selected, destination)
    assert caught.value.kind is kind
    assert trace == (["context_guard", "profile_read"] if sizes else ["context_guard"])
    assert read_sizes == sizes
    assert probe.resolved is None and probe.prepare is None
    assert not destination.exists()


@pytest.mark.asyncio
async def test_edge_hands_off_resolved_value_and_unsubmitted_closure_before_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edge = _edge()
    selected = _selected(tmp_path)
    destination = tmp_path / "explicit.sqlite3"
    trace: list[str] = []
    probe = AdmissionProbe(trace)
    _track_profile_read(monkeypatch, selected, trace)
    with monkeypatch.context() as guard:
        _block_preparation(guard, destination)
        result = await edge(probe, selected, destination)
    assert result is probe.reported
    assert trace == ["context_guard", "profile_read", "admission"]
    assert isinstance(probe.resolved, profile.ResolvedDutProfile)
    assert callable(probe.prepare)
    assert not destination.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("as_text", [False, True], ids=["paths", "strings"])
async def test_preparation_creates_exact_journal_policy_then_unopened_basic_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_text: bool
) -> None:
    edge = _edge()
    selected = _selected(tmp_path)
    destination = tmp_path / "explicit.sqlite3"
    trace: list[str] = []
    probe = AdmissionProbe(trace)
    fake, factory, created = _inject_fake_basic(monkeypatch, destination, trace)
    _track_profile_read(monkeypatch, selected, trace)
    await edge(
        probe,
        str(selected) if as_text else selected,
        str(destination) if as_text else destination,
    )
    assert not destination.exists() and not created and not factory.calls
    prepared = await probe.captured_preparation()
    try:
        assert prepared.recorder is created[0]
        assert prepared.recorder.policy == _expected_policy()
        assert probe.resolved is not None
        assert prepared.recorder.policy == probe.resolved.session_policy
        assert prepared.recorder.session_id == created[0].session_id
        assert trace == [
            "context_guard",
            "profile_read",
            "admission",
            "journal_create",
            "journal_created",
            "backend_constructed",
        ]
        assert factory.calls == [] and not fake.is_open and fake.read_calls == 0
        # The actual adapter proves that all intended Profile values reached it.
        connection = await prepared.backend.open()
        try:
            assert factory.calls == [{"port": None}]
            assert (
                fake.port,
                fake.baudrate,
                fake.bytesize,
                fake.parity,
                fake.stopbits,
            ) == ("/dev/fixture-only", 19200, 7, "E", 2)
            assert (fake.rtscts, fake.xonxoff, fake.dtr, fake.rts) == (
                False,
                True,
                False,
                False,
            )
            assert fake.read_calls == 0
        finally:
            await connection.close()
    finally:
        await prepared.recorder.close()
    assert destination.is_file() and fake.close_calls == 1


@pytest.mark.asyncio
async def test_existing_acquisition_opens_once_only_after_journal_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    edge = _edge()
    selected = _selected(tmp_path)
    destination = tmp_path / "explicit.sqlite3"
    trace: list[str] = []
    probe = AdmissionProbe(trace)
    fake, factory, created = _inject_fake_basic(monkeypatch, destination, trace)
    await edge(probe, selected, destination)
    prepared = await probe.captured_preparation()
    owner = acquisition.Acquisition(prepared.recorder)
    try:
        await owner.start(prepared.backend)
        assert owner.snapshot().provenance is not None
        assert trace == [
            "context_guard",
            "admission",
            "journal_create",
            "journal_created",
            "backend_constructed",
            "backend_open",
        ]
        assert factory.calls == [{"port": None}] and len(created) == 1
        assert await asyncio.to_thread(fake.read_started[0].wait, 1.0)
        assert fake.read_calls == 1 and fake.max_active_reads == 1
    finally:
        await owner.stop()
        snapshot = await owner.join_terminated()
        await prepared.recorder.close()
    assert snapshot.physical_release_confirmed
    assert fake.close_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", ["arbitrary", "journal"])
async def test_existing_destination_rejects_without_overwrite_reopen_or_backend_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing: str
) -> None:
    edge = _edge()
    selected = _selected(tmp_path)
    destination = tmp_path / "existing.sqlite3"
    if existing == "journal":
        journal = await sqlite_evidence.SqliteEvidenceJournal.create(
            destination, _expected_policy()
        )
        await journal.close()
    else:
        destination.write_bytes(b"preexisting destination\x00\xff")
    before = destination.read_bytes()
    trace: list[str] = []
    probe = AdmissionProbe(trace)
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "open", _forbidden)
    monkeypatch.setattr(basic_serial.BasicSerialBackend, "__init__", _forbidden)
    monkeypatch.setattr(basic_serial.BasicSerialBackend, "open", _forbidden)
    await edge(probe, selected, destination)
    with pytest.raises(rt.PreparationFailure) as caught:
        await probe.captured_preparation()
    assert caught.value.primary_issue == rt.RuntimeIssue(
        rt.RuntimeIssueSource.PREPARATION, evidence.JournalFailureKind.JOURNAL_EXISTS
    )
    assert caught.value.session_id is None
    assert caught.value.recorder_close_confirmed
    assert caught.value.cleanup_issue is None
    assert destination.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["replace", "remove"])
async def test_preparation_uses_captured_immutable_profile_after_source_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    edge = _edge()
    selected = _selected(tmp_path)
    destination = tmp_path / "explicit.sqlite3"
    trace: list[str] = []
    probe = AdmissionProbe(trace)
    fake, factory, _ = _inject_fake_basic(monkeypatch, destination, trace)
    read_sizes = _track_profile_read(monkeypatch, selected, trace)
    await edge(probe, selected, destination)
    assert probe.resolved is not None
    resolved = probe.resolved
    if change == "replace":
        selected.write_text(
            _PROFILE.replace("19200", "38400")
            .replace('"Observation fixture"', '"Edited fixture"')
            .replace("max_retained_records = 100", "max_retained_records = 200"),
            encoding="utf-8",
        )
    else:
        selected.unlink()
    prepared = await probe.captured_preparation()
    try:
        assert resolved.dut.name == "Observation fixture"
        assert resolved.uart.baud_rate == 19200
        assert prepared.recorder.policy == _expected_policy()
        connection = await prepared.backend.open()
        try:
            assert fake.baudrate == 19200
            assert factory.calls == [{"port": None}]
        finally:
            await connection.close()
    finally:
        await prepared.recorder.close()
    assert read_sizes == [65537]


# T013: preparation/transfer failures only. No T014 teardown-failure matrix,
# cancellation implementation, or substitute runtime is introduced here.
_RAW_DIAGNOSTIC = "fixture private cause /secret/profile-and-device"


def _t013_block_artifact_access(patch: pytest.MonkeyPatch, destination: Path) -> None:
    """Install after bootstrap: infrastructure's own create I/O stays real."""
    patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "open", _forbidden)
    patch.setattr(sqlite_evidence, "_connect_sqlite", _forbidden)

    def guard(original: Callable[..., object]) -> Callable[..., object]:
        def checked(path: str | Path, *args: object, **kwargs: object) -> object:
            if Path(path) == destination:
                pytest.fail("failed artifact must not be probed, reopened, or removed")
            return original(path, *args, **kwargs)

        return checked

    for name in ("open", "stat", "resolve", "unlink", "rename", "replace"):
        patch.setattr(Path, name, guard(getattr(Path, name)))
    for name in ("remove", "unlink"):
        patch.setattr(os, name, guard(getattr(os, name)))


async def _t013_preparation_failure(probe: AdmissionProbe) -> rt.PreparationFailure:
    # Ordinary try/except avoids generator-context exception transport for the
    # separately known frozen JournalFailure limitation. PreparationFailure's
    # normal exception transport is covered by the T024 regressions.
    try:
        async with asyncio.timeout(3.0):  # Test watchdog only.
            await probe.captured_preparation()
    except Exception as error:
        assert isinstance(error, rt.PreparationFailure), (
            f"preparation leaked {type(error).__name__} instead of PreparationFailure"
        )
        assert error.__cause__ is None and error.__context__ is None
        assert _RAW_DIAGNOSTIC not in str(error) + repr(error)
        return error
    pytest.fail(
        "failing preparation transferred resources instead of reporting failure"
    )


async def _t013_empty_journal(path: Path, known_id: model.SessionId) -> None:
    # Explicit test readback occurs after the normalization guard is restored;
    # this is not an application probe for a failed-create artifact's identity.
    reopened = await sqlite_evidence.SqliteEvidenceJournal.open(
        path, expected_session_id=known_id
    )
    try:
        page = await reopened.retrieve(
            evidence.EvidenceRetrievalRequest(known_id, 11, 16384)
        )
        assert page.records == () and page.snapshot_end_exclusive == 0
    finally:
        await reopened.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "kind", "confirmed"),
    [
        (
            evidence.JournalOperation.CREATE,
            evidence.JournalFailureKind.INVALID_INPUT,
            True,
        ),
        (
            evidence.JournalOperation.CREATE,
            evidence.JournalFailureKind.JOURNAL_EXISTS,
            True,
        ),
        (
            evidence.JournalOperation.OPEN,
            evidence.JournalFailureKind.INVALID_INPUT,
            False,
        ),
        (
            evidence.JournalOperation.OPEN,
            evidence.JournalFailureKind.JOURNAL_EXISTS,
            False,
        ),
    ],
)
async def test_t013_preopen_certainty_requires_exact_create_operation_and_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: evidence.JournalOperation,
    kind: evidence.JournalFailureKind,
    confirmed: bool,
) -> None:
    selected = _selected(tmp_path)
    destination = tmp_path / "untouched.sqlite3"
    destination.write_bytes(b"existing artifact\x00\xff")
    probe = AdmissionProbe([])
    await _edge()(probe, selected, destination)
    calls = 0

    async def failed_create(
        cls: type[sqlite_evidence.SqliteEvidenceJournal],
        path: str | Path,
        policy: model.SessionPolicy,
    ) -> sqlite_evidence.SqliteEvidenceJournal:
        nonlocal calls
        del cls
        calls += 1
        assert calls == 1, "failed journal creation must not be retried"
        assert Path(path) == destination and policy == _expected_policy()
        raise evidence.JournalFailure(operation, kind, _RAW_DIAGNOSTIC) from OSError(
            _RAW_DIAGNOSTIC
        )

    with monkeypatch.context() as patch:
        patch.setattr(
            sqlite_evidence.SqliteEvidenceJournal, "create", classmethod(failed_create)
        )
        patch.setattr(basic_serial.BasicSerialBackend, "__init__", _forbidden)
        patch.setattr(basic_serial.BasicSerialBackend, "open", _forbidden)
        _t013_block_artifact_access(patch, destination)
        failure = await _t013_preparation_failure(probe)
        assert failure.primary_issue == rt.RuntimeIssue(
            rt.RuntimeIssueSource.PREPARATION, kind
        )
        assert failure.recorder_close_confirmed is confirmed
        assert failure.session_id is None and failure.cleanup_issue is None
        assert calls == 1
    assert destination.read_bytes() == b"existing artifact\x00\xff"


@pytest.mark.asyncio
async def test_t013_structurally_invalid_destination_confirms_no_recorder_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = AdmissionProbe([])
    await _edge()(probe, _selected(tmp_path), cast("Path", None))
    with monkeypatch.context() as patch:
        patch.setattr(sqlite_evidence, "_connect_sqlite", _forbidden)
        patch.setattr(basic_serial.BasicSerialBackend, "__init__", _forbidden)
        failure = await _t013_preparation_failure(probe)
    assert failure.primary_issue == rt.RuntimeIssue(
        rt.RuntimeIssueSource.PREPARATION, evidence.JournalFailureKind.INVALID_INPUT
    )
    assert failure.recorder_close_confirmed
    assert failure.session_id is None and failure.cleanup_issue is None


@pytest.mark.parametrize(
    "stage", ["before_artifact", "partial_artifact", "after_commit"]
)
@pytest.mark.parametrize("fault", ["io_failure", "capacity", "unexpected"])
@pytest.mark.asyncio
async def test_t013_failed_create_keeps_artifact_without_identity_probe_or_certainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, fault: str
) -> None:
    selected = _selected(tmp_path)
    destination = tmp_path / "failed-create.sqlite3"
    probe = AdmissionProbe([])
    await _edge()(probe, selected, destination)
    original_create = sqlite_evidence.SqliteEvidenceJournal.create
    calls = 0
    before: bytes | None = None
    hidden_id: model.SessionId | None = None
    with monkeypatch.context() as patch:

        async def failed_create(
            cls: type[sqlite_evidence.SqliteEvidenceJournal],
            path: str | Path,
            policy: model.SessionPolicy,
        ) -> sqlite_evidence.SqliteEvidenceJournal:
            nonlocal calls, before, hidden_id
            del cls
            calls += 1
            assert calls == 1, "failed journal creation must not be retried"
            assert Path(path) == destination and policy == _expected_policy()
            if stage == "partial_artifact":
                destination.write_bytes(b"partial bootstrap\x00\xff")
            elif stage == "after_commit":
                journal = await original_create(path, policy)
                hidden_id = journal.session_id
                await journal.close()  # Bootstrap knows; caller never received it.
            if stage != "before_artifact":
                before = destination.read_bytes()
            _t013_block_artifact_access(patch, destination)
            if fault == "unexpected":
                raise OSError(_RAW_DIAGNOSTIC)
            raise evidence.JournalFailure(
                evidence.JournalOperation.CREATE,
                evidence.JournalFailureKind(fault),
                _RAW_DIAGNOSTIC,
            ) from OSError(_RAW_DIAGNOSTIC)

        patch.setattr(
            sqlite_evidence.SqliteEvidenceJournal, "create", classmethod(failed_create)
        )
        patch.setattr(basic_serial.BasicSerialBackend, "__init__", _forbidden)
        patch.setattr(basic_serial.BasicSerialBackend, "open", _forbidden)
        failure = await _t013_preparation_failure(probe)
        assert not failure.recorder_close_confirmed
        assert failure.session_id is None and failure.cleanup_issue is None
        assert failure.primary_issue.code == (
            "internal_contract_failure"
            if fault == "unexpected"
            else evidence.JournalFailureKind(fault)
        )
        if fault != "unexpected":
            assert failure.primary_issue.source is rt.RuntimeIssueSource.PREPARATION
        assert calls == 1
    if before is None:
        assert not destination.exists()
    else:
        assert destination.read_bytes() == before
    if hidden_id is not None:
        await _t013_empty_journal(destination, hidden_id)


@pytest.mark.parametrize("stage", ["translation", "construction"])
@pytest.mark.parametrize("fault", ["normalized", "unexpected"])
@pytest.mark.parametrize(
    "close_fails", [False, True], ids=["close-success", "close-failure"]
)
@pytest.mark.asyncio
async def test_t013_postcreate_failure_closes_owned_recorder_and_keeps_known_empty_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    fault: str,
    close_fails: bool,
) -> None:
    selected = _selected(tmp_path)
    destination = tmp_path / "known-empty.sqlite3"
    probe = AdmissionProbe([])
    await _edge()(probe, selected, destination)
    edge_module = importlib.import_module(_EDGE_MODULE)
    original_create = sqlite_evidence.SqliteEvidenceJournal.create
    original_close = sqlite_evidence.SqliteEvidenceJournal.close
    created: list[sqlite_evidence.SqliteEvidenceJournal] = []
    trace: list[str] = []
    code: rt.RuntimeIssueCode = "internal_contract_failure"
    if fault == "normalized":
        if stage == "translation":
            code = profile.ProfileFailureKind.INVALID_VALUE
            error: Exception = profile.ProfileFailure(code, _RAW_DIAGNOSTIC)
        else:
            code = BackendFailureKind.CONFIGURATION_REJECTED
            error = NormalizedBackendFailure(
                BackendFailureOperation.OPEN, code, _RAW_DIAGNOSTIC
            )
    else:
        error = ValueError(_RAW_DIAGNOSTIC)
    try:
        with monkeypatch.context() as patch:

            async def create(
                cls: type[sqlite_evidence.SqliteEvidenceJournal],
                path: str | Path,
                policy: model.SessionPolicy,
            ) -> sqlite_evidence.SqliteEvidenceJournal:
                del cls
                assert Path(path) == destination and policy == _expected_policy()
                assert created == []
                journal = await original_create(path, policy)
                created.append(journal)
                trace.append("created")
                return journal

            async def close(journal: sqlite_evidence.SqliteEvidenceJournal) -> None:
                assert journal is created[0]
                trace.append("close")
                await original_close(journal)
                if close_fails:
                    raise evidence.JournalFailure(
                        evidence.JournalOperation.CLOSE,
                        evidence.JournalFailureKind.IO_FAILURE,
                        _RAW_DIAGNOSTIC,
                    ) from OSError(_RAW_DIAGNOSTIC)

            def fail_after_create(*args: object, **kwargs: object) -> NoReturn:
                del args, kwargs
                assert len(created) == 1
                trace.append(stage)
                _t013_block_artifact_access(patch, destination)
                raise error from OSError(_RAW_DIAGNOSTIC)

            patch.setattr(
                sqlite_evidence.SqliteEvidenceJournal, "create", classmethod(create)
            )
            patch.setattr(sqlite_evidence.SqliteEvidenceJournal, "close", close)
            patch.setattr(basic_serial.BasicSerialBackend, "open", _forbidden)
            if stage == "translation":
                patch.setattr(
                    edge_module, "to_basic_serial_open_request", fail_after_create
                )
                patch.setattr(basic_serial.BasicSerialBackend, "__init__", _forbidden)
            else:
                patch.setattr(
                    basic_serial.BasicSerialBackend, "__init__", fail_after_create
                )
            failure = await _t013_preparation_failure(probe)
            assert trace == ["created", stage, "close"]
            assert failure.session_id == created[0].session_id
            assert failure.primary_issue.code == code
            if fault == "normalized":
                assert failure.primary_issue.source is rt.RuntimeIssueSource.PREPARATION
            assert failure.recorder_close_confirmed is not close_fails
            assert failure.cleanup_issue == (
                rt.RuntimeIssue(
                    rt.RuntimeIssueSource.RECORDER_CLOSE,
                    evidence.JournalFailureKind.IO_FAILURE,
                )
                if close_fails
                else None
            )
        await _t013_empty_journal(destination, created[0].session_id)
    finally:
        for journal in created:
            await original_close(journal)


async def _t013_failed_status(work: Awaitable[rt.RuntimeStatus]) -> rt.RuntimeStatus:
    try:
        async with asyncio.timeout(3.0):  # Test watchdog, not runtime deadline.
            result = await work
    except Exception as error:
        pytest.fail(
            f"attach leaked {type(error).__name__} instead of failed RuntimeStatus"
        )
    assert result.state is rt.RuntimeState.FAILED
    assert result.owner_settled
    assert result.terminal_reason is rt.RuntimeTerminalReason.STARTUP_FAILURE
    assert result.primary_issue is not None
    assert _RAW_DIAGNOSTIC not in repr(result)
    return result


async def _t013_join_test_resources(
    runtime: rt.ObservationRuntime,
    journals: list[sqlite_evidence.SqliteEvidenceJournal],
    original_close: Callable[[sqlite_evidence.SqliteEvidenceJournal], Awaitable[None]],
) -> None:
    # A missing production failure path may leave a failed owner reflected as
    # pending. Join through its public API; never inspect/cancel that owner.
    try:
        await runtime.detach()
    except Exception:
        pass
    finally:
        for journal in journals:
            await original_close(journal)


@pytest.mark.parametrize(
    "kind", ["device_not_found", "permission_denied", "io_failure", "unexpected"]
)
@pytest.mark.asyncio
async def test_t013_failed_open_keeps_session_but_never_proves_physical_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    selected = _selected(tmp_path)
    destination = tmp_path / "failed-open.sqlite3"
    runtime = rt.ObservationRuntime()
    trace: list[str] = []
    fake, factory, created = _inject_fake_basic(monkeypatch, destination, trace)
    original_close = sqlite_evidence.SqliteEvidenceJournal.close
    closes = 0
    opens = 0

    async def failed_open(backend: basic_serial.BasicSerialBackend) -> NoReturn:
        nonlocal opens
        del backend
        opens += 1
        assert len(created) == 1 and created[0].policy == _expected_policy()
        if kind == "unexpected":
            raise OSError(_RAW_DIAGNOSTIC)
        raise NormalizedBackendFailure(
            BackendFailureOperation.OPEN, BackendFailureKind(kind), _RAW_DIAGNOSTIC
        ) from OSError(_RAW_DIAGNOSTIC)

    async def close(journal: sqlite_evidence.SqliteEvidenceJournal) -> None:
        nonlocal closes
        closes += 1
        await original_close(journal)

    monkeypatch.setattr(basic_serial.BasicSerialBackend, "open", failed_open)
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "close", close)
    try:
        result = await _t013_failed_status(_edge()(runtime, selected, destination))
        assert result.session_id == created[0].session_id
        assert result.acquisition is not None
        assert (
            result.acquisition.descriptor is None
            and result.acquisition.provenance is None
        )
        assert not result.physical_release_confirmed
        assert result.recorder_close_confirmed and not result.attach_admissible
        assert result.cleanup_issues == ()
        assert opens == closes == 1
        assert not factory.calls and fake.read_calls == fake.close_calls == 0
        assert destination.is_file()
    finally:
        await _t013_join_test_resources(runtime, created, original_close)


@pytest.mark.asyncio
async def test_t013_transferred_recorder_policy_mismatch_is_closed_before_any_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = _selected(tmp_path)
    destination = tmp_path / "mismatched-policy.sqlite3"
    runtime = rt.ObservationRuntime()
    original_create = sqlite_evidence.SqliteEvidenceJournal.create
    original_close = sqlite_evidence.SqliteEvidenceJournal.close
    created: list[sqlite_evidence.SqliteEvidenceJournal] = []
    closes = 0

    async def mismatched_create(
        cls: type[sqlite_evidence.SqliteEvidenceJournal],
        path: str | Path,
        policy: model.SessionPolicy,
    ) -> sqlite_evidence.SqliteEvidenceJournal:
        del cls
        assert Path(path) == destination and policy == _expected_policy()
        assert created == []
        journal = await original_create(path, replace(policy, max_retained_records=101))
        created.append(journal)
        return journal

    async def forbidden_open(backend: basic_serial.BasicSerialBackend) -> NoReturn:
        del backend
        raise AssertionError("policy mismatch must be rejected before backend open")

    async def close(journal: sqlite_evidence.SqliteEvidenceJournal) -> None:
        nonlocal closes
        closes += 1
        await original_close(journal)

    monkeypatch.setattr(
        sqlite_evidence.SqliteEvidenceJournal, "create", classmethod(mismatched_create)
    )
    monkeypatch.setattr(sqlite_evidence.SqliteEvidenceJournal, "close", close)
    monkeypatch.setattr(basic_serial.BasicSerialBackend, "open", forbidden_open)
    try:
        result = await _t013_failed_status(_edge()(runtime, selected, destination))
        assert result.session_id == created[0].session_id
        assert result.primary_issue == rt.RuntimeIssue(
            rt.RuntimeIssueSource.INTERNAL_CONTRACT, "internal_contract_failure"
        )
        assert result.acquisition is None
        assert result.physical_release_confirmed and result.recorder_close_confirmed
        assert result.attach_admissible and result.cleanup_issues == ()
        assert closes == 1 and destination.is_file()
    finally:
        await _t013_join_test_resources(runtime, created, original_close)
