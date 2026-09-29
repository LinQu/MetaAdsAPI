"""Baris berkas/sheet Informasi."""

import os
from datetime import datetime
from typing import Any, List

from ..constants import CSV_DELIMITER
from .schema import csv_delimiter_label
from .values import to_csv_date


def information_rows(
    mode: str,
    status_filter: str,
    api_version: str,
    since: str,
    until: str,
    input_file: str,
    date_source: str,
    output_format: str,
    images_enabled: bool,
    input_source: str = "excel",
    source_reference: str = "",
    csv_delimiter: str = CSV_DELIMITER,
    csv_include_header: bool = True,
) -> List[List[Any]]:
    display_since = to_csv_date(since) if output_format == "csv" else since
    display_until = to_csv_date(until) if output_format == "csv" else until
    if input_source == "api":
        account_source = source_reference or "API DATAMETA"
        token_source = (
            "Field Detail.token dari API DATAMETA; token tidak ditulis ke output, "
            "log, atau checkpoint."
        )
    else:
        account_source = os.path.abspath(input_file) if input_file else ""
        token_source = (
            "Kolom TOKEN pada file input; token tidak ditulis ke output, "
            "log, atau checkpoint."
        )

    return [
        ["Parameter", "Nilai"],
        ["Mode", mode],
        ["Status", status_filter],
        ["API Version", api_version],
        ["Awal pelaporan", display_since],
        ["Akhir pelaporan", display_until],
        ["Sumber tanggal", date_source],
        ["Format output", output_format],
        [
            "Delimiter CSV",
            csv_delimiter_label(csv_delimiter) if output_format == "csv" else "-",
        ],
        [
            "Header CSV",
            ("ya" if csv_include_header else "tidak") if output_format == "csv" else "-",
        ],
        ["Gambar tertanam", "ya" if images_enabled else "tidak"],
        ["Sumber akun", input_source],
        ["Referensi sumber akun", account_source],
        ["Sumber token", token_source],
        ["Waktu pembuatan", datetime.now().astimezone().isoformat()],
        [
            "Definisi status",
            "Status efektif dibaca saat ekspor, bukan status historis pada tanggal laporan.",
        ],
        [
            "Definisi CTR",
            "inline_link_click_ctr / CTR klik tautan, bukan CTR Semua",
        ],
        [
            "Kategori waktu",
            "Dini hari 00-04; Pagi 05-10; Siang 11-14; Sore 15-17; Malam 18-23.",
        ],
    ]
