/**
 * 官方 playground 浮动工具条移植层（选中文字即弹出）。
 *
 * 蓝本（udecode/plate-playground-template@main，与本地 platejs 53.3.14 同代）：
 *   src/components/ui/floating-toolbar.tsx         → FloatingToolbar
 *   src/components/ui/floating-toolbar-buttons.tsx → FloatingToolbarButtons
 *
 * 为什么需要它：官方 AIChatPlugin 的 useEditorChat 依赖数组**只有 [open]**
 * （@platejs/ai/dist/react/index.js:793 原文），三个回调是菜单「已经打开后」
 * 重新挂锚点用的——选中文字本身不会打开 AI 菜单。官方 playground 的做法是
 * 选中先弹这条浮动工具条，点其中的 AI 按钮再展开菜单。本文件照此实现。
 *
 * 与官方的落地差异（宿主限制，非设计选择）：
 *   ① 宿主无 @udecode/cn → useComposedRef 就地内联实现（行为等价）；
 *   ② 类名落 `pltx-ftb-*` 自包含 CSS（视觉等价）；
 *   ③ 按钮裁剪到本插件真装了的标记：AI / 加粗 / 斜体 / 下划线 / 删除线 /
 *      行内码。官方的链接、行内公式、评论、建议、更多 依赖未安装的插件，不列。
 */
import {
  type FloatingToolbarState,
  flip,
  offset,
  useFloatingToolbar,
  useFloatingToolbarState,
} from '@platejs/floating';
import { AIChatPlugin } from '@platejs/ai/react';
import { BoldIcon, Code2Icon, ItalicIcon, StrikethroughIcon, UnderlineIcon } from 'lucide-react';
import { KEYS } from 'platejs';
import {
  useEditorId,
  useEditorReadOnly,
  useEventEditorValue,
  usePluginOption,
} from 'platejs/react';
import React from 'react';
import clsx from 'clsx';

import { AIToolbarButton, MarkToolbarButton, Toolbar, ToolbarGroup } from './toolbar-native.js';

/**
 * 官方用 @udecode/cn 的 useComposedRef；宿主没装那个包，
 * 这里就地实现等价语义：把内层与传入的 ref 一起挂到同一个节点上。
 */
function useComposedRef<T>(
  ...refs: Array<React.Ref<T> | undefined>
): (node: T | null) => void {
  return React.useCallback((node: T | null) => {
    for (const ref of refs) {
      if (!ref) continue;
      if (typeof ref === 'function') ref(node);
      else (ref as React.MutableRefObject<T | null>).current = node;
    }
    // refs 每次渲染都是新数组字面量，用展开长度+逐项比对太重；
    // 官方同样是「每次渲染重建」，这里保持一致。
  }, refs);
}

export function FloatingToolbar({
  children,
  className,
  ref: forwardedRef,
  state,
  ...props
}: React.ComponentProps<typeof Toolbar> & { state?: FloatingToolbarState }) {
  const editorId = useEditorId();
  const focusedEditorId = useEventEditorValue('focus');
  // AI 菜单打开时收起工具条，避免两层浮层打架（官方同款判定）
  const isAIChatOpen = usePluginOption(AIChatPlugin, 'open');

  const floatingToolbarState = useFloatingToolbarState({
    editorId,
    focusedEditorId,
    hideToolbar: isAIChatOpen,
    ...state,
    floatingOptions: {
      middleware: [
        offset(12),
        flip({
          fallbackPlacements: [
            'top-start',
            'top-end',
            'bottom-start',
            'bottom-end',
          ],
          padding: 12,
        }),
      ],
      placement: 'top',
      ...state?.floatingOptions,
    },
  });

  const {
    clickOutsideRef,
    hidden,
    props: rootProps,
    ref: floatingRef,
  } = useFloatingToolbar(floatingToolbarState);

  const ref = useComposedRef<HTMLDivElement>(forwardedRef, floatingRef);

  if (hidden) return null;

  return (
    <div ref={clickOutsideRef}>
      {/*
        定位 ref 必须落在真实 DOM 节点上（useFloatingToolbar 返回的 ref 是
        floating-ui 的 setFloating 回调 ref，props 里只有 style）。
        本宿主实测过「函数组件拿不到 props.ref」——ref 会直接掉进黑洞，
        浮层停在未定位位（translate(0,-200%)）。因此这里不复刻官方把 ref 交给
        <Toolbar> 的写法，改为自带一个定位用的包裹节点，位置语义完全等价。
      */}
      <div
        {...rootProps}
        className={clsx('pltx-ftb-root', className)}
        data-plate-floating-toolbar=""
        ref={ref}
      >
        <Toolbar {...props}>{children}</Toolbar>
      </div>
    </div>
  );
}

export function FloatingToolbarButtons() {
  const readOnly = useEditorReadOnly();

  if (readOnly) return null;

  return (
    <>
      <ToolbarGroup>
        <AIToolbarButton />
      </ToolbarGroup>

      <ToolbarGroup>
        <MarkToolbarButton nodeType={KEYS.bold} tooltip="加粗 (⌘+B)">
          <BoldIcon />
        </MarkToolbarButton>

        <MarkToolbarButton nodeType={KEYS.italic} tooltip="斜体 (⌘+I)">
          <ItalicIcon />
        </MarkToolbarButton>

        <MarkToolbarButton nodeType={KEYS.underline} tooltip="下划线 (⌘+U)">
          <UnderlineIcon />
        </MarkToolbarButton>

        <MarkToolbarButton
          nodeType={KEYS.strikethrough}
          tooltip="删除线 (⌘+⇧+M)"
        >
          <StrikethroughIcon />
        </MarkToolbarButton>

        <MarkToolbarButton nodeType={KEYS.code} tooltip="行内代码 (⌘+E)">
          <Code2Icon />
        </MarkToolbarButton>
      </ToolbarGroup>
    </>
  );
}

// ---------------------------------------------------------------------------
// 自包含样式（宿主无 tailwind：官方类名的等价落地）
export const floatingToolbarNativeCss = `
.pltx-ftb-root {
  position: absolute;
  z-index: 50;
  max-width: 80vw;
  overflow-x: auto;
  white-space: nowrap;
  border-radius: 6px;
  border: 1px solid var(--ds-border, rgba(0,0,0,.12));
  background: var(--ds-bg-elevated, #fff);
  padding: 4px;
  box-shadow: 0 4px 12px rgba(0,0,0,.12);
  opacity: 1;
}
/* 内层 Toolbar 在浮动条里不换行、不带自己那套相对定位 */
.pltx-ftb-root .pltx-tlb-root {
  position: static;
  flex-wrap: nowrap;
}
.pltx-ftb-root .pltx-tlb-btn {
  height: 28px;
  min-width: 28px;
}
.pltx-ftb-root .pltx-tlb-btn svg {
  width: 15px;
  height: 15px;
}
`;
