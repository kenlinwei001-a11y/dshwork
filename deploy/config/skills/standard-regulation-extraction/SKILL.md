---
name: standard-regulation-extraction
description: 从「标准 / 法规 / 政策 / 公告」四类规范性文件中确定性抽取条款，产出跨项目复用的公共标准库。当需要把 GB/建标/JGJ 国家标准、条例/办法/规定类法规、通知/意见/大纲类政策、发布公告等外部文件转成可被项目引用的条款库（clause_no + clause_text + 强制性等级 + 溯源），或需要判断某份文件该用哪种抽取模式、抽取率是否达标、多源同标准如何合并时使用。与 knowledge-processing 的区别：本 skill 专管外部规范性文件的条款抽取与公共库治理，knowledge-processing 管项目内稿件的七道工序。
---

# 标准 / 法规 / 政策抽取（规范性文件 → 公共标准库）

## 目的

外部规范性文件（国家标准、行业标准、法规、政策、公告）是所有项目的**设计依据**，
必须抽成**跨项目复用的公共库**，而不是塞进每个项目目录里重抽一遍。

实测教训：某项目把 20 份外部文档放在项目内，900 段只抽出 22 条条款（2.4%），
后续被迫在每个项目里重抽，且同一标准的 5 个来源各建一套重复节点。

## 何时使用

- 收到 GB / GB-T / 建标 / JGJ / DGJ / 发改投资规 / 部委令 等规范性文件
- 需要判断「这份文件该按什么模式抽条款」
- 需要评估抽取率是否达标、多源同标准如何合并
- 要为多个项目建立共享的标准条款库

## 工序（四段式：契约 / 执行 / 门禁 / 代价）

> **为什么不用自然语言写步骤**：实测「条款必须带标准号」写在散文里，
> 69 个条款节点的 `standard` 字段 **0/69 全空**；
> 写成 `validate_clause_library` 断言后，152/152 立刻通过。
> **纪律靠提醒，机制靠退出码。**

---

### 工序 1 · 判型

**契约**

```json
{
  "doc_type": {"enum": ["standard", "regulation", "policy", "notice"],
               "description": "standard=GB/建标/JGJ；regulation=条例办法；policy=通知意见大纲；notice=发布公告"},
  "router": {"required": ["doc_type", "extractor", "basis"],
             "basis": {"description": "判型依据：文号格式 / 正文结构 / 强制性用语"}}
}
```

**执行**

```python
# scripts/extractors.py:detect_kind
def detect_kind(chunks: list[str]) -> str:
    """逐段 match，不要先 join —— 正则含 ^，拼接后只匹配开头一次（实测踩过）"""
    for seg in chunks:
        if re.match(r"^\s*第[一二三四五六七八九十百]+条", seg):   return "regulation"
        if re.match(r"^\s*\d+(\.\d+)*\s+[\u4e00-\u9fa5]", seg): return "standard"
        if re.search(r"(发布公告|住房和城乡建设部公告)", seg):      return "notice"
        if re.search(r"(通知|意见|大纲|规划)", seg):                return "policy"
    return "standard"

assert doc_type in DOC_TYPES, "判型越界"
assert basis, "必须有判型依据，否则无法复核"
```

**门禁 S1 · 判型可复核**

```python
{"stage": "S1", "gate": "判型可复核",
 "check": "doc_type 在四类内；basis 非空（写清依据哪一行）"}
```

**代价（实测）**

```
用 " ".join(chunks) 后 findall → 正则含 ^ → 只匹配开头一次
→ 12 个标准全判成 notice → 抽取器全选错
```

---

### 工序 2 · 选抽取器

**契约**

```json
{
  "extractor": {"enum": ["ex_gb", "ex_intensity", "ex_outline", "ex_appendix", "ex_article", "ex_notice"]},
  "selection": {"required": ["doc_scope", "extractor", "why"],
                "doc_scope": {"description": "文档范围：正文条款 / 参数表 / 大纲目录 / 附录 / 法规条文"}}
}
```

**执行**

```python
def pick_extractor(doc) -> str:
    """按文档范围选，不按标准编号选 —— 同一个 GB 可能正文+附录都要抽"""
    if has_parameter_table(doc):  return "ex_intensity"   # 烈度/限值表
    if has_appendix(doc):         return "ex_appendix"    # 附录条款
    if is_outline(doc):           return "ex_outline"     # 政策大纲
    if is_article_style(doc):     return "ex_article"     # 法规条文
    if is_notice(doc):            return "ex_notice"
    return "ex_gb"

assert why, "必须写清为什么选这个抽取器"
```

