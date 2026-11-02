---
name: document-parsing-skill
description: "把 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，保留页码、段落、表格与原文定位。触发：解析这份 PDF/Word、把扫描件转成可检索文本、批量导入文档建库。不适用：抽取实体或事实（走 entity-extraction / fact-extraction）。"
---

# Document Parsing Skill

## Skill ID
SK-00

## Purpose
将 PDF/DOCX/XLSX/PPTX/扫描件解析为统一 Document IR，并保留页码、段落、表格和原文定位信息。

## 何时使用

调用条件：已拿到原始文件（PDF/DOCX/XLSX/PPTX/扫描件）；没有文件先索取，不凭描述生成“解析结果”。
- 典型请求：解析这份 PDF/Word｜把扫描件转成可检索文本｜批量导入文档建库
- 不要在此调用：抽取实体或事实（走 entity-extraction / fact-extraction）
## 边界与不适用

- 不做：只产出 IR，不做切片、抽取或改写
- 不做：扫描件识别不清时标注置信度与页码，不猜字
- 缺输入：没有原始文件时先索取文件；不能凭描述生成"解析结果"
