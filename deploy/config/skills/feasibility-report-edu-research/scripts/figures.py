#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
插图生成：把图上的节点画成 SVG，嵌入正文对应段落。

只画**数据图**——面积构成、投资构成、资金平衡、缺额对比、进度横道。
它们的全部内容都来自已确认的节点，画图只是换一种表述方式，不引入新事实。

**设计图一律不画**（总平面、建筑平面立面剖面、结构布置、机电系统、效果图）。
那些承载的是设计单位的专业判断，agent 没有也推不出来；画出来会被当成设计成果审，
问题却记到设计单位头上。缺设计图走 WITHHOLD，正文写明「详见设计单位提供的 XX 图」。

判据一句话：**这张图里有没有「图上没有的信息」。** 有就是设计图，不画。

规则见 references/figures.yaml。用法见 render.py 的 {{figure:F_XXX}} 占位符。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assets import AssetError, REF  # noqa: E402

import yaml  # noqa: E402

# 打印友好：白底深墨，相邻分项明度差足够，黑白打印仍可辨
INK = "#1a1a1a"
GRID = "#c8ccd2"
SUB = "#5b6270"
SERIES = ["#2f5d9e", "#6f9bd1", "#a8bfd9", "#4a4a4a", "#8a8a8a", "#c0c0c0"]
# 字体链把能解析到中文字形的名字排在前面。
# 光谱化名（-apple-system 之类）在服务器端栅格化时解析不到，
# 会静默退到无中文字形的字体，输出一片方框——而图里全是方框这件事
# 只有真的打开图才看得见，测试查不出来。所以这里只用真实字体名。
FONT = ("'Noto Sans CJK SC','Source Han Sans SC','WenQuanYi Zen Hei',"
        "'PingFang SC','Microsoft YaHei',sans-serif")


class FigureError(Exception):
    """图画不出来。缺节点、分项对不上合计，都在这里抛出——不出半成品。"""


def load_spec():
    p = REF / "figures.yaml"
    if not p.exists():
        raise AssetError(
            "缺少 references/figures.yaml —— 它规定了哪些图可以生成、哪些绝对不能。\n"
            "  缺了它，agent 会去画总平面图，那是把不存在的设计判断伪装成设计成果。")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


# =============================================================================
# SVG 基元
# =============================================================================

def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _txt(x, y, s, size=11, fill=INK, anchor="start", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}">{_esc(s)}</text>')


def _rect(x, y, w, h, fill, stroke="none"):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w,0):.1f}" height="{max(h,0):.1f}" '
            f'fill="{fill}" stroke="{stroke}"/>')


def _line(x1, y1, x2, y2, stroke=GRID, w=1, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{w}"{d}/>')


def _wrap(w, h, body, title, caption, nodes):
    """统一外框：图题在上，图注在下。

    图题固定带「示意图，据本报告数据生成」——让读者一眼知道这不是设计成果。
    图注列出所用节点，评审问「这张图的数从哪来」时答得上。
    """
    src = "数据来源：" + "、".join(nodes)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}">'
        f'<rect width="{w}" height="{h}" fill="#ffffff"/>'
        + _txt(w / 2, 20, title, 12.5, INK, "middle", "600")
        + _txt(w / 2, 36, "（示意图，据本报告数据生成）", 9.5, SUB, "middle")
        + body
        + _txt(w / 2, h - 18, caption, 9.5, SUB, "middle")
        + _txt(w / 2, h - 6, src, 8.5, "#8b919c", "middle")
        + "</svg>")


def _num(v):
    if isinstance(v, float) and not v.is_integer():
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return str(int(v)) if isinstance(v, (int, float)) else str(v)


# =============================================================================
# 图形
# =============================================================================

