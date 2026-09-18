import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { mkdtemp, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir, homedir } from "node:os";
import { join } from "node:path";
import { Context } from "@deepseek-ai/cordis";
import {
	anchorStatus,
	anchorRoots,
	apply,
	buildDataToolDefinitions,
	buildDisclosureArgs,
	buildObservationRequest,
	buildProviderArgs,
	clearCredentials,
	collectAnchorLines,
	Config,
	credentialsPath,
	inject,
	name,
	nextTriggerDate,
	parseAnchorDates,
	parseAnchorInstrument,
	parseToolJson,
	readCredentials,
	renderAnchorHits,
	runAnchorCheck,
	runScript,
	scanAnchorDir,
	summarizeDisclosures,
	validateTushareToken,
	writeCredentials,
} from "../lib/index.js";

const MS_PER_DAY = 86_400_000;
const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const md = (d) => `${d.getMonth() + 1}/${d.getDate()}`;

// ── 1. 纯函数：日期解析 ────────────────────────────────────────────────────
{
	const today = new Date(2026, 7, 13); // 2026-08-13
	assert.deepEqual(
		parseAnchorDates("更新触发器：2026-08-25 半年报；9/1 另一次", today).map(iso),
		["2026-08-25", "2026-09-01"],
	);
	// 错过触发日后保持 overdue，不得静默滚到下一年或消失
	assert.deepEqual(parseAnchorDates("8/12 已过期", today).map(iso), ["2026-08-12"]);
	assert.deepEqual(parseAnchorDates("2026-08-12 已过期", today).map(iso), ["2026-08-12"]);
	assert.deepEqual(parseAnchorDates("2026/08/25", today).map(iso), ["2026-08-25"]);
	assert.equal(iso(nextTriggerDate("## 锚 1\n- 更新触发器：2026-08-12 半年报", today)), "2026-08-12");
	// JS Date 会自动归一化 2/31；解析器必须拒绝这种伪日期
	assert.deepEqual(parseAnchorDates("2026-02-31", today), []);
	// 中文日期
	assert.deepEqual(parseAnchorDates("2026年8月25日 中报", today).map(iso), ["2026-08-25"]);
	// 失效锚不参与
	const text = `## 锚 1：有效\n- 更新触发器：2026-08-25\n\n## 锚 2：[失效] 已推翻\n- 更新触发器：2026-08-13\n`;
	assert.equal(iso(nextTriggerDate(text, today)), "2026-08-25");
	assert.equal(anchorStatus("锚 1\n- 状态：active\n"), "active");
	assert.equal(anchorStatus("锚 2\n- 状态：refuted\n"), "refuted");
	assert.equal(anchorStatus("锚 3\n- status: realized\n"), "realized");
	assert.equal(anchorStatus("锚 4 [archived]\n"), "archived");
	const lifecycle = `## active\n- 状态：active\n- 更新触发器：2026-08-25\n\n## realized\n- 状态：realized\n- 更新触发器：2026-08-13\n`;
	assert.equal(iso(nextTriggerDate(lifecycle, today)), "2026-08-25");
}

