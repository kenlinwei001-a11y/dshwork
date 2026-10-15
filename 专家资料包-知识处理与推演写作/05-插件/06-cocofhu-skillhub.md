# 插件：@cocofhu/skillhub（第三方技能货架）

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 是什么

第三方 DSH 插件，向技能页提供 SkillHub 目录的搜索与安装通道（skillhub_search / skillhub_list / skillhub_install 等）。它只负责发现与安装，不拥有技能内容。

## 2. 证据

- Profile 组合中包含 @cocofhu/skillhub（版本见 09-Profile组合与安装.md）。
- 技能页的 SkillHub 面板通过 ./skillhub 路由访问；当 Profile 未安装该插件时该路由不存在（实测 405），界面会显示「当前 Profile 未安装 SkillHub 插件」。

## 3. 与这两个专家的关系

- 没有直接关系：两个专家配备的 Skill 全部来自本机技能根，而不是 SkillHub。
- 间接关系：如果未来通过 SkillHub 安装新 Skill，它会落在同一技能根，因而可以被专家配备（再发布一次专家即冻结进快照）。
- 边界：第三方市场内容不代表内置或已审核；许可与依赖由来源与安装校验决定。
