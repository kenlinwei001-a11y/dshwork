---
name: cadcraft-preliminary-drawing
description: 用 CADCraft（craftcad 插件）生成初步设计图纸并导出 PDF 的可执行规程，已在 CADCraft CLI 0.14.0 上逐条验证。当需要通过 MCP 桥新建或打开图纸、建图层与图框、画轴线墙体门窗、加三道尺寸与房间面积、出立面剖面节点、校验实体与文字、或用 exportpdf 按 A1/A2 图幅导出 PDF 时加载。
---

# CADCraft 初设出图规程（实测版）

本规程的每条命令、参数与坑都在 CADCraft CLI 0.14.0（cadcraft-cli fbd97d4）上实际跑通。工具面以 MCP 桥为主：它是有状态的绘图会话，适合"建基准 → 分段成图 → 校验 → 导出"的连续操作。

## 0. 能力探测（每次任务先做）

1. cadcraft_mcp_status：确认二进制路径与桥接是否可用。
2. list_commands（或 cadcraft_commands）：查命令目录；cadcraft_describe 查参数语法。
3. 不可用（返回未安装/空目录）时立即停止绘图流程，如实告诉用户"当前无法生成或修改图纸"，并给出原因，不伪造结果。

### 0.1 两个 MCP server（运行时依赖）

本技能依赖两个 CADCraft MCP server，缺一不可：

| Server | 作用 | 关键工具 |
|---|---|---|
| craftcad（headless） | 程序化建图、加实体、建层、查询、存 DXF | new_drawing / load_dxf / create_layer / add_entities / query / save_dxf |
| craftcad-ui（驱动运行中的 CraftCAD Web，默认 http://127.0.0.1:8080） | **把成品交到人手里**：打开文件供在线编辑、查询、截图、缩放、回存 | open / query / zoom / screenshot / save_dxf / command |

分工与完整参数见 references/mcp-servers.md。交付回路：headless 生成并 save_dxf → craftcad_ui_open 打开（用户可直接在线改）→ zoom extents + screenshot 留证 → 用户改完 craftcad_ui_save_dxf 回存 → 再加工或导出 PDF。craftcad-ui 不可用时降级为"交付 DXF/PDF + 请用户自己启动 Web 打开"，不假装已打开。

## 1. 建图纸基准

- 新建：new_drawing {metric:true}。默认是英制，建筑图必须显式公制。
- 打开：open {path}（.dxf/.dwg）。
- 图层：layer.new {name, color, lineweight, current}。**不传 current:true 就不会成为当前层**，图元会落到 0 层；绘图命令参数里的 layer 字段**不会生效**（实测被忽略），换层必须先用 layer.current {name} 把目标层设为当前层，再画。
- 图框：优先用随包模板 assets/a1-frame-template.dxf（841×594，外框/内框/标题栏/会签栏/图名位齐全），open 后另存为项目文件；A2/A3 按 references/sheet-and-title-block-spec.md 缩放或重画。
- 尺寸样式：dimstyle {name:"Standard", current:true, textHeight, arrowSize}。模型字高 = 图面字高 × 比例分母（1:100 的 2.5mm 字 → 250）。

## 2. 分段成图（execute，每段一次校验）

已验证的命令与参数：

    execute {command:"line",    params:{points:[[x,y],...], closed:true}}
    execute {command:"pline",   params:{vertices:[...], ...}}
    execute {command:"text",    params:{at:[x,y], text:"办公 20.00", height:7}}
    execute {command:"mtext",   params:{at:[x,y], text:"...", height:5, width:200}}
    execute {command:"dimlinear", params:{p1:[x,y], p2:[x,y], at:[x,y]}}
    execute {command:"dimradius", params:{handle:"...", at:[x,y]}}
    execute {command:"block",   params:{name:"A-TITLEBLOCK", base:[x,y], handles:[...]}}

分段顺序：图框 → 轴网 → 墙体柱 → 门窗 → 楼梯电梯 → 尺寸 → 文字与面积 → 立面 → 剖面 → 节点 → 说明与表。每段结束执行一次 inspect_drawing 并确认预期图层出现、实体数量级合理、范围未越出内框。

批量：多行命令可用 script（按行模拟命令行输入），或 cadcraft_run 的 commands 数组（注意"已知坑"第 6 条）。

## 3. 校验（3.1 机械核对 + 3.2 目视校核）

### 3.1 机械核对（每张图至少三项）

- inspect_drawing {entities:true, limit:n}：counts、currentLayer、各实体 layer、extents。
- query_entities {type:"Line", layer:"A-WALL", window:[[x0,y0],[x1,y1]]}：按类型/图层/范围抽查。
- find_text {contains:"图名"} / {window:...}：检查房间名、面积、标高、图名是否真的写进去了。
- 比例反算：任取三处轴线，用几何反算值对照标注值，必须相等。

### 3.2 目视校核（craftcad-ui 在 CraftCAD Web 里看）

