"""Golden output regression harness.

Harness ini menjalankan ``meta_ads_tool.cli.main`` pada workspace sementara
kemudian membandingkan file yang dihasilkan dengan snapshot baseline.

Prinsip:

- Skenario sepenuhnya offline. ``MetaAdsClient`` dan ``read_accounts_from_api``
  selalu di-patch.
- Fixture Meta payload bersifat deterministik.
- Nilai yang memang tidak deterministik dinetralkan:
  ``Tanggal proses`` (lewat patch ``current_date_text``), ``Waktu pembuatan``,
  dan seluruh path workspace (diganti ``<WORKSPACE>``).
- CSV dibandingkan setelah normalisasi baris-per-baris.
- XLSX dibandingkan secara struktural, karena file ZIP-nya sendiri tidak
  byte-stable antar penulisan.
"""

import contextlib
import csv
import io
import os
import re
import shutil
import tempfile
import threading
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from meta_ads_tool.cli import main as cli_main
from meta_ads_tool.constants import CSV_REPORT_COLUMNS, ERROR_COLUMNS

# Nilai yang dinetralkan agar output deterministik.
PLACEHOLDER_CREATED_AT = "<WAKTU_PEMBUATAN>"
PLACEHOLDER_WORKSPACE = "<WORKSPACE>"

# Dipatch ke ``reporting.csv_writer.current_date_text`` supaya kolom "Tanggal proses" stabil.
FIXED_PROCESS_DATE = "2026-08-06"

LABEL_CREATED_AT = "Waktu pembuatan"

ACCOUNT_XLSX_HEADERS = ["ID ACCOUNT", "TOKEN", "CABANG", "BISNIS"]
TARGET_RESULT_INDICATOR = "actions:onsite_conversion.messaging_conversation_started_7d"


# ---------------------------------------------------------------------------
# Fixture input Excel
# ---------------------------------------------------------------------------