def stacked_bar(items, total_label, unit, title, caption, nodes, check_total=None):
    """构成图：一根横条，分项按比例切分。

    check_total 给了就核对分项之和——「图漏了一个分项」由此变成可机检的问题（C15c）。
    """
    vals = [v for _, v in items]
    s = sum(vals)
    if check_total is not None and abs(s - check_total) > max(1e-6, abs(check_total) * 0.001):
        raise FigureError(
            f"分项之和 {_num(s)} 与合计 {_num(check_total)} 不符，差 {_num(check_total - s)}。\n"
            f"  这不是画图的问题——要么图上漏了一个分项，要么合计节点算错了。\n"
            f"  先在图上把它解决，再渲染。")
    W, H = 580, 210
    x0, x1, y = 60, W - 60, 78
    bh = 42
    body = []
    cx = x0
    span = x1 - x0
    for i, (name, v) in enumerate(items):
        w = span * (v / s) if s else 0
        c = SERIES[i % len(SERIES)]
        body.append(_rect(cx, y, w, bh, c))
        if w > 34:
            body.append(_txt(cx + w / 2, y + bh / 2 + 4, _num(v), 10.5, "#ffffff", "middle", "600"))
        cx += w
    body.append(_txt(x0, y - 10, f"{total_label} {_num(s)} {unit}", 10.5, INK, "start", "600"))

    # 图例排在下方成两列。原来用引导线标在柱子正下方，
    # 窄分项（占比 1% 以下）的标签会互相压住，打印出来根本读不了。
    cols = 2
    rows = (len(items) + cols - 1) // cols
    for i, (name, v) in enumerate(items):
        col, row = i // rows, i % rows
        lx = x0 + col * ((x1 - x0) / cols)
        ly = y + bh + 26 + row * 17
        body.append(_rect(lx, ly - 9, 10, 10, SERIES[i % len(SERIES)]))
        pct = f"（{v / s * 100:.1f}%）" if s else ""
        body.append(_txt(lx + 15, ly, f"{name}　{_num(v)} {unit}{pct}", 9.5, INK))
    H2 = y + bh + 26 + rows * 17 + 34
    return _wrap(W, max(H, H2), "".join(body), title, caption, nodes)


def bar(items, unit, title, caption, nodes):
    """分项条形图。横向，便于放中文标签。"""
    W = 560
    H = 92 + len(items) * 30 + 40
    x0 = 150
    x1 = W - 90
    mx = max([v for _, v in items] + [1])
    body = []
    for i, (name, v) in enumerate(items):
        y = 72 + i * 30
        w = (x1 - x0) * (v / mx)
        body.append(_txt(x0 - 8, y + 13, name, 10, INK, "end"))
        body.append(_rect(x0, y, w, 18, SERIES[i % len(SERIES)]))
        body.append(_txt(x0 + w + 6, y + 13, f"{_num(v)} {unit}", 9.5, SUB))
    body.append(_line(x0, 66, x0, 72 + len(items) * 30 - 6, GRID, 1))
    return _wrap(W, H, "".join(body), title, caption, nodes)


def compare_bar(pairs, unit, title, caption, nodes, note=None):
    """两值对比图，自动标注偏差率。"""
    W, H = 520, 220
    x0, x1 = 120, W - 110
    mx = max([v for _, v in pairs] + [1])
    body = []
    for i, (name, v) in enumerate(pairs):
        y = 74 + i * 46
        w = (x1 - x0) * (v / mx)
        body.append(_txt(x0 - 8, y + 18, name, 10.5, INK, "end"))
        body.append(_rect(x0, y, w, 26, SERIES[i * 2 % len(SERIES)]))
        body.append(_txt(x0 + w + 6, y + 18, f"{_num(v)} {unit}", 10, INK, "start", "600"))
    if len(pairs) == 2 and pairs[0][1]:
        dev = (pairs[1][1] - pairs[0][1]) / pairs[0][1] * 100
        body.append(_txt(W / 2, 74 + 2 * 46 + 22,
                         f"偏差 {dev:+.2f}%", 10.5, INK, "middle", "600"))
        if note:
            body.append(_txt(W / 2, 74 + 2 * 46 + 36, note, 9, SUB, "middle"))
    return _wrap(W, max(H, 74 + 2 * 46 + 36 + 34), "".join(body), title, caption, nodes)


def deficit_bar(required, existing, deficit, new_area, unit, title, caption, nodes):
    """缺额分析图：应建 / 现有 / 缺额 / 本次新建，并显示硬约束是否满足。"""
    W, H = 560, 240
    x0, x1 = 120, W - 110
    mx = max(required, 1)
    rows = [("应建规模", required, SERIES[2]), ("现有存量", existing, SERIES[1]),
            ("缺额", deficit, SERIES[0]), ("本次新建", new_area, SERIES[3])]
    body = []
    for i, (name, v, c) in enumerate(rows):
        y = 72 + i * 34
        w = (x1 - x0) * (v / mx)
        body.append(_txt(x0 - 8, y + 15, name, 10, INK, "end"))
        body.append(_rect(x0, y, w, 21, c))
        body.append(_txt(x0 + w + 6, y + 15, f"{_num(v)} {unit}", 9.5, SUB))
    ok = new_area <= deficit
    msg = ("本次新建 ≤ 缺额，未构成重复建设" if ok
           else "本次新建超出缺额，须在论断的「反驳」项中说明依据")
    body.append(_txt(W / 2, 72 + 4 * 34 + 18, msg, 10, INK if ok else "#a33", "middle", "600"))
    return _wrap(W, max(H, 72 + 4 * 34 + 18 + 34), "".join(body), title, caption, nodes)


