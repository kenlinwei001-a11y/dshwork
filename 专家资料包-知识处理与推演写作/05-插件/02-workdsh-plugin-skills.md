# 插件：workdsh-plugin-skills（技能插件）

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 是什么

技能管理插件：一个插件管理多个 Skill 业务对象，提供技能页、SkillHub 浏览入口、导入预检与确认安装、启停、可恢复卸载等能力，并通过 Host 服务 ctx.workdshSkills 对外开放。

## 2. 内置技能（随插件）

| Skill | 说明 |
|---|---|
| workdsh-ppt-design | PPT 叙事与视觉设计指南 |
| workdsh-word-design | Word 报告体裁与版式指南 |
| workdsh-excel-design | Excel 字段/公式/可用性指南 |
| workdsh-web-design | 网站与 Web 应用组织指南 |
| workdsh-skill-creator | 技能创建与打包（含 init/validate/package 脚本） |

这些以 source=bundled、resourceBase 指向插件包内 resources/skills/<name>/ 注册，卸载插件即消失。

## 3. 与这两个专家的关系

- 两个专家配备的 21 个 Skill 并不在本插件内置，而是位于本机技能根 ~/.agents/skills/，属于用户/本地安装技能。
- 本插件的技能页与专家页共享同一技能目录视图：专家编辑时用 workdsh_expert_list_skills 查询的就是这份真实目录（state=enabled、selectable=true）。
- 技能当前没有不可变修订能力（README 明确「不可变 SkillRevision 尚未实现」）；版本冻结发生在专家发布时的受管快照。

## 4. 本机技能根分层

| 根 | 路径 | 内容 | 说明 |
|---|---|---|---|
| 全局/共享（本包主体） | ~/.agents/skills/ | 21 个知识处理链路 Skill 等共 30 个 | 两个专家使用的 Skill 都在这里 |
| Profile 级 | DSH_HOME/skills/ | design-master、drawio-diagrams、ui-new 等 | 随 Profile 隔离 |
| 插件内置 | 插件包内 resources/skills/ | 5 个设计/创建类 Skill | 随插件生命周期 |
