#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出时按 value_ref 展开数值；指纹或原文不符标 DANGLING。
用法: python3 resolve.py --elements refs.json --db store.db --out resolved.json
"""
import argparse, json, sqlite3, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--elements', required=True); ap.add_argument('--db', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    d = json.load(open(a.elements, encoding='utf-8'))
    con = sqlite3.connect(a.db)
    sha = con.execute('select sha from standards').fetchone()[0]
    ok = dangling = plain = 0
    for e in d['elements']:
        for p in e.get('parameters') or []:
            ref = p.get('value_ref')
            if not ref: plain += 1; continue
            if 'table' in ref:
                t = con.execute('select value from table_cells where table_id=? and row=? and col=?',
                                (ref['table'], ref['row'], ref['col'])).fetchone()
                if t and t[0] == str(ref.get('raw')):
                    p['resolved_raw'] = ref['raw']; ok += 1
                else:
                    p['status'] = 'DANGLING'; dangling += 1
                continue
            row = con.execute('select text, start from clauses where clause=?', (ref['clause'],)).fetchone()
            bad = (not row) or (ref.get('sha') and ref['sha'] != sha) or \
                  (row[0][ref['span'][0] - row[1]:ref['span'][1] - row[1]] != ref['raw'])
            if bad:
                p['status'] = 'DANGLING'; dangling += 1
            else:
                p['resolved_value'] = p.get('value'); p['resolved_raw'] = ref['raw']; ok += 1
    json.dump(d, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({'resolved': ok, 'dangling': dangling, 'literal': plain}, ensure_ascii=False))
    return 0 if dangling == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
