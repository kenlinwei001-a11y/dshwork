# MCP：semantica

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 三视图在场情况

| 视图 | 是否存在 | 说明 |
|---|---|---|
| 会话可见 | 是 | 模型可调用 mcp__semantica__* |
| WorkDSH 定义 | 是 | DSH_HOME/storages/workdsh_connectors/definitions/semantica.json |
| 第三方注册表 | 否 | - |
| 运行时状态 | 未采集 | - |

## 2. WorkDSH 定义（磁盘权威）

| 字段 | 值 |
|---|---|
| id | semantica |
| 标题 | Semantica |
| 描述 | 图原生上下文与决策基础设施（15 工具）：实体/关系抽取、决策记录与检索、先例查找、因果链、知识图谱增删改查、推理、图分析、导出。｜已接入 DeepSeek LLM（凭据取自 ~/.semantica/env） |
| 传输 | stdio |
| 命令 | /bin/sh |
| 参数 | -c [ -f /Users/apple/.semantica/env ] && . /Users/apple/.semantica/env; SEMANTICA_KG_PATH=/Users/apple/.semantica/graph.json exec /Users/apple/.venvs/semantica/bin/python -m semantica.mcp_server |
| URL | - |
| env 键名 | （无） |
| 启用 | true |
| 创建时间 | 2026-10-13T07:18:21.700000Z |

## 3. 工具清单（0）

（无工具记录）

## 4. 关联

- 引用该 server 的技能：knowledge-processing
- 引用该项目连接：团队知识库 配置#8
