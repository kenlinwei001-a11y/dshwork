---
name: knowledge-processing
description: 把文档/语料（docx/pdf/md）经七道工序处理为结构化知识图谱语料包，产出 30 个契约文件（含脱敏骨架 skeletons.jsonl）。当用户要求把稿件处理成语料包、跑「归一化→骨架→切块→本体→回放→质量→脱敏索引」七道工序流水线、产出知识图谱/脱敏骨架、或使用 kp_toolkit / corpus_pipeline / MCP 工具（5 组 65 工具）时使用。与 knowledge-processing-toolchain 的区别：本 skill 覆盖完整流水线与 30 文件产物契约，toolchain 覆盖工具+LLM 分层方法论。
---

# 知识处理（Knowledge Processing）

## 目的

把一份历史稿件（docx/pdf/md）经七道工序产出「语料包」：30 个契约文件，供写作 Agent 使用。写作 Agent 只拿脱敏骨架，永远拿不到原文。

## 何时使用

- 用户要求「把稿件处理成语料包」「跑七道工序」「产出语料包」
- 用户要求「结构化知识图谱」「脱敏骨架 skeletons.jsonl」「30 文件契约」
- 用户上传 docx/pdf 要求处理为可溯源、可审计的图谱
- 用户提到 kp_toolkit / corpus_pipeline / kp-*（5 组 MCP）工具

不适用：单纯的文本总结/改写（通用写作）；图谱尚未构建时的自由写作。

## 项目位置

代码工程：`/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/`（kp_toolkit、corpus_pipeline、mcp/server.py）。

## 七道工序（四段式：契约 / 执行 / 门禁 / 代价）

> **为什么不用自然语言写步骤**：实测写了 3 遍「假缺四问」纪律，假缺率仍 77%；
> 写了 1 次 `gap_verify.py` 立刻生效。**纪律靠提醒，机制靠退出码。**
>
> 每道工序四段：① 契约（schema，机器校验）② 执行（真代码+断言）③ 门禁（不通过阻断）
> ④ 代价（为什么必须这么做，只写实测过的坑）。

---

### 工序 1 · 归一化

**契约**

```json
{
  "source": {
    "required": ["normalized_md", "offset_map", "original_ext"],
    "offset_map": {"type": "array", "items": {"required": ["norm_pos", "orig_pos"]}}
  }
}
```

**执行**

```python
def normalize(original) -> dict:
    md = strip_header_footer(original)      # 去页眉页脚
    md = formula_to_latex(md)               # 公式转 LaTeX
    md, offsets = record_offsets(md, original)   # 每个字符的原始位置
    assert len(md) > 0.8 * len(original), "归一化丢失超过 20% 内容"
    assert offsets, "必须有 offset_map，否则无法回原文"
    return {"normalized_md": md, "offset_map": offsets}
```

**门禁 S1 · 归一化闭环**

```python
{"stage": "S1", "gate": "归一化闭环",
 "check": "去空白字符数 ≈ 原稿（±15%）；offset_map 长度 = 归一化后长度"}
```

**代价（实测）**

- 表格拍平成 markdown → 表头与数据行分离 → 40+ 财务节点 subject 退化成「2018」
- 公式不转 LaTeX → 推演算式抽不出来，`computed_from` 关系断了

---

### 工序 1b · 表格解析（**新增，独立于切片**）

> **表格不是文本，是二维结构对象。绝对不许拍平后按行切片。**

**契约**

```json
{
  "table": {
    "required": ["id", "section", "grid", "column_paths", "header_rows"],
    "column_paths": {"type": "array", "minItems": 1,
                     "description": "多级表头合并后的完整路径，如 '资产 / 小计'"},
    "cells": {"items": {"required": ["row", "col", "value", "row_header", "col_path", "subject"]}}
  }
}
```

**执行**

```python
# build/parse_docx_tables.py（已实现并跑通 31 个表）
def parse_tables(docx_path) -> list[Table]:
    for tbl in docx.iter_tables():                    # 读 <w:tbl>，不用 OCR
        grid = []
        for tr in tbl.rows():
            row = []
            for tc in tr.cells():
                span = tc.gridSpan()                  # 跨列
                vmerge = tc.vMerge()                  # 跨行（继承上格）
                row.append(Cell(text=tc.text(), span=span, vmerge=vmerge))
            grid.append(row)
        header_rows = detect_multi_level_header(grid)  # ① 首列空 ② 与首行重复文本
        column_paths = merge_header_paths(grid, header_rows)  # 多级合并 + 去重复
        yield Table(grid=grid, header_rows=header_rows, column_paths=column_paths)

def cell_subject(row_header, col_path):
    """行头 × 列路径 → subject。行头必须跳过序号列。"""
    main, qual = split_qualifier(col_path)     # '技术经济指标 / 合价' → ('', '合价')
    if is_year(row_header):  return f"{row_header}年{main}{qual}"   # 2018年资产总额
    if qual:                 return f"{row_header}（{qual}）"        # 通风空调工程（合价）
    return f"{row_header}{main}"
```

**断言（三条，缺一即失败）**

```python
assert len(tables) == xml_count("<w:tbl>"),        "表格数与 XML 不符"
assert all(t.column_paths for t in tables),        "有表无列路径"
assert all(len(t.column_paths) == t.cols for t in tables), "列路径数与列数不符"
```

**门禁 S1b · 表格结构闭环**

```python
{"stage": "S1b", "gate": "表格结构闭环",
 "check": "每表有 column_paths 且与列数一致；多级表头已合并（含 ' / '）；"
          "每个数值格有 row_header + col_path"}
```

**代价（实测，三次踩坑）**

| 错误做法 | 后果 |
|---|---|
| 拍平成 markdown 后按行切片 | 表头独立成 chunk，列名永远关联不上 → subject 全是「2018」 |
| 取第 0 列当行头 | 表5「序号\|级别\|规划人数」取到「1」→ subject =「1规划人数」 |
| 按列数套表头模板 | 表13-2（5列）被套表13-3 的列名 → `373711.34` 标成「财政补助收入」 |
| 按值反查列名 | `156278.08` 在同一表出现两次（小计/总支出）→ 二义，错配 |

**正确做法**：**用列位 + 行头双坐标**，不猜、不反查。

**载体选择（不是所有表格都要 OCR）**

| 载体 | 方案 | 理由 |
|---|---|---|
| DOCX/XLSX/PPTX | **读原生结构**（`<w:tbl>` / openpyxl） | 行列完整，含 rowspan/colspan |
| PDF 文字层完好 | pdfplumber / Camelot | 有坐标，可还原 grid |
| PDF 扫描件 | 表格识别模型（最后手段） | 只有像素 |

---

### 工序 2 · 骨架抽取

**契约**

```json
{"outline": {"required": ["sections", "mapping", "coverage"],
             "sections": {"items": {"required": ["id", "title", "level", "span"]}},
             "mapping": {"description": "章节 → 法定大纲条款（如 304 号文）"},
             "coverage": {"description": "法定章节全覆盖情况"}}}
```

**执行**

```python
def extract_outline(md, outline_spec) -> dict:
    secs = parse_headings(md)
    mapping = map_to_legal_outline(secs, outline_spec)
    missing = [x for x in outline_spec if x not in mapping]
    return {"sections": secs, "mapping": mapping,
            "coverage": {"missing": missing, "rate": 1 - len(missing)/len(outline_spec)}}
```

**门禁 S2 · 大纲覆盖**

```python
{"stage": "S2", "gate": "大纲覆盖",
 "check": "法定章节 must_cover 全覆盖；每节有 span 可回原文"}
```

**代价**

- 章节号靠正则抓 → 附录「表13-2」被当成「§13.2」，章节树错位
- 无 span → 后续 claim 的 evidence 无法定位到原文

---

### 工序 3 · 切块

**契约**

```json
{"chunk": {"required": ["id", "text", "span", "section"],
           "text": {"minLength": 1},
           "span": {"required": ["start", "end"], "description": "在 normalized_md 中的字符偏移"}}}
```

**执行**

```python
def chunk(md, secs) -> list[Chunk]:
    out = []
    for sec in secs:
        for seg in semantic_split(md[sec.span]):   # 按段落/表/图注切
            out.append(Chunk(text=seg, span=seg_span, section=sec.id))
    assert sum(len(c.text) for c in out) >= 0.85 * len(md), "切块丢失超过 15%"
    return out
```

**门禁 S3 · 切块闭环（引用 P3）**

```python
{"stage": "S3", "gate": "切块闭环",
 "check": "见 semantic-chunking-skill P3：Σchunk 去空白 ≈ 原稿（±15%）；span 可回查"}
```

> **为什么引用而不重写**：同一判据写两遍，改一处必漏另一处（本轮踩过：前端 REL_SCHEMA 与后端 relation_types.yaml 各写一份，96 条误报）。

**代价**

- **表格按行切块** → 见工序 1b，这是最容易犯的错
- 切块丢 span → 溯源链断，正文无法回读成节点

---

### 工序 4 · 本体抽取

**契约**

```json
{
  "node": {
    "required": ["id", "kind", "subject", "section"],
    "kind": {"enum": ["quantity", "text", "fact", "claim", "evidence", "reference"]}
  },
  "relation": {
    "required": ["id", "from", "to", "type"],
    "type": {"enum": "读 reuse/relation_types.yaml，不硬编码"}
  },
  "claim": {"required": ["id", "text", "claim_type", "falsifiable_by"],
            "claim_type": {"enum": ["conclusion", "recommendation", "hypothesis", "inference"]}},
  "evidence": {"required": ["id", "kind"],
               "kind": {"enum": ["E0","E1","E2","E3","E4","E5","E6","hypothesis","fact"]}}
}
```

