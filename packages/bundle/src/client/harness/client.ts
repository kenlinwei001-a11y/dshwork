import type { Context } from '@deepseek-ai/cordis';
import type {} from '@deepseek-ai/dsh-api-remotes/client';
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client';
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client';
import type {} from '@deepseek-ai/dsh-client-ui-theme/client';
import * as workbench from 'workdsh-plugin-workbench';
import { BrandMark, BrandName, DiagnosticsMark } from '../components/Brand.js';
import { DiagnosticsPanel, type Inventory } from '../components/DiagnosticsPanel.js';
import { NavigationLocation } from '../components/NavigationLocation.js';

export const name = 'workdsh-client';
export const inject = ['slots', 'layout', 'remote', 'remote.pluginInventory', 'theme'];

const productViews: Readonly<Record<string, string>> = {
  experts: 'workdsh-experts', skills: 'workdsh-skills', assistant: 'workdsh-assistant', projects: 'workdsh-projects',
  library: 'workdsh-library', automation: 'workdsh-automation', more: 'workdsh-more',
};

export function apply(ctx: Context): void {
  const diagnostics = new URL(window.location.href).searchParams.get('diagnostics') === '1';
  const viewToPanel = diagnostics ? { ...productViews, diagnostics: 'workdsh-probe' } : productViews;
  const panelToView = Object.fromEntries(Object.entries(viewToPanel).map(([view, panel]) => [panel, view]));
  const selectView = (view: string | null) => {
    const requested = view ? viewToPanel[view] : undefined;
    const selected = requested && ctx.slots.entriesOfSlot('main').some(entry => entry.options.key === requested)
      ? requested as Parameters<typeof ctx.layout.selectPanel>[0] : null;
    ctx.layout.selectPanel(selected);
    return selected;
  };

  const previousTheme = ctx.theme.getTheme().preference;
  const unregisterTheme = ctx.theme.register({ id: 'workdsh', colorScheme: 'dark', tokens: {
    '--dsw-alias-bg-layer-1': '#121212', '--dsw-alias-bg-layer-2': '#202020',
    '--dsw-alias-bg-layer-3': '#242424', '--dsw-alias-label-primary': '#e7e7e7',
    '--dsw-alias-label-secondary': '#a5a5a5', '--dsw-specific-sidebar-fill': '#202020',
    '--dsw-specific-sidebar-nav-item-active': '#3a3a3a',
  } });
  const stopThemeSync = ctx.on('theme/change', snapshot => {
    if (snapshot.active.colorScheme !== 'dark') ctx.theme.setTheme('workdsh');
  });
  ctx.theme.setTheme('workdsh');
  ctx.effect(() => () => {
    stopThemeSync();
    if (ctx.theme.getTheme().active.id === 'workdsh') ctx.theme.setTheme(previousTheme);
    unregisterTheme();
  });

  ctx.plugin(workbench);
  ctx.slots.inject('sidebar.brand.name', () => ctx.slots.register({ name: 'sidebar.brand.name', priority: -10 }, BrandName));
  ctx.slots.inject('sidebar.brand.mark', () => ctx.slots.register({ name: 'sidebar.brand.mark', priority: -10 }, BrandMark));
  ctx.slots.inject('shell.overlay', () => ctx.slots.register({
    name: 'shell.overlay', id: 'workdsh-location', inject: () => ({ panelToView, selectView }),
  }, NavigationLocation));

  ctx.slots.inject('main', () => {
    const dispose = diagnostics ? ctx.slots.register({
      name: 'main', key: 'workdsh-probe', inject: () => ({
        inspect: async (): Promise<Inventory> => {
          const response = await ctx.remote.pluginInventory.list();
          if (!response.ok) throw new Error(response.error.code);
          return { total: response.value.entries.length, modules: response.value.entries
            .filter(row => row.moduleName.startsWith('workdsh-'))
            .map(row => ({ module: row.moduleName, phase: row.fiberPhase })) };
        },
        returnToConversation: () => ctx.layout.selectPanel(null),
      }),
    }, DiagnosticsPanel) : () => {};
    return dispose;
  });
  if (diagnostics) ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
    name: 'sidebar.panellist', id: 'workdsh-probe', label: 'NexusOne 接入验证', order: 90,
  }, DiagnosticsMark));
}
