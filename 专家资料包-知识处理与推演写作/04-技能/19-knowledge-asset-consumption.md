# 技能：knowledge-asset-consumption

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T11:27:23Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | knowledge-asset-consumption |
| description | 消费「知识资产包」（形包/语料包）的通用协议。当拿到一个打包好的知识资产（含骨架、规则、模板、门禁、索引）需要读懂它、按引用链取数、避免取错或用错时使用。提供三层索引读法、10 类引用的取数方式、形/值边界判定、悬空引用校验、8 类已知缺陷避坑。适用于建图、审计、写作、领域实例化等任何需要「借形」的场景——即需要复用历史资产的结构与规则、但绝不继承其数值。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/knowledge-asset-consumption |
| 所属插件 | （非插件内置） |
| 文件数 | 4 |
| 体积 | 14.7 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：**未被范围内专家配备**
- 全部专家引用（含范围外）：无

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: knowledge-asset-consumption
description: 消费「知识资产包」（形包/语料包）的通用协议。当拿到一个打包好的知识资产（含骨架、规则、模板、门禁、索引）需要读懂它、按引用链取数、避免取错或用错时使用。提供三层索引读法、10 类引用的取数方式、形/值边界判定、悬空引用校验、8 类已知缺陷避坑。适用于建图、审计、写作、领域实例化等任何需要「借形」的场景——即需要复用历史资产的结构与规则、但绝不继承其数值。
---

# 知识资产消费协议（Knowledge Asset Consumption）

## 何时使用

**任何「拿到一个资产包，要读懂它、按需取、别用错」的场景**：

- 建图：拿历史形包借结构，建新项目图
- 写作：拿形包取骨架/规则/写作提示词
- 审计：拿形包对照门禁与缺陷清单
- 领域实例化：拿形包套用某类报告的法定章节

**不适用**：从零处理原始文档（用 `knowledge-processing`）；已编译图谱的推演写作（用 `graph-deductive-writing-skill`）。

## 核心主张

> **资产包的价值在「形」，不在「值」。**
> 读包的第一要务是分清哪些是形、哪些是值，然后**只取形、值从客户材料来**。

## 第一步：读索引，不要逐个读文件

**32 个文件的包，逐个读会淹死。先读索引。**

| 索引 | 回答什么 | 给谁 |
|---|---|---|
| **`FILE-INDEX.yaml`** | 每个文件有什么（主键/关键字段）、谁引用谁、按什么 key 取 | **agent** |
| `INDEX.yaml` | 有哪几层、查什么去哪 | agent |
| `形包说明.md` / `README.md` | 这个包解决什么问题、怎么用 | 人 |

**读 FILE-INDEX 的三个字段**：

```yaml
files.
  "<相对路径>":
    what:         这个文件是什么
    primary_key:  按什么查（rule_id / fact / code / gate_id / domain）
    key_fields:   里面有哪些关键字段、什么含义
    referenced_by: 谁引用它
reference_graph[]: 10 条引用的 from→to、类型、取数方式
```

## 第二步：按任务取最小集

**不要全读。按你要做的事取。**

| 要做的事 | 取哪个文件 |
|---|---|
| 写某节 | `templates/section-writing-guide-2023.yaml` 的该节 |
| 某条规则怎么算 | `functions/derivation_templates.yaml` 的 `rules.<rule_id>` |
| 规则的依赖 | 同上 `rules[].deps_required` |
| 某事实谁负责给 | `ontology/fact_source_map.yaml` 的 `source_type` |
| 某事实是输入还是算出来的 | `ontology/input_vs_derived.yaml` 的 `role` |
| 规则依据哪个标准 | `lineage/standard-registry.yaml` 的 `rule_to_standard` |
| 有哪些坑 | `ontology/known-defects.yaml` |
| 发布前要过什么关 | `gates/quality_gates.yaml` |

## 第三步：沿引用链取数，遵守三铁律

### 铁律① 只引用 ID / 名称，不复制内容

```
✗ 在写作指引里存 expr        → 改公式时不跟，两份定义漂移
✓ 只存 rule_id，按 id 去定义文件取
```

**判据**：如果一个字段的内容**能在别处找到**，它应该存引用而不是内容。

### 铁律② 每条引用必须写明取数方式

```yaml
#6 from: fact_source_map.facts[].cross_check_rules[]
   to:   derivation_templates.rules.<rule_id>
   how:  "中间量（CUSTOMER_PRIMARY）必须用这些规则复算校验"
   #   ↑ 不写这个，下游不知道该拿它干什么
```

### 铁律③ 引用目标必须存在（悬空 = 0）

**每次读包先校验**：

```python
# 悬空引用检查
for r in index["reference_graph"]:
    if r["to"]["file"] not in ("(无)", "(全部文件)"):
        assert r["to"]["file"] in index["files"], f"悬空: {r['no']}"

# 主键可查性检查
tpl_ids = set(derivation_templates["rules"])
for sec in writing_guide["sections"].values():
    for rid in sec.get("rules_required", []):
        assert rid in tpl_ids, f"悬空 rule_id: {rid}"
```

