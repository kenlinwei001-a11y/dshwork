#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档要素定位：把「规则要的证据」定位到「哪份文档的哪一节哪一栏」。

三级键: doc_type / section / field
匹配等级:
  EXACT   doc_type+section+field 全中
  SECTION doc_type+section 中，field 未命中
  DOC     仅 doc_type 中（旧行为，风险最高：会把"同类文档"当"同一文档"）
  NONE    该 doc_type 本批不存在 → 不得判 PASS/FAIL，只能 UNVERIFIABLE(DOC_ABSENT)
用法:
  python3 doc_element_locator.py --packs <包...> --docs <目录> [--min-level EXACT]
"""
import argparse,glob,json,os,re,sys

# 文档类型别名：同一份文档的多种叫法归到同一 doc_type
ALIAS={
 '委托书':['委托书','测试委托','委托单'],
 '合同评审':['合同评审'],
 '风险评估':['风险评估','风险识别'],
 '样品流转单':['出入库','流转单','样品登记'],
 '检测任务单':['任务单'],
 '原始记录':['原始记录','检测记录','测定记录'],
 '前处理记录':['前处理','消解记录','萃取记录'],
 '检测报告':['检测报告','检验报告'],
 '仪器使用记录':['仪器运行','仪器使用'],
 '环境记录':['环境记录','温湿度'],
 '校准证书':['校准证书','检定证书'],
 '试剂配制记录':['试剂配制'],
 '质控记录':['质控','加标','平行'],
}
def doc_type_of(name):
    for t,keys in ALIAS.items():
        if any(k in name for k in keys): return t
    return '未知'

def sections_of(text):
    """区块标题：中文短行 / 表格首列标签"""
    secs=set()
    for m in re.finditer(r'<td[^>]*>([^<]{2,14})</td>',text):
        s=m.group(1).strip()
        if s and not re.fullmatch(r'[\d.\s%\-/]+',s): secs.add(s)
    for line in text.splitlines():
        s=re.sub(r'<[^>]+>','',line).strip()
        if 2<=len(s)<=16 and not re.search(r'[。；]',s): secs.add(s)
    return secs

def scan_docs(d):
    out=[]
    for p in sorted(glob.glob(os.path.join(d,'*.md'))):
        name=os.path.basename(p); t=open(p,encoding='utf-8',errors='ignore').read()
        out.append({'file':name,'doc_type':doc_type_of(name),'sections':sections_of(t),'text':t})
    return out

def locate(target,docs):
    dt=(target or {}).get('doc_type') or ''
    field=(target or {}).get('field') or ''
    hints=(target or {}).get('match_hints') or []
    same=[x for x in docs if x['doc_type']==dt]
    if not same: return 'NONE',None,'该 doc_type 本批不存在'
    if field or hints:
        for x in same:
            if field and field in x['text']: return 'EXACT',x,'字段名命中'
            hit=[h for h in hints if h in x['text']]
            if hints and len(hit)>=max(1,len(hints)//2): return 'EXACT',x,f'关键词命中 {hit[:3]}'
        return 'SECTION',same[0],'doc_type 存在但字段/关键词未命中'
    return 'DOC',same[0],'仅按 doc_type 定位'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--packs',nargs='+',required=True)
    ap.add_argument('--docs',required=True); ap.add_argument('--min-level',default='SECTION')
    ap.add_argument('--json-out'); a=ap.parse_args()
    docs=scan_docs(a.docs)
    print("本批文档类型:",dict(sorted({d['doc_type']:0 for d in docs}.items())) or '空')
    from collections import Counter
    c=Counter(); rows=[]
    for pk in a.packs:
        std=os.path.basename(pk.rstrip('/'))
        for l in open(os.path.join(pk,'rules.jsonl'),encoding='utf-8'):
            if not l.strip(): continue
            r=json.loads(l); t=r.get('target') or {}
            lv,f,why=locate(t,docs)
            c[lv]+=1
            rows.append({'standard':std,'rule_id':r['rule_id'],'doc_type':t.get('doc_type'),
                         'field':t.get('field'),'level':lv,'file':(f or {}).get('file'),'why':why})
    print(f"\n定位等级: {dict(sorted(c.items()))}")
    if a.json_out: json.dump(rows,open(a.json_out,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    order=['NONE','DOC','SECTION','EXACT']
    lim=order.index(a.min_level)
    bad=[x for x in rows if order.index(x['level'])<lim]
    if bad:
        print(f"\n低于 {a.min_level} 的规则 {len(bad)} 条（不得据此判 PASS/FAIL）：")
        for x in bad[:12]:
            print(f"  {x['level']:8s} {x['standard']:11s} {x['rule_id']:22s} 要 {x['doc_type']}／{x['field']} —— {x['why']}")
    return 0

if __name__=='__main__': sys.exit(main())
