# -*- coding: utf-8 -*-
"""evo_semantica_lab —— Semantica P0–P2 实测适配器（只读实验层）。

为什么需要它
------------
`evo_native.py` 的 15 个 op 是最小统一门面；实测发现几个能力被门面截断：

1. `parse` 只回传 full_text_len / head / metadata，丢掉 `tables` / `sections`；
2. `evals` 不透传 config，且 `evaluate()` 的元组语义是 `(expected, actual)`；
3. `conflicts` 只调 `detect_conflicts()`，而该方法默认 **不包含**
   relationship 冲突；logical 冲突也不是 A>B/B>A，而是类型互斥；
4. `shacl` 把原始 GRAPH 直接喂给 `SHACLGenerator`，缺少 ontology dict 必失败；
5. `export` 对 dict 形态的 GRAPH 会生成 `_entities.csv` 等后缀文件，
   请求路径本身为 0 字节；RDF 只认顶层 entities/relationships；
6. `seed` 不返回 integrate 后的可比对摘要。

本适配器不修改 semantica，也不修改 `evo_native.py`。它只做三件事：
把输入整理成 semantica 真正需要的形态、调用真实 API、把结果与校验证据
序列化成 JSON。所有 op 仍然在 `/Users/apple/.venvs/semantica/bin/python`
下执行。

协议
----
stdin  : {"op": "...", ...参数}
stdout : {"ok": true, "op": "...", "result": {...}}
         {"ok": false, "op": "...", "error": "...", "trace": "..."}
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- serialization
def _ser(x, depth=0):
    """把 semantica 对象序列化成 JSON 友好结构。"""
    if depth > 8:
        return str(x)[:300]
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, dict):
        return {str(k): _ser(v, depth + 1) for k, v in list(x.items())[:500]}
    if isinstance(x, (list, tuple, set)):
        return [_ser(v, depth + 1) for v in list(x)[:2000]]
    if isinstance(x, Path):
        return str(x)
    if hasattr(x, "value") and hasattr(x, "name") and type(x).__module__ == "enum":
        return x.value
    if hasattr(x, "model_dump"):
        try:
            return _ser(x.model_dump(), depth + 1)
        except Exception:
            pass
    if hasattr(x, "__dict__"):
        d = {k: v for k, v in vars(x).items() if not k.startswith("_")}
        if d:
            return _ser(d, depth + 1)
    return str(x)[:500]


def _entity(e):
    return {
        "text": getattr(e, "text", None),
        "label": getattr(e, "label", None) or getattr(e, "entity_type", None),
        "start_char": getattr(e, "start_char", None),
        "end_char": getattr(e, "end_char", None),
        "confidence": getattr(e, "confidence", None),
        "metadata": _ser(getattr(e, "metadata", {})),
    }


def _relation(r):
    return {
        "subject": _entity(getattr(r, "subject", None)),
        "predicate": getattr(r, "predicate", None),
        "object": _entity(getattr(r, "object", None)),
        "confidence": getattr(r, "confidence", None),
        "context": getattr(r, "context", None),
        "metadata": _ser(getattr(r, "metadata", {})),
    }


def _conflict(c):
    return {
        "conflict_id": getattr(c, "conflict_id", None),
        "conflict_type": _ser(getattr(c, "conflict_type", None)),
        "entity_id": getattr(c, "entity_id", None),
        "property_name": getattr(c, "property_name", None),
        "relationship_id": getattr(c, "relationship_id", None),
        "conflicting_values": _ser(getattr(c, "conflicting_values", [])),
        "sources": _ser(getattr(c, "sources", [])),
        "confidence": getattr(c, "confidence", None),
        "severity": getattr(c, "severity", None),
        "recommended_action": getattr(c, "recommended_action", None),
        "metadata": _ser(getattr(c, "metadata", {})),
    }


# ---------------------------------------------------------------- capability
def op_capability(req):
    import importlib
    import semantica
    caps = {}
    for p in ("docling", "spacy", "sentence_transformers", "networkx",
              "rdflib", "pyshacl", "pandas", "pyarrow", "docx"):
        try:
            importlib.import_module(p)
            caps[p] = True
        except Exception:
            caps[p] = False
    import spacy
    models = []
    try:
        import importlib.metadata as md
        models = sorted(
            d.metadata["Name"] for d in md.distributions()
            if d.metadata.get("Name") and "core_web" in d.metadata["Name"]
        )
    except Exception:
        pass
    return {
        "version": getattr(semantica, "__version__", "?"),
        "python": sys.version.split()[0],
        "deps": caps,
        "spacy_version": getattr(spacy, "__version__", "?"),
        "spacy_models": models,
    }


# ---------------------------------------------------------------- parse
def op_parse(req):
    from semantica.parse import DocumentParser
    path = req.get("path")
    if not path:
        raise RuntimeError("parse 需要 path")
    parsed = DocumentParser().parse(path, extract_tables=True)
    if not isinstance(parsed, dict):
        return {"raw": _ser(parsed)}

    full = str(parsed.get("full_text") or "")
    tables = parsed.get("tables") or []
    want_index = req.get("table_index")
    want_kw = req.get("table_keyword")
    max_rows = int(req.get("max_rows", 8))

    tsum = []
    for i, t in enumerate(tables):
        rows = t.get("rows") or []
        flat = "\n".join(" | ".join(str(c) for c in row) for row in rows)
        tsum.append({
            "index": i,
            "row_count": t.get("row_count", len(rows)),
            "col_count": t.get("col_count", len(rows[0]) if rows else 0),
            "header": rows[0] if rows else [],
            "contains_keyword": bool(want_kw and want_kw in flat),
            "first_rows": rows[:max_rows],
        })

    full_tables = []
    for i, t in enumerate(tables):
        rows = t.get("rows") or []
        flat = "\n".join(" | ".join(str(c) for c in row) for row in rows)
        if i == want_index or (want_kw and want_kw in flat):
            full_tables.append({
                "index": i,
                "row_count": t.get("row_count", len(rows)),
                "col_count": t.get("col_count", len(rows[0]) if rows else 0),
                "rows": rows,
            })

    sections = parsed.get("sections") or []
    return {
        "keys": list(parsed.keys()),
        "metadata": _ser(parsed.get("metadata")),
        "full_text_len": len(full),
        "full_text_len_nospace": len(re.sub(r"\s", "", full)),
        "full_text_head": full[:500],
        "full_text_tail": full[-300:],
        "paragraph_count": len(parsed.get("paragraphs") or []),
        "total_paragraphs": parsed.get("total_paragraphs"),
        "total_tables": parsed.get("total_tables"),
        "table_summaries": tsum,
        "full_tables": full_tables,
        "section_count": len(sections),
        "section_samples": _ser(sections[:12]),
        "comments_count": len(parsed.get("comments") or []),
    }


# ---------------------------------------------------------------- conflicts
def op_conflicts(req):
    from semantica.conflicts import ConflictDetector, ConflictResolver
    ents = req.get("entities") or []
    rels = req.get("relationships") or []
    methods = req.get("methods") or ["value", "type", "relationship",
                                     "temporal", "logical"]
    det = ConflictDetector()
    out = {}
    all_cs = []

    if "all" in methods:
        cs = det.detect_conflicts(ents)
        out["all"] = [_conflict(c) for c in cs]
        all_cs.extend(cs)

    if "value" in methods:
        # entity-wide 会检查 name/value 等所有共同字段；只保留 value_conflict
        cs = det.detect_entity_conflicts(ents)
        cs = [c for c in cs
              if _ser(getattr(c, "conflict_type", "")) == "value_conflict"]
        out["value"] = [_conflict(c) for c in cs]
        all_cs.extend(cs)

    if "type" in methods:
        cs = det.detect_type_conflicts(ents)
        out["type"] = [_conflict(c) for c in cs]
        all_cs.extend(cs)

    if "relationship" in methods:
        cs = det.detect_relationship_conflicts(rels)
        out["relationship"] = [_conflict(c) for c in cs]
        all_cs.extend(cs)

    if "temporal" in methods:
        cs = det.detect_temporal_conflicts(ents)
        out["temporal"] = [_conflict(c) for c in cs]
        all_cs.extend(cs)

    if "logical" in methods:
        cs = det.detect_logical_conflicts(ents)
        out["logical"] = [_conflict(c) for c in cs]
        all_cs.extend(cs)

    # 去重（同一 conflict_id 可能被 all 与单类各收一次）
    uniq = {}
    for c in all_cs:
        uniq[getattr(c, "conflict_id", id(c))] = c

    result = {
        "counts": {k: len(v) for k, v in out.items()},
        "conflicts": out,
        "union_count": len(uniq),
    }
    if req.get("resolve"):
        try:
            resolver = ConflictResolver()
            resolved = resolver.resolve_conflicts(
                list(uniq.values()), strategy=req.get("strategy", "most_recent"))
            result["resolved"] = _ser(resolved)
        except Exception as e:
            result["resolve_error"] = "%s: %s" % (type(e).__name__, e)
    return result


# ---------------------------------------------------------------- evals
def op_evals(req):
    from semantica.evals import evaluate, list_evaluators
    evs = req.get("evaluators") or ["exact_match"]
    cases = []
    for i, c in enumerate(req.get("cases") or []):
        case = dict(c)
        case.setdefault("id", "case-%d" % i)
        cases.append(case)
    summary = evaluate(cases, evs, config=req.get("config") or {})
    out_cases = []
    for c in summary.cases:
        metrics = {}
        for name, m in (c.metrics or {}).items():
            metrics[name] = {"score": m.score, "passed": m.passed,
                             "meta": _ser(m.meta)}
        out_cases.append({"id": c.case_id, "status": c.status,
                          "metrics": metrics,
                          "details": _ser(c.details)})
    return {
        "evaluators_available": list_evaluators(),
        "total": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "errors": summary.errors,
        "pass_rate": summary.pass_rate,
        "cases": out_cases,
    }


# ---------------------------------------------------------------- extract
def op_extract(req):
    from semantica.semantic_extract import (
        NERExtractor, RelationExtractor, TripletExtractor, CoreferenceResolver,
    )
    text = req.get("text") or ""
    model = req.get("model")
    ner_method = req.get("ner_method", "ml")
    rel_method = req.get("rel_method", "pattern")
    result = {}

    if req.get("do_ner", True):
        kw = {"model": model} if model else {}
        ents = NERExtractor(method=ner_method, **kw).extract(text)
        result["ner"] = {"method": ner_method, "model": model,
                         "count": len(ents), "entities": [_entity(e) for e in ents]}
        entities = ents
    else:
        entities = []

    if req.get("entities") is not None:
        from semantica.semantic_extract.types import Entity
        entities = [Entity(text=e.get("text"), label=e.get("label"),
                           start_char=e.get("start_char", 0),
                           end_char=e.get("end_char", 0),
                           confidence=e.get("confidence", 1.0),
                           metadata=e.get("metadata") or {})
                    for e in req["entities"]]

    if req.get("do_relations", True):
        kw = {"model": model} if model else {}
        try:
            rels = RelationExtractor(method=rel_method, **kw).extract(
                text, entities=entities)
            result["relations"] = {
                "method": rel_method, "model": model, "count": len(rels),
                "relationships": [_relation(r) for r in rels],
            }
        except Exception as e:
            result["relations"] = {
                "method": rel_method, "model": model,
                "error": "%s: %s" % (type(e).__name__, e),
            }

    if req.get("do_triplets"):
        try:
            ts = TripletExtractor(method=req.get("triplet_method", "pattern")).extract(text)
            result["triplets"] = {"count": len(ts), "triplets": _ser(ts)}
        except Exception as e:
            result["triplets"] = {"error": "%s: %s" % (type(e).__name__, e)}

    if req.get("do_coref"):
        kw = {"model": model} if model else {}
        try:
            cr = CoreferenceResolver(ner_method=ner_method, **kw)
            chains = cr.resolve(text)
            result["coref"] = {
                "method": ner_method, "model": model, "chain_count": len(chains),
                "chains": [{
                    "representative": getattr(c.representative, "text", None),
                    "entity_type": getattr(c, "entity_type", None),
                    "mentions": [{
                        "text": getattr(m, "text", None),
                        "type": getattr(m, "mention_type", None),
                        "start": getattr(m, "start_char", None),
                        "end": getattr(m, "end_char", None),
                        "entity_id": getattr(m, "entity_id", None),
                        "metadata": _ser(getattr(m, "metadata", {})),
                    } for m in (c.mentions or [])],
                } for c in chains],
            }
        except Exception as e:
            result["coref"] = {"error": "%s: %s" % (type(e).__name__, e)}
    return result


# ---------------------------------------------------------------- provenance
def op_provenance(req):
    from semantica.provenance import ProvenanceManager
    storage_path = req.get("storage_path")
    if not storage_path:
        storage_path = str(Path(tempfile.mkdtemp(prefix="semprov-")) / "prov.db")
    if req.get("reset") and Path(storage_path).exists():
        Path(storage_path).unlink()
    mgr = ProvenanceManager(storage_path=storage_path)

    records = req.get("records") or []
    tracked = []
    for rec in records:
        eid = rec.get("entity_id")
        if not eid:
            continue
        entry = mgr.track_entity(
            eid,
            source=rec.get("source") or "unknown",
            metadata=rec.get("metadata") or {},
            parent_entity_id=rec.get("parent_entity_id"),
            source_location=rec.get("source_location"),
            source_quote=rec.get("source_quote"),
            start_index=rec.get("start_index"),
            end_index=rec.get("end_index"),
            confidence=rec.get("confidence", 1.0),
        )
        tracked.append({"entity_id": eid, "stored": entry is not None})

    lineages = {}
    for rec in records:
        eid = rec.get("entity_id")
        if eid:
            lineages[eid] = _ser(mgr.get_lineage(eid))

    prov_ttl = mgr.export_prov(
        format=req.get("format", "turtle"),
        base_uri=req.get("base_uri") or "https://workdsh.example/prov#",
    )
    out_path = req.get("path")
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(prov_ttl, encoding="utf-8")

    verify = {}
    try:
        import rdflib
        g = rdflib.Graph()
        g.parse(data=prov_ttl, format=req.get("format", "turtle"))
        PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")
        def cnt(pred):
            return sum(1 for _ in g.subjects(pred, None))
        preds = {}
        for s, p, o in g:
            key = str(p).split("#")[-1]
            preds[key] = preds.get(key, 0) + 1
        verify = {
            "triples": len(g),
            "predicates": preds,
            "entities": sum(1 for _ in g.subjects(rdflib.RDF.type, PROV.Entity)),
            "agents": sum(1 for _ in g.subjects(rdflib.RDF.type, PROV.Agent)),
            "activities": sum(1 for _ in g.subjects(rdflib.RDF.type, PROV.Activity)),
            "wasDerivedFrom": cnt(PROV.wasDerivedFrom),
            "wasAttributedTo": cnt(PROV.wasAttributedTo),
            "wasGeneratedBy": cnt(PROV.wasGeneratedBy),
            "generatedAtTime": cnt(PROV.generatedAtTime),
        }
    except Exception as e:
        verify = {"error": "%s: %s" % (type(e).__name__, e)}

    return {
        "storage_path": storage_path,
        "tracked": tracked,
        "lineages": lineages,
        "prov_ttl_path": out_path,
        "prov_ttl_len": len(prov_ttl),
        "prov_ttl_head": prov_ttl[:800],
        "rdf_verify": verify,
    }


# ---------------------------------------------------------------- dedup
def op_dedup(req):
    from semantica.deduplication import (
        DuplicateDetector, EntityMerger, SimilarityCalculator,
    )
    ents = req.get("entities") or []
    threshold = float(req.get("threshold", 0.85))
    det = DuplicateDetector(similarity_threshold=threshold)
    cands = det.detect_duplicates(ents)
    cand_out = []
    for c in cands:
        cand_out.append({
            "entity1": _ser(getattr(c, "entity1", None)),
            "entity2": _ser(getattr(c, "entity2", None)),
            "similarity_score": getattr(c, "similarity_score", None),
            "confidence": getattr(c, "confidence", None),
            "reasons": _ser(getattr(c, "reasons", [])),
            "metadata": _ser(getattr(c, "metadata", {})),
        })

    pair_scores = []
    if req.get("all_pairs"):
        sc = SimilarityCalculator()
        for i in range(len(ents)):
            for j in range(i + 1, len(ents)):
                r = sc.calculate_similarity(ents[i], ents[j], track=False)
                pair_scores.append({
                    "a": ents[i].get("id"), "b": ents[j].get("id"),
                    "a_name": ents[i].get("name"), "b_name": ents[j].get("name"),
                    "score": getattr(r, "score", None),
                    "method": getattr(r, "method", None),
                    "components": _ser(getattr(r, "components", {})),
                    "metadata": _ser(getattr(r, "metadata", {})),
                })

    out = {"threshold": threshold, "candidate_count": len(cand_out),
           "candidates": cand_out, "pair_scores": pair_scores}
    if req.get("merge"):
        merger = EntityMerger()
        ops = merger.merge_duplicates(
            ents, strategy=req.get("strategy", "keep_most_complete"))
        out["merge_ops"] = _ser(ops)
    return out


# ---------------------------------------------------------------- shacl
def _fact_iri(fid):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(fid))
    return "fact_" + safe


def op_shacl(req):
    import rdflib
    from rdflib import Graph, Literal, Namespace, RDF, XSD
    from rdflib.namespace import SH
    from semantica.ontology import SHACLGenerator

    facts = req.get("facts") or []
    base = req.get("base_uri") or "https://workdsh.example/ns#"
    EX = Namespace(base)

    ontology = {
        "namespace": {"base_uri": base},
        "classes": [
            {"name": "Fact", "label": "事实节点",
             "description": "知识图谱中的一条事实"},
        ],
        "properties": [
            {"name": "subject", "label": "主体", "type": "datatype",
             "range": "string", "domain": "Fact", "required": True},
            {"name": "predicate", "label": "谓词", "type": "datatype",
             "range": "string", "domain": "Fact", "required": True},
            {"name": "value", "label": "取值", "type": "datatype",
             "range": "decimal", "domain": "Fact", "required": True},
            {"name": "unit", "label": "单位", "type": "datatype",
             "range": "string", "domain": "Fact"},
            {"name": "section", "label": "章节", "type": "datatype",
             "range": "string", "domain": "Fact"},
            {"name": "status", "label": "状态", "type": "datatype",
             "range": "string", "domain": "Fact",
             "one_of": ["provided", "computed", "undefined"]},
        ],
    }

    gen = SHACLGenerator(
        base_uri=base,
        target_namespace=base,
        quality_tier="standard",
    )
    shapes = gen.generate(ontology)
    shapes_ttl = gen.serialize(shapes, format="turtle")

    # Semantica 的 SHACLGenerator 不生成 sh:minInclusive/maxInclusive；
    # 追加一条显式值域形状，用于验证「值域越界」。这是本实验的补充，
    # 报告中会明确标注。
    range_shape = """
