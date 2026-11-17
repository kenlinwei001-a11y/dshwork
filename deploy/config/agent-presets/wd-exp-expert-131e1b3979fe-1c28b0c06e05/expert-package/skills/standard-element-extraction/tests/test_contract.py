#!/usr/bin/env python3
"""契约测试：规则卡三处口径必须一致（v1.1）。"""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VO = os.path.join(ROOT, "scripts", "validate_ontology.py")
LINT = os.path.join(ROOT, "scripts", "cap.py")
F = os.path.join(HERE, "fixtures")

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr

cases = [
    ("numeric.json", 0, 0, "数值卡：两套校验都应通过"),
    ("qualitative.json", 0, 0, "定性卡（无 predicate）：两套校验都应通过"),
    ("neither.json", 1, 0, "两者都缺：两套校验都应失败"),
    ("both.json", 1, 0, "两者并存：两套校验都应失败"),
]
fail = 0
for name, want_o, want_l, why in cases:
    p = os.path.join(F, name)
    co, outo = run([sys.executable, VO, "--ses", p])
    cl, outl = run([sys.executable, LINT, "lint", "--ses", p])
    ok = (co == want_o and cl == want_l)
    print(("PASS " if ok else "FAIL ") + f"{name:18s} ontology={co} lint={cl}  # {why}")
    if not ok:
        fail += 1
        print("   ontology:", outo.strip()[:300])
        print("   lint:", outl.strip()[:300])
print("contract:", "ALL PASS" if fail == 0 else f"{fail} FAILED")
sys.exit(1 if fail else 0)
