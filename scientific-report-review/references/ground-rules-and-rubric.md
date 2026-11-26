# Ground Rules and Four-Stage Review Rubric

This rubric governs all **blind critical reviewers** and the **main synthesizing/editing agent** across all four stages (`Stage 0 → Stage 1A/1B → Stage 2 → Stage 3`, plus revision re-checks at any stage).

---

## Ground Rules (All Stages)

1. **Never invent scientific content.** Never supply missing motivation, definitions, methods, parameters, results, or conclusions, and never fill gaps with plausible assumptions (e.g., *"presumably default regularization was used"*). If it is not in the report, it is missing.
2. **Do not ghost-write sections or paragraphs before Stage 3.** In Stages 0–2, fix code integrity and science first; **Reviewer 1 only** may propose a numbered section-reordering blueprint and 2–4 sentence plain-English specimen openings strictly grounded in facts already in the draft (zero invented numbers/claims). Even in Stage 3, keep prose edits strictly meaning-preserving (never alter numbers, equations, symbols, definitions, or citation keys).
3. **Use explicit author placeholders.** Whenever a fix requires scientific content, insert a slot: `[AUTHOR: explain why this approximation was chosen]`, `[AUTHOR: define this quantity and give units]`, etc.
4. **Never make the report sound more complete than it is.** Mechanical/grammar/wording edits are permitted *only* when they preserve scientific content and uncertainty boundaries exactly.
5. **Locate everything.** Cite section, figure, table, equation, `file:line`, or an exact short quote.
6. **Ask concrete, actionable questions.** Not *"Methods are unclear"*, but *"What convergence threshold and shot budget were used in Section 2.3?"*
7. **Mark possibilities explicitly.** Label inferences not directly proven by data as **Possibility:** and state what is needed to confirm them.
8. **Never vouch for code.** Never declare code correct unless verified line-by-line (Stage 0) or backed by explicit independent test evidence (Stage 2).

Adapt domain checklists to the field (customize defaults via optional gitignored `local_config.yaml` / `local_overlay.md`; e.g., basis sets/mappings for quantum chemistry, hyperparameters/dataset versions for ML, or reagent lots/instrument settings for wet lab).

---

## Stage 0 Output Structure — Code-to-Math Alignment & Fail-Loud Gate

**Active reviewer:** Reviewer 0 (`code_math_auditor`, `type_name="self"`, strictly no repo edits; may execute ≤ 5 fast `< 15 s` read-only `--smoke`, `pytest -q --tb=short`, and boundary/metamorphic micro-probe commands) — loads [code-math-alignment](../../code-math-alignment/SKILL.md) verbatim + 0-token pre-linter hits. Zero prose, grammar, or formatting nitpicks. **Hard gate before HPC sweeps and Stage 1.**

Produce these exact sections plus the machine-readable verdict block:

1. **Branch-to-Equation Trace & Unapproved Assumptions (`P0` / `P1`)**
   - Table: `file:line | Code Branch / Clip / Magic Constant | Spec Equation / Claim | Classification (Aligned / P0 Unapproved Assumption / P1 Undocumented Heuristic) | Required Fix`
2. **Fail-Loud Violations & Silent-Fallback Audit (`P0` / `P1`)**
   - Silent `try/except`, unlogged solver fallbacks (`maxiter`, `optimal_inaccurate`, `NaN`/non-convergence), and missing PSD/eigenvalue/simplex guards claimed in the spec, with exact `file:line` pointers.
3. **Cross-Pipeline Symmetry, Thread-Lock & Atomic-Write Audit (`P0` / `P1`)**
   - Side-by-side config, baseline/method call, summary, and plotting asymmetries; missing BLAS/Rust thread locks (`OMP_NUM_THREADS=1`, `RAYON_NUM_THREADS=1`, etc.) in parallel workers; non-atomic result/cache writes.
