#!/usr/bin/env python3
"""Collect the eight-case paired Resanity v2 A/B through DSH headless.

Dry-run is the default. A real run requires two already-prepared, equivalent
DSH profiles: the baseline profile must not contain Resanity; the candidate
profile may differ only by the Resanity dependency/config entry. The runner
does not install or edit either profile. It launches every arm once, disables
host retries and subagents with a per-session patch, preserves raw DSH
sessions, and prepares a blinded review tree without scoring semantics.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BASE_RUNNER_PATH = ROOT / "validation/v2/run_final_ab.py"
_BASE_SPEC = importlib.util.spec_from_file_location("resanity_final_ab_base", BASE_RUNNER_PATH)
if _BASE_SPEC is None or _BASE_SPEC.loader is None:
    raise RuntimeError("cannot load shared final A/B runner")
BASE = importlib.util.module_from_spec(_BASE_SPEC)
_BASE_SPEC.loader.exec_module(BASE)

FinalAbError = BASE.FinalAbError
ARMS = BASE.ARMS
SCHEMA_VERSION = "resanity.final-ab-dsh-collection.v1"
BUDGET_GUARD_PACKAGE = "resanity-validation-budget"
BUDGET_GUARD_TOOL_REASON = "RESANITY_VALIDATION_BUDGET_TOOL_LIMIT"
BUDGET_GUARD_WEB_REASON = "RESANITY_VALIDATION_BUDGET_WEB_LIMIT"
TOP_LEVEL_ID = re.compile(r"^- id:\s*['\"]?([^'\"\s]+)['\"]?\s*$")
DISABLED_RUNTIME_PLUGINS = (
    "llm-retry",
    "subagent",
    "subagent-spawn-in-process",
    "subagent-fork-in-process",
    "tool-subagent-control",
    "tool-subagent-list-agents",
    "tool-subagent",
    "tool-subagent-fork",
    "tool-subagent-report",
    "workflow-worker-thread",
    "tool-workflow",
    "tool-ralph",
)
WATCH_DISABLED_RUNTIME_PLUGINS = (
    "settings",
    "credentials",
    "skill-filesystem",
)
WATCH_ENVIRONMENT = {
    "CHOKIDAR_USEPOLLING": "1",
    "CHOKIDAR_INTERVAL": "250",
}


def dsh_version(dsh_bin: str) -> str:
    result = subprocess.run(
        [dsh_bin, "--version"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise FinalAbError(f"cannot run DSH: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def zstd_version(zstd_bin: str) -> str:
    result = subprocess.run(
        [zstd_bin, "--version"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise FinalAbError(f"cannot run zstd: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def read_profile_package(dsh_home: Path, profile: str) -> tuple[Path, dict[str, Any]]:
    profile_root = (dsh_home / "profiles" / profile).resolve()
    package_path = profile_root / "package.json"
    if not package_path.is_file():
        raise FinalAbError(f"DSH profile package missing: {package_path}")
    package = BASE.load_json(package_path)
    if not isinstance(package, dict):
        raise FinalAbError(f"DSH profile package root must be an object: {package_path}")
    return profile_root, package


def profile_bundles(package: dict[str, Any], profile: str) -> list[str]:
    dsh = package.get("dsh")
    profile_config = dsh.get("profile") if isinstance(dsh, dict) else None
    bundles = profile_config.get("bundles") if isinstance(profile_config, dict) else None
    if not isinstance(bundles, list) or any(not isinstance(item, str) for item in bundles):
        raise FinalAbError(f"DSH profile bundles invalid: {profile}")
    return bundles


def profile_dependencies(package: dict[str, Any], profile: str) -> dict[str, str]:
    dependencies = package.get("dependencies", {})
    if not isinstance(dependencies, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in dependencies.items()
    ):
        raise FinalAbError(f"DSH profile dependencies invalid: {profile}")
    return dependencies


def dump_config(
    dsh_bin: str, dsh_home: Path, profile: str, patch: Path | None = None
) -> str:
    environment = os.environ.copy()
    environment["DSH_HOME"] = str(dsh_home)
    environment["DSH_TELEMETRY_MODE"] = "DISABLED"
    command = [dsh_bin, "--profile", profile]
    if patch is not None:
        command.extend(["--patch", str(patch)])
    command.append("--dump-config")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise FinalAbError(f"cannot dump DSH profile {profile}: {detail[-2000:]}")
    return result.stdout


def top_level_ids(config: str) -> list[str]:
    ids = []
    for line in config.splitlines():
        match = TOP_LEVEL_ID.fullmatch(line)
        if match:
            ids.append(match.group(1))
    return ids


def remove_top_level_entry(config: str, plugin_id: str) -> str:
    """Remove exactly one top-level Cordis entry by id, preserving all others."""
    lines = config.splitlines()
    starts = []
    for index, line in enumerate(lines):
        match = TOP_LEVEL_ID.fullmatch(line)
        if match and match.group(1) == plugin_id:
            starts.append(index)
    if len(starts) != 1:
        raise FinalAbError(
            f"candidate dump must contain exactly one top-level {plugin_id!r} entry"
        )
    entry_start = starts[0]
    start = entry_start
    # DSH annotates a user-layer entry with a source comment that exists only
    # in the candidate dump. It belongs to the removed treatment entry too.
    while start > 0 and lines[start - 1].startswith("# =="):
        start -= 1
    end = len(lines)
    for index in range(entry_start + 1, len(lines)):
        if TOP_LEVEL_ID.fullmatch(lines[index]):
            end = index
            break
    return "\n".join(lines[:start] + lines[end:]).strip() + "\n"


def profile_pair_receipt(args: argparse.Namespace, skill_sha: str) -> dict[str, Any]:
    if args.baseline_profile == args.candidate_profile:
        raise FinalAbError("baseline and candidate DSH profiles must be distinct")
    baseline_root, baseline_package = read_profile_package(
        args.dsh_home, args.baseline_profile
    )
    candidate_root, candidate_package = read_profile_package(
        args.dsh_home, args.candidate_profile
    )
    baseline_bundles = profile_bundles(baseline_package, args.baseline_profile)
    candidate_bundles = profile_bundles(candidate_package, args.candidate_profile)
    if candidate_bundles != [*baseline_bundles, "resanity"]:
        raise FinalAbError(
            "candidate DSH profile bundles must equal baseline bundles plus final resanity"
        )

    baseline_dependencies = profile_dependencies(
        baseline_package, args.baseline_profile
    )
    candidate_dependencies = profile_dependencies(
        candidate_package, args.candidate_profile
    )
    if "resanity" in baseline_dependencies:
        raise FinalAbError("baseline DSH profile contains a Resanity dependency")
    baseline_without = dict(sorted(baseline_dependencies.items()))
    candidate_without = dict(sorted(candidate_dependencies.items()))
    candidate_resanity_spec = candidate_without.pop("resanity", None)
    if candidate_resanity_spec is None:
        raise FinalAbError("candidate DSH profile has no Resanity dependency")
    if baseline_without != candidate_without:
        raise FinalAbError("DSH profile dependency sets differ beyond Resanity")
    guard_spec = baseline_without.get(BUDGET_GUARD_PACKAGE)
    if guard_spec is None:
        raise FinalAbError(
            f"both DSH profiles must install shared {BUDGET_GUARD_PACKAGE}"
        )

    active_skill = args.active_skill.resolve()
    try:
        active_skill.relative_to(candidate_root)
    except ValueError as error:
        raise FinalAbError(
            "--active-skill must resolve inside the candidate DSH profile"
        ) from error
    if not active_skill.is_file():
        raise FinalAbError(f"active DSH Skill missing: {active_skill}")
    if BASE.sha256_file(active_skill) != skill_sha:
        raise FinalAbError("active DSH Skill hash does not match the frozen canonical Skill")
    baseline_skill = baseline_root / "node_modules/resanity/SKILL.md"
    if baseline_skill.exists():
        raise FinalAbError(f"baseline DSH profile is contaminated: {baseline_skill}")
    dsh_user_skill = args.dsh_home / "skills/resanity/SKILL.md"
    if dsh_user_skill.exists():
        raise FinalAbError(
            f"shared DSH_HOME user Skill would contaminate both arms: {dsh_user_skill}"
        )

    baseline_dump = dump_config(args.dsh_bin, args.dsh_home, args.baseline_profile)
    candidate_dump = dump_config(args.dsh_bin, args.dsh_home, args.candidate_profile)
    if "resanity" in top_level_ids(baseline_dump):
        raise FinalAbError("baseline DSH config activates Resanity")
    if top_level_ids(candidate_dump).count("resanity") != 1:
        raise FinalAbError("candidate DSH config must activate Resanity exactly once")
    normalized_candidate = remove_top_level_entry(candidate_dump, "resanity")
    if baseline_dump.strip() != normalized_candidate.strip():
        raise FinalAbError(
            "DSH dump-config differs beyond the single Resanity entry; clone one "
            "headless profile, then add only Resanity to the candidate"
        )

    identities = {}
    for profile in ("core", "investing"):
        result = subprocess.run(
            [
                sys.executable,
                str(BASE.IDENTITY_CHECK),
                "--canonical-root",
                str(args.candidate_root),
                "--host",
                "dsh",
                "--cwd",
                str(ROOT),
                "--user-home",
                str(args.isolated_user_home),
                "--dsh-home",
                str(args.dsh_home),
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
            detail = result.stderr.strip() or result.stdout.strip()
            raise FinalAbError(f"DSH active Skill identity failed for {profile}: {detail[-2000:]}")
        identity = json.loads(result.stdout)
        if identity.get("matches_canonical") != {"profile": True, "skill": True}:
            raise FinalAbError(f"DSH active {profile} profile does not match canonical")
        identities[profile] = identity

    return {
        "schema_version": "resanity.dsh-profile-pair.v1",
        "status": "PASS",
        "dsh_home": str(args.dsh_home),
        "baseline_profile": {
            "name": args.baseline_profile,
            "root": str(baseline_root),
            "package_json_sha256": BASE.sha256_file(baseline_root / "package.json"),
            "dump_config_sha256": BASE.sha256_bytes(baseline_dump.encode("utf-8")),
            "resanity_dependency": False,
            "resanity_active": False,
        },
        "candidate_profile": {
            "name": args.candidate_profile,
            "root": str(candidate_root),
            "package_json_sha256": BASE.sha256_file(candidate_root / "package.json"),
            "dump_config_sha256": BASE.sha256_bytes(candidate_dump.encode("utf-8")),
            "normalized_dump_config_sha256": BASE.sha256_bytes(
                normalized_candidate.encode("utf-8")
            ),
            "resanity_dependency": candidate_resanity_spec,
            "active_skill": str(active_skill),
            "active_skill_sha256": skill_sha,
        },
        "shared_bundles": baseline_bundles,
        "treatment_bundle": "resanity",
        "shared_dependencies": baseline_without,
        "budget_guard": {
            "package": BUDGET_GUARD_PACKAGE,
            "dependency": guard_spec,
        },
        "canonical_identities": identities,
    }


def shared_instruction(args: argparse.Namespace) -> str:
    return (
        f"统一运行日期为 {args.run_date.isoformat()}。任务内显式 as-of 优先；不得用其后的信息回填。\n"
        f"宿主预算上限：{args.max_non_cached_input_tokens} 非缓存输入 token、"
        f"{args.max_tool_calls} 次工具调用、{args.max_web_searches} 次 Web 搜索、"
        f"{args.max_wall_seconds} 秒。封闭任务禁止外部检索。失败动作不重试，不启动子代理。\n"
        "开放网络任务把每个最承重来源的快照保存到工作区 sources/；封闭任务不创建来源快照。\n"
        "最终消息只交付研究报告，不提及对照、评测、评分规则、运行计量或本指令。"
    )


def session_patch(
    session_root: Path, max_tool_calls: int = 30, max_web_searches: int = 15
) -> str:
    patch = (
        "- id: session-persistence-jsonl\n"
        "  config:\n"
        f"    root: {json.dumps(str(session_root))}\n"
        f"- id: {BUDGET_GUARD_PACKAGE}\n"
        "  config:\n"
        f"    maxToolCalls: {max_tool_calls}\n"
        f"    maxWebSearches: {max_web_searches}\n"
    )
    patch += "".join(
        f"- id: {plugin_id}\n  disabled: true\n"
        for plugin_id in DISABLED_RUNTIME_PLUGINS
    )
    return patch + "".join(
        f"- id: {plugin_id}\n  config:\n    watch: false\n"
        for plugin_id in WATCH_DISABLED_RUNTIME_PLUGINS
    )


def validate_runtime_patch(args: argparse.Namespace) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="resanity-dsh-ab-patch-") as raw:
        root = Path(raw)
        patch_path = root / "session.patch.yml"
        patch_path.write_text(
            session_patch(
                root / "sessions", args.max_tool_calls, args.max_web_searches
            ),
            encoding="utf-8",
        )
        dumps = {}
        for profile in (args.baseline_profile, args.candidate_profile):
            config = dump_config(args.dsh_bin, args.dsh_home, profile, patch_path)
            required = (
                "id: session-persistence-jsonl",
                f"id: {BUDGET_GUARD_PACKAGE}",
                f"name: {BUDGET_GUARD_PACKAGE}",
                f"maxToolCalls: {args.max_tool_calls}",
                f"maxWebSearches: {args.max_web_searches}",
            ) + tuple(
                f"id: {plugin_id}" for plugin_id in DISABLED_RUNTIME_PLUGINS
            ) + tuple(
                f"id: {plugin_id}" for plugin_id in WATCH_DISABLED_RUNTIME_PLUGINS
            )
            missing = [marker for marker in required if marker not in config]
            if missing:
                raise FinalAbError(
                    f"DSH runtime patch did not compose for {profile}: {', '.join(missing)}"
                )
            for plugin_id in DISABLED_RUNTIME_PLUGINS:
                block = re.search(
                    rf"(?ms)^- id:\s*{re.escape(plugin_id)}\s*$.*?(?=^- id:|\Z)",
                    config,
                )
                if block is None or "disabled: true" not in block.group(0):
                    raise FinalAbError(
                        f"DSH runtime patch did not disable {plugin_id} in {profile}"
                    )
            for plugin_id in WATCH_DISABLED_RUNTIME_PLUGINS:
                block = re.search(
                    rf"(?ms)^- id:\s*{re.escape(plugin_id)}\s*$.*?(?=^- id:|\Z)",
                    config,
                )
                if block is None or "watch: false" not in block.group(0):
                    raise FinalAbError(
                        f"DSH runtime patch did not disable {plugin_id} watcher in {profile}"
                    )
            dumps[profile] = BASE.sha256_bytes(config.encode("utf-8"))
    return {
        "schema_version": "resanity.dsh-runtime-patch.v5",
        "status": "PASS",
        "automatic_retries": 0,
        "subagents": "DISABLED",
        "budget_guard": {
            "package": BUDGET_GUARD_PACKAGE,
            "max_tool_calls": args.max_tool_calls,
            "max_web_searches": args.max_web_searches,
            "mode": "pre-execution hard deny plus next-step tool removal",
        },
        "disabled_plugins": list(DISABLED_RUNTIME_PLUGINS),
        "watch_disabled_plugins": list(WATCH_DISABLED_RUNTIME_PLUGINS),
        "watch_environment": WATCH_ENVIRONMENT,
        "composed_dump_sha256": dumps,
    }


def read_dsh_events(path: Path, zstd_bin: str) -> list[dict[str, Any]]:
    process = subprocess.Popen(
        [zstd_bin, "-dc", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.stdout is None:
        raise FinalAbError("zstd stdout pipe was not created")
    events = []
    malformed = 0
    try:
        for raw_line in process.stdout:
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(event, dict):
                events.append(event)
            else:
                malformed += 1
    finally:
        process.stdout.close()
    stderr = process.stderr.read() if process.stderr is not None else ""
    if process.wait() != 0:
        raise FinalAbError(f"zstd failed: {stderr.strip()}")
    if malformed:
        events.append({"type": "runner/malformed-lines", "data": {"count": malformed}})
    return events


def skill_names(events: list[dict[str, Any]]) -> list[str]:
    names = []
    for event in events:
        if event.get("type") != "tool/call":
            continue
        data = event.get("data")
        if not isinstance(data, dict) or data.get("name") != "skill":
            continue
        arguments = data.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                continue
        if isinstance(arguments, dict) and isinstance(arguments.get("name"), str):
            names.append(arguments["name"])
    return names


def integer(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


TOOL_PROTOCOL_MARKERS = (
    "<｜｜DSML｜｜tool_calls>",
    "<｜｜DSML｜｜invoke",
    "<|tool_calls|>",
    "<|invoke",
)
PROCESS_ONLY_MARKERS = (
    "Budget check:",
    "active-research cap",
    "remaining call",
    "required deliverable write",
    "budget limit",
    "write failed",
    "预算已接近上限",
    "不再重试",
)
REPORT_CONTENT_MARKERS = ("#", "[C", "根结论", "一句话结论", "主张：")
BOUNDARY_TOKENS = (
    "FACT",
    "SINGLE_SOURCE",
    "INFERENCE",
    "HYPOTHESIS",
    "NO_RESULT",
    "INSUFFICIENT",
)
TEMPORAL_TOKENS = (
    "EVENT_BY_DATE",
    "STATE_AT_AS_OF",
    "ABSENCE_BY_AS_OF",
    "TIMELESS",
)
REALITY_NEGATIONS = (
    "不成立",
    "未形成",
    "不存在",
    "没有项目",
    "闭环未闭",
    "为空",
    "尚无收入",
)
CLAIM_START = re.compile(
    r"^\s*(?:#{2,6}\s*)?(?:\[?C\d+\]?|主张(?:卡)?\s*\[?C?\d+\]?)\s*(?:[：:｜|—-].*)?$",
    re.IGNORECASE,
)
INLINE_CLAIM_START = re.compile(
    r"^\s*\*{0,2}主张\s*C?\d+\s*(?:[（(](?:EVENT_BY_DATE|STATE_AT_AS_OF|ABSENCE_BY_AS_OF|TIMELESS)[）)])?\*{0,2}\s*[：:].+$",
    re.IGNORECASE,
)
EXIT_CODE = re.compile(r"\[exit code:\s*(-?\d+)\]", re.IGNORECASE)


def report_delivery_failures(report: str) -> list[str]:
    """Check delivery shape without interpreting research semantics."""
    if not report.strip():
        return ["report_missing"]
    if any(marker in report for marker in TOOL_PROTOCOL_MARKERS):
        return ["report_tool_protocol_leak"]
    process_markers = sum(marker in report for marker in PROCESS_ONLY_MARKERS)
    if (
        len(report) < 1000
        and process_markers >= 2
        and not any(marker in report for marker in REPORT_CONTENT_MARKERS)
    ):
        return ["report_process_only"]
    return []


def markdown_section(report: str, title_pattern: str) -> str:
    """Return one Markdown section body, or a labeled inline block."""
    lines = report.splitlines()
    heading = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
    wanted = re.compile(title_pattern, re.IGNORECASE)
    for index, line in enumerate(lines):
        match = heading.match(line)
        if not match or not wanted.search(match.group(2)):
            continue
        end = len(lines)
        for candidate in range(index + 1, len(lines)):
            next_heading = heading.match(lines[candidate])
            if next_heading:
                end = candidate
                break
        return "\n".join(lines[index + 1 : end]).strip()
    inline = re.search(
        rf"(?ms)^\s*{title_pattern}\s*[：:]\s*(.+?)(?=^\s*(?:主张|唯一.*下一)|\Z)",
        report,
    )
    return inline.group(1).strip() if inline else ""


def claim_blocks(report: str) -> list[str]:
    lines = report.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if CLAIM_START.match(line) or INLINE_CLAIM_START.match(line)
    ]
    return [
        "\n".join(lines[start : starts[offset + 1] if offset + 1 < len(starts) else len(lines)])
        for offset, start in enumerate(starts)
    ]


def one_next_evidence_object(section: str) -> bool:
    if not section.strip():
        return False
    object_families = (
        r"年报|年度报告|半年报|半年度报告|季报|季度报告",
        r"公告索引|披露索引|公告清单|披露清单",
        r"备案文件|备案清单|项目备案",
        r"合同(?:原件)?",
        r"发票",
        r"结算单|电费账单",
        r"验收(?:文件|报告|单|证明)",
        r"绿证(?:注销|交易)?记录",
        r"物理直连(?:批复|协议)",
        r"访谈(?:记录)?",
        r"客户确认",
        r"收入明细|项目台账",
    )
    actions = list(re.finditer(r"获取|读取|调取|索取|下载|查阅|申请|拿到", section))
    if len(actions) != 1:
        return False
    acquired = re.split(r"，?用它|，?以此|，?用于|，?来核验|，?核验|，?裁决", section[actions[0].end() :], maxsplit=1)[0]
    matches = []
    for pattern in object_families:
        match = re.search(pattern, acquired)
        if match:
            matches.append(match)
    if not matches:
        return False
    matches.sort(key=lambda match: match.start())
    if len(matches) == 1:
        return True
    between = acquired[matches[0].end() : matches[-1].start()]
    nested = re.search(r"中(?:的|所列|披露)|内(?:的|所列|披露)|所附", between)
    separate = re.search(r"、|以及|和|及|与|另|同时", between)
    return bool(nested) and not separate


def delivery_contract_failures(
    report: str,
    contract: dict[str, Any],
    *,
    saved_report: bool = False,
) -> list[str]:
    """Execute the natural-delivery regression contract against a real report."""
    failures: list[str] = []
    if contract.get("report_required"):
        failures.extend(report_delivery_failures(report))
    if contract.get("saved_report_required") and not saved_report:
        failures.append("delivery_saved_report_missing")
    if not report.strip():
        return list(dict.fromkeys(failures))

    if contract.get("root_uses_evidence_language"):
        root = markdown_section(report, r"根结论|一句话结论")
        required = ("公开证据支持", "尚未闭合", "现实中", "未知", "NOT_EVALUABLE")
        if not root or any(token not in root for token in required):
            failures.append("delivery_root_evidence_language")
        if any(token in root for token in REALITY_NEGATIONS):
            failures.append("delivery_root_reality_negation")

    blocks = claim_blocks(report)
    if (contract.get("one_boundary_per_claim") or contract.get("temporal_mode_per_claim")) and not 1 <= len(blocks) <= 5:
        failures.append("delivery_claim_cards_missing")
    for number, block in enumerate(blocks, start=1):
        if contract.get("one_boundary_per_claim"):
            boundary_lines = [
                line for line in block.splitlines() if re.search(r"证据边界\s*[（(]", line) or re.search(r"证据边界\s*[：:]", line)
            ]
            tokens = re.findall(r"\b(?:" + "|".join(BOUNDARY_TOKENS) + r")\b", "\n".join(boundary_lines))
            if len(boundary_lines) != 1 or len(tokens) != 1:
                failures.append(f"delivery_claim_boundary:C{number}")
        if contract.get("temporal_mode_per_claim"):
            temporal_lines = [line for line in block.splitlines() if re.search(r"时态\s*[：:]", line)]
            if not temporal_lines:
                heading_tokens = re.findall(
                    r"\b(?:" + "|".join(TEMPORAL_TOKENS) + r")\b",
                    block.splitlines()[0],
                )
                if heading_tokens:
                    temporal_lines = [block.splitlines()[0]]
            tokens = re.findall(r"\b(?:" + "|".join(TEMPORAL_TOKENS) + r")\b", "\n".join(temporal_lines))
            if len(temporal_lines) != 1 or len(tokens) != 1:
                failures.append(f"delivery_claim_temporal:C{number}")
                continue
            if tokens[0] == "STATE_AT_AS_OF" and not re.search(
                r"覆盖(?:至|到)|coverage_through|状态(?:持续|截至)至", block, re.IGNORECASE
            ):
                failures.append(f"delivery_claim_state_without_coverage:C{number}")
            if tokens[0] == "ABSENCE_BY_AS_OF":
                corpus = re.search(r"索引|语料|公告清单|披露清单|corpus", block, re.IGNORECASE)
                dates = set(re.findall(r"(?:19|20)\d{2}-\d{2}-\d{2}", block))
                if not corpus or len(dates) < 2:
                    failures.append(f"delivery_claim_absence_without_corpus:C{number}")

    if contract.get("one_next_evidence_object"):
        section = markdown_section(report, r"唯一.*下一|下一验证")
        if not one_next_evidence_object(section):
            failures.append("delivery_next_evidence_object")
    return list(dict.fromkeys(failures))


def compact_arguments(value: Any, limit: int = 2000) -> str:
    if isinstance(value, str):
        raw = value
    else:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return raw if len(raw) <= limit else raw[:limit] + "…"


def tool_result_text(data: dict[str, Any]) -> str:
    values: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in {"message", "text", "output", "content", "error", "stderr"}:
                    visit(item)

    visit(data)
    return "\n".join(values)


def result_failure_reason(data: dict[str, Any], text: str) -> str | None:
    message = data.get("message")
    explicit = data.get("isError") is True or (
        isinstance(message, dict) and message.get("isError") is True
    )
    if explicit:
        return "isError"
    codes = [int(match) for match in EXIT_CODE.findall(text)]
    if any(code != 0 for code in codes):
        return "nonzero_exit_code"
    if re.search(
        r"(?im)(?:^\s*(?:fetch failed|traceback\b)|^.*no such file or directory\b)",
        text,
    ):
        return "command_error_text"
    return None


def trace_contract_failures(metrics: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    failures = []
    trace = metrics.get("tool_trace")
    if not isinstance(trace, list):
        return ["delivery_tool_trace_missing"]
    calls = [row for row in trace if row.get("event") == "call"]
    results = [row for row in trace if row.get("event") == "result"]
    research = [row for row in calls if row.get("name") in {"bash", "web_search"}]
    investing_reads = [
        row
        for row in calls
        if row.get("name") == "read"
        and "references/investing.md" in str(row.get("arguments", ""))
    ]
    read_complete_sequence = None
    if investing_reads:
        call_id = investing_reads[0].get("call_id")
        completed = [row["sequence"] for row in results if row.get("call_id") == call_id]
        if completed:
            read_complete_sequence = min(completed)
    first_research_sequence = research[0]["sequence"] if research else None
    if contract.get("profile_loaded_before_research") and (
        read_complete_sequence is None
        or first_research_sequence is None
        or read_complete_sequence >= first_research_sequence
    ):
        failures.append("delivery_profile_not_loaded_before_research")
    if contract.get("official_index_first_for_ashare"):
        if not research or "ashare_disclosures.py" not in str(research[0].get("arguments", "")):
            failures.append("delivery_official_index_not_first")
    return failures


def receipt_tool_trace(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep order/failure evidence without copying arbitrary tool arguments."""
    trace = metrics.get("tool_trace")
    if not isinstance(trace, list):
        return []
    safe = []
    for row in trace:
        if not isinstance(row, dict):
            continue
        arguments = str(row.get("arguments", ""))
        markers = []
        if "references/investing.md" in arguments:
            markers.append("investing_profile")
        if "ashare_disclosures.py" in arguments:
            markers.append("ashare_disclosure_index")
        safe.append(
            {
                key: row.get(key)
                for key in (
                    "sequence",
                    "event",
                    "call_id",
                    "name",
                    "failed",
                    "failure_reason",
                )
                if key in row
            }
        )
        if markers:
            safe[-1]["argument_markers"] = markers
    return safe