机械核对只证明"数据在"，不证明"人看着对"。目视校核一律在 CraftCAD Web 里做，用 craftcad-ui 三个动作：

    craftcad_ui_status {}                                         // 确认 Web 在运行（返回文件/实体/图层）
    craftcad_ui_open   {path:"01_dxf/plan-V1.2.dxf"}              // 打开待校核图纸
    craftcad_ui_zoom   {mode:"extents"}                           // 全图铺满，避免"只看到局部"
    craftcad_ui_screenshot {path:"04_过程/plan-V1.2-web.png", canvasOnly:true}   // 留证

截图逐项看（任一条不过就回改，不许"看着差不多"放过）：

1. 图框与内框完整，标题栏字段齐全，设计阶段写"初步设计"。
2. 图名在标题栏/图名下框内，位置正确、无截断。
3. 线宽层级：墙柱最粗、门窗次之、标注文字最细，屏幕上能分辨。
4. 文字：无重叠、无截断、无乱码；房间名与面积成对。
5. 标注：三道尺寸不压图、不越出图框，箭头与文字方向正确。
6. 填充：不遮挡文字与标注（填充层置于文字之下）。
7. 与 DXF 摘要一致：截图上看到的图幅/内容，与 inspect_drawing 的 counts、extents 对得上。

render 只作 headless 快速预览（不必开 Web 时用）；**正式目视校核以 Web 打开 + 截图为凭据**。craftcad-ui 不可用时降级为 render 预览，并在交付说明里注明"未做 Web 目视校核"。

## 4. 导出（先 DXF，后 PDF）

    save  {path:"01_dxf/plan-V1.2.dxf"}                                  // 源文件
    execute {command:"exportpdf", params:{path:"02_pdf/plan.pdf",
             paper:"A1", landscape:true, fit:true}}                       // 指定图幅
    save  {path:"02_pdf/quick.pdf"}                                       // 仅按模型范围快速出图

- 图幅、方向、是否满幅以 exportpdf 为准；save 到 .pdf 不保证 A1。
- 导出后读回返回的 bytes/pages，并用 tools.bash 确认文件存在、非空；再 render 抽页目视。
- 转换备用：cadcraft_convert {input:"x.dxf", output:"x.pdf"}。
- **交付到 Web 供在线编辑**（必做）：craftcad_ui_open {path:"01_dxf/plan-V1.2.dxf"} → craftcad_ui_zoom {mode:"extents"} → craftcad_ui_screenshot {path:"04_过程/web-open.png", canvasOnly:true}；告知用户"图纸已在 CraftCAD Web 打开，可直接编辑"。用户改完用 craftcad_ui_save_dxf 回存为新版本，不回写原件。

## 5. 已知坑（实测）

| 现象 | 原因 | 处置 |
|---|---|---|
| 实体全在当前层/0 层 | layer.new 未设 current:true；命令里的 layer 参数被忽略 | 用 layer.new{current:true} 或 layer.current 切层后再画，query_entities 按层复核 |
| 尺寸数字小到看不见 | 未按比例设 dimstyle.textHeight | 1:100 用 250，1:50 用 125，以此类推 |
| save 出的 PDF 不是 A1 | save 只按模型范围出图 | 改用 exportpdf 的 paper/landscape/fit |
| 中文变问号/方框 | 本机缺对应工程字体 | 用 --fontalt/--fontfallback 指定已有字体，或改用系统已装字体 |
| 图形画到图框外 | 未先定图幅与比例 | 先开图框模板再排布，用 inspect extents 对比内框 |
| cadcraft_run 报 unknown command "id={...}" | 插件命令分隔符与 CLI 0.14.0 的 "id {json}" 不一致 | 改用 MCP 桥 execute，并记录版本差异 |
| 每次调用都画在新图纸上 | 用了 cadcraft_run 的一次性会话 | MCP 桥是连续会话；批处理时显式传上一版 DXF |
| Web 里看不到文字/线宽层级不对 | 图层颜色接近背景、字高过小或填充盖字 | 改图层颜色/字高/绘制顺序后重新 craftcad_ui_open 复核 |
| 截图与 DXF 摘要不一致 | 打开的不是最新版本，或保存失败 | 先 craftcad_ui_status 看文件名，再按 DXF 摘要排查；不以截图为准 |

## 6. 交付前最后一眼

- 图框、标题栏、会签栏齐全，设计阶段写"初步设计"。
- 图纸目录与实际图纸一一对应，图号连续，版本与修订记录一致。
- 每张平面有三道尺寸、房间名与面积、必要标高；立面有层高与总高；剖面有净高与构造。
- PDF 页数 = 目录张数，首页目录，黑白打印可读；DXF 源文件同目录归档。
- 交付文字只写实际存在、已读回确认的文件。

## 7. 参考文件与模板

- references/drawing-depth-checklist.md：初设出图深度检查表。
- references/layer-linewidth-standard.md：图层、线宽、字体、标注数值。
- references/sheet-and-title-block-spec.md：图幅、图框、标题栏、图号与版本规则。
- references/cadcraft-tool-playbook.md：MCP 工具参数、实测调用序列、批处理与失败回退。
- references/mcp-servers.md：两个 MCP server（headless 与 Web）的工具清单、分工、交付回路与降级处理。
- assets/a1-frame-template.dxf：A1（841×594）图框模板。
- assets/layer-standard.csv、assets/sheet-catalog.csv：图层清单与图纸目录模板。
