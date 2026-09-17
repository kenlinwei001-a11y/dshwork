import { TaskExecutionNotice } from '../client/components/TaskExecutionNotice.js';
import type { Context } from '@deepseek-ai/cordis';
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client';
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client';
import {
  BusinessPanel,
  BusinessPanelIcon,
  businessPanels,
} from '../client/components/BusinessPanel.js';

/**
 * Keep the official Sidebar and Conversation occupants in place. WorkDSH only
 * contributes business navigation and paired main panels through public Slots.
 */
export const name = 'workdsh-workbench-client';
export const inject = ['slots'];

export function apply(ctx: Context): void {
  ctx.slots.inject('conversation.input.dock', () => ctx.slots.register({ name: 'conversation.input.dock', id: 'workdsh-task-execution-notice' }, TaskExecutionNotice));
  for (const panel of businessPanels) {
    if ('description' in panel && panel.description && panel.id !== 'workdsh-library') {
      ctx.slots.inject('main', () => ctx.slots.register({
        name: 'main',
        key: panel.id,
        inject: () => ({ label: panel.label, description: panel.description }),
      }, BusinessPanel));
    }
    ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
      name: 'sidebar.panellist',
      id: panel.id,
      label: panel.label,
      order: panel.order,
      inject: () => ({ icon: panel.icon }),
    }, BusinessPanelIcon));
  }
}
