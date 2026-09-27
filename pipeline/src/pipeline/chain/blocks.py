from collections.abc import Callable

from web3 import Web3


def first_block_at(get_ts: Callable[[int], int], lo: int, hi: int, ts: int) -> int:
    """Block pertama di [lo, hi] dengan timestamp >= ts. Timestamp diasumsikan tidak turun."""
    if get_ts(hi) < ts:
        raise ValueError(f"timestamp {ts} lebih baru dari block {hi}")
    while lo < hi:
        mid = (lo + hi) // 2
        if get_ts(mid) < ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def block_at_timestamp(w3: Web3, ts: int) -> int:
    """Konversi waktu -> block lewat binary search timestamp, bukan asumsi block time."""
    latest = w3.eth.block_number
    return first_block_at(lambda n: w3.eth.get_block(n)["timestamp"], 0, latest, ts)
