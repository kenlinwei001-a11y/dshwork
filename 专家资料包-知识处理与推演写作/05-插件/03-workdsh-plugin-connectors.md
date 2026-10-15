# 插件：workdsh-plugin-connectors（连接器插件）

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 是什么

MCP 连接管理插件：管理多条 stdio / Streamable HTTP MCP 实例，提供官方工具与资源发现、健康检查、运行时启停、增删改配置、官方凭据引用、能力中心页面与按会话的工具隔离。

## 2. 关键机制

- 令牌只写入 DSH 官方凭据服务；连接器配置、列表与诊断只返回凭据引用或「已配置」。
- 注入模式：始终注入 / 按会话选择；按会话选择时，Host 在官方 agent/created 生命周期中只开放对应 mcp__<server>__* 命名空间。
- 作用域：全局或绑定到具体项目（状态里有 scope.binding.projects）；全局启用状态与当前会话选择相互独立。
- 健康状态来自真实握手与工具注册观测，不用配置存在冒充「已连接」。

## 3. 本机连接（6 条）

| 连接 | 类型 | 传输 | 注入 | 作用域 | 健康 |
|---|---|---|---|---|---|
| PostgreSQL | postgresql | stdio | always | 全局 | healthy |
| kp-processing | 自定义 | stdio | always | 全局 | healthy |
| kp-assembly | 自定义 | stdio | always | 全局 | healthy |
| kp-library | 自定义 | stdio | always | 全局 | healthy |
| kp-semantic | 自定义 | stdio | always | 全局 | healthy |
| kp-reserved | 自定义 | stdio | always | 全局 | healthy |

## 4. 与这两个专家的关系

- 知识处理链路依赖 kp-processing / kp-assembly / kp-library / kp-semantic / kp-reserved 五个 stdio server（本地 Python 环境）提供 5 组工具。
- 项目「团队知识库」把连接器 kp-mcp（知识处理工具层）与知识处理专家、knowledge-processing-toolchain 一起固定进配置修订。
- 两专家的定义中没有任何 MCP 字段：连接是外部能力，由会话/项目选择。
