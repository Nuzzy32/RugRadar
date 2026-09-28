from collections.abc import Callable

from web3 import Web3


def first_block_at(get_ts: Callable[[int], int], lo: int, hi: int, ts: int) -> int:
    """Block pertama di [lo, hi] dengan timestamp >= ts. Timestamp diasumsikan tidak turun.

    Interpolation search (timestamp hampir linear, jadi cukup beberapa panggilan RPC),
    dengan fallback bisection kalau interval tidak menyusut setengah.
    """
    hi_ts = get_ts(hi)
    if hi_ts < ts:
        raise ValueError(f"timestamp {ts} lebih baru dari block {hi}")
    lo_ts = get_ts(lo)
    if lo_ts >= ts:
        return lo
    # Invariant: ts(lo) < ts <= ts(hi)
    bisect = False
    while hi - lo > 1:
        if bisect:
            mid = (lo + hi) // 2
        else:
            mid = lo + (ts - lo_ts) * (hi - lo) // (hi_ts - lo_ts)
            mid = min(max(mid, lo + 1), hi - 1)
        width = hi - lo
        mid_ts = get_ts(mid)
        if mid_ts < ts:
            lo, lo_ts = mid, mid_ts
        else:
            hi, hi_ts = mid, mid_ts
        bisect = (hi - lo) > width // 2
    return hi


def block_at_timestamp(w3: Web3, ts: int, lo: int = 0, hi: int | None = None) -> int:
    """Konversi waktu -> block lewat timestamp, bukan asumsi block time.

    `lo`/`hi` opsional untuk mempersempit pencarian (harus mengapit target).
    """
    if hi is None:
        hi = w3.eth.block_number
    return first_block_at(lambda n: w3.eth.get_block(n)["timestamp"], lo, hi, ts)
