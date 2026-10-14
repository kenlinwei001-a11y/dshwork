# -*- coding: utf-8 -*-
"""生成「装配输入包」单文件 MD：事实输入（借值）+ 依据层（外部检索文件）+ 章节装配表 + 写作纪律。

面向下游「推演写作专家」：与知识资产域（reuse/domains/，借形）装配后，还原写作本报告。
确定性：所有内容从语料包读回并按固定顺序渲染，同输入同输出。
"""
import json
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
OUT = WS / "交付物" / "装配输入包-报告还原.md"
OUT.parent.mkdir(parents=True, exist_ok=True)


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


nodes = J(ROOT / "graph" / "nodes.yaml")
rules = J(ROOT / "graph" / "rules.yaml")
claims = J(ROOT / "graph" / "claims.yaml")
relations = J(ROOT / "graph" / "relations.yaml")
evidence = J(ROOT / "evidence" / "evidence.yaml")
outline = J(ROOT / "outline.yaml")
manifest = J(ROOT / "manifest.yaml")
meta = J(ROOT / "meta.yaml")
conflicts = J(ROOT / "quality" / "conflicts.yaml")
gaps = J(ROOT / "quality" / "gaps.yaml")
derivation = J(ROOT / "reasoning" / "derivation.yaml")
judgements = J(ROOT / "reasoning" / "judgements.yaml")
terms = J(ROOT / "index" / "term_index.json")
domains = J(ROOT / "reuse" / "domains.yaml")["domains"]
EXT_DOCS = J(ROOT / "external" / "documents.yaml")["documents"]
EXT_MANDATES = J(ROOT / "external" / "mandates.yaml")["mandates"]
EXT_CONSTRAINTS = J(ROOT / "external" / "constraints.yaml")["constraints"]
EXT_BINDINGS = J(ROOT / "external" / "bindings.yaml")["bindings"]
COMPLIANCE = J(ROOT / "external" / "compliance.yaml")
SEC_PROMPTS = J(ROOT / "style" / "section_prompts.yaml")
REG_DEP = J(ROOT / "reuse" / "regulatory_dependency.yaml")
SP_BY_CH = {x["chapter"]: x for x in SEC_PROMPTS["sections"]}
chunks = [json.loads(l) for l in (ROOT / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
chunk_by_id = {c["id"]: c for c in chunks}

# 事实的原文定位（locator / verbatim）来自语义抽取产物
FACT_META = {}
for p in sorted((BUILD / "extractions-clean").glob("*.json")):
    for u in json.loads(p.read_text(encoding="utf-8")):
        for f in u.get("facts", []):
            FACT_META[(str(f.get("subject")), str(f.get("predicate")), str(f.get("value")))] = \
                {"locator": (f.get("from") or {}).get("locator", ""),
                 "verbatim": (f.get("from") or {}).get("verbatim", "")}

CURATED_EV = [e for e in evidence if str(e.get("id", "")).startswith("EV-")]
AUTO_EV = [e for e in evidence if not str(e.get("id", "")).startswith("EV-")]
EV_BY_ID = {e["id"]: e for e in CURATED_EV}

# 顶层章节归属（node → 章节）
L1 = [s["title"] for s in outline["sections"] if s["level"] == 1]


def chapter_of(chunk_id):
    c = chunk_by_id.get(chunk_id)
    if not c:
        return "（未归属）"
    sp = c.get("section_path") or []
    return sp[0] if sp else "（未归属）"


def section_of(chunk_id):
    c = chunk_by_id.get(chunk_id)
    if not c:
        return ""
    sp = c.get("section_path") or []
    return " / ".join(sp[1:]) if len(sp) > 1 else ""


for n in nodes:
    n["_chapter"] = chapter_of(n.get("source", ""))
    n["_section"] = section_of(n.get("source", ""))

# 同一 (主体,属性,值,时间) → 同一节点 ID；在多处陈述会产生多条同 ID 记录
from collections import Counter as _C  # noqa: E402

OCC = _C(n["id"] for n in nodes)
UNIQUE_NODES = len(OCC)
NODES_SEEN_IN_CHAPTERS = {}   # 节点 → 出现过的章节数（跨章重复的直接体现）
for n in nodes:
    NODES_SEEN_IN_CHAPTERS.setdefault(n["id"], set()).add(n["_chapter"])
MULTI_CHAPTER = sorted([(nid, len(chs)) for nid, chs in NODES_SEEN_IN_CHAPTERS.items() if len(chs) > 1],
                       key=lambda x: -x[1])

CHAPTERS = L1 + ["（未归属）"]
L = []
A = L.append

# ══════════════════════════════════════════════════════════════════ 头
A("# 装配输入包 · 报告还原")
A("")
A("> **上海财经大学中山北一路校区大数据研究中心 可行性研究报告（修订版）**")
A("> 用途：交给「推演写作专家」，与**知识资产域**装配后，还原写作本报告。")
A("")
A("| 项 | 值 |")
A("|----|----|")
A(f"| 语料包 ID | `{manifest['corpus_id']}` |")
A(f"| 版本 / 状态 | `{manifest['version']}` / **{manifest['status']}** |")
A(f"| 原稿 sha256 | `{manifest.get('source_original_sha256','')}` |")
A(f"| 文档类型 | {manifest.get('doc_type','')} |")
A(f"| 编制单位 / 日期 | {meta.get('title','')} ｜ {meta.get('data_cutoff','2019年8月')} |")
A(f"| 事实节点（唯一）/ 陈述次数 | {UNIQUE_NODES} / {len(nodes)} |")
A(f"| 规则 / 论断 / 证据 | {len(rules)} / {len(claims)} / {len(CURATED_EV)} |")
A(f"| 跨章重复陈述的节点 | {len(MULTI_CHAPTER)} 个（最多跨 {MULTI_CHAPTER[0][1] if MULTI_CHAPTER else 0} 章） |")
A(f"| 依据文件 / 条款 / 约束 / 绑定 | {len(EXT_DOCS)} / {len(EXT_MANDATES)} / {len(EXT_CONSTRAINTS)} / {len(EXT_BINDINGS)} |")
A(f"| 章节（docx 标题样式） | {len(outline['sections'])} 个标题 / {len(L1)} 个一级章 |")
A(f"| 待审冲突 / 显式缺口 | {len(conflicts)} / {len(gaps)} |")
A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 0 使用说明
A("## 0. 使用说明")
A("")
A("### 0.1 输入构成：借形 + 借值")
A("")
A("| 来源 | 管什么 | 位置 |")
A("|------|--------|------|")
A("| **知识资产域（借形）** | 结构 / 规则 / 关系 / 口径 / 术语 / 句式 / 模板 | `SHUFE-BDC-2019-001/reuse/domains/`（16 域，每域一文件，索引 `reuse/domains.yaml`） |")
A("| **本文件（借值）** | 本项目的事实输入、规则实例、论断与证据、依据层 | 本文件 |")
A("| **原文切片（按需检索）** | 需要逐字原文时才取，不进起草上下文 | `chunks/chunks.jsonl`（报告）/ `external/chunks.jsonl`（依据） |")
A("| **脱敏骨架（可选）** | 数值已替换为 `{{node:Nxx}}`，用于结构参照 | `chunks/skeletons.jsonl` |")
A("")
A("### 0.2 装配步骤")
A("")
A("1. **读资产域**：按 `reuse/domains.yaml` 的 `depends_on` 拓扑顺序加载 16 域，得到章节模板、规则形态、关系类型、质量闸门；")
A("2. **读本文件**：把 §3 事实输入载入项目变量表，§4 规则实例化，§5 论断建论证图，§6 依据挂到对应章节；")
A("3. **建章节骨架**：按 §2 与 §7 生成章节树，逐章核销法定内容项；")
A("4. **逐章起草**：正文里的每个数字只写 `{{node:N-xxxxxxxxxxxx}}`（见 §0.3 第 1 条）；")
A("5. **回读校验**：把成稿反向回读为节点，与本文件 §3 比对；不一致项按 §8 处理。")
A("")
A("### 0.3 写作硬纪律（不得违反）")
A("")
A("1. **数字只写占位符**：正文与表格中不得出现手打数字，一律写 `{{node:N-xxxxxxxxxxxx}}`（如 `{{N-8f432cf2e264}}`），由装配侧注入本文件 §3 的值；")
A("2. **冲突一律待审**：§8 的并列取值**不得自行裁决、不得取其一、不得改数**，按「待审」原样呈现并给出并列值；")
A("3. **缺值不编造**：§9 的缺口在正文中显式留白（写「待 X 确认后生成」），不估算、不套用同类项目、不写「暂按经验值」；")
A("4. **规范版本不臆断**：引用规范一律用 §6 中的条款与状态；`status` 标注为「未核实/二手转录」的，正文须同步标注；")
A("5. **派生值不手填**：§4 中标为 `compute` 的量必须由规则算出，不得直接录入；")
A("6. **依据不足不下判定**：§6.4 结论为「待核查」的项，正文写明缺哪份原文，不得用沾边内容顶上；")
A("7. **论证六元组写全**：§5 中 `toulmin.warrant` 为空的论断，正文不得替它补一个保证——宁可标注「保证未给出」；")
A("8. **写法不可退化为通用条款**：凡 §7 中列出的「取值点」，正文必须给出具体取值与依据，不得写「满足规范要求」。")
A("")
A("### 0.4 不变量（装配后自检）")
A("")
for inv in ["同一 (主题, 属性) 的数值必须一致", "关系两端必须指向存在的节点", "论断的证据引用必须存在",
            "冲突只呈现待审、不自动裁决", "UNDEFINED 不得填 0、不得估值",
            "依赖存在未裁决冲突时，派生校核阻塞而非取一值硬算"]:
    A(f"- {inv}")
A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 1 项目元信息
A("## 1. 项目元信息")
A("")
A("```yaml")
A("project:")
keys = ["项目名称", "建设单位", "建设地点", "建设性质", "资金来源", "开工时间", "竣工时间", "建设工期"]
for k in keys:
    for n in nodes:
        if n["subject"] == "本项目" and n["predicate"] == k:
            v = f"{n['value']} {n['unit']}".strip()
            A(f"  {k}: \"{v}\"   # {n['id']}")
            break
A("report_identity:")
for k in ["报告编号", "文件全称", "编制单位", "项目负责人", "项目审核人", "主要编制人", "编制日期"]:
    for n in nodes:
        if n["subject"] == "本报告" and n["predicate"] == k:
            A(f"  {k}: \"{n['value']}\"   # {n['id']}")
            break
A("owner_unit:")
for n in nodes:
    if n["subject"] == "上海财经大学" and n["predicate"] in ("校园占地", "校区数量"):
        A(f"  {n['predicate']}: {n['value']} {n['unit']}   # {n['id']}")
A("```")
A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 2 法定大纲与结构
A("## 2. 法定大纲与本报告结构")
A("")
A("### 2.1 法定大纲（发改投资规〔2023〕304号《政府投资项目可行性研究报告编写通用大纲》）")
A("")
A("| # | 法定章 | 法定内容项 | 本报告对应 |")
A("|---|--------|-----------|-----------|")
MUST = [("概述", ["项目概况", "项目单位概况", "编制依据", "主要结论和建议"], "总论"),
        ("项目建设背景和必要性", ["项目建设背景", "规划政策符合性", "项目建设必要性"], "项目建设背景及必要性分析"),
        ("项目需求分析与产出方案", ["需求分析", "建设内容和规模", "项目产出方案"], "项目建设内容及规模"),
        ("项目选址与要素保障", ["项目选址或选线", "项目建设条件", "要素保障分析"], "项目选址及建设条件"),
        ("项目建设方案", ["技术方案", "设备方案", "工程方案", "数字化方案", "建设管理方案"], "项目规划设计方案 / 节能设计"),
        ("项目运营方案", ["运营模式选择", "运营组织方案", "安全保障方案", "绩效管理方案"], "（缺独立章，散见 项目管理及实施进度）"),
        ("项目投融资与财务方案", ["投资估算", "盈利能力分析", "融资方案", "债务清偿能力分析", "财务可持续性分析"], "投资估算及资金筹措"),
        ("项目影响效果分析", ["经济影响分析", "社会影响分析", "资源和能源利用效果分析", "碳达峰碳中和分析"], "环境影响评价 / 社会效益"),
        ("项目风险管控方案", ["风险识别与评价", "风险管控方案", "风险应急预案"], "社会稳定风险分析"),
        ("研究结论及建议", ["主要研究结论", "问题与建议"], "结论与建议")]
for i, (ch, items, rep) in enumerate(MUST, 1):
    A(f"| {i} | {ch} | {'、'.join(items)} | {rep} |")
A("")
A("> 本报告编制于 2019 年 8 月，早于 2023 版大纲。**还原写作时按哪个大纲，须由客户确认资金性质与报审时点**；")
A("> 若按现行大纲，须补齐上表「本报告对应」为空或不足的内容项（详见 §6.4 的 B-14 判定）。")
A("")
A("### 2.2 本报告实际章节结构（源自 docx 标题样式）")
A("")
A("```")
for s in outline["sections"]:
    if s["level"] == 1:
        A(f"# {s['title']}")
    elif s["level"] == 2:
        A(f"  ## {s['title']}")
A("```")
A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 3 事实输入
A("## 3. 事实输入（Fact Input）")
A("")
A(f"共 **{UNIQUE_NODES}** 个唯一事实节点（{len(nodes)} 次陈述），按来源章节归组。")
A("")
A("**列义**：`节点ID` 是正文占位符的唯一键；`主题`/`属性` 构成一致性检查键（同键异值即冲突）；")
A("`全篇出现` 是该事实被陈述的处数（空表示仅一处）；`定位` 指回原报告的表号/条号，可按需检索 "
  "`chunks/chunks.jsonl` 取逐字原文。")
A("")
A(f"**跨章重复陈述的节点共 {len(MULTI_CHAPTER)} 个**——这正是本类报告「改一处要改十处」的根因：")
A("同一事实在多个章节以自然语言表述出现，人工改稿时记不住另外十处。写作时这些量一律写占位符，由装配侧统一注入。")
A("")
if MULTI_CHAPTER:
    A("| 节点ID | 主题 · 属性 | 出现处数 | 跨章数 | 涉及章节 |")
    A("|--------|-------------|----------|--------|----------|")
    for nid, nch in MULTI_CHAPTER[:15]:
        n0 = next(x for x in nodes if x["id"] == nid)
        chs = sorted(NODES_SEEN_IN_CHAPTERS[nid])
        A(f"| `{nid}` | {n0['subject']} · {n0['predicate']} | {OCC[nid]} | {nch} | {'、'.join(chs)} |")
    A("")
A("")
for ch in CHAPTERS:
    sub = [n for n in nodes if n["_chapter"] == ch]
    if not sub:
        continue
    # 同一 ID 可能在多章重复出现（同一事实被多处陈述）——按 ID 去重，并给出全篇出现次数
    seen, rows = set(), []
    for n in sorted(sub, key=lambda x: (x["subject"], x["predicate"], str(x["value"]))):
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        rows.append(n)
    A(f"### 3.{CHAPTERS.index(ch)+1} {ch}（{len(rows)} 个事实 / {len(sub)} 次陈述）")
    A("")
    A("| 节点ID | 主题 | 属性 | 值 | 单位 | 类型 | 全篇出现 | 定位 |")
    A("|--------|------|------|----|------|------|----------|------|")
    for n in rows:
        fm = FACT_META.get((n["subject"], n["predicate"], str(n["value"])), {})
        loc = fm.get("locator", "") or n["_section"]
        val = str(n["value"]).replace("|", "\\|")
        if len(val) > 90:
            val = val[:88] + "…"
        occ = OCC.get(n["id"], 1)
        A(f"| `{n['id']}` | {n['subject']} | {n['predicate']} | {val} | {n['unit']} | {n['kind']} | "
          f"{occ if occ > 1 else '—'} | {loc} |")
    A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 4 规则
INF = {d["rule"]: d for d in derivation["derivation_diff"]}
CLOSED = {d["rule"] for d in derivation["closure_ok"]}
NOSTATED = {d["rule"] for d in derivation.get("derivation_nostated", [])}
BLOCKED = {u["rule"] for u in derivation["unresolved_rules"] if u.get("reason") == "blocked_by_conflict"}
MISSING = {u["rule"] for u in derivation["unresolved_rules"] if u.get("reason") == "missing_deps"}
A("## 4. 计算与判定规则（Rule Instance）")
A("")
A(f"共 **{len(rules)}** 条。**派生量不得手填**，一律按 `expr` 由 `deps` 算出。")
A(f"已确定性复算：闭合 {len(CLOSED)} 条、派生差异 {len(INF)} 条、仅重算 {len(NOSTATED)} 条、"
  f"因未裁决冲突阻塞 {len(BLOCKED)} 条、因缺口径未解 {len(MISSING)} 条。")
A("")
A("```yaml")
A("rules:")
for r in rules:
    st = ("闭合" if r["id"] in CLOSED else "派生差异" if r["id"] in INF else
          "仅重算" if r["id"] in NOSTATED else "阻塞(冲突未裁决)" if r["id"] in BLOCKED else
          "未解(缺口径)" if r["id"] in MISSING else "—")
    A(f"  - id: {r['id']}")
    A(f"    kind: {r.get('kind')}")
    A(f"    label: {r.get('label')}")
    A(f"    expr: \"{r.get('expr','')}\"")
    A(f"    deps: {json.dumps(r.get('deps', []), ensure_ascii=False)}")
    A(f"    target: {r.get('target','')}")
    A(f"    guard: {r.get('guard','')}")
    A(f"    recheck: {st}")
A("```")
A("")
if INF:
    A("### 4.1 派生差异（重算值 ≠ 原报告声明值，**不得改数，按待审呈现**）")
    A("")
    A("| 规则 | 重算值 | 原文值 | 差额 | 占比 |")
    A("|------|--------|--------|------|------|")
    for d in derivation["derivation_diff"]:
        A(f"| {d['rule']} | {d['computed']:g} | {d['stated']:g} | {d['delta']:g} | {d['delta_pct']}% |")
    A("")
if judgements:
    A("### 4.2 判定类结论（select 规则求值）")
    A("")
    for j in judgements:
        A(f"- **{j['id']}** {j['question']}")
        A(f"  - 前提：`{json.dumps(j['premises'], ensure_ascii=False)}`")
        A(f"  - 结论：**{j['verdict']}**　｜　{j['note']}")
    A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 5 论断
A("## 5. 论证单元（Claim + Toulmin + 证据）")
A("")
A(f"共 **{len(claims)}** 条论断。**每条论断必须绑定证据**；Toulmin 六元组中的 `warrant`（保证）是")
A("评审最常抓的断链点——本表中为空的，正文不得替它补写。")
A("")
for c in claims:
    A(f"### {c['id']}")
    A("")
    A(f"- **论断性质**：`{c.get('type','')}`　**论证类型**：`{c.get('claim_type','')}`　**状态**：`{c.get('status','')}`")
    A(f"- **论断**：{c.get('text','')}")
    A(f"- **来源**：`{c.get('source','')}`")
    t = c.get("toulmin") or {}
    if t:
        A("- **Toulmin 六元组**：")
        for k, cn in (("claim", "论点"), ("grounds", "论据"), ("warrant", "保证"),
                      ("backing", "支撑"), ("qualifier", "限定"), ("rebuttal", "反驳")):
            v = t.get(k, "")
            v = "**（原文未给出——不得代拟）**" if (k == "warrant" and (not v or "未" in v[:6])) else v
            A(f"  - {cn}（`{k}`）：{v}")
    ev = [e for e in c.get("evidence_refs", []) if e in EV_BY_ID]
    if ev:
        A("- **证据**：")
        for eid in ev:
            e = EV_BY_ID[eid]
            A(f"  - `{eid}`（{e.get('kind','')}｜{e.get('status','')}）{e.get('doc','')}"
              + (f"　定位：{e.get('locator','')}" if e.get("locator") else ""))
    else:
        A("- **证据**：**（无外部证据——已登记为缺口，正文不得硬撑结论）**")
    if c.get("premise_refs"):
        A(f"- **前提**：{'、'.join('`' + p + '`' for p in c['premise_refs'])}")
    A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 6 依据层
A("## 6. 依据层（外部检索文件）")
A("")
A("报告的技术函数**不是自证的**：其取值域约束与推理保证来自外部规范与政策文件。")
A("本节即这些依据的条款级内容，已与报告取值逐条绑定。")
A("")
A("### 6.1 外部检索文件台账")
A("")
A("| 文件ID | 内容 | 发布主体 | 检索状态 | 来源 |")
A("|--------|------|----------|----------|------|")
for d in EXT_DOCS:
    title = d["title"].replace("|", "\\|")[:60]
    A(f"| `{d['id']}` | {title} | {d.get('publisher','')[:22]} | `{d['retrieval_status']}` | "
      + (f"[链接]({d['url']})" if str(d.get('url','')).startswith('http') else "—") + " |")
A("")
A("> 检索状态：`ok` 可用 ｜ `ok_secondary` 二手转录 ｜ `ok_partial` 表格被剥离 ｜ `ok_mislabeled` 文件名与实际内容不符"
  "（按实际内容使用）｜ `duplicate` 同条款另一版式 ｜ `failed_403` 不可用 |")
A("")
A("### 6.2 Mandate 条款（引用时以此为准）")
A("")
for m in EXT_MANDATES:
    A(f"#### {m['id']}　{m['standard']}　{m['code']}")
    A("")
    A(f"- **角色**：`{m['role']}`　**效力状态**：{m['status']}")
    A(f"- **条文**：{m['text']}")
    if m.get("source_url"):
        A(f"- **来源**：{m['source_url']}")
    A("")
A("### 6.3 取值域约束")
A("")
A("| 约束ID | 适用对象 | 约束式 | 强制性 | 依据条款 |")
A("|--------|----------|--------|--------|----------|")
for c in EXT_CONSTRAINTS:
    mand = next((x["code"] for x in EXT_MANDATES if x["id"] == c["mandate"]), "")
    A(f"| `{c['id']}` | {c['applies_to']} | {c['expr'].replace('|', chr(92)+'|')} | "
      f"{'**是**' if c.get('mandatory') else '否'} | {mand} |")
A("")
A("### 6.4 报告技术函数 × 依据：绑定与三态判定")
A("")
A("| 绑定ID | 报告取值 | 依据角色 | 依据 | 判定 |")
A("|--------|----------|----------|------|------|")
ICON = {"合规": "✅ 合规", "不合规": "❌ 不合规", "待审": "⚠️ 待审", "待核查": "🔍 待核查"}
for r in COMPLIANCE["results"]:
    A(f"| `{r['binding']}` | {r['report']['rule']} | `{r['role']}` | {'；'.join(r['basis_titles'])} | "
      f"{ICON.get(r['verdict'], r['verdict'])} |")
A("")
for r in COMPLIANCE["results"]:
    A(f"#### {r['binding']}　{ICON.get(r['verdict'], r['verdict'])}　{r['report']['rule']}")
    A("")
    A(f"- **报告取值**：{r['report']['value']}")
    A(f"- **依据**：{'；'.join(r['basis_titles'])}（角色 `{r['role']}`）")
    A(f"- **为何必须依赖依据**：{r['why']}")
    A(f"- **判定说明**：{r['finding']}")
    if r.get("branches"):
        A("- **分支结论（前提未裁决，两条路径并列，不得自行选定）**：")
        for br in r["branches"]:
            A(f"  - 若 {br['假设']} ⇒ {br['结论']}")
    if r.get("needs_to_verify"):
        A("- **须核对**：" + "；".join(r["needs_to_verify"]))
    A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 7 章节装配表
TEMPL_MAP = {}
for f in sorted((ROOT / "style" / "section_templates").glob("*.yaml")):
    TEMPL_MAP[f.stem.split("-", 1)[-1]] = f"style/section_templates/{f.name}"
A("### 6.5 规范依赖模式（跨项目可复用资产）")
A("")
A(f"> 资产文件：`reuse/regulatory_dependency.yaml`；已挂到 {('、'.join('`'+x+'`' for x in REG_DEP['attached_to_domains']))} 六个域的 `reusable_form` 上。")
A("")
A(f"- **为何是资产**：{REG_DEP['reusable_form']['why_asset']}")
A("- **可复用检查项**：")
for c in REG_DEP["reusable_form"]["reusable_checks"]:
    A(f"  - `{c['id']}` **{c['name']}**：{c['desc']}")
    A(f"    - 为什么：{c['why']}")
A(f"- **契约说明**：{REG_DEP['contract_note']}")
A("")
A("---")
A("")

A("## 7. 章节装配表（含逐章提示词）")
A("")
A("**每章是不同的活**：必要性章在论证、规模章在测算、技术章在判定与取值、投资章在归集、结论章在复述。")
A("下面是本项目逐章实例化的起草提示（`style/section_prompts.yaml`）。"
  "`prepare` 里的项没做完就不要动笔——写出来也要返工。")
A("")
A("### 7.0 通用约束（每章都适用）")
A("")
for x in SEC_PROMPTS["common"]["hard"]:
    A(f"- **硬规则**：{x}")
for x in SEC_PROMPTS["common"]["style"]:
    A(f"- 文风：{x}")
A(f"- 自检：{SEC_PROMPTS['common']['self_check']}")
A("")
for i, ch in enumerate(L1, 1):
    sp = SP_BY_CH.get(ch)
    sub = [n for n in nodes if n["_chapter"] == ch]
    csub = [c for c in claims if chapter_of(c.get("source", "")) == ch]
    tmpl = TEMPL_MAP.get(ch) or next((v for k, v in TEMPL_MAP.items() if k.startswith(ch[:6])), "（无模板，按 §2.2 结构）")
    A(f"### 7.{i} {ch}　<span id=\"s{i}\"></span>")
    A("")
    if not sp:
        A("（无专属提示，按 §7.0 通用约束起草）")
        A("")
        continue
    A(f"- **章节族**：`{sp['family']}`（{sp['family_cn']}）　**法定覆盖**：{'、'.join(sp['covers'])}")
    A(f"- **核心问题**：{sp['focus']}")
    A(f"- **形态**：{sp['shape']}　｜　**评审盯什么**：{sp['review']}")
    si = sp["slice"]
    A(f"- **本章切片**：可用事实节点 **{si['available_facts']}** 条"
      + (f"（{'、'.join('`' + x + '`' for x in si['fact_ids'])}{' …' if si['available_facts'] > len(si['fact_ids']) else ''}）" if si["fact_ids"] else "")
      + (f"；论断 {'、'.join('`' + c + '`' for c in si['claims'])}" if si["claims"] else ""))
    if si["predicates"]:
        A(f"- **本章关键取值**（正文须给出具体数值）**{'；'.join(si['predicates'][:14])}**")
    A(f"- **模板**：`{tmpl}`")
    A("- **起草前置（prepare）**：")
    for x in sp["prepare"]:
        A(f"  - {x}")
    A("- **必须写到（must_state）**：")
    for x in sp["must_state"]:
        A(f"  - {x}")
    A("- **本章特有的坑（must_not）**：")
    for x in sp["must_not"]:
        A(f"  - {x}")
    pi = sp["project_issues"]
    if pi["conflicts"]:
        A(f"- **⚠️ 本章涉及 {len(pi['conflicts'])} 条待审冲突（不得裁决）**：")
        for c in pi["conflicts"]:
            A(f"  - {c['subject']} · {c['predicate']} ⇒ `{'` / `'.join(c['values'])}`")
    if pi["gaps"]:
        A(f"- **🔍 本章涉及 {len(pi['gaps'])} 条缺口（正文留白）**："
          + "；".join(f"{g['id']} {g['subject']}" for g in pi["gaps"]))
    if pi["external_bindings"]:
        A("- **📐 本章涉及的外部依据绑定**：")
        for b in pi["external_bindings"]:
            r = next((x for x in COMPLIANCE["results"] if x["binding"] == b["id"]), None)
            ic = {"合规": "✅", "不合规": "❌", "待审": "⚠️", "待核查": "🔍"}.get(b["verdict"], "")
            A(f"  - `{b['id']}` {ic} **{b['verdict']}**（角色 `{b['role']}`）——{r['report']['rule'] if r else ''}"
              + (f"：{r['finding'][:120]}…" if r else ""))
    A("")
A("> 章节与法定内容项的核销表见 §2.1；**标题可变，覆盖不可少**——变形只搬动内容的容器，不增减内容。")
A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 8 冲突
A("## 8. 冲突待审清单（写作时**保留并列，不得裁决**）")
A("")
A(f"共 **{len(conflicts)}** 条。处理方式：正文按「待审」呈现并列值与来源；**不得取其一、不得改数、不得补口径**。")
A("")
A("| # | 类型 | 主体 · 属性 | 并列取值 | 说明 |")
A("|---|------|-------------|----------|------|")
for i, c in enumerate(conflicts, 1):
    A(f"| {i} | {c['type']} | {c['subject']} · {c['predicate']} | "
      f"`{'` / `'.join(c['values'])}` | {c.get('note','')[:110]} |")
A("")
A("### 8.1 因未裁决冲突而阻塞的派生规则")
A("")
A("| 规则 | 阻塞依赖 | 并列取值 |")
A("|------|----------|----------|")
for u in derivation["unresolved_rules"]:
    if u.get("reason") == "blocked_by_conflict":
        for d in u["detail"]:
            A(f"| {u['rule']} | {d['dep']} | {' / '.join(d['values'])} |")
A("")
A("> 一处笔误（第13章把总建筑面积写成 18219）导致上述派生规则**全部无法计算**——写作时这些量须标为待审，不得给出一个值。")
A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 9 缺口
A("## 9. 缺口清单（正文显式留白，不编造）")
A("")
A(f"共 **{len(gaps)}** 条。**缺就是缺**：正文写「待 X 确认后生成」，不估算、不套用同类项目、不写「暂按经验值」。")
A("")
TYPES = {"missing_fact": "缺事实（口径未给出）", "blocked_by_conflict": "被未裁决冲突阻塞",
         "explicit_unknown": "原文显式未知", "basis_missing": "外部依据未取到"}
for t, cn in TYPES.items():
    sub = [g for g in gaps if g["type"] == t]
    if not sub:
        continue
    A(f"### 9.{list(TYPES).index(t)+1} {cn}（{len(sub)} 条）")
    A("")
    for g in sub:
        head = g.get("subject") or g.get("label") or g.get("rule") or g["id"]
        A(f"- **{g['id']} · {head}**：{g['note']}"
          + (f"　缺失项：`{'`、`'.join(g['missing'])}`" if g.get("missing") else ""))
    A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 10 术语与口径
A("## 10. 术语与口径")
A("")
A("### 10.1 高频术语（前 40）")
A("")
A("| 术语 | 规范形 | 频次 |")
A("|------|--------|------|")
for t in terms[:40]:
    A(f"| {t['surface']} | {t['canonical']} | {t['freq']} |")
A("")
A("### 10.2 单位与量纲陷阱（本项目实测踩到）")
A("")
A("- **未预见系数**以 `%` 表达（10），公式中须 `/100`，否则结果放大 100 倍；")
A("- **用电量**由 W·h 折「万 kW·h」除数为 `1e7`（不是 `1e4`），否则结果放大 1000 倍；")
A("- **万元 / 元**在单位造价与分项金额之间必须显式换算；")
A("- **使用面积 / 建筑面积**换算口径为 `使用面积系数 K`（= 使用面积 ÷ 建筑面积，%），本项目 K=0.55。")
A("")
A("### 10.3 指标口径")
A("")
A("- **分类人数**必须分「科研人员」与「研究生/博士生/访问学者」两档——两档人均指标不同（16 与 8 ㎡/人）；")
A("- **人均建筑面积指标**是上限（「不超过」），不是目标值；")
A("- **规划人数**（表5-6，合计 1665 人）与**用水/用电计算人数**（表6-2：科研学生 1800 人 + 办公 288 人，均标注「暂定」）"
  "**口径不同**，已登记为冲突，正文不得混用。")
A("")
A("---")
A("")

# ══════════════════════════════════════════════════════════════════ 11 溯源索引
A("## 11. 溯源索引")
A("")
A("### 11.1 论断 → 证据 → 原文定位")
A("")
A("| 论断 | 证据ID | 证据等级 | 状态 | 出处 | 定位 |")
A("|------|--------|----------|------|------|------|")
for c in claims:
    for eid in c.get("evidence_refs", []):
        e = EV_BY_ID.get(eid)
        if e:
            A(f"| {c['id']} | `{eid}` | {e.get('kind','')} | {e.get('status','')} | {e.get('doc','')[:34]} | {e.get('locator','')} |")
A("")
A("### 11.2 节点 → 原文切片")
A("")
A("每个节点的 `source` 即 `chunks/chunks.jsonl` 中的 chunk id；完整倒排见 `index/node_index.json`。")
A("示例（前 12 条）：")
A("")
A("| 节点ID | chunk | 章节路径 |")
A("|--------|-------|----------|")
for n in nodes[:12]:
    A(f"| `{n['id']}` | `{n['source']}` | {n['_chapter']} / {n['_section']} |")
A("")
A("### 11.3 依据 → 外部切片")
A("")
A("| 条款ID | 外部 chunk | 定位状态 |")
A("|--------|-----------|----------|")
for m in EXT_MANDATES:
    A(f"| `{m['id']}` | {'、'.join('`' + c + '`' for c in m.get('chunks', [])) or '—'} | `{m['trace_status']}` |")
A("")
A("---")
A("")
A("## 12. 交付边界声明")
A("")
A("本装配输入包**不对任何数值的准确性负责**，也不判断造价高低、人数是否合理。")
A("本包保证的是：事实单源可定位、规则可复算、论断可追溯到证据、冲突与缺口显式待审、依据可回溯到条款。")
A("")

OUT.write_text("\n".join(L), encoding="utf-8")
size = OUT.stat().st_size
print(json.dumps({"file": str(OUT.relative_to(WS)), "bytes": size, "lines": len(L),
                  "facts": len(nodes), "rules": len(rules), "claims": len(claims),
                  "curated_evidence": len(CURATED_EV), "auto_evidence": len(AUTO_EV),
                  "mandates": len(EXT_MANDATES), "bindings": len(EXT_BINDINGS),
                  "chapters": len(L1), "conflicts": len(conflicts), "gaps": len(gaps)},
                 ensure_ascii=False, indent=2))
