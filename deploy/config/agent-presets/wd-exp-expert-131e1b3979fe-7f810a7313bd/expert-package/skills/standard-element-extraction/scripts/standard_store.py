#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""建立标准原文库：clauses(文本/span/sha) + table_cells + chunks。
用法: python3 standard_store.py --clauses 01-clauses.json --text std.txt --db store.db
"""
import argparse, hashlib, json, os, re, sqlite3, sys

DDL = """
CREATE TABLE IF NOT EXISTS standards(id TEXT PRIMARY KEY, slug TEXT, sha TEXT, pages INT, text_path TEXT);
CREATE TABLE IF NOT EXISTS clauses(clause TEXT, page INT, heading TEXT, text TEXT, start INT, end INT, sha TEXT, PRIMARY KEY(clause));
CREATE TABLE IF NOT EXISTS table_cells(table_id TEXT, row INT, col INT, value TEXT, page INT);
CREATE TABLE IF NOT EXISTS chunks(cid TEXT PRIMARY KEY, clause TEXT, text TEXT, kind TEXT);
"""

def locate(text, x):
    """返回 (start,end)：优先用 quote 定位，回退到条款号 token；找不到返回 (0,0)。"""
    q = (x.get('quote') or '')[:40]
    if q:
        i = text.find(q)
        if i >= 0:
            return i, min(len(text), i + 1500)
    import re as _re
    m = _re.search(r'(?m)^\s*' + _re.escape(str(x.get('clause'))) + r'(?![\d.])', text)
    if m: return m.start(), min(len(text), m.start() + 1500)
    return 0, 0

def blocks(text, clauses):
    marks = []
    for x in clauses:
        no = str(x.get('clause'))
        m = re.search(r'(?m)^\s*' + re.escape(no) + r'(?![\d.])', text)
        if m: marks.append((m.start(), no))
    marks.sort()
    out = {}
    for i, (st, no) in enumerate(marks):
        en = marks[i + 1][0] if i + 1 < len(marks) else min(len(text), st + 1500)
        out.setdefault(no, (st, en))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--clauses', required=True); ap.add_argument('--text', required=True)
    ap.add_argument('--db', required=True)
    a = ap.parse_args()
    c = json.load(open(a.clauses, encoding='utf-8'))
    text = open(a.text, encoding='utf-8').read()
    sha = hashlib.sha256(text.encode()).hexdigest()[:12]
    # 不可变存储：按文本 sha 命名；已存在且匹配则复用；原子写
    base, ext = os.path.splitext(a.db)
    db = f'{base}-{sha}{ext or ".db"}'
    if os.path.exists(db):
        try:
            con0 = sqlite3.connect(db); s0 = con0.execute('select sha from standards').fetchone()[0]; con0.close()
            if s0 == sha:
                print(json.dumps({'db': db, 'sha': sha, 'reused': True}, ensure_ascii=False)); return 0
        except Exception:
            pass
    tmp = f'{db}.tmp-{os.getpid()}'
    if os.path.exists(tmp): os.remove(tmp)
    con = sqlite3.connect(tmp); con.executescript(DDL)
    con.execute('INSERT INTO standards VALUES (?,?,?,?,?)',
                (c['standard_id'], c.get('standard_slug'), sha, c.get('source_fingerprint', {}).get('pages'), a.text))
    bl = {str(x.get('clause')): locate(text, x) for x in (c.get('clause_registry') or [])}
    n_clause = n_cells = 0
    for x in c.get('clause_registry') or []:
        no = str(x.get('clause'))
        st, en = bl.get(no, (0, 0))
        body = text[st:en]
        con.execute('INSERT OR REPLACE INTO clauses VALUES (?,?,?,?,?,?,?)',
                    (no, x.get('page'), x.get('heading'), body, st, en, sha)); n_clause += 1
        con.execute('INSERT OR REPLACE INTO chunks VALUES (?,?,?,?)', (f'{no}#0', no, body[:800], 'clause'))
        tid = None
        for line in body.splitlines():
            m = re.search(r'表\s*([0-9A-Za-z.]+)', line)
            if m: tid = 'T' + m.group(1)
            nums = re.findall(r'\d+(?:\.\d+)?', line)
            if tid and len(nums) >= 3:
                for j, v in enumerate(nums):
                    con.execute('INSERT INTO table_cells VALUES (?,?,?,?,?)', (tid, n_cells, j, v, x.get('page')))
                n_cells += 1
    cells = con.execute('select count(*) from table_cells').fetchone()[0]
    con.commit(); con.close()
    os.replace(tmp, db)
    print(json.dumps({'db': db, 'sha': sha, 'clauses': n_clause, 'table_rows': n_cells,
                      'cells': cells}, ensure_ascii=False))

if __name__ == '__main__':
    sys.exit(main())
