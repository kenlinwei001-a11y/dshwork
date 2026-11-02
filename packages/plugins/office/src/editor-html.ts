/**
 * The Office editor document is ~20 MB of inlined JS/CSS/fonts. Keeping it in
 * the client entry made every page boot download it; it is now emitted as a
 * package-local client chunk and fetched only when an Office preview opens.
 *
 * The chunk route is package-local and revisioned by the client-modules system:
 * `/plugins/<package>/client.<name>.js?rev=<entry rev>`. The boot manifest is
 * the only public source of that rev.
 */
type BootEntry = { readonly id?: string; readonly rev?: string };

let pending: Promise<string> | undefined;

function chunkUrl(): string {
  const boot = (window as unknown as { __DSH_BOOT__?: { entries?: readonly BootEntry[] } }).__DSH_BOOT__;
  const rev = boot?.entries?.find(row => row?.id === 'workdsh-plugin-office')?.rev;
  const path = `plugins/workdsh-plugin-office/client.office-editor.js${typeof rev === 'string' && rev ? `?rev=${encodeURIComponent(rev)}` : ''}`;
  return new URL(path, document.baseURI).href;
}

export function loadEditorHtml(): Promise<string> {
  if (!pending) {
    pending = import(/* @vite-ignore */ chunkUrl()).then(
      (module: { default?: unknown }) => {
        const html = typeof module.default === 'string' ? module.default : '';
        if (!html) throw new Error('office/editor-chunk-empty');
        return html;
      },
      (cause: unknown) => {
        pending = undefined;
        throw cause;
      },
    );
  }
  return pending;
}
