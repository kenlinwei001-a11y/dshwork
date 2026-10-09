# -*- coding: utf-8 -*-
"""运行时 + 治理层（对齐智演装配引擎 V3/V5 阶段）。

组件：
  check_access    —— 权限校验（governance.check_access，默认拒绝 fail-closed）
  SkillRegistry   —— Skill 加载/输入校验/执行（validateSkillInput / executeSkill）
  MCPToolRouter   —— 工具发现/权限校验/调用（invokeTool）
  DAGRuntime      —— DAG 拓扑执行/重试/恢复（runWorkflow / resumeWorkflow）
  AssetPublisher  —— 版本发布/审批/回滚（publishBundle / rollbackBundle）
  AuditService    —— 审计事件流（recordEvent，不可变追加）
"""
from __future__ import annotations

from .orchestrator import topological_order


# --------------------------------------------------------------------------- #
# 权限校验（governance.check_access）
# --------------------------------------------------------------------------- #
def check_access(identity: str, resource: str, operation: str, policies: dict) -> dict:
    """权限校验：identity 是否对 resource 有 operation 权限。

    policies: {resource: {operation: [allowed_identities]}}；"*" 表示放行所有。
    返回 {allowed, reason}。默认拒绝（fail-closed）。
    """
    res_policy = policies.get(resource, {})
    allowed = res_policy.get(operation, [])
    if identity in allowed or "*" in allowed:
        return {"allowed": True}
    return {"allowed": False, "reason": f"{identity} 无权限对 {resource} 执行 {operation}"}


# --------------------------------------------------------------------------- #
# AuditService（审计事件流，不可变追加）
# --------------------------------------------------------------------------- #
class AuditService:
    def __init__(self):
        self._events: list[dict] = []

    def record(self, event_type: str, **kwargs) -> dict:
        ev = {"event_type": event_type, **kwargs}
        self._events.append(ev)
        return {"event_id": len(self._events), "event": ev}

    def list_events(self, event_type: str | None = None) -> list[dict]:
        if event_type is None:
            return list(self._events)
        return [e for e in self._events if e["event_type"] == event_type]


# --------------------------------------------------------------------------- #
# SkillRegistry（Skill 加载/输入校验/执行）
# --------------------------------------------------------------------------- #
class SkillRegistry:
    def __init__(self, audit: AuditService | None = None):
        self._skills: dict = {}
        self.audit = audit

    def register(self, name, execute, input_schema=None, version="1.0", permissions=None):
        """注册 Skill：execute 为 callable(args)→result。"""
        self._skills[name] = {
            "name": name, "version": version, "execute": execute,
            "input_schema": input_schema or {}, "permissions": permissions or {},
        }

    def list_skills(self) -> dict:
        return {n: {"name": s["name"], "version": s["version"]} for n, s in self._skills.items()}

    def validate_input(self, name: str, args: dict) -> dict:
        if name not in self._skills:
            return {"ok": False, "reason": f"Skill 未注册：{name}"}
        required = self._skills[name]["input_schema"].get("required", [])
        missing = [f for f in required if f not in args]
        if missing:
            return {"ok": False, "reason": f"缺少必填参数：{missing}"}
        return {"ok": True}

    def execute(self, name: str, args: dict, identity: str = "system") -> dict:
        """权限校验 → 输入校验 → 执行，返回 {ok, result|reason, skill, version}。"""
        if name not in self._skills:
            return {"ok": False, "reason": f"Skill 未注册：{name}"}
        skill = self._skills[name]
        access = check_access(identity, name, "execute", {name: skill["permissions"]})
        if not access["allowed"]:
            return {"ok": False, "reason": access["reason"]}
        v = self.validate_input(name, args)
        if not v["ok"]:
            return {"ok": False, "reason": v["reason"]}
        result = skill["execute"](args)
        if self.audit:
            self.audit.record("skill_execute", skill=name, identity=identity, version=skill["version"])
        return {"ok": True, "result": result, "skill": name, "version": skill["version"]}


# --------------------------------------------------------------------------- #
# MCPToolRouter（工具发现/权限校验/调用）
# --------------------------------------------------------------------------- #
class MCPToolRouter:
    def __init__(self, audit: AuditService | None = None):
        self._tools: dict = {}
        self.audit = audit

    def register(self, name, execute, input_schema=None, permissions=None):
        self._tools[name] = {
            "name": name, "execute": execute,
            "input_schema": input_schema or {}, "permissions": permissions or {},
        }

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def invoke(self, name: str, args: dict, identity: str = "system") -> dict:
        """权限校验 → 调用工具，返回 {ok, result|reason}。"""
        if name not in self._tools:
            return {"ok": False, "reason": f"工具未注册：{name}"}
        tool = self._tools[name]
        access = check_access(identity, name, "invoke", {name: tool["permissions"]})
        if not access["allowed"]:
            return {"ok": False, "reason": access["reason"]}
        result = tool["execute"](args)
        if self.audit:
            self.audit.record("tool_invoke", tool=name, identity=identity)
        return {"ok": True, "result": result}