ex:FactValueRangeShape a sh:NodeShape ;
    sh:targetClass ex:Fact ;
    sh:property [
        sh:path ex:value ;
        sh:minInclusive 0 ;
        sh:maxInclusive 100000000 ;
    ] .
"""
    # shapes_ttl 已声明 ex/sh/xsd 前缀，这里只追加形状本体，避免重复前缀。
    combined_shapes = shapes_ttl.rstrip() + "\n\n" + range_shape.lstrip()

    def build_data(records, defects=False):
        g = Graph()
        g.bind("ex", EX)
        for i, f in enumerate(records):
            fid = f.get("id") or "row_%d" % i
            node = EX[_fact_iri(fid)]
            g.add((node, RDF.type, EX.Fact))
            subject = f.get("subject")
            predicate = f.get("predicate")
            value = f.get("value")
            if defects and i == 0:
                subject = None                     # 必填缺失
            if defects and i == 1:
                predicate = 123                    # 类型不符（谓词应为 string）
            if defects and i == 2:
                value = -1                         # 值域越界
            if subject is not None:
                g.add((node, EX.subject, Literal(str(subject))))
            if predicate is not None:
                if isinstance(predicate, (int, float)):
                    g.add((node, EX.predicate, Literal(predicate)))
                else:
                    g.add((node, EX.predicate, Literal(str(predicate))))
            if value is not None:
                try:
                    # 用字符串词法 + xsd:decimal，避免 rdflib 把 float
                    # 自动标成 xsd:double 引发误报。
                    g.add((node, EX.value, Literal(str(value), datatype=XSD.decimal)))
                except (TypeError, ValueError):
                    g.add((node, EX.value, Literal(str(value), datatype=XSD.string)))
            if f.get("unit"):
                g.add((node, EX.unit, Literal(str(f["unit"]))))
            if f.get("section"):
                g.add((node, EX.section, Literal(str(f["section"]))))
            if f.get("status"):
                g.add((node, EX.status, Literal(str(f["status"]))))
        return g

    def validate(data_g):
        import pyshacl
        shapes_g = rdflib.Graph()
        shapes_g.parse(data=combined_shapes, format="turtle")
        conforms, results_g, results_text = pyshacl.validate(
            data_g, shacl_graph=shapes_g, inference="none", abort_on_first=False)
        rows = []
        for r in results_g.subjects(RDF.type, SH.ValidationResult):
            focus = results_g.value(r, SH.focusNode)
            path = results_g.value(r, SH.resultPath)
            comp = results_g.value(r, SH.sourceConstraintComponent)
            sev = results_g.value(r, SH.resultSeverity)
            msg = results_g.value(r, SH.resultMessage)
            val = results_g.value(r, SH.value)
            rows.append({
                "focus": str(focus) if focus else None,
                "path": str(path) if path else None,
                "constraint": str(comp).split("#")[-1] if comp else None,
                "severity": str(sev).split("#")[-1] if sev else None,
                "message": str(msg) if msg else None,
                "value": str(val) if val else None,
            })
        by_c = {}
        for row in rows:
            by_c[row["constraint"]] = by_c.get(row["constraint"], 0) + 1
        return {"conforms": conforms, "violation_count": len(rows),
                "by_constraint": by_c, "violations": rows}

    data_g = build_data(facts, defects=False)
    data_ttl = data_g.serialize(format="turtle")
    normal = validate(data_g)
    defect_g = build_data(facts, defects=True)
    defect = validate(defect_g)

    out_path = req.get("shapes_path")
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(combined_shapes, encoding="utf-8")
    data_path = req.get("data_path")
    if data_path:
        Path(data_path).parent.mkdir(parents=True, exist_ok=True)
        Path(data_path).write_text(data_ttl, encoding="utf-8")

    return {
        "ontology_classes": [c["name"] for c in ontology["classes"]],
        "ontology_properties": [p["name"] for p in ontology["properties"]],
        "shapes_ttl_path": out_path,
        "shapes_ttl_len": len(combined_shapes),
        "shapes_ttl_head": combined_shapes[:1200],
        "generated_only_ttl": shapes_ttl,
        "data_triples": len(data_g),
        "data_ttl_path": data_path,
        "normal": normal,
        "defect_injected": defect,
        "note": ("Semantica SHACLGenerator 支持 required→sh:minCount、"
                 "datatype、one_of；不支持数值区间，值域形状为本实验追加。"),
    }


# ---------------------------------------------------------------- seed
def op_seed(req):
    from semantica.seed import SeedDataManager
    csv_path = req.get("csv")
    if not csv_path:
        raise RuntimeError("seed 需要 csv 路径")
    seed = SeedDataManager()
    records = seed.load_from_csv(
        csv_path, entity_type=req.get("entity_type", "StandardLimit"))
    extracted = req.get("extracted") or []
    combined = seed.integrate_with_extracted(
        {"entities": records, "relationships": []},
        {"entities": extracted, "relationships": []},
        merge_strategy=req.get("merge_strategy", "seed_first"),
    )
    seed_ids = {str(r.get("id")) for r in records if r.get("id")}
    ext_ids = {str(e.get("id")) for e in extracted if e.get("id")}
    return {
        "csv": csv_path,
        "seed_count": len(records),
        "seed_sample": _ser(records[:5]),
        "seed_id_count": len(seed_ids),
        "extracted_count": len(extracted),
        "extracted_ids": sorted(ext_ids),
        "combined_count": len(combined.get("entities") or []),
        "combined_metadata": _ser(combined.get("metadata")),
        "overridden_by_seed": sorted(seed_ids & ext_ids),
        "seed_only": sorted(seed_ids - ext_ids),
        "extracted_only": sorted(ext_ids - seed_ids),
        "combined_sample": _ser((combined.get("entities") or [])[:5]),
    }


# ---------------------------------------------------------------- export
def _normalize_graph_for_export(graph):
    items = graph.get("items") if isinstance(graph, dict) else {}
    items = items or {}
    facts = items.get("facts") or []
    rels = items.get("relations") or []
    entities = []
    for f in facts:
        entities.append({
            "id": f.get("id"),
            "name": f.get("subject"),
            "type": "Fact",
            "metadata": {
                "predicate": f.get("predicate"),
                "value": f.get("value"),
                "unit": f.get("unit"),
                "section": f.get("section"),
                "status": f.get("status"),
                "source": f.get("source"),
            },
        })
    relationships = []
    for r in rels:
        relationships.append({
            "id": r.get("id"),
            "source_id": r.get("from"),
            "target_id": r.get("to"),
            "type": r.get("type"),
        })
    return {"entities": entities, "relationships": relationships,
            "metadata": {"source": "GRAPH-新项目-华东理工AI研究院.json"}}


def op_export(req):
    from semantica.export import (
        JSONExporter, CSVExporter, ParquetExporter, RDFExporter,
    )
    graph = req.get("graph") or {}
    normalized = _normalize_graph_for_export(graph)
    outdir = Path(req.get("outdir") or ".")
    outdir.mkdir(parents=True, exist_ok=True)
    results = {}

    # JSON：完整 GRAPH（保留 items 结构）
    json_path = outdir / req.get("json_name", "export-graph.json")
    JSONExporter().export(graph, file_path=str(json_path))
    results["json"] = {
        "path": str(json_path), "bytes": json_path.stat().st_size,
        "verify": _verify_json(json_path),
    }

    # CSV：事实表（一行一条 fact）
    csv_path = outdir / req.get("csv_name", "export-graph.csv")
    CSVExporter().export(normalized["entities"], file_path=str(csv_path))
    results["csv"] = {
        "path": str(csv_path), "bytes": csv_path.stat().st_size,
        "verify": _verify_csv(csv_path),
    }

    # Parquet：事实表
    parquet_path = outdir / req.get("parquet_name", "export-graph.parquet")
    ParquetExporter().export(normalized["entities"], file_path=str(parquet_path))
    results["parquet"] = {
        "path": str(parquet_path), "bytes": parquet_path.stat().st_size,
        "verify": _verify_parquet(parquet_path),
    }

    # RDF：实体 + 关系。自定义 metadata key 必须显式给 metadata_terms，
    # 否则 Semantica 会丢弃 predicate/value/unit/section/status。
    rdf_path = outdir / req.get("rdf_name", "export-graph.ttl")
    base_ns = req.get("base_uri") or "https://workdsh.example/ns#"
    metadata_terms = {k: base_ns + k for k in
                      ("predicate", "value", "unit", "section", "status", "source")}
    RDFExporter().export(normalized, file_path=str(rdf_path), format="turtle",
                         metadata_terms=metadata_terms)
    results["rdf"] = {
        "path": str(rdf_path), "bytes": rdf_path.stat().st_size,
        "verify": _verify_rdf(rdf_path),
        "metadata_terms": metadata_terms,
    }

    # 附加：扁平事实 CSV（Semantica 原生 CSV 把自定义字段塞进 metadata JSON）
    flat_path = outdir / req.get("flat_csv_name", "export-graph-facts.csv")
    with open(flat_path, "w", encoding="utf-8", newline="") as f:
        fields = ["id", "subject", "predicate", "value", "unit", "section", "status", "source"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for fact in (graph.get("items") or {}).get("facts") or []:
            w.writerow({k: fact.get(k) for k in fields})
    results["flat_csv"] = {
        "path": str(flat_path), "bytes": flat_path.stat().st_size,
        "verify": _verify_csv(flat_path),
    }

    # 门面直调对照：dict 形态会生成 _entities.* 后缀文件
    facade_probe = {}
    probe_base = outdir / "export-facade-probe"
    try:
        CSVExporter().export(normalized, file_path=str(probe_base.with_suffix(".csv")))
        ParquetExporter().export(normalized, file_path=str(probe_base.with_suffix(".parquet")))
        facade_probe = {
            "csv_requested_bytes": _size(probe_base.with_suffix(".csv")),
            "parquet_requested_bytes": _size(probe_base.with_suffix(".parquet")),
            "csv_suffixed_exists": (outdir / "export-facade-probe_entities.csv").exists(),
            "parquet_suffixed_exists": (outdir / "export-facade-probe_entities.parquet").exists(),
        }
    except Exception as e:
        facade_probe = {"error": "%s: %s" % (type(e).__name__, e)}
    results["facade_dict_export_probe"] = facade_probe

    return {"outdir": str(outdir),
            "entity_count": len(normalized["entities"]),
            "relationship_count": len(normalized["relationships"]),
            "results": results}


def _size(p):
    p = Path(p)
    return p.stat().st_size if p.exists() else 0


def _verify_json(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return {"top_keys": list(d.keys())[:10],
            "facts": len((d.get("items") or {}).get("facts") or [])}


def _verify_csv(path):
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {"rows": len(rows),
            "columns": list(rows[0].keys()) if rows else [],
            "first": rows[0] if rows else None}


def _verify_parquet(path):
    import pandas as pd
    df = pd.read_parquet(path)
    return {"rows": len(df), "columns": list(df.columns),
            "dtypes": {c: str(t) for c, t in df.dtypes.items()}}


def _verify_rdf(path):
    import rdflib
    g = rdflib.Graph()
    g.parse(str(path), format="turtle")
    types = {}
    for s, p, o in g.triples((None, rdflib.RDF.type, None)):
        key = str(o).split("#")[-1]
        types[key] = types.get(key, 0) + 1
    preds = {}
    for s, p, o in g:
        key = str(p).split("#")[-1]
        preds[key] = preds.get(key, 0) + 1
    return {"triples": len(g), "type_counts": types,
            "predicate_counts": preds}


OPS = {
    "capability": op_capability,
    "parse": op_parse,
    "conflicts": op_conflicts,
    "evals": op_evals,
    "extract": op_extract,
    "provenance": op_provenance,
    "dedup": op_dedup,
    "shacl": op_shacl,
    "seed": op_seed,
    "export": op_export,
}


def main():
    try:
        req = json.load(sys.stdin)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "bad stdin: %s" % e},
                         ensure_ascii=False))
        return
    op = req.get("op")
    fn = OPS.get(op)
    if not fn:
        print(json.dumps({"ok": False, "error": "unknown op: %s" % op,
                          "available": sorted(OPS)}, ensure_ascii=False))
        return
    try:
        result = fn(req)
        print(json.dumps({"ok": True, "op": op, "result": result},
                         ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "op": op, "error": str(e),
                          "trace": traceback.format_exc()[-1200:]},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
