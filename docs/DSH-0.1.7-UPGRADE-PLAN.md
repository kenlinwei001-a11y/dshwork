# DSH 0.1.7-alpha.1 升级计划

日期：2026-09-22。用户授权实施；原则：能用原生就用原生。
基线：0.1.6-alpha.2；目标：0.1.7-alpha.1。独立升级专项，不代表 D04/D11 或其他业务模块整体完成。

## 实施与验收

- [x] U17-1：核对已发布包 exports/types，更新精确版本族及锁文件；禁止改上游和用户 Profile。
- [x] U17-2：专家发布/恢复改用官方 AgentPresetRegistry，保留业务修订、资源校验、授权和冷启动注册；不创建每专家 npm 包。旧修订不能静默重编后冒充同一运行组合。
- [x] U17-3：默认使用原生工作过程与 Team 面板，停止组合重复 Activity 展示；保留独立插件历史兼容与业务活动记录。
- [x] U17-4：默认使用原生 XLSX/XLS/CSV/TSV 预览，保留差异编辑入口；适配原生二进制预览契约。
- [x] U17-5：检查 Session V4、附件、配置和项目引用链，使用隔离数据验证；不直接改写用户 Session 日志。
- [x] U17-6：构建、类型、相关单元/集成测试、版本/计划门禁、隔离 Profile 启动与冷恢复；回填真实证据和未验证范围。

## 官方能力复用记录

|任务|官方依据/公开面|WorkDSH 差异与验证|
|---|---|---|
|U17-1|docs/dsh-v0.1.7-alpha.1/docs/config-catalog.zh.md；已发布 0.1.7-alpha.1 包|精确依赖、Loader/Profile 安装与构建|
|U17-2|subsystems/core.zh.md 的 ctx.agentPresets；dsh-agent-preset-registry|专家多对象/冻结修订/主体绑定仍由专家服务拥有；注册、释放、重启、资源漂移测试|
|U17-3|release.txt 工作过程/Team；原生 Conversation 与 Team 工具|不另解析和调度执行；默认组合不注册自有重复过程栏|
|U17-4|subsystems/sidebar-right.zh.md；documentPreviews|只保留 Office 编辑业务；原生预览优先、字节数据和选择器验证|
|U17-5|persistence-changes/2026-09-16-session-format-v4.zh.md；workspace.zh.md|自有业务引用与 Session 格式分离；历史恢复、引用展示/读取验证|

## 风险与回退

先验证发布包，再实现，文档不能代替运行。既有旧专家预设是目录格式；迁移必须显式诊断不支持的历史格式。Session V4 用官方迁移，测试副本先行。保留正式预览现有运行版本直到隔离验收完成。安装失败、真实模型未执行或视觉未验收须明确记录。提交、推送、发布不属于本次授权。

## 执行记录

- 初始工作树干净；npm 已确认目标 dsh 版本存在。当前 shell Node 21，后续使用本机 Node 22.23.2 与 pnpm 10.34.5。

## 验收结果（2026-09-22）

- Node 22.23.2 / pnpm 10.34.5；全量 build、typecheck 通过。
- 精确版本门禁通过：545 条 DSH 锁记录统一 0.1.7-alpha.1，Cordis 4.0.3、schemastery 3.18.3。
- 集成 110/110，资料库 5/5，项目 10/10，规划 2/2；Activity 15/15（含新增 Session V4 回归）。
- 真正的公开 Loader + AgentPresetRegistry 验证声明注册、释放、重新注册、冻结内容以及摘要漂移拒绝。专家发布采用临时目录再原子重命名，失败不会覆盖既有修订。
- 隔离安装探针验证打包安装、Host 启动、匿名 401/登录 200、卸载重启和重新安装。
- 专家浏览器探针 13 项通过：独立 Profile 安装、真实身份授权/审计、原生 Session 与固定绑定、草稿引用、技能选择、显式发布与召唤、响应式界面无页面错误、两次 Host 冷启动恢复。
- 本地日志：`.test-runtime/upgrade-017/` 的 build-final.log、typecheck-final.log、integration2.log、library.log、projects.log、versions.log、install-probe.log、experts-package.log。浏览器证据在 `.artifacts/experts-package/`。

## 交付边界与迁移注意

- 完成本地代码与验证；未提交、推送、发布，也未替换用户正在运行的 Profile。
- 原生工作过程与 Team 面板拥有展示；项目自身业务活动记录保留。Activity 历史事件投影兼容 V3/V4，但不再注册重复界面或轮询子代理。
- Office 不再接管 CSV/TSV；Office 编辑注册为 builtin 备选，随默认原生预览之后加载，保留编辑入口。原生 XLS/XLSX/CSV/TSV 已发布支持；本轮补充六种格式浏览器视觉验收，均正常；三种编辑入口也可切换。
- 旧目录格式专家修订不静默重编。旧资产及日志保留，需要重新发布形成新的声明式预设，再创建新任务；旧任务自动迁移续跑不在已验证范围。
- Session V4 的 Skill 调用与持久化恢复已测；没有直接修改用户历史日志。项目/资料库为模块回归，本轮已跑项目 @ 引用→原生执行→右侧预览→冷启动重开链路；未做跨项目权限的全面浏览器回归。
- 未运行付费模型、专家团小时级长任务、OAuth、跨平台测试。`probe-presets.mjs`、`probe-official-expert-composition.mjs`、`probe-native-expert-team.mjs` 仍是旧 0.1.6 诊断脚本，不作为本次证据；本次采用新版 registry 集成与 experts-package 浏览器探针。

## 补充验收

详见 [2026-09-22 验收记录](evidence/dsh-0.1.7-acceptance.md)：16 项浏览器检查和旧格式专家回归通过；资料引用预览浅色主题不一致已修复，续轮 17 项浏览器验收通过（含主题往返切换）。核心升级兼容通过不等于完整产品或发行验收。
