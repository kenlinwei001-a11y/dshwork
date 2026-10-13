#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反向回读：客户改了文档，把改动读回图上的节点变更。

这是 references/reconcile.yaml 的实现。规格写了却不实现，
在工业标准下就是缺陷——这个脚本补上它。

两种承载模式：
  协同文档（腾讯文档/飞书等）：平台给块 ID + 变更事件，定位是确定的
  docx 往返：靠渲染时埋的书签定位，书签被破坏时退化为文本匹配

不回读的后果：客户改了第 5 章的面积，第 7 章的能耗、第 8 章的造价、
第 1 章的指标表全是旧值，而且没人知道。这正是本方案要消灭的事故。

用法：
    # docx 模式
    python3 scripts/reconcile.py <project.yaml> --bindings out/bindings.json \\
        --edited edited.docx
    # 协同文档模式（平台变更事件）
    python3 scripts/reconcile.py <project.yaml> --bindings out/bindings.json \\
        --changes changes.json
    # 变更事件格式：[{"block": "CH1#2", "old": "26400", "new": "26800"}, ...]
"""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from impact import ImpactAnalyzer  # noqa: E402
from assets import load_l0, guard  # noqa: E402
from schema import _refs_in_formula  # noqa: E402


# =============================================================================
# 从 docx 读回锚点当前值
# =============================================================================

def read_bookmarks(docx_path):
    """返回 {bookmark_name: 当前文本}。"""
    import docx
    from docx.oxml.ns import qn

    doc = docx.Document(docx_path)
    out = {}

    def scan(paragraph):
        p = paragraph._p
        children = list(p)
        open_bm = {}
        for idx, el in enumerate(children):
            tag = el.tag
            if tag == qn("w:bookmarkStart"):
                open_bm[el.get(qn("w:id"))] = (el.get(qn("w:name")), idx)
            elif tag == qn("w:bookmarkEnd"):
                bid = el.get(qn("w:id"))
                if bid in open_bm:
                    name, start_idx = open_bm.pop(bid)
                    text = ""
                    for mid in children[start_idx + 1:idx]:
                        if mid.tag == qn("w:r"):
                            for t in mid.iter(qn("w:t")):
                                text += t.text or ""
                    out[name] = text

    for para in doc.paragraphs:
        scan(para)
    for tb in doc.tables:
        for row in tb.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    scan(para)
    return out


def parse_number(text):
    t = (text or "").strip().replace(",", "").replace("，", "")
    try:
        v = float(t)
        return int(v) if v.is_integer() else v
    except ValueError:
        return None


# =============================================================================
# 回读
# =============================================================================

class Reconciler:

    def __init__(self, proj, bindings, core, argu, deriv):
        self.p = proj
        self.b = bindings
        self.nodes = proj.get("nodes") or {}
        self.rules = [r for r in (proj.get("rules") or []) if isinstance(r, dict)]
        self.an = ImpactAnalyzer(proj, core, argu, deriv)
        self.derived_targets = {r.get("target") for r in self.rules if r.get("formula")}
        # bookmark → (node, 渲染时的值)
        self.bm2node = {}
        # block → [(node, 渲染值, 书签)]
        self.block2nodes = {}
        for node, occs in bindings.items():
            for o in occs:
                self.bm2node[o["bookmark"]] = (node, o)
                # block 只有协同文档模式才有；docx 模式只埋 bookmark。
                # 缺 block 就跳过这条索引，不该让整个回读崩掉
                if o.get("block"):
                    self.block2nodes.setdefault(o["block"], []).append((node, o))

    # ------------------------------------------------------------------
    def _origin_section(self, node):
        """节点的权威来源章节：provides 它的那一章。"""
        for s in (self.p.get("sections") or []):
            if isinstance(s, dict) and node in (s.get("provides") or []):
                return s.get("id")
        occs = self.b.get(node) or []
        return occs[0]["section"] if occs else None

    def _rule_of(self, node):
        return next((r for r in self.rules if r.get("target") == node), None)

    def _upstream(self, node):
        r = self._rule_of(node)
        if not r or not r.get("formula"):
            return []
        try:
            return sorted(set(_refs_in_formula(r["formula"])))
        except SyntaxError:
            return []

    # ------------------------------------------------------------------
    def classify(self, node, occ, old_text, new_text):
        """按 reconcile.yaml 的 change_types 分类。"""
        new_val = parse_number(new_text)
        old_val = occ.get("value")

        if new_val is None:
            return {"type": "T_prose", "action": "accept_no_graph_change",
                    "message": f"改为非数值文本「{new_text}」，视为行文修改，不动图"}

        if new_val == old_val:
            return {"type": "unchanged", "action": "none", "message": "值未变"}

        if node in self.derived_targets:
            r = self._rule_of(node)
            ups = self._upstream(node)
            up_vals = {u: (self.nodes.get(u) or {}).get("value") for u in ups}
            return {
                "type": "T_derived", "action": "reject",
                "message": (
                    f"「{node}」是由规则 {r.get('id')} 计算得出的派生值，不能直接改。\n"
                    f"      公式：{r.get('formula')}\n"
                    f"      当前上游取值：{up_vals}\n"
                    f"      若要得到 {new_val}，需要调整的是上游中的某一项。\n"
                    f"      请确认改哪一项——您想说的多半不是「这个数变成 {new_val}」，"
                    f"而是某个上游变了。"),
                "upstream": ups,
            }

        occs = self.b.get(node) or []
        origin = self._origin_section(node)
        if len(occs) > 1 and occ.get("section") != origin:
            return {
                "type": "T_restated", "action": "reject",
                "message": (
                    f"「{node}」在本报告中出现 {len(occs)} 处，权威来源是 {origin}。\n"
                    f"      您改的是 {occ.get('section')} 的复述处。\n"
                    f"      请在 {origin} 修改，全部 {len(occs)} 处会同步更新。"),
                "origin": origin, "occurrences": len(occs),
            }

        return {"type": "T_given", "action": "accept",
                "message": f"客户给定事实变更：{old_val} → {new_val}",
                "new_value": new_val}

    # ------------------------------------------------------------------
    def from_docx(self, docx_path):
        current = read_bookmarks(docx_path)
        changes, orphans = [], []
        for bm, text in current.items():
            if bm not in self.bm2node:
                orphans.append({"bookmark": bm, "text": text})
                continue
            node, occ = self.bm2node[bm]
            if text.strip() != str(occ.get("rendered", "")).strip():
                changes.append((node, occ, occ.get("rendered"), text))
        missing = [bm for bm in self.bm2node if bm not in current]
        return changes, orphans, missing

    def from_changes(self, events):
        """协同文档模式：平台给块 ID + 前后值，定位是确定的。"""
        changes, orphans = [], []
        for ev in events:
            blk = ev.get("block")
            cands = self.block2nodes.get(blk) or []
            if not cands:
                orphans.append({"block": blk, "text": ev.get("new")})
                continue
            old = str(ev.get("old", "")).strip()
            hit = [(n, o) for n, o in cands if str(o.get("rendered")).strip() == old]
            if len(hit) != 1:
                # 块内多节点且旧值无法唯一匹配 → 交人工
                orphans.append({"block": blk, "text": ev.get("new"),
                                "candidates": [n for n, _ in cands]})
                continue
            node, occ = hit[0]
            changes.append((node, occ, occ.get("rendered"), str(ev.get("new"))))
        return changes, orphans, []

    # ------------------------------------------------------------------
    def coverage_at_risk(self, missing_bookmarks):
        """锚点丢失 → 哪些法定 covers 可能失去承载。

        原来这里只打印一句「删除会触发 C7 法定覆盖检查」，却没有真去查。
        提示一个不存在的检查比不提示更糟——它让人以为已经查过了。
        """
        if not missing_bookmarks:
            return []
        secs = set()
        for bm in missing_bookmarks:
            hit = self.bm2node.get(bm)
            if hit:
                _node, occ = hit
                if occ.get("section"):
                    secs.add(occ["section"])
        if not secs:
            return []
        out = []
        for sec in sorted(secs):
            spec = next((x for x in (self.p.get("sections") or [])
                         if isinstance(x, dict) and x.get("id") == sec), None)
            covers = (spec or {}).get("covers") or []
            if covers:
                out.append({"section": sec, "title": (spec or {}).get("title"),
                            "covers": covers})
        return out

    def run(self, changes, orphans, missing):
        decisions = []
        accepted = {}
        for node, occ, old_text, new_text in changes:
            d = self.classify(node, occ, old_text, new_text)
            d.update({"node": node, "section": occ.get("section"),
                      "block": occ.get("block"),
                      "old": old_text, "new": new_text})
            decisions.append(d)
            if d["action"] == "accept" and "new_value" in d:
                accepted[node] = d["new_value"]

        impact = self.an.analyze(accepted) if accepted else None
        return {"decisions": decisions, "accepted": accepted,
                "impact": impact, "orphans": orphans, "lost_anchors": missing,
                "coverage_at_risk": self.coverage_at_risk(missing)}


def render(res):
    L = ["=" * 70, "反向回读结果", "=" * 70, ""]
    dec = res["decisions"]
    by = {}
    for d in dec:
        by.setdefault(d["type"], []).append(d)

    labels = {"T_given": "接受：客户给定事实变更", "T_derived": "拒绝：改了派生值",
              "T_restated": "拒绝：改了复述处", "T_prose": "接受：行文修改，不动图",
              "unchanged": "未变"}
    for t, items in by.items():
        if t == "unchanged":
            continue
        L.append(f"【{labels.get(t, t)}】{len(items)} 处")
        for d in items:
            L.append(f"  {d['node']}  ({d['section']} / {d['block']})")
            L.append(f"    {d['old']} → {d['new']}")
            for line in str(d["message"]).split("\n"):
                L.append(f"    {line}" if not line.startswith("      ") else line)
            L.append("")

    if res["orphans"]:
        L.append(f"【图外内容】{len(res['orphans'])} 处")
        L.append("  这些改动无法回溯到图上的节点，不在 C1-C7 的保护范围内。")
        L.append("  逐条确认：是否应当建为图上的节点/论断/Mandate。")
        for o in res["orphans"][:10]:
            L.append(f"    · {o}")
        L.append("")

    if res["lost_anchors"]:
        L.append(f"【锚点丢失】{len(res['lost_anchors'])} 处")
        L.append("  渲染时埋的书签在返回的文档中找不到了——可能被编辑操作破坏，")
        L.append("  也可能整段被删除。删除会触发 C7 法定覆盖检查。")
        L.append("  锚点丢失率持续偏高，说明应改用协同文档模式（块 ID 稳定）。")
        car = res.get("coverage_at_risk") or []
        if car:
            L.append("")
            L.append("  ⚠ 丢失的锚点所在章节承载着法定内容。若这些章节确实被删除，")
            L.append("    以下法定 covers 将失去承载，C7 会报 error，评审按大纲逐项对照时会被打回：")
            for c in car:
                L.append(f"      {c['section']} {c.get('title') or ''} → {c['covers']}")
            L.append("    先确认是「整段被删」还是「书签被编辑操作破坏」——")
            L.append("    前者要问清楚为什么删、能不能改为降级为节；后者重渲染即可恢复。")
        else:
            L.append("  已查：丢失的锚点不涉及承载法定内容的章节。")
        L.append("")

    imp = res.get("impact")
    if imp:
        L.append("-" * 70)
        L.append("被接受的变更会牵动：")
        L.append("")
        d = imp["delta"]
        L.append(f"  派生值变化 {len(d)} 项：")
        for k, v in list(d.items())[:15]:
            L.append(f"    {k}: {v['old']} → {v['new']}")
        secs = imp["affected_sections"]
        L.append(f"  需重写章节 {len(secs)} 章：{[s['id'] for s in secs]}")
        if imp["errors_after_change"]:
            L.append(f"  新引入错误 {len(imp['errors_after_change'])} 项：")
            for e in imp["errors_after_change"][:6]:
                L.append(f"    [{e['code']}] {e['subject']}")
        L.append("")
        L.append("确认后才执行回写与重写。")
    elif not any(d["action"] == "accept" for d in dec):
        L.append("-" * 70)
        L.append("没有被接受的节点变更，图保持不变。")
    return "\n".join(L)


@guard
def main(argv):
    if len(argv) < 2 or "--bindings" not in argv:
        print("用法: reconcile.py <project.yaml> --bindings bindings.json "
              "(--edited edited.docx | --changes changes.json) [--json out]")
        return 2
    core, argu, deriv = load_l0()
    proj = yaml.safe_load(Path(argv[1]).read_text(encoding="utf-8"))
    bindings = json.loads(Path(argv[argv.index("--bindings") + 1]).read_text(encoding="utf-8"))
    rc = Reconciler(proj, bindings, core, argu, deriv)

    if "--edited" in argv:
        ch, orph, miss = rc.from_docx(argv[argv.index("--edited") + 1])
    elif "--changes" in argv:
        events = json.loads(Path(argv[argv.index("--changes") + 1]).read_text(encoding="utf-8"))
        ch, orph, miss = rc.from_changes(events)
    else:
        print("需要 --edited 或 --changes")
        return 2

    res = rc.run(ch, orph, miss)
    print(render(res))
    if "--json" in argv:
        out = Path(argv[argv.index("--json") + 1])
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
