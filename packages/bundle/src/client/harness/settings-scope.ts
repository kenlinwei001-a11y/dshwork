import type { Context } from '@deepseek-ai/cordis';

/**
 * Compatibility bridge for third-party client plugins that still inject the
 * legacy `settingsScope` service. DSH 0.2 replaced that service with the
 * document-based settings Remote (`settings/describe` + `settings/mutate`),
 * so plugins such as dsh-mcp-connector and dshmarket silently lose their
 * settings bindings and fall back to visible-by-default UI.
 *
 * The adapter keeps the old shape (`bind({namespace, decode})` returning a
 * snapshot store) and reads/writes through the new Remote. It is deliberately
 * small: it only covers the surface those plugins use.
 */
type SettingsScopeSpec = {
  namespace: string;
  decode?: (value: unknown) => unknown;
};

type SettingsSnapshot = {
  status: 'loading' | 'ready' | 'error';
  value?: unknown;
};

type SettingsScope = {
  getSnapshot(): SettingsSnapshot;
  subscribe(listener: () => void): () => void;
  set(field: string, value: unknown): Promise<boolean>;
  unset(field: string): Promise<boolean>;
};

type SettingsNamespaceView = {
  ns: string;
  value?: unknown;
  revision?: number;
};

type SettingsRemote = {
  describe(): Promise<{ ok: boolean; value?: { namespaces?: SettingsNamespaceView[] }; error?: unknown }>;
  mutate(namespace: string, ops: unknown[], expectedRevision?: number): Promise<{ ok: boolean; error?: unknown }>;
};

type RemoteFace = {
  settings?: SettingsRemote;
  $on(event: string, listener: (event: { ns?: string }) => void): () => void;
};

/**
 * The namespaces whose old plugins have no DSH 0.2 settings document. Their
 * explicit product default is kept here; the MCP Connector must stay out of
 * the sidebar unless the user turns it back on.
 */
const ABSENT_NAMESPACE_DEFAULTS: Readonly<Record<string, unknown>> = {
  'mcp-connector': { showSidebarEntry: false },
};

function createScope(ctx: Context, remote: RemoteFace, spec: SettingsScopeSpec): SettingsScope {
  const { namespace, decode } = spec;
  let snapshot: SettingsSnapshot = { status: 'loading' };
  let revision = -1;
  const listeners = new Set<() => void>();
  const publish = (): void => {
    for (const listener of listeners) listener();
  };
  const applyView = (value: { namespaces?: SettingsNamespaceView[] } | undefined): void => {
    const view = value?.namespaces?.find((row) => row.ns === namespace);
    if (view !== undefined) {
      snapshot = { status: 'ready', value: decode === undefined ? view.value : decode(view.value) };
      revision = view.revision ?? -1;
      return;
    }
    snapshot = { status: 'ready', value: ABSENT_NAMESPACE_DEFAULTS[namespace] };
    revision = -1;
  };
  const load = async (): Promise<void> => {
    try {
      const response = await remote.settings!.describe();
      if (response.ok) applyView(response.value);
      else snapshot = { status: 'error' };
    } catch {
      snapshot = { status: 'error' };
    }
    publish();
  };
  const disposeUpdate = remote.$on('settings/document-updated', (event) => {
    if (event?.ns === undefined || event.ns === namespace) void load();
  });
  ctx.effect(() => disposeUpdate, `workdsh.settings-scope(${namespace})`);
  void load();
  const write = async (ops: unknown[]): Promise<boolean> => {
    try {
      const response = await remote.settings!.mutate(namespace, ops, revision >= 0 ? revision : undefined);
      await load();
      return response.ok;
    } catch {
      await load();
      return false;
    }
  };
  return {
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    set: (field, value) => write([{ op: 'set', path: [field], value }]),
    unset: (field) => write([{ op: 'unset', path: [field] }]),
  };
}

/** Register the legacy `settingsScope` client service on this composition. */
export function installSettingsScope(ctx: Context): void {
  const remote = (ctx as unknown as { remote?: RemoteFace }).remote;
  if (remote?.settings === undefined) return;
  const scopes = new Map<string, SettingsScope>();
  const service = {
    bind(spec: SettingsScopeSpec): SettingsScope {
      const key = `${spec.namespace}\0${String(spec.decode)}`;
      let scope = scopes.get(key);
      if (scope === undefined) {
        scope = createScope(ctx, remote, spec);
        scopes.set(key, scope);
      }
      return scope;
    },
  };
  (ctx as unknown as { provide(name: string, value: unknown): void }).provide('settingsScope', service);
}
