# 插件与 Skill 的关系

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 一句话

插件是安装与供货单元，Skill 是内容与能力单元。一个插件可以自带、管理、分发多个 Skill；但 Skill 本身不是插件，也不需要发 npm 包。

## 2. 三种真实关系（本机均有实例）

### ① 插件捆绑内置 Skill（source=bundled）
- 机制：插件把正文放进自己的 resources/skills/<name>/SKILL.md，在 apply 时 ctx.skills.register({ source: bundled, resourceBase }) 注册。
- 实例：workdsh-plugin-skills 内置 5 个；workdsh-plugin-experts 内置 1 个（workdsh-expert-manager）。
- 生命周期：跟着插件——卸载即消失、升级即更新、管理页只读。

### ② 用户/市场安装的 Skill（普通目录）
- 机制：技能根下的一个目录（SKILL.md + references/ + scripts/ + assets/），由技能管理服务写入。
- 实例：两个专家配备的 21 个 Skill 均属此类（~/.agents/skills/）。
- 生命周期：独立于插件——卸载插件不删、重装插件不覆盖。

### ③ 插件只提供货架与安装通道
- 实例：@cocofhu/skillhub 提供 SkillHub 搜索与安装；未安装时技能页对应路由不存在（实测 405）。
- 它给的是「发现 + 安装」，不拥有技能内容。

## 3. 判定标准

| 需求 | 做什么 |
|---|---|
| 注册 Host 服务、提供 UI/路由/工具、管理一类业务对象 | 写插件（npm tgz，装进 Profile，重载生效） |
| 只是给模型的一套任务指令 + 参考 + 脚本 + 模板 | 写 Skill（一个目录，装上即用） |
| 把一批 Skill 随版本发给别人 | 要么插件捆绑，要么打 ZIP 走导入流程 |

## 4. 两个容易踩的边界

- Skill 目前没有不可变修订（skills 插件 README 明确）；真正的版本冻结发生在专家发布时的受管快照。
- Skill 正文里出现的「安装命令/插件名」是资料而非授权：专家制作规范要求把外部平台的工具名映射到本系统，不能照搬执行。
