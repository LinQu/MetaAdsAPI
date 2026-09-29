# Changelog 5.4.3

- Menambahkan delimiter CSV fleksibel: `comma`, `tab`, `pipe`, dan `semicolon`.
- Menambahkan CLI `--csv-delimiter` / `--delimiter`.
- Mendukung literal `,`, `|`, `;` serta alias `tsv` untuk tab.
- Default tetap `pipe` agar kompatibel dengan v5.4.x sebelumnya.
- Menambahkan environment variable `META_CSV_DELIMITER`.
- File utama, `_errors.csv`, dan `_info.csv` selalu menggunakan delimiter yang sama.
- Format tanggal CSV tetap `DD-MM-YYYY`.
- Tidak mengubah source Excel/API DATAMETA, frequency harian, maupun strict messaging result.
