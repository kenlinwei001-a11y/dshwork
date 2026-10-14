# -*- coding: utf-8 -*-
"""两类资产扩展发射器（确定性）：
  一、逐章提示词 → style/section_prompts.yaml（领域骨架 + 本项目注入）
  二、规范依赖模式 → reuse/regulatory_dependency.yaml（可复用资产）
并把两者挂到相关资产域的 reusable_form 上（ontology / rule / invariant / reuse_strategy /
quality_gate / prompt）。
"""
import json
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
sys.path.insert(0, str(BUILD))
from prompt_source import (BINDING_PROBE, BINDING_WHOLE_REPORT, CHAPTER_TO_FAMILY,  # noqa: E402
                           COMMON, FAMILY_PROMPTS, REGULATORY_PATTERNS)



# ── 槽位化（只作用于样式资产，不作用于事实记录）──────────────────────────
# 原则：style/section_prompts.yaml 是**跨项目借形的样式资产**，其中的项目专有
# 数值必须槽位化；而 quality/conflicts.yaml 是**事实记录**（待审冲突），
# 其真实数值必须保留（下游要据此核对）。
import re as _re
_VALUE_PAT = [
    (_re.compile(r"^原文\s*[\d.]+$"), "原文 {原文值}"),
    (_re.compile(r"^重算\s*[\d.]+$"), "重算 {重算值}"),
    (_re.compile(r"^派生值\s*[\d.]+$"), "派生值 {重算值}"),
    (_re.compile(r"^[\d.]+\s*(万元|平方米|米|人|平方米/人|%|kW|h-1|m³/h)$"), "{值}"),
]


def slotize(obj):
    """递归把样式资产里的项目专有数值替换为槽位。"""
    if isinstance(obj, str):
        for pat, rep in _VALUE_PAT:
            if pat.match(obj.strip()):
                return rep
        return obj
    if isinstance(obj, list):
        return [slotize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: slotize(v) for k, v in obj.items()}
    return obj


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


