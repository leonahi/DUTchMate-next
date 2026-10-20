"""Contracts for immutable DUT Profile domain values."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from typing import Any, cast

import pytest

import dutchmate_core
from dutchmate_core import model, profile


def test_t016_root_package_exports_only_generic_profile_symbols() -> None:
    expected_exports = {
        "DutIdentity",
        "ObservationPolicy",
        "ProfileBackendSelection",
        "ProfileFailure",
        "ProfileFailureKind",
        "ProfileFormatVersion",
        "ProfileSerialOpenLineIntent",
        "ProfileUartConfiguration",
        "ResolvedDutProfile",
    }

    assert set(dutchmate_core.__all__) == expected_exports
    for symbol_name in expected_exports:
        assert vars(dutchmate_core)[symbol_name] is vars(profile)[symbol_name]


def _assert_unsupported_behavior(action: Callable[[], object]) -> None:
    try:
        action()
    except Exception as failure:
        assert type(failure).__name__ == "ProfileFailure"
        assert getattr(failure, "kind", None) == "unsupported_behavior"
    else:
        pytest.fail("unsafe Profile policy must be rejected")


def _session_policy() -> model.SessionPolicy:
    return model.SessionPolicy(
        max_retained_records=10_000,
        max_retained_charged_bytes=8_388_608,
        max_record_charged_bytes=65_536,
        max_database_pages=4_096,
        max_retrieval_page_records=256,
        max_retrieval_page_charged_bytes=262_144,
    )


def _resolved_profile(
    *,
    hardware_flow_control: bool = False,
    rts: str = "deasserted",
) -> profile.ResolvedDutProfile:
    return profile.ResolvedDutProfile(
        format_version=profile.ProfileFormatVersion(1),
        dut=profile.DutIdentity(id="board/opaque:17", name="Board A"),
        backend=profile.ProfileBackendSelection(
            kind="basic_serial",
            expected_device="/dev/ttyUSB0",
        ),
        uart=profile.ProfileUartConfiguration(
            baud_rate=115_200,
            data_bits=8,
            parity="none",
            stop_bits=1,
            hardware_flow_control=hardware_flow_control,
            software_flow_control=False,
        ),
        open_lines=profile.ProfileSerialOpenLineIntent(
            dtr="deasserted",
            rts=rts,
        ),
        policy=profile.ObservationPolicy(
            uart_rx_enabled=True,
            evidence_recording_enabled=True,
            uart_tx_enabled=False,
            semantic_control_enabled=False,
            automatic_reconnect_enabled=False,
        ),
        session_policy=_session_policy(),
    )


def test_profile_format_version_accepts_only_integer_one() -> None:
    version = profile.ProfileFormatVersion(1)

    assert version.value == 1
    with pytest.raises(TypeError, match="integer"):
        profile.ProfileFormatVersion(cast("int", True))
    with pytest.raises(ValueError, match="version 1"):
        profile.ProfileFormatVersion(2)


@pytest.mark.parametrize("value", ["", "   "])
def test_dut_identity_rejects_empty_or_whitespace_values(value: str) -> None:
    with pytest.raises(ValueError, match="identity"):
        profile.DutIdentity(id=value, name="Board A")
    with pytest.raises(ValueError, match="name"):
        profile.DutIdentity(id="board-a", name=value)


def test_dut_identity_and_backend_selection_preserve_exact_text() -> None:
    dut = profile.DutIdentity(id=" board/opaque:17 ", name=" Board A ")
    backend = profile.ProfileBackendSelection(
        kind="basic_serial",
        expected_device=" /dev/ttyUSB0 ",
    )

    assert dut.id == " board/opaque:17 "
    assert dut.name == " Board A "
    assert backend.kind == "basic_serial"
    assert backend.expected_device == " /dev/ttyUSB0 "


@pytest.mark.parametrize("baud_rate", [1, 9_600, 115_200, 1_000_000])
def test_profile_uart_accepts_positive_baud_rates(baud_rate: int) -> None:
    uart = profile.ProfileUartConfiguration(
        baud_rate=baud_rate,
        data_bits=8,
        parity="none",
        stop_bits=1,
        hardware_flow_control=False,
        software_flow_control=False,
    )

    assert uart.baud_rate == baud_rate


@pytest.mark.parametrize("baud_rate", [0, -1])
def test_profile_uart_rejects_non_positive_baud_rates(baud_rate: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        profile.ProfileUartConfiguration(
            baud_rate=baud_rate,
            data_bits=8,
            parity="none",
            stop_bits=1,
            hardware_flow_control=False,
            software_flow_control=False,
        )


def test_profile_uart_rejects_boolean_baud_rate() -> None:
    with pytest.raises(TypeError, match="integer"):
        profile.ProfileUartConfiguration(
            baud_rate=cast("int", True),
            data_bits=8,
            parity="none",
            stop_bits=1,
            hardware_flow_control=False,
            software_flow_control=False,
        )


@pytest.mark.parametrize("data_bits", [5, 6, 7, 8])
@pytest.mark.parametrize("parity", ["none", "even", "odd"])
@pytest.mark.parametrize("stop_bits", [1, 2])
def test_profile_uart_accepts_supported_framing(
    data_bits: int,
    parity: str,
    stop_bits: int,
) -> None:
    uart = profile.ProfileUartConfiguration(
        baud_rate=115_200,
        data_bits=data_bits,
        parity=parity,
        stop_bits=stop_bits,
        hardware_flow_control=False,
        software_flow_control=False,
    )

    assert (uart.data_bits, uart.parity, uart.stop_bits) == (
        data_bits,
        parity,
        stop_bits,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("data_bits", 9), ("parity", "mark"), ("stop_bits", 3)],
)
def test_profile_uart_rejects_unsupported_framing(
    field: str,
    value: int | str,
) -> None:
    values: dict[str, object] = {
        "baud_rate": 115_200,
        "data_bits": 8,
        "parity": "none",
        "stop_bits": 1,
        "hardware_flow_control": False,
        "software_flow_control": False,
    }
    values[field] = value

    with pytest.raises(ValueError, match=field.replace("_", " ")):
        profile.ProfileUartConfiguration(**values)  # type: ignore[arg-type]


def test_profile_uart_rejects_simultaneous_flow_control() -> None:
    with pytest.raises(ValueError, match="simultaneous"):
        profile.ProfileUartConfiguration(
            baud_rate=115_200,
            data_bits=8,
            parity="none",
            stop_bits=1,
            hardware_flow_control=True,
            software_flow_control=True,
        )


def test_profile_open_lines_reject_driver_managed_dtr() -> None:
    with pytest.raises(ValueError, match="DTR"):
        profile.ProfileSerialOpenLineIntent(
            dtr="driver_managed",
            rts="deasserted",
        )


@pytest.mark.parametrize(
    ("hardware_flow_control", "rts"),
    [(False, "driver_managed"), (True, "asserted"), (True, "deasserted")],
)
def test_resolved_profile_requires_rts_to_match_hardware_flow_control(
    hardware_flow_control: bool,
    rts: str,
) -> None:
    with pytest.raises(ValueError, match="driver-managed"):
        _resolved_profile(
            hardware_flow_control=hardware_flow_control,
            rts=rts,
        )


@pytest.mark.parametrize(
    ("hardware_flow_control", "rts"),
    [(False, "asserted"), (False, "deasserted"), (True, "driver_managed")],
)
def test_resolved_profile_accepts_coherent_rts_intent(
    hardware_flow_control: bool,
    rts: str,
) -> None:
    resolved = _resolved_profile(
        hardware_flow_control=hardware_flow_control,
        rts=rts,
    )

    assert resolved.open_lines.rts == rts


def test_resolved_profile_is_an_immutable_generic_snapshot() -> None:
    resolved = _resolved_profile()

    assert resolved.policy == profile.ObservationPolicy(
        uart_rx_enabled=True,
        evidence_recording_enabled=True,
        uart_tx_enabled=False,
        semantic_control_enabled=False,
        automatic_reconnect_enabled=False,
    )
    assert resolved.session_policy == _session_policy()
    with pytest.raises(FrozenInstanceError):
        resolved.dut = profile.DutIdentity("other", "Other")  # type: ignore[misc]


class TestT007ObservationPolicy:
    def test_omitted_policy_values_default_to_observation_only(self) -> None:
        policy_factory = cast(
            "Callable[[], profile.ObservationPolicy]",
            profile.ObservationPolicy,
        )
        policy = policy_factory()

        assert (
            policy.uart_rx_enabled,
            policy.evidence_recording_enabled,
            policy.uart_tx_enabled,
            policy.semantic_control_enabled,
            policy.automatic_reconnect_enabled,
        ) == (True, True, False, False, False)

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
    def test_opposite_observation_or_permission_value_is_unsupported(
        self,
        field_name: str,
        opposite_value: bool,
    ) -> None:
        values = {
            "uart_rx_enabled": True,
            "evidence_recording_enabled": True,
            "uart_tx_enabled": False,
            "semantic_control_enabled": False,
            "automatic_reconnect_enabled": False,
        }
        values[field_name] = opposite_value

        _assert_unsupported_behavior(lambda: profile.ObservationPolicy(**values))


def _interaction_policy_type() -> Any:
    policy_type = getattr(profile, "InteractionPolicy", None)
    assert policy_type is not None, "T006: immutable InteractionPolicy is missing"
    return policy_type


class TestT006InteractionPolicy:
    """012 adds a distinct policy without relaxing any v1 constructor."""

    @pytest.mark.parametrize("tx_enabled", [False, True])
    def test_only_explicit_tx_permission_changes_the_safe_defaults(
        self, tx_enabled: bool
    ) -> None:
        policy_type = _interaction_policy_type()
        policy_value = policy_type(uart_tx_enabled=tx_enabled)

        assert not isinstance(policy_value, profile.ObservationPolicy)
        assert (
            policy_value.uart_rx_enabled,
            policy_value.evidence_recording_enabled,
            policy_value.uart_tx_enabled,
            policy_value.semantic_control_enabled,
            policy_value.automatic_reconnect_enabled,
        ) == (True, True, tx_enabled, False, False)
        assert policy_type().uart_tx_enabled is False
        with pytest.raises(FrozenInstanceError):
            policy_value.uart_tx_enabled = not tx_enabled

    @pytest.mark.parametrize(
        "field_name",
        [
            "uart_rx_enabled",
            "evidence_recording_enabled",
            "uart_tx_enabled",
            "semantic_control_enabled",
            "automatic_reconnect_enabled",
        ],
    )
    @pytest.mark.parametrize("value", [None, 0, 1, "true", b"false", 1.0])
    def test_every_policy_value_requires_an_exact_boolean(
        self, field_name: str, value: object
    ) -> None:
        policy_type = _interaction_policy_type()
        with pytest.raises(TypeError):
            policy_type(**{field_name: value})

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("uart_rx_enabled", False),
            ("evidence_recording_enabled", False),
            ("semantic_control_enabled", True),
            ("automatic_reconnect_enabled", True),
        ],
    )
    @pytest.mark.parametrize("tx_enabled", [False, True])
    def test_rx_and_recording_are_mandatory_and_other_actions_unavailable(
        self, field_name: str, value: bool, tx_enabled: bool
    ) -> None:
        policy_type = _interaction_policy_type()
        _assert_unsupported_behavior(
            lambda: policy_type(uart_tx_enabled=tx_enabled, **{field_name: value})
        )

    def test_no_new_permission_or_control_mapping_fields(self) -> None:
        policy_type = _interaction_policy_type()
        with pytest.raises(TypeError):
            policy_type(control_mappings={})

    def test_v1_values_stay_strict_after_v2_construction(self) -> None:
        policy_value = _interaction_policy_type()(uart_tx_enabled=True)

        assert profile.ObservationPolicy().uart_tx_enabled is False
        _assert_unsupported_behavior(
            lambda: profile.ObservationPolicy(uart_tx_enabled=True)
        )
        with pytest.raises(ValueError):
            profile.ProfileFormatVersion(2)
        with pytest.raises(TypeError):
            replace(_resolved_profile(), policy=policy_value)
