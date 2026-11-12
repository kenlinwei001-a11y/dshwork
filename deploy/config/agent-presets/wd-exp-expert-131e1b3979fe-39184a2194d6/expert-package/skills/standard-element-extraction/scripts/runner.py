#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""能力执行器：按注册表解析能力 -> 套配置 -> 执行 -> 记录溯源。
用法:
  python3 runner.py list
  python3 runner.py run text.probe --config pdf=/abs/x.pdf --out out/provenance.json
配置优先级: CLI --config > 运行配置 > 注册表 default。
"""
import argparse, hashlib, json, os, shlex, subprocess, sys, time

ROOT = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(ROOT)
REG = os.path.join(ROOT, 'registry', 'capabilities.json')

def load():
    return json.load(open(REG, encoding='utf-8'))['capabilities']

def resolve_config(cap, cli):
    cfg = {}
    for k, spec in (cap.get('config_schema') or {}).items():
        if 'default' in spec:
            cfg[k] = spec['default']
    cfg.update(cli)
    for k, spec in (cap.get('config_schema') or {}).items():
        if spec.get('required') and cfg.get(k) in (None, ''):
            sys.exit(f'缺少必填配置 {k}')
        if 'range' in spec and k in cfg:
            lo, hi = spec['range']
            if not (lo <= cfg[k] <= hi):
                sys.exit(f'配置 {k}={cfg[k]} 越界 [{lo},{hi}]')
        if 'values' in spec and k in cfg and cfg[k] not in spec['values']:
            sys.exit(f'配置 {k}={cfg[k]} 不在 {spec["values"]}')
    return cfg

def build(cap, cfg):
    impl = cap['impl']
    if impl['runtime'] == 'agent':
        sys.exit('llm 能力不在此执行；由编排器派给 agent 并按 schema 校验')
    entry = impl['entry'].replace('${SKILL}', SKILL)
    args = [a.format(**cfg) for a in impl.get('args', [])]
    if impl['runtime'] == 'python3':
        return ['python3', entry] + args
    return [entry] + args

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['list', 'run'])
    ap.add_argument('cap', nargs='?')
    ap.add_argument('--config', action='append', default=[])
    ap.add_argument('--out')
    a = ap.parse_args()
    caps = load()
    if a.action == 'list':
        for k, v in caps.items():
            print(f"{k:18s} {v['kind']:4s} v{v['version']:8s} status={v.get('status','OK')}")
        return 0
    cap = caps.get(a.cap) or sys.exit(f'未知能力 {a.cap}')
    if cap.get('status') == 'CONTRACT_CONFLICT':
        print(json.dumps({'capability': a.cap, 'blocked': True, 'reason': cap.get('conflict')}, ensure_ascii=False))
        return 2
    cfg = resolve_config(cap, {kv.split('=', 1)[0]: kv.split('=', 1)[1] for kv in a.config})
    for k in ('dpi', 'min_level'):
        if k in cfg: cfg[k] = int(cfg[k])
    cmd = build(cap, cfg)
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    dt = round(time.time() - t0, 2)
    stdout = p.stdout.strip()
    rec = {'capability': a.cap, 'version': cap['version'], 'kind': cap['kind'],
           'config': cfg, 'cmd': ' '.join(shlex.quote(c) for c in cmd),
           'exit': p.returncode, 'seconds': dt,
           'stdout_sha12': hashlib.sha256(stdout.encode()).hexdigest()[:12],
           'stdout': stdout[:4000], 'stderr': p.stderr.strip()[:2000]}
    if a.out:
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        json.dump(rec, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f"{a.cap} exit={p.returncode} {dt}s sha12={rec['stdout_sha12']}")
    print(stdout[:800])
    return p.returncode

if __name__ == '__main__':
    sys.exit(main())
