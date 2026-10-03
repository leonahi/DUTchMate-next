"""Contract tests for Basic adapter Profile translation."""

from collections.abc import Callable
from typing import NoReturn, cast

import pytest
import serial

import dutchmate_core.adapters as adapters
from dutchmate_core import model, profile
from dutchmate_core.adapters import basic_profile, basic_serial, toml_profile


def test_t016_adapter_package_exports_only_profile_entry_points() -> None:
    assert set(adapters.__all__) == {
        "resolve_profile",
        "to_basic_serial_open_request",
    }
    assert adapters.resolve_profile is toml_profile.resolve_profile
    assert (
        adapters.to_basic_serial_open_request
        is basic_profile.to_basic_serial_open_request
    )


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
    uart: profile.ProfileUartConfiguration,
    open_lines: profile.ProfileSerialOpenLineIntent,
) -> profile.ResolvedDutProfile:
    return profile.ResolvedDutProfile(
        format_version=profile.ProfileFormatVersion(1),
        dut=profile.DutIdentity("board/opaque:17", "Board A"),
        backend=profile.ProfileBackendSelection(
            kind="basic_serial",
            expected_device=" /dev/tty-profile ",
        ),
        uart=uart,
        open_lines=open_lines,
        policy=profile.ObservationPolicy(),
        session_policy=_session_policy(),
    )


def _translate(
    resolved: profile.ResolvedDutProfile,
) -> basic_serial.BasicSerialOpenRequest:
    translator = cast(
        "Callable[[profile.ResolvedDutProfile], "
        "basic_serial.BasicSerialOpenRequest]",
        vars(basic_profile)["to_basic_serial_open_request"],
    )
    return translator(resolved)


def _fail_on_hardware(*args: object, **kwargs: object) -> NoReturn:
    del args, kwargs
    pytest.fail("Profile translation must not inspect or open serial hardware")


@pytest.fixture(autouse=True)
def block_basic_translation_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    targets: tuple[tuple[object, str], ...] = (
        (serial, "Serial"),
        (basic_serial, "BasicSerialBackend"),
    )
    for target, attribute in targets:
        monkeypatch.setattr(target, attribute, _fail_on_hardware)


