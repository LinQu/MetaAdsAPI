"""Konfigurasi yang dibaca dari environment.

Semua nilai di sini dievaluasi sekali saat import, sama seperti sebelumnya saat
blok konstanta masih berada di cli.py. Nilai environment yang tidak valid tidak
menggagalkan program; ia hanya memunculkan peringatan dan memakai default.
"""

import argparse
import os

from .accounts.datameta import DEFAULT_SOURCE_API_URL
from .constants import STATUS_CHOICES
from .logging_utils import warning

OUTPUT_LOCATION_CHOICES = ("default", "project", "home")

DEFAULT_API_VERSION = os.getenv("META_API_VERSION", "v25.0").strip() or "v25.0"
DEFAULT_SHEET = os.getenv("META_ACCOUNT_SHEET", "").strip()
DEFAULT_STATUS = os.getenv("META_AD_STATUS", "aktif").strip().lower() or "aktif"
ENV_SINCE = os.getenv("META_REPORT_SINCE", "").strip()
ENV_UNTIL = os.getenv("META_REPORT_UNTIL", "").strip()
ENV_PRESET = os.getenv("META_REPORT_PRESET", "").strip()
DEFAULT_INPUT_SOURCE = os.getenv("META_ACCOUNT_SOURCE", "excel").strip().lower() or "excel"
DEFAULT_SOURCE_API_URL = (
    os.getenv("META_SOURCE_API_URL", DEFAULT_SOURCE_API_URL).strip()
    or DEFAULT_SOURCE_API_URL
)
DEFAULT_SOURCE_API_NOHP = os.getenv("META_SOURCE_API_NOHP", "").strip()
DEFAULT_SOURCE_API_LAT = os.getenv("META_SOURCE_API_LAT", "0.00").strip() or "0.00"
DEFAULT_SOURCE_API_LON = os.getenv("META_SOURCE_API_LON", "0.00").strip() or "0.00"
DEFAULT_SOURCE_API_JAM = (
    os.getenv("META_SOURCE_API_JAM_MULAI", "-10:00:00").strip() or "-10:00:00"
)
DEFAULT_SOURCE_API_BODY_MODE = (
    os.getenv("META_SOURCE_API_BODY_MODE", "auto").strip().lower() or "auto"
)
DEFAULT_CSV_DELIMITER = os.getenv("META_CSV_DELIMITER", "pipe").strip() or "pipe"
DEFAULT_OUTPUT_LOCATION = (
    os.getenv("META_OUTPUT_LOCATION", "default").strip().lower() or "default"
)


def normalize_csv_delimiter(value: str) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
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
        raise argparse.ArgumentTypeError(
            "delimiter CSV harus comma, tab, pipe, semicolon, atau simbol , \t | ;"
        )
    return canonical


def normalize_status(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "aktif": "aktif",
        "active": "aktif",
        "semua": "semua",
        "all": "semua",
        "tidak-aktif": "tidak-aktif",
        "tidakaktif": "tidak-aktif",
        "nonaktif": "tidak-aktif",
        "inactive": "tidak-aktif",
    }
    if normalized not in aliases:
        raise argparse.ArgumentTypeError(
            "status harus salah satu dari: {}".format(", ".join(STATUS_CHOICES))
        )
    return aliases[normalized]


def resolved_default_csv_delimiter() -> str:
    try:
        return normalize_csv_delimiter(DEFAULT_CSV_DELIMITER)
    except argparse.ArgumentTypeError:
        warning(
            "META_CSV_DELIMITER '{}' tidak valid; default pipe dipakai.".format(
                DEFAULT_CSV_DELIMITER
            )
        )
        return "pipe"


def resolved_default_status() -> str:
    try:
        return normalize_status(DEFAULT_STATUS)
    except argparse.ArgumentTypeError:
        warning(
            "META_AD_STATUS '{}' tidak valid; default aktif dipakai.".format(
                DEFAULT_STATUS
            )
        )
        return "aktif"
