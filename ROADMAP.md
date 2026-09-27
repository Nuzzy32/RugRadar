# Roadmap

Setiap fase punya kriteria selesai. Jangan lanjut ke fase berikutnya sebelum kriteria terpenuhi.

## Fase 0: Validasi Akses Data

- Pilih provider RPC archive dan uji `eth_getLogs` untuk range historis
- Uji `anvil` fork pada block historis
- Verifikasi alamat factory, router, WBNB dari dokumentasi resmi
- Uji endpoint explorer API yang dibutuhkan (source code, pembuat kontrak)

**Selesai jika:** bisa mengambil event satu pair lama secara lengkap dan menjalankan satu simulasi jual di fork historis.
**Go/no-go:** jika RPC archive tidak terjangkau, persempit periode data atau kurangi fitur yang butuh state historis.

## Fase 1: Setup & Indexer

- Struktur monorepo, `.gitignore` (termasuk `CLAUDE.md` dan `.claude/`), `.env.example`
- Migration database sesuai `DATA_MODEL.md`
- Indexer `PairCreated` lalu event pool, LP transfer, token transfer, dengan checkpoint
- Helper `block_at_timestamp()`

**Selesai jika:** backfill satu bulan data berjalan tanpa duplikat dan bisa dilanjutkan setelah dihentikan paksa.

## Fase 2: Labeling & Simulasi

- Clustering deployer
- Label rug pull, honeypot, clean, ambiguous, rugged_before_snapshot
- Audit manual 100 sampel

**Selesai jika:** kesesuaian audit minimal 95% dan jumlah token berlabel positif maupun negatif cukup (target awal ratusan per kelas).
**Go/no-go:** jika label positif terlalu sedikit, perpanjang periode data.

## Fase 3: Feature Pipeline

- Semua fitur di `FEATURES.md`
- Test otomatis untuk memastikan tidak ada data setelah `as_of_block` yang terbaca

**Selesai jika:** dataset Parquet terbentuk dan test leakage lulus.

## Fase 4: Baseline & Model

- Baseline aturan dan logistic regression
- LightGBM, kalibrasi, threshold, SHAP
- Laporan evaluasi sesuai `ML_PIPELINE.md` bagian 9

**Selesai jika:** model mengalahkan baseline di semua fold dan hasil test set tercatat.

## Fase 5: API

- Endpoint read-only, validasi input, rate limit, CORS, error handler

**Selesai jika:** p95 latensi di bawah 300 ms untuk token yang sudah diindeks.

## Fase 6: Dashboard

- Halaman cek token, feed, metodologi
- Semua state (loading, error, tidak ditemukan, belum 24 jam)
- Responsif dan aksesibel dasar

**Selesai jika:** alur utama berjalan dan checklist `SECURITY.md` terpenuhi.

## Fase 7: Live Scoring (opsional, v2)

- Worker yang memantau pair baru dan menilai tepat di jam ke-24

## Fase 8: Publikasi Portofolio

- README final, halaman metodologi, write-up hasil (termasuk kegagalan dan keterbatasan)
- Demo online
