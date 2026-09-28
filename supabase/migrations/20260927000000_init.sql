-- Skema awal. Lihat docs/DATA_MODEL.md.

create domain evm_address as text
  check (value ~ '^0x[0-9a-f]{40}$');
create domain uint256 as numeric(78, 0) check (value >= 0);

-- Inti

create table tokens (
  address        evm_address primary key,
  name           text check (char_length(name) <= 128),   -- input tidak tepercaya
  symbol         text check (char_length(symbol) <= 32),
  decimals       smallint,
  total_supply   uint256,
  deployer       evm_address,
  created_block  bigint,
  created_at     timestamptz,
  is_verified    boolean,
  status         text not null default 'indexing'
                 check (status in ('indexing', 'complete', 'incomplete'))
);

create table pairs (
  address          evm_address primary key,
  token            evm_address not null unique references tokens (address),
  token_is_token0  boolean not null,
  t0_block         bigint not null,
  t0_timestamp     timestamptz not null,
  snapshot_block   bigint             -- block pertama dengan timestamp >= t0 + 24 jam
);
create index pairs_t0_block_idx on pairs (t0_block);

create table deployers (
  address           evm_address primary key,
  first_seen_block  bigint,
  funded_by         evm_address,
  cluster_id        bigint
);

-- Event mentah. Arah in/out relatif terhadap pool.

create table pool_events (
  pair              evm_address not null references pairs (address),
  block_number      bigint not null,
  block_time        timestamptz not null,
  tx_hash           text not null,
  log_index         int not null,
  event_type        text not null check (event_type in ('sync', 'mint', 'burn', 'swap')),
  reserve_token     uint256,   -- sync
  reserve_wbnb      uint256,   -- sync
  amount_token_in   uint256,   -- swap (jual) / mint
  amount_wbnb_in    uint256,   -- swap (beli) / mint
  amount_token_out  uint256,   -- swap (beli) / burn
  amount_wbnb_out   uint256,   -- swap (jual) / burn
  recipient         evm_address,  -- field "to" pada swap/burn
  primary key (tx_hash, log_index)
);
create index pool_events_pair_block_idx on pool_events (pair, block_number);

create table lp_transfers (
  pair          evm_address not null references pairs (address),
  block_number  bigint not null,
  block_time    timestamptz not null,
  tx_hash       text not null,
  log_index     int not null,
  from_addr     evm_address not null,
  to_addr       evm_address not null,
  amount        uint256 not null,
  primary key (tx_hash, log_index)
);
create index lp_transfers_pair_block_idx on lp_transfers (pair, block_number);

create table token_transfers (
  token         evm_address not null references tokens (address),
  block_number  bigint not null,
  block_time    timestamptz not null,
  tx_hash       text not null,
  log_index     int not null,
  from_addr     evm_address not null,
  to_addr       evm_address not null,
  amount        uint256 not null,
  primary key (tx_hash, log_index)
);
create index token_transfers_token_block_idx on token_transfers (token, block_number);

-- Analisis, label, fitur, prediksi

create table contract_analysis (
  token                  evm_address primary key references tokens (address),
  has_mint_fn            boolean,
  has_blacklist_fn       boolean,
  has_settable_tax       boolean,
  is_proxy               boolean,
  owner_renounced_block  bigint,
  analyzed_at            timestamptz
);

create table sell_simulations (
  token          evm_address not null references tokens (address),
  at_block       bigint not null,
  status         text not null check (status in ('ok', 'reverted', 'error')),
  sell_tax_pct   numeric(6, 2),
  buy_tax_pct    numeric(6, 2),
  revert_reason  text,
  primary key (token, at_block)
);

create table labels (
  token          evm_address primary key references tokens (address),
  label          text not null
                 check (label in ('rug_pull', 'honeypot', 'clean', 'ambiguous', 'rugged_before_snapshot')),
  evidence       jsonb not null,
  label_version  text not null,
  created_at     timestamptz default now()
);

create table feature_snapshots (
  token            evm_address not null references tokens (address),
  as_of_block      bigint not null,
  feature_version  text not null,
  features         jsonb not null,
  primary key (token, as_of_block, feature_version)
);

create table model_versions (
  id               text primary key,
  feature_version  text not null,
  label_version    text not null,
  metrics          jsonb not null,
  thresholds       jsonb not null,
  artifact_path    text not null,
  created_at       timestamptz default now()
);

create table predictions (
  token        evm_address not null references tokens (address),
  model_id     text not null references model_versions (id),
  as_of_block  bigint not null,
  probability  numeric(5, 4) not null,
  risk_level   text not null check (risk_level in ('low', 'medium', 'high')),
  top_reasons  jsonb not null,
  created_at   timestamptz default now(),
  primary key (token, model_id)
);
create index predictions_model_id_idx on predictions (model_id);

create table indexer_checkpoints (
  job_name    text primary key,
  last_block  bigint not null,
  updated_at  timestamptz default now()
);

-- Akses: RLS aktif tanpa policy = tertutup untuk anon/authenticated.
-- Pipeline memakai role postgres/service role. Role read-only API dibuat di fase API.

do $$
declare t text;
begin
  foreach t in array array[
    'tokens', 'pairs', 'deployers', 'pool_events', 'lp_transfers', 'token_transfers',
    'contract_analysis', 'sell_simulations', 'labels', 'feature_snapshots',
    'model_versions', 'predictions', 'indexer_checkpoints'
  ] loop
    execute format('alter table %I enable row level security', t);
    execute format('revoke all on %I from anon, authenticated', t);
  end loop;
end $$;
