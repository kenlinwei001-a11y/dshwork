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
from corpus_pipeline import review as corpus_review
from corpus_pipeline import dependencies as _dependencies
from corpus_pipeline import quality_gates as _quality_gates
from corpus_pipeline import capability as _capability
from corpus_pipeline import entity_registry as _entity_registry
from corpus_pipeline import schema_diff as _schema_diff
from corpus_pipeline import semantic_model as _semantic_model
from corpus_pipeline import ontology_schema as _ontology_schema
from corpus_pipeline import verification as _verification
from corpus_pipeline import reserved as _reserved
from corpus_pipeline.spec import MANIFEST, AGENT_TOOLS
from corpus_pipeline.groups import TOOL_GROUPS, GROUP_SERVER_NAMES
import os
import sys

# 按权限域/数据域拆分：--group 命令行参数（优先）或 KP_MCP_GROUP 环境变量决定本进程暴露哪一组工具。
# all=全部（兼容旧连接）；processing/assembly/library/semantic/reserved=单一分组。
GROUP = os.environ.get("KP_MCP_GROUP", "all")
if "--group" in sys.argv:
    idx = sys.argv.index("--group")
    if idx + 1 < len(sys.argv):
        GROUP = sys.argv[idx + 1]
if GROUP not in TOOL_GROUPS and GROUP != "all":
    GROUP = "all"

SERVER_NAME = GROUP_SERVER_NAMES.get(GROUP, "kp-mcp")
SERVER_INFO = {"name": SERVER_NAME, "version": "0.1.0"}
PROTOCOL_VERSION = "2025-06-18"


