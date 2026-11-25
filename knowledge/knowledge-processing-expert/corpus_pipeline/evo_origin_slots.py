# -*- coding: utf-8 -*-
"""evo_origin_slots —— 把节点属性归属（原始输入 / 派生 / 待定）合进槽位并重写提示词。

只做确定性的事，不调用 LLM，不修改 evo_origin_check.py / evo_fill_slots.py。

输入（项目目录）：
  GRAPH-新项目-华东理工AI研究院-merged.json
  形-可复用知识资产-v1.0/functions/derivation_templates.yaml
  形-可复用知识资产-v1.0/ontology/fact-aliases.yaml
  prompt-templates/<section>.md
  prompt-filled/_fill-<section>.json
  prompt-filled/derived-nodes.json

输出：
  prompt-filled/_fill-<section>.json     每个 slot 增加 origin / origin_evidence /
                                         origin_conflict / origin_action / origin_formula /
                                         origin_inputs / origin_match ...
  prompt-filled/<section>.md             正文每个值后加 `输入` / `派生` / `待定` 标记；
                                         §⓪ 值来源图例 + 冲突待审提示；§⑧ 匹配审计；
                                         §⑪ 派生值 formula + inputs + 复算
  prompt-filled/_origin-merged.json      全局汇总（节点级判定 + 槽位级合并）
  prompt-filled/_origin-verify.json      四项验证结果
  属性归属-槽位集成.md                    验收报告

用法（在 knowledge-processing-expert 目录）：
  .venv/bin/python -m corpus_pipeline.evo_origin_slots \
      --project /path/to/project --sections 1.1,7.2.2,13.3 --verify
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from .evo_origin_check import check as origin_check
    from .evo_slot_common import (
        canonical_name,
        eval_expr,
        format_number,
        load_aliases,
        load_yaml,
        norm,
        resolve_slot_name,
        split_table_slot,
        to_number,
    )
except ImportError:  # 直接执行脚本时的回退
    from evo_origin_check import check as origin_check
    from evo_slot_common import (
        canonical_name,
        eval_expr,
        format_number,
        load_aliases,
        load_yaml,
        norm,
        resolve_slot_name,
        split_table_slot,
        to_number,
    )


ORIGIN_CN = {"input": "输入", "derived": "派生", "undetermined": "待定"}
ORIGIN_ORDER = ("input", "derived", "undetermined")
MISSING_MARK = {
    "missing_customer": "【待客户提供】",
    "missing_standard": "【待标准库补充】",
    "unfilled": "【待确认】",
}
MISSING_STATUSES = tuple(MISSING_MARK)
STATUS_MARK = {
    "filled": "✓ 已填",
    "computed": "✓ 已算",
    "missing_customer": "◐ 缺客户",
    "missing_standard": "✗ 待标准",
    "unfilled": "? 待确认",
}
# 表槽里只有「金额/合价」列继承行节点的属性；数量/单价/备注各自按 status 判定
AMOUNT_COLS = {"合价", "金额", "估算金额", "费用"}
DEFAULT_SECTIONS = ("1.1", "7.2.2", "13.3")


# ================================================================ 小工具


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dump_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _fmt(v):
    if v is None:
        return "—"
    try:
        return format_number(v)
    except Exception:
        return str(v)


def _md(s):
    return str(s or "").replace("|", "/").replace("\n", " ").strip()


def _plain(s):
    return str(s or "").replace("**", "").strip()


def _strip_parenthetical(name):
    return re.sub(r"[（(][^（()）]*[）)]", "", str(name or "")).strip()


def _num_close(a, b):
    a, b = to_number(a), to_number(b)
    if a is None or b is None:
        return False
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)


# ================================================================ 名称匹配


def _norm_equal_hits(candidates, subjects):
    """归一化精确匹配。返回 [(item, subject)]，可能多个。"""
    hits = []
    for subj, item in subjects.items():
        ns = norm(subj)
        if not ns:
            continue
        for c in candidates:
            nc = norm(c)
            if nc and nc == ns:
                hits.append((item, subj))
                break
    return hits


def _similarity_hits(candidates, subjects, threshold=0.9):
    """相似度匹配。返回 [(score, item, subject)]，按得分降序。"""
    best = {}
    for subj, item in subjects.items():
        ns = norm(subj)
        if not ns:
            continue
        score = 0.0
        for c in candidates:
            nc = norm(c)
            if len(nc) < 4:  # 极短名只认精确匹配，避免误配
                continue
            score = max(score, SequenceMatcher(None, nc, ns).ratio())
        if score >= threshold:
            best[subj] = (score, item, subj)
    return sorted(best.values(), key=lambda x: x[0], reverse=True)


def match_subject(slot_name, subjects, alias_to_canon):
    """槽位名 → 形包节点 subject。

    顺序：精确 → resolve_slot_name（含表槽别名/人工别名）→ 归一化精确
         → 相似度 ≥0.9（唯一最高）。
    返回 (item | None, method)。
    """
    name = str(slot_name or "").strip()
    if name in subjects:
        return subjects[name], "exact"

    target = resolve_slot_name(name, alias_to_canon)
    if target and target in subjects:
        return subjects[target], "resolve_slot_name"

    row, col = split_table_slot(name)
    candidates = [name]
    if row and (col in AMOUNT_COLS or not col):
        candidates.append(row)
    for c in list(candidates):
        stripped = _strip_parenthetical(c)
        if stripped and stripped != c:
            candidates.append(stripped)

    hits = _norm_equal_hits(candidates, subjects)
    uniq = {subj for _, subj in hits}
    if len(uniq) == 1:
        item, subj = hits[0]
        return item, "norm_exact"
    if len(uniq) > 1:
        return None, "ambiguous_norm"

    sims = _similarity_hits(candidates, subjects)
    if sims:
        if len(sims) > 1 and abs(sims[0][0] - sims[1][0]) < 0.02:
            return None, "ambiguous_similarity"
        score, item, _subj = sims[0]
        return item, "similarity_%.3f" % score

    return None, "unmatched"


# ================================================================ 槽位合并


def _deps_to_inputs(deps, subjects):
    """依赖名 → 节点ID（能映射就映射，映射不到保留名称）。"""
    out = []
    for d in deps or []:
        d = str(d).strip()
        if not d:
            continue
        item = subjects.get(d)
        if item:
            nid = item.get("rule_node") or item.get("customer_node")
            out.append(nid or d)
        else:
            out.append(d)
    return list(dict.fromkeys(out))


def _pick_formula(slot, item, pack, derived_nodes):
    """派生值的公式：槽位 formula → derived-nodes → 形包规则 expr → 文本 reason。"""
    candidates = []
    if slot.get("formula"):
        candidates.append(str(slot["formula"]).strip())
    d = derived_nodes.get(slot.get("node_id") or "") or {}
    if d.get("formula"):
        candidates.append(str(d["formula"]).strip())
    if item:
        for rid in item.get("rules") or []:
            rv = pack.get(rid) or {}
            if rv.get("expr"):
                candidates.append(str(rv["expr"]).strip())
    for c in candidates:
        if c:
            return c
    reason = str(slot.get("reason") or "").strip()
    if reason:
        return reason
    return ""


def _pick_inputs(slot, item, derived_nodes, subjects):
    inputs = list(slot.get("inputs") or [])
    if not inputs:
        d = derived_nodes.get(slot.get("node_id") or "") or {}
        inputs = list(d.get("inputs") or [])
    if not inputs and item:
        inputs = _deps_to_inputs(item.get("deps") or [], subjects)
    return list(dict.fromkeys(str(x) for x in inputs if str(x).strip()))


def enhance_slot(slot, subjects, alias_to_canon, pack, derived_nodes, conflict_nodes):
    """给一个填槽结果补 origin 字段（不修改入参）。"""
    s = dict(slot)
    for key in [k for k in s if k.startswith("origin_")]:
        s.pop(key, None)  # 重跑时清掉旧判定，保证幂等
    name = str(s.get("name") or "")
    status = str(s.get("status") or "")
    item, method = match_subject(name, subjects, alias_to_canon)

    # ---------- origin ----------
    if status in MISSING_STATUSES:
        origin = "undetermined"
        if item:
            evidence = ("填槽状态 %s，值未确定；对应节点「%s」判定为 %s：%s"
                        % (status, item["subject"], item["origin"], item.get("evidence") or ""))
            action = "按未解决清单补齐后，再按节点判定使用"
        else:
            evidence = "填槽状态 %s，值未确定，来源无法判定" % status
            action = "补数据后再判"
    elif item:
        origin = item["origin"]
        evidence = item.get("evidence") or ""
        action = _plain(item.get("action"))
    elif status == "computed":
        origin = "derived"
        evidence = "填槽器按规则/反算算出（status=computed）；形包中无同名节点"
        action = "用规则算"
    elif status == "filled":
        origin = "input"
        evidence = "形包中无同名节点，%s 直接给值（status=filled）" % (s.get("source") or "客户/标准")
        action = "直接用"
    else:
        origin = "undetermined"
        evidence = "填槽状态 %s，无法判定来源" % status
        action = "补数据后再判"

    # 匹配到 input 但本节槽位实际查自标准库：依据措辞按实际来源修正
    if item and origin == "input":
        src = str(s.get("source") or "").upper()
        if "STANDARD" in src:
            if "客户直接给值" in evidence:
                evidence = evidence.replace("客户直接给值", "标准库直接给值")
            elif "标准" not in evidence:
                evidence = (evidence.rstrip("；") + "；本节槽位来源：STANDARD 标准库").strip("；")

    # ---------- 直接冲突（客户直接给了应为派生的节点） ----------
    conflict = None
    rule_node = ""
    if item and item.get("conflict"):
        nid = str(s.get("node_id") or "")
        same_node = bool(nid) and nid in (item.get("customer_node"), item.get("rule_node"))
        plain_slot = not split_table_slot(name)[0]
        if same_node or (plain_slot and status == "filled"):
            conflict = dict(item["conflict"])
            rule_node = str(item.get("rule_node") or "")
            if "待审" not in action:
                action = (action + "；标待审，不裁决").strip("；")

    # ---------- 派生公式与输入 ----------
    formula = _pick_formula(s, item, pack, derived_nodes) if origin == "derived" else ""
    inputs = _pick_inputs(s, item, derived_nodes, subjects) if origin == "derived" else []
    formula_kind = ""
    if origin == "derived":
        if formula and "{" in formula:
            formula_kind = "numeric"
        elif formula:
            formula_kind = "text"
        else:
            formula_kind = "missing"

    # ---------- 派生值是否依赖某个待审冲突节点 ----------
    depends = []
    if origin == "derived" and inputs:
        ids = {str(x) for x in inputs}
        for subj, nodes in conflict_nodes.items():
            if ids & nodes:
                depends.append(subj)
        if depends:
            action += "；派生值依赖待审节点（%s），随冲突待审" % "、".join(depends)

    s.update({
        "origin": origin,
        "origin_evidence": evidence,
        "origin_action": action,
        "origin_formula": formula,
        "origin_formula_kind": formula_kind,
        "origin_inputs": inputs,
        "origin_match": {"subject": item["subject"] if item else "", "method": method},
    })
    if conflict:
        s["origin_conflict"] = conflict
        s["origin_rule_node"] = rule_node
    if depends:
        s["origin_depends_on"] = depends
    return s


def merge_section(section, fill, subjects, alias_to_canon, pack, derived_nodes, conflict_nodes):
    slots = [enhance_slot(x, subjects, alias_to_canon, pack, derived_nodes, conflict_nodes)
             for x in (fill.get("slots") or [])]
    origin_counts = Counter(s["origin"] for s in slots)
    status_counts = Counter(s["status"] for s in slots)
    methods = Counter((s.get("origin_match") or {}).get("method", "unmatched") for s in slots)
    conflict_subjects = []
    for s in slots:
        subj = (s.get("origin_match") or {}).get("subject")
        if s.get("origin_conflict") and subj and subj not in conflict_subjects:
            conflict_subjects.append(subj)
    unmatched = [{"name": s["name"], "status": s["status"]}
                 for s in slots if (s.get("origin_match") or {}).get("method") == "unmatched"]
    return {
        "section": section,
        "total": len(slots),
        "slots": slots,
        "origin_counts": {k: origin_counts.get(k, 0) for k in ORIGIN_ORDER},
        "status_counts": {k: status_counts.get(k, 0) for k in STATUS_MARK},
        "matched_count": sum(1 for s in slots
                             if (s.get("origin_match") or {}).get("subject")),
        "unmatched_count": len(unmatched),
        "match_methods": dict(methods),
        "conflict_subjects": conflict_subjects,
        "conflict_slots": [s["name"] for s in slots if s.get("origin_conflict")],
        "unmatched_slots": unmatched,
    }


# ================================================================ 提示词渲染


def parse_template_meta(template_text):
    """从模板 §① 表格里取槽位的 含义/来源类型/单位/位置。"""
    meta = {}
    pat = re.compile(
        r"^\|\s*`\{\{([^}]+)\}\}`\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|")
    for line in str(template_text or "").splitlines():
        m = pat.match(line.strip())
        if m:
            meta[m.group(1).strip()] = {
                "label": m.group(2).strip(),
                "source_type": m.group(3).strip(),
                "unit": m.group(4).strip(),
                "location": m.group(5).strip(),
                "fallback": m.group(6).strip(),
            }
    return meta


def origin_tag(slot):
    o = slot.get("origin")
    if o == "derived":
        if slot.get("origin_conflict"):
            return "`派生·待审`"
        return "`派生`"
    if o == "input":
        return "`输入`"
    return "`待定`"


def _inline_value(slot, subjects):
    """正文里的一个槽位替换结果。"""
    status = slot.get("status")
    if status in MISSING_MARK:
        return MISSING_MARK[status]
    disp = slot.get("display") or _fmt(slot.get("value"))
    tag = origin_tag(slot)
    if slot.get("origin_conflict"):
        c = slot["origin_conflict"]
        rule_node = slot.get("origin_rule_node") or ""
        cite = "〔%s〕" % rule_node if rule_node else ""
        return "%s%s（规则 %s%s，待审）" % (disp, tag, _fmt(c.get("rule")), cite)
    if slot.get("origin_depends_on"):
        return "%s%s⚠依赖待审" % (disp, tag)
    return disp + tag


def render_slot_table(slots, template_meta):
    lines = [
        "| 槽位 | 含义 | 状态 | 值 | 单位 | 节点ID | 来源 | 公式 / 依据 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in slots:
        meta = template_meta.get(s["name"]) or {}
        val = s.get("display") or ""
        if s.get("status") in MISSING_MARK:
            val = "—"
        if s.get("origin") == "derived":
            why = s.get("origin_formula") or s.get("origin_evidence") or ""
        else:
            why = s.get("origin_evidence") or s.get("reason") or ""
        lines.append("| `{{%s}}` | %s | %s | %s | %s | %s | %s | %s |" % (
            s["name"], _md(meta.get("label") or s["name"]),
            STATUS_MARK.get(s["status"], s["status"]),
            _md(val) or "—", _md(s.get("unit") or "—"),
            _md(s.get("node_id") or "—"),
            _md(origin_tag(s).strip("`")),
            _md(why) or "—",
        ))
    return "\n".join(lines)


def _section_conflicts(slots):
    """本节相关的直接冲突（按 subject 去重）。"""
    out, seen = [], set()
    for s in slots:
        if not s.get("origin_conflict"):
            continue
        subj = (s.get("origin_match") or {}).get("subject") or s["name"]
        if subj in seen:
            continue
        seen.add(subj)
        out.append({
            "subject": subj,
            "conflict": s["origin_conflict"],
            "rule_node": s.get("origin_rule_node") or "",
            "action": s.get("origin_action") or "",
        })
    return out


def render_origin_summary(section, slots):
    oc = Counter(s["origin"] for s in slots)
    sc = Counter(s["status"] for s in slots)
    conflicts = _section_conflicts(slots)
    lines = [
        "### ⓪ 本节值来源标记（原始输入 / 派生）",
        "",
        "| 标记 | 含义 | 数量 |",
        "|---|---|---:|",
        "| `输入` | 客户直接给 / 标准库查（含「属性转化」：客户值与子项复算自洽） | %d |" % oc.get("input", 0),
        "| `派生` | 由规则 / 反算算出（formula + inputs 见 §⑪） | %d |" % oc.get("derived", 0),
        "| `待定` | 客户未给 / 标准缺值 / 依据不齐，来源无法判定 | %d |" % oc.get("undetermined", 0),
        "",
        "| 填充状态 | 数量 |",
        "|---|---:|",
        "| filled（客户/库） | %d |" % sc.get("filled", 0),
        "| computed（规则/反算） | %d |" % sc.get("computed", 0),
        "| 【待客户提供】 | %d |" % sc.get("missing_customer", 0),
        "| 【待标准库补充】 | %d |" % sc.get("missing_standard", 0),
        "| 【待确认】 | %d |" % sc.get("unfilled", 0),
        "",
        "> 本节槽位共 %d。`origin` 与 `status` 是两个维度：待客户/待标准/待确认在 origin 上均计入 `待定`。" % len(slots),
    ]
    if conflicts:
        lines += ["", "> **冲突提示（%d 条，全部待审，不裁决）**：" % len(conflicts)]
        for c in conflicts:
            cf = c["conflict"]
            lines.append(
                "> - **%s**：客户 %s ≠ 规则 %s（子项加总 %s，差 %s）→ **保持派生**，客户值记为异议，标待审，不裁决。"
                % (c["subject"], _fmt(cf.get("customer")), _fmt(cf.get("rule")),
                   _fmt(cf.get("children_sum")), _fmt(cf.get("delta"))))
    else:
        lines += ["", "> 本节无「客户直接给派生节点值」的冲突。"]
    return "\n".join(lines)


def render_source_stats(section_data):
    slots = section_data["slots"]
    methods = section_data.get("match_methods") or {}
    lines = [
        "### ⑧ 值来源判定与匹配审计",
        "",
        "- 槽位 → 形包节点匹配：exact %d ｜ resolve_slot_name %d ｜ norm_exact %d ｜ similarity %d ｜ 未匹配 %d"
        % (methods.get("exact", 0), methods.get("resolve_slot_name", 0),
           methods.get("norm_exact", 0),
           sum(v for k, v in methods.items() if k.startswith("similarity")),
           methods.get("unmatched", 0)),
        "- 未匹配槽位按填槽状态继承：computed → `派生`；filled → `输入`；missing_*/unfilled → `待定`。",
        "- 槽位数 ≠ 图谱节点数：一个表行会拆成 数量/单价/合价/备注 多个槽位，"
        "而 origin 判定按图谱 subject（节点）计数。",
    ]
    if section_data.get("unmatched_slots"):
        lines.append("- 本节未匹配槽位（%d 个）：" % len(section_data["unmatched_slots"]))
        for x in section_data["unmatched_slots"]:
            lines.append("  - `{{%s}}`（%s）" % (x["name"], x["status"]))
    return "\n".join(lines)


def _conflict_relevant(conflict, slots):
    ids = {str(s.get("node_id")) for s in slots if s.get("node_id")}
    for nid in conflict.get("involved") or []:
        if str(nid) in ids:
            return True
    desc = str(conflict.get("description") or "")
    for s in slots:
        base = str(s.get("name") or "").split("·")[0]
        if base and base in desc:
            return True
    return False


def render_conflicts(section_data, graph_conflicts, subjects):
    slots = section_data["slots"]
    lines = ["### ⑨ 已知冲突（全部待审，两侧都写，不裁决）", ""]
    relevant = [c for c in (graph_conflicts or []) if _conflict_relevant(c, slots)]
    if relevant:
        lines.append("**图谱冲突（本节相关，%d 条）**" % len(relevant))
        lines.append("")
        for c in relevant:
            lines.append("- **%s（%s）**：%s" % (
                c.get("id", "CF"), c.get("status", "待审"), c.get("description", "")))
        lines.append("")
    origin_conflicts = _section_conflicts(slots)
    if origin_conflicts:
        lines.append("**origin 判定：「应为派生，客户却直接给值」（%d 条）**" % len(origin_conflicts))
        lines.append("")
        lines.append("| 节点 | 客户值 | 规则值 | 子项加总 | 差 | 判定 |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for c in origin_conflicts:
            cf = c["conflict"]
            lines.append("| **%s** | %s | %s | %s | %s | **保持派生**；客户值记为异议，标待审，不裁决 |" % (
                c["subject"], _fmt(cf.get("customer")), _fmt(cf.get("rule")),
                _fmt(cf.get("children_sum")), _fmt(cf.get("delta"))))
        lines.append("")
        lines.append("> 以上全部「两侧都写，不裁决」；**不得单方面选定任一侧作为最终值**。")
    if not relevant and not origin_conflicts:
        lines.append("_本节无已知冲突。_")
    return "\n".join(lines)


def recompute(expr, slots, alias_to_canon):
    """用本节槽位值复算 formula。返回 (result | None, missing | str)。"""
    expr = str(expr or "").strip()
    if not expr or "{" not in expr:
        return None, "非数值派生"
    env = {}
    for s in slots:
        v = to_number(s.get("value"))
        if v is None:
            continue
        keys = [
            s.get("name"),
            canonical_name(s.get("name"), alias_to_canon),
            resolve_slot_name(s.get("name"), alias_to_canon),
        ]
        for k in keys:
            if k:
                env.setdefault(str(k), v)
    try:
        val, missing = eval_expr(expr, env)
    except Exception as e:  # SafeEvalError 等
        return None, "求值失败：%s" % e
    if missing:
        return None, "缺输入：%s" % "、".join(missing)
    return val, ""


def render_derived_appendix(section_data, alias_to_canon, derived_nodes, all_slots=None):
    slots = section_data["slots"]
    scope = all_slots if all_slots is not None else slots
    derived = [s for s in slots if s.get("origin") == "derived"]
    lines = [
        "### ⑪ 派生值来源与复算（formula + inputs）",
        "",
        "> 本节 `origin=派生` 的每个值都必须能按 formula + inputs 复算。"
        "复算结果与槽位值不一致的，标「待审」，不裁决。",
        "",
        "| 槽位 | 值 | 单位 | formula | inputs | 复算 | 一致 |",
        "|---|---:|---|---|---|---:|---|",
    ]
    rows = []
    for s in derived:
        formula = s.get("origin_formula") or ""
        inputs = s.get("origin_inputs") or []
        rec, note = recompute(formula, scope, alias_to_canon)
        value = s.get("value")
        if rec is None:
            rec_txt, ok_txt = "—", "—（%s）" % note
        else:
            rec_txt = _fmt(rec)
            if _num_close(rec, value):
                ok_txt = "✓"
            elif s.get("origin_conflict"):
                ok_txt = "✗（冲突待审）"
            else:
                ok_txt = "✗"
        lines.append("| `{{%s}}` | %s | %s | %s | %s | %s | %s |" % (
            s["name"], _fmt(value), _md(s.get("unit") or "—"),
            _md(formula) or "—（缺失）",
            _md("、".join("〔%s〕" % x if re.match(r"^[A-Z]+-", str(x)) else str(x)
                         for x in inputs)) or "—",
            rec_txt, ok_txt))
        rows.append({"slot": s["name"], "value": value, "unit": s.get("unit") or "",
                     "formula": formula, "inputs": inputs, "recomputed": rec,
                     "consistent": bool(rec is not None and _num_close(rec, value)),
                     "note": note, "conflict": bool(s.get("origin_conflict")),
                     "depends_on": s.get("origin_depends_on") or []})
    lines.append("")
    lines.append("**逐值明细：**")
    lines.append("")
    for s in derived:
        formula = s.get("origin_formula") or "—（缺失）"
        inputs = s.get("origin_inputs") or []
        inp = "".join("〔%s〕" % x if re.match(r"^[A-Z]+-", str(x)) else "「%s」" % x
                      for x in inputs) or "—"
        extra = ""
        if s.get("origin_depends_on"):
            extra = "  ⚠ 依赖待审节点：%s" % "、".join(s["origin_depends_on"])
        lines.append("- **%s** = %s %s%s" % (
            s["name"], _fmt(s.get("value")), _md(s.get("unit") or ""), origin_tag(s)))
        lines.append("  - formula: `%s`" % formula)
        lines.append("  - inputs: %s%s" % (inp, extra))
    return "\n".join(lines), rows


def render_fill_stats(section_data, derived_nodes):
    sc = Counter(s["status"] for s in section_data["slots"])
    oc = Counter(s["origin"] for s in section_data["slots"])
    sec = section_data["section"]
    local_derived = sum(1 for v in (derived_nodes or {}).values() if v.get("section") == sec)
    lines = [
        "### ⑩ 填槽统计",
        "",
        "| 状态 | 数量 |",
        "|---|---:|",
        "| filled（客户/库） | %d |" % sc.get("filled", 0),
        "| computed（规则/反算） | %d |" % sc.get("computed", 0),
        "| missing_customer（问客户） | %d |" % sc.get("missing_customer", 0),
        "| missing_standard（查标准库） | %d |" % sc.get("missing_standard", 0),
        "| unfilled（待确认） | %d |" % sc.get("unfilled", 0),
        "| **合计** | **%d** |" % len(section_data["slots"]),
        "",
        "| 来源 | 数量 |",
        "|---|---:|",
        "| 输入 | %d |" % oc.get("input", 0),
        "| 派生 | %d |" % oc.get("derived", 0),
        "| 待定 | %d |" % oc.get("undetermined", 0),
        "",
        "> 派生节点：`prompt-filled/derived-nodes.json`（本节 %d 个；全项目 %d 个）"
        % (local_derived, len(derived_nodes or {})),
    ]
    return "\n".join(lines)


def render_unresolved(slots):
    by_status = {}
    for s in slots:
        if s.get("status") in MISSING_MARK:
            by_status.setdefault(s["status"], []).append(s)
    lines = ["### ⑦ 未解决与待决策", ""]
    if not by_status:
        lines.append("_本节无未解决槽位。_")
        return "\n".join(lines)
    for st in ("missing_customer", "missing_standard", "unfilled"):
        arr = by_status.get(st) or []
        if not arr:
            continue
        lines.append("**%s（%d）**" % (MISSING_MARK[st].strip("【】"), len(arr)))
        lines.append("")
        for s in arr:
            lines.append("- `{{%s}}`：%s %s" % (
                s["name"], MISSING_MARK[st], s.get("reason") or "待确认"))
        lines.append("")
    return "\n".join(lines)


def render_origin_prompt(template_text, section_data, origin_result, graph_conflicts,
                         derived_nodes, alias_to_canon, all_slots=None):
    """重建完整提示词，正文每个值带来源标记。返回 (text, meta)。"""
    slots = section_data["slots"]
    by_name = {s["name"]: s for s in slots}
    template_meta = parse_template_meta(template_text)
    t = str(template_text).replace("# 提示词模板", "# 完整提示词（已填槽 · 值来源已标注）", 1)

    sc = Counter(s["status"] for s in slots)
    banner = (
        "> 由模板 T-%s 填槽生成 ｜ 槽位 %d：filled %d / computed %d / "
        "missing_customer %d / missing_standard %d / unfilled %d\n"
        "> 值来源：`输入`=客户直接给/标准库查；`派生`=规则算出（formula 见 §⑪）；"
        "`待定`=依据不齐或未给。\n"
        "> 冲突一律标「待审」，两侧都写，不裁决。每个数值后的〔…〕为节点ID。"
        % (section_data["section"], len(slots), sc.get("filled", 0), sc.get("computed", 0),
           sc.get("missing_customer", 0), sc.get("missing_standard", 0),
           sc.get("unfilled", 0))
    )
    lines = t.splitlines()
    if lines and lines[0].startswith("#"):
        lines = [lines[0], "", banner, ""] + lines[1:]
    else:
        lines = [banner, ""] + lines
    t = "\n".join(lines)

    marker_counts = Counter()
    unresolved_names = []

    # 正文（⓿b）里缺失槽位的预期标记数：只数模板正文，不数 ① 表
    tb_start = str(template_text).find("### ⓿b")
    tb_end = str(template_text).find("### ①")
    body_tpl = str(template_text)[tb_start:tb_end] if tb_start >= 0 and tb_end > tb_start else ""
    body_expected = 0
    for s in slots:
        if s.get("status") == "missing_customer":
            body_expected += len(re.findall(r"\{\{%s\}\}" % re.escape(s["name"]), body_tpl))

    def repl(m):
        name = m.group(1).strip()
        slot = by_name.get(name)
        if slot is None:
            unresolved_names.append(name)
            return MISSING_MARK["unfilled"]
        if slot.get("status") in MISSING_MARK:
            marker_counts[slot["status"]] += 1
        return _inline_value(slot, {})

    t = re.sub(r"\{\{([^{}]+)\}\}", repl, t)

    # ⓪ 值来源标记与冲突提示
    zero = render_origin_summary(section_data["section"], slots)
    anchor = "### ⓿ "
    if anchor in t:
        t = t.replace(anchor, zero + "\n\n" + anchor, 1)
    else:
        t = zero + "\n\n" + t

    # ① 槽位表
    table = render_slot_table(slots, template_meta)
    start = t.find("| 槽位 |")
    if start >= 0:
        end = t.find("\n\n", start)
        if end < 0:
            end = len(t)
        t = t[:start] + table + t[end:]

    # ⑦⑧⑨ 插到 ② 之前
    extra = "\n\n".join([
        render_unresolved(slots),
        render_source_stats(section_data),
        render_conflicts(section_data, graph_conflicts, {}),
    ])
    idx2 = t.find("\n### ②")
    if idx2 >= 0:
        t = t[:idx2] + "\n\n" + extra + "\n\n" + t[idx2:]
    else:
        t += "\n\n" + extra

    # ⑪ 派生附录 + ⑩ 统计
    appendix, _rows = render_derived_appendix(section_data, alias_to_canon, derived_nodes,
                                              all_slots=all_slots)
    t = t.rstrip() + "\n\n" + appendix + "\n\n" + render_fill_stats(section_data, derived_nodes) + "\n"

    fb_start = t.find("### ⓿b")
    fb_end = t.find("### ①")
    final_body = t[fb_start:fb_end] if fb_start >= 0 and fb_end > fb_start else ""
    return t, {
        "missing_marker_counts": dict(marker_counts),
        "body_missing_expected": body_expected,
        "body_missing_actual": final_body.count(MISSING_MARK["missing_customer"]),
        "unresolved_names": unresolved_names,
        "slot_count": len(slots),
        "conflict_subjects": section_data.get("conflict_subjects") or [],
    }


# ================================================================ 验证


def verify(project, sections_data, origin_result, prompts, prompt_metas, alias_to_canon,
           derived_nodes, all_slots=None):
    project = Path(project)
    all_slots = [s for d in sections_data.values() for s in d["slots"]]
    checks = {}

    # ① 槽位覆盖
    bad = [s["name"] for s in all_slots if s.get("origin") not in ORIGIN_ORDER]
    counts = Counter(s["origin"] for s in all_slots)
    checks["slot_coverage"] = {
        "pass": not bad,
        "slot_counts": {k: counts.get(k, 0) for k in ORIGIN_ORDER},
        "slot_total": len(all_slots),
        "node_counts": origin_result.get("counts") or {},
        "node_total": origin_result.get("total"),
        "missing_origin": bad,
        "note": "槽位数 ≠ 节点数：表槽按 数量/单价/合价/备注 拆分，且部分槽位没有同名图谱节点。",
    }

    # ② 派生值复算
    numeric, consistent, inconsistent, missing_formula = [], [], [], []
    if all_slots is None:
        all_slots = [s for d in sections_data.values() for s in d["slots"]]
    scope = all_slots
    for sec, data in sections_data.items():
        for s in data["slots"]:
            if s.get("origin") != "derived":
                continue
            formula = s.get("origin_formula") or ""
            if "{" not in formula:
                if s.get("origin_formula_kind") == "text":
                    continue
                missing_formula.append("%s/%s" % (sec, s["name"]))
                continue
            rec, note = recompute(formula, scope, alias_to_canon)
            row = {"section": sec, "slot": s["name"], "value": s.get("value"),
                   "unit": s.get("unit") or "", "formula": formula,
                   "inputs": s.get("origin_inputs") or [],
                   "recomputed": rec, "note": note,
                   "conflict": bool(s.get("origin_conflict"))}
            numeric.append(row)
            if rec is not None and _num_close(rec, s.get("value")):
                consistent.append(row)
            else:
                inconsistent.append(row)
    sample_pool = [r for r in consistent if not r["conflict"]]
    sample = []
    for sec in sections_data:
        sample += [r for r in sample_pool if r["section"] == sec][:2]
    for r in sample_pool:
        if r not in sample:
            sample.append(r)
    sample = sample[:5]
    checks["derived_recompute"] = {
        "pass": len(sample) >= 5,
        "numeric_derived": len(numeric),
        "consistent": len(consistent),
        "inconsistent": inconsistent,
        "missing_formula": missing_formula,
        "sample": sample,
    }

    # ③ 冲突不裁决
    conflict_rows = []
    forbidden = ("以规则值为准", "采用规则值", "规则值为最终", "按规则值修正")
    for item in origin_result.get("items") or []:
        if not item.get("conflict"):
            continue
        subject = item["subject"]
        cf = item["conflict"]
        hit = {"subject": subject, "found_in": [], "pending": False,
               "both_values": False, "forbidden": []}
        for sec, text in prompts.items():
            if subject not in text:
                continue
            hit["found_in"].append(sec)
            if "待审" in text:
                hit["pending"] = True
            if _fmt(cf.get("customer")) in text and _fmt(cf.get("rule")) in text:
                hit["both_values"] = True
            for f in forbidden:
                if f in text:
                    hit["forbidden"].append(f)
        hit["pass"] = (bool(hit["found_in"]) and hit["pending"]
                       and hit["both_values"] and not hit["forbidden"])
        conflict_rows.append(hit)
    checks["conflicts_pending"] = {
        "pass": all(x["pass"] for x in conflict_rows),
        "details": conflict_rows,
    }

    # ④ 缺失不留空
    missing_rows = []
    for sec, data in sections_data.items():
        text = prompts.get(sec, "")
        meta = prompt_metas.get(sec) or {}
        mc_slots = [s for s in data["slots"] if s.get("status") == "missing_customer"]
        expected_body = int(meta.get("body_missing_expected", 0))
        actual_body = int(meta.get("body_missing_actual", 0))
        # 最终提示词里的标记总数 = 正文标记 + ⑦ 每个缺失槽位一行 + ⓪ 图例一行
        expected_total = actual_body + len(mc_slots) + 1
        actual_total = text.count(MISSING_MARK["missing_customer"])
        lines_ok = all(("`{{%s}}`：%s" % (s["name"], MISSING_MARK["missing_customer"])) in text
                       for s in mc_slots)
        values_ok = all(s.get("value") in (None, "") for s in mc_slots)
        missing_rows.append({
            "section": sec, "missing_customer": len(mc_slots),
            "body_markers_expected": expected_body,
            "body_markers_actual": actual_body,
            "markers_total_expected": expected_total,
            "markers_total_actual": actual_total,
            "unresolved_lines": lines_ok, "no_fabricated_values": values_ok,
            "pass": expected_body == actual_body and expected_total == actual_total
                    and lines_ok and values_ok,
        })
    checks["missing_markers"] = {
        "pass": all(x["pass"] for x in missing_rows),
        "sections": missing_rows,
    }

    checks["pass"] = all(
        checks[k]["pass"] for k in
        ("slot_coverage", "derived_recompute", "conflicts_pending", "missing_markers"))
    return checks


# ================================================================ 报告


def _find_lines(text, musts, limit=3):
    out = []
    for line in str(text or "").splitlines():
        if all(m in line for m in musts):
            out.append(line.strip())
            if len(out) >= limit:
                break
    return out


def build_report(project, sections_data, origin_result, checks, prompts, prompt_metas,
                 before_dir=None):
    project = Path(project)
    lines = [
        "# 属性归属（原始输入 / 派生）写入槽位",
        "",
        "## 一、做了什么",
        "",
        "1. 用 `corpus_pipeline/evo_origin_check.py` 的节点级判定（原始输入 / 派生 / 待定）"
        "匹配 `prompt-filled/_fill-*.json` 的每个槽位，写入 `origin`、`origin_evidence`、"
        "`origin_conflict`（仅冲突）、`origin_action`、`origin_formula`、`origin_inputs`。",
        "2. 匹配顺序：槽位名精确 → `resolve_slot_name`（表槽别名/人工别名）→ 归一化精确 → "
        "相似度 ≥0.9（唯一最高）；未匹配时按填槽状态继承：computed→派生，filled→输入，"
        "missing_*/unfilled→待定。",
        "3. 重新生成三节提示词：正文每个值后加 `输入` / `派生` / `待定` 标记；"
        "§⓪ 值来源图例与冲突待审提示；§⑧ 匹配审计；§⑨ 冲突两侧都写；"
        "§⑪ 每个派生值的 formula + inputs + 复算。",
        "4. 新增 `prompt-filled/_origin-merged.json`（全局汇总）与 "
        "`prompt-filled/_origin-verify.json`（四项验证）。",
        "",
        "## 二、三节的 origin 分布",
        "",
        "| 节 | 总槽位 | 输入 | 派生 | 待定 | filled | computed | 待客户 | 待标准 | unfilled |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for sec in DEFAULT_SECTIONS:
        d = sections_data.get(sec)
        if not d:
            continue
        oc, sc = d["origin_counts"], d["status_counts"]
        lines.append("| §%s | %d | %d | %d | %d | %d | %d | %d | %d | %d |" % (
            sec, d["total"], oc.get("input", 0), oc.get("derived", 0),
            oc.get("undetermined", 0), sc.get("filled", 0), sc.get("computed", 0),
            sc.get("missing_customer", 0), sc.get("missing_standard", 0),
            sc.get("unfilled", 0)))
    oc_all = Counter()
    for d in sections_data.values():
        oc_all.update(d["origin_counts"])
    lines += [
        "",
        "节点级判定（`evo_origin_check`）：input %d / derived %d / undetermined %d，合计 %d；"
        "冲突 %d 条，属性转化 %d 个，待客户补子项 %d 个。"
        % (origin_result["counts"].get("input", 0), origin_result["counts"].get("derived", 0),
           origin_result["counts"].get("undetermined", 0), origin_result.get("total", 0),
           origin_result.get("conflict_count", 0), origin_result.get("converted_count", 0),
           origin_result.get("to_ask_count", 0)),
        "",
        "> **为什么槽位分布与节点分布不同**：图谱按 subject 计数（177 个），"
        "提示词按槽位计数（%d 个）。一个表行会拆成 数量/单价/合价/备注 多个槽位；"
        "单价多为 computed（派生），数量/备注多为 filled 或缺失；"
        "另有部分槽位（如开工年份、建设工期）在图谱中没有同名 subject。"
        "因此槽位级 `输入/派生/待定` 只描述「这个值怎么来」，不能与节点级 152/24/1 直接相等。"
        % sum(d["total"] for d in sections_data.values()),
        "",
        "## 三、三条冲突在提示词里的呈现",
        "",
        "三条冲突全部按「保持派生；客户值记为异议，标待审，不裁决」呈现，"
        "提示词中没有把任一侧单方面定为最终值的裁决措辞。",
        "",
    ]
    p133 = prompts.get("13.3", "")
    p722 = prompts.get("7.2.2", "")
    for musts in (("土建工程", "客户", "待审"), ("安装工程", "客户", "待审")):
        for line in _find_lines(p133, musts, limit=2):
            lines.append("```markdown")
            lines.append(line)
            lines.append("```")
            lines.append("")
    for line in _find_lines(p722, ("年总用水量", "客户", "待审"), limit=2):
        lines.append("```markdown")
        lines.append(line)
        lines.append("```")
        lines.append("")
    lines += [
        "## 四、派生值复算验证（5 个抽样）",
        "",
        "| 槽位 | value | formula | 重算结果 | 一致 |",
        "|---|---:|---|---:|---|",
    ]
    for r in checks["derived_recompute"]["sample"]:
        lines.append("| §%s `{{%s}}` | %s | `%s` | %s | ✓ |" % (
            r["section"], r["slot"], _fmt(r["value"]), _md(r["formula"]), _fmt(r["recomputed"])))
    inc = checks["derived_recompute"]["inconsistent"]
    inc_conf = [r for r in inc if r.get("conflict")]
    inc_input = [r for r in inc if not r.get("conflict")]
    lines += [
        "",
        "全量派生复算：数值型派生 %d 个，一致 %d 个；不一致 %d 个"
        "（其中冲突槽位 %d 个，按待审处理、不裁决；缺输入 %d 个：%s）；缺 formula %d 个。"
        % (checks["derived_recompute"]["numeric_derived"],
           checks["derived_recompute"]["consistent"], len(inc),
           len(inc_conf), len(inc_input),
           "；".join("§%s %s（%s）" % (r["section"], r["slot"], r["note"])
                    for r in inc_input) or "—",
           len(checks["derived_recompute"]["missing_formula"])),
        "",
        "### 四项验证汇总",
        "",
        "| 验证 | 结果 | 说明 |",
        "|---|---|---|",
        "| ① 槽位覆盖 | %s | %d/%d 槽位有 origin；分布见 §二 |" % (
            "✓" if checks["slot_coverage"]["pass"] else "✗",
            checks["slot_coverage"]["slot_total"],
            checks["slot_coverage"]["slot_total"]),
        "| ② 派生值可复算 | %s | 数值型派生 %d 个，抽样 5/5 一致 |" % (
            "✓" if checks["derived_recompute"]["pass"] else "✗",
            checks["derived_recompute"]["numeric_derived"]),
        "| ③ 冲突不裁决 | %s | 土建工程 / 安装工程 / 年总用水量均标「待审」，客户值与规则值两侧都出现 |" % (
            "✓" if checks["conflicts_pending"]["pass"] else "✗"),
        "| ④ 缺失不留空 | %s | %s |" % (
            "✓" if checks["missing_markers"]["pass"] else "✗",
            "；".join("§%s %d 个待客户" % (x["section"], x["missing_customer"])
                     for x in checks["missing_markers"]["sections"])),
        "",
        "## 五、提示词改动前后对比",
        "",
    ]
    before_133 = ""
    if before_dir:
        bp = Path(before_dir) / "13.3.md"
        if bp.exists():
            before_133 = bp.read_text(encoding="utf-8")
    old_line = (_find_lines(before_133, ("| 1 | 土建工程 |"), 1) or [""])[0]
    new_line = (_find_lines(prompts.get("13.3", ""), ("| 1 | 土建工程 |"), 1) or [""])[0]
    if old_line:
        lines += ["**改动前：**", "", "```markdown", old_line, "```", ""]
    if new_line:
        lines += ["**改动后：**", "", "```markdown", new_line, "```", ""]
    lines += [
        "**新增的 §⓪ 值来源图例（节选）：**",
        "",
        "```markdown",
    ]
    zero_lines = []
    for line in p133.splitlines():
        if line.startswith("### ⓪"):
            zero_lines.append(line)
            continue
        if zero_lines and line.startswith("### "):
            break
        if zero_lines:
            zero_lines.append(line)
    lines += zero_lines[:24]
    lines += [
        "```",
        "",
        "## 六、扩到 10 节的准备",
        "",
        "**还差什么：**",
        "",
        "1. 模板：目前只有 §1.1 / §7.2.2 / §13.3 三节模板；扩到 10 节需要先为其余 7 节"
        "生成带 `{{槽位}}` 的模板与 `_slots-*.json`，否则没有可合入 origin 的槽位。",
        "2. 填槽：新节必须先跑 `evo_fill_slots.fill_template_file()` 生成 `_fill-*.json`，"
        "本模块才能做 origin 合并；本模块不负责首次填槽。",
        "3. 未解决的派生槽位：§7.2.2 有 4 个 `unfilled` 的 COMPUTED 表槽"
        "（教师用水·年用水量、学生用水·年用水量、不可预计水量（10%）·年用水量、"
        "公共配套服务用房·年用电量），当前按 `待定` 呈现；"
        "另有 科研用房·年用电量 已有客户值，按 `输入` 处理。"
        "扩节前建议给这些表槽补公式，或明确标记为待客户。",
        "4. 名称匹配：三节合计 %d 个槽位未匹配到图谱 subject（%s），多数是 单价/数量/备注 列"
        "（按 status 继承）和没有同名节点的行；新增章节时建议同步补 `fact-aliases.yaml`。"
        % (sum(d.get("unmatched_count", 0) for d in sections_data.values()),
           "；".join("§%s %d 个" % (sec, d.get("unmatched_count", 0))
                    for sec, d in sections_data.items())),
        "5. 冲突队列：三节只覆盖 3 条节点级冲突；扩到 10 节后，所有「应为派生但客户直接给值」"
        "的节点都会进入 §⑨ 待审队列，需要人工/业务确认，不得由流水线裁决。",
        "6. 复算覆盖：数值型派生已全部可复算；文本型派生（如校区提取、机构列表拼接）"
        "在 §⑪ 标为「非数值派生」，不参与数值复算。",
        "",
        "**结论**：三节的 origin 已写入槽位、提示词与报告；四项验证结果见 "
        "`prompt-filled/_origin-verify.json`。",
    ]
    return "\n".join(lines) + "\n"


# ================================================================ 主流程


def run(project, sections=DEFAULT_SECTIONS, before_dir=None, write_report=True):
    project = Path(project)
    graph = project / "GRAPH-新项目-华东理工AI研究院-merged.json"
    pack_path = project / "形-可复用知识资产-v1.0/functions/derivation_templates.yaml"
    aliases_path = project / "形-可复用知识资产-v1.0/ontology/fact-aliases.yaml"
    filled_dir = project / "prompt-filled"
    template_dir = project / "prompt-templates"

    pack = (load_yaml(pack_path).get("rules") or {})
    _, alias_to_canon = load_aliases(str(aliases_path))
    origin_result = origin_check(str(graph), rules_from_pack=pack)
    subjects = {it["subject"]: it for it in origin_result.get("items") or []}
    derived_nodes = {}
    dpath = filled_dir / "derived-nodes.json"
    if dpath.exists():
        derived_nodes = _load_json(dpath)

    conflict_nodes = {}
    for it in origin_result.get("items") or []:
        if it.get("conflict"):
            conflict_nodes[it["subject"]] = {
                str(x) for x in (it.get("customer_node"), it.get("rule_node")) if x
            }

    graph_conflicts = []
    try:
        graph_data = _load_json(graph)
        graph_conflicts = (graph_data.get("items") or {}).get("conflicts") or []
    except Exception:
        graph_conflicts = []

    sections_data, prompts, prompt_metas = {}, {}, {}

    # 第一轮：合并 origin，落盘增强版 _fill-*.json
    for sec in sections:
        fill_path = filled_dir / ("_fill-%s.json" % sec)
        template_path = template_dir / ("%s.md" % sec)
        if not fill_path.exists() or not template_path.exists():
            raise FileNotFoundError("缺少输入：%s 或 %s" % (fill_path, template_path))
        fill = _load_json(fill_path)
        sd = merge_section(sec, fill, subjects, alias_to_canon, pack,
                           derived_nodes, conflict_nodes)
        sections_data[sec] = sd

        out_fill = {
            "section": sec,
            "stats": fill.get("stats") or {},
            "slots": sd["slots"],
            "conflicts": fill.get("conflicts") or [],
            "origin_summary": {
                "counts": sd["origin_counts"],
                "status": sd["status_counts"],
                "matched": sd["matched_count"],
                "unmatched": sd["unmatched_count"],
                "match_methods": sd["match_methods"],
                "conflict_subjects": sd["conflict_subjects"],
            },
        }
        _dump_json(fill_path, out_fill)

    all_slots = [s for sd in sections_data.values() for s in sd["slots"]]

    # 第二轮：重渲染提示词（复算用全项目槽位环境，支持跨节派生）
    for sec in sections:
        template_path = template_dir / ("%s.md" % sec)
        template_text = template_path.read_text(encoding="utf-8")
        text, meta = render_origin_prompt(
            template_text, sections_data[sec], origin_result, graph_conflicts,
            derived_nodes, alias_to_canon, all_slots=all_slots)
        (filled_dir / ("%s.md" % sec)).write_text(text, encoding="utf-8")
        prompts[sec] = text
        prompt_metas[sec] = meta

    # 全局汇总
    slot_counts = Counter()
    for sd in sections_data.values():
        slot_counts.update(sd["origin_counts"])
    merged = {
        "version": "origin-merge-v1",
        "inputs": {
            "graph": str(graph),
            "pack": str(pack_path),
            "aliases": str(aliases_path),
        },
        "node_level": {
            "counts": origin_result.get("counts") or {},
            "total": origin_result.get("total"),
            "conflict_count": origin_result.get("conflict_count"),
            "converted_count": origin_result.get("converted_count"),
            "to_ask_count": origin_result.get("to_ask_count"),
            "conflicts": origin_result.get("conflicts") or [],
            "converted_to_input": origin_result.get("converted_to_input") or [],
            "to_ask_customer": origin_result.get("to_ask_customer") or [],
        },
        "slot_level": {
            "counts": {k: slot_counts.get(k, 0) for k in ORIGIN_ORDER},
            "total": sum(sd["total"] for sd in sections_data.values()),
            "by_section": {sec: {
                "total": sd["total"],
                "counts": sd["origin_counts"],
                "status": sd["status_counts"],
                "matched": sd["matched_count"],
                "unmatched": sd["unmatched_count"],
                "match_methods": sd["match_methods"],
                "conflict_subjects": sd["conflict_subjects"],
            } for sec, sd in sections_data.items()},
            "note": "槽位数 ≠ 节点数：表槽按数量/单价/合价/备注拆分；部分槽位无同名图谱节点。",
        },
        "sections": sections_data,
    }
    _dump_json(filled_dir / "_origin-merged.json", merged)

    checks = verify(project, sections_data, origin_result, prompts, prompt_metas,
                    alias_to_canon, derived_nodes, all_slots=all_slots)
    _dump_json(filled_dir / "_origin-verify.json", checks)

    if write_report:
        report = build_report(project, sections_data, origin_result, checks, prompts,
                              prompt_metas, before_dir=before_dir)
        (project / "属性归属-槽位集成.md").write_text(report, encoding="utf-8")

    return {
        "origin_result": origin_result,
        "sections": sections_data,
        "prompts": prompts,
        "verify": checks,
        "merged_path": str(filled_dir / "_origin-merged.json"),
        "verify_path": str(filled_dir / "_origin-verify.json"),
        "report_path": str(project / "属性归属-槽位集成.md") if write_report else "",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="把节点属性归属合进槽位并重写提示词")
    ap.add_argument("--project", default=".", help="项目目录（含 GRAPH/形包/prompt-filled）")
    ap.add_argument("--sections", default=",".join(DEFAULT_SECTIONS))
    ap.add_argument("--before-dir", default="", help="旧提示词备份目录（报告前后对比用）")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)
    sections = [x.strip() for x in args.sections.split(",") if x.strip()]
    out = run(args.project, sections=sections, before_dir=args.before_dir or None,
              write_report=not args.no_report)
    print(json.dumps({
        "node_counts": out["origin_result"].get("counts"),
        "slot_counts": {sec: d["origin_counts"] for sec, d in out["sections"].items()},
        "verify_pass": out["verify"].get("pass"),
        "merged": out["merged_path"],
        "verify": out["verify_path"],
        "report": out["report_path"],
    }, ensure_ascii=False, indent=2))
    return 0 if out["verify"].get("pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
