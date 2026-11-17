#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量级与跨源一致性校验（问题 #38–#41 的机制）。

三条校验：
  M1 曲线量级自洽：|斜率| × 最大浓度 ≈ 最大吸光度（|斜率|×最大浓度 与最大吸光度之比须在 0.5~2，超出即报量级错误）
  M2 系数一致：γ 与 r² 应满足 r²≈γ²（差 >0.002 报冲突）
  M3 跨源同项：同一字段在多份文档取值不同（温差 >1℃、偏差 >0.5%）→ CONFLICT_PENDING
用法: python3 magnitude_check.py --docs <目录> [--json-out <path>]
"""
import argparse,glob,json,os,re,sys

def f(x):
    try: return float(x)
    except Exception: return None

def m1(text):
    """斜率 + 最大浓度 + 最大吸光度"""
    s=re.search(r'斜率[^\d\-]{0,8}(-?[\d.]+)',text) or re.search(r'[yY]\s*=\s*(-?[\d.]+)\s*[xX]',text)
    c=re.search(r'(?:μg|ug|mg)\s*[）)]?[^\d]{0,10}([\d.]+)',text)
    ab=re.findall(r'\b(0\.\d{2,4})\b',text)
    if not (s and ab): return None
    slope=f(s.group(1)); amax=f(ab[-1]) if ab else None
    cmax=None
    for m in re.finditer(r'([\d.]+)\s*(?:μg|ug)',text):
        v=f(m.group(1)); cmax=max(cmax or 0,v)
    if slope is None or not cmax or amax is None: return None
    pred=abs(slope)*cmax
    ratio=pred/amax if amax else 0
    return {'slope':slope,'max_conc':cmax,'max_abs':amax,'predicted_abs':round(pred,3),
            'ratio':round(ratio,2),'ok':0.5<=ratio<=2.0}

def m2(text):
    g=re.search(r'(?:γ|相关系数|r)\s*[=≥]\s*(0\.9\d{2,4})',text)
    r2=re.search(r'判定系数%?\s*(?:[:：|]\s*)?(9\d\.\d{1,4})',text)
    if not (g and r2): return None
    gv=f(g.group(1)); r2v=f(r2.group(1))/100
    d=abs(r2v-gv*gv)
    return {'gamma':gv,'r2':r2v,'diff':round(d,5),'ok':d<=0.002}

def m3(docs):
    temps=[]; devs=[]
    for name,t in docs.items():
        for m in re.finditer(r'(\d{2}\.\d)\s*℃',t): temps.append((name,f(m.group(1))))
        for m in re.finditer(r'相对偏差[:：]?\s*([\d.]+)\s*%',t): devs.append((name,f(m.group(1))))
    out=[]
    for label,vals,tol in (('温度℃',temps,1.0),('相对偏差%',devs,0.5)):
        if len(vals)<2: continue
        lo=min(v for _,v in vals); hi=max(v for _,v in vals)
        out.append({'field':label,'min':lo,'max':hi,'spread':round(hi-lo,2),
                    'ok':(hi-lo)<=tol,'sources':[n for n,_ in vals][:4]})
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--docs',required=True)
    ap.add_argument('--json-out',default=''); a=ap.parse_args()
    docs={os.path.basename(p):re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',open(p,encoding='utf-8',errors='ignore').read()))
          for p in glob.glob(os.path.join(a.docs,'*.md'))}
    res=[]
    for name,t in docs.items():
        if '原始记录' not in name: continue
        r1=m1(t); r2=m2(t)
        if r1: res.append({'doc':name,'check':'M1 曲线量级',**r1,
                           'verdict':'PASS' if r1['ok'] else 'FAIL',
                           'note':f"|斜率|×最大浓度={r1['predicted_abs']} vs 最大吸光度 {r1['max_abs']}（比 {r1['ratio']}）"})
        if r2: res.append({'doc':name,'check':'M2 系数一致',**r2,
                           'verdict':'PASS' if r2['ok'] else 'CONFLICT_PENDING',
                           'note':f"γ={r2['gamma']}, r²={r2['r2']}, 差 {r2['diff']}"})
    for x in m3(docs):
        res.append({'doc':'跨文档','check':'M3 跨源一致',**x,
                    'verdict':'PASS' if x['ok'] else 'CONFLICT_PENDING',
                    'note':f"{x['field']} 极差 {x['spread']}（来源 {x['sources']}）"})
    print(json.dumps({'checks':len(res),'fail':sum(1 for x in res if x['verdict']!='PASS')},ensure_ascii=False))
    for x in res: print(f"  {x['verdict']:18s} {x['check']:12s} {x['doc'][:22]:24s} {x['note'][:62]}")
    if a.json_out: json.dump(res,open(a.json_out,'w',encoding='utf-8'),ensure_ascii=False,indent=1)
    return 0
if __name__=='__main__': sys.exit(main())
