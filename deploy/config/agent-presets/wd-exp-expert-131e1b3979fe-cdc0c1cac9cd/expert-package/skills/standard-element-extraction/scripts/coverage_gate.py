#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R1 章节覆盖闸：标准每一章必须「有规则」或「显式登记为无可判定要求」。

用法: python3 coverage_gate.py --packs <包目录...> --std-dir <标准md目录> --waivers contracts/coverage_waivers.json [--strict]
豁免文件格式: {"HJ84-2016": {"3": "方法原理，无判定要求", ...}}
未豁免且无规则的章 → 报错；--strict 时 exit 1。
"""
import argparse,glob,json,os,re,sys

HEAD=re.compile(r'(?m)^#{1,3}\s*(\d{1,2})\s+\S')

def chapters(text):
    hs={int(m.group(1)) for m in HEAD.finditer(text)}
    if not hs:
        for m in re.finditer(r'(?:^|\n)\s*(\d{1,2})\s+(适用范围|规范性引用文件|方法原理|原理|干扰|试剂和材料|仪器和设备|样品|分析步骤|结果计算|精密度|质量保证|废物处理|注意事项)',text):
            hs.add(int(m.group(1)))
    return sorted(hs)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--packs',nargs='+',required=True)
    ap.add_argument('--std-dir',required=True); ap.add_argument('--waivers',default=None)
    ap.add_argument('--strict',action='store_true'); a=ap.parse_args()
    wv=json.load(open(a.waivers,encoding='utf-8')) if a.waivers and os.path.exists(a.waivers) else {}
    bad=0
    for pk in a.packs:
        std=os.path.basename(pk.rstrip('/'))
        f=next((p for p in glob.glob(os.path.join(a.std_dir,'*.md')) if os.path.basename(p).startswith(std.split('-')[0])),None)
        if not f: print(f"  ! {std} 无标准文本，跳过"); continue
        chs=chapters(open(f,encoding='utf-8').read())
        have=set()
        for l in open(os.path.join(pk,'rules.jsonl'),encoding='utf-8'):
            if not l.strip(): continue
            m=re.match(r'(\d{1,2})',str(json.loads(l).get('clause') or ''))
            if m: have.add(int(m.group(1)))
        miss=[c for c in chs if c>2 and c not in have]
        wa=wv.get(std,{})
        unwaived=[c for c in miss if str(c) not in wa]
        state='OK' if not unwaived else 'FAIL'
        print(f"  {state} {std:12s} 章 {len(chs)} | 有规则 {len([c for c in chs if c in have])} | "
              f"无规则 {miss if miss else '无'} | 已豁免 {[c for c in miss if str(c) in wa] or '无'}")
        for c in unwaived: print(f"      ✗ 第 {c} 章无规则且未登记豁免")
        bad+=len(unwaived)
    print(f"\n未覆盖且未豁免章节合计: {bad}")
    return 1 if (a.strict and bad) else 0

if __name__=='__main__': sys.exit(main())
