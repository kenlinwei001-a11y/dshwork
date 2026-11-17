#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分桶判定 v2：阈值只从规则集读；标准未规定 → NOT_APPLICABLE（不再借用他标准阈值）。

用法: python3 bucket_judge_v2.py --out <run> --packs <包目录...> --docs <记录目录> [--nd-policy pass]
输出: machine/bucket_judgement_v2.json
原则:
  ① 每条检查必须有对应规则；没有 → NOT_APPLICABLE + reason="标准未规定"
  ② 阈值/算子一律取 rule.predicate，禁止代码里写死
  ③ 取不到值 → UNVERIFIABLE（区分子类归因）
"""
import argparse,glob,json,os,re,sys
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
try:
    import value_normalize as VN
    _VNT=VN.load()
except Exception:
    VN=None; _VNT={}

CONCEPT={'相关系数':['相关系数'],'空白吸光度':['空白','吸光度'],'空白值':['空白'],'空白个数':['空白','2个'],'空白个数':['空白','至少做','2个'],
         '平行偏差':['平行','相对偏差'],'加标回收率':['回收率'],'中间点误差':['中间点','相对误差']}
BIND={'HJ636':'总氮','HJ535':'氨氮','HJ84':'硝酸根','HJ671':'总磷'}

def load_rules(pk):
    return [json.loads(l) for l in open(os.path.join(pk,'rules.jsonl'),encoding='utf-8') if l.strip()]

UNIT_HINT={'空白个数':'个','空白值':'mg/L','空白吸光度':'1','相关系数':'1',
           '平行偏差':'%','加标回收率':'%','中间点误差':'%'}
def rule_for(rules, concept):
    kws=CONCEPT[concept]; uh=UNIT_HINT.get(concept)
    cand=[r for r in rules if r.get('predicate') and all(k in (r.get('requirement') or '') for k in kws)]
    if uh:
        exact=[r for r in cand if str((r.get('predicate') or {}).get('unit'))==uh]
        if exact: return exact[0]
        if concept in ('空白值','空白个数','空白吸光度'): return None   # 单位不符不得顶替
    return cand[0] if cand else None

def _flat(t):
    import re as _r
    return _r.sub(r'<[^>]+>',' ',t)

def extract(concept,text):
    text=_flat(text)
    if concept=='相关系数':
        for p in (r'相关系数[^\d]{0,14}([01]\.\d{3,5})', r'[RrＲx×γ]\s*[=＝:]\s*([01]\.\d{3,5})'):
            m=re.search(p,text)
            if m: return float(m.group(1)),f'相关系数 {m.group(1)}'
    if concept=='空白个数':
        n=len(set(re.findall(r'空白样品\s*(\d)',text)))
        if n: return float(n),f'空白样品 {n} 个'
        return None,'未找到空白样品编号'
    if concept in ('空白吸光度','空白值'):
        for pat in (r'平均值\s*Ab[:：]\s*([01]\.\d{3})',            # HJ636 实测 Ab
                    r'空白吸光度[^\n]{0,20}?([01]\.\d{3})',
                    r'空白[^\n|]{0,12}\|[^|]*\|\s*([01]\.\d{3})'):  # 空白行 As
            m=re.search(pat,text)
            if m: return float(m.group(1)),f'空白实测 {m.group(1)}'
        if 'ND' in text: return ('ND',None),'空白报 ND（低于检出限）'
        return None,'记录只声明上限，无实测值'
    if concept=='平行偏差':
        v=[float(x) for x in re.findall(r'相对偏差[:：]?\s*([\d.]+)\s*%',text)]
        if v: return max(v),f'相对偏差 max={max(v)}（全部 {v}）'
    if concept=='加标回收率':
        v=[float(x) for x in re.findall(r'回收率[:：]?\s*([\d.]+)\s*%',text)]
        if v: return (min(v),max(v)),f'回收率 {v}'
    if concept=='中间点误差':
        for pat in (r'曲线中间点[^\n]{0,60}?(?:相对误差|相对偏差)[:：]?\s*([\d.]+)\s*%',
                    r'中间点[^\n]{0,40}?(?:相对误差|相对偏差)[:：]?\s*([\d.]+)\s*%'):
            m=re.search(pat,text)
            if m: return float(m.group(1)),f'中间点 {m.group(1)}%'
    return None,'记录中未找到'

def cmp_ok(op,val,got):
    if isinstance(got,tuple): a,b=got
    else: a=b=got
    if op=='<=': return b<=val
    if op=='>=': return a>=val
    if op=='<':  return b<val
    if op=='>':  return a>val
    if op=='==': return a==val
    if op=='between': return a>=val[0] and b<=val[1]
    return None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True)
    ap.add_argument('--packs',nargs='+',required=True); ap.add_argument('--docs',required=True)
    ap.add_argument('--nd-policy',default='pass'); a=ap.parse_args(); O=a.out
    packs={os.path.basename(p.rstrip('/')):load_rules(p) for p in a.packs}
    texts={}
    for f in glob.glob(os.path.join(a.docs,'*.md')):
        texts[os.path.basename(f)]=open(f,encoding='utf-8',errors='ignore').read()
    out=[]
    def enum_check(std,concept,raw,allowed,rules_note):
        if VN is None:
            return {'standard':std,'concept':concept,'value':raw,'verdict':'UNVERIFIABLE',
                    'basis':'值归一化模块不可用'}
        rr=VN.eval_in(raw,allowed,_VNT,on_unmapped='UNVERIFIABLE')
        return {'standard':std,'concept':concept,'value':raw,'allowed':allowed,
                'verdict':rr['verdict'],'mapped':rr.get('mapped'),'basis':rr['basis'],
                'reason':rules_note}
    for std,rules in packs.items():
        kw=next((v for k,v in BIND.items() if k in std),'')
        doc=next((t for n,t in texts.items() if kw and kw in n), None)
        concepts=['相关系数','空白吸光度','平行偏差','加标回收率','中间点误差']
        if 'HJ84' in std: concepts=['相关系数','空白个数','空白值','平行偏差','加标回收率','中间点误差']
        for concept in concepts:
            r=rule_for(rules,concept)
            if not r:
                out.append({'standard':std,'concept':concept,'verdict':'NOT_APPLICABLE',
                            'reason':'标准未规定（旧判定曾借用其他标准的阈值）'}); continue
            val,note=extract(concept,doc or '')
            p=r['predicate']
            if val is None:
                key = r.get('criticality')=='KEY'
                mk  = r.get('missing_kind') or 'FIELD_ABSENT'
                if key and mk=='DOC_ABSENT':
                    vv,basis='PENDING_EVIDENCE','KEY 要素：整份文档未上传，补证后可重判'
                elif key and mk=='UNOBSERVABLE_WITH_TEMPLATE':
                    vv,basis='UNVERIFIABLE','KEY 要素：模板结构上无此栏，责任在模板而非实验室'
                elif key:
                    vv,basis='FAIL','KEY 要素：文档在册但该记的未记，属记录缺陷'
                else:
                    vv,basis='UNVERIFIABLE','普通要素缺证挂起'
                out.append({'standard':std,'concept':concept,'verdict':vv,
                            'rule_id':r['rule_id'],'threshold':p.get('value'),'reason':note,
                            'criticality':r.get('criticality'),'missing_kind':mk,
                            'evidence_state':'ABSENT','basis':basis}); continue
            if isinstance(val,tuple) and val[0]=='ND':
                ok = (a.nd_policy=='pass' and p.get('op') in ('<=','<'))
                out.append({'standard':std,'concept':concept,'rule_id':r['rule_id'],'op':p.get('op'),
                            'threshold':p.get('value'),'value':'ND','verdict':'PASS' if ok else 'UNVERIFIABLE',
                            'reason':'据 ND 推定（低于检出限）' if ok else 'ND 且阈值非上限类'}); continue
            uncertain = ('不可辨' in (note or '')) or ('转引' in (note or '')) or ('见' in (note or '') and '记录表' in (note or ''))
            if uncertain:
                out.append({'standard':std,'concept':concept,'rule_id':r['rule_id'],
                            'threshold':p.get('value'),'value':val,'verdict':'UNVERIFIABLE',
                            'evidence_state':'UNCERTAIN','reason':note}); continue
            ok=cmp_ok(p.get('op'),p.get('value'),val)
            out.append({'standard':std,'concept':concept,'rule_id':r['rule_id'],
                        'op':p.get('op'),'threshold':p.get('value'),'value':val,
                        'verdict':'PASS' if ok else 'FAIL','reason':note,
                        'evidence_state':'MEASURED','criticality':r.get('criticality')})
    from collections import Counter
    json.dump({'items':out,'counts':dict(Counter(x['verdict'] for x in out))},
              open(os.path.join(O,'machine','bucket_judgement_v2.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(f"{'标准':12s}{'检查项':10s}{'规则':22s}{'阈值':10s}{'实测':10s}{'判定'}")
    for x in out:
        print(f"{x['standard']:12s}{x['concept']:10s}{str(x.get('rule_id') or '—'):22s}"
              f"{str(x.get('threshold') or '—'):10s}{str(x.get('value') or '—'):10s}{x['verdict']}")
    print("\n汇总:",dict(Counter(x['verdict'] for x in out)))
    return 0
if __name__=='__main__': sys.exit(main())
