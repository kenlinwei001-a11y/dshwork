#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A 阶段编排器（只跑 tool 段）：provenance -> metrics -> package。
LLM 节点（clauses/elements/rules/audit/fix/handoff）仍由 agent 执行。
用法:
  python3 run_all.py --out DIR --stages provenance --pdf x.pdf
  python3 run_all.py --out DIR --stages metrics,package
"""
import argparse, json, subprocess, sys, os

def run(cap, cfg, out, node):
    rec = os.path.join(out, f'runner-{node}.json')
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'runner.py'), 'run', cap]
    for k, v in cfg.items(): cmd += ['--config', f'{k}={v}']
    cmd += ['--out', rec]
    p = subprocess.run(cmd, capture_output=True, text=True)
    print(p.stdout.strip().splitlines()[0] if p.stdout.strip() else f'{cap} (no output)')
    return p.returncode

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--stages', default='provenance,metrics,package')
    ap.add_argument('--pdf'); ap.add_argument('--slug')
    a = ap.parse_args(); out = os.path.abspath(a.out)
    rc = 0
    for s in [x.strip() for x in a.stages.split(',') if x.strip()]:
        if s == 'provenance':
            if not a.pdf: print('skip provenance: 缺 --pdf'); rc = 2; continue
            rc |= run('text.probe', {'pdf': a.pdf}, out, 'provenance')
        elif s == 'metrics':
            f = os.path.join(out, '03-rules.json')
            if not os.path.exists(f): print('skip metrics: 03-rules.json 未就绪'); rc = 2; continue
            rc |= run('audit.lint', {'ses': f}, out, 'metrics-lint')
            rc |= run('audit.ontology', {'ses': f}, out, 'metrics-ontology')
            recs = [json.load(open(os.path.join(out, f'runner-{n}.json'), encoding='utf-8'))
                    for n in ('metrics-lint', 'metrics-ontology')]
            gate = 'PASS' if all(r['exit'] == 0 for r in recs) else 'FAIL'
            json.dump({'capabilities': [{'id': r['capability'], 'version': r['version'], 'exit': r['exit'],
                                         'stdout_sha12': r['stdout_sha12'], 'summary': r['stdout'][:300]}
                                        for r in recs], 'counts': {}, 'gate': gate, 'generated_by': 'runner.py'},
                      open(os.path.join(out, 'audit_metrics.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
            print('metrics gate =', gate)
            os.replace(os.path.join(out, 'runner-metrics-lint.json'), os.path.join(out, 'runner-metrics.json'))
        elif s == 'package':
            if not os.path.exists(os.path.join(out, 'audit_result.json')):
                print('skip package: audit_result.json 未就绪（需 audit 节点先跑）'); rc = 2; continue
            rc |= run('merge.ses', {'out': out}, out, 'package')
        elif s == 'semantica':
            ses = os.path.join(out, 'ses.json')
            if not os.path.exists(ses): print('skip semantica: ses.json 未就绪'); rc = 2; continue
            p = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'semantica_ingest.py'),
                                '--ses', ses, '--out', out], capture_output=True, text=True)
            print((p.stdout or p.stderr).strip()[:300]); rc |= p.returncode
        else:
            print('unknown stage', s); rc = 2
    print('run_all:', 'ok' if rc == 0 else f'rc={rc}')
    return rc

if __name__ == '__main__':
    sys.exit(main())
