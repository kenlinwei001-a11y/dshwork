import { loadClientChunk } from './client-chunk.js';

/**
 * The Office editor document is ~20 MB of inlined JS/CSS/fonts. It ships as the
 * `office-editor` package-local chunk and is fetched only when an Office
 * preview opens.
 */
let pending: Promise<string> | undefined;

export function loadEditorHtml(): Promise<string> {
  if (!pending) {
    pending = loadClientChunk<{ default?: unknown }>('office-editor').then(
      module => {
        const html = typeof module.default === 'string' ? module.default : '';
        if (!html) throw new Error('office/editor-chunk-empty');
        return html;
      },
      cause => {
        pending = undefined;
        throw cause;
      },
    );
  }
  return pending;
}
