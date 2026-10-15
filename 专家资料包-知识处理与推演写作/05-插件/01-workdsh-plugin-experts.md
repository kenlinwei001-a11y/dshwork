# 插件：workdsh-plugin-experts（专家插件）

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 是什么

一个插件管理多个专家与专家团配置。它负责专家目录、搜索、收藏、复制、草稿、导入导出、启停与确认发布，并把发布后的专家编译为官方 Agent preset。本机两个专家（知识处理专家、推演写作专家）就是它的业务对象。

## 2. 提供的 Host 服务与工具

| 能力 | 说明 |
|---|---|
| ctx.workdshExperts（继承契约） | 页面与 Agent 管理工具使用同一 Host 服务 |
| 专家管理工具 11 个 | create_draft / get / list / list_skills / save_documents / save_resources / get_documents / update_draft / validate / request_publish / export_file |
| 内置 Skill | workdsh-expert-manager（制作指南，source=bundled，resourceBase 指向插件包内目录） |
| 官方预设编译 | 把专家定义 + 技能快照编译成 wd-exp-<kebab>-<digest> 形式的 Agent preset |
| 执行准入 | 在 agent/created、agent/pre-step 中核验资产、主体与组织，拒绝未配置的成员名 |

## 3. 关键机制（决定了专家的行为边界）

- 发布冻结：专家定义、成员修订、技能快照与官方 preset 一起冻结；改草稿不会静默改变已发布内容。
- 预设幂等：同样的输入摘要得到同样的 preset id，可复用；内容变化时报 preset-drift，要求重新发布。
- 技能快照：skill_requirements（上限 32）对应的技能目录被复制为受管快照，编译成官方 skill filesystem 配置。
- 团队执行外置：成员创建、消息与共享任务使用官方 Agent Teams 插件，专家插件不自建调度器（旧的 workdsh_expert_team_* 工具已删除）。

## 4. 与这两个专家的关系

| 事项 | 知识处理专家 | 推演写作专家 |
|---|---|---|
| 由本插件管理 | 是 | 是 |
| 技能快照数量 | 21 | 6 |
| 是否配置成员（team） | 否 | 否 |
| 是否被项目引用 | 是（团队知识库 #7） | 否 |
