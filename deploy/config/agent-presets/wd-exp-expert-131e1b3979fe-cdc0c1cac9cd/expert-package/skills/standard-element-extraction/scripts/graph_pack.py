#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「判定所需」并入 SOP 图 YAML，使单个文件可交付判定。

用法:
  python3 graph_pack.py --out <run> [--yaml machine/sop-graph.yaml] [--write-yaml]

合并内容（都来自同一次抽取，避免版本错位）：
  03-rules.json     → rules[]（predicate{op,value,unit} / on_missing / category / clause）
  audit_tasks.jsonl → rules[] 内追加 target{slot, doc_type, match_hints}
  ses.json          → method_family / gaps / standard_id / fingerprint
  01-clauses.json   → clauses{clause: {page, quote}}（截断 120 字）
  图本身            → nodes / edges（含 invalidates / records 等判定用边）

输出：<out>/machine/sop-graph.packed.yaml
"""
import argparse,json,os,sys
import yaml

def load(p,d=None):
    return json.load(open(p,encoding='utf-8')) if os.path.exists(p) else d

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',required=True)
    ap.add_argument('--rules',default='03-rules.json')
    ap.add_argument('--tasks',default='audit_tasks.jsonl')
    ap.add_argument('--ses',default='ses.json')
    ap.add_argument('--clauses',default='01-clauses.json')
    ap.add_argument('--graph',default='sop-graph.json')
    a=ap.parse_args(); O=a.out
    g=load(os.path.join(O,a.graph))
    if not g: print(json.dumps({'error':'sop-graph.json 缺失'})); return 2
    rules={r['rule_id']:r for r in (load(os.path.join(O,a.rules),{}).get('audit_rule_cards') or [])}
    tasks={}
    tp=os.path.join(O,a.tasks)
    if os.path.exists(tp):
        for line in open(tp,encoding='utf-8'):
            if line.strip():
                t=json.loads(line); tasks.setdefault(t.get('rule_id'),t)
    ses=load(os.path.join(O,a.ses),{}) or {}
    cl=load(os.path.join(O,a.clauses),{}) or {}

    doc_std=ses.get('standard_id') or g.get('standard')
    out_rules=[]
    for rid,r in rules.items():
        t=tasks.get(rid) or {}
        p=r.get('predicate') or {}
        item={'rule_id':rid,'category':r.get('category'),'clause':r.get('clause'),
              'covers_clauses':r.get('covers_clauses') or ([r.get('clause')] if r.get('clause') else []),
              'anchor_notes':r.get('anchor_notes'),
              'judge_ceiling':r.get('judge_ceiling'),
              'requirement':(r.get('requirement') or '')[:160],
              'predicate':{'op':p.get('op'),'value':p.get('value'),'unit':p.get('unit')} if p else None,
              'on_missing':r.get('on_missing'),
              'target':{'slot':t.get('slot'),'doc_type':t.get('doc_type'),
                        'match_hints':t.get('match_hints') or []},
              'qualitative':not bool(p)}
        out_rules.append(item)
    out_rules.sort(key=lambda x:(str(x['category']),str(x['clause'])))

    clauses={}
    for c in (cl.get('clause_registry') or []):
        q=str(c.get('quote') or '')
        clauses[str(c.get('clause'))]={'page':c.get('page'),'quote':q[:120]+('…' if len(q)>120 else '')}

    refreg=cl.get('reference_register') or []
    mf=ses.get('method_family') or []
    if not mf:
        mf=[{'standard':doc_std or ses.get('standard_id'),'rule_set_id':'RS-'+str(ses.get('standard_slug') or ''),'status':'PROVIDED'}]
        for x in refreg:
            mf.append({'standard':x.get('standard_no'),'rule_set_id':None,
                       'status':x.get('status') or 'PENDING_UPLOAD','scope':x.get('scope')})
    doc={'standard_id':ses.get('standard_id') or g.get('standard'),
         'coverage_thresholds':{'blank_min':2,'parallel_ratio':0.1,'spike_min':1,'batch_max':20,
                                'note':'HJ 84 11.1/11.4/11.5；每批 ≤20 个样品'},
         'counts':g.get('counts'),'rule_nodes':g.get('rule_nodes'),
         'reference_register':refreg,
         'judging_contract':{'script_judged':'predicate 非空 → 由 eval_slots 比较，不由模型判',
                             'agent_judged':'qualitative=true → 只能判 符合/不符合/缺证（NO_PASS）',
                             'verdicts':['PASS','FAIL','UNVERIFIABLE','NOT_APPLICABLE','CONFLICT_PENDING'],
                             'on_missing_default':'UNVERIFIABLE；仅 C8 允许 FAIL',
                             'quote_required':'PASS/FAIL 必须带 page+quote；命中不了标 unlocated',
                             'no_downgrade':'FAIL 不得改 PASS；PASS 无依据降 UNVERIFIABLE'},
         'rules':out_rules,
         'clauses':clauses,
         'nodes':g.get('nodes'),'edges':g.get('edges'),
         'gaps':ses.get('gaps') or []}
    doc['method_family']=mf
    doc['source_fingerprint']=ses.get('source_fingerprint') or {}
    text=yaml.safe_dump(doc,allow_unicode=True,sort_keys=False,width=110,default_flow_style=False)
    head=(f"# {doc['standard_id']} 判定包（由图 + 规则 + 任务 + ses 合并；勿手改）\n"
          f"# 规则 {len(out_rules)} 条 / 节点 {len(doc['nodes'])} / 边 {len(doc['edges'])} / 条款 {len(clauses)}\n"
          f"# 重生成：python3 toolchain/run.py std.pack_graph --out <运行目录>\n")
    dst=os.path.join(O,'machine','sop-graph.packed.yaml')
    os.makedirs(os.path.dirname(dst),exist_ok=True)
    open(dst,'w',encoding='utf-8').write(head+text)
    print(json.dumps({'written':'machine/sop-graph.packed.yaml','rules':len(out_rules),
                      'with_predicate':sum(1 for r in out_rules if r['predicate']),
                      'with_slot':sum(1 for r in out_rules if r['target']['slot']),
                      'clauses':len(clauses),'nodes':len(doc['nodes']),'edges':len(doc['edges']),
                      'bytes':len((head+text).encode())},ensure_ascii=False))
    return 0
if __name__=='__main__': sys.exit(main())
