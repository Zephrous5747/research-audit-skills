---
name: idea-falsification-loop
description: >-
  Bounded, low-compute autonomous Generator + Falsification Loop built on top of
  `idea-novelty-screen`, `code-math-alignment`, and `baseline-killer-audit`.
  Iterates for at most `max_rounds` (default 3, hard cap 5): proposes one
  falsifiable idea, screens it live with a 1-round Pivot Red-Team, optionally
  runs a <60 s CPU toy Day-1 pilot gated by Stage 0 and Stage 1A, records every
  killed round and emitted `design_space_constraints` in a `GRAVEYARD` to block
  repackaging, and delivers a <=2-page human review handoff (`SURVIVOR_FOUND`,
  `EXHAUSTED_NO_SURVIVOR`, or fail-closed `BLOCKED_OFFLINE`).
---

# Idea Falsification Loop (Bounded Autonomous Generator + Verifier)

Thin outer orchestrator over the three pre-compute validity gates — **zero duplicated rubrics**. Invokes [idea-novelty-screen](../idea-novelty-screen/SKILL.md), [code-math-alignment](../code-math-alignment/SKILL.md) (Stage 0), and [baseline-killer-audit](../baseline-killer-audit/SKILL.md) (Stage 1A) verbatim inside a strict, fail-closed loop capped at `max_rounds <= 5`.

## Architecture (Fail-Closed State Machine)

```text
Inputs: problem_space, domain, track, max_rounds (default 3, cap <= 5),
        run_day1_pilot (default false), skip_local_overlay ("auto"), optional cutoff_year
        │
        ▼  For r = 1 .. max_rounds:
  1. Propose (Generator):
     - Emit ONE concrete, falsifiable idea (mechanism, claim, why cheap baseline fails, <60 s CPU test).
     - For r > 1: enforce explicit non-overlap with GRAVEYARD + compliance with accumulated design_space_constraints.
        │
        ▼
  2. Screen (`idea-novelty-screen` verbatim via `screen_idea.py`):
     - `NEEDS_LIVE_SEARCH_VERIFICATION` (or offline search on hard-novelty track) ──► HALT (`BLOCKED_OFFLINE`)
     - Killed (`0/N` survivors) or only `NEEDS_FRESH_SCREEN` ──► append failure + constraints to GRAVEYARD, next r
     - `PROCEED_TO_PROTOTYPE` or surviving `SURVIVES_RED_TEAM` / 1-sentence `VIABLE_WITH_PATCH`:
         • `run_day1_pilot == false` ──► STOP (`SURVIVOR_FOUND`)
         • `run_day1_pilot == true`  ──► Step 3
        │
        ▼
  3. Day-1 Falsification Pilot (`run_day1_pilot == true` ONLY):
     - Local CPU only, single-file toy script (<60 s total, `--smoke` <10 s), zero HPC/SLURM, zero sweeps/tuning.
     - Matched inputs/budgets vs. strongest cheap baseline (<=~50 lines or library call).
     - Gate A: `code-math-alignment` (Stage 0) MUST return `ALIGNED_FAIL_LOUD`, `p0_p1_count == 0`, not `blocked_by_permission`.
     - Gate B: `baseline-killer-audit` (Stage 1A) MUST return `SOLID_BASELINE` or `MECHANISM_SOLID_PARITY_FIX_NEEDED` with `p0_count == 0`.
     - Any pilot/Stage 0/Stage 1A failure ──► log exact defect to GRAVEYARD (NO same-round patching), next r.
     - Both pass ──► STOP (`SURVIVOR_FOUND`).
        │
        ▼
  Loop exhausted ──► STOP (`EXHAUSTED_NO_SURVIVOR`) with GRAVEYARD + consolidated design_space_constraints.
```

---

## Step 1: Launch `run_workflow` (Antigravity)

Call `run_workflow` with `ScriptPath` resolved to [run_idea_loop.py](./scripts/run_idea_loop.py) relative to this `SKILL.md` directory:

```json
{
  "problem_space": "Low-variance estimators for sparse non-symmetric linear systems",
  "domain": "numerical linear algebra",
  "track": "numerical_algorithm",
  "max_rounds": 3,
  "run_day1_pilot": false,
  "skip_local_overlay": "auto"
}
```