def write_accounts_workbook(path, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(ACCOUNT_XLSX_HEADERS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


EXCEL_ACCOUNTS = [
    ["123", "token-excel-123", "34THJO81", "MGA"],
    ["456", "token-excel-456", "33KDGP81", "HMC"],
]

API_ACCOUNTS = [
    {
        "account_id": "123",
        "access_token": "token-api-123",
        "cabang": "34THJO81",
        "bisnis": "MGA",
    },
    {
        "account_id": "456",
        "access_token": "token-api-456",
        "cabang": "44MAA91",
        "bisnis": "HMC",
    },
]


# ---------------------------------------------------------------------------
# Fixture Meta payload
# ---------------------------------------------------------------------------


def _ads(account_id):
    base = 3000 if account_id == "123" else 4000
    return [
        {
            "ad_id": str(base + 1),
            # Nama generasi Meta: harus dibersihkan oleh normalize_ad_name.
            "ad_name": 'Postingan: "Butuh dana cepat, tanpa ribet"',
        },
        {
            "ad_id": str(base + 2),
            # Memicu sanitasi formula spreadsheet.
            "ad_name": "=1+1alice",
        },
        {
            "ad_id": str(base + 3),
            # Tanpa indicator target: kolom Hasil harus kosong.
            "ad_name": "Iklan Tanpa Hasil",
        },
    ]


def _rekap_rows(since, until, account_id):
    rows = []
    for index, ad in enumerate(_ads(account_id)):
        results = (
            [{"indicator": TARGET_RESULT_INDICATOR, "values": [{"value": str(9 + index)}]}]
            if index < 2
            else []
        )
        rows.append(
            {
                "campaign_id": "1001",
                "campaign_name": "Kampanye Juli",
                "adset_id": "2001",
                "adset_name": "Set Iklan",
                "ad_id": ad["ad_id"],
                "ad_name": ad["ad_name"],
                "date_start": since,
                "date_stop": until,
                "impressions": "1500628",
                "reach": "1000000",
                "frequency": "1.150628",
                "inline_link_clicks": "42",
                "inline_link_click_ctr": "0.028",
                "cost_per_inline_link_click": "214.29",
                "spend": "9000",
                "objective": "OUTCOME_ENGAGEMENT",
                "optimization_goal": "CONVERSATIONS",
                "attribution_setting": {ad["ad_id"]: 7},
                "adset_start": "{}T00:00:00+0700".format(since),
                "adset_end": "{}T23:59:59+0700".format(until),
                "results": results,
                "cost_per_result": (
                    [
                        {
                            "indicator": TARGET_RESULT_INDICATOR,
                            "values": [{"value": str(9000.0 / (9 + index))}],
                        }
                    ]
                    if index < 2
                    else []
                ),
            }
        )
    return rows


def _hourly_rows(since, account_id):
    rows = []
    for ad in _ads(account_id):
        for hour in (0, 13):
            rows.append(
                {
                    "campaign_id": "1001",
                    "campaign_name": "Kampanye Juli",
                    "adset_id": "2001",
                    "adset_name": "Set Iklan",
                    "ad_id": ad["ad_id"],
                    "ad_name": ad["ad_name"],
                    "date_start": since,
                    "hourly_stats_aggregated_by_advertiser_time_zone": (
                        "{:02d}:00:00 - {:02d}:59:59".format(hour, hour)
                    ),
                    "attribution_setting": {ad["ad_id"]: 7},
                    "adset_start": "{}T00:00:00+0700".format(since),
                    "adset_end": "{}T23:59:59+0700".format(since),
                    "impressions": "344" if hour == 0 else "13",
                    "inline_link_clicks": "5" if hour == 0 else "1",
                    "inline_link_click_ctr": "1.45" if hour == 0 else "7.69",
                    "spend": "4932" if hour == 0 else "96",
                    "objective": "OUTCOME_ENGAGEMENT",
                    "optimization_goal": "CONVERSATIONS",
                }
            )
    return rows


def _daily_row(ad, since, index, results, cost_value=None):
    """Satu barik insight harian tanpa breakdown jam."""
    return {
        "campaign_id": "1001",
        "campaign_name": "Kampanye Juli",
        "adset_id": "2001",
        "adset_name": "Set Iklan",
        "ad_id": ad["ad_id"],
        "ad_name": ad["ad_name"],
        "date_start": since,
        "impressions": "1500628",
        "reach": "1000000",
        "frequency": "1.150628",
        "spend": "9000",
        "objective": "OUTCOME_ENGAGEMENT",
        "optimization_goal": "CONVERSATIONS",
        "results": results,
        "cost_per_result": (
            [{"indicator": results[0]["indicator"], "values": [{"value": cost_value}]}]
            if results and cost_value is not None
            else []
        ),
    }


def _daily_rows(since, account_id):
    rows = []
    for index, ad in enumerate(_ads(account_id)):
        results = (
            [{"indicator": TARGET_RESULT_INDICATOR, "values": [{"value": str(9 + index)}]}]
            if index < 2
            else []
        )
        rows.append(
            _daily_row(
                ad,
                since,
                index,
                results,
                cost_value=str(9000.0 / (9 + index)) if index < 2 else None,
            )
        )
    return rows


def make_png_bytes(width=240, height=120, color=(10, 120, 200)):
    """Buat PNG kecil yang valid untuk fixture gambar lokal."""
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


class LocalImageServer(object):
    """HTTP server lokal yang menyajikan fixture PNG.

    Dipakai untuk menguji ``_embed_rekap_images`` dan ``_download_image_to_png``
    tanpa menyentuh jaringan luar. URL yang tidak terdaftar sengaja membalas
    404 agar jalur "Gagal dimuat" ikut teruji.
    """

    def __init__(self, images):
        self.images = dict(images)
        self.requests = []
        handler = self._make_handler()
        self._server = HTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever)
        self._thread.daemon = True

    def _make_handler(self):
        images = self.images
        requests_log = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - nama method dictated by stdlib
                requests_log.append(self.path)
                payload = images.get(self.path)
                if payload is None:
                    self.send_error(404, "not found")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                """Matikan log request agar output test bersih."""

        return Handler

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        return False

    @property
    def base_url(self):
        host, port = self._server.server_address[:2]
        return "http://{}:{}".format(host, port)


def _image_url_for(index):
    """URL gambar untuk iklan ke-``index``.

    Hanya aktif saat ``image_base_url`` diisi oleh skenario gambar:
    indeks 0 tersedia, indeks 1 sengaja 404, indeks 2 tidak punya URL.
    """
    base = FakeMetaClient.image_base_url
    if not base:
        return "https://cdn.example.com/c{}.jpg".format(3001 + index)
    if index == 0:
        return base + "/tersedia.png"
    if index == 1:
        return base + "/hilang.png"
    return ""


class FakeMetaClient(object):
    """MetaAdsClient palsu dengan payload fully deterministik."""

    created_tokens = []
    # Diisi skenario gambar dengan base URL HTTP server lokal.
    image_base_url = ""

    def __init__(self, *args, **kwargs):
        self.__class__.created_tokens.append(kwargs.get("access_token"))
        self.access_token = kwargs.get("access_token")

    def get_account_information(self, account_id):
        return {
            "id": account_id,
            "name": "Akun Test {}".format(account_id),
            "currency": "IDR",
            "timezone_name": "Asia/Jakarta",
        }

    def fetch_campaigns(self, account_id):
        return {
            "1001": {
                "id": "1001",
                "name": "Kampanye Juli",
                "objective": "OUTCOME_ENGAGEMENT",
                "status": "ACTIVE",
                "effective_status": "ACTIVE",
            }
        }

    def fetch_adsets(self, account_id):
        return {
            "2001": {
                "id": "2001",
                "name": "Set Iklan",
                "campaign_id": "1001",
                "optimization_goal": "CONVERSATIONS",
                "status": "ACTIVE",
                "effective_status": "ACTIVE",
                "start_time": "2026-08-01T00:00:00+0700",
                "end_time": "2026-08-31T23:59:59+0700",
                "attribution_spec": [
                    {"event_type": "CLICK_THROUGH", "window_days": 7}
                ],
            }
        }

    def fetch_ads(self, account_id, status_filter):
        rows = []
        for index, ad in enumerate(_ads(account_id)):
            thumbnail_url = _image_url_for(index)
            creative = {"id": "c{}".format(ad["ad_id"]), "name": "Creative"}
            if thumbnail_url:
                creative["thumbnail_url"] = thumbnail_url
            rows.append(
                {
                    "id": ad["ad_id"],
                    "name": ad["ad_name"],
                    "campaign_id": "1001",
                    "adset_id": "2001",
                    "configured_status": "ACTIVE",
                    "effective_status": "ACTIVE",
                    "created_time": "2026-07-01T00:00:00+0000",
                    "updated_time": "2026-07-01T00:00:00+0000",
                    "creative": creative,
                }
            )
        return rows

    def fetch_creative_metadata(self, creative_id):
        return {"id": creative_id, "name": "Creative", "thumbnail_url": ""}

    def fetch_all_insights(self, account_id, mode, since, until):
        if mode == "rinci":
            return _hourly_rows(since, account_id), []
        return _rekap_rows(since, until, account_id), []

    def fetch_daily_result_insights(self, account_id, since, until):
        return _daily_rows(since, account_id), []


class FailingMetaClient(FakeMetaClient):
    """Selalu gagal saat mengambil insight, untuk menguji jalur error akun."""

    def fetch_all_insights(self, account_id, mode, since, until):
        raise RuntimeError("Simulasi kegagalan API Meta")


LEAD_RESULT_INDICATOR = "actions:onsite_conversion.lead_grouped"


class LeadMetaClient(FakeMetaClient):
    """Iklan ber-goal leads: ``results`` hanya berisi indikator lead.

    Menutmaskah fixture conversation supaya skenario ini membuktikan bahwa
    kolom Hasil terisi dari lead ketika tidak ada conversation.
    """

    def fetch_adsets(self, account_id):
        adsets = dict(FakeMetaClient.fetch_adsets(self, account_id))

        for adset in adsets.values():
            adset = dict(adset)
            adset["optimization_goal"] = "LEADS"
            adsets[adset["id"]] = adset

        return adsets

    def fetch_all_insights(self, account_id, mode, since, until):
        if mode != "rekap":
            return FakeMetaClient.fetch_all_insights(
                self, account_id, mode, since, until
            )

        rows = []
        for index, row in enumerate(_rekap_rows(since, until, account_id)):
            row = dict(row)
            row["optimization_goal"] = "LEADS"
            value = str(4 + index)
            row["results"] = (
                [{"indicator": LEAD_RESULT_INDICATOR, "values": [{"value": value}]}]
                if index < 2
                else []
            )
            row["cost_per_result"] = (
                [{"indicator": LEAD_RESULT_INDICATOR, "values": [{"value": str(9000.0 / int(value))}]}]
                if index < 2
                else []
            )
            rows.append(row)

        return rows, []

    def fetch_daily_result_insights(self, account_id, since, until):
        rows = []
        for index, ad in enumerate(_ads(account_id)):
            if index >= 2:
                # Iklan ketiga tetap tanpa hasil agar kasus kosong ikut teruji.
                rows.append(_daily_row(ad, since, index, []))
                continue
            value = str(4 + index)
            rows.append(_daily_row(ad, since, index, [
                {
                    "indicator": LEAD_RESULT_INDICATOR,
                    "values": [{"value": value}],
                }
            ], cost_value=str(9000.0 / int(value))))

        return rows, []


# ---------------------------------------------------------------------------
# Normalisasi output
# ---------------------------------------------------------------------------


LOOPBACK_URL_RE = re.compile(r"https?://127\.0\.0\.1:\d+")


def _scrub(value, roots):
    """Ganti path workspace dan port loopback agar stabil antar mesin."""
    if not isinstance(value, str):
        return value
    for root in roots:
        if root:
            value = value.replace(root, PLACEHOLDER_WORKSPACE)
    return LOOPBACK_URL_RE.sub("http://127.0.0.1:<PORT>", value)


def _normalize_info_rows(rows, roots):
    for row in rows:
        if len(row) > 1 and row[0] == LABEL_CREATED_AT:
            row[1] = PLACEHOLDER_CREATED_AT
    return [[_scrub(cell, roots) for cell in row] for row in rows]


def _read_rows(path, delimiter):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(io.StringIO(handle.read()), delimiter=delimiter))


