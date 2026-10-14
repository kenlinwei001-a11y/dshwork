# -*- coding: utf-8 -*-
"""闭环校验（closure verification）——verify 机制的修正实现。

旧机制的结构缺陷：
    validate_extraction 迭代 ext.get("facts", []) —— 只遍历**产物**。
    对产物的遍历，无论多严格，都不可能发现「产物里没有、但源里有」的东西。
    这是逻辑上的不可能，不是严谨度不够。

修正思路：先让**源可枚举**（source ledger，用与抽取无关的方法生成），
然后把 verify 变成**两个集合的差**：
    missing = ledger(源) − extracted(产物) − exempt(显式豁免)
差集非空即不通过。

另加探针自证：每个探针必须在源中命中一个**已知存在的正样本**，
否则该探针无效、不得输出结论（本次诊断我曾三次误判，全因探针未标定）。
"""
import json
import re
from pathlib import Path

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
DOCX = WS / "build" / "source-original.docx"
ENTERPRISE = None

ORIG = (BUILD / "doc-clean" / "大数据研究中心可研.md").read_text(encoding="utf-8")
RECON = (WS / "交付物" / "报告" / "上海财经大学中山北一路校区大数据研究中心可行性研究报告（还原稿）.md").read_text(encoding="utf-8")


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


nodes = J(ROOT / "graph" / "nodes.yaml")
outline = J(ROOT / "outline.yaml")
evidence = [e for e in J(ROOT / "evidence" / "evidence.yaml") if str(e.get("id", "")).startswith("EV-")]

# ══════════════════════════════════════════════════════════════════════
# 第一步：源侧索引（source ledger）—— 用与 LLM 抽取无关的方法生成
# ══════════════════════════════════════════════════════════════════════
LEDGER = {}

# L1 引用：正则扫原稿全部《》
LEDGER["citations"] = sorted(set(re.findall(r"《([^》]{2,80})》", ORIG)))
LEDGER["citations_raw_count"] = len(re.findall(r"《[^》]{2,80}》", ORIG))

# L2 表格：原稿的 ```table 块（由 docx 的 w:tbl 决定，与我的表抽取无关）
LEDGER["tables"] = len(re.findall(r"```table", ORIG))

# L3 带单位数值（关键取值）：正则
UNIT = r"(?:万元|元/㎡|元|㎡|平方米|米|m|人|个|台|套|座|间|层|kW|kW·h|万kW·h|kWh|kPa|Pa|L/s|L／S|m3/h|m³/h|%|kgce|dB)"
LEDGER["valued_numbers"] = sorted(set(re.findall(rf"(\d[\d,]*(?:\.\d+)?)\s*{UNIT}", ORIG)))

# L4 标题：正则（层级与文本）
LEDGER["headings"] = [m.group(2).strip() for m in
                      (re.match(r"^(#{1,6})\s+(.+?)\s*$", l) for l in ORIG.split("\n")) if m]

# L5 设备铭牌参数：正则
DEV = re.compile(r"\bQ\s*=|\bH\s*=|风量|全压|静压|IPLV|单台泵流量|有效容积V=|功率[：:]")
LEDGER["device_params"] = len([l for l in ORIG.split("\n") if DEV.search(l)])

# L6 图表题注：正则
LEDGER["captions"] = sorted(set(re.findall(r"(表\s?\d+-\d+|图\s?\d+-\d+)", ORIG)))

# L7 图片：docx 内嵌图（独立于文本）
try:
    import zipfile
    with zipfile.ZipFile(DOCX) as z:
        LEDGER["images_in_docx"] = len([n for n in z.namelist() if n.startswith("word/media/")])
except Exception as e:
    LEDGER["images_in_docx"] = f"不可读: {e}"

# ══════════════════════════════════════════════════════════════════════
# 第二步：探针自证（probe calibration）—— 每个探针必须有正样本
# ══════════════════════════════════════════════════════════════════════
PROBES = [
    ("citations", r"《([^》]{2,80})》", ["普通高等学校建筑规划面积指标", "建筑设计防火规范"]),
    ("headings", r"^(#{1,6})\s+(.+?)\s*$", ["总论", "投资估算及资金筹措"]),
    ("valued_numbers", rf"(\d[\d,]*(?:\.\d+)?)\s*{UNIT}", ["18319", "13032"]),
    ("device_params", r"\bQ\s*=|\bH\s*=|风量|全压|静压", ["风量"]),
    ("captions", r"(表\s?\d+-\d+|图\s?\d+-\d+)", ["表1-2", "表5-5"]),
]
calib = []
for name, pat, anchors in PROBES:
    found = re.findall(pat, ORIG, re.M) if name != "citations" else re.findall(pat, ORIG)
    flat = " ".join(str(x) for x in (found if isinstance(found, list) else [found]))
    ok = all(a in flat for a in anchors)
    calib.append({"probe": name, "pattern": pat[:44], "anchors": anchors, "valid": ok,
                  "hits": len(found)})
