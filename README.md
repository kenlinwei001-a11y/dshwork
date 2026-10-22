# 2026-10-22b 增量更新（加密）

前提：已恢复 `migration/20261019` 基础包，并应用过 `migration/20261020`、`migration/20261022`。
密码与基础包相同，由提供者私下发送。

## 下载与校验

```bash
git clone --branch migration/20261022b --single-branch https://github.com/kenlinwei001-a11y/dshwork.git dshwork-update-1022b
cd dshwork-update-1022b
cat parts/part-* > update-package.tar.enc
shasum -a 256 update-package.tar.enc
# 应为 6921492b77cba9615b737057900dc12101af992ae24b4ef692c84bbd510af6b6
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
`retarget-sessions.mjs`。

## 内容

- DSH_HOME 变更 420 个文件，约 2.7 MiB：10-22 报告构建期间新增/更新的会话
  （含 Desktop 工作区的最新对话）和存储元数据。
- AGENTS_HOME 无变更。
- 没有删除项。
