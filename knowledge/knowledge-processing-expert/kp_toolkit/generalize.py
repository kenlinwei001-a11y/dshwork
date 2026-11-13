#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「上财实例提示词」泛化为**项目无关**的写作提示词。

目标（用户口径）：只复用写作逻辑、写作风格、覆盖内容，**不带任何上财身份与取值**。
  - 写作逻辑：核心问题 / prepare / must_state / must_not / 形态 / 评审盯什么
  - 覆盖内容：本节该覆盖哪些"量"（保留语义名，如 总建筑面积），不保留值
  - 写作风格：骨架 few-shot（残留字面值一并清洗成 {{值}}）

做法（确定性）：
  generalize_prompt()  值行 → 「量 + 约束 + 证据等级」槽位；标题/路径 → 占位；节点 ID 不进输出
  scrub_skeleton()     骨架里的字面数值 → {{值}}；上财专名 → {{主体}}；保留标准号/条款号
  scan_clean()         复核：专名 / 节点 ID / 带单位数值 必须为 0（标准号除外）
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

NODE_ID_RE = re.compile(r"N-[0-9a-f]{12}")
VALUE_LINE_RE = re.compile(r"^\s*·\s")
UNIT_AFTER_NUM = re.compile(r"(?<![A-Za-z0-9])(\d[\d,\.]*)\s*(万元|㎡|平方米|人|米|%|m³|吨|L/s|kW|元|个|间|层|m|KN/m2|kN/m2|KN/m²|kg/m2|kg/m³)")
STD_CODE = re.compile(r"(GB\s?/?T?\s?\d{3,5}(?:[-—.]\d{2,4})?|JGJ\s?\d{2,4}(?:[-—]\d{2,4})?|建标\s?\d{3}(?:[-—]\d{4})?|第\s?\d+(?:\.\d+)*\s?条|表\s?\d+(?:[-.]\d+)*)")


def scrub_skeleton(text: str, entities: List[str]) -> str:
    """骨架清洗：值 → {{值}}，专名 → {{主体}}；标准号/条款号原样保留。"""
    # 先把标准号整体保护起来
    keep: List[str] = []

    def _keep(m: "re.Match[str]") -> str:
        keep.append(m.group(0))
        return "\u0000K%d\u0000" % (len(keep) - 1)

    text = STD_CODE.sub(_keep, text)
    text = re.sub(r"\{\{node:N-[0-9a-f]{12}\}\}", "{{值}}", text)
    text = re.sub(r"\{\{node:[^}]+\}\}", "{{值}}", text)
    text = re.sub(r"\{\{ent:[^}]+\}\}", "{{主体}}", text)
    text = re.sub(r"\{\{time:[^}]+\}\}", "{{时间}}", text)
    for ent in sorted(entities, key=len, reverse=True):
        text = text.replace(ent, "{{主体}}")
    text = UNIT_AFTER_NUM.sub(lambda m: "{{值}} " + m.group(2), text)
    text = re.sub(r"(?<![A-Za-z%])\d{2,}(?:\.\d+)?(?![A-Za-z%])", "{{值}}", text)
    for i, k in enumerate(keep):
        text = text.replace("\u0000K%d\u0000" % i, k)
    return text


def generalize_prompt(prompt: str, corpus: Dict[str, Any], entities: List[str]) -> Dict[str, Any]:
    """把一节实例提示词转成项目无关版本。返回 {text, quantities}。"""
    by_id = corpus["by_id"]
    fills = corpus.setdefault("_fills", None)
    out: List[str] = []
    quantities: List[Dict[str, Any]] = []
    seen = set()
    emitted_style = False

    for raw in prompt.splitlines():
        line = raw

        m = re.match(r"依据脱敏骨架撰写《(.+?)》一节（(.+?)，层级 (\d)）。", line)
        if m:
            out.append("依据本节骨架撰写《{{本节标题}}》（{{章节路径}}，层级 {{层级}}）。")
            continue
        if line.startswith("本项目标签："):
            out.append(line)
            continue
        if re.match(r"本节原文约\s*\d+\s*字符", line):
            out.append("本节篇幅：按目标项目工作包预算给定（不在提示词内固化）。")
            continue
        if re.match(r"本节须覆盖\s*\d+\s*条事实节点", line):
            out.append("本节须覆盖 {{覆盖条数}} 个量，取值唯一来源是本节事实表：")
            continue

        m = NODE_ID_RE.search(line)
        if VALUE_LINE_RE.match(line) and m:
            nid = m.group(0)
            if nid in seen:
                continue
            seen.add(nid)
            n = by_id.get(nid) or {}
            pred = n.get("predicate") or ""
            if pred in ("", "=", "实体名", "规则计算结果"):
                pred = n.get("subject") or "{{量}}"
            cons = "硬" if (n.get("effect_level") in ("A（强制性）", "B（强）")) else "硬"
            ev = n.get("evidence_kind") or ""
            quantities.append({"name": pred, "evidence": ev, "kind": n.get("kind")})
            out.append("  · 须覆盖「%s」｜ 约束 {{硬/软}} ｜ 证据等级 %s ｜ 值取本节事实表" % (pred, ev or "{{E}}"))
            continue

        if re.match(r"^\s*·\s*另\s*\d+\s*条见本节事实表", line):
            continue
        if line.startswith("涉及技术函数："):
            out.append(line)
            continue
        if re.match(r"^\s*·\s*R-[^\s:：]+\s*[:：]", line):
            out.append(re.sub(r"\s*#.*$", "", line) + "   # 按本节事实表取值复算")
            continue
        if line.startswith("本章证据等级分布："):
            out.append("本章证据等级分布：见本节事实表（E1 必须注明提供方与日期；E2 必须带标准号+条款号）")
            continue
        if line.startswith("须显式呈现的待审冲突"):
            out.append(line)
            continue
        if VALUE_LINE_RE.match(line) and ("／" in line or "strong" in line or "确认后" in line):
            out.append("  · {{冲突主体}}·{{冲突谓词}}：{{值A}} ／ {{值B}}（待审；并列呈现，不裁决）")
            continue
        if re.match(r"^\s*·\s*\[[a-z_]+\]", line):
            out.append("  · [{{claim_type}}] {{论断}}（数值走节点槽位）")
            continue

        line = scrub_skeleton(line, entities)
        out.append(line)

    return {"text": "\n".join(out), "quantities": quantities}


def scan_clean(text: str, entities: List[str]) -> Dict[str, int]:
    """复核模板是否已无项目痕迹。"""
    ent = sum(text.count(e) for e in entities)
    ids = len(NODE_ID_RE.findall(text))
    nums = len(UNIT_AFTER_NUM.findall(text))
    return {"项目专名": ent, "节点ID": ids, "带单位数值": nums}
