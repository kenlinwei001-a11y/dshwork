#!/usr/bin/env node
/**
 * Re-apply the DSH 0.2.1 compatibility shims for dsh-moki-taskboard.
 *
 * Two 0.2.2-only APIs break on DSH 0.2.1:
 *  1. The panel route is registered with `webServer.register({ resource })`.
 *     0.2.1 only calls `route.handler(req, res)`, so opening the taskboard
 *     fails with 400/404. The shim adapts Node req/res to the plugin's
 *     Fetch-style resource and calls ctx.connection.admit + route.resource.
 *  2. Dispatch calls `agent.model.select(selection)`; 0.2.1 has no
 *     `agent.model`, but the public session controller exposes
 *     `selectModel({ sessionId, provider, model, reasoningEffort? })`.
 *     Without the shim every run fails with
 *     "Cannot read properties of undefined (reading 'select')".
 *
 * Idempotent and safe to run on every service start and from a launchd watcher.
 * No plugin installed -> no-op. Unknown layout -> leave the file untouched (exit 2).
 *
 * Usage:
 *   node patch-moki-route.mjs [--home <DSH_HOME>] [--profile preview] [--quiet] [--check]
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { homedir } from 'node:os';
import { join } from 'node:path';

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const at = args.indexOf(name);
  return at >= 0 && args[at + 1] ? args[at + 1] : fallback;
};
const home = opt('--home', process.env.DSH_HOME || join(homedir(), 'workdsh/.test-runtime/preview'));
const profile = opt('--profile', 'preview');
const quiet = args.includes('--quiet');
const checkOnly = args.includes('--check');
const log = (...values) => { if (!quiet) console.log(...values); };

const file = join(home, 'profiles', profile, 'node_modules', 'dsh-moki-taskboard', 'dist', 'host.mjs');
if (!existsSync(file)) {
  log('moki compat shims: dsh-moki-taskboard not installed; nothing to do');
  process.exit(0);
}

const source = readFileSync(file, 'utf8');
const routeMarker = 'route.resource(req, admitted.peer)';
const modelMarker = 'sessionController.selectModel({ sessionId: threadId';
const modelCall = 'agent.model.select(selection);';

const openPattern = /ctx\.effect\(\(\) => ctx\.webServer\.register\(\{\s*kind:\s*"exact",\s*path:\s*"\/moki-taskboard\/open",\s*resource:\s*async\s*\(req,\s*peer\)\s*=>\s*\{/;
const closePattern = /\}\s*\}\s*\)\s*,\s*"moki-taskboard: desktop panel"\s*\)\s*;/;
const openReplacement = 'ctx.effect(() => { const dispose = ctx.webServer.register({ kind: "exact", path: "/moki-taskboard/open", resource: async (req, peer) => {';
const closeReplacement = '} }); const route = ctx.webServer.exact.get("/moki-taskboard/open"); if (route && !route.handler) route.handler = async (nodeReq, nodeRes) => { const host = nodeReq.headers.host ?? "127.0.0.1"; const req = new Request(new URL(nodeReq.url ?? "/", "http://" + host), { method: nodeReq.method ?? "GET", headers: nodeReq.headers }); const admitted = ctx.connection.admit(req); const response = await route.resource(req, admitted.peer); const hdrs = {}; response.headers.forEach((v, k) => { hdrs[k] = v; }); nodeRes.writeHead(response.status, hdrs); nodeRes.end(Buffer.from(await response.arrayBuffer())); }; return dispose; }, "moki-taskboard: desktop panel");';
const modelReplacement = 'await this.ctx.sessionController.selectModel({ sessionId: threadId, provider: selection.provider, model: selection.model, ...(selection.reasoningEffort === void 0 ? {} : { reasoningEffort: selection.reasoningEffort }) });';

let next = source;
const applied = [];
let unsupported = false;

if (!next.includes(routeMarker)) {
  if (!openPattern.test(next) || !closePattern.test(next)) {
    console.error('moki route shim: unsupported plugin layout (route); file left untouched');
    unsupported = true;
  } else {
    next = next.replace(openPattern, openReplacement).replace(closePattern, closeReplacement);
    if (next.includes(routeMarker)) applied.push('route');
    else {
      console.error('moki route shim: replacement did not take; file left untouched');
      unsupported = true;
    }
  }
}

if (!next.includes(modelMarker)) {
  if (next.includes(modelCall)) {
    next = next.replace(modelCall, modelReplacement);
    if (next.includes(modelMarker)) applied.push('model');
    else {
      console.error('moki model shim: replacement did not take; file left untouched');
      unsupported = true;
    }
  } else {
    // The plugin either already uses a 0.2.1-compatible call or changed shape.
    log('moki model shim: no 0.2.2-only agent.model.select call found; nothing to do');
  }
}

if (unsupported) process.exit(2);
if (applied.length === 0) {
  log('moki compat shims: already applied');
  process.exit(0);
}
if (checkOnly) {
  console.log('moki compat shims: NOT applied (' + applied.join(' + ') + ')');
  process.exit(1);
}

const backupDir = join(homedir(), 'agent-backups', 'moki-shim');
mkdirSync(backupDir, { recursive: true });
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const backup = join(backupDir, `host.mjs.${stamp}`);
writeFileSync(backup, source);
writeFileSync(file, next);

const syntax = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
if (syntax.status !== 0) {
  writeFileSync(file, source);
  console.error('moki compat shims: syntax check failed; original restored\n' + String(syntax.stderr || '').slice(0, 600));
  process.exit(3);
}
// Always report an actual re-application so the launchd watchdog log records upgrades.
console.log(`moki compat shims: applied ${applied.join(' + ')} (backup ${backup})`);
