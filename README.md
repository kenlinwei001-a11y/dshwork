# 2026-10-22 增量更新（加密）

前提：已经恢复 `migration/20261019` 基础包，并应用过 `migration/20261020` 增量包。
本分支只存放密文，密码与基础包/10-20 增量相同，由提供者私下发送。

## 下载与校验

```bash
git clone --branch migration/20261022 --single-branch https://github.com/kenlinwei001-a11y/dshwork.git dshwork-update-1022
cd dshwork-update-1022
cat parts/part-* > update-package.tar.enc
shasum -a 256 update-package.tar.enc
# 应为 68945c09db0ce970bea3d2a86e488e988a953d26c3a45b036438628d17be3634
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

- DSH_HOME 变更 3241 个文件，约 166.5 MiB：10-22 最新会话、附件、项目文件、
  Office 文档、workspace、成本账本。
- AGENTS_HOME 变更 54 个文件：10-22 新建的 4 个专家预设和技能保留修订。
- 没有删除项。
