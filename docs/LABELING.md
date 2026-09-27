# Labeling

Label adalah "kunci jawaban" untuk model. Kualitas label menentukan kualitas seluruh project. Semua ambang di dokumen ini adalah **nilai awal** dan wajib bisa diubah lewat config.

## 1. Kelas Label

| Label | Arti | Masuk training? |
|---|---|---|
| `rug_pull` | Likuiditas ditarik oleh deployer atau wallet terkait dalam jendela label | Ya (positif) |
| `honeypot` | Simulasi jual gagal atau pajak jual ekstrem di salah satu checkpoint | Ya (positif) |
| `clean` | Masih punya likuiditas wajar di akhir hari ke-90 | Ya (negatif) |
| `ambiguous` | Tidak memenuhi kriteria di atas | Tidak |
| `rugged_before_snapshot` | Sudah di-rug sebelum jam ke-24 | Tidak (dicatat terpisah) |

Target biner model: `is_scam = label IN ('rug_pull','honeypot')`.

## 2. Config Awal

```python
class LabelConfig(BaseModel):
    label_window_days: int = 30
    clean_check_days: int = 90
    rug_drop_ratio: float = 0.90          # likuiditas turun > 90% dari puncak
    clean_min_ratio: float = 0.30         # di hari ke-90 masih >= 30% dari puncak
    min_peak_liquidity_wbnb: float = 1.0  # di bawah ini dianggap noise
    honeypot_sell_tax_pct: float = 50.0   # pajak jual >= 50% dianggap honeypot
    honeypot_checkpoints_hours: list[int] = [24, 168, 720]
    label_version: str = "v1"
```

`min_peak_liquidity_wbnb` bisa menyingkirkan scam berukuran kecil. Catat jumlah token yang terbuang karena ambang ini di laporan dan uji sensitivitasnya.

## 3. Algoritma Rug Pull

1. Hitung `peak_wbnb` = cadangan WBNB tertinggi dari event `Sync` antara T0 dan akhir jendela label
2. Cari event `burn` di pool dalam jendela label
3. Untuk setiap burn, tentukan **siapa pelakunya**:
   - Di Uniswap V2 / PancakeSwap V2, `sender` pada event `Burn` biasanya adalah **router**, bukan user. Jadi jangan pakai `sender`
   - Gunakan `tx_from` (pengirim transaksi) dan field `to` (penerima hasil burn)
   - Cocokkan juga dengan `lp_transfers`: wallet yang mengirim LP token ke alamat pair dalam transaksi yang sama
4. Burn dianggap **oleh deployer** jika pelaku adalah deployer atau wallet terkait
5. Label `rug_pull` jika:
   - `reserve_wbnb` setelah burn tersebut `< peak_wbnb × (1 − rug_drop_ratio)`, dan
   - burn dilakukan oleh deployer atau wallet terkait
6. Jika kondisi ini terjadi sebelum snapshot, label `rugged_before_snapshot`

### Wallet Terkait

Wallet dianggap terkait dengan deployer jika salah satu berlaku:
- Menerima LP token langsung dari deployer
- Menerima dana awal (BNB) langsung dari deployer
- Berada di `cluster_id` yang sama (lihat bagian 6)

## 4. Algoritma Honeypot

1. Jalankan simulasi jual (lihat `ARCHITECTURE.md` bagian 5) pada setiap checkpoint di `honeypot_checkpoints_hours`
2. Label `honeypot` jika pada salah satu checkpoint:
   - status `reverted` karena kontrak token, atau
   - `sell_tax_pct >= honeypot_sell_tax_pct`
3. Status `error` (gagal teknis) tidak dihitung. Jika semua checkpoint `error`, token diberi label `ambiguous`

Catatan: token bisa aman di jam ke-24 lalu pajaknya dinaikkan owner di hari ke-7. Karena itu ada beberapa checkpoint.

## 5. Kriteria Clean

Label `clean` jika semua berlaku:
- Tidak memenuhi kriteria `rug_pull` maupun `honeypot`
- Di hari ke-90, `reserve_wbnb >= peak_wbnb × clean_min_ratio`
- Simulasi jual di checkpoint terakhir berstatus `ok`

## 6. Clustering Deployer

Scammer sering memakai banyak wallet. Clustering sederhana:
1. Untuk setiap deployer, cari transaksi pertama yang memberinya BNB (`funded_by`)
2. Abaikan jika sumber dana ada di `KNOWN_CEX_WALLETS` (banyak orang jujur juga didanai dari exchange)
3. Gabungkan deployer yang punya sumber dana sama dengan union-find
4. Hasilnya `cluster_id`, dipakai untuk fitur riwayat deployer dan untuk grouping saat split data

## 7. Evidence

Setiap label wajib menyimpan bukti di kolom `evidence`, contoh:

```json
{
  "peak_wbnb": "152300000000000000000",
  "post_burn_wbnb": "410000000000000000",
  "burn_tx": "0xabc...",
  "burn_block": 51234567,
  "remover": "0xdef...",
  "remover_relation": "lp_received_from_deployer"
}
```

## 8. Audit Kualitas Label

Wajib sebelum training pertama:
1. Ambil sampel acak 100 token (proporsional per kelas)
2. Periksa manual lewat block explorer
3. Hitung persentase kesesuaian
4. Jika di bawah 95%, perbaiki aturan, naikkan `label_version`, dan ulangi

Hasil audit dicatat di `reports/label_audit_<label_version>.md`.
