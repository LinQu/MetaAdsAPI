"""Hasil ekspor laporan."""

from dataclasses import dataclass


@dataclass
class ExportResult:
    report_file: str
    error_file: str = ""
    info_file: str = ""
