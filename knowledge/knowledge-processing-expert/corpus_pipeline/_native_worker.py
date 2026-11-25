# -*- coding: utf-8 -*-
"""_native_worker —— 在 semantica venv 里执行各类操作，stdin/stdout 传 JSON。

## 为什么需要

semantica 装在 /Users/apple/.venvs/semantica（Py3.11），本项目在 Py3.9。
跨解释器只能 subprocess。

## 支持的 op

    conflicts     5 类冲突检测（value/type/relationship/temporal/logical）
    conflicts_resolve  冲突解决（most_recent/reliable/majority/manual）
    evals         10 个评估器（exact_match/levenshtein/rouge/llm_as_judge/...）
    ner           实体抽取（pattern/ml/llm）
    relations     关系抽取（pattern/ml/llm）
    triplets      三元组抽取（pattern）
    coref         指代消解
    dedup         实体去重（DuplicateDetector + EntityMerger）
    shacl         生成 SHACL 形状 + 校验
    ontology      从图谱生成本体
    provenance    W3C PROV-O 记录
    seed          可信源 bootstrap（seed_first 冲突优先）
    export        导出（json/parquet/csv/rdf-turtle）
    parse         文档解析（DocumentParser）
    reasoning     推理（Reasoner 前向链 / DatalogReasoner）
    capability    探测环境能力

## 协议

stdin  {"op": "...", ...参数}
stdout {"ok": true, "result": ...} | {"ok": false, "error": "..."}
"""
import json
import sys
import traceback


def _ser(x, depth=0):
    """把 semantica 对象序列化成 JSON 友好结构。"""
    if depth > 6:
        return str(x)[:200]
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, dict):
        return {str(k): _ser(v, depth + 1) for k, v in list(x.items())[:200]}
    if isinstance(x, (list, tuple, set)):
        return [_ser(v, depth + 1) for v in list(x)[:500]]
    if hasattr(x, "model_dump"):
        try:
            return _ser(x.model_dump(), depth + 1)
        except Exception:
            pass
    if hasattr(x, "__dict__"):
        d = {k: v for k, v in vars(x).items() if not k.startswith("_")}
        if d:
            return _ser(d, depth + 1)
    return str(x)[:300]


def _entities_from_req(req):
    """把输入实体统一成 semantica 需要的形态。"""
    ents = req.get("entities") or []
    out = []
    for e in ents:
        if isinstance(e, str):
            out.append({"id": e, "name": e})
        elif isinstance(e, dict):
            out.append(e)
    return out


# ---------------------------------------------------------------- 各 op
def op_capability(req):
    import importlib
    caps = {}
    for p in ("docling", "spacy", "sentence_transformers", "networkx",
              "rdflib", "pyshacl", "pandas", "pyarrow"):
        try:
            importlib.import_module(p)
            caps[p] = True
        except Exception:
            caps[p] = False
    import semantica
    return {"version": getattr(semantica, "__version__", "?"), "deps": caps}


def op_conflicts(req):
    from semantica.conflicts import ConflictDetector, ConflictResolver
    ents = _entities_from_req(req)
    det = ConflictDetector()
    cs = det.detect_conflicts(ents)
    result = {"count": len(cs) if hasattr(cs, "__len__") else 0,
              "conflicts": _ser(cs)}
    if req.get("resolve"):
        try:
            resolver = ConflictResolver()
            resolved = resolver.resolve_conflicts(
                cs, strategy=req.get("strategy", "most_recent"))
            result["resolved"] = _ser(resolved)
        except Exception as e:
            result["resolve_error"] = str(e)[:200]
    return result


def op_evals(req):
    from semantica.evals import evaluate, list_evaluators
    evs = req.get("evaluators") or ["exact_match"]
    cases = [(str(a), str(b)) for a, b in (req.get("cases") or [])]
    if not cases:
        return {"evaluators": list_evaluators(), "total": 0, "passed": 0}
    summary = evaluate(cases, evaluators=evs)
    return {"evaluators": list_evaluators(),
            "total": getattr(summary, "total", 0),
            "passed": getattr(summary, "passed", 0),
            "pass_rate": getattr(summary, "pass_rate", 0),
            "detail": _ser(summary)}


def op_ner(req):
    from semantica.semantic_extract import NERExtractor
    method = req.get("method", "pattern")
    text = req.get("text") or ""
    ner = NERExtractor(method=method)
    ents = ner.extract(text)
    return {"method": method, "count": len(ents) if hasattr(ents, "__len__") else 0,
            "entities": _ser(ents)}


def op_relations(req):
    from semantica.semantic_extract import NERExtractor, RelationExtractor
    method = req.get("method", "pattern")
    text = req.get("text") or ""
    ents = NERExtractor(method=method).extract(text) if req.get("entities") is None else req["entities"]
    rel = RelationExtractor(method=method)
    rels = rel.extract(text, entities=ents)
    return {"method": method, "count": len(rels) if hasattr(rels, "__len__") else 0,
            "relationships": _ser(rels)}


def op_triplets(req):
    from semantica.semantic_extract import TripletExtractor
    text = req.get("text") or ""
    trip = TripletExtractor(method=req.get("method", "pattern"))
    ts = trip.extract(text)
    return {"count": len(ts) if hasattr(ts, "__len__") else 0, "triplets": _ser(ts)}


