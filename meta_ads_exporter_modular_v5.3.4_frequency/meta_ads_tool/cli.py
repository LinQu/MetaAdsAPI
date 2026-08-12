"""Command line interface for the modular Meta Ads exporter."""

import argparse
import os
import sys
from typing import List, Optional, Tuple

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from . import __version__
from .api import MetaAdsClient
from .checkpoint import (
    CheckpointMismatchError,
    CheckpointStore,
    build_job_signature,
)
from .constants import OUTPUT_FORMAT_CHOICES, PRESET_CHOICES, STATUS_CHOICES
from .dates import normalize_preset, resolve_date_range
from .exporters import ExportResult, export_report
from .input_excel import read_accounts_from_excel, validate_input_file
from .logging_utils import error, info, warning
from .runner import run_accounts


DEFAULT_API_VERSION = os.getenv("META_API_VERSION", "v25.0").strip() or "v25.0"
DEFAULT_SHEET = os.getenv("META_ACCOUNT_SHEET", "").strip()
DEFAULT_STATUS = os.getenv("META_AD_STATUS", "aktif").strip().lower() or "aktif"
ENV_SINCE = os.getenv("META_REPORT_SINCE", "").strip()
ENV_UNTIL = os.getenv("META_REPORT_UNTIL", "").strip()
ENV_PRESET = os.getenv("META_REPORT_PRESET", "").strip()


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


def _resolved_default_status() -> str:
    try:
        return normalize_status(DEFAULT_STATUS)
    except argparse.ArgumentTypeError:
        warning(
            "META_AD_STATUS '{}' tidak valid; default aktif dipakai.".format(
                DEFAULT_STATUS
            )
        )
        return "aktif"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Ambil Meta Ads dari Excel A:D (ID ACCOUNT, TOKEN, CABANG, BISNIS) "
            "dan ekspor ke XLSX/CSV. Token digunakan per akun dan tidak diekspor. "
            "Mendukung preset tanggal, retry, checkpoint/resume, dan log realtime."
        )
    )
    parser.add_argument(
        "input_file",
        help="File XLSX dengan kolom A:D: ID ACCOUNT, TOKEN, CABANG, BISNIS.",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("rekap", "rinci"),
        help="rekap = satu baris per iklan; rinci = data harian per jam.",
    )
    parser.add_argument(
        "--status",
        type=normalize_status,
        choices=STATUS_CHOICES,
        default=_resolved_default_status(),
        help="Filter status efektif saat ekspor. Default: %(default)s.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="File output. Ekstensi boleh .xlsx atau .csv.",
    )
    parser.add_argument(
        "--format",
        "--output-format",
        dest="output_format",
        choices=OUTPUT_FORMAT_CHOICES,
        default=None,
        help="Format output. Jika kosong, diinfer dari --output atau default xlsx.",
    )
    parser.add_argument(
        "--sheet",
        default=DEFAULT_SHEET,
        help="Nama sheet input. Jika kosong, memakai sheet aktif.",
    )
    parser.add_argument("--since", default=None, help="Awal laporan YYYY-MM-DD.")
    parser.add_argument("--until", default=None, help="Akhir laporan YYYY-MM-DD.")
    parser.add_argument(
        "--preset",
        type=normalize_preset,
        choices=PRESET_CHOICES,
        default=None,
        help="Preset tanggal: {}.".format(", ".join(PRESET_CHOICES)),
    )
    parser.add_argument(
        "--api-version",
        default=DEFAULT_API_VERSION,
        help="Versi Graph API, misalnya v25.0.",
    )
    parser.add_argument(
        "--tanpa-gambar",
        action="store_true",
        help="Mode rekap XLSX: jangan unduh/sematkan gambar; URL tetap disimpan.",
    )
    parser.add_argument(
        "--image-width",
        type=int,
        default=160,
        help="Lebar maksimum gambar dalam pixel.",
    )
    parser.add_argument(
        "--image-height",
        type=int,
        default=100,
        help="Tinggi maksimum gambar dalam pixel.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Jumlah retry setelah percobaan pertama. Default: 5.",
    )
    parser.add_argument(
        "--retry-base-delay",
        type=float,
        default=1.5,
        help="Delay dasar exponential backoff dalam detik.",
    )
    parser.add_argument(
        "--retry-max-delay",
        type=float,
        default=60.0,
        help="Batas maksimum delay retry dalam detik.",
    )
    parser.add_argument(
        "--checkpoint",
        default="",
        help="Lokasi checkpoint SQLite. Default: <output>.checkpoint.sqlite3.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Lanjutkan proses dari checkpoint yang cocok.",
    )
    parser.add_argument(
        "--keep-checkpoint",
        action="store_true",
        help="Jangan hapus checkpoint setelah ekspor berhasil.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s {}".format(__version__),
    )
    return parser


def make_default_output(
    input_file: str,
    mode: str,
    status: str,
    since: str,
    until: str,
    output_format: str,
) -> str:
    directory = os.path.dirname(os.path.abspath(input_file))
    stem = os.path.splitext(os.path.basename(input_file))[0]
    filename = "{}_meta_ads_{}_{}_{}_{}.{}".format(
        stem,
        mode,
        status.replace("-", "_"),
        since.replace("-", ""),
        until.replace("-", ""),
        output_format,
    )
    return os.path.join(directory, filename)


