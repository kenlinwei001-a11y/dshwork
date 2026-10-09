"""验证 tool+LLM 两阶段：LLM 语义抽取 → 正确事实 + 正确冲突检测。"""
import json
import tempfile
from pathlib import Path

from corpus_pipeline import stage_1_normalize, stage_2_outline, stage_3_chunk, stage_4_ontology, stage_5_replay
from corpus_pipeline.ontology import apply_extraction, validate_extraction, replay

SAMPLE = """某公司2024年度报告

第一章 总则
某公司成立于2010年，注册资本5000万元。

第二章 财务数据
2024年营业收入100亿元，同比增长20%。
2024年营业收入120亿元。净利润12.5亿元。
"""

# 模拟 LLM 语义抽取输出（主语用业务语义，非 chunk id）
LLM_EXTRACTIONS = [
    {"chunk_id": "C_EST", "facts": [
        {"subject": "成立年份", "predicate": "等于", "value": "2010", "unit": "年", "time": "", "source": "C_EST"},
        {"subject": "注册资本", "predicate": "等于", "value": "5000", "unit": "万元", "time": "", "source": "C_EST"},
    ]},
    {"chunk_id": "C_FIN", "facts": [
        {"subject": "营业收入", "predicate": "等于", "value": "100", "unit": "亿元", "time": "2024", "source": "C_FIN"},
        {"subject": "营业收入", "predicate": "等于", "value": "120", "unit": "亿元", "time": "2024", "source": "C_FIN"},
        {"subject": "净利润", "predicate": "等于", "value": "12.5", "unit": "亿元", "time": "2024", "source": "C_FIN"},
        {"subject": "同比增速", "predicate": "等于", "value": "20", "unit": "%", "time": "2024", "source": "C_FIN"},
    ]},
]


def test_llm_extraction():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        stage_1_normalize(SAMPLE, root / "source")
        chunks = stage_3_chunk((root / "source" / "normalized.md").read_text(), root / "chunks")
        # 用真实 chunk id 替换占位
        cids = [c["id"] for c in chunks]
        for ext, cid in zip(LLM_EXTRACTIONS, [cids[1], cids[2]]):  # 第2、3个chunk是正文
            ext["chunk_id"] = cid
            for f in ext["facts"]:
                f["source"] = cid

        graph = apply_extraction(chunks, LLM_EXTRACTIONS)
        facts = graph["facts"]
        subs = {f["subject"] for f in facts}
        assert "营业收入" in subs and "净利润" in subs and "注册资本" in subs and "成立年份" in subs, f"主语缺失: {subs}"

        r = replay(graph)
        # 只有「营业收入」100 vs 120 是冲突；「成立年份」vs「注册资本」不是
        conflict_subs = {c["subject"] for c in r["contradictions"]}
        assert "营业收入" in conflict_subs, "应检出营业收入矛盾"
        assert "成立年份" not in conflict_subs and "注册资本" not in conflict_subs, "误判不同事实为冲突"
        print("LLM_EXTRACTION OK:", json.dumps(r["contradictions"], ensure_ascii=False))


if __name__ == "__main__":
    test_llm_extraction()
