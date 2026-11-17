#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用判定器：规则自带 requires/谓词，本脚本不认任何标准号或被测物名。

设计原则（与 bucket_judge_v2 的区别）：
  · 没有 BIND（标准→被测物）表，没有 CONCEPT（概念→关键词）表
  · 字段抽取模式只来自 contracts/fields.yaml
  · 规则通过 requires: [字段] 声明要什么；有 requires 才判，没有则跳过（并登记）
  · 关键性（KEY/NORMAL）× 缺证类型 → PASS/FAIL/PENDING_EVIDENCE/UNVERIFIABLE
用法:
  python3 judge_from_rules.py --packs <包目录...> --docs <文档目录> [--fields contracts/fields.yaml] [--out <dir>]
"""
import argparse,glob,json,os,re,sys
try:
    import yaml
except Exception:
    yaml=None

ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def norm_text(t):
    t=re.sub(r'<[^>]+>',' ',t)
    return re.sub(r'[ \t\u3000]+',' ',t)

def load_docs(d):
    out={}
    for p in sorted(glob.glob(os.path.join(d,'*.md'))):
        out[os.path.basename(p)]=norm_text(open(p,encoding='utf-8',errors='ignore').read())
    return out

def load_fields(path):
    if yaml is None: return {}
    return (yaml.safe_load(open(path,encoding='utf-8')) or {}).get('fields',{})

UNIT_ALIAS={'ug/L':'μg/L','ug/mL':'μg/mL'}
def extract(field,spec,docs):
    """返回 (value, unit, source_doc, quote, how)。取不到返回 (None,...)"""
    pats=spec.get('patterns') or []
    vals=[]
    for name,text in docs.items():
        for pat in pats:
            for m in re.finditer(pat,text):
                g=[x for x in m.groups() if x is not None]
                if not g: continue
                raw=g[0]; unit=g[1] if len(g)>1 else None
                v=None
                try: v=float(str(raw).replace('%',''))
                except ValueError: v=str(raw)
                q=text[max(0,m.start()-30):m.end()+20].strip()
                vals.append((v,UNIT_ALIAS.get(unit,unit),name,q,pat))
    if not vals: return (None,None,None,None,'未命中')
    agg=spec.get('agg','last')
    if isinstance(agg,list):
        nums=[x for x in vals if isinstance(x[0],(int,float))]
        if not nums: return (None,None,None,None,'非数值')
        return (min(nums[0] for _ in [0]) if False else (min(x[0] for x in nums), max(x[0] for x in nums)),
                nums[0][1],nums[0][2],nums[0][3],f'agg={agg}')
    do_agg={'max':max,'min':min,'first':lambda s:s[0],'last':lambda s:s[-1]}.get(agg or 'last',lambda s:s[-1])
    nums=[x for x in vals if isinstance(x[0],(int,float))] or vals
    pick=do_agg(nums) if nums else None
    if not pick: return (None,None,None,None,'非数值')
    return (pick[0],pick[1],pick[2],pick[3],f'agg={agg}')

def cmp_ok(op,target,value):
    if value is None: return None
    a,b=(value if isinstance(value,tuple) else (value,value))
    if op=='<=': return b<=target
    if op=='>=': return a>=target
    if op=='<':  return b<target
    if op=='>':  return a>target
    if op=='==': return a==target
    if op=='between': return target[0]<=a and b<=target[1]
    return None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--packs',nargs='+',required=True)
    ap.add_argument('--docs',required=True); ap.add_argument('--fields',default=os.path.join(ROOT,'contracts','fields.yaml'))
    ap.add_argument('--out',default=''); ap.add_argument('--allow-self-bootstrap',action='store_true')
    a=ap.parse_args()
    F=load_fields(a.fields); docs=load_docs(a.docs)
    rows=[]; skipped=[]
    def iter_rules(pk):
        jl=os.path.join(pk,'rules.jsonl'); js=os.path.join(pk,'03-rules.json')
        if os.path.exists(jl):
            for line in open(jl,encoding='utf-8'):
                if line.strip(): yield json.loads(line)
        elif os.path.exists(js):
            d=json.load(open(js,encoding='utf-8'))
            for r in (d.get('audit_rule_cards') or []): yield r
    for pk in a.packs:
        std=os.path.basename(pk.rstrip('/'))
        for r in iter_rules(pk):
            pred=r.get('predicate') or {}
            req=r.get('requires') or ([pred['field']] if pred.get('field') in F else [])
            if not req:
                skipped.append((std,r['rule_id'],'规则未声明 requires/未知字段')); continue
            got={f:extract(f,F[f],docs) for f in req if f in F}
            miss=[f for f,v in got.items() if v[0] is None]
            key=r.get('criticality')=='KEY'; mk=r.get('missing_kind') or 'FIELD_ABSENT'
            if miss:
                vv=('PENDING_EVIDENCE' if key and mk=='DOC_ABSENT'
                    else 'FAIL' if key else 'UNVERIFIABLE')
                rows.append({'standard':std,'rule_id':r['rule_id'],'category':r.get('category'),
                             'field':req[0],'missing':miss,'verdict':vv,'criticality':r.get('criticality'),
                             'basis':f'字段未取到 {miss}'}); continue
            f0=req[0]; val,unit,doc,q,how=got[f0]
            if not pred:  # 定性卡
                rows.append({'standard':std,'rule_id':r['rule_id'],'category':r.get('category'),
                             'field':f0,'value':val,'unit':unit,'doc':doc,'quote':q,
                             'verdict':'PENDING_JUDGE','basis':'定性卡，交人判'}); continue
            target=pred.get('value')
            if not isinstance(target,(int,float,list)):
                rows.append({'standard':std,'rule_id':r['rule_id'],'category':r.get('category'),
                             'field':f0,'value':val,'unit':unit,'doc':doc,'quote':q,
                             'verdict':'UNVERIFIABLE','basis':f'阈值非数值（{target}），需按分析物/分档解析'}); continue
            ok=cmp_ok(pred.get('op'),target,val)
            rows.append({'standard':std,'rule_id':r['rule_id'],'category':r.get('category'),
                         'field':f0,'value':val,'unit':unit,'doc':doc,'quote':q,
                         'verdict':'PASS' if ok else 'FAIL','basis':f'{val} {pred.get("op")} {target}'})
    from collections import Counter
    c=Counter(x['verdict'] for x in rows)
    print(json.dumps({'judged':len(rows),'skipped_no_requires':len(skipped),
                      'verdicts':dict(c)},ensure_ascii=False))
    for x in rows:
        if x['verdict'] in ('FAIL','PENDING_EVIDENCE'):
            print(f"  {x['verdict']:16s} {x['standard']:12s} {x['rule_id']:22s} {x.get('field','')} {x['basis'][:50]}")
    for s in skipped[:5]: print(f"  SKIP {s[0]} {s[1]} — {s[2]}")
    if a.out:
        os.makedirs(a.out,exist_ok=True)
        json.dump({'items':rows,'skipped':skipped,'counts':dict(c)},
                  open(os.path.join(a.out,'judge_result.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    return 0

if __name__=='__main__': sys.exit(main())
