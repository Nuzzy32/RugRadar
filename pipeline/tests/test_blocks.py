import pytest

from pipeline.chain.blocks import first_block_at

# Block time berubah di tengah (3s -> 1s) dan ada beberapa block di detik yang sama.
TS = [0, 3, 6, 9, 10, 10, 11, 12, 12, 12, 13]


def get_ts(n: int) -> int:
    return TS[n]


@pytest.mark.parametrize(
    ("ts", "expected"),
    [(0, 0), (1, 1), (9, 3), (10, 4), (12, 7), (13, 10)],
)
def test_first_block_at(ts: int, expected: int) -> None:
    assert first_block_at(get_ts, 0, len(TS) - 1, ts) == expected


def test_future_timestamp_raises() -> None:
    with pytest.raises(ValueError):
        first_block_at(get_ts, 0, len(TS) - 1, 14)
