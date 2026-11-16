#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 facts.json 导出视图 01/02/03（视图只读，不是事实）。
用法: python3 facts_export.py --out <out>
"""
import argparse, json, os, sys

def load(p): return json.load(open(p, encoding='utf-8'))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True)
    a = ap.parse_args(); O = a.out
    F = load(os.path.join(O, 'facts.json')); D = load(os.path.join(O, 'derived.json'))
    meta = F.get('meta') or {}
    clauses = [dict(x) for x in F.get('clauses') or []]
    v01 = {'standard_id': meta.get('standard_id'), 'standard_slug': meta.get('standard_slug'),
           'standard_type': meta.get('standard_type'), 'source_fingerprint': meta.get('source_fingerprint'),
           'clause_registry': clauses, 'reference_register': F.get('refs') or [], 'gaps': F.get('gaps') or [],
           'counts': {'clauses': len(clauses)}}
    rec = F.get('records') or {}
    v02 = {'standard_id': meta.get('standard_id'), 'standard_slug': meta.get('standard_slug'), 'elements': rec.get('elements') or [], 'formula_cards': rec.get('formula_cards') or [],
           'bindings': F.get('bindings') or [], 'counts': {'elements': len(rec.get('elements') or [])}}
    cov = [{'clause': x['clause'], 'rules': [r['rule_id'] for r in (rec.get('rules') or []) if str(r.get('clause')) == x['clause']],
            'judgeable': x['has_rule'], 'note': 'derived'} for x in D['coverage'].get('rows') and [{'clause': c, 'has_rule': c in {str(r.get('clause')) for r in (rec.get('rules') or [])}} for c in [x['clause'] for x in clauses]]]
    v03 = {'standard_id': meta.get('standard_id'), 'standard_slug': meta.get('standard_slug'),
           'rule_set_id': meta.get('standard_id') and 'RS-' + str(meta.get('standard_id')).replace(' ', ''), 'audit_rule_cards': rec.get('rules') or [], 'coverage_matrix': cov,
           'gaps': F.get('gaps') or [], 'counts': {'rules': len(rec.get('rules') or [])}}
    for name, obj in (('01-clauses.json', v01), ('02-elements.json', v02), ('03-rules.json', v03)):
        json.dump(obj, open(os.path.join(O, name), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    open(os.path.join(O, '.views_exported'), 'w').write('views are read-only; facts.json is authoritative\n')
    print(json.dumps({'exported': ['01', '02', '03'], 'counts': D['counts']}, ensure_ascii=False))
    return 0

if __name__ == '__main__':
    sys.exit(main())
