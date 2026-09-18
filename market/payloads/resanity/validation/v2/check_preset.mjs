#!/usr/bin/env node
/**
 * Preset regression gate for the 「散修研究」user preset.
 *
 * Runs after every preset-composition or package edit to catch the exact
 * failure modes the Resanity formal-audit identity binding worries about:
 *
 *   1. the preset composition stays a consumers-only agent-plane file
 *      (plane rule: no unknown rows, no service publishing, realms only
 *      where the shipped presets use them);
 *   2. the resanity-data row activates data tools without duplicating the
 *      host row's timer/commands;
 *   3. the delegation group keeps the workflowEngine isolate realm and
 *      carries no codex/claude rows;
 *   4. the mounted skills/resanity copy stays byte-identical to the repo-owned
 *      preset source (验证 A、实际加载 B 的漂移直接失败；npm run preset:sync 修复);
 *   5. the mounted preset is a REAL directory (the roster does not follow
 *      symlinked preset dirs) and the repo skills/resanity stays the
 *      canonical-root symlink (仓库内单一事实源);
 *   6. the profile patch keeps webFetch: true on the host resanity row.
 *
 * This checker verifies composition identity only. It does not prove
 * research validity, and it never launches sessions.
 *
 * Usage:
 *   node validation/v2/check_preset.mjs [--dsh-home ~/.dsh] [--profile web]
 */

import { lstat, readFile, realpath } from "node:fs/promises";
import { createHash } from "node:crypto";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import yaml from "js-yaml";

const JS_TYPE = new yaml.Type("tag:yaml.org,2002:js", { kind: "scalar" });
const SCHEMA = yaml.DEFAULT_SCHEMA.extend([JS_TYPE]);

const argv = process.argv.slice(2);
const flag = (name, fallback) => {
	const index = argv.indexOf(name);
	return index >= 0 && argv[index + 1] !== undefined ? argv[index + 1] : fallback;
};
const DSH_HOME = flag("--dsh-home", process.env.DSH_HOME || join(homedir(), ".dsh"));
const PROFILE = flag("--profile", "web");

const PROJECT_ROOT = fileURLToPath(new URL("../..", import.meta.url)).replace(/\/+$/, "");
const REPO_PRESET = join(PROJECT_ROOT, "preset");
const PRESET_DIR = join(DSH_HOME, ".agent-presets", "resanity");
const PRESET_SKILL = join(PRESET_DIR, "skills", "resanity");
const REPO_SKILL = join(REPO_PRESET, "skills", "resanity");

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

/** Consumer-only row names copied from the shipped presets; anything else fails. */
const ALLOWED_PACKAGES = new Set([
	"@deepseek-ai/dsh-persona",
	"@deepseek-ai/dsh-tool-bash",
	"@deepseek-ai/dsh-tool-fs",
	"@deepseek-ai/dsh-tool-fs-search",
	"@deepseek-ai/dsh-tool-jobs",
	"@deepseek-ai/dsh-skill-filesystem",
	"@deepseek-ai/dsh-tool-skill",
	"resanity",
	"@deepseek-ai/dsh-tool-goal",
	"@deepseek-ai/dsh-tool-web",
	"@deepseek-ai/dsh-tool-subagent-control",
	"@deepseek-ai/dsh-tool-subagent-control/list-agents",
	"@deepseek-ai/dsh-tool-subagent",
	"@deepseek-ai/dsh-workflow-worker-thread",
	"@deepseek-ai/dsh-tool-workflow",
	"@deepseek-ai/dsh-compaction-basic",
	"@deepseek-ai/dsh-command-compact",
	"@deepseek-ai/dsh-compaction-tool-result-pruner",
	"@deepseek-ai/dsh-tool-ask-user",
	"@deepseek-ai/dsh-tool-todo",
	"cordis:group",
]);

const REQUIRED_ROW_IDS = [
	"persona", "tool-bash", "tool-fs", "tool-fs-search", "tool-jobs",
	"skill-filesystem", "tool-skill", "resanity-data", "tool-goal",
	"tool-web", "delegation", "compaction", "tool-ask-user", "tool-todo",
];