**门禁 S2 · 抽取器匹配**

```python
{"stage": "S2", "gate": "抽取器匹配",
 "check": "抽取器与文档范围一致；一个文档允许多抽取器并存"}
```

**代价（实测）**

```
按标准编号硬编码 → GB50016 只抽正文、漏了表5.1.1 与附录
建标191 判成 article（实为 appendix，46 条里混了非附录内容）
```

---

### 工序 3 · 抽取

**契约**

```json
{
  "clause": {
    "required": ["code", "standard", "clause_no", "clause_text", "source_url"],
    "code": {"description": "标准号，如 GB50016-2014"},
    "standard": {"description": "标准全称，如《建筑设计防火规范》"},
    "clause_no": {"description": "条款号，如 5.1.1 / 附录E 表E.5"},
    "clause_text": {"minLength": 4, "description": "条款原文；表格条款可用 table 替代"},
    "effect_level": {"enum": ["A（强制性）", "B（强）", "C（推荐）"]}
  }
}
```

**执行**

```python
def extract(doc, extractor) -> list[Clause]:
    clauses = []
    for seg in doc.segments:
        c = EXTRACTORS[extractor](seg)
        if not c: continue
        c["code"]   = c.get("code")   or infer_code(doc.url)   # 从 URL 反推标准号
        c["standard"] = c.get("standard") or doc.title
        c["clause_text"] = c.get("clause_text") or c.get("text")
        clauses.append(c)
    # 表格条款：table 即原文，不算缺 clause_text
    for c in clauses:
        assert c.get("clause_text") or c.get("table"), f"{c['clause_no']} 无原文"
    return clauses
```

**门禁 S3 · 五项必填**

```python
{"stage": "S3", "gate": "条款五项必填",
 "check": "code / standard / clause_no / clause_text（或 table）/ source_url 齐全；"
          "不合格标 pending_fetch，不编造"}
```

**代价（实测）**

```
69 个条款节点：standard 字段 0/69 全空
42 条文献名被抽取截断（GB5 / DGJ0 / 建标 / 〔2023〕）
→ 从原文恢复 24 条，标 recovery_basis: 从原文恢复（非编造）
```

---

### 工序 4 · 质量评估

**契约**

```json
{
  "quality": {"required": ["coverage", "min_length_ok", "dup_ok"],
              "coverage": {"description": "已抽条数 / 应抽条数，按目录或章节号估算"}}
}
```

**执行**

```python
def judge_quality(clauses, doc) -> dict:
    expected = estimate_clause_count(doc)      # 按目录/章节号推断
    return {
        "coverage": len(clauses) / max(expected, 1),
        "min_length_ok": all(len(c.get("clause_text") or "") >= 4 for c in clauses),
        "dup_ok": len(clauses) == len({c["clause_no"] for c in clauses}),
    }

assert q["coverage"] >= 0.6,   "抽取率低于 60%，换抽取器"
assert q["min_length_ok"],     "有条款短于 4 字，抽取器错位"
assert q["dup_ok"],            "同号重复，需多源合并"
```

**门禁 S4 · 三条硬指标**

```python
{"stage": "S4", "gate": "抽取质量",
 "check": "覆盖率 ≥60%；无过短条款；无同号重复"}
```

**代价（实测）**

```
建标191 抽 46 条，其中混入非附录内容 → 覆盖率虚高，实为抽取器错位
8 个标准报「有重复条款」→ 多源合并后同号重复，需去重
```

---

### 工序 5 · 多源合并

**契约**

```json
{
  "merge": {"required": ["keep", "drop", "merge_basis"],
            "merge_basis": {"description": "同号多源时保留哪一份的依据（更完整/更权威/更晚）"}}
}
```

**执行**

```python
def merge_sources(candidates: list[Clause]) -> list[Clause]:
    """同 clause_no 保留 clause_text 最长的（最完整），但记下候选来源"""
    best = {}
    for c in candidates:
        k = (c["code"], c["clause_no"])
        if k not in best or len(c.get("clause_text") or "") > len(best[k].get("clause_text") or ""):
            best[k] = c
            best[k]["merge_basis"] = "取 clause_text 最长（最完整）"
    return list(best.values())
```

