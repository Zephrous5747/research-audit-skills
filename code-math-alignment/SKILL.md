---
name: code-math-alignment
description: >-
  Domain-general white-box code-to-math alignment, fail-loud, symmetry, and
  pre-flight smoke verification gate (Stage 0). Use standalone right after
  writing or modifying algorithm/estimator/benchmark code (before submitting
  expensive HPC/SLURM cluster sweeps) OR as Stage 0 (`Reviewer 0:
  code_math_auditor`) inside `scientific-report-review` before Stage 1
  scientific reviews. Completely ignores prose and formatting and focuses
  exclusively on preventing silent numerical pollution: tracing every branch,
  clip, regularization, and tolerance to the mathematical specification;
  banning silent fallbacks and unlogged solver failures; auditing cross-pipeline
  parameter/thread/atomic-write symmetry; and enforcing boundary-crossing
  micro-probes, metamorphic invariance tests, and a fast (<10 s) local `--smoke`
  pre-flight check.
---

# Code-to-Math Alignment & Fail-Loud Gate (Stage 0)

This skill prevents **silent numerical pollution** before burning HPC/SLURM node-hours and before spending Stage 1–3 review cycles on untrustworthy numbers.

Its sole mission is **white-box code verification** against the mathematical specification and execution environment. It has **zero prose, grammar, or formatting duties**.

Use this skill at **two gates**:
1. **Standalone Pre-HPC Gate** — immediately after writing or modifying core algorithms, estimators, baselines, or sweep drivers, *before* submitting cluster jobs.
2. **Stage 0 of `scientific-report-review`** — loaded verbatim as **Reviewer 0 (`code_math_auditor`)** as a hard gate before Stage 1A/1B scientific reviews.

---

## The Four Mandatory Audit Rules

### Rule 1 — Branch-to-Equation Trace (Every `if`, Clip & Tolerance Check)
Read the actual implementation lines of every core algorithm, estimator, solver wrapper, and baseline (never trust docstrings or Methods prose alone).
- Trace **every** conditional branch (`if` / `elif` / `else`), numerical clip (`np.clip`, `max(x, eps)`, floor/ceiling clamp), damping/regularization term (e.g., Tikhonov ridge, diagonal shift, shrinkage factor), and tolerance threshold (`atol`, `rtol`, `tol`, `eps`, `maxiter`) back to an explicit equation or assumption in the mathematical specification.
- Flag any undocumented heuristic, hardcoded magic number, silent branch switch, or unapproved mathematical relaxation as **`P0 Unapproved Assumption`** with exact `file:line` pointers.
- Verify sign conventions, normalization factors, index bases, Hermitian/transpose conventions, and unit/scaling factors match the equations identically.

### Rule 2 — Fail-Loud & Silent-Fallback Ban
Silent recovery hides broken physics and contaminates aggregate benchmark tables.
- **Ban silent exception swallowing:** Flag every broad or silent `try/except` (`except Exception: pass`, `except ...: return fallback`) that masks numerical, linear-algebra, or solver errors without raising or recording an explicit failure flag.
- **Ban unlogged solver fallbacks:** Audit every numerical optimizer/solver call (e.g., `scipy.optimize`, CVXPY/SCS/CLARABEL/MOSEK, eigensolvers, linear solvers). If a solver hits `maxiter`, `optimal_inaccurate`, `infeasible`, `NaN`/`Inf`, or non-convergence and falls back to a default, previous iterate, or frozen solution, it MUST either **raise loudly** or **explicitly increment a fallback/failure counter and record status in the output metadata** so polluted runs can never silently enter summary tables.
- **Enforce spec-claimed mathematical guards:** Verify every positive-semidefinite (PSD), eigenvalue-floor, probability-simplex, normalization, or conservation guard claimed in the specification is actually enforced in code (and logged/counted whenever triggered).