// ── 2. 纯函数：扫描与渲染 ──────────────────────────────────────────────────
{
	const dir = await mkdtemp(join(tmpdir(), "resanity-scan-"));
	try {
		await mkdir(join(dir, "anchors"));
		const due = new Date(); // 今天 → due
		const overdue = new Date(Date.now() - 2 * MS_PER_DAY); // 前天 → 仍需提醒
		const near = new Date(Date.now() + 2 * MS_PER_DAY); // 后天 → near（窗口 3）
		const far = new Date(Date.now() + 20 * MS_PER_DAY); // 20 天后 → 窗口外
		await writeFile(join(dir, "anchors", "算力链.md"), `## 锚 1\n\n- 更新触发器：${md(due)} 半年报\n`);
		await writeFile(join(dir, "anchors", "逾期锚.md"), `## 锚 1\n\n- 更新触发器：${iso(overdue)} 财报\n`);
		await writeFile(join(dir, "anchors", "光伏.md"), `## 锚 1\n\n- 更新触发器：${iso(near)} 互动易\n`);
		await writeFile(join(dir, "anchors", "远方.md"), `## 锚 1\n\n- 更新触发器：${iso(far)} 远期\n`);
		await writeFile(join(dir, "anchors", "_template.md"), `## 锚 1\n\n- 更新触发器：${md(due)}\n`);
		await writeFile(join(dir, "anchors", "example.md"), `## 锚 1\n\n- 更新触发器：${md(due)}\n`);
		await writeFile(join(dir, "anchors", "index.md"), `# 仪表盘\n\n| 主题 | 活跃锚数 |\n`);
		await writeFile(join(dir, "anchors", "README.md"), `# 说明\n`);

		const hits = await scanAnchorDir(join(dir, "anchors"), { windowDays: 3 });
		assert.equal(hits.length, 3, "应扫到 overdue + due + near，模板/示例/索引跳过");
		assert.equal(hits.filter((h) => h.kind === "due").length, 2);
		assert.equal(hits.filter((h) => h.kind === "near").length, 1);

		const lines = renderAnchorHits(hits);
		assert.ok(lines.some((l) => l.includes("锚触发已到") && l.includes("算力链")));
		assert.ok(lines.some((l) => l.includes("锚触发已到") && l.includes("逾期锚")));
		assert.ok(lines.some((l) => l.includes("锚触发临近") && l.includes("光伏") && l.includes("还有 2 天")));
		assert.ok(!lines.some((l) => l.includes("远方")), "窗口外不提醒");
	} finally {
		await rm(dir, { recursive: true, force: true });
	}
}

// ── 3. 插件装配：provider / 命令 / 定时器 ──────────────────────────────────
{
	const root = new Context();
	const providers = [];
	const commands = [];
	const intervals = [];
	const timeouts = [];
	const workdir = await mkdtemp(join(tmpdir(), "resanity-plugin-"));
	try {
		await mkdir(join(workdir, "anchors"));
		const due = new Date();
		await writeFile(join(workdir, "anchors", "算力链.md"), `## 锚 1\n\n- 更新触发器：${md(due)} 半年报\n`);
		const near = new Date(Date.now() + 2 * MS_PER_DAY);
		await writeFile(join(workdir, "anchors", "光伏.md"), `## 锚 1\n\n- 更新触发器：${iso(near)} 互动易\n`);

		root.provide("skills", { registerProvider: (factory) => providers.push(factory()) });
		root.provide("timer", {
			interval: (fn, ms) => intervals.push({ fn, ms }),
			timeout: (fn, ms) => timeouts.push({ fn, ms }),
		});
		root.provide("commands", { register: (def) => commands.push(def) });
		let agentList = [{ session: { header: { cwd: workdir } } }];
		root.provide("agents", { list: () => agentList });

		await root.plugin({ apply, inject, name, Config }, {
			checkIntervalHours: 6,
			reminderWindowDays: 3,
			systemNotifications: false,
			anchorsDirs: [],
		});

		// provider
		assert.equal(providers.length, 1);
		const candidates = await providers[0].list();
		assert.equal(candidates.length, 1);
		assert.equal(candidates[0].name, "resanity");
		assert.equal(candidates[0].rank, 600);
		assert.ok(candidates[0].description.includes("投资研究可自动使用"));
		assert.ok(candidates[0].description.includes("普通总结、编码、改写或一般问答"));
		const definition = await providers[0].get(candidates[0]);
		assert.ok(definition.content.startsWith("# Resanity"), "正文不含 frontmatter");
		assert.ok(definition.content.includes("原子主张协议"));
		assert.ok(definition.content.includes("观察到什么"));
		assert.ok(definition.content.includes("可以推出什么"));
		assert.ok(definition.content.includes("不能推出什么"));
		assert.ok(definition.content.includes("对决策的影响"));
		assert.ok(definition.content.includes("references/investing.md"));
		assert.equal(existsSync(join(definition.resourceBase.path, "scripts")), true);
		assert.equal(existsSync(join(definition.resourceBase.path, "references", "investing.md")), true);
		assert.equal(existsSync(join(definition.resourceBase.path, "SKILL.md")), true);

		// 命令
		const command = commands.find((c) => c.name === "resanity-check");
		assert.ok(command, "/resanity-check 已注册");
		const result = await command.handler({
			rawInput: "",
			agent: { session: { header: { cwd: workdir } } },
		});
		assert.equal(result.kind, "success");
		assert.ok(result.text.includes("锚触发已到"), result.text);
		assert.ok(result.text.includes("锚触发临近"), result.text);
		agentList = [];
		const empty = await command.handler({ rawInput: "", agent: { session: { header: { cwd: join(workdir, "nope") } } } });
		assert.equal(empty.text, "⚓ 锚体检：无到期触发器");
		agentList = [{ session: { header: { cwd: workdir } } }];

		// 定时器注册与执行逻辑
		assert.equal(intervals.length, 1);
		assert.equal(intervals[0].ms, 6 * 3_600_000);
		assert.equal(timeouts.length, 1);
		assert.equal(timeouts[0].ms, 30_000);
		await intervals[0].fn(); // 不抛异常；systemNotifications: false 不弹通知
		const checkCtx = { get: (service) => (service === "agents" ? { list: () => agentList } : undefined) };
		const check = await runAnchorCheck(checkCtx, {
			anchorsDirs: [],
			reminderWindowDays: 3,
		});
		assert.equal(check.hits.length, 2);
		assert.ok(check.roots.includes(join(workdir, "anchors")));

		// anchorRoots：env + config + 会话 cwd 三来源去重
		const roots = anchorRoots({
			env: { RESANITY_ANCHORS: "/tmp/from-env" },
			config: { anchorsDirs: ["/tmp/from-env"] },
			agents: { list: () => [{ session: { header: { cwd: "/tmp/from-session" } } }] },
		});
		assert.deepEqual(roots, ["/tmp/from-env", "/tmp/from-session/anchors"]);
	} finally {
		await rm(workdir, { recursive: true, force: true });
	}
}

