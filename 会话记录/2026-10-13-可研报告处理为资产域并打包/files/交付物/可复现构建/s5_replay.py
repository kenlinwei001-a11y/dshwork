# -*- coding: utf-8 -*-
"""工序 5 推演回放（确定性补强层）。

kp 工具层 stage_5_replay 只按 (subject, predicate) 字面比对，有两个不足：
  ① 限定词未归一（"70" vs "≤70" 被误报为冲突）；
  ② 只做「同键异值」比对，不做「按规则重算 → 与原文声明值比对」的派生校核。
本脚本全部确定性、零 LLM、可复现：
  A. 数值归一 + 主体别名归并后重跑同键异值检测；
  B. 逐条求值 compute 规则（含规则链式传递），与原文声明值比对，输出派生差异；
  C. 显式求值 select 判定规则（规模符合性 / 投资闭合 / 建安费口径 / 节能版本）；
  D. 归集证据层软约束版本冲突（同一规范多版本并存 / 废止版本被引用）。
产出：reasoning/derivation.yaml、reasoning/decisions.yaml、reasoning/replay.json、quality/conflicts.yaml
"""
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "SHUFE-BDC-2019-001"
SAFE = {"round": round, "abs": abs, "floor": math.floor, "ceil": math.ceil,
        "max": max, "min": min, "pow": pow}

QUALIFIER = re.compile(r"^[≤≥<>=约不小于不大于]+")


