# -*- coding: utf-8 -*-
"""verify_pipeline —— 把门禁接进流水线（第 2 步：让它自动跑，而不是只能被调用）。

三件事：
  ① `verify_pipeline()`：一次跑完 三族门禁（闭环 / 分步 / 客观判据），写 quality/*.yaml，
     返回**合并判定**；
  ② `apply_manifest_gate()`：把合并判定写进 manifest ——
     · 有 FAIL ⇒ 状态保持 `draft` 并记录阻塞项（**不得进入 validated**）
     · 全 pass / pass_with_waivers ⇒ 允许 `draft → validated`
     · **任何情况下都不自动 publish**（publish 需用户在 UI 亲自确认）
  ③ `section_gate()`：逐节门禁（供编排器在每节起草后调用），
     在既有 gate_check_draft 之外补「must_cover / facts 引用率 / 题注」三项。

设计约束：**判定由门禁做，不由写作 Agent 自判**；探针未标定 ⇒ invalid，不得当 pass。
"""
from __future__ import annotations

import json
from pathlib import Path

from .closure_verify import closure_verify, save_closure_report
from .objective_criteria import run_objective_criteria, save_objective_report
from .stage_gates import run_stage_gates, save_stage_gates

_PASS = ("pass", "pass_with_waivers")


