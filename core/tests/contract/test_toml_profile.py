"""Contract tests for explicit TOML DUT Profile resolution."""

import errno
import os
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import pytest
import serial

from dutchmate_core import acquisition, model, profile
from dutchmate_core.adapters import sqlite_evidence, toml_profile

_SAFE_POLICY_LINES = (
    "uart_rx_enabled = true",
    "evidence_recording_enabled = true",
    "uart_tx_enabled = false",
    "semantic_control_enabled = false",
    "automatic_reconnect_enabled = false",
)
_VALID_PERSISTENCE_LINES = (
    "max_retained_records = 10000",
    "max_retained_charged_bytes = 8388608",
    "max_record_charged_bytes = 65536",
    "max_database_pages = 4096",
    "max_retrieval_page_records = 256",
    "max_retrieval_page_charged_bytes = 262144",
)
_PERSISTENCE_FIELDS = tuple(
    line.partition(" = ")[0] for line in _VALID_PERSISTENCE_LINES
)


def _valid_profile(
    *,
    name: str = "Board A",
    device: str = "/dev/ttyUSB0",
    policy_lines: tuple[str, ...] | None = _SAFE_POLICY_LINES,
    persistence_lines: tuple[str, ...] = _VALID_PERSISTENCE_LINES,
    extra_configuration: str = "",
) -> str:
    policy_section = (
        "" if policy_lines is None else f"[policy]\n{'\n'.join(policy_lines)}\n\n"
    )
    return f'''profile_version = 1

[dut]
id = "board/opaque:17"
name = "{name}"

[backend]
kind = "basic_serial"
expected_device = "{device}"

[uart]
baud_rate = 115200
data_bits = 8
parity = "none"
stop_bits = 1
hardware_flow_control = false
software_flow_control = false

[uart.open_lines]
dtr = "deasserted"
rts = "asserted"

{policy_section}[persistence]
{"\n".join(persistence_lines)}
{extra_configuration}
'''


def _policy_lines_with(field_name: str, value: bool) -> tuple[str, ...]:
    rendered = "true" if value else "false"
    prefix = f"{field_name} = "
    return tuple(
        f"{prefix}{rendered}" if line.startswith(prefix) else line
        for line in _SAFE_POLICY_LINES
    )


def _persistence_lines_with(field_name: str, literal: str) -> tuple[str, ...]:
    prefix = f"{field_name} = "
    return tuple(
        f"{prefix}{literal}" if line.startswith(prefix) else line
        for line in _VALID_PERSISTENCE_LINES
    )


def _replace_once(document: str, old: str, new: str) -> str:
    assert document.count(old) == 1
    return document.replace(old, new, 1)


def _profile_bytes_with_size(size: int) -> bytes:
    captured = _valid_profile().encode("utf-8")
    padding_size = size - len(captured)
    assert padding_size >= 2
    return captured + b"#" + (b"x" * (padding_size - 2)) + b"\n"


def _assert_safe_policy(policy: profile.ObservationPolicy) -> None:
    assert (
        policy.uart_rx_enabled,
        policy.evidence_recording_enabled,
        policy.uart_tx_enabled,
        policy.semantic_control_enabled,
        policy.automatic_reconnect_enabled,
    ) == (True, True, False, False, False)


def _assert_profile_failure(
    action: Callable[[], object],
    expected_kind: str,
) -> None:
    try:
        action()
    except Exception as failure:
        assert type(failure).__name__ == "ProfileFailure"
        assert getattr(failure, "kind", None) == expected_kind
        detail = getattr(failure, "detail", None)
        assert detail is None or type(detail) is str
        assert failure.__cause__ is None
        assert failure.__context__ is None
    else:
        pytest.fail(f"Profile resolution must fail as {expected_kind}")


def _assert_unsupported_behavior(action: Callable[[], object]) -> None:
    _assert_profile_failure(action, "unsupported_behavior")


