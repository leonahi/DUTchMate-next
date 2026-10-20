"""T006 RED: additive Profile-v2 resolution; no TX or runtime execution."""

import os
import tomllib
from dataclasses import FrozenInstanceError, fields, replace
from io import BytesIO
from pathlib import Path
from typing import Any, NoReturn

import pytest
import serial

from dutchmate_core import acquisition, evidence, model, profile, runtime
from dutchmate_core.adapters import (
    basic_profile,
    basic_serial,
    sqlite_evidence,
    toml_profile,
)
from tests.contract.test_toml_profile import (
    _PERSISTENCE_FIELDS,
    _SAFE_POLICY_LINES,
    _VALID_PERSISTENCE_LINES,
    _assert_profile_failure,
    _persistence_lines_with,
    _replace_once,
    _valid_profile,
)


def _v2_profile(**kwargs: Any) -> str:
    return _replace_once(
        _valid_profile(**kwargs), "profile_version = 1", "profile_version = 2"
    )


def _resolve(tmp_path: Path, document: str) -> Any:
    selected = tmp_path / "explicit.toml"
    selected.write_text(document, encoding="utf-8")
    return toml_profile.resolve_profile(selected)


def _resolve_v2(tmp_path: Path, document: str) -> Any:
    try:
        return _resolve(tmp_path, document)
    except profile.ProfileFailure as failure:
        # Do not propagate a frozen exception through pytest/contextlib's
        # traceback assignment; report the actual missing-feature rejection.
        pytest.fail(
            f"T006: valid Profile-v2 rejected as {failure.kind.value}", pytrace=False
        )


def _without_table(document: str, table: str) -> str:
    before, section = document.split(f"[{table}]\n", 1)
    _, separator, after = section.partition("\n[")
    return before + ("[" + after if separator else "")


