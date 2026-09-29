"""Definisi skenario golden.

Setiap skenario mengembalikan :class:`tests.golden.harness.RunResult` berisi
exit code dan artefak yang sudah dinormalisasi.

Semua skenario offline: ``MetaAdsClient`` dan ``read_accounts_from_api``
selalu di-patch oleh harness.
"""

import os

from tests.golden import harness


class Scenario(object):
    """Skenario golden yang dapat dijalankan ulang."""

    def __init__(self, name, runner):
        self.name = name
        self._runner = runner

    def run(self):
        workspace = harness.Workspace()
        try:
            return self._runner(workspace)
        finally:
            workspace.discard()


# ---------------------------------------------------------------------------
# Skenario Excel: mode x format x delimiter x lokasi output
# ---------------------------------------------------------------------------


def _excel_runner(
    mode,
    output,
    extra_args=None,
    output_location=None,
    files=None,
    status="semua",
    delimiter=None,
):
    def runner(workspace):
        argv = harness.excel_argv(
            workspace,
            mode=mode,
            output=output,
            extra_args=extra_args,
            output_location=output_location,
            status=status,
        )
        include_header = "--csv-no-header" not in argv
        return harness.run_cli(
            workspace,
            argv,
            files or harness.csv_files(output, delimiter),
            include_header=include_header,
        )

    return runner


SCENARIOS = {
    "excel_rekap_xlsx": Scenario(
        "excel_rekap_xlsx",
        _excel_runner(
            "rekap",
            "rekap.xlsx",
            # Gambar butuh jaringan; kolom URL gambar tetap teruji.
            extra_args=["--tanpa-gambar"],
            files=harness.xlsx_files("rekap.xlsx"),
        ),
    ),
    "excel_rinci_xlsx": Scenario(
        "excel_rinci_xlsx",
        _excel_runner("rinci", "rinci.xlsx", files=harness.xlsx_files("rinci.xlsx")),
    ),
    "excel_rekap_csv_pipe": Scenario(
        "excel_rekap_csv_pipe",
        _excel_runner(
            "rekap", "rekap.csv", extra_args=["--csv-delimiter", "pipe"], delimiter="|"
        ),
    ),
    "excel_rinci_csv_pipe": Scenario(
        "excel_rinci_csv_pipe",
        _excel_runner(
            "rinci", "rinci.csv", extra_args=["--csv-delimiter", "pipe"], delimiter="|"
        ),
    ),
    "excel_rinci_csv_comma": Scenario(
        "excel_rinci_csv_comma",
        _excel_runner(
            "rinci",
            "rinci_comma.csv",
            extra_args=["--csv-delimiter", "comma"],
            delimiter=",",
        ),
    ),
    "excel_rinci_csv_semicolon": Scenario(
        "excel_rinci_csv_semicolon",
        _excel_runner(
            "rinci",
            "rinci_semicolon.csv",
            extra_args=["--csv-delimiter", "semicolon"],
            delimiter=";",
        ),
    ),
    "excel_rinci_csv_tab": Scenario(
        "excel_rinci_csv_tab",
        _excel_runner(
            "rinci", "rinci_tab.csv", extra_args=["--csv-delimiter", "tab"], delimiter="\t"
        ),
    ),
    "excel_rinci_csv_delimiter_alias": Scenario(
        "excel_rinci_csv_delimiter_alias",
        # Bentuk alias ";" harus dinormalisasi menjadi semicolon.
        _excel_runner(
            "rinci",
            "rinci_alias.csv",
            extra_args=["--csv-delimiter", ";"],
            delimiter=";",
        ),
    ),
    "excel_rinci_csv_no_header": Scenario(
        "excel_rinci_csv_no_header",
        # Tanpa header baris pertama tidak bisa dipakai untuk mendeteksi
        # delimiter, jadi delimiter harus dinyatakan eksplisit.
        _excel_runner(
            "rinci",
            "rinci_noheader.csv",
            extra_args=["--csv-delimiter", "pipe", "--csv-no-header"],
            delimiter="|",
        ),
    ),
    "excel_rinci_location_project": Scenario(
        "excel_rinci_location_project",
        _excel_runner(
            "rinci",
            "project_report.csv",
            extra_args=["--csv-delimiter", "pipe"],
            output_location="project",
            delimiter="|",
        ),
    ),
    "excel_rinci_location_home": Scenario(
        "excel_rinci_location_home",
        _excel_runner(
            "rinci",
            "home_report.csv",
            extra_args=["--csv-delimiter", "pipe"],
            output_location="home",
            delimiter="|",
        ),
    ),
    "excel_rinci_status_aktif": Scenario(
        "excel_rinci_status_aktif",
        _excel_runner(
            "rinci",
            "rinci_aktif.csv",
            extra_args=["--csv-delimiter", "pipe"],
            status="aktif",
            delimiter="|",
        ),
    ),
}


