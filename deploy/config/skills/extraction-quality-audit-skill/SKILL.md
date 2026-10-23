---
name: extraction-quality-audit-skill
description: "对抽取结果执行结构完整性、证据覆盖、关系合法性、跨项目污染和孤立节点等质量审计。"
---

# Extraction Quality Audit Skill

## Skill ID
SK-17

## Purpose
对抽取结果执行结构完整性、证据覆盖、关系合法性、跨项目污染和孤立节点等质量审计。

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

## 关系类型（七族 · 开放词表）

权威定义：`relation_types.yaml`（**单点定义**，可用 MCP `relation_types` 读取）。
关系不是"边"，而是**能承载推理步的对象**；判据：**是否对应一个可执行算子**。

| 族 | 类型 | **必需载荷**（缺即不可判定） |
|---|---|---|
| **A 推理** | derives_from · entails · supports · contradicts · presupposes(=depends_on) · concludes · causes | 算子（operator/strength/prerequisite/conflict_type/mechanism） |
| **B 结构** | part_of · has_part · composes · located_in · temporal | **公理**（`axiom ∈ {sum,containment,membership}`；**sum 仅对可加量成立**） |
| **C 借用引用** | reuses · instantiates · fills · cites · sourced_from · declared_in · transfers_to · generalizes_to · supersedes · scoped_to | **范围** |
| **D 对齐锚定** | same_as · distinct_from · ambiguous_with | 消歧依据 |
| **E 资产治理** | depends_on_asset · gated_by · published_as · impacted_by | 状态与版本 |
| **F 规则**（**超边 n→1**） | computes · judges · selects | 输入/输出洞 + 类型约束 + guard |
| **G 约束** | bounds · requires · recommends · propagates_modality_to | 权威(名+条款+效力)+谓词+值域+模态+强度 |

**三条硬规则**：① 必需载荷缺一不可（缺则不可判定，不得提交）；② **`has_value` 不是关系**（节点字段，已弃用；实测曾占 77%，把 108 条真关系膨胀成 466 条）；③ 不符合七族者**不得丢弃、不得硬塞** —— 记入 `relation_candidates.yaml` 作为候选（抽取只能**归纳候选**，登记是受控动作）。

**扩充机制**：新类型过五条准入【有算子 / 有必需载荷 / 不同义 / 有实例 / 可迁移】；**同义按归约优先作别名**（如 `depends_on` → `presupposes`）；词表版本化，跨项目按版本解释。

**本 skill 的审计项（对七族逐项审计）**：
- **载荷完备率**：各类关系是否带齐必需载荷（缺载荷 ⇒ 该关系不可判定，计入不合格）
- **伪关系占比**：`has_value`/`has_attribute` 占关系层的比例（**>20% 即告警**；本项目实测 77%）
- **整族缺失**：是否出现族级空档（本项目实测 **C 借用引用 / F 规则 / G 约束 三族 0 条** ⇒ 可复用性、推演能力、合法性判据同时缺失）
- **超边丢形**：规则是否被压成二元边（应保持 n→1）
- **模态断链**：G 约束是否缺 `propagates_modality_to`（缺 ⇒ 「上限当最低需求」类错误必然发生）
- **死类型**：声明但零使用的类型须清理（如 `instance_of`/`has_attribute`）
- **候选积压**：`relation_candidates.yaml` 是否长期未审（只提议不登记 ⇒ 词表停滞）


## Validation
使用 `tests/golden.json` 和 `tests/expected.json` 执行基础验收。

<!-- kp-patch:v1 -->
## 闭环审计（对「完整性」的审计，而非仅「自洽性」）

本 skill 原有的审计维度（结构完整性、证据覆盖、关系合法性、跨项目污染、孤立节点）
检查的是**产物内部的自洽性**。它们**无法发现遗漏**——因为遗漏的东西不在被遍历的集合里。

补一层**闭环审计**：以源侧索引为基准做集合差。

| 闭环 | 判据 | 阈值 | 失败含义 |
|------|------|------|----------|
| C1 依据 | `原稿《》 − evidence − 豁免 = ∅` | 依据类缺口 = 0 | 报告引用的规范未登记，时效无法核查 |
| C2 关键取值 | `原稿「数字+单位」 − 节点值 − 量纲等价 = ∅` | 缺口 = 0 | 原稿有该数、图谱没建模 |
| C3 章节 | `原稿标题 − outline = ∅` | ≥ 98% | 抽取漏章 |
| C4 设备参数 | `原稿设备参数语句 − 设备节点 ≈ ∅` | ≥ 80% | 明细表无法重建 |
| C5 题注 | `原稿表/图题注 − 成稿 = ∅` | ≥ 60% | 表图未重出 |
| C6 装配 | `defined 且非明细节点 ∩ 成稿引用` | ≥ 95% | 抽到了没写进去 |
| C7 关系 | `应有 claim 关系 − 已有边 = ∅` | 各 100% | 关系词表缺类型 |