4. **Micro-Probe & Pre-Flight `--smoke` Gate Status**
   - Boundary-crossing unit tests (e.g., `n_samples = n_min - 1` vs. `n_min`), metamorphic invariance checks (scaling/symmetry), benchmark/evaluator sanity probes (ground-truth/oracle solvability, null-model rejection, garbage-padding monotonicity, zero-leakage/denominator checks when auditing evaluators/task banks), and `< 10 s` single-threaded local `--smoke` coverage across all case keys/caches.
5. **Machine-Readable Stage 0 Gate Verdict Block**
   - `stage0_verdict`: `ALIGNED_FAIL_LOUD` (ONLY when `p0_p1_count == 0`) vs. `SILENT_POLLUTION_RISK` (`p0_p1_count > 0`), `stage0_closed`, `blocking_pointers` (`file:line`), and `next_action` (`PROCEED_TO_HPC_OR_STAGE1A` vs. `BLOCK_AND_FIX_P0_P1`).

---

## Stage 1 Output Structure — Science Core & PI Supervision Gate (Stage 1A → Stage 1B)

Zero prose, grammar, or formatting nitpicks. Operates on Stage 0-verified, unpolluted data. Runs in **two gated sub-stages** (or together via `stage1` if explicitly requested):

### Stage 1A — Adversarial Baseline-Killer Circuit Breaker *(Reviewer 7 ONLY, bounded 1–3 rounds)*
- **Stopping rule:** Stop **immediately** once `p0_p1_count == 0` AND `baseline_verdict == SOLID_BASELINE` (do **not** run extra rounds; ignore minor P2 nitpicks; hard-capped at 3 rounds max). If `baseline_verdict == MECHANISM_SOLID_PARITY_FIX_NEEDED` (`p0_count == 0`, localized P1 parity/accounting/scope fixes only), you may launch **Stage 1B** in parallel and close Stage 1A via a quick diff-scoped recheck before Stage 2.
- **Advance trigger:** Launch **Stage 1B** (Reviewers 8 & 9 in parallel) once `stage1a_gate.can_advance_to_stage1b == true` (`SOLID_BASELINE`, or `MECHANISM_SOLID_PARITY_FIX_NEEDED` with `p0_count == 0`).

Produce these four sections for Stage 1A:
1. **Baseline Inventory & Literature Faithfulness Table**
   - Columns: `Baseline | Source (Author code vs. Reimplementation) | Key Heuristics in Code | Regime Match vs. Paper | Potential Handicap?`
2. **Detected Information Asymmetries, Handicaps & Unpulled Anomalies (P0 / P1)**
   - Exact `file:line` pointers, exact table/figure anomalies, quantitative impact on primary vs. secondary headline rows, and P0 vs. P1 classification (excluding P2 `<10–15%` polish and out-of-scope R8/R2 items).
3. **Top 2–3 Cheap Baseline-Killer Experiments (Minimal Patch or ≤ ~50-Line Textbook Pilot)**
   - Concrete code-level change (with realistic line-count/effort estimate), non-toy test system(s), estimated pilot runtime, quantitative expected impact, and explicit pass/fail criterion distinguishing **Repair** vs. **Discovery**.
4. **Stage 1A Gate Status & Verdict**
   - `baseline_verdict` (`SOLID_BASELINE` / `MECHANISM_SOLID_PARITY_FIX_NEEDED` / `REPAIR_RISK_PILOT_REQUIRED` / `HANDICAPPED_BASELINE_RERUN_REQUIRED`), exact `p0_count` & `p0_p1_count`, round `k/3`, and explicit status: **CLOSED → Launch Stage 1B**, **ADVANCE WITH LOCAL P1 FIXES → Launch Stage 1B in parallel**, or **OPEN → Fix P0/P1 & re-run Stage 1A**.

### Stage 1B — Domain Theory, Mechanism, Novelty & Senior Supervisor Gate *(Reviewers 8 & 9 in parallel, zero cross-talk)*
Launched once Stage 1A is closed. Reviewer 9 runs with `type_name="self"` (no file edits/shell) to execute 2–4 live `search_web` prior-art queries directly (also honoring any supplied `prior_art_summary`; see [stage1-domain-supervision-guide.md](./stage1-domain-supervision-guide.md)):