**门禁 S5 · 合并留痕**

```python
{"stage": "S5", "gate": "合并留痕",
 "check": "每条合并结果带 merge_basis；被丢弃的源记入 drop 列表"}
```

**代价（实测）**

```
多源合并后 8 个标准报「有重复条款」→ 去重时没留痕，无法复核保留的是哪份
```

---

### 工序 6 · 打标与溯源

**契约**

```json
{
  "tags": {"required": ["primary_tag", "tags"],
           "tags": {"items": {"required": ["domain", "topic", "code"]}}},
  "trace": {"required": ["source_url", "trace_status"],
            "trace_status": {"enum": ["full", "pending_fetch"]}}
}
```

**执行**

```python
def tag_clause(c) -> dict:
    """两级标签：先判 10 域，再判 42 主题，顺序不可换"""
    domain = pick_domain(c["clause_text"])
    topic  = pick_topic(c["clause_text"], domain)
    return {"primary_tag": f"{domain}.{topic}",
            "tags": [{"domain": domain, "topic": topic, "code": DOMAIN_CODE[domain]}]}

assert c["tags"],         "条款必须有标签，否则无法精准匹配"
assert c["source_url"],   "必须有抓取来源"
assert c["trace_status"] in ("full", "pending_fetch"), "溯源状态越界"
```

**门禁 S6 · 标签与溯源**

```python
{"stage": "S6", "gate": "标签溯源闭环",
 "check": "每条有 primary_tag + tags；source_url 非空；trace_status 在枚举内"}
```

**代价（实测）**

```
无标签 → 42 个主题无法精准匹配，只能用关键词 grep（准确率低）
无 source_url → 抓取失败的标准无法区分「没抓」与「抓了但空」
```

---

### 工序 7 · 入库校验与发布

**契约**

```json
{
  "library": {"required": ["standards", "totals"],
              "standard": {"required": ["code", "name", "version", "clauses", "status"],
                           "status": {"enum": ["draft", "validated", "published"]}}}
}
```

**执行**

```python
# scripts/extractors.py:validate_library（已实现）
def validate_library(all_clauses) -> dict:
    items = []
    for c in all_clauses:
        missing = [k for k in ("code", "standard", "clause") if not c.get(k)]
        if not (c.get("text") or c.get("table")): missing.append("clause_text")
        items.append({"clause": c.get("clause"), "missing": missing})
    return {"total": len(items),
            "ready": sum(1 for x in items if not x["missing"]),
            "items": items}

# scripts/extractors.py:check_relation_targets
def check_relation_targets(rels, nodes) -> dict:
    """bounded_by 必须指向带 code + clause_no 的条款"""
```

**门禁 S7 · 条款溯源闭环**

```python
{"stage": "S7", "gate": "条款溯源闭环",
 "check": "五项必填全齐（152/152）；bounded_by 指向的条款必须有标准号与条款号"}
```

**代价（实测）**

```
入库前不校验 → 69 个条款 standard 全空也能进库 → 下游 bound 上去查不到是哪条标准
不校验关系指向 → bounded_by 指向泛化条款节点（NX-条款-GB50016），架空真实节点
```

## 第四步：公共标准库结构

> **与工序 S3「契约」段的区别**：
> 本节管**库的目录组织**（每个标准一个目录，含 standard.yaml + clauses.yaml + chunks.jsonl），
> S3 管**单条条款的字段必填**（code/standard/clause_no/text/url 五项）。
> 本节答「库怎么摆」，S3 答「每条条款长什么样」。

```
公共标准库/
├── standards.yaml                索引（编号/名称/版本/源数/段数/条款数/抽取器/状态）
├── GB50016-2014/
│   ├── standard.yaml             元数据 + 来源清单（含 URL、抓取状态）
│   ├── chunks.jsonl              合并去重后的原文
│   └── clauses.yaml              条款（clause / text / effect_level / chunk / url）
└── ...

项目/external/
└── references.yaml               只记「本项目引用了哪些标准 + 被几条关系用到」
```

**多源合并规则**：同一标准有多个来源（如 GB50016 有官方页、转载页、转录页 5 个源）时，
按 `条款号` 去重，保留**正文最长**的那条，并把其他源的 URL 并入 `sources`。

## 第五步：强制性与溯源

### 强制性分级（GB 标准通用表述）

