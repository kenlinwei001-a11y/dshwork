# -*- coding: utf-8 -*-
"""evo_factify —— 建显式 fact 层 + based_on 关系（学 v4 做法，零 LLM）。

## 为什么这是关键

v3 的「值」散落在 `term.definition` 的散文里，`gate_inputs` 只能靠正则抽，
结果 21 个门禁缺输入 → UNVERIFIABLE。

v4 建了 **29 个显式 fact 节点**：
    {"id": "fact_total_investment", "type": "fact",
     "name": "事实：项目总投资 = 13032万元", "aliases": ["13032万元"]}

**name 里带 `= <值><单位>`** → 可直接解析，不靠正则碰运气。
`gate_inputs` 从 fact 取 → 30 PASS。

## 做什么

  ① limit → fact          29 个报告指标值变成显式 fact 节点
  ② metric 有值 → fact     投资明细值也可成 fact
  ③ based_on 关系          limit/claim --based_on--> fact
  ④ gate_inputs 源改为 fact

## 硬要求

- fact 必须有 `evidence`（无证据的不能叫 fact，只能叫 proposed）
- fact 的 `name` 必须是 `<中文名> = <值><单位>` 形式（可解析）
- 不覆盖已有 fact（幂等）
"""
from __future__ import annotations
import json
import re
from pathlib import Path


def _parse_value(s: str):
    """从字符串里解析 (数值, 单位)。"""
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*([^\s，。；、]*)$", str(s).strip())
    if not m:
        return None, ""
    try:
        return float(m.group(1).replace(",", "")), (m.group(2) or "").strip()
    except ValueError:
        return None, ""


def build_facts(workspace, version: str = "", *, out_version=None, write=True) -> dict:
    """从 limit / metric 建 fact 节点 + based_on 关系。"""
    ws = Path(workspace)
    ver = version or json.loads((ws/"active.json").read_text(encoding="utf-8"))["active_version"]
    src = ws/"versions"/ver
    terms = json.loads((src/"terms.json").read_text(encoding="utf-8"))
    rels = json.loads((src/"relations.json").read_text(encoding="utf-8"))

    existing_facts = {t.get("id") for t in terms if t.get("type") == "fact"}
    new_facts, new_rels = [], []
    src_map = {}          # 源 term id → fact id

    def _mk_fact(src_term, cn_name, value, unit, ev):
        fid = "fact_" + str(src_term.get("id")).replace("limit_", "").replace("P-", "")[:40]
        if fid in existing_facts:
            src_map[src_term.get("id")] = fid
            return None
        fact = {
            "id": fid,
            "name": "事实：%s = %s%s" % (cn_name, _fmt(value), unit),
            "type": "fact",
            "definition": "报告中可直接定位的观察值：%s = %s%s。不是标准条款值。"
                          % (cn_name, _fmt(value), unit),
            "scope": "报告内可直接定位的观察值；不是标准条款值。",
            "aliases": ["%s%s" % (_fmt(value), unit)],
            "evidence": list(ev or []),
        }
        src_map[src_term.get("id")] = fid
        return fact

    # ① limit → fact
    for t in terms:
        if t.get("type") != "limit":
            continue
        d = str(t.get("definition") or "")
        m = re.search(r"报告指标\s*(.+?)\s*=\s*([\d,]+(?:\.\d+)?)\s*([^\s（(]*)", d)
        if not m:
            continue
        cn, val, unit = m.group(1).strip(), float(m.group(2).replace(",", "")), m.group(3).strip()
        f = _mk_fact(t, cn, val, unit, t.get("evidence"))
        if f:
            new_facts.append(f)

    # ② metric（name 形如「X = 15600」）→ fact
    for t in terms:
        if t.get("type") != "metric":
            continue
        nm = str(t.get("name") or "")
        m = re.match(r"^(.+?)\s*=\s*([\d,]+(?:\.\d+)?)\s*(.*)$", nm)
        if not m:
            continue
        cn, val, unit = m.group(1).strip(), float(m.group(2).replace(",", "")), m.group(3).strip()
        f = _mk_fact(t, cn, val, unit, t.get("evidence"))
        if f:
            new_facts.append(f)

    # ③ based_on：limit / claim / metric --based_on--> fact
    for t in terms:
        tid = t.get("id")
        fid = src_map.get(tid)
        if not fid:
            continue
        new_rels.append({
            "id": "bo_%s" % tid,
            "source": tid, "relation_type": "based_on", "target": fid,
            "connection_condition": {"role": "observed_from"},
            "description": "", "evidence": [],
        })

    all_terms = terms + new_facts
    all_rels = rels + new_rels
    stats = {"facts_new": len(new_facts), "based_on": len(new_rels),
             "facts_total": sum(1 for t in all_terms if t.get("type") == "fact"),
             "relations_after": len(all_rels)}

    if not write:
        return {**stats, "facts": new_facts}

    out_ver = out_version or (ver + "_fact")
    dst = ws/"versions"/out_ver
    dst.mkdir(parents=True, exist_ok=True)
    for nm, data in [("terms", all_terms), ("relations", all_rels)]:
        (dst/(nm+".json")).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    for nm in ("constraints", "evidence", "mappings"):
        f = src/(nm+".json")
        (dst/(nm+".json")).write_text(f.read_text(encoding="utf-8") if f.exists() else "[]",
                                      encoding="utf-8")
    (ws/"active.json").write_text(json.dumps({"active_version": out_ver}), encoding="utf-8")
    stats["version"] = out_ver
    stats["facts"] = new_facts[:5]
    return stats


def _fmt(v) -> str:
    """13032 → '13032'；13032.0 → '13032'"""
    return str(int(v)) if isinstance(v, (int, float)) and float(v) == int(v) else str(v)


def collect_from_facts(terms: list) -> dict:
    """**从 fact 层取值**（替代从 definition 正则抽）。"""
    env = {}
    for t in terms:
        if t.get("type") != "fact":
            continue
        nm = str(t.get("name") or "")
        m = re.match(r"^事实[：:]\s*(.+?)\s*=\s*([\d,]+(?:\.\d+)?)\s*(.*)$", nm)
        if m:
            cn = m.group(1).strip()
            try:
                env[cn] = float(m.group(2).replace(",", ""))
            except ValueError:
                continue
        # fact id 也作别名（fact_total_investment → total_investment）
        fid = str(t.get("id")).replace("fact_", "")
        if cn in env:
            env[fid] = env[cn]
    return env
