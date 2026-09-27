# PRD: RugRadar

## 1. Latar Belakang

Setiap hari ribuan token baru dibuat di BNB Chain dan sebagian besar berakhir sebagai scam. Korban umumnya membeli di jam-jam awal karena FOMO, sebelum ada tanda yang jelas. Tool yang ada kebanyakan memeriksa aturan statis (LP dikunci atau tidak, kontrak terverifikasi atau tidak) dan tidak mempertimbangkan kombinasi sinyal maupun riwayat deployer.

## 2. Tujuan

1. Memprediksi kemungkinan token mengalami rug pull atau honeypot dalam 30 hari, berdasarkan kondisi token pada 24 jam setelah pair dibuat.
2. Memberikan alasan yang bisa dipahami untuk setiap skor.
3. Membuktikan secara terukur bahwa model ML lebih baik dari baseline berbasis aturan.

## 3. Non-Goals (v1)

- Mendeteksi soft rug / dev dump bertahap
- DEX selain PancakeSwap V2, pair selain WBNB
- Chain selain BNB Chain
- Fitur trading, alert Telegram, akun user, atau pembayaran
- Menjamin token aman

## 4. Pengguna

| Persona | Kebutuhan |
|---|---|
| Trader ritel | Cek cepat apakah token baru berisiko sebelum membeli |
| Peneliti / recruiter | Melihat metodologi, metrik, dan kualitas analisis |

## 5. User Story

1. Sebagai trader, saya bisa memasukkan alamat token dan melihat skor risiko beserta 3 sampai 5 alasan utamanya.
2. Sebagai trader, saya bisa melihat daftar token baru yang sudah dinilai, diurutkan dari yang terbaru.
3. Sebagai peneliti, saya bisa membuka halaman metodologi yang menjelaskan definisi label, metrik evaluasi, dan keterbatasan model.
4. Sebagai trader, saya mendapat pesan jelas jika token belum diindeks atau belum berumur 24 jam.

## 6. Fitur MVP

| Fitur | Deskripsi |
|---|---|
| Indexer historis | Backfill pair baru dan event pool untuk periode tertentu |
| Labeling otomatis | Label rug pull dan honeypot sesuai `LABELING.md` |
| Feature pipeline | Fitur point-in-time pada snapshot 24 jam |
| Model + baseline | LightGBM terkalibrasi dan baseline aturan |
| API | Endpoint skor risiko, daftar token, health check |
| Dashboard | Halaman cek token, feed token, halaman metodologi |

## 7. Halaman Web

1. **Beranda / cek token**: input alamat, hasil skor (level `low` / `medium` / `high`), probabilitas, alasan SHAP, ringkasan data token.
2. **Feed token**: tabel token terbaru dengan skor, umur, likuiditas.
3. **Metodologi**: definisi label, fitur utama, metrik model vs baseline, keterbatasan, disclaimer.

State wajib: loading, error, token tidak ditemukan, token belum 24 jam, data belum lengkap.

## 8. Metrik Sukses

Target, bukan janji. Angka final ditentukan setelah melihat data.

| Metrik | Target |
|---|---|
| Kualitas label (audit manual 100 sampel) | Kesesuaian minimal 95% |
| PR-AUC model vs baseline | Model lebih tinggi secara konsisten di semua fold dan test set |
| Recall pada precision minimal 0,7 | Minimal 0,8 |
| Latensi API untuk token yang sudah diindeks | p95 di bawah 300 ms |

## 9. Risiko

- Data historis butuh RPC archive (biaya atau batasan)
- Label noise dari definisi otomatis
- Pergeseran pola scam dari waktu ke waktu
- Risiko hukum jika UI terkesan menuduh project tertentu

## 10. Keputusan Terbuka

Nama final, provider RPC archive, periode data v1, ambang label, hosting, dan apakah live scoring masuk v1.
