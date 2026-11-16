#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐样品判定引擎：填补「单值槽装不下结果表」的缺口。

用法:
  python3 eval_sample_slots.py --out <运行目录> [--rules contracts/sample_rules.json] [--verify]

做什么（全确定性）：
  1. 读 machine/tables.json（表格抽取产物）与 contracts/sample_rules.json
  2. 每条规则按列名/别名找到列，逐样品判一次（sig3_or_3dp / range / not_nd）
  3. 逐样品结论带 page + quote（原文连续片段），ND/空值判 NOT_APPLICABLE 或 UNVERIFIABLE
  4. 按 aggregate.worst 聚合成规则级结论，写 machine/sample_results.json

不猜：列找不到 → 规则级 UNVERIFIABLE 并写 column_missing；不合格式 → FAIL 并给期望格式。
"""
import argparse
import json
import os
import re
import sys

ORDER = ['FAIL', 'CONFLICT_PENDING', 'UNVERIFIABLE', 'NOT_APPLICABLE', 'PASS']
ND = ('ND', 'nd', 'n.a.', 'N.A.', '—', '-', '未检出')


def load(p, d=None):
    if not os.path.exists(p):
        return d
    return json.load(open(p, encoding='utf-8'))


def sig_figs(num_text):
    t = num_text.strip().lstrip('+-')
    t = t.split('e')[0].split('E')[0].replace('.', '')
    t = t.lstrip('0')
    return len(t)


def decimals(num_text):
    return len(num_text.split('.')[1]) if '.' in num_text else 0


def check_sig3_or_3dp(val_text, threshold=1.0):
    """§9.2：<1 保留三位小数；≥1 保留三位有效数字。"""
    try:
        v = float(val_text)
    except Exception:
        return 'UNVERIFIABLE', f'值「{val_text}」不是数值，需回原文核对'
    if v < threshold:
        d = decimals(val_text)
        if d == 3:
            return 'PASS', f'{val_text} <{threshold}，保留三位小数 ✓'
        return 'FAIL', f'{val_text} <{threshold} 应保留三位小数，实为 {d} 位'
    s = sig_figs(val_text)
    if s == 3:
        return 'PASS', f'{val_text} ≥{threshold}，三位有效数字 ✓'
    return 'FAIL', f'{val_text} ≥{threshold} 应保留三位有效数字，实为 {s} 位'


def check_range(val_text, params):
    """值是否 ≥ 测定下限（检出限）；ND 由上层判 NOT_APPLICABLE。"""
    try:
        v = float(val_text)
    except Exception:
        return 'UNVERIFIABLE', f'值「{val_text}」不是数值'
    lo = params.get('min')
    if lo is None:
        return 'UNVERIFIABLE', '缺下限'
    if v < lo:
        return 'FAIL', f'{v} < 检出限 {lo}（且非 ND）'
    return 'PASS', f'{v} ≥ 检出限 {lo}'


CHECKS = {'sig3_or_3dp': lambda v, p: check_sig3_or_3dp(v, p.get('threshold', 1.0)),
          'range': check_range}


def pick_column(table, rule):
    cols = table.get('columns') or []
    want = [rule['column']] + list(rule.get('column_aliases') or [])
    for w in want:
        for c in cols:
            if c == w or w in c or c in w:
                return c
    # 退化：按前缀比（PO4 / PO3- 这类 OCR 变体）
    key = re.sub(r'[^A-Za-z]', '', rule['column']).upper()
    for c in cols:
        cc = re.sub(r'[^A-Za-z]', '', c).upper()
        if key and (cc.startswith(key[:2]) and abs(len(cc) - len(key)) <= 3):
            return c
    return None


def _write_trail(O, node, ok, detail=''):
    """verify 结果必须落盘：没有 trail 记录 = 没跑过，门禁会拒。"""
    import datetime
    p = os.path.join(O, 'trail.jsonl')
    with open(p, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'step': 'verify', 'node': node, 'pass': bool(ok),
                            'detail': detail,
                            'at': datetime.datetime.now().isoformat(timespec='seconds')},
                           ensure_ascii=False) + '\n')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--rules', default='contracts/sample_rules.json')
    ap.add_argument('--verify', action='store_true')
    a = ap.parse_args()
    O = a.out

    if a.verify:
        p = os.path.join(O, 'machine', 'sample_results.json')
        if not os.path.exists(p):
            print(json.dumps({'verify': 'FAIL', 'error': 'sample_results.json 缺失'}, ensure_ascii=False))
            return 1
        d = load(p)
        errs = []
        for r in d.get('rules') or []:
            for it in r.get('samples') or []:
                if it['verdict'] not in ORDER:
                    errs.append(f"{r['rule_id']}/{it['sample_id']}: 非法判定 {it['verdict']}")
                if it['verdict'] == 'PASS' and not it.get('quote'):
                    errs.append(f"{r['rule_id']}/{it['sample_id']}: PASS 无 quote")
            agg = worst([it['verdict'] for it in r.get('samples') or []])
            if agg != r.get('verdict'):
                errs.append(f"{r['rule_id']}: 聚合不一致（明细 {agg} vs 声明 {r.get('verdict')}）")
        out = {'verify': 'PASS' if not errs else 'FAIL', 'errors': errs[:20],
               'rules': len(d.get('rules') or [])}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        _write_trail(O, 'sample-eval', not errs, f'{len(d.get("rules") or [])} 条逐样品规则')
        return 0 if not errs else 1

    tables = (load(os.path.join(O, 'machine', 'tables.json'), {}) or {}).get('tables') or []
    rules = (load(a.rules, {}) or {}).get('rules') or []
    if not tables:
        print(json.dumps({'error': 'machine/tables.json 无表格，先跑 extract_tables'}, ensure_ascii=False))
        return 2

    table = tables[0]
    out_rules = []
    for rule in rules:
        col = pick_column(table, rule)
        if not col:
            out_rules.append({'rule_id': rule['rule_id'], 'clause': rule['clause'],
                              'column': rule['column'], 'column_found': None,
                              'verdict': 'UNVERIFIABLE', 'samples': [],
                              'column_missing': True, 'anchor': rule.get('anchor')})
            continue
        fn = CHECKS.get(rule['check'])
        samples = []
        for row in table.get('rows') or []:
            cells = (row.get('cells') or {}).get(col) or []
            if not cells:
                samples.append({'sample_id': row['sample_id'], 'verdict': 'UNVERIFIABLE',
                                'value': None, 'quote': None, 'message': '该样品此列无值'})
                continue
            cell = cells[0]
            raw = str(cell.get('value') or '').strip()
            if raw in ND:
                samples.append({'sample_id': row['sample_id'], 'verdict': 'NOT_APPLICABLE',
                                'value': raw, 'quote': cell.get('quote'), 'page': cell.get('page'),
                                'message': '未检出（ND），结果表示不适用'})
                continue
            verdict, msg = fn(raw, rule.get('params') or {}) if fn else ('UNVERIFIABLE', '未实现的 check')
            samples.append({'sample_id': row['sample_id'], 'verdict': verdict, 'value': raw,
                            'quote': cell.get('quote'), 'page': cell.get('page'), 'message': msg})
        out_rules.append({'rule_id': rule['rule_id'], 'clause': rule['clause'], 'column': col,
                          'column_found': col, 'verdict': worst([s['verdict'] for s in samples]),
                          'samples': samples, 'anchor': rule.get('anchor'),
                          'origin': rule.get('origin')})

    doc = {'table_source': 'machine/tables.json', 'rows': len(table.get('rows') or []),
           'rules': out_rules,
           'counts': {v: sum(1 for r in out_rules if r['verdict'] == v) for v in ORDER}}
    os.makedirs(os.path.join(O, 'machine'), exist_ok=True)
    json.dump(doc, open(os.path.join(O, 'machine', 'sample_results.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)

    summary = []
    for r in out_rules:
        c = {v: sum(1 for s in r['samples'] if s['verdict'] == v) for v in ORDER}
        summary.append({'rule_id': r['rule_id'], 'column': r.get('column_found'),
                        'verdict': r['verdict'], 'samples': len(r['samples']),
                        'by_verdict': {k: v for k, v in c.items() if v}})
    print(json.dumps({'rows': doc['rows'], 'rules': summary}, ensure_ascii=False, indent=1))
    return 0


def worst(vs):
    for v in ORDER:
        if v in vs:
            return v
    return 'UNVERIFIABLE'


if __name__ == '__main__':
    sys.exit(main())
