from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ValidationContractTests(unittest.TestCase):
    def test_canonical_skill_is_thin_and_routes_profiles(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for marker in (
            "原子主张协议",
            "观察到什么",
            "时态：EVENT_BY_DATE / STATE_AT_AS_OF / ABSENCE_BY_AS_OF / TIMELESS",
            "可以推出什么",
            "不能推出什么",
            "对决策的影响",
            "每张主张卡都不得省略",
            "因果、归纳、外推、可能性、价值判断",
            "X 说明 Y 尚未闭合",
            "每张卡只给“主张”整句一个证据边界",
            "不要在边界行拆成多个标签",
            "形式逻辑裁决也属于推断",
            "必须收录报告中每个承重来源",
            "只观察到原始数值差时",
            "相容性证据与区分性证据",
            "动作已生效、覆盖范围已确认",
            "已保存来源若含相反或限定性观察",
            "逐字服从带日期原始文件",
            "references/investing.md",
            "references/anchors.md",
            "references/formal-audit.md",
            "普通总结、编码、改写或一般问答",
            "即使对象尚未给全也应使用",
            "不得把工程测试、机械审计或有限评审升级成研究有效",
            "用户可直接阅读的回答始终是第一交付物",
            "用户提供且要求接受的信息可作为 `USER_PROVIDED` 前提",
            "报告交付与机械审计是两条独立轴",
            "不得改写成“报告未完成”",
            "不建立运行状态机",
            "交付编译（不得省略）",
            "SINGLE_UPSTREAM_SOURCE",
            "一个外部证据获取单元",
        ):
            self.assertIn(marker, skill)
        self.assertLess(len(skill.splitlines()), 100)
        self.assertNotIn("候选论点（多头/基准/空头）", skill)
        self.assertNotIn("≤3 个具名候选载体", skill)
        self.assertIn("不要仅因出现订单、合同、公告或验收等词", skill)

    def test_references_keep_domain_details_off_the_hot_path(self) -> None:
        investing = (ROOT / "references/investing.md").read_text(encoding="utf-8")
        anchors = (ROOT / "references/anchors.md").read_text(encoding="utf-8")
        formal = (ROOT / "references/formal-audit.md").read_text(encoding="utf-8")
        self.assertIn("完整报告格式", investing)
        self.assertIn("市场已经定价", investing)
        self.assertIn("没有被材料证明", investing)
        self.assertIn("不得写“未收到”“未形成”“不存在”", investing)
        for lifecycle in ("active", "refuted", "realized", "archived"):
            self.assertIn(lifecycle, anchors)
        self.assertIn("active_locator", formal)
        self.assertIn("profile_sha256", formal)
        self.assertIn("不得理解或改写结论", formal)
        self.assertIn("报告先于审计", formal)
        self.assertIn("不是状态机", formal)
        self.assertIn("不能阻止报告本身", formal)
        self.assertIn("先保存 `report.md`", formal)
        self.assertIn("写成“报告未生成”", formal)
        self.assertIn("输入 provenance", formal)
        self.assertIn("不是 `boundary` 或 `source.kind`", formal)

    def test_v2_suite_has_all_layers_and_conservative_triggers(self) -> None:
        suite = json.loads(
            (ROOT / "validation/v2/suite.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            list(suite["layers"]),
            [
                "core_contract",
                "investing_profile",
                "open_network",
                "anchor",
                "trigger",
                "install_identity",
                "final_ab",
            ],
        )
        triggers = suite["layers"]["trigger"]["cases"]
        self.assertTrue(any(row["reason"] == "investment-auto" for row in triggers))
        self.assertTrue(
            any(row["reason"] == "explicit-non-investing" for row in triggers)
        )
        for reason in (
            "ordinary-summary",
            "ordinary-coding",
            "ordinary-writing",
            "ordinary-translation",
            "ordinary-qa",
        ):
            self.assertTrue(
                any(
                    row["reason"] == reason and row["expected_invocation"] is False
                    for row in triggers
                )
            )
        self.assertEqual(suite["layers"]["final_ab"]["result_status"], "NOT_RUN")
        self.assertTrue(suite["layers"]["final_ab"]["task_prompts_neutral"])
        self.assertEqual(suite["method_status"], "UNBENCHMARKED_CURRENT")
        delivery_cases = [
            row for row in triggers if isinstance(row.get("delivery_regression"), dict)
        ]
        self.assertEqual(len(delivery_cases), 1)
        self.assertEqual(delivery_cases[0]["id"], "T11-natural-investing-delivery")
        self.assertNotIn("Resanity", delivery_cases[0]["input"])
        self.assertEqual(
            delivery_cases[0]["delivery_regression"],
            {
                "report_required": True,
                "saved_report_required": False,
                "root_uses_evidence_language": True,
                "one_boundary_per_claim": True,
                "temporal_mode_per_claim": True,
                "one_next_evidence_object": True,
                "profile_loaded_before_research": True,
                "official_index_first_for_ashare": True,
            },
        )
        prelayers = json.loads(
            (ROOT / "validation/v2/prelayers-receipt-template.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            prelayers["schema_version"], "resanity.prelayers-receipt.v2"
        )
        self.assertEqual(
            set(prelayers["candidate_profiles_sha256"]),
            {"core", "investing", "anchors", "formal-audit"},
        )

        anchor_cases = suite["layers"]["anchor"]["cases"]
        self.assertEqual(len(anchor_cases), 6)
        groups = {case["workspace_group"] for case in anchor_cases}
        self.assertEqual(groups, {"A01", "A02", "A03"})
        for group in groups:
            self.assertEqual(
                sum(case["workspace_group"] == group for case in anchor_cases), 2
            )

    def test_final_ab_task_prompts_do_not_leak_candidate_method(self) -> None:
        suite = json.loads(
            (ROOT / "validation/v2/suite.json").read_text(encoding="utf-8")
        )
        prompt_by_id = {
            case["id"]: ROOT / "validation/v2" / case["prompt"]
            for layer_name in (
                "core_contract",
                "investing_profile",
                "open_network",
            )
            for case in suite["layers"][layer_name]["cases"]
        }
        forbidden = (
            "resanity",
            "$resanity",
            "原子主张卡",
            "投资 profile",
            "watch_only",
            "not_evaluable",
            "setup",
        )
        for case_id in suite["layers"]["final_ab"]["case_ids"]:
            text = prompt_by_id[case_id].read_text(encoding="utf-8").lower()
            for marker in forbidden:
                self.assertNotIn(marker, text, f"{case_id} leaks {marker}")
        candidate = (
            ROOT
            / "validation/v2"
            / suite["layers"]["final_ab"]["candidate_prompt"]
        ).read_text(encoding="utf-8")
        self.assertIn("$resanity", candidate)

    def test_investing_closed_prompts_freeze_as_of_and_evidence_packets(self) -> None:
        for filename in ("investing-company.md", "investing-profit-pool.md"):
            prompt = (ROOT / "validation/v2/prompts" / filename).read_text(
                encoding="utf-8"
            )
            self.assertIn("as-of 为 2026-07-31", prompt)
            self.assertIn("封闭证据包", prompt)
            self.assertIn("不做外部检索", prompt)
            self.assertIn("E1｜2026-", prompt)
            self.assertGreaterEqual(prompt.count("- E"), 5)

    def test_method_contract_keeps_missingness_and_budget_rules_hot(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        investing = (ROOT / "references/investing.md").read_text(encoding="utf-8")
        self.assertIn("只有用户或宿主明确给出", skill)
        self.assertIn("不得猜测上限、已用次数或剩余次数", skill)
        self.assertIn("宿主计量与拒绝回执优先于模型估算", skill)
        self.assertIn("不得以待执行的工具请求、协议标记或半截表格结束", skill)
        self.assertIn("未知、未闭合或 `INSUFFICIENT` 是报告内容", skill)
        self.assertIn("随后才尝试来源快照、宿主收据和审计收据", skill)
        self.assertIn("来源资格当作硬边界", skill)
        self.assertIn("不得承重、不得进入承重快照", skill)
        self.assertIn("每个上游来源只保留一份规范原始快照", skill)
        self.assertIn("只有一项具名证据对象", skill)
        self.assertIn("用它裁决一个承重分叉", skill)
        self.assertIn("标题、根结论、摘要、表格和主张卡", investing)
        self.assertIn("现实中是否已经形成 {target} 未知", investing)
        self.assertIn("ashare_disclosures.py", investing)
        self.assertIn("不得把 profile 读取与搜索并行", investing)
        self.assertIn("没有额外证成时默认 `EVENT_BY_DATE`", investing)
        self.assertIn("无可归属暴露", investing)
        self.assertIn("同一血缘链", investing)
        self.assertIn("公司整体积压、收入、利润和经营现金流", investing)
        self.assertIn("TUSHARE > BAOSTOCK > AKSHARE_TENCENT", investing)
        self.assertIn("provider_override_reason", investing)
        self.assertIn("不自动尝试下一来源", investing)
        self.assertIn("同样适用于“公司合并口径”", investing)
        self.assertIn("不得写链条闭合、订单转化或回款兑现已被证明", investing)
        self.assertIn("交付前对标题、根结论和摘要做三项闸门", investing)
        self.assertIn("二手站点只可定位", investing)

    def test_dsh_prelayers_give_trigger_cases_a_neutral_budget(self) -> None:
        runner = (ROOT / "validation/v2/run_dsh_prelayers.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def trigger_instruction", runner)
        self.assertIn('prompt = trigger_instruction(args) + case["input"]', runner)
        self.assertNotIn('prompt = case["input"]', runner)

    def test_open_network_prompts_reject_post_as_of_backfill(self) -> None:
        for filename in (
            "network-product.md",
            "network-policy.md",
            "network-investing.md",
        ):
            prompt = (ROOT / "validation/v2/prompts" / filename).read_text(
                encoding="utf-8"
            )
            self.assertIn("2026-07-31", prompt)
            self.assertIn("无公开日期的可变当前页", prompt)
            self.assertIn("不得回填历史判断", prompt)

    def test_validation_source_contract_passes_without_semantic_claim(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/validation_source_check.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "VALIDATION_SOURCE_OK")
        self.assertEqual(payload["protocol"]["semantic_status"], "NOT_RUN")

    def test_internal_validation_corpus_is_not_in_package_files(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(
            package["scripts"]["validate:v2:ab:dsh"],
            "python3 validation/v2/run_final_ab_dsh.py",
        )
        self.assertEqual(
            package["scripts"]["validate:v2:prelayers:dsh"],
            "python3 validation/v2/run_dsh_prelayers.py",
        )
        self.assertNotIn("validation/", package["files"])
        self.assertNotIn("validation/v2/", package["files"])
        self.assertIn("validation/README.md", package["files"])
        self.assertNotIn("validation/v2/README.md", package["files"])
        self.assertIn("validation/receipt-template.json", package["files"])
        self.assertIn("references/", package["files"])
        self.assertIn("agents/", package["files"])
        self.assertIn("cordis.patch.yml", package["files"])
        self.assertEqual(package["dsh"]["bundle"]["patch"], "./cordis.patch.yml")
        self.assertNotIn("scripts/", package["files"])
        self.assertIn("scripts/ashare_disclosures.py", package["files"])
        self.assertIn("scripts/free_market_observations.py", package["files"])
        self.assertIn("scripts/tier1_providers.py", package["files"])

if __name__ == "__main__":
    unittest.main()
