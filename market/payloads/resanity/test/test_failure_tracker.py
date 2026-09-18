from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.failure_tracker import aggregate, main, scan_dir

TODAY = date(2026, 8, 25)


def make_anchors(directory: Path) -> None:
    (directory / "refuted.md").write_text(
        "## 锚A\n- 状态：refuted\n- 失效类型：tense\n- 检验结果：公告晚于预期\n\n"
        "## 锚B\n- 状态：refuted\n- 检验结果：无类型标注\n",
        encoding="utf-8",
    )
    (directory / "overdue.md").write_text(
        "## 锚C\n- 状态：active\n- 更新触发器：2020-01-01 财报\n",
        encoding="utf-8",
    )
    (directory / "reviewed.md").write_text(
        "## 锚D\n- 状态：active\n- 更新触发器：2020-01-01 财报\n- 检验结果：确认\n",
        encoding="utf-8",
    )
    (directory / "realized.md").write_text(
        "## 锚E\n- 状态：realized\n- 失效类型：tense\n- 更新触发器：2020-01-01\n",
        encoding="utf-8",
    )
    (directory / "README.md").write_text("# 仪表盘\n", encoding="utf-8")


class TestFailureTracker(unittest.TestCase):
    def test_scan_and_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "anchors"
            root.mkdir()
            make_anchors(root)
            result = aggregate([str(root)], today=TODAY)
            self.assertEqual(result["refuted_count"], 2)
            self.assertEqual(result["failure_types"], {"tense": 1})
            self.assertEqual(result["overdue_active"], 1)
            self.assertEqual(result["themes_refuted"], ["refuted.md"])
            self.assertTrue(any("未标注失效类型" in w for w in result["warnings"]), result["warnings"])
            self.assertTrue(any("overdue" in w for w in result["warnings"]), result["warnings"])

    def test_missing_roots_tolerated(self) -> None:
        result = aggregate(["/nonexistent/anchors"], today=TODAY)
        self.assertEqual(result["roots_scanned"], 0)
        self.assertEqual(result["refuted_count"], 0)

    def test_scan_dir_skips_skip_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "anchors"
            root.mkdir()
            (root / "_template.md").write_text("## 锚X\n- 状态：refuted\n- 失效类型：tense\n", encoding="utf-8")
            result = scan_dir(root, TODAY)
            self.assertEqual(result["refuted"], [])
            self.assertEqual(result["overdue"], [])

    def test_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "anchors"
            root.mkdir()
            make_anchors(root)
            code = main([str(root), "--json"])
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
