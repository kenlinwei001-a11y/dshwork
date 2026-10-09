import type { Context } from '@deepseek-ai/cordis';
import type { HostConnectionHandle } from '@deepseek-ai/dsh-client-connection';
import type {} from '@deepseek-ai/dsh-agent-default-model';
import type { GenerateOptions, ReasoningEffortId } from '@deepseek-ai/dsh-llm';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { createUIMessageStream, createUIMessageStreamResponse } from 'ai';
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
  // doc-export 随「导出 .plate」功能一并移除（用户 2026-09-29：不需要这个功能）。
  z.object({ endpoint: z.literal('rev-append'), docId: docIdParam, content: slateJson, cause: z.enum(['edit', 'ai', 'import']) }).strict(),
  z.object({
    endpoint: z.literal('ai-command'),
    // AI SDK transport 会在 body 里附带 id 等自有字段，不 strict。
    messages: z.unknown().array().max(64),
    ctx: z.object({
      children: slateJson,
      selection: z.unknown().nullable(),
      toolName: z.enum(['generate', 'edit']),
    }),
  }),
  z.object({ endpoint: z.literal('get-default-editor') }).strict(),
  z.object({ endpoint: z.literal('set-default-editor'), editor: z.enum(['office', 'plate']) }).strict(),
  z.object({ endpoint: z.literal('plate-pending'), sessionId: z.string().max(128) }).strict(),
  z.object({ endpoint: z.literal('docx-import'), path: z.string().min(1).max(1024) }).strict(),
]);

