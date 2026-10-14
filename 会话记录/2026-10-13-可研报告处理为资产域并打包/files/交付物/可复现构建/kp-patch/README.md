# kp-patch v1 —— 知识抽取与推演写作环节优化（上游补丁包）

## 这个包解决什么

四类缺陷，全部由实测发现、由确定性判据修复：

| 缺陷 | 根因 | 本包的修复 |
|------|------|-----------|
| 依据漏抽 54 条、设备参数漏抽 32 条 | `validate_extraction` **只遍历产物**，逻辑上查不出遗漏 | `source_ledger.py` + `closure_verify.py` |
| claim 关系缺 cites/restates/causes/derives | 关系词表缺 6 类，`premise_refs`/`derived_from` 无从填充 | `relations_ext.py` + `ontology.py` 词表扩展 |
| 总论章 0 论断（复述层缺失） | 源侧缺层 | `relations_ext.py` 的 restates 推导 + 契约扩展 |
| 435 条关系端点不可寻址 | 实体未建节点 | `alias.py` + `providers.py` 的 graph provider |

## 安装了什么

### 一、新增 8 个模块（`corpus_pipeline/`，互不侵入）

| 模块 | 作用 | 判据类型 |
|------|------|----------|
| `units.py` | 量纲归一，消除跨单位假缺口 | 数值比较 |
| `alias.py` | 别名/同义归并（difflib，非 LLM） | 字符串算法 |
| `source_ledger.py` | 源侧索引（引用/表/数值/标题/题注/设备参数） | 正则 + XML |
| `closure_verify.py` | 七道闭环 C1–C7 | 集合差 |
| `stage_gates.py` | 分步门禁 S0–S11 + **探针自证** | 集合差/守恒 |
| `objective_criteria.py` | 12 条客观判据 K1–K12 | 确定性算法 |
| `relations_ext.py` | 7 类 claim 关系 + 应有关系推导 | 规则推导 |
| `providers.py` | **可替换环节接缝**（entity/relation/reasoning/graph） | — |

### 二、修改 4 个现有文件（插入式，均有 `.bak`）

| 文件 | 插入内容 |
|------|----------|
| `corpus_pipeline/ontology.py` | 论断级关系词表扩展（引用 `relations_ext`） |
| `corpus_pipeline/spec.py` | 契约扩展 30 → 32：`chunks/sentences.jsonl`、`source_ledger.json` |
| `mcp/server.py` | 6 个工具 schema + dispatch 分支 |
| `mcp/mcp-config.json` | `tools.verify` 分组 |
| `corpus_pipeline/groups.py` | 新增 `verify` 分组 |

### 三、新增 6 个 MCP 工具（TOOLS 65 → 71，新增 `verify` 组）

```
build_source_ledger     生成源侧索引（门禁前提）
verify_closure          七道闭环校验
stage_gate              分步门禁 S0–S11（含探针标定）
objective_verify        12 条客观判据
apply_claim_relations   按规则推导并合并 claim 关系（幂等）
provider_status         可替换环节的 provider 与能力表
```

### 四、5 个 skill 增量（插入式，标记 `<!-- kp-patch:v1 -->`）

| skill | 增量 |
|-------|------|
| `knowledge-processing` | 三道机制（源侧索引/闭环校验/分步门禁）+ 契约 30→32 |
| `knowledge-processing-toolchain` | 客观判据清单 + 三条铁律（判定不消费 LLM 意见） |
| `extraction-quality-audit-skill` | 闭环审计七道 + 量纲归一 + 探针自证 |
| `semantic-graph-compilation-skill` | 7 类论断级关系 + 复述层必须成层 |
| `graph-deductive-writing-skill` | 返回契约增 `unreferenced_nodes`（reason 固定枚举） |

## 安装

```bash
cd kp-patch
python install.py --check      # 体检
python install.py              # 装模块 + 补丁 3 个文件
python install_mcp_tools.py    # 注册 MCP 工具（schema + dispatch + 分组）
python apply_skills.py --skills-dir /Users/apple/.agents/skills
```

回滚（各自独立，从 `.bak` / `.bak2` 恢复）：

```bash
python install.py --rollback
python install_mcp_tools.py --rollback
python apply_skills.py --rollback
```

## 验证（安装后实测）

```
闭环   verify_closure      → pass 3 / FAIL 4 / invalid 0
门禁   stage_gate          → pass 7/12，探针作废 0
判据   objective_verify    → pass 4 / FAIL 7 / invalid 1，judgment_required 3
索引   build_source_ledger → 引用 155 / 表 31 / 带单位数值 196 / 标题 151 / 题注 42 / 设备参数 32
provider_status            → entity/relation/graph 均为本地默认实现，9 项能力判据全部 ready
```

## 把某个环节换成外围实现（provider 接缝）

门禁只依赖 `providers.py` 的接口契约，**换实现不需要改任何判据**：

```python
from corpus_pipeline.providers import register_provider

class XxxEntityProvider:                      # 任意实现
    name = "xxx-entity"
    capabilities = {"extract", "disambiguate"}   # 必须如实声明能力
    def extract(self, text): ...
    def disambiguate(self, names): ...

register_provider("entity", XxxEntityProvider())
```

**能力缺省即 `invalid`，不是 pass**：若替换后的 provider 未声明
`extract` / `reasoning` / `graph_write`，则依赖该能力的判据（C4、C7、K8）
自动标 `invalid`，**不会因为「没查出问题」而被计为通过**。

## 设计要点（为什么这样做）

1. **源不可枚举，则「漏了什么」不可问** —— 所以先建索引，再做集合差。
2. **索引必须由与抽取无关的方法生成** —— 否则继承同一盲区，差集恒为空。
3. **门禁放在可重做单元的出口** —— 早一步拦住 = 重做该单元；晚一步 = 重做全部 + 归因丢失。
4. **判据必须客观** —— 只用集合差/守恒/正则/数值比较/哈希/图算法/枚举/覆盖率；
   判不了的记 `judgment_required`，**既不放行也不自判**。
5. **探针必须自证** —— 未过标定的探针输出 `invalid`，不得输出「无误」。
6. **判定不消费 LLM 的意见** —— LLM 产出候选，工具判定候选是否合格。
