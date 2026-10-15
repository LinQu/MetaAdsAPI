# Meta Ads Exporter 5.5.1

Exporter Meta Ads modular untuk menghasilkan laporan XLSX atau CSV. Program mendukung source akun dari **Excel** atau **API DATAMETA**, token berbeda per akun, retry, checkpoint/resume, data rinci hourly, result/frequency harian, dan output CSV untuk integrasi database.

## Instalasi

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

## Source akun 1: Excel

Default tetap Excel sehingga command versi lama masih kompatibel.

Header wajib A:D:

```text
ID ACCOUNT | TOKEN | CABANG | BISNIS
```

Contoh:

```bash
python3 ScrapeMeta.py \
  --mode rinci \
  --status semua \
  --since 2026-07-01 \
  --until 2026-07-31 \
  --format csv \
  daftar_akun_meta.xlsx
```

Atau eksplisit:

```bash
python3 ScrapeMeta.py \
  --sumber-akun excel \
  --mode rinci \
  --status semua \
  --since 2026-07-01 \
  --until 2026-07-31 \
  --format csv \
  daftar_akun_meta.xlsx
```

## Source akun 2: API DATAMETA

Endpoint default:

```text
https://api2nss.nusantara-sakti.co.id/ksapisvr
```

Program melakukan `POST` JSON berbentuk:

```json
{
  "api_jsoncmonss": [
    {
      "Request": "DATAMETA",
      "noHP": "<diisi dari konfigurasi>",
      "tanggalAwal": "2026-07-01",
      "tanggalAkhir": "2026-07-31",
      "latMulai": "0.00",
      "lonMulai": "0.00",
      "jamMulai": "-10:00:00"
    }
  ]
}
```

`tanggalAwal` dan `tanggalAkhir` otomatis memakai periode report. Jadi tidak perlu mengisi tanggal dua kali.

Response yang diharapkan:

```json
{
  "status": "ok",
  "Detail": [
    {
      "idAcoount": "1000000000000001",
      "token": "<access-token>",
      "cabang": "34XXXX81",
      "bisnis": "MGA"
    }
  ]
}
```

Seluruh item `Detail` diproses. Token tidak ditulis ke output/log/checkpoint.

### Menjalankan source API

Disarankan simpan `noHP` di `.env`:

```text
META_ACCOUNT_SOURCE=api
META_SOURCE_API_NOHP=08xxxxxxxxxx
META_SOURCE_API_URL=https://api2nss.nusantara-sakti.co.id/ksapisvr
META_SOURCE_API_LAT=0.00
META_SOURCE_API_LON=0.00
META_SOURCE_API_JAM_MULAI=-10:00:00
```

Lalu:

```bash
python3 ScrapeMeta.py \
  --sumber-akun api \
  --mode rinci \
  --status semua \
  --since 2026-07-01 \
  --until 2026-07-31 \
  --format csv \
  --output meta_ads_juli.csv
```

Atau tanpa `.env`:

```bash
python3 ScrapeMeta.py \
  --sumber-akun api \
  --source-api-nohp "08xxxxxxxxxx" \
  --mode rinci \
  --status semua \
  --since 2026-07-01 \
  --until 2026-07-31 \
  --format csv \
  --output meta_ads_juli.csv
```

Tidak perlu memberikan file Excel pada mode API.


## Lokasi output laporan

Mulai v5.4.6, lokasi file laporan dapat dipilih tanpa menulis path panjang. Pada v5.4.7, hanya **file laporan utama** yang mengikuti lokasi tersebut; file teknis CSV dan checkpoint default tetap berada di folder project. Fitur ini tidak menambah dependency baru dan tetap dibangun dari basis v5.4.4.

Pilihan:

```text
default = perilaku v5.4.4
project = folder project yang berisi ScrapeMeta.py
home    = folder laporan di home user (~/laporan)
```

Contoh simpan ke folder project:

```bash
python3 ScrapeMeta.py \
  --sumber-akun api \
  --source-api-nohp "08xxxxxxxxxx" \
  --mode rinci \
  --status semua \
  --since 2026-07-01 \
  --until 2026-07-31 \
  --format csv \
  --output-location project \
  --output meta_ads_juli.csv
```

Jika project berada di:

```text
D:\\MetaAdsAPI\\ScrapeMeta.py
```

maka file laporan dan file teknis sama-sama berada di project karena lokasi laporan juga `project`:

```text
D:\\MetaAdsAPI\\meta_ads_juli.csv
D:\\MetaAdsAPI\\meta_ads_juli_errors.csv
D:\\MetaAdsAPI\\meta_ads_juli_info.csv
```

Contoh simpan ke home user:

```bash
python3 ScrapeMeta.py \
  --sumber-akun api \
  --source-api-nohp "08xxxxxxxxxx" \
  --mode rinci \
  --status semua \
  --since 2026-07-01 \
  --until 2026-07-31 \
  --format csv \
  --output-location home \
  --output meta_ads_juli.csv
```

Windows, contohnya menjadi:

