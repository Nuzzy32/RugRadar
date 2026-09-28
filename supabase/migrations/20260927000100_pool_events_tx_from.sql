-- Pengirim transaksi asli. Hanya diisi untuk event burn (dipakai labeling rug pull).
alter table pool_events add column tx_from evm_address;
