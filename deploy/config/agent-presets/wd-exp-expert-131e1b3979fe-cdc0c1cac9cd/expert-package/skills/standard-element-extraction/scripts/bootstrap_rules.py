#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 01-clauses 自举初版要素与规则卡（不调模型，粗粒度但可追溯）。

用法: python3 bootstrap_rules.py --out <run> [--write]

做什么：
  02-elements.json：按章映射步骤节点（procedure_graph），要素族按章归类
  03-rules.json   ：逐条条款生成规则卡；能抽到阈值的给 predicate，抽不到的标 qualitative
判定口径：
  章 → C 类映射（可改）：1→C1 3→C1 4→C1 5→C4 6→C3 7→C2/C5 8→C5 9→C6 10→C7 11+→C7/C8
  阈值抽取：≥/≤/不得大于/不少于 + 数字（含单位）
限制：这是"初版"，必须人工复核；抽不到阈值的一律 qualitative，不硬造。
"""
import argparse,json,os,re,sys

_TOC = re.compile(r'^\s*#*\s*(?:\d{1,2}(?:\.\d{1,2})*|表\s?[0-9]{1,2}|附录\s?[A-Z])[^\n]{0,70}(?:\.{3,}|…{2,}|·{3,})\s*\d+\s*$')
def _strip_toc(text):
    """去目录行：标准开头都有「1 适用范围....1」，不过滤会把目录当条款正文。"""
    return '\n'.join(l for l in text.splitlines() if not _TOC.match(l))


def _body_after(md, no, n=200):
    """条款号最后一次出现之后的正文（TOC 行已被 _strip_toc 去掉，取最后一处最接近正文）。"""
    import re as _r
    occ=[m.start() for m in _r.finditer(r'(?m)^\s*#*\s*'+_r.escape(str(no))+r'(?![\d.])', md)]
    if not occ: return ''
    seg=md[occ[-1]:occ[-1]+n]
    return _r.sub(r'\s+',' ',seg).strip()

CH_CAT={'1':'C1','2':'C1','3':'C1','4':'C1','5':'C4','6':'C3','7':'C2','8':'C5','9':'C6','10':'C7'}
CH_NAME={'1':'适用范围','2':'规范性引用文件','3':'方法原理','4':'干扰和消除','5':'试剂和材料',
         '6':'仪器和设备','7':'样品','8':'分析步骤','9':'计算','10':'精密度和准确度',
         '11':'质量保证和质量控制','12':'废物处理','13':'注意事项'}
NUM=r'(\d+(?:\.\d+)?)'
PAT=[(rf'[≥>]=?\s*{NUM}', '>='), (rf'[≤<]=?\s*{NUM}', '<='),
     (rf'不得(?:大于|超过|高于)\s*{NUM}', '<='), (rf'不得(?:小于|低于)\s*{NUM}', '>='),
     (rf'(?:不少于|不低于|至少)\s*{NUM}', '>='), (rf'(?:不大于|不超过|至多)\s*{NUM}', '<=')]

def pred_of(q):
    for rx,op in PAT:
        m=re.search(rx,q)
        if m:
            unit='%' if '%' in q[max(0,m.start()-0):m.end()+8] else None
            return {'op':op,'value':float(m.group(1)),'unit':unit}, m.group(0)
    return None,None

def section_text(md, no):
    """从源文本里取该条款的整段（到下一个同级/上级条款为止）。"""
    lines=md.splitlines()
    pat=re.compile(r'^\s*'+re.escape(no)+r'(?![\d.])')
    start=None
    for i,l in enumerate(lines):
        if pat.match(l): start=i; break
    if start is None: return ''
    out=[lines[start]]
    for l in lines[start+1:]:
        if re.match(r'^\s*\d+(?:\.\d+){0,2}\s+\S', l): break
        out.append(l)
        if len(' '.join(out))>1200: break
    return ' '.join(out)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); ap.add_argument('--write',action='store_true')
    ap.add_argument('--text',default=None); ap.add_argument('--standard',default=None)
    a=ap.parse_args(); O=a.out
    cl=json.load(open(os.path.join(O,'01-clauses.json'),encoding='utf-8'))
    std=cl.get('standard_id') or a.standard or os.path.basename(os.path.dirname(O.rstrip('/')))
    md=''
    if a.text and os.path.exists(a.text): md=_strip_toc(open(a.text,encoding='utf-8').read())
    reg=cl.get('clause_registry') or []
    steps=[]; elements=[]; rules=[]
    seen_step=set()
    for x in reg:
        no=str(x['clause']); top=no.split('.')[0]
        cat=CH_CAT.get(top,'C8' if int(top)>=11 else 'C5')
        q=x.get('quote') or ''
        # 步骤节点：每章一个
        if top not in seen_step and top in CH_NAME:
            seen_step.add(top)
            steps.append({'id':f'P{top}','clause':top,'step':CH_NAME[top],
                          'params':[],'done_when':f'完成第{top}章要求','conditional':top in ('4',)})
        body=(section_text(md,no) or _body_after(md,no)) if md else ''
        pred,hit=pred_of(body or q)
        rid=f"ARC-{cat}-{no}-01"
        rules.append({'rule_id':rid,'category':cat,'clause':no,
                      'requirement':((body or q)[:180]),
                      'predicate':pred,
                      'on_missing':'FAIL' if cat=='C8' else 'UNVERIFIABLE',
                      'check_targets':[], 'origin':'derived' if pred else 'verbatim',
                      'evidence_required':[], 'source_layer':'STANDARD'})
        elements.append({'element_id':f"SE-{cat}-{no}-01",'family':{'C1':'SCOPE','C2':'SAMP','C3':'APPA',
                        'C4':'MATL','C5':'PROC','C6':'CALC','C7':'QC','C8':'META'}[cat],
                        'statement':((body or q)[:160]),'parameters':([{'name':'阈值','value':pred['value'],'unit':pred['unit'] or '1'}]
                        if pred else []),'obligation':'MUST' if x.get('modality')in('MUST','应') else 'SHOULD',
                        'applicability':'本标准适用域','evidence':[],'source_layer':'STANDARD',
                        'anchor':{'clause':no,'page':x.get('page'),'quote':(body or q)[:120]},
                        'origin':'derived' if pred else 'verbatim'})
    # C7 质控门 → 连到「分析步骤」与「结果」节点，满足不变量（verifies/invalidates 至少一条）
    qc=[r['rule_id'] for r in rules if r['category']=='C7']
    extra=[{'from':f'SE-C7-{r["clause"]}-01','to':'P8','type':'verifies'} for r in rules if r['category']=='C7' and '8' in {x['clause'] for x in steps}]
    extra+=[{'from':f'SE-C7-{r["clause"]}-01','to':'P9','type':'invalidates'} for r in rules if r['category']=='C7']
    el={'standard_id':std,'elements':elements,
        'procedure_graph':{'nodes':steps,'edges':[{'from':f'P{steps[i]["clause"]}','to':f'P{steps[i+1]["clause"]}','type':'precedes'} for i in range(len(steps)-1)]+extra}}
    ru={'standard_id':std,'audit_rule_cards':rules}
    if a.write:
        json.dump(el,open(os.path.join(O,'02-elements.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
        json.dump(ru,open(os.path.join(O,'03-rules.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    from collections import Counter
    print(json.dumps({'standard':std,'clauses':len(reg),'steps':len(steps),
                      'rules':len(rules),'with_predicate':sum(1 for r in rules if r['predicate']),
                      'by_category':dict(Counter(r['category'] for r in rules))},ensure_ascii=False))
    return 0
if __name__=='__main__': sys.exit(main())
