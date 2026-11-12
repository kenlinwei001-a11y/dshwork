#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按候选 + 判断合成 02-elements.json（结构由脚本定，判断来自 LLM）。
judgments 每条: {element_id, clause, family, statement, obligation, applicability?, evidence?, origin,
                params:[{ref:"5.1#2"} | {name,value,unit}], derive_from?}
"""
import argparse, json, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--clauses', required=True); ap.add_argument('--candidates', required=True)
    ap.add_argument('--judgments', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    c = json.load(open(a.clauses, encoding='utf-8'))
    cand = json.load(open(a.candidates, encoding='utf-8'))
    cmap = {x['clause']: x for x in cand['clauses']}
    cl = {x['clause']: x for x in c.get('clause_registry') or []}
    js = json.load(open(a.judgments, encoding='utf-8'))
    if isinstance(js, dict): js = js.get('elements') or []
    els, errs = [], []
    for j in js:
        cl_no = j.get('clause'); src = cmap.get(cl_no) or {}
        params = []
        for p in j.get('params') or []:
            if 'ref' in p:
                base, _, idx = p['ref'].partition('#'); idx = int(idx)
                row = (cmap.get(base) or {}).get('numbers') or []
                m = next((n for n in row if n['i'] == idx), None)
                if not m: errs.append(f"{j.get('element_id')}: 候选引用不存在 {p['ref']}"); continue
                params.append({'name': p.get('name') or m['raw'], 'value': float(m['value']),
                               'unit': m['unit'], 'raw': m['raw']})
            else:
                params.append(p)
        els.append({'element_id': j['element_id'], 'family': j['family'], 'statement': j['statement'],
                    'parameters': params, 'obligation': j.get('obligation', 'MUST'),
                    'applicability': j.get('applicability', ''), 'evidence': j.get('evidence') or [],
                    'source_layer': 'STANDARD', 'origin': j.get('origin', 'verbatim'),
                    'derive_from': j.get('derive_from') or [],
                    'anchor': {'standard': c['standard_id'], 'clause': cl_no,
                               'page': (cl.get(cl_no) or {}).get('page'), 'quote': (cl.get(cl_no) or {}).get('quote')}})
    doc = {'standard_id': c['standard_id'], 'standard_slug': c.get('standard_slug'),
           'elements': els, 'counts': {'elements': len(els)},
           'assemble': {'from_candidates': len(cand['clauses']), 'errors': errs}}
    json.dump(doc, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({'elements': len(els), 'errors': len(errs), 'sample': errs[:3]}, ensure_ascii=False))
    return 1 if errs else 0

if __name__ == '__main__':
    sys.exit(main())
