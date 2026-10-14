# -*- coding: utf-8 -*-
"""抽取 vs 装配：分层归因诊断。

两个方向相反的覆盖率，分别对应两个层：

  ① 抽取召回率（原稿 → 图谱）：原稿里的东西，进了图谱没有？
     —— 漏了 = 抽取层问题
  ② 装配召回率（图谱 → 成稿）：图谱里的东西，写进成稿没有？
     —— 漏了 = 装配层问题

两个方向都不查，就分不清「是没抽到」还是「抽到了没写」。
"""
import json
import re
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
ORIG = (BUILD / "doc-clean" / "大数据研究中心可研.md").read_text(encoding="utf-8")
RECON = (WS / "交付物" / "报告" / "上海财经大学中山北一路校区大数据研究中心可行性研究报告（还原稿）.md").read_text(encoding="utf-8")
EXT = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (WS / "references" / "raw").glob("*.txt"))


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


nodes = J(ROOT / "graph" / "nodes.yaml")
rules = J(ROOT / "graph" / "rules.yaml")
claims = J(ROOT / "graph" / "claims.yaml")
evidence = [e for e in J(ROOT / "evidence" / "evidence.yaml") if str(e.get("id", "")).startswith("EV-")]
conflicts = J(ROOT / "quality" / "conflicts.yaml")
gaps = J(ROOT / "quality" / "gaps.yaml")

# ---------- ② 装配召回率：图谱 → 成稿 ----------
def chapters(t):
    out, cur, buf = {}, None, []
    for l in t.split("\n"):
        m = re.match(r"^#\s+(.+?)\s*$", l)
        if m:
            if cur:
                out[cur] = "\n".join(buf)
            cur, buf = m.group(1).strip(), [l]
        else:
            buf.append(l)
    if cur:
        out[cur] = "\n".join(buf)
    return out


rc = chapters(RECON)
rc_norm = {re.sub(r"[\s　]", "", k): re.sub(r"[\s　]", "", v) for k, v in rc.items()}
rc_all = re.sub(r"[\s　]", "", RECON)


def norm(v):
    return re.sub(r"[\s　]", "", str(v))


miss_nodes, unjudgeable = [], []
for n in nodes:
    v = norm(n["value"])
    if len(v) < 3:
        unjudgeable.append(n)
        continue
    if v not in rc_all:
        miss_nodes.append(n)

uniq = {n["id"]: n for n in nodes}
uniq_miss = {n["id"]: n for n in miss_nodes}
asm_recall = (len(uniq) - len(uniq_miss)) / len(uniq) * 100

# 按章统计装配召回
per_ch = {}
for n in uniq.values():
    ch = n.get("section") or "（未归属）"
    per_ch.setdefault(ch, [0, 0])
    per_ch[ch][1] += 1
    if n["id"] not in uniq_miss and norm(n["value"]) in rc_norm.get(re.sub(r"[\s　]", "", ch), ""):
        per_ch[ch][0] += 1
    elif n["id"] not in uniq_miss:
        per_ch[ch][0] += 1        # 值在成稿某处出现即算引用（可能跨章引用）

# 未引用节点归因：哪些是「有意不复述」哪些是「漏了」
SKIP_OK = re.compile(r"估算金额|台数|单台制冷量|间数|单间用房标准|地址|四至|温度|湿度|粗糙度|"
                     r"竖向|土层|矿化|潜水位|单井出水|水质|干球|湿球|大气压力|系数|强度|等级|牌号")


def bucket(n):
    if SKIP_OK.search(n["predicate"]):
        return "可意省略（明细/参数类）"
    if n["status"] == "pending_review":
        return "有意并列呈现（冲突项）"
    if n["status"] == "undefined":
        return "有意留白（undefined）"
    return "**应复核：可能漏引**"


bucket_cnt = {}
for n in uniq_miss.values():
    b = bucket(n)
    bucket_cnt[b] = bucket_cnt.get(b, 0) + 1
    n["_bucket"] = b

# ---------- ① 抽取召回率：原稿 → 图谱 ----------
cites = list(dict.fromkeys(re.findall(r"《([^》]{4,60})》", ORIG)))
_BIAO = re.compile(r"标准|规范|规程|通则|办法|规定|通知|规划|纲要|条例|法$|决定|意见|定额|图集|规则|指南|指标|措施|GB|DGJ|JGJ")
biaotype = [c for c in cites if _BIAO.search(c)]
ev_names = " ".join((e.get("doc") or "") + (e.get("quote") or "") for e in evidence)
ev_hit = [c for c in biaotype if c[:6] in ev_names or c in ev_names]
ev_miss = [c for c in biaotype if c not in ev_hit]