**执行**

```python
# 确定性部分（零 LLM）
def classify_claim(text, has_value, has_triple) -> dict:
    """四步判定，顺序不可换（kp_toolkit/claim_classify.py）"""
    if is_norm_restatement(text):     return {"kind": "fact"}     # ① 规范转述
    if has_triple and not has_judge(text): return {"kind": "fact"} # ①b 三元组完整
    ct = classify_judge_words(text)    # ② 判断词四族
    if ct: return {"kind": "claim", "claim_type": ct}
    if has_value: return {"kind": "fact"}   # ③ 有值无判断词
    return None                              # ④ 都不是

assert claim["claim_type"] in CLAIM_TYPES,     "claim_type 越界"
assert claim.get("falsifiable_by"),            "claim 缺 falsifiable_by = 口号"
assert evidence["kind"] in EVIDENCE_KINDS,     "证据等级越界"
```

**语义部分（LLM + schema + validator + 重试）**

```python
for attempt in range(3):
    out = llm_extract(chunk, schema)
    if validator(out): break
```

**门禁 S4 · 抽取闭环 ×3**

```python
{"stage": "S4", "gate": "抽取闭环 ×3",
 "check": "① 引用闭环（原稿引用 ⊆ 条款∪豁免） ② 数值闭环 ③ 论层闭环（有论断义务的章必须产 claim）"}
```

**代价**

- 按章节倾向给 kind → 68 个 judgment 里 49 条实为 fact（误差 74%）
- claim 无 `falsifiable_by` → 写作时把 hypothesis 写成既成事实
- 证据标 E1 但无 provider → 31 条全部缺三要素，说明 E1 是默认值不是判断结果

---

### 工序 5 · 推演回放

**契约**

```json
{
  "binding": {"required": ["target", "expr", "deps"],
              "deps": {"items": {"required": ["node", "value"], "description": "node 必填，null 即未绑定"}}},
  "rule": {"required": ["id", "expr", "kind"],
           "kind": {"enum": ["compute", "condition"], "description": "condition 是 A=>B；否则=>C 判定式"}}
}
```

**执行**

```python
def replay(bindings, nodes) -> dict:
    ok, missing, mismatch = [], [], []
    for rid, b in bindings.items():
        deps = {k: v for k, v in b["deps"].items() if v.get("node")}
        if len(deps) < len(b["deps"]):
            missing.append((rid, [k for k in b["deps"] if k not in deps])); continue
        res = eval_rule(b["expr"], deps)          # 支持 compute 与 condition 两型
        original = find_original(nodes, b["target"])
        (ok if match(res, original) else mismatch).append((rid, res, original))
        # 关键：算出结果必须落成节点，否则下游查不到
        ensure_output_node(b["target"], res, b["expr"])
    assert not missing or all(has_reason(m) for m in missing), "缺依赖必须带 searched 证据"
```

**门禁 S5 · 派生闭环（引用 P11）**

```python
{"stage": "S5", "gate": "派生闭环",
 "check": "见 reasoning-extraction-skill P11：要么闭合要么显式阻塞；可算规则必须产出 output 节点"}
```

**代价（实测最重的一处）**

| 错误 | 后果 |
|---|---|
| 绑定表填了 node，不建 relations 边 | 输入节点成孤儿，图查询查不出「这值被哪条规则用」 |
| 规则算出了结果，不建输出节点 | 输入节点永远悬空；`49m` 只存在于表达式里 |
| 「主体包含」匹配不校验量纲 | `基本预备费费率` 绑到 `基本预备费=618万元` → 算出 76378（应为 618） |
| 判定式用 `eval` 硬算 | `A<=B => 合理；否则 => 待审` 必然 SyntaxError |
| 两个依赖绑到同一节点 | `建安工程费用` 与 `招标估算` 都绑 10135 → 判定恒为「一致」，掩盖 1053 万差异 |

---

### 工序 6 · 质量登记

**契约**

```json
{
  "gap": {"required": ["what", "why_real", "searched"],
          "searched": {"minItems": 1, "description": "没有 searched 的缺不许进台账"}},
  "conflict": {"required": ["id", "subject", "values", "evidence_strength", "status"],
               "evidence_strength": {"enum": ["strong", "weak", "none"]},
               "status": {"enum": ["resolved", "report_fix", "open"]}}
}
```

**执行**

```python
# 假缺四问（kp_toolkit/gap_verify.py，已实现）
def verify_gap(gap, nodes, chunks, aliases):
    n, way, cands = search_node(gap, nodes, aliases)   # ① 精确/别名/包含
    if n: return {"verdict": "false", "action": "补绑定"}
    found, carrier, _ = search_text(gap, chunks)       # ② 文本/表格/表注
    if found: return {"verdict": "false", "action": "补抽取（在%s里）" % carrier}
    if not dimension_ok(gap): return {"verdict": "false", "action": "量纲不符，检查绑定"}
    if should_not_exist(gap): return {"verdict": "false", "action": "设计上不需要"}
    return {"verdict": "real", "searched": [...]}

assert gap["searched"], "无 searched = 未验证 = 不许报缺"
```

**门禁 S6 · 冲突/缺口闭环**

```python
{"stage": "S6", "gate": "冲突/缺口闭环",
 "check": "每个 (主体,属性) 多值必须登记待审；每条缺必须带 searched 三问证据"}
```

**代价（最贵的一课）**

```
累计报「缺」1496 个 → 复核后真缺 345 个 → 假缺率 77%

关系缺证据  190 → 2（三级判定缺失）
模糊引用     48 → 4（缺四层过滤）
条款必填    131 → 0（字段别名不认）
推演必填     75 → 0（False 被当缺失）
孤儿节点   1010 → 327（'None' 字符串 + 描述性无关系）
```

**公信力 = 1 / (1 + 假缺率)。77% 假缺率下，编制方查 4 条有 3 条是假的。**

---

### 工序 7 · 脱敏索引

**契约**

```json
{
  "skeleton": {"required": ["id", "text", "node_refs"],
               "text": {"description": "值已被 {{node:N-xxx}} 替换"}},
  "desensitize_levels": {"enum": ["node", "time", "entity"],
                         "description": "三层：节点引用 / 时间 / 主体名"}
}
```

**执行**

```python
def desensitize(chunks, nodes) -> list[Skeleton]:
    for c in chunks:
        t = replace_values(c.text, nodes)     # 值 → {{node:ID}}
        t = replace_times(t)                  # 时间 → {{time:2020-07}}
        t = replace_entities(t)               # 主体 → {{ent:owner}}
        assert count_placeholders(t) == count_refs(c), "占位符数 ≠ 节点引用数"
        assert not has_nested_placeholder(t),        "不允许嵌套占位符"
        assert not has_residual_number(t, nodes),    "不许残留可反推的字面数"
```

**门禁 S7 · 脱敏闭环**

```python
{"stage": "S7", "gate": "脱敏闭环",
 "check": "占位符数 = 节点引用数；无嵌套；无残留字面数"}
```

**形 vs 值判据**（决定脱不脱敏）

```
删掉它，文档结构还完整吗？
  完整 → 形（章节号/页码/序号）→ 保留
  不完整 → 值（测量值/时间/实体）→ 脱敏
```

**代价**

- 数值不脱敏 → 骨架泄露真实项目数据，跨项目复用失去意义
- 脱敏后不回填值表 → 骨架里的占位符还原不了

---

## 工序依赖与门禁总表

```
S1 归一化 ──┬─→ S1b 表格解析 ──┐
            └─→ S2 骨架 ──→ S3 切块 ──┴─→ S4 本体抽取
                                              ↓
                                        S5 推演回放
                                              ↓
                                        S6 质量登记
                                              ↓
                                        S7 脱敏索引
```

| 门禁 | 不通过的后果 |
|---|---|
| S1 归一化 | 回不到原文，溯源链断 |
| **S1b 表格** | **列名丢失，subject 退化** |
| S2 大纲 | 法定章节漏写 |
| S3 切块 | 切块丢失内容 |
| S4 抽取 | 论断/证据分类错，写作口径错 |
| S5 派生 | 规则静默跳过，数值无来源 |
| S6 质量 | 假缺泛滥，公信力崩塌 |
| S7 脱敏 | 跨项目复用失效 |

**任何一项 covered < total → 装配侧拒绝发布。**

## 运行方式

```bash
cd /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert
# 七道工序全链路（docx/pdf 解析需 venv 里的 pymupdf/python-docx）
.venv/bin/python -m corpus_pipeline.cli run 稿件.docx --out 语料包目录
# 确定性工具层自测
python3 -m kp_toolkit.test_kp_toolkit
python3 -m corpus_pipeline.test_pipeline
python3 -m corpus_pipeline.test_llm_extraction
```

`run_pipeline` 关键参数：

- `legal_outline`：法定大纲列表（工序 2 覆盖校验用）
- `extractions`：LLM 语义抽取输出（缺省时工序 4 降级为数值占位）
- `original_path`：原稿路径（落盘 source/original.<ext>）

## 30 文件契约

契约定义在 `corpus_pipeline/spec.py`（MANIFEST 列表，含主存/副本/可变/Agent 形式）。要点：

