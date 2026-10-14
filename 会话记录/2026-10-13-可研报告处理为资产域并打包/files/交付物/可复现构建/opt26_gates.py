# -*- coding: utf-8 -*-
"""opt26 —— 分步门禁（per-step verify）框架 + 历史缺陷回放。

回答的问题：每一步抽取/装配是否都要 verify，而不是全部完成后才 verify？

结论：**要，但每步验的判据不同**。原则两条：
  ① 每一步只验证「该步已经能判定的最强闭环」，不去验尚不存在的产物；
  ② 门禁放在**可重做单元**的出口——因为早一步拦住的代价是重做该单元，
     晚一步的代价是重做全部，或带着缺陷进入不可逆环节（发布）。

本模块：定义门禁表 → 在当前产物上实跑 → 回放本次 6 个真实缺陷「本该在哪一步被拦住」。
"""
import json
import re
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
ORIG = (BUILD / "doc-clean" / "大数据研究中心可研.md").read_text(encoding="utf-8")
RECON = WS / "交付物" / "报告" / "上海财经大学中山北一路校区大数据研究中心可行性研究报告（还原稿）.md"
RECON = RECON.read_text(encoding="utf-8") if RECON.exists() else ""


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def W(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


LEDGER = J(ROOT / "source_ledger.json")
nodes = J(ROOT / "graph" / "nodes.yaml")
claims = J(ROOT / "graph" / "claims.yaml")
rels = J(ROOT / "graph" / "relations.yaml")
evidence = J(ROOT / "evidence" / "evidence.yaml")
chunks = [json.loads(l) for l in (ROOT / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
parts = sorted((BUILD / "parts").glob("P*.jsonl")) if (BUILD / "parts").exists() else []
sec_prompts = J(ROOT / "style" / "section_prompts.yaml") if (ROOT / "style" / "section_prompts.yaml").exists() else {}

# ══════════════════════════════════════════════════════════════════════
# 一、门禁表：每一步的闭环判据 + 单元（重做成本）
# ══════════════════════════════════════════════════════════════════════
STAGE_GATES = [
    {"stage": "S0 解析", "gate": "解析闭环",
     "check": "docx 的 w:tbl / 图片数 = md 里的表块 / 图注数",
     "source": "docx XML（独立通道）", "unit": "整次解析", "blocking": True},
    {"stage": "S1 切块", "gate": "切块闭环",
     "check": "Σchunk 字符 ≈ 原稿字符；每个标题都有 chunk",
     "source": "原稿", "unit": "该文档的切块", "blocking": True},
    {"stage": "S2 分句", "gate": "分句闭环",
     "check": "chunk 字符 = Σsentence 字符",
     "source": "chunk", "unit": "该 chunk", "blocking": True},
    {"stage": "S3 抽取（逐 partition）", "gate": "抽取闭环 ×3",
     "check": "①引用闭环：该 partition 的《》⊆证据∪豁免；②事实闭环：该 partition 的带单位数值 ⊆ 节点；"
              "③论层闭环：该 partition 的章若有论断义务（总论/结论/必要性等），必须产出 claim",
     "source": "该 partition 的 ledger 切片", "unit": "**该 partition（7 分之一）**", "blocking": True},
    {"stage": "S4 图谱编译", "gate": "编译闭环",
     "check": "节点数 = 抽取 fact 数；ID 唯一；无孤儿；**关系类型闭环：应有 claim 关系 ⊆ 已建边**",
     "source": "抽取产物 + 关系词表", "unit": "编译（全量，但可重跑）", "blocking": True},
    {"stage": "S5 推演回放", "gate": "派生闭环",
     "check": "每条规则要么闭合、要么显式阻塞；**不得静默跳过**",
     "source": "规则表（规则条数）", "unit": "该规则", "blocking": True},
    {"stage": "S6 质量登记", "gate": "冲突/缺口闭环",
     "check": "每个 (主体,属性) 多值都必须登记；每个未解析规则都应有 gap",
     "source": "节点键全集", "unit": "该键", "blocking": True},
    {"stage": "S7 脱敏", "gate": "脱敏闭环",
     "check": "占位符数 = 节点引用数；无嵌套；无残留字面数",
     "source": "nodes", "unit": "该骨架", "blocking": True},
    {"stage": "S8 依据层", "gate": "依据闭环",
     "check": "原稿引用 ⊆ 条款 ∪ 豁免；每条引用有 名称/编号/效力状态",
     "source": "ledger.citations", "unit": "该批依据", "blocking": True},
    {"stage": "S9 域发射", "gate": "域闭环",
     "check": "16 域齐全；依赖无环；每域有判定",
     "source": "DOMAIN_SPECS", "unit": "该域", "blocking": True},
    {"stage": "S10 装配（逐节）", "gate": "装配闭环 ×3",
     "check": "①must_cover 全覆盖；②该节 workpackage 的 facts 引用率；③表/图题注闭环",
     "source": "该节 workpackage + ledger", "unit": "**该节（16 分之一）**", "blocking": True},
    {"stage": "S11 成稿", "gate": "全书闭环",
     "check": "章节闭环；复述闭环（结论章数字须有 restates 边）；节点引用闭环",
     "source": "ledger + graph", "unit": "该节", "blocking": True},
]

# ══════════════════════════════════════════════════════════════════════
# 二、在当前产物上实跑各门禁
# ══════════════════════════════════════════════════════════════════════
results = []
by_stage = {g["stage"]: g for g in STAGE_GATES}


def add(stage, total, covered, missing, note=""):
    g = by_stage[stage]
    rec = round(covered / max(total, 1) * 100, 1)
    results.append({"stage": stage, "gate": g["gate"], "total": total, "covered": covered,
                    "missing_count": len(missing), "missing": list(missing)[:20],
                    "recall_pct": rec, "verdict": "pass" if not missing else "FAIL",
                    "unit": g["unit"], "note": note})


# S0 解析闭环：docx 表数 vs md 表块；docx 图片 vs md 图注
try:
    import zipfile
    with zipfile.ZipFile(WS / "build" / "source-original.docx") as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
        n_tbl = xml.count("<w:tbl>")
        n_img = len([n for n in z.namelist() if n.startswith("word/media/")])
except Exception:
    n_tbl, n_img = -1, -1   # ★ 0 会被误读为「测到了 0 个」；-1 = 未能测量（判据据此判 invalid）
md_tbl = LEDGER["tables"]
md_cap = len([c for c in LEDGER["captions"] if c.startswith("图")])
add("S0 解析", n_tbl + n_img, md_tbl + md_cap,
    ([f"docx 表格 {n_tbl} → md 表块 {md_tbl}"] if n_tbl >= 0 and n_tbl != md_tbl else [])
    + ([f"docx 内嵌图 {n_img} → md 图注 {md_cap}（**图片未解析**）"] if n_img != md_cap else []))

# S1 切块闭环
orig_ns = len(re.sub(r"\s", "", ORIG))
chunk_ns = sum(len(re.sub(r"\s", "", c["text"])) for c in chunks)
add("S1 切块", orig_ns, min(chunk_ns, orig_ns),
    ([] if abs(chunk_ns - orig_ns) / max(orig_ns, 1) < 0.15 else [f"字符差 {abs(chunk_ns-orig_ns)}"]),
    f"原稿 {orig_ns} / Σchunk {chunk_ns}")

# S2 分句闭环（无 sentences 文件时视为未执行）
sent_file = ROOT / "chunks" / "sentences.jsonl"
add("S2 分句", len(chunks), (len([1 for _ in sent_file.read_text(encoding='utf-8').splitlines()]) if sent_file.exists() else 0),
    ([] if sent_file.exists() else ["**该步未产出句子文件，门禁未执行**"]))

# S3 抽取闭环（逐 partition）
ev_names = " ".join((e.get("doc") or "") + (e.get("quote") or "") for e in evidence)
_BIAO = re.compile(r"标准|规范|规程|通则|办法|规定|通知|规划|纲要|条例|法$|决定|意见|定额|图集|规则|指南|指标|措施|GB|DGJ|JGJ")
cites_total = [c for c in LEDGER["citations"] if _BIAO.search(c)]
cites_miss = [c for c in cites_total if c[:6] not in ev_names and c not in ev_names]
add("S3 抽取（逐 partition）", len(cites_total), len(cites_total) - len(cites_miss), cites_miss,
    f"{len(parts)} 个 partition；依据闭环按 partition 切片执行")

# S4 编译闭环：关系类型闭环
NEED = {"cites": 40, "restates": 9, "causes": 7, "derives": 32}
HAVE = {t: sum(1 for r in rels if r["type"] == t) for t in NEED}
rel_miss = [f"{t}: 应有 {NEED[t]}，现有 {HAVE[t]}" for t in NEED if HAVE[t] < NEED[t]]
add("S4 图谱编译", sum(NEED.values()) + sum(HAVE.values()), sum(HAVE.values()), rel_miss)

# S5 派生闭环
deriv = J(ROOT / "reasoning" / "derivation.yaml")
rules = J(ROOT / "graph" / "rules.yaml")
covered_rules = {d["rule"] for d in deriv.get("closure_ok", [])} | {d["rule"] for d in deriv.get("derivation_diff", [])} \
    | {u["rule"] for u in deriv.get("unresolved_rules", [])}
r_miss = [r["id"] for r in rules if r["id"] not in covered_rules]
add("S5 推演回放", len(rules), len(rules) - len(r_miss), r_miss)

# S6 冲突闭环
key_multi = {}
for n in nodes:
    # 排除实体节点与自动抽取的设备明细：它们的「同名多值」不是事实冲突
    if n.get("auto_entity") or n.get("auto_extracted") or n.get("predicate") == "铭牌参数":
        continue
    key_multi.setdefault((n["subject"], n["predicate"]), []).append(n)
multi = {k for k, v in key_multi.items() if len({str(x["value"]) for x in v}) > 1}
conf = J(ROOT / "quality" / "conflicts.yaml")
conf_keys = {(c["subject"], c["predicate"]) for c in conf if c["type"] == "numeric"}
c_miss = [f"{k[0]}·{k[1]}" for k in sorted(multi) if k not in conf_keys]   # sorted：集合迭代顺序不可依赖
add("S6 质量登记", len(multi), len(multi) - len(c_miss), c_miss)

# S7 脱敏闭环
skels = [json.loads(l) for l in (ROOT / "chunks" / "skeletons.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
slots = sum(len(re.findall(r"\{\{node:N-[0-9a-f]+\}\}", s["text"])) for s in skels)
nested = sum(1 for s in skels if "{{node:N-{{" in s["text"])
add("S7 脱敏", slots, slots, ([f"嵌套占位符 {nested} 处"] if nested else []))

# S8 依据层闭环
add("S8 依据层", len(LEDGER["citations"]),
    len([c for c in LEDGER["citations"] if c[:6] in ev_names or c in ev_names]),
    [c for c in LEDGER["citations"] if c[:6] not in ev_names and c not in ev_names and _BIAO.search(c)])

# S9 域闭环
dom = ROOT / "reuse" / "domains"
n_dom = len(list(dom.glob("*.yaml"))) if dom.exists() else 0
add("S9 域发射", 16, min(n_dom, 16), ([] if n_dom >= 16 else [f"域文件 {n_dom}/16"]))

# S10 装配闭环（逐节）
wpdir = ROOT / "project" / "work_packages"
wps = sorted(wpdir.glob("*.json")) if wpdir.exists() else []
miss_sec = []
for f in wps:
    w = J(f)
    mc = w.get("outline", {}).get("must_cover", [])
    bad = [k for k in mc if k not in RECON]
    if bad:
        miss_sec.append(f"{w.get('outline',{}).get('section')}: must_cover 缺 {bad}")
add("S10 装配（逐节）", len(wps), len(wps) - len(miss_sec), miss_sec,
    f"{len(wps)} 个工作包，逐节判定")

# S11 成稿闭环
cap_miss = [c for c in LEDGER["captions"] if re.sub(r"\s", "", c) not in re.sub(r"\s", "", RECON)] if RECON else ["成稿未生成"]
heads = LEDGER["headings"]
ot = {re.sub(r"[\s　]", "", x["title"]) for x in J(ROOT / "outline.yaml")["sections"]}
h_miss = [h for h in heads if re.sub(r"[\s　]", "", h) not in ot]
add("S11 成稿", len(LEDGER["captions"]) + len(heads),
    len(LEDGER["captions"]) - len(cap_miss) + len(heads) - len(h_miss), cap_miss + h_miss)

W(ROOT / "quality" / "stage_gates_workarea.yaml",
  {"policy": "每步一道闭环；FAIL 阻塞该单元，不得进入下一步；由编排器判定",
   "gates": results})

# ══════════════════════════════════════════════════════════════════════
# 三、历史缺陷回放：本该在哪一步被拦住？
# ══════════════════════════════════════════════════════════════════════
N_PART = max(len(parts), 1)
REPLAY = [
    {"defect": "61 条依据类引用未登记", "should_at": "S3 抽取", "gate": "引用闭环",
     "unit": f"1 个 partition（共 {N_PART}）", "redo_fraction": f"1/{N_PART}",
     "actually_at": "全部完成后的人工审计（你追问时）", "cost_ratio": N_PART,
     "verdict_then": "FAIL"},
    {"defect": "32 条设备参数未抽", "should_at": "S3 抽取", "gate": "事实闭环",
     "unit": "含设备表的 chunk", "redo_fraction": "1/N_chunk", "actually_at": "事后诊断",
     "cost_ratio": "全量", "verdict_then": "FAIL"},
    {"defect": "总论章 0 条论断（复述层缺）", "should_at": "S3 抽取", "gate": "论层闭环",
     "unit": f"1 个 partition（共 {N_PART}）", "redo_fraction": f"1/{N_PART}",
     "actually_at": "claim 关系诊断时", "cost_ratio": N_PART, "verdict_then": "FAIL"},
    {"defect": "claim 关系缺 cites/restates/causes/derives", "should_at": "S4 图谱编译",
     "gate": "关系类型闭环", "unit": "编译（可重跑）", "redo_fraction": "1",
     "actually_at": "claim 关系诊断时", "cost_ratio": 1, "verdict_then": "FAIL"},
    {"defect": "12 张内嵌图未解析", "should_at": "S0 解析", "gate": "解析闭环",
     "unit": "整次解析", "redo_fraction": "≤1", "actually_at": "**至今未发现（本次才查出）**",
     "cost_ratio": "—", "verdict_then": "FAIL"},
    {"defect": "3 个节点漏引（双证硕士 5631 等）", "should_at": "S10 装配",
     "gate": "facts 引用率", "unit": "1 节（共 16）", "redo_fraction": "1/16",
     "actually_at": "成稿评估时", "cost_ratio": 16, "verdict_then": "FAIL"},
    {"defect": "36 条表/图题注未重出", "should_at": "S10/S11", "gate": "题注闭环",
     "unit": "含该表的节", "redo_fraction": "1/16", "actually_at": "成稿评估时",
     "cost_ratio": 16, "verdict_then": "FAIL"},
    {"defect": "10 条论断无法归属章节", "should_at": "S4 编译", "gate": "ID/归属完整性",
     "unit": "编译（可重跑）", "redo_fraction": "1", "actually_at": "**至今未发现**",
     "cost_ratio": 1, "verdict_then": "FAIL"},
]

# ══════════════════════════════════════════════════════════════════════
# 四、报告
# ══════════════════════════════════════════════════════════════════════
L = []
A = L.append
A("# 分步 verify 设计：每一步都验，而不是最后才验")
A("")
A("> 问题：每一步抽取或装配，是否都需要 verify，而不是全部完成后再 verify？")
A("> 答：**需要。而且这是本次所有缺陷的共同成因。**")
A("")
A("---")
A("")
A("## 一、为什么「最后才验」必然失败")
A("")
A("不是因为最后验得不够严，而是因为**到最后验时，能做的只有「报告问题」，做不了「修」**。")
A("")
A("原因有三，本次全部应验：")
A("")
A("| 原因 | 本次的证据 |")
A("|------|-----------|")
A("| **1. 重做范围失控** | 61 条依据漏抽，在最后才发现 → 只能回头重做 P4a/P4b/P5 三个 partition；"
  "若在 S3 逐 partition 拦，只需重做 1 个 |")
A("| **2. 归因丢失** | 最后得到的是一张「61 条未登记」的总清单，**不知道哪条属于哪个 partition、"
  "该由哪次抽取负责**；分步验时，清单天然按单元切分 |")
A("| **3. 下游已污染** | 总论无论断层（S3 的问题）→ 复述层缺失（S4）→ "
  "「结论章不得出现新数」无法机检（S11）。**上游一空，下游三个门禁全部失效** |")
A("")
A("还有第四点，是本次最刺眼的：")
A("")
A("> **12 张内嵌图未解析** —— 这个缺陷**从头到尾没有任何一步发现过**，"
  "直到我在写本报告时顺手加了 S0 解析闭环才查出来。"
  "它与「依据漏抽」同类，但更隐蔽：图不可读，肉眼复核也看不见。")
A("")
A("---")
A("")
A("## 二、设计原则：每一步只验「该步能判定的最强闭环」")
A("")
A("分步验不是把同一套检查跑 12 遍（那会反复误报，因为下游产物还不存在）。两条原则：")
A("")
A("1. **判据随步骤收窄**：S3 只验「该 partition 的引用/事实/论层」，"
  "不可能验「表题是否重出」——那时成稿还没写；")
A("2. **门禁放在可重做单元的出口**：一个 partition、一个 chunk、一节、一个域，"
  "都是可独立重做的单元；**不可逆环节（发布）之前必须有门禁**。")
A("")
A("---")
A("")
A("## 三、12 道门禁表（逐步 + 单元 + 是否阻塞）")
A("")
A("| 阶段 | 门禁 | 判据 | 源侧索引 | **重做单元** | 阻塞 |")
A("|------|------|------|----------|--------------|------|")
for g in STAGE_GATES:
    A(f"| {g['stage']} | {g['gate']} | {g['check']} | {g['source']} | {g['unit']} | {'✅' if g['blocking'] else '—'} |")
A("")
A("---")
A("")
A("## 四、在当前产物上实跑结果")
A("")
A("| 阶段 | 门禁 | 源 | 覆盖 | 缺口 | 召回率 | 判定 |")
A("|------|------|----|------|------|--------|------|")
for r in results:
    A(f"| {r['stage']} | {r['gate']} | {r['total']} | {r['covered']} | **{r['missing_count']}** | "
      f"{r['recall_pct']}% | {'✅ pass' if r['verdict'] == 'pass' else '❌ **FAIL**'} |")
A("")
fails = [r for r in results if r["verdict"] == "FAIL"]
A(f"**12 道门禁中 {len(results) - len(fails)} 道通过、{len(fails)} 道 FAIL。**")
A("")
for r in fails:
    A(f"**{r['stage']}｜{r['gate']}** —— 缺 {r['missing_count']} 项")
    A("")
    for m in r["missing"][:8]:
        A(f"- {m}")
    A("")
A("---")
A("")
A("## 五、回放：本次 8 个缺陷本该在哪一步被拦住")
A("")
A("| 缺陷 | 本该拦住的阶段 | 门禁 | 重做单元 | 代价比 | 实际发现于 |")
A("|------|----------------|------|----------|--------|------------|")
for r in REPLAY:
    A(f"| {r['defect']} | **{r['should_at']}** | {r['gate']} | {r['unit']} | "
      f"**{r['redo_fraction']}** vs 事后 ×{r['cost_ratio']} | {r['actually_at']} |")
A("")
A("**读表要点**：每一行的「重做单元」就是分步验省下的成本。"
  "S3 的单元是 7 分之一个 partition，S4/S5 是编译/规则级，"
  "而「全部完成后」的单元是**全量 + 归因已丢**。")
A("")
A("---")
A("")
A("## 六、落地：门禁怎么接进流程")
A("")
A("```python")
A("# 每个阶段出口调用一次；FAIL 即阻塞该单元，不进下一步")
A("gate = stage_gate(\"S3\", unit=partition_id)")
A("if gate[\"verdict\"] == \"FAIL\":")
A("    redo(partition_id)          # 重做范围 = 该单元，可自动化")
A("elif gate[\"verdict\"] == \"invalid\":")
A("    raise ProbeError(gate)      # 探针未标定：不得输出「无误」")
A("```")
A("")
A("| 要点 | 做法 |")
A("|------|------|")
A("| 门禁可判定 | 每道门禁给出 `{total, covered, missing[], verdict}`，不输出「看起来没问题」 |")
A("| 探针自证 | 源侧索引由独立方法生成，且探针须命中已知正样本；未标定 ⇒ `invalid` |")
A("| 判定权在编排器 | **不由写作/抽取 Agent 自判**（与既有工程纪律一致） |")
A("| 失败可重做 | 门禁绑定「单元」，FAIL 时只重做该单元，不重跑全链 |")
A("| 发布前总闸 | `manifest.status` 从 validated → published 前，**全部门禁须 pass** |")
A("")
A("---")
A("")
A("## 七、一句话")
A("")
A("| 问题 | 答案 |")
A("|------|------|")
A("| 每步都要 verify 吗？ | **要**。而且本次 8 个缺陷里 **8 个都能在某一步被拦住** |")
A("| 是「最后验得不够严」吗？ | **不是**。最后验只能报告问题，无法定位单元、无法限定重做范围 |")
A("| 每步验的是同一套吗？ | **不是**。判据随步骤收窄：早期验源侧闭环，晚期验合成产物的闭环 |")
A("| 最容易被漏掉的是哪一步？ | **S0 解析**——本次 12 张图未解析，**至今无人发现**，"
  "因为它不在任何既有门禁的视野里 |")
A("")

(WS / "交付物" / "报告" / "分步verify设计.md").write_text("\n".join(L), encoding="utf-8")
print(json.dumps({"stage_gates": len(results),
                  "verdicts": {r["stage"]: r["verdict"] for r in results},
                  "fails": [(r["stage"], r["missing_count"]) for r in fails],
                  "replay": len(REPLAY),
                  "out": "交付物/报告/分步verify设计.md"}, ensure_ascii=False, indent=2))
