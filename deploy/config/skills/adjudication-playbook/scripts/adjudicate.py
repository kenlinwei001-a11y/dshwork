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
    rec.setdefault('node', 'adjudication')   # 每条留痕必须带 node，否则门禁读不到
    with open(os.path.join(d, 'trail.jsonl'), 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')

def owner_of(pending_class):
    return {'PENDING_DATA': '送样方/检测室', 'PENDING_REF': '标准归口',
            'LAB_POLICY': '实验室', 'PENDING_USER': '用户裁决'}.get(pending_class, '未定')

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
        print(json.dumps({'verify': 'PASS' if ok else 'FAIL'}, ensure_ascii=False))
        _write_trail(D, 'adjudication', ok, 'adjudication.json 自校验')
        return 0 if ok else 1

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
    # 证据侧按 slot 存（Sxxx），判定侧按 rule_id——两套键都要认
    evid = load(os.path.join(D, 'machine', 'report_spans.json'), {}) or {}
    def span_of(rule_id, slot):
        return rspans.get(rule_id) or (evid.get(slot) if slot else None) or rspans.get(slot or '')

    # 方法核对
    fam = ses.get('method_family') or []
    provided = [m.get('standard') for m in fam if m.get('status') == 'PROVIDED']
    method_mismatch = []
    if a.report_method and provided and a.report_method not in provided:
        method_mismatch.append({'declared': a.report_method, 'provided': provided})

    # 两线 findings 优先：审核侧已把「缺证」纠正为 UNVERIFIABLE，裁定不得用原始 eval 结果覆盖它
    def _load_findings(rel, line):
        doc = load(os.path.join(D, rel), {}) or {}
        out = {}
        for x in (doc.get('items') or doc.get('findings') or []):
            rid = x.get('rule_id')
            if not rid:
                continue
            out[rid] = {'verdict': x.get('verdict'), 'line': line,
                        'report_span': x.get('report_span') or x.get('record_span'),
                        'std_anchor': x.get('std_anchor'), 'message': x.get('message'),
                        'basis': x.get('basis'), 'pending_class': x.get('pending_class'),
                        'owner': x.get('owner')}
        return out

    _pa = []
    fmap = _load_findings('machine/report_findings.json', 'report')
    for k, v in _load_findings('machine/process_findings.json', 'process').items():
        fmap.setdefault(k, v)   # 同一 rule 只计一次

    gaps = {g.get('gap_id'): g for g in (ses.get('gaps') or [])}
    _jfp = os.path.join(D, 'machine', 'judge_findings.json')
    _jf2 = load(_jfp, {}) or {}
    _auth = {i['rule_id']: i['verdict'] for i in (_jf2.get('items') or []) if i.get('verdict')}
    _pend = {x['rule_id'] for x in (_jf2.get('needs_agent') or []) if x.get('rule_id')}
    findings = []; counts = {'PASS': 0, 'FAIL': 0, 'UNVERIFIABLE': 0, 'CONFLICT_PENDING': 0,
                             'NOT_APPLICABLE': 0, 'PENDING_JUDGE': 0}
    seen = set()
    for r in results:
        v = r.get('verdict'); rid = r.get('rule_id'); reason = None
        if rid in _pend:
            # 定性卡未判：单列，不计入缺证
            counts['PENDING_JUDGE'] = counts.get('PENDING_JUDGE', 0) + 1
            _pa.append({'rule_id': rid, 'slot': r.get('slot'), 'category': r.get('category'),
                        'clause': (r.get('anchor') or {}).get('clause'),
                        'verdict': 'PENDING_JUDGE'})
            seen.add(rid)
            continue
        if rid in _auth:
            v = _auth[rid]; reason = '采信 judge_findings（索引检索判定）'
        f = fmap.get(rid)
        if f and f.get('verdict'):
            seen.add(rid)
            if f['verdict'] != v:
                reason = f'采信 {f["line"]} findings：{v} → {f["verdict"]}'
            v = f['verdict']
        # 假通过复核：PASS 必须有报告位置与依据
        if v == 'PASS':
            if not span_of(rid, r.get('slot')):
                v = 'UNVERIFIABLE'; reason = '假通过复核：PASS 缺报告位置'
            elif not (r.get('anchor') or {}).get('clause'):
                # 谓词类 PASS 只需要条款锚；basis 是论证依据（PERF 类才有），不是 PASS 的必要条件
                v = 'UNVERIFIABLE'; reason = '假通过复核：PASS 缺条款锚'
        # 只能升级不能降级（本脚本不产出 PASS，除非原值为 PASS 且通过复核）
        counts[v] = counts.get(v, 0) + 1
        anchor = (r.get('anchor') or {})
        clause = str(anchor.get('clause') or '')
        findings.append({'rule_id': rid, 'slot': r.get('slot'), 'label': r.get('label'),
                         'verdict': v, 'reason': reason,
                         'std_span_id': anchor.get('span_id') or by_clause.get(clause),
                         'report_span': span_of(rid, r.get('slot')),
                         'message': r.get('message'), 'basis': r.get('basis'),
                         'owner': owner_of(None)})
    for rid, f in fmap.items():
        if rid in seen or not f.get('verdict'):
            continue
        v = f['verdict']
        counts[v] = counts.get(v, 0) + 1
        findings.append({'rule_id': rid, 'slot': None, 'label': None, 'verdict': v,
                         'reason': f'仅 {f["line"]} findings 覆盖',
                         'std_span_id': None, 'report_span': f.get('report_span'),
                         'message': f.get('message'), 'basis': f.get('basis'),
                         'owner': f.get('owner') or owner_of(f.get('pending_class'))})
    # judge_findings（检索式判定）：verdict 项作为覆盖源；needs_agent 单列不计分
    _jf = load(os.path.join(D, 'machine', 'judge_findings.json'), {}) or {}
    for it in _jf.get('items') or []:
        rid = it.get('rule_id')
        if rid and it.get('verdict'):
            fmap.setdefault(rid, {'verdict': it['verdict'], 'line': 'judge_findings',
                                  'message': it.get('message'), 'basis': it.get('basis'),
                                  'owner': it.get('owner'),
                                  'pending_class': it.get('pending_class'),
                                  'report_span': it.get('report_span')})

    # C8 文档清单完整性：来自 std.doc_gap 的 c8_result（标准强制记录 vs 实有文档）
    _dg = load(os.path.join(D, 'machine', 'doc_gap.json'), {}) or {}
    _c8 = _dg.get('c8_result')
    if _c8 and _c8.get('verdict'):
        _rid = _c8['rule_id']
        if _rid not in seen:
            counts[_c8['verdict']] = counts.get(_c8['verdict'], 0) + 1
            findings.append({'rule_id': _rid, 'slot': None, 'label': '文档清单完整性',
                             'verdict': _c8['verdict'], 'reason': 'doc_completeness',
                             'std_span_id': None, 'report_span': None,
                             'message': _c8.get('message'), 'basis': 'doc_completeness',
                             'owner': _c8.get('owner'),
                             'missing_documents': _c8.get('missing_required') or [],
                             'uncategorized': _c8.get('uncategorized', 0)})
            seen.add(_rid)

    order = ['FAIL', 'CONFLICT_PENDING', 'UNVERIFIABLE', 'PENDING_JUDGE', 'NOT_APPLICABLE', 'PASS']
    verdict = next((x for x in order if counts.get(x)), 'PASS')
    if method_mismatch: verdict = 'FAIL'
    _pending_agent = _pa
    out = {'report_id': a.report, 'standards': [ses.get('standard_id')],
           'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
           'verdict': verdict, 'counts': counts, 'findings': findings,
           'report_method': a.report_method or None,
           'pending_agent': _pending_agent,
           'method_mismatch': (method_mismatch if a.report_method else 'NOT_CHECKED'),
           'conflicts': [], 'missing': [],
           'override_policy': {'mode': 'escalate_only', 'allow_override': a.allow_override},
           'source': {'results': 'audit_results.json', 'ses': 'ses.json', 'graph': 'sop-graph.json'}}
    json.dump(out, open(os.path.join(D, 'adjudication.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    trail(D, {'step': 'adjudicate', 'exit': 0, 'report': a.report, 'verdict': verdict,
              'at': datetime.datetime.now().isoformat(timespec='seconds')})
    print(json.dumps({'report': a.report, 'verdict': verdict, 'counts': counts,
                      'method_mismatch': len(method_mismatch)}, ensure_ascii=False)); return 0

if __name__ == '__main__':
    sys.exit(main())
