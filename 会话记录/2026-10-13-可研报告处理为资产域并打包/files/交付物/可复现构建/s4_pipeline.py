# -*- coding: utf-8 -*-
"""工序 4-7 全链路驱动：本体抽取（注入 LLM 语义产物）→ 推演回放 → 质量登记 → 脱敏索引。

注意：**不传 doc_type**。kp 项目内置的 domain_rules 注册表只有「产线类可研」计算规格
（新增生产线数量/合格产能/单套变动成本…），对高校科研用房项目属于跨域污染；
本项目的领域规则由 LLM 层从原文抽取，已随 extractions 注入 graph["rules"]。
"""
import json
import re
import sys
from pathlib import Path

KP = "/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert"
sys.path.insert(0, KP)
from corpus_pipeline import stage_4_ontology, stage_5_replay, stage_6_quality, stage_7_desensitize  # noqa: E402
from corpus_pipeline import stage_1_normalize, stage_2_outline, stage_3_chunk  # noqa: E402
from corpus_pipeline import full_emit as FE  # noqa: E402
from corpus_pipeline.ontology import validate_extraction  # noqa: E402

WS = Path(__file__).resolve().parent.parent
BUILD = Path(__file__).resolve().parent
ROOT = WS / "SHUFE-BDC-2019-001"

# 法定大纲（发改投资规〔2023〕304号 通用大纲）covers
GOV = Path("/Users/apple/.agents/.workdsh-state/skills/retained-revisions/"
           "rev-624abe095b926ebf4cbf0804/feasibility-report-edu-research/references/outline-gov-2023.yaml")
legal: list[str] = []
for m in re.finditer(r"covers:\s*\[([^\]]*)\]", GOV.read_text(encoding="utf-8")):
    for item in m.group(1).split(","):
        item = item.strip().strip("'\"")
        if item and item not in legal:
            legal.append(item)

# ---- 载入 LLM 语义抽取产物并逐单元校验 ----
extractions, bad = [], []
for p in sorted((BUILD / "extractions-clean").glob("*.json")):
    for unit in json.loads(p.read_text(encoding="utf-8")):
        v = validate_extraction(unit)
        if v["ok"]:
            extractions.append(unit)
        else:
            bad.append({"file": p.name, "chunk_id": unit.get("chunk_id"), "errors": v["errors"]})

# ---- 工序 1-3 重放（确定性：同输入同 chunk id）----
raw = (BUILD / "doc-clean" / "大数据研究中心可研.md").read_text(encoding="utf-8")
stage_1_normalize(raw, ROOT / "source")
import shutil  # noqa: E402
_dst = ROOT / "source" / "original.docx"
if _dst.exists():
    _dst.chmod(0o644); _dst.unlink()
shutil.copy2(BUILD / "source-original.docx", _dst)
_dst.chmod(0o644)  # copy2 会继承源文件的只读位，幂等重跑需可写
normalized = (ROOT / "source" / "normalized.md").read_text(encoding="utf-8")
FE.emit_meta(ROOT, raw)
# 工序 2 骨架抽取：章节层级取自 docx 标题样式（权威），覆盖校验对 304 号文法定内容项。
# 不用 kp stage_2_outline 的 _parse_heading 正则——它会把「1.财经特色鲜明…」这类
# 编号列表项误判为标题（实测本报告多出 20+ 个假章节）。
_authoritative = json.loads((BUILD / "doc-clean" / "headings.json").read_text(encoding="utf-8"))
sections = [{"level": h["level"], "title": h["title"]} for h in _authoritative]
covered = [s["title"] for s in sections]
missing_literal = [t for t in legal if not any(t in c for c in covered)]
outline = {"sections": sections, "legal_outline": legal, "covered": covered,
           "missing": missing_literal, "coverage_ok": not missing_literal,
           "structure_source": "docx w:pStyle 1/2/3（权威）",
           "literal_missing_note": "法定内容项按标题字面匹配的未命中清单；本报告为 2019 年编制，"
                                   "采用旧版章节体系，字面未命中不等于内容缺失。"
                                   "语义映射结论见 outline_coverage.yaml（待客户确认）。"}