def num(value):
    if value is None:
        return None
    s = QUALIFIER.sub("", str(value).strip())
    m = re.match(r"^-?[\d,]+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def canon(value):
    n = num(value)
    return str(value).strip() if n is None else f"{n:g}"


SUBJECT_ALIAS = {
    "教师用水": "办公用水（288 人）", "办公": "办公用水（288 人）",
    "科研学生": "科研学生用水（1800 人）", "学生用水": "科研学生用水（1800 人）",
    "公共配套服务用房": "公共服务配套用房",
}
# 规则依赖名 → (subject, predicate) 显式别名（术语归一，记录在案、可审计）
DEP_ALIAS = {
    "本项目建筑面积": ("本项目", "总建筑面积"),
    "公共服务配套用房使用面积合计": ("公共服务配套用房", "使用面积需求合计"),
    "公共服务配套用房综合平面利用系数": ("公共服务配套用房", "综合平面利用系数"),
    "工程建设其他费": ("本项目", "工程建设其他费用"),
    "原建筑拆除费用": ("本项目", "原建筑拆除费用"),
    "科研学生用水人数": ("科研学生", "用水人数"),
    "科研学生用水定额": ("科研学生", "用水定额"),
    "办公用水人数": ("办公", "用水人数"),
    "办公用水定额": ("办公", "用水定额"),
    "教师用水日水量": ("教师用水", "日用水量"),
    "学生用水日水量": ("学生用水", "日用水量"),
    "未预见系数": ("本项目", "未预见系数"),
    "电力折标系数当量值": ("综合能耗·电力", "折标系数（当量值）"),
    "水折标系数": ("综合能耗·水", "折标系数"),
    "30HP机组单台制冷量": ("多联机室外机组30HP", "单台制冷量"),
    "30HP机组台数": ("多联机室外机组30HP", "台数"),
    "16HP机组单台制冷量": ("多联机室外机组16HP", "单台制冷量"),
    "16HP机组台数": ("多联机室外机组16HP", "台数"),
    "10HP机组单台制冷量": ("多联机室外机组10HP", "单台制冷量"),
    "10HP机组台数": ("多联机室外机组10HP", "台数"),
    "道路广场硬地铺装": ("道路、广场、硬地、铺装", "估算金额"),
    "通风空调工程": ("通风、空调工程", "估算金额"),
    "绿化景观": ("绿化、景观", "估算金额"),
    "施工监理费": ("施工监理费（含财务监理费）", "估算金额"),
}
AMOUNT_PREDICATES = {"估算金额", "取值", "面积需求", "合计", "需求建筑面积", "规划人数合计"}

nodes = json.loads((ROOT / "graph" / "nodes.yaml").read_text(encoding="utf-8"))
rules = json.loads((ROOT / "graph" / "rules.yaml").read_text(encoding="utf-8"))

computed: dict[str, float] = {}          # 规则目标 → 重算值（供规则链式传递）
computed_nodes: dict[str, list] = {}


def resolve(dep: str):
    """返回 (值, 来源节点列表, 原因)。三级匹配 + 显式别名 + 已重算目标。

    原因 ∈ ok / missing / ambiguous_conflict：同一键存在多个未裁决取值时返回
    ambiguous_conflict —— 按铁律「不带着冲突往下走」，派生校核因冲突而阻塞，不擅自取一个值硬算。
    """
    if dep in computed:
        return computed[dep], computed_nodes.get(dep, []), "ok"
    if dep in DEP_ALIAS:
        alias = DEP_ALIAS[dep]
        if alias is None:
            return None, [], "missing"
        subj, pred = alias
        cands = [n for n in nodes if n["subject"] == subj and n["predicate"] == pred]
    else:
        cands = [n for n in nodes if n["subject"] == "本项目" and n["predicate"] == dep]
        if not cands and "·" in dep:
            subj, pred = dep.split("·", 1)
            cands = [n for n in nodes if n["subject"] == subj and n["predicate"] == pred]
        if not cands:  # subject+predicate 拼接匹配
            cands = [n for n in nodes if n["subject"] + n["predicate"] == dep]
        if not cands:  # subject == dep 且谓词属于金额/取值族
            cands = [n for n in nodes if n["subject"] == dep and n["predicate"] in AMOUNT_PREDICATES]
        if not cands:  # 唯一同谓词
            cands = [n for n in nodes if n["predicate"] == dep]
    vals = {canon(n.get("value")) for n in cands if num(n.get("value")) is not None}
    if not vals:
        return None, cands, "missing"
    if len(vals) != 1:
        return None, cands, "ambiguous_conflict"
    return num(next(iter(vals))), cands, "ok"


# --------------------------------------------------------------------------- #
# A. 同键异值冲突（归一后）
# --------------------------------------------------------------------------- #
conflicts: list[dict] = []


def add_conflict(ctype, subject, predicate, values, involved, note=""):
    conflicts.append({"type": ctype, "subject": subject, "predicate": predicate,
                      "values": sorted({canon(v) for v in values}),
                      "involved": sorted(set(involved)), "status": "待审", "note": note})


by_key: dict[tuple[str, str], list[dict]] = {}
for n in nodes:
    if num(n.get("value")) is None:
        continue
    by_key.setdefault((SUBJECT_ALIAS.get(n["subject"], n["subject"]), n["predicate"]), []).append(n)

for (subj, pred), fs in by_key.items():
    if len({canon(f.get("value")) for f in fs}) > 1:
        add_conflict("numeric", subj, pred, [f.get("value") for f in fs], [f["id"] for f in fs],
                     "同 (主体, 属性) 在不同章节取值不一致，按「待审」呈现，未擅自裁决")

# --------------------------------------------------------------------------- #
# B. 派生校核
# --------------------------------------------------------------------------- #
derivation, diff_items, unresolved = [], [], []
for r in rules:
    if r.get("kind") != "compute":
        continue
    expr = r.get("expr", "")
    if "=>" in expr:
        continue
    deps = r.get("deps") or []
    env, missing, blocked, srcs, ph = {}, [], [], [], {}
    for i, d in enumerate(deps):
        v, cs, why = resolve(d)
        ph[d] = f"v{i}"                      # 安全占位名（依赖名可能以数字/中文字符开头）
        if why == "ok":
            env[ph[d]] = v
            srcs.extend(c["id"] for c in cs[:1])
        elif why == "ambiguous_conflict":
            blocked.append({"dep": d, "values": sorted({canon(c.get("value")) for c in cs})})
        else:
            missing.append(d)
    py = expr
    for d in deps:
        py = py.replace("{" + d + "}", ph[d])
    if blocked:
        unresolved.append({"rule": r["id"], "label": r.get("label"), "reason": "blocked_by_conflict",
                           "detail": blocked})
        continue
    if missing or "{" in py:
        unresolved.append({"rule": r["id"], "label": r.get("label"), "reason": "missing_deps",
                           "missing_deps": missing})
        continue
    try:
        got = eval(py, {"__builtins__": {}}, {**SAFE, **env})  # noqa: S307 受控表达式
    except Exception as e:  # noqa: BLE001
        unresolved.append({"rule": r["id"], "label": r.get("label"), "reason": "eval_error", "error": str(e)})
        continue

    target = r.get("target", "")
    # 先取原文声明值（此时 computed 尚未包含 target，resolve 走事实节点分支）
    stated_v, stated_nodes, _why = resolve(target)
    computed[target] = got
    computed_nodes[target] = []
    item = {"rule": r["id"], "label": r.get("label"), "expr": expr,
            "inputs": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in env.items()},
            "input_nodes": sorted(set(srcs)),
            "computed": round(got, 4) if isinstance(got, float) else got,
            "stated": stated_v, "stated_nodes": [n["id"] for n in (stated_nodes or [])[:2]],
            "basis": r.get("basis", "")}
    if stated_v is None:
        item["status"] = "已重算（原文无对应声明值）"
        derivation.append(item)
        continue
    delta = abs(round(got, 2) - round(stated_v, 2))
    ratio = (delta / stated_v * 100) if stated_v else 0.0
    item.update({"delta": round(delta, 2), "delta_pct": round(ratio, 2)})
    if delta > 1e-6:
        item["status"] = "待审"
        diff_items.append(item)
        add_conflict("derivation", r.get("label", ""), "派生值 vs 原文值",
                     [f"重算 {round(got, 2)}", f"原文 {round(stated_v, 2)}"],
                     sorted(set(srcs)) + [n["id"] for n in (stated_nodes or [])[:1]],
                     f"按规则 {r['id']} 重算得 {round(got, 2)}，原文写 {round(stated_v, 2)}"
                     f"（差 {round(delta, 2)}，{round(ratio, 2)}%）；按铁律不擅自改数")
    else:
        item["status"] = "闭合"
    derivation.append(item)

