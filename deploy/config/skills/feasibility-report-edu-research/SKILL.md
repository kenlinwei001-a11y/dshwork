---
name: feasibility-report-edu-research
description: "编制、审校、修订【高校科研用房】类可行性研究报告（最终交付 Word/.docx），以发改投资规〔2023〕304 号大纲为基准，本体图谱驱动：事实单源、跨章自动传播、论断绑定证据、法定章节校验、改稿反向回读。触发：科研楼可研/实验楼立项/研究中心可行性研究/科研用房规模论证/建标191-2018，或上传科研用房可研要写改审、按2023大纲改口径时。不适用：学生宿舍食堂、教学楼图书馆、产业园区厂房、施工图、招标文件。"
---

# 可行性研究报告本体图谱 · 高校科研用房

## 交付物

**一份 .docx**，按发改投资规〔2023〕304号（10 章 41 节）。
详细格式见 `references/交付物规范.md`。

## 何时使用

- 调用条件：项目基本信息（建设单位/地点/规模/投资口径）、已有批复或前期材料、目标大纲版本齐备。
- 典型请求：科研楼可研｜实验楼立项｜研究中心可行性研究｜科研用房规模论证（建标 191-2018）｜按 2023 新大纲改口径｜审阅可研并核查数字矛盾。
- 不要在此调用：学生宿舍与食堂、教学楼图书馆、产业园区厂房、施工图设计、招标文件编制。

## 适用范围（已下沉）

见 `references/适用与不适用.md`。**一句话**：只做高校科研用房类可研
（研究中心 / 实验室 / 交叉平台 / 中试基地）；学生宿舍、教学楼、厂房不在范围。

## 五条硬规则

**① 法定基准是发改投资规〔2023〕304号。** 不是任何一份样板报告，也不是客户手上的旧模板。样本可以是错的，法定大纲不能不覆盖。政府投资项目适用《通用大纲》（强制），企业投资项目适用《参考大纲》（参考）。每个垂类必须 `extends` 其中一本。

**② 单一事实源。** 任何事实在图中只存在一份，正文永远是引用而非复制。渲染时注入，不复制粘贴。

**③ 可派生的量不许人工录入。** 总投资是算出来的，不是填出来的。允许手填派生值，等于允许图与正文脱节。

**④ 不得编造。** 没有素材依据、也没有客户答复的量，一律保持 UNKNOWN。不估算、不套用同类项目、不写"暂按经验值"、不用行业均值填坑。凡入图必带 `from`（素材 id + 页码/表号），带不出 `from` 的就不入图——这是这条规则唯一可机检的部分（C8）。禁令清单见 `references/materials.yaml → no_fabrication`。

**⑤ 事实没确认就不写正文。** 宁可空着并说明"待 X 确认后生成"，也不要先写一版占位文字。占位文字会被当成初稿，被润色，然后被遗忘——更要命的是，客户看到通顺的段落就会去改句子，而不是纠正数字。

## 来源路由（已下沉）

见 `references/来源路由.md`。摘要：每类信息标注来源类型（客户给 / 可检索 /
可推导 / 需判断），决定它能不能问客户、能不能自己查。

## 工作方式：状态机，不是流水线（已下沉）

见 `references/工作方式-状态机.md`。摘要：章节间有依赖，前章未定稿不写后章；
改写任一章要回检下游。

## 四道闸门（已下沉）

见 `references/四道闸门.md`。摘要：契约闸 → 证据闸 → 覆盖闸 → 一致性闸，
任一不过不出稿。

## 执行流程（四段式：契约 / 执行 / 门禁 / 代价）

> **为什么不用自然语言写步骤**：实测把「写作要按证据强度选句式」写成散文，
> 结果 hypothesis 写成既成事实、`range_known=false` 写成「符合规范」；
> 写成断言后一跑就定位。**纪律靠提醒，机制靠退出码。**

---

### 工序 1 · 素材摄入

> **本工序的方法在「素材摄入：客户交来一堆材料之后」一节**（intake_scan.py、
> 四样输出、追料三档时钟、S1–S4 出口）。本节只加**可校验的契约**与**两条增量断言**，
> 不重复那边的流程说明。

**契约**（新增：让「素材台账」可机器校验）

```json
{
  "intake": {"required": ["docs", "dedup_report"],
             "docs": {"items": {"required": ["id", "m_class", "pages", "text_hash"],
                                "m_class": {"description": "M1批复/M2规划用地/M3设计/M4造价财务/M5施工/M6基础资料/M7专项评估/M8规范"}}},
             "dedup_report": {"required": ["kept", "dropped", "basis"]}}
}
```

**执行**