INVALID = [c for c in calib if not c["valid"]]

# ══════════════════════════════════════════════════════════════════════
# 第三步：闭环校验 —— 集合差
# ══════════════════════════════════════════════════════════════════════
def witness(name, extra=None):
    return {"probe": name, "calibrated": name not in {c["probe"] for c in INVALID},
            "extra": extra or {}}


CLOSURES = []

# C1 依据闭环：原稿引用 ⊆ 证据条目 ∪ 豁免
ev_names = " ".join((e.get("doc") or "") + (e.get("quote") or "") for e in evidence)
_BIAO = re.compile(r"标准|规范|规程|通则|办法|规定|通知|规划|纲要|条例|法$|决定|意见|定额|图集|规则|指南|指标|措施|GB|DGJ|JGJ|方案")
_EXEMPT_CIT = re.compile(r"Journal|Annals|学报|杂志|Econometrica|JASA|统计|挖掘|测度|动力学|"
                         r"预制|桁架|叠合板|楼梯|阳台板|连接节点|灌浆料|合同$|教材|课程")
c_cov, c_miss, c_exempt = [], [], []
for c in LEDGER["citations"]:
    if c[:6] in ev_names or c in ev_names:
        c_cov.append(c)
    elif _EXEMPT_CIT.search(c):
        c_exempt.append(c)
    elif _BIAO.search(c):
        c_miss.append(c)
    else:
        c_exempt.append(c)
CLOSURES.append({"id": "C1", "name": "依据闭环（原稿引用 → 证据条目）", "probe": "citations",
                 "total": len(LEDGER["citations"]), "covered": len(c_cov),
                 "exempt": len(c_exempt), "missing": c_miss,
                 "recall_pct": round(len(c_cov) / max(len(c_cov) + len(c_miss), 1) * 100, 1)})

# C2 表格闭环：原稿表数 → 成稿表数
r_tables = len(re.findall(r"^\|.*\|$", RECON, re.M))
CLOSURES.append({"id": "C2", "name": "表格闭环（原稿表 → 成稿表）", "probe": "tables",
                 "total": LEDGER["tables"], "covered": None, "exempt": None,
                 "missing": [], "note": f"原稿 ```table 块 {LEDGER['tables']} 个；成稿表格行由 (cap,col) 计数口径不同，"
                                        f"按「表题闭环」另行判定（见 C6）"})

# C3 关键取值闭环：原稿带单位数值 ⊆ 图谱节点值 ∪ 豁免
g_vals = {re.sub(r"[^\d.]", "", str(n["value"])) for n in nodes}
v_cov, v_miss = [], []
for v in LEDGER["valued_numbers"]:
    key = v.replace(",", "")
    if key in g_vals or any(key == x for x in g_vals):
        v_cov.append(v)
    else:
        v_miss.append(v)
CLOSURES.append({"id": "C3", "name": "关键取值闭环（原稿带单位数值 → 图谱）", "probe": "valued_numbers",
                 "total": len(LEDGER["valued_numbers"]), "covered": len(v_cov),
                 "exempt": 0, "missing": v_miss,
                 "recall_pct": round(len(v_cov) / max(len(LEDGER["valued_numbers"]), 1) * 100, 1)})

# C4 章节闭环：原稿标题 ⊆ outline
o_titles = {re.sub(r"[\s　]", "", x["title"]) for x in outline["sections"]}
h_cov, h_miss = [], []
for h in LEDGER["headings"]:
    k = re.sub(r"[\s　]", "", h)
    if k in o_titles:
        h_cov.append(h)
    else:
        h_miss.append(h)
CLOSURES.append({"id": "C4", "name": "章节闭环（原稿标题 → outline）", "probe": "headings",
                 "total": len(LEDGER["headings"]), "covered": len(h_cov), "exempt": 0,
                 "missing": h_miss[:40], "missing_count": len(h_miss),
                 "recall_pct": round(len(h_cov) / max(len(LEDGER["headings"]), 1) * 100, 1)})

