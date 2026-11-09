/**
 * Package-local on-demand chunks. The client-modules host serves
 * `/plugins/<package>/client.<name>.js?rev=<entry rev>`; the boot manifest is
 * the only public source of that revision. Heavy renderers stay out of the
 * boot bundle and load on first use.
 */
type BootEntry = { readonly id?: string; readonly rev?: string };

let cachedRev: string | undefined;

function entryRev(): string | undefined {
  if (cachedRev !== undefined) return cachedRev;
  try {
    const boot = (window as unknown as { __DSH_BOOT__?: { entries?: readonly BootEntry[] } }).__DSH_BOOT__;
    const rev = boot?.entries?.find(row => row?.id === 'workdsh-plugin-office')?.rev;
    cachedRev = typeof rev === 'string' && rev ? rev : undefined;
  } catch {
    cachedRev = undefined;
  }
  return cachedRev;
}

export function clientChunkUrl(name: string): string {
  const rev = entryRev();
  const path = `plugins/workdsh-plugin-office/client.${name}.js${rev ? `?rev=${encodeURIComponent(rev)}` : ''}`;
  return new URL(path, document.baseURI).href;
}

export function loadClientChunk<T = unknown>(name: string): Promise<T> {
  return import(/* @vite-ignore */ clientChunkUrl(name)) as Promise<T>;
}
