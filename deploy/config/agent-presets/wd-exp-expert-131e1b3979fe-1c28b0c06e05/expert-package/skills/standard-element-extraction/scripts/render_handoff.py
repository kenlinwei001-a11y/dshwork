#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交接件渲染：数字只有脚本能写，模型只写带占位符的结论段。

用法: python3 render_handoff.py --out <run> [--model machine/handoff.model.md]

规则：
  1. 数字来自 machine/handoff_state.json（脚本统计），模板里写 {{rule_count}} 这类占位符
  2. 模型段落里**不许出现裸数字**（除 ①②③ 序号与日期）；出现即判违规并拒绝渲染
  3. 占位符解析不到 → 报错，不静默留空
输出：05-handoff.md；退出码 0=合规，3=模型段违规
"""
import argparse,json,os,re,sys

PH=re.compile(r'\{\{\s*([a-zA-Z_][\w]*)\s*\}\}')
ORD=re.compile(r'[①②③④⑤⑥⑦⑧⑨⑩]')
BARE=re.compile(r'(?<![\d{])\d+(?![\d}])')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',required=True); ap.add_argument('--model',default='machine/handoff.model.md')
    a=ap.parse_args(); O=a.out
    sp=os.path.join(O,'machine','handoff_state.json')
    if not os.path.exists(sp):
        print(json.dumps({'error':'缺 machine/handoff_state.json（先跑 std.run_contract --util handoff_state）'}))
        return 2
    state=json.load(open(sp,encoding='utf-8'))
    mp=os.path.join(O,a.model)
    if not os.path.exists(mp):
        print(json.dumps({'error':f'缺 {a.model}（模型结论段，可用占位符）'})); return 2
    model=open(mp,encoding='utf-8').read()

    # 校验：模型段里裸数字（去掉占位符后仍存在的数字）
    stripped=PH.sub('', model)
    bare=[m.group(0) for m in BARE.finditer(ORD.sub('', stripped))]
    if bare:
        print(json.dumps({'status':'VIOLATION','reason':'模型段落出现裸数字，必须改用 {{占位符}}',
                          'bare':bare[:8]},ensure_ascii=False))
        return 3

    missing=[k for k in PH.findall(model) if k not in state]
    if missing:
        print(json.dumps({'status':'ERROR','reason':'占位符在 handoff_state 里不存在','missing':missing},ensure_ascii=False))
        return 2

    body=PH.sub(lambda m: str(state[m.group(1)]), model)
    head=f"# 交接件\n\n> 数字由脚本从 handoff_state.json 渲染；结论段由模型撰写（不含裸数字）。\n\n"
    open(os.path.join(O,'05-handoff.md'),'w',encoding='utf-8').write(head+body+'\n')
    print(json.dumps({'status':'OK','written':'05-handoff.md','placeholders':list(dict.fromkeys(PH.findall(model)))},ensure_ascii=False))
    return 0
if __name__=='__main__': sys.exit(main())
