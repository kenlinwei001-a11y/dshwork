
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export const BT = String.fromCharCode(96);
export const code = s => BT + s + BT;

export function sha256(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}
export function sha256File(p) {
  return sha256(fs.readFileSync(p));
}
export function readJson(p) {
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}
export function readJsonSafe(p) {
  try { return readJson(p); } catch { return null; }
}
export function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}
export function writeFile(p, content) {
  ensureDir(path.dirname(p));
  fs.writeFileSync(p, content);
}
export function rmrf(p) {
  fs.rmSync(p, { recursive: true, force: true });
}
export function human(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(2) + ' MB';
}
export function cmp(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}
/** Recursively list files. Returns [{abs, rel, bytes, mtimeMs}] sorted by rel. */
export function walk(dir, base, skip, acc) {
  base = base || dir;
  acc = acc || [];
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return acc; }
  entries.sort((x, y) => cmp(x.name, y.name));
  for (const e of entries) {
    const abs = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === '.git' || e.name === 'node_modules' || e.name === '__pycache__') continue;
      walk(abs, base, skip, acc);
    } else {
      const rel = path.relative(base, abs);
      if (skip && skip(rel, e.name)) continue;
      const st = fs.statSync(abs);
      acc.push({ abs, rel, bytes: st.size, mtimeMs: st.mtimeMs });
    }
  }
  return acc;
}
/** Skip editor backups and OS noise: never part of a skill contract. */
export function skipNoise(rel, name) {
  if (name === '.DS_Store') return true;
  if (name.indexOf('SKILL.md.bak') === 0) return true;
  if (name.endsWith('.bak') || name.endsWith('.bak~') || name.endsWith('~')) return true;
  if (name === '.DS_Store') return true;
  return false;
}
/** Parse YAML-ish frontmatter without a YAML dependency (single-line scalars only). */
export function frontmatter(rawText) {
  // CRLF is common in third-party skills; without this the whole frontmatter fails to parse.
  const text = String(rawText).replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const out = { meta: {}, body: text, raw: '' };
  if (!text.startsWith('---')) return out;
  const end = text.indexOf('\n---', 3);
  if (end < 0) return out;
  const head = text.slice(3, end);
  out.raw = head;
  let key = null;
  for (const line of head.split('\n')) {
    if (!line.trim()) continue;
    const m = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line);
    if (m) { key = m[1]; out.meta[key] = m[2].replace(/^["']|["']$/g, ''); continue; }
    if (key && /^\s+/.test(line)) out.meta[key] = String(out.meta[key] || '') + ' ' + line.trim();
  }
  const bodyStart = text.indexOf('\n', end + 1);
  out.body = bodyStart < 0 ? '' : text.slice(bodyStart + 1);
  return out;
}
export function table(headers, rows) {
  const esc = v => String(v === undefined || v === null ? '' : v).replace(/\|/g, '\\|').replace(/\r?\n/g, ' ');
  return ['| ' + headers.join(' | ') + ' |', '|' + headers.map(() => '---').join('|') + '|',
    ...rows.map(r => '| ' + r.map(esc).join(' | ') + ' |')].join('\n');
}
export function fence(text, lang) {
  const s = String(text === undefined || text === null ? '' : text);
  const ticks = s.indexOf('~~~') >= 0 ? BT.repeat(4) : '~~~';
  return ticks + (lang || 'text') + '\n' + s.replace(/\s+$/, '') + '\n' + ticks;
}
export function iso(ms) {
  return new Date(ms).toISOString().replace(/\.\d+Z$/, 'Z');
}
/** Redact obvious secrets from free text (defense in depth before writing docs). */
export function redactSecrets(text) {
  const s = String(text);
  return s
    .replace(/sk-[A-Za-z0-9_-]{16,}/g, 'sk-***REDACTED***')
    .replace(/(Bearer\s+)[A-Za-z0-9._-]{16,}/g, '$1***REDACTED***')
    .replace(/((?:token|secret|password|api[_-]?key|authorization)["'\s:=]+)([A-Za-z0-9._-]{12,})/gi, '$1***REDACTED***');
}
export function csvCell(v) {
  const s = String(v === undefined || v === null ? '' : v);
  if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
  return s;
}
