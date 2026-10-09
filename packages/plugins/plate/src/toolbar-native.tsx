/**
 * 官方 playground 工具栏移植层。
 *
 * 蓝本（udecode/plate-playground-template@main，与本地 platejs 53.3.14 同代）：
 *   src/components/ui/toolbar.tsx                  → Toolbar / ToolbarGroup / ToolbarButton
 *   src/components/ui/mark-toolbar-button.tsx      → MarkToolbarButton
 *   src/components/ui/turn-into-toolbar-button.tsx → TurnIntoToolbarButton
 *   src/components/ui/fixed-toolbar-buttons.tsx    → 按钮编排（裁剪到本插件已装插件范围）
 *   src/components/editor/transforms.ts            → getBlockType / setBlockType
 *
 * DOM 结构、Radix 原语（toolbar / tooltip / dropdown-menu）、图标、交互均照官方；
 * 只有三处落地差异，且都是宿主限制而非设计选择：
 *   ① 宿主无 tailwind 工具链 → 官方类名落到自包含的 pltx-tlb-* CSS（视觉等价）；
 *   ② 菜单与提示文案中文化（与既有无 AI 菜单同策略）；
 *   ③ 组件一律 forwardRef 显式透传 ref（官方靠 Slot 的 cloneElement 隐式传递，
 *      本宿主里 React 19 不把它交给函数组件——见下方 withTooltip 注释）。
 * 官方 cva 变体未引入：它只产出类名字符串，最终同样落到 pltx-tlb-* 上。
 */
import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu';
import * as ToolbarPrimitive from '@radix-ui/react-toolbar';
import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import clsx from 'clsx';
import {
  BoldIcon,
  CheckIcon,
  ChevronDownIcon,
  Code2Icon,
  Heading1Icon,
  Heading2Icon,
  Heading3Icon,
  ImageIcon,
  ItalicIcon,
  MinusIcon,
  PilcrowIcon,
  QuoteIcon,
  StrikethroughIcon,
  UnderlineIcon,
  WandSparklesIcon,
} from 'lucide-react';
import { KEYS, type NodeEntry, type Path, type TElement } from 'platejs';
import type { PlateEditor } from 'platejs/react';
import {
  useEditorPlugin,
  useEditorRef,
  useMarkToolbarButton,
  useMarkToolbarButtonState,
  useSelectionFragmentProp,
} from 'platejs/react';
import * as React from 'react';

import { AIChatPlugin } from '@platejs/ai/react';

// ---------------------------------------------------------------------------
// 基元：Toolbar / ToolbarGroup / ToolbarSeparator（蓝本 ui/toolbar.tsx）
export function Toolbar({
  className,
  ...props
}: React.ComponentProps<typeof ToolbarPrimitive.Root>) {
  return (
    // 官方把 TooltipProvider（delayDuration=0）挂在 app 根，这里没有那样的根，
    // 就挂在工具栏上——Radix Tooltip.Root 不套 Provider 会直接抛
    // 「`Tooltip` must be used within `TooltipProvider`」，整个 tab 挂不掉。
    <TooltipPrimitive.Provider delayDuration={0}>
      <ToolbarPrimitive.Root
        className={clsx('pltx-tlb-root', className)}
        {...props}
      />
    </TooltipPrimitive.Provider>
  );
}

export function ToolbarGroup({
  children,
  className,
}: React.ComponentProps<'div'>) {
  return (
    <div className={clsx('pltx-tlb-group', className)}>
      <div className="pltx-tlb-group-inner">{children}</div>
      <div className="pltx-tlb-group-sep">
        <span className="pltx-tlb-sep-line" />
      </div>
    </div>
  );
}

export function ToolbarSeparator({
  className,
  ...props
}: React.ComponentProps<typeof ToolbarPrimitive.Separator>) {
  return (
    <ToolbarPrimitive.Separator
      className={clsx('pltx-tlb-sep', className)}
      {...props}
    />
  );
}

// ---------------------------------------------------------------------------
// Tooltip（蓝本 ui/tooltip.tsx：Provider 默认 delayDuration=0）
function TooltipContent({
  children,
  className,
  sideOffset = 4,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        className={clsx('pltx-tlb-tip', className)}
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        {...props}
      >
        {children}
        <TooltipPrimitive.Arrow className="pltx-tlb-tip-arrow" />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  );
}

type TooltipProps<T extends React.ElementType> = {
  tooltip?: React.ReactNode;
  tooltipContentProps?: Omit<
    React.ComponentPropsWithoutRef<typeof TooltipContent>,
    'children'
  >;
  tooltipTriggerProps?: React.ComponentPropsWithoutRef<
    typeof TooltipPrimitive.Trigger
  >;
} & React.ComponentProps<T>;

