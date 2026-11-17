#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用槽位填充：由任务单的 label + match_hints 驱动，支持 HTML 表格与纯文本。

用法:
  python3 fill_slots.py --out <run> --packs <包目录...> --docs <文档目录> [--write]

流程:
  ① 从判定包 rules.jsonl 生成 slot 任务（按标准命名空间：HJ636-S010）
  ② 按 doc_type 选文档（文件名前缀 → 类型）
  ③ 逐任务：在候选文档里按 hint 定位，取「标签右侧/单元格右侧/标签后 60 字内」的数值
  ④ 写 machine/report_slots.json 与 report_spans.json（含 doc + quote）
口径: 取不到就不填（UNVERIFIABLE），不猜、不跨文档硬填。
"""
import argparse,glob,json,os,re,sys

DOC_TYPE={'原始记录':'原始记录','质控记录':'原始记录','前处理记录':'原始记录','试剂配制记录':'原始记录',
          '检测报告':'检测报告','样品流转单':'样品流转单','仪器使用记录':'仪器使用记录',
          '环境记录':'环境记录','校准证书':'校准证书','委托书':'委托书','检测任务单':'检测任务单',
          '合同评审':'合同评审','风险评估':'风险评估'}
NUM=r'([-+]?\d+(?:\.\d+)?)'
UNIT=r'(mg/L|μg/L|ug/L|mg|g|mL|ml|L|%|℃|d|h|min|nm|mm|μm|um|个|倍|1)'

def texts(docs_dir):
    out=[]
    for p in sorted(glob.glob(os.path.join(docs_dir,'*.md'))):
        name=os.path.basename(p); typ=name.split('-')[0]
        out.append({'path':p,'name':name,'type':DOC_TYPE.get(typ,typ),
                    'text':open(p,encoding='utf-8',errors='ignore').read()})
    return out

def cells(text):
    """把 HTML 表格拆成「单元格 + 同行下一格」，用于 label→value。"""
    pairs=[]
    for tr in re.findall(r'<tr>(.*?)</tr>', text, re.S):
        tds=[re.sub(r'<[^>]+>','',x).strip() for x in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
        for i,c in enumerate(tds[:-1]):
            pairs.append((c, tds[i+1]))
    return pairs

STDNO=re.compile(r'(HJ|GB|GB/T|HJ/T)\s*\d[\d./-]*')
DATE=re.compile(r'^20\d{2}[.\-/]')

def _ok(task, val, unit, ctx):
    """三条校验：① 不像标准号/日期 ② 单位要对得上 ③ 期望是文本时别塞数字"""
    exp=task.get('value'); exp_unit=(task.get('unit') or '').strip()
    if STDNO.search(ctx or ''): return False
    if DATE.match(str(val)): return False
    if isinstance(exp,list) and exp and isinstance(exp[0],str): return False   # in 清单：应匹配文本
    if isinstance(exp,str): return False
    if exp_unit and exp_unit not in ('1','类型'):
        if not unit or unit.replace('ml','mL').replace('ug','μg')!=exp_unit: return False
    return True

BIND={'HJ636':'总氮','HJ535':'氨氮','HJ84':'硝酸根','HJ671':'总磷','HJ700':'金属'}
AGG={'相对偏差':'max','回收率':'min','相关系数':'last','检出限':'min'}

def _bound(task, docs):
    std=str(task.get('standard') or '')
    kw=next((v for k,v in BIND.items() if k in std), None)
    if kw:
        hit=[d for d in docs if kw in d['name']]
        if hit: return hit
    return docs

def find(task, docs):
    docs=_bound(task, docs)
    hits=[]
    label=task.get('label') or ''; hints=[h for h in (task.get('match_hints') or []) if h]
    want=task.get('doc_type'); want=DOC_TYPE.get(want,want)
    cands=[d for d in docs if d['type']==want] or [d for d in docs if '原始记录' in d['type']]
    keys=[label]+hints
    for d in cands:
        for k in keys:
            if not k: continue
            for c,nxt in cells(d['text']):
                if k in c:
                    m=re.search(NUM+r'\s*'+UNIT+'?', nxt) or re.search(NUM, nxt)
                    if m:
                        v=m.group(1); u=(m.group(2) if m.lastindex and m.lastindex>=2 else '')
                        if _ok(task, v, u, c+' '+nxt) and not re.search(r'[0-9a-f]{16,}', c+nxt):
                            hits.append({'value':float(v),'unit':u or task.get('unit'),
                                         'doc':d['name'],'quote':(c+' | '+nxt)[:90],'method':'table_cell'})
            for m in re.finditer(re.escape(k)+r'[^\n]{0,60}', d['text']):
                seg=m.group(0)
                mm=re.search(NUM+r'\s*'+UNIT+'?', seg[len(k):])
                if mm:
                    v=mm.group(1); u=(mm.group(2) if mm.lastindex and mm.lastindex>=2 else '')
                    if _ok(task, v, u, seg) and not re.search(r'[0-9a-f]{16,}', seg):
                        hits.append({'value':float(v),'unit':u or task.get('unit'),
                                     'doc':d['name'],'quote':seg[:90],'method':'keyword'})
    if not hits: return None
    lab=str(task.get('label') or '')
    how=next((v for k,v in AGG.items() if k in lab), 'first')
    if how=='max':   return max(hits,key=lambda x:x['value'])
    if how=='min':   return min(hits,key=lambda x:x['value'])
    if how=='last':  return hits[-1]
    return hits[0]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True)
    ap.add_argument('--packs',nargs='+',required=True); ap.add_argument('--docs',required=True)
    ap.add_argument('--write',action='store_true'); a=ap.parse_args(); O=a.out
    docs=texts(a.docs)
    tasks=[]
    for pk in a.packs:
        std=os.path.basename(pk.rstrip('/'))
        for line in open(os.path.join(pk,'rules.jsonl'),encoding='utf-8'):
            r=json.loads(line); t=r.get('target') or {}
            if not t.get('slot'): continue
            tasks.append({'task_id':f"{std}-{t['slot']}",'slot':f"{std}-{t['slot']}",'standard':std,
                          'rule_id':r['rule_id'],'label':t.get('field') or r['requirement'][:24],
                          'doc_type':t.get('doc_type'),'match_hints':t.get('match_hints') or [],
                          'op':(r.get('predicate') or {}).get('op'),
                          'value':(r.get('predicate') or {}).get('value'),
                          'unit':(r.get('predicate') or {}).get('unit')})
    slots={}; spans={}; by_type={}
    for t in tasks:
        hit=find(t,docs)
        if hit:
            slots[t['slot']]=hit['value']
            spans[t['slot']]={'doc':hit['doc'],'quote':hit['quote'],'method':hit['method'],'unit':hit.get('unit')}
            by_type[t['doc_type']]=by_type.get(t['doc_type'],0)+1
    os.makedirs(os.path.join(O,'machine'),exist_ok=True)
    if a.write:
        json.dump(slots,open(os.path.join(O,'machine','report_slots.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
        json.dump(spans,open(os.path.join(O,'machine','report_spans.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
        with open(os.path.join(O,'machine','slot_tasks.jsonl'),'w',encoding='utf-8') as f:
            for t in tasks: f.write(json.dumps(t,ensure_ascii=False)+'\n')
    from collections import Counter
    print(json.dumps({'tasks':len(tasks),'filled':len(slots),
                      'fill_rate':round(len(slots)/max(len(tasks),1),3),
                      'by_doc_type':by_type,
                      'docs':Counter(d['type'] for d in docs)},ensure_ascii=False))
    return 0
if __name__=='__main__': sys.exit(main())
