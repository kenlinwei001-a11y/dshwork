# -*- coding: utf-8 -*-
"""kp-mcp 工具分组：65 个工具按「权限域/数据域」拆成 5 个 MCP。

避免 65 个工具塞一个 MCP 导致的上下文膨胀 / 调度不准 / 权限无法隔离 / 故障无法隔离。
5 组职责边界：
  processing —— 知识处理七道工序 + 基础工具（建图/抽取/冲突/溯源/脱敏）
  assembly   —— 项目装配 + 验证 + 写作（Schema Diff/复用决策/建图/组包/闸门/查数/关口）
  library    —— 历史资产库 + 发布（检索/复用/状态机）
  semantic   —— 语义对齐 + 本体（Ossie/Jev/Semantica 对接）
  reserved   —— 预留接口（向量/求解/图库/对象存储/模型网关，未接入）
"""
from __future__ import annotations

TOOL_GROUPS = {
    "processing": [
        "corpus_run", "segment_sentences", "segment_chunks", "validate_graph", "validate_schema",
        "detect_numeric_conflicts", "detect_time_conflicts", "build_provenance", "manifest",
        "embed", "embed_chunks",
        "reemit_meta", "reemit_provenance", "reemit_invariants", "reemit_evidence",
        "reemit_reasoning", "reemit_quality", "reemit_style", "reemit_index",
        "corpus_search", "corpus_get_chunk", "corpus_get_skeleton", "corpus_where_used",
        "graph_get_node", "graph_query", "graph_explain", "graph_impact", "graph_why",
        "gate_check", "evidence_get",
    ],
    "assembly": [
        "schema_diff", "decide_reuse", "instantiate_project", "build_work_package",
        "gate_check_draft", "bootstrap_ontology", "impacted_assets", "run_quality_gates",
        "check_number_consistency", "check_requirements", "sensitivity_analysis", "validate_shacl",
        "assess_capability", "validate_source_anchor", "project_where_written", "wp_get_facts",
    ],
    "library": [
        "library_list_packages", "library_search", "library_get_asset", "library_find_analog",
        "library_status", "library_promote", "library_publish",
    ],
    "semantic": [
        "resolve_concept", "semantic_classify", "ossie_import", "ossie_export",
        "ontology_export", "ontology_import",
    ],
    "reserved": [
        "semantic_search", "asset_rerank", "solve_constraint", "graph_db_query",
        "store_object", "llm_invoke",
    ],
}

GROUP_DISPLAY = {
    "processing": "知识处理七道工序",
    "assembly": "项目装配 + 验证 + 写作",
    "library": "历史资产库 + 发布",
    "semantic": "语义对齐 + 本体",
    "reserved": "预留接口",
}

GROUP_SERVER_NAMES = {
    "processing": "kp-processing",
    "assembly": "kp-assembly",
    "library": "kp-library",
    "semantic": "kp-semantic",
    "reserved": "kp-reserved",
}
