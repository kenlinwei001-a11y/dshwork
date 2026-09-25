import { useEffect, useState } from 'react';
import type { Context } from '@deepseek-ai/cordis';
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client';
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-documentpreview/client';
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-right/client';
import { createPlateEditor, Plate, PlateContent } from 'platejs/react';
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
      <div className="plate-toolbar">
        <ToolbarButton label="加粗" active={editor.api.isMarkActive?.('bold')} onClick={() => editor.api.mark?.toggle('bold')} />
        <ToolbarButton label="斜体" active={editor.api.isMarkActive?.('italic')} onClick={() => editor.api.mark?.toggle('italic')} />
        <ToolbarButton label="下划线" active={editor.api.isMarkActive?.('underline')} onClick={() => editor.api.mark?.toggle('underline')} />
        <ToolbarButton label="删除线" active={editor.api.isMarkActive?.('strikethrough')} onClick={() => editor.api.mark?.toggle('strikethrough')} />
        <ToolbarButton label="代码" active={editor.api.isMarkActive?.('code')} onClick={() => editor.api.mark?.toggle('code')} />
        <span className="plate-toolbar-sep" />
        <ToolbarButton label="标题 1" onClick={() => editor.api.block?.toggle('h1')} />
        <ToolbarButton label="标题 2" onClick={() => editor.api.block?.toggle('h2')} />
        <ToolbarButton label="标题 3" onClick={() => editor.api.block?.toggle('h3')} />
        <ToolbarButton label="引用" onClick={() => editor.api.block?.toggle('blockquote')} />
        <ToolbarButton label="分隔线" onClick={() => editor.api.block?.toggle('hr')} />
        <span className="plate-toolbar-sep" />
        <button type="button" className="plate-toolbar-save" disabled={saving} onClick={() => void save()}>
          {saving ? '保存中…' : '保存'}
        </button>
        {savedAt ? <span className="plate-saved-at">已保存 {savedAt}</span> : null}
      </div>
      <div className="plate-canvas">
        <Plate editor={editor}>
          <PlateContent placeholder="开始输入…" className="plate-content" />
        </Plate>
      </div>
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

  if (opened) {
    return (
      <div className="plate-doc-editor">
        <div className="plate-doc-head">
          <button type="button" className="plate-back" onClick={() => setOpened(null)}>← 文档列表</button>
          <span className="plate-doc-title">{opened.title}</span>
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

export function apply(ctx: Context): void {
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
}
