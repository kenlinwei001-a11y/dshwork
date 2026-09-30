#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外部证据适配性评估与排序。

SEARCH 捞回来的政策/法规/标准不能直接入图——一条管不着本项目的地方规定
写进"政策符合性"，评审一眼看穿，整章的可信度一起塌。

本脚本做三件事：
  ① 硬否决（地域不覆盖 / 类别不覆盖 / 主体不适用 / 已废止）—— 出局但留痕
  ② 六维打分并排序（规则见 references/external-fit.yaml）
  ③ 输出一张**给客户勾选**的候选表

它不采纳任何一条。采纳是客户的动作，脚本只负责把选择题出好。

用法:
  fit_rank.py <project.yaml> <candidates.yaml> [--json out.json] [--top 6]

candidates.yaml 格式（每条一个映射）：
  candidates:
    - id: C1
      title: 某某配建规定
      doc_no: 某发〔2021〕31号
      issuer: 某省人防办
      authority: 地方规范性文件        # 见 external-fit.yaml F5
      status: 现行有效                  # 现行有效 / 已废止 / 被替代 / 未查证
      verified_at: 2026-07-05          # 缺省视为未核验
      jurisdiction: [某省]              # 效力地域；全国性文件写 [全国]
      applies_to: [公共设施用地建设项目] # 适用对象
      subjects: [政府投资]              # 适用的投资主体；不限则写 [不限]
      clause: 第X条                     # 有具体条款则填
      quantified: true                  # 条款是否含量化要求
      proposed_role: [benchmark, domain]
      mandatory: false                  # 是否强制适用
