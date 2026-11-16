#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给缺口打 pending_class（v1.3）。用法: --rules 03.json [--write]"""
import argparse, json, sys, collections
MAP={'GAP-REF':'PENDING_REF','GAP-DATA':'PENDING_DATA','GAP-EXTERNAL':'PENDING_DOC',
     'GAP-CONFLICT':'REGISTERED_CONFLICT','GAP-AMB':'LAB_POLICY','GAP-PERF':'LAB_POLICY'}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--rules',required=True); ap.add_argument('--write',action='store_true')
    a=ap.parse_args(); d=json.load(open(a.rules,encoding='utf-8'))
    for g in d.get('gaps') or []:
        gid=g.get('gap_id') or ''
        cls=MAP.get(g.get('type'),'PENDING_USER')
        desc=str(g.get('description') or '')
        if g.get('type')=='GAP-AMB' and '参考' in desc: cls='PENDING_USER'   # 效力二义：真裁决
        elif g.get('type')=='GAP-AMB' and ('高于' in desc or '超' in desc): cls='REGISTERED_CONFLICT'
        if gid.startswith('GAP-CONFLICT'): cls='REGISTERED_CONFLICT'
        g['pending_class']=cls
    if a.write: json.dump(d,open(a.rules,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    c=collections.Counter(g['pending_class'] for g in d.get('gaps') or [])
    print(json.dumps(dict(c),ensure_ascii=False))
    return 0
if __name__=='__main__': sys.exit(main())
