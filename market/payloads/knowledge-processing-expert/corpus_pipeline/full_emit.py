"""补齐 30 文件契约里缺失产物的发射器（meta/provenance/invariants/evidence/reasoning三件套/quality三件套/style两件套/index三件套）。

original.docx(#5)、assets(#8)、embeddings.parquet(#11) 需外部输入（原稿/嵌入模型），此处不生成。
"""
from __future__ import annotations
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

_TERM = re.compile(r'[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{1,}')


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def emit_meta(root: Path, raw_text: str, title: str = "") -> dict:
    """#2 meta.yaml"""
    m = re.search(r'^#\s+(.+)$', raw_text, re.M) or re.search(r'^(.{2,40})$', raw_text, re.M)
    meta = {
        "title": title or (m.group(1).strip() if m else "未命名稿件"),
        "doc_type": "report",
        "data_cutoff": None,
        "lang": "zh",
        "source_sha": _sha(raw_text),
    }
    (root / "meta.yaml").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def emit_provenance(root: Path, graph: dict, chunks: list[dict]) -> list[dict]:
    """#3 provenance.yaml —— 每个对象追溯到来源 chunk"""
    prov = []
    for f in graph.get("facts", []):
        prov.append({"obj_type": "fact", "obj_id": f["id"], "derived_from": [f.get("source")], "stage": "4"})
    for c in graph.get("claims", []):
        prov.append({"obj_type": "claim", "obj_id": c["id"], "derived_from": c.get("evidence", []), "stage": "4"})
    for r in graph.get("rules", []):
        prov.append({"obj_type": "rule", "obj_id": r["id"], "derived_from": r.get("inputs", []), "stage": "4"})
    (root / "provenance.yaml").write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
    return prov


def emit_invariants(root: Path) -> dict:
    """#16 graph/invariants.yaml —— 不变式"""
    inv = {"invariants": [
        {"id": "INV-1", "expr": "同一 (subject, predicate) 的数值必须一致"},
        {"id": "INV-2", "expr": "relation 的 from/to 必须指向存在节点"},
        {"id": "INV-3", "expr": "claim 的 evidence 引用必须存在"},
        {"id": "INV-4", "expr": "数值冲突只呈现「待审」，不自动裁决"},
    ]}
    (root / "graph" / "invariants.yaml").write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
    return inv


def emit_evidence(root: Path, graph: dict, chunks: list[dict]) -> dict:
    """#18 evidence/evidence.yaml + #19 evidence/excerpts/*.md"""
    chunk_map = {c["id"]: c for c in chunks}
    evidence = list(graph.get("evidence", []))
    # 为每个 fact 自动生成证据记录（source chunk + span）
    for f in graph.get("facts", []):
        if not any(e.get("id") == f"ev-{f['id']}" for e in evidence):
            c = chunk_map.get(f.get("source"))
            span = [0, len(c["text"])] if c else [0, 0]
            evidence.append({"id": f"ev-{f['id']}", "claim": "", "doc": f.get("source"), "span": span, "kind": "fact", "fact": f["id"]})

    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "evidence.yaml").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    exdir = root / "evidence" / "excerpts"
    exdir.mkdir(parents=True, exist_ok=True)
    for e in evidence:
        c = chunk_map.get(e.get("doc"))
        if c:
            (exdir / f"{e['id']}.md").write_text(f"# {e['id']}\n\n来源 chunk: {e.get('doc')}\n\n```\n{c['text']}\n```\n", encoding="utf-8")
    return {"evidence": len(evidence), "excerpts": len(list(exdir.glob("*.md")))}


def emit_reasoning(root: Path, replay: dict, graph: dict, trace: list[dict]) -> dict:
    """#20 derivation.yaml + #21 decisions.yaml + #22 trace.jsonl"""
    # 推导链：facts → 对比 → 结论
    derivation = {
        "replayed": replay.get("replayed", 0),
        "steps": [
            {"step": i + 1, "subject": c.get("subject"), "predicate": c.get("predicate"),
             "values": c.get("values"), "verdict": c.get("status")}
            for i, c in enumerate(replay.get("contradictions", []))
        ],
    }
    (root / "reasoning" / "derivation.yaml").write_text(json.dumps(derivation, ensure_ascii=False, indent=2), encoding="utf-8")

    decisions = {"decisions": [
        {"id": f"d{i+1}", "subject": c.get("subject"), "decision": "待审", "rationale": f"数值不一致: {c.get('values')}"}
        for i, c in enumerate(replay.get("contradictions", []))
    ]}
    (root / "reasoning" / "decisions.yaml").write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")

    tp = root / "reasoning" / "trace.jsonl"
    with open(tp, "a", encoding="utf-8") as f:
        for ev in trace:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return {"derivation_steps": len(derivation["steps"]), "decisions": len(decisions["decisions"])}


