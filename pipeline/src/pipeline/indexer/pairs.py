"""Job pairs: PairCreated (pair WBNB) -> tabel tokens + pairs."""

import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import psycopg
from eth_abi import decode
from web3 import Web3

from pipeline.chain.abi import ERC20_ABI, FACTORY_ABI, MULTICALL3_ABI
from pipeline.chain.blocks import first_block_at
from pipeline.chain.rpc import get_logs_chunked, log_timestamp
from pipeline.config import (
    LOGS_ADDRESS_BATCH,
    LOGS_BLOCK_STEP,
    MAX_TOKEN_AGE_AT_PAIR_DAYS,
    MULTICALL3,
    PANCAKE_V2_FACTORY,
    SNAPSHOT_HOURS,
    WBNB,
)
from pipeline.db import get_checkpoint, set_checkpoint
from pipeline.indexer.events import TRANSFER, batches

ZERO_TOPIC = "0x" + "00" * 32

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩]")


def clean_text(value: str | None, max_len: int) -> str | None:
    """Nama/simbol dari kontrak = input tidak tepercaya: buang karakter kontrol & bidi, potong."""
    if value is None:
        return None
    value = _CONTROL_CHARS.sub("", value).strip()[:max_len]
    return value or None


def _decode_str(data: bytes) -> str | None:
    if not data:
        return None
    try:
        return decode(["string"], data)[0]
    except Exception:  # noqa: BLE001 - token lama memakai bytes32
        if len(data) == 32:
            return data.rstrip(b"\x00").decode("utf-8", "replace")
        return None


def _decode_uint(data: bytes) -> int | None:
    try:
        return decode(["uint256"], data)[0] if data else None
    except Exception:  # noqa: BLE001
        return None


def token_metadata(w3: Web3, tokens: list[str], block: int) -> dict[str, dict[str, Any]]:
    """name/symbol/decimals/totalSupply banyak token: satu eth_call Multicall3 per 100 token."""
    erc20 = w3.eth.contract(abi=ERC20_ABI)
    mc = w3.eth.contract(Web3.to_checksum_address(MULTICALL3), abi=MULTICALL3_ABI)
    fns = ["name", "symbol", "decimals", "totalSupply"]
    data = {fn: bytes.fromhex(erc20.encode_abi(fn)[2:]) for fn in fns}
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(tokens), 100):
        batch = tokens[i : i + 100]
        calls = [(t, True, data[fn]) for t in batch for fn in fns]
        res = mc.functions.aggregate3(calls).call(block_identifier=block)
        for j, t in enumerate(batch):
            r = {fn: (ok, ret) for fn, (ok, ret) in zip(fns, res[j * 4 : j * 4 + 4], strict=True)}
            decimals = _decode_uint(r["decimals"][1]) if r["decimals"][0] else None
            out[t.lower()] = {
                "name": clean_text(_decode_str(r["name"][1]) if r["name"][0] else None, 128),
                "symbol": clean_text(_decode_str(r["symbol"][1]) if r["symbol"][0] else None, 32),
                "decimals": decimals if decimals is not None and decimals <= 255 else None,
                "total_supply": _decode_uint(r["totalSupply"][1]) if r["totalSupply"][0] else None,
            }
    return out


def snapshot_blocks(
    get_ts: Callable[[int], int], items: list[tuple[int, int]], latest: int, latest_ts: int
) -> list[int | None]:
    """Snapshot block untuk tiap (t0_block, target_ts), `items` terurut target.

    Pencarian dimulai dari snapshot sebelumnya (target berdekatan): ~4 panggilan RPC per pair.
    Timestamp beresolusi detik (~1.3 block per detik) membuat ini mendekati batas bawah.
    `get_ts` sebaiknya di-cache.
    """
    out: list[int | None] = []
    prev: int | None = None
    for t0, target in items:
        if target > latest_ts:
            out.append(None)
            continue
        # ts(prev - 1) < target sebelumnya <= target ini, jadi aman sebagai batas bawah.
        lo = max(t0, prev - 1) if prev is not None else t0
        gap = max(0, target - get_ts(lo))
        hi = min(latest, lo + gap * 3 + 10)  # block time BSC >= 0.33 detik
        try:
            b = first_block_at(get_ts, lo, hi, target)
        except ValueError:
            b = first_block_at(get_ts, lo, latest, target)
        out.append(b)
        prev = b
    return out


