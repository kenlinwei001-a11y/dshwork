# 推演式报告写作专家（deductive-report-writer）

以本体图谱、语义图谱、实体关系图谱与 Claim 图谱驱动的严谨商业报告推演写作专家，覆盖 50+ 商业文档类型。

## 定位

- **专家类型**：单专家（agent）
- **人格**：沈溯源，20 年商业报告专家
- **核心方法**：图谱驱动的推演式内容生成 —— 事实单源存储、跨章节自动传播、每条论断绑定证据与溯源链、正文可反向回读为图谱节点、冲突以「待审」显式呈现

## 覆盖的文档类型（节选，共 50+）

科研报告、立项报告、可行性研究报告（含政府投资项目可研）、ESG 报告、财报/年报、尽职调查报告、行业研究报告、投资分析报告、商业计划书、环评报告、安全评估报告、验收报告、结题报告等。

## 依赖技能（冻结于发布时）

| 能力 | 技能 |
|------|------|
| 资料解析 | document-parsing-skill |
| 语义分块 | semantic-chunking-skill |
| 句子切分 | sentence-segmentation-skill |
| 事实抽取 | fact-extraction-skill |
| 实体抽取 | entity-extraction-skill |
| 实体消解 | entity-resolution-skill |
| 本体映射 | ontology-resolution-skill |
| 关系抽取 | relation-extraction-skill |
| Claim 抽取 | claim-extraction-skill |
| Claim 校验 | claim-validation-skill |
| 证据绑定 | claim-evidence-binding-skill |
| 证据定位 | evidence-extraction-skill |
| 推理抽取 | reasoning-extraction-skill |
| 来源链 | provenance-binding-skill |
| 冲突检测 | conflict-detection-skill |
| 图谱编译 | semantic-graph-compilation-skill |
| 推演写作 | graph-deductive-writing-skill |
| 质量审计 | extraction-quality-audit-skill |
| 方法沉淀 | knowledge-generalization-skill |
| 可研（科研用房） | feasibility-report-edu-research |

> Word 交付遵循内置的 workdsh-word-design 指南与原生内容工具，不列为可冻结依赖。

## 交付物

- 本体注册表、语义图谱 JSON、实体关系清单、Claim 依赖树、溯源链
- 报告正文（Word/PDF）
- 冲突待审清单、证据覆盖审计表
- 正文 → 图谱节点回读索引

## 使用示例

见 plugin.json 的 `quickPrompts`（3 条）。

## 头像

当前未绑定头像图片。推荐在界面手动补充一张 512×512 PNG/JPG（≤500KB），建议风格：专业插画/漫画，一位戴细框眼镜的资深报告专家，背景为知识图谱节点与连线，冷青色（teal）调，与 categoryId `12-IndustryConsultant` 一致。

推荐生成提示词：

```
Professional cartoon-style illustration avatar, a senior male business report writing expert,
wearing refined glasses and a sharp vest over dress shirt, gesturing toward a holographic knowledge graph,
confident and meticulous expression with deep analytical aura,
ontology nodes, semantic graph links and evidence pins floating in the background.
Bust shot, facing forward. Clean simple deep teal background with silver accent. High quality, professional, natural.
```

## 状态

- 已完成：角色设计、完整文件包、技能绑定、校验。
- 待用户：在专家界面统一预览并确认发布。