"""

import sys
import json
import argparse
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assets import guard, AssetError, REF  # noqa: E402

WEIGHTS = {"F1": 0.20, "F2": 0.25, "F3": 0.10, "F4": 0.15, "F5": 0.15, "F6": 0.15}

AUTHORITY_SCORE = {
    "法律": 3, "行政法规": 3, "部门规章": 3, "强制性国家标准": 3, "强制性标准": 3,
    "国务院规范性文件": 2, "部委规范性文件": 2, "规范性文件": 2,
    "推荐性标准": 1, "地方规范性文件": 1, "行业协会文件": 1, "标准": 1,
    "指南": 0, "白皮书": 0, "研究报告": 0, "新闻稿": 0,
}

NATIONWIDE = {"全国", "国家", "中华人民共和国"}


def _load_fit_spec():
    p = REF / "external-fit.yaml"
    if not p.exists():
        raise AssetError(
            "缺少 references/external-fit.yaml —— 外部证据的适配性规则在这个文件里。\n"
            "  缺了它，排序的口径无据可依，等于让 agent 自己拍脑袋选政策。")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


# =============================================================================
# 硬否决
# =============================================================================

def _covers(scope, target):
    """scope 列表是否覆盖 target（字符串包含即算覆盖，支持省覆盖市的写法）。"""
    if not scope:
        return None  # 未声明，无法判定
    if any(s in NATIONWIDE for s in scope):
        return True
    if not target:
        return None
    return any(s and (s in target or target in s) for s in scope)


def veto_check(c, proj):
    """返回 (否决码, 说明) 或 (None, None)。"""
    status = str(c.get("status", "未查证"))
    if any(k in status for k in ("废止", "被替代", "失效", "到期")):
        if not c.get("historical_reference"):
            return "V1_repealed", f"现行状态为「{status}」"

    loc = (proj.get("project") or {}).get("location") or proj.get("location")
    cov = _covers(c.get("jurisdiction"), loc)
    if cov is False:
        return "V2_jurisdiction_miss", f"效力地域 {c.get('jurisdiction')} 不含项目所在地「{loc}」"
    if cov is None and c.get("jurisdiction") and not loc:
        return None, None  # 项目所在地未知，留给 C10b 报，不在此处否决

    cat = c.get("applies_to")
    ptype = (proj.get("project") or {}).get("category") or (proj.get("project") or {}).get("profile")
    if cat and ptype and c.get("category_verified") is False:
        return "V3_category_miss", f"适用对象 {cat} 不含本项目类别「{ptype}」"

    subs = c.get("subjects") or []
    regime = (proj.get("project") or {}).get("funding_regime")
    if subs and "不限" not in subs and regime and regime not in subs:
        return "V4_subject_miss", f"仅适用于 {subs}，本项目为「{regime}」"
    return None, None


# =============================================================================
# 六维打分
# =============================================================================

def score(c, proj):
    loc = (proj.get("project") or {}).get("location") or proj.get("location") or ""
    juris = c.get("jurisdiction") or []

    # F1 地域
    if any(j in NATIONWIDE for j in juris):
        f1 = 2 if loc else 2
    elif loc and any(j and j in loc and j != loc for j in juris):
        f1 = 2                      # 上位（省级）覆盖
    elif loc and any(j == loc for j in juris):
        f1 = 3                      # 同级直接对应
    elif juris:
        f1 = 2
    else:
        f1 = 1

    # F2 类别
    f2 = int(c.get("category_fit", 2))

    # F3 主体
    subs = c.get("subjects") or []
    regime = (proj.get("project") or {}).get("funding_regime")
    nature = (proj.get("project") or {}).get("nature")
    if regime and regime in subs and nature and c.get("nature_matched"):
        f3 = 3
    elif regime and regime in subs:
        f3 = 2
    elif "不限" in subs or not subs:
        f3 = 1
    else:
        f3 = 0

    # F4 时效
    status = str(c.get("status", "未查证"))
    as_of = proj.get("as_of")
    if "现行" in status and c.get("verified_at"):
        fresh = True
        try:
            d0 = c["verified_at"]
            d1 = as_of
            if hasattr(d0, "toordinal") and hasattr(d1, "toordinal"):
                fresh = (d1.toordinal() - d0.toordinal()) <= 90
        except Exception:
            fresh = True
        f4 = 3 if fresh else 2
    elif "现行" in status:
        f4 = 2
    elif "未查证" in status:
        f4 = 1
    else:
        f4 = 0

    # F5 效力层级
    f5 = AUTHORITY_SCORE.get(str(c.get("authority", "")).strip(), 1)

    # F6 条款针对性
    if c.get("clause") and c.get("quantified"):
        f6 = 3
    elif c.get("clause"):
        f6 = 2
    elif c.get("principle_only"):
        f6 = 1
    else:
        f6 = 1

    dims = {"F1": f1, "F2": f2, "F3": f3, "F4": f4, "F5": f5, "F6": f6}
    total = round(sum(dims[k] * WEIGHTS[k] for k in dims), 3)
    return dims, total


def bucket(dims, total, c):
    if c.get("mandatory"):
        return "mandatory", True
    if total >= 2.2 and dims["F2"] >= 2 and dims["F6"] >= 2:
        return "recommended", True
    if total >= 1.5:
        return "optional", False
    return "background", False


BUCKET_CN = {"mandatory": "强制适用（默认勾选，仍须确认）",
             "recommended": "建议采纳", "optional": "备选", "background": "仅作背景"}
BUCKET_ORDER = {"mandatory": 0, "recommended": 1, "optional": 2, "background": 3}


def why(dims, total):
    hi = max(dims, key=lambda k: dims[k])
    lo = min(dims, key=lambda k: dims[k])
    CN = {"F1": "地域", "F2": "类别", "F3": "主体", "F4": "时效", "F5": "效力层级", "F6": "条款针对性"}
    return f"{CN[hi]}拉高（{dims[hi]}/3）、{CN[lo]}拉低（{dims[lo]}/3）"



# =============================================================================
# 数值候选 —— ASK 回退检索
# =============================================================================
# 政策候选问的是「这条规定管不管本项目」；
# 数值候选问的是「这个数和本项目的那个量，说的是不是同一件事」。
# 后者的头号杀手是统计口径：口径对不上，报告读起来完全正常，
# 只有算到后面才发现哪里不对——而那时已经写完三章了。
# =============================================================================

VWEIGHTS = {"N1": 0.30, "N2": 0.25, "N3": 0.15, "N4": 0.15, "N5": 0.10, "N6": 0.05}

VAUTHORITY = {
    "强制性标准": 3, "国家标准": 3, "部委发布": 3, "地方主管部门": 3, "地方发布": 3,
    "推荐性标准": 2, "行业协会": 2, "统计公报": 2,
    "设计院研究": 1, "咨询机构研究": 1,
    "媒体报道": 0, "二手转述": 0,
}
VTYPE = {"约束值": 3, "限额": 3, "引导值": 2, "目标值": 2, "平均值": 1, "统计平均值": 1}


def score_value(c, proj):
    """数值候选打分。字段缺省时取保守值——宁可排低，不要排高。"""
    dims = {
        "N1": int(c.get("metric_definition_fit", 1)),
        "N2": int(c.get("object_fit", 1)),
        "N3": int(c.get("geography_fit", 1)),
        "N4": int(c.get("vintage_fit", 1)),
        "N5": VAUTHORITY.get(str(c.get("authority", "")).strip(), 1),
        "N6": VTYPE.get(str(c.get("value_type", "")).strip(), 0),
    }
    total = round(sum(dims[k] * VWEIGHTS[k] for k in dims), 3)
    return dims, total


def rank_values(proj, cands):
    """返回 (排序后的候选, 被剔除的)。

    N5 == 0（媒体报道/二手转述）直接剔除：出处都追不到的数字，
    呈给客户等于把核实责任推给他。
    """
    kept, dropped = [], []
    for c in cands:
        dims, total = score_value(c, proj)
        if dims["N5"] == 0:
            dropped.append({"id": c.get("id"), "title": c.get("source_doc") or c.get("title"),
                            "veto": "N5_untraceable",
                            "reason": "二手转述或媒体报道，出处追不到——不作为候选呈报"})
            continue
        if total >= 2.2 and dims["N1"] >= 2:
            bucket = "recommended"
        elif total >= 1.5:
            bucket = "optional"
        else:
            bucket = "reference_only"
        kept.append({
            "id": c.get("id"), "value": c.get("value"), "unit": c.get("unit"),
            "title": c.get("source_doc") or c.get("title"),
            "issuer": c.get("issuer"), "published": c.get("published"),
            "clause": c.get("clause") or "未注明条款",
            "metric_definition": c.get("metric_definition") or "**发布方未写明口径——须先问清楚**",
            "value_type": c.get("value_type") or "性质不明",
            "provenance_after": c.get("provenance_after") or "E3_external",
            "dims": dims, "total": total, "bucket": bucket,
            "default_checked": False,          # 数值候选一律不默认勾选
            "why": vwhy(dims),
        })
    kept.sort(key=lambda x: (-x["total"], -x["dims"]["N1"], -x["dims"]["N5"]))
    return kept, dropped


VCN = {"N1": "口径", "N2": "对象", "N3": "地域气候区", "N4": "年份",
       "N5": "发布机构", "N6": "值的性质"}


def vwhy(dims):
    hi = max(dims, key=lambda k: dims[k])
    lo = min(dims, key=lambda k: dims[k])
    return f"{VCN[hi]}拉高（{dims[hi]}/3）、{VCN[lo]}拉低（{dims[lo]}/3）"


VBUCKET_CN = {"recommended": "可作参照值", "optional": "备选", "reference_only": "仅供参考"}


def report_values(kept, dropped, proj, slot=None, query=None):
    L = ["=" * 74, "数值候选 —— 请客户选一个作为参照值", "=" * 74]
    if slot:
        L.append(f"槽位：{slot}")
    loc = (proj.get("project") or {}).get("location") or "（未提供）"
    L.append(f"项目所在地：{loc}")
    if query:
        L.append(f"检索式：{query}")
    L.append("")
    L.append("⚠ 这些是**别处发布的值，不是本项目的实测值**。选中后：")
    L.append("   · 按真实来源标 E2/E3/E5，**不标 E1_given**——标 E1 等于宣称这是本项目的数")
    L.append("   · 标 is_placeholder: true，并写明何时必须替换成实定值")
    L.append("   · 正文写成「参照某发布值，待核定」，不能写成本项目的实定值")
    L.append("")

    if not kept:
        L.append("没有可呈报的候选。")
        L.append("检不到就说检不到——不许用一个「沾边」的值顶上。该槽位走 WITHHOLD，")
        L.append("正文留白并写明待补。")
    for i, k in enumerate(kept, 1):
        L.append(f"[ ] {i}. {k['value']} {k['unit'] or ''}    结论：{VBUCKET_CN[k['bucket']]}")
        L.append(f"      出处：{k['title'] or '—'}  {k['issuer'] or ''}  {k['published'] or ''}"
                 f"  {k['clause']}")
        L.append(f"      统计口径：{k['metric_definition']}")
        L.append(f"      值的性质：{k['value_type']}    入图后标：{k['provenance_after']} + is_placeholder")
        d = k["dims"]
        L.append(f"      适配性 {k['total']}    口径 {d['N1']} · 对象 {d['N2']} · 地域 {d['N3']}"
                 f" · 年份 {d['N4']} · 机构 {d['N5']} · 性质 {d['N6']}")
        L.append(f"      为什么在这个位置：{k['why']}")
        if d["N1"] <= 1:
            L.append("      ⚠ 口径存疑。口径对不上时报告读起来完全正常，错误要到很后面才暴露——")
            L.append("        采用前必须问清楚：分母是什么、边界含不含哪些部分、是限额还是平均值")
        L.append("")

    if dropped:
        L.append("-" * 74)
        L.append(f"已剔除（{len(dropped)} 条）—— 留痕备查")
        L.append("-" * 74)
        for d in dropped:
            L.append(f"  × {d['title']}  [{d['veto']}] {d['reason']}")
        L.append("")

    L.append("[ ] 以上都不合适")
    L.append("[ ] 我方另有取值（请提供数值与出处）")
    L.append("")
    L.append("-" * 74)
    L.append("这两个出口是必须留的。只给候选不给出口，客户会随便选一个，")
    L.append("然后这个数会一路写进报告。")
    return "\n".join(L)

# =============================================================================
# 主流程
# =============================================================================

def rank(proj, cands, top=6):
    kept, dropped = [], []
    for c in cands:
        code, msg = veto_check(c, proj)
        if code:
            dropped.append({"id": c.get("id"), "title": c.get("title"), "veto": code, "reason": msg})
            continue
        dims, total = score(c, proj)
        b, checked = bucket(dims, total, c)
        kept.append({"id": c.get("id"), "title": c.get("title"), "doc_no": c.get("doc_no"),
                     "issuer": c.get("issuer"), "authority": c.get("authority"),
                     "status": c.get("status"), "verified_at": str(c.get("verified_at") or "未核验"),
                     "clause": c.get("clause") or "无具体条款",
                     "proposed_role": c.get("proposed_role") or [],
                     "dims": dims, "total": total, "bucket": b,
                     "default_checked": checked, "why": why(dims, total)})
    kept.sort(key=lambda x: (BUCKET_ORDER[x["bucket"]], -x["total"], -x["dims"]["F5"], -x["dims"]["F4"]))
    over = max(0, len(kept) - top)
    return kept[:top], dropped, over


def report(kept, dropped, over, proj, query=None):
    L = []
    L.append("=" * 74)
    L.append("外部证据适配性排序 —— 请勾选采纳项")
    L.append("=" * 74)
    loc = (proj.get("project") or {}).get("location") or "（未提供，F1/V2 无法判定）"
    regime = (proj.get("project") or {}).get("funding_regime") or "（未提供）"
    L.append(f"项目所在地：{loc}    投资主体：{regime}")
    if query:
        L.append(f"检索式：{query}")
    L.append("")

    if not kept:
        L.append("没有候选进入排序表。")
        L.append("这意味着**该事项暂无可引的外部依据**——不要用背景类文件凑数。")
        L.append("正确处置：告知客户未检索到可引依据，并问客户手上有没有")
        L.append("（地方内部文件、主管部门口头口径常常检索不到）。")
    for i, k in enumerate(kept, 1):
        mark = "[✓]" if k["default_checked"] else "[ ]"
        L.append(f"{mark} {i}. {k['title']}  {k['doc_no'] or ''}")
        L.append(f"      发文/层级：{k['issuer'] or '—'} / {k['authority'] or '—'}"
                 f"    状态：{k['status']}（核验 {k['verified_at']}）")
        d = k["dims"]
        L.append(f"      适配性 {k['total']}    地域 {d['F1']} · 类别 {d['F2']} · 主体 {d['F3']}"
                 f" · 时效 {d['F4']} · 层级 {d['F5']} · 针对性 {d['F6']}")
        L.append(f"      可引条款：{k['clause']}")
        L.append(f"      拟担角色：{'、'.join(k['proposed_role']) or '待定'}"
                 f"    结论：{BUCKET_CN[k['bucket']]}")
        L.append(f"      为什么在这个位置：{k['why']}")
        if k["bucket"] == "background":
            L.append("      ⚠ 仅可写进综述性文字，不得作为某条论断的 warrant 或 backing")
        L.append("")

    if dropped:
        L.append("-" * 74)
        L.append(f"硬否决（{len(dropped)} 条）—— 已检索并判断，留痕备查")
        L.append("-" * 74)
        for d in dropped:
            L.append(f"  × {d['title']}  [{d['veto']}] {d['reason']}")
        L.append("")

    if over:
        L.append(f"⚠ 另有 {over} 条候选未呈报（每题上限 6 条）。")
        L.append("  超限说明检索式不够聚焦，建议收敛检索分面后重跑，而不是让客户在长表里挑。")
        L.append("")

    L.append("-" * 74)
    L.append("下一步")
    L.append("-" * 74)
    L.append("  客户勾选后，把选中项写入 project.yaml 的 evidence 段（含 fit 分值、")
    L.append("  adopted_by、adopted_at），未选中项写入 screened_evidence 段。")
    L.append("  两边都要写——没有留痕，看起来就像是没检索到。")
    return "\n".join(L)


@guard
def main(argv):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("project")
    ap.add_argument("candidates")
    ap.add_argument("--json")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--mode", choices=["policy", "value"], default="policy",
                    help="policy=政策法规候选（默认）；value=数值候选（ASK 回退检索）")
    a = ap.parse_args(argv[1:])

    spec = _load_fit_spec()
    proj = yaml.safe_load(Path(a.project).read_text(encoding="utf-8"))
    doc = yaml.safe_load(Path(a.candidates).read_text(encoding="utf-8")) or {}
    cands = doc.get("candidates") or []
    if not cands:
        print("candidates.yaml 里没有 candidates 段，或为空。")
        return 2

    if a.mode == "value":
        if not spec.get("value_fit_dimensions"):
            raise AssetError(
                "references/external-fit.yaml 缺 value_fit_dimensions 段。\n"
                "  数值候选与政策候选的评分维度不同，缺了它排序口径无据可依。")
        kept, dropped = rank_values(proj, cands)
        print(report_values(kept, dropped, proj, doc.get("slot"), doc.get("query")))
        if a.json:
            Path(a.json).write_text(json.dumps(
                {"ranked": kept, "dropped": dropped}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            print(f"\n已写出 {a.json}")
        return 0

    kept, dropped, over = rank(proj, cands, a.top)
    print(report(kept, dropped, over, proj, doc.get("query")))
    if a.json:
        Path(a.json).write_text(json.dumps(
            {"ranked": kept, "vetoed": dropped, "overflow": over},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写出 {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
