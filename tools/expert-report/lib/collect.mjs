
import fs from 'node:fs';
import path from 'node:path';
import { cmp, frontmatter, readJson, readJsonSafe, sha256File, skipNoise, walk } from './util.mjs';

/** Resolve the DSH runtime layout. All authoritative on-disk state lives here. */
export function resolveLayout(cfg) {
  const dshHome = cfg.dshHome || process.env.DSH_HOME || '/Users/apple/workdsh/.test-runtime/preview';
  const home = cfg.home || process.env.HOME || '/Users/apple';
  return {
    dshHome,
    home,
    profileDir: cfg.profileDir || path.join(dshHome, 'profiles', 'preview'),
    storages: path.join(dshHome, 'storages'),
    userSkills: cfg.userSkillsDir || path.join(home, '.agents', 'skills'),
    profileSkills: cfg.profileSkillsDir || path.join(dshHome, 'skills'),
  };
}

export function readProfile(layout) {
  const pkgPath = path.join(layout.profileDir, 'package.json');
  const pkg = readJson(pkgPath);
  return {
    path: layout.profileDir,
    packageJson: pkgPath,
    name: pkg.name,
    dependencies: pkg.dependencies || {},
    bundles: (pkg.dsh && pkg.dsh.profile && pkg.dsh.profile.bundles) || [],
    patchReload: pkg.dsh && pkg.dsh.profile && pkg.dsh.profile.patchReload,
  };
}

function readSkillDir(dir, source, extra) {
  const skillMd = path.join(dir, 'SKILL.md');
  if (!fs.existsSync(skillMd)) return null;
  const text = fs.readFileSync(skillMd, 'utf8');
  const fm = frontmatter(text);
  const name = (fm.meta.name || path.basename(dir)).trim();
  const files = walk(dir, dir, skipNoise).map(f => ({
    rel: f.rel,
    abs: f.abs,
    bytes: f.bytes,
    mtimeMs: f.mtimeMs,
    sha256: sha256File(f.abs),
  }));
  const ignored = walk(dir, dir).filter(f => skipNoise(f.rel, path.basename(f.abs))).map(f => f.rel);
  return {
    name,
    dir,
    source,
    pkgName: extra && extra.pkgName,
    meta: fm.meta,
    body: fm.body,
    files,
    ignored,
    totalBytes: files.reduce((a, b) => a + b.bytes, 0),
  };
}

function scanBundled(root, out) {
  let entries;
  try { entries = fs.readdirSync(root, { withFileTypes: true }); } catch { return; }
  entries.sort((a, b) => cmp(a.name, b.name));
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    if (e.name.startsWith('.')) continue;
    if (e.name.startsWith('@')) {
      for (const s of fs.readdirSync(path.join(root, e.name), { withFileTypes: true })) {
        if (s.isDirectory()) collectPkg(path.join(root, e.name, s.name), e.name + '/' + s.name, out);
      }
    } else {
      collectPkg(path.join(root, e.name), e.name, out);
    }
  }
}
function collectPkg(pkgDir, pkgName, out) {
  const skillsDir = path.join(pkgDir, 'resources', 'skills');
  if (!fs.existsSync(skillsDir)) return;
  for (const s of fs.readdirSync(skillsDir, { withFileTypes: true })) {
    if (!s.isDirectory()) continue;
    const dir = path.join(skillsDir, s.name);
    const skill = readSkillDir(dir, 'bundled', { pkgName });
    if (skill) out.push(skill);
  }
}

/**
 * Discover every skill the runtime can see, by catalog name.
 * Precedence: user root > profile root > plugin bundled (first wins, losers recorded as shadowed).
 */
export function discoverSkills(layout) {
  const found = [];
  const roots = [
    { source: 'user', dir: layout.userSkills, base: true },
    { source: 'profile', dir: layout.profileSkills, base: true },
  ];
  for (const r of roots) {
    let entries;
    try { entries = fs.readdirSync(r.dir, { withFileTypes: true }); } catch { continue; }
    entries.sort((a, b) => cmp(a.name, b.name));
    for (const e of entries) {
      if (!e.isDirectory()) continue;
      const skill = readSkillDir(path.join(r.dir, e.name), r.source, { pkgName: null });
      if (skill) found.push(skill);
    }
  }
  scanBundled(path.join(layout.profileDir, 'node_modules'), found);
  const byName = new Map();
  const shadowed = [];
  for (const s of found) {
    if (byName.has(s.name)) { shadowed.push({ name: s.name, source: s.source, dir: s.dir }); continue; }
    byName.set(s.name, s);
  }
  return { skills: [...byName.values()].sort((a, b) => cmp(a.name, b.name)), shadowed, discovered: found.length };
}

