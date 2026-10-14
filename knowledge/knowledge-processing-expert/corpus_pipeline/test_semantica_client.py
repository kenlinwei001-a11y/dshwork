# -*- coding: utf-8 -*-
"""Semantica 桥接回归测试（预留接口落地）。

- Semantica 未部署/不可用时：全部 skip（不阻塞主链路）。
- 已部署时：用临时 KG 路径验证 handshake / bootstrap_schema / 图写入检索 / 导出，
  不污染正式图（~/.semantica/graph.json）。
"""
from __future__ import annotations
import os
import tempfile
import unittest

from .semantica_client import SemanticaClient, SemanticaUnavailable


def _client():
    tmp = os.path.join(tempfile.gettempdir(), f"kp-semantica-test-{os.getpid()}.json")
    try:
        c = SemanticaClient(kg_path=tmp)
        c.start()
        return c, tmp
    except SemanticaUnavailable as e:
        return None, str(e)
    except Exception as e:  # noqa: BLE001
        return None, str(e)


@unittest.skipUnless(_client()[0] is not None, "Semantica 未部署或不可用，跳过")
class SemanticaBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client, cls.tmp = _client()

    @classmethod
    def tearDownClass(cls):
        if cls.client is not None:
            cls.client.close()
        if os.path.exists(cls.tmp):
            os.remove(cls.tmp)

    def test_handshake(self):
        self.assertIsNotNone(self.client.protocol_version)
        self.assertGreaterEqual(len(self.client.tool_names), 1)

    def test_bootstrap_schema_shape(self):
        diffs = [{"kind": "added", "path": "claims", "detail": {"claim_type": "conclusion"}}]
        boot = self.client.bootstrap_schema(diffs)
        self.assertTrue(boot.get("bootstrapped"))
        self.assertEqual(boot.get("source"), "semantica")
        ont = boot["ontology"]
        for key in ("classes", "properties", "constraints", "vocabulary"):
            self.assertIn(key, ont)
        # 底座类/属性必须保留（与确定性分支同构）
        names = {c["name"] for c in ont["classes"]}
        self.assertIn("Claim", names)
        self.assertIn("Evidence", names)

    def test_graph_roundtrip(self):
        c = self.client
        c.add_entity("kp-test-node", "测试节点", "Concept", {"origin": "test"})
        c.add_relationship("kp-test-node", "Claim", "USES")
        summary = c.get_graph_summary()
        self.assertGreaterEqual(summary.get("node_count", 0), 1)
        found = c.search_graph("kp-test-node")
        self.assertTrue(isinstance(found, (dict, list)))
        self.assertNotIn("error", found if isinstance(found, dict) else {})

    def test_export_graph(self):
        exp = self.client.export_graph("json-ld")
        self.assertTrue(exp)


if __name__ == "__main__":
    unittest.main()
