# Meta Ads Exporter 5.3.0 by Asira

Exporter Meta Ads modular untuk menghasilkan laporan XLSX atau CSV, dengan data rinci per tanggal dan jam, retry exponential backoff, pemecahan request Insights per hari, checkpoint/resume, serta token berbeda untuk setiap akun.

## Format input XLSX

Header wajib berada berurutan pada kolom A:D:

| Kolom | Header | Isi |
|---|---|---|
| A | `ID ACCOUNT` | ID akun iklan tanpa atau dengan awalan `act_` |
| B | `TOKEN` | System User Access Token untuk akun tersebut |
| C | `CABANG` | Kode atau nama cabang |
| D | `BISNIS` | Kategori/unit bisnis |

Contoh:

| ID ACCOUNT | TOKEN | CABANG | BISNIS |
|---|---|---|---|
| `123456789012345` | `EAA...` | `JKT01` | `GADAI` |
| `987654321098765` | `EAA...` | `BDG01` | `MIKRO` |

Template kosong tersedia pada `template_input_meta_ads_4_kolom.xlsx`.

Ketentuan:

- Urutan A:D harus persis seperti di atas.
- Keempat nilai wajib terisi pada setiap baris akun.
- Format kolom `ID ACCOUNT` dan `TOKEN` sebagai **Text**.
- Token dibaca per akun dan tidak pernah ditulis ke laporan, log, file error, atau checkpoint.
- File input mengandung kredensial. Batasi akses file dan jangan commit ke Git.

## Instalasi

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Token tidak perlu dimasukkan ke `.env`. `.env` hanya dipakai untuk konfigurasi opsional seperti versi API dan zona waktu.

## Ekspor CSV rinci

```bash
python3 ScrapeMeta.py \
  --mode rinci \
  --status semua \
  --since 2026-08-01 \
  --until 2026-08-05 \
  --format csv \
  daftar_akun_meta.xlsx
```

CSV utama memiliki urutan kolom:

1. `ID ACCOUNT`
2. `Nama akun`
3. `ID kampanye`
4. `Nama kampanye`
5. `ID iklan`
6. `Nama iklan`
7. `Tanggal`
8. `Waktu (zona waktu akun iklan)`
9. `Impresi`
10. `Klik tautan`
11. `CTR klik tautan`
12. `Biaya per klik tautan`
13. `Hasil`
14. `Biaya per hasil`
15. `Jumlah yang dibelanjakan`
16. `CABANG`
17. `BISNIS`
18. `Tanggal proses`

`TOKEN` tidak masuk ke CSV.

File CSV pendamping:

```text
hasil.csv
hasil_errors.csv
hasil_info.csv
```

## Ekspor XLSX rinci

```bash
python3 ScrapeMeta.py \
  --mode rinci \
  --status semua \
  --preset 7-hari-terakhir \
  --format xlsx \
  daftar_akun_meta.xlsx
```

XLSX mempertahankan kolom lengkap, termasuk ID set iklan, jam mulai, kategori waktu, mata uang, `CABANG`, dan `BISNIS`. Token tidak masuk ke workbook.

## Rekap tanpa gambar

```bash
python3 ScrapeMeta.py \
  --mode rekap \
  --status aktif \
  --preset bulan-ini \
  --tanpa-gambar \
  daftar_akun_meta.xlsx
```

## Preset tanggal

```text
hari-ini
kemarin
7-hari-terakhir
30-hari-terakhir
bulan-ini
bulan-lalu
```

## Checkpoint dan resume

Checkpoint otomatis dibuat sebagai:

```text
<output>.checkpoint.sqlite3
```

Melanjutkan proses:

```bash
python3 ScrapeMeta.py \
  --mode rinci \
  --status semua \
  --since 2026-08-01 \
  --until 2026-08-05 \
  --format csv \
  --resume \
  daftar_akun_meta.xlsx
```

Checkpoint menyimpan hasil, error, `ID ACCOUNT`, `CABANG`, dan `BISNIS`. Token tidak disimpan. Checkpoint dari versi sebelum 5.3.0 tidak kompatibel dengan skema baru.

## Retry

```bash
--max-retries 5
--retry-base-delay 1.5
--retry-max-delay 60
```

Mode rinci otomatis memecah rentang menjadi request harian untuk menghindari error:

```text
Please reduce the amount of data you're asking for
```

## Struktur kode

```text
ScrapeMeta.py
meta_ads_tool/
├── api.py
├── checkpoint.py
├── cli.py
├── constants.py
├── dates.py
├── exporters.py
├── input_excel.py
├── logging_utils.py
├── metrics.py
├── runner.py
└── transform.py
```

File yang menangani perubahan format input:

- `meta_ads_tool/constants.py`: nama header dan kolom output.
- `meta_ads_tool/input_excel.py`: membaca A:D dan memvalidasi token per akun.
- `meta_ads_tool/runner.py`: membuat `MetaAdsClient` baru menggunakan token setiap akun.
- `meta_ads_tool/transform.py`: menambahkan `CABANG` dan `BISNIS` pada baris output.
- `meta_ads_tool/exporters.py`: menulis skema XLSX/CSV tanpa token.

## Pengujian

```bash
python3 -m unittest discover -s tests -v
```

## Perubahan Hasil mode rinci sejak 5.3.2

Mode rinci memakai dua query Insights terpisah:

- **hourly** untuk `Impresi`, `Klik tautan`, `CTR klik tautan`, `Biaya per klik tautan`, dan `Jumlah yang dibelanjakan`;
- **daily tanpa breakdown jam** untuk `Hasil` dan `Biaya per hasil`.

Hal ini dilakukan karena `SUM(results per jam)` tidak selalu sama dengan `results` harian Meta Ads Manager.

Agar `Hasil` harian tidak terduplikasi 24 kali, nilai `Hasil` dan `Biaya per hasil` hanya ditulis pada baris jam paling awal untuk setiap `ID iklan + Tanggal`. Baris jam lainnya kosong pada dua kolom tersebut.

Contoh:

```text
ID iklan       Tanggal       Jam     Hasil
52510676405480 2026-07-01    00:00   9
52510676405480 2026-07-01    01:00   
...
52510676405480 2026-07-01    23:00   
```

Dengan model ini, agregasi `SUM(Hasil)` per `ID iklan + Tanggal` tetap menghasilkan `9`.