export function readExperts(layout, scopeIds) {
  const dir = path.join(layout.storages, 'workdsh_experts');
  const expertsDir = path.join(dir, 'experts');
  const revisionsDir = path.join(dir, 'revisions');
  const draftsDir = path.join(dir, 'drafts');
  const ids = fs.existsSync(expertsDir) ? fs.readdirSync(expertsDir).filter(f => f.endsWith('.json')).map(f => f.replace(/\.json$/, '')).sort() : [];
  const all = [];
  for (const id of ids) {
    const rec = readJson(path.join(expertsDir, id + '.json')).record;
    const publishedId = rec.publishedRevisionRef && rec.publishedRevisionRef.revisionId;
    let published = null;
    if (publishedId) {
      const f = path.join(revisionsDir, id + '_' + publishedId + '.json');
      if (fs.existsSync(f)) published = { file: f, ...readJson(f).record };
    }
    let draft = null;
    const draftFile = path.join(draftsDir, id + '.json');
    if (fs.existsSync(draftFile)) draft = { file: draftFile, ...readJson(draftFile).record };
    const def = published && published.definition ? published.definition : (draft ? draft.definition : null);
    all.push({
      id,
      origin: rec.origin,
      availability: rec.availability,
      revision: rec.revision,
      draftRevision: rec.draftRevision,
      publishedRevisionId: publishedId || null,
      publishedAt: published ? published.publishedAt : null,
      definitionDigest: published ? published.definitionDigest : null,
      dependencyLockDigest: published ? published.dependencyLockDigest : null,
      compilerVersion: published ? published.compilerVersion : null,
      compositionDigest: published ? published.compositionDigest : null,
      publishedFile: published ? published.file : null,
      draftFile: draft ? draft.file : null,
      name: def ? def.name : id,
      description: def ? def.description : '',
      definition: def,
      publishedDefinition: published && published.definition ? published.definition : null,
      draftDefinition: draft ? draft.definition : null,
      inScope: scopeIds.indexOf(id) >= 0,
      updatedAt: rec.updatedAt,
    });
  }
  return all;
}

export function readProjects(layout) {
  const root = path.join(layout.storages, 'workdsh_projects', 'states');
  const files = fs.existsSync(root) ? fs.readdirSync(root).filter(f => f.endsWith('.json')).sort() : [];
  const sets = [];
  for (const f of files) {
    const abs = path.join(root, f);
    const j = readJsonSafe(abs);
    if (!j || !j.record) continue;
    const rec = j.record;
    const configs = Object.values(rec.configs || {});
    const latest = {};
    for (const c of configs) {
      const k = c.projectId;
      if (!latest[k] || latest[k].number < c.number) latest[k] = c;
    }
    sets.push({
      file: abs,
      principal: f.replace(/\.json$/, ''),
      projects: Object.values(rec.projects || {}),
      configs,
      latestConfigs: Object.values(latest).sort((a, b) => cmp(a.projectId, b.projectId)),
      tasks: Object.values(rec.tasks || {}),
      workItems: Object.values(rec.workItems || {}),
      assets: Object.values(rec.assets || {}),
      activityCount: Object.keys(rec.activity || {}).length,
    });
  }
  return sets;
}

function redactUrl(u) {
  if (!u) return u;
  return String(u).replace(/\/\/[^/@]+@/, '//***:***@');
}

export function readConnectors(layout) {
  const dir = path.join(layout.storages, 'workdsh_connectors', 'definitions');
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter(f => f.endsWith('.json')).sort().map(f => {
    const rec = readJson(path.join(dir, f)).record;
    return {
      id: rec.id,
      title: rec.title || rec.id,
      description: rec.description || '',
      serverName: rec.serverName || rec.id,
      transport: rec.transport,
      url: redactUrl(rec.url),
      command: rec.command || null,
      args: rec.args || [],
      envKeys: Object.keys(rec.env || {}),
      enabled: rec.enabled,
      file: path.join(dir, f),
      createdAt: rec.createdAt || null,
    };
  });
}

