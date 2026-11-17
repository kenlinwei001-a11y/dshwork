#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽取验收（**不是判定**）：证明抽出来的规则能被判据驱动跑通。

只回答三个问题，不出 PASS/FAIL：
  ① 可判定条数：kind∈{result,parameter} 且四条件齐（requires/predicate/evidence/anchor）
  ② 跳过率：requires 缺失或字段未定义导致无法取值的比例
  ③ 字段缺口：规则要求的字段在 fields.yaml 里没有定义的清单

产出: machine/extraction_acceptance.json
用法: python3 extraction_acceptance.py --packs <包...> --fields contracts/fields.yaml [--out <dir>]
"""
import argparse,json,os,sys,yaml

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--packs',nargs='+',required=True)
    ap.add_argument('--fields',required=True); ap.add_argument('--out',default=''); a=ap.parse_args()
    F=set(yaml.safe_load(open(a.fields,encoding='utf-8'))['fields'])
    rows=[]; miss_field=set(); skipped=0; judgeable=0; total=0
    for pk in a.packs:
        std=os.path.basename(pk.rstrip('/'))
        p=os.path.join(pk,'rules.jsonl')
        if not os.path.exists(p): continue
        for l in open(p,encoding='utf-8'):
            if not l.strip(): continue
            r=json.loads(l); total+=1
            req=r.get('requires') or []
            und=[f for f in req if f not in F]
            miss_field.update(und)
            ok = (r.get('kind') in ('result','parameter')
                  and req and not und and r.get('predicate')
                  and (r.get('check_targets') or r.get('target')) and r.get('clause'))
            if ok: judgeable+=1
            else: skipped+=1
            rows.append({'standard':std,'rule_id':r['rule_id'],'kind':r.get('kind'),
                         'judgeable':bool(ok),'requires':req,'undefined_fields':und})
    res={'total_rules':total,'judgeable':judgeable,
         'skip_rate':round(skipped/max(total,1),3),
         'undefined_fields':sorted(miss_field),
         'note':'本文件只证明"规则可被判据驱动"，不含 verdict；判定归审核专家'}
    print(json.dumps({k:res[k] for k in ('total_rules','judgeable','skip_rate','undefined_fields')},ensure_ascii=False))
    if a.out:
        os.makedirs(os.path.join(a.out,'machine'),exist_ok=True)
        json.dump({'summary':res,'items':rows},
                  open(os.path.join(a.out,'machine','extraction_acceptance.json'),'w',encoding='utf-8'),
                  ensure_ascii=False,indent=1)
        print("  →",os.path.join(a.out,'machine','extraction_acceptance.json'))
    return 0

if __name__=='__main__': sys.exit(main())
