# 技能：workdsh-excel-design

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | workdsh-excel-design |
| description | 设计、分析或审查 Excel 工作簿时确定字段、来源、真实布局、公式和可用性；能力取决于当前可用表格工具，不宣称支持完整新建或高级图表。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 插件内置（bundled） |
| 目录 | /Users/apple/workdsh/.test-runtime/preview/profiles/preview/node_modules/workdsh-plugin-skills/resources/skills/workdsh-excel-design |
| 所属插件 | workdsh-plugin-skills |
| 文件数 | 3 |
| 体积 | 4.9 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：**未被范围内专家配备**
- 全部专家引用（含范围外）：无

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: workdsh-excel-design
description: "设计、分析或审查 Excel 工作簿时确定字段、来源、真实布局、公式和可用性；能力取决于当前可用表格工具，不宣称支持完整新建或高级图表。"
---

为 Excel 任务提供工作簿规划、公式与质量审查方法。读取 references/schema-and-formulas.md 规划表与数据；读取 references/audit-and-usability.md 检查范围、单位和使用体验。已有文件先读取当前工作簿结构和实际数据，不能猜路径、工作表 ID 或行列坐标。创建、编辑、分析和审查分别处理，只调用当前真实可用且授权的表格工具。WorkDSH Preview 已接入 spreadsheet：先读取 content_capabilities，使用 content_open 新建、content_read 获取真实 sheetId 与 revision，再通过 spreadsheet.* 操作修改值、公式和工作表，content_export 输出 XLSX。格式、合并与图表尚未接入；不能拿 document 操作伪造 Excel，也不能照搬 sheetagent MCP、子代理或安装命令。没有真实新建/导出能力时说明边界并交付可用的设计或分析，不能把它称为已生成 XLSX。
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 1165 | 9007ad5a621e8525 |
| references/audit-and-usability.md | 2046 | d783d223eacb4522 |
| references/schema-and-formulas.md | 1815 | 98c137228befb2ba |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/workdsh-excel-design/`（未改写；已用 SHA-256 复算校验）。
