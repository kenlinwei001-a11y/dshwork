#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""值归一化层：枚举同义词/上位词、单位换算、ND 语义。

用法（库）:
  from value_normalize import load, normalize_enum, convert_unit, null_kind, eval_in
用法（自测）:
  python3 value_normalize.py --selftest
"""
import json,os,sys

DEFAULT=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     'contracts','value_normalize.json')


# 内置兜底词典（包内无 contracts/ 时使用；与 contracts/value_normalize.json 同构）
_EMBED = {
 "enums": {
  "基质": {"canonical": ["地表水","地下水","工业废水","生活污水"],
           "synonyms": {"废水": {"maps_to": ["工业废水","生活污水"], "how": "上位词拆分（含歧义）"},
                         "污水": {"maps_to": ["生活污水"], "how": "同义"},
                         "地表水/地下水": {"maps_to": ["地表水","地下水"], "how": "并列写法"},
                         "生活废水": {"maps_to": ["生活污水"], "how": "同义"}}},
  "介质": {"canonical": ["水","废水","土壤","底泥","固废","环境空气","废气","生物"],
           "synonyms": {"水样": {"maps_to": ["水"], "how": "同义"},
                         "气样": {"maps_to": ["环境空气","废气"], "how": "上位词拆分（含歧义）"},
                         "泥样": {"maps_to": ["底泥"], "how": "同义"}}},
  "定量方式": {"canonical": ["峰面积","峰高"], "synonyms": {"峰面积定量": {"maps_to": ["峰面积"], "how": "同义"}}}
 },
 "units": {"mg/L": {"μg/L": 1000.0, "ug/L": 1000.0, "g/L": 0.001},
           "μg/L": {"mg/L": 0.001, "ug/L": 1.0},
           "mg/kg": {"μg/kg": 1000.0, "ug/kg": 1000.0},
           "μg/m3": {"mg/m3": 0.001}, "mg/m3": {"μg/m3": 1000.0},
           "g": {"mg": 1000.0, "μg": 1000000.0}, "mL": {"L": 0.001, "ml": 1.0}, "L": {"mL": 1000.0},
           "%": {"1": 0.01}, "℃": {"°C": 1.0}},
 "nulls": {"ND": {"kind": "below_lod", "note": "低于检出限；上限类阈值可推定满足"},
           "未检出": {"kind": "below_lod", "note": "同 ND"},
           "n.a.": {"kind": "not_applicable", "note": "该行无此量的定义"},
           "/": {"kind": "no_item", "note": "无此项/未计算"},
           "-": {"kind": "not_occurred", "note": "未发生（如未稀释→倍数取1）"}}
}

def load(path=None):
    p = path or DEFAULT
    if os.path.exists(p):
        return json.load(open(p,encoding='utf-8'))
    return _EMBED          # 包内无 contracts/ 时用内置兜底

def normalize_enum(val, allowed, table):
    """返回 (mapped_list|None, how)。mapped 全部落在 allowed 内才算成功。"""
    v=str(val).strip()
    if v in allowed: return [v], '字面命中'
    enums=table.get('enums',{})
    for name,spec in enums.items():
        canon=spec.get('canonical',[])
        if not set(allowed) & set(canon): continue
        syn=spec.get('synonyms',{}).get(v)
        if syn:
            mapped=syn['maps_to']
            return (mapped,syn['how']) if set(mapped) <= set(allowed) else (None,'映射越界')
        # 组合写法：A/B、A、B、A;B
        parts=[p for p in v.replace('、','/').replace(';','/').replace('，','/').split('/') if p]
        if len(parts)>1 and set(parts) <= set(allowed):
            return parts,'并列写法拆分'
    return None,'未收录同义词'

def convert_unit(value, from_u, to_u, table):
    if from_u==to_u: return value,'单位一致'
    f=table.get('units',{}).get(from_u,{}).get(to_u)
    return (value*f,'换算 %s→%s'%(from_u,to_u)) if f is not None else (None,'不可换算')

def null_kind(raw, table):
    return table.get('nulls',{}).get(str(raw).strip())

def eval_in(raw, allowed, table, on_unmapped='UNVERIFIABLE'):
    """无损归一（同义/并列写法）→ PASS；含歧义的上位词 → 需补证，不得判通过。"""
    mapped,how=normalize_enum(raw,allowed,table)
    if mapped and '歧义' in how:
        return {'verdict':'PENDING_EVIDENCE','mapped':mapped,
                'basis':f'归一化：{how}——「{raw}」是上位词，不能确定具体类别',
                'suggest':f'请委托方补写具体类别（{" / ".join(mapped)} 之一）'}
    if mapped: return {'verdict':'PASS','mapped':mapped,'basis':f'归一化：{how}'}
    return {'verdict':on_unmapped,'mapped':None,'basis':f'归一化失败：{how}',
            'suggest':f'补 {raw} 到 synonyms 或交人工判定'}

def _selftest():
    t=load(); ok=0; bad=0
    cases=[('废水',['地表水','地下水','工业废水','生活污水'],'PENDING_EVIDENCE'),
           ('地表水',['地表水','地下水','工业废水','生活污水'],'PASS'),
           ('中水',['地表水','地下水','工业废水','生活污水'],'UNVERIFIABLE'),
           ('地下水/地表水',['地表水','地下水'],'PASS')]
    for raw,allow,want in cases:
        r=eval_in(raw,allow,t)
        good=r['verdict']==want; ok+=good; bad+=not good
        print(f"  {'✓' if good else '✗'} {raw!r:14s} → {r['verdict']:14s} {r['basis']}")
    v,how=convert_unit(0.5,'mg/L','μg/L',t); print(f"  单位 0.5 mg/L → {v} μg/L（{how}）")
    print(f"  ND 语义: {null_kind('ND',t)}")
    print(f"\n自测 {ok} 通过 / {bad} 失败")
    return 0 if not bad else 1

if __name__=='__main__':
    sys.exit(_selftest() if '--selftest' in sys.argv else 0)
