# 依赖与环境

## 必需

| 项 | 版本 | 说明 |
|---|---|---|
| Python | ≥3.8 | 仅用标准库：`sqlite3 / json / re / difflib / subprocess / urllib`，**无需 pip 安装** |

## 可选（仅表格/图抽取需要）

| 项 | 用途 | 获取方式 |
|---|---|---|
| `bin/grid` | PDF 页 → 网格线检测 + 逐格 OCR | macOS：`xcrun swiftc -O -framework PDFKit -framework Vision -framework AppKit -o bin/grid bin/grid.swift` |
| `bin/pdftext` | 有文本层 PDF → 纯文本 | 同上：`-framework PDFKit -o bin/pdftext bin/pdftext.swift` |
| `bin/crop` | 图片区域裁切放大（人工核读用） | 同上：`-framework AppKit -o bin/crop bin/crop.swift` |
| `bin/pdfocr` | 无文本层 PDF → 逐页 OCR + 坐标 TSV | 同上：`-framework PDFKit -framework Vision -o bin/pdfocr bin/pdfocr.swift` |

四个 Swift 工具都依赖 **macOS 系统框架**（PDFKit / Vision / AppKit）。Linux/Windows 上请替换为等效实现：
网格检测可用 `pdfplumber`/`PyMuPDF.find_tables`，OCR 用本地模型（见下）。

## OCR 后端（可插拔）

| 后端 | 状态 | 启用方式 |
|---|---|---|
| `vision` | 内置可用（macOS） | 默认 |
| `local` | **留白，待接入本地模型** | 设 `OCR_LOCAL_ENDPOINT=http://127.0.0.1:PORT/ocr` |
| `none` | 只抽结构、值留空 | `--ocr-engine none` |

**本地模型接入契约**：`recognize(单格PNG字节) -> {"text": str, "conf": float}`
- 输入是单格裁切图（300 dpi 以上）
- **不得改写数字位数**（`0.00` 不得输出 `0.0`）
- 识别不了返回空串，不要猜

## 环境变量

| 变量 | 作用 |
|---|---|
| `TABLE_GRID_BIN` | 指定 `grid` 二进制路径（覆盖 `scripts/bin/grid`） |
| `OCR_LOCAL_ENDPOINT` | 本地 OCR 服务地址 |
