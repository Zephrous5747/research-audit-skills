# Example 1 — Pre-Code Idea Screen & Pivot Red-Team Kill-Card (`idea-novelty-screen`)

> **Scenario:** Before writing a solver or burning GPU/HPC hours, a researcher pitches a hybrid variance-reduced adaptive subspace estimator (`numerical_algorithm` track). Three blind scouts (Baseline Killer, Theory/Limits Critic, Live Literature Strategist) run in parallel with zero cross-talk, followed by a 1-round blind Pivot Red-Team pass over candidate reframings.

---

## Part 1 — 1-Page Executive Kill-Card

- **Track:** `numerical_algorithm` (`user_supplied`)
- **Gate Verdict:** `KILL_OR_REFRAME`
- **Novelty Verdict (`hard_gate`):** `OVERLAP_OR_INCREMENTAL_RISK`
- **Live Search:** `searched_live` (Phase 1 + Phase 2 verified)

### Decisive Verdict
- **Killed by cheap baseline + cost shift (`FM-1`):** The proposed multi-stage adaptive resampling reduces per-iteration variance by ~2.5x only by shifting 3.8x extra matrix-vector evaluations into the pilot scoring step; a 15-line antithetic + control-variate patch on the standard fixed-basis solver matches accuracy at lower total wall-clock cost.
- **Prior-art collision (`FM-2`):** Two recent arXiv preprints already combine adaptive subspace selection with stratified variance reduction under different subfield terminology (*"greedy Krylov control variates"* and *"importance-weighted active subspaces"*), leaving no clear novelty wedge for the current formulation.
- **0/3 candidate Pivots cleared Red-Team:** Two proposed Pivots fall to simple off-the-shelf preconditioning/sorting floors, and the third requires introducing a brand-new estimator object (`NEEDS_FRESH_SCREEN`) rather than a 1-line scope trim.

### Red-Teamed Pivot Comparison Table

| Pivot | Strongest Cheap Baseline | Primary Math / Scaling / Overlap Trap | Verdict | 1-Line Trim / Next Gate |
| :--- | :--- | :--- | :--- | :--- |
| **P1: Reuse pilot samples across iterations** | Fixed-basis solver + 15-line common random numbers (CRN) | Sample reuse introduces adaptive selection bias $\mathcal{O}(\sqrt{\log M / N})$ (`FM-3`); bias exceeds variance gain at $N \le 10^4$. | `DROP_PIVOT` | N/A |
| **P2: Benchmark/phase-diagram study across sparsity regimes** | Existing survey & benchmark suite in numerical linear algebra | Already subsumed by prior empirical studies; no new scaling law or non-trivial phase boundary established. | `DROP_PIVOT` | N/A |
| **P3: Certifiable stopping rule via martingale concentration** | Standard empirical-Bernstein bound on fixed basis | Introduces a new stopping-time estimator & proof object (not a 1-line trim); unvetted against sequential-testing prior art. | `NEEDS_FRESH_SCREEN` | Re-run a fresh blind Day-0 screen focused solely on the martingale stopping rule before coding. |

> **Design-Space Constraints (0/3 Pivots Cleared Directly — Next-Iteration Checklist)**
> - **Baseline floor to beat:** Fixed-basis solver + 15-line control-variate / CRN patch, measured on *total* function/matvec evaluations including pilot overhead.
> - **Non-negotiable invariants:** Strict sample splitting (or provably unbiased reweighting) between selection and estimation to eliminate adaptive selection bias (`FM-3`).
> - **Verified open window:** Any-time valid stopping criteria for ill-conditioned non-symmetric operators where naive empirical-Bernstein bounds are loose by $> 5\times$.
> - **5-minute whiteboard litmus test:** Write total cost $C_{\text{total}} = C_{\text{pilot}} + C_{\text{est}}$ in closed form; if $C_{\text{pilot}}$ scales linearly with ambient dimension $d$, reject before coding.

### Day-1 Falsification Pilot (24h, Before Any Refactoring)
- **Setup:** Single synthetic 200-dim ill-conditioned test matrix + one real benchmark instance; compare proposed method vs. fixed-basis solver + 15-line CRN/control-variate patch at matched **total** matvec budget ($10^3$–$10^5$).
- **Kill Criterion:** Proposed method fails to achieve $\ge 2\times$ lower total-budget RMSE than the 15-line CRN patch.
- **Build Criterion:** $\ge 2\times$ net total-budget win *after* including all pilot overhead and strict sample splitting.

### Referee #2 Fatal Objection
This method shifts compute from estimation into an uncounted pilot selection phase and is outperformed at matched total evaluations by a standard control-variate baseline. Moreover, adaptive subspace variance reduction is already established under Krylov control-variate literature without demonstrating a distinct scaling advantage here.

---

## Part 2 — Evidence Appendix *(Summary Excerpt)*

| Failure ID | Mechanism | Win vs. Break Regime |
| :--- | :--- | :--- |
| **`FM-1`** | Uncounted pilot matvec overhead inflates apparent per-step speedup by ~3.8x. | Only wins when pilot cost is amortized across $\ge 20$ downstream queries on the *same* operator. |
| **`FM-2`** | Cross-field terminology overlap ("adaptive subspace sampling" $\equiv$ "active Krylov control variates"). | Novelty requires an algorithmic or theoretical advance absent from both fields. |
| **`FM-3`** | Reusing selection samples for estimation creates $\mathcal{O}(\sqrt{\log M / N})$ winner's-curse bias. | Breaks whenever candidate pool size $M$ grows faster than $N$. |
