#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 packed YAML 拆成机器友好格式：rules.jsonl + meta.json (+ graph.jsonl)。

理由：nodes/edges 占六成体积而判定用不到；JSONL 可按行切片、按行 diff、按行追加。
用法: python3 pack_split.py --out <run> [--dest <目录>] [--graph]
产出: <dest>/rules.jsonl  meta.json  [graph.jsonl]
"""
import argparse,json,os,sys,hashlib
import yaml
ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True)
ap.add_argument('--dest',default=None); ap.add_argument('--graph',action='store_true'); a=ap.parse_args()
O=a.out; p=os.path.join(O,'machine','sop-graph.packed.yaml')
d=yaml.safe_load(open(p,encoding='utf-8'))
std=str(d.get('standard_id') or '').strip() or os.path.basename(O.rstrip('/'))
dest=a.dest or os.path.join('docs','判定包',std)
os.makedirs(dest,exist_ok=True)
with open(os.path.join(dest,'rules.jsonl'),'w',encoding='utf-8') as f:
    for r in d.get('rules') or []: f.write(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n')
meta={'standard_id':std,'source_fingerprint':d.get('source_fingerprint'),
      'method_family':d.get('method_family'),'coverage_thresholds':d.get('coverage_thresholds'),
      'judging_contract':d.get('judging_contract'),'reference_register':d.get('reference_register'),
      'gaps':d.get('gaps'),'counts':d.get('counts'),
      'clauses':d.get('clauses')}
json.dump(meta,open(os.path.join(dest,'meta.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
if a.graph:
    with open(os.path.join(dest,'graph.jsonl'),'w',encoding='utf-8') as f:
        for n in d.get('nodes') or []: f.write(json.dumps({'kind':'node',**n},ensure_ascii=False,separators=(',',':'))+'\n')
        for e in d.get('edges') or []: f.write(json.dumps({'kind':'edge',**e},ensure_ascii=False,separators=(',',':'))+'\n')
sz=lambda x: os.path.getsize(os.path.join(dest,x))
print(json.dumps({'standard':std,'dest':dest,'rules':len(d.get('rules') or []),
 'rules_jsonl':sz('rules.jsonl'),'meta_json':sz('meta.json'),
 'graph_jsonl':sz('graph.jsonl') if a.graph else None,
 'yaml_bytes':os.path.getsize(p)},ensure_ascii=False))