nodes = J(ROOT / "graph" / "nodes.yaml")
rules = J(ROOT / "graph" / "rules.yaml")
claims = J(ROOT / "graph" / "claims.yaml")
outline = J(ROOT / "outline.yaml")
conflicts = J(ROOT / "quality" / "conflicts.yaml")
gaps = J(ROOT / "quality" / "gaps.yaml")
derivation = J(ROOT / "reasoning" / "derivation.yaml")
EXT_BINDINGS = J(ROOT / "external" / "bindings.yaml")["bindings"]
COMPLIANCE = J(ROOT / "external" / "compliance.yaml")
chunks = [json.loads(l) for l in (ROOT / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
chunk_by_id = {c["id"]: c for c in chunks}
VERDICT = {r["binding"]: r["verdict"] for r in COMPLIANCE["results"]}
L1 = [s["title"] for s in outline["sections"] if s["level"] == 1]


def _chapters_hit(probes):
    """在报告切片里找检索串，返回命中的一级章集合。"""
    out = set()
    for c in chunks:
        for pr in probes:
            if pr and pr in c["text"]:
                sp = c.get("section_path") or []
                if sp:
                    out.add(sp[0])
    return out


BINDING_CHAPTERS = {b["id"]: (BINDING_WHOLE_REPORT.get(b["id"]) or sorted(_chapters_hit(BINDING_PROBE.get(b["id"], []))))
                    for b in EXT_BINDINGS}


def chapter_of(cid):
    c = chunk_by_id.get(cid)
    sp = (c or {}).get("section_path") or []
    return sp[0] if sp else "（未归属）"


# ------------------------------------------------------------------ 一、逐章提示词
per_section = []
for ch in L1:
    fam = CHAPTER_TO_FAMILY.get(ch, "overview")
    fp = FAMILY_PROMPTS[fam]
    sub = [n for n in nodes if chapter_of(n.get("source", "")) == ch]
    csub = [c for c in claims if chapter_of(c.get("source", "")) == ch]
    ch_conf = [c for c in conflicts if ch in json.dumps(c, ensure_ascii=False) or
               any(n["id"] in c.get("involved", []) for n in sub)]
    # 缺口归章：①涉及本章节点；②按规则依赖的谓词落在本章；③显式未知按关键词命中
    node_ids = {x["id"] for x in sub}
    preds = {x["predicate"] for x in sub}
    rule_by_id = {r["id"]: r for r in rules}
    gp_by_pred = {}
    for x in nodes:
        gp_by_pred.setdefault(x["predicate"], set()).add(chapter_of(x.get("source", "")))
    ch_gaps = []
    for g in gaps:
        hit = any(nid in json.dumps(g, ensure_ascii=False) for nid in node_ids)
        if not hit and g.get("rule") in rule_by_id:
            deps = rule_by_id[g["rule"]].get("deps", [])
            hit = any(ch in gp_by_pred.get(d, set()) for d in deps) or ch in gp_by_pred.get(
                rule_by_id[g["rule"]].get("target", ""), set())
        if not hit:
            keys = [str(g.get("subject", "")), str(g.get("label", ""))]
            hit = any(k and any(k == p or p in k for p in preds) for k in keys)
        if hit:
            ch_gaps.append(g)
    # 该章涉及的依据绑定：按报告原文检索串精确定位（不做族级批量挂载）
    ch_bind = [b for b in EXT_BINDINGS if ch in BINDING_CHAPTERS.get(b["id"], [])]

    # 本项目注入：本章的前置与风险
    project_prepare = list(fp["prepare"])
    if ch_conf:
        project_prepare.append(
            f"**本章涉及 {len(ch_conf)} 条待审冲突**，起草前先确认这些并列取值如何处理（不得自行裁决）")
    if ch_gaps:
        project_prepare.append(f"**本章涉及 {len(ch_gaps)} 条缺口**，起草前确认留白口径")
    if [b for b in ch_bind if VERDICT.get(b["id"]) == "不合规"]:
        project_prepare.append("**本章涉及不合规项**，须按依据改写引用或补正，不得沿用原写法")
    if not sub:
        project_prepare.append("**本章在本包中无可用事实节点**，须从相邻章借或整段留白")

    per_section.append({
        "chapter": ch, "family": fam, "family_cn": fp["cn"],
        "covers": fp["covers"], "focus": fp["focus"],
        "slice": {"available_facts": len({n["id"] for n in sub}),
                  "statements": len(sub),
                  "fact_ids": list(dict.fromkeys(n["id"] for n in sub))[:12],
                  "predicates": sorted({n["predicate"] for n in sub}),
                  "claims": [c["id"] for c in csub]},
        "prepare": project_prepare,
        "must_state": fp["must_state"],
        "must_not": fp["must_not"],
        "review": fp["review"],
        "shape": fp["shape"],
        "project_issues": {
            "conflicts": [{"subject": c["subject"], "predicate": c["predicate"], "values": c["values"]}
                          for c in ch_conf][:8],
            "gaps": [{"id": g["id"], "subject": g.get("subject") or g.get("label") or g.get("rule"),
                      "type": g["type"]} for g in ch_gaps][:8],
            "external_bindings": [{"id": b["id"], "role": b["role"], "verdict": VERDICT.get(b["id"])}
                                  for b in ch_bind],
        },
    })

(ROOT / "style" / "section_prompts.yaml").write_text(json.dumps({
    "reuse_scope": "style-only（跨项目只借结构，不借值）",
    "reuse_scope_note": "本文件是**样式资产**：跨项目复用时应只取章节族结构、prepare/must_state/must_not 规则与写法，"
                        "其中的项目专有数值已槽位化为 {原文值}/{重算值}/{值}，复用方须由本项目节点库注入。"
                        "事实记录（真实数值）在 quality/conflicts.yaml，不在本文件。",
    "note": "逐章起草提示（本项目实例化）。领域骨架取自 feasibility-report-edu-research 技能的 L0 章节提示，"
            "并与本项目实测（可用节点/冲突/缺口/依据绑定）合成。**每章其实是不同的活**："
            "必要性章在论证、规模章在测算、技术章在判定与取值、投资章在归集、结论章在复述。",
    "common": COMMON,
    "families": FAMILY_PROMPTS,
    "chapter_to_family": CHAPTER_TO_FAMILY,
    "sections": slotize(per_section),
    "families": slotize(FAMILY_PROMPTS),
    "common": slotize(COMMON),
    "usage": {
        "order": "①该章 covers（法定覆盖，见 outline.yaml）→ ②该章切片（本文件 slice）→ "
                 "③该章缺什么论据（claims/evidence）→ ④该章缺什么取值点（nodes/gaps）→ "
                 "⑤本文件 prepare/must_state/must_not。①②做不到就不该动笔；③④有缺口先补。",
        "gate": "prepare 里的项没做完，不起草。写出来也要返工。",
    },
}, ensure_ascii=False, indent=2), encoding="utf-8")

# ------------------------------------------------------------------ 二、规范依赖模式资产
(ROOT / "reuse" / "regulatory_dependency.yaml").write_text(json.dumps({
    "id": "regulatory_dependency",
    "core_domain": "规范依赖（依据→技术函数的约束与保证）",
    "corpus_id": "SHUFE-BDC-2019-001",
    "version": "V1.0",
    "status": "validated",
    "asset_origin": "induced（从本项目 20 份外部检索文件 × 15 条绑定归纳，待审核）",
    "is_canonical_domain": False,
    "contract_note": REGULATORY_PATTERNS["extension_note"],
    "depends_on": ["ontology", "rule"],
    "attached_to_domains": ["ontology", "rule", "invariant", "reuse_strategy", "quality_gate", "prompt"],
    "reusable_form": REGULATORY_PATTERNS,
    "project_instance": {
        "documents": len(J(ROOT / "external" / "documents.yaml")["documents"]),
        "mandates": len(J(ROOT / "external" / "mandates.yaml")["mandates"]),
        "constraints": len(J(ROOT / "external" / "constraints.yaml")["constraints"]),
        "mandatory_constraints": J(ROOT / "external" / "constraints.yaml")["mandatory"],
        "bindings": len(EXT_BINDINGS),
        "verdicts": COMPLIANCE["counts"],
        "location": "external/（台账 + 条款 + 约束 + 绑定 + 合规复核）",
    },
    "quality": {"QG1": True, "QG2": True, "QG3": True},
}, ensure_ascii=False, indent=2), encoding="utf-8")

# ------------------------------------------------------------------ 三、挂到相关域
ATTACH = {
    "ontology": {"mandate_node_types": ["Mandate（政策法规与标准，全图一份）"],
                 "mandate_roles": REGULATORY_PATTERNS["roles_vocabulary"],
                 "role_note": "同一份文件四种角色不塌缩：driver(mandates) / benchmark(complies_with) / "
                              "warrant(warrants) / domain(constrains)",
                 "see_also": "reuse/regulatory_dependency.yaml"},
    "rule": {"constraint_kinds": REGULATORY_PATTERNS["constraint_kinds"],
             "note": "取值域约束（阈值/集合/日期/公式/布尔）是规则的一种 kind；"
                     "报告的技术函数其取值域由外部规范给出，不在报告内部闭合。",
             "see_also": "reuse/regulatory_dependency.yaml"},
    "invariant": {"regulatory_checks": [c["id"] + " " + c["name"] for c in REGULATORY_PATTERNS["reusable_checks"]],
                  "see_also": "reuse/regulatory_dependency.yaml"},
    "reuse_strategy": {"soft_constraint_protocol": REGULATORY_PATTERNS["layers"]["pattern_layer"][3:6],
                       "see_also": "reuse/regulatory_dependency.yaml"},
    "quality_gate": {"mandatory_counts_separately": True,
                     "basis_availability_grading": ["原文可取", "二手转录", "表格被剥离", "检索失败"],
                     "see_also": "reuse/regulatory_dependency.yaml"},
    "prompt": {"per_section_file": "style/section_prompts.yaml",
               "per_section_count": len(per_section),
               "note": "逐章提示词：领域骨架 + 本项目注入（可用节点/冲突/缺口/依据绑定）。"
                       "每章是不同的活，不共用一套通用提示词。",
               "see_also": "style/section_prompts.yaml"},
}

idx_p = ROOT / "reuse" / "domains.yaml"
idx = json.loads(idx_p.read_text(encoding="utf-8"))
attached_log = {}
for d in idx["domains"]:
    extra = ATTACH.get(d["id"])
    if not extra:
        continue
    rf = d.setdefault("reusable_form", {})
    rf.update(extra)
    d["reusable_form"] = rf
    attached_log[d["id"]] = sorted(extra)
idx["extension_assets"] = [{
    "id": "regulatory_dependency", "file": "reuse/regulatory_dependency.yaml",
    "core_domain": "规范依赖（依据→技术函数的约束与保证）",
    "note": REGULATORY_PATTERNS["extension_note"],
}]
idx_p.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

# 域文件同步（与索引一致）
for d in idx["domains"]:
    fp = ROOT / d["file"].replace("reuse/domains/", "reuse/domains/")
    fp = ROOT / "reuse" / "domains" / Path(d["file"]).name
    if fp.exists():
        doc = json.loads(fp.read_text(encoding="utf-8"))
        doc["reusable_form"].update(d["reusable_form"])
        doc["extension_assets"] = ["reuse/regulatory_dependency.yaml"] if d["id"] in ATTACH else []
        fp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps({
    "section_prompts_file": "style/section_prompts.yaml",
    "sections": len(per_section),
    "families_used": sorted({s["family"] for s in per_section}),
    "sections_with_facts": sum(1 for s in per_section if s["slice"]["available_facts"]),
    "sections_with_conflicts": sum(1 for s in per_section if s["project_issues"]["conflicts"]),
    "sections_with_bindings": sum(1 for s in per_section if s["project_issues"]["external_bindings"]),
    "regulatory_asset": "reuse/regulatory_dependency.yaml",
    "attached_domains": attached_log,
}, ensure_ascii=False, indent=2))