**两个必须遵守的细节**：

- **量纲归一**：不归一，「5000 万元」与「50000000 元」会被判成两个不同的数，产生**假缺口**；
  假缺口会磨损门禁可信度（报得太多，人就学会忽略）。
- **探针自证**：未过标定的探针，其判据输出 `invalid`，不得输出「无误」。

**输出契约**：`{id, name, total, covered, exempt, missing[], recall_pct, threshold, verdict}`
，`verdict ∈ {pass, FAIL, invalid}`。**不接受「看起来没问题」这类输出。**



## 门禁从 3 项到 13 项：新增 S8b 条款溯源（V2.8）

### 13 项门禁

| 阶段 | 门禁 | 检查什么 |
|---|---|---|
| S0 | 解析闭环 | docx 表格数 = md 表块数 |
| S1 | 切块闭环 | Σchunk ≈ 原稿字符（±15%） |
| S2 | 分句闭环 | Σsentence = Σchunk |
| S3 | 抽取闭环·引用 | 原稿引用 ⊆ 条款 |
| S4 | 编译闭环 | 端点可寻址 + 无孤儿 |
| S5 | 派生闭环 | 每条规则要么闭合要么显式阻塞 |
| S6 | 冲突/缺口闭环 | 多值必须登记待审 |
| S7 | 脱敏闭环 | 占位符数 = 节点引用数 |
| S8 | 依据闭环 | 每条有名称/编号/效力状态 |
| **S8b** | **条款溯源闭环** | **五项必填 + bounded_by 指向** |
| S9 | 域闭环 | 契约域齐全 |
| S10 | 装配闭环 | must_cover 全覆盖 |
| S11 | 全书闭环 | 章节闭环 + 节点引用闭环 |

### S8b 新增内容

```
条款五项必填：code / standard / clause_no / clause_text / source
bounded_by 必须指向带标准号的条款节点
不合格 → 标 pending_fetch，不编造
```

**实测**：69 条条款节点原本 `standard` 字段 0/69 全空 → 补齐后 69/69，
`trace_status=full` 68 条，1 条 `pending_fetch`（GB50009 未抓）。

### 缺陷登记册（22 条 / 6 类）

| 类型 | 条数 | 质疑什么 |
|---|---|---|
| 模糊引用 | 4 | 只写「符合规范」不给编号 |
| 缺依据 | 3 | 论断无出处 |
| 引用失效 | 6 | 引的旧版已被替代 |
| 标准缺日期 | 6 | 无法判是否现行 |
| 冲突待确认 | 2 | 原文自相矛盾 |
| 条款未引用 | 1 | 抓了没用（非缺陷） |

**每条都写：缺什么、为什么质疑、原文在哪。**

### 模糊引用的四层过滤

```
初扫 48 处 → 收紧后 4 处
排除 44 处误报：
  警示语（「不得据此判定符合规范」）29
  同句有编号 8
  后接书名号 4
  规范内部互引（「本规范」）3
```

**不做过滤就报 48 条，整份缺陷册失去可信度。**

### 一条铁律

> **门禁失败要能说清「缺什么、为什么、怎么补」。**
>
> 只报「不通过」没有价值；报「第 5.1.1 条缺标准号，从 source_url 反推可补」才有。


## 假缺四问：审计者的第一纪律（V2.9）

### 为什么审计 skill 必须讲这个

审计的价值不在于「报了多少问题」，在于「报的问题是不是真的」。

**实测**：一个项目累计报缺 1496 个，复核后真缺 345 个 —— **假缺率 77%**。

| 报的问题 | 报的数量 | 真缺 | 假的原因 |
|---|---|---|---|
| 关系缺证据 | 190 | **2** | 只查 `relation.source` |
| 模糊引用 | 48 | **4** | 缺四层过滤 |
| 条款必填缺失 | 131 | **0** | 字段别名不认 |
| 推演必填缺失 | 75 | **0** | `False` 被当缺失 |
| 缺依赖规则 | 42 | **12** | 绑定漏 + 值没抽 + 表格没解析 |
| 孤儿节点 | 1010 | **327** | `'None'` 字符串 + 描述性无关系 |

### 四问（每一问都要留 searched 证据）

