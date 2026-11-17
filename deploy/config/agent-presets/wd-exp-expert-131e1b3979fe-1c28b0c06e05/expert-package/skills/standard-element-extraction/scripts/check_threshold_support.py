#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阈值原文回检：规则里的数值必须能在自己标准的原文找到，否则视为污染/编造。

用法: python3 check_threshold_support.py --packs <包目录...> --std-dir <标准md目录> [--strict]
分级: A 条款内可证 / B 本标其他处 / C 仅见他标准（污染）/ D 各标准皆无（编造）
--strict 时 C 或 D 出现即 exit 1。
"""
import argparse,glob,json,os,re,sys

def norm(t):
    t=re.sub(r'\\mathrm|\\text|\\geqslant|\\leqslant|\$|\{|\}','',t)
    t=re.sub(r'(?<=\d)\s+(?=\d)','',t)          # 1 0 5 → 105
    t=re.sub(r'(?<=\d)\s*\.\s*(?=\d)','.',t)     # 1 . 8 4 → 1.84
    return re.sub(r'\s+',' ',t)

def near(txt,v):
    s=f"{v:g}"
    return re.search(r'(?<![\d.])'+re.escape(s)+r'\.?0*(?![\d])',txt) is not None

def win(t,cl):
    if not cl: return ''
    m=re.search(re.escape(str(cl).strip())+r'(?![\d.])',t)
    return t[max(0,m.start()-30):m.start()+400] if m else ''

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--packs',nargs='+',required=True)
    ap.add_argument('--std-dir',required=True); ap.add_argument('--strict',action='store_true')
    ap.add_argument('--json-out')
    a=ap.parse_args()
    TXT={}
    for f in glob.glob(os.path.join(a.std_dir,'*.md')):
        TXT[os.path.basename(f)[:-3]]=norm(open(f,encoding='utf-8',errors='ignore').read())
    rows=[]
    for pk in a.packs:
        std=os.path.basename(pk.rstrip('/'))
        txt=TXT.get(std) or next((v for k,v in TXT.items() if k.startswith(std.split('-')[0])),None)
        if txt is None: print(f"  ! {std} 无对应标准文本，跳过"); continue
        for l in open(os.path.join(pk,'rules.jsonl'),encoding='utf-8'):
            if not l.strip(): continue
            r=json.loads(l); p=r.get('predicate') or {}
            vs=[]
            for x in (p.get('value') if isinstance(p.get('value'),list) else [p.get('value')]):
                try: vs.append(float(str(x).replace('%','')))
                except (TypeError,ValueError): pass
            if not vs: continue
            w=win(txt,r.get('clause')); notes=norm(r.get('anchor_notes') or '')
            in_clause=all(near(w,v) for v in vs) or all(near(notes,v) for v in vs)
            in_std=all(near(txt,v) for v in vs)
            other=[k for k,v2 in TXT.items() if k!=std and all(near(v2,v) for v in vs)]
            lvl='A' if in_clause else 'B' if in_std else 'C' if other else 'D'
            rows.append({'standard':std,'rule_id':r['rule_id'],'clause':r.get('clause'),
                         'value':p.get('value'),'unit':p.get('unit'),'level':lvl,'seen_in':other})
    from collections import Counter
    c=Counter(x['level'] for x in rows)
    print(f"阈值型规则 {len(rows)} | A {c.get('A',0)} | B {c.get('B',0)} | C {c.get('C',0)} | D {c.get('D',0)}")
    bad=[x for x in rows if x['level'] in ('C','D')]
    for x in bad:
        tag='污染（仅见他标准）' if x['level']=='C' else '编造（各标准皆无）'
        print(f"  ✗ {x['standard']:11s} {x['rule_id']:22s} §{x['clause']} 值={x['value']} {x['unit'] or ''} {tag}"
              +(f" ← 见 {','.join(x['seen_in'])}" if x['seen_in'] else ''))
    if a.json_out: json.dump(rows,open(a.json_out,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    if a.strict and bad: return 1
    return 0

if __name__=='__main__': sys.exit(main())
