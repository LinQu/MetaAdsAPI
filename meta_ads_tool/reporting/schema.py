"""Skema kolom laporan dan pemetaan delimiter CSV."""

from typing import List

from ..constants import (
    CSV_DELIMITER_MAP,
    CSV_REPORT_COLUMNS,
    REKAP_COLUMNS,
    RINCI_COLUMNS,
)

_NUMERIC_COLUMNS = {
    "Impresi",
    "Jangkauan",
    "Frekuensi",
    "Klik tautan",
    "Jam mulai",
    "Biaya per klik tautan",
    "Hasil",
    "Biaya per hasil",
    "Jumlah yang dibelanjakan",
}

_ID_TEXT_COLUMNS = {
    "ID ACCOUNT",
    "ID kampanye",
    "ID set iklan",
    "ID iklan",
    "Waktu (zona waktu akun iklan)",
}

_DATE_COLUMNS = {
    "Tanggal",
    "Tanggal proses",
    "Awal pelaporan",
    "Akhir pelaporan",
}

_DATETIME_COLUMNS = {
    "Mulai",
    "Berakhir",
}


def report_columns(mode: str) -> List[str]:
    """Kolom lengkap untuk workbook XLSX."""
    return list(REKAP_COLUMNS if mode == "rekap" else RINCI_COLUMNS)


def csv_report_columns() -> List[str]:
    """Kolom ringkas CSV untuk integrasi lanjutan."""
    return list(CSV_REPORT_COLUMNS)


def resolve_csv_delimiter(value: str = "pipe") -> str:
    """Resolve canonical delimiter name or supported literal to one character."""
    raw = str(value if value is not None else "").strip().lower()
    aliases = {
        "": "pipe",
        "comma": "comma",
        ",": "comma",
        "tab": "tab",
        "\\t": "tab",
        "tsv": "tab",
        "pipe": "pipe",
        "|": "pipe",
        "vertical-bar": "pipe",
        "vertical_bar": "pipe",
        "semicolon": "semicolon",
        "semi-colon": "semicolon",
        "semi_colon": "semicolon",
        ";": "semicolon",
    }
    canonical = aliases.get(raw)
    if canonical is None:
        raise ValueError(
            "Delimiter CSV harus comma, tab, pipe, semicolon, atau simbol , \t | ;."
        )
    return CSV_DELIMITER_MAP[canonical]


def csv_delimiter_label(delimiter: str) -> str:
    labels = {
        ",": "comma (,) ",
        "\t": "tab (\\t)",
        "|": "pipe (|)",
        ";": "semicolon (;)",
    }
    return labels.get(delimiter, repr(delimiter))
