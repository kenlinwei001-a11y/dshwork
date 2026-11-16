#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性候选抽取：从条款册抽「可抄字段」，供 LLM 只做判断。
用法: python3 extract_candidates.py --clauses 01-clauses.json --text std.txt --out candidates.json
"""
import argparse, json, os, re, sys

NUM = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(mg/L|μg/L|ug/L|mol/L|mmol/L|g/L|ml|mL|L|μl|ul|g|mg|μg|ug|℃|°C|nm|min|h|d|kHz|MPa|%|mol|mmol|μmol)(?![\w])')
CHEM = re.compile(r'\b([A-Z][a-z]?(?:\d+)?(?:[A-Z][a-z]?\d*)+)\b|([\u4e00-\u9fa5]{2,12}(?:钠|钾|镁|钙|铵|汞|锌|酸|碱|盐|溶液|试剂|树脂|指示剂|试纸))')
INST = re.compile(r'(分光光度计|离子色谱仪|色谱柱|抑制器|电导检测器|天平|烘箱|干燥器|容量瓶|移液管|滴定管|烧杯|锥形瓶|蒸馏装置|纯水器|滤膜|注射器|进样器)')
VERB = re.compile(r'(称取|量取|移取|吸取|溶解|稀释|定容|混匀|摇匀|静置|加热|冷却|过滤|蒸馏|离心|调节|保存|贮存|干燥|洗涤|加入|注入|测定|绘制|计算|记录)')

def locate(text, x):
    """返回 (start,end)：优先用 quote 定位，回退到条款号 token；找不到返回 (0,0)。"""
    q = (x.get('quote') or '')[:40]
    if q:
        i = text.find(q)
        if i >= 0:
            return i, min(len(text), i + 1500)
    import re as _re
    m = _re.search(r'(?m)^\s*' + _re.escape(str(x.get('clause'))) + r'(?![\d.])', text)
    if m: return m.start(), min(len(text), m.start() + 1500)
    return 0, 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--clauses', required=True); ap.add_argument('--text'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    c = json.load(open(a.clauses, encoding='utf-8'))
    cr = c.get('clause_registry') or []
    text = open(a.text, encoding='utf-8').read() if a.text else ''
    # 用条款号在正文中定位块（找不到则退回 quote）
    blocks, marks = {}, []
    for x in cr:
        no = str(x.get('clause'))
        m = re.search(r'(?m)^\s*' + re.escape(no) + r'(?![\d.])', text) if text else None
        if m: marks.append((m.start(), m.end(), no))
    marks.sort()
    for i, (st, en, no) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else min(len(text), st + 1500)
        blocks.setdefault(no, text[st:end])
    out = []
    for x in cr:
        st, en = locate(text, x) if text else (0, 0)
        q = text[st:en] if en > st else (x.get('quote') or '')
        nums = [{'i': i, 'value': m.group(1), 'unit': m.group(2), 'raw': m.group(0)}
                for i, m in enumerate(NUM.finditer(q))]
        chems = sorted({m.group(0) for m in CHEM.finditer(q)})
        insts = sorted({m.group(1) for m in INST.finditer(q)})
        verbs = sorted({m.group(1) for m in VERB.finditer(q)})
        out.append({'clause': x.get('clause'), 'page': x.get('page'), 'modality': x.get('modality'),
                    'type': x.get('type'), 'heading': x.get('heading'), 'quote': q,
                    'numbers': nums, 'chemicals': chems, 'instruments': insts, 'actions': verbs})
    doc = {'standard_id': c.get('standard_id'), 'standard_slug': c.get('standard_slug'),
           'clauses': out,
           'coverage': {'clauses': len(out),
                        'with_numbers': sum(1 for x in out if x['numbers']),
                        'with_chemicals': sum(1 for x in out if x['chemicals']),
                        'with_instruments': sum(1 for x in out if x['instruments']),
                        'with_actions': sum(1 for x in out if x['actions']),
                        'numbers_total': sum(len(x['numbers']) for x in out)}}
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    json.dump(doc, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(json.dumps(doc['coverage'], ensure_ascii=False))
    return 0

if __name__ == '__main__':
    sys.exit(main())
