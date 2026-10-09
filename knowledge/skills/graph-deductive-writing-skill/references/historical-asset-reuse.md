# 写新项目：复用历史项目资产（Historical Asset Reuse）

写**新项目**时，先从知识处理专家沉淀的「历史语料资产库」中找相似项目、借其**形**（结构/
句式/规则/术语），再用新项目事实实例化图库，最后进入推演写作。本文档定义这一场景的工具
调用与硬约束。

## 前置条件

- `kp-mcp` MCP server 已连接（知识处理专家的工具层，含 library_* 工具）。
- 历史语料资产库目录存在（默认 `knowledge-processing-expert/corpus-library`，每个子目录是
  一个完整语料包，至少含 `manifest.yaml` + `meta.yaml`）。

## 四个 library_* 工具

| 工具 | 作用 | 关键参数 |
|------|------|----------|
| `library_list_packages` | 盘点资产库所有语料包（名称/标题/文档类型/数据截止/规模） | `library_root`（可选） |
| `library_search` | 跨语料包按关键词检索（标题/术语/章节标题命中） | `query`、`library_root` |
| `library_get_asset` | 取某语料包的指定可复用资产 | `package`、`asset`、`library_root` |
| `library_find_analog` | 为新项目找最相似语料包（文档类型优先 + 关键词排序） | `doc_type`、`query`、`library_root` |

`asset` 可选值：`meta` / `outline` / `templates`（节模板）/ `style`（文风）/ `terms`（术语表）/
`claims` / `nodes` / `rules`（规则表达式）/ `skeleton`（脱敏骨架）/ `evidence` / `manifest`。

## 工作流（写新项目）

1. 判定新项目的文档类型 `doc_type` 与主题 `query`。
2. `library_find_analog(doc_type, query)` → 得到最相似历史包 `best` 及建议资产清单。
3. 按需 `library_get_asset(best, asset)` 借形：
   - `outline` → 章节骨架与 must_cover 依据；
   - `templates` → 各节段落顺序、表格列结构、论证句式；
   - `style` → 数字格式/术语归一/引用体例/表题格式；
   - `terms` → 领域术语表；
   - `claims` / `rules` / `nodes` → Claim 模式、规则表达式、节点类型纪律。
4. `instantiate_project(corpus_dir=best, project_dir=<新项目目录>, provided_facts=<新事实>,
   meta=<新项目 meta>)` → 输出重绑定的新项目图库。
5. 进入 `SKILL.md` 的推演写作工作流（阶段 0–5）。

## 硬约束：借形不借值

- **可继承（形）**：outline 结构、节模板的段落顺序与论证句式、术语表、规则表达式、Claim
  模式、style profile、推导逻辑。
- **绝不继承（值）**：数值、单位、日期、具体实体名、结论、证据原文。`skeleton` 仅含
  `{{node:Nxx}}` 占位符，不携带任何历史原值。
- 新项目事实**只能**来自 `provided_facts`（用户/客户提供），不得从历史资产抄数值。
- **缺值守卫**：新项目缺失的输入 → `UNDEFINED` + instruction，正文写「待……后测算」并挂 gap，
  永不按 0 计算。
- **冲突待审**：回放检出的不一致 → 待审，不裁决、不改数字、不补口径。

## 反例

- ❌ 把历史包的「投资估算 3.2 亿」抄进新项目正文——值不可继承。
- ✅ 借历史包的「投资估算」节模板（列结构 + 论证句式），数值填入新项目 `provided_facts`。
- ❌ 新项目缺某输入时按 0 或历史值填——应挂 gap 写「待补充」。

## 历史语料资产库（corpus-library）

- 默认位置：`knowledge-processing-expert/corpus-library/`，每个子目录是一个完整语料包
  （30 文件契约 + `reuse/domains.yaml`）。
- 样例包：`PX-2026-001-feasibility`（某新材料生产基地扩产项目可研），由
  `corpus_pipeline/make_demo_library.py` 确定性生成，与知识处理专家产出格式一致。
- 生成/更新样例：`.venv/bin/python corpus_pipeline/make_demo_library.py`。

## 16 个可复用资产域（reuse/domains.yaml）

每个历史语料包携带 16 个「核心资产域」，写新项目时按域借形；每域记录其
`assembly_method`（装配方法）与 `mismatch_handling`（不一致处理）：

| # | 资产域 | 装配输出（形，可继承） |
|---|--------|------------------------|
| 1 | 本体中心 | 项目本体 Schema、变更集、映射表、版本记录 |
| 2 | 论证链 | 项目论证图、Claim 清单、缺失证据清单、推理任务 |
| 3 | 推演场景 | 项目场景集、参数绑定表、场景运行配置 |
| 4 | 变量定义 | 项目变量字典、字段映射、公式依赖图 |
| 5 | 任务图 DAG | 项目任务 DAG、节点参数、执行顺序和依赖检查结果 |
| 6 | 函数库 | 函数绑定清单、输入输出映射、测试结果 |
| 7 | 规则库 | 项目规则集、参数配置、冲突报告 |
| 8 | 不变式 | 项目约束集、约束绑定、可满足性检查结果 |
| 9 | Skills／技能库 | 项目 Skill 配置、输入输出契约、调用计划、执行记录 |
| 10 | 报告结构 | 项目报告大纲、章节依赖图、内容填充映射 |
| 11 | 报告表单 | 项目表单 Schema、字段映射、校验规则 |
| 12 | 提示词资产 | 版本化提示词、动态上下文、结构化输出契约 |
| 13 | 质量闸门 | 项目质量规则、校验报告、阻断项与整改项 |
| 14 | 复用策略 | 复用决策清单、资产来源、兼容性报告 |
| 15 | 实体与关系模型 | 项目实体图、关系实例、实体映射和消歧记录 |
| 16 | 成本／风险计算方法 | 项目成本模型、风险模型、参数表、计算与校验结果 |

取单域：`library_get_asset(package, "reuse")` 返回全部 16 域；按 `id` 定位单域
（ontology / argument_chain / scenario / variable / task_dag / function / rule / invariant /
skill / report_structure / report_form / prompt / quality_gate / reuse_strategy /
entity_relation / cost_risk）。

## Schema Diff + 语义对齐 + Ossie 对接

写新项目时，除借历史资产，还要做「结构差异分析 + 语义对齐」，判断新输入与历史模板的差异
类型（新增/缺失/类型变化/改名/同名异义），再按依赖关系**局部装配**。相关 MCP 工具：

| 工具 | 作用 |
|------|------|
| `schema_diff(old_schema, new_schema)` | 结构比对 + 语义分类：差异清单（added/removed/type_changed/renamed）+ 摘要 |
| `resolve_concept(name)` | 语义对齐：字段名 → 标准概念（canonical_name/aliases/kind/unit/formula） |
| `ossie_import(yaml_text)` | 从 Apache Ossie 语义模型 YAML 导入概念字典（fields→attribute、metrics→metric、synonyms→aliases） |
| `ossie_export(concepts)` | 概念字典导出为 Ossie 语义模型 YAML |

原则（「增量装配」而非模板复制）：

- 先 `schema_diff` 识别差异，再决定复用/扩展/重建；不因单字段差异判整个模板失效。
- `resolve_concept` 做语义对齐：命中概念判「改名/同义」，未命中交语义分类器判「新变量/元数据」。
- Ossie 导入/导出用于与 Apache Ossie 生态对接（dbt 转换器、DuckDB ossie 扩展），
  让语义概念用标准格式沉淀与交换。

