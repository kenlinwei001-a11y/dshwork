# 2026-10-25 增量更新（加密）

前提：已恢复 `migration/20261019` 基础包，并应用过 `migration/20261020`、
`migration/20261022`、`migration/20261022b`、`migration/20261022c`、
`migration/20261023`、`migration/20261023b`、`migration/20261023c`、`migration/20261023d`。
密码与基础包相同，由提供者私下发送。

## 下载与校验

```bash
git clone --branch migration/20261025 --single-branch https://github.com/kenlinwei001-a11y/dshwork.git dshwork-update-1025
cd dshwork-update-1025
cat parts/part-* > update-package.tar.enc
shasum -a 256 update-package.tar.enc
# 应为 e9047974b01bfe48ff68b97324ed919b8fb168b44a45d8a327a0721988144d5c
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

- DSH_HOME 变更 6,563 个文件，约 149.5 MiB：10-23d 之后新增/更新的会话、
  专家修订/预设、项目文件、附件和存储元数据。
- AGENTS_HOME 变更 257 个文件，约 1.7 MiB。
- 本次不计算删除项，只覆盖。
- `.credentials.yaml` 不包含在包内；目标机单独配置自己的 key。
