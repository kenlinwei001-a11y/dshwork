
import fs from 'node:fs';
import path from 'node:path';
import { cmp, code, fence, frontmatter, human, iso, redactSecrets, table } from './util.mjs';

const pad = n => String(n).padStart(2, '0');

function offEquipped(skillName, experts) {
  return experts.filter(e => e.inScope && (e.definition && (e.definition.skillRequirements || []).some(r => r.name === skillName)));
}
function allEquipped(skillName, experts) {
  return experts.filter(e => e.definition && (e.definition.skillRequirements || []).some(r => r.name === skillName));
}
function mcpRefs(skill) {
  const refs = new Set();
  for (const f of skill.files) {
    if (!/\.(md|json|yaml|yml|py|txt)$/.test(f.rel)) continue;
    let txt = '';
    try { txt = fs.readFileSync(f.abs, 'utf8'); } catch { continue; }
    for (const m of txt.matchAll(/mcp__([a-z0-9-]+)__/g)) refs.add(m[1]);
    for (const m of txt.matchAll(/\bkp_[a-z_]+/g)) refs.add('kp_toolkit');
  }
  return [...refs].sort();
}

export function render(sources, cfg, checks, prev) {
  const out = new Map();
  const put = (rel, content) => out.set(rel, redactSecrets(content));
  const { profile, skills, experts, projects, connectors, plugins, runtime, layout, meta } = sources;
  const scoped = experts.filter(e => e.inScope);
  const others = experts.filter(e => !e.inScope);
  const stamp = meta.builtAtIso;
  const H = (extra) => '> 本文件由 ' + code('tools/expert-report/build.mjs') + ' 从本机权威数据源自动构建，内容基准时间（UTC）：' + stamp + '（= 源文件最新 mtime；构建器实际运行时间见 .state/manifest.json）。' +
    '所有内容可凭 07-核对/ 下的清单与哈希复算；手工修改会在下次构建被覆盖。' + (extra ? ' ' + extra : '');
  const owner = sources.manifestSources.length;

  // ---------------------------------------------------------------- 00
  {
    const lines = [];
    lines.push('# 专家 · 技能 · 项目 · 插件 · MCP 完整资料包');
    lines.push('');
    lines.push(H());
    lines.push('');
    lines.push('## 1. 这份资料包怎么来的');
    lines.push('');
    lines.push('不是手工拼装，而是由本仓库的构建器从**本机权威数据源**全量生成：');
    lines.push('');
    lines.push(table(['数据', '权威来源', '校验'], [
      ['专家定义', 'storages/workdsh_experts/{experts,revisions,drafts}/*.json', '所有定义文件记录 SHA-256'],
      ['技能库', '~/.agents/skills、DSH_HOME/skills、各插件 resources/skills', '逐字节复制并复算哈希'],
      ['项目', 'storages/workdsh_projects/states/*.json', '能力快照取每项目最新配置修订'],
      ['MCP 连接', 'storages/workdsh_connectors/definitions/*.json', 'env 只记录键名，URL 去凭据'],
      ['插件与组合', 'profiles/preview/package.json + 各包 package.json', '版本取自实际安装包'],
      ['运行时观测', 'sources/runtime.json（会话工具快照）', '记录快照时间与哈希，过期会被指出'],
    ]));
    lines.push('');
    lines.push('## 2. 覆盖范围');
    lines.push('');
    lines.push('- 本次范围内的专家：' + scoped.map(e => e.name + '（' + e.id + '）').join('、') + '。');
    lines.push('- 技能库：完整收录 ' + skills.skills.length + ' 个（不按专家裁剪，避免"库里有、包里没有"的坑）。');
    lines.push('- 其他专家 ' + others.length + ' 个：列出简档，便于确认哪些没有纳入范围。');
    lines.push('- MCP 连接 ' + connectors.length + ' 条、已装插件 ' + plugins.length + ' 个、项目记录 ' + projects.reduce((a, s) => a + s.projects.length, 0) + ' 个。');
    lines.push('');
    lines.push('## 3. 目录导航');
    lines.push('');
    lines.push(table(['目录', '内容', '文件数'], [
      ['00-总介绍.md', '本文件', '1'],
      ['01-关系总览/', '五者关系、数据来源与核对方法', '2'],
      ['02-项目/', '项目总览 + 每个项目一份（指令、能力快照、任务、工作区）', String(1 + projects.reduce((a, s) => a + s.projects.length, 0))],
      ['03-专家/', '专家总览 + 范围内专家详档 + 其他专家简档', String(2 + scoped.length)],
      ['04-技能/', '技能总览 + 每个技能的正文与资源清单', String(1 + skills.skills.length)],
      ['05-插件/', '插件总览 + 每个插件一份', String(1 + plugins.length)],
      ['06-MCP/', 'MCP 总览 + 每条连接一份', String(1 + connectors.length)],
      ['07-核对/', '校验结果、变更报告、构建清单、源文件哈希', '4'],
      ['99-原件/', '技能目录与专家定义的逐字节副本', '目录树'],
      ['REBUILD.md', '如何一键重建、如何判断是否过期', '1'],
    ]));
    lines.push('');
    lines.push('## 4. 五者关系（一句话）');
    lines.push('');
    lines.push('插件是安装与供货单元；技能、专家、MCP 连接、项目是插件管理的业务对象；项目把专家＋技能＋连接器组合成一次任务的能力快照，交给 Harness 原生 Agent 执行。');
    lines.push('');
    lines.push(fence([
      'DSH Profile（bundles + cordis.patch.yml）',
      '  └─ 插件 plugin',
      '       ├─ skills 插件      → N 个技能（怎么做）',
      '       ├─ experts 插件     → N 个专家（谁来做），发布时把技能冻结成快照 + Agent preset',
      '       ├─ connectors 插件  → N 个 MCP 连接（能连什么），按会话开放 mcp__<server>__*',
      '       └─ projects 插件    → N 个项目（把三类 + 资料 + 任务组织起来）',
      '                                   ↓ 新建任务：能力快照 + 配置修订',
      '                          官方 Agent preset + MCP 工具命名空间',
    ].join('\n'), 'text'));
    lines.push('');
    lines.push('细节见 ' + code('01-关系总览/01-关系总览.md') + '。');
    lines.push('');
    lines.push('## 5. 诚实边界');
    lines.push('');
    lines.push('- 描述的是构建时刻的本机状态；会话里的实时观测来自运行时快照（时间见 ' + code('01-关系总览/02-数据来源与核对说明.md') + '）。');
    lines.push('- 专家定义没有 MCP 字段；MCP 能力来自连接器，由项目或会话选择。');
    lines.push('- 技能的 "已改动" 与 "已生效" 是两件事：已发布专家使用发布时冻结的快照，改库文件不改变已发布专家。');
    lines.push('- 包内不含任何凭据；env 只留键名，URL 去 userinfo。');
    lines.push('');
    put('00-总介绍.md', lines.join('\n'));
  }

  // ---------------------------------------------------------------- 01
  {
    const lines = [];
    lines.push('# 项目 · 专家 · 插件 · Skill · MCP 关系总览');
    lines.push('');
    lines.push(H());
    lines.push('');
    lines.push('## 1. 分层');
    lines.push('');
    lines.push(table(['层', '实体', '拥有者', '生命周期'], [
      ['安装层', '插件 plugin', 'DSH Profile（官方 Loader）', '随插件安装/卸载'],
      ['能力层', '技能 Skill', '技能根目录 / 各插件 resources/skills', '用户技能独立于插件；内置技能随插件'],
      ['角色层', '专家 / 专家团', 'experts 插件（storages/workdsh_experts）', '发布即冻结不可变修订 + Agent preset'],
      ['连接层', 'MCP 连接', 'connectors 插件（storages/workdsh_connectors）', '全局或按项目；按会话开放工具命名空间'],
      ['组织层', '项目', 'projects 插件（storages/workdsh_projects）', '只存引用 + 不可变配置修订'],
      ['执行层', '原生任务（会话）', 'Harness Agent/Session', '创建时固定能力快照'],
    ]));
    lines.push('');
    lines.push('## 2. 六条关键关系');
    lines.push('');
    lines.push('**2.1 插件 → 技能**：插件可以把自己的 skills 目录注册为 bundled 技能；用户技能是技能根下的普通目录，卸载插件不会删除。');
    lines.push('');
    lines.push('**2.2 专家 → 技能**：专家定义的 skillRequirements 在发布时冻结为受管快照并编译进 Agent preset；改技能文件不影响已发布专家。');
    lines.push('');
    lines.push('**2.3 专家 ⇄ MCP**：专家定义里没有 MCP 字段。MCP 来自连接器，由项目或会话选择。');
    lines.push('');
    lines.push('**2.4 项目 → 三者**：能力类型固定为 skill / expert / connector，只保存 kind+id+label+revision，任务创建时固定快照。');
    lines.push('');
    lines.push('**2.5 技能 → MCP**：技能正文里出现的 mcp__<server>__<tool> 才构成依赖；否则只依赖自身脚本与工作区文件。');
    lines.push('');
    lines.push('**2.6 专家团 → 官方 Team**：成员引用各专家修订，执行使用官方 spawn_teammate / team_task_*。');
    lines.push('');
    lines.push('## 3. 本机实例链路（构建时自动提取）');
    lines.push('');
    const chain = [];
    for (const e of scoped) {
      chain.push('专家「' + e.name + '」(' + e.id + ')');
      chain.push('  发布修订: ' + (e.publishedRevisionId || '未发布') + ' | 定义摘要: ' + String(e.definitionDigest || '-').slice(0, 16) + ' | 编译器: ' + (e.compilerVersion || '-'));
      const reqs = (e.definition.skillRequirements || []);
      chain.push('  技能依赖: ' + reqs.length + ' 个' + (reqs.length ? '（首个: ' + reqs[0].name + '）' : ''));
      const refs = [];
      for (const s of projects) for (const c of s.latestConfigs) {
        if ((c.capabilities || []).some(x => x.id === e.id)) {
          const caps = c.capabilities || [];
          refs.push('  项目引用: ' + ((s.projects.find(p => p.id === c.projectId) || {}).name || c.projectId) +
            ' 配置#' + c.number + ' → 技能 ' + caps.filter(x => x.kind === 'skill').length + '、连接器 ' + caps.filter(x => x.kind === 'connector').map(x => x.label).join('/') + '');
        }
      }
      chain.push(...(refs.length ? refs : ['  项目引用: 无']));
    }
    lines.push(fence(chain.join('\n'), 'text'));
    lines.push('');
    lines.push('## 4. 常见误解');
    lines.push('');
    lines.push(table(['误解', '事实'], [
      ['专家自带 MCP', '专家无 MCP 字段；连接由项目/会话选择'],
      ['技能是插件', '技能是内容单元；插件可内置，但二者不等价'],
      ['项目拥有专家与技能', '项目只有引用，正文归各领域所有'],
      ['改技能就能改专家行为', '已发布专家用冻结快照，需重新发布'],
      ['包里技能数 = 专家技能数', '本包收录完整技能库，专家只引用其中一部分'],
    ]));
    lines.push('');
    put('01-关系总览/01-关系总览.md', lines.join('\n'));

    const l2 = [];
    l2.push('# 数据来源与核对说明');
    l2.push('');
    l2.push(H());
    l2.push('');
    l2.push('## 1. 环境');
    l2.push('');
    l2.push(table(['项', '值'], [
      ['DSH_HOME', layout.dshHome],
      ['Profile', profile.path],
      ['用户技能根', layout.userSkills],
      ['Profile 技能根', layout.profileSkills],
      ['Node', meta.nodeVersion],
      ['平台', meta.platform],
      ['构建时间（UTC）', stamp],
      ['源数据时间基准 sourceEpoch', meta.sourceEpochIso],
    ]));
    l2.push('');
    l2.push('## 2. 权威数据源与哈希');
    l2.push('');
    l2.push('本次共记录 ' + owner + ' 个源文件，完整清单见 ' + code('07-核对/03-构建清单.json') + ' 与 ' + code('07-核对/04-源文件哈希.csv') + '。摘要：');
    l2.push('');
    l2.push(table(['源', '路径', 'SHA-256（前 16）', '字节'], sources.manifestSources.slice(0, 20).map(s => [s.kind, s.path.replace(layout.dshHome, 'DSH_HOME'), s.sha256.slice(0, 16), String(s.bytes)])));
    l2.push('');
    if (sources.manifestSources.length > 20) l2.push('（仅列前 20 条，完整见 CSV。）');
    l2.push('');
    l2.push('## 3. 运行时快照');
    l2.push('');
    if (runtime) {
      l2.push('- 文件：' + code('tools/expert-report/sources/runtime.json'));
      l2.push('- 快照时间：' + (runtime.generatedAt || '未记录') + '（UTC）');
      l2.push('- SHA-256：' + code(runtime.sha256));
      l2.push('- 提供：专家 readiness/revision、技能库 state/selectable、连接健康状态、各 server 工具清单。');
      l2.push('- 局限：这是"某个时刻的观测"，不是磁盘事实；过期时 ' + code('build.mjs --check') + ' 会明确列出。');
    } else {
      l2.push('- 本次构建**未提供**运行时快照：健康状态、工具清单、技能库启用状态标记为「未采集」。');
      l2.push('- 恢复方式见 ' + code('REBUILD.md') + '。');
    }
    l2.push('');
    l2.push('## 4. 复核方法');
    l2.push('');
    l2.push('1. 跑 ' + code('node tools/expert-report/build.mjs --check') + '：逐项比对本机数据与构建清单，输出"未变化/已变化"。');
    l2.push('2. 跑 ' + code('node tools/expert-report/build.mjs --self-check') + '：连续构建两次到临时目录，确认两次产物逐字节相同（幂等性证明）。');
    l2.push('3. 手工抽查：任取 ' + code('99-原件/') + ' 下文件与源文件比 SHA-256。');
    l2.push('');
    put('01-关系总览/02-数据来源与核对说明.md', l2.join('\n'));
  }

  // ---------------------------------------------------------------- 02 项目
  {
    const allProjects = projects.flatMap(s => s.projects.map(p => ({ principal: s.principal, p, state: s })));
    const lines = [];
    lines.push('# 项目总览');
    lines.push('');
    lines.push(H());
    lines.push('');
    lines.push('## 1. 机制');
    lines.push('');
    lines.push('项目只保存引用（kind+id+label+revision）与不可变配置修订；正文分别归专家、技能、资料库。任务创建时固定配置修订，运行中不被后续修改替换。');
    lines.push('');
    lines.push('## 2. 本机项目记录（' + allProjects.length + ' 个）');
    lines.push('');
    lines.push(table(['项目', '主体', '状态', '最新配置', '专家', '技能数', '连接器', '更新'], allProjects.map(({ principal, p, state }) => {
      const c = state.latestConfigs.find(x => x.projectId === p.id);
      const caps = (c && c.capabilities) || [];
      return [p.name, principal, p.status, '#' + ((c && c.number) || '-'),
        caps.filter(x => x.kind === 'expert').map(x => x.label).join('、') || '-',
        String(caps.filter(x => x.kind === 'skill').length),
        caps.filter(x => x.kind === 'connector').map(x => x.label).join('、') || '-',
        (p.updatedAt || '').slice(0, 10)];
    })));
    lines.push('');
    lines.push('## 3. 与本次范围内专家的关系');
    lines.push('');
    for (const e of scoped) {
      const hits = [];
      for (const s of projects) for (const c of s.latestConfigs) {
        if ((c.capabilities || []).some(x => x.id === e.id)) {
          hits.push('- ' + ((s.projects.find(p => p.id === c.projectId) || {}).name || c.projectId) + ' 配置#' + c.number);
        }
      }
      lines.push('- ' + e.name + '：' + (hits.length ? '被引用\n' + hits.join('\n') : '未被任何项目引用'));
    }
    lines.push('');
    put('02-项目/00-项目总览.md', lines.join('\n'));

    allProjects.forEach(({ principal, p, state }, i) => {
      const c = state.latestConfigs.find(x => x.projectId === p.id);
      const caps = (c && c.capabilities) || [];
      const tasks = state.tasks.filter(t => t.projectId === p.id);
      const wis = state.workItems.filter(x => x.projectId === p.id);
      const assets = state.assets.filter(a => a.projectId === p.id);
      const l = [];
      l.push('# 项目：' + p.name);
      l.push('');
      l.push(H());
      l.push('');
      l.push('## 1. 基本信息');
      l.push('');
      l.push(table(['字段', '值'], [
        ['项目 ID', p.id], ['名称', p.name], ['描述', p.description || '（空）'], ['模板', p.templateId || '（无）'],
        ['状态', p.status], ['主体', principal],
        ['归属', p.owner ? p.owner.organizationId + ' / ' + p.owner.ownerPrincipalId + ' / ' + p.owner.scope : '-'],
        ['创建时间', p.createdAt], ['更新时间', p.updatedAt],
        ['最新配置修订', '#' + ((c && c.number) || '-') + '（' + ((c && c.id) || '-') + '）'],
      ]));
      l.push('');
      l.push('## 2. 项目指令（最新修订全文）');
      l.push('');
      l.push(c && c.instruction && c.instruction.trim() ? fence(c.instruction, 'text') : '（该修订未设置指令）');
      l.push('');
      l.push('## 3. 能力快照（' + caps.length + ' 项）');
      l.push('');
      l.push(caps.length ? table(['类型', 'id', '名称', 'scope', 'revision'], caps.map(x => [x.kind, x.id, x.label, x.scope || '-', x.revision || '（连接器无修订）'])) : '（无已选能力）');
      l.push('');
      if (caps.some(x => x.kind === 'expert')) {
        l.push('### 3.1 专家引用解析');
        l.push('');
        l.push(table(['专家 id', '名称', '本包文档', '解析状态'], caps.filter(x => x.kind === 'expert').map(x => {
          const e = experts.find(y => y.id === x.id);
          return [x.id, x.label, e && e.inScope ? code('03-专家/' + pad(scoped.findIndex(z => z.id === e.id) + 1) + '-' + e.name + '.md') : (e ? '见 03-专家/99-其他专家.md' : '（本机无此专家）'), e ? '已收录（' + (e.publishedRevisionId || '未发布') + '）' : '未找到'];
        })));
        l.push('');
      }
      if (caps.some(x => x.kind === 'skill')) {
        l.push('### 3.2 技能引用解析');
        l.push('');
        l.push(table(['技能 id', '名称', '本包文档'], caps.filter(x => x.kind === 'skill').map(x => {
          const idx = skills.skills.findIndex(s => s.name === x.id);
          return [x.id, x.label, idx >= 0 ? code('04-技能/' + pad(idx + 1) + '-' + x.id + '.md') : '（本机技能库中不存在）'];
        })));
        l.push('');
      }
      if (caps.some(x => x.kind === 'connector')) {
        l.push('### 3.3 连接器引用解析');
        l.push('');
        l.push(table(['连接器 id', '名称', '本机连接'], caps.filter(x => x.kind === 'connector').map(x => {
          const hit = connectors.filter(cn => cn.id === x.id || cn.serverName === x.id);
          return [x.id, x.label, hit.length ? hit.map(h => h.serverName).join('、') : '（未在本机 definitions 中找到）'];
        })));
        l.push('');
      }
      l.push('## 4. 关联任务（' + tasks.length + '）');
      l.push('');
      l.push(tasks.length ? table(['任务 id', '标题', '配置修订', '引用'], tasks.map(t => [t.id, t.title || '-', t.configRevisionId || t.configRevision || '-', (t.references || []).map(r => r.kind + ':' + (r.label || r.id)).join('；') || '-'])) : '（无）');
      l.push('');
      l.push('## 5. 工作项与资产');
      l.push('');
      l.push(wis.length ? table(['工作项', '状态', '优先级', '标签'], wis.map(x => [x.title, x.status, x.priority || '-', (x.tags || []).join('、') || '-'])) : '（无工作项）');
      l.push('');
      l.push(assets.length ? table(['资产引用', '类型', '库内 assetId'], assets.map(a => [a.label || a.id, a.kind, a.assetId])) : '（无资产引用）');
      l.push('');
      put('02-项目/' + pad(i + 1) + '-' + p.name.replace(/[\/:*?"<>|]/g, '_') + '.md', l.join('\n'));
    });
  }

  // ---------------------------------------------------------------- 03 专家
  {
    const lines = [];
    lines.push('# 专家总览');
    lines.push('');
    lines.push(H());
    lines.push('');
    lines.push('## 1. 全部专家（' + experts.length + '）');
    lines.push('');
    lines.push(table(['专家', 'id', '来源', '技能数', '发布修订', '可用性', '就绪', '更新'], experts.map(e => {
      const rt = runtime && runtime.experts[e.id];
      return [e.name, e.id, e.origin, String(((e.definition || {}).skillRequirements || []).length),
        e.publishedRevisionId || '未发布', e.availability, rt ? rt.readiness : '未采集', (e.updatedAt || '').slice(0, 10)];
    })));
    lines.push('');
    lines.push('## 2. 范围内专家');
    lines.push('');
    lines.push(scoped.map((e, i) => '- ' + code('03-专家/' + pad(i + 1) + '-' + e.name + '.md') + ' — ' + e.name + '（' + e.id + '）').join('\n'));
    lines.push('');
    lines.push('## 3. 其他专家');
    lines.push('');
    lines.push('- ' + code('03-专家/' + pad(scoped.length + 1) + '-其他专家.md') + ' — 不在本次范围，仅列简档。');
    lines.push('');
    lines.push('## 4. 发布语义');
    lines.push('');
    lines.push('专家发布时冻结：定义正文、成员修订、技能快照、Agent preset；之后修改技能库或草稿都不改变已发布专家，需要重新发布才会生成新修订。');
    lines.push('');
    put('03-专家/00-专家总览.md', lines.join('\n'));

    scoped.forEach((e, i) => {
      const def = e.publishedDefinition || e.draftDefinition || {};
      const reqs = def.skillRequirements || [];
      const rt = runtime && runtime.experts[e.id];
      const l = [];
      l.push('# 专家：' + e.name);
      l.push('');
      l.push(H());
      l.push('');
      l.push('## 1. 基本信息');
      l.push('');
      l.push(table(['字段', '值'], [
        ['专家 id', e.id], ['名称', e.name], ['来源', e.origin + '（' + (e.origin === 'personal' ? '我的专家' : e.origin) + '）'],
        ['可用性', e.availability],
        ['就绪状态（运行时）', rt ? rt.readiness : '未采集'],
        ['并发令牌 revision', e.revision],
        ['草稿 revision', e.draftRevision],
        ['发布修订', e.publishedRevisionId || '（未发布）'],
        ['发布时间', e.publishedAt || '-'],
        ['定义摘要', e.definitionDigest || '-'],
        ['依赖锁摘要', e.dependencyLockDigest || '-'],
        ['编译器版本', e.compilerVersion || '-'],
        ['组合摘要', e.compositionDigest || '-'],
        ['一句话描述', def.description || '-'],
        ['标签', (def.tags || []).join('、') || '（无）'],
        ['分类', def.categoryId || '（未设置）'],
      ]));
      l.push('');
      if (rt && rt.issues && rt.issues.length) {
        l.push('> 运行时报告的问题：' + rt.issues.join('；'));
        l.push('');
      }
      l.push('## 2. 专业定义');
      l.push('');
      for (const [k, label] of [['role', '角色定位（role）'], ['methodology', '工作方法（methodology）'], ['boundaries', '行为边界（boundaries）'], ['deliverables', '交付物（deliverables）']]) {
        l.push('### 2.' + (Object.keys({ role: 1, methodology: 1, boundaries: 1, deliverables: 1 }).indexOf(k) + 1) + ' ' + label);
        l.push('');
        l.push(def[k] || '（空）');
        l.push('');
      }
      l.push('## 3. 技能依赖（' + reqs.length + ' 个，按定义顺序）');
      l.push('');
      l.push(table(['#', '技能', '本包文档', '解析'], reqs.map((r, idx) => {
        const found = skills.skills.find(s => s.name === r.name);
        return [String(idx + 1), r.name, found ? code('04-技能/' + pad(skills.skills.indexOf(found) + 1) + '-' + r.name + '.md') : '（缺失）', found ? '已解析' : '**技能库中找不到**'];
      })));
      l.push('');
      l.push('> 依赖在发布时冻结为受管快照；当前库内同名技能的后续修改不会进入本修订。');
      l.push('');
      l.push('## 4. 能力缺口与示例');
      l.push('');
      l.push('- futureRequirements：' + (((def.futureRequirements || []).length) ? JSON.stringify(def.futureRequirements) : '空'));
      l.push('- examples：' + (((def.examples || []).length) ? JSON.stringify(def.examples) : '空'));
      l.push('- team：' + (def.team ? '已配置' : '未配置（单专家）'));
      l.push('');
      if (e.publishedDefinition && e.draftDefinition && JSON.stringify(e.publishedDefinition) !== JSON.stringify(e.draftDefinition)) {
        l.push('## 5. 草稿与已发布版本的差异');
        l.push('');
        const pub = e.publishedDefinition, drf = e.draftDefinition;
        const fields = ['name', 'description', 'role', 'methodology', 'boundaries', 'deliverables', 'agentDocument'];
        const changedFields = fields.filter(x => JSON.stringify(pub[x]) !== JSON.stringify(drf[x]));
        const pubSkills = (pub.skillRequirements || []).map(r => r.name);
        const drfSkills = (drf.skillRequirements || []).map(r => r.name);
        const added = drfSkills.filter(x => pubSkills.indexOf(x) < 0);
        const removed = pubSkills.filter(x => drfSkills.indexOf(x) < 0);
        l.push('- 变化的文本字段：' + (changedFields.length ? changedFields.join('、') : '无'));
        l.push('- 草稿新增技能：' + (added.length ? added.join('、') : '无'));
        l.push('- 草稿移除技能：' + (removed.length ? removed.join('、') : '无'));
        l.push('');
        l.push('> 草稿不影响已发布修订；要让变化生效必须在专家界面重新发布。');
        l.push('');
      }
      l.push('## 6. 完整 Agent MD（已发布冻结正文）');
      l.push('');
      l.push(fence(def.agentDocument || '（未采集）', 'markdown'));
      l.push('');
      l.push('## 7. 源文件');
      l.push('');
      l.push(table(['文件', 'SHA-256（前 16）'], [
        ['experts/' + e.id + '.json', '见 07-核对/03-构建清单.json'],
        e.publishedFile ? [path.basename(e.publishedFile), '见 07-核对/03-构建清单.json'] : ['（无发布修订）', '-'],
        e.draftFile ? [path.basename(e.draftFile), '见 07-核对/03-构建清单.json'] : ['（无草稿）', '-'],
      ]));
      l.push('');
      put('03-专家/' + pad(i + 1) + '-' + e.name + '.md', l.join('\n'));
    });

    const l = [];
    l.push('# 其他专家（不在本次范围）');
    l.push('');
    l.push(H());
    l.push('');
    l.push('列出本机其余专家，便于确认范围边界与后续扩展。');
    l.push('');
    l.push(table(['专家', 'id', '技能数', '发布修订', '更新'], others.map(e => [e.name, e.id, String(((e.definition || {}).skillRequirements || []).length), e.publishedRevisionId || '未发布', (e.updatedAt || '').slice(0, 10)])));
    l.push('');
    l.push('需要纳入时：把 id 加入 ' + code('tools/expert-report/config.json') + ' 的 ' + code('scope.experts') + ' 后重建，无需改代码。');
    l.push('');
    put('03-专家/' + pad(scoped.length + 1) + '-其他专家.md', l.join('\n'));
  }

  // ---------------------------------------------------------------- 04 技能
  {
    const s = skills.skills;
    const lines = [];
    lines.push('# 技能总览（完整技能库）');
    lines.push('');
    lines.push(H());
    lines.push('');
    lines.push('## 1. 收录原则');
    lines.push('');
    lines.push('收录本机运行时可见的**全部技能**（用户根 + Profile 根 + 插件内置），不按专家裁剪；专家的引用关系单独标注。这样库里新增/删除技能时，构建器会直接反映，不会出现"库里有、包里没有"。');
    lines.push('');
    lines.push('## 2. 总表（' + s.length + ' 个）');
    lines.push('');
    lines.push(table(['#', '技能', '来源', '范围专家配备', '全部引用', '文件数', '体积', 'MCP'], s.map((sk, i) => {
      const off = offEquipped(sk.name, experts).map(e => e.name);
      const all = allEquipped(sk.name, experts).map(e => e.name);
      const refs = mcpRefs(sk);
      return [String(i + 1), sk.name, sk.source, off.length ? off.join('、') : '-', String(all.length), String(sk.files.length), human(sk.totalBytes), refs.length ? refs.join('、') : '-'];
    })));
    lines.push('');
    const bySource = { user: 0, profile: 0, bundled: 0 };
    for (const k of s) bySource[k.source] = (bySource[k.source] || 0) + 1;
    lines.push('按来源：用户根 ' + bySource.user + '、Profile 根 ' + bySource.profile + '、插件内置 ' + bySource.bundled + '。');
    if (skills.shadowed.length) {
      lines.push('');
      lines.push('被遮蔽的同名技能（同名按 user > profile > bundled 优先，其余不参与运行）：');
      lines.push('');
      lines.push(table(['名称', '被遮蔽来源', '路径'], skills.shadowed.map(x => [x.name, x.source, x.dir])));
    }
    lines.push('');
    lines.push('## 3. 逐技能文档');
    lines.push('');
    lines.push(s.map((sk, i) => '- ' + code('04-技能/' + pad(i + 1) + '-' + sk.name + '.md') + ' — ' + sk.name).join('\n'));
    lines.push('');
    put('04-技能/00-技能总览.md', lines.join('\n'));

    s.forEach((sk, i) => {
      const off = offEquipped(sk.name, experts);
      const all = allEquipped(sk.name, experts);
      const refs = mcpRefs(sk);
      const fm = sk.meta;
      const l = [];
      l.push('# 技能：' + sk.name);
      l.push('');
      l.push(H());
      l.push('');
      l.push('## 1. 元数据');
      l.push('');
      l.push(table(['字段', '值'], Object.keys(fm).length ? Object.entries(fm) : [['—', '（SKILL.md 无 frontmatter）']]));
      l.push('');
      l.push('## 2. 位置与来源');
      l.push('');
      l.push(table(['项', '值'], [
        ['来源类型', sk.source === 'user' ? '用户/共享技能根' : sk.source === 'profile' ? 'Profile 技能根' : '插件内置（bundled）'],
        ['目录', sk.dir],
        ['所属插件', sk.pkgName || '（非插件内置）'],
        ['文件数', String(sk.files.length)],
        ['体积', human(sk.totalBytes)],
        ['被忽略文件', sk.ignored.length ? sk.ignored.join('、') + '（编辑器备份/系统文件，不进入副本）' : '无'],
      ]));
      l.push('');
      l.push('## 3. 引用关系');
      l.push('');
      l.push('- 本次范围内专家配备：' + (off.length ? off.map(e => e.name).join('、') : '**未被范围内专家配备**'));
      l.push('- 全部专家引用（含范围外）：' + (all.length ? all.map(e => e.name + '（' + e.id + '）').join('、') : '无'));
      l.push('');
      l.push('## 4. SKILL.md 正文（全文）');
      l.push('');
      l.push(fence(fs.readFileSync(path.join(sk.dir, 'SKILL.md'), 'utf8'), 'markdown'));
      l.push('');
      l.push('## 5. 资源清单');
      l.push('');
      l.push(table(['文件', '字节', 'SHA-256（前 16）'], sk.files.map(f => [f.rel, String(f.bytes), f.sha256.slice(0, 16)])));
      l.push('');
      l.push('## 6. MCP 关联（文本取证）');
      l.push('');
      l.push(refs.length ? '正文或资源中出现：' + refs.map(r => code(r)).join('、') + '。对应连接见 ' + code('06-MCP/') + '。' : '未发现 mcp__<server>__ 或 kp_ 工具引用：只依赖自身脚本与工作区文件。');
      l.push('');
      l.push('## 7. 副本');
      l.push('');
      l.push('逐字节副本：' + code('99-原件/skills/' + sk.name + '/') + '（未改写；已用 SHA-256 复算校验）。');
      l.push('');
      put('04-技能/' + pad(i + 1) + '-' + sk.name + '.md', l.join('\n'));
    });
  }

  // ---------------------------------------------------------------- 05 插件
  {
    const officialAllow = new Set((cfg.plugins && cfg.plugins.officialDetail) || []);
    const detailed = plugins.filter(p => p.kind !== 'official' || officialAllow.has(p.name) || p.bundledSkills.length > 0);
    const rest = plugins.filter(p => detailed.indexOf(p) < 0);
    const slugOf = name => name.replace(/[@\/]/g, m => (m === '@' ? '' : '__'));
    const byKind = { workdsh: [], official: [], 'third-party': [] };
    for (const p of plugins) byKind[p.kind].push(p.name);

    const lines = [];
    lines.push('# 插件总览');
    lines.push('');
    lines.push(H());
    lines.push('');
    lines.push('插件是安装与供货单元：官方 Loader 按 Profile 组合加载，注册 Host 服务与界面，并可携带内置技能。');
    lines.push('');
    lines.push('## 1. Profile');
    lines.push('');
    lines.push(table(['项', '值'], [
      ['Profile', profile.path],
      ['包名', profile.name],
      ['bundles 数量', String((profile.bundles || []).length)],
      ['patchReload', String(profile.patchReload)],
      ['已解析包数', String(plugins.length)],
    ]));
    lines.push('');
    lines.push('按类型：WorkDSH ' + byKind.workdsh.length + '、官方 ' + byKind.official.length + '、第三方 ' + byKind['third-party'].length + '。');
    lines.push('');
    lines.push('## 2. bundles 启用顺序');
    lines.push('');
    lines.push(fence((profile.bundles || []).join('\n'), 'text'));
    lines.push('');
    lines.push('## 3. 已装插件（' + plugins.length + '）');
    lines.push('');
    lines.push(table(['插件', '版本', '类型', '在 bundles', '内置技能', '单独成文'], plugins.map(p => [
      p.name, p.version || '（未知）', p.kind, p.inBundles ? '是' : '否',
      p.bundledSkills.length ? p.bundledSkills.join('、') : '-',
      detailed.indexOf(p) >= 0 ? '是' : '否',
    ])));
    lines.push('');
    lines.push('## 4. 逐插件文档（' + (detailed.length + (rest.length ? 1 : 0)) + '）');
    lines.push('');
    lines.push(detailed.map((p, i) => '- ' + code('05-插件/' + pad(i + 1) + '-' + slugOf(p.name) + '.md') + ' — ' + p.name).join('\n'));
    if (rest.length) {
      lines.push('- ' + code('05-插件/' + pad(detailed.length + 1) + '-官方其余插件.md') + ' — ' + rest.length + ' 个官方基础插件（简表）');
    }
    lines.push('');
    lines.push('> 官方基础插件（' + byKind.official.length + ' 个）多数是 Harness 运行时构件，与专家/技能的关系集中在 persona、skill-filesystem、tool-skill、agent-preset、agent-team、mcp-client、credentials，故只有相关项单独成文。');
    lines.push('');
    put('05-插件/00-插件总览.md', lines.join('\n'));

    detailed.forEach((p, i) => {
      const notes = (cfg.pluginNotes || {})[p.name] || {};
      const usedBy = [];
      for (const bn of p.bundledSkills) {
        const es = allEquipped(bn, experts);
        if (es.length) usedBy.push(bn + '（被 ' + es.map(e => e.name).join('、') + ' 引用）');
      }
      const l = [];
      l.push('# 插件：' + p.name);
      l.push('');
      l.push(H());
      l.push('');
      l.push(table(['字段', '值'], [
        ['名称', p.name],
        ['版本', p.version || '（未安装或未知）'],
        ['类型', p.kind === 'workdsh' ? 'WorkDSH 功能插件' : p.kind === 'official' ? '官方 Harness/DSH 插件' : '第三方插件'],
        ['是否在 bundles', p.inBundles ? '是' : '否'],
        ['安装目录', path.join(layout.profileDir, 'node_modules', p.name)],
      ]));
      l.push('');
      if (notes.role) { l.push('## 1. 职责'); l.push(''); l.push(notes.role); l.push(''); }
      const base = notes.role ? 2 : 1;
      l.push('## ' + base + '. 内置技能（' + p.bundledSkills.length + '）');
      l.push('');
      l.push(p.bundledSkills.length ? table(['技能', '本包文档', '被专家引用'], p.bundledSkills.map(bn => {
        const idx = skills.skills.findIndex(s2 => s2.name === bn);
        const es = allEquipped(bn, experts);
        return [bn, idx >= 0 ? code('04-技能/' + pad(idx + 1) + '-' + bn + '.md') : '（未收录）', es.length ? es.map(e => e.name).join('、') : '-'];
      })) : '（该插件不携带内置技能）');
      l.push('');
      l.push('## ' + (base + 1) + '. 与本包范围专家的关系');
      l.push('');
      l.push(usedBy.length ? '- 其内置技能被引用：' + usedBy.join('；') : '- 其内置技能未被范围内专家引用。');
      if (notes.relation) l.push('- ' + notes.relation);
      l.push('');
      put('05-插件/' + pad(i + 1) + '-' + slugOf(p.name) + '.md', l.join('\n'));
    });

    if (rest.length) {
      const l = [];
      l.push('# 官方其余插件（' + rest.length + '）');
      l.push('');
      l.push(H());
      l.push('');
      l.push('以下官方插件属于 Harness 运行时基础构件，未单独成文；列出以便确认环境完整性。');
      l.push('');
      l.push(table(['插件', '版本', '在 bundles', '内置技能'], rest.map(p => [p.name, p.version || '（未知）', p.inBundles ? '是' : '否', p.bundledSkills.length ? p.bundledSkills.join('、') : '-'])));
      l.push('');
      l.push('需要单独成文时：把它们加入 ' + code('tools/expert-report/config.json') + ' 的 ' + code('plugins.officialDetail') + ' 后重建。');
      l.push('');
      put('05-插件/' + pad(detailed.length + 1) + '-官方其余插件.md', l.join('\n'));
    }
  }

  // ---------------------------------------------------------------- 06 MCP
  {
    const reg = sources.mcpRegistry;
    const sessionServers = (runtime && runtime.sessionServers) || [];
    const diskDefs = connectors;
    const regConns = reg ? reg.connections : [];
    const nameOf = c => c.serverName || c.id;
    const allNames = [...new Set([...sessionServers, ...diskDefs.map(nameOf), ...regConns.map(nameOf)])].sort(cmp);

    const view = name => {
      const disk = diskDefs.find(c => nameOf(c) === name) || null;
      const rec = regConns.find(c => nameOf(c) === name) || null;
      const rt = runtime ? (runtime.connectors.find(x => (x.serverName || x.id) === name) || null) : null;
      const fromCatalog = (reg && reg.toolCatalog && reg.toolCatalog[name]) || [];
      const fromRuntime = ((runtime && runtime.connectorTools && runtime.connectorTools[name]) || []).map(t => t.name);
      const tools = fromCatalog.length ? fromCatalog : fromRuntime;
      return { name, disk, rec, rt, tools, session: sessionServers.indexOf(name) >= 0 };
    };

    const lines = [];
    lines.push('# MCP 总览');
    lines.push('');
    lines.push(H());
    lines.push('');
    lines.push('## 1. 为什么这里有三套视图');
    lines.push('');
    lines.push('本机同时存在两个 MCP 管理面，它们的连接集合并不相同：');
    lines.push('');
    lines.push(table(['视图', '来源', '含义', '本机数量'], [
      ['会话可见', 'Harness 提供给本会话的 server 列表', '模型实际能调用 mcp__<server>__* 的范围', String(sessionServers.length || 0)],
      ['WorkDSH 定义', 'storages/workdsh_connectors/definitions/*.json', 'WorkDSH 连接器页面管理的连接', String(diskDefs.length)],
      ['第三方注册表', 'storages/mcp_connector.json（dsh-mcp-connector）', 'mcp_connector_* 工具管理的连接 / 策略 / 授权', reg ? String(reg.connections.length) : '无'],
    ]));
    lines.push('');
    lines.push('> 三者不一致是**本机现状**，不是本资料的判断错误。构建器如实并列，不做合并；不一致会在 ' + code('07-核对/01-校验结果.md') + ' 的"提示"区列出。');
    lines.push('');
    lines.push('## 2. 按 server 并列（' + allNames.length + ' 个）');
    lines.push('');
    lines.push(table(['server', '会话可见', 'WorkDSH 定义', '第三方注册表', '运行时状态', '工具数'], allNames.map(n => {
      const v = view(n);
      return [n, v.session ? '是' : '-', v.disk ? (v.disk.enabled ? '启用' : '停用') : '-',
        v.rec ? (v.rec.enabled ? '存在（启用）' : '存在（停用）') : '-',
        v.rt ? (v.rt.connectionState || '-') : '未采集',
        reg ? String(v.tools.length) : (runtime ? String(v.tools.length) : '未采集')];
    })));
    lines.push('');
    if (reg) {
      lines.push('第三方注册表补充：grant 记录 ' + reg.grantsCount + ' 条、快照 ' + reg.snapshotCount + ' 条；**令牌与 env 值一律不采集**。');
      lines.push('');
    }
    if (runtime) {
      lines.push('运行时健康（第三方注册表来源）：' + (runtime.connectors.map(c => (c.serverName || c.id) + '=' + (c.connectionState || '?')).join('、') || '无') + '；快照 ' + (runtime.generatedAt || '-') + '。');
      lines.push('');
    } else {
      lines.push('> 本次未提供运行时快照：健康 / 工具数标为"未采集"。');
      lines.push('');
    }
    lines.push('## 3. 逐 server 文档');
    lines.push('');
    lines.push(allNames.map((n, i) => '- ' + code('06-MCP/' + pad(i + 1) + '-' + n + '.md')).join('\n'));
    lines.push('');
    lines.push('## 4. 与技能 / 项目的关系');
    lines.push('');
    lines.push('- 技能对 MCP 的依赖只来自正文里的 mcp__<server>__ 引用（逐条取证见各技能文档第 6 节）。');
    lines.push('- 项目在能力快照里以 connector 类型引用连接，构建时逐条解析到上表的 server。');
    lines.push('');
    lines.push('## 5. 安全');
    lines.push('');
    lines.push('- env 只记录键名；URL 去 userinfo；第三方注册表整体不复制（可能含 accessToken / refreshToken）。');
    lines.push('- 连接存在 ≠ 工具被授权调用：策略（Tool > Server > Connection）与会话可见性逐层生效。');
    lines.push('');
    put('06-MCP/00-MCP总览.md', lines.join('\n'));

    allNames.forEach((name, i) => {
      const v = view(name);
      const l = [];
      l.push('# MCP：' + name);
      l.push('');
      l.push(H());
      l.push('');
      l.push('## 1. 三视图在场情况');
      l.push('');
      l.push(table(['视图', '是否存在', '说明'], [
        ['会话可见', v.session ? '是' : '否', v.session ? '模型可调用 mcp__' + name + '__*' : '本会话未提供该 server'],
        ['WorkDSH 定义', v.disk ? '是' : '否', v.disk ? v.disk.file.replace(layout.dshHome, 'DSH_HOME') : '-'],
        ['第三方注册表', v.rec ? '是' : '否', v.rec ? 'key=' + v.rec.key : '-'],
        ['运行时状态', v.rt ? '有' : '未采集', v.rt ? (v.rt.connectionState || '-') : '-'],
      ]));
      l.push('');
      if (v.disk) {
        l.push('## 2. WorkDSH 定义（磁盘权威）');
        l.push('');
        l.push(table(['字段', '值'], [
          ['id', v.disk.id], ['标题', v.disk.title], ['描述', v.disk.description || '-'],
          ['传输', v.disk.transport], ['命令', v.disk.command || '-'], ['参数', (v.disk.args || []).join(' ') || '-'],
          ['URL', v.disk.url || '-'], ['env 键名', v.disk.envKeys.length ? v.disk.envKeys.join('、') + '（值不采集）' : '（无）'],
          ['启用', String(v.disk.enabled)], ['创建时间', v.disk.createdAt || '-'],
        ]));
        l.push('');
      }
      if (v.rec) {
        l.push('## ' + (v.disk ? '3' : '2') + '. 第三方注册表记录（脱敏）');
        l.push('');
        l.push(table(['字段', '值'], [
          ['key', v.rec.key], ['connectorId', v.rec.connectorId || '-'], ['名称', v.rec.name || '-'],
          ['传输', v.rec.transport || '-'], ['serverName', v.rec.serverName || '-'],
          ['启用', String(v.rec.enabled)],
          ['env 键名', v.rec.envKeys.length ? v.rec.envKeys.join('、') + '（值不采集）' : '（无）'],
          ['header 键名', v.rec.headerKeys.length ? v.rec.headerKeys.join('、') + '（值不采集）' : '（无）'],
        ]));
        l.push('');
      }
      if (v.rt) {
        l.push('## ' + ((v.disk ? 1 : 0) + (v.rec ? 1 : 0) + 2) + '. 运行时观测');
        l.push('');
        l.push(table(['字段', '值'], [
          ['健康状态', v.rt.connectionState || '-'],
          ['诊断', v.rt.diagnostic ? (v.rt.diagnostic.code + ' · ' + v.rt.diagnostic.message) : '-'],
          ['作用域', (v.rt.scope && v.rt.scope.label) || '-'],
          ['注入模式', v.rt.injectionLabel || v.rt.injectionMode || '-'],
          ['最近成功', v.rt.lastSuccessfulAt ? iso(v.rt.lastSuccessfulAt) : '（无）'],
        ]));
        l.push('');
      }
      l.push('## ' + ((v.disk ? 1 : 0) + (v.rec ? 1 : 0) + (v.rt ? 1 : 0) + 2) + '. 工具清单（' + (reg || runtime ? v.tools.length : '未采集') + '）');
      l.push('');
      l.push(reg || runtime ? (v.tools.length ? table(['工具'], v.tools.map(t => [t])) : '（无工具记录）') : '未采集（没有注册表也没有运行时快照）。');
      l.push('');
      const usedBySkills = skills.skills.filter(sk => mcpRefs(sk).indexOf(name) >= 0).map(sk => sk.name);
      const usedByProjects = [];
      for (const st of projects) for (const c2 of st.latestConfigs) {
        for (const cap of (c2.capabilities || [])) {
          const hitDisk = v.disk && (cap.id === v.disk.id || cap.id === v.disk.serverName);
          const hitRec = v.rec && (cap.id === v.rec.key || cap.id === v.rec.serverName || cap.id === v.rec.connectorId);
          if (cap.kind === 'connector' && (hitDisk || hitRec || String(cap.label).indexOf(name) >= 0)) {
            usedByProjects.push(((st.projects.find(p => p.id === c2.projectId) || {}).name || c2.projectId) + ' 配置#' + c2.number);
          }
        }
      }
      l.push('## ' + ((v.disk ? 1 : 0) + (v.rec ? 1 : 0) + (v.rt ? 1 : 0) + 3) + '. 关联');
      l.push('');
      l.push('- 引用该 server 的技能：' + (usedBySkills.length ? usedBySkills.map(x => x).join('、') : '无'));
      l.push('- 引用该项目连接：' + (usedByProjects.length ? usedByProjects.join('、') : '无'));
      l.push('');
      put('06-MCP/' + pad(i + 1) + '-' + name + '.md', l.join('\n'));
    });
  }

  // ---------------------------------------------------------------- 07 核对
  {
    const cl = [];
    cl.push('# 变更报告（相对上一次构建）');
    cl.push('');
    cl.push(H());
    cl.push('');
    if (!prev) {
      cl.push('这是首次由构建器生成的版本，没有上一次构建记录可比对。之后每次构建都会在这里列出源文件的新增 / 变更 / 删除。');
    } else {
      cl.push('上次构建：' + prev.builtAt + '（UTC）；本次：' + stamp + '。');
      cl.push('');
      const prevMap = new Map((prev.sources || []).map(x => [x.path, x.sha256]));
      const curMap = new Map(sources.manifestSources.map(x => [x.path, x.sha256]));
      const added = [...curMap.keys()].filter(k => !prevMap.has(k));
      const removed = [...prevMap.keys()].filter(k => !curMap.has(k));
      const changed = [...curMap.entries()].filter(([k, v]) => prevMap.has(k) && prevMap.get(k) !== v).map(([k]) => k);
      cl.push(table(['类型', '数量'], [['新增源', String(added.length)], ['源已变更', String(changed.length)], ['源已删除', String(removed.length)]]));
      cl.push('');
      for (const [title, list] of [['新增源文件', added], ['已变更源文件', changed], ['已删除源文件', removed]]) {
        cl.push('## ' + title + '（' + list.length + '）');
        cl.push('');
        cl.push(list.length ? list.slice(0, 200).map(p => '- ' + p.replace(layout.dshHome, 'DSH_HOME')).join('\n') : '（无）');
        if (list.length > 200) cl.push('');
        if (list.length > 200) cl.push('（仅列前 200 条）');
        cl.push('');
      }
    }
    put('07-核对/02-变更报告.md', cl.join('\n'));

    const csv = ['kind,path,bytes,sha256'];
    for (const s of sources.manifestSources) csv.push([s.kind, s.path, s.bytes, s.sha256].map(v => String(v).indexOf(',') >= 0 ? '"' + String(v).replace(/"/g, '""') + '"' : v).join(','));
    put('07-核对/04-源文件哈希.csv', csv.join('\n') + '\n');
  }

  return out;
}

/** Written by build.mjs after every late check (copies, secret scan) is known. */
export function renderChecksDoc(checks, builtAt) {
  const lines = [];
  lines.push('# 构建校验结果');
  lines.push('');
  lines.push('> 由 ' + code('tools/expert-report/build.mjs') + ' 在全部检查完成后写入，内容基准时间（UTC）：' + builtAt + '。任何 FAIL 都意味着产物不可交付。');
  lines.push('');
  lines.push('## 1. 校验项');
  lines.push('');
  lines.push(table(['#', '检查', '结果', '说明'], checks.items.map((c, i) => [String(i + 1), c.name, c.ok ? 'PASS' : 'FAIL', c.detail])));
  lines.push('');
  lines.push('## 2. 汇总');
  lines.push('');
  lines.push(table(['项', '值'], [
    ['检查总数', String(checks.items.length)],
    ['通过', String(checks.items.filter(c => c.ok).length)],
    ['失败', String(checks.items.filter(c => !c.ok).length)],
    ['提示（不阻断）', String((checks.warnings || []).length)],
    ['结论', checks.ok ? '全部通过' : '**存在失败项，产物不可交付**'],
  ]));
  lines.push('');
  if ((checks.warnings || []).length) {
    lines.push('## 3. 提示（不阻断交付，但需要知道）');
    lines.push('');
    lines.push(table(['#', '提示', '说明'], (checks.warnings || []).map((w, i) => [String(i + 1), w.name, w.detail])));
    lines.push('');
  }
  return lines.join('\n');
}
