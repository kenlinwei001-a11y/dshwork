# Skill · ontology-resolution-skill（SK-04）

## 名称与定位

- **名称**：`ontology-resolution-skill`（Skill ID SK-04）
- **一句话**：将候选 Entity 映射到项目 Ontology Registry 中的标准类型、属性和约束。

## 角色

七道工序**第 4 道「本体抽取」**的规范化通道：把自由抽取的实体对齐到领域本体的标准类型体系，保证图谱 schema 一致性（也对应装配侧 resolve_concept 的语义面）。

## 输入

候选 Entity（entity-extraction-skill 输出）+ 项目 Ontology Registry（标准类型/属性/约束）

## 输出

- 映射结果：entity → 标准 type、属性、约束
- 无法映射项：显式标记（新建类型建议 or 待定）

## 执行规则

- 优先映射到已有标准类型；确无对应时显式声明「新建类型建议」，不强行塞进不匹配类型。
- 映射保留依据（文本证据）。
- 属性/约束随类型落地。

## 关系

上游：entity-extraction-skill；下游：relation-extraction-skill、semantic-graph-compilation-skill。