def recover_workspace_report(workspace: Path, destination: Path) -> dict[str, Any] | None:
    """Preserve a workspace report without converting a failed host delivery to success."""
    source = workspace / "REPORT.md"
    if not source.is_file():
        return None
    try:
        content = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    if not content.strip():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "path": destination.name,
        "sha256": BASE.sha256_file(destination),
    }


def parse_dsh_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    event_types: Counter[str] = Counter()
    tool_call_attempts: Counter[str] = Counter()
    tool_names_by_call_id: dict[str, str] = {}
    budget_denied_call_ids: set[str] = set()
    tool_trace: list[dict[str, Any]] = []
    tool_failure_records: list[tuple[str | None, str, str]] = []
    session_id = None
    session_cwd = None
    provider = None
    model = None
    reasoning_effort = None
    permission_preset = None
    sandbox_mode = None
    approval_policy = None
    available_tools: list[str] = []
    input_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    cache_read_tokens = 0
    first_ms = None
    last_ms = None
    malformed_lines = 0
    retry_events = 0

    for sequence, event in enumerate(events):
        event_type = event.get("type")
        if not isinstance(event_type, str):
            event_type = "?"
        event_types[event_type] += 1
        if "retry" in event_type.lower():
            retry_events += 1
        data = event.get("data")
        if not isinstance(data, dict):
            data = {}
        if event_type == "runner/malformed-lines":
            malformed_lines += integer(data.get("count"))
        timestamp = event.get("time")
        if isinstance(timestamp, int) and not isinstance(timestamp, bool):
            first_ms = timestamp if first_ms is None else min(first_ms, timestamp)
            last_ms = timestamp if last_ms is None else max(last_ms, timestamp)
        if event_type == "session":
            session_id = event.get("id")
            session_cwd = event.get("cwd")
        elif event_type == "permission/preset":
            permission_preset = data.get("preset")
        elif event_type == "sandbox/mode":
            sandbox_mode = data.get("mode")
        elif event_type == "approval/policy":
            approval_policy = data.get("policy")
        elif event_type == "request/header":
            header = data.get("header")
            if isinstance(header, dict):
                config = header.get("config")
                if isinstance(config, dict):
                    provider = provider or config.get("provider")
                    model = model or config.get("model")
                    reasoning_effort = reasoning_effort or config.get("reasoningEffort")
                tools = header.get("tools")
                if isinstance(tools, list):
                    available_tools = sorted(
                        {
                            item.get("name")
                            for item in tools
                            if isinstance(item, dict)
                            and isinstance(item.get("name"), str)
                        }
                    )
        elif event_type == "tool/call":
            name = data.get("name")
            resolved_name = name if isinstance(name, str) else "?"
            tool_call_attempts[resolved_name] += 1
            call_id = data.get("callId")
            if isinstance(call_id, str):
                tool_names_by_call_id[call_id] = resolved_name
            tool_trace.append(
                {
                    "sequence": sequence,
                    "event": "call",
                    "call_id": call_id if isinstance(call_id, str) else None,
                    "name": resolved_name,
                    "arguments": compact_arguments(data.get("arguments")),
                }
            )
        elif event_type == "tool/result":
            serialized = json.dumps(data, ensure_ascii=False, sort_keys=True)
            message = data.get("message")
            source = message.get("source") if isinstance(message, dict) else None
            call_id = data.get("callId")
            if not isinstance(call_id, str):
                call_id = source.get("callId") if isinstance(source, dict) else None
            resolved_name = tool_names_by_call_id.get(call_id, "?")
            result_text = tool_result_text(data)
            failure_reason = result_failure_reason(data, result_text)
            tool_trace.append(
                {
                    "sequence": sequence,
                    "event": "result",
                    "call_id": call_id if isinstance(call_id, str) else None,
                    "name": resolved_name,
                    "failed": failure_reason is not None,
                    "failure_reason": failure_reason,
                }
            )
            if failure_reason is not None:
                tool_failure_records.append((call_id, resolved_name, failure_reason))
            if (
                BUDGET_GUARD_TOOL_REASON in serialized
                or BUDGET_GUARD_WEB_REASON in serialized
            ):
                if isinstance(call_id, str):
                    budget_denied_call_ids.add(call_id)

        usage = data.get("usage")
        if isinstance(usage, dict):
            input_tokens += integer(usage.get("inputTokens"))
            output_tokens += integer(usage.get("outputTokens"))
            reasoning_tokens += integer(usage.get("reasoningTokens"))
            cache_read_tokens += integer(usage.get("cacheReadTokens"))
        message = data.get("message")
        if isinstance(message, dict):
            source = message.get("source")
            if isinstance(source, dict):
                provider = provider or source.get("provider")
                model = model or source.get("model")

    budget_denied: Counter[str] = Counter(
        tool_names_by_call_id.get(call_id, "?")
        for call_id in budget_denied_call_ids
    )
    tool_failures: Counter[str] = Counter(
        name
        for call_id, name, _reason in tool_failure_records
        if call_id not in budget_denied_call_ids
    )
    tool_calls = tool_call_attempts - budget_denied
    return {
        "session_id": session_id,
        "session_cwd": session_cwd,
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "permission_preset": permission_preset,
        "sandbox_mode": sandbox_mode,
        "approval_policy": approval_policy,
        "available_tools": available_tools,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cache_read_tokens": cache_read_tokens,
        "tokens_total": input_tokens + output_tokens + reasoning_tokens,
        "tool_calls": sum(tool_calls.values()),
        "tool_calls_by_name": dict(sorted(tool_calls.items())),
        "tool_call_attempts": sum(tool_call_attempts.values()),
        "tool_call_attempts_by_name": dict(sorted(tool_call_attempts.items())),
        "budget_denied_tool_calls": sum(budget_denied.values()),
        "budget_denied_tool_calls_by_name": dict(sorted(budget_denied.items())),
        "tool_result_failures": sum(tool_failures.values()),
        "tool_result_failures_by_name": dict(sorted(tool_failures.items())),
        "tool_result_failure_reasons": dict(
            sorted(
                Counter(
                    reason
                    for call_id, _name, reason in tool_failure_records
                    if call_id not in budget_denied_call_ids
                ).items()
            )
        ),
        "tool_trace": tool_trace,
        "web_search": tool_calls["web_search"],
        "host_retry_events": retry_events,
        "malformed_jsonl_lines": malformed_lines,
        "wall_seconds_from_events": (
            round((last_ms - first_ms) / 1000, 3)
            if isinstance(first_ms, int) and isinstance(last_ms, int)
            else None
        ),
    }


