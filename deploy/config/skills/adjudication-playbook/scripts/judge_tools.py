#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定性卡判定的三段式：导出待判 → 切片给模型 → 合并回 findings（带校验）。

用法:
  judge_tools.py --out <run> --export            # pending_human → machine/pending_human.jsonl + 切片
  judge_tools.py --out <run> --split 10          # 按 10 条一片切到 machine/pending/
  judge_tools.py --out <run> --merge <judged.jsonl>
"""
import argparse,json,os,sys
def load(p,d=None):
    return json.load(open(p,encoding='utf-8')) if os.path.exists(p) else d
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True)
    ap.add_argument('--export',action='store_true'); ap.add_argument('--split',type=int)
    ap.add_argument('--merge'); ap.add_argument('--findings',default='machine/report_findings.json')
    a=ap.parse_args(); O=a.out
    fp=os.path.join(O,a.findings)
    f=load(fp)
    if f is None: print(json.dumps({'error':f'{a.findings} 缺失'})); return 2
    items=f.get('items') or f.get('findings') or []

    if a.export:
        pend=[{'rule_id':x.get('rule_id'),'label':(x.get('message') or '')[:60],
               'quote':(x.get('report_span') or {}).get('quote'),
               'clause':(x.get('std_anchor') or {}).get('clause'),
               'verdict_now':x.get('verdict'),
               'basis':x.get('basis')}
              for x in items if x.get('pending_class') or x.get('verdict')=='UNVERIFIABLE']
        with open(os.path.join(O,'machine','pending_human.jsonl'),'w',encoding='utf-8') as fh:
            for p in pend: fh.write(json.dumps(p,ensure_ascii=False)+'\n')
        print(json.dumps({'pending':len(pend),'written':'machine/pending_human.jsonl'})); return 0

    if a.split:
        pend=[json.loads(l) for l in open(os.path.join(O,'machine','pending_human.jsonl'),encoding='utf-8') if l.strip()]
        d=os.path.join(O,'machine','pending'); os.makedirs(d,exist_ok=True)
        n=0
        for i in range(0,len(pend),a.split):
            n+=1; json.dump(pend[i:i+a.split],open(os.path.join(d,f'{n:03d}.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
        print(json.dumps({'pending':len(pend),'slices':n,'dir':'machine/pending'})); return 0

    if a.merge:
        judged={}
        for line in open(a.merge,encoding='utf-8'):
            if not line.strip(): continue
            j=json.loads(line)
            if j.get('verdict') not in ('PASS','FAIL','UNVERIFIABLE'): continue
            judged[j['rule_id']]=j
        allowed={'UNVERIFIABLE'}   # 只有原本存疑的项可被判；不得改已定的 PASS/FAIL
        changed=refused=0
        for x in items:
            rid=x.get('rule_id'); j=judged.get(rid)
            if not j: continue
            if x.get('verdict') not in allowed:
                refused+=1; continue
            if x.get('verdict')=='FAIL' and j['verdict']=='PASS':
                refused+=1; continue
            x['verdict']=j['verdict']; x['message']=j.get('reason') or x.get('message')
            x['basis']='manual_qualitative'; x['judged_by']='审核专家'; changed+=1
        cnt={}
        for x in items: cnt[x['verdict']]=cnt.get(x['verdict'],0)+1
        f['counts']=cnt
        json.dump(f,open(fp,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
        print(json.dumps({'merged':changed,'refused':refused,'counts':cnt},ensure_ascii=False)); return 0
    print(json.dumps({'error':'需 --export / --split / --merge 之一'})); return 2
if __name__=='__main__': sys.exit(main())
