# Research Audit Skill Suite — Development Log

Newest entries last. Records architectural milestones, prompt/schema refinements, deterministic linter upgrades, and verification checks for the public Research Audit Skill Suite (`idea-novelty-screen`, `code-math-alignment`, `baseline-killer-audit`, and `scientific-report-review`).

---

## 2026-11-21 — Initial Multi-Agent Review Framework & `baseline-killer-audit` Skill

- **Core multi-agent review architecture (`scientific-report-review`):** Established an isolated blind multi-agent review panel with strict anti-invention ground rules (`references/ground-rules-and-rubric.md`), concise technical writing guidelines (`references/supervisor-writing-guide.md`), and a Stage 3 natural-prose/AI-tell polishing rubric (`references/academic-humanizer-guide.md`, adapted from MIT-licensed `AIScientists-Dev/academic-humanizer`).
- **New standalone skill (`baseline-killer-audit/SKILL.md`):** Created an adversarial pre-compute and pre-submission baseline audit encoding five rules:
  1. *5-line strongest cheap baseline* test on non-toy instances;
  2. *Information-asymmetry / double-standard* side-by-side code audit;
  3. *Repair vs. Discovery* mechanism diagnostic;
  4. *Pull every anomaly thread* (zero-burying policy for weaker-beats-stronger results);
  5. *External literature comparator faithfulness* audit.
- **Panel integration:** Wired `baseline-killer-audit` directly into `scientific-report-review/scripts/review_panel.py` as Reviewer 7 (`baseline_killer`).

## 2026-11-23 — Four-Stage Gated Pipeline & Standalone `code-math-alignment` (Stage 0) Skill

