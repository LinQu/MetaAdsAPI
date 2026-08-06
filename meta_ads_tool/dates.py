"""Date preset parsing and validation."""

import argparse
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from .constants import PRESET_CHOICES

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


_PRESET_ALIASES = {
    "hari-ini": "hari-ini",
    "today": "hari-ini",
    "kemarin": "kemarin",
    "yesterday": "kemarin",
    "7-hari-terakhir": "7-hari-terakhir",
    "7hari": "7-hari-terakhir",
    "last-7-days": "7-hari-terakhir",
    "30-hari-terakhir": "30-hari-terakhir",
    "30hari": "30-hari-terakhir",
    "last-30-days": "30-hari-terakhir",
    "bulan-ini": "bulan-ini",
    "this-month": "bulan-ini",
    "bulan-lalu": "bulan-lalu",
    "last-month": "bulan-lalu",
}


def normalize_preset(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    if normalized not in _PRESET_ALIASES:
        raise argparse.ArgumentTypeError(
            "preset harus salah satu dari: {}".format(", ".join(PRESET_CHOICES))
        )
    return _PRESET_ALIASES[normalized]


def parse_iso_date(value: str, label: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError("{} harus berformat YYYY-MM-DD.".format(label))


def today_jakarta() -> date:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("Asia/Jakarta")).date()
        except Exception:
            pass
    return datetime.now().astimezone().date()


def preset_date_range(preset: str, today: Optional[date] = None) -> Tuple[date, date]:
    current = today or today_jakarta()
    preset = normalize_preset(preset)

    if preset == "hari-ini":
        return current, current
    if preset == "kemarin":
        previous = current - timedelta(days=1)
        return previous, previous
    if preset == "7-hari-terakhir":
        return current - timedelta(days=6), current
    if preset == "30-hari-terakhir":
        return current - timedelta(days=29), current
    if preset == "bulan-ini":
        return current.replace(day=1), current
    if preset == "bulan-lalu":
        last_day_previous = current.replace(day=1) - timedelta(days=1)
        first_day_previous = last_day_previous.replace(day=1)
        return first_day_previous, last_day_previous

    raise ValueError("Preset tidak dikenali: {}".format(preset))


def resolve_date_range(
    since_value: Optional[str],
    until_value: Optional[str],
    preset: Optional[str],
    env_since: str = "",
    env_until: str = "",
    env_preset: str = "",
    today: Optional[date] = None,
) -> Tuple[str, str, str]:
    """Resolve CLI and environment date inputs.

    Returns (since, until, source_label).
    """
    if preset and (since_value or until_value):
        raise ValueError("--preset tidak boleh digabung dengan --since/--until.")
    if bool(since_value) != bool(until_value):
        raise ValueError("--since dan --until harus diberikan bersamaan.")

    if preset:
        since_date, until_date = preset_date_range(preset, today=today)
        return since_date.isoformat(), until_date.isoformat(), "preset:{}".format(preset)

    if since_value and until_value:
        since_date = parse_iso_date(since_value, "--since")
        until_date = parse_iso_date(until_value, "--until")
        if since_date > until_date:
            raise ValueError("--since tidak boleh lebih besar dari --until.")
        return since_date.isoformat(), until_date.isoformat(), "manual"

    if env_preset:
        normalized = normalize_preset(env_preset)
        since_date, until_date = preset_date_range(normalized, today=today)
        return since_date.isoformat(), until_date.isoformat(), "env-preset:{}".format(normalized)

    if env_since or env_until:
        if not (env_since and env_until):
            raise ValueError(
                "META_REPORT_SINCE dan META_REPORT_UNTIL harus diisi bersamaan."
            )
        since_date = parse_iso_date(env_since, "META_REPORT_SINCE")
        until_date = parse_iso_date(env_until, "META_REPORT_UNTIL")
        if since_date > until_date:
            raise ValueError("META_REPORT_SINCE tidak boleh lebih besar dari META_REPORT_UNTIL.")
        return since_date.isoformat(), until_date.isoformat(), "environment"

    since_date, until_date = preset_date_range("bulan-ini", today=today)
    return since_date.isoformat(), until_date.isoformat(), "default:bulan-ini"
