from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "validation/v2/run_final_ab_dsh.py"
PRELAYER_PATH = ROOT / "validation/v2/run_dsh_prelayers.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("resanity_final_ab_dsh", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load DSH final A/B runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_prelayer():
    spec = importlib.util.spec_from_file_location("resanity_dsh_prelayers", PRELAYER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load DSH prelayer runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DshFinalAbRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_runner()
        cls.prelayer = load_prelayer()

    def test_prelayer_plan_keeps_natural_delivery_regression(self) -> None:
        layers = self.prelayer.plan(self.runner.BASE.load_suite())
        self.assertEqual(sum(len(rows) for rows in layers.values()), 25)
        delivery = [
            case
            for case in layers["trigger"]
            if case["id"] == "T11-natural-investing-delivery"
        ]
        self.assertEqual(len(delivery), 1)
        self.assertTrue(delivery[0]["expected_invocation"])
        self.assertFalse(
            delivery[0]["delivery_regression"]["saved_report_required"]
        )

    def make_profile_pair(self, raw: str) -> SimpleNamespace:
        root = Path(raw)
        dsh_home = root / "dsh-home"
        baseline = dsh_home / "profiles/headless-baseline"
        candidate = dsh_home / "profiles/headless-resanity"
        baseline.mkdir(parents=True)
        active_root = candidate / "node_modules/resanity"
        (active_root / "references").mkdir(parents=True)
        shared = {
            "private": True,
            "dependencies": {
                "shared-helper": "1.0.0",
                "resanity-validation-budget": "file:/tmp/budget-guard",
            },
            "dsh": {"profile": {"bundles": ["base", "headless"]}},
        }
        (baseline / "package.json").write_text(json.dumps(shared), encoding="utf-8")
        candidate_package = json.loads(json.dumps(shared))
        candidate_package["dependencies"]["resanity"] = "file:resanity.tgz"
        candidate_package["dsh"]["profile"]["bundles"].append("resanity")
        candidate.mkdir(parents=True, exist_ok=True)
        (candidate / "package.json").write_text(
            json.dumps(candidate_package), encoding="utf-8"
        )
        shutil.copy2(ROOT / "SKILL.md", active_root / "SKILL.md")
        for name in ("investing.md", "anchors.md", "formal-audit.md"):
            shutil.copy2(ROOT / "references" / name, active_root / "references" / name)
        return SimpleNamespace(
            dsh_home=dsh_home,
            baseline_profile="headless-baseline",
            candidate_profile="headless-resanity",
            active_skill=active_root / "SKILL.md",
            candidate_root=ROOT,
            isolated_user_home=root / "empty-home",
            dsh_bin="unused-dsh",
        )

    def test_profile_pair_allows_only_one_resanity_delta(self) -> None:
        baseline_dump = "- id: base\n  name: base\n- id: headless\n  name: headless\n"
        candidate_dump = (
            baseline_dump
            + "# == /tmp/headless-resanity/cordis.patch.yml\n"
            + "- id: resanity\n  name: resanity\n"
        )
        skill_sha = self.runner.BASE.sha256_file(ROOT / "SKILL.md")
        with tempfile.TemporaryDirectory() as raw:
            args = self.make_profile_pair(raw)
            with mock.patch.object(
                self.runner,
                "dump_config",
                side_effect=[baseline_dump, candidate_dump],
            ):
                receipt = self.runner.profile_pair_receipt(args, skill_sha)
        self.assertEqual(receipt["status"], "PASS")
        self.assertFalse(receipt["baseline_profile"]["resanity_active"])
        self.assertEqual(
            receipt["candidate_profile"]["active_skill_sha256"], skill_sha
        )
        self.assertEqual(set(receipt["canonical_identities"]), {"core", "investing"})

    def test_profile_pair_rejects_non_resanity_config_drift(self) -> None:
        baseline_dump = "- id: base\n  config:\n    value: 1\n"
        candidate_dump = (
            "- id: base\n  config:\n    value: 2\n"
            "- id: resanity\n  name: resanity\n"
        )
        skill_sha = self.runner.BASE.sha256_file(ROOT / "SKILL.md")
        with tempfile.TemporaryDirectory() as raw:
            args = self.make_profile_pair(raw)
            with mock.patch.object(
                self.runner,
                "dump_config",
                side_effect=[baseline_dump, candidate_dump],
            ):
                with self.assertRaises(self.runner.FinalAbError):
                    self.runner.profile_pair_receipt(args, skill_sha)

    def test_session_patch_disables_retry_and_subagents(self) -> None:
        patch = self.runner.session_patch(
            Path("/tmp/one-session"), max_tool_calls=7, max_web_searches=3
        )
        self.assertIn("id: session-persistence-jsonl", patch)
        self.assertIn("id: resanity-validation-budget", patch)
        self.assertNotIn("name: resanity-validation-budget", patch)
        self.assertIn("maxToolCalls: 7", patch)
        self.assertIn("maxWebSearches: 3", patch)
        for plugin_id in self.runner.DISABLED_RUNTIME_PLUGINS:
            self.assertIn(f"id: {plugin_id}\n  disabled: true", patch)
        self.assertIn("tool-subagent-control", self.runner.DISABLED_RUNTIME_PLUGINS)
        self.assertIn("tool-workflow", self.runner.DISABLED_RUNTIME_PLUGINS)
        self.assertIn("tool-ralph", self.runner.DISABLED_RUNTIME_PLUGINS)
        for plugin_id in self.runner.WATCH_DISABLED_RUNTIME_PLUGINS:
            self.assertIn(f"id: {plugin_id}\n  config:\n    watch: false", patch)
        self.assertEqual(
            self.runner.WATCH_ENVIRONMENT["CHOKIDAR_USEPOLLING"], "1"
        )

    def test_dsh_metrics_and_skill_invocation_come_from_raw_events(self) -> None:
        events = [
            {"type": "session", "id": "session-1", "cwd": "/tmp/work"},
            {
                "type": "request/header",
                "data": {
                    "header": {
                        "config": {
                            "provider": "provider-1",
                            "model": "model-1",
                            "reasoningEffort": "max",
                        },
                        "tools": [{"name": "skill"}, {"name": "web_search"}],
                    }
                },
            },
            {
                "type": "tool/call",
                "data": {
                    "name": "skill",
                    "arguments": json.dumps({"name": "resanity"}),
                },
            },
            {
                "type": "step/end",
                "data": {
                    "usage": {
                        "inputTokens": 100,
                        "outputTokens": 20,
                        "reasoningTokens": 5,
                        "cacheReadTokens": 60,
                    }
                },
            },
        ]
        metrics = self.runner.parse_dsh_metrics(events)
        self.assertEqual(metrics["provider"], "provider-1")
        self.assertEqual(metrics["model"], "model-1")
        self.assertEqual(metrics["input_tokens"], 100)
        self.assertEqual(metrics["cache_read_tokens"], 60)
        self.assertEqual(metrics["tool_calls"], 1)
        self.assertEqual(self.runner.skill_names(events), ["resanity"])

    def test_budget_guard_denials_are_attempts_not_executions(self) -> None:
        events = [
            {
                "type": "tool/call",
                "data": {"callId": "one", "name": "web_search", "arguments": "{}"},
            },
            {
                "type": "tool/result",
                "data": {
                    "message": {
                        "source": {"kind": "tool", "callId": "one"},
                        "content": [{"type": "text", "text": "ok"}],
                    }
                },
            },
            {
                "type": "tool/call",
                "data": {"callId": "two", "name": "web_search", "arguments": "{}"},
            },
            {
                "type": "tool/result",
                "data": {
                    "message": {
                        "source": {"kind": "tool", "callId": "two"},
                        "content": [
                            {
                                "type": "text",
                                "text": "Error: RESANITY_VALIDATION_BUDGET_WEB_LIMIT",
                            }
                        ],
                    }
                },
            },
        ]
        metrics = self.runner.parse_dsh_metrics(events)
        self.assertEqual(metrics["tool_call_attempts"], 2)
        self.assertEqual(metrics["tool_calls"], 1)
        self.assertEqual(metrics["web_search"], 1)
        self.assertEqual(metrics["budget_denied_tool_calls"], 1)

    def test_command_nonzero_exit_is_visible_when_outer_result_is_not_error(self) -> None:
        events = [
            {
                "type": "tool/call",
                "data": {
                    "callId": "bash-1",
                    "name": "bash",
                    "arguments": {"command": "curl official.example"},
                },
            },
            {
                "type": "tool/result",
                "data": {
                    "isError": False,
                    "message": {
                        "source": {"kind": "tool", "callId": "bash-1"},
                        "content": [
                            {"type": "text", "text": "fetch failed\n[exit code: 1]"}
                        ],
                    },
                },
            },
        ]
        metrics = self.runner.parse_dsh_metrics(events)
        self.assertEqual(metrics["tool_result_failures"], 1)
        self.assertEqual(metrics["tool_result_failures_by_name"], {"bash": 1})
        self.assertEqual(
            metrics["tool_result_failure_reasons"], {"nonzero_exit_code": 1}
        )
        self.assertTrue(metrics["tool_trace"][1]["failed"])

    def test_t11_trace_requires_completed_profile_read_then_official_index(self) -> None:
        contract = {
            "profile_loaded_before_research": True,
            "official_index_first_for_ashare": True,
        }
        good = [
            {
                "type": "tool/call",
                "data": {
                    "callId": "read-1",
                    "name": "read",
                    "arguments": {"path": "/skill/references/investing.md"},
                },
            },
            {
                "type": "tool/result",
                "data": {
                    "message": {
                        "source": {"callId": "read-1"},
                        "content": [{"type": "text", "text": "profile"}],
                    }
                },
            },
            {
                "type": "tool/call",
                "data": {
                    "callId": "bash-1",
                    "name": "bash",
                    "arguments": {
                        "command": "python3 /skill/scripts/ashare_disclosures.py --ticker 002015 --as-of 2026-08-19"
                    },
                },
            },
        ]
        metrics = self.runner.parse_dsh_metrics(good)
        self.assertEqual(self.runner.trace_contract_failures(metrics, contract), [])
        receipt_trace = self.runner.receipt_tool_trace(metrics)
        self.assertNotIn("arguments", receipt_trace[0])
        self.assertEqual(
            receipt_trace[0]["argument_markers"], ["investing_profile"]
        )
        self.assertEqual(
            receipt_trace[2]["argument_markers"], ["ashare_disclosure_index"]
        )

        parallel = [good[0], good[2], good[1]]
        failures = self.runner.trace_contract_failures(
            self.runner.parse_dsh_metrics(parallel), contract
        )
        self.assertIn("delivery_profile_not_loaded_before_research", failures)

        search_first = [good[0], good[1], {
            "type": "tool/call",
            "data": {
                "callId": "web-1",
                "name": "web_search",
                "arguments": {"query": "002015 算力"},
            },
        }]
        failures = self.runner.trace_contract_failures(
            self.runner.parse_dsh_metrics(search_first), contract
        )
        self.assertIn("delivery_official_index_not_first", failures)

    def test_report_delivery_shape_rejects_tool_protocol_leaks(self) -> None:
        leaked = (
            "预算接近上限，随后交付。\n"
            "<｜｜DSML｜｜tool_calls>\n"
            "<｜｜DSML｜｜invoke name=\"write\">"
        )
        self.assertEqual(
            self.runner.report_delivery_failures(leaked),
            ["report_tool_protocol_leak"],
        )
        self.assertEqual(
            self.runner.report_delivery_failures(
                "# 根结论\n\n证据不足。\n\n# 来源表\n\n- E1"
            ),
            [],
        )
        self.assertEqual(
            self.runner.report_delivery_failures("  \n"), ["report_missing"]
        )

    def test_report_delivery_shape_rejects_process_only_stdout(self) -> None:
        process_only = (
            "Budget check: active-research cap reached; one remaining call is "
            "reserved for the required deliverable write."
        )
        self.assertEqual(
            self.runner.report_delivery_failures(process_only),
            ["report_process_only"],
        )

    def test_t11_delivery_contract_is_executed_against_report_semantics(self) -> None:
        contract = {
            "report_required": True,
            "saved_report_required": False,
            "root_uses_evidence_language": True,
            "one_boundary_per_claim": True,
            "temporal_mode_per_claim": True,
            "one_next_evidence_object": True,
        }
        good = """## 根结论

截至 2026-08-19，公开证据支持公司曾披露能源与算力合作；尚未闭合项目投运、供电方式和可归属收入。现实中是否已经形成绿电加算力业务未知，因此当前为 NOT_EVALUABLE。

## 承重主张卡

### C1
主张：公司曾披露一项算力合作事件。
时态：EVENT_BY_DATE
观察到什么：2025-05-01 的公司公告写明签署合作协议。
可以推出什么：截至公告日合作事件已披露。
不能推出什么：不能推出项目已经投运或产生收入。
对决策的影响：保持不确定。
证据边界（针对“主张”整句）：INSUFFICIENT

## 唯一下一验证

获取公司 2026 年半年度报告，用它核验具名项目是否已投运并产生可归属收入。
"""
        self.assertEqual(
            self.runner.delivery_contract_failures(good, contract), []
        )

        bad = good.replace(
            "截至 2026-08-19，公开证据支持公司曾披露能源与算力合作；尚未闭合项目投运、供电方式和可归属收入。现实中是否已经形成绿电加算力业务未知，因此当前为 NOT_EVALUABLE。",
            "协鑫能科的绿电加算力布局未形成，因此假设不成立。",
        ).replace("EVENT_BY_DATE", "STATE_AT_AS_OF")
        failures = self.runner.delivery_contract_failures(bad, contract)
        self.assertIn("delivery_root_evidence_language", failures)
        self.assertIn("delivery_root_reality_negation", failures)
        self.assertIn("delivery_claim_state_without_coverage:C1", failures)

    def test_t11_absence_mode_requires_named_corpus_and_date_range(self) -> None:
        report = """## 根结论
截至 2026-08-19，公开证据支持已披露合作；尚未闭合项目状态。现实中是否已经形成业务未知，因此当前为 NOT_EVALUABLE。
## 主张卡
### C1
主张：范围内未发现项目投运公告。
时态：ABSENCE_BY_AS_OF
观察到什么：没有找到。
可以推出什么：无。
不能推出什么：不能推出不存在。
对决策的影响：保持不确定。
证据边界（针对“主张”整句）：INSUFFICIENT
## 唯一下一验证
获取公司 2026 年半年度报告，用它核验项目状态。
"""
        failures = self.runner.delivery_contract_failures(
            report,
            {
                "root_uses_evidence_language": True,
                "one_boundary_per_claim": True,
                "temporal_mode_per_claim": True,
                "one_next_evidence_object": True,
            },
        )
        self.assertIn("delivery_claim_absence_without_corpus:C1", failures)

    def test_next_evidence_object_allows_nested_field_but_rejects_multiple_artifacts(self) -> None:
        self.assertTrue(
            self.runner.one_next_evidence_object(
                "获取公司半年度报告中的项目收入明细，用它核验经济暴露。"
            )
        )
        self.assertFalse(
            self.runner.one_next_evidence_object(
                "同时索取项目合同、发票和结算单，用它们核验收入。"
            )
        )

    def test_workspace_report_is_recovered_without_becoming_host_success(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "REPORT.md").write_text(
                "# 根结论\n\n证据不足。\n", encoding="utf-8"
            )
            destination = root / "artifacts" / "recovered-report.md"
            recovered = self.runner.recover_workspace_report(workspace, destination)
            self.assertIsNotNone(recovered)
            self.assertTrue(destination.is_file())
            self.assertEqual(recovered["path"], "recovered-report.md")
            self.assertEqual(
                recovered["sha256"], self.runner.BASE.sha256_file(destination)
            )

    def test_prelayer_failure_recovers_report_but_stays_host_incomplete(self) -> None:
        process_only = (
            "Budget check: active-research cap reached; one remaining call is "
            "reserved for the required deliverable write."
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            output = root / "output"
            workspace = output / "workspaces" / "Q01"
            artifact = output / "cases" / "Q01"
            args = SimpleNamespace(
                output=output,
                dsh_bin="unused-dsh",
                dsh_home=root / "dsh-home",
                candidate_profile="headless-resanity",
                max_tool_calls=30,
                max_web_searches=15,
                max_non_cached_input_tokens=150_000,
                max_wall_seconds=900,
                zstd_bin="unused-zstd",
                expected_provider="deepseek-official",
                expected_model="deepseek-v4-pro",
                expected_reasoning_effort="max",
            )

            def failed_run(*_args, **kwargs):
                cwd = Path(kwargs["cwd"])
                (cwd / "REPORT.md").write_text(
                    "# 根结论\n\n已交付可读报告。\n", encoding="utf-8"
                )
                return SimpleNamespace(returncode=1, stdout=process_only, stderr="quota")

            with mock.patch.object(
                self.prelayer.subprocess, "run", side_effect=failed_run
            ):
                row = self.prelayer.run_session(
                    args=args,
                    case={
                        "id": "Q01",
                        "layer": "core_contract",
                        "profile": "core",
                        "mode": "closed",
                    },
                    prompt="frozen prompt",
                    workspace=workspace,
                    artifact=artifact,
                )

            self.assertFalse(row["host_complete"])
            self.assertFalse(row["report_present"])
            self.assertTrue(row["report_available"])
            self.assertEqual(row["report_origin"], "workspace_recovery")
            self.assertTrue(row["recovered_report"])
            self.assertIn("dsh_exit_code", row["mechanical_failures"])
            self.assertIn("report_process_only", row["mechanical_failures"])
            self.assertTrue((artifact / "stdout.md").is_file())
            self.assertTrue((artifact / "report.md").is_file())
            self.assertTrue((artifact / "recovered-report.md").is_file())
            self.assertEqual(
                (artifact / "report.md").read_text(encoding="utf-8"),
                "# 根结论\n\n已交付可读报告。\n",
            )

    def test_prelayer_run_session_consumes_t11_delivery_and_trace_contract(self) -> None:
        report = """## 根结论
截至 2026-08-19，公开证据支持公司披露合作；尚未闭合项目状态和收入。现实中是否已经形成业务未知，因此当前为 NOT_EVALUABLE。
## 主张卡
### C1
主张：公司披露过合作事件。
时态：EVENT_BY_DATE
观察到什么：2026-01-01 公司公告披露合作。
可以推出什么：合作事件被披露。
不能推出什么：不能推出项目投运。
对决策的影响：保持不确定。
证据边界（针对“主张”整句）：INSUFFICIENT
## 唯一下一验证
获取公司半年度报告，用它核验项目投运状态。
"""
        contract = {
            "report_required": True,
            "saved_report_required": False,
            "root_uses_evidence_language": True,
            "one_boundary_per_claim": True,
            "temporal_mode_per_claim": True,
            "one_next_evidence_object": True,
            "profile_loaded_before_research": True,
            "official_index_first_for_ashare": True,
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            output = root / "output"
            workspace = output / "workspaces" / "T11"
            artifact = output / "cases" / "T11"
            args = SimpleNamespace(
                output=output,
                dsh_bin="unused-dsh",
                dsh_home=root / "dsh-home",
                candidate_profile="headless-resanity",
                max_tool_calls=30,
                max_web_searches=15,
                max_non_cached_input_tokens=150_000,
                max_wall_seconds=900,
                zstd_bin="unused-zstd",
                expected_provider="deepseek-official",
                expected_model="deepseek-v4-pro",
                expected_reasoning_effort="max",
            )

            def completed_run(*_args, **_kwargs):
                session = artifact / "session-store" / "one" / "session.jsonl.zstd"
                session.parent.mkdir(parents=True)
                session.write_bytes(b"fixture")
                return SimpleNamespace(returncode=0, stdout=report, stderr="")

            events = [
                {"type": "session", "id": "session-1", "cwd": str(workspace)},
                {"type": "permission/preset", "data": {"preset": "workspace-write"}},
                {"type": "sandbox/mode", "data": {"mode": "workspace-write"}},
                {"type": "approval/policy", "data": {"policy": "ask"}},
                {
                    "type": "request/header",
                    "data": {
                        "header": {
                            "config": {
                                "provider": "deepseek-official",
                                "model": "deepseek-v4-pro",
                                "reasoningEffort": "max",
                            },
                            "tools": [
                                {"name": "skill"},
                                {"name": "read"},
                                {"name": "bash"},
                            ],
                        }
                    },
                },
                {
                    "type": "tool/call",
                    "data": {
                        "callId": "skill-1",
                        "name": "skill",
                        "arguments": json.dumps({"name": "resanity"}),
                    },
                },
                {
                    "type": "tool/call",
                    "data": {
                        "callId": "read-1",
                        "name": "read",
                        "arguments": {"path": "/skill/references/investing.md"},
                    },
                },
                {
                    "type": "tool/result",
                    "data": {
                        "message": {
                            "source": {"callId": "read-1"},
                            "content": [{"type": "text", "text": "profile"}],
                        }
                    },
                },
                {
                    "type": "tool/call",
                    "data": {
                        "callId": "bash-1",
                        "name": "bash",
                        "arguments": {
                            "command": "python3 /skill/scripts/ashare_disclosures.py --ticker 002015 --as-of 2026-08-19"
                        },
                    },
                },
            ]
            with mock.patch.object(
                self.prelayer.subprocess, "run", side_effect=completed_run
            ), mock.patch.object(
                self.prelayer.DSH, "read_dsh_events", return_value=events
            ):
                row = self.prelayer.run_session(
                    args=args,
                    case={
                        "id": "T11",
                        "layer": "trigger",
                        "expected_invocation": True,
                        "delivery_regression": contract,
                    },
                    prompt="natural investing prompt",
                    workspace=workspace,
                    artifact=artifact,
                )

            self.assertTrue(row["host_complete"])
            self.assertEqual(row["delivery_contract_failures"], [])
            self.assertEqual(row["trace_contract_failures"], [])


if __name__ == "__main__":
    unittest.main()
