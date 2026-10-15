# Changelog 5.5.1

Perubahan pada isi kolom `Hasil` dan `Biaya per hasil`. Skema kolom CSV **tidak
berubah**, sehingga pemetaan AHM/DSB tetap berlaku tanpa penyesuaian.

## Perubahan

- Kolom `Hasil` kini dibaca dengan urutan prioritas tetap:
  1. indikator **conversation**
     (`onsite_conversion.messaging_conversation_started_7d`,
     `messaging_conversation_started_7d`, `onsite_conversion.messaging_first_reply`);
  2. bila tidak ada, indikator **leads**
     (`onsite_conversion.lead_grouped`, `lead`,
     `offsite_conversion.fb_pixel_lead`, `onsite_conversion.lead`);
  3. bila keduanya tidak ada, `Hasil` dan `Biaya per hasil` dikosongkan.
- Kedua keluarga angka **tidak dijumlahkan**. Satu baris tetap berisi satu jenis
  hasil, sesuai `results` yang dikembalikan Meta.
- Indikator dikenali dengan maupun tanpa awalan `actions:`.
- `Biaya per hasil` memakai `cost_per_result` untuk indikator yang terpilih. Bila
  tidak tersedia, dihitung dari `spend / hasil` pada baris yang sama.
- Goal selain conversation dan leads (purchase, traffic, engagement, app install)
  **belum dihitung** dan tetap menghasilkan kolom kosong.
- Sheet/berkas Informasi tambah baris `Definisi Hasil` yang menjelaskan aturan di
  atas.
- `SCHEMA_VERSION` checkpoint dinaikkan dari `"5"` ke `"6"`.

## Tindakan yang diperlukan

Checkpoint versi lama ditolak. Laporan bisa bercampur antara baris lama
(`Hasil` kosong untuk akun leads) dan baris baru. Hapus checkpoint lama
(`*.checkpoint.sqlite3`) atau jalankan tanpa `--resume` agar laporan bersih.

## Perbaikan internal

- Menghapus kode mati di `processing/metrics.py`: `preferred_action_types`,
  `_first_metric_pair`, `_find_metric`, `_find_cost_for_metric`, `_append_unique`.
  Fungsi-fungsi ini tidak pernah dipanggil dan memuat daftar kandidat action_type
  lawas yang membuat sumber `Hasil` tampak ambigu.
- Test: 7 unit test baru untuk prioritas conversation/lead; 2 skenario golden
  baru (`excel_rinci_lead_result`, `excel_rekap_lead_result`) untuk akun
  ber-goal leads. Total 21 skenario golden, 50 test (49 unit + 1 golden).

## Verifikasi

Seluruh 19 baseline golden lama hanya berubah satu baris, yaitu penambahan
`Definisi Hasil` pada berkas/sheet Informasi. Tidak ada perubahan angka pada
kolom laporan mana pun.
