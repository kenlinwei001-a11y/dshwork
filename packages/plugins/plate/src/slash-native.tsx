/**
 * 官方 playground 斜杠菜单移植层。
 *
 * 蓝本（udecode/plate-playground-template@main，与本地 platejs 53.3.14 同代）：
 *   src/components/ui/inline-combobox.tsx → InlineCombobox* 全套原语
 *   src/components/ui/slash-node.tsx      → SlashInputElement（触发字符 "/"）
 *   src/components/editor/plugins/slash-kit.tsx → SlashPlugin + SlashInputPlugin 接线
 *
 * 为什么需要它：官方 PlateAI 编辑器的「这是 AI 编辑器」的身份标识，主要就靠
 * "/" 菜单的第一组 AI（SparklesIcon → aiChat.show()）。此前只搬了 AI 交互层
 * （ai-native.tsx），没装 SlashPlugin，于是敲 "/" 只会插入一个字面斜杠，
 * 编辑器看上去和 Word 没有区别——用户实测反馈的正是这一点。
 *
 * 与官方的落地差异（都是宿主限制，非设计选择）：
 *   ① 宿主无 tailwind / cva → 类名落 `slx-*` 自包含 CSS（视觉等价）；
 *   ② 菜单文案中文化（与本插件工具栏同策略）；
 *   ③ 条目裁剪到本插件真装了的 block：正文/p、h1-h3、引用、分隔线。
 *      官方的列表/待办/折叠/代码块/表格/Callout/TOC/分栏/公式/绘图等
 *      依赖未安装的插件，一律不列（列了点了会炸）。
 *
 * 触发语义保持官方：仅在空段落行首敲 "/" 生成 slash_input 节点。
 */
import {
  Combobox,
  ComboboxGroup,
  ComboboxGroupLabel,
  ComboboxItem,
  type ComboboxItemProps,
  ComboboxPopover,
  ComboboxProvider,
  ComboboxRow,
  Portal,
  useComboboxContext,
  useComboboxStore,
} from '@ariakit/react';
import { filterWords } from '@platejs/combobox';
import {
  type UseComboboxInputResult,
  useComboboxInput,
  useHTMLInputCursorState,
} from '@platejs/combobox/react';
import { AIChatPlugin } from '@platejs/ai/react';
import clsx from 'clsx';
import {
  Heading1Icon,
  Heading2Icon,
  Heading3Icon,
  MinusIcon,
  PilcrowIcon,
  QuoteIcon,
  SparklesIcon,
} from 'lucide-react';
import { KEYS, type PointRef, type TElement } from 'platejs';
import {
  PlateElement,
  useComposedRef,
  useEditorRef,
  type PlateElementProps,
  type PlateEditor,
} from 'platejs/react';
import * as React from 'react';

import { setBlockType } from './toolbar-native.js';

type FilterFn = (
  item: { value: string; group?: string; keywords?: string[]; label?: string },
  search: string,
) => boolean;

type InlineComboboxContextValue = {
  filter: FilterFn | false;
  inputProps: UseComboboxInputResult['props'];
  inputRef: React.RefObject<HTMLInputElement | null>;
  removeInput: UseComboboxInputResult['removeInput'];
  showTrigger: boolean;
  trigger: string;
  setHasEmpty: (hasEmpty: boolean) => void;
};

const InlineComboboxContext = React.createContext<InlineComboboxContextValue>(
  null as unknown as InlineComboboxContextValue,
);

const defaultFilter: FilterFn = (
  { group, keywords = [], label, value },
  search,
) => {
  const uniqueTerms = new Set(
    [value, ...keywords, group, label].filter(Boolean),
  );

  return Array.from(uniqueTerms).some((keyword) =>
    filterWords(keyword!, search),
  );
};

type InlineComboboxProps = {
  children: React.ReactNode;
  element: TElement;
  trigger: string;
  filter?: FilterFn | false;
  hideWhenNoValue?: boolean;
  showTrigger?: boolean;
  value?: string;
  setValue?: (value: string) => void;
};

