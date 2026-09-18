#!/usr/bin/env node
/**
 * Sync the repo-owned preset into the DSH user preset root.
 *
 * The agentPresets roster discovers REAL directories only (it does not
 * follow symlinked preset dirs), so the mounted preset must be a materialized
 * copy. The repo `preset/` directory is the single source of truth; this
 * script copies it into `${DSH_HOME}/.agent-presets/resanity/` and keeps
 * file modes at 644. `check_preset.mjs` then verifies byte identity between
 * the two — drift is impossible to miss, and one command fixes it.
 *
 * Usage:
 *   node validation/v2/sync_preset.mjs [--dsh-home ~/.dsh]
 */

import { chmod, copyFile, mkdir, readdir, rm } from "node:fs/promises";
import { homedir } from "node:os";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const argv = process.argv.slice(2);
const flag = (name, fallback) => {
	const index = argv.indexOf(name);
	return index >= 0 && argv[index + 1] !== undefined ? argv[index + 1] : fallback;
};

const DSH_HOME = flag("--dsh-home", process.env.DSH_HOME || join(homedir(), ".dsh"));
const PROJECT_ROOT = fileURLToPath(new URL("../..", import.meta.url));
const SOURCE = join(PROJECT_ROOT, "preset");
const TARGET = join(DSH_HOME, ".agent-presets", "resanity");

const SKILL_FILES = [
	"SKILL.md",
	"references/investing.md",
	"references/anchors.md",
	"references/formal-audit.md",
	"tools/skill_identity.py",
	"tools/research_check.py",
	"tools/anchor_check.py",
	"tools/validation_source_check.py",
	"tools/report_check.py",
	"tools/failure_tracker.py",
	"scripts/ashare_disclosures.py",
	"scripts/free_market_observations.py",
	"scripts/tier1_providers.py",
	"validation/receipt-template.json",
	"validation/host-receipt-template.json",
];

async function copyTree(sourceDir, targetDir, relativePaths) {
	for (const relativePath of relativePaths) {
		const from = join(sourceDir, relativePath);
		const to = join(targetDir, relativePath);
		await mkdir(join(to, ".."), { recursive: true });
		await copyFile(from, to);
		await chmod(to, 0o644).catch(() => {});
	}
}

async function main() {
	await rm(TARGET, { recursive: true, force: true });
	await mkdir(TARGET, { recursive: true });
	await copyTree(SOURCE, TARGET, ["agent.cordis.yml", "preset.yml"]);
	// 仓库内 skills/resanity 是指向 canonical 根目录的软链；copyFile 按真实路径复制内容
	await copyTree(join(SOURCE, "skills", "resanity"), join(TARGET, "skills", "resanity"), SKILL_FILES);
	const top = await readdir(TARGET);
	console.log(`synced ${SOURCE} -> ${TARGET}`);
	console.log(`top-level: ${top.join(", ")}`);
	console.log(`skill files materialized: ${SKILL_FILES.length}`);
}

await main();
