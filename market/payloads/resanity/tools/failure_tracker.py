#!/usr/bin/env python3
"""Aggregate anchor failure types and overdue reviews for method revision.

Scans anchor directories, counts `失效类型` labels on refuted anchors and
anchors whose trigger passed without a recorded review, and emits a compact
report. It aggregates only — it never edits anchors and never revises the
protocol; method revision stays with the model/human.

Failure-type convention (recorded by the model when a claim fails its
verification):

    ## <主题>
    - 状态：refuted
    - 失效类型：tense|boundary|observation|verification
    - 检验结果：<one-line reality vs claim>

`verification` means the "唯一下一验证" itself failed to adjudicate the fork.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from tools.anchor_check import SKIP_NAMES, anchor_status, next_trigger

SCHEMA_VERSION = "resanity.failure-tracker.v1"
FAILURE_TYPE_PATTERN = re.compile(r"失效类型\s*[：:]\s*([^\n]+)")
REVIEW_PATTERN = re.compile(r"检验结果\s*[：:]")
KNOWN_TYPES = frozenset({"tense", "boundary", "observation", "verification"})


def scan_dir(directory: Path, today: date) -> dict[str, Any]:
    refuted: list[tuple[str, str]] = []
    overdue: list[tuple[str, date]] = []
    for path in sorted(directory.glob("*.md")):
        if path.name in SKIP_NAMES or path.name.startswith("_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for block in re.split(r"^##\s", text, flags=re.MULTILINE)[1:]:
            status = anchor_status("## " + block)
            if status == "refuted":
                match = FAILURE_TYPE_PATTERN.search(block)
                refuted.append((path.name, (match.group(1).strip() if match else "unlabeled")))
        trigger = next_trigger(path, today)
        if trigger is not None:
            theme, when = trigger
            if when < today and not REVIEW_PATTERN.search(text):
                overdue.append((theme, when))
    return {"refuted": refuted, "overdue": overdue}


def aggregate(roots: list[str], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    refuted: list[tuple[str, str]] = []
    overdue: list[tuple[str, date]] = []
    scanned = 0
    for raw in roots:
        directory = Path(raw)
        if not directory.is_dir():
            continue
        scanned += 1
        result = scan_dir(directory, today)
        refuted.extend(result["refuted"])
        overdue.extend(result["overdue"])

    type_counts: Counter[str] = Counter()
    unlabeled = 0
    for _theme, kind in refuted:
        if kind in KNOWN_TYPES:
            type_counts[kind] += 1
        elif kind == "unlabeled":
            unlabeled += 1
        else:
            type_counts["other"] += 1

    warnings = []
    if overdue:
        warnings.append(
            f"{len(overdue)} 个 active 锚已过触发日但未记录检验结果："
            + "、".join(f"{theme}({when.isoformat()})" for theme, when in overdue[:5])
            + ("…" if len(overdue) > 5 else "")
        )
    if unlabeled:
        warnings.append(f"{unlabeled} 个 refuted 锚未标注失效类型，补上 失效类型 后才能进入统计")

    result = {
        "schema_version": SCHEMA_VERSION,
        "roots_scanned": scanned,
        "refuted_count": len(refuted),
        "failure_types": dict(sorted(type_counts.items())),
        "overdue_active": len(overdue),
        "themes_refuted": sorted({theme for theme, _kind in refuted}),
        "warnings": warnings,
        "note": "统计只聚合锚文件；协议修订由人/模型决定，本工具不自动改写方法。",
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate anchor failure types and overdue reviews without revising the protocol."
    )
    parser.add_argument("roots", nargs="*", help="anchor directories to scan")
    parser.add_argument("--json", action="store_true", help="emit one machine-readable JSON object")
    args = parser.parse_args(argv)

    result = aggregate(args.roots)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"status: OK（schema {SCHEMA_VERSION}）")
        print(f"扫描目录：{result['roots_scanned']}；refuted 锚：{result['refuted_count']}")
        if result["failure_types"]:
            for kind, count in result["failure_types"].items():
                print(f"  失效类型 {kind}: {count}")
        else:
            print("  无已标注失效类型")
        print(f"逾期未复核：{result['overdue_active']}")
        for warning in result["warnings"]:
            print(f"  ⚠ {warning}")
        print(result["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
