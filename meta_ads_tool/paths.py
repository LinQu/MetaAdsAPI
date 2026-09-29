"""Resolusi folder output dan folder teknis.

Pemisahan ini membuat cli.py hanya menangani parsing argumen dan orkestrasi,
tanpa harus tahu detail filesystem.
"""

import os


def project_root() -> str:
    """Return the project folder that contains ScrapeMeta.py."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def home_report_directory() -> str:
    """Return the portable report folder under the current user home."""
    return os.path.join(os.path.expanduser("~"), "laporan")


def auxiliary_output_directory() -> str:
    """Keep technical CSV/checkpoint files in the project folder."""
    return project_root()
