"""kp_toolkit — 知识处理确定性工具层（tool + LLM 架构中的「tool」部分）。

只做确定性计算，零 LLM：同输入同输出、可单测、可复现。
对应 🔵 档技能：分句、图谱编译、溯源链、数字/时间冲突检测、schema 校验。
仅依赖 Python 标准库，无第三方依赖。
"""
from .segmentation import segment_sentences, segment_chunks, stable_id
from .graph import compile_graph, validate_graph, dangling_refs
from .provenance import build_provenance, trace_to_evidence
from .conflict import detect_numeric_conflicts, detect_time_conflicts
from .validate import validate_schema

__all__ = [
    "segment_sentences", "segment_chunks", "stable_id",
    "compile_graph", "validate_graph", "dangling_refs",
    "build_provenance", "trace_to_evidence",
    "detect_numeric_conflicts", "detect_time_conflicts",
    "validate_schema",
]
__version__ = "0.1.0"
