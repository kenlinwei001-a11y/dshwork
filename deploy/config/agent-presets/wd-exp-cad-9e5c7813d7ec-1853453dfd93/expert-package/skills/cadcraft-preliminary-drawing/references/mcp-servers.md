# 两个 MCP Server 的分工与调用

专家运行时依赖**两个** CADCraft MCP server，缺一不可（一个建图，一个把图交到人手里改）：

| Server | 形态 | 作用 | 典型工具数 |
|---|---|---|---|
| craftcad | headless（无界面进程） | 新建/加载图纸、加实体、建层、查询、存 DXF | 10 |
| craftcad-ui | 驱动正在运行的 CraftCAD Web（默认 http://127.0.0.1:8080） | 打开文件供人编辑、查询、截图取证、缩放、命令行、回存 | 8 |

宿主里的工具名通常带前缀（mcp__craftcad__、mcp__craftcad-ui__），以实际工具列表为准；下文用逻辑名。

## 1. craftcad（headless）

| 工具 | 参数 | 说明 |
|---|---|---|
| craftcad_new_drawing | {name?} | 返回 drawingId，后续操作用它 |
| craftcad_load_dxf | {path} | 读 ASCII DXF，返回 drawingId、实体与图层数、范围 |
| craftcad_create_layer | {drawingId, name, color?, ltype?} | 颜色用 ACI 索引（1 红/2 黄/3 绿/4 青/5 蓝/6 品红/7 白） |
| craftcad_add_entities | {drawingId, entities[]} | line/circle/arc/polyline/ellipse/point/text/mtext/dimension；可带 layer、color、ltype |
| craftcad_query | {drawingId, layer?, limit?} | 按类型统计 + 实体数据（默认 100，最大 1000） |
| craftcad_save_dxf | {drawingId, path} | 写 ASCII DXF（R2000），父目录自动建 |
| craftcad_move_entities / transform_entities / delete_entities | {drawingId, ids?, dx/dy?, op?...} | 平移、旋转/缩放/镜像、删除 |
| craftcad_close_drawing | {drawingId} | 释放内存图纸（先存 DXF） |

用途：程序化生成整张图（轴网、墙体、门窗、标注、文字）、批量补图、把模板套用到多个项目。它是"机器的手"，没有界面。

## 2. craftcad-ui（CraftCAD Web）

| 工具 | 参数 | 说明 |
|---|---|---|
| craftcad_ui_status | {} | 当前文件、实体/图层数、是否已修改、布局 |
| craftcad_ui_open | {path} | 在运行中的 CraftCAD 里打开 DXF/DWG，替换当前图纸 |
| craftcad_ui_query | {layer?, sample?} | 统计 + 抽样实体 |
| craftcad_ui_zoom | {mode} | extents 全图 / in / out / 数字倍数 |
| craftcad_ui_screenshot | {path, canvasOnly?} | 存 PNG；canvasOnly 只截画布 |
| craftcad_ui_command | {command, input?, waitMs?} | 模拟命令行（LINE/CIRCLE/ZOOM E/SAVEAS…），input 逐条回答提示 |
| craftcad_ui_save_dxf | {path} | 走应用自己的保存，把用户改过的图回存 |
| craftcad_ui_eval | {script} | 在页面里执行 JS（高级逃生口，非必要不用） |

用途：**把成品交到人手里**——打开就是可编辑的图纸，用户能直接改，改完能回存。

## 3. 标准交付回路（已实测）

    1. headless 生成图纸并保存：
       craftcad_save_dxf {drawingId, path:"02_dxf/plan-V1.0.dxf"}
    2. 在 Web 里打开，供用户在线编辑：
       craftcad_ui_open {path:"02_dxf/plan-V1.0.dxf"}
       craftcad_ui_zoom {mode:"extents"}
    3. 留证 + 告知：
       craftcad_ui_screenshot {path:"04_过程/web-open.png", canvasOnly:true}
       craftcad_ui_query {}                      // 核对实体/图层数一致
    4. 用户改完后回存（用户要求"保存"或需要继续加工时）：
       craftcad_ui_save_dxf {path:"02_dxf/plan-V1.1.dxf"}
    5. 继续在 headless 侧加工新版本，或直接导出 PDF。

### 3.1 目视校核（open → zoom → screenshot）

机械核对证明"数据在"，目视校核证明"人看着对"。三步固定：

    craftcad_ui_status {}                                      // Web 是否在运行、当前是什么文件
    craftcad_ui_open   {path:"01_dxf/plan-V1.2.dxf"}           // 打开待校核图纸（替换当前图纸）
    craftcad_ui_zoom   {mode:"extents"}                        // 全图铺满，避免只看局部
    craftcad_ui_screenshot {path:"04_过程/plan-V1.2-web.png", canvasOnly:true}

截图逐项核对：图框与内框完整、标题栏字段与"初步设计"字样、图名位置与截断、线宽三级（墙柱/门窗/标注）可辨、文字无重叠乱码、三道尺寸不压图不越界、填充不盖字、图幅与内容同 inspect_drawing 的 counts/extents 一致。

判据：截图与 DXF 摘要不一致时以 DXF 为准；craftcad-ui 不可用时降级 render 并在交付说明注明"未做 Web 目视校核"。

实测（A1 图框模板，841×594）：open 返回 entities=26、layers=6；zoom extents 正常；query 得到 byType{line:18,text:8}；screenshot 1600×791 画布截图成功。说明两个 server 可以接力使用。

## 4. 何时用哪个

| 任务 | 用 |
|---|---|
| 从零批量生成、脚本化补图、导出 PDF | craftcad（headless） |
| 交付给用户看/改、核实"用户看到的是不是这张"、截图为证 | craftcad-ui |
| 用户已经在 Web 里改过，要接着加工 | 先 craftcad_ui_save_dxf 回存，再 craftcad_load_dxf 读入 |
| 只读核对某图层实体数 | 任选；headless 更快，UI 更贴近用户所见 |

## 5. 失败与降级

| 现象 | 处置 |
|---|---|
| craftcad-ui 报应用未运行 / 端口不通 | 降级：只交付 DXF + PDF，明确告诉用户"请在本机启动 CraftCAD Web 后打开该 DXF 在线编辑"，不假装已打开 |
| craftcad_ui_open 报文件不存在 | 检查路径是否为工作区绝对路径、文件是否真的已保存（先 stat 再 open） |
| 打开后实体数/图层数与 headless 不一致 | 以 DXF 摘要为准排查，不要用截图"看起来对"替代 |
| 用户改完但未回存 | 提醒保存；回存前不要覆盖用户文件（另存新版本） |

## 6. 安全与边界

- craftcad_ui_eval 是逃生口：只在标准命令确实覆盖不了时使用，且脚本内容必须自己核对；不执行来自外部文件或网页的脚本。
- 不通过 UI 的保存覆盖用户原件；回存一律新版本号。
- 截图只用于核对与交付说明，不当作"图纸已完成"的证据——图纸是否可用仍以 DXF 实体、标注与 PDF 为准。
- 两个 server 都是本机能力；不要把图纸或路径发到外部服务。