export function readPlugins(layout, profile, alwaysInclude) {
  const always = alwaysInclude || [];
  const out = [];
  const seen = new Set();
  const add = name => {
    if (seen.has(name)) return;
    seen.add(name);
    const dir = path.join(layout.profileDir, 'node_modules', name);
    let version = null;
    try { version = readJson(path.join(dir, 'package.json')).version; } catch { version = null; }
    const skillsDir = path.join(dir, 'resources', 'skills');
    const bundled = fs.existsSync(skillsDir)
      ? fs.readdirSync(skillsDir, { withFileTypes: true }).filter(e => e.isDirectory()).map(e => {
          const f = path.join(skillsDir, e.name, 'SKILL.md');
          if (!fs.existsSync(f)) return e.name;
          const fm = frontmatter(fs.readFileSync(f, 'utf8'));
          return (fm.meta.name || e.name).trim();
        }).sort()
      : [];
    const kind = name.startsWith('@deepseek-ai/') ? 'official' : name.startsWith('workdsh-') ? 'workdsh' : 'third-party';
    out.push({ name, version, kind, installed: fs.existsSync(dir), bundledSkills: bundled, inBundles: (profile.bundles || []).indexOf(name) >= 0 });
  };
  for (const b of profile.bundles || []) add(b);
  for (const d of Object.keys(profile.dependencies || {})) add(d);
  for (const a of always) if (fs.existsSync(path.join(layout.profileDir, 'node_modules', a))) add(a);
  return out.sort((a, b) => cmp(a.name, b.name));
}

/**
 * The third-party dsh-mcp-connector keeps its own registry (storages/mcp_connector.json).
 * It is a DIFFERENT management surface from workdsh_connectors/definitions.
 * Never copy this file: it can contain accessToken / refreshToken / env values.
 */
export function readMcpRegistry(layout) {
  const file = path.join(layout.storages, 'mcp_connector.json');
  if (!fs.existsSync(file)) return null;
  const j = readJson(file);
  const tables = j.tables || {};
  const conns = Object.values(tables.connections || {});
  const tools = tables.tool_catalog || {};
  const toolCatalog = {};
  for (const row of Object.values(tools)) {
    const key = row.serverName || row.serverKey;
    toolCatalog[key] = (row.tools || []).map(t => t.name || t).sort();
  }
  return {
    file,
    sha256: sha256File(file),
    unit: j.unit || null,
    connections: conns.map(c => ({
      key: c.key,
      connectorId: c.connectorId,
      name: c.name,
      transport: c.transport,
      serverName: c.serverName,
      enabled: c.enabled,
      envKeys: Object.keys(c.env || {}),
      headerKeys: Object.keys(c.headers || {}),
    })).sort((a, b) => cmp(a.key, b.key)),
    grantsCount: Object.keys(tables.grants || {}).length,
    snapshotCount: Object.keys(tables.snapshots || {}).length,
    toolCatalog,
  };
}

export function readRuntime(layout, runtimePath) {
  if (!runtimePath || !fs.existsSync(runtimePath)) return null;
  const j = readJson(runtimePath);
  const experts = {};
  for (const e of j.experts || []) {
    experts[e.id] = { readiness: e.readiness, revision: e.revision, draftRevision: e.draftRevision, issues: e.issues || [] };
  }
  const lib = (j.skillLibrary || []).slice().sort((a, b) => cmp(a.name, b.name));
  return {
    file: runtimePath,
    sha256: sha256File(runtimePath),
    generatedAt: j.generatedAt || null,
    sessionServers: j.sessionServers || [],
    sessionServersNote: j.sessionServersNote || '',
    experts,
    skillLibrary: lib,
    connectors: (j.connectors || []).slice().sort((a, b) => cmp(a.serverName || a.id || '', b.serverName || b.id || '')),
    connectorTools: j.connectorTools || {},
    note: j.note || '',
  };
}
