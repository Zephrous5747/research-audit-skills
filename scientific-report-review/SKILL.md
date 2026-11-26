---
name: scientific-report-review
description: >-
  Pre-compute & scientific-validity blind multi-agent audit suite for
  quantitative/computational research, plus an optional lean manuscript audit
  and prose pass. Enforces code-first and science-first gating: Stage 0
  (`code-math-alignment` + read-only `--smoke`/`pytest`), Stage 1A (bounded
  `baseline-killer-audit`), Stage 1B (theory/mechanism + live web/arXiv novelty
  + 1-round Pivot Red-Team), Stage 2 (optional lean 3-pillar manuscript audit:
  skimmability/2-pass reader, provenance/spec-sync + API citation check, and
  compression), and Stage 3 (optional decoupled prose/formatting polish). Use
  for pre-HPC code-to-math gates, baseline/novelty/reproducibility reviews,
  compression, or pre-submission verification.
---

# Scientific Report Review (Four-Stage Code-First & Science-First Blind Panel)

Enforces a **4-stage sequential pipeline** (`Stage 0 → Stage 1A/1B → Stage 2 → Stage 3`) so you **eliminate silent numerical pollution first, verify and deepen the science second, polish structure/provenance and compress bloat third, and edit natural prose last**. Reviewers run blind via `run_workflow` with **zero message passing** and a **0-token Python pre-flight linter** ([preflight_lint.py](./scripts/preflight_lint.py)).

