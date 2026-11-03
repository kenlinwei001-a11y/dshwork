# 技能：knowledge-processing

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-03T02:37:14Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 元数据

| 字段 | 值 |
|---|---|
| name | knowledge-processing |
| description | 把文档/语料（docx/pdf/md）经七道工序处理为结构化知识图谱语料包，产出 30 个契约文件（含脱敏骨架）。触发：跑「归一化→骨架→切块→本体→回放→质量→脱敏索引」流水线、产出图谱/脱敏骨架、或使用 kp_toolkit / corpus_pipeline / MCP 工具（5 组 65 工具）时。与 knowledge-processing-toolchain 分工：本 skill 管完整流水线与 30 文件契约，toolchain 管工具+LLM 分层方法论。 |

## 2. 位置与来源

| 项 | 值 |
|---|---|
| 来源类型 | 用户/共享技能根 |
| 目录 | /Users/apple/.agents/skills/knowledge-processing |
| 所属插件 | （非插件内置） |
| 文件数 | 3 |
| 体积 | 82.0 KB |
| 被忽略文件 | SKILL.md.v2bak（编辑器备份/系统文件，不进入副本） |

## 3. 引用关系

- 本次范围内专家配备：**未被范围内专家配备**
- 全部专家引用（含范围外）：标准要素抽取专家（expert-131e1b3979fe）

## 4. SKILL.md 正文（全文）

~~~markdown
---
name: knowledge-processing
description: "把文档/语料（docx/pdf/md）经七道工序处理为结构化知识图谱语料包，产出 30 个契约文件（含脱敏骨架）。触发：跑「归一化→骨架→切块→本体→回放→质量→脱敏索引」流水线、产出图谱/脱敏骨架、或使用 kp_toolkit / corpus_pipeline / MCP 工具（5 组 65 工具）时。与 knowledge-processing-toolchain 分工：本 skill 管完整流水线与 30 文件契约，toolchain 管工具+LLM 分层方法论。"
---

# 知识处理（Knowledge Processing）

## 建图能力分层：七道工序 vs 轻量路径（V3.2 新增）

**本 skill 处理「完整建图」；同一条链路上还有一档「轻量建图」由推演写作专家承担。**

| | **完整建图（本 skill）** | **轻量建图（推演写作专家阶段 -1）** |
|---|---|---|
| 入口 | `corpus_run` 七道工序 | `doc_facts.to_provided_facts` |
| 抽取 | 实体/事实/关系/Claim/Reasoning/Evidence + 脱敏骨架 | 原生表格 + 固定句式正则 |
| 产出 | 语料包 30 文件 + `chunks.jsonl` + `skeletons.jsonl` | `graph.json`（八类节点） |
| 耗时 | 分钟级，多次 LLM | 秒级，零 LLM |
| 适用 | 沉淀资产、跨项目复用、要条款库 | 单份材料、只写一份报告 |

### 判定

```
要 skeletons.jsonl / chunks.jsonl / 脱敏骨架  → 必须走本 skill
要跨项目 library_* 借形                       → 必须走本 skill
只写这一份报告，材料以表格为主                 → 轻量路径即可
材料是散乱叙述、隐性事实多                     → 必须走本 skill
```

### 两档的衔接

```
轻量起步 → graph.json → 写作
                ↓ 后续要沉淀
完整重跑 → 语料包（覆盖 graph.json，schema 相同）
```

**两档共用 `instantiate_project` 与 `COMPUTE_SPEC`**，所以「借形不借值」约束一致；轻量的 `graph.json` 可直接作为完整建图的对照基线。

### 边界

- 本 skill **不负责**轻量路径的 `doc_facts` / `graph_from_project`（那是推演写作专家阶段 -1 的工具）。
- 但**两档的判定标准必须一致**：`claim_type` 四类、证据 E0~E6、`range_known` 三态 —— 改动时全链同步。

### 轻量产物**不可发布**（三质量关口的实测结论）

用 `run_all_gates` 对轻量产物（项目图库目录）实测：

| 关口 | 结果 | 原因 |
|---|---|---|
| **QG1 来源可信度** | ✗ | 缺 `meta.source_fingerprint`、文档版本号（轻量不做来源登记） |
| **QG2 语义完整性** | ✓ | Claim 结构、关系 from/to/type、证据来源都合法 |
| **QG3 资产可复用性** | ✗ | 无 `reuse/domains.yaml`（16 域）、无 `constraints`（复用边界） |

**结论**：

```
轻量产物（graph.json / 项目图库）
   → 只过 QG2 → **只能自用写作，不得 library_publish 到资产库**
   → 要发布 → 必须走完整七道工序（QG1+QG2+QG3 全过）
```

