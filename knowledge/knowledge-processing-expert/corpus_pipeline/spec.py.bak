"""语料包 30 个产物的数据契约（单一事实源）。

字段：
  name     产物路径
  stage    工序（0=原稿入仓，全程=跨工序）
  fmt      格式
  size     量级
  primary  主存（权威副本）
  replica  副本（性能/交付冗余，以主存为准）
  mutable  可变性：冻结 / 可更新 / 追加
  agent    Agent 访问形式：① 注入 · ② 工具调用 · ③ 内嵌 · ✕ 不对外
"""
from __future__ import annotations

# 十类关系（全局单一事实源）
TEN_RELATIONS = (
    "has_value",     # 实体 → 数值
    "has_attribute", # 实体 → 属性
    "instance_of",   # 实体 → 类型
    "part_of",       # 部分 → 整体
    "causes",        # 事件 → 事件
    "depends_on",    # 节点 → 节点
    "supports",      # 证据 → 论断
    "contradicts",   # 事实 → 事实
    "temporal",      # 事件 → 时间
    "located_in",    # 实体 → 地点
)

# 30 个产物契约
MANIFEST: list[dict] = [
    {"name": "manifest.yaml",               "stage": "7",   "fmt": "YAML",     "size": "~2KB",      "primary": "对象存储",       "replica": "PG corpus 表",      "mutable": "冻结", "agent": "① 注入(constraints 段)"},
    {"name": "meta.yaml",                   "stage": "2",   "fmt": "YAML",     "size": "~1KB",      "primary": "PG corpus_meta", "replica": "对象存储",           "mutable": "冻结", "agent": "① 注入"},
    {"name": "provenance.yaml",             "stage": "全程", "fmt": "YAML",     "size": "~3KB",      "primary": "PG corpus_provenance", "replica": "对象存储",      "mutable": "冻结", "agent": "✕"},
    {"name": "outline.yaml",                "stage": "2",   "fmt": "YAML",     "size": "5-20KB",    "primary": "图库 :Section",  "replica": "对象存储",           "mutable": "冻结", "agent": "① 注入"},
    {"name": "source/original.docx",        "stage": "0",   "fmt": "二进制",    "size": "1-50MB",    "primary": "对象存储",       "replica": "—",                 "mutable": "冻结", "agent": "✕"},
    {"name": "source/normalized.md",        "stage": "1",   "fmt": "Markdown", "size": "200KB-2MB", "primary": "对象存储",       "replica": "—",                 "mutable": "冻结", "agent": "✕"},
    {"name": "source/offset_map.json",      "stage": "1",   "fmt": "JSON",     "size": "50-300KB",  "primary": "对象存储",       "replica": "—",                 "mutable": "冻结", "agent": "✕"},
    {"name": "source/assets/*",             "stage": "1",   "fmt": "png/csv",  "size": "不定",       "primary": "对象存储",       "replica": "—",                 "mutable": "冻结", "agent": "✕"},
    {"name": "chunks/chunks.jsonl",         "stage": "3",   "fmt": "JSONL",    "size": "100KB-1MB", "primary": "对象存储",       "replica": "—",                 "mutable": "冻结", "agent": "✕(含原值)"},
    {"name": "chunks/skeletons.jsonl",      "stage": "7",   "fmt": "JSONL",    "size": "80KB-800KB","primary": "对象存储",       "replica": "—",                 "mutable": "冻结", "agent": "② corpus_get_chunk"},
    {"name": "chunks/embeddings.parquet",   "stage": "3",   "fmt": "Parquet",  "size": "2-20MB",    "primary": "向量库",         "replica": "对象存储",           "mutable": "冻结", "agent": "✕"},
    {"name": "graph/nodes.yaml",            "stage": "4",   "fmt": "YAML",     "size": "20-200KB",  "primary": "图库 :Node",     "replica": "对象存储",           "mutable": "冻结", "agent": "② graph_get_node/graph_query"},
    {"name": "graph/rules.yaml",            "stage": "4",   "fmt": "YAML",     "size": "10-80KB",   "primary": "图库 :Rule",     "replica": "对象存储",           "mutable": "冻结", "agent": "② graph_explain"},
    {"name": "graph/relations.yaml",        "stage": "4",   "fmt": "YAML",     "size": "30-300KB",  "primary": "图库 边",        "replica": "对象存储",           "mutable": "冻结", "agent": "② graph_impact"},
    {"name": "graph/claims.yaml",           "stage": "4",   "fmt": "YAML",     "size": "10-60KB",   "primary": "图库 :Claim",    "replica": "对象存储",           "mutable": "冻结", "agent": "②+③"},
    {"name": "graph/invariants.yaml",       "stage": "6",   "fmt": "YAML",     "size": "~3KB",      "primary": "图库 :Invariant","replica": "对象存储",           "mutable": "冻结", "agent": "② gate_check"},
    {"name": "graph/graph.yaml",            "stage": "4",   "fmt": "YAML",     "size": "80-600KB",  "primary": "对象存储",       "replica": "—",                 "mutable": "冻结", "agent": "✕(整包不给)"},
    {"name": "evidence/evidence.yaml",      "stage": "4",   "fmt": "YAML",     "size": "5-40KB",    "primary": "PG evidence",    "replica": "对象存储",           "mutable": "可更新", "agent": "② evidence_get"},
    {"name": "evidence/excerpts/*.md",      "stage": "4",   "fmt": "Markdown", "size": "每条1-5KB",  "primary": "对象存储",       "replica": "—",                 "mutable": "冻结", "agent": "② evidence_get(with_excerpt)"},
    {"name": "reasoning/derivation.yaml",   "stage": "5",   "fmt": "YAML",     "size": "20-150KB",  "primary": "图库(链可由边重建)+对象存储", "replica": "—",       "mutable": "冻结", "agent": "② graph_explain"},
    {"name": "reasoning/decisions.yaml",    "stage": "5",   "fmt": "YAML",     "size": "5-50KB",    "primary": "PG decisions",   "replica": "对象存储",           "mutable": "冻结", "agent": "② graph_why"},
    {"name": "reasoning/trace.jsonl",       "stage": "5",   "fmt": "JSONL",    "size": "50-500KB",  "primary": "事件流",         "replica": "对象存储",           "mutable": "追加", "agent": "✕"},
    {"name": "quality/conflicts.yaml",      "stage": "6",   "fmt": "YAML",     "size": "~5KB",      "primary": "图库 :Conflict", "replica": "对象存储",           "mutable": "可更新", "agent": "③ 内嵌"},
    {"name": "quality/gaps.yaml",           "stage": "6",   "fmt": "YAML",     "size": "~5KB",      "primary": "图库 :Gap",      "replica": "对象存储",           "mutable": "可更新", "agent": "③ 内嵌"},
    {"name": "quality/gate_report.yaml",    "stage": "6",   "fmt": "YAML",     "size": "~3KB",      "primary": "PG gate_report","replica": "对象存储",           "mutable": "冻结", "agent": "①(仅结论行)"},
    {"name": "style/style_profile.yaml",    "stage": "7",   "fmt": "YAML",     "size": "~4KB",      "primary": "PG style_profile","replica": "对象存储",          "mutable": "可更新", "agent": "① 注入"},
    {"name": "style/section_templates/*.yaml","stage": "7", "fmt": "YAML",    "size": "每节2-10KB", "primary": "对象存储",      "replica": "—",                 "mutable": "冻结", "agent": "② corpus_get_skeleton"},
    {"name": "index/node_index.json",       "stage": "7",   "fmt": "JSON",     "size": "20-200KB",  "primary": "PG node_mention 表","replica": "对象存储",        "mutable": "冻结", "agent": "② corpus_where_used"},
    {"name": "index/term_index.json",       "stage": "7",   "fmt": "JSON",     "size": "5-50KB",    "primary": "PG term 表",     "replica": "对象存储",           "mutable": "可更新", "agent": "①(术语表段)"},
    {"name": "index/signature.yaml",        "stage": "7",   "fmt": "YAML",     "size": "~1KB",      "primary": "向量库 + PG",    "replica": "—",                 "mutable": "—",   "agent": "—"},
]

