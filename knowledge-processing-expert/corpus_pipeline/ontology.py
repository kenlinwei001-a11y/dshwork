"""工序 4 本体抽取 —— tool + LLM 两阶段语义层。

确定性部分（tool）：发出结构化抽取请求、校验 LLM 输出、登记节点、建十类关系。
语义部分（LLM）：按抽取请求从 chunk 文本抽取 主语/谓语/值/时间/单位 等真实事实。

契约：LLM 每 chunk 输出一份 extraction JSON，经 validate_extraction 确定性校验后才入图。
"""
from __future__ import annotations
import json
import re
from pathlib import Path

from .spec import TEN_RELATIONS

# --------------------------------------------------------------------------- #
# Claim 语义模型：Claim 是独立论证对象（非普通文本字段）。
# 三类字段严格区分：
#   输入字段（用户/外部系统提供，LLM 抽取）→ CLAIM_INPUT_FIELDS
#   推演字段（系统经抽取/关联/验证/推理产生，非原始输入）→ CLAIM_DERIVED_FIELDS
#   治理字段（版本/时间/审核等系统管理信息）→ CLAIM_GOVERNANCE_FIELDS
# 推演字段（status/confidence/evidence_refs）若 LLM 未提供，须标「未验证」，不得伪装成已证。
# --------------------------------------------------------------------------- #
CLAIM_INPUT_FIELDS = ("id", "text", "claim_type", "source")
CLAIM_DERIVED_FIELDS = ("status", "evidence_refs", "premise_refs", "derived_from", "confidence")
CLAIM_GOVERNANCE_FIELDS = ("valid_time",)

CLAIM_TYPE_VALUES = ("fact", "hypothesis", "inference", "conclusion", "recommendation")
CLAIM_STATUS_VALUES = ("unverified", "supported", "contradicted", "verified")

# 旧「论断性质 type」→ 新「论证类型 claim_type」映射（向后兼容旧抽取产物）
_TYPE_TO_CLAIM_TYPE = {
    "judgment": "conclusion",
    "prediction": "hypothesis",
    "causal": "inference",
    "suggestion": "recommendation",
    "risk": "hypothesis",
}


# 抽取契约：LLM 每 chunk 应输出的结构
EXTRACTION_SCHEMA = {
    "chunk_id": "string",
    "facts": [{"subject": "string", "predicate": "string", "value": "string", "unit": "string", "time": "string", "source": "string"}],
    "rules": [{"id": "string", "expr": "string", "inputs": ["node_id"], "output": "node_id"}],
    "claims": [{
        "id": "string", "text": "string",
        "claim_type": "fact|hypothesis|inference|conclusion|recommendation",
        "source": "string",
        "status": "unverified|supported|contradicted|verified",
        "evidence_refs": ["evidence_id"], "premise_refs": ["claim_id"],
        "derived_from": ["claim_id"], "confidence": "number|null",
        "valid_time": {"start": "datetime|null", "end": "datetime|null"},
    }],
    "evidence": [{"id": "string", "claim": "claim_id", "doc": "string", "span": "int,int", "kind": "string"}],
    "relations": [{"from": "string", "to": "string", "type": "has_value|has_attribute|instance_of|part_of|causes|depends_on|supports|contradicts|temporal|located_in"}],
}

# 给 LLM 的抽取指令（运行时按此 prompt 抽取）
EXTRACTION_PROMPT = """你是知识抽取器。对下面的 chunk 文本，抽取结构化知识，只输出 JSON（不要 markdown）。

规则：
- facts：抽「主语-谓语-值」，主语用业务语义（如「营业收入」「净利润」「注册资本」「成立年份」），不要用 chunk id。
  数值拆出 unit（亿元/万元/%/年），时间拆出 time（如 2024）。
- rules：抽可复用的推导规则（公式/换算），expr 用自然语言或算式，inputs/outputs 引用节点 id。
- claims：抽论断/结论/风险/预测/因果/建议，claim_type 取 fact|hypothesis|inference|conclusion|recommendation。
  只填「输入字段」id/text/claim_type/source；status/evidence_refs/premise_refs/derived_from/confidence 是
  「推演字段」，由系统后续产生，不要填（留空即可），更不要把模型推断的属性伪装成用户提供的事实。
- evidence：为 claim 定位证据（doc/span/kind）。
- relations：只建十类关系：has_value, has_attribute, instance_of, part_of, causes, depends_on, supports, contradicts, temporal, located_in。
- 不编造文本中不存在的数字或事实；不确定就省略该字段。

chunk_id: {chunk_id}
text:
{text}
"""


