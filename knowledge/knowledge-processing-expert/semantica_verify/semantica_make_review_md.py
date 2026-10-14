# -*- coding: utf-8 -*-
import json
from pathlib import Path
from datetime import date
from collections import defaultdict, Counter
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from semantica_metrics import stats as _jstats, fmt as _jfmt, tier_fmt as _tier_fmt

BT = chr(96)
WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"; OUT = PKG / "外部核验"
q = json.loads((OUT / "subject-normalization-queue.yaml").read_text(encoding="utf-8"))
E = q["entries"]
need = [e for e in E if e["review_label"].startswith("待人工判断")]
order = {"待人工判断（引擎分歧）": 0, "待人工判断": 1}
def key(e): return (order[e["review_label"]], -e["confidence"])
need.sort(key=key)
GCOUNT = Counter(e["review_label"] for e in need)
L = []; A = L.append
A("# 实体归一 · 人工判断清单")
A("")
A(f"> 标签：**待人工判断** = 需人工决定是否归一（含 引擎分歧）；**不需人工** = 已自动判为不同概念。生成 {date.today().isoformat()}")
A("")
A("**收敛过程**：Semantica 去重候选 **1104 组** → 规则判官（Semantica reasoning，替代 JEV）自动排除 737 组 → LLM 判官（DeepSeek，DIFF 精度 100%）再排除 296 组 → **仅 {n} 条需人工**（降幅 {p:.0f}%）。".replace("{n}", str(len(need))).replace("{p:.0f}", f"{(1-len(need)/1104)*100:.0f}"))
A("")
A("| 分档 | 条数 | 判据 | 人工投入 |")
A("| --- | --- | --- | --- |")
A(f"| A 高置信（建议采纳 · 抽审） | {sum(1 for e in need if e['review_tier'].startswith('A'))} | 规则与 LLM 一致 | 只抽审 |")
A(f"| B 中置信（快速确认） | {sum(1 for e in need if e['review_tier'].startswith('B'))} | 单路判官支持 | 快速过目 |")
A(f"| C 低置信（逐条审校） | {sum(1 for e in need if e['review_tier'].startswith('C'))} | 两路分歧或信息不足 | 逐条判断 |")
A(f"| **合计** | **{len(need)}** | 原始候选 1104 | |")
A("")
A("**分档精度校准**（对 17 组人工标准答案）：" + _tier_fmt(str(OUT), "A") + "；B 档样本不足。阈值据此外推，非拍脑袋。")
A("")
A("**操作方式**：末列填 合并 / 不合并 / 裁决：取值，回填本文件即可。")
A("")
cur = None
for e in need:
    if e["review_label"] != cur:
        cur = e["review_label"]; A("## " + cur + "（" + str(GCOUNT[cur]) + " 条）"); A("")
        A("| # | subject A | subject B | 取值 | 相似度 | 规则 | confidence | 分档 | LLM | 人工决定 |")
        A("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    va = e["value_a"] or "—"; vb = e["value_b"] or "—"
    val = f"{va} ／ {vb}" if va != vb else va
    ll = e["llm_judge"] or {}
    A(f'| {e["id"]} | {e["subjects"][0]} | {e["subjects"][1]} | {val} | {e["name_similarity"]} | '
      f'{e["rule_engine"]["verdict"]}/{e["rule_engine"]["basis"]} | **{e["confidence"]}** | {e["review_tier"][0]} | '
      f'{ll.get("verdict") or "—"} |  |')
A("")
(OUT / "实体归一-人工判断清单.md").write_text("\n".join(L), encoding="utf-8")
rows = ["id\treview_label\tconfidence\treview_tier\tsubject_a\tsubject_b\tvalue_a\tvalue_b\tsimilarity\trule_verdict\trule_basis\tllm_verdict\tfinal_verdict\thuman_decision"]
for e in need:
    ll = e["llm_judge"] or {}
    rows.append("\t".join([e["id"], e["review_label"], str(e["confidence"]), e["review_tier"],
        e["subjects"][0], e["subjects"][1], e["value_a"], e["value_b"], str(e["name_similarity"]),
        e["rule_engine"]["verdict"], e["rule_engine"]["basis"], str(ll.get("verdict") or ""),
        e["final_verdict"], ""]))
(OUT / "entity-normalization-queue.tsv").write_text("\n".join(rows), encoding="utf-8")
print("清单条数:", len(rows) - 1)
print("\n=== A 档（建议直接采纳，7 条）===")
for e in [x for x in need if x["review_tier"].startswith("A")]:
    print(f'  conf={e["confidence"]}  {e["subjects"][0]} ~ {e["subjects"][1]}  值={e["value_a"] or e["value_b"]}  [{e["final_verdict"]}]')
print("\n=== 引擎分歧（优先，前 8）===")
for e in [x for x in need if x["review_label"].endswith("分歧")][:8]:
    print(f'  conf={e["confidence"]}  {e["subjects"][0]}({e["value_a"]}) ~ {e["subjects"][1]}({e["value_b"]})')
