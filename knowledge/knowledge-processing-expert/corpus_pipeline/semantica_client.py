# -*- coding: utf-8 -*-
"""Semantica 桥接客户端 —— 预留接口落地。

ARCHITECTURE.md 此前预留 `semantica_client`（本体管理 OWL/SHACL/SKOS 对接位）：
`bootstrap_claim_ontology(diffs, semantica_client=None)` 在客户端存在时委托其
`bootstrap_schema(diffs)` 从数据诱导本体草稿。本模块把该预留接口接到**已部署的
Semantica MCP**（stdio、NDJSON 帧、`python -m semantica.mcp_server`）。

设计约束：
- 纯标准库实现，无 `mcp` SDK 依赖（与 kp-mcp 自身一致）；
- 懒启动 + 单例；spawn/握手失败一律返回 None（调用方降级确定性规则，绝不阻塞主链路）；
- 图形数据落在 Semantica 自己的 KG 文件（默认 ~/.semantica/graph.json），
  不写入语料包目录；测试可用临时 KG 路径隔离，避免污染正式图。
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading

DEFAULT_KG_PATH = "/Users/apple/.semantica/graph.json"
DEFAULT_PYTHON = "/Users/apple/.venvs/semantica/bin/python"

# 本体诱导兜底底座：Semantica 抽取结果与本地 Claim 本体合并时保留的基础类/属性
_BASE_ONTOLOGY = {
    "classes": [
        {"name": "Claim", "type": "owl:Class", "description": "论证对象"},
        {"name": "Evidence", "type": "owl:Class", "description": "证据"},
    ],
    "properties": [
        {"name": "claim_type", "type": "owl:DatatypeProperty"},
        {"name": "status", "type": "owl:DatatypeProperty"},
        {"name": "has_evidence", "type": "owl:ObjectProperty", "range": "Evidence"},
        {"name": "has_premise", "type": "owl:ObjectProperty", "range": "Claim"},
    ],
    "constraints": [
        {"shape": "ClaimShape", "targetClass": "Claim", "constraints": []},
    ],
    "vocabulary": [
        {"concept": "Claim", "prefLabel": "论断", "altLabels": ["声明", "主张", "论点"]},
    ],
}


class SemanticaUnavailable(RuntimeError):
    """Semantica 不可用（未部署/spawn 失败/握手失败/调用失败）。"""


def _diffs_to_text(diffs: list[dict]) -> str:
    """把 Schema Diff 转成可交给 Semantica 抽取的自然语言描述。"""
    lines = []
    for d in diffs or []:
        kind = d.get("kind") or d.get("change") or "change"
        path = d.get("path") or d.get("field") or ""
        lines.append(f"{kind}: {path} {json.dumps(d.get('detail') or d.get('value') or '', ensure_ascii=False)}")
    return "\n".join(lines)


def _unwrap_result(resp: dict):
    """从 MCP tools/call 响应解出结构化结果（content[0].text 多为 JSON 字符串）。"""
    result = resp.get("result") or {}
    content = result.get("content") or []
    if content:
        text = content[0].get("text", "")
        if isinstance(text, str):
            try:
                return json.loads(text)
            except Exception:
                return text
    return result


class SemanticaClient:
    """极简 stdio MCP 客户端（NDJSON 帧，仅 tools/call 所需的最小实现）。"""

    def __init__(self, command: str | None = None, kg_path: str | None = None):
        self.kg_path = kg_path or os.environ.get("KP_SEMANTICA_KG_PATH", DEFAULT_KG_PATH)
        self.python = os.environ.get("KP_SEMANTICA_PYTHON", DEFAULT_PYTHON)
        self.command = command or os.environ.get("KP_SEMANTICA_COMMAND")
        self.proc: subprocess.Popen | None = None
        self._lock = threading.RLock()  # 可重入：start/call 内层 _write 会再次加锁
        self._next_id = 0
        self.protocol_version = None
        self.tool_names: list[str] = []

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> "SemanticaClient":
        with self._lock:
            if self.proc is not None and self.proc.poll() is None:
                return self
            if self.command:
                argv = shlex.split(self.command)
                env = dict(os.environ, SEMANTICA_KG_PATH=self.kg_path,
                           SEMANTICA_DISABLE_PROGRESS="1")
            else:
                argv = [self.python, "-m", "semantica.mcp_server"]
                env = dict(os.environ, SEMANTICA_KG_PATH=self.kg_path,
                           SEMANTICA_DISABLE_PROGRESS="1")
            try:
                self.proc = subprocess.Popen(
                    argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, text=True, env=env)
            except Exception as cause:
                raise SemanticaUnavailable(f"Semantica spawn 失败: {cause}") from cause
            self._handshake()
            return self

    def _handshake(self):
        req_id = self._write({"jsonrpc": "2.0", "method": "initialize",
                              "params": {"protocolVersion": "2024-11-05",
                                         "capabilities": {},
                                         "clientInfo": {"name": "kp-semantic-bridge", "version": "0.1.0"}}})
        resp = self._read_until(req_id)
        if "error" in resp or "result" not in resp:
            raise SemanticaUnavailable(f"initialize 失败: {resp.get('error')}")
        self.protocol_version = resp["result"].get("protocolVersion")
        self._write({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = self.call("tools/list", {}, _method=True)
        self.tool_names = [t.get("name") for t in tools] if isinstance(tools, list) else []

    # ------------------------------------------------------------------ 帧与收发
    def _write(self, obj: dict) -> int:
        with self._lock:
            self._next_id += 1
            if "id" not in obj:
                obj["id"] = self._next_id
            self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            return obj["id"]

    def _read_until(self, req_id: int) -> dict:
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise SemanticaUnavailable("Semantica 进程退出，未返回响应")
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("id") == req_id:
                return msg

    def call(self, name: str, arguments: dict | None = None, _method: bool = False):
        """调用 Semantica 工具；_method=True 用于协议方法（tools/list）。"""
        method = name if _method else "tools/call"
        params = arguments if _method else {"name": name, "arguments": arguments or {}}
        with self._lock:
            req_id = self._write({"jsonrpc": "2.0", "method": method, "params": params})
            resp = self._read_until(req_id)
        if "error" in resp:
            raise SemanticaUnavailable(f"{name} 失败: {resp['error'].get('message', resp['error'])}")
        return _unwrap_result(resp) if not _method else resp.get("result", {}).get("tools", [])

    def close(self):
        with self._lock:
            if self.proc is not None:
                proc, self.proc = self.proc, None
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                try:
                    proc.stdout.close()
                except Exception:
                    pass
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    pass

    # ------------------------------------------------------------------ 类型化适配
    def bootstrap_schema(self, diffs: list[dict]) -> dict:
        """从 Schema Diff 诱导本体草稿（Semantica 抽取 → OWL/SHACL/SKOS 形状）。

        返回契约与 ontology_schema.bootstrap_claim_ontology 的确定性分支一致：
        {bootstrapped, ontology, source}。
        """
        text = _diffs_to_text(diffs)
        entities = self.call("extract_entities", {"text": text}) if "extract_entities" in self.tool_names else []
        relations = self.call("extract_relations", {"text": text}) if "extract_relations" in self.tool_names else []
        ent_list = entities.get("entities", []) if isinstance(entities, dict) else (entities or [])
        rel_list = relations.get("relations", relations.get("triplets", [])) if isinstance(relations, dict) else (relations or [])

        classes = [dict(c) for c in _BASE_ONTOLOGY["classes"]]
        properties = [dict(p) for p in _BASE_ONTOLOGY["properties"]]
        vocabulary = [dict(v) for v in _BASE_ONTOLOGY["vocabulary"]]
        seen = {c["name"] for c in classes}

        for e in ent_list:
            if not isinstance(e, dict):
                continue
            name = (e.get("name") or e.get("entity") or e.get("label") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            classes.append({"name": name, "type": "owl:Class",
                            "description": e.get("type") or e.get("label") or "Semantica 诱导实体类"})
            vocabulary.append({"concept": name, "prefLabel": name,
                               "altLabels": e.get("aliases") or [], "kind": "semantica_induced"})

        for r in rel_list:
            if not isinstance(r, dict):
                continue
            pname = (r.get("predicate") or r.get("relation") or r.get("type") or "").strip().upper()
            if pname and not any(p["name"] == pname for p in properties):
                properties.append({"name": pname, "type": "owl:ObjectProperty"})

        return {"bootstrapped": True,
                "ontology": {"classes": classes, "properties": properties,
                             "constraints": [dict(c) for c in _BASE_ONTOLOGY["constraints"]],
                             "vocabulary": vocabulary},
                "source": "semantica"}

    def add_entity(self, node_id: str, label: str = "", node_type: str = "Concept", metadata: dict | None = None) -> dict:
        args = {"id": node_id, "type": node_type}
        if label:
            args["label"] = label
        if metadata:
            args["metadata"] = metadata
        return self.call("add_entity", args)

    def add_relationship(self, source: str, target: str, rel_type: str, metadata: dict | None = None) -> dict:
        args = {"source": source, "target": target, "type": rel_type}
        if metadata:
            args["metadata"] = metadata
        return self.call("add_relationship", args)

    def search_graph(self, query: str, node_type: str | None = None, limit: int = 20) -> dict:
        args = {"query": query}
        if node_type:
            args["node_type"] = node_type
        if limit:
            args["limit"] = limit
        if "search_graph" in self.tool_names:
            return self.call("search_graph", args)
        # 旧版 15 工具服务器：query_graph 的 search 模式
        qg = {"mode": "search", "query": query}
        if node_type:
            qg["node_type"] = node_type
        if limit:
            qg["limit"] = limit
        return self.call("query_graph", qg)

    def get_graph_summary(self) -> dict:
        return self.call("get_graph_summary", {})

    def export_graph(self, fmt: str = "json-ld") -> dict:
        return self.call("export_graph", {"format": fmt})

    def get_provenance(self, entity_id: str) -> dict:
        return self.call("get_provenance", {"entity_id": entity_id})

    def run_reasoning(self, facts: list[str]) -> dict:
        return self.call("run_reasoning", {"facts": facts})


# --------------------------------------------------------------------------- #
# 懒加载单例
# --------------------------------------------------------------------------- #
_client: SemanticaClient | None = None
_client_lock = threading.RLock()


def get_semantica_client() -> SemanticaClient | None:
    """懒启动单例；任何失败返回 None（调用方降级确定性规则）。"""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            try:
                _client = SemanticaClient().start()
            except Exception:
                _client = None
        return _client
