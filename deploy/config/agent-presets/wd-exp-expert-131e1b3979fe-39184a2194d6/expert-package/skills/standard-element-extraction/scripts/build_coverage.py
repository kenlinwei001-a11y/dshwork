#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由规则卡反推覆盖矩阵（确定性）。用法: python3 build_coverage.py --clauses 01.json --rules 03.json [--write]"""
import argparse, json, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--clauses', required=True); ap.add_argument('--rules', required=True)
    ap.add_argument('--out'); ap.add_argument('--write', action='store_true')
    a = ap.parse_args()
    c = json.load(open(a.clauses, encoding='utf-8')); r = json.load(open(a.rules, encoding='utf-8'))
    cards = r.get('audit_rule_cards') or []
    by = {}
    for k in cards:
        cl = str(k.get('clause'))
        by.setdefault(cl, []).append(k['rule_id'])
        for cov in (k.get('covers_clauses') or []):
            by.setdefault(str(cov), []).append(k['rule_id'])
    rows = []
    for x in c.get('clause_registry') or []:
        cl = str(x['clause']); ids = sorted(set(by.get(cl, [])))
        rows.append({'clause': cl, 'elements': 0, 'rules': ids, 'judgeable': bool(ids),
                     'gap_ids': [], 'note': ('规则：' + ', '.join(ids[:3]) + ('…' if len(ids) > 3 else '')) if ids else '无规则（见缺口/理由）'})
    if a.write:
        r['coverage_matrix'] = rows
        json.dump(r, open(a.rules, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({'rows': len(rows), 'with_rules': sum(1 for x in rows if x['rules']), 'written': a.write}, ensure_ascii=False))
    return 0

if __name__ == '__main__':
    sys.exit(main())
