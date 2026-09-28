-- Event mentah pindah ke Parquet lokal (data/raw/), lihat docs/DATA_MODEL.md.
-- 1 hari data = ~517 MB di Postgres vs ~48 MB Parquet; tidak muat di free tier.
drop table pool_events, lp_transfers, token_transfers;
