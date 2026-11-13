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
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kp_toolkit import prompt_fill as pf  # noqa: E402

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


def cmd_render(corpus: Dict[str, Any], out_path: str, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    overrides = overrides or {}
    audit = pf.audit(corpus)
    rendered = pf.render_all(corpus, overrides)
    o: List[str] = []
    o += _md_header(corpus, audit, overrides)
    o.append("## 1　规则复算状态")
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


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        sys.stderr.write(__doc__ or "usage: prompt_fill_cli.py <cmd> <corpus> ...\n")
        return 2
    cmd, corpus_dir = argv[1], argv[2]
    corpus = pf.load_corpus(corpus_dir)
    if cmd == "audit":
        print(json.dumps(pf.audit(corpus), ensure_ascii=False, indent=1))
        return 0
    if cmd == "model":
        print(json.dumps(cmd_model(corpus, argv[3]), ensure_ascii=False))
        return 0
    if cmd == "render":
        print(json.dumps(cmd_render(corpus, argv[3]), ensure_ascii=False))
        return 0
    if cmd == "whatif":
        print(json.dumps(cmd_whatif(corpus, argv[3], argv[4:]), ensure_ascii=False))
        return 0
    sys.stderr.write("unknown cmd: %s\n" % cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