- **主存列是权威副本**，副本列是冗余拷贝，以主存为准。
- **Agent 访问形式**：① 注入（constraints/meta/outline/gate/style/terms）· ② 工具调用（corpus_get_chunk 等 10 个）· ③ 内嵌（conflicts/gaps）· ✕ 不对外（原文/整包/事件流）。
- **安全边界**：写作 Agent 只拿 `chunks/skeletons.jsonl`（数值已替换为 {{node:Nxx}}），永远不拿 `chunks/chunks.jsonl`（原文）。

> **与七道工序「契约」段的区别**：
> 本节管**产物清单与管理规则**（有哪些文件、谁是权威副本、谁能访问），
> 工序里的「契约」段管**每道工序的输入输出字段结构**（如 table 必须有哪些键）。
> 两者不重复：本节答「交付什么」，工序契约答「每步产出长什么样」。

## 确定性 vs 语义（tool+LLM 分层）

- 确定性步骤（分句/分块/建图/溯源/数字·时间冲突/schema 校验）→ kp_toolkit 代码，零 LLM，可复现可单测。
- 语义步骤（实体/事实/关系/Claim/证据/推理抽取、证据判断、推演写作）→ LLM 结构化输出 + schema + validator + 重试（复用 20 个抽取技能）。
- 分层方法论详见 knowledge-processing-toolchain skill。

## MCP 工具（65 个，按权限域拆 5 组）

`mcp/server.py`（stdio，NDJSON 帧，用 venv python 启动），按 `KP_MCP_GROUP` / `--group` 拆 5 个 MCP：

- kp-processing（30）：知识处理七道工序 —— corpus_run / segment_* / detect_* / validate_graph / manifest / embed / reemit_* / corpus_search / graph_* / gate_check / evidence_get
- kp-assembly（16）：装配+验证+写作 —— schema_diff / decide_reuse / instantiate_project / build_work_package / gate_check_draft / bootstrap_ontology / impacted_assets / run_quality_gates / check_number_consistency / check_requirements / sensitivity_analysis / validate_shacl / assess_capability / validate_source_anchor / project_where_written / wp_get_facts
- kp-library（7）：资产库+发布 —— library_list_packages / library_search / library_get_asset / library_find_analog / library_status / library_promote / library_publish
- kp-semantic（6）：语义对齐+本体 —— resolve_concept / semantic_classify / ossie_import / ossie_export / ontology_export / ontology_import
- kp-reserved（6）：预留 —— semantic_search / asset_rerank / solve_constraint / graph_db_query / store_object / llm_invoke

## 嵌入

`corpus_pipeline/embed.py`：fastembed（ONNX，无 torch）+ paraphrase-multilingual-MiniLM-L12-v2（384 维，支持中文）。`build_embeddings` 严格输出 `chunks/embeddings.parquet`（pyarrow）。

## 存储

`corpus_pipeline/backends.py`：PG/Neo4j/Qdrant 真实适配器 + 文件系统回退。环境变量 KP_PG_DSN / KP_NEO4J_URI / KP_QDRANT_URL 配置；docker-compose.yml + storage/schema.sql 在项目目录。未配置时自动回退文件系统（对象存储）。

## 铁律

- 冲突一律「待审」呈现，不擅自改数字或补口径。
- 缺失事实保持显式未知（TODO/待补充），绝不编造。
- 数值单源存在图节点；正文可反向回读为图谱节点。
- 能确定性的绝不交给模型；需要语义的才调 LLM，且必须结构化 + 校验。

<!-- kp-patch:v1 -->
## 工序之外的三道机制（v1 新增）

七道工序解决「怎么处理」；下面三道解决「**怎么知道没漏**」。它们不是工序，是门禁。

| 机制 | 模块 | 作用 | 判据 |
|------|------|------|------|
| **源侧索引 source ledger** | `corpus_pipeline/source_ledger.py` | 让「漏了什么」成为可计算的问题 | 引用/表/带单位数值/标题/题注/设备参数 逐类枚举 |
| **闭环校验 closure verify** | `corpus_pipeline/closure_verify.py` | `S − P − 豁免 = ∅` | C1 依据 / C2 关键取值 / C3 章节 / C4 设备参数 / C5 题注 / C6 装配 / C7 关系 |
| **分步门禁 stage gates** | `corpus_pipeline/stage_gates.py` | 每步一道闭环，落在**可重做单元的出口** | S0–S11；含**探针正样本标定** |

**为什么必须有**：旧 `validate_extraction` 的三个循环都是 `for x in ext.get(...)`——
**只遍历产物**。对产物集合的任何遍历，逻辑上不可能发现「属于源而不属于产物」的元素。
因此「依据漏抽 54 条」这类缺陷会**静默通过**，不是校验不够严，是方向错了。

**契约扩展（30 → 32 文件）**：

| 新增文件 | 用途 |
|----------|------|
| `chunks/sentences.jsonl` | 句子层：Claim 追踪的最小单位，稳定 ID 可回溯到 chunk |
| `source_ledger.json` | 源侧索引：闭环校验的基准 |

**判定权归属**：门禁由**编排器**调用，**不由抽取/写作 Agent 自判**。
探针未过标定 ⇒ 该项 `invalid`，**不得输出「无误」**。

**可替换环节**：实体/关系/推理/图存储四个环节走 `corpus_pipeline/providers.py` 的 provider 接缝；
换实现（例如换成外部图基础设施）**不需要改任何门禁判据**。缺能力时该项判 `invalid`。


<!-- kp-patch:v2 -->
## Semantica 外部核验（v2 新增）

Semantica 是**图原生知识基础设施**（27 模块 / 6 层，官方原则：*Every Semantica module works independently*）。
在 v1 的 provider 接缝之外，它提供**另一种外部图实现**，可独立承担多道工序的一部分，也能与 LLM 组成组合。

### 前置（本机已就绪）

| 项 | 值 |
|----|----|
| venv | `/Users/apple/.venvs/semantica`（semantica 0.7.0） |
| LLM 路径依赖 | venv 内需 `openai` + `instructor`（缺则 DeepSeek provider 报 not available） |
| 凭据 | `~/.semantica/env`（600 权限，`DEEPSEEK_API_KEY`）；**不写进连接器定义** |
| KG | `/Users/apple/.semantica/graph.json` |
| MCP | 已注册 `semantica` 连接器（15 工具），由 definitions 目录管理，连接器管理器不可见 |

### 模块到工序映射

| 工序 | 模块 | 独立可用 | +LLM 组合 |
|------|------|----------|-----------|
| 1 归一化 | `ingest` + `parse` + `normalize` | 是 | DoclingParser 的 OCR/版面 |
| 3 切块 | `split.TextSplitter`（12 法） | 是（sentence/paragraph/recursive） | semantic_transformer / llm / entity_aware |
| 4 本体抽取 | `semantic_extract`（NER/关系/三元组/事件/共指） | 仅英文（pattern） | `method="llm"`：**中文唯一可用路径** |
| 4' 消歧 | `deduplication.DuplicateDetector` | 是 | - |
| 5 推演回放 | `reasoning`（前向链/后向链/Datalog/SPARQL/RETE/时间区间） | 是 | 第 8 种 LLM 图推理 |
| 6 质量 | `conflicts.ConflictDetector` + `ontology.SHACLGenerator` | 是（检测） | `expert review` 策略 |
| 全程溯源 | `provenance.ProvenanceManager` | 是（W3C PROV-O + SHA-256） | - |
| 决策台账 | `context` / MCP `record_decision` | 是 | GraphRAG 查询 |
| 实体归一（暂代 JEV） | `reasoning` 规则前向链（约等于 MCP `run_reasoning`） | 是 | DeepSeek 判官交叉校验 |

### 铁律约束（违反即作废）

1. **禁用 `ConflictResolver`**：其 7 种策略（可信度加权投票、最近优先等）会产出单一决议值，直接违反「冲突一律待审」。只用 `ConflictDetector`。
2. **归一只产候选**：LLM 判官**判 DIFF 精度 100%（可直接过滤）**，**判 SAME 精度仅 58%（系统性过度合并）**；合并必须人工确认。
3. **中文抽取必须 `method="llm"`**：`pattern` 是英文规则集（中文 0 实体），`ml` 依赖 spaCy（本机未装）。

### 实体归一（`run_reasoning` 暂代 JEV）

规则判官（对 17 组人工标准答案 **15/17 = 88%**）+ DeepSeek 判官（12/17 = 71%）双路合并：

```text
1104 组去重候选 -> 规则判官排除 737 -> LLM 的 DIFF 排除 296 -> 71 条待人工判断（降幅 94%）
  A 高置信 7 条（confidence >= 0.85，抽审）
  B 中置信 16 条（0.60-0.84，快速过目）
  C 低置信 48 条（< 0.60，逐条审校；含 53 条两路引擎分歧）
```

产物落位 `语料包/外部核验/`：`实体归一-人工判断清单.md`（末列填 合并/不合并/裁决）、
`entity-normalization-queue.tsv`、`subject-normalization-queue.yaml`（含 `confidence` / `review_tier`）。
**合并未执行，须人工确认。**

### 复现脚本（`构建脚本/`）

