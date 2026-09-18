from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.report_check import BOUNDARIES, TENSES, check_report, main, parse_report

MINIMAL_CARD = """
主张：该订单已进入交付阶段
时态：EVENT_BY_DATE
观察到什么：公司公告显示 2026-08-01 交付完成（来源：巨潮公告）
可以推出什么：交付环节已闭合
不能推出什么：尚未推出验收、收入与回款已闭合
对决策的影响：维持观察，等待验收公告
证据边界：INFERENCE
最强反例：无公开来源否定交付事实；裁决：维持 INFERENCE
"""

SCAFFOLD = """
## 二、主张树

根结论（条件式）← 主张卡 #1 [INFERENCE] ← 观察：交付公告 2026-08-01

## 五、决策菜单

- WATCH_ONLY：等待验收公告（所需证据：验收完成公告）
- 等待验证：验收环节（所需证据：验收公告）

## 七、建议锚草稿

- 标的：示例公司；主张：验收将于 Q4 完成；状态：active；更新触发器：2026-12-31 验收公告
"""


def minimal_report(card: str = MINIMAL_CARD, next_line: str = "唯一下一验证：获取验收公告，用它核验验收是否完成", scaffold: str = SCAFFOLD) -> str:
    return (
        "# 测试报告\n\n"
        "决策问题：验收是否完成；时间边界：至 2026-08-19；as-of：2026-08-19；来源资格：一手公告\n\n"
        "## 根结论\n\n"
        "公开证据支持交付环节闭合，验收、收入与现金尚未闭合，现实状态未知。若验收公告出现则升级为验收闭合，若 Q4 未出现则降级。\n\n"
        "## 主张卡\n\n"
        + card
        + "\n\n"
        + next_line
        + "\n"
        + scaffold
        + "\n"
    )


class TestParseReport(unittest.TestCase):
    def test_card_splitting(self) -> None:
        text = minimal_report() + "\n\n主张：第二条\n时态：TIMELESS\n观察到什么：无\n可以推出什么：无\n不能推出什么：无\n对决策的影响：无\n证据边界：INSUFFICIENT\n"
        parsed = parse_report(text)
        self.assertEqual(len(parsed["cards"]), 2)
        self.assertTrue(parsed["root"])
        self.assertTrue(parsed["as_of"])
        self.assertEqual(len(parsed["next"]), 1)

    def test_no_cards(self) -> None:
        parsed = parse_report("# 空报告\n\n没有主张卡\n")
        self.assertEqual(parsed["cards"], [])


class TestCheckReport(unittest.TestCase):
    def test_minimal_passes(self) -> None:
        result = check_report(minimal_report())
        self.assertEqual(result["status"], "DELIVERY_READY")
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["card_count"], 1)

    def test_missing_next_verification(self) -> None:
        result = check_report(minimal_report(next_line=""))
        self.assertIn("报告缺少唯一下一验证", result["failures"])
        self.assertEqual(result["status"], "DELIVERY_INCOMPLETE")

    def test_invalid_tense(self) -> None:
        result = check_report(minimal_report(card=MINIMAL_CARD.replace("EVENT_BY_DATE", "SOMEDAY")))
        self.assertTrue(any("时态" in f for f in result["failures"]), result["failures"])

    def test_two_boundary_labels(self) -> None:
        card = MINIMAL_CARD.replace("证据边界：INFERENCE", "证据边界：FACT / INFERENCE")
        result = check_report(minimal_report(card=card))
        self.assertTrue(any("多个标签" in f for f in result["failures"]), result["failures"])

    def test_missing_fields(self) -> None:
        card = "主张：缺字段\n时态：TIMELESS\n"
        result = check_report(minimal_report(card=card))
        self.assertTrue(any("缺少字段" in f for f in result["failures"]), result["failures"])

    def test_negation_with_insufficient_warns(self) -> None:
        card = MINIMAL_CARD.replace("证据边界：INFERENCE", "证据边界：INSUFFICIENT").replace(
            "主张：该订单已进入交付阶段", "主张：该公司尚不存在该业务"
        )
        result = check_report(minimal_report(card=card))
        self.assertEqual(result["status"], "DELIVERY_READY", result["failures"])
        self.assertTrue(any("现实否定" in w for w in result["warnings"]), result["warnings"])

    def test_singularity_warning(self) -> None:
        result = check_report(minimal_report(next_line="唯一下一验证：获取验收公告和发票，核验收入与验收"))
        self.assertTrue(any("疑似包含多个证据对象" in w for w in result["warnings"]), result["warnings"])

    def test_scaffold_complete_no_quality_warnings(self) -> None:
        result = check_report(minimal_report())
        quality = ("页眉要素", "主张树", "决策菜单", "建议锚草稿", "条件式", "最强反例")
        self.assertFalse(any(any(key in w for key in quality) for w in result["warnings"]), result["warnings"])

    def test_scaffold_missing_warns(self) -> None:
        result = check_report(minimal_report(scaffold=""))
        self.assertTrue(any("主张树" in w for w in result["warnings"]), result["warnings"])
        self.assertTrue(any("决策菜单" in w for w in result["warnings"]), result["warnings"])
        self.assertTrue(any("建议锚草稿" in w for w in result["warnings"]), result["warnings"])

    def test_countercase_missing_warns(self) -> None:
        card = MINIMAL_CARD.replace("最强反例：无公开来源否定交付事实；裁决：维持 INFERENCE", "")
        result = check_report(minimal_report(card=card))
        self.assertTrue(any("最强反例" in w for w in result["warnings"]), result["warnings"])
        self.assertEqual(result["status"], "DELIVERY_READY", "反例缺失是告警不是阻断")


class TestMain(unittest.TestCase):
    def test_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            path.write_text(minimal_report(), encoding="utf-8")
            with open(Path(tmp) / "out.json", "w", encoding="utf-8") as out:
                import contextlib
                import sys

                with contextlib.redirect_stdout(out):
                    code = main([str(path), "--json"])
                self.assertEqual(code, 0)
            parsed = json.loads((Path(tmp) / "out.json").read_text(encoding="utf-8"))
            self.assertEqual(parsed["status"], "DELIVERY_READY")

    def test_cli_missing_file(self) -> None:
        code = main(["/nonexistent/report.md", "--json"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
