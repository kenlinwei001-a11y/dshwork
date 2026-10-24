# 专家预设完整性规则（防 experts/package-drift）

## 为什么会出现 package-drift

专家发布后，平台会生成两样东西：

- 冻结修订：`<DSH_HOME>/storages/workdsh_experts/revisions/<expert>_rev-<id>.json` 里的 `packageDocuments` / `packageAssets`
- 编译预设：`<AGENTS_HOME>/.workdsh-state/experts/presets/<preset>/expert-package/`

会话创建时会绑定一个修订和预设。之后每个回合执行前，守卫都会把预设目录里的文件与冻结修订逐字符/逐字节比对。只要预设目录被手工改过、部分覆盖过，或从别处拷入了不同版本，比对就会失败并报：

```text
experts/package-drift
```

这不是“偶发错误”，而是**受保护的不可变产物被修改**的信号。

## 必须遵守

1. 不要手工编辑或部分覆盖 `~/.agents/.workdsh-state/experts/presets/**`。
2. 不要手工编辑已发布的 `storages/workdsh_experts/revisions/*.json`。已发布修订是不可变的。
3. 要修改专家：走专家管理器的「草稿 → 校验 → 发布」流程。发布会生成新的修订和预设。
4. 当前会话绑定的是创建时的修订，**不会**自动切换到新发布版本。需要使用新内容的，新开任务。
5. 同一个专家同一时间只让一个 Agent/人编辑，避免两个流程同时改草稿/预设。
6. 同步、备份、迁移时，专家状态要**整体**恢复；不要把 preset 目录排除后单独拷、也不要只恢复其中几个文件。恢复后必须跑巡检。
7. 如果使用同步盘/备份工具，避免让它把旧版本的预设文件“还原”覆盖到 `.workdsh-state`；要么整体同步，要么排除该目录。

## 巡检

在仓库根目录运行：

```bash
node deploy/scripts/check-expert-presets.mjs
# 可显式指定：
node deploy/scripts/check-expert-presets.mjs --home "$DSH_HOME" --agents "$AGENTS_HOME"
```

- 输出每个带包修订的 `OK` / `DRIFT`，并标出绑定它的会话
- 退出码 0 = 全部一致；1 = 有 drift；2 = 参数/读取错误
- 建议在每次发布、迁移、恢复或修改专家后运行；也可以放进启动前的检查流程

## 发现 drift 的处置

1. 先停掉可能正在写预设目录的 Agent/编辑器/同步进程。
2. 运行上面的巡检，确认具体是哪个修订、哪个文件。
3. 如果内容应当等于已发布修订：把预设目录恢复成修订里的原内容（逐字符/逐字节一致），不要混用两个版本。
4. 如果确实想保留手工改的内容：不要改预设目录，改为在专家管理器里更新草稿并发布新修订，然后新开任务使用它。
5. 旧会话继续用它绑定的旧修订；不要试图通过改预设目录让旧会话“升级”。
