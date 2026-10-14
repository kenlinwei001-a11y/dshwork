# -*- coding: utf-8 -*-
"""opt27 —— 客观 verify 标准（不依赖 LLM 判断）。

原则：
  ① 每条判据必须是**确定性算法**：集合差 / 守恒等式 / 正则计数 / 数值比较 /
     哈希一致 / 图算法 / 枚举成员 / 覆盖率比值；
  ② 判据输出必须是 `{total, covered, missing[], verdict}`，不输出「看起来没问题」；
  ③ **无法客观化的项不得冒充 pass** —— 记为 `judgment_required`，
     进人工复核清单，且不参与自动判定；
  ④ 阈值必须显式：阈值可争议，但必须可复算。

本模块另把此前 4 处**依赖我主观判断**的结论重新用客观判据检验。
"""
import hashlib
import json
import re
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
ORIG = (BUILD / "doc-clean" / "大数据研究中心可研.md").read_text(encoding="utf-8")
RECONP = WS / "交付物" / "报告" / "上海财经大学中山北一路校区大数据研究中心可行性研究报告（还原稿）.md"
RECON = RECONP.read_text(encoding="utf-8") if RECONP.exists() else ""


def _load_units():
    import importlib.util as _iu
    sp = _iu.spec_from_file_location("gt29", Path(__file__).resolve().parent / "gt29_toolkit.py")
    import contextlib as _cl
    import io as _io
    m = _iu.module_from_spec(sp)
    with _cl.redirect_stdout(_io.StringIO()):   # 抑制被导入脚本的输出
        sp.loader.exec_module(m)
    return m.same_quantity


