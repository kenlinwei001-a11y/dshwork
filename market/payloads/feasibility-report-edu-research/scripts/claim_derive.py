#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
论证需求推演 + 专业取值点问询。

回答两个问题，都是「建设内容那一章为什么写成了通用条款」的根因：

  ① 这个项目该论证哪些论点？每条论点要哪几类论据？各该 ASK 还是 SEARCH？
  ② 这个子类必须写实的专业取值点有哪些？哪些还空着？

两件事都不靠垂类手写死——子类是长尾的，穷举不了，也维护不动。
它们是**推出来的**：适用维度 × 项目属性 × 子类 ⇒ 待办清单。

产物是待办清单，不是成品。它回答「还缺什么、找谁要」，
不回答「论证写好了」——后者是 WRITE，且必须基于已确认的事实。

用法:
  claim_derive.py <project.yaml> [--vertical <目录>] [--json out.json]
  claim_derive.py <project.yaml> --subtypes ST_WET_LAB,ST_PRECISION   手工指定子类
"""

import sys
import json
import argparse
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assets import guard, AssetError, REF, load_all  # noqa: E402


def _load(name):
    p = REF / name
    if not p.exists():
        raise AssetError(
            f"缺少 references/{name}\n"
            f"  它定义了论证需求怎么推、专业取值点问什么。缺了它，"
            f"「建设内容」章只能靠通用条款顶上，评审会指出套模板。")
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"第 {mark.line + 1} 行第 {mark.column + 1} 列" if mark else "位置未知"
        raise AssetError(f"L0 资产 references/{name} 解析失败（{where}）\n"
                         f"  {getattr(e, 'problem', e)}") from None


def _vertical_dir(proj, explicit):
    if explicit:
        return Path(explicit)
    vd = REF / "vertical"
    if (vd / "subtypes.yaml").exists():
        return vd
    pid = (proj.get("project") or {}).get("profile")
    if pid:
        d = REF / "verticals" / str(pid)
        if (d / "subtypes.yaml").exists():
            return d
    return None


# =============================================================================
# 子类识别
# =============================================================================

def recognize_subtypes(proj, sub_doc, forced=None):
    """返回 (命中的子类, 证据, 是否需要客户确认)。

    识别是**建议**，一律须客户确认——与垂类识别同一规格。
    识别不出来时不退回通用条款，而是把全部子类的问询取并集反问客户。
    """
    subs = (sub_doc or {}).get("subtypes") or {}
    if forced:
        hit = {k: ["人工指定"] for k in forced if k in subs}
        return hit, {}, False

    name = str((proj.get("project") or {}).get("name") or "")
    mat_names = " ".join(str(m.get("name") or "") for m in (proj.get("materials") or [])
                         if isinstance(m, dict))
    declared = set((proj.get("project") or {}).get("subtypes") or [])

    hit = {}
    for sid, spec in subs.items():
        why = []
        if sid in declared:
            why.append("项目图已声明")
        rec = spec.get("recognize") or {}
        for h in (rec.get("name_hints") or []):
            if h and h in name:
                why.append(f"项目名称含「{h}」")
        for h in (rec.get("material_hints") or []):
            if h and h in mat_names:
                why.append(f"素材名称含「{h}」")
        if why:
            hit[sid] = why
    return hit, subs, True


# =============================================================================
# 专业取值点
# =============================================================================

def collect_probes(dp_l0, sub_doc, hits):
    """通用取值点 + 命中子类的增量。多子类取并集，按 id 去重。"""
    probes = {p["id"]: dict(p, source="通用") for p in (dp_l0.get("common_probes") or [])}
    subs = (sub_doc or {}).get("subtypes") or {}
    for sid in hits:
        spec = subs.get(sid) or {}
        for p in (spec.get("probes") or []):
            probes.setdefault(p["id"], dict(p, source=(spec.get("cn") or sid)))
    return probes


def probe_status(probes, proj):
    """取值点是否已落地。三种合格状态，其余算空着。"""
    nodes = proj.get("nodes") or {}
    confirmed = set((proj.get("project") or {}).get("probes_confirmed_na") or [])
    answered = set((proj.get("probes_answered") or {}).keys())
    out = []
    for pid, p in probes.items():
        if pid in confirmed:
            st = "confirmed_na"          # 客户明确确认"不涉及"——也是有效输入
        elif pid in answered or pid in nodes:
            st = "satisfied"
        else:
            st = "missing"
        out.append(dict(p, id=pid, status=st))
    order = {"missing": 0, "confirmed_na": 1, "satisfied": 2}
    out.sort(key=lambda x: (order[x["status"]], x.get("discipline", ""), x["id"]))
    return out


# =============================================================================
# 论证需求推演
# =============================================================================

def _applicable_dims(argu, proj):
    dims = (argu.get("feasibility_frame") or {}).get("dimensions") or {}
    ctx = proj.get("project") or {}
    na = set(proj.get("not_applicable") or {})
    out = []
    for d, spec in dims.items():
        expr = (spec.get("applicable_when") or "always").strip()
        ok = True
        if expr != "always":
            neg = expr.startswith("not ")
            key = (expr[4:] if neg else expr).split(".")[-1].strip()
            val = bool(ctx.get(key, False))
            ok = (not val) if neg else val
        if ok:
            out.append((d, spec.get("cn", d), d in na))
    return out


def _match_rule(when, proj):
    ctx = proj.get("project") or {}
    w = str(when).strip()
    if "==" in w:
        left, right = [x.strip() for x in w.split("==", 1)]
        key = left.split(".")[-1]
        right = right.strip().strip("\"'")
        cur = ctx.get(key)
        if isinstance(cur, bool):
            return cur == (right.lower() == "true")
        return str(cur).strip() == right
    return False


def derive_claims(cd_l0, argu, proj, sub_doc, hits):
    """推出论点清单，每条带论据槽与路由。"""
    dg = cd_l0.get("dimension_grounds") or {}
    gp = cd_l0.get("grounds_patterns") or {}
    existing = proj.get("claims") or {}
    served = {}
    for cid, c in existing.items():
        for d in ((c or {}).get("serves") or []):
            served.setdefault(d, []).append(cid)

    items = []
    for d, cn, is_na in _applicable_dims(argu, proj):
        if is_na:
            continue
        spec = dg.get(d) or {}
        req = spec.get("required") or []
        have = served.get(d) or []
        # 已有论点里，哪些论据模式已经落地
        got = set()
        for cid in have:
            arg = (existing.get(cid) or {}).get("argument") or {}
            got |= set(arg.get("grounds_patterns") or [])
        missing = [g for g in req if g not in got]
        items.append({
            "dimension": d, "dimension_cn": cn,
            "has_claim": bool(have), "claims": have,
            "required_grounds": req,
            "missing_grounds": [{"pattern": g, "cn": (gp.get(g) or {}).get("cn", g),
                                 "route": (gp.get(g) or {}).get("route", "ASK"),
                                 "trap": (gp.get(g) or {}).get("trap")}
                                for g in missing],
            "source": "builtin",
        })

    # 规则触发的追加论点
    extra = []
    for r in (cd_l0.get("derivation_rules") or []):
        if r.get("when") and _match_rule(r["when"], proj):
            extra.append({"rule": r["id"], "effect": r.get("effect"),
                          "grounds": r.get("grounds") or [], "note": r.get("note"),
                          "source": "derived_by_rule"})

    # 垂类与子类的额外论点
    for c in ((sub_doc or {}).get("vertical_extra_claims") or []):
        extra.append(dict(c, source="vertical"))
    subs = (sub_doc or {}).get("subtypes") or {}
    for sid in hits:
        for c in ((subs.get(sid) or {}).get("extra_claims") or []):
            extra.append(dict(c, source=f"subtype:{subs[sid].get('cn', sid)}"))

    items.sort(key=lambda x: (x["has_claim"], -len(x["missing_grounds"])))
    return items, extra


def section_prompt(sec_key):
    """取某章的起草提示。每章是不同的活，提示词就该不同。"""
    f = REF / "section-prompts.yaml"
    if not f.exists():
        return None
    doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    spec = (doc.get("sections") or {}).get(sec_key)
    if not spec:
        return None
    return {"common": doc.get("common") or {}, "section": spec}


def render_prompt(sec_key, p):
    if not p:
        return f"未定义章节 {sec_key} 的起草提示。可用：见 references/section-prompts.yaml"
    sp, cm = p["section"], p["common"]
    L = ["=" * 74, f"起草提示 · {sp.get('cn')}", "=" * 74, ""]
    L.append(f"这一章要回答的：{sp.get('focus')}")
    sl = sp.get("slice") or {}
    L.append(f"切片：服务 {sl.get('serves')}　产出 {sl.get('provides') or '（不产出，只复述与论证）'}")
    L.append(f"形态：{sp.get('shape')}")
    L.append("")
    for key, title in (("prepare", "起草前必须先完成（没做完就不要动笔）"),
                       ("must_state", "必须写到"),
                       ("must_not", "这一章特有的坑")):
        items = sp.get(key) or []
        if not items:
            continue
        L.append(f"【{title}】")
        for it in items:
            L.append("  · " + " ".join(str(it).split()))
        L.append("")
    if sp.get("review"):
        L.append(f"【评审盯什么】{sp['review']}")
        L.append("")
    L.append("【通用约束（每章都适用）】")
    for it in (cm.get("hard") or []):
        L.append("  · " + str(it))
    for it in (cm.get("style") or []):
        L.append("  - " + str(it))
    if cm.get("self_check"):
        L.append("  自检：" + str(cm["self_check"]))
    return "\n".join(L)


# =============================================================================
# 报告
# =============================================================================

def report(hits, subs, need_confirm, probes, claims, extra, dp_l0, vname):
    L = ["=" * 74, f"论证需求推演与专业取值点{'（' + vname + '）' if vname else ''}", "=" * 74, ""]

    L.append("-" * 74)
    L.append("一、子类识别")
    L.append("-" * 74)
    if hits:
        for sid, why in hits.items():
            cn = (subs.get(sid) or {}).get("cn", sid) if subs else sid
            L.append(f"  · {cn}（{sid}）—— 线索：{'；'.join(why)}")
        if need_confirm:
            L.append("")
            L.append("  ⚠ 识别结果是**建议**，须客户确认。多子类可并存，取并集。")
    else:
        L.append("  ✗ 未识别出子类。")
        L.append("    **不退回通用条款。** 正确处置是把本垂类全部子类的取值点取并集，")
        L.append("    按专业分组反过来问客户：「本项目是否涉及以下条件？」")
        L.append("    客户答「都不涉及」也是有效输入——它把通用条款从偷懒的默认")
        L.append("    变成有依据的选择。这个区别评审看得出来。")
    L.append("")

    miss = [p for p in probes if p["status"] == "missing"]
    L.append("-" * 74)
    L.append(f"二、专业取值点（{len(probes)} 项，空着 {len(miss)} 项）")
    L.append("-" * 74)
    if miss:
        # 按 resolution 分组，而不是按专业分组。
        # 可研阶段的设计是方案深度：规范查表加算术能定的，agent 自己做；
        # 只有方案比选与设计单位专属的才需要外部输入。
        # 混成一句「去问客户」，会把该自己算的推给客户，也会让该设计单位定的被编掉。
        GROUP = [
            ("norm_lookup", "① 我来做 · 规范判定", "查规范定出，结论必须带条款依据"),
            ("computed",    "② 我来做 · 参数推导", "由上一层算出，不许手填"),
            ("mixed",       "③ 分层处理", "一个取值点跨多层，见 resolve_by"),
            ("choice",      "④ 我给候选 · 您来定", "有多个合规解，选哪个是决策不是计算"),
            ("design_only", "⑤ 必须设计单位提供", "推不出来，只能要；要不到就留白"),
            ("ask",         "⑥ 必须您提供", "客户的口径或使用要求，无从推导"),
        ]
        disc = dp_l0.get("disciplines") or {}
        for key, title, note in GROUP:
            items = [p for p in miss if (p.get("resolution") or "ask") == key]
            if not items:
                continue
            L.append(f"  {title}（{len(items)} 项）—— {note}")
            for p in items:
                d = (disc.get(p.get("discipline", "")) or {}).get("cn", p.get("discipline", ""))
                L.append(f"      · [{d}] {p.get('cn')}　来源：{p.get('source')}")
                if p.get("resolve_by"):
                    L.append(f"          怎么定：{' '.join(str(p['resolve_by']).split())}")
                if key in ("ask", "choice", "design_only", "mixed"):
                    L.append(f"          问：{p.get('ask')}")
                if p.get("must_cite"):
                    L.append(f"          ⚠ {p['must_cite']}")
                if p.get("if_missing"):
                    L.append(f"          缺了会怎样：{p['if_missing']}")
            L.append("")
        need_out = [p for p in miss
                    if (p.get("resolution") or "ask") in ("ask", "choice", "design_only")]
        L.append(f"  合计 {len(miss)} 项空着，其中 {len(miss) - len(need_out)} 项我可以自己完成，"
                 f"{len(need_out)} 项需要您或设计单位提供。")
        L.append("  取值点空着时，「建设内容」章写出来一定是通用条款——")
        L.append("  评审追问的从来不是「有没有通风系统」，而是「换气次数取几次」。")
    else:
        L.append("  ✓ 全部取值点已取到或已由客户确认不涉及")
    L.append("")

    L.append("-" * 74)
    L.append("三、论证需求")
    L.append("-" * 74)
    nostart = [c for c in claims if not c["has_claim"]]
    if nostart:
        L.append(f"  ✗ {len(nostart)} 个适用维度还没有任何论点：")
        for c in nostart:
            L.append(f"      {c['dimension']} {c['dimension_cn']}")
        L.append("     依赖这些维度的章节不得起草（C13 / CD8）。")
        L.append("")
    for c in claims:
        if not c["missing_grounds"]:
            continue
        L.append(f"  {c['dimension']} {c['dimension_cn']}  缺 {len(c['missing_grounds'])} 类论据")
        for g in c["missing_grounds"]:
            L.append(f"      · {g['cn']}（{g['pattern']}）→ {g['route']}")
            if g.get("trap"):
                L.append(f"          注意：{' '.join(str(g['trap']).split())[:110]}")
        L.append("")

    if extra:
        L.append("-" * 74)
        L.append(f"四、追加论点（{len(extra)} 条）")
        L.append("-" * 74)
        for e in extra:
            head = e.get("about") or e.get("effect") or e.get("id")
            L.append(f"  · [{e.get('source')}] {head}")
            if e.get("serves"):
                L.append(f"      服务维度：{e['serves']}    论据：{e.get('grounds') or []}")
            if e.get("warrant_hint"):
                L.append(f"      保证怎么写：{' '.join(str(e['warrant_hint']).split())[:150]}")
            elif e.get("note"):
                L.append(f"      说明：{' '.join(str(e['note']).split())[:150]}")
        L.append("")

    L.append("-" * 74)
    L.append("下一步")
    L.append("-" * 74)
    L.append("  ASK 项并入 intake_gen.py 的提问队列，按阻塞度降序，每批不超过 5 问。")
    L.append("  SEARCH 项批量前置检索，结果须过 fit_rank.py 排序后交客户勾选。")
    L.append("  取值点全部落地之前，「建设内容」章不要起草——写出来也是通用条款。")
    return "\n".join(L)


@guard
def main(argv):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("project")
    ap.add_argument("--vertical")
    ap.add_argument("--subtypes", help="逗号分隔，手工指定子类，跳过识别")
    ap.add_argument("--json")
    ap.add_argument("--prompt", help="输出某章的起草提示（如 technical / scale / background）")
    a = ap.parse_args(argv[1:])

    if a.prompt:
        print(render_prompt(a.prompt, section_prompt(a.prompt)))
        return 0

    dp_l0 = _load("discipline-probes.yaml")
    cd_l0 = _load("claim-derivation.yaml")
    _core, argu, _deriv, _norms = load_all()
    proj = yaml.safe_load(Path(a.project).read_text(encoding="utf-8"))

    vd = _vertical_dir(proj, a.vertical)
    sub_doc = yaml.safe_load((vd / "subtypes.yaml").read_text(encoding="utf-8")) if vd else {}
    vname = (sub_doc or {}).get("vertical") or (vd.name if vd else "")

    forced = [x.strip() for x in a.subtypes.split(",")] if a.subtypes else None
    hits, subs, need_confirm = recognize_subtypes(proj, sub_doc, forced)
    if not hits and sub_doc:
        # 兜底：全部子类的取值点取并集反问客户
        hits = {k: ["未识别，按兜底取并集"] for k in (sub_doc.get("subtypes") or {})}
        subs = sub_doc.get("subtypes") or {}
        probes = probe_status(collect_probes(dp_l0, sub_doc, hits), proj)
        hits = {}
    else:
        probes = probe_status(collect_probes(dp_l0, sub_doc, hits), proj)
    claims, extra = derive_claims(cd_l0, argu, proj, sub_doc, hits)

    print(report(hits, subs or (sub_doc.get("subtypes") or {}), need_confirm,
                 probes, claims, extra, dp_l0, vname))
    if a.json:
        Path(a.json).write_text(json.dumps(
            {"subtypes": hits, "probes": probes, "claims": claims, "extra_claims": extra},
            ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n已写出 {a.json}")
    return 1 if ([p for p in probes if p["status"] == "missing"]
                 or [c for c in claims if not c["has_claim"]]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
