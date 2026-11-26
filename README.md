# Research Audit Skill Suite

A modular, blind multi-agent research auditing and manuscript review suite designed to catch **silent numerical bugs**, **weak or handicapped baselines**, **theoretical/scaling flaws**, and **unverified prior-art claims** before you burn HPC compute or submit a paper.

## Skills & Sharp Boundaries

| Skill | When to Use | Core Output |
| :--- | :--- | :--- |
| **`idea-novelty-screen`** | Pre-code / whiteboard pitch / rough notes | **Fast 1-Page Executive Kill-Card** (upfront `track` routing, 3 blind scouts, bounded 1-round Pivot Red-Team pass, 2-sentence Referee #2 objection, Day-1 falsification pilot) + deduplicated Evidence Appendix. |
| **`code-math-alignment`** | Right after coding algorithms/benchmarks, *before* HPC sweeps (or Stage 0) | White-box branch-to-equation trace, fail-loud/silent-fallback ban, pipeline/thread-lock/atomic-write audit, `<10 s` `--smoke` gate (`ALIGNED_FAIL_LOUD` vs. `SILENT_POLLUTION_RISK`). |
| **`baseline-killer-audit`** | Pre-compute design gate or Stage 1A adversarial audit | Adversarial supervisor audit trying to break the headline speedup with a cheap baseline (minimal patch, library call, or simple ≤~50-line textbook baseline), information-asymmetry check, Repair vs. Discovery diagnostic, and external-baseline faithfulness table. |
| **`scientific-report-review`** | Full draft / code + manuscript / grant proposal | **4-Stage Sequential Blind Panel** (`Stage 0 -> Stage 1A -> Stage 1B + Pivot Red-Team -> Stage 2 [incl. blind 2-pass average reader] -> Stage 3`) with a 0-token pre-flight & storyflow linter (`preflight_lint.py`), diff-scoped `recheck`, and universal P0/P1 freeze. |

## Blind-Panel Architecture & Anti-Sycophancy Guardrails

1. **Zero Cross-Talk Isolation:** Scouts and reviewers run in isolated parallel contexts with no message passing, preventing consensus collapse and sycophantic echoing.
2. **Bounded Pivot Red-Team Mini-Pass:** Candidate Pivots proposed during screening (`idea-novelty-screen`) or Stage 1 (`scientific-report-review`) undergo a separate 1-round blind red-team pass with live subfield `search_web`, checking each Pivot against the strongest cheap baseline and derived constraints (`SURVIVES_RED_TEAM` / `VIABLE_WITH_PATCH` [strictly 1-sentence scope trim] / `NEEDS_FRESH_SCREEN` [unvetted rewrite requiring a fresh Day-0 screen] / `DROP_PIVOT`; 0 survivors is explicitly valid, in which case the panel emits a compact 4-bullet **Design-Space Constraints** checklist for the next iteration without pitching an unvetted 4th Pivot).
3. **Upfront Track Routing (`idea-novelty-screen`):** Ideas are classified upfront into `numerical_algorithm`, `pure_theory`, or `engineering_portfolio` so pure theory gets theorem/counterexample/analytic-pilot gates instead of awkward code benchmarks, and engineering projects keep strict validity/leakage/baseline gates without treating academic novelty as a hard kill.
4. **Evidence & Fail-Loud Discipline:** Live web/arXiv prior-art checks require real arXiv IDs/DOIs/URLs (never fabricated citations); code gates ban silent `except` fallbacks and unlogged solver failures; manuscript stages enforce `[AUTHOR: ...]` slots instead of inventing missing science; revision rechecks enforce a P0/P1 freeze to stop goalpost-shifting.

## Two-Layer Configuration (Public Core + Private Local Overlay)

This repository separates reusable **Public Core** skills (committed) from optional **Private Local Overlays** (`.gitignore`d):

1. Copy `config.example.yaml` to `local_config.yaml` to set your lab's default domain, target venues, arXiv categories, or HPC cluster names.
2. Optionally copy `local_overlay.example.md` to `local_overlay.md` to inject group-specific domain priors, benchmark conventions, or cluster rules.
3. Scripts (`idea-novelty-screen/scripts/screen_idea.py` and `scientific-report-review/scripts/review_panel.py`) check workspace `.agents/skills/` first, then the skill suite root. Under default `skip_local_overlay="auto"`, lab overlays and domain-specific venues/arXiv categories are automatically suppressed whenever an explicit cross-domain `domain` argument is supplied. If no local overlay exists, every skill runs cleanly with generic Public Core defaults.

## Quick Install (Antigravity, Claude Code & OpenAI Codex)

All four skills follow the open **Agent Skills** (`SKILL.md`) layout (`name` matches folder, `description <= 1,024` chars) and work across all three hosts:

| Host | Install Directory (Global or Repo) | Execution Path |
| :--- | :--- | :--- |
| **Antigravity** *(strictest native schema enforcement)* | `~/.gemini/config/skills/` or `<repo>/.agents/skills/` | Native `run_workflow` (`review_panel.py` / `screen_idea.py`) + standalone `SKILL.md` |
| **Claude Code** | `~/.claude/skills/` or `<repo>/.claude/skills/` | Standalone `SKILL.md` (`baseline-killer-audit`, `code-math-alignment`) + native parallel `Agent` subagents + `preflight_lint.py` |
| **OpenAI Codex** | `~/.codex/skills/` or `<repo>/.agents/skills/` | Standalone `SKILL.md` + native parallel subagents + `preflight_lint.py` |

Optional lab customization: copy `config.example.yaml` → `local_config.yaml` (and optionally `local_overlay.example.md` → `local_overlay.md`) inside your skills root. Both files are `.gitignore`d.

One-command install/update (preserves your existing `local_config.yaml` & `local_overlay.md`):

```bash
# Install or update into Antigravity, Claude Code, Codex, or a custom directory
python scripts/manage_skills.py install --target antigravity
python scripts/manage_skills.py install --target claude
python scripts/manage_skills.py install --target codex
```

## Quick Verification & Release Packaging

```bash
# Run the 0-token deterministic pre-flight linter standalone
python scientific-report-review/scripts/preflight_lint.py path/to/manuscript.tex path/to/refs.bib

# Run the fast (<1 s, zero-LLM) regression & Agent Skills compatibility test suite
pytest -q tests/test_skills_suite.py

# Maintainer workflow: sync Public Core from local Antigravity skills, audit, test & build clean release zip
python scripts/manage_skills.py sync --from ~/.gemini/config/skills
python scripts/manage_skills.py pack
```
