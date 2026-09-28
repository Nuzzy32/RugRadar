from eth_abi import encode
from hexbytes import HexBytes

from pipeline.indexer.events import TOPIC, TRANSFER, decode_pool_log

PAIR = "0x" + "11" * 20
USER = "0x" + "22" * 20


def _log(topic: HexBytes, data: bytes, extra_topics: list[str] = (), block: int = 100) -> dict:
    return {
        "address": PAIR,
        "topics": [topic] + [HexBytes(bytes(12) + bytes.fromhex(a[2:])) for a in extra_topics],
        "data": HexBytes(data),
        "blockNumber": block,
        "blockTimestamp": "0x64",
        "transactionHash": HexBytes(b"\x01" * 32),
        "logIndex": 7,
    }


def swap(in0: int, in1: int, out0: int, out1: int, block: int = 100) -> dict:
    data = encode(["uint256"] * 4, [in0, in1, out0, out1])
    return _log(TOPIC["Swap"], data, [PAIR, USER], block)


def test_buy_when_token_is_token0() -> None:
    # Beli: WBNB (token1) masuk, token (token0) keluar.
    kind, row = decode_pool_log(swap(0, 5, 1000, 0), token_is_token0=True, snapshot_block=None)
    assert kind == "pool" and row[5] == "swap"
    # amount_token_in, amount_wbnb_in, amount_token_out, amount_wbnb_out, recipient
    assert row[8:13] == (0, 5, 1000, 0, USER)


def test_sell_when_token_is_token1() -> None:
    # Jual: token (token1) masuk, WBNB (token0) keluar.
    _, row = decode_pool_log(swap(0, 1000, 5, 0), token_is_token0=False, snapshot_block=None)
    assert row[8:12] == (1000, 0, 0, 5)


def test_swap_after_snapshot_dropped() -> None:
    assert decode_pool_log(swap(0, 5, 1000, 0, block=101), True, snapshot_block=100) is None
    assert decode_pool_log(swap(0, 5, 1000, 0, block=100), True, snapshot_block=100) is not None


def test_sync_orients_reserves() -> None:
    log = _log(TOPIC["Sync"], encode(["uint112", "uint112"], [7, 9]))
    _, row = decode_pool_log(log, token_is_token0=False, snapshot_block=None)
    assert (row[6], row[7]) == (9, 7)  # reserve_token, reserve_wbnb


def test_burn_and_lp_transfer() -> None:
    burn = _log(TOPIC["Burn"], encode(["uint256", "uint256"], [3, 4]), [PAIR, USER], block=500)
    _, row = decode_pool_log(burn, token_is_token0=True, snapshot_block=100)  # burn tetap disimpan
    assert row[5] == "burn" and row[10:13] == (3, 4, USER)

    lp = _log(TRANSFER, encode(["uint256"], [42]), [USER, PAIR])
    kind, row = decode_pool_log(lp, True, None)
    assert kind == "lp" and row[0] == PAIR and row[5:] == (USER, PAIR, 42)
    assert row[3] == "0x" + "01" * 32
