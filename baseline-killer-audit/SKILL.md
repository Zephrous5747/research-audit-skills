---
name: baseline-killer-audit
description: >-
  Adversarial "hostile supervisor" baseline and mechanism audit ("How much did
  we save? Compared to which baseline?"). Use BEFORE launching large cluster
  sweeps or production benchmarks, AFTER initial pilot results, or alongside
  manuscript review to test whether a headline speedup is genuinely new or an
  artifact of a handicapped baseline, information asymmetry, unfaithful external
  reimplementation, or buried anomaly. Completely ignores prose and formatting
  and focuses exclusively on trying to break or shrink the headline claim with
  the strongest cheap baseline a skilled practitioner would actually implement
  (a minimal ~5–20 line patch, off-the-shelf library call, or simple ≤~50-line
  textbook baseline).
---

# Baseline-Killer Audit (Adversarial Supervisor Gate)

This skill encodes the single sharpest instinct of an experienced research supervisor: **"How much did we actually save, and compared to which baseline?"**

General paper reviews spread attention across 30+ prose, formatting, and table checks and subconsciously treat an existing benchmark pipeline as fixed. This skill has **zero prose or formatting duties**. Its sole mission is to read the exact baseline and method code side by side, check literature baselines for faithfulness, pull every anomalous result thread, and try to **collapse or sharply shrink the headline speedup using a cheap baseline (a minimal ~5–20 line patch to an existing baseline, an off-the-shelf library call, or a simple single-file textbook baseline ≤ ~50 lines / ≤ 1 hour to code, at a fraction of the proposed method's compute cost)**.

Use this skill at **two gates**:
1. **Pre-Compute Design Gate** — *before* burning cluster node-hours on large sweeps.
2. **Pre-Submission Adversarial Audit** — standalone or loaded directly as **Reviewer 7** inside `scientific-report-review`.

---

## The Five Mandatory Audit Rules

### Rule 1 — The "Strongest Cheap Baseline" Test (Non-Toy Pilot Gate)
List every heuristic, ordering, initialization, stopping rule, grouping, rounding, or regularization choice inside the main baseline $B$.
- For each choice, ask: **what is the strongest cheap upgrade to $B$ a skilled practitioner would actually implement first** — either a **minimal targeted patch (~5–20 lines)** to existing repo code, an **off-the-shelf library call**, or a **simple single-file textbook baseline ($\le \sim 50$ lines / $\le 1$ hour to code)** at a small fraction of $M$'s complexity/runtime? *(Report realistic code size honestly; never require a heavyweight new-research baseline, and never skip a strong 30-line textbook baseline just to stay under 10 lines.)*
- **Objective–proxy alignment (including shared front-ends):** Do not treat a heuristic, scoring rule, weighting, or aggregation ported from a related single-target task—or shared identically by both $B$ and $M$—as fixed. Check whether its mathematical functional form matches *this* task's actual decision objective (e.g., sum vs. max/minimax/pairwise contrast, average vs. tail risk, uniform vs. variance-weighted, full-set vs. active-subset); an objective-aligned cheap fix to a shared front-end can lower absolute costs for both $B$ and $M$ and change which downstream mechanism still pays off.
- **Non-toy requirement:** NEVER validate baseline choices only on the smallest toy system (e.g., tiny 4–8-variable or synthetic inputs). Correlations, scaling cliffs, and solver bottlenecks often have $\approx 0$ effect on toy problems and dominate at realistic problem sizes. Always test cheap baseline upgrades on at least one **non-toy medium/hard instance** before scaling up.
- **Quantitative impact sizing:** For every cheap baseline upgrade you propose, state explicitly *which benchmark systems/regimes are affected, its approximate magnitude, and whether the primary non-toy headline gain still survives*. A patch that trims a small secondary regime by 20–30% while large non-toy targets retain a multi-fold advantage is a localized P1 caveat/parity item—not a headline-collapsing P0.

### Rule 2 — The "Information-Asymmetry / Double-Standard" Code Audit
Read the exact setup/constructor code for both the proposed method $M$ and every baseline $B$ **side by side** (never rely solely on prose descriptions in the manuscript).
- Flag every piece of cheap information (e.g., problem coefficients/weights, symmetries, candidate structure, exact/approximate bounds, tolerances, sample reuse) that $M$ or any subroutine of $M$ (such as preprocessing, warm-starting, or partitioning) already uses, **but that is withheld from $B$**.
- **Interaction & input parity (for iterative/agentic benchmarks):** Check whether one arm receives multi-step retries, tool outputs, or leaked ground-truth oracle diagnostics (e.g., nested match/count error fields) while baselines run blind 1-shot, or whether required inputs/metadata (such as instrument/group labels) are silently withheld from one arm's runtime environment.
- **Fairness principle:** Give all free/cheap information to the baseline $B$ first, so that any remaining ratio $B / M$ isolates the genuine new algorithmic mechanism rather than an unfair handicap.

### Rule 3 — The "Repair vs. Discovery" Mechanism Diagnostic
Whenever an expensive optimizer or complex method $M$ beats a simpler baseline $B$ by a substantial factor (e.g., $1.5\text{--}3\times$):
- Ask: **is $M$ discovering a genuinely better mathematical optimum, or is $M$ merely repairing a poor initialization/heuristic inside $B$?**
- **Diagnostic test:** Upgrade $B$'s initialization/heuristic with the best cheap rule from Rules 1–2 and compare *both* $B_{\text{new}}$ and $M_{\text{new}}$:
  - If $B$ drops sharply (e.g., $2\times$) while $M$'s absolute cost stays flat $\implies$ $M$ was **repairing a weak baseline** (major headline vulnerability!).
  - If *both* $B$ and $M$ drop multiplicatively and $B_{\text{new}} / M_{\text{new}}$ stays large $\implies$ **genuine orthogonal mechanism** (and you just improved your own method's absolute performance too!).
  - **Regime-weighted sizing:** Distinguish whether the cheap upgrade collapses $B / M$ on the **primary non-toy targets** (P0) vs. trimming only a small secondary/toy regime while primary non-toy wins remain multi-fold (P1).

### Rule 4 — The "Pull Every Anomaly Thread" Rule (Zero-Burying Policy)
Whenever a theoretically weaker comparator beats a theoretically stronger stage of your pipeline on *any* system or setting (e.g., fixed heuristic beats adaptive optimizer; zero-prior beats informative prior; shallower/simpler approximation beats richer one) — OR whenever all evaluated methods collapse to 0% or an unexplainable cliff on a benchmark split:
- **STOP and diagnose the anomaly.** Do **not** wave it away as a footnote without checking its cause.
- **Size its materiality honestly:** Treat it as a **P0** red flag if it threatens, inverts, or invalidates the headline claim (e.g., universal 0%/cliff collapse—verify immediately whether exact **ground truth / an oracle-initialized solver** passes the evaluator and whether timed-out/errored runs were silently excluded from summary denominators—or a broken/handicapped primary baseline). Treat it as **P1** if it is a localized secondary-regime anomaly or minor subdominant cost inversion ($< 20\text{--}30\%$ impact on a multi-fold primary win) whose diagnosis leaves the core mechanism intact, or **P2** (advisory, excluded from `p0_p1_count`) if already disclosed and quantitatively negligible ($< 10\text{--}15\%$).

### Rule 5 — External Literature Comparator Faithfulness Audit
For every external literature baseline cited or compared against in tables, figures, or claims:
1. **Code provenance:** Explicitly check whether the comparison ran the **authors' own published code/data** or an **in-house reimplementation**. Never imply an in-house reimplementation is the authors' code.
2. **Regime & problem-class match:** Check whether the benchmark's setting (candidate family, discretization/basis, representation, stopping rule, variance/noise model, metric) matches the regime the external method was designed for. If an external method was designed for one regime (e.g., local/sparse structure) and ported to another (e.g., dense/non-local structure), state clearly what breaks under that port (e.g., overhead explosion, lost closed-form bounds) and what stays valid.
3. **Strongest fair variant:** Check whether an obvious, cheap cleanup (e.g., deduplicating repeated evaluations, tuning obvious default tolerances/hyperparameters, replacing a conservative analytical bound with an empirical estimate) strengthens the external baseline — and report it transparently.
4. **Apples-to-apples metric check:** Verify whether the external paper optimizes the same objective (e.g., total sample/query count vs. wall-clock latency vs. hardware overhead vs. fixed accuracy vs. statistical certification) before quoting speedup ratios.

---

## Severity, Materiality & Scope Calibration (Keep the Teeth, Avoid False-Nuclear Verdicts)

Distinguish sharply between **headline-collapsing baseline flaws** and **localized parity/accounting fixes on a genuine Discovery mechanism**:

- **P0 — Headline-Threatening (Blocks Stage 1A; `HANDICAPPED_BASELINE_RERUN_REQUIRED` or `REPAIR_RISK_PILOT_REQUIRED`):** A baseline handicap, information/budget/interaction asymmetry, oracle leak, missing primary baseline, unpulled fatal anomaly, or core table bug that **plausibly collapses, inverts, or cuts the primary non-toy headline gain by a material factor** (e.g., $\ge 50\%$ loss, winner reversal, or unreproducible core comparison).
- **P1 — Localized Parity / Accounting / Scope Fix (When P0 = 0 and core mechanism is verified `Discovery` $\implies$ `MECHANISM_SOLID_PARITY_FIX_NEEDED`):** A real parity, table-convention, or scope-wording defect affecting only a **secondary regime**, a **subdominant prefactor ($< 20\text{--}30\%$ of a large headline speedup)**, or an **overly broad verbal claim** (fixable via a targeted table correction or 1-sentence scope trim) while leaving the primary non-toy mechanism intact.
- **P2 — Advisory / Out-of-Scope (NEVER count in `p0_p1_count`):** Minor constant-factor baseline tweaks ($< 10\text{--}15\%$ impact on primary benchmarks), already-disclosed minor asymmetries whose magnitude is negligible vs. the headline win, or defects owned by other reviewers.
- **Role Boundary vs. Reviewers 8 & 2:** Do **not** inflate `p0_p1_count` with general asymptotic/failure-mode theory (Reviewer 8's scope) or missing reproducibility metadata/parameter/qubit tables (Reviewer 2's scope) unless they directly handicap a baseline comparison or falsify a headline comparison table.

---

## Execution Checklist & Output Format

When invoked (standalone or inside `scientific-report-review`), inspect the actual source code of all baselines and methods, plus all quantitative results/anomalies, and deliver a concise, calibrated adversarial report with these **exact four sections**:

1. **Baseline Inventory & Literature Faithfulness Table**
   - Columns: `Baseline | Source (Author code vs. Reimplementation) | Key Heuristics in Code | Regime Match vs. Paper | Potential Handicap?`
2. **Detected Information Asymmetries, Handicaps & Unpulled Anomalies (P0 / P1)**
   - Exact `file:line` pointers, exact table/figure anomalies, quantitative impact on primary vs. secondary headline rows, and P0 vs. P1 classification.
3. **Top 2–3 Cheap Baseline-Killer Experiments (Minimal Patch or ≤ ~50-Line Textbook Pilot)**
   - Concrete code-level change (with realistic line-count/effort estimate), non-toy test system(s), estimated pilot runtime, quantitative expected impact, and explicit pass/fail criterion distinguishing **Repair** vs. **Discovery**.
4. **Go / No-Go Verdict (Before Heavy Compute or Before Submission)**
   - One of:
     - `SOLID_BASELINE` (`0` P0, `0` P1 — verified Discovery, baselines fair),
     - `MECHANISM_SOLID_PARITY_FIX_NEEDED` (`0` P0, $\ge 1$ localized P1 — core mechanism is verified Discovery and survives the strongest cheap baseline on primary non-toy targets, needing only localized table/parity/scope fixes),
     - `REPAIR_RISK_PILOT_REQUIRED` (genuine Repair-vs.-Discovery ambiguity; run cheap falsification pilot(s) first), or
     - `HANDICAPPED_BASELINE_RERUN_REQUIRED` ($\ge 1$ headline-threatening P0 handicap, oracle leak, missing primary baseline, or fatal unpulled anomaly).

---

## Ground Rules (Shared with `scientific-report-review`)
- **Never invent numbers or claim a baseline fails without code/data evidence.**
- **Read the actual code lines**, not just the Methods prose.
- **Zero prose/formatting nitpicks** — keep 100% of attention on baselines, mechanisms, and headline validity.
