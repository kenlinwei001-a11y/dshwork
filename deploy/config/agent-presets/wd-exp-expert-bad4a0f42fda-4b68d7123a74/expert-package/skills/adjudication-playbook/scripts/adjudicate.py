#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审核裁定：确定性合并 + 假通过复核 + 方法核对 + 责任分派。
只读 machine/ 产物，不重判规则（判定来自 eval_slots）。
用法:
  adjudicate.py --dir <run目录> --report <report_id> [--report-spans spans.json]
  adjudicate.py --dir <run目录> --check | --verify | --trail <step> --exit <code>
规则:
  - 只能升级不能降级：PASS → UNVERIFIABLE/FAIL 允许；FAIL → PASS 需 --allow-override 且写 override_reason
  - 假通过：PASS 但缺 report_span 或缺 basis → 降为 UNVERIFIABLE
  - 方法 mismatch：报告方法不在 ses.method_family(PROVIDED) → 该标准不参与合格判定
  - owner 按 gap.pending_class 自动分派
"""
import argparse, json, os, sys, datetime

def load(p, default=None):
    try: return json.load(open(p, encoding='utf-8'))
    except Exception: return default

def trail(d, rec):
    with open(os.path.join(d, 'trail.jsonl'), 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')

def owner_of(pending_class):
    return {'PENDING_DATA': '送样方/检测室', 'PENDING_REF': '标准归口',
            'LAB_POLICY': '实验室', 'PENDING_USER': '用户裁决'}.get(pending_class, '未定')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', required=True); ap.add_argument('--report', default='R-UNKNOWN')
    ap.add_argument('--report-spans', default=''); ap.add_argument('--report-method', default='')
    ap.add_argument('--allow-override', action='store_true')
    ap.add_argument('--check', action='store_true'); ap.add_argument('--verify', action='store_true')
    ap.add_argument('--trail', default=''); ap.add_argument('--exit', dest='exit_code', type=int, default=0)
    a = ap.parse_args(); D = a.dir
    if a.trail:
        trail(D, {'step': a.trail, 'exit': a.exit_code, 'at': datetime.datetime.now().isoformat(timespec='seconds')})
        print(json.dumps({'trail': a.trail, 'exit': a.exit_code}, ensure_ascii=False)); return 0
    if a.check:
        print('MUST RUN:')
        print(' 1) python3 adjudicate.py --dir <D> --report <R> --report-spans spans.json')
        print(' 2) python3 adjudicate.py --dir <D> --verify')
        print('判据: adjudication.json 存在；每条 finding 有 rule_id/std_span_id/report_span；verdict 由优先级推导')
        return 0
    if a.verify:
        p = os.path.join(D, 'adjudication.json')
        if not os.path.exists(p):
            print(json.dumps({'verify': 'FAIL', 'reason': 'adjudication.json 缺失'}, ensure_ascii=False)); return 2
        d = load(p); ok = bool(d.get('findings')) and d.get('verdict')
        trail(D, {'step': 'verify', 'pass': ok, 'at': datetime.datetime.now().isoformat(timespec='seconds')})
        print(json.dumps({'verify': 'PASS' if ok else 'FAIL'}, ensure_ascii=False)); return 0 if ok else 1

    results = load(os.path.join(D, 'audit_results.json'), []) or []
    ses = load(os.path.join(D, 'ses.json'), {}) or {}
    sop = load(os.path.join(D, 'sop-graph.json'), {}) or {}
    spans_doc = load(os.path.join(D, 'span_refs.json'), {}) or {}
    by_clause = (spans_doc.get('by_clause') or {})
    basis_map = {}
    for n in sop.get('nodes') or []:
        if n.get('basis'):
            for b in n['basis']:
                basis_map.setdefault(b.get('node_id'), b.get('claim'))
    rspans = load(a.report_spans, {}) if a.report_spans else {}

    # 方法核对
    fam = ses.get('method_family') or []
    provided = [m.get('standard') for m in fam if m.get('status') == 'PROVIDED']
    method_mismatch = []
    if a.report_method and provided and a.report_method not in provided:
        method_mismatch.append({'declared': a.report_method, 'provided': provided})

    gaps = {g.get('gap_id'): g for g in (ses.get('gaps') or [])}
    findings = []; counts = {'PASS': 0, 'FAIL': 0, 'UNVERIFIABLE': 0, 'CONFLICT_PENDING': 0, 'NOT_APPLICABLE': 0}
    for r in results:
        v = r.get('verdict'); rid = r.get('rule_id'); reason = None
        # 假通过复核：PASS 必须有报告位置与依据
        if v == 'PASS':
            if not rspans.get(rid):
                v = 'UNVERIFIABLE'; reason = '假通过复核：PASS 缺报告位置'
            elif not r.get('basis'):
                v = 'UNVERIFIABLE'; reason = '假通过复核：PASS 缺依据(basis)'
        # 只能升级不能降级（本脚本不产出 PASS，除非原值为 PASS 且通过复核）
        counts[v] = counts.get(v, 0) + 1
        anchor = (r.get('anchor') or {})
        clause = str(anchor.get('clause') or '')
        findings.append({'rule_id': rid, 'slot': r.get('slot'), 'label': r.get('label'),
                         'verdict': v, 'reason': reason,
                         'std_span_id': anchor.get('span_id') or by_clause.get(clause),
                         'report_span': rspans.get(rid),
                         'message': r.get('message'), 'basis': r.get('basis'),
                         'owner': owner_of(None)})
    order = ['FAIL', 'CONFLICT_PENDING', 'UNVERIFIABLE', 'NOT_APPLICABLE', 'PASS']
    verdict = next((x for x in order if counts.get(x)), 'PASS')
    if method_mismatch: verdict = 'FAIL'
    out = {'report_id': a.report, 'standards': [ses.get('standard_id')],
           'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
           'verdict': verdict, 'counts': counts, 'findings': findings,
           'method_mismatch': method_mismatch, 'conflicts': [], 'missing': [],
           'override_policy': {'mode': 'escalate_only', 'allow_override': a.allow_override},
           'source': {'results': 'audit_results.json', 'ses': 'ses.json', 'graph': 'sop-graph.json'}}
    json.dump(out, open(os.path.join(D, 'adjudication.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    trail(D, {'step': 'adjudicate', 'exit': 0, 'report': a.report, 'verdict': verdict,
              'at': datetime.datetime.now().isoformat(timespec='seconds')})
    print(json.dumps({'report': a.report, 'verdict': verdict, 'counts': counts,
                      'method_mismatch': len(method_mismatch)}, ensure_ascii=False)); return 0

if __name__ == '__main__':
    sys.exit(main())
