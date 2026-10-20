"""Immutable backend-neutral DUT Profile domain values."""

from dataclasses import dataclass
from enum import StrEnum

from dutchmate_core.model import SessionPolicy


class ProfileFailureKind(StrEnum):
    """Stable Profile-boundary failure categories."""

    MISSING_FILE = "missing_file"
    NOT_A_FILE = "not_a_file"
    UNREADABLE = "unreadable"
    INPUT_TOO_LARGE = "input_too_large"
    INVALID_SYNTAX = "invalid_syntax"
    INCOMPATIBLE_VERSION = "incompatible_version"
    MISSING_FIELD = "missing_field"
    UNKNOWN_FIELD = "unknown_field"
    INVALID_VALUE = "invalid_value"
    UNSUPPORTED_BACKEND = "unsupported_backend"
    UNSUPPORTED_BEHAVIOR = "unsupported_behavior"


@dataclass(frozen=True, slots=True)
class ProfileFailure(RuntimeError):
    """Normalized Profile failure without adapter exception leakage."""

    kind: ProfileFailureKind
    detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ProfileFailureKind):
            raise TypeError("Profile failure kind must be declared")
        if self.detail is not None and not isinstance(self.detail, str):
            raise TypeError("Profile failure detail must be text or absent")
        message = self.kind.value
        if self.detail:
            message = f"{message}: {self.detail}"
        RuntimeError.__init__(self, message)


@dataclass(frozen=True, slots=True)
class ProfileFormatVersion:
    """Version discriminator for the human-authored Profile format."""

    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int:
            raise TypeError("Profile format version must be an integer")
        if self.value != 1:
            raise ValueError("only Profile format version 1 is supported")


@dataclass(frozen=True, slots=True)
class DutIdentity:
    """Opaque DUT identity and human-readable name."""

    id: str
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("DUT identity must be non-empty text")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("DUT name must be non-empty text")


@dataclass(frozen=True, slots=True)
class ProfileBackendSelection:
    """Explicit backend kind and exact expected local device name."""

    kind: str
    expected_device: str

    def __post_init__(self) -> None:
        if self.kind != "basic_serial":
            raise ValueError("Profile backend kind must be basic_serial")
        if not isinstance(self.expected_device, str) or not self.expected_device.strip():
            raise ValueError("expected serial device must be non-empty text")
        candidate = self.expected_device.strip()
        if (
            candidate.isdecimal()
            or candidate.casefold() == "auto"
            or candidate == "-"
            or "://" in candidate
        ):
            raise ValueError("expected serial device must be an exact local name")


@dataclass(frozen=True, slots=True)
class ProfileUartConfiguration:
    """Backend-neutral requested UART settings."""

    baud_rate: int
    data_bits: int
    parity: str
    stop_bits: int
    hardware_flow_control: bool
    software_flow_control: bool

    def __post_init__(self) -> None:
        if type(self.baud_rate) is not int:
            raise TypeError("UART baud rate must be an integer")
        if self.baud_rate <= 0:
            raise ValueError("UART baud rate must be positive")
        if type(self.data_bits) is not int or self.data_bits not in {5, 6, 7, 8}:
            raise ValueError("UART data bits must be 5, 6, 7, or 8")
        if not isinstance(self.parity, str) or self.parity not in {
            "none",
            "even",
            "odd",
        }:
            raise ValueError("UART parity must be none, even, or odd")
        if type(self.stop_bits) is not int or self.stop_bits not in {1, 2}:
            raise ValueError("UART stop bits must be 1 or 2")
        if type(self.hardware_flow_control) is not bool:
            raise TypeError("hardware flow control must be boolean")
        if type(self.software_flow_control) is not bool:
            raise TypeError("software flow control must be boolean")
        if self.hardware_flow_control and self.software_flow_control:
            raise ValueError("simultaneous hardware and software flow control")


@dataclass(frozen=True, slots=True)
class ProfileSerialOpenLineIntent:
    """DTR/RTS intent applied by a later backend construction boundary."""

    dtr: str
    rts: str

    def __post_init__(self) -> None:
        if not isinstance(self.dtr, str) or self.dtr not in {
            "asserted",
            "deasserted",
        }:
            raise ValueError("DTR intent must be asserted or deasserted")
        if not isinstance(self.rts, str) or self.rts not in {
            "asserted",
            "deasserted",
            "driver_managed",
        }:
            raise ValueError(
                "RTS intent must be asserted, deasserted, or driver_managed"
            )


@dataclass(frozen=True, slots=True)
class ObservationPolicy:
    """Immutable current observation invariants and future permissions."""

    uart_rx_enabled: bool = True
    evidence_recording_enabled: bool = True
    uart_tx_enabled: bool = False
    semantic_control_enabled: bool = False
    automatic_reconnect_enabled: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "uart_rx_enabled",
            "evidence_recording_enabled",
            "uart_tx_enabled",
            "semantic_control_enabled",
            "automatic_reconnect_enabled",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name.replace('_', ' ')} must be boolean")

        if not self.uart_rx_enabled:
            raise ProfileFailure(
                ProfileFailureKind.UNSUPPORTED_BEHAVIOR,
                "UART RX is mandatory for Profile version 1",
            )
        if not self.evidence_recording_enabled:
            raise ProfileFailure(
                ProfileFailureKind.UNSUPPORTED_BEHAVIOR,
                "evidence recording is mandatory for Profile version 1",
            )
        if self.uart_tx_enabled:
            raise ProfileFailure(
                ProfileFailureKind.UNSUPPORTED_BEHAVIOR,
                "UART TX is unavailable in Profile version 1",
            )
        if self.semantic_control_enabled:
            raise ProfileFailure(
                ProfileFailureKind.UNSUPPORTED_BEHAVIOR,
                "semantic Control is unavailable in Profile version 1",
            )
        if self.automatic_reconnect_enabled:
            raise ProfileFailure(
                ProfileFailureKind.UNSUPPORTED_BEHAVIOR,
                "automatic reconnect is unavailable in Profile version 1",
            )


