# 2026-10-23b 增量更新（加密）

前提：已恢复 `migration/20261019` 基础包，并应用过 `migration/20261020`、
`migration/20261022`、`migration/20261022b`、`migration/20261022c`、`migration/20261023`。
密码与基础包相同，由提供者私下发送。

## 下载与校验

```bash
git clone --branch migration/20261023b --single-branch https://github.com/kenlinwei001-a11y/dshwork.git dshwork-update-1023b
cd dshwork-update-1023b
cat parts/part-* > update-package.tar.enc
shasum -a 256 update-package.tar.enc
# 应为 c9358b994a37d5b3c99c15dd5a0846a2e505c801bfb65fc8f283171e495bc20c
shasum -a 256 -c SHA256SUMS
```

## 解密与覆盖

```bash
export WORKBENCH_PW='<与基础包相同的密码>'
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in update-package.tar.enc -out update-package.tar -pass env:WORKBENCH_PW
mkdir -p update-package && tar -xf update-package.tar -C update-package
./update-package/apply-update.sh <目标DSH_HOME> <AGENTS_HOME>

node retarget-sessions.mjs <目标DSH_HOME> --new-repo <仓库路径> --new-agents <AGENTS_HOME>
```

如果目标路径与 `/Users/apple/...` 不同，回到基础包先跑 `retarget.sh`，再跑
`retarget-sessions.mjs`。WSL/Windows 上如果 MCP 定义被这批数据覆盖，再跑一次：

```bash
SKIP_EXPERTS=1 bash deploy/scripts/install-local-config.sh "$DSH_HOME" "$AGENTS_HOME"
```

## 内容

- DSH_HOME 变更 2219 个文件，约 390.3 MiB：4 个会话（约 76.4 MiB）、项目文件
  约 180 MiB、附件约 126 MiB、存储元数据。
- AGENTS_HOME 变更 6 个文件，约 140 KiB。
- 本次不计算删除项，只覆盖。
- `.credentials.yaml` 不包含在包内；目标机单独配置自己的 key。
