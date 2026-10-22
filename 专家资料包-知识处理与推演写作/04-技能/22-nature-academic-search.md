# 技能：nature-academic-search

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-10-22T05:53:59Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | nature-academic-search |
| description | >- Use when users ask to 找文献、做文献检索、查论文、查临床试验、核验引用、去重文献、设计 PubMed/MeSH 检索式、追踪上下游引文、解析 DOI/PMID/PMCID/arXiv/OpenAlex/Semantic Scholar/NCT ID， 或导出 RIS、BibTeX、NBIB、ENW；also use for multi-source academic search, citation verification, citation graphs, trial registration search, research workflows, or DeepSeek Harness academic-search MCP setup. |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/nature-academic-search |
| 所属插件 | （非插件内置） |
| 文件数 | 146 |
| 体积 | 1.11 MB |
| 被忽略文件 | 无 |

## 3. 引用关系

- 本次范围内专家配备：**未被范围内专家配备**
- 全部专家引用（含范围外）：无

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: nature-academic-search
description: >-
  Use when users ask to 找文献、做文献检索、查论文、查临床试验、核验引用、去重文献、设计
  PubMed/MeSH 检索式、追踪上下游引文、解析 DOI/PMID/PMCID/arXiv/OpenAlex/Semantic Scholar/NCT ID，
  或导出 RIS、BibTeX、NBIB、ENW；also use for multi-source academic search,
  citation verification, citation graphs, trial registration search, research workflows,
  or DeepSeek Harness academic-search MCP setup.
---

# Academic Paper Search

## 什么时候触发

用户提到找文献、文献检索、引用核验、引文图谱、MeSH、PubMed、预印本、临床试验、RIS/BibTeX
或 DOI/PMID/PMCID/arXiv/OpenAlex/Semantic Scholar/NCT 时触发本 skill。目标是论文时使用
`entity_type="publication"`；目标是注册试验时使用 `entity_type="trial"`，两者不能按题名合并。

## 任务路由

以下工具路由以实际工具输出为准；适配器存在不代表本次已经查询。

| 用户目标 | 入口 | 执行要求 |
|---|---|---|
| 找文献、综述前期检索 | `search_papers` | 按源检索、去重，报告 `sources_queried` / `sources_succeeded` / `sources_skipped` / `errors` |
| 核验已有引用 | `get_paper_by_id` + `expected` | 输出字段级 `verified`、`mismatch`、`not_found` 或 `manual_needed` |
| 追踪上下游引文 | `get_paper_by_id(include_relations=true)` | 默认 `depth=1`；需要二跳时显式 `depth=2`，保留图谱边和来源缺口 |
| 构建 PubMed 检索式 | `lookup_mesh` | 先核对 MeSH 词和 ID，再组合自由词；不要凭空猜主题词 |
| 生成单条引用 | `get_citation` | 只格式化已解析论文；NCT 注册不生成论文引用 |
| 批量导出或自动化 | CLI `citation` / `workflow` | 保留 `run.json`、核验状态和人工待处理清单 |

