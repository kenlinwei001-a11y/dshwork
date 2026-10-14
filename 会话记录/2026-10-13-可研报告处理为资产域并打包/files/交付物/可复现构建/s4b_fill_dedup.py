# -*- coding: utf-8 -*-
"""s4b —— 图谱补全与去重（**必须跑在脱敏之前**）。

架构性根因（本步存在的理由）：
  原链路 order = s4(回放) → s5a(脱敏骨架 s7b) → … → s5e(opt25 图谱补救)
  即**图谱补救发生在脱敏之后** ⇒ 补救新增的节点永远进不了骨架，
  骨架里那些量值只能留字面值（或此前被伪造 id）。
  故补全/去重必须前置到脱敏之前。

两件事（均为确定性）：
  ① 去重：同 (subject, predicate, value, unit) 的多条 fact 合并，保留最早来源，
     合并后的 sources 列表保留全部出处（可追溯）。**仅数值相同不算重复**
     （如 0.5 分别属屋面活荷载/地震影响系数，是不同事实）。
  ② 补全：从设备表格行中抽取「设备名 → 制冷量/制热量/功率」参数，建 fact+node。
     推导式中的项（如 315人×16㎡/人+…+2200㎡=18040㎡）**不建节点**，登记为公式项。
"""
import json, re, sys
from collections import defaultdict, OrderedDict
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
R = WS / "SHUFE-BDC-2019-001"
sys.path.insert(0, "/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert")
from corpus_pipeline import stable_id  # noqa: E402


