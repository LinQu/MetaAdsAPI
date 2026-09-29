"""Ringkasan proses yang dicetak ke log setelah ekspor selesai."""

import argparse
import os
from datetime import datetime

from .logging_utils import info
from .paths import auxiliary_output_directory


def format_elapsed_seconds(seconds: float) -> str:
    """Format elapsed seconds as HH:MM:SS, retaining hours beyond 24."""
    total_seconds = max(0, int(round(float(seconds))))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return "{:02d}:{:02d}:{:02d}".format(hours, minutes, secs)


def print_summary(
    args: argparse.Namespace,
    since: str,
    until: str,
    date_source: str,
    result,
    total_accounts: int,
    skipped_accounts: int,
    row_count: int,
    error_count: int,
    checkpoint_path: str,
    checkpoint_kept: bool,
    started_at: datetime,
    finished_at: datetime,
    elapsed_seconds: float,
) -> None:
    info("RINGKASAN")
    info("Mode              : {}".format(args.mode))
    info("Status            : {}".format(args.status))
    info("Sumber akun       : {}".format(args.input_source))
    info("Lokasi output     : {}".format(args.output_location))
    technical_dir = (
        os.path.dirname(result.error_file)
        if result.error_file
        else os.path.abspath(auxiliary_output_directory())
    )
    info("Folder teknis     : {}".format(technical_dir))
    info("Mulai proses      : {}".format(started_at.strftime("%Y-%m-%d %H:%M:%S")))
    info("Selesai proses    : {}".format(finished_at.strftime("%Y-%m-%d %H:%M:%S")))
    info("Durasi proses     : {}".format(format_elapsed_seconds(elapsed_seconds)))
    if result.report_file.lower().endswith(".csv"):
        delimiter_display = {
            "comma": "comma (,)" ,
            "tab": "tab (\\t)",
            "pipe": "pipe (|)",
            "semicolon": "semicolon (;)",
        }.get(args.csv_delimiter, args.csv_delimiter)
        info("Delimiter CSV     : {}".format(delimiter_display))
        info("Header CSV        : {}".format("tidak" if args.csv_no_header else "ya"))
    info("Periode           : {} s.d. {} ({})".format(since, until, date_source))
    info("Total akun sumber : {}".format(total_accounts))
    info("Akun dari resume  : {}".format(skipped_accounts))
    info("Total baris output: {}".format(row_count))
    info("Total error       : {}".format(error_count))
    info("File laporan      : {}".format(result.report_file))
    if result.error_file:
        info("File error        : {}".format(result.error_file))
    if result.info_file:
        info("File informasi    : {}".format(result.info_file))
    info(
        "Checkpoint        : {} ({})".format(
            checkpoint_path,
            "disimpan" if checkpoint_kept else "dihapus setelah sukses",
        )
    )
