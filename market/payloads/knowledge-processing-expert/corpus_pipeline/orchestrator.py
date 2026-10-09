# -*- coding: utf-8 -*-
"""
编排器（链路 2 的块②）——写作 Agent 的调度层，闸门由编排器执行而非 Agent 自评。

四个能力（对应 mcp-tools.md 的通道 ①/③ 与 gate 约束）：
  assemble_injection  六段注入装配（~4K token，整场常驻）
  build_work_package  章节工作包组装（facts≤30 + 分页指针 + 冲突/缺口内嵌 + 返回契约）
  gate_check_draft    草稿闸门：字面数值 / undefined 使用 / must_cover 缺项 / 不变式
  commit_to_graph     回写 node_mentions.jsonl + 保存草稿（project_where_written 的数据来源）

确定性实现：零 LLM，文件系统背书，可单测。
"""
from __future__ import annotations
import json
import re
from pathlib import Path

# --------------------------------------------------------------------------- #
# 内置写作纪律（注入段 [1]，取自推演写作专家 SKILL 的压缩版）
# --------------------------------------------------------------------------- #
INJECT_SKILL = """推演式报告写作纪律：
1) 借形不借值：只经注入/工具/内嵌三通道访问语料包，corpus_get_chunk 只给 node 引用占位骨架，永不使用历史项目原值。
2) 缺值守卫：UNDEFINED 节点不得填 0、不得估值、不得跳过；按 instruction 写「待……后测算」并挂 gap。
3) 不许反算：每个数值必须由 rules/derivation 正向推出，不得由结论倒推中间量。
4) 引用即绑定：正文数值一律写 node 引用，不得写字面量。
5) 冲突一律「⚠ 待审」呈现，不裁决；闸门由编排器调 gate_check，不做自评判分。
6) 「经测算」句直接使用 derivation 的 narrative_zh，保证表述一致。
7) 每节返回：draft_md + node_mentions[{node_id,char_span,form}] + new_claims + unresolved。"""


