import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const root = resolve(import.meta.dirname, '../..');
const installer = join(root, 'scripts/install-project-release.mjs');
const harnessVersion = '0.1.6-alpha.2';
const packageNames = [
  'workdsh-provider-identity-local', 'workdsh-plugin-audit', 'workdsh-plugin-access',
  'workdsh-plugin-skills', 'workdsh-plugin-experts', 'workdsh-plugin-connectors',
  'workdsh-plugin-activity', 'workdsh-plugin-office', 'workdsh-bundle',
];

async function fixture(version = harnessVersion) {
  const home = await mkdtemp(join(tmpdir(), 'workdsh-installer-'));
  const release = join(home, 'release');
  await mkdir(release, { recursive: true });
  const packages = [];
  for (const name of packageNames) {
    const filename = `${name}-fixture.tgz`;
    const bytes = Buffer.from(`fixture:${name}`);
    await writeFile(join(release, filename), bytes);
    packages.push({ name, filename, sha256: createHash('sha256').update(bytes).digest('hex') });
  }
  await writeFile(join(release, 'release-manifest.json'), JSON.stringify({ version: 'test', harness: harnessVersion, packages }));
  const fakeDsh = join(home, 'fake-dsh.mjs');
  await writeFile(fakeDsh, `#!/usr/bin/env node
import { appendFileSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
const args = process.argv.slice(2);
appendFileSync(process.env.INSTALL_LOG, JSON.stringify(args) + '\\n');
if (args[0] === '--version') { console.log(${JSON.stringify(version)}); process.exit(0); }
const profile = args[args.indexOf('--profile') + 1];
if (args.includes('--from-default-profile')) {
  const dir = join(process.env.DSH_HOME, 'profiles', profile);
  if (existsSync(join(dir, 'package.json'))) process.exit(9);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'package.json'), '{}');
  writeFileSync(join(dir, 'pnpm-workspace.yaml'), 'packages: []\\n');
}
`);
  await chmod(fakeDsh, 0o755);
  return { home, release, fakeDsh, log: join(home, 'calls.jsonl'), dshHome: join(home, 'dsh-home') };
}

function run(input, profile) {
  return spawnSync(process.execPath, [installer, '--directory', input.release, '--profile', profile, '--dsh', input.fakeDsh], {
    encoding: 'utf8',
    env: { ...process.env, DSH_HOME: input.dshHome, INSTALL_LOG: input.log },
  });
}

const calls = async input => (await readFile(input.log, 'utf8')).trim().split('\n').map(line => JSON.parse(line));

test('project installer initializes a new profile exactly once', async () => {
  const input = await fixture();
  try {
    const result = run(input, 'fresh');
    assert.equal(result.status, 0, result.stderr);
    const recorded = await calls(input);
    assert.deepEqual(recorded[0], ['--version']);
    assert.deepEqual(recorded[1], ['--profile', 'fresh', '--from-default-profile', 'web', '--dump-config']);
    assert.equal(recorded.filter(args => args[0] === 'plugin').length, 9);
  } finally { await rm(input.home, { recursive: true, force: true }); }
});

test('project installer upgrades an existing profile without reinitializing it', async () => {
  const input = await fixture();
  try {
    const profileDir = join(input.dshHome, 'profiles', 'existing');
    await mkdir(profileDir, { recursive: true });
    await writeFile(join(profileDir, 'package.json'), '{"marker":"preserve"}');
    await writeFile(join(profileDir, 'pnpm-workspace.yaml'), 'packages: []\n');
    const result = run(input, 'existing');
    assert.equal(result.status, 0, result.stderr);
    const recorded = await calls(input);
    assert.deepEqual(recorded[1], ['--profile', 'existing', '--dump-config']);
    assert.ok(recorded.every(args => !args.includes('--from-default-profile')));
    assert.match(await readFile(join(profileDir, 'package.json'), 'utf8'), /preserve/);
    assert.equal(recorded.filter(args => args[0] === 'plugin').length, 9);
  } finally { await rm(input.home, { recursive: true, force: true }); }
});

test('project installer rejects an incompatible Harness before changing a profile', async () => {
  const input = await fixture('0.1.5-rc.1');
  try {
    const result = run(input, 'blocked');
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, new RegExp(`requires dsh ${harnessVersion.replaceAll('.', '\\.')}; found 0\\.1\\.5-rc\\.1`));
    assert.deepEqual(await calls(input), [['--version']]);
  } finally { await rm(input.home, { recursive: true, force: true }); }
});