@pytest.mark.parametrize(
    ("uart", "open_lines", "expected_configuration", "expected_line_intent"),
    [
        pytest.param(
            profile.ProfileUartConfiguration(
                baud_rate=9_600,
                data_bits=5,
                parity="none",
                stop_bits=1,
                hardware_flow_control=False,
                software_flow_control=False,
            ),
            profile.ProfileSerialOpenLineIntent(
                dtr="asserted",
                rts="asserted",
            ),
            basic_serial.SerialConfiguration(
                baud_rate=9_600,
                data_bits=basic_serial.SerialDataBits.FIVE,
                parity=basic_serial.SerialParity.NONE,
                stop_bits=basic_serial.SerialStopBits.ONE,
                hardware_flow_control=False,
                software_flow_control=False,
            ),
            basic_serial.SerialOpenLineIntent(
                dtr=basic_serial.SerialLineState.ASSERTED,
                rts=basic_serial.SerialLineState.ASSERTED,
            ),
            id="five-none-one-static-asserted",
        ),
        pytest.param(
            profile.ProfileUartConfiguration(
                baud_rate=19_200,
                data_bits=6,
                parity="even",
                stop_bits=2,
                hardware_flow_control=False,
                software_flow_control=False,
            ),
            profile.ProfileSerialOpenLineIntent(
                dtr="deasserted",
                rts="deasserted",
            ),
            basic_serial.SerialConfiguration(
                baud_rate=19_200,
                data_bits=basic_serial.SerialDataBits.SIX,
                parity=basic_serial.SerialParity.EVEN,
                stop_bits=basic_serial.SerialStopBits.TWO,
                hardware_flow_control=False,
                software_flow_control=False,
            ),
            basic_serial.SerialOpenLineIntent(
                dtr=basic_serial.SerialLineState.DEASSERTED,
                rts=basic_serial.SerialLineState.DEASSERTED,
            ),
            id="six-even-two-static-deasserted",
        ),
        pytest.param(
            profile.ProfileUartConfiguration(
                baud_rate=38_400,
                data_bits=7,
                parity="odd",
                stop_bits=1,
                hardware_flow_control=False,
                software_flow_control=True,
            ),
            profile.ProfileSerialOpenLineIntent(
                dtr="asserted",
                rts="asserted",
            ),
            basic_serial.SerialConfiguration(
                baud_rate=38_400,
                data_bits=basic_serial.SerialDataBits.SEVEN,
                parity=basic_serial.SerialParity.ODD,
                stop_bits=basic_serial.SerialStopBits.ONE,
                hardware_flow_control=False,
                software_flow_control=True,
            ),
            basic_serial.SerialOpenLineIntent(
                dtr=basic_serial.SerialLineState.ASSERTED,
                rts=basic_serial.SerialLineState.ASSERTED,
            ),
            id="seven-odd-one-software-flow",
        ),
        pytest.param(
            profile.ProfileUartConfiguration(
                baud_rate=115_200,
                data_bits=8,
                parity="none",
                stop_bits=2,
                hardware_flow_control=False,
                software_flow_control=True,
            ),
            profile.ProfileSerialOpenLineIntent(
                dtr="deasserted",
                rts="deasserted",
            ),
            basic_serial.SerialConfiguration(
                baud_rate=115_200,
                data_bits=basic_serial.SerialDataBits.EIGHT,
                parity=basic_serial.SerialParity.NONE,
                stop_bits=basic_serial.SerialStopBits.TWO,
                hardware_flow_control=False,
                software_flow_control=True,
            ),
            basic_serial.SerialOpenLineIntent(
                dtr=basic_serial.SerialLineState.DEASSERTED,
                rts=basic_serial.SerialLineState.DEASSERTED,
            ),
            id="eight-none-two-software-flow-static-rts",
        ),
        pytest.param(
            profile.ProfileUartConfiguration(
                baud_rate=1_000_000,
                data_bits=5,
                parity="even",
                stop_bits=1,
                hardware_flow_control=True,
                software_flow_control=False,
            ),
            profile.ProfileSerialOpenLineIntent(
                dtr="asserted",
                rts="driver_managed",
            ),
            basic_serial.SerialConfiguration(
                baud_rate=1_000_000,
                data_bits=basic_serial.SerialDataBits.FIVE,
                parity=basic_serial.SerialParity.EVEN,
                stop_bits=basic_serial.SerialStopBits.ONE,
                hardware_flow_control=True,
                software_flow_control=False,
            ),
            basic_serial.SerialOpenLineIntent(
                dtr=basic_serial.SerialLineState.ASSERTED,
                rts=basic_serial.SerialLineState.DRIVER_MANAGED,
            ),
            id="hardware-flow-driver-managed-rts",
        ),
    ],
)
def test_t013_maps_every_profile_field_to_exact_basic_request_values(
    uart: profile.ProfileUartConfiguration,
    open_lines: profile.ProfileSerialOpenLineIntent,
    expected_configuration: basic_serial.SerialConfiguration,
    expected_line_intent: basic_serial.SerialOpenLineIntent,
) -> None:
    resolved = _resolved_profile(uart, open_lines)
    expected_selector = basic_serial.SerialDeviceSelector(" /dev/tty-profile ")
    expected_request = basic_serial.BasicSerialOpenRequest(
        selector=expected_selector,
        configuration=expected_configuration,
        line_intent=expected_line_intent,
    )

    request = _translate(resolved)

    assert type(request) is basic_serial.BasicSerialOpenRequest
    assert type(request.selector) is basic_serial.SerialDeviceSelector
    assert type(request.configuration) is basic_serial.SerialConfiguration
    assert type(request.line_intent) is basic_serial.SerialOpenLineIntent
    assert request == expected_request


def test_t013_defensively_rejects_non_basic_resolved_selection() -> None:
    resolved = _resolved_profile(
        profile.ProfileUartConfiguration(
            baud_rate=115_200,
            data_bits=8,
            parity="none",
            stop_bits=1,
            hardware_flow_control=False,
            software_flow_control=False,
        ),
        profile.ProfileSerialOpenLineIntent(
            dtr="deasserted",
            rts="asserted",
        ),
    )
    object.__setattr__(resolved.backend, "kind", "enhanced")

    with pytest.raises(ValueError):
        _translate(resolved)
