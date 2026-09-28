"""Job events: event pool + transfer LP per pair, transfer token sampai snapshot.

Output: Parquet di RAW_DIR/<tabel>/<job>/<a>_<b>.parquet, satu file per chunk block.
Nama file deterministik + tulis atomik + checkpoint setelah file = aman diulang tanpa duplikat.
"""

import time
from datetime import UTC, datetime
from typing import Any

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
from eth_abi import decode
from hexbytes import HexBytes
from web3 import Web3
from web3.types import LogReceipt

from pipeline.chain.abi import PAIR_ABI
from pipeline.chain.rpc import get_logs_chunked, log_timestamp
from pipeline.config import INDEX_WINDOW_DAYS, LOGS_ADDRESS_BATCH, LOGS_BLOCK_STEP, RAW_DIR
from pipeline.db import get_checkpoint, set_checkpoint

_pair = Web3().eth.contract(abi=PAIR_ABI)
TOPIC = {n: HexBytes(getattr(_pair.events, n)().topic) for n in ("Sync", "Mint", "Burn", "Swap")}
TRANSFER = HexBytes(_pair.events.Transfer().topic)
POOL_TOPICS = [[t.to_0x_hex() for t in TOPIC.values()] + [TRANSFER.to_0x_hex()]]

# uint256 disimpan sebagai string desimal: exact, dan decimal256 Parquet hanya 76 digit.
_U = pa.string()
_META = [
    ("block_number", pa.int64()),
    ("block_time", pa.timestamp("s", tz="UTC")),
    ("tx_hash", pa.string()),
    ("log_index", pa.int32()),
]
_TRANSFER = [*_META, ("from_addr", pa.string()), ("to_addr", pa.string()), ("amount", _U)]
SCHEMAS = {
    "pool_events": pa.schema(
        [
            ("pair", pa.string()),
            *_META,
            ("event_type", pa.string()),
            ("reserve_token", _U),
            ("reserve_wbnb", _U),
            ("amount_token_in", _U),
            ("amount_wbnb_in", _U),
            ("amount_token_out", _U),
            ("amount_wbnb_out", _U),
            ("recipient", pa.string()),
            ("tx_from", pa.string()),
        ]
    ),
    "lp_transfers": pa.schema([("pair", pa.string()), *_TRANSFER]),
    "token_transfers": pa.schema([("token", pa.string()), *_TRANSFER]),
}


def write_chunk(table: str, job: str, a: int, b: int, rows: list[tuple]) -> None:
    """Tulis rows chunk [a, b] ke satu file Parquet, atomik (tmp lalu rename)."""
    if not rows:
        return
    schema = SCHEMAS[table]
    cols = {
        f.name: [r[i] if f.type != _U or r[i] is None else str(r[i]) for r in rows]
        for i, f in enumerate(schema)
    }
    path = RAW_DIR / table / job.replace(":", "_") / f"{a}_{b}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    pq.write_table(pa.table(cols, schema=schema), tmp, compression="zstd")
    tmp.replace(path)


def _addr(topic: bytes) -> str:
    return "0x" + bytes(topic)[-20:].hex()


def _meta(log: LogReceipt) -> tuple[int, datetime, str, int]:
    return (
        log["blockNumber"],
        datetime.fromtimestamp(log_timestamp(log), UTC),
        log["transactionHash"].to_0x_hex(),
        log["logIndex"],
    )


def decode_transfer(log: LogReceipt) -> tuple | None:
    """Transfer ERC20 standar -> (from, to, value). Varian non-standar dilewati."""
    topics = log["topics"]
    if len(topics) != 3 or topics[0] != TRANSFER or len(log["data"]) != 32:
        return None
    return (*_meta(log), _addr(topics[1]), _addr(topics[2]), decode(["uint256"], log["data"])[0])


def decode_pool_log(
    log: LogReceipt, token_is_token0: bool, snapshot_block: int | None
) -> tuple[str, tuple] | None:
    """Log dari alamat pair -> ("pool", row) atau ("lp", row). Swap setelah snapshot dibuang."""
    topics, data = log["topics"], log["data"]
    pair = log["address"].lower()
    t = 0 if token_is_token0 else 1  # indeks token di pair; WBNB = 1 - t
    w = 1 - t
    none4 = (None, None, None, None)

    if topics[0] == TRANSFER:
        row = decode_transfer(log)
        return ("lp", (pair, *row)) if row else None
    if topics[0] == TOPIC["Sync"]:
        r = decode(["uint112", "uint112"], data)
        return "pool", (pair, *_meta(log), "sync", r[t], r[w], *none4, None)
    if topics[0] == TOPIC["Mint"]:
        a = decode(["uint256", "uint256"], data)
        return "pool", (pair, *_meta(log), "mint", None, None, a[t], a[w], None, None, None)
    if topics[0] == TOPIC["Burn"]:
        a = decode(["uint256", "uint256"], data)
        to = _addr(topics[2])
        return "pool", (pair, *_meta(log), "burn", None, None, None, None, a[t], a[w], to)
    if topics[0] == TOPIC["Swap"]:
        if snapshot_block is not None and log["blockNumber"] > snapshot_block:
            return None
        a_in0, a_in1, a_out0, a_out1 = decode(["uint256"] * 4, data)
        ins, outs = (a_in0, a_in1), (a_out0, a_out1)
        to = _addr(topics[2])
        return "pool", (pair, *_meta(log), "swap", None, None, ins[t], ins[w], outs[t], outs[w], to)
    return None


