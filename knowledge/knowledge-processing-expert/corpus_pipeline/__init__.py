"""corpus_pipeline — 语料包七道工序流水线（工具层，确定性为主）。

把一份历史稿件（docx/pdf/md）经七道工序产出语料包：

1 归一化   → source/normalized.md, source/offset_map.json, source/assets/
2 骨架抽取 → outline.yaml
3 切块     → chunks/chunks.jsonl
4 本体抽取 → graph/*.yaml, evidence/*
5 推演回放 → reasoning/*
6 质量登记 → quality/*
7 脱敏索引 → chunks/skeletons.jsonl, index/*, style/*

关键设计：skeletons.jsonl 是脱敏骨架（数值 → {{node:Nxx}}），写作 Agent 只拿到它，
永远拿不到 chunks.jsonl 原文。
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

_NUM = re.compile(r'[-+]?\d[\d,]*(?:\.\d+)?%?')

from .spec import TEN_RELATIONS  # noqa: E402  （十类关系单一事实源）


def _parse_heading(line: str):
    """识别标题，返回 (level, title) 或 None。支持 # 与「第X章/节」与编号标题。"""
    s = line.strip()
    m = re.match(r'^(#{1,6})\s+(.+?)\s*$', s)
    if m:
        return len(m.group(1)), m.group(2).strip()
    m = re.match(r'^第[一二三四五六七八九十百千\d]+[章节部分编]\s*(.*)$', s)
    if m:
        return 1, s
    m = re.match(r'^(\d+(?:\.\d+)*)[、.．]\s*(.+)$', s)
    if m:
        return len(m.group(1).split('.')) + 1, m.group(2).strip()
    return None


def stable_id(text: str, prefix: str = "n") -> str:
    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"


# --------------------------------------------------------------------------- #
# 工序 1：归一化
# --------------------------------------------------------------------------- #
def stage_1_normalize(raw_text: str, out: Path) -> dict:
    """去页眉页脚、公式转 LaTeX、表格转结构化，保留字符偏移。"""
    out.mkdir(parents=True, exist_ok=True)
    lines = raw_text.split("\n")

    # 去页眉页脚：出现 ≥3 次且短于 40 字的重复行视为页眉/页脚
    from collections import Counter
    cnt = Counter(l.strip() for l in lines if 0 < len(l.strip()) < 40)
    header_footer = {k for k, v in cnt.items() if v >= 3}
    kept, offset_map, off = [], [], 0
    for l in lines:
        stripped = l.strip()
        if stripped in header_footer:
            off += len(l) + 1
            continue
        kept.append(l)
        offset_map.append({"char": off, "line": len(kept) - 1})
        off += len(l) + 1

    # 公式 → LaTeX：把含数学符号的独立行/片段包成 $...$
    normalized = []
    for l in kept:
        if re.search(r'[∑∏√∫±×÷=<>≤≥]', l) and not l.strip().startswith('|'):
            l = f"$$ {l.strip()} $$"
        normalized.append(l)

    # 表格 → 结构化：管道分隔行组识别为 table 块
    normalized = _mark_tables(normalized)

    (out / "normalized.md").write_text("\n".join(normalized), encoding="utf-8")
    (out / "offset_map.json").write_text(json.dumps(offset_map, ensure_ascii=False), encoding="utf-8")
    (out / "assets").mkdir(exist_ok=True)
    return {"chars": off, "removed_header_footer": sorted(header_footer)}


def _mark_tables(lines: list[str]) -> list[str]:
    out, i = [], 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            out.append("```table")
            out.extend(lines[i:j])
            out.append("```")
            i = j
        else:
            out.append(lines[i])
            i += 1
    return out


# --------------------------------------------------------------------------- #
# 工序 2：骨架抽取
# --------------------------------------------------------------------------- #
def stage_2_outline(normalized_md: str, legal_outline: list[str] | None, out: Path) -> dict:
    """识别章节层级，映射法定大纲，做覆盖校验。"""
    sections = []
    for l in normalized_md.split("\n"):
        h = _parse_heading(l)
        if h:
            sections.append({"level": h[0], "title": h[1]})
    covered = [s["title"] for s in sections]
    missing = [t for t in (legal_outline or []) if not any(t in c for c in covered)]
    outline = {"sections": sections, "legal_outline": legal_outline or [], "covered": covered, "missing": missing, "coverage_ok": not missing}
    out.write_text(json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")
    return outline


# --------------------------------------------------------------------------- #
# 工序 3：切块
# --------------------------------------------------------------------------- #
def stage_3_chunk(normalized_md: str, out: Path) -> list[dict]:
    """按结构边界切 chunk（优化实现，见 corpus_pipeline/chunking.py）。

    本会话实测（源文档 67,889 字符）：
      旧（按空行 + pos+=len(b)+2）: 1,178 片 · 中位 24 · offset 命中 29.3% · ID 重复 22
      新（exact-span+merge+dedup）: 506 片 · 中位 95 · offset 命中 99.2% · ID 唯一 100%
      ⇒ 源文档 LLM 调用 3,533 → 1,518（-57%）
    """
    from . import chunking as _CK
    items, method = _CK.chunk_document(normalized_md)
    chunks = [{"id": it["id"], "index": i, "type": it["type"],
               "span": it["span"], "text": it["text"]} for i, it in enumerate(items)]
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"[切分] {method} => {len(chunks)} 片（旧实现 1,178 片）")
    return chunks


