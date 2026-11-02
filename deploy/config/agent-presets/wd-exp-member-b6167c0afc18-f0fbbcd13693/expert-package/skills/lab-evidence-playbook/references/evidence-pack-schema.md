# 证据包 schema（v1.0）

证据包是**规则无关**的事实集合。它回答「报告与记录里写了什么、写在哪」，不回答「符不符合」。

## 1 顶层

~~~json
{
  "schema_version": "1.0.0",
  "report_id": "202203001",
  "generated_at": "2026-10-22",
  "report": {},
  "documents": [],
  "methods": [],
  "instruments": [],
  "fields": [],
  "records": {},
  "missing": [],
  "consistency_flags": [],
  "stats": {}
}
~~~

## 2 report（报告元数据）

| 字段 | 说明 |
|---|---|
| report_no | 报告编号（原文） |
| lab / client | 检测机构 / 委托单位 |
| sample_type / sample_count | 样品类型与数量 |
| sample_dates / receive_dates / test_dates | 采样、接收、检测日期（原文） |
| report_date | 报告日期 |
| conclusion | 结论原文（如有） |

## 3 documents（文档清单）

~~~json
{ "doc_id": "D10", "doc_type": "report", "title": "检测报告", "file_name": "6-检测报告.pdf",
  "sha256": "…", "pages": 5, "ocr": false, "status": "PARSED", "parse_note": null }
~~~

status：PARSED / PARTIAL / UNREADABLE / MISSING。

## 4 methods（方法声明）

~~~json
{ "analyte": "总磷", "declared": "GB 11893-89", "standard_id": null,
  "method_match": "mismatch", "doc_id": "D10", "page": 5, "quote": "水质 总磷的测定 钼酸铵分光光度法 GB 11893-89" }
~~~

method_match：match / mismatch / unknown。由报告声明与库内标准比对得出，不改写原文。

## 5 instruments（仪器）

~~~json
{ "name": "紫外可见分光光度计", "model": "UH5300", "code": "N-187", "doc_id": "D10", "page": 5 }
~~~

## 6 fields（字段级证据）

通用字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| evidence_id | 是 | EV-0001 |
| field | 是 | 字段名（见字段字典） |
| value / text | 是 | 数值或文本 |
| unit | 否 | 单位 |
| sample_id | 否 | 样品编号 |
| doc_id / doc_type | 是 | 来源文档 |
| page | 是 | PDF 页码 |
| block_id | 否 | 表格/段落 ID |
| char_start / char_end | 否 | 字符区间 |
| quote | 是 | 原文引文，可检索 |
| confidence | 是 | 0–1 |
| status | 是 | LOCATED / UNLOCATED |
| ocr | 否 | 是否 OCR |

## 7 records（过程记录分册）

~~~json
{
  "calibration": [ { "analyte": "总氮", "points": [], "intercept": null, "slope": null, "r": null, "evidence_id": "EV-0101" } ],
  "blank": [],
  "duplicate": [],
  "spike": [],
  "qc_sample": [],
  "reagent": [],
  "environment": [],
  "instrument_run": [],
  "sample_chain": []
}
~~~

每类记录沿用 fields 的 span 契约；表格式记录用 rows 数组逐行。

## 8 missing（缺失清单）

~~~json
{ "doc_type": "reagent_record", "expected_by": "HJ 671 5.x / 原始记录",
  "reason": "报告包内未提供试剂配制记录", "impact_category": "C4" }
~~~

只写影响类别（C1–C8），不写具体规则 ID。

## 9 consistency_flags（一致性初筛）

~~~json
{ "type": "method_mismatch", "detail": "报告总磷方法 GB 11893-89，库内标准 HJ 671-2013",
  "doc_id": "D10", "page": 5, "severity_hint": "high" }
~~~

type：method_mismatch / value_conflict / date_conflict / sample_count_conflict / instrument_conflict / unit_conflict / missing_signature。

## 10 stats

文档数、字段数、LOCATED 比例、OCR 页数、缺失项数、flags 数。

## 11 入库映射

| 证据包 | 数据库 |
|---|---|
| documents | report_document |
| fields | report_evidence |
| report / methods | report、report_standard |
| missing / flags | 由审核专家读取证据包，或写入 audit_result 的 context |

## 12 校验

- 每个 field 有 quote 且能在原文检索命中；命中不了标 UNLOCATED。
- 每个文档有 sha256；同文件重复出现只登记一次。
- 数值带单位；百分比、mg/L、μg/L 不混。
- 表格行数与报告声明样品数一致；不一致登记 flag。
- 方法声明逐字保留，不改写标准号/年号。
