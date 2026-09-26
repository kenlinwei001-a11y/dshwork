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

export class PlateDocService extends Service {
  static inject = ['storageDomain'];
  private store?: PlateStore;

  constructor(ctx: Context) {
    super(ctx, 'workdshPlate');
  }

  async [Service.init](): Promise<void> {
    const domain = await this.ctx.storageDomain.open(plateDomainSpec);
    this.ctx.effect(() => () => domain.close(), 'workdshPlate.domainClose');
    this.store = {
      documents: domain.table('documents'),
      revisions: domain.table('revisions'),
    };
  }

  private tables(): PlateStore {
    if (!this.store) throw new Error('workdsh-plate: store not initialized');
    return this.store;
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
