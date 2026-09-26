import { useEffect, useState } from 'react';
import type { Context } from '@deepseek-ai/cordis';
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client';
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client';
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-documentpreview/client';
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-right/client';
import { createPlateEditor, Plate, PlateContent, useEditorVersion } from 'platejs/react';
import type { PlateEditor } from 'platejs/react';
import {
  BaseBasicMarksPlugin,
  BaseBasicBlocksPlugin,
  BaseBoldPlugin,
  BaseItalicPlugin,
  BaseUnderlinePlugin,
  BaseStrikethroughPlugin,
  BaseCodePlugin,
  BaseHeadingPlugin,
  BaseBlockquotePlugin,
  BaseHorizontalRulePlugin,
} from '@platejs/basic-nodes';

export const name = 'workdsh-plate-client';
export const inject = ['slots', 'documentPreviews'];

const plugins = [
  BaseBasicMarksPlugin,
  BaseBasicBlocksPlugin,
  BaseBoldPlugin,
  BaseItalicPlugin,
  BaseUnderlinePlugin,
  BaseStrikethroughPlugin,
  BaseCodePlugin,
  BaseHeadingPlugin,
  BaseBlockquotePlugin,
  BaseHorizontalRulePlugin,
];

type SlateContent = { type?: string; text?: string; children: unknown[] }[];

async function post<T>(endpoint: string, payload: Record<string, unknown> = {}): Promise<T> {
  const response = await fetch('/api/workdsh-plate', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ endpoint, ...payload }),
  });
  const body = await response.json();
  if (!response.ok || !body.ok) throw new Error(body.code ?? String(response.status));
  return body as T;
}

// SSE variant of post(): consumes data: frames, feeding text deltas to
// onText; throws on an error frame or a non-SSE (JSON) response.
async function streamPost(
  endpoint: string,
  payload: Record<string, unknown>,
  onText: (delta: string) => void,
): Promise<void> {
  const response = await fetch('/api/workdsh-plate', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ endpoint, ...payload }),
  });
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('text/event-stream')) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.code ?? `HTTP ${response.status}`);
  }
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const dataLine = frame.split('\n').find((line) => line.startsWith('data: '));
      if (dataLine) {
        const event = JSON.parse(dataLine.slice(6)) as { text?: string; error?: string };
        if (event.error) throw new Error(event.error);
        if (event.text) onText(event.text);
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
}

type DocMeta = { id: string; title: string; updatedAt: string };

const emptyContent: SlateContent = [{ type: 'p', children: [{ text: '' }] }];

function ToolbarButton(props: { label: string; active?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      className="plate-toolbar-btn"
      data-active={props.active ? 'true' : undefined}
      onMouseDown={(event) => { event.preventDefault(); props.onClick(); }}
      title={props.label}
    >
      {props.label}
    </button>
  );
}

// 汉化层 + M3：AI 动作菜单（润色/续写/扩写/缩写/纠错/翻译），全走
// ctx.llm.stream（/api/workdsh-plate ai-stream），遵循 agent-default-model。
const AI_ACTIONS = [
  { key: 'polish', label: '润色' },
  { key: 'continue', label: '续写' },
  { key: 'expand', label: '扩写' },
  { key: 'condense', label: '缩写' },
  { key: 'proofread', label: '纠错' },
  { key: 'translate', label: '翻译' },
] as const;

type AiActionKey = (typeof AI_ACTIONS)[number]['key'];

