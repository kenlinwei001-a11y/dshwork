# Skill · document-parsing-skill（SK-00）

## 名称与定位

- **名称**：`document-parsing-skill`（Skill ID SK-00）
- **一句话**：将 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，并保留页码、段落、表格和原文定位信息。

## 角色

七道工序**第 1 道「归一化」**的语义承载：把异质文档格式统一为 Document IR（统一中间表示），是所有下游工序的输入源。生产可用 docling / unstructured / PyMuPDF / python-docx / openpyxl 等库承载。

## 输入

- 文档文件：PDF / DOCX / XLSX / PPTX / 扫描件
- project_id、document_id、version_id

## 输出

统一 Document IR，含：
- 页面、段落、表格结构化
- 页码、段落号、原文定位信息（供后续证据级溯源）
- 稳定 ID 与 provenance 字段

## 执行规则

- 只使用输入中可提取的信息，不编造内容。
- 结果绑定 project_id / document_id / version_id。
- 解析失败（扫描件 OCR 等）显式标记，不静默跳过。

## 关系

下游：semantic-chunking-skill（切块）→ sentence-segmentation-skill（分句）→ 各抽取技能。
