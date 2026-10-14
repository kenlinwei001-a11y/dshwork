# 环节 s0 交接说明（README）

- 脚本：`s0_docx2md.py`　退出码：0　耗时：0.8s
- 是否产生变更：否（幂等）　must_change：False

## 我产出了什么（自报，见 manifest_A.json）
- `build/doc-clean/大数据研究中心可研.md`（170597 B）

## 给下游的说明
- 声明的产物 glob：["build/doc-clean/*.md"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：b9d66d2df74fb4e70def331eec88e7eda36885790c3fef30fe",
  "derived_md": "build/doc-clean/大数据研究中心可研.md",
  "derived_md_sha256": "e906e68b385d4de7a652babedc6ab9a810dded3ca1c57b7df7e6d8db8e13cb3d",
  "chars": 68518,
  "blocks": 1187,
  "headings": 151,
  "h1": 16,
  "h2": 60,
  "h3": 75,
  "tables": 31
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
