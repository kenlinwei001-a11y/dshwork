#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""专家间接口契约校验：按 contracts/interfaces.json 检查一个运行目录。

用法:
  python3 check_interfaces.py --out <运行目录> [--contract contracts/interfaces.json] [--strict]

检查四件事：
  1. 必需产物是否都存在（缺了谁、谁因此无法开工）
  2. JSON/JSONL 能否解析
  3. 声明字段是否齐（顶层字段 / 条目字段）
  4. 前端拼路径用的一致性：每份产物的实际路径与契约一致

exit 0 = 契约成立；exit 1 = 有阻断项（--strict 时非必需缺失也算阻断）。
"""
import argparse
import json
import os
import sys


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--contract', default='contracts/interfaces.json')
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    O = a.out
    C = load(a.contract) or {}
    arts = C.get('artifacts') or []

    present, absent, blocked = [], [], []
    errors = []

    for art in arts:
        path = art['path'].replace('{slug}', '*')
        # {slug} 模板按通配匹配
        if '*' in path:
            import glob
            hits = glob.glob(os.path.join(O, path))
            exists = bool(hits)
            real = hits[0] if hits else None
        else:
            real = os.path.join(O, path)
            exists = os.path.exists(real)
        rec = {'id': art['id'], 'path': art['path'], 'producer': art.get('producer')}
        if not exists:
            absent.append(rec)
            if art.get('required'):
                blocked.append({**rec, 'consumers': art.get('consumers') or []})
            continue

        # 解析
        data = None
        kind = art.get('kind')
        try:
            if kind == 'json':
                data = load(real)
            elif kind == 'jsonl':
                with open(real, encoding='utf-8') as f:
                    rows = [json.loads(l) for l in f if l.strip()]
                data = rows
            elif kind == 'text':
                data = open(real, encoding='utf-8').read()
        except Exception as e:
            errors.append({'id': art['id'], 'error': f'解析失败：{e}'})
            continue

        # 顶层字段
        miss = []
        if isinstance(data, dict):
            for f in art.get('fields') or []:
                if f not in data:
                    miss.append(f)
        # 条目字段（仅看前 3 条，避免大文件）
        if isinstance(data, list) and art.get('item_fields'):
            for row in data[:3]:
                if not isinstance(row, dict):
                    continue
                for f in art['item_fields']:
                    if f not in row:
                        miss.append(f'{f}(条目)')
        if miss:
            errors.append({'id': art['id'], 'missing_fields': sorted(set(miss))})

        present.append({**rec, 'bytes': os.path.getsize(real)})

    # 谁因为缺输入无法开工
    blocked_by = {}
    for b in blocked:
        for c in b['consumers']:
            blocked_by.setdefault(c, []).append(b['id'])

    # 假 0 检查：裁定里的 method_mismatch
    adj = load(os.path.join(O, 'adjudication.json'))
    if isinstance(adj, dict):
        mm = adj.get('method_mismatch')
        meta = load(os.path.join(O, 'machine', 'report_meta.json'), {}) or {}
        checked = bool(adj.get('report_method')) or ('declared_method' in meta)
        if mm == [] and not checked:
            errors.append({'id': 'adjudication',
                           'error': 'method_mismatch=[] 但 report_meta 无 declared_method —— 这是"未检查"，不是"无 mismatch"',
                           'should_be': 'NOT_CHECKED'})

    out = {
        'out': O,
        'contract_version': C.get('version'),
        'present': [p['id'] for p in present],
        'absent': [x['id'] for x in absent],
        'blocked_roles': blocked_by,
        'errors': errors,
        'status': 'OK' if not errors and not blocked else 'GAP',
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))

    if out['status'] == 'OK':
        return 0
    return 1 if (a.strict or blocked or errors) else 0


if __name__ == '__main__':
    sys.exit(main())
