"""kp-mcp — 知识处理工具层的最小 stdio MCP 服务（纯标准库，无 mcp SDK 依赖）。

暴露工具：
  corpus_run               七道工序全链路
  segment_sentences        确定性分句
  segment_chunks           确定性分块
  validate_graph           图谱校验（悬空引用/重复id）
  detect_numeric_conflicts 数字冲突（待审）
  detect_time_conflicts    时间冲突（待审）
  build_provenance         溯源链
  validate_schema          schema 校验
  library_list_packages    列出历史项目语料资产库
  library_search           跨语料包关键词检索
  library_get_asset        取历史语料包可复用资产（借形不借值）
  library_find_analog      为新项目找最相似的历史语料包
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

# 使项目根可被 import（kp_toolkit / corpus_pipeline 为兄弟包）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kp_toolkit import (
    segment_sentences, segment_chunks, validate_graph,
    detect_numeric_conflicts, detect_time_conflicts, check_number_consistency,
    build_provenance, validate_schema, compile_graph,
)
from corpus_pipeline import run_pipeline
from corpus_pipeline import store as corpus_store
from corpus_pipeline import library as corpus_library
from corpus_pipeline import schema_diff as _schema_diff
from corpus_pipeline import semantic_model as _semantic_model
from corpus_pipeline import ontology_schema as _ontology_schema
from corpus_pipeline.spec import MANIFEST, AGENT_TOOLS

SERVER_INFO = {"name": "kp-mcp", "version": "0.1.0"}
PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {"name": "corpus_run", "description": "运行语料包七道工序全链路，返回工序汇总",
     "inputSchema": {"type": "object",
                     "properties": {"raw_text": {"type": "string"}, "out_dir": {"type": "string"},
                                    "legal_outline": {"type": "array", "items": {"type": "string"}},
                                    "doc_type": {"type": "string"}},
                     "required": ["raw_text", "out_dir"]}},
    {"name": "segment_sentences", "description": "确定性分句，返回稳定ID句子列表",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "doc_id": {"type": "string"}}, "required": ["text"]}},
    {"name": "segment_chunks", "description": "确定性语义分块",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "doc_id": {"type": "string"}}, "required": ["text"]}},
    {"name": "validate_graph", "description": "校验图谱（悬空引用/重复id/统计）",
     "inputSchema": {"type": "object", "properties": {"graph": {"type": "object"}}, "required": ["graph"]}},
    {"name": "detect_numeric_conflicts", "description": "检测同一主语谓词下数值不一致，输出待审清单",
     "inputSchema": {"type": "object", "properties": {"facts": {"type": "array"}}, "required": ["facts"]}},
    {"name": "detect_time_conflicts", "description": "检测时间矛盾，输出待审清单",
     "inputSchema": {"type": "object", "properties": {"facts": {"type": "array"}}, "required": ["facts"]}},
    {"name": "check_number_consistency", "description": "写作查数：核实正文数字与事实源一致，检测前后不一致与口径存疑",
     "inputSchema": {"type": "object",
                     "properties": {"draft_md": {"type": "string"}, "facts": {"type": "array"}},
                     "required": ["draft_md", "facts"]}},
    {"name": "schema_diff", "description": "Schema 结构差异分析：新增/缺失/类型变化/改名 + 语义分类",
     "inputSchema": {"type": "object",
                     "properties": {"old_schema": {"type": "object"}, "new_schema": {"type": "object"}},
                     "required": ["old_schema", "new_schema"]}},
    {"name": "resolve_concept", "description": "语义对齐：字段名 → 标准概念（canonical_name/aliases/kind/unit/formula）",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "ossie_import", "description": "从 Apache Ossie 语义模型 YAML 导入概念字典（fields→attribute、metrics→metric、synonyms→aliases）",
     "inputSchema": {"type": "object", "properties": {"yaml_text": {"type": "string"}}, "required": ["yaml_text"]}},
    {"name": "ossie_export", "description": "把概念字典导出为 Apache Ossie 语义模型 YAML",
     "inputSchema": {"type": "object", "properties": {"concepts": {"type": "object"}}, "required": ["concepts"]}},
    {"name": "semantic_classify", "description": "语义分类：判断字段属于新变量/别名/元数据（默认确定性，可插拔接 Jev MCP）",
     "inputSchema": {"type": "object",
                     "properties": {"name": {"type": "string"}, "field_def": {"type": "object"}},
                     "required": ["name"]}},
    {"name": "ontology_export", "description": "导出本体 Schema（对齐 Semantica 的 OWL/SHACL/SKOS：类/属性/约束/词表）",
     "inputSchema": {"type": "object", "properties": {"concepts": {"type": "object"}}, "required": []}},
    {"name": "ontology_import", "description": "从本体 Schema 导入概念字典（SKOS 词表 → 概念）",
     "inputSchema": {"type": "object", "properties": {"schema": {"type": "object"}}, "required": ["schema"]}},
    {"name": "bootstrap_ontology", "description": "从新旧 Schema 差异生成 16 域可执行装配变更集（本体/论证链/任务DAG/规则/Skill/表单/提示词/质量闸门/复用策略/实体关系）",
     "inputSchema": {"type": "object",
                     "properties": {"old_schema": {"type": "object"}, "new_schema": {"type": "object"}},
                     "required": ["old_schema", "new_schema"]}},
    {"name": "build_provenance", "description": "从节点反向追溯证据，返回溯源链",
     "inputSchema": {"type": "object", "properties": {"node_id": {"type": "string"}, "graph": {"type": "object"}}, "required": ["node_id", "graph"]}},
    {"name": "validate_schema", "description": "校验一类节点的必填字段",
     "inputSchema": {"type": "object", "properties": {"nodes": {"type": "array"}, "kind": {"type": "string"}}, "required": ["nodes", "kind"]}},
    {"name": "manifest", "description": "返回语料包 30 个产物的文件清单契约",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "corpus_get_chunk", "description": "取脱敏 chunk（写作 Agent 唯一拿到的原文形态）",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "chunk_id": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["corpus_dir"]}},
    {"name": "corpus_get_skeleton", "description": "取节模板",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "section": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "corpus_where_used", "description": "查节点被哪些 chunk 使用",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "node_id": {"type": "string"}}, "required": ["corpus_dir", "node_id"]}},
    {"name": "graph_get_node", "description": "取图节点",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "node_id": {"type": "string"}}, "required": ["corpus_dir", "node_id"]}},
    {"name": "graph_query", "description": "查询图节点",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "filter_text": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "graph_explain", "description": "解释规则与推导链",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "rule_id": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "graph_impact", "description": "查节点的关系影响",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "node_id": {"type": "string"}}, "required": ["corpus_dir", "node_id"]}},
    {"name": "graph_why", "description": "解释决策依据",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "decision_id": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "gate_check", "description": "运行不变式并返回闸门结论",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "evidence_get", "description": "取论断证据（可带摘录）",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "claim_id": {"type": "string"}, "with_excerpt": {"type": "boolean"}}, "required": ["corpus_dir"]}},
    {"name": "embed", "description": "把文本向量化（fastembed / BAAI-bge-small-zh-v1.5），返回向量",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "texts": {"type": "array", "items": {"type": "string"}}, "model": {"type": "string"}}, "required": []}},
    {"name": "embed_chunks", "description": "把语料包的所有 chunk 向量化并写 embeddings.json",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "model": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "reemit_meta", "description": "重发 meta.yaml（#2）", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "reemit_provenance", "description": "重发 provenance.yaml（#3）", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "reemit_invariants", "description": "重发 graph/invariants.yaml（#16）", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "reemit_evidence", "description": "重发 evidence.yaml + excerpts（#18/#19）", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "reemit_reasoning", "description": "重发 derivation/decisions/trace（#20/#21/#22）", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "reemit_quality", "description": "重发 conflicts/gaps/gate_report（#23/#24/#25）", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "reemit_style", "description": "重发 style_profile + section_templates（#26/#27）", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "reemit_index", "description": "重发 node_index/term_index/signature（#28/#29/#30）", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "corpus_search", "description": "向量检索脱敏 chunk（只返回占位符骨架，永不返回字面数值）",
     "inputSchema": {"type": "object",
                     "properties": {"corpus_dir": {"type": "string"}, "query": {"type": "string"},
                                    "k": {"type": "integer"}, "filters": {"type": "object"}},
                     "required": ["corpus_dir", "query"]}},
    {"name": "project_where_written", "description": "查节点在本项目已写草稿中的位置（project/drafts/node_mentions.jsonl）",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "node_id": {"type": "string"}}, "required": ["corpus_dir", "node_id"]}},
    {"name": "wp_get_facts", "description": "工作包 facts 分页（facts>30 时编排器按页拉取；未落盘工作包时按 section 过滤图谱事实分页）",
     "inputSchema": {"type": "object",
                     "properties": {"corpus_dir": {"type": "string"}, "work_package_id": {"type": "string"},
                                    "page": {"type": "integer"}, "page_size": {"type": "integer"}},
                     "required": ["corpus_dir"]}},
    {"name": "instantiate_project", "description": "新项目图库实例化：输入新事实 + 借用语料规则/推导链/风格，输出重绑定图库（借形不借值、缺值守卫、回放检矛盾）",
     "inputSchema": {"type": "object",
                     "properties": {"corpus_dir": {"type": "string"}, "project_dir": {"type": "string"},
                                    "provided_facts": {"type": "array", "items": {"type": "object"}},
                                    "meta": {"type": "object"}},
                     "required": ["corpus_dir", "project_dir", "provided_facts"]}},
    {"name": "build_work_package", "description": "编排器组装章节工作包（outline/facts≤30/claims/conflicts/undefined/返回契约，落盘 project/work_packages/<section>.json）",
     "inputSchema": {"type": "object",
                     "properties": {"project_dir": {"type": "string"}, "section_id": {"type": "string"},
                                    "corpus_dir": {"type": "string"}, "must_cover": {"type": "array", "items": {"type": "string"}},
                                    "word_budget": {"type": "array", "items": {"type": "integer"}}, "page_size": {"type": "integer"}},
                     "required": ["project_dir", "section_id"]}},
    {"name": "gate_check_draft", "description": "编排器草稿闸门（由编排器调用，非 Agent 自评）：查字面数值、undefined 引用、must_cover 缺项，返回 verdict",
     "inputSchema": {"type": "object",
                     "properties": {"project_dir": {"type": "string"}, "section_id": {"type": "string"}, "draft_md": {"type": "string"}},
                     "required": ["project_dir", "section_id", "draft_md"]}},
    # ④ 历史项目资产库（写新项目时复用知识处理专家沉淀的语料包，借形不借值）
    {"name": "library_list_packages", "description": "列出历史项目语料资产库中的所有语料包（名称/标题/文档类型/数据截止/规模），写新项目前先调用以盘点可复用资产",
     "inputSchema": {"type": "object", "properties": {"library_root": {"type": "string"}}, "required": []}},
    {"name": "library_search", "description": "跨历史语料包按关键词检索（标题/术语/章节匹配），返回命中片段，用于写新项目时找相似项目",
     "inputSchema": {"type": "object", "properties": {"library_root": {"type": "string"}, "query": {"type": "string"}}, "required": []}},
    {"name": "library_get_asset", "description": "取某个历史语料包的指定可复用资产（outline/templates/style/terms/claims/nodes/rules/skeleton/evidence/meta），仅借形、不借值",
     "inputSchema": {"type": "object",
                     "properties": {"library_root": {"type": "string"}, "package": {"type": "string"}, "asset": {"type": "string"}},
                     "required": ["package", "asset"]}},
    {"name": "library_find_analog", "description": "为新项目找最相似的历史语料包（文档类型优先匹配 + 关键词命中排序），返回建议复用的资产清单",
     "inputSchema": {"type": "object",
                     "properties": {"library_root": {"type": "string"}, "doc_type": {"type": "string"}, "query": {"type": "string"}},
                     "required": []}},
]


def _dispatch(name: str, args: dict):
    if name == "corpus_run":
        return run_pipeline(args["raw_text"], Path(args["out_dir"]), args.get("legal_outline"), doc_type=args.get("doc_type"))
    if name == "segment_sentences":
        return segment_sentences(args["text"], args.get("doc_id", "doc"))
    if name == "segment_chunks":
        return segment_chunks(args["text"], args.get("doc_id", "doc"))
    if name == "validate_graph":
        return validate_graph(args["graph"])
    if name == "detect_numeric_conflicts":
        return detect_numeric_conflicts(args["facts"])
    if name == "detect_time_conflicts":
        return detect_time_conflicts(args["facts"])
    if name == "check_number_consistency":
        return check_number_consistency(args["draft_md"], args["facts"])
    if name == "schema_diff":
        diffs = _schema_diff.diff_schemas(args["old_schema"], args["new_schema"])
        return {"diffs": diffs, "summary": _schema_diff.summarize(diffs),
                "impact_analysis": _schema_diff.analyze_schema_impact(diffs)}
    if name == "resolve_concept":
        concept, via = _semantic_model.resolve_concept(args["name"])
        return {"name": args["name"], "concept": concept, "via": via}
    if name == "ossie_import":
        return {"concepts": _semantic_model.import_ossie_yaml(args["yaml_text"])}
    if name == "ossie_export":
        return {"yaml": _semantic_model.export_ossie_yaml(args["concepts"])}
    if name == "semantic_classify":
        concepts = _semantic_model.build_concepts()
        concept, via = _semantic_model.resolve_concept(args["name"], concepts)
        if concept:
            return {"name": args["name"], "kind": "alias_of_existing", "concept_id": concept["id"],
                    "via": via, "confidence": 1.0, "classifier": "deterministic"}
        return {"name": args["name"],
                **_schema_diff.DeterministicClassifier().classify(args["name"], args.get("field_def", {}), concepts)}
    if name == "ontology_export":
        return _ontology_schema.export_ontology_schema(args.get("concepts"))
    if name == "ontology_import":
        return {"concepts": _ontology_schema.import_ontology_schema(args["schema"])}
    if name == "bootstrap_ontology":
        diffs = _schema_diff.diff_schemas(args["old_schema"], args["new_schema"])
        return _ontology_schema.assemble_domain_changes(diffs)
    if name == "build_provenance":
        return build_provenance(args["node_id"], args["graph"])
    if name == "validate_schema":
        return validate_schema(args["nodes"], args["kind"])
    if name == "manifest":
        return {"count": len(MANIFEST), "files": MANIFEST, "agent_tools": AGENT_TOOLS}
    # ② Agent 访问工具
    cd = args.get("corpus_dir")
    if name == "corpus_get_chunk":
        return corpus_store.corpus_get_chunk(cd, args.get("chunk_id"), args.get("limit", 20))
    if name == "corpus_get_skeleton":
        return corpus_store.corpus_get_skeleton(cd, args.get("section"))
    if name == "corpus_where_used":
        return corpus_store.corpus_where_used(cd, args["node_id"])
    if name == "graph_get_node":
        return corpus_store.graph_get_node(cd, args["node_id"])
    if name == "graph_query":
        return corpus_store.graph_query(cd, args.get("filter_text", ""))
    if name == "graph_explain":
        return corpus_store.graph_explain(cd, args.get("rule_id"))
    if name == "graph_impact":
        return corpus_store.graph_impact(cd, args["node_id"])
    if name == "graph_why":
        return corpus_store.graph_why(cd, args.get("decision_id"))
    if name == "gate_check":
        return corpus_store.gate_check(cd)
    if name == "evidence_get":
        return corpus_store.evidence_get(cd, args.get("claim_id"), args.get("with_excerpt", False))
    if name == "corpus_search":
        return corpus_store.corpus_search(cd, args.get("query", ""), args.get("k", 5), args.get("filters"))
    if name == "project_where_written":
        return corpus_store.project_where_written(cd, args["node_id"])
    if name == "wp_get_facts":
        return corpus_store.wp_get_facts(cd, args.get("work_package_id"), args.get("page", 0), args.get("page_size", 30))
    if name == "instantiate_project":
        from corpus_pipeline import instantiate as _ins
        return _ins.instantiate_project(args["corpus_dir"], args["project_dir"], args.get("provided_facts", []), args.get("meta"))
    if name == "build_work_package":
        from corpus_pipeline import orchestrator as _orc
        return _orc.build_work_package(args["project_dir"], args["section_id"], corpus_dir=args.get("corpus_dir"),
                                       must_cover=args.get("must_cover"), word_budget=args.get("word_budget", (1200, 1800)),
                                       page_size=args.get("page_size", 30))
    if name == "gate_check_draft":
        from corpus_pipeline import orchestrator as _orc
        return _orc.gate_check_draft(args["project_dir"], args["section_id"], args.get("draft_md", ""))
    # ④ 历史项目资产库
    if name == "library_list_packages":
        return corpus_library.list_packages(args.get("library_root") or corpus_library.DEFAULT_LIBRARY)
    if name == "library_search":
        return corpus_library.search_packages(args.get("library_root") or corpus_library.DEFAULT_LIBRARY, args.get("query", ""))
    if name == "library_get_asset":
        return corpus_library.get_asset(args.get("library_root") or corpus_library.DEFAULT_LIBRARY, args["package"], args["asset"])
    if name == "library_find_analog":
        return corpus_library.find_analog(args.get("library_root") or corpus_library.DEFAULT_LIBRARY, args.get("doc_type", ""), args.get("query", ""))
    if name == "embed":
        from corpus_pipeline.embed import embed_texts, DEFAULT_MODEL
        texts = args.get("texts") or ([args["text"]] if args.get("text") else [])
        if not texts:
            return {"error": "需要 text 或 texts"}
        return {"model": args.get("model", DEFAULT_MODEL), "dim": None, "vectors": embed_texts(texts, args.get("model", DEFAULT_MODEL))}
    if name == "embed_chunks":
        from corpus_pipeline.embed import build_embeddings, DEFAULT_MODEL
        import json as _json
        chunks = [_json.loads(l) for l in (Path(args["corpus_dir"]) / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l]
        return build_embeddings(chunks, Path(args["corpus_dir"]), args.get("model", DEFAULT_MODEL))
    if name.startswith("reemit_"):
        import importlib
        m = importlib.import_module("corpus_pipeline.full_emit")
        fn = getattr(m, name)
        return fn(args["corpus_dir"])
    raise ValueError(f"unknown tool {name}")


def _read_message():
    """NDJSON 帧：SDK v2 的 stdio 用换行分隔 JSON（无 Content-Length 头）。"""
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    return json.loads(line.decode("utf-8"))


def _send(obj):
    """NDJSON 帧：一行一个 JSON。"""
    body = json.dumps(obj, ensure_ascii=False) + "\n"
    sys.stdout.write(body)
    sys.stdout.flush()


def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _text_result(data):
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}], "isError": False}


def handle(msg):
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "initialize":
        # 回显客户端请求的协议版本（MCP 标准行为），避免版本协商失败导致断连
        requested = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION
        return _result(req_id, {"protocolVersion": requested,
                                "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS})
    if method == "tools/call":
        try:
            name = msg["params"]["name"]
            args = msg["params"].get("arguments", {}) or {}
            return _result(req_id, _text_result(_dispatch(name, args)))
        except Exception as e:  # noqa: BLE001
            return _result(req_id, _text_result({"error": str(e), "isError": True}))
    return _error(req_id, -32601, f"method not found: {method}")


def main():
    while True:
        msg = _read_message()
        if msg is None:
            break
        resp = handle(msg)
        if resp is not None:
            _send(resp)


if __name__ == "__main__":
    main()
