
import { readFileSync, writeFileSync, existsSync, copyFileSync } from "node:fs";

const target = process.argv[2];
if (!target) { console.error("usage: node patch-workflow-lite-nav.mjs <client.js>"); process.exit(2); }
const backup = target + ".orig-nav";
const src = readFileSync(target, "utf8");

if (src.includes("workflow-lite-nav")) {
  console.log("already-patched");
  process.exit(0);
}
const anchor = "\n\t\t}\n\t\t//#endregion\n\t\texports.apply = apply;";
if (!src.includes(anchor)) {
  console.error("anchor-not-found");
  process.exit(2);
}
if (!existsSync(backup)) copyFileSync(target, backup);

const block = [
  "\t\t\t//#region workdsh-preview: 左侧导航栏（轻量工作流） workflow-lite-nav",
  "\t\t\tctx.inject([\"sessions\", \"layout\"], (shell) => {",
  "\t\t\t\tconst currentSession = () => {",
  "\t\t\t\t\ttry {",
  "\t\t\t\t\t\tconst list = shell.get(\"sessions\").list.getSnapshot();",
  "\t\t\t\t\t\tconst rows = list.ids.map((id) => list.byId[id]).filter((row) => row !== void 0);",
  "\t\t\t\t\t\tconst active = rows.find((row) => (row.retainedBy?.mainView ?? 0) > 0);",
  "\t\t\t\t\t\treturn String((active ?? rows[0] ?? { id: list.ids[0] }).id ?? \"\");",
  "\t\t\t\t\t} catch {",
  "\t\t\t\t\t\treturn \"\";",
  "\t\t\t\t\t}",
  "\t\t\t\t};",
  "\t\t\t\tconst t = shell.get(\"locale\").bind(NS);",
  "\t\t\t\tconst openView = (view) => {",
  "\t\t\t\t\ttry {",
  "\t\t\t\t\t\tshell.get(\"layout\").selectPanel(null);",
  "\t\t\t\t\t} catch { /* 布局服务可选 */ }",
  "\t\t\t\t\ttry {",
  "\t\t\t\t\t\tshell.get(\"conversation\").selectView(view || \"chat\");",
  "\t\t\t\t\t} catch { /* 会话视图服务可选 */ }",
  "\t\t\t\t};",
  "\t\t\t\tshell.slots.inject(\"main\", () => shell.slots.register({",
  "\t\t\t\t\tname: \"main\",",
  "\t\t\t\t\tkey: \"workflow-lite\"",
  "\t\t\t\t}, function WorkflowLiteMainPanel() {",
  "\t\t\t\t\tconst sessionId = currentSession();",
  "\t\t\t\t\tif (sessionId === \"\") return react.createElement(\"div\", {",
  "\t\t\t\t\t\tstyle: { padding: \"32px 24px\", fontSize: 13, color: \"var(--dsw-alias-label-secondary,#657185)\" }",
  "\t\t\t\t\t}, \"先打开一个会话，再回到这里使用轻量工作流。\");",
  "\t\t\t\t\treturn react.createElement(WorkflowView, { rpc, sessionId, sessions, desktop, t, openView });",
  "\t\t\t\t}));",
  "\t\t\t\tshell.slots.inject(\"sidebar.panellist\", () => shell.slots.register({",
  "\t\t\t\t\tname: \"sidebar.panellist\",",
  "\t\t\t\t\tid: \"workflow-lite\",",
  "\t\t\t\t\tlabel: \"轻量工作流\",",
  "\t\t\t\t\torder: 46",
  "\t\t\t\t}, function WorkflowLiteNavIcon({ size }) {",
  "\t\t\t\t\tconst s = typeof size === \"number\" ? size : 20;",
  "\t\t\t\t\treturn react.createElement(\"svg\", {",
  "\t\t\t\t\t\twidth: s,",
  "\t\t\t\t\t\theight: s,",
  "\t\t\t\t\t\tviewBox: \"0 0 24 24\",",
  "\t\t\t\t\t\tfill: \"none\",",
  "\t\t\t\t\t\tstroke: \"currentColor\",",
  "\t\t\t\t\t\tstrokeWidth: 1.6,",
  "\t\t\t\t\t\tstrokeLinecap: \"round\",",
  "\t\t\t\t\t\tstrokeLinejoin: \"round\"",
  "\t\t\t\t\t},",
  "\t\t\t\t\t\treact.createElement(\"rect\", { key: \"a\", x: 3, y: 4, width: 7, height: 6, rx: 1.5 }),",
  "\t\t\t\t\t\treact.createElement(\"rect\", { key: \"b\", x: 14, y: 14, width: 7, height: 6, rx: 1.5 }),",
  "\t\t\t\t\t\treact.createElement(\"path\", { key: \"c\", d: \"M10 7h4a2 2 0 0 1 2 2v5\" }),",
  "\t\t\t\t\t\treact.createElement(\"path\", { key: \"d\", d: \"M3 17h8a2 2 0 0 0 2-2\" })",
  "\t\t\t\t\t);",
  "\t\t\t\t}));",
  "\t\t\t});",
  "\t\t\t//#endregion",
].join("\n");

const next = src.replace(anchor, "\n" + block + anchor);
writeFileSync(target, next, "utf8");
console.log("patched", { before: src.length, after: next.length });