```
必须 / 严禁 / 不应 / 不得  → A（强制性）
应                        → B（强）
宜 / 可 / 不宜            → C（推荐）
无上述词                   → D（资料性）
```

### 溯源字段（缺一不可）

```yaml
id: SC-GB50011-2010-003
clause: 附录A-3
clause_text: 烈度 7 度 / 加速度 0.10g / 第一组：上海(黄浦区、卢湾区…)
effect_level: D（资料性）
chunk: c-xxxxx                # 原文切片 ID
source_url: https://...       # 原始 URL
trace_status: located          # located / not_located
```

## 坑（实测）

1. **不要用同一个正则套所有文件**——GB50011 附录A 是表格、304号大纲是中文编号，用 `5.1.1` 模式会抽出 0 条
2. **条款正文常分多段**——首段有编号、续段无编号；必须把续段并入上一条，否则丢内容（实测丢过 469 段）
3. **多源同标准必须去重**——否则同一标准建出重复节点（实测 140 个节点里 37 个重复）
4. **公告类不该硬抽条款**——批准发布公告全文就是一条，强行按条款号抽会得 0 条
5. **抽取率低先怀疑模式**，不要怀疑原文——模式对了覆盖率立刻从 2% 跳到 20%+

## 与其他 skill 的分工

| skill | 管什么 |
|---|---|
| **本 skill** | 外部规范性文件 → 条款库（跨项目公共资产） |
| knowledge-processing | 项目内稿件 → 语料包（七道工序、30 契约文件） |
| graph-deductive-writing-skill | 消费图谱写正文（引 computed_from 复算、bounded_by 判合规） |


## 打标：条款必须有标签，否则无法精准匹配

### 为什么

只有条款正文时，匹配只能靠「章节」或「关键词」猜。实测把
「风荷载体型系数 1.3」挂到了《建筑工程抗震设防分类标准》上——
因为那一章既有风荷载又有地震作用，整章映射必然错。

### 两级标签

```yaml
# taxonomy.yaml
domains:
  结构:
    code: STRU
    topics:
      荷载:         [基本风压, 基本雪压, 活荷载, 地面粗糙度, 体型系数]
      抗震设防分类: [设防类别, 标准设防类, 重点设防类]
      地震参数:     [设防烈度, 地震加速度, 设计地震分组, 特征周期, 阻尼比]
      场地类别:     [建筑场地类别, 覆盖层厚度]
  消防:
    topics:
      耐火等级:     [耐火等级, 耐火极限, 燃烧性能]
      防火分区:     [防火分区, 允许建筑面积]
  给排水:
    topics:
      消防给水:     [消防用水量, 消火栓, 自动喷水, 消防水箱]
      用水量:       [用水定额, 最高日用水量, 未预见系数]
```

### 打标规则（顺序不能换）

1. **标准编号定域**（最可靠）
   ```python
   STD2DOM = {"GB50016": ("消防", None), "GB50974": ("给排水", "消防给水"),
              "GB50011": ("结构", None), "GB50223": ("结构", "抗震设防分类")}
   ```
2. **关键词定 topic**
3. **量纲兜底**（给数值节点用）

### 效果对比

```
打标前：GB50016 挂 30 条（含荷载、气象、喷淋、消防给水）
打标后：GB50016 挂  3 条（耐火等级 2 + 建筑分类 1）
       每个数值最多挂 1 条（唯一归属）
```

### 文档也要标签

```
desc  = 标题本身（《建筑设计防火规范》2014(2018年版)）
tags  = 专业域（消防、建筑）
topics= 该标准覆盖的主题（耐火等级、防火分区、安全疏散）
```

### 检索

```python
tag_query(library_path, domain="结构", topic="地震参数")   → 11 条
tag_query(library_path, code="GB50016")                  → 27 条
tag_query(library_path, q="耐火等级")                     → 15 条
```


## 待抓清单：本 skill 的输入来源

上游用 `detect_citations` 扫出「报告引用了哪些标准、缺哪些」，
按三档分级后交给本 skill 抓取与抽取。

### 清单结构

```yaml
tasks:
  - standard: GB50736
    tier: 应抓            # 必抓 / 应抓 / 暂缓
    type: 国家强制性标准    # 决定去哪抓
    mentions: 2
    sections: ["6.7", "7.1"]
    action: 批量抓取并抽查
    caution: 以标准全文库或官方发布页为准
```

### 按 type 选抓取源

