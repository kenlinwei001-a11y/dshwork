# 环节 s6h 交接说明（README）

- 脚本：`fix33_residual.py`　退出码：0　耗时：0.18s
- 是否产生变更：是　must_change：True

## 我产出了什么（自报，见 manifest_A.json）
- `SHUFE-BDC-2019-001/quality/waivers.yaml`（7426 B）
- `SHUFE-BDC-2019-001/reuse/domains.yaml`（66283 B）

## 给下游的说明
- 声明的产物 glob：["SHUFE-BDC-2019-001/quality/waivers.yaml", "SHUFE-BDC-2019-001/reuse/domains.yaml"]
- 检查项：[{"id": "exit_zero", "verdict": "pass"}, {"id": "outputs_exist", "verdict": "pass"}, {"id": "outputs_nonempty", "verdict": "pass"}, {"id": "noop_policy", "verdict": "pass"}]
- 已知缺口/备注：{
  "k13a_tightened": true,
  "k4_waivers": 15,
  "k10_prefix_match": true,
  "k10_waived": [
    "本项目·消防水泵接合器",
    "项目排风口·与环境敏感目标间距",
    "项目排风口·底部离地面高度",
    "本项目·抗震设防类别（安全章口径）",
    "上海财经大学·项目管理架构",
    "本项目·招标方式",
    "本项目·估算范围排除项",
    "附件·清单"
  ],
  "s11_tables_emitted": true
}

> 下游**不应只看本文件**：请按 SOP 契约实际读产物，自行形成 manifest_B，
> 再从产物内容读出 manifest_C，四者比对后才开工。
