# Changelog 5.3.5

- Memperbaiki `Frekuensi` mode rinci/CSV yang sebelumnya dapat menjadi `0` ketika response hourly Meta tidak membawa field `frequency`.
- `frequency` mode rinci sekarang diambil dari query harian tanpa hourly breakdown berdasarkan `ad_id + date_start`.
- Query harian menambahkan `impressions`, `reach`, dan `frequency`.
- Jika `frequency` tidak dikirim Meta, fallback dihitung sebagai `impressions / reach`.
- Nilai frequency harian diulang pada semua row jam untuk kombinasi ad + tanggal yang sama; frequency tidak boleh dijumlahkan antar jam.
- Mode rekap tetap mengambil `frequency` langsung dari query rekap.
- Checkpoint schema dinaikkan ke versi 4 agar checkpoint lama tidak digunakan dengan semantik frequency baru.
- Logic `Hasil` tetap strict pada indicator `actions:onsite_conversion.messaging_conversation_started_7d`.
