# MCP 连接：kp-library

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 配置

| 字段 | 值 |
|---|---|
| 显示名 | kp-library |
| 连接 key | custom-kp-library |
| connectorId | __custom__ |
| serverName | kp-library |
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

语料/图谱资料的库内读写与检索

## 3. 工具清单（7 个）

| 公开工具名（publicName） | 工具名 | 说明 |
|---|---|---|
| mcp__kp-library__library_list_packages | library_list_packages | 列出历史项目语料资产库中的所有语料包（名称/标题/文档类型/数据截止/规模），写新项目前先调用以盘点可复用资产 |
| mcp__kp-library__library_search | library_search | 跨历史语料包按关键词检索（标题/术语/章节匹配），返回命中片段，用于写新项目时找相似项目 |
| mcp__kp-library__library_get_asset | library_get_asset | 取某个历史语料包的指定可复用资产（outline/templates/style/terms/claims/nodes/rules/skeleton/evidence/meta），仅借形、不借值 |
| mcp__kp-library__library_find_analog | library_find_analog | 为新项目找最相似的历史语料包（文档类型优先匹配 + 关键词命中排序），返回建议复用的资产清单 |
| mcp__kp-library__library_status | library_status | 查询语料包的发布状态（draft/validated/published，P0 状态机） |
| mcp__kp-library__library_promote | library_promote | 推进语料包状态（draft→validated→published 单向），需先 validated 才能发布 |
| mcp__kp-library__library_publish | library_publish | 发布语料包（validated→published），发布后装配侧 library_* 才可检索/复用 |

## 4. 使用方式

- 在会话/项目的连接器选择中选中该连接后，Host 在 agent/created 生命周期开放对应 mcp__ kp-library __* 命名空间。
- 项目「团队知识库」以连接器 kp-mcp（知识处理工具层）的形式引用了知识处理工具层；实际展开为上述 server。
- 没有连接选择时，这些工具不出现在模型的工具面上。

## 5. 边界

- 本包不采集、不保存任何凭据或本机密钥。
- 工具是否存在与工具是否被授权调用是两件事：策略（Tool > Server > Connection）与会话可见性逐层生效。
