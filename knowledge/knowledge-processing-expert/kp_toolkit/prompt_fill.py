#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""节点填充模型：把「提示词里的节点值」变成可动态重算的活数据。

三件事（全部确定性，零 LLM）：
1. classify()  给每个节点定填充模式（客户输入 / 推演结果 / 规范固定 / 可检索补全 / 结构性无值）
                与约束强度（硬约束 / 软约束）。
2. recompute() 按 graph/rules.yaml 的 expr + deps 重算推演节点；缺输入按 guard 置 undefined；
                与图中已存值比对，给出 stale（值已过期）清单。
3. render()    把某节提示词里的取值行按其节点现值重渲染，逐行标 [硬|客户输入] / [硬|推演 R-x] /
                [软|检索·状态] / [硬|缺值→留白]，并给出该节的检索任务（软约束缺值才触发）。

设计约束：
- 不猜值：软约束缺值 → 出「检索任务」；硬约束缺值 → 出「缺口」，正文留白。
- 不改写原提示词的叙述句：只重渲染取值行、函数段与冲突标注。
- 同输入同输出。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

NODE_ID_RE = re.compile(r"(N-[0-9a-f]{12})")
VALUE_LINE_RE = re.compile(r"^\s*·\s")

VALUE_KINDS = {"fact", "quantity", "quantity_tolerance", "spec", "grade"}
HARD_EFFECT = {"A（强制性）", "B（强）"}
SOFT_EFFECT = {"C（推荐）", "D（资料性）", "待核"}

# 填充模式 → 中文标签
FILL_CN = {
    "customer_input": "客户输入",
    "derived": "推演",
    "fixed_norm": "规范固定",
    "retrievable": "可检索",
    "structural": "结构性",
    "missing_hard": "缺值",
}


