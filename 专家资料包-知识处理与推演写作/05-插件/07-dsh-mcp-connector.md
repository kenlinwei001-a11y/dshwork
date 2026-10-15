# 插件：dsh-mcp-connector（第三方 MCP 治理工具面）

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 是什么

第三方插件，提供 mcp_connector_* 工具族（状态、目录、配置、凭据、作用域、策略、快照、会话工具可见性等），用于在本机管理与治理 MCP 连接。

## 2. 能力概览（按用途分组）

| 分组 | 代表工具 | 用途 |
|---|---|---|
| 状态与发现 | mcp_connector_status / catalog / tools_list / tool_search / tool_detail | 看有哪些连接、每个 server 暴露哪些工具 |
| 配置与凭据 | configure / reconfigure / get_editable_config / rename / set_enabled / disconnect | 增删改连接，凭据只写官方凭据服务 |
| 作用域 | mcp_connector_scope | 全局或按项目绑定，copy/move 不复制 token |
| 治理策略 | mcp_connector_policy | Tool > Server > Connection > 默认允许 |
| 会话可见性 | mcp_connector_session_tools | 按会话激活精确工具，须用户明确指定 |
| 快照与迁移 | snapshot / export_config / import_json / migration_preview / migrate_legacy | 备份、脱敏导出、批量导入 |

## 3. 与这两个专家的关系

- 它是本包 MCP 章节的数据来源；知识处理链路所依赖的 5 个 kp-* server 与 PostgreSQL 都由它管理。
- 专家本身不调用它；调用它的是「配置链路的人（用户或会话）」，而不是专家角色。