const InlineCombobox = ({
  children,
  element,
  filter = defaultFilter,
  hideWhenNoValue = false,
  setValue: setValueProp,
  showTrigger = true,
  trigger,
  value: valueProp,
}: InlineComboboxProps) => {
  const editor = useEditorRef();
  const inputRef = React.useRef<HTMLInputElement>(null);
  const cursorState = useHTMLInputCursorState(inputRef);

  const [valueState, setValueState] = React.useState('');
  const hasValueProp = valueProp !== undefined;
  const value = hasValueProp ? valueProp : valueState;

  const setValue = React.useCallback(
    (newValue: string) => {
      setValueProp?.(newValue);

      if (!hasValueProp) {
        setValueState(newValue);
      }
    },
    [setValueProp, hasValueProp],
  );

  /**
   * Track the point just before the input element so we know where to
   * insertText if the combobox closes due to a selection change.
   */
  const insertPointRef = React.useRef<PointRef | null>(null);

  React.useEffect(() => {
    insertPointRef.current?.unref();
    insertPointRef.current = null;

    const path = editor.api.findPath(element);

    if (!path) return;

    const point = editor.api.before(path);

    if (!point) return;

    const pointRef = editor.api.pointRef(point);
    insertPointRef.current = pointRef;

    return () => {
      if (insertPointRef.current === pointRef) {
        insertPointRef.current = null;
      }
      pointRef.unref();
    };
  }, [editor, element]);

  const { props: inputProps, removeInput } = useComboboxInput({
    cancelInputOnBlur: true,
    cursorState,
    autoFocus: true,
    ref: inputRef,
    onCancelInput: (cause) => {
      if (cause !== 'backspace') {
        editor.tf.insertText(trigger + value, {
          at: insertPointRef.current?.current ?? undefined,
        });
      }
      if (cause === 'arrowLeft' || cause === 'arrowRight') {
        editor.tf.move({
          distance: 1,
          reverse: cause === 'arrowLeft',
        });
      }
    },
  });

  const [hasEmpty, setHasEmpty] = React.useState(false);

  const contextValue: InlineComboboxContextValue = React.useMemo(
    () => ({
      filter,
      inputProps,
      inputRef,
      removeInput,
      setHasEmpty,
      showTrigger,
      trigger,
    }),
    [
      trigger,
      showTrigger,
      filter,
      inputRef,
      inputProps,
      removeInput,
      setHasEmpty,
    ],
  );

  const store = useComboboxStore({
    setValue: (newValue) => React.startTransition(() => setValue(newValue)),
  });

  const items = store.useState('items');

  /**
   * If there is no active ID and the list of items changes, select the first
   * item.
   */
  React.useEffect(() => {
    if (!store.getState().activeId) {
      store.setActiveId(store.first());
    }
  }, [items, store]);

  return (
    <span contentEditable={false}>
      <ComboboxProvider
        open={
          (items.length > 0 || hasEmpty) &&
          (!hideWhenNoValue || value.length > 0)
        }
        store={store}
      >
        <InlineComboboxContext.Provider value={contextValue}>
          {children}
        </InlineComboboxContext.Provider>
      </ComboboxProvider>
    </span>
  );
};

const InlineComboboxInput = ({
  className,
  ref: propRef,
  ...props
}: React.HTMLAttributes<HTMLInputElement> & {
  ref?: React.RefObject<HTMLInputElement | null>;
}) => {
  const {
    inputProps,
    inputRef: contextRef,
    showTrigger,
    trigger,
  } = React.useContext(InlineComboboxContext);

  const store = useComboboxContext()!;
  const value = store.useState('value');

  const ref = useComposedRef(propRef, contextRef);

  /**
   * 自适应宽度输入框：底下垫一层不可见的同值 span 撑开，输入框绝对定位盖上去
   * （官方原样，含超宽时不换行这一已知限制）。
   */
  return (
    <>
      {showTrigger && trigger}

      <span className="slx-input-wrap">
        <span aria-hidden="true" className="slx-input-ghost">
          {value || '​'}
        </span>

        <Combobox
          autoSelect
          className={clsx('slx-input', className)}
          ref={ref}
          value={value}
          {...inputProps}
          {...props}
        />
      </span>
    </>
  );
};

InlineComboboxInput.displayName = 'InlineComboboxInput';

