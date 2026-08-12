# Pemetaan CSV Meta Ads ke struktur AHM

Dokumen ini hanya rekomendasi pemetaan. Program tidak melakukan koneksi, `INSERT`, `UPDATE`, atau `DELETE` ke database AHM.

| Index | Kolom CSV | Field AHM | Offset | Tipe AHM | Catatan |
|---:|---|---|---:|---|---|
| 1 | ID ACCOUNT | `ahmno1` | 360 | `TEXT[31]` | Identifier akun Meta sebagai teks |
| 2 | Nama akun | `ahmnama1` | 1450 | `TEXT[101]` | Nama akun Meta |
| 3 | ID kampanye | `ahmno2` | 391 | `TEXT[31]` | Identifier kampanye sebagai teks |
| 4 | Nama kampanye | `ahmket1` | 746 | `TEXT[251]` | Nama kampanye |
| 5 | ID iklan | `ahmno3` | 422 | `TEXT[31]` | Identifier iklan sebagai teks |
| 6 | Nama iklan | `ahmket2` | 997 | `TEXT[251]` | Nama iklan |
| 7 | Tanggal | `ahmtgl1` | 2056 | `LONG` | Konversi mengikuti format tanggal internal AHM. |
| 8 | Waktu (zona waktu akun iklan) | `ahmstr301` | 3064 | `TEXT[31]` | Contoh `07:00 - 07:59`. |
| 9 | Impresi | `ahmjml1` | 2096 | `double` | Jumlah impresi |
| 10 | Frekuensi | `ahmjml5` | 3712 | `double` | Nilai frequency dari Meta Insights. |
| 11 | Klik tautan | `ahmjml2` | 2104 | `double` | Jumlah klik tautan |
| 12 | CTR klik tautan | `ahmjml3` | 2112 | `double` | CSV menyimpan angka persen, misalnya `2.5`. |
| 13 | Biaya per klik tautan | `ahmhrg1` | 2128 | `double` | Biaya per klik |
| 14 | Hasil | `ahmjml4` | 2120 | `double` | Hasil utama |
| 15 | Biaya per hasil | `ahmhrg2` | 2136 | `double` | Biaya per hasil |
| 16 | Jumlah yang dibelanjakan | `ahmtotal` | 4000 | `double` | Total spend |
| 17 | CABANG | `ahmcab` | 79 | `TEXT[31]` | Cabang |
| 18 | BISNIS | `ahmdvs` | 110 | `TEXT[31]` | Rekomendasi unit bisnis ke Divisi |
| 19 | Tanggal proses | `ahmtgl2` | 2060 | `LONG` | Konversi mengikuti tanggal internal AHM |

## Kunci logis yang disarankan

```text
ID ACCOUNT + ID kampanye + ID iklan + Tanggal + Waktu
```

`TOKEN` dari file input tidak masuk CSV dan tidak memiliki pemetaan ke AHM.
