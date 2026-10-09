# -*- coding: utf-8 -*-
"""运行时 + 治理层验证（对齐智演装配引擎 V3/V5 阶段）。

覆盖：权限校验、Skill 注册/校验/执行、MCP 工具路由、DAG 执行/重试/恢复、版本发布/回滚、审计。

运行：.venv/bin/python corpus_pipeline/test_runtime.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus_pipeline.runtime import (
    check_access, AuditService, SkillRegistry, MCPToolRouter, DAGRuntime, AssetPublisher,
)


def test_check_access():
    policies = {"ontology": {"read": ["editor", "*"], "write": ["admin"]}}
    assert check_access("editor", "ontology", "read", policies)["allowed"] is True
    assert check_access("editor", "ontology", "write", policies)["allowed"] is False  # 无写权限
    assert check_access("admin", "ontology", "write", policies)["allowed"] is True
    assert check_access("guest", "unknown", "read", policies)["allowed"] is False  # 默认拒绝
    print("[OK] check_access：允许/拒绝/默认拒绝（fail-closed）")


def test_audit_service():
    audit = AuditService()
    audit.record("publish", project_id="NEW", version="1.0")
    audit.record("publish", project_id="NEW", version="2.0")
    audit.record("rollback", project_id="NEW")
    assert len(audit.list_events()) == 3
    assert len(audit.list_events("publish")) == 2
    print("[OK] AuditService：追加记录 + 按类型过滤")


def test_skill_registry():
    audit = AuditService()
    reg = SkillRegistry(audit=audit)
    reg.register("claim_validate", lambda a: {"claims_checked": len(a["claims"])},
                 input_schema={"required": ["claims"]},
                 permissions={"execute": ["writer"]})
    # 输入校验：缺必填参数
    assert reg.validate_input("claim_validate", {})["ok"] is False
    # 执行成功
    r = reg.execute("claim_validate", {"claims": [{"id": "C1"}]}, identity="writer")
    assert r["ok"] and r["result"]["claims_checked"] == 1
    # 权限拒绝
    r2 = reg.execute("claim_validate", {"claims": []}, identity="guest")
    assert r2["ok"] is False and "无权限" in r2["reason"]
    # 未注册
    assert reg.execute("nope", {})["ok"] is False
    print("[OK] SkillRegistry：输入校验 + 执行 + 权限拒绝 + 未注册")


def test_mcp_tool_router():
    router = MCPToolRouter()
    router.register("graph.query", lambda a: {"nodes": 3}, permissions={"invoke": ["analyst"]})
    assert router.invoke("graph.query", {}, identity="analyst")["ok"] is True
    assert router.invoke("graph.query", {}, identity="guest")["ok"] is False
    assert "graph.query" in router.list_tools()
    print("[OK] MCPToolRouter：调用 + 权限拒绝 + 工具清单")


def test_dag_runtime():
    log = []
    tasks = [
        {"id": "a", "deps": [], "desc": "a"},
        {"id": "b", "deps": ["a"], "desc": "b"},
        {"id": "c", "deps": ["b"], "desc": "c"},
    ]
    rt = DAGRuntime()
    r = rt.run(tasks, lambda t: (log.append(t["id"]) or f"result-{t['id']}"))
    assert r["ok"] and r["done"] == 3 and log == ["a", "b", "c"]
    print("[OK] DAGRuntime：拓扑执行 a→b→c")


def test_dag_runtime_retry():
    attempts = {"count": 0}

    def flaky(task):
        if task["id"] == "b" and attempts["count"] == 0:
            attempts["count"] += 1
            raise RuntimeError("临时失败")
        return "ok"

    tasks = [{"id": "a", "deps": []}, {"id": "b", "deps": ["a"]}]
    rt = DAGRuntime()
    r = rt.run(tasks, flaky, max_retries=1)
    assert r["ok"] and r["state"]["b"]["status"] == "done" and r["state"]["b"]["retries"] == 1
    print("[OK] DAGRuntime：失败重试 1 次后成功")


def test_dag_runtime_skip_downstream():
    def fail_b(task):
        if task["id"] == "b":
            raise RuntimeError("硬失败")
        return "ok"

    tasks = [{"id": "a", "deps": []}, {"id": "b", "deps": ["a"]}, {"id": "c", "deps": ["b"]}]
    rt = DAGRuntime()
    r = rt.run(tasks, fail_b)
    assert r["ok"] is False and "b" in r["failed"] and "c" in r["skipped"]  # 下游跳过
    print("[OK] DAGRuntime：依赖失败 → 下游 skipped（不执行）")


def test_dag_runtime_resume():
    def ok_if_a_ok(task):
        if task["id"] == "b" and rt_resume["flag"] == 0:
            rt_resume["flag"] = 1
            raise RuntimeError("第一次失败")
        return "ok"

    rt_resume = {"flag": 0}
    tasks = [{"id": "a", "deps": []}, {"id": "b", "deps": ["a"]}]
    rt = DAGRuntime()
    rt.run(tasks, ok_if_a_ok)
    assert rt._state["b"]["status"] == "failed"
    r2 = rt.resume(tasks, ok_if_a_ok)
    assert r2["ok"] and rt._state["b"]["status"] == "done"
    print("[OK] DAGRuntime：resume 从失败任务恢复")


def test_asset_publisher():
    audit = AuditService()
    pub = AssetPublisher(audit=audit)
    b1 = {"project_id": "NEW", "version": "1.0", "content_hash": "h1", "published": False}
    # 无审批人 → 拒绝发布
    assert pub.publish(b1)["ok"] is False
    # 审批发布
    r = pub.publish(b1, approved_by="admin")
    assert r["ok"] and r["bundle"]["published"] is True and r["bundle"]["approved_by"] == "admin"
    # 发布 v2，再回滚
    b2 = {"project_id": "NEW", "version": "2.0", "content_hash": "h2", "published": False}
    pub.publish(b2, approved_by="admin")
    assert pub.current("NEW")["version"] == "2.0"
    rb = pub.rollback("NEW")
    assert rb["ok"] and pub.current("NEW")["version"] == "1.0"
    # 审计事件
    assert len(audit.list_events("publish")) == 2 and len(audit.list_events("rollback")) == 1
    print("[OK] AssetPublisher：审批发布 + 版本回滚 + 审计")


def main() -> int:
    test_check_access()
    test_audit_service()
    test_skill_registry()
    test_mcp_tool_router()
    test_dag_runtime()
    test_dag_runtime_retry()
    test_dag_runtime_skip_downstream()
    test_dag_runtime_resume()
    test_asset_publisher()
    print("\n运行时 + 治理层验证通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
