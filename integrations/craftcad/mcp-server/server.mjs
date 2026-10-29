#!/usr/bin/env node
// CraftCAD MCP server (stdio).
// Exposes headless drawing tools backed by the CraftCAD source tree:
// create/load/modify drawings in memory, save to DXF, query contents.
// The web UI at http://127.0.0.1:8080 can open the saved DXF (Ctrl+O or drag & drop).

import { createInterface } from 'node:readline';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { basename, dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = process.env.CRAFTCAD_DIR
  ? resolve(process.env.CRAFTCAD_DIR)
  : '/Users/apple/Desktop/CraftCAD';
const imp = (rel) => import(pathToFileURL(resolve(ROOT, rel)).href);

const { Drawing } = await imp('src/core/document.ts');
const { readDxf } = await imp('src/io/dxfReader.ts');
const { writeDxf } = await imp('src/io/dxfWriter.ts');
const { loadDxfData } = await imp('src/io/files.ts');
const { entTransform } = await imp('src/core/entities.ts');
const { mxTranslate, mxRotate, mxScale, mxMirror, boxValid } = await imp('src/core/geom.ts');

// ---------------------------------------------------------------------------
// Drawing registry

const drawings = new Map();
let nextDrawing = 1;

const SERVER = { name: 'craftcad-mcp', version: '0.1.0' };

function getDrawing(id) {
  const d = drawings.get(id);
  if (!d) throw new Error(`Unknown drawingId "${id}". Create one with craftcad_new_drawing or craftcad_load_dxf first.`);
  return d;
}

const boxOut = (b) => (boxValid(b)
  ? { minX: r6(b.minX), minY: r6(b.minY), maxX: r6(b.maxX), maxY: r6(b.maxY), width: r6(b.maxX - b.minX), height: r6(b.maxY - b.minY) }
  : null);
const r6 = (v) => Math.round(v * 1e6) / 1e6;

// ---------------------------------------------------------------------------
// Entity input normalization (accepts friendly input, fills entity defaults)

const D2R = (d) => (d * Math.PI) / 180;

const vec = (v, field) => {
  if (!v || !Number.isFinite(v.x) || !Number.isFinite(v.y)) {
    throw new Error(`${field} must be an object {x, y} with finite numbers.`);
  }
  return { x: v.x, y: v.y };
};
const num = (v, field, min = -Infinity) => {
  if (!Number.isFinite(v)) throw new Error(`${field} must be a finite number.`);
  if (v < min) throw new Error(`${field} must be >= ${min}.`);
  return v;
};
const optNum = (v, field, def, min = -Infinity) => (v === undefined ? def : num(v, field, min));

function commonProps(e) {
  const p = {};
  if (e.layer !== undefined) p.layer = String(e.layer);
  if (e.color !== undefined) p.color = num(e.color, 'color', 0);
  if (e.ltype !== undefined) p.ltype = String(e.ltype);
  return p;
}

function normEntity(e) {
  if (!e || typeof e !== 'object' || !e.type) throw new Error('Each entity needs a "type" field.');
  const p = commonProps(e);
  switch (e.type) {
    case 'line':
      return { type: 'line', p1: vec(e.p1, 'p1'), p2: vec(e.p2, 'p2'), ...p };
    case 'circle':
      return { type: 'circle', c: vec(e.c, 'c'), r: num(e.r, 'r', 1e-9), ...p };
    case 'arc':
      return {
        type: 'arc', c: vec(e.c, 'c'), r: num(e.r, 'r', 1e-9),
        a0: D2R(num(e.a0, 'a0')), a1: D2R(num(e.a1, 'a1')), ...p,
      };
    case 'polyline': {
      if (!Array.isArray(e.pts) || e.pts.length < 2) throw new Error('polyline needs pts: at least 2 {x,y} points.');
      const pts = e.pts.map((q, i) => vec(q, `pts[${i}]`));
      const bulges = Array.isArray(e.bulges) ? e.bulges.map((b, i) => num(b, `bulges[${i}]`)) : pts.map(() => 0);
      const out = { type: 'polyline', pts, bulges, closed: !!e.closed, ...p };
      if (e.width !== undefined) out.width = num(e.width, 'width', 0);
      return out;
    }
    case 'ellipse':
      return {
        type: 'ellipse', c: vec(e.c, 'c'), major: vec(e.major, 'major'),
        ratio: num(e.ratio, 'ratio', 1e-9),
        a0: D2R(optNum(e.a0, 'a0', 0)), a1: D2R(optNum(e.a1, 'a1', 360)), ...p,
      };
    case 'point':
      return { type: 'point', p: vec(e.p, 'p'), ...p };
    case 'text':
      return {
        type: 'text', p: vec(e.p, 'p'), h: num(e.h, 'h', 1e-9), text: String(e.text ?? ''),
        rot: D2R(optNum(e.rot, 'rot', 0)), halign: optNum(e.halign, 'halign', 0),
        valign: optNum(e.valign, 'valign', 0), wf: optNum(e.wf, 'wf', 1), ...p,
      };
    case 'mtext':
      return {
        type: 'mtext', p: vec(e.p, 'p'), h: num(e.h, 'h', 1e-9), text: String(e.text ?? ''),
        rot: D2R(optNum(e.rot, 'rot', 0)), width: optNum(e.width, 'width', 0),
        attach: optNum(e.attach, 'attach', 1), ...p,
      };
    case 'dimension': {
      const dimType = e.dimType;
      if (!['linear', 'aligned', 'radius', 'diameter', 'angular'].includes(dimType)) {
        throw new Error('dimension.dimType must be one of linear, aligned, radius, diameter, angular.');
      }
      const out = {
        type: 'dimension', dimType,
        p1: vec(e.p1, 'p1'), p2: vec(e.p2, 'p2'),
        loc: vec(e.loc, 'loc'),
        rot: D2R(optNum(e.rot, 'rot', 0)), ...p,
      };
      if (dimType === 'angular') out.p3 = vec(e.p3, 'p3');
      if (e.textOverride !== undefined) out.textOverride = String(e.textOverride);
      return out;
    }
    default:
      throw new Error(`Unsupported entity type "${e.type}". Supported: line, circle, arc, polyline, ellipse, point, text, mtext, dimension.`);
  }
}

// ---------------------------------------------------------------------------
// Tools

const TOOLS = [
  {
    name: 'craftcad_new_drawing',
    description: 'Create a new empty CraftCAD drawing (model space, layer "0"). Returns a drawingId used by the other tools. The drawing lives in this MCP server process until saved to DXF.',
    inputSchema: {
      type: 'object',
      properties: { name: { type: 'string', description: 'Drawing name (default Drawing1).' } },
      additionalProperties: false,
    },
  },
  {
    name: 'craftcad_load_dxf',
    description: 'Load an ASCII DXF file from disk into a new in-memory drawing. Returns a drawingId plus entity/layer counts and extents.',
    inputSchema: {
      type: 'object',
      properties: { path: { type: 'string', description: 'Absolute path, or a path relative to the MCP server process cwd.' } },
      required: ['path'],
      additionalProperties: false,
    },
  },
  {
    name: 'craftcad_add_entities',
    description: [
      'Add entities to a drawing. Coordinates are drawing units; angles are in degrees.',
      'Entity shapes (JSON):',
      'line {p1:{x,y}, p2:{x,y}}',
      'circle {c:{x,y}, r}',
      'arc {c:{x,y}, r, a0, a1} (degrees, counter-clockwise)',
      'polyline {pts:[{x,y},...], bulges?:number[], closed?:boolean, width?:number} (bulge 1 = half circle)',
      'ellipse {c, major:{x,y} (half-axis vector), ratio, a0?, a1?}',
      'point {p:{x,y}}',
      'text {p:{x,y}, h, text, rot?, halign? (0 left,1 center,2 right,4 middle), valign? (0 baseline,1 bottom,2 middle,3 top)}',
      'mtext {p:{x,y}, h, text, width?, rot?, attach? (1..9)}',
      'dimension {dimType:"linear"|"aligned"|"radius"|"diameter"|"angular", p1, p2, p3? (angular), loc, rot?, textOverride?}',
      'Every entity may also set layer, color (AutoCAD color index 1-255, 7 = default), ltype.',
    ].join('\n'),
    inputSchema: {
      type: 'object',
      properties: {
        drawingId: { type: 'string' },
        entities: { type: 'array', minItems: 1, items: { type: 'object', properties: { type: { type: 'string' } }, required: ['type'] } },
      },
      required: ['drawingId', 'entities'],
      additionalProperties: false,
    },
  },
  {
    name: 'craftcad_move_entities',
    description: 'Translate existing entities by (dx, dy).',
    inputSchema: {
      type: 'object',
      properties: {
        drawingId: { type: 'string' },
        ids: { type: 'array', items: { type: 'number' }, minItems: 1 },
        dx: { type: 'number' },
        dy: { type: 'number' },
      },
      required: ['drawingId', 'ids', 'dx', 'dy'],
      additionalProperties: false,
    },
  },
  {
    name: 'craftcad_transform_entities',
    description: 'Rotate, scale or mirror entities. op "rotate": angle in degrees around center (default 0,0). op "scale": uniform factor around center. op "mirror": across the line through p1 and p2.',
    inputSchema: {
      type: 'object',
      properties: {
        drawingId: { type: 'string' },
        ids: { type: 'array', items: { type: 'number' }, minItems: 1 },
        op: { type: 'string', enum: ['rotate', 'scale', 'mirror'] },
        angle: { type: 'number', description: 'rotate only, degrees (positive = counter-clockwise).' },
        factor: { type: 'number', description: 'scale only, positive number.' },
        center: { type: 'object', properties: { x: { type: 'number' }, y: { type: 'number' } }, description: 'rotate/scale pivot, default 0,0.' },
        p1: { type: 'object', properties: { x: { type: 'number' }, y: { type: 'number' } }, description: 'mirror axis first point.' },
        p2: { type: 'object', properties: { x: { type: 'number' }, y: { type: 'number' } }, description: 'mirror axis second point.' },
      },
      required: ['drawingId', 'ids', 'op'],
      additionalProperties: false,
    },
  },
  {
    name: 'craftcad_delete_entities',
    description: 'Delete entities by id.',
    inputSchema: {
      type: 'object',
      properties: {
        drawingId: { type: 'string' },
        ids: { type: 'array', items: { type: 'number' }, minItems: 1 },
      },
      required: ['drawingId', 'ids'],
      additionalProperties: false,
    },
  },
  {
    name: 'craftcad_query',
    description: 'Return drawing summary (counts by type, layers, extents) and entity data. Use layer to filter, limit to cap the entity list (default 100, max 1000).',
    inputSchema: {
      type: 'object',
      properties: {
        drawingId: { type: 'string' },
        layer: { type: 'string' },
        limit: { type: 'number' },
      },
      required: ['drawingId'],
      additionalProperties: false,
    },
  },
  {
    name: 'craftcad_create_layer',
    description: 'Create or update a layer. color is an AutoCAD color index (1 red, 2 yellow, 3 green, 4 cyan, 5 blue, 6 magenta, 7 white/black).',
    inputSchema: {
      type: 'object',
      properties: {
        drawingId: { type: 'string' },
        name: { type: 'string' },
        color: { type: 'number' },
        ltype: { type: 'string' },
      },
      required: ['drawingId', 'name'],
      additionalProperties: false,
    },
  },
  {
    name: 'craftcad_save_dxf',
    description: 'Write the drawing to an ASCII DXF file (AutoCAD R2000). Open it in the CraftCAD web UI (Ctrl+O or drag & drop) or any CAD program.',
    inputSchema: {
      type: 'object',
      properties: {
        drawingId: { type: 'string' },
        path: { type: 'string', description: 'Absolute path or relative to cwd; parent directories are created.' },
      },
      required: ['drawingId', 'path'],
      additionalProperties: false,
    },
  },
  {
    name: 'craftcad_close_drawing',
    description: 'Drop an in-memory drawing (save it first if you need it later).',
    inputSchema: {
      type: 'object',
      properties: { drawingId: { type: 'string' } },
      required: ['drawingId'],
      additionalProperties: false,
    },
  },
];

function summarize(d) {
  const counts = {};
  for (const e of d.entities.values()) counts[e.type] = (counts[e.type] ?? 0) + 1;
  return {
    drawingId: d.__id,
    name: d.fileName,
    entities: d.entities.size,
    counts,
    layers: [...d.layers.values()].map((l) => ({ name: l.name, color: l.color, on: l.on, frozen: l.frozen, locked: l.locked })),
    extents: boxOut(d.extents()),
  };
}

const HANDLERS = {
  craftcad_new_drawing({ name }) {
    const doc = new Drawing();
    doc.fileName = name ? String(name) : `Drawing${nextDrawing}`;
    const id = `d${nextDrawing++}`;
    doc.__id = id;
    drawings.set(id, doc);
    return { ...summarize(doc), hint: 'Add geometry with craftcad_add_entities, then craftcad_save_dxf.' };
  },

  craftcad_load_dxf({ path }) {
    const file = resolve(String(path));
    const bytes = readFileSync(file);
    const data = readDxf(bytes);
    const doc = new Drawing();
    loadDxfData(doc, data, basename(file));
    const id = `d${nextDrawing++}`;
    doc.__id = id;
    drawings.set(id, doc);
    return { ...summarize(doc), path: file };
  },

  craftcad_add_entities({ drawingId, entities }) {
    const doc = getDrawing(drawingId);
    if (!Array.isArray(entities) || entities.length === 0) throw new Error('entities must be a non-empty array.');
    const added = [];
    for (let i = 0; i < entities.length; i++) {
      let ne;
      try { ne = normEntity(entities[i]); } catch (err) { throw new Error(`entities[${i}]: ${err.message}`); }
      const e = doc.add(ne);
      added.push({ id: e.id, type: e.type, layer: e.layer });
    }
    return { added, total: doc.entities.size };
  },

  craftcad_move_entities({ drawingId, ids, dx, dy }) {
    const doc = getDrawing(drawingId);
    const m = mxTranslate(num(dx, 'dx'), num(dy, 'dy'));
    const moved = [];
    for (const id of ids) {
      const e = doc.entities.get(id);
      if (!e) throw new Error(`Entity ${id} not found in ${drawingId}.`);
      doc.update(entTransform(e, m));
      moved.push(id);
    }
    return { moved, total: doc.entities.size };
  },

  craftcad_transform_entities({ drawingId, ids, op, angle, factor, center, p1, p2 }) {
    const doc = getDrawing(drawingId);
    let m;
    if (op === 'rotate') {
      const c = center === undefined ? { x: 0, y: 0 } : vec(center, 'center');
      m = mxRotate(D2R(num(angle, 'angle')), c);
    } else if (op === 'scale') {
      const c = center === undefined ? { x: 0, y: 0 } : vec(center, 'center');
      const f = num(factor, 'factor', 1e-9);
      m = mxScale(f, f, c);
    } else if (op === 'mirror') {
      m = mxMirror(vec(p1, 'p1'), vec(p2, 'p2'));
    } else {
      throw new Error('op must be rotate, scale or mirror.');
    }
    const changed = [];
    for (const id of ids) {
      const e = doc.entities.get(id);
      if (!e) throw new Error(`Entity ${id} not found in ${drawingId}.`);
      doc.update(entTransform(e, m));
      changed.push(id);
    }
    return { op, changed, total: doc.entities.size };
  },

  craftcad_delete_entities({ drawingId, ids }) {
    const doc = getDrawing(drawingId);
    const deleted = [];
    for (const id of ids) {
      if (!doc.entities.has(id)) throw new Error(`Entity ${id} not found in ${drawingId}.`);
      doc.remove(id);
      deleted.push(id);
    }
    return { deleted, total: doc.entities.size };
  },

  craftcad_query({ drawingId, layer, limit }) {
    const doc = getDrawing(drawingId);
    const cap = Math.min(Math.max(Number(limit) || 100, 1), 1000);
    const all = [...doc.entities.values()].filter((e) => !layer || e.layer === layer);
    return {
      ...summarize(doc),
      filter: layer ?? null,
      returned: Math.min(all.length, cap),
      truncated: all.length > cap,
      entities: all.slice(0, cap),
    };
  },

  craftcad_create_layer({ drawingId, name, color, ltype }) {
    const doc = getDrawing(drawingId);
    const n = String(name || '').trim();
    if (!n) throw new Error('Layer name is required.');
    const c = optNum(color, 'color', 7, 1);
    const lt = ltype ? String(ltype) : 'Continuous';
    const layer = doc.addLayerQuiet(n, c, lt);
    return { layer };
  },

  craftcad_save_dxf({ drawingId, path }) {
    const doc = getDrawing(drawingId);
    const file = resolve(String(path));
    mkdirSync(dirname(file), { recursive: true });
    const dxf = writeDxf(doc);
    writeFileSync(file, dxf, 'utf8');
    return { path: file, bytes: Buffer.byteLength(dxf), entities: doc.entities.size };
  },

  craftcad_close_drawing({ drawingId }) {
    getDrawing(drawingId);
    drawings.delete(drawingId);
    return { closed: drawingId, remaining: drawings.size };
  },
};

import { existsSync } from 'node:fs';

// ---------------------------------------------------------------------------
// UI bridge tools (craftcad_ui_*) — drive the running CraftCAD web app
// Distinguish from the headless tools above by the "craftcad_ui_" name prefix.

import { createRequire } from 'node:module';
const requireUi = createRequire(import.meta.url);
const PW_CANDIDATES = [
  process.env.CRAFTCAD_PLAYWRIGHT,
  '/Users/apple/workdsh/.test-runtime/preview/profiles/preview/node_modules/playwright-core',
  '/Users/apple/workdsh/node_modules/playwright-core',
];
let playwrightMod = null;
for (const p of PW_CANDIDATES) {
  if (!p) continue;
  try { playwrightMod = requireUi(p); break; } catch {}
}
if (!playwrightMod) {
  try { playwrightMod = requireUi('playwright-core'); } catch {}
}
const UI_URL = process.env.CRAFTCAD_URL || 'http://127.0.0.1:8080/';
const UI_HEADLESS = process.env.CRAFTCAD_HEADLESS !== '0';
let uiCtx = null;

const uiAbs = (p) => resolve(process.cwd(), String(p));

async function uiEnsurePage() {
  if (!playwrightMod) throw new Error('playwright-core not found; set CRAFTCAD_PLAYWRIGHT to its install path.');
  if (uiCtx && !uiCtx.page.isClosed()) return uiCtx;
  let browser;
  try { browser = await playwrightMod.chromium.launch({ channel: 'chrome', headless: UI_HEADLESS }); }
  catch { browser = await playwrightMod.chromium.launch({ headless: UI_HEADLESS }); }
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  page.on('pageerror', () => {});
  await page.exposeBinding('__craftcadWrite', async (_src, payload) => {
    const { path, b64, data } = payload;
    const buf = b64 ? Buffer.from(b64, 'base64')
      : typeof data === 'string' ? Buffer.from(data, 'utf8') : Buffer.from(data || []);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, buf);
    return { path, bytes: buf.length };
  });
  await page.goto(UI_URL, { waitUntil: 'load', timeout: 30000 });
  await page.waitForSelector('.ribbon', { timeout: 30000 });
  await page.waitForTimeout(400);
  uiCtx = { browser, page };
  return uiCtx;
}

