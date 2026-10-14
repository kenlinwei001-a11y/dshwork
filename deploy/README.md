# deploy/ — 本地部署的补丁与模板

这个目录存在的理由：**本机部署里那些"只在本地、一升级就没"的改动，必须在这里有可重放的来源**，否则换机器、重装、升级之后就会静默失效——那是隐患，不是配置。

## 目录内容

| 路径 | 是什么 | 什么时候用 |
| --- | --- | --- |
| `patches/semantica-0.7.0-graph-analytics.patch` | 修 semantica 0.7.0 `get_graph_analytics` 的三个上游 bug | 装/升级 semantica 后 |
| `patches/dsh-mcp-connector-hide-sidebar-entry.patch` | 让 `dsh-mcp-connector` 不再往左侧栏塞「MCP连接器」入口 | **每次插件升级后** |
| `scripts/install-semantica-mcp.sh` | 建 venv + 装 semantica + 打补丁 + 生成连接器定义 | 新机器 / 升级 semantica |
| `scripts/reapply-local-patches.sh` | 重打"会被升级冲掉"的补丁（可重复执行） | `dsh plugin add/update` 或重装 profile 后 |
| `connectors/*.json` | MCP 连接器定义（部署里登记用） | 重建部署时 |
| `launchd/com.workdsh.preview.plist.template` | launchd 服务模板（含 `KeepAlive`，进程挂了会自动拉起） | 新机器 |

## 为什么这些补丁非打不可

**semantica 0.7.0 的三个硬 bug**（不修则 `get_graph_analytics` 必坏）：

1. `kg/centrality_calculator.py` 与 `kg/community_detector.py` 把 `graph.nodes`（字典属性）当函数调 → `'dict' object is not callable`
2. `mcp_server/__init__.py` 把 PageRank 的嵌套返回 `{centrality, rankings}` 当扁平结构排序 → `'<' not supported between 'dict' and 'list'`
3. 同文件：`edge_count` 读的是不存在的属性（恒 0）、`community_count` 数的是字典键个数（恒 4）——**不报错但数字是错的**

**`dsh-mcp-connector` 的侧栏入口**：插件支持的开关读的是设置命名空间 `mcp-connector`，而该命名空间在 dsh 0.2.0 下不被服务 ⇒ 客户端取不到值、按代码回落到"显示"。所以只能改包内默认值。

## 一条必须记住的规则

**同一个 `serverName` 只能出现在一处连接器存储里。** 本机有两套：

- `storages/workdsh_connectors/definitions/` —— 「专家·技能·连接器」→「连接器」页读这份
- `storages/mcp_connector.json` —— 「MCP连接器」弹窗（dsh 插件）读这份

两套都会真正拉起进程；同名同现 ⇒ 后注册的那个报 `serverName "X" is already in use`，且"谁赢"不确定（改了一份配置可能不生效）。新增 MCP 时先两边各查一遍。

## 复现一个完整部署的步骤

```bash
# 1. 代码
git clone <repo> && cd <repo> && bash knowledge/setup.sh

# 2. semantica MCP（含上游补丁）
bash deploy/scripts/install-semantica-mcp.sh

# 3. 把存档的配置装进部署：技能 / 专家 / MCP 连接器 / Agent 预设
#    —— 只克隆不跑这步，系统里看不到这些内容（deploy/config/ 只是存档，不会自动生效）
bash deploy/scripts/install-local-config.sh [DSH_HOME] [DSH_AGENTS_HOME]
#    脚本会把存档里写死的原作者路径改写成本机的；装完会告警哪些 MCP 的命令不存在

# 4. 服务：按 deploy/launchd/*.template 填好路径后放进 ~/Library/LaunchAgents/

# 5. 每次插件升级后
bash deploy/scripts/reapply-local-patches.sh
```

## 关于 deploy/config/

这里是**存档**，不是安装好的配置。三个必须知道的点：

- **必须跑 `install-local-config.sh` 才会生效**——文件在仓库里 ≠ 系统里有。
- 存档里含原作者机器的绝对路径（`/Users/apple/...`），安装脚本会按下列规则改写：
  `.../Desktop/workdsh`→ 当前仓库根、`.../workdsh/.test-runtime/preview`→ 目标 DSH_HOME、
  `.../.venvs/semantica`→ 本机 venv、`.../workdsh-mcp-servers`→ `$MCP_SERVERS_ROOT`。
- `experts/bindings/` **不安装**：那是按会话 ID 绑定的状态，换机器后对应会话不存在。
  `plugin-manifest/` **也不安装**：里面的 package.json 写的是本机缓存 tarball 的绝对路径，
  属于安装产物，应由 `preview:install` 流程重新生成。

### 会话记录（`../会话记录/`）是归档，不是可导入的会话

放进去的是原始 JSONL 文本。应用的会话列表读的是 `<DSH_HOME>/sessions/`，
所以**它们不会自动出现在界面的会话列表里**——要恢复某条会话上屏，需按应用格式放回
`<DSH_HOME>/sessions/<项目>/session-<id>/`（正文 `session.v4.jsonl.zstd`）
并在 `storages/session_projcache/sessions/` 补对应元数据；两者的 cwd 字段还需改成本机路径。
