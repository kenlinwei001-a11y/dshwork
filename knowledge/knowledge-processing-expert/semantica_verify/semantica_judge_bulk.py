# -*- coding: utf-8 -*-
"""批量：用 DeepSeek 判定 1081 组 diff_value 是否同一概念。密钥仅从环境变量读。"""
import json, os, re, sys, time
from pathlib import Path
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from semantica_env import load_env as _load_env
_load_env()  # 缺 key 直接退出，避免 provider 静默降级为空结果
WS = Path(__file__).resolve().parent.parent
PKG = WS / "知识资产-上财大数据研究中心可研"; OUT = PKG / "外部核验"
nodes = json.loads((PKG / "graph/nodes.yaml").read_text(encoding="utf-8"))
vals = {}
for n in nodes:
    vals.setdefault(n["subject"], []).append(f'{n["value"]}{n.get("unit","")}')
ded = json.loads((OUT / "dedup-candidates.yaml").read_text(encoding="utf-8"))
pairs = [(p["a"], p["b"], p["similarity"]) for p in ded["buckets"]["diff_value"]]
print("待判 pair:", len(pairs), flush=True)

API = os.environ["DEEPSEEK_API_KEY"]
if not API: print("NO KEY"); sys.exit(2)
from semantica.llms import DeepSeek
llm = DeepSeek(model="deepseek-chat", api_key=API)

SYS = """你是可研报告知识图谱的实体归一判官。判断两个主体名是否指同一概念。
- SAME：同一概念（简称/全称/同义表述/同一指标的不同写法）
- DIFF：不同概念（字面相似但语义不同，如"资产总额"vs"净资产总额"、"标准"vs"需求"）
- UNKNOWN：信息不足
判据要点：名称的语义角色必须一致（"标准/指标"≠"需求/总量"；不同年份≠同一概念；不同对象≠同一概念）。
只输出 JSON 数组，每项 {"i":序号,"verdict":"SAME|DIFF|UNKNOWN","confidence":0-1,"reason":"<=20字"}。不要其他文字。"""

def batch(ps, k=15):
    for i in range(0, len(ps), k): yield i, ps[i:i+k]

results = []
t0 = time.time()
for start, chunk in batch(pairs):
    lines = []
    for j, (a, b, sim) in enumerate(chunk):
        va = "；".join(vals.get(a, [])[:2]) or "无值"
        vb = "；".join(vals.get(b, [])[:2]) or "无值"
        lines.append(f'{j+1}. A="{a}"(值{va}) || B="{b}"(值{vb}) 字面相似度{sim}')
    prompt = SYS + "\n\n" + "\n".join(lines)
    got = None
    for attempt in range(3):
        try:
            raw = llm.generate(prompt)
            m = re.search(r'\[[\s\S]*\]', raw if isinstance(raw, str) else str(raw))
            if m: got = json.loads(m.group(0)); break
        except Exception as e:
            time.sleep(2 + attempt * 3)
    if not got:
        for j, (a, b, sim) in enumerate(chunk):
            results.append({"a": a, "b": b, "similarity": sim, "verdict": "ERROR", "confidence": None, "reason": ""})
        continue
    for j, (a, b, sim) in enumerate(chunk):
        it = next((x for x in got if x.get("i") == j + 1), None)
        results.append({"a": a, "b": b, "similarity": sim,
                        "verdict": (it or {}).get("verdict", "MISSING"),
                        "confidence": (it or {}).get("confidence"),
                        "reason": (it or {}).get("reason", "")})
    done = start + len(chunk)
    if done % 150 < 15:
        print(f"  {done}/{len(pairs)}  {round(time.time()-t0)}s", flush=True)

from collections import Counter
cnt = Counter(r["verdict"] for r in results)
same = [r for r in results if r["verdict"] == "SAME"]
print("判定分布:", dict(cnt), flush=True)
(OUT / "llm-subject-alignment.yaml").write_text(json.dumps({
  "judge": "semantica.llms.DeepSeek(model=deepseek-chat)",
  "calibration": {"accuracy_on_17_ground_truth": 0.71,
                  "same_precision": 0.583, "diff_precision": 1.0,
                  "bias": "过度合并：5/5 错误均为 DIFF/UNKNOWN 被判成 SAME。故 DIFF 可信、SAME 仅作候选"},
  "total": len(results), "distribution": dict(cnt), "results": results,
  "same_candidates": same,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print("已写 llm-subject-alignment.yaml | SAME 候选", len(same), flush=True)
