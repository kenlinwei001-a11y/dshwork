#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""节点间交接只传引用：生成 handoff_state.json（不转述内容）。
用法: python3 handoff_state.py --out <out> --next <node> --changed clauses:81
"""
import argparse, json, os, sys

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True)
    ap.add_argument('--next', default=''); ap.add_argument('--changed', action='append', default=[])
    a = ap.parse_args(); O = a.out
    dv = json.load(open(os.path.join(O, 'derived.json'), encoding='utf-8')) if os.path.exists(os.path.join(O, 'derived.json')) else {}
    st = {'out': os.path.abspath(O), 'next': a.next, 'changed': a.changed,
          'derived': dv.get('counts') or {}, 'facts': os.path.join(os.path.abspath(O), 'facts.json'),
          'rows': os.path.join(os.path.abspath(O), 'rows.json'),
          'note': '下游直接读 facts/rows/derived；不要转述、不要重读视图'}
    json.dump(st, open(os.path.join(O, 'handoff_state.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({'handoff_state': st['derived'], 'next': a.next}, ensure_ascii=False)); return 0

if __name__ == '__main__':
    sys.exit(main())
