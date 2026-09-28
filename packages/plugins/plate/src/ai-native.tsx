/**
 * v1.5.0：plate 官方原生 AI 编辑器 UI（移植层）。
 *
 * 蓝本：官方仓库 udecode/plate-playground-template（platejs.org 同源 UI）：
 *   src/components/editor/use-chat.ts                       → useChat()
 *   src/components/editor/plugins/ai-kit.tsx                → aiChatPlugin
 *   src/components/ui/ai-menu.tsx                           → AIMenu / AIMenuItems / AILoadingBar / 菜单项
 *   src/components/ui/ai-node.tsx                           → AILeaf / AIAnchorElement
 *   src/components/ui/ai-chat-editor.tsx + editor-static.tsx → AIChatEditor / EditorStatic
 *   src/components/ui/ai-toolbar-button.tsx                 → AIToolbarButton
 *   src/components/editor/plugins/suggestion-base-kit.tsx + ui/suggestion-node-static.tsx → 建议 diff 渲染
 *
 * 裁剪（如实声明）：comment/table 工具不移植（需 @platejs/comment/discussion kit，
 * 非本产品需求）；faker mock 流不移植；宿主无 tailwind 工具链 → 官方组件结构与
 * 交互逐行照搬，样式类落地为 .pltx-* scoped CSS（随插件 <style> 注入）。
 */
import * as React from 'react';
import { useChat as useBaseChat } from '@ai-sdk/react';
import { DefaultChatTransport, type UIMessage } from 'ai';
import { withAIBatch } from '@platejs/ai';
import {
  AIChatPlugin,
  AIPlugin,
  applyAISuggestions,
  getInsertPreviewStart,
  streamInsertChunk,
  useAIChatEditor,
  useChatChunk,
  useEditorChat,
  useLastAssistantMessage,
} from '@platejs/ai/react';
import { BlockSelectionPlugin, useIsSelecting } from '@platejs/selection/react';
import { BaseSuggestionPlugin, getTransientSuggestionKey } from '@platejs/suggestion';
import { MarkdownPlugin, serializeMd } from '@platejs/markdown';
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
import { Command } from 'cmdk';
import { Popover, PopoverAnchor, PopoverContent } from '@radix-ui/react-popover';
import {
  Check,
  CornerUpLeft,
  Languages,
  ListEnd,
  ListMinus,
  ListPlus,
  Loader2Icon,
  PauseIcon,
  PenLine,
  SpellCheck,
  Wand,
  X,
} from 'lucide-react';
import { clsx } from 'clsx';
import {
  ElementApi,
  getPluginType,
  isHotkey,
  KEYS,
  NodeApi,
  PathApi,
  BaseParagraphPlugin,
  type SlateEditor,
  type TElement,
  type TSuggestionText,
} from 'platejs';
import {
  PlateStatic,
  SlateLeaf,
  type PlateStaticProps,
  type SlateLeafProps,
} from 'platejs/static';
import {
  PlateElement,
  PlateText,
  useEditorPlugin,
  useEditorRef,
  useFocusedLast,
  useHotkeys,
  usePlateEditor,
  usePluginOption,
  type PlateEditor,
  type PlateElementProps,
  type PlateTextProps,
} from 'platejs/react';

type ChatMessage = UIMessage<{}, { toolName?: 'generate' | 'edit' }>;

// ---------------------------------------------------------------------------
// AI 落地回调：Accept / Insert below 之后由 client.tsx 注入 rev-append（cause='ai'）。
// 同一时刻只挂一个活编辑器实例，模块级 handler 足够。
let aiAppliedHandler: (() => void) | null = null;
export function setAiAppliedHandler(handler: (() => void) | null): void {
  aiAppliedHandler = handler;
}

