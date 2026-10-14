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
# B/C. 派生校核与判定 —— **必须路由到 Semantica Reasoner**（已删除本地实现）
# --------------------------------------------------------------------------- #
# 原实现（本会话删除，客户反馈 ②④⑤ 全部源自此段）：
#   B 逐条求值 compute 规则 + computed[target] 链式传递  = **手写前向链**替身
#     → Semantica 未参与却被记成完成，并产出假的「建筑高度 60 vs 49」冲突，级联出错误消防类别
#   C 直接判定「规模符合性/建安费口径/投资闭合」 = 手写推理
#     → 无视「人均指标为上限」，把 18000 < 18040 判成「不满足」
#   diff_sum = Σ(delta) 把**不同量纲**（万元/米/千瓦时）相加 → 「差额合计 18.25 万元」，单位标签本身即错
# 现行为：推理交给 Semantica；不可用时**不产出任何派生/判定结论**（fail-closed），
#         只登记状态，由判据判 invalid —— 绝不硬算、绝不用替身。
derivation, diff_items, unresolved, judgements = [], [], [], []

_reason_status = {"engine": None, "status": "not_run", "reason": ""}
# ★ 先把 kp 工程加入 sys.path —— 否则会把自己的 import 错误误报成「引擎失败」
import sys as _sys
_KP = "/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert"
if _KP not in _sys.path:
    _sys.path.insert(0, _KP)
try:
    from corpus_pipeline import providers as _P          # noqa: PLC0415
    _rp = _P.get_provider("relation")
    _facts = [{"subject": n.get("subject"), "predicate": n.get("predicate"),
               "value": n.get("value"), "unit": n.get("unit"), "source": n.get("source")}
              for n in nodes]
    _out = _rp.run_reasoning(_facts, rules)
    # ★ 输出为空 = 静默降级：引擎被调用但没产出。**不得记成 ok**（那正是假通过）。
    #   对应 Semantica 侧 workflow.require(step, engines, output_count, min_output)。
    if not _out:
        _reason_status = {"engine": getattr(_rp, "name", "?"), "status": "invalid",
                          "outputs": 0,
                          "reason": "引擎已调用但输出为空 —— 疑似静默降级（require(min_output=1) 应拦截），"
                                    "不得视为推理完成"}
    else:
        _reason_status = {"engine": getattr(_rp, "name", "?"), "status": "ok",
                          "outputs": len(_out)}
        derivation = list(_out)
except NotImplementedError as _e:
    _reason_status = {"engine": None, "status": "invalid",
                      "reason": f"Semantica 推理未注册：{_e}"}
except Exception as _e:                                   # noqa: BLE001
    _reason_status = {"engine": None, "status": "invalid",
                      "reason": f"Semantica 推理失败：{type(_e).__name__}: {_e}"}

(ROOT / "reasoning" / "derivation_status.json").write_text(
    json.dumps({"status": _reason_status,
                "note": "推理（规则求值/前向链）必须由 Semantica Reasoner 承担；"
                        "未参与时**不产出结论**，判据据此判 invalid —— 禁止降级或替身"},
               ensure_ascii=False, indent=2), encoding="utf-8")

# C.（判定类）：推理未执行时**不由本地判定**，只登记 judgment_required
_JUDGE_Q = {
    "J-规模符合性": "设计地上建筑面积是否满足人均指标法测算的用房需求？"
                    "（须先取人均指标的口径方向：上限/下限）",
    "J-建安费口径": "表12-1 建安工程招标估算金额与表13-1 建安工程费用是否一致？"
                    "（须先确认口径范围：是否含拆除费/室外总体/抗震支架）",
    "J-投资构成闭合": "投资估算表各层级「分项之和」是否等于「合计」？"
                      "（须按量纲分组核对，**不得跨量纲求和**）",
}
for _rid, _q in _JUDGE_Q.items():
    judgements.append({"id": _rid, "question": _q, "premises": {}, "verdict": None,
                       "status": "judgment_required",
                       "note": ("推理未执行（Semantica 未参与）⇒ 不由本地判定；"
                                "交 Semantica Reasoner 或人工，**不产出任何结论**"
                                if _reason_status["status"] != "ok" else
                                "由 Semantica Reasoner 产出（见 derivation）")})

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