function PlateAiSection(props: { editor: PlateEditor; docId: string }) {
  const { editor, docId } = props;
  const [state, setState] = useState<{
    action: AiActionKey;
    busy: boolean;
    text: string;
    expanded: boolean;
    savedRange: typeof editor.selection;
    inserted: boolean;
    error: string | null;
  } | null>(null);

  const start = async (action: AiActionKey) => {
    // Selection is still live here: the buttons preventDefault on mousedown.
    const selection = editor.selection;
    const expanded = !!selection && !editor.api.isCollapsed(selection);
    const text = expanded
      ? editor.api.string(selection)
      : editor.api.string({ anchor: editor.api.start(editor, []), focus: editor.api.end(editor, []) });
    if (!text.trim()) {
      setState({ action, busy: false, text: '', expanded, savedRange: expanded ? selection : null, inserted: false, error: '没有可处理的文本，请先输入内容。' });
      return;
    }
    setState({ action, busy: true, text: '', expanded, savedRange: expanded ? selection : null, inserted: false, error: null });
    try {
      await streamPost('ai-stream', { docId, action, text }, (delta) => {
        setState((prev) => (prev ? { ...prev, text: prev.text + delta } : prev));
      });
      setState((prev) => (prev ? { ...prev, busy: false } : prev));
    } catch (error) {
      setState((prev) => (prev ? { ...prev, busy: false, error: String(error) } : prev));
    }
  };

  const insert = async () => {
    if (!state || state.busy || !state.text) return;
    if (state.expanded && state.savedRange) {
      editor.tf.select(state.savedRange);
      editor.tf.insertText(state.text);
    } else {
      editor.tf.select(editor.api.end(editor, []));
      editor.tf.insertText(`\n${state.text}`);
    }
    // AI 修改同样进入修订链，cause='ai' 与手动编辑区分。
    try {
      await post('rev-append', { docId, content: editor.children, cause: 'ai' });
      setState((prev) => (prev ? { ...prev, inserted: true } : prev));
    } catch (error) {
      setState((prev) => (prev ? { ...prev, error: String(error) } : prev));
    }
  };

  const busyLabel = state?.busy ? `${AI_ACTIONS.find((a) => a.key === state.action)?.label}中…` : null;

  return (
    <>
      {AI_ACTIONS.map((a) => (
        <button
          key={a.key}
          type="button"
          className="plate-ai-btn"
          disabled={state?.busy}
          onMouseDown={(event) => { event.preventDefault(); void start(a.key); }}
          title={`AI ${a.label}`}
        >
          {state?.busy && state.action === a.key ? '…' : a.label}
        </button>
      ))}
      {state ? (
        <div className="plate-ai-panel">
          {busyLabel ? <div className="plate-ai-status">{busyLabel}</div> : null}
          {state.error ? <div className="plate-error">{state.error}</div> : null}
          <textarea
            className="plate-ai-text"
            value={state.text}
            readOnly={state.busy}
            placeholder={state.busy ? 'AI 正在生成…' : 'AI 生成结果（可编辑后再写入）'}
            onChange={(event) => setState((prev) => (prev ? { ...prev, text: event.target.value, inserted: false } : prev))}
          />
          <div className="plate-ai-actions">
            <button type="button" disabled={state.busy || !state.text} onClick={() => void insert()}>
              {state.expanded ? '替换选区' : '插入文末'}
            </button>
            <button
              type="button"
              disabled={!state.text}
              onClick={() => { void navigator.clipboard.writeText(state.text).catch(() => {}); }}
            >
              复制
            </button>
            <button type="button" onClick={() => setState(null)}>关闭</button>
            {state.inserted ? <span className="plate-saved-at">已写入并保存</span> : null}
          </div>
        </div>
      ) : null}
    </>
  );
}

// Toolbar buttons must live INSIDE <Plate> so useEditorVersion() can resolve
// the Plate store from context and re-render on every editor change; without
// the subscription, active marks are evaluated once at mount and never update.
function PlateToolbarButtons(props: { editor: PlateEditor }) {
  useEditorVersion();
  const markActive = (key: string) => (props.editor.api.marks?.() ?? {})[key] === true;
  return (
    <>
      <ToolbarButton label="加粗" active={markActive('bold')} onClick={() => props.editor.tf.toggleMark('bold')} />
      <ToolbarButton label="斜体" active={markActive('italic')} onClick={() => props.editor.tf.toggleMark('italic')} />
      <ToolbarButton label="下划线" active={markActive('underline')} onClick={() => props.editor.tf.toggleMark('underline')} />
      <ToolbarButton label="删除线" active={markActive('strikethrough')} onClick={() => props.editor.tf.toggleMark('strikethrough')} />
      <ToolbarButton label="代码" active={markActive('code')} onClick={() => props.editor.tf.toggleMark('code')} />
      <span className="plate-toolbar-sep" />
      <ToolbarButton label="标题 1" onClick={() => props.editor.tf.toggleBlock('h1')} />
      <ToolbarButton label="标题 2" onClick={() => props.editor.tf.toggleBlock('h2')} />
      <ToolbarButton label="标题 3" onClick={() => props.editor.tf.toggleBlock('h3')} />
      <ToolbarButton label="引用" onClick={() => props.editor.tf.toggleBlock('blockquote')} />
      <ToolbarButton label="分隔线" onClick={() => props.editor.tf.toggleBlock('hr')} />
    </>
  );
}

