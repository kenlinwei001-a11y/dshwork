#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0+P1：从 OCR/文本层结果里抽表格并落定位，不叫模型。

用法:
  python3 extract_tables.py --out <运行目录> --report-text <报告txt> [--write-slots]

做三件事（全确定性）：
  P0 表格抽取：把 `[x=.. y=..] 文本` 形式的 OCR 行还成「行 × 列」表格，写 machine/tables.json
  P1 定位：每个单元格带 page/quote/method，quote 直接可在原文本检索命中（不靠模糊匹配）
  填槽：--write-slots 时，把「单值型」槽（基质/方法/仪器/报告号）填进 report_slots，
        并把表格产物写进 machine/report_tables_ref.json 供审核侧逐样品取用

不猜：识别不出的单元格留空并记 reason；同一行多列错位不做纠正。
"""
import argparse
import json
import os
import re
import sys

LINE = re.compile(r'\[x=\s*(\d+)\s*y=\s*(\d+)\]\s*(.*)$')
PAGE = re.compile(r'^={3,}\s*(.+?)\s*={3,}$')
ROW_TOL = 40      # 同一行的 y 容差
COL_TOL = 120     # 列归属的 x 容差


def parse_html_tables(text):
    """从 markdown 里的 <table> 解析成 rows/cells（保留原文，供 quote 校验）。"""
    import re as _re
    out=[]
    for ti,tb in enumerate(_re.findall(r'<table>(.*?)</table>', text, _re.S),1):
        rows=[]
        for tr in _re.findall(r'<tr>(.*?)</tr>', tb, _re.S):
            cells=[]
            for td in _re.findall(r'<td[^>]*>(.*?)</td>', tr, _re.S):
                v=_re.sub(r'<[^>]+>','',td)
                v=v.replace('&nbsp;',' ').strip()
                cells.append({'value':v,'quote':v})
            if cells: rows.append({'cells':cells})
        if rows: out.append({'table_id':f'tbl-{ti:02d}','rows':rows})
    return out

def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def dump(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def parse_tokens(text):
    """→ [{page, x, y, text}]，page 按 ===== 分节计数。"""
    toks, page, name = [], 0, None
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        m = PAGE.match(s)
        if m:
            page += 1
            name = m.group(1)
            continue
        m = LINE.match(s)
        if not m:
            continue
        toks.append({'page': page or 1, 'doc': name, 'x': int(m.group(1)),
                     'y': int(m.group(2)), 'text': m.group(3).strip()})
    return toks


def group_rows(toks):
    rows = []
    for t in sorted(toks, key=lambda z: (z['page'], z['y'], z['x'])):
        if rows and rows[-1]['page'] == t['page'] and abs(rows[-1]['y'] - t['y']) <= ROW_TOL:
            rows[-1]['cells'].append(t)
        else:
            rows.append({'page': t['page'], 'y': t['y'], 'cells': [t]})
    for r in rows:
        r['cells'].sort(key=lambda z: z['x'])
    return rows


def find_header(rows, keywords):
    """找含≥2个关键词的行作为表头。"""
    best = None
    for r in rows:
        hit = sum(1 for c in r['cells'] if any(k in c['text'] for k in keywords))
        if hit >= 2 and (best is None or hit > best[0]):
            best = (hit, r)
    return best[1] if best else None


def build_table(rows, header):
    cols = [{'header': c['text'], 'x': c['x']} for c in header['cells']]
    out = []
    for r in rows:
        if r['page'] != header['page'] or r['y'] <= header['y']:
            continue
        # 样品编号：第一列里形如 2022-03-15-1 / 202203001 的文本
        sid = None
        for c in r['cells']:
            if re.search(r'\d{4}-\d{2}-\d{2}-\d+', c['text']) or re.fullmatch(r'\d{6,}-\d+', c['text']):
                sid = c['text']
                break
        if not sid:
            continue
        cells = {}
        for c in r['cells']:
            if c['text'] == sid:
                continue
            # 就近归列
            col = min(cols, key=lambda z: abs(z['x'] - c['x']))
            if abs(col['x'] - c['x']) > COL_TOL:
                continue
            cells.setdefault(col['header'], []).append(
                {'value': c['text'], 'quote': c['text'],
                 'page': r['page'], 'x': c['x'], 'method': 'table_cell'})
        out.append({'sample_id': sid, 'page': r['page'], 'cells': cells})
    return {'page': header['page'], 'y': header['y'],
            'columns': [c['header'] for c in cols], 'rows': out,
            'row_count': len(out)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--report-text', required=True)
    ap.add_argument('--write-slots', action='store_true')
    a = ap.parse_args()
    O = a.out
    text = open(a.report_text, encoding='utf-8').read()

    toks = parse_tokens(text)
    rows = group_rows(toks)
    KW = ['样品编号', '客户编号', '总磷', '总氮', '氨氮', 'NO', 'PO', 'mg/L', '检出限']
    header = find_header(rows, KW)
    tables = []
    if header:
        t = build_table(rows, header)
        if t['row_count']:
            tables.append(t)

    # report_meta：前端与裁定都靠它，不能让下游拿 R-UNKNOWN
    def _g(pat, default=None):
        m = re.search(pat, text)
        return m.group(1).strip() if m else default
    meta = {
        'report_id': _g(r'报告编号[：:]\s*(\S+)'),
        'declared_method': _g(r'(HJ\s*\d{2,3}-\d{4})'),
        'report_date': _g(r'报告日期[^\n]*\n\s*\[x=\s*\d+\s*y=\s*\d+\]\s*(\S+)'),
        'sample_count': None,
        'source': os.path.basename(a.report_text),
    }
    if tables:
        meta['sample_count'] = tables[0]['row_count']
    dump(os.path.join(O, 'machine', 'report_meta.json'), {k: v for k, v in meta.items() if v is not None})

    doc = {
        'source': os.path.basename(a.report_text),
        'tokens': len(toks),
        'rows_scanned': len(rows),
        'tables': tables,
        'unparsed_rows': max(0, len(rows) - sum(t['row_count'] + 2 for t in tables)),
    }
    dump(os.path.join(O, 'machine', 'tables.json'), doc)

    filled = {}
    if a.write_slots:
        slots = load(os.path.join(O, 'machine', 'report_slots.json'), {}) or {}
        spans = load(os.path.join(O, 'machine', 'report_spans.json'), {}) or {}
        tasks = [json.loads(l) for l in open(os.path.join(O, 'audit_tasks.jsonl'), encoding='utf-8')
                 if l.strip()] if os.path.exists(os.path.join(O, 'audit_tasks.jsonl')) else []

        htm = parse_html_tables(text)
        if htm:
            json.dump({'source':'report_text','tables':htm},
                      open(os.path.join(O,'machine','tables.json'),'w',encoding='utf-8'),
                      ensure_ascii=False,indent=1)
        # 单值型：基质、方法依据、仪器、报告编号
        def find_value(pats, src=text):
            for p in pats:
                m = re.search(p, src)
                if m:
                    return (m.group(1) if m.groups() else m.group(0)).strip()
            return None

        single = {
            '样品基质类型': (find_value([r'样品名称[^\n]*\n\s*\[x=\s*\d+\s*y=\s*\d+\]\s*(\S+)',
                                     r'样品名称\s+(\S+)']), '样品名称'),
            '方法依据': (find_value([r'HJ\s*\d{2,3}-\d{4}']), None),
        }
        for t in tasks:
            label = str(t.get('label') or '')
            for key, (val, how) in single.items():
                if key in label and val and slots.get(t['slot']) in (None, ''):
                    slots[t['slot']] = val
                    spans[t['slot']] = {'page': 1, 'quote': val, 'method': how or 'regex',
                                        'note': 'quote 必须是原文连续片段，故只取值本身'}
                    filled[t['slot']] = val
        if tables:
            dump(os.path.join(O, 'machine', 'report_tables_ref.json'),
                 {'tables': len(tables), 'rows': tables[0]['row_count'],
                  'columns': tables[0]['columns'],
                  'note': '逐样品数值在此文件内，按 sample_id 取；不摊平成单值槽'})
        dump(os.path.join(O, 'machine', 'report_slots.json'), slots)
        dump(os.path.join(O, 'machine', 'report_spans.json'), spans)

    print(json.dumps({'tokens': len(toks), 'rows': len(rows),
                      'tables': len(tables),
                      'table_rows': tables[0]['row_count'] if tables else 0,
                      'columns': tables[0]['columns'] if tables else [],
                      'slots_filled': filled,
                      'written': 'machine/tables.json'}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
