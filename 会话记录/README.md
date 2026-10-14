# 会话记录

存放要归档／交接的会话。**两种形态，用途不同**：

| 形态 | 长什么样 | 能不能在应用里看到 |
| --- | --- | --- |
| 归档（单文件 `.jsonl`） | 一份原始文本 | ❌ 只是文本，应用不读它 |
| **bundle（目录）** | `manifest.json` + `session.v4.jsonl` + `session.meta.json` + `files/` | ✅ 用 `import-session.sh` 导进去后，会话列表里就有 |

## 当前内容

| 条目 | 形态 | 来源 | 说明 |
| --- | --- | --- | --- |
| `2026-10-13-部署与补丁-4c53a782.jsonl` | 归档 | Claude Code | 本机部署与补丁那轮的过程。**已脱敏**：LLM API Key / 会话令牌 / GitHub PAT 一律替换为 `<REDACTED-*>` |
| `2026-10-13-可研报告处理为资产域并打包/` | **bundle** | WorkDSH 应用 | 含会话正文、元数据，以及它产出的文档（资产域包 ZIP、知识资产 ZIP、交付物/） |

## 怎么用

**导出**（在有这条会话的机器上）：

```bash
bash deploy/scripts/export-session.sh <session-id> <输出目录> --files <要一起带的项目条目>...
```

**导入**（在对方的机器上，装完系统之后）：

```bash
bash deploy/scripts/import-session.sh "会话记录/2026-10-13-可研报告处理为资产域并打包"
# 默认写进 ~/workdsh/.test-runtime/preview；换地方就加第二个参数
# 先看会做什么而不落盘：DRY_RUN=1 bash deploy/scripts/import-session.sh ...
```

导入脚本会做四件事：**改写路径**（原作者的 DSH_HOME → 本机）、**按应用的编码规则**放正文目录
（`sessions/<cwd 把 / 换成 - 并加 -->/session-<id>/session.v4.jsonl.zstd`）、**补元数据**
（`storages/session_projcache/sessions/session-<id>.json`）、**还原产出的文档**到会话的工作目录。

## 三条必须知道的

1. **直接拷文件进去不会上屏。** 会话目录名是按 cwd 编码的、元数据另存一处、路径还是原作者的——
   这就是 `import-session.sh` 存在的理由。
2. **本仓库是 public**，含凭据的记录必须先脱敏；替换后要**复扫确认真密钥残留为 0**，
   并且要有"必然命中"的对照项（扫不出东西 ≠ 没有）。
3. **旧会话的 cwd 指回本机路径。** 导入后会话的工作目录是脚本新建的；原项目里的其他中间产物
   不会自动带过来，需要的话用 `--files` 一起导出。