// ---------------------------------------------------------------------------
// useChat：官方接线（蓝本 use-chat.ts，去掉 mock 流）。transport 的 fetch 覆写
// 负责把插件端点合入 body —— submitAIChat 只会发 { messages, ctx }。
function useChat(): void {
  const editor = useEditorRef();
  const options = usePluginOption(aiChatPlugin, 'chatOptions');

  const transport = React.useMemo(
    () =>
      new DefaultChatTransport({
        api: options.api || '/api/workdsh-plate',
        fetch: (async (input, init) => {
          const initBody = JSON.parse((init?.body as string) || '{}');
          const body = { ...initBody, endpoint: 'ai-command' };
          return fetch(input, { ...init, body: JSON.stringify(body) });
        }) as typeof fetch,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- editor 参与 transport 仅官方签名一致性
    [editor, options.api],
  );

  const chat = useBaseChat<ChatMessage>({ id: 'editor', transport });

  React.useEffect(() => {
    editor.setOption(AIChatPlugin, 'chat', chat as never);
  }, [chat.status, chat.messages, chat.error]);
}

// ---------------------------------------------------------------------------
// AI 节点渲染（蓝本 ai-node.tsx 逐行照搬）。
export function AILeaf(props: PlateTextProps) {
  const streaming = usePluginOption(AIChatPlugin, 'streaming');
  const streamingLeaf = props.editor
    .getApi(AIChatPlugin)
    .aiChat.node({ streaming: true });

  const isLast = streamingLeaf?.[0] === props.text;

  return (
    <PlateText
      className={clsx('pltx-ai-leaf', isLast && streaming && 'pltx-ai-leaf-last')}
      {...props}
    />
  );
}

export function AIAnchorElement(props: PlateElementProps) {
  return (
    <PlateElement {...props}>
      <div className="pltx-ai-anchor" />
    </PlateElement>
  );
}

// ---------------------------------------------------------------------------
// 建议 diff 渲染（蓝本 suggestion-node-static.tsx + suggestion-base-kit 的 render 段）。
function isStaticVoidRemoveSuggestion(element: TElement) {
  return (
    (element as TElement & { suggestion?: { type?: string } }).suggestion
      ?.type === 'remove'
  );
}

function VoidRemoveSuggestionOverlayStatic(props: { editor: PlateEditor; element: TElement }) {
  const { editor, element } = props;
  const active =
    editor.api.isVoid(element) &&
    !editor.api.isInline(element) &&
    isStaticVoidRemoveSuggestion(element);

  if (!active) return null;

  return (
    <div className="pltx-suggestion-void" contentEditable={false} data-slot="void-remove-suggestion" />
  );
}

function SuggestionLeafStatic(props: SlateLeafProps<TSuggestionText>) {
  const { editor, leaf } = props;

  const dataList = editor
    .getApi(BaseSuggestionPlugin)
    .suggestion.dataList(leaf);
  const hasRemove = dataList.some((data: { type: string }) => data.type === 'remove');
  const diffOperation = { type: hasRemove ? 'delete' : 'insert' } as const;

  const Component = ({ delete: 'del', insert: 'ins', update: 'span' } as const)[
    diffOperation.type
  ];

  return (
    <SlateLeaf
      {...props}
      as={Component}
      className={clsx('pltx-suggestion', hasRemove && 'pltx-suggestion-remove')}
    >
      {props.children}
    </SlateLeaf>
  );
}

export const suggestionPlugin = BaseSuggestionPlugin.configure({
  render: {
    belowRootNodes: VoidRemoveSuggestionOverlayStatic as never,
    node: SuggestionLeafStatic as never,
  },
});

// plainMarks：suggestion 标记在 md 序列化时按纯文本处理（官方同款配置，裁掉 comment）。
export const markdownPlugin = MarkdownPlugin.configure({
  options: {
    plainMarks: [KEYS.suggestion],
  },
});

// ---------------------------------------------------------------------------
// 聊天预览（蓝本 ai-chat-editor.tsx + editor-static.tsx 的 aiChat variant）。
// aiEditor 只读预览：反序列化生成结果的 md（useAIChatEditor 依赖 MarkdownPlugin）。
const aiEditorPlugins = [
  BaseParagraphPlugin,
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
  markdownPlugin,
];

function EditorStatic({ className, ...props }: PlateStaticProps) {
  return (
    <PlateStatic
      className={clsx('pltx-editor-static-aichat', className)}
      {...props}
    />
  );
}

export const AIChatEditor = React.memo(function AIChatEditor({
  content,
}: {
  content: string;
}) {
  const aiEditor = usePlateEditor({
    plugins: aiEditorPlugins,
  });

  const value = useAIChatEditor(aiEditor, content);

  return <EditorStatic editor={aiEditor} value={value} />;
});

// ---------------------------------------------------------------------------
// 菜单项（蓝本 ai-menu.tsx 的 aiChatItems/menuStateItems，中文产品项 + 官方项）。
type MenuItemDef = {
  icon: React.ReactNode;
  label: string;
  value: string;
  onSelect: (args: { aiEditor: SlateEditor; editor: PlateEditor; input: string }) => void;
};

// 选区片段序列化为 Markdown（无选区时取全文）——prompt 在点击时拼好，
// ai-command 服务端直接使用最后一条用户消息文本。
function selectionMarkdown(editor: PlateEditor): string {
  const selection = editor.selection;
  if (selection && !editor.api.isCollapsed(selection)) {
    const fragment = editor.api.fragment();
    return serializeMd(editor, { value: fragment as never });
  }
  return serializeMd(editor, { value: editor.children as never });
}

const DOC_OUTPUT_RULE = '只输出修改后的 Markdown 全文，不要任何解释。';

const aiChatItems: Record<string, MenuItemDef> = {
  // ---- 中文产品项（原 6 个 AI 动作 → 官方菜单项）----
  polish: {
    icon: <Wand />,
    label: '润色',
    value: 'polish',
    onSelect: ({ editor, input }) => {
      void editor.getApi(AIChatPlugin).aiChat.submit(input, {
        prompt: `请润色以下内容，改进表达与流畅度，不改变原意，保留 Markdown 结构（标题、加粗等）。${DOC_OUTPUT_RULE}\n\n${selectionMarkdown(editor)}`,
        toolName: 'edit',
      });
    },
  },
  continueWrite: {
    icon: <PenLine />,
    label: '续写',
    value: 'continueWrite',
    onSelect: ({ editor, input }) => {
      const ancestorNode = editor.api.block({ highest: true });
      if (!ancestorNode) return;
      const isEmpty = NodeApi.string(ancestorNode[0]).trim().length === 0;
      void editor.getApi(AIChatPlugin).aiChat.submit(input, {
        mode: 'insert',
        prompt: isEmpty
          ? `请为以下文档新写一段（输出 Markdown）：\n\n${selectionMarkdown(editor)}`
          : `请紧接以下内容续写一段，不要重复已有文字，只输出续写部分（Markdown）：\n\n${selectionMarkdown(editor)}`,
        toolName: 'generate',
      });
    },
  },
  makeLonger: {
    icon: <ListPlus />,
    label: '扩写',
    value: 'makeLonger',
    onSelect: ({ editor, input }) => {
      void editor.getApi(AIChatPlugin).aiChat.submit(input, {
        prompt: `请扩写以下内容，在原有基础上补充细节、丰富表达，不改变核心意思，保留 Markdown 结构。${DOC_OUTPUT_RULE}\n\n${selectionMarkdown(editor)}`,
        toolName: 'edit',
      });
    },
  },
  makeShorter: {
    icon: <ListMinus />,
    label: '缩写',
    value: 'makeShorter',
    onSelect: ({ editor, input }) => {
      void editor.getApi(AIChatPlugin).aiChat.submit(input, {
        prompt: `请缩写以下内容，删减冗余、保留要点与关键信息，保留 Markdown 结构。${DOC_OUTPUT_RULE}\n\n${selectionMarkdown(editor)}`,
        toolName: 'edit',
      });
    },
  },
  fixSpelling: {
    icon: <SpellCheck />,
    label: '纠错',
    value: 'fixSpelling',
    onSelect: ({ editor, input }) => {
      void editor.getApi(AIChatPlugin).aiChat.submit(input, {
        prompt: `请纠正以下内容的错别字、语法与标点错误，不改变原意与风格，保留 Markdown 结构。${DOC_OUTPUT_RULE}\n\n${selectionMarkdown(editor)}`,
        toolName: 'edit',
      });
    },
  },
  translate: {
    icon: <Languages />,
    label: '翻译',
    value: 'translate',
    onSelect: ({ editor, input }) => {
      void editor.getApi(AIChatPlugin).aiChat.submit(input, {
        prompt: `请将以下内容翻译为英文，保留 Markdown 结构。${DOC_OUTPUT_RULE}\n\n${selectionMarkdown(editor)}`,
        toolName: 'edit',
      });
    },
  },
  // ---- 官方项（原样保留）----
  accept: {
    icon: <Check />,
    label: 'Accept',
    value: 'accept',
    onSelect: ({ aiEditor, editor }) => {
      const { mode, toolName } = editor.getOptions(AIChatPlugin);

      if (mode === 'chat' && toolName === 'generate') {
        editor.getTransforms(AIChatPlugin).aiChat.replaceSelection(aiEditor);
      } else {
        editor.getTransforms(AIChatPlugin).aiChat.accept();
        editor.tf.focus({ edge: 'end' });
      }
      // AI 修改进修订链，cause='ai' 与手动编辑区分。
      aiAppliedHandler?.();
    },
  },
  discard: {
    icon: <X />,
    label: 'Discard',
    value: 'discard',
    onSelect: ({ editor }) => {
      editor.getTransforms(AIPlugin).ai.undo();
      editor.getApi(AIChatPlugin).aiChat.hide();
    },
  },
  insertBelow: {
    icon: <ListEnd />,
    label: 'Insert below',
    value: 'insertBelow',
    onSelect: ({ aiEditor, editor }) => {
      void editor
        .getTransforms(AIChatPlugin)
        .aiChat.insertBelow(aiEditor, { format: 'none' });
      aiAppliedHandler?.();
    },
  },
  tryAgain: {
    icon: <CornerUpLeft />,
    label: 'Try again',
    value: 'tryAgain',
    onSelect: ({ editor }) => {
      void editor.getApi(AIChatPlugin).aiChat.reload();
    },
  },
};

// 菜单态（官方同名结构，裁剪 comment 相关组）：
// 无消息 → 命令菜单；有消息（建议/预览已生成）→ 建议操作菜单。
const menuStateItems: Record<
  'cursorCommand' | 'cursorSuggestion' | 'selectionCommand' | 'selectionSuggestion',
  { items: MenuItemDef[] }[]
> = {
  cursorCommand: [
    {
      items: [aiChatItems.continueWrite],
    },
  ],
  cursorSuggestion: [
    {
      items: [aiChatItems.accept, aiChatItems.discard, aiChatItems.tryAgain],
    },
  ],
  selectionCommand: [
    {
      items: [
        aiChatItems.polish,
        aiChatItems.makeLonger,
        aiChatItems.makeShorter,
        aiChatItems.fixSpelling,
        aiChatItems.translate,
      ],
    },
  ],
  selectionSuggestion: [
    {
      items: [aiChatItems.accept, aiChatItems.discard, aiChatItems.insertBelow, aiChatItems.tryAgain],
    },
  ],
};

export function AIMenuItems({
  input,
  setInput,
  setValue,
}: {
  input: string;
  setInput: (value: string) => void;
  setValue: (value: string) => void;
}) {
  const editor = useEditorRef();
  const { messages } = usePluginOption(AIChatPlugin, 'chat');
  const aiEditor = usePluginOption(AIChatPlugin, 'aiEditor')!;
  const isSelecting = useIsSelecting();

  const menuState = React.useMemo(() => {
    if (messages && messages.length > 0) {
      return isSelecting ? 'selectionSuggestion' : 'cursorSuggestion';
    }

    return isSelecting ? 'selectionCommand' : 'cursorCommand';
  }, [isSelecting, messages]);

  const menuGroups = React.useMemo(() => menuStateItems[menuState], [menuState]);

  React.useEffect(() => {
    if (menuGroups.length > 0 && menuGroups[0].items.length > 0) {
      setValue(menuGroups[0].items[0].value);
    }
  }, [menuGroups, setValue]);

  return (
    <>
      {menuGroups.map((group, index) => (
        <Command.Group className="pltx-ai-group" key={index}>
          {group.items.map((menuItem) => (
            <Command.Item
              className="pltx-ai-item"
              key={menuItem.value}
              onSelect={() => {
                menuItem.onSelect?.({
                  aiEditor,
                  editor,
                  input,
                });
                setInput('');
              }}
              value={menuItem.value}
            >
              {menuItem.icon}
              <span>{menuItem.label}</span>
            </Command.Item>
          ))}
        </Command.Group>
      ))}
    </>
  );
}

export function AIMenu() {
  const { api, editor } = useEditorPlugin(AIChatPlugin);
  const mode = usePluginOption(AIChatPlugin, 'mode');
  const toolName = usePluginOption(AIChatPlugin, 'toolName');

  const streaming = usePluginOption(AIChatPlugin, 'streaming');
  const isSelecting = useIsSelecting();
  const isFocusedLast = useFocusedLast();
  const open = usePluginOption(AIChatPlugin, 'open') && isFocusedLast;
  const [value, setValue] = React.useState('');

  const [input, setInput] = React.useState('');

  const chat = usePluginOption(AIChatPlugin, 'chat');

  const { messages, status } = chat;
  const [anchorElement, setAnchorElement] = React.useState<HTMLElement | null>(
    null
  );

  const content = useLastAssistantMessage()?.parts.find(
    (part) => part.type === 'text'
  )?.text;

  React.useEffect(() => {
    if (!streaming) return;

    const anchorEntry = api.aiChat.node({ anchor: true });
    if (!anchorEntry) return;

    const anchorDom = editor.api.toDOMNode(anchorEntry[0])!;
    setAnchorElement(anchorDom);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming]);

  const setOpen = (open: boolean) => {
    if (open) {
      api.aiChat.show();
    } else {
      api.aiChat.hide();
    }
  };

  const show = (anchorElement: HTMLElement) => {
    setAnchorElement(anchorElement);
    setOpen(true);
  };

  useEditorChat({
    onOpenBlockSelection: (blocks) => {
      show(editor.api.toDOMNode(blocks.at(-1)![0])!);
    },
    onOpenChange: (open) => {
      if (!open) {
        setAnchorElement(null);
        setInput('');
      }
    },
    onOpenCursor: () => {
      const [ancestor] = editor.api.block({ highest: true })!;

      if (!editor.api.isAt({ end: true }) && !editor.api.isEmpty(ancestor)) {
        editor
          .getApi(BlockSelectionPlugin)
          .blockSelection.set(ancestor.id as string);
      }

      show(editor.api.toDOMNode(ancestor)!);
    },
    onOpenSelection: () => {
      show(editor.api.toDOMNode(editor.api.blocks().at(-1)![0])!);
    },
  });

  useHotkeys('esc', () => {
    api.aiChat.stop();
  });

  const isLoading = status === 'streaming' || status === 'submitted';

  React.useEffect(() => {
    if (toolName !== 'edit' || mode !== 'chat' || isLoading) return;

    let anchorNode = editor.api.node({
      at: [],
      reverse: true,
      match: (n: Record<string, unknown>) =>
        !!n[KEYS.suggestion] && !!n[getTransientSuggestionKey()],
    });

    if (!anchorNode) {
      anchorNode = editor
        .getApi(BlockSelectionPlugin)
        .blockSelection.getNodes({ selectionFallback: true, sort: true })
        .at(-1);
    }

    if (!anchorNode) return;

    const block = editor.api.block({ at: anchorNode[1] });
    setAnchorElement(editor.api.toDOMNode(block![0])!);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading]);

  if (isLoading && mode === 'insert') return null;

  if (toolName === 'edit' && mode === 'chat' && isLoading) return null;

  return (
    <Popover modal={false} onOpenChange={setOpen} open={open}>
      <PopoverAnchor virtualRef={{ current: anchorElement! }} />

      <PopoverContent
        align="center"
        className="pltx-ai-popover"
        onEscapeKeyDown={(e) => {
          e.preventDefault();

          api.aiChat.hide();
        }}
        side="bottom"
        style={{
          width: anchorElement?.offsetWidth,
        }}
      >
        <Command
          className="pltx-ai-cmd"
          onValueChange={setValue}
          value={value}
        >
          {mode === 'chat' &&
            isSelecting &&
            content &&
            toolName === 'generate' && <AIChatEditor content={content} />}

          {isLoading ? (
            <div className="pltx-ai-thinking">
              <Loader2Icon className="pltx-ai-ic pltx-ai-spin" />
              {messages.length > 1 ? '正在修改…' : '正在思考…'}
            </div>
          ) : (
            <Command.Input
              autoFocus
              className="pltx-ai-input"
              data-plate-focus
              onKeyDown={(e) => {
                if (isHotkey('backspace')(e) && input.length === 0) {
                  e.preventDefault();
                  api.aiChat.hide();
                }
                if (isHotkey('enter')(e) && !e.shiftKey && input.length > 0) {
                  // 官方门是 !value：英文菜单下自由文本总能模糊匹配到某项，Enter 选中该项
                  // （项 onSelect 以输入文本提交）。中文菜单下自由文本匹配不到任何项，
                  // cmdk 对无高亮项的 Enter 是死路径 → 补丁：无高亮项时直接提交自由输入；
                  // 有高亮项时放行给 cmdk（官方语义：输入文本优先，项只提供 prompt 模板）。
                  const root = (e.target as HTMLElement).closest('[cmdk-root]');
                  const highlighted = root?.querySelector('[cmdk-item][aria-selected="true"]');
                  if (!value || !highlighted) {
                    e.preventDefault();
                    // 自由输入默认走 generate（官方服务端会自动选 tool，本实现固定）。
                    void api.aiChat.submit(input, { toolName: 'generate' });
                    setInput('');
                  }
                }
              }}
              onValueChange={setInput}
              placeholder="Ask AI anything..."
              value={input}
            />
          )}

          {!isLoading && (
            <Command.List className="pltx-ai-list">
              <AIMenuItems
                input={input}
                setInput={setInput}
                setValue={setValue}
              />
            </Command.List>
          )}
        </Command>
      </PopoverContent>
    </Popover>
  );
}

export function AILoadingBar() {
  const toolName = usePluginOption(AIChatPlugin, 'toolName');
  const chat = usePluginOption(AIChatPlugin, 'chat');
  const mode = usePluginOption(AIChatPlugin, 'mode');

  const { status } = chat;

  const { api } = useEditorPlugin(AIChatPlugin);

  const isLoading = status === 'streaming' || status === 'submitted';

  useHotkeys('esc', () => {
    api.aiChat.stop();
  });

  if (
    isLoading &&
    (mode === 'insert' || (toolName === 'edit' && mode === 'chat'))
  ) {
    return (
      <div className="pltx-ai-loading">
        <span className="pltx-ai-spinner" />
        <span>{status === 'submitted' ? '正在思考…' : '正在写作…'}</span>
        <button
          className="pltx-ai-stop"
          onClick={() => api.aiChat.stop()}
          type="button"
        >
          <PauseIcon className="pltx-ai-ic" />
          停止
          <kbd className="pltx-ai-kbd">Esc</kbd>
        </button>
      </div>
    );
  }

  return null;
}

// ---------------------------------------------------------------------------
// 工具条按钮（蓝本 toolbar.tsx 的 ToolbarButton/ToolbarToggle 结构；
// radix toolbar 不引入，等价 button 实现，视觉类同官方）。
export function ToolbarButton(props: {
  children?: React.ReactNode;
  active?: boolean;
  title?: string;
  className?: string;
  onClick?: () => void;
  onMouseDown?: (event: React.MouseEvent) => void;
}) {
  return (
    <button
      type="button"
      className={clsx('pltx-tb', props.active && 'pltx-tb-active', props.className)}
      data-active={props.active ? 'true' : undefined}
      title={props.title}
      onMouseDown={(event) => {
        event.preventDefault();
        props.onMouseDown?.(event);
      }}
      onClick={() => props.onClick?.()}
    >
      {props.children}
    </button>
  );
}

export function AIToolbarButton(
  props: React.ComponentProps<typeof ToolbarButton>,
) {
  const { api } = useEditorPlugin(AIChatPlugin);

  return (
    <ToolbarButton
      {...props}
      onClick={() => {
        api.aiChat.show();
      }}
      onMouseDown={(e) => {
        e.preventDefault();
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// aiChatPlugin（蓝本 ai-kit.tsx 逐行照搬，裁剪 CursorOverlay/comment kit）。
export const aiChatPlugin = AIChatPlugin.extend({
  options: {
    chatOptions: {
      api: '/api/workdsh-plate',
      body: {},
    },
  },
  render: {
    afterContainer: AILoadingBar,
    afterEditable: AIMenu,
    node: AIAnchorElement,
  },
  shortcuts: { show: { keys: 'mod+j' } },
  useHooks: ({ editor, getOption }: { editor: PlateEditor; getOption: (key: string) => unknown }) => {
    useChat();

    const mode = usePluginOption(AIChatPlugin, 'mode');
    const toolName = usePluginOption(AIChatPlugin, 'toolName');
    useChatChunk({
      onChunk: ({ chunk, isFirst, nodes, text: content }) => {
        if (isFirst && mode === 'insert') {
          const { startBlock, startInEmptyParagraph } =
            getInsertPreviewStart(editor);

          editor.getTransforms(AIPlugin).ai.beginPreview({
            originalBlocks:
              startInEmptyParagraph &&
              startBlock &&
              ElementApi.isElement(startBlock)
                ? [JSON.parse(JSON.stringify(startBlock))]
                : [],
          });

          editor.tf.withoutSaving(() => {
            editor.tf.insertNodes(
              {
                children: [{ text: '' }],
                type: getPluginType(editor, KEYS.aiChat),
              },
              {
                at: PathApi.next(editor.selection!.focus.path.slice(0, 1)),
              },
            );
          });
          editor.setOption(AIChatPlugin, 'streaming', true);
        }

        if (mode === 'insert' && nodes.length > 0) {
          editor.tf.withoutSaving(() => {
            if (!getOption('streaming')) return;

            editor.tf.withScrolling(() => {
              streamInsertChunk(editor, chunk, {
                textProps: {
                  [getPluginType(editor, KEYS.ai)]: true,
                },
              });
            });
          });
        }

        if (toolName === 'edit' && mode === 'chat') {
          withAIBatch(
            editor,
            () => {
              applyAISuggestions(editor, content);
            },
            {
              split: isFirst,
            },
          );
        }
      },
      onFinish: () => {
        editor.getApi(AIChatPlugin).aiChat.stop();
      },
    });
  },
});

// AI 标记叶子 + 聊天插件：主编辑器 plugins 数组新增项。
export const aiLeafPlugin = AIPlugin.withComponent(AILeaf as never);

// ---------------------------------------------------------------------------
// .pltx-* scoped CSS：官方组件 tailwind 工具类的静态等价实现（宿主无
// tailwind 工具链）。由 client.tsx injectStyles() 一并注入。
export const aiNativeCss = `
@keyframes pltx-spin { to { transform: rotate(360deg); } }
.pltx-ai-leaf { border-bottom: 2px solid #f3e8ff; background: #faf5ff; color: #6b21a8; transition: all .2s ease-in-out; }
.pltx-ai-leaf-last::after { margin-left: 6px; display: inline-block; height: 12px; width: 12px; border-radius: 50%; background: #7c3aed; vertical-align: middle; content: ""; }
.pltx-ai-anchor { height: .1px; }
.pltx-suggestion { border-bottom: 2px solid rgba(124,58,237,.24); background: rgba(124,58,237,.08); color: rgba(109,40,217,.8); text-decoration: none; transition: color .2s; }
.pltx-suggestion-remove { border-bottom-color: #d1d5db; background: rgba(209,213,219,.25); color: #9ca3af; text-decoration: line-through; }
.pltx-suggestion-void { position: absolute; inset: 0; z-index: 20; overflow: hidden; border-radius: inherit; pointer-events: none; }
.pltx-suggestion-void::before { content: "X"; position: absolute; top: 50%; left: 50%; z-index: 20; display: flex; width: 40px; height: 40px; transform: translate(-50%,-50%); align-items: center; justify-content: center; border-radius: 50%; background: rgba(239,68,68,.9); color: #fff; font-size: 24px; font-weight: 600; box-shadow: 0 10px 15px -3px rgba(0,0,0,.1); }
.pltx-suggestion-void::after { content: ""; position: absolute; inset: 0; z-index: 10; border: 1px solid rgba(252,165,165,.8); background: rgba(24,24,27,.35); }
.pltx-ai-popover { border: none; background: transparent; padding: 0; box-shadow: none; }
.pltx-ai-cmd { width: 100%; overflow: hidden; border: 1px solid #e4e4e7; border-radius: 8px; background: #fff; box-shadow: 0 4px 6px -1px rgba(0,0,0,.1), 0 2px 4px -2px rgba(0,0,0,.1); }
.pltx-ai-input { display: flex; height: 36px; width: 100%; min-width: 0; border: 0; border-bottom: 1px solid #e4e4e7; background: transparent; padding: 0 12px; font-size: 14px; color: #18181b; outline: none; }
.pltx-ai-input::placeholder { color: #a1a1aa; }
.pltx-ai-thinking { display: flex; flex-grow: 1; align-items: center; gap: 8px; padding: 8px; color: #71717a; font-size: 14px; }
.pltx-ai-list { max-height: 280px; overflow-y: auto; padding: 4px; }
.pltx-ai-group { padding: 2px 0; }
.pltx-ai-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; font-size: 14px; color: #3f3f46; cursor: pointer; }
.pltx-ai-item[data-selected="true"] { background: #f4f4f5; color: #18181b; }
.pltx-ai-item svg { width: 16px; height: 16px; color: #71717a; flex-shrink: 0; }
.pltx-ai-loading { position: absolute; bottom: 16px; left: 50%; z-index: 20; display: flex; transform: translateX(-50%); align-items: center; gap: 12px; border: 1px solid #e4e4e7; border-radius: 6px; background: #f4f4f5; padding: 6px 12px; color: #71717a; font-size: 14px; box-shadow: 0 4px 6px -1px rgba(0,0,0,.1); }
.pltx-ai-spinner { height: 16px; width: 16px; border: 2px solid #71717a; border-top-color: transparent; border-radius: 50%; animation: pltx-spin 1s linear infinite; flex-shrink: 0; }
.pltx-ai-stop { display: flex; align-items: center; gap: 4px; border: 0; border-radius: 4px; background: transparent; padding: 2px 4px; color: inherit; font-size: 12px; cursor: pointer; }
.pltx-ai-stop:hover { background: #e4e4e7; }
.pltx-ai-kbd { margin-left: 4px; border-radius: 4px; background: #e4e4e7; padding: 0 4px; font-family: ui-monospace, monospace; font-size: 10px; color: #71717a; box-shadow: 0 1px 2px rgba(0,0,0,.05); }
.pltx-ai-ic { width: 16px; height: 16px; pointer-events: none; flex-shrink: 0; }
.pltx-ai-spin { animation: pltx-spin 1s linear infinite; }
.pltx-editor-static-aichat { max-height: min(70vh,320px); width: 100%; overflow-y: auto; padding: 20px 12px; font-size: 14px; border-bottom: 1px solid #e4e4e7; }
.pltx-tb { display: inline-flex; height: 32px; min-width: 32px; align-items: center; justify-content: center; gap: 4px; border: 0; border-radius: 6px; background: transparent; padding: 0 8px; color: #3f3f46; font-size: 13px; font-weight: 500; white-space: nowrap; cursor: pointer; }
.pltx-tb:hover { background: #f4f4f5; color: #52525b; }
.pltx-tb[data-active="true"] { background: #f4f4f5; color: #18181b; }
.pltx-tb svg { width: 16px; height: 16px; pointer-events: none; flex-shrink: 0; }
`;
