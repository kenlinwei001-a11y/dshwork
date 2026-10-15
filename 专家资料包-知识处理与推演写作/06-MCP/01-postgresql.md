# MCP 连接：postgresql

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 配置

| 字段 | 值 |
|---|---|
| 显示名 | PostgreSQL |
| 连接 key | postgresql-postgresql |
| connectorId | postgresql |
| serverName | postgresql |
| 传输 | stdio |
| 端点 | stdio · npx |
| 启用状态 | true |
| 注入模式 | 始终注入 |
| 作用域 | 全局 |
| 鉴权模式 | none |
| 连接策略 | inherit |
| 健康状态 | healthy |
| 最近成功检查 | 2026-10-13T07:33:04.962Z |
| 诊断码 / 说明 | ok · 最近一次可用性检查通过 |

## 2. 该 server 的业务角色

PostgreSQL 数据库查询与诊断（与两个专家无直接关系）

## 3. 工具清单（13 个）

| 公开工具名（publicName） | 工具名 | 说明 |
|---|---|---|
| mcp__postgresql__postgres_mcp_list_connection_profiles | postgres_mcp_list_connection_profiles | List all available PostgreSQL connection profiles. Returns a list of profiles with ID, name, host, port, and default dat |
| mcp__postgresql__postgres_mcp_connect | postgres_mcp_connect | Connect to a PostgreSQL database server using a profile ID and optional database name. The profile ID is retrieved from  |
| mcp__postgresql__postgres_mcp_disconnect | postgres_mcp_disconnect | Disconnect from a PostgreSQL database server using a connection ID. |
| mcp__postgresql__postgres_mcp_list_databases | postgres_mcp_list_databases | List all databases on the connected PostgreSQL server. Requires a connectionId from postgres_mcp_connect. Returns a list |
| mcp__postgresql__postgres_mcp_db_context | postgres_mcp_db_context | Get context about this database by fetching the CREATE scripts for a specific type of database object or all types. Use  |
| mcp__postgresql__postgres_mcp_bulk_load_csv | postgres_mcp_bulk_load_csv | Bulk‐load CSV file via COPY into a PostgreSQL table. Supports column mapping, optional SQL transforms, truncate-before-i |
| mcp__postgresql__postgres_mcp_describe_csv | postgres_mcp_describe_csv | Describe the structure and contents of a CSV file. Returns a YAML description of the CSV file, including fields, types,  |
| mcp__postgresql__postgres_mcp_get_server_capabilities | postgres_mcp_get_server_capabilities | CALL THIS FIRST before diagnosing performance issues. Discovers what diagnostic tools are available for the connected se |
| mcp__postgresql__postgres_mcp_get_metrics_group | postgres_mcp_get_metrics_group | Diagnose slow database and performance issues. USE THIS FIRST when users report slow queries, high CPU, or performance p |
| mcp__postgresql__postgres_mcp_query | postgres_mcp_query | Run a formatted SQL query against a database. For performance diagnostics, prefer postgres_mcp_get_metrics_group instead |
| mcp__postgresql__postgres_mcp_modify | postgres_mcp_modify | Modify the database and/or schema by executing SQL statements including DDL (CREATE, ALTER, DROP) and DML (INSERT, UPDAT |
| mcp__postgresql__postgres_mcp_add_connection | postgres_mcp_add_connection | Add a new PostgreSQL connection profile. The profile will be stored in ~/.postgres-mcp/connections.yaml. IMPORTANT: This |
| mcp__postgresql__postgres_mcp_remove_connection | postgres_mcp_remove_connection | Remove a PostgreSQL connection profile. This removes the profile from ~/.postgres-mcp/connections.yaml and deletes its p |

## 4. 使用方式

- 在会话/项目的连接器选择中选中该连接后，Host 在 agent/created 生命周期开放对应 mcp__ postgresql __* 命名空间。
- 项目「团队知识库」以连接器 kp-mcp（知识处理工具层）的形式引用了知识处理工具层；实际展开为上述 server。
- 没有连接选择时，这些工具不出现在模型的工具面上。

## 5. 边界

- 本包不采集、不保存任何凭据或本机密钥。
- 工具是否存在与工具是否被授权调用是两件事：策略（Tool > Server > Connection）与会话可见性逐层生效。
