#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prompt_fill 命令行：把「节点填充」接进提示词。

子命令：
  audit                        体检：填充模式分布、规则可复算率、过期值、歧义
  model   <out.yaml>           导出节点填充模型（每节点的 fill_mode / constraint）
  render  <out.md>             渲染动态提示词包（值取节点现值 + 硬/软标签 + 检索任务）
  whatif  <out.md> k=v ...     假设输入变化：重算 → 重渲染 → 出受影响节与差异

用法示例：
  python3 tools/prompt_fill_cli.py render  "$CORPUS" out/动态提示词.md
  python3 tools/prompt_fill_cli.py whatif  "$CORPUS" out/whatif.md "pred:地上建筑面积=18500"
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kp_toolkit import prompt_fill as pf  # noqa: E402
from kp_toolkit import style_fewshot as sf  # noqa: E402
from kp_toolkit import prompt_hygiene as ph  # noqa: E402

FILL_CN = {
    "customer_input": "客户输入事实",
    "derived": "推演结果",
    "fixed_norm": "规范固定值",
    "retrievable": "可检索补全",
    "missing_hard": "缺值（硬）",
    "structural": "结构性（无值）",
}
CONS_CN = {"hard": "硬约束", "soft": "软约束", "none": "—"}


def _model_rows(corpus: Dict[str, Any]) -> List[Dict[str, Any]]:
    fills = pf.classify_all(corpus["nodes"])
    rows = []
    for n in corpus["nodes"]:
        f = fills[n["id"]]
        rows.append({
            "id": n["id"], "subject": n.get("subject"), "predicate": n.get("predicate"),
            "value": n.get("value"), "unit": n.get("unit"), "section": n.get("section"),
            "kind": n.get("kind"),
            "fill_mode": f["fill_mode"], "constraint": f["constraint"], "reason": f["reason"],
        })
    return rows


def cmd_model(corpus: Dict[str, Any], out_path: str) -> Dict[str, Any]:
    rows = _model_rows(corpus)
    import yaml
    payload = {"meta": {"corpus": "SHUFE-BDC-2019-001", "nodes": len(rows),
                        "legend": {"fill_mode": FILL_CN, "constraint": CONS_CN}},
               "nodes": rows}
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False, width=200)
    return {"out": out_path, "nodes": len(rows)}