def balance_bar(sources, total_cost, unit, title, caption, nodes):
    """资金平衡图：来源分项 vs 总投资，两柱等高才算平衡。"""
    W, H = 520, 250
    base_y, top_y = 200, 62
    mx = max(sum(v for _, v in sources), total_cost, 1)
    h_of = lambda v: (base_y - top_y) * (v / mx)
    body = [_line(70, base_y, W - 70, base_y, GRID, 1)]
    # 左柱：来源堆叠
    cx, bw = 150, 74
    y = base_y
    for i, (name, v) in enumerate(sources):
        h = h_of(v)
        y -= h
        body.append(_rect(cx, y, bw, h, SERIES[i % len(SERIES)]))
        if h > 16:
            body.append(_txt(cx + bw / 2, y + h / 2 + 4, f"{name} {_num(v)}",
                             9, "#ffffff", "middle"))
    src_total = sum(v for _, v in sources)
    body.append(_txt(cx + bw / 2, y - 7, f"{_num(src_total)} {unit}", 10, INK, "middle", "600"))
    body.append(_txt(cx + bw / 2, base_y + 15, "资金来源", 10, INK, "middle"))
    # 右柱：总投资
    cx2 = W - 150 - bw
    h2 = h_of(total_cost)
    body.append(_rect(cx2, base_y - h2, bw, h2, "#4a4a4a"))
    body.append(_txt(cx2 + bw / 2, base_y - h2 - 7, f"{_num(total_cost)} {unit}",
                     10, INK, "middle", "600"))
    body.append(_txt(cx2 + bw / 2, base_y + 15, "项目总投资", 10, INK, "middle"))
    diff = src_total - total_cost
    msg = ("平衡" if abs(diff) < 1e-6
           else f"差额 {_num(diff)} {unit} —— 硬等式不成立，须核对")
    body.append(_txt(W / 2, base_y + 34, msg, 10.5,
                     INK if abs(diff) < 1e-6 else "#a33", "middle", "600"))
    return _wrap(W, H, "".join(body), title, caption, nodes)


def grouped_bar(groups, series_names, unit, title, caption, nodes):
    """分组柱状图（如分年度、分来源的资金安排）。"""
    W = 560
    base_y, top_y = 200, 66
    n = len(groups)
    gw = (W - 140) / max(n, 1)
    mx = max([sum(vals) for _, vals in groups] + [1])
    body = [_line(70, base_y, W - 70, base_y, GRID, 1)]
    for gi, (gname, vals) in enumerate(groups):
        gx = 80 + gi * gw
        bw = min(46, gw * 0.5)
        y = base_y
        for si, v in enumerate(vals):
            h = (base_y - top_y) * (v / mx)
            y -= h
            body.append(_rect(gx + (gw - bw) / 2, y, bw, h, SERIES[si % len(SERIES)]))
        body.append(_txt(gx + gw / 2, y - 6, _num(sum(vals)), 9.5, INK, "middle", "600"))
        body.append(_txt(gx + gw / 2, base_y + 15, gname, 9.5, INK, "middle"))
    for si, sname in enumerate(series_names):
        lx = 80 + si * 96
        body.append(_rect(lx, base_y + 28, 10, 10, SERIES[si % len(SERIES)]))
        body.append(_txt(lx + 15, base_y + 37, f"{sname}（{unit}）", 9, SUB))
    return _wrap(W, 250, "".join(body), title, caption, nodes)


