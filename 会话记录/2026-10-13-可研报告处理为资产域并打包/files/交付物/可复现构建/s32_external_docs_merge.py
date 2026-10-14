# -*- coding: utf-8 -*-
"""s32 —— 把 web 检索到的文档一并纳入抽取目标（多文档抽取）。

此前状态：
  · 20 份外部检索文档已被切块（external/chunks.jsonl 950 条）、并抽出 22 条条款、
    17 条约束、15 条绑定 —— 但它们只是 **external/ 层**，
    没有作为**一等文档**进入语料包文档集，其条款也未作为**节点**进入主图谱。

本步做两件事：
  ① 注册一等文档集：`documents.yaml`（报告 + 20 份外部文档，含 url/sha/层级/状态）；
  ② 把外部条款/约束**合并进主图谱**（作为 judgment 节点 + 证据边），
     使图谱成为真正的多文档图谱，而不是「项目图谱 + 旁挂依据层」。

这样做的直接后果：K3/C1 引用闭环、K4 数值闭环、S8 依据闭环都会把外部文档
当作**抽取目标**一并核对，而不是只核对报告。
"""
import json
import re
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
ROOT = WS / "SHUFE-BDC-2019-001"
EXT = ROOT / "external"


def J(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:                                     # noqa: BLE001
        return d


def W(p, o):
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


docs = J(EXT / "documents.yaml", {}) or {}
docs_list = docs.get("documents") if isinstance(docs, dict) else docs
docs_list = docs_list or []
mandates = (J(EXT / "mandates.yaml", {}) or {}).get("mandates", [])
constraints = (J(EXT / "constraints.yaml", {}) or {}).get("constraints", [])
man = J(ROOT / "manifest.yaml", {}) or {}
chunks = [json.loads(l) for l in (EXT / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] \
    if (EXT / "chunks.jsonl").exists() else []

# ── ① 一等文档集 ──────────────────────────────────────────────
documents = [{
    "doc_id": "DOC-REPORT-01", "title": man.get("title", "可行性研究报告"),
    "layer": "report", "doc_type": "可行性研究报告",
    "sha256": man.get("source_original_sha256", ""),
    "source": "source/original.docx", "status": "ok",
    "extraction_role": "抽取目标（主文档）",
}]
for i, d in enumerate(docs_list, 1):
    documents.append({
        "doc_id": d.get("id") or f"DOC-EXT-{i:02d}",
        "title": d.get("title") or d.get("doc") or f"外部依据 {i}",
        "layer": "external", "doc_type": d.get("type", "标准/政策"),
        "url": d.get("url", ""), "source": d.get("file") or d.get("path", ""),
        "status": d.get("status", "ok"),
        "chunks": sum(1 for c in chunks if c.get("doc") == (d.get("id") or f"DOC-EXT-{i:02d}")),
        "extraction_role": "抽取目标（依据文档）",
    })
W(ROOT / "documents.yaml", {
    "count": len(documents), "layers": {"report": 1, "external": len(documents) - 1},
    "note": "外部检索文档与报告**同为抽取目标**；其条款与约束已合并进主图谱",
    "documents": documents})

# ── ② 外部条款/约束 → 主图谱节点 ────────────────────────────
nodes = J(ROOT / "graph" / "nodes.yaml", []) or []
existing = {n.get("id") for n in nodes}
ext_nodes = []
for i, m in enumerate(mandates, 1):
    nid = f"NX-条款-{i:03d}"
    if nid in existing:
        continue
    ext_nodes.append({
        "id": nid, "subject": (m.get("standard") or m.get("doc") or "标准"),
        "predicate": (m.get("clause") or "条款"), "value": (m.get("text") or "")[:180],
        "unit": "", "kind": "judgment", "caliber": "",
        "status": "defined", "instruction": "", "inheritable": "yes",
        "section": "外部依据", "section_index": 0,
        "source": (m.get("chunks") or [""])[0] if m.get("chunks") else "",
        "doc_layer": "external", "ext_source": "s32_merge",
        "effect_level": m.get("effect_level", ""), "code": m.get("code", ""),
    })
for i, c in enumerate(constraints, 1):
    nid = f"NX-约束-{i:03d}"
    if nid in existing:
        continue
    ext_nodes.append({
        "id": nid, "subject": (c.get("subject") or c.get("target") or "约束对象"),
        "predicate": (c.get("predicate") or c.get("constraint") or "取值约束"),
        "value": str(c.get("value") or c.get("threshold") or c.get("rule") or "")[:180],
        "unit": c.get("unit", ""), "kind": "judgment", "caliber": "",
        "status": "defined", "instruction": "", "inheritable": "yes",
        "section": "外部依据", "section_index": 0,
        "source": c.get("chunk", ""), "doc_layer": "external", "ext_source": "s32_merge",
        "mandatory": bool(c.get("mandatory", False)),
    })
if ext_nodes:
    W(ROOT / "graph" / "nodes.yaml", nodes + ext_nodes)

# ── ③ 证据条目（指向外部 chunk，可追溯）──────────────────────
ev = J(ROOT / "evidence" / "evidence.yaml", []) or []
have_ev = {e.get("id") for e in ev}
ext_ev = []
for n in ext_nodes:
    eid = f"EVX-外部-{n['id'].split('-')[-1]}"
    if eid in have_ev:
        continue
    ext_ev.append({"id": eid, "kind": "standard", "doc": n["subject"],
                   "quote": n["value"][:120], "locator": {"section": "外部依据", "clause": n["predicate"]},
                   "chunk": n.get("source", ""), "doc_layer": "external",
                   "verification": {"timeliness": "待核", "note": "来自外部检索文档，时效状态见 effective_dates.yaml"},
                   "auto_registered": True})
if ext_ev:
    W(ROOT / "evidence" / "evidence.yaml", ev + ext_ev)

# ── ④ 合并报告 ───────────────────────────────────────────────
W(ROOT / "quality" / "external_merge_report.yaml", {
    "documents_registered": len(documents),
    "external_docs": len(documents) - 1,
    "external_chunks": len(chunks),
    "clause_nodes_added": sum(1 for n in ext_nodes if n["id"].startswith("NX-条款")),
    "constraint_nodes_added": sum(1 for n in ext_nodes if n["id"].startswith("NX-约束")),
    "evidence_added": len(ext_ev),
    "note": "外部检索文档已作为一等文档与抽取目标纳入；其条款/约束进入主图谱，"
            "闭环与依据判据会一并核对",
})
print(json.dumps({"documents": len(documents), "clause_nodes": sum(1 for n in ext_nodes if n['id'].startswith('NX-条款')),
                  "constraint_nodes": sum(1 for n in ext_nodes if n['id'].startswith('NX-约束')),
                  "evidence": len(ext_ev), "nodes_total": len(nodes) + len(ext_nodes)},
                 ensure_ascii=False, indent=2))