async function uiStatus() {
  const { page } = await uiEnsurePage();
  return page.evaluate(() => {
    const d = window.craftcad.doc;
    return {
      file: d.fileName || null,
      entities: d.entities.size,
      layers: d.layers.size,
      blocks: d.blocks ? d.blocks.size : null,
      modified: !!d.modified,
      layout: d.layout ? (d.layout.name || 'Model') : 'Model',
    };
  });
}

async function uiOpen(path) {
  const { page } = await uiEnsurePage();
  const file = uiAbs(path);
  if (!existsSync(file)) throw new Error('file not found: ' + file);
  const b64 = readFileSync(file).toString('base64');
  const name = basename(file);
  await page.evaluate(({ b64, name, target }) => {
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const f = new File([bin], name);
    window.__ccWriteTarget = target;
    window.showOpenFilePicker = async () => [{
      kind: 'file',
      name,
      getFile: async () => f,
      createWritable: async () => {
        const chunks = [];
        return {
          write: async (data) => { chunks.push(data); },
          close: async () => {
            const blob = new Blob(chunks);
            const buf = await blob.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let s = '';
            for (let i = 0; i < bytes.length; i += 0x8000) {
              s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
            }
            await window.__craftcadWrite({ path: window.__ccWriteTarget || target, b64: btoa(s) });
          },
        };
      },
    }];
  }, { b64, name, target: file });
  await page.keyboard.press('Control+o');
  await page.waitForTimeout(1200);
  for (let i = 0; i < 20; i++) {
    const st = await page.evaluate(() => ({ n: window.craftcad.doc.entities.size, f: window.craftcad.doc.fileName }));
    if (st.f === name && st.n > 0) return { ...(await uiStatus()), path: file };
    await page.waitForTimeout(250);
  }
  return { ...(await uiStatus()), path: file, warning: 'opened but entity count is 0 or filename mismatch' };
}

