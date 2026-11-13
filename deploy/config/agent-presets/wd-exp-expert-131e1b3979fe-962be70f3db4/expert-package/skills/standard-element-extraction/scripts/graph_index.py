#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOP 图进库：把 sop-graph.json 落成 nodes / edges / rule_node 三张表。

目的：下游按 node_id 分组、沿边找记录时查库，不再读 JSON 文件；
     并把「规则挂不上节点」从静默漏洞变成登记缺口（machine/graph_gaps.json）。

被两处复用：
  run_contract.py --util load_library   节点契约运行时
  load_library.py                       独立建库
"""
import json
import os

DDL = """
CREATE TABLE IF NOT EXISTS nodes(
  standard_id TEXT, node_id TEXT, type TEXT, step TEXT, clauses TEXT,
  params TEXT, done_when TEXT, basis TEXT, usage TEXT, payload TEXT,
  PRIMARY KEY(standard_id, node_id));
CREATE TABLE IF NOT EXISTS edges(
  standard_id TEXT, src TEXT, dst TEXT, type TEXT,
  PRIMARY KEY(standard_id, src, dst, type));
CREATE TABLE IF NOT EXISTS rule_node(
  standard_id TEXT, rule_id TEXT, node_id TEXT, link TEXT,
  PRIMARY KEY(standard_id, rule_id, node_id));
