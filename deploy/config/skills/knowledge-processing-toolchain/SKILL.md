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

### EN6 草稿的所有字段必须在「请求发布」之前改完

**实测**：改专家草稿时顺序错了 ——

```
1. 改 agent_document（能力 7/8/9 + 判断框架）   ✅ 成功
2. request_publish（发布前校验）                  → needs-confirmation
3. 再改 description / examples                    ❌ 失败
   "专家已被修改，请刷新后重试"
   刷新后 draft_revision 没变，仍无法更新
```

**根因**：`request_publish` 返回 `needs-confirmation` 后，**草稿被锁定**，
防止「用户正在确认的版本」被偷偷改动。这是正确设计，不是 bug。

**代价**：`description`（摘要）和 `examples`（快捷入口）停在旧版，
而正文里的核心能力已经更新 —— 版本内部不一致。

**正确顺序**：

```
① 改所有字段（正文 / 摘要 / 标签 / 示例 / 技能依赖）
② validate（可发布性校验，无副作用）
③ request_publish（进入待确认，锁定）
④ 用户确认 → 发布
```

**判据**：

```
凡是「进入待确认/锁定态」的操作，必须在所有编辑动作之后
发布、提审、签名、冻结 —— 都是这类操作
```

**同类操作**（都遵守这条）：

| 操作 | 锁定后不能做什么 |
|---|---|
| `request_publish` | 改草稿任何字段 |
| `git tag` 后 push | 改 tag 指向的 commit（需删 tag 重建）|
| 语料包 `manifest.status: published` | 改包内文件（需新修订）|
| 合同签署 | 改条款（需补充协议）|

### EN5 目录整理前先查引用数（`quality/` 移动 42 个文件的教训）

**实测**：`quality/` 有 69 个文件，平铺难找。按 `graph/gates/review/archive` 分子目录，
移动 42 个文件后：

```
门禁    24/24 → 23/24
一致性  check_consistency.py 报 FileNotFoundError: quality/gaps.yaml
```

**因为 20+ 处代码硬编码了 `quality/xxx.yaml` 路径。**

**回滚后恢复 24/24。**

**判据**：

```
移动文件前，先 grep 该文件名在代码里的出现次数。
> 3 次 → 不移动，改用 README 索引按主题查找。
```

**正确做法**：

```markdown
# quality/ 目录索引
> 不分子目录 —— 曾试过分，破坏 20+ 处引用，已回滚。用本索引按主题查找。

## 冲突
- conflicts.yaml
- conflict_classification.yaml

## 缺口
- gaps.yaml
- clause_gaps.yaml
...
```

**教训**：目录整齐是审美需求，引用正确是功能需求。**功能优先。**

### EN3 枚举必须单一真理源（`kind` 20 处硬编码的教训）

**实测**：`kind` 枚举散在 4 个文件、20 处字面量。

```python
build/extract_unified.py      13 处
build/add_span_marks.py        6 处
build/build_orphan_ledger.py   1 处
```

**加一个新 `kind`（如 `interval` 区间值）要改 4 个文件、20 处，改漏一处就静默失效。**

**对照做对的**（关系类型）：

```
reuse/relation_types.yaml   唯一权威
  → 前端 REL_SCHEMA    由 sync_rel_schema.py 单向生成
  → 后端 gate_checks   从 yaml 读
```

**修法**：

```
reuse/node_kinds.yaml
  kinds:        13 类定义（含 requires / evidence_default / example）
  form_to_kind: 形态→kind 映射
  groups:       实体/引用/事实/论断/证据/其他

代码只读不写；check_consistency 第 ⑩ 项校验「节点 kind 都在定义内」。
```

**判据一**：任何枚举（kind / type / status / severity / 形态）都不许在代码里写字面量。

### 判据二：新增编号前必须先 grep 已有编号

**这是我自己违反 E3 的实例** —— 一边写「枚举不许两处定义」，一边造了第二套 K 编号。

**实测事故**：

```
代码 corpus_pipeline/objective_criteria.py 里已有 K1–K14
我在 toolchain 里新增「K13 零产出率」「K14 YAML 缓存」
→ 撞号
```

| 编号 | 代码里的定义 | 我写的 |
|---|---|---|
| K13 | 事实用逻辑·函数用值 | ❌ 零产出率 |
| K14 | 依据时效标注 | ❌ YAML 缓存 |

**后果**：读者看到「K13」不知道指哪个；文档与代码不一致。

**修法**：我加的改为 E 系列（E1–E6），与代码的 K 系列分开。

```
K1–K14   可执行判据（objective_criteria.py 实现，可跑）
E1–E6    工程教训（不是判据，是「不要这样写代码」的经验）
```

**强制动作**（新增任何编号前）：

