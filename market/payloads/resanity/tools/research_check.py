#!/usr/bin/env python3
"""Validate a Resanity report receipt without judging research semantics.

The Markdown report remains the only semantic artifact. This checker only
verifies mechanical boundaries: canonical/active/profile identity, frozen
hashes, as-of dates, claim/source references, declared source lineage, and
explicit tool budgets. It never
rewrites a report, changes an evidence label, retries research, or decides a
conclusion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

try:
    from tools.skill_identity import IdentityError, file_locator, profile_identity
except ModuleNotFoundError:  # direct `python3 tools/research_check.py`
    from skill_identity import IdentityError, file_locator, profile_identity


SCHEMA_VERSION = "resanity.audit-receipt.v2"
HOST_RECEIPT_SCHEMA_VERSION = "resanity.host-receipt.v1"
BOUNDARIES = {
    "FACT",
    "SINGLE_SOURCE",
    "INFERENCE",
    "HYPOTHESIS",
    "NO_RESULT",
    "INSUFFICIENT",
}
SOURCE_KINDS = {"PRIMARY", "SECONDARY", "DATA", "INDEX"}
TEMPORAL_MODES = {
    "EVENT_BY_DATE",
    "STATE_AT_AS_OF",
    "ABSENCE_BY_AS_OF",
    "TIMELESS",
}
TEMPORAL_BASES = {
    "DATED_PUBLICATION",
    "VERSIONED_ARTIFACT",
    "ARCHIVED_SNAPSHOT",
    "LIVE_CURRENT",
    "UNKNOWN",
}
HISTORICAL_TEMPORAL_BASES = {
    "DATED_PUBLICATION",
    "VERSIONED_ARTIFACT",
    "ARCHIVED_SNAPSHOT",
}
DATE_EVIDENCE_KINDS = {
    "DOCUMENT_DATE",
    "DOCUMENT_METADATA",
    "VERSION_LABEL",
    "ARCHIVE_TIMESTAMP",
}
ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]{0,31}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _non_negative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _non_negative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _date(value: Any, code: str, errors: list[str]) -> date | None:
    if not isinstance(value, str):
        errors.append(code)
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors.append(code)
        return None
    if parsed.isoformat() != value:
        errors.append(code)
        return None
    return parsed


def _optional_date(value: Any, code: str, errors: list[str]) -> date | None:
    if value is None:
        return None
    return _date(value, code, errors)


def _inside(base: Path, raw: Any, code: str, errors: list[str]) -> Path | None:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        errors.append(code)
        return None
    base = base.resolve()
    target = (base / raw).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        errors.append(code)
        return None
    return target


def _load_host_receipt(path: Path, errors: list[str]) -> dict[str, Any] | None:
    """Load and mechanically validate a normalized host-owned runtime receipt."""
    try:
        host_receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append("host_receipt.json_invalid")
        return None
    if not isinstance(host_receipt, dict):
        errors.append("host_receipt.not_object")
        return None
    if host_receipt.get("schema_version") != HOST_RECEIPT_SCHEMA_VERSION:
        errors.append("host_receipt.schema_version_invalid")

    if not _text(host_receipt.get("host")):
        errors.append("host_receipt.host_missing")
    if not _text(host_receipt.get("model")):
        errors.append("host_receipt.model_missing")
    if not _text(host_receipt.get("session_id")):
        errors.append("host_receipt.session_id_missing")

    runtime = host_receipt.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
        errors.append("host_receipt.runtime_missing")
    for field in ("tokens_total", "tool_calls", "wall_seconds"):
        value = runtime.get(field)
        valid = _non_negative_number(value)
        if field in {"tokens_total", "tool_calls"}:
            valid = _non_negative_integer(value)
        if not valid:
            errors.append(f"host_receipt.runtime_{field}_invalid")

    budget_usage = host_receipt.get("budget_usage")
    if not isinstance(budget_usage, dict):
        budget_usage = {}
        errors.append("host_receipt.budget_usage_missing")
    else:
        for name, value in budget_usage.items():
            if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
                errors.append("host_receipt.budget_dimension_invalid")
            if not _non_negative_integer(value):
                errors.append(f"host_receipt.budget_usage_invalid:{name}")
    for field in ("tokens_total", "tool_calls", "wall_seconds"):
        if field not in budget_usage:
            errors.append(f"host_receipt.budget_usage_missing:{field}")
        if field in runtime and field in budget_usage and runtime[field] != budget_usage[field]:
            errors.append(f"host_receipt.runtime_budget_mismatch:{field}")

    raw_session = host_receipt.get("raw_session")
    if not isinstance(raw_session, dict):
        errors.append("host_receipt.raw_session_missing")
    else:
        raw_path = _inside(
            path.resolve().parent,
            raw_session.get("path"),
            "host_receipt.raw_session_path_invalid",
            errors,
        )
        raw_sha = _text(raw_session.get("sha256"))
        if not SHA_RE.fullmatch(raw_sha):
            errors.append("host_receipt.raw_session_sha256_invalid")
        elif raw_path is not None:
            if not raw_path.is_file():
                errors.append("host_receipt.raw_session_missing")
            elif sha256_file(raw_path) != raw_sha:
                errors.append("host_receipt.raw_session_sha256_mismatch")
    return host_receipt


def _validate_method_identity(
    method: Any,
    *,
    skill_path: Path,
    active_skill_path: Path,
    errors: list[str],
) -> None:
    """Bind the canonical Skill, actual loaded Skill, and selected profile."""
    if not isinstance(method, dict):
        errors.append("receipt.method_missing")
        return

    expected_canonical_sha = _text(method.get("canonical_skill_sha256"))
    if not SHA_RE.fullmatch(expected_canonical_sha):
        errors.append("method.canonical_skill_sha256_invalid")
    if not skill_path.is_file():
        errors.append("method.canonical_skill_file_missing")
    elif (
        SHA_RE.fullmatch(expected_canonical_sha)
        and sha256_file(skill_path) != expected_canonical_sha
    ):
        errors.append("method.canonical_skill_sha256_mismatch")

    profile = method.get("profile")
    if not isinstance(profile, dict):
        profile = {}
        errors.append("method.profile_missing")
    profile_name = _text(profile.get("name"))
    expected_profile_sha = _text(profile.get("sha256"))
    if not profile_name:
        errors.append("method.profile_name_missing")
    if not SHA_RE.fullmatch(expected_profile_sha):
        errors.append("method.profile_sha256_invalid")
    if skill_path.is_file() and profile_name:
        try:
            actual_profile = profile_identity(skill_path.parent, profile_name)
        except (IdentityError, OSError):
            errors.append("method.profile_files_invalid")
        else:
            if (
                SHA_RE.fullmatch(expected_profile_sha)
                and actual_profile["sha256"] != expected_profile_sha
            ):
                errors.append("method.profile_sha256_mismatch")

    active = method.get("active")
    if not isinstance(active, dict):
        active = {}
        errors.append("method.active_missing")
    expected_locator = _text(active.get("locator"))
    expected_active_sha = _text(active.get("skill_sha256"))
    expected_active_profile_sha = _text(active.get("profile_sha256"))
    if not expected_locator:
        errors.append("method.active_locator_missing")
    elif expected_locator != file_locator(active_skill_path):
        errors.append("method.active_locator_mismatch")
    if not SHA_RE.fullmatch(expected_active_sha):
        errors.append("method.active_skill_sha256_invalid")
    if not active_skill_path.is_file():
        errors.append("method.active_skill_file_missing")
    elif (
        SHA_RE.fullmatch(expected_active_sha)
        and sha256_file(active_skill_path) != expected_active_sha
    ):
        errors.append("method.active_skill_sha256_mismatch")
    if not SHA_RE.fullmatch(expected_active_profile_sha):
        errors.append("method.active_profile_sha256_invalid")
    if active_skill_path.is_file() and profile_name:
        try:
            actual_active_profile = profile_identity(active_skill_path.parent, profile_name)
        except (IdentityError, OSError):
            errors.append("method.active_profile_files_invalid")
        else:
            if (
                SHA_RE.fullmatch(expected_active_profile_sha)
                and actual_active_profile["sha256"] != expected_active_profile_sha
            ):
                errors.append("method.active_profile_sha256_mismatch")

    if (
        SHA_RE.fullmatch(expected_canonical_sha)
        and SHA_RE.fullmatch(expected_active_sha)
        and expected_canonical_sha != expected_active_sha
    ):
        errors.append("method.active_skill_not_canonical")
    if (
        SHA_RE.fullmatch(expected_profile_sha)
        and SHA_RE.fullmatch(expected_active_profile_sha)
        and expected_profile_sha != expected_active_profile_sha
    ):
        errors.append("method.active_profile_not_canonical")


def validate_receipt(
    receipt: Any,
    *,
    receipt_path: Path,
    skill_path: Path,
    active_skill_path: Path | None = None,
    strict: bool = False,
) -> tuple[list[str], list[str]]:
    """Return stable error and warning codes for one receipt."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(receipt, dict):
        return ["receipt.not_object"], warnings
    if receipt.get("schema_version") != SCHEMA_VERSION:
        errors.append("receipt.schema_version_invalid")

    _validate_method_identity(
        receipt.get("method"),
        skill_path=skill_path.resolve(),
        active_skill_path=(active_skill_path or skill_path).resolve(),
        errors=errors,
    )

    report = receipt.get("report")
    if not isinstance(report, dict):
        report = {}
        errors.append("receipt.report_missing")
    receipt_dir = receipt_path.resolve().parent
    report_path = _inside(receipt_dir, report.get("path"), "report.path_invalid", errors)
    report_text = ""
    if report_path is not None:
        if not report_path.is_file():
            errors.append("report.file_missing")
        else:
            try:
                report_text = report_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append("report.not_utf8")
            expected_report_sha = _text(report.get("sha256"))
            if not SHA_RE.fullmatch(expected_report_sha):
                errors.append("report.sha256_invalid")
            elif sha256_file(report_path) != expected_report_sha:
                errors.append("report.sha256_mismatch")
    as_of = _date(report.get("as_of"), "report.as_of_invalid", errors)
    if as_of is not None and report_text and as_of.isoformat() not in report_text:
        errors.append("report.as_of_marker_missing")

    runtime = receipt.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
        errors.append("receipt.runtime_missing")
    for field in ("host", "model"):
        if not _text(runtime.get(field)):
            errors.append(f"runtime.{field}_missing")
    declared_usage: dict[str, int | float] = {}
    for field in ("tokens_total", "tool_calls", "wall_seconds"):
        value = runtime.get(field)
        if value is None:
            continue
        valid = _non_negative_number(value)
        if field in {"tokens_total", "tool_calls"}:
            valid = _non_negative_integer(value)
        if valid:
            declared_usage[field] = value
        else:
            errors.append(f"runtime.{field}_invalid")

    budget = receipt.get("budget")
    budget_items: dict[str, dict[str, Any]] = {}
    if not isinstance(budget, dict) or not budget:
        errors.append("receipt.budget_missing")
    else:
        for name, item in budget.items():
            if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
                errors.append("budget.dimension_invalid")
                continue
            if not isinstance(item, dict):
                errors.append(f"budget.shape_invalid:{name}")
                continue
            budget_items[name] = item
            used, limit = item.get("used"), item.get("limit")
            if used is not None and not _non_negative_integer(used):
                errors.append(f"budget.used_invalid:{name}")
            if not _non_negative_integer(limit):
                errors.append(f"budget.limit_invalid:{name}")
            if (
                _non_negative_integer(used)
                and _non_negative_integer(limit)
                and used > limit
            ):
                errors.append(f"budget.exceeded:{name}")
            metric = item.get("metric", name)
            if not isinstance(metric, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", metric):
                errors.append(f"budget.metric_invalid:{name}")

    artifacts = receipt.get("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
        errors.append("receipt.artifacts_invalid")
    artifact_paths: dict[str, Path] = {}
    for role, item in artifacts.items():
        if not isinstance(role, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", role):
            errors.append("artifact.role_invalid")
            continue
        if not isinstance(item, dict):
            errors.append(f"artifact.shape_invalid:{role}")
            continue
        artifact_path = _inside(
            receipt_dir, item.get("path"), f"artifact.path_invalid:{role}", errors
        )
        if artifact_path is not None:
            artifact_paths[role] = artifact_path
        artifact_sha = _text(item.get("sha256"))
        if not SHA_RE.fullmatch(artifact_sha):
            errors.append(f"artifact.sha256_invalid:{role}")
        elif artifact_path is not None:
            if not artifact_path.is_file():
                errors.append(f"artifact.file_missing:{role}")
            elif sha256_file(artifact_path) != artifact_sha:
                errors.append(f"artifact.sha256_mismatch:{role}")
    if strict:
        for role in ("prompt", "host_receipt"):
            if role not in artifacts:
                errors.append(f"artifact.required:{role}")

    host_receipt: dict[str, Any] | None = None
    host_receipt_path = artifact_paths.get("host_receipt")
    if host_receipt_path is not None and host_receipt_path.is_file():
        host_receipt = _load_host_receipt(host_receipt_path, errors)

    if host_receipt is None:
        if declared_usage:
            errors.append("runtime.metrics_without_host_receipt")
        if any(item.get("used") is not None for item in budget_items.values()):
            errors.append("budget.usage_without_host_receipt")
        if not strict:
            warnings.append("runtime.host_receipt_missing")
    else:
        host_name = _text(host_receipt.get("host"))
        host_model = _text(host_receipt.get("model"))
        if _text(runtime.get("host")) != host_name:
            errors.append("runtime.host_mismatch")
        if _text(runtime.get("model")) != host_model:
            errors.append("runtime.model_mismatch")
        host_runtime = host_receipt.get("runtime")
        if not isinstance(host_runtime, dict):
            host_runtime = {}
        for field, declared_value in declared_usage.items():
            if host_runtime.get(field) != declared_value:
                errors.append(f"runtime.{field}_host_mismatch")
        host_budget = host_receipt.get("budget_usage")
        if not isinstance(host_budget, dict):
            host_budget = {}
        for name, item in budget_items.items():
            metric = item.get("metric", name)
            if not isinstance(metric, str) or metric not in host_budget:
                errors.append(f"budget.host_metric_missing:{name}")
                continue
            actual_used = host_budget[metric]
            declared_used = item.get("used")
            if declared_used is not None and declared_used != actual_used:
                errors.append(f"budget.used_host_mismatch:{name}")
            limit = item.get("limit")
            if _non_negative_integer(actual_used) and _non_negative_integer(limit) and actual_used > limit:
                errors.append(f"budget.exceeded:{name}")

    raw_sources = receipt.get("sources")
    if not isinstance(raw_sources, list):
        raw_sources = []
        errors.append("receipt.sources_missing")
    sources: dict[str, dict[str, Any]] = {}
    source_temporal: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_sources):
        prefix = f"source[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}.not_object")
            continue
        source_id = _text(item.get("source_id"))
        if not ID_RE.fullmatch(source_id):
            errors.append(f"{prefix}.id_invalid")
            continue
        if source_id in sources:
            errors.append(f"source.id_duplicate:{source_id}")
            continue
        sources[source_id] = item
        locator = _text(item.get("locator"))
        if not locator.startswith(("https://", "http://", "packet://")):
            errors.append(f"source.locator_invalid:{source_id}")
        if not _text(item.get("publisher")):
            errors.append(f"source.publisher_missing:{source_id}")
        temporal_basis = item.get("temporal_basis")
        if temporal_basis is None:
            errors.append(f"source.temporal_basis_missing:{source_id}")
            temporal_basis = ""
        elif temporal_basis not in TEMPORAL_BASES:
            errors.append(f"source.temporal_basis_invalid:{source_id}")
            temporal_basis = ""

        published_at = _optional_date(
            item.get("published_at"), f"source.published_at_invalid:{source_id}", errors
        )
        retrieved_at = _date(
            item.get("retrieved_at"), f"source.retrieved_at_invalid:{source_id}", errors
        )
        coverage_through = _optional_date(
            item.get("coverage_through"),
            f"source.coverage_through_invalid:{source_id}",
            errors,
        )
        evidence_date = None
        date_evidence = item.get("date_evidence")
        if temporal_basis in HISTORICAL_TEMPORAL_BASES:
            if not isinstance(date_evidence, dict):
                errors.append(f"source.publication_evidence_missing:{source_id}")
            else:
                evidence_kind = date_evidence.get("kind")
                evidence_date = _date(
                    date_evidence.get("value"),
                    f"source.publication_evidence_date_invalid:{source_id}",
                    errors,
                )
                if evidence_kind not in DATE_EVIDENCE_KINDS:
                    errors.append(f"source.publication_evidence_kind_invalid:{source_id}")
                if not _text(date_evidence.get("anchor")):
                    errors.append(f"source.publication_evidence_anchor_missing:{source_id}")
                expected_kinds = {
                    "DATED_PUBLICATION": {"DOCUMENT_DATE", "DOCUMENT_METADATA"},
                    "VERSIONED_ARTIFACT": {
                        "DOCUMENT_DATE",
                        "DOCUMENT_METADATA",
                        "VERSION_LABEL",
                    },
                    "ARCHIVED_SNAPSHOT": {"ARCHIVE_TIMESTAMP"},
                }
                if evidence_kind not in expected_kinds.get(temporal_basis, set()):
                    errors.append(f"source.publication_evidence_kind_ineligible:{source_id}")
        elif date_evidence is not None and not isinstance(date_evidence, dict):
            errors.append(f"source.publication_evidence_invalid:{source_id}")

        if temporal_basis in {"DATED_PUBLICATION", "VERSIONED_ARTIFACT"}:
            if published_at is None:
                errors.append(f"source.published_at_missing:{source_id}")
            if (
                published_at is not None
                and evidence_date is not None
                and published_at != evidence_date
            ):
                errors.append(f"source.publication_evidence_mismatch:{source_id}")
        if as_of is not None and published_at is not None and published_at > as_of:
            errors.append(f"source.after_as_of:{source_id}")
        if (
            as_of is not None
            and temporal_basis == "ARCHIVED_SNAPSHOT"
            and evidence_date is not None
            and evidence_date > as_of
        ):
            errors.append(f"source.after_as_of:{source_id}")
        if (
            as_of is not None
            and temporal_basis == "LIVE_CURRENT"
            and retrieved_at is not None
            and retrieved_at > as_of
        ):
            errors.append(f"source.live_current_after_as_of:{source_id}")
        source_temporal[source_id] = {
            "basis": temporal_basis,
            "published_at": published_at,
            "retrieved_at": retrieved_at,
            "coverage_through": coverage_through,
            "evidence_date": evidence_date,
        }
        if not _text(item.get("lineage_key")):
            errors.append(f"source.lineage_key_missing:{source_id}")
        if item.get("kind") not in SOURCE_KINDS:
            errors.append(f"source.kind_invalid:{source_id}")

        snapshot_path_raw = item.get("snapshot_path")
        snapshot_sha = _text(item.get("snapshot_sha256"))
        has_snapshot_path = isinstance(snapshot_path_raw, str) and bool(snapshot_path_raw)
        has_snapshot_sha = bool(snapshot_sha)
        if has_snapshot_path != has_snapshot_sha:
            errors.append(f"source.snapshot_pair_incomplete:{source_id}")
        elif has_snapshot_path:
            snapshot_path = _inside(
                receipt_dir,
                snapshot_path_raw,
                f"source.snapshot_path_invalid:{source_id}",
                errors,
            )
            if not SHA_RE.fullmatch(snapshot_sha):
                errors.append(f"source.snapshot_sha256_invalid:{source_id}")
            elif snapshot_path is not None:
                if not snapshot_path.is_file():
                    errors.append(f"source.snapshot_missing:{source_id}")
                elif sha256_file(snapshot_path) != snapshot_sha:
                    errors.append(f"source.snapshot_sha256_mismatch:{source_id}")
        elif strict:
            errors.append(f"source.snapshot_required:{source_id}")

    raw_claims = receipt.get("claims")
    if not isinstance(raw_claims, list) or not raw_claims:
        raw_claims = []
        errors.append("receipt.claims_missing")
    claim_ids: set[str] = set()
    referenced_sources: set[str] = set()
    for index, item in enumerate(raw_claims):
        prefix = f"claim[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}.not_object")
            continue
        claim_id = _text(item.get("claim_id"))
        if not ID_RE.fullmatch(claim_id):
            errors.append(f"{prefix}.id_invalid")
            continue
        if claim_id in claim_ids:
            errors.append(f"claim.id_duplicate:{claim_id}")
            continue
        claim_ids.add(claim_id)
        if report_text and f"[{claim_id}]" not in report_text:
            errors.append(f"claim.marker_missing:{claim_id}")

        boundary = item.get("boundary")
        if boundary not in BOUNDARIES:
            errors.append(f"claim.boundary_invalid:{claim_id}")
            boundary = ""
        temporal_mode = item.get("temporal_mode")
        if temporal_mode not in TEMPORAL_MODES:
            errors.append(f"claim.temporal_mode_invalid:{claim_id}")
            temporal_mode = ""
        source_ids = item.get("source_ids")
        if not isinstance(source_ids, list) or any(not isinstance(value, str) for value in source_ids):
            errors.append(f"claim.source_ids_invalid:{claim_id}")
            source_ids = []
        if len(source_ids) != len(set(source_ids)):
            errors.append(f"claim.source_ids_duplicate:{claim_id}")
        unknown = sorted(set(source_ids) - set(sources))
        for source_id in unknown:
            errors.append(f"claim.source_unknown:{claim_id}:{source_id}")
        known_sources = [sources[source_id] for source_id in source_ids if source_id in sources]
        referenced_sources.update(source_id for source_id in source_ids if source_id in sources)

        for source_id in source_ids:
            temporal = source_temporal.get(source_id)
            if temporal is None:
                continue
            basis = temporal["basis"]
            if temporal_mode == "EVENT_BY_DATE":
                effective_date = temporal["published_at"] or temporal["evidence_date"]
                if basis not in HISTORICAL_TEMPORAL_BASES or effective_date is None:
                    errors.append(
                        f"claim.temporal_source_ineligible:{claim_id}:{source_id}"
                    )
            elif temporal_mode in {"STATE_AT_AS_OF", "ABSENCE_BY_AS_OF"}:
                if basis not in HISTORICAL_TEMPORAL_BASES:
                    errors.append(
                        f"claim.temporal_source_ineligible:{claim_id}:{source_id}"
                    )
                coverage = temporal["coverage_through"]
                if coverage is None:
                    errors.append(f"claim.temporal_coverage_missing:{claim_id}:{source_id}")
                elif as_of is not None and coverage < as_of:
                    errors.append(
                        f"claim.temporal_coverage_before_as_of:{claim_id}:{source_id}"
                    )

        if boundary in {"FACT", "SINGLE_SOURCE", "INFERENCE", "NO_RESULT"} and not known_sources:
            errors.append(f"claim.sources_required:{claim_id}")
        if boundary == "FACT" and known_sources:
            distinct_lineages = {_text(source.get("lineage_key")) for source in known_sources}
            has_direct_source = any(
                source.get("kind") in {"PRIMARY", "DATA"} for source in known_sources
            )
            if not has_direct_source and len(distinct_lineages - {""}) < 2:
                errors.append(f"claim.fact_independence_insufficient:{claim_id}")
        if boundary == "NO_RESULT":
            no_result = item.get("no_result")
            if not isinstance(no_result, dict):
                errors.append(f"claim.no_result_scope_missing:{claim_id}")
            else:
                for field in ("queries", "locations"):
                    value = no_result.get(field)
                    if not isinstance(value, list) or not value or any(not _text(entry) for entry in value):
                        errors.append(f"claim.no_result_{field}_invalid:{claim_id}")
                date_from = _date(
                    no_result.get("date_from"), f"claim.no_result_date_from_invalid:{claim_id}", errors
                )
                date_to = _date(
                    no_result.get("date_to"), f"claim.no_result_date_to_invalid:{claim_id}", errors
                )
                if date_from is not None and date_to is not None and date_from > date_to:
                    errors.append(f"claim.no_result_date_range_invalid:{claim_id}")
                if as_of is not None and date_to is not None and date_to > as_of:
                    errors.append(f"claim.no_result_after_as_of:{claim_id}")
            if known_sources and not any(
                source.get("kind") in {"INDEX", "PRIMARY"} for source in known_sources
            ):
                errors.append(f"claim.no_result_index_missing:{claim_id}")
        if boundary == "INSUFFICIENT" and not _text(item.get("gap")):
            errors.append(f"claim.insufficient_gap_missing:{claim_id}")

    for source_id in sorted(set(sources) - referenced_sources):
        errors.append(f"source.orphan:{source_id}")
    if report_text:
        for source_id in sources:
            if f"[{source_id}]" not in report_text:
                errors.append(f"source.marker_missing:{source_id}")

    return sorted(set(errors)), sorted(set(warnings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Resanity audit receipt without judging its conclusion."
    )
    parser.add_argument("receipt", help="path to a resanity.audit-receipt.v2 JSON file")
    parser.add_argument("--skill", default=str(ROOT / "SKILL.md"), help="exact SKILL.md to hash-bind")
    parser.add_argument(
        "--active-skill",
        help="actual SKILL.md locator loaded by the host (defaults to --skill)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="require source snapshots and measured token/tool/time usage (for formal validation)",
    )
    parser.add_argument("--json", action="store_true", help="emit one machine-readable JSON object")
    args = parser.parse_args(argv)

    receipt_path = Path(args.receipt)
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        result = {"ok": False, "errors": ["receipt.file_missing"], "warnings": []}
    except (UnicodeDecodeError, json.JSONDecodeError):
        result = {"ok": False, "errors": ["receipt.json_invalid"], "warnings": []}
    else:
        errors, warnings = validate_receipt(
            receipt,
            receipt_path=receipt_path,
            skill_path=Path(args.skill),
            active_skill_path=Path(args.active_skill) if args.active_skill else None,
            strict=args.strict,
        )
        result = {"ok": not errors, "errors": errors, "warnings": warnings}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif result["ok"]:
        print(f"AUDIT_RECEIPT_OK ({len(result['warnings'])} warning(s))")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("AUDIT_RECEIPT_FAILED")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
