"""Strict, side-effect-free TOML DUT Profile resolution adapter."""

import stat
import tomllib
from os import stat_result
from pathlib import Path
from typing import cast

from dutchmate_core.model import SessionPolicy
from dutchmate_core.profile import (
    DutIdentity,
    InteractionPolicy,
    InteractionProfileFormatVersion,
    ObservationPolicy,
    ProfileBackendSelection,
    ProfileFailure,
    ProfileFailureKind,
    ProfileFormatVersion,
    ProfileSerialOpenLineIntent,
    ProfileUartConfiguration,
    ResolvedDutProfile,
    ResolvedInteractionProfile,
    ResolvedProfile,
)

type TomlTable = dict[str, object]

_PROFILE_MAX_BYTES = 65_536
_PROFILE_CAPTURE_LIMIT = _PROFILE_MAX_BYTES + 1
_UNSUPPORTED_BEHAVIOR_TABLES = (
    "tx",
    "interact",
    "console",
    "control",
    "reconnect",
    "reacquire",
)
_ROOT_FIELDS = (
    "profile_version",
    "dut",
    "backend",
    "uart",
    "policy",
    "persistence",
)
_DUT_FIELDS = ("id", "name")
_BACKEND_FIELDS = ("kind", "expected_device")
_UART_FIELDS = (
    "baud_rate",
    "data_bits",
    "parity",
    "stop_bits",
    "hardware_flow_control",
    "software_flow_control",
    "open_lines",
)
_OPEN_LINE_FIELDS = ("dtr", "rts")
_POLICY_FIELDS = (
    "uart_rx_enabled",
    "evidence_recording_enabled",
    "uart_tx_enabled",
    "semantic_control_enabled",
    "automatic_reconnect_enabled",
)
_PERSISTENCE_FIELDS = (
    "max_retained_records",
    "max_retained_charged_bytes",
    "max_record_charged_bytes",
    "max_database_pages",
    "max_retrieval_page_records",
    "max_retrieval_page_charged_bytes",
)


def resolve_profile(explicit_path: str | Path) -> ResolvedProfile:
    """Resolve one captured Profile by its explicit version, without fallback."""

    captured = _capture_profile(Path(explicit_path))
    document = _parse_profile(captured)
    dut, backend, uart, open_lines, policy = _validate_schema(document)
    version = cast("int", document["profile_version"])

    backend_kind = backend["kind"]
    if type(backend_kind) is not str:
        raise ProfileFailure(
            ProfileFailureKind.INVALID_VALUE,
            "backend.kind must be text",
        )
    if backend_kind != "basic_serial":
        raise ProfileFailure(
            ProfileFailureKind.UNSUPPORTED_BACKEND,
            f"the selected backend is unavailable in Profile version {version}",
        )

    try:
        dut_value = DutIdentity(
            id=cast("str", dut["id"]),
            name=cast("str", dut["name"]),
        )
        backend_value = ProfileBackendSelection(
            kind=backend_kind,
            expected_device=cast("str", backend["expected_device"]),
        )
        uart_value = ProfileUartConfiguration(
            baud_rate=cast("int", uart["baud_rate"]),
            data_bits=cast("int", uart["data_bits"]),
            parity=cast("str", uart["parity"]),
            stop_bits=cast("int", uart["stop_bits"]),
            hardware_flow_control=cast("bool", uart["hardware_flow_control"]),
            software_flow_control=cast("bool", uart["software_flow_control"]),
        )
        open_lines_value = ProfileSerialOpenLineIntent(
            dtr=cast("str", open_lines["dtr"]),
            rts=cast("str", open_lines["rts"]),
        )
        policy_values = {
            "uart_rx_enabled": cast("bool", policy.get("uart_rx_enabled", True)),
            "evidence_recording_enabled": cast(
                "bool", policy.get("evidence_recording_enabled", True)
            ),
            "uart_tx_enabled": cast("bool", policy.get("uart_tx_enabled", False)),
            "semantic_control_enabled": cast(
                "bool", policy.get("semantic_control_enabled", False)
            ),
            "automatic_reconnect_enabled": cast(
                "bool", policy.get("automatic_reconnect_enabled", False)
            ),
        }
        resolved: ResolvedProfile
        if version == 1:
            resolved = ResolvedDutProfile(
                format_version=ProfileFormatVersion(1),
                dut=dut_value,
                backend=backend_value,
                uart=uart_value,
                open_lines=open_lines_value,
                policy=ObservationPolicy(**policy_values),
                session_policy=_resolve_session_policy(document),
            )
        else:
            resolved = ResolvedInteractionProfile(
                format_version=InteractionProfileFormatVersion(2),
                dut=dut_value,
                backend=backend_value,
                uart=uart_value,
                open_lines=open_lines_value,
                policy=InteractionPolicy(**policy_values),
                session_policy=_resolve_session_policy(document),
            )
    except TypeError, ValueError:
        failure = ProfileFailure(
            ProfileFailureKind.INVALID_VALUE,
            f"a Profile value violates the version {version} schema",
        )
    else:
        return resolved
    raise failure