| type | 去哪抓 | 不能用的源 |
|---|---|---|
| 地方标准（DGJ） | **地方住建委官网** | 各类标准转载站 |
| 行业标准（JGJ/CJJ） | 住建部发布页 | 同上 |
| 国家强制性（GB） | 标准全文库 / 官方发布页 | 二手解读文章 |
| 国家推荐性（GB/T） | 同上 | 同上 |
| 建设标准（建标） | 住建部 + 发改委联合公告 | — |
| 政策文件 | 发改委公告 | — |

### 抓完必做三道校验

1. **版本**：报告写的是哪版？抓到的能不能替代？
   `resolve_version()` 判定；旧版只能作历史对照，不能当现行依据
2. **来源**：官方 / 标准库 / 二手
   二手只能当线索，不能进公共库
3. **完整性**：拿到的是完整条款还是 PDF 某页片段？
   片段不能当条款

### 抽取

抓到的原文按 `ex_gb` / `ex_intensity` / `ex_outline` / `ex_appendix` / `ex_article` 五类抽取器处理，
再做质量判据（覆盖率 ≥10%、过短 <5%、重复 =0）。

### 一个提醒

**「暂缓」不等于「不需要」**——只是引用次数少、对当前结论影响小。
清单要留档，下次有需要可直接捡起来。


## 时间标签与版本选择：默认用最新，除非语义要求特定版本

### 三个日期字段（缺一不可）

```yaml
code: GB50034-2013
issue_date: "2013-XX-XX"          # 发布日期
effective_date: "2014-06-01"      # 生效日期 ← 决定「是不是现行」
status: superseded                # current / superseded / abolished / pending_fetch
superseded_by: GB/T50034-2024     # 被谁替代
superseded_date: "2024-XX-XX"     # 何时被替代
date_basis: "已被 GB/T50034-2024 替代"
```

**`effective_date` 是最关键的字段**——它决定「这条条款现在还有效吗」。

### 日期从哪来（不许推测）

| 来源 | 可靠性 | 例子 |
|---|---|---|
| **发布公告原文** | 最高 | 「现批准…自2019年8月1日起实施」→ `effective_date: 2019-08-01` |
| 标准封面/前言 | 高 | 「2015-10-01 实施」 |
| 标准正文条款 | 中 | 少数标准在条文里写施行日期 |
| 第三方网站 | **低，必须回原文核对** | 只能当线索 |

**取不到就写 `unknown`，并在 `date_gaps` 里登记。绝不推测。**

实测：14 个标准里只有 8 个能取到生效日期，其余 6 个的发布公告不在抓取范围内 → 全部标 unknown。

### 版本选择策略（写进 standards.yaml）

```yaml
version_policy:
  principle: 默认使用最新现行版本；仅当语义判断需要特定版本时，才使用指定标准号
  rules:
    - when: 无特别说明
      use: 现行版本（effective_date 最新且 status=current）
    - when: 报告编制时点早于替代日期
      use: 编制时点的现行版本，标注「编制时有效，现已被 X 替代」
    - when: 合同/招标文件指定标准号
      use: 指定标准号，标注「按合同约定」
    - when: 引用历史数据或对标
      use: 产生该数据时的版本，标注「历史数据，口径对应 X 版」
  status_values:
    current: 现行有效
    superseded: 已被替代
    abolished: 已废止
    pending_fetch: 未获取原文
  unknown_policy: 未取到日期一律写 unknown，不得推测
```

### 实测：版本校验救了两次

**案例一：GB50034-2013 已废止**

```
报告 2019 年编制时引用：GB50034-2013  ← 当时现行，引用正确
2026 年复核：页面标题明确标注【已废止】，已被 GB/T50034-2024 替代
处理：status=superseded，superseded_by=GB/T50034-2024
      引用时写「编制时有效，现已被 GB/T50034-2024 替代」
```

**如果没做版本校验，会直接把废止标准的限值当现行依据用。**

**案例二：旧版被合并**

```
GB50019-2003 采暖通风与空气调节设计规范
  → 暖通部分已并入 GB50736-2012
  → 报告若还引 GB50019-2003，应改为 GB50736-2012
```

### 什么时候「故意用旧版」是合法的

| 场景 | 写法 |
|---|---|
| 报告编制时点早于替代日期 | 「按编制时点（2019）现行版本 GB50034-2013」 |
| 合同/招标文件指定 | 「按合同约定采用 GB50034-2013」 |
| 对标历史项目 | 「对标项目采用 GB50034-2013，口径对应」 |
| 新旧对比分析 | 明确列出两版差异，不混用 |

