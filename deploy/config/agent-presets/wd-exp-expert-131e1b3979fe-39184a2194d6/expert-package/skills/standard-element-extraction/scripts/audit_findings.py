#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计确定性发现（零 LLM）：一次算出所有可计算项，输出精简 findings.json（默认 ≤ 6 KB）。
用法: python3 audit_findings.py --out <out目录> --text <正文>
"""
import argparse, json, os, re, sys, collections, random

def norm(s): return re.sub(r'\s+', '', s or '')
def load(p):
    with open(p, encoding='utf-8') as f: return json.load(f)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--text', required=True)
    a = ap.parse_args(); O = a.out
    t = norm(open(a.text, encoding='utf-8').read())
    fp = os.path.join(O, 'facts.json')
    if os.path.exists(fp):
        F = load(fp)
        c = {'clause_registry': F.get('clauses') or []}
        e = {'elements': (F.get('records') or {}).get('elements') or []}
        r = {'audit_rule_cards': (F.get('records') or {}).get('rules') or [], 'gaps': F.get('gaps') or []}
        print(json.dumps({'source': 'facts.json'}, ensure_ascii=False))
    else:
        c = load(os.path.join(O, '01-clauses.json')); e = load(os.path.join(O, '02-elements.json')); r = load(os.path.join(O, '03-rules.json'))
        print(json.dumps({'source': 'views'}, ensure_ascii=False))
    cr, els, cards = c.get('clause_registry') or [], e.get('elements') or [], r.get('audit_rule_cards') or []
    def miss(items, q):
        return [x for x in items if norm(q(x)) not in t]
    a1 = miss(cr, lambda x: x.get('quote')); a2 = miss(els, lambda x: (x.get('anchor') or {}).get('quote'))
    a3 = miss(cards, lambda x: (x.get('anchor') or {}).get('quote'))
    nc = [x['clause'] for x in cr if x.get('type') == 'normative']
    elc = {(x.get('anchor') or {}).get('clause') for x in els}; ruc = {x.get('clause') for x in cards}
    ids = [x.get('element_id') for x in els] + [x.get('rule_id') for x in cards]
    dup = [k for k, v in collections.Counter(ids).items() if v > 1]
    bad_p = []
    for x in cards:
        p = x.get('predicate') or {}; v = p.get('value')
        if isinstance(v, bool) or v is None or isinstance(v, (list, dict)): continue
        if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r'-?\d+(?:\.\d+)?', v)):
            if str(v) not in t: bad_p.append(x.get('rule_id'))
    unv = [p for x in els for p in (x.get('parameters') or []) if p.get('unverified')]
    gaps = r.get('gaps') or []
    # 随机抽样（固定种子，可复现）
    random.seed(42); pool = [m.group(0) for m in re.finditer(r'\d+(?:\.\d+)?', t)]
    sample = random.sample(pool, min(12, len(pool)))
    F = {
        'standard': c.get('standard_id'), 'clauses': len(cr), 'normative': len(nc),
        'anchors': {'clause': [len(cr)-len(a1), len(cr)], 'element': [len(els)-len(a2), len(els)], 'rule': [len(cards)-len(a3), len(cards)],
                    'miss': {'clause': [x.get('clause') for x in a1][:8], 'element': [x.get('element_id') for x in a2][:8], 'rule': [x.get('rule_id') for x in a3][:8]}},
        'coverage': {'missing_element': [x for x in nc if x not in elc][:12], 'missing_rule': [x for x in nc if x not in ruc][:12]},
        'ids': {'duplicates': dup[:8]}, 'predicate_not_in_text': bad_p[:8],
        'qualitative_with_predicate': [x.get('rule_id') for x in cards if x.get('qualitative_check') and x.get('predicate')][:8],
        'unverified_params': len(unv), 'gaps': len(gaps), 'gaps_without_rules': [g.get('gap_id') for g in gaps if not g.get('affected_rules')][:8],
        'categories': dict(sorted(collections.Counter(x.get('category') for x in cards).items())),
        'sample_numbers': sample,
    }
    p = os.path.join(O, 'audit_findings.json')
    json.dump(F, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps({k: F[k] for k in ('clauses','normative','unverified_params','gaps')}, ensure_ascii=False),
          'size', os.path.getsize(p), 'bytes')
    ok = not (a1 or a2 or a3 or dup or bad_p)
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
