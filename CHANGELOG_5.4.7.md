# Changelog 5.4.7

Basis: v5.4.6 output-location. Perubahan portable `.env` dari build v5.4.5 tetap tidak dibawa ke build ini.

## Perubahan

- `--output-location home` sekarang memindahkan **hanya file laporan utama** ke `~/laporan`.
- File CSV pendamping `_errors.csv` dan `_info.csv` selalu disimpan di folder project yang berisi `ScrapeMeta.py`.
- Checkpoint default juga disimpan di folder project agar hanya file laporan yang berada di lokasi laporan eksternal.
- `--checkpoint <path>` tetap menjadi override jika lokasi checkpoint ingin ditentukan manual.
- Untuk `--output-location project`, laporan dan file teknis secara alami berada di folder project yang sama.
- Ringkasan akhir menampilkan `Mulai proses`, `Selesai proses`, dan `Durasi proses` (`HH:MM:SS`).
- Pengukuran durasi memakai `time.perf_counter()` agar stabil terhadap perubahan jam sistem.
- Tidak ada dependency Python baru.

## Pengujian

43 automated tests berhasil, termasuk pemisahan lokasi laporan/sidecar/checkpoint dan format durasi proses.
