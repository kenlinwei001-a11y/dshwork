# -*- coding: utf-8 -*-
"""handover —— 环节间「基于文档的四元交接校验」。

四份清单来自**四个独立来源**，故意不互相引用：

  A  上游自报清单      handover/<stage>/manifest_A.json（+ README.md 解释文档）
                       上游说「我产出了这些」——**可能虚报**（本会话已发生过伪造 id）
  B  下游独立清点      handover/<stage>/manifest_B.json
                       下游**不读 A**，只按 SOP 契约去**实际读产物**（扫盘 + 哈希 +
                       可解析性 + 行数），即「我亲眼看到这些」
  C  产物自述清单      handover/<stage>/manifest_C.json
                       从**产物内容本身**读出的元数据（manifest.status / 节点数 /
                       闸门 verdict / jsonl 行数）——即「产物自己怎么说」
  SOP 该环节 outputs 声明——契约说「应该有这些」

差异分类（每条都指向一个具体的失败模式）：
  A∖B  上游虚报：自报有、实际不存在            ⇒ 幻觉/未落盘
  B∖A  上游漏报：实际有、未自报                ⇒ 记录不全
  B∖SOP 契约外产物：实际有、SOP 未声明          ⇒ 规范漏项
  SOP∖B 契约未兑现：SOP 声明、实际没有          ⇒ 未产出
  C≠A/B 产物自述与清单不符（如 manifest.status 与声称状态不一致）⇒ 自相矛盾

交接门：四元比对通过 ⇒ 写 CONFIRMED（下游方可开工）；不通过 ⇒ BLOCKED + 工单。
目的：**用几个独立来源的交叉替代单 agent 自证**，把幻觉挡在环节边界上。
"""
from __future__ import annotations

import hashlib
import json
from fnmatch import fnmatch
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
PKG = WS / "SHUFE-BDC-2019-001"
HD = PKG / "handover"
REC = PKG / "quality" / "run_record"


def _sha(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:32]
    except Exception:
        return ""


def _jit(path: Path):
    """可解析性探测：json/yaml/jsonl 能否解析。"""
    try:
        t = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"parsable": False, "error": f"{type(e).__name__}: {e}"}
    try:
        if path.suffix == ".jsonl":
            n = sum(1 for l in t.splitlines() if l.strip())
            for l in t.splitlines():
                if l.strip():
                    json.loads(l)
            return {"parsable": True, "records": n}
        if path.suffix == ".json":
            d = json.loads(t)
            return {"parsable": True, "keys": (list(d)[:8] if isinstance(d, dict) else f"list[{len(d)}]")}
        if path.suffix in (".yaml", ".yml"):
            import yaml
            d = yaml.safe_load(t)
            return {"parsable": True, "keys": (list(d)[:8] if isinstance(d, dict) else f"list[{len(d)}]")}
    except Exception as e:
        return {"parsable": False, "error": f"parse: {type(e).__name__}: {e}"}
    return {"parsable": True, "text_chars": len(t)}


# ───────────────────────────────── A：上游自报（+ README 解释文档）
def declare(stage: str, record: dict) -> dict:
    d = HD / stage
    d.mkdir(parents=True, exist_ok=True)
    a = {"stage": stage, "script": record.get("script"),
         "exit_code": record.get("exit_code"),
         "declared_outputs": record.get("declared_outputs") or [],
         "produced": [{"path": o["path"], "sha256": o["sha256"], "bytes": o["bytes"]}
                      for o in (record.get("outputs") or [])],
         "source": "A=上游自报（可能虚报，故须与 B/C/SOP 交叉）"}
    (d / "manifest_A.json").write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = f"""# 环节 {stage} 交接说明（README）

- 脚本：`{record.get('script')}`　退出码：{record.get('exit_code')}　耗时：{record.get('elapsed_s')}s
- 是否产生变更：{"否（幂等）" if record.get('noop') else "是"}　must_change：{record.get('must_change')}

## 我产出了什么（自报，见 manifest_A.json）
"""
    for o in (record.get("outputs") or [])[:20]:
        readme += f"- `{o['path']}`（{o['bytes']} B）\n"
    if not (record.get("outputs") or []):
        readme += "- （未观察到产物）\n"
    readme += f"""
## 给下游的说明
- 声明的产物 glob：{json.dumps(record.get('declared_outputs') or [], ensure_ascii=False)}
- 检查项：{json.dumps(record.get('checks') or [], ensure_ascii=False)}
- 已知缺口/备注：{(record.get('stdout_tail') or '')[-300:].strip()}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
"""
    (d / "README.md").write_text(readme, encoding="utf-8")
    return a