def host_signature(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: metrics.get(key)
        for key in (
            "provider",
            "model",
            "reasoning_effort",
            "permission_preset",
            "sandbox_mode",
            "approval_policy",
            "available_tools",
        )
    }


def run_one(
    *,
    args: argparse.Namespace,
    case: dict[str, Any],
    arm: str,
    arm_instruction: str,
    shared: str,
    output: Path,
    seed: str,
) -> dict[str, Any]:
    case_id = case["id"]
    opaque = BASE.blind_id(seed, case_id, arm)
    operator_dir = output / "operator/cases" / case_id / arm
    review_dir = output / "review/cases" / case_id / opaque
    workspace = output / "operator/workspaces" / case_id / arm
    session_root = operator_dir / "session-store"
    isolated_home = output / "operator/runtime-homes" / case_id / arm
    for path in (operator_dir, review_dir, workspace, session_root, isolated_home):
        path.mkdir(parents=True, exist_ok=False)
    (workspace / "sources").mkdir()

    task = case["prompt_path"].read_text(encoding="utf-8")
    composed = BASE.compose_prompt(arm_instruction, shared, task)
    patch_text = session_patch(
        session_root, args.max_tool_calls, args.max_web_searches
    )
    (operator_dir / "task-prompt.md").write_text(task, encoding="utf-8")
    (operator_dir / "arm-instruction.md").write_text(arm_instruction, encoding="utf-8")
    (operator_dir / "shared-run-instruction.md").write_text(shared + "\n", encoding="utf-8")
    (operator_dir / "composed-prompt.md").write_text(composed, encoding="utf-8")
    patch_path = operator_dir / "session.patch.yml"
    patch_path.write_text(patch_text, encoding="utf-8")

    if arm == "candidate":
        identity = args.profile_pair["canonical_identities"][case["profile"]]
        profile_name = args.candidate_profile
    else:
        identity = {
            "schema_version": "resanity.dsh-baseline-absence.v1",
            "status": "PASS",
            "profile": args.baseline_profile,
            "candidate_skill_present": False,
            "checked": [
                str(args.dsh_home / "profiles" / args.baseline_profile / "node_modules/resanity/SKILL.md"),
                str(workspace / ".dsh/skills/resanity/SKILL.md"),
                str(isolated_home / ".agents/skills/resanity/SKILL.md"),
            ],
        }
        profile_name = args.baseline_profile
    BASE.write_json(operator_dir / "skill-identity.json", identity)

    environment = os.environ.copy()
    environment["DSH_HOME"] = str(args.dsh_home)
    environment["HOME"] = str(isolated_home)
    environment["DSH_PERMISSION_MODE"] = "workspace-write"
    environment["DSH_TELEMETRY_MODE"] = "DISABLED"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.update(WATCH_ENVIRONMENT)
    if not args.inherit_market_data_credentials:
        environment.pop("TUSHARE_TOKEN", None)
        environment.pop("RESANITY_CREDENTIALS", None)
    command = [
        args.dsh_bin,
        "--profile",
        profile_name,
        "--patch",
        str(patch_path),
        composed,
    ]
    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            command,
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
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
    (operator_dir / "stdout.md").write_text(stdout, encoding="utf-8")
    (operator_dir / "stderr.log").write_text(stderr, encoding="utf-8")
    (operator_dir / "exit-code").write_text(f"{exit_code}\n", encoding="utf-8")

    sessions = sorted(session_root.rglob("session.jsonl.zstd"))
    metrics: dict[str, Any] = {}
    skills: list[str] = []
    raw_path = operator_dir / "raw-session.jsonl.zstd"
    if len(sessions) == 1:
        shutil.copy2(sessions[0], raw_path)
        events = read_dsh_events(raw_path, args.zstd_bin)
        metrics = parse_dsh_metrics(events)
        skills = skill_names(events)

    report_failures = report_delivery_failures(stdout)
    report_present = not report_failures
    report_available = report_present
    report_origin = "final_response" if report_present else "missing"
    recovered_report = None
    if report_present:
        report_path = operator_dir / "report.md"
        report_path.write_text(stdout, encoding="utf-8")
        shutil.copy2(report_path, review_dir / "report.md")
    else:
        recovered_report = recover_workspace_report(
            workspace, operator_dir / "recovered-report.md"
        )
        if recovered_report is not None:
            shutil.copy2(
                operator_dir / "recovered-report.md",
                review_dir / "recovered-report.md",
            )
            shutil.copy2(
                operator_dir / "recovered-report.md",
                operator_dir / "report.md",
            )
            shutil.copy2(operator_dir / "report.md", review_dir / "report.md")
            report_available = True
            report_origin = "workspace_recovery"
    sources = BASE.copy_sources(workspace, operator_dir, review_dir)

    host_receipt = {
        "schema_version": "resanity.host-receipt.v1",
        "host": "dsh",
        "profile": profile_name,
        "provider": metrics.get("provider"),
        "model": metrics.get("model"),
        "reasoning_effort": metrics.get("reasoning_effort"),
        "session_id": metrics.get("session_id"),
        "runtime": {
            "input_tokens": metrics.get("input_tokens"),
            "output_tokens": metrics.get("output_tokens"),
            "reasoning_tokens": metrics.get("reasoning_tokens"),
            "cache_read_tokens": metrics.get("cache_read_tokens"),
            "non_cached_input_tokens": metrics.get("input_tokens"),
            "tokens_total": metrics.get("tokens_total"),
            "tool_calls": metrics.get("tool_calls"),
            "tool_call_attempts": metrics.get("tool_call_attempts"),
            "budget_denied_tool_calls": metrics.get("budget_denied_tool_calls"),
            "tool_result_failures": metrics.get("tool_result_failures"),
            "wall_seconds": wall_seconds,
        },
        "budget_usage": {
            "non_cached_input_tokens": metrics.get("input_tokens"),
            "tool_calls": metrics.get("tool_calls"),
            "web_search": metrics.get("web_search"),
            "wall_seconds": wall_seconds,
        },
        "host_signature": host_signature(metrics),
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
        "tool_trace": receipt_tool_trace(metrics),
        "invoked_skills": skills,
        "raw_session": (
            {"path": raw_path.name, "sha256": BASE.sha256_file(raw_path)}
            if raw_path.is_file()
            else None
        ),
        "runner": {
            "automatic_retries": 0,
            "host_retry_events": metrics.get("host_retry_events"),
            "malformed_jsonl_lines": metrics.get("malformed_jsonl_lines"),
            "timed_out": timed_out,
            "session_artifacts": len(sessions),
            "recovered_report": recovered_report,
            "report_available": report_available,
            "report_origin": report_origin,
        },
    }
    BASE.write_json(operator_dir / "host-receipt.json", host_receipt)

    failures = []
    if exit_code != 0:
        failures.append("dsh_exit_code")
    if len(sessions) != 1:
        failures.append("raw_session_count")
    failures.extend(report_failures)
    if metrics:
        expected = {
            "provider": args.expected_provider,
            "model": args.expected_model,
            "reasoning_effort": args.expected_reasoning_effort,
            "permission_preset": "workspace-write",
            "sandbox_mode": "workspace-write",
            "approval_policy": "ask",
        }
        for key, value in expected.items():
            if metrics.get(key) != value:
                failures.append(f"host_{key}_mismatch")
        if metrics.get("session_cwd") != str(workspace):
            failures.append("session_cwd_mismatch")
        if integer(metrics.get("input_tokens")) > args.max_non_cached_input_tokens:
            failures.append("non_cached_input_tokens")
        if integer(metrics.get("tool_calls")) > args.max_tool_calls:
            failures.append("tool_calls")
        if integer(metrics.get("web_search")) > args.max_web_searches:
            failures.append("web_search")
        if integer(metrics.get("host_retry_events")):
            failures.append("host_retry_events")
        if integer(metrics.get("malformed_jsonl_lines")):
            failures.append("malformed_jsonl_lines")
    if wall_seconds > args.max_wall_seconds:
        failures.append("wall_seconds")
    resanity_invocations = skills.count("resanity")
    if arm == "candidate" and resanity_invocations != 1:
        failures.append("candidate_resanity_invocation_count")
    if arm == "baseline" and resanity_invocations != 0:
        failures.append("baseline_resanity_contamination")
    if case["mode"] == "open" and sources == 0:
        failures.append("open_case_source_snapshots_missing")

    result_summary = {
        "case_id": case_id,
        "arm": arm,
        "blind_id": opaque,
        "exit_code": exit_code,
        "artifact_complete": not failures,
        "report_present": report_present,
        "report_available": report_available,
        "report_origin": report_origin,
        "recovered_report": recovered_report is not None,
        "source_files": sources,
        "resanity_invocations": resanity_invocations,
        "mechanical_failures": failures,
        "host_signature": host_signature(metrics),
        "host_receipt": str((operator_dir / "host-receipt.json").relative_to(output)),
    }
    BASE.write_json(operator_dir / "collection-result.json", result_summary)
    return result_summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="launch 16 paid DSH sessions")
    parser.add_argument("--output", type=Path, help="new output directory; required with --run")
    parser.add_argument("--candidate-root", type=Path, default=ROOT)
    parser.add_argument("--expected-skill-sha256", help="frozen canonical SKILL.md SHA-256")
    parser.add_argument("--prelayers-receipt", type=Path, help="frozen prelayer receipt")
    parser.add_argument(
        "--accept-known-prelayer-failures",
        action="store_true",
        help="run an experimental A/B while preserving explicit known prelayer failures",
    )
    parser.add_argument("--dsh-bin", default=shutil.which("dsh") or "dsh")
    parser.add_argument(
        "--dsh-home",
        type=Path,
        default=Path(os.environ["DSH_HOME"]) if "DSH_HOME" in os.environ else None,
    )
    parser.add_argument("--baseline-profile", default="headless-baseline")
    parser.add_argument("--candidate-profile", default="headless-resanity")
    parser.add_argument("--active-skill", type=Path, required=True)
    parser.add_argument("--expected-provider", required=True)
    parser.add_argument("--expected-model", required=True)
    parser.add_argument("--expected-reasoning-effort", required=True)
    parser.add_argument("--zstd-bin", default=shutil.which("zstd") or "zstd")
    parser.add_argument("--run-date", type=BASE.parse_date, default=date.today())
    parser.add_argument("--seed", help="recorded arm-order/blinding seed")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-non-cached-input-tokens", type=int, default=150_000)
    parser.add_argument("--max-tool-calls", type=int, default=30)
    parser.add_argument("--max-web-searches", type=int, default=15)
    parser.add_argument("--max-wall-seconds", type=int, default=900)
    parser.add_argument(
        "--inherit-market-data-credentials",
        action="store_true",
        help="explicitly expose host Tushare/Resanity credentials to both arms",
    )
    args = parser.parse_args(argv)
    if args.dsh_home is None:
        parser.error("--dsh-home is required when DSH_HOME is not set")
    args.dsh_home = args.dsh_home.expanduser().resolve()
    args.candidate_root = args.candidate_root.resolve()
    args.active_skill = args.active_skill.expanduser().resolve()
    args.isolated_user_home = Path("/nonexistent/resanity-dsh-ab-user")
    if args.output is not None:
        args.output = args.output.expanduser().resolve()
    if args.run and args.output is None:
        parser.error("--output is required with --run")
    if args.run and args.output is not None:
        try:
            args.output.relative_to(ROOT)
        except ValueError:
            pass
        else:
            parser.error("--output must be outside the source repository")
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
    pair: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "DRY_RUN_READY"
            if prelayers is not None and args.expected_skill_sha256
            else "DRY_RUN_BLOCKED"
        ),
        "method_status": "UNBENCHMARKED_CURRENT",
        "semantic_scoring": "NOT_RUN",
        "candidate_skill_sha256": skill_sha,
        "candidate_profiles_sha256": profiles_sha,
        "expected_skill_sha256_supplied": args.expected_skill_sha256 is not None,
        "prelayers_receipt": (
            prelayers.get("status") if prelayers is not None else "NOT_SUPPLIED"
        ),
        "host": {
            "adapter": "dsh-headless",
            "version": version,
            "provider": args.expected_provider,
            "model": args.expected_model,
            "reasoning_effort": args.expected_reasoning_effort,
        },
        "profile_pair": pair,
        "runtime_patch": args.runtime_patch,
        "zstd_version": args.compressor_version,
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
    BASE.run_source_contract()
    suite = BASE.load_suite()
    plan = BASE.final_ab_plan(suite)
    skill_sha = BASE.validate_expected_skill(
        args.candidate_root, args.expected_skill_sha256, required=args.run
    )
    profiles_sha = BASE.profile_hashes(args.candidate_root)
    prelayers = BASE.validate_prelayers(
        args.prelayers_receipt,
        skill_sha,
        profiles_sha,
        required=args.run,
        allow_known_failures=args.accept_known_prelayer_failures,
    )
    version = dsh_version(args.dsh_bin)
    compressor_version = zstd_version(args.zstd_bin)
    pair = profile_pair_receipt(args, skill_sha)
    runtime_patch = validate_runtime_patch(args)
    args.profile_pair = pair
    args.runtime_patch = runtime_patch
    args.compressor_version = compressor_version
    if not args.run:
        print(
            BASE.canonical_json(
                dry_run_receipt(
                    args, plan, skill_sha, profiles_sha, prelayers, version, pair
                )
            ),
            end="",
        )
        return 0

    assert args.output is not None
    if args.output.exists():
        raise FinalAbError(f"output already exists; refusing overwrite: {args.output}")
    args.output.mkdir(parents=True)
    seed = args.seed or os.urandom(16).hex()
    repository = BASE.freeze_repository()
    shared = shared_instruction(args)
    final_ab = suite["layers"]["final_ab"]
    arm_instructions = {
        "baseline": (BASE.SUITE_PATH.parent / final_ab["baseline_prompt"]).read_text(
            encoding="utf-8"
        ),
        "candidate": (BASE.SUITE_PATH.parent / final_ab["candidate_prompt"]).read_text(
            encoding="utf-8"
        ),
    }
    jobs = [(case, arm) for case in plan for arm in ARMS]
    random.Random(seed).shuffle(jobs)
    arm_map = {
        case["id"]: {
            BASE.blind_id(seed, case["id"], arm): arm for arm in ARMS
        }
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
        "prelayers_receipt_sha256": BASE.sha256_file(args.prelayers_receipt.resolve()),
        "prelayers_status": prelayers.get("status"),
        "known_prelayer_failures_accepted": args.accept_known_prelayer_failures,
        "host": {
            "adapter": "dsh-headless",
            "version": version,
            "provider": args.expected_provider,
            "model": args.expected_model,
            "reasoning_effort": args.expected_reasoning_effort,
            "permission_mode": "workspace-write",
        },
        "profile_pair": pair,
        "runtime_patch": runtime_patch,
        "zstd_version": compressor_version,
        "budgets_per_arm": {
            "non_cached_input_tokens": args.max_non_cached_input_tokens,
            "tool_calls": args.max_tool_calls,
            "web_search": args.max_web_searches,
            "wall_seconds": args.max_wall_seconds,
        },
        "market_data_credentials_inherited": args.inherit_market_data_credentials,
        "run_date": args.run_date.isoformat(),
        "seed": seed,
        "concurrency": args.concurrency,
        "automatic_retries": 0,
        "session_count": len(jobs),
        "job_order": [
            {
                "case_id": case["id"],
                "blind_id": BASE.blind_id(seed, case["id"], arm),
            }
            for case, arm in jobs
        ],
    }
    BASE.write_json(args.output / "operator/run-manifest.json", manifest)
    BASE.write_json(args.output / "operator/arm-map.json", arm_map)
    BASE.write_json(args.output / "operator/dsh-profile-pair.json", pair)
    BASE.write_json(
        args.output / "review/review-manifest.json",
        {
            "schema_version": "resanity.final-ab-blind-review.v1",
            "candidate_skill_sha256": skill_sha,
            "case_ids": [case["id"] for case in plan],
            "blind_arms": {
                case["id"]: sorted(arm_map[case["id"]]) for case in plan
            },
            "instructions": (
                "Review reports and source snapshots without opening operator/arm-map.json; "
                "establish the fact index before scoring load-bearing claims."
            ),
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
                output=args.output,
                seed=seed,
            ): (case, arm)
            for case, arm in jobs
        }
        for future in concurrent.futures.as_completed(futures):
            case, arm = futures[future]
            try:
                row = future.result()
            except Exception as error:  # one-shot failure is preserved, never retried
                row = {
                    "case_id": case["id"],
                    "arm": arm,
                    "blind_id": BASE.blind_id(seed, case["id"], arm),
                    "exit_code": None,
                    "artifact_complete": False,
                    "report_present": False,
                    "source_files": 0,
                    "mechanical_failures": [f"runner_error:{type(error).__name__}"],
                    "runner_error": str(error),
                }
            results.append(row)
            print(
                f"{row['case_id']} {arm}: "
                f"{'COMPLETE' if row['artifact_complete'] else 'INCOMPLETE'}",
                file=sys.stderr,
                flush=True,
            )

    pair_signature_failures = []
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for row in results:
        by_case.setdefault(row["case_id"], {})[row["arm"]] = row
    for case_id, arms in by_case.items():
        if set(arms) != set(ARMS):
            pair_signature_failures.append(f"{case_id}:missing_arm")
            continue
        if arms["baseline"].get("host_signature") != arms["candidate"].get(
            "host_signature"
        ):
            pair_signature_failures.append(f"{case_id}:host_signature_mismatch")

    results.sort(key=lambda row: (row["case_id"], row["arm"]))
    complete = [row for row in results if row.get("artifact_complete")]
    status = (
        "COLLECTION_COMPLETE_AWAITING_BLIND_REVIEW"
        if len(complete) == 16 and not pair_signature_failures
        else "COLLECTION_INCOMPLETE"
    )
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
        "pair_signature_failures": pair_signature_failures,
        "results": results,
        "next_step": (
            "independent blind human review; do not infer a winner from collection status"
        ),
    }
    BASE.write_json(args.output / "collection-summary.json", summary)
    BASE.write_json(
        args.output / "operator/run-manifest.json",
        {
            **manifest,
            "status": status,
            "completed_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "completed_artifacts": len(complete),
            "expected_artifacts": 16,
        },
    )
    print(BASE.canonical_json(summary), end="")
    return 0 if status == "COLLECTION_COMPLETE_AWAITING_BLIND_REVIEW" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FinalAbError, OSError, json.JSONDecodeError) as error:
        print(f"FINAL_AB_DSH_BLOCKED: {error}", file=sys.stderr)
        raise SystemExit(2)