def _detect_delimiter(path):
    """Temukan delimiter dengan mencocokkan baris header terhadap skema known."""
    candidates = [",", "\t", "|", ";"]
    known = (
        CSV_REPORT_COLUMNS,
        ERROR_COLUMNS,
        ["Parameter", "Nilai"],
    )
    for candidate in candidates:
        try:
            rows = _read_rows(path, candidate)
        except csv.Error:
            continue
        if not rows:
            continue
        if any(tuple(rows[0]) == tuple(header) for header in known):
            return candidate
    return None


def normalize_csv(path, include_header, roots, delimiter=None):
    resolved = delimiter
    if resolved is None:
        resolved = _detect_delimiter(path)
    if resolved is None:
        raise AssertionError(
            "Delimiter CSV tidak dapat dideteksi untuk {!r}; "
            "berikan delimiter secara eksplisit.".format(path)
        )

    rows = _read_rows(path, resolved)
    if not rows:
        return {"empty": True, "delimiter": resolved}

    header = rows[0] if include_header else None
    body = rows[1:] if include_header else rows

    # File info dikenali dari baris "Waktu pembuatan" agar tetap berlaku pada
    # mode tanpa header.
    is_info = any(
        len(row) > 1 and row[0] == LABEL_CREATED_AT for row in rows
    )
    if is_info:
        return {
            "kind": "info",
            "delimiter": resolved,
            "rows": _normalize_info_rows(body, roots),
        }

    return {
        "kind": "report",
        "delimiter": resolved,
        "header": header,
        "rows": [[_scrub(cell, roots) for cell in row] for row in body],
    }


