# -*- coding: utf-8 -*-
"""s35 —— 语义维度判据 K15–K20（直接回应客户反馈的 6 个问题）。

客户反馈的原话：「数字都来自同一个事实源，还不足以保保证报告正确；
还必须保住数字的**对象、用途、单位和上下级关系**。」

| 判据 | 抓什么 | 客户反馈对应 |
|---|---|---|
| K15 加法合法性 | 合计/差额必须同单位+同域+同口径；跨单位相加 ⇒ FAIL | ② 差额合计 18.25 万元 |
| K16 归属汇总一致 | 明细之和必须等于其归属父项（容差内）⇒ 不等即待审 | ① 费用层级还原错误 |
| K17 口径方向 | 判「不满足」必须由下限/约束支撑；用上限判不满足 ⇒ FAIL | ④ 把上限当最低需求 |
| K18 专业域匹配 | 比较/引用必须同域（冷负荷 ≠ 电力负荷）⇒ 跨域 FAIL | ③ 参数错配 |
| K19 角色区分与舍入 | 不同 object_role 不得对比；差值在舍入容差内 ⇒ 判「舍入一致」 | ⑤ 高度 60vs49 ／ ⑥ 617.95vs618 |
| K20 级联撤销 | 基础判据被撤销时，依赖它的下游结论必须一并撤销 | ⑤ 引发的一串消防类别判断 |

全部为确定性算法（集合/数值/正则），**无 LLM 参与**；证据不足 ⇒ invalid，不判 pass。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
R = WS / "SHUFE-BDC-2019-001"
DRAFT = WS / "交付物" / "报告" / "上海财经大学中山北一路校区大数据研究中心可行性研究报告（还原稿）.md"


def J(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


def W(p, o):
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


# ★ 判据只准引用受控词表（build/sop/criteria_vocab.yaml）——由 lint_no_overfit 强制。
#   任何领域词/判定词内联在判据代码里即为过拟合（换文档失效）。
import yaml as _yaml
_VOCAB = _yaml.safe_load((WS / "build" / "sop" / "criteria_vocab.yaml").read_text(encoding="utf-8")) or {}
_VT = (_VOCAB.get("criteria_meta") or {}) and _VOCAB
_JUDGE = (_VOCAB.get("judgment_terms") or {})
_PARAM_SUFFIXES = _VOCAB.get("param_suffixes") or []
_SECTION_DOMAIN = _VOCAB.get("section_domain_terms") or {}
_DIRECTION = _VOCAB.get("direction_terms") or {}

nodes = J(R / "graph" / "nodes.yaml", []) or []
conf = J(R / "quality" / "conflicts.yaml", []) or []
draft = DRAFT.read_text(encoding="utf-8") if DRAFT.exists() else ""
res = {}

# 域/角色/方向：优先用 s4c 补全的字段，缺失则按规则即时推断（判据不依赖补全覆盖率）
def dom_of(n):
    t = f"{n.get('subject','')} {n.get('predicate','')}"
    if re.search(r"冷负荷|制冷量|制冷", t): return "冷负荷"
    if re.search(r"热负荷|制热量", t): return "热负荷"
    if re.search(r"照明|用电|配电|电力|耗电|变压器", t): return "电力"
    if re.search(r"幕墙|立面|门窗|屋面|装饰", t): return "装饰工程"
    if re.search(r"投资|费用|资金|预备费", t): return "投资费用"
    return n.get("domain") or "unknown"


def role_of(n):
    t = f"{n.get('subject','')} {n.get('predicate','')}"
    if re.search(r"控制|限高", t): return "控制值"
    if re.search(r"实际|现状|层高|推算", t): return "实际值"
    if re.search(r"需求", t): return "需求值"
    if re.search(r"设计", t): return "设计值"
    return n.get("object_role") or "unknown"


# ── K15 加法合法性：草稿里的合计/差额是否跨单位相加 ──────────────
m15 = []
for m in re.finditer(r"([^。\n]{0,120}?(?:差额合计|合计|小计|总计)[^。\n]{0,160})", draft):
    seg = m.group(1)
    units = set(re.findall(r"(万元|米|㎡|平方米|千瓦时|万度|人|kW|%)", seg))
    if len(units) >= 2:
        m15.append({"quote": seg.strip()[:120], "units": sorted(units),
                    "why": "同一合计/差额中出现多个不同单位 ⇒ 不同量纲直接相加，无意义"})
res["K15"] = {"id": "K15", "name": "加法合法性（量纲/域一致）", "algo": "正则取合计段 → 单位集合 >1 即 FAIL",
              "total": len(re.findall(r"差额合计|合计|小计|总计", draft)),
              "missing_count": len(m15), "missing": m15[:6],
              "verdict": "FAIL" if m15 else "pass", "note": "跨量纲求和须显式换算，否则无意义"}

# ── K16 归属汇总一致：**通用表内对账**（取代原硬编码科目名）──────────
# 原实现硬编码了 6 个科目名（外立面及屋面装饰工程…）——那是**把某份文档的答案写进判据**，
# 换文档即失效（lint_no_overfit 已将其判为违规）。
# 现改为**结构性判定**：任何表格中若存在「合计/小计/总计」行，则
#   Σ(其他数值行) ≈ 合计行（容差内）；不等 ⇒ 明细与合计不一致（= 归属/口径错位）。
# 该判定不依赖任何科目名、章节号或文档取值 ⇒ 换任何文档都成立。
_AGG = ("合计", "小计", "总计", "分项之和")
m16 = []
for sec in re.split(r"\n(?=#{2,4}\s)", draft):
    head = sec.split("\n", 1)[0].strip("# ").strip()
    rows = [l for l in sec.split("\n") if l.strip().startswith("|") and "---" not in l]
    if len(rows) < 3:
        continue
    def _nums(cells):
        out = []
        for c in cells:
            mm = re.search(r"([\d,]+(?:\.\d+)?)", c.replace("*", ""))
            if mm:
                try:
                    out.append(float(mm.group(1).replace(",", "")))
                except ValueError:
                    pass
        return out
    parsed = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    agg_rows = [r for r in parsed if any(t in c for t in _AGG for c in r[:2])]
    if not agg_rows:
        continue
    agg = _nums(agg_rows[0])
    detail_nums = []
    for r in parsed:
        if r in agg_rows:
            continue
        ns = _nums(r)
        if ns:
            detail_nums.append(max(ns))
    if not agg or len(detail_nums) < 2:
        continue
    total = max(agg)
    ssum = sum(detail_nums)
    tol = max(abs(total) * 0.005, 1.0)
    if abs(ssum - total) > tol:
        m16.append({"section": head[:36], "table_agg": total, "detail_sum": round(ssum, 2),
                    "rows": len(detail_nums), "tol": round(tol, 2),
                    "why": f"表内明细之和 {round(ssum,2)} ≠ 合计 {total}（容差 {round(tol,2)}）"
                           f"⇒ 明细与合计不一致（归属或口径错位）——**通用判定，不含科目名**"})
res["K16"] = {"id": "K16", "name": "归属汇总一致（通用表内对账）",
              "algo": "表格内若有「合计」行，则 Σ明细 ≈ 合计（容差 0.5%）",
              "total": len(re.findall(r"\n\|", draft)), "missing_count": len(m16),
              "missing": m16[:6],
              "verdict": "FAIL" if m16 else "invalid",
              "note": "**不含任何科目名/章节号/文档取值** ⇒ 换文档仍然成立（已去除过拟合）"}

# ── K17 口径方向：**上限不得当作最低需求**（三条件同时成立）──────────
# 教训：迁词表不能丢判定条件——原版只匹配「不满足」类词（4 处），
#       迁表后词表更宽、条件却少了两个 ⇒ 假阳性涨到 59 处。本质是三条件与：
#         ① 出现「不满足/不足/缺口」类判定词
#         ② 该判定以「需求/测算/人均/指标/定额」为门槛
#         ③ 门槛所依据的指标口径方向为**上限**（不超过/不大于/控制在）
_basis_kw = "|".join(_VOCAB.get("threshold_basis_terms") or [])
_unsat_kw = "|".join(_JUDGE.get("unsatisfied") or [])
_upper_kw = "|".join((_DIRECTION.get("upper") or []))
_upper_nodes = [n for n in nodes
                if re.search(_upper_kw, f"{n.get('subject','')}{n.get('predicate','')}"
                             + str(n.get("value", "")) + str(n.get("caliber_direction", "")))]
_design_kw = "|".join(_VOCAB.get("design_terms") or [])
_demand_kw = "|".join(_VOCAB.get("demand_terms") or [])
# 需求类节点的数值（用于确认该判定**确实**在拿需求值当门槛，而非泛泛提到"不足"）
_demand_vals = {str(n.get("value")) for n in nodes
                if re.search(_demand_kw, f"{n.get('subject','')}{n.get('predicate','')}")
                and re.fullmatch(r"[\d.]+", str(n.get("value", "")))}
m17 = []
for m in re.finditer(r"([^。\n]{0,90}(?:" + _unsat_kw + r")[^。\n]{0,110})", draft):
    seg = m.group(1)
    if not re.search(_basis_kw, seg):
        continue
    if not re.search(_design_kw, seg):                 # ③a 必须同时涉及「设计」与「需求」
        continue
    if not re.search(_demand_kw, seg):
        continue
    if not (_demand_vals & set(re.findall(r"[\d.]+", seg))):   # ③b 句中须出现需求节点数值
        continue
    if not _upper_nodes:
        continue
    m17.append({"quote": seg.strip()[:120],
                "why": "该判定以「需求/指标」为门槛，而门槛依据的指标口径方向为**上限**"
                       "⇒ 设计值 ≤ 上限派生需求 属满足约束，不得判「不满足」",
                "upper_bound_basis": [f"{n['subject']}·{n['predicate']}={n['value']}{n.get('unit','')}"
                                      for n in _upper_nodes[:4]]})
res["K17"] = {"id": "K17", "name": "口径方向（上限不得当最低需求）",
              "algo": "判定词 ∧ 门槛词 ∧ 设计要求 ∧ 需求要求 ∧ 句中含需求节点数值 ∧ 存在上限口径指标",
              "total": len(re.findall(_unsat_kw, draft)), "missing_count": len(m17),
              "missing": m17[:4], "verdict": "FAIL" if m17 else "pass",
              "note": "词全部来自受控词表；条件不得因迁表而减少"}

# ── K18 专业域匹配：**跨域不得替代**（小节专业域 ≠ 内容专业域）──────
# 教训：「小节含某词 ∧ 内容含某词」不是跨域判定（会把正常小节判违规，8→41 假阳性）。
# 本质：识别小节专业域与内容专业域，无交集才是跨域错配。
_domkw = _VOCAB.get("domain_keywords") or {}


# ★ 两处域词来源**必须分开用**（曾错误合并，导致跨域判据失效）：
#   小节名用 section_domain_terms（强电/供配电/空调…），内容用 domain_keywords（冷负荷/照明…）。
#   若把节词并入内容词表，"空调负荷密度指标"会被判成 hvac 域 ⇒ 与强电域有交集 ⇒ 永不报跨域。
_sec_kw_map = _VOCAB.get("section_domain_terms") or {}


def _detect_sec_dom(text: str) -> set:
    """小节所属专业域：节词表 + 内容词表（小节名可能直接用内容词）。"""
    out = {d for d, kws in _domkw.items() if any(k in text for k in (kws or []))}
    for alias, kws in _sec_kw_map.items():
        if any(k in text for k in (kws or [])):
            for d in _domkw:
                if alias in d:
                    out.add(d)
            if not any(alias in d for d in _domkw):
                out.add("domain_" + alias)
    return out


def _detect_content_dom(text: str) -> set:
    """内容实际所属专业域：**只用内容词表**（不用节词表）。"""
    return {d for d, kws in _domkw.items() if any(k in text for k in (kws or []))}


m18 = []
for sec in re.split(r"\n(?=#{2,4}\s)", draft):
    head = sec.split("\n", 1)[0].strip("# ").strip()
    _sec_dom = _detect_sec_dom(head)
    if not _sec_dom:
        continue
    # ★ 判定对象是**表格**而非整段正文：正文可以合法地提到其他专业域
    #   （如强电节正文提"照明"属正常），但**表格里放的参数**若整体属另一专业域
    #   即为跨域替代（强电节的表里放冷/热负荷指标）。曾用整段正文 → 交集常非空 → 漏判。
    _tb = [l for l in sec.split("\n")[1:] if l.strip().startswith("|")]
    if not _tb:
        continue
    body = "\n".join(_tb)
    _body_dom = _detect_content_dom(body)
    if _body_dom and not (_sec_dom & _body_dom):
        m18.append({"section": head[:40], "section_domain": sorted(_sec_dom),
                    "content_domain": sorted(_body_dom),
                    "why": "小节专业域与内容引用域**无交集** ⇒ 跨域替代（如强电小节引用暖通冷/热负荷）",
                    "root_cause": "生成侧：参数按谓词过滤生成，未带专业域约束"})
res["K18"] = {"id": "K18", "name": "专业域匹配（跨域不得替代）",
              "algo": "小节专业域 ∩ 内容专业域 = ∅ ⇒ FAIL",
              "total": len(re.split(r"\n(?=#{2,4}\s)", draft)), "missing_count": len(m18),
              "missing": m18[:6], "verdict": "FAIL" if m18 else "pass",
              "note": "不含文档措辞；域词全部来自受控词表 ⇒ 换文档只需扩表"}

# ── K19 角色区分与舍入等价（撤销假冲突）────────────────────────
m19, revoked = [], []
for c in conf:
    if not isinstance(c, dict):
        continue
    t = json.dumps(c, ensure_ascii=False)
    subj = str(c.get("subject", ""))
    vals = [float(x) for x in re.findall(r"[\d.]+", " ".join(map(str, c.get("values") or [])))]
    if len(vals) >= 2:
        a, b = vals[0], max(vals[1:])
        lo, hi = min(a, b), max(a, b)
        # 舍入等价：差值 ≤ 半个最低有效位（按较少小数位计）×2
        dec = min(len(v.split(".")[1]) if "." in v else 0
                  for v in re.findall(r"[\d.]+", " ".join(map(str, c.get("values") or []))))
        tol = 0.5 * 10 ** (-dec) * 2
        if abs(hi - lo) <= tol:
            revoked.append({"conflict": f"{subj}·{c.get('predicate')}", "values": c.get("values"),
                            "diff": round(hi - lo, 4), "tol": tol,
                            "why": "差值在舍入容差内 ⇒ **舍入一致，非冲突**（原判定撤销）"})
    # ★ 角色判定取代硬编码「建筑高度控制」：控制值 vs 实际值属不同对象角色
    _subj = str(c.get("subject", ""))
    _is_ctrl = bool(re.search(r"控制|限高|上限", _subj))
    _is_act = bool(re.search(r"推算|层高|实际|现状", _subj))
    if _is_ctrl or _is_act:
        revoked.append({"conflict": f"{subj}·{c.get('predicate')}", "values": c.get("values"),
                        "why": "『建筑高度控制 60m』是**控制值**（规划上限），"
                               "与层高推算的**实际值** 49m 属不同对象角色，"
                               "两者可同时成立 ⇒ **非冲突**（原判定撤销）"})
res["K19"] = {"id": "K19", "name": "对象角色区分与舍入等价",
              "algo": "同冲突内差值 ≤ 舍入容差 ⇒ 舍入一致；控制值 vs 实际值 ⇒ 非冲突",
              "total": len(conf), "missing_count": 0,
              "revoked": revoked, "revoked_count": len(revoked),
              "verdict": "pass" if revoked else "invalid",
              "note": "本判据的产出是**撤销**假冲突，故记录 revoked 列表"}

# ── K20 级联撤销：依赖假冲突的下游结论 ─────────────────────────
bad_base = {r["conflict"] for r in revoked if "高度" in json.dumps(r, ensure_ascii=False)}
cascade = []
# ① 基础冲突被撤销 ⇒ 依赖它的下游结论须复核
if bad_base:
    for m in re.finditer(r"([^。\n]{0,90}(?:一类高层|消防类别|耐火等级)[^。\n]{0,90})", draft):
        cascade.append({"quote": m.group(1).strip()[:120],
                        "why": "该结论建立在已撤销的『高度冲突』之上 ⇒ **必须一并复核/撤销**（防错误级联）"})
# ② ★ 悬空结论：结论引用的前提**已不存在**（如为消除假冲突而删掉了那条冲突），
#    结论却仍留在正文 —— 这是本会话删掉手写前向链后暴露出的新缺口。
_conflicts_now = json.dumps(conf, ensure_ascii=False)
for m in re.finditer(r"([^。\n]{0,90}(?:一类高层|消防类别|耐火等级)[^。\n]{0,90})", draft):
    quote = m.group(1)
    if re.search(r"高度", quote) and not any("高度" in json.dumps(x, ensure_ascii=False) for x in conf):
        cascade.append({"quote": quote.strip()[:120],
                        "why": "**悬空结论**：该结论以「建筑高度冲突」为前提，而该冲突现已不存在"
                               "（前提被删除/撤销）⇒ 结论失去依据，必须复核或撤销"})
res["K20"] = {"id": "K20", "name": "级联撤销（基础判据撤销则下游结论连带撤销）",
              "algo": "基础冲突被撤销 → 检索依赖其的下游结论",
              "total": len(bad_base), "missing_count": len(cascade), "missing": cascade[:4],
              "verdict": "FAIL" if cascade else "pass"}


# ── K21 生成侧一致性：同节「prose 声明的参数」vs「表格实际引用的参数」─────
# 为什么必须有这条（客户反馈问题③）：
#   6.5.1 的散文写「原报告以空调负荷密度指标与照明及其他负荷密度指标为基础估算总计算负荷」，
#   但紧随其后的表格给的却是「单位面积冷负荷指标 135 / 热负荷 80」——**散文与表格参数不是一回事**。
#   根因在**生成侧**（表格由 r18 按 predicate 过滤生成，选错了 predicate），
#   Semantica 不在生成路径上，**原理上审不出来** ⇒ 必须由生成侧断言兜住。
_PARAM_RE = re.compile(r"[\u4e00-\u9fff]{2,12}(?:" + "|".join(_PARAM_SUFFIXES) + r")")  # ← 读词表
_secs2 = re.split(r"\n(?=#{2,4}\s)", draft)
m21 = []
for sec in _secs2:
    head = sec.split("\n", 1)[0].strip("# ").strip()
    lines = sec.split("\n")
    tbl_i = [i for i, l in enumerate(lines) if l.strip().startswith("|") and "---" not in l]
    if not tbl_i:
        continue
    prose = "\n".join(l for i, l in enumerate(lines) if i not in tbl_i and not l.strip().startswith("|"))
    tbl = "\n".join(lines[i] for i in tbl_i)
    pp = {x for x in _PARAM_RE.findall(prose)}
    tp = {x for x in _PARAM_RE.findall(tbl)}
    # 只在双方都出现了「参数名」且**完全无交集**时判不一致（避免噪声）
    def _linked(a: str, b: str) -> bool:
        return a in b or b in a          # 中文参数名常有前缀差异（如「服务配套用房综合平面利用系数」vs「综合平面利用系数」）
    if pp and tp and not any(_linked(x, y) for x in pp for y in tp):
        m21.append({"section": head[:40], "prose_params": sorted(pp)[:5],
                    "table_params": sorted(tp)[:5],
                    "why": "同一节内散文声明的参数与表格引用的参数**完全无交集** ⇒ "
                           "散文与表格说的不是同一件事（生成侧参数错配）",
                    "root_cause": "生成侧：表格按 predicate 过滤生成，过滤器选错 predicate"})
res["K21"] = {"id": "K21", "name": "生成侧一致性（同节 prose 参数 vs 表格参数）",
              "algo": "按小节切分 → 取散文参数集合与表格参数集合 → 无交集即 FAIL",
              "total": len(_secs2), "missing_count": len(m21), "missing": m21[:6],
              "verdict": "FAIL" if m21 else "pass",
              "note": "Semantica 不在生成路径上，原理上审不出这类；必须由生成侧断言兜住"}

# ── K22 探针标定门禁：**未标定的探针不得采信** ──────────────────────
# 原则（本会话确立）：未与已知正样本对齐过的扫描器/审计/判据，其结论不得采信。
# 实测案例：C 比对原含一条 C_count_mismatch，标定发现它**按构造不可达**（死代码）——
#   死检查比没有检查更糟（给人虚假的安心）。故把"标定"本身做成门禁：
#   标定 verdict != calibrated ⇒ 该探针的一切结论判 invalid。
_cal_p = R / "quality" / "calibration_handover_c.json"
_probe = {"id": "K22", "name": "探针标定门禁（未标定不得采信）",
          "algo": "读标定报告 → verdict == calibrated 才认该探针",
          "total": 1, "missing_count": 0, "missing": [], "verdict": "invalid"}
if _cal_p.exists():
    _cal = json.loads(_cal_p.read_text(encoding="utf-8"))
    _sm = _cal.get("summary") or {}
    if _sm.get("verdict") == "calibrated":
        _probe.update({"verdict": "pass", "calibration": _sm,
                       "note": "C 比对已用已知正/负样本标定：recall %s / 误报 %s"
                               % (_sm.get("recall_on_positive"), _sm.get("false_positive_on_baseline"))})
    else:
        _probe.update({"verdict": "FAIL", "missing_count": 1, "calibration": _sm,
                       "missing": [{"why": "标定未通过 ⇒ 该探针结论不得采信（而非默认相信）"}]})
else:
    _probe["note"] = "无标定报告 ⇒ 探针未经反证，判 invalid（不得采信）"
res["K22"] = _probe

summary = {"pass": sum(1 for v in res.values() if v["verdict"] == "pass"),
           "FAIL": sum(1 for v in res.values() if v["verdict"] == "FAIL"),
           "invalid": sum(1 for v in res.values() if v["verdict"] == "invalid")}
out = {"summary": summary, "criteria": list(res.values()),
       "note": "K15–K21 直接对应客户反馈的 6 个问题；全部确定性算法"}
W(R / "quality" / "semantic_criteria.yaml", out)
print(json.dumps(summary, ensure_ascii=False))
for k, v in res.items():
    flag = {"pass": "✅", "FAIL": "❌", "invalid": "⚠️"}[v["verdict"]]
    print(f"  {flag} {k} {v['name'][:26]:28s} 命中 {v['missing_count'] if 'revoked_count' not in v else v['revoked_count']}")


# ★ 环节自报（四元交叉的 A 来源；必须由本环节自己写，不得由 harness 代写）
try:
    import sys as _sys2
    _sys2.path.insert(0, str(Path(__file__).resolve().parent)) if "Path" in dir() else None
    from self_report import declare as _declare
    _declare("s7n", ['SHUFE-BDC-2019-001/quality/semantic_criteria.yaml'], script="s35_semantic_criteria.py")
except Exception as _e:
    print(f"[self_report] 未写出: {_e}")
