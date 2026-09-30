"""Shared hardware-free test fixtures."""

from collections.abc import Callable, Iterable

import pytest
import serial

type BinaryPayloadFactory = Callable[[Iterable[int]], bytes]


@pytest.fixture(autouse=True)
def block_physical_serial_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail closed if a default test path reaches pySerial's real factory."""

    def fail_on_physical_serial_access(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail(
            "default tests must inject a fake serial factory; "
            "physical serial access is forbidden"
        )

    monkeypatch.setattr(serial, "Serial", fail_on_physical_serial_access)


@pytest.fixture
def binary_payload_factory() -> BinaryPayloadFactory:
    """Build binary payloads without consulting host devices or transports."""

    def build(values: Iterable[int]) -> bytes:
        return bytes(values)

    return build