def _tools_for_group() -> list:
    """返回当前 GROUP 应暴露的工具列表。"""
    if GROUP == "all":
        return TOOLS
    names = set(TOOL_GROUPS.get(GROUP, []))
    return [t for t in TOOLS if t["name"] in names]

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
    {"name": "disambiguate", "description": "消歧（抽取后、冲突检测前必做）：主体/型号/表述/版本四类。返回各类修正条数。不做这步会把噪声当冲突报给甲方。",
     "inputSchema": {"type": "object", "properties": {
         "nodes_path": {"type": "string"},
         "chunks_path": {"type": "string", "description": "可选，用于主体消歧"},
         "table_rows": {"type": "array", "items": {"type": "object"},
                        "description": "可选，设备表行（no/name/air/cool/heat/power/qty），用于型号消歧"},
         "out_path": {"type": "string"}},
         "required": ["nodes_path", "out_path"]}},
    {"name": "resolve_version", "description": "版本消歧：给定标准编号或名称，返回应使用的现行版本与理由。",
     "inputSchema": {"type": "object", "properties": {"code_or_name": {"type": "string"}},
                     "required": ["code_or_name"]}},
    {"name": "tag_query", "description": "按标签检索公共标准库条款（域/主题/标准编号/关键词）。标签体系见 taxonomy.yaml，节点级标签如 结构.地震参数、给排水.消防给水。",
     "inputSchema": {"type": "object", "properties": {
         "library_path": {"type": "string", "description": "公共标准库目录"},
         "domain": {"type": "string", "description": "专业域，如 结构 / 消防 / 给排水"},
         "topic": {"type": "string", "description": "主题，如 地震参数 / 消防给水"},
         "code": {"type": "string", "description": "标准编号，如 GB50011"},
         "q": {"type": "string", "description": "条款正文关键词"}},
         "required": ["library_path"]}},
    {"name": "tag_text", "description": "给一段文本打标签（专业域.主题）。标准编号可优先定域，避免把防火规范误判成消防给水。",
     "inputSchema": {"type": "object", "properties": {
         "taxonomy_path": {"type": "string"}, "text": {"type": "string"},
         "std_hint": {"type": "string", "description": "标准编号或名称，如 GB50016-2014"}},
         "required": ["taxonomy_path", "text"]}},
    {"name": "build_derivation", "description": "把规则 deps 绑定到节点并生成 computed_from 关系（推演链进图谱）。返回绑定覆盖率、可执行规则、缺依赖清单。",
     "inputSchema": {"type": "object", "properties": {"nodes_path": {"type": "string"}, "rules_path": {"type": "string"},
                     "relations_path": {"type": "string"}}, "required": ["nodes_path", "rules_path", "relations_path"]}},
    {"name": "verify_derivation", "description": "执行推演链：按规则表达式算出结果，与原文值比对。返回 ✓对上 / ✗不符 / ⊘依赖缺失 明细。",
     "inputSchema": {"type": "object", "properties": {"bindings_path": {"type": "string"}, "nodes_path": {"type": "string"}},
                     "required": ["bindings_path", "nodes_path"]}},
    {"name": "parse_table_grid", "description": "从 docx 还原表格真实列结构（gridSpan/vMerge）。合并单元格在转 markdown 时会丢列，导致表头与数据错位（如「事业支出」跨 3 列）。返回定宽网格 + 合并后的表头（分组·子列）。",
     "inputSchema": {"type": "object", "properties": {"docx_path": {"type": "string"}}, "required": ["docx_path"]}},
    {"name": "extract_table_values", "description": "从 chunks 的 ```table 块抽值节点（确定性，9 条规则：序号排除/语义对齐校验/双层表头/汇总行/值列自带单位/跨列合并还原/占位符/全角归一化）。返回 nodes + skipped（含跳过原因）。",
     "inputSchema": {"type": "object", "properties": {"chunks_path": {"type": "string"}, "docx_path": {"type": "string"},
                     "exist_pairs": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}},
                     "required": ["chunks_path"]}},
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
    {"name": "validate_relation", "description": "按关系类型契约校验**一条**关系：类型是否已登记（含别名归约）、是否弃用、必需载荷是否齐备；返回 verdict 与缺失载荷清单；不合格时提示走 relation_candidates 候选路径",
     "inputSchema": {"type": "object", "properties": {"type": {"type": "string"}, "payload": {"type": "object"}}, "required": ["type"]}},
    {"name": "classify_changes", "description": "客户改稿 diff→分类→action（零 LLM、可复现）：结构 diff 判「多了/少了/变了」、锚判「同一对象移动 vs 新对象」；返回 changes[{action,id,anchor_before,anchor_after}]（move/add/delete/edit_number/edit_claim/edit_wording/untraced）",
     "inputSchema": {"type": "object", "properties": {"old_text": {"type": "string"}, "new_text": {"type": "string"}, "records": {"type": "array"}}, "required": ["old_text", "new_text"]}},
    {"name": "rebind_positions", "description": "位置重绑：**ID 不变**，只按 doc_span/quote 把锚重新解析到当前这一代物理层；重绑不到 ⇒ 保持 DANGLING 待审（只处理 DANGLING，UNLOCATED 不算失效）",
     "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "relation_types", "description": "关系类型登记表（七族·开放词表）：返回各族的类型清单与**必需载荷**，并可按 family 过滤；供抽取与校验环节引用，避免各处各写一份词表",
     "inputSchema": {"type": "object", "properties": {"family": {"type": "string"}}, "required": []}},
    {"name": "bootstrap_ontology", "description": "从新旧 Schema 差异生成 16 域可执行装配变更集（本体/论证链/任务DAG/规则/Skill/表单/提示词/质量闸门/复用策略/实体关系）",
     "inputSchema": {"type": "object",
                     "properties": {"old_schema": {"type": "object"}, "new_schema": {"type": "object"}},
                     "required": ["old_schema", "new_schema"]}},
    {"name": "check_requirements", "description": "需求完备性检查：对比已提供事实与必需变量，输出缺失清单（不编造）",
     "inputSchema": {"type": "object",
                     "properties": {"provided_facts": {"type": "array"}, "required_variables": {"type": "array"}, "project_goal": {"type": "string"}},
                     "required": []}},
    {"name": "sensitivity_analysis", "description": "敏感性分析：对输入变量做 ±Δ 扰动重算派生值，识别敏感变量（哪些变量变化显著影响结论）",
     "inputSchema": {"type": "object",
                     "properties": {"corpus_dir": {"type": "string"}, "provided_facts": {"type": "array"}, "meta": {"type": "object"}, "delta_ratio": {"type": "number"}},
                     "required": ["corpus_dir", "provided_facts"]}},
    {"name": "validate_shacl", "description": "SHACL 约束执行：检查节点是否符合本体约束（枚举/必填），输出违规清单",
     "inputSchema": {"type": "object",
                     "properties": {"nodes": {"type": "array"}, "shapes": {"type": "array"}},
                     "required": ["nodes"]}},
    {"name": "semantic_search", "description": "向量语义检索（预留）：按语义相似度检索资产，需 pgvector/Qdrant；当前 fallback=library_search",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}, "filters": {"type": "object"}}, "required": ["query"]}},
    {"name": "asset_rerank", "description": "候选资产重排序（预留）：语义相关性重排，需 sentence-transformers；当前 fallback=library_find_analog",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "candidates": {"type": "array"}}, "required": ["query", "candidates"]}},
    {"name": "solve_constraint", "description": "约束求解/优化（预留）：线性规划/排程/分配，需 OR-Tools/Pyomo；当前 fallback=规则重算",
     "inputSchema": {"type": "object", "properties": {"model": {"type": "object"}}, "required": ["model"]}},
    {"name": "graph_db_query", "description": "图数据库查询（预留）：Cypher/Gremlin 受限查询，需 Neo4j/AGE；当前 fallback=graph_query(JSON 图)",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "params": {"type": "object"}}, "required": ["query"]}},
    {"name": "store_object", "description": "对象存储（预留）：归档交付文件/附件，需 MinIO/S3；当前 fallback=本地 project_dir",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": []}},
    {"name": "llm_invoke", "description": "模型网关（预留）：统一模型路由/重试/统计，需 LiteLLM；当前 fallback=Agent 直接调 LLM",
     "inputSchema": {"type": "object", "properties": {"prompt": {"type": "string"}, "model": {"type": "string"}, "schema": {"type": "object"}}, "required": ["prompt"]}},
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
    {"name": "library_status", "description": "查询语料包的发布状态（draft/validated/published，P0 状态机）",
     "inputSchema": {"type": "object",
                     "properties": {"library_root": {"type": "string"}, "package": {"type": "string"}},
                     "required": ["package"]}},
    {"name": "library_promote", "description": "推进语料包状态（draft→validated→published 单向），需先 validated 才能发布",
     "inputSchema": {"type": "object",
                     "properties": {"library_root": {"type": "string"}, "package": {"type": "string"}, "target": {"type": "string"}},
                     "required": ["package", "target"]}},
    {"name": "library_publish", "description": "发布语料包（validated→published），发布后装配侧 library_* 才可检索/复用",
     "inputSchema": {"type": "object",
                     "properties": {"library_root": {"type": "string"}, "package": {"type": "string"}},
                     "required": ["package"]}},
    {"name": "impacted_assets", "description": "资产依赖图影响传播：给定变更资产，沿依赖图返回受影响的下游资产（取代按域静态判断）",
     "inputSchema": {"type": "object",
                     "properties": {"asset": {"type": "string"}},
                     "required": ["asset"]}},
    {"name": "decide_reuse", "description": "复用决策：根据新旧 Schema 差异决定 7 种复用策略之一（直接复用/参数化/向后兼容扩展/依赖联动/分支/重建/拒绝）",
     "inputSchema": {"type": "object",
                     "properties": {"old_schema": {"type": "object"}, "new_schema": {"type": "object"}, "forbidden": {"type": "boolean"}},
                     "required": ["old_schema", "new_schema"]}},
    {"name": "run_quality_gates", "description": "三质量关口 QG1/QG2/QG3：来源可信度/语义完整性/资产可复用性，返回汇总与失败关口",
     "inputSchema": {"type": "object",
                     "properties": {"corpus_dir": {"type": "string"}},
                     "required": ["corpus_dir"]}},
    {"name": "assess_capability", "description": "知识≠能力评估：区分「归纳的候选方法」与「登记的真实能力」，含候选缺口时 actionable=False",
     "inputSchema": {"type": "object",
                     "properties": {"domains": {"type": "array"}},
                     "required": ["domains"]}},
    {"name": "validate_source_anchor", "description": "校验 SourceAnchor 定位完整性（document_id 必填 + table_cell/char 精确定位）",
     "inputSchema": {"type": "object",
                     "properties": {"anchor": {"type": "object"}},
                     "required": ["anchor"]}},
    {"name": "build_source_ledger", "description": "生成源侧索引（引用/表/带单位数值/标题/题注/设备参数）。门禁前提。", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "source_md": {"type": "string"}, "source_docx": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "verify_closure", "description": "七道闭环校验：源侧索引 − 产物 − 豁免 = ∅。missing 非空即 FAIL。", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "draft_path": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "stage_gate", "description": "分步门禁 S0–S11（含探针正样本标定；未标定判 invalid）。", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "draft_path": {"type": "string"}, "source_md": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "objective_verify", "description": "12 条客观判据（确定性算法）；无法客观化者标 judgment_required。", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "draft_path": {"type": "string"}, "source_md": {"type": "string"}, "source_docx": {"type": "string"}, "declared_sha256": {"type": "string"}}, "required": ["corpus_dir"]}},
    {"name": "apply_claim_relations", "description": "按规则推导应有 claim 关系并合并入图（幂等；dry_run 支持）。", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "dry_run": {"type": "boolean"}}, "required": ["corpus_dir"]}},
    {"name": "verify_all", "description": "一次跑完三族门禁（闭环/分步/客观判据），落盘 quality/*.yaml，并按状态机写 manifest（FAIL 则停在 draft，不自动 publish）", "inputSchema": {"type": "object", "properties": {"corpus_dir": {"type": "string"}, "draft_path": {"type": "string"}, "source_md": {"type": "string"}, "source_docx": {"type": "string"}, "compile_point": {"type": "string"}, "declared_sha256": {"type": "string"}}, "required": ["corpus_dir"]}},

    {"name": "provider_status", "description": "可替换环节（entity/relation/reasoning/graph）的 provider 与能力表；供门禁判断判据可用性（缺能力 ⇒ invalid，不得 pass）。", "inputSchema": {"type": "object", "properties": {}}}
]


