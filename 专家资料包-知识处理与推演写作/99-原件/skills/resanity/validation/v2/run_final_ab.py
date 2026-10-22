#!/usr/bin/env python3
"""Collect the eight-case paired Resanity v2 A/B without scoring semantics.

Dry-run is the default.  A real run requires an explicit frozen Skill hash, a
same-hash prelayer PASS receipt, a new output directory, and ``--run``.  Each
arm is launched exactly once in an isolated Codex home/workspace.  The script
preserves raw host events, measured usage, prompts, reports, source snapshots,
identity receipts, and a separately blinded review tree; it never retries or
decides which report is better.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SUITE_PATH = ROOT / "validation/v2/suite.json"
SOURCE_CHECK = ROOT / "tools/validation_source_check.py"
IDENTITY_CHECK = ROOT / "tools/skill_identity.py"
SCHEMA_VERSION = "resanity.final-ab-collection.v1"
PRELAYERS_SCHEMA_VERSION = "resanity.prelayers-receipt.v2"
REQUIRED_PRELAYERS = (
    "core_contract",
    "investing_profile",
    "open_network",
    "anchor",
    "trigger",
    "install_identity",
)
ARMS = ("baseline", "candidate")
NON_TOOL_ITEM_TYPES = {"agent_message", "reasoning"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROFILE_NAMES = ("core", "investing", "anchors", "formal-audit")


class FinalAbError(RuntimeError):
    """Fail-closed final A/B setup or collection error."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value), encoding="utf-8")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalAbError(f"cannot read JSON {path}: {error}") from error


def load_suite() -> dict[str, Any]:
    suite = load_json(SUITE_PATH)
    if not isinstance(suite, dict) or suite.get("schema") != "resanity.validation-suite.v2":
        raise FinalAbError("validation/v2/suite.json schema mismatch")
    return suite