def _forbid_resource_access(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    pytest.fail(
        "Profile resolution/translation must not access hardware, runtime or evidence"
    )


@pytest.fixture(autouse=True)
def block_profile_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    targets: tuple[tuple[object, str], ...] = (
        (serial, "Serial"),
        (serial, "serial_for_url"),
        (basic_serial.BasicSerialBackend, "open"),
        (basic_serial, "BasicSerialBackend"),
        (acquisition.Acquisition, "start"),
        (runtime.ObservationRuntime, "attach"),
        (evidence.InMemoryEvidenceRecorder, "append"),
        (sqlite_evidence.SqliteEvidenceJournal, "create"),
        (sqlite_evidence.SqliteEvidenceJournal, "open"),
        (sqlite_evidence.SqliteEvidenceJournal, "create_v2"),
        (sqlite_evidence.SqliteEvidenceJournal, "open_v2"),
        (sqlite_evidence.SqliteEvidenceJournal, "create_v3"),
        (sqlite_evidence.SqliteEvidenceJournal, "open_v3"),
        (sqlite_evidence.SqliteEvidenceJournal, "append"),
    )
    for target, attribute in targets:
        monkeypatch.setattr(target, attribute, _forbid_resource_access)
    monkeypatch.setattr("serial.tools.list_ports.comports", _forbid_resource_access)
    monkeypatch.setattr("serial.tools.list_ports.grep", _forbid_resource_access)


@pytest.mark.parametrize(
    ("policy_lines", "tx_enabled"),
    [
        (None, False),
        ((), False),
        (("uart_rx_enabled = true",), False),
        (_SAFE_POLICY_LINES, False),
        (("uart_tx_enabled = false",), False),
        (("uart_tx_enabled = true",), True),
    ],
)
def test_t006_v2_policy_defaults_and_explicit_tx_authorization(
    tmp_path: Path, policy_lines: tuple[str, ...] | None, tx_enabled: bool
) -> None:
    resolved = _resolve_v2(tmp_path, _v2_profile(policy_lines=policy_lines))

    assert type(resolved) is getattr(profile, "ResolvedInteractionProfile", None)
    assert type(resolved.policy) is getattr(profile, "InteractionPolicy", None)
    assert not isinstance(resolved, profile.ResolvedDutProfile)
    assert not isinstance(resolved.policy, profile.ObservationPolicy)
    assert not isinstance(resolved.format_version, profile.ProfileFormatVersion)
    assert resolved.format_version.value == 2
    assert (
        resolved.policy.uart_rx_enabled,
        resolved.policy.evidence_recording_enabled,
        resolved.policy.uart_tx_enabled,
        resolved.policy.semantic_control_enabled,
        resolved.policy.automatic_reconnect_enabled,
    ) == (True, True, tx_enabled, False, False)


def test_t006_v2_preserves_exact_generic_snapshot_and_all_explicit_limits(
    tmp_path: Path,
) -> None:
    resolved = _resolve_v2(
        tmp_path, _v2_profile(name=" Board A ", device=" /dev/ttyUSB0 ")
    )

    assert resolved.dut == profile.DutIdentity("board/opaque:17", " Board A ")
    assert resolved.backend == profile.ProfileBackendSelection(
        "basic_serial", " /dev/ttyUSB0 "
    )
    assert resolved.uart == profile.ProfileUartConfiguration(
        115_200, 8, "none", 1, False, False
    )
    assert resolved.open_lines == profile.ProfileSerialOpenLineIntent(
        "deasserted", "asserted"
    )
    assert resolved.session_policy == model.SessionPolicy(
        10_000, 8_388_608, 65_536, 4_096, 256, 262_144
    )
    assert {field.name for field in fields(resolved)} == {
        "format_version",
        "dut",
        "backend",
        "uart",
        "open_lines",
        "policy",
        "session_policy",
    }


@pytest.mark.parametrize(
    "component",
    [
        None,
        "format_version",
        "dut",
        "backend",
        "uart",
        "open_lines",
        "policy",
        "session_policy",
    ],
)
def test_t006_v2_snapshot_and_nested_values_are_immutable(
    tmp_path: Path, component: str | None
) -> None:
    resolved = _resolve_v2(tmp_path, _v2_profile())
    value = resolved if component is None else getattr(resolved, component)
    field_name = fields(value)[0].name
    with pytest.raises(FrozenInstanceError):
        setattr(value, field_name, getattr(value, field_name))


def test_t006_separate_v2_version_value_rejects_other_versions_and_coercions(
    tmp_path: Path,
) -> None:
    resolved = _resolve_v2(tmp_path, _v2_profile())
    version_type = type(resolved.format_version)
    assert version_type(2) == resolved.format_version
    for value in (True, False, "2", 2.0, None):
        with pytest.raises(TypeError):
            version_type(value)
    for value in (-1, 0, 1, 3):
        with pytest.raises(ValueError):
            version_type(value)


@pytest.mark.parametrize(
    "field_name",
    [
        "format_version",
        "dut",
        "backend",
        "uart",
        "open_lines",
        "policy",
        "session_policy",
    ],
)
def test_t006_v2_requires_validated_component_values(
    tmp_path: Path, field_name: str
) -> None:
    resolved = _resolve_v2(tmp_path, _v2_profile())
    with pytest.raises(TypeError):
        replace(resolved, **{field_name: object()})


def test_t006_v1_and_v2_values_cannot_be_mixed(tmp_path: Path) -> None:
    old = _resolve(tmp_path, _valid_profile())
    new = _resolve_v2(tmp_path, _v2_profile())
    for field_name in ("format_version", "policy"):
        with pytest.raises(TypeError):
            replace(old, **{field_name: getattr(new, field_name)})
        with pytest.raises(TypeError):
            replace(new, **{field_name: getattr(old, field_name)})


def test_t006_explicit_resolution_dispatch_and_source_edits_preserve_old_snapshots(
    tmp_path: Path,
) -> None:
    old = _resolve(tmp_path, _valid_profile(name="Before"))
    new = _resolve_v2(
        tmp_path,
        _v2_profile(name="Authorized", policy_lines=("uart_tx_enabled = true",)),
    )
    later = _resolve_v2(tmp_path, _v2_profile(name="After"))
    old_again = _resolve(tmp_path, _valid_profile(name="Back to v1"))

    assert type(old) is type(old_again) is profile.ResolvedDutProfile
    assert (
        old.format_version
        == old_again.format_version
        == profile.ProfileFormatVersion(1)
    )
    assert old.dut.name == "Before"
    assert new.dut.name == "Authorized"
    assert new.policy.uart_tx_enabled is True
    assert later.dut.name == "After"
    assert later.policy.uart_tx_enabled is False
    assert old_again.policy == old.policy == profile.ObservationPolicy()


@pytest.mark.parametrize("tx_enabled", [False, True])
@pytest.mark.parametrize(
    ("baud", "bits", "parity", "stops", "hardware", "software", "dtr", "rts"),
    [
        (9_600, 5, "none", 1, False, False, "asserted", "deasserted"),
        (19_200, 6, "even", 2, False, True, "deasserted", "asserted"),
        (230_400, 8, "odd", 1, True, False, "deasserted", "driver_managed"),
    ],
)
def test_t006_v2_basic_translation_preserves_uart_and_open_lines_without_resources(
    tmp_path: Path,
    tx_enabled: bool,
    baud: int,
    bits: int,
    parity: str,
    stops: int,
    hardware: bool,
    software: bool,
    dtr: str,
    rts: str,
) -> None:
    document = _v2_profile(
        device=" /dev/explicit ",
        policy_lines=(f"uart_tx_enabled = {str(tx_enabled).lower()}",),
    )
    for old, new in (
        ("baud_rate = 115200", f"baud_rate = {baud}"),
        ("data_bits = 8", f"data_bits = {bits}"),
        ('parity = "none"', f'parity = "{parity}"'),
        ("stop_bits = 1", f"stop_bits = {stops}"),
        (
            "hardware_flow_control = false",
            f"hardware_flow_control = {str(hardware).lower()}",
        ),
        (
            "software_flow_control = false",
            f"software_flow_control = {str(software).lower()}",
        ),
        ('dtr = "deasserted"', f'dtr = "{dtr}"'),
        ('rts = "asserted"', f'rts = "{rts}"'),
    ):
        document = _replace_once(document, old, new)
    resolved = _resolve_v2(tmp_path, document)
    request = basic_profile.to_basic_serial_open_request(resolved)

    expected = basic_serial.BasicSerialOpenRequest(
        selector=basic_serial.SerialDeviceSelector(" /dev/explicit "),
        configuration=basic_serial.SerialConfiguration(
            baud,
            basic_serial.SerialDataBits(bits),
            basic_serial.SerialParity(parity),
            {1: basic_serial.SerialStopBits.ONE, 2: basic_serial.SerialStopBits.TWO}[
                stops
            ],
            hardware,
            software,
        ),
        line_intent=basic_serial.SerialOpenLineIntent(
            basic_serial.SerialLineState(dtr), basic_serial.SerialLineState(rts)
        ),
    )
    assert request.selector == expected.selector
    assert request.configuration == expected.configuration
    assert request.line_intent == expected.line_intent


@pytest.mark.parametrize(
    ("field_name", "literal"),
    [
        ("uart_rx_enabled", "false"),
        ("evidence_recording_enabled", "false"),
        ("semantic_control_enabled", "true"),
        ("automatic_reconnect_enabled", "true"),
    ],
)
def test_t006_v2_forbidden_policy_is_still_unsupported(
    tmp_path: Path, field_name: str, literal: str
) -> None:
    _assert_profile_failure(
        lambda: _resolve(
            tmp_path, _v2_profile(policy_lines=(f"{field_name} = {literal}",))
        ),
        "unsupported_behavior",
    )


@pytest.mark.parametrize(
    "field_name", [line.partition(" = ")[0] for line in _SAFE_POLICY_LINES]
)
@pytest.mark.parametrize("literal", ["0", "1", '"true"', "1.0", "[]", "{}"])
def test_t006_v2_policy_has_no_boolean_coercion(
    tmp_path: Path, field_name: str, literal: str
) -> None:
    _assert_profile_failure(
        lambda: _resolve(
            tmp_path, _v2_profile(policy_lines=(f"{field_name} = {literal}",))
        ),
        "invalid_value",
    )


@pytest.mark.parametrize(
    "table",
    [None, "dut", "backend", "uart", "uart.open_lines", "policy", "persistence"],
)
def test_t006_v2_schema_rejects_unknown_keys_at_every_level(
    tmp_path: Path, table: str | None
) -> None:
    document = _v2_profile()
    document = (
        "surprise = true\n" + document
        if table is None
        else _replace_once(document, f"[{table}]\n", f"[{table}]\nsurprise = true\n")
    )
    _assert_profile_failure(lambda: _resolve(tmp_path, document), "unknown_field")


@pytest.mark.parametrize(
    "table", ["tx", "interact", "console", "control", "reconnect", "reacquire"]
)
def test_t006_v2_does_not_accept_other_behavior_tables(
    tmp_path: Path, table: str
) -> None:
    _assert_profile_failure(
        lambda: _resolve(
            tmp_path, _v2_profile(extra_configuration=f"[{table}]\nenabled = false\n")
        ),
        "unsupported_behavior",
    )


@pytest.mark.parametrize(
    "table", ["dut", "backend", "uart", "uart.open_lines", "persistence"]
)
def test_t006_v2_required_tables_have_no_defaults(tmp_path: Path, table: str) -> None:
    document = _v2_profile()
    if table == "uart":
        document = _without_table(document, "uart.open_lines")
    document = _without_table(document, table)
    _assert_profile_failure(lambda: _resolve(tmp_path, document), "missing_field")


@pytest.mark.parametrize(
    "table", ["dut", "backend", "uart", "uart.open_lines", "policy", "persistence"]
)
@pytest.mark.parametrize("literal", ['"table"', "[]", "true", "1"])
def test_t006_v2_known_tables_require_tables(
    tmp_path: Path, table: str, literal: str
) -> None:
    document = _v2_profile()
    if table == "uart":
        document = _without_table(document, "uart.open_lines")
    document = _without_table(document, table)
    assignment = f"{table} = {literal}\n"
    document = (
        _replace_once(document, "[uart]\n", "[uart]\nopen_lines = " + literal + "\n")
        if table == "uart.open_lines"
        else assignment + document
    )
    _assert_profile_failure(lambda: _resolve(tmp_path, document), "invalid_value")


@pytest.mark.parametrize(
    "line",
    [
        'id = "board/opaque:17"',
        'name = "Board A"',
        'kind = "basic_serial"',
        'expected_device = "/dev/ttyUSB0"',
        "baud_rate = 115200",
        "data_bits = 8",
        'parity = "none"',
        "stop_bits = 1",
        "hardware_flow_control = false",
        "software_flow_control = false",
        'dtr = "deasserted"',
        'rts = "asserted"',
        *_VALID_PERSISTENCE_LINES,
    ],
)
def test_t006_v2_required_fields_have_no_defaults(tmp_path: Path, line: str) -> None:
    document = _replace_once(_v2_profile(), line + "\n", "")
    _assert_profile_failure(lambda: _resolve(tmp_path, document), "missing_field")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('id = "board/opaque:17"', 'id = " "'),
        ('name = "Board A"', "name = 4"),
        ('kind = "basic_serial"', "kind = true"),
        *(
            ('expected_device = "/dev/ttyUSB0"', f'expected_device = "{value}"')
            for value in ("", "auto", "17", "-", "loop://")
        ),
        ("baud_rate = 115200", "baud_rate = true"),
        ("baud_rate = 115200", "baud_rate = 0"),
        ("data_bits = 8", "data_bits = 9"),
        ("data_bits = 8", "data_bits = true"),
        ('parity = "none"', 'parity = "mark"'),
        ("stop_bits = 1", "stop_bits = 1.5"),
        ("hardware_flow_control = false", "hardware_flow_control = 1"),
        ("software_flow_control = false", 'software_flow_control = "false"'),
        ('dtr = "deasserted"', 'dtr = "driver_managed"'),
        ('rts = "asserted"', 'rts = "driver_managed"'),
        ("hardware_flow_control = false", "hardware_flow_control = true"),
    ],
)
def test_t006_v2_retains_exact_uart_identity_and_selector_validation(
    tmp_path: Path, old: str, new: str
) -> None:
    _assert_profile_failure(
        lambda: _resolve(tmp_path, _replace_once(_v2_profile(), old, new)),
        "invalid_value",
    )


