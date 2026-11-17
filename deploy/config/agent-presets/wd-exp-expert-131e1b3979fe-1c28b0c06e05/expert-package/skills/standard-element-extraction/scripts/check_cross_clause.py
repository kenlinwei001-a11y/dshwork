#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核查「谓词阈值是否真在本条条款里」：不在就找它出自哪一条。

用法: python3 check_cross_clause.py --out <run> --text <标准md> [--write]
输出: machine/cross_clause_check.json
  {checked, in_clause, suspect:[{rule_id, clause, value, found_in:[候选条款], quote}]}
判法（确定性）：
  取该规则 anchor.clause 的整段正文；阈值字符串不在其中 → 疑似跨条款
  再全文搜该阈值，回看最近的条款号 → 候选来源
"""
import argparse,json,os,re,sys

def sections(md):
    """切成 {clause: text}：以行首 N / N.N / N.N.N 开头为界。"""
    out={}; cur=None; buf=[]
    for line in md.splitlines():
        if '....' in line or '……' in line:      # 跳过目次行
            continue
        m=re.match(r'^\s*(\d+(?:\.\d+){0,2})\s+\S', line)
        if m:
            if cur: out[cur]=' '.join(buf)
            cur=m.group(1); buf=[line.strip()]
        elif cur:
            buf.append(line.strip())
    if cur: out[cur]=' '.join(buf)
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True)
    ap.add_argument('--text',required=True); ap.add_argument('--rules',default='03-rules.json')
    ap.add_argument('--write',action='store_true'); ap.add_argument('--node',default='')
    a=ap.parse_args(); O=a.out
    md=open(a.text,encoding='utf-8').read()
    sec=sections(md)
    rules=json.load(open(os.path.join(O,a.rules),encoding='utf-8')).get('audit_rule_cards') or []
    checked=0; inc=0; suspect=[]
    for r in rules:
        p=r.get('predicate') or {}
        if not p: continue
        if p.get('op')=='in' and isinstance(p.get('value'),list):
            continue      # 适用域/清单类：值本就分散，不做跨条款判定
        checked+=1
        val=p.get('value')
        def _leaves(x):
            if isinstance(x,dict):
                out=[]
                for v in x.values(): out+=_leaves(v)
                return out
            if isinstance(x,list):
                out=[]
                for v in x: out+=_leaves(v)
                return out
            return [str(x)]
        vals=[v for v in _leaves(val) if re.fullmatch(r'\d+(?:\.\d+)?', v)] or [str(val)]
        cl=str(r.get('clause'))
        body=sec.get(cl,'')
        if not body:                      # 本条没抓到正文，跳过不误报
            continue
        def _norm(t):
            return re.sub(r'(?<=\d)\s+(?=\d)','',t)      # "1 000" → "1000"
        def _hit(v,b):
            b=_norm(b)
            if re.search(r'(?<![\d.])'+re.escape(v)+r'(?![\d])', b): return True
            try:                                          # 数值等价：0.03 == 0.030
                f=float(v)
                return re.search(r'(?<![\d.])'+re.escape(('%.3f'%f).rstrip('0').rstrip('.'))+r'(?![\d])', b) is not None \
                    or re.search(r'(?<![\d.])'+re.escape('%.3f'%f)+r'(?![\d])', b) is not None
            except Exception:
                return False
        if any(_hit(v,body) for v in vals):
            inc+=1; continue
        cand=[]
        for v in vals:
            for m in re.finditer(r'(?<![\d.])'+re.escape(v)+r'(?![\d])', md):
                head=md[:m.start()]
                ms=list(re.finditer(r'(?m)^\s*(\d+(?:\.\d+){0,2})\s+\S', head))
                if '....' in md[m.start()-80:m.start()+40]: continue
                if ms and ms[-1].group(1)!=cl: cand.append(ms[-1].group(1))
        suspect.append({'rule_id':r['rule_id'],'clause':cl,'value':val,'found_in':sorted(set(cand))[:4],
                        'quote':((r.get('anchor') or {}).get('quote') or '')[:80]})
    doc={'text':os.path.basename(a.text),'rules':len(rules),'checked':checked,
         'in_clause':inc,'suspect':suspect,'suspect_count':len(suspect)}
    os.makedirs(os.path.join(O,'machine'),exist_ok=True)
    if a.write or True:
        json.dump(doc,open(os.path.join(O,'machine','cross_clause_check.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    if a.node:
        import datetime
        open(os.path.join(O,'trail.jsonl'),'a',encoding='utf-8').write(json.dumps(
          {'step':'script','node':a.node,'exit':0,'note':'cross_clause_check','at':datetime.datetime.now().isoformat(timespec='seconds')},ensure_ascii=False)+'\n')
    print(json.dumps({'standard':os.path.basename(a.text),'checked':checked,'in_clause':inc,
                      'suspect':len(suspect),'detail':suspect[:5]},ensure_ascii=False))
    return 0
if __name__=='__main__': sys.exit(main())
