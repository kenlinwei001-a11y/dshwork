# MCP：craftcad

> 本文件由 `tools/expert-report/build.mjs` 从本机权威数据源自动构建，内容基准时间（UTC）：2026-11-02T13:05:37Z（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。

## 1. 三视图在场情况

| 视图 | 是否存在 | 说明 |
|---|---|---|
| 会话可见 | 否 | 本会话未提供该 server |
| WorkDSH 定义 | 是 | DSH_HOME/storages/workdsh_connectors/definitions/craftcad.json |
| 第三方注册表 | 是 | key=json-craftcad |
| 运行时状态 | 有 | disabled |

## 2. WorkDSH 定义（磁盘权威）

| 字段 | 值 |
|---|---|
| id | craftcad |
| 标题 | CraftCAD |
| 描述 | CraftCAD 二维出图 MCP 桥（DXF 建图 / 校验 / 导出）；随 CAD 专家会话自动启用，普通会话不注入。 |
| 传输 | stdio |
| 命令 | /usr/local/bin/node |
| 参数 | /Users/apple/Desktop/craftcad-mcp/server.mjs |
| URL | - |
| env 键名 | （无） |
| 启用 | true |
| 创建时间 | 2026-10-29T12:18:51.030Z |

## 3. 第三方注册表记录（脱敏）

| 字段 | 值 |
|---|---|
| key | json-craftcad |
| connectorId | __json__ |
| 名称 | craftcad |
| 传输 | stdio |
| serverName | craftcad |
| 启用 | false |
| env 键名 | （无） |
| header 键名 | （无） |

## 4. 运行时观测

| 字段 | 值 |
|---|---|
| 健康状态 | disabled |
| 诊断 | disabled · 连接已停用，未执行可用性检查 |
| 作用域 | 全局 |
| 注入模式 | 始终注入 |
| 最近成功 | （无） |

## 5. 工具清单（18）

| 工具 |
|---|
| craftcad_add_entities |
| craftcad_close_drawing |
| craftcad_create_layer |
| craftcad_delete_entities |
| craftcad_load_dxf |
| craftcad_move_entities |
| craftcad_new_drawing |
| craftcad_query |
| craftcad_save_dxf |
| craftcad_transform_entities |
| craftcad_ui_command |
| craftcad_ui_eval |
| craftcad_ui_open |
| craftcad_ui_query |
| craftcad_ui_save_dxf |
| craftcad_ui_screenshot |
| craftcad_ui_status |
| craftcad_ui_zoom |

## 6. 关联

- 引用该 server 的技能：无
- 引用该项目连接：无
