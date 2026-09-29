"""Konversi nilai sel untuk XLSX dan CSV."""

from datetime import date, datetime
from typing import Any

from .schema import (
    _DATE_COLUMNS,
    _DATETIME_COLUMNS,
    _ID_TEXT_COLUMNS,
    _NUMERIC_COLUMNS,
)


def sanitize_spreadsheet_text(value: Any) -> str:
    """Prevent Excel/CSV formula execution for untrusted text fields."""
    text = "" if value is None else str(value)
    probe = text.lstrip()
    if probe.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def to_number(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return sanitize_spreadsheet_text(value)
    if number.is_integer():
        return int(number)
    return number


def to_excel_date(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(text, fmt)
            if "T" in text:
                return parsed.replace(tzinfo=None)
            return parsed.date()
        except (TypeError, ValueError):
            continue
    return sanitize_spreadsheet_text(value)


def excel_value(column_name: str, value: Any) -> Any:
    if column_name in _ID_TEXT_COLUMNS:
        return sanitize_spreadsheet_text(value)
    if column_name in _DATE_COLUMNS or column_name in _DATETIME_COLUMNS:
        return to_excel_date(value)
    if column_name in _NUMERIC_COLUMNS:
        return to_number(value)
    if column_name == "CTR klik tautan":
        number = to_number(value)
        if isinstance(number, (int, float)):
            return float(number) / 100.0
        return number
    return sanitize_spreadsheet_text(value)


def to_csv_date(value: Any) -> str:
    """Format report dates as DD-MM-YYYY for delimited CSV output."""
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")

    text = str(value).strip()
    for fmt in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt).strftime("%d-%m-%Y")
        except (TypeError, ValueError):
            continue
    return sanitize_spreadsheet_text(value)


def csv_value(column_name: str, value: Any) -> Any:
    if column_name in _DATE_COLUMNS:
        return to_csv_date(value)
    if column_name in _NUMERIC_COLUMNS or column_name == "CTR klik tautan":
        return to_number(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return sanitize_spreadsheet_text(value)
