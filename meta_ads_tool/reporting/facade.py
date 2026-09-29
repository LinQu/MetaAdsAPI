"""Fasad ekspor laporan: pilih XLSX atau CSV."""

from typing import Any, Dict, List

from ..constants import CSV_DELIMITER
from .csv_writer import export_csv
from .result import ExportResult
from .xlsx.writer import export_xlsx


def export_report(
    output_format: str,
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
    image_width: int,
    image_height: int,
    embed_images: bool,
    input_source: str = "excel",
    source_reference: str = "",
    csv_delimiter: str = CSV_DELIMITER,
    csv_include_header: bool = True,
    auxiliary_directory: str = "",
) -> ExportResult:
    if output_format == "xlsx":
        return export_xlsx(
            output_file=output_file,
            mode=mode,
            rows=rows,
            errors=errors,
            input_file=input_file,
            api_version=api_version,
            since=since,
            until=until,
            status_filter=status_filter,
            date_source=date_source,
            image_width=image_width,
            image_height=image_height,
            embed_images=embed_images,
            input_source=input_source,
            source_reference=source_reference,
        )
    if output_format == "csv":
        return export_csv(
            output_file=output_file,
            mode=mode,
            rows=rows,
            errors=errors,
            input_file=input_file,
            api_version=api_version,
            since=since,
            until=until,
            status_filter=status_filter,
            date_source=date_source,
            input_source=input_source,
            source_reference=source_reference,
            csv_delimiter=csv_delimiter,
            csv_include_header=csv_include_header,
            auxiliary_directory=auxiliary_directory,
        )
    raise ValueError("Format output tidak didukung: {}".format(output_format))