`semantica_p0.py`（冲突互证）、`semantica_p1p2.py`（消歧 + PROV-O + 切块）、`semantica_p1a_refine.py`（候选分类）、
`semantica_rule_judge.py`（规则判官 + 校准）、`semantica_normalize_queue.py` / `semantica_refine_confidence.py` /
`semantica_merge_judges.py` / `semantica_make_review_md.py` / `semantica_report.py`；
LLM 两脚本 `semantica_judge_test.py` / `semantica_judge_bulk.py` 需 `DEEPSEEK_API_KEY`。

### MCP 通道的正确调用姿势（2026-10-13 实测，务必照做）

MCP 版抽取与 Python API 版**不是同一套 provider 解析**，踩过三个坑：

1. **MCP 的 `extract_entities` 内部走 `openai` provider**，它**不读** `DEEPSEEK_API_KEY`。
   只设 DEEPSEEK key 时，调用会静默回退 pattern 并返回 `{"entities": []}`（无报错）。
2. 因此 `~/.semantica/env` 必须**同时**导出：
   `export OPENAI_API_KEY=<deepseek key>` 与 `export OPENAI_BASE_URL=https://api.deepseek.com/v1`
   （OpenAI SDK 原生读 `OPENAI_BASE_URL`，从而把 openai provider 指向 DeepSeek 端点）
3. **必须显式传 `model="deepseek-chat"`**；省略 model 会 422（`model: invalid type: null`）。

正确调用：

```text
mcp__semantica__extract_entities(
  text="…18319平方米…", method="llm", language="zh", model="deepseek-chat")
→ entities: [上海财经大学(ORG), 中山北一路校区(GPE), 18319平方米(CONCEPT), …]
```

**已知工具级缺陷**：`extract_relations` 的 MCP 包装**硬编码 NER 步为 `methods=["ml"]`**（spaCy 未装），
且 `TripletExtractor()` 用默认（pattern）；因此**经 MCP 无法走 LLM 抽关系/三元组**（返回空）。
关系与三元组请走 **Python API**：

```python
from semantica.semantic_extract import RelationExtractor, TripletExtractor
RelationExtractor(method="llm", provider="deepseek", llm_model="deepseek-chat")
TripletExtractor(method="llm", provider="deepseek", llm_model="deepseek-chat")
# 实测：1 个 chunk → 24 关系 / 25 三元组
```

**改完 env 后必须让 MCP 进程重生**：kill 掉 semantica 的 python 进程（Host 会懒重生），或重启 dsh web。
进程只在启动时读一次 env，运行中修改无效。

### 已决：不装 spaCy、不给 Semantica MCP 打补丁（2026-10-13）

评估过三个选项，结论如下（**后续不要再重新讨论**）：

| 选项 | 结论 | 理由 |
|---|---|---|
| 装 spaCy + zh 模型 | **否决** | 只能救 `mcp_server/__init__.py` 第 160 行写死的 `methods=["ml"]`，救不了第 162 行 `TripletExtractor()` 的漏传（签名本就支持 method）→ 三元组照样空；zh 通用模型抽不到领域指标；且会让 NER 工具与关系工具走两套引擎，同文本实体不一致 |
| 修 MCP 包装（约 5 行） | **暂不做** | 技术上可行，但改 site-packages，升级即丢 |
| **走 Python API** | **采纳** | 实测 1 chunk → 24 关系 / 25 三元组；provider/model 完全可控；已固化 `semantica_verify/` |

**A 方案下的通道分工（照此执行）**：

| 能力 | 走哪条通道 |
|---|---|
| 中文实体抽取 | MCP `extract_entities(method="llm", language="zh", model="deepseek-chat")` 或 Python API |
| 中文关系 / 三元组抽取 | **仅 Python API**：`RelationExtractor / TripletExtractor(method="llm", provider="deepseek", llm_model="deepseek-chat")` |
| 规则推理（实体归一判官） | MCP `run_reasoning` 或 `semantica.reasoning` |
| 决策台账 | MCP `record_decision` / `query_decisions` / `find_precedents` |
| 图谱 CRUD / 分析 / 导出 | MCP `add_entity` / `add_relationship` / `update_node` / `query_graph` / `get_graph_analytics` / `export_graph` |

上游 `semantica 0.7.0` 是本机最新版（PyPI 确认），无修复版可升。

### 已决：解析保持 DocumentParser，暂不部署 docling（2026-10-14）

| 项 | 结论 |
| --- | --- |
| 结论 | **保持 semantica.parse.DocumentParser**（Semantica 官方标准路径，非第三方替代，不构成降级） |
| docling 定位 | Semantica 的 **optional extra**：`Provides-Extra: parse-docling` / `Requires-Dist: docling>=2.107.0`；包内只有适配器 `docling_parser.py`，**不含 docling 本体** |
| 实测缺口 | 31 表 / 1551 单元格中 **270 个合并单元格(17.4%)** 被 python-docx 重复填充，**真实 colspan/rowspan 无法还原**；无表头识别；无 OCR；无版面模型 |
| 不装的依据 | ① 本件是 Word 2007+ 原生 docx，**非扫描件 -> OCR 无需求**；② 表格规模不大；③ docling 会引入 **torch**，此前实测与 numpy 2 冲突并**打穿过 `semantica.vector_store`**；④ 标准路径已够用 |
| 已做的缓解 | 按「左/上邻同值置空」去合并渲染（`ingest_parse/tables-by-semantica.md`），并把结构化表落盘（`tables.jsonl`） |
| 复核触发条件 | 出现扫描件 / 批量表格密集文档 / 需要真实单元格跨度或表头时，再部署并做安装后回归验证 |

**教训**：Semantica 是**适配层**——带接口，不带被适配的实体。向量（需 fastembed）、解析（需 docling）、LLM（需 provider key）都是同一形态；装之前先确认 extra 与依赖，并做安装后回归验证。

### 已决：不重建语料（2026-10-14）

**背景**：本轮补齐了 `source/original.docx`（1,123,286 B / 12 图 / 31 表），并用 Semantica 解析出
150,841 字正文 + 31 个表格的结构化数据（1,551 单元格）。但语料的 **1208 chunk 与 442 事实**
仍是基于【资料库文本视图】构建的，表格在语料中呈**扁平文本**。

**决定**：本轮**不重建语料**。核心数字保持不变（442 事实 / 1208 chunk / 13 冲突 / 7 缺口 / 514 关系）。

**含义**：

| 项 | 状态 |
| --- | --- |
| `外部核验/ingest_parse/tables.jsonl`（1,551 单元格） | 与语料**解耦**，仅作外部核验产物 |
| 语料中 31 个表格的内容 | 仍为扁平文本（如投资估算表、用水量表、技术指标表） |
| 若将来要表格入语料 | 需以 `parsed-by-semantica.md` + `tables.jsonl` 为源重跑七道工序，**核心数字会全部重算** |

**这不是跳过 Semantica**：加载与解析环节已真实执行并留证（`ingest_parse/semantica-attestation.yaml`），
只是**解析结果未回灌语料构建链**——属产品决策，非能力缺失。

# SKILL.md 补充章节（追加到 knowledge-processing / document-parsing-skill）

## 表格抽取：宽表必须回 docx 取列结构

### 什么时候需要

文档里的表格满足以下任一条，就不能只靠 markdown 抽值：

- 表头有**合并单元格**（一个分组名跨多列，如「技术经济指标」跨「数量/单位/单价」）
- 表头列数 ≠ 数据列数
- 同一行有 **3 个以上数值**（数量、单价、合价并存）

### 必须做的四步

```python
# 1. 回 docx 拿真实列结构
from kp_toolkit.tables import parse_docx_table_grid
grids = parse_docx_table_grid("source/original.docx")

# 2. 抽值（自动用 gridSpan 还原表头、按列角色映射）
from kp_toolkit.tables import extract_table_values
nodes, skipped = extract_table_values(chunks, grids, exist_pairs)

# 3. 检查 skipped：每一条都是「为什么这张表没抽」，不是静默跳过
for s in skipped:
    if not s.get("info"):          # info=True 是「已修复」，无 info 是真跳过
        print("跳过:", s["section"], s["reason"])

# 4. 抽完必须回填脱敏
#    新节点的值要进值表（否则骨架里的占位符还原不了）
#    表格里的字面量要换成 {{node:ID}}
```

### 九条规则速查

| 规则 | 一句话 |
|---|---|
| ① | `1.7.1` 这类多级编号不是主体 |
| ②b | 值列在数据里必须 ≥80% 是数字，否则说明列错位 |
| ③ | 双层表头以子列行为准，列名 = `分组·子列` |
| ④ | `合计/小计` → predicate=合计；`（一）` → 汇总 |
| ⑤ | 两个值列相邻 = 中间缺单位列，搬空列补齐 |
| ⑥ | **跨列合并必须回 docx 取 gridSpan**（markdown 不可恢复） |
| ⑦ | `/ - — 无 待定` 是空值，不计入数字比例 |
| ⑧ | `72．0` 是全角句号，要归一化成 `72.0` |
| ⑨ | `13．5` 被拆成 `{{node:X}}．5` 要整格还原 |
| ⑩ | **时间也是值，必须脱敏**：`2020年7月` → `{{time:2020-07}}`、`2018` → `{{year:2018}}` |

### 三层脱敏缺一不可

| 层 | 占位符 | 例子 | 换项目 |
|---|---|---|---|
| 值 | `{{node:N-xxx}}` | `18319 ㎡` | 换值表 |
| 时间 | `{{time:2020-07}}` | `2020年7月开工` | 换 time_values |
| **实体** | `{{ent:owner}}` | `上海财经大学` | 换 entity_values |