5. **Theoretical Foundations, Scaling, Bounds & Bias Check** *(Reviewer 8)*
   - Asymptotic scaling vs. constant factor (quantum & classical), distance to fundamental/oracle lower bounds, unbiasedness/bias–variance tradeoffs, exact symmetries/invariants, and analytically known limits.
6. **Causal Mechanism, Proxy Fragility & Failure-Mode Map** *(Reviewer 8)*
   - Quantitative driver of *why* the method works, regimes where it fails or saturates (e.g., strong correlation, stretched bonds, noisy/wrong proxies, non-local encodings), and benchmark diversity / finite-sample gaps.
7. **End-to-End Bottleneck & Target-Regime Audit** *(Reviewer 8)*
   - Net cost accounting (samples/queries vs. classical runtime/memory vs. implementation/hardware overhead vs. calibration budget) and target hardware/workflow fit.
8. **Contribution-by-Contribution Novelty & Target Venue-Bar Audit** *(Reviewer 9 live web/arXiv search)*
   - Table: `Claimed Contribution | Novelty Tier (new_math_or_algorithm / cross_domain_transfer / empirical_discovery / incremental_tweak / subsumed_or_overlap) | Closest Prior Art | Genuine Delta & Overlap Risk`
   - Missing or overlapping recent arXiv/journal prior art verified via live search or `prior_art_summary` (never invented).
   - Irreducible 1–2 sentence new idea and `novelty_verdict` vs. `target_venue` (`CLEAR_NOVELTY_ABOVE_BAR`, `BORDERLINE_NEEDS_SHARPER_DIFFERENTIATION`, or `OVERLAP_OR_INCREMENTAL_RISK`).
9. **Cross-Field Knowledge Connections, Conceptual Elevation & Red-Teamed Pivot Table** *(Reviewer 9 + Bounded 1-Round Blind Pivot Red-Team)*
   - Bridges to neighboring fields/methods, theorem/bound opportunities, minimal-core simplification/ablations, and clear boundary between *this paper* vs. *future work*.
   - **Red-Teamed Pivot Table (mandatory whenever Pivots/reframings are proposed):** `Pivot | Strongest Cheap Baseline | Primary Math / Scaling / Overlap Trap | Verdict (SURVIVES_RED_TEAM / VIABLE_WITH_PATCH / NEEDS_FRESH_SCREEN / DROP_PIVOT) | 1-Line Trim / Next Gate`. Never recommend `DROP_PIVOT`; treat `NEEDS_FRESH_SCREEN` strictly as an unvetted lead requiring a fresh blind Day-0 screen / Stage 1 (`skip_pivot_red_team=true`) before coding (0 survivors is valid).
   - **Conditional — Design-Space Constraints (ONLY when 0 Pivots earn `SURVIVES_RED_TEAM` or `VIABLE_WITH_PATCH`):** Emit a compact 4-bullet box (colleague-safe tone, strictly necessary conditions — never an unvetted 4th Pivot): *Baseline floor to beat*, *Non-negotiable invariants*, *Verified open window*, and *5-minute whiteboard litmus test*.
10. **Referee #2's Full Pre-Mortem & Kill-Shot Action** *(Reviewer 9 — full multi-point pre-mortem reserved for Stage 1; `idea-novelty-screen` uses a 2-sentence objection)*
    - Referee #2's sharpest 3-sentence rejection argument (including novelty/overlap angles), and the single highest-leverage derivation/experiment/reframing to neutralize it.
11. **Prioritized Supervisor Questions & Stage 1 Readiness Verdict (Before Advancing to Stage 2)**
    - Concrete research-development questions for the author, plus a clear Go/No-Go recommendation on what science/novelty positioning must be settled before running Stage 2.

---

## Stage 2 Output Structure — Narrative Structure, Provenance, Claims, Presentation & Compression (`stage2` = 2A + 2B together; `stage2a` / `stage2b` standalone)

