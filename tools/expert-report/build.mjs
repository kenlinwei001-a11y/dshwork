
/**
 * WorkDSH 专家资料包构建器（根因方案）
 *
 * 设计原则：
 * 1. 单一数据来源：所有事实从本机权威存储读取，不依赖上一次的产物。
 * 2. 可重复：同样的源状态 => 同样的文档、同样的 ZIP 字节（时间基准取源文件最新 mtime）。
 * 3. 可校验：每个源单元、每个源文件、每个产物、每个副本都有 SHA-256，副本逐字节复算。
 * 4. 可发现漂移：--check 对比清单，明确列出新增 / 变更 / 删除。
 * 5. 不泄露凭据：env 只留键名、URL 去 userinfo、产物再扫一遍密钥特征。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { buildZip } from './lib/zip.mjs';
import { cmp, code, ensureDir, fence, human, iso, readJson, readJsonSafe, rmrf, sha256, sha256File, table } from './lib/util.mjs';
import { discoverSkills, readConnectors, readExperts, readMcpRegistry, readPlugins, readProfile, readProjects, readRuntime, resolveLayout } from './lib/collect.mjs';
import { render, renderChecksDoc } from './lib/render.mjs';

const HERE = path.dirname(new URL(import.meta.url).pathname);
const STATE_DIR = path.join(HERE, '.state');
const STATE_FILE = path.join(STATE_DIR, 'manifest.json');
const DEFAULT_CONFIG = path.join(HERE, 'config.json');

function parseArgs(argv) {
  const out = { check: false, selfCheck: false, zip: true, config: DEFAULT_CONFIG, allExperts: false };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--check') out.check = true;
    else if (a === '--self-check') out.selfCheck = true;
    else if (a === '--no-zip') out.zip = false;
    else if (a === '--all-experts') out.allExperts = true;
    else if (a === '--config') out.config = path.resolve(argv[++i]);
    else if (a === '--help' || a === '-h') out.help = true;
    else throw new Error('未知参数: ' + a);
  }
  return out;
}

function digestFiles(files) {
  return sha256(Buffer.from(files.map(f => f.rel + ':' + f.sha256).sort(cmp).join('\n'), 'utf8'));
}

function readAllExpertIds(layout) {
  const dir = path.join(layout.storages, 'workdsh_experts', 'experts');
  return fs.readdirSync(dir).filter(f => f.endsWith('.json')).map(f => f.replace(/\.json$/, '')).sort();
}

function collectAll(cfg, opts) {
  const layout = resolveLayout(cfg);
  const profile = readProfile(layout);
  const skills = discoverSkills(layout);
  const scopeIds = opts.allExperts ? readAllExpertIds(layout) : cfg.scope.experts;
  const experts = readExperts(layout, scopeIds);
  if (!opts.allExperts) {
    const order = new Map(scopeIds.map((id, i) => [id, i]));
    const scoped = experts.filter(e => e.inScope).sort((a, b) => (order.get(a.id) ?? 99) - (order.get(b.id) ?? 99));
    experts.length = 0;
    experts.push(...scoped, ...readExperts(layout, scopeIds).filter(e => !e.inScope));
  }
  const projects = readProjects(layout);
  const connectors = readConnectors(layout);
  const plugins = readPlugins(layout, profile, (cfg.plugins && cfg.plugins.officialDetail) || []);
  const runtimePath = cfg.runtimeSnapshot ? path.resolve(HERE, cfg.runtimeSnapshot) : path.join(HERE, 'sources', 'runtime.json');
  const runtime = readRuntime(layout, runtimePath);
  const mcpRegistry = readMcpRegistry(layout);

  const units = [];
  for (const s of skills.skills) {
    units.push({
      kind: 'skill:' + s.source,
      path: s.dir,
      bytes: s.files.reduce((a, b) => a + b.bytes, 0),
      sha256: digestFiles(s.files),
      detail: s.files.length + ' files',
    });
  }
  for (const e of experts) {
    if (!e.inScope) continue;
    for (const f of [path.join(layout.storages, 'workdsh_experts', 'experts', e.id + '.json'), e.publishedFile, e.draftFile]) {
      if (!f || !fs.existsSync(f)) continue;
      units.push({ kind: 'expert', path: f, bytes: fs.statSync(f).size, sha256: sha256File(f), detail: path.basename(f) });
    }
  }
  for (const st of projects) units.push({ kind: 'project', path: st.file, bytes: fs.statSync(st.file).size, sha256: sha256File(st.file), detail: st.principal });
  for (const c of connectors) units.push({ kind: 'connector', path: c.file, bytes: fs.statSync(c.file).size, sha256: sha256File(c.file), detail: c.serverName });
  const pkgFile = path.join(layout.profileDir, 'package.json');
  units.push({ kind: 'profile', path: pkgFile, bytes: fs.statSync(pkgFile).size, sha256: sha256File(pkgFile), detail: 'profile composition' });
  for (const p of plugins) {
    const f = path.join(layout.profileDir, 'node_modules', p.name, 'package.json');
    if (!fs.existsSync(f)) continue;
    units.push({ kind: 'plugin', path: f, bytes: fs.statSync(f).size, sha256: sha256File(f), detail: p.name });
  }
  if (runtime) units.push({ kind: 'runtime', path: runtime.file, bytes: fs.statSync(runtime.file).size, sha256: runtime.sha256, detail: 'generatedAt=' + runtime.generatedAt });
  // hashed but never copied: it can contain accessToken / refreshToken / env values
  if (mcpRegistry) units.push({ kind: 'mcp-registry', path: mcpRegistry.file, bytes: fs.statSync(mcpRegistry.file).size, sha256: mcpRegistry.sha256, detail: mcpRegistry.connections.length + ' connections (not copied: secrets)' });

  const files = [];
  for (const s of skills.skills) for (const f of s.files) files.push({ kind: 'skill:' + s.source, path: f.abs, bytes: f.bytes, sha256: f.sha256 });
  for (const u of units) files.push({ kind: u.kind, path: u.path, bytes: u.bytes, sha256: u.sha256 });

  const sourceEpoch = Math.max(...units.map(u => fs.statSync(u.path).mtimeMs), Date.UTC(2020, 0, 1));
  const epoch = Math.floor(sourceEpoch / 1000) * 1000;
  const epochIso = iso(epoch);
  const runAt = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
  return {
    layout, profile, skills, experts, projects, connectors, mcpRegistry, plugins, runtime,
    manifestSources: units,
    manifestFiles: files,
    meta: {
      // deterministic content timestamp: same sources => same bytes (see --self-check)
      builtAt: epochIso,
      builtAtIso: epochIso,
      sourceEpoch: epoch,
      sourceEpochIso: epochIso,
      runAt,
      nodeVersion: process.version,
      platform: process.platform + ' ' + os.release(),
    },
    cfg,
  };
}

function verify(sources) {
  const items = [];
  const add = (name, ok, detail) => items.push({ name, ok, detail: detail || '' });
  const { skills, experts, projects, runtime } = sources;
  const scoped = experts.filter(e => e.inScope);
  const warnings = [];

  const noName = skills.skills.filter(s => !s.meta.name).map(s => path.basename(s.dir));
  add('技能目录均含可解析的 SKILL.md', noName.length === 0,
    noName.length ? '无法解析 name：' + noName.join('、') : skills.skills.length + ' 个技能全部解析成功');
  const dup = skills.skills.map(s => s.name).filter((n, i, arr) => arr.indexOf(n) !== i);
  add('技能名称唯一', dup.length === 0, dup.length ? '重复：' + dup.join('、') : '无重复');
  if (runtime) {
    const libNames = runtime.skillLibrary.map(x => x.name).sort(cmp);
    const diskNames = skills.skills.map(x => x.name).sort(cmp);
    const missingOnDisk = libNames.filter(n => diskNames.indexOf(n) < 0);
    const missingInLib = diskNames.filter(n => libNames.indexOf(n) < 0);
    add('技能库（运行时）与磁盘一致', missingOnDisk.length === 0 && missingInLib.length === 0,
      '库 ' + libNames.length + ' / 磁盘 ' + diskNames.length +
      (missingOnDisk.length ? '；库有磁盘无：' + missingOnDisk.join('、') : '') +
      (missingInLib.length ? '；磁盘有库无：' + missingInLib.join('、') : ''));
  } else {
    add('技能库一致性', false, '未提供运行时快照，无法比对（磁盘事实不受影响）');
  }
  add('范围内专家均已发布', scoped.length > 0 && scoped.every(e => !!e.publishedRevisionId),
    scoped.map(e => e.name + '=' + (e.publishedRevisionId || '未发布')).join('；') || '无范围内专家');
  const unresolved = [];
  for (const e of scoped) for (const r of ((e.definition || {}).skillRequirements || [])) {
    if (!skills.skills.some(s => s.name === r.name)) unresolved.push(e.name + '→' + r.name);
  }
  add('专家技能依赖全部可解析', unresolved.length === 0, unresolved.length ? '缺失：' + unresolved.join('、') : '全部命中本机技能库');
  const projUnresolved = [];
  const danglingConnectors = [];
  for (const st of projects) for (const c of st.latestConfigs) for (const cap of (c.capabilities || [])) {
    if (cap.kind === 'skill' && !skills.skills.some(s => s.name === cap.id)) projUnresolved.push('skill:' + cap.id);
    if (cap.kind === 'expert' && !experts.some(e => e.id === cap.id)) projUnresolved.push('expert:' + cap.id);
    if (cap.kind === 'connector' && !sources.connectors.some(cn => cn.id === cap.id || cn.serverName === cap.id) &&
        !(sources.mcpRegistry && sources.mcpRegistry.connections.some(cn => cn.key === cap.id || cn.serverName === cap.id || cn.connectorId === cap.id))) {
      danglingConnectors.push(cap.id);
    }
  }
  add('项目中的专家/技能引用可解析', projUnresolved.length === 0, projUnresolved.length ? '未找到：' + [...new Set(projUnresolved)].join('、') : '专家与技能引用均命中');
  if (danglingConnectors.length) warnings.unshift({
    name: '项目引用了不存在的连接器',
    detail: '项目能力快照中的 connector 引用未在两套 MCP 管理面找到：' + [...new Set(danglingConnectors)].join('、') + '（该任务可能缺少对应工具，需在项目配置里改选或补建连接）',
  });
  add('副本忽略规则只作用于备份文件', skills.skills.every(s => s.files.every(f => s.ignored.every(i => i !== f.rel))), '只忽略 .bak / SKILL.md.bak* / .DS_Store');

  const sessionServers = (runtime && runtime.sessionServers) || [];
  const diskNames = sources.connectors.map(c => c.serverName || c.id).sort(cmp);
  const regNames = (sources.mcpRegistry ? sources.mcpRegistry.connections : []).map(c => c.serverName || c.key).sort(cmp);
  if (runtime) {
    const onlySession = sessionServers.filter(n => diskNames.indexOf(n) < 0 && regNames.indexOf(n) < 0);
    const onlyDisk = diskNames.filter(n => sessionServers.indexOf(n) < 0);
    const onlyReg = regNames.filter(n => sessionServers.indexOf(n) < 0 && diskNames.indexOf(n) < 0);
    if (onlySession.length || onlyDisk.length || onlyReg.length) {
      warnings.push({
        name: '三套 MCP 视图不一致',
        detail: '会话可见 ' + sessionServers.length + ' / WorkDSH 定义 ' + diskNames.length + ' / 第三方注册表 ' + regNames.length +
          (onlyDisk.length ? '；仅 WorkDSH 定义有：' + onlyDisk.join('、') : '') +
          (onlyReg.length ? '；仅注册表有：' + onlyReg.join('、') : '') +
          (onlySession.length ? '；仅会话可见：' + onlySession.join('、') : ''),
      });
    }
    warnings.push({ name: '运行时快照是某个时刻的观测', detail: '快照时间 ' + (runtime.generatedAt || '未记录') + '；磁盘重建不会刷新健康状态与工具清单，需要重新采集 sources/runtime.json。' });
  } else {
    warnings.push({ name: '未提供运行时快照', detail: '健康状态、工具清单、技能库 state 标为未采集；磁盘事实不受影响。' });
  }
  const ignoredTotal = skills.skills.reduce((a, s) => a + s.ignored.length, 0);
  if (ignoredTotal) warnings.push({ name: '技能目录存在备份文件', detail: ignoredTotal + ' 个 .bak / SKILL.md.bak* 文件被排除在副本外（源码未被修改）。' });
  if (skills.shadowed.length) warnings.push({ name: '存在被遮蔽的同名技能', detail: skills.shadowed.map(s => s.name + '(' + s.source + ')').join('、') });

  return { ok: items.every(i => i.ok), items, warnings };
}

function writeTree(outRoot, files) {
  for (const [rel, content] of files) {
    const p = path.join(outRoot, rel);
    ensureDir(path.dirname(p));
    fs.writeFileSync(p, content);
  }
}

function copyOriginals(sources, outRoot) {
  const { skills, experts, layout, runtime } = sources;
  const copied = [];
  const push = (source, rel) => {
    const target = path.join(outRoot, rel);
    ensureDir(path.dirname(target));
    fs.copyFileSync(source, target);
    copied.push({ target, source, sha256: sha256File(source), rel });
  };
  for (const s of skills.skills) for (const f of s.files) push(f.abs, path.join('99-原件', 'skills', s.name, f.rel));
  for (const e of experts) {
    if (!e.inScope) continue;
    // keep the source subdirectory (experts/ drafts/ revisions/) so identical basenames never collide
    const list = [
      [path.join(layout.storages, 'workdsh_experts', 'experts', e.id + '.json'), 'experts'],
      [e.publishedFile, 'revisions'],
      [e.draftFile, 'drafts'],
    ];
    for (const pair of list) {
      const src = pair[0];
      if (!src || !fs.existsSync(src)) continue;
      push(src, path.join('99-原件', '专家定义', e.name + '（' + e.id + '）', pair[1], path.basename(src)));
    }
  }
  for (const st of sources.projects) push(st.file, path.join('99-原件', '项目', st.principal + '.json'));
  for (const c of sources.connectors) push(c.file, path.join('99-原件', 'MCP定义', c.serverName + '.json'));
  if (runtime) push(runtime.file, path.join('99-原件', '数据', 'runtime-snapshot.json'));
  return copied;
}

function verifyCopies(copied) {
  const bad = copied.filter(c => sha256File(c.target) !== c.sha256);
  return { ok: bad.length === 0, count: copied.length, bad: bad.map(b => b.rel) };
}

function secretScan(files) {
  const patterns = [/sk-[A-Za-z0-9_-]{20,}/, /(?:api[_-]?key|secret|password)\s*[:=]\s*["']?[A-Za-z0-9._-]{16,}/i, /Bearer\s+[A-Za-z0-9._-]{20,}/];
  const hits = [];
  for (const [rel, content] of files) {
    for (const p of patterns) if (p.test(content)) { hits.push(rel + ' 命中 ' + String(p)); break; }
  }
  return hits;
}

function renderManifest(sources, cfg, checks, docs, copies, docsHash) {
  const scoped = sources.experts.filter(e => e.inScope);
  return {
    builder: 'tools/expert-report/build.mjs',
    schemaVersion: 2,
    builtAt: sources.meta.builtAt,
    sourceEpoch: sources.meta.sourceEpochIso,
    scope: { experts: scoped.map(e => ({ id: e.id, name: e.name, publishedRevisionId: e.publishedRevisionId })) },
    counts: {
      expertsTotal: sources.experts.length,
      expertsScoped: scoped.length,
      skills: sources.skills.skills.length,
      // +1: the manifest file itself is written after rendering
      docs: docs.size + 1,
      copiedFiles: copies.length,
      connectors: sources.connectors.length,
      plugins: sources.plugins.length,
      projects: sources.projects.reduce((a, s) => a + s.projects.length, 0),
    },
    sourceUnits: sources.manifestSources.length,
    sourceFiles: sources.manifestFiles.length,
    runtimeSnapshot: sources.runtime ? { file: 'sources/runtime.json', sha256: sources.runtime.sha256, generatedAt: sources.runtime.generatedAt } : null,
    checks: { ok: checks.ok, items: checks.items, warnings: checks.warnings || [] },
    docsSha256: docsHash,
    sources: sources.manifestSources.map(u => ({ kind: u.kind, path: u.path, bytes: u.bytes, sha256: u.sha256, detail: u.detail })),
    copies: copies.map(c => ({ path: c.rel, sha256: c.sha256 })),
  };
}

function buildPackage(sources, cfg, opts) {
  const outRoot = opts.outRoot;
  const zipName = (cfg.output && cfg.output.zipName) || (path.basename(outRoot) + '.zip');
  const zipRoot = (cfg.output && cfg.output.zipRoot) || path.basename(outRoot);
  rmrf(outRoot);
  ensureDir(outRoot);

  const copies = copyOriginals(sources, outRoot);
  const copyCheck = verifyCopies(copies);

  const checks = verify(sources);
  const prev = readJsonSafe(opts.prevManifestPath || STATE_FILE);
  const docs = render(sources, cfg, checks, prev && prev.schemaVersion === 2 ? prev : null);

  checks.items.push({
    name: '原件副本逐字节一致',
    ok: copyCheck.ok,
    detail: copyCheck.count + ' 个文件复算 SHA-256' + (copyCheck.bad.length ? '；不一致：' + copyCheck.bad.slice(0, 5).join('、') : ''),
  });
  const secretHits = secretScan(docs);
  checks.items.push({
    name: '产物无密钥特征',
    ok: secretHits.length === 0,
    detail: secretHits.length ? secretHits.slice(0, 5).join('；') : '未命中（sk-* / Bearer / api_key 等模式）',
  });
  const allOk = checks.items.every(i => i.ok);
  checks.ok = allOk;

  docs.set('99-原件/README.md', renderOriginalsReadme(sources, cfg));
  docs.set('REBUILD.md', renderRebuild(sources, cfg, { docsCount: docs.size + 1, copyCount: copies.length }));
  docs.set('07-核对/01-校验结果.md', renderChecksDoc({ ok: allOk, items: checks.items, warnings: checks.warnings || [] }, sources.meta.builtAt));

  const manifestRel = '07-核对/03-构建清单.json';
  const docsHash = sha256(Buffer.from([...docs.keys()].sort(cmp).map(k => k + ':' + sha256(Buffer.from(docs.get(k), 'utf8'))).join('\n'), 'utf8'));
  const manifest = renderManifest(sources, cfg, { ok: allOk, items: checks.items, warnings: checks.warnings || [] }, docs, copies, docsHash);
  manifest.excludes = [manifestRel];
  docs.set(manifestRel, JSON.stringify(manifest, null, 2) + '\n');

  writeTree(outRoot, docs);

  let zip = null;
  if (opts.zip) {
    const entries = [];
    for (const [rel, content] of docs) entries.push({ name: zipRoot + '/' + rel, data: Buffer.from(content, 'utf8') });
    for (const c of copies) entries.push({ name: zipRoot + '/' + c.rel, data: fs.readFileSync(c.target) });
    const built = buildZip(entries, sources.meta.sourceEpoch);
    const zipPath = opts.zipPath || path.join(path.dirname(outRoot), zipName);
    fs.writeFileSync(zipPath, built.buffer);
    zip = { path: zipPath, sha256: sha256(built.buffer), bytes: built.buffer.length, entries: built.count };
  }
  return { outRoot, docs, copies, checks: { ok: allOk, items: checks.items }, manifest, zip };
}

function renderRebuild(sources, cfg, opts) {
  const lines = [];
  lines.push('# 重建说明');
  lines.push('');
  lines.push('本资料包由构建器生成，**不要手工修改**（下次构建会覆盖）。要更新内容：改数据源或配置后重建。');
  lines.push('');
  lines.push('## 1. 两种重建模式');
  lines.push('');
  lines.push('纯磁盘重建（无需会话工具，随时可跑）：');
  lines.push('');
  lines.push(fence('node tools/expert-report/build.mjs', 'bash'));
  lines.push('');
  lines.push('带运行时观测重建（健康状态、工具清单、技能库启用状态更准）：先刷新 ' + code('tools/expert-report/sources/runtime.json') + '，再执行上面的命令。');
  lines.push('');
  lines.push('## 2. 判断是否过期');
  lines.push('');
  lines.push(fence('node tools/expert-report/build.mjs --check', 'bash'));
  lines.push('');
  lines.push('逐项比对本机数据与构建清单：输出"未变化"说明包是最新的；否则列出新增 / 变更 / 删除的源。退出码 0=最新，1=已过期，2=没有历史清单。');
  lines.push('');
  lines.push('## 3. 验证幂等性');
  lines.push('');
  lines.push(fence('node tools/expert-report/build.mjs --self-check', 'bash'));
  lines.push('');
  lines.push('连续构建两次到临时目录，比较全部文档与 ZIP 字节是否完全一致。');
  lines.push('');
  lines.push('## 4. 本次构建');
  lines.push('');
  lines.push(table(['项', '值'], [
    ['构建时间（UTC）', sources.meta.builtAt],
    ['源时间基准（ZIP 时间戳）', sources.meta.sourceEpochIso],
    ['范围内专家', sources.experts.filter(e => e.inScope).map(e => e.name).join('、')],
    ['技能库收录', sources.skills.skills.length + ' 个（全量，不按专家裁剪）'],
    ['源单元 / 源文件', sources.manifestSources.length + ' / ' + sources.manifestFiles.length],
    ['运行时快照', sources.runtime ? (sources.runtime.generatedAt || '有，但未记录时间') : '无（相关字段标为未采集）'],
    ['产物文档 / 副本', opts.docsCount + ' / ' + opts.copyCount],
  ]));
  lines.push('');
  lines.push('## 5. 为什么这样设计');
  lines.push('');
  lines.push('- **全量而非裁剪**：技能按运行时可见集合收录，杜绝"库里有、包里没有"。');
  lines.push('- **不变量化**：文档直接从存储读取，不做二次人工整理，杜绝"文档与事实分叉"。');
  lines.push('- **可复算**：源单元、源文件、产物、副本四级哈希。');
  lines.push('- **确定性**：ZIP 条目排序 + 固定时间基准，源不变则字节不变。');
  lines.push('');
  return lines.join('\n');
}

function renderOriginalsReadme(sources, cfg) {
  const lines = [];
  lines.push('# 99-原件（逐字节副本）');
  lines.push('');
  lines.push('本目录是源文件的**原样复制**，供离线核对与二次加工；正文未改写。');
  lines.push('');
  lines.push(table(['目录', '内容', '来源'], [
    ['skills/<name>/', sources.skills.skills.length + ' 个技能的完整目录（已排除 .bak / .DS_Store）', '用户根 / Profile 根 / 插件 resources/skills'],
    ['专家定义/', '范围内专家的记录 / 草稿 / 发布修订 JSON（保留源目录结构 experts|drafts|revisions）', 'storages/workdsh_experts'],
    ['项目/', '项目状态文件（含配置修订、任务、资产引用）', 'storages/workdsh_projects/states'],
    ['MCP定义/', '各 MCP 连接的磁盘定义（源文件本身可能含 env 值，副本保持原样，请勿外发）', 'storages/workdsh_connectors/definitions'],
    ['数据/runtime-snapshot.json', '本次构建使用的运行时快照', 'tools/expert-report/sources/runtime.json'],
  ]));
  lines.push('');
  lines.push('核对：' + code('07-核对/04-源文件哈希.csv') + ' 给出每个源文件的 SHA-256，可逐条复算。');
  lines.push('');
  if (sources.skills.shadowed.length) {
    lines.push('注意：以下同名技能被更高优先级根遮蔽，未收录运行版本：' + sources.skills.shadowed.map(s => s.name + '(' + s.source + ')').join('、'));
    lines.push('');
  }
  return lines.join('\n');
}

function checkDrift(opts) {
  const cfg = readJson(opts.config);
  const sources = collectAll(cfg, { allExperts: false });
  const prev = readJsonSafe(STATE_FILE);
  const lines = [];
  lines.push('# 漂移检查');
  lines.push('');
  lines.push('检查时间（UTC）：' + sources.meta.builtAt);
  lines.push('');
  if (!prev) {
    lines.push('没有历史构建清单，无法比较。先跑一次 ' + code('node tools/expert-report/build.mjs') + '。');
    console.log(lines.join('\n'));
    return 2;
  }
  const prevMap = new Map((prev.sources || []).map(s => [s.path, s.sha256]));
  const curMap = new Map(sources.manifestSources.map(s => [s.path, s.sha256]));
  const added = [...curMap.keys()].filter(k => !prevMap.has(k));
  const removed = [...prevMap.keys()].filter(k => !curMap.has(k));
  const changed = [...curMap.entries()].filter(([k, v]) => prevMap.has(k) && prevMap.get(k) !== v).map(([k]) => k);
  lines.push('上次内容基准：' + prev.builtAt + (prev.runAt ? '；上次运行：' + prev.runAt : ''));
  lines.push('');
  lines.push(table(['状态', '数量'], [['新增源', String(added.length)], ['已变更源', String(changed.length)], ['已删除源', String(removed.length)]]));
  lines.push('');
  for (const [title, list] of [['新增', added], ['已变更', changed], ['已删除', removed]]) {
    if (!list.length) continue;
    lines.push('## ' + title);
    lines.push('');
    for (const p of list.slice(0, 80)) lines.push('- ' + p.replace(sources.layout.dshHome, 'DSH_HOME'));
    if (list.length > 80) lines.push('- …（共 ' + list.length + ' 条）');
    lines.push('');
  }
  if (prev.runtimeSnapshot) {
    lines.push('运行时快照上次采集：' + (prev.runtimeSnapshot.generatedAt || '未记录') + '；磁盘重建不会自动刷新它。');
    lines.push('');
  }
  const drift = added.length + removed.length + changed.length;
  lines.push(drift === 0 ? '**结论：未变化，当前资料包是最新状态。**' : '**结论：已过期（' + drift + ' 处源变化），请重新构建。**');
  console.log(lines.join('\n'));
  return drift === 0 ? 0 : 1;
}

function docsDigest(docs) {
  return sha256(Buffer.from([...docs.keys()].sort(cmp).map(k => k + ':' + sha256(Buffer.from(docs.get(k), 'utf8'))).join('\n'), 'utf8'));
}

function selfCheck(opts) {
  const cfg = readJson(opts.config);
  const sources = collectAll(cfg, { allExperts: false });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'expert-report-'));
  const first = buildPackage(sources, cfg, { outRoot: path.join(tmp, 'A'), zip: true, zipPath: path.join(tmp, 'A.zip') });
  const second = buildPackage(sources, cfg, { outRoot: path.join(tmp, 'B'), zip: true, zipPath: path.join(tmp, 'B.zip') });
  const hA = sha256File(first.zip.path);
  const hB = sha256File(second.zip.path);
  const dA = docsDigest(first.docs);
  const dB = docsDigest(second.docs);
  const sameZip = hA === hB;
  const sameDocs = dA === dB;
  const sameCopies = first.copies.length === second.copies.length &&
    first.copies.every((c, i) => c.sha256 === second.copies[i].sha256);
  const ok = sameZip && sameDocs && sameCopies && first.checks.ok;
  console.log(table(['项', '结果'], [
    ['第一次 ZIP sha256', hA],
    ['第二次 ZIP sha256', hB],
    ['ZIP 字节一致', sameZip ? '是' : 'NO'],
    ['文档内容一致', sameDocs ? '是（' + dA.slice(0, 16) + '）' : 'NO'],
    ['副本集合一致', sameCopies ? '是（' + first.copies.length + ' 个）' : 'NO'],
    ['校验通过', first.checks.ok ? '是' : '否'],
    ['结论', ok ? '幂等：源不变则产物完全相同' : '**不可重复**'],
  ]));
  rmrf(tmp);
  return ok ? 0 : 1;
}

function main() {
  const opts = parseArgs(process.argv);
  if (opts.help) {
    console.log('用法: node build.mjs [--check] [--self-check] [--all-experts] [--no-zip] [--config <path>]');
    return 0;
  }
  if (opts.check) return checkDrift(opts);
  if (opts.selfCheck) return selfCheck(opts);

  const cfg = readJson(opts.config);
  const sources = collectAll(cfg, { allExperts: opts.allExperts });
  const outRoot = path.resolve(path.dirname(opts.config), '..', '..', cfg.output.dir);
  const result = buildPackage(sources, cfg, { outRoot, zip: opts.zip, prevManifestPath: STATE_FILE });

  ensureDir(STATE_DIR);
  fs.writeFileSync(STATE_FILE, JSON.stringify({
    builtAt: sources.meta.builtAt,
    runAt: sources.meta.runAt,
    schemaVersion: 2,
    sources: result.manifest.sources,
    runtimeSnapshot: result.manifest.runtimeSnapshot,
    counts: result.manifest.counts,
  }, null, 2) + '\n');

  console.log(table(['项', '值'], [
    ['内容基准', sources.meta.sourceEpochIso + '（源文件最新 mtime，决定 ZIP 字节）'],
    ['本次运行', sources.meta.runAt],
    ['输出目录', path.relative(process.cwd(), outRoot)],
    ['文档', String(result.docs.size)],
    ['原件副本', String(result.copies.length)],
    ['校验', result.checks.ok ? 'PASS（' + result.checks.items.length + ' 项）' : 'FAIL'],
    ['ZIP', result.zip ? path.basename(result.zip.path) + '  ' + human(result.zip.bytes) + '  sha256=' + result.zip.sha256.slice(0, 16) : '（未生成）'],
  ]));
  for (const c of result.checks.items) if (!c.ok) console.log('  FAIL  ' + c.name + ' — ' + c.detail);
  return result.checks.ok ? 0 : 1;
}

process.exitCode = main();
