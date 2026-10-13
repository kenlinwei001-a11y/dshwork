import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = "0.2.1"
INTERNAL_CANDIDATE_PATTERN = re.compile(r"\b2[.]0[.]0-rc[.][1-3]\b|\bRC[1-3]\b")


class ReleaseTreeTests(unittest.TestCase):
    def test_public_version_is_consistent(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["version"], RELEASE_VERSION)

        for relative in ("README.md", "ARCHITECTURE.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(RELEASE_VERSION, text, relative)
            self.assertNotIn("0.2." + "0", text, relative)
            self.assertIsNone(INTERNAL_CANDIDATE_PATTERN.search(text), relative)

    def test_historical_material_is_not_in_current_tree(self) -> None:
        tracked = set(
            subprocess.check_output(
                ["git", "ls-files"], cwd=ROOT, text=True
            ).splitlines()
        )
        forbidden = (
            "PLAN-0.1.0.md",
            "EXAMPLES.md",
            "validation/dsh-pilot",
            "validation/dsh-full",
            "validation/v2/runs",
            "validation/v2/run-targeted-bridge-dsh.sh",
            "anchors/README.md",
            "journal/weekly-review.md",
            "assets/social-preview.jpg",
        )
        for relative in forbidden:
            self.assertFalse(
                any(path == relative or path.startswith(f"{relative}/") for path in tracked),
                relative,
            )

    def test_public_docs_do_not_expose_internal_candidate_versions(self) -> None:
        for relative in (
            "README.md",
            "ARCHITECTURE.md",
            "validation/README.md",
            "validation/v2/README.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIsNone(INTERNAL_CANDIDATE_PATTERN.search(text), relative)


if __name__ == "__main__":
    unittest.main()