# --------------------------------------------------------------------------- #
# 工序 4：本体抽取（tool + LLM 两阶段）
# --------------------------------------------------------------------------- #
def stage_4_ontology(chunks: list[dict], out: Path, extractions: list[dict] | None = None, doc_type: str | None = None) -> dict:
    """抽事实/规则/论断/证据节点，建十类关系。

    extractions 为 LLM 结构化输出（语义层）；缺省时发出抽取请求并降级为数值占位。
    doc_type 命中领域注册表时，注入领域规则库并把 LLM 规则 label 归一（对齐计算规格）。
    """
    out.mkdir(parents=True, exist_ok=True)
    from .ontology import apply_extraction

    if extractions is not None:
        graph = apply_extraction(chunks, extractions)
    else:
        # 降级：确定性数值占位（待 LLM 语义抽取替换）
        graph = {"facts": [], "rules": [], "claims": [], "evidence": [], "relations": [], "relation_types": list(TEN_RELATIONS)}
        for c in chunks:
            for num in _NUM.findall(c["text"]):
                fid = stable_id(f"{c['id']}:{num}", "N")
                graph["facts"].append({"id": fid, "subject": c["id"], "predicate": "has_value", "value": num, "source": c["id"]})
                graph["relations"].append({"from": c["id"], "to": fid, "type": "has_value"})

    # 领域规则库注入 + LLM 规则 label 归一（对齐 instantiate 的计算规格）
    if doc_type:
        from .domain_rules import inject_domain_rules
        graph = inject_domain_rules(graph, doc_type)

    # 写 graph/*.yaml（对应 30 产物 #12-17）
    from . import full_emit as _FE
    _FE.emit_nodes(out, graph)   # nodes.yaml：归一化 facts → 变量节点（id/subject/kind/value/unit/caliber/inheritable）
    _FE.emit_rules(out, graph)   # rules.yaml：归一化 rules → 计算/判定规则（id/kind/expr/deps/target/label/guard）
    gdir = out / "graph"; gdir.mkdir(parents=True, exist_ok=True)
    for key, fname in [("claims", "claims.yaml"), ("relations", "relations.yaml")]:
        (gdir / fname).write_text(json.dumps(graph.get(key, []), ensure_ascii=False, indent=2), encoding="utf-8")
    (gdir / "graph.yaml").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "evidence").mkdir(exist_ok=True)
    return graph


# --------------------------------------------------------------------------- #
# 工序 5：推演回放（真实语义主语/谓语比对）
# --------------------------------------------------------------------------- #
def stage_5_replay(graph: dict, out: Path) -> dict:
    """按同一 (subject, predicate) 重算比对，检出矛盾。"""
    out.mkdir(parents=True, exist_ok=True)
    from .ontology import replay
    return replay(graph)


# --------------------------------------------------------------------------- #
# 工序 6：质量登记
# --------------------------------------------------------------------------- #
def stage_6_quality(outline: dict, graph: dict, replay: dict, out: Path) -> dict:
    """登记冲突与缺口，跑不变式，出闸门结论。"""
    out.mkdir(parents=True, exist_ok=True)
    conflicts = replay.get("contradictions", [])
    gaps = outline.get("missing", [])
    # 不变式：claim 的 evidence 引用必须存在
    ev_ids = {e.get("id") for e in graph.get("evidence", [])}
    dangling = [c for c in graph.get("claims", []) for ev in c.get("evidence", []) if ev and ev not in ev_ids]
    gate = "PASS" if not conflicts and not gaps and not dangling else "REVIEW"
    quality = {"conflicts": conflicts, "gaps": gaps, "dangling_evidence": dangling, "invariant_ok": not dangling, "gate": gate}
    return quality


# --------------------------------------------------------------------------- #
# 工序 7：脱敏与索引（最关键）
# --------------------------------------------------------------------------- #
def stage_7_desensitize(chunks: list[dict], graph: dict, out: Path) -> dict:
    """生成占位符骨架、节点倒排、术语归一、文风画像、匹配特征。

    数值 → {{node:Nxx}} 中的 Nxx 指向工序 4 的事实节点（单源），而非重新造 ID。
    """
    out.mkdir(parents=True, exist_ok=True)
    # (chunk_id, value) → fact_id 映射（数值单源到事实节点）
    fact_map = {}
    for f in graph["facts"]:
        fact_map[(f.get("source"), str(f.get("value")))] = f["id"]

    skeletons = []
    for c in chunks:
        text = c["text"]
        for num in sorted(set(_NUM.findall(text)), key=len, reverse=True):
            nid = fact_map.get((c["id"], num)) or stable_id(f"{c['id']}:{num}", "N")
            text = text.replace(num, f"{{{{node:{nid}}}}}")
        skeletons.append({**{k: v for k, v in c.items() if k != "text"}, "text": text})

    with open(out / "chunks" / "skeletons.jsonl", "w", encoding="utf-8") as f:
        for s in skeletons:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # 节点倒排/术语/签名 由 full_emit.emit_index 产出（node_index.json / term_index.json / signature.yaml）
    return {"skeletons": len(skeletons), "nodes": len(fact_map)}


