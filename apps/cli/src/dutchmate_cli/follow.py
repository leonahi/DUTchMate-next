"""Bounded Follow framing and delivery validation; no capture or journal policy."""

import re
from collections.abc import AsyncIterator

from dutchmate_cli import context, evidence

_LIMIT = 1048576
_MEDIA = re.compile(
    r'application/x-ndjson(?:[ \t]*;[ \t]*charset[ \t]*=[ \t]*(?:utf-8|"utf-8"))?',
    re.IGNORECASE,
)
_REASONS = {
    "detached",
    "service_stopping",
    "source_ended",
    "source_failed",
    "read_capacity",
    "delivery_too_large",
}
_ERRORS = {
    (404, "no_associated_session"),
    (409, "session_not_associated"),
    (409, "not_active"),
    (503, "follow_unavailable"),
    (409, "busy"),
    (503, "read_capacity"),
    (413, "delivery_too_large"),
}


def request(session: str) -> dict[str, object]:
    try:
        return {"session_id": evidence._input_session(session)}
    except ValueError, TypeError:
        raise context.CliFailure(context.CliFailureKind.INVALID_ARGUMENTS) from None


def recognized_error(value: object, status: int) -> bool:
    error = evidence._view(
        evidence._view(value, ("error",))["error"], ("source", "code")
    )
    source, code = evidence._text(error["source"]), evidence._text(error["code"])
    return (
        (source == "follow" and (status, code) in _ERRORS)
        or (source == "service" and (status, code) == (503, "follow_capacity"))
        or (source == "journal" and evidence.recognized_error(value, status))
    )


class Frames:
    """One partial frame and an offset into the current external HTTP chunk.

    Chunks can contain many frames. Slice only bounded portions into the frame
    buffer; never join chunks, copy their whole remainder or keep a transcript.
    """

    def __init__(self, chunks: AsyncIterator[bytes]) -> None:
        self._chunks = chunks
        self._chunk = b""
        self._offset = 0
        self._buffer = bytearray()

    async def read(self) -> bytearray | None:
        while True:
            if self._offset == len(self._chunk):
                try:
                    self._chunk = await anext(self._chunks)
                    self._offset = 0
                except StopAsyncIteration:
                    if self._buffer:
                        raise ValueError("invalid_response") from None
                    return None
            delimiter = self._chunk.find(b"\n", self._offset)
            end = len(self._chunk) if delimiter < 0 else delimiter
            count = min(end - self._offset, _LIMIT + 1 - len(self._buffer))
            self._buffer.extend(self._chunk[self._offset : self._offset + count])
            self._offset += count
            if len(self._buffer) > _LIMIT:
                raise ValueError("invalid_response")
            if delimiter >= 0:
                self._offset += 1
                result, self._buffer = self._buffer, bytearray()
                return result

    async def require_eof(self) -> None:
        if self._offset < len(self._chunk):
            raise ValueError("invalid_response")
        async for chunk in self._chunks:
            if chunk:
                raise ValueError("invalid_response")


class Position:
    """Validate the received prefix only; never reconstruct Core decisions."""

    def __init__(self, session: str, *, api_version: int = 1) -> None:
        self._session = session
        self._api_version = api_version
        self._next: int | None = None
        self.terminal = False

    def accept(self, value: object) -> dict[str, object]:
        if type(value) is not dict or self.terminal:
            raise ValueError("invalid_response")
        if self._next is None:
            view = evidence._view(
                value, ("type", "run_id", "session_id", "start_sequence", "provenance")
            )
            evidence._choice(view["type"], {"started"})
            evidence._text(view["run_id"])
            if (
                evidence._input_session(evidence._text(view["session_id"]))
                != self._session
            ):
                raise ValueError("invalid_response")
            self._next = evidence._counter(view["start_sequence"])
            view["provenance"] = evidence._provenance(view["provenance"])
            return view
        match value.get("type"):
            case "record":
                view = evidence._view(value, ("type", "record"))
                record = evidence._record(view["record"], api_version=self._api_version)
                if record["sequence"] != self._next:
                    raise ValueError("invalid_response")
                self._next += 1
                view["record"] = record
            case "gap":
                view = evidence._view(
                    value, ("type", "missed_range", "retention_marker")
                )
                missed, marker = (
                    evidence._range(view["missed_range"]),
                    evidence._marker(view["retention_marker"]),
                )
                if missed is None or marker is None:
                    raise ValueError("invalid_response")
                expired = evidence._range(marker["expired_range"])
                assert expired is not None
                start, end = (
                    evidence._counter(missed["start_inclusive"]),
                    evidence._counter(missed["end_exclusive"]),
                )
                if not (
                    start == self._next
                    and start < end
                    and evidence._counter(expired["start_inclusive"]) == 0
                    and end <= evidence._counter(expired["end_exclusive"])
                    and evidence._counter(marker["discarded_record_count"])
                    == evidence._counter(expired["end_exclusive"])
                ):
                    raise ValueError("invalid_response")
                first, last = (
                    marker["first_discarded_timestamp"],
                    marker["last_discarded_timestamp"],
                )
                if (first is None) != (last is None):
                    raise ValueError("invalid_response")
                for endpoint in (first, last):
                    if endpoint is not None:
                        entry = evidence._view(endpoint, ("timestamp", "domain"))
                        timestamp = evidence._timestamp(entry["timestamp"])
                        domain = evidence._domain(entry["domain"])
                        if timestamp["domain_id"] != domain["domain_id"]:
                            raise ValueError("invalid_response")
                self._next = end
                view["missed_range"], view["retention_marker"] = missed, marker
            case "heartbeat":
                view = evidence._view(value, ("type",))
            case "terminal":
                view = evidence._view(
                    value, ("type", "reason", "next_sequence", "source_end_exclusive")
                )
                evidence._choice(view["reason"], _REASONS)
                if evidence._counter(view["next_sequence"]) != self._next:
                    raise ValueError("invalid_response")
                cutoff = view["source_end_exclusive"]
                if cutoff is not None and evidence._counter(cutoff) < self._next:
                    raise ValueError("invalid_response")
                self.terminal = True
            case _:
                raise ValueError("invalid_response")
        return view
