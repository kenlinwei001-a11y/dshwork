# Linux 服务器部署指南（浏览器模式）

目标：一台 Linux 服务器（Debian/Ubuntu 推荐）跑 WorkDSH，同事用浏览器访问。
与 Windows 版的区别：**用 systemd 常驻**、**可选直接监听 0.0.0.0 或走 nginx 反代**、**启动后打印令牌登录链接**。

## 一条命令（反代拓扑，推荐）

~~~bash
git clone https://github.com/kenlinwei001-a11y/dshwork.git
cd dshwork && git checkout 26d2616754
sudo bash deploy/bootstrap-linux.sh
~~~

默认：应用只听 127.0.0.1:18989，由 nginx/HTTPS 对外；服务名 workdsh-preview。

常用变体：

| 目的 | 命令 |
| --- | --- |
| 生成 nginx 配置 | sudo bash deploy/bootstrap-linux.sh --nginx-host dsh.example.com |
| 直接对外（无 TLS） | sudo bash deploy/bootstrap-linux.sh --public |
| 换端口 / 堆 | ... --port 19000 --heap 4096 |
| 只装不启动 | ... --no-start |
| 无 sudo / 无 systemd | bash deploy/bootstrap-linux.sh --no-systemd |
| 导入仓库自带会话 | ... --with-sessions |
| 只打印计划 | bash deploy/bootstrap-linux.sh --dry-run |
| 机器可读结果 | ... --json |

## 三种拓扑，选一个

### A. nginx 反代 + HTTPS（公网/多人，推荐）

~~~bash
sudo bash deploy/bootstrap-linux.sh --nginx-host dsh.example.com
sudo cp deploy/nginx/workdsh.generated.conf /etc/nginx/conf.d/workdsh.conf
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d dsh.example.com        # 可选但强烈建议
~~~

要点：
- 应用保持只听 127.0.0.1，攻击面最小；
- **必须转发 WebSocket**（模板已带 Upgrade/Connection），否则界面能开、对话一直转圈；
- 上传大文件时调大 client_max_body_size（默认 500m）；
- 想要运维层再兜一层，可加 Basic Auth（模板里有注释）。

### B. 直接监听 0.0.0.0（内网快速验证）

~~~bash
sudo bash deploy/bootstrap-linux.sh --public
# 防火墙只放行给你的办公网段
sudo ufw allow from 10.0.0.0/8 to any port 18989 proto tcp
~~~

代价：**没有 TLS**。应用只有 ?token= 登录（令牌启动时打印），能防误入，但不能替代 HTTPS。

### C. 不开放端口，SSH 隧道（最安全）

服务器上只跑 127.0.0.1:18989，同事本地：

~~~bash
ssh -N -L 18989:127.0.0.1:18989 user@server
# 浏览器打开 http://127.0.0.1:18989/?token=<服务器日志里的令牌>
~~~

## 令牌登录链接在哪

部署脚本会直接打印：

~~~
  登录链接（含令牌，等同密码，不要公开）：
    http://127.0.0.1:18989/?token=xxxxxxxx
~~~

自己找（systemd 版）：

~~~bash
journalctl -u workdsh-preview --no-pager | grep -o 'http://[^ ]*token=[A-Za-z0-9_-]*' | tail -1
~~~

> 令牌等同登录凭据：不要贴到群里、不要写进文档。走反代时把 URL 里的 host 换成域名。

## 运维命令

~~~bash
systemctl status workdsh-preview
journalctl -u workdsh-preview -f
sudo systemctl restart workdsh-preview
sudo systemctl disable --now workdsh-preview
~~~

升级（保留数据）：

~~~bash
cd ~/workdsh
git fetch --all && git checkout <新提交号>
sudo bash deploy/bootstrap-linux.sh
~~~

改存档/专家后（重要）：

~~~bash
bash deploy/scripts/export-local-config.sh --check    # 存档是否过期
bash deploy/scripts/export-local-config.sh            # 刷新存档
~~~

备份：**只需备份 ~/.workdsh/preview**（含 storages、sessions、.agent-presets、logs）；技能在 ~/.agents。

## 部署后会得到什么（与仓库存档一致）

| 项 | 数量 |
| --- | --- |
| 技能 | 用户根 31 + Profile 5 |
| 专家 | 11 |
| 发布修订 | 23 |
| Agent 预设 | 10 |
| MCP 连接器 | 8 |

会话默认不导入；加 --with-sessions 才导入仓库里那 3 条。

## 排错

| 现象 | 处理 |
| --- | --- |
| 服务起不来 | journalctl -u workdsh-preview -n 200；多半是 Node 版本或 corepack enable 失败 |
| 端口能连但页面 401/403 | 正常：需要带 ?token= 的登录链接 |
| 页面能开、对话转圈 | 反代没转发 WebSocket；对照 deploy/nginx/workdsh.conf.template |
| 上传失败 | nginx 的 client_max_body_size 太小 |
| install-local-config.sh 报命令不存在 | 对应 MCP 依赖没装：重跑第 4/5 步（别跳过 mcp-servers、semantica） |
| 内存不足 | --heap 4096，并给服务器加 swap |
| 令牌找不到 | nohup 模式看 ~/.workdsh/preview/logs/preview-server.log |

## 与其它平台的关系

| 平台 | 入口 | 服务方式 |
| --- | --- | --- |
| Windows（WSL2） | deploy/bootstrap-windows.ps1 | nohup（WSL 内） |
| Linux 服务器 | deploy/bootstrap-linux.sh | systemd |
| macOS（本机） | deploy/scripts/setup-all.sh | launchd |
