# Data Model

Database: Postgres (Supabase). Alamat disimpan lowercase `TEXT` dengan constraint format. Nilai mentah on-chain memakai `NUMERIC(78,0)`.

```sql
-- Domain helper
CREATE DOMAIN evm_address AS TEXT
  CHECK (VALUE ~ '^0x[0-9a-f]{40}$');
CREATE DOMAIN uint256 AS NUMERIC(78,0) CHECK (VALUE >= 0);
```

## Tabel Inti

```sql
CREATE TABLE tokens (
  address          evm_address PRIMARY KEY,
  name             TEXT,           -- input tidak tepercaya, dipotong maks 128 char
  symbol           TEXT,           -- dipotong maks 32 char
  decimals         SMALLINT,
  total_supply     uint256,
  deployer         evm_address,
  created_block    BIGINT,
  created_at       TIMESTAMPTZ,
  is_verified      BOOLEAN,
  status           TEXT NOT NULL DEFAULT 'indexing'
                   CHECK (status IN ('indexing','complete','incomplete'))
);

CREATE TABLE pairs (
  address          evm_address PRIMARY KEY,
  token            evm_address NOT NULL REFERENCES tokens(address),
  token_is_token0  BOOLEAN NOT NULL,
  t0_block         BIGINT NOT NULL,
  t0_timestamp     TIMESTAMPTZ NOT NULL,
  snapshot_block   BIGINT,          -- block pertama >= t0 + 24 jam
  UNIQUE (token)
);

CREATE TABLE deployers (
  address            evm_address PRIMARY KEY,
  first_seen_block   BIGINT,
  funded_by          evm_address,   -- sumber dana pertama
  cluster_id         BIGINT          -- hasil clustering funding
);
```

## Event Mentah (Parquet)

Event mentah **tidak** disimpan di Postgres, tapi di Parquet lokal (`data/raw/`), lihat `ARCHITECTURE.md` bagian Penyimpanan. Kolomnya sama dengan definisi di bawah; nilai `uint256` disimpan sebagai string desimal (exact, karena `decimal256` Parquet hanya 76 digit). Definisi SQL di bawah dipertahankan sebagai spesifikasi kolom.

```sql
CREATE TABLE pool_events (
  pair             evm_address NOT NULL REFERENCES pairs(address),
  block_number     BIGINT NOT NULL,
  block_time       TIMESTAMPTZ NOT NULL,  -- dari blockTimestamp di log
  tx_hash          TEXT NOT NULL,
  log_index        INT NOT NULL,
  event_type       TEXT NOT NULL CHECK (event_type IN ('sync','mint','burn','swap')),
  reserve_token    uint256,            -- sync
  reserve_wbnb     uint256,            -- sync
  amount_token_in  uint256,            -- arah relatif terhadap pool: swap jual / mint
  amount_wbnb_in   uint256,            -- swap beli / mint
  amount_token_out uint256,            -- swap beli / burn
  amount_wbnb_out  uint256,            -- swap jual / burn
  recipient        evm_address,        -- field "to" pada burn/swap
  tx_from          evm_address,        -- pengirim transaksi asli, hanya diisi untuk burn
  PRIMARY KEY (tx_hash, log_index)
);
CREATE INDEX ON pool_events (pair, block_number);

CREATE TABLE lp_transfers (
  pair          evm_address NOT NULL REFERENCES pairs(address),
  block_number  BIGINT NOT NULL,
  tx_hash       TEXT NOT NULL,
  log_index     INT NOT NULL,
  from_addr     evm_address NOT NULL,
  to_addr       evm_address NOT NULL,
  amount        uint256 NOT NULL,
  PRIMARY KEY (tx_hash, log_index)
);  -- juga punya kolom block_time
CREATE INDEX ON lp_transfers (pair, block_number);

CREATE TABLE token_transfers (
  token         evm_address NOT NULL REFERENCES tokens(address),
  block_number  BIGINT NOT NULL,
  tx_hash       TEXT NOT NULL,
  log_index     INT NOT NULL,
  from_addr     evm_address NOT NULL,
  to_addr       evm_address NOT NULL,
  amount        uint256 NOT NULL,
  PRIMARY KEY (tx_hash, log_index)
);  -- juga punya kolom block_time
CREATE INDEX ON token_transfers (token, block_number);
```

