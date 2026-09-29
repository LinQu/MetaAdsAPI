"""Golden regression tests.

Test ini menjalankan exporter pada kombinasi mode/format/delimiter/lokasi
output, lalu membandingkan hasilnya dengan snapshot baseline yang disimpan di
``tests/golden/snapshots``.

Tujuan: memastikan refactor internal TIDAK mengubah file laporan yang
dihasilkan.

Untuk memperbarui baseline setelah perubahan yang disengaja:

    python3 tests/golden/regenerate.py
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GOLDEN_DIR = os.path.join(HERE, "golden")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.golden.scenarios import SCENARIOS  # noqa: E402

SNAPSHOT_DIR = os.path.join(GOLDEN_DIR, "snapshots")

MISSING_SNAPSHOT = (
    "\nSnapshot belum ada. Jalankan:\n"
    "    python3 tests/golden/regenerate.py\n"
)


def snapshot_path(name):
    return os.path.join(SNAPSHOT_DIR, name + ".json")


def load_snapshot(name):
    path = snapshot_path(name)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _describe_difference(expected, actual):
    """Beri ringkasan diff yang berguna saat golden test gagal."""
    lines = []
    if expected is None:
        return "baseline belum ada"
    if expected.get("exit_code") != actual.get("exit_code"):
        lines.append(
            "exit_code: expected={} actual={}".format(
                expected.get("exit_code"), actual.get("exit_code")
            )
        )
    expected_artifacts = expected.get("artifacts", {})
    actual_artifacts = actual.get("artifacts", {})

    for key in sorted(set(expected_artifacts) | set(actual_artifacts)):
        left = expected_artifacts.get(key)
        right = actual_artifacts.get(key)
        if left is None:
            lines.append("{}: artefak baru muncul di output (tidak ada di baseline)".format(key))
            continue
        if right is None:
            lines.append("{}: artefak hilang dari output (ada di baseline)".format(key))
            continue
        left_text = json.dumps(left, ensure_ascii=False, sort_keys=True, indent=1)
        right_text = json.dumps(right, ensure_ascii=False, sort_keys=True, indent=1)
        if left_text == right_text:
            continue
        left_rows = left.get("rows") or []
        right_rows = right.get("rows") or []
        if len(left_rows) != len(right_rows):
            lines.append(
                "{}: jumlah baris berbeda expected={} actual={}".format(
                    key, len(left_rows), len(right_rows)
                )
            )
        for index, (row_left, row_right) in enumerate(zip(left_rows, right_rows)):
            if row_left != row_right:
                lines.append("{} baris {} berbeda:".format(key, index))
                for column, (a, b) in enumerate(zip(row_left, row_right)):
                    if a != b:
                        lines.append("  kolom {}: {!r} -> {!r}".format(column, a, b))
                break
        if not left_rows and not right_rows:
            lines.append("{}: struktur berbeda (bukan tabular)".format(key))
            lines.append("  expected keys: {}".format(sorted(left.keys())))
            lines.append("  actual keys  : {}".format(sorted(right.keys())))
            for field in sorted(set(left.keys()) & set(right.keys())):
                if left[field] != right[field]:
                    lines.append("  field {!r} berbeda".format(field))
    if not lines:
        lines.append("artefak sama secara tekstual namun berbeda serialisasi")
    return "\n".join(lines)


class GoldenOutputTests(unittest.TestCase):
    """Setiap skenario dibandingkan dengan snapshot baseline-nya."""

    def _check(self, name):
        result = SCENARIOS[name].run()
        actual = result.as_dict()
        expected = load_snapshot(name)
        if expected is None:
            self.fail("Snapshot '{}' belum ada.{}".format(name, MISSING_SNAPSHOT))
        if expected != actual:
            self.fail(
                "Output skenario '{}' berubah.\n{}".format(
                    name, _describe_difference(expected, actual)
                )
            )

    def test_all_scenarios(self):
        for name in sorted(SCENARIOS):
            with self.subTest(scenario=name):
                self._check(name)


if __name__ == "__main__":
    unittest.main()
