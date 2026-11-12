
import { readFileSync, writeFileSync, existsSync, copyFileSync } from "node:fs";

const target = process.argv[2];
if (!target) { console.error("usage: node patch-workflow-lite-dock.mjs <client.js>"); process.exit(2); }
const backup = target + ".orig-dock";
const src = readFileSync(target, "utf8");

if (src.includes("workflow-lite-dock")) {
  console.log("already-patched");
  process.exit(0);
}
const marker = "}, WorkflowView));\n\t\t}";
if (!src.includes(marker)) {
  console.error("marker-not-found");
  process.exit(2);
}
if (!existsSync(backup)) copyFileSync(target, backup);

const block = [
  "}, WorkflowView));",
  "\t\t\t//#region workdsh-preview: 右侧面板导航入口（轻量工作流）",
  "\t\t\tctx.inject([\"sidebarRightTabs\", \"sessions\"], (dock) => {",
  "\t\t\t\tconst currentSession = () => {",
  "\t\t\t\t\ttry {",
  "\t\t\t\t\t\tconst list = dock.get(\"sessions\").list.getSnapshot();",
  "\t\t\t\t\t\tconst rows = list.ids.map((id) => list.byId[id]).filter((row) => row !== void 0);",
  "\t\t\t\t\t\tconst active = rows.find((row) => (row.retainedBy?.mainView ?? 0) > 0);",
  "\t\t\t\t\t\treturn String((active ?? rows[0] ?? { id: list.ids[0] }).id ?? \"\");",
  "\t\t\t\t\t} catch {",
  "\t\t\t\t\t\treturn \"\";",
  "\t\t\t\t\t}",
  "\t\t\t\t};",
  "\t\t\t\tdock.effect(() => dock.get(\"sidebarRightTabs\").register({",
  "\t\t\t\t\tid: \"workflow-lite-dock\",",
  "\t\t\t\t\tkind: \"workflow-lite-dock\",",
  "\t\t\t\t\ttitle: () => \"轻量工作流\",",
  "\t\t\t\t\tguide: [{",
  "\t\t\t\t\t\tid: \"workflow-lite-dock\",",
  "\t\t\t\t\t\torder: 30,",
  "\t\t\t\t\t\ttitle: () => \"轻量工作流\",",
  "\t\t\t\t\t\tdescription: () => \"画布编排步骤、条件与循环，编译成计划交给模型执行\"",
  "\t\t\t\t\t}]",
  "\t\t\t\t}), \"workflow-lite: right panel tab\");",
  "\t\t\t\tdock.slots.inject(\"sidebar.right.pane.tab\", () => dock.slots.register({",
  "\t\t\t\t\tname: \"sidebar.right.pane.tab\",",
  "\t\t\t\t\tkey: \"workflow-lite-dock\",",
  "\t\t\t\t\tinject: () => ({})",
  "\t\t\t\t}, function WorkflowLiteDockPane() {",
  "\t\t\t\t\tconst sessionId = currentSession();",
  "\t\t\t\t\tconst t = dock.get(\"locale\").bind(NS);",
  "\t\t\t\t\tconst openView = (view) => {",
  "\t\t\t\t\t\ttry {",
  "\t\t\t\t\t\t\tdock.get(\"conversation\").selectView(view);",
  "\t\t\t\t\t\t} catch { /* 会话视图服务可选 */ }",
  "\t\t\t\t\t};",
  "\t\t\t\t\tif (sessionId === \"\") return react.createElement(\"div\", {",
  "\t\t\t\t\t\tstyle: { padding: \"18px 16px\", fontSize: 13, color: \"var(--dsw-alias-label-secondary,#657185)\" }",
  "\t\t\t\t\t}, \"先打开一个会话，再回到这里使用轻量工作流。\");",
  "\t\t\t\t\treturn react.createElement(WorkflowView, { rpc, sessionId, sessions, desktop, t, openView });",
  "\t\t\t\t}));",
  "\t\t\t});",
  "\t\t\t//#endregion",
  "\t\t}",
].join("\n");

const next = src.replace(marker, block);
writeFileSync(target, next, "utf8");
console.log("patched", { before: src.length, after: next.length });