### Rule 3 — Cross-Pipeline Parameter & Environment Symmetry
Audit configuration dictionaries, baseline vs. method setup calls, job launchers, aggregation/summary scripts, and plotting scripts **side by side**:
- **Baseline vs. method call symmetry:** Catch hidden call-site asymmetries where a different ordering, grouping heuristic, warm-start, cache key, shot budget, tolerance, or preprocessing step is passed to a baseline vs. the proposed method (or where a summary/plotting script filters or normalizes one method differently from another).
- **HPC thread-lock hygiene:** In parallel workers (multiprocessing, SLURM job arrays, joblib, Ray, Rust/PyO3 extensions), verify explicit single-thread BLAS/OpenMP/Rust locks (`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `NUMEXPR_NUM_THREADS=1`, `RAYON_NUM_THREADS=1`) to prevent thread oversubscription, nondeterministic contention, or silent cluster slowdowns/timeouts.
- **Atomic result writes & crash safety:** Verify checkpoint, cache, and result writers use atomic write semantics (write to a unique temporary file in the same directory + `os.replace` / atomic rename, never raw in-place overwrite of shared JSON/NPZ/CSV artifacts that corrupt on walltime kill or concurrent workers).

### Rule 4 — Micro-Probe & Pre-Flight Smoke Gate
Require concrete, lightweight verification gates before any expensive sweep or paper table generation:
- **Boundary-crossing unit tests:** Check for targeted tests that explicitly straddle every critical threshold/branch (e.g., `n_samples = n_min - 1` vs. `n_min`, `rank = 0` vs. `1`, singular/near-singular covariance, zero-weight edge cases, exact tolerance boundaries).
- **Metamorphic invariance checks:** Check for invariance/equivariance tests verifying mathematical laws that must hold without knowing the analytical answer (e.g., operator/objective rescaling $A \mapsto c A$, constant shift $A \mapsto A + c I$, basis/permutation symmetry, deterministic replay under fixed seed).
- **Benchmark & evaluator sanity probes (when auditing evaluators, graders, or synthetic/real task banks):** Verify (a) a **Ground-Truth / Oracle Solvability probe** confirming exact ground truth (or an oracle-initialized reference) clears 100% of grading gates and synthetic tasks satisfy identifiability/SNR solvability (no double-counted noise or unattainable thresholds), (b) a **Null/Empty-Model probe** confirming a trivial constant/zero submission fails statistical-improvement gates, (c) a **Monotonicity / Garbage-Padding probe** confirming replacing an imperfect component with out-of-range dummy outputs can never raise the score, and (d) **Zero-Leakage & Denominator checks** confirming grader feedback strips nested ground-truth fields and timed-out/errored runs remain counted in summary denominators.
- **Fast local `--smoke` pre-flight gate (`< 10 s`):** Verify a single-threaded local `--smoke` (or equivalent pre-flight) mode exists and exercises **every** case key, method variant, cache lookup/save path, fallback-counter schema, and output writer end-to-end in under 10 seconds before submitting any cluster sweep.

---

## Required Structured Gate Output

When invoked (standalone or as Stage 0 inside `scientific-report-review`), inspect the actual code files, configs, tests, and launch/summary scripts, and emit these **exact four sections** plus the machine-readable verdict block:

1. **Branch-to-Equation Trace & Unapproved Assumptions (`P0` / `P1`)**
   - Table: `file:line | Code Branch / Clip / Magic Constant | Spec Equation / Claim | Classification (Aligned / P0 Unapproved Assumption / P1 Undocumented Heuristic) | Required Fix`
2. **Fail-Loud Violations & Silent-Fallback Audit (`P0` / `P1`)**
   - Every silent `try/except`, unlogged solver fallback (`maxiter`, `optimal_inaccurate`, `NaN`/non-convergence), and missing PSD/eigenvalue/simplex guard with exact `file:line` pointers.
3. **Cross-Pipeline Symmetry, Thread-Lock & Atomic-Write Audit (`P0` / `P1`)**
   - Side-by-side discrepancies across configs, method/baseline calls, summary/plotting scripts, missing `OMP_NUM_THREADS=1` / `RAYON_NUM_THREADS=1` (etc.) locks, and non-atomic writes with exact `file:line` pointers.
4. **Micro-Probe & Pre-Flight `--smoke` Gate Status**
   - Existing vs. missing boundary-crossing tests, metamorphic invariance checks, benchmark/evaluator sanity probes (ground-truth/oracle solvability, null-model rejection, garbage-padding monotonicity, zero-leakage/denominator accounting when applicable), and `< 10 s` single-threaded `--smoke` coverage across all case keys/caches.
5. **Machine-Readable Stage 0 Gate Verdict Block**
   Emit an explicit JSON block using strictly one of two verdicts:
   - `ALIGNED_FAIL_LOUD` — **only** when `p0_p1_count == 0` (every branch traced, zero silent fallbacks, cross-pipeline symmetry + thread locks + atomic writes verified, boundary/metamorphic/smoke gates in place).
   - `SILENT_POLLUTION_RISK` — whenever **any** P0 or P1 violation remains (`p0_p1_count > 0`).

```json
{
  "stage0_verdict": "ALIGNED_FAIL_LOUD | SILENT_POLLUTION_RISK",
  "p0_p1_count": 0,
  "stage0_closed": true,
  "blocking_pointers": [
    "path/to/file.py:123 — P0 Unapproved Assumption / Silent Fallback / Asymmetry"
  ],
  "next_action": "PROCEED_TO_HPC_OR_STAGE1A | BLOCK_AND_FIX_P0_P1"
}
```

---

## Ground Rules (Shared with `scientific-report-review`)
- **Read actual source lines** — never rely solely on manuscript Methods text, comments, or docstrings.
- **Never invent test results or assume a branch is harmless** without verifying it in code.
- **Zero prose, grammar, or formatting nitpicks** — keep 100% of attention on code-to-math fidelity, fail-loud safety, pipeline symmetry, and pre-flight verification.
- **Recheck strictness:** In revision re-checks, reject cosmetic comments or docstrings that leave silent fallbacks, unapproved clips, asymmetries, missing thread locks, or missing smoke probes unfixed.