# ---------------------------------------------------------------- loading
def load_json_yaml(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    stripped = text.lstrip()
    if stripped[:1] in "[{":           # 语料包里不少 .yaml 实际是 JSON 载荷，先走快路径
        try:
            return json.loads(text)
        except Exception:
            pass
    import yaml
    return yaml.safe_load(text)


def load_corpus(corpus_dir: str) -> Dict[str, Any]:
    nodes = load_json_yaml(os.path.join(corpus_dir, "graph/nodes.yaml"))
    rules = load_json_yaml(os.path.join(corpus_dir, "graph/rules.yaml"))
    sections = load_json_yaml(os.path.join(corpus_dir, "graph/sections.yaml"))
    if isinstance(sections, dict):
        sections = sections.get("sections", [])
    prompts = load_json_yaml(os.path.join(corpus_dir, "写作输入/section-prompts.yaml"))
    binds = {}
    bind_path = os.path.join(corpus_dir, "graph/derivation_bindings.yaml")
    if os.path.exists(bind_path):
        binds = load_json_yaml(bind_path) or {}
    return {"nodes": nodes, "rules": rules, "sections": sections, "prompts": prompts,
            "by_id": {n["id"]: n for n in nodes}, "binds": binds}


# ---------------------------------------------------------------- classify
def classify(node: Dict[str, Any]) -> Tuple[str, str, str]:
    """返回 (fill_mode, constraint, reason)。constraint ∈ {hard, soft, none}。"""
    rid = node.get("rule_id")
    origin = str(node.get("origin") or "")
    derived = bool(rid or node.get("expr") or origin.startswith("rule_output"))
    eff = (node.get("effect_level") or "").strip()
    has_val = node.get("value") not in (None, "", [], {})

    if derived:
        return "derived", "hard", "推演输出 %s" % (rid or "expr")
    if node.get("kind") == "norm_requirement":
        if eff in HARD_EFFECT:
            return "fixed_norm", "hard", "条款 %s" % eff
        return "retrievable", "soft", "条款 %s" % (eff or "未定级")
    if eff in HARD_EFFECT:
        return "fixed_norm", "hard", "条款 %s" % eff
    if eff in SOFT_EFFECT:
        return "retrievable", "soft", "资料性 %s" % eff
    if node.get("source") or node.get("source_url") or node.get("doc_id"):
        return ("customer_input", "hard", "有来源") if has_val else ("missing_hard", "hard", "有来源但无值")
    if has_val and node.get("kind") in VALUE_KINDS | {"text", "reference", "material", "method"}:
        return "customer_input", "hard", "图谱值"
    if has_val:
        return "customer_input", "hard", "图谱值"
    return "structural", "none", "无值"


def classify_all(nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {n["id"]: dict(fill_mode=classify(n)[0], constraint=classify(n)[1], reason=classify(n)[2])
            for n in nodes}


# ---------------------------------------------------------------- recompute
def _pick(nodes: List[Dict[str, Any]], predicate: str, subject: Optional[str]) -> Optional[Dict[str, Any]]:
    cands = [n for n in nodes if n.get("predicate") == predicate and n.get("value") not in (None, "", [])]
    if subject:
        scoped = [n for n in cands if n.get("subject") == subject]
        if scoped:
            return scoped[0]
    if len(cands) == 1:
        return cands[0]
    return cands[0] if cands else None


def resolve_dep(nodes: List[Dict[str, Any]], dep: str) -> Optional[Dict[str, Any]]:
    if "·" in dep:
        subject, predicate = dep.split("·", 1)
        return _pick(nodes, predicate.strip(), subject.strip())
    return _pick(nodes, dep.strip(), None)


def _ov(node: Dict[str, Any], overrides: Dict[str, Any]) -> Any:
    """what-if 覆盖：先按节点 ID，再按谓词（pred:xxx），便于「改一类值」而不用记 ID。"""
    if not overrides:
        return None
    nid = str(node.get("id") or "")
    if nid.startswith("EN-") or node.get("kind") == "reference_subject" or node.get("predicate") == "实体名":
        return None          # 实体名不是量，不参与数值覆盖
    if nid in overrides:
        return overrides[nid]
    pred, subj = str(node.get("predicate") or ""), str(node.get("subject") or "")
    if "pred:%s" % pred in overrides:
        return overrides["pred:%s" % pred]
    if "pred:%s" % subj in overrides:
        return overrides["pred:%s" % subj]
    # 标签覆盖：仅允许「同义后缀」命中（数量/合计/总计/值），避免 地上建筑面积 误伤 地上建筑面积缺口
    ALLOWED_SUFFIX = ("数量", "合计", "总计", "值")
    if node.get("kind") in ("reference_subject",) or pred == "实体名":
        return None
    for key, val in overrides.items():
        if not key.startswith("pred:"):
            continue
        label = key[5:]
        for field in (pred, subj):
            if not field.startswith(label):
                continue
            rest = field[len(label):]
            if rest == "" or rest in ALLOWED_SUFFIX or rest.lstrip("·").strip() in ALLOWED_SUFFIX:
                return val
    return None


def _num(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


SAFE = {"round": round, "min": min, "max": max, "abs": abs, "int": int, "float": float}


def _candidates(nodes: List[Dict[str, Any]], dep: str) -> List[Dict[str, Any]]:
    if "·" in dep:
        subject, predicate = dep.split("·", 1)
        return [n for n in nodes if n.get("predicate") == predicate.strip()
                and n.get("subject") == subject.strip() and n.get("value") not in (None, "", [])]
    return [n for n in nodes if n.get("predicate") == dep.strip() and n.get("value") not in (None, "", [])]


def eval_rule(rule: Dict[str, Any], nodes: List[Dict[str, Any]],
              overrides: Optional[Dict[str, Any]] = None,
              binds: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    overrides = overrides or {}
    binds = binds or {}
    by_id = {n["id"]: n for n in nodes}
    bound = (binds.get(rule.get("id")) or {}).get("deps") or {}
    missing, vals, used = [], {}, {}
    for dep in rule.get("deps") or []:
        bound_id = bound.get(dep, {}).get("node") or ""
        if bound_id:
            node = by_id.get(bound_id)
        else:
            cands = _candidates(nodes, dep)
            distinct = {str(c.get("value")) for c in cands}
            if len(distinct) > 1:
                return {"rule": rule.get("id"), "status": "ambiguous", "dep": dep,
                        "candidates": ["%s=%s" % (c["id"], c.get("value")) for c in cands[:6]],
                        "inputs": used}
            node = cands[0] if cands else None
        if node is None:
            missing.append(dep)
            continue
        default = bound.get(dep, {}).get("value", node.get("value"))
        ov = _ov(node, overrides)
        raw = ov if ov is not None else (default if default not in (None, "") else node.get("value"))
        num = _num(raw)
        if num is None:
            missing.append(dep)
            continue
        vals[dep] = num
        used[dep] = {"node": node["id"], "value": num}
    if missing:
        return {"rule": rule.get("id"), "status": "undefined", "missing": missing, "inputs": used}
    expr = rule.get("expr") or ""
    for k, v in vals.items():
        expr = expr.replace("{%s}" % k, repr(v))
    if rule.get("kind") == "select" or "=>" in expr:
        return _eval_select(rule, expr, used)
    try:
        out = eval(expr, {"__builtins__": {}}, SAFE)  # noqa: S307 - 已限定命名空间
    except Exception as exc:
        return {"rule": rule.get("id"), "status": "expr_error", "error": str(exc), "inputs": used}
    return {"rule": rule.get("id"), "status": "ok", "value": out, "inputs": used}


def _eval_select(rule: Dict[str, Any], expr: str, used: Dict[str, Any]) -> Dict[str, Any]:
    """把「cond => A；否则 => B」判定为分支文本，不产出数值。"""
    m = re.match(r"\s*(.+?)\s*=>\s*(.+?)\s*(?:[；;]\s*否则\s*=>\s*(.+))?$", expr)
    if not m:
        return {"rule": rule.get("id"), "status": "expr_error", "error": "select 表达式无法解析", "inputs": used}
    cond, yes, no = m.group(1).strip(), m.group(2).strip(), (m.group(3) or "待审").strip()
    cond = cond.replace("！", "!")
    for op in ("<=", ">=", "==", "<", ">"):
        if op in cond:
            left, right = [x.strip() for x in cond.split(op, 1)]
            try:
                l, r = eval(left, {"__builtins__": {}}, SAFE), eval(right, {"__builtins__": {}}, SAFE)
            except Exception as exc:
                return {"rule": rule.get("id"), "status": "expr_error", "error": str(exc), "inputs": used}
            ok = {"<=": l <= r, ">=": l >= r, "==": l == r, "<": l < r, ">": l > r}[op]
            return {"rule": rule.get("id"), "status": "ok", "value": yes if ok else no,
                    "branch": yes if ok else no, "inputs": used}
    return {"rule": rule.get("id"), "status": "expr_error", "error": "条件算子未识别", "inputs": used}


def recompute(rules: List[Dict[str, Any]], nodes: List[Dict[str, Any]],
              overrides: Optional[Dict[str, Any]] = None,
              binds: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    out = {}
    for r in rules:
        res = eval_rule(r, nodes, overrides, binds)
        stored = None
        for n in nodes:
            if n.get("rule_id") == r.get("id"):
                stored = n
                break
        if stored is not None and res.get("status") == "ok":
            a, b = _num(stored.get("value")), _num(res["value"])
            if a is not None and b is not None:
                tol = 0.01 if abs(b) >= 100 else 0.005
                res["stored"] = stored.get("value")
                res["stale"] = abs(a - b) > tol
        out[r.get("id")] = res
    return out


# ---------------------------------------------------------------- render
def _loc(node: Dict[str, Any]) -> str:
    sec = node.get("section") or ""
    anchor = node.get("anchor") or {}
    quote = anchor.get("quote") or node.get("row_head") or ""
    quote = re.sub(r"\s+", " ", str(quote)).strip()
    return ("§%s %s" % (sec, quote)).strip() if quote else ("§%s" % sec if sec else "")


def _fmt_value(node: Dict[str, Any], overrides: Dict[str, Any]) -> str:
    ov = _ov(node, overrides)
    v = ov if ov is not None else node.get("value")
    v = "" if v is None else str(v)
    unit = node.get("unit") or ""
    return (v + (" " + unit if unit else "")).strip()


def render_section(prompt_entry: Dict[str, Any], corpus: Dict[str, Any],
                   fills: Dict[str, Dict[str, Any]],
                   rules_res: Dict[str, Dict[str, Any]],
                   overrides: Optional[Dict[str, Any]] = None,
                   values_in_prompt: bool = True) -> Dict[str, Any]:
    overrides = overrides or {}
    nodes = corpus["nodes"]
    by_id = corpus["by_id"]
    targets = rule_targets(corpus)
    text = (prompt_entry.get("prompt") or "").strip()

    ids: List[str] = []
    for m in NODE_ID_RE.finditer(text):
        nid = m.group(1)
        if nid not in ids:
            ids.append(nid)

    out_lines: List[str] = []
    value_rows: List[Dict[str, Any]] = []
    soft_tasks: List[Dict[str, Any]] = []
    seen_nodes = set()
    for raw in text.splitlines():
        if (not values_in_prompt) and VALUE_LINE_RE.match(raw) and re.search(r"〔(?:CL|EV|RS|TD)-", raw):
            out_lines.append("  · {{论断或证据引文}}〔{{引文编号}}〕   # 引文属项目内容，见本节论断/证据表")
            continue
        if VALUE_LINE_RE.match(raw) and NODE_ID_RE.search(raw):
            nid = NODE_ID_RE.search(raw).group(1)
            if nid in seen_nodes:
                continue
            seen_nodes.add(nid)
            node = by_id.get(nid) or {}
            f = fills.get(nid) or {}
            mode, cons = f.get("fill_mode", "?"), f.get("constraint", "?")
            tag = "[%s|%s]" % ("硬" if cons == "hard" else ("软" if cons == "soft" else "—"),
                              FILL_CN.get(mode, mode))
            if mode == "derived" and node.get("rule_id"):
                rr = rules_res.get(node["rule_id"]) or {}
                if rr.get("status") == "ok":
                    tag += " R=%s" % rr["value"]
                    if rr.get("stale"):
                        tag += "⚠️过期(图中%s)" % rr.get("stored")
                elif rr.get("status") == "undefined":
                    tag += " R=undefined(缺%s)" % "、".join(rr.get("missing") or [])
            if mode in ("missing_hard",):
                tag += " →正文留白"
            st = str(node.get("status") or "")
            need_fetch = cons == "soft" and (
                node.get("value") in (None, "", []) or st in ("unverified", "pending_review"))
            if need_fetch:
                tag += " →需检索%s" % ("（%s）" % st if st in ("unverified", "pending_review") else "")
                soft_tasks.append({
                    "node": nid, "subject": node.get("subject"), "predicate": node.get("predicate"),
                    "section": prompt_entry.get("section_no"), "why": f.get("reason"), "status": st,
                    "sources": ["知识库（kp-library / 语料包）", "web（标准原文/官方公告）"],
                })
            note = ""
            hit = _matching_rule(node, targets, rules_res)
            if hit:
                rid, rv = hit
                a_v, b_v = _num(_fmt_value(node, overrides).split(" ")[0]), _num(rv)
                if a_v is not None and b_v is not None and abs(a_v - b_v) > (0.01 if abs(b_v) >= 100 else 0.005):
                    note = "   # ⚠️复算 %s 不符（%s），须重算或确认" % (rv, rid)
                else:
                    note = "   # = %s 复算一致" % rid
            if values_in_prompt:
                line = "  · %s = %s ｜ %s〔%s〕%s%s" % (
                    node.get("subject") or "?", _fmt_value(node, overrides), _loc(node), nid, tag, note)
            else:
                subj = str(node.get("subject") or "?")
                try:
                    from .prompt_hygiene import PROJECT_ENTITIES
                except Exception:
                    PROJECT_ENTITIES = ()
                if any(e in subj for e in PROJECT_ENTITIES):
                    subj = "{{项目主体}}"
                line = "  · 节点 %s ｜ %s·%s ｜%s ｜ 取值见本节事实表" % (
                    nid, subj, node.get("predicate") or "?", tag)
            out_lines.append(line)
            value_rows.append({"node": nid, "tag": tag, "value": _fmt_value(node, overrides)})
        elif re.match(r"本节原文约\s*\d+\s*字符", raw) and not values_in_prompt:
            out_lines.append("本节篇幅与切片数：见本节工作包（不在提示词内固化）。")
        elif re.match(r"^\s{2}·\s*另\s*\d+\s*条见本节事实表", raw):
            out_lines.append("  · 另 %d 条见本节事实表。" % max(0, int(prompt_entry.get("facts_count") or 0) - len(value_rows)))
        elif re.match(r"^\s{2}·\s*R-[^\s:：]+\s*[:：]", raw):
            rid = re.search(r"(R-[^\s:：]+)", raw)
            if rid and rid.group(1) in rules_res:
                rr = rules_res[rid.group(1)]
                if values_in_prompt:
                    status = {"ok": "可复算 ⇒ %s" % rr.get("value"),
                              "undefined": "缺输入 ⇒ undefined（%s）" % "、".join(rr.get("missing") or []),
                              "expr_error": "算式错误 ⇒ %s" % rr.get("error")}.get(rr.get("status"), rr.get("status"))
                else:
                    status = {"ok": "可复算（结果见事实表）",
                              "undefined": "缺输入 ⇒ undefined（%s）" % "、".join(rr.get("missing") or []),
                              "expr_error": "算式待修"}.get(rr.get("status"), rr.get("status"))
                out_lines.append("%s   # %s" % (raw, status))
            else:
                out_lines.append(raw)
        elif raw.strip().startswith("·") and ("／" in raw or "待审冲突" in raw or "确认后" in raw or "strong" in raw):
            if values_in_prompt:
                out_lines.append("%s   # 冲突随输入变化：输入改动后须重新确认，不得沿用旧判定" % raw)
            else:
                out_lines.append("  · 待审冲突：见本节冲突表（并列值不裁决；输入改动后须重新确认）")
        elif (not values_in_prompt) and re.match(r"^\s*·\s*\[[a-z_]+\]", raw):
            out_lines.append("  · [{{claim_type}}] {{论断原文（取值走节点槽位，见本节论断表）}}")
        elif (not values_in_prompt) and VALUE_LINE_RE.match(raw) and "=" in raw \
                and not raw.strip().startswith("· R-") and "／" not in raw:
            m2 = re.match(r"^\s*·\s*([^=｜]+?)\s*=", raw)
            label = (m2.group(1).strip() if m2 else "{{主体}}")
            from .prompt_hygiene import PROJECT_ENTITIES as _PE
            if any(e in label for e in _PE):
                label = "{{项目主体}}"
            out_lines.append("  · %s = 取值见本节事实表 ｜ 约束见本节事实表 ｜ 绑定 {{节点}}" % label)
        elif raw.startswith("本章证据等级分布：") and not values_in_prompt:
            out_lines.append("本章证据等级分布：见本节事实表（E1 必须注明提供方与日期；E2 必须带标准号+条款号）")
        else:
            out_lines.append(raw)

    for r in (prompt_entry.get("norm_refs") or []):
        if isinstance(r, dict) and r.get("status") and r.get("status") != "已核":
            soft_tasks.append({
                "node": "", "standard": r.get("standard"), "clause": r.get("clause"),
                "section": prompt_entry.get("section_no"), "why": "规范条款待核", "status": r.get("status"),
                "sources": ["web（标准原文）", "知识库（公共标准库）"],
            })

    return {
        "section_no": prompt_entry.get("section_no"),
        "title": prompt_entry.get("title"),
        "prompt": "\n".join(out_lines),
        "value_rows": value_rows,
        "soft_tasks": soft_tasks,
    }


def rule_targets(corpus: Dict[str, Any]) -> List[Tuple[str, str]]:
    """[(rule_id, target_label)] —— target 来自 derivation_bindings（缺失则读 rules.yaml）。"""
    out = []
    for rid, b in (corpus.get("binds") or {}).items():
        if b.get("target"):
            out.append((rid, b["target"]))
    known = {r for r, _ in out}
    for r in corpus["rules"]:
        if r.get("id") not in known and r.get("target"):
            out.append((r["id"], r["target"]))
    return out


def _norm_label(label: str) -> str:
    """去掉「数量/合计/总计」等统计后缀后比较，避免「建筑面积」误命中「总建筑面积」。"""
    out = str(label or "").strip()
    for suf in ("数量", "合计", "总计", "值"):
        if out.endswith(suf) and len(out) > len(suf):
            out = out[: -len(suf)]
    return out


def _matching_rule(node: Dict[str, Any], targets: List[Tuple[str, str]],
                   rules_res: Dict[str, Dict[str, Any]]) -> Optional[Tuple[str, Any]]:
    pred = str(node.get("predicate") or "")
    for rid, target in targets:
        if not target or rid not in rules_res:
            continue
        if rules_res[rid].get("status") != "ok":
            continue
        if _norm_label(target) == _norm_label(pred):
            return rid, rules_res[rid].get("value")
    return None


def render_all(corpus: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None,
               values_in_prompt: bool = True) -> List[Dict[str, Any]]:
    fills = classify_all(corpus["nodes"])
    rules_res = recompute(corpus["rules"], corpus["nodes"], overrides, corpus.get("binds"))
    return [render_section(p, corpus, fills, rules_res, overrides, values_in_prompt)
            for p in corpus["prompts"]]


def audit(corpus: Dict[str, Any]) -> Dict[str, Any]:
    fills = classify_all(corpus["nodes"])
    rules_res = recompute(corpus["rules"], corpus["nodes"], None, corpus.get("binds"))
    cnt: Dict[str, Dict[str, int]] = {}
    for f in fills.values():
        cnt.setdefault(f["fill_mode"], {}).setdefault(f["constraint"], 0)
        cnt[f["fill_mode"]][f["constraint"]] += 1
    stale = {k: v for k, v in rules_res.items() if v.get("stale")}
    undefined = {k: v for k, v in rules_res.items() if v.get("status") != "ok"}
    return {
        "nodes": len(corpus["nodes"]),
        "fill_modes": cnt,
        "rules": len(corpus["rules"]),
        "rules_ok": sum(1 for v in rules_res.values() if v.get("status") == "ok"),
        "rules_stale": {k: {"stored": v.get("stored"), "recomputed": v.get("value")} for k, v in stale.items()},
        "rules_unsatisfied": {k: {"status": v.get("status"), "missing": v.get("missing")} for k, v in undefined.items()},
    }
