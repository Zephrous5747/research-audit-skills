---
name: idea-novelty-screen
description: >-
  Fast pre-code, pre-manuscript blind multi-agent screening (1-page Kill-Card
  mode) with upfront track routing (`numerical_algorithm`, `pure_theory`,
  `engineering_portfolio`), live web/arXiv novelty search, and a bounded 1-round
  Pivot Red-Team mini-pass. Screens an early pitch, rough math notes, or seed
  papers before writing code using 3 isolated blind scouts (zero cross-talk)
  plus an isolated red-team audit of every candidate Pivot. Use whenever the
  user proposes a new research idea, asks "has this been done?", wants a
  literature/novelty check before coding, or wants to stress-test and sharpen
  an early concept.
---

# Idea Novelty & Feasibility Screen (Fast Kill-Card Mode)

Pre-code companion to `scientific-report-review` (Stage 1) and `code-math-alignment` (Stage 0). Screens an early idea **before writing months of code** using **upfront track routing**, **3 blind parallel scouts**, and a **bounded 1-round blind Pivot Red-Team pass**, outputting a scannable **1-page Executive Kill-Card** plus a deduplicated **Evidence Appendix**.

**Boundary vs. `scientific-report-review`:** Use `idea-novelty-screen` for rapid pre-code triage (1-page Kill-Card, 2-sentence Referee #2 objection, red-teamed Pivots). Reserve full multi-point Referee #2 pre-mortems, code/manuscript rubric breakdowns, and Stage 0–3 gates for `scientific-report-review`.

## Architecture (Zero Cross-Talk + Bounded Pivot Red-Team)

```text
User Input (Idea pitch / rough equations / notes / optional seed papers)
        │
        ▼  Upfront Track Classification: `numerical_algorithm` | `pure_theory` | `engineering_portfolio`
Main Agent calls `run_workflow` -> `./scripts/screen_idea.py` (resolved relative to this SKILL.md)
        │
        ├──► Phase 1 (Parallel, Zero Cross-Talk):
        │      ├── Scout 1 (`baseline_feasibility_killer`, `research`): Track-routed cheap baseline + Day-1 pilot
        │      ├── Scout 2 (`theory_limits_critic`, `research`): Track-routed bounds/validity + labeled FM-k map
        │      └── Scout 3 (`literature_novelty_strategist`, `self`): 5-8 live `search_web` queries + 2-sent R#2 + Pivots
        │
        ├──► Phase 2 (Bounded 1-Round Blind Red-Team, `self` read-only + live `search_web`):
        │      └── Pivot Red-Team Auditor: checks every candidate Pivot vs. cheapest baseline, Phase 1 constraints & live subfield search
        │            -> `SURVIVES_RED_TEAM` | `VIABLE_WITH_PATCH` (1-sent trim only) | `NEEDS_FRESH_SCREEN` | `DROP_PIVOT`
        ▼
Main Agent verifies citations, enforces No-Repetition & No-Unvetted-Pivots rules, and emits Kill-Card + Appendix
```

---

## Step 1: Classify `track` Upfront & Launch `run_workflow`

1. **Classify `track` upfront** (accept user-supplied `track` or auto-classify and declare in the header):
   - **`numerical_algorithm`** — algorithmic/computational ideas: strict cheap code baselines (minimal patch, off-the-shelf library call, or ≤ ~50-line / ≤ 1 h textbook script), complexity/memory bounds, 24–48h toy + non-toy numerical falsification pilots, hard academic novelty gate.
   - **`pure_theory`** — theorems/proofs/conceptual frameworks: swaps code benchmarks for (i) tightest known existing theorem/no-go bound/classical reduction as cheap baseline, (ii) minimal adversarial counterexample suite, and (iii) 24–48h **analytic** falsification pilot (exact toy calculation, truth table, or proof-obstruction check), hard academic novelty gate.
   - **`engineering_portfolio`** — applied systems/portfolio builds: relaxes academic novelty to a **secondary note**, while keeping **strict** kill gates on mathematical validity, zero data leakage, domain realism, and standard practitioner baselines.
2. **Collect optional inputs:** `idea` (string) and/or `idea_files` (paths), `seed_papers`, `domain` (inherits optional gitignored `local_config.yaml` or defaults to `"computational science"`), `target_venue`, `context`, `previous_screen` (for Pivot Round 2 recheck).
3. **Call `run_workflow`:**
   - `ScriptPath`: Resolve `./scripts/screen_idea.py` relative to this `SKILL.md` directory.
   - `Description`: `"Screen research idea (track-routed blind scouts + 1-round Pivot Red-Team)"`
   - `Args`:
     ```json
     {
       "track": "numerical_algorithm",
       "idea": "Concise pitch or hypothesis...",
       "idea_files": ["notes/idea_sketch.md"],
       "seed_papers": ["arXiv:2305.xxxxx"],
       "domain": "computational science",
       "target_venue": "Target Journal / Conference"
     }
     ```
   - Optional knobs: `scouts`, `candidate_pivots`, `skip_pivot_red_team` (default `false`), `skip_local_overlay` (default `"auto"`, auto-suppressing lab `local_overlay.md` / venues / arXiv categories on cross-domain `domain` overrides), `agent_type` (`"auto"` default), `model` (`"inherit"` default).
4. **Non-Antigravity Hosts (Claude Code / OpenAI Codex):** If `run_workflow` is unavailable, read the track-routed scout scopes and Phase 2 Pivot Red-Team rubric from `./scripts/screen_idea.py`, spawn the 3 isolated Phase 1 subagents in parallel via your host's native subagent tool (read-only + web search for Scout 3; read-only for Scouts 1–2, zero cross-talk), then run 1 isolated read-only + web-search Phase 2 Pivot Red-Team subagent over Scout 3's candidate Pivots and Phase 1's derived constraints.

---

## Step 2: Verification & Deduplicated Output (Kill-Card + Evidence Appendix)

Once `run_workflow` finishes:
1. **Verify citations & Pivot gating (mandatory):**
   - Confirm every cited paper has a real URL/arXiv ID/DOI (discard unverified citations; if `live_search_status == "blocked_or_offline"`, run 3–5 `search_web` checks directly before finalizing).
   - **No Unvetted Pivots:** Never recommend `DROP_PIVOT`. Treat `NEEDS_FRESH_SCREEN` (any multi-part rewrite, new mechanism, or domain switch) strictly as an unvetted lead requiring a fresh blind Day-0 screen (`skip_pivot_red_team=true`) before coding — only `SURVIVES_RED_TEAM` or strictly scope-trimmed `VIABLE_WITH_PATCH` may go directly to a Day-1 pilot (0 survivors is valid).
   - **No-Repetition Rule:** Explain each failure mechanism **once in full** inside the Evidence Appendix (tagged `FM-1`, `FM-2`, ...). In the Kill-Card, reference those mechanisms concisely by ID/phrase only — never repeat the same kill explanation across Verdict, Referee #2, and Failure-Mode Map.
2. **Deliver the report in this exact two-part structure:**

### Part 1 — 1-Page Executive Kill-Card
1. **Header Metadata:** `Track` (`user_supplied`/`auto_inferred`) | `Gate Verdict` (`PROCEED_TO_PROTOTYPE` / `PIVOT_BEFORE_CODING` / `KILL_OR_REFRAME`) | `Novelty Verdict` (`hard_gate` or `secondary_note`) | `Live Search` (`searched_live` / `blocked_or_offline`).
2. **Decisive Verdict (Strictly 3 Bullets, Zero Prose Padding):** Core go/pivot/kill reason referencing Appendix IDs (`FM-k`, closest paper) without repeating full derivations.
3. **Red-Teamed Pivot Comparison Table:**
   - Columns: `Pivot | Strongest Cheap Baseline | Primary Math / Scaling / Overlap Trap | Verdict (SURVIVES_RED_TEAM / VIABLE_WITH_PATCH / NEEDS_FRESH_SCREEN / DROP_PIVOT) | 1-Line Trim / Next Gate`
   - **Conditional — Design-Space Constraints (ONLY when 0 Pivots earn `SURVIVES_RED_TEAM` or `VIABLE_WITH_PATCH`):** Add a compact 4-bullet box (colleague-safe, strictly necessary conditions — never an unvetted 4th Pivot): *Baseline floor to beat*, *Non-negotiable invariants*, *Verified open window*, and *5-minute whiteboard litmus test*.
4. **Concise Day-1 Falsification Pilot (24–48h, Track-Appropriate):**
   - Exact setup (numerical toy + non-toy for `numerical_algorithm`; analytic toy/truth-table/proof-obstruction for `pure_theory`; leakage-free realistic split vs. off-the-shelf baseline for `engineering_portfolio`) + strict **Kill** vs. **Build** criteria.
5. **Referee #2 Fatal Objection:** Strictly **2 crisp sentences** (reserve full multi-point pre-mortems for `scientific-report-review` Stage 1).

---

### Part 2 — Evidence Appendix *(below horizontal divider)*
1. **Verified Literature & Cross-Field Terminology Table:**
   - Table (`Paper / arXiv / Year | Field | Overlap / Scoop Risk | What Remains Open`) + cross-field terminology translations.
2. **Failure-Mode & Theoretical-Constraint Map (`FM-1`, `FM-2`, ...):**
   - Full explanation (once) of scaling/bounds, validity/invariants/leakage risks, cost shifting, and win-vs-break regimes.
3. **Lifecycle Handoff:** Once a Day-1 pilot passes, hand off to **`code-math-alignment`** (Stage 0) before HPC sweeps, then **`scientific-report-review`** (Stages 1–3).