def _capture_profile(path: Path) -> bytes:
    source_metadata = _inspect_profile_source(path)
    if not stat.S_ISREG(source_metadata.st_mode):
        raise ProfileFailure(
            ProfileFailureKind.NOT_A_FILE,
            "the selected Profile is not a regular file",
        )

    captured = _read_profile_source(path)
    if len(captured) > _PROFILE_MAX_BYTES:
        raise ProfileFailure(
            ProfileFailureKind.INPUT_TOO_LARGE,
            "Profile input exceeds 65,536 bytes",
        )
    return captured


def _inspect_profile_source(path: Path) -> stat_result:
    try:
        return path.stat()
    except FileNotFoundError:
        failure = ProfileFailure(
            ProfileFailureKind.MISSING_FILE,
            "the selected Profile does not exist",
        )
    except (OSError, ValueError):
        failure = ProfileFailure(
            ProfileFailureKind.UNREADABLE,
            "the selected Profile cannot be inspected",
        )
    raise failure


def _read_profile_source(path: Path) -> bytes:
    try:
        with path.open("rb") as source:
            return source.read(_PROFILE_CAPTURE_LIMIT)
    except FileNotFoundError:
        failure = ProfileFailure(
            ProfileFailureKind.MISSING_FILE,
            "the selected Profile does not exist",
        )
    except IsADirectoryError:
        failure = ProfileFailure(
            ProfileFailureKind.NOT_A_FILE,
            "the selected Profile is not a regular file",
        )
    except (OSError, ValueError):
        failure = ProfileFailure(
            ProfileFailureKind.UNREADABLE,
            "the selected Profile cannot be read",
        )
    raise failure


def _parse_profile(captured: bytes) -> TomlTable:
    try:
        decoded = captured.decode("utf-8")
        return cast("TomlTable", tomllib.loads(decoded))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        failure = ProfileFailure(
            ProfileFailureKind.INVALID_SYNTAX,
            "the selected Profile is not valid UTF-8 TOML",
        )
    raise failure


def _validate_schema(
    document: TomlTable,
) -> tuple[TomlTable, TomlTable, TomlTable, TomlTable, TomlTable]:
    for table_name in _UNSUPPORTED_BEHAVIOR_TABLES:
        if table_name in document:
            raise ProfileFailure(
                ProfileFailureKind.UNSUPPORTED_BEHAVIOR,
                f"{table_name} configuration is unavailable",
            )

    _reject_unknown_fields(document, _ROOT_FIELDS, "Profile root")
    _validate_version(document)

    dut = _required_table(document, "dut", "dut")
    backend = _required_table(document, "backend", "backend")
    uart = _required_table(document, "uart", "uart")
    open_lines = _required_table(uart, "open_lines", "uart.open_lines")
    persistence = _required_table(document, "persistence", "persistence")
    policy = _optional_table(document, "policy")

    _reject_unknown_fields(dut, _DUT_FIELDS, "dut")
    _reject_unknown_fields(backend, _BACKEND_FIELDS, "backend")
    _reject_unknown_fields(uart, _UART_FIELDS, "uart")
    _reject_unknown_fields(open_lines, _OPEN_LINE_FIELDS, "uart.open_lines")
    _reject_unknown_fields(policy, _POLICY_FIELDS, "policy")
    _reject_unknown_fields(persistence, _PERSISTENCE_FIELDS, "persistence")

    _require_fields(dut, _DUT_FIELDS, "dut")
    _require_fields(backend, _BACKEND_FIELDS, "backend")
    _require_fields(uart, _UART_FIELDS, "uart")
    _require_fields(open_lines, _OPEN_LINE_FIELDS, "uart.open_lines")
    _require_fields(persistence, _PERSISTENCE_FIELDS, "persistence")
    return dut, backend, uart, open_lines, policy