def emit_quality_split(root: Path, quality: dict) -> dict:
    """#23 conflicts.yaml + #24 gaps.yaml + #25 gate_report.yaml"""
    (root / "quality" / "conflicts.yaml").write_text(json.dumps(quality.get("conflicts", []), ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "quality" / "gaps.yaml").write_text(json.dumps({"gaps": quality.get("gaps", [])}, ensure_ascii=False, indent=2), encoding="utf-8")
    gate = {"gate": quality.get("gate", "REVIEW"), "blockers": quality.get("conflicts", []), "invariant_ok": quality.get("invariant_ok", False)}
    (root / "quality" / "gate_report.yaml").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    return gate


def emit_style(root: Path, chunks: list[dict], outline: dict) -> dict:
    """#26 style_profile.yaml + #27 section_templates/*.yaml"""
    lens = [len(c["text"]) for c in chunks] or [0]
    profile = {
        "avg_chunk_len": sum(lens) // len(lens),
        "chunk_count": len(chunks),
        "lang": "zh",
        "tone": "formal",
    }
    (root / "style").mkdir(parents=True, exist_ok=True)
    (root / "style" / "style_profile.yaml").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    tdir = root / "style" / "section_templates"
    tdir.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(outline.get("sections", [])):
        (tdir / f"{i+1:02d}-{s['title']}.yaml").write_text(json.dumps({"level": s["level"], "title": s["title"], "template": "## " + s["title"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"templates": len(list(tdir.glob("*.yaml")))}


def emit_index(root: Path, graph: dict, chunks: list[dict], skeletons: list[dict]) -> dict:
    """#28 node_index.json + #29 term_index.json + #30 signature.yaml"""
    # 节点倒排：node → 出现的 chunk
    (root / "index").mkdir(parents=True, exist_ok=True)
    node_index = []
    for s, c in zip(skeletons, chunks):
        for nid in re.findall(r'\{\{node:(N-[0-9a-f]+)\}\}', s["text"]):
            node_index.append({"node": nid, "chunk": c["id"], "role": "value"})
    (root / "index" / "node_index.json").write_text(json.dumps(node_index, ensure_ascii=False, indent=2), encoding="utf-8")

    # 术语归一：surface → canonical（低频化/计数）
    all_text = " ".join(c["text"] for c in chunks)
    terms = Counter(_TERM.findall(all_text))
    term_index = [{"surface": t, "canonical": t.lower(), "freq": n} for t, n in terms.most_common(50)]
    (root / "index" / "term_index.json").write_text(json.dumps(term_index, ensure_ascii=False, indent=2), encoding="utf-8")

    # 签名：manifest + graph 的指纹
    sig = {"files": len(list(root.rglob("*"))), "graph_facts": len(graph.get("facts", [])), "sha": _sha(json.dumps(graph, ensure_ascii=False, sort_keys=True))}
    (root / "index" / "signature.yaml").write_text(json.dumps(sig, ensure_ascii=False, indent=2), encoding="utf-8")
    return sig


# --------------------------------------------------------------------------- #
# reemit：把每个发射器单独暴露为可调用工具（按需重发单产物）
# --------------------------------------------------------------------------- #
def load_corpus(root) -> dict:
    """从语料包读回全部状态，供 reemit_* 使用。"""
    root = Path(root)

    def jl(rel):
        p = root / rel
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l] if p.exists() else []

    def jf(rel):
        p = root / rel
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    chunks = jl("chunks/chunks.jsonl")
    graph = jf("graph/graph.yaml")
    outline = jf("outline.yaml")
    from .ontology import replay as _replay
    rp = _replay(graph)
    conflicts = rp["contradictions"]
    gaps = outline.get("missing", [])
    ev_ids = {e.get("id") for e in graph.get("evidence", [])}
    dangling = [c for c in graph.get("claims", []) for ev in c.get("evidence", []) if ev and ev not in ev_ids]
    gate = "PASS" if not conflicts and not gaps and not dangling else "REVIEW"
    quality = {"conflicts": conflicts, "gaps": gaps, "dangling_evidence": dangling, "invariant_ok": not dangling, "gate": gate}
    raw = (root / "source" / "normalized.md").read_text(encoding="utf-8") if (root / "source" / "normalized.md").exists() else ""
    return {"chunks": chunks, "graph": graph, "outline": outline, "replay": rp, "quality": quality, "raw": raw}


def reemit_meta(root):
    s = load_corpus(root)
    return emit_meta(Path(root), s["raw"])


def reemit_provenance(root):
    s = load_corpus(root)
    return emit_provenance(Path(root), s["graph"], s["chunks"])


def reemit_invariants(root):
    return emit_invariants(Path(root))


def reemit_evidence(root):
    s = load_corpus(root)
    return emit_evidence(Path(root), s["graph"], s["chunks"])


def reemit_reasoning(root):
    s = load_corpus(root)
    return emit_reasoning(Path(root), s["replay"], s["graph"], [{"stage": "5", "event": "reemit", "detail": "replayed"}])


def reemit_quality(root):
    s = load_corpus(root)
    return emit_quality_split(Path(root), s["quality"])


def reemit_style(root):
    s = load_corpus(root)
    return emit_style(Path(root), s["chunks"], s["outline"])


def reemit_index(root):
    s = load_corpus(root)
    p = Path(root)
    skeletons = [json.loads(l) for l in (p / "chunks" / "skeletons.jsonl").read_text(encoding="utf-8").splitlines() if l]
    return emit_index(p, s["graph"], s["chunks"], skeletons)
