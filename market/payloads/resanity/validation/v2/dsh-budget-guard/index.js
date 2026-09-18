import z from "@deepseek-ai/schemastery";

const name = "resanity-validation-budget";
const inject = ["tools"];

const TOOL_LIMIT_REASON = "RESANITY_VALIDATION_BUDGET_TOOL_LIMIT";
const WEB_LIMIT_REASON = "RESANITY_VALIDATION_BUDGET_WEB_LIMIT";

const Config = z.object({
	maxToolCalls: z.number().default(30),
	maxWebSearches: z.number().default(15),
});

function validateLimit(value, key) {
	if (!Number.isInteger(value) || value < 1) {
		throw new Error(`${name}: ${key} must be a positive integer`);
	}
}

/**
 * Admit at most the configured number of actual tool executions per agent.
 * Calls denied by this guard never enter a tool body. The raw transcript keeps
 * the denied attempt so the runner can report both attempts and executions.
 */
export function createBudgetGuard({ maxToolCalls, maxWebSearches }) {
	validateLimit(maxToolCalls, "maxToolCalls");
	validateLimit(maxWebSearches, "maxWebSearches");
	const states = new WeakMap();
	const stateFor = (agent) => {
		let state = states.get(agent);
		if (state === undefined) {
			state = { toolCalls: 0, webSearches: 0 };
			states.set(agent, state);
		}
		return state;
	};
	const guard = (exec) => {
		if (exec.agent === undefined) return undefined;
		const state = stateFor(exec.agent);
		if (exec.name === "web_search" && state.webSearches >= maxWebSearches) {
			return WEB_LIMIT_REASON;
		}
		if (state.toolCalls >= maxToolCalls) return TOOL_LIMIT_REASON;
		state.toolCalls += 1;
		if (exec.name === "web_search") state.webSearches += 1;
		return undefined;
	};
	return { guard, stateFor };
}

function apply(ctx, config) {
	const budget = createBudgetGuard(config);
	ctx.tools.guard(budget.guard);

	// Once a ceiling is reached, remove the exhausted surface before the next
	// model request. The guard remains the exact enforcement point for any
	// additional calls already emitted in the same assistant step.
	const restrictions = new WeakMap();
	ctx.on("agent/pre-step", ({ agent }, next) => {
		const state = budget.stateFor(agent);
		let installed = restrictions.get(agent);
		if (installed === undefined) {
			installed = { all: false, web: false };
			restrictions.set(agent, installed);
		}
		if (!installed.all && state.toolCalls >= config.maxToolCalls) {
			const visible = agent.ctx.tools
				.schemas()
				.map((tool) => tool.name)
				.filter((toolName) => toolName !== "run_code");
			if (visible.length > 0) agent.ctx.tools.restrict({ deny: visible });
			installed.all = true;
		} else if (
			!installed.web &&
			state.webSearches >= config.maxWebSearches &&
			agent.ctx.tools.schemas().some((tool) => tool.name === "web_search")
		) {
			agent.ctx.tools.restrict({ deny: ["web_search"] });
			installed.web = true;
		}
		return next();
	});
}

export {
	Config,
	TOOL_LIMIT_REASON,
	WEB_LIMIT_REASON,
	apply,
	inject,
	name,
};