// ── 4. DSH 失败路径回归提示 ────────────────────────────────────────────────
{
	const manifest = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
	assert.equal(manifest.dsh.bundle.patch, "./cordis.patch.yml");
	assert.ok(manifest.files.includes("cordis.patch.yml"));
	const activation = await readFile(new URL("../cordis.patch.yml", import.meta.url), "utf8");
	assert.equal(
		activation,
		"# Keep the bundled patch limited to Skill activation; host profiles own scenario composition.\n" +
			"- insert:\n    - id: resanity\n      name: resanity\n",
	);

	const prompt = await readFile(
		new URL("./fixtures/unreadable-decision.md", import.meta.url),
		"utf8",
	);
	assert.ok(prompt.includes("./decision-document.pdf"));
	assert.ok(prompt.includes("禁止 Web、外部检索和模型记忆补全"));
	assert.ok(prompt.includes("不得重试同一路径或换命令重复读取"));
	assert.ok(prompt.includes("底层血缘仍为 `[E2]`"));
}

// ── 5. tushare 凭据：纯函数 + 命令全路径 ───────────────────────────────────
{
	// credentialsPath 解析优先级
	assert.equal(credentialsPath({ RESANITY_CREDENTIALS: "/x/y.json" }), "/x/y.json");
	assert.equal(
		credentialsPath({ DSH_HOME: "/home/u/.dsh" }),
		"/home/u/.dsh/resanity/credentials.json",
	);
	assert.equal(
		credentialsPath({ DSH_HOME: undefined }),
		join(homedir(), ".dsh", "resanity", "credentials.json"),
	);

	// 在线校验：网络失败 → NETWORK
	const realFetch = globalThis.fetch;
	const TOKEN = "a".repeat(40);
	const dir = await mkdtemp(join(tmpdir(), "resanity-tushare-"));
	const credEnv = { RESANITY_CREDENTIALS: join(dir, "creds", "credentials.json") };
	try {
		globalThis.fetch = async () => {
			throw new Error("offline");
		};
		assert.equal((await validateTushareToken(TOKEN)).code, "NETWORK");

		// 写入/读取/清除
		const path = await writeCredentials(TOKEN, credEnv);
		assert.equal(path, credEnv.RESANITY_CREDENTIALS);
		const mode = (await stat(path)).mode & 0o777;
		assert.equal(mode, 0o600, "凭据文件 600 权限");
		assert.equal((await readCredentials(credEnv)).token, TOKEN);
		await clearCredentials(credEnv);
		assert.equal((await readCredentials(credEnv)).token, "");
	} finally {
		globalThis.fetch = realFetch;
		await rm(dir, { recursive: true, force: true });
	}
}

