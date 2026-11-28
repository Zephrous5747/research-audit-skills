# Research Audit Skills

**Pre-compute & scientific-validity auditing for quantitative and computational research** — catch broken code-to-math assumptions, handicapped baselines, and scooped ideas *before* burning HPC hours or drafting a paper.

Core pipeline: **Idea Screen → Code-to-Math Gate (Stage 0) → Baseline-Killer Gate (Stage 1A) → Theory, Live Novelty & Pivot Red-Team (Stage 1B)**, plus a lean optional manuscript audit (Stage 2–3) as a companion side-product.

## Why This Exists

Most AI research tools focus on polishing prose. In computational science, the expensive mistakes happen much earlier: silent `except` fallbacks, evaluator leakage, self-sabotaged baselines, or spending three months on an algorithm beaten by a 20-line standard baseline. These skills audit **validity first** using isolated blind reviewers (zero cross-talk) and fail-closed gates.

### Design Principle: One-Way, Report-Once Isolation (No Agent-to-Agent Chat)

Every reviewer runs as an **isolated, one-shot, schema-bound report** — never a multi-turn conversation between reviewers or with the main agent:
- **Zero agent-to-agent chat** prevents compounding hallucinations, sycophantic drift, and wasted time cleaning up circular debates.
- **One-way return only** — each reviewer inspects the artifacts independently, emits a single structured JSON report, and terminates; the main agent verifies and synthesizes once.
- **Recommendation when customizing or running on Claude Code / Codex:** keep this boundary intact — dispatch every exported reviewer prompt as a single-turn, report-once subagent rather than a conversational loop.

## The 5 Skills

### Core Pre-Compute & Validity Gates *(Primary Focus)*
| Skill | When to use it | What it catches |
| :--- | :--- | :--- |
| **`idea-novelty-screen`** | Before writing code | Live arXiv/web overlap, theoretical/scaling traps, cheap baseline floors, and a 1-round blind Pivot Red-Team (outputs a 1-page Go/Pivot/Kill card). |
| **`idea-falsification-loop`** | Exploring a new problem space | Bounded autonomous Generator + Falsification loop (`max_rounds <= 5`) chaining `idea-novelty-screen` and optional `<60 s` CPU Day-1 pilots gated by Stage 0 & Stage 1A, maintaining a `GRAVEYARD` to block repackaging killed ideas. |
| **`code-math-alignment`** *(Stage 0)* | Right after coding, before cluster sweeps | Code-vs.-equation mismatches, silent fallbacks/clips, missing thread locks/atomic writes, evaluator oracle/null-model exploits, and `<10 s` local `--smoke` checks. |
| **`baseline-killer-audit`** *(Stage 1A)* | After initial pilot results | Tries to break your headline claim with a simple baseline (minimal patch, library call, or ≤ ~50-line textbook baseline) and exposes interaction/budget asymmetries. |

### Full Panel & Optional Manuscript Companion
| Skill | When to use it | What it covers |
| :--- | :--- | :--- |
| **`scientific-report-review`** | Full code + draft audit | Orchestrates **Stage 0** + **Stage 1A/1B** (with Pivot Red-Team), plus an **optional slim Stage 2 manuscript audit** across 3 high-signal checks: **(1) Skimmability** (R1 + 2-pass Main-blind-to-SI skimmer + 0-token math-wall linter), **(2) Provenance, Main↔SI Spec Sync & Citations** (R2 + R3 + arXiv/Crossref verifier), and **(3) Compression & Triage** (R10). Micro-style/prose polish (R4/R5/R6) is decoupled as opt-in Stage 3. |

**See real output structure:** [examples/01_idea_screen_kill_card.md](examples/01_idea_screen_kill_card.md) · [examples/02_precompute_stage0_stage1_audit.md](examples/02_precompute_stage0_stage1_audit.md)

## Platform Compatibility (Honest Boundary)

| Component | Antigravity | Claude Code / OpenAI Codex |
| :--- | :--- | :--- |
| **`code-math-alignment` & `baseline-killer-audit` (`SKILL.md`)** | Native | Native |
| **CLI tools (`preflight_lint.py`, `verify_citations.py`)** | Native (Python stdlib) | Native (Python stdlib) |
| **Parallel multi-agent workflows (`screen_idea.py`, `review_panel.py`, `run_idea_loop.py`)** | Native via `run_workflow` | Export exact prompts/schemas & run fail-closed gates via `scripts/export_panel.py`, then dispatch with your host's subagent tool |

## Quick Install

```bash
git clone https://github.com/Zephrous5747/research-audit-skills.git
cd research-audit-skills

python scripts/manage_skills.py install --target antigravity   # ~/.gemini/config/skills
# or: --target claude  (~/.claude/skills)
# or: --target codex   (~/.codex/skills)
```

Update anytime with `git pull` + re-running `install` (existing `local_config.yaml` and `local_overlay.md` are preserved).

## Quick Usage

**In agent chat (natural language):**
- *"Screen this idea before I code it: ..."* (`idea-novelty-screen`)
- *"Run a 3-round idea falsification loop in numerical linear algebra for sparse preconditioners (paper-only)."* (`idea-falsification-loop`)
- *"Run Stage 0 code-to-math audit on `src/` against `methods.tex` before I submit `sbatch`."* (`code-math-alignment`)
- *"Try to kill our benchmark speedup with a simple baseline."* (`baseline-killer-audit`)
- *"Run Stage 1B + Stage 2 on `manuscript.tex` and `supplement.tex`."* (`scientific-report-review`)

**Standalone zero-dependency CLI tools (any host or CI):**
```bash
# 0-token code hygiene, LaTeX, and math-wall/storyflow linter
python scientific-report-review/scripts/preflight_lint.py src/ manuscript.tex refs.bib

# Lightweight arXiv / Crossref / Semantic Scholar citation verifier (use --offline for syntax only)
python scientific-report-review/scripts/verify_citations.py refs.bib manuscript.tex --format md

# Export exact Stage 1 prompts & JSON schemas for Claude Code / Codex subagents
python scripts/export_panel.py export --workflow review --stage stage1 --report manuscript.tex --extra-files src/ --out-dir .audit_prompts
python scripts/export_panel.py gate --stage stage1 --results-dir .audit_results
```

## Optional: Lab Customization & Testing

- Copy `config.example.yaml` → `local_config.yaml` (and optionally `local_overlay.example.md` → `local_overlay.md`) inside your installed skills folder to set your group's default domain, venues, or cluster rules. Both are `.gitignore`d and auto-suppressed whenever you audit a paper in a different domain.
- Verify locally: `pytest -q tests/test_skills_suite.py` (`< 1 s`, zero LLM calls).

## License

[MIT](LICENSE)
