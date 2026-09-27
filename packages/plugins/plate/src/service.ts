import { Context, Service } from '@deepseek-ai/cordis';
import { randomUUID } from 'node:crypto';
import type { PlateDocument, PlateRevision, PlateStore } from './storage.js';
import { documentSchema, plateDomainSpec, revisionSchema, slateJson } from './storage.js';
import { z } from 'zod';

declare module '@deepseek-ai/cordis' {
  interface Context {
    workdshPlate: PlateDocService;
  }
}

export type DefaultEditor = 'office' | 'plate';

// agent 会话（exec.agent.id）→ 待客户端轮询打开的活文档。
export interface PlatePendingEntry {
  sessionId: string;
  documentId: string;
  requestId: string;
}

export class PlateDocService extends Service {
  static inject = ['storageDomain'];
  private store?: PlateStore;
  private defaultEditor: DefaultEditor = 'office';
  private readyResolve!: () => void;
  readonly ready: Promise<void>;
  private pending: PlatePendingEntry[] = [];

  constructor(ctx: Context) {
    super(ctx, 'workdshPlate');
    this.ready = new Promise((resolve) => {
      this.readyResolve = resolve;
    });
  }

  async [Service.init](): Promise<void> {
    const domain = await this.ctx.storageDomain.open(plateDomainSpec);
    this.ctx.effect(() => () => domain.close(), 'workdshPlate.domainClose');
    this.store = {
      documents: domain.table('documents'),
      revisions: domain.table('revisions'),
      settings: domain.table('settings'),
    };
    const saved = this.store.settings.get('default-editor');
    if (saved && (saved.value === 'office' || saved.value === 'plate')) {
      this.defaultEditor = saved.value;
    }
    this.readyResolve();
  }

  private tables(): PlateStore {
    if (!this.store) throw new Error('workdsh-plate: store not initialized');
    return this.store;
  }

  // 同步读缓存：systemPrompt 段 text provider 每次组装同步求值。
  getDefaultEditor(): DefaultEditor {
    return this.defaultEditor;
  }

  setDefaultEditor(editor: DefaultEditor): DefaultEditor {
    this.tables().settings.put('default-editor', { key: 'default-editor', value: editor });
    this.defaultEditor = editor;
    return editor;
  }

  pushPending(entry: PlatePendingEntry): void {
    this.pending.push(entry);
  }

  takePending(sessionId: string): PlatePendingEntry[] {
    const mine = this.pending.filter((p) => p.sessionId === sessionId);
    this.pending = this.pending.filter((p) => p.sessionId !== sessionId);
    return mine;
  }

  listDocuments(): PlateDocument[] {
    const { documents } = this.tables();
    return [...documents.entries()]
      .map(([, doc]) => doc)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }

  openDocument(docId: string): { doc: PlateDocument; head: PlateRevision } {
    const { documents, revisions } = this.tables();
    const doc = documents.get(docId);
    if (!doc) throw new Error('NOT_FOUND');
    const head = revisions.get(doc.headRevId);
    if (!head) throw new Error('HEAD_REVISION_MISSING');
    return { doc, head };
  }

  createDocument(
    title: string,
    content: z.infer<typeof slateJson>,
    cause: 'create' | 'import' = 'create',
  ): { doc: PlateDocument; head: PlateRevision } {
    const { documents, revisions } = this.tables();
    const docId = randomUUID();
    const revId = randomUUID();
    const now = new Date().toISOString();
    const doc = documentSchema.parse({
      id: docId,
      title,
      createdAt: now,
      updatedAt: now,
      headRevId: revId,
    });
    const head = revisionSchema.parse({
      revId,
      docId,
      seq: 0,
      createdAt: now,
      cause,
      slateJson: content,
    });
    revisions.put(revId, head);
    documents.put(docId, doc);
    return { doc, head };
  }

  appendRevision(docId: string, content: z.infer<typeof slateJson>, cause: PlateRevision['cause']): { doc: PlateDocument; head: PlateRevision } {
    const { documents, revisions } = this.tables();
    const doc = documents.get(docId);
    if (!doc) throw new Error('NOT_FOUND');
    const previous = revisions.get(doc.headRevId);
    if (!previous) throw new Error('HEAD_REVISION_MISSING');
    const revId = randomUUID();
    const now = new Date().toISOString();
    const head = revisionSchema.parse({
      revId,
      docId,
      seq: previous.seq + 1,
      createdAt: now,
      cause,
      slateJson: content,
    });
    revisions.put(revId, head);
    const updated = documentSchema.parse({ ...doc, headRevId: revId, updatedAt: now });
    documents.put(docId, updated);
    return { doc: updated, head };
  }
}

export const docIdParam = z.string().min(8).max(64).regex(/^[a-zA-Z0-9_-]+$/);
