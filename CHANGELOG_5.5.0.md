# Changelog 5.5.0

Restrukturisasi internal ke subpackage. **Tidak ada perubahan perilaku**: isi CSV,
nilai sel XLSX, format, exit code, dan opsi CLI tetap sama seperti 5.4.7.

## Perubahan struktur

- `meta_ads_tool/` dipecah menjadi subpackage:
  - `accounts/` — `excel.py` (eks `input_excel.py`), `datameta.py` (eks `input_api.py`).
  - `graph/` — `client.py` (eks `api.py`).
  - `processing/` — `flatten.py` (eks `transform.py`), `metrics.py`, `runner.py`.
  - `storage/` — `checkpoint.py`.
  - `reporting/` — hasil pemecahan `exporters.py` menjadi `schema.py`, `values.py`,
    `info.py`, `csv_writer.py`, `facade.py`, `result.py`, serta `xlsx/writer.py`,
    `xlsx/styles.py`, `xlsx/images.py`.
- Modul top-level baru: `paths.py` (`project_root`, `home_report_directory`,
  `auxiliary_output_directory`), `config_env.py` (konstanta env + normalisasi
  delimiter/status), `summary.py` (ringkasan + durasi proses).
- `meta_ads_tool.exporters` dihapus dan digantikan `meta_ads_tool.reporting`
  (tanpa compatibility shim).

## Pengujian & tooling

- Golden regression harness di `tests/golden/` dengan 19 baseline snapshot yang
  membandingkan output XLSX/CSV secara deterministik (tanggal proses, waktu
  pembuatan, path, dan port disamakan). Test ke-44 sendiri adalah golden runner.
- `pyproject.toml`: metadata package, dependency runtime/dev, konfigurasi ruff
  (target `py38`, `E501` diabaikan) dan pytest. Entry point `scrape-meta`.
- Suite dibuat hermetik: tidak ada request Meta produksi saat test, dan file
  teknis (`*_errors.csv`, `*_info.csv`, checkpoint) tidak lagi bocor ke folder
  project saat test.

## Kompatibilitas

- Python 3.8+.
- Skema checkpoint dan `SCHEMA_VERSION` tidak berubah; resume dari checkpoint
  5.4.x tetap didukung.
