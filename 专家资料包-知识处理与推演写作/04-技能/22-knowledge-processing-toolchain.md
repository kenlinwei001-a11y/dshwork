# 技能：knowledge-processing-toolchain

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T11:27:23Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | knowledge-processing-toolchain |
| description | 以工具加 LLM 分层做知识处理：确定性步骤走 kp_toolkit 代码，语义步骤才调 LLM 并按 schema 校验。触发：这一步该用工具还是模型、把流水线分层、要求确定性可复现。不适用：替代具体工序执行（解析、分句、建图等由对应 skill 或 kp 工具完成）。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/knowledge-processing-toolchain |
| 所属插件 | （非插件内置） |
| 文件数 | 5 |
| 体积 | 36.9 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：知识处理专家、推演写作专家
- 全部专家引用（含范围外）：知识处理专家（expert-a54010bbb24e）、推演写作专家（expert-a0a771c8b0da）、标准要素抽取专家（expert-131e1b3979fe）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: knowledge-processing-toolchain
description: "以工具加 LLM 分层做知识处理：确定性步骤走 kp_toolkit 代码，语义步骤才调 LLM 并按 schema 校验。触发：这一步该用工具还是模型、把流水线分层、要求确定性可复现。不适用：替代具体工序执行（解析、分句、建图等由对应 skill 或 kp 工具完成）。"
---

# 知识处理工具链（Tool + LLM）

## 核心原则

**能确定性计算的，绝不交给模型去"猜"；只有真正需要语义理解的，才调用 LLM。**

把知识处理流水线拆成两层：

```
确定性底座（工具层，kp_toolkit，零 LLM，可复现可单测）
  分句 · 分块 · 图谱编译 · 溯源链 · 数字/时间冲突 · schema 校验
        ↓ 输出结构化 JSON
语义层（LLM，结构化调用 + schema + validator + 重试）
  实体/事实/关系/Claim/证据/推理抽取 · 证据充分性判断 · 推演写作
```

## 确定性步骤（用工具，不调 LLM）

| 步骤 | kp_toolkit 函数 | 说明 |
|------|-----------------|------|
| 分句 | `segment_sentences(text, doc_id)` | 稳定 ID，同输入同输出 |
| 分块 | `segment_chunks(text, doc_id)` | 按标题/空行切块 |
| 图谱编译 | `compile_graph(items, project_id, version_id)` | 八类节点装配 |
| 图谱校验 | `validate_graph(graph)` | 悬空引用 / 重复 id |
| 溯源链 | `build_provenance(node_id, graph)` | 反向追到证据 |
| 数字冲突 | `detect_numeric_conflicts(facts)` | 输出「待审」 |
| 时间冲突 | `detect_time_conflicts(facts)` | 输出「待审」 |
| schema 校验 | `validate_schema(nodes, kind)` | 必填字段检查 |

运行方式：`python3 -m kp_toolkit.cli <command>`，或 `import kp_toolkit`。
自测：`python3 -m kp_toolkit.test_kp_toolkit`（全绿才算工具层就绪）。

## 语义步骤（才调 LLM，必须结构化）

只有以下步骤调用 LLM，且必须：
1. 按 `schema/output.json` 契约输出 JSON（不裸奔自由文本）。
2. 输出后立即经 `validators/validator.py` 确定性校验。
3. 校验失败 → 重试（最多 3 次）→ 仍失败则显式标记「待审」。

- 实体抽取（entity-extraction-skill）
- 事实抽取（fact-extraction-skill）
- 关系抽取（relation-extraction-skill）
- Claim 抽取（claim-extraction-skill）
- 证据/推理抽取（evidence-/reasoning-extraction-skill）
- 证据充分性判断（claim-validation-skill）
- 推演写作（graph-deductive-writing-skill）

## 工作流

1. 判定任务与文档类型，确定领域本体。
2. 工具层：解析 → 分句 → 分块 → 建图 → 溯源 → 数值/时间冲突 → schema 校验（全代码）。
3. LLM 层：语义抽取（结构化 + validator + 重试）。
4. 图谱编译与审计：统一图谱 + 冲突待审清单 + 质量审计。
5. 下游交付：检索 / 推演 / 写作，绑定证据与溯源链。

## 铁律

- 确定性步骤绝不用 LLM 复现（否则失去可复现/可审计性）。
- LLM 步骤绝不裸奔自由文本，必须 schema + validator。
- 冲突一律「待审」，不擅自改数字或补口径。
- 缺失事实保持显式未知，不编造。

<!-- kp-patch:v1 -->

