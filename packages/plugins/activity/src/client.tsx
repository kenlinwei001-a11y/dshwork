import * as React from 'react';
import type { Context } from '@deepseek-ai/cordis';
import type { ISessions } from '@deepseek-ai/dsh-api-session-controller/client';
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client';
import type { PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots';
import type {} from '@deepseek-ai/dsh-client-ui-session/client';
import type {} from '@deepseek-ai/dsh-client-ui-slots';
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client';
import type { ActivityIdentity, ActivityPresentation } from 'workdsh-contracts/activity';
import { createPresentationRegistry } from './registry.js';
import { activityMessage, projectActivity } from './projection.js';
import { summarizeTeamActivity, type TeamView } from './team-status.js';
import { css } from './styles.js';

declare module '@deepseek-ai/cordis' { interface Context { activityPresentation: ActivityPresentation; } }
declare module '@deepseek-ai/dsh-api-session-controller/client' { interface SessionReferenceSourceMap { workdshActivityMember: unknown; } }
export const name = 'workdsh-activity-client';
export const inject = ['slots', 'sessions', 'remote'];
const motionKey = 'workdsh.activity.motion.v1';
function readMotion() { try { return localStorage.getItem(motionKey) !== 'off'; } catch { return true; } }
function Face({ identity, phase }: { identity?: ActivityIdentity; phase: string }) {
  const avatar = identity?.avatar;
  const safe = avatar?.startsWith('data:image/png;base64,') || avatar?.startsWith('data:image/jpeg;base64,') || avatar?.startsWith('data:image/webp;base64,');
  return <span className="wd-activity-face" data-active={phase === 'working'} aria-hidden="true">{safe ? <img src={avatar} alt="" /> : identity?.kind === 'expert' || identity?.kind === 'team' ? identity.name.slice(0,1) : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4"><g className="wd-activity-eyes"><circle cx="9" cy="10" r=".8"/><circle cx="15" cy="10" r=".8"/></g>{phase === 'completed' || phase === 'idle' ? <path d="M7.5 13.5q4.5 5 9 0"/> : <path d="M8.5 14.5h7"/>}</svg>}</span>;
}

export function apply(ctx: Context): void {
  const registry = createPresentationRegistry();
  let teamRemote: { view(id: string): Promise<{ ok: true; value: TeamView } | { ok: false }> } | undefined;
  ctx.provide('activityPresentation', registry);
  // The official Team UI mounts its generated Remote namespace dynamically.
  // Bind to that exact service lifecycle instead of sampling `ctx.remote`
  // before the contribution exists.
  ctx.inject(['remote.agentTeams'], teamCtx => {
    teamRemote = (teamCtx as unknown as { remote: { agentTeams: typeof teamRemote } }).remote.agentTeams;
    return () => { teamRemote = undefined; };
  });
  const sessions = ctx.sessions as unknown as ISessions;
  ctx.effect(() => { const style = document.createElement('style'); style.textContent = css; style.dataset.workdshActivity = 'true'; document.head.append(style); return () => style.remove(); });

  function Bar(props: PropsRuntime<'conversation.session.header.utilities'>) {
    const session = props.useSession(value => value);
    const list = props.useSessions(value => value);
    const binding = sessions.binding(props.sessionId);
    const source = binding?.eventSource;
    const feed = React.useMemo(() => ({ subscribe: (listener: () => void) => source?.subscribe(listener) ?? (() => {}), getSnapshot: () => source?.getSnapshot() }), [source]);
    const window = React.useSyncExternalStore(feed.subscribe, feed.getSnapshot);
    const revision = React.useSyncExternalStore(registry.subscribe, registry.getRevision);
    const state = React.useMemo(() => projectActivity(window?.entries ?? [], session.running), [window, session.running]);
    const [expanded, setExpanded] = React.useState(false);
    const [motion, setMotion] = React.useState(readMotion);
    const [clock, setClock] = React.useState(Date.now);
    const [identities, setIdentities] = React.useState<ReadonlyMap<string, ActivityIdentity>>(new Map());
    const [labels, setLabels] = React.useState<ReadonlyMap<string,string>>(new Map());
    const address = session.subagent?.address;
    const rootSessionId = address?.parentSessionId ?? props.sessionId;
    const catalog = list.subagentsByParent[rootSessionId];
    const children = catalog?.entries.filter(row => row.kind === 'child').slice(-20) ?? [];
    const ids = children.map(row => row.id).join('|');
    React.useEffect(() => {
      const cancel = new AbortController();
      for (const id of [props.sessionId, rootSessionId, ...ids.split('|').filter(Boolean)]) {
        void registry.resolveIdentity(id, cancel.signal).then(identity => { if (!cancel.signal.aborted) setIdentities(previous => { const next = new Map(previous); if (identity) next.set(id, identity); else next.delete(id); return next; }); }).catch(() => { /* optional identity or cancelled session */ });
      }
      void registry.resolveSkillLabels().then(value => { if (!cancel.signal.aborted) setLabels(value); });
      return () => cancel.abort();
    }, [props.sessionId, rootSessionId, ids, revision]);
    React.useEffect(() => { setIdentities(new Map()); setExpanded(false); }, [props.sessionId]);
    // The catalog is a sampled driver state, not a continuously running child feed.
    React.useEffect(() => {
      let disposed = false;
      const refresh = () => { if (!disposed) void sessions.refreshSubagents(rootSessionId).catch(() => { /* native catalog carries its error; retry while running */ }); };
      refresh();
      const timer = session.running ? windowGlobal.setInterval(refresh, 3000) : undefined;
      return () => { disposed = true; if (timer !== undefined) windowGlobal.clearInterval(timer); };
    }, [rootSessionId, session.running]);

    const rootIdentity = identities.get(rootSessionId) ?? identities.get(props.sessionId);
    const isTeam = rootIdentity?.kind === 'team' || children.length > 0 || !!address;
    const [teamView, setTeamView] = React.useState<TeamView>();
    React.useEffect(() => {
      setTeamView(undefined);
      if (!isTeam) return;
      let disposed = false;
      const refresh = async () => {
        try {
          if (!teamRemote) return;
          const result = await teamRemote.view(String(rootSessionId));
          if (!disposed && result.ok) setTeamView(result.value);
        } catch { /* Team Remote is optional for ordinary activity installations. */ }
      };
      void refresh();
      // A teammate can be running while the Lead Session itself is idle.
      const timer = windowGlobal.setInterval(refresh, 1500);
      return () => { disposed = true; windowGlobal.clearInterval(timer); };
    }, [rootSessionId, isTeam, session.running]);
    const memberIds = teamView?.members.map(member => String(member.id)).join('|') ?? '';
    const [memberTerminalPhases, setMemberTerminalPhases] = React.useState<ReadonlyMap<string, 'failed' | 'interrupted'>>(new Map());
    React.useEffect(() => {
      // alpha.2: borrowing a binding needs a retained generation. Retain every listed
      // member with this plugin's own source; full teardown releases each reference.
      let disposed = false;
      const cleanups: Array<() => void> = [];
      const references = memberIds.split('|').filter(Boolean).flatMap(id => {
        try { return [sessions.retain(id as Parameters<ISessions['scope']>[0], { source: 'workdshActivityMember' })]; }
        catch { return []; }
      });
      const refresh = () => {
        const next = new Map<string, 'failed' | 'interrupted'>();
        for (const reference of references) {
          try {
            const memberWindow = reference.binding.eventSource.getSnapshot();
            const memberSnapshot = reference.binding.session.getSnapshot();
            const phase = projectActivity(memberWindow?.entries ?? [], memberSnapshot.running).phase;
            if (phase === 'failed' || phase === 'interrupted') next.set(String(reference.sessionId), phase);
          } catch { /* released or generation disposed before it settled */ }
        }
        if (!disposed) setMemberTerminalPhases(next);
      };
      for (const reference of references) {
        void reference.ready.then(binding => {
          if (disposed) return;
          cleanups.push(binding.eventSource.subscribe(refresh));
          cleanups.push(binding.session.subscribe(refresh));
          refresh();
        }).catch(() => { /* member open failed; nothing to observe */ });
      }
      refresh();
      return () => {
        disposed = true;
        for (const cleanup of cleanups) cleanup();
        for (const reference of references) reference.release();
      };
    }, [memberIds]);

    React.useEffect(() => { if (!session.running) return; setClock(Date.now()); const timer = windowGlobal.setInterval(() => setClock(Date.now()), 1000); return () => windowGlobal.clearInterval(timer); }, [session.running, props.sessionId]);
    React.useEffect(() => { const update = () => setMotion(readMotion()); windowGlobal.addEventListener('storage', update); return () => windowGlobal.removeEventListener('storage', update); }, []);
    React.useEffect(() => { if (!expanded) return; const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setExpanded(false); }; windowGlobal.addEventListener('keydown', escape); return () => windowGlobal.removeEventListener('keydown', escape); }, [expanded]);
    if (session.blank) return null;
    const identity = rootIdentity;
    // The official Team panel owns roster, task board and member navigation.
    // This strip remains the compact, glanceable execution state for both
    // individual and Team sessions; it never duplicates Team controls.
    const team = isTeam;
    const elapsed = state.startedAt ? Math.max(0, Math.floor((clock - state.startedAt)/1000)) : 0;
    const stale = session.running && state.lastProgressAt && clock - state.lastProgressAt > 120000;
    const text = stale ? '暂未收到新进展' : activityMessage(state);
    const teamSummary = summarizeTeamActivity(teamView, String(address?.childSessionId ?? props.sessionId), text, memberTerminalPhases);
    const activeIdentity = teamSummary.member
      ? identity?.members?.find(member => member.key === teamSummary.member?.name) ?? { name: teamSummary.member.name, kind: 'expert' as const }
      : identity;
    const teamExtra = teamSummary.member && teamSummary.runningCount > 1 ? ` · 另 ${teamSummary.runningCount - 1} 位专家处理中` : '';
    const displayText = team
      ? teamSummary.member ? `${activeIdentity?.name ?? teamSummary.member.name} · ${teamSummary.focus ?? '正在处理'}${teamExtra}` : teamSummary.message
      : text;
    const displayPhase = teamSummary.phase ?? (team && teamSummary.runningCount > 0 ? 'working' : state.phase);
    const changeMotion = (value: boolean) => { setMotion(value); try { localStorage.setItem(motionKey, value ? 'on' : 'off'); } catch { /* session-only fallback */ } };
    return <section className="wd-activity" aria-label="活动与协作进度" data-phase={displayPhase} data-motion={motion} data-long={elapsed >= 480} data-team={team}>
      <div className="wd-activity-bar">
        <span className="wd-activity-people"><Face identity={activeIdentity} phase={displayPhase}/></span>
        <div className="wd-activity-copy">
          <span className="wd-activity-title">{team ? identity?.teamName ?? identity?.name ?? '团队协作' : '工作动态'}</span>
          <span className="wd-activity-action" title={displayText}>
            {`${displayText}${state.skill ? ` · ${labels.get(state.skill) ?? state.skill}` : ''}`}
          </span>
        </div>
        {session.running && elapsed >= 60 && <span className="wd-activity-time">{Math.floor(elapsed/60)}分{elapsed%60}秒</span>}
        <button className="wd-activity-motion" title={motion ? '动画已开启，点击关闭' : '动画已关闭，点击开启'} aria-label={motion ? '关闭动态效果' : '开启动效'} aria-pressed={motion} onClick={() => changeMotion(!motion)}><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.4">{motion ? <><path d="M7 5v10M13 5v10"/></> : <path d="m7 4 8 6-8 6Z"/>}</svg></button>
        <button className="wd-activity-toggle" aria-label="展开协作详情" aria-expanded={expanded} aria-controls={`activity-${props.sessionId}`} onClick={() => setExpanded(!expanded)}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d={expanded ? 'm6 15 6-6 6 6' : 'm6 9 6 6 6-6'}/></svg></button>
      </div>
      {expanded && <div className="wd-activity-details" id={`activity-${props.sessionId}`}><header><strong>{identity?.name ?? '助理'} · {activityMessage(state)}</strong><button aria-label="关闭协作详情" onClick={() => setExpanded(false)}>×</button></header>
        <p>状态来自原生任务记录。</p>

        {state.skill && <p>已加载技能：{labels.get(state.skill) ?? state.skill}</p>}
        {state.tool && <p>当前工具：{state.tool}</p>}
        {teamView?.members.map(member => {
          const task = teamView.tasks.find(row => row.ownerName === member.name && row.status === 'in_progress');
          const person = identity?.members?.find(row => row.key === member.name);
          return <div className="wd-activity-person" key={String(member.id)}><span className="wd-activity-status"/><span className="wd-activity-name">{person?.name ?? member.name}</span><span>{task?.subject ?? member.description ?? member.status}</span></div>;
        })}
        <label><input type="checkbox" checked={motion} onChange={event => changeMotion(event.target.checked)}/>启用轻量动画</label><small>关闭后状态照常更新。遵循系统“减少动态效果”设置。</small>
      </div>}
    </section>;
  }
  // Public additive header utility slot. Local CSS reserves one strip beneath
  // the native tabs; native header, child slots and body keep their owners.
  ctx.slots.inject('conversation.session.header.utilities', () => ctx.slots.register({
    name: 'conversation.session.header.utilities', id: 'workdsh-activity', order: 100,
  }, Bar));
}
const windowGlobal = globalThis.window;
