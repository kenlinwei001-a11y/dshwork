#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用节点门禁：只认 trail.jsonl 里「该节点最后一条 verify 记录」。

用法:
  python3 check_gate.py --out <运行目录> --node <节点名> [--allow-attested]

判据（与 validate_node.py 的 trail_present 同一口径）：
  - 没有 trail.jsonl        → FAIL（视为未执行）
  - 该节点没有 verify 记录   → FAIL
  - 最后一条 pass=false      → FAIL，并打印 missing/detail
  - 最后一条 pass=true       → PASS

为什么只认「最后一条」：旧的成功记录不能掩盖新的失败。
"""
import argparse
import json
import os
import sys


def last_verify(out, node):
    p = os.path.join(out, 'trail.jsonl')
    if not os.path.exists(p):
        return None, 'trail.jsonl 不存在（视为未执行）'
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
    if last is None:
        return None, f'没有 {node} 的 verify 记录'
    return last, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--node', required=True)
    ap.add_argument('--allow-attested', action='store_true')
    ap.add_argument('--require', nargs='*', default=[],
                    help='该节点声明产出的文件（相对运行目录），缺一即 FAIL')
    a = ap.parse_args()

    missing_out = [p for p in (a.require or []) if not os.path.exists(os.path.join(a.out, p))]
    if missing_out:
        print(json.dumps({'gate': 'FAIL', 'node': a.node,
                          'reason': '声明的产出不存在', 'missing_outputs': missing_out},
                         ensure_ascii=False))
        return 1

    rec, err = last_verify(a.out, a.node)
    if rec is None:
        print(json.dumps({'gate': 'FAIL', 'node': a.node, 'reason': err}, ensure_ascii=False))
        return 1

    ok = bool(rec.get('pass'))
    attested = bool(rec.get('attested'))
    if attested and not a.allow_attested:
        print(json.dumps({'gate': 'FAIL', 'node': a.node,
                          'reason': '留痕为补录（artifact_exists），非本次执行',
                          'hint': '确认后加 --allow-attested'}, ensure_ascii=False))
        return 1
    out = {'gate': 'PASS' if ok else 'FAIL', 'node': a.node,
           'pass': ok, 'at': rec.get('at'), 'attested': attested}
    for k in ('missing', 'detail', 'counts'):
        if k in rec:
            out[k] = rec[k]
    print(json.dumps(out, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
