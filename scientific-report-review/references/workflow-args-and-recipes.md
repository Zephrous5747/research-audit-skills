# Workflow `Args` Reference & Invocation Recipes

Invoke `run_workflow` with `ScriptPath` resolved to `<skill_dir>/scripts/review_panel.py` (relative to `scientific-report-review/SKILL.md`). Optional gitignored `local_config.yaml` and `local_overlay.md` at workspace `.agents/skills/` or the skill suite root are loaded automatically if present.

## Stage Routing & Sandbox Capabilities

| `stage` | Default Reviewer(s) | Default `agent_type` | Gate / Purpose |
| :--- | :--- | :--- | :--- |
| `stage0` *(default)* | `code_math_auditor` (R0) | `self` (no repo edits; ≤5 fast `<15 s` read-only `--smoke`/`pytest`/micro-probe commands) | Hard gate before `sbatch` & Stage 1 (`ALIGNED_FAIL_LOUD`, `p0_p1_count == 0`) |
| `stage1a` | `baseline_killer` (R7) | `research` | Bounded 1–3 rounds, immediate early exit on `SOLID_BASELINE` + `p0_p1_count == 0` |
| `stage1b` | `theory_mechanism_critic` (R8), `supervisor_strategist` (R9) | R8: `research`; R9: `self` (no edits/shell; 2–4 live `search_web` prior-art queries) | Theory/limits/failure modes + live novelty/venue-bar & Referee #2 strategy |
| `stage1` | R7 + R8 + R9 | R7/R8: `research`; R9: `self` | Combined one-shot Stage 1 if explicitly requested |
| `stage2` *(default Stage 2)* | Lean 3-pillar audit: R1 (`structure_narrative`) + R11 (`average_reader`, 2-pass `flash`) + R2 (`reproducibility_code`) + R3 (`claims_definitions`) + R10 (`conciseness_editor`) | `research` | Optional computational-paper audit: skimmability, provenance/spec-sync & compression (R4/R5 decoupled as opt-in) |
| `stage2a` | R1 + R2 + R3 + R11 (`average_reader` [review only, `flash`]) | `research` | Skimmability, provenance, Main↔SI spec sync & blind average-reader audit |
| `stage2b` | `conciseness_editor` (R10) | `research` | Anti-ping-pong Main + SI squeeze alone (e.g., final squeeze right before Stage 3) |
| `stage3` | `grammar_humanizer` (R6); opt-in R4 (`prose_style`) / R5 (`figures_refs_format`) via `reviewers` | `research` | Optional decoupled prose/formatting polish (hard-gated after Stages 0, 1 & 2) |

---

## Optional `Args` Knobs

