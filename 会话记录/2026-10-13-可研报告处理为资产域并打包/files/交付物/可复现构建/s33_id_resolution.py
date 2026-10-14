# -*- coding: utf-8 -*-
"""s33 —— 引用 ID 可解析性门禁（**纯集合差，客观判据**）。

背景：本会话出现 13 个节点 ID 因数字替换吃进 hex 内部而失效，
      当时无任何判据能发现 —— 这条门禁就是补这个洞。

判据：资产文件里出现的每个 "N-xxxxxxxxxxxx" 引用，必须能在 graph/nodes.yaml 找到。
      · 无法解析 ⇒ FAIL（引用悬空，下游（推演写作专家）会拿到打不开的节点ID）
      · 只报集合差，不做任何语义判断。
"""
import json, re, sys
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
R = WS / "SHUFE-BDC-2019-001"
NODE_RE = re.compile(r'"(N-[^"]{4,40})"')
# 允许的 ID 形态：N- + 12 位 hex（本体节点）
CANON = re.compile(r"^N-[0-9a-f]{12}$")


def check() -> dict:
    nodes = json.loads((R / "graph" / "nodes.yaml").read_text(encoding="utf-8"))
    ids = {n["id"] for n in nodes}
    bad_form, unresolved, per_file = [], {}, {}
    for p in sorted(list(R.rglob("*.yaml")) + list(R.rglob("*.json"))):
        if "run_record" in str(p):
            continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        for ref in set(NODE_RE.findall(t)):
            if not CANON.match(ref):
                bad_form.append(f"{p.relative_to(R)}: {ref} ← 形态非法（疑似被替换污染）")
            elif ref not in ids:
                unresolved.setdefault(str(p.relative_to(R)), []).append(ref)
    gaps = bad_form + [f"{f}: {r}" for f, rs in unresolved.items() for r in rs]
    res = {"verdict": "FAIL" if gaps else "pass",
           "nodes": len(ids), "gaps": len(gaps), "bad_form": len(bad_form),
           "unresolved": sum(len(v) for v in unresolved.values()),
           "detail": gaps[:20],
           "note": "引用 ID 必须可解析（集合差）；形态非法者几乎必然是替换污染"}
    (R / "quality" / "id_resolution.yaml").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = check()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(1 if r["verdict"] == "FAIL" else 0)