**Parameters:**
- `problem_space` *(required)*: Target scientific problem space or open bottleneck.
- `domain` *(recommended)*: Explicit research domain string (cross-domain values auto-suppress mismatched `local_config.yaml` / `local_overlay.md` when `skip_local_overlay="auto"`).
- `track`: `"numerical_algorithm"` *(default)*, `"pure_theory"`, or `"engineering_portfolio"`.
- `max_rounds`: Default `3`, hard-capped at `5` (raises on `< 1` or `> 5`).
- `run_day1_pilot`: `false` *(default, paper-only screening)* or `true` *(adds `< 60 s` CPU toy pilot + Stage 0 + Stage 1A)*.
- `skip_local_overlay`: `"auto"` *(default)*, `true`, or `false`.
- Optional passthroughs: `cutoff_year`, `target_venue`, `prior_art_summary`, `context`, `pilot_dir`, `agent_type`, `model`.

**Non-Antigravity Hosts (Claude Code / OpenAI Codex):** `run_idea_loop.py` uses Antigravity's `run_workflow`. On Claude Code or Codex, execute the exact same fail-closed loop round by round (`r = 1 .. max_rounds <= 5`):
1. Export the round's Generator prompt/schema via `python scripts/export_panel.py export --workflow loop --problem-space "..." --domain "..." --track <track> --out-dir .loop_r1` (pass `--graveyard-json .graveyard.json` on `r > 1`).
2. Screen the proposed pitch via `python scripts/export_panel.py export --workflow screen ...` using isolated read-only subagents (`BLOCKED_OFFLINE` halts immediately; kills append failure + `design_space_constraints` to `.graveyard.json`).
3. If `run_day1_pilot=true` and the idea clears screening, write and run one `< 60 s` local CPU toy script (`--smoke < 10 s`), then gate it with `export_panel.py export --workflow review --stage stage0` and `--stage stage1a` (evaluating gates with `export_panel.py gate`; any failure logs to `.graveyard.json` and advances to `r + 1` with zero same-round patching).

---

## Step 2: Deliver the Half-Day Human Review Handoff (`<= 2` Pages)

Synthesize the workflow output into a concise, scannable handoff (**strictly `<= 2` pages**, zero invented numbers or unverified citations):

1. **Header & Terminal Verdict:**
   - `Terminal Status`: `SURVIVOR_FOUND` | `EXHAUSTED_NO_SURVIVOR` | `BLOCKED_OFFLINE`
   - `Track` | `Domain` | `Rounds Run (r / max_rounds)` | `Day-1 Pilot Enabled (true/false)` | `Local Overlay Applied`
2. **If `SURVIVOR_FOUND`:**
   - **1-Page `idea-novelty-screen` Go/Pivot Card** (verdict, red-teamed Pivot table if a vetted pivot survived, verified closest prior art).
   - **Referee #2 Fatal Objection** (strictly 2 crisp sentences) + **Explicit Failure Boundary Conditions** (regimes where the mechanism breaks).
   - **If `run_day1_pilot == true`:** Exact `< 60 s` CPU repro command, `--smoke` command, compact toy comparison table vs. strongest cheap baseline, and exact Stage 0 (`ALIGNED_FAIL_LOUD`) + Stage 1A (`SOLID_BASELINE` / `MECHANISM_SOLID_PARITY_FIX_NEEDED`, `p0_count=0`) verdicts.
3. **If `BLOCKED_OFFLINE`:**
   - State exact offline search block (`live_search_status`) and halt — never fabricate a pass or advance without live verification.
4. **`GRAVEYARD` Summary (Always Included):**
   - Strictly 1–2 concise bullets per killed round (`Round r | Idea | Exact Failure Mode / Gate Rejection`).
5. **Consolidated `design_space_constraints` (Mandatory when `EXHAUSTED_NO_SURVIVOR`):**
   - Deduplicated 4-bullet next-iteration design checklist (*Baseline floor to beat*, *Non-negotiable invariants*, *Verified open window*, *5-minute whiteboard litmus test*) — never pitch an unvetted extra idea.
