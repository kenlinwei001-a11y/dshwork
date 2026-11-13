# 执行体不在本包内（单源声明）

自 2026-11-13 起，标准要素抽取的**全部可执行脚本只有一个副本**，位于工作区：

```
skill-update/scripts/            ← 唯一执行体
  run_contract.py                契约执行器（8 个节点，含 --util check / verify）
  validate_node.py               8 道门禁（含 trail_present）
  graph_index.py                 SOP 图落库与反查
  check_gate.py                  通用节点门禁（读 trail，只认最后一条 verify）
  gate_status.py                 前端一次取全量门禁状态
  check_interfaces.py            专家间接口契约校验
  extract_tables 等其余脚本       见该目录
```

本专家包此前带有一份 `scripts/` 副本（37 个文件，其中 `run_contract.py` 55.6KB），
但它**从未被任何工作流节点调用**——节点写的是工作区路径：

```
python3 skill-update/scripts/run_contract.py --node <name> --out <运行目录>
python3 skill-update/scripts/validate_node.py --node <name> --out <运行目录>
```

留着旧副本的唯一后果是让人误以为在跑它（工作区版本 76.2KB，包内 55.6KB，差 20KB）。
故整体移除。

## 分发注意

若要**跨机分发**本专家，需要先把执行体收进包内并让节点改用技能根相对路径。
那是"脚本分离 / toolchain"方案要解决的事，目前有意搁置；届时应一次性收敛，
不要靠一份过期副本假装自包含。