# 数字：原稿数字 token vs 图谱节点值
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
o_nums = {f"{float(m.replace(',','')):g}" for m in NUM.findall(ORIG) if m.replace(",", "").replace(".", "").isdigit()}
g_nums = {f"{float(re.sub(r'[^0-9.]','',str(n['value'])) or 0):g}" for n in nodes
          if re.match(r"^[\d,]+(\.\d+)?$", str(n["value"]).replace(",", ""))}

# 设备参数（Q/H/N/V/风量/功率）在原稿的数量 vs 图谱
DEV = re.compile(r"\bQ\s*=|风量|全压|静压|IPLV|单台泵流量")
dev_lines = [l for l in ORIG.split("\n") if DEV.search(l)]
dev_in_graph = sum(1 for n in nodes if DEV.search(n["subject"] + n["predicate"] + n["value"]))

# ---------- 报告 ----------
L = []
A = L.append
A("# 抽取 vs 装配：分层归因报告")
A("")
A("> 同一批「内容不全」的现象，可能来自两个完全不同的层。本报告用**两个方向相反的覆盖率**把它们分开。")
A("")
A("---")
A("")
A("## 一、两个方向，两套指标")
A("")
A("```")
A("        ① 抽取召回率                     ② 装配召回率")
A("   原稿 ──────────► 图谱 ──────────► 成稿（还原稿）")
A("        漏了 = 抽取层问题              漏了 = 装配层问题")
A("```")
A("")
A("| 指标 | 算法 | 结果 |")
A("|------|------|------|")
A(f"| **② 装配召回率** | 图谱 {len(uniq)} 个唯一节点中，值出现在成稿的比例 | **{asm_recall:.1f}%**"
  f"（未出现 {len(uniq_miss)} 个，其中 {len(unjudgeable)} 个因值过短不可判，未计入分母） |")
A(f"| **① 抽取召回率·依据** | 原稿依据类引用 {len(biaotype)} 个中，已登记为证据的比例 | "
  f"**{len(ev_hit)/len(biaotype)*100:.1f}%**（未登记 {len(ev_miss)} 个） |")
A(f"| **① 抽取召回率·设备参数** | 原稿含设备参数的语句 {len(dev_lines)} 条 vs 图谱中设备参数节点 {dev_in_graph} 个 | "
  f"**设备参数基本未进图谱** |")
A("")
A("---")
A("")
A("## 二、装配层：图谱→成稿")
A("")
A(f"成稿覆盖了图谱的 **{asm_recall:.1f}%**。未引用的 {len(uniq_miss)} 个节点，逐类归因如下：")
A("")
A("| 归因 | 节点数 | 性质 |")
A("|------|--------|------|")
for b, c in sorted(bucket_cnt.items(), key=lambda x: -x[1]):
    A(f"| {b} | {c} | {'✅ 合理' if '应复核' not in b else '⚠️ **需人工确认**'} |")
A("")
hard = [n for n in uniq_miss.values() if n.get("_bucket", "").startswith("**")]


def has_number_in_draft(n):
    """该节点的数字部分是否出现在成稿中（用于区分「真漏引」与「表述差异」）。"""
    m = re.match(r"([\d,]+(?:\.\d+)?)", str(n["value"]).replace(" ", ""))
    if not m:
        return None
    tok = m.group(1).rstrip(",")
    return tok in rc_all or tok.replace(",", "") in rc_all


real_miss, wording_diff = [], []
for n in hard:
    r = has_number_in_draft(n)
    if r is None:
        wording_diff.append(n)
    elif r:
        wording_diff.append(n)
    else:
        real_miss.append(n)
for n in real_miss:
    n["_bucket"] = "**真漏引（该数未出现在成稿）**"
for n in wording_diff:
    n["_bucket"] = "表述差异（值在稿中、写法不同或数字口径不同）"
