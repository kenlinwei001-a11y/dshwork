import type { ConnectorInput } from '../shared.js';

/**
 * dsh-mcp-connector 目录的只读门面：把它的远程目录（100+ 条目）引入
 * 「添加 MCP」流程。连接仍由本插件 manager.create 建立，保持按会话隔离。
 */

export type CatalogCredentialField = { key: string; label?: string; placeholder?: string; description?: string; helpLabel?: string; required?: boolean; secret?: boolean };
export type CatalogServer = { serverKey: string; serverName: string; transport: 'stdio' | 'streamable-http'; url?: string; command?: string; args?: string[]; credentialBindings?: Record<string, string> };
export type CatalogPrompt = { title: string; text: string };
export type CatalogItem = {
  id: string; name: string; vendor?: string; icon?: string; category?: string; summary?: string; description?: string;
  tags?: string[]; featured?: boolean; homepage?: string; authMode?: 'none' | 'bearer' | 'api-key' | 'oauth2-pkce';
  apiKeyHeader?: string; credentialFields?: CatalogCredentialField[]; prompts?: CatalogPrompt[]; servers?: CatalogServer[];
};

/** native = 可直接在本插件创建；oauth / external = 需交给目录插件的完整流程。 */
export type ServerSupport = { kind: 'native' } | { kind: 'oauth' } | { kind: 'external'; reason: string };

const path = '/mcp-connector/api';

export async function fetchCatalog(signal?: AbortSignal): Promise<readonly CatalogItem[]> {
  const response = await fetch(path, {
    method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ method: 'catalog', params: {} }), signal: signal ?? AbortSignal.timeout(20_000),
  });
  const result = await response.json() as { ok?: boolean; detail?: { items?: CatalogItem[] }; message?: string };
  if (!result.ok) throw new Error(result.message || '目录服务暂不可用。');
  return result.detail?.items ?? [];
}

export function serverSupport(item: CatalogItem, server: CatalogServer): ServerSupport {
  const mode = item.authMode ?? 'none';
  if (mode === 'oauth2-pkce') return { kind: 'oauth' };
  const fields = item.credentialFields ?? [];
  if (fields.length > 1) return { kind: 'external', reason: '需要多组凭据' };
  if (server.transport === 'stdio') {
    if (mode !== 'none' || Object.keys(server.credentialBindings ?? {}).length > 0) return { kind: 'external', reason: '需要环境变量凭据' };
    return { kind: 'native' };
  }
  return { kind: 'native' };
}

/** 目录条目在本面板里的整体可接入性（任一 server 可原生接入即可用）。 */
export function itemSupport(item: CatalogItem): 'native' | 'oauth' | 'external' {
  const servers = item.servers ?? [];
  if (servers.some(server => serverSupport(item, server).kind === 'native')) return 'native';
  if (servers.some(server => serverSupport(item, server).kind === 'oauth')) return 'oauth';
  return 'external';
}

const clip = (value: string, max: number) => value.length > max ? `${value.slice(0, max - 1)}…` : value;
const safeServerName = (value: string) => value.replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 32) || 'mcp';

/** 把目录条目 + server 映射为创建输入；bearer 凭据按目录语义补 Bearer 前缀。 */
export function toConnectorInput(item: CatalogItem, server: CatalogServer, credential?: string): ConnectorInput {
  const title = clip((item.servers ?? []).length > 1 ? `${item.name}·${server.serverKey}` : item.name, 80);
  const description = clip(item.summary || item.description || '', 240);
  const base = { title, description, serverName: safeServerName(server.serverName), transport: server.transport };
  if (server.transport === 'stdio') return { ...base, command: server.command ?? '', args: server.args ?? [] };
  const mode = item.authMode ?? 'none';
  const token = credential?.trim();
  if (!token || mode === 'none') return { ...base, url: server.url ?? '' };
  if (mode === 'bearer') return { ...base, url: server.url ?? '', authorizationToken: /^Bearer\s+/i.test(token) ? token : `Bearer ${token}` };
  return { ...base, url: server.url ?? '', credentialHeader: item.apiKeyHeader || 'Authorization', authorizationToken: token };
}

export const authLabel = (item: CatalogItem): string => {
  switch (item.authMode ?? 'none') {
    case 'oauth2-pkce': return 'OAuth 授权';
    case 'bearer': return '访问令牌';
    case 'api-key': return 'API Key';
    default: return '免登录';
  }
};

/** icon 多为 emoji，也可能是同源路径或 URL；渲染交给调用方。 */
export const iconKind = (icon?: string): { kind: 'img'; src: string } | { kind: 'text'; text: string } => {
  if (!icon) return { kind: 'text', text: '' };
  if (icon.startsWith('/') || icon.startsWith('http://') || icon.startsWith('https://')) return { kind: 'img', src: icon };
  return { kind: 'text', text: icon };
};