def _fail_on_side_effect(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    pytest.fail("Profile resolution must not start hardware or lifecycle work")


@pytest.fixture
def block_profile_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    targets: tuple[tuple[object, str], ...] = (
        (acquisition.Acquisition, "start"),
        (serial, "Serial"),
        (sqlite_evidence.SqliteEvidenceJournal, "create"),
        (sqlite_evidence.SqliteEvidenceJournal, "open"),
    )
    for target, attribute in targets:
        monkeypatch.setattr(target, attribute, _fail_on_side_effect)


def test_valid_profile_resolves_exact_values_without_side_effects(
    tmp_path: Path,
    block_profile_side_effects: None,
) -> None:
    del block_profile_side_effects
    selected_path = tmp_path / "selected.toml"
    selected_path.write_text(_valid_profile(), encoding="utf-8")

    resolved = toml_profile.resolve_profile(selected_path)

    assert resolved.format_version.value == 1
    assert resolved.dut.id == "board/opaque:17"
    assert resolved.dut.name == "Board A"
    assert resolved.backend.kind == "basic_serial"
    assert resolved.backend.expected_device == "/dev/ttyUSB0"
    assert resolved.uart.baud_rate == 115_200
    assert resolved.uart.data_bits == 8
    assert resolved.uart.parity == "none"
    assert resolved.uart.stop_bits == 1
    assert resolved.uart.hardware_flow_control is False
    assert resolved.uart.software_flow_control is False
    assert resolved.open_lines.dtr == "deasserted"
    assert resolved.open_lines.rts == "asserted"
    assert resolved.policy.uart_rx_enabled is True
    assert resolved.policy.evidence_recording_enabled is True
    assert resolved.policy.uart_tx_enabled is False
    assert resolved.policy.semantic_control_enabled is False
    assert resolved.policy.automatic_reconnect_enabled is False
    assert resolved.session_policy == model.SessionPolicy(
        max_retained_records=10_000,
        max_retained_charged_bytes=8_388_608,
        max_record_charged_bytes=65_536,
        max_database_pages=4_096,
        max_retrieval_page_records=256,
        max_retrieval_page_charged_bytes=262_144,
    )
    assert not hasattr(resolved, "session_id")
    assert not hasattr(resolved, "source_path")


def test_resolution_returns_a_snapshot_isolated_from_later_source_edits(
    tmp_path: Path,
) -> None:
    selected_path = tmp_path / "selected.toml"
    selected_path.write_text(
        _valid_profile(name="First Name", device="/dev/first"),
        encoding="utf-8",
    )
    first = toml_profile.resolve_profile(selected_path)

    selected_path.write_text(
        _valid_profile(name="Second Name", device="/dev/second"),
        encoding="utf-8",
    )
    second = toml_profile.resolve_profile(selected_path)

    assert first.dut.name == "First Name"
    assert first.backend.expected_device == "/dev/first"
    assert second.dut.name == "Second Name"
    assert second.backend.expected_device == "/dev/second"


@pytest.mark.usefixtures("block_profile_side_effects")
class TestT007ObservationPolicyResolution:
    def test_omitted_policy_table_uses_safe_defaults(self, tmp_path: Path) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _valid_profile(policy_lines=None),
            encoding="utf-8",
        )

        resolved = toml_profile.resolve_profile(selected_path)

        _assert_safe_policy(resolved.policy)

    @pytest.mark.parametrize(
        "omitted_field",
        [
            "uart_rx_enabled",
            "evidence_recording_enabled",
            "uart_tx_enabled",
            "semantic_control_enabled",
            "automatic_reconnect_enabled",
        ],
    )
    def test_each_omitted_policy_field_uses_its_safe_default(
        self,
        tmp_path: Path,
        omitted_field: str,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _valid_profile(
                policy_lines=tuple(
                    line
                    for line in _SAFE_POLICY_LINES
                    if not line.startswith(f"{omitted_field} = ")
                )
            ),
            encoding="utf-8",
        )

        resolved = toml_profile.resolve_profile(selected_path)

        _assert_safe_policy(resolved.policy)

    @pytest.mark.parametrize(
        ("field_name", "opposite_value"),
        [
            ("uart_rx_enabled", False),
            ("evidence_recording_enabled", False),
            ("uart_tx_enabled", True),
            ("semantic_control_enabled", True),
            ("automatic_reconnect_enabled", True),
        ],
    )
    def test_opposite_policy_value_is_unsupported_behavior(
        self,
        tmp_path: Path,
        field_name: str,
        opposite_value: bool,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _valid_profile(
                policy_lines=_policy_lines_with(field_name, opposite_value)
            ),
            encoding="utf-8",
        )

        _assert_unsupported_behavior(
            lambda: toml_profile.resolve_profile(selected_path)
        )

    @pytest.mark.parametrize(
        "extra_configuration",
        [
            '[tx]\nline_ending = "crlf"',
            '[interact]\ncompletion = "line"',
            '[console]\ninput_enabled = false',
            '[control]\nrole_mapping = "reset:dtr"',
            '[control]\naction_sequence = ["assert", "deassert"]',
            '[control]\nsafe_state = "deasserted"',
            '[reconnect]\ntopology = "native_usb"',
            '[reconnect]\nmatch_expected_device = true',
            "[reconnect]\nretry_limit = 3",
            "[reacquire]\nautomatic = true",
        ],
        ids=(
            "tx-line-ending",
            "interact-policy",
            "console-policy",
            "control-role-mapping",
            "control-sequence",
            "control-safe-state",
            "reconnect-topology",
            "reconnect-matching",
            "reconnect-retry",
            "automatic-reacquire",
        ),
    )
    def test_recognized_state_changing_configuration_is_unsupported_behavior(
        self,
        tmp_path: Path,
        extra_configuration: str,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _valid_profile(extra_configuration=extra_configuration),
            encoding="utf-8",
        )

        _assert_unsupported_behavior(
            lambda: toml_profile.resolve_profile(selected_path)
        )


