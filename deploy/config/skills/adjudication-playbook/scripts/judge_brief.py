#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给判定 agent 的作业单：只出"模型该判的"，不含"脚本已判的"。

用法: python3 judge_brief.py --out <run> [--pack machine/sop-graph.packed.yaml] [--slice 8]
输出:
  machine/judge_tasks.jsonl   只含 qualitative=true 的规则（每行一条，带 quote 要求）
  machine/judge_brief.md      人读/agent 读的作业单（分片，≤slice 条/片）
  machine/judge_slices/00N.md 单片
原则: 谓词规则（predicate 非空）**不进作业单**——那些由 eval_slots 判。
"""
import argparse,json,os,sys
import yaml

ap=argparse.ArgumentParser()
ap.add_argument('--out',required=True)
ap.add_argument('--pack',default='machine/sop-graph.packed.yaml')
ap.add_argument('--slice',type=int,default=8)
ap.add_argument('--json-only',action='store_true',default=True,help='只出 JSON（默认；md 仅供排查）')
a=ap.parse_args(); O=a.out
p=os.path.join(O,a.pack)
if not os.path.exists(p): print(json.dumps({'error':f'{a.pack} 缺失'})); sys.exit(2)
d=yaml.safe_load(open(p,encoding='utf-8'))
rules=d.get('rules') or []
qual=[r for r in rules if r.get('qualitative')]
os.makedirs(os.path.join(O,'machine','judge_slices'),exist_ok=True)

with open(os.path.join(O,'machine','judge_tasks.jsonl'),'w',encoding='utf-8') as f:
    for r in qual:
        t={'rule_id':r['rule_id'],'category':r.get('category'),'clause':r.get('clause'),
           'requirement':r.get('requirement'),
           'ask':{'slot':(r.get('target') or {}).get('slot'),
                  'doc_type':(r.get('target') or {}).get('doc_type'),
                  'match_hints':(r.get('target') or {}).get('match_hints') or []},
           'allowed':['符合','不符合','缺证'],'forbid':'PASS（定性卡 NO_PASS）'}
        f.write(json.dumps(t,ensure_ascii=False)+'\n')

def render(items,idx,total):
    L=[f"# 判定作业单 {idx}/{total}｜{d.get('standard_id')}",
       "","> 只判定性卡。谓词规则已由脚本判定，**不在此单**。",
       "> 每条给出：verdict（符合/不符合/缺证）+ 一句理由 + **quote（原文连续片段）**。",
       "> 没把握就写「缺证」，不要猜。缺证请写 pending_class（PENDING_DATA/LAB_POLICY/PENDING_REF/PENDING_USER）。",""]
    for r in items:
        t=r.get('target') or {}
        L+= [f"## {r['rule_id']}（{r.get('category')}｜条款 {r.get('clause')}）",
             f"- 要求：{r.get('requirement')}",
             f"- 去哪找：{t.get('doc_type')}｜槽 {t.get('slot')}｜关键词 {'、'.join(t.get('match_hints') or []) or '—'}",
             "- 输出：`{\"rule_id\":\"...\",\"verdict\":\"符合|不符合|缺证\",\"quote\":\"...\",\"reason\":\"...\"}`",""]
    return "\n".join(L)

n=0
for i in range(0,len(qual),a.slice):
    n+=1
    json.dump(qual[i:i+a.slice],open(os.path.join(O,'machine','judge_slices',f'{n:03d}.json'),'w',encoding='utf-8'),
              ensure_ascii=False,indent=1)
if not a.json_only:
    open(os.path.join(O,'machine','judge_brief.md'),'w',encoding='utf-8').write(
        render(qual,1,(len(qual)+a.slice-1)//a.slice))
print(json.dumps({'rules_total':len(rules),'qualitative':len(qual),
                  'slices':n,'slice_size':a.slice,
                  'tasks_jsonl':'machine/judge_tasks.jsonl','slices_dir':'machine/judge_slices/',
                  'tasks_bytes':os.path.getsize(os.path.join(O,'machine','judge_tasks.jsonl'))},ensure_ascii=False))
