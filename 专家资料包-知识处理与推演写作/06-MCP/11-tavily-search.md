# MCP：tavily-search

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 三视图在场情况

| 视图 | 是否存在 | 说明 |
|---|---|---|
| 会话可见 | 否 | 本会话未提供该 server |
| WorkDSH 定义 | 否 | - |
| 第三方注册表 | 是 | key=tavily-search-tavily-search |
| 运行时状态 | 有 | recovering |

## 2. 第三方注册表记录（脱敏）

| 字段 | 值 |
|---|---|
| key | tavily-search-tavily-search |
| connectorId | tavily-search |
| 名称 | Tavily |
| 传输 | streamable-http |
| serverName | tavily-search |
| 启用 | true |
| env 键名 | （无） |
| header 键名 | Accept（值不采集） |

## 3. 运行时观测

| 字段 | 值 |
|---|---|
| 健康状态 | recovering |
| 诊断 | refresh · OAuth 刷新暂时失败，正在自动重试：HTTP 500: Internal Server Error |
| 作用域 | 全局 |
| 注入模式 | 始终注入 |
| 最近成功 | （无） |

## 4. 工具清单（5）

| 工具 |
|---|
| tavily_crawl |
| tavily_extract |
| tavily_map |
| tavily_research |
| tavily_search |

## 5. 关联

- 引用该 server 的技能：无
- 引用该项目连接：无
