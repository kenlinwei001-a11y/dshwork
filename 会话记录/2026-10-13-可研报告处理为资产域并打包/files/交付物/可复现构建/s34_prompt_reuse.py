# -*- coding: utf-8 -*-
"""s34 —— 提示词复用与逐片记录门禁（**客观：哈希相等 + 计数相等**）。

判据（全部为确定性算法，无 LLM 参与）：
  ① **提示词复用**：同一 (doc, task) 的所有分片记录中 prompt_sha256 种类数必须 == 1
     （>1 ⇒ 提示词被逐片重编，缓存失效、结果不可比）
  ② **记录可信**：记录里的 prompt_sha256 必须等于
     `prompts/<doc>.<task>.json` 内 prompt_sha256（哈希相等）——防止记录里的哈希是编造的
  ③ **覆盖完整**：记录条数 == 该文档切片数（集合计数相等）
  ④ **调用状态**：status == "not_invoked" 的记录 ⇒ 本判据**判 invalid**（不得视为通过）
     （无 provider 时诚实留白，不伪造抽取结果）
"""
import json
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
R = WS / "SHUFE-BDC-2019-001"
RUNS = R / "quality" / "extraction_runs"


def check() -> dict:
    fails, invalids, stats = [], [], []
    if not RUNS.exists():
        return {"verdict": "invalid", "note": "无 extraction_runs（抽取未由编译器驱动）",
                "gaps": [], "invalid_count": 0, "stats": []}
    for f in sorted(RUNS.glob("*.jsonl")):
        recs = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not recs:
            continue
        doc, task = recs[0]["doc_id"], recs[0]["task"]
        cp_path = R / "prompts" / f"{doc}.{task}.json"
        cp = json.loads(cp_path.read_text(encoding="utf-8")) if cp_path.exists() else {}
        kinds = {r["prompt_sha256"] for r in recs}
        not_inv = sum(1 for r in recs if r["status"] == "not_invoked")
        # ① 复用
        if len(kinds) != 1:
            fails.append(f"{doc}.{task}: 出现 {len(kinds)} 种 prompt_sha256（应恒为 1）")
        # ② 记录可信
        if cp and (kinds != {cp.get("prompt_sha256")}):
            fails.append(f"{doc}.{task}: 记录 prompt_sha256 与编译产物不一致（疑似编造）")
        # ③ 覆盖
        n_chunks = None
        src = (R / "chunks" / "chunks.jsonl") if doc.startswith("DOC-REPORT") else (R / "external" / "chunks.jsonl")
        if src.exists():
            cs = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
            n_chunks = (len(cs) if doc.startswith("DOC-REPORT")
                        else sum(1 for c in cs
                                 if c.get("doc") == doc or c.get("document_id") == doc))
            # ★ 适配「零切片文档」：应恰好 1 条 no_chunks 记录（显式记录缺失，而非留空）
            if n_chunks == 0:
                if not (len(recs) == 1 and recs[0].get("status") == "no_chunks"):
                    fails.append(f"{doc}.{task}: 无切片，但记录不是单条 no_chunks（{len(recs)} 条）")
            elif n_chunks != len(recs):
                fails.append(f"{doc}.{task}: 记录 {len(recs)} 条 ≠ 切片 {n_chunks} 片")
        # ④ 调用状态
        if not_inv > 0:
            invalids.append(f"{doc}.{task}: {not_inv}/{len(recs)} 片未调用（无 provider）")
        stats.append({"run": f"{doc}.{task}", "records": len(recs), "chunks": n_chunks,
                      "distinct_prompt_sha256": len(kinds), "not_invoked": not_inv})
    total_rec = sum(s["records"] for s in stats)
    verdict = "FAIL" if fails else ("invalid" if invalids else "pass")
    res = {"verdict": verdict, "runs": len(stats), "total_chunk_records": total_rec,
           "gaps": len(fails), "failures": fails[:20],
           "invalid_count": len(invalids), "invalid": invalids[:5],
           "reuse_ok": all(s["distinct_prompt_sha256"] == 1 for s in stats),
           "stats": stats,
           "note": "提示词复用与逐片记录；not_invoked ⇒ invalid（不得视为通过）"}
    (R / "quality" / "prompt_reuse.yaml").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = check()
    print(json.dumps({k: v for k, v in r.items() if k != "stats"}, ensure_ascii=False, indent=2))
    sys.exit(1 if r["verdict"] == "FAIL" else 0)