def _md_header(corpus: Dict[str, Any], audit: Dict[str, Any], overrides: Dict[str, Any]) -> List[str]:
    o = []
    fm = audit["fill_modes"]
    def g(mode, cons):
        return fm.get(mode, {}).get(cons, 0)
    o.append("# 上海财经大学中山北一路大数据研究中心 · 写作提示词（动态填充版）")
    o.append("")
    o.append("> **这份文件不是快照。** 每节提示词里的取值、算式状态与冲突标注都是**按节点现值现渲染**的；"
             "节点填充信息一变（客户改数、或推演重算），重跑渲染器，提示词即随之变化。")
    o.append("")
    o.append("| 项 | 值 |")
    o.append("|---|---|")
    o.append("| 节点总数 | %d（其中硬约束 %d ／ 软约束 %d ／ 结构性 %d） |" % (
        audit["nodes"], g("customer_input", "hard") + g("derived", "hard") + g("fixed_norm", "hard"),
        g("retrievable", "soft"), g("structural", "none")))
    o.append("| 填充模式 | 客户输入 %d　推演结果 %d　规范固定 %d　可检索 %d |" % (
        g("customer_input", "hard"), g("derived", "hard"), g("fixed_norm", "hard"), g("retrievable", "soft")))
    o.append("| 技术函数 | %d 条，可复算 %d 条，未满足 %d 条（缺输入/歧义/算式待修） |" % (
        audit["rules"], audit["rules_ok"], len(audit["rules_unsatisfied"])))
    o.append("| 图中过期值 | %d 条（复算值与图存值不一致） |" % len(audit["rules_stale"]))
    o.append("| 本次覆盖 | %s |" % ("、".join(sorted(overrides)) if overrides else "无（按图现值）"))
    o.append("")
    o.append("---")
    o.append("")
    o.append("## 0　机制：填充模式 × 约束强度")
    o.append("")
    o.append("| 填充模式 | 约束 | 值从哪来 | 变的时候提示词怎么变 | 缺了怎么办 |")
    o.append("|---|---|---|---|---|")
    o.append("| 客户输入事实 | **硬** | 客户材料/原报告，带来源 chunk | 该行取值直接换新；引用它的规则全部重算 | **留白** + 缺口，不估、不检索替代 |")
    o.append("| 推演结果 | **硬** | `rules.yaml` 的 expr 按 deps 算出 | 输入变 → 重算 → 行内 `R=…` 与正文取值同步换 | `guard: missing_any_dep => undefined`，不得填 0 |")
    o.append("| 规范固定值 | **硬** | 强制性/强约束条款（A/B 级） | 条款版本变 → 按新条款重绑 | 标「条款待核」，不得写「符合规范」 |")
    o.append("| 可检索补全 | **软** | **自动触发检索**：知识库（语料包/公共标准库）+ web（标准原文/官方公告） | 检索结果入图后，该行由「需检索」变为带来源的值 | 出**检索任务**（见 §2），结果带 URL 与状态 |")
    o.append("| 结构性 | 无 | 骨架标题/编号 | 不随值变 | — |")
    o.append("")
    o.append("**硬约束的铁律**：数值、金额、面积、人数、日期、文号、实体名，只能来自客户输入或推演；"
             "**不得检索替代、不得插值**。**软约束**才允许触发检索，且检索结果必须带来源与「已核/待核」状态。")
    o.append("")
    o.append("---")
    o.append("")
    return o


def _md_tasks(rendered: List[Dict[str, Any]]) -> List[str]:
    o = ["## 2　检索任务（软约束缺值 / 待核条款，自动触发）", ""]
    rows = [(s["section_no"], s["title"], t) for s in rendered for t in s["soft_tasks"]]
    if not rows:
        o += ["（本次无软约束缺值，未触发检索）", ""]
        return o
    o.append("| # | 节 | 对象 | 缺什么 | 允许来源 |")
    o.append("|---|---|---|---|---|")
    for i, (no, title, t) in enumerate(rows, 1):
        obj = t.get("standard") or ("%s·%s" % (t.get("subject") or "", t.get("predicate") or ""))
        cl = str(t.get("clause") or "")
        clause = (" 第%s条" % cl) if cl and all(c.isdigit() or c == "." for c in cl) else ((" " + cl) if cl else "")
        why = t.get("why") or ""
        st = t.get("status") or ""
        o.append("| %d | `%s` %s | %s%s | %s%s | %s |" % (
            i, no, title, obj, clause, why, ("（%s）" % st if st else ""),
            "、".join(t.get("sources") or [])))
    o.append("")
    o.append("> 检索回来的值只填**软约束**位；命中硬约束位的（数值/金额/日期等）一律拒绝，按留白处理。")
    o.append("")
    o.append("---")
    o.append("")
    return o


def _md_transmission(rendered: List[Dict[str, Any]], corpus: Dict[str, Any]) -> List[str]:
    """按「谓词标签」聚合影响面：同一个量往往在多个节各有一个节点。"""
    label_secs: Dict[str, set] = {}
    label_vals: Dict[str, set] = {}
    for s in rendered:
        for r in s["value_rows"]:
            n = corpus["by_id"].get(r["node"], {})
            label = str(n.get("predicate") or "")
            if not label or label == "=":
                label = str(n.get("subject") or "")
            if not label:
                continue
            label_secs.setdefault(label, set()).add(s["section_no"])
            label_vals.setdefault(label, set()).add(str(n.get("value")))
    top = sorted(label_secs.items(), key=lambda kv: -len(kv[1]))[:15]
    o = ["## 3　变更传导（改一个量，哪些节跟着变）", "",
         "| 量（谓词/主体） | 当前值 | 影响节数 | 节 |", "|---|---|---|---|"]
    for label, secs in top:
        vals = "、".join(sorted(label_vals.get(label, []))[:3])
        o.append("| %s | %s | %d | %s |" % (
            label, vals or "—", len(secs),
            "、".join("§%s" % x for x in sorted(secs)[:8]) + ("…" if len(secs) > 8 else "")))
    o += ["", "> 同一个量在报告不同位置各有一个节点（值应一致）；改一处即影响全部列出的节。"
              "规则侧传导见每节 `R=…` 行：输入变 → 复算值变 → 该行与正文取值一起换；"
              "图存值与复算值不符时，正文行标 `⚠️复算不符`。", "", "---", ""]
    return o


