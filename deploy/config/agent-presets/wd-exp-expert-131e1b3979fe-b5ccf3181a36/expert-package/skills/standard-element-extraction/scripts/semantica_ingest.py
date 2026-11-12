#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""semantica 灌图适配器（命名空间化，**默认 dry-run**）。

约束：
  1. 只读 ses.json，不修改抽取产物；
  2. 必须带命名空间 std:<slug>，禁止裸节点（共享图已有他人内容）；
  3. 默认只产出 payload，不写入；--apply 需要显式确认写入工具可用。

用法：
  python3 semantica_ingest.py --ses <out/ses.json> [--out <dir>] [--apply]
"""
import argparse, json, os, sys

def build(ses):
    slug = ses["standard_slug"]; ns = f"std:{slug}"
    ents, rels = [], []
    def ent(kind, key, **props):
        name = f"{ns}::{kind}:{key}"
        ents.append({"name": name, "type": kind,
                     "properties": {"namespace": ns, "project": slug, "node_id": key,
                                    "standard_id": ses["standard_id"], **props}})
        return name
    for c in ses.get("clause_registry", []):
        ent("Clause", c["clause"], page=c.get("page"), modality=c.get("modality"), type=c.get("type"))
    for e in ses.get("elements", []):
        ent("Element", e["element_id"], family=e.get("family"), obligation=e.get("obligation"),
            clause=(e.get("anchor") or {}).get("clause"))
        rels.append({"from": f"{ns}::Element:{e['element_id']}",
                     "to": f"{ns}::Clause:{(e.get('anchor') or {}).get('clause')}", "type": "ANCHORS"})
    for r in ses.get("audit_rule_cards", []):
        ent("Rule", r["rule_id"], category=r.get("category"), clause=r.get("clause"),
            on_missing=r.get("on_missing"), judge=r.get("judge_mode") or r.get("judge_method"))
        rels.append({"from": f"{ns}::Rule:{r['rule_id']}", "to": f"{ns}::Clause:{r.get('clause')}", "type": "ANCHORS"})
    for g in ses.get("gaps", []):
        ent("Gap", g["gap_id"], type_=g.get("type"), desc=(g.get("description") or "")[:200])
        for c in (g.get("affected_clauses") or []):
            rels.append({"from": f"{ns}::Gap:{g['gap_id']}", "to": f"{ns}::Clause:{c}", "type": "AFFECTS"})
    ents = [e for i, e in enumerate(ents) if e["name"] not in {x["name"] for x in ents[:i]}]
    rels = [r for i, r in enumerate(rels) if r not in rels[:i]]
    return {"namespace": ns, "entities": ents, "relationships": rels}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ses", required=True); ap.add_argument("--out"); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ses = json.load(open(a.ses, encoding="utf-8"))
    p = build(ses)
    out = a.out or os.path.dirname(os.path.abspath(a.ses))
    os.makedirs(out, exist_ok=True)
    ent_p, rel_p = os.path.join(out, "semantica-entities.jsonl"), os.path.join(out, "semantica-rels.jsonl")
    for path, rows in ((ent_p, p["entities"]), (rel_p, p["relationships"])):
        with open(path, "w", encoding="utf-8") as f:
            for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {"namespace": p["namespace"], "entities": len(p["entities"]), "relationships": len(p["relationships"]),
               "mode": "apply" if a.apply else "dry-run", "files": [ent_p, rel_p]}
    if a.apply:
        summary["applied"] = False
        summary["reason"] = "MCP 仅暴露只读资源（summary/decisions/schema），未挂载写入工具；payload 已生成，待工具可用后再灌"
        summary["required_tool"] = {"name": "graph.ingest", "namespace": p["namespace"], "dry_run": True}
    json.dump(summary, open(os.path.join(out, "semantica-ingest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
