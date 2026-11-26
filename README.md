# Research Audit Skills

Four AI agent skills for catching **code bugs**, **weak baselines**, **novelty gaps**, and **manuscript issues** before you burn compute or submit a paper.

Works with **Antigravity**, **Claude Code**, and **OpenAI Codex**.

## The 4 Skills

| Skill | When to use it | What it checks |
| :--- | :--- | :--- |
| **`idea-novelty-screen`** | Before writing code | Checks literature novelty, theoretical traps, and cheap baselines; outputs a 1-page Go/Pivot/Kill summary. |
| **`code-math-alignment`** | Right after coding, before big runs | Traces code branches against equations, flags silent fallbacks/clips, and runs a fast local smoke check. |
| **`baseline-killer-audit`** | After initial pilot results | Tries to beat your headline claim with a simple baseline or catch handicapped/unfair comparisons. |
| **`scientific-report-review`** | Draft manuscript, report, or grant | Runs blind reviewers in stages: code → baselines & novelty → structure, claims & readability → prose polish. |

## Install & Update

Clone the repo and run the installer for your tool:

```bash
git clone https://github.com/Zephrous5747/research-audit-skills.git
cd research-audit-skills

python scripts/manage_skills.py install --target antigravity   # ~/.gemini/config/skills
# or: --target claude  (~/.claude/skills)
# or: --target codex   (~/.codex/skills)
```

To update later, run `git pull` and re-run the same `install` command. Your local config files are preserved.

## How to Use

Just ask your agent in plain English — it will pick the matching skill automatically:

- *"Screen this research idea before I start coding: ..."* (`idea-novelty-screen`)
- *"Audit `src/` against the equations in `methods.tex` before I submit cluster jobs."* (`code-math-alignment`)
- *"Try to break our benchmark speedup with a simple baseline."* (`baseline-killer-audit`)
- *"Run Stage 2 review on `manuscript.tex` and `supplement.tex`."* (`scientific-report-review`)

## Optional: Customize for Your Group

Inside your installed skills folder, you can optionally add private overrides (never committed):

- Copy `config.example.yaml` → `local_config.yaml` to set your default domain, venues, or arXiv categories.
- Copy `local_overlay.example.md` → `local_overlay.md` to add group-specific conventions or cluster rules.

If you review a paper outside your default domain, lab defaults are suppressed automatically.

## Verify / Maintain

```bash
pytest -q tests/test_skills_suite.py          # fast offline checks (<1 s)
python scripts/manage_skills.py pack          # audit, test, and build clean release zip
```
