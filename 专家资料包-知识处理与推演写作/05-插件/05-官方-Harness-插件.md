# 官方 Harness 插件（专家真正运行时的装配件）

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 为什么单独列一组

专家、Skill、团队、Model、工具这些「运行期能力」由官方 DSH 插件提供；WorkDSH 插件只做业务对象与装配。看懂这组插件，才能理解「专家是怎么跑起来的」。

## 2. 与本链路直接相关的官方插件

| 插件 | 职责 | 在本链路中的作用 |
|---|---|---|
| @deepseek-ai/dsh-persona | 把角色人设（Agent MD）注入 Agent 局部 | 专家正文真正生效的地方 |
| @deepseek-ai/dsh-skill-filesystem | 从技能根加载 Skill 清单与正文 | 让专家的技能快照与用户技能可被发现 |
| @deepseek-ai/dsh-tool-skill | 官方 skill 工具（加载 SKILL.md） | 模型按需读取技能正文 |
| @deepseek-ai/dsh-agent-preset-registry | 注册与解析 Agent preset | 专家编译产物 wd-exp-* 的注册处 |
| @deepseek-ai/dsh-experimental-agent-team | 成员、消息、共享任务、持久化恢复 | 专家团执行的基础设施 |
| @deepseek-ai/dsh-experimental-tool-agent-team | 官方九项团队工具 | spawn_teammate / team_task_* 等 |
| @deepseek-ai/dsh-experimental-client-ui-agent-team | 官方成员与共享任务面板 | 团队面板 UI |
| @deepseek-ai/dsh-mcp-client | 官方 MCP client（stdio / Streamable HTTP） | 连接器插件复用的执行适配 |
| @deepseek-ai/dsh-credentials | 官方凭据服务 | MCP token 的唯一存放处 |

## 3. 与本机两个专家的关系

- 两个专家在发布时被编译成 Agent preset：persona（专家正文）+ skill filesystem（技能快照）+ 工具集。
- 二者都是单专家，因此不涉及 agent-team 三个插件；一旦配置成员，就转由官方 Team 执行。
- Skill 的加载走官方 provider：目录清单常驻、正文按需加载（渐进披露），WorkDSH 不重造执行器。