def cmd_render(corpus: Dict[str, Any], out_path: str, overrides: Dict[str, Any] | None = None,
               with_style: bool = True, values_in_prompt: bool = True) -> Dict[str, Any]:
    overrides = overrides or {}
    audit = pf.audit(corpus)
    rendered = pf.render_all(corpus, overrides, values_in_prompt)
    o: List[str] = []
    o += _md_header(corpus, audit, overrides)
    style_idx: Dict[str, List[Dict[str, Any]]] = {}
    if with_style:
        sk = sf.load_skeletons(corpus["dir"])
        style_idx = sf.index_by_section(sk)
        o.append("## 1　文体层（few-shot ＋ 可机检画像）")
        o.append("")
        o += sf.render_profile_block(sf.profile(sk))
        o.append("**为什么用骨架做 few-shot**：骨架保留了原报告的句式、叙述顺序与段落节奏，"
                 "同时把项目值抽成 `{{node:}}`/`{{ent:}}`/`{{time:}}` 槽位——"
                 "所以它天然满足「借形不借值」，写作时只换槽位、不改骨架。")
        o.append("")
        o.append("### 1.2　规则复算状态")
    o.append("")
    o.append("| 规则 | 状态 | 复算值 | 图存值 |")
    o.append("|---|---|---|---|")
    rules_res = pf.recompute(corpus["rules"], corpus["nodes"], overrides, corpus.get("binds"))
    for rid in sorted(rules_res):
        r = rules_res[rid]
        st = {"ok": "可复算", "undefined": "缺输入", "ambiguous": "歧义（多值候选）",
              "expr_error": "算式待修"}.get(r.get("status"), r.get("status"))
        o.append("| `%s` | %s | %s | %s |" % (
            rid, st,
            ("" if r.get("value") is None else r["value"]),
            r.get("stored", "—")))
    unsat = {k: v for k, v in rules_res.items() if v.get("status") != "ok"}
    if unsat:
        o.append("")
        for k, v in unsat.items():
            detail = v.get("missing") or v.get("candidates") or v.get("error") or ""
            if isinstance(detail, list):
                detail = "、".join(map(str, detail))
            o.append("- `%s`：%s %s" % (k, v.get("status"), detail))
    o.append("")
    o.append("---")
    o.append("")
    o += _md_tasks(rendered)
    o += _md_transmission(rendered, corpus)
    o.append("## 4　逐节提示词（%d 节，值随节点变）" % len(rendered))
    o.append("")
    for i, s in enumerate(rendered, 1):
        o.append("### 4.%d　`%s`　%s" % (i, s["section_no"], s["title"]))
        o.append("")
        o.append("```text")
        o.append(s["prompt"])
        o.append("```")
        o.append("")
        if with_style:
            o += sf.render_examples_block(s["section_no"], sf.section_examples(style_idx, s["section_no"]))
    o.append("---")
    o.append("")
    o.append("## 5　怎么更新（值变了就重跑，不用改提示词）")
    o.append("")
    o.append("```bash")
    o.append("python3 tools/prompt_fill_cli.py audit   <corpus>                  # 体检：填充分布/复算率/过期值/歧义")
    o.append("python3 tools/prompt_fill_cli.py render  <corpus> 动态提示词.md    # 按节点现值重渲染全部提示词")
    o.append('python3 tools/prompt_fill_cli.py whatif  <corpus> diff.md "pred:<标签>=<新值>"  # 假设值变，看差异')
    o.append("```")
    o.append("")
    o.append("> 数据源：`graph/nodes.yaml`（%d 节点）· `graph/rules.yaml`（%d 规则）· "
             "`graph/derivation_bindings.yaml`（规则→输入绑定）· `写作输入/section-prompts.yaml`（%d 节）。"
             "渲染器：`tools/prompt_fill_cli.py render`，零 LLM、同输入同输出。" % (
                 len(corpus["nodes"]), len(corpus["rules"]), len(corpus["prompts"])))
    o.append("")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(o))
    return {"out": out_path, "sections": len(rendered), "tasks": sum(len(s["soft_tasks"]) for s in rendered)}