# ---------------------------------------------------------------------------
# Skenario API
# ---------------------------------------------------------------------------


def _api_runner(output, extra_args=None, accounts=None, output_location=None, files=None):
    def runner(workspace):
        argv = harness.api_argv(output, extra_args=extra_args)
        if output_location:
            argv += ["--output-location", output_location]
        return harness.run_cli(
            workspace,
            argv,
            files or harness.csv_files(output, "|"),
            accounts=accounts or harness.API_ACCOUNTS,
        )

    return runner


SCENARIOS["api_rinci_csv"] = Scenario("api_rinci_csv", _api_runner("api_rinci.csv"))
SCENARIOS["api_rinci_location_home"] = Scenario(
    "api_rinci_location_home",
    _api_runner("api_home.csv", output_location="home"),
)


# ---------------------------------------------------------------------------
# Skenario khusus: error, resume, validasi
# ---------------------------------------------------------------------------


def _api_account_error(workspace):
    """Seluruh akun gagal: exercising _errors.csv dan exit code 1."""
    output = "api_error.csv"
    argv = harness.api_argv(output)
    return harness.run_cli(
        workspace,
        argv,
        harness.csv_files(output, "|"),
        client_class=harness.FailingMetaClient,
        accounts=harness.API_ACCOUNTS,
    )


SCENARIOS["api_account_error"] = Scenario("api_account_error", _api_account_error)


def _resume_flow(workspace):
    """Resume: tanpa checkpoint (gagal), proses penuh, lalu resume ulang."""
    output = "resume.csv"
    base = harness.api_argv(output, extra_args=["--keep-checkpoint"])
    result = harness.run_cli_sequence(
        workspace,
        [base + ["--resume"], base, base + ["--resume"]],
        harness.csv_files(output, "|"),
        accounts=harness.API_ACCOUNTS,
    )
    checkpoint = os.path.join(workspace.project, output + ".checkpoint.sqlite3")
    result.extra["checkpoint_kept"] = os.path.isfile(checkpoint)
    return result


SCENARIOS["resume_flow"] = Scenario("resume_flow", _resume_flow)


def _missing_input_file(workspace):
    """File input tidak ada: harus gagal dengan exit code 1."""
    output = "tidak_ada.csv"
    argv = [
        "--sumber-akun",
        "excel",
        "--mode",
        "rekap",
        "--status",
        "semua",
        "--since",
        "2026-08-01",
        "--until",
        "2026-08-05",
        "--output",
        output,
        os.path.join(workspace.project, "hilang.xlsx"),
    ]
    return harness.run_cli(workspace, argv, harness.csv_files(output, "|"))


SCENARIOS["missing_input_file"] = Scenario("missing_input_file", _missing_input_file)


def _output_format_conflict(workspace):
    """Ekstensi .csv bentrok dengan --format xlsx: parser error, exit 2."""
    output = "konflik.csv"
    argv = harness.excel_argv(
        workspace,
        mode="rekap",
        output=output,
        extra_args=["--format", "xlsx", "--tanpa-gambar"],
    )
    return harness.run_cli(workspace, argv, harness.csv_files(output, "|"))


SCENARIOS["output_format_conflict"] = Scenario(
    "output_format_conflict", _output_format_conflict
)


# ---------------------------------------------------------------------------
# Skenario gambar: server HTTP lokal, tanpa jaringan luar
# ---------------------------------------------------------------------------


def _image_runner(output, image_files):
    """Rekap XLSX dengan gambar tertanam dari HTTP server lokal.

    Tiga kasus diuji dalam satu skenario:
    - iklan 1: gambar ada, berhasil diunduh dan disematkan;
    - iklan 2: URL 404 sehingga kolom gambar berisi "Gagal dimuat" dan muncul
      satu baris di sheet Error;
    - iklan 3: tidak ada URL sehingga kolom gambar berisi "Tidak tersedia".
    """

    def runner(workspace):
        payload = harness.make_png_bytes()
        with harness.LocalImageServer({"/tersedia.png": payload}) as server:
            harness.FakeMetaClient.image_base_url = server.base_url
            try:
                argv = harness.excel_argv(workspace, mode="rekap", output=output)
                result = harness.run_cli(
                    workspace,
                    argv,
                    image_files,
                )
            finally:
                harness.FakeMetaClient.image_base_url = ""
        return result

    return runner


SCENARIOS["excel_rekap_xlsx_images"] = Scenario(
    "excel_rekap_xlsx_images",
    _image_runner("rekap_gambar.xlsx", harness.xlsx_files("rekap_gambar.xlsx")),
)