def _j(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:                                     # noqa: BLE001
        return d


def verify_pipeline(corpus_dir, *, draft_path=None, source_md=None, source_docx=None,
                    compile_point=None, declared_sha256=None) -> dict:
    """跑完三族门禁并落盘。返回合并判定。

    参数均可选：缺成稿则相关的判据自动记 invalid，**不当作通过**。
    """
    root = Path(corpus_dir)
    qdir = root / "quality"
    qdir.mkdir(parents=True, exist_ok=True)

    clo = closure_verify(corpus_dir, draft_path=draft_path)
    gat = run_stage_gates(corpus_dir, draft_path=draft_path, source_md=source_md,
                          source_docx=source_docx)
    obj = run_objective_criteria(corpus_dir, draft_path=draft_path, source_md=source_md,
                                 source_docx=source_docx, declared_sha256=declared_sha256,
                                 compile_point=compile_point or "")

    save_closure_report(clo, qdir / "closure_report.yaml")
    save_stage_gates(gat, qdir / "stage_gates.yaml")
    save_objective_report(obj, qdir / "objective_verify.yaml")

    def _stat(coll):
        return {"pass": sum(1 for x in coll if x.get("verdict") in _PASS),
                "FAIL": sum(1 for x in coll if x.get("verdict") == "FAIL"),
                "invalid": sum(1 for x in coll if x.get("verdict") == "invalid"),
                "total": len(coll)}

    # 记录 provider 能力来源（使「两图不一致」成为可审计项，而非隐患）
    try:
        from .providers_semantica import probe_semantica
        pr = probe_semantica()
        (qdir / "provider_probe.yaml").write_text(
            json.dumps({"policy": "能力须实测；未获证据的能力不声明",
                        "probe": {k: v for k, v in pr.items() if k != "client"}},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as _e:                                # noqa: BLE001
        (qdir / "provider_probe.yaml").write_text(
            json.dumps({"probe": {"available": False, "error": str(_e)}},
                       ensure_ascii=False, indent=2), encoding="utf-8")

    blocking = [f"{x.get('id') or x.get('stage')}: {x.get('missing', [])[:3]}"
                for x in clo["closures"] + gat["gates"] + obj["criteria"]
                if x.get("verdict") == "FAIL"]
    verdict = "blocked" if blocking else "passed"
    result = {"verdict": verdict,
              "closure": _stat(clo["closures"]),
              "stage_gates": _stat(gat["gates"]),
              "objective": _stat(obj["criteria"]),
              "blocking_count": len(blocking),
              "blocking": blocking[:20],
              "invalid_count": (_stat(clo["closures"])["invalid"] + _stat(gat["gates"])["invalid"]
                                + _stat(obj["criteria"])["invalid"]),
              "note": "invalid 表示判据对象缺失或探针未标定 —— **不得视为通过**"}
    (qdir / "verify_pipeline.yaml").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def apply_manifest_gate(corpus_dir, result: dict | None = None) -> dict:
    """把合并判定写进 manifest，并按状态机约束推进/保持状态。

    规则（P0 状态机 draft → validated → published）：
      · verdict == blocked ⇒ status 保持 draft，记录 gate_summary
      · verdict == passed  ⇒ 允许 draft → validated（若当前是 draft）
      · **永不**由本函数写 published —— 发布须用户在界面亲自确认
    """
    root = Path(corpus_dir)
    mpath = root / "manifest.yaml"
    man = _j(mpath, {}) or {}
    result = result or _j(root / "quality" / "verify_pipeline.yaml", {}) or {}
    verdict = result.get("verdict", "unknown")

    man["gate_summary"] = {"verdict": verdict,
                           "closure": result.get("closure"),
                           "stage_gates": result.get("stage_gates"),
                           "objective": result.get("objective"),
                           "blocking_count": result.get("blocking_count"),
                           "invalid_count": result.get("invalid_count"),
                           "checked_at_source": "quality/verify_pipeline.yaml"}
    prev = man.get("status", "draft")
    if verdict == "blocked":
        man["status"] = "draft" if prev == "draft" else prev
        man["status_note"] = (f"门禁未通过（{result.get('blocking_count')} 项 FAIL）——"
                              f"不得进入 validated；阻塞项见 manifest.gate_summary 与 quality/*.yaml")
    elif verdict == "passed" and prev == "draft":
        man["status"] = "validated"
        man["status_note"] = "门禁全部通过（含豁免）；可由用户确认后 publish"
    elif verdict == "passed":
        man["status"] = prev
        man["status_note"] = "门禁全部通过；当前状态保持不变（published 仅由用户确认产生）"
    mpath.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": man.get("status"), "verdict": verdict,
            "note": man.get("status_note", "")}


def section_gate(project_dir, section_id: str, draft_md: str) -> dict:
    """逐节门禁：供编排器在每节起草后调用。

    在既有 gate_check_draft（字面数字 / must_cover / undefined）之外，补三项：
      ① must_cover 覆盖率（分母来自工作包）
      ② 该节 facts 引用率（defined 且非明细节点是否出现）
      ③ 占位符形态合规（若为占位符版）
    仍**不做**价值判断（论证是否成立等）——那类记 judgment_required 交人工。
    """
    import re
    pdir = Path(project_dir)
    wp = _j(pdir / "project" / "work_packages" / f"{section_id}.json", {}) or {}
    nodes = _j(pdir / "graph" / "nodes.yaml", []) or []
    dn = re.sub(r"[\s　]", "", draft_md or "")

    mc = wp.get("outline", {}).get("must_cover", []) or []
    mc_miss = [k for k in mc if k not in (draft_md or "")]

    sec_nodes = [n for n in nodes
                 if (n.get("section") == wp.get("outline", {}).get("title")
                     or n.get("section_index") == wp.get("outline", {}).get("index"))]
    if not sec_nodes:
        sec_nodes = [n for n in nodes if wp.get("semantic_key") and
                     wp["semantic_key"] in str(n.get("subject", ""))]
    facts_total, facts_miss = 0, []
    for n in sec_nodes:
        v = re.sub(r"[\s　]", "", str(n.get("value") or ""))
        if len(v) < 3 or n.get("status", "defined") != "defined" or n.get("kind") == "text":
            continue
        facts_total += 1
        if v not in dn:
            mm = re.match(r"([\d,]+(?:\.\d+)?)", v)
            if not (mm and (mm.group(1) in dn or mm.group(1).replace(",", "") in dn)):
                facts_miss.append(f"{n.get('subject')}·{n.get('predicate')}")
    ref_rate = round((facts_total - len(facts_miss)) / max(facts_total, 1) * 100, 1)

    ph_ok = True
    if "{{node:" in (draft_md or ""):
        bad = re.findall(r"\{\{(?!node:N-[0-9a-f]{12}\}\})[^}]*\}\}", draft_md)
        ph_ok = not bad

    blocking = []
    if mc_miss:
        blocking.append(f"must_cover 缺 {mc_miss}")
    if ref_rate < 95 and facts_total:
        blocking.append(f"facts 引用率 {ref_rate}% < 95%（缺 {len(facts_miss)}）")
    if not ph_ok:
        blocking.append("占位符形态违规")
    return {"section_id": section_id, "verdict": "FAIL" if blocking else "pass",
            "must_cover_total": len(mc), "must_cover_missing": mc_miss,
            "facts_total": facts_total, "facts_reference_rate": ref_rate,
            "facts_missing": facts_miss[:20], "placeholder_form_ok": ph_ok,
            "blocking": blocking,
            "judgment_required": ["该节论证是否成立", "证据支持等级"],
            "note": "判定由门禁做；judgment_required 项交人工，**不计为通过**"}