## 客观判据清单（判定不消费 LLM 的意见）

`corpus_pipeline/objective_criteria.py` 提供 12 条**确定性**判据（K1–K12）。
判据类型仅允许 8 种：**集合差 / 守恒等式 / 正则计数 / 数值比较 / 哈希一致 / 图算法 / 枚举成员 / 覆盖率比值**。

**14 条判据全表**（与 `objective_criteria.py` 的 `CRITERIA` 列表一一对应）：

| ID | 类型 | 名称 | 算法 | 阈值 | 备注 |
|---|---|---|---|---|---|
| **K1** | 守恒等式 | 解析守恒 | `docx <w:tbl> = md 表块`；`word/media ≥ md 图注` | 差 = 0 | — |
| **K2** | 守恒等式 | 切块守恒 | `Σchunk 去空白字符 = 原稿去空白字符` | 偏差 ≤ 15% | — |
| **K3** | 集合差 | 引用闭环 | `set(原稿《》) − set(evidence.doc) − 豁免 = ∅` | 依据类缺口 = 0 | — |
| **K4** | 集合差 | 数值闭环 | `set(原稿「数字+单位」) − set(节点值) − 量纲等价 = ∅` | 关键单位类缺口 = 0 | — |
| **K5** | 覆盖率比值 | 关系闭环 | `应有 claim 关系 − 已有边 = ∅` | 四类各 100% | — |
| **K6** | 正则计数 | 占位符合规 | 剥离 `{{node:…}}` 后手打数字 = 0；占位符形须匹配 `^\{\{node:N-[0-9a-f]{12}\}\}$` | 违规 = 0 | `draft_only` |
| **K7** | 枚举成员 | 值域合法 | `claim_type`/`status`/`kind`/`relation.type` ∈ 词表 | 越界 = 0 | — |
| **K8** | 图算法 | 图完整性 | 每条 relation 端点可寻址；无孤立节点；依赖无环 | 违规 = 0 | — |
| **K9** | 哈希一致 | 溯源可复现 | `source_original_sha256 = 实际文件哈希` | 一致 | — |
| **K10** | 覆盖率比值 | 装配覆盖 | `\|defined 且非明细节点 ∩ 成稿引用\| / \|…\|` | ≥ 95% | `draft_only` |
| **K11** | 数值比较 | 派生闭合 | `\|规则重算值 − 报告声明值\| ≤ 容差` | 超差项必须登记为待审 | — |
| **K12** | 正则计数 | 论证要件实质存在 | `toulmin.warrant/backing` 非占位（`未写出`/`不代拟`/`待补充`/`无`/`—`/`N/A`） | 占位率须显式登记，不得计为通过 | — |
| **K13** | 集合差 | 事实用逻辑·函数用值 | K13a `事实类字面值 ∩ 资产 = ∅`；K13b `函数类值 ⊆ 资产` | 残留 = 0 且 丢失 = 0 | 复合判据 |
| **K14** | 数值比较 | 依据时效标注 | K14a 生效时间必填（原文无则待核）；K14b 窗口合法；K14c 同月切换单列；K14d 超前核查 | 有而未标/越窗/超前 = 0；待核项单列 | 复合判据 |

**注意编号顺序**：`CRITERIA` 列表里 K13/K14 出现在 K12 之前（代码里是
`K1...K11, K13, K14, K12`），因为 K12 是最后追加的。**读音时按 ID 顺序，不按列表顺序。**

**三条铁律**：

1. **LLM 产出候选，工具判定候选是否合格**；判定**不消费 LLM 的意见**。
2. **无法客观化的项不得冒充 pass** —— 标 `judgment_required`，
   既不进自动门禁也不计为通过，交人工。
   当前明确列入的 3 项：论证是否成立、证据支持等级的语义判断、取舍是否可接受。
3. **探针必须自证**：每个探针须先在源中命中一个已知存在的正样本；
   未过标定则该判据 `invalid`。
   （教训：曾三次因探针故障把「探针坏了」误报成「源里没有」。）

**为什么不能用 NLP 分类器替代**：那只是把「LLM 主观」换成「模型主观」，
仍是不确定判定；写进 pass 通道比没有门禁更糟——它给了一个**虚假的保证**。

**需要的是确定性组件，不是模型**：中文分句器、量纲归一表、别名归并（编辑距离）、
表格解析器。四者均为输入确定、输出确定、可单测，且标准库即可实现。

## 分层判定的四段式（本 skill 是方法论，只有一道工序：分层决策）

**契约**

