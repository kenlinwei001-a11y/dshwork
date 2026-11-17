#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 packed.yaml 建成可检索索引（SQLite），让判定 agent 按 rule/clause/slot/关键词检索。

用法:
  python3 pack_index.py --out <run> --build
  python3 pack_index.py --out <run> --rule ARC-C7-11.1-01
  python3 pack_index.py --out <run> --slot S041
  python3 pack_index.py --out <run> --clause 11.4
  python3 pack_index.py --out <run> --keyword 平行双样
  python3 pack_index.py --out <run> --traverse SE-QC-11.1-01 --edge invalidates

设计：一次检索只返回该条目相关的极少量内容（几十行），不让 agent 读整份 YAML。
"""
import argparse,json,os,sqlite3,sys
import yaml

DDL="""
CREATE TABLE IF NOT EXISTS rules(rule_id TEXT PRIMARY KEY, standard TEXT, category TEXT, clause TEXT,
  requirement TEXT, op TEXT, val TEXT, unit TEXT, on_missing TEXT, slot TEXT, doc_type TEXT,
  match_hints TEXT, qualitative INT);
CREATE TABLE IF NOT EXISTS clauses(clause TEXT, page TEXT, quote TEXT);
CREATE TABLE IF NOT EXISTS nodes(node_id TEXT, type TEXT, name TEXT, clauses TEXT);
CREATE TABLE IF NOT EXISTS edges(src TEXT, dst TEXT, etype TEXT);
CREATE INDEX IF NOT EXISTS i_r_clause ON rules(clause);
CREATE INDEX IF NOT EXISTS i_r_slot ON rules(slot);
CREATE INDEX IF NOT EXISTS i_e_src ON edges(src);
"""

def build_from_json(O):
    """直接从 03-rules + audit_tasks + sop-graph + ses + 01-clauses 建库，不经 YAML。"""
    def L(n,d=None):
        import json as J, os as OS
        p=OS.path.join(O,n)
        return J.load(open(p,encoding='utf-8')) if OS.path.exists(p) else d
    rules=L('03-rules.json',{}).get('audit_rule_cards') or []
    ses=L('ses.json',{}) or {}
    cl=L('01-clauses.json',{}) or {}
    g=L('sop-graph.json',{}) or {}
    tasks={}
    import os as OS, json as J
    tp=OS.path.join(O,'audit_tasks.jsonl')
    if OS.path.exists(tp):
        for line in open(tp,encoding='utf-8'):
            if line.strip():
                t=J.loads(line); tasks.setdefault(t.get('rule_id'),t)
    db=OS.path.join(O,'machine','judge_index.db')
    OS.makedirs(os.path.dirname(db),exist_ok=True)
    if OS.path.exists(db): OS.remove(db)
    con=sqlite3.connect(db); con.executescript(DDL)
    std=ses.get('standard_id') or g.get('standard')
    for r in rules:
        pr=r.get('predicate') or {}; t=tasks.get(r.get('rule_id')) or {}
        con.execute("INSERT OR REPLACE INTO rules VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (r['rule_id'],std,r.get('category'),r.get('clause'),r.get('requirement'),
           pr.get('op'),J.dumps(pr.get('value'),ensure_ascii=False) if pr else None,pr.get('unit'),
           r.get('on_missing'),t.get('slot'),t.get('doc_type'),
           J.dumps(t.get('match_hints') or [],ensure_ascii=False),0 if pr else 1))
    for c in (cl.get('clause_registry') or []):
        con.execute("INSERT INTO clauses VALUES(?,?,?)",(str(c.get('clause')),str(c.get('page')),c.get('quote')))
    for n in g.get('nodes') or []:
        con.execute("INSERT INTO nodes VALUES(?,?,?,?)",(n.get('node_id'),n.get('type'),
          n.get('name') or n.get('step') or '',J.dumps(n.get('clauses') or [],ensure_ascii=False)))
    for e in g.get('edges') or []:
        con.execute("INSERT INTO edges VALUES(?,?,?)",(e.get('from'),e.get('to'),e.get('type')))
    con.commit(); con.close(); return db

def build(O,pack):
    d=yaml.safe_load(open(pack,encoding='utf-8'))
    db=os.path.join(O,'machine','judge_index.db')
    if os.path.exists(db): os.remove(db)
    con=sqlite3.connect(db); con.executescript(DDL)
    for r in d.get('rules') or []:
        p=r.get('predicate') or {}; t=r.get('target') or {}
        con.execute("INSERT OR REPLACE INTO rules VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (r['rule_id'],d.get('standard_id'),r.get('category'),r.get('clause'),r.get('requirement'),
           p.get('op'),json.dumps(p.get('value'),ensure_ascii=False) if p else None,p.get('unit'),
           r.get('on_missing'),t.get('slot'),t.get('doc_type'),
           json.dumps(t.get('match_hints') or [],ensure_ascii=False),1 if r.get('qualitative') else 0))
    for c,v in (d.get('clauses') or {}).items():
        con.execute("INSERT INTO clauses VALUES(?,?,?)",(c,str(v.get('page')),v.get('quote')))
    for n in d.get('nodes') or []:
        con.execute("INSERT INTO nodes VALUES(?,?,?,?)",(n.get('id'),n.get('type'),
          n.get('name') or n.get('step') or '',json.dumps(n.get('clauses') or [],ensure_ascii=False)))
    for e in d.get('edges') or []:
        con.execute("INSERT INTO edges VALUES(?,?,?)",(e.get('from'),e.get('to'),e.get('type')))
    con.commit(); con.close()
    return db

def row2rule(r):
    return {'rule_id':r[0],'category':r[2],'clause':r[3],'requirement':r[4],
            'predicate':{'op':r[5],'value':json.loads(r[6]) if r[6] else None,'unit':r[7]} if r[5] else None,
            'on_missing':r[8],'slot':r[9],'doc_type':r[10],
            'match_hints':json.loads(r[11] or '[]'),'qualitative':bool(r[12])}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True)
    ap.add_argument('--pack',default=None); ap.add_argument('--build',action='store_true')
    ap.add_argument('--rule'); ap.add_argument('--slot'); ap.add_argument('--clause')
    ap.add_argument('--keyword'); ap.add_argument('--traverse'); ap.add_argument('--edge')
    a=ap.parse_args(); O=a.out
    pack=a.pack or os.path.join(O,'machine','sop-graph.packed.yaml')
    db=os.path.join(O,'machine','judge_index.db')
    if a.build_json:
        build_from_json(O)
        con=sqlite3.connect(db)
        print(json.dumps({'built':db,'source':'json','rules':con.execute('select count(*) from rules').fetchone()[0],
                          'clauses':con.execute('select count(*) from clauses').fetchone()[0],
                          'nodes':con.execute('select count(*) from nodes').fetchone()[0],
                          'edges':con.execute('select count(*) from edges').fetchone()[0]},ensure_ascii=False)); return 0
    if a.build:
        d=yaml.safe_load(open(pack,encoding='utf-8'))
        build(O,pack)
        con=sqlite3.connect(db); n=con.execute('select count(*) from rules').fetchone()[0]
        print(json.dumps({'built':db,'rules':n,'clauses':con.execute('select count(*) from clauses').fetchone()[0],
                          'nodes':con.execute('select count(*) from nodes').fetchone()[0],
                          'edges':con.execute('select count(*) from edges').fetchone()[0]},ensure_ascii=False)); return 0
    if not os.path.exists(db): print(json.dumps({'error':'索引不存在，先 --build'})); return 2
    con=sqlite3.connect(db); out={}
    if a.rule:
        r=con.execute("select * from rules where rule_id=?",(a.rule,)).fetchone()
        if not r: print(json.dumps({'error':'rule 不存在'},ensure_ascii=False)); return 1
        out['rule']=row2rule(r)
        c=con.execute("select page,quote from clauses where clause=?",(r[3],)).fetchone()
        out['clause_anchor']={'clause':r[3],'page':c[0],'quote':c[1]} if c else None
        out['node']=[{'node_id':x[0],'type':x[1],'name':x[2]} for x in
                     con.execute("select node_id,type,name from nodes where clauses like ?",('%'+str(r[3])+'%',))]
    if a.slot:
        out['rules']=[row2rule(r) for r in con.execute("select * from rules where slot=?",(a.slot,))]
    if a.clause:
        out['rules']=[row2rule(r) for r in con.execute("select * from rules where clause=?",(a.clause,))]
        c=con.execute("select page,quote from clauses where clause=?",(a.clause,)).fetchone()
        out['clause_anchor']={'clause':a.clause,'page':c[0],'quote':c[1]} if c else None
    if a.keyword:
        out['rules']=[row2rule(r) for r in con.execute(
          "select * from rules where requirement like ? or match_hints like ?",
          ('%'+a.keyword+'%','%'+a.keyword+'%'))]
    if a.traverse:
        q="select dst,etype from edges where src=?"+(" and etype=?" if a.edge else "")
        args=(a.traverse,)+((a.edge,) if a.edge else ())
        out['edges']=[{'to':x[0],'type':x[1]} for x in con.execute(q,args)]
    s=json.dumps(out,ensure_ascii=False,indent=1)
    print(s); print(f"\n[检索返回 {len(s.encode())} 字节]",file=sys.stderr); return 0
if __name__=='__main__': sys.exit(main())
