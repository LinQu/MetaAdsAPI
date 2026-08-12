# Changelog 5.4.0

## Sumber akun Excel atau API DATAMETA

Program sekarang mendukung dua sumber `ID ACCOUNT`, `TOKEN`, `CABANG`, dan `BISNIS`:

- `--sumber-akun excel` (default, kompatibel dengan command lama)
- `--sumber-akun api`

Endpoint default API sumber:

```text
https://api2nss.nusantara-sakti.co.id/ksapisvr
```

Body `DATAMETA` dibangun otomatis. `tanggalAwal` dan `tanggalAkhir` mengikuti periode laporan `--since/--until` atau preset.

Parser mengambil seluruh item `Detail` dan mendukung field account `idAcoount` sesuai kontrak response yang diberikan.

## CSV

- Separator berubah dari koma menjadi `|`.
- `Tanggal` dan `Tanggal proses` berformat `dd-MM-yyyy`.
- Contoh: `31-07-2026`.
- Sidecar `_errors.csv` dan `_info.csv` juga memakai separator `|`.
- `Frekuensi` tetap dipertahankan dengan nilai desimal dari Meta.

## Keamanan

- Token dari Excel maupun API hanya digunakan di memory.
- Token tidak ditulis ke laporan, log, error, info, atau checkpoint.
- Response API DATAMETA tidak dimasukkan mentah ke error message karena dapat mengandung token.
- Checkpoint memakai fingerprint SHA-256 daftar akun dan hash token, bukan raw token.
- Duplikasi `ID ACCOUNT` dari API dengan token/cabang/bisnis berbeda dihentikan agar output/checkpoint tidak tertukar.

## Reliability

- API sumber memiliki retry untuk network error, HTTP 408, 429, dan 5xx.
- API source memiliki timeout terpisah.
- Checkpoint schema dinaikkan menjadi versi 5.

## Testing

25 automated tests berhasil, termasuk:

- kompatibilitas source Excel;
- source API tanpa Excel;
- parsing seluruh `Detail`;
- body DATAMETA memakai periode laporan;
- CSV pipe-delimited;
- tanggal CSV `dd-MM-yyyy`;
- frequency tetap presisi;
- strict messaging result dari versi sebelumnya.