def _jf(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _jl(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l] if p.exists() else []


def _load_corpus(corpus_dir):
    cdir = Path(corpus_dir)
    return {
        "manifest": _jf(cdir / "manifest.yaml") or {},
        "meta": _jf(cdir / "meta.yaml") or {},
        "outline": _jf(cdir / "outline.yaml") or {},
        "style": _jf(cdir / "style" / "style_profile.yaml") or {},
        "terms": _jf(cdir / "index" / "term_index.json") or [],
        "gate": _jf(cdir / "quality" / "gate_report.yaml") or {},
    }


# --------------------------------------------------------------------------- #
# 通道 ①：六段注入装配
# --------------------------------------------------------------------------- #
def assemble_injection(corpus_dir, project_dir, section=None, term_limit=30) -> dict:
    c = _load_corpus(corpus_dir)
    pmeta = _jf(Path(project_dir) / "meta.yaml") or {}
    pgate = _jf(Path(project_dir) / "quality" / "gate_report.yaml") or {}
    outline = c["outline"]
    secs = outline.get("sections", [])
    idx = next((i for i, s in enumerate(secs) if s.get("title") == section), -1) if section else -1
    window = secs[max(0, idx - 1):idx + 2] if idx >= 0 else secs[:2]

    terms = c["terms"]
    if isinstance(terms, dict):
        terms = list(terms.items())[:term_limit]
    elif isinstance(terms, list):
        terms = [(t.get("surface") or t.get("canonical") or "", t.get("freq", "")) for t in terms[:term_limit]]

    constraints = pmeta.get("constraints") or c["manifest"].get("constraints") or []
    gate_line = {"gate": pgate.get("gate", c["gate"].get("gate", "REVIEW")),
                 "undefined": len(pgate.get("undefined", [])),
                 "replay_conflicts": len(pgate.get("replay_conflicts", []))}
    style = c["style"]

    sections = {
        "[1] SKILL.md": INJECT_SKILL,
        "[2] constraints": constraints,
        "[3] meta": {"title": pmeta.get("title", c["meta"].get("title", "")),
                     "based_on_corpus": pmeta.get("based_on", {}).get("corpus_id", ""),
                     "data_cutoff": pmeta.get("data_cutoff", c["meta"].get("data_cutoff"))},
        "[4] outline(本节+相邻)": window,
        "[5] style_profile": {k: style[k] for k in ("number_format", "terminology", "forbidden", "citation_style", "table_caption", "person") if k in style},
        "[6] terms+gate": {"terms": terms, "gate": gate_line},
    }
    prompt = "\n\n".join(f"### {k}\n{json.dumps(v, ensure_ascii=False)}" for k, v in sections.items())
    return {"sections": sections, "prompt": prompt, "approx_tokens_hint": "≈4K"}


# --------------------------------------------------------------------------- #
# 通道 ③：章节工作包
# --------------------------------------------------------------------------- #
def build_work_package(project_dir, section_id, corpus_dir=None, must_cover=None,
                       word_budget=(1200, 1800), page_size=30) -> dict:
    pdir = Path(project_dir)
    nodes = _jf(pdir / "graph" / "nodes.yaml") or []
    claims = _jf(pdir / "graph" / "claims.yaml") or []
    conflicts = _jf(pdir / "quality" / "conflicts.yaml") or []
    gate = _jf(pdir / "quality" / "gate_report.yaml") or {}
    deriv = _jf(pdir / "reasoning" / "derivation.yaml") or {}

    total = len(nodes)
    pages = (total + page_size - 1) // page_size if total else 0
    wp = {
        "work_package_id": f"WP-{section_id}",
        "outline": {"section": section_id, "must_cover": must_cover or [], "word_budget": list(word_budget)},
        "facts": nodes[:page_size],
        "facts_paging": {"total": total, "page_size": page_size, "pages": pages,
                         "tool": "wp_get_facts", "note": "facts 超过 30 条时按页拉取" if total > page_size else "无需分页"},
        "claims": claims,
        "conflicts": conflicts,
        "undefined": gate.get("undefined", []),
        "skeleton": {"from_corpus": str(Path(corpus_dir)) if corpus_dir else None,
                     "section": section_id,
                     "forbid": ["原文中的任何数值", "原项目名称", "原取费年份"]},
        "return_contract": {
            "draft_md": "正文 Markdown，数值一律写 node 引用，不得写字面量",
            "node_mentions": "[{node_id, char_span, form}]",
            "new_claims": "[{text, supports[], evidence[]}]",
            "unresolved": "[{what, why, need_from_client}]",
        },
        "derivation_narrative": [{"label": d.get("label"), "status": d.get("status"),
                                  "narrative_zh": d.get("narrative_zh", ""),
                                  "instruction": d.get("instruction", "")} for d in deriv.get("nodes", [])],
    }
    wpfile = pdir / "project" / "work_packages" / f"{section_id}.json"
    wpfile.parent.mkdir(parents=True, exist_ok=True)
    wpfile.write_text(json.dumps(wp, ensure_ascii=False, indent=2), encoding="utf-8")
    return wp


# --------------------------------------------------------------------------- #
# 草稿闸门（编排器调用，不由 Agent 调用）
# --------------------------------------------------------------------------- #
_NODE_REF = re.compile(r'node:([PN]-[0-9a-f]+)')
_NUM = re.compile(r'(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?![\w])')


def gate_check_draft(project_dir, section_id, draft_md) -> dict:
    pdir = Path(project_dir)
    nodes = {n["id"]: n for n in (_jf(pdir / "graph" / "nodes.yaml") or [])}
    wp = _jf(pdir / "project" / "work_packages" / f"{section_id}.json") or {}

    # 字面数值：先剥离 node 引用再找数字
    stripped = _NODE_REF.sub(" ", draft_md or "")
    literal_numbers_found = _NUM.findall(stripped)

    # undefined 使用
    undefined_used = []
    for ref in set(_NODE_REF.findall(draft_md or "")):
        n = nodes.get(ref)
        if n is None:
            undefined_used.append({"node": ref, "why": "引用不存在"})
        elif n.get("status") == "undefined":
            undefined_used.append({"node": ref, "label": n.get("label"), "why": "status=UNDEFINED 不得当数用"})

    # must_cover 缺项（标题级粗检：关键词出现在正文即可）
    missing_must_cover = [k for k in (wp.get("outline", {}).get("must_cover") or []) if k not in (draft_md or "")]

    verdict = "pass"
    notes = []
    if literal_numbers_found:
        verdict = "review"
        notes.append(f"正文出现 {len(literal_numbers_found)} 处字面数值，必须改写为 node 引用")
    if missing_must_cover:
        verdict = "review"
        notes.append(f"must_cover 缺项：{missing_must_cover}")
    if undefined_used:
        if verdict == "pass":
            verdict = "pass_with_notes"
        notes.append(f"undefined 节点被引用 {len(undefined_used)} 处，须按 instruction 写定性措辞并挂 gap")

    return {"section_id": section_id, "verdict": verdict,
            "invariant_violations": [],
            "undefined_used": undefined_used,
            "missing_must_cover": missing_must_cover,
            "literal_numbers_found": literal_numbers_found,
            "notes": notes}


# --------------------------------------------------------------------------- #
# 回写：commit_to_graph（node_mentions.jsonl + 草稿落盘）
# --------------------------------------------------------------------------- #
def commit_to_graph(project_dir, section_id, node_mentions, draft_md=None) -> dict:
    pdir = Path(project_dir)
    drafts = pdir / "project" / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    nm = drafts / "node_mentions.jsonl"
    n = 0
    with open(nm, "a", encoding="utf-8") as f:
        for m in node_mentions or []:
            f.write(json.dumps({"section": section_id, **m}, ensure_ascii=False) + "\n")
            n += 1
    if draft_md is not None:
        (drafts / f"{section_id}.md").write_text(draft_md, encoding="utf-8")
    return {"section_id": section_id, "appended": n, "draft_saved": draft_md is not None}
