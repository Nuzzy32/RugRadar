# ML Pipeline

## 1. Dataset

- Satu baris per token
- Hanya token dengan status `complete` dan label `rug_pull`, `honeypot`, atau `clean`
- Target: `is_scam` (1 untuk `rug_pull` / `honeypot`, 0 untuk `clean`)
- Dataset disimpan sebagai Parquet dengan nama yang memuat `feature_version` dan `label_version`
- Catat distribusi kelas dan jumlah token yang dibuang per alasan

## 2. Split Data

Dua lapis, keduanya wajib:

1. **Holdout berdasarkan waktu.** Contoh: token dengan T0 di 80% periode pertama untuk train/validasi, 20% terakhir untuk test. Tambahkan jeda (gap) minimal 30 hari di antara keduanya supaya jendela label train tidak tumpang tindih dengan periode test
2. **Cross-validation di data train** memakai `StratifiedGroupKFold` dengan group `deployer_cluster_id`. Semua token dari satu cluster harus berada di fold yang sama

Test set hanya dievaluasi **satu kali** di akhir. Semua tuning dilakukan di CV.

## 3. Baseline

Wajib ada sebelum model ML, supaya klaim "ML lebih baik" bisa dibuktikan.

**Baseline aturan (skor 0 sampai 5):**
- +1 jika `lp_locked_pct + lp_burned_pct < 50`
- +1 jika `owner_renounced = false`
- +1 jika `has_settable_tax = true` atau `has_mint_fn = true`
- +1 jika `top10_holder_pct > 70`
- +1 jika `deployer_prior_rugs > 0`

**Baseline statistik:** logistic regression dengan fitur yang sama dengan model utama (setelah imputasi dan scaling).

## 4. Model Utama

- LightGBM (`LGBMClassifier`)
- Class imbalance ditangani dengan `scale_pos_weight` atau `class_weight`, bukan oversampling acak
- Tuning ringan (Optuna atau grid kecil) di dalam CV
- Seed dikunci untuk reproducibility

## 5. Kalibrasi

Skor mentah LightGBM belum tentu probabilitas yang benar. Kalibrasi dengan isotonic atau sigmoid pada prediksi out-of-fold. Evaluasi kalibrasi dengan reliability diagram dan Brier score.

## 6. Metrik

| Metrik | Alasan |
|---|---|
| PR-AUC | Metrik utama, cocok untuk data tidak seimbang |
| Recall pada precision ≥ 0,7 | Seberapa banyak scam tertangkap dengan tingkat salah tuduh terkendali |
| Precision@K | Kualitas daftar token paling berisiko |
| Brier score | Kualitas probabilitas setelah kalibrasi |
| ROC-AUC | Pelengkap saja |

Accuracy **tidak** dipakai sebagai metrik utama.

Laporkan metrik per kelas label (`rug_pull` vs `honeypot`) karena keduanya bisa punya performa sangat berbeda.

## 7. Threshold Level Risiko

Level ditentukan dari probabilitas terkalibrasi:
- `high`: threshold yang memberi precision ≥ 0,7 di CV
- `medium`: di antara `low` dan `high`, ditentukan dari distribusi skor
- `low`: di bawah threshold dengan recall scam yang sangat kecil

Nilai final disimpan di `model_versions.thresholds`. Kebijakan: lebih baik condong ke recall tinggi, karena kerugian user yang tertipu lebih besar dibanding user yang batal membeli token jujur.

## 8. Penjelasan (SHAP)

- Gunakan `TreeExplainer`
- Simpan 5 kontribusi terbesar yang **menaikkan** risiko per token ke `predictions.top_reasons`
- Mapping nama fitur ke kalimat yang mudah dipahami disimpan di satu file (misal `reasons_i18n.py`)

## 9. Analisis Wajib di Laporan

1. Perbandingan model vs kedua baseline di CV dan test
2. Feature importance global (SHAP summary)
3. Analisis kesalahan: contoh false positive dan false negative, beserta dugaan penyebabnya
4. Uji sensitivitas ambang label (`rug_drop_ratio`, `min_peak_liquidity_wbnb`)
5. Performa per bulan di test set untuk melihat pergeseran pola (drift)

## 10. Model Registry

Setiap training menghasilkan:
- Artifact model (`models/<model_id>/model.txt` dan kalibrator)
- `metrics.json`, `thresholds.json`, `config.json`
- Baris baru di `model_versions`

Model hanya dipromosikan ke produksi jika PR-AUC di CV lebih tinggi dari baseline di semua fold.
