# NexusOne 垂直技能池

三个垂直域的社区高质量技能，经逐个开 README 核实、frontmatter 校验后收编。
本目录是**唯一真相源**；部署 = 整体复制到 `~/.agents/.workdsh-catalog/`（技能插件按 catalog.json 的 mtime+size 签名自动重载，无需重启服务，刷新页面即可在「全部技能」按分类页签筛选、点 ＋ 激活安装）。

## 收录清单（2026-09-18）

| 技能 | 域 | 来源 | 许可 | 星(收录时) |
|---|---|---|---|---|
| math-modeling | 数学建模 | [XiaoMaColtAI/math-modeling-skill](https://github.com/XiaoMaColtAI/math-modeling-skill) | 未声明（公开仓库，保留出处） | 1594 |
| auto-mcm | 数学建模 | [RealSeaberry/AutoMCM-Pro](https://github.com/RealSeaberry/AutoMCM-Pro) | MIT | 249 |
| nature-academic-search | 学术科研 | [wp-a/nature-academic-search](https://github.com/wp-a/nature-academic-search) | MIT | 256 |
| claude-paper-study | 学术科研 | [alaliqing/claude-paper](https://github.com/alaliqing/claude-paper) | MIT | 328 |
| claude-paper-summary | 学术科研 | 同上 | MIT | — |
| resanity | 金融投研 | [Thhoho/reSanity](https://github.com/Thhoho/reSanity) | MIT | 4 |
| stock-data-assistant | 金融投研 | [Yourdaylight/stock_datasource](https://github.com/Yourdaylight/stock_datasource) | MIT | 186 |
| stock-mcp-query | 金融投研 | 同上 | MIT | — |

## 已知依赖

- `stock-*` 两个技能的取数能力依赖本地 stock_datasource 服务（MCP/8001/6666），未接入时仅提供流程指导；接入数据源是后续独立任务。
- `nature-academic-search` 的完整核验工具链依赖 academic-search MCP；纯技能形态下用宿主检索能力工作。
- `math-modeling-skill` 上游无 LICENSE 文件（公开仓库+CSDN 教程配套），收编保留出处；如产品化分发需联系作者确认。

## 更新方法

从上游拉新版 → 替换 `market/payloads/<name>/` → 确认 SKILL.md frontmatter `name` 与目录名一致 → 同步到 `~/.agents/.workdsh-catalog/`。catalog.json 的 `name` 必须等于 payload 目录名和 frontmatter name。