def gantt(tasks, title, caption, nodes):
    """进度横道图。tasks: [(名称, 起月, 历时月)]，单位为自项目起算的月。"""
    W = 580
    H = 92 + len(tasks) * 26 + 46
    x0, x1 = 160, W - 60
    span = max([s + d for _, s, d in tasks] + [1])
    body = []
    step = max(1, round(span / 8))
    for m in range(0, span + 1, step):
        x = x0 + (x1 - x0) * (m / span)
        body.append(_line(x, 66, x, 72 + len(tasks) * 26, GRID, 0.7, "2 3"))
        body.append(_txt(x, 60, f"第{m}月", 8.5, SUB, "middle"))
    for i, (name, s, d) in enumerate(tasks):
        y = 74 + i * 26
        bx = x0 + (x1 - x0) * (s / span)
        bw = (x1 - x0) * (d / span)
        body.append(_txt(x0 - 8, y + 13, name, 9.5, INK, "end"))
        body.append(_rect(bx, y + 3, bw, 14, SERIES[i % 3]))
        body.append(_txt(bx + bw + 5, y + 13, f"{d}个月", 8.5, SUB))
    return _wrap(W, H, "".join(body), title, caption, nodes)


# =============================================================================
# 从图上的节点构造插图
# =============================================================================

CN = {
    "scale.design_above": "地上建筑面积", "scale.design_under": "地下建筑面积",
    "scale.stilt_floor": "架空层", "scale.above_bldg": "地上单体",
    "scale.dorm": "宿舍", "scale.canteen": "食堂",
    "cost.construction": "建筑安装工程费", "cost.other": "工程建设其他费",
    "cost.contingency": "基本预备费", "cost.demolition": "拆除费",
    "cost.equipment": "设备购置费",
    "funding.gov": "政府投资", "funding.self": "自筹资金", "funding.loan": "银行贷款",
    "program.researcher.demand": "科研人员用房", "program.student.demand": "学生用房",
    "program.support.demand": "配套用房",
    "scale.demand_total": "需求测算值", "scale.design_total": "设计规模",
}


def _v(nodes, key, figure_id):
    n = nodes.get(key)
    if not isinstance(n, dict) or n.get("value") is None:
        raise FigureError(
            f"插图 {figure_id} 需要节点「{key}」，图上没有。\n"
            f"  与 {{{{节点名}}}} 占位符同一条约束：缺就中止，不出半成品图。\n"
            f"  带着空白坐标轴的图流出去，会有人手工把数填上。")
    return n["value"], n.get("unit", "")


