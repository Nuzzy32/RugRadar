from typing import Any

import httpx

from pipeline.config import BSC_CHAIN_ID, EXPLORER_API_URL, settings


class ExplorerError(RuntimeError):
    pass


def _get(params: dict[str, str]) -> Any:
    # ponytail: tanpa throttle; free tier 3 req/s, tambahkan limiter saat dipakai batch.
    r = httpx.get(
        EXPLORER_API_URL,
        params={"chainid": BSC_CHAIN_ID, **params, "apikey": settings.explorer_api_key},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "1":
        raise ExplorerError(f"{data.get('message')}: {data.get('result')}")
    return data["result"]


def get_source_code(address: str) -> dict[str, Any]:
    """Kontrak belum terverifikasi tetap sukses, dengan SourceCode kosong."""
    return _get({"module": "contract", "action": "getsourcecode", "address": address})[0]