async function uiRunCommand(command, inputs = [], waitMs = 600) {
  const { page } = await uiEnsurePage();
  await page.evaluate(() => {
    if (window.__ccLog) return;
    window.__ccLog = [];
    const ed = window.craftcad;
    const orig = ed.print.bind(ed);
    ed.print = (msg, kind) => { try { window.__ccLog.push(String(msg)); } catch {} return orig(msg, kind); };
  });
  const r = await page.evaluate((cmd) => {
    try { window.craftcad.runCommand(cmd); return 'ok'; }
    catch (e) { return 'error: ' + (e && e.message); }
  }, command);
  await page.waitForTimeout(120);
  for (const s of inputs || []) {
    await page.keyboard.type(String(s), { delay: 8 });
    await page.keyboard.press('Enter');
    await page.waitForTimeout(120);
  }
  await page.waitForTimeout(waitMs);
  const log = await page.evaluate(() => (window.__ccLog || []).slice(-40));
  return { command, result: r, log, status: await uiStatus() };
}

async function uiQuery(layer, sample = 0) {
  const { page } = await uiEnsurePage();
  return page.evaluate(({ layer, sample }) => {
    const d = window.craftcad.doc;
    const byType = {};
    const sampleOut = [];
    for (const e of d.entities.values()) {
      if (layer && e.layer !== layer) continue;
      const t = e.type || e.constructor.name;
      byType[t] = (byType[t] || 0) + 1;
      if (sampleOut.length < sample) sampleOut.push({ type: t, layer: e.layer, id: e.id ?? null });
    }
    return {
      file: d.fileName || null,
      total: [...d.entities.values()].filter((e) => !layer || e.layer === layer).length,
      byType,
      layers: [...d.layers.values()].map((l) => ({ name: l.name, color: l.color, on: l.on !== false })),
      sample: sampleOut,
    };
  }, { layer, sample });
}

