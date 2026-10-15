# Skill · knowledge-processing-toolchain

## 名称与触发

- **名称**：`knowledge-processing-toolchain`
- **一句话**：以「工具 + LLM」分层模式做知识处理。

## 角色

方法论技能——规定「哪些步骤确定性、哪些步骤语义」的判据与执行纪律。两个专家（知识处理专家、推演写作专家）都绑定它。

## 核心原则

**能确定性计算的，绝不交给模型去「猜」；只有真正需要语义理解的，才调用 LLM。**

```
确定性底座（工具层，kp_toolkit，零 LLM，可复现可单测）
  分句 · 分块 · 图谱编译 · 溯源链 · 数字/时间冲突 · schema 校验
        ↓ 输出结构化 JSON
语义层（LLM，结构化调用 + schema + validator + 重试）
  实体/事实/关系/Claim/证据/推理抽取 · 证据充分性判断 · 推演写作
```

## 确定性步骤（工具，不调 LLM）

| 步骤 | kp_toolkit 函数 | 说明 |
|------|-----------------|------|
| 分句 | segment_sentences(text, doc_id) | 稳定 ID，同输入同输出 |
| 分块 | segment_chunks(text, doc_id) | 按标题/空行切块 |
| 图谱编译 | compile_graph(items, project_id, version_id) | 八类节点装配 |
| 图谱校验 | validate_graph(graph) | 悬空引用 / 重复 id |
| 溯源链 | build_provenance(node_id, graph) | 反向追到证据 |
| 数字冲突 | detect_numeric_conflicts(graph) | 待审输出 |
| 时间冲突 | detect_time_conflicts(graph) | 待审输出 |
| schema 校验 | validate_schema(payload, schema) | 失败重试 |

## 语义步骤（LLM，结构化）

- 必须按 schema 输出 JSON，经 validator 确定性校验；不通过→带错误重试（有限次数）。
- 抽取类交给 20 个抽取技能（fact/entity/claim/evidence/reasoning 等）。
- 证据判断用五级：SUPPORT / PARTIAL_SUPPORT / CONTRADICT / CONTEXT / INSUFFICIENT。

## 绑定专家

知识处理专家（expert-a54010bbb24e）、推演写作专家（expert-a0a771c8b0da）。
