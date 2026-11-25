# -*- coding: utf-8 -*-
"""evo_distill —— 第二步工序：把含值本体「去值留形」（零 LLM，确定性）。

## 两步走

    第 1 步  EvoOntology build-ontology / evolve-ontology
             原文 → terms / mappings / relations / constraints / evidence（**含项目值**）

    第 2 步  本模块 distill
             含值本体 → 形包（**0 项目值，可跨项目复用**）

## 去什么、留什么（判据写死在代码里，不靠模型判断）

| 去（值） | 留（形） |
|---|---|
| 项目名 / 编号 / 地点 / 建设单位 / 编制单位 | **术语类型**（entity/metric/gate/limit/clause/guard/claim/category/concept）|
| 金额 / 面积 / 人数 / 工期 / 负荷 / 造价 | **关系类型**（11 种）|
| 具体 standard 号里的版本年份 | **标准号本身**（建标191-2018 是形）|
| evidence 的 source/result（含原文数值） | evidence 的 **validation_method 类别**（逐行求和/交叉核对…）|
| definition 里的具体数字 | definition 的**句式骨架**（用 {占位符} 替换）|
| 具体 id（total_investment） | **id 模式**（`metric_<谓词>`）|

## 关键：标准号与条款原文

- **标准号 = 形**（`建标191-2018` 跨项目都要引）
- **条款原文 = 值**？→ **不是值，是外部事实**。本模块只保留「槽位」，
  条款原文应由公共标准库提供（见形包 `lineage/`）。

## 硬要求

- **每个被去掉的数字必须有占位符替代**，否则下游不知道怎么填
- **去不掉的（无法判断是形还是值）→ 标 `UNKNOWN`**，不猜
- **输出必须能通过「0 项目数值」检查**（复用 release-check 的 BAD 列表）
"""
from __future__ import annotations
import json
import re
from pathlib import Path