def batches(items: list[Any], n: int) -> list[list[Any]]:
    return [items[i : i + n] for i in range(0, len(items), n)]


def run_events_job(
    w3: Web3,
    conn: psycopg.Connection,
    job: str,
    pair_start: int,
    pair_end: int,
    start: int,
    end: int,
) -> None:
    """Event untuk pair dengan t0 di [pair_start, pair_end], di-scan pada block [start, end]."""
    pairs = conn.execute(
        "select p.address, p.token, p.token_is_token0, p.t0_block,"
        " extract(epoch from p.t0_timestamp)::bigint, p.snapshot_block,"
        " coalesce(t.created_block, p.t0_block)"
        " from pairs p join tokens t on t.address = p.token"
        " where p.t0_block between %s and %s",
        (pair_start, pair_end),
    ).fetchall()
    info = {p[0]: p for p in pairs}
    window = INDEX_WINDOW_DAYS * 86400

    ckpt = get_checkpoint(conn, job)
    a = start if ckpt is None else max(start, ckpt + 1)
    while a <= end:
        b = min(a + LOGS_BLOCK_STEP - 1, end)
        t = time.monotonic()
        ts_a = w3.eth.get_block(a)["timestamp"]
        ts_b = w3.eth.get_block(b)["timestamp"]
        active_pairs = [p[0] for p in pairs if p[3] <= b and p[4] + window >= ts_a]
        active_tokens = [p[1] for p in pairs if p[6] <= b and (p[5] is None or p[5] >= a)]
        snap_of_token = {p[1]: p[5] for p in pairs}

        pool_rows, lp_rows, token_rows = [], [], []
        for batch in batches(active_pairs, LOGS_ADDRESS_BATCH):
            addrs = [Web3.to_checksum_address(x) for x in batch]
            for log in get_logs_chunked(w3, addrs, a, b, POOL_TOPICS, step=LOGS_BLOCK_STEP):
                p = info[log["address"].lower()]
                res = decode_pool_log(log, p[2], p[5])
                if res:
                    (pool_rows if res[0] == "pool" else lp_rows).append(res[1])

        for batch in batches(active_tokens, LOGS_ADDRESS_BATCH):
            addrs = [Web3.to_checksum_address(x) for x in batch]
            topics = [TRANSFER.to_0x_hex()]
            for log in get_logs_chunked(w3, addrs, a, b, [topics], step=LOGS_BLOCK_STEP):
                token = log["address"].lower()
                snap = snap_of_token[token]
                if snap is not None and log["blockNumber"] > snap:
                    continue
                row = decode_transfer(log)
                if row:
                    token_rows.append((token, *row))

        # tx_from hanya untuk burn: jarang, dan dibutuhkan labeling rug pull.
        burn_txs = {r[3] for r in pool_rows if r[5] == "burn"}
        tx_from = {h: w3.eth.get_transaction(h)["from"].lower() for h in burn_txs}

        write_chunk("pool_events", job, a, b, [(*r, tx_from.get(r[3])) for r in pool_rows])
        write_chunk("lp_transfers", job, a, b, lp_rows)
        write_chunk("token_transfers", job, a, b, token_rows)
        with conn.transaction():
            # Token selesai jika jendela event pair dan transfer token sudah lewat.
            conn.execute(
                "update tokens t set status = 'complete' from pairs p"
                " where p.token = t.address and t.status = 'indexing'"
                " and p.t0_block between %s and %s"
                " and p.t0_timestamp + make_interval(days => %s) <= to_timestamp(%s)"
                " and p.snapshot_block <= %s",
                (pair_start, pair_end, INDEX_WINDOW_DAYS, ts_b, b),
            )
            set_checkpoint(conn, job, b)
        print(
            f"[{job}] {a}..{b}: pair aktif={len(active_pairs)} token aktif={len(active_tokens)}"
            f" | pool={len(pool_rows)} lp={len(lp_rows)} transfer={len(token_rows)}"
            f" | {time.monotonic() - t:.0f}s",
            flush=True,
        )
        a = b + 1
