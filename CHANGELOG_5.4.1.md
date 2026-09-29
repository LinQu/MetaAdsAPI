# Changelog 5.4.1

## DATAMETA compatibility fix

- Menambahkan `--source-api-body-mode auto|json|form`.
- Default `auto` mencoba POST JSON lalu fallback form-urlencoded jika response pertama tidak dapat digunakan.
- Parser response menerima JSON biasa, UTF-8 BOM, nested/stringified JSON, JSON dengan prefix/suffix teks, dan form-urlencoded response.
- `Detail` yang dikirim sebagai JSON string juga dapat dibaca.
- Menambahkan `--source-api-debug` untuk menampilkan status HTTP, Content-Type, panjang body, dan preview response yang sudah disensor.
- Token/access_token dan noHP disensor dari debug preview.
- Pesan API (`message`/`pesan`/`error`) ditampilkan secara aman ketika `status` bukan ok.
- User-Agent diperbarui ke `MetaAdsExporter/5.4.1`.
