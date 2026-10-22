# Windows 同事部署指南（WSL2 运行 + Windows 浏览器访问）

本机这套系统不在 Windows 原生跑：服务（dsh web + MCP + Python 流水线）跑在 WSL2 里，
同事用 Windows 浏览器访问 http://127.0.0.1:18989。
（仓库 deploy/WINDOWS-WSL.md 已说明：Windows 原生有 15 个文件不兼容，不建议。）

## 一条命令

普通 PowerShell（不需要管理员）：

~~~
cd <仓库目录>
powershell -ExecutionPolicy Bypass -File deploy/bootstrap-windows.ps1
~~~

它会：检查 WSL2/Ubuntu → 在 WSL 里执行 deploy/bootstrap-wsl.sh → 从 Windows 侧验证 → 打开浏览器。

常用变体：

| 目的 | 命令 |
| --- | --- |
| 指定分支/提交 | powershell -ExecutionPolicy Bypass -File deploy/bootstrap-windows.ps1 -Ref main |
| 换端口 | ... -Port 19000 |
| 小内存机器（WSL 分不到 8G） | ... -Heap 4096 |
| 只装不启动 | ... -NoStart |
| 顺带装 Ubuntu | ... -Install（之后要重启并设 Linux 用户名密码） |
| localhost 转发失效 | 管理员 PowerShell 加 -PortProxy |
| 顺带导入仓库自带会话 | ... -WithSessions |

仓库已在 WSL 里时，也可只在 WSL 终端跑：

~~~
bash deploy/bootstrap-wsl.sh --port 18989 --heap 8192
bash deploy/bootstrap-wsl.sh --dry-run          # 只打印计划
~~~

## 部署脚本做了什么（9 步，幂等可重跑）

1. 预检：系统 / Node（^22.19 或 >=24）/ python3（3.10-3.13）/ git / patch / curl
2. 仓库：已有就 fetch，没有就 clone，可指定 ref
3. Web：corepack + pnpm install --frozen-lockfile + pnpm build + preview:install（装 Profile）
4. 知识处理：knowledge/setup.sh 建 venv + 6 个基础技能
5. MCP 服务端程序包：install-mcp-servers.sh（filesystem / playwright）
6. semantica MCP：建 venv + 装包 + 打补丁
7. 存档导入：install-local-config.sh 装技能 / 专家 / MCP 定义 / Agent 预设，并把存档里的
   /Users/apple/... 改写成这台机器的路径
8. 本地补丁重放（可选）
9. 校验：数字（技能/专家/修订/预设/连接器）+ 逐条检查 MCP 命令是否存在 + 启动并探活

失败不会“假装成功”：每步打印真实输出，最后汇总 WARN 清单；加 --json 输出机器可读结果。

## 浏览器模式必须知道的 5 件事

1. 服务只监听 WSL 内的 127.0.0.1（start-preview.mjs 用 --host 127.0.0.1），
   Windows 浏览器靠 WSL2 的 localhostForwarding 访问。默认开启；配置文件是用户目录下的 .wslconfig：
   ~~~
   [wsl2]
   localhostForwarding=true
   ~~~
   打不开时先 wsl --shutdown 重开 WSL；仍不行就用 -PortProxy 建静态转发。
2. 端口冲突：Windows 侧 netstat -ano | findstr :18989 看占用；换端口用 -Port 19000。
3. 内存：preview 默认 Node 堆 8192 MB。WSL 默认最多拿宿主机一半内存，
   8G 机器建议 -Heap 4096，并在 .wslconfig 里限制 memory=6GB。
4. 上传文件落在 WSL 里：浏览器上传的附件/工作区文件在 /home/用户名/ 下，
   要读 Windows 文件用 /mnt/c/（跨盘 IO 慢，不建议把工作区放 /mnt）。
5. 宿主重启后要重新拉起：nohup 进程在 WSL 存活期间有效；Windows 重启后 WSL 会关。
   重跑一次部署脚本即可（幂等），或建计划任务：
   ~~~
   wsl.exe -d Ubuntu -- bash -lc "cd ~/workdsh && bash deploy/bootstrap-wsl.sh --no-build --no-start"
   ~~~

## 装完应该看到什么

| 检查 | 期望（当前仓库存档） |
| --- | --- |
| 技能 | 用户根 31 个 + Profile 根 5 个（共 36） |
| 专家 | 11 个 |
| MCP 连接器 | 8 个（filesystem / kp-assembly / kp-library / kp-processing / kp-reserved / kp-semantic / playwright / semantica） |
| Agent 预设 | 10 个（与已发布专家一一对应；1 个专家未发布故无预设） |
| 浏览器 | http://127.0.0.1:18989 可打开 |

## 脚本不会做的事（刻意）

- 不写模型 API Key：浏览器里按提示添加，或写 ~/.workdsh/preview/.credentials.yaml。
- 不替你授权 Tavily：需要在「MCP 连接器」里添加，然后浏览器里 OAuth。
- postgresql / tavily 属于 dsh 侧另一套存储，与 WorkDSH 连接器不是同一套，需单独添加。
- 不复制他人会话全集：仓库只带少量脱敏会话，加 -WithSessions 才导入。
- 存档会被时间甩开：deploy/config 已刷新到当前状态（11 专家 / 36 技能 / 10 预设），
  但以后你再新建或改动专家、技能，存档不会自动更新。推送前请重跑：
  ~~~
  bash deploy/scripts/export-local-config.sh            # 导出当前状态
  bash deploy/scripts/export-local-config.sh --check    # 只看是否过期（0=一致 1=过期）
  ~~~

## 故障排查

| 现象 | 处理 |
| --- | --- |
| wsl 报找不到发行版 | wsl --install -d Ubuntu，或加 -Install |
| 打不开页面 | 先在 WSL 里 curl http://127.0.0.1:18989/ 确认服务本身通 |
| WSL 内通、Windows 打不开 | 用户目录 .wslconfig 的 localhostForwarding；或管理员加 -PortProxy |
| 页面能开但对话一直转圈 | 浏览器 WebSocket 被代理/防火墙拦；关掉 VPN/代理再试 |
| 提示添加 API Key | 正常，填自己的 key |
| install-local-config.sh 报「命令不存在」 | 对应 MCP 依赖没装：重跑并在 --skip 里不要带 mcp-servers / semantica |
| pnpm preview:install 失败 | 查 Node 版本（需 ^22.19 或 >=24）与 corepack 是否要 sudo |
| 端口被占 | -Port 19000，或 netstat -ano | findstr :18989 找占用进程 |

## 最小验证清单（交给同事自己跑）

~~~
# WSL 内
find ~/.agents/skills -maxdepth 2 -name SKILL.md | wc -l
ls ~/.workdsh/preview/storages/workdsh_experts/experts | wc -l
ls ~/.workdsh/preview/storages/workdsh_connectors/definitions | wc -l

# Windows PowerShell
Invoke-WebRequest http://127.0.0.1:18989/ -UseBasicParsing | Select-Object StatusCode
~~~