def _validate_version(document: TomlTable) -> None:
    version = document.get("profile_version")
    if type(version) is not int or version not in {1, 2}:
        raise ProfileFailure(
            ProfileFailureKind.INCOMPATIBLE_VERSION,
            "Profile version 1 or 2 is required",
        )


def _required_table(
    parent: TomlTable,
    field_name: str,
    qualified_name: str,
) -> TomlTable:
    if field_name not in parent:
        raise ProfileFailure(
            ProfileFailureKind.MISSING_FIELD,
            f"{qualified_name} table is required",
        )
    value = parent[field_name]
    if not isinstance(value, dict):
        raise ProfileFailure(
            ProfileFailureKind.INVALID_VALUE,
            f"{qualified_name} must be a table",
        )
    return cast("TomlTable", value)


def _optional_table(parent: TomlTable, field_name: str) -> TomlTable:
    if field_name not in parent:
        return {}
    value = parent[field_name]
    if not isinstance(value, dict):
        raise ProfileFailure(
            ProfileFailureKind.INVALID_VALUE,
            f"{field_name} must be a table",
        )
    return cast("TomlTable", value)


def _reject_unknown_fields(
    table: TomlTable,
    allowed_fields: tuple[str, ...],
    table_name: str,
) -> None:
    unknown_fields = sorted(set(table).difference(allowed_fields))
    if unknown_fields:
        raise ProfileFailure(
            ProfileFailureKind.UNKNOWN_FIELD,
            f"{table_name}.{unknown_fields[0]} is not defined",
        )


def _require_fields(
    table: TomlTable,
    required_fields: tuple[str, ...],
    table_name: str,
) -> None:
    for field_name in required_fields:
        if field_name not in table:
            raise ProfileFailure(
                ProfileFailureKind.MISSING_FIELD,
                f"{table_name}.{field_name} is required",
            )


def _resolve_session_policy(document: TomlTable) -> SessionPolicy:
    if "persistence" not in document:
        raise ProfileFailure(
            ProfileFailureKind.MISSING_FIELD,
            "persistence table is required",
        )
    persistence_value = document["persistence"]

    if not isinstance(persistence_value, dict):
        raise ProfileFailure(
            ProfileFailureKind.INVALID_VALUE,
            "persistence must be a table",
        )
    persistence = cast("TomlTable", persistence_value)

    for field_name in _PERSISTENCE_FIELDS:
        if field_name not in persistence:
            raise ProfileFailure(
                ProfileFailureKind.MISSING_FIELD,
                f"persistence.{field_name} is required",
            )

    try:
        session_policy = SessionPolicy(
            max_retained_records=cast(
                "int", persistence["max_retained_records"]
            ),
            max_retained_charged_bytes=cast(
                "int", persistence["max_retained_charged_bytes"]
            ),
            max_record_charged_bytes=cast(
                "int", persistence["max_record_charged_bytes"]
            ),
            max_database_pages=cast("int", persistence["max_database_pages"]),
            max_retrieval_page_records=cast(
                "int", persistence["max_retrieval_page_records"]
            ),
            max_retrieval_page_charged_bytes=cast(
                "int", persistence["max_retrieval_page_charged_bytes"]
            ),
        )
    except (TypeError, ValueError):
        failure = ProfileFailure(
            ProfileFailureKind.INVALID_VALUE,
            "persistence values violate the durable session policy",
        )
    else:
        return session_policy
    raise failure