// ── 6. 插件装配：tushare 命令 ───────────────────────────────────────────────
{
	const root = new Context();
	const commands = [];
	root.provide("skills", { registerProvider: () => {} });
	root.provide("timer", { interval: () => {}, timeout: () => {} });
	root.provide("commands", { register: (def) => commands.push(def) });
	await root.plugin({ apply, inject, name, Config }, {});

	const tushare = commands.find((c) => c.name === "resanity-tushare");
	assert.ok(tushare, "/resanity-tushare 已注册");
	assert.equal(tushare.recordInput, false, "token 不进 command/run 日志");

	const realFetch = globalThis.fetch;
	const savedCredEnv = process.env.RESANITY_CREDENTIALS;
	const dir = await mkdtemp(join(tmpdir(), "resanity-tushare-cmd-"));
	process.env.RESANITY_CREDENTIALS = join(dir, "credentials.json");
	const TOKEN = "a".repeat(40);
	const agent = { session: { header: { cwd: dir } } };
	try {
		// 空输入 / 未知子命令：给出行级用法
		const empty = await tushare.handler({ rawInput: "", agent });
		assert.ok(empty.text.includes("缺少子命令"), empty.text);
		const unknown = await tushare.handler({ rawInput: "help", agent });
		assert.ok(unknown.text.includes("不认识的子命令「help」"), unknown.text);

		// set：不校验长度/格式，保存后自动在线校验
		globalThis.fetch = async () =>
			new Response(JSON.stringify({ code: 0 }), {
				status: 200,
				headers: { "Content-Type": "application/json" },
			});
		const saved = await tushare.handler({ rawInput: `set ${TOKEN}`, agent });
		assert.equal(saved.kind, "success");
		assert.ok(saved.text.includes("自动在线校验通过"), saved.text);
		assert.ok(saved.text.includes("…aaaa"), saved.text);
		assert.ok(!saved.text.includes(TOKEN), "完整 token 不得出现在输出");

		// 非 40 位 hex 也原样保存（无格式门槛）
		const odd = await tushare.handler({ rawInput: "set not-a-token", agent });
		assert.equal(odd.kind, "success", odd.text);
		assert.equal((await readCredentials()).token, "not-a-token");

		// 仅去掉不可见零宽字符，可见字符（引号/横线）原样保留
		const noisy = `set "aaaa-\u200ba${"b".repeat(35)}"`;
		const cleaned = await tushare.handler({ rawInput: noisy, agent });
		assert.equal(cleaned.kind, "success");
		assert.ok(cleaned.text.includes("不可见字符"), cleaned.text);
		assert.equal((await readCredentials()).token, `"aaaa-a${"b".repeat(35)}"`);

		// 恢复 TOKEN，供 status/test 断言
		await tushare.handler({ rawInput: `set ${TOKEN}`, agent });

		// status 脱敏
		const status = await tushare.handler({ rawInput: "status", agent });
		assert.ok(status.text.includes("已配置（…aaaa）"), status.text);
		assert.ok(!status.text.includes(TOKEN));

		// test 通过
		const test = await tushare.handler({ rawInput: "test", agent });
		assert.ok(test.text.includes("在线校验通过"), test.text);

		// 自动在线校验失败：不覆盖已保存的有效 token
		globalThis.fetch = async () =>
			new Response(JSON.stringify({ code: -2002, msg: "token不正确" }), {
				status: 200,
				headers: { "Content-Type": "application/json" },
			});
		const warned = await tushare.handler({ rawInput: `set ${"b".repeat(40)}`, agent });
		assert.equal(warned.kind, "error");
		assert.ok(warned.text.includes("自动在线校验未通过"), warned.text);
		assert.ok(warned.text.includes("-2002"), warned.text);
		assert.equal((await readCredentials()).token, TOKEN);

		// 网络不可用：不保存、不覆盖
		globalThis.fetch = async () => {
			throw new Error("offline");
		};
		const offline = await tushare.handler({ rawInput: `set ${"c".repeat(40)}`, agent });
		assert.equal(offline.kind, "error");
		assert.ok(offline.text.includes("token 未保存"), offline.text);
		assert.equal((await readCredentials()).token, TOKEN);

		// clear → status 未配置
		const cleared = await tushare.handler({ rawInput: "clear", agent });
		assert.ok(cleared.text.includes("已清除"));
		const after = await tushare.handler({ rawInput: "status", agent });
		assert.ok(after.text.includes("未配置"));
	} finally {
		globalThis.fetch = realFetch;
		if (savedCredEnv === undefined) delete process.env.RESANITY_CREDENTIALS;
		else process.env.RESANITY_CREDENTIALS = savedCredEnv;
		await rm(dir, { recursive: true, force: true });
	}
}

