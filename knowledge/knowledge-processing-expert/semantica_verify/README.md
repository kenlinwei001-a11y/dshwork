# Semantica 外部核验

对一份**已建好的知识图谱语料包**做外部核验。只读语料包，产物写入 `外部核验/`。

## 前提

| 项 | 值 |
|----|----|
| venv | `/Users/apple/.venvs/semantica`（semantica 0.7.0） |
| LLM 依赖 | `openai` + `instructor`（缺则 DeepSeek provider 报 not available） |
| 凭据 | `~/.semantica/env`（600，含 `DEEPSEEK_API_KEY`） |
| KG | `/Users/apple/.semantica/graph.json` |

## 用法

```bash
KP_CORPUS_DIR=/path/to/语料包 sh semantica_verify/run_all.sh
```

脚本可用 `KP_CORPUS_DIR` 覆盖语料包路径，默认取脚本上级目录下的同名语料包。

## 链序

1. `semantica_p0.py` 冲突检测互证（P0-a）
2. `semantica_p1p2.py` 实体消歧 + PROV-O 溯源 + 切块对照（P1/P2）
3. `semantica_p1a_refine.py` 去重候选按「值是否一致」分类
4. `semantica_report.py` 人工复核 17 组 + 生成核验报告
5. `semantica_rule_judge.py` 规则判官（替代 JEV）+ 17 组校准
6. `semantica_normalize_queue.py` 生成待人工判断队列
7. `semantica_refine_confidence.py` 差异片段判据 + confidence 分档校准
8. `semantica_merge_judges.py` 规则判官与 LLM 判官合并
9. `semantica_make_review_md.py` 生成人工判断清单（MD + TSV）

LLM 两脚本 `semantica_judge_test.py` / `semantica_judge_bulk.py` 需密钥，插在步骤 5 与 8 之间。

## 铁律约束

1. **禁用 `ConflictResolver`**：其 7 种策略会产出单一决议值，违反「冲突一律待审」。只用 `ConflictDetector`。
2. **归一只产候选**：LLM 判 DIFF 精度 100%（可直接过滤），判 SAME 精度仅 58%（过度合并），合并必须人工确认。
3. **中文抽取必须 method=llm**：pattern 仅英文，ml 依赖 spaCy（本机未装）。
4. **合并未执行**：产物只是队列，不得据自动判定改动语料。

## 校准结果（对 17 组人工标准答案）

| 判官 | 准确率 | 特性 |
|------|--------|------|
| 规则判官（reasoning） | 15/17 = 88% | 负证据优先 |
| LLM 判官（DeepSeek） | 12/17 = 71% | DIFF 精度 100%，SAME 精度 58% |

收敛：1104 组候选 -> 71 条待人工判断（降幅 94%）。

## 铺到其它 DSH 运行时（幂等）

DSH 的 MCP 连接器注册在 `<运行时home>/storages/workdsh_connectors/definitions/*.json`，不经过连接器管理界面。
新增运行时（备份 profile、新 profile）需要同样的定义文件，`install_connector.py` 负责幂等补齐。

```bash
cd semantica_verify
python3 install_connector.py                       # 只检查所有运行时
python3 install_connector.py --apply               # 写入所有运行时
python3 install_connector.py --apply --home /path  # 只处理指定运行时
```

行为约定：

| 情形 | 动作 |
|------|------|
| 定义缺失 | 创建（含 enabled:true 与 env 引用） |
| 已存在且 args/enabled 一致 | **零改动**（幂等） |
| 已存在但不一致 | 备份到 `definitions/ 的上级目录`（时间戳后缀）后覆盖 |
| 默认（不加 --apply） | 只检查，不写盘 |

凭据**不写进定义**：定义只引用 `~/.semantica/env`，密钥始终只存在于那一个 600 文件。
写入后，对应会话需重连（新会话或重启 dsh web）才生效。

## 凭据载入（必须，踩过坑）

Semantica 的 LLM provider 在**构造时**读环境变量。未载入时它**不报错**，而是**静默降级**返回空结果
—— 曾导致 169 个 chunk 的三元组全部为空，日志却显示「成功 169 | 失败 0」。

因此所有需要 LLM 的脚本开头都必须：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from semantica_env import load_env
load_env()          # 缺 key 直接 SystemExit，绝不静默降级
```

`semantica_env.py` 负责从 `~/.semantica/env` 载入 `export` 变量（幂等，不覆盖已有环境变量）。
自检：

```bash
python3 semantica_env.py
#   [OK]   DEEPSEEK_API_KEY
#   [OK]   OPENAI_API_KEY
#   [OK]   OPENAI_BASE_URL
```

可用 `SEMANTICA_ENV_FILE` 指向别的凭据文件（测试用）。