**Default (`stage2`):** Runs Stage 2A (Reviewers 1–5) and Stage 2B (Reviewer 10) together in parallel so the Main Agent pairs additive items against compression/demotion in one pass. Either sub-stage can also be invoked standalone (`stage2a` or `stage2b`).

### Stage 2A — Narrative Structure, Completeness, Provenance, Claims & Presentation Gate *(Reviewers 1–5 in parallel, zero cross-talk)*

**Active reviewers:** `structure_narrative`, `reproducibility_code`, `claims_definitions`, `prose_style`, `figures_refs_format`, plus `average_reader` (R11, `flash`, compiled Main + SI PDFs preferred, review mode, advisory).

Produce these sections in order (skip a section only if truly empty — write `"None found"`):

1. **Paper Structure, Pedagogical Architecture & Motivation Assessment** *(Reviewer 1 — writing guide + reader-first craft)*
   - Title & short-route parity (`Title -> Abstract -> Figures+Captions -> Conclusions` tells one same-scope story; shortening a title never broadens claims), Abstract (5 functions in a compact paragraph within journal limits, prior work vs. new delta boundary, zero internal acronyms/shifting-baseline chains, 1–2 plain-language headline numbers), Introduction (central question before implementation taxonomy, concrete motivation without `"only way"` hype, polite prior-work positioning, stop-before-the-choice & combined-method interaction, teaser), Methods/Theory (decision before schedules/priors/solvers; minimal concrete toy example before general notation; estimator defined before optimization objective; Propositions/Theorems placed *after* the objective they bound; plain English before nicknames; non-historical optimal flow; 0-token math-wall, symbol-density & unanchored-stretch triage), Results/Benchmarks (model/plot rationale, trend explanation vs. narration, checked surprising findings treated honestly), Conclusions (restraint), descriptive discourse lacking a clear point, plus optional `structural_blueprint` (reordering steps + grounded 2–4 sentence specimen openings).
2. **Missing-Information, Definitions & Operational Edge-Case Spec Sync** *(Reviewer 3)*
   - For each item: **What is missing / inconsistent** | **Where** | **Target Slot (`main_text_one_clause` vs. `table_footnote_or_si`)** | **Question for the author**.
   - Cover undefined symbols/acronyms/metrics, one-name-for-one-concept consistency (drifting near-synonyms), implicit assumptions, **three-way epistemic separation** in Theory/Methods (exact identity under explicit space/assumptions vs. justified approximation vs. empirical observation), and **Main Methods vs. SI operational edge-case spec sync** (caps, fallbacks, ties, uncertified outputs, diagnostic return values).
3. **Ambiguous Statements, Forward Refs & Science-Altering Syntax** *(Reviewers 3 & 4)*
   - Quote each ambiguous scientific statement, dangling reference (`which`/`that`/`this`/`these`/`it`/`in that case`), structural forward reference, blurry physical-action phrasing, or science-altering syntax slip (restrictive `that` vs. `, which`, replacement direction, trend direction, incomplete comparison, `"obviously"`/`"clearly"`), list possible interpretations, and ask which is intended.
4. **Manuscript Provenance & Reproducibility Metadata** *(Reviewer 2 — white-box code-vs-math logic is handled in Stage 0)*
   - Classify as **sufficient**, **mostly sufficient with minor gaps**, or **insufficient**.
   - Audit documented benchmark systems/datasets, discretizations/model specifications, grids, thresholds, cutoffs, software versions & citations/bib entries, random seeds/sample budgets/averaging protocols, explicit uncertainty definitions (SD/SE/CI + $N$; sampling vs. model/basis/convergence error; residuals $\ll$ error bars caveat), table precision honesty (missing vs. `0`, convergence digits vs. physical accuracy), archive/reproducibility manifest, script-to-table/figure provenance mapping, exact metric definitions, reported verification summaries, and textbook filler omitting the authors' own formulation.
