// 把会话文件头部帧里的 cwd 从来源机器路径改写到目标机器。
// 只改第一帧(header)的 cwd，不改对话正文，避免破坏会话内容。
// 用法:
//   node retarget-sessions.mjs <目标DSH_HOME> [--new-repo PATH] [--new-agents PATH] [--dry-run]
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const MAGIC = 0xfd2fb528;
function scanFrames(buf) {
  const frames = [];
  let pos = 0;
  while (pos + 4 <= buf.length) {
    if (buf.readUInt32LE(pos) !== MAGIC) return { frames, tornStart: pos };
    const start = pos; pos += 4;
    if (pos >= buf.length) return { frames, tornStart: start };
    const fhd = buf[pos++];
    const fcsFlag = (fhd >> 6) & 3;
    const single = (fhd >> 5) & 1;
    const checksum = (fhd >> 2) & 1;
    const dictFlag = fhd & 3;
    if (!single) { if (pos >= buf.length) return { frames, tornStart: start }; pos++; }
    pos += [0, 1, 2, 4][dictFlag];
    const fcsSize = fcsFlag === 0 ? (single ? 1 : 0) : fcsFlag === 1 ? 2 : fcsFlag === 2 ? 4 : 8;
    pos += fcsSize;
    if (pos > buf.length) return { frames, tornStart: start };
    let last = false, blocks = 0;
    while (!last) {
      if (pos + 3 > buf.length) return { frames, tornStart: start };
      const hdr = buf[pos] | (buf[pos + 1] << 8) | (buf[pos + 2] << 16); pos += 3;
      last = (hdr & 1) === 1;
      const type = (hdr >> 1) & 3;
      const size = hdr >> 3;
      if (type === 0 || type === 2) pos += size;
      else if (type === 1) pos += 1;
      else return { frames, tornStart: start };
      if (pos > buf.length) return { frames, tornStart: start };
      if (++blocks > 1000000) return { frames, tornStart: start };
    }
    if (checksum) pos += 4;
    if (pos > buf.length) return { frames, tornStart: start };
    frames.push({ start, end: pos });
  }
  return { frames, tornStart: pos < buf.length ? pos : undefined };
}

const args = process.argv.slice(2);
const target = args[0];
const dry = args.includes('--dry-run');
const get = (name, dflt) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : dflt; };
if (!target) { console.error('用法: node retarget-sessions.mjs <目标DSH_HOME> [--new-repo PATH] [--dry-run]'); process.exit(2); }
const oldHome = '/Users/apple/workdsh/.test-runtime/preview';
const oldRepo = '/Users/apple/Desktop/workdsh';
const oldAgents = '/Users/apple/.agents';
const newHome = target;
const newRepo = get('--new-repo', path.join(process.env.HOME || '', 'Desktop/workdsh'));
const newAgents = get('--new-agents', path.join(process.env.HOME || '', '.agents'));

const sessionRoot = path.join(target, 'sessions');
if (!fs.existsSync(sessionRoot)) { console.log('没有 sessions 目录，跳过:', sessionRoot); process.exit(0); }

function mapPath(p) {
  if (typeof p !== 'string') return p;
  return p.split(oldHome).join(newHome)
          .split(oldRepo).join(newRepo)
          .split(oldAgents).join(newAgents);
}

let changed = 0, scanned = 0;
function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.isFile() && e.name === 'session.v4.jsonl.zstd') processFile(p);
  }
}
function processFile(file) {
  scanned++;
  const buf = fs.readFileSync(file);
  const { frames, tornStart } = scanFrames(buf);
  if (!frames.length) { console.log('SKIP no frames', file); return; }
  const first = frames[0];
  let header;
  try { header = JSON.parse(zlib.zstdDecompressSync(buf.subarray(first.start, first.end)).toString('utf8')); }
  catch (e) { console.log('SKIP header decode', file, e.message); return; }
  if (typeof header.cwd !== 'string') return;
  const next = mapPath(header.cwd);
  if (next === header.cwd) return;
  console.log((dry ? 'DRY ' : 'FIX ') + file + '\n  ' + header.cwd + '\n  -> ' + next);
  if (dry) return;
  header.cwd = next;
  const firstOut = zlib.zstdCompressSync(Buffer.from(JSON.stringify(header), 'utf8'));
  const out = [firstOut, ...frames.slice(1).map(f => buf.subarray(f.start, f.end))];
  if (tornStart !== undefined) out.push(buf.subarray(tornStart));
  const tmp = file + '.retarget-tmp';
  fs.writeFileSync(tmp, Buffer.concat(out));
  fs.chmodSync(tmp, 0o600);
  fs.renameSync(tmp, file);
  // 回读校验
  const check = fs.readFileSync(file);
  const cf = scanFrames(check).frames[0];
  const ch = JSON.parse(zlib.zstdDecompressSync(check.subarray(cf.start, cf.end)).toString('utf8'));
  if (ch.cwd !== next) throw new Error('verify failed: ' + file);
  changed++;
}
walk(sessionRoot);
console.log(JSON.stringify({ scanned, changed, dry }));