// 与官方同名同形，唯一实质差异：这里必须 forwardRef 显式透传。
// 官方 playground 是 Next 应用，Radix 的 Slot 走 cloneElement 把 ref 交给子组件；
// 在本宿主里实测 React 19 并不会把它作为 props.ref 交给函数组件
// （探针实证：refInProps=false refType=undefined）——ref 直接掉进黑洞，
// PopperAnchor 的 onAnchorChange 永远收不到节点，context.anchor=null，
// 浮层（提示气泡与「转换为」菜单）全部停在 translate(0,-200%) 的未定位兜底位。
// 做成 forwardRef 后 ref 走第二参数，绕开该行为。
function withTooltip<T extends React.ElementType>(Component: T) {
  return React.forwardRef<unknown, TooltipProps<T>>(function ExtendComponent(
    { tooltip, tooltipContentProps, tooltipTriggerProps, ...props },
    ref,
  ) {
    const [mounted, setMounted] = React.useState(false);

    React.useEffect(() => {
      setMounted(true);
    }, []);

    // 泛型元素 + ref 的组合 TS 推不动（LibraryManagedAttributes 对未定类型无解），
    // 这里按运行时行为断言：ref 走 forwardRef 第二参数传给被包组件。
    const ComponentWithRef = Component as React.ElementType;
    const component = (
      <ComponentWithRef {...(props as object)} ref={ref} />
    );

    if (tooltip && mounted) {
      return (
        <TooltipPrimitive.Root>
          <TooltipPrimitive.Trigger asChild {...tooltipTriggerProps}>
            {component}
          </TooltipPrimitive.Trigger>
          <TooltipContent {...tooltipContentProps}>{tooltip}</TooltipContent>
        </TooltipPrimitive.Root>
      );
    }

    return component;
  });
}

// ---------------------------------------------------------------------------
// ToolbarButton（蓝本 ui/toolbar.tsx 同名组件）
// pressed 为布尔时走 ToolbarToggleItem（aria-checked 即 CSS 的激活态判据），
// 否则走普通 ToolbarButton。isDropdown 在尾部补 ChevronDown。
type ToolbarButtonProps = {
  isDropdown?: boolean;
  pressed?: boolean;
  size?: 'sm' | 'default' | 'lg';
} & Omit<
  React.ComponentPropsWithoutRef<typeof ToolbarPrimitive.ToggleItem>,
  'asChild' | 'value'
>;

export const ToolbarButton = withTooltip(
  React.forwardRef<HTMLButtonElement, ToolbarButtonProps>(
  function ToolbarButtonContent({
    children,
    className,
    isDropdown,
    pressed,
    size = 'sm',
    ...props
  }, ref) {
  const sizeClass =
    size === 'lg' ? 'pltx-tlb-lg' : size === 'default' ? 'pltx-tlb-md' : '';

  // 用 Toolbar 自己的 ToggleGroup/ToggleItem（官方同名组件；内部的
  // rovingFocus:false 也是官方选择）。
  return typeof pressed === 'boolean' ? (
    <ToolbarPrimitive.ToolbarToggleGroup disabled={props.disabled} type="single" value="single">
      <ToolbarPrimitive.ToolbarToggleItem
        className={clsx('pltx-tlb-btn', sizeClass, isDropdown && 'pltx-tlb-dropdown', className)}
        value={pressed ? 'single' : ''}
        {...props}
        ref={ref}
      >
        {isDropdown ? (
          <>
            <div className="pltx-tlb-dropdown-label">{children}</div>
            <div>
              <ChevronDownIcon className="pltx-tlb-chevron" data-icon />
            </div>
          </>
        ) : (
          children
        )}
      </ToolbarPrimitive.ToolbarToggleItem>
    </ToolbarPrimitive.ToolbarToggleGroup>
  ) : (
    <ToolbarPrimitive.Button
      className={clsx('pltx-tlb-btn', sizeClass, isDropdown && 'pltx-tlb-dropdown', className)}
      {...props}
      ref={ref}
    >
      {children}
    </ToolbarPrimitive.Button>
  );
  }),
);

