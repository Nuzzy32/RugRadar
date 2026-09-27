# CLAUDE.md

> File ini adalah konteks untuk Claude Code. **JANGAN di-commit.** Pastikan `CLAUDE.md` dan `.claude/` sudah ada di `.gitignore` sebelum commit pertama.

## Ringkasan Project

**RugRadar** (nama kerja, belum final) adalah sistem deteksi dini token scam di BNB Chain. Sistem memberi **skor risiko** untuk token baru berdasarkan kondisinya **24 jam setelah pair dibuat** di PancakeSwap V2.

Scope v1: **rug pull** dan **honeypot** saja.

Sifat project:
- Project portofolio, bukan produk komersial
- **Read-only** terhadap blockchain. Tidak pernah mengirim transaksi, tidak pernah memegang private key
- Output berupa skor risiko + alasan (SHAP), bukan vonis "scam"

## Dokumen Referensi

Baca dokumen yang relevan sebelum mengerjakan bagian terkait:

| Dokumen | Isi | Baca saat |
|---|---|---|
| `docs/PRD.md` | Tujuan, scope, user story, metrik sukses | Memulai fitur baru |
| `docs/ARCHITECTURE.md` | Komponen, alur data, konsep snapshot, simulasi | Menyentuh lebih dari satu modul |
| `docs/DATA_MODEL.md` | Skema database | Membuat migration atau query |
| `docs/LABELING.md` | Definisi dan algoritma label | Mengerjakan modul `labeling` |
| `docs/FEATURES.md` | Katalog fitur dan aturan point-in-time | Mengerjakan modul `features` |
| `docs/ML_PIPELINE.md` | Split data, training, evaluasi, kalibrasi | Mengerjakan modul `training` |
| `docs/SECURITY.md` | Threat model dan kontrol keamanan | Mengerjakan API, web, atau secrets |
| `docs/ROADMAP.md` | Fase kerja dan kriteria selesai | Merencanakan pekerjaan |

## Stack

| Layer | Teknologi |
|---|---|
| Pipeline data & ML | Python 3.12, uv, web3.py, pandas, pyarrow, LightGBM, scikit-learn, SHAP, pydantic |
| Simulasi transaksi | Foundry (`anvil` fork + impersonation) |
| Database | Supabase (Postgres) |
| API | FastAPI, uvicorn, slowapi (rate limit) |
| Web | Next.js 15 (App Router), TypeScript, Tailwind v4 |
| Tooling | ruff, pytest, eslint, prettier |

Jangan mengganti stack atau menambah library besar tanpa persetujuan.

## Struktur Repo

```
/
├── pipeline/                 # Paket Python (uv project)
│   ├── src/pipeline/
│   │   ├── config.py         # Semua konstanta & alamat kontrak ada di sini
│   │   ├── chain/            # Client RPC, explorer API, helper block-by-timestamp
│   │   ├── indexer/          # Ambil PairCreated, Sync, Mint, Burn, Swap, Transfer LP
│   │   ├── simulation/       # Simulasi jual (anvil fork)
│   │   ├── labeling/         # Pembuat label (TIDAK boleh diimport oleh features)
│   │   ├── features/         # Fitur point-in-time
│   │   └── training/         # Dataset builder, training, evaluasi, registry model
│   └── tests/
├── api/                      # FastAPI service
├── web/                      # Next.js dashboard
├── supabase/migrations/      # SQL migration
└── docs/
```

## Aturan Kritis (WAJIB)

