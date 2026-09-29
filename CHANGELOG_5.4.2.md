# Changelog 5.4.2

## Perbaikan response DATAMETA NSS

- Mendukung response legacy NSS dengan pembuka `{ status = ok , "Detail": [...] }`.
- Parser hanya menormalisasi bagian `status = ...`; token dan isi Detail tidak dimodifikasi.
- `--source-api-body-mode auto` tidak lagi fallback ke form jika response JSON mode menggunakan wrapper legacy ini.
- `CABANG` dari DATAMETA sekarang opsional. Record dengan cabang kosong tetap diproses dan output CABANG dibiarkan kosong.
- Token/noHP tetap tidak ditampilkan pada debug dan tidak disimpan ke output/checkpoint.
- User-Agent diperbarui ke `MetaAdsExporter/5.4.2`.

## Verifikasi terhadap contoh produksi

Parser diuji terhadap bentuk response yang diberikan pengguna: 131 Detail dapat dibaca, termasuk record dengan CABANG kosong.
