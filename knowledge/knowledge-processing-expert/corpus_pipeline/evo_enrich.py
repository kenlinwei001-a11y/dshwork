# -*- coding: utf-8 -*-
"""evo_enrich —— 给 workspace 补 connection_condition 与 requires 边（零 LLM）。

## 第三步方案里的前两步

  第一步  为计算类 derivation 边回填 connection_condition
          {formula, tolerance, gate} —— 子项边带父项公式和容差

  第二步  新增 requires 边：gate → 输入指标
          gate_calc_civil_works_sum --requires--> pile_foundation（×7）
          让门禁输入**可查询**，而不是藏在 definition 字符串里

## 只做计算类

`hierarchy` / `association` / `citation` **不硬造** —— 只有 definition 里
明确写了条件才填，否则保持空。
"""
from __future__ import annotations
import json
import re
from pathlib import Path


def _target_var(expr: str):
    """从表达式里抓「被定义的那个变量」。支持两种形态：

        X == ...                          → X
        abs(X - (...)) <= tol             → X
        abs(X * k - Y) <= tol             → X（取第一个出现的变量）
    """
    m = re.match(r"^([a-z_][a-z0-9_]*)\s*==", expr)
    if m:
        return m.group(1)
    m = re.match(r"^abs\(\s*([a-z_][a-z0-9_]*)\s*[-*]", expr)
    if m:
        return m.group(1)
    return None


def _gate_map(terms: list) -> dict:
    """gate_id → {expr, inputs, target}"""
    out = {}
    for t in terms:
        if t.get("type") != "gate":
            continue
        d = str(t.get("definition") or "")
        m = re.search(r"表达式[：:]\s*([^；]+)", d)
        expr = m.group(1).strip() if m else ""
        m2 = re.search(r"输入[：:]\s*([^；]+)", d)
        inputs = [x.strip() for x in m2.group(1).split(",")] if m2 else []
        # 容差：从 abs(...) <= N 里取
        tol = None
        mt = re.search(r"<=\s*([\d.]+)\s*$", expr)
        if mt:
            tol = float(mt.group(1))
        out[t.get("id")] = {"expr": expr, "inputs": inputs,
                            "tolerance": tol, "target_var": _target_var(expr)}
    return out


def enrich(workspace, version: str = "", *, out_version=None, write=True) -> dict:
    """回填 connection_condition + 生成 requires 边。写入 out_version（默认 <ver>_enriched）。"""
    ws = Path(workspace)
    ver = version or json.loads((ws/"active.json").read_text(encoding="utf-8"))["active_version"]
    src = ws/"versions"/ver
    terms = json.loads((src/"terms.json").read_text(encoding="utf-8"))
    rels = json.loads((src/"relations.json").read_text(encoding="utf-8"))
    cons = json.loads((src/"constraints.json").read_text(encoding="utf-8"))
    evid = json.loads((src/"evidence.json").read_text(encoding="utf-8"))
    gates = _gate_map(terms)

    # ① 建「结果变量 → gate」索引
    var2gate = {}
    for gid, g in gates.items():
        tv = g.get("target_var")
        if tv:
            var2gate.setdefault(tv, []).append(gid)

    stats = {"cc_filled": 0, "requires_added": 0, "skipped_noncalc": 0}
    new_rels = []
    seen_req = set()

    for r in rels:
        rt = str(r.get("relation_type") or "")
        # ---------- 第一步：计算类 derivation 回填 connection_condition ----------
        if rt == "derivation" and not r.get("connection_condition"):
            tgt = str(r.get("target") or "")
            src_ = str(r.get("source") or "")
            # calc_* → 结果：该 gate 就是它的公式
            if src_.startswith("calc_"):
                gs = var2gate.get(tgt, [])
                if gs:
                    g = gates[gs[0]]
                    r = dict(r)
                    r["connection_condition"] = {
                        "formula": g["expr"],
                        "tolerance": g["tolerance"],
                        "gate": gs[0],
                        "role": "computed_by",
                    }
                    stats["cc_filled"] += 1
            else:
                # 子项 → 父项：找父项的 gate
                gs = var2gate.get(tgt, [])
                if gs:
                    g = gates[gs[0]]
                    r = dict(r)
                    r["connection_condition"] = {
                        "formula": g["expr"],
                        "tolerance": g["tolerance"],
                        "gate": gs[0],
                        "role": "input_of",
                    }
                    stats["cc_filled"] += 1
        elif rt in ("hierarchy", "association", "citation"):
            stats["skipped_noncalc"] += 1
        # ---------- 第二步：requires 边 ----------
        new_rels.append(r)

    # ② gate → 输入指标 的 requires 边
    for gid, g in gates.items():
        tgt_var = g.get("target_var")
        for inp in g["inputs"]:
            key = (gid, inp)
            if key in seen_req:
                continue
            seen_req.add(key)
            new_rels.append({
                "id": "req_%s__%s" % (gid, inp),
                "source": gid,
                "relation_type": "requires",
                "target": inp,
                "connection_condition": {"role": "gate_input",
                                         "for_target": tgt_var},
                "description": "",
                "evidence": [],
            })
            stats["requires_added"] += 1

    out_ver = out_version or (ver + "_enriched")
    if write:
        d = ws/"versions"/out_ver
        d.mkdir(parents=True, exist_ok=True)
        for name, data in [("terms", terms), ("relations", new_rels),
                           ("constraints", cons), ("evidence", evid)]:
            (d/(name+".json")).write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        # mappings 原样复制（若有）
        mp = src/"mappings.json"
        if mp.exists():
            (d/"mappings.json").write_text(mp.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            (d/"mappings.json").write_text("[]", encoding="utf-8")
        (ws/"active.json").write_text(
            json.dumps({"active_version": out_ver}), encoding="utf-8")
    stats["version"] = out_ver
    stats["relations_before"] = len(rels)
    stats["relations_after"] = len(new_rels)
    return stats
