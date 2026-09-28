import bisect
import random

from pipeline.indexer.pairs import snapshot_blocks

DAY = 86400


def test_matches_bisect_and_is_cheap() -> None:
    # ~0.75 detik per block dengan jitter, dibulatkan ke detik (banyak block per detik sama).
    rng = random.Random(1)
    ts, t = [], 1_750_000_000.0
    for _ in range(400_000):
        t += 0.75 * rng.uniform(0.8, 1.2)
        ts.append(int(t))
    latest = len(ts) - 1
    calls = 0
    cache: dict[int, int] = {}

    def get_ts(n: int) -> int:
        nonlocal calls
        if n not in cache:
            calls += 1
            cache[n] = ts[n]
        return cache[n]

    t0s = sorted(rng.sample(range(0, 200_000), 500))
    items = [(b, ts[b] + DAY) for b in t0s]
    got = snapshot_blocks(get_ts, items, latest, ts[latest])

    assert got == [bisect.bisect_left(ts, target) for _, target in items]
    assert calls / len(items) <= 5  # rata-rata panggilan RPC per pair (terukur ~4.3)


def test_future_target_is_none() -> None:
    ts = list(range(100))
    got = snapshot_blocks(lambda n: ts[n], [(10, 50), (20, 500)], 99, 99)
    assert got == [50, None]
