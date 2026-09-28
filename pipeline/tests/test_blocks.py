import bisect
import random

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


def test_matches_bisect_on_nonlinear_chain() -> None:
    # Riwayat mirip BSC: 3s, lalu 1.5s, 0.75s, 0.45s (dibulatkan ke detik).
    rng = random.Random(0)
    ts, t = [], 0.0
    for block_time, n in [(3, 20_000), (1.5, 20_000), (0.75, 40_000), (0.45, 40_000)]:
        for _ in range(n):
            t += block_time * rng.uniform(0.9, 1.1)
            ts.append(int(t))
    calls = 0

    def counted(n: int) -> int:
        nonlocal calls
        calls += 1
        return ts[n]

    for target in rng.sample(range(ts[0], ts[-1] + 1), 300):
        calls = 0
        assert first_block_at(counted, 0, len(ts) - 1, target) == bisect.bisect_left(ts, target)
        assert calls <= 40  # batas bisection murni ~2 + log2(120k) = 19; beri ruang