def cmd_whatif(corpus: Dict[str, Any], out_path: str, pairs: List[str]) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    for p in pairs:
        k, _, v = p.partition("=")
        overrides[k.strip()] = v.strip()
    base = pf.render_all(corpus, {})
    after = pf.render_all(corpus, overrides)
    a_rules = pf.recompute(corpus["rules"], corpus["nodes"], {}, corpus.get("binds"))
    b_rules = pf.recompute(corpus["rules"], corpus["nodes"], overrides, corpus.get("binds"))

    o = ["# 假设输入变化 → 提示词随之变化（what-if）", ""]
    o.append("**覆盖**：" + "；".join("`%s` = %s" % (k, v) for k, v in overrides.items()))
    o.append("")
    o.append("## 1　规则重算差异")
    o.append("")
    o.append("| 规则 | 前 | 后 |")
    o.append("|---|---|---|")
    changed_rules = 0
    for rid in sorted(a_rules):
        x, y = a_rules[rid].get("value"), b_rules[rid].get("value")
        if x != y:
            changed_rules += 1
            o.append("| `%s` | %s | %s |" % (rid, x, y))
    if not changed_rules:
        o.append("| — | 无 | 无 |")
    o.append("")
    o.append("## 2　提示词差异（仅列发生变化的节）")
    o.append("")
    changed_sections = 0
    for sb, sa in zip(base, after):
        if sb["prompt"] == sa["prompt"]:
            continue
        changed_sections += 1
        o.append("### `%s` %s" % (sa["section_no"], sa["title"]))
        o.append("")
        o.append("```diff")
        diff = difflib.unified_diff(sb["prompt"].splitlines(), sa["prompt"].splitlines(),
                                    fromfile="覆盖前", tofile="覆盖后", lineterm="", n=1)
        o.extend(list(diff)[:60])
        o.append("```")
        o.append("")
    if not changed_sections:
        o.append("（无节变化）")
        o.append("")
    o.append("---")
    o.append("")
    o.append("> 结论：提示词不是静态文本——覆盖值一变，取值行、`R=` 复算状态、冲突备注同步改写；"
             "本节即为同一批提示词在两组输入下的真实渲染差异。")
    o.append("")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(o))
    return {"out": out_path, "changed_rules": changed_rules, "changed_sections": changed_sections}


