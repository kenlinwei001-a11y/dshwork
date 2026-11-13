#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性合并：01/02/03 + audit -> ses.json（零判断）。
用法: python3 merge_ses.py --out DIR [--std SLUG] [--audit DIR/04-audit.md]
"""
import argparse, hashlib, json, os, re, sys

def load(p):
    return json.load(open(p, encoding='utf-8'))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--slug', default=None)
    a = ap.parse_args()
    o = a.out
    c = load(os.path.join(o, '01-clauses.json'))
    e = load(os.path.join(o, '02-elements.json'))
    r = load(os.path.join(o, '03-rules.json'))
    slug = a.slug or c.get('standard_slug')
    ses = {
        'standard_id': c['standard_id'],
        'standard_slug': slug,
        'standard_type': c.get('standard_type'),
        'title': c.get('title'),
        'source_fingerprint': c.get('source_fingerprint'),
        'status': c.get('status'),
        'extraction': {'scope': 'full', 'date': __import__('datetime').date.today().isoformat(),
                       'extractor': 'standard-element-extraction', 'schema_version': '1.1.0',
                       'merged_by': 'merge_ses.py'},
        'clause_registry': c.get('clause_registry', []),
        'reference_register': c.get('reference_register', []),
        'elements': e.get('elements', []),
        'formula_cards': e.get('formula_cards', []),
        'procedure_graph': e.get('procedure_graph', {}),
        'dependency_graph': r.get('dependency_graph', e.get('dependency_graph', {})),
        'lab_alignment': r.get('lab_alignment', []),
        'method_family': c.get('method_family', []),
        'audit_rule_cards': r.get('audit_rule_cards', []),
        'coverage_matrix': r.get('coverage_matrix', []),
        'gaps': r.get('gaps') or e.get('gaps') or c.get('gaps') or [],
        'rule_set_id': f"RS-{slug}",
    }
    # 计数（确定性，不手填）
    ses['counts'] = {
        'clauses': len(ses['clause_registry']),
        'normative': sum(1 for x in ses['clause_registry'] if x.get('type') == 'normative'),
        'elements': len(ses['elements']),
        'formulas': len(ses['formula_cards']),
        'rules': len(ses['audit_rule_cards']),
        'gaps': len(ses['gaps']),
        'lab_alignment': len(ses['lab_alignment']),
    }
    ar = os.path.join(o, 'audit_result.json')
    if os.path.exists(ar):
        ses['audit_result'] = load(ar)
    out = os.path.join(o, 'ses.json')
    json.dump(ses, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    h = hashlib.sha256(open(out, 'rb').read()).hexdigest()[:12]
    print(json.dumps({'out': out, 'counts': ses['counts'], 'sha256_12': h, 'rule_set_id': ses['rule_set_id']},
                     ensure_ascii=False))
    return 0

if __name__ == '__main__':
    sys.exit(main())