async function uiZoom(mode) {
  const { page } = await uiEnsurePage();
  const m = String(mode || 'extents');
  await page.keyboard.press('Escape');
  await page.keyboard.type('ZOOM', { delay: 15 });
  await page.keyboard.press('Enter');
  await page.waitForTimeout(200);
  const arg = m === 'extents' ? 'E' : m === 'in' ? '2X' : m === 'out' ? '0.5X' : String(m);
  await page.keyboard.type(arg, { delay: 15 });
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  return { mode: m, status: await uiStatus() };
}

async function uiScreenshot(path, canvasOnly = false) {
  const { page } = await uiEnsurePage();
  const out = uiAbs(path);
  mkdirSync(dirname(out), { recursive: true });
  if (canvasOnly) {
    const el = await page.$('.overlay-canvas');
    const box = el ? await el.boundingBox() : null;
    if (box) { await page.screenshot({ path: out, clip: box }); return { path: out, clip: box }; }
  }
  await page.screenshot({ path: out });
  return { path: out };
}

async function uiSaveDxf(path) {
  const { page } = await uiEnsurePage();
  const out = uiAbs(path);
  mkdirSync(dirname(out), { recursive: true });
  await page.evaluate((target) => {
    window.__ccWriteTarget = target;
    window.showSaveFilePicker = async () => [{
      kind: 'file',
      name: target.split('/').pop(),
      createWritable: async () => {
        const chunks = [];
        return {
          write: async (data) => { chunks.push(data); },
          close: async () => {
            const blob = new Blob(chunks);
            const buf = await blob.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let s = '';
            for (let i = 0; i < bytes.length; i += 0x8000) {
              s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
            }
            window.__craftcadWrite({ path: target, b64: btoa(s) });
          },
        };
      },
    }];
  }, out);
  await page.keyboard.press('Control+s');
  for (let i = 0; i < 40; i++) {
    if (existsSync(out) && readFileSync(out).length > 1000) {
      const st = await page.evaluate(() => ({ n: window.craftcad.doc.entities.size, f: window.craftcad.doc.fileName }));
      return { path: out, bytes: readFileSync(out).length, entities: st.n, file: st.f };
    }
    await page.waitForTimeout(250);
  }
  throw new Error('save did not complete: no DXF written to ' + out);
}

