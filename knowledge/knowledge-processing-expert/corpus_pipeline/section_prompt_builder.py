# -*- coding: utf-8 -*-
"""section_prompt_builder —— 从 graph 生成章节写作提示词（零 LLM）。

## 为什么要有

写作侧真正需要的不是「骨架」，是「这一节要写什么、依据什么、必须覆盖什么、
哪些数不能裁决」。原语料包的 section-prompts 含上财的具体值，不能复用。
本模块按 `templates/section-prompt-template.yaml` 的**结构**，把新项目 graph 的
**值**运行时注入。

## 用法

    from corpus_pipeline.section_prompt_builder import build_prompt, build_all

    p = build_prompt(graph, section="5.2", tags=["科研","可研","中型"])
    print(p["prompt"])     # 可直接喂给写作 agent
    p2 = build_all(graph, tags=[...])     # 全部节
"""
from __future__ import annotations
import re

TAG_DEFAULT = ["科研", "可研", "中型"]

# 从章节号猜标签（粗略；调用方可覆盖）
def _guess_tags(node):
    return TAG_DEFAULT


def _facts_of(graph, section):
    out = []
    for f in (graph.get("items", {}).get("facts") or []):
        if str(f.get("section") or "").lstrip("§") == str(section).lstrip("§"):
            out.append(f)
    return out


def _reasoning_of(graph, section):
    out = []
    for r in (graph.get("items", {}).get("reasoning") or []):
        if str(r.get("section") or "").lstrip("§") == str(section).lstrip("§"):
            out.append(r)
    return out


def _conflicts_of(graph, section):
    facts = {str(f.get("id")): f for f in (graph.get("items", {}).get("facts") or [])}
    sec_ids = {str(f.get("id")) for f in _facts_of(graph, section)}
    out = []
    for c in (graph.get("items", {}).get("conflicts") or []):
        inv = {str(x) for x in (c.get("involved") or [])}
        if inv & sec_ids or (not inv and str(c.get("id"))):
            out.append(c)
    return out


def _fmt_facts(facts, limit=40):
    lines = []
    for f in facts[:limit]:
        lab = str(f.get("subject") or "")
        val = f.get("value")
        unit = f.get("unit") or ""
        sec = str(f.get("section") or "")
        nid = str(f.get("id") or "")
        rule = f.get("rule")
        tail = " 算法 %s" % rule if rule else ""
        lines.append("  · %s = %s %s ｜ %s〔%s〕%s" % (lab, val, unit, sec, nid, tail))
    if len(facts) > limit:
        lines.append("  · 另 %d 条见本节事实表。" % (len(facts) - limit))
    return "\n".join(lines)


def _fmt_exprs(reasoning):
    lines = []
    for r in reasoning:
        rid = r.get("rule_id") or r.get("id")
        expr = r.get("formula") or ""
        if expr:
            lines.append("  · %s: %s" % (rid, expr))
    return "\n".join(lines)


def _fmt_conflicts(conflicts):
    lines = []
    for c in conflicts:
        desc = str(c.get("description") or "")
        sev = c.get("severity") or ""
        lines.append("  · %s（%s）" % (desc, sev))
    return "\n".join(lines)


def build_prompt(graph, *, section, title="", path="", level=2, tags=None) -> dict:
    """生成单节提示词。返回 {prompt, facts, rules, conflicts, contract, stats}。"""
    meta = graph.get("meta") or {}
    tags = tags or _guess_tags(None)
    facts = _facts_of(graph, section)
    reasoning = _reasoning_of(graph, section)
    conflicts = _conflicts_of(graph, section)
    rules = sorted({str(r.get("rule_id")) for r in reasoning if r.get("rule_id")})
    sec_title = title or ("§%s" % section)
    sec_path = path or str(meta.get("title") or "")

    parts = []
    # ① basis
    parts.append("依据脱敏骨架撰写《%s》一节（%s，层级 %d）。" % (sec_title, sec_path, level))
    # ② tags
    parts.append("本项目标签：%s（同类项目可直接复用本节结构，只替换数值）" % " · ".join(tags))
    # ③ length（按项数推导，不写历史字数）
    n_items = len(facts) or 4
    parts.append("本节篇幅按 must_cover 的 %d 项逐项展开，每项 150-300 字（合计约 %d-%d 字）。"
                 % (n_items, n_items * 150, n_items * 300))
    # ④ facts（条件）
    if facts:
        parts.append("本节须覆盖 %d 条事实节点，取值唯一来源是事实节点值表：\n%s"
                     % (len(facts), _fmt_facts(facts)))
    # ⑤ functions（条件）
    exprs = _fmt_exprs(reasoning)
    if exprs:
        parts.append("涉及技术函数：%s。**必须写出算式**，并按下列表达式复算：\n%s"
                     % ("、".join(rules), exprs))
    # ⑥ conflicts（条件）
    if conflicts:
        parts.append("须显式呈现的待审冲突（**不得裁决、不得两值并存**）：\n%s"
                     % _fmt_conflicts(conflicts))
    # ⑦ return
    parts.append("返回：正文 Markdown（数值写〔节点ID〕引用）＋ node_mentions ＋ new_claims ＋ unresolved。")

    return {
        "section": section, "title": sec_title, "tags": tags,
        "prompt": "\n".join(parts),
        "facts": facts, "rules": rules, "conflicts": conflicts,
        "contract": {"body": "Markdown，数值写〔N-xxx〕引用",
                     "node_mentions": [], "new_claims": [], "unresolved": []},
        "stats": {"facts": len(facts), "rules": len(rules), "conflicts": len(conflicts),
                  "chars": len("\n".join(parts))},
    }


def build_all(graph, *, tags=None) -> list:
    """按 graph 里出现的所有 section 批量生成。"""
    secs = sorted({str(f.get("section") or "").lstrip("§")
                   for f in (graph.get("items", {}).get("facts") or [])
                   if f.get("section")})
    return [build_prompt(graph, section=s, tags=tags) for s in secs]