const InlineComboboxContent: typeof ComboboxPopover = ({
  className,
  ...props
}) => {
  // Portal prevents CSS from leaking into popover
  const store = useComboboxContext();

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (!store) return;

    const state = store.getState();
    const { items, activeId } = state;

    if (!items.length) return;

    const currentIndex = items.findIndex((item) => item.id === activeId);

    if (event.key === 'ArrowUp' && currentIndex <= 0) {
      event.preventDefault();
      store.setActiveId(store.last());
    } else if (event.key === 'ArrowDown' && currentIndex >= items.length - 1) {
      event.preventDefault();
      store.setActiveId(store.first());
    }
  }

  return (
    <Portal>
      <ComboboxPopover
        className={clsx('slx-pop', className)}
        onKeyDownCapture={handleKeyDown}
        {...props}
      />
    </Portal>
  );
};

const InlineComboboxItem = ({
  className,
  focusEditor = true,
  group,
  keywords,
  label,
  onClick,
  ...props
}: {
  focusEditor?: boolean;
  group?: string;
  keywords?: string[];
  label?: string;
} & ComboboxItemProps &
  Required<Pick<ComboboxItemProps, 'value'>>) => {
  const { value } = props;

  const { filter, removeInput } = React.useContext(InlineComboboxContext);

  const store = useComboboxContext()!;

  // Optimization: Do not subscribe to value if filter is false
  const search = filter && store.useState('value');

  const visible = React.useMemo(
    () =>
      !filter || filter({ group, keywords, label, value }, search as string),
    [filter, group, keywords, label, value, search],
  );

  if (!visible) return null;

  return (
    <ComboboxItem
      className={clsx('slx-item', className)}
      onClick={(event) => {
        removeInput(focusEditor);
        onClick?.(event);
      }}
      {...props}
    />
  );
};

const InlineComboboxEmpty = ({
  children,
  className,
}: React.HTMLAttributes<HTMLDivElement>) => {
  const { setHasEmpty } = React.useContext(InlineComboboxContext);
  const store = useComboboxContext()!;
  const items = store.useState('items');

  React.useEffect(() => {
    setHasEmpty(true);

    return () => {
      setHasEmpty(false);
    };
  }, [setHasEmpty]);

  if (items.length > 0) return null;

  return <div className={clsx('slx-item slx-item-static', className)}>{children}</div>;
};

const InlineComboboxRow = ComboboxRow;

function InlineComboboxGroup({
  className,
  ...props
}: React.ComponentProps<typeof ComboboxGroup>) {
  return <ComboboxGroup {...props} className={clsx('slx-group', className)} />;
}

function InlineComboboxGroupLabel({
  className,
  ...props
}: React.ComponentProps<typeof ComboboxGroupLabel>) {
  return (
    <ComboboxGroupLabel {...props} className={clsx('slx-group-label', className)} />
  );
}

// ---------------------------------------------------------------------------
// "/" 菜单条目（蓝本 slash-node.tsx，裁剪到本插件已装的 block）
// 第一组必须是 AI：这是官方编辑器表明自己"是 AI 编辑器"的地方。
type Group = {
  group: string;
  items: {
    icon: React.ReactNode;
    value: string;
    onSelect: (editor: PlateEditor, value: string) => void;
    focusEditor?: boolean;
    keywords?: string[];
    label?: string;
  }[];
};

const groups: Group[] = [
  {
    group: 'AI',
    items: [
      {
        focusEditor: false,
        icon: <SparklesIcon />,
        keywords: ['ai', '写作', '润色', '续写', '扩写', '缩写', '纠错', '翻译'],
        label: 'AI 写作',
        value: 'AI',
        onSelect: (editor) => {
          editor.getApi(AIChatPlugin).aiChat.show();
        },
      },
    ],
  },
  {
    group: '基本块',
    items: [
      {
        icon: <PilcrowIcon />,
        keywords: ['正文', '段落', 'paragraph', 'text'],
        label: '正文',
        value: KEYS.p,
        onSelect: (editor, value) => setBlock(editor, value),
      },
      {
        icon: <Heading1Icon />,
        keywords: ['标题', 'title', 'h1'],
        label: '标题 1',
        value: KEYS.h1,
        onSelect: (editor, value) => setBlock(editor, value),
      },
      {
        icon: <Heading2Icon />,
        keywords: ['标题', 'subtitle', 'h2'],
        label: '标题 2',
        value: KEYS.h2,
        onSelect: (editor, value) => setBlock(editor, value),
      },
      {
        icon: <Heading3Icon />,
        keywords: ['标题', 'subtitle', 'h3'],
        label: '标题 3',
        value: KEYS.h3,
        onSelect: (editor, value) => setBlock(editor, value),
      },
      {
        icon: <QuoteIcon />,
        keywords: ['引用', 'citation', 'blockquote', 'quote', '>'],
        label: '引用',
        value: KEYS.blockquote,
        onSelect: (editor, value) => setBlock(editor, value),
      },
      {
        icon: <MinusIcon />,
        keywords: ['分隔线', 'hr', 'divider', '---'],
        label: '分隔线',
        value: KEYS.hr,
        onSelect: (editor, value) => setBlock(editor, value),
      },
    ],
  },
];

