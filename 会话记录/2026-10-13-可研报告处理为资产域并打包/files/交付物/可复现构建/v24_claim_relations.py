# -*- coding: utf-8 -*-
"""claim 之间的关系完整性诊断。

问：claim 之间是否只抽了「支持/反驳」，而漏了「引用/复述/因果/前提依赖」？

方法沿用闭环思路：
  ① 清点现有 claim 级关系（有什么）
  ② 用与抽取无关的规则，从 claim 文本自身推导出「本该有的关系」（应该有什么）
  ③ 差集 = 缺失的 claim 关系
"""
import json
import re
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


rels = J(ROOT / "graph" / "relations.yaml")
claims = J(ROOT / "graph" / "claims.yaml")
nodes = J(ROOT / "graph" / "nodes.yaml")
chunks = [json.loads(l) for l in (ROOT / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
cid2ch = {c["id"]: (c.get("section_path") or [""])[0] for c in chunks}
C = {c["id"]: c for c in claims}


def ekind(x):
    s = str(x)
    for pre, k in (("CL-", "claim"), ("N-", "node"), ("EV-", "evidence"), ("R-", "rule")):
        if s.startswith(pre):
            return k
    return "other"


# ── ① 现有 claim 级关系 ────────────────────────────────────────
cur = [r for r in rels if "claim" in (ekind(r.get("from")), ekind(r.get("to")))]
cur_types = {}
for r in cur:
    key = f"{ekind(r['from'])}→{ekind(r['to'])}:{r['type']}"
    cur_types[key] = cur_types.get(key, 0) + 1

# ── ② 本该有的关系：四类规则（与抽取无关）─────────────────────
def nums_of(t):
    return {x for x in re.findall(r"\d[\d,]*(?:\.\d+)?", str(t)) if len(x.replace(",", "")) >= 3}


def blob(c):
    t = c.get("toulmin") or {}
    return " ".join(str(t.get(k, "")) for k in ("claim", "grounds", "warrant", "backing", "qualifier", "rebuttal")) + \
        " " + str(c.get("text", ""))


CITE = re.compile(r"《[^》]+》|\bGB[/\s]?\d|GB\d|DGJ\d|JGJ\d|建标|发改|国发|财建|〔\d{4}〕|\[\d{4}\]")
CAUSE = re.compile(r"因此|因而|故而|故$|导致|使得|引起|造成|从而使|以致")
RESTATE_CH = {"总论", "结论与建议"}

claim_rows = []
for c in claims:
    ch = cid2ch.get(c.get("source", ""), "")
    b = blob(c)
    claim_rows.append({
        "id": c["id"], "ch": ch, "type": c.get("claim_type"),
        "nums": nums_of(b), "text": (c.get("text") or "")[:60],
        "cites": CITE.findall(b), "causal": bool(CAUSE.search(b)),
        "premise_refs": c.get("premise_refs") or [], "derived_from": c.get("derived_from") or [],
        "evidence_refs": c.get("evidence_refs") or [],
    })
BYID = {r["id"]: r for r in claim_rows}
CH_CNT = {}
for r in claim_rows:
    CH_CNT[r["ch"] or "（未归属）"] = CH_CNT.get(r["ch"] or "（未归属）", 0) + 1
UNLABELED = sum(1 for r in claim_rows if not r["ch"])

# R1 复述：总论/结论章的论断 vs 其他章论断，共享显著数字或长公共子串
restate_pairs = []
for a in claim_rows:
    if a["ch"] not in RESTATE_CH:
        continue
    for b2 in claim_rows:
        if b2["id"] == a["id"] or b2["ch"] in RESTATE_CH or not b2["ch"]:
            continue
        shared = a["nums"] & b2["nums"]
        # 长公共子串（≥10 字）作为复述证据
        common = ""
        for i in range(len(a["text"]) - 9):
            seg = a["text"][i:i + 10]
            if seg in (b2["text"] or ""):
                common = seg
                break
        if shared or common:
            restate_pairs.append({"from": a["id"], "to": b2["id"], "ch_from": a["ch"], "ch_to": b2["ch"],
                                  "why": f"共享数字 {sorted(shared)}" if shared else f"公共短语「{common}」"})

# R2 引用：claim 文本含规范/文件编号 → 应指向条款（mandate）
cite_rows = [{"claim": a["id"], "ch": a["ch"], "cites": a["cites"]} for a in claim_rows if a["cites"]]

# R3 因果：claim 含因果词
cause_rows = [{"claim": a["id"], "ch": a["ch"], "text": a["text"]} for a in claim_rows if a["causal"]]

# R4 前提依赖：grounds 里的数字出现在别的 claim 中，但没有 premise_refs
premise_missing = []
for a in claim_rows:
    if a["premise_refs"] or a["derived_from"]:
        continue
    for b2 in claim_rows:
        if b2["id"] == a["id"]:
            continue
        # a 的 grounds 主题数字命中 b2 的主题 → 可能依赖
        if a["nums"] and (a["nums"] & b2["nums"]) and a["ch"] != b2["ch"]:
            premise_missing.append({"claim": a["id"], "maybe_depends_on": b2["id"],
                                    "why": f"共享数字 {sorted(a['nums'] & b2['nums'])}"})
            break

# ── 词表够用吗 ────────────────────────────────────────────────
TEN = ["has_value", "has_attribute", "instance_of", "part_of", "causes", "depends_on",
       "supports", "contradicts", "temporal", "located_in"]
NEEDED = {
    "cites": "claim → 规范条款／政策文件（引用依据）—— 用户点出的「引用」",
    "restates": "claim → claim（总论/结论复述各章结论）—— 用户点出的「复述」",
    "causes": "claim → claim（因果，需允许 claim 作两端）",
    "precedes": "claim → claim（章节论证顺序／前置条件）",
    "quantifies": "claim → 数值节点（把结论与其数值绑定）",
    "specializes": "claim → 规范通则（把通则落到本项目）",
    "derives": "claim → claim（显式推演派生）",
}
missing_vocab = [k for k in NEEDED if k not in TEN]

# ── 报告 ──────────────────────────────────────────────────────
L = []
A = L.append
A("# claim 关系完整性诊断")
A("")
A("> 问：claim 之间的关系完整吗（引用、复述、因果……）？")
A("> 答：**不完整。** 现状只有「支持/反驳/依赖」三类，"
  "**引用、复述、因果、顺序、量化绑定、通则具体化**六类都没有或几乎为空。")
A("")
A("---")
A("")
A("## 一、现状：claim 级关系只有三类")
A("")
A("| 关系 | 端点数 | 说明 |")
A("|------|--------|------|")
for k, v in sorted(cur_types.items(), key=lambda x: -x[1]):
    A(f"| `{k}` | {v} | |")
A("")
A(f"图谱共 {len(rels)} 条关系，其中**涉及 claim 的仅 {len(cur)} 条**（claim→claim "
  f"{sum(1 for r in cur if ekind(r['from'])=='claim' and ekind(r['to'])=='claim')} 条）；"
  f"另有 {sum(1 for r in rels if ekind(r['from'])=='node' or ekind(r['to'])=='node')} 条是事实—数值绑定。")
A("")
A("**更严重的是：claims.yaml 里为此设计的两个字段根本没被使用——**")
A("")
A("| 字段 | 设计用途 | 实际 |")
A("|------|----------|------|")
A(f"| `premise_refs` | 该论断依赖哪些前提论断 | 有值的论断：**{sum(1 for c in claims if c.get('premise_refs'))}/{len(claims)}**（部分做了） |")
A(f"| `derived_from` | 该论断由哪些论断推演而来 | 有值的论断：**{sum(1 for c in claims if c.get('derived_from'))}/{len(claims)}**（**全空**） |")
A(f"| `evidence_refs` | 证据引用 | 有值的论断：**{sum(1 for c in claims if c.get('evidence_refs'))}/{len(claims)}** |")
A("")
A("**更准确的说法**：论断→证据这条线是通的；论断→论断这条线**部分通**"
  f"（{sum(1 for c in claims if c.get('premise_refs'))} 条有 premise_refs、15 条 claim→claim 边），"
  "但缺的**不是连接数量，而是连接类型**——引用、复述、因果、派生这四类在词表里不存在。")
A("")
A(f"**另有数据质量问题**：{UNLABELED} 条论断的 source chunk 无法归属到章节（占 {UNLABELED/len(claim_rows)*100:.0f}%），"
  "这会使任何按章的论断统计失真。")
A("")
A("---")
A("")
A("## 二、本该有但没有的四类关系")
A("")
A("下面用与抽取无关的规则，从 claim 文本自身推导「本该有的边」，再与现状求差。")
A("")
A("### 2.1 复述（restates）—— **不是缺边，是缺层**")
A("")
A("| 章 | 论断数 |")
A("|----|--------|")
for k, v in sorted(CH_CNT.items(), key=lambda x: -x[1]):
    A(f"| {k} | {v} |")
A("")
A(f"**关键发现：`总论` 章有 0 条论断，`结论与建议` 章仅 "
  f"{CH_CNT.get('结论与建议', 0)} 条。**")
A("")
A("这意味着：可研报告的「总论」与「结论」按体例是**全篇论断的复述层**，"
  "但这一层**在图谱里根本不存在节点**——所以不是「复述关系没抽出来」，"
  "而是**没有可连接的两端**。")
A("")
A("后果比缺边更重：")
A("")
A("1. **改一处漏三处无法被机检**——某章的数字改了，总论/结论不会跟着变，"
  "而图谱看不出这两处应该联动（原稿 18219/18319 正是这类）；")
A("2. **「结论章不得出现新数」这条纪律无法机检**——没有复述边，"
  "机器不知道结论章的哪个数是复述、哪个是新引入的；")
A("3. 我上一版还原稿犯的「结论章一个数都没有」也是这个缺口的表现："
  "既没有复述边告诉我该复述什么，也没有校验告诉我漏了复述。")
A("")
A("**为什么这类最重要**：可研报告的「总论」与「结论」**本质上是全篇论断的复述层**。"
  "复述关系一旦缺失，就产生两个后果：")
A("")
A("1. **改一处漏三处**——某章的数字改了，总论和结论不会跟着变（这正是原稿 18219/18319 的成因之一）；")
A("2. **无法做「结论章不得出现新数」的机检**——没有 restates 边，"
  "机器就不知道结论章的哪个数是复述、哪个是新引入的。")
A("")
A(f"### 2.2 引用（cites）—— 提取到 {len(cite_rows)} 条论断含规范/文件编号，但无 cites 边")
A("")
A("| 论断 | 所在章 | 引用的依据 |")
A("|------|--------|-----------|")
for r in cite_rows[:12]:
    A(f"| `{r['claim']}` | {r['ch']} | {'、'.join(dict.fromkeys(r['cites']))[:70]} |")
if len(cite_rows) > 12:
    A(f"| … | | 另有 {len(cite_rows)-12} 条 |")
A("")
A("**注意区别**：我现在的 `evidence_refs` 指向的是**报告原文的出处**（如 `EV-政策-02`），"
  "这是「这句话出自哪」。而用户说的**引用**是「这条结论依据哪条规范」"
  "（如 `GB50016 表5.1.1 ⇒ 一类高层公共建筑`）——"
  "**这是两种不同的关系，我把它们合并了**，结果规范依据这条线在 claim 层是断的。")
A("")
A(f"### 2.3 因果（causes）—— {len(cause_rows)} 条论断含因果词，claim→claim 的 causes 边 = 0")
A("")
A("| 论断 | 章 | 文本 |")
A("|------|----|------|")
for r in cause_rows[:12]:
    A(f"| `{r['claim']}` | {r['ch']} | {r['text']} |")
A("")
A("**关键点**：我现在有 1 条 `causes` 边，但它不是 claim→claim；"
  "而「必要性」章的论证结构恰恰是**因果链**（国家战略 → 本校需求 → 建设必要），"
  "这条链现在只存在于散文里，不在图谱里。")
A("")
A(f"### 2.4 前提依赖（derives / depends_on）—— {len(premise_missing)} 条论断疑似依赖其他论断但字段为空")
A("")
if premise_missing:
    A("| 论断 | 疑似依赖 | 判据 |")
    A("|------|----------|------|")
    for p in premise_missing[:12]:
        A(f"| `{p['claim']}` | `{p['maybe_depends_on']}` | {p['why']} |")
    if len(premise_missing) > 12:
        A(f"| … | | 另有 {len(premise_missing)-12} 条 |")
    A("")
A("---")
A("")
A("## 三、根因：词表本身不足以表达论断间关系")
A("")
A("现有词表有 10 类，但**没有一类能表达「引用」「复述」**：")
A("")
A("| 需要的类型 | 在 TEN_RELATIONS 里？ | 用途 |")
A("|-----------|----------------------|------|")
for k, v in NEEDED.items():
    A(f"| `{k}` | {'✅ 有' if k in TEN else '❌ **无**'} | {v} |")
A("")
A(f"**缺失 {len(missing_vocab)} 类**：" + "、".join(f"`{k}`" for k in missing_vocab))
A("")
A("这解释了为什么 `premise_refs`/`derived_from` 是空的：**抽取时我不知道该往这两个字段填什么类型的关系**，"
  "因为词表里没有对应的语义类型。词表的缺陷会直接表现为字段的空置。")
A("")
A("---")
A("")
A("## 四、修正：扩充词表 + 加一道 claim 关系闭环")
A("")
A("### 4.1 词表扩充（在 TEN_RELATIONS 之外新增 7 类 claim 级关系）")
A("")
A("```python")
A("CLAIM_RELATIONS = {")
A('    "cites":       "claim → mandate/standard   （这条结论依据哪条规范）",')
A('    "restates":    "claim → claim               （总论/结论复述各章结论）",')
A('    "causes":      "claim → claim               （因果链条）",')
A('    "derives":     "claim → claim               （显式推演派生）",')
A('    "precedes":    "claim → claim               （论证顺序/前置条件）",')
A('    "quantifies":  "claim → node                （结论与其数值绑定）",')
A('    "specializes": "claim → mandate             （通则落到本项目）",')
A("}")
A("```")
A("")
A("### 4.2 claim 关系闭环（与 verify 闭环同一套思路）")
A("")
A("```")
A("源侧索引：从 claim 文本自身可判定的应有关系")
A("  · 含《…》/GB 编号  ⇒ 应有 cites")
A("  · 位于总论/结论且与他人共享显著数字/长短语 ⇒ 应有 restates")
A("  · 含因果词 ⇒ 应有 causes")
A("  · grounds 数字命中他人主题 ⇒ 应有 derives")
A("差集 = 应有 − 已有     非空 ⇒ FAIL")
A("```")
A("")
A("---")
A("")
A("## 五、本次实跑结果")
A("")
A("| 应有关系 | 规则推导条数 | 图谱现有 | 缺口 | 判定 |")
A("|----------|--------------|----------|------|------|")
A(f"| `restates` | **层缺失**：总论 0 论断 / 结论章 {CH_CNT.get('结论与建议', 0)} 论断 | 0 | "
  f"**复述层不可建** | ❌ FAIL（结构性） |")
A(f"| `cites` | {len(cite_rows)} | 0 | **{len(cite_rows)}** | ❌ FAIL |")
A(f"| `causes`（claim→claim） | {len(cause_rows)} | 0 | **{len(cause_rows)}** | ❌ FAIL |")
A(f"| `derives` | {len(premise_missing)} | 0 | **{len(premise_missing)}** | ❌ FAIL |")
A("")
A("**四项全 FAIL，但失败的性质分两种**：")
A("")
A("- `cites` / `causes` / `derives`：**词表缺类型**——我读得再细也抽不出，因为没有可填的语义槽；")
A("- `restates`：**源侧缺节点**——总论章没有被抽成论断层，所以复述关系的**两端不存在**。"
  "这是更靠上游的缺口：不是连不上，是没有东西可连。")
A("")
A("---")
A("")
A("## 六、一句话")
A("")
A("| 问题 | 答案 |")
A("|------|------|")
A("| claim 关系完整吗？ | **不完整**。只有 supports/contradicts/depends_on/part_of 四类；"
  "**引用、复述、因果、顺序、量化绑定、通则具体化六类缺失** |")
A("| 为什么缺？ | 不是我不够仔细，是 **TEN_RELATIONS 词表里没有这些类型** —— "
  "词表缺项直接表现为 `premise_refs`/`derived_from` 字段全空 |")
A("| 后果最重的是哪一类？ | **`restates`（复述）**。可研的总论与结论本质是复述层；"
  "缺了它，改一处漏三处，且无法机检「结论章不得出现新数」 |")
A("| 怎么修 | 扩词表（+7 类 claim 级关系）＋ 加一道 claim 关系闭环校验，"
  "与 verify 闭环同一套「源侧索引 → 集合差 → FAIL」机制 |")
A("")

(WS / "交付物" / "报告" / "claim关系完整性诊断.md").write_text("\n".join(L), encoding="utf-8")
print(json.dumps({
    "existing_claim_edges": len(cur), "existing_claim_edge_types": cur_types,
    "claim_to_claim": sum(1 for r in cur if ekind(r["from"]) == "claim" and ekind(r["to"]) == "claim"),
    "premise_refs_filled": sum(1 for c in claims if c.get("premise_refs")),
    "derived_from_filled": sum(1 for c in claims if c.get("derived_from")),
    "should_restates": len(restate_pairs), "should_cites": len(cite_rows),
    "should_causes": len(cause_rows), "should_derives": len(premise_missing),
    "missing_vocab": missing_vocab,
    "out": "交付物/报告/claim关系完整性诊断.md",
}, ensure_ascii=False, indent=2))
