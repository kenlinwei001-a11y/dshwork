import type { Context } from '@deepseek-ai/cordis';
import type { HostConnectionHandle } from '@deepseek-ai/dsh-client-connection';
import type {} from '@deepseek-ai/dsh-agent-default-model';
import type { GenerateOptions, ReasoningEffortId } from '@deepseek-ai/dsh-llm';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { PlateDocService, docIdParam } from './service.js';
import { slateJson } from './storage.js';
import { importDocx } from './docx.js';
import { z } from 'zod';

export const name = 'workdsh-plate';
export const inject = ['llm', 'agentDefaultModel', 'connection', 'tools', 'systemPrompt'];

const PREFIX = '[workdsh-plate]';

const requestShape = z.discriminatedUnion('endpoint', [
  z.object({ endpoint: z.literal('ping') }).strict(),
  z.object({ endpoint: z.literal('ai-smoke'), prompt: z.string().max(4000).optional() }).strict(),
  z.object({ endpoint: z.literal('docs-list') }).strict(),
  z.object({ endpoint: z.literal('doc-create'), title: z.string().min(1).max(256), content: slateJson }).strict(),
  z.object({ endpoint: z.literal('doc-import'), title: z.string().min(1).max(256), content: slateJson }).strict(),
  z.object({ endpoint: z.literal('doc-open'), docId: docIdParam }).strict(),
  z.object({ endpoint: z.literal('doc-export'), docId: docIdParam }).strict(),
  z.object({ endpoint: z.literal('rev-append'), docId: docIdParam, content: slateJson, cause: z.enum(['edit', 'ai', 'import']) }).strict(),
  z.object({
    endpoint: z.literal('ai-stream'),
    docId: docIdParam,
    action: z.enum(['polish', 'continue', 'expand', 'condense', 'proofread', 'translate']),
    text: z.string().min(1).max(8000),
  }).strict(),
  z.object({ endpoint: z.literal('get-default-editor') }).strict(),
  z.object({ endpoint: z.literal('set-default-editor'), editor: z.enum(['office', 'plate']) }).strict(),
  z.object({ endpoint: z.literal('plate-pending'), sessionId: z.string().max(128) }).strict(),
  z.object({ endpoint: z.literal('docx-import'), path: z.string().min(1).max(1024) }).strict(),
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

// 「缺省文档编辑器 = PlateAI」时的 agent 写作指南。作为动态 text provider 注册：
// 缺省=office 时返回空串，行为与改前逐字节一致；缺省=plate 时注入本段。
// order 排在 office 指南（TOOL_REPORT）之后，后置+明确禁令覆盖文档类请求；
// PPT/Excel/PDF/HTML 请求仍走 office（content_* 照常）。
const plateGuide = `PlateAI live document writing (the default document editor is PlateAI):
When the user asks you to write a document, report, or Word-style document, use the plate_* tools to write in the live Plate editor on the right. Do NOT use content_* tools for this kind of request; content_* remains only for PPT, Excel, PDF and HTML requests.
First call plate_open with a title and a unique operationId; this immediately opens an empty Plate document on the right. Do this before lengthy planning. Reuse the same operationId on retries. Do not compose the entire report in chat first.
Then call plate_edit to write the title and first useful paragraph, and continue in small meaningful batches so the user sees progress. plate_edit REPLACES the entire document: every call must submit the complete Slate JSON — all previous content plus this batch — never a fragment. Content is Slate editor JSON: an array of nodes, e.g. [{"type":"p","children":[{"text":"标题"}]}]; paragraphs use type "p", headings type "h1".."h3", lists/blocks optional. Keep a single edit under roughly 1 MiB; embedded images are base64 data URLs inside the JSON and count toward the 6 MB document limit, so prefer small images. After a human edit, call plate_read first and re-read the latest content before the next plate_edit; never guess the existing text. Do not fabricate citations, claims or figures.
The deliverable is the live Plate document itself. After finishing, tell the user it is open in the right Plate editor where they can keep editing and click 导出 .plate to download. Do not claim a file was delivered, and do not use Bash/Python or a file-generation skill to build the document.`;

// Tool 参数/输出 schema（镜像 office：string = {type:'string', required:true}）。
const string = { type: 'string', required: true } as const;
const slateContentSchema = {
  type: 'array',
  required: true,
  items: { type: 'object', additionalProperties: true },
} as const;
const render = (_args: unknown, value: unknown) => [
  { type: 'text' as const, text: JSON.stringify(value) },
];
const permissiveOutput = {
  schema: { type: 'object', additionalProperties: true } as const,
  render,
};

function registerTools(ctx: Context) {
  for (const toolName of ['plate_open', 'plate_read', 'plate_edit']) {
    if (ctx.tools.get(toolName)) {
      throw new Error(`Plate tool name already registered: ${toolName}`);
    }
  }
  ctx.effect(() => ctx.tools.register(defineTool({
    name: 'plate_open',
    description:
      'Create a new Plate document and open it in the live right-hand editor immediately. Use this for document/report/Word-style requests (the default document editor is PlateAI); never use content_* for these. Pass a title and a unique operationId; reuse the same operationId on retries. New documents start with one empty paragraph.',
    parameters: { title: string, operationId: string },
    output: permissiveOutput,
    execute: async (args, exec) => {
      exec.signal.throwIfAborted();
      const { doc, head } = ctx.workdshPlate.createDocument(
        args.title,
        [{ type: 'p', children: [{ text: '' }] }],
        'create',
      );
      ctx.workdshPlate.pushPending({
        sessionId: exec.agent ? String(exec.agent.id) : '',
        documentId: doc.id,
        requestId: args.operationId,
      });
      return { documentId: doc.id, title: doc.title, revision: head.seq };
    },
  })));
  ctx.effect(() => ctx.tools.register(defineTool({
    name: 'plate_read',
    description:
      'Read the latest committed content of a Plate document. Re-read after a human edit or before every plate_edit; never guess the existing text. Returns the complete Slate JSON the next plate_edit must be based on.',
    parameters: { documentId: string },
    output: permissiveOutput,
    execute: async (args, exec) => {
      exec.signal.throwIfAborted();
      const { doc, head } = ctx.workdshPlate.openDocument(args.documentId);
      // JSON 往返保证 wire 安全（同 office 的 jsonValue 过滤思路）。
      return { documentId: doc.id, title: doc.title, revision: head.seq, content: JSON.parse(JSON.stringify(head.slateJson)) };
    },
  })));
  ctx.effect(() => ctx.tools.register(defineTool({
    name: 'plate_edit',
    description:
      'Replace the ENTIRE content of a Plate document in one commit: submit the complete Slate JSON — all previous content plus this batch — never a fragment. Use after plate_read, in small meaningful batches (title and first paragraph first), so the user sees progress. Paragraphs are {"type":"p","children":[{"text":"..."}]}; headings {"type":"h1".."h3","children":[...]}. Keep one edit under roughly 1 MiB; the whole document must stay under 6 MB (embedded images are base64 data URLs).',
    parameters: { documentId: string, content: slateContentSchema },
    output: permissiveOutput,
    execute: async (args, exec) => {
      exec.signal.throwIfAborted();
      const { doc, head } = ctx.workdshPlate.appendRevision(
        args.documentId,
        args.content as unknown as z.infer<typeof slateJson>,
        'ai',
      );
      return { documentId: doc.id, revision: head.seq };
    },
  })));
}

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

  // 「缺省文档编辑器」开关的 agent 侧效果：动态段逐次组装求值，读服务端缓存。
  // 根插件不能注入自己提供的 workdshPlate（自注入死锁），提示词段与工具、
  // 连接一样走子插件绕行——否则每次 prompt 组装都会抛 "without inject"。
  await ctx.plugin({
    name: 'workdsh-plate-prompt',
    inject: ['systemPrompt', 'workdshPlate'],
    apply(api: Context) {
      api.effect(() => api.systemPrompt.section({
        name: 'workdsh:plate-authoring',
        order: api.systemPrompt.getSectionOrder('TOOL_REPORT') + 1,
        text: () => (api.workdshPlate.getDefaultEditor() === 'plate' ? plateGuide : ''),
      }));
    },
  });

  // plate_* 工具链：与 office 的 content_* 平行的 agent 入口。
  await ctx.plugin({
    name: 'workdsh-plate-tools',
    inject: ['tools', 'workdshPlate'],
    apply(api: Context) {
      registerTools(api);
    },
  });

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
      if (body.endpoint === 'doc-import') {
        // 从 .plate 文件导入：首修订 cause='import'，与手动新建（'create'）区分。
        try {
          return Response.json({ ok: true, ...ctx.workdshPlate.createDocument(body.title, body.content, 'import') });
        } catch (error) {
          return Response.json({ ok: false, code: 'IMPORT_FAILED', message: String(error) }, { status: 500 });
        }
      }
      if (body.endpoint === 'doc-open' || body.endpoint === 'doc-export') {
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
      if (body.endpoint === 'get-default-editor') {
        return Response.json({ ok: true, editor: ctx.workdshPlate.getDefaultEditor() });
      }
      if (body.endpoint === 'set-default-editor') {
        ctx.workdshPlate.setDefaultEditor(body.editor);
        return Response.json({ ok: true, editor: ctx.workdshPlate.getDefaultEditor() });
      }
      if (body.endpoint === 'plate-pending') {
        return Response.json({ ok: true, requests: ctx.workdshPlate.takePending(body.sessionId) });
      }
      if (body.endpoint === 'docx-import') {
        // 「用 PlateAI 打开」：读 docx 文件 → 解析成 Slate JSON → 导入 plate 域。
        try {
          const { title, content } = await importDocx(body.path);
          const { doc, head } = ctx.workdshPlate.createDocument(title, content as unknown as z.infer<typeof slateJson>, 'import');
          return Response.json({ ok: true, doc, head: { seq: head.seq } });
        } catch (error) {
          return Response.json({ ok: false, code: 'DOCX_IMPORT_FAILED', message: String(error) }, { status: 400 });
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