# C5 设备参数闭环：原稿设备参数语句 → 设备节点
dev_nodes = [n for n in nodes if DEV.search(n["subject"] + n["predicate"] + str(n["value"]))]
CLOSURES.append({"id": "C5", "name": "设备参数闭环（原稿设备参数 → 设备节点）", "probe": "device_params",
                 "total": LEDGER["device_params"], "covered": len(dev_nodes), "exempt": 0,
                 "missing": [f"未抽设备参数语句 {LEDGER['device_params'] - len(dev_nodes)} 条（明细表未重建）"],
                 "recall_pct": round(len(dev_nodes) / max(LEDGER["device_params"], 1) * 100, 1)})

# C6 表题闭环：原稿表/图题注 → 成稿
cap_miss = [c for c in LEDGER["captions"] if re.sub(r"\s", "", c) not in re.sub(r"\s", "", RECON)]
CLOSURES.append({"id": "C6", "name": "表题闭环（原稿表/图题注 → 成稿）", "probe": "captions",
                 "total": len(LEDGER["captions"]), "covered": len(LEDGER["captions"]) - len(cap_miss),
                 "exempt": 0, "missing": cap_miss, "missing_count": len(cap_miss),
                 "recall_pct": round((len(LEDGER["captions"]) - len(cap_miss)) / max(len(LEDGER["captions"]), 1) * 100, 1)})

# C7 装配闭环：图谱节点（defined，非明细类） → 成稿引用
rc_all = re.sub(r"[\s　]", "", RECON)
SKIP = re.compile(r"估算金额|台数|单台制冷量|间数|单间用房标准|地址|四至|粗糙度|竖向|土层|矿化|潜水位|单井出水")
a_total, a_miss = 0, []
for n in nodes:
    v = re.sub(r"[\s　]", "", str(n["value"]))
    if len(v) < 3 or SKIP.search(n["predicate"]) or n["status"] != "defined":
        continue
    a_total += 1
    if v not in rc_all:
        mm = re.match(r"([\d,]+(?:\.\d+)?)", v)
        if not (mm and (mm.group(1) in rc_all or mm.group(1).replace(",", "") in rc_all)):
            a_miss.append(f"{n['subject']}·{n['predicate']} = {n['value']}")
CLOSURES.append({"id": "C7", "name": "装配闭环（图谱 defined 节点 → 成稿引用）", "probe": "—",
                 "total": a_total, "covered": a_total - len(a_miss), "exempt": 0, "missing": a_miss,
                 "missing_count": len(a_miss),
                 "recall_pct": round((a_total - len(a_miss)) / max(a_total, 1) * 100, 1)})

# ══════════════════════════════════════════════════════════════════════
# 第四步：判定与输出
# ══════════════════════════════════════════════════════════════════════
THRESH = {"C1": 95, "C3": 90, "C4": 98, "C5": 80, "C6": 60, "C7": 95}
verdicts = {}
for c in CLOSURES:
    if c["id"] in THRESH and c.get("recall_pct") is not None:
        verdicts[c["id"]] = "pass" if c["recall_pct"] >= THRESH[c["id"]] else "FAIL"
    else:
        verdicts[c["id"]] = "n/a"

L = []
A = L.append
A("# verify 机制修正方案（闭环校验）")
A("")
A("> 结论先说：**是机制的问题，而且是结构性缺陷**——不是「校验不够严格」，"
  "而是**校验的数学对象选错了**。")
A("")
A("---")
A("")
A("## 一、旧机制的结构缺陷（为什么它必然查不出遗漏）")
A("")
A("现有校验函数 `validate_extraction(ext)` 的实现是：")
A("")
A("```python")
A("for f in ext.get(\"facts\", []):        # 遍历【产物】")
A("    if not f.get(\"subject\") or not f.get(\"value\"):")
A("        errors.append(...)")
A("for cl in ext.get(\"claims\", []):       # 遍历【产物】")
A("for r in ext.get(\"relations\", []):     # 遍历【产物】")
A("```")
A("")
A("**三个循环，遍历的都是产物。** 这带来一个逻辑上的不可能：")
A("")
A("> 对产物集合 P 的任何遍历，都无法发现「不属于 P 但属于源 S」的元素。"
  "因为那个元素**不在被遍历的集合里**，循环根本不会碰到它。")
A("")
A("所以旧机制能保证的是「抽出来的东西**格式对、值合法**」，"
  "**永远不可能保证「该抽的都抽了」**——"
  "哪怕我把校验写到极致，54 条未登记的依据依旧会一条不漏地穿过去。")
