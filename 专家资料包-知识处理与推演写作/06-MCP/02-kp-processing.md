# MCP 连接：kp-processing

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 配置

| 字段 | 值 |
|---|---|
| 显示名 | kp-processing |
| 连接 key | custom-kp-processing |
| connectorId | __custom__ |
| serverName | kp-processing |
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

语料包七道工序执行（归一化 → 骨架 → 切块 → 本体 → 回放 → 质量 → 脱敏索引）

## 3. 工具清单（30 个）

| 公开工具名（publicName） | 工具名 | 说明 |
|---|---|---|
| mcp__kp-processing__corpus_run | corpus_run | 运行语料包七道工序全链路，返回工序汇总 |
| mcp__kp-processing__segment_sentences | segment_sentences | 确定性分句，返回稳定ID句子列表 |
| mcp__kp-processing__segment_chunks | segment_chunks | 确定性语义分块 |
| mcp__kp-processing__validate_graph | validate_graph | 校验图谱（悬空引用/重复id/统计） |
| mcp__kp-processing__detect_numeric_conflicts | detect_numeric_conflicts | 检测同一主语谓词下数值不一致，输出待审清单 |
| mcp__kp-processing__detect_time_conflicts | detect_time_conflicts | 检测时间矛盾，输出待审清单 |
| mcp__kp-processing__build_provenance | build_provenance | 从节点反向追溯证据，返回溯源链 |
| mcp__kp-processing__validate_schema | validate_schema | 校验一类节点的必填字段 |
| mcp__kp-processing__manifest | manifest | 返回语料包 30 个产物的文件清单契约 |
| mcp__kp-processing__corpus_get_chunk | corpus_get_chunk | 取脱敏 chunk（写作 Agent 唯一拿到的原文形态） |
| mcp__kp-processing__corpus_get_skeleton | corpus_get_skeleton | 取节模板 |
| mcp__kp-processing__corpus_where_used | corpus_where_used | 查节点被哪些 chunk 使用 |
| mcp__kp-processing__graph_get_node | graph_get_node | 取图节点 |
| mcp__kp-processing__graph_query | graph_query | 查询图节点 |
| mcp__kp-processing__graph_explain | graph_explain | 解释规则与推导链 |
| mcp__kp-processing__graph_impact | graph_impact | 查节点的关系影响 |
| mcp__kp-processing__graph_why | graph_why | 解释决策依据 |
| mcp__kp-processing__gate_check | gate_check | 运行不变式并返回闸门结论 |
| mcp__kp-processing__evidence_get | evidence_get | 取论断证据（可带摘录） |
| mcp__kp-processing__embed | embed | 把文本向量化（fastembed / BAAI-bge-small-zh-v1.5），返回向量 |
| mcp__kp-processing__embed_chunks | embed_chunks | 把语料包的所有 chunk 向量化并写 embeddings.json |
| mcp__kp-processing__reemit_meta | reemit_meta | 重发 meta.yaml（#2） |
| mcp__kp-processing__reemit_provenance | reemit_provenance | 重发 provenance.yaml（#3） |
| mcp__kp-processing__reemit_invariants | reemit_invariants | 重发 graph/invariants.yaml（#16） |
| mcp__kp-processing__reemit_evidence | reemit_evidence | 重发 evidence.yaml + excerpts（#18/#19） |
| mcp__kp-processing__reemit_reasoning | reemit_reasoning | 重发 derivation/decisions/trace（#20/#21/#22） |
| mcp__kp-processing__reemit_quality | reemit_quality | 重发 conflicts/gaps/gate_report（#23/#24/#25） |
| mcp__kp-processing__reemit_style | reemit_style | 重发 style_profile + section_templates（#26/#27） |
| mcp__kp-processing__reemit_index | reemit_index | 重发 node_index/term_index/signature（#28/#29/#30） |
| mcp__kp-processing__corpus_search | corpus_search | 向量检索脱敏 chunk（只返回占位符骨架，永不返回字面数值） |

## 4. 使用方式

- 在会话/项目的连接器选择中选中该连接后，Host 在 agent/created 生命周期开放对应 mcp__ kp-processing __* 命名空间。
- 项目「团队知识库」以连接器 kp-mcp（知识处理工具层）的形式引用了知识处理工具层；实际展开为上述 server。
- 没有连接选择时，这些工具不出现在模型的工具面上。

## 5. 边界

- 本包不采集、不保存任何凭据或本机密钥。
- 工具是否存在与工具是否被授权调用是两件事：策略（Tool > Server > Connection）与会话可见性逐层生效。
