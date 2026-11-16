#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把大 JSON 行集切成小片，供模型一次只读一片（不读整份）。

用法: python3 split_rows.py --in machine/rows.json [--size 20] [--out machine/rows] [--key rows]
输出: <out>/0001.json ... + index.json {slices:[{file,count,from,to}],total}
"""
import argparse,json,os,sys
ap=argparse.ArgumentParser()
ap.add_argument('--in',dest='src',required=True); ap.add_argument('--out',dest='dst',default=None)
ap.add_argument('--size',type=int,default=20); ap.add_argument('--key',default=None)
a=ap.parse_args()
try:
    d=json.load(open(a.src,encoding='utf-8'))
except Exception:
    d=[json.loads(l) for l in open(a.src,encoding='utf-8') if l.strip()]   # JSONL 支持
rows = d.get(a.key) if a.key and isinstance(d,dict) else (d if isinstance(d,list) else None)
if rows is None:
    for k,v in (d.items() if isinstance(d,dict) else []):
        if isinstance(v,list): rows, a.key = v, k; break
if rows is None: print(json.dumps({'error':'找不到行集'})); sys.exit(2)
dst=a.dst or os.path.join(os.path.dirname(a.src) or '.', os.path.splitext(os.path.basename(a.src))[0]+'-slices')
os.makedirs(dst,exist_ok=True)
idx={'source':a.src,'key':a.key,'total':len(rows),'size':a.size,'slices':[]}
for i in range(0,len(rows),a.size):
    no=len(idx['slices'])+1; fn=f'{no:04d}.json'
    chunk=rows[i:i+a.size]
    json.dump(chunk,open(os.path.join(dst,fn),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    idx['slices'].append({'file':fn,'count':len(chunk),'from':i,'to':i+len(chunk)-1})
json.dump(idx,open(os.path.join(dst,'index.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps({'slices':len(idx['slices']),'total':len(rows),'dir':dst}))
