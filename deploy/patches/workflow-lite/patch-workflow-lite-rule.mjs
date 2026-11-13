#!/usr/bin/env node
// 让 workflow_lite 的 write_node 对 outputs[].rule 更宽容：
//  - rule 继续接受纯文本（推荐写法，不再引导模型往里面塞 JSON 字符串）
//  - 新增 rule_object（对象），插件在写入前 stringify 成 rule 文本
// 这是第三方包补丁：装/升级 @xiaoso/dsh-workflow-lite 后由 reapply-local-patches.sh 重打。
import { readFileSync, writeFileSync } from 'node:fs';

const MARK = 'workflow-lite-rule-patch';
const target = process.argv[2];
if (!target) {
  console.error('usage: node patch-workflow-lite-rule.mjs <lib/index.mjs>');
  process.exit(2);
}

let src;
try {
  src = readFileSync(target, 'utf8');
} catch (error) {
  console.error('read failed:', target, error.message);
  process.exit(2);
}
if (src.includes('rule_object') || src.includes(MARK)) {
  console.log('already-patched');
  process.exit(0);
}

const schemaOld = 'rule: {\n\t\t\t\t\ttype: "string",\n\t\t\t\t\tdescription: "这份产出该怎么写：结构、必须包含什么、长度上限（进资源说明）。"\n\t\t\t\t},';
const schemaNew = 'rule: {\n\t\t\t\t\ttype: "string",\n\t\t\t\t\tdescription: "这份产出该怎么写：纯文本说明；不要在这里写 JSON 字符串。"\n\t\t\t\t},\n\t\t\t\trule_object: {\n\t\t\t\t\ttype: "object",\n\t\t\t\t\tadditionalProperties: true,\n\t\t\t\t\tdescription: "结构化产出规则对象；插件会转成 JSON 文本写入 rule。rule 与 rule_object 二选一。"\n\t\t\t\t},';

const descOld = '"节点定位一律用 id。",';
const descNew = '"节点定位一律用 id。",\n\t"write_node 的 outputs[].rule 是纯文本说明，不要在里面嵌 JSON 字符串；需要结构化规则时用 outputs[].rule_object（对象），插件会转成文本。",';

const mapOld = 'upsert.outputs = args.outputs.map((spec) => spec.rule === void 0 ? { path: spec.path } : {\n\t\t\t\t\t\tpath: spec.path,\n\t\t\t\t\t\trule: spec.rule\n\t\t\t\t\t});';
const mapNew = 'upsert.outputs = args.outputs.map((spec) => {\n\t\t\t\t\t\tconst rule = ruleText(spec.rule_object ?? spec.rule);\n\t\t\t\t\t\treturn rule === void 0 ? { path: spec.path } : { path: spec.path, rule };\n\t\t\t\t\t});';

const helperAnchor = 'function createWorkflowLiteHandler(deps) {';
const helper = `// ${MARK}
function ruleText(value) {
\tif (value === void 0 || value === null) return void 0;
\tif (typeof value === "string") return value;
\ttry { return JSON.stringify(value); } catch { return String(value); }
}
`;

const checks = [['schema', schemaOld], ['description', descOld], ['outputs-map', mapOld], ['handler', helperAnchor]];
for (const [name, anchor] of checks) {
  const count = src.split(anchor).length - 1;
  if (count !== 1) {
    console.error(`anchor ${name}: expected 1 occurrence, found ${count}`);
    process.exit(3);
  }
}

let next = src;
next = next.replace(schemaOld, schemaNew);
next = next.replace(descOld, descNew);
next = next.replace(mapOld, mapNew);
next = next.replace(helperAnchor, helper + helperAnchor);
writeFileSync(target, next, 'utf8');
console.log('patched', { before: src.length, after: next.length });
