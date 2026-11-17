#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""节点门禁：按节点契约校验产物，exit 0 才算该节点完成。
用法: python3 validate_node.py --node rules --out <out目录> [--text <正文>]
"""
import argparse, json, os, re, sys

def norm(s): return re.sub(r'\s+', '', s or '')
def load(p):
    with open(p, encoding='utf-8') as f: return json.load(f)

def text_for(out, explicit, c=None):
    """正文来源必须锚定 out；找不到就返回空并让调用方报错，绝不跨目录取。"""
    if explicit: return open(explicit, encoding='utf-8').read()
    c = c or load(os.path.join(out, '01-clauses.json'))
    slug = c.get('standard_slug') or ''
    d = os.path.join(out, 'standards')
    cands = [os.path.join(d, slug + '.txt'), os.path.join(d, slug + '.TXT')] if slug else []
    # 兜底：standards/ 下只有一个 txt 时用它（历史 run 的 slug 与文件名可能不一致）
    if os.path.isdir(d):
        only = sorted(f for f in os.listdir(d) if f.lower().endswith('.txt'))
        if len(only) == 1: cands.append(os.path.join(d, only[0]))
    for p in cands:
        if os.path.exists(p):
            print(f'  text = {os.path.relpath(p, out)}')
            return open(p, encoding='utf-8').read()
    print(f'  text = 缺失（out/standards/{slug or "<slug>"}.txt 不存在；不得回退到工作目录）')
    return ''


def rec(fails, ok, msg):
    if ok:
        print(f'  OK   {msg}')
    else:
        print(f'  FAIL {msg}')
        fails.append(msg)

def gate_clauses(out, text):
    f = []; c = load(os.path.join(out, '01-clauses.json'))
    rec(f, bool(c.get('standard_id')), 'standard_id 存在')
    rec(f, bool(c.get('standard_slug')), 'standard_slug 存在')
    rec(f, isinstance(c.get('standard_type'), (dict, str)) and bool(c.get('standard_type')), 'standard_type 存在')
    cr = c.get('clause_registry') or []
    rec(f, len(cr) > 0, f'条款数 {len(cr)} > 0')
    ids = [x.get('clause') for x in cr]
    rec(f, len(ids) == len(set(ids)), '条款号唯一')
    t = norm(text)
    miss = [x.get('clause') for x in cr if norm(x.get('quote') or (x.get('anchor') or {}).get('quote')) not in t]
    rec(f, not miss, f'quote 全部命中原文（miss={miss[:5]}）')
    rec(f, all(x.get('modality') in ('MUST','SHOULD','MAY','MUST_NOT','INFO') for x in cr), '模态枚举合法')
    for r in c.get('reference_register') or []:
        rec(f, bool(r.get('status')), f"引用 {r.get('ref_id')} 有 status")
    pend = [r['ref_id'] for r in (c.get('reference_register') or []) if r.get('status') == 'PENDING_UPLOAD']
    gap_ids = ' '.join(g.get('gap_id','') for g in c.get('gaps') or [])
    rec(f, all(p in gap_ids for p in pend), 'PENDING_UPLOAD 均落 GAP-REF')
    rec(f, all(g.get('request') for g in c.get('gaps') or []), '每条缺口有最小补充请求')
    return f

def gate_elements(out, text):
    f = []; e = load(os.path.join(out, '02-elements.json'))
    els = e.get('elements') or []
    rec(f, len(els) > 0, f'要素数 {len(els)} > 0')
    t = norm(text)
    miss = [x.get('element_id') for x in els if norm((x.get('anchor') or {}).get('quote')) not in t]
    rec(f, not miss, f'要素 quote 全部命中（miss={miss[:5]}）')
    rec(f, all((x.get('anchor') or {}).get('clause') for x in els), '每个要素有 clause')
    bad = [x.get('element_id') for x in els for p in (x.get('parameters') or [])
           if p.get('value') is not None and not p.get('unit')]
    rec(f, not bad, f'数值参数均带 unit（bad={bad[:5]}）')
    fams = {x.get('family') for x in els}
    rec(f, len(fams) >= 10, f'覆盖族数 {len(fams)} ≥ 10')
    fcs = e.get('formula_cards') or []
    rec(f, all((x.get('self_check') or {}).get('pass') for x in fcs), f'公式卡自检通过 {len(fcs)} 张')
    ids = [x.get('element_id') for x in els]
    rec(f, len(ids) == len(set(ids)), 'element_id 唯一')
    parts = os.path.join(out, 'parts')
    rec(f, not (os.path.isdir(parts) and os.listdir(parts)), '分片已清理（parts/ 空或不存在）')
    asm = e.get('assemble') or {}
    rec(f, not (asm.get('errors') or []), f"组装错误 0（errors={len(asm.get('errors') or [])}）")
    dang = [x.get('element_id') for x in els for p2 in (x.get('parameters') or []) if p2.get('status') == 'DANGLING']
    rec(f, not dang, f'无 DANGLING 引用（{dang[:3]}）')
    nref = sum(1 for x in els for p2 in (x.get('parameters') or []) if p2.get('value_ref'))
    npar = sum(len(x.get('parameters') or []) for x in els)
    print(f'  INFO value_ref {nref}/{npar}')
    return f

def gate_rules(out, text):
    f = []; r = load(os.path.join(out, '03-rules.json'))
    cards = r.get('audit_rule_cards') or []
    rec(f, len(cards) > 0, f'规则数 {len(cards)} > 0')
    ids = [x.get('rule_id') for x in cards]
    rec(f, len(ids) == len(set(ids)), 'rule_id 唯一')
    bad = [x.get('rule_id') for x in cards if not (x.get('clause') and x.get('anchor',{}).get('quote')
           and x.get('check_targets') and x.get('on_missing'))]
    rec(f, not bad, f'lint 必检字段齐（bad={bad[:5]}）')
    rec(f, all(x.get('on_missing') in ('FAIL','UNVERIFIABLE') for x in cards), 'on_missing 枚举合法')
    t = norm(text)
    miss = [x.get('rule_id') for x in cards if norm((x.get('anchor') or {}).get('quote')) not in t]
    rec(f, not miss, f'规则 quote 全部命中（miss={miss[:5]}）')
    # 定性卡不得带 predicate
    bad = [x.get('rule_id') for x in cards if x.get('qualitative_check') and x.get('predicate')]
    rec(f, not bad, f'定性卡无 predicate（bad={bad[:5]}）')
    # 谓词数值落点
    bad = []
    for x in cards:
        p = x.get('predicate') or {}
        v = p.get('value')
        # 只核数值型阈值；文本型谓词（==）不要求出现在正文
        if isinstance(v, bool) or v is None or isinstance(v,(list,dict)): continue
        if not (isinstance(v,(int,float)) or (isinstance(v,str) and re.fullmatch(r'-?\d+(?:\.\d+)?', v))):
            continue
        if str(v) not in t: bad.append(x.get('rule_id'))
    rec(f, not bad, f'谓词数值可回原文（bad={bad[:5]}）')
    c = load(os.path.join(out, '01-clauses.json'))
    cm = r.get('coverage_matrix') or []
    rec(f, len(cm) == len(c.get('clause_registry') or []), f'覆盖矩阵 {len(cm)} 行 = 条款数')
    parts = os.path.join(out, 'parts')
    rec(f, not (os.path.isdir(parts) and os.listdir(parts)), '分片已清理（parts/ 空或不存在）')
    return f

def gate_audit(out, text):
    f = []
    md = os.path.join(out, '04-audit.md')
    rec(f, os.path.exists(md), '04-audit.md 存在')
    body = open(md, encoding='utf-8').read() if os.path.exists(md) else ''
    rec(f, '## 判定' in body, '含「## 判定」节')
    ar = os.path.join(out, 'audit_result.json')
    rec(f, os.path.exists(ar), 'audit_result.json 存在')
    if os.path.exists(ar):
        v = load(ar).get('verdict')
        rec(f, v in ('pass','fail'), f'verdict 合法（{v}）')
    return f

def gate_fix(out, text):
    f = []
    for name in ('02-elements.json','03-rules.json'):
        d = load(os.path.join(out, name))
        rec(f, bool(d.get('revision_log')), f'{name} 有 revision_log')
    return f

def gate_handoff(out, text):
    f = []
    # 说明里的数字必须来自 derived（唯一派生源）
    dv = os.path.join(out, 'derived.json')
    md0 = os.path.join(out, '05-handoff.md')
    if os.path.exists(dv) and os.path.exists(md0):
        import re as _re
        D = load(dv); body = open(md0, encoding='utf-8').read()
        user = (D.get('pending_class') or {}).get('PENDING_USER', 0)
        m = _re.search(r'待裁\s*(\d+)', body)
        if m:
            rec(f, int(m.group(1)) == user, f'derived_consistency：待裁 {m.group(1)} vs 派生 {user}')
        for k in ('clauses', 'elements', 'rules'):
            v = (D.get('counts') or {}).get(k)
            if v is not None:
                rec(f, str(v) in body, f'derived_consistency：{k}={v} 出现在说明中')
    for name in ('05-handoff.md','dashboard.html','ses.json'):
        rec(f, os.path.exists(os.path.join(out, name)), f'{name} 存在')
    if os.path.exists(os.path.join(out, 'ses.json')):
        s = load(os.path.join(out, 'ses.json'))
        rec(f, (s.get('audit_result') or {}).get('verdict') == 'pass', 'ses 内 audit_result=pass')
        for k in ('clause_registry','elements','audit_rule_cards','gaps'):
            rec(f, isinstance(s.get(k), list) and len(s[k]) > 0, f'ses.{k} 非空')
        rec(f, bool(s.get('rule_set_id')), 'rule_set_id 存在')
    md = os.path.join(out, '05-handoff.md')
    if os.path.exists(md):
        body = open(md, encoding='utf-8').read()
        secs = sum(1 for i in range(1,8) if f'## {i}' in body)
        rec(f, secs >= 7, f'handoff 七节齐（{secs}/7）')
    graph_link_check(out, f)
    return f

def gate_toolchain(out, text):
    f = []
    p = os.path.join(out, 'audit_metrics.json')
    rec(f, os.path.exists(p), 'audit_metrics.json 存在')
    if os.path.exists(p):
        m = load(p); rec(f, m.get('gate') == 'PASS', f"gate={m.get('gate')}")
    need = ['metrics']
    if os.path.exists(os.path.join(out, '00-provenance.json')): need.append('provenance')
    if os.path.exists(os.path.join(out, 'ses.json')): need.append('package')
    for n in need:
        rec(f, os.path.exists(os.path.join(out, f'runner-{n}.json')), f'runner-{n}.json 存在')
    return f

def trail_ok(out, node):
    import json as _j
    p=os.path.join(out,'trail.jsonl')
    if not os.path.exists(p): return False, '未发现 trail.jsonl（视为未执行）'
    last=None
    for line in open(p,encoding='utf-8'):
        if not line.strip(): continue
        r=_j.loads(line)
        if r.get('step')=='verify' and r.get('node')==node: last=r
    # 只认最后一次 verify：旧的成功记录不能掩盖新的失败
    if last is None: return False, f'缺少 verify 记录（--util verify --node {node}）'
    if not last.get('pass'):
        return False, f'最后一次 verify 未通过：{last.get("missing")}'
    return True, ''

def trail_attested(out, node):
    p=os.path.join(out,'trail.jsonl')
    if not os.path.exists(p): return 0
    for line in reversed(open(p,encoding='utf-8').read().splitlines()):
        if not line.strip(): continue
        r=json.loads(line)
        if r.get('step')=='verify' and r.get('node')==node: return int(r.get('attested') or 0)
    return 0


def _graph_rules(out):
    """全部规则 rule_id（来自槽位任务或 ses）与图上已挂节点的 rule_id。"""
    rules = set()
    p = os.path.join(out, 'audit_tasks.jsonl')
    if os.path.exists(p):
        for line in open(p, encoding='utf-8'):
            if line.strip():
                rules.add(json.loads(line).get('rule_id'))
    if not rules and os.path.exists(os.path.join(out, 'ses.json')):
        for k in (load(os.path.join(out, 'ses.json')).get('audit_rule_cards') or []):
            rules.add(k.get('rule_id'))
    rules.discard(None)
    mapped = set()
    g = os.path.join(out, 'sop-graph.json')
    if os.path.exists(g):
        for n in (load(g).get('nodes') or []):
            mapped.update(n.get('criteria') or [])
            mapped.update(n.get('qualitative') or [])
    return rules, mapped

def graph_link_check(out, f):
    """每条规则都要在 SOP 图上有落点；没有落点必须登记进 machine/graph_gaps.json。"""
    rules, mapped = _graph_rules(out)
    if not rules:
        print('  OK   图挂载：规则尚未生成，本节点跳过'); return
    if not mapped:
        rec(f, False, '图挂载：sop-graph.json 无 criteria/qualitative，规则全部无落点'); return
    um = sorted(rules - mapped)
    if not um:
        rec(f, True, f'图挂载：{len(rules)}/{len(rules)} 规则有节点落点'); return
    gp = os.path.join(out, 'machine', 'graph_gaps.json')
    reg = set()
    if os.path.exists(gp):
        reg = {x.get('rule_id') for x in (load(gp).get('items') or [])}
    missing = [r for r in um if r not in reg]
    rec(f, not missing,
        f'图挂载：{len(rules)-len(um)}/{len(rules)} 有落点，{len(um)} 未挂'
        f'（已登记 {len(um)-len(missing)}，未登记 {len(missing)}:{missing[:4]}）')

def gate_sop(out, text):
    f=[]; p=os.path.join(out,'sop-graph.json')
    rec(f, os.path.exists(p), 'sop-graph.json 存在')
    if os.path.exists(p):
        d=load(p); n=d.get('invariant_error_count',999)
        rec(f, n==0, f'图谱不变量错误 {n}')
        for e in (d.get('invariant_errors') or [])[:5]: print('   -',e)
    graph_link_check(out, f)
    return f

GATES = {'sop':gate_sop,'clauses':gate_clauses,'elements':gate_elements,'rules':gate_rules,
         'audit':gate_audit,'fix':gate_fix,'handoff':gate_handoff,'toolchain':gate_toolchain}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--node', required=True, choices=list(GATES))
    ap.add_argument('--out', required=True); ap.add_argument('--text')
    a = ap.parse_args()
    try: text = text_for(a.out, a.text)
    except Exception: text = ''
    print(f'== gate {a.node}')
    fails = GATES[a.node](a.out, text)
    if os.environ.get('SKIP_TRAIL_CHECK') == '1':
        print('  SKIP trail_present（attest 内容预检，不判留痕）')
    else:
        ok,msg = trail_ok(a.out, a.node)
        rec(fails, ok, 'trail_present：'+('有 verify 记录' if ok else msg))
        att = trail_attested(a.out, a.node)
        if ok and att:
            print(f'  NOTE 留痕含补录 {att} 条（basis=artifact_exists，非本次执行）')
    print(('GATE: PASS' if not fails else 'GATE: FAIL'))
    for x in fails: print('  -', x)
    return 0 if not fails else 1

if __name__ == '__main__':
    sys.exit(main())
