# dsh 侧 MCP 连接器（存档）

本目录保存 DSH `storages/mcp_connector.json`（「MCP连接器」弹窗）里已登记的连接定义。
它与 `../mcp-connectors/` 的 workdsh 侧定义是两套独立存储，不要混用：

- `install-local-config.sh` 只把 `../mcp-connectors/*.json` 安装到
  `<DSH_HOME>/storages/workdsh_connectors/definitions/`；本目录不会被自动安装。
- 本目录只用于记录和重建时手工核对，重建时在「MCP连接器」弹窗里添加。
- 同一个 `serverName` 只能出现在一套存储里，两边同名会报
  `serverName "X" is already in use`。
- OAuth 授权凭据（grantKey）不入库；Tavily 等连接重建后需要在弹窗里重新授权。
