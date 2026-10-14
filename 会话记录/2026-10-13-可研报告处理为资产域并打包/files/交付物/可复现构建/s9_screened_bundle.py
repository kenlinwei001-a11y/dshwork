# -*- coding: utf-8 -*-
"""外部核查线索登记 + 交付物装配 + ZIP 打包。

1. 把外部规范时效核查线索写入 quality/screened_evidence.yaml（adopted=false，留痕备查）；
2. 装配 交付物/：语料包 + 审计 + 外部核查 + 可复现构建；
3. 打包为 ZIP（同内容不重复覆盖）。
"""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from screened_source import SCREENED  # noqa: E402

BUILD = Path(__file__).resolve().parent
WS = BUILD.parent
ROOT = WS / "SHUFE-BDC-2019-001"
DELIV = WS / "交付物"
ZIP_NAME = "上财大数据研究中心可研-资产域包-v1.zip"
ZIP_ROOT = "上财大数据研究中心可研-资产域包-v1"

# ---------------------------------------------------------------- 1 外部核查线索


# ---------------------------------------------------------------- 2 装配交付物
# 只刷新语料包子目录；保留 s8 已生成的 README.md 与 审计/
DELIV.mkdir(parents=True, exist_ok=True)
_pkg = DELIV / ROOT.name
if _pkg.exists():
    shutil.rmtree(_pkg)
shutil.copytree(ROOT, _pkg)

EXT = DELIV / "外部核查"
EXT.mkdir(parents=True, exist_ok=True)
appendix_src = WS / "input" / "appendix_a.md"
appendix_txt = appendix_src.read_text(encoding="utf-8") if appendix_src.exists() else ""
header = """<!--
  交付说明（由本包处理者添加，非附录原文，亦非原报告内容）
  性质：外部检索线索，**非原报告内容**，未并入 source/normalized.md，不作为事实进入图谱。
  来源：本次任务进行期间，另一进程向工作区中间文件 input/大数据研究中心可研.md 追加的附录A；
        本次交付已将其从原稿链路中剥离并单独归位于此处。
  处置：全部线索登记在 SHUFE-BDC-2019-001/quality/screened_evidence.yaml，字段 adopted=false（未采纳）。
  纪律：检索结果不直接入图；规范的现行状态一律不臆断；采纳前须经适配性评估并由客户确认。
-->

"""
(EXT / "appendix-外部规范与法定大纲核查.md").write_text(header + appendix_txt, encoding="utf-8")

REPRO = DELIV / "可复现构建"
REPRO.mkdir(parents=True, exist_ok=True)
for f in sorted(BUILD.glob("*.py")):
    shutil.copy2(f, REPRO / f.name)
shutil.copy2(BUILD / "EXTRACTION_SPEC.md", REPRO / "EXTRACTION_SPEC.md")
(REPRO / "原稿与产物散列.txt").write_text(
    f"""原稿文件: 上海财经大学中山北一路校区大数据研究中心 可行性研究报告（修订版）.docx
原稿 sha256: {json.loads((BUILD / 'doc-clean' / 'derivation.json').read_text(encoding='utf-8'))['source_docx_sha256']}
重推文档文本 sha256: {json.loads((BUILD / 'doc-clean' / 'derivation.json').read_text(encoding='utf-8'))['derived_md_sha256']}

重建命令:
  /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python build/run_all.py --fresh
  /Users/apple/Desktop/workdsh/knowledge/knowledge-processing-expert/.venv/bin/python build/s9_screened_bundle.py

说明:
  - 语料包内已含原稿二进制：SHUFE-BDC-2019-001/source/original.docx
    （sha256 须等于上述值；任何与该散列不符的中间产物均不得作为权威输入）。
  - 阶段顺序与确定性边界见 审计/05-可复现性与输入完整性说明.md。
""", encoding="utf-8")

# ---------------------------------------------------------------- 3 ZIP
zip_path = WS / ZIP_NAME
if zip_path.exists():
    zip_path.unlink()
FIXED_TS = (2020, 1, 1, 0, 0, 0)   # 固定时间戳：让 ZIP 在字节层也可复现（不受文件 mtime 影响）
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in sorted(DELIV.rglob("*")):
        if not p.is_file():
            continue
        info = zipfile.ZipInfo(str(Path(ZIP_ROOT) / p.relative_to(DELIV)), date_time=FIXED_TS)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (0o644 & 0xFFFF) << 16
        z.writestr(info, p.read_bytes())

sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
n_files = sum(1 for p in DELIV.rglob("*") if p.is_file())
print(json.dumps({"zip": str(zip_path.relative_to(WS)), "bytes": zip_path.stat().st_size,
                  "sha256": sha, "files": n_files,
                  "screened_leads": len(SCREENED),
                  "adopted": sum(1 for x in SCREENED if x["adopted"]),
                  "pending": sum(1 for x in SCREENED if not x["adopted"])}, ensure_ascii=False, indent=2))
