#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按图执行标准抽取全链——**不依赖 toolchain/run.py**，直接调用同目录脚本。

用法:
  python3 run_graph.py --out <run> --text <标准文本> --standard <编号> [--rules <手写规则>]
                       [--mode full|extract] [--max-rounds 3]

两种调用面：
  ① 包内自足：python3 scripts/run_graph.py ...            （专家包 / 工作区皆可）
  ② 工作区分发：python3 toolchain/run.py std.run_graph ...  （若已注册原子）

原子解析顺序：同目录 <name>.py → 上级 skill 目录 → PATH 上的 toolchain（仅兜底）
"""
import argparse,json,os,subprocess,sys,datetime

HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(os.path.dirname(HERE))

# 原子 → 同目录脚本文件名（不依赖 contracts/scripts.json）
ATOM={
 'route':('run_contract.py',['--util','route']),
 'clauses':('run_contract.py',['--util','clause_preclassify']),
 'merge':('run_contract.py',['--util','clause_merge']),
 'elements':('bootstrap_rules.py',[]),
 'graph':('run_contract.py',['--util','sop_graph']),
 'slots':('run_contract.py',['--util','build_slots']),
 'pack':('graph_pack.py',[]),
 'sop_graph':('run_contract.py',['--util','sop_graph']),
 'load_library':('run_contract.py',['--util','load_library']),
 'verify':('run_contract.py',['--util','verify']),
 'trail':('run_contract.py',['--util','trail']),
 'cross':('check_cross_clause.py',[]),
 'rows':('rows_split.py',[]),
 'backfill':('backfill_slices.py',[]),
 'merge_judged':('merge_judged.py',[]),
 'sample':('sample_findings.py',[]),
 'handoff_pack':('handoff_pack.py',[]),
 'render_handoff':('render_handoff.py',[]),
 'pack_split':('pack_split.py',[]),
}

def resolve(atom):
    fn,pre=ATOM[atom]
    for base in (HERE, os.path.join(HERE,'scripts')):
        p=os.path.join(base,fn)
        if os.path.exists(p): return p,pre
    p=os.path.join(ROOT,'toolchain','run.py')       # 兜底
    return p, []

def call(atom,*argv):
    path,pre=resolve(atom)
    if path.endswith('run.py'):
        cmd=[sys.executable,path,'std.'+atom]+list(argv)
    else:
        cmd=[sys.executable,path]+pre+list(argv)
    p=subprocess.run(cmd,capture_output=True,text=True,cwd=ROOT)
    return p.returncode,(p.stdout or '').strip(),(p.stderr or '')[-400:]

def trail(O,node,step,rc,note=''):
    os.makedirs(O,exist_ok=True)
    with open(os.path.join(O,'trail.jsonl'),'a',encoding='utf-8') as f:
        f.write(json.dumps({'step':step,'node':node,'exit':rc,'note':note,'auto':True,
                            'at':datetime.datetime.now().isoformat(timespec='seconds')},ensure_ascii=False)+'\n')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',required=True); ap.add_argument('--text',required=True)
    ap.add_argument('--standard',required=True); ap.add_argument('--rules',default=None)
    ap.add_argument('--mode',choices=['full','extract'],default='full')
    ap.add_argument('--max-rounds',type=int,default=3)
    a=ap.parse_args(); O=a.out
    os.makedirs(os.path.join(O,'standards'),exist_ok=True)
    tgt=os.path.join(O,'standards',os.path.basename(a.text))
    if not os.path.exists(tgt): open(tgt,'w',encoding='utf-8').write(open(a.text,encoding='utf-8').read())
    steps=[('route',['--out',O,'--text',tgt]),('clauses',['--out',O,'--text',tgt]),
           ('merge',['--out',O,'--standard',a.standard])]
    for name,argv in steps:
        rc,out,err=call(name,*argv); trail(O,'clauses','script',rc,name)
        print(f"[extract] {name:8s} {'ok' if rc==0 else 'FAIL'}")
        if rc: print((err or out)[-300:]); return 1
    # 要素/规则
    rc,out,err=call('elements','--out',O,'--text',tgt,'--standard',a.standard,'--write')
    trail(O,'elements','script',rc,'bootstrap')
    if rc:
        print((err or out)[-300:]); return 1
    if a.rules:                                   # bootstrap 之后覆盖为手写规则（支持 .json 与 .jsonl）
        raw=open(a.rules,encoding='utf-8').read().strip()
        try:
            card=json.loads(raw)
            if isinstance(card,list): card={'audit_rule_cards':card}
        except json.JSONDecodeError:              # JSONL：一行一条
            card={'audit_rule_cards':[json.loads(l) for l in raw.splitlines() if l.strip()]}
        card['standard_id']=card.get('standard_id') or a.standard
        json.dump(card,open(os.path.join(O,'03-rules.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
        trail(O,'rules','llm',0,'rules_override')
    print(f"[extract] rules    {'ok' if rc==0 else 'FAIL'}")
    if rc: print((err or out)[-300:]); return 1
    for name,argv in [('graph',['--out',O]),('slots',['--out',O]),('pack',['--out',O])]:
        rc,out,err=call(name,*argv); trail(O,'sop','script',rc,name)
        print(f"[extract] {name:8s} {'ok' if rc==0 else 'FAIL'}")
        if rc: print((err or out)[-300:]); return 1
    g=json.load(open(os.path.join(O,'sop-graph.json'),encoding='utf-8'))
    r=json.load(open(os.path.join(O,'03-rules.json'),encoding='utf-8'))['audit_rule_cards']
    print(json.dumps({'ok':True,'standard':a.standard,'rules':len(r),
                      'with_predicate':sum(1 for x in r if x.get('predicate')),
                      'nodes':len(g['nodes']),'edges':len(g['edges']),
                      'invariant_errors':g.get('invariant_error_count',0)},ensure_ascii=False))
    if a.mode=='extract': return 0
    # full：交叉核查 + 机器筛 + 回修循环 + 交付
    rc,out,_=call('cross','--out',O,'--text',tgt,'--node','clauses'); trail(O,'clauses','script',rc,'cross_clause')
    rc,out,_=call('sample','--out',O,'--n','5','--rules','--seed','42'); trail(O,'audit','llm',rc,'sample')
    def screen():
        rr=json.load(open(os.path.join(O,'03-rules.json'),encoding='utf-8'))['audit_rule_cards']
        n=len(rr) or 1
        bad=[x['rule_id'] for x in rr if not x.get('check_targets')]
        npq=[x['rule_id'] for x in rr if not x.get('predicate') and not x.get('qualitative_check')]
        ratio=sum(1 for x in rr if x.get('predicate'))/n
        fails=[]
        if bad: fails.append(f'B-01 {len(bad)} 条无 check_targets')
        if npq: fails.append(f'B-02 {len(npq)} 条既无谓词又非定性')
        if ratio<0.30: fails.append(f'B-03 谓词比例 {ratio:.0%} < 30%')
        return ('pass' if not fails else 'fail'),fails
    verdict,fails=screen(); trail(O,'audit','llm',0,f'screen:{verdict}')
    rnd=0
    while verdict=='fail' and rnd<a.max_rounds:
        rnd+=1
        rc,out,err=call('rows','--out',O,'--size','20')
        rc2,_,_=call('backfill','--out',O)
        rc3,_,_=call('merge_judged','--out',O)
        for nm,rcc in (('rows',rc),('backfill',rc2),('merge_judged',rc3)): trail(O,'fix','script',rcc,nm)
        call('graph','--out',O); call('slots','--out',O); call('pack','--out',O)
        verdict,fails=screen(); trail(O,'audit','llm',0,f'round{rnd}:{verdict}')
        print(f"[full] fix round {rnd} → {verdict}")
    rc,out,_=call('handoff_pack','--out',O); trail(O,'handoff','script',rc,'handoff_pack')
    rc,out,_=call('render_handoff','--out',O); trail(O,'handoff','script',rc,'render')
    print(json.dumps({'ok':True,'audit':verdict,'fails':fails,
                      'handoff':'05-handoff.md' if os.path.exists(os.path.join(O,'05-handoff.md')) else None},ensure_ascii=False))
    return 0

if __name__=='__main__': sys.exit(main())
