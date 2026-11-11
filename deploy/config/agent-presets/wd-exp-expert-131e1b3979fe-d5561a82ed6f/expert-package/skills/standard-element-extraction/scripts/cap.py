# -*- coding: utf-8 -*-
"""抽取能力件（与具体标准无关，可复用到任意 HJ/GB 方法标准）

子命令：
  probe <pdf>                       文本层判定与取字分流
  patternize --ses <ses.json>       规则模式匹配 → 候选规则 + 对已有规则的召回率
  lint --ses a.json [b.json ...]    一致性检查（ID/锚/定位/枚举/数值/参照隔离/跨标准差异）
  gate --ses <ses.json> --toc <json>准入闸回测（漏判/多判）

设计原则：全部为确定性计算，零 LLM；输出 JSON + 退出码（有 ERROR 则 1）。
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATTERNS = json.load(open(os.path.join(HERE, "patterns.json"), encoding="utf-8"))["patterns"]

# ---------------------------------------------------------------- probe
def probe(pdf_path):
    b = open(pdf_path, "rb").read()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", b))
    fonts = len(re.findall(rb"/Font", b))
    imgs = len(re.findall(rb"/Subtype\s*/Image", b))
    if fonts > 0:
        route, note = "PDFKIT", "有文本层，PDFKit 直取；抽查 3 页与图像比对"
    elif imgs > 0:
        route, note = "OCR", "无文本层（图像/转曲），需 300 dpi 栅格化 + OCR；数值回图像逐格核读"
    else:
        route, note = "MANUAL", "无文本层也无图像，需人工获取可读版本"
    return {"file": os.path.basename(pdf_path), "pages": pages, "fonts": fonts,
            "images": imgs, "route": route, "note": note,
            "size_bytes": len(b)}

# ---------------------------------------------------------------- patternize
def _has(text, kind):
    if kind == "numeric":
        return bool(re.search(r"\d", text))
    if kind == "timeunit":
        return bool(re.search(r"\d+\s*(天|周|个月|月|年|h|min)", text))
    if kind == "matrix":
        return bool(re.search(r"(地表水|地下水|污水|废水|海水|饮用水)", text))
    if kind == "formula":
        return bool(re.search(r"[=＝]|式\s*\(?\d", text))
    return True

def patternize(ses):
    clauses = ses["clause_registry"]
    cands = []
    for c in clauses:
        text = (c.get("heading") or "") + " " + (c.get("quote") or "")
        for p in PATTERNS:
            if not any(t in text for t in p["triggers"]):
                continue
            if not _has(text, p.get("require", "none")):
                continue
            m = re.search(p["extract"], text) if p.get("extract") else None
            val = None
            if m:
                g = [x for x in m.groups()]
                tpl = p["predicate"].get("value")
                if isinstance(tpl, str) and "$1" in tpl:
                    val = "$1..$2" if "$2" in tpl and len(g) > 1 else g[0]
                    if str(tpl).startswith("$1..$2") and len(g) > 1:
                        val = f"{g[0]}..{g[1]}"
            cands.append({"pattern": p["id"], "name": p["name"], "category": p["category"],
                          "clause": c["clause"], "page": c["page"],
                          "predicate": p["predicate"], "extracted": val,
                          "primitives": p["primitives"], "on_missing": p["on_missing"],
                          "anchor_quote": (c.get("quote") or "")[:80]})
    # 召回：已有规则是否被某候选的「条款+分类」覆盖
    existing = ses.get("audit_rule_cards") or []
    cand_by_clause = {}
    for x in cands:
        cand_by_clause.setdefault(x["clause"], set()).add(x["category"])
    hit_cat, hit_clause, miss = [], [], []
    for r in existing:
        cats = cand_by_clause.get(r["clause"], set())
        if cats:
            hit_clause.append(r["rule_id"])
            if r["category"] in cats:
                hit_cat.append(r["rule_id"])
            else:
                miss.append({"rule": r["rule_id"], "clause": r["clause"],
                             "existing": r["category"], "candidate": sorted(cats)})
        else:
            miss.append({"rule": r["rule_id"], "clause": r["clause"], "existing": r["category"],
                         "candidate": []})
    return {"standard": ses["standard_id"], "clauses": len(clauses),
            "candidates": len(cands), "existing_rules": len(existing),
            "covered_clause": len(hit_clause),
            "recall_clause": round(len(hit_clause) / max(1, len(existing)), 3),
            "covered_category": len(hit_cat),
            "recall_category": round(len(hit_cat) / max(1, len(existing)), 3),
            "uncovered": miss, "detail": cands}

# ---------------------------------------------------------------- lint
def lint(ses_list):
    errs, warns, info = [], [], []
    seen = {}
    for ses in ses_list:
        sid = ses["standard_id"]
        rules = ses.get("audit_rule_cards") or []
        ids = [r["rule_id"] for r in rules]
        # 1 ID 唯一
        dup = sorted({x for x in ids if ids.count(x) > 1})
        (errs if dup else info).append({"check": "id_unique", "standard": sid,
                                        "detail": dup or "ok"})
        # 2 锚完整
        bad = [r["rule_id"] for r in rules
               if not (r.get("clause") and r.get("page") and (r.get("anchor") or {}).get("quote"))]
        (errs if bad else info).append({"check": "anchor_complete", "standard": sid, "detail": bad or "ok"})
        # 3 定位线索
        bad = [r["rule_id"] for r in rules if not r.get("check_targets")]
        (errs if bad else info).append({"check": "locator_present", "standard": sid, "detail": bad or "ok"})
        # 4 on_missing 枚举
        bad = [r["rule_id"] for r in rules if r.get("on_missing") not in ("FAIL", "UNVERIFIABLE")]
        (errs if bad else info).append({"check": "on_missing_enum", "standard": sid, "detail": bad or "ok"})
        # 5 数值合理性
        for r in rules:
            p = r.get("predicate") or {}
            f, v = str(p.get("field", "")), p.get("value")
            if "相关系数" in f and isinstance(v, (int, float)) and not (0.9 <= v <= 1.0):
                errs.append({"check": "numeric_sanity", "standard": sid,
                             "detail": f"{r['rule_id']} 相关系数阈值越界: {v}"})
            if p.get("op") == "between" and isinstance(v, list) and len(v) == 2 \
               and all(isinstance(x, (int, float)) for x in v):
                if v[0] > v[1]:
                    errs.append({"check": "numeric_sanity", "standard": sid,
                                 "detail": f"{r['rule_id']} 区间上小于下: {v}"})
            if "回收率" in f and isinstance(v, list) and len(v) == 2:
                if not (0 <= v[0] <= 100 and 0 <= v[1] <= 150):
                    errs.append({"check": "numeric_sanity", "standard": sid,
                                 "detail": f"{r['rule_id']} 回收率越界: {v}"})
        # 6 参照隔离：锚在「精密度/准确度」章且做阈值判定 → 警告
        for r in rules:
            q = (r.get("anchor") or {}).get("quote", "")
            if re.search(r"精密度|准确度|重复性限|再现性限", q) and \
               (r.get("predicate") or {}).get("op") in (">=", "<=", "==", "between"):
                warns.append({"check": "reference_isolation", "standard": sid,
                              "detail": f"{r['rule_id']} 疑将性能数据当判定阈值"})
        # 7 规则集规模
        info.append({"check": "scale", "standard": sid,
                     "detail": f"clauses={len(ses.get('clause_registry', []))} rules={len(rules)}"})
        seen[sid] = rules

    # 8 跨标准差异（同名字段，不同阈值）
    diff = {}
    for sid, rules in seen.items():
        for r in rules:
            p = r.get("predicate") or {}
            f = p.get("field")
            if f and isinstance(p.get("value"), (int, float)):
                diff.setdefault(f, {}).setdefault(str(p["value"]), []).append(sid)
    ANALYTE_SPECIFIC = {"方法检出限", "测定下限", "测定范围", "检测结果"}
    cross = [{"field": f, "values": {v: s for v, s in vals.items()}}
             for f, vals in diff.items() if len(vals) > 1 and f not in ANALYTE_SPECIFIC]
    if cross:
        warns.append({"check": "cross_standard_diff", "standard": "ALL",
                      "detail": f"{len(cross)} 个字段在不同标准间阈值不同，须按方法族隔离"})
    return {"errors": errs, "warnings": warns, "info": info, "cross_standard": cross,
            "ok": not errs}

# ---------------------------------------------------------------- gate
def gate(ses, toc):
    clauses, rules = ses["clause_registry"], ses.get("audit_rule_cards") or []
    has_rule = {}
    for r in rules:
        has_rule[r["clause"]] = has_rule.get(r["clause"], 0) + 1
    ch_has = {}
    for cl, n in has_rule.items():
        m = re.match(r"^(\d+)", str(cl))
        if m: ch_has[m.group(1)] = ch_has.get(m.group(1), 0) + n
    ROLE = [(r"范围", ["R"]), (r"引用", ["B"]), (r"原理|术语|定义", ["SKIP"]), (r"干扰", ["R"]),
            (r"试剂|材料", ["R"]), (r"仪器|设备", ["R"]), (r"样品", ["R"]), (r"步骤|测定", ["R"]),
            (r"计算|表示", ["R"]), (r"精密度|准确度", ["A"]), (r"质量保证|质量控制", ["R"]),
            (r"注意", ["R"]), (r"废物", ["R"])]
    def role_of(txt):
        for pat, role in ROLE:
            if re.search(pat, txt or ""):
                return role
        return ["SKIP"]
    leak, over, hit = [], [], 0
    for c in clauses:
        cl = str(c["clause"])
        if cl in ("目次", "前言", "公告"):
            role = ["SKIP"]
        elif cl.startswith(("表", "图")):
            txt = (c.get("heading") or "") + (c.get("quote") or "")
            role = ["A"] if re.search(r"精密度|准确度|重复性限|再现性限", txt) else ["R"]
        elif cl.startswith("附录"):
            role = ["R"]
        elif cl == "封面":
            role = ["R"]
        else:
            m = re.match(r"^(\d+)", cl)
            role = role_of(toc.get(m.group(1), "") if m and toc else "") if m else ["SKIP"]
            if role == ["SKIP"] and m:
                role = role_of(c.get("heading"))
        pred = bool(set(role) & {"R", "G", "M"})
        true = has_rule.get(cl, 0) > 0
        m = re.match(r"^(\d+)", cl)
        if pred and true: hit += 1
        elif pred and not true and not (m and ch_has.get(m.group(1))): over.append(cl)
        elif (not pred) and true and role == ["SKIP"]: leak.append(cl)
        else: hit += 1
    n = len(clauses)
    return {"standard": ses["standard_id"], "clauses": n, "hit": hit,
            "leak": leak, "over": over, "leak_count": len(leak),
            "hit_pct": round(hit / n, 3), "pass": len(leak) == 0}

# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("probe"); s.add_argument("pdf")
    s = sub.add_parser("patternize"); s.add_argument("--ses", required=True)
    s = sub.add_parser("lint"); s.add_argument("--ses", nargs="+", required=True)
    s = sub.add_parser("gate"); s.add_argument("--ses", required=True); s.add_argument("--toc")
    a = ap.parse_args()

    if a.cmd == "probe":
        print(json.dumps(probe(a.pdf), ensure_ascii=False, indent=2))
    elif a.cmd == "patternize":
        r = patternize(json.load(open(a.ses, encoding="utf-8")))
        print(f"{r['standard']}: 条款 {r['clauses']}｜候选 {r['candidates']}｜已有 {r['existing_rules']}｜"
              f"条款级召回 {r['recall_clause']:.0%}｜分类级召回 {r['recall_category']:.0%}")
        none = [u for u in r["uncovered"] if not u["candidate"]]
        if none:
            print("  完全无模式命中:", [u["rule"] for u in none][:8])
        json.dump(r, open(os.path.join(os.path.dirname(a.ses), "patternize.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=2)
    elif a.cmd == "lint":
        r = lint([json.load(open(p, encoding="utf-8")) for p in a.ses])
        print(f"errors={len(r['errors'])} warnings={len(r['warnings'])} ok={r['ok']}")
        for e in r["errors"]: print("  ERROR", e["check"], e["standard"], str(e["detail"])[:120])
        for w in r["warnings"]: print("  WARN ", w["check"], w["standard"], str(w["detail"])[:120])
        if r["cross_standard"]:
            print("  跨标准差异字段:", [c["field"] for c in r["cross_standard"]])
        sys.exit(0 if r["ok"] else 1)
    elif a.cmd == "gate":
        toc = json.load(open(a.toc, encoding="utf-8")) if a.toc else {}
        r = gate(json.load(open(a.ses, encoding="utf-8")), toc)
        print(f"{r['standard']}: 条款 {r['clauses']}｜判对 {r['hit']}（{r['hit_pct']:.0%}）"
              f"｜漏判 {r['leak_count']}｜多判 {len(r['over'])}")
        if r["leak"]: print("  漏判:", r["leak"])
        sys.exit(0 if r["pass"] else 1)

if __name__ == "__main__":
    main()
