# CADCraft 工具调用规程（实测）

craftcad 插件向同一套 CADCraft CLI 暴露了两层工具。本文件记录实测参数与调用序列，不替代运行时的命令目录。

## 1. 两层工具，各管一段

| 层 | 工具 | 特点 | 适合 |
|---|---|---|---|
| MCP 桥 | cadcraft_mcp_tools、cadcraft_mcp_call（command_line / script / execute / list_commands / inspect_drawing / query_entities / render / find_text / new_drawing / open / save / cancel） | **有状态会话**：new_drawing 后当前图纸一直保留，连续 execute 累加 | 建图纸、分段成图、逐段校验、导出 |
| 命令行包装 | cadcraft_commands、cadcraft_describe、cadcraft_inspect、cadcraft_run、cadcraft_convert | 每次调用独立进程（run 的一次性会话） | 批量脚本、格式转换、快速看图摘要 |

结论：**绘图主流程走 MCP 桥**；一次任务里不要混用两套的"当前图纸"概念。

## 2. MCP 工具参数要点

    new_drawing  {metric:true}                     // 公制；默认英制，建筑图必须显式
    open         {path:"x.dxf"}
    save         {path:"x.dxf"}                    // 存源文件
    save         {path:"x.pdf"}                    // 按模型范围导出 PDF（不控图幅）
    execute      {command:"layer.new", params:{name:"A-WALL", color:7, lineweight:0.5, current:true}}
    execute      {command:"layer.current", params:{name:"A-AXIS"}}   // 切当前层；命令里的 layer 字段不生效
    command_line {text:"LINE 0,0 841,0 "}          // 逐行命令行，空格=回车
    script       {text:"..."}                      // 多行脚本
    inspect_drawing {entities:true, limit:20}      // counts / currentLayer / layers / extents
    query_entities  {type:"Line", layer:"A-WALL", window:[[0,0],[841,594]]}
    find_text    {contains:"图名", limit:50}
    render       {path:"preview.png", width:1600} // 也可 window 单张图幅
    list_commands{filter:"dim"}
    cancel       {}                                // Esc

## 3. 实测调用序列（可照抄改写）

    // 1) 新图纸 + 图层（current:true 决定后续图元落在哪层；绘图命令里的 layer 参数实测被忽略）
    new_drawing {metric:true}
    execute {command:"layer.new", params:{name:"A-FRAME", color:7, lineweight:0.5, current:true}}
    execute {command:"layer.new", params:{name:"A-WALL",  color:7, lineweight:0.5}}
    execute {command:"layer.new", params:{name:"A-AXIS",  color:1, lineweight:0.18}}
    execute {command:"layer.new", params:{name:"A-DIM",   color:3, lineweight:0.18}}
    execute {command:"layer.new", params:{name:"A-TEXT",  color:7, lineweight:0.18}}

    // 2) 图框（或直接 open assets/a1-frame-template.dxf）
    execute {command:"layer.current", params:{name:"A-FRAME"}}
    execute {command:"line", params:{points:[[0,0],[841,0],[841,594],[0,594]], closed:true}}
    execute {command:"line", params:{points:[[25,10],[831,10],[831,584],[25,584]], closed:true}}

    // 3) 轴网与房间（先切层，再画）
    execute {command:"layer.current", params:{name:"A-AXIS"}}
    execute {command:"line", params:{points:[[300,120],[300,480]]}}
    execute {command:"layer.current", params:{name:"A-WALL"}}
    execute {command:"line", params:{points:[[300,250],[500,250],[500,430],[300,430]], closed:true}}

    // 4) 尺寸样式与标注
    execute {command:"dimstyle", params:{name:"Standard", current:true, textHeight:10, arrowSize:10}}
    execute {command:"dimlinear", params:{p1:[300,250], p2:[500,250], at:[300,220]}}

    // 5) 文字
    execute {command:"text", params:{at:[360,520], text:"首层平面图 1:100", height:14, layer:"A-TEXT"}}
    execute {command:"text", params:{at:[310,330], text:"办公 20.00", height:7, layer:"A-TEXT"}}

    // 6) 校验后导出
    inspect_drawing {entities:true, limit:10}
    find_text {contains:"办公"}
    save {path:"01_dxf/plan-V1.0.dxf"}
    execute {command:"exportpdf", params:{path:"02_pdf/plan-V1.0.pdf", paper:"A1", landscape:true, fit:true}}

实测返回：line 返回 handles 数组；text 返回 handle；dimlinear 返回 handle；save 返回 {path, bytes, version}；exportpdf 返回 {path, bytes, pages, layout}。

### 3.5 目视校核（craftcad-ui，Web）

    craftcad_ui_status     {}                                    // {"file":"plan.dxf","entities":26,"layers":6,...}
    craftcad_ui_open       {path:"01_dxf/plan-V1.2.dxf"}         // 返回 entities/layers，可与 headless 摘要比对
    craftcad_ui_zoom       {mode:"extents"}                      // extents | in | out | 数字倍数
    craftcad_ui_screenshot {path:"04_过程/plan-web.png", canvasOnly:true}   // 返回 path 与 clip 尺寸

看图判据：图框/内框/标题栏齐全，图名不截断，墙-门窗-标注三级线宽可辨，文字无重叠乱码，尺寸不越界，填充不盖字；截图所见与 inspect_drawing 的实体数、范围一致。这是交付前"人看到的版本"，不能用 render 的 headless 预览替代。

## 4. 校验读法

inspect_drawing 的关键字段：

| 字段 | 判读 |
|---|---|
| counts | 按类型统计；新增段应让对应类型增加 |
| currentLayer | 后续图元会落在这层；不是预期层就说明 current:true 没生效 |
| entities[].layer | 逐条复核，出现 0 层立即修正 |
| extents | 应落在内框（25,10)-(831,584) 内；越界说明排布或图幅错 |
| dirty | 有未保存修改时为 true；导出前应为 false 或已显式 save |

## 5. 失败处理

| 现象 | 判断 | 处置 |
|---|---|---|
| MCP 工具列表为空 / status 报未安装 | 环境不可用 | 停止并如实报告 |
| execute 报 unknown command | id 不匹配 | list_commands 检索真实 id，或 cadcraft_describe 查语法 |
| 参数报错 | 字段名/类型不符 | 按 describe 返回逐字段修正，不连打试错 |
| 标注文字异常 | dimstyle 未设或比例不符 | 设 textHeight/arrowSize，按比例换算 |
| cadcraft_run 报 unknown command "id={...}" | 插件分隔符与 CLI "id {json}" 不一致 | 改用 MCP execute；记录 CLI 版本 |
| 导出失败 | 路径或权限 | 先 save DXF，再用 cadcraft_convert 补 PDF |
| 图形错乱 | 基准/顺序错 | 重开上一版 DXF，重做该段（不改几何凑数） |

## 6. 路径与命名

- 全部使用工作区相对路径：01_dxf、02_pdf、03_清单、04_过程。
- 不覆盖用户原件；改图另存新版本，文件名带图号与版本。
- 每个交付文件导出后都要读回（存在、非空、页数）再写进交付清单。
