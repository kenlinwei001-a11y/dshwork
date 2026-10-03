import * as React from 'react';

export type LogoMarkProps = {
  readonly size?: number;
  readonly title?: string;
};

/** Cross-platform NexusOne mark. The application tile is deliberately kept outside. */
export function LogoMark({ size = 24, title }: LogoMarkProps) {
  const labelled = Boolean(title);
  return (
    <svg width={size} height={size} viewBox="0 0 256 256" role={labelled ? 'img' : undefined} aria-label={title} aria-hidden={labelled ? undefined : true} focusable={false}>
      <path d="M56 194V84c0-19 21-26 31-9l102 116c10 15 31 9 31-12V58" fill="none" stroke="#176BFF" strokeWidth="38" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M203 39c3 14 11 22 25 25-14 3-22 11-25 25-3-14-11-22-25-25 14-3 22-11 25-25z" fill="#18CFE7" />
    </svg>
  );
}