5. **Unsupported, Overstrong, or Overly Hedged Conclusions** *(Reviewer 3)*
   - Overstrong/unsupported claims: claim, why data fall short, what data/analysis/qualification is needed.
   - Unnecessary hedging (`might/may/can be` where narrower `is/are/will` is justified by the data).
6. **Conclusions Present in Data That Should Be Stated More Clearly** *(Reviewer 3)*
   - Templates with `[AUTHOR: ...]` placeholders only.
7. **Possible Additional Conclusions** *(Reviewer 3)*
   - Each labeled **Possibility:** with what is needed to confirm it.
8. **Repetitions, Textual Precision, Figures, References & LaTeX Hygiene** *(Reviewers 4 & 5 — writing guide)*
   - Purpose-based repetitions (text repeating figures/tables without analysis; captions making figures/tables standalone vs. main-text explanation; rewriting cited/textbook work), bracket/dash abuse, filler pruning without cutting helpful orienting transitions, repetitive transitions & `thus/hence/therefore/ergo` precision, sentence-initial structural references (`Equation`/`Figure`/`Table`/`Section`), LaTeX quotes & math-mode variable consistency, figure standards (final printed-size legibility after 1-column reduction, PDF or EPS vector, color + line-style/marker redundancy, short panel labels ok / ban caption-repeating titles, plot-line & uncertainty honesty), and reference completeness, uniformity, and claim-to-citation accuracy.
9. **Blind Average-Reader Skimmer & Teach-Back Audit** *(Reviewer 11 `average_reader`, `flash`, compiled Main + SI PDFs preferred, automatic 2-pass Main-only $\to$ Main+SI when $\ge 2$ files provided, advisory)*
   - Main Agent cross-checks R11's plain-English reconstruction (`problem`, `prior_work_vs_new_delta_from_abstract`, `method_steps`, `headline_result_and_baseline`, `main_limitation`), forced `walkout_point`, ranked `friction_hotspots` (`math_wall_no_intuition`, `story_detour`, `working_memory_overload`, `prose_breaks_if_math_skipped`, `pacing_drag`), `where_i_got_lost_or_bored`, and (when 2-pass active) `pass1_main_only` + `two_pass_si_audit` against the actual draft, promoting genuine reading-friction / Main-vs-SI drop-off points into the action list and discarding obvious small-model slips.
10. **Stage 2A Author Action List (Before Advancing to Stage 2B)**
   - **Essential structural/provenance/scientific fixes required before Stage 2B:**
   - **Clarifications to add:**
   - **Formatting/figure/reference fixes:**

### Stage 2B — Ruthless Compression & Triage Pass *(Reviewer 10 `conciseness_editor` ONLY — Anti-Ping-Pong Safe)*

Runs in parallel with Stage 2A by default under `stage2` (Main Agent pairs Stage 2A additions against Stage 2B cuts/demotions), or standalone right **before** Stage 3 via `stage2b` with `protected_requirements` pointing to the Stage 2A review. **Anti-Ping-Pong Invariant:** Stage 2A decides *whether* scientific information must exist; Stage 2B decides *where* it lives and *how compactly* it is expressed—never recommending `cut` on any unique parameter, seed, metric, caveat, or provenance item.

Produce these sections in order:
1. **Length & Bloat Diagnostic (Main Text + SI vs. `length_budget`)**
   - Current estimated footprint (pages, tables, figures, SI sections) vs. target budget and primary bloat drivers.
2. **4-Bucket Compression & Triage Ledger**
   - Table: `Tier (tier1_prose_only / tier2_table_or_script_refactor / tier3_author_policy) | Action (cut / merge_squeeze / demote_main_to_si / archive_si_to_repo) | Scope | Location | Est. Savings | Replacement Pointer & Archive Status (exists_on_disk / must_generate_before_cutting) | Preserves Reproducibility & Main-Text Honest Limits?`
3. **Anti-Ping-Pong Verification Summary (Ready for Stage 3)**
   - Explicit confirmation that zero Stage 1/2A-required facts, definitions, caveats, or provenance pointers are lost—so no return loop to Stage 2A is needed before Stage 3.

---

