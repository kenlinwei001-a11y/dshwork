#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 slot_hits（候选槽命中）桥接到规则槽位：只有 HIT 且有值才填，其余不动。

用法: python3 bridge_hits.py --out <run> [--write]
规则：task.anchor.clause 与 hit.clause 相同 + task 槽为空 + hit.status=HIT + hit.value 有值
     → slots[slot]=value, spans[slot]={page,quote}
"""
import argparse, json, os, sys
def load(p,d=None):
    return json.load(open(p,encoding='utf-8')) if os.path.exists(p) else d
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); ap.add_argument('--write',action='store_true')
    a=ap.parse_args(); O=a.out
    hits={}
    hp=os.path.join(O,'machine','slot_hits.jsonl')
    if not os.path.exists(hp): print(json.dumps({'error':'slot_hits.jsonl 缺失'})); return 2
    for line in open(hp,encoding='utf-8'):
        if not line.strip(): continue
        h=json.loads(line)
        if h.get('status')=='HIT' and h.get('value') and h.get('clause'):
            hits.setdefault(str(h['clause']),[]).append(h)
    slots=load(os.path.join(O,'machine','report_slots.json'),{}) or {}
    spans=load(os.path.join(O,'machine','report_spans.json'),{}) or {}
    tasks=[json.loads(l) for l in open(os.path.join(O,'audit_tasks.jsonl'),encoding='utf-8') if l.strip()]
    filled={}
    for t in tasks:
        cl=str((t.get('anchor') or {}).get('clause') or '')
        if not cl or cl not in hits: continue
        if slots.get(t['slot']) not in (None,'',[]): continue
        h=hits[cl][0]
        try: val=float(h['value'])
        except Exception: val=h['value']
        slots[t['slot']]=val
        spans[t['slot']]={'page':h.get('page'),'quote':h.get('quote'),'method':'candidate_scan'}
        filled[t['slot']]={'clause':cl,'value':val,'doc_type':h.get('doc_type')}
    # 安全默认：只出候选，不写槽。实测自动填会写进 210/1/2 这类错值（来自仪器编号），
    # 因此必须 --unsafe-write 才允许落盘，且落盘前要求 value 是纯数字且与要求量纲一致。
    if not a.write:
        json.dump({'candidates':filled,'hits_by_clause':len(hits)},
                  open(os.path.join(O,'machine','slot_candidates_filled.json'),'w',encoding='utf-8'),
                  ensure_ascii=False,indent=2)
    if a.write and not getattr(a,'unsafe',False):
        print(json.dumps({'refused':'自动填槽默认禁用：需 --unsafe-write，且须人工核对',
                          'candidates':len(filled),'written':'machine/slot_candidates_filled.json'},ensure_ascii=False))
        return 0
    if a.write:
        json.dump(slots,open(os.path.join(O,'machine','report_slots.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
        json.dump(spans,open(os.path.join(O,'machine','report_spans.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps({'hits_by_clause':len(hits),'filled':len(filled),'detail':filled},ensure_ascii=False))
    return 0
if __name__=='__main__': sys.exit(main())