@pytest.mark.parametrize("field_name", _PERSISTENCE_FIELDS)
@pytest.mark.parametrize(
    "literal", ["true", '"10000"', "1.0", "0", "-1", "9223372036854775808"]
)
def test_t006_v2_persistence_limits_remain_explicit_positive_exact_signed_integers(
    tmp_path: Path, field_name: str, literal: str
) -> None:
    _assert_profile_failure(
        lambda: _resolve(
            tmp_path,
            _v2_profile(persistence_lines=_persistence_lines_with(field_name, literal)),
        ),
        "invalid_value",
    )


@pytest.mark.parametrize(
    "field_name", ["max_retained_charged_bytes", "max_retrieval_page_charged_bytes"]
)
def test_t006_v2_record_limit_must_fit_retention_and_retrieval(
    tmp_path: Path, field_name: str
) -> None:
    _assert_profile_failure(
        lambda: _resolve(
            tmp_path,
            _v2_profile(persistence_lines=_persistence_lines_with(field_name, "65535")),
        ),
        "invalid_value",
    )


def test_t006_v2_does_not_add_interact_specific_persistence_minima(
    tmp_path: Path,
) -> None:
    for limit in (1, 9_223_372_036_854_775_807):
        resolved = _resolve_v2(
            tmp_path,
            _v2_profile(
                persistence_lines=tuple(
                    f"{field} = {limit}" for field in _PERSISTENCE_FIELDS
                )
            ),
        )
        assert all(
            getattr(resolved.session_policy, field) == limit
            for field in _PERSISTENCE_FIELDS
        )