```python
# 主体流程走原有脚本
#   python3 scripts/intake_scan.py project.yaml
# 本节只加两条断言（原有流程没覆盖的）
def assert_intake_quality(docs) -> None:
    # ① 每份素材要有内容指纹 —— 否则同一份材料发三次会被当三份证据
    assert all(d.get("text_hash") for d in docs), "有素材缺内容指纹，无法去重"
    # ② 同指纹必须已去重并留痕
    seen, dup = set(), []
    for d in docs:
        if d["text_hash"] in seen: dup.append(d["id"])
        seen.add(d["text_hash"])
    assert not dup, f"仍有未去重的重复素材：{dup}"
```

**门禁 F1 · 素材台账可溯**（增量，原有四样输出仍照跑）

```
原有：台账 / 缺哪几类（含追料话术）/ 指不回具体页的取值 / ASK-SEARCH-COMPUTE-WITHHOLD 路由
增量：① 每份有 m_class + text_hash ② 同指纹已去并留痕（防同一份材料被当多份证据）
```

**代价（实测）**

```
同一份图纸被客户发了三次（pdf / 扫描 / pdf转图）
→ 三份都当独立证据 → 证据量虚高 3 倍
→ 加 text_hash 后去重，发现是同一份内容
```

### 工序 2 · 来源路由

**契约**

```json
{
  "routed_fact": {"required": ["subject", "value", "source_kind", "provider"],
                  "source_kind": {"enum": ["E0", "E1", "E2", "E3", "E4", "E5", "E6"]},
                  "provider": {"description": "E1 必填：谁给的、什么时候、哪一版"}}
}
```

**执行**

```python
def route(fact, docs) -> dict:
    """每条信息必须说清「从哪来」，不许默认 E1"""
    kind = classify_source(fact)
    if kind == "E1":
        assert fact.get("provider") and fact.get("provide_date") and fact.get("version"), \
            f"{fact['subject']} 标 E1 但缺 provider/date/version"
    return {**fact, "source_kind": kind}

assert all(f["source_kind"] for f in facts), "有事实没标来源等级"
```

**门禁 F2 · 来源等级**

```
每条事实有 E0~E6；E1 必须带 provider / provide_date / version；缺一即降级或标 unknown
```

> **与「来源路由」一节的区别**（两个维度，都要过）：
> 路由（ASK/SEARCH/COMPUTE/WRITE/WITHHOLD）管**去哪拿**；
> 等级（E0~E6）管**拿到后有多可信**。
> 例：某数走了 ASK 路由拿到 → 等级是 E1，还必须带 provider/date/version；
> 同一数若走 COMPUTE 算出 → 等级是 E4，必须带可复算算式。

**代价（实测）**

```
31 条标 E1 的证据全部缺 provider/date/version
→ 说明 E1 是「默认值」不是「判断结果」
→ 重分为 E0×7 / E1×15 / E3×15 / E4×8 / hypothesis×5
```

---

### 工序 3 · 建设规模论证

**契约**

```json
{
  "scale": {"required": ["recipe", "inputs", "result", "basis"],
            "basis": {"description": "指标依据：建标191-2018 表/条 + 是否拿到原文"}}
}
```

**执行**

```python
def compute_scale(recipe, inputs) -> dict:
    need = sum(n * quota for n, quota in inputs["people_quota_pairs"])
    need += inputs["support_area"]
    assert all(i.get("basis") for i in inputs["quotas"]), "每个人均指标要有依据"
    return {"result": need, "basis": inputs["quotas"],
            "range_known": all(i.get("clause_verified") for i in inputs["quotas"])}
```

**门禁 F3 · 规模可复算**

```
规模算式可复算；每个人均指标带依据（标准号+条款号）；未拿到原文标 range_known=false
```

**代价（实测）**

```
人均面积指标 16㎡/人（科研）/8㎡/人（研究生）—— 建标191 原文未抓到
→ 只能写「参考建标191 指标」，不能写「符合指标」
→ 规划 18040㎡ vs 实际 18000㎡，差 40㎡，判「规模合理」需说明依据
```

---

### 工序 4 · 投资估算

**契约**

```json
{
  "estimate": {"required": ["items", "total", "closing_check"],
               "items": {"items": {"required": ["name", "area", "unit_price", "amount"]}},
               "closing_check": {"required": ["subtotal_sum", "stated_total", "diff"]}}
}
```

**执行**

```python
def estimate(items) -> dict:
    for it in items:
        if it.get("area") and it.get("unit_price"):
            calc = it["area"] * it["unit_price"] / 10000
            assert abs(calc - it["amount"]) < 2, \
                f"{it['name']} 单价×面积={calc} ≠ 金额={it['amount']}"
    total = sum(i["amount"] for i in items)
    return {"total": total, "closing_check": {...}}

assert abs(total - stated_total) < 1, "构成合计与报告总投资不符"
```

**门禁 F4 · 投资闭合**

