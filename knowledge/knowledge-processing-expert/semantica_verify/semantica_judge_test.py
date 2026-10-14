# -*- coding: utf-8 -*-
"""用 DeepSeek（经 Semantica llms 模块）判定主体对是否同一概念。
先在 17 组有人工标准答案的样本上测准确率。密钥只从环境变量读，绝不落盘。"""
import json, os, sys, re
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from semantica_env import load_env as _load_env
_load_env()  # 缺 key 直接退出，避免 provider 静默降级为空结果
WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"
OUT = PKG / "外部核验"
nodes = json.loads((PKG / "graph/nodes.yaml").read_text(encoding="utf-8"))
vals = {}
for n in nodes:
    vals.setdefault(n["subject"], []).append({"value": str(n["value"]), "unit": n.get("unit", ""), "section": n.get("section", "")})

API = os.environ["DEEPSEEK_API_KEY"]
if not API:
    print("NO KEY"); sys.exit(2)

from semantica.llms import DeepSeek
llm = DeepSeek(model="deepseek-chat", api_key=API)

SYS = """你是可研报告知识图谱的实体归一判官。给你若干「主体对」，每个含名称与各自取值。
判断两个主体是否指同一概念（同义/别名/同一指标）：
- SAME：同一概念（命名不同但指同一事物）
- DIFF：不同概念（字面相似但语义不同）
- UNKNOWN：信息不足
注意：取值相同不等于同一概念；取值不同也可能是同一概念（口径冲突）。
只输出 JSON 数组，每项 {"i":序号,"verdict":"SAME|DIFF|UNKNOWN","confidence":0-1,"reason":"不超过25字"}，不要任何其他文字。"""

def build(pairs):
    lines = []
    for i, (a, b) in enumerate(pairs):
        va = "；".join(f"{x['value']}{x['unit']}" for x in vals.get(a, [])[:3]) or "（无值）"
        vb = "；".join(f"{x['value']}{x['unit']}" for x in vals.get(b, [])[:3]) or "（无值）"
        lines.append(f'{i+1}. A="{a}" 值={va} || B="{b}" 值={vb}')
    return SYS + "\n\n主体对：\n" + "\n".join(lines)

def judge(pairs):
    raw = llm.generate(build(pairs))
    txt = raw if isinstance(raw, str) else str(raw)
    m = re.search(r'\[[\s\S]*\]', txt)
    if not m: return {"error": txt[:200]}
    try: return json.loads(m.group(0))
    except Exception as e: return {"error": f"{e} :: {m.group(0)[:200]}"}

rev = json.loads((OUT / "dedup-review.yaml").read_text(encoding="utf-8"))
gt = [(e["a"], e["b"], e["verdict"]) for e in rev["entries"]]
res = judge([(a, b) for a, b, _ in gt])
if isinstance(res, dict):
    print("判定失败:", res); sys.exit(1)

MAP = {"confirmed_alias": "SAME", "false_positive": "DIFF", "needs_review": "UNKNOWN"}
ok = 0; detail = []
for i, (a, b, v) in enumerate(gt):
    got = next((x for x in res if x.get("i") == i + 1), None)
    if not got: continue
    pred = got.get("verdict", "?")
    gold = "SAME" if v == "confirmed_alias" else ("DIFF" if v == "false_positive" else "UNKNOWN")
    hit = pred == gold
    ok += hit
    detail.append({"a": a, "b": b, "human": v, "gold": gold, "llm": pred,
                   "hit": hit, "confidence": got.get("confidence"), "reason": got.get("reason", "")})
print(f"LLM 判官 vs 人工标准答案：{ok}/{len(detail)} = {ok/len(detail):.0%}")
for d in detail:
    flag = "OK " if d["hit"] else "MISS"
    print(f"  {flag} 人工={d['gold']:7s} LLM={d['llm']:7s} conf={d['confidence']}  {d['a']} ~ {d['b']}  | {d['reason']}")
(OUT / "llm-judge-accuracy.yaml").write_text(json.dumps({
  "judge": "semantica.llms.DeepSeek(model=deepseek-chat)",
  "ground_truth": "处理者人工复核的 17 组（dedup-review.yaml）",
  "accuracy": round(ok / len(detail), 3), "n": len(detail), "detail": detail,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n已写 llm-judge-accuracy.yaml")


try:
    from semantica_metrics import append_history as _append_history
    _append_history(str(OUT), 'llm', {"accuracy": locals().get("acc") or (ok / len(detail) if 'detail' in dir() and detail else None), "n": len(detail) if 'detail' in dir() else None})
except Exception:
    pass
