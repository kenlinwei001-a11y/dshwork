# Profile 组合与安装

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. Profile 是什么

Profile 是 DSH 的运行时组合：一份 package.json（依赖锁定）+ dsh.profile.bundles（启用顺序）+ cordis.patch.yml（加载器补丁）。所有插件都必须装进某个 Profile 才对当前运行时生效。

## 2. 本机 Profile

- 路径：`/Users/apple/workdsh/.test-runtime/preview/profiles/preview`
- 热重载：patchReload = `live`（客户端插件改动可热重载，其余改动需重建并刷新）

## 3. bundles（启用顺序）

~~~text
@deepseek-ai/dsh-base
@deepseek-ai/dsh-web-app
workdsh-bundle
workdsh-plugin-access
workdsh-plugin-activity
workdsh-plugin-audit
workdsh-plugin-connectors
workdsh-plugin-experts
workdsh-plugin-office
workdsh-plugin-skills
workdsh-provider-identity-local
dsh-cost-meter
dshmarket
dsh-plugin-ssh
dsh-mcp-connector
workdsh-plugin-library
workdsh-plugin-projects
workdsh-plugin-plate
@cocofhu/skillhub
clearai-dsh
~~~

## 4. 安装/卸载方式（供参考，不在本包执行）

- 安装：以本地 tgz 或市集条目加入 Profile 的依赖与 bundles，按官方流程停服修改组合后重启该 Profile。
- 卸载：移除组合项后重启；用户技能文件与管理数据保留，重装可继续使用（技能页的「卸载」只是把技能对象放进可恢复回收站）。

## 5. 与这两个专家的关系

- 卸载 workdsh-plugin-experts 会让两个专家入口与其内置 Skill workdsh-expert-manager 消失；专家定义与已发布修订数据保留。
- 卸载 workdsh-plugin-skills 不会删除 ~/.agents/skills 下的 21 个 Skill 文件。
- 卸载 workdsh-plugin-connectors 会让 5 个 kp-* 连接失效，知识处理链路随之不可用（连接配置记录仍在）。
