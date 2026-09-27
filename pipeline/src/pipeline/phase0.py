"""Fase 0: validasi akses data end-to-end untuk satu pair historis.

uv run python -m pipeline.phase0 --date 2025-09-01
"""

import argparse
import sys
import time
from collections import Counter
from datetime import UTC, datetime

from web3 import Web3

from pipeline.chain import explorer
from pipeline.chain.abi import ERC20_ABI, FACTORY_ABI, PAIR_ABI, ROUTER_ABI
from pipeline.chain.blocks import block_at_timestamp
from pipeline.chain.rpc import get_logs_chunked, make_web3
from pipeline.config import (
    BSC_CHAIN_ID,
    DEAD_ADDRESSES,
    PANCAKE_V2_FACTORY,
    PANCAKE_V2_ROUTER,
    SNAPSHOT_HOURS,
    WBNB,
    settings,
)
from pipeline.simulation.sell import anvil_fork, simulate_sell


def step(msg: str) -> None:
    print(f"\n== {msg}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2025-09-01", help="tanggal UTC untuk mencari pair baru")
    ap.add_argument("--window-minutes", type=int, default=30)
    ap.add_argument("--max-pairs", type=int, default=10)
    args = ap.parse_args()

    if not settings.bsc_archive_rpc_url:
        sys.exit("BSC_ARCHIVE_RPC_URL belum diisi di .env")
    w3 = make_web3(settings.bsc_archive_rpc_url)

    step("Koneksi RPC")
    chain_id = w3.eth.chain_id
    print(f"chain_id={chain_id} latest={w3.eth.block_number}")
    if chain_id != BSC_CHAIN_ID:
        sys.exit("bukan BSC mainnet")
    router = w3.eth.contract(Web3.to_checksum_address(PANCAKE_V2_ROUTER), abi=ROUTER_ABI)
    weth = router.functions.WETH().call().lower()
    print(f"router.WETH()={weth} {'cocok' if weth == WBNB else 'TIDAK COCOK'} dengan config.WBNB")
    if weth != WBNB:
        sys.exit("alamat WBNB di config salah")

    step(f"PairCreated sekitar {args.date}")
    ts = int(datetime.fromisoformat(args.date).replace(tzinfo=UTC).timestamp())
    b0 = block_at_timestamp(w3, ts)
    b1 = block_at_timestamp(w3, ts + args.window_minutes * 60)
    factory = w3.eth.contract(Web3.to_checksum_address(PANCAKE_V2_FACTORY), abi=FACTORY_ABI)
    pc = factory.events.PairCreated()
    created = [
        pc.process_log(log) for log in get_logs_chunked(w3, factory.address, b0, b1, [pc.topic])
    ]
    wbnb_pairs = [e for e in created if WBNB in (e.args.token0.lower(), e.args.token1.lower())]
    print(f"blocks {b0}..{b1}: {len(created)} pair baru, {len(wbnb_pairs)} berpasangan dengan WBNB")

    pair_c = w3.eth.contract(abi=PAIR_ABI)
    topic_name = {
        getattr(pair_c.events, n)().topic: n for n in ("Sync", "Mint", "Burn", "Swap", "Transfer")
    }
    swap_ev = pair_c.events.Swap()
    skip = DEAD_ADDRESSES | {PANCAKE_V2_ROUTER}

    chosen = None
    for e in wbnb_pairs[: args.max_pairs]:
        pair, t0 = e.args.pair, e.blockNumber
        token_is_0 = e.args.token1.lower() == WBNB
        token = e.args.token0 if token_is_0 else e.args.token1
        snap = block_at_timestamp(w3, w3.eth.get_block(t0)["timestamp"] + SNAPSHOT_HOURS * 3600)

        step(f"Event pair {pair} (token {token}) block {t0}..{snap}")
        t = time.monotonic()
        logs = get_logs_chunked(w3, pair, t0, snap)
        counts = Counter(topic_name.get(log["topics"][0], "other") for log in logs)
        token_c = w3.eth.contract(token, abi=ERC20_ABI)
        n_token_tx = len(get_logs_chunked(w3, token, t0, snap, [token_c.events.Transfer().topic]))
        print(f"{dict(counts)} | token Transfer={n_token_tx} | {time.monotonic() - t:.1f}s")

        buyers: list[str] = []
        for log in logs:
            if topic_name.get(log["topics"][0]) != "Swap":
                continue
            a = swap_ev.process_log(log).args
            bought = a.amount0Out if token_is_0 else a.amount1Out
            if (
                bought
                and a.to.lower() not in skip
                and a.to.lower() != pair.lower()
                and a.to not in buyers
            ):
                buyers.append(a.to)

        # State historis di snapshot: ini yang membuktikan RPC benar-benar archive.
        for b in buyers[:20]:
            bal = token_c.functions.balanceOf(b).call(block_identifier=snap)
            if bal and w3.eth.get_code(b, block_identifier=snap) == b"":
                print(f"pembeli {b} saldo {bal} di block {snap} (state historis OK)")
                chosen = (token, b, snap)
                break
        if chosen:
            break
        print(f"{len(buyers)} pembeli, tidak ada EOA yang masih pegang token; coba pair berikutnya")

    if not chosen:
        sys.exit("tidak ada kandidat; perbesar --window-minutes atau --max-pairs")

    token, holder, snap = chosen
    step(f"Simulasi jual di anvil fork block {snap}")
    t = time.monotonic()
    with anvil_fork(settings.bsc_archive_rpc_url, snap) as fork:
        result = simulate_sell(fork, token, holder)
    print(f"{result.model_dump()} | {time.monotonic() - t:.1f}s")

    step("Explorer API (Etherscan V2)")
    if not settings.explorer_api_key:
        print("EXPLORER_API_KEY belum diisi, dilewati")
    else:
        try:
            src = explorer.get_source_code(token)
            creation = explorer.get_contract_creation([token])[0]
            verified = bool(src.get("SourceCode"))
            print(f"terverifikasi={verified} nama_kontrak={src.get('ContractName')!r:.60}")
            print(f"deployer={creation['contractCreator']} tx={creation['txHash']}")
        except explorer.ExplorerError as e:
            print(f"GAGAL: {e}")

    step("Selesai")
    print(
        "Event satu pair lengkap dan simulasi jual di fork historis berjalan."
        if result.status != "error"
        else "Simulasi gagal secara teknis; cek revert_reason di atas."
    )


if __name__ == "__main__":
    main()
