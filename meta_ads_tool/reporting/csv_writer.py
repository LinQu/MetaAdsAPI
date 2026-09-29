"""Penulis CSV: laporan utama, berkas error, dan berkas informasi."""

import csv
import os
from typing import Any, Dict, List, Sequence

from ..constants import CSV_DELIMITER, ERROR_COLUMNS
from ..logging_utils import current_date_text
from .info import information_rows
from .result import ExportResult
from .schema import csv_report_columns, resolve_csv_delimiter
from .values import csv_value, sanitize_spreadsheet_text


def write_csv(
    path: str,
    columns: Sequence[str],
    rows: Sequence[Dict[str, Any]],
    delimiter: str = CSV_DELIMITER,
    include_header: bool = True,
) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
        if include_header:
            writer.writerow(columns)
        for row in rows:
            writer.writerow([
                csv_value(column, row.get(column, ""))
                for column in columns
            ])


def export_csv(
    output_file: str,
    mode: str,
    rows: List[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    input_file: str,
    api_version: str,
    since: str,
    until: str,
    status_filter: str,
    date_source: str,
    process_date: str = "",
    input_source: str = "excel",
    source_reference: str = "",
    csv_delimiter: str = CSV_DELIMITER,
    csv_include_header: bool = True,
    auxiliary_directory: str = "",
) -> ExportResult:
    delimiter = resolve_csv_delimiter(csv_delimiter)
    # CSV sengaja memakai skema tetap/ringkas. Output XLSX tetap memakai
    # kolom lengkap sesuai mode. Field yang tidak tersedia pada suatu mode
    # akan ditulis kosong.
    columns = csv_report_columns()
    resolved_process_date = process_date or current_date_text()
    csv_rows = []
    for source_row in rows:
        output_row = dict(source_row)
        output_row["Tanggal proses"] = resolved_process_date
        csv_rows.append(output_row)
    write_csv(
        output_file,
        columns,
        csv_rows,
        delimiter=delimiter,
        include_header=csv_include_header,
    )

    stem, _ = os.path.splitext(output_file)
    report_stem_name = os.path.basename(stem)
    if auxiliary_directory:
        sidecar_directory = os.path.abspath(auxiliary_directory)
        os.makedirs(sidecar_directory, exist_ok=True)
        error_file = os.path.join(sidecar_directory, report_stem_name + "_errors.csv")
        info_file = os.path.join(sidecar_directory, report_stem_name + "_info.csv")
    else:
        error_file = stem + "_errors.csv"
        info_file = stem + "_info.csv"
    write_csv(
        error_file,
        ERROR_COLUMNS,
        errors,
        delimiter=delimiter,
        include_header=csv_include_header,
    )

    info_rows = information_rows(
        mode=mode,
        status_filter=status_filter,
        api_version=api_version,
        since=since,
        until=until,
        input_file=input_file,
        date_source=date_source,
        output_format="csv",
        images_enabled=False,
        input_source=input_source,
        source_reference=source_reference,
        csv_delimiter=delimiter,
        csv_include_header=csv_include_header,
    )
    with open(info_file, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
        rows_to_write = info_rows if csv_include_header else info_rows[1:]
        for row in rows_to_write:
            writer.writerow([sanitize_spreadsheet_text(value) for value in row])

    return ExportResult(
        report_file=os.path.abspath(output_file),
        error_file=os.path.abspath(error_file),
        info_file=os.path.abspath(info_file),
    )