def first_mints(w3: Web3, tokens: list[str], from_block: int, to_block: int) -> dict[str, Any]:
    """Log Transfer dari 0x0 paling awal per token = jejak pembuatan token (supply awal dicetak).

    Pengganti nr_getContractCreationTransaction (250 CU per token): getLogs 50 CU per 300 token.
    """
    out: dict[str, Any] = {}
    for batch in batches(tokens, LOGS_ADDRESS_BATCH):
        addrs = [Web3.to_checksum_address(t) for t in batch]
        topics = [TRANSFER.to_0x_hex(), ZERO_TOPIC]
        for log in get_logs_chunked(w3, addrs, from_block, to_block, topics, step=LOGS_BLOCK_STEP):
            out.setdefault(log["address"].lower(), log)  # log terurut block, ambil yang pertama
    return out


def run_pairs_job(
    w3: Web3, conn: psycopg.Connection, job: str, start: int, end: int, workers: int = 4
) -> None:
    factory = w3.eth.contract(Web3.to_checksum_address(PANCAKE_V2_FACTORY), abi=FACTORY_ABI)
    pc = factory.events.PairCreated()
    ckpt = get_checkpoint(conn, job)
    a = start if ckpt is None else max(start, ckpt + 1)
    latest = w3.eth.block_number
    latest_ts = w3.eth.get_block(latest)["timestamp"]
    max_age = MAX_TOKEN_AGE_AT_PAIR_DAYS * 86400

    @lru_cache(maxsize=100_000)
    def get_ts(n: int) -> int:
        return w3.eth.get_block(n)["timestamp"]

    with ThreadPoolExecutor(workers) as pool:
        while a <= end:
            b = min(a + LOGS_BLOCK_STEP - 1, end)
            t = time.monotonic()
            logs = get_logs_chunked(w3, factory.address, a, b, [pc.topic], step=LOGS_BLOCK_STEP)
            pairs = []
            for log in logs:
                e = pc.process_log(log)
                token_is_0 = e.args.token1.lower() == WBNB
                if not token_is_0 and e.args.token0.lower() != WBNB:
                    continue
                token = (e.args.token0 if token_is_0 else e.args.token1).lower()
                pairs.append(
                    (e.args.pair.lower(), token, token_is_0, e.blockNumber, log_timestamp(log))
                )

            # Pembuatan token: mint pertama dalam MAX_TOKEN_AGE hari sebelum chunk.
            lo = max(0, a - max_age * 3)
            mint_from = first_block_at(get_ts, lo, a, get_ts(a) - max_age) if a > 0 else 0
            mints = first_mints(w3, [p[1] for p in pairs], mint_from, b)
            kept = [
                p for p in pairs if p[1] in mints and p[4] - log_timestamp(mints[p[1]]) <= max_age
            ]
            txs = [mints[p[1]]["transactionHash"] for p in kept]
            deployers = [tx["from"].lower() for tx in pool.map(w3.eth.get_transaction, txs)]
            snaps = snapshot_blocks(
                get_ts, [(p[3], p[4] + SNAPSHOT_HOURS * 3600) for p in kept], latest, latest_ts
            )
            meta = token_metadata(w3, [Web3.to_checksum_address(p[1]) for p in kept], b)

            with conn.transaction():
                with conn.cursor() as cur:
                    cur.executemany(
                        "insert into tokens (address, name, symbol, decimals, total_supply,"
                        " deployer, created_block, created_at)"
                        " values (%s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
                        [
                            (
                                p[1],
                                meta[p[1]]["name"],
                                meta[p[1]]["symbol"],
                                meta[p[1]]["decimals"],
                                meta[p[1]]["total_supply"],
                                dep,
                                mints[p[1]]["blockNumber"],
                                datetime.fromtimestamp(log_timestamp(mints[p[1]]), UTC),
                            )
                            for p, dep in zip(kept, deployers, strict=True)
                        ],
                    )
                    cur.executemany(
                        "insert into pairs (address, token, token_is_token0, t0_block,"
                        " t0_timestamp, snapshot_block) values (%s, %s, %s, %s, %s, %s)"
                        " on conflict do nothing",
                        [
                            (p[0], p[1], p[2], p[3], datetime.fromtimestamp(p[4], UTC), snap)
                            for p, snap in zip(kept, snaps, strict=True)
                        ],
                    )
                set_checkpoint(conn, job, b)
            print(
                f"[{job}] {a}..{b}: {len(pairs)} pair WBNB, {len(kept)} disimpan"
                f" ({len(pairs) - len(kept)} token lama/tanpa mint) | {time.monotonic() - t:.0f}s",
                flush=True,
            )
            a = b + 1
