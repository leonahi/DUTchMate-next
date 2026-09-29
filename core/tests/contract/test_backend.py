"""Contract tests for one owned normalized backend connection."""

import pytest

from dutchmate_core.backend import EventStreamAlreadyConsumedError
from dutchmate_core.model import Disconnected, RxBytesObserved
from tests.fakes import BACKEND_FIXTURE_FACTORIES, BackendFixtureFactory


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_connection_event_stream_has_exactly_one_consumer(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    first_stream = connection.events()

    with pytest.raises(EventStreamAlreadyConsumedError):
        connection.events()

    await connection.close()
    assert [event async for event in first_stream] == []


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_disconnect_is_the_last_observation_in_stream_order(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    await connection.emit_rx(b"before-disconnect", timestamp=10)
    await connection.disconnect("fixture unplugged")

    events = [event async for event in connection.events()]

    assert [type(event) for event in events] == [RxBytesObserved, Disconnected]
    disconnected = events[1]
    assert isinstance(disconnected, Disconnected)
    assert disconnected.reason == "fixture unplugged"


@pytest.mark.parametrize("fixture_factory", BACKEND_FIXTURE_FACTORIES)
@pytest.mark.asyncio
async def test_close_is_idempotent_and_terminates_the_stream(
    fixture_factory: BackendFixtureFactory,
) -> None:
    fixture = fixture_factory()
    connection = fixture.connection
    stream = connection.events()

    await connection.close()
    await connection.close()

    assert [event async for event in stream] == []
