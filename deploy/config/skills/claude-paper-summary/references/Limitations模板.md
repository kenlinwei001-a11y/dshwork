## Limitations
- [Limitation 1]
- [Limitation 2]
```

**Guidelines for each section:**

| Section | Length | Focus |
|---------|--------|-------|
| One Sentence | 1 sentence | High-level summary |
| Problem | 2-3 sentences | Context and motivation |
| Core Idea | 2-3 sentences | The main innovation |
| Key Contributions | 3-5 bullets | What's new/novel |
| Main Results | 1 table | Quantitative metrics from the paper |
| Why It Matters | 2-3 sentences | Practical value |
| Limitations | 2-3 bullets | What the paper doesn't solve |

**Total length:** ~300-500 words (excluding results table)

---

# Step 3: Update Index

**CRITICAL**: Read existing index.json first, then append the new paper. Never overwrite the entire file.

If index.json does not exist, create:

```json
{"papers": []}
```

Append new entry to the papers array:

```json
{
  "id": "paper-slug",
  "title": "Paper Title",
  "slug": "paper-slug",
  "authors": ["Author 1", "Author 2"],
  "abstract": "Paper abstract...",
  "year": 2024,
  "date": "2024-01-01",
  "tags": ["quick-summary"],
  "githubLinks": ["https://github.com/..."],
  "codeLinks": ["https://..."]
}
```

**IMPORTANT**: The index.json file must be located at:
```
~/claude-papers/index.json
```

---

# Step 4: Relaunch Web UI

Load and follow the `claude-paper-webui` skill.

---

# Step 5: Present Summary to User

After generating the summary:

1. **Show the user the quick-summary.md content** - Display the full summary

2. **Offer next steps:**
   - "Would you like to study this paper in more depth? Use `claude-paper-study` skill for comprehensive materials."
   - "Do you have questions about specific parts of the paper?"
   - "Would you like me to explain any section in more detail?"

3. **File location reminder:**
   - Summary saved to: `~/claude-papers/papers/{paper-slug}/quick-summary.md`
   - Web UI available at: `http://localhost:5815`

---

# Example Output

```markdown
# Quick Summary: Attention Is All You Need
