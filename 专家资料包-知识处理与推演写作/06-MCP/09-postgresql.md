# MCP：postgresql

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 三视图在场情况

| 视图 | 是否存在 | 说明 |
|---|---|---|
| 会话可见 | 是 | 模型可调用 mcp__postgresql__* |
| WorkDSH 定义 | 否 | - |
| 第三方注册表 | 是 | key=postgresql-postgresql |
| 运行时状态 | 有 | unknown |

## 2. 第三方注册表记录（脱敏）

| 字段 | 值 |
|---|---|
| key | postgresql-postgresql |
| connectorId | postgresql |
| 名称 | PostgreSQL |
| 传输 | stdio |
| serverName | postgresql |
| 启用 | true |
| env 键名 | （无） |
| header 键名 | （无） |

## 3. 运行时观测

| 字段 | 值 |
|---|---|
| 健康状态 | unknown |
| 诊断 | host-tools-pending · Host 尚未注册该 stdio Server 的工具，请检查启动日志后重试 |
| 作用域 | 全局 |
| 注入模式 | 始终注入 |
| 最近成功 | （无） |

## 4. 工具清单（13）

| 工具 |
|---|
| postgres_mcp_add_connection |
| postgres_mcp_bulk_load_csv |
| postgres_mcp_connect |
| postgres_mcp_db_context |
| postgres_mcp_describe_csv |
| postgres_mcp_disconnect |
| postgres_mcp_get_metrics_group |
| postgres_mcp_get_server_capabilities |
| postgres_mcp_list_connection_profiles |
| postgres_mcp_list_databases |
| postgres_mcp_modify |
| postgres_mcp_query |
| postgres_mcp_remove_connection |

## 5. 关联

- 引用该 server 的技能：无
- 引用该项目连接：无
