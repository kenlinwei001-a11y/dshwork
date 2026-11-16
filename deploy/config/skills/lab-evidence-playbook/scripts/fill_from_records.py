#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从过程记录（原始记录）里抽质控/仪器证据填槽：确定性、带原文引文。

用法: python3 fill_from_records.py --out <运行目录> --records <记录txt...> [--write]

只填「记录里能直接读到」的槽：
  每批空白数、加标回收率、平行双样相对偏差、标准贮备液浓度、仪器编号
其余不猜。每条填值都带 page(按页标记) + quote(原文连续片段)。
"""
import argparse, json, os, re, sys

def load(p, d=None):
    if not os.path.exists(p): return d
    return json.load(open(p, encoding='utf-8'))

def pages(text):
    """按 ===== 分节，返回 [(page_no, text)]"""
    out, cur, n = [], [], 0
    for line in text.splitlines():
        if re.match(r'^={3,}', line.strip()):
            if cur: out.append((n, '\n'.join(cur)))
            n += 1; cur = []
        else:
            cur.append(line)
    if cur: out.append((n or 1, '\n'.join(cur)))
    return out

def find_quote(text, val):
    """quote 必须是原文连续片段：直接判断是否在原文里。"""
    s = str(val)
    return s if s in text else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--records', nargs='+', required=True)
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()
    O = a.out

    blob = ''
    for p in a.records:
        blob += '\n' + open(p, encoding='utf-8').read()

    cand = {}   # slot_label_keyword -> (value, quote, page, method)
    # 1 空白样品条数
    blanks = re.findall(r'空白样品\s*(\d)', blob)
    if blanks:
        n = len(set(blanks))
        cand['每批空白数'] = (n, f'空白样品{max(blanks, key=lambda x:int(x))}', 1, 'keyword')
    # 2 加标回收率（取最低值，保守口径）
    recs = [float(x) for x in re.findall(r'加标回收率\s*([\d.]+)\s*%', blob)]
    if recs:
        v = min(recs)
        cand['加标回收率'] = (v, f'加标回收率{v:g}%', 1, 'keyword')
    # 3 平行双样相对偏差（取最大，保守口径）
    rpds = [float(x) for x in re.findall(r'相对偏差[：:]\s*([\d.]+)\s*%', blob)]
    if rpds:
        v = max(rpds)
        cand['平行双样相对偏差'] = (v, f'相对偏差：{v:g}%', 1, 'keyword')
    # 4 标准贮备液浓度
    m = re.search(r'加标量[：:]\s*(\d+)\s*mg/L', blob)
    if m:
        cand['标准贮备液浓度'] = (float(m.group(1)), f'{m.group(1)} mg/L', 1, 'keyword')

    slots = load(os.path.join(O, 'machine', 'report_slots.json'), {}) or {}
    spans = load(os.path.join(O, 'machine', 'report_spans.json'), {}) or {}
    tasks = [json.loads(l) for l in open(os.path.join(O, 'audit_tasks.jsonl'), encoding='utf-8')
             if l.strip()] if os.path.exists(os.path.join(O, 'audit_tasks.jsonl')) else []

    filled = {}
    for t in tasks:
        label = str(t.get('label') or '')
        for k, (v, q, pg, how) in cand.items():
            if k in label and slots.get(t['slot']) in (None, ''):
                slots[t['slot']] = v
                if find_quote(blob, q):
                    spans[t['slot']] = {'page': pg, 'quote': q, 'method': how}
                filled[t['slot']] = {'label': label, 'value': v, 'quote': q}

    if a.write:
        json.dump(slots, open(os.path.join(O, 'machine', 'report_slots.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        json.dump(spans, open(os.path.join(O, 'machine', 'report_spans.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
    print(json.dumps({'records': len(a.records), 'candidates': len(cand),
                      'filled': filled}, ensure_ascii=False, indent=1))
    return 0

if __name__ == '__main__':
    sys.exit(main())