const DELEGATION_ROWS = [
	["tool-subagent-control", "@deepseek-ai/dsh-tool-subagent-control"],
	["tool-subagent-list-agents", "@deepseek-ai/dsh-tool-subagent-control/list-agents"],
	["tool-subagent", "@deepseek-ai/dsh-tool-subagent"],
	["tool-subagent-fork", "@deepseek-ai/dsh-tool-subagent"],
	["workflow-worker-thread", "@deepseek-ai/dsh-workflow-worker-thread"],
	["tool-workflow", "@deepseek-ai/dsh-tool-workflow"],
];

const failures = [];
const ok = [];
const check = (condition, message) => (condition ? ok.push(message) : failures.push(message));
const sha256 = (data) => createHash("sha256").update(data).digest("hex");

function flatten(rows, path = "$") {
	const out = [];
	for (const row of rows) {
		const here = `${path}.${row?.id ?? "?"}`;
		out.push({ row, path: here });
		if (row && row.group === true && Array.isArray(row.config)) out.push(...flatten(row.config, here));
	}
	return out;
}

// ── 1. 组合结构 ──────────────────────────────────────────────────────────────
let composition;
let mountedText;
try {
	mountedText = await readFile(join(PRESET_DIR, "agent.cordis.yml"), "utf8");
	composition = yaml.load(mountedText, { schema: SCHEMA });
} catch (error) {
	console.error(`✗ agent.cordis.yml 无法解析：${error.message}`);
	process.exit(1);
}
{
	// 挂载的组合必须与仓库预设源一致（编辑一律发生在仓库 preset/）
	const repoText = await readFile(join(REPO_PRESET, "agent.cordis.yml"), "utf8").catch(() => null);
	check(repoText !== null && sha256(repoText) === sha256(mountedText), "agent.cordis.yml 与仓库 preset/ 一致（否则运行 npm run preset:sync）");
}
check(Array.isArray(composition), "agent.cordis.yml 顶层是数组");
if (!Array.isArray(composition)) process.exit(1);

const top = composition;
const all = flatten(top);
const ids = top.map((row) => row?.id).filter(Boolean);
check(new Set(ids).size === ids.length, "顶层行 id 唯一");
for (const id of REQUIRED_ROW_IDS) check(ids.includes(id), `必需行存在：${id}`);

const findTop = (id) => top.find((row) => row?.id === id);
const findRows = (name) => all.filter(({ row }) => row?.name === name);

for (const { row, path } of all) {
	if (row?.name === undefined) {
		check(false, `${path}：缺少 name`);
		continue;
	}
	if (!ALLOWED_PACKAGES.has(row.name)) {
		check(false, `${path}：不允许的行包 ${row.name}（发布服务或未审查的行）`);
		continue;
	}
	if (row.group === true) {
		check(row.isolate !== undefined, `${path}：group 必须有 isolate realm`);
	} else {
		check(row.isolate === undefined, `${path}：非 group 行不得携带 isolate`);
	}
}

// resanity-data 行：只开数据工具与纪律段落，不重复宿主定时器/命令，也不越界开 webFetch
const dataRow = findTop("resanity-data");
check(dataRow?.name === "resanity", "resanity-data 行指向 resanity 包");
check(dataRow?.config?.dataTools === true, "resanity-data 开启 dataTools");
check(dataRow?.config?.researchPrompt === true, "resanity-data 开启 researchPrompt（三段研究纪律）");
check(dataRow?.config?.anchorTimer === false, "resanity-data 关闭 anchorTimer（宿主行保留）");
check(dataRow?.config?.commands === false, "resanity-data 关闭 commands（宿主行保留）");
check(dataRow?.config?.webFetch !== true, "resanity-data 不开 webFetch（属于宿主平面）");

// 网络检索：fetch 开启，由宿主 resanity 行的 webFetch 提供方支撑
check(findTop("tool-web")?.config?.fetch === true, "tool-web 开启 fetch");

// delegation 组：workflowEngine isolate + 六个固定行 + 无 codex/claude
const delegation = findTop("delegation");
check(delegation?.group === true, "delegation 是 group");
check(delegation?.isolate?.workflowEngine === true, "delegation isolate workflowEngine");
if (delegation?.config) {
	const childIds = delegation.config.map((row) => row?.id).filter(Boolean);
	check(new Set(childIds).size === childIds.length, "delegation 子行 id 唯一");
	for (const [id, pkg] of DELEGATION_ROWS) {
		const child = delegation.config.find((row) => row?.id === id);
		check(child?.name === pkg, `delegation 子行 ${id} → ${pkg}`);
	}
	check(!childIds.some((id) => id.includes("codex") || id.includes("claude")), "delegation 不引入 codex/claude-code 行");
	const spawn = delegation.config.find((row) => row?.id === "tool-subagent");
	check(spawn?.config?.provider === "spawn", "subagent 使用 spawn 后端");
	const fork = delegation.config.find((row) => row?.id === "tool-subagent-fork");
	check(fork?.config?.provider === "fork", "subagent_fork 使用 fork 后端");
	const worker = delegation.config.find((row) => row?.id === "workflow-worker-thread");
	check(worker?.config?.provider === "spawn", "workflow worker 使用 spawn 后端");
}

