# 专家资料包构建器

把「专家 / 技能 / 项目 / 插件 / MCP」的本机权威状态，一次性构建成可核对、可重复、可发现漂移的资料包。

## 快速使用

    node tools/expert-report/build.mjs            # 全量重建（磁盘权威数据）
    node tools/expert-report/build.mjs --check    # 是否过期：0=最新 1=过期 2=没有历史清单
    node tools/expert-report/build.mjs --self-check  # 幂等性证明：两次构建字节一致
    node tools/expert-report/build.mjs --all-experts # 范围扩到全部专家
    node tools/expert-report/build.mjs --no-zip      # 只出目录，不打 ZIP

产物：

- 目录：`专家资料包-知识处理与推演写作/`
- ZIP：`知识处理与推演写作专家-完整资料包.zip`

## 数据来源（全部为磁盘权威状态）

| 数据 | 来源 |
| --- | --- |
| 专家 | `storages/workdsh_experts/{experts,revisions,drafts}/*.json` |
| 技能 | `~/.agents/skills`、`DSH_HOME/skills`、各插件 `resources/skills` |
| 项目 | `storages/workdsh_projects/states/*.json` |
| MCP（WorkDSH） | `storages/workdsh_connectors/definitions/*.json` |
| MCP（第三方注册表） | `storages/mcp_connector.json`（只哈希，不复制：可能含 token） |
| 插件与组合 | `profiles/preview/package.json` + 各包 `package.json` |
| 运行时观测 | `sources/runtime.json`（会话工具快照，可选） |

## 设计约束

1. **单一来源**：文档全部由数据生成，不读上一次产物；因此不会出现"文档与事实分叉"。
2. **全量收录**：技能按运行时可见集合收录（当前 43 个），不按专家裁剪。
3. **内容确定性**：文档里的时间用 `sourceEpoch`（源文件最新 mtime）而不是 `now`；ZIP 条目排序、固定时间戳、UTF-8 文件名标志。源不变 ⇒ 字节不变（`--self-check` 会验证）。
4. **四级哈希**：源单元、源文件、产物文档、原件副本，全部 SHA-256；副本写入后立即复算。
5. **漂移可发现**：`.state/manifest.json` 存上次源摘要，`--check` 逐条比对。
6. **不泄露凭据**：env 只记键名、URL 去 userinfo、第三方注册表不复制、产物再扫一遍密钥特征（sk-*/Bearer/api_key）。
7. **不合并矛盾**：MCP 的三套视图（会话可见 / WorkDSH 定义 / 第三方注册表）并列呈现；不一致写入"提示"，不假装一致。
8. **FAIL 即阻断**：任一硬检查失败，构建返回非零退出码，产物不可交付。

## 目录

    tools/expert-report/
      build.mjs          编排：采集 → 校验 → 渲染 → 复制 → 清单 → ZIP
      config.json        范围、输出命名、插件说明（唯一需要人工维护的地方）
      sources/runtime.json  运行时快照（可选；由会话工具采集）
      lib/collect.mjs    读权威数据
      lib/render.mjs     生成文档
      lib/zip.mjs        确定性 ZIP
      lib/util.mjs       哈希 / frontmatter / 表格 / 脱敏
      .state/manifest.json  上次构建的源摘要（--check 用）

## 日常维护

- **新增专家进范围**：把 id 加到 `config.json` 的 `scope.experts`，重建。
- **技能库新增技能**：无需操作，重建即收录。
- **插件说明**：在 `config.json` 的 `pluginNotes` 里按包名写 `role` / `relation`。
- **刷新运行时观测**：重新采集 `sources/runtime.json`（字段见文件内的 `note`），再重建。
- **判断是否需要重建**：`--check`。
