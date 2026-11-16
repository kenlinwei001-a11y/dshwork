#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把要素参数改为 value_ref（derived 除外）。用法: --elements 02-elements.json --db store.db --out refs.json"""
import argparse, json, re, sqlite3, sys

SUB = {'μ':'u', 'µ':'u', '℃':'C', '°':'', '（':'(', '）':')', '，':',', '：':':', '　':''}
# 全角→半角（数字/字母/常见符号）
FW = {chr(0xFF10 + i): str(i) for i in range(10)}
FW.update({chr(0xFF21 + i): chr(65 + i) for i in range(26)})
FW.update({chr(0xFF41 + i): chr(97 + i) for i in range(26)})
# 已知 OCR 串错
FIX = [('m(l', 'ml'), ('m（l', 'ml'), ('m(I', 'ml'), ('ug/ml', 'ug/ml')]

def pre(t):
    for a, b in FIX: t = t.replace(a, b)
    return t.translate(str.maketrans(FW))

def norm_map(t):
    out, idx = [], []
    for i, ch in enumerate(pre(t)):
        if ch.isspace(): continue
        ch = SUB.get(ch, ch)
        out.append(ch); idx.append(i)
    return ''.join(out), idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--elements', required=True); ap.add_argument('--db', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    d = json.load(open(a.elements, encoding='utf-8'))
    con = sqlite3.connect(a.db)
    refs = miss = derived = 0
    for e in d['elements']:
        cl = e['anchor']['clause']
        row = con.execute('select text, start, sha from clauses where clause=?', (str(cl),)).fetchone()
        body, base, sha = (row[0], row[1], row[2]) if row else ('', 0, None)
        nb, nmap = norm_map(body)
        for p in e.get('parameters') or []:
            if e.get('origin') == 'derived' or p.get('unverified'):
                derived += 1; continue
            u = str(p.get('unit') or '')
            raw = (p.get('raw') or '').strip() or (str(p.get('value')) + ('' if u in ('1', '—', '类型', '') else u))
            nr, _ = norm_map(raw)
            k = nb.find(nr) if nr else -1
            if k >= 0:
                st = base + nmap[k]
                en = base + nmap[k + len(nr) - 1] + 1
                p['value_ref'] = {'clause': str(cl), 'span': [st, en], 'raw': body[nmap[k]:nmap[k + len(nr) - 1] + 1], 'sha': sha}
                refs += 1; continue
            # else: search all clauses (cross-clause)
            hit = None
            for (t2, b2, s2, sh2) in con.execute('select clause, text, start, sha from clauses').fetchall():
                nb2, nm2 = norm_map(b2); k2 = nb2.find(nr) if nr else -1
                if k2 >= 0: hit = (t2, b2, s2, sh2, k2, nm2); break
            if hit:
                t2, b2, s2, sh2, k2, nm2 = hit
                p['value_ref'] = {'clause': str(t2), 'source_clause': str(t2), 'anchor_clause': str(cl),
                                  'span': [s2 + nm2[k2], s2 + nm2[k2 + len(nr) - 1] + 1],
                                  'raw': b2[nm2[k2]:nm2[k2 + len(nr) - 1] + 1], 'sha': sh2, 'cross_clause': True}
                refs += 1; continue
            # else: table cell reference
            t = con.execute("select table_id,row,col,value from table_cells where value=? and page=? limit 1",
                            (str(p.get('value')), e['anchor'].get('page'))).fetchone()
            if t:
                p['value_ref'] = {'table': t[0], 'row': t[1], 'col': t[2], 'raw': t[3], 'page': e['anchor'].get('page')}
                refs += 1; continue
            miss += 1
    json.dump(d, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({'params_total': sum(len(e.get('parameters') or []) for e in d['elements']),
                      'value_ref': refs, 'literal': miss, 'derived_or_unverified': derived}, ensure_ascii=False))

if __name__ == '__main__':
    sys.exit(main())