# --------------------------------------------------------------------------- #
# C. 判定类（select）规则的显式确定性求值
# --------------------------------------------------------------------------- #
judgements = []


def judge(rid, question, premises, verdict, note):
    judgements.append({"id": rid, "question": question, "premises": premises,
                       "verdict": verdict, "note": note, "status": "待审"})


demand, _, _ = resolve("地上总建筑面积需求")
design, _, _ = resolve("地上建筑面积")
if demand is not None and design is not None:
    judge("J-规模符合性", "设计地上建筑面积是否满足人均指标法测算的用房需求？",
          {"地上总建筑面积需求": demand, "设计地上建筑面积": design},
          "不满足" if design < demand else "满足",
          f"需求 {demand:g} ㎡ > 设计 {design:g} ㎡，差 {demand - design:g} ㎡；"
          f"原文结论为「设计规模在各类用房面积需求范围内，规模设置合理」，该结论与自身测算不符")

bid, _, _ = resolve("建安工程招标估算金额")
baf, _, _ = resolve("建筑安装工程费用")
if bid is not None and baf is not None:
    judge("J-建安费口径", "表12-1 建安工程招标估算金额与表13-1 建安工程费用是否一致？",
          {"表12-1 建安工程": bid, "表13-1 建筑安装工程费用": baf},
          "不一致" if abs(bid - baf) > 1e-6 else "一致",
          f"差 {abs(baf - bid):g} 万元；招标估算金额通常应小于等于估算费用，"
          f"此处口径差异需客户说明是否含拆除费/室外总体/抗震支架/绿色二星增量")