A("")
A("| | 旧机制 | 结论 |")
A("|---|---|---|")
A("| 校验对象 | 产物内部（facts/claims/relations 的字段与枚举） | 自洽性 |")
A("| 能否发现遗漏 | **不能（逻辑上不可能）** | ❌ |")
A("| 对「漏抽」的表现 | 静默通过 | 最危险的一类失败 |")
A("")
A("---")
A("")
A("## 二、修正后的机制：闭环校验（closure verification）")
A("")
A("```")
A("旧：  P ──► 遍历 P ──► 自洽？           （产物内省，看不见 S−P）")
A("")
A("新：  S ──► 源侧索引 ledger（独立方法生成）")
A("      P ──► 产物集合")
A("      missing = S − P − 显式豁免        （集合差，漏了就非空）")
A("      missing ≠ ∅ ⇒ FAIL")
A("```")
A("")
A("**关键在第一步：把源变成可枚举的索引（ledger）。** 源不可枚举时，"
  "「漏了什么」这个问题无法被提出，更无法被回答。")
A("")
A("### 2.1 源侧索引（用与 LLM 无关的方法生成）")
A("")
A("| 索引 | 生成方法 | 条数 |")
A("|------|----------|------|")
A(f"| `citations` | 正则扫原稿 `《…》` | {len(LEDGER['citations'])} 个唯一（{LEDGER['citations_raw_count']} 处） |")
A(f"| `tables` | 数原稿 ```` ```table ```` 块（由 docx 的 w:tbl 决定） | {LEDGER['tables']} |")
A(f"| `valued_numbers` | 正则扫「数字＋单位」 | {len(LEDGER['valued_numbers'])} 个唯一 |")
A(f"| `headings` | 正则扫标题层级 | {len(LEDGER['headings'])} |")
A(f"| `device_params` | 正则扫 `Q=`/`H=`/风量/全压/静压/功率 | {LEDGER['device_params']} 条语句 |")
A(f"| `captions` | 正则扫 `表N-M`/`图N-M` | {len(LEDGER['captions'])} 个 |")
A(f"| `images_in_docx` | 读 docx 的 `word/media/` | {LEDGER['images_in_docx']} |")
A("")
A("**为什么必须是独立方法**：如果 ledger 也用「读一遍原稿、凭理解记下来」的方式生成，"
  "它会继承**同一双眼睛的同一盲区**，S−P 依旧为空。"
  "正则/XML 与 LLM 阅读是两条独立通道，差集才有意义。")
A("")
A("### 2.2 探针自证（本次最痛的教训）")
A("")
A("我这次诊断**三次误判**：把「功率因数」（节能章灯具要求）当成变压器匹配口径、"
  "把「需要系数」（节能章表7-2 列标题）当成负荷估算口径、"
  "以及正则 `^## 6.5 强电设计` 没匹配到（原稿正文标题不带编号）导致探针区间为空。")
A("")
A("**根因：探针没有正样本标定。** 一个探针分不清「源里没有」和「我的正则写错了」，"
  "却会输出「源里没有」——这是把探针故障伪装成事实结论。")
A("")
A("修正：每个探针必须先在源中命中**一个已知存在的正样本**，命中失败则探针作废、不得出结论。")
A("")
A("| 探针 | 正样本（必须命中） | 结果 |")
A("|------|--------------------|------|")
for c in calib:
    A(f"| `{c['probe']}` | {'、'.join(c['anchors'])} | {'✅ 有效' if c['valid'] else '❌ **作废**'}（命中 {c['hits']} 处） |")
A("")
A(f"**本次探针标定结果：{len(calib) - len(INVALID)}/{len(calib)} 有效**"
  + (f"，作废 {len(INVALID)} 个" if INVALID else "，全部有效") + "。")
A("")
A("---")
A("")
A("## 三、七道闭环的实跑结果")
A("")
A("| 闭环 | 源（ledger） | 产物（covered） | 豁免 | **缺口** | 召回率 | 阈值 | 判定 |")
A("|------|--------------|-----------------|------|----------|--------|------|------|")
for c in CLOSURES:
    r = f"{c['recall_pct']}%" if c.get("recall_pct") is not None else "—"
    m = c.get("missing_count", len(c["missing"]))
    A(f"| **{c['id']}** {c['name']} | {c['total']} | {c['covered'] if c['covered'] is not None else '—'} | "
      f"{c['exempt'] if c['exempt'] is not None else '—'} | **{m}** | {r} | "
      f"{THRESH.get(c['id'], '—')} | {'✅ pass' if verdicts[c['id']] == 'pass' else ('❌ **FAIL**' if verdicts[c['id']] == 'FAIL' else '—')} |")