@pytest.mark.usefixtures("block_profile_side_effects")
class TestT008PersistenceInput:
    @pytest.mark.parametrize("missing_field", _PERSISTENCE_FIELDS)
    def test_each_missing_persistence_field_is_missing_field(
        self,
        tmp_path: Path,
        missing_field: str,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _valid_profile(
                persistence_lines=tuple(
                    line
                    for line in _VALID_PERSISTENCE_LINES
                    if not line.startswith(f"{missing_field} = ")
                )
            ),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "missing_field",
        )

    @pytest.mark.parametrize("field_name", _PERSISTENCE_FIELDS)
    @pytest.mark.parametrize("wrong_scalar", ['"100"', "100.5"])
    def test_each_persistence_field_rejects_wrong_scalar_types(
        self,
        tmp_path: Path,
        field_name: str,
        wrong_scalar: str,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _valid_profile(
                persistence_lines=_persistence_lines_with(
                    field_name,
                    wrong_scalar,
                )
            ),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "invalid_value",
        )

    @pytest.mark.parametrize("field_name", _PERSISTENCE_FIELDS)
    def test_each_persistence_field_rejects_boolean_as_integer(
        self,
        tmp_path: Path,
        field_name: str,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _valid_profile(
                persistence_lines=_persistence_lines_with(field_name, "true")
            ),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "invalid_value",
        )

    @pytest.mark.parametrize("field_name", _PERSISTENCE_FIELDS)
    @pytest.mark.parametrize("invalid_integer", ["0", "-1", "9223372036854775808"])
    def test_each_persistence_field_rejects_non_positive_or_out_of_range_integer(
        self,
        tmp_path: Path,
        field_name: str,
        invalid_integer: str,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _valid_profile(
                persistence_lines=_persistence_lines_with(
                    field_name,
                    invalid_integer,
                )
            ),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "invalid_value",
        )

    @pytest.mark.parametrize(
        ("field_name", "literal"),
        [
            ("max_retained_charged_bytes", "65535"),
            ("max_retrieval_page_charged_bytes", "65535"),
        ],
        ids=("record-exceeds-retention", "record-exceeds-retrieval-page"),
    )
    def test_record_charge_must_fit_both_byte_ceilings(
        self,
        tmp_path: Path,
        field_name: str,
        literal: str,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _valid_profile(
                persistence_lines=_persistence_lines_with(field_name, literal)
            ),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "invalid_value",
        )

    def test_signed_64_bit_upper_bounds_map_directly_to_session_policy(
        self,
        tmp_path: Path,
    ) -> None:
        maximum = "9223372036854775807"
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _valid_profile(
                persistence_lines=tuple(
                    f"{field_name} = {maximum}"
                    for field_name in _PERSISTENCE_FIELDS
                )
            ),
            encoding="utf-8",
        )

        resolved = toml_profile.resolve_profile(selected_path)

        assert resolved.session_policy == model.SessionPolicy(
            max_retained_records=9_223_372_036_854_775_807,
            max_retained_charged_bytes=9_223_372_036_854_775_807,
            max_record_charged_bytes=9_223_372_036_854_775_807,
            max_database_pages=9_223_372_036_854_775_807,
            max_retrieval_page_records=9_223_372_036_854_775_807,
            max_retrieval_page_charged_bytes=9_223_372_036_854_775_807,
        )
        assert not hasattr(resolved.session_policy, "max_page_count")

    def test_retention_and_retrieval_limits_remain_independent(
        self,
        tmp_path: Path,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _valid_profile(
                persistence_lines=(
                    "max_retained_records = 2",
                    "max_retained_charged_bytes = 100000",
                    "max_record_charged_bytes = 500",
                    "max_database_pages = 17",
                    "max_retrieval_page_records = 50",
                    "max_retrieval_page_charged_bytes = 500",
                )
            ),
            encoding="utf-8",
        )

        resolved = toml_profile.resolve_profile(selected_path)

        assert resolved.session_policy == model.SessionPolicy(
            max_retained_records=2,
            max_retained_charged_bytes=100_000,
            max_record_charged_bytes=500,
            max_database_pages=17,
            max_retrieval_page_records=50,
            max_retrieval_page_charged_bytes=500,
        )


