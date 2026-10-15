# MCP · kp-mcp（知识处理工具服务）

> stdio MCP 服务，65 个工具，按「权限域/数据域」拆成 5 组。纯标准库实现（NDJSON 帧），
> 无需 `mcp` SDK。用工程 venv 的 Python 启动。

## 一、总体

| 项 | 值 |
|---|---|
| 主入口 | `mcp/server.py`（`--group <组>` 或 `KP_MCP_GROUP` 环境变量决定暴露哪一组；缺省 all=65） |
| 分组合入口 | `mcp/servers/kp_processing_server.py` / `kp_assembly_server.py` / `kp_library_server.py` / `kp_semantic_server.py` / `kp_reserved_server.py`（各自硬编码 GROUP，绕开 connector 参数传递 bug） |
| 分组定义 | `corpus_pipeline/groups.py`（TOOL_GROUPS / GROUP_DISPLAY / GROUP_SERVER_NAMES） |
| 协议 | JSON-RPC 2.0 over stdio，NDJSON 帧（一行一个 JSON）；initialize 回显客户端 protocolVersion |
| 工具总数 | 65（processing 30 + assembly 16 + library 7 + semantic 6 + reserved 6） |

## 二、五组职责

| 组 | 服务名 | 工具数 | 职责 |
|---|---|---|---|
| processing | kp-processing | 30 | 知识处理七道工序 + 基础工具（建图/抽取/冲突/溯源/脱敏） |
| assembly | kp-assembly | 16 | 项目装配 + 验证 + 写作（Schema Diff/复用决策/建图/组包/闸门/查数/关口） |
| library | kp-library | 7 | 历史资产库 + 发布（检索/复用/状态机） |
| semantic | kp-semantic | 6 | 语义对齐 + 本体（Ossie/Jev/Semantica 对接） |
| reserved | kp-reserved | 6 | 预留接口（向量/求解/图库/对象存储/模型网关，未接入） |

## 三、工具清单

### kp-processing（30）

| 工具 | 说明 |
|---|---|
| corpus_run | 七道工序全链路（文档 → 30 文件语料包） |
| segment_sentences / segment_chunks | 分句 / 分块（稳定 ID） |
| validate_graph / validate_schema | 图谱校验（悬空引用/重复 id）/ schema 校验 |
| detect_numeric_conflicts / detect_time_conflicts | 数字冲突 / 时间冲突检测（待审输出） |
| build_provenance | 溯源链构建（反向追到证据） |
| manifest | 30 文件契约清单 |
| embed / embed_chunks | 向量嵌入（fastembed 384 维） |
| reemit_meta / reemit_provenance / reemit_invariants / reemit_evidence / reemit_reasoning / reemit_quality / reemit_style / reemit_index | 8 个重发器（按需重生成指定产物） |
| corpus_search / corpus_get_chunk / corpus_get_skeleton / corpus_where_used | 语料检索（骨架/引用定位） |
| graph_get_node / graph_query / graph_explain / graph_impact / graph_why | 图谱访问（节点/查询/推演链/影响/理由） |
| gate_check / evidence_get | 闸门检查 / 证据读取 |

### kp-assembly（16）

| 工具 | 说明 |
|---|---|
| schema_diff | Schema 差异（added/removed/type_changed/renamed/semantic） |
| decide_reuse | 复用策略决策（strategy/reason/modify_template） |
| instantiate_project | 建新项目图库（语料包借形 + 新事实清单） |
| build_work_package | 组写作工作包（outline/facts/claims/conflicts/skeleton 指针） |
| gate_check_draft | 草稿闸门（字面数值/undefined 引用/must_cover） |
| bootstrap_ontology | 本体引导 |
| impacted_assets | 16 域依赖影响传播 |
| run_quality_gates | 三质量关口（QG1/QG2/QG3） |
| check_number_consistency | 查数（unbound 数字/口径存疑→待审） |
| check_requirements | 需求核对 |
| sensitivity_analysis | 敏感性分析 |
| validate_shacl | SHACL 校验 |
| assess_capability | 知识≠能力判定（induced/registered） |
| validate_source_anchor | SourceAnchor 校验（document_id+table_cell/char） |
| project_where_written / wp_get_facts | 反向回读 / 工作包事实分页 |

### kp-library（7）

| 工具 | 说明 |
|---|---|
| library_list_packages | 列出语料包（默认仅 published） |
| library_search | 关键词检索语料包（标题/术语/章节） |
| library_get_asset | 取语料包指定资产（16 域） |
| library_find_analog | 找最相似历史语料包（doc_type + 关键词命中） |
| library_status | 语料包状态（draft/validated/published） |
| library_promote / library_publish | 状态机推进 / 发布（validated→published） |

### kp-semantic（6）

| 工具 | 说明 |
|---|---|
| resolve_concept | 语义映射（Ossie 概念字典命中，未命中交分类器） |
| semantic_classify | 语义分类（默认确定性，Jev 预留 MCP 插槽） |
| ossie_import / ossie_export | Apache Ossie 标准字典导入/导出 |
| ontology_export / ontology_import | 本体导出/导入（OWL/SHACL/SKOS） |

### kp-reserved（6，预留未接入）

semantic_search（向量检索）/ asset_rerank（重排）/ solve_constraint（约束求解）/ graph_db_query（图库查询）/ store_object（对象存储）/ llm_invoke（模型网关）。

## 四、启动方式

```bash
cd /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert
.venv/bin/python mcp/server.py                     # 单进程全部 65 工具
.venv/bin/python mcp/servers/kp_library_server.py  # 只暴露 library 组 7 工具
```

## 五、注册（WorkDSH Host）

- 5 组连接定义存于 `~/.test-runtime/preview/storages/workdsh_connectors/definitions/kp-*.json`（workdsh-plugin-connectors 域）。
- 每组 `serverName` 分别 kp-processing/kp-assembly/kp-library/kp-semantic/kp-reserved；Host 中工具名为 `mcp__<组>__<tool>`。
- 项目「添加 MCP」与对话「连接器」按钮读该域列表；修改定义后需重启 DSH Host。

## 六、与 30 文件契约/装配链的对应

- processing 组对应「知识处理」主题（七道工序产出语料包）；
- library 组对应「写新项目时调用之前的资产」场景（历史语料包检索/复用/发布）；
- assembly 组对应「推演写作」主题（建图/组包/闸门/查数/回读）；
- semantic 组对接开源语义生态；reserved 组为未来 DB/图/向量/对象存储升级位。
