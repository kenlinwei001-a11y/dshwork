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
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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

_SEMANTICA_SINGLETON = {}

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
    {"name": "check_standard_limit", "description": "按已转录的标准限值判定合规：围护结构热工性能（GB50189 表3.3.1-4 夏热冬冷）或照明功率密度（GB50034 表6.3）。缺参数或未匹配条目返回 UNKNOWN，不猜。",
     "inputSchema": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": ["thermal", "lpd"]},
         "part": {"type": "string", "description": "thermal: 屋面/外墙/架空或外挑楼板/外窗/屋顶透明部分"},
         "k": {"type": "number", "description": "thermal: 设计传热系数 W/(m²·K)"},
         "d": {"type": "number", "description": "thermal: 热惰性指标（屋面/外墙必填）"},
         "wwr": {"type": "number", "description": "thermal: 窗墙面积比（外窗必填）"},
         "shgc": {"type": "number", "description": "thermal: 太阳得热系数（可选）"},
         "direction": {"type": "string", "description": "thermal: 东/南/西/北"},
         "room": {"type": "string", "description": "lpd: 房间或场所"},
         "value": {"type": "number", "description": "lpd: 设计 LPD W/㎡"},
         "mode": {"type": "string", "enum": ["现行", "目标"]},
         "table": {"type": "string", "description": "lpd: 表号 6.3.3/6.3.7/6.3.13"}},
         "required": ["kind"]}},
    {"name": "normalize_name", "description": "命名归一化：去顿号/逗号/括号/空格后比较，并解析别名。用于「规则写通风空调工程 vs 原文写通风、空调工程」这类只差标点的误报。",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"},
         "aliases_path": {"type": "string", "description": "可选，别名表路径"}},
         "required": ["name"]}},
    {"name": "semantica_query", "description": "Semantica 图查询（全能）：mode=node 查单节点 / neighbors 多跳遍历（depth 1-5，可按边类型过滤）/ search 关键词搜索（可按节点类型过滤）。比本地 YAML 强在：模糊搜、多跳遍历、按边类型筛。",
     "inputSchema": {"type": "object", "properties": {
         "mode": {"type": "string", "enum": ["node", "neighbors", "search"], "description": "默认 neighbors"},
         "node_id": {"type": "string", "description": "node/neighbors 模式必填（Semantica UUID，可先用 semantica_node 由本地 ID 换 UUID）"},
         "depth": {"type": "integer", "description": "neighbors 跳数 1-5，默认 1"},
         "relationship_types": {"type": "array", "items": {"type": "string"}, "description": "只保留这些边类型，如 [computed_from, bounded_by]"},
         "query": {"type": "string", "description": "search 模式关键词"},
         "node_type": {"type": "string", "description": "search 模式节点类型过滤：fact/claim/evidence/decision"},
         "limit": {"type": "integer", "description": "结果上限"}},
         "required": ["mode"]}},
    {"name": "semantica_node", "description": "按本地节点 ID（N-xxx/CL-xxx/MC-xxx）查 Semantica 节点：返回 UUID、类型、properties、入边/出边明细（含对端 local_id 与标签）、度数。",
     "inputSchema": {"type": "object", "properties": {
         "local_id": {"type": "string", "description": "本地节点 ID"}},
         "required": ["local_id"]}},
    {"name": "semantica_analytics", "description": "Semantica 图分析：节点/边总数、PageRank Top10、社区数（community_count）。用于找最被依赖的节点与结构健康度。",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "semantica_precedents", "description": "按场景描述找相似历史决策（混合相似度）。单项目内也能用 —— 会返回本项目已记录的 decision 作为先例，用于判断同类冲突以前怎么处理的。",
     "inputSchema": {"type": "object", "properties": {
         "scenario": {"type": "string", "description": "场景描述，如「办公用水定额两个口径并存」"},
         "max_results": {"type": "integer", "description": "默认 5"}},
         "required": ["scenario"]}},
    {"name": "semantica_causal_chain", "description": "从 decision 节点追因果链（upstream/downstream，max_depth 默认5）。注意：只有当 decision 之间有 causes 类边时才有结果，本项目 20 个 decision 目前只连了 belongs_to，故返回空。",
     "inputSchema": {"type": "object", "properties": {
         "decision_id": {"type": "string", "description": "Semantica UUID"},
         "direction": {"type": "string", "enum": ["upstream", "downstream"]},
         "max_depth": {"type": "integer", "description": "默认 5"}},
         "required": ["decision_id"]}},
    {"name": "scan_vague_references", "description": "扫描「只写基于GB/符合规范/相关规范、没给具体标准号」的 fact 与 claim。这是真缺陷：读者无法核验引的哪一版哪一条。自动排除三类误报：警示语、规范内部引用（本规范）、同句已给编号或书名号。",
     "inputSchema": {"type": "object", "properties": {
         "nodes_path": {"type": "string", "description": "nodes.yaml 路径"},
         "relations_path": {"type": "string", "description": "可选，relations.yaml"},
         "out_path": {"type": "string", "description": "可选，结果输出路径"}},
         "required": ["nodes_path"]}},
    {"name": "validate_clause_library", "description": "条款库入库校验：检查每条条款是否带标准号(code)/标准全称(standard)/条款号(clause_no)/原文(clause_text)/来源(source)。可选校验关系是否指向带标准号的条款节点。不合格的返回补齐动作，不编造。",
     "inputSchema": {"type": "object", "properties": {
         "standard_dir": {"type": "string", "description": "公共标准库单一标准目录（含 clauses.yaml + standard.yaml）"},
         "library_dir": {"type": "string", "description": "或整个公共标准库根目录（批量校验）"},
         "relations_path": {"type": "string", "description": "可选，relations.yaml，校验 bounded_by 指向"},
         "nodes_path": {"type": "string", "description": "可选，nodes.yaml"},
         "out_path": {"type": "string", "description": "可选，报告输出路径"}},
         "required": []}},
    {"name": "scan_numeric_entities", "description": "扫描数值实体与判断句实体。① 数值实体：主体+数值+单位三者可核验，自动排除章节号/条款号/年份/序号/标准号；区分「规范要求」(norm) 与「项目取值」(value)。② 判断句实体：按判断词四族抽判断主体/对象/依据，每条带 falsifiable_by。",
     "inputSchema": {"type": "object", "properties": {
         "chunks_path": {"type": "string", "description": "chunks.jsonl 路径"},
         "nodes_path": {"type": "string", "description": "可选，nodes.yaml 路径（用于判漏抽）"},
         "mode": {"type": "string", "enum": ["numeric", "judgment", "both"], "description": "默认 both"},
         "out_path": {"type": "string", "description": "可选，结果输出路径"}},
         "required": ["chunks_path"]}},
    {"name": "detect_citations", "description": "识别文档内引用的外部标准（GB/JGJ/DGJ/建标/发改），对比公共标准库生成待抓清单。按引用次数分必抓/应抓/暂缓三档，并标注标准类型与抓取注意事项。只识别不抓取。",
     "inputSchema": {"type": "object", "properties": {
         "chunks_path": {"type": "string", "description": "chunks.jsonl 路径"},
         "library_path": {"type": "string", "description": "可选，公共标准库目录（用于判定缺哪些）"},
         "out_path": {"type": "string", "description": "可选，待抓清单输出路径"}},
         "required": ["chunks_path"]}},
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

    {"name": "provider_status", "description": "可替换环节（entity/relation/reasoning/graph）的 provider 与能力表；供门禁判断判据可用性（缺能力 ⇒ invalid，不得 pass）。", "inputSchema": {"type": "object", "properties": {}}},
  {"name": "recognize_number_forms",
   "description": "数值形态统一识别（八形态：quantity/tolerance/grade/material/spec/standard/count/表格行）。输入一句话，返回所有识别出的实体。",
   "inputSchema": {"type": "object", "properties": {
       "text": {"type": "string", "description": "待识别的句子"},
       "forms": {"type": "array", "items": {"type": "string"},
                 "description": "限定只识别某几类形态，省略则全识别"}},
       "required": ["text"]}},
  {"name": "extract_standard_forms",
   "description": "标准/规范引用抽取（含笔误纠正：JGJI00-1998→JGJ100-1998；全角破折号归一；无编号书名单独登记）。",
   "inputSchema": {"type": "object", "properties": {
       "text": {"type": "string"},
       "own_standard_codes": {"type": "array", "items": {"type": "string"},
                              "description": "排除已知标准号（避免把自身当引用）"}},
       "required": ["text"]}},
  {"name": "extract_two_pass",
   "description": "两级筛 + 二次判断：先判句子有无数字，排噪后识别，再对有数字但零产出的句子逐句报原因（防漏网）。",
   "inputSchema": {"type": "object", "properties": {
       "corpus_root": {"type": "string", "description": "语料包根目录"},
       "dry_run": {"type": "boolean", "description": "只报统计不落盘"}},
       "required": ["corpus_root"]}},
  {"name": "link_strict",
   "description": "严格建关系（名实相符判据）：has_attribute 要求名含、bounded_by 要求主题词交集≥2、part_of 要求子串、supports 要求同句。",
   "inputSchema": {"type": "object", "properties": {
       "corpus_root": {"type": "string"},
       "types": {"type": "array", "items": {"type": "string"},
                 "description": "限定建哪几类关系"}},
       "required": ["corpus_root"]}},
  {"name": "detect_universal_parent",
   "description": "检测万能父节点：单节点度数>40 且无 link_basis 占比>50%，按父节点主题词判不合格子节点。",
   "inputSchema": {"type": "object", "properties": {
       "corpus_root": {"type": "string"},
       "threshold": {"type": "integer", "description": "度数阈值，默认 40"}},
       "required": ["corpus_root"]}},
  {"name": "semantica_search",
   "description": "在 Semantica 图库中按关键词检索节点（区别于 graph_query 的本地图查询）。",
   "inputSchema": {"type": "object", "properties": {
       "query": {"type": "string"}, "limit": {"type": "integer"}},
       "required": ["query"]}}
]


