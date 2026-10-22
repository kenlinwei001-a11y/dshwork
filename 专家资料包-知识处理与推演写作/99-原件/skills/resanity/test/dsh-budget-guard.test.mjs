import assert from "node:assert/strict";
import {
	TOOL_LIMIT_REASON,
	WEB_LIMIT_REASON,
	apply,
	createBudgetGuard,
} from "../validation/v2/dsh-budget-guard/index.js";

{
	const agent = {};
	const budget = createBudgetGuard({ maxToolCalls: 2, maxWebSearches: 1 });
	assert.equal(budget.guard({ agent, name: "skill" }), undefined);
	assert.equal(budget.guard({ agent, name: "web_search" }), undefined);
	assert.equal(budget.guard({ agent, name: "bash" }), TOOL_LIMIT_REASON);
	assert.deepEqual(budget.stateFor(agent), { toolCalls: 2, webSearches: 1 });
}

{
	const agent = {};
	const budget = createBudgetGuard({ maxToolCalls: 3, maxWebSearches: 1 });
	assert.equal(budget.guard({ agent, name: "web_search" }), undefined);
	assert.equal(budget.guard({ agent, name: "web_search" }), WEB_LIMIT_REASON);
	assert.equal(budget.guard({ agent, name: "read" }), undefined);
	assert.deepEqual(budget.stateFor(agent), { toolCalls: 2, webSearches: 1 });
}

{
	let guard;
	let preStep;
	const restrictions = [];
	const ctx = {
		tools: { guard: (value) => { guard = value; } },
		on: (event, listener) => {
			if (event === "agent/pre-step") preStep = listener;
		},
	};
	apply(ctx, { maxToolCalls: 1, maxWebSearches: 1 });
	const agent = {
		ctx: {
			tools: {
				schemas: () => [{ name: "skill" }, { name: "web_search" }, { name: "bash" }],
				restrict: (filter) => restrictions.push(filter),
			},
		},
	};
	assert.equal(guard({ agent, name: "skill" }), undefined);
	await preStep({ agent }, async () => undefined);
	assert.deepEqual(restrictions, [{ deny: ["skill", "web_search", "bash"] }]);
}

console.log("DSH validation budget guard tests: all passed");