```text
C:\\Users\\<user>\\laporan\\meta_ads_juli.csv
```

Linux/macOS, contohnya menjadi:

```text
/home/<user>/laporan/meta_ads_juli.csv
```

**Hanya file laporan utama** yang ditempatkan di `~/laporan`. File teknis tetap di folder project:

```text
<folder-project>/meta_ads_juli_errors.csv
<folder-project>/meta_ads_juli_info.csv
<folder-project>/meta_ads_juli.csv.checkpoint.sqlite3
```

Checkpoint default dihapus setelah sukses kecuali memakai `--keep-checkpoint`. Jika `--checkpoint` diberikan secara eksplisit, path checkpoint tersebut tetap dihormati.

Folder `laporan` dibuat otomatis jika belum ada. Alias Indonesia juga tersedia:

```bash
--lokasi-output project
--lokasi-output home
```

Bisa pula ditetapkan lewat `.env`:

```text
META_OUTPUT_LOCATION=project
```

atau:

```text
META_OUTPUT_LOCATION=home
```

Jika `--output` berisi **path absolut**, path absolut tersebut selalu dipakai dan `--output-location` tidak mengubahnya.

## Format CSV

Delimiter CSV sekarang fleksibel. Pilihan:

```text
comma     = ,
tab       = TAB
pipe      = |
semicolon = ;
```

Default tetap `pipe`. Contoh:

```bash
python3 ScrapeMeta.py --sumber-akun api --source-api-nohp "08xxxxxxxxxx" \
  --mode rinci --status semua --since 2026-07-01 --until 2026-07-31 \
  --format csv --csv-delimiter semicolon --output meta_ads_juli.csv
```

Alias `--delimiter` juga dapat digunakan. Literal `,`, `|`, dan `;` didukung; untuk tab gunakan `tab` agar aman di shell.

Header CSV secara default tetap ditulis. Untuk output tanpa header gunakan:

```bash
--csv-no-header
```

Alias Indonesia:

```bash
--tanpa-header-csv
```

Contoh lengkap:

```bash
python3 ScrapeMeta.py --sumber-akun api --source-api-nohp "08xxxxxxxxxx" \
  --mode rinci --status semua --since 2026-07-01 --until 2026-07-31 \
  --format csv --csv-delimiter pipe --csv-no-header --output meta_ads_juli.csv
```

Jika flag aktif, file utama, `_errors.csv`, dan `_info.csv` semuanya ditulis tanpa baris header. Output XLSX tidak terpengaruh.

Tanggal menggunakan:

```text
dd-MM-yyyy
```

Contoh:

```text
31-07-2026
```

Header CSV utama:

```text
ID ACCOUNT|Nama akun|ID kampanye|Nama kampanye|ID iklan|Nama iklan|Tanggal|Waktu (zona waktu akun iklan)|Impresi|Frekuensi|Klik tautan|CTR klik tautan|Biaya per klik tautan|Hasil|Biaya per hasil|Jumlah yang dibelanjakan|CABANG|BISNIS|Tanggal proses
```

Jika isi teks mengandung delimiter yang dipilih, Python CSV writer otomatis melakukan quoting agar struktur file tetap valid.

File pendamping:

```text
hasil.csv
hasil_errors.csv
hasil_info.csv
```

Ketiganya memakai delimiter yang sama dengan `--csv-delimiter`.

## Frequency mode rinci

Frequency mode rinci diambil dari query harian tanpa hourly breakdown. Nilai seperti:

```text
1.150628
```

dipertahankan dan diulang pada setiap row jam untuk `ID iklan + Tanggal` yang sama. Jangan `SUM(Frekuensi)` saat agregasi dashboard.

## Kolom Hasil

Mulai v5.5.1, kolom `Hasil` dibaca dari field `results` dengan urutan prioritas
tetap: **conversation lebih dulu, lalu leads**.

```text
1. actions:onsite_conversion.messaging_conversation_started_7d
   messaging_conversation_started_7d
   onsite_conversion.messaging_first_reply
2. onsite_conversion.lead_grouped
   lead
   offsite_conversion.fb_pixel_lead
   onsite_conversion.lead
```

Aturan importance:

- Satu baris hanya berisi satu jenis hasil. Angka conversation **tidak**
  dijumlahkan dengan angka leads.
- Indikator dikenali dengan maupun tanpa awalan `actions:`.
- Bila tidak ada indikator yang dikenali, `Hasil` dan `Biaya per hasil`
  dikosongkan. Ini berlaku untuk goal selain conversation dan leads (purchase,
  traffic, engagement, app install) yang belum dihitung.
- `Biaya per hasil` memakai `cost_per_result` untuk indikator yang terpilih, atau
  `Jumlah yang dibelanjakan / Hasil` bila Meta tidak menyediakannya.

Karena Meta hanya mengembalikan indikator yang sesuai *performance goal* iklan,
iklan ber-goal leads otomatis terisi dari leads tanpa konfigurasi tambahan.
Aturan ini juga tercatat pada baris `Definisi Hasil` di berkas/sheet Informasi.