def build(figure_id, proj, spec=None):
    """按 figure_id 生成 SVG 字符串。缺节点抛 FigureError。"""
    spec = spec or load_spec()
    cat = (spec.get("figures") or {})
    if figure_id not in cat:
        forb = [f.get("kind") for f in (spec.get("forbidden") or []) if isinstance(f, dict)]
        raise FigureError(
            f"未知插图 {figure_id}。可生成的图见 references/figures.yaml。\n"
            f"  以下类型**一律不生成**（属设计成果，agent 推不出来）：{'、'.join(x for x in forb if x)}\n"
            f"  缺设计图时正文写「详见设计单位提供的 XX 图」，并列入 M3 素材缺口。")
    f = cat[figure_id]
    nodes = proj.get("nodes") or {}
    cap = f.get("caption", "")
    title = f"图 {f.get('cn')}"

    if figure_id == "F_AREA_COMPOSITION":
        items, used = [], []
        for k in ["scale.design_above", "scale.design_under", "scale.stilt_floor"]:
            if k in nodes:
                v, u = _v(nodes, k, figure_id)
                items.append((CN.get(k, k), v)); used.append(k)
        if len(items) < 2:
            raise FigureError(f"{figure_id} 至少需要两个面积分项，当前只有 {len(items)} 个")
        tot = nodes.get("scale.design_total", {}).get("value")
        _, u = _v(nodes, used[0], figure_id)
        return stacked_bar(items, "总建筑面积", u, title, cap, used + (["scale.design_total"] if tot else []),
                           check_total=tot)

    if figure_id == "F_COST_COMPOSITION":
        items, used = [], []
        for k in ["cost.construction", "cost.other", "cost.contingency",
                  "cost.demolition", "cost.equipment"]:
            if k in nodes:
                v, u = _v(nodes, k, figure_id)
                items.append((CN.get(k, k), v)); used.append(k)
        tot = nodes.get("cost.total", {}).get("value")
        _, u = _v(nodes, used[0], figure_id)
        return stacked_bar(items, "项目总投资", u, title, cap,
                           used + (["cost.total"] if tot else []), check_total=tot)

    if figure_id == "F_DEMAND_BREAKDOWN":
        items, used = [], []
        for k in sorted(nodes):
            if k.endswith(".demand") and k != "scale.demand_total":
                v, u = _v(nodes, k, figure_id)
                items.append((CN.get(k, k), v)); used.append(k)
        if len(items) < 2:
            raise FigureError(f"{figure_id} 需要至少两项需求节点（*.demand）")
        _, u = _v(nodes, used[0], figure_id)
        return bar(items, u, title, cap, used)

    if figure_id == "F_DEMAND_VS_DESIGN":
        a, u = _v(nodes, "scale.demand_total", figure_id)
        b, _ = _v(nodes, "scale.design_total", figure_id)
        note = None
        if a and abs(b - a) / a > 0.01:
            note = "偏差超 1%，正文须在论断的「反驳」项说明超出部分的构成"
        return compare_bar([("需求测算值", a), ("设计规模", b)], u, title, cap,
                           ["scale.demand_total", "scale.design_total"], note)

    if figure_id == "F_DEFICIT":
        base = f.get("_facility") or _guess_facility(nodes)
        req, u = _v(nodes, f"{base}.required.phase", figure_id)
        exi, _ = _v(nodes, f"{base}.existing.phase", figure_id)
        dfc, _ = _v(nodes, f"{base}.deficit.phase", figure_id)
        new = nodes.get(f"scale.{base}", {}).get("value", dfc)
        return deficit_bar(req, exi, dfc, new, u, title, cap,
                           [f"{base}.required.phase", f"{base}.existing.phase",
                            f"{base}.deficit.phase", f"scale.{base}"])

    if figure_id == "F_FUNDING_BALANCE":
        srcs, used = [], []
        for k in sorted(nodes):
            if k.startswith("funding.") and k not in ("funding.total", "funding.annual"):
                v, u = _v(nodes, k, figure_id)
                srcs.append((CN.get(k, k.split(".")[-1]), v)); used.append(k)
        if not srcs:
            raise FigureError(f"{figure_id} 找不到任何资金来源节点（funding.*）")
        tot, _ = _v(nodes, "cost.total", figure_id)
        _, u = _v(nodes, used[0], figure_id)
        return balance_bar(srcs, tot, u, title, cap, used + ["cost.total"])

    if figure_id == "F_FUNDING_ANNUAL":
        ann = nodes.get("funding.annual", {}).get("value")
        if not isinstance(ann, dict):
            raise FigureError(f"{figure_id} 需要 funding.annual 为分年度映射")
        names = sorted({s for y in ann.values() if isinstance(y, dict) for s in y})
        groups = [(str(y), [ (ann[y] or {}).get(s, 0) for s in names]) for y in sorted(ann)]
        return grouped_bar(groups, [CN.get("funding." + s, s) for s in names],
                           "万元", title, cap, ["funding.annual"])

    if figure_id == "F_SCHEDULE":
        ms = nodes.get("schedule.milestones", {}).get("value")
        if not isinstance(ms, list) or not ms:
            raise FigureError(
                f"{figure_id} 需要 schedule.milestones。\n"
                f"  客户只给了总工期没给里程碑时**不要自己拆**——"
                f"拆出来的节点会被当成承诺。")
        tasks = [(m.get("name"), m.get("start_month", 0), m.get("months", 1)) for m in ms]
        return gantt(tasks, title, cap, ["schedule.milestones"])

    raise FigureError(f"{figure_id} 在清单中但尚未实现生成器")


def _guess_facility(nodes):
    for k in nodes:
        if k.endswith(".required.phase"):
            return k.split(".")[0]
    raise FigureError("找不到 *.required.phase 节点，无法确定缺额图的用房类型")


def to_png(svg, width=None):
    """转 PNG 供 docx 嵌入。没有转换器时明确报错，不出半成品。"""
    try:
        import cairosvg
    except ImportError:
        raise FigureError(
            "缺少 SVG 转换器，无法把插图嵌入 docx。\n"
            "  安装：pip install cairosvg --break-system-packages\n"
            "  SVG 本身已生成在 out/figures/ 下，可单独查看或交排版处理。") from None
    return cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                            output_width=width or 900, background_color="white")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="生成单张插图，用于调试")
    ap.add_argument("project")
    ap.add_argument("figure_id")
    ap.add_argument("-o", "--out", default="figure.svg")
    a = ap.parse_args()
    proj = yaml.safe_load(Path(a.project).read_text(encoding="utf-8"))
    try:
        Path(a.out).write_text(build(a.figure_id, proj), encoding="utf-8")
        print(f"已生成 {a.out}")
    except (FigureError, AssetError) as e:
        print(f"插图未生成：\n{e}")
        sys.exit(1)
