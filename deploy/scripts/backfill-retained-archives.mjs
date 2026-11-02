#!/usr/bin/env node
/**
 * Backfill the sealed archive for retained Skill revisions.
 *
 * The skills plugin keeps a second, read-only copy under
 * `<retained-root>/.archives/<revisionId>/<skill>` so a drifted mounted
 * snapshot can be restored instead of permanently refusing the task. This
 * script fills that store for revisions created before the archive existed.
 *
 * It never writes a mounted snapshot: revisions whose mounted digest no longer
 * matches their manifest are reported and skipped (they need a repair source).
 *
 * Usage:
 *   node deploy/scripts/backfill-retained-archives.mjs [retained-root]
 *   node deploy/scripts/backfill-retained-archives.mjs --check
 */
import { chmod, copyFile, mkdir, readFile, readdir, rm, stat } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, join, relative } from 'node:path';
import { homedir } from 'node:os';

const args = process.argv.slice(2);
const checkOnly = args.includes('--check');
const explicit = args.find(arg => !arg.startsWith('-'));
const agentsHome = process.env.DSH_AGENTS_HOME ?? join(homedir(), '.agents');
const retainedRoot = explicit ?? join(agentsHome, '.workdsh-state/skills/retained-revisions');
const archiveRoot = join(retainedRoot, '.archives');

async function resourceFiles(directory, root = directory, depth = 0) {
  if (depth > 4) return [];
  const rows = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const row of rows) {
    if (row.isSymbolicLink()) continue;
    const path = join(directory, row.name);
    if (row.isDirectory()) files.push(...await resourceFiles(path, root, depth + 1));
    else if (row.isFile() && row.name !== 'SKILL.md') files.push(relative(root, path));
    if (files.length >= 200) break;
  }
  return files.slice(0, 200).sort();
}

async function digest(directory) {
  const paths = ['SKILL.md', ...await resourceFiles(directory)].sort();
  const hash = createHash('sha256');
  for (const path of paths) {
    hash.update(path); hash.update('\0');
    hash.update(await readFile(join(directory, path))); hash.update('\0');
  }
  return hash.digest('hex');
}

async function treeEntries(root) {
  const dirs = [root];
  const files = [];
  const visit = async (directory) => {
    for (const row of await readdir(directory, { withFileTypes: true })) {
      if (row.isSymbolicLink()) continue;
      const path = join(directory, row.name);
      if (row.isDirectory()) { dirs.push(path); await visit(path); }
      else if (row.isFile()) files.push(path);
    }
  };
  await visit(root);
  return { dirs, files };
}

async function setTreeMode(root, fileMode, dirMode) {
  let entries;
  try { entries = await treeEntries(root); }
  catch (error) { if (error.code === 'ENOENT') return; throw error; }
  for (const file of entries.files) await chmod(file, fileMode);
  for (const directory of [...entries.dirs].reverse()) await chmod(directory, dirMode);
}

async function exists(path) { try { await stat(path); return true; } catch { return false; } }

const manifests = (await readdir(retainedRoot)).filter(name => name.endsWith('.manifest.json')).sort();
let archived = 0, existing = 0, sealed = 0, drifted = 0, missing = 0;
for (const manifestName of manifests) {
  const manifest = JSON.parse(await readFile(join(retainedRoot, manifestName), 'utf8'));
  const ref = manifest.ref;
  const mounted = join(retainedRoot, ref.revisionId, ref.name);
  const archive = join(archiveRoot, ref.revisionId, ref.name);
  if (!await exists(mounted)) { missing++; console.log('MISSING', ref.skillId, ref.revisionId); continue; }
  if (await digest(mounted) !== manifest.contentDigest) { drifted++; console.log('DRIFT  ', ref.skillId, ref.revisionId); continue; }
  if (await exists(archive) && await digest(archive) === manifest.contentDigest) {
    existing++;
    if (!checkOnly) { await setTreeMode(archive, 0o444, 0o555); sealed++; }
    continue;
  }
  if (checkOnly) { archived++; console.log('TODO   ', ref.skillId, ref.revisionId); continue; }
  await setTreeMode(archive, 0o644, 0o755);
  await rm(archive, { recursive: true, force: true });
  await mkdir(archive, { recursive: true });
  const files = ['SKILL.md', ...await resourceFiles(mounted)].sort();
  for (const file of files) {
    const to = join(archive, file);
    await mkdir(dirname(to), { recursive: true });
    await copyFile(join(mounted, file), to);
  }
  if (await digest(archive) !== manifest.contentDigest) { console.error('ARCHIVE MISMATCH', ref.skillId, ref.revisionId); process.exitCode = 1; continue; }
  await setTreeMode(archive, 0o444, 0o555);
  archived++;
}
console.log(`\nretained-root: ${retainedRoot}`);
console.log(`manifests=${manifests.length} archived=${archived} existing=${existing} resealed=${sealed} drifted=${drifted} missing=${missing}${checkOnly ? ' (check only)' : ''}`);
