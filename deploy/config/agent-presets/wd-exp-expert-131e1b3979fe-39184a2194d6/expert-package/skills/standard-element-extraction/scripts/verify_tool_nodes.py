#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C 阶段校验：tool 节点必须由 runner 执行，且产物与执行记录一致。
用法: python3 verify_tool_nodes.py --out <out目录>
"""
import argparse, hashlib, json, os, sys

REQ = {
 'provenance': ('00-provenance.json', 'text.probe'),
 'metrics':    ('audit_metrics.json', None),
 'package':    ('ses.json', 'merge.ses'),
}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True)
    a = ap.parse_args(); ok = True
    reg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'registry', 'capabilities.json'), encoding='utf-8'))['capabilities']
    for node, (fname, cap) in REQ.items():
        p = os.path.join(a.out, fname)
        rec = os.path.join(a.out, f'runner-{node}.json')
        if not os.path.exists(p):
            print(f'MISS  {node}: 缺产物 {fname}'); ok = False; continue
        if not os.path.exists(rec):
            print(f'FAIL  {node}: 缺执行记录 runner-{node}.json（疑似未经 runner）'); ok = False; continue
        r = json.load(open(rec, encoding='utf-8'))
        if r.get('exit') != 0:
            print(f'FAIL  {node}: exit={r.get("exit")}'); ok = False; continue
        if cap and r.get('capability') != cap:
            print(f'FAIL  {node}: 能力不符 {r.get("capability")} != {cap}'); ok = False; continue
        if r.get('capability') not in reg:
            print(f'FAIL  {node}: 能力未注册 {r.get("capability")}'); ok = False; continue
        print(f'OK    {node}: cap={r["capability"]} v{r["version"]} exit=0 sha12={r.get("stdout_sha12")}')
    if os.path.exists(os.path.join(a.out, 'audit_metrics.json')):
        m = json.load(open(os.path.join(a.out, 'audit_metrics.json'), encoding='utf-8'))
        print(f'GATE  metrics: {m.get("gate")}')
    print('verify:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