# 值特征（命中即脱敏）
VALUE_PATTERNS = [
    (re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"), "{NUM}"),      # 1,234 / 13,032
    (re.compile(r"\d+(?:\.\d+)?\s*(?:万元|元|平方米|㎡|m²|m3|m³|kWh|kVA|kW|tce|吨|人|个|层|米|m|%|天|月|年)"), "{NUM}{UNIT}"),
    (re.compile(r"\d{4}年\d{1,2}月(?:\d{1,2}日)?"), "{DATE}"),
    (re.compile(r"\b\d{5,}\b"), "{NUM}"),                         # 编号
    # 中文后紧跟的数字（Python 的 \w 含中文，会误判为词内）
    (re.compile(r"(?<=[\u4e00-\u9fa5])\d{2,}(?![\w}])"), "{NUM}"),
    # 裸数字（无单位）：2 位以上，且不在 {NUM} 占位符里
    #   规则：前面不是 ASCII 字母/下划线/{，后面不是 ASCII 字母/下划线/}
    (re.compile(r"(?<![A-Za-z_{])\d{2,}(?![A-Za-z_}])"), "{NUM}"),
]
# 项目专名（从 source 里学到的，由调用方传入；这里给默认清单）
DEFAULT_BAD = ["上海财经", "中山北一路", "2019ZX054", "同济工程咨询", "大数据研究中心"]

EVIDENCE_METHOD_KINDS = {
    "逐行求和": "row_sum", "逐行读取": "row_read", "交叉核对": "cross_check",
    "复算": "recompute", "提取": "extract", "核对": "verify",
}


def _mask(s: str, bad: list) -> tuple[str, int]:
    """把字符串里的值换成占位符。返回 (脱敏后, 替换次数)。"""
    if not isinstance(s, str):
        return s, 0
    n = 0
    for b in bad:
        if b and b in s:
            s = s.replace(b, "{项目}")
            n += 1
    for pat, rep in VALUE_PATTERNS:
        s2, k = pat.subn(rep, s)
        if k: n += k; s = s2
    return s, n


def distill(workspace, version: str = "", *, out_dir=None,
            bad_names: list | None = None) -> dict:
    """含值本体 → 形包。返回统计与产物路径。"""
    ws = Path(workspace)
    ver = version or json.loads((ws/"active.json").read_text(encoding="utf-8"))["active_version"]
    src = ws/"versions"/ver
    if not src.exists():
        raise FileNotFoundError("版本目录不存在: %s" % src)
    bad = list(bad_names or DEFAULT_BAD)

    terms = json.loads((src/"terms.json").read_text(encoding="utf-8"))
    rels = json.loads((src/"relations.json").read_text(encoding="utf-8"))
    cons = json.loads((src/"constraints.json").read_text(encoding="utf-8"))
    evid = json.loads((src/"evidence.json").read_text(encoding="utf-8"))

    # 从 term 里再学一批专名（definition 里高频的实体名）
    for t in terms:
        if t.get("type") == "entity" and t.get("name"):
            nm = str(t["name"])
            if 4 <= len(nm) <= 40 and nm not in bad:
                bad.append(nm)

    stats = {"terms_in": len(terms), "terms_out": 0, "masked": 0,
             "by_type": {}, "evidence_out": 0, "relations_out": 0}

    # ① 术语：去值，保留类型/关系/口径句式
    out_terms = {}
    for t in terms:
        ty = str(t.get("type") or "unknown")
        defn, n1 = _mask(str(t.get("definition") or ""), bad)
        scope, n2 = _mask(str(t.get("scope") or ""), bad)
        name, n3 = _mask(str(t.get("name") or ""), bad)
        stats["masked"] += n1 + n2 + n3
        # 别名里全是值的丢掉
        aliases = []
        for a in (t.get("aliases") or []):
            aa, k = _mask(str(a), bad)
            if k == 0 and not re.search(r"\d", str(a)):
                aliases.append(aa)
        key = "%s:%s" % (ty, re.sub(r"[^\w]+", "_", str(t.get("id"))) [:40])
        out_terms[key] = {
            "term_type": ty, "name_pattern": name, "definition_pattern": defn,
            "scope_pattern": scope, "aliases_shape": aliases[:5],
            "evidence_kinds": [], "id_shape": _id_shape(str(t.get("id") or "")),
        }
        stats["by_type"][ty] = stats["by_type"].get(ty, 0) + 1

    # ② 关系：只留类型分布 + 端点类型组合
    rel_shapes = {}
    for r in rels:
        rt = str(r.get("relation_type") or "unknown")
        rel_shapes[rt] = rel_shapes.get(rt, 0) + 1
    stats["relations_out"] = len(rel_shapes)

    # ③ 证据：只留验证方法类别，不留 source/result
    ev_kinds = {}
    for e in evid:
        m = str(e.get("validation_method") or "")
        kind = next((v for k, v in EVIDENCE_METHOD_KINDS.items() if k in m), "other")
        ev_kinds[kind] = ev_kinds.get(kind, 0) + 1
    stats["evidence_out"] = len(ev_kinds)

    # ④ 约束：去值留判据
    out_cons = []
    for c in cons:
        desc, k = _mask(str(c.get("description") or ""), bad)
        stats["masked"] += k
        out_cons.append({"constraint_type": c.get("constraint_type"),
                         "severity": c.get("severity"),
                         "scope_pattern": _mask(str(c.get("scope") or ""), bad)[0],
                         "description_pattern": desc})

    # ⑤ 四类专门结构（gate/limit/guard/clause）—— 从 definition 里解析结构
    gate_shapes, limit_shapes, guard_shapes, clause_shapes = [], [], [], []
    for t_ in terms:
        ty = str(t_.get("type") or "")
        d = str(t_.get("definition") or "")
        if ty == "gate":
            g = {"gate_kind": None, "expr_pattern": None, "inputs": [], "fail_pattern": None,
                 "status": None, "id": t_.get("id")}
            m = re.search(r"([a-z_]+) 门禁", d)
            if m: g["gate_kind"] = m.group(1)
            m = re.search(r"表达式[：:]\s*([^；]+)", d)
            if m: g["expr_pattern"] = _mask(m.group(1).strip(), bad)[0]
            m = re.search(r"输入[：:]\s*([^；]+)", d)
            if m: g["inputs"] = [x.strip() for x in m.group(1).split(",") if x.strip()]
            m = re.search(r"失败信息[：:]\s*([^；]+)", d)
            if m: g["fail_pattern"] = _mask(m.group(1).strip(), bad)[0][:200]
            m = re.search(r"状态[：:]\s*([a-z_]+)", d)
            if m: g["status"] = m.group(1)
            gate_shapes.append(g)
        elif ty == "limit":
            l = {"id": t_.get("id"), "metric": None, "value_pattern": None,
                 "operator": None, "scope_pattern": None}
            m = re.search(r"报告指标\s*(.+?)\s*=\s*([^（(]+)[（(]比较符\s*([^）)]+)", d)
            if m:
                l["metric"] = _mask(m.group(1).strip(), bad)[0]
                l["value_pattern"] = _mask(m.group(2).strip(), bad)[0]
                l["operator"] = m.group(3).strip()
            else:
                m = re.search(r"报告指标\s*(.+?)\s*=\s*(.+)", d)
                if m:
                    l["metric"] = _mask(m.group(1).strip(), bad)[0]
                    l["value_pattern"] = _mask(m.group(2).strip()[:60], bad)[0]
            l["scope_pattern"] = _mask(str(t_.get("scope") or ""), bad)[0]
            limit_shapes.append(l)
        elif ty == "guard":
            gd = {"id": t_.get("id"), "risk_level": None, "condition_pattern": None, "action": None}
            m = re.search(r"风险等级[：:]\s*(\w+)", d)
            if m: gd["risk_level"] = m.group(1)
            m = re.search(r"条件[：:]\s*([^；]+)", d)
            if m: gd["condition_pattern"] = _mask(m.group(1).strip(), bad)[0]
            m = re.search(r"动作[：:]\s*([^；]+)", d)
            if m: gd["action"] = _mask(m.group(1).strip(), bad)[0]
            guard_shapes.append(gd)
        elif ty == "clause":
            c = {"id": t_.get("id"), "standard": None, "document_number": None,
                 "cited_sections": [], "slot_status": "empty"}
            m = re.search(r"《(.+?)》\(([^)]+)\)", d)
            if m:
                c["standard"] = m.group(1); c["document_number"] = m.group(2)
            m = re.search(r"引用章节[：:]\s*([^；]+)", d)
            if m: c["cited_sections"] = [x.strip() for x in m.group(1).split(",") if x.strip()]
            if "待补" not in d: c["slot_status"] = "filled"
            clause_shapes.append(c)

    stats["gate_shapes"] = len(gate_shapes)
    stats["limit_shapes"] = len(limit_shapes)
    stats["guard_shapes"] = len(guard_shapes)
    stats["clause_shapes"] = len(clause_shapes)

    result = {
        "schema": "shape-from-evo/v1",
        "source": {"workspace": str(ws), "version": ver},
        "why": "第 2 步：把含值本体去值留形；第 1 步（抽取+建关系）由 EvoOntology 完成",
        "stats": stats,
        "term_shapes": out_terms,
        "relation_shape_counts": rel_shapes,
        "evidence_method_kinds": ev_kinds,
        "constraint_shapes": out_cons,
        "gate_shapes": gate_shapes,
        "limit_shapes": limit_shapes,
        "guard_shapes": guard_shapes,
        "clause_shapes": clause_shapes,
        "still_has_value": _scan_values(out_terms, out_cons, bad),
    }
    if out_dir:
        od = Path(out_dir); od.mkdir(parents=True, exist_ok=True)
        (od/"shape-from-evo.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        stats["out"] = str(od/"shape-from-evo.json")
    return result


def _id_shape(i: str) -> str:
    """id → 模式（total_investment → metric_<style>）"""
    if re.match(r"^[a-z]+_\d+$", i): return re.sub(r"_\d+$", "_<n>", i)
    if re.match(r"^[a-z0-9_]+$", i): return "<snake_case>"
    return "<id>"


def _scan_values(term_shapes: dict, cons: list, bad: list) -> list:
    """终检：形包里还有没有值。"""
    blob = json.dumps({"t": term_shapes, "c": cons}, ensure_ascii=False)
    hits = [b for b in bad if b in blob]
    hits += re.findall(r"\d{1,3}(?:,\d{3})+", blob)[:5]
    return hits