# 存储 schema（生产拓扑）
PG_TABLES = {
    "corpus":          "id, manifest_json, created_at",
    "corpus_meta":     "id, title, doc_type, data_cutoff, lang, source_sha",
    "corpus_provenance":"id, obj_type, obj_id, derived_from[], stage, ts",
    "evidence":        "id, claim_id, doc, page, span, kind, status",
    "decisions":       "id, derivation_id, decision, rationale, ts",
    "gate_report":     "id, corpus_id, gate, blockers[], ts",
    "style_profile":   "id, corpus_id, features_json, version",
    "node_mention":    "node_id, chunk_id, span, role",
    "term":            "id, surface, canonical, domain, freq",
}

GRAPH_LABELS = {
    "node":      "(:Node {id,type,value,chunk})",
    "section":   "(:Section {id,title,level,outline_ref})",
    "rule":      "(:Rule {id,expr,inputs[],outputs[]})",
    "claim":     "(:Claim {id,text,status,evidence[]})",
    "invariant": "(:Invariant {id,expr,scope})",
    "conflict":  "(:Conflict {id,type,involved[],status})",
    "gap":       "(:Gap {id,type,section,desc})",
    "edge":      "()-[:REL {type,evidence}]->()  # 十类关系",
}

VECTOR_COLLECTIONS = {
    "chunks":    "embeddings.parquet 的向量索引（语义检索 chunk）",
    "signature": "index/signature.yaml 的文风/匹配特征向量",
}

EVENT_STREAM = {
    "trace": "reasoning/trace.jsonl —— 推演回放步骤事件（追加）",
}

# Agent 访问契约：② 工具名 → 对应产物
AGENT_TOOLS = {
    "corpus_get_chunk":     "chunks/skeletons.jsonl",
    "corpus_get_skeleton":  "style/section_templates/*.yaml",
    "corpus_where_used":    "index/node_index.json",
    "graph_get_node":       "graph/nodes.yaml",
    "graph_query":          "graph/nodes.yaml",
    "graph_explain":        "graph/rules.yaml + reasoning/derivation.yaml",
    "graph_impact":         "graph/relations.yaml",
    "graph_why":            "reasoning/decisions.yaml",
    "gate_check":           "graph/invariants.yaml",
    "evidence_get":         "evidence/evidence.yaml (+excerpts)",
}

# ① 注入段（直接进 prompt）
INJECT_SECTIONS = {
    "constraints":   "manifest.yaml 的约束段",
    "meta":          "meta.yaml",
    "outline":       "outline.yaml",
    "gate":          "quality/gate_report.yaml（仅结论行）",
    "style":         "style/style_profile.yaml",
    "terms":         "index/term_index.json（术语表段）",
}
