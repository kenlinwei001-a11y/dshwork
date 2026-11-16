#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 SOP 关系图谱导出为人读/可 diff 的 YAML。

用法:
  python3 graph_to_yaml.py --out <运行目录> [--file sop-graph.json] [--stdout]

输入：<out>/sop-graph.json（nodes / edges / counts）
输出：<out>/machine/sop-graph.yaml

设计取舍：
  - 节点按 type 分组排序，边按 (type, from, to) 排序 —— 让 diff 只反映真实变化
  - criteria / qualitative 合成 rules.criteria / rules.qualitative，比原 JSON 好读
  - anchors 只保留第一个（其余进 anchors_all），避免 YAML 过长
  - 不丢信息：节点其余字段原样保留在 extra 之外（顶层平铺）
"""
import argparse
import json
import os
import sys

import yaml


def load(p, d=None):
    if not os.path.exists(p):
        return d
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def node_row(n):
    row = {'id': n.get('node_id'), 'type': n.get('type')}
    for k in ('step', 'name', 'field', 'statement', 'done_when', 'family', 'usage'):
        if n.get(k):
            row[k] = n[k]
    if n.get('clauses'):
        row['clauses'] = n['clauses']
    if n.get('params'):
        row['params'] = n['params']
    rules = {}
    if n.get('criteria'):
        rules['criteria'] = n['criteria']
    if n.get('qualitative'):
        rules['qualitative'] = n['qualitative']
    if rules:
        row['rules'] = rules
    anchors = n.get('anchors') or []
    if anchors:
        a = anchors[0] or {}
        row['anchor'] = {k: a.get(k) for k in ('clause', 'page') if a.get(k)}
        if a.get('quote'):
            q = a['quote']
            row['anchor']['quote'] = q if len(q) <= 120 else q[:117] + '...'
        if len(anchors) > 1:
            row['anchors_all'] = [{k: x.get(k) for k in ('clause', 'page')} for x in anchors[1:]]
    if n.get('basis'):
        row['basis'] = [b.get('node_id') if isinstance(b, dict) else b for b in n['basis']]
    if n.get('no_threshold'):
        row['no_threshold'] = True
    if n.get('conditional'):
        row['conditional'] = True
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--file', default='sop-graph.json')
    ap.add_argument('--stdout', action='store_true')
    a = ap.parse_args()
    O = a.out

    graph = load(os.path.join(O, a.file))
    if not graph:
        print(json.dumps({'error': f'{a.file} 不存在'}, ensure_ascii=False))
        return 2

    nodes = sorted((node_row(n) for n in (graph.get('nodes') or [])),
                   key=lambda r: (str(r.get('type')), str(r.get('id'))))
    edges = sorted(({'from': e.get('from'), 'to': e.get('to'), 'type': e.get('type')}
                    for e in (graph.get('edges') or [])),
                   key=lambda e: (str(e.get('type')), str(e.get('from')), str(e.get('to'))))

    doc = {
        'standard': graph.get('standard'),
        'source': a.file,
        'counts': graph.get('counts'),
        'rule_nodes': graph.get('rule_nodes'),
        'unattached_rules': graph.get('unattached_rules') or [],
        'invariants': {'errors': graph.get('invariant_error_count', 0),
                       'detail': (graph.get('invariant_errors') or [])[:5]},
        'nodes': nodes,
        'edges': edges,
    }

    text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=110,
                          default_flow_style=False)
    header = (f"# {graph.get('standard')} SOP 关系图谱（由 {a.file} 导出，勿手改）\n"
              f"# 节点 {len(nodes)} 个 / 边 {len(edges)} 条；重导出：python3 toolchain/run.py std.graph_yaml --out <运行目录>\n")
    out_text = header + text

    if a.stdout:
        print(out_text)
        return 0

    dst = os.path.join(O, 'machine', 'sop-graph.yaml')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(out_text)
    print(json.dumps({'written': dst, 'nodes': len(nodes), 'edges': len(edges),
                      'bytes': len(out_text.encode()), 'counts': graph.get('counts')},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
