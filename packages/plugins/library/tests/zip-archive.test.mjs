import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Context } from '@deepseek-ai/cordis';
import Storage from '@deepseek-ai/dsh-storage';
import * as JsonStorage from '@deepseek-ai/dsh-storage-json';
import * as StorageDomain from '@deepseek-ai/dsh-storage-domain';
import JSZip from 'jszip';
import { LibraryManager } from '../dist/index.js';

const actor = { principalId: 'owner-a', organizationId: 'organization-a', requestId: 'zip-request', resolvedBy: 'test' };

async function boot(root) {
  const ctx = new Context();
  try {
    await ctx.plugin(Storage);
    await ctx.plugin(JsonStorage, { root: join(root, 'storage') });
    await ctx.plugin(StorageDomain, { backend: 'json' });
    await ctx.plugin(LibraryManager, { root: join(root, 'library') });
    return ctx;
  } catch (error) { await ctx.fiber.dispose(); throw error; }
}

test('zip archives upload, preserve original bytes and index entry names', async () => {
  const root = await mkdtemp(join(tmpdir(), 'workdsh-library-zip-'));
  let ctx;
  try {
    ctx = await boot(root);
    const zip = new JSZip();
    zip.file('唯一词-ZipInner.txt', 'hello');
    zip.file('目录/图片.png', new Uint8Array([1, 2, 3]));
    const bytes = new Uint8Array(await zip.generateAsync({ type: 'uint8array' }));

    const entry = await ctx.workdshLibrary.importAsset(actor, { name: '资料包.zip', bytes, operationId: 'zip-import' });
    assert.equal(entry.asset.kind, 'zip');
    assert.equal(entry.asset.mediaType, 'application/zip');
    assert.equal(entry.revision.conversionStatus, 'ready');
    assert.deepEqual(await ctx.workdshLibrary.readOriginal(actor, entry.asset.id), bytes);

    const text = await ctx.workdshLibrary.readText(actor, entry.asset.id);
    assert.match(text, /唯一词-ZipInner\.txt/);
    assert.match(text, /目录\/图片\.png/);
    assert.equal((await ctx.workdshLibrary.search(actor, '唯一词-ZipInner'))[0].name, '资料包.zip');
    assert.equal((await ctx.workdshLibrary.search(actor, 'hello')).length, 0, 'zip contents are not extracted into search text');

    await assert.rejects(
      ctx.workdshLibrary.importAsset(actor, { name: '坏的.zip', bytes: new TextEncoder().encode('not a zip'), operationId: 'bad-zip' }),
      /library\/invalid-zip/,
    );
  } finally {
    await ctx?.fiber.dispose();
    await rm(root, { recursive: true, force: true });
  }
});
