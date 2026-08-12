# Mapping CSV Meta Ads ke tabel `dsb` — v3

Perubahan utama:
- `Nama akun` tidak disimpan.
- `Nama iklan` → `dsbket1`.
- `Nama kampanye` → `dsbket2`.
- Kolom waktu disimpan **hanya sebagai string** ke `dsbtype4`.
- `dsbjam1` tidak digunakan untuk data Meta Ads.

## Mapping CSV

| # | Kolom CSV | Field DSB | Offset | Tipe | Catatan |
|---:|---|---|---:|---|---|
| 1 | ID ACCOUNT | `dsbtype3` | 114 | `TEXT[21]` | Simpan ID Meta sebagai teks; masuk komponen index dsbdattypidx. |
| 2 | Nama akun | `-` | - | `-` | Tidak disimpan ke tabel DSB. |
| 3 | ID kampanye | `dsbkode1` | 177 | `TEXT[21]` | Simpan ID kampanye sebagai teks. |
| 4 | Nama kampanye | `dsbket2` | 868 | `TEXT[76]` | Nama kampanye untuk display. Perhatikan batas panjang field. |
| 5 | ID iklan | `dsbkode2` | 198 | `TEXT[21]` | Simpan ID iklan sebagai teks. |
| 6 | Nama iklan | `dsbket1` | 792 | `TEXT[76]` | Nama iklan untuk display. Jika melebihi kapasitas, importer harus menentukan kebijakan truncate/normalisasi. |
| 7 | Tanggal | `dsbtgl1` | 48 | `LONG` | Tanggal data Meta. Konversi mengikuti format tanggal internal sistem DSB. |
| 8 | Waktu (zona waktu akun iklan) | `dsbtype4` | 135 | `TEXT[21]` | Simpan string waktu apa adanya, contoh "00:00 - 00:59". Tidak menggunakan dsbjam1. |
| 9 | Impresi | `dsbjml1` | 388 | `double` | Jumlah impresi. |
| 10 | Frekuensi | `dsbper1` | 628 | `double` | Simpan rasio mentah, contoh 1.150628. Jangan SUM. |
| 11 | Klik tautan | `dsbjml2` | 396 | `double` | Jumlah link clicks. |
| 12 | CTR klik tautan | `dsbper2` | 636 | `double` | Simpan skala CSV apa adanya: 0.45 berarti 0.45%. |
| 13 | Biaya per klik tautan | `dsbhr1` | 708 | `double` | CPC per row. Untuk agregat lebih aman SUM(spend)/SUM(click). |
| 14 | Hasil | `dsbjml3` | 404 | `double` | Result messaging target. Pada mode rinci hasil harian hanya ditulis sekali per ad+tanggal. |
| 15 | Biaya per hasil | `dsbhr2` | 716 | `double` | Cost per result. Untuk agregat lebih aman SUM(spend)/SUM(hasil). |
| 16 | Jumlah yang dibelanjakan | `dsbtot1` | 468 | `double` | Spend/biaya iklan. |
| 17 | CABANG | `dsbtype2` | 93 | `TEXT[21]` | Cabang; masuk komponen index dashboard. |
| 18 | BISNIS | `dsbtype1` | 72 | `TEXT[21]` | Contoh MGA/HMC; masuk komponen index dashboard. |
| 19 | Tanggal proses | `dsbtglcrt` | 16 | `LONG` | Tanggal file/proses dibuat. Konversi mengikuti format tanggal internal DSB. |

## Waktu

Contoh nilai `"00:00 - 00:59"` disimpan langsung ke `dsbtype4`. Tidak dikonversi ke `dsbjam1`.

## Field teknis DSB

| Field | Offset | Tipe | Fungsi | Rekomendasi |
|---|---:|---|---|---|
| `dsbprm` | 0 | `LONG` | Primary key | Dibuat oleh mekanisme database/importer; bukan dari CSV. |
| `dsbdata` | 4 | `TEXT[11]` | Penanda dataset | Disarankan konstanta "METAADS". |
| `dsbtglcrt` | 16 | `LONG` | Tanggal buat | Diisi dari kolom Tanggal proses. |
| `dsbjamcrt` | 20 | `COUNT` | Jam buat | Opsional: jam proses/import. |
| `dsbusrcrt` | 24 | `TEXT[21]` | User buat | Opsional: misalnya "METAADSAPI". |
| `dsbtgl1` | 48 | `LONG` | Tanggal data | Diisi dari kolom Tanggal. |
| `dsbjam1` | 60 | `COUNT` | Tidak digunakan untuk Meta Ads | Bucket waktu tidak disimpan sebagai angka jam. |
| `dsbtype1` | 72 | `TEXT[21]` | BISNIS | Membantu filter index. |
| `dsbtype2` | 93 | `TEXT[21]` | CABANG | Membantu filter index. |
| `dsbtype3` | 114 | `TEXT[21]` | ID ACCOUNT | Membantu filter index. |
| `dsbtype4` | 135 | `TEXT[21]` | Waktu string | Contoh "00:00 - 00:59". |
| `dsbtype5` | 156 | `TEXT[21]` | Jenis record | Opsional: konstanta "RINCI". |
| `dsbket1` | 792 | `TEXT[76]` | Nama iklan | Nama iklan untuk display. |
| `dsbket2` | 868 | `TEXT[76]` | Nama kampanye | Nama kampanye untuk display. |