**关键：说明为什么用旧版，而不是悄悄用。**

### 前端展示

标准库里每个标准标签带生效年月：

```
GB50016-2014 · 2019-XX   ← 绿色，现行
GB50034-2013 · 已替代     ← 红色，被 GB/T50034-2024 替代
```

hover 显示完整名称 + 生效日期 + 替代关系。


## 入库校验：条款必须带标准号与原文

### 为什么单独设关

实测一个可研项目的 69 个条款节点，**入库时 `standard`（标准全称）字段 0/69 全部为空**，
7 条缺 `code`（标准号），4 条缺 `clause_no`（条款号）。

后果：下游 `bounded_by` 关系指向条款，但条款不知道自己属于哪份标准 —— 无法判现行有效性。

### 五项必填（缺一不可）

| 字段 | 含义 | 缺失后果 |
|---|---|---|
| `code` | 标准号（如 GB50016-2014） | 无法查版本、无法判是否已被替代 |
| `standard` | 标准全称（如《建筑设计防火规范》） | 人读不可理解，跨项目无法检索 |
| `clause_no` | 条款号（如 5.1.1 / 附录B） | 引用时无法定位 |
| `clause_text` | 条款原文 | 无法核验、无法判合规 |
| `source_url` 或 `doc_id` | 来源定位 | 无法回查 |

**只有 4 项以上齐全，才允许 `trace_status = full`。**

### 入库校验流程

```python
def check_clause_ready(clause):
    missing = [f for f in ("code","standard","clause_no","clause_text")
               if not clause.get(f)]
    if not (clause.get("source_url") or clause.get("doc_id")):
        missing.append("source")
    if missing:
        return {"ready": False, "missing": missing,
                "action": "补齐后方可入库；确实取不到标 pending_fetch，不编造"}
    return {"ready": True, "trace_status": "full"}
```

### 不合格怎么办（三条铁律）

| 情况 | 处理 |
|---|---|
| **有原文，缺标准号** | 从 `source_url` 反推（URL 含 GB50016 → 补 GB50016-2014） |
| **有标准号，缺原文** | 标 `trace_status: pending_fetch`，**不编造 clause_text** |
| **两者都缺** | **不入库**。宁可缺，不可假 |

**实测处理**：

```
69 条中 62 条有 code → 从 URL 反推补 7 条 → 69/69
69 条中 0 条有 standard → 从标准号映射全称 → 69/69
68 条 trace_status=full
1 条 pending_fetch（GB50009-2012 未抓原文，如实标注）
```

### 下游必须能回溯到条款

条款入库后，所有引用它的关系必须指向**带标准号的条款节点**，不是指向标准本身。

```yaml
# 错误：只指向「标准」
bounded_by:
  to: "GB50016-2014"           # 哪一条？
  payload: {clause: 5.1.1}     # 条款号写在关系里，重复且易漂移

# 正确：指向「条款节点」
bounded_by:
  to: "MC-004"                 # 条款节点
  # 该节点自带 code=GB50016-2014, clause_no=5.1.1, clause_text=...
```

**校验**：

```python
for r in bounded_by_relations:
    t = nodes[r["to"]]
    assert t.get("code") and t.get("clause_no"), f"{r['to']} 条款缺标准号/条款号"
```

实测：68 条 `bounded_by` 全部指向合规条款，合规率 68/68。

### 函数也要标依据

从标准里抽的**函数/规则**（如"火灾延续时间 2h"、"用水定额 40 L/生·日"）必须标依据，
纯算术（加减乘除/汇总）不需要。

```yaml
# 有规范依据
computed_from:
  payload:
    rule_id: R-消防一次灭火用水量
    standard_basis:
      code: GB50974-2014
      why: 火灾延续时间取值（2h/1h）依规范
      name: 《消防给水及消火栓系统技术规范》

# 纯算术
computed_from:
  payload:
    rule_id: R-总投资构成
    standard_basis:
      code: null
      why: 纯算术合成（加减乘除/汇总），不涉规范取值
```

实测：71 条 `computed_from` 中 20 条有规范依据、51 条纯算术。

**关键区分**：

> **从标准抽的函数，必须能说出「依据哪条」；说不出的，就不是从标准抽的，是自己的算法。**

### 一条铁律

