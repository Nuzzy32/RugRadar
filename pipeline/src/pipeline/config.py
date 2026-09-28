from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw"  # event mentah (Parquet)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    bsc_rpc_url: str | None = None
    bsc_archive_rpc_url: str | None = None
    explorer_api_key: str | None = None
    database_url: str | None = None


settings = Settings()

BSC_CHAIN_ID = 56

# PancakeSwap V2, BSC mainnet. Lowercase per konvensi penyimpanan.
# Sumber: https://developer.pancakeswap.finance/contracts/v2/addresses
PANCAKE_V2_FACTORY = "0xca143ce32fe78f1f7019d7d551a6402fc5350c73"
PANCAKE_V2_ROUTER = "0x10ed43c718714eb63d5aa57b78b54704e256024e"
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
# Multicall3, alamat sama di semua chain EVM. Sumber: https://www.multicall3.com
MULTICALL3 = "0xca11bde05977b3631167028862be2a173976ca11"

DEAD_ADDRESSES = frozenset(
    {
        "0x0000000000000000000000000000000000000000",
        "0x000000000000000000000000000000000000dead",
    }
)

SNAPSHOT_HOURS = 24

# Indexer
INDEX_WINDOW_DAYS = 30  # event pool disimpan dari T0 sampai T0 + jendela label
MAX_TOKEN_AGE_AT_PAIR_DAYS = 7  # token yang dibuat jauh sebelum pair-nya bukan "token baru"
LOGS_BLOCK_STEP = 50_000  # batas range eth_getLogs NodeReal
LOGS_ADDRESS_BATCH = 300

# Etherscan API V2. Free tier BSC: getsourcecode jalan, getcontractcreation tidak
# (deployer diambil lewat chain.rpc.get_contract_creation).
EXPLORER_API_URL = "https://api.etherscan.io/v2/api"
