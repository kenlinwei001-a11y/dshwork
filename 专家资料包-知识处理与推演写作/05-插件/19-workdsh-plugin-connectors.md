# 插件：workdsh-plugin-connectors

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

| 字段 | 值 |
|---|---|
| 名称 | workdsh-plugin-connectors |
| 版本 | 0.1.0-alpha.4 |
| 类型 | WorkDSH 功能插件 |
| 是否在 bundles | 是 |
| 安装目录 | /Users/apple/workdsh/.test-runtime/preview/profiles/preview/node_modules/workdsh-plugin-connectors |

## 1. 职责

WorkDSH MCP 连接管理：stdio / Streamable HTTP 实例、工具与资源发现、健康检查、凭据引用、按会话工具隔离。

## 2. 内置技能（0）

（该插件不携带内置技能）

## 3. 与本包范围专家的关系

- 其内置技能未被范围内专家引用。
- storages/workdsh_connectors/definitions 下的 8 条连接定义由它管理；与第三方 dsh-mcp-connector 是两套独立管理面。
