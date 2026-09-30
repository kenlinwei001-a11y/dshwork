"""corpus_pipeline 端到端自测：跑通七道工序并验证关键产物（尤其 skeletons.jsonl 脱敏）。"""
import json
import tempfile
from pathlib import Path

from corpus_pipeline import run_pipeline

SAMPLE = """某公司2024年度报告

第一章 总则
某公司成立于2010年，注册资本5000万元。

第二章 财务数据
2024年营业收入100亿元，同比增长20%。
2024年营业收入120亿元。净利润12.5亿元。

| 指标 | 2024 |
|------|------|
| 营收 | 100亿 |
| 净利 | 12.5亿 |
"""


def test_full_pipeline():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "pkg"
        r = run_pipeline(SAMPLE, root, legal_outline=["第一章 总则", "第二章 财务数据", "第三章 风险"])

        # 骨架覆盖校验：缺第三章
        assert r["outline"]["missing"] == ["第三章 风险"]

        # 切块产物存在
        chunks_path = root / "chunks" / "chunks.jsonl"
        assert chunks_path.exists()

        # 关键：skeletons.jsonl 存在且已脱敏（无原始数值，有 {{node:Nxx}}）
        sk_path = root / "chunks" / "skeletons.jsonl"
        assert sk_path.exists()
        skeletons = [json.loads(l) for l in sk_path.read_text(encoding="utf-8").splitlines()]
        joined = "".join(s["text"] for s in skeletons)
        assert "100" not in joined and "120" not in joined and "12.5" not in joined, "骨架必须脱敏"
        assert "{{node:N-" in joined, "数值应替换为 {{node:Nxx}}"

        # 推演回放检出矛盾：营收 100 vs 120（同一主语谓语数值不一致）
        derivation = json.loads((root / "reasoning" / "derivation.yaml").read_text(encoding="utf-8"))
        assert any(("100" in c.get("values", []) and "120" in c.get("values", [])) for c in derivation["steps"])

        # 质量闸门：有冲突 → REVIEW
        gate = json.loads((root / "quality" / "gate_report.yaml").read_text(encoding="utf-8"))
        assert gate["gate"] == "REVIEW"

        # 节点倒排 + 术语 + 签名存在（30 契约 index 三件套）
        assert (root / "index" / "node_index.json").exists()
        assert (root / "index" / "term_index.json").exists()
        assert (root / "index" / "signature.yaml").exists()
        print("PIPELINE E2E PASSED")


if __name__ == "__main__":
    test_full_pipeline()
