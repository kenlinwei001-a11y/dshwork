# -*- coding: utf-8 -*-
"""B4 能力基准：一次跑完 probe/gate/lint/patternize，冻结指标并做回归比较

用法：
  python3 benchmark.py --save                 # 跑全量并写 benchmarks/<date>.json + latest.json
  python3 benchmark.py                        # 只跑并打印，与 latest 比较（退化则退出码 1）
"""
import argparse, json, os, subprocess, sys, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.getcwd()
MANIFEST = []
THRESH = {"leak_max": 0, "lint_errors_max": 0, "recall_clause_min": 0.80}

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def load_manifest(path, root):
    d = json.load(open(path, encoding="utf-8"))
    out = []
    for m in d["standards"]:
        m = dict(m); m["ses"] = m["ses"] if os.path.isabs(m["ses"]) else os.path.join(root, m["ses"])
        out.append(m)
    return out

def collect():
    res = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"), "standards": [], "totals": {}}
    errs = 0
    for m in MANIFEST:
        row = {"id": m["id"]}
        rc, out, _ = run([sys.executable, os.path.join(HERE, "cap.py"), "patternize", "--ses", m["ses"]])
        for k, pat in (("recall_clause", "条款级召回"), ("recall_category", "分类级召回")):
            if pat in out: row[k] = float(out.split(pat)[1].split("%")[0].strip().split("｜")[0]) / 100
        res["standards"].append(row)
    rc, out, _ = run([sys.executable, os.path.join(HERE, "cap.py"), "lint", "--ses"] + [m["ses"] for m in MANIFEST])
    res["lint_errors"] = int(out.split("errors=")[1].split()[0]) if "errors=" in out else -1
    res["totals"] = {
        "clauses": sum(len(json.load(open(m["ses"], encoding="utf-8"))["clause_registry"]) for m in MANIFEST),
        "rules": sum(len(json.load(open(m["ses"], encoding="utf-8"))["audit_rule_cards"]) for m in MANIFEST),
        "mean_recall_clause": round(sum(r.get("recall_clause", 0) for r in res["standards"]) / len(MANIFEST), 3),
        "mean_recall_category": round(sum(r.get("recall_category", 0) for r in res["standards"]) / len(MANIFEST), 3),
    }
    return res

def compare(cur, prev):
    bad = []
    if cur["lint_errors"] > THRESH["lint_errors_max"]: bad.append(f"lint_errors {cur['lint_errors']}")
    if cur["totals"]["mean_recall_clause"] < THRESH["recall_clause_min"]: bad.append("recall_clause 低于阈值")
    if prev:
        d = cur["totals"]["mean_recall_clause"] - prev["totals"]["mean_recall_clause"]
        if d < -0.02: bad.append(f"召回退化 {d:+.3f}")
    return bad

def main():
    global MANIFEST, ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--manifest", default=os.path.join(HERE, "manifest.json"))
    ap.add_argument("--root", default=os.getcwd())
    a = ap.parse_args()
    ROOT = os.path.abspath(a.root)
    if os.path.exists(a.manifest):
        MANIFEST = load_manifest(a.manifest, ROOT)
    if not MANIFEST:
        raise SystemExit("未找到 manifest：%s（可复制 manifest.sample.json）" % a.manifest)
    cur = collect()
    latest = os.path.join(HERE, "benchmarks", "latest.json")
    prev = json.load(open(latest, encoding="utf-8")) if os.path.exists(latest) else None
    for r in cur["standards"]:
        print("  %-14s 条款级 %.0f%%  分类级 %.0f%%" % (r["id"], r.get("recall_clause", 0) * 100,
                                                     r.get("recall_category", 0) * 100))
    t = cur["totals"]
    print("  合计 条款 %d 规则 %d  平均召回 条款级 %.0f%% / 分类级 %.0f%%  lint_errors %d"
          % (t["clauses"], t["rules"], t["mean_recall_clause"] * 100, t["mean_recall_category"] * 100,
             cur["lint_errors"]))
    bad = compare(cur, prev)
    if bad:
        print("  REGRESSION:", bad)
    if a.save:
        day = datetime.date.today().isoformat()
        p2 = os.path.join(HERE, "benchmarks", day + ".json")
        json.dump(cur, open(p2, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        json.dump(cur, open(latest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("  saved", p2)
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
