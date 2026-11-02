# 技能：fact-extraction-skill

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:44:08Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | fact-extraction-skill |
| description | 把可验证信息抽取为 Subject-Predicate-Value-Time-Source 结构化事实。触发：抽取事实、把数字和条件结构化、建立事实表。不适用：抽取观点、预测与建议（claim-extraction）、判定真伪（claim-validation）。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/fact-extraction-skill |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 5.3 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、标准要素抽取专家（expert-131e1b3979fe）、实验室证据抽取专家（expert-46a04687c733）、推演式报告写作专家（expert-97703554b311）、沈证源（member-ac7b53fc37a5）、沈证源（member-b6167c0afc18）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: fact-extraction-skill
description: "把可验证信息抽取为 Subject-Predicate-Value-Time-Source 结构化事实。触发：抽取事实、把数字和条件结构化、建立事实表。不适用：抽取观点、预测与建议（claim-extraction）、判定真伪（claim-validation）。"
---

# Fact Extraction Skill

## Skill ID
SK-06

## Purpose
将文本中的可验证信息抽取为 Subject-Predicate-Value-Time-Source 结构化事实。

## 何时使用

调用条件：已有 Sentence/Chunk 或 Document IR。
- 典型请求：抽取事实｜把数字和条件结构化｜建立事实表
- 不要在此调用：抽取观点、预测与建议（claim-extraction）、判定真伪（claim-validation）
## 边界与不适用

- 不做：不把判断或预测写成事实
- 不做：同一指标不同时点的数值不合并；无来源标记缺失
- 缺输入：先有 Sentence/Chunk 或 IR
## Input
- `project_id`
- `document_id`
- `version_id`
- 上游 Skill 输出
- 原文或结构化中间结果

## Output
必须输出稳定 ID、结构化结果以及 provenance/来源关联字段。

## Execution Rules
1. 只使用输入中存在或可由明确规则推导的信息，不编造事实。
2. 所有结果尽可能绑定 `project_id`、`document_id`、`version_id`。
3. Fact、Claim、Evidence、Reasoning 必须保留来源链。
4. 发现冲突时输出冲突状态，不擅自裁决。
5. 不得在没有复用策略的情况下跨项目复制项目专属事实。

## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。

## 与 claim 的边界：49 条 judgment 实为 fact（V2.8）

### 实测数据

一个可研项目 68 个 judgment 节点，**49 条实际是 fact**：

| 例子 | 为什么是 fact |
|---|---|
| `本报告编号 = 2019ZX054` | 编号，可查 |
| `建筑耐火等级 = 二级` | 参数，查图纸可验 |
| `各空调系统防火阀与风机联锁` | 规范要求转述（GB50016） |
| `人均面积指标应不超过 16㎡/人` | 规范要求转述（建标191） |
| `国拨 6000 万、自筹 7032 万` | 金额，查批复可验 |

### 判据（与 claim 的分工）

```
有具体取值 + 无判断词          → fact
含「应/不应/必须」+ 标准号      → fact（规范要求转述，不是本项目的判断）
主体-谓词-取值三元组齐全        → fact
含判断词（充分/合理/必要/可能）  → claim
```

### 改判不能删节点

改判为 fact 的节点**仍在图谱里**（`kind` 变了），只是移出 `claims.yaml`。

```python
# 正确：改 kind，保留节点与关系
n["kind"] = "fact"
n["reclassified_from"] = "judgment"
n["reclassified_claim_type"] = n.pop("claim_type")   # 保留痕迹

# 错误：删节点
# → 关系悬空
```

**实测坑**：改判后 `claim_type='fact'` 残留了 7 个节点，校验时报错。必须清掉并保留到 `reclassified_claim_type`。

### 规范要求 ≠ 项目取值

```
「无障碍电梯候梯厅深度 >1.8m」  → 这是 GB50763 的要求，不是本项目设计值
                              → 归 fact 但标 E2（规范条文），不标本项目取值
```

**实测 12 条无障碍尺寸被误当项目参数。**

## 工序（四段式）

**契约**

```json
{"fact": {"required": ["id", "subject", "predicate", "value", "section"],
          "value": {"description": "可为数字或字符串（'二级' / '2026-08-18/36h'）"}}
```

**执行**

```python
def extract(text, chunk) -> list[dict]:
    """与 claim 的边界：有具体取值+无判断词 → fact"""
    facts = []
    for m in SPO_PATTERN.finditer(text):
        if is_judge_sentence(m.group(0)):  continue      # 有判断词 → 去 claim
        if is_norm_restatement(m.group(0)):              # 规范转述 → fact 但标 E2
            facts.append({"subject": m["s"], "predicate": m["p"], "value": m["o"],
                          "kind": "fact", "evidence_kind": "E2"})
        else:
            facts.append({"subject": m["s"], "predicate": m["p"], "value": m["o"],
                          "kind": "fact", "evidence_kind": "E1"})
    return facts
```

**门禁 P7 · 事实完整**

```
每条有 主体-谓词-取值；规范转述标 E2（不是项目取值）；改判不删节点
```

**代价（实测）**

```
49 条 judgment 实为 fact（参数/规范转述/编号）
改判后 claim_type='fact' 残留 7 个节点 → 校验报错
→ 移到 reclassified_claim_type，保留改判痕迹
```
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 4493 | aaea9e8827c961ab |
| prompts/system.md | 153 | 577de86641e9c876 |
| schema/output.json | 378 | 27a42c18f725be78 |
| tests/expected.json | 45 | 5d712dd7c5c3f790 |
| tests/golden.json | 85 | e6f9967349a4bfc7 |
| validators/validator.py | 223 | b98df48348d743f6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/fact-extraction-skill/`（未改写；已用 SHA-256 复算校验）。
