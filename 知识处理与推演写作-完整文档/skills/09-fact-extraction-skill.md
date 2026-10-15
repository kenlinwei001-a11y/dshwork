# Skill · fact-extraction-skill（SK-06）

## 名称与定位

- **名称**：`fact-extraction-skill`（Skill ID SK-06）
- **一句话**：将文本中的可验证信息抽取为 Subject-Predicate-Value-Time-Source 结构化事实。

## 角色

七道工序**第 4 道「本体抽取」**的事实通道。Fact 是图谱中参与计算的最小数值/断言单元，是「数值单源存储」的载体。

## 输入

Sentence/Chunk + 数值上下文（单位/口径）

## 输出

SPVTS 结构：
- Subject（主体）、Predicate（谓词）、Value（值）、Time（时间）、Source（来源）
- fact_id、单位（unit）、口径（caliber）、status（verified/unverified）
- 绑定 Sentence/Evidence 溯源

## 执行规则（语义，LLM 结构化 + validator）

- Value 带单位与口径；流量/存量区分标记（不可直接相减）。
- 无可验证来源的标 unverified，不升级为事实。
- 冲突不裁决（留给 conflict-detection-skill）。

## 关系

上游：sentence-segmentation；下游：claim/evidence/reasoning 抽取、semantic-graph-compilation-skill；装配侧 check_number_consistency 以事实清单查数。
