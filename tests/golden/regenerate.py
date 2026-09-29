"""Buat atau perbarui snapshot baseline golden.

Jalankan hanya setelah perubahan output disengaja dan sudah direview::

    python3 tests/golden/regenerate.py
    python3 tests/golden/regenerate.py excel_rinci_csv_pipe   # subset
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.golden import harness  # noqa: E402
from tests.golden.scenarios import SCENARIOS  # noqa: E402

SNAPSHOT_DIR = os.path.join(HERE, "snapshots")


def write_snapshot(name, data):
    path = os.path.join(SNAPSHOT_DIR, name + ".json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, sort_keys=True, indent=1)
        handle.write("\n")
    return path


def main(argv):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    requested = [item for item in argv if not item.startswith("-")]
    names = sorted(requested) if requested else sorted(SCENARIOS)

    unknown = [name for name in names if name not in SCENARIOS]
    if unknown:
        sys.stderr.write("Skenario tidak dikenal: {}\n".format(", ".join(unknown)))
        return 2

    for name in names:
        result = SCENARIOS[name].run()
        path = write_snapshot(name, result.as_dict())
        print("{:<38} exit={} -> {}".format(name, result.exit_code, path))
    return 0


def check_all_snapshots_present():
    """Pastikan setiap skenario punya baseline di dalam repository."""
    missing = [
        name
        for name in sorted(SCENARIOS)
        if not os.path.isfile(os.path.join(SNAPSHOT_DIR, name + ".json"))
    ]
    if missing:
        sys.stderr.write(
            "Snapshot baseline belum ada untuk: {}\n".format(", ".join(missing))
        )
        return False
    return True


if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        sys.exit(0 if check_all_snapshots_present() else 1)
    sys.exit(main(sys.argv[1:]))
