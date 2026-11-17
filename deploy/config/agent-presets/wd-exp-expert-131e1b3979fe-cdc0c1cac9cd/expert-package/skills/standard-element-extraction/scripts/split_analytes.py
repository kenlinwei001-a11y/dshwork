#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按被测项目把报告拆成多个判定分桶，并把每个桶匹配到方法族规则集。

用法: python3 split_analytes.py --out <run> --packs-dir docs/判定包
输入: machine/tables.json（报告表格，需含"检测项目→检测方法"表 与 结果表）
输出: machine/analyte_buckets.json
规则: 只按报告声明的方法配规则；声明的方法无规则集 → PENDING_UPLOAD，不得套用其他方法（红线）
"""
import argparse,json,os,re,sys,glob
ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); ap.add_argument('--packs-dir',default='docs/判定包')
a=ap.parse_args(); O=a.out
t=json.load(open(os.path.join(O,'machine','tables.json'),encoding='utf-8'))['tables']
# 1) 找"检测项目/检测方法"表
method_tbl=None
for tb in t:
    head=[c['value'] for c in (tb['rows'][0]['cells'] if tb['rows'] else [])]
    if any('检测项目' in h for h in head) and any('方法' in h for h in head):
        method_tbl=tb; break
if not method_tbl:
    print(json.dumps({'error':'未找到「检测项目/检测方法」表'},ensure_ascii=False)); sys.exit(2)
hdr=[c['value'] for c in method_tbl['rows'][0]['cells']]
i_proj=hdr.index(next(h for h in hdr if '检测项目' in h))
i_meth=hdr.index(next(h for h in hdr if '方法' in h))
i_inst=hdr.index(next((h for h in hdr if '仪器' in h),hdr[-1])) if any('仪器' in h for h in hdr) else None
# 2) 结果表的列（被测物）
res_tbl=None
for tb in t:
    for row in tb['rows'][:4]:
        vals=[c['value'] for c in row['cells']]
        if '样品编号' in vals: res_tbl=tb; break
    if res_tbl: break
cols=[]
if res_tbl:
    for row in res_tbl['rows'][:3]:
        vals=[c['value'] for c in row['cells']]
        if '样品编号' in vals:
            cols=[v for v in vals if v and v not in ('样品编号','客户编号','样品状态')]
            break
# 3) 规则集索引
packs={}
for d in glob.glob(os.path.join(a.packs_dir,'*')):
    rp=os.path.join(d,'rules.jsonl')
    if not os.path.exists(rp): continue
    std=os.path.basename(d)
    rules=[json.loads(l) for l in open(rp,encoding='utf-8') if l.strip()]
    packs[re.sub(r'[^A-Z0-9]','',std)]={'standard_id':std,'rules':rules,'n':len(rules)}
def pack_for(s):
    k=re.sub(r'[^A-Z0-9]','',s)
    return packs.get(k)
buckets=[]
for row in method_tbl['rows'][1:]:
    vals=[c['value'] for c in row['cells']]
    proj=vals[i_proj] if i_proj<len(vals) else ''
    meth=vals[i_meth] if i_meth<len(vals) else ''
    inst=vals[i_inst] if (i_inst is not None and i_inst<len(vals)) else ''
    m=re.search(r'((?:HJ|GB|HJ/T|GB/T)\s*\d[\d./-]*\s*[-—]\s*\d{2,4})', meth)
    std_no=(m.group(1).replace(' ','').replace('—','-') if m else '')
    pk=pack_for(std_no) if std_no else None
    analytes=[x.strip() for x in re.split(r'[、,，/]',proj) if x.strip()]
    buckets.append({'analytes':analytes,'declared_method':meth,'standard_no':std_no,
                    'instrument':inst,
                    'rule_set':pk['standard_id'] if pk else None,
                    'rules':pk['n'] if pk else 0,
                    'status':'PROVIDED' if pk else 'PENDING_UPLOAD',
                    'note':'' if pk else f'{std_no} 未收录，不得套用其他方法标准'})
doc={'report_methods_source':'tbl-04 检测项目/检测方法','result_columns':cols,
     'buckets':buckets,
     'unmatched_columns':[c for c in cols if not any(c in b['analytes'] for b in buckets)]}
json.dump(doc,open(os.path.join(O,'machine','analyte_buckets.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps({'buckets':len(buckets),'result_columns':cols,
                  'provided':[b['standard_no'] for b in buckets if b['status']=='PROVIDED'],
                  'pending':[b['standard_no'] for b in buckets if b['status']!='PROVIDED'],
                  'unmatched_columns':doc['unmatched_columns']},ensure_ascii=False))
