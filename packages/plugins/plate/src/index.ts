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
  z.object({
    endpoint: z.literal('ai-stream'),
    docId: docIdParam,
    action: z.enum(['polish', 'continue', 'expand', 'condense', 'proofread', 'translate']),
    text: z.string().min(1).max(8000),
  }).strict(),
]);

// 汉化层：AI 动作 → 中文提示词模板（设计稿 v0.2 的 prompt 中文化）。
const AI_PROMPTS: Record<string, { system: string; user: (text: string) => string }> = {
  polish: {
    system: '你是中文写作助手，输出保持原文句子边界，不拆句不合句。',
    user: (text) => `请润色下面的文本：保持原意，改正生硬与冗余的表达，直接输出润色后的文本，不要任何解释。\n\n${text}`,
  },
  continue: {
    system: '你是中文写作助手，续写风格与原文一致。',
    user: (text) => `请接着下面的文本继续写下去，语气连贯、风格一致，直接输出续写的内容，不要任何解释。\n\n${text}`,
  },
  expand: {
    system: '你是中文写作助手，扩写时保持原文结构与句子边界。',
    user: (text) => `请扩写下面的文本：补充必要的细节与论证，不改变原有结构，直接输出扩写后的全文，不要任何解释。\n\n${text}`,
  },
  condense: {
    system: '你是中文写作助手，压缩时保留核心要点与关键数据。',
    user: (text) => `请压缩下面的文本：保留核心要点与关键数字，删去冗余修饰，直接输出压缩后的文本，不要任何解释。\n\n${text}`,
  },
  proofread: {
    system: '你是中文校对助手，只修正错误，不改写风格。',
    user: (text) => `请校对下面的文本：修正错别字、语法错误与标点问题，直接输出修正后的全文，不要任何解释。\n\n${text}`,
  },
  translate: {
    system: '你是翻译助手，输出译文时保持原文句子边界。',
    user: (text) => `请翻译下面的文本：若原文是中文则译为英文，若原文是英文则译为中文，直接输出译文，不要任何解释。\n\n${text}`,
  },
};

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
      // ai-smoke / ai-stream: build options from the default model selection
      // and stream ctx.llm.stream as SSE text-delta frames.
      const prompt = body.endpoint === 'ai-smoke'
        ? (body.prompt?.trim() ? body.prompt.trim().slice(0, 4000) : '用一句话介绍富文本编辑器。')
        : null;
      const aiAction = body.endpoint === 'ai-stream' ? body.action : null;
      let options: GenerateOptions;
      try {
        const selection = ctx.agentDefaultModel.currentSelection();
        const template = aiAction ? AI_PROMPTS[aiAction] : null;
        const userText = aiAction && body.endpoint === 'ai-stream' ? body.text : prompt!;
        options = {
          provider: selection.provider,
          model: selection.model,
          ...(selection.reasoningEffort
            ? { reasoningEffort: selection.reasoningEffort as ReasoningEffortId }
            : {}),
          system: template?.system ?? '你是中文写作助手，回答简洁。',
          messages: [{
            role: 'user',
            content: [{ type: 'text', text: template ? template.user(userText) : userText }],
          }],
          maxTokens: aiAction ? 2048 : 512,
          signal: request.signal,
        };
      } catch (error) {
        return Response.json({ ok: false, code: 'SELECTION_FAILED', message: String(error) }, { status: 500 });
      }
      if (body.endpoint === 'ai-stream') {
        // The stream must target a real document so the client's cause:'ai'
        // revision lands somewhere; reject unknown ids before burning tokens.
        try {
          ctx.workdshPlate.openDocument(body.docId);
        } catch {
          return Response.json({ ok: false, code: 'NOT_FOUND' }, { status: 404 });
        }
      }
      console.log(`${PREFIX} ${body.endpoint} action=${aiAction ?? '-'} provider=${options.provider} model=${options.model}`);
      return streamLlm(ctx, options);
    },
  });
  ctx.effect(() => () => unregister());
}

// Shared SSE pipe: text-delta frames with per-chunk timestamps, a usage frame
// when the model reports it, then a terminal done/error frame.
function streamLlm(ctx: Context, options: GenerateOptions): Response {
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
}