- `mode`: `"review"` (default) or `"recheck"` (auto-enabled when `previous_review`, `diff_file`, `git_ref`, or `original_report` is passed).
- `diff_file` / `git_ref`: Preferred for `recheck` mode — scopes reviewers to prior open P0/P1 issues + the unified diff (`git diff <git_ref>`), cutting recheck tokens 50–70% and preventing goalpost-shifting.
- `iteration`: `1`–`3` for bounded `stage1a` (hard-capped at `3`).
- `extra_files`: Code, configs, tests, `.bib`, `.log`/`.blg`, plotting scripts, SI, or archive manifests.
- `doc_type`: `"paper"` (default), `"report"`, `"proposal"`, `"nsf"`, or `"nih"` (enables Layer 6 proposal mode in R6).
- `target_venue`: Target journal/conference/agency (e.g., `"Nature Computational Science"`, `"NeurIPS"`, `"Phys. Rev. X"`, `"NSF"`).
- `prior_art_summary`: Optional pre-compiled prior-art brief (supplied to R8, R9, and Stage 1 Pivot Red-Team; supports offline `agent_type="research"` runs via `used_supplied_brief`).
- `cutoff_year`: Optional integer upper-bound year (e.g., `2025`) for retrospective pre-cutoff evaluations; bounds `search_window` and injects an explicit `<= <cutoff_year>-12-31` prior-art directive.
- `length_budget`: Optional target page/figure/table budget for `stage2` / `stage2b` (R10).
- `protected_requirements`: Optional path/text of Stage 1/2A facts/provenance items R10 must preserve via compress/demote/archive and never cut.
- `voice_sample`: Optional path(s) to author's prior paper(s) for Stage 3 voice matching (R6).
- `reviewers`: Explicit subset override from `["code_math_auditor", "structure_narrative", "reproducibility_code", "claims_definitions", "prose_style", "figures_refs_format", "grammar_humanizer", "baseline_killer", "theory_mechanism_critic", "supervisor_strategist", "conciseness_editor", "average_reader"]`.
- `agent_type`: `"auto"` (default per-reviewer routing above), or explicit `"research"` / `"self"` override.
- `candidate_pivots`: Optional list of candidate Pivots to audit via the bounded 1-round Stage 1/1B Pivot Red-Team mini-pass (if omitted, automatically audits Reviewer 9's `candidate_pivots`).
- `skip_pivot_red_team`: Set `true` to skip the bounded 1-round Pivot Red-Team mini-pass in Stage 1/1B.
- `skip_lint`: Set `true` to skip the 0-token deterministic pre-linter (`scripts/preflight_lint.py`).
- `skip_local_overlay`: `"auto"` (default: auto-suppresses lab `local_overlay.md` and domain-specific venues/arXiv categories when an explicit `domain` has zero overlap with `local_config.yaml`'s `default_domain`), `true` (always skip), or `false` (force apply if present).
- `model`: `"inherit"` (default), `"pro"`, `"flash"`, or `"flash_lite"`.
- `reader_model`: Model tier for Reviewer 11 (`average_reader`; default `"flash"` — fast impatient-skimmer reader reading compiled Main + SI PDFs only).
- `reader_report`: Optional compiled PDF path(s) for Reviewer 11 (e.g., `["reports/manuscript.pdf", "reports/supplement.pdf"]`) so R11 reads rendered figures/tables while R1–R5/R10 read `.tex`; falls back to `report`.
- `reader_two_pass`: `"auto"` (default: automatically runs Pass 1 Main-only with SI withheld $\to$ Pass 2 Main+SI follow-up whenever R11 receives $\ge 2$ files in `review` mode), `true`, or `false` (force single-pass).

---

## JSON Payload Recipes

### Stage 0 — Pre-HPC / Code-to-Math Gate (R0 with live `--smoke`/`pytest`)
```json
{
  "stage": "stage0",
  "report": ["reports/manuscript.tex"],
  "extra_files": [
    "src/",
    "tests/",
    "cluster/"
  ],
  "domain": "computational science / physics"
}
```

### Stage 1A — Bounded Baseline-Killer Gate (Round 1 → Diff-Scoped Recheck)
```json
{
  "stage": "stage1a",
  "iteration": 1,
  "report": ["reports/manuscript.tex"],
  "extra_files": ["src/baselines.py", "src/method.py"]
}
```
```json
{
  "stage": "stage1a",
  "mode": "recheck",
  "iteration": 2,
  "previous_review": "reports/review_stage1a_r1.md",
  "git_ref": "HEAD~1",
  "report": ["reports/manuscript.tex"],
  "extra_files": ["src/baselines.py", "src/method.py"]
}
```

### Stage 1B — Theory/Limits + Live Web/arXiv Novelty & Strategy (R8 + R9)
```json
{
  "stage": "stage1b",
  "report": ["reports/manuscript.tex", "reports/supplement.tex"],
  "target_venue": "top domain journal",
  "domain": "computational science / physics"
}
```

### Stage 2 (Combined 2A + 2B Default) & Standalone Stage 2B Squeeze
```json
{
  "stage": "stage2",
  "report": ["reports/manuscript.tex", "reports/supplement.tex"],
  "extra_files": ["reports/refs.bib", "README.md"],
  "length_budget": "Main <= 10 pages, <= 5 figs, <= 3 tables; SI <= 15 pages"
}
```
```json
{
  "stage": "stage2b",
  "report": ["reports/manuscript.tex", "reports/supplement.tex"],
  "protected_requirements": "reports/review_stage2a.md",
  "length_budget": "Main <= 10 pages, <= 5 figs, <= 3 tables; SI <= 15 pages"
}
```

### Stage 3 — Natural Prose & Word Editing Pass (After Stages 0, 1, 2 Pass)
```json
{
  "stage": "stage3",
  "report": ["reports/manuscript.tex"],
  "doc_type": "paper",
  "target_venue": "top domain journal",
  "voice_sample": ["reports/prior_paper.pdf"]
}
```

### Standalone 0-Token Pre-Linter CLI
```bash
python <skill_dir>/scripts/preflight_lint.py reports/manuscript.tex reports/refs.bib
```