def resolve_output(
    output_value: str,
    format_value: Optional[str],
    input_file: str,
    mode: str,
    status: str,
    since: str,
    until: str,
) -> Tuple[str, str]:
    extension = os.path.splitext(output_value)[1].lower() if output_value else ""
    inferred = ""
    if extension == ".xlsx":
        inferred = "xlsx"
    elif extension == ".csv":
        inferred = "csv"
    elif extension:
        raise ValueError("Ekstensi --output harus .xlsx atau .csv.")

    output_format = format_value or inferred or "xlsx"
    if inferred and format_value and inferred != format_value:
        raise ValueError(
            "--format {} bertentangan dengan ekstensi --output {}.".format(
                format_value,
                extension,
            )
        )

    if output_value:
        output_file = output_value
        if not extension:
            output_file += ".{}".format(output_format)
    else:
        output_file = make_default_output(
            input_file=input_file,
            mode=mode,
            status=status,
            since=since,
            until=until,
            output_format=output_format,
        )
    return os.path.abspath(output_file), output_format


def validate_runtime(
    args: argparse.Namespace,
    output_file: str,
    output_format: str,
) -> None:
    validate_input_file(args.input_file)
    if not args.api_version:
        raise RuntimeError("--api-version tidak boleh kosong.")
    if args.image_width <= 0 or args.image_height <= 0:
        raise RuntimeError("Ukuran gambar harus lebih besar dari 0.")
    if args.max_retries < 0:
        raise RuntimeError("--max-retries tidak boleh negatif.")
    if args.retry_base_delay < 0 or args.retry_max_delay < 0:
        raise RuntimeError("Delay retry tidak boleh negatif.")
    if args.retry_base_delay > args.retry_max_delay:
        raise RuntimeError(
            "--retry-base-delay tidak boleh lebih besar dari --retry-max-delay."
        )
    if output_format not in OUTPUT_FORMAT_CHOICES:
        raise RuntimeError("Format output tidak valid.")
    if os.path.abspath(args.input_file) == os.path.abspath(output_file):
        raise RuntimeError("File output tidak boleh sama dengan file input.")


def _print_summary(
    args: argparse.Namespace,
    since: str,
    until: str,
    date_source: str,
    result: ExportResult,
    total_accounts: int,
    skipped_accounts: int,
    row_count: int,
    error_count: int,
    checkpoint_path: str,
    checkpoint_kept: bool,
) -> None:
    info("RINGKASAN")
    info("Mode              : {}".format(args.mode))
    info("Status            : {}".format(args.status))
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


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        since, until, date_source = resolve_date_range(
            since_value=args.since,
            until_value=args.until,
            preset=args.preset,
            env_since=ENV_SINCE,
            env_until=ENV_UNTIL,
            env_preset=ENV_PRESET,
        )
        output_file, output_format = resolve_output(
            output_value=args.output,
            format_value=args.output_format,
            input_file=args.input_file,
            mode=args.mode,
            status=args.status,
            since=since,
            until=until,
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    try:
        validate_runtime(args, output_file, output_format)
        accounts = read_accounts_from_excel(args.input_file, args.sheet)
    except (RuntimeError, ValueError) as exc:
        error("KONFIGURASI/EXCEL: {}".format(exc))
        return 1

    if output_format == "csv" and args.mode == "rekap" and not args.tanpa_gambar:
        warning(
            "Format CSV tidak dapat menyematkan gambar. Kolom URL gambar tetap tersedia."
        )
    if args.mode == "rinci" and args.tanpa_gambar:
        warning("--tanpa-gambar tidak berpengaruh pada mode rinci.")

    embed_images = (
        args.mode == "rekap"
        and output_format == "xlsx"
        and not args.tanpa_gambar
    )
    checkpoint_path = os.path.abspath(
        args.checkpoint or (output_file + ".checkpoint.sqlite3")
    )
    signature = build_job_signature(
        input_file=args.input_file,
        mode=args.mode,
        status=args.status,
        since=since,
        until=until,
        api_version=args.api_version,
        output_format=output_format,
    )

    checkpoint: Optional[CheckpointStore] = None
    checkpoint_closed = False
    try:
        checkpoint = CheckpointStore(
            path=checkpoint_path,
            signature=signature,
            resume=args.resume,
        )
        info("Checkpoint: {}".format(checkpoint_path))

        run_result = run_accounts(
            accounts=accounts,
            mode=args.mode,
            status_filter=args.status,
            since=since,
            until=until,
            checkpoint=checkpoint,
            api_version=args.api_version,
            max_retries=args.max_retries,
            retry_base_delay=args.retry_base_delay,
            retry_max_delay=args.retry_max_delay,
            client_factory=MetaAdsClient,
        )

        export_result = export_report(
            output_format=output_format,
            output_file=output_file,
            mode=args.mode,
            rows=run_result.rows,
            errors=run_result.errors,
            input_file=args.input_file,
            api_version=args.api_version,
            since=since,
            until=until,
            status_filter=args.status,
            date_source=date_source,
            image_width=args.image_width,
            image_height=args.image_height,
            embed_images=embed_images,
        )

        if args.keep_checkpoint:
            checkpoint.close()
            checkpoint_closed = True
        else:
            checkpoint.delete_file()
            checkpoint_closed = True

        _print_summary(
            args=args,
            since=since,
            until=until,
            date_source=date_source,
            result=export_result,
            total_accounts=run_result.total_accounts,
            skipped_accounts=run_result.skipped_accounts,
            row_count=len(run_result.rows),
            error_count=len(run_result.errors),
            checkpoint_path=checkpoint_path,
            checkpoint_kept=args.keep_checkpoint,
        )

        if run_result.errors and not run_result.rows:
            return 1
        return 0
    except KeyboardInterrupt:
        warning("Proses dibatalkan. Checkpoint dipertahankan untuk --resume.")
        return 130
    except (RuntimeError, ValueError, OSError, CheckpointMismatchError) as exc:
        error("PROSES: {}".format(exc))
        return 1
    finally:
        if checkpoint is not None and not checkpoint_closed:
            checkpoint.close()
