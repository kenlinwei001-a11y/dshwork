# MCP 总览

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:31:19Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 为什么这里有三套视图

本机同时存在两个 MCP 管理面，它们的连接集合并不相同：

| 视图 | 来源 | 含义 | 本机数量 |
|---|---|---|---|
| 会话可见 | Harness 提供给本会话的 server 列表 | 模型实际能调用 mcp__<server>__* 的范围 | 9 |
| WorkDSH 定义 | storages/workdsh_connectors/definitions/*.json | WorkDSH 连接器页面管理的连接 | 9 |
| 第三方注册表 | storages/mcp_connector.json（dsh-mcp-connector） | mcp_connector_* 工具管理的连接 / 策略 / 授权 | 3 |

> 三者不一致是**本机现状**，不是本资料的判断错误。构建器如实并列，不做合并；不一致会在 `07-核对/01-校验结果.md` 的"提示"区列出。

## 2. 按 server 并列（12 个）

| server | 会话可见 | WorkDSH 定义 | 第三方注册表 | 运行时状态 | 工具数 |
|---|---|---|---|---|---|
| craftcad | - | 启用 | 存在（停用） | disabled | 18 |
| craftcad-ui | - | - | 存在（停用） | disabled | 8 |
| filesystem | 是 | 启用 | - | 未采集 | 0 |
| kp-assembly | 是 | 启用 | - | 未采集 | 0 |
| kp-library | 是 | 启用 | - | 未采集 | 0 |
| kp-processing | 是 | 启用 | - | 未采集 | 0 |
| kp-reserved | 是 | 启用 | - | 未采集 | 0 |
| kp-semantic | 是 | 启用 | - | 未采集 | 0 |
| playwright | 是 | 启用 | - | 未采集 | 0 |
| postgresql | 是 | - | - | 未采集 | 0 |
| semantica | 是 | 启用 | - | 未采集 | 0 |
| tavily-search | - | - | 存在（启用） | reauth | 5 |

第三方注册表补充：grant 记录 1 条、快照 20 条；**令牌与 env 值一律不采集**。

运行时健康（第三方注册表来源）：craftcad=disabled、craftcad-ui=disabled、tavily-search=reauth；快照 2026-11-02T11:27:22Z。

## 3. 逐 server 文档

- `06-MCP/01-craftcad.md`
- `06-MCP/02-craftcad-ui.md`
- `06-MCP/03-filesystem.md`
- `06-MCP/04-kp-assembly.md`
- `06-MCP/05-kp-library.md`
- `06-MCP/06-kp-processing.md`
- `06-MCP/07-kp-reserved.md`
- `06-MCP/08-kp-semantic.md`
- `06-MCP/09-playwright.md`
- `06-MCP/10-postgresql.md`
- `06-MCP/11-semantica.md`
- `06-MCP/12-tavily-search.md`

## 4. 与技能 / 项目的关系

- 技能对 MCP 的依赖只来自正文里的 mcp__<server>__ 引用（逐条取证见各技能文档第 6 节）。
- 项目在能力快照里以 connector 类型引用连接，构建时逐条解析到上表的 server。

## 5. 安全

- env 只记录键名；URL 去 userinfo；第三方注册表整体不复制（可能含 accessToken / refreshToken）。
- 连接存在 ≠ 工具被授权调用：策略（Tool > Server > Connection）与会话可见性逐层生效。