// ── 7. 配置门控：dataTools 行挂载数据工具，且不重复定时器/命令 ───────────────
{
	const root = new Context();
	const providers = [];
	const registered = [];
	root.provide("skills", { registerProvider: (factory) => providers.push(factory()) });
	root.provide("tools", { register: (def) => { registered.push(def); return () => {}; } });
	await root.plugin({ apply, inject, name, Config }, {
		dataTools: true,
		anchorTimer: false,
		commands: false,
	});

	assert.equal(providers.length, 1, "skill provider 仍然注册");
	assert.equal(registered.length, 3, "三个数据工具");
	assert.deepEqual(
		registered.map((d) => d.name).sort(),
		["ashare_disclosures", "market_observations", "structured_providers"],
	);
	// 门控关闭时挂载不注册数据工具（默认 config 语义不变量）
	const bare = new Context();
	const bareTools = [];
	bare.provide("skills", { registerProvider: () => {} });
	bare.provide("tools", { register: (def) => bareTools.push(def) });
	await bare.plugin({ apply, inject, name, Config }, {});
	assert.equal(bareTools.length, 0);
}

// ── 8. 数据工具纯函数：argv / 请求对象 / 信封解析 ──────────────────────────
{
	assert.deepEqual(
		buildDisclosureArgs({ ticker: "002015", asOf: "2026-08-19" }),
		["--ticker", "002015", "--as-of", "2026-08-19"],
	);
	assert.deepEqual(
		buildDisclosureArgs({ ticker: "600001", asOf: "2026-08-19", market: "sse", lookbackDays: 60, pageSize: 20, timeoutMs: 15_000 }),
		["--ticker", "600001", "--as-of", "2026-08-19", "--market", "sse", "--lookback-days", "60", "--page-size", "20", "--timeout", "15000"],
	);

	const obs = buildObservationRequest({
		ticker: "002015",
		asOf: "2026-08-19",
		exchange: "XSHE",
		provider: "AUTO",
		benchmarkTicker: "000300",
		benchmarkExchange: "XSHG",
	});
	assert.equal(obs.as_of_date, "2026-08-19");
	assert.equal(obs.lookback_calendar_days, 180);
	assert.equal(obs.provider, "AUTO");
	assert.equal(obs.candidate.ticker, "002015");
	assert.equal(obs.candidate.exchange, "XSHE");
	assert.equal(obs.candidate.asset_type, "EQUITY");
	assert.equal(obs.benchmark.ticker, "000300");
	assert.equal(obs.benchmark.asset_type, "INDEX");
	const override = buildObservationRequest({
		ticker: "600519",
		asOf: "2026-08-19",
		provider: "CSV",
		providerOverrideReason: "手工导入的交易所历史收盘价",
		lookbackDays: 120,
		benchmarkTicker: "000300",
	});
	assert.equal(override.provider_override_reason, "手工导入的交易所历史收盘价");
	assert.equal(override.lookback_calendar_days, 120);
	assert.equal(override.benchmark.ticker, "000300");
	assert.equal(override.benchmark.exchange, "XSHG");
	assert.equal(override.benchmark.asset_type, "INDEX");

	assert.deepEqual(buildProviderArgs({ fred: "DGS10" }), ["--fred", "DGS10"]);
	assert.deepEqual(buildProviderArgs({ edgar: "NVDA", form: "10-K" }), ["--edgar", "NVDA", "--form", "10-K"]);
	assert.deepEqual(
		buildProviderArgs({ comtradeReporter: "156", comtradePartner: "0", comtradeHs: "854143", comtradePeriod: "2023" }),
		["--comtrade", "156", "0", "854143", "2023"],
	);
	assert.equal(buildProviderArgs({}), null);

	// 成功信封透传
	assert.deepEqual(parseToolJson({ code: 0, timedOut: false, stdout: '{"status":"OK","n":1}', stderr: "" }), { status: "OK", n: 1 });
	// 失败信封优先于退出码：脚本把 UNAVAILABLE 等写到 stdout 并带非零退出码
	assert.deepEqual(
		parseToolJson({ code: 2, timedOut: false, stdout: '{"status":"PROVIDER_UNAVAILABLE","reason":"no_ranked_provider_locally_ready"}', stderr: "boom" }),
		{ status: "PROVIDER_UNAVAILABLE", reason: "no_ranked_provider_locally_ready" },
	);
	// 无信封的失败 → EXECUTION_ERROR
	const bareFail = parseToolJson({ code: 2, timedOut: false, stdout: "", stderr: "boom" });
	assert.equal(bareFail.status, "EXECUTION_ERROR");
	assert.equal(bareFail.reason, "exit_code_2");
	assert.equal(parseToolJson({ code: null, timedOut: true, stdout: "", stderr: "" }).reason, "script_timeout");
	assert.equal(parseToolJson({ code: 0, timedOut: false, stdout: "not json", stderr: "" }).reason, "unparseable_output");
	assert.equal(parseToolJson({ code: 0, timedOut: false, stdout: "[1]", stderr: "" }).reason, "non_object_output");
	assert.equal(parseToolJson({ code: 0, timedOut: false, stdout: "", stderr: "" }).reason, "empty_output");
}