# --------------------------------------------------------------------------- #
# DAGRuntime（DAG 拓扑执行/重试/恢复）
# --------------------------------------------------------------------------- #
class DAGRuntime:
    def __init__(self, audit: AuditService | None = None):
        self._state: dict = {}
        self.audit = audit

    def run(self, tasks: list[dict], executor, max_retries: int = 0) -> dict:
        """按拓扑顺序执行任务 DAG。executor(task)->result；抛异常视为失败。

        依赖失败/跳过时，下游任务标记 skipped（不执行）。
        返回 {ok, done, failed, skipped, state}。
        """
        topo = topological_order(tasks)
        if not topo["ok"]:
            return {"ok": False, "reason": topo.get("reason", "循环依赖"), "state": {}}
        order = topo["order"]
        self._state = {t["id"]: {"status": "pending", "result": None, "retries": 0} for t in tasks}
        task_of = {t["id"]: t for t in tasks}

        for tid in order:
            task = task_of[tid]
            deps_bad = [d for d in task.get("deps", []) if self._state.get(d, {}).get("status") != "done"]
            if deps_bad:
                self._state[tid] = {"status": "skipped", "reason": f"依赖未完成：{deps_bad}", "retries": 0}
                continue
            for attempt in range(max_retries + 1):
                try:
                    result = executor(task)
                    self._state[tid] = {"status": "done", "result": result, "retries": attempt}
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == max_retries:
                        self._state[tid] = {"status": "failed", "reason": str(e), "retries": attempt}
                    else:
                        self._state[tid] = {"status": "retrying", "reason": str(e), "retries": attempt + 1}

        done = sum(1 for s in self._state.values() if s["status"] == "done")
        failed = [t for t, s in self._state.items() if s["status"] == "failed"]
        skipped = [t for t, s in self._state.items() if s["status"] == "skipped"]
        if self.audit:
            self.audit.record("dag_run", done=done, failed=failed, skipped=skipped)
        return {"ok": not failed, "done": done, "failed": failed, "skipped": skipped, "state": dict(self._state)}

    def resume(self, tasks: list[dict], executor) -> dict:
        """从失败/跳过的任务恢复：重新执行 failed + skipped 的任务。"""
        retryable = {t["id"] for t in tasks
                     if self._state.get(t["id"], {}).get("status") in ("failed", "skipped", "retrying")}
        if not retryable:
            return {"ok": True, "done": 0, "resumed": [], "reason": "无可恢复任务"}
        # 只重跑失败/跳过任务（依赖若已 done 则保留）
        for tid in retryable:
            task = next(t for t in tasks if t["id"] == tid)
            try:
                self._state[tid] = {"status": "done", "result": executor(task), "retries": 0}
            except Exception as e:  # noqa: BLE001
                self._state[tid] = {"status": "failed", "reason": str(e), "retries": 0}
        failed = [t for t in retryable if self._state[t].get("status") == "failed"]
        return {"ok": not failed, "done": len(retryable) - len(failed), "resumed": list(retryable), "failed": failed}


# --------------------------------------------------------------------------- #
# AssetPublisher（版本发布/审批/回滚）
# --------------------------------------------------------------------------- #
class AssetPublisher:
    def __init__(self, audit: AuditService | None = None):
        self._published: dict = {}   # project_id → 当前已发布 bundle
        self._history: dict = {}     # project_id → [历史版本]
        self.audit = audit

    def publish(self, bundle: dict, approved_by: str | None = None) -> dict:
        """发布 bundle（置 published=True）。必须经审批人确认。"""
        if approved_by is None:
            return {"ok": False, "reason": "发布需审批人确认（approved_by 不能为空）"}
        b = dict(bundle)
        b["published"] = True
        b["approved_by"] = approved_by
        pid = b["project_id"]
        if pid in self._published:
            self._history.setdefault(pid, []).append(self._published[pid])
        self._published[pid] = b
        if self.audit:
            self.audit.record("publish", project_id=pid, version=b["version"], approved_by=approved_by)
        return {"ok": True, "bundle": b}

    def rollback(self, project_id: str) -> dict:
        """回滚到上一个已发布版本。"""
        if project_id not in self._history or not self._history[project_id]:
            return {"ok": False, "reason": "无历史版本可回滚"}
        prev = self._history[project_id].pop()
        current = self._published.get(project_id)
        self._published[project_id] = prev
        if self.audit:
            self.audit.record("rollback", project_id=project_id,
                              from_version=(current or {}).get("version"),
                              to_version=prev.get("version"))
        return {"ok": True, "bundle": prev}

    def current(self, project_id: str) -> dict | None:
        return self._published.get(project_id)