```bash
# ① 查代码里已有的编号
grep -oE "K[0-9]+" corpus_pipeline/objective_criteria.py | sort -u -V

# ② 查 skill 里已有的编号
grep -oE "^### [A-Z][0-9]+" ~/.agents/skills/*/SKILL.md | sort -u

# ③ 查前端/台账里的编号前缀
python build/audit_numbering.py   # 若没有，手工 grep
```

**编号前缀分配表**（全局唯一，不可重复占用）：

| 前缀 | 归属 | 来源 |
|---|---|---|
| `S` | 主流程八工序 | knowledge-processing |
| `S1b` | 表格解析（工序 1 的补充） | knowledge-processing |
| `R` | 标准抽取七工序 | standard-regulation-extraction |
| `P` | 单 skill 校验 | 各抽取/校验 skill |
| `F` | 可研编制 | feasibility-report-edu-research |
| `G` | 推演写作 | graph-deductive-writing |
| `L` | 方法论分层 | knowledge-processing-toolchain |
| `K` | **可执行判据** | `objective_criteria.py`（代码权威） |
| `E` | **工程教训** | knowledge-processing-toolchain（本文档） |
| `CF-` | 冲突台账 | quality/conflicts.yaml |
| `GAP-` | 缺口台账 | quality/gaps.yaml |

**新前缀要登记到这张表**，否则第三次撞号只是时间问题。

**同类踩过的坑**：

```
· 门禁编号：knowledge-processing 与 standard-regulation 各有一套 S1–S7（已把后者改为 R1–R7）
· 冲突 id：16 条旧冲突没有 id，无法追踪（已补确定性 id）
· 关系 id：只对 from|type|to 做哈希，4 个不同 dep 撞同一个 id（已加 dep_name）
```

**一句话**：

> **枚举要单点定义，编号要先查后用。两件事都是「同一事实只许一处」。**

### EN4 脚本必须分区，否则无法交接

**实测**：`build/` 下积累 **234 个脚本**，其中：

```
production        18   ← 可复用，进 CI
project-specific  36   ← 只对当前项目有效（fix_*/rebuild_*/link_*）
archive          180   ← 一次性（_patch_*/_gen_*/final_*）
```

**交接时新人的第一个问题**：「这 234 个里哪些能用？」**没有分区，他无法回答。**

**修法**：生成 `CODE_MAP.md`，三区列出。**不移动文件**（移动会破坏现有绝对路径），只做清单。

**判据**：新同事能在 5 分钟内指出「哪个脚本是可复用工具、哪个只对当前项目有效」。

### EN2 大 YAML 必须缓存为 JSON（实测 600 倍差距）

**实测数字**（同一个 1.9 MB / 2,400 节点的 `nodes.yaml`）：

```
yaml.safe_load      624 s     ← PyYAML 纯 Python 解析
yaml.CSafeLoader    604 s     ← libyaml C 实现，反而没快（该结构上无优势）
json.loads          0.04 s    ← 快 15,000 倍
```

**为什么 nodes.yaml 特别慢，relations.yaml 只要 5.7 s**：

```
nodes: 2,400 条 × 每条一个 200 字 anchor.quote（长字符串 + 特殊字符）
relations: 2,155 条 × 每条约 5 个短字段
```

**PyYAML 的解析成本与「字符串长度 × 转义字符数」正相关，不与条目数正相关。**

**修法**：

```python
# 首次：生成 .cache.json
yaml.safe_load(p.read_text()) → json.dumps(..., separators=(",", ":"))

# 之后：优先读缓存（比对 mtime）
cache = p.with_suffix(".cache.json")
if cache.exists() and cache.stat().st_mtime >= p.stat().st_mtime:
    return json.loads(cache.read_text())
```

**效果**：24 条门禁从 **11 分钟 → 1.07 秒**。

**注意**：这条不只影响门禁 —— 任何每次启动都要读大 YAML 的脚本
（`build_seed.py`、`check_consistency.py`、`link_strict.py`）都该用缓存。

## 工程教训（E 系列）

> **为什么用 EN 不用 E**：证据分级已占用 `E0~E6`（见 evidence_model.yaml），
> 工程教训若用 `E1` 会与「证据等级 E1（客户给定）」撞号。已改 `EN`（Engineering Note）。
>
> **EN 与 K 的区别**：
> **K1–K14** 是 `corpus_pipeline/objective_criteria.py` 里的**可执行判据**（代码实现，可跑）。
> **E1–E6** 是本轮踩出来的**工程教训**（不是判据，是「不要这样写代码」的经验）。
>
> 曾把教训编号写成 K13/K14，与代码里的 K13（事实用逻辑）/K14（依据时效）**撞号** —— 已改为 E 系列。