## Stage 3 Output Structure — Natural Prose, Grammar & Word Editing Pass

**Hard Gate:** Run Stage 3 **only after all Stage 0, Stage 1 (1A + 1B), and Stage 2 science issues are resolved** (never polish prose over silent numerical pollution, unfixed baselines, missing parameters, or unsupported claims).

**Active reviewer:** Reviewer 6 (`grammar_humanizer`) ONLY — adopted from [academic-humanizer-guide.md](./academic-humanizer-guide.md).

Produce these sections in order:

1. **Grammar & Sentence-Mechanics Audit**
   - Subject-verb agreement, articles, tense consistency, syntax, and splitting overlong clause-stacked sentences (> ~30 words or 3+ subordinate clauses).
2. **AI-Writing Tells & Scholarly Voice Audit**
   - General AI tells (buzzwords, superficial `-ing` tails, copula avoidance, negative parallelisms, rule-of-three padding, elegant variation, em-dashes `—`/`---`) and academic AI tells (over-claiming verbs, significance hype, empty intensifiers, novelty padding, formulaic openers, consecutive connectives, citation dumping, hedging-by-vagueness, boilerplate emphasis).
   - Explicitly note preserved scholarly conventions (evidence-tied hedging, appropriate passive voice, `"we"`, formal definitions, equations, numbers, citation keys).
   - If `doc_type` is `proposal`/`nsf`/`nih`, include Layer 6 proposal-craft & claim↔feasibility audit.
3. **Word Edits Applied / Proposed & Integrity Verification**
   - List all meaning-preserving word edits applied (or proposed if review-only), with file links and an explicit confirmation that **zero numbers, equations, symbols, definitions, or citation keys were altered or invented**.
   - List any remaining `[AUTHOR: ...]` items where removing an empty intensifier or vague magnitude requires author-supplied numbers.

---

## Revision Re-Check Structure (`mode: "recheck"` — Usable at Any Stage, Diff-Scoped + P0/P1 Freeze)

When the author returns with a revision to verify fixes from an earlier pass of Stage 0, Stage 1A, Stage 1B, Stage 2 (2A/2B), or Stage 3 (prefer passing `git_ref` or `diff_file` + `previous_review` so reviewers inspect only open issues + changed lines):

Additional rules:
- Count an issue as fixed **only** if explicitly fixed in the revised code/report. Never assume.
- Give **zero credit** for cosmetic or vague changes (docstrings masking silent fallbacks, *"carefully chosen"*, SI caveats burying an unfixed baseline handicap, *"the code was tested"* with no details).
- **Universal P0/P1 Freeze (Anti-Goalpost-Shifting):** Verify prior open P0/P1 items and diff regressions only — do NOT re-audit untouched text to manufacture new P2 nitpicks. Close the stage as soon as `stage_gate.total_p0_p1_count == 0` (plus `ALIGNED_FAIL_LOUD` for Stage 0 / `SOLID_BASELINE` for Stage 1A).
- For partial fixes, state what improved and what remains missing, quoting the revision as evidence.

Produce:
1. **Stage Readiness Verdict** — Exactly one of:
   - **Ready to advance / share.** (Stage 0 must show `ALIGNED_FAIL_LOUD` with `p0_p1_count == 0`; Stage 1A must show `SOLID_BASELINE` with `p0_p1_count == 0`.)
   - **Almost ready, but minor clarifications are still needed.**
   - **Not ready; important information is still missing.**
   - **Not ready; major code-integrity, scientific, baseline, or provenance gaps remain.**
2. **Issue-by-Issue Assessment Table** — Columns: `Original issue | Status (Addressed / Partially addressed / Not addressed / Unclear) | Evidence from revision | Remaining problem | Author action still needed`.
3. **New Problems Introduced by the Revision** — New unapproved branches/fallbacks, contradictions, new undefined symbols, altered numbers/citations, new AI tells/em-dashes, or formatting regressions.
4. **Remaining Action Checklist** — Essential fixes required before advancing / Minor clarifications / Optional polishing.
