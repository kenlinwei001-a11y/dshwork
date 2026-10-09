#!/usr/bin/env python3
"""Resolve and hash the active Resanity Skill without interpreting research.

The host-reported locator is authoritative when supplied via --active-skill.
Otherwise this tool applies an explicit, documented candidate order and emits
every candidate so shadowing stays visible. It never installs or edits files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "resanity.skill-identity.v2"
PROFILE_SCHEMA_VERSION = "resanity.method-profile.v2"
ROOT = Path(__file__).resolve().parents[1]
PROFILE_ORDER = ("investing", "anchors", "formal-audit")
PROFILE_REFERENCES = {
    "investing": Path("references/investing.md"),
    "anchors": Path("references/anchors.md"),
    "formal-audit": Path("references/formal-audit.md"),
}


class IdentityError(ValueError):
    """Invalid profile or unresolved Skill identity."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_profile(name: str) -> tuple[str, tuple[Path, ...]]:
    raw_parts = [part.strip() for part in name.split("+") if part.strip()]
    if not raw_parts:
        raise IdentityError("profile is empty")
    unknown = sorted(set(raw_parts) - ({"core"} | set(PROFILE_REFERENCES)))
    if unknown:
        raise IdentityError(f"unknown profile component(s): {', '.join(unknown)}")
    selected = [part for part in PROFILE_ORDER if part in raw_parts]
    normalized = "+".join(selected) if selected else "core"
    files = (Path("SKILL.md"), *(PROFILE_REFERENCES[part] for part in selected))
    return normalized, files


def profile_identity(root: Path, profile: str) -> dict[str, Any]:
    normalized, relative_files = normalize_profile(profile)
    entries = []
    for relative in relative_files:
        path = root / relative
        if not path.is_file():
            raise IdentityError(f"profile file missing: {path}")
        entries.append({"path": relative.as_posix(), "sha256": sha256_file(path)})
    manifest = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "name": normalized,
        "files": entries,
    }
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {**manifest, "sha256": hashlib.sha256(encoded).hexdigest()}


def file_locator(path: Path) -> str:
    return path.resolve().as_uri()


def parse_candidate(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise IdentityError("candidate must use scope=/absolute/path/SKILL.md")
    scope, path_text = raw.split("=", 1)
    scope = scope.strip()
    path = Path(path_text).expanduser()
    if not scope or not path.is_absolute():
        raise IdentityError("candidate scope must be non-empty and path absolute")
    return scope, path


def candidate_paths(
    *,
    host: str,
    cwd: Path,
    user_home: Path,
    dsh_home: Path,
    canonical_skill: Path,
    explicit: list[tuple[str, Path]],
) -> list[tuple[str, Path]]:
    candidates = list(explicit)
    if host == "codex":
        candidates.extend(
            [
                ("project", cwd / ".codex/skills/resanity/SKILL.md"),
                ("user", user_home / ".codex/skills/resanity/SKILL.md"),
            ]
        )
    elif host == "dsh":
        candidates.extend(
            [
                ("project", cwd / ".dsh/skills/resanity/SKILL.md"),
                ("user", dsh_home / "skills/resanity/SKILL.md"),
                ("portable-user", user_home / ".agents/skills/resanity/SKILL.md"),
            ]
        )
    candidates.append(("bundled-canonical", canonical_skill))

    result: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for scope, path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append((scope, resolved))
    return result


def resolve_identity(
    *,
    canonical_root: Path,
    profile: str,
    host: str,
    cwd: Path,
    user_home: Path,
    dsh_home: Path,
    active_skill: Path | None = None,
    explicit_candidates: list[tuple[str, Path]] | None = None,
) -> dict[str, Any]:
    canonical_root = canonical_root.resolve()
    canonical_skill = canonical_root / "SKILL.md"
    if not canonical_skill.is_file():
        raise IdentityError(f"canonical SKILL.md missing: {canonical_skill}")
    canonical_profile = profile_identity(canonical_root, profile)

    if active_skill is not None:
        ordered = [("host-reported", active_skill.resolve())]
        resolution = "host-reported"
    else:
        ordered = candidate_paths(
            host=host,
            cwd=cwd.resolve(),
            user_home=user_home.resolve(),
            dsh_home=dsh_home.resolve(),
            canonical_skill=canonical_skill,
            explicit=explicit_candidates or [],
        )
        resolution = "candidate-precedence"

    candidates = []
    active: dict[str, Any] | None = None
    for scope, path in ordered:
        item: dict[str, Any] = {
            "scope": scope,
            "locator": file_locator(path),
            "exists": path.is_file(),
        }
        if path.is_file():
            item["skill_sha256"] = sha256_file(path)
            try:
                item["profile"] = profile_identity(path.parent, profile)
            except IdentityError as error:
                item["profile_error"] = str(error)
            if active is None:
                active = item
        candidates.append(item)

    if active is None:
        raise IdentityError("no active Resanity SKILL.md candidate exists")
    active_profile = active.get("profile")
    active_profile_sha = (
        active_profile.get("sha256") if isinstance(active_profile, dict) else None
    )
    matches = {
        "skill": active.get("skill_sha256") == sha256_file(canonical_skill),
        "profile": active_profile_sha == canonical_profile["sha256"],
    }
    ok = all(matches.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "host": host,
        "resolution": resolution,
        "precedence": [item["scope"] for item in candidates],
        "canonical": {
            "root": str(canonical_root),
            "locator": file_locator(canonical_skill),
            "skill_sha256": sha256_file(canonical_skill),
            "profile": canonical_profile,
        },
        "active": active,
        "shadowed": [
            item for item in candidates[candidates.index(active) + 1 :] if item["exists"]
        ],
        "candidates": candidates,
        "matches_canonical": matches,
        "receipt_method": {
            "canonical_skill_sha256": sha256_file(canonical_skill),
            "profile": {
                "name": canonical_profile["name"],
                "sha256": canonical_profile["sha256"],
            },
            "active": {
                "locator": active["locator"],
                "skill_sha256": active["skill_sha256"],
                "profile_sha256": active_profile_sha,
            },
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-root", type=Path, default=ROOT)
    parser.add_argument("--profile", default="core")
    parser.add_argument("--host", choices=("codex", "dsh", "generic"), default="generic")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--user-home", type=Path, default=Path.home())
    parser.add_argument(
        "--dsh-home",
        type=Path,
        default=Path(os.environ.get("DSH_HOME", str(Path.home() / ".dsh"))),
    )
    parser.add_argument(
        "--active-skill",
        type=Path,
        help="actual SKILL.md locator reported by the host; disables path guessing",
    )
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="extra high-priority candidate as scope=/absolute/path/SKILL.md",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        explicit = [parse_candidate(raw) for raw in args.candidate]
        result = resolve_identity(
            canonical_root=args.canonical_root,
            profile=args.profile,
            host=args.host,
            cwd=args.cwd,
            user_home=args.user_home,
            dsh_home=args.dsh_home,
            active_skill=args.active_skill,
            explicit_candidates=explicit,
        )
    except (IdentityError, OSError) as error:
        result = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "error": str(error),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
