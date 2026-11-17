#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字段-原文一致性校验：requires 指向的字段，其语义词必须出现在规则原文里。

为什么需要：准入闸只查「有没有 requires」，不查「对不对」。
  错配后果比缺证严重——判定器会去抽一个无关字段，拿错值比阈值，产出假 PASS/FAIL。

判据：
  OK        字段语义词命中，且无负向词
  CONFLICT  出现负向词（如「不得贮存」却被映射到保存时限）
  NO_KW     字段语义词未出现在原文 → 疑错配
用法: python3 check_requires_consistency.py --packs <包...> [--strict]
"""
import argparse,json,os,re,sys

# 显式语义词（优先）
SEM={
 'CAL.相关系数':['相关系数','γ','r≥','r='],
 'CAL.校准点数':['浓度点','校准点','标准系列','个点'],
 'QC.平行偏差':['平行','相对偏差'],
 'QC.加标回收率':['回收率','加标'],
 'QC.加标比例':['加标'],
 'QC.空白值':['空白'],'QC.空白个数':['空白'],
 'QC.中间点误差':['中间点','中间浓度','核查'],
 'QC.精密度RSD':['相对标准偏差','精密度','RSD'],
 'SCOPE.基质':['地表水','地下水','废水','污水','基质','样品类型'],
 'APPA.分离度':['分离度','分辨率'],
 'SCOPE.检出限':['检出限'],'SCOPE.测定下限':['测定下限'],
 'SCOPE.测定范围':['测定范围','线性范围'],'SCOPE.光程':['光程','比色皿','检测池'],
 'SCOPE.粒径上限':['粒径','悬浮物'],
 'SAMP.保存pH':['pH'],'SAMP.保存温度':['℃','保存温度','冷藏','冷冻'],
 'SAMP.保存时限':['保存','贮存','天内','个月','h'],
 'SAMP.固定剂':['硫酸','硝酸','盐酸','酸化','保存剂'],
 'SAMP.采样容器':['容器','瓶','聚乙烯','玻璃'],
 'APPA.仪器编号':['仪器编号'],'APPA.校准有效期':['校准','检定','有效期'],
 'APPA.检测波长':['波长','nm'],'APPA.环境温度':['室温','环境温度'],
 'APPA.流速':['流速','ml/min','mL/min'],'APPA.进样量':['进样量'],
 'APPA.消解温度':['消解','120','124'],
 'CHEM.标准溶液浓度':['贮备液','储备液','使用液','标准溶液','浓度'],
 'CHEM.试剂有效期':['有效期'],'CHEM.实验用水电导率':['电导率'],
 'CHEM.试剂等级':['优级纯','分析纯','纯度'],
 'CALC.稀释倍数':['稀释'],'CALC.结果值':['结果','保留','修约'],
 'CAL.仪器读数':['仪器读数','样品量'],
 'REC.检测人':['检测人','审核人'],'REC.报告要素':['报告','载明','表述'],
 'PROC.曲线批次时间':['批次','检测日期'],'PROC.样品批次时间':['批次','检测日期'],
}
NEG={'SAMP.保存时限':['不得贮存','现配','临用时现配'],
     'SAMP.保存温度':['干燥','烘干','恒重','灰化'],
     'APPA.消解温度':['消解效率','R 应大于'],
     'APPA.检测波长':['天平','精度'],
     'CHEM.试剂有效期':['保存期']}

def kws(f):
    if f in SEM: return SEM[f]
    core=f.split('.')[-1]
    return [core]

def judge(rule):
    req=rule.get('requires') or []
    if not req: return None
    text=(rule.get('requirement') or '')+' '+(rule.get('anchor_notes') or '')
    bad=[]; nokw=[]
    for f in req:
        if any(n in text for n in NEG.get(f,[])): bad.append(f)
        elif not any(k in text for k in kws(f)): nokw.append(f)
    if bad: return 'CONFLICT',bad,text
    if nokw: return 'NO_KW',nokw,text
    return 'OK',[],text

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--packs',nargs='+',required=True)
    ap.add_argument('--out',default=''); ap.add_argument('--strict',action='store_true'); a=ap.parse_args()
    rows=[]; from collections import Counter; c=Counter()
    for pk in a.packs:
        std=os.path.basename(pk.rstrip('/'))
        for l in open(os.path.join(pk,'rules.jsonl'),encoding='utf-8'):
            if not l.strip(): continue
            r=json.loads(l); res=judge(r)
            if res is None: continue
            st,fs,text=res; c[st]+=1
            if st!='OK':
                rows.append({'standard':std,'rule_id':r['rule_id'],'requires':r['requires'],
                             'status':st,'fields':fs,'requirement':text[:110],
                             'requires_source':r.get('requires_source')})
    print(json.dumps({'checked':c['OK']+c['CONFLICT']+c['NO_KW'],'OK':c['OK'],
                      'CONFLICT':c['CONFLICT'],'NO_KW':c['NO_KW']},ensure_ascii=False))
    for x in rows[:12]:
        print(f"  {x['status']:9s} {x['standard']:11s} {x['rule_id']:20s} {x['fields']} ← {x['requirement'][:56]}")
    if a.out:
        with open(a.out,'w',encoding='utf-8') as f:
            for x in rows: f.write(json.dumps(x,ensure_ascii=False)+'\n')
        print(f"  → {a.out}")
    return 1 if (a.strict and rows) else 0
if __name__=='__main__': sys.exit(main())
