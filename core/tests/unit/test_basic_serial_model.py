"""Validated values for the receive-only Basic serial adapter."""

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from dutchmate_core.adapters.basic_serial import (
    BasicSerialConnectionProvenance,
    BasicSerialOpenRequest,
    SerialConfiguration,
    SerialDataBits,
    SerialDeviceSelector,
    SerialElectricalVerification,
    SerialExclusivityMechanism,
    SerialExclusivityProvenance,
    SerialExclusivityResult,
    SerialLineState,
    SerialOpenApplyStrategy,
    SerialOpenLineIntent,
    SerialOpenLineProvenance,
    SerialOpenTransitionGuarantee,
    SerialParity,
    SerialStopBits,
)


def _configuration(
    *,
    baud_rate: int = 115_200,
    data_bits: SerialDataBits = SerialDataBits.EIGHT,
    parity: SerialParity = SerialParity.NONE,
    stop_bits: SerialStopBits = SerialStopBits.ONE,
    hardware_flow_control: bool = False,
    software_flow_control: bool = False,
) -> SerialConfiguration:
    return SerialConfiguration(
        baud_rate=baud_rate,
        data_bits=data_bits,
        parity=parity,
        stop_bits=stop_bits,
        hardware_flow_control=hardware_flow_control,
        software_flow_control=software_flow_control,
    )


@pytest.mark.parametrize(
    "device_name",
    ["/dev/ttyUSB0", "/dev/cu.usbserial-example", "COM3", " tty device "],
)
def test_explicit_device_selector_preserves_the_exact_name(device_name: str) -> None:
    selector = SerialDeviceSelector(device_name)

    assert selector.device_name == device_name


@pytest.mark.parametrize(
    "device_name",
    ["", "   ", "7", "auto", "AUTO", "-", "loop://", "socket://host:23"],
)
def test_device_selector_rejects_implicit_or_url_like_values(
    device_name: str,
) -> None:
    with pytest.raises(ValueError):
        SerialDeviceSelector(device_name)


@pytest.mark.parametrize("baud_rate", [1, 9_600, 115_200, 1_000_000])
def test_serial_configuration_accepts_positive_baud_rates(baud_rate: int) -> None:
    assert _configuration(baud_rate=baud_rate).baud_rate == baud_rate


@pytest.mark.parametrize("baud_rate", [0, -1])
def test_serial_configuration_rejects_non_positive_baud_rates(
    baud_rate: int,
) -> None:
    with pytest.raises(ValueError, match="positive"):
        _configuration(baud_rate=baud_rate)


def test_serial_configuration_rejects_boolean_baud_rate() -> None:
    with pytest.raises(TypeError, match="integer"):
        _configuration(baud_rate=cast("int", True))


@pytest.mark.parametrize("data_bits", list(SerialDataBits))
@pytest.mark.parametrize("parity", list(SerialParity))
@pytest.mark.parametrize("stop_bits", list(SerialStopBits))
def test_serial_configuration_accepts_the_supported_framing_values(
    data_bits: SerialDataBits,
    parity: SerialParity,
    stop_bits: SerialStopBits,
) -> None:
    configuration = _configuration(
        data_bits=data_bits,
        parity=parity,
        stop_bits=stop_bits,
    )

    assert configuration.data_bits is data_bits
    assert configuration.parity is parity
    assert configuration.stop_bits is stop_bits


def test_serial_configuration_rejects_undeclared_framing_values() -> None:
    with pytest.raises(TypeError, match="data bits"):
        _configuration(data_bits=cast("SerialDataBits", 9))
    with pytest.raises(TypeError, match="parity"):
        _configuration(parity=cast("SerialParity", "mark"))
    with pytest.raises(TypeError, match="stop bits"):
        _configuration(stop_bits=cast("SerialStopBits", "one_and_a_half"))


def test_serial_configuration_rejects_simultaneous_flow_control() -> None:
    with pytest.raises(ValueError, match="simultaneous"):
        _configuration(
            hardware_flow_control=True,
            software_flow_control=True,
        )


@pytest.mark.parametrize(
    ("hardware_flow_control", "rts"),
    [
        (False, SerialLineState.ASSERTED),
        (False, SerialLineState.DEASSERTED),
        (True, SerialLineState.DRIVER_MANAGED),
    ],
)
def test_open_request_accepts_rts_intent_matching_flow_control(
    hardware_flow_control: bool,
    rts: SerialLineState,
) -> None:
    request = BasicSerialOpenRequest(
        selector=SerialDeviceSelector("/dev/ttyUSB0"),
        configuration=_configuration(
            hardware_flow_control=hardware_flow_control,
        ),
        line_intent=SerialOpenLineIntent(
            dtr=SerialLineState.DEASSERTED,
            rts=rts,
        ),
    )

    assert request.line_intent.rts is rts


@pytest.mark.parametrize(
    ("hardware_flow_control", "rts"),
    [
        (False, SerialLineState.DRIVER_MANAGED),
        (True, SerialLineState.ASSERTED),
        (True, SerialLineState.DEASSERTED),
    ],
)
def test_open_request_rejects_rts_intent_not_matching_flow_control(
    hardware_flow_control: bool,
    rts: SerialLineState,
) -> None:
    with pytest.raises(ValueError, match="driver-managed"):
        BasicSerialOpenRequest(
            selector=SerialDeviceSelector("/dev/ttyUSB0"),
            configuration=_configuration(
                hardware_flow_control=hardware_flow_control,
            ),
            line_intent=SerialOpenLineIntent(
                dtr=SerialLineState.DEASSERTED,
                rts=rts,
            ),
        )


def test_dtr_intent_cannot_be_driver_managed() -> None:
    with pytest.raises(ValueError, match="DTR"):
        SerialOpenLineIntent(
            dtr=SerialLineState.DRIVER_MANAGED,
            rts=SerialLineState.DEASSERTED,
        )


def test_basic_connection_provenance_is_an_immutable_snapshot() -> None:
    configuration = _configuration()
    line_intent = SerialOpenLineIntent(
        dtr=SerialLineState.DEASSERTED,
        rts=SerialLineState.DEASSERTED,
    )
    provenance = BasicSerialConnectionProvenance(
        selected_device_name="/dev/ttyUSB0",
        opened_device_name="/dev/ttyUSB0",
        requested_configuration=configuration,
        effective_configuration=configuration,
        open_line_provenance=SerialOpenLineProvenance(
            requested=line_intent,
            apply_strategy=SerialOpenApplyStrategy.PRECONFIGURED_WHILE_CLOSED,
            library_reported_dtr=SerialLineState.DEASSERTED,
            library_reported_rts=SerialLineState.DEASSERTED,
            transition_guarantee=SerialOpenTransitionGuarantee.NOT_GUARANTEED,
            electrical_verification=SerialElectricalVerification.NOT_VERIFIED,
        ),
        exclusivity=SerialExclusivityProvenance(
            requested=True,
            mechanism=SerialExclusivityMechanism.POSIX_PYSERIAL_EXCLUSIVE,
            result=SerialExclusivityResult.OPEN_SUCCEEDED_WITH_REQUESTED_MECHANISM,
        ),
    )

    assert provenance.requested_configuration is configuration
    assert provenance.effective_configuration is configuration
    with pytest.raises(FrozenInstanceError):
        provenance.opened_device_name = "/dev/other"  # type: ignore[misc]