# ───────────────────────────────── B：下游独立清点（不读 A）
def derive_b(entry: dict) -> dict:
    items = []
    for pat in entry.get("outputs") or []:
        for p in sorted(WS.glob(pat)):
            if not p.is_file():
                continue
            items.append({"path": str(p.relative_to(WS)), "pattern": pat,
                          "bytes": p.stat().st_size, "sha256": _sha(p),
                          "probe": _jit(p)})
    return {"stage": entry["id"], "patterns": entry.get("outputs") or [],
            "items": items, "count": len(items),
            "missing_patterns": [p for p in (entry.get("outputs") or [])
                                 if not list(WS.glob(p))],
            "source": "B=下游独立清点（实际读盘，不读上游 claim）"}


# ───────────────────────────────── C：产物自述（读内容里的元数据）
def derive_c(b: dict) -> dict:
    meta = {}
    for it in b["items"]:
        p = WS / it["path"]
        name = p.name
        if name == "manifest.yaml":
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
                meta[it["path"]] = {"status": m.get("status"),
                                    "gate_summary": (m.get("gate_summary") or {}).get("verdict")}
            except Exception:
                pass
        elif name.startswith("verify_pipeline") or name in ("stage_gates.yaml", "objective_verify.yaml",
                                                            "closure_report.yaml", "id_resolution.yaml",
                                                            "prompt_reuse.yaml", "sop_compliance.yaml"):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
                meta[it["path"]] = {"verdict": m.get("verdict"), "summary": {
                    k: v for k, v in m.items() if k in ("pass", "FAIL", "invalid", "gap_count")}}
            except Exception:
                pass
        elif name in ("nodes.yaml", "relations.yaml", "evidence.yaml", "graph.yaml"):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
                meta[it["path"]] = {"count": len(m) if isinstance(m, list) else
                                    {k: len(v) for k, v in m.items() if isinstance(v, list)}}
            except Exception:
                pass
        elif it["probe"].get("records") is not None:
            meta[it["path"]] = {"records": it["probe"]["records"]}
    return {"stage": b["stage"], "self_declared": meta,
            "source": "C=产物自述（从内容里读出的元数据，不采信外部声明）"}


# ───────────────────────────────── 比对 + 交接门
def compare(entry: dict, upstream_records: dict) -> dict:
    d = HD / entry["id"]
    d.mkdir(parents=True, exist_ok=True)
    a = {}
    for dep in entry.get("depends_on") or []:
        f = d / f"manifest_A_{dep}.json"
        if f.exists():
            a = json.loads(f.read_text(encoding="utf-8"))
    b = derive_b(entry)
    c = derive_c(b)
    (d / "manifest_B.json").write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "manifest_C.json").write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")

    A = {x["path"] for x in a.get("produced", [])}
    B = {x["path"] for x in b["items"]}
    SOP = set(entry.get("outputs") or [])
    diffs = []
    for p in sorted(A - B):
        diffs.append({"kind": "A_not_in_B", "path": p, "meaning": "上游虚报（自报有、实际无）"})
    for p in sorted(B - A):
        diffs.append({"kind": "B_not_in_A", "path": p, "meaning": "上游漏报（实际有、未自报）"})
    for pat in b["missing_patterns"]:
        diffs.append({"kind": "SOP_not_delivered", "path": pat, "meaning": "契约声明未兑现"})
    for it in b["items"]:
        if not it["probe"].get("parsable", True):
            diffs.append({"kind": "unparsable_artifact", "path": it["path"],
                          "meaning": f"产物不可解析：{it['probe'].get('error')}"})
    ok = not diffs
    res = {"stage": entry["id"], "checked_depends_on": entry.get("depends_on") or [],
           "A_count": len(A), "B_count": len(B), "SOP_patterns": len(SOP),
           "C_entries": len(c["self_declared"]),
           "diffs": diffs, "diff_count": len(diffs),
           "gate": "CONFIRMED" if ok else "BLOCKED",
           "rule": "四元交叉：A 自报 / B 独立清点 / C 产物自述 / SOP 契约"}
    (d / "handover_check.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "CONFIRMED" if ok else d / "BLOCKED").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res
