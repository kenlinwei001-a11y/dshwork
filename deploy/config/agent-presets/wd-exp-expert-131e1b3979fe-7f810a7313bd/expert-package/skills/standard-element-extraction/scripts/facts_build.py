#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""事实层构建：只保留 4 类可写事实，其余全部派生。
用法: python3 facts_build.py --out <out> [--std HJ671-2013]
产物: facts.json（可写事实）、derived.json（派生视图）、integrity 报告
"""
import argparse, json, os, sys, collections

def load(p):
    with open(p, encoding='utf-8') as f: return json.load(f)

def derive(F, O):
    clauses = {x['clause']: x for x in F.get('clauses') or []}
    judgments = F.get('judgments') or []; bindings = F.get('bindings') or []; gaps = F.get('gaps') or []
    rec = F.get('records') or {}
    if rec.get('elements'): judgments = judgments + [{'element_id': x.get('element_id'), 'clause': str((x.get('anchor') or {}).get('clause')), 'family': x.get('family'), 'obligation': x.get('obligation'), 'origin': x.get('origin')} for x in rec['elements'] if not any(j.get('element_id') == x.get('element_id') for j in judgments)]
    if rec.get('rules'): judgments = judgments + [{'rule_id': x.get('rule_id'), 'clause': str(x.get('clause')), 'category': x.get('category'), 'ceiling': x.get('verdict_ceiling'), 'on_missing': x.get('on_missing'), 'has_predicate': bool(x.get('predicate')), 'qualitative': bool(x.get('qualitative_check'))} for x in rec['rules'] if not any(j.get('rule_id') == x.get('rule_id') for j in judgments)]
    rule_clauses = {j['clause'] for j in judgments if j.get('rule_id')}
    el_clauses = {j['clause'] for j in judgments if j.get('element_id')}
    coverage = [{'clause': cl, 'has_element': cl in el_clauses, 'has_rule': cl in rule_clauses, 'judgeable': cl in rule_clauses} for cl in clauses]
    return {
        'counts': {'clauses': len(clauses), 'elements': sum(1 for j in judgments if j.get('element_id')),
                   'rules': sum(1 for j in judgments if j.get('rule_id')),
                   'bindings': len(bindings), 'gaps': len(gaps),
                   'normative': sum(1 for v in clauses.values() if v['type'] == 'normative')},
        'coverage': {'rows': len(coverage), 'with_rule': sum(1 for x in coverage if x['has_rule']),
                     'without_rule': [x['clause'] for x in coverage if not x['has_rule']][:20]},
        'categories': dict(sorted(collections.Counter(j.get('category') for j in judgments if j.get('rule_id')).items())),
        'pending_class': dict(sorted(collections.Counter(g.get('pending_class') for g in gaps).items())),
    }

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--facts', default='')
    a = ap.parse_args(); O = a.out
    fp = a.facts or os.path.join(O, 'facts.json')
    if a.facts and os.path.exists(fp):
        F = load(fp)
        json.dump(derive(F, O), open(os.path.join(O, 'derived.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print(json.dumps({'mode': 'derive_only', 'counts': load(os.path.join(O, 'derived.json'))['counts']}, ensure_ascii=False)); return 0
    if os.path.exists(os.path.join(O, '.views_exported')) and not os.path.exists(os.path.join(O, 'facts.json')) and '--force' not in sys.argv:
        print(json.dumps({'error': 'views_are_readonly', 'hint': '视图由 facts 导出，不能反推事实；确需重建请加 --force'}, ensure_ascii=False)); return 2
    c = load(os.path.join(O, '01-clauses.json'))
    e = load(os.path.join(O, '02-elements.json')) if os.path.exists(os.path.join(O, '02-elements.json')) else {}
    r = load(os.path.join(O, '03-rules.json')) if os.path.exists(os.path.join(O, '03-rules.json')) else {}
    clauses = {str(x['clause']): {k: x.get(k) for k in ('clause','page','quote','modality','type','heading','section_role','section_roles') if x.get(k) is not None}
               for x in c.get('clause_registry') or []}
    bindings, judgments, gaps = [], [], []
    for el in e.get('elements') or []:
        cl = str((el.get('anchor') or {}).get('clause'))
        for p in el.get('parameters') or []:
            ref = p.get('value_ref')
            if ref:
                bindings.append({'element_id': el['element_id'], 'clause': cl, 'ref': ref})
        judgments.append({'element_id': el['element_id'], 'clause': cl, 'family': el.get('family'),
                          'obligation': el.get('obligation'), 'origin': el.get('origin')})
    for k in r.get('audit_rule_cards') or []:
        judgments.append({'rule_id': k['rule_id'], 'clause': str(k.get('clause')), 'category': k.get('category'),
                          'ceiling': k.get('verdict_ceiling'), 'on_missing': k.get('on_missing'),
                          'has_predicate': bool(k.get('predicate')), 'qualitative': bool(k.get('qualitative_check'))})
    for g in (r.get('gaps') or c.get('gaps') or []):
        gg = dict(g); gg.setdefault('pending_class', g.get('pending_class'))
        gaps.append(gg)
    # ---- 完整性（写入时约束）----
    errs = []
    for b in bindings:
        if b['clause'] not in clauses: errs.append(f"FK: {b['element_id']} clause {b['clause']} 不存在")
        if not b['ref'].get('raw'): errs.append(f"REF: {b['element_id']} ref 缺 raw")
    for j in judgments:
        if j['clause'] not in clauses: errs.append(f"FK: {j.get('element_id') or j.get('rule_id')} clause {j['clause']} 不存在")
    ids = [j.get('element_id') or j.get('rule_id') for j in judgments]
    for k, v in collections.Counter(ids).items():
        if v > 1: errs.append(f"ID: {k} 重复 {v} 次")
    # ---- 派生视图（模型不得写）----
    rule_clauses = {j['clause'] for j in judgments if j.get('rule_id')}
    el_clauses = {j['clause'] for j in judgments if j.get('element_id')}
    coverage = [{'clause': cl, 'has_element': cl in el_clauses, 'has_rule': cl in rule_clauses,
                 'judgeable': cl in rule_clauses} for cl in clauses]
    derived = {
        'counts': {'clauses': len(clauses), 'elements': sum(1 for j in judgments if j.get('element_id')),
                   'rules': sum(1 for j in judgments if j.get('rule_id')),
                   'bindings': len(bindings), 'gaps': len(gaps),
                   'normative': sum(1 for v in clauses.values() if v['type'] == 'normative')},
        'coverage': {'rows': len(coverage), 'with_rule': sum(1 for x in coverage if x['has_rule']),
                     'without_rule': [x['clause'] for x in coverage if not x['has_rule']][:20]},
        'categories': dict(sorted(collections.Counter(j.get('category') for j in judgments if j.get('rule_id')).items())),
        'pending_class': dict(sorted(collections.Counter(g.get('pending_class') for g in gaps).items())),
    }
    json.dump({'standard': c.get('standard_id'),
               'meta': {'standard_id': c.get('standard_id'), 'standard_slug': c.get('standard_slug'),
                        'standard_type': c.get('standard_type'), 'source_fingerprint': c.get('source_fingerprint')},
               'refs': c.get('reference_register') or [],
               'clauses': list(clauses.values()),
               'bindings': bindings,
               'records': {'elements': e.get('elements') or [], 'rules': r.get('audit_rule_cards') or [],
                           'formula_cards': e.get('formula_cards') or [], 'coverage_extra': []},
               'judgments': judgments, 'gaps': gaps},
              open(os.path.join(O, 'facts.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    json.dump(derived, open(os.path.join(O, 'derived.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({'integrity_errors': len(errs), 'sample': errs[:5], 'derived': derived['counts']}, ensure_ascii=False))
    return 0 if not errs else 1

if __name__ == '__main__':
    sys.exit(main())
