# Changelog 5.4.6

Basis: v5.4.4 CSV no-header. Perubahan portable `.env` dari build v5.4.5 sebelumnya tidak dibawa ke build ini.

## Baru

- Tambah `--output-location` / `--lokasi-output`.
- `default`: mempertahankan perilaku output v5.4.4.
- `project`: simpan laporan di folder project yang berisi `ScrapeMeta.py`.
- `home`: simpan laporan di `~/laporan`; folder dibuat otomatis saat ekspor.
- Mendukung `META_OUTPUT_LOCATION=default|project|home`.
- `--output` relatif digabung dengan base folder yang dipilih.
- `--output` absolut selalu menjadi override dan tidak dipindahkan.
- File utama, `_errors`, `_info`, dan checkpoint mengikuti folder output yang sama.
- Tidak ada dependency Python baru.

## Pengujian

41 automated tests berhasil, termasuk output project/home dan kompatibilitas default v5.4.4.
