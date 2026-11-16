#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""候选槽扫描器：按 slots_candidate 的 doc_type / clause / match_hints 去文档里找值。

用法:
  python3 scan_candidates.py --out <运行目录> --text <报告txt> [--text <记录txt>...] \
                             [--doc-type 原始记录] [--min-hits 1]

做什么（全确定性，不叫模型）：
  1. 载入 contracts/derived/slots_candidate.jsonl
  2. 每条候选：用 match_hints 在正文里找命中行，取该行原文作 quote（连续片段）
  3. 从命中行里取数值候选（保留单位与 ND 原样）
  4. 输出 machine/slot_hits.jsonl：{clause, doc_item, doc_type, status, quote, page, value}
     status ∈ HIT / NO_HINT / MISS

为什么是脚本：候选槽已有文档类型与关键词，扫描是字符串匹配，不该由模型读全文。
模型只在 status=MISS 或一条候选命中多行时介入。
"""
import argparse
import json
import os
import re
import sys

NUM = re.compile(r'(ND|n\.a\.|[<>]?\s?\d+(?:\.\d+)?)\s*(mg/L|%|℃|nm|kHz|mL|g|h|min)?')


def load(p, d=None):
    if not os.path.exists(p):
        return d
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def pages(text):
    """按 '===== PAGE n =====' 或 '--- page-XX.tsv' 切页，返回 [(page, line)] 列表。"""
    out, page = [], 1
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        m = re.search(r'PAGE\s+(\d+)', s) or re.search(r'page-(\d+)', s)
        if m:
            page = int(m.group(1))
            continue
        # OCR 行前缀 [x= y=] 去掉，保留正文
        m2 = re.match(r'\[x=\s*\d+\s*y=\s*\d+\]\s*(.*)$', s)
        body = m2.group(1).strip() if m2 else s
        if body:
            out.append((page, body))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--text', action='append', required=True)
    ap.add_argument('--candidates', default='contracts/derived/slots_candidate.jsonl')
    ap.add_argument('--doc-type', action='append', default=[])
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--emit-pending', action='store_true',
                    help='另存 AMBIGUOUS/MISS 到 machine/slot_hits_pending.jsonl（供切片给模型）')
    ap.add_argument('--min-hints', type=int, default=2,
                    help='命中强度阈值：命中 hint 数达到才算 HIT，否则 AMBIGUOUS')
    ap.add_argument('--clause-bonus', action='store_true', default=True,
                    help='行内含条款号时加 1 分（条款邻近）')
    a = ap.parse_args()
    O = a.out

    cands = []
    with open(a.candidates, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                cands.append(json.loads(line))
    if a.doc_type:
        cands = [c for c in cands if c.get('doc_type') in a.doc_type]

    lines = []
    for p in a.text:
        if os.path.exists(p):
            lines += pages(open(p, encoding='utf-8').read())
    blob = '\n'.join(b for _, b in lines)

    hits, stat = [], {'HIT': 0, 'AMBIGUOUS': 0, 'NO_HINT': 0, 'MISS': 0}
    for c in cands:
        hints = [h for h in (c.get('match_hints') or []) if h]
        if not hints:
            stat['NO_HINT'] += 1
            hits.append({**pick(c), 'status': 'NO_HINT', 'reason': '候选无 match_hints'})
            continue
        strong = strong_hints(c)
        scored = []
        for pg, body in lines:
            sc = sum(1 for h in hints if h in body)
            sc += 3 * sum(1 for h in strong if h in body)   # 行标签命中权重 3
            if a.clause_bonus and c.get('clause') and str(c['clause']) in body:
                sc += 1
            if sc:
                scored.append((sc, pg, body))
        if not scored:
            stat['MISS'] += 1
            hits.append({**pick(c), 'status': 'MISS', 'tried': hints})
            continue
        scored.sort(key=lambda x: (-x[0], len(x[2])))
        sc, pg, body = scored[0]
        m = NUM.search(body)
        status = 'HIT' if sc >= a.min_hints else 'AMBIGUOUS'
        stat[status] += 1
        hits.append({**pick(c), 'status': status, 'score': sc, 'page': pg, 'quote': body,
                     'matched_hints': [h for h in hints if h in body],
                     'value': (m.group(1).strip() if m else None),
                     'unit': (m.group(2) if m else None),
                     'quote_ok': body in blob,
                     'alternatives': len(scored) - 1})

    total = len(cands)
    rate = round(stat['HIT'] / total, 3) if total else None
    if a.write:
        os.makedirs(os.path.join(O, 'machine'), exist_ok=True)
        with open(os.path.join(O, 'machine', 'slot_hits.jsonl'), 'w', encoding='utf-8') as f:
            for h in hits:
                f.write(json.dumps(h, ensure_ascii=False) + '\n')
    if a.emit_pending:
        pend=[h for h in hits if h.get('status') in ('AMBIGUOUS','MISS')]
        os.makedirs(os.path.join(O,'machine'),exist_ok=True)
        with open(os.path.join(O,'machine','slot_hits_pending.jsonl'),'w',encoding='utf-8') as fh:
            for h in pend: fh.write(json.dumps(h,ensure_ascii=False)+'\n')
    print(json.dumps({'candidates': total, 'hit': stat['HIT'], 'ambiguous': stat['AMBIGUOUS'],
                      'miss': stat['MISS'], 'no_hint': stat['NO_HINT'], 'hit_rate': rate,
                      'quote_ok': sum(1 for h in hits if h.get('quote_ok')),
                      'multi_line': sum(1 for h in hits if h.get('alternatives'))},
                     ensure_ascii=False))
    return 0


def strong_hints(c):
    """条目名里的引号内容是行标签（如 “空白样品1/2”行），是最强定位信号。"""
    import re as _re
    item = str(c.get('doc_item') or '')
    raw = _re.findall(r'[“\"]([^”\"]{2,30})[”\"]', item)
    out = []
    for seg in raw:
        for part in _re.split(r'[、，,；;/]', seg):
            part = _re.sub(r'(行|首页|页|栏|表|部分)$', '', part.strip())
            if len(part) >= 2:
                out.append(part)
    return out


def pick(c):
    return {k: c.get(k) for k in ('standard', 'clause', 'doc_item', 'doc_type')}


if __name__ == '__main__':
    sys.exit(main())