```
① 节点真的不存在？
   → 精确 / 包含 / 去标点归一，三种方式都搜过

② 原文真的没有？
   → 纯文本 / markdown 表格 / 表格注 / 跨节引用，四种载体都搜过

③ 绑对了节点吗？
   → 量纲校验（费率不能绑金额）+ 章节校验 + 最长匹配

④ 设计上就不该有？
   → 描述性事实不需要关系；判定项不是数值依赖
```

### 报缺的输出格式（强制）

```yaml
- missing: 增容后变压器容量
  why_real: ① 节点表三方式无 ② 原文 §6.5.2 只有原容量 2×1000kVA ③ 非表格值 ④ 是数值依赖
  searched: ["nodes: 精确+包含+归一", "chunks: 增容|变压器|kVA", "tables: §6.5.2 全部"]
  conclusion: 真缺
```

**没有 `searched` 字段的「缺」，不许进台账。**

### 三个自检脚本（建议实现）

```bash
# ① 报缺前：验证节点真的不存在
python -m kp_toolkit.cli search-node "<subject>" --ways exact,contains,norm

# ② 报缺前：验证原文真的没有
python -m kp_toolkit.cli search-text "<keyword>" --carriers text,table,note,cross-section

# ③ 报缺后：抽查 3 条，看是不是假缺
python -m kp_toolkit.cli audit-gaps --sample 3 --explain
```

### 一条铁律

> **审计的公信力 = 1 / (1 + 假缺率)。**
>
> 77% 假缺率意味着编制方查 4 条就有 3 条是假的，整份报告不再被信任。
> **宁可少报一个真缺，不要多报十个假缺。**

## 改动影响面：审计员也要查（V2.9）

审计不只看数据，还要看**改动是否同步**。

### 六种不同步（本项目全踩过）

| # | 上游改了 | 下游没跟上 | 后果 |
|---|---|---|---|
| 1 | `content_export` 返回 presented | 文件没落盘 | 交付了不存在的文件 |
| 2 | 推 1301 节点到图库 | 缺 `content` 字段 | 全搜不到 |
| 3 | skill SKILL.md 改了 | 7 个 references/scripts 没改 | 方法论与执行不一致 |
| 4 | skill 改了 | 提示词生成器没改 | 119 节提示词还是旧的 |
| 5 | claim 判据变了 | 其他 skill 没改 | 口径不一致（19 vs 68） |
| 6 | schema 加了字段 | 校验脚本没加 | 新字段无人校验 |

### 审计时要查的三条

```
① 声明了但没实现？→ MCP 工具声明数 vs dispatch 数
② 改了但没重新生成？→ 生成器 mtime vs 产物 mtime
③ 多个 skill 共用标准？→ 各处口径是否一致（如 claim 数量）
```

### 实测

```
MCP 声明 94 工具，其中 14 个没 dispatch → 调用报错
119 节提示词比 skill 落后一轮 → 缺 5 个新字段
```

**这类问题不会自己暴露，必须主动查。**

## 工序（四段式）

> **「假缺四问」的判据、四问清单、报缺输出格式都在上一节**（156–219 行，已详述）。
> 本节只加**契约**与**量化门禁**，不重复那边的四问内容。

**契约**

```json
{"audit": {"required": ["checks", "failures"],
           "failure": {"required": ["gate", "what", "searched"],
                       "searched": {"description": "没有 searched 的不许进台账"}}}
}
```

**执行**（四问的实现在 `kp_toolkit/gap_verify.py`；本节只加可量化断言）

```python
def audit(graph, gates) -> dict:
    failures = []
    for g in gates:
        covered, total, missing = g["fn"](graph)
        if covered < total:
            failures.append({"gate": g["id"], "what": missing,
                             "searched": g["searched_evidence"]})
    return {"checks": len(gates), "failures": failures}

# 三条量化断言（原文只说「要留 searched」，这里给出可执行阈值）
assert all(f["searched"] for f in failures),        "无 searched = 未验证 = 不许报缺"
assert all(f["what"] for f in failures),            "报缺必须说清缺什么，不许只报「不通过」"
assert false_rate(failures, graph) < 0.20,          "假缺率 ≥20% 说明判据有问题，先修判据再报数"
```

**门禁 P17 · 审计可信**

```
① 每条失败带 searched 三问证据
② 每条失败说清「缺什么」，不许只报「不通过」
③ 假缺率 < 20%（超了先修判据，不交付）
```

**代价（量化汇总，明细见上一节的六行表）**

```
累计报「缺」1496 → 真缺 345 → 假缺率 77%
六类问题的更正过程见「假缺四问」一节的表格。
```