def op_coref(req):
    from semantica.semantic_extract import CoreferenceResolver
    text = req.get("text") or ""
    cr = CoreferenceResolver()
    # 不同版本签名可能不同，逐个尝试
    for call in (lambda: cr.resolve(text),
                 lambda: cr.resolve_coreferences(text),
                 lambda: cr.extract(text)):
        try:
            r = call()
            return {"count": len(r) if hasattr(r, "__len__") else 0, "result": _ser(r)}
        except Exception:
            continue
    raise RuntimeError("CoreferenceResolver 无可用方法")


def op_dedup(req):
    from semantica.deduplication import DuplicateDetector, EntityMerger
    ents = _entities_from_req(req)
    det = DuplicateDetector(similarity_threshold=float(req.get("threshold", 0.85)))
    cands = det.detect_duplicates(ents)
    out = {"candidates": len(cands) if hasattr(cands, "__len__") else 0,
           "detail": _ser(cands)}
    if req.get("merge"):
        merger = EntityMerger()
        ops = merger.merge_duplicates(
            ents, strategy=req.get("strategy", "keep_most_complete"))
        out["merge"] = _ser(ops)
    return out


def op_shacl(req):
    from semantica.ontology import SHACLGenerator, OntologyValidator
    graph = req.get("graph") or {}
    out = {}
    try:
        shapes = SHACLGenerator().generate(graph)
        out["shapes"] = _ser(shapes)
    except Exception as e:
        out["shapes_error"] = str(e)[:200]
    try:
        v = OntologyValidator()
        out["validation"] = _ser(v.validate(graph))
    except Exception as e:
        out["validation_error"] = str(e)[:200]
    return out


def op_ontology(req):
    from semantica.ontology import OntologyGenerator
    graph = req.get("graph") or {}
    onto = OntologyGenerator().generate_from_graph(graph)
    return {"ontology": _ser(onto)}


def op_provenance(req):
    from semantica.provenance import ProvenanceManager
    mgr = ProvenanceManager()
    eid = req.get("entity_id") or "entity_1"
    mgr.track_entity(eid, source=req.get("source") or "unknown",
                     metadata=req.get("metadata") or {})
    return {"entity": eid, "lineage": _ser(mgr.get_lineage(eid))}


def op_seed(req):
    from semantica.seed import SeedDataManager
    seed = SeedDataManager()
    csv_path = req.get("csv")
    etype = req.get("entity_type", "Item")
    if not csv_path:
        raise RuntimeError("seed 需要 csv 路径")
    sd = seed.load_from_csv(csv_path, entity_type=etype)
    out = {"seed_entities": _ser(sd)}
    if req.get("extracted"):
        combined = seed.integrate_with_extracted(
            {"entities": sd, "relationships": []},
            {"entities": req["extracted"], "relationships": []},
            merge_strategy=req.get("merge_strategy", "seed_first"))
        out["combined"] = _ser(combined)
    return out


def op_export(req):
    from semantica.export import JSONExporter, CSVExporter, ParquetExporter
    graph = req.get("graph") or {}
    fmt = req.get("format", "json")
    path = req.get("path") or "/tmp/export.out"
    if fmt == "json":
        JSONExporter().export(graph, file_path=path)
    elif fmt == "csv":
        CSVExporter().export(graph, file_path=path)
    elif fmt == "parquet":
        ParquetExporter().export(graph, file_path=path)
    elif fmt in ("rdf", "turtle"):
        from semantica.export import RDFExporter
        RDFExporter().export(graph, file_path=path, format="turtle")
    else:
        raise RuntimeError("不支持的 format: %s" % fmt)
    import os
    return {"format": fmt, "path": path,
            "bytes": os.path.getsize(path) if os.path.exists(path) else 0}


def op_parse(req):
    from semantica.parse import DocumentParser
    p = req.get("path")
    if not p:
        raise RuntimeError("parse 需要 path")
    parsed = DocumentParser().parse(p)
    d = parsed if isinstance(parsed, dict) else {"raw": _ser(parsed)}
    return {"keys": list(d.keys())[:20],
            "full_text_len": len(str(d.get("full_text") or "")),
            "full_text_head": str(d.get("full_text") or "")[:500],
            "metadata": _ser(d.get("metadata"))}


def op_reasoning(req):
    from semantica.reasoning import Reasoner
    eng = Reasoner()
    for f in req.get("facts") or []:
        eng.add_fact(str(f))
    for r in req.get("rules") or []:
        eng.add_rule(str(r))
    res = eng.forward_chain()
    return {"count": len(res) if hasattr(res, "__len__") else 0,
            "inferences": _ser(res)}


OPS = {
    "capability": op_capability, "conflicts": op_conflicts, "evals": op_evals,
    "ner": op_ner, "relations": op_relations, "triplets": op_triplets,
    "coref": op_coref, "dedup": op_dedup, "shacl": op_shacl,
    "ontology": op_ontology, "provenance": op_provenance, "seed": op_seed,
    "export": op_export, "parse": op_parse, "reasoning": op_reasoning,
}


def main():
    try:
        req = json.load(sys.stdin)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "bad stdin: %s" % e}, ensure_ascii=False))
        return
    op = req.get("op") or "capability"
    fn = OPS.get(op)
    if not fn:
        print(json.dumps({"ok": False, "error": "unknown op: %s" % op,
                          "available": sorted(OPS)}, ensure_ascii=False))
        return
    try:
        r = fn(req)
        print(json.dumps({"ok": True, "op": op, "result": r}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "op": op, "error": str(e),
                          "trace": traceback.format_exc()[-600:]},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
