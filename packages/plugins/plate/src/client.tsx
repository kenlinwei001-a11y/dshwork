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
import { BlockSelectionPlugin } from '@platejs/selection/react';
import { BoldIcon, Code2Icon, ItalicIcon, StrikethroughIcon, UnderlineIcon } from 'lucide-react';
import {
  aiChatPlugin,
  aiLeafPlugin,
  aiNativeCss,
  markdownPlugin,
  setAiAppliedHandler,
  suggestionPlugin,
} from './ai-native.js';
// v1.6.0：工具栏换官方 playground 那套（图标按钮 + 分组 + 「转换为」下拉 + 悬浮提示）。
import {
  AIToolbarButton,
  HrToolbarButton,
  ImageToolbarButton,
  MarkToolbarButton,
  Toolbar,
  ToolbarGroup,
  TurnIntoToolbarButton,
  toolbarNativeCss,
} from './toolbar-native.js';
// v1.7.0：补上官方的 "/" 斜杠菜单（SlashKit）。官方把 AI 放在 "/" 菜单第一组，
// 这是编辑器表明「我是 AI 编辑器」的地方——此前只搬了 mod+j 那条快捷键，
// 敲 "/" 只会插入字面斜杠，编辑器看着和 Word 没区别。
import { SlashInputElement, slashNativeCss } from './slash-native.js';
import { SlashInputPlugin, SlashPlugin } from '@platejs/slash-command/react';

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
  markdownPlugin,
  suggestionPlugin,
  BlockSelectionPlugin,
  aiLeafPlugin,
  aiChatPlugin,
  // 官方的 SlashKit：键盘斜杠输入框 + 触发插件（本地无 codeBlock，故不配 triggerQuery）。
  SlashPlugin,
  SlashInputPlugin.withComponent(SlashInputElement as never),
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
// v1.7.1：打开失败不再是静默的（见 openPlateLiveTab），错误就地显示在按钮旁。
function OpenInPlateAction(openLiveEditor: (documentId: string) => string | undefined) {
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
        const openError = openLiveEditor(result.doc.id);
        if (openError) setError(openError);
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

// 工具栏必须嵌在 <Plate> 子树内：Radix 按钮的状态读的是 Plate store。
// v1.6.0：整条工具栏改用官方 playground 的编排（图标按钮 + 分组分隔 +
// 「转换为」下拉 + 悬浮提示），不再是自研的中文文字按钮。
function PlateToolbarButtons(props: { onPickImage: () => void; imageBusy?: boolean }) {
  useEditorVersion();
  return (
    <Toolbar>
      <ToolbarGroup>
        <AIToolbarButton />
      </ToolbarGroup>
      <ToolbarGroup>
        <TurnIntoToolbarButton />
      </ToolbarGroup>
      <ToolbarGroup>
        <MarkToolbarButton nodeType="bold" tooltip="加粗 (⌘+B)">
          <BoldIcon />
        </MarkToolbarButton>
        <MarkToolbarButton nodeType="italic" tooltip="斜体 (⌘+I)">
          <ItalicIcon />
        </MarkToolbarButton>
        <MarkToolbarButton nodeType="underline" tooltip="下划线 (⌘+U)">
          <UnderlineIcon />
        </MarkToolbarButton>
        <MarkToolbarButton nodeType="strikethrough" tooltip="删除线">
          <StrikethroughIcon />
        </MarkToolbarButton>
        <MarkToolbarButton nodeType="code" tooltip="行内代码 (⌘+E)">
          <Code2Icon />
        </MarkToolbarButton>
      </ToolbarGroup>
      <ToolbarGroup>
        <ImageToolbarButton disabled={props.imageBusy} onClick={props.onPickImage} />
        <HrToolbarButton />
      </ToolbarGroup>
    </Toolbar>
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

// 隐藏的文件输入：工具栏的「插图」按钮只负责 click()，真正的读取仍在 readImageFile。
function PlateImageInput(props: {
  editor: PlateEditor;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onStatus: (status: string) => void;
}) {
  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ''; // 允许连续选择同一文件
    if (file) readImageFile(file, props.editor, props.onStatus);
  };
  return (
    <input
      ref={props.inputRef}
      type="file"
      accept="image/*"
      style={{ display: 'none' }}
      data-plate-file-input="true"
      onChange={onChange}
    />
  );
}

type SyncRef = { current: { server: string; live: string; dirty: boolean } };

// 把编辑器的 live 指纹同步给父组件的轮询。
// **必须渲染在 <Plate> 子树内**：useEditorVersion 读的是 Plate store，放在
// PlateDocEditor 自身（它不在自己的 <Plate> 里）会抛
// "Plate hooks must be used inside a Plate or PlateController" 并炸掉整个 slot。
function LiveFingerprint(props: { editor: PlateEditor; syncRef: SyncRef }) {
  useEditorVersion();
  const s = props.syncRef.current;
  const json = JSON.stringify(props.editor.children);
  if (s.live === '') {
    s.live = json; // 首次见到：认下这一版，不算改动
  } else if (json !== s.live) {
    s.live = json;
    // 只记「编辑器自上次与服务端对齐后动过」，**不**拿客户端 JSON 去和服务端 JSON
    // 比字节：存储层回写会补/规整节点 id，两侧序列化本就不保证逐字节一致，
    // 那样比法会一旦不等就永久卡在 dirty、把实时更新悄悄关掉。
    s.dirty = true;
  }
  return null;
}

function PlateDocEditor(props: {
  docId: string;
  title: string;
  content: SlateContent;
  syncRef: SyncRef;
}) {
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [imageStatus, setImageStatus] = useState('');
  const imageRef = useRef<HTMLInputElement>(null);
  const editor = useState(() => createPlateEditor({ plugins, value: props.content }))[0];

  // 原生 AI 菜单的 Accept / Insert below / 流式续写写完 → AI 修改进修订链（cause='ai'）。
  // 落库成功才把 server 指纹推到最新，否则下次轮询会把这份内容当成"服务端已知"而抹掉。
  useEffect(() => {
    setAiAppliedHandler(() => {
      const json = JSON.stringify(editor.children);
      void post('rev-append', {
        docId: props.docId,
        content: editor.children as SlateContent,
        cause: 'ai',
      })
        .then(() => {
          // 落库成功 = 与服务端对齐：server 推到这一版，dirty 清掉，
          // 轮询从此刻起可以继续自动跟进 agent 的改动。
          props.syncRef.current.server = json;
          props.syncRef.current.dirty = false;
        })
        .catch(() => {});
    });
    return () => setAiAppliedHandler(null);
  }, [props.docId, editor]);

  // 探针调试钩子（不影响 UI）：暴露编辑器状态与确定性光标/块选区操作，供 E2E 用。
  useEffect(() => {
    const w = window as unknown as { __workdshPlateProbe?: Record<string, unknown> };
    w.__workdshPlateProbe = {
      state: () => {
        const sel = editor.selection;
        return {
          collapsed: !sel || editor.api.isCollapsed(),
          atEnd: editor.api.isAt({ end: true }),
          apiEnd: editor.api.end(),
          selection: sel,
          blockSome: (() => {
            try {
              return editor.getTransforms(BlockSelectionPlugin).isSelectingSome?.();
            } catch (error) {
              return `ERR:${String(error).slice(0, 120)}`;
            }
          })(),
          blockPaths: (() => {
            try {
              return editor
                .getApi(BlockSelectionPlugin)
                .blockSelection.getNodes({ sort: true })
                .map(([, path]: [unknown, unknown[]]) => path);
            } catch (error) {
              return `ERR:${String(error).slice(0, 120)}`;
            }
          })(),
        };
      },
      // 终点从最后一块的最后一个 text 子节点确定性计算，不依赖 api.end() 的 null 行为。
      cursorToEnd: () => {
        try {
          const last = editor.api.blocks().at(-1);
          if (!last) return 'no-blocks';
          const [node, path] = last;
          const children = (node.children ?? []) as Array<{ text?: string }>;
          const offset = children.at(-1)?.text?.length ?? 0;
          const end = { path: [...path, 0], offset };
          editor.tf.select({ anchor: end, focus: end });
          editor.tf.focus();
          return null;
        } catch (error) {
          return `ERR:${String(error).slice(0, 200)}`;
        }
      },
      clearBlocks: () => {
        try {
          editor.getApi(BlockSelectionPlugin).blockSelection.deselect();
          return null;
        } catch (error) {
          return `ERR:${String(error).slice(0, 200)}`;
        }
      },
    };
    return () => {
      delete w.__workdshPlateProbe;
    };
  }, [editor]);

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
      const json = JSON.stringify(editor.children);
      await post('rev-append', { docId: props.docId, content: editor.children as SlateContent, cause: 'edit' });
      // 存完这一版就是"服务端已知"，轮询从此刻起可以继续自动跟进 agent 的改动。
      props.syncRef.current.server = json;
      props.syncRef.current.dirty = false;
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
        <LiveFingerprint editor={editor} syncRef={props.syncRef} />
        <div className="plate-toolbar">
          <PlateToolbarButtons
            onPickImage={() => imageRef.current?.click()}
            imageBusy={saving}
          />
          <PlateImageInput editor={editor} inputRef={imageRef} onStatus={setImageStatus} />
          {/* 保存是产品动作，官方工具栏里没有对应物——留在工具栏右端，不进分组。 */}
          <span className="plate-toolbar-gap" />
          {imageStatus ? <span className="plate-image-status">{imageStatus}</span> : null}
          {savedAt ? <span className="plate-saved-at">已保存 {savedAt}</span> : null}
          <Button type="button" variant="primary" size="sm" disabled={saving} onClick={() => void save()}>
            {saving ? '保存中…' : '保存'}
          </Button>
        </div>
        <div className="plate-canvas" onPaste={handlePaste}>
          <PlateContent placeholder="开始输入…" className="plate-content" />
        </div>
      </Plate>
    </div>
  );
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
  // 同步指纹：server = 最后一次「服务端已知」的内容，live = 编辑器当前内容。
  // 两者不等 ⇒ 本地还有没落库的改动（AI 流式预览 / 手打），此时**绝不**按服务端重绘——
  // 否则一次自动重载就把用户没保存的内容抹掉，这正是「AI 写完文字消失」的放大器。
  const syncRef = useRef({ server: '', live: '', dirty: false });

  useEffect(() => {
    setState(null);
    setError('');
    syncRef.current = { server: '', live: '', dirty: false };
    if (!docId) return;
    let cancelled = false;
    let first = true;
    const load = async () => {
      try {
        const result = await post<{ doc: DocMeta; head: { slateJson: SlateContent; seq: number } }>('doc-open', { docId });
        if (cancelled) return;
        const headJson = JSON.stringify(result.head.slateJson);
        // 服务端没变就不动；编辑器有未落库改动（dirty）就保护它不重绘。
        if (headJson !== syncRef.current.server && !syncRef.current.dirty) {
          syncRef.current = { server: headJson, live: '', dirty: false };
          setState({ docId, title: result.doc.title, content: result.head.slateJson, revision: result.head.seq });
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
        </div>
      </div>
      {error ? <div className="plate-error">{error}</div> : null}
      {editorError ? <div className="plate-error">{editorError}</div> : null}
      {state ? (
        <PlateDocEditor
          key={state.revision}
          docId={state.docId}
          title={state.title}
          content={state.content}
          syncRef={syncRef}
        />
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
.plate-toolbar-sep { width: 1px; height: 18px; background: #e5e7eb; margin: 0 4px; }
.plate-toolbar-gap { flex: 1 1 auto; }
.plate-saved-at { color: #16a34a; font-size: 12px; }
.plate-canvas { padding: 16px; overflow-y: auto; position: relative; }
.plate-content { min-height: 260px; outline: none; }
.plate-file-preview { padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }
.plate-file-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.plate-file-body { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; background: #fff; }
.plate-image-status { color: #6366f1; font-size: 12px; }
.plate-content img { max-width: 100%; height: auto; border-radius: 6px; }
${aiNativeCss}
${toolbarNativeCss}
${slashNativeCss}
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
  // plate_open 的 pending 打开：500ms 轮询服务端队列，命中即开右侧活编辑器。
  const lifetime = new AbortController();
  const currentSessionId = () => {
    const state = (ctx.sessions as unknown as ISessions).list.getSnapshot();
    // retainedBy 的声明键集不含 mainView（office 同款派生），显式窄化。
    const retainedBy = (row: unknown) => ((row as { retainedBy?: { mainView?: number } }).retainedBy ?? {}).mainView ?? 0;
    return Object.values(state.byId).find((row) => retainedBy(row) > 0)?.id;
  };

  // v1.7.1：把「转成 Plate 文档」真正落到屏幕上。
  //
  // 宿主源码实证（dsh-client-ui-sidebar-right service.d.ts 原文）：openTabIn 是
  // Tab 域内部路径，「nothing happens for a session whose store was never adopted
  // or whose adoption was released」——运行期 `actionsFor()` 返回 undefined 就直接
  // return，**不抛错也不开**。点「用 PlateAI 打开」时转换已经成功（服务端落了文档），
  // 却因为这一层静默 no-op 什么都不上屏，用户看到的还是原来那个 Word 页面。
  //
  // 公开面 openTab() 作用在**当前挂载的座位**上，宿主保证「The column expands in
  // the same step, because content the user cannot see is not opened」；没有座位时
  // 它抛错（"sidebarRight: no session surface is mounted"）而不是沉默。故：
  // 先 openTab，抛错才回退到指定会话的 openTabIn，并补一次显式展开
  //（openTabIn 不开栏，开在折叠栏里等于没开）。
  let lastOpen: { at: number; documentId: string; via: string; error?: string } | null = null;
  const openPlateLiveTab = (documentId: string): string | undefined => {
    const options = { params: { documentId } };
    try {
      ctx.sidebarRight.openTab('workdsh-plate-live', options as never);
      lastOpen = { at: Date.now(), documentId, via: 'openTab' };
      return undefined;
    } catch (e) {
      const seatError = String(e);
      const sessionId = currentSessionId();
      if (!sessionId) {
        lastOpen = { at: Date.now(), documentId, via: 'none', error: seatError };
        return `没有可用的会话，无法在右侧打开：${seatError}`;
      }
      ctx.sidebarRight.openTabIn(sessionId as never, 'workdsh-plate-live', options as never);
      try {
        if (!ctx.sidebarRight.isExpanded()) ctx.sidebarRight.toggleExpanded();
      } catch {
        /* 无座位时 isExpanded 恒 false，展开无效；不影响开 tab 的尝试。 */
      }
      lastOpen = { at: Date.now(), documentId, via: 'openTabIn' };
      return undefined;
    }
  };
  const openLiveEditor = (documentId: string): string | undefined => openPlateLiveTab(documentId);
  ctx.effect(() => {
    const w = window as unknown as { __workdshPlateOpen?: unknown };
    w.__workdshPlateOpen = () => lastOpen;
    return () => {
      delete w.__workdshPlateOpen;
    };
  });

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
              // 与「用 PlateAI 打开」同一条路：agent 的 plate_open 也要真上屏。
              if (openPlateLiveTab(request.documentId) === undefined) seen.add(request.requestId);
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