def cmd_template(corpus: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
    """拆成「模板（零项目值）」＋「事实包」＋「泄漏审计」。"""
    import yaml
    r = ph.build(corpus, corpus["prompts"])
    os.makedirs(out_dir, exist_ok=True)
    tpl_path = os.path.join(out_dir, "prompt-templates-无项目值.yaml")
    fact_path = os.path.join(out_dir, "prompt-fact-pack-上财.yaml")
    audit_path = os.path.join(out_dir, "泄漏审计.md")
    with open(tpl_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"meta": {"corpus": "generic", "sections": len(r["templates"]),
                                 "note": "模板不含任何项目值；{{…}} 为槽位，实例化时由事实包填入"},
                        "templates": r["templates"]}, fh, allow_unicode=True, sort_keys=False, width=200)
    with open(fact_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"meta": {"corpus": "SHUFE-BDC-2019-001", "facts": sum(len(f["facts"]) for f in r["facts"]),
                                 "note": "本项目事实包：只在写本项目时注入，不得进模板"},
                        "sections": r["facts"]}, fh, allow_unicode=True, sort_keys=False, width=200)
    b, a = r["report"]["before"], r["report"]["after"]
    o = ["# 提示词泄漏审计（模板化前后）", "",
         "判据：模板里**不许出现本项目身份与取值**；允许保留标准号、条款号、层级、表号、`R-` 规则名与算式常量。", "",
         "| 类别 | 模板化前 | 模板化后 | 说明 |", "|---|---|---|---|",
         "| 项目专名（上财/虹口/各研究中心…） | %d | %d | 全部换为 `{{项目专名}}` / `{{主体}}` |" % (b["项目专名"], a["项目专名"]),
         "| 节点 ID | %d | %d | 换为 `{{节点}}`，实例化时重绑 |" % (b["节点ID"], a["节点ID"]),
         "| 项目尺度（原文约 N 字符 / M 个切片 / 证据等级计数） | %d | %d | 换为 `{{骨架字数}}` 等 |" % (b["项目尺度"], a["项目尺度"]),
         "| 字面数值 | %d | %d | 剩余仅标准号/条款号片段（见下） |" % (b["字面数值"], a["字面数值"]),
         "",
         "## 残留（逐条说明，不隐藏）", ""]
    if r["report"]["residual"]:
        o.append("| 节 | 残留数 | 样例 | 判定 |")
        o.append("|---|---|---|---|")
        for x in r["report"]["residual"]:
            samp = (x["scan"]["字面数值"]["samples"] or [""])[0]
            o.append("| `%s` | %d | %s | 标准号/条款号片段，非项目值 |" % (
                x["section"], x["scan"]["字面数值"]["count"], samp))
    else:
        o.append("无残留。")
    o += ["", "## 组装方式（三步，缺一不可）", "",
          "1. **模板**（本文附 `prompt-templates-无项目值.yaml`）：结构、法定覆盖、技术函数算式、文体规则——跨项目复用。",
          "2. **事实包**（`prompt-fact-pack-上财.yaml`）：本项目的节点、值、定位、证据等级、冲突——**只在本项目注入**。",
          "3. **骨架 few-shot**（`chunks/skeletons.jsonl`）：同节 2–3 段，值已在槽位里，复刻句式而不搬值。", "",
          "> 只给模板不给事实包 → 写手无值可写（会去猜）；只给事实包不给模板 → 退化成罗列数字。",
          "> 三样一起给，才是「写法可复用、取值不串项目」。", ""]
    with open(audit_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(o))
    return {"templates": tpl_path, "facts": fact_path, "audit": audit_path,
            "before": b, "after": a, "residual_sections": len(r["report"]["residual"])}


def cmd_factpack(corpus: Dict[str, Any], out_path: str) -> Dict[str, Any]:
    """从图谱重新导出事实包（唯一真相源 = graph/nodes.yaml，不从旧提示词文本解析）。"""
    import yaml
    fills = pf.classify_all(corpus["nodes"])
    by_id = corpus["by_id"]
    sections, total, dangling = [], 0, []
    for p in corpus["prompts"]:
        ids = []
        for m in re.finditer(r"N-[0-9a-f]{12}", p.get("prompt") or ""):
            if m.group(0) not in ids:
                ids.append(m.group(0))
        facts = []
        for nid in ids:
            n = by_id.get(nid)
            if not n:
                dangling.append(nid)
                continue
            f = fills[nid]
            facts.append({"node": nid, "subject": n.get("subject"), "predicate": n.get("predicate"),
                          "value": n.get("value"), "unit": n.get("unit") or "",
                          "section": n.get("section"), "fill_mode": f["fill_mode"],
                          "constraint": f["constraint"], "status": n.get("status") or "",
                          "evidence": n.get("evidence_kind") or ""})
        total += len(facts)
        sections.append({"section_no": p.get("section_no"), "title": p.get("title"),
                         "level": p.get("level"), "path": p.get("path"), "facts": facts})
    payload = {"meta": {"corpus": "SHUFE-BDC-2019-001", "source": "graph/nodes.yaml",
                        "sections": len(sections), "entries": total,
                        "dangling": sorted(set(dangling)),
                        "note": "由图谱导出；值以 nodes.yaml 为准，节点不在图中的记入 dangling 并留待修"},
               "sections": sections}
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False, width=200)
    return {"out": out_path, "entries": total, "sections": len(sections),
            "dangling": len(set(dangling))}