def emit_extraction_requests(chunks: list[dict]) -> list[dict]:
    """确定性阶段：为每个 chunk 生成一条抽取请求（供 LLM 填充）。"""
    return [{"chunk_id": c["id"], "text": c["text"], "schema": EXTRACTION_SCHEMA} for c in chunks]


def _normalize_claim(c: dict) -> dict:
    """归一化 claim：兼容旧字段（type→claim_type、evidence→evidence_refs），补推演字段缺省。"""
    c = dict(c)
    if "evidence_refs" not in c and "evidence" in c:
        c["evidence_refs"] = c.pop("evidence")
    if not c.get("claim_type"):
        c["claim_type"] = _TYPE_TO_CLAIM_TYPE.get(c.get("type"), "hypothesis")
    c.setdefault("status", "unverified")
    c.setdefault("evidence_refs", [])
    c.setdefault("premise_refs", [])
    c.setdefault("derived_from", [])
    c.setdefault("confidence", None)
    return c


def validate_extraction(ext: dict) -> dict:
    """确定性校验 LLM 输出，返回 {ok, errors}。"""
    errors: list[str] = []
    if not isinstance(ext, dict) or not ext.get("chunk_id"):
        return {"ok": False, "errors": ["缺少 chunk_id"]}
    for f in ext.get("facts", []):
        if not f.get("subject") or not f.get("value"):
            errors.append(f"fact 缺 subject/value: {f}")
    for cl in ext.get("claims", []):
        if not cl.get("id") or not cl.get("text"):
            errors.append(f"claim 缺 id/text: {cl}")
        if cl.get("claim_type") and cl["claim_type"] not in CLAIM_TYPE_VALUES:
            errors.append(f"claim 非法 claim_type: {cl.get('claim_type')}")
        if cl.get("status") and cl["status"] not in CLAIM_STATUS_VALUES:
            errors.append(f"claim 非法 status: {cl.get('status')}")
    for r in ext.get("relations", []):
        if r.get("type") not in TEN_RELATIONS:
            errors.append(f"非法关系类型: {r.get('type')}")
        if not r.get("from") or not r.get("to"):
            errors.append(f"relation 缺 from/to: {r}")
    return {"ok": not errors, "errors": errors}


def _fact_id(subject: str, predicate: str, value: str, time: str) -> str:
    from hashlib import sha1
    return "N-" + sha1(f"{subject}|{predicate}|{value}|{time}".encode("utf-8")).hexdigest()[:12]


def apply_extraction(chunks: list[dict], extractions: list[dict]) -> dict:
    """确定性阶段：把 LLM 输出登记为图谱（facts/rules/claims/evidence + 十类关系）。"""
    graph = {"facts": [], "rules": [], "claims": [], "evidence": [], "relations": [], "relation_types": list(TEN_RELATIONS)}
    for ext in extractions:
        v = validate_extraction(ext)
        if not v["ok"]:
            continue
        for f in ext.get("facts", []):
            fid = _fact_id(f["subject"], f["predicate"], str(f["value"]), f.get("time", ""))
            node = {"id": fid, "subject": f["subject"], "predicate": f["predicate"],
                    "value": f["value"], "unit": f.get("unit", ""), "time": f.get("time", ""), "source": f.get("source", ext["chunk_id"])}
            graph["facts"].append(node)
            graph["relations"].append({"from": f["subject"], "to": fid, "type": "has_value"})
        graph["rules"].extend(ext.get("rules", []))
        graph["claims"].extend(_normalize_claim(c) for c in ext.get("claims", []))
        graph["evidence"].extend(ext.get("evidence", []))
        graph["relations"].extend(ext.get("relations", []))
    return graph


def replay(graph: dict) -> dict:
    """工序 5 推演回放：同一 (subject, predicate) 下数值不一致 → 矛盾（待审）。"""
    from collections import defaultdict
    by_key = defaultdict(list)
    for f in graph["facts"]:
        by_key[(f["subject"], f["predicate"])].append(f)

    conflicts = []
    for (subj, pred), fs in by_key.items():
        vals = {(f["value"], f.get("unit", "")) for f in fs}
        if len(vals) > 1:
            conflicts.append({
                "type": "numeric", "subject": subj, "predicate": pred,
                "values": sorted(v[0] + (v[1] and (" " + v[1]) or "") for v in vals),
                "involved": [f["id"] for f in fs], "status": "待审",
            })
    return {"replayed": len(graph["facts"]), "contradictions": conflicts}