// ── 9. runScript：真实 python3 子进程 + 超时/失败路径 ───────────────────────
{
	const dir = await mkdtemp(join(tmpdir(), "resanity-script-"));
	try {
		const okScript = join(dir, "echo_json.py");
		await writeFile(okScript, 'import json\nprint(json.dumps({"status": "OK", "who": "py"}))\n', "utf8");
		const ok = await runScript(okScript, [], { timeoutMs: 10_000 });
		assert.equal(ok.code, 0, ok.stderr);
		assert.deepEqual(parseToolJson(ok), { status: "OK", who: "py" });

		const failScript = join(dir, "fail.py");
		await writeFile(failScript, 'import sys\nprint("oops", file=sys.stderr)\nsys.exit(3)\n', "utf8");
		const fail = await runScript(failScript, [], { timeoutMs: 10_000 });
		assert.equal(fail.code, 3);
		const envelope = parseToolJson(fail);
		assert.equal(envelope.status, "EXECUTION_ERROR");
		assert.equal(envelope.reason, "exit_code_3");
		assert.ok(envelope.stderr.includes("oops"));
	} finally {
		await rm(dir, { recursive: true, force: true });
	}
}

// ── 10. 工具定义通过 defineTool 校验（无网络调用）─────────────────────────
{
	const definitions = buildDataToolDefinitions({ dataToolTimeoutMs: 90_000 });
	assert.equal(definitions.length, 3);
	for (const definition of definitions) {
		assert.ok(definition.name, "每个工具都有名字");
		assert.ok(Object.keys(definition.parameters).length > 0, `${definition.name} 有参数 schema`);
		assert.equal(typeof definition.execute, "function");
	}
	// structured_providers 无模式调用直接拒绝，不触网
	const structured = definitions.find((d) => d.name === "structured_providers");
	const rejected = await structured.execute({});
	assert.equal(rejected.status, "REQUEST_REJECTED");
	assert.equal(rejected.reason, "exactly_one_mode_required");
}

