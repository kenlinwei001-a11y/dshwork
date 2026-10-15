# workdsh-bundle 与其余功能插件

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 本机安装的 WorkDSH 功能插件

| 插件 | 职责 |
|---|---|
| workdsh-bundle | 工作台导航与总装配（把各功能包组合为 WorkDSH 体验） |
| workdsh-plugin-access | 访问控制与授权 |
| workdsh-plugin-activity | 个人工作动态（只显示自己的工作） |
| workdsh-plugin-audit | 审计 |
| workdsh-plugin-connectors | MCP 连接管理（见 03） |
| workdsh-plugin-experts | 专家与专家团（见 01） |
| workdsh-plugin-library | 资料库资产与修订 |
| workdsh-plugin-office | Word / Excel / PPT / PDF 内容工具 |
| workdsh-plugin-plate | NexusAI 实时文档编辑器 |
| workdsh-plugin-projects | 项目工作台（见 04） |
| workdsh-plugin-skills | 技能管理（见 02） |
| workdsh-provider-identity-local | 本机个人身份提供者 |
| workdsh-provider-browser-session | 浏览器会话提供者 |

## 2. 与这两个专家相关的部分

- workdsh-plugin-office 与 workdsh-plugin-plate：专家交付物（DOCX 分析报告、可研报告）最终通过它们落盘，但专家定义本身不绑定编辑器。
- workdsh-plugin-library：项目资产引用指向资料库的 assetId + revisionId；项目不保存正文。
- workdsh-plugin-activity / -audit：记录本机操作，不产生「虚假成员留言或通知」。

## 3. 不相关但会出现在同一 Profile 里的插件

~~~text
dshmarket（第三方插件市场 UI/工具）
clearai-dsh（第三方）
dsh-cost-meter（用量计费显示，第三方）
dsh-plugin-ssh（SSH 能力，第三方）
~~~
