# Changelog 5.3.0

## Format input baru

File XLSX wajib memiliki empat header berurutan pada kolom A:D:

1. `ID ACCOUNT`
2. `TOKEN`
3. `CABANG`
4. `BISNIS`

## Token per akun

- Setiap akun menggunakan token dari baris Excel yang sama.
- `META_ACCESS_TOKEN` tidak lagi diperlukan.
- Token tidak ditulis ke CSV, XLSX, file error, log, ataupun checkpoint SQLite.
- File input sekarang mengandung kredensial dan harus disimpan secara aman.

## Output

- `ID ACCOUNT TERBARU` diganti menjadi `ID ACCOUNT`.
- `CAB GSI` diganti menjadi `CABANG`.
- `BISNIS` ditambahkan ke XLSX dan CSV.
- CSV utama memiliki 18 kolom dan tetap menyertakan `Tanggal proses`.

## Checkpoint

- Schema checkpoint naik ke versi 2.
- Checkpoint menyimpan `account_id`, `cabang`, dan `bisnis`, tetapi tidak menyimpan token.
- Checkpoint versi lama tidak kompatibel dengan `--resume`; mulai proses baru atau hapus checkpoint lama.
