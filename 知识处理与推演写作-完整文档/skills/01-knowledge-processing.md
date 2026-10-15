# Skill · knowledge-processing

## 名称与触发

- **名称**：`knowledge-processing`（调用 `/knowledge-processing`）
- **一句话**：把文档/语料（docx/pdf/md）经七道工序处理为结构化知识图谱语料包，产出 30 个契约文件（含脱敏骨架 skeletons.jsonl）。

## 角色

体系总纲技能——覆盖「知识处理」主题的完整流水线与 30 文件产物契约（区别于 knowledge-processing-toolchain 只覆盖工具+LLM 分层方法论）。

## 触发条件

- 用户要求「把稿件处理成语料包」「跑七道工序」「产出语料包」
- 用户要求「结构化知识图谱」「脱敏骨架 skeletons.jsonl」「30 文件契约」
- 用户上传 docx/pdf 要求处理为可溯源、可审计的图谱
- 用户提到 kp_toolkit / corpus_pipeline / kp-* MCP 工具

不适用：单纯的文本总结/改写（通用写作）；图谱尚未构建时的自由写作。

## 内容要点

- **七道工序**：归一化→骨架抽取→切块→本体抽取→推演回放→质量登记→脱敏索引，含每道产出。
- **运行方式**：`.venv/bin/python -m corpus_pipeline.cli run 稿件.docx --out 语料包目录`；三个自测命令（kp_toolkit / test_pipeline / test_llm_extraction）。
- **30 文件契约**：主存/副本/可变/Agent 形式；安全边界——写作 Agent 只拿 skeletons.jsonl，永不拿 chunks.jsonl。
- **工具+LLM 分层**：确定性走 kp_toolkit（零 LLM），语义走 LLM+validator（复用 20 个抽取技能）。
- **MCP**：5 组 65 工具（processing/assembly/library/semantic/reserved）。
- **嵌入**：fastembed + paraphrase-multilingual-MiniLM-L12-v2（384 维）+ parquet。
- **存储**：PG/Neo4j/Qdrant 适配器 + 文件系统回退（KP_PG_DSN / KP_NEO4J_URI / KP_QDRANT_URL）。
- **铁律**：冲突待审、缺失显式未知、数值单源在图节点、正文可反向回读。

## 绑定专家

知识处理专家（expert-a54010bbb24e）体系内使用；发布在 shared-agents 作用域。
