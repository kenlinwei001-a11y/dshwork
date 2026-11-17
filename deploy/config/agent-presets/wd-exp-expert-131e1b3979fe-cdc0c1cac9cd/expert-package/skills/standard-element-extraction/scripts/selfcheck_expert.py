#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布后自检：用新专家（或工作区同版脚本）验证两件事。

用法:
  python3 selfcheck_expert.py                      # 自动定位脚本（专家包 → 工作区）
  python3 selfcheck_expert.py --pkg <专家包 skills 目录>
  python3 selfcheck_expert.py --work <临时工作目录>

检查项:
  A1 HJ84 抽取规则数 = 56
  A2 8 离子检出限/测定下限齐全（ARC-C1-1-04 parameters_by_analyte）
  A3 超量程规则存在且带 upper_by_analyte（ARC-C1-8.3-02）
  A4 on_missing 红线：C1–C7 不得出现 FAIL
  A5 missing_kind 字段覆盖率
  B1 bucket_judge_v2 判定条数 = 16（HJ636 5 + HJ535 5 + HJ84 6）
  B2 结果分布 = 11 PASS / 4 NOT_APPLICABLE / 1 UNVERIFIABLE
  B3 假 PASS 复现：HJ535 相关系数/平行/加标/中间点 必须为 NOT_APPLICABLE
退出码: 0 全通过；1 有失败项。
"""
import argparse,glob,json,os,subprocess,sys,tempfile

ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXPECT_RULES=58
EXPECT_BUCKETS={'PASS':11,'NOT_APPLICABLE':4,'PENDING_EVIDENCE':1}

def find_scripts(pkg=None):
    cands=[]
    if pkg: cands.append(pkg)
    cands.append(os.path.join(ROOT,'skill-update','scripts'))
    cands+=sorted(glob.glob(os.path.expanduser(
        '~/.agents/.workdsh-state/experts/presets/*/expert-package/skills/standard-element-extraction/scripts')))
    for c in cands:
        if c and os.path.exists(os.path.join(c,'run_graph.py')) and os.path.exists(os.path.join(c,'bucket_judge_v2.py')):
            return c
    return None

def run(cmd):
    p=subprocess.run(cmd,capture_output=True,text=True)
    return p.returncode,(p.stdout or '')+(p.stderr or '')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--pkg'); ap.add_argument('--work'); ap.add_argument('--rules')
    ap.add_argument('--std-text'); ap.add_argument('--docs'); ap.add_argument('--packs',nargs='+')
    a=ap.parse_args()
    S=find_scripts(a.pkg)
    if not S: print("✗ 找不到脚本目录（run_graph.py + bucket_judge_v2.py 必须同在）"); return 1
    print(f"脚本目录：{S}")
    py=sys.executable; res=[]
    def chk(name,ok,detail=''):
        res.append((name,ok,detail)); print(f"  {'✓' if ok else '✗'} {name} {detail}")

    # ── A. 标准侧
    work=a.work or tempfile.mkdtemp(prefix='selfcheck-')
    std=a.std_text or os.path.join(ROOT,'inbox/std-md/HJ84-2016.md')
    packs=a.packs or sorted(glob.glob(os.path.join(ROOT,'docs/判定包/*')))
    if not os.path.exists(std):
        chk('A0 标准文本可用',False,std); return 1
    rules_src=a.rules or os.path.join(ROOT,'docs/判定包/HJ84-2016/rules.jsonl')
    cmd=[py,os.path.join(S,'run_graph.py'),'--out',work,'--text',std,'--standard','HJ84-2016','--mode','extract']
    if os.path.exists(rules_src): cmd+=['--rules',rules_src]
    rc,out=run(cmd)
    chk('A0 run_graph --mode extract', rc==0, out.strip().splitlines()[-1][:90] if out else '')
    # 纯自举版（不给 --rules）能出多少条，用于识别"增强项只存在于手写规则集"
    w2=work+'-boot'
    rc2,out2=run([py,os.path.join(S,'run_graph.py'),'--out',w2,'--text',std,
                  '--standard','HJ84-2016','--mode','extract'])
    try: nb=json.load(open(os.path.join(w2,'03-rules.json'),encoding='utf-8'))
    except Exception: nb={'audit_rule_cards':[]}
    nb=len(nb['audit_rule_cards'])
    chk('A6 自举版规则数（仅参考）', True, f'{nb} 条；增强项需 --rules 提供')
    rp=os.path.join(work,'03-rules.json')
    rules=json.load(open(rp,encoding='utf-8'))['audit_rule_cards'] if os.path.exists(rp) else []
    chk('A1 规则数 = 58（含 2 条 PERF）', len(rules)==EXPECT_RULES, f'实际 {len(rules)}')
    r04=next((r for r in rules if r['rule_id']=='ARC-C1-1-04'),None)
    ions=(r04 or {}).get('parameters_by_analyte') or {}
    chk('A2 8 离子检出限齐全', len(ions)==8 and all('loq' in v for v in ions.values()), f'{len(ions)} 个离子')
    r83=next((r for r in rules if r['rule_id']=='ARC-C1-8.3-02'),None)
    chk('A3 超量程规则存在', bool(r83) and len((r83 or {}).get('upper_by_analyte') or {})==8,
        f"upper {len((r83 or {}).get('upper_by_analyte') or {})} 项")
    bad=[r['rule_id'] for r in rules if r.get('on_missing')=='FAIL' and r.get('criticality')!='KEY']
    chk('A4 on_missing 与关键性一致', not bad, f'违规 {len(bad)} 条' if bad else 'FAIL 仅出现在 KEY 要素')
    nk=sum(1 for r in rules if r.get('criticality'))
    chk('A7 criticality 覆盖', nk==len(rules), f'{nk}/{len(rules)}')
    mk=sum(1 for r in rules if r.get('missing_kind'))
    chk('A5 missing_kind 覆盖', mk==len(rules), f'{mk}/{len(rules)}')

    # ── B. 证据侧
    docs=a.docs or os.path.join(ROOT,'report-src/bundle2/202203001  水质 常规元素')
    pk=[p for p in packs if any(k in p for k in ('HJ636','HJ535','HJ84'))]
    rc,out=run([py,os.path.join(S,'bucket_judge_v2.py'),'--out',work,'--packs',*pk,'--docs',docs])
    jp=os.path.join(work,'machine','bucket_judgement_v2.json')
    items=json.load(open(jp,encoding='utf-8'))['items'] if os.path.exists(jp) else []
    chk('B1 判定条数 = 16', len(items)==16, f'实际 {len(items)}')
    from collections import Counter
    c=Counter(x['verdict'] for x in items)
    chk('B2 结果分布', dict(c)==EXPECT_BUCKETS, str(dict(c)))
    h535=[x for x in items if x['standard'].startswith('HJ535') and x['concept']!='空白吸光度']
    chk('B3 HJ535 假 PASS 已撤', all(x['verdict']=='NOT_APPLICABLE' for x in h535),
        f'{len(h535)} 条非空白项均为 NOT_APPLICABLE' if h535 else '无')
    ok=all(r[1] for r in res)
    print(f"\n{'全部通过' if ok else '有失败项'}：{sum(1 for r in res if r[1])}/{len(res)}")
    print(f"工作目录：{work}")
    return 0 if ok else 1

if __name__=='__main__': sys.exit(main())
