#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次级步骤顺序校验（procedure_order）：三条规则 + 严格同日口径。

规则：
  PROC-01 曲线批 ≤ 样品批        校准先于测定
  PROC-02 空白批覆盖每一样品批     每批都要有空白
  PROC-03 加标批 ≥ 首个样品批      加标在样品之后或同批
口径（关键）：
  两批都有时分       → 严格比较时间戳，PASS/FAIL
  只有日期且不同     → 按日期比较，PASS/FAIL
  只有日期且相同     → UNVERIFIABLE(SAME_DAY)：顺序不可分辨，**不得判 PASS**
  任一侧无时间       → UNVERIFIABLE(NO_TIME)
用法: python3 check_procedure_order.py --docs <目录> [--json-out <path>] [--rules-out <path>]
"""
import argparse,glob,json,os,re,sys
from datetime import datetime

DATE=re.compile(r'(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})')
TIME=re.compile(r'(\d{1,2}):(\d{2})(?::(\d{2}))?')
CURVE=re.compile(r'(标准曲线|校正总结|校准曲线|工作曲线)')
SAMPLE=re.compile(r'(样品(测试|检测)?结果|样品测定|样品检测记录)')
SPIKE=re.compile(r'(加标|加标回收)')
BLANK=re.compile(r'(空白样?品?1|空白试验|空白吸光度|平均值\s*Ab|<0\.0\d{2})')

RULES=[
 {'rule_id':'PROC-01','name':'曲线批不晚于样品批','kind':'procedure_order',
  'requirement':'标准曲线（校准）批次的测定时间应不晚于首个样品批次的测定时间','criticality':'KEY'},
 {'rule_id':'PROC-02','name':'空白覆盖每个样品批','kind':'procedure_order',
  'requirement':'每一个样品测定批次都应有对应的空白试验记录','criticality':'KEY'},
 {'rule_id':'PROC-03','name':'加标批不早于样品批','kind':'procedure_order',
  'requirement':'加标（回收率）试验应在样品测定之后或同批进行','criticality':'KEY'},
]

def events(text):
    ev=[]
    for m in re.finditer(r'检测日期[:：]?\s*',text):
        seg=text[m.end():m.end()+900]
        d=DATE.search(seg)
        if not d: continue
        t=TIME.search(seg[:200])
        ts=datetime(int(d.group(1)),int(d.group(2)),int(d.group(3)),
                    int(t.group(1)) if t else 0,int(t.group(2)) if t else 0)
        kinds=[]
        if CURVE.search(seg): kinds.append('曲线批')
        if SAMPLE.search(seg): kinds.append('样品批')
        if SPIKE.search(seg): kinds.append('加标批')
        if BLANK.search(seg): kinds.append('空白批')
        for k in (kinds or ['未识别']):
            ev.append({'batch':k,'ts':ts,'has_time':bool(t),'quote':seg[:60]})
    for m in re.finditer(r'进样日期[^\n]{0,30}',text):
        seg=text[m.start():m.start()+260]
        d=DATE.search(seg) or DATE.search(text[m.start():m.start()+260])
        t=TIME.search(seg)
        if not d: continue
        ts=datetime(int(d.group(1)),int(d.group(2)),int(d.group(3)),
                    int(t.group(1)) if t else 0,int(t.group(2)) if t else 0)
        (ev.append({'batch':'曲线批','ts':ts,'has_time':bool(t),'quote':seg[:60]})
         if CURVE.search(seg) or '进样' in seg else None)
    return ev

def cmp_batches(a,b,label):
    """a 应不晚于 b → PASS；a 晚于 b → FAIL；同日无时分 → UNVERIFIABLE"""
    if not a or not b: return 'UNVERIFIABLE','NO_TIME','任一批次无时间信息'
    a_min=min(x['ts'] for x in a); b_min=min(x['ts'] for x in b)
    has_t=all(x['has_time'] for x in a) and all(x['has_time'] for x in b)
    if a_min.date()==b_min.date() and not has_t:
        return 'UNVERIFIABLE','SAME_DAY',f'同为 {a_min.date()}，无时分，顺序不可分辨'
    return ('PASS','OK',f'{a_min:%Y-%m-%d %H:%M} ≤ {b_min:%Y-%m-%d %H:%M}'
            if a_min<=b_min else 'FAIL','ORDER','') if a_min<=b_min else \
           ('FAIL','ORDER',f'{a_min:%Y-%m-%d %H:%M} > {b_min:%Y-%m-%d %H:%M}')

def check_one(ev):
    g=lambda k:[x for x in ev if x['batch']==k]
    curve,sample,blank,spike=g('曲线批'),g('样品批'),g('空白批'),g('加标批')
    res={}
    res['PROC-01']=cmp_batches(curve,sample,'曲线≤样品')
    # PROC-02：每个样品批日期是否都有空白记录
    if not sample: res['PROC-02']=('UNVERIFIABLE','NO_SAMPLE','无样品批')
    elif not blank: res['PROC-02']=('FAIL','NO_BLANK','有样品批但无任何空白记录')
    else:
        sd={x['ts'].date() for x in sample}; bd={x['ts'].date() for x in blank}
        miss=sorted(str(d) for d in sd-bd)
        res['PROC-02']=('PASS','OK','每批均有空白') if not miss else ('FAIL','BLANK_GAP',f'缺空白批次 {miss}')
    # PROC-03：加标不早于首个样品批
    if not spike: res['PROC-03']=('UNVERIFIABLE','NO_SPIKE','无加标记录')
    else: res['PROC-03']=cmp_batches(sample[:1],spike,'样品≤加标')
    return res

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--docs',required=True)
    ap.add_argument('--json-out',default=''); ap.add_argument('--rules-out',default=''); a=ap.parse_args()
    report=[]
    for f in sorted(glob.glob(os.path.join(a.docs,'*.md'))):
        name=os.path.basename(f)
        if '原始记录' not in name: continue
        text=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',open(f,encoding='utf-8',errors='ignore').read()))
        ev=events(text)
        res=check_one(ev)
        report.append({'doc':name,'events':[{**e,'ts':e['ts'].isoformat(sep=' ')} for e in ev],
                       'verdicts':{k:{'verdict':v[0],'code':v[1],'reason':v[2]} for k,v in res.items()}})
        print(f"── {name[:34]}")
        for rid in ('PROC-01','PROC-02','PROC-03'):
            v=res[rid]; print(f"     {rid} {v[0]:14s} {v[2]}")
    if a.json_out:
        os.makedirs(os.path.dirname(a.json_out) or '.',exist_ok=True)
        json.dump(report,open(a.json_out,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    if a.rules_out:
        cards=[]
        for r in RULES:
            cards.append({**r,'category':'C5','requires':['PROC.曲线批次时间','PROC.样品批次时间','PROC.空白批次数','PROC.加标批次时间'],
                          'check_targets':[{'target_type':'process_record','doc_type':'原始记录',
                          'field':'检测日期/进样时间','match_hints':['检测日期','进样日期','序列'],'locator_strategy':'keyword'}],
                          'on_missing':'UNVERIFIABLE','impact':'record_gap','origin':'derived',
                          'anchor_notes':'批次时间证据：每页检测日期 + 仪器进样时间'})
        json.dump({'audit_rule_cards':cards},open(a.rules_out,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
        print(f"\n  规则卡 → {a.rules_out}")
    return 0
if __name__=='__main__': sys.exit(main())
