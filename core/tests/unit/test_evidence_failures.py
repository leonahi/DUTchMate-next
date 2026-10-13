"""Normalized journal failures survive resource-scope exception transport."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from dutchmate_core.evidence import JournalFailure, JournalFailureKind, JournalOperation


@contextmanager
def _resource_scope() -> Iterator[None]:
    yield


@asynccontextmanager
async def _async_resource_scope() -> AsyncIterator[None]:
    yield


def test_journal_failure_survives_sync_resource_scope() -> None:
    failure = JournalFailure(JournalOperation.RETRIEVE, JournalFailureKind.BUSY)
    with pytest.raises(JournalFailure) as caught:
        with _resource_scope():
            raise failure
    assert caught.value is failure
    assert caught.value.operation is JournalOperation.RETRIEVE
    assert caught.value.kind is JournalFailureKind.BUSY
    assert str(caught.value) == "retrieve/busy"
    assert caught.value.__traceback__ is not None


@pytest.mark.asyncio
async def test_journal_failure_survives_async_resource_scope_with_cause() -> None:
    cause = OSError("private storage diagnostic")
    failure = JournalFailure(
        JournalOperation.OPEN, JournalFailureKind.READ_ONLY, "private detail"
    )
    with pytest.raises(JournalFailure) as caught:
        async with _async_resource_scope():
            raise failure from cause
    assert caught.value is failure
    assert failure.operation is JournalOperation.OPEN
    assert failure.kind is JournalFailureKind.READ_ONLY
    assert failure.detail == "private detail"
    assert str(failure) == "open/read_only: private detail"
    assert failure.__cause__ is cause
    assert failure.__traceback__ is not None


@pytest.mark.parametrize("name", ["operation", "kind", "detail"])
@pytest.mark.parametrize("action", ["assign", "delete"])
def test_journal_failure_facts_cannot_be_changed(name: str, action: str) -> None:
    failure = JournalFailure(JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE)
    before = (failure.operation, failure.kind, failure.detail, hash(failure))
    with pytest.raises(FrozenInstanceError):
        if action == "assign":
            setattr(failure, name, "replacement")
        else:
            delattr(failure, name)
    assert (failure.operation, failure.kind, failure.detail, hash(failure)) == before


def test_standard_exception_metadata_remains_writable() -> None:
    failure = JournalFailure(JournalOperation.CLOSE, JournalFailureKind.IO_FAILURE)
    original_hash = hash(failure)
    cause, context = OSError("cause"), RuntimeError("context")
    failure.__cause__ = cause
    failure.__context__ = context
    failure.__suppress_context__ = True
    failure.add_note("scope cleanup completed")
    assert failure.with_traceback(None) is failure
    assert failure.__cause__ is cause and failure.__context__ is context
    assert failure.__suppress_context__ is True
    assert failure.__notes__ == ["scope cleanup completed"]
    assert hash(failure) == original_hash
    assert str(failure) == "close/io_failure"


@pytest.mark.parametrize(
    ("operation", "kind", "detail", "message"),
    [
        (JournalOperation.RETRIEVE, JournalFailureKind.BUSY, None, "retrieve/busy"),
        (JournalOperation.APPEND, JournalFailureKind.CAPACITY, "", "append/capacity"),
        (
            JournalOperation.OPEN,
            JournalFailureKind.DATABASE_OVER_CEILING,
            "private detail",
            "open/capacity/database_over_ceiling: private detail",
        ),
    ],
)
def test_existing_constructor_and_message_contract(
    operation: JournalOperation,
    kind: JournalFailureKind,
    detail: str | None,
    message: str,
) -> None:
    positional = JournalFailure(operation, kind, detail)
    keyword = JournalFailure(operation=operation, kind=kind, detail=detail)
    assert positional == keyword
    assert positional.operation is operation and positional.kind is kind
    assert positional.detail == detail
    assert str(positional) == message
    assert positional.args == (message,)


@pytest.mark.parametrize("kind", list(JournalFailureKind))
def test_declared_categories_survive_raise_and_catch(kind: JournalFailureKind) -> None:
    failure = JournalFailure(JournalOperation.RETRIEVE, kind)
    with pytest.raises(JournalFailure) as caught:
        raise failure
    assert caught.value.kind is kind
    assert caught.value.operation is JournalOperation.RETRIEVE
    assert caught.value.detail is None


@pytest.mark.parametrize(
    ("operation", "kind", "detail", "field"),
    [
        ("retrieve", JournalFailureKind.BUSY, None, "operation"),
        (JournalOperation.RETRIEVE, "busy", None, "kind"),
        (JournalOperation.RETRIEVE, JournalFailureKind.BUSY, 1, "detail"),
    ],
)
def test_constructor_still_rejects_unnormalized_facts(
    operation: object, kind: object, detail: object, field: str
) -> None:
    with pytest.raises(TypeError, match=field):
        JournalFailure(
            cast("JournalOperation", operation),
            cast("JournalFailureKind", kind),
            cast("str | None", detail),
        )