const UI_TOOLS = [
  {
    name: 'craftcad_ui_open',
    description: 'Open a DXF/DWG from disk in the running CraftCAD web app (the browser UI at CRAFTCAD_URL). Returns entity/layer counts.',
    inputSchema: { type: 'object', properties: { path: { type: 'string', description: 'DXF/DWG path (absolute or relative to the server cwd).' } }, required: ['path'], additionalProperties: false },
  },
  {
    name: 'craftcad_ui_command',
    description: 'Run one AutoCAD-style command line in the CraftCAD UI (e.g. "LINE", "CIRCLE", "ZOOM", "ERASE"), optionally feeding follow-up inputs one prompt at a time.',
    inputSchema: {
      type: 'object',
      properties: {
        command: { type: 'string' },
        input: { type: 'array', items: { type: 'string' } },
        waitMs: { type: 'number' },
      },
      required: ['command'],
      additionalProperties: false,
    },
  },
  {
    name: 'craftcad_ui_query',
    description: 'Query the drawing currently open in the CraftCAD UI: entity counts by type, layers, optional samples.',
    inputSchema: {
      type: 'object',
      properties: { layer: { type: 'string' }, sample: { type: 'number' } },
      additionalProperties: false,
    },
  },
  {
    name: 'craftcad_ui_status',
    description: 'Report the state of the CraftCAD UI: current file, entity/layer/block counts, modified flag.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'craftcad_ui_zoom',
    description: 'Zoom the CraftCAD UI view: "extents", "in", "out" or a scale factor.',
    inputSchema: { type: 'object', properties: { mode: { type: 'string' } }, required: ['mode'], additionalProperties: false },
  },
  {
    name: 'craftcad_ui_screenshot',
    description: 'Save a PNG screenshot of the CraftCAD UI window (or just the drawing canvas).',
    inputSchema: { type: 'object', properties: { path: { type: 'string' }, canvasOnly: { type: 'boolean' } }, required: ['path'], additionalProperties: false },
  },
  {
    name: 'craftcad_ui_save_dxf',
    description: 'Save the drawing currently open in the CraftCAD UI to a DXF file on disk (through the app’s own save flow).',
    inputSchema: { type: 'object', properties: { path: { type: 'string' } }, required: ['path'], additionalProperties: false },
  },
  {
    name: 'craftcad_ui_eval',
    description: 'Evaluate JavaScript in the CraftCAD UI page (access to window.craftcad). Advanced escape hatch.',
    inputSchema: { type: 'object', properties: { script: { type: 'string' } }, required: ['script'], additionalProperties: false },
  },
];