**实例**：某次建索引时抓出 **8 个悬空 rule_id** —— 2 个是名称不同（`R-总建筑面积` 实为 `R-建筑面积构成`），6 个是源包完全没有的规则名。前者做别名映射，后者从 `rules_required` 剔除并记入 `_unresolved_rules`。

## 形 / 值边界：五类标签

**资产的每个事实位都要能回答「这是形还是值」**。

| 标签 | 含义 | 处置 |
|---|---|---|
| **HARD_INPUT** | 客户必给，无可替代 | 缺 → **问客户**，不得用行业惯例/同类项目值代替 |
| **SOFT_INPUT** | 客户可给，也可由分项加总 | 客户给了也**必须复算校验**；不一致登记待审 |
| **RETRIEVABLE** | 可从标准/web 检索 | 缺 → 自己去查，按获取流程登记 `source_url` |
| **DERIVED** | 只能由规则算出 | **不得问客户要**；缺输入则阻塞，输出 UNDEFINED |
| **JUDGMENT** | 需专业判断 | 必须绑证据才能下结论 |

**二维必须一起看**：

```
source_type（谁给）  ×  role（输入 / 中间量 / 推演结果）
```

只看来源会漏「客户给的也得复算」，只看角色会漏「这个值能不能搜」。

**新项目的标签怎么来**：源包的标签表只覆盖源项目的 116 个事实位，新项目要重算：

```python
from corpus_pipeline.label_enrichment import enrich
enrich("<项目目录>")   # 结构性判据，零 LLM
```

## 8 类已知缺陷必须避开

| ID | 缺陷 | 状态 |
|---|---|---|
| DF1 | 公式缺修正系数（结果偏大数倍）| fixed |
| DF2 | 引用字段是拼接串而非 ID | flagged |
| DF3 | 字段填错位置（标准号填进条款号）| flagged |
| DF4 | 同一事实两套节点（正文+表格）| flagged |
| DF5 | 规则缺 label | excluded |
| DF6 | 客户分项与加总不一致 | flagged（登记待审）|
| DF7 | 汇总量两口径 | flagged（登记待审）|
| **DF9** | **数字解析误伤**（`0.8`→`8`）| fixed |

**DF9 最危险**：不报错、不告警，只有回放冲突才暴露，且暴露时像「客户口径问题」。

**自检三条**（每批抽检）：

```
① 量级合理性：系数应落在有限区间（如 0.1~2.0），抽出 >10 即可疑
② 回放：provided ≠ recomputed 时登记待审
③ 专项：形如 0.x / 1.x 的单元格逐条核对是否丢点
```

**注意**：不要把它做成「系数 >10 报警」的门禁 —— 百分数、千分数会误报，最后只能靠放宽阈值消除告警。

## 消费后的自检清单

读完包、取完数，过一遍：

```
□ 我取到的每个值，能说出它来自哪个文件的哪个字段吗？
□ 有没有哪个值是从资产包抄来的（而不是客户材料）？→ 有就是污染
□ 引用链上有没有悬空（to.file / rule_id / standard code）？
□ 缺值项是否已分类（HARD_INPUT / RETRIEVABLE / DERIVED / JUDGMENT）？
□ 待审冲突是否登记且未被裁决？
□ 我用的规则是否在 known-defects 里有对应的坑要避开？
```

## 详细协议（已下沉）

| 文件 | 讲什么 | 何时读 |
|---|---|---|
| `references/标准引用链.md` | 三层库（L1标准/L2函数/L3因果）+ 四类引用 | 要引用标准或查限值时 |
| `references/分片检索.md` | 三种分片键 + 倒排 + 依赖闭包（不依赖章节） | 读包要按需取数时 |
| `references/口径冲突判定.md` | caliber_check 三级置信度与正文写法 | 遇到两个数不等时 |

## 与既有 skill 的分工

| skill | 管什么 |
|---|---|
| **本 skill** | **读包协议**：索引读法、引用取数、形/值边界、缺陷避坑 |
| `knowledge-processing` | 从原始文档建完整语料包（七道工序）|
| `graph-deductive-writing-skill` | 消费已编译图谱推演写报告 |
| `standard-regulation-extraction` | 建公共标准库（条款级）|

**本 skill 是「横切关注点」**——建图、审计、写作都要用，但不属于其中任何一个。

## 边界与禁忌

- **不生产资产**：本 skill 只消费，不建包（建包用 `knowledge-processing`）。
- **不推断业务结论**：读到什么是什么，不替客户判断。
- **不忽略缺陷清单**：跳过 `known-defects.yaml` 直接使用，等于重复踩坑。
- **不跨包混用数值**：两个包的值永远不可混算，即使字段名相同。
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 8271 | 2b4cbfc6a38dd85d |
| references/分片检索.md | 2918 | 6ba28d125062dec6 |
| references/口径冲突判定.md | 2168 | a3db3994f0853bb3 |
| references/标准引用链.md | 1719 | 5f6535158bd3b3c9 |

## 6. MCP 关联（文本取证）

正文或资源中出现：`kp_toolkit`。对应连接见 `06-MCP/`。

## 7. 副本

逐字节副本：`99-原件/skills/knowledge-asset-consumption/`（未改写；已用 SHA-256 复算校验）。