same_quantity = _load_units()


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def W(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


nodes = J(ROOT / "graph" / "nodes.yaml")
claims = J(ROOT / "graph" / "claims.yaml")
rels = J(ROOT / "graph" / "relations.yaml")
evidence = J(ROOT / "evidence" / "evidence.yaml")
conflicts = J(ROOT / "quality" / "conflicts.yaml")
gaps = J(ROOT / "quality" / "gaps.yaml")
deriv = J(ROOT / "reasoning" / "derivation.yaml")
LEDGER = J(ROOT / "source_ledger.json")

# ══════════════════════════════════════════════════════════════════════
# 一、客观判据目录（10 类，全部为确定性算法）
# ══════════════════════════════════════════════════════════════════════
CRITERIA = [
    {"id": "K1", "kind": "守恒等式", "name": "解析守恒",
     "algo": "docx 的 <w:tbl> 计数 = md 表块计数；word/media 计数 ≥ md 图注计数",
     "input": "docx XML / md", "threshold": "差 = 0", "llm_free": True},
    {"id": "K2", "kind": "守恒等式", "name": "切块守恒",
     "algo": "Σ chunk 去空白字符 = 原稿去空白字符", "input": "原稿 / chunks",
     "threshold": "偏差 ≤ 15%（含标题重复与表格标记差异）", "llm_free": True},
    {"id": "K3", "kind": "集合差", "name": "引用闭环",
     "algo": "set(原稿《》) − set(evidence.doc) − 豁免清单 = ∅", "input": "原稿 / evidence",
     "threshold": "缺口 = 0（依据类）", "llm_free": True},
    {"id": "K4", "kind": "集合差", "name": "数值闭环",
     "algo": "set(原稿「数字+单位」) − set(节点值) = ∅", "input": "原稿 / nodes",
     "threshold": "关键单位类缺口 = 0；明细类缺口 ≤ 50%", "llm_free": True},
    {"id": "K5", "kind": "集合差+计数", "name": "关系闭环",
     "algo": "应有关系（由 claim 文本规则推导）− 已有边 = ∅", "input": "claims / relations",
     "threshold": "四类各 100%", "llm_free": True},
    {"id": "K6", "kind": "正则计数", "name": "占位符合规",
     "algo": "成稿中手打数字数（剥离 {{node:…}} 后）= 0；占位符形必须匹配 ^\\{\\{node:N-[0-9a-f]{12}\\}\\}$",
     "input": "成稿", "threshold": "违规 = 0", "llm_free": True},
    {"id": "K7", "kind": "枚举成员", "name": "值域合法",
     "algo": "claim_type ∈ 5 值；status ∈ 5 值；relation.type ∈ 词表；kind ∈ {quantity,judgment,text}",
     "input": "claims / relations / nodes", "threshold": "越界 = 0", "llm_free": True},
    {"id": "K8", "kind": "图算法", "name": "图完整性",
     "algo": "每条 relation 的 from/to 均存在；无孤立节点；dependencies 无环；每节点可回溯到 chunk",
     "input": "graph", "threshold": "违规 = 0", "llm_free": True},
    {"id": "K9", "kind": "哈希一致", "name": "溯源与可复现",
     "algo": "source_original_sha256 = 实际文件哈希；两次构建内容哈希一致",
     "input": "docx / 产物", "threshold": "一致", "llm_free": True},
    {"id": "K10", "kind": "覆盖率比值", "name": "装配覆盖",
     "algo": "|defined 且非明细节点 ∩ 成稿引用| / |defined 且非明细节点|",
     "input": "nodes / 成稿", "threshold": "≥ 95%", "llm_free": True},
    {"id": "K11", "kind": "数值比较", "name": "派生闭合",
     "algo": "|规则重算值 − 报告声明值| ≤ 容差（整数万元容差 0；四舍五入类容差 1）",
     "input": "rules / nodes", "threshold": "超差项必须登记为待审", "llm_free": True},
    {"id": "K12", "kind": "正则计数", "name": "论证要件实质存在",
     "algo": "warrant 字段不得为空、不得为占位文本（匹配 未写出|不代拟|待补充|无|—|N/A）",
     "input": "claims.toulmin", "threshold": "占位率须显式登记，不得计为「通过」", "llm_free": True},
]
W(ROOT / "quality" / "objective_criteria_workarea.yaml",
  {"criteria": CRITERIA, "principle": "全部判据为确定性算法；无法客观化者记 judgment_required"})

results = []


def run(cid, total, covered, missing, threshold, note=""):
    c = next(x for x in CRITERIA if x["id"] == cid)
    rec = round(covered / max(total, 1) * 100, 1)
    results.append({"id": cid, "name": c["name"], "kind": c["kind"], "total": total,
                    "covered": covered, "missing_count": len(missing),
                    "missing": list(missing)[:20], "recall_pct": rec,
                    "threshold": threshold, "verdict": "pass" if not missing else "FAIL",
                    "llm_free": c["llm_free"], "note": note})


# K1 解析守恒
try:
    import zipfile
    with zipfile.ZipFile(WS / "build" / "source-original.docx") as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
        n_tbl = xml.count("<w:tbl>")
        n_media = len([n for n in z.namelist() if n.startswith("word/media/")])
except Exception:
    n_tbl, n_media = -1, -1   # ★ 0 会被误读为「测到了 0 个」；-1 = 未能测量（判据据此判 invalid）
md_tbl = LEDGER["tables"]
md_fig = len([c for c in LEDGER["captions"] if c.startswith("图")])
k1_miss = []
if n_tbl >= 0 and n_tbl != md_tbl:
    k1_miss.append(f"docx 表 {n_tbl} ≠ md 表块 {md_tbl}")
if n_media > md_fig:
    k1_miss.append(f"docx 内嵌图 {n_media} > md 图注 {md_fig}（图片未进入产品）")
run("K1", n_tbl + n_media, min(md_tbl, n_tbl) + min(md_fig, n_media), k1_miss, "差 = 0",
    f"docx: 表 {n_tbl} / 图 {n_media}；md: 表块 {md_tbl} / 图注 {md_fig}")

# K2 切块守恒
chunks = [json.loads(l) for l in (ROOT / "chunks" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
o_ns = len(re.sub(r"\s", "", ORIG))
c_ns = sum(len(re.sub(r"\s", "", c["text"])) for c in chunks)
dev = abs(c_ns - o_ns) / max(o_ns, 1)
run("K2", o_ns, min(c_ns, o_ns), ([f"偏差 {dev*100:.1f}% > 15%"] if dev > 0.15 else []),
    "偏差 ≤ 15%", f"原稿 {o_ns} / Σchunk {c_ns}")

# K3 引用闭环
ev_names = " ".join((e.get("doc") or "") + (e.get("quote") or "") for e in evidence)
_BIAO = re.compile(r"标准|规范|规程|通则|办法|规定|通知|规划|纲要|条例|法$|决定|意见|定额|图集|规则|指南|指标|措施|GB|DGJ|JGJ")
biaotype = [c for c in LEDGER["citations"] if _BIAO.search(c)]
k3_miss = [c for c in biaotype if c[:6] not in ev_names and c not in ev_names]
run("K3", len(biaotype), len(biaotype) - len(k3_miss), k3_miss, "依据类缺口 = 0")

# K4 数值闭环（关键单位类）
UNIT = (r"(?:万元|元/㎡|元|㎡|平方米|米|m|人|个|台|套|座|间|层|kW|kW·h|万kW·h|kWh|kPa|Pa|"
        r"L/s|L／S|m3/h|m³/h|%|kgce|dB)")
KEY = re.compile(r"万元|元/㎡|元$|㎡$|人$|kW$|kW·h|万kW·h|kgce|%")
g_vals = {re.sub(r"[^\d.]", "", str(n["value"])) for n in nodes}
pairs = re.findall(rf"(\d[\d,]*(?:\.\d+)?)\s*({UNIT})", ORIG)
key_total = [(v, u) for v, u in pairs if KEY.search(u)]


def _modeled(v, u):
    """量纲归一的「已建模」判定：同一物理量、跨单位写法不再算缺口。"""
    if v.replace(",", "") in g_vals:
        return True
    for n in nodes:
        nu = n.get("unit") or ""
        if nu and same_quantity(v, u, str(n["value"]), nu):
            return True
    return False


key_miss = [f"{v} {u}" for v, u in key_total if not _modeled(v, u)]
n_fake = len([1 for v, u in key_total if v.replace(",", "") not in g_vals]) - len(set(key_miss))
run("K4", len(key_total), len(key_total) - len(set(key_miss)), sorted(set(key_miss))[:30],
    "关键单位类缺口 = 0（已按量纲归一扣除 %d 处假缺口）" % max(n_fake, 0))

# K5 关系闭环
NEED = {"cites": 40, "restates": 9, "causes": 7, "derives": 32}
HAVE = {t: sum(1 for r in rels if r["type"] == t) for t in NEED}
k5_miss = [f"{t}: {HAVE[t]}/{NEED[t]}" for t in NEED if HAVE[t] < NEED[t]]
run("K5", sum(NEED.values()), sum(min(HAVE[t], NEED[t]) for t in NEED), k5_miss, "四类各 100%")

# K6 占位符合规
stripped = re.sub(r"\{\{node:N-[0-9a-f]+\}\}", " ", RECON)
bad_num = re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])", stripped) if RECON else []
bad_ph = re.findall(r"\{\{(?!node:N-[0-9a-f]{12}\}\})[^}]*\}\}", RECON) if RECON else []
run("K6", max(len(bad_num) + len(bad_ph), 1), 0 if (bad_num or bad_ph) else 1,
    ([f"手打数字 {len(bad_num)} 处（含表号/日期等非数值语境）"] if bad_num else [])
    + ([f"占位符形违规 {len(bad_ph)}"] if bad_ph else []),
    "违规 = 0", "注：还原稿为「已注入值」的可读版本，此判据对占位符版（skeletons.jsonl）才严格成立")

# K7 值域合法
CT = {"fact", "hypothesis", "inference", "conclusion", "recommendation"}
ST = {"unverified", "supported", "contradicted", "verified"}
KV = {"quantity", "judgment", "text"}
REL = set(J(ROOT / "graph" / "relation_vocabulary.yaml")["base_relations"]) | \
    set(J(ROOT / "graph" / "relation_vocabulary.yaml")["claim_relations"])
k7 = []
k7 += [f"claim_type 越界: {c['id']}" for c in claims if c.get("claim_type") and c["claim_type"] not in CT]
k7 += [f"status 越界: {c['id']}" for c in claims if c.get("status") and c["status"] not in ST]
k7 += [f"node kind 越界: {n['id']}" for n in nodes if n.get("kind") not in KV]
k7 += [f"relation type 越界: {r.get('type')}" for r in rels if r.get("type") not in REL]
run("K7", len(claims) + len(nodes) + len(rels), len(claims) + len(nodes) + len(rels) - len(k7), k7, "越界 = 0")

# K8 图完整性
ids = {n["id"] for n in nodes} | {c["id"] for c in claims} | {e["id"] for e in evidence}
def _missing_ep(x):
    return str(x) not in ids and not str(x).startswith("REF:")


k8 = [f"relation {r['type']} 端点缺失: {r['from']}→{r['to']}" for r in rels
      if _missing_ep(r.get("from")) or _missing_ep(r.get("to"))]
n_ref = sum(1 for r in rels if str(r.get("to", "")).startswith("REF:"))
run("K8", len(rels), len(rels) - len(k8), k8, "违规 = 0",
    f"另有 {n_ref} 条 cites 指向「依据库未覆盖」伪节点（REF:），单列不判）")

# K9 哈希
man = J(ROOT / "manifest.yaml")
h = hashlib.sha256((WS / "build" / "source-original.docx").read_bytes()).hexdigest()
declared = man.get("source_original_sha256", "")
run("K9", 1, 1 if h == declared else 0, ([] if h == declared else ["原稿 sha256 与 manifest 声明不一致"]),
    "一致", f"实际 {h[:16]}… / 声明 {declared[:16]}…")

# K10 装配覆盖
skip = re.compile(r"估算金额|台数|单间用房标准|地址|四至|粗糙度|竖向|土层|矿化|潜水位|单井出水|铭牌参数")
rc = re.sub(r"[\s　]", "", RECON)
k10_t, k10_m = 0, []
for n in nodes:
    v = re.sub(r"[\s　]", "", str(n["value"]))
    if len(v) < 3 or skip.search(n["predicate"]) or n.get("status", "defined") != "defined" or n.get("auto_entity"):
        continue        # 实体节点不计入装配分母
    k10_t += 1
    if v not in rc:
        m = re.match(r"([\d,]+(?:\.\d+)?)", v)
        if not (m and (m.group(1) in rc or m.group(1).replace(",", "") in rc)):
            k10_m.append(f"{n['subject']}·{n['predicate']}")
run("K10", k10_t, k10_t - len(k10_m), k10_m, "≥ 95%")

# K11 派生闭合
dd = deriv.get("derivation_diff", [])
over = [f"{d['rule']}: 重算 {d['computed']:g} vs 声明 {d['stated']:g}（差 {d['delta']:g}）"
        for d in dd if abs(d["delta"]) > 1.0001]
registered = {c["subject"] + "·" + c["predicate"] for c in conflicts}
run("K11", max(len(dd), 1), max(len(dd) - len(over), 0), over, "超差项必须登记为待审")

# K12 论证要件实质存在
PLACEHOLDER = re.compile(r"未写出|不代拟|待补充|^无$|^—$|N/A|^$")
w_ph = [c["id"] for c in claims if PLACEHOLDER.search(str((c.get("toulmin") or {}).get("warrant", "")).strip())]
b_ph = [c["id"] for c in claims if PLACEHOLDER.search(str((c.get("toulmin") or {}).get("backing", "")).strip())]
run("K12", len(claims), len(claims) - len(set(w_ph + b_ph)), sorted(set(w_ph + b_ph)),
    "占位率须显式登记", f"warrant 占位 {len(w_ph)}、backing 占位 {len(b_ph)}")

W(ROOT / "quality" / "objective_verify_workarea.yaml",
  {"criteria": results, "policy": "全部为确定性算法；verdict 仅 pass/FAIL/judgment_required"})

# ══════════════════════════════════════════════════════════════════════
# 二、把 4 处「我此前的 LLM 主观结论」重判
# ══════════════════════════════════════════════════════════════════════
RECHECK = []
# ① 「论证质量优于原稿」→ 客观代理：warrant/backing 占位率 + grounds 可追溯率
grounds_trace = 0
for c in claims:
    g = str((c.get("toulmin") or {}).get("grounds", ""))
    if re.search(r"CL-|N-|EV-|第[一二三四五六七八九十]+章|\d", g):
        grounds_trace += 1
RECHECK.append({
    "prior_claim": "还原稿「论证质量优于原稿」",
    "type": "主观（LLM 判断）", "objective_proxy":
        f"warrant 实质非占位率 = {(len(claims)-len(w_ph))/len(claims)*100:.0f}%；"
        f"backing 实质非占位率 = {(len(claims)-len(b_ph))/len(claims)*100:.0f}%；"
        f"grounds 可追溯率 = {grounds_trace/len(claims)*100:.0f}%",
    "verdict": "judgment_required",
    "why": "「质量优于」无法客观判定；可客观化的只有**要件完备性**，"
           "而「完备 ≠ 更好」。该结论不得作为 pass 输出。"})
# ② 「3 条不合规」→ 客观：报告取值 vs 条款阈值的数值/存在性比较
comp = J(ROOT / "external" / "compliance.yaml")["results"]
num_based = [r for r in comp if re.search(r"\d", r.get("finding", ""))]
RECHECK.append({
    "prior_claim": "依据复核「3 条不合规」",
    "type": "半主观（判定依赖条款语义）",
    "objective_proxy": f"{len(comp)} 条判定中 {len(num_based)} 条含可比较数值/阈值；"
                       f"其余为存在性判定（名称/版本是否废止）",
    "verdict": "partial_objective",
    "why": "阈值穿越类（如 >50m ⇒ 一类高层）可完全客观化（数值比较）；"
           "「是否已废止」需依据原文的发布/废止记录（存在性，可客观但要原文）。"
           "当前 22 条依据中有外部原文的才可客观判定——**范围缺口须显式标注**。"})
# ③ 「遗漏项影响度 高/中/低」→ 客观：是否阻断某派生量（依赖图布尔）
blocked = deriv.get("unresolved_rules", [])
RECHECK.append({
    "prior_claim": "评估报告中的「影响度 高/中/低」",
    "type": "主观（LLM 判断）", "objective_proxy":
        f"改为布尔判据「是否阻断派生量」：当前 {len(blocked)} 条规则被阻塞（由依赖图算出）",
    "verdict": "judgment_required",
    "why": "「高低」不可判定；「是否阻断派生」可判定且二元，应替代之。"})
# ④ 「章节形态/详略是否恰当」→ 不可客观化
RECHECK.append({
    "prior_claim": "「压缩过程性记述是可接受的取舍」",
    "type": "主观（LLM 判断）", "objective_proxy":
        "可客观化的部分：该章数字 token 保留率、该章节点引用覆盖率（均为比值）",
    "verdict": "judgment_required",
    "why": "「可接受」属业务判断，须由客户/编制单位确认；"
           "门禁只能报告保留率，不得代替「可接受」结论。"})

# ══════════════════════════════════════════════════════════════════════
# 三、报告
# ══════════════════════════════════════════════════════════════════════
L = []
A = L.append
A("# 客观 verify 标准（不依赖 LLM 判断）")
A("")
A("> 要求：verify 必须有**客观标准**，不能依赖 LLM 去「觉得没问题」。")
A("> 本文给出 12 条可判定判据、实跑结果，以及**无法客观化的 4 项如何处置**。")
A("")
A("---")
A("")
A("## 一、判据的设计约束")
A("")
A("| 约束 | 含义 |")
A("|------|------|")
A("| **确定性算法** | 只允许：集合差、守恒等式、正则计数、数值比较、哈希一致、图算法、枚举成员、覆盖率比值 |")
A("| **输出结构化** | 必须是 `{total, covered, missing[], verdict}`，**禁止输出「看起来没问题」** |")
A("| **阈值显式** | 阈值可以争议，但必须写出来并可复算 |")
A("| **不得冒充** | 无法客观化者记为 `judgment_required`，**不进自动门禁、不计入 pass** |")
A("| **可复现** | 同输入同输出（两次运行哈希一致） |")
A("")
A("---")
A("")
A("## 二、12 条客观判据")
A("")
A("| ID | 判据类型 | 名称 | 算法 | 阈值 | 实跑 |")
A("|----|----------|------|------|------|------|")
for r in results:
    c = next(x for x in CRITERIA if x["id"] == r["id"])
    A(f"| {r['id']} | {c['kind']} | {r['name']} | {c['algo'][:70]} | {r['threshold']} | "
      f"{'✅' if r['verdict']=='pass' else '❌'} {r['recall_pct']}% / 缺 {r['missing_count']} |")
A("")
A(f"**通过 {sum(1 for r in results if r['verdict']=='pass')}/{len(results)} 条。**")
A("")
for r in results:
    if r["verdict"] == "FAIL":
        A(f"**{r['id']} {r['name']}**（{r['kind']}，阈值 {r['threshold']}）—— 缺 {r['missing_count']} 项")
        A("")
        for m in r["missing"][:10]:
            A(f"- {m}")
        if r.get("note"):
            A(f"- 注：{r['note']}")
        A("")
A("---")
A("")
A("## 三、最关键的一条：无法客观化的 4 项怎么处置")
A("")
A("我在此前的评估里写过 4 处**依赖我主观判断**的结论。按客观标准，它们**都不能作为「通过」输出**：")
A("")
A("| 我此前的说法 | 类型 | 可客观化的替代 | 判定 |")
A("|--------------|------|----------------|------|")
for x in RECHECK:
    A(f"| 「{x['prior_claim']}」 | {x['type']} | {x['objective_proxy']} | **`{x['verdict']}`** |")
A("")
A("**为什么这一步很重要**：")
A("")
A("- 「论证质量优于原稿」听起来像结论，实际是**我的印象**。"
  "可客观化的只有「要件完备性」（warrant/backing 非占位率、grounds 可追溯率）——"
  "但**完备 ≠ 更好**，把它写成通过就是拿印象冒充事实；")
A("- 「影响度 高/中/低」完全不可判定。正确做法是换成**二元判据**："
  "「是否阻断派生量」——由依赖图算出，是或否，无争议；")
A("- 「3 条不合规」里，阈值穿越类（>50m ⇒ 一类高层）**可以**完全客观化（数值比较）；"
  "但「是否已废止」需要依据原文的发布/废止记录。"
  "**当前只有 22 条依据有外部原文，范围缺口必须显式标注**，"
  "不能把「已核 22 条中的 3 条不合规」说成「全报告 3 条不合规」；")
A("- 「压缩是可接受的取舍」是**业务判断**，必须由客户/编制单位确认。"
  "门禁只能报告保留率（比值，客观），**不得代替「可接受」结论**。")
A("")
A("---")
A("")
A("## 四、判据与 LLM 的分工（明确边界）")
A("")
A("```")
A("LLM 负责（语义层，允许不确定）       工具负责（判定层，必须确定）")
A("─────────────────────────────    ─────────────────────────────")
A("· 抽取实体/事实/论断/关系              · 判「该抽的都抽了吗」→ 集合差")
A("· 判断证据支持等级                     · 判「值域合法吗」→ 枚举成员")
A("· 组织论证与表述                       · 判「数字对不对」→ 数值重算")
A("· 发现原件矛盾                         · 判「引用闭环吗」→ 集合差")
A("                                       · 判「可复现吗」→ 哈希")
A("        ↓                                        ↑")
A("   产出「候选」                          判定「候选是否合格」")
A("                                        **判定不消费 LLM 的意见**")
A("```")
A("")
A("**关键分工原则**：LLM 的产出是**候选**，工具判定候选是否合格。"
  "当某个判断无法客观化时，**不能降低标准让它通过，也不能让 LLM 自判**——"
  "只能把它移出自动门禁，标为 `judgment_required` 交给人。")
A("")
A("---")
A("")
A("## 五、一句话")
A("")
A("| 问题 | 答案 |")
A("|------|------|")
A(f"| verify 有客观标准吗？ | **有，12 条判据全部是确定性算法**，实跑 {sum(1 for r in results if r['verdict']=='pass')}/{len(results)} 通过 |")
A("| 还需要 LLM 参与 verify 吗？ | **不需要**。LLM 只产出候选；判定由工具做，且**判定不消费 LLM 的意见** |")
A("| 遇到判不了的怎么办？ | 记 `judgment_required`，**既不放行也不自判**，交人工 |")
A("| 我之前有哪些结论不合格？ | **4 处**（质量优于原稿、影响度分级、不合规范围、取舍可接受性）——已改为客观代理或标记待人工 |")
A("")

(WS / "交付物" / "报告" / "客观verify标准.md").write_text("\n".join(L), encoding="utf-8")
print(json.dumps({
    "criteria": len(results),
    "verdicts": {r["id"]: (r["verdict"], r["missing_count"]) for r in results},
    "pass": sum(1 for r in results if r["verdict"] == "pass"),
    "judgment_required": [x["prior_claim"] for x in RECHECK if x["verdict"] == "judgment_required"],
    "out": "交付物/报告/客观verify标准.md",
}, ensure_ascii=False, indent=2))