只做值脱敏 → 封面「编号 2019ZX054 · 上海财经大学中山北一路校区 · 大数据研究中心·上海同济工程咨询有限公司」换项目一字不可用。

### 形 vs 值的判据

> 删掉它，文档结构还完整吗？完整 → 形（保留）；不完整 → 值（脱敏）

- **形**（保留）：章节号 `1.1`、页码 `118`、列表序号 `1 2 3`
- **值**（脱敏）：测量值、**时间**、项目编号

反例：把年份当页码一起排除 → 骨架里 101 处时间全裸，写作专家可直接抄「2020年7月开工」。

### 反例（这些做法会出错）

- ❌ 只用 `(首格, 列数)` 匹配 docx 表 → 收入表和支出表都是「年度+5列」会撞车，必须加第 2 列名
- ❌ 双层表头按索引硬拼 `h1[i]+"·"+h2[i]` → `备注·单位造价` 这种语义错乱
- ❌ 列数不一致就跳过 → 会漏掉「值列自带单位」的表（第 ⑤ 条能救）
- ❌ 抽完不回填值表 → 占位符变成死引用（实测 220/284 无法还原）

### 验收标准

```
占位符可还原率 = 100%      # 每个 {{node:ID}} 在值表里都能查到值
坏占位符（拆分）= 0         # 不存在 {{node:X}}．5 这种
skipped 每条都有 reason    # 没有静默跳过
数值自洽                   # 小计 = 各分项之和（抽查）
```


## 推演链：数值来源必须进图谱（computed_from）

### 为什么

数值事实的「从哪算出来」以前只存在旁路文件（derivation_bindings.yaml），不在关系图谱里。后果：
- 下游写作拿到的图谱只有「值 = 95.04」，看不到「由 1800×40 + 288×50 按公式算出」
- 无法复算、无法审计、冲突时定位不到是输入错还是公式错
- 换项目时要重算，却不知道依赖哪些输入

### 规则

**推演链是一种关系，不是旁路数据。** 数值由规则算出，必须在图谱里生成边：

```yaml
# 输出值 --computed_from--> 输入值
- from: N-c67295c8a345        # 95.04
  to:   N-d33295e7e784        # 1800
  type: computed_from
  family: 依据
  payload:
    rule_id: R-最高日用水量
    expr: round(({科研学生用水人数}*{科研学生用水定额}+...)/1000*(1+{未预见系数}/100), 2)
    dep_var: 科研学生用水人数
    dep_value: "1800"
    output_value: "95.04"
    output_unit: m³/d
```

一条规则有 N 个输入 → N 条边（同一 rule_id）。

### 三类关系不要混

| 关系 | 用在 | 判据 |
|---|---|---|
| `derives_from` | **论断**层面 | A 由 B 推出一个判断（不含数值计算） |
| `computed_from` | **数值**层面 | A 由 B/C/D 按公式算出（payload 必带 rule_id + expr） |
| `depends_on` | 依赖但不计算 | A 的成立取决于 B，但算不出来 |

反例：把「95.04 从 1800 算出」记成 `derives_from` —— 无法区分是论断推导还是数值计算，下游无法复算。

### 产出四件套（缺一不可）

```
① graph/rules.yaml              规则表达式（{变量} + round()）
② graph/derivation_bindings.yaml 变量名 → 节点 ID 的绑定（含 how 说明）
③ graph/relations.yaml          computed_from 边（带 rule_id + expr）
④ quality/derivation_gaps.yaml  缺口报告（哪些规则缺依赖、哪些值孤立）
```

### 绑定 deps 的坑（实测）

- 规则 deps 是**设计变量名**（`科研学生用水人数`），节点是（subject=科研学生, value=1800, unit=人）—— 名字对不上
- 绑定必须只考虑 **value 是数字** 的节点（EN- 实体节点的 value 是名称，会污染）
- 单位要**精确相等**：`"人" in "L/人·日"` 为真 → 会把用水定额误绑成人数
- 无名依赖（系数/天数）按「target 所在章节」+ 单位定位，不是按规则自身 section

### 验收

```
可执行规则数 / 总规则数        越高越好（本项目 8/35）
可执行且算出=原文              8/8（差 0.01 以内视为对上）
缺依赖规则                      每条都要列清楚缺哪个变量
孤立数值节点                    既非规则输出也非输入 → 逐个判断是真静态还是漏挂
```


## 约束关系：数值取值必须有边界（bounded_by）

### 为什么

一个数值不仅要问「怎么算出来的」（computed_from），还要问「这个取值合不合规」。
如果图谱里只有值没有边界，下游写作就会写出「符合规范」这种没有依据的话。

### 规则

数值取值受外部条款约束时，必须生成 `bounded_by` 边：

```yaml
- from: N-7c3d781cf6f1            # 地上总建筑面积需求 18040 ㎡
  to:   NX-条款-00x               # 建标191-2018 专职科研机构用房人均建筑面积指标
  type: bounded_by
  payload:
    clause: 建标191-2018 专职科研机构用房人均建筑面积指标
    taken_value: "18040 ㎡"
    range_known: false            # ← 关键：条款限值原文是否取到
    status: 待核
    note: 本次未取到条款限值原文，不得据此判定符合规范
```

### range_known 是硬开关

| range_known | 含义 | 允许说什么 | 禁止说什么 |
|---|---|---|---|
| `true` + lower/upper | 条款限值已知 | 「在 X~Y 区间内，符合」 | — |
| `false` | 限值原文未取到 | 「取值 16㎡/人，依据条款待核」 | **「符合规范」** |

实测本项目 25 条 norm_link **全部是 range_known=false** —— 即所有合规判定都只能标「待核」。

### 和另外两类别混

| 关系 | 回答的问题 |
|---|---|
| `computed_from` | 这个数**怎么算出来的**（输入 + 公式） |
| `bounded_by` | 这个取值**合不合规**（边界 + 条款） |
| `cites` | 这段论述**依据哪个文件**（不涉及数值） |

反例：把「人均面积 16㎡/人受建标191约束」记成 `cites` —— 拿不到区间，无法判合规。

### 绑定坑（实测）

- `norm_link` 里的 `norm_node` 可能是**失效旧 ID**（本项目 25 个全部失效）
- 必须按条款关键词回退匹配 `NX-条款-*` 节点（标准号 → 主题词）
- 匹配不上就**不生成边**，不要硬挂到错误条款上


## 工程类专业数据：四类必建关系 + 覆盖率验收

### 背景

设计类文档（可研的"项目规划设计方案"章）里数据最密集：设备台数、负荷指标、消防水量、气象参数。
实测某个第六章 **112 个数值节点里只有 14 个建了关系（12%）** —— 剩下 98 个孤立，
意味着「这栋楼要装多少冷量、为什么是 135 W/㎡、消防水量怎么来的」全答不上来。

### 四类必建关系

| 数据形态 | 关系 | 公式 | 实测例子 |
|---|---|---|---|
| **设备产能** | `computed_from` | 台数 × 单台能力 | 22 台 × 90 kW = 1980 kW |
| **设备功率** | `computed_from` | 台数 × 单台功率 | 22 台 × 28.4 kW = 624.8 kW |
| **空调负荷** | `computed_from` | 面积 × 指标 ÷ 1000 | 18319 × 135 ÷ 1000 = 2473 kW |
| **消防水量** | `computed_from` | 流量 × 延续时间 × 3.6 | 40 L/s × 2h × 3.6 = 288 m³ |
| **排水量** | `computed_from` | 用水量 × 排放系数 0.9 | 95.04 × 0.9 = 85.54 m³/d |
| **设计参数** | `bounded_by` | 条款限值 | 室外 34.4℃ ← GB50736 附录A |

### 设计参数必须挂规范（不能裸值）

| 参数组 | 挂到 |
|---|---|
| 室外气象（温度/湿度/气压/海拔） | GB50736 附录 A |
| 室内设计（温度/湿度/新风/噪声） | GB50736 / GB50189 |
| 换气次数（卫生间/机房/泵房） | GB50736 表 |
| 耐火等级 / 防火分区面积 | GB50016 表 5.3.1 |
| 抗震设防类别 / 地震参数 | GB50223 / GB50011 附录A |
| 楼面活荷载 / 地面粗糙度 | GB50009 |
| 设计使用年限 | GB50352 |
| 绿色建筑等级 | GB/T50378 |

### 覆盖率是真指标

```
覆盖率 = (有 computed_from 或是其输入 或 有 bounded_by 的数值节点) / 该章数值节点总数
```

**实测：第六章 12% → 63%（补了 48 条推演边 + 40 条约束边）**

低于 50% 就要逐条问：为什么这个值没有关系？

### 剩下 37% 必须是这四类之一（否则算漏）

| 类型 | 例子 | 判据 |
|---|---|---|
| 设备铭牌参数 | 30HP 单台 100kW | 选型给定，不可推 |
| 建筑尺寸 | 60m 高 / 5m 层高 / 1 层 | 设计给定 |
| 缺明细 | 室内机 166 台（无分型号台数） | 有总数无分项，算不了 |
| 原文只给结果 | 952kW 总计算负荷 | 有结果无算式 |

### 推导节点必须标注来源

新建的合计节点不能冒充原文事实：

