#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材摄入扫描 —— 客户交来一堆材料，先算清楚"够不够、缺的归谁管"。

真实工作形态是：客户丢过来设计方案、造价书、批复、台账，说"照这些写"。
材料永远不齐。缺的那部分若被顺手编出来，报告读起来最通顺，
却在评审环节爆掉，而且编造的痕迹已被抹平，没人能倒查。

本脚本在动笔之前把缺口摊开，并按**来源路由**分成四份责任清单：

  ASK      只有客户有 → 追料/追问（含追料话术与可接受的替代物）
  SEARCH   公开可查   → agent 自己去查，不占客户时间
  COMPUTE  可派生     → 不许问也不许填，等输入齐了自动算
  WRITE    可起草     → agent 起草
  WITHHOLD 都不成立   → 留白，写明待补

路由规则见 references/provenance-routing.yaml，
素材分类与追料话术见 references/materials.yaml。

用法:
  intake_scan.py <project.yaml> [--vertical <垂类目录>] [--json out.json]
"""

import sys
import json
import argparse
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assets import guard, AssetError, REF, ROOT  # noqa: E402
from schema import _refs_in_formula  # noqa: E402


def _load(name, required=True):
    p = REF / name
    if not p.exists():
        if not required:
            return {}
        raise AssetError(
            f"缺少 references/{name}\n"
            f"  它规定了素材怎么归类、缺了找谁要。缺这个文件，"
            f"缺口清单会退化成一句「资料不全」，客户无从补起。")
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"第 {mark.line + 1} 行第 {mark.column + 1} 列" if mark else "位置未知"
        raise AssetError(
            f"L0 资产 references/{name} 解析失败（{where}）\n"
            f"  {getattr(e, 'problem', e)}\n"
            f"  常见原因：流式映射 {{}} 里写了块标量 |、中文引号未配对、缩进不一致。") from None


def _vertical_dir(proj, explicit):
    if explicit:
        return Path(explicit)
    vd = REF / "vertical"                     # 生成品布局
    if (vd / "materials.yaml").exists():
        return vd
    pid = (proj.get("project") or {}).get("profile")
    if pid:
        d = REF / "verticals" / str(pid)      # base 布局
        if (d / "materials.yaml").exists():
            return d
    return None


# =============================================================================
# 素材覆盖
# =============================================================================

def _required(spec, proj):
    """required: true 直给；required_when: 表达式则按项目属性求值。

    拆除重建项目的施工与实施类素材是必须的，新建项目则可延后——
    同一个素材类在不同项目里阻塞性不同，写死会误报也会漏报。
    """
    ctx = proj.get("project") or {}
    # 先看豁免，再看 required —— 顺序反了，required: true 会直接短路掉豁免判断。
    # required_when_not: "not project.physical" —— 该条件成立时**免除**强制。
    # 纯软件/纯服务项目没有用地也没有建筑设计，硬要它交这两类材料是误报。
    neg = spec.get("required_when_not")
    if neg:
        expr = str(neg).strip()
        negated = expr.startswith("not ")
        key = (expr[4:] if negated else expr).split(".")[-1].strip()
        val = bool(ctx.get(key, True))
        exempt = (not val) if negated else val
        if exempt:
            return False
    if spec.get("required"):
        return True
    expr = spec.get("required_when")
    if not expr:
        return False
    if "==" in str(expr):
        left, right = [x.strip() for x in str(expr).split("==", 1)]
        key = left.split(".")[-1]
        return str(ctx.get(key, "")).strip() == right.strip().strip("\"'")
    return False


def scan_materials(proj, mat_l0, vert):
    """返回 (已登记, 缺失, 未归类, 用的哪套要求)。

    没有匹配垂类时退回 L0 的缺省必备素材集，**不退化为"什么都不要求"**——
    后者会报"缺素材：无"，读起来像资料齐了，比不检查更危险。
    """
    classes = mat_l0.get("material_classes") or {}
    registered = [m for m in (proj.get("materials") or []) if isinstance(m, dict)]
    have = {}
    unclassified = []
    for m in registered:
        cls = m.get("class")
        if not cls or cls not in classes:
            unclassified.append(m)
            continue
        have.setdefault(cls, []).append(m)

    req = (vert or {}).get("required_materials") or {}
    source = "垂类要求"
    if not req:
        req = {k: v for k, v in (mat_l0.get("default_required_materials") or {}).items()
               if isinstance(v, dict)}
        source = "L0 缺省必备集（未匹配到垂类，这是下限不是清单）"
    missing = []
    for cls, spec in req.items():
        if cls in have:
            continue
        base = classes.get(cls) or {}
        im = base.get("if_missing") or {}
        missing.append({
            "class": cls,
            "cn": base.get("cn", cls),
            "required": _required(spec, proj),
            "provider": base.get("provider", "建设单位"),
            "ask": spec.get("ask") or im.get("ask") or f"请提供{base.get('cn', cls)}相关材料",
            "consequence": spec.get("consequence") or im.get("consequence") or "相关章节无法起草",
            "blocking": base.get("blocking", "-"),
            "substitutes": [s.get("what") for s in (base.get("substitutes") or [])],
        })
    missing.sort(key=lambda x: (not x["required"], x["class"]))
    return have, missing, unclassified, source


# =============================================================================
# 取值可溯源
# =============================================================================

def scan_traceability(proj):
    """返回 (坏 from 列表, 无 from 的 E1/E6 节点列表)。"""
    reg = {m.get("id") for m in (proj.get("materials") or []) if isinstance(m, dict)}
    bad, unsourced = [], []
    has_registry = bool(proj.get("materials"))
    for nid, n in (proj.get("nodes") or {}).items():
        if not isinstance(n, dict):
            continue
        pv = n.get("provenance")
        fr = n.get("from")
        if fr:
            if not isinstance(fr, dict):
                bad.append((nid, "from 不是映射结构"))
            elif fr.get("material") not in reg:
                bad.append((nid, f"from.material「{fr.get('material')}」未在 materials 段登记"))
            elif not fr.get("locator"):
                bad.append((nid, "from 缺 locator（页码/表号/图号），视同未抽取"))
        elif has_registry and pv in ("E1_given", "E6_administrative"):
            unsourced.append(nid)
    return bad, unsourced



# =============================================================================
# 追料时效
# =============================================================================

def _bdays(d0, d1):
    """工作日差。不精确到节假日——那需要日历数据，且各地不同；
    多算几天不会让判断走反，少算会。所以只扣周末。"""
    if not d0 or not d1:
        return None
    a, b = min(d0, d1), max(d0, d1)
    days = (b - a).days
    full_weeks, rem = divmod(days, 7)
    n = full_weeks * 5
    wd = a.weekday()
    for i in range(rem):
        if (wd + i + 1) % 7 not in (5, 6):
            n += 1
    return n if d1 >= d0 else -n


def scan_aging(proj, mat_l0):
    """追料到期判定。

    没有时限的等待会一直等下去——直到某个人受不了了，随手把那个数填上。
    编造多数是这样发生的，不是恶意，是拖久了。时限的目的不是催客户，
    是逼出一个显式决定：补料 / 用替代物 / 显式留白 / 暂停。
    """
    sla = mat_l0.get("intake_sla") or {}
    profiles = sla.get("profiles") or {}
    classes = mat_l0.get("material_classes") or {}
    as_of = proj.get("as_of")
    out = []
    for g in (proj.get("material_gaps") or []):
        if not isinstance(g, dict) or g.get("status") in ("resolved", "closed"):
            continue
        cls = g.get("class")
        pname = (classes.get(cls) or {}).get("sla") or "commissioned"
        prof = profiles.get(pname) or {}
        age = _bdays(g.get("asked_at"), as_of)
        if age is None:
            stage, action = "unknown", "缺 asked_at，时钟没起算——追料没留痕等于没追"
        elif age >= prof.get("decide_days", 20):
            stage = "decide"
            action = "停止等待，把 S1–S4 四条出口摆给客户，请其书面选一条并入账"
        elif age >= prof.get("escalate_days", 10):
            stage = "escalate"
            action = "升级到建设单位项目负责人，**同时给出替代方案**——只说「还没收到」是无效升级"
        elif age >= prof.get("remind_days", 5):
            stage = "remind"
            action = "第一次催办，重述卡住哪几章、可接受的替代物是什么"
        else:
            stage = "open"
            action = "正常等待，不打扰"
        out.append({"class": cls, "cn": (classes.get(cls) or {}).get("cn", cls),
                    "profile": pname, "profile_cn": prof.get("cn", pname),
                    "age_bdays": age, "stage": stage, "action": action,
                    "planned_exit": g.get("planned_exit"),
                    "note": g.get("note")})
    order = {"decide": 0, "escalate": 1, "remind": 2, "unknown": 3, "open": 4}
    out.sort(key=lambda x: (order[x["stage"]], -(x["age_bdays"] or 0)))
    return out

# =============================================================================
# 来源路由
# =============================================================================

def _rule_targets(proj):
    return {r.get("target") for r in (proj.get("rules") or []) if isinstance(r, dict)}


def route_missing(proj, routing_l0, vert):
    """对图中缺失的节点判定路由。"""
    nodes = set((proj.get("nodes") or {}).keys())
    targets = _rule_targets(proj)
    table = (vert or {}).get("routing_overrides") or {}

    missing = set()
    for r in (proj.get("rules") or []):
        if not isinstance(r, dict) or not r.get("formula"):
            continue
        try:
            refs = _refs_in_formula(r["formula"])
        except SyntaxError:
            continue
        for ref in refs:
            if ref not in nodes and ref not in targets:
                missing.add(ref)

    out = {"ASK": [], "SEARCH": [], "COMPUTE": [], "WITHHOLD": []}
    for n in sorted(missing):
        if n in targets:
            out["COMPUTE"].append({"node": n, "why": "是某条规则的 target，输入齐了自动算"})
            continue
        route = table.get(n)
        if not route:
            route = _guess_route(n)
        out.setdefault(route, []).append({"node": n, "why": _route_why(n, route)})

    # 手填的派生值（C11a 的口径）：声明为 E4 却无规则
    handfilled = [nid for nid, nd in (proj.get("nodes") or {}).items()
                  if isinstance(nd, dict) and nd.get("provenance") == "E4_derived"
                  and nid not in targets]
    return out, handfilled


SEARCH_HINTS = ("index.", ".rate", "mandate.", "norm.")
COMPUTE_HINTS = (".total", ".demand", ".required", ".deficit", ".contingency", ".unit_price")


def _guess_route(n):
    if any(h in n for h in SEARCH_HINTS):
        return "SEARCH"
    if any(n.endswith(h) for h in COMPUTE_HINTS):
        return "COMPUTE"
    return "ASK"


def _route_why(n, route):
    return {
        "ASK": "只存在于客户的台账/方案/决策中，外部查不到",
        "SEARCH": "公开可查（标准规范/地方法规），不占客户时间；但入图前须过适配性评估并由客户勾选",
        "COMPUTE": "可由图中其他节点算出，不许问也不许手填",
        "WITHHOLD": "四条路径均不成立，留白并写明待补",
    }.get(route, "")


# =============================================================================
# 报告
# =============================================================================

EXIT_CN = {"S1_substitute": "S1 用替代物", "S2_withhold_and_risk": "S2 留白+进风险章",
           "S3_narrow_scope": "S3 缩小出具范围", "S4_suspend": "S4 暂停并告知阻塞"}


def report(have, missing, unclassified, bad, unsourced, routed, handfilled,
           vert_name, req_source="垂类要求", aging=None):
    L = ["=" * 74, f"素材摄入扫描{'（' + vert_name + '）' if vert_name else ''}", "=" * 74, ""]

    L.append(f"已登记素材 {sum(len(v) for v in have.values())} 份，覆盖 {len(have)} 个素材类")
    for cls, items in sorted(have.items()):
        L.append(f"  ✓ {cls}：" + "、".join(str(m.get("name") or m.get("id")) for m in items))
    L.append("")

    blocking = [m for m in missing if m["required"]]
    if missing:
        L.append("-" * 74)
        L.append(f"一、缺素材（{len(missing)} 类，其中阻塞 {len(blocking)} 类）")
        L.append(f"    比对依据：{req_source}")
        L.append("-" * 74)
        for m in missing:
            tag = "【阻塞】" if m["required"] else "【可延后】"
            L.append(f"{tag} {m['cn']}（{m['class']}）  找谁要：{m['provider']}")
            L.append(f"    追料话术：{m['ask']}")
            L.append(f"    不给的后果：{m['consequence']}")
            if m["substitutes"]:
                L.append(f"    可接受的替代物：{'、'.join(x for x in m['substitutes'] if x)}")
            L.append("")
    else:
        L.append(f"一、缺素材：无。{req_source}的素材类均已登记。\n")

    L.append("-" * 74)
    L.append(f"二、未归类素材（{len(unclassified)} 份）")
    L.append("-" * 74)
    if unclassified:
        for m in unclassified:
            L.append(f"  ? {m.get('name') or m.get('id')} —— 请客户确认这是什么")
        L.append("    不要自行猜测用途后抽取——猜错会把一份过期草案当成正式件用。")
    else:
        L.append("  ✓ 无")
    L.append("")

    L.append("-" * 74)
    L.append(f"二之二、追料时效（{len(aging or [])} 笔在追）")
    L.append("-" * 74)
    if aging:
        STAGE_CN = {"open": "正常等待", "remind": "到催办点", "escalate": "到升级点",
                    "decide": "**到决策点**", "unknown": "时钟未起算"}
        for a in aging:
            age = f"{a['age_bdays']} 个工作日" if a["age_bdays"] is not None else "—"
            L.append(f"  [{STAGE_CN[a['stage']]}] {a['cn']}（{a['profile_cn']}，已 {age}）")
            L.append(f"      {a['action']}")
            if a.get("planned_exit"):
                L.append(f"      预定出口：{EXIT_CN.get(a['planned_exit'], a['planned_exit'])}")
            if a.get("note"):
                L.append(f"      备注：{a['note']}")
        if any(a["stage"] == "decide" for a in aging):
            L.append("")
            L.append("  ⚠ 已有到决策点的追料。四条合法出口：")
            L.append("      S1 用可接受的替代物（证据降级，须显式标注）")
            L.append("      S2 显式留白 + CH9 列为前置条件未闭合（行政批复类的默认出口）")
            L.append("      S3 该维度声明资料不足、本次不出具结论（须客户书面确认）")
            L.append("      S4 暂停并告知阻塞（主干素材缺位时的唯一出口）")
            L.append("      **到期不改变编造的性质。估一个、套同类、写「暂按经验值」都不是出口。**")
    else:
        L.append("  ✓ 无在追素材")
    L.append("")

    L.append("-" * 74)
    L.append("三、取值可溯源")
    L.append("-" * 74)
    if bad:
        for nid, msg in bad:
            L.append(f"  ✗ {nid}：{msg}")
    if unsourced:
        L.append(f"  ⚠ {len(unsourced)} 个客户给定/批复类取值没有 from（无法倒查出自哪份材料的哪一页）：")
        L.append(f"    {sorted(unsourced)}")
        L.append("    编造若发生，必然发生在这一批里。补 from，或降级为待确认。")
    if not bad and not unsourced:
        L.append("  ✓ 全部客户给定取值都能指回具体材料的具体位置")
    L.append("")

    L.append("-" * 74)
    L.append("四、缺口按来源路由分派")
    L.append("-" * 74)
    CN = {"ASK": "必须客户输入", "SEARCH": "agent 自行检索",
          "COMPUTE": "由图派生（不许问、不许填）", "WITHHOLD": "留白待补"}
    for k in ("ASK", "SEARCH", "COMPUTE", "WITHHOLD"):
        items = routed.get(k) or []
        L.append(f"  {k}（{CN[k]}）：{len(items)} 项")
        for it in items:
            L.append(f"      · {it['node']} —— {it['why']}")
    L.append("")

    if handfilled:
        L.append("-" * 74)
        L.append("五、路由违规")
        L.append("-" * 74)
        L.append(f"  ✗ 以下节点声明为 E4_derived 但图中没有对应规则，即手填的派生值：")
        L.append(f"    {sorted(handfilled)}")
        L.append("    手填派生值等于切断派生链，C2 从此对它失效。补规则，或改标 E1_given。")
        L.append("")

    L.append("-" * 74)
    L.append("下一步")
    L.append("-" * 74)
    if blocking:
        L.append(f"  先追 {len(blocking)} 类阻塞素材。它们不到位，动笔就是编。")
    L.append("  SEARCH 项批量前置做掉，不占客户时间；结果须过 fit_rank.py 排序后交客户勾选。")
    L.append("  提问顺序用 intake_gen.py --batch 5 出，按阻塞度降序，不按章节顺序。")
    return "\n".join(L)


@guard
def main(argv):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("project")
    ap.add_argument("--vertical")
    ap.add_argument("--json")
    a = ap.parse_args(argv[1:])

    mat_l0 = _load("materials.yaml")
    routing_l0 = _load("provenance-routing.yaml")
    proj = yaml.safe_load(Path(a.project).read_text(encoding="utf-8"))

    vd = _vertical_dir(proj, a.vertical)
    vert = yaml.safe_load((vd / "materials.yaml").read_text(encoding="utf-8")) if vd else {}
    vname = (vert or {}).get("vertical") or (vd.name if vd else "")

    have, missing, unclassified, req_source = scan_materials(proj, mat_l0, vert)
    bad, unsourced = scan_traceability(proj)
    routed, handfilled = route_missing(proj, routing_l0, vert)
    aging = scan_aging(proj, mat_l0)

    print(report(have, missing, unclassified, bad, unsourced, routed, handfilled,
                 vname, req_source, aging))
    if a.json:
        Path(a.json).write_text(json.dumps({
            "requirement_source": req_source,
            "have": {k: [m.get("id") for m in v] for k, v in have.items()},
            "missing_materials": missing, "unclassified": [m.get("id") for m in unclassified],
            "aging": aging,
            "bad_from": bad, "unsourced": unsourced,
            "routed": routed, "handfilled_derived": handfilled,
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n已写出 {a.json}")
    overdue = [a for a in aging if a["stage"] in ("decide", "unknown")]
    return 1 if ([m for m in missing if m["required"]] or bad or handfilled or overdue) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
