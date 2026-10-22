# 2026-10-22c 增量更新（加密）

前提：已恢复 `migration/20261019` 基础包，并应用过 `migration/20261020`、
`migration/20261022`、`migration/20261022b`。
密码与基础包相同，由提供者私下发送。

## 下载与校验

```bash
git clone --branch migration/20261022c --single-branch https://github.com/kenlinwei001-a11y/dshwork.git dshwork-update-1022c
cd dshwork-update-1022c
cat parts/part-* > update-package.tar.enc
shasum -a 256 update-package.tar.enc
# 应为 90ce7810a4f63fbefd53ddfb30b5451d722cc59a43f4754c05e2fe7c7d0849a7
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

- DSH_HOME 变更 9309 个文件，约 140.4 MiB：22 个会话（约 61.8 MiB）、
  项目文件、附件、存储元数据、profile 配置。
- AGENTS_HOME 变更 221 个文件，约 1.15 MiB。
- 删除 21 个项目内陈旧产物（旧章节提示词、旧 ZIP、旧控制台原型）；
  `apply-update.sh` 会按清单删除。
- `.credentials.yaml` 不包含在包内；目标机单独配置自己的 key。
