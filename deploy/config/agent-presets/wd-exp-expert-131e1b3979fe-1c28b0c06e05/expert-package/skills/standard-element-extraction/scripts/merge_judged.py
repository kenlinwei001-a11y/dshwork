#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并切片判定 → 02-elements / 03-rules，并校验覆盖与必检项。

用法: python3 merge_judged.py --out <run> [--rules <校验基准>]
读: machine/elt_judged/*.json、machine/rule_judged/*.json
校验: ① 每条 rows 都被判过（或标 skipped+理由）② 每张规则卡有 clause+anchor+check_targets
      ③ predicate 或 qualitative 二者必居其一
"""
import argparse,json,os,sys,glob
ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True)
ap.add_argument('--rules',default='03-rules.json'); a=ap.parse_args(); O=a.out
rows=json.load(open(os.path.join(O,'machine','rows.json'),encoding='utf-8'))['rows']
elt=[];rule=[]
for p in sorted(glob.glob(os.path.join(O,'machine','elt_judged','*.json'))): elt+=json.load(open(p,encoding='utf-8'))
for p in sorted(glob.glob(os.path.join(O,'machine','rule_judged','*.json'))): rule+=json.load(open(p,encoding='utf-8'))
judged={str(x['clause']) for x in elt}|{str(x['clause']) for x in rule}
skipped={str(x['clause']) for x in elt if x.get('skipped')}
missing=[r['clause'] for r in rows if r['clause'] not in judged and r['clause'] not in skipped]
bad=[c.get('rule_id') for c in rule if not (c.get('clause') and c.get('anchor') and c.get('check_targets'))]
nopred=[c.get('rule_id') for c in rule if not c.get('predicate') and not c.get('qualitative_check')]
# 写回：保留原要素中「非规则」的那些（步骤/分析物/干扰的锚），规则条款用判定覆盖
_prev=json.load(open(os.path.join(O,'02-elements.json'),encoding='utf-8')) if os.path.exists(os.path.join(O,'02-elements.json')) else {'elements':[]}
_judged_clauses={str(x.get('clause')) for x in elt if not x.get('skipped')}
_keep=[e for e in (_prev.get('elements') or [])]          # 全量保留：锚只增不减
el={'standard_id':json.load(open(os.path.join(O,'01-clauses.json'),encoding='utf-8')).get('standard_id'),
    'elements':list({e.get('element_id'):e for e in (_keep+[x for x in elt if not x.get('skipped')])}.values()),
    'procedure_graph':json.load(open(os.path.join(O,'02-elements.json'),encoding='utf-8')).get('procedure_graph') if os.path.exists(os.path.join(O,'02-elements.json')) else {'nodes':[],'edges':[]}}
json.dump(el,open(os.path.join(O,'02-elements.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
ru=json.load(open(os.path.join(O,'03-rules.json'),encoding='utf-8'))
ru['audit_rule_cards']=rule
ru['coverage_matrix']=[{'clause':c,'rules':len([x for x in rule if str(x.get('clause'))==c])} for c in sorted({str(x.get('clause')) for x in rule})]
json.dump(ru,open(os.path.join(O,'03-rules.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps({'elements':len(el['elements']),'rules':len(rule),'judged_clauses':len(judged),
  'missing':len(missing),'missing_sample':missing[:5],'bad_cards':len(bad),'no_pred_no_qual':len(nopred),
  'ok':not missing},ensure_ascii=False))
# 结构性错误（条款没判到）才判失败；质量项交给 audit 的机器筛
sys.exit(0 if not missing else 1)
