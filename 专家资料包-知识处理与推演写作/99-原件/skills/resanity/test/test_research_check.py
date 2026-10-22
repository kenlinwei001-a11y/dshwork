from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.research_check import ROOT as REPO_ROOT
from tools.research_check import main, sha256_file, validate_receipt
from tools.skill_identity import file_locator, profile_identity


class ResearchCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.skill = self.root / "SKILL.md"
        self.report = self.root / "report.md"
        self.snapshot = self.root / "sources" / "E1.txt"
        self.prompt = self.root / "prompt.md"
        self.host_receipt = self.root / "host-receipt.json"
        self.raw_session = self.root / "raw-session.jsonl"
        self.skill.write_text("# frozen skill\n", encoding="utf-8")
        self.report.write_text(
            "# 报告\n\n截止日：2026-08-14\n\n[C1] 决定性事实。[E1]\n",
            encoding="utf-8",
        )
        self.snapshot.parent.mkdir()
        self.snapshot.write_text("official source snapshot\n", encoding="utf-8")
        self.prompt.write_text("question + exact instructions\n", encoding="utf-8")
        self.raw_session.write_text('{"type":"session","id":"session-test"}\n', encoding="utf-8")
        self.host_receipt_payload = {
            "schema_version": "resanity.host-receipt.v1",
            "host": "codex",
            "provider": "test-provider",
            "model": "test-model",
            "session_id": "session-test",
            "runtime": {
                "tokens_total": 100,
                "tool_calls": 2,
                "wall_seconds": 4,
            },
            "budget_usage": {
                "tokens_total": 100,
                "tool_calls": 2,
                "wall_seconds": 4,
                "search": 1,
                "fetch": 1,
            },
            "tool_calls_by_name": {"fetch": 1, "search": 1},
            "raw_session": {
                "path": "raw-session.jsonl",
                "sha256": sha256_file(self.raw_session),
            },
        }
        self.write_host_receipt()
        self.receipt_path = self.root / "report.receipt.json"
        self.receipt = {
            "schema_version": "resanity.audit-receipt.v2",
            "method": {
                "canonical_skill_sha256": sha256_file(self.skill),
                "profile": {
                    "name": "core",
                    "sha256": profile_identity(self.root, "core")["sha256"],
                },
                "active": {
                    "locator": file_locator(self.skill),
                    "skill_sha256": sha256_file(self.skill),
                    "profile_sha256": profile_identity(self.root, "core")["sha256"],
                },
            },
            "report": {
                "path": "report.md",
                "sha256": sha256_file(self.report),
                "as_of": "2026-08-14",
            },
            "runtime": {
                "host": "codex",
                "model": "test-model",
                "tokens_total": 100,
                "tool_calls": 2,
                "wall_seconds": 4,
            },
            "budget": {
                "search": {"used": 1, "limit": 3},
                "fetch": {"used": 1, "limit": 2},
            },
            "artifacts": {
                "prompt": {"path": "prompt.md", "sha256": sha256_file(self.prompt)},
                "host_receipt": {
                    "path": "host-receipt.json",
                    "sha256": sha256_file(self.host_receipt),
                },
            },
            "sources": [
                {
                    "source_id": "E1",
                    "locator": "https://example.com/filing",
                    "publisher": "Example Exchange",
                    "temporal_basis": "DATED_PUBLICATION",
                    "published_at": "2026-08-13",
                    "retrieved_at": "2026-08-14",
                    "coverage_through": "2026-08-14",
                    "date_evidence": {
                        "kind": "DOCUMENT_DATE",
                        "value": "2026-08-13",
                        "anchor": "official filing heading",
                    },
                    "lineage_key": "example-exchange:filing-1",
                    "kind": "PRIMARY",
                    "snapshot_path": "sources/E1.txt",
                    "snapshot_sha256": sha256_file(self.snapshot),
                }
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "boundary": "FACT",
                    "temporal_mode": "EVENT_BY_DATE",
                    "source_ids": ["E1"],
                }
            ],
        }

    def write_host_receipt(self) -> None:
        self.host_receipt.write_text(
            json.dumps(self.host_receipt_payload, ensure_ascii=False), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def validate(self, *, strict: bool = False) -> tuple[list[str], list[str]]:
        self.receipt_path.write_text(
            json.dumps(self.receipt, ensure_ascii=False), encoding="utf-8"
        )
        return validate_receipt(
            self.receipt,
            receipt_path=self.receipt_path,
            skill_path=self.skill,
            strict=strict,
        )

    def test_valid_strict_receipt(self) -> None:
        self.assertEqual(self.validate(strict=True), ([], []))

    def test_cli_reports_strict_success(self) -> None:
        self.validate(strict=True)
        output = StringIO()
        with redirect_stdout(output):
            status = main([str(self.receipt_path), "--skill", str(self.skill), "--strict"])
        self.assertEqual(status, 0)
        self.assertIn("AUDIT_RECEIPT_OK", output.getvalue())

    def test_budget_overrun_fails(self) -> None:
        self.receipt["budget"]["search"] = {"used": 4, "limit": 3}
        errors, _ = self.validate()
        self.assertIn("budget.exceeded:search", errors)

    def test_post_cutoff_source_fails(self) -> None:
        self.receipt["sources"][0]["published_at"] = "2026-08-15"
        errors, _ = self.validate()
        self.assertIn("source.after_as_of:E1", errors)

    def test_exact_skill_hash_is_required(self) -> None:
        self.receipt["method"]["canonical_skill_sha256"] = "0" * 64
        errors, _ = self.validate()
        self.assertIn("method.canonical_skill_sha256_mismatch", errors)

    def test_active_skill_locator_and_hash_are_required(self) -> None:
        self.receipt["method"]["active"]["locator"] = "file:///wrong/SKILL.md"
        self.receipt["method"]["active"]["skill_sha256"] = "0" * 64
        errors, _ = self.validate()
        self.assertIn("method.active_locator_mismatch", errors)
        self.assertIn("method.active_skill_sha256_mismatch", errors)
        self.assertIn("method.active_skill_not_canonical", errors)

    def test_profile_hash_is_bound(self) -> None:
        self.receipt["method"]["profile"]["sha256"] = "0" * 64
        errors, _ = self.validate()
        self.assertIn("method.profile_sha256_mismatch", errors)
        self.assertIn("method.active_profile_not_canonical", errors)

    def test_fact_reposts_do_not_become_independent(self) -> None:
        source = self.receipt["sources"][0]
        source.update({"kind": "SECONDARY", "lineage_key": "wire:story-1"})
        second = {
            **source,
            "source_id": "E2",
            "locator": "https://mirror.example.com/story",
            "snapshot_path": "sources/E1.txt",
        }
        self.receipt["sources"].append(second)
        self.receipt["claims"][0]["source_ids"] = ["E1", "E2"]
        self.report.write_text(
            "# 报告\n\n截止日：2026-08-14\n\n[C1] 决定性事实。[E1][E2]\n",
            encoding="utf-8",
        )
        self.receipt["report"]["sha256"] = sha256_file(self.report)
        errors, _ = self.validate()
        self.assertIn("claim.fact_independence_insufficient:C1", errors)

    def test_no_result_requires_bounded_scope_and_index(self) -> None:
        self.receipt["claims"][0]["boundary"] = "NO_RESULT"
        self.receipt["sources"][0]["kind"] = "SECONDARY"
        errors, _ = self.validate()
        self.assertIn("claim.no_result_scope_missing:C1", errors)
        self.assertIn("claim.no_result_index_missing:C1", errors)

    def test_bounded_no_result_with_index_passes(self) -> None:
        self.receipt["sources"][0]["kind"] = "INDEX"
        self.receipt["claims"][0] = {
            "claim_id": "C1",
            "boundary": "NO_RESULT",
            "temporal_mode": "ABSENCE_BY_AS_OF",
            "source_ids": ["E1"],
            "no_result": {
                "queries": ["company pledge announcements"],
                "locations": ["official disclosure index"],
                "date_from": "2026-04-01",
                "date_to": "2026-08-14",
            },
        }
        self.assertEqual(self.validate(strict=True), ([], []))

    def test_o01_live_current_replay_fails_temporal_gate(self) -> None:
        source = self.receipt["sources"][0]
        source.update(
            {
                "temporal_basis": "LIVE_CURRENT",
                "published_at": None,
                "retrieved_at": "2026-08-17",
                "coverage_through": None,
            }
        )
        self.receipt["claims"][0]["temporal_mode"] = "STATE_AT_AS_OF"
        errors, _ = self.validate()
        self.assertIn("source.live_current_after_as_of:E1", errors)
        self.assertIn("claim.temporal_source_ineligible:C1:E1", errors)
        self.assertIn("claim.temporal_coverage_missing:C1:E1", errors)

    def test_o02_dated_notice_replay_passes(self) -> None:
        self.receipt["claims"][0]["temporal_mode"] = "STATE_AT_AS_OF"
        self.assertEqual(self.validate(strict=True), ([], []))

    def test_state_source_must_cover_as_of(self) -> None:
        self.receipt["claims"][0]["temporal_mode"] = "STATE_AT_AS_OF"
        self.receipt["sources"][0]["coverage_through"] = "2026-08-13"
        errors, _ = self.validate()
        self.assertIn("claim.temporal_coverage_before_as_of:C1:E1", errors)

    def test_absence_cannot_use_current_index(self) -> None:
        self.receipt["sources"][0].update(
            {
                "kind": "INDEX",
                "temporal_basis": "LIVE_CURRENT",
                "published_at": None,
            }
        )
        self.receipt["claims"][0]["temporal_mode"] = "ABSENCE_BY_AS_OF"
        errors, _ = self.validate()
        self.assertIn("claim.temporal_source_ineligible:C1:E1", errors)

    def test_insufficient_without_temporally_qualified_source_passes(self) -> None:
        self.receipt["sources"] = []
        self.receipt["claims"][0] = {
            "claim_id": "C1",
            "boundary": "INSUFFICIENT",
            "temporal_mode": "STATE_AT_AS_OF",
            "source_ids": [],
            "gap": "No dated source covering the report as-of was found.",
        }
        self.report.write_text(
            "# 报告\n\n截止日：2026-08-14\n\n[C1] 状态证据不足。\n",
            encoding="utf-8",
        )
        self.receipt["report"]["sha256"] = sha256_file(self.report)
        self.assertEqual(self.validate(strict=True), ([], []))

    def test_temporal_basis_and_mode_are_required(self) -> None:
        self.receipt["sources"][0].pop("temporal_basis")
        self.receipt["claims"][0].pop("temporal_mode")
        errors, _ = self.validate()
        self.assertIn("source.temporal_basis_missing:E1", errors)
        self.assertIn("claim.temporal_mode_invalid:C1", errors)

    def test_repository_formal_audit_identity_runs_positive_and_o01_negative(self) -> None:
        repo_skill = REPO_ROOT / "SKILL.md"
        formal_profile = profile_identity(REPO_ROOT, "formal-audit")
        self.receipt["method"] = {
            "canonical_skill_sha256": sha256_file(repo_skill),
            "profile": {
                "name": "formal-audit",
                "sha256": formal_profile["sha256"],
            },
            "active": {
                "locator": file_locator(repo_skill),
                "skill_sha256": sha256_file(repo_skill),
                "profile_sha256": formal_profile["sha256"],
            },
        }
        self.receipt["claims"][0]["temporal_mode"] = "STATE_AT_AS_OF"
        self.receipt_path.write_text(
            json.dumps(self.receipt, ensure_ascii=False), encoding="utf-8"
        )
        self.assertEqual(
            validate_receipt(
                self.receipt,
                receipt_path=self.receipt_path,
                skill_path=repo_skill,
                active_skill_path=repo_skill,
                strict=True,
            ),
            ([], []),
        )

        self.receipt["sources"][0].update(
            {
                "temporal_basis": "LIVE_CURRENT",
                "published_at": None,
                "retrieved_at": "2026-08-17",
                "coverage_through": None,
            }
        )
        errors, _ = validate_receipt(
            self.receipt,
            receipt_path=self.receipt_path,
            skill_path=repo_skill,
            active_skill_path=repo_skill,
            strict=True,
        )
        self.assertIn("source.live_current_after_as_of:E1", errors)
        self.assertIn("claim.temporal_source_ineligible:C1:E1", errors)
        self.assertIn("claim.temporal_coverage_missing:C1:E1", errors)

    def test_report_hash_and_markers_are_bound(self) -> None:
        self.receipt["report"]["sha256"] = "0" * 64
        self.report.write_text("截止日：2026-08-14\n", encoding="utf-8")
        errors, _ = self.validate()
        self.assertIn("report.sha256_mismatch", errors)
        self.assertIn("claim.marker_missing:C1", errors)
        self.assertIn("source.marker_missing:E1", errors)

    def test_receipt_cannot_escape_its_directory(self) -> None:
        self.receipt["report"]["path"] = "../report.md"
        errors, _ = self.validate()
        self.assertIn("report.path_invalid", errors)

    def test_strict_mode_derives_usage_from_host_receipt_and_requires_snapshots(self) -> None:
        self.receipt["runtime"].pop("tokens_total")
        self.receipt["runtime"].pop("tool_calls")
        self.receipt["runtime"].pop("wall_seconds")
        self.receipt["sources"][0].pop("snapshot_path")
        self.receipt["sources"][0].pop("snapshot_sha256")
        errors, _ = self.validate(strict=True)
        self.assertIn("source.snapshot_required:E1", errors)

    def test_model_reported_usage_without_host_receipt_fails(self) -> None:
        self.receipt["artifacts"].pop("host_receipt")
        errors, _ = self.validate()
        self.assertIn("runtime.metrics_without_host_receipt", errors)
        self.assertIn("budget.usage_without_host_receipt", errors)

    def test_non_strict_receipt_may_omit_unavailable_host_usage(self) -> None:
        self.receipt["artifacts"].pop("host_receipt")
        for field in ("tokens_total", "tool_calls", "wall_seconds"):
            self.receipt["runtime"].pop(field)
        for item in self.receipt["budget"].values():
            item.pop("used")
        errors, warnings = self.validate()
        self.assertEqual(errors, [])
        self.assertEqual(warnings, ["runtime.host_receipt_missing"])

    def test_host_runtime_mismatch_fails(self) -> None:
        self.receipt["runtime"]["tool_calls"] = 25
        errors, _ = self.validate(strict=True)
        self.assertIn("runtime.tool_calls_host_mismatch", errors)

    def test_host_budget_usage_overrides_model_claim(self) -> None:
        self.receipt["budget"]["search"] = {"used": 0, "limit": 3}
        errors, _ = self.validate(strict=True)
        self.assertIn("budget.used_host_mismatch:search", errors)

    def test_host_receipt_binds_raw_session(self) -> None:
        self.raw_session.write_text("tampered\n", encoding="utf-8")
        errors, _ = self.validate(strict=True)
        self.assertIn("host_receipt.raw_session_sha256_mismatch", errors)


if __name__ == "__main__":
    unittest.main()