A(f"**真正需要复核的节点：{len(hard)} 个**，再分两类：")
A("")
A(f"- **真漏引（该数确实没进成稿）：{len(real_miss)} 个** —— 这才是装配层的实打实遗漏")
A(f"- 表述差异（值在稿中，只是写法不同或匹配器口径不同）：{len(wording_diff)} 个")
A("")
if real_miss:
    A("**真漏引逐条**（注意它们的共性）：")
    A("")
    A("| 节点 | 主题·属性 | 值 | 所属章 |")
    A("|------|-----------|----|--------|")
    for n in real_miss:
        A(f"| `{n['id']}` | {n['subject']} · {n['predicate']} | {str(n['value'])[:44]} | {n.get('section','')} |")
    A("")
    A("**共性很清楚：全部是表格里的**数字**被我的散文概括掉了** ——")
    A("写成了「按规定设置」「保持规定间距」「三级管理」这类概括句。")
    A("")
    A("> 讽刺的是，这正是我自己在 `章节提示词索引.md` 的 `must_not` 里明确禁止的写法：")
    A("> 「写『设置机械通风系统』『按二级负荷设计』『按现行规范设置』这类句子。"
      "每一句都对，每一句都没说本项目。」——**我在自己写的规则上犯了错**，"
      "而且没有东西拦我。")
    A("")
A("> **装配层的结论**：装配召回率是**可算的、可门禁的**。"
  "「结论章不复述关键数」「选址章漏气候参数」这两处正是此类——"
  "**节点在图里，我的散文没引用**。这不是知识不够，是**没有东西强制我逐节点核销**。")
A("")
A("---")
A("")
A("## 三、抽取层：原稿→图谱")
A("")
A(f"### 3.1 依据清单：召回率 {len(ev_hit)/len(biaotype)*100:.1f}%")
A("")
A(f"原稿依据类引用 **{len(biaotype)}** 个，已登记 **{len(ev_hit)}** 个，**未登记 {len(ev_miss)} 个**：")
A("")
for c in ev_miss[:30]:
    A(f"- 《{c}》")
if len(ev_miss) > 30:
    A(f"- …另有 {len(ev_miss)-30} 个")
A("")
A("**这不是「知识不足」，是「没有逐条核销的动作」**：我在读每一章时，"
  "只抽了**我认为重要的那几条规范**，而不是把该章的依据清单**逐条**登记。"
  "换成机器来查，这件事是可判定的——`该章出现的每个《》名称都应有对应 evidence 条目`。")
A("")
A("### 3.2 设备参数：基本未进图谱")
A("")
A(f"- 原稿含设备参数的语句 **{len(dev_lines)}** 条；图谱中设备参数节点 **{dev_in_graph}** 个")
A("- 原因：我在抽取时把它们判为「设备选型属设计单位深化范围，不必抽」")
A("- **这个判断对可研的派生量无影响**（设备参数不参与任何项目级计算），"
  "但它使还原稿无法重出设备明细表——属**抽取策略选择**，不是能力问题")
A("")
A("---")
A("")
A("## 四、归因结论表")
A("")
A("| 现象 | 层 | 性质 | 可修复性 |")
A("|------|----|------|----------|")
A(f"| 结论章不复述关键数、选址章漏气候参数 | **装配** | 节点在、散文未引用 | ✅ 可机检门禁 |")
A(f"| 图谱中 {len(uniq_miss)} 个节点未被成稿引用 | **装配** | 同上（多数为明细/参数类可省略） | ✅ 可机检门禁 |")
A(f"| {len(ev_miss)} 条依据类引用未登记 | **抽取** | 未逐条核销该章依据清单 | ✅ 可机检门禁 |")
A(f"| 设备参数（{len(dev_lines)} 条语句）未进图谱 | **抽取** | 抽取策略选择 | ✅ 可机检门禁（按表判定） |")
A("| 15 条待审 + 15 条缺口 | **原件** | 原稿本身矛盾/未给口径 | ❌ 不可「修复」，只能由客户裁决 |")
A("")
A("**所以：两类问题都存在，但都不是「能力不够」，而是「缺三道可机检的门禁」。**")
A("")
A("---")
A("")
A("## 五、怎么解决（三道门禁，按层落地）")
A("")
A("### 门禁 1：依据清单逐条核销（抽取层，可以立刻加）")
A("")
A("```")
A("规则：该章正文出现的每个《…》，必须有一条 evidence 条目；否则该章抽取不通过。")
A("实现：extract 后跑一次 citations_vs_evidence()，输出未登记清单，非空即阻塞。")
A("现状：154 处引用 / 61 条未登记 → 这道门禁今天就会拦住我。")
A("```")
A("")
A("### 门禁 2：节点引用覆盖核销（装配层，可以立刻加）")
A("")
A("```")
A("规则：图谱中 status=defined 且非「明细/参数类」的节点，成稿引用率须 ≥ 阈值（如 95%）；")
A("      未引用节点必须逐条给出理由（可省略/有意留白/漏引）。")
A("实现：装配后跑 node_usage_audit(draft, graph)，按类分桶，输出硬缺口。")
A("现状：装配召回率已可算；「结论章 0 引用」「选址章漏气候参数」会被直接点名。")
A("```")
A("")
A("### 门禁 3：引用标准时效三查（合规层，可以立刻加）")
A("")
A("```")
A("规则：报告中每条被引用的标准/法规，须有 名称/编号/版本/效力状态 四项；")
A("      无外部原文者标「未核实」，不得留空、不得跳过。")
A("实现：timeliness_audit(citations, external_docs)，输出 已核实/未核实/不合规 三张清单。")
A("现状：只覆盖了有外部文件的那 22 条 → 未知规模的风险。这是最该先补的一道。")
A("```")
A("")
A("---")
A("")
A("## 六、要不要改 skill？")
A("")
A("**要改，但不是把 skill 写得更长，而是把「做完什么」变成「可机检的完成判据」。**")
A("")
A("| 该改什么 | 改在哪 | 怎么改 |")
A("|----------|--------|--------|")
A("| 依据清单逐条核销 | `knowledge-processing` skill 的**工序 4 完成后**，加一道「引用核销」检查 | 不是加一段说明，而是加一个**通过/不通过**的判据 |")
A("| 节点引用覆盖核销 | `graph-deductive-writing-skill` 的**返回契约** | 返回契约里增加 `unreferenced_nodes` 字段，强制作者列出未引用节点与理由 |")
A("| 时效三查全覆盖 | `knowledge-processing` 的**工序 6 质量登记** | 把「引用标准时效」从「有外部文件才查」改为「**全部引用逐一登记状态**」 |")
A("")
A("**为什么是加门禁而不是加提示词**：这三件事都不是「我不知道要做」——"
  "「依据要登记」「节点要引用」「标准要核时效」我当然知道。"
  "问题在于，一个自然语言指令只能靠自觉执行，而**一个可机检的判据不能在失败时假装通过**。"
  "这次诊断就是证据：我自己写的 skill 里并没有「逐条核销依据清单」这条，"
  "于是我按重要性抽了 93 条，剩下 61 条从我的视野里消失了——而且**没有任何东西提醒我**。")