```yaml
id: N-ch6-a1b2c3d4e5
subject: 多联机室外机组30HP·总制冷量
value: "1980"
unit: kW
origin: derived_ch6
derived_note: "22 台 × 90 kW = 1980 kW（按台数与单台能力计算）"
```

否则下游会把它当原文里写的数引用。


## 标签体系：项目标签 + 节点标签（两层，别混）

### 为什么需要

抽取出的节点，`subject` 常常是「本项目」「该项目」——没有信息量。
没有标签时，检索只能靠数值猜，人工也看不出这个值是什么。
实测：一章 8 个数值全被挂到同一标准，因为只能靠「章节」猜归属。

### 两层标签

| 层 | 字段 | 回答 | 例子 |
|---|---|---|---|
| **项目** | `project_profile.yaml` | 这个项目是什么 | 用途=科研 · 类型=建筑 · 规模=中型 · 阶段=可研 · 专项=[高层,抗震,消防] |
| **节点** | `primary_tag`（自有） | 这个值属于哪个专业域 | `结构.地震参数` |
| **节点** | `project_tags`（继承） | 它属于什么项目 | `科研·建筑·中型·可研·高层·抗震·消防` |

**报告下面的所有节点，都继承项目标签。** 这样可跨项目做「同类项目的同类参数」对比。

### 节点必须带 desc

```
本项目 = 0.1 g ｜ §6.3.2 主要荷载取值 ｜ 受 GB50011-2010 附录A 约束
```

格式：`主体 = 值 单位 ｜ 章节标题 ｜ 用途（算出/用于/受约束）`

没有 desc 的节点等于不可读。

### 打标三条判据

1. **量纲先行**：`度`(5~9) → 结构.地震参数；`L/s` / `m³` → 给排水.消防给水；`kN/m²` → 结构.荷载
2. **标准编号定域**：条款打标时，GB50016 → 消防（不是"关键词含消防就给排水"）
3. **原文上下文兜底**：subject 无信息时，取数值在 chunk 里的 ±120 字打标

### 项目标签 → 适用标准自动推导

```yaml
用途=科研   → 建标191-2018
类型=建筑   → GB50352-2005
专项=高层   → GB50016-2014
专项=抗震   → GB50011-2010 + GB50223-2008
专项=消防   → GB50016 + GB50974 + GB50084
```

不用人工列标准清单——标签就是清单。

### MCP 工具

```
tag_text(taxonomy_path, text, std_hint)   → 给文本打标签
tag_query(library_path, domain?, topic?, code?, q?) → 按标签检索条款
```


### 与标准抽取 skill 的分工

外部规范性文件（GB/建标/条例/通知）→ **由 `standard-regulation-extraction` skill 抽成「公共标准库」**，
本 skill 只管项目内稿件。项目侧只保留 `external/references.yaml` 记录「引用了公共库哪些标准」，
不复制条款原文。

条款检索用 `tag_query`（MCP），别在项目里重建一份条款索引。


## 消歧（Disambiguation）：抽取后、冲突检测前的必做环节

### 为什么必须单独一步

实测某项目报出 **15 条「冲突」，其中 9 条根本不是冲突**，是抽取没做消歧：

| 类型 | 条数 | 症状 |
|---|---|---|
| 设备型号混淆 | 6 | 同一名称下多个规格被抽成同一 subject |
| 主体识别错 | 1 | 办公用水 35 实为教师定额 |
| 表述差异 | 2 | `≤70` vs `70`、`约2300` vs `2300` |

噪声淹没真信号：真正需要甲方拍板的只有 2 条，却混在 15 条里。

### 顺序：消歧 → 冲突检测 → 待审

```
抽取
  ↓
① 消歧（本环节）
  ↓
② 冲突检测
  ↓
③ 分类：resolved / report_fix / open
```

**跳过消歧直接检测 = 制造噪声。**

### 四类消歧

#### ① 主体消歧

症状：`subject` 是「本项目」「该项目」「本工程」——没有信息量；或主体识别错。

做法：
1. subject 为泛称 → 从 chunk 上下文（数值 ±120 字）找真实主体
2. 数值与 subject 语义不符 → 回原文核对该句主语

实测：
```
抽取结果：办公用水（288 人）· 用水定额 = 35 / 50
原文：教师 35 L/人·日、办公 50 L/人·日
修正：35 → subject 改为「教师用水定额」
```

#### ② 型号消歧

症状：同一 subject 下多个值，且分属原文表格的不同行。

做法：按**唯一且业务可读**的特征加后缀（风量 / 功率 / 表格序号）。

实测：
```
原文 §6.7.7 表：
  直膨式新风机组  制冷45/制热29.5/功率0.774/风量4000  10 台
  直膨式新风机组  制冷28/制热17.4/功率0.52 /风量2100   2 台

抽取结果：直膨式新风机组 = 45 和 = 28（同 subject → 假冲突）
修正：直膨式新风机组（风量4000m³/h）= 45
      直膨式新风机组（风量2100m³/h）= 28
```

选择标识的原则：**唯一 + 业务可读**。风量比序号好，序号比随机 id 好。

#### ③ 表述消歧

症状：同一事实被抽两次，一次带前缀一次不带。

做法：剥离前缀，原表述存 `raw_value`。

```python
PREFIX = r'^(≤|≥|约|不小于|不大于|不超过|不低于)'
n['raw_value'] = v          # "≤70"
n['value']     = "70"       # 归一化
```

实测 10 处：`≤70`/`≤55`/`≤50`/`不小于3.5`/`不小于180`/`约2300` …

归一化后 `70` 与 `≤70` 不再算冲突；但**语义不能丢**——`≤70` 是限值、`70` 是实测时不同，看 `raw_value` 判断。

#### ④ 版本消歧

症状：同一标准在报告里出现多个版本号或多种写法。

做法：查发布/废止关系，判定应使用哪版；结果标 `report_fix`（报告需修正），不是 `open`（待甲方确认）。

实测 5 条：

| 报告写法 | 应改为 | 依据 |
|---|---|---|
| 无障碍 GB50673-2002 / JGJ50-2001 | GB50763-2012 | 前者已废止 |
| 节能 DGJ08-107-2012 / GB50189-2005 | DGJ08-107-2015 | 后者已被替代 |
| 照明 GB50034-2004 | GB50034-2013 | 新版替代 |
| 暖通 GB50019-2003 | GB50736-2012 | 新版替代 |
| 建标「建筑规划面积指标」 | 「建筑面积指标」 | 前者是 2008 旧版名称 |

**这类系统能判定，不需要问甲方**——但要写进报告修正清单。

### 消歧后的冲突分类

```yaml
review_status:
  resolved:    已按证据解决（型号/表述/主体）
  report_fix:  报告需修正（系统已判定应改什么）
  open:        需甲方确认（原文自相矛盾，系统不能替其选择）
```

实测分布：`resolved 9 · report_fix 5 · open 2`

**只有 open 才真正需要人。** 从 15 条噪声里筛出 2 条真决策，这才是消歧的价值。

### 一条判据

> 消歧能做的事，不要让甲方做；
> 但**原文自相矛盾**（两个值都有出处、都无计算支撑）必须交给甲方——
> 系统替甲方选一个，等于伪造事实。


## 识别引用 → 生成待抓清单（自动触发检索的第一步）

### 为什么单独一步

报告里会引用几十个外部标准，但抓取时往往只抓了正文用到的少数几个。
实测某可研报告：**正文出现 56 个标准编号，公共库只有 12 个，缺 44 个**——
手工只发现了 6 个，正则扫出 44 个，漏了 38 个。

### 只做识别与分级，不擅自抓取

这是整条链路里**唯一可以完全自动化且无风险**的一步：

```
① 识别引用（本步）      ✅ 确定性正则，零风险
② 生成待抓清单（本步）  ✅ 按引用次数分档
③ 执行检索              ⚠️ 需要人确认源
④ 校验版本/来源/完整性   ⚠️ 必须人工把关
⑤ 抽条款                ✅ 有抽取器
⑥ 纳入公共库            ⚠️ 一旦错全项目跟着错
```

**为什么 ③④⑥ 不能全自动**：把二手转载或旧版当权威条款写进公共库，
所有引用它的项目都会跟着错。

### 识别模式

```python
PAT = re.compile(
    r"(?:GB\s*/?\s*T?\s*\d{4,5}(?:[-—]\d{4})?|JGJ\s*\d+(?:[-—]\d{4})?|"
    r"DGJ\s*[\dA-Z]+(?:[-—]\d{4})?|CJJ\s*\d+|"
    r"建标\s*[﹝〔\[]?\d{4}[﹞〕\]]?\s*\d+|"
    r"发改投资规〔\d{4}〕\d+号|发改委令第\s*\d+\s*号)")
NAME = re.compile(r"《[^》]{4,40}(?:规范|标准|指标|规定|办法|大纲|通则|规程)》")
```

**同时抽两种**：有编号的（GB50016-2014）+ 只有名称的（《建筑设计防火规范》）。
只有名称的也重要——说明作者知道该标准但没写编号，抓取时要靠名称反查。

### 三档分级（按引用次数）

| 档 | 判据 | 动作 | 实测 |
|---|---|---|---|
| **必抓** | ≥ 3 次 | 人工确认官方源后抓 | 3 个（DGJ08 13次 / GB50034 6次 / GB50189 4次） |
| **应抓** | = 2 次 | 批量抓取并抽查 | 8 个 |
| **暂缓** | = 1 次 | 只登记引用，标注未抓原文 | 33 个 |

