#!/usr/bin/env python3
"""Mechanical delivery gate for a saved Resanity report.

Checks the invariants of the 交付编译 step without interpreting any
conclusion:

- the report carries a root conclusion and at least one atomic claim card;
- every card names a tense and an evidence boundary, and the boundary line
  carries exactly one label;
- a single next-verification section exists (singularity is a heuristic
  warning);
- reality negations co-occurring with INSUFFICIENT boundaries surface as
  warnings, since only a named qualified source may negate.

Two card layouts are recognized: the plain protocol layout
(``主张：`` / ``时态：`` lines) and the report layout where the claim is a
``### [C#]`` heading and fields are bold ``**时态：**`` lines.

`DELIVERY_READY` means the mechanical contract is closed, not that the
conclusion is correct; `DELIVERY_INCOMPLETE` is never a verdict on the report
having been produced.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "resanity.report-check.v1"

TENSES = frozenset({"EVENT_BY_DATE", "STATE_AT_AS_OF", "ABSENCE_BY_AS_OF", "TIMELESS"})
BOUNDARIES = frozenset({"FACT", "SINGLE_SOURCE", "INFERENCE", "HYPOTHESIS", "NO_RESULT", "INSUFFICIENT"})
BOUNDARY_PATTERN = re.compile(r"|".join(sorted(BOUNDARIES, key=len, reverse=True)))
NEGATION_PATTERN = re.compile(r"不成立|不存在|未形成|没有项目|尚无收入|无收入|未通过|未落地|闭环未闭")
DATE_PATTERN = re.compile(r"20\d{2}[-/年]\d{1,2}")

CARD_START = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?主张(?:\*\*)?[：:]")
CARD_HEADING = re.compile(r"^#{2,4}\s*\[C\d+\]\s*(.+?)\s*$")

FIELD_PATTERNS = {
    "时态": re.compile(r"(?:\*\*)?时态(?:\*\*)?[：:](?:\*\*)?\s*`?([^`\n]+?)`?\s*$", re.MULTILINE),
    "观察到什么": re.compile(r"(?:\*\*)?观察到什么(?:\*\*)?[：:](?:\*\*)?"),
    "可以推出什么": re.compile(r"(?:\*\*)?可以推出什么(?:\*\*)?[：:](?:\*\*)?"),
    "不能推出什么": re.compile(r"(?:\*\*)?不能推出什么(?:\*\*)?[：:](?:\*\*)?"),
    "对决策的影响": re.compile(r"(?:\*\*)?对决策的影响(?:\*\*)?[：:](?:\*\*)?"),
    "证据边界": re.compile(r"(?:\*\*)?证据边界(?:\*\*)?[：:](?:\*\*)?\s*([^\n]+)"),
}


def split_cards(lines: list[str]) -> list[str]:
    """Split a report into claim cards; each card starts at a 主张 line or a [C#] heading."""
    cards = []
    current: list[str] = []
    for line in lines:
        if CARD_START.match(line) or CARD_HEADING.match(line):
            if current:
                cards.append("\n".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        cards.append("\n".join(current))
    return cards


def next_verification(lines: list[str]) -> tuple[list[str], str]:
    """Return the next-verification heading lines and their body text."""
    for index, line in enumerate(lines):
        if re.match(r"^#{1,4}\s*[^#]*唯一下一验证", line):
            body = []
            for rest in lines[index + 1 :]:
                if re.match(r"^#{1,4}\s", rest):
                    break
                body.append(rest)
            return [line], "\n".join(body)
    fallback = [line for line in lines if "下一验证" in line and not line.strip().startswith("|")]
    return fallback, ""


def parse_report(text: str) -> dict[str, Any]:
    """Split one saved report into cards and the surrounding scaffold."""
    lines = text.splitlines()
    next_lines, next_body = next_verification(lines)
    return {
        "root": bool(re.search(r"根结论|#\s*根结论|##\s*根结论", text)),
        "as_of": bool(DATE_PATTERN.search(text)),
        "next": next_lines,
        "next_body": next_body,
        "cards": split_cards(lines),
        "text": text,
    }


def boundary_labels(value: str) -> list[str]:
    return BOUNDARY_PATTERN.findall(value)


def check_report(text: str) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []

    parsed = parse_report(text)
    if not parsed["root"]:
        failures.append("报告缺少根结论")
    if not parsed["as_of"]:
        warnings.append("报告未发现 as-of/日期标记（TIMELESS 情形可忽略）")
    if not parsed["next"]:
        failures.append("报告缺少唯一下一验证")
    elif len(parsed["next"]) > 1:
        warnings.append("存在多条下一验证行；交付编译要求收敛为一个外部证据获取单元")
    else:
        next_text = parsed["next_body"] or "\n".join(parsed["next"])
        if re.search(r"[、和与]|同时", next_text):
            warnings.append("唯一下一验证疑似包含多个证据对象，人工确认是否为单一获取单元")

    # ── 质量脚手架（告警级，不阻断交付）──────────────────────────────────────
    for label, pattern in (
        ("决策问题", re.compile(r"决策(?:问题)?\s*[：:]")),
        ("时间边界", re.compile(r"时间边界")),
        ("来源资格", re.compile(r"来源资格")),
    ):
        if not pattern.search(text):
            warnings.append(f"报告缺少页眉要素「{label}」")
    if "主张树" not in text:
        warnings.append("报告缺少主张树（根结论 ← 承重主张 ← 观察，逐边标证据边界）")
    if "决策菜单" not in text:
        warnings.append("报告缺少决策菜单（WATCH_ONLY / 等待验证 / 停止研究 / 条件升级，逐项标注所需证据）")
    if "建议锚草稿" not in text:
        warnings.append("报告缺少建议锚草稿（可证伪句 + active + 更新触发器日期，用户确认后入 anchors/）")
    if not re.search(r"若[^，。\n]{0,40}(?:则|→|->)", text):
        warnings.append("根结论建议写成条件式（若 X 被验证 → 升级为 Y；若 Z 未发生 → 降级为 W）")

    if not parsed["cards"]:
        failures.append("未发现原子主张卡（「主张：」或「### [C#]」格式）")
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "DELIVERY_INCOMPLETE",
            "failures": failures,
            "warnings": warnings,
        }

    has_insufficient = False
    for index, card in enumerate(parsed["cards"], start=1):
        label = f"主张卡 #{index}"
        for field in ("观察到什么", "可以推出什么", "不能推出什么", "对决策的影响"):
            if not FIELD_PATTERNS[field].search(card):
                failures.append(f"{label}缺少字段「{field}」")

        tense_match = FIELD_PATTERNS["时态"].search(card)
        if tense_match:
            tense = tense_match.group(1).strip().strip("`")
            if tense not in TENSES:
                failures.append(f"{label}时态「{tense}」不在 {sorted(TENSES)} 内")
        else:
            failures.append(f"{label}缺少时态")

        boundary_match = FIELD_PATTERNS["证据边界"].search(card)
        if boundary_match:
            boundary_line = boundary_match.group(1)
            labels = boundary_labels(boundary_line)
            if not labels:
                failures.append(f"{label}证据边界行没有可识别标签")
            elif len(labels) > 1:
                failures.append(f"{label}证据边界行出现多个标签：{labels}（整句主张只允许一个）")
            else:
                if labels[0] == "INSUFFICIENT":
                    has_insufficient = True
                if "FACT" in labels and len(boundary_line.strip("` ")) > len("FACT") + 8:
                    warnings.append(f"{label}证据边界为 FACT 但行内另有解释文字；FACT 只用于直接复述来源观察")
        else:
            failures.append(f"{label}缺少证据边界")
        if "最强反例" not in card:
            warnings.append(f"{label}缺少最强反例行（红队结论：最强反例 + 裁决理由）")

    if has_insufficient:
        for index, card in enumerate(parsed["cards"], start=1):
            first = card.splitlines()[0] if card.splitlines() else ""
            if first and NEGATION_PATTERN.search(first):
                warnings.append(f"主张卡 #{index} 出现现实否定且证据边界为 INSUFFICIENT；只有具名合格来源明确否定才可写")

    status = "DELIVERY_READY" if not failures else "DELIVERY_INCOMPLETE"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "card_count": len(parsed["cards"]),
        "failures": failures,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a saved Resanity report's delivery contract without judging its conclusion."
    )
    parser.add_argument("report", help="path to a saved report.md")
    parser.add_argument("--json", action="store_true", help="emit one machine-readable JSON object")
    args = parser.parse_args(argv)

    path = Path(args.report)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "DELIVERY_INCOMPLETE",
            "failures": [f"报告不可读：{exc.strerror or exc}"],
            "warnings": [],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    result = check_report(text)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"status: {result['status']}（schema {SCHEMA_VERSION}）")
        print(f"主张卡：{result.get('card_count', 0)} 张")
        for warning in result["warnings"]:
            print(f"  ⚠ {warning}")
        for failure in result["failures"]:
            print(f"  ✗ {failure}")
        if result["status"] == "DELIVERY_READY":
            print("DELIVERY_READY 只代表交付合同闭合，不代表结论正确。")
    return 0 if result["status"] == "DELIVERY_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
