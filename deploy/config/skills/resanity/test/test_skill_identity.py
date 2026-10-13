from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.skill_identity import IdentityError, profile_identity, resolve_identity


class SkillIdentityTests(unittest.TestCase):
    def make_skill(self, root: Path, text: str = "# canonical\n", *, references: bool = True) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        skill = root / "SKILL.md"
        skill.write_text(text, encoding="utf-8")
        if references:
            refs = root / "references"
            refs.mkdir()
            (refs / "investing.md").write_text("# investing\n", encoding="utf-8")
            (refs / "anchors.md").write_text("# anchors\n", encoding="utf-8")
            (refs / "formal-audit.md").write_text("# formal\n", encoding="utf-8")
        return skill

    def test_profile_hash_binds_only_selected_references(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "canonical"
            self.make_skill(root)
            core_before = profile_identity(root, "core")["sha256"]
            investing_before = profile_identity(root, "investing")["sha256"]
            (root / "references/investing.md").write_text("changed\n", encoding="utf-8")
            self.assertEqual(profile_identity(root, "core")["sha256"], core_before)
            self.assertNotEqual(
                profile_identity(root, "investing")["sha256"], investing_before
            )

    def test_host_reported_locator_overrides_discovered_project_copy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            canonical_root = base / "canonical"
            canonical_skill = self.make_skill(canonical_root)
            project_skill = self.make_skill(
                base / "workspace/.codex/skills/resanity", "# drift\n"
            )
            result = resolve_identity(
                canonical_root=canonical_root,
                profile="core",
                host="codex",
                cwd=base / "workspace",
                user_home=base / "home",
                dsh_home=base / "dsh",
                active_skill=canonical_skill,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["resolution"], "host-reported")
            self.assertNotEqual(result["active"]["locator"], project_skill.as_uri())

    def test_project_copy_shadows_user_and_fails_when_drifted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            canonical_root = base / "canonical"
            self.make_skill(canonical_root)
            project_skill = self.make_skill(
                base / "workspace/.dsh/skills/resanity", "# drift\n"
            )
            self.make_skill(base / "home/.agents/skills/resanity")
            result = resolve_identity(
                canonical_root=canonical_root,
                profile="core",
                host="dsh",
                cwd=base / "workspace",
                user_home=base / "home",
                dsh_home=base / "dsh-home",
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["active"]["locator"], project_skill.resolve().as_uri())
            self.assertEqual(result["active"]["scope"], "project")

    def test_missing_profile_reference_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            canonical_root = base / "canonical"
            self.make_skill(canonical_root)
            active = self.make_skill(base / "active", references=False)
            result = resolve_identity(
                canonical_root=canonical_root,
                profile="investing",
                host="generic",
                cwd=base,
                user_home=base,
                dsh_home=base,
                active_skill=active,
            )
            self.assertFalse(result["ok"])
            self.assertIn("profile_error", result["active"])

    def test_unknown_profile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.make_skill(root)
            with self.assertRaises(IdentityError):
                profile_identity(root, "unknown")


if __name__ == "__main__":
    unittest.main()
