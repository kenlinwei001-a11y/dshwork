#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""报告审核（C1/C6）确定性执行器。

agent 侧唯一入口，不读任何 md：
  python3 report_audit.py --out <运行目录> --check    # 检查输入齐不齐、该做什么
  python3 report_audit.py --out <运行目录>            # 准备 + 确定性判定 + 假通过降级
  python3 report_audit.py --out <运行目录> --verify   # 校验结论完整性
  python3 report_audit.py --out <运行目录> --strict   # verify 不通过则 exit 1

做四件事（全部确定性，不叫模型）：
  1. 筛 C1/C6 任务，拼装审核输入
  2. 采信 eval_slots 的谓词结论（不重算）
  3. 三条假通过降级：PASS 无 report_span / PASS 无 basis / 定性卡给 PASS
  4. 定性卡标 pending_human（三档需人判），不擅自给 PASS

模型只在需要时补：定性卡三档、方法 mismatch、冲突并列。脚本把「哪些条需要人」列清楚。
"""
import argparse
import json
import os
import sys

CATS = ('C1', 'C6')
VERDICTS = ('PASS', 'FAIL', 'UNVERIFIABLE', 'NOT_APPLICABLE', 'CONFLICT_PENDING')


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def dump(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def read_tasks(O):
    p = os.path.join(O, 'audit_tasks.jsonl')
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]


def read_results(O):
    """eval_slots 结果：支持 list 或 {results:[...]} 两种形态。"""
    d = load(os.path.join(O, 'audit_results.json'), [])
    if isinstance(d, dict):
        d = d.get('results') or d.get('items') or []
    return {r.get('rule_id'): r for r in d if isinstance(r, dict)}


def prepare(O):
    tasks = [t for t in read_tasks(O) if t.get('category') in CATS]
    slots = load(os.path.join(O, 'machine', 'report_slots.json'), {}) or {}
    spans = load(os.path.join(O, 'machine', 'report_spans.json'), {}) or {}
    results = read_results(O)
    doc = {'tasks': tasks, 'slots': slots, 'spans': spans,
           'results': [results[t['rule_id']] for t in tasks if t.get('rule_id') in results]}
    dump(os.path.join(O, 'machine', 'report_audit_input.json'), doc)
    return tasks, slots, spans, results


def judge(O, tasks, slots, spans, results):
    items, downgraded, pending_human = [], [], []
    for t in tasks:
        rid, slot = t.get('rule_id'), t.get('slot')
        span = spans.get(slot) or {}
        anchor = t.get('anchor') or {}
        r = results.get(rid) or {}
        verdict = r.get('verdict') or 'UNVERIFIABLE'
        message = r.get('message') or ''
        basis = 'eval_slots'
        # 定性卡判定：任务单里 op/value 都没有才算定性（audit_tasks 用 op/value，不用 predicate）
        qualitative = bool(t.get('qualitative')) or (
            t.get('op') in (None, '') and t.get('value') in (None, '', []))
        ceiling = (t.get('ceiling') or '').upper()

        # 缺证：没有值 → UNVERIFIABLE（不判 FAIL）
        if slots.get(slot) in (None, '', []):
            verdict, message, basis = 'UNVERIFIABLE', '缺证：该槽未取到值', 'missing_evidence'

        # 三条假通过降级
        if verdict == 'PASS':
            if not span.get('quote'):
                downgraded.append({'rule_id': rid, 'from': 'PASS', 'reason': 'no_span'})
                verdict, message, basis = 'UNVERIFIABLE', 'PASS 无报告定位，降级', 'downgrade_no_span'
            elif not anchor.get('clause'):
                downgraded.append({'rule_id': rid, 'from': 'PASS', 'reason': 'no_basis'})
                verdict, message, basis = 'UNVERIFIABLE', 'PASS 无条款依据，降级', 'downgrade_no_basis'
            elif qualitative or ceiling == 'NO_PASS':
                downgraded.append({'rule_id': rid, 'from': 'PASS', 'reason': 'qualitative_no_pass'})
                verdict, message, basis = 'UNVERIFIABLE', '定性卡不得给 PASS，降级', 'downgrade_qualitative'

        if qualitative and verdict not in ('FAIL', 'NOT_APPLICABLE'):
            pending_human.append({'rule_id': rid, 'slot': slot,
                                  'label': t.get('label'),
                                  'question': '定性三档：符合 / 不符合 / 缺证（人工判）'})

        if verdict not in VERDICTS:
            verdict, message = 'UNVERIFIABLE', f'非法判定 {verdict}，降级'

        items.append({
            'rule_id': rid, 'category': t.get('category'), 'slot': slot,
            'verdict': verdict, 'message': message,
            'report_span': span or None,
            'std_anchor': anchor,
            'basis': basis,
            'pending_class': None if verdict != 'UNVERIFIABLE' else 'PENDING_DATA',
        })

    # 逐样品判定结果并入（singleton 槽装不下的结果表结论）
    sr = load(os.path.join(O, 'machine', 'sample_results.json'), {}) or {}
    for r in sr.get('rules') or []:
        if not r.get('verdict'):
            continue
        items.append({
            'rule_id': r['rule_id'], 'category': 'C6', 'slot': None,
            'verdict': r['verdict'],
            'message': f"{r.get('column_found')} 逐样品判定：{len(r.get('samples') or [])} 个样品",
            'report_span': None,
            'std_anchor': r.get('anchor') or {},
            'basis': 'sample_level',
            'pending_class': 'PENDING_DATA' if r['verdict'] == 'UNVERIFIABLE' else None,
            'samples': [{'sample_id': s['sample_id'], 'verdict': s['verdict'],
                         'value': s.get('value'), 'quote': s.get('quote')}
                        for s in (r.get('samples') or [])],
        })

    counts = {v: sum(1 for x in items if x['verdict'] == v) for v in VERDICTS}
    doc = {'standard_id': (load(os.path.join(O, 'ses.json'), {}) or {}).get('standard_id'),
           'report_id': (load(os.path.join(O, 'machine', 'report_meta.json'), {}) or {}).get('report_id'),
           'items': items, 'counts': counts,
           'downgraded': downgraded, 'pending_human': pending_human}
    dump(os.path.join(O, 'machine', 'report_findings.json'), doc)
    return doc


def verify(O):
    p = os.path.join(O, 'machine', 'report_findings.json')
    if not os.path.exists(p):
        print(json.dumps({'verify': 'FAIL', 'error': 'report_findings.json 缺失'}, ensure_ascii=False))
        return 1
    d = load(p)
    items = d.get('items') or []
    errs = []
    for x in items:
        rid = x.get('rule_id')
        if not x.get('std_anchor', {}).get('clause'):
            errs.append(f'{rid}: 缺 std_anchor.clause')
        if x.get('verdict') == 'PASS' and not (x.get('report_span') or {}).get('quote'):
            errs.append(f'{rid}: PASS 但无 report_span.quote')
        if x.get('verdict') not in VERDICTS:
            errs.append(f'{rid}: 非法判定 {x.get("verdict")}')
    actual = {v: sum(1 for x in items if x.get('verdict') == v) for v in VERDICTS}
    if actual != (d.get('counts') or {}):
        errs.append(f'counts 不一致：明细 {actual} vs 声明 {d.get("counts")}')
    for g in d.get('downgraded') or []:
        hit = [x for x in items if x.get('rule_id') == g.get('rule_id')]
        if not hit or hit[0].get('verdict') != 'UNVERIFIABLE':
            errs.append(f'{g.get("rule_id")}: downgraded 记录无对应 UNVERIFIABLE')
    out = {'verify': 'PASS' if not errs else 'FAIL', 'items': len(items),
           'counts': actual, 'errors': errs[:20],
           'pending_human': len(d.get('pending_human') or [])}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if not errs else 1


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
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    O = a.out

    if a.check:
        miss = [n for n in ('audit_tasks.jsonl', 'machine/report_slots.json',
                            'machine/report_spans.json', 'audit_results.json')
                if not os.path.exists(os.path.join(O, n))]
        tasks = [t for t in read_tasks(O) if t.get('category') in CATS]
        print(json.dumps({'out': O, 'missing_inputs': miss,
                          'c1_c6_tasks': len(tasks),
                          'next': 'python3 report_audit.py --out %s' % O,
                          'then': 'python3 report_audit.py --out %s --verify' % O},
                         ensure_ascii=False, indent=1))
        return 0 if not miss else 2

    if a.verify:
        rc = verify(O)
        _write_trail(O, 'report-audit', rc == 0, 'report_findings 自校验')
        return rc if a.strict else 0

    tasks, slots, spans, results = prepare(O)
    doc = judge(O, tasks, slots, spans, results)
    print(json.dumps({'items': len(doc['items']), 'counts': doc['counts'],
                      'downgraded': len(doc['downgraded']),
                      'pending_human': len(doc['pending_human']),
                      'written': os.path.join(O, 'machine', 'report_findings.json')},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
