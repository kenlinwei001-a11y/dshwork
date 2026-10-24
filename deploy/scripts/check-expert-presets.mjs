#!/usr/bin/env node
// 检查已发布专家修订的 expert-package 是否与冻结修订逐字节一致。
// 这是 experts/package-drift 的预防/巡检工具：专家预设目录是不可变编译产物，
// 只能由专家管理器的“发布”流程生成；任何手工编辑都会让绑定该修订的会话无法运行。
//
// 用法:
//   node deploy/scripts/check-expert-presets.mjs [--home DSH_HOME] [--agents AGENTS_HOME]
// 退出码: 0=全部一致; 1=存在 drift; 2=参数/读取错误
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}
const home = arg('--home', process.env.DSH_HOME || path.join(os.homedir(), 'workdsh/.test-runtime/preview'));
const agents = arg('--agents', process.env.DSH_AGENTS_HOME || path.join(os.homedir(), '.agents'));
const revisionsDir = path.join(home, 'storages/workdsh_experts/revisions');
const bindingsDir = path.join(home, 'storages/workdsh_experts/bindings');
const presetRoot = path.join(agents, '.workdsh-state/experts/presets');

if (!fs.existsSync(revisionsDir)) {
  console.error('找不到专家修订目录:', revisionsDir);
  process.exit(2);
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}
function decodeAsset(asset) {
  if (typeof asset === 'string') return { bytes: Buffer.from(asset, 'base64'), executable: false };
  if (asset && typeof asset === 'object') {
    const data = asset.data ?? asset.base64 ?? '';
    const bytes = typeof data === 'string' ? Buffer.from(data, 'base64') : Buffer.from(data);
    return { bytes, executable: asset.executable === true || asset.mode === '755' };
  }
  return { bytes: Buffer.alloc(0), executable: false };
}

const bindings = new Map();
if (fs.existsSync(bindingsDir)) {
  for (const file of fs.readdirSync(bindingsDir)) {
    if (!file.endsWith('.json')) continue;
    try {
      const b = readJson(path.join(bindingsDir, file)).record ?? readJson(path.join(bindingsDir, file));
      const rev = b.expertRevisionRef?.revisionId ?? b.expertRevisionRef;
      if (typeof rev === 'string') {
        if (!bindings.has(rev)) bindings.set(rev, []);
        bindings.get(rev).push(file.replace(/^session-/, '').replace(/\.json$/, ''));
      }
    } catch { /* ignore malformed bindings; revisions are the source of truth */ }
  }
}

let checked = 0;
let drift = 0;
const rows = [];
for (const file of fs.readdirSync(revisionsDir)) {
  if (!file.endsWith('.json')) continue;
  let record;
  try { record = readJson(path.join(revisionsDir, file)).record ?? readJson(path.join(revisionsDir, file)); }
  catch (error) { console.error('无法读取修订', file, error.message); process.exitCode = 2; continue; }
  const docs = record.definition?.packageDocuments ?? {};
  const assets = record.definition?.packageAssets ?? {};
  if (!Object.keys(docs).length && !Object.keys(assets).length) continue;
  checked++;
  const preset = record.presetRevisionRef;
  const root = path.join(presetRoot, String(preset), 'expert-package');
  const problems = [];
  const expected = [...Object.keys(docs), ...Object.keys(assets)].sort();
  const found = [];
  if (!fs.existsSync(root)) problems.push('missing_preset_dir');
  else {
    const walk = (dir, prefix = '') => {
      for (const name of fs.readdirSync(dir)) {
        const p = path.join(dir, name);
        const rel = prefix ? `${prefix}/${name}` : name;
        const st = fs.lstatSync(p);
        if (st.isSymbolicLink()) { problems.push(`symlink:${rel}`); continue; }
        if (st.isDirectory()) walk(p, rel);
        else if (st.isFile()) found.push(rel);
        else problems.push(`special:${rel}`);
      }
    };
    walk(root);
  }
  const actual = found.sort();
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    const missing = expected.filter(x => !actual.includes(x));
    const extra = actual.filter(x => !expected.includes(x));
    if (missing.length) problems.push('missing:' + missing.slice(0, 5).join(','));
    if (extra.length) problems.push('extra:' + extra.slice(0, 5).join(','));
  }
  for (const [rel, text] of Object.entries(docs)) {
    const p = path.join(root, rel);
    if (!fs.existsSync(p)) continue;
    if (fs.readFileSync(p, 'utf8') !== text) problems.push('content:' + rel);
  }
  for (const [rel, asset] of Object.entries(assets)) {
    const p = path.join(root, rel);
    if (!fs.existsSync(p)) continue;
    const expectedAsset = decodeAsset(asset);
    const actualBytes = fs.readFileSync(p);
    if (!actualBytes.equals(expectedAsset.bytes)) problems.push('asset:' + rel);
    if (expectedAsset.executable && (fs.statSync(p).mode & 0o111) === 0) problems.push('exec:' + rel);
  }
  const bound = bindings.get(record.revisionId) ?? [];
  const status = problems.length ? 'DRIFT' : 'OK';
  if (problems.length) drift++;
  rows.push({ status, file, revisionId: record.revisionId, preset, bound, problems });
}
for (const row of rows) {
  console.log(row.status, row.file, 'preset=' + row.preset,
    row.bound.length ? 'bound=' + row.bound.join(',') : 'bound=-',
    row.problems.length ? row.problems.join(' | ') : '');
}
console.log(`checked=${checked} drift=${drift}`);
process.exit(drift ? 1 : 0);
