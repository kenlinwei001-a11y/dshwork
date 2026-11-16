#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2：OCR 接线。引擎未部署时显式 BLOCKED，不静默跳过、不让模型猜图上的字。

用法: python3 ocr_step.py --out <运行目录> [--images <目录或文件...>]

输出 machine/ocr_status.json：
  {engine, status: OK|BLOCKED, reason, images:[{path, handled_by}], gaps:[GAP-DATA...]}
规则：引擎不可用 → 每张图登记 GAP-DATA（不可辨，不出数值），下游只能判 UNVERIFIABLE。
"""
import argparse, json, os, sys

def load(p, d=None):
    if not os.path.exists(p): return d
    return json.load(open(p, encoding='utf-8'))

IMG = ('.jpg', '.jpeg', '.png', '.tif', '.tiff')

def cap_status():
    for p in ('skill-update/scripts/registry/capabilities.json',
              'skill-update/scripts/registry/capabilities.json'):
        c = load(p)
        if not c: continue
        ocr = (c.get('capabilities') or {}).get('ocr.to_text') or {}
        return ocr.get('status') or ocr.get('contract', {}).get('status') or 'UNKNOWN'
    return 'UNKNOWN'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--images', nargs='*', default=[])
    a = ap.parse_args()
    O = a.out

    status = cap_status()
    engine_ok = status in ('OK', 'STANDARD')

    imgs = []
    for p in a.images:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                imgs += [os.path.join(root, f) for f in files if f.lower().endswith(IMG)]
        elif os.path.exists(p) and p.lower().endswith(IMG):
            imgs.append(p)

    gaps = []
    for i in imgs:
        gaps.append({'gap_id': 'GAP-DATA-OCR-' + os.path.basename(i)[:20],
                     'type': 'GAP-DATA', 'pending_class': 'PENDING_DOC',
                     'request': f'请提供 {os.path.basename(i)} 的可读文本或部署 OCR 引擎后重跑',
                     'reason': 'OCR 引擎未部署，画面内容不可辨，不出数值'})

    doc = {'engine': 'ocr.to_text', 'capability_status': status,
           'status': 'OK' if engine_ok else 'BLOCKED',
           'reason': None if engine_ok else f'ocr.to_text 状态={status}，引擎未部署',
           'images': [{'path': os.path.basename(i), 'handled_by': 'ocr' if engine_ok else 'none'} for i in imgs],
           'gaps': gaps,
           'note': 'BLOCKED 时下游对这些图只能判 UNVERIFIABLE，不得由模型猜字'}
    os.makedirs(os.path.join(O, 'machine'), exist_ok=True)
    json.dump(doc, open(os.path.join(O, 'machine', 'ocr_status.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(json.dumps({'status': doc['status'], 'capability': status,
                      'images': len(imgs), 'gaps': len(gaps)}, ensure_ascii=False, indent=1))
    return 0

if __name__ == '__main__':
    sys.exit(main())
