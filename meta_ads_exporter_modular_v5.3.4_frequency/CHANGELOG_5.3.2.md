# Changelog 5.3.2 - Daily Results untuk mode rinci

## Masalah yang diperbaiki

Pada mode rinci, sebelumnya `Hasil` dibaca dari response Insights yang memakai breakdown:

`hourly_stats_aggregated_by_advertiser_time_zone`

Untuk beberapa objective/performance goal, penjumlahan result per jam tidak sama dengan field `results` pada query harian tanpa breakdown. Contoh yang memicu perubahan ini: result harian Meta = 9, sedangkan penjumlahan result hourly = 24.

## Desain baru

Mode rinci sekarang memakai dua request terpisah:

1. **Hourly delivery request**
   - breakdown: `hourly_stats_aggregated_by_advertiser_time_zone`
   - sumber: impresi, klik tautan, CTR klik tautan, CPC link, spend
   - tidak meminta `results`/`actions`

2. **Daily results request**
   - `time_increment=1`
   - tanpa `breakdowns`
   - sumber: `results`, `cost_per_result`, dan spend harian
   - `use_unified_attribution_setting=true`

`Hasil` dan `Biaya per hasil` harian ditulis hanya pada baris jam paling awal yang tersedia untuk setiap kombinasi `ID iklan + Tanggal`. Baris jam berikutnya dikosongkan. Dengan demikian, `SUM(Hasil)` untuk satu iklan/tanggal tidak berlipat 24 kali dan mengikuti result harian Meta.

## File yang berubah

- `meta_ads_tool/api.py`
- `meta_ads_tool/metrics.py`
- `meta_ads_tool/runner.py`
- `meta_ads_tool/transform.py`
- `meta_ads_tool/checkpoint.py` (schema checkpoint dinaikkan ke 3)
- `meta_ads_tool/__init__.py` (versi 5.3.2)
- `tests/test_core.py`

## Catatan resume

Karena semantik `Hasil` berubah, checkpoint lama sebaiknya tidak digunakan. Schema checkpoint dinaikkan agar proses baru tidak mencampur row lama dan row baru.