```
① 每个分项：单价 × 面积 = 金额（±2 万元容差）
② 构成合计 = 报告总投资
③ 两套口径（投资估算 / 招标估算）不得混用
```

**代价（实测）**

```
建安工程费用绑了招标估算 10135，应绑投资估算 11188
→ 10135+1171+618+55 = 11979 ≠ 13032（差 1053）
→ 换 11188 后 = 13032 完全一致（11/11 分项单价×面积全部对平）
```

---

### 工序 5 · 论断分级与写作

**契约**

```json
{
  "claim_out": {"required": ["id", "claim_type", "falsifiable_by", "evidence_strength"],
                "claim_type": {"enum": ["conclusion", "recommendation", "hypothesis", "inference"]},
                "evidence_strength": {"enum": ["SUPPORT", "PARTIAL_SUPPORT", "CONTRADICT",
                                               "CONTEXT", "INSUFFICIENT"]}}
}
```

**执行**

```python
def write(claim, evidence) -> str:
    st = classify(claim, evidence)
    if st in ("CONTRADICT", "INSUFFICIENT"):
        return f"{claim['text']}（依据待补：{claim['falsifiable_by']}）"
    if claim["claim_type"] == "recommendation":
        return f"建议{claim['text']}"
    if claim["claim_type"] == "hypothesis":
        return f"若{claim['condition']}，则{claim['text']}"      # 不许写成既成事实
    return claim["text"]

# 硬检查（文本包含，不用 LLM 判定）
for c in claims:
    if c["claim_type"] == "hypothesis":
        assert "若" in md or "预计" in md, "hypothesis 写成既成事实"
    if c["claim_type"] == "recommendation":
        assert "建议" in md, "recommendation 未写成建议句"
```

**门禁 F5 · 论断句式**

```
hypothesis 必须含「若」或「预计」；recommendation 必须含「建议」；
INSUFFICIENT 只能写「依据待补」，不得写「综上所述」
```

**代价（实测）**

```
必要性 4 条前提，3 条有依据、1 条断点
→ 仍写「综上所述，项目建设十分必要」
→ 评审一查即破
```

---

### 工序 6 · 冲突呈现

**契约**

```json
{
  "conflict_out": {"required": ["subject", "values", "root_cause", "action"],
                   "root_cause": {"description": "若有因果链，写根因；无则写「无共同上游」"}}
}
```

**执行**

```python
def present(conflicts) -> str:
    """按根因分组，不并列罗列"""
    groups = group_by_root_cause(conflicts)     # 读 CAUSED / INFLUENCED 边
    out = []
    for root, children in groups.items():
        out.append(f"【根因】{root}")
        for c in children:
            out.append(f"  · {c['subject']}：{c['values'][0]} vs {c['values'][1]}")
        out.append(f"【处置】{decide_action(children)}")
    return "\n".join(out)
```

**门禁 F6 · 冲突按根因**

```
同一根因派生的冲突必须在同一节呈现，不许分散；每条冲突不得裁决，只标待审
```

**代价（实测）**

```
建筑高度 60 vs 49、耐火等级二级 vs 一级、消防水箱 18 vs 36
→ 并列写三条「待审」，读者看不出「先解决高度，另两条自动消解」
→ 建 CAUSED 边后可按根因组织
```

---

**（F7 已合并进 G4 出稿：G4 的放行条件就是 F1–F6 全绿 + C1–C7 全绿 + 裁决留痕）**

## 脚本（已下沉）

见 `references/脚本清单.md`。摘要：17 个 scripts/ 的用途与调用方式；
**只在需要跑批处理时读**，正常写作不涉及。

## 边界声明

要向客户讲清楚：本 skill **不对任何数值的准确性负责**。造价单价、人均指标、能耗基准由客户或造价方提供，我们保证的是——法定内容不遗漏、事实在全文传播中不矛盾、每条论断都能追溯到证据、变更影响可见。判断造价高不高、人数合不合理，不在保证范围内。

同时也要讲清楚**我们保证不做什么**：不替客户估数、不拿同类项目的数填本项目的空、不代拟第三方结论、不自行采纳外部政策。材料缺到哪里，报告就空到哪里，并写明空的原因和找谁要。

## 资源导航（素材摄入、章节写作细节、论证与证据规则已下沉 references/）

- `references/写作细节.md` — 16 节
## 边界与不适用

- 不做：不替客户估数；不拿同类项目数值填本项目空；不代拟第三方结论；不自行采纳外部政策。
- 不保证：造价单价、人均指标、能耗基准的准确性（由客户或造价方提供），也不判断造价高低、人数是否合理。
- 保证：法定章节不遗漏、事实跨章传播不矛盾、每条论断可溯源、客户改稿影响可见。
- 缺输入：材料缺到哪，报告就空到哪，并写明缺什么、向谁要；不得用假设补齐。