def cmd_snapshot(corpus: Dict[str, Any], out_path: str, pack_path: str,
                 with_style: bool = True) -> Dict[str, Any]:
    """值快照版：提示词正文保持值外置，每节附「本节值快照」并带事实包哈希。"""
    import hashlib
    import yaml
    pack = yaml.safe_load(open(pack_path, encoding="utf-8"))
    pack_hash = hashlib.sha256(open(pack_path, "rb").read()).hexdigest()[:16]
    by_sec = {s["section_no"]: s for s in pack["sections"]}
    style_idx = {}
    if with_style:
        style_idx = sf.index_by_section(sf.load_skeletons(corpus["dir"]))
    rendered = pf.render_all(corpus, None, values_in_prompt=False)
    o = ["# 上财可研 · 写作提示词（值快照版）", "",
         "> 提示词正文**不含值**；每节末尾附「本节值快照」，取自事实包 `%s`（SHA-256 前 16 位 `%s`）。" % (
             os.path.basename(pack_path), pack_hash),
         "> 快照与事实包不一致时，**以事实包为准**；事实包与 `graph/nodes.yaml` 不一致时，以图为准并回写。", ""]
    o += ["---", "", "## 逐节（%d 节）" % len(rendered), ""]
    for i, r in enumerate(rendered, 1):
        o.append("### %d　`%s`　%s" % (i, r["section_no"], r["title"]))
        o.append("")
        o.append("```text")
        o.append(r["prompt"])
        o.append("```")
        o.append("")
        if with_style:
            o += sf.render_examples_block(r["section_no"], sf.section_examples(style_idx, r["section_no"]))
        facts = (by_sec.get(r["section_no"]) or {}).get("facts") or []
        if facts:
            o.append("**本节值快照**（%d 条，来自事实包）：" % len(facts))
            o.append("")
            o.append("| 节点 | 主体·谓词 | 值 | 约束 | 状态 |")
            o.append("|---|---|---|---|---|")
            for f in facts[:40]:
                o.append("| `%s` | %s·%s | %s %s | %s | %s |" % (
                    f["node"], f.get("subject"), f.get("predicate"),
                    f.get("value"), f.get("unit") or "",
                    "硬" if f.get("constraint") == "hard" else "软", f.get("status") or "—"))
            if len(facts) > 40:
                o.append("| … | 共 %d 条 | | | |" % len(facts))
        else:
            o.append("**本节值快照**：无（本节为结构章或无绑定节点）。")
        o.append("")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(o))
    return {"out": out_path, "sections": len(rendered), "pack_hash": pack_hash}