**判定口诀**：
- 要写报告 → 轻量够（QG2 过）
- 要进资产库 → 必须完整（QG1+QG3 是准入门槛）

**禁止**：不得为了让轻量产物过 QG1/QG3 而放宽门禁必填项 —— 那会让「不可复用」的东西混进资产库。

## 目的

把一份历史稿件（docx/pdf/md）经七道工序产出「语料包」：30 个契约文件，供写作 Agent 使用。写作 Agent 只拿脱敏骨架，永远拿不到原文。

## 何时使用

- 用户要求「把稿件处理成语料包」「跑七道工序」「产出语料包」
- 用户要求「结构化知识图谱」「脱敏骨架 skeletons.jsonl」「30 文件契约」
- 用户上传 docx/pdf 要求处理为可溯源、可审计的图谱
- 用户提到 kp_toolkit / corpus_pipeline / kp-*（5 组 MCP）工具

不适用：单纯的文本总结/改写（通用写作）；图谱尚未构建时的自由写作。

## 项目位置

代码工程：`/Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/`（kp_toolkit、corpus_pipeline、mcp/server.py）。

## 工序依赖与门禁总表

```
S1 归一化 ──┬─→ S1b 表格解析 ──┐
            └─→ S2 骨架 ──→ S3 切块 ──┴─→ S4 本体抽取
                                              ↓
                                        S5 推演回放
                                              ↓
                                        S6 质量登记
                                              ↓
                                        S7 脱敏索引
```

| 门禁 | 不通过的后果 |
|---|---|
| S1 归一化 | 回不到原文，溯源链断 |
| **S1b 表格** | **列名丢失，subject 退化** |
| S2 大纲 | 法定章节漏写 |
| S3 切块 | 切块丢失内容 |
| S4 抽取 | 论断/证据分类错，写作口径错 |
| S5 派生 | 规则静默跳过，数值无来源 |
| S6 质量 | 假缺泛滥，公信力崩塌 |
| S7 脱敏 | 跨项目复用失效 |

**任何一项 covered < total → 装配侧拒绝发布。**

## 运行方式

```bash
cd /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert
# 七道工序全链路（docx/pdf 解析需 venv 里的 pymupdf/python-docx）
.venv/bin/python -m corpus_pipeline.cli run 稿件.docx --out 语料包目录
# 确定性工具层自测
python3 -m kp_toolkit.test_kp_toolkit
python3 -m corpus_pipeline.test_pipeline
python3 -m corpus_pipeline.test_llm_extraction
```

`run_pipeline` 关键参数：

- `legal_outline`：法定大纲列表（工序 2 覆盖校验用）
- `extractions`：LLM 语义抽取输出（缺省时工序 4 降级为数值占位）
- `original_path`：原稿路径（落盘 source/original.<ext>）

## 确定性 vs 语义（tool+LLM 分层）

- 确定性步骤（分句/分块/建图/溯源/数字·时间冲突/schema 校验）→ kp_toolkit 代码，零 LLM，可复现可单测。
- 语义步骤（实体/事实/关系/Claim/证据/推理抽取、证据判断、推演写作）→ LLM 结构化输出 + schema + validator + 重试（复用 20 个抽取技能）。
- 分层方法论详见 knowledge-processing-toolchain skill。

## 铁律

- 冲突一律「待审」呈现，不擅自改数字或补口径。
- 缺失事实保持显式未知（TODO/待补充），绝不编造。
- 数值单源存在图节点；正文可反向回读为图谱节点。
- 能确定性的绝不交给模型；需要语义的才调 LLM，且必须结构化 + 校验。

<!-- kp-patch:v1 -->

## 资源导航（工序细节与深度纪律已下沉 references/）

- `references/工序与契约.md` — 7 节
- `references/深度纪律.md` — 12 节

## 四个已落地的性能/质量工具（可执行，不是建议）

七道工序跑一次 34 s，其中 **32 s 在读 YAML**，纯计算只占 0.01 s。
下面四个模块是为此加的，**都有退出码或 raise，不能靠"记得用"**。

### ① `fastload` —— YAML 带 JSON 缓存

```python
from corpus_pipeline.fastload import load, warm, clear

d = load(Path("graph/nodes.yaml"))     # 首次慢（建缓存），之后 0.08~0.2 s
warm(corpus.rglob("*.yaml"))           # 批量预热
clear(corpus)                          # 清缓存
```

**实测**：`nodes.yaml` 1.87 MB / 2410 节点
```
yaml.safe_load : 36.18 s
json.loads     :  0.08 s      → 快 388~797 倍
```

