# Pemetaan CSV Meta Ads ke struktur AHM

Dokumen ini hanya rekomendasi pemetaan. Program tidak melakukan koneksi, `INSERT`, `UPDATE`, atau `DELETE` ke database AHM.

| Index | Kolom CSV | Field AHM | Offset | Tipe AHM | Catatan |
|---:|---|---|---:|---|---|
| 1 | ID ACCOUNT | `ahmno1` | 360 | `TEXT[31]` | Simpan sebagai teks. |
| 2 | Nama akun | `ahmnama1` | 1450 | `TEXT[101]` | Nama akun Meta. |
| 3 | ID kampanye | `ahmno2` | 391 | `TEXT[31]` | Simpan sebagai teks. |
| 4 | Nama kampanye | `ahmket1` | 746 | `TEXT[251]` | Nama dapat panjang. |
| 5 | ID iklan | `ahmno3` | 422 | `TEXT[31]` | Simpan sebagai teks. |
| 6 | Nama iklan | `ahmket2` | 997 | `TEXT[251]` | Nama dapat panjang. |
| 7 | Tanggal | `ahmtgl1` | 2056 | `LONG` | Konversi mengikuti format tanggal internal AHM. |
| 8 | Waktu (zona waktu akun iklan) | `ahmstr301` | 3064 | `TEXT[31]` | Contoh `07:00 - 07:59`. |
| 9 | Impresi | `ahmjml1` | 2096 | `double` | Nilai jumlah. |
| 10 | Klik tautan | `ahmjml2` | 2104 | `double` | Nilai jumlah. |
| 11 | CTR klik tautan | `ahmjml3` | 2112 | `double` | CSV menyimpan angka persen, misalnya `2.5`. |
| 12 | Biaya per klik tautan | `ahmhrg1` | 2128 | `double` | Nilai biaya. |
| 13 | Hasil | `ahmjml4` | 2120 | `double` | Nilai hasil utama. |
| 14 | Biaya per hasil | `ahmhrg2` | 2136 | `double` | Nilai biaya. |
| 15 | Jumlah yang dibelanjakan | `ahmtotal` | 4000 | `double` | Total spend. |
| 16 | CABANG | `ahmcab` | 79 | `TEXT[31]` | Field cabang. |
| 17 | BISNIS | `ahmdvs` | 110 | `TEXT[31]` | Rekomendasi memakai field Divisi untuk unit bisnis. |
| 18 | Tanggal proses | `ahmtgl2` | 2060 | `LONG` | Konversi mengikuti format tanggal internal AHM. |

## Kunci logis yang disarankan

```text
ID ACCOUNT + ID kampanye + ID iklan + Tanggal + Waktu
```

`TOKEN` dari file input tidak masuk CSV dan tidak memiliki pemetaan ke AHM.