@pytest.mark.usefixtures("block_profile_side_effects")
class TestT012ProfileSourceBoundary:
    def test_missing_source_is_missing_file(self, tmp_path: Path) -> None:
        selected_path = tmp_path / "missing.toml"

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "missing_file",
        )

    def test_non_regular_source_is_not_a_file(self, tmp_path: Path) -> None:
        selected_path = tmp_path / "profile-directory"
        selected_path.mkdir()

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "not_a_file",
        )

    @pytest.mark.parametrize(
        "misleading_message",
        ["No such file or directory", "invalid TOML document"],
    )
    def test_unreadable_source_classification_ignores_os_error_message(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        misleading_message: str,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(_valid_profile(), encoding="utf-8")

        def deny_read(*args: object, **kwargs: object) -> NoReturn:
            del args, kwargs
            raise PermissionError(errno.EACCES, misleading_message)

        monkeypatch.setattr(Path, "open", deny_read)

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "unreadable",
        )

    def test_invalid_local_path_is_normalized_as_unreadable(
        self,
        tmp_path: Path,
    ) -> None:
        selected_path = Path(f"{tmp_path}/profile\0.toml")

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "unreadable",
        )

    def test_exactly_65536_captured_bytes_may_resolve(
        self,
        tmp_path: Path,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_bytes(_profile_bytes_with_size(65_536))

        resolved = toml_profile.resolve_profile(selected_path)

        assert resolved.format_version.value == 1
        assert resolved.dut.id == "board/opaque:17"

    def test_65537_captured_bytes_fail_before_parsing_despite_stale_metadata(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_bytes(_profile_bytes_with_size(65_537))
        real_stat = Path.stat
        stat_fields = list(real_stat(selected_path))
        stat_fields[6] = 1
        stale_stat = os.stat_result(stat_fields)

        def report_stale_size(
            path: Path,
            *,
            follow_symlinks: bool = True,
        ) -> os.stat_result:
            if path == selected_path:
                return stale_stat
            return real_stat(path, follow_symlinks=follow_symlinks)

        def fail_if_parsed(*args: object, **kwargs: object) -> NoReturn:
            del args, kwargs
            pytest.fail("oversized Profile input must not reach TOML parsing")

        monkeypatch.setattr(Path, "stat", report_stale_size)
        monkeypatch.setattr(tomllib, "loads", fail_if_parsed)

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "input_too_large",
        )

    @pytest.mark.parametrize(
        ("contents", "case"),
        [
            (b"\xff", "invalid-utf8"),
            (b"profile_version = ", "invalid-toml"),
            (
                b"profile_version = 1\nprofile_version = 1\n",
                "duplicate-key",
            ),
        ],
        ids=lambda value: value if isinstance(value, str) else None,
    )
    def test_invalid_source_syntax_is_normalized(
        self,
        tmp_path: Path,
        contents: bytes,
        case: str,
    ) -> None:
        del case
        selected_path = tmp_path / "profile.toml"
        selected_path.write_bytes(contents)

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "invalid_syntax",
        )