(ROOT / "outline.yaml").write_text(json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")
chunks = stage_3_chunk(normalized, ROOT / "chunks")

# ---- 工序 4：本体抽取（注入语义产物，不注入领域规则）----
graph = stage_4_ontology(chunks, ROOT, extractions=extractions, doc_type=None)

# ---- 工序 5/6/7 ----
trace_seed = [
    {"stage": "1", "event": "normalize", "detail": "ok"},
    {"stage": "2", "event": "outline", "detail": f"{len(outline.get('sections', []))} sections"},
    {"stage": "3", "event": "chunk", "detail": f"{len(chunks)} chunks（stage_3_chunk 同步改写 graph）"},
    {"stage": "4", "event": "ontology", "detail": f"{len(graph.get('facts', []))} facts"},
]
# stage_4_ontology 会把 graph/*.yaml 写到 out=ROOT；chunks 已在 ROOT/chunks
FE.emit_nodes(ROOT, graph)
FE.emit_rules(ROOT, graph)
replay = stage_5_replay(graph, ROOT / "reasoning")
quality = stage_6_quality(outline, graph, replay, ROOT / "quality")
desens = stage_7_desensitize(chunks, graph, ROOT)
FE.emit_provenance(ROOT, graph, chunks)
FE.emit_invariants(ROOT)
FE.emit_evidence(ROOT, graph, chunks)
trace = trace_seed + [
    {"stage": "5", "event": "replay", "detail": f"{len(replay.get('contradictions', []))} conflicts"},
    {"stage": "6", "event": "quality", "detail": quality["gate"]},
    {"stage": "7", "event": "desensitize", "detail": f"{desens['skeletons']} skeletons"},
]
FE.emit_reasoning(ROOT, replay, graph, trace)
FE.emit_quality_split(ROOT, quality)
# 工具层缺陷绕行：emit_style 用章节标题直接做文件名，标题含 "/" 时路径断裂
# （本报告 6.6 节标题为「数据/语音通信系统与综合布线系统」）。仅对文件名安全副本做替换，
# outline.yaml 保留真实标题；缺陷已登记到 quality/gaps.yaml。
def _safe_name(t: str, limit: int = 60) -> str:
    # 文件名安全化：替换路径分隔符 + 截断（emit_style 直接用标题做文件名，
    # 长标题会触发 OSError: File name too long，标题含 "/" 会断裂路径）
    t = t.replace("/", "／").replace("\\", "＼").replace(":", "：")
    return t if len(t) <= limit else t[:limit] + "…"


_safe_outline = {**outline,
                 "sections": [{**s, "title": _safe_name(s["title"])} for s in outline["sections"]]}
FE.emit_style(ROOT, chunks, _safe_outline)
print("[note] emit_style 使用文件名安全标题副本（/ -> ／），outline.yaml 保留真实标题")
skeletons = [json.loads(l) for l in (ROOT / "chunks" / "skeletons.jsonl").read_text(encoding="utf-8").splitlines() if l]
FE.emit_index(ROOT, graph, chunks, skeletons)
FE.emit_reuse(ROOT, graph, outline)
from corpus_pipeline.store import emit_manifest  # noqa: E402
import hashlib  # noqa: E402

emit_manifest(ROOT, corpus_id="SHUFE-BDC-2019-001", version="V1.0",
              source_fingerprint=hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16])

# ---- 报告 ----
report = {
    "input_md": "build/doc-clean/大数据研究中心可研.md（由 build/source-original.docx 确定性重推）",
    "extractions_loaded": len(extractions),
    "extraction_units_rejected": bad,
    "chunks": len(chunks),
    "facts": len(graph["facts"]),
    "rules": len(graph["rules"]),
    "claims": len(graph["claims"]),
    "evidence": len(graph["evidence"]),
    "relations": len(graph["relations"]),
    "conflicts": len(replay.get("contradictions", [])),
    "outline_missing_legal_items": len(outline["missing"]),
    "gate": quality["gate"],
    "skeletons": desens["skeletons"],
    "desensitized_nodes": desens["nodes"],
}
(BUILD / "stage4_7_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "extraction_units_rejected"}, ensure_ascii=False, indent=2))
if bad:
    print("REJECTED:", json.dumps(bad, ensure_ascii=False, indent=2)[:2000])
