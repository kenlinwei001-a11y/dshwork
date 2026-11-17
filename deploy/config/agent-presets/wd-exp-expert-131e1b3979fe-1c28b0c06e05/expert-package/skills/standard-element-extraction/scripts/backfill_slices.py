import argparse,json,os,sys
ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True)
O=ap.parse_args().out
FAM={'C1':'SCOPE','C2':'SAMP','C3':'APPA','C4':'MATL','C5':'PROC','C6':'CALC','C7':'QC','C8':'META'}
cl=json.load(open(f"{O}/01-clauses.json",encoding='utf-8'))['clause_registry']
cards=json.load(open(f"{O}/03-rules.json",encoding='utf-8'))['audit_rule_cards']
by={}
for c in cards: by.setdefault(str(c.get('clause')),[]).append(c)
os.makedirs(f"{O}/machine/elt_judged",exist_ok=True); os.makedirs(f"{O}/machine/rule_judged",exist_ok=True)
rows=json.load(open(f"{O}/machine/rows.json",encoding='utf-8'))['rows']
SZ=20
row_clauses={r['clause'] for r in rows}
orphan=[c for c in cards if str(c.get('clause')) not in row_clauses]   # 条款号不在登记册里的规则卡
for i in range(0,len(rows),SZ):
    n=i//SZ+1; chunk=rows[i:i+SZ]
    last=(i+SZ>=len(rows))
    elt=[];rul=[]
    for r in chunk:
        cl_=r['clause']; cs=by.get(cl_)
        if not cs:
            elt.append({'clause':cl_,'skipped':True,'reason':'条款为程序/背景说明，未成规则'}); continue
        for c in cs:
            fam=FAM.get(c['category'],'META')
            elt.append({'clause':cl_,'element_id':f"SE-{c['category']}-{cl_}-01",'family':fam,
                        'statement':(c.get('requirement') or '')[:160],
                        'parameters':([{'name':'阈值','value':c['predicate'].get('value'),'unit':c['predicate'].get('unit')}] if c.get('predicate') else []),
                        'obligation':'MUST','anchor':c.get('anchor'),'origin':c.get('origin') or 'verbatim'})
            rul.append(c)
    if last and orphan:                    # 孤儿卡并入末片，绝不丢弃
        for c in orphan:
            fam=FAM.get(c['category'],'META')
            elt.append({'clause':str(c.get('clause')),'element_id':f"SE-{c['category']}-{c.get('clause')}-01",
                        'family':fam,'statement':(c.get('requirement') or '')[:160],
                        'parameters':([{'name':'阈值','value':c['predicate'].get('value'),'unit':c['predicate'].get('unit')}] if c.get('predicate') else []),
                        'obligation':'MUST','anchor':c.get('anchor'),'origin':c.get('origin') or 'verbatim',
                        'note':'条款号不在 rows（表注/子条），按规则卡归属'})
            rul.append(c)
    json.dump(elt,open(f"{O}/machine/elt_judged/{n:04d}.json",'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    json.dump(rul,open(f"{O}/machine/rule_judged/{n:04d}.json",'w',encoding='utf-8'),ensure_ascii=False,indent=1)
print(json.dumps({"rows":len(rows),"cards":len(cards),"orphan":len(orphan)},ensure_ascii=False)); import sys as _s; _s.exit(0)
#print(f"{O}: rows {len(rows)}, cards {len(cards)}, orphan {len(orphan)}, slices {(len(rows)+SZ-1)//SZ}")
