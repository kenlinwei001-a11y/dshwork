#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为规则补「可复算」声明：值必须能从记录里的原始数据重算，而不是只报一个数。

为什么：审核时最常见的问题是「记录只写结果、没有可复算的中间量」。
       规则里声明 recompute（公式 + 所需原始输入），审核侧才能判「可复算/不可复算」。

用法: python3 declare_recompute.py --packs <包...> [--write]
"""
import argparse,glob,json,os,re,sys

# 字段 → (公式, 所需原始输入)
# 输入名 → 字段 id（绑不上就留空，审核侧会判"不可自动取值"）
BIND={'加标量':'QC.加标量','加标样测定值':'QC.加标样测定值','原样测定值':'QC.原样测定值',
 '平行样1测定值':'QC.平行样测定值1','平行样2测定值':'QC.平行样测定值2',
 '中间点标称浓度':'QC.中间点标称值','中间点实测值':'QC.中间点实测值',
 '各空白逐次测定值':'QC.空白测定值','各次测定值':'QC.重复测定值',
 '6 个浓度点':'CAL.浓度点','各点响应值':'CAL.响应值','校准系列浓度点':'CAL.浓度点',
 '响应值 y':'CAL.响应值','斜率 b':'CAL.斜率','截距 a':'CAL.截距',
 '稀释倍数 f':'CALC.稀释倍数','报告值':'CALC.结果值','仪器读数':'CAL.仪器读数',
 '空白或低浓度重复测定值':'QC.空白测定值','采样日期':'SAMP.采样日期','测定日期':'SAMP.测定日期',
 '称样量':'CHEM.称样量','定容体积':'CHEM.定容体积','移取体积':'CHEM.移取体积',
 '纯度':'CHEM.纯度','摩尔质量':'CHEM.摩尔质量','母液浓度':'CHEM.母液浓度','稀释比':'CHEM.稀释比','配制日期':'CHEM.配制日期','使用日期':'CHEM.使用日期'}

# 试剂配制类（按原文动作分类）
PREP=[
 ('solid_to_conc', r'(称取|准确称取).{0,40}(溶于|溶解|定容)',
  'c(mg/L) = m(mg) × p(%) / 100 ÷ V(L)  [或 c = m × p / (M × V) 换算为 mol/L]',
  ['称样量','纯度','定容体积']),
 ('dilute_volume', r'(加至|稀释至|定容至)[^。]{0,20}(ml|mL|L)',
  'c₂ = c₁ × V₁ / V₂（按体积稀释；V₂ 为定容体积）',
  ['母液浓度','移取体积','定容体积']),
 ('dilute_conc', r'(移取|吸取|量取).{0,40}(定容|稀释)',
  'c₂ = c₁ × V₁ / V₂   （逐级稀释）',
  ['母液浓度','移取体积','定容体积']),
 ('purity_convert', r'(按实际纯度折算|纯度.{0,10}折算|纯度大于)',
  '实际用量 m'' = m / (p/100)   （按纯度折算称样量）',
  ['称样量','纯度']),
 ('shelf_time', r'(可稳定|有效期|稳定\s*\d+\s*个月|保存期|一个月|2\s*周)',
  't = 使用日期 − 配制日期，应 ≤ 规定有效期',
  ['配制日期','使用日期']),
 ('fresh_prepare', r'(临用时现配|不得贮存|现配现用)',
  'Δt = 使用日期 − 配制日期 = 0（现配现用，不得贮存）',
  ['配制日期','使用日期']),
 ('density_volume', r'(ρ\(.{0,12}\)\s*=|密度.{0,6}g/ml).{0,30}(移取|取量)',
  'V = m / ρ   （由质量与密度换算取液体积）',
  ['移取体积','纯度']),
]

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
            text=(r.get('requirement') or '')          # 只看要求原文，避免备注里的"稳定性"误命中
            prepm=next((x for x in PREP if re.search(x[1],text)),None) if r.get('category')=='C4' else None
            if prepm and not r.get('recompute'):
                _,pat,expr,inputs=prepm
                r['recompute']={'field':(req[0] if req else 'CHEM.标准溶液浓度'),'kind':'preparation',
                                'expr':expr,'inputs':inputs,
                                'input_fields':[BIND[i] for i in inputs if i in BIND],
                                'verdict_rule':'记录缺配制参数（称样量/体积/纯度/母液浓度/日期）→ 不可复算 → UNVERIFIABLE（不得判 PASS）'}
                n+=1; added+=1; continue
            f=next((x for x in req if x in FORM),None)
            if f and not r.get('recompute'):
                expr,inputs=FORM[f]
                r['recompute']={'field':f,'expr':expr,'inputs':inputs,
                                'input_fields':[BIND[i] for i in inputs if i in BIND],
                                'verdict_rule':'记录缺任一原始输入 → 不可复算 → UNVERIFIABLE（不得判 PASS）'}
                n+=1; added+=1; continue
            # 试剂配制类：C4 或原文含配制动作，且还没声明
            if r.get('recompute'): continue
            kindm=next((x for x in PREP if re.search(x[1],text)),None)
            if not kindm: continue
            if r.get('category') not in ('C4','C5','C1','C7') and '标准溶液' not in text: continue
            _,pat,expr,inputs=kindm
            r['recompute']={'field':(req[0] if req else 'CHEM.标准溶液浓度'),
                            'kind':'preparation','expr':expr,'inputs':inputs,
                            'input_fields':[BIND[i] for i in inputs if i in BIND],
                            'verdict_rule':'记录缺配制参数（称样量/体积/纯度/母液浓度）→ 不可复算 → UNVERIFIABLE（不得判 PASS）'}
            n+=1; added+=1
        if a.write:
            with open(p,'w',encoding='utf-8') as fo:
                for r in rs: fo.write(json.dumps(r,ensure_ascii=False)+'\n')
        print(f"  {os.path.basename(pk.rstrip('/')):12s} 补 recompute {n:3d} 条 / {len(rs)}")
    print(f"\n合计：{added}/{total} 条规则声明了可复算")
    return 0

if __name__=='__main__': sys.exit(main())
