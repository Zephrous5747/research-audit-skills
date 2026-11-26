# Example 2 — Pre-Compute Stage 0 (`code-math-alignment`) + Stage 1A (`baseline-killer-audit`)

> **Scenario:** A team built an automated scientific model-fitting benchmark (code + draft methods) reporting a 0% baseline pass rate vs. 42% for their proposed agentic solver. Before launching a full cluster sweep, they run **Stage 0** (white-box code-to-math + evaluator sanity probes) and **Stage 1A** (adversarial baseline killer).

---

## Stage 0 — Code-to-Math & Fail-Loud Gate (`code_math_auditor`)

- **Stage 0 Verdict:** `SILENT_POLLUTION_RISK` (`stage0_closed: false`, `p0_p1_count: 3`)
- **Pre-Flight Linter (`preflight_lint.py`):** 0 tokens, scanned 9 files (`2` silent `except`, `1` missing BLAS thread lock, `1` non-atomic JSON write).
- **Read-Only Smoke Execution (`pytest -q --tb=short`):** `executed_failed` — Oracle Solvability micro-probe failed on 2/5 tasks.

### Blocking P0 Findings (Must Fix Before Any Cluster Sweep)

| ID | File:Line | Code-to-Math / Fail-Loud Defect | Micro-Probe Evidence |
| :--- | :--- | :--- | :--- |
| **P0-1** | `src/evaluator.py:114` | **Silent fallback masks solver divergence:** `except Exception: return 0.0` converts numerical crashes and timeouts into valid `0.0` score entries, silently dragging baseline means down without logging failures. | Injecting `NaN` parameters returns score `0.0` instead of raising / recording `status="failed"`. |
| **P0-2** | `src/evaluator.py:182` | **Oracle Solvability & Null-Model exploit:** Passing an *empty/zero* parameter vector scores `0.61` because the residual penalty clips asymmetrically (`np.clip(err, 0, 1)`), while the exact ground-truth parameters fail the tolerance check on noisy synthetic tasks where the Cramér–Rao bound exceeds the hard grading threshold. | Null-model probe scored `0.61` (`> 0.5` pass threshold); ground-truth oracle passed only `3/5` tasks. |
| **P0-3** | `cluster/run_sweep.py:47` | **Missing thread locks & non-atomic output:** `ProcessPoolExecutor` launches 32 workers without `OMP_NUM_THREADS=1` / `OPENBLAS_NUM_THREADS=1` and writes directly via `json.dump(..., open("results.json", "w"))`. | High risk of 32x thread oversubscription and truncated checkpoint files on timeout. |

**Stage 0 Action:** Blocked from `sbatch` and Stage 1B until P0-1..P0-3 are fixed and `python scripts/run_benchmark.py --smoke` passes cleanly (`< 10 s`).

---

## Stage 1A — Adversarial Baseline-Killer Gate (`baseline_killer`)

- **Stage 1A Verdict:** `HANDICAPPED_BASELINE_RERUN_REQUIRED` (`closed: false`, `p0_p1_count: 2`)

### Baseline Inventory & Interaction Parity Audit

| Method | Runtime Budget / Retries | Inputs Exposed | Fair Parity? | Defect |
| :--- | :--- | :--- | :--- | :--- |
| **Proposed Agentic Solver** | 12 turns + error tracebacks + intermediate residual diagnostics | Full data + exact noise floor $\sigma$ + iterative evaluator feedback | — | Reference |
| **Reported "Classical Baseline"** | 1-shot fixed initialization, `maxiter=50`, no restarts | Raw data only ($\sigma$ omitted; fixed default step size) | **NO (P0)** | **Handicapped baseline + interaction asymmetry:** Baseline is starved of $\sigma$, capped at 50 iterations, and gets 1 start while proposed method gets 12 feedback turns. |

### Top 2 Cheap Baseline-Killer Pilots (Run Before Any Full Sweep)
1. **18-line multi-start `scipy.optimize.least_squares` baseline** (passing the same $\sigma$ exposed to the proposed method, 10 random restarts, standard `max_nfev=2000`): tests whether the reported `0% -> 42%` jump collapses once the classical optimizer isn't artificially crippled.
2. **Timeout-denominator audit:** Separate `converged_wrong` from `timed_out` and re-score with the fixed Stage 0 oracle-verified evaluator.

### Go / No-Go Gate
- **BLOCKED from Stage 1B & Stage 2.** Fix Stage 0 P0-1..P0-3 first, run the 18-line multi-start parity baseline on a 20-task pilot, and re-run `stage1a` in diff-scoped `recheck` mode.
