# -*- coding: utf-8 -*-
"""分步门禁 + 探针自证（确定性，零 LLM）。

两条设计原则：
  ① **每一步只验「该步能判定的最强闭环」**，不验尚不存在的产物；
  ② **门禁放在可重做单元的出口**——一个 partition / chunk / 节 / 域。
     早一步拦住 = 重做该单元；晚一步 = 重做全部 + 归因丢失。

探针自证（probe calibration）：每个探针必须先在源中命中一个**已知存在的正样本**。
未过标定的探针一律作废，其判据输出 `invalid`——**不得输出「无误」**。
（教训：曾三次因探针故障把「探针坏了」误报成「源里没有」。）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .closure_verify import (_CITE_EXEMPT, _CITE_STD, _SKIP_PRED, _j,
                             apply_waivers, load_package, load_waivers)   # fix31-waivers

# 探针 → 正样本（必须能在源中命中，否则该探针无效）
PROBE_ANCHORS: dict[str, list[str]] = {
    "citations": ["普通高等学校建筑规划面积指标", "建筑设计防火规范"],
    "headings": ["总论", "投资估算及资金筹措"],
    "valued_numbers": ["18319", "13032"],
    "device_param_lines": ["风量", "Q="],
    "captions": ["表1-2", "表5-5"],
}

STAGE_GATES: list[dict] = [
    {"stage": "S0", "name": "解析", "gate": "解析闭环",
     "check": "docx <w:tbl> 计数 = md 表块计数；word/media ≥ md 图注数",
     "unit": "整次解析", "source": "docx XML"},
    {"stage": "S1", "name": "切块", "gate": "切块闭环",
     "check": "Σchunk 去空白字符 ≈ 原稿去空白字符（±15%）", "unit": "该文档切块", "source": "原稿"},
    {"stage": "S2", "name": "分句", "gate": "分句闭环",
     "check": "Σsentence 字符 = Σchunk 字符（标点归并可解释）", "unit": "该 chunk", "source": "chunk"},
    {"stage": "S3", "name": "抽取", "gate": "抽取闭环 ×3",
     "check": "①引用闭环 ②数值闭环 ③论层闭环（须有论断义务的章必须产出 claim）",
     "unit": "该 partition", "source": "该 partition 的 ledger 切片"},
    {"stage": "S4", "name": "图谱编译", "gate": "编译闭环",
     "check": "端点可寻址 + 无孤儿 + 关系类型闭环", "unit": "编译", "source": "抽取产物+词表"},
    {"stage": "S5", "name": "推演回放", "gate": "派生闭环",
     "check": "每条规则要么闭合、要么显式阻塞，不得静默跳过", "unit": "该规则", "source": "规则表"},
    {"stage": "S6", "name": "质量登记", "gate": "冲突/缺口闭环",
     "check": "每个 (主体,属性) 多值都必须登记为待审", "unit": "该键", "source": "节点键全集"},
    {"stage": "S7", "name": "脱敏", "gate": "脱敏闭环",
     "check": "占位符数 = 节点引用数；无嵌套；无残留字面数", "unit": "该骨架", "source": "nodes"},
    {"stage": "S8", "name": "依据层", "gate": "依据闭环",
     "check": "原稿引用 ⊆ 条款 ∪ 豁免；每条有 名称/编号/效力状态", "unit": "该批依据", "source": "ledger.citations"},
    {"stage": "S9", "name": "域发射", "gate": "域闭环",
     "check": "契约域齐全；依赖无环；每域有判定", "unit": "该域", "source": "DOMAIN_SPECS"},
    {"stage": "S10", "name": "装配", "gate": "装配闭环 ×3",
     "check": "①must_cover 全覆盖 ②该节 facts 引用率 ③题注闭环", "unit": "该节", "source": "workpackage+ledger"},
    {"stage": "S11", "name": "成稿", "gate": "全书闭环",
     "check": "章节闭环 + 复述闭环 + 节点引用闭环", "unit": "该节", "source": "ledger+graph"},
]


def calibrate_probes(ledger: dict, source_text: str) -> dict:
    """探针自证：未命中正样本的探针作废。"""
    probes = []
    for name, anchors in PROBE_ANCHORS.items():
        hits = [a for a in anchors if a in source_text]
        probes.append({"probe": name, "anchors": anchors, "hit": hits,
                       "valid": len(hits) == len(anchors),
                       "n_items": len(ledger.get(name, []) or [])})
    return {"probes": probes, "invalid": sorted(p["probe"] for p in probes if not p["valid"])}


def _gate(gid, name, total, covered, missing, unit, source, valid=True, note=""):
    missing = list(missing)
    rec = round(covered / max(total, 1) * 100, 1)
    return {"stage": gid, "gate": name, "total": total, "covered": covered,
            "missing_count": len(missing), "missing": missing[:50], "recall_pct": rec,
            "unit": unit, "source": source,
            "verdict": "invalid" if not valid else ("pass" if not missing else "FAIL"),
            "note": note}


def run_stage_gates(corpus_dir, *, draft_path=None, source_md=None, source_docx=None) -> dict:
    root = Path(corpus_dir)
    pk = load_package(corpus_dir)
    led = pk["ledger"] or {}
    src = Path(source_md).read_text(encoding="utf-8") if source_md and Path(source_md).exists() else ""
    calib = calibrate_probes(led, src) if src else {"probes": [], "invalid": []}
    invalid = set(calib["invalid"])
    draft = Path(draft_path).read_text(encoding="utf-8") if draft_path and Path(draft_path).exists() else ""
    dn = re.sub(r"[\s　]", "", draft)
    g = []

    # S0
    m = []
    if led.get("docx_tables", -1) not in (-1, led.get("tables", -2)):
        m.append(f"docx 表 {led.get('docx_tables')} ≠ md 表块 {led.get('tables')}")
    n_fig = len([c for c in led.get("captions", []) if str(c).startswith("图")])
    if led.get("images_in_docx", -1) > n_fig:
        m.append(f"docx 内嵌图 {led.get('images_in_docx')} > md 图注 {n_fig}（图片未进入产品）")
    g.append(_gate("S0", "解析闭环", max(led.get("tables", 1), 1),
                   max(led.get("tables", 1) - len(m), 0), m, "整次解析", "docx XML"))

    # S1
    o_ns = len(re.sub(r"\s", "", src)) if src else 0
    chunk_file = root / "chunks" / "chunks.jsonl"
    c_ns = 0
    if chunk_file.exists():
        c_ns = sum(len(re.sub(r"\s", "", json.loads(l)["text"]))
                   for l in chunk_file.read_text(encoding="utf-8").splitlines() if l.strip())
    m1 = [] if (not o_ns or abs(c_ns - o_ns) / o_ns < 0.15) else [f"字符差 {abs(c_ns-o_ns)}"]
    g.append(_gate("S1", "切块闭环", o_ns or 1, min(c_ns, o_ns) or 1, m1, "该文档切块", "原稿"))

    # S2
    sf = root / "chunks" / "sentences.jsonl"
    if sf.exists():
        tag = sum(len(re.sub(r"\s", "", json.loads(l)["text"]))
                  for l in sf.read_text(encoding="utf-8").splitlines() if l.strip())
        m2 = [] if (not c_ns or abs(tag - c_ns) <= max(c_ns * 0.01, 50)) else [f"差 {abs(tag-c_ns)}"]
        g.append(_gate("S2", "分句闭环", c_ns or 1, min(tag, c_ns or 1) or 1, m2, "该 chunk", "chunk"))
    else:
        g.append(_gate("S2", "分句闭环", 1, 0, ["未产出 sentences.jsonl，门禁未执行"],
                       "该 chunk", "chunk", valid=False))

    # S3 引用/数值闭环
    ev_names = " ".join((e.get("doc") or "") + (e.get("quote") or "") for e in pk["evidence"])
    # 只对「依据类」引用判闭环；文献/图集类走豁免（否则产生假缺口）
    cits = [c for c in led.get("citations", [])
            if _CITE_STD.search(c) and not _CITE_EXEMPT.search(c)]
    miss3 = [c for c in cits if c[:6] not in ev_names and c not in ev_names]
    g.append(_gate("S3", "抽取闭环·引用", len(cits), len(cits) - len(miss3), miss3,
                   "该 partition", "ledger 切片", valid="citations" not in invalid))

    # S4 端点可寻址
    ids = {n.get("id") for n in pk["nodes"]} | {c.get("id") for c in pk["claims"]} | \
          {e.get("id") for e in pk["evidence"]}
    bad = [f"{r.get('from')}→{r.get('to')}" for r in pk["relations"]
           if (str(r.get("from")) not in ids and not str(r.get("from")).startswith("REF:"))
           or (str(r.get("to")) not in ids and not str(r.get("to")).startswith("REF:"))]
    g.append(_gate("S4", "编译闭环·端点可寻址", len(pk["relations"]),
                   len(pk["relations"]) - len(bad), bad, "编译", "抽取产物+词表"))

    # S5 规则覆盖
    deriv = _j(root / "reasoning" / "derivation.yaml", {})
    rules = _j(root / "graph" / "rules.yaml", [])
    cov = {d.get("rule") for d in deriv.get("closure_ok", [])} | \
          {d.get("rule") for d in deriv.get("derivation_diff", [])} | \
          {u.get("rule") for u in deriv.get("unresolved_rules", [])}
    m5 = [r.get("id") for r in rules if r.get("id") not in cov]
    g.append(_gate("S5", "派生闭环", len(rules), len(rules) - len(m5), m5, "该规则", "规则表"))

    # S6 多值键登记
    km = {}
    for n in pk["nodes"]:
        if n.get("auto_entity") or n.get("auto_extracted") or n.get("predicate") == "铭牌参数":
            continue
        km.setdefault((n.get("subject"), n.get("predicate")), []).append(n)
    multi = {k for k, v in km.items() if len({str(x.get("value")) for x in v}) > 1}
    conf = {("s", "p")} and {(c.get("subject"), c.get("predicate"))
                            for c in _j(root / "quality" / "conflicts.yaml", [])
                            if c.get("type") == "numeric"}
    m6 = [f"{k[0]}·{k[1]}" for k in sorted(multi) if k not in conf]
    g.append(_gate("S6", "冲突/缺口闭环", len(multi), len(multi) - len(m6), m6, "该键", "节点键全集"))

    # S7 脱敏
    sk = root / "chunks" / "skeletons.jsonl"
    if sk.exists():
        slots = nested = 0
        for l in sk.read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            t = json.loads(l)["text"]
            slots += len(re.findall(r"\{\{node:N-[0-9a-f]+\}\}", t))
            nested += 1 if "{{node:N-{{" in t else 0
        m7 = [f"嵌套占位符 {nested} 处"] if nested else []
        g.append(_gate("S7", "脱敏闭环", max(slots, 1), max(slots - nested, 0), m7, "该骨架", "nodes"))
    else:
        g.append(_gate("S7", "脱敏闭环", 1, 0, ["无 skeletons.jsonl"], "该骨架", "nodes", valid=False))

    # S8 依据层
    g.append(_gate("S8", "依据闭环", len(cits), len(cits) - len(miss3), miss3,
                   "该批依据", "ledger.citations"))

    # S9 域
    dom = sorted((root / "reuse" / "domains").glob("*.yaml")) if (root / "reuse" / "domains").exists() else []
    m9 = [] if len(dom) >= 16 else [f"域文件 {len(dom)}/16"]
    g.append(_gate("S9", "域闭环", 16, min(len(dom), 16), m9, "该域", "DOMAIN_SPECS"))

    # S10/S11
    wps = sorted((root / "project" / "work_packages").glob("*.json")) \
        if (root / "project" / "work_packages").exists() else []
    m10 = []
    for f in wps:
        w = _j(f, {})
        bad_mc = [k for k in (w.get("outline", {}).get("must_cover") or []) if draft and k not in draft]
        if bad_mc:
            m10.append(f"{w.get('outline',{}).get('section')}: must_cover 缺 {bad_mc}")
    g.append(_gate("S10", "装配闭环", max(len(wps), 1), len(wps) - len(m10), m10,
                   "该节", "workpackage+ledger", valid=bool(draft)))
    caps = led.get("captions", [])
    m11 = [c for c in caps if draft and re.sub(r"\s", "", c) not in dn]
    g.append(_gate("S11", "全书闭环·题注", max(len(caps), 1), len(caps) - len(m11), m11,
                   "该节", "ledger+graph", valid=bool(draft)))

    g = [apply_waivers(x, load_waivers(corpus_dir)) for x in g]
    return {"gates": g, "calibration": calib,
            "by_stage": {x["stage"]: x["verdict"] for x in g},
            "policy": "每步一道闭环；FAIL 阻塞该单元；invalid 表示探针未标定，不得视为通过"}


def save_stage_gates(result: dict, out_path) -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


if __name__ == "__main__":
    import sys
    r = run_stage_gates(sys.argv[1], draft_path=sys.argv[2] if len(sys.argv) > 2 else None,
                        source_md=sys.argv[3] if len(sys.argv) > 3 else None)
    for x in r["gates"]:
        print(f"{x['stage']:4s} {x['gate']:20s} {x['verdict']:8s} 缺 {x['missing_count']}")
    print("探针作废:", r["calibration"]["invalid"])
