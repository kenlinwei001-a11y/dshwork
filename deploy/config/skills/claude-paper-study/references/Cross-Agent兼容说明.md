## Cross-Agent Compatibility

> This file is generated from the existing Claude Paper Skill. Its workflow and output requirements are unchanged; only equivalent host metadata, the plugin-root variable, and cross-skill invocation are adapted.

Resolve `CLAUDE_PAPER_PLUGIN_ROOT` to the absolute `plugin/` directory in this package before each shell invocation. From this `SKILL.md`, that directory is `../../plugin`.
Treat every `${CLAUDE_PAPER_PLUGIN_ROOT}` reference below as that resolved absolute directory. Do not substitute the current workspace root.

When this workflow asks to launch the viewer, load and follow the `claude-paper-webui` skill.

---

# Paper Study Workflow

Invoke this skill with a paper PDF path.

**Language Detection**: Detect the user's language from their input and generate ALL materials in that language.
- Example: User says "我们学习一下这篇论文吧" → Generate materials in Chinese
- Example: User says "Let's study this paper" → Generate materials in English

---

# Core Philosophy

Primary Objective:
Facilitate deep conceptual understanding and research-level thinking.

Secondary Objective:
Create a structured, reusable paper knowledge system.

This workflow is not just for summarizing — it builds a learning environment around the paper.

---

# Step 0: Check Dependencies (First Run Only)

```bash
if [ ! -f "${CLAUDE_PAPER_PLUGIN_ROOT}/.installed" ]; then
  echo "First run - installing dependencies..."
  cd "${CLAUDE_PAPER_PLUGIN_ROOT}"
  npm install || exit 1

  # Install Python dependencies for image extraction
  python3 -m pip install pymupdf --user 2>/dev/null || pip3 install pymupdf --user 2>/dev/null || echo "Warning: Failed to install pymupdf"

  touch "${CLAUDE_PAPER_PLUGIN_ROOT}/.installed"
  echo "Dependencies installed!"
fi
```

Recommended:

* Node >= 18
* Python 3 with pip (for image extraction)

---

# Step 1: Download and Parse PDF

Supports multiple input formats:

* **Local path**: `~/Downloads/paper.pdf`
* **Direct PDF URL**: `https://arxiv.org/pdf/1706.03762.pdf`
* **arXiv URL**: `https://arxiv.org/abs/1706.03762`
