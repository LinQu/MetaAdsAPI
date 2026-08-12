# Meta Ads Exporter 5.4.0

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

## Format CSV 5.4.0

CSV menggunakan separator:

```text
|
```

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

Jika isi teks mengandung karakter `|`, Python CSV writer otomatis melakukan quoting agar struktur file tetap valid.

File pendamping:

```text
hasil.csv
hasil_errors.csv
hasil_info.csv
```

Ketiganya memakai delimiter `|`.

## Frequency mode rinci

Frequency mode rinci diambil dari query harian tanpa hourly breakdown. Nilai seperti:

```text
1.150628
```

dipertahankan dan diulang pada setiap row jam untuk `ID iklan + Tanggal` yang sama. Jangan `SUM(Frekuensi)` saat agregasi dashboard.

## Hasil mode rinci

`Hasil` hanya memakai indicator:

```text
actions:onsite_conversion.messaging_conversation_started_7d
```

Jika indicator tersebut tidak ada, `Hasil` dikosongkan.

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
<output>.checkpoint.sqlite3
```

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
├── api.py
├── checkpoint.py
├── cli.py
├── constants.py
├── dates.py
├── exporters.py
├── input_api.py
├── input_excel.py
├── logging_utils.py
├── metrics.py
├── runner.py
└── transform.py
```

## Pengujian

```bash
python3 -m unittest discover -s tests -v
```

Versi 5.4.0 memiliki 25 automated tests.

## Catatan keamanan

Jangan commit file Excel berisi token atau `.env` produksi ke Git. Bila access token pernah dibagikan ke tempat yang tidak seharusnya, lakukan rotasi token sebelum dipakai untuk proses produksi.
