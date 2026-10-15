# Skill · semantic-chunking-skill（SK-01）

## 名称与定位

- **名称**：`semantic-chunking-skill`（Skill ID SK-01）
- **一句话**：按照章节、主题和语义边界将 Document IR 切分为稳定的语义 Chunk，供后续抽取和检索使用。

## 角色

七道工序**第 3 道「切块」**的语义承载。与确定性分块工具（segment_chunks）配合：工具给确定性边界，本技能处理语义边界判断（主题漂移、表格/图注独立成块）。

## 输入

Document IR（document-parsing-skill 输出）

## 输出

- 稳定语义 Chunk 列表（章节、主题、语义边界）
- 每个 Chunk 的 span（字符/位置范围）、所属章节
- Chunk 级稳定 ID（支撑 Semantic Diff）

## 执行规则

- 切分保持语义完整：不把一条事实/推导拦腰切断。
- 表格、图注独立成块。
- 输出绑定来源定位；同输入同输出（确定性优先）。

## 关系

上游：document-parsing-skill；下游：sentence-segmentation-skill、各抽取技能、embed_chunks（向量化）。
