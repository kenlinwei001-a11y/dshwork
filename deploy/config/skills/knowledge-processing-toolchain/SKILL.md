---
name: knowledge-processing-toolchain
description: 以「工具 + LLM」分层模式做知识处理。确定性步骤（分句、分块、图谱编译、溯源、数字/时间冲突、schema 校验）调用 kp_toolkit 代码执行（零 LLM、可复现）；语义步骤（实体/事实/关系/Claim/证据/推理抽取、证据判断、推演写作）才调用 LLM，且必须按 schema 输出 JSON 并经 validator 校验、失败重试。当用户要求把文档/语料处理为结构化知识图谱、或要求「确定性走工具、语义走 LLM」时使用。
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

## 生产工具映射（从 kp_toolkit 升级到第三方库时）

- 分句/分块：spaCy / jieba / semantic-text-splitter
- 文档解析：docling / unstructured / PyMuPDF / python-docx / openpyxl
- 中文 NER：HanLP / LTP
- 图谱存储：rdflib / NetworkX / Neo4j / GraphRAG
- 向量检索：Qdrant / pgvector / Milvus
- 实体消解：dedupe / recordlinkage / sentence-transformers + faiss

## 铁律

- 确定性步骤绝不用 LLM 复现（否则失去可复现/可审计性）。
- LLM 步骤绝不裸奔自由文本，必须 schema + validator。
- 冲突一律「待审」，不擅自改数字或补口径。
- 缺失事实保持显式未知，不编造。

<!-- kp-patch:v1 -->
## 客观判据清单（判定不消费 LLM 的意见）

`corpus_pipeline/objective_criteria.py` 提供 12 条**确定性**判据（K1–K12）。
判据类型仅允许 8 种：**集合差 / 守恒等式 / 正则计数 / 数值比较 / 哈希一致 / 图算法 / 枚举成员 / 覆盖率比值**。

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


## 改 skill 的三问（判断「改会更好」还是「为改而改」）

### 背景（实测）

一次改造给 23 个 skill 加了四段式结构，行数从 5,200 增到 6,800。
事后审查发现 **6 处是子集重复**（把原文讲得更细的内容重写了一遍）。
删掉后行数没少多少，但**同一个问题只在一处有答案了**。

### 三问（改前问两个，改后问一个）

#### 改前第一问：同一个问题，现在在几个地方有答案？

```
≥2 处 → 要么合并，要么一处定义、其余引用
=1 处 → 这段是新增的，继续第二问
```

**实测案例**：

```
「切块闭环」判据 = Σchunk 去空白 ≈ 原稿（±15%）
  → knowledge-processing S3 写了一遍
  → semantic-chunking P3 也写了一遍（一字不差）
修法：判据定义在 semantic-chunking，主流程只引用
```

#### 改前第二问：要加的内容，原文是「没讲」还是「讲了但没写成断言」？

| 情况 | 该怎么改 | 例子 |
|---|---|---|
| **原文没讲** | 直接新增 | `falsifiable_by` 必须非空（原文没有） |
| **原文讲了、但散文形式** | **加断言，不重写散文** | 原文有「四问」，我加 `assert all(f["searched"])` |
| **原文讲得比我要写的更细** | **只引用，不重复** | entity-extraction 的 UNITS 清单有 30 项，我写 5 项就是退步 |

**第三行是最容易犯的错** —— 以为「我加的是结构，不算重复」，实际是用简版替换了详版。

#### 改后第三问：删掉这段，读者会不会少知道什么？

```
会少 → 保留（它承载了独有信息）
不会 → 删掉，或改成一句引用
```

**实测**：

```
❌ 删掉 entity-extraction 的 extract_numeric() 重写 → 不会少知道（原文有 UNITS 清单 + 排除表）
✅ 保留 infer_subject_fixed(window=40)          → 会少知道（原文只说「取前 window」，没说 40）
```

### 三种改动的分类（只有前两种值得做）

| 类型 | 定义 | 本轮次数 | 判断 |
|---|---|---|---|
| **减** | 删重复 / 改成引用 | **6** | ✅ 值得 |
| **消歧** | 名字像但维度不同，加边界说明 | **2** | ✅ 值得 |
| **增** | 原文真没有的断言/门禁 | 16 | ✅ 值得 |
| **形式主义** | 只换写法、只对齐格式、只增加字数 | **0** | ❌ 应避免 |

### 一个例外：共享底线允许重复

**17 个 skill 都有同样 6 条铁律**（不编造 / 绑 project_id / 保留来源链 / 冲突不裁决 / 不跨项目复制 / 用 golden 测试）。

**这不是重复建设**，理由：

| 特征 | 重复建设 | 共享底线 |
|---|---|---|
| 性质 | 具体判据（会各自演化） | 不变的红线（永不变） |
| 改动频率 | 高 | 零 |
| 漏写代价 | 两处不一致 | 某个 skill 失守 |

**判断**：会演化的判据必须单点定义；永不改的红线可以各自声明（防止某个 skill 漏写）。

**但如果红线本身要改，必须全 17 处一起改** —— 这点要记住。

### 两类重复的检测方法

#### ① 文本重复（好抓）

```bash
grep -h "^\*\*门禁" */SKILL.md | sed 's/\*\*//g' | awk -F'·' '{print $2}' | sort | uniq -c | sort -rn
# 输出里 count > 1 的就是重名门禁
```

**本轮抓到**：`切块闭环` × 2、`派生闭环` × 2。

#### ② 语义重复（难抓，必须人读）

```python
# 自动检测只能辅助：比对「新增段的关键句」是否在原有内容里出现过
for k in 新增段的断言句:
    if k in 原有内容: 标记重复
```

**本轮自动检测报「无重复」的 2 处，人读后发现是语义重复**：

```
entity-extraction   新增 extract_numeric() vs 原有「识别模式 + 排除表」
extraction-quality  新增 verify_gap()      vs 原有「假缺四问」
```

**所以：自动检测能抓重名和逐字重复，语义重复必须人读一遍。**

### 一个必须承认的诱惑

**写四段式时，最容易把「散文版」改写成「代码版」就交差。**

```
原文：必须排除章节号、条款号、页码、年份、序号
改写：if is_time_point(v): continue        ← 只覆盖了「年份」，其余四项丢了
```

**这是退步，不是进步。**

**正确做法**：原文的清单原样保留，代码只补原文没说的那一条（如 `window=40`）。

### 一条铁律

> **改 skill 的目标不是「结构更整齐」，是「同一个问题只在一处有答案，且那一处比原来更可执行」。**
>
> 整齐但不精确 = 退步。
> 结构不齐但每题一处 = 可接受。