def _encode_cell(value):
    if isinstance(value, datetime):
        return ["datetime", value.isoformat()]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    return value


def _image_details(worksheet):
    """Rekam posisi dan ukuran tiap gambar yang tertanam."""
    details = []
    for image in getattr(worksheet, "_images", []):
        anchor = getattr(image, "anchor", None)
        origin = getattr(anchor, "_from", None)
        details.append(
            [
                getattr(origin, "col", None),
                getattr(origin, "row", None),
                image.width,
                image.height,
            ]
        )
    return details


def canonical_xlsx(path, roots):
    workbook = load_workbook(path, data_only=False)
    try:
        result = {"sheetnames": list(workbook.sheetnames), "sheets": {}}
        for name in workbook.sheetnames:
            worksheet = workbook[name]
            cells = []
            formats = []
            hyperlinks = []
            for row in worksheet.iter_rows():
                cells.append([_encode_cell(cell.value) for cell in row])
                formats.append([cell.number_format for cell in row])
                for cell in row:
                    if cell.hyperlink is not None:
                        target = cell.hyperlink.target or cell.hyperlink.location or ""
                        hyperlinks.append([cell.coordinate, _scrub(str(target), roots)])

            if name == "Informasi":
                cells = [
                    [_scrub(_encode_cell(item), roots) for item in row]
                    for row in cells
                ]
                cells = _normalize_info_rows(cells, roots)
            else:
                cells = [
                    [_scrub(_encode_cell(item), roots) for item in row]
                    for row in cells
                ]

            result["sheets"][name] = {
                "cells": cells,
                "number_formats": formats,
                "hyperlinks": sorted(hyperlinks),
                "freeze_panes": str(worksheet.freeze_panes or ""),
                "auto_filter": str(worksheet.auto_filter.ref or ""),
                "show_gridlines": bool(worksheet.sheet_view.showGridLines),
                "images": _image_details(worksheet),
                "column_widths": {
                    key: dimension.width
                    for key, dimension in sorted(worksheet.column_dimensions.items())
                },
                "row_heights": {
                    str(key): dimension.height
                    for key, dimension in sorted(worksheet.row_dimensions.items())
                    if dimension.height
                },
            }
        return result
    finally:
        workbook.close()