@pytest.mark.usefixtures("block_profile_side_effects")
class TestT012ProfileCompatibilityAndSchema:
    @pytest.mark.parametrize(
        "version_line",
        [None, "profile_version = true", 'profile_version = "1"',
         "profile_version = 1.0", "profile_version = 0",
         "profile_version = -1", "profile_version = 2"],
        ids=("missing", "boolean", "string", "float", "zero", "negative", "two"),
    )
    def test_incompatible_profile_versions_are_rejected(
        self,
        tmp_path: Path,
        version_line: str | None,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        replacement = "" if version_line is None else f"{version_line}\n"
        selected_path.write_text(
            _replace_once(_valid_profile(), "profile_version = 1\n", replacement),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "incompatible_version",
        )

    @pytest.mark.parametrize(
        ("table_name", "table_block"),
        [
            ("dut", '[dut]\nid = "board/opaque:17"\nname = "Board A"\n\n'),
            (
                "backend",
                '[backend]\nkind = "basic_serial"\n'
                'expected_device = "/dev/ttyUSB0"\n\n',
            ),
            (
                "uart",
                "[uart]\nbaud_rate = 115200\ndata_bits = 8\nparity = \"none\"\n"
                "stop_bits = 1\nhardware_flow_control = false\n"
                "software_flow_control = false\n\n[uart.open_lines]\n"
                'dtr = "deasserted"\nrts = "asserted"\n\n',
            ),
            (
                "uart.open_lines",
                '[uart.open_lines]\ndtr = "deasserted"\nrts = "asserted"\n\n',
            ),
            (
                "persistence",
                "[persistence]\n" + "\n".join(_VALID_PERSISTENCE_LINES) + "\n",
            ),
        ],
    )
    def test_each_required_table_is_missing_field(
        self,
        tmp_path: Path,
        table_name: str,
        table_block: str,
    ) -> None:
        del table_name
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _replace_once(_valid_profile(), table_block, ""),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "missing_field",
        )

    @pytest.mark.parametrize(
        ("table_name", "table_block"),
        [
            ("dut", '[dut]\nid = "board/opaque:17"\nname = "Board A"\n\n'),
            (
                "backend",
                '[backend]\nkind = "basic_serial"\n'
                'expected_device = "/dev/ttyUSB0"\n\n',
            ),
            (
                "uart",
                "[uart]\nbaud_rate = 115200\ndata_bits = 8\nparity = \"none\"\n"
                "stop_bits = 1\nhardware_flow_control = false\n"
                "software_flow_control = false\n\n[uart.open_lines]\n"
                'dtr = "deasserted"\nrts = "asserted"\n\n',
            ),
            (
                "policy",
                "[policy]\n" + "\n".join(_SAFE_POLICY_LINES) + "\n\n",
            ),
            (
                "persistence",
                "[persistence]\n" + "\n".join(_VALID_PERSISTENCE_LINES) + "\n",
            ),
        ],
    )
    def test_root_table_with_scalar_value_is_invalid_value(
        self,
        tmp_path: Path,
        table_name: str,
        table_block: str,
    ) -> None:
        without_table = _replace_once(_valid_profile(), table_block, "")
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _replace_once(
                without_table,
                "profile_version = 1\n",
                f'profile_version = 1\n{table_name} = "not-a-table"\n',
            ),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "invalid_value",
        )

    def test_open_lines_with_scalar_value_is_invalid_value(
        self,
        tmp_path: Path,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _replace_once(
                _valid_profile(),
                '[uart.open_lines]\ndtr = "deasserted"\nrts = "asserted"\n\n',
                'open_lines = "not-a-table"\n\n',
            ),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "invalid_value",
        )

    @pytest.mark.parametrize(
        "required_line",
        [
            'id = "board/opaque:17"\n',
            'name = "Board A"\n',
            'kind = "basic_serial"\n',
            'expected_device = "/dev/ttyUSB0"\n',
            "baud_rate = 115200\n",
            "data_bits = 8\n",
            'parity = "none"\n',
            "stop_bits = 1\n",
            "hardware_flow_control = false\n",
            "software_flow_control = false\n",
            'dtr = "deasserted"\n',
            'rts = "asserted"\n',
        ],
    )
    def test_each_required_non_persistence_field_is_missing_field(
        self,
        tmp_path: Path,
        required_line: str,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _replace_once(_valid_profile(), required_line, ""),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "missing_field",
        )

    @pytest.mark.parametrize(
        ("location", "old", "new"),
        [
            (
                "root-key",
                "profile_version = 1\n",
                "profile_version = 1\nfuture_option = true\n",
            ),
            (
                "root-table",
                "\n[persistence]\n",
                "\n[future]\nenabled = true\n\n[persistence]\n",
            ),
            ("dut", 'name = "Board A"\n', 'name = "Board A"\nalias = "A"\n'),
            (
                "backend",
                'expected_device = "/dev/ttyUSB0"\n',
                'expected_device = "/dev/ttyUSB0"\ndiscovery = true\n',
            ),
            (
                "uart",
                "software_flow_control = false\n",
                "software_flow_control = false\nread_timeout = 1\n",
            ),
            (
                "uart.open_lines",
                'rts = "asserted"\n',
                'rts = "asserted"\nelectrical_safe = true\n',
            ),
            (
                "policy",
                "automatic_reconnect_enabled = false\n",
                "automatic_reconnect_enabled = false\nmonitor_enabled = true\n",
            ),
            (
                "persistence",
                "max_retrieval_page_charged_bytes = 262144\n",
                "max_retrieval_page_charged_bytes = 262144\n"
                "journal_path = \"journal.sqlite3\"\n",
            ),
        ],
    )
    def test_unknown_root_and_nested_fields_are_unknown_field(
        self,
        tmp_path: Path,
        location: str,
        old: str,
        new: str,
    ) -> None:
        del location
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _replace_once(_valid_profile(), old, new),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "unknown_field",
        )

    @pytest.mark.parametrize(
        ("field_name", "old", "new"),
        [
            ("dut.id", 'id = "board/opaque:17"', "id = 1"),
            ("dut.name", 'name = "Board A"', "name = 1"),
            ("backend.kind", 'kind = "basic_serial"', "kind = 1"),
            (
                "backend.expected_device",
                'expected_device = "/dev/ttyUSB0"',
                "expected_device = 1",
            ),
            ("uart.baud_rate", "baud_rate = 115200", 'baud_rate = "115200"'),
            ("uart.data_bits", "data_bits = 8", 'data_bits = "8"'),
            ("uart.parity", 'parity = "none"', "parity = 1"),
            ("uart.stop_bits", "stop_bits = 1", "stop_bits = true"),
            (
                "uart.hardware_flow_control",
                "hardware_flow_control = false",
                'hardware_flow_control = "false"',
            ),
            (
                "uart.software_flow_control",
                "software_flow_control = false",
                "software_flow_control = 0",
            ),
            ("uart.open_lines.dtr", 'dtr = "deasserted"', "dtr = true"),
            ("uart.open_lines.rts", 'rts = "asserted"', "rts = 1"),
            (
                "policy.uart_rx_enabled",
                "uart_rx_enabled = true",
                'uart_rx_enabled = "true"',
            ),
            (
                "policy.evidence_recording_enabled",
                "evidence_recording_enabled = true",
                "evidence_recording_enabled = 1",
            ),
            (
                "policy.uart_tx_enabled",
                "uart_tx_enabled = false",
                'uart_tx_enabled = "false"',
            ),
            (
                "policy.semantic_control_enabled",
                "semantic_control_enabled = false",
                "semantic_control_enabled = 0",
            ),
            (
                "policy.automatic_reconnect_enabled",
                "automatic_reconnect_enabled = false",
                'automatic_reconnect_enabled = "false"',
            ),
        ],
    )
    def test_known_fields_with_wrong_scalar_types_are_invalid_value(
        self,
        tmp_path: Path,
        field_name: str,
        old: str,
        new: str,
    ) -> None:
        del field_name
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _replace_once(_valid_profile(), old, new),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "invalid_value",
        )

    @pytest.mark.parametrize("field_name", ["id", "name"])
    def test_whitespace_identity_values_are_invalid_value(
        self,
        tmp_path: Path,
        field_name: str,
    ) -> None:
        old = (
            'id = "board/opaque:17"'
            if field_name == "id"
            else 'name = "Board A"'
        )
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _replace_once(_valid_profile(), old, f'{field_name} = "   "'),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "invalid_value",
        )

    @pytest.mark.parametrize("backend_kind", ["enhanced", "future_backend"])
    def test_non_basic_backend_is_unsupported_backend(
        self,
        tmp_path: Path,
        backend_kind: str,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _replace_once(
                _valid_profile(),
                'kind = "basic_serial"',
                f'kind = "{backend_kind}"',
            ),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "unsupported_backend",
        )

    @pytest.mark.parametrize(
        "device",
        ["", "   ", "7", "auto", "AUTO", "-", "loop://", "socket://host:23"],
    )
    def test_feature_002_invalid_device_selectors_are_invalid_value(
        self,
        tmp_path: Path,
        device: str,
    ) -> None:
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(_valid_profile(device=device), encoding="utf-8")

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "invalid_value",
        )

    @pytest.mark.parametrize(
        ("case", "old", "new"),
        [
            ("non-positive-baud", "baud_rate = 115200", "baud_rate = 0"),
            ("invalid-data-bits", "data_bits = 8", "data_bits = 9"),
            ("unsupported-parity", 'parity = "none"', 'parity = "mark"'),
            ("invalid-stop-bits", "stop_bits = 1", "stop_bits = 3"),
            (
                "both-flow-controls",
                "hardware_flow_control = false\nsoftware_flow_control = false",
                "hardware_flow_control = true\nsoftware_flow_control = true",
            ),
            (
                "driver-managed-dtr",
                'dtr = "deasserted"',
                'dtr = "driver_managed"',
            ),
            ("unsupported-dtr", 'dtr = "deasserted"', 'dtr = "floating"'),
            ("unsupported-rts", 'rts = "asserted"', 'rts = "floating"'),
            (
                "driver-managed-rts-without-rtscts",
                'rts = "asserted"',
                'rts = "driver_managed"',
            ),
            (
                "static-rts-with-rtscts",
                "hardware_flow_control = false",
                "hardware_flow_control = true",
            ),
        ],
    )
    def test_invalid_uart_or_open_line_values_are_invalid_value(
        self,
        tmp_path: Path,
        case: str,
        old: str,
        new: str,
    ) -> None:
        del case
        selected_path = tmp_path / "profile.toml"
        selected_path.write_text(
            _replace_once(_valid_profile(), old, new),
            encoding="utf-8",
        )

        _assert_profile_failure(
            lambda: toml_profile.resolve_profile(selected_path),
            "invalid_value",
        )