def J(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


def W(p, o):
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


facts = J(R / "graph" / "graph.yaml")["facts"]
nodes = J(R / "graph" / "nodes.yaml")
report = {}

# ── ① 去重（按完整事实元组，不按数值）──────────────────────────
groups = OrderedDict()
for i, f in enumerate(facts):
    k = (f.get("subject"), f.get("predicate"), str(f.get("value")), f.get("unit"))
    groups.setdefault(k, []).append((i, f))
deduped, merged = [], []
for k, items in groups.items():
    items.sort(key=lambda x: x[0])                      # 保留最早出现者
    keep = items[0][1]
    srcs = [x[1].get("source") for x in items if x[1].get("source")]
    if len(items) > 1:
        keep = dict(keep); keep["sources"] = sorted(set(srcs))
        keep["merged_count"] = len(items)
        merged.append({"fact": list(k), "merged": len(items), "sources": keep["sources"]})
    deduped.append(keep)
report["dedup"] = {"before": len(facts), "after": len(deduped),
                   "merged_groups": len(merged), "merged_facts": len(facts) - len(deduped),
                   "merged_detail": merged[:40]}
W(R / "graph" / "graph.yaml", {**J(R / "graph" / "graph.yaml"), "facts": deduped})

# 节点侧同步去重（同 id 或同 subject+predicate+value）
ng, kept_nodes, ndup = OrderedDict(), [], 0
for n in nodes:
    k = n.get("id") or (n.get("subject"), n.get("predicate"), str(n.get("value")))
    if k in ng:
        ndup += 1
        continue
    ng[k] = n; kept_nodes.append(n)
W(R / "graph" / "nodes.yaml", kept_nodes)
report["node_dedup"] = {"before": len(nodes), "after": len(kept_nodes), "removed": ndup}

# ── ② 补全：设备参数表行 → fact + node ────────────────────────
chunks = [json.loads(l) for l in (R / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
PARAM = re.compile(r"(制冷量|制热量|功率)\s*[:：]\s*([\d.]+)\s*(kW|KW|kw|W)")
# 水泵/风机常用 N＝XkW 表示功率（本会话曾因只认「功率：XkW」漏抽 37/2.2）
PARAM_N = re.compile(r"[Nn]\s*[=＝]\s*([\d.]+)\s*(kW|KW|kw)")
RANGE_V = re.compile(r"([\d.]+)\s*[~～]\s*([\d.]+)\s*(米/昼夜|m/d|米)")
# 区间事实的主体：取区间前最近的中文名词（不要把值当成主体）
RANGE_SUBJ = re.compile(r"([\u4e00-\u9fff]{2,10})\s*$")
ANNUAL = re.compile(r"年均资金需求量约\s*([\d.]+)\s*(万元)")
DEV = re.compile(r"([\u4e00-\u9fffA-Za-z（）()\d\s]{4,40}?)\s*[|｜]?\s*(?:制冷量|制热量|功率)")
have = {(f.get("subject"), f.get("predicate"), str(f.get("value"))) for f in deduped}
ids = {n["id"] for n in kept_nodes}
added, formula_terms = [], []
for c in chunks:
    text = c.get("text") or ""
    for line in text.split("\n"):
        if not any(k in line for k in ("制冷量", "制热量", "功率")):
            continue
        devs = DEV.findall(line)
        dev = devs[0].strip(" |｜") if devs else None
        if not dev or len(dev) < 3:
            continue
        extra = [(("功率"), v, u) for v, u in PARAM_N.findall(line)]
        for pname, val, unit in list(PARAM.findall(line)) + extra:
            unit = "kW" if unit.lower() == "kw" else unit
            # 同值同设备已存在则跳过
            if (dev, pname, val) in have:
                continue
            nid = stable_id(f"{dev}|{pname}|{val}", "N")
            if nid in ids:
                continue
            ids.add(nid); have.add((dev, pname, val))
            added.append({"id": nid, "subject": dev, "predicate": pname, "value": val,
                          "unit": unit, "time": "", "source": c["id"],
                          "kind": "quantity", "status": "defined",
                          "section": (c.get("section_path") or [""])[0],
                          "output_source": "extract:设备参数表行（补全，带来源 chunk）"})
    # 区间事实：建模为一条区间事实（而非端点各自成节点，避免假缺口）
    for m_r in RANGE_V.finditer(text):
        lo, hi, unit = m_r.group(1), m_r.group(2), m_r.group(3)
        _pre = text[max(0, m_r.start() - 14):m_r.start()]
        _sm = RANGE_SUBJ.search(_pre)
        subj = _sm.group(1) if _sm else "（未指明对象）"
        key = (subj, "取值区间")
        if key in {(f.get("subject"), f.get("predicate")) for f in deduped}:
            continue
        nid = stable_id(f"{subj}|取值区间|{lo}~{hi}|{unit}", "N")
        if nid in ids: continue
        ids.add(nid)
        added.append({"id": nid, "subject": subj, "predicate": "取值区间",
                      "value": f"{lo}~{hi}", "unit": unit, "time": "", "source": c["id"],
                      "kind": "quantity", "status": "defined",
                      "section": (c.get("section_path") or [""])[0],
                      "output_source": "extract:区间取值（补全，带来源 chunk）"})
    # 年均资金需求（原稿明写，此前漏抽）
    for v, u in ANNUAL.findall(text):
        if ("本项目", "年均资金需求量", v) in have: continue
        nid = stable_id(f"本项目|年均资金需求量|{v}", "N")
        if nid in ids: continue
        ids.add(nid); have.add(("本项目", "年均资金需求量", v))
        added.append({"id": nid, "subject": "本项目", "predicate": "年均资金需求量",
                      "value": v, "unit": u, "time": "", "source": c["id"],
                      "kind": "quantity", "status": "defined",
                      "section": (c.get("section_path") or [""])[0],
                      "output_source": "extract:原文明写（补全，带来源 chunk）"})
    # 推导式项登记（不建节点；**登记即声明为非缺口**）
    for m in re.finditer(r"[\d.]+\s*人\s*[×xX]\s*[\d.]+\s*㎡/人\s*\+\s*[\d.]+\s*人\s*[×xX]\s*[\d.]+\s*㎡/人\s*\+\s*([\d.]+)\s*㎡", text):
        formula_terms.append({"chunk": c["id"], "term": m.group(0)[:80],
                              "reason": "推导式中的项，非独立事实（由 rules/reasoning 层承载）"})
if added:
    W(R / "graph" / "nodes.yaml", kept_nodes + added)
    g = J(R / "graph" / "graph.yaml")
    g["facts"] = deduped + added
    W(R / "graph" / "graph.yaml", g)
report["fill"] = {"added": len(added), "sample": added[:6],
                  "formula_terms_registered": len(formula_terms),
                  "formula_sample": formula_terms[:3],
                  "formula_values_excluded": sorted({t["term"] for t in formula_terms}),
                  "note": "登记为公式项 ⇒ 是推导式的操作数，**不再计入未建模缺口**"}
# ★ 非独立值契约：推导式操作数与区间端点**不是独立事实**，显式声明（而非静默丢弃），
#   供脱敏阶段排除出「未建模缺口」——它们是公式/区间的组成部分。
_ns = {}
for t in formula_terms:
    for v in re.findall(r"[\d.]+", t["term"]):
        _ns.setdefault(v, "推导式操作数（公式的一部分，非独立事实）")
for c in chunks:
    for lo, hi, unit in RANGE_V.findall(c.get("text") or ""):
        for v in (lo, hi):
            _ns.setdefault(v, f"区间端点（该区间已建模为一条区间事实 {lo}~{hi} {unit}）")
W(R / "quality" / "nonstandalone_values.json",
  {"count": len(_ns), "note": "已声明为非独立值：不计入未建模缺口（显式声明，非静默丢弃）",
   "values": _ns})
report["nonstandalone"] = {"count": len(_ns), "values": _ns}
W(R / "quality" / "fill_dedup_report.json", report)
print(json.dumps({k: (v if not isinstance(v, dict) else
                      {kk: vv for kk, vv in v.items() if kk not in ("sample", "merged_detail", "formula_sample")})
                  for k, v in report.items()}, ensure_ascii=False, indent=2))


# ★ 环节自报（四元交叉的 A 来源；必须由本环节自己写，不得由 harness 代写）
try:
    import sys as _sys2
    _sys2.path.insert(0, str(Path(__file__).resolve().parent)) if "Path" in dir() else None
    from self_report import declare as _declare
    _declare("s4b", ['SHUFE-BDC-2019-001/quality/fill_dedup_report.json',
                              'SHUFE-BDC-2019-001/graph/graph.yaml',
                              'SHUFE-BDC-2019-001/graph/nodes.yaml',
                              'SHUFE-BDC-2019-001/quality/nonstandalone_values.json'], script="s4b_fill_dedup.py")
except Exception as _e:
    print(f"[self_report] 未写出: {_e}")