### Hasil mode rinci

Hasil harian hanya ditulis sekali pada row jam paling awal per `ID iklan + Tanggal`, sehingga `SUM(Hasil)` tidak terduplikasi 24 kali.

## Preset tanggal

```text
hari-ini
kemarin
7-hari-terakhir
30-hari-terakhir
bulan-ini
bulan-lalu
```

Preset juga otomatis menjadi `tanggalAwal/tanggalAkhir` pada request DATAMETA.

## Retry source API DATAMETA

Default:

```text
--source-api-timeout 60
--source-api-retries 3
```

Retry dilakukan untuk network error, HTTP 408, 429, dan 5xx.

## Retry Meta Marketing API

```text
--max-retries 5
--retry-base-delay 1.5
--retry-max-delay 60
```

## Checkpoint

Default:

```text
<folder-project>/<nama-output>.checkpoint.sqlite3
```

Checkpoint tidak ikut dipindahkan ke `~/laporan`; hanya file laporan utama yang mengikuti `--output-location home`.

Resume:

```bash
python3 ScrapeMeta.py \
  --sumber-akun api \
  --source-api-nohp "08xxxxxxxxxx" \
  --mode rinci \
  --status semua \
  --since 2026-07-01 \
  --until 2026-07-31 \
  --format csv \
  --output meta_ads_juli.csv \
  --resume
```

Checkpoint tidak menyimpan raw token. Untuk source API, signature memakai fingerprint SHA-256 dari daftar akun dan hash token agar perubahan source terdeteksi tanpa menyimpan credential.

## Struktur kode

```text
ScrapeMeta.py
meta_ads_tool/
├── __init__.py
├── accounts/
│   ├── datameta.py      # source akun API DATAMETA
│   └── excel.py         # source akun Excel
├── cli.py               # parser argumen + orkestrasi
├── config_env.py        # konstanta env + normalisasi delimiter/status
├── constants.py         # definisi kolom output
├── dates.py
├── graph/
│   └── client.py        # MetaAdsClient (Meta Marketing API)
├── logging_utils.py
├── paths.py             # project_root, home_report_directory
├── processing/
│   ├── flatten.py       # transform response -> baris laporan
│   ├── metrics.py       # result/frequency harian
│   └── runner.py        # run_accounts
├── reporting/
│   ├── csv_writer.py    # laporan CSV + file error/informasi
│   ├── facade.py        # export_report (pilih XLSX/CSV)
│   ├── info.py          # baris sheet/berkas Informasi
│   ├── result.py        # ExportResult
│   ├── schema.py        # kolom + delimiter
│   ├── values.py        # konversi nilai sel
│   └── xlsx/
│       ├── images.py
│       ├── styles.py
│       └── writer.py
├── storage/
│   └── checkpoint.py
└── summary.py           # ringkasan + durasi proses
```

## Pengujian

```bash
python3 -m unittest discover -s tests -v
# atau
.venv/bin/python -m pytest tests/ -q
```

Versi 5.5.1 memiliki 50 automated tests: 49 unit test hermetik dan 1 golden
regression test (`tests/golden/`) yang membandingkan output terhadap 21 baseline
snapshot. Baseline tidak boleh diregenerasi tanpa alasan eksplisit; jalankan
`python3 tests/golden/regenerate.py --check` untuk memverifikasi kelengkapannya.

## Catatan keamanan

Jangan commit file Excel berisi token atau `.env` produksi ke Git. Bila access token pernah dibagikan ke tempat yang tidak seharusnya, lakukan rotasi token sebelum dipakai untuk proses produksi.

## Troubleshooting response DATAMETA bukan JSON

Mulai v5.4.1, mode API default memakai:

```bash
--source-api-body-mode auto
```

`auto` mencoba request JSON terlebih dahulu lalu form-urlencoded jika response pertama tidak dapat diparse/digunakan.

Untuk melihat diagnostic yang aman:

```bash
python3 ScrapeMeta.py \
  --sumber-akun api \
  --source-api-debug \
  --mode rinci \
  --status semua \
  --since 2026-07-01 \
  --until 2026-07-31 \
  --format csv
```

Log debug menampilkan HTTP status, Content-Type, panjang response dan preview singkat. Field token/access_token dan noHP disensor.

Jika server diketahui hanya menerima form-urlencoded, gunakan:

```bash
--source-api-body-mode form
```

Jika hanya menerima JSON body:

```bash
--source-api-body-mode json
```

## Ringkasan waktu proses

Ringkasan akhir sekarang mencatat waktu mulai, waktu selesai, dan durasi total proses:

```text
RINGKASAN
Mulai proses      : 2026-08-13 10:20:14
Selesai proses    : 2026-08-13 10:38:56
Durasi proses     : 00:18:42
```

Durasi memakai format `HH:MM:SS` dan dihitung dengan monotonic timer sehingga tidak terpengaruh perubahan jam sistem selama proses berjalan.

