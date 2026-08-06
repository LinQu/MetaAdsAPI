# Perubahan 5.2.2

- Mode rinci memecah permintaan Insights menjadi satu request per tanggal.
- Error "Please reduce the amount of data..." tidak lagi di-retry dengan query identik.
- Jika Meta masih menolak, program mencoba susunan field Insights yang lebih ringan.
- Jika request satu hari dengan field minimal tetap terlalu besar, error menjadi lebih jelas dan akun lain tetap diproses.
- Menambahkan test pemecahan tanggal dan klasifikasi error ukuran data.