**Boundary vs. `idea-novelty-screen`:** Use `idea-novelty-screen` for rapid pre-code Kill-Card screening (1-page verdict + 2-sentence Referee #2 objection). Use `scientific-report-review` for full code/manuscript auditing, full multi-point Referee #2 pre-mortems, and Stage 0–3 publication gates.

## Pipeline Architecture (Zero Cross-Talk)

```text
STAGE 0: Code-to-Math & Fail-Loud Gate (HARD GATE before `sbatch` & Stage 1)
  ──► Reviewer 0 (`code_math_auditor`, type=`self` read-only + <=5 fast `--smoke`/`pytest` cmds)
  Pass condition: `ALIGNED_FAIL_LOUD` & `p0_p1_count == 0` (if shell blocked, Main Agent runs `--smoke`)
        │
        ▼
STAGE 1A: Bounded Baseline-Killer Gate (1-3 rounds max, immediate early exit on `p0_p1_count == 0`)
  ──► Reviewer 7 (`baseline_killer`, type=`research`, loads `baseline-killer-audit`)
        │
        ▼  [STAGE 1A CLEARED FOR 1B: `SOLID_BASELINE` (`p0_p1=0`) OR `MECHANISM_SOLID_PARITY_FIX_NEEDED` (`p0=0`, local P1 fixes)]
STAGE 1B: Theory, Mechanism, Live Novelty & Supervisor Strategy (2 blind reviewers in parallel)
  ──┬──► Reviewer 8 (`theory_mechanism_critic`, type=`research`)
    └──► Reviewer 9 (`supervisor_strategist`, type=`self` — direct live recent web/arXiv search)
        │
        ▼  [If Reviewer 9 proposes candidate Pivots: 1-round blind Pivot Red-Team Mini-Pass (`self` read-only + live `search_web`)]
           -> Audits each Pivot vs. cheapest baseline, R8 constraints & subfield search (`SURVIVES_RED_TEAM` | `VIABLE_WITH_PATCH` | `NEEDS_FRESH_SCREEN` | `DROP_PIVOT`)
        │
        ▼
STAGE 2 (Optional Manuscript Side-Product — Lean 3-Pillar Computational-Paper Audit):
  ──┬──► [Pillar 1 — Skimmability & Narrative]
    │      Reviewer 1 (`structure_narrative` + 0-token `lint_storyflow_load`)
    │      Reviewer 11 (`average_reader`, `flash`, automatic 2-pass Main-blind-to-SI skimmer, advisory)
    ├──► [Pillar 2 — Provenance, Main<->SI Spec Sync & Citations]
    │      Reviewer 2 (`reproducibility_code` + `.bib`/`.log` lint + `verify_citations.py` arXiv/Crossref check)
    │      Reviewer 3 (`claims_definitions` — 3-way epistemic separation & Main<->SI spec sync)
    └──► [Pillar 3 — Compression & Triage]
           Reviewer 10 (`conciseness_editor` — Main+SI cut/merge/demote/archive, anti-ping-pong safe)
        │
        ▼  [HARD GATE: Proceed to Stage 3 ONLY after Stages 0, 1, and 2 are resolved]
STAGE 3 (Optional Decoupled Polish — opt-in only):
  ──► Reviewer 6 (`grammar_humanizer`, default Stage 3); R4 (`prose_style`) & R5 (`figures_refs_format`) opt-in via `reviewers`
  ──► Main Agent applies strictly meaning-preserving word edits (zero numbers/equations/cite keys altered)
```

## Reference Guides (Read On Demand)
- **Full `Args`, stage table & JSON recipes:** [workflow-args-and-recipes.md](./references/workflow-args-and-recipes.md)
- **Ground rules & 4-stage output rubrics:** [ground-rules-and-rubric.md](./references/ground-rules-and-rubric.md)
- **Stage 0 white-box gate:** [code-math-alignment](../code-math-alignment/SKILL.md)
- **Stage 1A baseline gate:** [baseline-killer-audit](../baseline-killer-audit/SKILL.md)
- **Stage 1B domain supervision & novelty rubric:** [stage1-domain-supervision-guide.md](./references/stage1-domain-supervision-guide.md)
- **Stage 2 scientific writing guide:** [supervisor-writing-guide.md](./references/supervisor-writing-guide.md)
- **Stage 3 grammar & AI-tell guide (`academic-humanizer`, MIT):** [academic-humanizer-guide.md](./references/academic-humanizer-guide.md)

---

## Step 1: Select Stage, Mode, and Inputs

1. **Choose the stage** (default order: `stage0 → stage1a → stage1b → stage2 → stage3`):
   - **`stage0`**: Required before ANY `sbatch` / HPC job or Stage 1 review whenever executable code is present. Pass source files, configs, tests, and cluster scripts in `extra_files` (plus equations/draft in `report`). If `stage0_gate.execution_status == "blocked_by_permission"`, **the Main Agent MUST run the `< 10 s` local `--smoke` and `pytest` commands directly** before declaring Stage 0 passed.
   - **`stage1a`**: Runs Reviewer 7 alone, max 3 rounds. Stop **immediately** when `stage1a_gate.closed == true` (`SOLID_BASELINE` and `p0_p1_count == 0`) and launch `stage1b`; if `stage1a_gate.can_advance_to_stage1b == true` (`MECHANISM_SOLID_PARITY_FIX_NEEDED` with `p0_count == 0`), you may launch `stage1b` in parallel while fixing localized P1 table/parity/scope items before Stage 2. Never re-run on prose-only edits; save each round to a file (e.g., `reports/review_stage1a_r1.md`).
   - **`stage1b`**: Runs Reviewers 8 & 9 in parallel. Reviewer 9 runs 2–4 live `search_web` queries directly inside its own isolated context (no need to clutter Main Agent context unless `live_search_status == "blocked_or_offline"`, in which case pass a `prior_art_summary`). Whenever Reviewer 9 proposes candidate Pivots/reframings, `review_panel.py` automatically runs a bounded 1-round blind **Pivot Red-Team Mini-Pass** against Reviewer 8's derived constraints before finalizing Stage 1B.
   - **`stage2`** *(default = 2A + 2B together; `stage2a` / `stage2b` standalone)*: Pass both Main Text and SI in `report` plus `.bib`/manifests in `extra_files` and optional `length_budget`. When running `stage2b` standalone after Stage 2A edits, pass the Stage 2A review via `protected_requirements` so Reviewer 10 never cuts protected facts/provenance (zero Stage 2A ping-pong).
   - **`stage3`**: **Hard Gate** — warn and stop if unresolved Stage 0, Stage 1, or Stage 2 essential science gaps exist. Pass optional `doc_type`, `target_venue`, and `voice_sample`.
2. **Choose the mode (`review` vs. diff-scoped `recheck`)**:
   - In `recheck` mode, **prefer passing `git_ref` (e.g. `"HEAD~1"`) or `diff_file` plus `previous_review`** instead of full `original_report` blobs. This cuts recheck tokens ~50–70% and enforces the **universal P0/P1 freeze** (reviewers verify prior open P0/P1 items + diff regressions only, stopping once `stage_gate.total_p0_p1_count == 0`).

---

## Step 2: Launch `run_workflow`

Call `run_workflow` with `ScriptPath` resolved to `./scripts/review_panel.py` relative to this `SKILL.md` directory, and `Args` matching [workflow-args-and-recipes.md](./references/workflow-args-and-recipes.md). (Optional gitignored `local_config.yaml` and `local_overlay.md` at `.agents/skills/` or the skill suite root are loaded automatically when present.)

`review_panel.py` automatically:
1. Runs the 0-token pre-flight linter (`preflight_lint.py`) and attaches scoped `file:line` hits to Reviewers 0, 1, 2, 4, 5, 6, and 10 (optionally run `python ./scripts/verify_citations.py refs.bib manuscript.tex` before Stage 2 to verify arXiv/Crossref DOIs).
2. Routes R0 (`self`, read-only `--smoke`/`pytest`), R9 & Stage 1 Pivot Red-Team (`self`, read-only live `search_web`), and all other reviewers (`research`, strict read-only).
3. Assigns each reviewer a lean per-role JSON schema, runs a bounded 1-round blind **Pivot Red-Team Mini-Pass** whenever Stage 1/1B proposes candidate Pivots, and returns `stage_gate` (`total_p0_p1_count`, `ready_to_advance`), `stage0_gate`, `stage1a_gate`, and `pivot_red_team`.

**Non-Antigravity Hosts (Claude Code / OpenAI Codex):** `review_panel.py` uses Antigravity's `run_workflow`. On Claude Code or Codex, run `python ./scripts/preflight_lint.py` and `python ./scripts/verify_citations.py` directly via shell, or export exact per-reviewer prompts and JSON schemas for your host's native subagents via `python scripts/export_panel.py export --workflow review --stage <stage> ...` (and evaluate the fail-closed gate with `export_panel.py gate`).

---

## Step 3: Main-Agent Verification, Synthesis & Stage-Gated Editing

1. **Verify before reporting:** Cross-check findings against actual source files; discard false positives; deduplicate overlapping points across reviewers; in Stage 1/1B, never recommend `DROP_PIVOT`, treat `NEEDS_FRESH_SCREEN` strictly as an unvetted lead requiring a fresh blind Stage 1 / Day-0 screen (`skip_pivot_red_team=true`) before coding, clear only `SURVIVES_RED_TEAM` or strictly scope-trimmed `VIABLE_WITH_PATCH` for direct piloting, and when 0 Pivots clear directly, include the compact 4-bullet **Design-Space Constraints** box (strictly necessary conditions, colleague-safe tone, no unvetted 4th Pivot); in `stage2`/`stage2b`, execute `tier1_prose_only` trims before `tier2_table_or_script_refactor`, keep at least one compact Main-Text clause for every honest limitation/bound, and never delete an SI table marked `must_generate_before_cutting` until its replacement CSV is emitted and verified on disk.
2. **Synthesize** using the exact headings in [ground-rules-and-rubric.md](./references/ground-rules-and-rubric.md), obeying all 8 ground rules (never invent scientific content; use `[AUTHOR: ...]` slots; cite exact locations/quotes; assign strictest justified verdict in `recheck`).
3. **Stage-gated editing policy:**
   - **Stages 0, 1, 2:** Review-only on manuscript prose by default. Apply code fixes in Stage 0 or strictly mechanical LaTeX/typo fixes in Stage 2 only when explicitly requested by the user (and never alter scientific meaning).
   - **Stage 3 (science already fixed):** Apply Reviewer 6's verified, strictly meaning-preserving word edits (grammar, clause splitting, AI-tell & em-dash removal) while keeping evidence-tied hedging, passive voice where appropriate, `"we"`, formal definitions, equations, numbers, and citation keys **100% verbatim**. Confirm integrity explicitly after editing.
4. **Output:** Present the synthesized review in chat (or save to `reports/review_<stage>.md` for clean diff-scoped rechecks) and state clearly whether the work is cleared for the next gate (`Stage 0 → Stage 1A → Stage 1B → Stage 2 → Stage 3`).
