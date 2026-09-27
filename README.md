# RugRadar

Sistem deteksi dini token berisiko (rug pull dan honeypot) di BNB Chain berbasis machine learning.

RugRadar menganalisis token baru di PancakeSwap V2 pada 24 jam pertamanya, lalu memberi **skor risiko** beserta alasan yang bisa dipahami, misalnya likuiditas belum dikunci atau deployer punya riwayat token yang ditarik likuiditasnya.

> **Disclaimer.** Project ini adalah project riset dan portofolio. Skor risiko adalah estimasi statistik, bukan vonis dan bukan nasihat keuangan. Selalu lakukan riset sendiri.

## Cara Kerja Singkat

1. **Indexer** mengumpulkan data on-chain publik: pair baru, perubahan likuiditas, distribusi holder, dan riwayat deployer.
2. **Labeling** menandai token historis yang terbukti mengalami rug pull atau honeypot.
3. **Feature pipeline** menghitung kondisi setiap token tepat di jam ke-24, tanpa memakai data masa depan.
4. **Model** (LightGBM) belajar dari pola token historis dan dibandingkan dengan baseline berbasis aturan.
5. **Dashboard** menampilkan skor risiko dan penjelasan SHAP untuk setiap token.

## Stack

Python (web3.py, LightGBM, SHAP), Foundry (simulasi transaksi via fork), Supabase (Postgres), FastAPI, Next.js 15, TypeScript, Tailwind v4.

## Struktur

```
pipeline/   Indexer, labeling, fitur, training (Python)
api/        FastAPI service
web/        Dashboard Next.js
supabase/   Migration database
docs/       Dokumentasi teknis
```

## Menjalankan Secara Lokal

```bash
cp .env.example .env        # isi RPC URL, API key, dan database URL

cd pipeline && uv sync
uv run pytest

cd ../api && uv run uvicorn app.main:app --reload
cd ../web && pnpm install && pnpm dev
```

## Dokumentasi

- [PRD](docs/PRD.md)
- [Arsitektur](docs/ARCHITECTURE.md)
- [Data Model](docs/DATA_MODEL.md)
- [Labeling](docs/LABELING.md)
- [Fitur](docs/FEATURES.md)
- [ML Pipeline](docs/ML_PIPELINE.md)
- [Security](docs/SECURITY.md)
- [Roadmap](docs/ROADMAP.md)

## Keterbatasan

- Hanya mencakup pair PancakeSwap V2 dengan WBNB
- Label dibuat secara otomatis dari data on-chain sehingga tetap mengandung noise
- Scammer terus mengubah taktik, jadi performa model bisa menurun seiring waktu
# RugRadar
