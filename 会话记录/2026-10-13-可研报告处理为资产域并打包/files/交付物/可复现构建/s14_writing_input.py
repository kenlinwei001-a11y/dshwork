# -*- coding: utf-8 -*-
"""写作投递件生成（确定性）：为「推演写作专家」产出分层输入。

分层原则（Agent 访问形式）：
  ① 注入（小、恒定、每章都用）→ 写作输入/推演写作输入包.md（瘦身版，目标 ≈30KB）
  ② 按需（大、稀疏、写某章才取）→ 写作输入/chapters/NN-*.md（按章切片）+ 索引
  ③ 知识资产（借形，走文件索引）→ 写作输入/知识资产索引.md（只给索引与指针，不展开内容）
  ④ 禁止注入 → chunks.jsonl（原文）、graph.yaml（整包）、skeletons.jsonl（全量）、evidence/excerpts（全量）
"""
import json
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
W = WS / "交付物" / "写作输入"
W.mkdir(parents=True, exist_ok=True)
CH = W / "chapters"


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


nodes = J(ROOT / "graph" / "nodes.yaml")
rules = J(ROOT / "graph" / "rules.yaml")
claims = J(ROOT / "graph" / "claims.yaml")
evidence = J(ROOT / "evidence" / "evidence.yaml")
outline = J(ROOT / "outline.yaml")
manifest = J(ROOT / "manifest.yaml")
conflicts = J(ROOT / "quality" / "conflicts.yaml")
gaps = J(ROOT / "quality" / "gaps.yaml")
derivation = J(ROOT / "reasoning" / "derivation.yaml")
judgements = J(ROOT / "reasoning" / "judgements.yaml")
domains = J(ROOT / "reuse" / "domains.yaml")
dep_graph = J(ROOT / "reuse" / "dependency_graph.yaml")
reg_dep = J(ROOT / "reuse" / "regulatory_dependency.yaml")
sec_prompts = J(ROOT / "style" / "section_prompts.yaml")
terms = J(ROOT / "index" / "term_index.json")
EXT_DOCS = J(ROOT / "external" / "documents.yaml")["documents"]
EXT_MANDATES = J(ROOT / "external" / "mandates.yaml")["mandates"]
EXT_CONSTRAINTS = J(ROOT / "external" / "constraints.yaml")["constraints"]
COMPLIANCE = J(ROOT / "external" / "compliance.yaml")
chunks = [json.loads(l) for l in (ROOT / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
chunk_by_id = {c["id"]: c for c in chunks}

FACT_META = {}
for p in sorted((BUILD / "extractions-clean").glob("*.json")):
    for u in json.loads(p.read_text(encoding="utf-8")):
        for f in u.get("facts", []):
            FACT_META[(str(f.get("subject")), str(f.get("predicate")), str(f.get("value")))] = \
                (f.get("from") or {})

CURATED_EV = {e["id"]: e for e in evidence if str(e.get("id", "")).startswith("EV-")}
L1 = [s["title"] for s in outline["sections"] if s["level"] == 1]
SP = {x["chapter"]: x for x in sec_prompts["sections"]}
VERDICT = {r["binding"]: r for r in COMPLIANCE["results"]}
DERIV_DIFF = {d["rule"] for d in derivation["derivation_diff"]}
DERIV_BLOCKED = {u["rule"] for u in derivation["unresolved_rules"] if u.get("reason") == "blocked_by_conflict"}
ICON = {"合规": "✅", "不合规": "❌", "待审": "⚠️", "待核查": "🔍"}


def chapter_of(cid):
    c = chunk_by_id.get(cid)
    sp = (c or {}).get("section_path") or []
    return sp[0] if sp else "（未归属）"


for n in nodes:
    n["_chapter"] = chapter_of(n.get("source", ""))
    n["_section"] = (chunk_by_id.get(n.get("source", ""), {}).get("section_path") or [""])[-1]

# ════════════════════════════════════════════════════ ① 注入档（瘦身）
L = []
A = L.append
A("# 推演写作输入包（注入档）")
A("")
A("> **上海财经大学中山北一路校区大数据研究中心 可行性研究报告（修订版）** · 还原写作")
A("> 本文件是**每章都要用的恒定约束**，可直接作为上下文注入；体量已控在 ~30 KB。")
A("> 大体积材料（事实全集、依据条文、原文切片）**不放这里**，见 §I 的投递分层。")
A("")
A("| 项 | 值 |")
A("|----|----|")
A(f"| 语料包 | `{manifest['corpus_id']}` · {manifest['version']} · **{manifest['status']}** |")
A(f"| 原稿 sha256 | `{manifest.get('source_original_sha256','')}` |")
_ni = {n["predicate"]: n["value"] for n in nodes if n["subject"] == "本报告"}
A(f"| 报告编号 / 编制单位 | {_ni.get('报告编号','—')} ｜ {_ni.get('编制单位','—')} |")
A(f"| 编制人 / 日期 | 负责人 {_ni.get('项目负责人','—')}；审核 {_ni.get('项目审核人','—')}；编制人 {_ni.get('主要编制人','—')} ｜ {_ni.get('编制日期','—')} |")
A(f"| 建设单位 | {next((n['value'] for n in nodes if n['subject']=='本项目' and n['predicate']=='建设单位'),'—')} |")
A(f"| 规模 | 16 章 / {len({n['id'] for n in nodes})} 个事实节点 / {len(rules)} 规则 / {len(claims)} 论断 / {len(EXT_MANDATES)} 依据条款 |")
A(f"| 待审冲突 / 缺口 | {len(conflicts)} / {len(gaps)} |")
A("")
A("---")
A("")

A("## A. 写作硬纪律（8 条，不得违反）")
A("")
for i, x in enumerate(sec_prompts["common"]["hard"], 1):
    A(f"{i}. {x}")
A("")
A(f"**自检**：{sec_prompts['common']['self_check']}")
A("")
A("**文风**：" + "；".join(sec_prompts["common"]["style"]))
A("")
A("**不变量（装配后自检）**：同一 (主题,属性) 数值必须一致；关系两端指向存在节点；论断证据引用必须存在；")
A("冲突只呈现待审不裁决；UNDEFINED 不得填 0 或估值；依赖存在未裁决冲突时派生校核阻塞而非取一值硬算。")
A("")
A("---")
A("")

A("## B. 关键项目信息（速查）")
A("")
A("| 项 | 值 | 节点ID |")
A("|----|----|--------|")
for subj, pred in [("本项目", "项目名称"), ("本项目", "建设性质"), ("本项目", "建设地点"),
                   ("本项目", "总建筑面积"), ("本项目", "地上建筑面积"), ("本项目", "地下建筑面积"),
                   ("原第五教学楼", "拆除面积"), ("本项目", "总投资"), ("本项目", "建安工程费用"),
                   ("本项目", "工程建设其他费用"), ("本项目", "预备费"), ("本项目", "原建筑拆除费用"),
                   ("本项目", "国拨资金"), ("本项目", "学校自筹资金"), ("本项目", "建设工期"),
                   ("本项目", "开工时间"), ("本项目", "竣工时间")]:
    for n in nodes:
        if n["subject"] == subj and n["predicate"] == pred:
            A(f"| {subj} · {pred} | {n['value']} {n['unit']} | `{n['id']}` |")
            break
A("")
A("---")
A("")

A("## C. 章节覆盖核销表（法定十章 × 内容项）")
A("")
A("| 法定章 | 法定内容项 | 本报告对应 | 核销 |")
A("|--------|-----------|-----------|------|")
MUST = [("概述", ["项目概况", "项目单位概况", "编制依据", "主要结论和建议"], "总论", "4/4"),
        ("项目建设背景和必要性", ["项目建设背景", "规划政策符合性", "项目建设必要性"], "项目建设背景及必要性分析", "3/3"),
        ("项目需求分析与产出方案", ["需求分析", "建设内容和规模", "项目产出方案"], "项目建设内容及规模", "2/3"),
        ("项目选址与要素保障", ["项目选址或选线", "项目建设条件", "要素保障分析"], "项目选址及建设条件", "2/3"),
        ("项目建设方案", ["技术方案", "设备方案", "工程方案", "数字化方案", "建设管理方案"], "项目规划设计方案 / 节能设计", "3/5"),
        ("项目运营方案", ["运营模式选择", "运营组织方案", "安全保障方案", "绩效管理方案"], "（缺独立章）", "0/4"),
        ("项目投融资与财务方案", ["投资估算", "盈利能力分析", "融资方案", "债务清偿能力分析", "财务可持续性分析"], "投资估算及资金筹措", "1/5"),
        ("项目影响效果分析", ["经济影响分析", "社会影响分析", "资源和能源利用效果分析", "碳达峰碳中和分析"], "环境影响评价 / 社会效益", "3/4"),
        ("项目风险管控方案", ["风险识别与评价", "风险管控方案", "风险应急预案"], "社会稳定风险分析", "2/3"),
        ("研究结论及建议", ["主要研究结论", "问题与建议"], "结论与建议", "2/2")]
for mc, items, rep, ok in MUST:
    bad = ok.split("/")[0] != ok.split("/")[1]
    A(f"| {mc} | {'、'.join(items)} | {rep} | {'❌ ' if bad else '✅ '}{ok} |")
A("")
A("> 本报告编制于 2019 年 8 月，早于 2023 版大纲。还原写作按哪个大纲须由客户确认；")
A("> 标 ❌ 的须补齐未覆盖内容项（详见 §G 的 B-14 与 `审计/06-外部依据绑定与合规复核.md`）。")
A("")
A("---")
A("")

A("## D. 逐章索引（详版按需取，见 §I）")
A("")
A("| # | 章 | 章节族 | 节点 | 冲突 | 缺口 | 依据绑定 | 按需切片 |")
A("|---|----|--------|------|------|------|----------|----------|")
for i, ch in enumerate(L1, 1):
    sp = SP.get(ch, {})
    sub = [n for n in nodes if n["_chapter"] == ch]
    pi = sp.get("project_issues", {})
    bd = " ".join(f"{b['id']}{ICON.get(b['verdict'],'')}" for b in pi.get("external_bindings", [])) or "—"
    fname = f"{i:02d}-{ch}.md"
    A(f"| {i} | {ch} | `{sp.get('family','—')}` | {sp['slice']['available_facts'] if sp else len({n['id'] for n in sub})} | "
      f"{len(pi.get('conflicts', []))} | {len(pi.get('gaps', []))} | {bd} | `写作输入/chapters/{fname}` |")
A("")
A("---")
A("")

A("## E. 冲突待审清单（正文保留并列，**不得裁决**）")
A("")
A("| # | 主体 · 属性 | 并列取值 | 说明 |")
A("|---|-------------|----------|------|")
for i, c in enumerate(conflicts, 1):
    A(f"| {i} | {c['subject']} · {c['predicate']} | `{'` / `'.join(c['values'])}` | {c.get('note','')[:100]} |")
A("")
if DERIV_BLOCKED:
    A("**因未裁决冲突而阻塞的派生规则**（这些量不得给出单一值）：")
    A("")
    for u in derivation["unresolved_rules"]:
        if u.get("reason") == "blocked_by_conflict":
            A(f"- `{u['rule']}`：阻塞依赖 " + "、".join(f"{d['dep']}={'/'.join(d['values'])}" for d in u["detail"]))
    A("")
    A(f"> 一处笔误（第13章把总建筑面积写成 18219）导致上述 {len(DERIV_BLOCKED)} 条规则全部无法计算。")
    A("")
A("---")
A("")

A("## F. 缺口清单（正文显式留白，不编造）")
A("")
TN = {"missing_fact": "缺事实", "blocked_by_conflict": "被冲突阻塞", "explicit_unknown": "原文显式未知",
      "basis_missing": "依据未取到"}
for t, cn in TN.items():
    sub = [g for g in gaps if g["type"] == t]
    if not sub:
        continue
    A(f"**{cn}（{len(sub)} 条）**")
    A("")
    for g in sub:
        h = g.get("subject") or g.get("label") or g.get("rule") or g["id"]
        A(f"- `{g['id']}` **{h}**：{g['note']}")
    A("")
A("---")
A("")

A("## G. 依据层要点（条文全文按需取）")
A("")
A("**外部检索文件台账**：" + "、".join(f"`{d['id']}`{d['title'][:22]}" for d in EXT_DOCS) + "（共 "
  + str(len(EXT_DOCS)) + " 份；详版 `external/documents.yaml`）")
A("")
A("| 判定 | 绑定 | 报告取值 | 依据（条款号） | 角色 |")
A("|------|------|----------|----------------|------|")
for r in COMPLIANCE["results"]:
    A(f"| {ICON.get(r['verdict'],'')} **{r['verdict']}** | `{r['binding']}` | {r['report']['rule']} | "
      f"{'；'.join(r['basis_titles'])} | `{r['role']}` |")
A("")
A("**结论分布**：" + "、".join(f"{k} {v} 条" for k, v in sorted(COMPLIANCE["counts"].items())) + "。")
A("")
A("**强制性约束（违反即报审退回）**：")
A("")
for c in EXT_CONSTRAINTS:
    if c.get("mandatory"):
        A(f"- `{c['id']}` {c['applies_to']}：{c['expr']}")
A("")
A(f"**规范依赖模式**（可复用资产 `reuse/regulatory_dependency.yaml`）的可复用检查："
  + "、".join(f"`{c['id']}`{c['name']}" for c in reg_dep["reusable_form"]["reusable_checks"]))
A("")
A("> 最要紧的一条：**阈值穿越检查（RP-1）**——报告声明建筑高度 60m、按层高推算 49m，"
  "而 GB50016 表5.1.1 的 50m 一类/二类分界恰在两者之间。此时**不得给出单一判定**，"
  "必须并列两条分支路径（B-01/B-02/B-03）。")
A("")
A("---")
A("")

A("## H. 术语与口径")
A("")
A("**高频术语（前 30）**：" + "、".join(f"{t['surface']}({t['freq']})" for t in terms[:30]))
A("")
A("**单位与量纲陷阱（本项目实测踩到）**")
A("")
A("- 未预见系数以 `%` 表达（10），公式中须 `/100`；")
A("- 用电量由 W·h 折「万 kW·h」除数为 `1e7`（不是 `1e4`）；")
A("- 万元 / 元 在单位造价与分项金额之间必须显式换算；")
A("- 使用面积 ↔ 建筑面积 换算用 `使用面积系数 K`（= 使用面积 ÷ 建筑面积，%），本项目 K=0.55。")
A("")
A("**指标口径**")
A("")
A("- 分类人数分两档（科研人员 / 研究生·博士生·访问学者），人均指标不同：**16 与 8 ㎡/人**，且均为**上限**；")
A("- 规划人数（表5-6 合计 **1665 人**）与用水/用电计算人数（表6-2：科研学生 1800 + 办公 288，均标「暂定」）**口径不同**，已登记冲突，**正文不得混用**。")
A("")
A("---")
A("")

A("## I. 投递分层（怎么把材料交给写作 Agent）")
A("")
A("**不要把所有材料都塞进上下文。** 本包共约 3 MB，其中原文 830 KB、脱敏骨架 874 KB、graph 整包 220 KB——"
  "这些进上下文既浪费预算，也会把 Agent 从「写」变成「抄」。")
A("")
A("| 层 | 内容 | 体积 | 投递方式 |")
A("|----|------|------|----------|")
A("| **① 注入** | **本文件** `写作输入/推演写作输入包.md` | ~30 KB | **直接作为上下文**（每章恒定） |")
A("| ① 注入 | `写作输入/章节提示词索引.md` | ~20 KB | 直接作为上下文（10 族提示 + 16 章索引） |")
A("| ① 注入 | `写作输入/知识资产索引.md` | ~6 KB | 直接作为上下文（**索引，非内容**） |")
A("| **② 按需** | `写作输入/chapters/NN-*.md` | 每章 5–60 KB | **写到该章时读该章文件**（一次一章） |")
A("| ② 按需 | `SHUFE-BDC-2019-001/reuse/domains/*.yaml` | 141 KB | 需要某个域的**具体形态**时，按 `知识资产索引.md` 的路径读该域文件 |")
A("| ② 按需 | `external/mandates.yaml`（条款全文） | 19 KB | 引用某条规范时读该条款 |")
A("| ② 按需 | `chunks/chunks.jsonl`（报告切片） | 830 KB | **只在需要逐字原文时按 chunk id 取单条**，不整文件读 |")
A("| **③ 禁止** | `graph/graph.yaml`（整包） | 220 KB | ✗ 不给 |")
A("| ③ 禁止 | `chunks/skeletons.jsonl` 全量 | 874 KB | ✗ 不给（只作结构参照时可单条取） |")
A("| ③ 禁止 | `evidence/excerpts/*`（443 文件） | 318 KB | ✗ 不给（按需单取） |")
A("| ③ 禁止 | `chunks/chunks.jsonl` 全文 | 830 KB | ✗ **绝不整文件给** |")
A("")
A("**工作流**：读本文件 + 两个索引 → 生成章节骨架 → **逐章**读 `chapters/NN-*.md` → 起草 → "
  "正文写 `{{node:N-xxxxxxxxxxxx}}` → 成稿反向回读比对。")
A("")
A("**知识资产放哪里**：放 `SHUFE-BDC-2019-001/reuse/domains/`（16 个文件 + `domains.yaml` 索引 + "
  "`dependency_graph.yaml` 依赖图 + `regulatory_dependency.yaml` 扩展资产）。"
  "**不整包进上下文**——上下文里只放 `知识资产索引.md`，正文按需读单个域文件。")
A("")

(W / "推演写作输入包.md").write_text("\n".join(L), encoding="utf-8")
inj_bytes = (W / "推演写作输入包.md").stat().st_size
print(json.dumps({"inject_file": "写作输入/推演写作输入包.md", "bytes": inj_bytes,
                  "kb": round(inj_bytes / 1024, 1)}, ensure_ascii=False))

# ════════════════════════════════════════════════════ ② 章节提示词索引
L = []; A = L.append
A("# 章节提示词索引")
A("")
A("> 用法：每章起草前读本文件对应行 + 该章的行内注入；`prepare` 没做完不要动笔。")
A("> 结构：**十个章节族各写一次**（不按章重复），16 个一级章各自指向所属族并附本项目注入。")
A("")
A("---")
A("")
A("## 一、通用约束")
A("")
A("**硬规则**")
for x in sec_prompts["common"]["hard"]:
    A(f"- {x}")
A("")
A("**文风**")
for x in sec_prompts["common"]["style"]:
    A(f"- {x}")
A("")
A(f"**自检**：{sec_prompts['common']['self_check']}")
A("")
A("---")
A("")
A("## 二、章节族提示（十族各一次）")
A("")
for fam in sorted(sec_prompts["families"]):
    fp = sec_prompts["families"][fam]
    A(f"### {fam}　{fp['cn']}")
    A("")
    A(f"- **法定覆盖**：{'、'.join(fp['covers'])}")
    A(f"- **核心问题**：{fp['focus']}")
    A(f"- **形态**：{fp['shape']}　｜　**评审盯什么**：{fp['review']}")
    A("- **起草前置（prepare）**：")
    for x in fp["prepare"]:
        A(f"  - {x}")
    A("- **必须写到（must_state）**：")
    for x in fp["must_state"]:
        A(f"  - {x}")
    A("- **本章特有的坑（must_not）**：")
    for x in fp["must_not"]:
        A(f"  - {x}")
    A("")
A("---")
A("")
A("## 三、本报告 16 章索引（族归属 + 本项目注入）")
A("")
for i, ch in enumerate(L1, 1):
    sp = SP.get(ch)
    if not sp:
        continue
    pi = sp["project_issues"]
    A(f"### {i}. {ch} → 族 `{sp['family']}`")
    A("")
    A(f"- **切片**：{sp['slice']['available_facts']} 个唯一事实节点（{sp['slice'].get('statements', 0)} 次陈述）"
      + (f"；论断 {'、'.join('`' + c + '`' for c in sp['slice']['claims'])}" if sp["slice"]["claims"] else ""))
    if sp["slice"]["predicates"]:
        A(f"- **本章关键取值**：**{'；'.join(sp['slice']['predicates'][:16])}**")
    extra = [x for x in sp["prepare"] if x.startswith("**本章")]
    if extra:
        A("- **本项目注入的前置**：")
        for x in extra:
            A(f"  - {x}")
    if pi["conflicts"]:
        A(f"- **⚠️ 待审冲突 {len(pi['conflicts'])} 条**：" +
          "；".join(f"{c['subject']}·{c['predicate']}（{'/'.join(c['values'])}）" for c in pi["conflicts"]))
    if pi["gaps"]:
        A(f"- **🔍 缺口 {len(pi['gaps'])} 条**：" + "、".join(f"{g['id']} {g['subject']}" for g in pi["gaps"]))
    if pi["external_bindings"]:
        A("- **📐 依据绑定**：")
        for b in pi["external_bindings"]:
            r = VERDICT.get(b["id"])
            A(f"  - `{b['id']}` {ICON.get(b['verdict'],'')} **{b['verdict']}** · {r['report']['rule'] if r else ''}")
    A(f"- **按需切片文件**：`写作输入/chapters/{i:02d}-{ch}.md`")
    A("")
(W / "章节提示词索引.md").write_text("\n".join(L), encoding="utf-8")

# ════════════════════════════════════════════════════ ③ 知识资产索引（只给索引）
L = []; A = L.append
A("# 知识资产索引")
A("")
A("> **本文件是索引，不是内容。** 16 个资产域共 141 KB——不要整包进上下文；")
A("> 需要某个域的具体形态时，按本表路径读**该域单个文件**。")
A("")
A("## 一、16 个资产域（kp 内置契约）")
A("")
A("| # | 域 id | 核心域 | 资产性质 | 文件 | 上游依赖 | 受影响域 | 相关依据绑定 | 什么时候读它 |")
A("|---|-------|--------|----------|------|----------|----------|--------------|--------------|")
WHEN = {
 "ontology": "写「项目单位概况/对象与关系」或需要实体类型与十类关系时",
 "argument_chain": "写必要性章、结论章，需要 Toulmin 形态与论证模式时",
 "scenario": "写风险章或做敏感性/多情景推演时",
 "variable": "写规模章、投资章，需要变量清单与量纲陷阱时",
 "task_dag": "编排多章起草顺序与前置依赖时",
 "function": "需要可复算函数与规则求值口径时",
 "rule": "写规模/投资/能耗章，需要公式与派生链时",
 "invariant": "成稿自检（一致性、冲突待审、阻塞规则）时",
 "skill": "选择抽取/写作技能组合时",
 "report_structure": "生成章节骨架、核销法定内容项时",
 "report_form": "确认必填字段与未知处理口径时",
 "prompt": "取提示词骨架（逐章实例见 style/section_prompts.yaml）时",
 "quality_gate": "出稿前跑三关口与依据可得性分级时",
 "reuse_strategy": "判断某历史资产可直接复用/参数化/重建/拒绝时",
 "entity_relation": "建实体实例与关系样本时",
 "cost_risk": "写投资章、风险章，需要造价构成与风险因子库时",
}
for i, d in enumerate(domains["domains"], 1):
    A(f"| {i} | `{d['id']}` | {d['core_domain']} | {d['asset_origin'].split('（')[0]} | `{d['file']}` | "
      f"{'、'.join(d['depends_on']) or '（根）'} | {len(d.get('impacted_assets', []))} | "
      f"{'、'.join(d.get('external_bindings', [])) or '—'} | {WHEN.get(d['id'],'—')} |")
A("")
A("**索引与依赖图**：`SHUFE-BDC-2019-001/reuse/domains.yaml`（含每域 `reusable_form` 摘要）、"
  "`SHUFE-BDC-2019-001/reuse/dependency_graph.yaml`（16 域依赖 + 变更影响传播）。")
A("")
A("**影响传播示例**（改一处会牵动谁）：")
A("")
for ex in dep_graph["impact_examples"]:
    A(f"- 变更 `{ex['changed_asset']}`（{ex['change']}）→ 受影响 **{ex['impacted_count']}** 个下游域")
A("")
A("## 二、扩展资产（16 域契约之外）")
A("")
A("kp 内置 16 域未包含下列两项，本包以独立文件承载：")
A("")
A("| 资产 | 文件 | 为什么沉淀 | 挂载域 | 什么时候读 |")
A("|------|------|-----------|--------|-----------|")
A(f"| **规范依赖** | `SHUFE-BDC-2019-001/reuse/regulatory_dependency.yaml` | "
  f"{reg_dep['reusable_form']['why_asset'][:70]}… | {'、'.join('`'+x+'`' for x in reg_dep['attached_to_domains'])} | "
  f"写技术章做规范判定、写各章核对引用时效时 |")
A(f"| **逐章提示词** | `SHUFE-BDC-2019-001/style/section_prompts.yaml` | "
  f"每章是不同的活，用一套通用提示词产出必然是同腔调流水账 | `prompt` | 起草任一章前 |")
A("")
A(f"> 契约说明：{reg_dep['contract_note']}")
A("")
A("## 三、资产的访问形式（重要）")
A("")
A("| 形式 | 适用于 | 目录 |")
A("|------|--------|------|")
A("| **① 注入** | constraints / meta / outline / gate / style / 术语表 —— 每章恒定 | 本目录三个索引文件 |")
A("| **② 工具调用** | 事实节点、规则、论断、原文切片、依据条款 —— 写到某章才取 | `graph/`、`chunks/`、`evidence/`、`external/` |")
A("| **③ 内嵌** | 冲突清单、缺口清单 —— 必须全程可见 | 已内嵌进 `推演写作输入包.md` §E/§F |")
A("| **✕ 不对外** | 原文全量、graph 整包、skeletons 全量、evidence 摘录全量 | 不给 |")
A("")
(W / "知识资产索引.md").write_text("\n".join(L), encoding="utf-8")

# ════════════════════════════════════════════════════ ④ 按章切片
CH.mkdir(parents=True, exist_ok=True)
sizes = {}
for i, ch in enumerate(L1, 1):
    sp = SP.get(ch)
    sub = [n for n in nodes if n["_chapter"] == ch]
    seen, uniq = set(), []
    for n in sorted(sub, key=lambda x: (x["subject"], x["predicate"], str(x["value"]))):
        if n["id"] in seen:
            continue
        seen.add(n["id"]); uniq.append(n)
    csub = [c for c in claims if chapter_of(c.get("source", "")) == ch]
    pi = (sp or {}).get("project_issues", {})
    M = []; B = M.append
    B(f"# 第 {i} 章切片 · {ch}")
    B("")
    B(f"> 按需取用文件。起草本章前读本文件 + `写作输入/推演写作输入包.md`（写作纪律与全局约束）。")
    B(f"> 章节族 `{sp['family'] if sp else '—'}`　切片：{len(uniq)} 个唯一事实节点 / {len(csub)} 条论断"
      + (f" / {len(pi.get('external_bindings', []))} 条依据绑定" if pi.get('external_bindings') else ""))
    B("")
    if sp:
        B("## 本章提示（prepare → 起草）")
        B("")
        B(f"- **核心问题**：{sp['focus']}")
        B(f"- **形态**：{sp['shape']}　｜　**评审盯什么**：{sp['review']}")
        if sp["slice"]["predicates"]:
            B(f"- **必写取值点**：**{'；'.join(sp['slice']['predicates'])}**")
        B("- **起草前置**：")
        for x in sp["prepare"]:
            B(f"  - {x}")
        B("- **必须写到**：")
        for x in sp["must_state"]:
            B(f"  - {x}")
        B("- **本章特有的坑**：")
        for x in sp["must_not"]:
            B(f"  - {x}")
        B("")
    B("## 本章事实输入（正文写 {{node:N-xxxxxxxxxxxx}}）")
    B("")
    if uniq:
        B("| 节点ID | 主题 | 属性 | 值 | 单位 | 定位 |")
        B("|--------|------|------|----|------|------|")
        for n in uniq:
            fm = FACT_META.get((n["subject"], n["predicate"], str(n["value"])), {})
            loc = fm.get("locator", "") or n["_section"]
            v = str(n["value"]).replace("|", "\\|")
            if len(v) > 110:
                v = v[:108] + "…"
            B(f"| `{n['id']}` | {n['subject']} | {n['predicate']} | {v} | {n['unit']} | {loc} |")
    else:
        B("**本章无专属事实节点。**" +
          ("本章为复述章，**不得出现一个新数**。" if sp and sp["family"] == "conclusion" else "须从相邻章借或整段留白。"))
    B("")
    if csub:
        B("## 本章论断（Toulmin 六元组）")
        B("")
        for c in csub:
            B(f"### {c['id']}　`{c.get('type','')}` / `{c.get('claim_type','')}`")
            B("")
            B(f"- **论断**：{c.get('text','')}")
            t = c.get("toulmin") or {}
            for k, cn in (("claim", "论点"), ("grounds", "论据"), ("warrant", "保证"),
                          ("backing", "支撑"), ("qualifier", "限定"), ("rebuttal", "反驳")):
                v = t.get(k, "")
                if k == "warrant" and (not v or "未" in v[:6]):
                    v = "**（原文未给出——不得代拟）**"
                B(f"  - {cn}：{v}")
            evs = [e for e in c.get("evidence_refs", []) if e in CURATED_EV]
            if evs:
                B(f"- **证据**：" + "；".join(
                    f"`{e}`（{CURATED_EV[e].get('kind')}｜{CURATED_EV[e].get('doc','')[:28]}"
                    f"{'　'+CURATED_EV[e].get('locator','') if CURATED_EV[e].get('locator') else ''}）" for e in evs))
            else:
                B("- **证据**：**（无——已登记缺口，不得硬撑结论）**")
            B("")
    if pi.get("external_bindings"):
        B("## 本章依据绑定（判定见 §G / 06 号报告）")
        B("")
        for b in pi["external_bindings"]:
            r = VERDICT.get(b["id"])
            B(f"### `{b['id']}` {ICON.get(b['verdict'],'')} {b['verdict']}　角色 `{b['role']}`")
            B("")
            if r:
                B(f"- **报告取值**：{r['report']['value']}")
                B(f"- **依据**：{'；'.join(r['basis_titles'])}")
                B(f"- **判定**：{r['finding']}")
                for br in r.get("branches", []):
                    B(f"  - 若 {br['假设']} ⇒ {br['结论']}")
                if r.get("needs_to_verify"):
                    B(f"- **须核对**：{'；'.join(r['needs_to_verify'])}")
            B("")
    if pi.get("conflicts"):
        B("## 本章待审冲突（保留并列，不得裁决）")
        B("")
        for c in pi["conflicts"]:
            B(f"- {c['subject']} · {c['predicate']} ⇒ `{'` / `'.join(c['values'])}`")
        B("")
    if pi.get("gaps"):
        B("## 本章缺口（正文留白）")
        B("")
        for g in pi["gaps"]:
            B(f"- `{g['id']}` **{g['subject']}**（{g['type']}）")
        B("")
    fp = CH / f"{i:02d}-{ch}.md"
    fp.write_text("\n".join(M), encoding="utf-8")
    sizes[f"{i:02d}-{ch}"] = fp.stat().st_size

print(json.dumps({
    "files": {
        "写作输入/推演写作输入包.md": (W / "推演写作输入包.md").stat().st_size,
        "写作输入/章节提示词索引.md": (W / "章节提示词索引.md").stat().st_size,
        "写作输入/知识资产索引.md": (W / "知识资产索引.md").stat().st_size,
    },
    "chapter_slices": len(sizes),
    "chapter_slice_bytes_total": sum(sizes.values()),
    "largest": sorted(sizes.items(), key=lambda x: -x[1])[:3],
    "smallest": sorted(sizes.items(), key=lambda x: x[1])[:3],
}, ensure_ascii=False, indent=2))