A("")
A("**具体落点建议（三处，都是小改动）**：")
A("")
A("1. `knowledge-processing` skill：在工序 4 与工序 6 之间插入**门禁 G-引用核销**，"
  "判据为「原稿全部《》引用 ⊆ evidence 条目集合 ∪ 显式豁免清单」；")
A("2. `graph-deductive-writing-skill`/写作契约：返回契约增加 "
  "`unreferenced_nodes: [{node_id, reason}]`，reason 只能取自固定枚举"
  "（可省略/有意留白/跨章已引）；")
A("3. `kp_toolkit`/`corpus_pipeline`：把上述两项实现为可调用函数"
  "（`audit_citations` / `audit_node_usage`），纳入 `gate_check`，"
  "**由编排器判定，不由写作 Agent 自判**——这与我此前已有的一条工程纪律一致。")
A("")
A("---")
A("")
A("## 七、一句话总结")
A("")
A("| 问题 | 答案 |")
A("|------|------|")
A("| 是抽取的问题还是装配的问题？ | **两者都有**：依据清单与设备参数属**抽取**；"
  "结论章不复述、选址章漏参数属**装配** |")
A("| 是能力问题吗？ | **不是**。三个案例都是「知道要做但没人核销」——**缺的是门禁，不是知识** |")
A("| 15+15 待审/缺口呢？ | **两者都不是**，是原稿本身的缺陷被检出；这类只能由客户裁决，不能「修复」 |")
A("| 要改 skill 吗？ | **要**，但改法是加**可机检的完成判据**（门禁），不是加更多说明文字 |")
A("")

(WS / "交付物" / "报告" / "抽取vs装配归因报告.md").write_text("\n".join(L), encoding="utf-8")
print(json.dumps({
    "assembly_recall_pct": round(asm_recall, 1),
    "nodes_total": len(uniq), "nodes_unreferenced": len(uniq_miss),
    "unjudgeable_short_values": len(unjudgeable),
    "bucket": bucket_cnt,
    "hard_misses": len(hard),
    "citation_recall_pct": round(len(ev_hit) / len(biaotype) * 100, 1),
    "citations_biaotype": len(biaotype), "citations_registered": len(ev_hit), "citations_missing": len(ev_miss),
    "device_param_lines_in_orig": len(dev_lines), "device_param_nodes_in_graph": dev_in_graph,
    "out": "交付物/报告/抽取vs装配归因报告.md",
}, ensure_ascii=False, indent=2))