// ---------------------------------------------------------------------------
// MarkToolbarButton（蓝本 ui/mark-toolbar-button.tsx，逐行）
export function MarkToolbarButton({
  clear,
  nodeType,
  ...props
}: React.ComponentProps<typeof ToolbarButton> & {
  nodeType: string;
  clear?: string[] | string;
}) {
  const state = useMarkToolbarButtonState({ clear, nodeType });
  const { props: buttonProps } = useMarkToolbarButton(state);

  return <ToolbarButton {...props} {...buttonProps} />;
}

// ---------------------------------------------------------------------------
// 转换为：block 类型下拉（蓝本 ui/turn-into-toolbar-button.tsx + transforms.ts）
// 条目裁剪到本插件实际装载的 block：段落 / h1-h3 / 引用。
// （官方的列表、toggle、代码块、三栏等依赖未安装的插件，不列。）
type TurnIntoItem = {
  icon: React.ReactNode;
  keywords: string[];
  label: string;
  value: string;
};

export const turnIntoItems: TurnIntoItem[] = [
  { icon: <PilcrowIcon />, keywords: ['正文', '段落', 'paragraph'], label: '正文', value: KEYS.p },
  { icon: <Heading1Icon />, keywords: ['标题', 'h1'], label: '标题 1', value: 'h1' },
  { icon: <Heading2Icon />, keywords: ['标题', 'h2'], label: '标题 2', value: 'h2' },
  { icon: <Heading3Icon />, keywords: ['标题', 'h3'], label: '标题 3', value: 'h3' },
  { icon: <QuoteIcon />, keywords: ['引用', 'quote', '>'], label: '引用', value: KEYS.blockquote },
];

export const getBlockType = (block: TElement): string => String(block.type ?? KEYS.p);

/** 蓝本 editor/transforms.ts 的 setBlockType，去掉本插件没有的列表/代码块分支。 */
export const setBlockType = (
  editor: PlateEditor,
  type: string,
  { at }: { at?: Path } = {},
) => {
  editor.tf.withoutNormalizing(() => {
    if (type === KEYS.blockquote) {
      const target = at ?? editor.selection;

      if (!target || editor.api.some({ at: target, match: { type } })) {
        return;
      }

      editor.tf.toggleBlock(type, { ...(at ? { at } : {}), wrap: true });

      return;
    }

    const setEntry = (entry: NodeEntry<TElement>) => {
      const [node, path] = entry;

      if (node.type !== type) {
        editor.tf.setNodes({ type }, { at: path });
      }
    };

    if (at) {
      const entry = editor.api.node<TElement>(at);

      if (entry) {
        setEntry(entry);

        return;
      }
    }

    editor.api.blocks({ mode: 'lowest' }).forEach((entry: NodeEntry<TElement>) => {
      setEntry(entry);
    });
  });
};

export function TurnIntoToolbarButton(
  props: React.ComponentProps<typeof DropdownMenuPrimitive.Root>,
) {
  const editor = useEditorRef();
  const [open, setOpen] = React.useState(false);

  const value = useSelectionFragmentProp({
    defaultValue: KEYS.p,
    getProp: (node) => getBlockType(node as TElement),
  });
  const selectedItem = React.useMemo(
    () =>
      turnIntoItems.find((item) => item.value === (value ?? KEYS.p)) ??
      turnIntoItems[0],
    [value],
  );

  return (
    <DropdownMenuPrimitive.Root modal={false} onOpenChange={setOpen} open={open} {...props}>
      <DropdownMenuPrimitive.Trigger asChild>
        <ToolbarButton
          className="pltx-tlb-turninto"
          isDropdown
          pressed={open}
          tooltip="转换为"
        >
          {selectedItem.label}
        </ToolbarButton>
      </DropdownMenuPrimitive.Trigger>

      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          align="start"
          className="pltx-tlb-menu"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            editor.tf.focus();
          }}
          sideOffset={4}
        >
          <DropdownMenuPrimitive.Label className="pltx-tlb-menu-label">
            转换为
          </DropdownMenuPrimitive.Label>
          <DropdownMenuPrimitive.RadioGroup
            onValueChange={(type) => setBlockType(editor, type)}
            value={value}
          >
            {turnIntoItems.map(({ icon, label, value: itemValue }) => (
              <DropdownMenuPrimitive.RadioItem
                className="pltx-tlb-menu-item"
                key={itemValue}
                value={itemValue}
              >
                <span className="pltx-tlb-menu-check">
                  <DropdownMenuPrimitive.ItemIndicator>
                    <CheckIcon />
                  </DropdownMenuPrimitive.ItemIndicator>
                </span>
                {icon}
                {label}
              </DropdownMenuPrimitive.RadioItem>
            ))}
          </DropdownMenuPrimitive.RadioGroup>
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}

