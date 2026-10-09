#!/usr/bin/env python3
"""Validate the current reusable validation source contract.

This command does not invoke a model, score semantics, or create a pass result
for any semantic validation layer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = ROOT / "validation/v2/suite.json"
EXPECTED_LAYERS = (
    "core_contract",
    "investing_profile",
    "open_network",
    "anchor",
    "trigger",
    "install_identity",
    "final_ab",
)
SEMANTIC_LAYERS = ("core_contract", "investing_profile", "open_network", "anchor")
ALLOWED_PROFILES = {"core", "investing", "anchors", "formal-audit"}


class ContractError(ValueError):
    pass


def read_suite() -> dict[str, Any]:
    try:
        value = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"invalid validation suite: {error}") from error
    if not isinstance(value, dict):
        raise ContractError("validation suite root must be an object")
    return value


def validate_protocol(suite: dict[str, Any]) -> dict[str, Any]:
    if not (SUITE_PATH.parent / "run_validation.py").is_file():
        raise ContractError("v2 mechanical validation runner missing")
    if not (SUITE_PATH.parent / "run_final_ab.py").is_file():
        raise ContractError("v2 final A/B collection runner missing")
    if not (SUITE_PATH.parent / "run_final_ab_dsh.py").is_file():
        raise ContractError("v2 DSH final A/B collection runner missing")
    if not (SUITE_PATH.parent / "run_dsh_prelayers.py").is_file():
        raise ContractError("v2 DSH prelayer collection runner missing")
    try:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"package.json invalid: {error}") from error
    scripts = package.get("scripts") if isinstance(package, dict) else None
    if not isinstance(scripts, dict) or scripts.get("validate:v2:ab:dsh") != (
        "python3 validation/v2/run_final_ab_dsh.py"
    ):
        raise ContractError("v2 DSH final A/B npm entry missing or changed")
    if scripts.get("validate:v2:prelayers:dsh") != (
        "python3 validation/v2/run_dsh_prelayers.py"
    ):
        raise ContractError("v2 DSH prelayer npm entry missing or changed")
    prelayers_template_path = SUITE_PATH.parent / "prelayers-receipt-template.json"
    try:
        prelayers_template = json.loads(prelayers_template_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"v2 prelayer receipt template invalid: {error}") from error
    if (
        prelayers_template.get("schema_version") != "resanity.prelayers-receipt.v2"
        or prelayers_template.get("status") != "NOT_RUN"
    ):
        raise ContractError("v2 prelayer receipt template must remain NOT_RUN")
    profile_hashes = prelayers_template.get("candidate_profiles_sha256")
    if not isinstance(profile_hashes, dict) or set(profile_hashes) != {
        "core",
        "investing",
        "anchors",
        "formal-audit",
    }:
        raise ContractError("v2 prelayer receipt template profile hashes incomplete")
    template_layers = prelayers_template.get("layers")
    required_prelayers = {
        "core_contract",
        "investing_profile",
        "open_network",
        "anchor",
        "trigger",
        "install_identity",
    }
    if (
        not isinstance(template_layers, dict)
        or set(template_layers) != required_prelayers
        or any(value != "NOT_RUN" for value in template_layers.values())
    ):
        raise ContractError("v2 prelayer receipt template layers must remain NOT_RUN")
    if suite.get("schema") != "resanity.validation-suite.v2":
        raise ContractError("v2 suite schema mismatch")
    if suite.get("method_status") != "UNBENCHMARKED_CURRENT":
        raise ContractError("method status must remain UNBENCHMARKED_CURRENT")
    if suite.get("result_status") != "NOT_RUN":
        raise ContractError("suite result must remain NOT_RUN before real validation")
    layers = suite.get("layers")
    if not isinstance(layers, dict) or tuple(layers) != EXPECTED_LAYERS:
        raise ContractError(f"v2 layers must be ordered as {EXPECTED_LAYERS}")

    case_ids: set[str] = set()
    case_prompts: dict[str, Path] = {}
    semantic_counts: dict[str, int] = {}
    for layer_name in SEMANTIC_LAYERS:
        layer = layers[layer_name]
        if layer.get("result_status") != "NOT_RUN":
            raise ContractError(f"{layer_name} must remain NOT_RUN")
        cases = layer.get("cases")
        if not isinstance(cases, list) or not cases:
            raise ContractError(f"{layer_name} cases missing")
        semantic_counts[layer_name] = len(cases)
        for case in cases:
            if not isinstance(case, dict):
                raise ContractError(f"{layer_name} case is not an object")
            case_id = case.get("id")
            prompt = case.get("prompt")
            profile = case.get("profile")
            if not isinstance(case_id, str) or not case_id or case_id in case_ids:
                raise ContractError(f"invalid or duplicate case id: {case_id!r}")
            case_ids.add(case_id)
            if profile not in ALLOWED_PROFILES:
                raise ContractError(f"{case_id}: invalid profile {profile!r}")
            if not isinstance(prompt, str) or not (SUITE_PATH.parent / prompt).is_file():
                raise ContractError(f"{case_id}: prompt missing")
            case_prompts[case_id] = SUITE_PATH.parent / prompt

    trigger_cases = layers["trigger"].get("cases")
    if not isinstance(trigger_cases, list) or len(trigger_cases) < 8:
        raise ContractError("trigger matrix too small")
    positives = [case for case in trigger_cases if case.get("expected_invocation") is True]
    negatives = [case for case in trigger_cases if case.get("expected_invocation") is False]
    reasons = {case.get("reason") for case in trigger_cases}
    required_reasons = {
        "investment-auto",
        "explicit-non-investing",
        "ordinary-summary",
        "ordinary-coding",
        "ordinary-writing",
    }
    if not positives or not negatives or not required_reasons.issubset(reasons):
        raise ContractError("trigger matrix lacks required positive/negative categories")
    delivery_regressions = [
        case for case in trigger_cases if isinstance(case.get("delivery_regression"), dict)
    ]
    if len(delivery_regressions) != 1:
        raise ContractError("trigger matrix must contain one natural delivery regression")
    delivery_contract = delivery_regressions[0]["delivery_regression"]
    expected_delivery_contract = {
        "report_required": True,
        "saved_report_required": False,
        "root_uses_evidence_language": True,
        "one_boundary_per_claim": True,
        "temporal_mode_per_claim": True,
        "one_next_evidence_object": True,
        "profile_loaded_before_research": True,
        "official_index_first_for_ashare": True,
    }
    if delivery_contract != expected_delivery_contract:
        raise ContractError("natural delivery regression contract is incomplete")

    identity_cases = layers["install_identity"].get("cases")
    if not isinstance(identity_cases, list) or len(identity_cases) < 4:
        raise ContractError("install identity matrix too small")

    anchor_cases = layers["anchor"].get("cases")
    anchor_groups: dict[str, list[str]] = {}
    for case in anchor_cases:
        group = case.get("workspace_group")
        if not isinstance(group, str) or not group:
            raise ContractError(f"{case.get('id')}: anchor workspace group missing")
        anchor_groups.setdefault(group, []).append(case["id"])
    if sorted(len(case_ids) for case_ids in anchor_groups.values()) != [2, 2, 2]:
        raise ContractError("anchor lifecycle must contain three two-session groups")
    required_anchor_endings = {"refuted", "realized", "archived"}
    observed_anchor_endings = {
        case_id.rsplit("-", 1)[-1]
        for case_ids in anchor_groups.values()
        for case_id in case_ids[1:]
    }
    if observed_anchor_endings != required_anchor_endings:
        raise ContractError("anchor lifecycle endings must cover refuted/realized/archived")

    final_ab = layers["final_ab"]
    if final_ab.get("result_status") != "NOT_RUN":
        raise ContractError("final A/B must remain NOT_RUN")
    if final_ab.get("paired") is not True or final_ab.get("automatic_retries") != 0:
        raise ContractError("final A/B must be paired and one-shot")
    if final_ab.get("baseline") != "strong-general-research":
        raise ContractError("final A/B baseline must be strong general research")
    baseline_prompt = final_ab.get("baseline_prompt")
    if (
        not isinstance(baseline_prompt, str)
        or not (SUITE_PATH.parent / baseline_prompt).is_file()
    ):
        raise ContractError("final A/B strong baseline prompt missing")
    if final_ab.get("candidate") != "canonical-resanity" or final_ab.get("freeze_required") is not True:
        raise ContractError("final A/B candidate must be canonical and frozen")
    candidate_prompt = final_ab.get("candidate_prompt")
    candidate_prompt_path = (
        SUITE_PATH.parent / candidate_prompt if isinstance(candidate_prompt, str) else None
    )
    if candidate_prompt_path is None or not candidate_prompt_path.is_file():
        raise ContractError("final A/B candidate instruction missing")
    if "$resanity" not in candidate_prompt_path.read_text(encoding="utf-8"):
        raise ContractError("candidate instruction must explicitly invoke $resanity")
    if final_ab.get("task_prompts_neutral") is not True:
        raise ContractError("final A/B task prompts must be declared neutral")
    ab_ids = final_ab.get("case_ids")
    if not isinstance(ab_ids, list) or len(ab_ids) < 8 or set(ab_ids) - case_ids:
        raise ContractError("final A/B case list is incomplete or unknown")
    contamination = (
        "resanity",
        "$resanity",
        "原子主张卡",
        "投资 profile",
        "watch_only",
        "not_evaluable",
        "setup",
    )
    for case_id in ab_ids:
        task_text = case_prompts[case_id].read_text(encoding="utf-8").lower()
        leaked = [marker for marker in contamination if marker in task_text]
        if leaked:
            raise ContractError(
                f"{case_id}: final A/B task prompt leaks candidate method: {', '.join(leaked)}"
            )

    return {
        "layers": list(layers),
        "semantic_case_counts": semantic_counts,
        "trigger_cases": len(trigger_cases),
        "delivery_regression_cases": len(delivery_regressions),
        "identity_cases": len(identity_cases),
        "final_ab_cases": len(ab_ids),
        "final_ab_baseline_prompt": baseline_prompt,
        "final_ab_candidate_prompt": candidate_prompt,
        "final_ab_task_prompts_neutral": True,
        "semantic_status": "NOT_RUN",
    }


def main() -> int:
    try:
        suite = read_suite()
        result = {
            "status": "VALIDATION_SOURCE_OK",
            "protocol": validate_protocol(suite),
        }
    except ContractError as error:
        result = {"status": "VALIDATION_SOURCE_FAILED", "error": str(error)}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
