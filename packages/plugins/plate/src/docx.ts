// v1.4.0：docx → Slate JSON 转换（「用 NexusAI 打开」的服务端半）。
// 只读 node:fs（experts/library/skills 插件同款先例；office 走 bash 是交付
// 策略非硬限）。解析对齐 office 编码器 src/live/docx.ts 的输出结构：
// w:p/w:pStyle HeadingN/w:r/w:t/w:b/w:i/a:blip r:embed→rels→media。
import { readFile } from 'node:fs/promises';
import JSZip from 'jszip';

const MAX_DOCX_BYTES = 10 * 1024 * 1024;
const MAX_IMAGE_BYTES = 1_500_000; // 单图（镜像客户端插图上限）
const MAX_IMAGE_TOTAL = 5_500_000; // 图片累计，给文本留余量（文档总上限 6MB 由 schema 兜底）

type SlateNode = {
  type?: string;
  text?: string;
  bold?: boolean;
  italic?: boolean;
  url?: string;
  children?: SlateNode[];
};

function decodeXml(text: string): string {
  return text
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex: string) => String.fromCodePoint(parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_, dec: string) => String.fromCodePoint(parseInt(dec, 10)))
    .replace(/&amp;/g, '&');
}

const textNode = (text: string, marks: { bold?: boolean; italic?: boolean } = {}): SlateNode => ({
  text,
  ...(marks.bold ? { bold: true } : {}),
  ...(marks.italic ? { italic: true } : {}),
});

const paragraph = (type: string, children: SlateNode[]): SlateNode => ({
  type,
  children: children.length ? children : [{ text: '' }],
});

const placeholder = (message: string): SlateNode =>
  paragraph('p', [{ text: message, italic: true }]);

// r:embed id → dataURL（懒加载，避免没图的文档也读 media）。
function mediaLoader(zip: JSZip, relsXml: string, budget: { remaining: number }) {
  const rels = new Map<string, { type: string; target: string }>();
  for (const m of relsXml.matchAll(/<Relationship\b[^>]*\bId="([^"]+)"[^>]*\bType="([^"]+)"[^>]*\bTarget="([^"]+)"|<Relationship\b[^>]*\bType="([^"]+)"[^>]*\bTarget="([^"]+)"[^>]*\bId="([^"]+)"/g)) {
    const id = m[1] ?? m[6];
    const type = m[2] ?? m[4];
    const target = m[3] ?? m[5];
    if (id) rels.set(id, { type, target });
  }
  const mediaCache = new Map<string, string>();
  return async (embed: string): Promise<{ url?: string; skipped: string }> => {
    const rel = rels.get(embed);
    if (!rel) return { skipped: '（图片关系缺失未导入）' };
    if (!rel.type.includes('/image')) return { skipped: '（图表暂不支持转换）' };
    const ext = rel.target.split('.').pop()?.toLowerCase() ?? 'png';
    if (!['png', 'jpeg', 'jpg', 'gif', 'webp'].includes(ext)) return { skipped: '（图片格式不支持）' };
    if (mediaCache.has(embed)) return { url: mediaCache.get(embed), skipped: '' };
    const entry = zip.file(`word/${rel.target}`);
    if (!entry) return { skipped: '（图片内容缺失）' };
    const bytes = await entry.async('uint8array');
    if (bytes.length > MAX_IMAGE_BYTES || bytes.length > budget.remaining) {
      budget.remaining = Math.max(0, budget.remaining - bytes.length);
      return { skipped: '（图片过大未导入）' };
    }
    budget.remaining -= bytes.length;
    const base64 = Buffer.from(bytes).toString('base64');
    const url = `data:image/${ext === 'jpg' ? 'jpeg' : ext};base64,${base64}`;
    mediaCache.set(embed, url);
    return { url, skipped: '' };
  };
}

export async function importDocx(path: string): Promise<{ title: string; content: SlateNode[] }> {
  if (!path.toLowerCase().endsWith('.docx')) throw new Error('只支持 .docx 文件');
  const bytes = await readFile(path);
  if (bytes.length > MAX_DOCX_BYTES) throw new Error('docx 超过 10MB 上限');

  let zip: JSZip;
  try {
    zip = await JSZip.loadAsync(bytes);
  } catch {
    throw new Error('不是有效的 docx 文件');
  }
  const documentXml = await zip.file('word/document.xml')?.async('string');
  if (!documentXml) throw new Error('不是有效的 docx 文件（缺少 word/document.xml）');
  const relsXml = (await zip.file('word/_rels/document.xml.rels')?.async('string')) ?? '';
  const loadMedia = mediaLoader(zip, relsXml, { remaining: MAX_IMAGE_TOTAL });

  const body = documentXml.replace(/^[\s\S]*?<w:body\b[^>]*>/, '').replace(/<\/w:body>[\s\S]*$/, '');
  const content: SlateNode[] = [];

  // 顶层单位：段落或表格（v1 表格占位）。docx 的 w:p 不嵌套（表格除外）。
  const units = body.match(/<w:p\b[^>]*>[\s\S]*?<\/w:p>|<w:tbl\b[^>]*>[\s\S]*?<\/w:tbl>/g) ?? [];
  for (const unit of units) {
    if (unit.startsWith('<w:tbl')) {
      content.push(placeholder('（表格暂不支持转换）'));
      continue;
    }
    const style = unit.match(/<w:pStyle[^>]*\bw:val="([^"]+)"/)?.[1] ?? '';
    const heading = style.match(/^Heading(\d)$/)?.[1];
    const type = heading ? `h${Math.min(Number(heading), 3)}` : 'p';
    const children: SlateNode[] = [];
    // 连续相同标记的 run 合并成一个 leaf（office 每 run 一个 w:t）。
    let pending = { text: '', bold: false, italic: false };
    const flush = () => {
      // 空 leaf 不落（段尾空内容由 paragraph() 兜底 {text:''}），
      // 避免图片前后出现无内容文本节点。
      if (pending.text.length) children.push(textNode(pending.text, pending));
      pending = { text: '', bold: false, italic: false };
    };
    for (const run of unit.matchAll(/<w:r\b[^>]*>([\s\S]*?)<\/w:r>/g)) {
      const inner = run[1];
      const bold = /(?<!\/)<w:b\b[^>]*>/.test(inner);
      const italic = /(?<!\/)<w:i\b[^>]*>/.test(inner);
      const drawing = inner.match(/<a:blip[^>]*\br:embed="([^"]+)"/);
      if (drawing) {
        flush();
        const { url, skipped } = await loadMedia(drawing[1]);
        if (url) children.push({ type: 'img', url, children: [{ text: '' }] });
        else children.push(textNode(skipped, { italic: true }));
        continue;
      }
      let text = '';
      for (const t of inner.matchAll(/<w:t\b[^>]*>([\s\S]*?)<\/w:t>/g)) text += decodeXml(t[1]);
      text = text.replace(/<w:tab\s*\/>/g, '  ').replace(/<w:br\s*\/>/g, '\n');
      if (!text) continue;
      if (bold !== pending.bold || italic !== pending.italic) flush();
      pending.text += text;
      pending.bold = bold;
      pending.italic = italic;
    }
    flush();
    content.push(paragraph(type, children));
  }

  const basename = path.split('/').pop() ?? '文档';
  const title = basename
    .replace(/\.docx$/i, '')
    // office 导出文件名 = `${title}-r${revision}-${identity}-${digest}.docx`（export.ts:45）
    .replace(/-r\d+-[0-9a-f]{16}-[0-9a-f]{64}$/i, '')
    .trim() || 'Word 文档';
  return { title, content };
}