diff_sum = sum(d.get("delta", 0) for d in diff_items)
if diff_items:
    judge("J-投资构成闭合", "投资估算表各层级「分项之和」是否等于「合计」？",
          {"存在差异的规则数": len(diff_items), "差额合计(万元)": round(diff_sum, 2)},
          "不闭合",
          "；".join(f"{d['label']}: {d['computed']:g} vs {d['stated']:g}" for d in diff_items[:8]))

(ROOT / "reasoning" / "judgements.yaml").write_text(json.dumps(judgements, ensure_ascii=False, indent=2), encoding="utf-8")

# --------------------------------------------------------------------------- #
# D. 证据层软约束版本冲突
# --------------------------------------------------------------------------- #
evidence_doc = json.dumps(json.loads((ROOT / "evidence" / "evidence.yaml").read_text(encoding="utf-8")),
                          ensure_ascii=False)
SOFT_FAMILIES = {
    "无障碍设计规范": ["GB50763-2012", "GB50673-2002", "JGJ50-2001"],
    "公共建筑节能设计标准": ["GB50189-2005", "DGJ08-107-2012", "DGJ08-107-2015"],
    "建筑照明设计标准": ["GB50034-2004", "GB50034-2013"],
    "采暖通风与空气调节设计规范": ["GB50019-2003", "GB50736-2012"],
    "上海市建筑抗震设计规程": ["DGJ08-9-2003", "DGJ08-9-2013"],
}
for fam, variants in SOFT_FAMILIES.items():
    present = [v for v in variants if v in evidence_doc]
    if len(present) > 1:
        add_conflict("spec_version", fam, "引用版本", present, [],
                     f"同一规范在本报告内出现 {len(present)} 种版本：{'、'.join(present)}；"
                     f"属软约束版本冲突，按「待审」呈现，未擅自替稿")

name_variants = [v for v in ["《普通高等学校建筑规划面积指标》（建标191-2018）",
                             "《普通高等学校建筑面积指标》（建标191-2018）"] if v in evidence_doc]
if len(name_variants) > 1:
    add_conflict("spec_naming", "建标191-2018", "规范名称写法", name_variants, [],
                 "同一编号两种名称写法：1.2 节写「建筑规划面积指标」（旧文件名称），5.6 节写「建筑面积指标」；"
                 "名称是否准确须按现行官方口径核对，agent 不臆断")

# --------------------------------------------------------------------------- #
# 归并输出
# --------------------------------------------------------------------------- #
seen, merged = set(), []
for c in conflicts:
    k = (c["type"], c["subject"], c["predicate"], tuple(c["values"]))
    if k not in seen:
        seen.add(k)
        merged.append(c)

(ROOT / "quality" / "conflicts.yaml").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
(ROOT / "reasoning" / "derivation.yaml").write_text(json.dumps({
    "replayed_rules": len(derivation), "unresolved_rules": unresolved,
    "closure_ok": [d for d in derivation if d.get("status") == "闭合"],
    "derivation_diff": diff_items,
    "derivation_nostated": [d for d in derivation if d.get("status", "").startswith("已重算")],
}, ensure_ascii=False, indent=2), encoding="utf-8")
(ROOT / "reasoning" / "decisions.yaml").write_text(json.dumps(
    [{"id": f"D-{i+1:03d}", "type": c["type"], "subject": c["subject"], "predicate": c["predicate"],
      "decision": "待审（呈现客户裁决，未擅自改数或补口径）", "values": c["values"],
      "rationale": c.get("note", ""), "involved": c["involved"]}
     for i, c in enumerate(merged)], ensure_ascii=False, indent=2), encoding="utf-8")

replay = {"replayed": len(nodes), "contradictions": merged, "judgements": judgements,
          "derivation": {"rules_replayed": len(derivation), "rules_unresolved": len(unresolved),
                         "closure_ok": len([d for d in derivation if d.get("status") == "闭合"]),
                         "derivation_diff": len(diff_items)}}
