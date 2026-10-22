# Windows 上完整复刻本机环境（WSL2 方案）

本机这套 `deploy/` 是按 macOS 写的：MCP 配置里是 `/Users/apple/...`、`/usr/local/bin/node`、
`.venv/bin/python`、`/bin/sh`，服务用 launchd 启动。Windows 原生直接跑会有 15 个文件不兼容。

最稳的做法是在 Windows 上装 **WSL2 + Ubuntu**，把应用、技能、专家、MCP、semantica、
知识处理流水线都放在 Linux 环境里，Windows 浏览器访问 `http://127.0.0.1:18989`。
这样不用把 Python/MCP 逐个移植到 Windows。

## 0. 安装 WSL2

Windows 管理员 PowerShell：

```powershell
wsl --install -d Ubuntu
```

重启，设置 Linux 用户名和密码。之后所有命令都在 Ubuntu 终端里执行。

## 1. 基础依赖

```bash
sudo apt update
sudo apt install -y git curl build-essential patch python3 python3-venv python3-dev
# Node 22（应用要求 ^22.19.0 或 >=24）
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
sudo corepack enable
```

可选：浏览器自动化要 Chrome：

```bash
sudo apt install -y chromium-browser   # 或按 Playwright 文档装 chrome
```

## 2. 克隆仓库

```bash
mkdir -p ~/workdsh && cd ~/workdsh
git clone https://github.com/kenlinwei001-a11y/dshwork.git .
git checkout aad55a0777   # 或更新的 main
```

## 3. 安装 Web 预览与 profile

```bash
cd ~/workdsh/apps/web
corepack pnpm install --frozen-lockfile
corepack pnpm build
```

先不要启动。数据恢复完再启动。

## 4. 装 MCP 服务端程序包

```bash
bash ~/workdsh/deploy/scripts/install-mcp-servers.sh
mkdir -p ~/mcp-workspace
```

装到 `~/workdsh-mcp-servers`（playwright / filesystem 的 npm 包）。

## 5. 装 semantica（带本机 3 个补丁）

```bash
cd ~/workdsh
SEMANTICA_PYTHON=python3 bash deploy/scripts/install-semantica-mcp.sh
```

脚本会建 `~/.venvs/semantica`、装 `semantica[graph-embeddings]`、打
`deploy/patches/semantica-0.7.0-graph-analytics.patch`，并准备 `~/.semantica/graph.json`。
Ubuntu 的 Python 3.10–3.12 都可以；如果 `python3.11` 不存在就用 `python3`。

## 6. 建知识处理 venv 和技能

```bash
cd ~/workdsh/knowledge
bash setup.sh
```

这会建 `knowledge/knowledge-processing-expert/.venv` 并装依赖，同时把 6 个基础 skill
装到 `~/.agents/skills`。其余技能由下一步的 `install-local-config.sh` 从
`deploy/config/skills` 全量安装。

## 7. 恢复对话和数据

先停掉应用（如果启动过），然后按基础包 + 增量包的 README 恢复。WSL 里路径示例：

```bash
export DSH_HOME="$HOME/.workdsh/preview"
export AGENTS_HOME="$HOME/.agents"
export REPO="$HOME/workdsh"
```

恢复基础包、跑 `retarget.sh`、覆盖增量包、跑 `retarget-sessions.mjs`。
`retarget.sh` 会把 `/Users/apple/...` 改成 WSL 路径，并重命名会话目录。
这一步同时恢复了最新的专家、技能和会话状态，所以下一步不要覆盖专家。

## 8. 安装技能 / MCP 定义（保留已恢复的专家状态）

```bash
cd ~/workdsh
SKIP_EXPERTS=1 bash deploy/scripts/install-local-config.sh "$DSH_HOME" "$AGENTS_HOME"
```

它会：

- 把 `deploy/config/skills` 下 30+ 个技能装到 `$AGENTS_HOME/skills`；
- 把 8 个 MCP 定义装到 `$DSH_HOME/storages/workdsh_connectors/definitions`；
- 把存档里的 `/Users/apple/...` 改写成 WSL 路径，并把 `/usr/local/bin/node`、
  `/usr/local/bin/python3.11` 改成 WSL 里实际的 node/python；
- `SKIP_EXPERTS=1` 保留第 7 步恢复出来的最新专家和 Agent 预设，不用仓库里的旧存档覆盖；
- 自检命令是否存在，缺依赖会明确告警。

## 9. 重装 profile 并单独配置凭据

```bash
cd ~/workdsh/apps/web
WORKDSH_PREVIEW_HOME="$HOME/.workdsh/preview" \
DSH_AGENTS_HOME="$HOME/.agents" \
corepack pnpm preview:install

"$HOME/dsh-migration/base-branch/migration-20261019/base-package/credentials/configure-credentials.sh" \
  "$HOME/.workdsh/preview"
```

## 10. 启动

```bash
cd ~/workdsh/apps/web
WORKDSH_PREVIEW_HOME="$HOME/.workdsh/preview" \
DSH_AGENTS_HOME="$HOME/.agents" \
WORKDSH_PREVIEW_PORT=18989 \
corepack pnpm preview
```

Windows 浏览器打开 `http://127.0.0.1:18989`。

如果没有自动转发端口，在 Windows 管理员 PowerShell 里查 WSL IP 并加端口代理：

```powershell
wsl hostname -I
netsh interface portproxy add v4tov4 listenport=18989 listenaddress=127.0.0.1 connectport=18989 connectaddress=<WSL_IP>
```

## 11. 验证 MCP / semantica

```bash
pgrep -af semantica.mcp_server
pgrep -af kp_processing_server
pgrep -af '@playwright/mcp'
```

界面「专家·技能·连接器」里能看到全部技能、专家和 MCP 连接器；
「MCP连接器」弹窗里的 postgresql / tavily 属于 dsh 侧另一套存储，需要在界面里单独添加，
Tavily 还需要在浏览器里重新授权。

## 已知限制

- Playwright MCP 需要 WSL 里有 Chrome/Chromium；没有就先禁用该连接器。
- WSL 关闭后服务会停；要用 systemd 或 `nohup` 常驻。
- 这套方案不依赖 Windows 原生 Python/MCP，所以不需要改那 15 个 macOS 文件。
- 如果坚持 Windows 原生，需要把 8 个 MCP 配置、5 个 bash 脚本和 launchd 逐个移植，
  且部分 Python 代码仍要真机验证；不建议。
