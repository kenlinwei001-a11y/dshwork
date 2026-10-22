# 99-原件（逐字节副本）

本目录是源文件的**原样复制**，供离线核对与二次加工；正文未改写。

| 目录 | 内容 | 来源 |
|---|---|---|
| skills/<name>/ | 43 个技能的完整目录（已排除 .bak / .DS_Store） | 用户根 / Profile 根 / 插件 resources/skills |
| 专家定义/ | 范围内专家的记录 / 草稿 / 发布修订 JSON（保留源目录结构 experts\|drafts\|revisions） | storages/workdsh_experts |
| 项目/ | 项目状态文件（含配置修订、任务、资产引用） | storages/workdsh_projects/states |
| MCP定义/ | 各 MCP 连接的磁盘定义（源文件本身可能含 env 值，副本保持原样，请勿外发） | storages/workdsh_connectors/definitions |
| 数据/runtime-snapshot.json | 本次构建使用的运行时快照 | tools/expert-report/sources/runtime.json |

核对：`07-核对/04-源文件哈希.csv` 给出每个源文件的 SHA-256，可逐条复算。
