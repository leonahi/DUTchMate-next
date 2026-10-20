"""Basic serial adapter translation for resolved DUT Profiles."""

from dutchmate_core.adapters.basic_serial import (
    BasicSerialOpenRequest,
    SerialConfiguration,
    SerialDataBits,
    SerialDeviceSelector,
    SerialLineState,
    SerialOpenLineIntent,
    SerialParity,
    SerialStopBits,
)
from dutchmate_core.profile import ResolvedProfile


def to_basic_serial_open_request(
    resolved_profile: ResolvedProfile,
) -> BasicSerialOpenRequest:
    """Translate one resolved Basic Profile into its serial-open request."""

    if resolved_profile.backend.kind != "basic_serial":
        raise ValueError("resolved Profile does not select the Basic backend")

    return BasicSerialOpenRequest(
        selector=SerialDeviceSelector(resolved_profile.backend.expected_device),
        configuration=SerialConfiguration(
            baud_rate=resolved_profile.uart.baud_rate,
            data_bits=SerialDataBits(resolved_profile.uart.data_bits),
            parity=SerialParity(resolved_profile.uart.parity),
            stop_bits={
                1: SerialStopBits.ONE,
                2: SerialStopBits.TWO,
            }[resolved_profile.uart.stop_bits],
            hardware_flow_control=(
                resolved_profile.uart.hardware_flow_control
            ),
            software_flow_control=(
                resolved_profile.uart.software_flow_control
            ),
        ),
        line_intent=SerialOpenLineIntent(
            dtr=SerialLineState(resolved_profile.open_lines.dtr),
            rts=SerialLineState(resolved_profile.open_lines.rts),
        ),
    )