// ---------------------------------------------------------------------------
// 本插件自有动作的官方外观按钮（插图 / 分隔线 / AI）。
// 行为仍是本插件的（图片走 data URL 自包含），chrome 与官方一致。
export function ImageToolbarButton({
  disabled,
  onClick,
}: {
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <ToolbarButton disabled={disabled} onClick={onClick} tooltip="插入图片">
      <ImageIcon />
    </ToolbarButton>
  );
}

export function HrToolbarButton() {
  const editor = useEditorRef();

  return (
    <ToolbarButton
      onClick={() => editor.tf.toggleBlock(KEYS.hr)}
      tooltip="分隔线"
    >
      <MinusIcon />
    </ToolbarButton>
  );
}

export function AIToolbarButton() {
  const { api } = useEditorPlugin(AIChatPlugin);

  return (
    <ToolbarButton onClick={() => api.aiChat.show()} tooltip="AI 命令">
      <WandSparklesIcon />
    </ToolbarButton>
  );
}

// ---------------------------------------------------------------------------
// 自包含样式（宿主无 tailwind：官方类名的等价落地）
export const toolbarNativeCss = `
.pltx-tlb-root { position: relative; display: flex; align-items: center; user-select: none; flex-wrap: wrap; gap: 2px; }
.pltx-tlb-group { position: relative; display: none; }
.pltx-tlb-group:has(button) { display: flex; }
.pltx-tlb-group-inner { display: flex; align-items: center; }
.pltx-tlb-group-sep { margin: 2px 6px; padding: 2px 0; }
.pltx-tlb-group:last-child .pltx-tlb-group-sep { display: none; }
.pltx-tlb-sep-line { display: block; width: 1px; height: 20px; background: #e4e4e7; }
.pltx-tlb-btn { display: inline-flex; height: 32px; min-width: 32px; cursor: pointer; align-items: center; justify-content: center; gap: 8px; white-space: nowrap; border: 0; border-radius: 6px; background: transparent; padding: 0 6px; color: #3f3f46; font-size: 14px; font-weight: 500; outline: none; transition: background-color .12s, color .12s; }
.pltx-tlb-md { height: 36px; min-width: 36px; padding: 0 8px; }
.pltx-tlb-lg { height: 40px; min-width: 40px; padding: 0 10px; }
.pltx-tlb-btn:hover { background: #f4f4f5; color: #71717a; }
.pltx-tlb-btn[aria-checked="true"] { background: #f4f4f5; color: #18181b; }
.pltx-tlb-btn:disabled { pointer-events: none; opacity: .5; }
.pltx-tlb-btn svg { width: 16px; height: 16px; pointer-events: none; flex-shrink: 0; }
.pltx-tlb-dropdown { justify-content: space-between; gap: 4px; padding-right: 4px; }
.pltx-tlb-dropdown-label { display: flex; flex: 1 1 auto; align-items: center; gap: 8px; white-space: nowrap; }
.pltx-tlb-chevron { width: 14px; height: 14px; color: #a1a1aa; }
.pltx-tlb-turninto { min-width: 104px; justify-content: space-between; }
.pltx-tlb-sep { width: 1px; height: 20px; flex-shrink: 0; background: #e4e4e7; margin: 0 4px; }
.pltx-tlb-tip { z-index: 60; width: fit-content; border-radius: 6px; background: #18181b; padding: 6px 12px; color: #fafafa; font-size: 12px; line-height: 1.2; box-shadow: 0 4px 12px rgba(0,0,0,.18); }
.pltx-tlb-tip-arrow { fill: #18181b; }
.pltx-tlb-menu { z-index: 60; min-width: 180px; border: 1px solid #e4e4e7; border-radius: 8px; background: #fff; padding: 4px; box-shadow: 0 8px 24px rgba(0,0,0,.12); }
.pltx-tlb-menu-label { padding: 6px 8px 4px; color: #71717a; font-size: 12px; font-weight: 600; user-select: none; }
.pltx-tlb-menu-item { position: relative; display: flex; align-items: center; gap: 8px; border-radius: 6px; padding: 6px 28px 6px 8px; color: #3f3f46; font-size: 14px; cursor: pointer; outline: none; }
.pltx-tlb-menu-item[data-highlighted] { background: #f4f4f5; color: #18181b; }
.pltx-tlb-menu-item svg { width: 16px; height: 16px; flex-shrink: 0; }
.pltx-tlb-menu-check { position: absolute; right: 8px; display: flex; width: 14px; height: 14px; align-items: center; justify-content: center; }
`;
