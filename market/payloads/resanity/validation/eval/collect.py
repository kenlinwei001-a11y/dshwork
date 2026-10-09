#!/usr/bin/env python3
"""Aggregate the single-arm eval runs into one summary table.

Scans `validation/eval/runs/<case-id>/` for delivery.json / scores.json /
review.json, and prints per-case and overall lines. It aggregates records
only — no scoring semantics are invented here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "resanity.eval-collect.v1"

DELIVERY_KEYS = ("D1", "D2", "D3", "D4", "D5", "D6", "D7")


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def empty_summary() -> dict[str, Any]:
    return {
        "cases": 0,
        "scored": 0,
        "delivery_ready": 0,
        "mean_scores": {key: None for key in DELIVERY_KEYS},
        "refuted_total": 0,
        "claims_total": 0,
    }


def collect(runs_dir: Path) -> dict[str, Any]:
    rows = []
    if not runs_dir.is_dir():
        return {"schema_version": SCHEMA_VERSION, "rows": [], "summary": empty_summary()}
    for case_dir in sorted(runs_dir.iterdir()):
        if not case_dir.is_dir():
            continue
        delivery = load_json(case_dir / "delivery.json") or {}
        scores = load_json(case_dir / "scores.json") or {}
        review = load_json(case_dir / "review.json") or {}
        row = {
            "case_id": case_dir.name,
            "report_check": delivery.get("report_check", "NOT_RUN"),
            "audit": delivery.get("audit_receipt", "NOT_RUN"),
            "scores": {key: scores.get("delivery", {}).get(key) for key in DELIVERY_KEYS},
            "overturn": review.get("overturn_rate") or {},
            "next_verification_executed": review.get("next_verification_executed", "NOT_REVIEWED"),
        }
        rows.append(row)

    score_totals = {key: [] for key in DELIVERY_KEYS}
    for row in rows:
        for key in DELIVERY_KEYS:
            value = row["scores"].get(key)
            if isinstance(value, (int, float)):
                score_totals[key].append(value)
    summary = {
        "cases": len(rows),
        "scored": len(score_totals["D1"]),
        "delivery_ready": sum(1 for row in rows if row["report_check"] == "DELIVERY_READY"),
        "mean_scores": {
            key: round(sum(values) / len(values), 2) if values else None
            for key, values in score_totals.items()
        },
        "refuted_total": sum(
            int(row["overturn"].get("refuted", 0)) for row in rows if isinstance(row["overturn"], dict)
        ),
        "claims_total": sum(
            int(row["overturn"].get("total", 0)) for row in rows if isinstance(row["overturn"], dict)
        ),
    }
    return {"schema_version": SCHEMA_VERSION, "rows": rows, "summary": summary}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate single-arm eval runs.")
    parser.add_argument("--runs", type=Path, default=Path(__file__).parent / "runs", help="runs directory")
    parser.add_argument("--json", action="store_true", help="emit one machine-readable JSON object")
    args = parser.parse_args(argv)

    result = collect(args.runs)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"eval collect（schema {SCHEMA_VERSION}）：{result['summary']['cases']} 个 case")
    for row in result["rows"]:
        scores = " ".join(f"{key}={row['scores'][key]}" for key in DELIVERY_KEYS if row["scores"][key] is not None)
        print(f"  {row['case_id']}: report={row['report_check']} audit={row['audit']} [{scores}] next={row['next_verification_executed']}")
    summary = result["summary"]
    print("汇总：")
    print(f"  DELIVERY_READY: {summary['delivery_ready']}/{summary['cases']}")
    print(f"  平均分: {summary['mean_scores']}")
    print(f"  推翻率: {summary['refuted_total']}/{summary['claims_total']}（复盘轮已覆盖的主张）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