def run_source_contract() -> None:
    result = subprocess.run(
        [sys.executable, str(SOURCE_CHECK)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise FinalAbError(f"validation source contract failed: {detail[-2000:]}")


def semantic_cases(suite: dict[str, Any]) -> dict[str, dict[str, Any]]:
    layers = suite["layers"]
    rows: dict[str, dict[str, Any]] = {}
    for layer_name in ("core_contract", "investing_profile", "open_network"):
        for row in layers[layer_name]["cases"]:
            rows[row["id"]] = {**row, "layer": layer_name}
    return rows


def final_ab_plan(suite: dict[str, Any]) -> list[dict[str, Any]]:
    final_ab = suite["layers"]["final_ab"]
    cases = semantic_cases(suite)
    case_ids = final_ab["case_ids"]
    if len(case_ids) != 8 or len(set(case_ids)) != 8:
        raise FinalAbError("final A/B must contain exactly eight unique cases")
    plan = []
    for case_id in case_ids:
        if case_id not in cases:
            raise FinalAbError(f"unknown final A/B case: {case_id}")
        row = cases[case_id]
        prompt_path = (SUITE_PATH.parent / row["prompt"]).resolve()
        if not prompt_path.is_file():
            raise FinalAbError(f"task prompt missing: {prompt_path}")
        plan.append(
            {
                "id": case_id,
                "layer": row["layer"],
                "mode": row["mode"],
                "profile": row["profile"],
                "prompt_path": prompt_path,
                "task_prompt_sha256": sha256_file(prompt_path),
            }
        )
    return plan


def validate_expected_skill(candidate_root: Path, expected: str | None, *, required: bool) -> str:
    skill_path = candidate_root / "SKILL.md"
    if not skill_path.is_file():
        raise FinalAbError(f"candidate SKILL.md missing: {skill_path}")
    actual = sha256_file(skill_path)
    if required and expected is None:
        raise FinalAbError("--expected-skill-sha256 is required with --run")
    if expected is not None:
        if not SHA256_RE.fullmatch(expected):
            raise FinalAbError("--expected-skill-sha256 must be 64 lowercase hex characters")
        if actual != expected:
            raise FinalAbError(f"candidate Skill hash drift: expected {expected}, actual {actual}")
    return actual


def profile_hashes(candidate_root: Path) -> dict[str, str]:
    hashes = {}
    for profile in PROFILE_NAMES:
        result = subprocess.run(
            [
                sys.executable,
                str(IDENTITY_CHECK),
                "--canonical-root",
                str(candidate_root),
                "--host",
                "generic",
                "--profile",
                profile,
                "--active-skill",
                str(candidate_root / "SKILL.md"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise FinalAbError(f"cannot hash candidate profile {profile}: {detail[-2000:]}")
        receipt = json.loads(result.stdout)
        profile_data = receipt.get("canonical", {}).get("profile", {})
        profile_sha = profile_data.get("sha256")
        if not isinstance(profile_sha, str) or not SHA256_RE.fullmatch(profile_sha):
            raise FinalAbError(f"candidate profile hash missing: {profile}")
        hashes[profile] = profile_sha
    return hashes


def validate_prelayers(
    path: Path | None,
    expected_skill_sha256: str,
    expected_profile_sha256: dict[str, str],
    *,
    required: bool,
    allow_known_failures: bool = False,
) -> dict[str, Any] | None:
    if path is None:
        if required:
            raise FinalAbError("--prelayers-receipt is required with --run")
        return None
    receipt = load_json(path)
    if not isinstance(receipt, dict):
        raise FinalAbError("prelayer receipt root must be an object")
    if receipt.get("schema_version") != PRELAYERS_SCHEMA_VERSION:
        raise FinalAbError("prelayer receipt schema mismatch")
    status = receipt.get("status")
    accepted_with_failures = (
        allow_known_failures
        and status == "PRELAYERS_ACCEPTED_WITH_KNOWN_FAILURES"
    )
    if status != "PRELAYERS_PASS" and not accepted_with_failures:
        raise FinalAbError(
            "prelayer receipt is neither PRELAYERS_PASS nor an explicitly "
            "accepted known-failure receipt"
        )
    if receipt.get("candidate_skill_sha256") != expected_skill_sha256:
        raise FinalAbError("prelayer receipt belongs to a different candidate Skill hash")
    if receipt.get("candidate_profiles_sha256") != expected_profile_sha256:
        raise FinalAbError("prelayer receipt belongs to different candidate profile hashes")
    layers = receipt.get("layers")
    if not isinstance(layers, dict):
        raise FinalAbError("prelayer receipt layers missing")
    if accepted_with_failures:
        allowed = {"PASS", "KNOWN_FAILURE", "HISTORICAL_PASS_NOT_RERUN"}
        invalid = [name for name in REQUIRED_PRELAYERS if layers.get(name) not in allowed]
        if invalid:
            raise FinalAbError(
                "known-failure prelayer receipt has invalid layer status: "
                + ", ".join(invalid)
            )
        if "KNOWN_FAILURE" not in layers.values():
            raise FinalAbError("known-failure prelayer receipt must name a failure")
        known_failures = receipt.get("known_failures")
        if not isinstance(known_failures, list) or not known_failures:
            raise FinalAbError("known-failure prelayer receipt needs known_failures")
    else:
        failed = [name for name in REQUIRED_PRELAYERS if layers.get(name) != "PASS"]
        if failed:
            raise FinalAbError("prelayer receipt does not pass: " + ", ".join(failed))
    evidence = receipt.get("evidence")
    if not isinstance(evidence, list):
        raise FinalAbError("prelayer receipt evidence must be a list")
    covered: set[str] = set()
    for row in evidence:
        if not isinstance(row, dict):
            raise FinalAbError("prelayer evidence entry must be an object")
        layer = row.get("layer")
        raw_path = row.get("path")
        expected_sha = row.get("sha256")
        if layer not in REQUIRED_PRELAYERS or layer in covered:
            raise FinalAbError(f"prelayer evidence layer invalid or duplicated: {layer!r}")
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise FinalAbError(f"prelayer evidence path must be absolute: {layer}")
        evidence_path = Path(raw_path)
        if not evidence_path.is_file():
            raise FinalAbError(f"prelayer evidence file missing: {evidence_path}")
        if not isinstance(expected_sha, str) or sha256_file(evidence_path) != expected_sha:
            raise FinalAbError(f"prelayer evidence hash mismatch: {layer}")
        covered.add(layer)
    missing_evidence = sorted(set(REQUIRED_PRELAYERS) - covered)
    if missing_evidence:
        raise FinalAbError("prelayer evidence missing: " + ", ".join(missing_evidence))
    return receipt


def codex_version(codex_bin: str) -> str:
    result = subprocess.run([codex_bin, "--version"], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FinalAbError(f"cannot run Codex CLI: {result.stderr.strip()}")
    return result.stdout.strip()


def freeze_repository() -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode or status.returncode:
        raise FinalAbError("repository must be a readable Git worktree")
    changed = [line[3:] for line in status.stdout.splitlines() if len(line) >= 4]
    return {
        "git_commit": head.stdout.strip(),
        "worktree_dirty": bool(changed),
        "changed_paths": changed,
    }


def pack_candidate(candidate_root: Path, destination: Path) -> tuple[Path, dict[str, Any]]:
    npm = shutil.which("npm")
    if npm is None:
        raise FinalAbError("npm not found; cannot freeze the candidate package")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="resanity-final-ab-npm-cache-") as cache:
        env = {**os.environ, "npm_config_cache": cache}
        result = subprocess.run(
            [npm, "pack", "--json", "--pack-destination", str(destination)],
            cwd=candidate_root,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    if result.returncode != 0:
        raise FinalAbError(f"npm pack failed: {(result.stderr or result.stdout).strip()[-2000:]}")
    try:
        payload = json.loads(result.stdout)
        row = payload[0]
        tarball = destination / row["filename"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise FinalAbError("npm pack returned unexpected JSON") from error
    if not tarball.is_file():
        raise FinalAbError("npm pack tarball missing")
    with tarfile.open(tarball, "r:gz") as archive:
        names = archive.getnames()
    leaked = [name for name in names if "__pycache__" in name or name.endswith(".pyc")]
    if leaked:
        raise FinalAbError("candidate tarball contains generated Python cache: " + ", ".join(leaked))
    return tarball, {
        "filename": tarball.name,
        "sha256": sha256_file(tarball),
        "file_count": len(names),
        "npm": row,
    }


def extract_candidate(tarball: Path, target: Path) -> None:
    if target.exists():
        raise FinalAbError(f"candidate target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:gz") as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if not path.parts or path.parts[0] != "package" or ".." in path.parts:
                raise FinalAbError(f"unsafe candidate archive member: {member.name}")
        archive.extractall(target.parent, filter="data")
    extracted = target.parent / "package"
    if extracted != target:
        extracted.rename(target)


def copy_auth(auth_source: Path, home: Path) -> None:
    if not auth_source.is_file():
        raise FinalAbError(f"Codex auth file missing: {auth_source}")
    home.mkdir(parents=True, exist_ok=True)
    target = home / "auth.json"
    shutil.copyfile(auth_source, target)
    target.chmod(stat.S_IRUSR | stat.S_IWUSR)


def shared_instruction(args: argparse.Namespace) -> str:
    return (
        f"统一运行日期为 {args.run_date.isoformat()}。任务内显式 as-of 优先；不得用其后的信息回填。\n"
        f"宿主预算上限：{args.max_non_cached_input_tokens} 非缓存输入 token、"
        f"{args.max_tool_calls} 次工具调用、{args.max_web_searches} 次 Web 搜索、"
        f"{args.max_wall_seconds} 秒。封闭任务禁止外部检索。失败动作不重试，不启动子代理。\n"
        "开放网络任务把每个最承重来源的快照保存到工作区 sources/；封闭任务不创建来源快照。\n"
        "最终消息只交付研究报告，不提及对照、评测、评分规则、运行计量或本指令。"
    )


def compose_prompt(arm_instruction: str, shared: str, task: str) -> str:
    return f"{arm_instruction.strip()}\n\n{shared.strip()}\n\n{task.strip()}\n"


def blind_id(seed: str, case_id: str, arm: str) -> str:
    return "arm-" + sha256_bytes(f"{seed}:{case_id}:{arm}".encode("utf-8"))[:12]


def parse_raw_metrics(raw: str) -> dict[str, Any]:
    session_id = "unknown"
    usage = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
    }
    tools: Counter[str] = Counter()
    retry_events = 0
    malformed = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        event_type = str(row.get("type", ""))
        if "retry" in event_type.lower():
            retry_events += 1
        if event_type == "thread.started" and isinstance(row.get("thread_id"), str):
            session_id = row["thread_id"]
        if event_type == "turn.completed" and isinstance(row.get("usage"), dict):
            usage = {key: int(row["usage"].get(key, 0) or 0) for key in usage}
        if event_type == "item.completed" and isinstance(row.get("item"), dict):
            item_type = str(row["item"].get("type", "unknown"))
            if item_type not in NON_TOOL_ITEM_TYPES:
                tools[item_type] += 1
    input_tokens = usage["input_tokens"]
    cached = usage["cached_input_tokens"]
    output_tokens = usage["output_tokens"]
    return {
        "session_id": session_id,
        "input_tokens": input_tokens,
        "cache_read_tokens": cached,
        "non_cached_input_tokens": max(0, input_tokens - cached),
        "output_tokens": output_tokens,
        "reasoning_tokens": usage["reasoning_output_tokens"],
        "tokens_total": input_tokens + output_tokens,
        "tool_calls": sum(tools.values()),
        "web_search": tools["web_search"],
        "tool_calls_by_name": dict(sorted(tools.items())),
        "host_retry_events": retry_events,
        "malformed_jsonl_lines": malformed,
    }


def identity_receipt(candidate_root: Path, active_skill: Path, workspace: Path, home: Path, profile: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            str(IDENTITY_CHECK),
            "--canonical-root",
            str(candidate_root),
            "--host",
            "codex",
            "--cwd",
            str(workspace),
            "--user-home",
            str(home.parent),
            "--profile",
            profile,
            "--active-skill",
            str(active_skill),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode != 0:
        raise FinalAbError(f"candidate identity check failed: {(result.stderr or result.stdout).strip()[-2000:]}")
    try:
        receipt = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise FinalAbError("candidate identity check did not return JSON") from error
    if receipt.get("ok") is not True or receipt.get("matches_canonical") != {"profile": True, "skill": True}:
        raise FinalAbError("candidate identity does not match canonical Skill/profile")
    return receipt


def baseline_absence_receipt(workspace: Path, home: Path) -> dict[str, Any]:
    candidates = [
        workspace / ".codex/skills/resanity/SKILL.md",
        home / "skills/resanity/SKILL.md",
    ]
    existing = [str(path) for path in candidates if path.exists()]
    if existing:
        raise FinalAbError("baseline contamination: " + ", ".join(existing))
    return {
        "schema_version": "resanity.baseline-skill-absence.v1",
        "status": "PASS",
        "candidate_skill_present": False,
        "checked": [str(path) for path in candidates],
    }


def copy_sources(workspace: Path, artifact_dir: Path, review_dir: Path) -> int:
    source = workspace / "sources"
    artifact_target = artifact_dir / "sources"
    review_target = review_dir / "sources"
    artifact_target.mkdir(parents=True, exist_ok=True)
    review_target.mkdir(parents=True, exist_ok=True)
    if not source.is_dir():
        return 0
    count = 0
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        for target_root in (artifact_target, review_target):
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        count += 1
    return count


def run_one(
    *,
    args: argparse.Namespace,
    case: dict[str, Any],
    arm: str,
    arm_instruction: str,
    shared: str,
    home: Path,
    tarball: Path,
    output: Path,
    seed: str,
) -> dict[str, Any]:
    case_id = case["id"]
    opaque = blind_id(seed, case_id, arm)
    operator_dir = output / "operator/cases" / case_id / arm
    review_dir = output / "review/cases" / case_id / opaque
    workspace = output / "operator/workspaces" / case_id / arm
    operator_dir.mkdir(parents=True, exist_ok=False)
    review_dir.mkdir(parents=True, exist_ok=False)
    workspace.mkdir(parents=True, exist_ok=False)
    (workspace / "sources").mkdir()

    task = case["prompt_path"].read_text(encoding="utf-8")
    composed = compose_prompt(arm_instruction, shared, task)
    (workspace / "task-prompt.md").write_text(task, encoding="utf-8")
    (operator_dir / "task-prompt.md").write_text(task, encoding="utf-8")
    (operator_dir / "arm-instruction.md").write_text(arm_instruction, encoding="utf-8")
    (operator_dir / "shared-run-instruction.md").write_text(shared + "\n", encoding="utf-8")
    (operator_dir / "composed-prompt.md").write_text(composed, encoding="utf-8")

    if arm == "candidate":
        active_root = workspace / ".codex/skills/resanity"
        active_root.parent.mkdir(parents=True, exist_ok=True)
        extract_candidate(tarball, active_root)
        identity = identity_receipt(
            args.candidate_root,
            active_root / "SKILL.md",
            workspace,
            home,
            case["profile"],
        )
    else:
        identity = baseline_absence_receipt(workspace, home)
    write_json(operator_dir / "skill-identity.json", identity)

    command = [
        args.codex_bin,
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--model",
        args.model,
        "--sandbox",
        args.sandbox,
        "-c",
        f'model_reasoning_effort="{args.reasoning_effort}"',
        "-c",
        'approval_policy="never"',
        "--cd",
        str(workspace),
        "--output-last-message",
        str(workspace / "report.md"),
        "-",
    ]
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(home)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for secret_name in ("TUSHARE_TOKEN", "RESANITY_CREDENTIALS"):
        environment.pop(secret_name, None)
    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            command,
            input=composed,
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
            timeout=args.max_wall_seconds,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        exit_code = 124
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        stderr += f"\nrunner timeout after {args.max_wall_seconds}s\n"
    wall_seconds = round(time.monotonic() - started, 3)
    raw_path = operator_dir / "raw.jsonl"
    raw_path.write_text(stdout, encoding="utf-8")
    (operator_dir / "stderr.log").write_text(stderr, encoding="utf-8")
    (operator_dir / "exit-code").write_text(f"{exit_code}\n", encoding="utf-8")

    metrics = parse_raw_metrics(stdout)
    metrics["wall_seconds"] = wall_seconds
    report_source = workspace / "report.md"
    if report_source.is_file():
        shutil.copy2(report_source, operator_dir / "report.md")
        shutil.copy2(report_source, review_dir / "report.md")
    sources = copy_sources(workspace, operator_dir, review_dir)
    host_receipt = {
        "schema_version": "resanity.host-receipt.v1",
        "host": "codex-cli",
        "provider": args.provider,
        "model": args.model,
        "session_id": metrics["session_id"],
        "runtime": {
            "input_tokens": metrics["input_tokens"],
            "output_tokens": metrics["output_tokens"],
            "reasoning_tokens": metrics["reasoning_tokens"],
            "cache_read_tokens": metrics["cache_read_tokens"],
            "non_cached_input_tokens": metrics["non_cached_input_tokens"],
            "tokens_total": metrics["tokens_total"],
            "tool_calls": metrics["tool_calls"],
            "wall_seconds": wall_seconds,
        },
        "budget_usage": {
            "tokens_total": metrics["tokens_total"],
            "tool_calls": metrics["tool_calls"],
            "web_search": metrics["web_search"],
            "wall_seconds": wall_seconds,
        },
        "tool_calls_by_name": metrics["tool_calls_by_name"],
        "raw_session": {"path": "raw.jsonl", "sha256": sha256_file(raw_path)},
        "runner": {
            "automatic_retries": 0,
            "host_retry_events": metrics["host_retry_events"],
            "malformed_jsonl_lines": metrics["malformed_jsonl_lines"],
            "timed_out": timed_out,
        },
    }
    write_json(operator_dir / "host-receipt.json", host_receipt)

    budget_failures = []
    if metrics["non_cached_input_tokens"] > args.max_non_cached_input_tokens:
        budget_failures.append("non_cached_input_tokens")
    if metrics["tool_calls"] > args.max_tool_calls:
        budget_failures.append("tool_calls")
    if metrics["web_search"] > args.max_web_searches:
        budget_failures.append("web_search")
    if wall_seconds > args.max_wall_seconds:
        budget_failures.append("wall_seconds")
    if metrics["host_retry_events"]:
        budget_failures.append("host_retry_events")
    report_present = report_source.is_file() and report_source.stat().st_size > 0
    artifact_complete = exit_code == 0 and report_present and not budget_failures
    if case["mode"] == "open" and sources == 0:
        artifact_complete = False
        budget_failures.append("open_case_source_snapshots_missing")
    result_summary = {
        "case_id": case_id,
        "arm": arm,
        "blind_id": opaque,
        "exit_code": exit_code,
        "artifact_complete": artifact_complete,
        "report_present": report_present,
        "source_files": sources,
        "mechanical_failures": budget_failures,
        "host_receipt": str((operator_dir / "host-receipt.json").relative_to(output)),
    }
    write_json(operator_dir / "collection-result.json", result_summary)
    return result_summary


def parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("must be canonical YYYY-MM-DD")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="launch 16 paid model sessions; default is dry-run")
    parser.add_argument("--output", type=Path, help="new output directory; required with --run")
    parser.add_argument("--candidate-root", type=Path, default=ROOT)
    parser.add_argument("--expected-skill-sha256", help="frozen canonical SKILL.md SHA-256")
    parser.add_argument("--prelayers-receipt", type=Path, help="same-hash PRELAYERS_PASS receipt")
    parser.add_argument("--codex-bin", default=shutil.which("codex") or "codex")
    parser.add_argument("--auth-source", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json")
    parser.add_argument("--provider", default="openai", help="exact provider identifier for host receipts")
    parser.add_argument("--model", required=True, help="exact Codex model identifier shared by both arms")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--sandbox", choices=("read-only", "workspace-write"), default="workspace-write")
    parser.add_argument("--run-date", type=parse_date, default=date.today())
    parser.add_argument("--seed", help="recorded arm-order/blinding seed; random when omitted")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-non-cached-input-tokens", type=int, default=150_000)
    parser.add_argument("--max-tool-calls", type=int, default=30)
    parser.add_argument("--max-web-searches", type=int, default=15)
    parser.add_argument("--max-wall-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    args.candidate_root = args.candidate_root.resolve()
    if args.output is not None:
        args.output = args.output.resolve()
    if args.run and args.output is None:
        parser.error("--output is required with --run")
    if args.run and args.output is not None:
        try:
            args.output.relative_to(ROOT)
        except ValueError:
            pass
        else:
            parser.error("--output must be outside the source repository for arm isolation")
    for name in (
        "concurrency",
        "max_non_cached_input_tokens",
        "max_tool_calls",
        "max_web_searches",
        "max_wall_seconds",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if args.concurrency > 4:
        parser.error("--concurrency must be at most 4")
    return args


def dry_run_receipt(
    args: argparse.Namespace,
    plan: list[dict[str, Any]],
    skill_sha: str,
    profiles_sha: dict[str, str],
    prelayers: dict[str, Any] | None,
    version: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "DRY_RUN_READY" if prelayers is not None and args.expected_skill_sha256 else "DRY_RUN_BLOCKED",
        "method_status": "UNBENCHMARKED_CURRENT",
        "semantic_scoring": "NOT_RUN",
        "candidate_skill_sha256": skill_sha,
        "candidate_profiles_sha256": profiles_sha,
        "expected_skill_sha256_supplied": args.expected_skill_sha256 is not None,
        "prelayers_receipt": "PASS" if prelayers is not None else "NOT_SUPPLIED",
        "host": {"adapter": "codex-cli", "version": version, "provider": args.provider, "model": args.model},
        "session_count": 16,
        "automatic_retries": 0,
        "cases": [
            {
                "id": row["id"],
                "profile": row["profile"],
                "mode": row["mode"],
                "task_prompt_sha256": row["task_prompt_sha256"],
                "arms": list(ARMS),
            }
            for row in plan
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_source_contract()
    suite = load_suite()
    plan = final_ab_plan(suite)
    skill_sha = validate_expected_skill(
        args.candidate_root,
        args.expected_skill_sha256,
        required=args.run,
    )
    profiles_sha = profile_hashes(args.candidate_root)
    prelayers = validate_prelayers(
        args.prelayers_receipt,
        skill_sha,
        profiles_sha,
        required=args.run,
    )
    version = codex_version(args.codex_bin)
    if not args.run:
        print(
            canonical_json(
                dry_run_receipt(args, plan, skill_sha, profiles_sha, prelayers, version)
            ),
            end="",
        )
        return 0

    assert args.output is not None
    if args.output.exists():
        raise FinalAbError(f"output already exists; refusing overwrite: {args.output}")
    args.output.mkdir(parents=True)
    seed = args.seed or os.urandom(16).hex()
    repository = freeze_repository()
    shared = shared_instruction(args)
    final_ab = suite["layers"]["final_ab"]
    arm_instructions = {
        "baseline": (SUITE_PATH.parent / final_ab["baseline_prompt"]).read_text(encoding="utf-8"),
        "candidate": (SUITE_PATH.parent / final_ab["candidate_prompt"]).read_text(encoding="utf-8"),
    }
    with tempfile.TemporaryDirectory(prefix="resanity-final-ab-runtime-") as runtime_raw:
        runtime = Path(runtime_raw)
        homes = {
            (case["id"], arm): runtime / "homes" / case["id"] / arm
            for case in plan
            for arm in ARMS
        }
        for home in homes.values():
            copy_auth(args.auth_source.resolve(), home)
        tarball, package = pack_candidate(args.candidate_root, runtime / "package")
        with tarfile.open(tarball, "r:gz") as archive:
            skill_member = archive.extractfile("package/SKILL.md")
            if skill_member is None or sha256_bytes(skill_member.read()) != skill_sha:
                raise FinalAbError("packed candidate SKILL.md does not match frozen source hash")

        jobs = [(case, arm) for case in plan for arm in ARMS]
        random.Random(seed).shuffle(jobs)
        arm_map = {
            case["id"]: {blind_id(seed, case["id"], arm): arm for arm in ARMS}
            for case in plan
        }
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "RUNNING",
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "method_status": "UNBENCHMARKED_CURRENT",
            "semantic_scoring": "NOT_RUN",
            "repository": repository,
            "candidate_skill_sha256": skill_sha,
            "candidate_profiles_sha256": profiles_sha,
            "candidate_package": package,
            "prelayers_receipt_sha256": sha256_file(args.prelayers_receipt.resolve()),
            "host": {
                "adapter": "codex-cli",
                "version": version,
                "provider": args.provider,
                "model": args.model,
                "reasoning_effort": args.reasoning_effort,
                "sandbox": args.sandbox,
                "approval_policy": "never",
            },
            "budgets_per_arm": {
                "non_cached_input_tokens": args.max_non_cached_input_tokens,
                "tool_calls": args.max_tool_calls,
                "web_search": args.max_web_searches,
                "wall_seconds": args.max_wall_seconds,
            },
            "run_date": args.run_date.isoformat(),
            "seed": seed,
            "concurrency": args.concurrency,
            "automatic_retries": 0,
            "session_count": len(jobs),
            "job_order": [{"case_id": case["id"], "blind_id": blind_id(seed, case["id"], arm)} for case, arm in jobs],
        }
        write_json(args.output / "operator/run-manifest.json", manifest)
        write_json(args.output / "operator/arm-map.json", arm_map)
        write_json(
            args.output / "review/review-manifest.json",
            {
                "schema_version": "resanity.final-ab-blind-review.v1",
                "candidate_skill_sha256": skill_sha,
                "case_ids": [case["id"] for case in plan],
                "blind_arms": {case["id"]: sorted(arm_map[case["id"]]) for case in plan},
                "instructions": "Review reports and source snapshots without opening operator/arm-map.json; establish the fact index before scoring load-bearing claims.",
            },
        )

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = {
                executor.submit(
                    run_one,
                    args=args,
                    case=case,
                    arm=arm,
                    arm_instruction=arm_instructions[arm],
                    shared=shared,
                    home=homes[(case["id"], arm)],
                    tarball=tarball,
                    output=args.output,
                    seed=seed,
                ): (case, arm)
                for case, arm in jobs
            }
            for future in concurrent.futures.as_completed(futures):
                case, arm = futures[future]
                try:
                    results.append(future.result())
                except Exception as error:  # preserve one-shot failure; never retry
                    results.append(
                        {
                            "case_id": case["id"],
                            "arm": arm,
                            "blind_id": blind_id(seed, case["id"], arm),
                            "exit_code": None,
                            "artifact_complete": False,
                            "report_present": False,
                            "source_files": 0,
                            "mechanical_failures": [f"runner_error:{type(error).__name__}"],
                            "runner_error": str(error),
                        }
                    )

    results.sort(key=lambda row: (row["case_id"], row["arm"]))
    complete = [row for row in results if row["artifact_complete"]]
    status = "COLLECTION_COMPLETE_AWAITING_BLIND_REVIEW" if len(complete) == 16 else "COLLECTION_INCOMPLETE"
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "method_status": "UNBENCHMARKED_CURRENT",
        "semantic_scoring": "NOT_RUN",
        "automatic_retries": 0,
        "candidate_skill_sha256": skill_sha,
        "candidate_profiles_sha256": profiles_sha,
        "completed_artifacts": len(complete),
        "expected_artifacts": 16,
        "results": results,
        "next_step": "independent blind human review; do not infer a winner from collection status",
    }
    write_json(args.output / "collection-summary.json", summary)
    print(canonical_json(summary), end="")
    return 0 if status == "COLLECTION_COMPLETE_AWAITING_BLIND_REVIEW" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FinalAbError as error:
        print(f"FINAL_AB_BLOCKED: {error}", file=sys.stderr)
        raise SystemExit(2)