CREATE INDEX IF NOT EXISTS idx_rule_node ON rule_node(standard_id, rule_id);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(standard_id, src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(standard_id, dst);
"""

# 规则挂不上节点时，按 C 类推断应当补哪类节点
EXPECT_NODE = {
    'C1': 'constraint', 'C2': 'step', 'C3': 'instrument', 'C4': 'reagent',
    'C5': 'step', 'C6': 'step', 'C7': 'qc_gate', 'C8': 'record',
}


def ensure(con):
    con.executescript(DDL)


def _graph_path(out):
    for p in (os.path.join(out, 'sop-graph.json'),
              os.path.join(out, 'machine', 'sop-graph.json')):
        if os.path.exists(p):
            return p
    return None


def load(con, sid, out):
    """幂等载入：先清该 standard_id 的三张表，再按图重写。"""
    ensure(con)
    for t in ('nodes', 'edges', 'rule_node'):
        con.execute(f'DELETE FROM {t} WHERE standard_id=?', (sid,))
    p = _graph_path(out)
    if not p:
        return {'nodes': 0, 'edges': 0, 'rule_node': 0, 'graph': None}
    g = json.load(open(p, encoding='utf-8'))
    nodes = g.get('nodes') or []
    edges = g.get('edges') or []
    n_node = n_edge = n_link = 0
    for n in nodes:
        nid = n.get('node_id')
        if not nid:
            continue
        con.execute('INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?)', (
            sid, nid, n.get('type'), n.get('step') or n.get('name') or '',
            json.dumps(n.get('clauses') or [], ensure_ascii=False),
            json.dumps(n.get('params') or [], ensure_ascii=False),
            n.get('done_when') or '',
            json.dumps(n.get('basis') or [], ensure_ascii=False),
            n.get('usage') or 'criteria',
            json.dumps(n, ensure_ascii=False)))
        n_node += 1
        for rid in (n.get('criteria') or []):
            con.execute('INSERT OR REPLACE INTO rule_node VALUES (?,?,?,?)',
                        (sid, rid, nid, 'criteria'))
            n_link += 1
        for rid in (n.get('qualitative') or []):
            con.execute('INSERT OR REPLACE INTO rule_node VALUES (?,?,?,?)',
                        (sid, rid, nid, 'qualitative'))
            n_link += 1
    for e in edges:
        a, b = e.get('from'), e.get('to')
        if not a or not b:
            continue
        con.execute('INSERT OR REPLACE INTO edges VALUES (?,?,?,?)',
                    (sid, a, b, e.get('type') or ''))
        n_edge += 1
    return {'nodes': n_node, 'edges': n_edge, 'rule_node': n_link, 'graph': p}


def unmapped(con, sid):
    """规则表里没挂上任何节点的规则。返回带 category / title 的清单。"""
    mapped = {r[0] for r in con.execute(
        'SELECT DISTINCT rule_id FROM rule_node WHERE standard_id=?', (sid,))}
    out = []
    for rid, cat, cl, payload in con.execute(
            'SELECT rule_id, category, clause, payload FROM rules WHERE standard_id=?', (sid,)):
        if rid in mapped:
            continue
        title = ''
        try:
            title = (json.loads(payload) or {}).get('title') or ''
        except Exception:
            pass
        out.append({'rule_id': rid, 'category': cat, 'clause': cl, 'title': title})
    return out


def _types_by_clause(out):
    import collections
    p = _graph_path(out)
    d = collections.defaultdict(set)
    if not p:
        return d
    for n in (json.load(open(p, encoding='utf-8')).get('nodes') or []):
        cls = [str(c) for c in (n.get('clauses') or [])]
        if not cls:
            for a in (n.get('anchors') or []):
                if a and a.get('clause'):
                    cls = [str(a['clause'])]
        for cl in cls:
            d[cl].add(n.get('type'))
    return d


def write_gaps(out, sid, items, source='graph_index'):
    """未挂节点的规则 → machine/graph_gaps.json（登记缺口，不静默丢失）。"""
    tbc = _types_by_clause(out)
    by_cat = {}
    for x in items:
        by_cat[x.get('category') or '?'] = by_cat.get(x.get('category') or '?', 0) + 1
    doc = {
        'standard_id': sid, 'source': source, 'count': len(items),
        'by_category': by_cat,
        'items': [_gap_item(x, tbc) for x in items],
    }
    d = os.path.join(out, 'machine')
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, 'graph_gaps.json')
    json.dump(doc, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    return p


def lookup_rule(con, sid, rule_id):
    found = con.execute('SELECT 1 FROM rules WHERE standard_id=? AND rule_id=?',
                        (sid, rule_id)).fetchone() is not None
    rows = con.execute(
        'SELECT rn.node_id, rn.link, n.type, n.step, n.done_when FROM rule_node rn '
        'LEFT JOIN nodes n ON n.standard_id=rn.standard_id AND n.node_id=rn.node_id '
        'WHERE rn.standard_id=? AND rn.rule_id=?', (sid, rule_id)).fetchall()
    out = [{'node_id': r[0], 'link': r[1], 'type': r[2], 'step': r[3], 'done_when': r[4]}
           for r in rows]
    edges = []
    for r in out:
        for e in con.execute(
                'SELECT src, dst, type FROM edges WHERE standard_id=? AND (src=? OR dst=?)',
                (sid, r['node_id'], r['node_id'])):
            edges.append({'from': e[0], 'to': e[1], 'type': e[2]})
    return {'standard_id': sid, 'rule_id': rule_id, 'rule_found': found, 'nodes': out,
            'mapped': bool(out), 'edges': edges}


def lookup_node(con, sid, node_id):
    r = con.execute(
        'SELECT type, step, clauses, params, done_when, usage FROM nodes '
        'WHERE standard_id=? AND node_id=?', (sid, node_id)).fetchone()
    if not r:
        return {'standard_id': sid, 'node_id': node_id, 'found': False}
    rules = [{'rule_id': x[0], 'link': x[1]} for x in con.execute(
        'SELECT rule_id, link FROM rule_node WHERE standard_id=? AND node_id=?',
        (sid, node_id))]
    edges = con.execute(
        'SELECT src, dst, type FROM edges WHERE standard_id=? AND (src=? OR dst=?)',
        (sid, node_id, node_id)).fetchall()
    return {'standard_id': sid, 'node_id': node_id, 'found': True, 'type': r[0],
            'step': r[1], 'clauses': json.loads(r[2] or '[]'),
            'params': json.loads(r[3] or '[]'), 'done_when': r[4], 'usage': r[5],
            'rules': rules,
            'edges': [{'from': e[0], 'to': e[1], 'type': e[2]} for e in edges]}


def _gap_item(x, tbc):
    """按该条款已有节点类型区分缺口性质：无节点 / 只有依据类节点（不可当判据）。"""
    cl = str(x.get('clause') or '')
    types = tbc.get(cl) or set()
    if types and types <= {'justification', 'analyte'}:
        return {
            'rule_id': x['rule_id'], 'category': x.get('category'), 'clause': cl,
            'title': x.get('title') or '',
            'reason': 'ONLY_JUSTIFICATION_NODE',
            'expected_node_type': 'constraint',
            'fix': '该条款只抽出依据类（PERF/论证）要素，按红线不得当判据；'
                   '要么在要素层补一个 constraint 要素承载该要求，要么确认它属报告红线、改由 C8 记录节点承载',
            'pending_class': 'PENDING_DATA',
        }
    return {
        'rule_id': x['rule_id'], 'category': x.get('category'), 'clause': cl,
        'title': x.get('title') or '',
        'reason': 'MISSING_NODE',
        'expected_node_type': EXPECT_NODE.get(x.get('category') or '', 'step'),
        'fix': '在 sop-graph.json 补该类型节点，把 rule_id 写进 criteria 或 qualitative，再重跑该节点门禁',
        'pending_class': 'PENDING_DATA',
    }
