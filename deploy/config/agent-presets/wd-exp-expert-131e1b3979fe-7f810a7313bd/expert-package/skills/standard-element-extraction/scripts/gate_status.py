#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前端一次取全量门禁状态：哪些节点已过、哪些能开始、为什么不能开始。

用法:
  python3 gate_status.py --out <运行目录> [--gates contracts/gates.json]

输出（exit 0 恒定，状态在 JSON 里；前端按 ready 决定按钮启用）：
  {
    "out": "...",
    "gates": { "<node>": {pass, at, attested, missing_outputs, reason} },
    "ready": { "<node>": bool },          // 上游门禁全过 且 自身未完成
    "done":  [ ... ],                     // 已过门禁的节点
    "blocked_reasons": { "<node>": [ ... ] },
    "all_green": bool
  }

规则（与 check_gate.py 同一口径）：
  - 无 trail.jsonl 或无该节点 verify 记录 → 未完成
  - 只认该节点最后一条 verify 记录；pass=false 即失败
  - requires_outputs 缺一即失败（产物不在 = 没跑成）
  - 补录留痕（attested=true）不计为完成
"""
import argparse
import json
import os
import sys


def load(p, d=None):
    if not os.path.exists(p):
        return d
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def last_verify(out, node):
    p = os.path.join(out, 'trail.jsonl')
    if not os.path.exists(p):
        return None
    last = None
    with open(p, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get('step') == 'verify' and r.get('node') == node:
                last = r
    return last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--gates', default='contracts/gates.json')
    a = ap.parse_args()
    O = a.out
    spec = load(a.gates, {}) or {}
    nodes = spec.get('nodes') or []

    gates, ready, done, blocked = {}, {}, [], {}
    for n in nodes:
        node = n['node']
        rec = last_verify(O, node)
        missing_out = [p for p in (n.get('requires_outputs') or [])
                       if not os.path.exists(os.path.join(O, p))]
        reasons = []
        if rec is None:
            reasons.append('无 verify 记录（视为未执行）')
        elif not rec.get('pass'):
            reasons.append(f'最后一条 verify 未通过：{rec.get("detail") or rec.get("missing") or "pass=false"}')
        elif rec.get('attested'):
            reasons.append('留痕为补录（artifact_exists），非本次执行')
        if missing_out:
            reasons.append(f'缺少产物：{missing_out}')

        ok = not reasons
        gates[node] = {
            'label': n.get('label'),
            'pass': ok,
            'at': (rec or {}).get('at'),
            'attested': bool((rec or {}).get('attested')),
            'missing_outputs': missing_out,
            'reason': None if ok else '；'.join(reasons),
        }
        if ok:
            done.append(node)

    # 过期判定：上游记录比本节点新，或上游已失效 → 本节点结论基于旧上游
    for n in nodes:
        node = n['node']
        ups = n.get('requires_gates') or []
        stale = False
        why = []
        for u in ups:
            ug = gates.get(u, {})
            if not ug.get('pass'):
                stale = True; why.append(f'上游 {u} 未过门禁')
                continue
            if (gates[node].get('at') or '') < (ug.get('at') or ''):
                stale = True; why.append(f'上游 {u} 在本节点之后重跑过')
        gates[node]['stale'] = bool(stale) and bool(gates[node].get('pass'))
        if gates[node]['stale']:
            gates[node]['stale_reason'] = '；'.join(why)

    # 可开始 = 上游门禁全过 且 自身未完成
    for n in nodes:
        node = n['node']
        if gates[node]['pass']:
            ready[node] = False
            continue
        ups = n.get('requires_gates') or []
        blocked_up = [u for u in ups if not gates.get(u, {}).get('pass')]
        ready[node] = not blocked_up
        if blocked_up:
            blocked[node] = [f'上游未过门禁：{blocked_up}']

    all_green = all(gates[n['node']]['pass'] for n in nodes)
    out = {
        'out': O,
        'gates': gates,
        'ready': ready,
        'done': done,
        'blocked_reasons': blocked,
        'all_green': all_green,
        'hint': '按钮规则：ready=false 且不在 done 中的节点，禁用「开始」并显示 reason；不得默认放行',
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
