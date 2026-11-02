# 技能：standard-regulation-extraction

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:44:08Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | standard-regulation-extraction |
| description | 从「标准/法规/政策/公告」四类规范性文件确定性抽取条款，产出跨项目复用的公共标准库（clause_no+clause_text+强制性等级+溯源）。触发：把 GB/建标/JGJ 国家标准、条例/办法/规定类法规、通知/意见/大纲类政策、发布公告转成条款库，或判定某文件该用哪种抽取模式、抽取率是否达标、多源同标准如何合并时。与 knowledge-processing 分工：本 skill 管外部规范性文件条款抽取与公共库治理，后者管项目内稿件七道工序。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/standard-regulation-extraction |
| 所属插件 | （非插件内置） |
| 文件数 | 6 |
| 体积 | 40.5 KB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：**未被范围内专家配备**
- 全部专家引用（含范围外）：标准要素抽取专家（expert-131e1b3979fe）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: standard-regulation-extraction
description: "从「标准/法规/政策/公告」四类规范性文件确定性抽取条款，产出跨项目复用的公共标准库（clause_no+clause_text+强制性等级+溯源）。触发：把 GB/建标/JGJ 国家标准、条例/办法/规定类法规、通知/意见/大纲类政策、发布公告转成条款库，或判定某文件该用哪种抽取模式、抽取率是否达标、多源同标准如何合并时。与 knowledge-processing 分工：本 skill 管外部规范性文件条款抽取与公共库治理，后者管项目内稿件七道工序。"
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

**门禁 R1 · 判型可复核**

```python
{"stage": "R1", "gate": "判型可复核",
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

**门禁 R2 · 抽取器匹配**

```python
{"stage": "R2", "gate": "抽取器匹配",
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

**门禁 R3 · 五项必填**

```python
{"stage": "R3", "gate": "条款五项必填",
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

**门禁 R4 · 三条硬指标**

```python
{"stage": "R4", "gate": "抽取质量",
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

**门禁 R5 · 合并留痕**

```python
{"stage": "R5", "gate": "合并留痕",
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

**门禁 R6 · 标签与溯源**

```python
{"stage": "R6", "gate": "标签溯源闭环",
 "check": "每条有 primary_tag + tags；source_url 非空；trace_status 在枚举内"}
```

**代价（实测）**

```
无标签 → 42 个主题无法精准匹配，只能用关键词 grep（准确率低）
无 source_url → 抓取失败的标准无法区分「没抓」与「抓了但空」
```

---

### 工序 7 · 入库校验与发布（已下沉）

**完整步骤见 `references/工序7-入库校验与发布.md`（45 行）。**

摘要：三件套齐备校验（标准号 + 条款号 + 原文）→ 强制等级标注 →
重复条款合并 → `validate_clause_library` 过检 → 发布到公共库。

## 与其他 skill 的分工（已下沉）

见 `references/与其他skill的分工.md`。核心：本 skill 管**外部规范性文件的条款抽取与公共库治理**，`knowledge-processing` 管**项目内稿件的七道工序**。
## 标准效力层级（已下沉）

**判据**：项目建设地决定抓哪一级标准（国标 / 行标 / 地标 / 团标）。

完整层级表见 `references/标准效力层级.md`（102 行），**建库或取条款时读**。

## 资源导航（工序细节、库结构、坑与细则已下沉 references/）

- `references/细则.md` — 7 节
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 10579 | 21aebe995370fa30 |
| references/与其他skill的分工.md | 349 | b16da586259227f3 |
| references/工序7-入库校验与发布.md | 1426 | 2552dd277bde61ff |
| references/标准效力层级.md | 3755 | 7215d5049be1cd4c |
| references/细则.md | 13707 | 57567268c099218d |
| scripts/extractors.py | 11702 | b9a2c68d17596cfd |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/standard-regulation-extraction/`（未改写；已用 SHA-256 复算校验）。