// skill-filesystem：customSkillDirs 指向预设自己的 skills/ 目录
const skillFs = findTop("skill-filesystem");
const dirs = Array.isArray(skillFs?.config?.customSkillDirs) ? skillFs.config.customSkillDirs : [];
check(dirs.length > 0 && dirs.some((dir) => typeof dir === "string" && dir.includes("skills")), "skill-filesystem 指向预设内 skills/ 目录");

// ── 2. 挂载的预设目录必须是真实目录（花名册不跟随软链预设目录）─────────────
{
	const mountedStat = await lstat(PRESET_DIR).catch(() => null);
	check(mountedStat?.isDirectory() === true && mountedStat?.isSymbolicLink() === false, "挂载的预设目录是真实目录（花名册不跟随软链预设目录）");
}

// ── 3. 仓库内 skills/resanity 是指向 canonical 根的软链（单一事实源）────────
{
	const linkStat = await lstat(REPO_SKILL).catch(() => null);
	check(linkStat?.isSymbolicLink() === true, "仓库 preset/skills/resanity 是指向 canonical 根的软链");
	const resolved = await realpath(REPO_SKILL).catch(() => null);
	check(resolved === PROJECT_ROOT, `仓库 preset/skills/resanity 解析到仓库根（实际：${resolved}）`);
}

// ── 4. 挂载的 skill 副本与仓库预设源逐字节一致 ─────────────────────────────
for (const relative of SKILL_FILES) {
	const canonical = await readFile(join(REPO_SKILL, relative)).catch(() => null);
	const copy = await readFile(join(PRESET_SKILL, relative)).catch(() => null);
	if (canonical === null) {
		failures.push(`仓库预设源 skills/resanity/${relative} 缺失`);
		continue;
	}
	if (copy === null) {
		failures.push(`挂载副本 skills/resanity/${relative} 缺失（运行 npm run preset:sync）`);
		continue;
	}
	const same = sha256(canonical) === sha256(copy);
	check(same, `skills/resanity/${relative} 与仓库预设源一致`);
}

// ── 3. preset.yml 元数据 ─────────────────────────────────────────────────────
try {
	const meta = yaml.load(await readFile(join(PRESET_DIR, "preset.yml"), "utf8"), { schema: SCHEMA });
	check(typeof meta?.name === "string" && meta.name.length > 0, "preset.yml 有 name");
	check(typeof meta?.description === "string" && meta.description.length > 0, "preset.yml 有 description");
} catch (error) {
	failures.push(`preset.yml 无法解析：${error.message}`);
}

// ── 4. profile 补丁的宿主 resanity 行保持 webFetch ─────────────────────────
try {
	const patchText = await readFile(join(DSH_HOME, "profiles", PROFILE, "cordis.patch.yml"), "utf8");
	const patch = yaml.load(patchText, { schema: SCHEMA });
	const insert = Array.isArray(patch) ? patch.find((entry) => entry?.insert)?.insert ?? [] : [];
	const hostRow = Array.isArray(insert) ? insert.find((row) => row?.id === "resanity") : undefined;
	check(hostRow?.name === "resanity", `profiles/${PROFILE}/cordis.patch.yml 有宿主 resanity 行`);
	check(hostRow?.config?.webFetch === true, "宿主 resanity 行开启 webFetch");
	check(hostRow?.config?.prefetchObservations === true, "宿主 resanity 行开启 prefetchObservations（锚到期预采集）");
} catch (error) {
	failures.push(`profile 补丁无法解析：${error.message}`);
}

// ── 报告 ─────────────────────────────────────────────────────────────────────
for (const line of ok) console.log(`✓ ${line}`);
for (const line of failures) console.error(`✗ ${line}`);
console.log(`\n${ok.length} passed, ${failures.length} failed`);
process.exit(failures.length === 0 ? 0 : 1);