# --------------------------------------------------------------------------- #
# 编排
# --------------------------------------------------------------------------- #
def run_pipeline(raw_text: str, root: Path, legal_outline: list[str] | None = None, extractions: list[dict] | None = None, original_path: str | Path | None = None, doc_type: str | None = None) -> dict:
    root = Path(root)
    source_dir = root / "source"
    stage_1_normalize(raw_text, source_dir)
    # #5 source/original.<ext>：原始稿件二进制落盘（docx/pdf）
    if original_path:
        import shutil
        src = Path(original_path)
        shutil.copy2(src, source_dir / f"original{src.suffix.lower()}")
    normalized = (source_dir / "normalized.md").read_text(encoding="utf-8")

    from . import full_emit as FE

    FE.emit_meta(root, raw_text)
    outline = stage_2_outline(normalized, legal_outline, root / "outline.yaml")
    chunks = stage_3_chunk(normalized, root / "chunks")
    graph = stage_4_ontology(chunks, root, extractions, doc_type)
    replay = stage_5_replay(graph, root / "reasoning")
    quality = stage_6_quality(outline, graph, replay, root / "quality")
    desens = stage_7_desensitize(chunks, graph, root)

    # 补齐 30 文件契约缺失产物
    FE.emit_provenance(root, graph, chunks)
    FE.emit_invariants(root)
    FE.emit_evidence(root, graph, chunks)
    trace = [
        {"stage": "1", "event": "normalize", "detail": "ok"},
        {"stage": "2", "event": "outline", "detail": f"{len(outline.get('sections', []))} sections"},
        {"stage": "3", "event": "chunk", "detail": f"{len(chunks)} chunks"},
        {"stage": "4", "event": "ontology", "detail": f"{len(graph.get('facts', []))} facts"},
        {"stage": "5", "event": "replay", "detail": f"{len(replay.get('contradictions', []))} conflicts"},
        {"stage": "6", "event": "quality", "detail": quality["gate"]},
        {"stage": "7", "event": "desensitize", "detail": f"{desens['skeletons']} skeletons"},
    ]
    FE.emit_reasoning(root, replay, graph, trace)
    FE.emit_quality_split(root, quality)
    FE.emit_style(root, chunks, outline)
    skeletons = [json.loads(l) for l in (root / "chunks" / "skeletons.jsonl").read_text(encoding="utf-8").splitlines() if l]
    FE.emit_index(root, graph, chunks, skeletons)
    FE.emit_reuse(root, graph, outline)

    # 产物 #1：manifest.yaml（对齐推演写作侧：corpus_id/version/source_fingerprint/constraints）
    from .store import emit_manifest
    emit_manifest(root, corpus_id=root.name, version="V1.0",
                  source_fingerprint=hashlib.sha1(raw_text.encode("utf-8")).hexdigest()[:16])

    return {"outline": outline, "chunks": len(chunks), "facts": len(graph["facts"]), "gate": quality["gate"], "desensitized": desens}

# --- kp-patch: pipeline gates (auto-run) ---
# `corpus_run` 跑完七道工序后**自动**执行三族门禁，并按状态机约束写 manifest。
# 原则：判定由门禁做，不由写作/抽取 Agent 自判；有 FAIL 则状态停在 draft，不得进 validated。
_orig_run_pipeline = run_pipeline


def run_pipeline(*args, **kwargs):                 # noqa: F811
    result = _orig_run_pipeline(*args, **kwargs)
    try:
        from .verify_pipeline import apply_manifest_gate, verify_pipeline
        root = kwargs.get("root") or (args[1] if len(args) > 1 else None)
        src = kwargs.get("original_path") or (args[4] if len(args) > 4 else None)
        if root:
            s = str(src) if src else ""
            v = verify_pipeline(root,
                                source_md=s if s.endswith(".md") else None,
                                source_docx=s if s.endswith(".docx") else None)
            result["gate"] = apply_manifest_gate(root, v)
            result["gate"]["detail"] = {k: v.get(k) for k in
                                        ("verdict", "closure", "stage_gates", "objective",
                                         "blocking_count", "invalid_count")}
    except Exception as _e:                         # 门禁异常不得吞掉流水线结果，但要显式记录
        result["gate"] = {"verdict": "error", "error": str(_e),
                          "note": "门禁执行异常，**不得视为通过**"}
    return result