def test_t006_v2_rejects_simultaneous_hardware_and_software_flow_control(
    tmp_path: Path,
) -> None:
    document = _v2_profile().replace("flow_control = false", "flow_control = true")
    document = _replace_once(document, 'rts = "asserted"', 'rts = "driver_managed"')
    _assert_profile_failure(lambda: _resolve(tmp_path, document), "invalid_value")


@pytest.mark.parametrize("kind", ["enhanced", "unknown"])
def test_t006_v2_non_basic_backend_is_explicitly_unsupported(
    tmp_path: Path, kind: str
) -> None:
    document = _replace_once(_v2_profile(), 'kind = "basic_serial"', f'kind = "{kind}"')
    _assert_profile_failure(lambda: _resolve(tmp_path, document), "unsupported_backend")


@pytest.mark.parametrize("literal", [None, "true", '"2"', "2.0", "0", "-1", "3"])
def test_t006_version_rejection_is_resource_free_and_never_falls_back(
    tmp_path: Path, literal: str | None
) -> None:
    document = _replace_once(
        _v2_profile(),
        "profile_version = 2\n",
        "" if literal is None else f"profile_version = {literal}\n",
    )
    _assert_profile_failure(
        lambda: _resolve(tmp_path, document), "incompatible_version"
    )


def test_t006_v1_explicit_tx_is_still_rejected_without_resources(
    tmp_path: Path,
) -> None:
    _assert_profile_failure(
        lambda: _resolve(
            tmp_path, _valid_profile(policy_lines=("uart_tx_enabled = true",))
        ),
        "unsupported_behavior",
    )