// ── 11. /resanity-init 与 /resanity-audit 命令 ──────────────────────────────
{
	const root = new Context();
	const commands = [];
	root.provide("skills", { registerProvider: () => {} });
	root.provide("commands", { register: (def) => commands.push(def) });
	await root.plugin({ apply, inject, name, Config }, { anchorTimer: false });

	const init = commands.find((c) => c.name === "resanity-init");
	assert.ok(init, "/resanity-init 已注册");
	const audit = commands.find((c) => c.name === "resanity-audit");
	assert.ok(audit, "/resanity-audit 已注册");

	const dir = await mkdtemp(join(tmpdir(), "resanity-init-"));
	try {
		const first = await init.handler({ rawInput: "", agent: { session: { header: { cwd: dir } } } });
		assert.equal(first.kind, "success", first.text);
		assert.equal(existsSync(join(dir, "anchors")), true);
		assert.equal(existsSync(join(dir, "journal", "decisions.md")), true);
		const template = await readFile(join(dir, "journal", "decisions.md"), "utf8");
		assert.ok(template.includes("当时相信"), "决策日志模板内容");
		// 幂等：不覆盖已有文件
		const again = await init.handler({ rawInput: "", agent: { session: { header: { cwd: dir } } } });
		assert.equal(again.kind, "success");
		assert.ok(again.text.includes("已存在"), again.text);

		// 无收据 → 非零退出 + 错误提示，不伪造审计结论
		const missing = await audit.handler({ rawInput: "", agent: { session: { header: { cwd: dir } } } });
		assert.equal(missing.kind, "error");
		assert.ok(missing.text.includes("审计未闭合"), missing.text);
	} finally {
		await rm(dir, { recursive: true, force: true });
	}
}

// ── 12. researchPrompt 门控：三段纪律段落 + /resanity-report ────────────────
{
	const root = new Context();
	const providers = [];
	const sections = [];
	const commands = [];
	root.provide("skills", { registerProvider: (factory) => providers.push(factory()) });
	root.provide("systemPrompt", { section: (section) => { sections.push(section); return () => {}; } });
	root.provide("commands", { register: (def) => commands.push(def) });
	await root.plugin({ apply, inject, name, Config }, {
		researchPrompt: true,
		anchorTimer: false,
	});

	assert.equal(sections.length, 6, "六段研究纪律");
	const names = sections.map((s) => s.name).sort();
	assert.deepEqual(names, ["resanity:claims", "resanity:evidence", "resanity:expand", "resanity:fanout", "resanity:redteam", "resanity:report"]);
	assert.ok(sections.every((s) => typeof s.order === "number" && typeof s.text === "string"));
	assert.ok(sections.find((s) => s.name === "resanity:expand").text.includes("扩展成研究设计"));
	assert.ok(sections.find((s) => s.name === "resanity:expand").text.includes("3–5 行简述研究设计"));
	assert.ok(sections.find((s) => s.name === "resanity:expand").text.includes("语义翻译"));
	assert.ok(sections.find((s) => s.name === "resanity:evidence").text.includes("数据优先走数据工具"));
	assert.ok(sections.find((s) => s.name === "resanity:evidence").text.includes("web_fetch 只用于具名一手来源"));
	assert.ok(sections.find((s) => s.name === "resanity:claims").text.includes("唯一下一验证"));
	assert.ok(sections.find((s) => s.name === "resanity:fanout").text.includes("父代理职责：主张合成"));
	assert.ok(sections.find((s) => s.name === "resanity:fanout").text.includes("子代理指令模板"));
	assert.ok(sections.find((s) => s.name === "resanity:redteam").text.includes("只攻击、不修补"));
	assert.ok(sections.find((s) => s.name === "resanity:redteam").text.includes("self-countercase"));
	assert.ok(sections.find((s) => s.name === "resanity:report").text.includes("主张树"));
	assert.ok(sections.find((s) => s.name === "resanity:report").text.includes("决策菜单"));
	assert.ok(sections.find((s) => s.name === "resanity:report").text.includes("建议锚草稿"));

	const report = commands.find((c) => c.name === "resanity-report");
	assert.ok(report, "/resanity-report 已注册");
	const dir = await mkdtemp(join(tmpdir(), "resanity-report-"));
	try {
		const missing = await report.handler({ rawInput: "", agent: { session: { header: { cwd: dir } } } });
		assert.equal(missing.kind, "error", "缺报告文件 → 错误路径而非伪造通过");
		assert.ok(missing.text.includes("交付检查"), missing.text);
	} finally {
		await rm(dir, { recursive: true, force: true });
	}

	// 门控关闭时不注册段落（默认 config 语义不变量）
	const bare = new Context();
	const bareSections = [];
	bare.provide("skills", { registerProvider: () => {} });
	bare.provide("systemPrompt", { section: (s) => bareSections.push(s) });
	await bare.plugin({ apply, inject, name, Config }, {});
	assert.equal(bareSections.length, 0);
}