@dataclass(frozen=True, slots=True)
class ResolvedDutProfile:
    """Immutable validated snapshot suitable for later composition."""

    format_version: ProfileFormatVersion
    dut: DutIdentity
    backend: ProfileBackendSelection
    uart: ProfileUartConfiguration
    open_lines: ProfileSerialOpenLineIntent
    policy: ObservationPolicy
    session_policy: SessionPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.format_version, ProfileFormatVersion):
            raise TypeError("Profile format version must be validated")
        if not isinstance(self.dut, DutIdentity):
            raise TypeError("DUT identity must be validated")
        if not isinstance(self.backend, ProfileBackendSelection):
            raise TypeError("Profile backend selection must be validated")
        if not isinstance(self.uart, ProfileUartConfiguration):
            raise TypeError("Profile UART configuration must be validated")
        if not isinstance(self.open_lines, ProfileSerialOpenLineIntent):
            raise TypeError("Profile serial-open line intent must be validated")
        if not isinstance(self.policy, ObservationPolicy):
            raise TypeError("Profile observation policy must be validated")
        if not isinstance(self.session_policy, SessionPolicy):
            raise TypeError("Profile session policy must be validated")
        rts_is_driver_managed = self.open_lines.rts == "driver_managed"
        if rts_is_driver_managed != self.uart.hardware_flow_control:
            raise ValueError(
                "RTS must be driver-managed exactly when hardware flow control "
                "is enabled"
            )

@dataclass(frozen=True, slots=True)
class InteractionProfileFormatVersion:
    """Separate discriminator for the additive Profile-v2 contract."""

    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int:
            raise TypeError("Profile format version must be an integer")
        if self.value != 2:
            raise ValueError("only Profile format version 2 is supported")


@dataclass(frozen=True, slots=True)
class InteractionPolicy:
    """Profile-v2 permission; backend capability is checked independently."""

    uart_rx_enabled: bool = True
    evidence_recording_enabled: bool = True
    uart_tx_enabled: bool = False
    semantic_control_enabled: bool = False
    automatic_reconnect_enabled: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "uart_rx_enabled",
            "evidence_recording_enabled",
            "uart_tx_enabled",
            "semantic_control_enabled",
            "automatic_reconnect_enabled",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name.replace('_', ' ')} must be boolean")

        if not self.uart_rx_enabled:
            raise ProfileFailure(
                ProfileFailureKind.UNSUPPORTED_BEHAVIOR,
                "UART RX is mandatory for Profile version 2",
            )
        if not self.evidence_recording_enabled:
            raise ProfileFailure(
                ProfileFailureKind.UNSUPPORTED_BEHAVIOR,
                "evidence recording is mandatory for Profile version 2",
            )
        if self.semantic_control_enabled:
            raise ProfileFailure(
                ProfileFailureKind.UNSUPPORTED_BEHAVIOR,
                "semantic Control is unavailable in Profile version 2",
            )
        if self.automatic_reconnect_enabled:
            raise ProfileFailure(
                ProfileFailureKind.UNSUPPORTED_BEHAVIOR,
                "automatic reconnect is unavailable in Profile version 2",
            )


@dataclass(frozen=True, slots=True)
class ResolvedInteractionProfile:
    """Immutable validated v2 snapshot, distinct from observation-only v1."""

    format_version: InteractionProfileFormatVersion
    dut: DutIdentity
    backend: ProfileBackendSelection
    uart: ProfileUartConfiguration
    open_lines: ProfileSerialOpenLineIntent
    policy: InteractionPolicy
    session_policy: SessionPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.format_version, InteractionProfileFormatVersion):
            raise TypeError("Profile format version must be validated")
        if not isinstance(self.dut, DutIdentity):
            raise TypeError("DUT identity must be validated")
        if not isinstance(self.backend, ProfileBackendSelection):
            raise TypeError("Profile backend selection must be validated")
        if not isinstance(self.uart, ProfileUartConfiguration):
            raise TypeError("Profile UART configuration must be validated")
        if not isinstance(self.open_lines, ProfileSerialOpenLineIntent):
            raise TypeError("Profile serial-open line intent must be validated")
        if not isinstance(self.policy, InteractionPolicy):
            raise TypeError("Profile interaction policy must be validated")
        if not isinstance(self.session_policy, SessionPolicy):
            raise TypeError("Profile session policy must be validated")
        rts_is_driver_managed = self.open_lines.rts == "driver_managed"
        if rts_is_driver_managed != self.uart.hardware_flow_control:
            raise ValueError(
                "RTS must be driver-managed exactly when hardware flow control "
                "is enabled"
            )


type ResolvedProfile = ResolvedDutProfile | ResolvedInteractionProfile
