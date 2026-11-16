#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应有记录 ↔ 实有文档 差集：把「标准要求产生哪些记录」与「包里实际有哪些文件」对账。

用法:
  python3 doc_gap.py --out <run> [--graph sop-graph.json] --docs <目录> [--analyte 硝酸根,磷酸根]

输入:
  sop-graph.json 的 records 边（step → REC-*）与节点（step 名/clauses）
  --docs 目录下的文件名（或 --doc-list 文件，每行一个）
输出:
  machine/doc_gap.json {expected[], present[], missing_type[], matched[], note}
判法（确定性，不猜）:
  文档类型按文件名关键词归类；某类型「应有但一个都没有」→ missing_type
  某类型「有但未覆盖本标准的被测物」→ partial（需人核）
"""
import argparse,json,os,re,sys

TYPE_KW=[('样品流转单',['出入库','流转']),('前处理记录',['风险评估','环境记录']),
         ('仪器使用记录',['仪器运行','维护']),('原始记录',['原始记录']),
         ('检测报告',['检测报告']),('attachment',['校准证书','委托书','合同评审','任务单'])]

# 步骤名 → 应产生的文档类型（标准侧映射，不依赖文件命名）
STEP_KW=[('样品流转单',['接收','保存','采集','流转','样品']),
         ('前处理记录',['前处理','制备','过滤','干扰','消解']),
         ('原始记录',['校准','曲线','测定','空白','标准系列','配制','淋洗','试剂']),
         ('检测报告',['结果计算','修约','表示','报告']),
         ('仪器使用记录',['仪器','色谱柱','检测器','条件']),
         ('attachment',['证书','校准证书'])]

def step_doc_type(step):
    for t,kws in STEP_KW:
        if any(k in step for k in kws): return t
    return '未分类'

def doc_type(name):
    for t,kws in TYPE_KW:
        if any(k in name for k in kws): return t
    return '未分类'

IONS=['氟','氯','溴','亚硝酸根','硝酸根','磷酸根','亚硫酸根','硫酸根']
COND_KW=['按需','必要时','如需','可选','视情况']

def is_conditional(st, clauses):
    txt=(st.get('step') or '')+' '+(st.get('done_when') or '')
    if any(k in txt for k in COND_KW): return True
    # 干扰消除类条款（4.x）通常按需触发
    return bool([c for c in clauses if str(c).startswith('4.')])

def analytes_of(st):
    txt=(st.get('step') or '')+' '+' '.join(st.get('params') or [])+' '+(st.get('done_when') or '')
    return [i for i in IONS if i in txt]

ap=argparse.ArgumentParser()
ap.add_argument('--out',required=True); ap.add_argument('--graph',default='sop-graph.json')
ap.add_argument('--docs',default=None); ap.add_argument('--doc-list',default=None)
ap.add_argument('--analyte',default='')
a=ap.parse_args(); O=a.out

g=json.load(open(os.path.join(O,a.graph),encoding='utf-8'))
nodes={n['node_id']:n for n in g['nodes']}
expected=[]
for e in g.get('edges') or []:
    if e.get('type')!='records': continue
    st=nodes.get(e['from']) or {}
    _cl=st.get('clauses') or []
    _stype=st.get('type')
    _dt=step_doc_type(str(st.get('step') or '')) if _stype=='step' else {
        'instrument':'仪器使用记录','reagent':'原始记录','qc_gate':'原始记录',
        'constraint':'检测报告','result':'检测报告'}.get(_stype,'未分类')
    _an=analytes_of(st)
    if not _an and _dt in ('原始记录','检测报告') and a.analyte:
        _an=[k for k in a.analyte.split(',') if k]
    expected.append({'record_id':e['to'],'step':st.get('step') or st.get('name'),'source_type':_stype,
                     'clauses':_cl,'doc_type':_dt,
                     'conditional':is_conditional(st,_cl),'analyte':_an})

present=[]
if a.doc_list:
    names=[l.strip() for l in open(a.doc_list,encoding='utf-8') if l.strip()]
elif a.docs:
    names=[f for f in os.listdir(a.docs) if not f.startswith('.')]
else:
    names=[]
for f in names:
    present.append({'file':f,'doc_type':doc_type(f)})

exp_types={x['doc_type'] for x in expected}
have_types={x['doc_type'] for x in present}
missing_type=sorted(exp_types-have_types)
matched=sorted(exp_types & have_types)
# 被测物覆盖：原始记录里是否有含该被测物关键词的文件
partial=[]
if a.analyte:
    kws=[k for k in a.analyte.split(',') if k]
    if '原始记录' in have_types and not any(any(k in x['file'] for k in kws) for x in present):
        partial.append({'doc_type':'原始记录','reason':f'有原始记录类文件，但未见含 {kws} 的'})

required=[x for x in expected if not x['conditional'] and x['doc_type']!='未分类']
uncategorized=[x for x in expected if x['doc_type']=='未分类']
req_types={x['doc_type'] for x in required}
missing_required=sorted(req_types-have_types)
c8={'rule_id':'ARC-C8-DOC-01','category':'C8',
    'verdict':'PASS' if not missing_required else 'UNVERIFIABLE',
    'message':('标准强制记录均已齐备' if not missing_required
               else '强制记录缺失：'+'、'.join(missing_required)),
    'missing_required':missing_required,
    'conditional_skipped':sorted({x['doc_type'] for x in expected if x['conditional']}-req_types),
    'uncategorized':len(uncategorized),
    'owner':'实验室' if missing_required else None,
    'std_anchor':{'clause':'记录','page':None,'quote':'标准要求产生的强制记录'}}

doc={'graph':a.graph,'expected_count':len(expected),'present_count':len(present),
     'required_count':len(required),'uncategorized_count':len(uncategorized),'c8_result':c8,
     'expected':expected,'present':present,
     'missing_type':missing_type,'matched':matched,'partial':partial,
     'note':'按文档类型对账；类型命中不等于内容齐备，内容层由 missing.json 与一致性核对补'}
os.makedirs(os.path.join(O,'machine'),exist_ok=True)
json.dump(doc,open(os.path.join(O,'machine','doc_gap.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps({'expected':len(expected),'present':len(present),
                  'matched':matched,'missing_type':missing_type,'partial':partial},ensure_ascii=False))
