import * as React from 'react';
import { useEffect, useMemo, useState } from 'react';
import type { ConnectorInput } from '../shared.js';
import type { ConnectorManagementClient } from './management.js';
import { authLabel, fetchCatalog, iconKind, itemSupport, serverSupport, toConnectorInput, type CatalogItem, type CatalogServer } from './catalog.js';

type Props = {
  management: ConnectorManagementClient;
  /** 现有 serverName 集合，避免重复接入冲突。 */
  existingServerNames: readonly string[];
  /** stdio 条目先落表单，由用户确认启动命令路径后再保存。 */
  onPrefill: (input: ConnectorInput) => void;
  onChanged: () => void;
};

type RowState = { status: 'idle' | 'busy' | 'done' } | { status: 'error'; message: string };

const DIRECTORY_PLUGIN_URL = '/mcp-connector/ui/';
const bareCommand = /^(npx|npm|node|python3?|uvx?|deno|bunx?)$/;

function CatalogMark({ item }: { item: CatalogItem }) {
  const icon = iconKind(item.icon);
  if (icon.kind === 'img') return <img className="catalog-mark" src={icon.src} alt="" aria-hidden />;
  return <span className="catalog-mark" aria-hidden>{icon.text || item.name.charAt(0).toUpperCase()}</span>;
}

function ServerRow({ item, server, taken, management, onPrefill, onChanged }: {
  item: CatalogItem; server: CatalogServer; taken: boolean;
  management: ConnectorManagementClient; onPrefill: (input: ConnectorInput) => void; onChanged: () => void;
}) {
  const support = serverSupport(item, server);
  const needsCredential = support.kind === 'native' && server.transport === 'streamable-http' && (item.authMode === 'bearer' || item.authMode === 'api-key');
  const field = (item.credentialFields ?? [])[0];
  const [credential, setCredential] = useState('');
  const [row, setRow] = useState<RowState>({ status: 'idle' });
  const connect = async () => {
    setRow({ status: 'busy' });
    try {
      await management.create(toConnectorInput(item, server, credential));
      setRow({ status: 'done' }); onChanged();
    } catch (cause) { setRow({ status: 'error', message: cause instanceof Error ? cause.message : '接入失败，请重试。' }); }
  };
  const openDirectory = () => { window.open(DIRECTORY_PLUGIN_URL, '_blank', 'noopener'); };
  return <div className="catalog-server">
    <div className="catalog-server-head">
      <span className={`transport-chip ${server.transport}`}>{server.transport === 'stdio' ? '本机进程' : 'HTTP'}</span>
      <code>{server.serverName}</code>
      <span className="catalog-server-actions">
        {support.kind === 'native' && server.transport === 'streamable-http'
          ? <button className="primary" disabled={row.status === 'busy' || row.status === 'done' || taken || (needsCredential && !credential.trim())} onClick={() => void connect()}>
            {row.status === 'done' ? '✓ 已添加' : taken ? '已存在' : row.status === 'busy' ? '接入中…' : '接入'}</button>
          : null}
        {support.kind === 'native' && server.transport === 'stdio'
          ? <button className="secondary" disabled={taken} onClick={() => onPrefill(toConnectorInput(item, server))}>{taken ? '已存在' : '填入表单'}</button>
          : null}
        {support.kind === 'oauth' ? <><span className="badge oauth">需 OAuth 授权</span><button className="secondary" onClick={openDirectory}>前往授权</button></> : null}
        {support.kind === 'external' ? <><span className="badge">{support.reason}</span><button className="secondary" onClick={openDirectory}>前往目录插件</button></> : null}
      </span>
    </div>
    {needsCredential && row.status !== 'done' && !taken ? <label className="catalog-credential">{field?.label || (item.authMode === 'bearer' ? '访问令牌' : 'API Key')}
      <input type="password" autoComplete="new-password" value={credential} placeholder={field?.placeholder || '仅写入本机凭据服务，不会展示'} onChange={event => setCredential(event.currentTarget.value)} />
      {field?.description ? <small>{field.description}</small> : null}
    </label> : null}
    {server.transport === 'stdio' && bareCommand.test(server.command ?? '') && !taken
      ? <p className="catalog-hint">后台服务环境 PATH 不含 /usr/local/bin：填入表单后请把启动命令改成绝对路径（如 /usr/local/bin/{server.command}）。</p>
      : null}
    {row.status === 'error' ? <p className="error" role="alert">{row.message}</p> : null}
  </div>;
}