def _dispatch(name: str, args: dict):
    if name == "corpus_run":
        return run_pipeline(args["raw_text"], Path(args["out_dir"]), args.get("legal_outline"), doc_type=args.get("doc_type"))
    if name == "segment_sentences":
        return segment_sentences(args["text"], args.get("doc_id", "doc"))
    if name == "segment_chunks":
        return segment_chunks(args["text"], args.get("doc_id", "doc"))
    if name == "disambiguate":
        import json as _j
        from kp_toolkit.disambiguate import disambiguate as _dis
        _nodes = _j.load(open(args["nodes_path"], encoding="utf-8"))
        _ch = {}
        if args.get("chunks_path"):
            for _l in open(args["chunks_path"], encoding="utf-8"):
                if _l.strip():
                    _c = _j.loads(_l); _ch[_c["id"]] = _c.get("text") or ""
        _st = _dis(_nodes,
                   chunk_text_of=(lambda cid: _ch.get(cid, "")) if _ch else None,
                   table_rows=args.get("table_rows"))
        _j.dump(_nodes, open(args["out_path"], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return _st
    if name == "resolve_version":
        from kp_toolkit.disambiguate import resolve_version as _rv
        _use, _why = _rv(args["code_or_name"])
        return {"input": args["code_or_name"], "should_use": _use, "reason": _why,
                "status": "report_fix" if _use else "unknown"}

    if name == "tag_query":
        import yaml as _y, pathlib as _p
        from kp_toolkit.taxonomy import query as _q
        _lib = _p.Path(args["library_path"])
        _all = []
        for _d in sorted(_lib.iterdir()):
            _cf = _d / "clauses.yaml"
            if not _cf.exists(): continue
            _data = _y.safe_load(open(_cf, encoding="utf-8"))
            for _c in _data["clauses"]:
                _c.setdefault("standard", _data.get("standard") or _d.name)
                _all.append(_c)
        _hits = _q(_all, domain=args.get("domain"), topic=args.get("topic"),
                   code=args.get("code"), q=args.get("q"))
        return {"total": len(_hits), "clauses": _hits[:200]}
    if name == "tag_text":
        from kp_toolkit.taxonomy import load_taxonomy, tag_text as _tt
        _tax = load_taxonomy(args["taxonomy_path"])
        return {"tag": _tt(_tax, args["text"], args.get("std_hint"))}

    if name == "build_derivation":
        import json as _j, yaml as _y
        from kp_toolkit.derivation import bind_and_emit
        _n = _j.load(open(args["nodes_path"], encoding="utf-8"))
        _r = _y.safe_load(open(args["rules_path"], encoding="utf-8"))
        _rel = _j.load(open(args["relations_path"], encoding="utf-8"))
        _b, _rel2, _rep = bind_and_emit(_n, _r, _rel)
        _y.safe_dump(_b, open(args.get("bindings_out") or (args["rules_path"] + ".bindings.yaml"), "w", encoding="utf-8"),
                     allow_unicode=True, sort_keys=False, width=200)
        _j.dump(_rel2, open(args["relations_path"], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return _rep
    if name == "verify_derivation":
        import json as _j, yaml as _y
        from kp_toolkit.derivation import verify
        _b = _y.safe_load(open(args["bindings_path"], encoding="utf-8"))
        _n = _j.load(open(args["nodes_path"], encoding="utf-8"))
        return verify(_b, _n)

    if name == "parse_table_grid":
        from kp_toolkit.tables import parse_docx_table_grid
        return {"tables": parse_docx_table_grid(args["docx_path"])}
    if name == "extract_table_values":
        import json as _json
        from kp_toolkit.tables import parse_docx_table_grid, extract_table_values
        _ch = [_json.loads(l) for l in open(args["chunks_path"], encoding="utf-8") if l.strip()]
        _g = parse_docx_table_grid(args["docx_path"]) if args.get("docx_path") else []
        _ex = {(a, b) for a, b in (args.get("exist_pairs") or [])}
        _n, _sk = extract_table_values(_ch, _g, _ex)
        return {"nodes": _n, "skipped": _sk, "count": len(_n)}

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
    if name == "validate_relation":
        from pathlib import Path as _P
        import yaml as _y
        _cands = [_P(__file__).resolve().parent.parent / "corpus_pipeline" / "relation_types.yaml",
                  _P(__file__).resolve().parent.parent / "SHUFE-BDC-2019-001" / "reuse" / "relation_types.yaml"]
        _d = {}
        for _c in _cands:
            if _c.exists():
                _d = _y.load(_c.read_text(encoding="utf-8"),
                             Loader=getattr(_y, "CSafeLoader", _y.SafeLoader)) or {}
                break
        _reg = {}
        for _fam, _spec in (_d.get("families") or {}).items():
            for _ty, _meta in (_spec.get("types") or {}).items():
                _r = {"family": _fam, "required": _meta.get("required_payload") or [],
                      "status": _meta.get("status", "registered"),
                      "operator": _meta.get("operator", "")}
                _reg[_ty] = _r
                for _al in (_meta.get("aliases") or []):
                    _reg[_al] = dict(_r, alias_of=_ty)
        _ty = args.get("type")
        _pay = args.get("payload") or {}
        _m = _reg.get(_ty)
        if _ty == "has_value":
            return {"verdict": "reject", "reason": "has_value 是节点字段，不是关系",
                    "action": "把该值写在事实节点的 value/unit 上"}
        if not _m:
            return {"verdict": "candidate", "reason": f"类型未登记: {_ty}",
                    "action": "记入 relation_candidates.yaml，过五条准入后再登记",
                    "admission": ["有算子", "有必需载荷", "不同义", "有实例", "可迁移"]}
        if _m.get("status") == "deprecated":
            return {"verdict": "reject", "family": _m["family"], "reason": "类型已弃用"}
        _miss = [k for k in _m["required"] if k not in _pay]
        if _miss:
            return {"verdict": "candidate", "family": _m["family"], "missing": _miss,
                    "reason": "缺必需载荷 ⇒ 该关系不可判定",
                    "action": "补齐载荷后重提，或记入候选待审"}
        return {"verdict": "accept", "family": _m["family"], "operator": _m.get("operator", ""),
                "alias_of": _m.get("alias_of")}

    if name == "classify_changes":
        from corpus_pipeline.change_classify import classify as _cls
        return _cls(args.get("old_text", ""), args.get("new_text", ""),
                    args.get("records") or [], float(args.get("threshold", 0.72)))
    if name == "rebind_positions":
        # ★ 调**共享层**（不 import 项目环节脚本 —— 那会执行整条环节）
        from pathlib import Path as _P
        from corpus_pipeline import anchors as _anchors
        return _anchors.rebind(_P(args["corpus_dir"]))
    if name == "relation_types":
        from pathlib import Path as _P
        import json as _j, yaml as _y
        _p = _P(__file__).resolve().parent.parent / "corpus_pipeline" / "relation_types.yaml"
        if not _p.exists():
            _p = _P(__file__).resolve().parent.parent / "SHUFE-BDC-2019-001" / "reuse" / "relation_types.yaml"
        _d = _y.load(_p.read_text(encoding="utf-8"), Loader=getattr(_y, "CSafeLoader", _y.SafeLoader)) if _p.exists() else {}
        _fams = _d.get("families") or {}
        _want = args.get("family")
        _out = {k: v for k, v in _fams.items() if not _want or _want in k}
        return {"version": _d.get("version"), "families": _out,
                "governance": _d.get("governance"), "accounting": _d.get("accounting")}
    if name == "ontology_export":
        return _ontology_schema.export_ontology_schema(args.get("concepts"),
                                                       semantica_source=args.get("source", "local"))
    if name == "ontology_import":
        concepts = _ontology_schema.import_ontology_schema(args["schema"])
        result = {"concepts": concepts}
        if args.get("push_to_semantica"):
            result["semantica_push"] = _ontology_schema.push_ontology_to_semantica(args["schema"])
        return result
    if name == "bootstrap_ontology":
        diffs = _schema_diff.diff_schemas(args["old_schema"], args["new_schema"])
        return _ontology_schema.assemble_domain_changes(diffs, _ontology_schema._auto_semantica_client())
    if name == "check_requirements":
        return _verification.check_requirements(args.get("provided_facts", []),
                                                args.get("required_variables"), args.get("project_goal"))
    if name == "sensitivity_analysis":
        return _verification.sensitivity_analysis(args["corpus_dir"], args["provided_facts"],
                                                  args.get("meta"), args.get("delta_ratio", 0.1))
    if name == "validate_shacl":
        return _verification.validate_shacl(args.get("nodes", []), args.get("shapes"))
    if name in _reserved.RESERVED_BACKENDS:
        return _reserved.reserved_tool(name, args)
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
    if name == "library_status":
        return corpus_review.get_package_status(args.get("library_root") or corpus_library.DEFAULT_LIBRARY, args["package"])
    if name == "library_promote":
        return corpus_review.promote_package(args.get("library_root") or corpus_library.DEFAULT_LIBRARY, args["package"], args["target"])
    if name == "library_publish":
        return corpus_review.publish_package(args.get("library_root") or corpus_library.DEFAULT_LIBRARY, args["package"])
    if name == "impacted_assets":
        return {"asset": args["asset"], "impacted": _dependencies.impacted_assets(args["asset"])}
    if name == "decide_reuse":
        diffs = _schema_diff.diff_schemas(args["old_schema"], args["new_schema"])
        return _schema_diff.decide_change_strategy(diffs, forbidden=args.get("forbidden", False))
    if name == "run_quality_gates":
        return _quality_gates.run_all_gates(args["corpus_dir"])
    if name == "assess_capability":
        assess = _capability.assess_capability(args["domains"])
        return {**_capability.capability_summary(assess), "domains": assess}
    if name == "validate_source_anchor":
        return _entity_registry.validate_source_anchor(args["anchor"])
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
    # --- kp-patch: verify dispatch ---
    if name == "build_source_ledger":
        from corpus_pipeline.source_ledger import save_ledger as _save_ledger
        led = _build_ledger(md_path=args.get("source_md"), docx_path=args.get("source_docx"))
        _save_ledger(led, Path(args["corpus_dir"]) / "source_ledger.json")
        return {k: (len(v) if isinstance(v, list) else v) for k, v in led.items()}
    if name == "verify_closure":
        return _closure_verify(args["corpus_dir"], draft_path=args.get("draft_path"))
    if name == "stage_gate":
        return _run_stage_gates(args["corpus_dir"], draft_path=args.get("draft_path"),
                               source_md=args.get("source_md"))
    if name == "objective_verify":
        return _run_objective(args["corpus_dir"], draft_path=args.get("draft_path"),
                              source_md=args.get("source_md"),
                              source_docx=args.get("source_docx"),
                              declared_sha256=args.get("declared_sha256"))
    if name == "apply_claim_relations":
        return _apply_relations(args["corpus_dir"], dry_run=bool(args.get("dry_run")))
    if name == "provider_status":
        return _provider_status()
    # --- kp-patch: verify_all dispatch ---
    if name == "verify_all":
        from corpus_pipeline.verify_pipeline import apply_manifest_gate, verify_pipeline
        v = verify_pipeline(args["corpus_dir"], draft_path=args.get("draft_path"),
                            source_md=args.get("source_md"), source_docx=args.get("source_docx"),
                            compile_point=args.get("compile_point"),
                            declared_sha256=args.get("declared_sha256"))
        return {"verify": v, "manifest": apply_manifest_gate(args["corpus_dir"], v)}
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
    # 对齐 workdsh example-server：text 内容 + structuredContent 结构化结果。
    # MCP 客户端要求 structuredContent 必须是 object；数组一律包一层 {"items": [...]} 兜底。
    if not isinstance(data, dict):
        data = {"items": data}
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
            "structuredContent": data, "isError": False}


def handle(msg):
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "initialize":
        # 对齐 workdsh example-server：回显 client 请求的协议版本（默认 2025-06-18），
        # capabilities 声明 tools + resources。
        requested = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION
        return _result(req_id, {"protocolVersion": requested,
                                "capabilities": {"tools": {}, "resources": {}},
                                "serverInfo": SERVER_INFO})
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": _tools_for_group()})
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

# --- kp-patch: verification tools ---
# 校验类工具（客观判据；判定不消费 LLM 的意见）
try:
    from corpus_pipeline.source_ledger import build_source_ledger as _build_ledger
    from corpus_pipeline.closure_verify import closure_verify as _closure_verify
    from corpus_pipeline.stage_gates import run_stage_gates as _run_stage_gates
    from corpus_pipeline.objective_criteria import run_objective_criteria as _run_objective
    from corpus_pipeline.relations_ext import apply_expected_relations as _apply_relations
    from corpus_pipeline.providers import provider_status as _provider_status
    KP_VERIFY_TOOLS = ["build_source_ledger", "verify_closure", "stage_gate",
                       "objective_verify", "apply_claim_relations", "provider_status"]
except Exception:                       # pragma: no cover
    KP_VERIFY_TOOLS = []