**为什么按次数分档**：44 个全抓等于把工作量翻 3 倍，
但引用 1 次的标准对报告结论影响很小，可以先标缺口。

### 标准类型决定去哪抓（关键）

| 类型 | 编号特征 | 权威源 |
|---|---|---|
| **地方标准** | `DGJ` 开头 | **仅地方住建委官网**（其他都是转载） |
| 行业标准 | `JGJ` / `CJJ` | 住建部发布页 |
| 国家强制性 | `GB` | 标准全文库 / 官方发布页 |
| 国家推荐性 | `GB/T` | 同上 |
| 建设标准 | `建标` | 住建部 + 发改委联合发布 |
| 政策文件 | 发改投资规 / 发改委令 | 发改委公告 |

**实测踩过的坑**：DGJ08 引用 13 次（最高），但它是上海地方标准，
网上能找到大量转载，**只有上海市住建委官网发布的那份才是准的**。

### MCP 工具

```
detect_citations(chunks_path, library_path?, out_path?)
  → {summary: {cited, in_library, missing, named_only, tiers},
     tasks: [{standard, tier, type, mentions, action, caution}]}
```

### 输出示例（实测）

```yaml
summary:
  cited_standards: 56
  in_library: 12
  missing: 44
  named_only: 92
  tiers: {必抓: 3, 应抓: 8, 暂缓: 33}

tasks:
  - standard: DGJ08
    tier: 必抓
    type: 地方标准（仅地方住建委官网权威）
    mentions: 13
    sections: ["6.3", "6.4", "6.5"]
    action: 人工确认官方源后抓取
    caution: 地方标准仅地方住建委官网权威
```

### 一条铁律

> **「自动」只到「生成待抓清单」是安全的。**
> 再往后（认定权威源、判定版本、纳入公共库）必须有人确认——
> 公共库是所有项目的共同依据，错一条，所有项目跟着错。


## 表格转录 → 可判定函数：让 range_known 真正变成 true

### 为什么

条款正文拿到了，但**限值在表格里，而表格是图片**。
没有限值就只能 `range_known: false`，只能写「依据某条款，限值待核」。

实测某个标准 8 条条款正文全拿到，但 6 张表格全是图片——
真正能用的是表格里的 22 行数值，不是正文。

### 转录 → 判定函数的三步

```
① 读图转录   read_image 读表格图片 → 结构化行（不是 OCR）
② 落库       clauses.yaml 的 table 字段 + limits_extracted: true + 原图 URL
③ 写成函数   standards_check.py → check_thermal() / check_lpd()
```

**必须保留 `table_source` 与原图 URL**，让人能回查转录是否准确。

### 转录前的判断：报告有没有可比的数值

**这一步比转录更重要。** 实测踩过：

| 标准 | 表格转录 | 报告里有数值吗 | 能否判合规 |
|---|---|---|---|
| GB50189 围护结构 | ✅ 14 行传热系数限值 | ❌ 传热系数 **0 处**、窗墙比 0 处 | **不能** |
| GB50034 照明 | ✅ 4 张表 | ⚠️ 只写「按目标值设计」，无 LPD 数值 | **不能** |

**报告没给数值，转录了也只能存进公共库供未来项目用，当前项目建不了 `bounded_by`。**

所以转录前先查：报告里有没有这个参数的值？
没有 → 只记「章节级引用」，别硬造关系。

### 判定函数的三态返回

```python
check_thermal(part="屋面", k=0.35, d=2.0)
  → {"result": "PASS", "limit": 0.40, "basis": "GB50189-2015 表3.3.1-4（夏热冬冷）"}

check_thermal(part="屋面", k=0.40)          # 缺热惰性指标 D
  → {"result": "UNKNOWN", "reason": "缺少热惰性指标 D，无法判断 D≤2.5 还是 D>2.5"}

check_lpd(room="不存在房间", value=5)
  → {"result": "UNKNOWN", "reason": "GB50034 表6.3 无「不存在房间」条目"}
```

**UNKNOWN 不是失败，是缺参数或未匹配。** 不允许用近似限值凑一个 PASS/FAIL。

### 判定表怎么建

按「部位 + 条件」做键，不按「表格行号」：

```python
THERMAL_K = {
    ("屋面", "D≤2.5"): 0.40,
    ("外墙", "D≤2.5"): 0.60,
    ("外窗", "0.30<窗墙比≤0.40"): 2.6,
    ...
}

LPD = {
    ("普通办公室", "6.3.3"): (9.0, 8.0),   # (现行值, 目标值)
    ("走廊-一般", "6.3.13"): (2.5, 2.0),
    ...
}
```

**为什么用「部位 + 条件」而不是行号**：调用方知道的是「屋面 K=0.35、D=2.0」，
不知道「这是第 1 行」。键要贴近调用方的语言。

### MCP 工具

```
check_standard_limit(kind="thermal", part="屋面", k=0.35, d=2.0)
check_standard_limit(kind="lpd", room="普通办公室", value=7.5, mode="目标")
```

### 一个判断

**转录表格的价值往往不在当前项目，而在公共库。**

本次 22 行限值，当前项目一个都用不上（报告没给传热系数和 LPD），
但下次任何项目只要有传热系数，立刻能判合规——
这就是把标准提升为跨项目公共库的意义。


## 图查询：YAML 精确 vs Semantica 模糊+多跳+因果

### 两者不是替代关系

| 场景 | 用什么 | 理由 |
|---|---|---|
| 精确查「N-xxx 的 value」 | **读 YAML** | 快（~50ms），精确 |
| 模糊搜「和用水定额相关的」 | **`semantica_query(mode=search)`** | YAML 做不到 |
| 多跳遍历「依赖这条值的所有节点」 | **`semantica_query(mode=neighbors, depth=2)`** | 一条命令 |
| 按边类型筛「只要 computed_from」 | **`semantica_query(relationship_types=[...])`** | 一条命令 |
| 找「最被依赖的节点」 | **`semantica_analytics`** | pagerank |
| 追「一个冲突是不是另一个冲突的根因」 | **`semantica_causal_chain`** | BFS 因果链 |
| 全量遍历/统计 | **读 YAML** | 无启动开销 |

### 五个工具的实测边界（都是实测出来的，不是文档说的）

#### ① `semantica_query` —— 全能查询（3 模式）

```json
{
  "mode": "node | neighbors | search",
  "node_id": "完整 UUID（32位）",
  "depth": "1-5",
  "relationship_types": ["computed_from"],
  "query": "必要性",
  "node_type": "fact",
  "limit": 5
}
```

**实测**：

| 调用 | 结果 |
|---|---|
| `mode=node` | `本项目 = 95.04 m³/d` |
| `mode=neighbors depth=1` | 7 个邻居 |
| `mode=neighbors depth=3` | 8 个邻居 |
| `neighbors + relationship_types=[computed_from]` | 6 个（过滤生效） |
| `mode=search "必要性"` | 3 条 |
| `search + node_type=fact` | 1 条（过滤生效） |
| `search + node_type=claim` | 2 条 |

#### ② `semantica_node` —— 本地 ID → UUID + 邻接

```
输入 N-c67295c8a345
→ uuid / type / content / in_edges / out_edges / degree
→ in=1, out=6, degree=7
```

#### ③ `semantica_analytics` —— 含社区检测

```json
{
  "node_count": 1310,
  "edge_count": 334,
  "top_nodes_by_pagerank": [...10条],
  "community_count": 1037
}
```

**`community_count` 是个诊断指标**：社区数 ≈ 节点数说明图极稀疏（本例 0.25 边/节点，大部分节点孤立）。

#### ④ `semantica_precedents` —— 按场景找先例

```json
{"scenario": "建筑高度 49m 与 60m 两个口径", "max_results": 2}
→ 返回本项目已记录的相似 decision
```

**单项目内也能用** —— 不要求跨项目先例库。

#### ⑤ `semantica_causal_chain` —— 因果链

```json
{"decision_id": "完整 32 位 UUID", "direction": "upstream|downstream", "max_depth": 5}
```

**实测（补 4 条因果边后）**：

```
建筑高度 60vs49 → downstream
   [dist=1] 耐火等级 二级 ／ 一类高层不应低于一级
   [dist=1] 消防水箱 18 m³ ／ 不应小于 36 m³
```

### 三个必须知道的坑

#### 坑 1：ID 必须完整

```
✗ f6c1337ea1c517f2              （16 位前缀）
✓ f6c1337ea1c517f29f14fd6a3629accf  （32 位完整）
```

BFS 用 `current_id in self.nodes` 判断，**前缀匹配不上**。

#### 坑 2：因果边类型必须命中枚举

```python
_CAUSAL_TRAVERSAL_TYPES = {
    "CAUSES", "CAUSED", "INFLUENCES", "INFLUENCED",
    "PRECEDES", "PRECEDENT_FOR", "LEADS_TO", "LEAD_TO", "SUPPORTS", "SUPPORT"
}
```

**我一开始用 `causes`（小写）→ 不匹配 → chain 为空。改用 `CAUSED` 才行。**

#### 坑 3：`scenario` 为 None 的 decision 不能用关键词找

有些 decision 的 `scenario` 是 `None`，内容在 `reasoning` 里 —— 必须用 UUID 定位。

### 推入存储 ≠ 可检索（本轮最大的坑）

**1301 个节点推入 Semantica 后，`search_graph("GB50016")` 返回 0 条。**

