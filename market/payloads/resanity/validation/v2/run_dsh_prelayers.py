#!/usr/bin/env python3
"""Collect all six Resanity v2 prelayers through DSH without semantic scoring."""
from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DSH_RUNNER_PATH = ROOT / "validation/v2/run_final_ab_dsh.py"
_SPEC = importlib.util.spec_from_file_location("resanity_final_ab_dsh", DSH_RUNNER_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load DSH runner")
DSH = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(DSH)
BASE = DSH.BASE
PrelayerError = BASE.FinalAbError
SCHEMA_VERSION = "resanity.dsh-prelayer-collection.v1"


def plan(suite: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    layers = suite["layers"]
    result: dict[str, list[dict[str, Any]]] = {}
    for layer in ("core_contract", "investing_profile", "open_network", "anchor"):
        rows = []
        for case in layers[layer]["cases"]:
            prompt = (BASE.SUITE_PATH.parent / case["prompt"]).resolve()
            if not prompt.is_file():
                raise PrelayerError(f"prompt missing: {prompt}")
            rows.append({**case, "layer": layer, "prompt_path": prompt})
        result[layer] = rows
    result["trigger"] = [
        {**case, "layer": "trigger"} for case in layers["trigger"]["cases"]
    ]
    if sum(len(rows) for rows in result.values()) != 25:
        raise PrelayerError("DSH prelayer plan must contain exactly 25 sessions")
    return result


def select_plan(
    layers: dict[str, list[dict[str, Any]]], case_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    if not case_ids:
        return layers
    if len(set(case_ids)) != len(case_ids):
        raise PrelayerError("--case values must be unique")
    known = {
        case["id"]: case
        for rows in layers.values()
        for case in rows
    }
    unknown = sorted(set(case_ids) - set(known))
    if unknown:
        raise PrelayerError(f"unknown prelayer case(s): {', '.join(unknown)}")
    selected = {
        layer: [case for case in rows if case["id"] in case_ids]
        for layer, rows in layers.items()
    }
    anchor_groups: dict[str, int] = {}
    for case in selected["anchor"]:
        group = case["workspace_group"]
        anchor_groups[group] = anchor_groups.get(group, 0) + 1
    incomplete_groups = sorted(
        group for group, count in anchor_groups.items() if count != 2
    )
    if incomplete_groups:
        raise PrelayerError(
            "longitudinal anchor groups must select both cases: "
            + ", ".join(incomplete_groups)
        )
    return selected


def shared_instruction(args: argparse.Namespace) -> str:
    return (
        f"统一运行日期为 {args.run_date.isoformat()}。任务内显式 as-of 优先；不得使用其后的信息回填。\n"
        f"宿主预算上限：{args.max_non_cached_input_tokens} 非缓存输入 token、"
        f"{args.max_tool_calls} 次工具调用、{args.max_web_searches} 次 Web 搜索、"
        f"{args.max_wall_seconds} 秒，由宿主计量和强制执行；不得估算已用或剩余次数。"
        "收到一次预算拒绝就用现有证据交付；失败动作不换同义工具重试，不启动子代理。\n"
        "封闭任务禁止外部检索。开放网络任务把每个承重来源快照保存到工作区 sources/。\n"
        "最终消息只交付任务结果，不提及评测、评分规则、运行计量或本指令。"
    )


def trigger_instruction(args: argparse.Namespace) -> str:
    return (
        f"统一运行日期为 {args.run_date.isoformat()}。"
        f"本次宿主最多执行 {args.max_tool_calls} 次工具调用和 {args.max_web_searches} 次 Web 搜索；"
        "不得估算已用或剩余次数，收到一次预算拒绝就用现有材料交付。"
        "失败动作不换同义工具重试，不启动子代理。\n\n"
    )


def copy_tree(source: Path, target: Path) -> int:
    if not source.is_dir():
        return 0
    count = 0
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        count += 1
    return count


def run_session(
    *,
    args: argparse.Namespace,
    case: dict[str, Any],
    prompt: str,
    workspace: Path,
    artifact: Path,
) -> dict[str, Any]:
    artifact.mkdir(parents=True, exist_ok=False)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "sources").mkdir(exist_ok=True)
    session_root = artifact / "session-store"
    session_root.mkdir()
    isolated_home = artifact / "isolated-home"
    isolated_home.mkdir()
    patch_path = artifact / "session.patch.yml"
    patch_path.write_text(
        DSH.session_patch(
            session_root, args.max_tool_calls, args.max_web_searches
        ),
        encoding="utf-8",
    )
    (artifact / "composed-prompt.md").write_text(prompt, encoding="utf-8")

    environment = os.environ.copy()
    environment["DSH_HOME"] = str(args.dsh_home)
    environment["HOME"] = str(isolated_home)
    environment["DSH_PERMISSION_MODE"] = "workspace-write"
    environment["DSH_TELEMETRY_MODE"] = "DISABLED"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.update(DSH.WATCH_ENVIRONMENT)
    environment.pop("TUSHARE_TOKEN", None)
    environment.pop("RESANITY_CREDENTIALS", None)
    command = [
        args.dsh_bin,
        "--profile",
        args.candidate_profile,
        "--patch",
        str(patch_path),
        prompt,
    ]
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=args.max_wall_seconds,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        exit_code = 124
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        stderr += f"\nrunner timeout after {args.max_wall_seconds}s\n"
    wall_seconds = round(time.monotonic() - started, 3)
    (artifact / "stdout.md").write_text(stdout, encoding="utf-8")
    (artifact / "stderr.log").write_text(stderr, encoding="utf-8")
    (artifact / "exit-code").write_text(f"{exit_code}\n", encoding="utf-8")

    sessions = sorted(session_root.rglob("session.jsonl.zstd"))
    raw = artifact / "raw-session.jsonl.zstd"
    metrics: dict[str, Any] = {}
    skills: list[str] = []
    if len(sessions) == 1:
        shutil.copy2(sessions[0], raw)
        events = DSH.read_dsh_events(raw, args.zstd_bin)
        metrics = DSH.parse_dsh_metrics(events)
        skills = DSH.skill_names(events)

    source_count = copy_tree(workspace / "sources", artifact / "sources")
    anchor_count = copy_tree(workspace / "anchors", artifact / "anchors")
    failures = []
    if exit_code != 0:
        failures.append("dsh_exit_code")
    if len(sessions) != 1:
        failures.append("raw_session_count")
    report_failures = DSH.report_delivery_failures(stdout)
    failures.extend(report_failures)
    report_present = not report_failures
    report_available = report_present
    report_origin = "final_response" if report_present else "missing"
    recovered_report = None
    if report_present:
        (artifact / "report.md").write_text(stdout, encoding="utf-8")
    else:
        recovered_report = DSH.recover_workspace_report(
            workspace, artifact / "recovered-report.md"
        )
        if recovered_report is not None:
            shutil.copy2(artifact / "recovered-report.md", artifact / "report.md")
            report_available = True
            report_origin = "workspace_recovery"
    delivery_failures: list[str] = []
    trace_failures: list[str] = []
    delivery_contract = case.get("delivery_regression")
    if isinstance(delivery_contract, dict):
        delivery_failures = DSH.delivery_contract_failures(
            stdout,
            delivery_contract,
            saved_report=(workspace / "report.md").is_file()
            or (workspace / "REPORT.md").is_file(),
        )
        trace_failures = DSH.trace_contract_failures(metrics, delivery_contract)
        failures.extend(delivery_failures)
        failures.extend(trace_failures)
    if metrics:
        expected = {
            "provider": args.expected_provider,
            "model": args.expected_model,
            "reasoning_effort": args.expected_reasoning_effort,
            "permission_preset": "workspace-write",
            "sandbox_mode": "workspace-write",
            "approval_policy": "ask",
            "session_cwd": str(workspace),
        }
        for key, value in expected.items():
            if metrics.get(key) != value:
                failures.append(f"host_{key}_mismatch")
        if DSH.integer(metrics.get("input_tokens")) > args.max_non_cached_input_tokens:
            failures.append("non_cached_input_tokens")
        if DSH.integer(metrics.get("tool_calls")) > args.max_tool_calls:
            failures.append("tool_calls")
        if DSH.integer(metrics.get("web_search")) > args.max_web_searches:
            failures.append("web_search")
        if DSH.integer(metrics.get("host_retry_events")):
            failures.append("host_retry_events")
        if DSH.integer(metrics.get("malformed_jsonl_lines")):
            failures.append("malformed_jsonl_lines")
    if wall_seconds > args.max_wall_seconds:
        failures.append("wall_seconds")

    invocations = skills.count("resanity")
    if case["layer"] == "trigger":
        expected_invocation = case["expected_invocation"]
        if (invocations == 1) != expected_invocation:
            failures.append("trigger_invocation_mismatch")
    elif invocations != 1:
        failures.append("candidate_resanity_invocation_count")
    if case.get("mode") == "open" and source_count == 0:
        failures.append("open_case_source_snapshots_missing")
    if case["layer"] == "anchor" and anchor_count == 0:
        failures.append("anchor_artifacts_missing")

    host_receipt = {
        "schema_version": "resanity.host-receipt.v1",
        "host": "dsh",
        "profile": args.candidate_profile,
        "provider": metrics.get("provider"),
        "model": metrics.get("model"),
        "reasoning_effort": metrics.get("reasoning_effort"),
        "session_id": metrics.get("session_id"),
        "runtime": {
            "input_tokens": metrics.get("input_tokens"),
            "output_tokens": metrics.get("output_tokens"),
            "reasoning_tokens": metrics.get("reasoning_tokens"),
            "cache_read_tokens": metrics.get("cache_read_tokens"),
            "tool_calls": metrics.get("tool_calls"),
            "tool_call_attempts": metrics.get("tool_call_attempts"),
            "budget_denied_tool_calls": metrics.get("budget_denied_tool_calls"),
            "tool_result_failures": metrics.get("tool_result_failures"),
            "wall_seconds": wall_seconds,
        },
        "host_signature": DSH.host_signature(metrics),
        "tool_calls_by_name": metrics.get("tool_calls_by_name", {}),
        "tool_call_attempts_by_name": metrics.get("tool_call_attempts_by_name", {}),
        "budget_denied_tool_calls_by_name": metrics.get(
            "budget_denied_tool_calls_by_name", {}
        ),
        "tool_result_failures_by_name": metrics.get(
            "tool_result_failures_by_name", {}
        ),
        "tool_result_failure_reasons": metrics.get(
            "tool_result_failure_reasons", {}
        ),
        "tool_trace": DSH.receipt_tool_trace(metrics),
        "invoked_skills": skills,
        "raw_session": (
            {"path": raw.name, "sha256": BASE.sha256_file(raw)}
            if raw.is_file()
            else None
        ),
        "runner": {
            "automatic_retries": 0,
            "host_retry_events": metrics.get("host_retry_events"),
            "timed_out": timed_out,
            "session_artifacts": len(sessions),
            "recovered_report": recovered_report,
            "report_available": report_available,
            "report_origin": report_origin,
        },
    }
    BASE.write_json(artifact / "host-receipt.json", host_receipt)
    row = {
        "id": case["id"],
        "layer": case["layer"],
        "profile": case.get("profile"),
        "mode": case.get("mode"),
        "host_complete": not failures,
        "report_present": report_present,
        "report_available": report_available,
        "report_origin": report_origin,
        "recovered_report": recovered_report is not None,
        "semantic_review": "NOT_REVIEWED",
        "resanity_invocations": invocations,
        "source_files": source_count,
        "anchor_files": anchor_count,
        "wall_seconds": wall_seconds,
        "mechanical_failures": failures,
        "delivery_contract_failures": delivery_failures,
        "trace_contract_failures": trace_failures,
        "artifact": str(artifact.relative_to(args.output)),
    }
    BASE.write_json(artifact / "collection-result.json", row)
    return row


def run_independent_cases(
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    candidate_instruction: str,
    shared: str,
) -> list[dict[str, Any]]:
    jobs = list(rows)
    random.Random(args.seed).shuffle(jobs)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {}
        for case in jobs:
            if case["layer"] == "trigger":
                prompt = trigger_instruction(args) + case["input"]
            else:
                task = case["prompt_path"].read_text(encoding="utf-8")
                prompt = BASE.compose_prompt(candidate_instruction, shared, task)
            workspace = args.output / "workspaces" / case["id"]
            artifact = args.output / "cases" / case["id"]
            future = executor.submit(
                run_session,
                args=args,
                case=case,
                prompt=prompt,
                workspace=workspace,
                artifact=artifact,
            )
            futures[future] = case
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            results.append(row)
            print(
                f"{row['id']}: {'HOST_COMPLETE' if row['host_complete'] else 'HOST_INCOMPLETE'}",
                file=sys.stderr,
                flush=True,
            )
    return results


def run_anchor_groups(
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    candidate_instruction: str,
    shared: str,
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for case in rows:
        groups.setdefault(case["workspace_group"], []).append(case)
    for cases in groups.values():
        if len(cases) != 2:
            raise PrelayerError("each anchor group must contain two ordered cases")

    def one_group(item: tuple[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        group, cases = item
        workspace = args.output / "workspaces/anchor" / group
        group_rows = []
        for case in cases:
            task = case["prompt_path"].read_text(encoding="utf-8")
            prompt = BASE.compose_prompt(candidate_instruction, shared, task)
            artifact = args.output / "cases" / case["id"]
            group_rows.append(
                run_session(
                    args=args,
                    case=case,
                    prompt=prompt,
                    workspace=workspace,
                    artifact=artifact,
                )
            )
        return group_rows

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, args.concurrency)) as executor:
        futures = [executor.submit(one_group, item) for item in sorted(groups.items())]
        for future in concurrent.futures.as_completed(futures):
            for row in future.result():
                results.append(row)
                print(
                    f"{row['id']}: {'HOST_COMPLETE' if row['host_complete'] else 'HOST_INCOMPLETE'}",
                    file=sys.stderr,
                    flush=True,
                )
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="launch 25 paid DSH sessions")
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="run only this case id; repeat for a targeted bridge (default: all 25)",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-root", type=Path, default=ROOT)
    parser.add_argument("--expected-skill-sha256", required=True)
    parser.add_argument("--dsh-bin", default=shutil.which("dsh") or "dsh")
    parser.add_argument("--dsh-home", type=Path, required=True)
    parser.add_argument("--baseline-profile", default="headless-baseline")
    parser.add_argument("--candidate-profile", default="headless-resanity")
    parser.add_argument("--active-skill", type=Path, required=True)
    parser.add_argument("--expected-provider", required=True)
    parser.add_argument("--expected-model", required=True)
    parser.add_argument("--expected-reasoning-effort", required=True)
    parser.add_argument("--zstd-bin", default=shutil.which("zstd") or "zstd")
    parser.add_argument("--run-date", type=BASE.parse_date, default=date.today())
    parser.add_argument("--seed", default="resanity-v2-dsh-prelayers")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--max-non-cached-input-tokens", type=int, default=150_000)
    parser.add_argument("--max-tool-calls", type=int, default=30)
    parser.add_argument("--max-web-searches", type=int, default=15)
    parser.add_argument("--max-wall-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    args.candidate_root = args.candidate_root.resolve()
    args.dsh_home = args.dsh_home.expanduser().resolve()
    args.active_skill = args.active_skill.expanduser().resolve()
    args.isolated_user_home = Path("/nonexistent/resanity-dsh-prelayers-user")
    if args.output is not None:
        args.output = args.output.expanduser().resolve()
    if args.run and args.output is None:
        parser.error("--output is required with --run")
    if args.output is not None:
        try:
            args.output.relative_to(ROOT)
        except ValueError:
            pass
        else:
            parser.error("--output must be outside the source repository")
    if not 1 <= args.concurrency <= 4:
        parser.error("--concurrency must be between 1 and 4")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    BASE.run_source_contract()
    suite = BASE.load_suite()
    layers = select_plan(plan(suite), args.case)
    session_count = sum(len(rows) for rows in layers.values())
    if session_count == 0:
        raise PrelayerError("targeted prelayer plan is empty")
    skill_sha = BASE.validate_expected_skill(
        args.candidate_root, args.expected_skill_sha256, required=True
    )
    profiles_sha = BASE.profile_hashes(args.candidate_root)
    version = DSH.dsh_version(args.dsh_bin)
    compressor = DSH.zstd_version(args.zstd_bin)
    pair = DSH.profile_pair_receipt(args, skill_sha)
    runtime_patch = DSH.validate_runtime_patch(args)
    dry = {
        "schema_version": SCHEMA_VERSION,
        "status": "DRY_RUN_READY",
        "method_status": "UNBENCHMARKED_CURRENT",
        "semantic_review": "NOT_RUN",
        "candidate_skill_sha256": skill_sha,
        "candidate_profiles_sha256": profiles_sha,
        "host": {
            "adapter": "dsh-headless",
            "version": version,
            "provider": args.expected_provider,
            "model": args.expected_model,
            "reasoning_effort": args.expected_reasoning_effort,
        },
        "profile_pair": pair,
        "runtime_patch": runtime_patch,
        "zstd_version": compressor,
        "layer_counts": {layer: len(rows) for layer, rows in layers.items()},
        "selected_case_ids": sorted(
            case["id"] for rows in layers.values() for case in rows
        ),
        "session_count": session_count,
        "automatic_retries": 0,
    }
    if not args.run:
        print(BASE.canonical_json(dry), end="")
        return 0

    assert args.output is not None
    if args.output.exists():
        raise PrelayerError(f"output already exists; refusing overwrite: {args.output}")
    args.output.mkdir(parents=True)
    manifest = {
        **dry,
        "status": "RUNNING",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "seed": args.seed,
        "concurrency": args.concurrency,
        "budgets_per_session": {
            "non_cached_input_tokens": args.max_non_cached_input_tokens,
            "tool_calls": args.max_tool_calls,
            "web_search": args.max_web_searches,
            "wall_seconds": args.max_wall_seconds,
        },
    }
    BASE.write_json(args.output / "run-manifest.json", manifest)
    candidate_instruction = (
        BASE.SUITE_PATH.parent / suite["layers"]["final_ab"]["candidate_prompt"]
    ).read_text(encoding="utf-8")
    shared = shared_instruction(args)
    independent = [
        *layers["core_contract"],
        *layers["investing_profile"],
        *layers["open_network"],
        *layers["trigger"],
    ]
    results = run_independent_cases(
        args, independent, candidate_instruction, shared
    )
    if layers["anchor"]:
        results.extend(
            run_anchor_groups(args, layers["anchor"], candidate_instruction, shared)
        )
    results.sort(key=lambda row: row["id"])
    complete = sum(row["host_complete"] for row in results)
    status = (
        "HOST_COLLECTION_COMPLETE_AWAITING_SEMANTIC_REVIEW"
        if complete == session_count
        else "HOST_COLLECTION_INCOMPLETE"
    )
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "method_status": "UNBENCHMARKED_CURRENT",
        "semantic_review": "NOT_RUN",
        "candidate_skill_sha256": skill_sha,
        "candidate_profiles_sha256": profiles_sha,
        "selected_case_ids": dry["selected_case_ids"],
        "completed_sessions": complete,
        "expected_sessions": session_count,
        "automatic_retries": 0,
        "results": results,
        "next_step": "manual semantic review by layer; collection status is not a layer PASS",
    }
    BASE.write_json(args.output / "collection-summary.json", summary)
    BASE.write_json(
        args.output / "run-manifest.json",
        {
            **manifest,
            "status": status,
            "completed_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "completed_sessions": complete,
            "expected_sessions": session_count,
        },
    )
    print(BASE.canonical_json(summary), end="")
    return 0 if complete == session_count else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PrelayerError, OSError, json.JSONDecodeError) as error:
        print(f"DSH_PRELAYERS_BLOCKED: {error}", file=sys.stderr)
        raise SystemExit(2)
