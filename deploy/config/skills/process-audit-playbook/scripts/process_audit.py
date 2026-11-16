#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""过程文档审核（C2–C5/C7）确定性执行器。

agent 侧唯一入口，不读任何 md：
  python3 process_audit.py --out <运行目录> --check    # 缺什么、该做什么
  python3 process_audit.py --out <运行目录>            # 确定性判定 + 缺证派 owner + 冲突并列
  python3 process_audit.py --out <运行目录> --verify   # 校验
  python3 process_audit.py --out <运行目录> --strict   # verify 不通过 exit 1

做四件事（确定性，不叫模型）：
  1. 筛 C2–C5/C7 任务
  2. 采信 eval_slots 谓词结论（不重算）
  3. 缺证 → UNVERIFIABLE + pending_class + owner（按类别派，不问人）
  4. 记录冲突 → CONFLICT_PENDING，必须并列两处原文（两侧都要 page+quote）

模型只补：定性三档、冲突是否需要人裁的解释。脚本把「哪些条需要人」列清楚。
"""
import argparse
import json
import os
import sys

CATS = ('C2', 'C3', 'C4', 'C5', 'C7')
VERDICTS = ('PASS', 'FAIL', 'UNVERIFIABLE', 'NOT_APPLICABLE', 'CONFLICT_PENDING')
PENDING = ('PENDING_DATA', 'PENDING_DOC', 'PENDING_REF', 'LAB_POLICY', 'PENDING_USER')
# 缺证时责任方：不问人，先派给该给的人
OWNER = {
    'PENDING_DATA': '实验室（补数据/补记录）',
    'PENDING_DOC': '实验室（提交 SOP/说明书/记录模板）',
    'PENDING_REF': '标准归口 / 用户（上传被引文件）',
    'LAB_POLICY': '实验室技术负责人（内部规定）',
    'PENDING_USER': '用户（只能人裁）',
}
# 文档类型决定缺的是"证"还是"规程"
DOC2PENDING = {'试剂配制记录': 'PENDING_DATA', '仪器使用记录': 'PENDING_DATA',
               '前处理记录': 'PENDING_DATA', '质控记录': 'PENDING_DATA',
               '样品流转单': 'PENDING_DATA', '仪器说明书': 'PENDING_DOC',
               'SOP': 'PENDING_DOC'}


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
    d = load(os.path.join(O, 'audit_results.json'), [])
    if isinstance(d, dict):
        d = d.get('results') or d.get('items') or []
    return {r.get('rule_id'): r for r in d if isinstance(r, dict)}


def conflicts_of(O):
    """记录冲突：来自 consistency_flags（证据抽取侧只报事实，不判定）。"""
    flags = load(os.path.join(O, 'machine', 'consistency_flags.json'), []) or []
    out = {}
    for f in flags:
        for rid in (f.get('rule_ids') or []):
            out.setdefault(rid, []).append(f)
    return out


def judge(O):
    tasks = [t for t in read_tasks(O) if t.get('category') in CATS]
    slots = load(os.path.join(O, 'machine', 'report_slots.json'), {}) or {}
    spans = load(os.path.join(O, 'machine', 'report_spans.json'), {}) or {}
    results = read_results(O)
    conflicts = conflicts_of(O)

    items, pending_human = [], []
    for t in tasks:
        rid, slot = t.get('rule_id'), t.get('slot')
        span = spans.get(slot) or {}
        anchor = t.get('anchor') or {}
        r = results.get(rid) or {}
        verdict = r.get('verdict') or 'UNVERIFIABLE'
        message = r.get('message') or ''
        basis = 'eval_slots'
        qualitative = bool(t.get('qualitative')) or (
            t.get('op') in (None, '') and t.get('value') in (None, '', []))
        pclass = None

        if slots.get(slot) in (None, '', []):
            verdict, message, basis = 'UNVERIFIABLE', '缺证：该记录未取到值', 'missing_evidence'
        if verdict == 'PASS' and not span.get('quote'):
            verdict, message, basis = 'UNVERIFIABLE', 'PASS 无记录定位，降级', 'downgrade_no_span'

        # 记录冲突：两侧都在才判冲突，只有一侧就是缺证
        if rid in conflicts:
            both = [c for c in conflicts[rid]
                    if (c.get('a') or {}).get('quote') and (c.get('b') or {}).get('quote')]
            if both:
                verdict, basis = 'CONFLICT_PENDING', 'conflict'
                message = both[0].get('what') or '两处记录不一致'
            else:
                verdict, basis = 'UNVERIFIABLE', 'conflict_one_side'

        if verdict == 'UNVERIFIABLE':
            pclass = DOC2PENDING.get(t.get('doc_type') or '', 'PENDING_DATA')
        if qualitative and verdict in ('PASS', 'UNVERIFIABLE'):
            pending_human.append({'rule_id': rid, 'slot': slot, 'label': t.get('label'),
                                  'question': '定性三档：符合 / 不符合 / 缺证'})

        if verdict not in VERDICTS:
            verdict, message = 'UNVERIFIABLE', f'非法判定 {verdict}，降级'

        items.append({
            'rule_id': rid, 'category': t.get('category'), 'slot': slot,
            'doc_type': t.get('doc_type'),
            'verdict': verdict, 'message': message,
            'record_span': span or None,
            'std_anchor': anchor,
            'basis': basis,
            'pending_class': pclass,
            'owner': OWNER.get(pclass) if pclass else None,
            'conflict': (conflicts.get(rid) or [None])[0] if verdict == 'CONFLICT_PENDING' else None,
        })

    counts = {v: sum(1 for x in items if x['verdict'] == v) for v in VERDICTS}
    doc = {'standard_id': (load(os.path.join(O, 'ses.json'), {}) or {}).get('standard_id'),
           'items': items, 'counts': counts,
           'owners': {k: sum(1 for x in items if x.get('pending_class') == k)
                      for k in PENDING if any(x.get('pending_class') == k for x in items)},
           'pending_human': pending_human}
    dump(os.path.join(O, 'machine', 'process_findings.json'), doc)
    return doc


def verify(O):
    p = os.path.join(O, 'machine', 'process_findings.json')
    if not os.path.exists(p):
        print(json.dumps({'verify': 'FAIL', 'error': 'process_findings.json 缺失'}, ensure_ascii=False))
        return 1
    d = load(p)
    items = d.get('items') or []
    errs = []
    for x in items:
        rid = x.get('rule_id')
        if not (x.get('std_anchor') or {}).get('clause'):
            errs.append(f'{rid}: 缺 std_anchor.clause')
        v = x.get('verdict')
        if v not in VERDICTS:
            errs.append(f'{rid}: 非法判定 {v}')
        if v == 'UNVERIFIABLE':
            if x.get('pending_class') not in PENDING:
                errs.append(f'{rid}: 缺证但 pending_class 非法（{x.get("pending_class")}）')
            elif not x.get('owner'):
                errs.append(f'{rid}: 缺证但没派 owner')
        if v == 'CONFLICT_PENDING':
            c = x.get('conflict') or {}
            if not ((c.get('a') or {}).get('quote') and (c.get('b') or {}).get('quote')):
                errs.append(f'{rid}: 冲突未并列两处原文')
        if v == 'PASS' and not (x.get('record_span') or {}).get('quote'):
            errs.append(f'{rid}: PASS 但无 record_span.quote')
    actual = {v: sum(1 for x in items if x.get('verdict') == v) for v in VERDICTS}
    if actual != (d.get('counts') or {}):
        errs.append(f'counts 不一致：明细 {actual} vs 声明 {d.get("counts")}')
    out = {'verify': 'PASS' if not errs else 'FAIL', 'items': len(items),
           'counts': actual, 'owners': d.get('owners'), 'errors': errs[:20],
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
                          'c2_c5_c7_tasks': len(tasks),
                          'conflicts_declared': len(conflicts_of(O)),
                          'next': 'python3 process_audit.py --out %s' % O,
                          'then': 'python3 process_audit.py --out %s --verify' % O},
                         ensure_ascii=False, indent=1))
        return 0 if not miss else 2

    if a.verify:
        rc = verify(O)
        _write_trail(O, 'process-audit', rc == 0, 'process_findings 自校验')
        return rc if a.strict else 0

    doc = judge(O)
    print(json.dumps({'items': len(doc['items']), 'counts': doc['counts'],
                      'owners': doc['owners'], 'pending_human': len(doc['pending_human']),
                      'written': os.path.join(O, 'machine', 'process_findings.json')},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