客户端可能给工具名添加 MCP 前缀；工具总数仍为四个，不新增专用图谱工具。
DeepSeek Harness 使用独立的
[`dsh-academic-paper-search`](https://github.com/wp-a/dsh-academic-paper-search)
Bundle，通过官方 `@deepseek-ai/dsh-mcp-client` 映射为
`mcp__academic_search__*`；这是同一 MCP 运行时的客户端适配，不要在 DSH
中重写或假设额外的论文工具。
CLI 从 `0.3.1` 起可用 `nature-academic-search search` / `verify` 得到同一份 JSON；
旧版客户端先检查 `--help`，不要假设已安装包包含新命令。

## 最小成功路径

1. 中文问题先 `lookup_mesh` 或写出英文检索式；`search_run.query_analysis.mesh_required`
   为 true 时不得跳过。不要把中文整句直接当已核验检索。
2. `search_papers`（建议 `ranking="relevance"`）；必须报告
   `sources_queried` / `sources_succeeded` / `sources_skipped` / `errors`。
3. 对拟引用记录（通常先 3 条）调用 `get_paper_by_id` + `expected`。
4. 按 `verified` / `mismatch` / `not_found` / `manual_needed` 分组交付。

正确：`lookup_mesh("medical education")` →
`search_papers("generative AI medical education", ranking="relevance")` →
对 DOI 做 `expected` 核验。
错误：只调用 `search_papers("生成式AI医学教育")`，并把返回题名当作已核验参考文献。

## 来源与边界

- 默认论文源：`crossref`、`pubmed`、`arxiv`、`openalex`、`europe_pmc`。
- `semantic_scholar` 用于显式搜索、`enrich` 或图谱；富化优先使用 DOI、PMID、arXiv 等强标识符。
- OpenAlex 提供跨学科 references / cited_by；PubMed ELink 提供生物医学双向关系。
- Crossref 与 Europe PMC 主要提供 references；arXiv 目前只作为节点和版本线索。
- `clinicaltrials_gov` 只服务 `entity_type="trial"`，不是论文数据库。
- 未连接 Google Scholar、Web of Science、Scopus、Embase、CNKI、万方，不得声称覆盖这些来源。

源失败、限流、缺少强标识符或不支持某方向时，保留成功结果并记录缺口；不能把未查询到解释成没有关系。

## 引文图谱契约

调用 `get_paper_by_id` 时可以传：

```json
{
  "include_relations": true,
  "relation": "both",
  "depth": 1,
  "rows": 20,
  "relation_sources": ["openalex", "crossref", "pubmed", "europe_pmc", "semantic_scholar"]
}
```

`relation` 是 `references`、`cited_by` 或 `both`。输出 `citation_graph` 必须保留：

- `nodes`：合并后的 publication 节点和来源记录；
- `edges`：统一为 citing → cited，含 `relation` 与 `observed_by`；
- `sources_queried`、`sources_succeeded`、`sources_skipped`、`errors`；
- `truncated`、`truncation_reason`、`depth_completed`。

`references` 表示种子指向被引用节点，`cited_by` 表示引用者指向种子。图谱是关系导航和审计数据，
不是证据质量、因果关系、影响力或研究结论评分。

## 标准执行顺序

1. 明确主题、人群/系统、干预、结局、日期、文献类型、预印本政策和实体类型。
2. 生物医学问题先用 `lookup_mesh` 核验主题词，再组合题名/摘要自由词。含中文的问题必须先得到 MeSH 或英文检索式。
3. 调用 `search_papers`；保存原查询、日期、请求源、结果数量和 `search_run`。
4. 按 DOI、PMID、PMCID、arXiv、OpenAlex、Semantic Scholar 或 NCT 强标识符去重；弱题名匹配保留冲突。
5. 对拟引用记录调用 `get_paper_by_id` + `expected`，逐项核对题名、首位作者、年份、期刊和标识符。
6. 需要时追加一跳引文图谱；二跳、`rows` 和源列表必须有明确研究目的和预算。
7. 按 verified、mismatch、not_found、manual_needed、preprint、trial 分组交付；未核验记录不能静默导出。
8. 批量任务使用 workflow，先生成 `plan.json`，获得批准后再检索，并保存 `run.json`、`results.json`、
   `verification.json`、`screening.csv`、`references.ris` 和可选 `graph.json`。

Workflow 从 `0.3.1` 起默认按标识符回查并核验候选元数据。省略 `verify` 不会把候选视为已核验。
核验范围见 `fields`、`lookup_id` / `lookup_id_type`；来源无法提供的附加 ID 列入
`unchecked_identifiers`，不能称为已核验，RIS 不写入未匹配的 DOI / PMID。作者截断标记
`et al.` 不参与作者比较。原始候选和未核验附加 ID 保留在 `results.json`。
导出默认要求 `verified`；有 `screen` 时还要求筛选为 `include`，`exclude`、`pending_manual`、
缺失/无效决定和模型失败的待处理记录均不导出。无需模型筛选时使用
`steps: [plan, search, verify, export]`。保留人工待处理记录，报告 `exported_count`；
trial 只保留注册数据，不写成论文 RIS。`citation` CLI 只下载/转换格式，不自动做 `expected` 核验。

## WPIRONMAN 中转

WPIRONMAN 是可选的 OpenAI-compatible 模型入口，当前 runner 用于摘要级 `screen`；
`plan.json` 根据 YAML 本地生成，研究计划或规则可先在客户端整理。
它不是论文来源、数据库、引用验证器，也不替代 Crossref、PubMed、OpenAlex、Europe PMC 或 Semantic Scholar。

```bash
export ACADEMIC_SEARCH_LLM_BASE_URL=https://api.wpironman.top/v1
export ACADEMIC_SEARCH_LLM_API_KEY=你的中转密钥
export ACADEMIC_SEARCH_LLM_MODEL=你的模型名
export ACADEMIC_SEARCH_LLM_PROTOCOL=responses_http
```

默认只发送标题、摘要、标识符和获准元数据；全文必须显式设置 `privacy.allow_full_text: true`。
密钥不得进入日志、manifest 或 prompt artifact。中转超时、限流或返回坏 JSON 时，
失败的模型步骤标记为 `skipped`，学术检索、核验和审计继续；待人工筛选记录不进入 RIS。

## 结果契约

每次成功的 `search_papers` 返回 `search_run`，至少保存 `run_id`、UTC 时间、请求参数、去重前后数量和
`result_fingerprint`。每条记录保留稳定 `record_id`、`sources`、`source_records`、`conflicts`、
`citation_counts` 和 `citation_count_source`。不得合成没有来源的“总引用数”。

统一 `filters` 支持日期、语言、作者、文献类型和强标识符；`ranking` 可设为 `relevance` 或 `none`。
相关性排序会写入 `ranking_score`、`ranking_reasons` 和 `score_version`，只表示检索相关性，不表示证据质量。
含中文的查询会在 `query_analysis` 中给出 `contains_cjk`、`latin_terms`、`cjk_terms` 和 `mesh_required`。

详细查询构建、来源分层、引用文件和工作流见：

- [检索工作流](references/search-workflows.md)
- [来源分层](references/source-tiers.md)
- [引用文件](references/citation-files.md)

## 证据规则

- 不编造元数据、摘要、引用次数、标识符、开放获取状态、全文结论或试验结果。
- 不把预印本描述为同行评审论文，不把 trial 注册描述为已发表研究。
- 不因为来源适配器存在就声称它本次已查询；以实际 `sources_queried` 为准。
- 不把引用数量、图谱度数或模型排序当作证据质量或因果证据。
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| .agents/plugins/marketplace.json | 679 | c0c85b6ac234749f |
| .claude-plugin/marketplace.json | 692 | e3e503d2f0adc62e |
| .github/dependabot.yml | 271 | f2b9f03020b1c136 |
| .github/workflows/ci.yml | 1365 | c7de45d82c5d0c4a |
| .github/workflows/network-smoke.yml | 735 | e7fe6bd66317eafd |
| .github/workflows/publish.yml | 2135 | 1d2b19074ca774f5 |
| .gitignore | 94 | ba8ebe6f587052e1 |
| LICENSE | 1061 | 19c109d0a12b72bc |
| README.md | 28507 | 6446d4defdac90ae |
| SKILL.md | 9028 | 68293f30edcec627 |
| config/mcp-snippet.json | 539 | f988aa2c2de0477a |
| config/settings-snippet.json | 59 | 9c1eaadd248ee983 |
| config/triggers-academic-search.toml | 558 | b43f09b234ca62fc |
| docs/assets/academic-search-citation-verification.png | 129451 | 8288f9ca601f8a6b |
| docs/assets/academic-search-pubmed-mesh.png | 122374 | ad9b26d24825e3e5 |
| docs/assets/academic-search-topic-scoping.png | 169113 | 69393d0bad43167a |
| docs/community-growth.md | 5091 | 931fbea1e2475509 |
| docs/community-submissions.md | 5332 | 40f2b7e25db3bcd1 |
| docs/examples/citation-verification.md | 1628 | 6d5b4944a787ddc2 |
| docs/examples/pubmed-mesh.md | 1922 | 1702b4b33c2a885b |
| docs/examples/topic-scoping.md | 2164 | 3a726e026fb1b69f |
| docs/installation.md | 5848 | eb80c7ab8a4cfbbf |
| docs/maintenance.md | 6416 | 0d19105aa5443f8f |
| docs/plans/2026-07-15-academic-paper-search-brand-design.md | 3841 | fe80263579f8a58d |
| docs/plans/2026-07-15-academic-paper-search-brand-implementation.md | 10322 | 147c31da6a9ef2a0 |
| docs/plans/2026-07-15-pypi-plugin-redesign-design.md | 6355 | dcb2a24e880e11a5 |
| docs/plans/2026-07-15-pypi-plugin-redesign-implementation.md | 9667 | 3fd6c2846946caa5 |
| docs/plans/2026-07-15-readme-skill-star-conversion-design.md | 6053 | 717b00147e83680c |
| docs/plans/2026-07-15-readme-skill-star-conversion-implementation.md | 8944 | 6603bc4220ae25ae |
| docs/plans/2026-07-20-academic-search-source-expansion-design.md | 19056 | 7e512fd1a0b88540 |
| docs/plans/2026-07-20-academic-search-source-expansion-implementation.md | 27246 | 916118fa982fb171 |
| docs/plans/2026-07-31-community-discovery-growth-design.md | 4234 | 37cc8e71dfc5c9eb |
| docs/plans/2026-07-31-community-discovery-growth-implementation.md | 8325 | 388c09e786768325 |
| docs/plans/2026-08-16-readme-relay-promotion-design.md | 1150 | b6a31a7cf0afc29c |
| docs/plans/2026-08-16-readme-relay-promotion-implementation.md | 2828 | 0afcfec34306170e |
| docs/plans/2026-08-24-evidence-grade-search-implementation.md | 10182 | dd4b13bb581fbcd4 |
| docs/plans/2026-08-24-research-workflow-automation-design.md | 5764 | 41f0fe67a89213cd |
| docs/plans/2026-08-24-research-workflow-implementation.md | 1592 | 9811f3e354275f20 |
| docs/plans/2026-08-24-smart-discovery-implementation.md | 1837 | 612afd14c26af458 |
| docs/plans/2026-08-26-citation-graph-design.md | 2390 | 332d6ee3fd2d02b0 |
| docs/plans/2026-08-26-citation-graph-implementation.md | 2843 | 14738e68aafd25aa |
| docs/plans/2026-08-26-relay-visibility-design.md | 1572 | b58cc15e55cd3300 |
| docs/plans/2026-08-26-relay-visibility-implementation.md | 2242 | e53817fc66694033 |
| docs/plans/2026-08-27-readme-skill-redesign-design.md | 1995 | 478cea0696b2a712 |
| docs/plans/2026-08-27-readme-skill-redesign-implementation.md | 3346 | 739e8b42b781902a |
| docs/plans/2026-08-29-clarify-academic-search-skill.md | 1616 | ab4c88c923924ca4 |
| docs/plans/2026-08-29-deepseek-harness-bundle-design.md | 2523 | ae598737c1404a10 |
| docs/plans/2026-08-29-deepseek-harness-bundle-implementation.md | 4893 | a4772a3ae9d0b3a2 |
| docs/plans/2026-08-29-premium-readme-implementation.md | 1396 | 8153219c53b206c4 |
| docs/plans/2026-09-09-workflow-release-skill-fixes.md | 3258 | e07e315f7f23c4d9 |
| install.sh | 1972 | 58e3f2a2f8a53b4a |
| mcp-server/README.md | 1182 | 7ac95213ba917513 |
| mcp-server/academic_search_server.py | 548 | 6de7ba5a261cce93 |
| mcp-server/config.toml | 395 | 6838b27467458c79 |
| mcp-server/requirements.txt | 53 | dc6e75fed15c3836 |
| mcp-server/sources/__init__.py | 394 | 87013ce1d8f568ca |
| mcp-server/sources/arxiv.py | 234 | c0792ac4b38fe2c0 |
| mcp-server/sources/crossref.py | 240 | 25c18b6ae4f3c6fd |
| mcp-server/sources/pubmed.py | 236 | ea69d6c47e6b8008 |
| mcp-server/tests/__init__.py | 40 | be5036e0c0559ed6 |
| mcp-server/tests/test_sources.py | 27432 | 13adb71a21e817cd |
| mcp-server/utils/__init__.py | 359 | 3fe4a38f8922efc5 |
| mcp-server/utils/config.py | 1398 | da1e92409aba06f0 |
| mcp-server/utils/errors.py | 359 | bb1272a161c9c733 |
| mcp-server/utils/logging.py | 1166 | bd34f60b64f54fc5 |
| pyproject.toml | 2426 | 6cbf53464896037a |
| references/citation-files.md | 1959 | 756f3b0d04859da0 |
| references/citation-parser.md | 2755 | 7569d5a42b41c32a |
| references/dedup-engine.md | 1454 | 8358fd66e9f2f52e |
| references/pubmed-28344011.bib | 3410 | 476340d7ac4bb4bc |
| references/pubmed-28344011.nbib | 12205 | 1705f5869235a348 |
| references/pubmed-28344011.ris | 3513 | 62e55bea966681ef |
| references/ris-bibtex-format.md | 4382 | fdd4eaff2a8a070b |
| references/search-strategy.md | 1568 | 510c397cad6e55a3 |
| references/search-workflows.md | 9177 | a1d8885f9487abe6 |
| references/source-tiers.md | 3304 | ae53e26bb5ab2bb2 |
| references/workflows/wf1-multi-source-search.md | 1681 | 5696df60a78c7d9d |
| references/workflows/wf2-citation-verification.md | 943 | b96f621862229d59 |
| references/workflows/wf3-mesh-strategy.md | 627 | 7b9e470ec10dc48b |
| references/workflows/wf4-citation-file-mgmt.md | 856 | ac93c8ff76afc4ab |
| references/workflows/wf5-reference-mgmt.md | 1185 | 2b19f942cbb65bdf |
| scripts/check_wheel.py | 8053 | a43b65d74e4710fe |
| scripts/converters.py | 327 | c0960efd2b1dce63 |
| scripts/format-converter.py | 19051 | 62299022711010ab |
| scripts/preflight.py | 586 | 4fc0d32b7cb9d692 |
| scripts/sync_skill.py | 1801 | 9c00d355fc0eae61 |
| src/nature_academic_search/__init__.py | 91 | d935e4b0feffb403 |
| src/nature_academic_search/__main__.py | 175 | 1ba8f35b5fc12932 |
| src/nature_academic_search/citation.py | 18769 | e91fe050871aeb47 |
| src/nature_academic_search/cli.py | 6402 | d713692207995d4d |
| src/nature_academic_search/config.py | 2947 | f979ccc06163e94f |
| src/nature_academic_search/conversion/__init__.py | 279 | 30d6c79407fd4f6b |
| src/nature_academic_search/conversion/converters.py | 18286 | e828b54497b5c9f7 |
| src/nature_academic_search/discovery.py | 298 | f90e93122990abfb |
| src/nature_academic_search/errors.py | 710 | e232e5d477472536 |
| src/nature_academic_search/filters.py | 9304 | 4cac13c6e7f8c3b7 |
| src/nature_academic_search/graph.py | 10136 | 87ff39efa60a043a |
| src/nature_academic_search/http.py | 2972 | 4d350d3986ddafff |
| src/nature_academic_search/installer.py | 4096 | 1a66b99aeb4410b4 |
| src/nature_academic_search/logging.py | 1195 | 67596640ef174cd1 |
| src/nature_academic_search/preflight.py | 9874 | 15264939ce4368f8 |
| src/nature_academic_search/provenance.py | 3309 | aeb9630078203760 |
| src/nature_academic_search/ranking.py | 3954 | 9391a125aa9077c8 |
| src/nature_academic_search/relay.py | 6672 | 425ac1411a1230d6 |
| src/nature_academic_search/search.py | 18188 | f6c2230ecd2b416a |
| src/nature_academic_search/server.py | 18053 | 8d2e36c712035a3a |
| src/nature_academic_search/sources/__init__.py | 506 | f30b650d8801666b |
| src/nature_academic_search/sources/arxiv.py | 11330 | f9ea4a5a4b9c8f77 |
| src/nature_academic_search/sources/clinicaltrials.py | 5938 | 326d3d4f69f9d4b6 |
| src/nature_academic_search/sources/crossref.py | 10428 | b68b432b90c3a99a |
| src/nature_academic_search/sources/europe_pmc.py | 10729 | dc85f3bdf1b28d55 |
| src/nature_academic_search/sources/openalex.py | 11746 | 9a3947c11f5f0f95 |
| src/nature_academic_search/sources/pubmed.py | 14962 | b27cc9e780029648 |
| src/nature_academic_search/sources/registry.py | 2373 | 8e4b846568324566 |
| src/nature_academic_search/sources/semantic_scholar.py | 7973 | 44b36247176e7725 |
| src/nature_academic_search/verification.py | 5146 | 9f8ec7f994b04316 |
| src/nature_academic_search/workflow.py | 25624 | 72a24bc0f0b14243 |
| tests/fixtures/sources/clinicaltrials-search.json | 1749 | f3c39d1f640c157b |
| tests/fixtures/sources/europe-pmc-search.json | 605 | c2c4ba2acae8cb1e |
| tests/fixtures/sources/openalex-search.json | 1082 | 0ed154bd2e65ab21 |
| tests/fixtures/sources/semantic-scholar-search.json | 731 | be1c77d3f1385fa9 |
| tests/test_cli.py | 9404 | ad3de72236f7dd58 |
| tests/test_conversion.py | 946 | 11969e97f63875b3 |
| tests/test_discovery.py | 5470 | f10b35702fd5a893 |
| tests/test_discovery_source_queries.py | 2719 | 8508487aaa7e8912 |
| tests/test_graph.py | 4990 | 5052aa659a83b0bf |
| tests/test_graph_sources.py | 5525 | eaebc97f024867b1 |
| tests/test_http.py | 6669 | f7c6e03b4a055f54 |
| tests/test_installer.py | 4218 | 7d19dc458581aec5 |
| tests/test_package_metadata.py | 1341 | 44c37e28dde68894 |
| tests/test_plugin_artifacts.py | 8779 | 1d2c719c769b9447 |
| tests/test_provenance.py | 1055 | f56932007f1c939c |
| tests/test_relay.py | 1746 | 58e9565bb460058f |
| tests/test_release_metadata.py | 13662 | dbe4c7edf6724b25 |
| tests/test_search.py | 20912 | ab3b1820afb507c8 |
| tests/test_server.py | 14294 | 4e1e2c75ff49ab87 |
| tests/test_source_clinicaltrials.py | 4644 | 6897f35c807ed1fe |
| tests/test_source_europe_pmc.py | 5199 | e1bc64704b863b0e |
| tests/test_source_openalex.py | 5100 | 0ca7f6077f7e16e3 |
| tests/test_source_pubmed.py | 2217 | 60786957b7e4d27d |
| tests/test_source_registry.py | 1964 | 866b37233d53d4cd |
| tests/test_source_semantic_scholar.py | 5638 | 8ae706f52fb0b1ab |
| tests/test_sources.py | 1537 | cb619357676ce00e |
| tests/test_verification.py | 2737 | 633e25c44b29b1be |
| tests/test_wheel_smoke.py | 2662 | c3f755c646b40471 |
| tests/test_workflow.py | 15216 | 21c2fe7d5ee8fed6 |

## 6. MCP 关联（文本取证）

未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。

## 7. 副本

逐字节副本：`99-原件/skills/nature-academic-search/`（未改写；已用 SHA-256 复算校验）。