def _dispatch(name: str, args: dict):
    if name == "recognize_number_forms":
        import sys as _s
        _s.path.insert(0, str(ROOT / "kp_toolkit"))
        from number_forms import recognize
        hs = recognize(args["text"])
        forms = args.get("forms")
        if forms:
            hs = [h for h in hs if h["form"] in forms]
        return {"count": len(hs), "hits": [
            {"form": h["form"], "subject": h["subject"], "value": h["value"],
             "unit": h["unit"], "extra": h["extra"], "span": list(h["span"])} for h in hs]}
    if name == "extract_standard_forms":
        import sys as _s
        _s.path.insert(0, str(ROOT / "kp_toolkit"))
        from standard_forms import extract_standards
        hs = extract_standards(args["text"], set(args.get("own_standard_codes") or []))
        return {"count": len(hs), "hits": [
            {"title": h["title"], "code": h["code"], "code_was": h["code_was"],
             "code_suspect": h["code_suspect"], "edition": h["edition"],
             "no_code": h.get("no_code", False)} for h in hs]}
    if name == "extract_two_pass":
        import subprocess as _sp, sys as _s
        cr = Path(args["corpus_root"])
        script = cr / "build" / "extract_two_pass.py"
        if not script.exists():
            return {"error": "缺少项目脚本", "path": str(script),
                    "hint": "在语料包工作区准备 build/extract_two_pass.py 后再调用"}
        cmd = [_s.executable, str(script)]
        if args.get("dry_run"):
            return {"note": "dry_run 需在项目工作区执行 build/extract_two_pass.py", "cmd": cmd}
        r = _sp.run(cmd, cwd=str(cr), capture_output=True, text=True, timeout=300)
        return {"exit": r.returncode, "stdout": r.stdout[-3000:], "stderr": r.stderr[-1000:]}
    if name == "link_strict":
        import subprocess as _sp, sys as _s
        cr = Path(args["corpus_root"])
        script = cr / "build" / "link_strict.py"
        if not script.exists():
            return {"error": "缺少项目脚本", "path": str(script),
                    "hint": "在语料包工作区准备 build/link_strict.py 后再调用"}
        r = _sp.run([_s.executable, str(script)], cwd=str(cr),
                    capture_output=True, text=True, timeout=300)
        return {"exit": r.returncode, "stdout": r.stdout[-3000:], "stderr": r.stderr[-1000:]}
    if name == "detect_universal_parent":
        import json as _j, pathlib as _p
        from collections import Counter as _C
        cr = _p.Path(args["corpus_root"])
        rels = _j.load(open(cr / "graph/relations.yaml", encoding="utf-8"))
        nodes = {n["id"]: n for n in _j.load(open(cr / "graph/nodes.yaml", encoding="utf-8"))}
        th = int(args.get("threshold") or 40)
        deg = _C()
        for r in rels:
            deg[r["from"]] += 1; deg[r["to"]] += 1
        EX = {"本项目", "本工程", "累计", "合计", "总计"}
        out = []
        for nid, d in deg.most_common():
            subj = str((nodes.get(nid) or {}).get("subject") or "")
            if d <= th or subj in EX:
                continue
            rf = [r for r in rels if r["from"] == nid or r["to"] == nid]
            nb = [r for r in rf if not (r.get("payload") or {}).get("link_basis")]
            out.append({"id": nid, "subject": subj[:30], "degree": d,
                        "no_basis": len(nb), "no_basis_pct": round(len(nb) / len(rf) * 100)})
        return {"threshold": th, "count": len(out), "suspects": out[:20]}
    if name == "corpus_run":
        return run_pipeline(args["raw_text"], Path(args["out_dir"]), args.get("legal_outline"), doc_type=args.get("doc_type"))
    if name == "segment_sentences":
        return segment_sentences(args["text"], args.get("doc_id", "doc"))
    if name == "segment_chunks":
        return segment_chunks(args["text"], args.get("doc_id", "doc"))
    if name == "check_standard_limit":
        from kp_toolkit.standards_check import check_thermal, check_lpd
        if args.get("kind") == "thermal":
            return check_thermal(part=args.get("part"), k=args.get("k"),
                                 d=args.get("d"), wwr=args.get("wwr"),
                                 shgc=args.get("shgc"), direction=args.get("direction") or "南")
        if args.get("kind") == "lpd":
            return check_lpd(room=args.get("room"), value=args.get("value"),
                             mode=args.get("mode") or "目标", table=args.get("table"))
        return {"error": "kind 必须是 thermal 或 lpd"}
    if name in ("semantica_query", "semantica_node", "semantica_analytics",
                "semantica_precedents", "semantica_causal_chain"):
        import sys as _ss
        _root = str(Path(__file__).resolve().parent.parent)
        if _root not in _ss.path: _ss.path.insert(0, _root)
        try:
            from corpus_pipeline.semantica_client import SemanticaClient
            _c = _SEMANTICA_SINGLETON.get("c")
            if _c is None:
                _c = SemanticaClient(); _c.start()
                _SEMANTICA_SINGLETON["c"] = _c
        except Exception as _e:
            return {"error": "Semantica 不可用", "detail": "%s: %s" % (type(_e).__name__, str(_e)[:200]),
                    "hint": "本地 YAML 仍可精确查；Semantica 仅补模糊搜/多跳/图分析"}
    if name in ("verify_gaps", "normalize_name"):
        import sys as _s21, json as _j21, pathlib as _p21, os as _os21
        _root21 = str(Path(__file__).resolve().parent.parent)
        if _root21 not in _s21.path: _s21.path.insert(0, _root21)
        from kp_toolkit.normalize import norm as _norm21, load_aliases as _la21, resolve as _res21
        from kp_toolkit.gap_verify import audit as _audit21
        _corpus = args.get("corpus_dir") or _os21.environ.get("KP_CORPUS_DIR") or "."
        _ap = args.get("aliases_path") or str(_p21.Path(_corpus) / "../公共标准库/aliases.yaml")
        _al = _la21(_ap) if _p21.Path(_ap).exists() else {}
        if name == "normalize_name":
            n = str(args.get("name") or "")
            return {"input": n, "normalized": _norm21(n), "canonical": _res21(n, _al)}
        # verify_gaps
        _nd = _p21.Path(_corpus) / "graph/nodes.yaml"
        if not _nd.exists():
            return {"error": "未找到 graph/nodes.yaml", "corpus_dir": str(_corpus)}
        _nodes = _j21.load(open(_nd, encoding="utf-8"))
        _ch = []
        _cf = _p21.Path(_corpus) / "chunks/chunks.jsonl"
        if _cf.exists():
            _ch = [_j21.loads(l) for l in open(_cf, encoding="utf-8") if l.strip()]
        return _audit21(args.get("gaps") or [], _nodes, _ch, _al)

        if name == "semantica_query":
            _a = {"mode": args.get("mode") or "neighbors"}
            for _k in ("node_id", "query", "node_type"):
                if args.get(_k): _a[_k] = args[_k]
            for _k in ("depth", "limit"):
                if args.get(_k) is not None: _a[_k] = int(args[_k])
            if args.get("relationship_types"): _a["relationship_types"] = args["relationship_types"]
            return _c.call("query_graph", _a)
        if name == "semantica_analytics":
            return _c.call("get_graph_analytics", {})
        if name == "semantica_precedents":
            return _c.call("find_precedents", {"scenario": args["scenario"],
                                               "max_results": int(args.get("max_results") or 5)})
        if name == "semantica_causal_chain":
            _a = {"decision_id": args["decision_id"],
                  "direction": args.get("direction") or "downstream",
                  "max_depth": int(args.get("max_depth") or 5)}
            return _c.call("get_causal_chain", _a)
        if name == "semantica_node":
            import json as _j3, pathlib as _p3
            _lid = str(args["local_id"])
            _gp = _p3.Path.home() / ".semantica/graph.json"
            if not _gp.exists():
                return {"error": "图文件不存在", "path": str(_gp)}
            _g = _j3.load(open(_gp, encoding="utf-8"))
            _hit = next((n for n in _g.get("nodes", [])
                         if (n.get("properties") or {}).get("local_id") == _lid), None)
            if not _hit:
                return {"error": "未找到本地 ID", "local_id": _lid,
                        "hint": "可用 semantica_query(mode=search) 按关键词先搜"}
            _nid = _hit["id"]
            _mk = {n["id"]: (n.get("properties") or {}) for n in _g.get("nodes", [])}
            def _brief(e, other):
                o = _mk.get(other, {})
                return {"type": e.get("type"), "local_id": o.get("local_id"),
                        "label": str(o.get("label") or o.get("subject") or "")[:60]}
            _in = [e for e in _g.get("edges", []) if e.get("target_id") == _nid]
            _out = [e for e in _g.get("edges", []) if e.get("source_id") == _nid]
            return {"local_id": _lid, "uuid": _nid, "type": _hit.get("type"),
                    "content": str((_hit.get("properties") or {}).get("content"))[:150],
                    "in_edges": [_brief(e, e.get("source_id")) for e in _in],
                    "out_edges": [_brief(e, e.get("target_id")) for e in _out],
                    "degree": len(_in) + len(_out)}

        if name == "semantica_search":
            r = _c.search_graph(args["query"], node_type=args.get("node_type"),
                                limit=int(args.get("limit") or 10))
            return r
        if name == "semantica_analytics":
            return _c.call("get_graph_analytics", {})
        if name == "semantica_node":
            # 本地 ID → UUID：直接读图文件建索引（比 export_graph 快且结构确定）
            import json as _j3, pathlib as _p3
            _lid = str(args["local_id"])
            _gp = _p3.Path.home() / ".semantica/graph.json"
            if not _gp.exists():
                return {"error": "图文件不存在", "path": str(_gp)}
            _g = _j3.load(open(_gp, encoding="utf-8"))
            _hit = None
            for _n in _g.get("nodes", []):
                if (_n.get("properties") or {}).get("local_id") == _lid:
                    _hit = _n; break
            if not _hit:
                return {"error": "未找到本地 ID", "local_id": _lid,
                        "hint": "可用 semantica_search 按关键词先搜"}
            _nid = _hit["id"]
            # 邻接边
            _in = [e for e in _g.get("edges", []) if e.get("target_id") == _nid]
            _out = [e for e in _g.get("edges", []) if e.get("source_id") == _nid]
            _mk = {n["id"]: (n.get("properties") or {}) for n in _g.get("nodes", [])}
            def _brief(e, other):
                o = _mk.get(other, {})
                return {"type": e.get("type"), "local_id": o.get("local_id"),
                        "label": str(o.get("label") or o.get("subject") or "")[:60],
                        "node_type": o.get("type_raw") or ""}
            return {"local_id": _lid, "uuid": _nid,
                    "type": _hit.get("type"), "properties": _hit.get("properties"),
                    "in_edges": [_brief(e, e.get("source_id")) for e in _in],
                    "out_edges": [_brief(e, e.get("target_id")) for e in _out],
                    "degree": len(_in) + len(_out)}
    # ══════════════════════════════════════════════════════════════════════
    # 14 个补齐的 dispatch（6 个预留 fallback + 8 个 reemit）
    # ══════════════════════════════════════════════════════════════════════
    if name in ("semantic_search", "asset_rerank", "solve_constraint",
                "graph_db_query", "store_object", "llm_invoke"):
        import os as _os, json as _j14, pathlib as _p14, glob as _g14
        corpus = args.get("corpus_dir") or _os.environ.get("KP_CORPUS_DIR") or "."
        root = _p14.Path(corpus)

        if name == "semantic_search":
            # fallback：无向量库时退化为关键词检索（读 YAML + 子串匹配）
            q = str(args.get("query") or "").strip()
            if not q:
                return {"error": "query 必填"}
            limit = int(args.get("limit") or 10)
            nd = root / "graph/nodes.yaml"
            if not nd.exists():
                return {"error": "未找到 graph/nodes.yaml", "corpus_dir": str(root)}
            nodes = _j14.load(open(nd, encoding="utf-8"))
            hits = []
            for n in nodes:
                blob = " ".join(str(n.get(k) or "") for k in ("subject", "value", "clause_text", "desc"))
                if q.lower() in blob.lower():
                    hits.append({"id": n["id"], "kind": n.get("kind"),
                                 "section": n.get("section"),
                                 "text": blob[:160]})
                    if len(hits) >= limit: break
            return {"mode": "fallback:keyword", "query": q, "count": len(hits),
                    "results": hits,
                    "note": "未接向量库（pgvector/Qdrant）；当前为关键词子串匹配。"
                            "需要语义相似度时配置 KP_QDRANT_URL 后重启"}

        if name == "asset_rerank":
            # fallback：按标签命中数 + 域优先排序
            items = args.get("items") or []
            want = [t for t in (args.get("tags") or []) if t]
            if not items:
                return {"error": "items 必填（待排序候选列表）"}
            def score(it):
                tags = it.get("tags") or []
                hit = len(set(tags) & set(want))
                return (hit, 1 if it.get("status") == "published" else 0)
            ranked = sorted(items, key=score, reverse=True)
            for i, it in enumerate(ranked, 1):
                it["_rank"] = i
                it["_score"] = score(it)
            return {"mode": "fallback:tag-match", "count": len(ranked), "items": ranked,
                    "note": "未接 sentence-transformers；当前按标签交集 + published 状态排序"}

        if name == "solve_constraint":
            # fallback：只支持单变量线性（ax=b），超范围明确拒绝
            var = args.get("variable") or "x"
            expr = str(args.get("expression") or "")
            given = args.get("given") or {}
            if not expr:
                return {"error": "expression 必填，如 '40 * 1800 / 1000'"}
            env = {str(k): float(v) for k, v in given.items() if isinstance(v, (int, float))}
            import re as _re14
            varnames = set(_re14.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr))
            missing = [v for v in varnames if v not in env and v != var]
            if missing:
                return {"error": "缺少变量取值", "missing": missing,
                        "hint": "先在 given 里给出；本工具不做符号求解"}
            try:
                val = eval(expr, {"__builtins__": {}}, env)  # noqa: S307 受限表达式
            except Exception as e:
                return {"error": "表达式求值失败", "detail": str(e)}
            return {"mode": "fallback:arithmetic", "expression": expr, "given": env,
                    "result": val,
                    "note": "未接 OR-Tools/Pyomo；仅支持算术求值与线性代入，不做整数规划/排程"}

        if name == "graph_db_query":
            # fallback：委托 Semantica 图查询（JSON 图）
            import sys as _s14
            _rt = str(Path(__file__).resolve().parent.parent)
            if _rt not in _s14.path: _s14.path.insert(0, _rt)
            try:
                from corpus_pipeline.semantica_client import SemanticaClient
                _c = _SEMANTICA_SINGLETON.get("c")
                if _c is None:
                    _c = SemanticaClient(); _c.start(); _SEMANTICA_SINGLETON["c"] = _c
                a = {"mode": args.get("mode") or "search"}
                for k in ("node_id", "query", "node_type"):
                    if args.get(k): a[k] = args[k]
                for k in ("depth", "limit"):
                    if args.get(k) is not None: a[k] = int(args[k])
                return {"mode": "fallback:semantica", "result": _c.call("query_graph", a),
                        "note": "未接 Neo4j/AGE；Cypher 不可用，已委托 Semantica JSON 图（3 模式 + 5 跳）"}
            except Exception as e:
                return {"error": "Semantica 不可用", "detail": "%s: %s" % (type(e).__name__, str(e)[:160]),
                        "hint": "可改用 graph_query（读 graph/*.yaml）"}

        if name == "store_object":
            # fallback：复制到项目目录
            src = args.get("source_path")
            rel = args.get("relative_path") or (src and _p14.Path(src).name)
            if not src or not rel:
                return {"error": "source_path 与 relative_path 必填"}
            sp = _p14.Path(src)
            if not sp.exists():
                return {"error": "源文件不存在", "source_path": str(sp)}
            dst = root / "attachments" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            import shutil as _sh14
            _sh14.copy2(sp, dst)
            return {"mode": "fallback:local-fs", "stored_at": str(dst),
                    "bytes": dst.stat().st_size,
                    "note": "未接 MinIO/S3；已复制到项目 attachments/ 目录"}

        if name == "llm_invoke":
            # 不代调模型：明确交给 Agent
            return {"error": "本工具不代调模型",
                    "reason": "knowledge-processing MCP 是确定性层，按设计不含模型网关",
                    "how": "需要语义步骤时由 Agent 直接调用模型，并按 schema 输出 + validator 校验",
                    "fallback_note": "原声明的 fallback='Agent 直接调 LLM' 即此含义"}

    if name.startswith("reemit_"):
        import os as _os, json as _j15, pathlib as _p15, yaml as _y15, datetime as _dt15
        corpus = args.get("corpus_dir") or _os.environ.get("KP_CORPUS_DIR") or "."
        root = _p15.Path(corpus)
        # (源文件列表, 产物路径, 说明)
        SPEC = {
            "reemit_meta":        ([], "meta.yaml", "项目元信息（从 project_profile.yaml 生成）"),
            "reemit_provenance":  (["graph/relations.yaml"], "provenance.yaml", "全量关系的来源链快照"),
            "reemit_invariants":  (["graph/nodes.yaml"], "graph/invariants.yaml", "图不变量（无孤儿/端点可寻址/类型闭环）"),
            "reemit_evidence":    (["evidence/evidence.base.yaml"], "evidence/evidence.yaml", "证据合并视图 + 摘录索引"),
            "reemit_reasoning":   (["graph/rules.yaml", "graph/derivation_bindings.yaml"], "reasoning/derivation.yaml", "推演规则与绑定"),
            "reemit_quality":     (["quality/conflicts.yaml", "quality/gaps.yaml"], "quality/gate_report.yaml", "质量门禁汇总"),
            "reemit_style":       ([], "style/style_profile.yaml", "文风画像（本项目未产出，需先跑风格分析）"),
            "reemit_index":       (["graph/nodes.yaml"], "index/node_index.yaml", "节点索引（id → 章节/类型/标签）"),
        }
        srcs, out_rel, desc = SPEC[name]
        missing = [x for x in srcs if not (root / x).exists()]
        if missing:
            return {"error": "源文件缺失，无法重发", "tool": name, "missing": missing,
                    "output": out_rel, "what": desc}
        payload = {}
        for x in srcs:
            fp = root / x
            d = _y15.safe_load(open(fp, encoding="utf-8")) if fp.suffix in (".yaml", ".yml") else _j15.load(open(fp, encoding="utf-8"))
            payload[x] = d
        # 生成产物
        if name == "reemit_meta":
            pp = root / "project_profile.yaml"
            meta = _y15.safe_load(open(pp, encoding="utf-8")) if pp.exists() else {}
            out = {"project_id": meta.get("project_id"), "title": meta.get("title"),
                   "version": meta.get("version"), "generated_at": _dt15.datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "source": "project_profile.yaml" if pp.exists() else "（无 project_profile.yaml）"}
        elif name == "reemit_invariants":
            nodes = payload["graph/nodes.yaml"]
            ids = {n["id"] for n in nodes}
            rels_p = root / "graph/relations.yaml"
            rels = _j15.load(open(rels_p, encoding="utf-8")) if rels_p.exists() else []
            dangling = [r for r in rels if r.get("from") not in ids or r.get("to") not in ids]
            linked = {r.get("from") for r in rels} | {r.get("to") for r in rels}
            orphans = [i for i in ids if i not in linked]
            out = {"node_count": len(nodes), "relation_count": len(rels),
                   "dangling_relations": len(dangling), "orphan_nodes": len(orphans),
                   "invariants": {"endpoints_resolvable": not dangling,
                                  "no_orphans": not orphans},
                   "generated_at": _dt15.datetime.now().strftime("%Y-%m-%d %H:%M")}
        elif name == "reemit_index":
            nodes = payload["graph/nodes.yaml"]
            out = {"count": len(nodes),
                   "by_id": {n["id"]: {"section": n.get("section"), "kind": n.get("kind"),
                                       "tags": n.get("tags")} for n in nodes},
                   "generated_at": _dt15.datetime.now().strftime("%Y-%m-%d %H:%M")}
        elif name == "reemit_provenance":
            rels = payload["graph/relations.yaml"]
            out = {"count": len(rels),
                   "chains": [{"rel": r["from"] + "~" + r["type"] + "~" + r["to"],
                               "source": r.get("source")} for r in rels],
                   "generated_at": _dt15.datetime.now().strftime("%Y-%m-%d %H:%M")}
        elif name == "reemit_quality":
            c = payload["quality/conflicts.yaml"]
            gp = payload["quality/gaps.yaml"]
            cl = c.get("conflicts") if isinstance(c, dict) else c
            from collections import Counter as _C15
            out = {"conflicts": len(cl or []),
                   "by_status": dict(_C15(str(x.get("status")) for x in (cl or []))),
                   "gaps": len(gp if isinstance(gp, list) else (gp.get("gaps") or [])),
                   "generated_at": _dt15.datetime.now().strftime("%Y-%m-%d %H:%M")}
        elif name == "reemit_evidence":
            ev = payload["evidence/evidence.base.yaml"]
            ev = ev if isinstance(ev, list) else ev.get("evidence", [])
            from collections import Counter as _C16
            out = {"count": len(ev), "by_kind": dict(_C16(str(x.get("kind")) for x in ev)),
                   "generated_at": _dt15.datetime.now().strftime("%Y-%m-%d %H:%M")}
        elif name == "reemit_reasoning":
            rules = payload["graph/rules.yaml"] or []
            binds = payload["graph/derivation_bindings.yaml"] or []
            out = {"rules": len(rules), "bindings": len(binds),
                   "generated_at": _dt15.datetime.now().strftime("%Y-%m-%d %H:%M")}
        else:
            out = {"note": "本项目未产出该产物", "tool": name}
        dst = root / out_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        _y15.safe_dump(out, open(dst, "w", encoding="utf-8"),
                       allow_unicode=True, sort_keys=False, width=200)
        return {"tool": name, "what": desc, "output": str(dst),
                "bytes": dst.stat().st_size, "source_files": srcs}


    if name == "scan_vague_references":
        import json as _j2, yaml as _y2
        from kp_toolkit.vague_refs import scan as _sv
        _nodes = _j2.load(open(args["nodes_path"], encoding="utf-8"))
        _rels = None
        if args.get("relations_path"):
            _rp = args["relations_path"]
            import os as _os
            if _os.path.exists(_rp): _rels = _j2.load(open(_rp, encoding="utf-8"))
        _r = _sv(_nodes, _rels)
        if args.get("out_path"):
            _y2.safe_dump(_r, open(args["out_path"], "w", encoding="utf-8"),
                          allow_unicode=True, sort_keys=False, width=200)
        return _r

    if name == "validate_clause_library":
        import sys as _sys, json as _j, yaml as _y, pathlib as _p, os as _os
        _agents_home = _p.Path(_os.environ.get("DSH_AGENTS_HOME") or (_p.Path.home() / ".agents"))
        _sk = _agents_home / "skills" / "standard-regulation-extraction" / "scripts"
        if str(_sk) not in _sys.path: _sys.path.insert(0, str(_sk))
        from extractors import validate_library as _vl, check_relation_targets as _crt, code_from_url as _cfu
        _res = {}
        _clauses = []
        if args.get("standard_dir"):
            _d = _p.Path(args["standard_dir"])
            _cf = _d / "clauses.yaml"
            if _cf.exists():
                _data = _y.safe_load(open(_cf, encoding="utf-8"))
                _sf = _d / "standard.yaml"
                _code = _name = None
                if _sf.exists():
                    _m = _y.safe_load(open(_sf, encoding="utf-8"))
                    _code, _name = _m.get("code"), _m.get("name")
                for c in _data.get("clauses", []):
                    _clauses.append({"code": c.get("code") or _code,
                                     "standard": c.get("standard") or _name,
                                     "clause_no": c.get("clause") or c.get("clause_no"),
                                     "clause_text": c.get("clause_text") or c.get("text"),
                                     "source_url": c.get("source_url"),
                                     "doc_id": c.get("id")})
        elif args.get("library_dir"):
            for _d in sorted(_p.Path(args["library_dir"]).iterdir()):
                _cf = _d / "clauses.yaml"
                if not _cf.exists(): continue
                _data = _y.safe_load(open(_cf, encoding="utf-8"))
                _sf = _d / "standard.yaml"
                _code = _name = None
                if _sf.exists():
                    _m = _y.safe_load(open(_sf, encoding="utf-8"))
                    _code, _name = _m.get("code"), _m.get("name")
                for c in _data.get("clauses", []):
                    _clauses.append({"code": c.get("code") or _code,
                                     "standard": c.get("standard") or _name,
                                     "clause_no": c.get("clause") or c.get("clause_no"),
                                     "clause_text": c.get("clause_text") or c.get("text"),
                                     "source_url": c.get("source_url"),
                                     "doc_id": c.get("id"),
                                     "_std": _d.name})
        if not _clauses:
            return {"error": "未找到条款：请提供 standard_dir 或 library_dir"}
        _res["clauses"] = _vl(_clauses)
        if args.get("relations_path") and args.get("nodes_path"):
            _rels = _j.load(open(args["relations_path"], encoding="utf-8"))
            _nds = {n["id"]: n for n in _j.load(open(args["nodes_path"], encoding="utf-8"))}
            _res["relations"] = _crt(_rels, _nds)
        if args.get("out_path"):
            _y.safe_dump(_res, open(args["out_path"], "w", encoding="utf-8"),
                         allow_unicode=True, sort_keys=False, width=200)
        return _res

    if name == "scan_numeric_entities":
        import json as _j, yaml as _y, pathlib as _p
        from kp_toolkit.numeric_entities import scan_numeric as _sn, scan_judgment as _sj
        _ch = [_j.loads(l) for l in open(args["chunks_path"], encoding="utf-8") if l.strip()]
        _nd = None
        if args.get("nodes_path"):
            _pth = _p.Path(args["nodes_path"])
            if _pth.exists(): _nd = _j.load(open(_pth, encoding="utf-8"))
        _mode = args.get("mode") or "both"
        _out = {}
        if _mode in ("numeric", "both"):
            _r = _sn(_ch, _nd)
            _out["numeric"] = {"stats": _r["stats"], "items": _r["items"][:200],
                               "invalid_sample": _r["invalid"][:40]}
        if _mode in ("judgment", "both"):
            _j2 = _sj(_ch)
            _out["judgment"] = {"stats": _j2["stats"], "items": _j2["items"][:200]}
        if args.get("out_path"):
            _y.safe_dump(_out, open(args["out_path"], "w", encoding="utf-8"),
                         allow_unicode=True, sort_keys=False, width=200)
        return _out


    if name == "detect_citations":
        import json as _j, yaml as _y, pathlib as _p
        from kp_toolkit.citations import detect as _det, make_tasks as _mk, summary as _sm
        _ch = [_j.loads(l) for l in open(args["chunks_path"], encoding="utf-8") if l.strip()]
        _codes = []
        if args.get("library_path"):
            _lf = _p.Path(args["library_path"]) / "standards.yaml"
            if _lf.exists():
                _codes = [x["code"] for x in _y.safe_load(open(_lf, encoding="utf-8"))["standards"]]
        _r = _det(_ch, _codes)
        _t = _mk(_r["missing"])
        if args.get("out_path"):
            _y.safe_dump({"note": "自动识别的引用缺口 → 待抓清单（按引用次数分档）",
                          "summary": _sm(_r, _t), "tasks": _t},
                         open(args["out_path"], "w", encoding="utf-8"),
                         allow_unicode=True, sort_keys=False, width=200)
        return {"summary": _sm(_r, _t), "tasks": _t[:60],
                "named_only": list(_r["names"].keys())[:30]}

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

