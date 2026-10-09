# -*- coding: utf-8 -*-
"""空白 B 预留 MCP 接口（未来接入底层服务后透明可用）。

这些是「需要基础设施」的能力：向量检索、重排序、约束求解、图数据库、对象存储、模型网关。
MVP 阶段不实现底层，但预留 MCP 工具契约 + 占位实现，确保项目/专家能调用、未来接入后透明切换
（返回 status=reserved + 后端需求 + 当前可用的 fallback，不报错、不静默失败）。
"""
from __future__ import annotations

# 6 个预留工具：名称 → {kind, backend, fallback}
RESERVED_BACKENDS = {
    "semantic_search": {
        "kind": "vector",
        "backend": "pgvector 或 Qdrant + sentence-transformers",
        "fallback": "library_search（关键词检索，已可用）",
    },
    "asset_rerank": {
        "kind": "rerank",
        "backend": "sentence-transformers / reranker 模型",
        "fallback": "library_find_analog（确定性匹配，已可用）",
    },
    "solve_constraint": {
        "kind": "solver",
        "backend": "OR-Tools 或 Pyomo",
        "fallback": "instantiate_project 规则重算（四则运算，已可用）",
    },
    "graph_db_query": {
        "kind": "graph",
        "backend": "Neo4j 或 Apache AGE",
        "fallback": "graph_query（JSON 图查询，已可用）",
    },
    "store_object": {
        "kind": "storage",
        "backend": "MinIO 或 S3",
        "fallback": "本地文件（project_dir 落盘，已可用）",
    },
    "llm_invoke": {
        "kind": "gateway",
        "backend": "LiteLLM 或统一模型网关",
        "fallback": "Agent 直接调用 LLM（已可用）",
    },
}


def reserved_tool(name: str, args: dict) -> dict:
    """预留工具的统一占位返回。

    返回 status=reserved + 后端需求 + 当前可用的 fallback。接入后端后，本函数应被替换为
    真实实现（或由上层路由到真实后端），接口契约不变，调用方（项目/专家）无需改动。
    """
    spec = RESERVED_BACKENDS.get(name)
    if spec is None:
        return {"status": "unknown_tool", "name": name}
    return {
        "status": "reserved",
        "tool": name,
        "kind": spec["kind"],
        "backend_required": spec["backend"],
        "fallback_now": spec["fallback"],
        "note": "预留接口：接入后端后本工具透明切换为真实实现，调用方无需改动",
        "args": args,
    }