- **New standalone skill (`code-math-alignment/SKILL.md`, Stage 0 Gate):** Created a domain-general white-box code-to-math verification gate run before expensive HPC/SLURM sweeps or Stage 1 scientific reviews:
  1. Branch-to-equation trace for every conditional, clip, damping/regularization term, and tolerance threshold (`P0 Unapproved Assumption`);
  2. Fail-loud & silent-fallback ban (no silent `try/except`, no unlogged solver fallbacks on `maxiter`/`optimal_inaccurate`/`NaN`, explicit enforcement of spec-claimed PSD/eigenvalue/simplex guards);
  3. Cross-pipeline parameter/config symmetry, single-thread BLAS/OpenMP/Rust locks (`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `NUMEXPR_NUM_THREADS=1`, `RAYON_NUM_THREADS=1`), and atomic writes (temp file + `os.replace`);
  4. Boundary-crossing unit tests, metamorphic invariance checks, and a `< 10 s` local single-threaded `--smoke` pre-flight check emitting `ALIGNED_FAIL_LOUD` (`p0_p1_count == 0`) vs. `SILENT_POLLUTION_RISK`.
- **Four-stage refactor (`scientific-report-review`):** Refactored `SKILL.md`, `scripts/review_panel.py`, and `references/ground-rules-and-rubric.md` into four sequential gated stages (`Stage 0 -> Stage 1A -> Stage 1B -> Stage 2 -> Stage 3`):
  - **Stage 0 (`stage0`):** Reviewer 0 (`code_math_auditor`, dynamically loading `code-math-alignment/SKILL.md` and emitting `stage0_gate`).
  - **Stage 1 (`stage1a -> stage1b`):** Bounded Stage 1A (`baseline_killer`, hard-capped at 3 rounds with immediate early exit on `SOLID_BASELINE` + `p0_p1_count == 0`) followed by parallel Stage 1B (`theory_mechanism_critic`, `supervisor_strategist`).
  - **Stage 2 (`stage2`):** Reviewers 1–5 in parallel (`structure_narrative`, `reproducibility_code` scoped to manuscript-level provenance/metadata while white-box code logic lives in Stage 0, `claims_definitions`, `prose_style`, `figures_refs_format`).
  - **Stage 3 (`stage3`):** Reviewer 6 (`grammar_humanizer`) + strictly meaning-preserving prose edits, hard-gated until Stages 0, 1, and 2 pass.
- **Verification:** Validated Python AST / top-level-`await` compilation, verbatim dynamic skill loading (with YAML frontmatter stripped), and default stage routing.

## 2026-11-23 — Stage 1B Contribution Novelty & Prior-Art Audit

- Upgraded Reviewer 9 (`supervisor_strategist`) across `scripts/review_panel.py`, `SKILL.md`, `references/stage1-domain-supervision-guide.md`, and `references/ground-rules-and-rubric.md` with a structured contribution-by-contribution novelty and venue-bar schema (`NOVELTY_ASSESSMENT_SCHEMA`):
  - Five novelty tiers (`new_math_or_algorithm`, `cross_domain_transfer`, `empirical_discovery`, `incremental_tweak`, `subsumed_or_overlap`);
  - Venue-bar verdict (`CLEAR_NOVELTY_ABOVE_BAR` / `BORDERLINE_NEEDS_SHARPER_DIFFERENTIATION` / `OVERLAP_OR_INCREMENTAL_RISK`);
  - Prior-art overlap checking backed by live literature search / `prior_art_summary` with a strict ban on fabricated citations.

## 2026-11-24 — Stage 2B Compression & Triage Editor (`conciseness_editor`, Reviewer 10)

- Added Reviewer 10 (`conciseness_editor`) with four-bucket Main + SI triage (`cut`, `merge_squeeze`, `demote_main_to_si`, `archive_si_to_repo`), optional `length_budget` and `protected_requirements` arguments, and `COMPRESSION_LEDGER_SCHEMA` carrying explicit `preserves_reproducibility`, `preserves_stage1_2a_claims`, and `replacement_pointer` guardrails to prevent Stage 2A ↔ Stage 2B ping-pong.
- Updated default `stage2` to run Stage 2A (Reviewers 1–5) and Stage 2B (Reviewer 10) together in parallel so additive precision items balance against compression/demotion in a single pass, while preserving standalone `stage2a` and `stage2b` modes.

## 2026-11-24 — Workflow Hardening: 0-Token Pre-Linter, Diff-Scoped Rechecks, Lean Schemas & Active Capabilities

- **0-token deterministic pre-flight linter (`scientific-report-review/scripts/preflight_lint.py`):** Added a standalone CLI and dynamically loaded pre-linter scanning code, `.tex`/`.md`, `.log`/`.blg`, `.bib`, and plotting scripts to deliver exact `file:line` mechanical hits to Reviewers 0, 4, 5, and 6 before LLM execution.
- **Per-reviewer capability routing (`agent_type="auto"`):**
  - Reviewer 0 (`code_math_auditor`) routed to read-only active execution (`<= 5` fast `< 15 s` `--smoke`/`pytest`/micro-probe commands, reporting `execution_status` with graceful permission fallback).
  - Reviewer 9 (`supervisor_strategist`) routed to read-only live web/arXiv search (2–4 targeted `search_web` queries directly inside its isolated context, reporting `live_search_status`).
  - All remaining reviewers stay isolated in strict offline `research` mode.
- **Schema & protocol hardening (`scripts/review_panel.py`):**
  - Replaced monolithic union schemas with lean per-role `build_schema(reviewer_id, mode)` across all 11 reviewers;
  - Added diff-scoped `recheck` (`git_ref` / `diff_file`) with a universal P0/P1 freeze (preventing goalpost-shifting during revisions) and unified `stage_gate`;
  - Deduplicated Reviewer 4 (textual precision) vs. Reviewer 6 (Stage 3 grammar/AI tells);
  - Slimmed `SKILL.md` by factoring full `Args` tables and JSON invocation recipes into `references/workflow-args-and-recipes.md`.

## 2026-11-24 — Stage 2B (`conciseness_editor`) Hardening

- Extended `preflight_lint.py` with a 0-token Stage 2B density and table scanner (exact prose word counts, long-paragraph detection `>= 150` words, repeated caption boilerplate, table row counts, `--`/empty sparsity, near-constant columns, and orphan generated `.tex` files).
- Upgraded `COMPRESSION_LEDGER_SCHEMA` and Reviewer 10 prompts with `execution_tier` (`tier1_prose_only` / `tier2_table_or_script_refactor` / `tier3_author_policy`), `archive_artifact_status` (`exists_on_disk` / `must_generate_before_cutting`) + `source_script_to_update`, the **Honest-Limit Visibility Rule** (retain at least one compact Main-Text clause for every honest limitation/bound), and **Main-vs.-Table Contradiction Escalation**.

## 2026-11-24 — Global Portability & Multi-Workspace Path Resolution

- Migrated the skill suite from project-local `.agents/skills/` to global user configuration (`~/.gemini/config/skills/`).
- Generalized script path resolution in `review_panel.py` and documentation to check workspace `.agents/skills/` first and fall back to the skill suite root / `~/.gemini/config/skills/`, ensuring zero workspace-specific path coupling.

## 2026-11-25 — Standalone `idea-novelty-screen` Skill, Bounded Pivot Red-Team & Two-Layer Public/Local Config

- **New standalone skill (`idea-novelty-screen/`):** Built a fast pre-code, pre-manuscript screening workflow (`SKILL.md` + `scripts/screen_idea.py`) producing a **1-Page Executive Kill-Card** plus deduplicated Evidence Appendix:
  - Upfront track routing (`numerical_algorithm`, `pure_theory`, `engineering_portfolio`) so pure theory receives theorem/counterexample/analytic-pilot gates and engineering projects retain strict validity/baseline gates without treating academic novelty as a hard kill;
  - Three isolated blind scouts (feasibility/baseline killer, theory/limits critic, and live web/arXiv prior-art & venue-bar scout);
  - Bounded 1-round blind **Pivot Red-Team Mini-Pass** auditing every proposed Pivot against the strongest cheap baseline and derived scaling/math constraints (`SURVIVES_RED_TEAM` / `VIABLE_WITH_PATCH` / `DROP_PIVOT`);
  - Compact 2-sentence Referee #2 objection and concrete Day-1 falsification pilot.
- **Stage 1/1B Pivot Red-Team integration:** Added the matching bounded 1-round blind Pivot Red-Team mini-pass to `scientific-report-review/scripts/review_panel.py` whenever Reviewer 9 proposes candidate Pivots.
- **Two-layer Public Core + Private Local Overlay configuration:** Added `.gitignore`, `README.md`, `config.example.yaml`, and `local_overlay.example.md` so domain-general Public Core files stay cleanly committable while optional lab/cluster/domain priors load dynamically from gitignored `local_config.yaml` and `local_overlay.md`.

## 2026-11-25 — Stage 2 Top-Down Editorial Upgrades, Blind A/B Validation & Open-Source Sanitization

- **Five domain-general editorial upgrades (`scientific-report-review`):**
  1. **Reviewer 1 (`structure_narrative` — Pedagogical Architecture & Motivation):** Added Abstract zero-acronym / single-baseline test; reader-first Methods ordering (define the decision/problem before schedules, priors, or solvers; require a minimal concrete 2-object toy example before general notation; define the estimator before the optimization objective; place every Proposition/Theorem *after* the objective it bounds; use plain English before internal nicknames); descriptive-discourse audit; and optional `structural_blueprint` (`central_question_to_put_first`, `section_reordering_steps`, and 2–4 sentence draft-grounded `specimen_openings` with strictly zero invented claims).
  2. **Reviewer 3 (`claims_definitions` — Spec Sync & Slot Routing):** Added **Operational Edge-Case Spec Sync (Main Methods vs. SI)** auditing caps, fallbacks, ties, uncertified/unresolved statuses, return values vs. logged diagnostic indices, and stopping rules across Main Text and SI, plus **Anti-Defensive-Overstuffing Routing** tagging every qualification as `[SLOT: main_text_one_clause]` vs. `[SLOT: table_footnote_or_si]`.
  3. **Reviewer 10 (`conciseness_editor`):** Added **Abstract Baseline-Sprawl** and **Methods Constant-Eviction** checks (retaining core estimator, assumptions, objective, and stopping rules in Main while demoting solver iterations, tail cutoffs, and implementation constants to SI).
- **Blind A/B validation:** Verified the upgraded 6-reviewer Stage 2 panel in a 100% blind A/B benchmark against senior editorial revision criteria: blind reviewers independently surfaced backward Methods ordering (propositions placed before estimator/objective), missing minimal toy examples, Abstract acronym/baseline/timing sprawl, Main-vs.-SI operational edge-case spec mismatches, and Methods constant duplication, while maintaining zero regression across reproducibility, figure, prose-precision, and compression audits.
- **Public-repo sanitization & standalone `DEVLOG.md`:** Scrubbed all personal, group, institution, cluster, and project-specific domain references from Public Core skill files (`SKILL.md`, `references/*.md`, `scripts/*.py`), standardized internal filler-lint identifiers (`WORDY_FILLERS` / `wordy_fillers`), verified AST compilation + schema generation + standalone `preflight_lint.py` execution, and extracted this sanitized `DEVLOG.md` for GitHub publication.

## 2026-11-25 — Pivot Red-Team Calibration & Hardening (`NEEDS_FRESH_SCREEN` + Live Subfield Search)

- **Empirical false-acceptance calibration:** Blind standalone Day-0 re-audits (`skip_pivot_red_team=true`) of 5 prior `VIABLE_WITH_PATCH` survivors revealed an 80% false-acceptance rate (4/5 `FAIL`, 1/5 `BORDERLINE`), driven by offline Phase 2 zero-search blindness on new pivot subfields, multi-part rewrites smuggled into `one_line_patch` without independent verification, and benchmark-study escape hatches.
- **Minimal, concise fix across `screen_idea.py`, `review_panel.py`, `SKILL.md`, `ground-rules-and-rubric.md`, `stage1-domain-supervision-guide.md`, and `README.md`:**
  1. Routed Phase 2 Pivot Red-Team to read-only `self` with 1–2 targeted `search_web` queries per surviving Pivot (`live_search_status` in `PIVOT_RED_TEAM_SCHEMA`).
  2. Split `VIABLE_WITH_PATCH` strictly to single-sentence scope/parameter trims (zero new math objects, estimators, or domains) and added **`NEEDS_FRESH_SCREEN`** for multi-part rewrites/domain switches (flagged unvetted; requires a fresh blind Day-0 screen / Stage 1 before coding).
  3. Added explicit permission for `0/N` surviving pivots (all `DROP_PIVOT`) and banned generic "benchmark/phase-diagram" escape hatches unless live search confirms no subsuming critique.
- **Controlled blind A/B verification (3 benchmark prompts across `screen_idea.py` `engineering_portfolio` and `review_panel.py` `stage1b`/`stage1`):**
  - False `VIABLE_WITH_PATCH` approvals dropped from **4/9 (44%) $\to$ 0/9 (0%)**;
  - Phase 2 live subfield search rose from **0/3 $\to$ 3/3 (`searched_live`)**, catching subfield prior-art collisions directly inside Phase 2 without requiring a second full Stage 1 pass;
  - Direct kills (`DROP_PIVOT`) increased from **5/9 $\to$ 7/9** (including a clean `0/3` survivor outcome with no benchmark escape hatch), while the remaining **2/9** multi-part reframes were cleanly routed to **`NEEDS_FRESH_SCREEN`** (blocked from coding pending a fresh blind Day-0 screen);
  - Verified Python `PyCF_ALLOW_TOP_LEVEL_AWAIT` compilation and 4-tier `PIVOT_RED_TEAM_SCHEMA` assertions on both scripts.
- **Constructive dead-end handoff (`design_space_constraints`):** Added a conditional `design_space_constraints` field in `PIVOT_RED_TEAM_SCHEMA` (populated only when 0 Pivots clear as `SURVIVES_RED_TEAM` or `VIABLE_WITH_PATCH`) and a matching 4-bullet **Design-Space Constraints** box in `SKILL.md` / `ground-rules-and-rubric.md` (baseline floor, non-negotiable invariants, verified open window, and 5-minute whiteboard litmus test, in a colleague-safe tone with zero unvetted 4th Pivots).

## 2026-11-25 — Tier 1 Pre-Share Hardening, Linter Bug Fixes & `pytest` Regression Suite

- **Pivot Red-Team & gate hardening (`screen_idea.py`, `review_panel.py`):**
  - Added `"skipped_all_dropped"` to `PIVOT_RED_TEAM_SCHEMA`'s `live_search_status` enum and propagated Phase 2 `blocked_or_offline` status into `search_verification_required`.
  - Made machine gates fail-closed: `stage0_closed` / `ready_to_advance` remain `False` when `execution_status == "blocked_by_permission"`; R0/R7 are looked up by `reviewer_id`; `ready_to_advance` blocks on `OVERLAP_OR_INCREMENTAL_RISK`, offline live search, `reproducibility_rating == "insufficient"`, and `not_ready_*` recheck verdicts; `screen_idea.py` emits `NEEDS_LIVE_SEARCH_VERIFICATION` instead of `PROCEED_TO_PROTOTYPE` when live search is offline on hard-novelty tracks; `_extract_diff_text` fails loud with `diff_warnings` (including untracked target files) instead of silent `except: pass`.
- **Stage 2 prompt/schema alignment & sanitization (`review_panel.py`, `SKILL.md`, `ground-rules-and-rubric.md`, `academic-humanizer-guide.md`):**
  - Added Reviewer 1's `specimen_openings` carve-out to `GROUND_RULES` Rule 2; deduplicated Abstract baseline checks out of R10; aligned R3 and R10 on single canonical SI edge-case definitions + 1-line Main pointer; synced parallel `stage2` vs. standalone `stage2b` docs; enforced required role deliverables (`live_search_status`, `novelty_assessment`, `reproducibility_rating`, `conclusion_support_assessments`, `compression_ledger`) in `build_schema`; extended `LOCAL_OVERLAY_MD` to Stage 2 reviewers; cleaned remaining Public Core domain-example leftovers.
- **Linter fixes & regression tests (`preflight_lint.py`, `tests/test_skills_suite.py`):**
  - Fixed CLI usage docstring, binary `open(..., "wb")` / `.write_bytes()` detection, Markdown YAML/HR/table-separator/code-fence `---` em-dash false positives, `.bib` field-name regex checks, balanced-brace `\caption{...}` extraction, and inline `\begin{tabular}` scanning.
  - Added fast (`< 5 s`, zero-LLM) `pytest` regression suite in `tests/test_skills_suite.py`.
- **Light Tier 2 cross-platform compatibility (Antigravity / Claude Code / OpenAI Codex):**
  - Trimmed `scientific-report-review/SKILL.md` frontmatter `description` from 1,425 chars to under the strict 1,024-char Agent Skills standard limit enforced by Claude Code and OpenAI Codex (all 4 skills verified compliant).
  - Added `.claude/skills`, `.codex/skills`, and `~/.agents/skills` to `_skill_root_candidates()` in both workflow scripts, added concise 4-line non-Antigravity native-subagent fallback notes to `idea-novelty-screen/SKILL.md` and `scientific-report-review/SKILL.md` (preserving 100% native Antigravity `run_workflow` support with zero prompt duplication), updated `README.md` with a 3-host Quick Install table, and added automated Agent Skills frontmatter + relative-link compliance checks to `tests/test_skills_suite.py`.
- **Reviewer 11 (`average_reader` — Minimum-Effort Blind Teach-Back, `flash_lite`):**
  - Added advisory Reviewer 11 (`average_reader`, default `reader_model="flash_lite"`) to Stage 2 / 2A (`mode="review"`, skipped by default in diff-scoped `recheck` unless explicitly requested) in `review_panel.py`, `SKILL.md`, `workflow-args-and-recipes.md`, and `ground-rules-and-rubric.md`.
  - Strictly isolated from `extra_files`, `local_overlay.md`, and `preflight_lint` (reads Main Text + SI only), emits required `plain_english_reconstruction` and `where_i_got_lost_or_bored` fields, and never auto-blocks `stage_gate` (Main Agent promotes verified reader misunderstandings/drop-off points).

## 2026-11-26 — Cross-Domain External Stress Test, Local-Overlay Isolation & Evaluator Sanity Probes

- **Cross-domain external benchmark stress test:** Stress-tested the blind Stage 1 panel (`R7 baseline_killer`, `R8 theory_mechanism_critic`, `R9 supervisor_strategist` with live web/arXiv search, plus 1-round Pivot Red-Team) on an external, out-of-domain published benchmark paper + codebase (astrophysics radial-velocity model-fitting for AI agents, completely outside the local overlay's default domain). The panel maintained zero overlay bleed, independently uncovered verifiable code-vs-prose P0 defects (nested ground-truth feedback leakage, asymmetric-jitter null-model metric exploits, non-monotone lenient matching, self-sabotaged baselines, Cramér–Rao unidentifiable synthetic tasks, double-counted noise, dead-code conditional flags, and timeout survivorship bias), and rejected 3/3 candidate pivots against $\le 10$-line domain floors with constructive `design_space_constraints`.
- **Effort-bounded cheap-baseline calibration (`baseline-killer-audit`, `idea-novelty-screen`, `scientific-report-review`):** Replaced rigid literal `<= 10 lines` caps with an honest two-tier effort bound — minimal targeted patch (`~5–20` lines) to existing repo baselines, OR off-the-shelf library call / simple single-file textbook baseline (`<= ~50` lines / `<= 1` hour to code, at a fraction of the proposed method's compute) — eliminating artificial line-count compression while preserving anti-heavyweight discipline.
- **Automatic cross-domain local-overlay isolation (`review_panel.py`, `screen_idea.py`, `workflow-args-and-recipes.md`, `idea-novelty-screen/SKILL.md`):**
  - Added `_domain_tokens()` and `_resolve_local_overlay_policy()` plus an explicit `skip_local_overlay` argument (`"auto"` default, `True`, or `False`).
  - Under `"auto"`, when an explicit `domain` argument has zero domain-token overlap with `local_config.yaml`'s `default_domain`, both workflow scripts automatically suppress `local_overlay.md` as well as lab-specific `default_venues`, `arxiv_categories`, and `default_target_venue` (recording `local_overlay_loaded.applied = false` and `skipped_reason = "cross_domain_override"` in JSON output and logs), preventing domain bleed on cross-domain runs—especially on lighter models.
- **Stage 0 & Stage 1A benchmark/evaluator sanity upgrades (`code-math-alignment/SKILL.md`, `baseline-killer-audit/SKILL.md`, `ground-rules-and-rubric.md`):**
  - Extended Stage 0 (`code-math-alignment`, Rule 4) with four domain-general evaluator micro-probes when auditing evaluators, graders, or task banks: **Ground-Truth / Oracle Solvability**, **Null/Empty-Model rejection**, **Monotonicity / Garbage-Padding invariance**, and **Zero-Leakage & Denominator checks**.
  - Extended Stage 1A (`baseline-killer-audit`, Rules 2 & 4) with explicit **interaction & input parity** checks (retries, withheld runtime inputs, and leaked oracle diagnostics vs. 1-shot blind baselines) and **0%/cliff collapse anomaly** checks (requiring immediate ground-truth/oracle pass-rate and timeout-denominator verification).
- **Regression test expansion (`tests/test_skills_suite.py`):** Added 3 zero-LLM regression tests verifying cross-domain auto-suppression, in-domain retention, explicit `skip_local_overlay=True/False` overrides across both `review_panel.py` and `screen_idea.py`, and verbatim loading of the new Stage 0 and Stage 1A evaluator sanity/parity clauses (`13 passed in 1.51s`, including Agent Skills `< 1,024`-char description and relative-link compliance).
- **Revised scientific writing guide calibration (`supervisor-writing-guide.md`, `review_panel.py`, `preflight_lint.py`, `ground-rules-and-rubric.md`, `tests/test_skills_suite.py`):**
  - Retired outdated rigid formatting/prose constraints (EPS-only, fixed `lw >= 2` / `fontsize >= 20 pt` / 4-color rule, Abstract `<= half page`, blanket caption-repetition and `"explore"/"understand"` bans, blind minimum-word deletion) in favor of final printed-size legibility (PDF or EPS vector, color + line-style/marker redundancy, short panel annotations ok), compact venue-bounded Abstracts, purpose-based caption/text balance, and clarity-preserving filler pruning.
  - Added 7 targeted Stage 2/3 checks across R1–R6 and R11 (retained on `flash` so SI skimming is preserved): Title + short-route parity (`Title -> Abstract -> Figures+Captions -> Conclusions`), Abstract prior-work-vs.-new-delta teach-back (`prior_work_vs_new_delta_from_abstract` in R11), stop-before-the-choice & combined-method interaction (R1), three-way epistemic separation & one-name-for-one-concept (R3), structural forward refs + physical-action & science-altering syntax checks (R4/R6), explicit uncertainty/table/plot-line honesty & citation-to-claim accuracy (R2/R5), plus a concise Cover Letter / Referee Response section in `supervisor-writing-guide.md`.
  - Relaxed `preflight_lint.py` plot-script thresholds to advisory extreme-legibility cutoffs (`lw < 1.0`, `fontsize < 8 pt`) so clean 1-column PDF plot scripts (`lw=1.5, fontsize=10`) pass with zero false positives.
- **Anti-"smart-reader" friction upgrades (Options 1, 3 & 4 — `preflight_lint.py`, `review_panel.py`, `ground-rules-and-rubric.md`, `workflow-args-and-recipes.md`, `tests/test_skills_suite.py`):**
  - **Option 1 (Forced impatient-skimmer telemetry on R11):** Upgraded `average_reader` (`flash`) from passive "where did you get lost?" to an adjacent-field Friday-afternoon skimmer persona with mandatory `walkout_point`, mandatory ranked top 3–5 `friction_hotspots` (`math_wall_no_intuition`, `story_detour`, `working_memory_overload`, `prose_breaks_if_math_skipped`, `pacing_drag`), and a mental skip-the-equations storyline test.
  - **Option 3 (0-token storyflow & cognitive-load scanner $\to$ R1):** Added deterministic `lint_storyflow_load()` in `preflight_lint.py` detecting `math_walls` ($\ge 6$-line display blocks or $\ge 3$ clustered blocks with $< 25$ prose words between them), `symbol_density_spikes` ($\ge 10$ inline math spans with $\ge 6$ distinct tokens, or $\ge 4$ compound sub/superscripts in one paragraph), and `unanchored_long_stretches` ($\ge 450$ words without a heading or figure/table anchor), routed to Reviewer 1 (`structure_narrative`) while keeping R11 strictly lint-free.
  - **Option 4 (Automatic 2-pass no-lookahead split for R11):** Added `reader_two_pass` (`"auto"` default, `True`, `False`) and smart Main-vs.-SI filename splitting so whenever R11 receives $\ge 2$ files in `review` mode, Pass 1 reads Main Text strictly blind to SI (zero SI path in prompt), and Pass 2 cross-checks Pass 1's frozen gaps against Main + SI (`two_pass_si_audit` + attached `pass1_main_only`) concurrently inside Stage 2's parallel panel.
- **Public release sharpening (`v0.2.0-beta.1` — `README.md`, `SKILL.md`, `review_panel.py`, `preflight_lint.py`, `verify_citations.py`, `scripts/export_panel.py`, `LICENSE`, `examples/`):**
  - Reframed the suite explicitly around its core moat: **Pre-Compute & Scientific-Validity Auditing for Quantitative/Computational Research** (`Idea Screen -> Stage 0 Code-to-Math -> Stage 1A Baseline-Killer -> Stage 1B Theory/Novelty + Pivot Red-Team`), positioning Stage 2–3 as a lean optional manuscript side-product.
  - Slimmed default `stage2` / `stage2a` to the 3 high-signal computational-paper pillars (R1 + R11 2-pass skimmer + `lint_storyflow_load`; R2 + R3 spec-sync + `.bib`/`.log` lint; R10 anti-ping-pong compression), decoupling repetitive R4/R5/R6 micro-nitpicks into opt-in Stage 3 / explicit `reviewers`.
  - Added stdlib-only `scientific-report-review/scripts/verify_citations.py` (offline `.bib`/undefined-`\cite` checks + live arXiv Atom API / Crossref / Semantic Scholar verification).
  - Added pure-Python `scripts/export_panel.py` (`export` + fail-closed `gate`) so Claude Code / OpenAI Codex / custom CLI harnesses can execute the exact prompts, JSON schemas, 0-token linters, and gates without Antigravity `run_workflow`, with an explicit platform boundary table in `README.md`.
  - Added MIT `LICENSE` and two sanitized example audit transcripts in `examples/`.
- **Offline prior-art brief guard & retrospective `cutoff_year` support (`review_panel.py`, `screen_idea.py`, `workflow-args-and-recipes.md`, `tests/test_skills_suite.py`):**
  - Added `"used_supplied_brief"` to `PIVOT_RED_TEAM_SCHEMA` (both scripts) and Scout 3's `live_search_status` enum (`screen_idea.py`), wired `prior_art_summary` directly into Phase 2 Pivot Red-Team prompts (and `screen_idea.py`), and added a fail-closed `_enforce_offline_search_status()` guard so offline `agent_type="research"` subagents can never falsely self-report `"searched_live"` (deterministically normalized to `"used_supplied_brief"` when a brief is provided, or `"blocked_or_offline"` otherwise).
  - Added optional `cutoff_year` argument to both workflow scripts to bound `search_window` (e.g., `2022-2025` / `2019-2025`) and inject an explicit `<= <cutoff_year>-12-31` temporal cutoff directive for retrospective blind calibration benchmarks.
- **Reviewer 7 (`baseline-killer-audit` / Stage 1A) materiality & 4-tier verdict calibration (`baseline-killer-audit/SKILL.md`, `review_panel.py`, `ground-rules-and-rubric.md`, `scientific-report-review/SKILL.md`, `tests/test_skills_suite.py`):**
  - Added a 4th Stage 1A verdict (`MECHANISM_SOLID_PARITY_FIX_NEEDED`, paired with `p0_count` and `stage1a_gate.can_advance_to_stage1b`) to separate verified `Discovery` mechanisms needing localized P1 table/parity/scope fixes from headline-collapsing `HANDICAPPED_BASELINE_RERUN_REQUIRED` failures, with a fail-closed `STAGE1A_VERDICT_GUARD` escalating any `p0_count > 0` mismatch back to `HANDICAPPED_BASELINE_RERUN_REQUIRED`.
  - Added explicit P0 / P1 / P2 materiality cutoffs, quantitative impact sizing on cheap baseline upgrades (Rules 1, 3, and 4), and explicit role boundaries excluding out-of-scope R8 asymptotic/failure-mode theory and R2 parameter-table gaps from R7's `p0_p1_count`.
- **Objective–proxy alignment check & domain-vestige cleanup (`baseline-killer-audit/SKILL.md`, `stage1-domain-supervision-guide.md`, `review_panel.py`, `tests/test_skills_suite.py`):**
  - Controlled de-hinted blind replay tests showed `baseline-killer-audit` robustly catches asymmetries, anomalies, and closed-form pooling baselines even with origin-domain hints removed, but satisfices on standard literature heuristics shared identically by method and baseline.
  - Stripped residual domain-origin phrasing from `baseline-killer-audit/SKILL.md` (Rule 1, Rule 4, Rule 5), `stage1-domain-supervision-guide.md`, and Reviewer 8 in `review_panel.py` (removing `"unshared beats shared"`, `"magnitude-sorted ordering"`, `"Anti-correlations"`, `"exact-covariance"`, and `"shots"`/`"circuit"` specifics).
  - Added a domain-general **Objective–proxy alignment** check to `baseline-killer-audit` (Rule 1) and Stage 1B `theory_mechanism_critic` (`stage1-domain-supervision-guide.md` + `review_panel.py`) auditing whether imported or shared heuristics match the task's actual decision objective (e.g., sum vs. max/minimax/pairwise contrast, average vs. tail risk, full-set vs. active-subset), verified via `tests/test_skills_suite.py`.
