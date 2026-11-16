#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""质量审计抽样：脚本随机抽 N 条判定，供模型只读这一小份（不读整份 findings）。

用法: python3 sample_findings.py --out <run> [--findings machine/report_findings.json] [--n 5] [--seed 42]
输出: machine/audit_samples.json  {source,total,sampled:[{rule_id,verdict,message,quote,clause}]}
"""
import argparse,hashlib,json,os,random,sys
def load(p,d=None):
    return json.load(open(p,encoding='utf-8')) if os.path.exists(p) else d
ap=argparse.ArgumentParser()
ap.add_argument('--out',required=True); ap.add_argument('--findings',default=None)
ap.add_argument('--n',type=int,default=5); ap.add_argument('--seed',type=int,default=42)
a=ap.parse_args(); O=a.out
cands=[a.findings] if a.findings else [
  'machine/report_findings.json','machine/process_findings.json','audit_results.json']
src=next((p for p in cands if os.path.exists(os.path.join(O,p))),None)
if not src: print(json.dumps({'error':'找不到判定文件'})); sys.exit(2)
d=load(os.path.join(O,src))
items=d.get('items') or d.get('findings') or (d if isinstance(d,list) else [])
if not items: print(json.dumps({'error':f'{src} 无判定项'})); sys.exit(2)
random.Random(a.seed).shuffle(items)
samp=[{'rule_id':x.get('rule_id'),'verdict':x.get('verdict'),
       'message':(x.get('message') or '')[:120],
       'quote':(x.get('report_span') or x.get('record_span') or {}).get('quote'),
       'clause':(x.get('std_anchor') or x.get('anchor') or {}).get('clause')}
      for x in items[:a.n]]
doc={'source':src,'total':len(items),'n':len(samp),'seed':a.seed,'sampled':samp}
json.dump(doc,open(os.path.join(O,'machine','audit_samples.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps({'source':src,'total':len(items),'sampled':len(samp),
                  'verdicts':[s['verdict'] for s in samp]},ensure_ascii=False))
