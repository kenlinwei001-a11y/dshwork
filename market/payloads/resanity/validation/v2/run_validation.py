#!/usr/bin/env python3
"""Run Resanity v2 mechanical preflight without scoring research semantics.

The runner executes source, Skill, test, identity, anchor, and package checks.
It can also run one explicitly requested, read-only Tushare acquisition. It
never invokes a model, retries research, installs a Skill, or marks a semantic
layer/final A/B as passed.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "resanity.v2-mechanical-preflight.v1"
PROFILES = ("core", "investing", "anchors", "formal-audit")
EXPECTED_PACKAGE_FILES = {
    "SKILL.md",
    "references/anchors.md",
    "references/investing.md",
    "scripts/ashare_disclosures.py",
    "scripts/free_market_observations.py",
    "tools/anchor_check.py",
}
FORBIDDEN_PACKAGE_PREFIXES = ("validation/v2/",)


class ValidationError(ValueError):
    """A mechanical validation contract failed."""


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"invalid JSON {path}: {error}") from error


def safe_tail(value: str, limit: int = 4000) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[-limit:]


def run_command(
    name: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    parse_json: bool = False,
) -> tuple[dict[str, Any], Any | None]:
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    step: dict[str, Any] = {
        "name": name,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "exit_code": result.returncode,
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
    payload = None
    if parse_json and result.stdout.strip():
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            step["status"] = "FAIL"
            step["error"] = f"stdout was not JSON: {error}"
    if step["status"] == "FAIL":
        if result.stderr.strip():
            step["stderr_tail"] = safe_tail(result.stderr)
        if result.stdout.strip() and payload is None:
            step["stdout_tail"] = safe_tail(result.stdout)
    return step, payload


def skipped_step(name: str, reason: str) -> dict[str, Any]:
    return {"name": name, "status": "SKIPPED", "reason": reason}


def repository_identity() -> dict[str, Any]:
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
        raise ValidationError("source checkout must be a readable Git worktree")
    changed = [line[3:] for line in status.stdout.splitlines() if len(line) >= 4]
    return {
        "git_commit": head.stdout.strip(),
        "worktree_dirty": bool(changed),
        "changed_paths": changed,
        "canonical_skill_sha256": hashlib.sha256((ROOT / "SKILL.md").read_bytes()).hexdigest(),
    }


def resolve_skill_validator(explicit: Path | None) -> Path | None:
    candidates = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    configured = os.environ.get("RESANITY_SKILL_VALIDATOR")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(
        Path.home() / ".codex/skills/.system/skill-creator/scripts/quick_validate.py"
    )
    return next((path.resolve() for path in candidates if path.is_file()), None)


def identity_steps(
    *, host: str, active_skill: Path | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    actual = active_skill
    if actual is not None and actual.is_dir():
        actual = actual / "SKILL.md"
    target = actual or (ROOT / "SKILL.md")
    steps = []
    receipts: dict[str, Any] = {}
    for profile in PROFILES:
        command = [
            sys.executable,
            str(ROOT / "tools/skill_identity.py"),
            "--canonical-root",
            str(ROOT),
            "--host",
            host,
            "--cwd",
            str(ROOT),
            "--profile",
            profile,
            "--active-skill",
            str(target),
        ]
        step, payload = run_command(f"identity:{profile}", command, parse_json=True)
        steps.append(step)
        if isinstance(payload, dict):
            receipt_method = payload.get("receipt_method", {})
            receipts[profile] = {
                "ok": payload.get("ok"),
                "host": payload.get("host"),
                "resolution": payload.get("resolution"),
                "canonical_skill_sha256": receipt_method.get("canonical_skill_sha256"),
                "profile": receipt_method.get("profile"),
                "active": receipt_method.get("active"),
                "matches_canonical": payload.get("matches_canonical"),
                "shadowed": [
                    {
                        "scope": row.get("scope"),
                        "locator": row.get("locator"),
                        "skill_sha256": row.get("skill_sha256"),
                    }
                    for row in payload.get("shadowed", [])
                    if isinstance(row, dict)
                ],
            }
    install_status = "PASS" if active_skill is not None and all(
        step["status"] == "PASS" for step in steps
    ) else "NOT_CHECKED" if active_skill is None else "FAIL"
    return steps, {
        "status": install_status,
        "mode": "host-active-locator" if active_skill is not None else "canonical-source-only",
        "active_locator_supplied": active_skill is not None,
        "profiles": receipts,
    }


def anchor_smoke() -> dict[str, Any]:
    today = date.today().isoformat()
    with tempfile.TemporaryDirectory(prefix="resanity-anchor-smoke-") as raw:
        anchors = Path(raw)
        (anchors / "active-topic.md").write_text(
            f"## A1\n- 状态：active\n- 更新触发器：{today} 验收\n",
            encoding="utf-8",
        )
        (anchors / "realized-topic.md").write_text(
            f"## A2\n- 状态：realized\n- 更新触发器：{today} 验收\n",
            encoding="utf-8",
        )
        started = time.monotonic()
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/anchor_check.py"),
                "--anchors",
                str(anchors),
                "--window",
                "0",
                "--no-notify",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        step = {
            "name": "anchor-readonly-smoke",
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "exit_code": result.returncode,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
        if result.returncode != 0:
            step["stderr_tail"] = safe_tail(result.stderr)
        elif "active-topic" not in result.stdout or "realized-topic" in result.stdout:
            step["status"] = "FAIL"
            step["error"] = "active/non-active reminder boundary failed"
    return step


def package_step() -> tuple[dict[str, Any], dict[str, Any] | None]:
    npm = shutil.which("npm")
    if npm is None:
        return {"name": "npm-pack-dry-run", "status": "FAIL", "error": "npm not found"}, None
    with tempfile.TemporaryDirectory(prefix="resanity-npm-cache-") as cache:
        environment = os.environ.copy()
        environment["npm_config_cache"] = cache
        step, payload = run_command(
            "npm-pack-dry-run",
            [npm, "pack", "--dry-run", "--json"],
            env=environment,
            parse_json=True,
        )
    if step["status"] != "PASS":
        return step, None
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        step["status"] = "FAIL"
        step["error"] = "unexpected npm pack JSON"
        return step, None
    package = payload[0]
    files = {
        row.get("path") for row in package.get("files", []) if isinstance(row, dict)
    }
    missing = sorted(EXPECTED_PACKAGE_FILES - files)
    leaked = sorted(
        path for path in files if isinstance(path, str) and path.startswith(FORBIDDEN_PACKAGE_PREFIXES)
    )
    if missing or leaked:
        step["status"] = "FAIL"
        step["error"] = {"missing_required": missing, "internal_validation_leak": leaked}
    return step, {
        "filename": package.get("filename"),
        "package_size": package.get("size"),
        "unpacked_size": package.get("unpackedSize"),
        "file_count": len(files),
        "missing_required": missing,
        "internal_validation_leak": leaked,
    }


def load_market_module():
    path = ROOT / "scripts/free_market_observations.py"
    spec = importlib.util.spec_from_file_location("resanity_market_observations", path)
    if spec is None or spec.loader is None:
        raise ValidationError("cannot load market observation validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def secret_like_keys(value: Any, prefix: str = "") -> list[str]:
    hits = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            normalized = str(key).lower().replace("-", "_")
            if any(marker in normalized for marker in ("token", "secret", "credential", "api_key")):
                hits.append(path)
            hits.extend(secret_like_keys(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(secret_like_keys(child, f"{prefix}[{index}]"))
    return hits


def validate_tushare_packet(request: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    market = load_market_module()
    normalized_request = market._request(request)  # mechanical schema normalization
    if normalized_request["provider"] != "TUSHARE":
        raise ValidationError("live feature check requires provider=TUSHARE")
    if packet.get("status") != "OBSERVATIONS_READY" or packet.get("provider") != "TUSHARE":
        raise ValidationError(f"Tushare acquisition not ready: {packet.get('status')}")
    expected_policy = normalized_request.get("provider_policy")
    if not isinstance(expected_policy, dict) or packet.get("provider_policy") != expected_policy:
        raise ValidationError("market provider policy mismatch")
    if secret_like_keys(packet):
        raise ValidationError("Tushare packet contains credential-like keys")

    cutoff = date.fromisoformat(normalized_request["as_of_date"])
    series_summary = {}
    for label in ("candidate", "benchmark"):
        section = packet.get(label)
        observations = section.get("observations") if isinstance(section, dict) else None
        if not isinstance(observations, list) or not observations:
            raise ValidationError(f"{label} observations missing")
        dates = [date.fromisoformat(row["date"]) for row in observations]
        if dates != sorted(dates) or any(day > cutoff for day in dates):
            raise ValidationError(f"{label} dates are unordered or exceed as-of")
        series_summary[label] = {
            "sessions": len(observations),
            "first_session": dates[0].isoformat(),
            "last_session": dates[-1].isoformat(),
        }

    if series_summary["candidate"]["last_session"] != series_summary["benchmark"]["last_session"]:
        raise ValidationError("candidate and benchmark latest sessions differ")
    receipt = packet.get("acquisition_receipt")
    if not isinstance(receipt, dict):
        raise ValidationError("acquisition receipt missing")
    if receipt.get("provider_policy") != expected_policy:
        raise ValidationError("acquisition receipt provider policy mismatch")
    if receipt.get("request_sha256") != canonical_hash(normalized_request):
        raise ValidationError("request hash mismatch")
    expected_series_hashes = {
        label: canonical_hash(packet[label]["observations"])
        for label in ("candidate", "benchmark")
    }
    if receipt.get("series_sha256") != expected_series_hashes:
        raise ValidationError("series hash mismatch")
    receipt_core_keys = (
        "schema_version",
        "request_sha256",
        "provider",
        "provider_policy",
        "provider_version",
        "research_as_of_date",
        "market_session_date",
        "adjustment",
        "series_sha256",
        "raw_file_sha256",
        "provider_endpoints",
    )
    receipt_core = {key: receipt[key] for key in receipt_core_keys if key in receipt}
    if receipt.get("receipt_id") != canonical_hash(receipt_core):
        raise ValidationError("receipt id mismatch")
    if receipt.get("attempted_providers") != ["TUSHARE"] or receipt.get("fallback_attempted") is not False:
        raise ValidationError("provider lineage or fallback boundary mismatch")
    return {
        "status": "PASS",
        "as_of_date": normalized_request["as_of_date"],
        "adjustment": packet.get("adjustment"),
        "receipt_id": receipt.get("receipt_id"),
        "provider_policy": expected_policy,
        "provider_endpoints": receipt.get("provider_endpoints", []),
        "warnings": receipt.get("warnings", []),
        "series": series_summary,
    }


def tushare_step(request_path: Path, output_path: Path | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        request = load_json(request_path)
    except ValidationError as error:
        return {"name": "tushare-live", "status": "FAIL", "error": str(error)}, None
    if not isinstance(request, dict):
        return {"name": "tushare-live", "status": "FAIL", "error": "request root must be object"}, None
    try:
        normalized = load_market_module()._request(request)
    except Exception as error:
        return {
            "name": "tushare-live",
            "status": "FAIL",
            "error": f"request rejected: {type(error).__name__}",
        }, None
    if normalized.get("provider") != "TUSHARE":
        return {
            "name": "tushare-live",
            "status": "FAIL",
            "error": "live feature check requires provider=TUSHARE",
        }, None
    with tempfile.TemporaryDirectory(prefix="resanity-tushare-smoke-") as raw:
        target = output_path or (Path(raw) / "observations.json")
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        step, _ = run_command(
            "tushare-live",
            [
                sys.executable,
                str(ROOT / "scripts/free_market_observations.py"),
                "--input",
                str(request_path),
                "--output",
                str(target),
            ],
        )
        if not target.is_file():
            step["status"] = "FAIL"
            step["error"] = "observation or failure receipt was not written"
            return step, None
        packet = load_json(target)
        if not isinstance(packet, dict):
            step["status"] = "FAIL"
            step["error"] = "observation packet root must be object"
            return step, None
        try:
            summary = validate_tushare_packet(request, packet)
        except ValidationError as error:
            step["status"] = "FAIL"
            step["error"] = str(error)
            summary = {
                "status": packet.get("status", "INVALID"),
                "reason": packet.get("reason"),
            }
        if output_path is not None:
            summary["observation_path"] = str(output_path.resolve())
        return step, summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("generic", "codex", "dsh"), default="generic")
    parser.add_argument("--active-skill", type=Path, help="actual host-loaded SKILL.md or its directory")
    parser.add_argument("--skill-validator", type=Path, help="skill-creator quick_validate.py path")
    parser.add_argument("--tushare-request", type=Path, help="explicit read-only Tushare request JSON")
    parser.add_argument("--tushare-output", type=Path, help="optional observation packet path")
    parser.add_argument("--output", type=Path, help="write the mechanical receipt to this JSON file")
    parser.add_argument("--skip-npm-test", action="store_true")
    parser.add_argument("--skip-pack", action="store_true")
    parser.add_argument("--skip-skill-validator", action="store_true")
    args = parser.parse_args(argv)
    if args.tushare_output is not None and args.tushare_request is None:
        parser.error("--tushare-output requires --tushare-request")
    explicit_paths = [
        path.resolve()
        for path in (args.tushare_request, args.tushare_output, args.output)
        if path is not None
    ]
    if len(explicit_paths) != len(set(explicit_paths)):
        parser.error("request, observation, and receipt paths must be distinct")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    steps: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    try:
        repository = repository_identity()
    except ValidationError as error:
        repository = {"error": str(error)}
        steps.append({"name": "repository-identity", "status": "FAIL", "error": str(error)})

    source_step, source_payload = run_command(
        "validation-source",
        [sys.executable, str(ROOT / "tools/validation_source_check.py")],
        parse_json=True,
    )
    steps.append(source_step)
    if source_payload is not None:
        details["validation_source"] = source_payload

    if args.skip_skill_validator:
        steps.append(skipped_step("skill-creator-quick-validate", "explicitly skipped"))
    else:
        validator = resolve_skill_validator(args.skill_validator)
        if validator is None:
            steps.append({
                "name": "skill-creator-quick-validate",
                "status": "FAIL",
                "error": "quick_validate.py not found; pass --skill-validator or --skip-skill-validator",
            })
        else:
            step, _ = run_command(
                "skill-creator-quick-validate",
                [sys.executable, str(validator), str(ROOT)],
            )
            step["validator"] = str(validator)
            steps.append(step)

    identity, identity_receipt = identity_steps(host=args.host, active_skill=args.active_skill)
    steps.extend(identity)
    details["install_identity"] = identity_receipt
    steps.append(anchor_smoke())

    if args.skip_npm_test:
        steps.append(skipped_step("npm-test", "explicitly skipped"))
    else:
        npm = shutil.which("npm")
        if npm is None:
            steps.append({"name": "npm-test", "status": "FAIL", "error": "npm not found"})
        else:
            step, _ = run_command("npm-test", [npm, "test"])
            steps.append(step)

    if args.skip_pack:
        steps.append(skipped_step("npm-pack-dry-run", "explicitly skipped"))
    else:
        step, package = package_step()
        steps.append(step)
        if package is not None:
            details["package"] = package

    if args.tushare_request is None:
        details["tushare_live"] = {"status": "NOT_REQUESTED"}
    else:
        step, summary = tushare_step(args.tushare_request, args.tushare_output)
        steps.append(step)
        details["tushare_live"] = summary

    failed = [step["name"] for step in steps if step["status"] == "FAIL"]
    skipped = [step["name"] for step in steps if step["status"] == "SKIPPED"]
    if failed:
        status = "MECHANICAL_PRECHECK_FAILED"
    elif skipped:
        status = "MECHANICAL_PRECHECK_INCOMPLETE"
    elif args.active_skill is None:
        status = "MECHANICAL_PRECHECK_OK_ACTIVE_IDENTITY_NOT_CHECKED"
    else:
        status = "MECHANICAL_PRECHECK_OK"
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repository": repository,
        "method_status": "UNBENCHMARKED_CURRENT",
        "semantic_layers": "NOT_RUN",
        "final_ab": "NOT_RUN",
        "automatic_retries": 0,
        "steps": steps,
        "failed_steps": failed,
        "skipped_steps": skipped,
        "details": details,
    }
    rendered = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
