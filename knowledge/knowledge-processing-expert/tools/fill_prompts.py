#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把用户的事实表注入写作提示词：量名匹配 → 填值 → 报缺。

输入：
  prompts.md      项目无关提示词包（每节含「须覆盖「量名」」行）
  facts.yaml      用户提供的事实表（量名 / 值 / 单位 / 约束 / 证据等级 / 来源 / 冲突组）
输出：
  filled.md       填充后的提示词（每行带值；缺值行标 ⚠️）
  report.json     覆盖率、缺值清单、未被任何节引用的量、冲突组

匹配规则（确定性）：
  只按**量名逐字相等**匹配。不做同义词、不做相似度、不猜——
  量名对不上就是缺值，交给编排确认量名，而不是让模型去猜。
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List

LINE_RE = re.compile(r"^(  · )须覆盖「([^」]+)」(.*)$")
SECTION_RE = re.compile(r"^### (\d+\.\d+|\d+)　(.+)$")


def load_facts(path: str) -> Dict[str, Dict[str, Any]]:
    import yaml
    raw = yaml.safe_load(open(path, encoding="utf-8"))
    items = raw.get("facts") if isinstance(raw, dict) else raw
    out: Dict[str, Dict[str, Any]] = {}
    for it in items or []:
        name = str(it.get("量名") or it.get("name") or "").strip()
        if not name:
            continue
        if name in out:
            out[name].setdefault("duplicates", 0)
            out[name]["duplicates"] += 1
        out[name] = {
            "value": it.get("值", it.get("value")),
            "unit": it.get("单位", it.get("unit", "")) or "",
            "constraint": it.get("约束", it.get("constraint", "")),
            "evidence": it.get("证据等级", it.get("evidence", "")),
            "source": it.get("来源", it.get("source", "")),
            "conflict": it.get("冲突组", it.get("conflict", "")),
            "duplicates": out.get(name, {}).get("duplicates", 0),
        }
    return out


def render(prompts_md: str, facts: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    lines = prompts_md.splitlines()
    out: List[str] = []
    used: set = set()
    sec = ""
    sections: List[Dict[str, Any]] = []
    cur = {"section": "", "covered": 0, "missing": []}

    for line in lines:
        m = SECTION_RE.match(line)
        if m and ("　" in line):
            if cur["section"]:
                sections.append(cur)
            cur = {"section": m.group(1), "title": m.group(2), "covered": 0, "missing": []}
            out.append(line)
            continue
        mm = LINE_RE.match(line)
        if mm:
            name = mm.group(2).strip()
            f = facts.get(name)
            if f and f["value"] not in (None, ""):
                used.add(name)
                cur["covered"] += 1
                val = "%s%s" % (f["value"], (" " + f["unit"]) if f["unit"] else "")
                tag = "｜值 **%s**" % val
                meta = "｜约束 %s｜证据 %s" % (f["constraint"] or "—", f["evidence"] or "—")
                if f["source"]:
                    meta += "｜来源 %s" % f["source"]
                if f["conflict"]:
                    meta += "｜冲突组 %s（并列待审）" % f["conflict"]
                out.append("  · 须覆盖「%s」%s%s ｜值已注入" % (name, tag, meta))
            else:
                cur["missing"].append(name)
                out.append("  · 须覆盖「%s」⚠️ 缺值：事实表未提供同名量 → 正文留白并报 unresolved" % name)
            continue
        out.append(line)
    if cur["section"]:
        sections.append(cur)

    all_names = {m for m in re.findall(r"须覆盖「([^」]+)」", prompts_md)
                 if "{{" not in m and len(m) >= 2 and m not in ("X", "为")}
    missing_names = sorted(all_names - used)
    extra_in_facts = sorted(set(facts) - all_names)
    total = len(all_names)
    return {
        "text": "\n".join(out),
        "stats": {
            "量名总数": total,
            "已注入": len(used),
            "缺值": len(missing_names),
            "覆盖率": "%.1f%%" % (len(used) / total * 100 if total else 0),
            "事实表里但没有任何节引用": extra_in_facts[:20],
            "缺值量名(前 20)": missing_names[:20],
            "冲突组": sorted({f["conflict"] for f in facts.values() if f.get("conflict")}),
        },
        "sections": sections,
    }


def main(argv: List[str]) -> int:
    if len(argv) != 4:
        sys.stderr.write("用法: fill_prompts.py <prompts.md> <facts.yaml> <out.md>\n")
        return 2
    prompts_path, facts_path, out_path = argv[1], argv[2], argv[3]
    prompts_md = open(prompts_path, encoding="utf-8").read()
    facts = load_facts(facts_path)
    res = render(prompts_md, facts)
    open(out_path, "w", encoding="utf-8").write(res["text"])
    side = os.path.splitext(out_path)[0] + ".report.json"
    open(side, "w", encoding="utf-8").write(json.dumps(
        {"stats": res["stats"], "sections": res["sections"]}, ensure_ascii=False, indent=1))
    print(json.dumps(res["stats"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
