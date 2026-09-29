"""Shared hardware-free test fixtures."""

from collections.abc import Callable, Iterable

import pytest

type BinaryPayloadFactory = Callable[[Iterable[int]], bytes]


@pytest.fixture
def binary_payload_factory() -> BinaryPayloadFactory:
    """Build binary payloads without consulting host devices or transports."""

    def build(values: Iterable[int]) -> bytes:
        return bytes(values)

    return build