/**
 * 把光标所在块转成目标类型。
 * InlineComboboxItem 已先 removeInput()，slash_input 节点此时不在树里，
 * 这里直接复用工具栏那套 setBlockType 语义（blockquote 走 wrap）；
 * 分隔线没有对应 block 类型，走 toggleBlock(hr)，与工具栏的分隔线按钮同源。
 */
function setBlock(editor: PlateEditor, type: string) {
  if (type === KEYS.hr) {
    editor.tf.toggleBlock(KEYS.hr);
    return;
  }
  setBlockType(editor, type);
  editor.tf.focus();
}

export function SlashInputElement(
  props: PlateElementProps<TElement>,
) {
  const { editor, element } = props;

  return (
    <PlateElement {...props} as="span">
      <InlineCombobox element={element} trigger="/">
        <InlineComboboxInput />

        <InlineComboboxContent>
          <InlineComboboxEmpty>没有匹配项</InlineComboboxEmpty>

          {groups.map(({ group, items }) => (
            <InlineComboboxGroup key={group}>
              <InlineComboboxGroupLabel>{group}</InlineComboboxGroupLabel>

              {items.map(({ focusEditor, icon, keywords, label, value, onSelect }) => (
                <InlineComboboxItem
                  focusEditor={focusEditor}
                  group={group}
                  key={value}
                  keywords={keywords}
                  label={label}
                  onClick={() => onSelect(editor, value)}
                  value={value}
                >
                  <div className="slx-item-icon">{icon}</div>
                  {label ?? value}
                </InlineComboboxItem>
              ))}
            </InlineComboboxGroup>
          ))}
        </InlineComboboxContent>
      </InlineCombobox>
    </PlateElement>
  );
}

// ---------------------------------------------------------------------------
// 自包含样式（宿主无 tailwind：官方类名的等价落地）。
// 弹层走 Portal 挂到 body，故规则必须是全局的，用 slx- 前缀避免撞车。
export const slashNativeCss = `
.slx-input-wrap { position: relative; display: inline-block; min-width: 1px; min-height: 1.5em; }
.slx-input-ghost { visibility: hidden; overflow: hidden; white-space: nowrap; }
.slx-input { position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: 0; background: transparent; padding: 0; outline: none; font: inherit; color: inherit; }
.slx-pop { z-index: 500; max-height: 288px; width: 300px; overflow-y: auto; border: 1px solid #e4e4e7; border-radius: 6px; background: #fff; box-shadow: 0 8px 24px rgba(0,0,0,.12); padding: 4px 0; }
.slx-group { display: none; padding: 6px 0; }
.slx-group:has([role="option"]) { display: block; }
.slx-group:not(:last-child) { border-bottom: 1px solid #f4f4f5; }
.slx-group-label { margin: 6px 0 8px; padding: 0 12px; color: #71717a; font-size: 12px; font-weight: 500; }
.slx-item { position: relative; display: flex; height: 28px; margin: 0 4px; cursor: pointer; user-select: none; align-items: center; border-radius: 4px; padding: 0 8px; color: #3f3f46; font-size: 14px; outline: none; transition: background-color .12s, color .12s; }
.slx-item:hover, .slx-item[data-active-item="true"] { background: #f4f4f5; color: #18181b; }
.slx-item-static { cursor: default; color: #a1a1aa; }
.slx-item-icon { display: flex; margin-right: 8px; color: #71717a; }
.slx-item svg { width: 16px; height: 16px; flex-shrink: 0; pointer-events: none; }
`;