# ---------------------------------------------------------------------------
# Workspace dan runner
# ---------------------------------------------------------------------------


class Workspace(object):
    """Direktori sementara dengan input Excel dan folder output terisolasi."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="meta_ads_golden_")
        self.project = os.path.join(self.root, "project")
        self.home = os.path.join(self.root, "home")
        os.makedirs(self.project, exist_ok=True)
        os.makedirs(self.home, exist_ok=True)
        self.excel_file = os.path.join(self.project, "akun.xlsx")
        write_accounts_workbook(self.excel_file, EXCEL_ACCOUNTS)
        # Diprioritaskan: path yang lebih panjang lebih dulu agar tidak tertimpa.
        self.roots = [self.root, self.project, self.home]

    def discard(self):
        shutil.rmtree(self.root, ignore_errors=True)


class RunResult(object):
    def __init__(self, exit_code, artifacts, stdout, extra=None):
        self.exit_code = exit_code
        self.artifacts = artifacts
        self.stdout = stdout
        self.extra = extra or {}

    def as_dict(self):
        data = {"exit_code": self.exit_code, "artifacts": self.artifacts}
        if self.extra:
            data["extra"] = self.extra
        return data


@contextlib.contextmanager
def _isolated(workspace, client_class, accounts):
    """Chdir ke workspace, patch lokasi folder, tanggal proses, dan API client.

    ``accounts=None`` memasang guard yang gagal keras bila skenario tanpa sengaja
    memanggil API DATAMETA sungguhan.
    """
    previous_cwd = os.getcwd()
    os.chdir(workspace.project)
    FakeMetaClient.created_tokens = []
    if accounts is None:
        accounts_patch = patch(
            "meta_ads_tool.cli.read_accounts_from_api",
            side_effect=AssertionError(
                "golden harness tidak boleh memanggil API DATAMETA"
            ),
        )
    else:
        accounts_patch = patch(
            "meta_ads_tool.cli.read_accounts_from_api",
            return_value=[dict(item) for item in accounts],
        )
    try:
        with patch("meta_ads_tool.paths.project_root", return_value=workspace.project), patch(
            "meta_ads_tool.paths.home_report_directory", return_value=workspace.home
        ), patch(
            "meta_ads_tool.cli.project_root", return_value=workspace.project
        ), patch(
            "meta_ads_tool.cli.home_report_directory", return_value=workspace.home
        ), patch(
            "meta_ads_tool.summary.auxiliary_output_directory",
            return_value=workspace.project,
        ), patch(
            "meta_ads_tool.reporting.csv_writer.current_date_text",
            return_value=FIXED_PROCESS_DATE,
        ), patch(
            "meta_ads_tool.cli.MetaAdsClient", client_class
        ), accounts_patch:
            yield
    finally:
        os.chdir(previous_cwd)


def _resolve_artifact_path(workspace, relative):
    """Cari artefak di folder project, lalu home, lalu root workspace."""
    for directory in (workspace.project, workspace.home, workspace.root):
        path = os.path.join(directory, relative)
        if os.path.isfile(path):
            return path
    return None


def _collect(workspace, files, include_header, roots):
    artifacts = {}
    for label, relative, delimiter in files:
        path = _resolve_artifact_path(workspace, relative)
        if path is None:
            artifacts[label] = {"missing": True}
            continue
        if relative.endswith(".csv"):
            artifacts[label] = normalize_csv(path, include_header, roots, delimiter)
        else:
            artifacts[label] = canonical_xlsx(path, roots)
    return artifacts


def _invoke(argv):
    """Jalankan ``cli_main`` dan tangkap ``SystemExit`` dari ``parser.error()``.

    argparse memanggil ``sys.exit(2)`` sehingga ``SystemExit`` menembus
    handler ``except`` di dalam ``main``. Exit code itu tetap bagian dari
    kontrak yang harus direkam.
    """
    try:
        return cli_main(list(argv))
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1


def run_cli(
    workspace,
    argv,
    files,
    include_header=True,
    client_class=FakeMetaClient,
    accounts=None,
):
    """Jalankan CLI sekali pada workspace terisolasi."""
    stdout = io.StringIO()
    with _isolated(workspace, client_class, accounts):
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            exit_code = _invoke(argv)

    artifacts = _collect(workspace, files, include_header, workspace.roots)
    return RunResult(exit_code, artifacts, stdout.getvalue())


def run_cli_sequence(
    workspace,
    steps,
    files,
    include_header=True,
    client_class=FakeMetaClient,
    accounts=None,
):
    """Jalankan beberapa invocation CLI pada workspace yang sama."""
    stdout = io.StringIO()
    exit_codes = []
    with _isolated(workspace, client_class, accounts):
        for argv in steps:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
                exit_codes.append(_invoke(argv))

    artifacts = _collect(workspace, files, include_header, workspace.roots)
    return RunResult(
        exit_codes[-1],
        artifacts,
        stdout.getvalue(),
        extra={"exit_codes": exit_codes},
    )


def api_argv(output, extra_args=None, accounts_argv=True):
    argv = [
        "--sumber-akun",
        "api",
        "--source-api-nohp",
        "080000000000",
        "--mode",
        "rinci",
        "--status",
        "semua",
        "--since",
        "2026-08-01",
        "--until",
        "2026-08-05",
        "--format",
        "csv",
        "--output",
        output,
    ]
    return argv + list(extra_args or [])


def excel_argv(workspace, mode, output, extra_args=None, output_location=None, status="semua"):
    argv = [
        "--sumber-akun",
        "excel",
        "--mode",
        mode,
        "--status",
        status,
        "--since",
        "2026-08-01",
        "--until",
        "2026-08-05",
        "--output",
        output,
    ]
    if output_location:
        argv += ["--output-location", output_location]
    argv += list(extra_args or [])
    # Argumen posisional file input harus diakhirkan.
    return argv + [workspace.excel_file]


def csv_files(filename, delimiter=None):
    """File samping yang dihasilkan exporter CSV.

    Nama file teknis memakai stem tanpa ekstensi, misalnya
    ``rinci.csv`` menghasilkan ``rinci_errors.csv`` dan ``rinci_info.csv``.
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    return [
        ("report", filename, delimiter),
        ("errors", stem + "_errors.csv", delimiter),
        ("info", stem + "_info.csv", delimiter),
    ]


def xlsx_files(filename):
    return [("report", filename, None)]
