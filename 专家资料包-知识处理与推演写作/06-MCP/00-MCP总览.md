# MCP 总览

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. MCP 在本链路中的位置

MCP（Model Context Protocol）连接由连接器插件管理，向上以 mcp__<server>__<tool> 的形式暴露工具。专家定义里没有 MCP 字段；MCP 能力来自「项目/会话选择了哪条连接」。

## 2. 本机 6 条连接

| 连接 | key | 类型 | 传输 | 端点 | 注入 | 作用域 | 健康 |
|---|---|---|---|---|---|---|---|
| PostgreSQL | postgresql-postgresql | postgresql | stdio | stdio · npx | 始终注入 | 全局 | healthy |
| kp-processing | custom-kp-processing | 自定义 | stdio | stdio · /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python | 始终注入 | 全局 | healthy |
| kp-assembly | custom-kp-assembly | 自定义 | stdio | stdio · /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python | 始终注入 | 全局 | healthy |
| kp-library | custom-kp-library | 自定义 | stdio | stdio · /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python | 始终注入 | 全局 | healthy |
| kp-semantic | custom-kp-semantic | 自定义 | stdio | stdio · /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python | 始终注入 | 全局 | healthy |
| kp-reserved | custom-kp-reserved | 自定义 | stdio | stdio · /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python | 始终注入 | 全局 | healthy |

## 3. 工具规模

| server | 工具数 | 命名空间 |
|---|---|---|
| postgresql | 13 | mcp__postgresql__* |
| kp-processing | 30 | mcp__kp-processing__* |
| kp-assembly | 16 | mcp__kp-assembly__* |
| kp-library | 7 | mcp__kp-library__* |
| kp-semantic | 6 | mcp__kp-semantic__* |
| kp-reserved | 6 | mcp__kp-reserved__* |

## 4. 与这两个专家的关系

- 知识处理链路需要的 5 组工具（kp-processing / kp-assembly / kp-library / kp-semantic / kp-reserved）提供约 65 个工具，覆盖语料包七道工序与图谱/库/装配/保留区操作。
- 推演写作链路的脚本（graph-deductive-writing-skill 的 validate_graph.py 等）不依赖 MCP，可直接用本机 python3 运行。
- PostgreSQL 连接与两个专家无直接关系，属于本机通用数据能力。

## 5. 单条连接文档

- `01-postgresql.md`
- `02-kp-processing.md`
- `03-kp-assembly.md`
- `04-kp-library.md`
- `05-kp-semantic.md`
- `06-kp-reserved.md`

## 6. 安全与边界

- 令牌只写入官方凭据服务；本包不含任何凭据、token 或 API Key。
- 健康状态是采集时刻的观测值（5 条 healthy、PostgreSQL unknown/host-tools-pending）。
- 写操作类工具（如数据库 modify、批量装载）不因连接可用而自动获得授权，需按策略与会话可见性逐次确认。
