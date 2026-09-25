import type { Context } from '@deepseek-ai/cordis';
import type { HostConnectionHandle } from '@deepseek-ai/dsh-client-connection';
import type {} from '@deepseek-ai/dsh-agent-default-model';
import type { GenerateOptions, ReasoningEffortId } from '@deepseek-ai/dsh-llm';
import { PlateDocService, docIdParam } from './service.js';
import { slateJson } from './storage.js';
import { z } from 'zod';

export const name = 'workdsh-plate';
export const inject = ['llm', 'agentDefaultModel', 'connection'];

const PREFIX = '[workdsh-plate]';

const requestShape = z.discriminatedUnion('endpoint', [
  z.object({ endpoint: z.literal('ping') }).strict(),
  z.object({ endpoint: z.literal('ai-smoke'), prompt: z.string().max(4000).optional() }).strict(),
  z.object({ endpoint: z.literal('docs-list') }).strict(),
  z.object({ endpoint: z.literal('doc-create'), title: z.string().min(1).max(256), content: slateJson }).strict(),
  z.object({ endpoint: z.literal('doc-open'), docId: docIdParam }).strict(),
  z.object({ endpoint: z.literal('rev-append'), docId: docIdParam, content: slateJson, cause: z.enum(['edit', 'ai', 'import']) }).strict(),
]);

export async function apply(ctx: Context) {
  await ctx.plugin(PlateDocService);

  // S1/S2 evidence: the llm service is injectable and the default model
  // selection resolves to a concrete provider/model route.
  try {
    const selection = ctx.agentDefaultModel.currentSelection();
    console.log(`${PREFIX} applied; llm.stream=${typeof ctx.llm?.stream === 'function'} selection=${JSON.stringify(selection)}`);
  } catch (error) {
    console.log(`${PREFIX} applied; selection probe failed: ${String(error)}`);
  }

  // The API entry is a separate loader entry so it can inject the service
  // this plugin provides above (self-injection would deadlock at boot).
  await ctx.plugin({
    name: 'workdsh-plate-connection',
    inject: ['connection', 'llm', 'agentDefaultModel', 'workdshPlate'],
    apply(api: Context) {
      registerApi(api);
    },
  });
}

function registerApi(ctx: Context) {
  const connection = (ctx as Context & { connection: HostConnectionHandle }).connection;

  const unregister = connection.fetch.register({
    path: '/api/workdsh-plate',
    methods: ['POST'],
    requestBody: 'buffered',
    async fetch(request) {
      let raw: unknown;
      try {
        raw = await request.json();
      } catch {
        return Response.json({ ok: false, code: 'BAD_JSON' }, { status: 400 });
      }
      const parsed = requestShape.safeParse(raw);
      if (!parsed.success) {
        return Response.json({ ok: false, code: 'BAD_SHAPE', message: parsed.error.issues[0]?.message ?? 'invalid request' }, { status: 400 });
      }
      const body = parsed.data;
      if (body.endpoint === 'ping') {
        return Response.json({ ok: true, name: 'workdsh-plate' });
      }
      if (body.endpoint === 'docs-list') {
        return Response.json({ ok: true, documents: ctx.workdshPlate.listDocuments() });
      }
      if (body.endpoint === 'doc-create') {
        try {
          return Response.json({ ok: true, ...ctx.workdshPlate.createDocument(body.title, body.content) });
        } catch (error) {
          return Response.json({ ok: false, code: 'CREATE_FAILED', message: String(error) }, { status: 500 });
        }
      }
      if (body.endpoint === 'doc-open') {
        try {
          return Response.json({ ok: true, ...ctx.workdshPlate.openDocument(body.docId) });
        } catch {
          return Response.json({ ok: false, code: 'NOT_FOUND' }, { status: 404 });
        }
      }
      if (body.endpoint === 'rev-append') {
        try {
          return Response.json({ ok: true, ...ctx.workdshPlate.appendRevision(body.docId, body.content, body.cause) });
        } catch {
          return Response.json({ ok: false, code: 'NOT_FOUND' }, { status: 404 });
        }
      }
      // ai-smoke
      const prompt = body.prompt?.trim()
        ? body.prompt.trim().slice(0, 4000)
        : '用一句话介绍富文本编辑器。';
      let options: GenerateOptions;
      try {
        const selection = ctx.agentDefaultModel.currentSelection();
        options = {
          provider: selection.provider,
          model: selection.model,
          ...(selection.reasoningEffort
            ? { reasoningEffort: selection.reasoningEffort as ReasoningEffortId }
            : {}),
          system: '你是中文写作助手，回答简洁。',
          messages: [{ role: 'user', content: [{ type: 'text', text: prompt }] }],
          maxTokens: 512,
          signal: request.signal,
        };
      } catch (error) {
        return Response.json({ ok: false, code: 'SELECTION_FAILED', message: String(error) }, { status: 500 });
      }
      console.log(`${PREFIX} ai-smoke provider=${options.provider} model=${options.model}`);
      const encoder = new TextEncoder();
      const started = Date.now();
      const readable = new ReadableStream<Uint8Array>({
        async start(controller) {
          const send = (payload: unknown) =>
            controller.enqueue(encoder.encode(`data: ${JSON.stringify(payload)}\n\n`));
          try {
            for await (const chunk of ctx.llm.stream(options)) {
              if (chunk.type === 'text-delta') {
                send({ t: Date.now() - started, text: chunk.text });
              } else if (chunk.type === 'usage') {
                send({ t: Date.now() - started, usage: chunk.usage });
              }
            }
            send({ t: Date.now() - started, done: true });
          } catch (error) {
            send({ t: Date.now() - started, error: String(error) });
          } finally {
            controller.close();
          }
        },
      });
      return new Response(readable, {
        headers: {
          'content-type': 'text/event-stream; charset=utf-8',
          'cache-control': 'no-cache',
        },
      });
    },
  });
  ctx.effect(() => () => unregister());
}
