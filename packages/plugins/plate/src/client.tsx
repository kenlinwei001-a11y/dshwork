import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent, ClipboardEvent } from 'react';
import type { Context } from '@deepseek-ai/cordis';
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client';
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client';
import type { DocumentPreviewProps } from '@deepseek-ai/dsh-client-ui-sidebar-documentpreview/client';
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-right/client';
import type { PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots';
import type { ISessions } from '@deepseek-ai/dsh-api-session-controller/client';
import { Button, SegmentedControl } from '@deepseek-ai/dsh-client-ui-primitives';
import { createPlateEditor, Plate, PlateContent, PlateElement, useEditorVersion } from 'platejs/react';
import type { PlateEditor } from 'platejs/react';

// v1.3.0：右侧活编辑器 tab 的导航参数（镜像 office 的 workdsh-office-live）。
declare module '@deepseek-ai/dsh-client-ui-sidebar-right/client' {
  interface SidebarRightTabParamsMap {
    'workdsh-plate-live': { documentId?: string };
  }
}
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
import { insertImage } from '@platejs/media';
// v53 渲染挂载 = plugin.withComponent(组件)（core docstring 官方范式），
// 不是 render 字段；Image primitive 从 ElementProvider 上下文读 url。
import { Image, ImagePlugin } from '@platejs/media/react';

const ImageElement = (props: { element: { url?: string }; children?: unknown }) => (
  <PlateElement {...props}>
    <Image />
    {props.children as never}
  </PlateElement>
);

const ImageElementPlugin = ImagePlugin.withComponent(ImageElement as never);

export const name = 'workdsh-plate-client';
export const inject = ['slots', 'documentPreviews', 'sidebarRightTabs', 'sidebarRight', 'sessions'];

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
  ImageElementPlugin,
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

function ToolbarButton(props: { label: string; active?: boolean; onClick: () => void }) {
  return (
    <Button
      type="button"
      variant="toolbar"
      size="sm"
      className={props.active ? 'plate-btn-active' : undefined}
      data-active={props.active ? 'true' : undefined}
      onMouseDown={(event) => { event.preventDefault(); props.onClick(); }}
      title={props.label}
    >
      {props.label}
    </Button>
  );
}

// S5-b：.plate 文件打开路径。documentPreviews 声明由预览 owner 按扩展名
// 路由到本组件（keyed slot key === definition id），content.kind 'bytes'
// 时拿到完整文件字节；解析后只读渲染 + 一键导入到 Plate 文档域。
function PlateReadOnly(props: { content: SlateContent }) {
  const editor = useState(() => createPlateEditor({ plugins, value: props.content }))[0];
  return (
    <div className="plate-file-body">
      <Plate editor={editor}>
        <PlateContent readOnly className="plate-content" />
      </Plate>
    </div>
  );
}

function PlateFilePreview(props: DocumentPreviewProps & { onImported?: (docId: string) => void }) {
  const [parsed, setParsed] = useState<{ title: string; content: SlateContent } | null>(null);
  const [error, setError] = useState('');
  const [importing, setImporting] = useState(false);
  const [imported, setImported] = useState<string | null>(null);
  const bytes = props.content.kind === 'bytes' ? props.content.data : null;

  useEffect(() => {
    setError('');
    setParsed(null);
    setImported(null);
    if (!bytes) return;
    try {
      const doc = JSON.parse(new TextDecoder().decode(bytes)) as {
        format?: string; title?: string; content?: SlateContent;
      };
      if (doc.format !== 'workdsh-plate' || !Array.isArray(doc.content)) {
        throw new Error('不是有效的 workdsh-plate 文件');
      }
      const name = decodeURIComponent(props.resourceAddress).split('/').pop()?.split(/[?#]/)[0] ?? '未命名';
      setParsed({
        title: typeof doc.title === 'string' && doc.title.trim() ? doc.title : name.replace(/\.plate$/i, ''),
        content: doc.content,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [bytes, props.resourceAddress]);

  const doImport = async () => {
    if (!parsed || importing) return;
    setImporting(true);
    try {
      const result = await post<{ doc: DocMeta }>('doc-import', { title: parsed.title, content: parsed.content });
      setImported(result.doc.id);
      // 面板已移除：导入后直接打开右侧活编辑器，这也是手动进入编辑器的入口。
      props.onImported?.(result.doc.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="plate-file-preview">
      {error ? <div className="plate-error">{error}</div> : null}
      {parsed ? (
        <>
          <div className="plate-file-head">
            <span className="plate-doc-title">{parsed.title}</span>
            <Button type="button" variant="outline" size="sm" disabled={importing || !!imported} onClick={() => void doImport()}>
              {importing ? '导入中…' : imported ? '已导入到 Plate 文档' : '导入到 Plate 文档'}
            </Button>
          </div>
          <PlateReadOnly content={parsed.content} />
        </>
      ) : error ? null : (
        <div className="plate-empty">在文件列表中选择一个 .plate 文件查看内容。</div>
      )}
    </div>
  );
}

// v1.4.0：docx 预览工具条动作——「用 PlateAI 打开」。服务端读文件解析
// 成 Slate JSON 导入 plate 域，再开右侧活编辑器继续编辑。仅 docx 渲染。
function OpenInPlateAction(openLiveEditor: (documentId: string) => void) {
  return function OpenInPlateActionEntry(props: { absolutePath: string }) {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const isDocx = props.absolutePath.toLowerCase().endsWith('.docx');
    if (!isDocx) return null;
    const open = async () => {
      setBusy(true);
      setError('');
      try {
        const result = await post<{ doc: DocMeta }>('docx-import', { path: props.absolutePath });
        openLiveEditor(result.doc.id);
      } catch (e) {
        setError(String(e));
      } finally {
        setBusy(false);
      }
    };
    return (
      <>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="plate-open-in-plate"
          disabled={busy}
          onClick={() => void open()}
        >
          {busy ? '转换中…' : '用 PlateAI 打开'}
        </Button>
        {error ? <span className="plate-error">{error}</span> : null}
      </>
    );
  };
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
        <Button
          key={a.key}
          type="button"
          variant="toolbar"
          size="sm"
          disabled={state?.busy}
          onMouseDown={(event) => { event.preventDefault(); void start(a.key); }}
          title={`AI ${a.label}`}
        >
          {state?.busy && state.action === a.key ? '…' : a.label}
        </Button>
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
            <Button type="button" variant="outline" size="sm" disabled={state.busy || !state.text} onClick={() => void insert()}>
              {state.expanded ? '替换选区' : '插入文末'}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!state.text}
              onClick={() => { void navigator.clipboard.writeText(state.text).catch(() => {}); }}
            >
              复制
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setState(null)}>关闭</Button>
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

// M5：内嵌图片（附件资产 v1）。图片以 data URL 写入 image 节点，文档自
// 包含、导出 .plate 自然携带；单图 ≤1.5MB 客户端拦截，修订总上限服务端拦截。
const MAX_IMAGE_BYTES = 1_500_000;

function readImageFile(file: File, editor: PlateEditor, onStatus: (status: string) => void): void {
  if (!file.type.startsWith('image/')) {
    onStatus('只支持图片文件');
    return;
  }
  if (file.size > MAX_IMAGE_BYTES) {
    onStatus('图片超过 1.5MB 上限');
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    insertImage(editor, String(reader.result));
    onStatus(`已插入 ${file.name}`);
  };
  reader.onerror = () => onStatus('读取图片失败');
  reader.readAsDataURL(file);
}

function PlateImageButton(props: { editor: PlateEditor }) {
  const [status, setStatus] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ''; // 允许连续选择同一文件
    if (file) readImageFile(file, props.editor, setStatus);
  };
  return (
    <>
      <Button
        type="button"
        variant="toolbar"
        size="sm"
        title="插入图片"
        onMouseDown={(event) => { event.preventDefault(); inputRef.current?.click(); }}
      >
        插图
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        data-plate-file-input="true"
        onChange={onChange}
      />
      {status ? <span className="plate-image-status">{status}</span> : null}
    </>
  );
}

function PlateDocEditor(props: { docId: string; title: string; content: SlateContent }) {
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [imageStatus, setImageStatus] = useState('');
  const editor = useState(() => createPlateEditor({ plugins, value: props.content }))[0];

  // 粘贴图片：截获剪贴板里的图片文件，走与插图按钮相同的 data URL 管道。
  const handlePaste = (event: ClipboardEvent<HTMLDivElement>) => {
    const items = event.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (item.kind === 'file' && item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          event.preventDefault();
          readImageFile(file, editor, setImageStatus);
          return;
        }
      }
    }
  };

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
          <span className="plate-toolbar-sep" />
          <PlateImageButton editor={editor} />
          <Button type="button" variant="primary" size="sm" disabled={saving} onClick={() => void save()}>
            {saving ? '保存中…' : '保存'}
          </Button>
          {savedAt ? <span className="plate-saved-at">已保存 {savedAt}</span> : null}
          {imageStatus ? <span className="plate-image-status">{imageStatus}</span> : null}
        </div>
        <div className="plate-canvas" onPaste={handlePaste}>
          <PlateContent placeholder="开始输入…" className="plate-content" />
        </div>
      </Plate>
    </div>
  );
}

// 导出 .plate 的共享实现：doc-export 拉 head 修订 → 组装下载（列表与活编辑器共用）。
async function exportPlate(docId: string): Promise<void> {
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
}

// v1.3.0：缺省编辑器=PlateAI 时的右侧活编辑器。plate_open 落服务端 pending 队列，
// 客户端轮询命中后 openTabIn 打开本 tab；params.documentId → doc-open → 复用 PlateDocEditor。
type PlateLivePageProps = PropsRuntime<'sidebar.right.pane.tab'>;

function PlateLivePage(props: PlateLivePageProps) {
  const info = props.useTabInfo();
  const params = info.tab.navigation.params as { documentId?: string } | undefined;
  const docId = params?.documentId;
  const [state, setState] = useState<{ docId: string; title: string; content: SlateContent; revision: number } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  // 「缺省文档编辑器」开关（原面板头部按钮，v1.4.0 随面板移除搬到这里）：
  // 读服务端设置，点击乐观切换、失败回滚。
  const [defaultEditor, setDefaultEditor] = useState<'office' | 'plate' | null>(null);
  const [editorError, setEditorError] = useState('');
  useEffect(() => {
    void post<{ editor: 'office' | 'plate' }>('get-default-editor')
      .then((r) => setDefaultEditor(r.editor))
      .catch(() => setDefaultEditor('office'));
  }, []);
  const changeDefaultEditor = async (editor: 'office' | 'plate') => {
    if (defaultEditor === null || editor === defaultEditor) return;
    const previous = defaultEditor;
    setDefaultEditor(editor);
    setEditorError('');
    try {
      await post('set-default-editor', { editor });
    } catch (e) {
      setDefaultEditor(previous);
      setEditorError(String(e));
    }
  };
  // 已渲染内容的 JSON 指纹：agent 新提交（plate_edit）后 diff 命中即重载。
  const renderedRef = useRef('');

  useEffect(() => {
    setState(null);
    setError('');
    renderedRef.current = '';
    if (!docId) return;
    let cancelled = false;
    let first = true;
    const load = async () => {
      try {
        const result = await post<{ doc: DocMeta; head: { slateJson: SlateContent; seq: number } }>('doc-open', { docId });
        if (cancelled) return;
        const headJson = JSON.stringify(result.head.slateJson);
        if (headJson !== renderedRef.current) {
          // 用户正在编辑器里输入时不重载，保护本地未保存编辑（v1 保守策略）。
          const editing = document.activeElement !== null
            && document.querySelector('.plate-live-page')?.contains(document.activeElement);
          if (!editing) {
            renderedRef.current = headJson;
            setState({ docId, title: result.doc.title, content: result.head.slateJson, revision: result.head.seq });
          }
        }
      } catch (e) {
        if (!cancelled && first) setError(String(e));
      } finally {
        if (!cancelled && first) {
          first = false;
          setBusy(false);
        }
      }
    };
    setBusy(true);
    void load();
    // 活编辑器的"活"：2.5s 轮询 head，agent 的每次 plate_edit 落地即上屏。
    const timer = setInterval(() => void load(), 2500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [docId]);

  return (
    <div className="plate-live-page">
      <div className="plate-doc-head">
        <span className="plate-doc-title">{state ? state.title : '正在打开…'}</span>
        <div className="plate-live-head-actions">
          <SegmentedControl
            id="plate-editor-mode"
            className="plate-editor-mode"
            value={defaultEditor ?? 'office'}
            disabled={defaultEditor === null}
            label="AI 写文档的缺省编辑器"
            options={[
              { value: 'office', label: 'Word' },
              { value: 'plate', label: 'PlateAI' },
            ]}
            onChange={(editor) => void changeDefaultEditor(editor)}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!state || busy}
            onClick={() => {
              if (state) void exportPlate(state.docId).catch((e) => setError(String(e)));
            }}
          >
            导出 .plate
          </Button>
        </div>
      </div>
      {error ? <div className="plate-error">{error}</div> : null}
      {editorError ? <div className="plate-error">{editorError}</div> : null}
      {state ? (
        <PlateDocEditor key={state.revision} docId={state.docId} title={state.title} content={state.content} />
      ) : (
        <div className="plate-empty">{busy ? '正在打开…' : '等待 AI 打开文档…'}</div>
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
.plate-doc-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.plate-doc-title { font-weight: 600; font-size: 15px; }
.plate-live-head-actions { display: flex; gap: 8px; align-items: center; }
.plate-live-page { display: flex; flex-direction: column; min-height: 100%; }
.plate-empty { color: #9ca3af; padding: 24px 0; text-align: center; }
.plate-error { color: #dc2626; margin: 4px 0; }
.plate-doc-editor { display: flex; flex-direction: column; min-height: 320px; }
.plate-toolbar { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; padding: 6px 8px; border-bottom: 1px solid #e5e7eb; }
.plate-btn-active { background: #e0e7ff !important; color: #4338ca !important; }
.plate-toolbar-sep { width: 1px; height: 18px; background: #e5e7eb; margin: 0 4px; }
.plate-saved-at { color: #16a34a; font-size: 12px; }
.plate-canvas { padding: 16px; overflow-y: auto; }
.plate-content { min-height: 260px; outline: none; }
.plate-ai-panel { flex-basis: 100%; display: flex; flex-direction: column; gap: 6px; padding: 8px; border: 1px solid #c7d2fe; border-radius: 8px; background: #f8faff; margin-top: 4px; }
.plate-ai-text { width: 100%; min-height: 90px; font-size: 13px; line-height: 1.6; border: 1px solid #d1d5db; border-radius: 6px; padding: 8px; box-sizing: border-box; }
.plate-ai-actions { display: flex; gap: 6px; align-items: center; }
.plate-ai-status { font-size: 12px; color: #6366f1; }
.plate-file-preview { padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }
.plate-file-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.plate-file-body { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; background: #fff; }
.plate-image-status { color: #6366f1; font-size: 12px; }
.plate-content img { max-width: 100%; height: auto; border-radius: 6px; }
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
  // plate_open 的 pending 打开：500ms 轮询服务端队列，命中即 openTabIn。
  const lifetime = new AbortController();
  const currentSessionId = () => {
    const state = (ctx.sessions as unknown as ISessions).list.getSnapshot();
    // retainedBy 的声明键集不含 mainView（office 同款派生），显式窄化。
    const retainedBy = (row: unknown) => ((row as { retainedBy?: { mainView?: number } }).retainedBy ?? {}).mainView ?? 0;
    return Object.values(state.byId).find((row) => retainedBy(row) > 0)?.id;
  };
  const openLiveEditor = (documentId: string) => {
    const sessionId = currentSessionId();
    if (!sessionId) return;
    ctx.sidebarRight.openTabIn(sessionId as never, 'workdsh-plate-live', {
      params: { documentId },
    });
  };

  // S5-b: the document-tab renderer for .plate files (key matches the
  // documentPreviews definition id above; the owner delivers file bytes).
  // v1.4.0：面板已移除，导入成功后直接打开右侧活编辑器作为手动入口。
  ctx.slots.inject('sidebar.right.tab.document', () =>
    ctx.slots.register(
      { name: 'sidebar.right.tab.document', key: 'workdsh-plate' },
      (props: DocumentPreviewProps) => <PlateFilePreview {...props} onImported={openLiveEditor} />,
    ),
  );

  // v1.4.0：文档预览工具条的「用 PlateAI 打开」动作（框架 list 槽，owner
  // 给 absolutePath；docx 之外的扩展名返回 null 即不渲染）。Word 文档点
  // 开预览后可一键转成 Plate 文档并在右侧活编辑器继续编辑。
  ctx.slots.inject('sidebar.right.tab.document.actions', () =>
    ctx.slots.register(
      {
        name: 'sidebar.right.tab.document.actions',
        id: 'workdsh-plate-open',
        order: 10,
        label: '用 PlateAI 打开',
      },
      OpenInPlateAction(openLiveEditor),
    ),
  );

  // v1.3.0：右侧活编辑器 tab（与 office 的 workdsh-office-live 平行两阶段注册）。
  ctx.effect(() =>
    ctx.sidebarRightTabs.register({
      id: 'workdsh-plate-live',
      kind: 'workdsh-plate-live',
      title: () => 'Plate 文档 · 实时编辑',
      guide: [
        {
          id: 'workdsh-plate-live',
          order: 46,
          title: () => 'Plate 文档',
          description: () => '查看并编辑 AI 正在编写的 Plate 文档',
        },
      ],
    }),
  );
  ctx.slots.inject('sidebar.right.pane.tab', () =>
    ctx.slots.register(
      { name: 'sidebar.right.pane.tab', key: 'workdsh-plate-live', inject: () => ({}) },
      PlateLivePage,
    ),
  );
  ctx.effect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const seen = new Set<string>();
    async function poll() {
      const sessionId = currentSessionId();
      try {
        if (sessionId && document.visibilityState !== 'hidden') {
          const result = await post<{ requests: { sessionId: string; documentId: string; requestId: string }[] }>(
            'plate-pending',
            { sessionId: String(sessionId) },
          );
          for (const request of result.requests) {
            if (!seen.has(request.requestId)) {
              ctx.sidebarRight.openTabIn(sessionId as never, 'workdsh-plate-live', {
                params: { documentId: request.documentId },
              });
              seen.add(request.requestId);
            }
          }
        }
      } catch {
        /* 未绑定会话/宿主暂不可用不影响对话。 */
      } finally {
        if (!lifetime.signal.aborted) {
          timer = setTimeout(poll, document.visibilityState === 'hidden' ? 5000 : 500);
        }
      }
    }
    void poll();
    return () => {
      lifetime.abort();
      clearTimeout(timer);
    };
  });
}
