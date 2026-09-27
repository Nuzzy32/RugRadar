# Security

## 1. Aset yang Dilindungi

| Aset | Risiko |
|---|---|
| RPC URL dan API key | Disalahgunakan, kuota habis, tagihan membengkak |
| Kredensial Supabase (service role) | Akses penuh ke database |
| Integritas prediksi | Skor dimanipulasi, merugikan user atau project |
| Reputasi dan aspek hukum | UI dianggap menuduh project tertentu |

## 2. Threat Model

| Ancaman | Kontrol |
|---|---|
| Secret bocor ke repo | `.env` di `.gitignore`, `.env.example` tanpa nilai, cek `git diff --staged` sebelum push, opsional gitleaks di pre-commit |
| Secret bocor ke browser | Tidak ada secret di `NEXT_PUBLIC_*`. Web memanggil API dari server component |
| Service role terekspos | Service role hanya dipakai pipeline. API memakai role read-only |
| XSS lewat nama/simbol token | Data on-chain dianggap input tidak tepercaya. Render sebagai teks biasa, potong panjang, hapus karakter kontrol, tanpa `dangerouslySetInnerHTML`, tanpa auto-link URL |
| XSS lewat source code kontrak | Tampilkan di `<pre>` sebagai teks, atau pakai highlighter yang meng-escape output |
| Phishing lewat nama token | Nama seperti "Claim reward at xyz.com" ditampilkan apa adanya sebagai teks tanpa link, dengan label "nama dari kontrak" |
| Input alamat berbahaya | Validasi `^0x[0-9a-fA-F]{40}$` dan checksum di API sebelum query |
| SQL injection | Hanya query terparameterisasi (SQLAlchemy / psycopg) |
| Abuse API / scraping | Rate limit per IP (slowapi), cache respons, batasi page size |
| CORS terbuka | Izinkan hanya origin web sendiri |
| Error membocorkan internal | Handler error global, respons generik, detail hanya di log server |
| Manipulasi skor oleh scammer | Scammer bisa mempelajari fitur dan mengakalinya. Jangan publikasikan threshold per fitur secara detail, pantau drift, retrain berkala |
| Kode penanda tangan transaksi | Dilarang. Tidak ada private key di sistem. Simulasi hanya di fork lokal dengan impersonation |
| Dependency berbahaya | Pin versi (`uv.lock`, `pnpm-lock.yaml`), audit berkala |
| Fork anvil terekspos | `anvil` hanya bind ke `127.0.0.1`, tidak pernah dibuka ke publik |

## 3. Kontrol API

- Endpoint read-only saja:
  - `GET /health`
  - `GET /tokens/{address}/risk`
  - `GET /tokens/recent?limit=&cursor=`
- Tidak ada endpoint yang memicu indexing atau simulasi dari input publik di v1 (mencegah abuse kuota RPC)
- Header keamanan dasar di web: `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`

## 4. Aspek Hukum dan Etika

- Selalu gunakan istilah "skor risiko", tidak pernah "scam" secara pasti
- Disclaimer "bukan nasihat keuangan" di setiap halaman hasil
- Halaman metodologi menjelaskan keterbatasan dan tingkat kesalahan model
- Sediakan cara untuk melaporkan hasil yang dianggap keliru (misal email kontak)

## 5. Checklist Sebelum Deploy

- [ ] Tidak ada secret di repo dan di bundle frontend
- [ ] RLS aktif, role API read-only
- [ ] Rate limit dan CORS aktif
- [ ] Nama dan simbol token dirender aman
- [ ] Error handler tidak membocorkan stack trace
- [ ] Disclaimer tampil
