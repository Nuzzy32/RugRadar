"""Simulasi jual di fork anvil lokal. Tidak pernah menyentuh jaringan asli."""

import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel
from web3 import Web3
from web3.exceptions import ContractLogicError

from pipeline.chain.abi import ERC20_ABI, ROUTER_ABI
from pipeline.chain.rpc import make_web3
from pipeline.config import PANCAKE_V2_ROUTER, WBNB

LOCAL_HOSTS = {"127.0.0.1", "localhost"}


class SellResult(BaseModel):
    status: Literal["ok", "reverted", "error"]
    amount_in: int = 0
    expected_out_wei: int = 0
    actual_out_wei: int = 0
    sell_tax_pct: float | None = None
    revert_reason: str | None = None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def anvil_fork(fork_url: str, block: int, timeout_s: float = 60) -> Iterator[Web3]:
    """Jalankan anvil fork di 127.0.0.1 pada `block`, hentikan saat keluar."""
    anvil = shutil.which("anvil")
    if not anvil:
        raise RuntimeError("anvil tidak ditemukan; install Foundry")
    port = _free_port()
    proc = subprocess.Popen(
        [
            anvil,
            "--fork-url",
            fork_url,
            "--fork-block-number",
            str(block),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--quiet",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        w3 = make_web3(f"http://127.0.0.1:{port}", timeout=120)
        deadline = time.monotonic() + timeout_s
        while not w3.is_connected():
            if proc.poll() is not None:
                raise RuntimeError(f"anvil berhenti: {proc.stderr.read().decode()[-500:]}")
            if time.monotonic() > deadline:
                raise TimeoutError("anvil tidak siap")
            time.sleep(0.3)
        yield w3
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _assert_local(w3: Web3) -> None:
    host = urlparse(w3.provider.endpoint_uri).hostname
    if host not in LOCAL_HOSTS:
        raise RuntimeError(f"simulasi hanya boleh ke fork lokal, bukan {host}")


def simulate_sell(fork: Web3, token: str, holder: str, fraction: float = 0.1) -> SellResult:
    """Impersonate `holder`, jual `fraction` saldonya ke WBNB, bandingkan dgn getAmountsOut."""
    _assert_local(fork)
    token_c = fork.eth.contract(Web3.to_checksum_address(token), abi=ERC20_ABI)
    router = fork.eth.contract(Web3.to_checksum_address(PANCAKE_V2_ROUTER), abi=ROUTER_ABI)
    holder = Web3.to_checksum_address(holder)
    path = [token_c.address, Web3.to_checksum_address(WBNB)]

    balance = token_c.functions.balanceOf(holder).call()
    amount = int(balance * fraction)
    if amount == 0:
        return SellResult(status="error", revert_reason="holder tidak punya saldo")

    fork.provider.make_request("anvil_impersonateAccount", [holder])
    fork.provider.make_request("anvil_setBalance", [holder, hex(10**18)])
    tx = {"from": holder}
    try:
        expected = router.functions.getAmountsOut(amount, path).call()[-1]
        fork.eth.wait_for_transaction_receipt(
            token_c.functions.approve(router.address, amount).transact(tx)
        )
        swap = router.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
            amount, 0, path, holder, 2**32
        )
        swap.call(tx)  # revert di sini = kontrak menolak jual
        before = fork.eth.get_balance(holder)
        rcpt = fork.eth.wait_for_transaction_receipt(swap.transact(tx))
    except ContractLogicError as e:
        return SellResult(status="reverted", amount_in=amount, revert_reason=str(e)[:300])
    except Exception as e:  # noqa: BLE001 - kegagalan teknis, bukan bukti honeypot
        return SellResult(status="error", amount_in=amount, revert_reason=repr(e)[:300])
    finally:
        fork.provider.make_request("anvil_stopImpersonatingAccount", [holder])

    if rcpt["status"] != 1:
        return SellResult(status="reverted", amount_in=amount, expected_out_wei=expected)
    gas = rcpt["gasUsed"] * rcpt["effectiveGasPrice"]
    actual = fork.eth.get_balance(holder) - before + gas
    tax = (1 - actual / expected) * 100 if expected else None
    return SellResult(
        status="ok",
        amount_in=amount,
        expected_out_wei=expected,
        actual_out_wei=actual,
        sell_tax_pct=tax,
    )