def cmd_change(corpus: Dict[str, Any], out_path: str, pairs: List[str]) -> Dict[str, Any]:
    """事实变更 → 二次推演工单：影响面分级 + 派发对象 + 验收口径。"""
    overrides: Dict[str, Any] = {}
    for p in pairs:
        k, _, v = p.partition("=")
        overrides[k.strip()] = v.strip()

    base_rules = pf.recompute(corpus["rules"], corpus["nodes"], {}, corpus.get("binds"))
    new_rules = pf.recompute(corpus["rules"], corpus["nodes"], overrides, corpus.get("binds"))

    # 1) 直接变更节点：按 id 或按标签命中
    changed_nodes = []
    for n in corpus["nodes"]:
        ov = pf._ov(n, overrides)
        if ov is not None and str(ov) != str(n.get("value")):
            changed_nodes.append({"node": n["id"], "subject": n.get("subject"),
                                  "predicate": n.get("predicate"),
                                  "old": n.get("value"), "new": ov, "section": n.get("section")})

    # 2) 规则级变化（值变 / 缺输入变可算 / 可算变缺输入）
    rule_delta = []
    for rid in sorted(base_rules):
        a, b = base_rules[rid], new_rules[rid]
        if a.get("value") != b.get("value") or a.get("status") != b.get("status"):
            rule_delta.append({"rule": rid, "old": a.get("value"), "new": b.get("value"),
                               "status": "%s → %s" % (a.get("status"), b.get("status")),
                               "stored": b.get("stored")})

    # 3) 节级影响：A 直接引用变更节点；B 引用受影响规则；C 其余
    touched_ids = {c["node"] for c in changed_nodes}
    touched_rules = {r["rule"] for r in rule_delta}
    sections = []
    for p in corpus["prompts"]:
        text = p.get("prompt") or ""
        ids = set(re.findall(r"N-[0-9a-f]{12}", text))
        rules_here = set(p.get("rules") or [])
        if ids & touched_ids:
            level, why = "A", "直接引用变更节点"
        elif rules_here & touched_rules:
            level, why = "A", "引用受影响的技术函数"
        elif any((c["section"] or "") == p.get("section_no") for c in changed_nodes):
            level, why = "B", "同节存在变更节点的其他落点"
        else:
            continue
        sections.append({"section": p.get("section_no"), "title": p.get("title"),
                         "level": level, "why": why,
                         "hits": sorted(ids & touched_ids), "rules": sorted(rules_here & touched_rules)})

    o = ["# 事实变更 · 二次推演工单", ""]
    o.append("**变更集**：" + "；".join("`%s` = %s" % (k, v) for k, v in overrides.items()))
    o.append("")
    o.append("**责任链**（谁做哪一段，见文末）：客户/需求方提变更 → 知识处理侧确定性重算与重渲染 → "
             "主理人定影响面并派发 → 写作成员只重写被点名的节 → 总审只重审被改动的节。")
    o.append("")
    o.append("## 1　直接变更的节点（%d 个）" % len(changed_nodes))
    o.append("")
    if changed_nodes:
        o.append("| 节点 | 主体·谓词 | 原值 | 新值 | 所在节 |")
        o.append("|---|---|---|---|---|")
        for c in changed_nodes[:40]:
            o.append("| `%s` | %s·%s | %s | **%s** | §%s |" % (
                c["node"], c["subject"], c["predicate"], c["old"], c["new"], c["section"]))
        if len(changed_nodes) > 40:
            o.append("| … | 共 %d 个 | | | |" % len(changed_nodes))
    else:
        o.append("（无节点值变化：标签未命中，或新值与原值相同）")
    o.append("")
    o.append("## 2　规则重算差异（%d 条）" % len(rule_delta))
    o.append("")
    if rule_delta:
        o.append("| 规则 | 原值 | 新值 | 状态 | 与图存值 |")
        o.append("|---|---|---|---|---|")
        for r in rule_delta:
            stale = "—" if r["stored"] in (None, "") else (
                "**图存 %s，需回写**" % r["stored"] if str(r["stored"]) != str(r["new"]) else "与图一致")
            o.append("| `%s` | %s | **%s** | %s | %s |" % (r["rule"], r["old"], r["new"], r["status"], stale))
    else:
        o.append("（无规则值变化）")
    o.append("")
    o.append("## 3　受影响节（%d 节）" % len(sections))
    o.append("")
    o.append("| 级别 | 节 | 标题 | 原因 | 命中节点 | 命中函数 | 动作 |")
    o.append("|---|---|---|---|---|---|---|")
    for s in sections:
        act = "重写并送总审" if s["level"] == "A" else "核对取值一致性（不动笔）"
        o.append("| %s | `%s` | %s | %s | %s | %s | %s |" % (
            s["level"], s["section"], s["title"], s["why"],
            "、".join("`%s`" % x for x in s["hits"][:3]) or "—",
            "、".join("`%s`" % x for x in s["rules"][:3]) or "—", act))
    o.append("")
    o.append("## 4　冲突处置（变更即重开）")
    o.append("")
    o.append("- 变更使原「待审冲突」的两个值之一失效 → 该冲突降级为**已消解**，须在冲突表留痕（谁裁定的、依据）。")
    o.append("- 变更引入新的并列值 → 新建「待审冲突」，正文并列呈现，不裁决。")
    o.append("- 变更使某节由「可复算」变「缺输入」→ 该节返回 `unresolved`，正文对应取值留白。")
    o.append("")
    o.append("## 5　责任链（谁负责二次推演）")
    o.append("")
    o.append("| 环节 | 责任方 | 交付 | 不许做 |")
    o.append("|---|---|---|---|")
    o.append("| 提出变更、给依据 | 客户 / 需求方 | 变更单（改哪个量、改成多少、依据文件） | 口头改数不留痕 |")
    o.append("| 落变更集、定影响面 | **主理人（编排器）** | 本工单（分级 A/B/C + 派发） | 让模型自由判断影响面 |")
    o.append("| 重算与重渲染 | 知识处理侧（工具） | 规则新值、新提示词、stale 清单 | 替客户裁决冲突、补口径 |")
    o.append("| 重写正文 | 写作成员 | 被点名 A 级节的新回执 | 顺手改未被点名的节 |")
    o.append("| 重审 | 总审 | pass/reject（六项尺度） | 改稿、重算 |")
    o.append("")
    o.append("> 一句话：**二次推演由主理人发起与派发，知识处理侧提供确定性重算，写作与总审只处理被点名的节**。")
    o.append("> 工具只算「变了什么、影响谁」，不决定「要不要改」——那是主理人与客户的职责。")
    o.append("")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(o))
    return {"out": out_path, "changed_nodes": len(changed_nodes),
            "rule_delta": len(rule_delta), "sections": len(sections)}


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        sys.stderr.write(__doc__ or "usage: prompt_fill_cli.py <cmd> <corpus> ...\n")
        return 2
    cmd, corpus_dir = argv[1], argv[2]
    corpus = pf.load_corpus(corpus_dir)
    corpus["dir"] = corpus_dir
    if cmd == "audit":
        print(json.dumps(pf.audit(corpus), ensure_ascii=False, indent=1))
        return 0
    if cmd == "model":
        print(json.dumps(cmd_model(corpus, argv[3]), ensure_ascii=False))
        return 0
    if cmd == "render":
        with_style = "--no-style" not in argv
        values_in_prompt = "--values" in argv
        print(json.dumps(cmd_render(corpus, argv[3], with_style=with_style,
                                    values_in_prompt=values_in_prompt), ensure_ascii=False))
        return 0
    if cmd == "factpack":
        print(json.dumps(cmd_factpack(corpus, argv[3]), ensure_ascii=False))
        return 0
    if cmd == "snapshot":
        print(json.dumps(cmd_snapshot(corpus, argv[3], argv[4]), ensure_ascii=False))
        return 0
    if cmd == "change":
        print(json.dumps(cmd_change(corpus, argv[3], argv[4:]), ensure_ascii=False))
        return 0
    if cmd == "template":
        print(json.dumps(cmd_template(corpus, argv[3]), ensure_ascii=False))
        return 0
    if cmd == "whatif":
        print(json.dumps(cmd_whatif(corpus, argv[3], argv[4:]), ensure_ascii=False))
        return 0
    sys.stderr.write("unknown cmd: %s\n" % cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