function PlateDocEditor(props: { docId: string; title: string; content: SlateContent }) {
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const editor = useState(() => createPlateEditor({ plugins, value: props.content }))[0];

  const save = async () => {
    setSaving(true);
    try {
      await post('rev-append', { docId: props.docId, content: editor.children as SlateContent, cause: 'edit' });
      setSavedAt(new Date().toLocaleTimeString('zh-CN'));
    } catch (error) {
      console.error('[workdsh-plate] save failed', error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="plate-doc-editor">
      <Plate editor={editor}>
        <div className="plate-toolbar">
          <PlateToolbarButtons editor={editor} />
          <span className="plate-toolbar-sep" />
          <PlateAiSection editor={editor} docId={props.docId} />
          <button type="button" className="plate-toolbar-save" disabled={saving} onClick={() => void save()}>
            {saving ? '保存中…' : '保存'}
          </button>
          {savedAt ? <span className="plate-saved-at">已保存 {savedAt}</span> : null}
        </div>
        <div className="plate-canvas">
          <PlateContent placeholder="开始输入…" className="plate-content" />
        </div>
      </Plate>
    </div>
  );
}

function PlateDocumentsPanel() {
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [opened, setOpened] = useState<{ docId: string; title: string; content: SlateContent } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const result = await post<{ documents: DocMeta[] }>('docs-list');
      setDocs(result.documents);
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => { void refresh(); }, []);

  const create = async () => {
    setBusy(true);
    try {
      const result = await post<{ doc: DocMeta; head: { slateJson: SlateContent } }>('doc-create', {
        title: '未命名文档',
        content: emptyContent,
      });
      setOpened({ docId: result.doc.id, title: result.doc.title, content: result.head.slateJson });
      void refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const open = async (docId: string) => {
    setBusy(true);
    try {
      const result = await post<{ doc: DocMeta; head: { slateJson: SlateContent } }>('doc-open', { docId });
      setOpened({ docId: result.doc.id, title: result.doc.title, content: result.head.slateJson });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const exportDoc = async (docId: string) => {
    setBusy(true);
    try {
      const result = await post<{ doc: DocMeta; head: { slateJson: SlateContent } }>('doc-export', { docId });
      const payload = {
        format: 'workdsh-plate',
        version: 1,
        exportedAt: new Date().toISOString(),
        title: result.doc.title,
        content: result.head.slateJson,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${result.doc.title.replace(/[\\/:*?"<>|]/g, '_')}.plate`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (opened) {
    return (
      <div className="plate-doc-editor">
        <div className="plate-doc-head">
          <button type="button" className="plate-back" onClick={() => setOpened(null)}>← 文档列表</button>
          <span className="plate-doc-title">{opened.title}</span>
          <button type="button" className="plate-export" disabled={busy} onClick={() => void exportDoc(opened.docId)}>导出 .plate</button>
        </div>
        <PlateDocEditor docId={opened.docId} title={opened.title} content={opened.content} />
      </div>
    );
  }

  return (
    <div className="plate-docs">
      <div className="plate-doc-head">
        <span className="plate-doc-title">AI 富文本文档</span>
        <button type="button" className="plate-new" disabled={busy} onClick={() => void create()}>
          ＋ 新建文档
        </button>
      </div>
      {error ? <div className="plate-error">{error}</div> : null}
      {docs.length === 0 ? (
        <div className="plate-empty">还没有文档，点「新建文档」开始。</div>
      ) : (
        <ul className="plate-doc-list">
          {docs.map((doc) => (
            <li key={doc.id}>
              <button type="button" onClick={() => void open(doc.id)}>
                <span className="plate-item-title">{doc.title}</span>
                <span className="plate-item-time">{new Date(doc.updatedAt).toLocaleString('zh-CN')}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Self-contained styling: the plugin ships no CSS build step, so the bundle
// injects one <style> tag at apply time.
function injectStyles(): void {
  if (document.getElementById('workdsh-plate-style')) return;
  const style = document.createElement('style');
  style.id = 'workdsh-plate-style';
  style.textContent = `
.plate-docs { padding: 12px 16px; }
.plate-doc-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.plate-doc-title { font-weight: 600; font-size: 15px; }
.plate-new, .plate-back, .plate-export { padding: 4px 10px; border: 1px solid #d1d5db; border-radius: 6px; background: #fff; cursor: pointer; }
.plate-doc-list { list-style: none; margin: 0; padding: 0; }
.plate-doc-list li button { width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 8px; background: #fff; cursor: pointer; }
.plate-item-time { color: #9ca3af; font-size: 12px; }
.plate-empty { color: #9ca3af; padding: 24px 0; text-align: center; }
.plate-error { color: #dc2626; margin: 4px 0; }
.plate-doc-editor { display: flex; flex-direction: column; min-height: 320px; }
.plate-toolbar { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; padding: 6px 8px; border-bottom: 1px solid #e5e7eb; }
.plate-toolbar-btn, .plate-ai-btn { padding: 4px 10px; border: 1px solid #d1d5db; border-radius: 6px; background: #fff; cursor: pointer; font-size: 13px; }
.plate-toolbar-btn:hover, .plate-ai-btn:hover { background: #f3f4f6; }
.plate-toolbar-btn[data-active="true"] { background: #e0e7ff; border-color: #6366f1; color: #4338ca; }
.plate-toolbar-sep { width: 1px; height: 18px; background: #e5e7eb; margin: 0 4px; }
.plate-toolbar-save { margin-left: auto; padding: 4px 12px; border: 1px solid #6366f1; border-radius: 6px; background: #6366f1; color: #fff; cursor: pointer; }
.plate-saved-at { color: #16a34a; font-size: 12px; }
.plate-canvas { padding: 16px; overflow-y: auto; }
.plate-content { min-height: 260px; outline: none; }
.plate-ai-panel { flex-basis: 100%; display: flex; flex-direction: column; gap: 6px; padding: 8px; border: 1px solid #c7d2fe; border-radius: 8px; background: #f8faff; margin-top: 4px; }
.plate-ai-text { width: 100%; min-height: 90px; font-size: 13px; line-height: 1.6; border: 1px solid #d1d5db; border-radius: 6px; padding: 8px; box-sizing: border-box; }
.plate-ai-actions { display: flex; gap: 6px; align-items: center; }
.plate-ai-actions button { padding: 4px 10px; border: 1px solid #d1d5db; border-radius: 6px; background: #fff; cursor: pointer; }
.plate-ai-status { font-size: 12px; color: #6366f1; }
`;
  document.head.appendChild(style);
}

export function apply(ctx: Context): void {
  injectStyles();
  // S5-a: claim the .plate extension in the document preview registry.
  ctx.effect(() =>
    ctx.documentPreviews.register({
      id: 'workdsh-plate',
      extensions: ['plate'],
      title: () => 'Plate 文档',
      priority: 'builtin',
      loading: 'bytes-complete',
    }),
  );
  // S5-b: mount into the right-sidebar document tab, parallel to workdsh-office.
  ctx.slots.inject('sidebar.right.tab.document', () =>
    ctx.slots.register(
      { name: 'sidebar.right.tab.document', key: 'workdsh-plate' },
      PlateDocumentsPanel,
    ),
  );
  // Deterministic product entry: a left-nav page (main panel + panellist
  // entry), the same pattern as the bundle's DiagnosticsPanel.
  ctx.slots.inject('main', () =>
    ctx.slots.register({ name: 'main', key: 'workdsh-plate' }, PlateDocumentsPanel),
  );
  ctx.slots.inject('sidebar.panellist', () =>
    ctx.slots.register({
      name: 'sidebar.panellist', id: 'workdsh-plate', label: 'Plate 文档', order: 70,
    }, () => <span className="plate-nav-mark">📝</span>),
  );
}
