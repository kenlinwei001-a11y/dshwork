import { spawn } from 'node:child_process';
import {ensureNativeWorkbenchFrame} from './native-workbench-frame-patch.mjs';
import { previewProcessEnvironment } from './preview-process-environment.mjs';
import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { withoutRedundantAgentTeamProfile } from './preview-agent-team.mjs';
import { previewHome as resolvePreviewHome } from './preview-home.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const previewHome = resolvePreviewHome();
const agentsHome = process.env.DSH_AGENTS_HOME ?? join(previewHome, 'agents');
const port = process.env.WORKDSH_PREVIEW_PORT ?? '18989';
// Preview currently needs a larger startup heap; this does not fix the underlying growth.
const heapMb = process.env.WORKDSH_PREVIEW_HEAP_MB ?? '8192';
if (!/^\d+$/.test(heapMb) || Number(heapMb) < 512) throw new Error('WORKDSH_PREVIEW_HEAP_MB must be an integer >= 512');
const profile = resolve(previewHome, 'profiles/preview');
const profileManifestPath = resolve(profile, 'package.json');
if (existsSync(profileManifestPath)) {
  const profileManifest = JSON.parse(readFileSync(profileManifestPath, 'utf8'));
  const normalizedManifest = withoutRedundantAgentTeamProfile(profileManifest);
  if (normalizedManifest) {
    writeFileSync(profileManifestPath, `${JSON.stringify(normalizedManifest, null, 2)}\n`);
    console.log('Removed redundant standalone Agent Team profile; WorkDSH experts owns Team composition.');
  }
}
const dsh = resolve(profile, 'node_modules/@deepseek-ai/dsh/lib/bin.js');
// Fail before serving a broken UI if preview:install has not migrated the CLI.
const cliManifest = resolve(profile, 'node_modules/@deepseek-ai/dsh/package.json');
const expected = JSON.parse(readFileSync(resolve(root, 'node_modules/@deepseek-ai/dsh/package.json'), 'utf8')).version;
let installed;
try { installed = JSON.parse(readFileSync(cliManifest, 'utf8')); }
catch { throw new Error('Preview runtime is missing. Run corepack pnpm preview:install first.'); }
if (installed.version !== expected) throw new Error('Preview runtime is out of date. Run corepack pnpm preview:install first.');
const profileRequire = createRequire(resolve(profile, 'package.json'));
const bootFor = (consumer) => realpathSync(createRequire(profileRequire.resolve(`${consumer}/package.json`)).resolve('@deepseek-ai/dsh-app-boot'));
if (bootFor('@deepseek-ai/dsh') !== bootFor('@deepseek-ai/dsh-config-editor')) {
  throw new Error('Preview runtime has split settings dependencies. Run corepack pnpm preview:install first.');
}

mkdirSync(previewHome, { recursive: true });
// User-authorized local-preview outer frame only; exact version and byte guards.
await ensureNativeWorkbenchFrame(profile);
const child = spawn(process.execPath, [`--max-old-space-size=${heapMb}`, dsh, '--profile', 'preview', '--host', '127.0.0.1', '--port', port, '--no-open'], {
  cwd: root,
  env: { ...previewProcessEnvironment(root), DSH_HOME: previewHome, DSH_AGENTS_HOME: agentsHome },
  stdio: 'inherit',
});

// 收到终止信号时，必须由本进程负责把子进程杀干净再退，否则会出现孤儿：
// 原实现只把信号转发给子进程、自身不退，launchd 在宽限期后 SIGKILL 本进程，
// 子进程（dsh 服务）便带着 profile 留在世上；下一个实例启动时会在 storage
// 初始化处等这把永不释放的锁——表现为「永远不起监听」。
const shutdown = (signal) => {
  try { child.kill(signal); } catch {}
  const force = setTimeout(() => {
    try { child.kill('SIGKILL'); } catch {}
    process.exit(0);
  }, 8000);
  force.unref?.();
};
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => shutdown(signal));
child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exitCode = code ?? 1;
});
