# -*- coding: utf-8 -*-
"""evo_native —— 本项目 venv 调用 semantica 全部能力的统一门面。

## 架构

    knowledge-processing-expert/.venv (Py3.9)
        evo_native.call(op, **params)
            │  subprocess
            ▼
    /Users/apple/.venvs/semantica/bin/python  (Py3.11)
        _native_worker.py → semantica.<module>

## 15 个可用 op

    conflicts   5 类冲突检测（value/type/relationship/temporal/logical）+ 4 种解决
    evals       10 个评估器（exact_match/levenshtein/rouge/llm_as_judge/numeric_range/...）
    ner         实体抽取（pattern / ml / llm）
    relations   关系抽取
    triplets    三元组抽取
    coref       指代消解
    dedup       实体去重（阈值 + 合并策略）
    shacl       SHACL 形状生成 + 校验（需 pyshacl，已装）
    ontology    从图生成本体
    provenance  W3C PROV-O 溯源
    seed        可信源 bootstrap（seed_first 冲突优先）
    export      导出（json / csv / parquet / rdf-turtle）
    parse       文档解析（DocumentParser；DoclingParser 需 docling 未装）
    reasoning   推理（Reasoner 前向链）
    capability  探测环境

## 用法

    from corpus_pipeline.evo_native import call, capability
    print(capability())
    r = call("conflicts", entities=[{"id":"a","value":1},{"id":"a","value":2}])
    r = call("evals", cases=[("apple","aple")], evaluators=["levenshtein"])
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

SEM_PY = "/Users/apple/.venvs/semantica/bin/python"
WORKER = Path(__file__).resolve().parent / "_native_worker.py"
DEFAULT_TIMEOUT = 300


def call(op: str, timeout: int = DEFAULT_TIMEOUT, **params) -> dict:
    """调 semantica 的一个 op。返回 {"ok":bool, ...}。"""
    req = dict(params)
    req["op"] = op
    try:
        r = subprocess.run([SEM_PY, str(WORKER)],
                           input=json.dumps(req, ensure_ascii=False),
                           capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "").strip()
        if not out:
            return {"ok": False, "op": op,
                    "error": "empty stdout", "stderr": (r.stderr or "")[-400:]}
        d = json.loads(out)
        return d
    except subprocess.TimeoutExpired:
        return {"ok": False, "op": op, "error": "timeout %ds" % timeout}
    except Exception as e:
        return {"ok": False, "op": op, "error": str(e)}


def capability() -> dict:
    return call("capability", timeout=90)


def available_ops() -> list:
    return ["conflicts", "evals", "ner", "relations", "triplets", "coref",
            "dedup", "shacl", "ontology", "provenance", "seed", "export",
            "parse", "reasoning", "capability"]