const UI_HANDLERS = {
  craftcad_ui_open: ({ path }) => uiOpen(path),
  craftcad_ui_command: ({ command, input, waitMs }) => uiRunCommand(command, input, waitMs),
  craftcad_ui_query: ({ layer, sample }) => uiQuery(layer, sample || 0),
  craftcad_ui_status: () => uiStatus(),
  craftcad_ui_zoom: ({ mode }) => uiZoom(mode),
  craftcad_ui_screenshot: ({ path, canvasOnly }) => uiScreenshot(path, !!canvasOnly),
  craftcad_ui_save_dxf: ({ path }) => uiSaveDxf(path),
  craftcad_ui_eval: async ({ script }) => {
    const { page } = await uiEnsurePage();
    return page.evaluate(async (s) => {
      const fn = new Function('return (async () => { ' + s + ' })()');
      return await fn();
    }, script);
  },
};

process.on('SIGTERM', async () => { try { await uiCtx?.browser?.close(); } catch {} process.exit(0); });


// ---------------------------------------------------------------------------
// JSON-RPC over stdio (MCP stdio transport: one JSON message per line)

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

async function handleRequest(method, params) {
  switch (method) {
    case 'initialize':
      return {
        protocolVersion: params.protocolVersion || '2025-06-18',
        capabilities: { tools: { listChanged: false } },
        serverInfo: SERVER,
        instructions: 'CraftCAD tools. Headless (craftcad_*): build/modify drawings in memory and save DXF. UI bridge (craftcad_ui_*): drive the real CraftCAD web app at http://127.0.0.1:8080 — open a DXF, run AutoCAD-style commands, query, screenshot, save. Angles are in degrees. DWG export needs ODA File Converter.',
      };
    case 'ping':
      return {};
    case 'tools/list':
      return { tools: TOOLS.concat(UI_TOOLS) };
    case 'tools/call': {
      const name = params?.name;
      const fn = HANDLERS[name] ?? UI_HANDLERS[name];
      if (!fn) return { content: [{ type: 'text', text: `Unknown tool "${name}". Use tools/list.` }], isError: true };
      try {
        const out = await fn(params.arguments ?? {});
        return { content: [{ type: 'text', text: JSON.stringify(out, null, 2) }] };
      } catch (err) {
        return { content: [{ type: 'text', text: `Error: ${err?.message ?? err}` }], isError: true };
      }
    }
    case 'resources/list':
      return { resources: [] };
    case 'prompts/list':
      return { prompts: [] };
    default: {
      const err = new Error(`Method not found: ${method}`);
      err.code = -32601;
      throw err;
    }
  }
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
let queue = Promise.resolve();
rl.on('line', (line) => {
  const text = line.trim();
  if (!text) return;
  let msg;
  try {
    msg = JSON.parse(text);
  } catch {
    send({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } });
    return;
  }
  if (msg.id === undefined) return; // notification (initialized, canceled, ...)
  // Serialize tool calls so concurrent requests cannot interleave drawing mutations.
  queue = queue.then(async () => {
    try {
      const result = await handleRequest(msg.method, msg.params ?? {});
      send({ jsonrpc: '2.0', id: msg.id, result });
    } catch (err) {
      send({ jsonrpc: '2.0', id: msg.id, error: { code: err?.code ?? -32603, message: String(err?.message ?? err) } });
    }
  });
});
rl.on('close', () => process.exit(0));

console.error(`craftcad-mcp ${SERVER.version} ready (CraftCAD source: ${ROOT})`);
