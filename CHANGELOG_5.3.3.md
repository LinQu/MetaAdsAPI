# Changelog 5.3.3

## Hasil messaging dibuat strict

Kolom `Hasil` sekarang hanya menggunakan indicator berikut dari field Meta `results`:

`actions:onsite_conversion.messaging_conversation_started_7d`

Jika indicator tersebut tidak ada, `Hasil` dan `Biaya per hasil` dikosongkan. Program tidak lagi menggunakan fallback ke lead, purchase, link click, post engagement, atau action lain untuk menentukan Hasil.

`Biaya per hasil` menggunakan `cost_per_result` dengan indicator yang sama. Jika cost tersebut tidak tersedia tetapi indicator Hasil ada, biaya dihitung dari `spend / hasil` pada scope query yang sama.
