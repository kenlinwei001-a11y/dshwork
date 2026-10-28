# 审计事件归档与保留方案

## 为什么需要

`<DSH_HOME>/storages/workdsh_audit/events/` **每个审计事件一个 JSON 文件**。
持续使用后文件数会线性增长（2026-10-26 实测 67,476 个、约 263MB）。
文件数过大时，启动扫描/文件句柄会与系统上限冲突（曾触发 `EMFILE`）。

## 当前策略

- **live 保留 30 天**：最近 30 天的审计事件继续留在
  `<DSH_HOME>/storages/workdsh_audit/events/`
- **更早的按月份归档**：打包到 `~/Desktop/workdsh-audit-archive/`
  - 文件名：`workdsh-audit-<YYYY-MM>-<时间戳>.tar.gz`
  - 每次归档写 `MANIFEST-<时间戳>.json`（文件数、大小、SHA-256）
  - 只有 tar 回读校验通过后才从 live 删除
- 无法解析时间的文件、读取失败的文件一律保留，不删除
- 每日 03:17 自动执行一次（LaunchAgent `com.workdsh.audit-archive`）

## 脚本

```bash
# 预览（默认就是 dry-run）
python3 deploy/scripts/archive-audit-events.py --dry-run

# 实际归档
python3 deploy/scripts/archive-audit-events.py --apply

# 改保留天数 / 改归档位置
python3 deploy/scripts/archive-audit-events.py --apply --keep-days 14 \
  --archive-dir "$HOME/Desktop/workdsh-audit-archive"
```

## 恢复某个归档

```bash
tar -xzf ~/Desktop/workdsh-audit-archive/workdsh-audit-2026-09-*.tar.gz \
  -C <DSH_HOME>/storages/workdsh_audit/events
```

归档只影响审计历史在界面里的可见范围；恢复后事件会重新出现在审计列表中。

## 文件句柄上限

审计文件数与 DSH_HOME 总文件数较大，`com.workdsh.preview` 已设置：

- `SoftResourceLimits` / `HardResourceLimits`：`NumberOfFiles = 200000`
- 系统级 `kern.maxfiles = 400000`、`kern.maxfilesperproc = 200000`
- 持久化 LaunchDaemon：`/Library/LaunchDaemons/com.workdsh.fdlimits.plist`

如果以后审计/项目文件继续增长，优先调整 `--keep-days` 或进一步归档项目缓存，
不要只依赖提高句柄上限。
