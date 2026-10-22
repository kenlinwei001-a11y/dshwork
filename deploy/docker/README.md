# Docker 部署（浏览器模式）

把整套环境封进镜像：Node + apps/web 构建产物 + 知识处理 venv + MCP 程序包 + semantica venv。
数据（专家/技能/项目/会话/日志）放在命名卷 /data，容器升级不丢数据。

## 最快路径

~~~bash
# 仓库根目录
docker compose -f deploy/docker/docker-compose.yml up -d --build

# 看日志（首次会导入存档，约 30-90 秒）
docker compose -f deploy/docker/docker-compose.yml logs -f
~~~

取登录链接（含令牌）：

~~~bash
docker compose -f deploy/docker/docker-compose.yml exec workdsh cat /data/dsh/login-url.txt
# 或
docker compose -f deploy/docker/docker-compose.yml logs workdsh | grep -o 'http://[^ ]*token=[A-Za-z0-9_-]*' | tail -1
~~~

浏览器打开（默认只发布到宿主机回环，安全）：

    http://127.0.0.1:18989/?token=<上面的令牌>

要让同事访问，两种做法：

1. **宿主机 nginx 反代 + HTTPS**（推荐）：把 deploy/nginx/workdsh.conf.template 装到宿主机，proxy_pass 到 127.0.0.1:18989；
2. 改 compose 的 ports 为 "0.0.0.0:18989:18989"（无 TLS，必须配防火墙白名单）。

## 直接 docker run（不用 compose）

~~~bash
docker build -f deploy/docker/Dockerfile -t workdsh:local .
docker run -d --name workdsh \
  -p 127.0.0.1:18989:18989 \
  -v workdsh-data:/data \
  -e WORKDSH_PREVIEW_HEAP_MB=4096 \
  workdsh:local
~~~

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| WORKDSH_PREVIEW_PORT | 18989 | 容器内端口 |
| WORKDSH_PREVIEW_HOST | 0.0.0.0 | 容器内必须 0.0.0.0 才能被映射出来 |
| WORKDSH_PREVIEW_HEAP_MB | 4096 | Node 堆上限，小机器可设 2048 |
| WORKDSH_PREVIEW_HOME | /data/dsh | 数据目录（卷） |
| DSH_AGENTS_HOME | /data/agents | 技能目录（卷） |
| IMPORT_SESSIONS | 0 | 设 1 导入 /app/会话记录（需挂载） |
| FORCE_SEED | 0 | 设 1 强制重导存档（覆盖技能/专家） |
| MCP_SERVERS_ROOT | /opt/mcp-servers | MCP 程序包（镜像内） |
| SEMANTICA_VENV | /opt/venvs/semantica | semantica venv（镜像内） |
| SEED_SKILLS_DIR | /seed/.agents/skills | 构建时装的 6 个基础技能 |
| ENTRYPOINT_DRY_RUN | 0 | 设 1 只做播种检查后退出（排错用） |

## 首次启动做了什么

1. 从 /seed 补装 6 个基础技能（已存在不覆盖）；
2. 检测到 /data/dsh 没有专家数据 → 用 deploy/config 存档导入：技能 31 + Profile 5、专家 11、预设 10、MCP 连接器 8；
3. 把存档里的原机路径（/Users/apple/...）改写成容器路径（/app、/data、/opt/...）；
4. 可选导入会话（IMPORT_SESSIONS=1）；
5. 启动 preview，把带令牌的登录链接写进 /data/dsh/login-url.txt。

重复启动不会覆盖你的改动；要重导用 FORCE_SEED=1。

## 数据与备份

- 命名卷 workdsh-data 挂到 /data：包含 dsh（专家/项目/会话/预设/日志）、agents（技能）。
- 备份：docker run --rm -v workdsh-data:/data -v "$PWD":/backup alpine tar czf /backup/workdsh-data.tgz -C /data .
- 恢复：把 tgz 解回同一个卷，再 up -d。

## 升级

~~~bash
git fetch --all && git checkout <新提交号>
docker compose -f deploy/docker/docker-compose.yml up -d --build
~~~

数据在卷里，镜像重建不影响；镜像内的存档会重新导入吗？不会——只有 /data/dsh 为空时才导入。

## 已知边界

- **Chromium 默认不装**：Playwright MCP 需要时用 --build-arg INSTALL_CHROMIUM=1 重建（镜像约 +400MB）；
- **git 历史不进步镜像**（.dockerignore 排除 .git），容器里不能 git pull，升级靠重建镜像；
- **会话默认不带**（.dockerignore 排除 会话记录，约 146MB）；需要时在 compose 里挂载并设 IMPORT_SESSIONS=1；
- **令牌即密码**：/data/dsh/login-url.txt 不要外发；容器日志里也会出现，注意日志访问权限；
- **单实例共享**：所有访问者共享同一份数据与模型凭据配置，不是多租户。

## 排错

| 现象 | 处理 |
| --- | --- |
| 容器一直 restart | docker logs workdsh；多半是 /data 权限或 Node 版本 |
| healthy 但页面 401 | 正常，用带 token 的链接 |
| 页面能开、对话转圈 | 反代没转发 WebSocket；见 deploy/nginx 模板 |
| MCP 起不来 | docker exec workdsh ls /opt/mcp-servers；或跳过 mcp 相关步骤 |
| 技能/专家数量不对 | docker exec workdsh cat /data/dsh/logs/preview.log；设 FORCE_SEED=1 重导 |