### Cakupan penyimpanan event

Skema Postgres sebenarnya ada di `supabase/migrations/`, skema Parquet di `pipeline/src/pipeline/indexer/events.py` (`SCHEMAS`). Untuk menghemat storage:

| Tabel | Disimpan untuk block |
|---|---|
| `pool_events` sync/mint/burn, `lp_transfers` | T0 sampai T0 + `INDEX_WINDOW_DAYS` (30 hari) |
| `pool_events` swap | T0 sampai `snapshot_block` (hanya dipakai fitur) |
| `token_transfers` | token dibuat sampai `snapshot_block` (distribusi holder) |

Cadangan hari ke-90 untuk label `clean` dibaca langsung lewat `getReserves()` di block hari ke-90 saat labeling, bukan dari event. Token yang dibuat lebih dari `MAX_TOKEN_AGE_AT_PAIR_DAYS` sebelum pair WBNB-nya tidak diindeks (bukan token baru).

## Analisis, Label, Fitur, Prediksi

```sql
CREATE TABLE contract_analysis (
  token             evm_address PRIMARY KEY REFERENCES tokens(address),
  has_mint_fn       BOOLEAN,
  has_blacklist_fn  BOOLEAN,
  has_settable_tax  BOOLEAN,
  is_proxy          BOOLEAN,
  owner_renounced_block BIGINT,       -- NULL jika belum renounce
  analyzed_at       TIMESTAMPTZ
);

CREATE TABLE sell_simulations (
  token          evm_address NOT NULL REFERENCES tokens(address),
  at_block       BIGINT NOT NULL,
  status         TEXT NOT NULL CHECK (status IN ('ok','reverted','error')),
  sell_tax_pct   NUMERIC(6,2),
  buy_tax_pct    NUMERIC(6,2),
  revert_reason  TEXT,
  PRIMARY KEY (token, at_block)
);

CREATE TABLE labels (
  token          evm_address PRIMARY KEY REFERENCES tokens(address),
  label          TEXT NOT NULL
                 CHECK (label IN ('rug_pull','honeypot','clean','ambiguous','rugged_before_snapshot')),
  evidence       JSONB NOT NULL,     -- tx hash, block, angka pendukung
  label_version  TEXT NOT NULL,      -- versi aturan label
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE feature_snapshots (
  token            evm_address NOT NULL REFERENCES tokens(address),
  as_of_block      BIGINT NOT NULL,
  feature_version  TEXT NOT NULL,
  features         JSONB NOT NULL,
  PRIMARY KEY (token, as_of_block, feature_version)
);

CREATE TABLE model_versions (
  id              TEXT PRIMARY KEY,   -- misal lgbm-2026-10-01-a
  feature_version TEXT NOT NULL,
  label_version   TEXT NOT NULL,
  metrics         JSONB NOT NULL,
  thresholds      JSONB NOT NULL,     -- batas low/medium/high
  artifact_path   TEXT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE predictions (
  token          evm_address NOT NULL REFERENCES tokens(address),
  model_id       TEXT NOT NULL REFERENCES model_versions(id),
  as_of_block    BIGINT NOT NULL,
  probability    NUMERIC(5,4) NOT NULL,
  risk_level     TEXT NOT NULL CHECK (risk_level IN ('low','medium','high')),
  top_reasons    JSONB NOT NULL,      -- [{feature, value, shap}]
  created_at     TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (token, model_id)
);

CREATE TABLE indexer_checkpoints (
  job_name     TEXT PRIMARY KEY,
  last_block   BIGINT NOT NULL,
  updated_at   TIMESTAMPTZ DEFAULT now()
);
```

## Akses (RLS)

- Aktifkan RLS di semua tabel
- Pipeline memakai service role (server only)
- API memakai role read-only yang hanya boleh `SELECT` pada `tokens`, `pairs`, `predictions`, `model_versions`
- Tidak ada akses langsung dari browser ke database
