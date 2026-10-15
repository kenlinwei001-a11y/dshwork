# Skill · sentence-segmentation-skill（SK-02）

## 名称与定位

- **名称**：`sentence-segmentation-skill`（Skill ID SK-02）
- **一句话**：将 Chunk 切分为 Sentence，并生成稳定的 Sentence ID，支撑 Claim 追踪和 Semantic Diff。

## 角色

七道工序**第 3 道「切块」**的句子级细分：Sentence 是最小溯源单位，Claim/事实/证据都锚定到 Sentence。生产可用 spaCy / jieba / 正则承载，配合 kp_toolkit 的 segment_sentences 确定性实现。

## 输入

语义 Chunk（semantic-chunking-skill 输出）

## 输出

- Sentence 列表 + 稳定 Sentence ID（确定性：同输入同输出）
- Sentence → Chunk → Document 归属链
- 字符偏移（供证据精确锚定）

## 执行规则

- Sentence ID 必须确定性生成（不依赖 LLM 随机性）。
- 断句规则处理引号、括号、列表项等边界。
- 保留原文定位信息。

## 关系

上游：semantic-chunking-skill；下游：fact/claim/evidence 抽取（以 Sentence 为锚点）、provenance-binding-skill。
