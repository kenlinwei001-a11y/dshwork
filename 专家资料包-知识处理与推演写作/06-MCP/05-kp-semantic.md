# MCP 连接：kp-semantic

> 本文件由 WorkDSH 会话依据本机真实数据生成，采集时间（UTC）：2026-10-13T07:33:15Z。

## 1. 配置

| 字段 | 值 |
|---|---|
| 显示名 | kp-semantic |
| 连接 key | custom-kp-semantic |
| connectorId | __custom__ |
| serverName | kp-semantic |
| 传输 | stdio |
| 端点 | stdio · /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python |
| 启用状态 | true |
| 注入模式 | 始终注入 |
| 作用域 | 全局 |
| 鉴权模式 | none |
| 连接策略 | inherit |
| 健康状态 | healthy |
| 最近成功检查 | 2026-10-13T07:33:04.875Z |
| 诊断码 / 说明 | ok · 最近一次可用性检查通过 |

## 2. 该 server 的业务角色

语义层操作（实体、事实、关系、论断、证据、推理与图谱编译）

## 3. 工具清单（6 个）

| 公开工具名（publicName） | 工具名 | 说明 |
|---|---|---|
| mcp__kp-semantic__resolve_concept | resolve_concept | 语义对齐：字段名 → 标准概念（canonical_name/aliases/kind/unit/formula） |
| mcp__kp-semantic__ossie_import | ossie_import | 从 Apache Ossie 语义模型 YAML 导入概念字典（fields→attribute、metrics→metric、synonyms→aliases） |
| mcp__kp-semantic__ossie_export | ossie_export | 把概念字典导出为 Apache Ossie 语义模型 YAML |
| mcp__kp-semantic__semantic_classify | semantic_classify | 语义分类：判断字段属于新变量/别名/元数据（默认确定性，可插拔接 Jev MCP） |
| mcp__kp-semantic__ontology_export | ontology_export | 导出本体 Schema（对齐 Semantica 的 OWL/SHACL/SKOS：类/属性/约束/词表） |
| mcp__kp-semantic__ontology_import | ontology_import | 从本体 Schema 导入概念字典（SKOS 词表 → 概念） |

## 4. 使用方式

- 在会话/项目的连接器选择中选中该连接后，Host 在 agent/created 生命周期开放对应 mcp__ kp-semantic __* 命名空间。
- 项目「团队知识库」以连接器 kp-mcp（知识处理工具层）的形式引用了知识处理工具层；实际展开为上述 server。
- 没有连接选择时，这些工具不出现在模型的工具面上。

## 5. 边界

- 本包不采集、不保存任何凭据或本机密钥。
- 工具是否存在与工具是否被授权调用是两件事：策略（Tool > Server > Connection）与会话可见性逐层生效。
