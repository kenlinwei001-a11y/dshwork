#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为规则补「可复算」声明：值必须能从记录里的原始数据重算，而不是只报一个数。

为什么：审核时最常见的问题是「记录只写结果、没有可复算的中间量」。
       规则里声明 recompute（公式 + 所需原始输入），审核侧才能判「可复算/不可复算」。

用法: python3 declare_recompute.py --packs <包...> [--write]
"""
import argparse,glob,json,os,sys

# 字段 → (公式, 所需原始输入)
FORM={
 'QC.加标回收率':('P = (加标样测定值 − 原样测定值) / 加标量 × 100%',
                  ['加标量','加标样测定值','原样测定值']),
 'QC.平行偏差':('RPD = |x₁ − x₂| / ((x₁ + x₂)/2) × 100%',['平行样1测定值','平行样2测定值']),
 'QC.中间点误差':('RE = (实测值 − 标称值) / 标称值 × 100%',['中间点标称浓度','中间点实测值']),
 'QC.空白值':('Ab = 批内各空白测定值算术平均',['各空白逐次测定值']),
 'QC.精密度RSD':('RSD = s / x̄ × 100%',['各次测定值']),
 'CAL.相关系数':('r：以校准系列（浓度, 响应值）最小二乘回归求得',['6 个浓度点','各点响应值']),
 'CAL.斜率':('b：校准系列回归斜率',['6 个浓度点','各点响应值']),
 'CAL.截距':('a：校准系列回归截距',['6 个浓度点','各点响应值']),
 'CAL.校准点数':('计数：校准系列浓度点个数',['校准系列浓度点']),
 'CALC.结果值':('ρ = (y − a) / b × f（或按标准公式卡）',['响应值 y','斜率 b','截距 a','稀释倍数 f']),
 'CALC.稀释倍数':('f = 报告值 / 仪器读数（稀释前）',['报告值','仪器读数']),
 'SCOPE.检出限':('按标准/附录给定公式（如 3.14×s 或空白标准偏差法）',['空白或低浓度重复测定值']),
 'SAMP.保存时限':('t = 测定日期 − 采样日期（天）',['采样日期','测定日期']),
}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--packs',nargs='+',required=True)
    ap.add_argument('--write',action='store_true'); a=ap.parse_args()
    total=added=0
    for pk in a.packs:
        p=os.path.join(pk,'rules.jsonl')
        if not os.path.exists(p): continue
        rs=[json.loads(l) for l in open(p,encoding='utf-8') if l.strip()]
        n=0
        for r in rs:
            total+=1
            req=(r.get('requires') or [])
            f=next((x for x in req if x in FORM),None)
            if not f or r.get('recompute'): continue
            expr,inputs=FORM[f]
            r['recompute']={'field':f,'expr':expr,'inputs':inputs,
                            'verdict_rule':'记录缺任一原始输入 → 不可复算 → UNVERIFIABLE（不得判 PASS）'}
            n+=1; added+=1
        if a.write:
            with open(p,'w',encoding='utf-8') as fo:
                for r in rs: fo.write(json.dumps(r,ensure_ascii=False)+'\n')
        print(f"  {os.path.basename(pk.rstrip('/')):12s} 补 recompute {n:3d} 条 / {len(rs)}")
    print(f"\n合计：{added}/{total} 条规则声明了可复算")
    return 0

if __name__=='__main__': sys.exit(main())