@pytest.mark.parametrize(
    ("document", "kind"),
    [
        ("profile_version = 3\nsurprise = true\n[tx]\n", "unsupported_behavior"),
        ("profile_version = 3\nsurprise = true\n", "unknown_field"),
        ("profile_version = 3\n", "incompatible_version"),
        (
            _replace_once(_v2_profile(), 'id = "board/opaque:17"', "surprise = true"),
            "unknown_field",
        ),
        (
            _replace_once(
                _v2_profile(), 'kind = "basic_serial"', 'kind = "enhanced"'
            ).replace("baud_rate = 115200", "baud_rate = 0"),
            "unsupported_backend",
        ),
        (
            _v2_profile(
                policy_lines=("uart_rx_enabled = false",),
                persistence_lines=_persistence_lines_with("max_retained_records", "0"),
            ),
            "unsupported_behavior",
        ),
    ],
)
def test_t006_v2_preserves_004_failure_precedence(
    tmp_path: Path, document: str, kind: str
) -> None:
    _assert_profile_failure(lambda: _resolve(tmp_path, document), kind)


def test_t006_v2_accepts_exact_65536_byte_utf8_document(tmp_path: Path) -> None:
    captured = _v2_profile(name="Bøard").encode("utf-8")
    captured += b"#" + b"x" * (65_536 - len(captured) - 2) + b"\n"
    assert len(captured) == 65_536
    assert _resolve_v2(tmp_path, captured.decode("utf-8")).dut.name == "Bøard"


def test_t006_oversize_capture_is_bounded_and_rejected_before_parsing_despite_stale_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "oversize.toml"
    selected.write_bytes(_v2_profile().encode() + b"\xff" * 65_538)
    source = selected.read_bytes()
    metadata = list(selected.stat())
    metadata[6] = 1
    original_stat = Path.stat
    original_open = Path.open
    reads: list[int] = []

    class BoundedSource(BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            assert type(size) is int and 0 <= size <= 65_537
            reads.append(size)
            return super().read(size)

    def stale_stat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        return (
            os.stat_result(metadata)
            if path == selected
            else original_stat(path, *args, **kwargs)
        )

    def bounded_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        return (
            BoundedSource(source)
            if path == selected
            else original_open(path, *args, **kwargs)
        )

    def forbid_parser(*args: Any, **kwargs: Any) -> NoReturn:
        pytest.fail("oversized capture must be rejected before a parser tree exists")

    monkeypatch.setattr(Path, "stat", stale_stat)
    monkeypatch.setattr(Path, "open", bounded_open)
    monkeypatch.setattr(tomllib, "loads", forbid_parser)
    _assert_profile_failure(
        lambda: toml_profile.resolve_profile(selected), "input_too_large"
    )
    assert sum(reads) <= 65_537
    assert reads


@pytest.mark.parametrize(
    "captured",
    [
        b"profile_version = 2\n\xff",
        b"profile_version = 2\nprofile_version = 2\n",
        b"profile_version = 2\n[dut",
    ],
)
def test_t006_v2_invalid_utf8_toml_and_duplicate_keys_are_normalized(
    tmp_path: Path, captured: bytes
) -> None:
    selected = tmp_path / "invalid.toml"
    selected.write_bytes(captured)
    _assert_profile_failure(
        lambda: toml_profile.resolve_profile(selected), "invalid_syntax"
    )