1. **Point-in-time.** Setiap fungsi fitur menerima `as_of_block` dan hanya boleh membaca data dengan `block_number <= as_of_block`. Query tanpa batas block di modul `features` adalah bug.
2. **Label dan fitur terpisah.** Modul `features` tidak boleh import apa pun dari `labeling`.
3. **Split data.** Test set dipisah berdasarkan waktu. Cross-validation memakai grouping `deployer_cluster_id`. Random split dilarang.
4. **Read-only.** Tidak ada private key, tidak ada signing, tidak ada `eth_sendTransaction`. Simulasi hanya lewat `eth_call` atau `anvil` fork dengan `anvil_impersonateAccount`.
5. **Block time tidak konstan.** BNB Chain sudah beberapa kali mempercepat block time. Konversi waktu ke block selalu lewat helper `block_at_timestamp()`, jangan dihitung dari jumlah block.
6. **Indexer idempoten dan bisa dilanjutkan.** Simpan checkpoint per job. Menjalankan ulang tidak boleh menghasilkan duplikat.
7. **Angka on-chain.** Simpan nilai mentah sebagai `NUMERIC(78,0)` beserta `decimals`. Jangan pakai float untuk raw amount.
8. **Alamat.** Simpan lowercase. Tampilkan dalam format checksum.
9. **Data on-chain adalah input tidak tepercaya.** Nama token, simbol, dan source code bisa berisi HTML, URL phishing, atau karakter aneh. Escape, potong panjangnya, jangan auto-link.
10. **Konstanta terpusat.** Alamat kontrak (factory, router, WBNB, locker) hanya boleh ada di `config.py`.
11. **Wording.** UI dan API memakai istilah "skor risiko" dan level `low` / `medium` / `high`. Jangan pernah menampilkan "token ini scam" secara pasti.

## Konvensi Kode

**Python**
- Type hints wajib di semua fungsi publik
- Config dan skema data memakai pydantic
- Format dan lint dengan `ruff`
- Fungsi fitur bersifat murni: input data + `as_of_block`, output nilai. Tanpa efek samping

**TypeScript**
- `strict: true`
- Server Components secara default, Client Component hanya jika perlu interaksi
- Tidak ada secret di variabel `NEXT_PUBLIC_*`

**Git**
- Pesan commit singkat dan deskriptif (misal `feat(indexer): add Sync event backfill`)
- Tanpa emoji, tanpa atribusi AI, tanpa `Co-Authored-By` Claude
- Jalankan `git status` dan `git diff --staged` sebelum push untuk memastikan `.env` dan file Claude tidak ikut

## Perintah Umum

```bash
# Pipeline
cd pipeline && uv sync
uv run pytest
uv run ruff check . && uv run ruff format .
uv run python -m pipeline.indexer backfill --from-date 2025-07-01 --to-date 2025-12-31
uv run python -m pipeline.labeling run
uv run python -m pipeline.features build --snapshot-hours 24
uv run python -m pipeline.training train

# Simulasi (butuh RPC archive untuk block historis)
anvil --fork-url "$BSC_ARCHIVE_RPC_URL" --fork-block-number <BLOCK>

# API
cd api && uv run uvicorn app.main:app --reload

# Web
cd web && pnpm install && pnpm dev
```

## Environment Variables

| Nama | Dipakai di | Keterangan |
|---|---|---|
| `BSC_RPC_URL` | pipeline | RPC biasa untuk data terbaru |
| `BSC_ARCHIVE_RPC_URL` | pipeline | RPC archive untuk state historis dan fork |
| `EXPLORER_API_KEY` | pipeline | API explorer (cek dokumentasi Etherscan API V2 terbaru) |
| `DATABASE_URL` | pipeline, api | Koneksi Postgres Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | pipeline | Hanya untuk job backend, tidak pernah ke frontend |
| `API_BASE_URL` | web (server only) | URL FastAPI |

Semua disimpan di `.env` yang tidak di-commit. Sediakan `.env.example` tanpa nilai asli.

## Yang Tidak Boleh Dilakukan

- Menambah fitur di luar scope PRD tanpa persetujuan
- Melakukan random train/test split
- Menghitung fitur dengan data setelah `as_of_block`
- Menambahkan kode yang menandatangani atau mengirim transaksi
- Merender source code kontrak atau nama token dengan `dangerouslySetInnerHTML`
- Commit `.env`, `CLAUDE.md`, atau folder `.claude/`

## Keputusan yang Masih Terbuka

Tanyakan ke user sebelum mengasumsikan:
- Nama final project
- Provider RPC archive yang dipakai
- Periode data untuk dataset v1
- Nilai ambang label (lihat `docs/LABELING.md`, semua ada di config)
- Hosting API dan web
- Apakah mode live scoring masuk v1 atau v2
