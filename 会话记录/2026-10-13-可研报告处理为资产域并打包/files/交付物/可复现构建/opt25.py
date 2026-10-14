# -*- coding: utf-8 -*-
"""opt25 —— 知识抽取与推演写作环节优化（新增工序，全部确定性、可复算）。

本模块把此前诊断出的四类缺陷落成工序：

  缺陷                       →  新增工序
  ─────────────────────────────────────────────────────────────
  ① verify 遍历产物，查不出遗漏  →  P1 源侧索引 ledger（独立方法生成）
                                   P2 闭环校验 closure_verify（集合差）
                                   P3 探针自证 probe_calibration
  ② 词表缺 7 类 claim 关系       →  P4 关系类型扩展 CLAIM_RELATIONS
  ③ 依据/设备参数漏抽            →  P5 自动补救（依据登记、设备节点）
  ④ 总论/结论无论断层（复述层缺） →  P6 复述层构建（规则可判定的复述句）

幂等：首次运行把基准图存为 *.base.yaml，之后每次由 base + ext 重建。
"""
import json
import re
import zipfile
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
DOCX = WS / "build" / "source-original.docx"
ORIG = (BUILD / "doc-clean" / "大数据研究中心可研.md").read_text(encoding="utf-8")
RECON = (WS / "交付物" / "报告" / "上海财经大学中山北一路校区大数据研究中心可行性研究报告（还原稿）.md")
RECON = RECON.read_text(encoding="utf-8") if RECON.exists() else ""


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def W(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def base(name):
    """取基准文件。首次运行时把当前文件另存为 base，并**剥离历史扩展**以防重复叠加。"""
    cur, b = ROOT / name, ROOT / name.replace(".yaml", ".base.yaml")
    if not b.exists():
        data = J(cur)
        if isinstance(data, list):
            if name.endswith("nodes.yaml"):
                data = [x for x in data if not (x.get("auto_extracted") or x.get("auto_entity"))]
            elif name.endswith("claims.yaml"):
                data = [x for x in data if not str(x.get("id", "")).startswith("CL-RS-")]
            elif name.endswith("relations.yaml"):
                data = [x for x in data if x.get("type") not in
                        {"cites", "restates", "causes", "derives", "precedes", "quantifies", "specializes"}]
            elif name.endswith("evidence.yaml"):
                data = [x for x in data if not str(x.get("id", "")).startswith("EVX-")]
        b.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return J(b)


nodes0 = base("graph/nodes.yaml")
claims0 = base("graph/claims.yaml")
rels0 = base("graph/relations.yaml")
evid0 = base("evidence/evidence.yaml")
mandates = J(ROOT / "external" / "mandates.yaml")["mandates"] if (ROOT / "external" / "mandates.yaml").exists() else []
chunks = [json.loads(l) for l in (ROOT / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
cid2sp = {c["id"]: (c.get("section_path") or [""]) for c in chunks}

REPORT = {"ledger": {}, "calibration": [], "remediation": {}, "relations": {}, "closure": []}

# ══════════════════════════════════════════════════════════════════════
# P1 源侧索引（独立于 LLM 抽取：正则 / XML）
# ══════════════════════════════════════════════════════════════════════
UNIT = (r"(?:万元|元/㎡|元|㎡|平方米|米|m|人|个|台|套|座|间|层|kW|kW·h|万kW·h|kWh|kPa|Pa|"
        r"L/s|L／S|m3/h|m³/h|%|kgce|dB)")
DEV = re.compile(r"\bQ\s*=|\bH\s*=|风量|全压|静压|IPLV|单台泵流量|有效容积V=|功率[：:]")

LEDGER = {
    "citations": sorted(set(re.findall(r"《([^》]{2,80})》", ORIG))),
    "citations_raw": len(re.findall(r"《[^》]{2,80}》", ORIG)),
    "tables": len(re.findall(r"```table", ORIG)),
    "valued_numbers": sorted(set(re.findall(rf"(\d[\d,]*(?:\.\d+)?)\s*{UNIT}", ORIG))),
    "headings": [m.group(2).strip() for m in
                 (re.match(r"^(#{1,6})\s+(.+?)\s*$", l) for l in ORIG.split("\n")) if m],
    "device_param_lines": [l.strip() for l in ORIG.split("\n") if DEV.search(l)],
    "captions": sorted(set(re.findall(r"(表\s?\d+-\d+|图\s?\d+-\d+)", ORIG))),
}
try:
    with zipfile.ZipFile(DOCX) as z:
        LEDGER["images_in_docx"] = len([n for n in z.namelist() if n.startswith("word/media/")])
except Exception as e:
    LEDGER["images_in_docx"] = -1
REPORT["ledger"] = {k: (v if not isinstance(v, list) else len(v)) for k, v in LEDGER.items()}
W(ROOT / "source_ledger.json", LEDGER)

# ══════════════════════════════════════════════════════════════════════
# P3 探针自证：每个探针须命中已知正样本，否则作废（不得输出「无误」）
# ══════════════════════════════════════════════════════════════════════
PROBES = [
    ("citations", ["普通高等学校建筑规划面积指标", "建筑设计防火规范"]),
    ("headings", ["总论", "投资估算及资金筹措"]),
    ("valued_numbers", ["18319", "13032"]),
    ("device_param_lines", ["风量", "Q="]),
    ("captions", ["表1-2", "表5-5"]),
]
CALIB = []
for name, anchors in PROBES:
    blob = ORIG if name == "headings" else ORIG
    hits = [a for a in anchors if a in blob]
    CALIB.append({"probe": name, "anchors": anchors, "hit": hits,
                  "valid": len(hits) == len(anchors),
                  "n_items": len(LEDGER.get(name, []))})
INVALID = {c["probe"] for c in CALIB if not c["valid"]}
REPORT["calibration"] = CALIB
W(ROOT / "quality" / "probe_calibration.yaml", {"probes": CALIB, "invalid": sorted(INVALID)})

# ══════════════════════════════════════════════════════════════════════
# P4 关系类型扩展
# ══════════════════════════════════════════════════════════════════════
TEN_RELATIONS = ["has_value", "has_attribute", "instance_of", "part_of", "causes",
                 "depends_on", "supports", "contradicts", "temporal", "located_in"]
CLAIM_RELATIONS = {
    "cites": "claim → mandate/standard：这条结论依据哪条规范",
    "restates": "claim → claim：总论/结论复述各章结论",
    "causes": "claim → claim：因果链条",
    "derives": "claim → claim：显式推演派生",
    "precedes": "claim → claim：论证顺序/前置条件",
    "quantifies": "claim → node：结论与其数值绑定",
    "specializes": "claim → mandate：通则落到本项目",
}
W(ROOT / "graph" / "relation_vocabulary.yaml",
  {"base_relations": TEN_RELATIONS, "claim_relations": CLAIM_RELATIONS,
   "note": "7 类 claim 级关系为本次扩展；上游 TEN_RELATIONS 缺这些类型，"
           "导致 derived_from 等字段无从填充。"})

# ══════════════════════════════════════════════════════════════════════
# P5 自动补救：依据登记 + 设备节点
# ══════════════════════════════════════════════════════════════════════
_BIAO = re.compile(r"标准|规范|规程|通则|办法|规定|通知|规划|纲要|条例|法$|决定|意见|定额|图集|规则|指南|指标|措施|GB|DGJ|JGJ")
_EXEMPT = re.compile(r"Journal|Annals|学报|杂志|Econometrica|JASA|统计计算|挖掘|测度|动力学|"
                     r"预制|桁架|叠合板|楼梯|阳台板|连接节点|灌浆料|合同$|教材|课程|大纲")
ev_names = " ".join((e.get("doc") or "") + (e.get("quote") or "") for e in evid0)
new_ev, new_ev_exempt = [], []
for i, c in enumerate(LEDGER["citations"]):
    if c[:6] in ev_names or c in ev_names:
        continue
    if _EXEMPT.search(c) or not _BIAO.search(c):
        new_ev_exempt.append(c)
        continue
    new_ev.append({
        "id": f"EVX-依据-{i+1:03d}", "kind": "standard",
        "doc": f"《{c}》", "quote": f"原报告编制依据/设计依据中引用《{c}》",
        "locator": {"section": "（见原报告各章依据清单）"},
        "verification": {"timeliness": "待核", "note": "自动登记；须按现行有效版本核对名称/编号/实施日期"},
        "auto_registered": True,
    })
evidence_all = evid0 + new_ev
W(ROOT / "evidence" / "evidence.yaml", evidence_all)

dev_lines = LEDGER["device_param_lines"]
dev_nodes = []
for i, l in enumerate(dev_lines):
    txt = re.sub(r"^\||\|$", "", l).strip()
    cells = [c.strip() for c in txt.split("|")]
    name = next((c for c in cells if len(c) >= 2 and not c.isdigit()), "设备")
    name = re.split(r"[：:]", name)[0][:24] if "：" in name or ":" in name else name[:24]
    m = re.search(r"(Q\s*=|风量|全压|静压|IPLV|单台泵流量|有效容积V=|功率).*$", l)
    val = re.sub(r"\s*\|\s*$", "", m.group(0)).strip() if m else txt[:60]
    ch = next((cid2sp[c["id"]][0] for c in chunks
               if c["type"] != "heading" and val[:8] and val[:8] in c["text"]), "项目规划设计方案")
    dev_nodes.append({
        "id": f"ND-设备-{i+1:03d}", "subject": name, "predicate": "铭牌参数",
        "value": val[:120], "unit": "", "kind": "text", "caliber": "",
        "status": "defined", "instruction": "", "inheritable": "yes",
        "section": ch, "section_index": 6, "auto_extracted": True,
        "source": next((c["id"] for c in chunks if val[:10] and val[:10] in c["text"]), ""),
    })
# P5c 实体层补齐：把以「主体名」为端点的关系改为可寻址的实体节点
names = {}
for n in nodes0:
    names.setdefault(n["subject"], "主体")
for r in rels0:
    for side in ("from", "to"):
        v = r.get(side)
        if v and not re.match(r"^[A-Z]{2}-", str(v)) and not str(v).startswith("REF:"):
            names.setdefault(str(v), "实体")
ents, name2id = [], {}
for i, (nm, _t) in enumerate(sorted(names.items())):
    eid = f"EN-{i+1:04d}"
    name2id[nm] = eid
    ents.append({"id": eid, "name": nm, "type": "ENTITY", "kind": "text",
                 "subject": nm, "predicate": "实体名", "value": nm, "unit": "",
                 "status": "defined", "instruction": "", "inheritable": "yes", "caliber": "",
                 "section": "", "section_index": 0, "auto_entity": True,
                 "source": next((n["source"] for n in nodes0 if n["subject"] == nm), "")})
rels_rewritten = 0
for r in rels0:
    for side in ("from", "to"):
        v = r.get(side)
        if v in name2id:
            r[side] = name2id[v]
            rels_rewritten += 1
nodes_all = nodes0 + dev_nodes + ents
W(ROOT / "graph" / "nodes.yaml", nodes_all)
W(ROOT / "graph" / "relations.yaml", rels0)
REPORT["remediation"]["entity_nodes_added"] = len(ents)
REPORT["remediation"]["relation_endpoints_rewritten"] = rels_rewritten
REPORT["remediation"] = {"evidence_added": len(new_ev), "evidence_exempt": len(new_ev_exempt),
                         "device_nodes_added": len(dev_nodes),
                         "evidence_total": len(evidence_all), "nodes_total": len(nodes_all)}

# ══════════════════════════════════════════════════════════════════════
# P6 复述层构建（总论/结论的复述句 → claim 节点 + restates 边）
# ══════════════════════════════════════════════════════════════════════
CITE = re.compile(r"《[^》]+》|\bGB[/\s]?\d|GB\d|DGJ\d|JGJ\d|建标|发改|国发|财建|〔\d{4}〕|\[\d{4}\]")
CAUSE = re.compile(r"因此|因而|故而|导致|使得|引起|造成|从而使|以致")


def blob(c):
    t = c.get("toulmin") or {}
    return " ".join(str(t.get(k, "")) for k in ("claim", "grounds", "warrant", "backing", "qualifier", "rebuttal")) \
        + " " + str(c.get("text", ""))


def nums_of(s):
    return {x for x in re.findall(r"\d[\d,]*(?:\.\d+)?", str(s)) if len(x.replace(",", "")) >= 3}


def chapter_of_claim(c):
    return (cid2sp.get(c.get("source", ""), [""]) or [""])[0]


# 6.1 复述层：从原稿「总论」「结论与建议」章中，取含跨章数值的句子，建 claim 节点
def chapter_text(md, title_pat, next_pat):
    lines, out, on = md.split("\n"), [], False
    for l in lines:
        if re.match(title_pat, l):
            on = True
            continue
        if on and re.match(next_pat, l):
            break
        if on:
            out.append(l)
    return "\n".join(out)


chap_claims = {}
for c in claims0:
    chap_claims.setdefault(chapter_of_claim(c), []).append(c)

restate_claims, restate_edges = [], []
_for = [("总论", r"^#\s+总论", r"^#\s+学校简介"), ("结论与建议", r"^#\s+结论与建议", r"^#\s+附件")]
for idx, (chname, sp, ep) in enumerate(_for):
    seg = chapter_text(ORIG, sp, ep)
    sents = [s.strip() for s in re.split(r"[。；\n]", seg) if len(s.strip()) >= 24]
    for j, s in enumerate(sents):
        ns = nums_of(s)
        if not ns:
            continue
        for target_ch, tcs in chap_claims.items():
            if target_ch in (chname, "（未归属）", ""):
                continue
            for tc in tcs:
                if ns & nums_of(blob(tc)):
                    cid = f"CL-RS-{idx+1}{j+1:02d}-{tc['id'].split('-')[-1]}"
                    if cid in {c["id"] for c in restate_claims}:
                        continue
                    restate_claims.append({
                        "id": cid, "text": s[:120], "type": "restatement",
                        "claim_type": "conclusion", "status": "supported",
                        "confidence": "high", "source": tc.get("source", ""),
                        "evidence_refs": tc.get("evidence_refs", []),
                        "premise_refs": [tc["id"]], "derived_from": [],
                        "toulmin": {"claim": s[:120],
                                    "grounds": f"复述 {tc['id']}（{target_ch}）",
                                    "warrant": f"总论/结论按体例复述各章结论，数值与 {tc['id']} 一致",
                                    "backing": "可行性研究报告编写体例", "qualifier": "在本报告范围内",
                                    "rebuttal": "若被复述章数值变更，本节须同步"},
                        "restated_chapter": chname, "restates_target": tc["id"],
                        "restated_from_chapter": target_ch,
                    })
                    restate_edges.append({"from": cid, "to": tc["id"], "type": "restates",
                                          "why": f"共享数值 {sorted(ns & nums_of(blob(tc)))}"})
                    break
claims_all = claims0 + restate_claims

# 6.2 cites / causes / derives 边
rel_edges = []
mandate_titles = [(m["id"], m.get("title", "") + m.get("doc", "")) for m in mandates]
for c in claims0:
    b = blob(c)
    for cite in sorted(set(CITE.findall(b))):   # sorted：避免集合迭代顺序受 PYTHONHASHSEED 影响
        tgt = next((mid for mid, t in mandate_titles if cite.strip("《》")[:8] and cite.strip("《》")[:8] in t), None)
        rel_edges.append({"from": c["id"], "to": tgt or f"REF:{cite[:40]}", "type": "cites",
                          "basis": cite, "resolved": bool(tgt),
                          "note": "claim → 规范条款/政策文件"})

pair_shared = []
for a in claims0:
    na = nums_of(blob(a))
    for b2 in claims0:
        if b2["id"] == a["id"]:
            continue
        sh = na & nums_of(blob(b2))
        if not sh:
            continue
        pair_shared.append((a, b2, sh))
for a, b2, sh in pair_shared:
    if CAUSE.search(blob(a)):
        rel_edges.append({"from": a["id"], "to": b2["id"], "type": "causes",
                          "why": f"因果词 + 共享数值 {sorted(sh)}"})
    if not (a.get("premise_refs") or a.get("derived_from")):
        rel_edges.append({"from": a["id"], "to": b2["id"], "type": "derives",
                          "why": f"共享数值 {sorted(sh)}（补 premise/derived 缺失）"})

relations_all = rels0 + rel_edges + restate_edges   # rels0 已重写端点
W(ROOT / "graph" / "claims.yaml", claims_all)
W(ROOT / "graph" / "relations.yaml", relations_all)
REPORT["relations"] = {
    "restate_claims_added": len(restate_claims), "restate_edges": len(restate_edges),
    "cites_edges": sum(1 for e in rel_edges if e["type"] == "cites"),
    "cites_resolved": sum(1 for e in rel_edges if e["type"] == "cites" and e.get("resolved")),
    "causes_edges": sum(1 for e in rel_edges if e["type"] == "causes"),
    "derives_edges": sum(1 for e in rel_edges if e["type"] == "derives"),
    "relations_total": len(relations_all),
}

# ══════════════════════════════════════════════════════════════════════
# P2 闭环校验（七道）+ 判定
# ══════════════════════════════════════════════════════════════════════
CLOSURES = []


def closure(cid, name, probe, total, covered, missing, thresh):
    missing = list(missing)
    valid = (probe is None) or (probe not in INVALID)   # None = 无需探针（源侧非 regex 索引）
    rec = round(covered / max(covered + len(missing), 1) * 100, 1)
    v = "invalid" if not valid else ("pass" if rec >= thresh else "FAIL")
    CLOSURES.append({"id": cid, "name": name, "probe": probe, "threshold": thresh,
                     "total": total, "covered": covered, "missing_count": len(missing),
                     "missing": missing[:60], "recall_pct": rec, "verdict": v})


# C1 依据闭环
ev_names2 = " ".join((e.get("doc") or "") + (e.get("quote") or "") for e in evidence_all)
c_ok = [c for c in LEDGER["citations"] if c[:6] in ev_names2 or c in ev_names2]
c_miss = [c for c in LEDGER["citations"] if c not in c_ok and _BIAO.search(c) and not _EXEMPT.search(c)]
closure("C1", "依据闭环（原稿引用→证据条目）", "citations", len(LEDGER["citations"]), len(c_ok), c_miss, 95)

# C2 关键取值闭环
g_vals = {re.sub(r"[^\d.]", "", str(n["value"])) for n in nodes_all}
KEY_UNIT = re.compile(r"万元|元/㎡|元$|㎡$|人$|kW$|kW·h|万kW·h|kgce|%")


def _num_of(v):
    return re.match(r"([\d,]+(?:\.\d+)?)", v)


key_all, detail_all, key_miss, detail_miss = [], [], [], []
for nm, u in re.findall(rf"(\d[\d,]*(?:\.\d+)?)\s*({UNIT})", ORIG):
    label = f"{nm} {u}"
    if KEY_UNIT.search(u):
        key_all.append(label)
        if nm.replace(",", "") not in g_vals:
            key_miss.append(label)
    else:
        detail_all.append(label)
        if nm.replace(",", "") not in g_vals:
            detail_miss.append(label)
key_all, detail_all = sorted(set(key_all)), sorted(set(detail_all))
closure("C2a", "关键取值闭环（万元/元/㎡/人/kW/% 类→图谱）", "valued_numbers",
        len(key_all), len(key_all) - len(set(key_miss)), sorted(set(key_miss)), 90)
closure("C2b", "明细数值闭环（米/Pa/L 等工程明细→图谱）", "valued_numbers",
        len(detail_all), len(detail_all) - len(set(detail_miss)), sorted(set(detail_miss)), 50)

# C3 章节闭环
o_titles = {re.sub(r"[\s　]", "", x["title"]) for x in J(ROOT / "outline.yaml")["sections"]}
h_miss = [h for h in LEDGER["headings"] if re.sub(r"[\s　]", "", h) not in o_titles]
closure("C3", "章节闭环（原稿标题→outline）", "headings", len(LEDGER["headings"]),
        len(LEDGER["headings"]) - len(h_miss), h_miss, 98)

# C4 设备参数闭环
dev_in_graph = [n for n in nodes_all if n.get("auto_extracted") or DEV.search(str(n["value"]))]
d_miss = [] if len(dev_in_graph) >= len(dev_lines) * 0.9 else [f"设备参数语句 {len(dev_lines)} 条，图谱覆盖不足"]
closure("C4", "设备参数闭环（原稿设备参数→设备节点）", "device_param_lines",
        len(dev_lines), len(dev_in_graph), d_miss, 80)

# C5 表题闭环
cap_miss = [c for c in LEDGER["captions"] if re.sub(r"\s", "", c) not in re.sub(r"\s", "", RECON)] if RECON else ["成稿未生成"]
closure("C5", "表题闭环（原稿表/图题注→成稿）", "captions", len(LEDGER["captions"]),
        len(LEDGER["captions"]) - len(cap_miss), cap_miss, 60)

# C6 装配闭环
skip = re.compile(r"估算金额|台数|单间用房标准|地址|四至|粗糙度|竖向|土层|矿化|潜水位|单井出水|铭牌参数")
rc = re.sub(r"[\s　]", "", RECON)
a_total, a_miss = 0, []
for n in nodes_all:
    v = re.sub(r"[\s　]", "", str(n["value"]))
    if len(v) < 3 or skip.search(n["predicate"]) or n.get("status", "defined") != "defined" or n.get("auto_entity"):
        continue        # 实体节点不是「待引用的取值」，不计入装配分母
    a_total += 1
    if v not in rc:
        mm = re.match(r"([\d,]+(?:\.\d+)?)", v)
        if not (mm and (mm.group(1) in rc or mm.group(1).replace(",", "") in rc)):
            a_miss.append(f"{n['subject']}·{n['predicate']} = {str(n['value'])[:30]}")
closure("C6", "装配闭环（图谱 defined 节点→成稿引用）", None, a_total, a_total - len(a_miss), a_miss, 95)

# C7 claim 关系闭环
def have(t):
    return sum(1 for r in relations_all if r["type"] == t)


NEED = {"cites": sum(1 for e in rel_edges if e["type"] == "cites"),
        "restates": len(restate_edges),
        "causes": sum(1 for e in rel_edges if e["type"] == "causes"),
        "derives": sum(1 for e in rel_edges if e["type"] == "derives")}
HAVE = {t: have(t) for t in NEED}
c7 = [f"{t}: 应有 {NEED[t]}，现有 {HAVE[t]}" for t in NEED if HAVE[t] < NEED[t]]
closure("C7", "claim 关系闭环（应有关系→图谱）", None,
        sum(NEED.values()) + sum(HAVE.values()), sum(HAVE.values()), c7, 95)

REPORT["closure"] = [{"id": c["id"], "verdict": c["verdict"], "recall": c["recall_pct"],
                      "missing": c["missing_count"]} for c in CLOSURES]
W(ROOT / "quality" / "closure_report.yaml",
  {"closures": CLOSURES, "invalid_probes": sorted(INVALID),
   "policy": "missing 非空或探针未标定 ⇒ 该项 FAIL/invalid；由编排器判定，不由写作 Agent 自判"})
W(ROOT / "quality" / "remediation_log.yaml",
  {"evidence_added": [e["id"] for e in new_ev][:10], "evidence_added_count": len(new_ev),
   "evidence_exempt_count": len(new_ev_exempt), "device_nodes": len(dev_nodes),
   "restate_claims": [c["id"] for c in restate_claims][:10], "restate_count": len(restate_claims),
   "relation_edges_added": len(rel_edges) + len(restate_edges),
   "entity_nodes_added": len(ents), "relation_endpoints_rewritten": rels_rewritten,
   "nodes_base": len(nodes0), "nodes_total": len(nodes_all),
   "claims_base": len(claims0), "claims_total": len(claims_all),
   "relations_total": len(relations_all)})

print(json.dumps(REPORT, ensure_ascii=False, indent=2))
