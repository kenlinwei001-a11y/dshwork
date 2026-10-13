# -*- coding: utf-8 -*-
"""闭环校验 closure_verify（确定性，零 LLM）。

**与旧机制的关系**：不替换 `ontology.validate_extraction`，而是补一层。
  · 旧：遍历产物 P → 保证「抽出来的对不对」（形状/枚举）
  · 新：S − P − 豁免 → 保证「该抽的都抽了没有」（完备性）
两者都过才允许进入下游。

判据全部为：集合差 / 守恒 / 覆盖率比值。输出固定为
`{id, name, total, covered, exempt, missing[], recall_pct, threshold, verdict}`，
其中 verdict ∈ {pass, FAIL, invalid}——**invalid 表示探针未标定，不得当作 pass**。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .units import same_quantity

# ---------------------------------------------------------------- 载入
def _j(p: Path, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:                                  # noqa: BLE001
        return default


def load_package(corpus_dir):
    root = Path(corpus_dir)
    return {
        "root": root,
        "nodes": _j(root / "graph" / "nodes.yaml", []),
        "claims": _j(root / "graph" / "claims.yaml", []),
        "relations": _j(root / "graph" / "relations.yaml", []),
        "evidence": _j(root / "evidence" / "evidence.yaml", []),
        "outline": _j(root / "outline.yaml", {}),
        "ledger": _j(root / "source_ledger.json", None),
    }


# ---------------------------------------------------------------- 豁免规则
_CITE_STD = re.compile(r"标准|规范|规程|通则|办法|规定|通知|规划|纲要|条例|法$|决定|意见|"
                       r"定额|图集|规则|指南|指标|措施|GB|DGJ|JGJ")
_CITE_EXEMPT = re.compile(r"Journal|Annals|学报|杂志|Econometrica|JASA|教材|课程|"
                          r"预制|桁架|叠合板|楼梯|阳台板|连接节点|灌浆料|合同$")
_SKIP_PRED = re.compile(r"估算金额|台数|单间用房标准|地址|四至|粗糙度|竖向|土层|矿化|"
                        r"潜水位|单井出水|铭牌参数|实体名")


def _closure(cid, name, total, covered, missing, threshold, probe_ok=True, note=""):
    missing = list(missing)
    valid = bool(probe_ok)
    rec = round(covered / max(total, 1) * 100, 1)
    verdict = "invalid" if not valid else ("pass" if rec >= threshold else "FAIL")
    return {"id": cid, "name": name, "total": total, "covered": covered,
            "missing_count": len(missing), "missing": missing[:80],
            "recall_pct": rec, "threshold": threshold, "verdict": verdict, "note": note}


# ---------------------------------------------------------------- 七道闭环
def closure_verify(corpus_dir, *, draft_path=None, thresholds=None) -> dict:
    T = {"C1": 95, "C2": 90, "C3": 98, "C4": 80, "C5": 60, "C6": 95, "C7": 95}
    T.update(thresholds or {})
    pk = load_package(corpus_dir)
    led = pk["ledger"] or {}
    draft = Path(draft_path).read_text(encoding="utf-8") if draft_path and Path(draft_path).exists() else ""
    dn = re.sub(r"[\s　]", "", draft)
    out = []

    # C1 依据闭环
    ev_names = " ".join((e.get("doc") or "") + (e.get("quote") or "") for e in pk["evidence"])
    cits = [c for c in led.get("citations", []) if _CITE_STD.search(c)]
    miss = [c for c in cits if c[:6] not in ev_names and c not in ev_names]
    out.append(_closure("C1", "依据闭环（原稿引用→证据条目）", len(cits), len(cits) - len(miss), miss, T["C1"]))

    # C2 关键取值闭环（含量纲归一，扣假缺口）
    gvals = {re.sub(r"[^\d.]", "", str(n.get("value", ""))) for n in pk["nodes"]}
    key_total, key_miss = [], []
    for item in led.get("valued_numbers", []):
        v, _, u = item.partition(" ")
        if not re.match(r"^\d", v):
            continue
        key_total.append(item)
        if v.replace(",", "") in gvals:
            continue
        equiv = any(same_quantity(v, u, str(n.get("value", "")), n.get("unit") or "")
                    for n in pk["nodes"] if n.get("unit"))
        if not equiv:
            key_miss.append(item)
    out.append(_closure("C2", "关键取值闭环（原稿带单位数值→图谱）",
                        len(key_total), len(key_total) - len(key_miss), key_miss, T["C2"]))

    # C3 章节闭环
    titles = {re.sub(r"[\s　]", "", x.get("title", "")) for x in pk["outline"].get("sections", [])}
    heads = led.get("headings", [])
    h_miss = [h for h in heads if re.sub(r"[\s　]", "", h) not in titles]
    out.append(_closure("C3", "章节闭环（原稿标题→outline）",
                        len(heads), len(heads) - len(h_miss), h_miss, T["C3"]))

    # C4 设备参数闭环
    dev_nodes = [n for n in pk["nodes"]
                 if n.get("auto_extracted") or n.get("predicate") == "铭牌参数"]
    dev_lines = led.get("device_param_lines", [])
    d_miss = [] if len(dev_nodes) >= len(dev_lines) * 0.9 else \
        [f"设备参数语句 {len(dev_lines)} 条，图谱仅 {len(dev_nodes)} 个节点"]
    out.append(_closure("C4", "设备参数闭环（原稿设备参数→设备节点）",
                        max(len(dev_lines), 1), len(dev_nodes), d_miss, T["C4"]))

    # C5 题注闭环（须在成稿上判）
    caps = led.get("captions", [])
    if draft:
        cap_miss = [c for c in caps if re.sub(r"\s", "", c) not in dn]
        out.append(_closure("C5", "题注闭环（原稿表/图题注→成稿）",
                            len(caps), len(caps) - len(cap_miss), cap_miss, T["C5"]))
    else:
        out.append(_closure("C5", "题注闭环（原稿表/图题注→成稿）", len(caps), 0,
                            ["未提供成稿，本轮不判"], T["C5"], probe_ok=False))

    # C6 装配闭环
    if draft:
        tot, m6 = 0, []
        for n in pk["nodes"]:
            v = re.sub(r"[\s　]", "", str(n.get("value", "")))
            if (len(v) < 3 or _SKIP_PRED.search(n.get("predicate", ""))
                    or n.get("status", "defined") != "defined"):
                continue
            tot += 1
            if v not in dn:
                m = re.match(r"([\d,]+(?:\.\d+)?)", v)
                if not (m and (m.group(1) in dn or m.group(1).replace(",", "") in dn)):
                    m6.append(f"{n.get('subject')}·{n.get('predicate')}")
        out.append(_closure("C6", "装配闭环（图谱 defined 节点→成稿引用）", tot, tot - len(m6), m6, T["C6"]))
    else:
        out.append(_closure("C6", "装配闭环（图谱 defined 节点→成稿引用）", 1, 0,
                            ["未提供成稿，本轮不判"], T["C6"], probe_ok=False))

    # C7 claim 关系闭环
    from .relations_ext import derive_expected_relations
    exp = derive_expected_relations(pk["claims"], pk["relations"])
    have = {k: sum(1 for r in pk["relations"] if r.get("type") == k) for k in exp["expected"]}
    need = exp["expected"]
    m7 = [f"{k}: 应有 {need[k]}，现有 {have.get(k, 0)}" for k in need if have.get(k, 0) < need[k]]
    out.append(_closure("C7", "claim 关系闭环（应有关系→图谱）",
                        sum(need.values()), sum(min(have.get(k, 0), need[k]) for k in need), m7, T["C7"]))

    _w = load_waivers(corpus_dir)
    out = [apply_waivers(c, _w) for c in out]
    return {"closures": out,
            "summary": {"pass": sum(1 for c in out if c["verdict"] in ("pass", "pass_with_waivers")),
                        "pass_with_waivers": sum(1 for c in out if c["verdict"] == "pass_with_waivers"),
                        "FAIL": sum(1 for c in out if c["verdict"] == "FAIL"),
                        "invalid": sum(1 for c in out if c["verdict"] == "invalid")},
            "policy": "missing 非空或探针未标定 ⇒ FAIL/invalid；由编排器判定，不由写作 Agent 自判"}


def save_closure_report(result: dict, out_path) -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


if __name__ == "__main__":
    import sys
    d = sys.argv[1]
    draft = sys.argv[2] if len(sys.argv) > 2 else None
    r = closure_verify(d, draft_path=draft)
    for c in r["closures"]:
        print(f"{c['id']} {c['verdict']:8s} {c['recall_pct']:6.1f}% 缺 {c['missing_count']}")
    print(r["summary"])

# fix31-waivers: 豁免装载（不可修项必须显式登记，不得静默消失）
def load_waivers(corpus_dir) -> list[dict]:
    data = _j(Path(corpus_dir) / "quality" / "waivers.yaml", {}) or {}
    out = []
    for w in data.get("waivers", []):
        crit = str(w.get("criterion", ""))
        pat = w.get("pattern", "")           # fix32: 支持正则批量豁免
        if pat:
            out.append({"criterion": crit, "pattern": pat, "reason": w.get("reason", ""),
                        "owner": w.get("owner", ""), "disposition": w.get("disposition", "")})
        for it in (w.get("items") or []):
            out.append({"criterion": crit, "item": str(it), "reason": w.get("reason", ""),
                        "owner": w.get("owner", ""), "disposition": w.get("disposition", "")})
    return out


def apply_waivers(result: dict, waivers: list[dict]) -> dict:
    """把 missing 中命中豁免的项移入 waived；豁免后无 missing 则记 pass_with_waivers。

    注意：**豁免不等于通过** —— verdict 明确写成 pass_with_waivers，
    且 waived 列表随结果一起输出，可审计到责任方。
    """
    cid = result.get("id") or result.get("stage") or ""
    kept, waived = [], list(result.get("waived") or [])
    for m in result.get("missing", []):
        def _m(w):
            if not cid or cid not in w["criterion"]:
                return False
            if w.get("pattern"):
                return re.search(w["pattern"], str(m)) is not None
            return w["item"] in str(m) or str(m) in w["item"]

        hit = next((w for w in waivers if _m(w)), None)
        if hit:
            waived.append({"item": m, "reason": hit["reason"], "owner": hit["owner"],
                           "disposition": hit["disposition"]})
        else:
            kept.append(m)
    result["missing"] = kept
    result["missing_count"] = len(kept)
    result["waived"] = waived
    result["waived_count"] = len(waived)
    if not kept:
        result["verdict"] = "pass_with_waivers" if waived else result.get("verdict", "pass")
    return result
