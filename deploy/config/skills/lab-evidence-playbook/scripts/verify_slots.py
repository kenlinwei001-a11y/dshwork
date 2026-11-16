#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""证据抽取校验：只查确定性项，不判 PASS/FAIL。

用法:
  python3 verify_slots.py --out <运行目录>            # 校验并打印 JSON 结论
  python3 verify_slots.py --out <运行目录> --strict    # 有缺口时 exit 1（门禁用）

校验五件事：
  1. 覆盖率：audit_tasks.jsonl 的每个 slot 在 report_slots.json 里有键（值可为 null）
  2. 定位：有值的槽必须有 report_spans 条目且 quote 非空；quote 能在报告正文命中（给了 --report-text 才查）
  3. 类型：schema 声明 number 的槽，值必须是数字或可解析数字
  4. 缺失清单：值为 null 的槽必须出现在 missing 里，并带原因
  5. 不越权：本包内不得出现 verdict 字段（判定归审核专家）
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


def norm(s):
    return ''.join((s or '').split())


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
    ap.add_argument('--report-text', default='')
    ap.add_argument('--record-text', nargs='*', default=[],
                    help='过程记录正文；来自记录的 quote 在这些文件里命中即可')
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    O = a.out

    tasks = []
    tp = os.path.join(O, 'audit_tasks.jsonl')
    if os.path.exists(tp):
        tasks = [json.loads(l) for l in open(tp, encoding='utf-8') if l.strip()]

    slots = load(os.path.join(O, 'machine', 'report_slots.json'), {}) or {}
    spans = load(os.path.join(O, 'machine', 'report_spans.json'), {}) or {}
    missing = (load(os.path.join(O, 'machine', 'missing.json'), None)
               or load(os.path.join(O, 'machine', 'missing_documents.json'), []) or [])
    schema = load(os.path.join(O, 'slots.schema.json'), {}) or {}
    props = (schema.get('properties') or {})

    errs, warns = [], []
    task_slots = [t.get('slot') for t in tasks if t.get('slot')]

    # 1 覆盖率
    no_key = [s for s in task_slots if s not in slots]
    if no_key:
        errs.append({'check': 'coverage', 'detail': f'{len(no_key)} 个槽没有键：{no_key[:8]}'})

    # 2 定位
    no_span = []
    for s in task_slots:
        v = slots.get(s)
        if v in (None, '', []):
            continue
        sp = spans.get(s) or {}
        if not sp.get('quote'):
            no_span.append(s)
        elif sp.get('unlocated'):
            warns.append({'check': 'locator', 'detail': f'{s} 标为 unlocated（不可辨），已登记'})
    if no_span:
        errs.append({'check': 'locator', 'detail': f'有值但无 quote：{no_span[:8]}'})

    # quote 必须在报告正文里能命中
    texts = []
    for p_ in ([a.report_text] if a.report_text else []) + list(a.record_text or []):
        if p_ and os.path.exists(p_):
            texts.append(norm(open(p_, encoding='utf-8').read()))
    if texts:
        miss = [s for s in task_slots
                if (spans.get(s) or {}).get('quote')
                and not any(norm(spans[s]['quote']) in t for t in texts)]
        if miss:
            errs.append({'check': 'quote_hit', 'detail': f'{len(miss)} 条 quote 未命中报告原文：{miss[:8]}'})

    # 3 类型
    bad_type = []
    for s in task_slots:
        v = slots.get(s)
        if v in (None, '', []):
            continue
        want = (props.get(s) or {}).get('type')
        if want == 'number' and not isinstance(v, (int, float)):
            try:
                float(str(v))
            except Exception:
                bad_type.append({'slot': s, 'value': v, 'want': 'number'})
    if bad_type:
        errs.append({'check': 'type', 'detail': bad_type[:8]})

    # 4 缺失清单
    null_slots = [s for s in task_slots if slots.get(s) in (None, '', [])]
    miss_ids = {m.get('slot') for m in missing if isinstance(m, dict)}
    undeclared = [s for s in null_slots if s not in miss_ids]
    if undeclared:
        errs.append({'check': 'missing_declared', 'detail': f'{len(undeclared)} 个空槽未登记原因：{undeclared[:8]}'})
    no_reason = [m for m in missing if isinstance(m, dict) and not m.get('reason')]
    if no_reason:
        errs.append({'check': 'missing_reason', 'detail': f'{len(no_reason)} 条缺失没有 reason'})

    # 5 不越权
    verdict_keys = [k for k in slots if 'verdict' in str(k).lower()]
    if verdict_keys:
        errs.append({'check': 'no_verdict',
                     'detail': f'证据包内出现 verdict 字段（{verdict_keys[:5]}），判定归审核专家'})

    out = {
        'out': O,
        'slots_total': len(task_slots),
        'slots_filled': len([s for s in task_slots if slots.get(s) not in (None, '', [])]),
        'missing_declared': len(missing),
        'errors': errs,
        'warnings': warns,
        'verdict_field_present': bool(verdict_keys),
        'status': 'OK' if not errs else 'FAIL',
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if verdict_keys:
        print('提示：证据包内不应出现 verdict 字段，判定归审核专家。', file=sys.stderr)
    _write_trail(O, 'lab-evidence', not errs, f'slots {len(task_slots)} 条')
    if a.strict and errs:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
