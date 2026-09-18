from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "validation/v2/run_final_ab.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("resanity_final_ab", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load final A/B runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FinalAbRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_runner()

    def test_plan_is_exactly_eight_paired_cases(self) -> None:
        plan = self.runner.final_ab_plan(self.runner.load_suite())
        self.assertEqual(len(plan), 8)
        self.assertEqual(len({row["id"] for row in plan}), 8)
        self.assertEqual(sum(2 for _ in plan), 16)
        self.assertEqual({row["profile"] for row in plan}, {"core", "investing"})

    def test_dry_run_never_launches_sessions_or_claims_a_result(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_PATH),
                "--model",
                "test-model",
                "--codex-bin",
                "/bin/echo",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["status"], "DRY_RUN_BLOCKED")
        self.assertEqual(receipt["method_status"], "UNBENCHMARKED_CURRENT")
        self.assertEqual(receipt["semantic_scoring"], "NOT_RUN")
        self.assertEqual(receipt["session_count"], 16)

    def test_prelayer_receipt_must_match_frozen_hash_and_all_layers(self) -> None:
        skill_sha = self.runner.sha256_file(ROOT / "SKILL.md")
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "prelayers.json"
            evidence = []
            for name in self.runner.REQUIRED_PRELAYERS:
                evidence_path = Path(raw) / f"{name}.json"
                evidence_path.write_text(f"{name}\n", encoding="utf-8")
                evidence.append(
                    {
                        "layer": name,
                        "path": str(evidence_path),
                        "sha256": self.runner.sha256_file(evidence_path),
                    }
                )
            receipt = {
                "schema_version": self.runner.PRELAYERS_SCHEMA_VERSION,
                "status": "PRELAYERS_PASS",
                "candidate_skill_sha256": skill_sha,
                "candidate_profiles_sha256": self.runner.profile_hashes(ROOT),
                "layers": {name: "PASS" for name in self.runner.REQUIRED_PRELAYERS},
                "evidence": evidence,
            }
            path.write_text(json.dumps(receipt), encoding="utf-8")
            self.assertEqual(
                self.runner.validate_prelayers(
                    path, skill_sha, self.runner.profile_hashes(ROOT), required=True
                ),
                receipt,
            )
            receipt["layers"]["install_identity"] = "FAIL"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaises(self.runner.FinalAbError):
                self.runner.validate_prelayers(
                    path, skill_sha, self.runner.profile_hashes(ROOT), required=True
                )

    def test_prelayer_receipt_rejects_profile_hash_drift(self) -> None:
        self.assertNotEqual(
            self.runner.profile_hashes(ROOT)["core"],
            self.runner.profile_hashes(ROOT)["investing"],
        )

    def test_known_prelayer_failures_require_explicit_acceptance(self) -> None:
        skill_sha = self.runner.sha256_file(ROOT / "SKILL.md")
        profiles = self.runner.profile_hashes(ROOT)
        with tempfile.TemporaryDirectory() as raw:
            evidence = []
            for name in self.runner.REQUIRED_PRELAYERS:
                evidence_path = Path(raw) / f"{name}.json"
                evidence_path.write_text(name, encoding="utf-8")
                evidence.append(
                    {
                        "layer": name,
                        "path": str(evidence_path),
                        "sha256": self.runner.sha256_file(evidence_path),
                    }
                )
            receipt = {
                "schema_version": self.runner.PRELAYERS_SCHEMA_VERSION,
                "status": "PRELAYERS_ACCEPTED_WITH_KNOWN_FAILURES",
                "candidate_skill_sha256": skill_sha,
                "candidate_profiles_sha256": profiles,
                "layers": {
                    name: ("KNOWN_FAILURE" if name == "open_network" else "PASS")
                    for name in self.runner.REQUIRED_PRELAYERS
                },
                "known_failures": ["one preserved failure"],
                "evidence": evidence,
            }
            path = Path(raw) / "accepted.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaises(self.runner.FinalAbError):
                self.runner.validate_prelayers(
                    path, skill_sha, profiles, required=True
                )
            self.assertEqual(
                self.runner.validate_prelayers(
                    path,
                    skill_sha,
                    profiles,
                    required=True,
                    allow_known_failures=True,
                ),
                receipt,
            )

    def test_metrics_are_host_derived_and_count_no_agent_message_as_tool(self) -> None:
        raw = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message"}}),
                json.dumps({"type": "item.completed", "item": {"type": "web_search"}}),
                json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 40,
                            "output_tokens": 20,
                            "reasoning_output_tokens": 5,
                        },
                    }
                ),
            ]
        )
        metrics = self.runner.parse_raw_metrics(raw)
        self.assertEqual(metrics["session_id"], "thread-1")
        self.assertEqual(metrics["non_cached_input_tokens"], 60)
        self.assertEqual(metrics["tool_calls"], 2)
        self.assertEqual(metrics["web_search"], 1)
        self.assertEqual(metrics["tokens_total"], 120)

    def test_blind_ids_are_stable_and_arm_specific(self) -> None:
        left = self.runner.blind_id("seed", "C01-product-claim", "baseline")
        right = self.runner.blind_id("seed", "C01-product-claim", "candidate")
        self.assertNotEqual(left, right)
        self.assertEqual(
            left, self.runner.blind_id("seed", "C01-product-claim", "baseline")
        )


if __name__ == "__main__":
    unittest.main()
