# 2026-10-20 增量更新（加密）

这是 2026-10-19 基础迁移包之上的增量包，只存放密文。
解密密码与基础包相同，由数据提供者通过私下渠道发送，仓库里没有密码。

前提：已经按 `migration/20261019` 分支恢复过基础包。

## 下载

```bash
git clone --branch migration/20261020 --single-branch https://github.com/kenlinwei001-a11y/dshwork.git dshwork-update
cd dshwork-update
```

## 合并与校验

```bash
cat parts/part-* > update-package.tar.enc
shasum -a 256 update-package.tar.enc
# 应为 550018932839133414e0fdd9a81192f80bea4bc26a9d50a86aca0c9c130a05e8
shasum -a 256 -c SHA256SUMS
```

## 解密与覆盖

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in update-package.tar.enc -out update-package.tar -pass pass:'<与基础包相同的密码>'
mkdir update && tar -xf update-package.tar -C update
cd update
./apply-update.sh <目标DSH_HOME> <AGENTS_HOME>

# 回到本分支目录，修会话头部的 cwd
cd ..
node retarget-sessions.mjs <目标DSH_HOME> --new-repo <仓库路径>
```

如果目标路径与 `/Users/apple/...` 不同，先回到基础包目录重新运行 `retarget.sh`，
再运行上面的 `retarget-sessions.mjs`。后者只改会话文件头部的 `cwd`，不改对话正文。

## 内容

- DSH_HOME 变更 2323 个文件，约 53 MiB，包含 10-20 的新对话、附件、项目文件、Office 文档和 workspace 状态。
- AGENTS_HOME 变更 39 个文件，约 53 KiB，包含专家预设和技能保留修订。
- 没有删除项。
- Tavily 等 OAuth 连接仍需在弹窗里重新授权。
