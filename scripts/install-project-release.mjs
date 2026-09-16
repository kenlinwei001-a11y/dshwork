#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const argv = process.argv.slice(2);
const value = (name, fallback) => {
  const index = argv.indexOf(name);
  return index === -1 ? fallback : argv[index + 1];
};
const has = name => argv.includes(name);
const profile = value('--profile', 'workdsh');
const directory = resolve(value('--directory', dirname(fileURLToPath(import.meta.url))));
const dsh = value('--dsh', 'dsh');
const dryRun = has('--dry-run');
const manifestPath = join(directory, 'release-manifest.json');

if (!existsSync(manifestPath)) {
  throw new Error(`Missing ${manifestPath}. Put this installer beside release-manifest.json and all release .tgz files.`);
}

const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
const expectedHarness = manifest.harness;
if (typeof expectedHarness !== 'string' || expectedHarness.length === 0) {
  throw new Error('Release manifest does not declare the required Harness version.');
}
const packages = new Map(manifest.packages.map(item => [item.name, item]));
const installOrder = [
  'workdsh-provider-identity-local',
  'workdsh-plugin-audit',
  'workdsh-plugin-access',
  'workdsh-plugin-skills',
  // The experts layer installs and activates the three official DSH Agent Team modules.
  'workdsh-plugin-experts',
  'workdsh-plugin-connectors',
  'workdsh-plugin-activity',
  'workdsh-plugin-office',
  'workdsh-bundle',
];

for (const name of installOrder) {
  const item = packages.get(name);
  if (!item) throw new Error(`Release manifest is missing required package ${name}.`);
  const path = join(directory, item.filename);
  if (!existsSync(path)) throw new Error(`Missing release asset ${path}.`);
  const actual = createHash('sha256').update(readFileSync(path)).digest('hex');
  if (actual !== item.sha256) throw new Error(`SHA-256 mismatch for ${item.filename}.`);
}

function execute(args, options = {}) {
  console.log(`> ${dsh} ${args.join(' ')}`);
  if (dryRun && !options.always) return undefined;
  const result = spawnSync(dsh, args, options.capture
    ? { encoding: 'utf8' }
    : { stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
  return result;
}

// pnpm blocks dependency lifecycle scripts until the profile makes an explicit
// decision. protobufjs only runs a version-range warning in postinstall; the
// runtime library remains installed when this script is disabled.
const dshHome = resolve(process.env.DSH_HOME || join(homedir(), '.dsh'));
const versionResult = execute(['--version'], { always: true, capture: true });
const actualHarness = versionResult?.stdout?.trim();
if (actualHarness !== expectedHarness) {
  throw new Error(`WorkDSH ${manifest.version} requires dsh ${expectedHarness}; found ${actualHarness || 'unknown'}. Pass --dsh /absolute/path/to/a-compatible-dsh.`);
}

const profileManifest = join(dshHome, 'profiles', profile, 'package.json');
if (existsSync(profileManifest)) {
  console.log(`Existing profile ${profile} detected; preserving its configuration and stored data.`);
  execute(['--profile', profile, '--dump-config']);
} else {
  execute(['--profile', profile, '--from-default-profile', 'web', '--dump-config']);
}

const workspaceFile = join(dshHome, 'profiles', profile, 'pnpm-workspace.yaml');
if (!dryRun && existsSync(workspaceFile)) {
  const current = readFileSync(workspaceFile, 'utf8');
  if (!/^allowBuilds:/m.test(current)) {
    writeFileSync(workspaceFile, `${current.trimEnd()}\n\nallowBuilds:\n  protobufjs: false\n`);
  } else if (!/^\s{2}protobufjs:/m.test(current)) {
    writeFileSync(workspaceFile, current.replace(/^allowBuilds:\s*$/m, 'allowBuilds:\n  protobufjs: false'));
  }
}

for (const name of installOrder) {
  const item = packages.get(name);
  execute(['plugin', '--profile', profile, 'add', join(directory, item.filename)]);
}

console.log(`\nWorkDSH ${manifest.version} is installed in profile ${profile}.`);
console.log(`Start it with: ${dsh} --profile ${profile}`);
console.log('The conversation header should show “Agent Team”; its panel is supplied by the official DSH Team client.');
