# Arsitektur

## 1. Gambaran Umum

```
                 BNB Chain (RPC biasa + RPC archive)      Explorer API
                            │                                  │
                            ▼                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│ pipeline (Python)                                                  │
│                                                                    │
│  indexer ──► Parquet (raw events) ───► labeling ──► labels         │
│                     │                                              │
│                     ├──► features (as_of_block) ──► feature_snaps  │
│                     │                                              │
│  simulation (anvil fork) ──► sell_simulations                      │
│                                                                    │
│  training: labels + feature_snaps ──► model artifact + metrics     │
│  scoring:  model + feature_snaps ──► predictions                   │
└────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
                 FastAPI (read-only ke tabel predictions)
                            │
                            ▼
                 Next.js dashboard (server-side fetch ke API)
```

## 2. Komponen

| Komponen | Tanggung jawab |
|---|---|
| `chain/` | Client RPC dengan retry dan backoff, client explorer API, `block_at_timestamp()` (binary search) |
| `indexer/` | Ambil event `PairCreated` dari factory (tokens/pairs ke Postgres), lalu `Sync`, `Mint`, `Burn`, `Swap`, `Transfer` LP dan transfer token ke Parquet lokal. Checkpoint per job di Postgres |
| `simulation/` | Simulasi beli lalu jual di fork untuk mendeteksi honeypot dan mengukur pajak |
| `labeling/` | Menentukan label per token berdasarkan data setelah snapshot |
| `features/` | Menghitung fitur point-in-time pada `as_of_block` |
| `training/` | Membangun dataset, split, training, kalibrasi, evaluasi, menyimpan model |
| `api/` | Menyajikan prediksi yang sudah dihitung |
| `web/` | Menampilkan hasil ke user |

### Penyimpanan

| Data | Tempat | Alasan |
|---|---|---|
| Event mentah (swap, sync, mint, burn, transfer LP, transfer token) | Parquet di `data/raw/<tabel>/<job>/<a>_<b>.parquet` (tidak di-commit) | 1 hari data ~517 MB di Postgres vs ~48 MB Parquet (zstd). Tiga bulan tidak muat di Supabase free tier |
| tokens, pairs, deployers, label, fitur, simulasi, model, prediksi, checkpoint | Postgres (Supabase) | Kecil, dan dibutuhkan API |

Satu file Parquet per chunk block dengan nama deterministik, ditulis atomik (tmp lalu rename), dan checkpoint disimpan setelah file selesai. Menjalankan ulang chunk menimpa file yang sama, jadi tidak ada duplikat. Pembaca tetap dedupe dengan `(tx_hash, log_index)` untuk berjaga-jaga jika ukuran chunk pernah diubah.

## 3. Konsep Waktu (Penting)

Untuk setiap token:

- **T0**: block tempat `PairCreated` terjadi
- **Snapshot**: block pertama dengan timestamp ≥ `timestamp(T0) + 24 jam`. Semua fitur dihitung pada block ini
- **Jendela label**: dari snapshot sampai `timestamp(T0) + 30 hari`

```
T0 ──── 24 jam ────► snapshot ─────────── sampai hari ke-30 ──────►
        (fitur boleh pakai data di sini)   (label ditentukan di sini)
```

Token yang sudah di-rug **sebelum** snapshot dikeluarkan dari dataset training, karena pada saat prediksi token itu sudah mati dan fiturnya pasti membocorkan label. Jumlahnya tetap dicatat di laporan.

Block time BNB Chain berubah beberapa kali (hardfork mempercepat block time), jadi konversi waktu ke block selalu memakai timestamp, bukan jumlah block.

## 4. Konstanta Kontrak

Semua disimpan di `pipeline/src/pipeline/config.py`. **Verifikasi ulang setiap alamat dari dokumentasi resmi sebelum dipakai.**

| Nama | Keterangan |
|---|---|
| `PANCAKE_V2_FACTORY` | Factory PancakeSwap V2 (sumber event `PairCreated`) |
| `PANCAKE_V2_ROUTER` | Router V2 (dipakai untuk simulasi swap) |
| `WBNB` | Token WBNB |
| `DEAD_ADDRESSES` | Alamat burn (`0x000...000`, `0x000...dEaD`) |
| `KNOWN_LOCKERS` | Daftar kontrak locker LP (PinkLock, Unicrypt, Team Finance, dll). Dikelola manual |
| `KNOWN_CEX_WALLETS` | Hot wallet exchange, dikecualikan dari clustering deployer |

## 5. Simulasi Honeypot

Pendekatan utama memakai fork lokal karena paling andal:

1. Jalankan `anvil` fork pada block tertentu (butuh RPC archive untuk block historis)
2. Pilih wallet holder yang **membeli lewat swap**, bukan deployer (deployer sering masuk whitelist sehingga bisa jual)
3. `anvil_impersonateAccount` wallet tersebut
4. Approve router, lalu jual sebagian kecil token lewat `swapExactTokensForETHSupportingFeeOnTransferTokens`
5. Bandingkan hasil nyata dengan `getAmountsOut` untuk menghitung pajak efektif
6. Opsional: simulasi beli dari wallet baru untuk mengukur pajak beli

Hasil: `sell_ok` (bool), `sell_tax_pct`, `buy_tax_pct`, `revert_reason`.

Semua ini terjadi di fork lokal. Tidak ada transaksi yang dikirim ke jaringan asli.

## 6. Mode Operasi

| Mode | Deskripsi | Versi |
|---|---|---|
| Batch historis | Backfill, labeling, training | v1 |
| Scoring batch | Menilai token dalam periode tertentu | v1 |
| Live scoring | Worker yang memantau pair baru dan menilai di jam ke-24 | v2 (keputusan terbuka) |

## 7. Penanganan Kegagalan

- RPC error: retry dengan exponential backoff, batasi ukuran range `eth_getLogs`, turunkan otomatis jika kena limit
- Indexer terputus: lanjut dari checkpoint terakhir
- Simulasi gagal karena alasan teknis (bukan revert dari kontrak): tandai `simulation_status = error`, jangan dianggap honeypot
- Data tidak lengkap: token ditandai `incomplete` dan tidak masuk training