// ── 13. 锚预采集解析与公告紧凑输出 ─────────────────────────────────────────
{
	assert.deepEqual(
		parseAnchorInstrument("## 锚\n- 标的：002015\n- 市场：SZ\n- 更新触发器：2026-08-25\n"),
		{ ticker: "002015", exchange: "XSHE", benchmarkTicker: undefined, benchmarkExchange: undefined },
	);
	assert.equal(parseAnchorInstrument("## 锚\n- 更新触发器：2026-08-25\n"), null);
	const full = parseAnchorInstrument("- 标的：600519\n- 市场：XSHG\n- 基准：000300\n");
	assert.equal(full.ticker, "600519");
	assert.equal(full.exchange, "XSHG");
	assert.equal(full.benchmarkTicker, "000300");
	assert.equal(full.benchmarkExchange, undefined, "基准未显式声明市场时交给配置默认值");
	const english = parseAnchorInstrument("- ticker: 300750\n- exchange: SZ\n- 基准：000905（XSHE）\n");
	assert.equal(english.exchange, "XSHE");
	assert.equal(english.benchmarkTicker, "000905");
	assert.equal(english.benchmarkExchange, "XSHE");

	const envelope = {
		status: "OK",
		announcement_count: 3,
		announcements: [
			{ category: "pledge_restriction", title: "A" },
			{ category: "other", title: "B" },
			{ category: "pledge_restriction", title: "C" },
		],
	};
	const compact = summarizeDisclosures(envelope, {});
	assert.equal(compact.announcements, undefined, "紧凑模式不携带全量列表");
	assert.equal(compact.announcement_count, 3);
	assert.deepEqual(compact.category_counts, { pledge_restriction: 2, other: 1 });
	assert.equal(compact.recent.length, 3);
	assert.equal(compact.compact, true);
	assert.ok(compact.note.includes("compact:false"));
	assert.equal(summarizeDisclosures(envelope, { compact: false }), envelope, "compact:false 保留全量信封");
	const filtered = summarizeDisclosures(envelope, { categories: ["other"], limit: 1 });
	assert.equal(filtered.recent.length, 1);
	assert.equal(filtered.recent[0].title, "B");

	// collectAnchorLines 门控：关闭时不采集；开启但锚未声明标的时仍只是纯提醒
	const hits = [{ theme: "算力链", when: new Date(), days: 0, kind: "due", root: join(tmpdir(), "no-such-anchors") }];
	const off = await collectAnchorLines({ get: () => undefined }, { prefetchObservations: false }, hits);
	assert.equal(off.length, 1);
	const on = await collectAnchorLines({ get: () => undefined }, { prefetchObservations: true }, hits);
	assert.equal(on.length, 1, "无法读取锚文件/未声明标的时不追加采集行");
	assert.ok(on[0].includes("锚触发已到"));
}

// ── 14. /resanity-review 注册与失效追踪 ─────────────────────────────────────
{
	const root = new Context();
	const commands = [];
	root.provide("skills", { registerProvider: () => {} });
	root.provide("commands", { register: (def) => commands.push(def) });
	await root.plugin({ apply, inject, name, Config }, { anchorTimer: false });

	const review = commands.find((c) => c.name === "resanity-review");
	assert.ok(review, "/resanity-review 已注册");
	assert.ok(review.description.includes("不自动改协议"), "命令声明边界：只统计不改协议");
}

console.log("resanity plugin tests: all passed");
