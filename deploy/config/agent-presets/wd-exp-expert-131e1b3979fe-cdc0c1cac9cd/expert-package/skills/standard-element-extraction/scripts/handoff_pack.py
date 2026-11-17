#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 ses.json + machine/handoff_state.json + machine/handoff.model.md（占位符版）。"""
import argparse,json,os,sys
ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); a=ap.parse_args(); O=a.out
cl=json.load(open(os.path.join(O,'01-clauses.json'),encoding='utf-8'))
el=json.load(open(os.path.join(O,'02-elements.json'),encoding='utf-8'))
ru=json.load(open(os.path.join(O,'03-rules.json'),encoding='utf-8'))
g=json.load(open(os.path.join(O,'sop-graph.json'),encoding='utf-8'))
cards=ru['audit_rule_cards']; std=cl.get('standard_id')
ses={'standard_id':std,'standard_slug':str(std).replace(' ',''),'standard_type':{'kind':'method','reason':'方法标准'},
 'source_fingerprint':{'chars':None},'rule_set_id':'RS-'+str(std).replace(' ',''),
 'clause_registry':cl.get('clause_registry'),'reference_register':cl.get('reference_register') or [],
 'elements':el.get('elements'),'procedure_graph':el.get('procedure_graph'),'audit_rule_cards':cards,
 'counts':{'clauses':len(cl.get('clause_registry') or []),'elements':len(el.get('elements') or []),
  'rules':len(cards),'rules_with_predicate':sum(1 for x in cards if x.get('predicate')),
  'nodes':len(g['nodes']),'edges':len(g['edges'])},'gaps':cl.get('gaps') or []}
json.dump(ses,open(os.path.join(O,'ses.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
c=ses['counts']
st={'out':os.path.abspath(O),'standard_id':std,'rule_count':c['rules'],
 'predicate_count':c['rules_with_predicate'],'qualitative_count':c['rules']-c['rules_with_predicate'],
 'clause_count':c['clauses'],'element_count':c['elements'],'node_count':c['nodes'],
 'edge_count':c['edges'],'gap_count':len(ses['gaps'])}
os.makedirs(os.path.join(O,'machine'),exist_ok=True)
json.dump(st,open(os.path.join(O,'machine','handoff_state.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
p=os.path.join(O,'machine','handoff.model.md')
if not os.path.exists(p):
    open(p,'w',encoding='utf-8').write("""## 结论

本标准抽出 {{rule_count}} 条规则，覆盖 {{clause_count}} 条条款；{{predicate_count}} 条可由脚本直接比对，{{qualitative_count}} 条为定性卡。

流程图 {{node_count}} 个节点、{{edge_count}} 条边。

缺口 {{gap_count}} 条。
""")
print(json.dumps({'ses':True,'handoff_state':st['rule_count']},ensure_ascii=False)); sys.exit(0)
