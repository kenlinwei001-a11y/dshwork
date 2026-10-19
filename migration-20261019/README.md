# DSH_HOME 迁移数据（加密分片）

本分支只存放 AES-256 加密后的迁移包，按 <100MB 分片提交。
解密密码由数据提供者通过私下渠道发送，仓库里没有密码。

## 下载

```bash
git clone --branch migration/20261019 --single-branch https://github.com/kenlinwei001-a11y/dshwork.git
cd dshwork/migration-20261019
```

## 合并与校验

```bash
cat parts/part-* > package.tar.enc
shasum -a 256 package.tar.enc
# 应为 02412b4c190d8a713ccc51255d99c9d2d4be62812b32afef178b681346a520ae

shasum -a 256 -c SHA256SUMS.parts
```

## 解密

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in package.tar.enc -out package.tar -pass pass:'<密码由提供者私下发送>'
mkdir package
tar -xf package.tar -C package
```

然后按 `package/README.md` 的步骤恢复 DSH_HOME、重定位路径、单独配置凭据。

## 说明

- 分片共 5 个，前 4 个 90MiB，最后 1 个约 31MiB。
- 密码不要写进 issue、README、提交信息或公开发送。
- 恢复完成后，可让维护者删除本分支；GitHub 可能保留不可达对象一段时间，
  但其中只有密文。
- 解密后的目录不要再次提交到任何公开仓库。
