import * as React from 'react';
import type { Context } from '@deepseek-ai/cordis';

/**
 * WorkDSH-owned ".dxf" document preview for the local CraftCAD app.
 *
 * The CraftCAD panel plugin is a prebuilt local package: its DXF body used to
 * live only in its dist/client.js and was overwritten whenever that package was
 * rebuilt. This module keeps the preview in the shell instead, so updating or
 * reinstalling the panel cannot remove it. It is registered only when the
 * panel is present in the client inventory; without it the generic text
 * preview remains unchanged.
 */

const CRAFT_URL = 'http://127.0.0.1:8080/';
const CRAFT_ORIGIN = 'http://127.0.0.1:8080';
const CHANNEL = 'craftcad-embed';
const PREVIEW_ID = 'workdsh/craftcad-dxf';

const h = React.createElement;

const buttonStyle: React.CSSProperties = {
  padding: '5px 10px',
  borderRadius: 6,
  border: '1px solid rgba(127,127,127,.35)',
  background: 'rgba(127,127,127,.12)',
  color: 'inherit',
  font: 'inherit',
  cursor: 'pointer',
  whiteSpace: 'nowrap',
};
const primaryStyle: React.CSSProperties = {
  ...buttonStyle,
  background: '#2f6fed',
  borderColor: '#2f6fed',
  color: '#fff',
};

type DxfContent = { kind?: string; text?: string; eof?: boolean };
type DxfProps = { resourceAddress?: unknown; content?: DxfContent };

function baseName(address: unknown): string {
  const s = String(address ?? '');
  const cut = s.lastIndexOf('/');
  const raw = cut >= 0 ? s.slice(cut + 1) : s;
  try { return decodeURIComponent(raw) || 'drawing.dxf'; } catch { return raw || 'drawing.dxf'; }
}

function downloadText(text: string, name: string): void {
  const blob = new Blob([text], { type: 'application/dxf' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name || 'drawing.dxf';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

function DxfDocumentBody(props: DxfProps) {
  const content = props?.content;
  const name = baseName(props?.resourceAddress);
  const text = content && content.kind === 'text' ? content.text : null;
  const complete = !!(content && content.kind === 'text' && content.eof);
  const [ready, setReady] = React.useState(false);
  const [status, setStatus] = React.useState('');
  const [error, setError] = React.useState('');
  const iframeRef = React.useRef<HTMLIFrameElement | null>(null);
  const readyRef = React.useRef(false);
  const nameRef = React.useRef(name);
  const textRef = React.useRef<string | null>(null);
  const sentRef = React.useRef<string | null>(null);

  nameRef.current = name;
  textRef.current = complete && text !== undefined ? text : null;

  const postToFrame = React.useCallback((msg: Record<string, unknown>) => {
    const frame = iframeRef.current;
    if (frame?.contentWindow) {
      frame.contentWindow.postMessage({ channel: CHANNEL, ...msg }, CRAFT_ORIGIN);
    }
  }, []);

  const flush = React.useCallback(() => {
    const drawing = textRef.current;
    if (!readyRef.current || !drawing || sentRef.current === drawing) return;
    sentRef.current = drawing;
    postToFrame({ type: 'open', name: nameRef.current, text: drawing });
  }, [postToFrame]);

  React.useEffect(() => {
    const onMessage = (ev: MessageEvent) => {
      if (ev.origin !== CRAFT_ORIGIN) return;
      const d = (ev.data ?? {}) as Record<string, unknown>;
      if (d.channel !== CHANNEL) return;
      if (d.type === 'ready') {
        readyRef.current = true;
        setReady(true);
        flush();
      } else if (d.type === 'opened') {
        setStatus(`${String(d.name ?? nameRef.current)} · ${Number(d.entities ?? 0)} 个对象 · ${Number(d.layers ?? 0)} 个图层`);
        setError('');
      } else if (d.type === 'save') {
        downloadText(String(d.text ?? ''), String(d.name ?? nameRef.current));
        postToFrame({ type: 'saved' });
        setStatus(`已导出副本 · ${Number(d.entities ?? 0)} 个对象（浏览器不能直接写回工作区文件）`);
      } else if (d.type === 'error') {
        setError(`CraftCAD：${String(d.message ?? '未知错误')}`);
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [flush, postToFrame]);

  React.useEffect(() => {
    if (ready) flush();
  }, [ready, complete, text, flush]);

  return h('div', {
    style: { display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, boxSizing: 'border-box' },
  },
    h('div', {
      style: { display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderBottom: '1px solid rgba(127,127,127,.25)', flexWrap: 'wrap' },
    },
      h('span', { style: { fontWeight: 600, maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, title: name }, name),
      h('button', {
        onClick: () => postToFrame({ type: 'save-request' }),
        disabled: !ready,
        style: primaryStyle,
        title: '在 CraftCAD 里另存为 DXF 副本',
      }, '另存副本'),
      !ready && h('button', {
        onClick: () => {
          readyRef.current = false;
          sentRef.current = null;
          setReady(false);
          postToFrame({ type: 'ping' });
        },
        style: buttonStyle,
      }, '重新连接'),
      h('span', {
        style: { flex: 1, minWidth: 100, fontSize: 12, opacity: 0.7, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
      }, status || (complete ? '正在把图纸交给 CraftCAD…' : '正在读取图纸…')),
    ),
    error && h('div', { style: { padding: '6px 10px', fontSize: 12, color: '#b42318', background: 'rgba(180,35,24,.08)' } }, error),
    h('iframe', {
      ref: iframeRef,
      src: CRAFT_URL,
      title: 'CraftCAD 图纸',
      style: { flex: 1, minHeight: 0, width: '100%', border: 0, background: '#111' },
      onLoad: () => postToFrame({ type: 'ping' }),
    }),
  );
}

/** Register the CraftCAD DXF document implementation when the panel is present. */
export function installCraftCadDxfPreview(ctx: Context): void {
  // Inject the preview service lazily: the WorkDSH shell must keep loading
  // even on a host that has no document-preview service.
  (ctx as unknown as { inject(names: string[], callback: (scope: any) => void): void }).inject(['documentPreviews'], (scope) => {
    const previews = scope.documentPreviews as { register(spec: unknown): unknown } | undefined;
    if (typeof previews?.register !== 'function') return;
    scope.effect(() => previews.register({
      id: PREVIEW_ID,
      extensions: ['dxf'],
      priority: 'extension',
      title: () => 'CraftCAD 图纸',
      loading: 'text-pages',
      wrap: false,
    }) as () => void, 'workdsh.craftcad-dxf-preview');
    (scope.slots as unknown as { inject(name: string, register: () => unknown): void }).inject('sidebar.right.tab.document', () =>
      (scope.slots as unknown as { register(spec: unknown, component: unknown): unknown }).register({
        name: 'sidebar.right.tab.document',
        key: PREVIEW_ID,
        inject: () => ({}),
      }, DxfDocumentBody));
  });
}