**源码保持 YAML**（可 git diff），缓存名 `xxx.yaml.json`，不进包。

### ② `shard_index` —— 建完图必须建索引

```python
from corpus_pipeline.shard_index import build, build_inverted, assert_shardable

build(corpus)            # 5.3 s → shards/（104 节 / 235 分片 / 索引 23 KB）
build_inverted(corpus)   # 0.6 s → shards/inverted.json（169 前缀 / 20 单位 / 24 规则 / 27 dep）
```

**为什么必建**：`nodes.yaml` 一次全读 36 s，写一节只需几十个节点。
实测 `browse()` 0.001 s / `resolve(section)` 0.0033 s。

**分片键不限于章节**（无章节的客户材料同样可分片）：
```python
query(corpus, unit="万元")                 # 按单位
query(corpus, label_prefix="建")           # 按名字前缀
resolve_closure(corpus, "R-总投资构成")     # 按规则取依赖闭包 ← 最贴合写作
```

### ③ `bench_perf` —— 性能回归（退出码非 0）

```bash
python -m corpus_pipeline.bench_perf <语料包>
```

阈值（实测 × 3 倍余量）：
```
browse            <= 0.05 s   实测 0.0012
resolve           <= 0.10 s   实测 0.0142
write_41_sections <= 3.00 s   实测 1.12~2.25（波动大，见下）
cache_hit_nodes   <= 0.50 s   实测 0.051
```

**超阈值即 FAIL** —— 这是机制，不是提醒。

**阈值变更必须带记录**（`bench_perf.THRESH_NOTES`）：

```python
THRESH_NOTES = {
    "write_41_sections": [
        {"at": "v1.0", "value": 2.0, "why": "按分片理论值 0.136 s × 14.7 拍定"},
        {"at": "v1.1", "value": 3.0, "why": "实测 2.25 s（内部回读 nodes.yaml），2.0 会误报"},
    ],
}
```

**当前 3.0 s 不是目标，是现状**：
- 分片理论值 0.136 s
- 实测 1.12~2.25 s（波动）
- 差距原因：`query`/`closure` 内部仍回读 `nodes.yaml`
- **优化路径**：`resolve` 返回时带出节点对象，消除回读 → 预期 0.2 s，届时阈值应收紧到 0.6 s

### ④ `caliber_check` —— 口径冲突判定

```python
from corpus_pipeline.caliber_check import classify_conflict

r = classify_conflict("土建工程", 6780, 9350, fact_source_map)
# {'kind':'caliber_difference', 'confidence':'推测，待客户确认',
#  'reason':'规则值高于客户值 → 规则含装饰装修/外立面/装配式增量'}
```

**它解决什么**：两个数不等，可能是「算错了」也可能是「口径不同」。
没有口径信息时只能一律标冲突；有了 `mapping.calibers` 就能判。

**置信度三级，且都不得据此认定某个值正确**：
```
确定            ← 客户明确说了口径
推测，待客户确认  ← 按领域常识推断
待确认口径       ← 有口径位但方向不在已知清单内
```

### ⑤ `doc_facts` 的章节归属（解析环节必须记）

```python
from corpus_pipeline.doc_facts import to_provided_facts
r = to_provided_facts("客户材料.md")
# 每条 fact 带 section（MD 的表格行号 → 标题归属）
# 实测：121 条全部有章节
```

**为什么必须记**：不记 section，下游无法按章节分片，只能全读。

---

## 七道工序 + 三件必做动作

```
① 归一化  →  ② 骨架  →  ③ 切块  →  ④ 本体
                                       ↓
                             ⑤ 回放  →  ⑥ 质量  →  ⑦ 脱敏
                                       ↓
        ┌──────────────────────────────┴──────────────────┐
        │ 必做 A  fastload.warm(corpus)      预热缓存       │
        │ 必做 B  shard_index.build(corpus)  建分片索引     │
        │ 必做 C  bench_perf(corpus)         性能回归       │
        └─────────────────────────────────────────────────┘
```

**A/B 不做 → 下游全读变慢 500 倍；C 不做 → 性能回归无人发现。**
~~~

## 5. 资源清单

| 文件 | 字节 | SHA-256（前 16） |
|---|---|---|
| SKILL.md | 11327 | c4a1e1b64ce491df |
| references/工序与契约.md | 36216 | a0532b1b79630676 |
| references/深度纪律.md | 36405 | 5f12acfdd6764c39 |

## 6. MCP 关联（文本取证）

正文或资源中出现：`kp_toolkit`、`semantica`。对应连接见 `06-MCP/`。

## 7. 副本

逐字节副本：`99-原件/skills/knowledge-processing/`（未改写；已用 SHA-256 复算校验）。
