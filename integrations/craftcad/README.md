# CraftCAD 集成（MCP + WorkDSH 右侧面板）

这里只有**连接 CraftCAD 的组件**，不含 CraftCAD 软件本身：

- `mcp-server/`：无头 MCP 服务，给 agent 提供生成/修改 DXF 的工具（stdio）。
- `workdsh-panel/`：WorkDSH 右侧栏插件，打开 DXF 时内嵌 CraftCAD 编辑并保存回写；PDF / PNG 只读预览。

## 前置条件

- Node.js 24（MCP 与插件都直接跑源码，不需要构建）。
- 本机已部署 CraftCAD，并带有 `craftcad-embed` 嵌入桥（0.5.4+），默认监听 `http://127.0.0.1:8080/`。
- 浏览器使用 Chrome（面板保存回写依赖 File System Access API）。

## MCP 服务

`mcp-server/server.mjs` 通过 stdio 提供 10 个工具：
`craftcad_new_drawing`、`craftcad_load_dxf`、`craftcad_add_entities`、`craftcad_move_entities`、
`craftcad_transform_entities`、`craftcad_delete_entities`、`craftcad_query`、
`craftcad_create_layer`、`craftcad_save_dxf`、`craftcad_close_drawing`。

它直接 import CraftCAD 源码里的 `src/core` / `src/io`，不会复制图纸逻辑。CraftCAD 源码位置：

```bash
export CRAFTCAD_DIR=/path/to/CraftCAD   # 默认 /Users/apple/Desktop/CraftCAD
node mcp-server/server.mjs
```

注册到 DeepSeek Harness / WorkDSH 的官方 MCP 连接器（全局、始终注入）：

```bash
curl -s -H 'content-type: application/json' -H 'Origin: http://127.0.0.1:18989' \
  -d '{"method":"importJson","params":{"json":"{\"mcpServers\":{\"craftcad\":{\"command\":\"/usr/local/bin/node\",\"args\":[\"/abs/path/mcp-server/server.mjs\"],\"env\":{\"CRAFTCAD_DIR\":\"/abs/path/CraftCAD\"}}}}"}}' \
  http://127.0.0.1:18989/mcp-connector/api
```

导入后如需强制“始终注入”：

```bash
curl -s -H 'content-type: application/json' -H 'Origin: http://127.0.0.1:18989' \
  -d '{"method":"setInjectionMode","params":{"key":"json-craftcad","mode":"always"}}' \
  http://127.0.0.1:18989/mcp-connector/api
```

工具名以 `mcp__craftcad__` 为前缀。限制：只能写 DXF；不支持新建块/样条/填充/布局视口；PDF 导出与 DWG 写出不在本服务范围内。

## WorkDSH 右侧面板插件

把 `workdsh-panel/` 复制到目标 profile 的 `node_modules/`，并把包名加入 profile `package.json` 的 `dsh.profile.bundles`，然后重启 WorkDSH：

```bash
cp -R workdsh-panel "$DSH_HOME/profiles/<profile>/node_modules/workdsh-plugin-craftcad-panel"
```

重启后：

- 会话输入框左侧出现 `CraftCAD` 按钮；右侧栏引导页也有「CraftCAD 文件」入口。
- `打开文件` 支持 `.dxf` / `.pdf` / `.png`；DXF 内嵌 CraftCAD 编辑，`保存回写` 写回原文件（拖入的文件没有原路径，保存为下载副本）。
- 需要 CraftCAD 处于 `craftcad-embed` 桥版本；否则面板只能显示框架，不能打开/保存图纸。

## 通信协议（CraftCAD ⇄ 面板）

面板 iframe 加载 `http://127.0.0.1:8080/`，通过 `postMessage` 通信：

- 面板 → CraftCAD：`{channel:'craftcad-embed', type:'open', name, text}`、`{type:'save-request'}`、`{type:'saved'}`、`{type:'ping'}`
- CraftCAD → 面板：`{channel:'craftcad-embed', type:'ready' | 'opened' | 'save' | 'error'}`

双向都只接受 loopback 来源（127.0.0.1 / localhost）。
