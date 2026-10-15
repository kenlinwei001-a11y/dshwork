# MCP 连接：kp-reserved

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 配置

| 字段 | 值 |
|---|---|
| 显示名 | kp-reserved |
| 连接 key | custom-kp-reserved |
| connectorId | __custom__ |
| serverName | kp-reserved |
| 传输 | stdio |
| 端点 | stdio · /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python |
| 启用状态 | true |
| 注入模式 | 始终注入 |
| 作用域 | 全局 |
| 鉴权模式 | none |
| 连接策略 | inherit |
| 健康状态 | healthy |
| 最近成功检查 | 2026-10-13T07:33:04.875Z |
| 诊断码 / 说明 | ok · 最近一次可用性检查通过 |

## 2. 该 server 的业务角色

保留区/预留能力（不对外承诺的扩展面）

## 3. 工具清单（6 个）

| 公开工具名（publicName） | 工具名 | 说明 |
|---|---|---|
| mcp__kp-reserved__semantic_search | semantic_search | 向量语义检索（预留）：按语义相似度检索资产，需 pgvector/Qdrant；当前 fallback=library_search |
| mcp__kp-reserved__asset_rerank | asset_rerank | 候选资产重排序（预留）：语义相关性重排，需 sentence-transformers；当前 fallback=library_find_analog |
| mcp__kp-reserved__solve_constraint | solve_constraint | 约束求解/优化（预留）：线性规划/排程/分配，需 OR-Tools/Pyomo；当前 fallback=规则重算 |
| mcp__kp-reserved__graph_db_query | graph_db_query | 图数据库查询（预留）：Cypher/Gremlin 受限查询，需 Neo4j/AGE；当前 fallback=graph_query(JSON 图) |
| mcp__kp-reserved__store_object | store_object | 对象存储（预留）：归档交付文件/附件，需 MinIO/S3；当前 fallback=本地 project_dir |
| mcp__kp-reserved__llm_invoke | llm_invoke | 模型网关（预留）：统一模型路由/重试/统计，需 LiteLLM；当前 fallback=Agent 直接调 LLM |

## 4. 使用方式

- 在会话/项目的连接器选择中选中该连接后，Host 在 agent/created 生命周期开放对应 mcp__ kp-reserved __* 命名空间。
- 项目「团队知识库」以连接器 kp-mcp（知识处理工具层）的形式引用了知识处理工具层；实际展开为上述 server。
- 没有连接选择时，这些工具不出现在模型的工具面上。

## 5. 边界

- 本包不采集、不保存任何凭据或本机密钥。
- 工具是否存在与工具是否被授权调用是两件事：策略（Tool > Server > Connection）与会话可见性逐层生效。
