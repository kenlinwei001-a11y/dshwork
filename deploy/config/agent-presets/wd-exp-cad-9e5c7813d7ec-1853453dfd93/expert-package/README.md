# 初步设计CAD出图专家

把工程建筑初步设计阶段的方案，落成一套**图面自洽、达到初设深度、可打印送审**的 CAD 图纸集，并通过 CADCraft 输出 PDF。

## 它解决什么问题

初设阶段最常见的困境不是"不会画"，而是：
- 方案只存在于平面草图和层高表里，没人有时间把它变成一整套图；
- 画出来的图单看没问题，放在一起层数、层高、门窗编号、面积对不上；
- 图能看，但打印出来线宽糊、字太小、标注不闭合，评审一句话打回；
- 改了一处，忘了另外五张联动图纸。

这个专家把上述问题固化成流程：先出图纸策划表，再建图层与图框，按轴网与层高表成图，出图前做机械校核与图间一致性矩阵，最后导出 PDF 并交付清单。

## 能力

- 初设建筑图纸策划：图纸目录、图幅、比例、依据来源。
- 成套成图：总平面、各层平面、立面、剖面、主要节点、设计说明、门窗表、面积表、图纸目录。
- 制图标准落地：图层体系、线宽层级、字体与字高换算、三道尺寸、标高与面积口径。
- 初设深度控制：区分"初设必须有"与"施工图再深化"，不欠深度也不过度绘制。
- CADCraft 驱动：命令探测、分段执行、实体校验、DXF 保存与 PDF 导出、增量改图与版本管理。
- 质量校核：比例反算、图层检查、字高与线宽可读性、图间一致性矩阵、PDF 页数与目录核对。

## 典型用法

1. 把方案资料（平面图/照片/PDF/DWG、层高表、房间面积表、总图条件）交给它。
2. 它会先给一张"图纸目录草案"（图号、图名、图幅、比例），确认后连续出图。
3. 出图完成后给交付清单：已生成文件、未完成项、待确认项、校核结论。

示例提示词：

- 这是我的初设方案（平面、层高与房间表见附件），请出 A1 建筑初设图纸：总平面、各层平面、两个立面、一个剖面，按初设深度标注，最后输出 PDF。
- 这份初设平面只有轴网和轮廓，请补全墙体、门窗、楼梯、三道尺寸、房间名称与面积，按 A1 加图框标题栏，整理图纸目录并导出 PDF。
- 请按初设深度审查这份图纸 PDF，列缺项和制图问题，给整改清单，确认后重新出图。

## 依赖

本作品引用**两个 MCP server**（缺一不可）：

| Server | 形态 | 作用 |
|---|---|---|
| craftcad | headless 进程 | 新建/加载图纸、建层、加实体、查询、存 DXF |
| craftcad-ui | 驱动运行中的 CraftCAD Web（默认 http://127.0.0.1:8080） | 打开成品供用户在线编辑、查询、缩放、截图、回存 |

交付回路：headless 出 DXF → craftcad-ui 在 CraftCAD Web 打开 → 用户直接在线改 → save_dxf 回存新版本 → 导出 PDF。craftcad-ui 不可用时降级为交付文件并请用户自行打开，不假装已打开。工具清单与实测记录见 skills/cadcraft-preliminary-drawing/references/mcp-servers.md。

- **craftcad 插件**：提供 CADCraft 的 MCP 桥（cadcraft_mcp_*）与命令行包装（cadcraft_commands / describe / run / convert / inspect）。
- **CADCraft CLI**：本机已部署并在 **CADCraft CLI 0.14.0** 上完成实测（新建公制图纸、建层、尺寸样式、线段/文字/标注、DXF 保存、A1 PDF 导出、inspect、render 全部跑通）。
- **CraftCAD Web**：已在运行实例上实测 craftcad-ui 的 open / zoom / query / screenshot（打开 A1 模板返回 26 实体、6 图层）。
- 字体：建议本机安装长仿宋或宋体类工程字体，保证图面文字与打印效果。
- 字体：建议本机安装长仿宋或宋体类工程字体，保证图面文字与打印效果。

## 包内结构

    .workdsh-expert/plugin.json                 作品元数据（名称、分类、头像、快捷提示）
    agents/cad-preliminary-design-drafter.md    专家正文（能力、流程、规范、红线）
    skills/cadcraft-preliminary-drawing/        随包技能：CADCraft 出图规程
      SKILL.md
      references/drawing-depth-checklist.md     初设出图深度检查表
      references/layer-linewidth-standard.md    图层线宽字体标注数值
      references/sheet-and-title-block-spec.md  图幅图框标题栏图号版本
      references/cadcraft-tool-playbook.md      工具参数与调用模式
      references/mcp-servers.md                 两个 MCP server 的工具、分工与交付回路
      assets/layer-standard.csv                 图层清单（可直接对照）
      assets/sheet-catalog.csv                  图纸目录模板
      assets/a1-frame-template.dxf              A1 图框模板（841×594，含标题栏与字段）
    avatars/expert.png                          头像（蓝图立面风格插画）

## 适用与不适用

适用：工程建筑初步设计阶段的建筑专业出图、已有图纸补全与规范化、初设图纸深度审查与整改、图面一致性校核。

不适用：施工图深化与构造大样全套、结构/机电专业计算与系统图、效果图与三维渲染、代替注册人员签章或承诺审查结论。

## 版本与状态

- 版本：v1.2.0
- 状态：草稿已保存，待用户在专家界面预览确认后发布。
- 实测：2026-10 在 CADCraft CLI 0.14.0 上跑通"建层 → 画线/文字/标注 → 保存 DXF → exportpdf A1 → inspect/render"全链路；A1 图框模板即由该链路生成。
- 实测（Web）：craftcad-ui 打开该模板返回 26 实体 / 6 图层，zoom extents 正常，画布截图 1600×791 成功——即"点击文件 → CraftCAD Web 打开 → 在线编辑"这条交付回路。
- 头像：随包提供蓝图风格插画（512×512 PNG），可自行替换为团队或项目风格。

## 说明

专业内容按初设阶段通用要求编写；具体项目的院标、地方规定、甲方标准优先。专家会在不确定处标注"需专业负责人确认"，不替用户编造规范结论或尺寸数据。