A("")
A("**缺口明细（机器可读的待核销清单）：**")
A("")
for c in CLOSURES:
    if c.get("missing"):
        A(f"**{c['id']} {c['name']}** —— {c.get('missing_count', len(c['missing']))} 项")
        A("")
        for m in c["missing"][:12]:
            A(f"- {m}")
        if c.get("missing_count", len(c["missing"])) > 12:
            A(f"- …另有 {c.get('missing_count', len(c['missing'])) - 12} 项")
        A("")
A("---")
A("")
A("## 四、修正前后的行为差异（用本次的真实数据）")
A("")
A("| 事项 | 旧机制 | 新机制 |")
A("|------|--------|--------|")
A(f"| 54 条依据未登记 | 静默通过（校验只遍历抽到的 67 条） | **C1 FAIL**，输出 54 条清单 |")
A(f"| 29 条设备参数未抽 | 静默通过 | **C5 FAIL**，输出缺抽条数 |")
A(f"| 原稿 31 张表 / 30 个题注 | 静默通过 | **C6 判定**，输出未重出表题 |")
A(f"| 3 个节点未引用（双证硕士 5631 等） | 静默通过 | **C7 FAIL**，逐节点点名 |")
A(f"| 原稿 {LEDGER['images_in_docx']} 张内嵌图 | 静默通过 | **C8** 图片闭环（本轮先只登记数） |")
A(f"| 探针自身故障 | 伪装成事实结论（我误判 3 次） | **探针标定**，未过标定即作废 |")
A("")
A("---")
A("")
A("## 五、落到哪里（三处小改动）")
A("")
A("| 改动 | 位置 | 形式 |")
A("|------|------|------|")
A("| 建 `source_ledger.json` | `corpus_pipeline` 新工序（解析后、抽取前） | 确定性函数 `build_source_ledger(docx/md)` |")
A("| 七道闭环校验 | `corpus_pipeline` 新增 `closure_verify()` | 返回 `{closures:[{id,total,covered,exempt,missing,verdict}]}` |")
A("| 接入门禁 | `quality_gates` / `gate_check` | **missing 非空 ⇒ 该项 FAIL**，由编排器判定 |")
A("| 探针标定 | 上两者的前置 | 未过标定的探针 → 该项 `invalid`，输出「不作结论」而非「无误」 |")
A("")
A("**与旧机制的关系**：不替换，是**补一层**——")
A("")
A("```")
A("旧 validate_extraction  →  保证「抽出来的对不对」   （保留）")
A("新 closure_verify       →  保证「该抽的都抽了没有」 （新增）")
A("两者都过 → 才允许进入图谱编译")
A("```")
A("")
A("---")
A("")
A("## 六、一句话")
A("")
A("| 问题 | 答案 |")
A("|------|------|")
A("| 是 verify 机制的问题吗？ | **是，而且是根因**：旧机制遍历产物，逻辑上不可能发现遗漏 |")
A("| 是校验不够严吗？ | **不是**。再严的自洽性校验也查不出缺失——**方向错了** |")
A("| 修正的关键是什么？ | **把源变成可枚举的索引，然后做集合差**；并让探针先自证 |")
A("| 为什么这次能查出来？ | 因为我（被要求反思后）临时写了正则版源索引——**这正是应该固化成机制的东西** |")
A("")
A("> 最后一句自省：本次七个闭环全部是我**事后手写脚本**跑出来的。"
  "旧机制里没有它们，所以**在你不问的情况下，这 54 条依据、29 条设备参数、3 个未引用节点"
  "会安静地留在交付物里**。这不是我不小心，这是机制允许的默认结果。")
A("")

(WS / "交付物" / "报告" / "verify机制修正方案.md").write_text("\n".join(L), encoding="utf-8")
print(json.dumps({
    "ledger": {k: (v if not isinstance(v, list) else len(v)) for k, v in LEDGER.items()},
    "calibration_valid": len(calib) - len(INVALID), "calibration_total": len(calib),
    "invalid_probes": [c["probe"] for c in INVALID],
    "closures": [{"id": c["id"], "total": c["total"], "covered": c["covered"],
                  "missing": c.get("missing_count", len(c["missing"])),
                  "recall": c.get("recall_pct"), "verdict": verdicts[c["id"]]} for c in CLOSURES],
    "out": "交付物/报告/verify机制修正方案.md",
}, ensure_ascii=False, indent=2))