```json
{
  "split_decision": {
    "required": ["step", "layer", "why"],
    "layer": {"enum": ["tool", "llm"],
              "description": "tool=确定性可复现；llm=需语义理解"},
    "why": {"description": "必须写清判据：为什么这步能确定性 / 为什么必须语义"}
  }
}
```

**执行**

```python
def decide_layer(step) -> dict:
    """四问判定：能算吗 → 能校验吗 → 同输入同输出吗 → 需要理解吗"""
    if is_arithmetic(step):        return {"layer": "tool", "why": "纯算式，可复算"}
    if has_schema(step):           return {"layer": "tool", "why": "有 schema 可校验"}
    if is_deterministic(step):     return {"layer": "tool", "why": "同输入必同输出"}
    if needs_semantics(step):      return {"layer": "llm",  "why": "需理解语义"}
    return {"layer": "llm", "why": "无法确定性判定，交 LLM 但必须 schema 约束"}

# 硬约束：凡是选 tool 的步骤，必须有可运行实现
for s in steps:
    d = decide_layer(s)
    if d["layer"] == "tool":
        assert has_implementation(s), f"{s} 选了 tool 但没有可运行实现"
```

**门禁 L1 · 分层可审计**

```
每个步骤标明 tool 或 llm + 判据；选 tool 的必须有实现；选 llm 的必须有 schema + validator
```

**代价（实测）**

```
写 3 遍自然语言纪律（「假缺四问」「影响面三张表」），假缺率仍 77%
写 1 次 gap_verify.py，立刻生效

有代码的 2 条纪律生效，纯文字的 3 条没生效
→ 结论：能确定性的必须写成代码，自然语言只留「为什么」和「代价」
```

**三条判据（选 tool 还是 llm）**

| 判据 | 选 tool | 选 llm |
|---|---|---|
| 能算出来吗 | 算式/规则可复算 | 需要理解语义 |
| 能校验吗 | 有 schema 可断言 | 无客观正确答案 |
| 同输入同输出吗 | 是 | 否（有随机性） |

**反例（这些曾被误判为 tool）**

```
「判断这句话是不是论断」→ 以为是规则问题，实为语义 → 但建了确定性判据后变为 tool
「判断证据等级」→ 以为要 LLM，实为分类规则 → 可确定性
「判断表格列名」→ 以为要视觉模型，实为读原生 XML → 确定性
```

**一条铁律**

> **先问「能不能确定性判定」，不问「难不难」。**
> 难但确定性的（如表格多级表头合并）→ 写代码；
> 简单但语义的（如判断一句话是建议还是预测）→ 虽然可以写规则，但要穷举判断词表并承认边界。

## 详细方法论（已下沉）

以下四份放 `references/`，按需读，不默认加载：

| 文件 | 讲什么 | 何时读 |
|---|---|---|
| `references/改skill的三问.md` | 判断「改会更好」还是「为改而改」 | 要修改本 skill 时 |
| `references/三条工程纪律.md` | 派生数字不写死 / 重生成幂等 / 门禁编号唯一 | 写生成脚本时 |
| `references/性能与确定性.md` | 性能瓶颈用计时+阈值定位，不用 LLM 猜 | 发现变慢时 |
| `references/案例与映射.md` | 分层案例与工具映射 | 需要具体例子时 |

## 资源导航（分层案例、工具映射、工程教训已下沉 references/）

- `references/案例与映射.md` — 5 节

## 何时使用

- 调用条件：上游产物与 project_id / document_id / version_id 齐备
- 典型请求：这一步该用工具还是模型｜把流水线分层｜要求确定性可复现
- 不要在此调用：替代具体工序执行（解析、分句、建图等由对应 skill 或 kp 工具完成）
## 边界与不适用

- 不做：不确定能否确定性的步骤不得交给 LLM
- 不做：不跳过 validator；失败重试有上限，不无限重试
- 缺输入：先明确工序清单与输入产物
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 10820 | 07283ac950bd2b77 |
| references/三条工程纪律.md | 3136 | c6694b0fbf71e1bc |
| references/性能与确定性.md | 3230 | 05d4bd3deea9e8cb |
| references/改skill的三问.md | 4597 | a7b96747cf9fe686 |
| references/案例与映射.md | 15968 | aa918f784dcfa40b |

## 6. MCP 关联（文本取证）

正文或资源中出现：`kp_toolkit`。对应连接见 `06-MCP/`。

## 7. 副本

逐字节副本：`99-原件/skills/knowledge-processing-toolchain/`（未改写；已用 SHA-256 复算校验）。
