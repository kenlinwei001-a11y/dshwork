# 任务图谱数据存档

来源：WorkDSH preview 运行时（2026-11-03）

- 工作区：`团队知识库`
- workspaceId：`ba4adf2e-0277-4fb4-9180-760f4f6087f7`
- 原路径：`<DSH_HOME>/workdsh-projects/1667349c74609b4500654ac978662087a947e3f197112fe62706d819b8d081f0`
- 快照：revision 187，updatedAt 2026-11-03T11:38:55.703Z，35 个节点 / 32 条边

## 文件

- `graph.json`：任务图（节点、条件、边、里程碑）
- `events.jsonl`：该图的追加事件/审计流

## 恢复

把 `graph.json` 与 `events.jsonl` 复制到目标 workspace 的 `.dsh-task-graph/` 目录，
然后刷新页面或重启 preview。插件本身见 `deploy/plugins/dsh-task-dag/`。
