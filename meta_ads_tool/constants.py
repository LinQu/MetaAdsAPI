"""Constants shared by the Meta Ads exporter."""

ACCOUNT_ID_HEADER = "ID ACCOUNT"
TOKEN_HEADER = "TOKEN"
CABANG_HEADER = "CABANG"
BISNIS_HEADER = "BISNIS"
INPUT_HEADERS = (
    ACCOUNT_ID_HEADER,
    TOKEN_HEADER,
    CABANG_HEADER,
    BISNIS_HEADER,
)

STATUS_CHOICES = ("aktif", "semua", "tidak-aktif")
PRESET_CHOICES = (
    "hari-ini",
    "kemarin",
    "7-hari-terakhir",
    "30-hari-terakhir",
    "bulan-ini",
    "bulan-lalu",
)
OUTPUT_FORMAT_CHOICES = ("xlsx", "csv")

REKAP_COLUMNS = [
    "ID ACCOUNT",
    "Nama akun",
    "ID kampanye",
    "Nama kampanye",
    "Tujuan kampanye",
    "ID set iklan",
    "Nama set iklan",
    "Optimasi",
    "ID iklan",
    "Nama iklan",
    "Status efektif",
    "Status konfigurasi",
    "Gambar iklan",
    "URL gambar",
    "Pengaturan atribusi",
    "Mulai",
    "Berakhir",
    "Impresi",
    "Jangkauan",
    "Frekuensi",
    "Klik tautan",
    "CTR klik tautan",
    "Biaya per klik tautan",
    "Hasil",
    "Biaya per hasil",
    "Jumlah yang dibelanjakan",
    "Mata uang",
    "Awal pelaporan",
    "Akhir pelaporan",
    "CABANG",
    "BISNIS",
]

RINCI_COLUMNS = [
    "ID ACCOUNT",
    "Nama akun",
    "ID kampanye",
    "Nama kampanye",
    "ID set iklan",
    "Nama set iklan",
    "ID iklan",
    "Nama iklan",
    "Tanggal",
    "Waktu (zona waktu akun iklan)",
    "Jam mulai",
    "Kategori waktu",
    "Pengaturan atribusi",
    "Mulai",
    "Berakhir",
    "Impresi",
    "Klik tautan",
    "CTR klik tautan",
    "Biaya per klik tautan",
    "Hasil",
    "Biaya per hasil",
    "Jumlah yang dibelanjakan",
    "Mata uang",
    "Awal pelaporan",
    "Akhir pelaporan",
    "CABANG",
    "BISNIS",
]

# Format CSV utama tetap ringkas. TOKEN sengaja tidak pernah diekspor.
CSV_REPORT_COLUMNS = [
    "ID ACCOUNT",
    "Nama akun",
    "ID kampanye",
    "Nama kampanye",
    "ID iklan",
    "Nama iklan",
    "Tanggal",
    "Waktu (zona waktu akun iklan)",
    "Impresi",
    "Klik tautan",
    "CTR klik tautan",
    "Biaya per klik tautan",
    "Hasil",
    "Biaya per hasil",
    "Jumlah yang dibelanjakan",
    "CABANG",
    "BISNIS",
    "Tanggal proses",
]

ERROR_COLUMNS = [
    "ID ACCOUNT",
    "CABANG",
    "BISNIS",
    "ID iklan",
    "Tahap",
    "Error",
]
