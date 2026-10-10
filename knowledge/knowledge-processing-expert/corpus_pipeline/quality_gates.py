# -*- coding: utf-8 -*-
"""知识处理侧 P1：三个质量关口（QG1/QG2/QG3）显式化。

对齐文档「三个质量控制关口」：
  QG1 来源可信度（K1–K3 后）：原文可定位、解析完整、文档版本明确
  QG2 语义完整性（K4–K7 后）：对象类型/Claim/证据/关系/论证无结构错误
  QG3 资产可复用性（K8–K10 后）：资产有用途/适用条件/依赖/测试/复用边界

不通过时：QG1 回解析/标记来源不完整；QG2 修正抽取/人工确认；QG3 保留待审核，不进正式库。
"""
from __future__ import annotations
import json
from pathlib import Path

from .library import _read_data
from .ontology import CLAIM_TYPE_VALUES, CLAIM_STATUS_VALUES

# 三个关口定义
QUALITY_GATES = [
    {"id": "QG1", "name": "来源可信度", "stage": "K1-K3",
     "on_fail": "回到解析或标记来源不完整"},
    {"id": "QG2", "name": "语义完整性", "stage": "K4-K7",
     "on_fail": "修正抽取、补充映射或人工确认"},
    {"id": "QG3", "name": "资产可复用性", "stage": "K8-K10",
     "on_fail": "保留为待审核资产，不进入正式可复用注册状态"},
]


def gate_qg1(corpus_dir) -> dict:
    """QG1 来源可信度：文档版本明确 + 来源指纹 + 语义切片带来源锚点。"""
    d = Path(corpus_dir)
    checks = []
    manifest = _read_data(d / "manifest.yaml") or {}
    checks.append({"check": "文档版本明确", "passed": bool(manifest.get("version")),
                   "detail": manifest.get("version", "缺失")})
    checks.append({"check": "来源指纹", "passed": bool(manifest.get("source_fingerprint")),
                   "detail": manifest.get("source_fingerprint", "缺失")})
    # 语义切片是否带来源锚点（section/document 定位）
    sk = d / "chunks" / "skeletons.jsonl"
    anchored = 0
    total = 0
    if sk.exists():
        for line in sk.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            if c.get("section") or c.get("source_anchors") or c.get("document_id"):
                anchored += 1
    checks.append({"check": "切片来源锚点", "passed": total == 0 or anchored >= total,
                   "detail": f"{anchored}/{total}"})
    passed = all(c["passed"] for c in checks)
    return {"gate": "QG1", "name": "来源可信度", "passed": passed, "checks": checks}


def gate_qg2(corpus_dir) -> dict:
    """QG2 语义完整性：Claim 类型/状态合法 + 关系 from/to/type + 证据有来源。"""
    d = Path(corpus_dir)
    checks = []
    claims = _read_data(d / "graph" / "claims.yaml") or []
    if isinstance(claims, dict):
        claims = claims.get("claims", [])
    bad_claims = []
    for c in claims:
        if not c.get("id") or not c.get("text"):
            bad_claims.append({"id": c.get("id"), "reason": "缺 id/text"})
        if c.get("claim_type") and c["claim_type"] not in CLAIM_TYPE_VALUES:
            bad_claims.append({"id": c.get("id"), "reason": f"非法 claim_type {c.get('claim_type')}"})
        if c.get("status") and c["status"] not in CLAIM_STATUS_VALUES:
            bad_claims.append({"id": c.get("id"), "reason": f"非法 status {c.get('status')}"})
    checks.append({"check": "Claim 结构合法", "passed": not bad_claims,
                   "detail": f"{len(bad_claims)} 处问题" if bad_claims else "全部合法"})

    relations = _read_data(d / "graph" / "relations.yaml") or []
    if isinstance(relations, dict):
        relations = relations.get("relations", [])
    bad_rel = [r for r in relations if not r.get("from") or not r.get("to") or not r.get("type")]
    checks.append({"check": "关系 from/to/type 完整", "passed": not bad_rel,
                   "detail": f"{len(bad_rel)} 处缺 from/to/type" if bad_rel else "全部完整"})

    evidence = _read_data(d / "evidence" / "evidence.yaml") or []
    if isinstance(evidence, dict):
        evidence = evidence.get("evidence", [])
    no_src = [e for e in evidence if not (e.get("source") or e.get("source_anchor") or e.get("doc"))]
    checks.append({"check": "证据有来源", "passed": not no_src,
                   "detail": f"{len(no_src)} 处缺来源" if no_src else "全部有来源"})

    passed = all(c["passed"] for c in checks)
    return {"gate": "QG2", "name": "语义完整性", "passed": passed, "checks": checks}


def gate_qg3(corpus_dir) -> dict:
    """QG3 资产可复用性：16 域都带装配方法 + 不一致处理 + 可复用形态 + 依赖图无环。"""
    d = Path(corpus_dir)
    checks = []
    domains = _read_data(d / "reuse" / "domains.yaml") or {}
    domain_list = domains.get("domains") if isinstance(domains, dict) else domains
    domain_list = domain_list or []
    incomplete = []
    for dm in domain_list:
        if not (dm.get("assembly_method") and dm.get("mismatch_handling")):
            incomplete.append(dm.get("id", "?"))
    checks.append({"check": "16 域装配方法+不一致处理齐全",
                   "passed": len(domain_list) >= 16 and not incomplete,
                   "detail": f"{len(domain_list)} 域，缺 {len(incomplete)} 处"})

    from .dependencies import check_cycles
    cycle = check_cycles()
    checks.append({"check": "资产依赖图无环", "passed": not cycle,
                   "detail": f"环 {cycle}" if cycle else "无环"})

    manifest = _read_data(d / "manifest.yaml") or {}
    checks.append({"check": "复用边界（constraints）", "passed": bool(manifest.get("constraints")),
                   "detail": f"{len(manifest.get('constraints', []))} 条约束"})

    passed = all(c["passed"] for c in checks)
    return {"gate": "QG3", "name": "资产可复用性", "passed": passed, "checks": checks}


def run_all_gates(corpus_dir) -> dict:
    """跑三个关口，返回汇总（all_passed + 各关口结果）。"""
    gates = [gate_qg1(corpus_dir), gate_qg2(corpus_dir), gate_qg3(corpus_dir)]
    return {"gates": gates, "all_passed": all(g["passed"] for g in gates),
            "failed": [g["gate"] for g in gates if not g["passed"]]}
