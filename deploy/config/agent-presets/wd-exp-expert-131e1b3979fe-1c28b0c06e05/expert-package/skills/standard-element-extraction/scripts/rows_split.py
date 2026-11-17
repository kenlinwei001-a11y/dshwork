#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 01-clauses 生成 machine/rows.json 并切片（elements/rules 节点用）。

用法: python3 rows_split.py --out <run> [--size 20]
产出: machine/rows.json、machine/rows-slices/0001.json …
"""
import argparse,json,os,sys
ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); ap.add_argument('--size',type=int,default=20)
a=ap.parse_args(); O=a.out
cl=json.load(open(os.path.join(O,'01-clauses.json'),encoding='utf-8'))
rows=[{'row':i+1,'clause':str(c.get('clause')),'quote':(c.get('quote') or '')[:200],
       'modality':c.get('modality'),'type':c.get('type')} for i,c in enumerate(cl.get('clause_registry') or [])]
os.makedirs(os.path.join(O,'machine','rows-slices'),exist_ok=True)
json.dump({'standard_id':cl.get('standard_id'),'total':len(rows),'rows':rows},
          open(os.path.join(O,'machine','rows.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
n=0
for i in range(0,len(rows),a.size):
    n+=1
    json.dump(rows[i:i+a.size],open(os.path.join(O,'machine','rows-slices',f'{n:04d}.json'),'w',encoding='utf-8'),
              ensure_ascii=False,indent=1)
print(json.dumps({'rows':len(rows),'slices':n,'slice_size':a.size},ensure_ascii=False)); sys.exit(0)
