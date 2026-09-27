# Katalog Fitur

## Aturan Utama

1. Setiap fitur dihitung pada `as_of_block = snapshot_block`
2. Hanya boleh memakai data dengan `block_number <= as_of_block`
3. Fungsi fitur tidak boleh membaca tabel `labels`
4. Setiap perubahan definisi fitur menaikkan `feature_version`
5. Nilai yang tidak tersedia disimpan sebagai `null`, bukan 0. LightGBM bisa menangani missing value

Signature standar:

```python
def compute_features(token: str, as_of_block: int, db: Session) -> dict[str, float | int | bool | None]:
    ...
```

## A. Kontrak

| Fitur | Tipe | Keterangan |
|---|---|---|
| `is_verified` | bool | Source code terverifikasi di explorer pada saat snapshot (jika explorer tidak menyediakan waktu verifikasi, catat sebagai keterbatasan) |
| `owner_renounced` | bool | Ownership sudah ke alamat nol sebelum `as_of_block` |
| `has_mint_fn` | bool | Ada fungsi mint yang bisa dipanggil owner |
| `has_blacklist_fn` | bool | Ada fungsi blacklist / blocklist |
| `has_settable_tax` | bool | Pajak bisa diubah owner |
| `is_proxy` | bool | Kontrak upgradeable |
| `bytecode_similarity_to_scam` | float | Opsional v2. Kemiripan bytecode dengan token scam di data latih. **Rawan leakage**, hanya boleh memakai token yang labelnya sudah final sebelum `as_of_block` |

Deteksi fungsi dilakukan dari ABI / source code terverifikasi. Untuk kontrak tidak terverifikasi, nilai `null`.

## B. Likuiditas

| Fitur | Tipe | Keterangan |
|---|---|---|
| `initial_liquidity_wbnb` | float | WBNB pada `Mint` pertama |
| `liquidity_wbnb_at_snapshot` | float | Cadangan WBNB pada snapshot |
| `liquidity_change_ratio` | float | Snapshot dibanding awal |
| `lp_locked_pct` | float | Persentase LP di locker yang dikenal |
| `lp_burned_pct` | float | Persentase LP di alamat burn |
| `lp_held_by_deployer_pct` | float | Persentase LP di deployer dan wallet terkait |
| `lock_min_remaining_days` | float | Sisa waktu lock terpendek. `null` jika tidak dikunci |

## C. Distribusi Holder

| Fitur | Tipe | Keterangan |
|---|---|---|
| `holder_count` | int | Jumlah alamat dengan saldo > 0 (kecuali pair dan alamat burn) |
| `top10_holder_pct` | float | Persentase supply di 10 holder teratas (kecuali pair, burn, locker) |
| `deployer_supply_pct` | float | Persentase supply di deployer dan wallet terkait |
| `wallets_funded_by_deployer` | int | Holder yang menerima token langsung dari deployer |
| `holder_gini` | float | Koefisien Gini distribusi saldo |

Saldo dihitung dengan merekonstruksi `token_transfers` sampai `as_of_block`, bukan dengan memanggil `balanceOf` di block terbaru.

## D. Riwayat Deployer

| Fitur | Tipe | Keterangan |
|---|---|---|
| `deployer_age_days` | float | Umur wallet deployer saat T0 |
| `deployer_prior_tokens` | int | Token yang dibuat cluster deployer sebelum T0 |
| `deployer_prior_rugs` | int | Token sebelumnya yang **labelnya sudah final sebelum `as_of_block`** dan berlabel scam |
| `deployer_prior_rug_ratio` | float | `prior_rugs / prior_tokens` |
| `deployer_funded_by_cex` | bool | Dana awal dari exchange yang dikenal |

**Peringatan leakage:** `deployer_prior_rugs` hanya boleh menghitung token lama yang peristiwa rug-nya terjadi sebelum `as_of_block`. Token lama yang di-rug setelah snapshot token saat ini belum "diketahui" di dunia nyata.

## E. Aktivitas Trading Awal (T0 sampai snapshot)

| Fitur | Tipe | Keterangan |
|---|---|---|
| `buy_count` | int | Jumlah swap beli |
| `sell_count` | int | Jumlah swap jual |
| `buy_sell_ratio` | float | `buy_count / max(sell_count, 1)` |
| `unique_buyers` | int | Alamat unik yang membeli |
| `unique_sellers` | int | Alamat unik yang menjual |
| `sellers_to_buyers_ratio` | float | Indikator awal honeypot (banyak pembeli, hampir tidak ada penjual) |
| `volume_wbnb` | float | Total volume dalam WBNB |
| `first_hour_buy_share` | float | Porsi pembelian di jam pertama (indikasi bot / sniper milik deployer) |

## F. Simulasi di Snapshot

| Fitur | Tipe | Keterangan |
|---|---|---|
| `sell_sim_ok` | bool | Hasil simulasi jual pada snapshot |
| `sell_tax_pct` | float | Pajak jual efektif |
| `buy_tax_pct` | float | Pajak beli efektif |

Fitur ini sah dipakai karena tersedia pada saat prediksi. Wajar jika fitur ini sangat kuat untuk kelas honeypot.

## Fitur yang Dilarang

- Apa pun yang dihitung setelah `as_of_block`
- Harga atau likuiditas di masa depan
- Jumlah token yang sama dari deployer yang di-rug setelah snapshot
- ID atau alamat mentah sebagai fitur (model akan menghafal, bukan belajar pola)
