# dsh-task-dag（LGDMps fork）本机部署记录

- 上游：https://github.com/LGDMps/dsh-task-dag
- 版本：0.2.0（MIT，见同目录 LICENSE）
- 本机 DSH：0.2.1-rc.2；WorkDSH preview profile

## 安装方式

本机 `preview:install` 的 pnpm 依赖解析会卡死（GitHub 依赖 + 锁等待），因此采用手工安装：

1. 把本目录复制到 `<DSH_HOME>/profiles/preview/node_modules/dsh-task-dag`
2. 在 profile 的 `package.json` 中加入依赖 `"dsh-task-dag": "file:<本目录或缓存路径>"`
3. 把 `"dsh-task-dag"` 加入 `dsh.profile.bundles`
4. 重启 preview（SIGTERM supervisor，launchd 自动拉起）

## 本地兼容补丁（rc.2）

该 fork 按 DSH 0.2.1-rc.3 验证；rc.2 的 `dsh-tools` 校验器不支持 JSON Schema 的
`type` 数组（如 `['string','null']`），会导致 Agent 工具注册失败（宿主其他面仍可用）。

`rc2-schema.patch` 在 `src/tools.js` 的工具注册前加入归一化：把
`type: ['X','null']` 转成 `const oneOf = [{type:'X'},{type:'null'}]` 等价的 oneOf 形式。
补丁只改 schema 形状，不改工具语义。

**注意**：重新安装或升级插件会覆盖 `src/tools.js`，需要重新应用 `rc2-schema.patch`；
原始文件备份在部署时的 `/tmp/tools.js.pre-rc2-patch`（临时目录，可能被清理）。