export function CatalogBrowser({ management, existingServerNames, onPrefill, onChanged }: Props) {
  const [items, setItems] = useState<readonly CatalogItem[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [detailId, setDetailId] = useState<string>();
  const load = async () => {
    setStatus('loading'); setError('');
    try { setItems(await fetchCatalog()); setStatus('ready'); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '目录加载失败。'); setStatus('error'); }
  };
  useEffect(() => { void load(); }, []);
  const categories = useMemo(() => [...new Set(items.map(item => item.category).filter((value): value is string => Boolean(value)))], [items]);
  const normalized = query.trim().toLowerCase();
  const filtered = items.filter(item => (!category || item.category === category)
    && (!normalized || [item.id, item.name, item.vendor, item.summary, item.description, ...(item.tags ?? [])].filter(Boolean).some(value => String(value).toLowerCase().includes(normalized))));
  const detail = items.find(item => item.id === detailId);
  if (status === 'loading') return <div className="catalog-empty">正在读取 MCP 目录…</div>;
  if (status === 'error') return <div className="catalog-empty"><p>{error}</p><p className="muted">目录由 dsh-mcp-connector 插件提供，请确认它已安装并启用。</p><button className="secondary" onClick={() => void load()}>重试</button></div>;
  if (detail) {
    const support = itemSupport(detail);
    return <div className="catalog-detail">
      <button className="catalog-back" onClick={() => setDetailId(undefined)}>‹ 返回目录</button>
      <div className="catalog-detail-hero">
        <CatalogMark item={detail} />
        <div className="catalog-detail-title"><strong>{detail.name}</strong>
          <span className="muted">{[detail.vendor, detail.category].filter(Boolean).join(' · ')}</span></div>
        <span className={`badge support-${support}`}>{support === 'native' ? '可直接接入' : support === 'oauth' ? '需 OAuth 授权' : '需目录插件'}</span>
        {detail.homepage ? <a className="catalog-home" href={detail.homepage} target="_blank" rel="noreferrer noopener">官网</a> : null}
      </div>
      {detail.description ? <p className="catalog-description">{detail.description}</p> : null}
      {detail.tags?.length ? <p className="catalog-tags">{detail.tags.map(tag => <span key={tag} className="badge">{tag}</span>)}</p> : null}
      {detail.prompts?.length ? <div className="catalog-prompts"><small className="muted">示例用法</small>{detail.prompts.slice(0, 3).map(prompt => <p key={prompt.title}>· {prompt.title}</p>)}</div> : null}
      <div className="catalog-servers"><small className="muted">MCP 服务（{detail.servers?.length ?? 0}）</small>
        {(detail.servers ?? []).map(server => <ServerRow key={server.serverKey} item={detail} server={server}
          taken={existingServerNames.includes(server.serverName)} management={management} onPrefill={onPrefill} onChanged={onChanged} />)}
      </div>
      {support !== 'native' ? <p className="catalog-hint">OAuth 与多凭据连接由目录插件完成授权与配置，接入后工具全局可用；免登录与单凭据连接建议直接在此接入，可按会话启用。</p> : null}
    </div>;
  }
  return <div className="catalog-browser">
    <div className="catalog-toolbar">
      <input className="search" aria-label="搜索目录" placeholder="搜索目录" value={query} onChange={event => setQuery(event.currentTarget.value)} />
      <span className="muted">{filtered.length} / {items.length}</span>
    </div>
    <div className="catalog-categories">
      <button className={`catalog-chip ${category === '' ? 'active' : ''}`} onClick={() => setCategory('')}>全部</button>
      {categories.map(value => <button key={value} className={`catalog-chip ${category === value ? 'active' : ''}`} onClick={() => setCategory(value)}>{value}</button>)}
    </div>
    {filtered.length ? <div className="catalog-list">{filtered.map(item => {
      const support = itemSupport(item);
      return <button key={item.id} className="catalog-row" onClick={() => setDetailId(item.id)}>
        <CatalogMark item={item} />
        <span className="catalog-row-main"><strong>{item.name}</strong><small>{item.summary || item.description || item.vendor || ''}</small></span>
        <span className="catalog-row-meta"><span className="badge">{authLabel(item)}</span>{support !== 'native' ? <span className={`badge support-${support}`}>{support === 'oauth' ? 'OAuth' : '目录插件'}</span> : null}</span>
      </button>;
    })}</div> : <div className="catalog-empty">没有匹配的目录条目。</div>}
  </div>;
}
