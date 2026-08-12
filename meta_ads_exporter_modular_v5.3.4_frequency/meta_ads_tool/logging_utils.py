"""Small timestamped logger designed for CLI and web terminal streaming."""

import os
import sys
from datetime import datetime
from typing import TextIO

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None  # type: ignore


def local_now() -> datetime:
    """Return current time in configured local timezone."""
    timezone_name = os.getenv("META_LOG_TIMEZONE", "Asia/Jakarta").strip()
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(timezone_name))
        except Exception:
            pass
    return datetime.now().astimezone()


def current_date_text() -> str:
    """Current process date in YYYY-MM-DD using META_LOG_TIMEZONE."""
    return local_now().strftime("%Y-%m-%d")


def _now_text() -> str:
    return local_now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str, level: str = "INFO", stream: TextIO = sys.stdout) -> None:
    """Write one immediately flushed log line."""
    print(
        "[{}] [{}] {}".format(_now_text(), level.upper(), message),
        file=stream,
        flush=True,
    )


def info(message: str) -> None:
    log(message, "INFO", sys.stdout)


def warning(message: str) -> None:
    log(message, "WARNING", sys.stderr)


def error(message: str) -> None:
    log(message, "ERROR", sys.stderr)