> **条款没有标准号，就不是条款，是断章取义的引文。**
>
> 入库前五项必填：code / standard / clause_no / clause_text / source。
> 缺任何一项，要么补齐，要么标 pending_fetch，**绝不编造**。


## 标准效力层级：项目建设地决定抓哪一级

### 一句话原则

> **项目在哪建设，就优先抓哪里的地方标准。地方标准通常严于国标，国标只是底线。**

实测踩过的坑：一个上海项目，公共库收了 GB50189-2015（8 条，含夏热冬冷限值），
但**一处 DGJ08-107 都没收**（引用 13 次，最高频）。

这等于**把「底线」当成了「标准」**——上海项目的围护结构、节能指标，
DGJ08-107 的要求通常严于 GB50189，按国标判合规会得出「符合」的错误结论。

### 编号体系与效力

| 前缀 | 层级 | 适用范围 | 与其他标准的关系 |
|---|---|---|---|
| `GB` | 国家强制性 | 全国 | 底线，地方可严于此 |
| `GB/T` | 国家推荐性 | 全国 | 推荐，可被地方引用为强制 |
| `JGJ` / `CJJ` | 行业标准 | 全国该行业 | 底线 |
| **`DGJ` + 地区码** | **地方标准** | **该地区** | **通常严于国标，优先适用** |
| `建标` | 建设标准 | 全国 | 投资/规模控制 |
| 发改文件 | 政策 | 全国 | 程序性要求 |

**地区码示例**：

```
DGJ08   上海      DGJ32   江苏      DGJ01   北京
DGJ13   河北      DGJ03   山西      DGJ14   内蒙古
```

### 抓取优先级（按项目所在地定）

```
① 项目所在地地方标准   ← 第一优先，最严
② 国家强制性标准（GB）  ← 底线
③ 行业标准（JGJ/CJJ）   ← 补充
④ 国家推荐性（GB/T）    ← 参考
⑤ 政策文件（发改）      ← 程序
```

**判定规则**：

```python
def fetch_priority(project_city, std_code):
    loc = REGION_CODE.get(project_city)   # 上海 → 08
    if std_code.startswith("DGJ"):
        return 1 if std_code[3:5] == loc else 0   # 本地 1，外地 0（不抓）
    if std_code.startswith("GB/") : return 4
    if std_code.startswith("GB"):   return 2
    if std_code.startswith(("JGJ","CJJ")): return 3
    return 5
```

### 地方标准的抓取难点（必须知道）

| 难点 | 表现 | 应对 |
|---|---|---|
| **只有官网权威** | 转载站版本可能与官方有差异 | **只认地方住建委官网**，转载站不进公共库 |
| **PDF 字体编码损坏** | 下载成功但提取为乱码 | 找 HTML 版 / 文字层完好的 PDF / 索取原文本 |
| **无 OCR 工具时** | 图片型 PDF 无法转文字 | **标 `pending_fetch`，不编造** |
| **版本更新快** | 同一标准 3~5 年换版 | 必须记 `effective_date` + `superseded_by` |

实测：DGJ08-107-2015 从上海市住建委官网下载成功（5.1 MB / 108 页），
但 PyMuPDF 提取为乱码 —— **标 `pending_fetch`，13 处引用只能写「依据该标准，限值待核」**。

### 同一份报告引同一标准的两个版本

实测：一个上海项目的抗震设计规程

```
§6.3    引 DGJ08-9-2013   ← 新版
§9.2.1  引 DGJ08-9-2003   ← 旧版（同一份报告）
```

节能标准同样：

```
§6.4    引 DGJ08-107-2015
§7.1    引 DGJ08-107-2012
§7.3.1  引 DGJ08-107-2012
```

**这不是「引用旧版」，是「同一份报告内部判据不一致」** —— 必须登记为 `report_fix`。

### 入库后的判据优先级

```yaml
约束判定顺序：
  ① 有地方标准条款 → 按地方标准判
  ② 无地方标准 → 按国标判，但注明「未核地方标准，按国标底线」
  ③ 都无 → 待核，不得判「符合」
```

**绝对不能**：只有国标就判「符合规范」—— 地方可能更严，国标合格不等于项目合格。

### 一条铁律

> **国标是底线，地标是标准。**
>
> 上海项目按 GB50189 判「符合」，可能实际不满足 DGJ08-107。
> **抓不到地标，就只能说「待核」，不能说「符合」。**
