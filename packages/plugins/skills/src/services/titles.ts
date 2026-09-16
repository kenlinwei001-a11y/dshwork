import { mkdir, readFile, rename, stat, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

/**
 * WorkDSH-owned display-title overrides for installed skills.
 *
 * Plain data below the skills state root (`titles.json`); the store owns only
 * the `{ name: title }` map. Identity (frontmatter name, directory, `/name`
 * invocation) stays with Harness — an override never renames anything and a
 * cleared override restores the default display with no residue.
 */
const TITLE_SCHEMA = 1;
const TITLE_LIMIT = 80;

interface TitleFile {
  readonly schema: number;
  readonly overrides: Record<string, string>;
}

function sanitize(title: string): string {
  return title.replace(/[\r\n]+/g, ' ').trim().slice(0, TITLE_LIMIT);
}

export class SkillTitleStore {
  private readonly root: string;
  private readonly file: string;
  private cache?: { readonly signature: string; readonly overrides: Readonly<Record<string, string>> };
  private writing: Promise<unknown> = Promise.resolve();

  constructor(root: string) {
    this.root = root;
    this.file = join(root, 'titles.json');
  }

  /** All overrides, keyed by skill name. Missing or malformed file degrades to empty. */
  async all(): Promise<Readonly<Record<string, string>>> {
    let signature = '';
    try {
      const info = await stat(this.file);
      signature = `${info.mtimeMs}:${info.size}`;
    } catch {
      return {};
    }
    if (this.cache?.signature === signature) return this.cache.overrides;
    let raw: unknown;
    try {
      raw = JSON.parse(await readFile(this.file, 'utf8'));
    } catch {
      return {};
    }
    const source = raw !== null && typeof raw === 'object' && !Array.isArray(raw) ? (raw as { schema?: unknown; overrides?: unknown }) : {};
    const entries = source.schema === TITLE_SCHEMA && source.overrides !== null && typeof source.overrides === 'object' && !Array.isArray(source.overrides)
      ? Object.entries(source.overrides as Record<string, unknown>)
      : [];
    const overrides: Record<string, string> = {};
    for (const [name, value] of entries) {
      if (typeof value !== 'string') continue;
      const title = sanitize(value);
      if (title) overrides[name] = title;
    }
    this.cache = { signature, overrides };
    return overrides;
  }

  /**
   * Sets or clears (`null`, empty, or equal to the skill name) one override.
   * Writers are serialized and each write is atomic (tmp file + rename), so a
   * crashed host never leaves a half-written titles file behind.
   */
  async set(name: string, title: string | null): Promise<string | undefined> {
    const operation = this.writing.then(async () => {
      const current = { ...(await this.all()) };
      const next = title === null ? '' : sanitize(title);
      if (!next || next === name) delete current[name];
      else current[name] = next;
      await mkdir(this.root, { recursive: true });
      const temporary = `${this.file}.${process.pid}.tmp`;
      const payload: TitleFile = { schema: TITLE_SCHEMA, overrides: current };
      await writeFile(temporary, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
      await rename(temporary, this.file);
      const info = await stat(this.file);
      this.cache = { signature: `${info.mtimeMs}:${info.size}`, overrides: current };
      return current[name];
    });
    this.writing = operation.catch(() => undefined);
    return operation;
  }
}
