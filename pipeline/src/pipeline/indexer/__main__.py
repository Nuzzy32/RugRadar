"""uv run python -m pipeline.indexer backfill --from-date 2025-07-01 --to-date 2025-08-01

Pair yang dibuat di [from-date, to-date) beserta event-nya sampai T0 + INDEX_WINDOW_DAYS.
Aman dihentikan kapan saja; menjalankan perintah yang sama akan lanjut dari checkpoint.
"""

import argparse
import sys
from datetime import UTC, datetime
from urllib.parse import urlparse

from pipeline.chain.blocks import block_at_timestamp
from pipeline.chain.rpc import make_web3
from pipeline.config import INDEX_WINDOW_DAYS, settings
from pipeline.db import connect
from pipeline.indexer.events import run_events_job
from pipeline.indexer.pairs import run_pairs_job


def _ts(date: str) -> int:
    return int(datetime.fromisoformat(date).replace(tzinfo=UTC).timestamp())


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    bf = sub.add_parser("backfill")
    bf.add_argument("--from-date", required=True, help="UTC, inklusif")
    bf.add_argument("--to-date", required=True, help="UTC, eksklusif")
    bf.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    if not settings.bsc_archive_rpc_url:
        sys.exit("BSC_ARCHIVE_RPC_URL belum diisi di .env")
    w3 = make_web3(settings.bsc_archive_rpc_url)
    from_ts, to_ts = _ts(args.from_date), _ts(args.to_date)
    start = block_at_timestamp(w3, from_ts)
    end = block_at_timestamp(w3, to_ts) - 1
    job = f"{args.from_date}:{args.to_date}"
    print(f"pair dibuat di block {start}..{end}", flush=True)

    with connect() as conn:
        run_pairs_job(w3, conn, f"pairs:{job}", start, end, args.workers)

        row = conn.execute(
            "select min(coalesce(t.created_block, p.t0_block)) from pairs p"
            " join tokens t on t.address = p.token where p.t0_block between %s and %s",
            (start, end),
        ).fetchone()
        ev_start = min(start, row[0] or start)  # transfer token sejak token dibuat
        try:
            ev_end = block_at_timestamp(w3, to_ts + INDEX_WINDOW_DAYS * 86400)
        except ValueError:  # jendela belum lewat
            ev_end = w3.eth.block_number
        print(f"event di-scan pada block {ev_start}..{ev_end}", flush=True)
        run_events_job(w3, conn, f"events:{job}", start, end, ev_start, ev_end)
    print("backfill selesai")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - traceback requests memuat URL RPC berisi API key
        msg = f"{type(e).__name__}: {e}"
        for url in (settings.bsc_archive_rpc_url, settings.bsc_rpc_url):
            if url:  # pesan requests memecah URL jadi host + path; key ada di path
                msg = msg.replace(url, "<RPC_URL>").replace(urlparse(url).path, "/<API_KEY>")
        sys.exit(f"backfill gagal (aman dilanjutkan dengan perintah yang sama): {msg}")
