"""Command line interface for the modular Meta Ads exporter."""

import argparse
import os
import time
from typing import List, Optional, Tuple

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from . import __version__
from .accounts.datameta import SOURCE_API_BODY_MODES, read_accounts_from_api
from .accounts.excel import read_accounts_from_excel, validate_input_file
from .config_env import (
    DEFAULT_API_VERSION,
    DEFAULT_INPUT_SOURCE,
    DEFAULT_OUTPUT_LOCATION,
    DEFAULT_SHEET,
    DEFAULT_SOURCE_API_BODY_MODE,
    DEFAULT_SOURCE_API_JAM,
    DEFAULT_SOURCE_API_LAT,
    DEFAULT_SOURCE_API_LON,
    DEFAULT_SOURCE_API_NOHP,
    DEFAULT_SOURCE_API_URL,
    ENV_PRESET,
    ENV_SINCE,
    ENV_UNTIL,
    OUTPUT_LOCATION_CHOICES,
    normalize_csv_delimiter,
    normalize_status,
    resolved_default_csv_delimiter,
    resolved_default_status,
)
from .constants import (
    CSV_DELIMITER_CHOICES,
    INPUT_SOURCE_CHOICES,
    OUTPUT_FORMAT_CHOICES,
    PRESET_CHOICES,
    STATUS_CHOICES,
)
from .dates import normalize_preset, resolve_date_range
from .graph.client import MetaAdsClient
from .logging_utils import error, info, local_now, warning
from .paths import auxiliary_output_directory, home_report_directory, project_root
from .processing.runner import run_accounts
from .reporting import export_report, resolve_csv_delimiter
from .storage.checkpoint import (
    CheckpointMismatchError,
    CheckpointStore,
    accounts_source_fingerprint,
    build_job_signature,
)
from .summary import print_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Ambil Meta Ads dengan sumber akun dari Excel A:D atau API DATAMETA, "
            "lalu ekspor ke XLSX/CSV. Token digunakan per akun dan tidak diekspor. "
            "Delimiter CSV dapat dipilih (comma/tab/pipe/semicolon) dan tanggal DD-MM-YYYY."
        )
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        default="",
        help=(
            "File XLSX A:D untuk --sumber-akun excel. Tidak diperlukan jika "
            "--sumber-akun api."
        ),
    )
    parser.add_argument(
        "--sumber-akun",
        "--input-source",
        dest="input_source",
        choices=INPUT_SOURCE_CHOICES,
        default=(DEFAULT_INPUT_SOURCE if DEFAULT_INPUT_SOURCE in INPUT_SOURCE_CHOICES else "excel"),
        help="Sumber ID ACCOUNT/TOKEN/CABANG/BISNIS: excel atau api.",
    )
    parser.add_argument(
        "--source-api-url",
        default=DEFAULT_SOURCE_API_URL,
        help="Endpoint POST DATAMETA untuk --sumber-akun api.",
    )
    parser.add_argument(
        "--source-api-nohp",
        default=DEFAULT_SOURCE_API_NOHP,
        help="Nilai noHP pada body DATAMETA. Bisa disimpan di META_SOURCE_API_NOHP.",
    )
    parser.add_argument(
        "--source-api-lat",
        default=DEFAULT_SOURCE_API_LAT,
        help="Nilai latMulai body DATAMETA. Default: %(default)s.",
    )
    parser.add_argument(
        "--source-api-lon",
        default=DEFAULT_SOURCE_API_LON,
        help="Nilai lonMulai body DATAMETA. Default: %(default)s.",
    )
    parser.add_argument(
        "--source-api-jam-mulai",
        default=DEFAULT_SOURCE_API_JAM,
        help="Nilai jamMulai body DATAMETA. Default: %(default)s.",
    )
    parser.add_argument(
        "--source-api-body-mode",
        choices=SOURCE_API_BODY_MODES,
        default=(
            DEFAULT_SOURCE_API_BODY_MODE
            if DEFAULT_SOURCE_API_BODY_MODE in SOURCE_API_BODY_MODES
            else "auto"
        ),
        help=(
            "Format POST DATAMETA: auto mencoba JSON lalu form, json memaksa "
            "application/json, form memaksa form-urlencoded. Default: %(default)s."
        ),
    )
    parser.add_argument(
        "--source-api-debug",
        action="store_true",
        help=(
            "Tampilkan diagnostic/preview response DATAMETA yang sudah menyensor "
            "token dan noHP. Gunakan untuk troubleshooting."
        ),
    )
    parser.add_argument(
        "--source-api-timeout",
        type=float,
        default=60.0,
        help="Read timeout API DATAMETA dalam detik. Default: 60.",
    )
    parser.add_argument(
        "--source-api-retries",
        type=int,
        default=3,
        help="Retry API DATAMETA untuk network/408/429/5xx. Default: 3.",
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
        default=resolved_default_status(),
        help="Filter status efektif saat ekspor. Default: %(default)s.",
    )
    parser.add_argument(
        "--output",
        default="",
        help=(
            "Nama/path file output. Ekstensi boleh .xlsx atau .csv. Jika path "
            "absolut diberikan, --output-location tidak mengubah lokasinya."
        ),
    )
    parser.add_argument(
        "--output-location",
        "--lokasi-output",
        dest="output_location",
        choices=OUTPUT_LOCATION_CHOICES,
        default=(
            DEFAULT_OUTPUT_LOCATION
            if DEFAULT_OUTPUT_LOCATION in OUTPUT_LOCATION_CHOICES
            else "default"
        ),
        help=(
            "Base folder FILE LAPORAN: default = perilaku lokasi laporan lama, "
            "project = folder ScrapeMeta.py, home = ~/laporan. File teknis CSV "
            "(_errors/_info) dan checkpoint default tetap di folder project. "
            "Default: %(default)s."
        ),
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
        "--csv-delimiter",
        "--delimiter",
        dest="csv_delimiter",
        type=normalize_csv_delimiter,
        choices=CSV_DELIMITER_CHOICES,
        default=resolved_default_csv_delimiter(),
        help=(
            "Delimiter CSV: comma (,), tab, pipe (|), atau semicolon (;). "
            "Hanya berlaku untuk --format csv. Default: %(default)s."
        ),
    )
    parser.add_argument(
        "--csv-no-header",
        "--tanpa-header-csv",
        dest="csv_no_header",
        action="store_true",
        help=(
            "Hilangkan baris header pada output CSV utama dan file pendamping "
            "_errors.csv/_info.csv. Hanya berlaku untuk --format csv."
        ),
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
        help="Lokasi checkpoint SQLite. Default: folder project/<nama-output>.checkpoint.sqlite3.",
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


def resolve_output_directory(
    input_file: str,
    input_source: str,
    output_location: str,
) -> str:
    if output_location == "project":
        return project_root()
    if output_location == "home":
        return home_report_directory()
    if output_location != "default":
        raise ValueError(
            "--output-location harus salah satu dari: {}.".format(
                ", ".join(OUTPUT_LOCATION_CHOICES)
            )
        )

    if input_source == "api":
        return os.getcwd()
    return os.path.dirname(os.path.abspath(input_file))


def make_default_output(
    input_file: str,
    input_source: str,
    mode: str,
    status: str,
    since: str,
    until: str,
    output_format: str,
    output_location: str = "default",
) -> str:
    directory = resolve_output_directory(
        input_file=input_file,
        input_source=input_source,
        output_location=output_location,
    )
    if input_source == "api":
        stem = "datameta_api"
    else:
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
    input_source: str,
    mode: str,
    status: str,
    since: str,
    until: str,
    output_location: str = "default",
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

        if not os.path.isabs(output_file) and output_location != "default":
            base_directory = resolve_output_directory(
                input_file=input_file,
                input_source=input_source,
                output_location=output_location,
            )
            output_file = os.path.join(base_directory, output_file)
    else:
        output_file = make_default_output(
            input_file=input_file,
            input_source=input_source,
            mode=mode,
            status=status,
            since=since,
            until=until,
            output_format=output_format,
            output_location=output_location,
        )
    return os.path.abspath(output_file), output_format


def validate_runtime(
    args: argparse.Namespace,
    output_file: str,
    output_format: str,
) -> None:
    if args.input_source == "excel":
        if not args.input_file:
            raise RuntimeError(
                "--sumber-akun excel membutuhkan file XLSX sebagai argumen terakhir."
            )
        validate_input_file(args.input_file)
        if os.path.abspath(args.input_file) == os.path.abspath(output_file):
            raise RuntimeError("File output tidak boleh sama dengan file input.")
    else:
        if args.input_file:
            warning(
                "Argumen file input diabaikan karena --sumber-akun api digunakan."
            )
        if not str(args.source_api_nohp or "").strip():
            raise RuntimeError(
                "--sumber-akun api membutuhkan --source-api-nohp atau META_SOURCE_API_NOHP."
            )
        if args.source_api_timeout <= 0:
            raise RuntimeError("--source-api-timeout harus lebih besar dari 0.")
        if args.source_api_retries < 0:
            raise RuntimeError("--source-api-retries tidak boleh negatif.")

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
    resolve_csv_delimiter(args.csv_delimiter)


def main(argv: Optional[List[str]] = None) -> int:
    started_at = local_now()
    started_perf = time.perf_counter()
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
            input_source=args.input_source,
            mode=args.mode,
            status=args.status,
            since=since,
            until=until,
            output_location=args.output_location,
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    try:
        validate_runtime(args, output_file, output_format)
        if args.input_source == "api":
            accounts = read_accounts_from_api(
                api_url=args.source_api_url,
                no_hp=args.source_api_nohp,
                since=since,
                until=until,
                lat_mulai=args.source_api_lat,
                lon_mulai=args.source_api_lon,
                jam_mulai=args.source_api_jam_mulai,
                timeout_seconds=args.source_api_timeout,
                max_retries=args.source_api_retries,
                body_mode=args.source_api_body_mode,
                debug_response=args.source_api_debug,
            )
            source_reference = args.source_api_url
        else:
            accounts = read_accounts_from_excel(args.input_file, args.sheet)
            source_reference = os.path.abspath(args.input_file)
        source_fingerprint = accounts_source_fingerprint(accounts)
    except (RuntimeError, ValueError) as exc:
        error("KONFIGURASI/SUMBER AKUN: {}".format(exc))
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
    technical_directory = os.path.abspath(auxiliary_output_directory())
    os.makedirs(technical_directory, exist_ok=True)
    default_checkpoint_name = os.path.basename(output_file) + ".checkpoint.sqlite3"
    checkpoint_path = os.path.abspath(
        args.checkpoint or os.path.join(technical_directory, default_checkpoint_name)
    )
    signature = build_job_signature(
        input_file=args.input_file,
        input_source=args.input_source,
        source_fingerprint=source_fingerprint,
        source_reference=source_reference,
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
            input_source=args.input_source,
            source_reference=source_reference,
            csv_delimiter=args.csv_delimiter,
            csv_include_header=not args.csv_no_header,
            auxiliary_directory=technical_directory,
        )

        if args.keep_checkpoint:
            checkpoint.close()
            checkpoint_closed = True
        else:
            checkpoint.delete_file()
            checkpoint_closed = True

        print_summary(
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
            started_at=started_at,
            finished_at=local_now(),
            elapsed_seconds=time.perf_counter() - started_perf,
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