原因：推送时缺 `content` 字段。

```python
# 错：只有 subject/value/section
props = {"subject": ..., "value": ..., "section": ...}

# 对：必须有 content（Semantica 的 search 只索引这个字段）
props = {..., "content": "本项目 = 95.04 m³/d", "label": "本项目"}
```

**修前 `GB50016` → 0 条，修后 → 2 条。**

**验证必须用真实查询，不能只数节点条数。**

同类错误还有：`content_export` 返回 `presented` 但文件没落盘。**把「接口返回成功」当成「结果正确」是反复出现的缺陷模式。**

### 因果链的价值：一个根因，三个表象

本项目实测出一条链：

```
建筑高度 60m vs 49m   ← 根因
    ├─CAUSED→ 耐火等级 二级 vs 一级
    └─CAUSED→ 消防水箱 18 m³ vs 36 m³
```

**如果高度按 49m（算得出）→ 二类高层 → 二级耐火等级成立、18m³ 水箱成立**
**如果高度按 60m（原文写）→ 一类高层 → 耐火等级应一级、水箱应 36m³**

**三个冲突共用一个根因 —— 不建因果边就看不出来。**

### 建因果边的判据

不是所有 decision 之间都有因果。能建的条件：

| 判据 | 例子 |
|---|---|
| **A 的取值决定 B 的判据** | 建筑高度 >50m → 属一类高层 → 耐火等级要求变 |
| **A 和 B 共同决定同一输出** | 定额 × 人数 → 日用水量 |
| **A 是 B 的计算输入** | 总建筑面积 → 建安工程费 |

**不能建**：两条独立的冲突、只是同一章节、同一主题。

边要带 `why` 说明理由，**不能凭主题相似就建**。

### 一条铁律

> **推入不等于可检索，检索到不等于可推理。**
>
> 三步都要验证：① 节点数对上 ② 搜得到 ③ 能跑出因果链。
> 只验证第 ① 步，等于没验证。


## 报「缺」之前：假缺四问（V2.9 核心纪律）

### 实测数据

一个项目累计报「缺」1496 个，复核后**真缺只有 345 个 —— 假缺率 77%**。

| 报的问题 | 报的数量 | 真缺 | 根因 |
|---|---|---|---|
| 关系缺证据 | 190 | **2** | 只查 `relation.source`，没查 `cites`/`supports`/`computed_from`/`anchor` |
| 模糊引用 | 48 | **4** | 缺四层过滤（警示语 29 / 同句有编号 8 / 后接书名号 4 / 规范内部互引 3）|
| 条款必填缺失 | 131 | **0** | 字段别名不认（`clause`↔`clause_no`）+ 表格条款视为无原文 |
| 推演必填缺失 | 75 | **0** | `not payload.get(k)` 把 `range_known=False` 当缺失 |
| 缺依赖规则 | 42 | **12** | 绑定漏 11 + 值没抽 8 + 表格没解析 6 + 顿号 3 + 绑错 2 |
| 孤儿节点 | 1010 | **327** | `'None'` 字符串 343 + 描述性无关系 + 实体值没抽 + 证据没建边 |

**假缺的代价**：编制方看到 190 条「缺证据」，会认为系统在乱报，整份缺陷册失去可信度。

### 四问（每一问都要留证据）

报任何「缺」之前，按顺序过四问：

#### 第一问：节点真的不存在？

```
✗ 只看 subject 精确匹配就判缺
✓ 三种方式都搜过才算：
   ① 精确匹配 subject
   ② 包含匹配（注意：包含匹配会误中相邻节点，见第三问）
   ③ 去掉顿号/逗号/括号后匹配
      （实测：规则写「通风空调工程」，原文表写「通风、空调工程」）
```

**本项目实测**：11 条「缺依赖」的节点早就在 `nodes.yaml` 里，`node` 字段是 `null` 而已。

#### 第二问：原文真的没有？

```
✗ 只搜 chunks 的纯文本
✓ 四种载体都要搜：
   ① 纯文本段落
   ② markdown 表格（表头是列名，值在表体）
   ③ 表格注（「（一+二）×5%」这种在注释里）
   ④ 跨节引用（本节没有，但他节定义）
```

**本项目实测**：
- 6 条依赖的值在**表格**里（`单位面积冷负荷指标 135 W/m²`）
- 1 条费率在**表注**里（`基本预备费 = (一+二)×5%`）
- 3 条变量名与表内行名**差个顿号**

#### 第三问：绑对了节点吗？

```
✗ 主体包含匹配（「基本预备费费率」包含「基本预备费」→ 绑到 618 万元）
✓ 三道校验：
   ① 量纲校验：费率/系数/指标/比例 结尾的依赖，单位不能是万元/元
   ② 章节校验：同章节优先
   ③ 主体长度：取最长匹配（最具体）
```

**本项目实测**：`基本预备费费率` 绑到 `基本预备费 = 618 万元`，
表达式算出 **76378.62**（应为 618）—— 差 123 倍。

#### 第四问：设计上就不该有？

```
有些「孤儿」是正常的：
  · 报告编号、编者、单位名 → 描述性事实，不需要关系
  · META 章节的元信息 → 无正文原文
  · 判定项（规定性指标）→ 不是数值依赖
```

**本项目实测**：1010 个孤儿里 327 个才需处理，
其余是描述性事实（`本报告 = 2019ZX054`、`本项目 = 上海财经大学`）。

### 报缺的输出格式（强制）

```yaml
- missing: 增容后变压器容量
  why_real: ① 节点表搜过（精确/包含/归一三方式）无 ② 原文 §6.5.2 搜「增容」「变压器」只有原容量 2×1000kVA ③ 非表格值 ④ 是数值依赖不是判定项
  searched: ["nodes.yaml: subject 精确+包含+归一", "chunks: 增容|变压器|kVA", "tables: §6.5.2 全部表"]
  conclusion: 真缺，报告未给，需甲方补充或按规范估算
```

**没有 `searched` 字段的「缺」，不许进台账。**

### 一条铁律

> **宁可少报一个真缺，不要多报十个假缺。**
>
> 假缺会让整份审计失去可信度 —— 编制方发现第一个假缺后，
> 就不再相信后面 189 条。

## 改动影响面：改前必列（V2.9）

### 实测教训

改了一个判定标准，只改了「用户问到的那一个 skill」，**受影响的整条链没动**。

| 事件 | 上游改了 | 下游没跟上 |
|---|---|---|
| claim 判据变（68→19） | claim-extraction | fact-extraction / claim-validation / claim-evidence-binding |
| 证据分级变（E1→E0~E6） | evidence-extraction | claim-evidence-binding / graph-deductive-writing |
| `content_export` 返回 presented | — | **文件没落盘** |
| Semantica 推了 1301 节点 | — | **缺 `content` 字段，全搜不到** |
| skill SKILL.md 改了 | — | **7 个 references + 1 个 script 没改** |
| skill 改了 | — | **119 节提示词生成器没改** |

### 改前必列的三张表

#### 表一：谁依赖这个判定标准

```
改 claim 判据
  → claim-extraction（判据来源）
  → fact-extraction（改判的 49 条去哪）
  → claim-validation（falsifiable_by）
  → claim-evidence-binding（证据级别）
  → graph-deductive-writing（句式选择）
  → feasibility-report-edu-research（写作口径）
```

#### 表二：改 schema 后谁要跟着改

```
改 nodes.yaml 字段
  → relations.yaml 的引用
  → 前端 console.*.js 的读取
  → MCP 工具的 inputSchema
  → validate_*.py 的校验
  → 写作提示词的模板
```

#### 表三：改生成器后要重新生成什么

```
改 build_writing_prompts.py
  → 重跑生成 119 节
  → 抽查 3 节确认新字段进去
  → 对比新旧差异
```

### 改动后的自检清单

```
□ skill 改了 → references/ + scripts/ + assets/ 是否同步？
□ 生成器改了 → 产物重新生成了吗？抽查了吗？
□ schema 改了 → 所有 consumer 改了吗？
□ 数据改了 → 校验脚本跑了吗？0 错吗？
□ 声明改了 → 有 dispatch 吗？实测过吗？
```

### 一条铁律

> **改动不是「改一个文件」，是「改一条链」。**
>
> 改完必须回答：哪些东西依赖它？它们都改了吗？改完验证过吗？

## 命名归一化：差一个顿号就判缺

### 实测

| 规则变量名 | 原文表写法 | 匹配结果 |
|---|---|---|
| `通风空调工程` | **`通风、空调工程`** | ❌ 纯字符串匹配失败 |
| `道路广场硬地铺装` | **`道路、广场、硬地、铺装`** | ❌ |
| `绿化景观` | **`绿化、景观`** | ❌ |

**三条「缺依赖」全是顿号导致的。**

### 归一化函数

```python
def norm(s):
    return re.sub(r"[、,，\s（）()]", "", str(s))
# 比较前两边都归一
```

### 但归一后要防误中

```
归一后「空调」会匹配到「通风、空调工程」
→ 必须配「取最长匹配」+「同章节优先」
```

### 别名表（跨项目复用）

```yaml
aliases:
  通风空调工程: [通风、空调工程, 通风空调, 空调通风]
  道路广场硬地铺装: [道路、广场、硬地、铺装, 道路广场, 室外道路]
  绿化景观: [绿化、景观, 绿化, 景观绿化]
```

**别名表是资产，跨项目复用。** 每次遇到新写法就补进去。
