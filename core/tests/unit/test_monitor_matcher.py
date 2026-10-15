"""Bounded literal matching, original byte positions and final-byte priority."""

import pytest

from dutchmate_core import model, monitor


def test_overlap_binary_chunk_span_and_first_match() -> None:
    matcher = monitor.LiteralMonitorMatcher(b"ababa\x00\xff", 100)
    assert matcher.feed(4, b"xxabab") is None
    assert matcher.feed(5, b"aba\x00\xffTAIL") is model.MonitorOutcome.MATCHED
    assert matcher.examined_rx_bytes == 11
    assert matcher.match == model.MonitorMatch(
        model.MonitorMatchStart(4, 4), model.MonitorMatchEnd(5, 5)
    )
    assert matcher.feed(6, b"anything") is model.MonitorOutcome.MATCHED
    assert matcher.examined_rx_bytes == 11


def test_loss_discards_partial_prefix_without_resetting_examined_budget() -> None:
    matcher = monitor.LiteralMonitorMatcher(b"abc", 8)
    assert matcher.feed(1, b"ab") is None
    matcher.reset_prefix()
    assert matcher.feed(3, b"c") is None
    assert matcher.feed(4, b"abc") is model.MonitorOutcome.MATCHED
    assert matcher.match == model.MonitorMatch(
        model.MonitorMatchStart(4, 0), model.MonitorMatchEnd(4, 3)
    )
    assert matcher.examined_rx_bytes == 6


@pytest.mark.parametrize(
    ("payload", "outcome", "end"),
    [
        (b"xabTAIL", model.MonitorOutcome.MATCHED, 3),
        (b"xaxTAIL", model.MonitorOutcome.BYTE_LIMIT, None),
    ],
)
def test_match_on_last_allowed_byte_wins_and_trailing_bytes_are_untouched(
    payload: bytes, outcome: model.MonitorOutcome, end: int | None
) -> None:
    matcher = monitor.LiteralMonitorMatcher(b"ab", 3)
    assert matcher.feed(1, b"") is None
    assert matcher.examined_rx_bytes == 0
    assert matcher.feed(2, payload) is outcome
    assert matcher.examined_rx_bytes == 3
    assert (matcher.match.end.byte_offset_exclusive if matcher.match else None) == end
    assert payload.endswith(b"TAIL")


def test_long_adversarial_prefix_keeps_bounded_positions_and_linear_work() -> None:
    matcher = monitor.LiteralMonitorMatcher(b"a" * 255 + b"b", 1048576)
    for sequence in range(16):
        assert matcher.feed(sequence, b"a" * 4096) is None
        assert len(matcher._positions) <= 256
        assert len(matcher._prefix) <= 256
    assert matcher.feed(16, b"b") is model.MonitorOutcome.MATCHED
    assert matcher.match == model.MonitorMatch(
        model.MonitorMatchStart(15, 3841), model.MonitorMatchEnd(16, 1)
    )


def test_every_chunk_split_has_identical_original_positions() -> None:
    for split in range(1, 6):
        matcher = monitor.LiteralMonitorMatcher(b"\x00\xffaba", 6)
        payload = b"x\x00\xffaba"
        assert matcher.feed(1, payload[:split]) is None
        assert matcher.feed(2, payload[split:]) is model.MonitorOutcome.MATCHED
        assert matcher.examined_rx_bytes == 6
        assert matcher.match is not None
        assert matcher.match.start.sequence == (1 if split > 1 else 2)
        assert matcher.match.end == model.MonitorMatchEnd(2, 6 - split)


@pytest.mark.parametrize("chunk_size", [1, 2, 7, 256, 4096, 65536])
@pytest.mark.parametrize(
    ("condition", "payload", "budget"),
    [
        (b"\0\xffaba", b"head\0\xffabaTAIL\x80", 9),
        (b"ababa\0\xff", b"xabababa\0\xffTAIL", 1024),
        (b"z" * 255 + b"\xff", b"z" * 4096 + b"\xffTAIL", 1048576),
        (b"\0\xff", b"x" * 65536 + b"\0\xffTAIL", 65536),
    ],
    ids=["binary-last-byte", "overlap", "maximum-condition", "budget-before-match"],
)
def test_t018_chunking_and_empty_records_preserve_independent_first_match_oracle(
    chunk_size: int, condition: bytes, payload: bytes, budget: int
) -> None:
    # bytes.find is an independent finite oracle, not a second streaming matcher.
    start = payload[:budget].find(condition)
    expected = (
        model.MonitorOutcome.MATCHED if start >= 0 else model.MonitorOutcome.BYTE_LIMIT
    )
    examined = start + len(condition) if start >= 0 else budget
    matcher = monitor.LiteralMonitorMatcher(condition, budget)
    outcome = None
    chunks = [
        payload[offset : offset + chunk_size]
        for offset in range(0, len(payload), chunk_size)
    ]
    for index, chunk in enumerate(chunks):
        assert matcher.feed(index * 2, b"") is outcome
        outcome = matcher.feed(index * 2 + 1, chunk)
        assert len(matcher._positions) <= len(condition) <= 256
    assert outcome is expected and matcher.examined_rx_bytes == examined
    if start < 0:
        assert matcher.match is None
    else:
        assert matcher.match == model.MonitorMatch(
            model.MonitorMatchStart((start // chunk_size) * 2 + 1, start % chunk_size),
            model.MonitorMatchEnd(
                ((examined - 1) // chunk_size) * 2 + 1,
                (examined - 1) % chunk_size + 1,
            ),
        )
    frozen = matcher.match
    matcher.reset_prefix()
    assert matcher.feed(1000000, b"\0\xffababa") is expected
    assert matcher.match == frozen and matcher.examined_rx_bytes == examined