// 「缺省文档编辑器 = NexusAI」时的 agent 写作指南。作为动态 text provider 注册：
// 缺省=office 时返回空串，行为与改前逐字节一致；缺省=plate 时注入本段。
// order 排在 office 指南（TOOL_REPORT）之后，后置+明确禁令覆盖文档类请求；
// PPT/Excel/PDF/HTML 请求仍走 office（content_* 照常）。
const plateGuide = `NexusAI live document writing (the default document editor is NexusAI):
When the user asks you to write a document, report, or Word-style document, use the plate_* tools to write in the live Plate editor on the right. Do NOT use content_* tools for this kind of request; content_* remains only for PPT, Excel, PDF and HTML requests.
First call plate_open with a title and a unique operationId; this immediately opens an empty Plate document on the right. Do this before lengthy planning. Reuse the same operationId on retries. Do not compose the entire report in chat first.
Then call plate_edit to write the title and first useful paragraph, and continue in small meaningful batches so the user sees progress. plate_edit REPLACES the entire document: every call must submit the complete Slate JSON — all previous content plus this batch — never a fragment. Content is Slate editor JSON: an array of nodes, e.g. [{"type":"p","children":[{"text":"标题"}]}]; paragraphs use type "p", headings type "h1".."h3", lists/blocks optional. Keep a single edit under roughly 1 MiB; embedded images are base64 data URLs inside the JSON and count toward the 6 MB document limit, so prefer small images. After a human edit, call plate_read first and re-read the latest content before the next plate_edit; never guess the existing text. Do not fabricate citations, claims or figures.
The deliverable is the live Plate document itself. After finishing, tell the user it is open in the right Plate editor where they can keep editing. Do not claim a file was delivered, offer no download, and do not use Bash/Python or a file-generation skill to build the document; there is no export step for Plate documents.`;

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
    // 路由信号只放条件指南（plateGuide，缺省=plate 时注入），工具描述保持中性：
    // 硬编码「never use content_*」在缺省=office 时是假陈述，会绑架 agent
    // 选 plate_*，导致 office 文档流（content_* → docx 文件卡）断掉。
    description:
      'Create a new empty Plate document and open it in the live right-hand editor immediately, for writing that should appear in the live editor. Pass a title and a unique operationId; reuse the same operationId on retries. New documents start with one empty paragraph. Whether to use plate_* or content_* for a document request is decided by the active authoring guidance in the system prompt.',
    parameters: { title: string, operationId: string },
    output: permissiveOutput,
    execute: async (args, exec) => {
      exec.signal.throwIfAborted();
      const { doc, head } = await ctx.workdshPlate.createDocument(
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
      const { doc, head } = await ctx.workdshPlate.appendRevision(
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
          const created = await ctx.workdshPlate.createDocument(body.title, body.content);
          return Response.json({ ok: true, ...created });
        } catch (error) {
          return Response.json({ ok: false, code: 'CREATE_FAILED', message: String(error) }, { status: 500 });
        }
      }
      if (body.endpoint === 'doc-import') {
        // 从 .plate 文件导入：首修订 cause='import'，与手动新建（'create'）区分。
        try {
          const imported = await ctx.workdshPlate.createDocument(body.title, body.content, 'import');
          return Response.json({ ok: true, ...imported });
        } catch (error) {
          return Response.json({ ok: false, code: 'IMPORT_FAILED', message: String(error) }, { status: 500 });
        }
      }
      if (body.endpoint === 'doc-open') {
        try {
          return Response.json({ ok: true, ...ctx.workdshPlate.openDocument(body.docId) });
        } catch (error) {
          // 区分「文档不存在」与「文档在但 head 修订读不到」：两者都 404，
          // 但后者是写入未落地的一致性问题，报同一个码会把归因带偏。
          const code = error instanceof Error && error.message === 'HEAD_REVISION_MISSING' ? 'HEAD_REVISION_MISSING' : 'NOT_FOUND';
          return Response.json({ ok: false, code }, { status: 404 });
        }
      }
      if (body.endpoint === 'rev-append') {
        try {
          const appended = await ctx.workdshPlate.appendRevision(body.docId, body.content, body.cause);
          return Response.json({ ok: true, ...appended });
        } catch {
          return Response.json({ ok: false, code: 'NOT_FOUND' }, { status: 404 });
        }
      }
      if (body.endpoint === 'get-default-editor') {
        return Response.json({ ok: true, editor: ctx.workdshPlate.getDefaultEditor() });
      }
      if (body.endpoint === 'set-default-editor') {
        await ctx.workdshPlate.setDefaultEditor(body.editor);
        return Response.json({ ok: true, editor: ctx.workdshPlate.getDefaultEditor() });
      }
      if (body.endpoint === 'plate-pending') {
        return Response.json({ ok: true, requests: ctx.workdshPlate.takePending(body.sessionId) });
      }
      if (body.endpoint === 'docx-import') {
        // 「用 NexusAI 打开」：读 docx 文件 → 解析成 Slate JSON → 导入 plate 域。
        try {
          const { title, content } = await importDocx(body.path);
          const { doc, head } = await ctx.workdshPlate.createDocument(title, content as unknown as z.infer<typeof slateJson>, 'import');
          return Response.json({ ok: true, doc, head: { seq: head.seq } });
        } catch (error) {
          return Response.json({ ok: false, code: 'DOCX_IMPORT_FAILED', message: String(error) }, { status: 400 });
        }
      }
      if (body.endpoint === 'ai-command') {
        // v1.5.0 原生 AI 菜单的命令流：最后一条用户消息是客户端拼好的完整
        // 提示词（模板+选区 Markdown），按 AI SDK UI message stream 协议回码。
        let options: GenerateOptions;
        try {
          const selection = ctx.agentDefaultModel.currentSelection();
          const messages = body.messages as Array<{ parts?: Array<{ type?: string; text?: string }> }>;
          const lastWithText = [...messages].reverse().find((m) => m.parts?.some((p) => p.type === 'text'));
          const prompt = lastWithText?.parts?.find((p) => p.type === 'text')?.text?.trim();
          if (!prompt) {
            return Response.json({ ok: false, code: 'EMPTY_PROMPT' }, { status: 400 });
          }
          options = {
            provider: selection.provider,
            model: selection.model,
            ...(selection.reasoningEffort
              ? { reasoningEffort: selection.reasoningEffort as ReasoningEffortId }
              : {}),
            system: '你是中文写作助手。按用户指令处理文档内容，只输出结果的 Markdown（保留标题、加粗、段落结构），不要任何解释与前后缀。',
            messages: [{
              role: 'user',
              content: [{ type: 'text', text: prompt }],
            }],
            maxTokens: 2048,
            signal: request.signal,
          };
        } catch (error) {
          return Response.json({ ok: false, code: 'SELECTION_FAILED', message: String(error) }, { status: 500 });
        }
        console.log(`${PREFIX} ai-command tool=${body.ctx.toolName} provider=${options.provider} model=${options.model}`);
        return streamUiMessages(ctx, options);
      }
      // ai-smoke: build options from the default model selection and stream
      // ctx.llm.stream as SSE text-delta frames.
      const prompt = body.endpoint === 'ai-smoke'
        ? (body.prompt?.trim() ? body.prompt.trim().slice(0, 4000) : '用一句话介绍富文本编辑器。')
        : null;
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
          messages: [{
            role: 'user',
            content: [{ type: 'text', text: prompt! }],
          }],
          maxTokens: 512,
          signal: request.signal,
        };
      } catch (error) {
        return Response.json({ ok: false, code: 'SELECTION_FAILED', message: String(error) }, { status: 500 });
      }
      console.log(`${PREFIX} ${body.endpoint} provider=${options.provider} model=${options.model}`);
      return streamLlm(ctx, options);
    },
  });
  ctx.effect(() => () => unregister());
}

// v1.5.0：AI SDK UI message stream（text-start/text-delta/text-end/finish）。
// 协议编码交给 ai 包的 createUIMessageStream —— 客户端 DefaultChatTransport
// 解码后走官方 AIChat 流式管线（insert 模式流式插入 / edit 模式建议 diff）。
let uiStreamSeq = 0;
function streamUiMessages(ctx: Context, options: GenerateOptions): Response {
  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      uiStreamSeq += 1;
      const id = `pltx-${Date.now()}-${uiStreamSeq}`;
      writer.write({ type: 'text-start', id });
      try {
        for await (const chunk of ctx.llm.stream(options)) {
          if (chunk.type === 'text-delta') {
            writer.write({ type: 'text-delta', id, delta: chunk.text });
          }
        }
        writer.write({ type: 'text-end', id });
        writer.write({ type: 'finish', finishReason: 'stop' });
      } catch (error) {
        // 流中出错：标 error 而非静默空完成，避免客户端把空回当正常结果 Accept。
        console.error(`${PREFIX} ai-command stream error: ${String(error)}`);
        writer.write({ type: 'text-end', id });
        writer.write({ type: 'finish', finishReason: 'error' });
      }
    },
  });
  return createUIMessageStreamResponse({ stream });
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
