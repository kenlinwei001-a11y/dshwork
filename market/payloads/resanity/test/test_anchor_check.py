from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.anchor_check import anchor_status, next_trigger, parse_dates


class AnchorDateTests(unittest.TestCase):
    def test_missed_explicit_and_bare_dates_stay_overdue(self) -> None:
        today = date(2026, 8, 14)
        self.assertEqual(parse_dates("2026-08-13", today), [date(2026, 8, 13)])
        self.assertEqual(parse_dates("8/13", today), [date(2026, 8, 13)])

    def test_invalid_calendar_date_is_rejected(self) -> None:
        self.assertEqual(parse_dates("2026-02-31", date(2026, 1, 1)), [])

    def test_full_slash_date_is_not_double_counted_as_bare_date(self) -> None:
        self.assertEqual(parse_dates("2026/08/25", date(2026, 8, 14)), [date(2026, 8, 25)])

    def test_next_trigger_returns_overdue_date(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            anchor = Path(raw_dir) / "主题.md"
            anchor.write_text("## 锚 1\n- 更新触发器：2026-08-13 半年报\n", encoding="utf-8")
            self.assertEqual(next_trigger(anchor, date(2026, 8, 14)), ("主题", date(2026, 8, 13)))

    def test_only_active_lifecycle_is_reminded(self) -> None:
        self.assertEqual(anchor_status("A1\n- 状态：active\n"), "active")
        self.assertEqual(anchor_status("A2\n- 状态：refuted\n"), "refuted")
        self.assertEqual(anchor_status("A3\n- status: realized\n"), "realized")
        self.assertEqual(anchor_status("A4 [archived]\n"), "archived")
        with tempfile.TemporaryDirectory() as raw_dir:
            anchor = Path(raw_dir) / "主题.md"
            anchor.write_text(
                "## A1\n- 状态：refuted\n- 更新触发器：2026-08-13\n"
                "\n## A2\n- 状态：active\n- 更新触发器：2026-08-20\n",
                encoding="utf-8",
            )
            self.assertEqual(next_trigger(anchor, date(2026, 8, 14)), ("主题", date(2026, 8, 20)))


if __name__ == "__main__":
    unittest.main()
