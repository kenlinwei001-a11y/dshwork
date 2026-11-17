#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判定入口：给 rule_id（可选给观测值），检索索引 → 比对 → 出 verdict + 依据。

用法:
  python3 judge_query.py --out <run> --rule ARC-C7-11.4-01            # 自动从证据取观测值
  python3 judge_query.py --out <run> --rule ARC-C7-11.4-01 --obs 3.3  # 显式给值
  python3 judge_query.py --out <run> --slot S045                      # 看该槽全部规则与判定
  python3 judge_query.py --out <run> --pending                        # 全量跑一遍，只列非 PASS

比对口径与 eval_slots 一致（数字先转 float；>= <= == in between）；
定性卡（predicate 为空）返回 needs_agent，不由本脚本判。
缺观测值 → UNVERIFIABLE（C8 例外，允许 FAIL）。
"""
import argparse,json,os,sqlite3,sys

def num(x):
    try: return float(x)
    except Exception: return None

def compare(op,val,obs):
    a,b=num(obs),num(val) if not isinstance(val,list) else None
    if op=='in':
        if isinstance(val,list):
            s=str(obs)
            if s in [str(v) for v in val]: return True,None
            part=[v for v in val if s and s in str(v)]
            if part: return None,f"表述过宽，可落入 {part}"
            return False,None
        return str(obs) in str(val),None
    if op=='between':
        if a is None or not isinstance(val,list) or len(val)!=2: return None,'区间或数值不可比'
        return (num(val[0])<=a<=num(val[1])),None
    if a is not None and b is not None:
        return {'>=':a>=b,'<=':a<=b,'>':a>b,'<':a<b,'==':a==b,'!=':a!=b}.get(op,False),None
    s=str(obs)
    return {'==':s==str(val),'!=':s!=str(val)}.get(op,False),None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True)
    ap.add_argument('--rule'); ap.add_argument('--obs'); ap.add_argument('--slot')
    ap.add_argument('--pending',action='store_true')
    ap.add_argument('--emit-findings',action='store_true',
                    help='按 findings 格式写出 machine/judge_findings.json（items + counts + needs_agent）')
    a=ap.parse_args(); O=a.out
    db=os.path.join(O,'machine','judge_index.db')
    if not os.path.exists(db): print(json.dumps({'error':'索引不存在，先 std.pack_index --build'})); return 2
    con=sqlite3.connect(db)
    slots={}
    sp=os.path.join(O,'machine','report_slots.json')
    if os.path.exists(sp): slots=json.load(open(sp,encoding='utf-8'))

    def judge(row,obs=None):
        rid,std,cat,cl,req,op,val,unit,om,slot,dt,hints,qual = row
        out={'rule_id':rid,'category':cat,'clause':cl,'doc_type':dt,'slot':slot}
        c=con.execute("select page,quote from clauses where clause=?",(cl,)).fetchone()
        if c: out['anchor']={'clause':cl,'page':c[0],'quote':c[1]}
        if qual or not op:
            # C8 记录类：缺失即不符合，不必等 agent；有记录才交 agent 判三档
            _obs = obs if obs is not None else (slots.get(slot) if slot else None)
            if str(cat)=='C8' and str(om)=='FAIL' and _obs in (None,'',[]):
                out.update(verdict='FAIL',message=f'缺证（C8 记录类，缺失即不符合）：未提供槽 {slot}',
                           owner='实验室')
                return out
            out.update(verdict='needs_agent',message='定性卡：由判定 agent 三档判（符合/不符合/缺证），NO_PASS')
            return out
        v=json.loads(val) if val else None
        out['predicate']={'op':op,'value':v,'unit':unit}
        if obs is None:
            obs=slots.get(slot) if slot else None
        if obs in (None,'',[]):
            # C8（记录与报告）缺失即不符合；其余缺证只能 UNVERIFIABLE
            if str(cat)=='C8' and str(om)=='FAIL':
                out.update(verdict='FAIL',message=f'缺证（C8 记录类，缺失即不符合）：未提供槽 {slot}',
                           owner='实验室')
            else:
                out.update(verdict='UNVERIFIABLE',message=f'缺证：未提供槽 {slot} 的观测值',
                           owner='实验室' if dt!='检测报告' else '送样方/检测室')
            return out
        ok,note=compare(op,v,obs)
        out['observed']={'value':obs,'unit':unit}
        if ok is None:
            out.update(verdict='UNVERIFIABLE',message=note or '不可比')
        else:
            out.update(verdict='PASS' if ok else 'FAIL',
                       message=f'{obs}{unit or ""} {op} {v}{unit or ""}'+('' if ok else ' 不成立'))
        return out

    if a.rule:
        row=con.execute("select * from rules where rule_id=?",(a.rule,)).fetchone()
        if not row: print(json.dumps({'error':'rule 不存在'},ensure_ascii=False)); return 1
        obs=a.obs if a.obs is None else a.obs
        print(json.dumps(judge(row,obs),ensure_ascii=False,indent=1)); return 0
    if a.slot:
        rows=con.execute("select * from rules where slot=?",(a.slot,)).fetchall()
        print(json.dumps([judge(r) for r in rows],ensure_ascii=False,indent=1)); return 0
    if a.emit_findings:
        rows=con.execute("select * from rules").fetchall()
        res=[judge(r) for r in rows]
        items=[]
        for x in res:
            if x['verdict']=='needs_agent':
                continue
            items.append({'rule_id':x['rule_id'],'category':x['category'],'slot':x.get('slot'),
                          'verdict':x['verdict'],'message':x.get('message'),
                          'std_anchor':x.get('anchor'),'basis':'judge_query',
                          'doc_type':x.get('doc_type'),
                          'owner':x.get('owner'),
                          'pending_class':'PENDING_DATA' if x['verdict']=='UNVERIFIABLE' else None})
        from collections import Counter
        na=[{'rule_id':x['rule_id'],'category':x['category'],'clause':x['clause'],
             'target':{'slot':x.get('slot'),'doc_type':x.get('doc_type')},
             'anchor':x.get('anchor')} for x in res if x['verdict']=='needs_agent']
        doc={'source':'judge_index','items':items,'needs_agent':na,
             'counts':dict(Counter(i['verdict'] for i in items)),
             'pending_agent_count':len(na)}
        dst=os.path.join(O,'machine','judge_findings.json')
        json.dump(doc,open(dst,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
        print(json.dumps({'written':dst,'items':len(items),'counts':doc['counts'],
                          'needs_agent':len(na)},ensure_ascii=False)); return 0
    if a.pending:
        rows=con.execute("select * from rules").fetchall()
        res=[judge(r) for r in rows]
        nonpass=[x for x in res if x['verdict']!='PASS']
        from collections import Counter
        print(json.dumps({'total':len(res),'counts':dict(Counter(x['verdict'] for x in res)),
                          'non_pass':nonpass[:20]},ensure_ascii=False,indent=1)); return 0
    print(json.dumps({'error':'需要 --rule / --slot / --pending'})); return 2
if __name__=='__main__': sys.exit(main())
