#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""质控证据覆盖率：算「本批有多少样品真的有平行/加标/空白证据」。

用法: python3 qc_coverage.py --out <运行目录> --records <记录txt...>

为什么要有它：单条规则只能证明"做了的那一个合格"，证明不了"整批被覆盖"。
2/15 个样品做了平行、规则却 PASS —— 这就是「单条都对、整体不可信」。

输出 machine/qc_coverage.json：
  {"total_samples": 15,
   "parallel": {"count": 2, "samples": [...], "ratio": 0.133},
   "spike":    {"count": 1, ...},
   "blank":    {"declared": 2},
   "untested": {"parallel": [...], "spike": [...]}}
"""
import argparse
import json
import os
import re
import sys

SID = re.compile(r'(\d{4}-\d{2}-\d{2}-\d+)')


def load(p, d=None):
    if not os.path.exists(p):
        return d
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--records', nargs='+', required=True)
    a = ap.parse_args()
    O = a.out

    blob = ''
    for p in a.records:
        blob += '\n' + open(p, encoding='utf-8').read()

    # 本批样品总数：优先用表格抽取结果
    tables = (load(os.path.join(O, 'machine', 'tables.json'), {}) or {}).get('tables') or []
    all_samples = [r['sample_id'] for r in (tables[0]['rows'] if tables else []) if r.get('sample_id')]
    if not all_samples:
        all_samples = sorted(set(SID.findall(blob)))
    total = len(all_samples)

    def who(tag):
        """tag 附近出现的样品号（同行±1 行）"""
        found = set()
        lines = blob.splitlines()
        for i, ln in enumerate(lines):
            if tag in ln:
                for j in (i - 1, i, i + 1):
                    if 0 <= j < len(lines):
                        found.update(SID.findall(lines[j]))
        return sorted(found)

    par = who('平行')
    spk = who('加标')
    blanks = len(set(re.findall(r'空白样品\s*(\d)', blob)))

    def ratio(n):
        return round(n / total, 3) if total else None

    doc = {
        'total_samples': total,
        'samples': all_samples,
        'parallel': {'count': len(par), 'samples': par, 'ratio': ratio(len(par))},
        'spike': {'count': len(spk), 'samples': spk, 'ratio': ratio(len(spk))},
        'blank': {'declared': blanks},
        'untested': {
            'parallel': [s for s in all_samples if s not in par],
            'spike': [s for s in all_samples if s not in spk],
        },
        'note': '覆盖率只说明"证据覆盖面"，不评价单个证据是否合格；两者分开判',
    }
    os.makedirs(os.path.join(O, 'machine'), exist_ok=True)
    json.dump(doc, open(os.path.join(O, 'machine', 'qc_coverage.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(json.dumps({'total': total, 'parallel': doc['parallel']['count'],
                      'spike': doc['spike']['count'], 'blank': blanks,
                      'parallel_ratio': doc['parallel']['ratio'],
                      'spike_ratio': doc['spike']['ratio']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
