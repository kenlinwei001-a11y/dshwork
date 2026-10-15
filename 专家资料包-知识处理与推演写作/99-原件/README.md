# 99-原件（逐字节副本）

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

本目录存放**原样复制**的源文件，供离线核对与二次加工；正文未做任何改写或转写。

| 目录 | 内容 | 来源 |
|---|---|---|
| skills/<name>/ | 22 个 Skill 的完整目录（SKILL.md、references、scripts、prompts、schema、tests、validators 等） | ~/.agents/skills/<name>/ |
| 专家制作稿/知识处理专家/ | 3 个文件（.workdsh-expert/plugin.json、agents/knowledge-processing-expert.md、README.md） | workdsh_expert_get_documents(expert-a54010bbb24e) |
| 专家制作稿/推演写作专家/ | 2 个文件（agents/expert.md、README.md） | workdsh_expert_get_documents(expert-a0a771c8b0da) |
| 采集原始数据/_data.json | 本次采集的原始结构化数据（专家定义、项目记录、MCP 状态与工具清单、插件清单等） | 本会话工具调用结果的原样导出 |

核对方法：把本目录 skills/<name>/ 与 ~/.agents/skills/<name>/ 对比即可确认未改写（例如 diff -r）。
