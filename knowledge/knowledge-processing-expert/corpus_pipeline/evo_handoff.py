# -*- coding: utf-8 -*-
"""evo_handoff —— 给「推演写作专家团」的交接包（知识处理侧出参）。

## 对端入参契约（新版专家团，无 MCP，只靠 bash/fs 读文件）

成员：
  - engineering-writer → §1–6
  - investment-writer  → §7–13（本实现按用户规则，§14–16 也归 investment）
  - reviewer           → 写完的稿子

每个成员要的交付物：
  该节正文 + citations + self_check + 审核判定

本模块把「形 + 新项目事实 + 冲突 + 缺口 + 检查标准」写成一个
写作成员可以直接 `cat` 的 markdown，避免他再去猜格式。

## 出参 dict

{
  "section", "title", "source_title", "writer_role",
  "problem",                # 用上财 §X 的形 + 华东理工的值，还原 §X
  "input_files": [{path, role, exists}],
  "deliverable": {body, citations, self_check, notes_for_reviewer},
  "checks": [...],
  "shape_facts": {...},
  "facts": [...],           # 本节图谱节点（clean 图谱）
  "conflicts": [...],       # 本节相关冲突（两侧都写，不裁决）
  "gaps": [...],            # 缺什么（不许按 0 算）
  "slot_bindings": [...],   # 槽位 → 值/节点/状态/公式
}
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable


# ================================================================ 常量

DEFAULT_CLEAN_GRAPH = "GRAPH-新项目-华东理工AI研究院-clean.json"
DEFAULT_FILLED_DIR = "prompt-filled"
DEFAULT_TEMPLATE_DIR = "prompt-templates-all"
LEGACY_TEMPLATE_DIR = "prompt-templates"
DEFAULT_HANDOFF_DIR = "handoff"

DEFAULT_CHECKS = [
    "借形不借值：可用上财结构，不得继承上财数值。",
    "缺值守卫：missing_customer 项写定性措辞并挂 gap，不许按 0 算。",
    "不许反算：不得由结论倒推中间量；中间量必须来自客户事实或算式。",
    "引用即绑定：每处数值写〔P-xxx〕节点引用（派生节点可用〔D-xxx〕）。",
    "冲突待审：冲突两侧都写，标「待审」，不裁决。",
    "派生值必带 formula + inputs：正文或脚注给出算式与输入节点。",
]

WRITER_SCOPE = {
    "engineering-writer": "§1–6：总论、学校简介、建设背景、选址、建设内容、规划设计方案",
    "investment-writer": "§7–13：节能、环境、卫生、风险、管理、招投标、投资估算",
}


def writer_for(section: str) -> str:
    """§1-6 → engineering-writer；§7-13 → investment-writer（用户指定）。"""
    try:
        major = int(str(section).split(".")[0])
    except Exception:
        return "engineering-writer"
    return "investment-writer" if major >= 7 else "engineering-writer"


# ================================================================ 读入

def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _load_index(project_dir: Path, template_dir: str) -> list[dict]:
    idx = _read_json(project_dir / template_dir / "_index.json")
    return idx or []


def _load_template_meta(project_dir: Path, template_dir: str, section: str) -> dict:
    p = project_dir / template_dir / ("_slots-%s.json" % section)
    data = _read_json(p)
    if not data:
        raise FileNotFoundError("缺少模板元数据：%s（先跑 evo_template_all.py）" % p)
    return data


def _load_fill(project_dir: Path, section: str) -> dict | None:
    p = project_dir / DEFAULT_FILLED_DIR / ("_fill-%s.json" % section)
    return _read_json(p)


def _load_graph(project_dir: Path) -> dict:
    p = project_dir / DEFAULT_CLEAN_GRAPH
    if not p.exists():
        p = project_dir / "GRAPH-新项目-华东理工AI研究院-merged.json"
    return _read_json(p) or {}


def _section_label_id(label: str) -> str | None:
    m = re.match(r"^§?\s*(\d+(?:\.\d+)*)", str(label or ""))
    return m.group(1) if m else None


# ================================================================ 事实 / 冲突 / 缺口

def _fact_by_id(graph: dict) -> dict:
    return {f.get("id"): f for f in (graph.get("items") or {}).get("facts") or []}


def _slot_names(*sources: Iterable[dict] | None) -> set[str]:
    out: set[str] = set()
    for src in sources:
        for s in src or []:
            n = str(s.get("name") or "").strip()
            if n:
                out.add(n)
    return out


def _is_relevant_fact(fact: dict, section: str, names: set[str]) -> bool:
    if str(fact.get("subject") or "") in names:
        return True
    if _section_label_id(fact.get("section") or "") == str(section):
        return True
    return False


def collect_facts(graph: dict, section: str, template_meta: dict,
                  fill: dict | None) -> list[dict]:
    """本节图谱事实：节点 ID + subject 匹配 + section 匹配。"""
    facts = (graph.get("items") or {}).get("facts") or []
    by_id = _fact_by_id(graph)
    names = _slot_names(template_meta.get("slots"), (fill or {}).get("slots"))
    ids: set[str] = set()
    for s in (fill or {}).get("slots") or []:
        if s.get("node_id"):
            ids.add(str(s["node_id"]))
        for a in s.get("alternatives") or []:
            if a.get("node_id"):
                ids.add(str(a["node_id"]))
    out = []
    for f in facts:
        fid = str(f.get("id") or "")
        if fid in ids or _is_relevant_fact(f, section, names):
            out.append(f)
    # 保持稳定：先按 section/id 排序
    out.sort(key=lambda f: (str(f.get("section") or ""), str(f.get("id") or "")))
    return out


def collect_conflicts(graph: dict, section: str, facts: list[dict],
                      template_meta: dict, fill: dict | None) -> list[dict]:
    """本节相关冲突：只按 involved 节点 ID 命中，避免「建安工程费用」等
    通用槽位名把别节冲突误挂到 §1.1。"""
    fact_ids = {str(f.get("id") or "") for f in facts}
    out = []
    for c in (graph.get("items") or {}).get("conflicts") or []:
        involved = {str(x) for x in c.get("involved") or []}
        if involved & fact_ids:
            out.append(c)
    return out


def collect_gaps(template_meta: dict, fill: dict | None) -> list[dict]:
    """缺值：优先用 fill JSON 的五态；没有 fill 时按模板槽位来源判断。"""
    out = []
    if fill:
        for s in fill.get("slots") or []:
            st = str(s.get("status") or "")
            if st in ("missing_customer", "missing_standard", "unfilled"):
                out.append({
                    "slot": s.get("name"),
                    "status": st,
                    "source_type": s.get("source") or "",
                    "reason": s.get("reason") or "",
                    "fallback": ("问客户" if st == "missing_customer"
                                 else "去标准库查" if st == "missing_standard"
                                 else "提示用户决策"),
                })
        return out
    for s in template_meta.get("slots") or []:
        st = str(s.get("source_type") or "")
        if st in ("CUSTOMER", "CUSTOMER_PRIMARY", "STANDARD", "JUDGMENT"):
            if s.get("synthetic"):
                continue
            out.append({
                "slot": s.get("name"),
                "status": "missing_customer" if st.startswith("CUSTOMER") else
                          "missing_standard" if st == "STANDARD" else "unfilled",
                "source_type": st,
                "reason": "模板未绑定图谱事实",
                "fallback": s.get("fallback") or "问客户",
            })
    return out


def collect_slot_bindings(fill: dict | None, template_meta: dict) -> list[dict]:
    """槽位 → 值/节点/状态/公式；写作成员可直接引用。"""
    out = []
    fill_by_name = {str(s.get("name") or ""): s for s in (fill or {}).get("slots") or []}
    names = [str(s.get("name") or "") for s in template_meta.get("slots") or []]
    if fill:
        for s in fill.get("slots") or []:
            if str(s.get("name") or "") not in names:
                names.append(str(s.get("name") or ""))
    for name in names:
        f = fill_by_name.get(name) or {}
        out.append({
            "name": name,
            "status": f.get("status") or "unfilled",
            "value": f.get("value"),
            "display": f.get("display") or "",
            "unit": f.get("unit") or "",
            "node_id": f.get("node_id") or "",
            "source": f.get("source") or "",
            "formula": f.get("formula") or "",
            "inputs": f.get("inputs") or [],
            "alternatives": f.get("alternatives") or [],
        })
    return out


# ================================================================ 输入文件

def collect_input_files(project_dir: Path, section: str, template_dir: str,
                        shape_pack_dir: Path) -> list[dict]:
    files: list[dict] = []

    def add(rel: str, role: str) -> None:
        p = project_dir / rel
        files.append({"path": rel, "role": role, "exists": p.exists()})

    add("%s/%s.md" % (template_dir, section), "模板（含槽位，无值）")
    legacy = "%s/%s.md" % (LEGACY_TEMPLATE_DIR, section)
    if (project_dir / legacy).exists():
        add(legacy, "旧模板（对照用，不用于写作）")
    filled_md = "%s/%s.md" % (DEFAULT_FILLED_DIR, section)
    if (project_dir / filled_md).exists():
        add(filled_md, "已填槽的完整提示词（旧契约，仅作事实对照）")
    fill_json = "%s/_fill-%s.json" % (DEFAULT_FILLED_DIR, section)
    if (project_dir / fill_json).exists():
        add(fill_json, "槽位五态明细（filled/computed/missing）")
    origin = "%s/_origin-merged.json" % DEFAULT_FILLED_DIR
    if (project_dir / origin).exists():
        add(origin, "262 槽位 origin 明细")
    add(DEFAULT_CLEAN_GRAPH, "清洗后的图谱（P-xxx 事实）")
    try:
        shape_rel = os.path.relpath(shape_pack_dir, project_dir)
    except Exception:
        shape_rel = str(shape_pack_dir)
    add(os.path.join(shape_rel, "templates", "section-form.yaml"), "本节形态（形包）")
    add("SHUFE-BDC-2019-001/source/normalized.md", "上财原文（本节行号见上）")
    return files


# ================================================================ 构建

def _shape_facts(template_meta: dict, shape_pack_dir: Path) -> dict:
    shape = dict(template_meta.get("shape") or {})
    anchor = template_meta.get("source_anchor") or {}
    return {
        "paras": shape.get("paras"),
        "tables": shape.get("tables"),
        "style": shape.get("style"),
        "word_budget": shape.get("word_budget"),
        "source_outline": shape.get("source_outline") or template_meta.get("must_cover") or [],
        "table_columns": shape.get("table_columns") or [],
        "form_stats": shape.get("form_stats") or {},
        "line_start": anchor.get("line_start"),
        "line_end": anchor.get("line_end"),
        "anchor_mode": anchor.get("mode"),
    }


def build_handoff(section: str, *, project_dir: str | Path,
                  shape_pack_dir: str | Path,
                  template_dir: str = DEFAULT_TEMPLATE_DIR) -> dict:
    """生成给「推演写作专家团」的交接包（dict）。"""
    project_dir = Path(project_dir)
    shape_pack_dir = Path(shape_pack_dir)
    section = str(section)

    index = _load_index(project_dir, template_dir)
    entry = next((x for x in index if str(x.get("id")) == section), None)
    template_meta = _load_template_meta(project_dir, template_dir, section)
    fill = _load_fill(project_dir, section)
    graph = _load_graph(project_dir)

    title = (template_meta.get("title") or (entry or {}).get("title")
             or "本节")
    source_title = (template_meta.get("source_title")
                    or (entry or {}).get("source_title") or title)
    role = writer_for(section)
    shape = _shape_facts(template_meta, shape_pack_dir)
    facts = collect_facts(graph, section, template_meta, fill)
    conflicts = collect_conflicts(graph, section, facts, template_meta, fill)
    gaps = collect_gaps(template_meta, fill)
    bindings = collect_slot_bindings(fill, template_meta)

    anchor_note = ""
    if shape.get("line_start") and shape.get("line_end"):
        anchor_note = "（§%s 在 %s–%s 行）" % (
            section, shape["line_start"], shape["line_end"])

    problem = ("用上财 §%s「%s」的形 + 华东理工「%s」的值，还原 §%s「%s」。"
               % (section, source_title, title, section, title))
    if anchor_note:
        problem += "上财原文锚点：`SHUFE-BDC-2019-001/source/normalized.md`%s。" % anchor_note

    checks = list(DEFAULT_CHECKS)
    checks.append("形态实测：本节必须 %s 段、%s 张表（normalized.md 实测；"
                  "形包旧统计 %s/%s）。" % (
                      shape.get("paras"), shape.get("tables"),
                      (shape.get("form_stats") or {}).get("paras"),
                      (shape.get("form_stats") or {}).get("tables")))
    checks.append("上财真值与上财专名不得残留；数值只写本包 facts/bindings 里的节点。")
    checks.append("写作范围：%s；不得越界写其他成员负责的章节。"
                  % WRITER_SCOPE.get(role, "本节"))
    if conflicts:
        checks.append("本节有 %d 条待审冲突：正文两侧都写，标「待审」，不裁决。" % len(conflicts))
    if gaps:
        checks.append("本节有 %d 个缺口：missing_customer 写定性措辞并挂 gap，"
                      "missing_standard 标「需检索」，不许按 0 算。" % len(gaps))

    deliverable = {
        "body": "该节正文 Markdown；数值全部写〔P-xxx〕节点引用"
                "（派生节点写〔D-xxx〕），缺值写定性措辞并挂 gap。",
        "citations": [{
            "claim_text": "正文中的一句话",
            "evidence_ids": ["P-xxx 或 D-xxx"],
            "source_file": "normalized.md 或客户材料路径",
            "section": section,
            "quote": "证据原文片段",
        }],
        "self_check": {
            "number_bound": True,
            "missing_handled": True,
            "conflicts_pending": bool(conflicts),
            "formula_shown": True,
        },
        "self_check_meaning": {
            "number_bound": "每个数值都有〔节点ID〕",
            "missing_handled": "缺值写定性措辞并挂 gap，没按 0 算",
            "conflicts_pending": "冲突两侧都写且标待审；本节无冲突填 false",
            "formula_shown": "命中算式的派生值都给出 formula + inputs",
        },
        "notes_for_reviewer": "审核要点：本节形态实测、冲突、缺口、上财值残留、引用完整性。",
        "review_verdict": "reviewer 写：通过 / 需修改 + 修改点",
    }

    return {
        "section": section,
        "title": title,
        "source_title": source_title,
        "writer_role": role,
        "problem": problem,
        "input_files": collect_input_files(project_dir, section, template_dir,
                                           shape_pack_dir),
        "deliverable": deliverable,
        "checks": checks,
        "shape_facts": shape,
        "facts": facts,
        "conflicts": conflicts,
        "gaps": gaps,
        "slot_bindings": bindings,
    }


# ================================================================ 渲染 markdown

def _md(v: Any) -> str:
    s = "—" if v is None else str(v)
    return s.replace("|", "\\|").replace("\n", " ")


def render_handoff_markdown(h: dict) -> str:
    L: list[str] = []
    L.append("# 交接包 · §%s %s" % (h["section"], h["title"]))
    L.append("")
    L.append("> 给：`%s`（%s）  " % (h["writer_role"],
                                      WRITER_SCOPE.get(h["writer_role"], "")))
    L.append("> 上财对应节：§%s「%s」  " % (h["section"], h["source_title"]))
    L.append("> 本文件是知识处理侧交接物，不是正文；写作成员按此写正文。")
    L.append("")
    L.append("## 一、本次问题")
    L.append("")
    L.append(h["problem"])
    L.append("")
    L.append("**边界**：知识处理专家只负责「形 + 新项目信息」；正文、citations、"
             "self_check 由 `%s` 写；审核由 `reviewer` 做。" % h["writer_role"])
    L.append("")
    L.append("## 二、真实输入文件")
    L.append("")
    L.append("| 角色 | 路径 | 是否存在 |")
    L.append("|---|---|---|")
    for f in h["input_files"]:
        L.append("| %s | `%s` | %s |" % (
            f["role"], f["path"], "✅" if f.get("exists") else "❌ 缺失"))
    L.append("")
    L.append("> 所有路径相对项目根目录。写作成员只有 bash/fs，请直接 `cat` 上表文件。")
    L.append("")
    L.append("## 三、交付物")
    L.append("")
    L.append("### 3.1 正文 `body`")
    L.append("")
    L.append("- %s" % h["deliverable"]["body"])
    L.append("")
    L.append("### 3.2 `citations`")
    L.append("")
    L.append("`list[dict]`，每项字段：")
    L.append("")
    L.append("```json")
    L.append(json.dumps(h["deliverable"]["citations"][0], ensure_ascii=False, indent=2))
    L.append("```")
    L.append("")
    L.append("### 3.3 `self_check`")
    L.append("")
    L.append("`dict`，四个布尔键：")
    L.append("")
    L.append("```json")
    L.append(json.dumps(h["deliverable"]["self_check"], ensure_ascii=False, indent=2))
    L.append("```")
    L.append("")
    L.append("| 键 | 含义 |")
    L.append("|---|---|")
    for k, v in (h["deliverable"].get("self_check_meaning") or {}).items():
        L.append("| `%s` | %s |" % (k, v))
    L.append("")
    L.append("### 3.4 `notes_for_reviewer` 与审核判定")
    L.append("")
    L.append("- %s" % h["deliverable"]["notes_for_reviewer"])
    L.append("- %s" % h["deliverable"]["review_verdict"])
    L.append("")
    L.append("### 3.5 返回 JSON 外形")
    L.append("")
    L.append("```json")
    L.append(json.dumps({
        "section": h["section"],
        "body": "Markdown 正文",
        "citations": h["deliverable"]["citations"],
        "self_check": {
            "number_bound": True,
            "missing_handled": True,
            "conflicts_pending": bool(h["conflicts"]),
            "formula_shown": True,
        },
        "notes_for_reviewer": "本节审核要点",
        "review_verdict": "通过 / 需修改 + 修改点",
    }, ensure_ascii=False, indent=2))
    L.append("```")
    L.append("")
    L.append("## 四、检查标准")
    L.append("")
    for i, c in enumerate(h["checks"], 1):
        L.append("%d. %s" % (i, c))
    L.append("")
    L.append("## 五、本节形态（normalized.md 实测）")
    L.append("")
    sf = h["shape_facts"]
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    L.append("| 段落 | %s 段 |" % _md(sf.get("paras")))
    L.append("| 表格 | %s 张 |" % _md(sf.get("tables")))
    L.append("| 文体 | %s |" % _md(sf.get("style")))
    L.append("| 字数预算 | %s |" % _md(sf.get("word_budget")))
    L.append("| 上财原文行号 | %s–%s |" % (_md(sf.get("line_start")),
                                           _md(sf.get("line_end"))))
    L.append("| 形包旧统计 | %s 段 / %s 表 |" % (
        _md(sf.get("form_stats", {}).get("paras")),
        _md(sf.get("form_stats", {}).get("tables"))))
    if sf.get("table_columns"):
        L.append("")
        L.append("**表格列（不得减少）**：")
        for i, cols in enumerate(sf["table_columns"], 1):
            L.append("- 表 %d：%s" % (i, " ｜ ".join(str(c) for c in cols)))
    L.append("")
    L.append("**本节必须覆盖**：")
    for i, x in enumerate(sf.get("source_outline") or [], 1):
        L.append("%d. %s" % (i, x))
    L.append("")
    L.append("## 六、本节事实（引用即绑定）")
    L.append("")
    if h["facts"]:
        L.append("| 节点 | subject | value | unit | status | source_type | section |")
        L.append("|---|---|---|---|---|---|---|")
        for f in h["facts"]:
            L.append("| `%s` | %s | %s | %s | %s | %s | %s |" % (
                _md(f.get("id")), _md(f.get("subject")), _md(f.get("value")),
                _md(f.get("unit")), _md(f.get("status")),
                _md(f.get("source_type")), _md(f.get("section"))))
    else:
        L.append("_（本节图谱无直接事实；见 3.2 的 slot_bindings 或缺口语义。）_")
    L.append("")
    L.append("## 七、本节相关冲突（两侧都写，不裁决）")
    L.append("")
    if h["conflicts"]:
        L.append("| id | type | severity | status | 描述 | involved |")
        L.append("|---|---|---|---|---|---|")
        for c in h["conflicts"]:
            L.append("| %s | %s | %s | %s | %s | %s |" % (
                c.get("id"), _md(c.get("type")), _md(c.get("severity")),
                _md(c.get("status")), _md(c.get("description")),
                "、".join("`%s`" % x for x in c.get("involved") or [])))
    else:
        L.append("无。")
    L.append("")
    L.append("## 八、缺口（不许按 0 算）")
    L.append("")
    if h["gaps"]:
        L.append("| 槽位 | 五态 | 来源 | 原因 | 填不上时 |")
        L.append("|---|---|---|---|---|")
        for g in h["gaps"]:
            L.append("| `%s` | %s | %s | %s | %s |" % (
                _md(g.get("slot")), _md(g.get("status")), _md(g.get("source_type")),
                _md(g.get("reason")), _md(g.get("fallback"))))
    else:
        L.append("无。")
    L.append("")
    L.append("## 九、槽位 → 节点速查")
    L.append("")
    L.append("| 槽位 | 状态 | 值 | 单位 | 节点 | 来源 | 公式 |")
    L.append("|---|---|---|---|---|---|---|")
    for s in h["slot_bindings"]:
        L.append("| `%s` | %s | %s | %s | %s | %s | %s |" % (
            _md(s.get("name")), _md(s.get("status")), _md(s.get("display") or s.get("value")),
            _md(s.get("unit")), _md(s.get("node_id")), _md(s.get("source")),
            _md(s.get("formula"))))
    L.append("")
    L.append("---")
    L.append("")
    L.append("> 交接包结束。写作成员按「本次问题 + 输入文件 + 交付物 + 检查标准」执行；"
             "reviewer 按第四节与 3.4 审核。")
    L.append("")
    return "\n".join(L)


# ================================================================ 批量 / CLI

def build_all(*, project_dir: str | Path, shape_pack_dir: str | Path,
              out_dir: str | Path, sections: list[str] | None = None,
              template_dir: str = DEFAULT_TEMPLATE_DIR) -> dict:
    project_dir = Path(project_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index = _load_index(project_dir, template_dir)
    ids = sections or [str(x.get("id")) for x in index]
    results = []
    errors = []
    for sid in ids:
        try:
            h = build_handoff(sid, project_dir=project_dir,
                              shape_pack_dir=shape_pack_dir,
                              template_dir=template_dir)
            md = render_handoff_markdown(h)
            (out / ("%s.md" % sid)).write_text(md, encoding="utf-8")
            (out / ("_data-%s.json" % sid)).write_text(
                json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
            results.append({
                "section": sid, "title": h["title"],
                "writer_role": h["writer_role"],
                "facts": len(h["facts"]), "conflicts": len(h["conflicts"]),
                "gaps": len(h["gaps"]), "slots": len(h["slot_bindings"]),
                "input_files": len(h["input_files"]),
                "missing_inputs": sum(1 for f in h["input_files"]
                                      if not f.get("exists")),
            })
        except Exception as e:
            errors.append({"section": sid, "error": "%s: %s"
                           % (type(e).__name__, e)})
    (out / "_index.json").write_text(json.dumps({
        "generated": len(results), "errors": errors, "sections": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"generated": results, "errors": errors}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成给推演写作专家团的交接包")
    ap.add_argument("--project-dir", default=".")
    ap.add_argument("--shape-pack", default="形-可复用知识资产-v1.0")
    ap.add_argument("--out", default=DEFAULT_HANDOFF_DIR)
    ap.add_argument("--template-dir", default=DEFAULT_TEMPLATE_DIR)
    ap.add_argument("--sections", default="",
                    help="逗号分隔节号；默认全部 119 节")
    args = ap.parse_args(argv)
    sections = [x.strip() for x in args.sections.split(",") if x.strip()] or None
    result = build_all(project_dir=args.project_dir,
                       shape_pack_dir=args.shape_pack,
                       out_dir=args.out, sections=sections,
                       template_dir=args.template_dir)
    print("handoff generated %d; errors %d"
          % (len(result["generated"]), len(result["errors"])))
    for e in result["errors"]:
        print(" -", e)
    for x in result["generated"]:
        if x["section"] in ("1.1", "13.3"):
            print(" ", x)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
