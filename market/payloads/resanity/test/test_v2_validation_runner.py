from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "validation/v2/run_validation.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("resanity_v2_validation", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load v2 validation runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class V2ValidationRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_runner()

    def test_mechanical_run_never_claims_semantic_or_ab_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            receipt_path = Path(raw) / "receipt.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER_PATH),
                    "--active-skill",
                    str(ROOT / "SKILL.md"),
                    "--skip-skill-validator",
                    "--skip-npm-test",
                    "--skip-pack",
                    "--output",
                    str(receipt_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "MECHANICAL_PRECHECK_INCOMPLETE")
            self.assertEqual(receipt["method_status"], "UNBENCHMARKED_CURRENT")
            self.assertEqual(receipt["semantic_layers"], "NOT_RUN")
            self.assertEqual(receipt["final_ab"], "NOT_RUN")
            self.assertEqual(receipt["details"]["install_identity"]["status"], "PASS")
            self.assertFalse(receipt["failed_steps"])

    def test_missing_active_locator_is_explicit(self) -> None:
        steps, receipt = self.runner.identity_steps(host="generic", active_skill=None)
        self.assertTrue(all(step["status"] == "PASS" for step in steps))
        self.assertEqual(receipt["status"], "NOT_CHECKED")
        self.assertEqual(receipt["mode"], "canonical-source-only")

    def test_request_and_output_paths_cannot_collide(self) -> None:
        with self.assertRaises(SystemExit):
            self.runner.parse_args(
                [
                    "--tushare-request",
                    "/tmp/request.json",
                    "--tushare-output",
                    "/tmp/request.json",
                ]
            )

    def test_tushare_packet_validator_checks_cutoff_hashes_and_lineage(self) -> None:
        request = {
            "provider": "TUSHARE",
            "as_of_date": "2026-07-31",
            "lookback_calendar_days": 180,
            "candidate": {
                "name": "Candidate",
                "ticker": "000001",
                "exchange": "XSHE",
                "asset_type": "EQUITY",
            },
            "benchmark": {
                "name": "Benchmark",
                "ticker": "000300",
                "exchange": "XSHG",
                "asset_type": "INDEX",
            },
        }
        market = self.runner.load_market_module()
        normalized = market._request(request)
        provider_policy = normalized["provider_policy"]
        candidate = [{"date": "2026-07-30", "close": 10.0}, {"date": "2026-07-31", "close": 10.2}]
        benchmark = [{"date": "2026-07-30", "close": 100.0}, {"date": "2026-07-31", "close": 101.0}]
        series_hashes = {
            "candidate": self.runner.canonical_hash(candidate),
            "benchmark": self.runner.canonical_hash(benchmark),
        }
        receipt_core = {
            "schema_version": "resanity.free-market-acquisition-receipt.v1",
            "request_sha256": self.runner.canonical_hash(normalized),
            "provider": "TUSHARE",
            "provider_policy": provider_policy,
            "provider_version": "test",
            "research_as_of_date": "2026-07-31",
            "market_session_date": "2026-07-31",
            "adjustment": "QFQ_AS_OF_CUTOFF",
            "series_sha256": series_hashes,
            "provider_endpoints": ["daily", "index_daily"],
        }
        packet = {
            "schema_version": "resanity.free-market-observations.v1",
            "status": "OBSERVATIONS_READY",
            "as_of_date": "2026-07-31",
            "provider": "TUSHARE",
            "provider_policy": provider_policy,
            "adjustment": "QFQ_AS_OF_CUTOFF",
            "candidate": {"observations": candidate},
            "benchmark": {"observations": benchmark},
            "acquisition_receipt": {
                **receipt_core,
                "receipt_id": self.runner.canonical_hash(receipt_core),
                "attempted_providers": ["TUSHARE"],
                "fallback_attempted": False,
                "warnings": [],
            },
        }
        summary = self.runner.validate_tushare_packet(request, packet)
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["series"]["candidate"]["sessions"], 2)

        packet["candidate"]["observations"][1]["date"] = "2026-08-01"
        with self.assertRaises(self.runner.ValidationError):
            self.runner.validate_tushare_packet(request, packet)


if __name__ == "__main__":
    unittest.main()