(ROOT / "reasoning" / "replay.json").write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps({"conflicts_total": len(merged),
                  "by_type": {t: sum(1 for c in merged if c["type"] == t) for t in sorted({c["type"] for c in merged})},
                  "rules_replayed": len(derivation), "rules_unresolved": len(unresolved),
                  "closure_ok": len([d for d in derivation if d.get("status") == "闭合"]),
                  "derivation_diff": len(diff_items), "judgements": len(judgements)},
                 ensure_ascii=False, indent=2))
print("--- 派生差异 ---")
for d in diff_items:
    print(f"  {d['rule']:26s} 重算={d['computed']:>10g} 原文={d['stated']:>10g} 差={d['delta']:>7g} ({d['delta_pct']}%)")
print("--- 判定 ---")
for j in judgements:
    print(f"  {j['id']:14s} {j['verdict']}")
blocked_rules = [u for u in unresolved if u.get("reason") == "blocked_by_conflict"]
gap_rules = [u for u in unresolved if u.get("reason") == "missing_deps"]
print("--- 因未裁决冲突而阻塞的规则（不带着冲突往下算）---")
for u in blocked_rules:
    print(f"  {u['rule']:28s} 阻塞依赖: " + "；".join(f"{d['dep']}={'/'.join(d['values'])}" for d in u["detail"]))
print("--- 因缺事实而未解析的规则 ---")
for u in gap_rules:
    print(f"  {u['rule']:28s} 缺: {u.get('missing_deps')}")

gaps = [{"id": f"G-{i+1:03d}", "type": "missing_fact", "rule": u["rule"], "label": u.get("label"),
         "missing": u.get("missing_deps"),
         "note": "原文未给出该口径，保持显式未知；不估算、不套用同类项目。"}
        for i, u in enumerate(gap_rules)]
gaps += [{"id": f"G-{len(gaps)+j+1:03d}", "type": "blocked_by_conflict", "rule": u["rule"],
          "label": u.get("label"), "depends_on_conflict": [d["dep"] for d in u["detail"]],
          "note": "依赖项存在未裁决数值冲突，按铁律「不带着冲突往下走」，派生校核阻塞。"}
         for j, u in enumerate(blocked_rules)]
gaps += [
    {"id": "G-901", "type": "explicit_unknown", "subject": "容积率、绿地率",
     "note": "原文：容积率、绿地率等指标全校统筹（表1-2 注），本项目无独立取值，保持未知。"},
    {"id": "G-902", "type": "explicit_unknown", "subject": "实验室通风专项取值",
     "note": "原文表6-8 通风换气次数仅覆盖卫生间/电梯机房/水泵房，未给出实验室换气次数、通风柜台数与排风量；"
             "属高校科研用房评审必问取值点，保持未知并转 ASK。"},
    {"id": "G-903", "type": "explicit_unknown", "subject": "原有第五教学楼拆除手续",
     "note": "原文：拆除手续正同步进行办理中；附件清单亦标注（待补充）。"},
    {"id": "G-904", "type": "explicit_unknown", "subject": "国拨资金批复文件",
     "note": "资金筹措方案列出申请国拨资金 6000 万元，但附件未含上级批复文件。"},
    {"id": "G-905", "type": "explicit_unknown", "subject": "变压器容量匹配口径",
     "note": "原文给出总计算负荷 952kW 与增容后 2×2000kVA，未给功率因数与需要系数，无法复算匹配性。"},
    {"id": "G-906", "type": "explicit_unknown", "subject": "负荷估算面积口径",
     "note": "原文只给 45W/㎡ 与 25W/㎡ 两个指标与总计算负荷 952kW，未给出所采用的面积基数。"},
    {"id": "G-907", "type": "explicit_unknown", "subject": "竣工财务决算批准文号",
     "note": "原文述及报发展规划司批准，未给出文号。"},
]
(ROOT / "quality" / "gaps.yaml").write_text(json.dumps(gaps, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"--- 缺口登记 quality/gaps.yaml：{len(gaps)} 条 ---")
