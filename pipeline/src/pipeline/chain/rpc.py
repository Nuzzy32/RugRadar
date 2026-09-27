from web3 import Web3
from web3.exceptions import Web3RPCError
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import LogReceipt


def make_web3(url: str, timeout: int = 60) -> Web3:
    provider = Web3.HTTPProvider(url, request_kwargs={"timeout": timeout})
    # Retry bawaan web3 (koneksi, HTTP error termasuk 429, timeout) dengan backoff
    # eksponensial ~1+2+4+...+32 detik; default 0.125s terlalu cepat untuk rate limit.
    provider.exception_retry_configuration = provider.exception_retry_configuration.model_copy(
        update={"retries": 6, "backoff_factor": 1.0}
    )
    w3 = Web3(provider)
    # BSC menyimpan data validator di extraData (> 32 byte).
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_logs_chunked(
    w3: Web3,
    address: str | list[str],
    from_block: int,
    to_block: int,
    topics: list | None = None,
    step: int = 5_000,
) -> list[LogReceipt]:
    """eth_getLogs per potongan range; range dibelah dua tiap kali provider menolak."""
    logs: list[LogReceipt] = []
    start = from_block
    while start <= to_block:
        end = min(start + step - 1, to_block)
        params = {"address": address, "fromBlock": start, "toBlock": end}
        if topics:
            params["topics"] = topics
        try:
            chunk = w3.eth.get_logs(params)
        except Web3RPCError:
            # ponytail: semua RPC error dianggap "range terlalu besar";
            # bedakan per kode error provider kalau perlu.
            if step == 1:
                raise
            step = max(1, step // 2)
            continue
        logs.extend(chunk)
        start = end + 1
    return logs