### EN1 零产出率：发现「规则漏了哪类」的客观判据

枚举式规则永远不全。**不要靠穷举「可能有哪些情况」，而要找「本该有输出却零输出」的信号。**

| 工序 | 零产出信号 | 阈值 |
|---|---|---|
| 数值识别 | 句子含数字，但 `recognize()` 返回空 | <30% |
| 关系抽取 | 实体有同名值节点，但无边 | 逐条列出 |
| 条款抽取 | 条款号连续，但中间缺号 | 0 |
| 证据绑定 | 论断有前提，但无 `supports` | 0 |
| 表格解析 | 数值格存在，但无 `column_paths` | 0 |

```python
digits = [s for s in sentences if HAS_DIGIT(s)]
zero = [s for s in digits if not recognize(s)]
assert len(zero) / len(digits) < 0.30, f"零产出率 {len(zero)/len(digits):.0%}"
```

**为什么这条必须客观化**：本项目 8 类数值形态（单位变体 / 允差 / 等级 / 材料 /
规格 / 标准 / 表格行 / 计数）**全部是逐案发现后补的** ——
靠「想一想还漏了什么」永远想不全，靠「有数字却零产出」这个信号才找得到。

**注意区分**：零产出率高不一定是漏抽。目录、序号、纯年份本身就不该产出实体，
要先分类（目录/序号/时间点/真漏网）再判断。


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


## 三条工程纪律（V3.0 实测踩出来的）

### 纪律一：派生数字不许写死

**实测**：`console.config.js` 里 12 处数字是某次人工填的，数据变了没同步：

```
「314 条关系全部做了证据判定」→ 实际 1058
「212 条 · 关系自带 quote」    → 实际 956
「可溯源率 98.4%」             → 实际 97.0%
「122 个章节」                 → 实际 119
「42 条悬空引用」              → 实际 0
「117 个 META 节点」           → 实际 298
```

**这些错都没人发现**，因为页面上看起来一切正常。

**判据**：

```
凡是能从 yaml/json 算出来的数字，不许出现在展示层代码里。
  展示层只放「引用」，放「值」就会过期。
```

**机制**：

```python
# ① 生成：从源头重算
build/regen_config_numbers.py

# ② 检查：展示层的数字 vs 源头
check_consistency.py 第 ⑧ 项「派生数字与源头一致」

# ③ 验证：注入假数字确认检查有效
把 1058 改成 314 → 检查必须报错
```

### 纪律二：重生成脚本必须幂等

**实测**：`regen_config_numbers.py` 第一版用「旧文案 → 新文案」替换：

```python
s.replace("314 条关系", "1058 条关系")
s.replace("可溯源率 98.4%", "可溯源率 97.0%")
```

**问题**：跑完一次，旧文案不存在了，第二次跑「0 处替换」，看起来像成功，实际什么都没做。

**改法**：用正则捕获当前值 + 替换成真值：

```python
def repl(m):
    cur = m.group(1)
    if abs(float(cur) - want) < 0.05:
        return m.group(0)          # 已正确，不动
    return m.group(0).replace(cur, str(want), 1)

s = re.sub(r"(\d+) 条关系全部做了证据判定", repl, s)
```

**现在幂等**：第一次更新 6 处，第二次更新 0 处。

**判据**：

```
重生成脚本必须满足 f(f(x)) == f(x)。
验证方法：连跑两次，第二次输出必须是「0 处变更」。
```

### 纪律三：门禁编号必须全局唯一

**实测**：`knowledge-processing` 和 `standard-regulation-extraction` 各有一套 `S1-S7`：

```
knowledge-processing:        S1归一化 S2骨架 S3切块 ... S7脱敏
standard-regulation:         S1判型 S2抽取器 S3五项必填 ... S7溯源
```

**扫描门禁时 15 条 implemented 里有两套 S1-S7** —— 无法区分是哪个 skill 的。

**改法**：按 skill 加前缀

| 组 | 前缀 | 来源 |
|---|---|---|
| 主流程八工序 | `S` | knowledge-processing |
| 标准抽取 | `R` | standard-regulation |
| 单 skill 校验 | `P` | 各抽取/校验 skill |
| 可研编制 | `F` | feasibility-report-edu-research |
| 推演写作 | `G` | graph-deductive-writing |
| 方法论 | `L` | knowledge-processing-toolchain |

**判据**：

```
门禁编号 = 单字母前缀 + 数字（可带 b）
同一前缀只能属于一个 skill 家族。
```

**机制**：`build/wire_gates.py` 扫所有 skill 的门禁，冲突时报警。

### 一条铁律

> **能算的不写死，重跑的要幂等，编号的要唯一。**
>
> 这三条不是「最佳实践」，是「不这么做就一定会出错」。
