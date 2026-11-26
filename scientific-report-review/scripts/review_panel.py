"""
Four-stage blind multi-agent critical review workflow for scientific reports,
papers, and grant proposals.

Upgrades:
    - Per-reviewer capability routing (`agent_type="auto"` default):
        * Reviewer 0 (`code_math_auditor`, Stage 0) -> `self` (read-only on repo files;
          can execute <= 5 fast <15 s local `--smoke` / `pytest` / boundary micro-probes).
        * Reviewer 9 (`supervisor_strategist`, Stage 1B) & Stage 1 Pivot Red-Team -> `self`
          (read-only, no shell; live `search_web` queries for recent arXiv/journal prior art).
        * All other reviewers (R1-R8, R10) -> `research` (strict read-only sandbox).
    - Bounded 1-round blind Pivot Red-Team Mini-Pass in Stage 1 / Stage 1B (with live
      `search_web` on surviving Pivots and 4-tier gating: `SURVIVES_RED_TEAM` /
      `VIABLE_WITH_PATCH` / `NEEDS_FRESH_SCREEN` / `DROP_PIVOT`).
    - Two-layer Public Core + optional gitignored local overlay (`local_config.yaml` /
      `local_overlay.md`) with zero third-party dependencies.
    - Deterministic 0-token pre-flight linter (`preflight_lint.py`) runs locally in <1 s
      before spawning agents, feeding exact file:line hits to Reviewers 0, 4, 5, 6, and 10.
    - Lean per-reviewer JSON schemas (`build_schema`) to reduce token overhead and
      minimize `parallel(...)` cancellation risk.
    - Diff-scoped rechecks (`diff_file` / `git_ref`) + universal anti-goalpost-shifting
      P0/P1 freeze across ALL stages.

Expected `Args` (dict passed via run_workflow):
    stage (str): "stage0" (default), "stage1a", "stage1b", "stage1", "stage2"
        (both 2A+2B), "stage2a", "stage2b", or "stage3" (also 0/1a/1b/1/2/2a/2b/3).
    mode (str): "review" (default) or "recheck" (auto-enabled if `previous_review`,
        `original_report`, `diff_file`, or `git_ref` is supplied).
    iteration (int): Bounded iteration number for Stage 1A (1-3; default 1).
    report (str | list[str]): Path(s) to target report/spec (or revised report in recheck).
    report_text (str): Optional raw text if pasted directly.
    original_report (str | list[str]): Optional path(s) to original report (recheck).
    original_report_text (str): Optional raw text of original report (recheck).
    previous_review (str): Path to or text of prior review for this stage (recheck).
        Also accepts `stage1_review` as a legacy alias.
    diff_file (str): Optional path to a unified diff file for diff-scoped recheck.
    git_ref (str): Optional git ref (e.g. "HEAD~1") to auto-extract a bounded diff in recheck.
    extra_files (str | list[str]): Auxiliary files (code, configs, tests, .bib, figures, SI).
    doc_type (str): "paper" (default), "report", "proposal", "nsf", or "nih".
    target_venue (str): Optional target journal/conference/agency.
    prior_art_summary (str): Optional pre-compiled prior-art brief (supplied to R9, R8, and Pivot Red-Team).
    cutoff_year (int): Optional hard upper-bound year (e.g. 2025) for retrospective pre-cutoff evaluations.
    length_budget (str): Optional target page/table/figure budget (Stage 2 / 2B).
    protected_requirements (str): Optional path/text of Stage 1/2A facts Stage 2B must never cut.
    voice_sample (str | list[str]): Optional path(s) to author's prior writing sample (Stage 3).
    domain (str): Research domain (defaults to local_config.yaml or "computational science").
    context (str): Optional extra instructions.
    candidate_pivots (list[dict | str]): Optional explicit pivots to audit via Stage 1/1B Pivot Red-Team.
    skip_pivot_red_team (bool): Optional; set True to skip Stage 1/1B 1-round Pivot Red-Team pass.
    reviewers (list[str]): Optional explicit override of reviewer IDs.
    agent_type (str): "auto" (default: R0 & R9 -> "self", others -> "research"),
        or explicit "research" / "self" override for all reviewers.
    skip_lint (bool): Optional; set True to skip 0-token pre-flight linting.
    skip_local_overlay (bool | str): Optional; "auto" (default: auto-suppresses lab
        `local_overlay.md` and domain-specific venues/arXiv categories when an explicit
        `domain` does not overlap `local_config.yaml`'s `default_domain`), True (always
        skip), or False (always apply if present).
    model (str): Model tier ("inherit", "pro", "flash", "flash_lite"; default from overlay or "inherit").
    reader_model (str): Model tier for Reviewer 11 (`average_reader`; default `"flash"`).
    reader_report (str | list[str]): Optional compiled PDF path(s) for Reviewer 11 (e.g., Main+SI PDFs instead of raw `.tex`; falls back to `report`).
    reader_two_pass (bool | str): Optional; `"auto"` (default: automatically runs a 2-pass no-lookahead split — Pass 1 Main-only with SI withheld, Pass 2 Main+SI follow-up — whenever Reviewer 11 receives >=2 files in `review` mode), True, or False (force single-pass).
"""

import datetime
import importlib.util
import json
import re
import subprocess
from pathlib import Path

MAX_STAGE1A_ITERATIONS = 3
MAX_DIFF_CHARS = 24000
MAX_OVERLAY_CHARS = 6000


def _skill_root_candidates():
    """Locate skill suite roots in priority order (workspace overlay first, then installed root)."""
    cwd = Path.cwd()
    home = Path.home()
    candidates = [
        cwd / ".agents" / "skills",
        cwd / ".claude" / "skills",
        cwd / ".codex" / "skills",
    ]
    if "__file__" in globals():
        candidates.append(Path(__file__).resolve().parents[2])
    candidates.extend([
        home / ".gemini" / "config" / "skills",
        home / ".claude" / "skills",
        home / ".codex" / "skills",
        home / ".agents" / "skills",
    ])
    seen = set()
    unique = []
    for c in candidates:
        key = str(c)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _parse_simple_yaml(text: str) -> dict:
    """Zero-dependency parser for flat key/value and list YAML overlays (uses PyYAML if available)."""
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        pass

    data = {}
    current_list_key = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        m_item = re.match(r"^\s*-\s+(.*)$", line)
        if m_item and current_list_key is not None:
            val = m_item.group(1).strip().strip('"').strip("'")
            if val:
                data[current_list_key].append(val)
            continue
        m_kv = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$", line.strip())
        if not m_kv:
            current_list_key = None
            continue
        key, raw_val = m_kv.group(1), m_kv.group(2).strip()
        if raw_val == "":
            data[key] = []
            current_list_key = key
        elif raw_val == "[]":
            data[key] = []
            current_list_key = None
        else:
            current_list_key = None
            if (raw_val.startswith('"') and raw_val.endswith('"')) or (
                raw_val.startswith("'") and raw_val.endswith("'")
            ):
                data[key] = raw_val[1:-1]
            elif raw_val.lower() in ("true", "false"):
                data[key] = raw_val.lower() == "true"
            elif re.fullmatch(r"-?\d+", raw_val):
                data[key] = int(raw_val)
            else:
                data[key] = raw_val
    return data


def _load_local_overlay():
    """Gracefully load optional gitignored `local_config.yaml` and `local_overlay.md`."""
    cfg = {}
    cfg_source = None
    overlay_md = ""
    overlay_source = None
    for root in _skill_root_candidates():
        if cfg_source is None:
            p_cfg = root / "local_config.yaml"
            if p_cfg.exists():
                cfg = _parse_simple_yaml(p_cfg.read_text(encoding="utf-8", errors="replace"))
                cfg_source = p_cfg.name
        if overlay_source is None:
            p_md = root / "local_overlay.md"
            if p_md.exists():
                raw = p_md.read_text(encoding="utf-8", errors="replace").strip()
                overlay_md = raw[:MAX_OVERLAY_CHARS]
                overlay_source = p_md.name
    return cfg, cfg_source, overlay_md, overlay_source


def _load_sibling_skill(skill_dir_name: str, fallback: str) -> str:
    """Load a companion SKILL.md from workspace overlay, sibling skill directory, or global skills root."""
    for root in _skill_root_candidates():
        p = root / skill_dir_name / "SKILL.md"
        if p.exists():
            text = p.read_text(encoding="utf-8")
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) == 3:
                    return parts[2].strip()
            return text.strip()
    return fallback


def _load_code_math_skill() -> str:
    """Load the companion code-math-alignment SKILL.md directly."""
    return _load_sibling_skill(
        "code-math-alignment",
        (
            "Run the 4-rule Stage 0 Code-to-Math Alignment & Fail-Loud Gate: "
            "(1) trace every conditional branch, clip, damping/regularization, and tolerance to the math spec "
            "(flag undocumented heuristics/magic numbers as P0 Unapproved Assumption), "
            "(2) ban silent try/except and unlogged solver fallbacks and verify spec-claimed PSD/eigenvalue guards, "
            "(3) audit cross-pipeline config/baseline/method/summary/plot symmetry, BLAS/Rust thread locks "
            "(OMP_NUM_THREADS=1, RAYON_NUM_THREADS=1), and atomic result writes, and "
            "(4) require boundary-crossing unit tests, metamorphic invariance checks, and a fast (<10 s) "
            "single-threaded local --smoke gate. Emit ALIGNED_FAIL_LOUD (p0_p1_count==0) or SILENT_POLLUTION_RISK."
        ),
    )


def _load_baseline_killer_skill() -> str:
    """Load the companion baseline-killer-audit SKILL.md directly."""
    return _load_sibling_skill(
        "baseline-killer-audit",
        (
            "Run the 5-rule Adversarial Baseline-Killer Audit: (1) strongest cheap baseline (minimal patch, library call, or simple <=~50-line textbook baseline) on non-toy systems, "
            "(2) information-asymmetry code audit between baseline and proposed method, (3) repair vs. discovery check, "
            "(4) pull every P0 anomaly where a weaker comparator beats a stronger stage, and (5) external literature "
            "comparator faithfulness audit (author code vs. reimplementation, regime/pool match, strongest fair variant)."
        ),
    )


def _load_preflight_linter():
    """Dynamically load sibling scripts/preflight_lint.py without relying on sys.path."""
    candidates = []
    if "__file__" in globals():
        candidates.append(Path(__file__).resolve().parent / "preflight_lint.py")
    for root in _skill_root_candidates():
        candidates.append(root / "scientific-report-review" / "scripts" / "preflight_lint.py")
    for p in candidates:
        if p.exists():
            spec = importlib.util.spec_from_file_location("preflight_lint_mod", str(p))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    return None


def _normalize_list(value):
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if item]


def _extract_diff_text(diff_file, git_ref, target_paths):
    """Load unified diff from diff_file or `git diff <git_ref>` (bounded), failing loud on errors."""
    warnings = []
    if diff_file:
        p = Path(diff_file)
        if not p.is_absolute():
            p = Path.cwd() / p
        if p.exists():
            raw = p.read_text(encoding="utf-8", errors="replace")
            if len(raw) > MAX_DIFF_CHARS:
                return raw[:MAX_DIFF_CHARS] + "\n... [diff truncated at 24,000 chars]", warnings
            return raw, warnings
        msg = f"diff_file not found: {diff_file}"
        warnings.append(msg)
        return f"[{msg}]", warnings
    if git_ref:
        cmd = ["git", "diff", "--unified=3", git_ref]
        if target_paths:
            cmd.append("--")
            cmd.extend(target_paths)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            if proc.returncode != 0:
                warnings.append(f"git diff {git_ref} exited {proc.returncode}: {(proc.stderr or '').strip()[:200]}")
                return "", warnings
            raw = proc.stdout or ""
            # Flag untracked target files omitted by `git diff`
            status_cmd = ["git", "status", "--porcelain", "--untracked-files=all"]
            if target_paths:
                status_cmd.append("--")
                status_cmd.extend(target_paths)
            st = subprocess.run(status_cmd, capture_output=True, text=True, timeout=10, check=False)
            if st.returncode == 0 and st.stdout:
                untracked = [ln[3:].strip() for ln in st.stdout.splitlines() if ln.startswith("?? ")]
                if untracked:
                    warnings.append(f"Untracked target file(s) omitted from git diff: {', '.join(untracked[:10])}")
            if raw.strip():
                if len(raw) > MAX_DIFF_CHARS:
                    return raw[:MAX_DIFF_CHARS] + "\n... [git diff truncated at 24,000 chars]", warnings
                return raw, warnings
            warnings.append(f"git diff {git_ref} returned empty diff.")
        except Exception as exc:
            warnings.append(f"git diff {git_ref} failed: {exc}")
    return "", warnings


_DOMAIN_STOPWORDS = {
    "a", "an", "and", "or", "of", "for", "the", "in", "on", "to", "with",
    "science", "sciences", "scientific", "computational", "research",
    "method", "methods", "benchmark", "benchmarks", "model", "modeling",
    "ai", "ml", "agent", "agents", "analysis", "system", "systems",
}


def _domain_tokens(text: str) -> set:
    tokens = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
    return {t for t in tokens if len(t) >= 2 and t not in _DOMAIN_STOPWORDS}


def _resolve_local_overlay_policy(explicit_domain: str, cfg: dict, cfg_source, overlay_md: str, skip_arg):
    """Decide whether to inject lab-specific `local_overlay.md` and domain venue/arXiv priors."""
    has_any = bool(overlay_md or cfg_source)
    if skip_arg is True or (isinstance(skip_arg, str) and skip_arg.strip().lower() in ("true", "1", "yes")):
        return False, "explicit_skip"
    if skip_arg is False or (isinstance(skip_arg, str) and skip_arg.strip().lower() in ("false", "0", "no")):
        return has_any, (None if has_any else "not_found")
    if not has_any:
        return False, "not_found"
    cfg_default_domain = str(cfg.get("default_domain", "") or "").strip()
    if explicit_domain and cfg_default_domain:
        exp_toks = _domain_tokens(explicit_domain)
        def_toks = _domain_tokens(cfg_default_domain)
        if exp_toks and def_toks and exp_toks.isdisjoint(def_toks):
            return False, "cross_domain_override"
    return True, None


LOCAL_CFG, LOCAL_CFG_SOURCE, LOCAL_OVERLAY_MD, LOCAL_OVERLAY_SOURCE = _load_local_overlay()
CURRENT_YEAR = datetime.date.today().year
raw_cutoff_year = args.get("cutoff_year")
cutoff_year = None
if raw_cutoff_year is not None and str(raw_cutoff_year).strip() != "":
    cutoff_year = int(raw_cutoff_year)
    if not (1900 <= cutoff_year <= CURRENT_YEAR):
        raise ValueError(f"'cutoff_year' must be between 1900 and {CURRENT_YEAR}, got {cutoff_year}.")
EFFECTIVE_YEAR = cutoff_year if cutoff_year is not None else CURRENT_YEAR
STAGE1B_LOOKBACK = int(LOCAL_CFG.get("stage1b_lookback_years", 3) or 3)
STAGE1B_SEARCH_WINDOW = f"{EFFECTIVE_YEAR - STAGE1B_LOOKBACK}-{EFFECTIVE_YEAR}"
CUTOFF_DIRECTIVE = (
    f"\n- TEMPORAL CUTOFF ({EFFECTIVE_YEAR}-12-31): Restrict prior-art evaluation strictly to sources published "
    f"on or before {EFFECTIVE_YEAR}-12-31; ignore and NEVER cite any post-{EFFECTIVE_YEAR} work."
    if cutoff_year is not None
    else ""
)
DEFAULT_DOMAIN = str(LOCAL_CFG.get("default_domain", "computational science")).strip()
DEFAULT_MODEL = str(LOCAL_CFG.get("default_model", "inherit")).strip()

explicit_domain = str(args.get("domain") or "").strip()
domain = explicit_domain or DEFAULT_DOMAIN
OVERLAY_APPLIED, OVERLAY_SKIP_REASON = _resolve_local_overlay_policy(
    explicit_domain, LOCAL_CFG, LOCAL_CFG_SOURCE, LOCAL_OVERLAY_MD, args.get("skip_local_overlay")
)
ACTIVE_OVERLAY_MD = LOCAL_OVERLAY_MD if OVERLAY_APPLIED else ""
DEFAULT_VENUES = (
    (_normalize_list(LOCAL_CFG.get("default_venues")) or ["top domain journals/conferences"])
    if OVERLAY_APPLIED
    else ["top domain journals/conferences"]
)
ARXIV_CATS = _normalize_list(LOCAL_CFG.get("arxiv_categories")) if OVERLAY_APPLIED else []
VENUES_HINT = ", ".join(DEFAULT_VENUES)
ARXIV_HINT = f"arXiv ({', '.join(ARXIV_CATS)})" if ARXIV_CATS else "arXiv and domain preprints"

CODE_MATH_SKILL_TEXT = _load_code_math_skill()
BASELINE_KILLER_SKILL_TEXT = _load_baseline_killer_skill()
LINTER_MOD = _load_preflight_linter()

# --- Parse Args ---

raw_stage = str(args.get("stage", "stage0")).strip().lower()
if raw_stage in ("0", "stage0", "stage_0", "stage-0"):
    stage = "stage0"
elif raw_stage in ("1a", "stage1a", "stage_1a", "stage-1a"):
    stage = "stage1a"
elif raw_stage in ("1b", "stage1b", "stage_1b", "stage-1b"):
    stage = "stage1b"
elif raw_stage in ("1", "stage1", "stage_1", "stage-1"):
    stage = "stage1"
elif raw_stage in ("2a", "stage2a", "stage_2a", "stage-2a"):
    stage = "stage2a"
elif raw_stage in ("2b", "stage2b", "stage_2b", "stage-2b"):
    stage = "stage2b"
elif raw_stage in ("2", "stage2", "stage_2", "stage-2"):
    stage = "stage2"
elif raw_stage in ("3", "stage3", "stage_3", "stage-3"):
    stage = "stage3"
else:
    raise ValueError(
        f"Unsupported stage '{raw_stage}'. Use 'stage0', 'stage1a', 'stage1b', 'stage1', 'stage2', 'stage2a', 'stage2b', or 'stage3'."
    )

iteration = int(args.get("iteration", 1) or 1)
if iteration < 1:
    raise ValueError(f"'iteration' must be >= 1, got {iteration}.")
if stage == "stage1a" and iteration > MAX_STAGE1A_ITERATIONS:
    raise ValueError(
        f"Stage 1A is capped at {MAX_STAGE1A_ITERATIONS} iterations to prevent token burn and goalpost-shifting "
        f"(got iteration={iteration}). Escalate remaining P0/P1 items to the user."
    )

report_paths = _normalize_list(args.get("report"))
reader_report_paths = _normalize_list(args.get("reader_report"))
report_text = str(args.get("report_text", "") or "").strip()
original_paths = _normalize_list(args.get("original_report"))
original_text = str(args.get("original_report_text", "") or "").strip()
previous_review = str(
    args.get("previous_review", "") or args.get("stage1_review", "") or ""
).strip()
diff_file = str(args.get("diff_file", "") or "").strip()
git_ref = str(args.get("git_ref", "") or "").strip()
extra_files = _normalize_list(args.get("extra_files"))
doc_type = str(args.get("doc_type", "paper") or "paper").strip().lower()
target_venue = str(
    args.get("target_venue") or (LOCAL_CFG.get("default_target_venue", "") if OVERLAY_APPLIED else "") or ""
).strip()
prior_art_summary = str(args.get("prior_art_summary", "") or "").strip()
length_budget = str(args.get("length_budget", "") or "").strip()
protected_requirements = str(args.get("protected_requirements", "") or "").strip()
voice_samples = _normalize_list(args.get("voice_sample"))
context = str(args.get("context", "") or "").strip()
explicit_pivots = args.get("candidate_pivots")
skip_pivot_red_team = bool(args.get("skip_pivot_red_team", False))
agent_type_override = str(args.get("agent_type", "auto") or "auto").strip().lower()
skip_lint = bool(args.get("skip_lint", False))
model = str(args.get("model") or DEFAULT_MODEL).strip()
reader_model = str(args.get("reader_model") or "flash").strip()
reader_two_pass_arg = args.get("reader_two_pass", "auto")
selected_ids = args.get("reviewers")

raw_mode = str(args.get("mode", "") or "").strip().lower()
has_recheck_inputs = bool(original_paths or original_text or previous_review or diff_file or git_ref)
if raw_mode in ("", "auto"):
    mode = "recheck" if has_recheck_inputs else "review"
elif raw_mode in ("review", "initial", "audit"):
    mode = "review"
elif raw_mode in ("recheck", "revision", "verify"):
    mode = "recheck"
else:
    raise ValueError(f"Unsupported mode '{raw_mode}'. Use 'review' or 'recheck'.")

if not report_paths and not report_text and not (stage == "stage0" and extra_files):
    raise ValueError(
        "Provide 'report' (file path or list of paths) or 'report_text' "
        "(or 'extra_files' when running standalone Stage 0 code verification)."
    )

if mode == "recheck" and not has_recheck_inputs:
    raise ValueError(
        "Recheck mode requires 'previous_review', 'diff_file', 'git_ref', and/or 'original_report'."
    )

# --- Stage & Capability Routing ---

STAGE_DEFAULT_REVIEWERS = {
    "stage0": ["code_math_auditor"],
    "stage1a": ["baseline_killer"],
    "stage1b": ["theory_mechanism_critic", "supervisor_strategist"],
    "stage1": ["baseline_killer", "theory_mechanism_critic", "supervisor_strategist"],
    "stage2": [
        "structure_narrative",
        "reproducibility_code",
        "claims_definitions",
        "prose_style",
        "figures_refs_format",
        "conciseness_editor",
        "average_reader",
    ],
    "stage2a": [
        "structure_narrative",
        "reproducibility_code",
        "claims_definitions",
        "prose_style",
        "figures_refs_format",
        "average_reader",
    ],
    "stage2b": ["conciseness_editor"],
    "stage3": ["grammar_humanizer"],
}

# Advisory-only reviewers (diagnostic teach-back; Main Agent promotes verified gaps, never auto-blocks gates)
ADVISORY_REVIEWERS = {"average_reader"}

# Per-reviewer default sandbox routing:
#   - R0 (code_math_auditor): `self` for read-only local execution (--smoke, pytest, micro-probes)
#   - R9 (supervisor_strategist): `self` for live `search_web` prior-art sweeps
#   - All others: `research` (strict offline read-only sandbox)
REVIEWER_DEFAULT_AGENT_TYPE = {
    "code_math_auditor": "self",
    "supervisor_strategist": "self",
}

STAGE_DESCRIPTIONS = {
    "stage0": "STAGE 0 (Code-to-Math Alignment, Fail-Loud, Symmetry & Pre-Flight Smoke Gate)",
    "stage1a": "STAGE 1A (Adversarial Baseline-Killer Gate — Bounded 1-3 Rounds Until Zero P0/P1)",
    "stage1b": "STAGE 1B (Domain Theory, Mechanism, Live Novelty & Supervisor Strategy Gate)",
    "stage1": "STAGE 1 (Combined Science Core & PI Supervision Gate — Baselines, Theory/Mechanism & Strategy)",
    "stage2": "STAGE 2 (Combined 2A + 2B: Structure, Provenance, Claims, Presentation & Main+SI Compression)",
    "stage2a": "STAGE 2A (Narrative Structure, Completeness, Provenance, Claims & Presentation Gate)",
    "stage2b": "STAGE 2B (Ruthless Compression & Triage Pass — Main Text & SI Squeeze, Anti-Ping-Pong Safe)",
    "stage3": "STAGE 3 (Grammar, Scholarly Voice & Natural Word Editing Pass)",
}

STAGE_PHASE_LABELS = {
    "stage0": "Stage 0",
    "stage1a": "Stage 1A",
    "stage1b": "Stage 1B",
    "stage1": "Stage 1",
    "stage2": "Stage 2",
    "stage2a": "Stage 2A",
    "stage2b": "Stage 2B",
    "stage3": "Stage 3",
}


def resolve_agent_type(reviewer_id: str) -> str:
    if agent_type_override not in ("", "auto"):
        return agent_type_override
    return REVIEWER_DEFAULT_AGENT_TYPE.get(reviewer_id, "research")


def resolve_model(reviewer_id: str) -> str:
    if reviewer_id == "average_reader":
        return reader_model
    return model


# --- Ground Rules ---

GROUND_RULES = """GROUND RULES (MANDATORY):
1. NEVER INVENT CONTENT. Never supply missing motivation, definitions, methods, parameters, results, or conclusions, and never fill gaps with plausible assumptions. If a detail is not explicitly in the report, it is missing.
2. DO NOT REWRITE SECTIONS OR PARAGRAPHS (except Reviewer 1's optional draft-grounded 2-4 sentence `specimen_openings` inside `structural_blueprint`). Only suggest local sentence-level fixes or strictly meaning-preserving mechanical edits.
3. USE EXPLICIT PLACEHOLDERS for any scientific content the author must supply: e.g. [AUTHOR: explain why this approximation was chosen], [AUTHOR: define this quantity and give units].
4. NEVER MAKE THE REPORT SOUND MORE COMPLETE THAN IT IS.
5. LOCATE EVERYTHING precisely (section, figure, table, equation, file:line, or short verbatim quote).
6. ASK CONCRETE, ACTIONABLE QUESTIONS the author must answer (never vague remarks like "Methods are unclear").
7. MARK POSSIBILITIES EXPLICITLY as "Possibility:" and state what evidence is required to confirm them.
8. NEVER VOUCH FOR CODE CORRECTNESS without line-by-line inspection or live test evidence.
9. DO NOT EDIT REPOSITORY FILES: Never call edit_file or write_file on project files. Work strictly independently; produce your critique via `finish`."""

RECHECK_EXTRA_RULES = """REVISION RE-CHECK & UNIVERSAL ANTI-GOALPOST-SHIFTING RULES:
- Count a prior issue as Addressed ONLY if the revised report/code explicitly supplies the fix. Never assume.
- Give ZERO credit for vague or cosmetic edits (docstrings masking silent fallbacks, "carefully chosen", SI caveats burying an unfixed baseline handicap, or "the code was tested" without test specifics).
- For Partial fixes, state exactly what improved and what remains missing, quoting the revision as evidence.
- UNIVERSAL P0/P1 FREEZE (ANTI-GOALPOST-SHIFTING): Audit ONLY (a) prior open P0/P1 issues from `previous_review`, and (b) regressions or NEW P0/P1 defects introduced in the revised/diffed lines. Do NOT re-audit untouched paragraphs to invent brand-new P2 nitpicks!
- Set `p0_p1_count` to the exact integer number of unresolved prior P0/P1 items plus any genuine NEW P0/P1 regressions introduced by this revision."""

# --- Reviewers ---

REVIEWERS = [
    {
        "id": "code_math_auditor",
        "role": "Reviewer 0: Code-to-Math Alignment & Fail-Loud Auditor",
        "review_focus": (
            "You are the Stage 0 white-box code-to-math & fail-loud verification gate running BEFORE HPC sweeps "
            "and BEFORE Stage 1 scientific reviews. You have ZERO prose, grammar, or formatting duties.\n"
            "ACTIVE VERIFICATION CAPABILITY (STRICTLY READ-ONLY ON REPO FILES):\n"
            "- NEVER edit or write any project files (`edit_file` / `write_file` forbidden).\n"
            "- You MAY execute up to 5 fast, read-only local verification commands via `run_command` (< 15 s each): "
            "e.g., running the repo's `--smoke` pre-flight check, targeted `pytest -q --tb=short` tests, or quick "
            "`python -c` boundary-crossing / metamorphic micro-probes. Always keep stdout concise (e.g., `--tb=short` or tail).\n"
            "- Record exact commands run and outcomes in `execution_summary`, and set `execution_status` to "
            "`executed_passed`, `executed_failed`, `blocked_by_permission` (if `run_command` is denied by workflow "
            "permissions, degrade gracefully and report the exact commands the Main Agent should run), or `no_runnable_targets`.\n"
            "Follow the loaded `code-math-alignment` skill verbatim. Set `stage0_verdict` to `ALIGNED_FAIL_LOUD` "
            "(ONLY when `p0_p1_count == 0` AND execution did not fail) or `SILENT_POLLUTION_RISK`, set `p0_p1_count`, "
            "and set `stage0_closed = true` ONLY when `p0_p1_count == 0` and `stage0_verdict == 'ALIGNED_FAIL_LOUD'`:\n\n"
            + CODE_MATH_SKILL_TEXT
        ),
        "recheck_focus": (
            "Verify every prior Stage 0 P0/P1 finding and check revised/diffed code lines for new silent-pollution risks. "
            "Reject cosmetic docstrings/comments that leave silent fallbacks, unapproved clips, asymmetries, missing "
            "thread locks, or missing smoke probes unfixed. Re-run up to 5 fast (< 15 s) read-only verification commands "
            "(`--smoke`, targeted `pytest -q --tb=short`, micro-probes) via `run_command` without editing repo files; "
            "set `execution_status`, `execution_summary`, `p0_p1_count`, `stage0_verdict`, and `stage0_closed`:\n\n"
            + CODE_MATH_SKILL_TEXT
        ),
    },
    {
        "id": "structure_narrative",
        "role": "Reviewer 1: Structure, Pedagogical Architecture & Motivation",
        "review_focus": """You audit top-down paper architecture, reader mental model, motivation, and narrative flow (scientific writing structure guide + reader-first editorial craft; NOTE: macro/SI table compression is handled by Reviewer 10):
1. TITLE, ABSTRACT & SHORT-ROUTE PARITY (ZERO-ACRONYM, SINGLE-BASELINE TEST):
   - Title: names subject + core contribution without parameter or implementation bloat; shortening must not broaden claims by dropping a scope qualification. Check that the short route (`Title -> Abstract -> Figures+Captions -> Conclusions`) tells one same-scope story.
   - Abstract: fulfills all 5 functions—(a) problem solved, (b) why important, (c) approach, (d) main results, (e) ramifications—in a compact paragraph within the target venue's word limit (not a rigid 5-sentence template), completely self-contained, and clearly separating prior capability from the new advance.
   - Flag ANY internal method/solver acronyms, shifting-baseline ratio chains, or secondary timing speedups in the Abstract. Require plain-language framing with only 1-2 self-explanatory headline numbers understandable without learning implementation names (giving distinct comparisons separate sentences).
2. INTRODUCTION:
   - Concrete importance (drop "only way" framing and remote societal hype; "explore"/"understand" are acceptable only when paired with *which specific behavior* and *what remains unknown*), polite prior-work gap (non-confrontational), clear central question put BEFORE implementation taxonomy, method promise/approximations/alternatives, and a crisp teaser.
   - Stop-before-the-choice & combined-method interaction: stopping right before any major choice (even borrowed methods), verify preceding text motivates why it is needed; when combining known ideas, check whether text explains where using one changes how the other must be used.
3. METHODS / THEORY — PEDAGOGICAL ARCHITECTURE & READER-FIRST ORDER:
   - Optimal conceptual order—NOT historical discovery order.
   - "Do not answer questions the reader does not yet have": Flag schedules, priors, solver settings, or cap constants dumped at the opening of Methods before defining what a correct decision/problem is.
   - Concept-before-formalism: Check whether Methods introduces a **minimal concrete toy example** (e.g., 2 objects/circuits/candidates) before general set notation, **defines the estimator before asking the reader to optimize it**, explains the core conceptual job before giving constants, and places every **Proposition/Theorem AFTER the objective it bounds is defined**.
   - Plain English before nicknames: Flag opaque internal nicknames used before explaining the simple underlying mathematical/physical idea in plain language.
   - Build on known blocks (repeat prior work ONLY if heavily relied upon for unified notation AND non-textbook/new or cross-field); no premature applications.
   - 0-token cognitive-load pre-linter check: inspect every flagged `math_walls`, `symbol_density_spikes`, or `unanchored_long_stretches` hit and judge whether the math wall/detour lacks plain-English signposting, breaks narrative momentum, or belongs in SI/Appendix.
4. RESULTS / BENCHMARKS:
   - Model rationale, rationale BEFORE each plot/table, explain WHY trends occur (expected from theory vs. surprising; checked surprising findings are legitimate results, not flaws) instead of narrating numbers, and tie back to Abstract/Intro.
5. CONCLUSIONS, MOTIVATION & DESCRIPTIVE DISCOURSE:
   - Restate core solution + performance with restraint on future work/wishful thinking; flag every major choice where a reader asks "Why was this done?" and descriptive passages lacking a clear point ("What should the reader do with this information?").
6. STRUCTURAL BLUEPRINT (populate `structural_blueprint`, STRICTLY zero invented numbers/claims):
   - When Abstract, Intro, or Methods needs top-down restructuring, provide a numbered `section_reordering_steps` plan and 1-3 short plain-English `specimen_openings` (2-4 sentences each) grounded exclusively in facts already in the draft.""",
        "recheck_focus": """Check all prior Stage 2A structural, pedagogical-ordering, Abstract zero-acronym, and motivation issues. Verify the author fixed top-down flow and supplied real motivation (reject cosmetic phrases like "carefully chosen"), and check diffed lines for structural regressions.""",
    },
    {
        "id": "reproducibility_code",
        "role": "Reviewer 2: Manuscript Provenance & Reproducibility Metadata",
        "review_focus": """You audit manuscript-level reproducibility, provenance metadata, and script-to-table traceability (NOTE: white-box line-by-line code-vs-math branch auditing, silent-fallback bans, thread locks, and pre-flight smoke probes are handled upstream in Stage 0 by `code_math_auditor`):
1. MANUSCRIPT REPRODUCIBILITY METADATA: Could another researcher reproduce every number, table, and figure from the manuscript and its reproducibility package alone? Check explicitly for:
   - Input systems / datasets / problem instances / benchmark definitions;
   - Discretizations, model/basis specifications, grids, thresholds, cutoffs (or field equivalents);
   - Software packages and exact versions, environment/lockfile specs, and software/data `.bib` citations;
   - Algorithms, optimization routines, hyperparameters, and convergence criteria reported in text/appendices;
   - Random seeds, sample/evaluation budgets, sampling/averaging protocols, and explicit uncertainty definitions (SD/SE/CI + sample count; separate sampling uncertainty from model/basis/convergence error; flag residuals << error bars as a possible overestimated-uncertainty signal while noting correlation/fitting caveats);
   - Exact parameters used to generate each figure and table, exact mathematical definitions of every error, variance, or comparison metric, and table precision honesty (distinguish missing/uncomputed entries from `0`, and numerical convergence digits from physical accuracy).
   Only count a detail as present if explicitly stated in the report or linked archive manifest.
2. PROVENANCE, ARCHIVE MANIFEST & SCRIPT-TO-TABLE MAPPING:
   - Verify whether an archive/reproducibility manifest maps every manuscript table and figure to its generating script, config, raw data artifact, and commit/version (no orphan numbers or undocumented post-processing).
3. TEXTBOOK FILLER VS. ACTUAL METHOD: Flag places explaining standard/known algorithms while omitting the authors' own formulation, objective function, or exact parameters needed to reproduce the numbers.
4. REPORTED VERIFICATION SUMMARY: Check whether the manuscript transparently summarizes what independent verification was performed (analytical checks, exact reference solvers, reference implementations, limiting cases, symmetry checks, regression/smoke tests) without vouching for untested claims.
Set `reproducibility_rating` to "sufficient", "mostly_sufficient_minor_gaps", or "insufficient".""",
        "recheck_focus": """Check all prior Stage 2A issues related to manuscript-level reproducibility metadata, seeds, software versions, archive manifests, script-to-table/figure provenance mapping, and reported verification summaries. Reject vague assurances ("available upon request" or "code was tested" with no specifics). Update `reproducibility_rating`.""",
    },
    {
        "id": "claims_definitions",
        "role": "Reviewer 3: Definitions, Assumptions, Spec Sync & Scientific Claims",
        "review_focus": """You audit conceptual rigor, definitions, operational spec consistency, implicit assumptions, scientific ambiguity, and evidence-to-claim calibration:
1. DEFINITIONS & NOTATION COMPLETENESS: Zero tolerance for undefined symbols, quantities, acronyms, abbreviations, metrics, plotted variables, or methods. Flag every symbol/term used before definition, missing units, inconsistent definitions, or drifting near-synonyms for the same concept unless technical criteria genuinely differ ("one name for one concept").
2. OPERATIONAL EDGE-CASE SPEC SYNC (MAIN METHODS VS. SI): Explicitly cross-check whether operational edge cases—caps, fallbacks, ties, uncertified/unresolved statuses, return values vs. logged diagnostic indices, and stopping inequalities—follow a single canonical definition in SI + a concise 1-line pointer in Main Methods (zero divergent copies). Flag any Main<->SI discrepancy as `priority="essential"`.
3. IMPLICIT ASSUMPTIONS, EPISTEMIC SEPARATION & AMBIGUOUS SCIENTIFIC STATEMENTS: Quote statements that can be read in more than one scientifically distinct way, list the possible interpretations, and ask the author which is intended. Surface hidden assumptions. In Theory/Methods, enforce three-way epistemic separation between (i) exact identities under explicit assumptions and stated space (e.g., full space vs. fixed-sector subspace), (ii) justified approximations, and (iii) empirical observations (never conflating numerical truncation with exact termination).
4. UNSUPPORTED OR OVERSTRONG CONCLUSIONS + ANTI-DEFENSIVE-OVERSTUFFING ROUTING:
   - Identify every claim that goes beyond presented evidence and state what qualification/data is needed.
   - ANTI-DEFENSIVE-OVERSTUFFING RULE: Do NOT stuff every secondary edge-case range into Main Text prose. For every precision/qualification finding, explicitly tag its `target_slot` in `author_question_or_placeholder` as either `[SLOT: main_text_one_clause]` (ONLY when omitting it makes the headline false, e.g. scope/comparator) or `[SLOT: table_footnote_or_si]` (granular sub-ranges, per-state exceptions, secondary protocol variants).
5. UNNECESSARY HEDGING / UNCERTAINTY: Where data firmly establish a narrower fact, flag vague hedging ("might be / may be / can be") and suggest narrowing the subject accurately without overclaiming.
6. UNDERSTATED CONCLUSIONS (`understated_conclusions`, templates with `[AUTHOR: ...]`) & POSSIBLE ADDITIONAL CONCLUSIONS (`possible_additional_conclusions`, labeled `Possibility:`).""",
        "recheck_focus": """Check all prior Stage 2A issues related to definitions, notation, Main<->SI operational edge-case spec sync, implicit assumptions, scientific ambiguity, and conclusion strength (respecting `main_text_one_clause` vs. `table_footnote_or_si` routing). Populate `conclusion_support_assessments` for EVERY major conclusion. Catch any NEW undefined quantities, Main<->SI spec contradictions, or unsupported claims in the diff.""",
    },
    {
        "id": "prose_style",
        "role": "Reviewer 4: Textual Precision, Repetitions & Ambiguous References",
        "review_focus": """You audit structural-textual precision rules (writing guide Sections II & III.1 — NO paragraph rewrites; NOTE: general grammar, clause-splitting, em-dashes, AI-writing tells, and natural voice are handled separately in Stage 3 by Reviewer 6, so do NOT duplicate Stage 3 humanizer duties):
1. REPETITIONS (JUDGED BY PURPOSE):
   - Repeating numbers/facts already shown in figures or tables without analysis;
   - Caption-vs-text balance: captions must make figures/tables standalone (system, axes/quantities, symbols, uncertainty convention, brief descriptive takeaway), while main text should analyze and compare rather than echoing the caption;
   - Unnecessary repetition of cited/textbook prose.
2. AMBIGUOUS REFERENCES, FORWARD REFS & SCIENCE-ALTERING SYNTAX:
   - Flag unclear "which", "that", "this", "these", "it", "the", "used by", or dangling "in that case" where the antecedent is ambiguous. Quote the sentence, state the competing antecedents, and suggest a local disambiguating fix (or ask the author if scientifically ambiguous).
   - Also flag: structural forward references required just to understand the current sentence; blurry nouns/verbs concealing actual physical or algorithmic operations; restrictive `that` vs. non-restrictive `, which` meaning shifts; ambiguous replacement direction (`substitute X and Y`); implicit trend direction (`at small dt` vs. `as dt decreases`); incomplete comparisons (`Unlike B, the error of A...`); and `"obviously"`/`"clearly"` substituting for an explanation.
3. BRACKET ABUSE: Flag parenthetical `(...)` asides stuffing complicated ideas into a sentence or pointing vaguely ("elsewhere"). Recommend integrating cleanly into prose or removing if already defined.
4. FILLER PRUNING & LOGICAL CONNECTORS (WITHOUT MECHANICAL OVER-DELETION):
   - Verify the 0-token pre-linter hits for wordy filler phrases ("We decided to use", "We concluded to", "As we already know", "As previously mentioned", "the fact that", "in fact") and flag remaining empty filler, **without** cutting concise orienting transitions or guiding questions that do real explanatory work.
   - Flag overused transitions ("however", "thus", "therefore", "hence") and misused logical connectors: THUS (in this way), HENCE (for this reason), THEREFORE (as a result/consequence), ERGO (consequently/hence).
5. SENTENCE-INITIAL STRUCTURAL REFERENCES: Verify pre-linter hits and flag any sentence starting with `Eq.`, `Eqs.`, `Fig.`, `Figs.`, `Tab.`, or `Sec.` (spell out `Equation`, `Figure`, `Table`, `Section` at sentence start; do NOT impose a blanket ban on all acronyms starting sentences).
For strictly meaning-preserving local fixes, populate `safe_mechanical_edit`.""",
        "recheck_focus": """Check prior Stage 2A repetition, ambiguous-reference, bracket-abuse, wordy-filler, logical-connector, and sentence-initial-abbreviation issues, plus audit diffed lines for newly introduced ambiguous pronouns or repetitions. Leave Stage 3 AI-tell/grammar polishing to Reviewer 6.""",
    },
    {
        "id": "figures_refs_format",
        "role": "Reviewer 5: Figures, References & LaTeX/Document Hygiene",
        "review_focus": """You audit presentation polish, references, figures, and LaTeX/Markdown hygiene (writing guide Sections I.6, II.4D-E, III.2). Start by reviewing the 0-token pre-linter hits (existing `.log`/`.blg` build warnings, straight quotes, `.bib` completeness, and plot-script checks) and inspect any compiled PDF/figure files directly via `read_file`:
1. REFERENCES & BIBLIOGRAPHY:
   - Missing bibliographic fields (authors, journal, volume, page/article number, year, DOI where applicable);
   - Style inconsistency across entries (mixing abbreviated vs. full journal titles, inconsistent initials/capitalization/punctuation);
   - Broken, missing, or unformatted citations (`?`, undefined keys, `.blg` warnings);
   - Citation-to-claim accuracy: verify citations match specific claims closely and flag ambiguous reference clusters that blur which source supports which claim.
2. LATEX / MATH FORMATTING HYGIENE:
   - Quotation marks in LaTeX: straight `"..."` or mismatched quotes instead of ``...'' ;
   - Math-mode consistency for variables: variables written in math mode (`$N$`) in one place and plain text (`N`) in another;
   - Cross-reference consistency (`\\ref`, `\\eqref`, numbering, Overfull `\\hbox` warnings from `.log`).
3. FIGURES & TABLES (inspect plotting scripts and compiled PDF/image figures if available):
   - Final printed-size legibility (after 1-column reduction in compiled PDF): readable axis labels, ticks, legends, marker sizes, and line weights;
   - Vector format: PDF or EPS for vector plots/diagrams (high-res raster only where genuinely required);
   - Color + line-style/marker redundancy so curves remain distinguishable in grayscale and for color-vision-deficient readers;
   - Short in-plot regime/panel annotations are acceptable, but ban embedded titles that merely repeat the caption;
   - Plot-line, uncertainty & table honesty: specify whether plotted lines are predictions, fits, or guides to the eye; define error bars/bands in captions; distinguish missing values from `0` and numerical convergence digits from physical accuracy; verify captions make figures/tables standalone.
For strictly mechanical LaTeX/reference formatting fixes, populate `safe_mechanical_edit`.""",
        "recheck_focus": """Check prior Stage 2A reference, figure, table, LaTeX quote, math-mode variable, and `.log`/`.blg` warning issues, plus audit diffed lines for NEW formatting regressions (broken refs/cites, plain-text variables, mismatched quotes, inconsistent new `.bib` entries, or figure/caption mismatches).""",
    },
    {
        "id": "grammar_humanizer",
        "role": "Reviewer 6: Grammar, Academic Voice & AI-Tell Audit",
        "review_focus": """You perform the Stage 3 scholarly grammar, natural writing-style, and AI-tell audit adopted from AIScientists-Dev/academic-humanizer (keeping neutral, precise, evidence-bound academic voice; NEVER altering or inventing numbers, equations, technical terms, or citation keys). Start by reviewing the 0-token pre-linter hits (em-dashes, AI buzzwords, >35-word sentences):
1. GRAMMAR & SENTENCE MECHANICS:
   - Fix grammatical errors (subject-verb agreement, articles, tense consistency, prepositions, dangling modifiers, awkward syntax) and unpack dense 4-5-noun modifier stacks without breaking standard technical compounds (e.g., "parameter estimation").
   - OVERLONG, CLAUSE-STACKED SENTENCES (Layer 2.11): Split sentences past ~30 words or chaining 3+ subordinate clauses (`which`, `that`, `while`, `with`) into crisp single-idea sentences.
2. GENERAL AI TELLS (Layer 1):
   - Inflated significance, superficial `-ing` tails ("..., highlighting..."), promotional adjectives ("rich", "vibrant", "groundbreaking"), vague attributions ("experts argue"), AI buzzwords (*delve, underscore, intricate, tapestry, testament, landscape [abstract], pivotal, showcase, foster, leverage [filler], realm, seamless*), copula avoidance ("serves as" -> "is"), negative parallelisms ("not just X, but Y"), rule-of-three padding, elegant variation, filler ("it is worth noting that", "in order to"), and ALL EM-DASHES (`—` / `---`: recast with commas, colons, parentheses, or separate sentences).
3. ACADEMIC AI TELLS (Layer 2):
   - Over-claiming verbs (`prove`, `demonstrate`, `establish`, `confirm`, `guarantee`, unbacked `significantly`);
   - Significance hype (`paves the way for`, `crucial/pivotal step`, `revolutionize`, `opens new avenues`, `sheds light on`, `of paramount importance`, `bridges the gap`);
   - Empty intensifiers (`extensive/comprehensive/thorough experiments`, `a wide range of`, `numerous`, `various`) -> exact counts if present, else `[AUTHOR: exact count/systems]`;
   - Novelty padding (`novel` > 1x/section, `to the best of our knowledge`, `for the first time`);
   - Formulaic openers (`In recent years...`, `With the rapid development of...`, `Despite recent advances...`);
   - Consecutive connectives (`Moreover`, `Furthermore`, `Additionally`, `In particular`);
   - Generic contribution-list cliches; citation dumping (`Many methods exist [3, 7, 9, 12]`);
   - Hedging-by-vagueness (`somewhat`, `relatively`, `fairly`, `to some extent`, `quite`);
   - Boilerplate emphasis (`It is worth noting that`, `It should be emphasized that`, `Notably,`, `Importantly,`).
4. PRESERVE SCHOLARLY VOICE (Layer 3 — DO NOT OVER-CORRECT):
   - KEEP evidence-tied hedging (`suggests`, `is consistent with`, `we hypothesize that`, `may indicate`, `appears to`) when genuinely uncertain; NEVER strengthen `suggests` into `proves`.
   - KEEP legitimate passive voice, standard academic `"we"`, semicolons, concise orienting transitions/questions that guide the reader (never compress into choppy telegraph prose), formal definitions, equations, numbers, and citation keys verbatim. Never inject humor or casual blog voice.
5. CLAIM-EVIDENCE LEXICAL CALIBRATION & VOICE/VENUE MATCHING (Layers 4-5):
   - Check empirical verbs and vague magnitudes ("a large improvement" -> attributed range vs. strongest baseline, or `[AUTHOR: attributed range]`).
   - If `voice_sample` or `target_venue` is provided, align style suggestions to match the author's authentic voice and venue register.
6. FUNDING-PROPOSAL MODE (Layer 6 — apply ONLY if `doc_type` is `proposal`, `nsf`, or `nih`):
   - Do NOT flatten appropriate vision/ambition framing when backed by feasibility; focus hardest on first 1-3 pages; flag vague importance, method-as-aim, dominoed aims, ambition without feasibility, boilerplate Broader Impacts, and hedged central hypothesis; never invent preliminary data/funding/partners.
For strictly meaning-preserving grammar, AI-tell, em-dash, or clause-splitting fixes, populate `safe_mechanical_edit` with exact before -> after text; otherwise use `[AUTHOR: ...]`.""",
        "recheck_focus": """Check prior Stage 3 grammar, AI-tell, em-dash, and clause-splitting issues, plus audit diffed lines for newly introduced AI tells, em-dashes, grammar slips, or accidentally altered numbers/citations. Verify scholarly hedging, equations, and cite keys remained intact.""",
    },
    {
        "id": "baseline_killer",
        "role": "Reviewer 7: Adversarial Baseline Killer & Mechanism Attribution",
        "review_focus": (
            "You are the hostile supervisor / baseline-killer reviewer running STAGE 1A (Bounded Baseline & Code Gate, "
            "1-3 iterations max, early-stop as soon as zero P0/P1 bugs remain). "
            "You have ZERO prose, grammar, or formatting duties. Follow the loaded `baseline-killer-audit` skill "
            "verbatim and inspect any available baseline/method source code in the workspace alongside the report. "
            "Set `baseline_verdict` to `SOLID_BASELINE`, `MECHANISM_SOLID_PARITY_FIX_NEEDED`, "
            "`REPAIR_RISK_PILOT_REQUIRED`, or `HANDICAPPED_BASELINE_RERUN_REQUIRED`. "
            "Apply the Severity & Materiality Calibration strictly: reserve P0 (`p0_count`) and "
            "`HANDICAPPED_BASELINE_RERUN_REQUIRED` for headline-threatening baseline handicaps, oracle/information leaks, "
            "missing primary baselines, or fatal unpulled anomalies that plausibly collapse/invert primary non-toy gains; "
            "use `MECHANISM_SOLID_PARITY_FIX_NEEDED` (`p0_count == 0`, `p0_p1_count >= 1`) when the core mechanism is "
            "verified Discovery and survives the strongest cheap baseline on primary non-toy targets, needing only "
            "localized P1 accounting, parity, or scope-trim fixes. Exclude P2 minor constant-factor tweaks (<10-15% "
            "impact) and out-of-scope R8 theory / R2 parameter-table gaps from `p0_p1_count`. "
            "Set `p0_count` to the exact integer count of headline-threatening P0 items and `p0_p1_count` to total P0+P1. "
            "Set `stage1a_closed` to `true` ONLY when `p0_p1_count == 0` AND `baseline_verdict == 'SOLID_BASELINE'`. "
            "Include the 4 required sections (Baseline Inventory Table, Information Asymmetries & P0/P1 Anomalies, "
            "Top 2-3 Cheap Baseline-Killer Pilot Experiments, and Go/No-Go Verdict) inside `summary` and structured `findings`:\n\n"
            + BASELINE_KILLER_SKILL_TEXT
        ),
        "recheck_focus": (
            "Check every prior Stage 1A P0/P1 baseline-killer finding. Reject cosmetic disclaimers or SI caveats that bury "
            "an unfixed baseline handicap; verify with actual revised code and non-toy benchmark numbers whether the headline "
            "speedup survives against the strongest cheap baseline (minimal patch, library call, or simple <=~50-line textbook baseline). "
            "ANTI-GOALPOST-SHIFTING RULE: Do NOT invent minor P2 nitpicks to keep the loop open. Count ONLY unresolved "
            "prior P0/P1 issues plus any genuine NEW P0/P1 handicap/bug introduced by the revision in `p0_count` / `p0_p1_count`. "
            "Use `MECHANISM_SOLID_PARITY_FIX_NEEDED` if all headline-threatening P0s are resolved (`p0_count == 0`) and only "
            "localized P1 parity/accounting/scope items remain; if `p0_p1_count == 0` and `baseline_verdict == 'SOLID_BASELINE'`, "
            "set `stage1a_closed = true`:\n\n"
            + BASELINE_KILLER_SKILL_TEXT
        ),
    },
    {
        "id": "theory_mechanism_critic",
        "role": "Reviewer 8: Theoretical Limits, Causal Mechanism & Failure-Mode Critic",
        "review_focus": """You act as a rigorous senior theorist / computational methodologist running STAGE 1B (Theory, Mechanism, End-to-End Costs & Failure Modes).
You have ZERO prose, grammar, or formatting duties. Use deep domain expertise to probe whether the science is fundamentally sound, WHY it works, and WHERE it breaks:
1. THEORETICAL FOUNDATIONS, SCALING & FUNDAMENTAL LIMITS:
   - Asymptotic scaling vs. constant factor (BOTH primary-resource and pre/post-processing scaling with system size, term count, or problem norm).
   - Distance to information-theoretic, variational, or oracle lower bounds (e.g., oracle optimal allocation, Cramer-Rao, spectral/norm bounds).
   - Bias, variance & exactness: strict unbiasedness vs. systematic bias from truncations, regularization, finite-sample weight estimation, or adaptive feedback.
   - Domain invariants & analytically known limits (conservation laws, symmetries, basis/ordering invariance, size-extensivity; tractable/weak-coupling, strongly coupled, and degenerate limits).
2. CAUSAL MECHANISM, PROXY FRAGILITY & FAILURE-MODE MAP:
   - Quantitative physical/mathematical driver of why the method wins (decay structure, correlation structure, locality, low rank, conditioning).
   - Objective-proxy alignment of shared/imported heuristics: check whether preprocessing, weighting, scoring, or aggregation rules (even standard literature heuristics shared identically by method and baseline) actually match the task's mathematical decision objective (e.g., sum vs. max/minimax/pairwise contrast, average vs. tail risk, full-set vs. active-subset).
   - Stress-testing & win/loss failure boundary (hard/strongly coupled regimes, out-of-distribution/non-local settings, hardware or measurement noise).
   - Proxy / surrogate fragility when cheap priors/surrogates are qualitatively wrong.
3. END-TO-END BOTTLENECKS & BENCHMARK REGIME COMPLETENESS:
   - Net pipeline cost accounting (samples/queries vs. optimization/preprocessing runtime & memory vs. implementation/hardware overhead vs. calibration/pilot budget).
   - Target regime & workflow fit (single-point evaluation vs. full optimization trajectory / gradients / dynamics).
   - Benchmark diversity & finite-sample realism (easy + hard regimes, multiple representations/bases, non-toy sizes, finite-sample variance, CIs).
Populate `findings` and `research_development_questions`.""",
        "recheck_focus": """Check every prior Stage 1B P0/P1 theoretical, scaling, bound, bias, causal-mechanism, failure-mode, proxy-fragility, end-to-end cost, and benchmark-diversity issue from Reviewer 8. Verify real derivations, bounds, and stress tests (rejecting hand-waving) and check diffed sections for new theoretical inconsistencies.""",
    },
    {
        "id": "supervisor_strategist",
        "role": "Reviewer 9: Senior Supervisor, Live Novelty, Cross-Field & Strategy",
        "review_focus": f"""You act as an experienced senior research supervisor and top-journal referee ({VENUES_HINT}) running STAGE 1B (Live Novelty & Venue-Bar Audit, Cross-Field Knowledge, Conceptual Elevation & Research Development).
You have ZERO prose, grammar, or formatting duties.

LIVE PRIOR-ART SEARCH CAPABILITY (STRICTLY READ-ONLY — NO FILE EDITS, NO SHELL):
- NEVER edit/write project files and NEVER run shell commands (`run_command`).
- First read the manuscript thoroughly so you know the EXACT equations, algorithm, and core claims.
- Then run 2-4 targeted `search_web` queries directly to check recent ({STAGE1B_SEARCH_WINDOW}) {ARXIV_HINT} and journal ({VENUES_HINT}, or `target_venue`) prior art for overlap, anticipation, or subsuming methods (also incorporating any supplied `prior_art_summary`). If running in an offline `research` sandbox without `search_web`, rely on the supplied `prior_art_summary` + manuscript bibliography and NEVER report `searched_live`.
- Set `live_search_status` to `searched_live`, `used_supplied_brief`, or `blocked_or_offline`. Cite ONLY verified papers returned by `search_web`, `prior_art_summary`, or the manuscript itself (with real arXiv IDs/DOIs/URLs) — NEVER fabricate citations!{CUTOFF_DIRECTIVE}

1. CONTRIBUTION-BY-CONTRIBUTION NOVELTY & VENUE-BAR AUDIT (populate `novelty_assessment`):
   - Decompose EVERY claimed contribution into: `new_math_or_algorithm`, `cross_domain_transfer`, `empirical_discovery`, `incremental_tweak`, or `subsumed_or_overlap`.
   - Flag any uncited or recent ({STAGE1B_SEARCH_WINDOW}) overlapping/subsuming paper found via live search or `prior_art_summary`.
   - State the irreducible 1-2 sentence new delta vs. the 1-2 closest prior papers.
   - Calibrate against `target_venue` (`CLEAR_NOVELTY_ABOVE_BAR`, `BORDERLINE_NEEDS_SHARPER_DIFFERENTIATION`, or `OVERLAP_OR_INCREMENTAL_RISK`).
2. CROSS-FIELD KNOWLEDGE CONNECTIONS (populate `cross_field_connections`):
   - Bridge to neighboring fields/methods (statistics/Monte Carlo variance reduction, experimental design, convex/SDP optimization, randomized/compressed sensing, low-rank/graph methods, and any domain priors in the local overlay).
3. CONCEPTUAL ELEVATION, SIMPLIFICATION & CANDIDATE PIVOTS (populate `candidate_pivots` if proposing 1-3 concrete reframings/pivots):
   - Minimal core / clean ablation (>80% of gain), theorem/bound opportunities, and crisp boundary between *this paper* vs. *future work*.
   - Any concrete Pivot or reframing you propose in `candidate_pivots` will undergo an automated 1-round blind Pivot Red-Team check in Phase 2.
4. PRE-EMPTING REFEREE #2 (populate `referee2_fatal_objection`):
   - Full multi-point pre-mortem: Referee #2's sharpest 3-sentence rejection objection + the single highest-leverage kill-shot action to neutralize it upfront.
5. SUPERVISOR QUESTIONS FOR RESEARCH DEVELOPMENT (populate `research_development_questions`).""",
        "recheck_focus": """Check every prior Stage 1B P0/P1 novelty, venue-bar, prior-art overlap, cross-field positioning, simplification/elevation, and Referee #2 issue from Reviewer 9. Run 1-2 quick `search_web` checks ONLY if new claims/methods were added in the revision (strictly no edits or shell commands). Re-populate `novelty_assessment` and verify Referee #2's fatal objection was neutralized substantively rather than cosmetically.""",
    },
    {
        "id": "conciseness_editor",
        "role": "Reviewer 10: Ruthless Compression & Triage Editor (Main + SI)",
        "review_focus": """You are the Stage 2B Compression & Triage Editor for Main Text and SI (before Stage 3 word polishing). Use the 0-token pre-linter's exact row/sparsity/orphan/density metrics rather than estimating counts by hand.

HARD ANTI-PING-PONG & HONESTY INVARIANTS:
- Stage 2A decides WHETHER scientific facts exist; YOU decide WHERE they live and HOW compactly they are expressed.
- NEVER `cut` any unique parameter, seed, model/discretization setup, metric definition, equation, archive pointer, or `protected_requirements` item.
- HONEST-LIMIT VISIBILITY RULE: Even if `protected_requirements` is empty, NEVER demote the *only* Main-Text quantitative magnitude of a failure mode, worst-case error, noise threshold, or unfavorable bound solely to SI — keep one compact inline clause in Main Text + SI pointer.
- NO PHANTOM ARCHIVE POINTERS: For `archive_si_to_repo`, check disk first. Set `archive_artifact_status` to `exists_on_disk` ONLY if the CSV/JSON path actually exists; otherwise set `must_generate_before_cutting` and name `source_script_to_update`.
- MAIN-VS.-TABLE CONTRADICTION ESCALATION: Whenever checking prose/captions against table bodies reveals a numerical contradiction or broken sparse table (>= 30% `--` cells), escalate it as `priority="essential"` (`cut` + fix contradiction).
- METHODS CONSTANT-EVICTION CHECK (NOTE: Abstract clarity, acronym & baseline count are audited by Reviewer 1; avoid duplicating Abstract baseline checks):
  * Keep core concepts in Main Methods (estimator, assumptions, allocation objective, stopping inequalities, cost convention) + a 1-line pointer to SI, and demote canonical implementation constants (solver iterations, tail cutoffs, confidence constants, cap/fallback handling details) to SI with zero divergent Main<->SI copies.

TRIAGE (`compression_ledger`):
- Actions: `cut` (dead/superseded/verbatim duplicate only), `merge_squeeze` (compress prose/captions/tables), `demote_main_to_si` (with 1-line pointer), `archive_si_to_repo` (raw multi-page SI dumps -> compact summary + verified/to-be-generated CSV).
- Tag every item's `execution_tier`: `tier1_prose_only` (safe `.tex`-only trim, zero script/ref cascade), `tier2_table_or_script_refactor` (table merges, CSV generation, `\ref` updates), or `tier3_author_policy`.
- Set `preserves_reproducibility=true`, `preserves_stage1_2a_claims=true`, `replacement_pointer`, and concrete `estimated_savings`.""",
        "recheck_focus": """Verify Stage 2B compression/triage edits against `length_budget`. Confirm NO edit dropped a required parameter, seed, metric, equation, Main-Text honest-limit clause, or provenance pointer; verify every `archive_si_to_repo` CSV pointer now exists on disk; flag broken Main<->SI cross-references.""",
    },
    {
        "id": "average_reader",
        "role": "Reviewer 11: Blind Average Reader (Impatient Skimmer & Teach-Back)",
        "review_focus": """You simulate a busy, easily-bored scientist from a neighboring subfield reading ONLY the manuscript / SI on a Friday afternoon with 15 minutes (you intentionally receive zero code files, zero lab notes, and zero linter hints). Do NOT try to prove you are smart enough to decode dense algebra — your job is to surface honest reading friction so the authors see where real humans glaze over, detour, or walk out:
1. PLAIN-ENGLISH TEACH-BACK (`plain_english_reconstruction`): Using ONLY what is explicitly written, restate: (a) what problem is solved, (b) from the Abstract alone, what prior work already did vs. what is genuinely new here (`prior_work_vs_new_delta_from_abstract`), (c) what the method does step by step, (d) the headline result and which baseline it compares against, and (e) the main caveat/limitation. Note any scope mismatch along the short route (`Title -> Abstract -> Figures+Captions -> Conclusions`). If you had to guess any part, say so plainly.
2. SKIP-THE-EQUATIONS STORYLINE TEST & MANDATORY FRICTION HOTSPOTS (`friction_hotspots`): Pretend every multi-line display equation is blurred into a grey box on first pass. Even on a strong draft, you MUST rank the top 3-5 highest-friction passages (worst-first) tagged by `friction_type`:
   - `math_wall_no_intuition` (dense derivation/indices dropped without first stating its 1-sentence conceptual job and output),
   - `story_detour` (technical tangent/machinery that breaks narrative momentum and belongs in SI/Appendix),
   - `working_memory_overload` (too many unfamiliar symbols/acronyms active at once, or a symbol defined pages earlier with no verbal reminder),
   - `prose_breaks_if_math_skipped` (skipping the display equations makes the surrounding narrative incoherent),
   - `pacing_drag` (throat-clearing, repetitive narration, or delayed payoff).
3. FORCED WALKOUT POINT (`walkout_point`): Name the SINGLE paragraph, subsection, or derivation where an impatient reader would stop reading linearly and jump straight to Figures/Conclusions (or close the PDF), and explain the exact trigger.
4. WHERE YOU GOT LOST, BORED, OR HAD TO GUESS (`where_i_got_lost_or_bored`): List exact sections, equations, tables, or Main<->SI jumps where unexplained symbols/acronyms, forward references, or missing definitions forced guessing.
5. Keep `findings` brief and limited to `clarification` / `optional` readability, pacing, or missing-context gaps you genuinely hit.""",
        "recheck_focus": """Re-read ONLY the revised manuscript + SI (zero code/overlays) as a busy adjacent-field skimmer on a first pass, re-populate `plain_english_reconstruction`, `walkout_point`, `friction_hotspots`, and `where_i_got_lost_or_bored`, and report whether prior math-wall, story-detour, or confusion drop-off points are now smoothly readable without guessing.""",
    },
]

# --- Lean Per-Reviewer Schemas ---

FINDING_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "priority": {"type": "string", "enum": ["essential", "clarification", "optional"]},
        "category": {"type": "string"},
        "location": {"type": "string"},
        "quote_or_evidence": {"type": "string"},
        "issue": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "author_question_or_placeholder": {"type": "string"},
        "safe_mechanical_edit": {"type": "string"},
    },
    "required": [
        "priority",
        "category",
        "location",
        "issue",
        "why_it_matters",
        "author_question_or_placeholder",
    ],
}

PRIOR_ISSUE_SCHEMA = {
    "type": "object",
    "properties": {
        "original_issue": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["Addressed", "Partially addressed", "Not addressed", "Unclear"],
        },
        "evidence_from_revision": {"type": "string"},
        "remaining_problem": {"type": "string"},
        "author_action_needed": {"type": "string"},
    },
    "required": [
        "original_issue",
        "status",
        "evidence_from_revision",
        "remaining_problem",
        "author_action_needed",
    ],
}

REMAINING_FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "is_new_in_revision": {"type": "boolean"},
        "priority": {"type": "string", "enum": ["essential", "clarification", "optional"]},
        "category": {"type": "string"},
        "location": {"type": "string"},
        "issue": {"type": "string"},
        "author_action_needed": {"type": "string"},
        "safe_mechanical_edit": {"type": "string"},
    },
    "required": [
        "is_new_in_revision",
        "priority",
        "category",
        "location",
        "issue",
        "author_action_needed",
    ],
}

NOVELTY_ASSESSMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "novelty_verdict": {
            "type": "string",
            "enum": [
                "CLEAR_NOVELTY_ABOVE_BAR",
                "BORDERLINE_NEEDS_SHARPER_DIFFERENTIATION",
                "OVERLAP_OR_INCREMENTAL_RISK",
                "not_applicable",
            ],
        },
        "target_venue_bar_analysis": {"type": "string"},
        "irreducible_new_idea": {"type": "string"},
        "contributions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "novelty_tier": {
                        "type": "string",
                        "enum": [
                            "new_math_or_algorithm",
                            "cross_domain_transfer",
                            "empirical_discovery",
                            "incremental_tweak",
                            "subsumed_or_overlap",
                        ],
                    },
                    "closest_prior_art": {"type": "string"},
                    "delta_and_risk": {"type": "string"},
                },
                "required": ["claim", "novelty_tier", "closest_prior_art", "delta_and_risk"],
            },
        },
        "missing_or_overlapping_prior_art": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "novelty_verdict",
        "target_venue_bar_analysis",
        "irreducible_new_idea",
        "contributions",
    ],
}

COMPRESSION_LEDGER_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["cut", "merge_squeeze", "demote_main_to_si", "archive_si_to_repo"],
            },
            "execution_tier": {
                "type": "string",
                "enum": ["tier1_prose_only", "tier2_table_or_script_refactor", "tier3_author_policy"],
            },
            "scope": {"type": "string", "enum": ["main_text", "si", "main_and_si"]},
            "location": {"type": "string"},
            "target_description": {"type": "string"},
            "rationale": {"type": "string"},
            "estimated_savings": {"type": "string"},
            "replacement_pointer": {"type": "string"},
            "archive_artifact_status": {
                "type": "string",
                "enum": ["exists_on_disk", "must_generate_before_cutting", "not_applicable"],
            },
            "source_script_to_update": {"type": "string"},
            "preserves_reproducibility": {"type": "boolean"},
            "preserves_stage1_2a_claims": {"type": "boolean"},
            "risk_level": {"type": "string", "enum": ["zero", "low", "needs_author_decision"]},
        },
        "required": [
            "action",
            "execution_tier",
            "scope",
            "location",
            "target_description",
            "rationale",
            "estimated_savings",
            "archive_artifact_status",
            "preserves_reproducibility",
            "preserves_stage1_2a_claims",
            "risk_level",
        ],
    },
}

RESEARCH_QUESTIONS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "theme": {"type": "string"},
            "question": {"type": "string"},
            "why_it_matters": {"type": "string"},
            "suggested_experiment_or_derivation": {"type": "string"},
        },
        "required": ["theme", "question", "why_it_matters", "suggested_experiment_or_derivation"],
    },
}


READER_RECONSTRUCTION_SCHEMA = {
    "type": "object",
    "properties": {
        "problem": {"type": "string"},
        "prior_work_vs_new_delta_from_abstract": {"type": "string"},
        "method_steps": {"type": "string"},
        "headline_result_and_baseline": {"type": "string"},
        "main_limitation": {"type": "string"},
    },
    "required": [
        "problem",
        "prior_work_vs_new_delta_from_abstract",
        "method_steps",
        "headline_result_and_baseline",
        "main_limitation",
    ],
}

READER_WALKOUT_SCHEMA = {
    "type": "object",
    "properties": {
        "location": {"type": "string"},
        "trigger": {"type": "string"},
        "why_reader_stops_linear_reading": {"type": "string"},
    },
    "required": ["location", "trigger", "why_reader_stops_linear_reading"],
}

READER_FRICTION_HOTSPOTS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "location": {"type": "string"},
            "friction_type": {
                "type": "string",
                "enum": [
                    "math_wall_no_intuition",
                    "story_detour",
                    "working_memory_overload",
                    "prose_breaks_if_math_skipped",
                    "pacing_drag",
                ],
            },
            "quote_or_cue": {"type": "string"},
            "why_it_breaks_flow": {"type": "string"},
            "suggested_story_fix": {"type": "string"},
        },
        "required": ["location", "friction_type", "quote_or_cue", "why_it_breaks_flow", "suggested_story_fix"],
    },
}

READER_PASS1_SCHEMA = {
    "type": "object",
    "properties": {
        "main_only_summary": {"type": "string"},
        "plain_english_reconstruction": READER_RECONSTRUCTION_SCHEMA,
        "walkout_point": READER_WALKOUT_SCHEMA,
        "unresolved_main_gaps_and_si_jumps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "missing_or_deferred_item": {"type": "string"},
                    "breaks_main_story": {"type": "boolean"},
                },
                "required": ["location", "missing_or_deferred_item", "breaks_main_story"],
            },
        },
        "friction_hotspots": READER_FRICTION_HOTSPOTS_SCHEMA,
    },
    "required": [
        "main_only_summary",
        "plain_english_reconstruction",
        "walkout_point",
        "unresolved_main_gaps_and_si_jumps",
        "friction_hotspots",
    ],
}

READER_TWO_PASS_SI_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "pass1_gaps_resolved_by_si": {"type": "array", "items": {"type": "string"}},
        "pass1_gaps_still_missing": {"type": "array", "items": {"type": "string"}},
        "essential_story_buried_in_si": {"type": "array", "items": {"type": "string"}},
        "main_si_flipping_verdict": {"type": "string"},
    },
    "required": [
        "pass1_gaps_resolved_by_si",
        "pass1_gaps_still_missing",
        "essential_story_buried_in_si",
        "main_si_flipping_verdict",
    ],
}


def build_schema(reviewer_id: str, run_mode: str, reader_two_pass: bool = False):
    """Build a lean per-reviewer JSON schema containing only role-relevant fields."""
    if run_mode == "review":
        props = {
            "reviewer_id": {"type": "string"},
            "reviewer_role": {"type": "string"},
            "summary": {"type": "string"},
            "findings": {"type": "array", "items": FINDING_ITEM_SCHEMA},
        }
        req = ["reviewer_id", "reviewer_role", "summary", "findings"]
    else:
        props = {
            "reviewer_id": {"type": "string"},
            "reviewer_role": {"type": "string"},
            "domain_verdict": {
                "type": "string",
                "enum": [
                    "ready_to_share",
                    "almost_ready_minor_clarifications",
                    "not_ready_important_info_missing",
                    "not_ready_major_gaps_remain",
                ],
            },
            "p0_p1_count": {"type": "integer", "minimum": 0},
            "summary": {"type": "string"},
            "prior_issue_assessments": {"type": "array", "items": PRIOR_ISSUE_SCHEMA},
            "remaining_or_new_findings": {"type": "array", "items": REMAINING_FINDING_SCHEMA},
        }
        req = [
            "reviewer_id",
            "reviewer_role",
            "domain_verdict",
            "p0_p1_count",
            "summary",
            "prior_issue_assessments",
            "remaining_or_new_findings",
        ]

    if reviewer_id == "structure_narrative":
        props["structural_blueprint"] = {
            "type": "object",
            "properties": {
                "central_question_to_put_first": {"type": "string"},
                "section_reordering_steps": {"type": "array", "items": {"type": "string"}},
                "specimen_openings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target_section": {"type": "string"},
                            "proposed_opening": {"type": "string"},
                            "grounded_in_draft_evidence": {"type": "string"},
                        },
                        "required": ["target_section", "proposed_opening", "grounded_in_draft_evidence"],
                    },
                },
            },
            "required": ["central_question_to_put_first", "section_reordering_steps"],
        }
    elif reviewer_id == "code_math_auditor":
        props["stage0_verdict"] = {
            "type": "string",
            "enum": ["ALIGNED_FAIL_LOUD", "SILENT_POLLUTION_RISK"],
        }
        props["p0_p1_count"] = {"type": "integer", "minimum": 0}
        props["stage0_closed"] = {"type": "boolean"}
        props["execution_status"] = {
            "type": "string",
            "enum": ["executed_passed", "executed_failed", "blocked_by_permission", "no_runnable_targets"],
        }
        props["execution_summary"] = {"type": "string"}
        for k in ("stage0_verdict", "p0_p1_count", "stage0_closed", "execution_status"):
            if k not in req:
                req.append(k)
    elif reviewer_id == "baseline_killer":
        props["baseline_verdict"] = {
            "type": "string",
            "enum": [
                "SOLID_BASELINE",
                "MECHANISM_SOLID_PARITY_FIX_NEEDED",
                "REPAIR_RISK_PILOT_REQUIRED",
                "HANDICAPPED_BASELINE_RERUN_REQUIRED",
            ],
        }
        props["p0_count"] = {"type": "integer", "minimum": 0}
        props["p0_p1_count"] = {"type": "integer", "minimum": 0}
        props["stage1a_closed"] = {"type": "boolean"}
        for k in ("baseline_verdict", "p0_p1_count", "stage1a_closed"):
            if k not in req:
                req.append(k)
    elif reviewer_id == "theory_mechanism_critic":
        props["research_development_questions"] = RESEARCH_QUESTIONS_SCHEMA
    elif reviewer_id == "supervisor_strategist":
        props["live_search_status"] = {
            "type": "string",
            "enum": ["searched_live", "used_supplied_brief", "blocked_or_offline"],
        }
        props["novelty_assessment"] = NOVELTY_ASSESSMENT_SCHEMA
        props["cross_field_connections"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_or_method": {"type": "string"},
                    "connection": {"type": "string"},
                    "potential_payoff": {"type": "string"},
                },
                "required": ["field_or_method", "connection", "potential_payoff"],
            },
        }
        props["referee2_fatal_objection"] = {"type": "string"}
        props["candidate_pivots"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pivot_title": {"type": "string"},
                    "core_twist": {"type": "string"},
                    "theorem_or_experiment_hook": {"type": "string"},
                },
                "required": ["pivot_title", "core_twist", "theorem_or_experiment_hook"],
            },
        }
        props["research_development_questions"] = RESEARCH_QUESTIONS_SCHEMA
        for k in ("live_search_status", "novelty_assessment"):
            if k not in req:
                req.append(k)
    elif reviewer_id == "reproducibility_code":
        props["reproducibility_rating"] = {
            "type": "string",
            "enum": ["sufficient", "mostly_sufficient_minor_gaps", "insufficient", "not_applicable"],
        }
        if "reproducibility_rating" not in req:
            req.append("reproducibility_rating")
    elif reviewer_id == "claims_definitions":
        if run_mode == "review":
            props["understated_conclusions"] = {"type": "array", "items": {"type": "string"}}
            props["possible_additional_conclusions"] = {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "possibility": {"type": "string"},
                        "needed_to_confirm": {"type": "string"},
                    },
                    "required": ["possibility", "needed_to_confirm"],
                },
            }
        else:
            props["conclusion_support_assessments"] = {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "conclusion": {"type": "string"},
                        "supporting_data": {"type": "string"},
                        "support_level": {"type": "string", "enum": ["strong", "moderate", "weak", "absent"]},
                        "recommendation": {"type": "string"},
                    },
                    "required": ["conclusion", "supporting_data", "support_level", "recommendation"],
                },
            }
            if "conclusion_support_assessments" not in req:
                req.append("conclusion_support_assessments")
    elif reviewer_id == "conciseness_editor":
        props["compression_ledger"] = COMPRESSION_LEDGER_SCHEMA
        if "compression_ledger" not in req:
            req.append("compression_ledger")
    elif reviewer_id == "average_reader":
        props["plain_english_reconstruction"] = READER_RECONSTRUCTION_SCHEMA
        props["walkout_point"] = READER_WALKOUT_SCHEMA
        props["friction_hotspots"] = READER_FRICTION_HOTSPOTS_SCHEMA
        props["where_i_got_lost_or_bored"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "confusion_or_guess": {"type": "string"},
                    "what_is_missing": {"type": "string"},
                },
                "required": ["location", "confusion_or_guess", "what_is_missing"],
            },
        }
        for k in ("plain_english_reconstruction", "walkout_point", "friction_hotspots", "where_i_got_lost_or_bored"):
            if k not in req:
                req.append(k)
        if reader_two_pass:
            props["two_pass_si_audit"] = READER_TWO_PASS_SI_AUDIT_SCHEMA
            if "two_pass_si_audit" not in req:
                req.append("two_pass_si_audit")

    return {"type": "object", "properties": props, "required": req}


PIVOT_RED_TEAM_SCHEMA = {
    "type": "object",
    "properties": {
        "live_search_status": {
            "type": "string",
            "enum": ["searched_live", "used_supplied_brief", "skipped_all_dropped", "blocked_or_offline"],
        },
        "summary": {"type": "string"},
        "pivot_audit": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pivot_title": {"type": "string"},
                    "strongest_cheap_baseline": {"type": "string"},
                    "primary_math_or_scaling_trap": {"type": "string"},
                    "pivot_verdict": {
                        "type": "string",
                        "enum": ["SURVIVES_RED_TEAM", "VIABLE_WITH_PATCH", "NEEDS_FRESH_SCREEN", "DROP_PIVOT"],
                    },
                    "one_line_patch": {"type": "string"},
                },
                "required": [
                    "pivot_title",
                    "strongest_cheap_baseline",
                    "primary_math_or_scaling_trap",
                    "pivot_verdict",
                    "one_line_patch",
                ],
            },
        },
        "design_space_constraints": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["live_search_status", "summary", "pivot_audit", "design_space_constraints"],
}


# --- Select Active Reviewers & Run 0-Token Pre-Flight Diagnostics ---

if selected_ids:
    effective_ids = selected_ids
else:
    effective_ids = [
        rid for rid in STAGE_DEFAULT_REVIEWERS[stage]
        if not (mode == "recheck" and rid in ADVISORY_REVIEWERS)
    ]
wanted = set(effective_ids)
active_reviewers = [r for r in REVIEWERS if r["id"] in wanted]
if not active_reviewers:
    valid = [r["id"] for r in REVIEWERS]
    raise ValueError(f"No matching reviewers in {effective_ids}. Valid IDs: {valid}")

lint_report = None
if not skip_lint and LINTER_MOD is not None and (report_paths or extra_files):
    lint_report = LINTER_MOD.run_preflight_lint(report_paths + extra_files, base_dir=str(Path.cwd()))
    log(f"0-token pre-flight linter scanned {lint_report.get('files_scanned', 0)} file(s).")

diff_text, diff_warnings = (
    _extract_diff_text(diff_file, git_ref, report_paths + extra_files) if mode == "recheck" else ("", [])
)
for w in diff_warnings:
    log(f"DIFF WARNING: {w}")


RE_SI_FILENAME = re.compile(
    r"(?:^|[\W_])(si|supp|supplement|supplementary|appendix|appendices|sm)(?:[\W_]|$)",
    re.IGNORECASE,
)


def _split_main_and_si(paths):
    """Split >=2 report files into (main_paths, si_paths) for no-lookahead Pass 1 vs. Pass 2."""
    if len(paths) < 2:
        return list(paths), []
    main_list, si_list = [], []
    for p in paths:
        stem = Path(p).stem
        if RE_SI_FILENAME.search(stem):
            si_list.append(p)
        else:
            main_list.append(p)
    if main_list and si_list:
        return main_list, si_list
    return [paths[0]], list(paths[1:])


def _resolve_reader_two_pass(arg_val, active_revs, run_mode: str, reader_paths_eff):
    if run_mode != "review" or not any(r["id"] == "average_reader" for r in active_revs):
        return False, [], []
    if arg_val is False or (isinstance(arg_val, str) and arg_val.strip().lower() in ("false", "0", "no")):
        return False, [], []
    if len(reader_paths_eff) < 2:
        return False, [], []
    main_p, si_p = _split_main_and_si(reader_paths_eff)
    return bool(main_p and si_p), main_p, si_p


effective_reader_paths = reader_report_paths if reader_report_paths else report_paths
reader_two_pass_active, reader_main_paths, reader_si_paths = _resolve_reader_two_pass(
    reader_two_pass_arg, active_reviewers, mode, effective_reader_paths
)


def build_inputs_block(reviewer_id: str, report_paths_override=None):
    lines = [
        f"Research domain: {domain}",
        f"Document type: {doc_type}",
        f"Review stage: {stage} ({mode} mode)",
    ]
    if target_venue:
        lines.append(f"Target venue / agency: {target_venue}")
    if prior_art_summary and reviewer_id in ("supervisor_strategist", "theory_mechanism_critic"):
        lines.append(
            "Supplied live web/arXiv prior-art brief "
            "(if file path, read it; otherwise treat as text — never invent citations):\n"
            + prior_art_summary
        )
    if length_budget and reviewer_id == "conciseness_editor":
        lines.append(f"Target length / table / figure budget: {length_budget}")
    if protected_requirements and reviewer_id == "conciseness_editor":
        lines.append(
            "Protected Stage 1 / Stage 2A requirements "
            "(if file path, read it; NEVER cut these — only compress, demote Main->SI, or archive SI->Repo):\n"
            + protected_requirements
        )
    if voice_samples and reviewer_id == "grammar_humanizer":
        lines.append("Author writing sample(s) for voice matching:")
        for p in voice_samples:
            lines.append(f"  - {p}")
    if context:
        lines.append(f"Additional user context: {context}")
    if ACTIVE_OVERLAY_MD and reviewer_id in (
        "code_math_auditor",
        "baseline_killer",
        "theory_mechanism_critic",
        "supervisor_strategist",
        "structure_narrative",
        "reproducibility_code",
        "figures_refs_format",
        "conciseness_editor",
    ):
        lines.append("Optional local lab/domain overlay priors:\n---\n" + ACTIVE_OVERLAY_MD + "\n---")

    if report_paths_override is not None:
        active_report_paths = list(report_paths_override)
    else:
        active_report_paths = (
            reader_report_paths
            if (reviewer_id == "average_reader" and reader_report_paths)
            else report_paths
        )
    if mode == "review":
        if active_report_paths:
            lines.append("Target report/spec file(s) to read completely:")
            for p in active_report_paths:
                lines.append(f"  - {p}")
        if report_text and not (reviewer_id == "average_reader" and (reader_report_paths or report_paths_override is not None)):
            lines.append("Target report text:\n---\n" + report_text + "\n---")
    else:
        if previous_review:
            lines.append(
                "Previous review for this stage (if file path, read it; otherwise treat as full text):\n"
                + previous_review
            )
        if diff_text:
            lines.append(
                "DIFF-SCOPED RECHECK — Unified diff of changes since prior pass "
                "(focus on prior open P0/P1 issues + these changed lines; read full revised file ONLY as needed for context):\n"
                "```diff\n" + diff_text + "\n```"
            )
        else:
            if original_paths:
                lines.append("Original report file(s):")
                for p in original_paths:
                    lines.append(f"  - {p}")
            if original_text:
                lines.append("Original report text:\n---\n" + original_text + "\n---")
        if active_report_paths:
            lines.append("REVISED report file(s):")
            for p in active_report_paths:
                lines.append(f"  - {p}")
        if report_text and not (reviewer_id == "average_reader" and reader_report_paths):
            lines.append("REVISED report text:\n---\n" + report_text + "\n---")

    if extra_files and reviewer_id != "average_reader":
        lines.append("Auxiliary files available for inspection (code, configs, tests, .bib, figures, SI):")
        for p in extra_files:
            lines.append(f"  - {p}")

    if lint_report is not None and LINTER_MOD is not None and reviewer_id != "average_reader":
        scoped_lint = LINTER_MOD.format_lint_for_reviewer(lint_report, reviewer_id)
        if scoped_lint:
            lines.append("\n" + scoped_lint)

    return "\n".join(lines)


def build_prompt(reviewer):
    rid = reviewer["id"]
    focus = reviewer["review_focus"] if mode == "review" else reviewer["recheck_focus"]
    stage_label = STAGE_DESCRIPTIONS[stage]
    mode_label = "INITIAL AUDIT" if mode == "review" else "DIFF/REVISION RE-CHECK"
    extra = ("\n\n" + RECHECK_EXTRA_RULES) if mode == "recheck" else ""
    read_hint = (
        "- Read ONLY the compiled manuscript / SI PDF(s) (or document(s)) provided above like a busy first-time reader (including figures and tables).\n"
        if rid == "average_reader"
        else "- Read the target document(s) (and relevant auxiliary code/files) before forming judgments.\n"
    )
    return (
        f"You are {reviewer['role']} (reviewer_id='{rid}').\n"
        f"Task: Perform an independent blind {stage_label} — {mode_label}.\n\n"
        f"{build_inputs_block(rid)}\n\n"
        f"{GROUND_RULES}{extra}\n\n"
        f"YOUR SPECIFIC REVIEW SCOPE:\n{focus}\n\n"
        "Instructions:\n"
        f"{read_hint}"
        "- Stay strictly rigorous, evidence-based, and thorough within your scope.\n"
        "- Return your complete structured critique via the finish tool matching the required JSON schema.\n"
        f"- Set reviewer_id='{rid}' and reviewer_role='{reviewer['role']}'."
    )


def build_reader_pass1_prompt(reviewer, main_paths):
    rid = reviewer["id"]
    return (
        f"You are {reviewer['role']} — PASS 1/2 (MAIN TEXT ONLY, ZERO SI LOOKAHEAD) (reviewer_id='{rid}').\n"
        "Task: Simulate an impatient adjacent-field scientist reading ONLY the Main manuscript on a Friday afternoon with 15 minutes.\n"
        "STRICT BLINDING RULE: Supplementary / Appendix files are intentionally withheld in Pass 1. Do NOT search for or open any other files in the workspace — read ONLY the Main file(s) listed below.\n\n"
        f"{build_inputs_block(rid, report_paths_override=main_paths)}\n\n"
        f"{GROUND_RULES}\n\n"
        "PASS 1 AUDIT SCOPE (MAIN TEXT SELF-CONTAINMENT & STORYFLOW):\n"
        "1. PLAIN-ENGLISH TEACH-BACK (`plain_english_reconstruction`): From Main Text alone, restate problem, Abstract prior-work-vs-new delta, method steps, headline result + baseline, and main limitation. State plainly wherever you had to guess.\n"
        "2. SKIP-THE-EQUATIONS FRICTION HOTSPOTS (`friction_hotspots`): Pretend every multi-line display equation is blurred out. Rank the top 3-5 highest-friction passages in Main (worst-first) tagged by `math_wall_no_intuition`, `story_detour`, `working_memory_overload`, `prose_breaks_if_math_skipped`, or `pacing_drag`.\n"
        "3. FORCED WALKOUT POINT (`walkout_point`): Name the single paragraph/subsection in Main where an impatient reader stops linear reading and jumps to Figures/Conclusions (or closes the PDF), and why.\n"
        "4. UNRESOLVED MAIN GAPS & SI JUMPS (`unresolved_main_gaps_and_si_jumps`): List every forward jump to SI/Appendix or undefined symbol/detail that breaks or stalls Main-text comprehension (`breaks_main_story=true/false`).\n"
        "Return your structured JSON via `finish`."
    )


def build_reader_pass2_prompt(reviewer, all_paths, pass1_result):
    rid = reviewer["id"]
    stage_label = STAGE_DESCRIPTIONS[stage]
    pass1_json = json.dumps(pass1_result, indent=2)[:8000]
    return (
        f"You are {reviewer['role']} — PASS 2/2 (MAIN + SI FOLLOW-UP CHECK) (reviewer_id='{rid}').\n"
        f"Task: Complete the second pass of the blind {stage_label} average-reader audit by inspecting BOTH Main and SI.\n\n"
        f"{build_inputs_block(rid, report_paths_override=all_paths)}\n\n"
        "FROZEN PASS 1 (MAIN-ONLY, ZERO-SI-LOOKAHEAD) READER NOTES:\n"
        f"```json\n{pass1_json}\n```\n\n"
        f"{GROUND_RULES}\n\n"
        f"YOUR SPECIFIC REVIEW SCOPE:\n{reviewer['review_focus']}\n\n"
        "ADDITIONAL PASS 2 REQUIREMENT (`two_pass_si_audit`):\n"
        "- Cross-check EVERY item in Pass 1's `unresolved_main_gaps_and_si_jumps` against the SI now available: record which gaps SI genuinely resolved (`pass1_gaps_resolved_by_si`), which remain missing even in SI (`pass1_gaps_still_missing`), which core storyline steps are buried in SI instead of Main (`essential_story_buried_in_si`), and give an honest 1-2 sentence `main_si_flipping_verdict` on whether reading Main required painful back-and-forth SI lookups.\n"
        "- Keep Pass 1's genuine Main-text friction/walkout issues visible — do NOT erase Main-text math walls just because SI explains them.\n"
        "- Return your complete structured critique via the finish tool matching the required JSON schema.\n"
        f"- Set reviewer_id='{rid}' and reviewer_role='{reviewer['role']}'."
    )


# --- Execute Blind Parallel Panel ---

stage_label_short = STAGE_PHASE_LABELS[stage]
mode_suffix = "Revision Re-Check" if mode == "recheck" else "Audit"
iter_suffix = f" [Round {iteration}/{MAX_STAGE1A_ITERATIONS}]" if stage == "stage1a" else ""
phase_title = (
    f"{stage_label_short} {mode_suffix}{iter_suffix} "
    f"({len(active_reviewers)} Blind Reviewer{'s' if len(active_reviewers) != 1 else ''})"
)

phase(phase_title)
routed = [f"{r['id']}[{resolve_agent_type(r['id'])}/{resolve_model(r['id'])}]" for r in active_reviewers]
log(
    f"Launching {len(active_reviewers)} isolated reviewer(s) for {stage} ({mode}{iter_suffix}; "
    f"overlay_cfg={LOCAL_CFG_SOURCE or 'none'}, overlay_md={LOCAL_OVERLAY_SOURCE or 'none'}, "
    f"overlay_applied={OVERLAY_APPLIED}"
    + (f"[{OVERLAY_SKIP_REASON}]" if OVERLAY_SKIP_REASON else "")
    + (f", reader_two_pass=True[main={len(reader_main_paths)},si={len(reader_si_paths)}]" if reader_two_pass_active else "")
    + "): "
    + ", ".join(routed)
)


async def _run_reviewer(r):
    rid = r["id"]
    if rid == "average_reader" and reader_two_pass_active:
        pass1_res = await agent(
            prompt=build_reader_pass1_prompt(r, reader_main_paths),
            schema=READER_PASS1_SCHEMA,
            role="Reviewer 11 (Pass 1/2): Blind Average Reader — Main Only",
            type_name=resolve_agent_type(rid),
            model=resolve_model(rid),
        )
        pass2_res = await agent(
            prompt=build_reader_pass2_prompt(r, effective_reader_paths, pass1_res),
            schema=build_schema(rid, mode, reader_two_pass=True),
            role="Reviewer 11 (Pass 2/2): Blind Average Reader — Main + SI Check",
            type_name=resolve_agent_type(rid),
            model=resolve_model(rid),
        )
        if isinstance(pass2_res, dict):
            pass2_res["pass1_main_only"] = pass1_res
        return pass2_res
    return await agent(
        prompt=build_prompt(r),
        schema=build_schema(rid, mode),
        role=r["role"],
        type_name=resolve_agent_type(rid),
        model=resolve_model(rid),
    )


reviews = await parallel(active_reviewers, _run_reviewer)

log(f"Completed {len(reviews)} independent review(s) for {stage} ({mode}{iter_suffix}).")

# --- Bounded 1-Round Blind Pivot Red-Team Mini-Pass (Stage 1 / Stage 1B) ---


def _extract_stage1_constraints(stage_reviews):
    """Distill compact baseline & theoretical constraints proved in Stage 1 (blind to Pivot rationale)."""
    lines = []
    for rev in stage_reviews:
        rid = rev.get("reviewer_id", "")
        if rid not in ("baseline_killer", "theory_mechanism_critic"):
            continue
        if rev.get("summary"):
            lines.append(f"- [{rid} summary]: {str(rev['summary'])[:800]}")
        for item in rev.get("findings", [])[:10]:
            if item.get("priority") in ("essential", "clarification"):
                loc = item.get("location", "")
                lines.append(f"- [{rid} {item.get('priority')}] ({loc}) {item.get('issue', '')}")
    return "\n".join(lines) if lines else "- None extracted from Stage 1 reviewers."


def _format_stage1_pivots(raw_pivots):
    formatted = []
    for i, p in enumerate(raw_pivots, 1):
        if isinstance(p, dict):
            title = str(p.get("pivot_title") or p.get("title") or f"Pivot {i}")
            twist = str(p.get("core_twist") or p.get("description") or "")
            hook = str(p.get("theorem_or_experiment_hook") or "")
            formatted.append(f"{i}. {title}\n   Mechanism/Twist: {twist}\n   Hook: {hook}")
        else:
            formatted.append(f"{i}. {str(p)}")
    return "\n".join(formatted)


def _build_stage1_pivot_red_team_prompt(pivots_block: str, constraints_block: str, prt_agent_type: str):
    file_lines = []
    if report_paths:
        file_lines.append("Report file(s): " + ", ".join(report_paths))
    if extra_files:
        file_lines.append("Auxiliary/code file(s): " + ", ".join(extra_files))
    files_ctx = ("\n".join(file_lines) + "\n") if file_lines else ""
    brief_ctx = (
        "Supplied prior-art brief (if file path, read it; otherwise treat as text — never invent citations):\n"
        + prior_art_summary
        + "\n\n"
        if prior_art_summary
        else ""
    )
    if prt_agent_type == "research":
        search_block = (
            f"OFFLINE PRIOR-ART AUDIT (READ-ONLY `research` SANDBOX — NO `search_web`, NO FILE EDITS, NO SHELL): "
            f"Audit prior-art overlap ({STAGE1B_SEARCH_WINDOW}) strictly using the supplied prior-art brief and "
            "attached bibliography/files. NEVER report `searched_live`; set `live_search_status` to "
            "`used_supplied_brief` (when auditing against the supplied brief), `skipped_all_dropped` (when all Pivots "
            "fail math/baseline triage), or `blocked_or_offline` (when no prior-art brief is supplied and live search is "
            f"required). Cite only verified IDs/URLs.{CUTOFF_DIRECTIVE}\n\n"
        )
    else:
        search_block = (
            f"LIVE SEARCH (READ-ONLY — `search_web` ONLY, NO FILE EDITS, NO SHELL): Run 1-2 targeted `search_web` "
            f"queries ({STAGE1B_SEARCH_WINDOW}) per Pivot that passes initial math/baseline triage to check prior-art "
            "overlap in the Pivot's OWN target subfield (also honoring any supplied prior-art brief; skip search for "
            "obvious `DROP_PIVOT`s; set `live_search_status` to `searched_live`, `used_supplied_brief`, "
            f"`skipped_all_dropped`, or `blocked_or_offline`; cite only verified IDs/URLs).{CUTOFF_DIRECTIVE}\n\n"
        )
    return (
        "You are the Stage 1 Blind Pivot Red-Team Auditor (1-round bounded check).\n"
        "Mission: Adversarially audit EVERY candidate Pivot/reframing proposed in Stage 1 BEFORE it is "
        "recommended. Kill any Pivot that falls to a cheap baseline (minimal patch, library call, or simple <=~50-line textbook baseline), is already scooped in "
        "its own subfield, or contradicts theoretical, algebraic, statistical, scaling, or conservation "
        "constraints established below. Returning 0 survivors (all `DROP_PIVOT`) is completely valid and "
        "expected when all Pivots fail — never force a survivor or rescue a dead algorithm as a generic "
        "'benchmark/phase-diagram' study unless prior-art search proves no existing critique subsumes it.\n"
        + search_block
        + f"Research domain: {domain}\n"
        + (f"Target venue: {target_venue}\n" if target_venue else "")
        + files_ctx
        + brief_ctx
        + f"\nDERIVED CONSTRAINTS FROM STAGE 1 (check every Pivot for self-contradiction against these):\n"
        f"{constraints_block}\n\n"
        f"CANDIDATE PIVOTS TO AUDIT:\n{pivots_block}\n\n"
        f"{GROUND_RULES}\n\n"
        "REQUIRED AUDIT ROW FOR EVERY CANDIDATE PIVOT (populate `pivot_audit` with exact matching `pivot_title`):\n"
        "1. `strongest_cheap_baseline`: Strongest cheap baseline — minimal patch (~5-20 lines), off-the-shelf library call, simple <=~50-line textbook baseline (e.g., CRN, control variates, "
        "sorting, warm-start, standard iterative heuristic), or tightest known theorem/reduction that could kill or shrink this Pivot.\n"
        "2. `primary_math_or_scaling_trap`: Sharpest math, statistical, self-consistency, or prior-art overlap trap.\n"
        "3. `pivot_verdict`: Strictly one of:\n"
        "   - `SURVIVES_RED_TEAM` (unchanged mechanism passes prior-art check, cheap baseline, and Stage 1 constraints)\n"
        "   - `VIABLE_WITH_PATCH` (STRICTLY a single-sentence scope/parameter trim introducing ZERO new math objects, estimators, or domains, and passing prior-art check)\n"
        "   - `NEEDS_FRESH_SCREEN` (salvaging requires a new mechanism, domain switch, or >=2 bundled fixes — unvetted; must undergo a fresh blind Stage 1 / Day-0 screen before coding)\n"
        "   - `DROP_PIVOT` (killed by cheap baseline, prior-art scoop, or Stage 1 constraints)\n"
        "4. `one_line_patch`: Single-sentence trim for `VIABLE_WITH_PATCH`, brief unvetted direction for `NEEDS_FRESH_SCREEN`, or `'N/A'` for `SURVIVES_RED_TEAM`/`DROP_PIVOT`.\n"
        "5. `design_space_constraints`: Populate with 3-4 concise necessary conditions ONLY when 0 Pivots earn `SURVIVES_RED_TEAM` or `VIABLE_WITH_PATCH` (otherwise `[]`) — strictly inverted from Stage 1/Phase 2 findings without pitching an unvetted 4th Pivot: (a) baseline floor to beat, (b) non-negotiable math/scaling/validity invariants, (c) verified open literature window, and (d) 1-line whiteboard litmus check. Keep tone colleague-safe and constructive toward the design space while staying 100% strict on verdicts.\n"
        "Return your structured JSON via `finish`."
    )


def _enforce_offline_search_status(payload, resolved_type: str, has_brief: bool, label: str):
    """Fail-closed guard: offline `research` sandboxes cannot self-report `searched_live`."""
    if not isinstance(payload, dict) or resolved_type != "research":
        return
    if payload.get("live_search_status") == "searched_live":
        corrected = "used_supplied_brief" if has_brief else "blocked_or_offline"
        payload["live_search_status"] = corrected
        log(
            f"SEARCH_STATUS_GUARD: {label} ran in offline 'research' sandbox without search_web; "
            f"overrode invalid 'searched_live' -> '{corrected}'."
        )


for rev in reviews:
    if rev.get("reviewer_id") == "supervisor_strategist":
        _enforce_offline_search_status(
            rev, resolve_agent_type("supervisor_strategist"), bool(prior_art_summary), "supervisor_strategist"
        )

pivot_red_team = None
if stage in ("stage1", "stage1b") and mode == "review" and not skip_pivot_red_team:
    r9 = next((rev for rev in reviews if rev.get("reviewer_id") == "supervisor_strategist"), {})
    raw_stage1_pivots = explicit_pivots if explicit_pivots is not None else r9.get("candidate_pivots", [])
    if raw_stage1_pivots:
        phase(f"Stage 1 Pivot Red-Team Mini-Pass ({len(raw_stage1_pivots)} Candidate Pivot(s))")
        constraints_block = _extract_stage1_constraints(reviews)
        pivots_block = _format_stage1_pivots(raw_stage1_pivots)
        prt_agent_type = "self" if agent_type_override in ("", "auto") else agent_type_override
        mode_desc = (
            "with supplied prior-art brief (offline)"
            if (prt_agent_type == "research" and prior_art_summary)
            else ("in offline sandbox" if prt_agent_type == "research" else "with live search")
        )
        log(f"Red-teaming {len(raw_stage1_pivots)} Stage 1 candidate pivot(s) in isolated context {mode_desc}.")
        pivot_red_team = await agent(
            prompt=_build_stage1_pivot_red_team_prompt(pivots_block, constraints_block, prt_agent_type),
            schema=PIVOT_RED_TEAM_SCHEMA,
            role="Stage 1 Pivot Red-Team Auditor (1-Round)",
            type_name=prt_agent_type,
            model=model,
        )
        _enforce_offline_search_status(
            pivot_red_team, prt_agent_type, bool(prior_art_summary), "pivot_red_team"
        )
        log(f"Completed Stage 1 Pivot Red-Team ({len(pivot_red_team.get('pivot_audit', []))} row(s)).")

# --- Gate Summaries (Fail-Closed) ---

def _find_reviewer(rev_list, target_id):
    return next((rev for rev in rev_list if rev.get("reviewer_id") == target_id), None)

items_key = "findings" if mode == "review" else "remaining_or_new_findings"

stage0_gate = None
r0 = _find_reviewer(reviews, "code_math_auditor")
if r0 is not None:
    s0_verdict = r0.get("stage0_verdict", "SILENT_POLLUTION_RISK")
    s0_items = r0.get(items_key, [])
    s0_p0_p1 = (
        r0["p0_p1_count"]
        if isinstance(r0.get("p0_p1_count"), int)
        else sum(1 for item in s0_items if item.get("priority") == "essential")
    )
    exec_status = r0.get("execution_status", "no_runnable_targets")
    static_clean = (s0_p0_p1 == 0) and (s0_verdict == "ALIGNED_FAIL_LOUD")
    s0_closed = static_clean and (exec_status in ("executed_passed", "no_runnable_targets"))
    blocking_pointers = [
        f"{item.get('location', 'unknown')} — {item.get('issue', '')}"
        for item in s0_items
        if item.get("priority") == "essential"
    ]
    if static_clean and exec_status == "blocked_by_permission":
        s0_next = (
            "STATIC_ALIGNED_RUN_SMOKE_IN_MAIN — static audit passed with 0 P0/P1, but workflow shell "
            "execution was permission-blocked; Main Agent MUST run local <10 s --smoke & pytest before closing Stage 0."
        )
    elif s0_closed:
        s0_next = (
            "PROCEED_TO_HPC_OR_STAGE1A — ALIGNED_FAIL_LOUD with zero P0/P1 issues. "
            "Safe to submit HPC sweeps or advance to Stage 1A (Reviewer 7)."
        )
    else:
        s0_next = (
            f"BLOCK_AND_FIX_P0_P1 — SILENT_POLLUTION_RISK ({s0_p0_p1} P0/P1 issue(s), exec={exec_status}). "
            "Fix all branch/clip, fail-loud, symmetry/thread-lock/atomic-write, or test failures and re-run stage0."
        )
    stage0_gate = {
        "stage0_verdict": s0_verdict,
        "p0_p1_count": s0_p0_p1,
        "execution_status": exec_status,
        "stage0_closed": s0_closed,
        "blocking_pointers": blocking_pointers,
        "next_action": s0_next,
    }
    log(f"Stage 0 Gate: closed={s0_closed}, verdict={s0_verdict}, p0_p1={s0_p0_p1}, exec={exec_status}")

stage1a_gate = None
r7 = _find_reviewer(reviews, "baseline_killer")
if r7 is not None:
    verdict = r7.get("baseline_verdict", "REPAIR_RISK_PILOT_REQUIRED")
    p0_p1 = (
        r7["p0_p1_count"]
        if isinstance(r7.get("p0_p1_count"), int)
        else sum(1 for item in r7.get(items_key, []) if item.get("priority") == "essential")
    )
    p0_only = (
        r7["p0_count"]
        if isinstance(r7.get("p0_count"), int)
        else (0 if verdict in ("SOLID_BASELINE", "MECHANISM_SOLID_PARITY_FIX_NEEDED") else p0_p1)
    )
    # Fail-closed consistency: MECHANISM_SOLID_PARITY_FIX_NEEDED requires zero headline-threatening P0s
    if verdict == "MECHANISM_SOLID_PARITY_FIX_NEEDED" and p0_only > 0:
        log(
            f"STAGE1A_VERDICT_GUARD: R7 reported MECHANISM_SOLID_PARITY_FIX_NEEDED with p0_count={p0_only}; "
            "escalating to HANDICAPPED_BASELINE_RERUN_REQUIRED."
        )
        verdict = "HANDICAPPED_BASELINE_RERUN_REQUIRED"
    closed = (p0_p1 == 0) and (verdict == "SOLID_BASELINE")
    can_advance_to_stage1b = closed or (verdict == "MECHANISM_SOLID_PARITY_FIX_NEEDED" and p0_only == 0)
    if closed:
        next_action = "CLOSED — zero P0/P1 issues and SOLID_BASELINE. Stop Stage 1A early and proceed immediately to Stage 1B (Reviewers 8 & 9)."
    elif can_advance_to_stage1b:
        next_action = (
            f"ADVANCE_TO_STAGE1B_WITH_LOCAL_FIXES — core mechanism verified as Discovery (0 headline-threatening P0s, "
            f"{p0_p1} localized P1 parity/accounting/scope fix(es)). You may launch Stage 1B (R8 & R9) in parallel "
            f"and close Stage 1A via a quick diff-scoped recheck (iteration={iteration + 1}) before Stage 2."
        )
    elif stage == "stage1a" and iteration >= MAX_STAGE1A_ITERATIONS:
        next_action = (
            f"MAX_ITERATIONS_REACHED ({iteration}/{MAX_STAGE1A_ITERATIONS}) — do NOT auto-loop further; "
            "escalate remaining P0/P1 items to the user before proceeding."
        )
    else:
        next_action = (
            f"OPEN ({p0_only} P0 / {p0_p1} total P0+P1 issue(s) remaining) — fix code/baselines or run cheap baseline pilot, "
            f"then re-run stage1a in recheck mode with iteration={iteration + 1}."
        )
    stage1a_gate = {
        "iteration": iteration if stage == "stage1a" else 1,
        "max_iterations": MAX_STAGE1A_ITERATIONS,
        "baseline_verdict": verdict,
        "p0_count": p0_only,
        "p0_p1_count": p0_p1,
        "closed": closed,
        "can_advance_to_stage1b": can_advance_to_stage1b,
        "next_action": next_action,
    }
    log(
        f"Stage 1A Gate: closed={closed}, can_advance_to_stage1b={can_advance_to_stage1b}, "
        f"verdict={verdict}, p0={p0_only}, p0_p1={p0_p1} -> {next_action}"
    )

# Universal P0/P1 + verdict summary across all stages (advisory reviewers never auto-block)
total_p0_p1 = 0
for rev in reviews:
    if rev.get("reviewer_id") in ADVISORY_REVIEWERS:
        continue
    if isinstance(rev.get("p0_p1_count"), int):
        total_p0_p1 += rev["p0_p1_count"]
    else:
        total_p0_p1 += sum(1 for item in rev.get(items_key, []) if item.get("priority") == "essential")

blocking_reasons = []
if total_p0_p1 > 0:
    blocking_reasons.append(f"total_p0_p1_count={total_p0_p1}")
if stage0_gate and not stage0_gate["stage0_closed"]:
    blocking_reasons.append(f"stage0_open (verdict={stage0_gate['stage0_verdict']}, exec={stage0_gate['execution_status']})")
if stage1a_gate and not stage1a_gate["closed"]:
    blocking_reasons.append(f"stage1a_open (verdict={stage1a_gate['baseline_verdict']}, p0_p1={stage1a_gate['p0_p1_count']})")

r9_rev = _find_reviewer(reviews, "supervisor_strategist")
r9_search = r9_rev.get("live_search_status") if r9_rev else None
prt_search = pivot_red_team.get("live_search_status") if pivot_red_team else None
search_verification_required = (r9_search == "blocked_or_offline") or (prt_search == "blocked_or_offline")
if r9_rev:
    nov_v = (r9_rev.get("novelty_assessment") or {}).get("novelty_verdict")
    if nov_v == "OVERLAP_OR_INCREMENTAL_RISK":
        blocking_reasons.append("novelty_verdict=OVERLAP_OR_INCREMENTAL_RISK")
    if r9_search == "blocked_or_offline":
        blocking_reasons.append("r9_live_search=blocked_or_offline")
if prt_search == "blocked_or_offline":
    blocking_reasons.append("pivot_red_team_live_search=blocked_or_offline")

r2_rev = _find_reviewer(reviews, "reproducibility_code")
if r2_rev and r2_rev.get("reproducibility_rating") == "insufficient":
    blocking_reasons.append("reproducibility_rating=insufficient")

if mode == "recheck":
    for rev in reviews:
        if rev.get("reviewer_id") in ADVISORY_REVIEWERS:
            continue
        dv = rev.get("domain_verdict")
        if dv in ("not_ready_important_info_missing", "not_ready_major_gaps_remain"):
            blocking_reasons.append(f"{rev.get('reviewer_id', 'reviewer')}:{dv}")

pivot_rows = (pivot_red_team or {}).get("pivot_audit", [])
pivot_counts = (
    {
        "audited": len(pivot_rows),
        "survives_red_team": sum(1 for row in pivot_rows if row.get("pivot_verdict") == "SURVIVES_RED_TEAM"),
        "viable_with_patch": sum(1 for row in pivot_rows if row.get("pivot_verdict") == "VIABLE_WITH_PATCH"),
        "needs_fresh_screen": sum(1 for row in pivot_rows if row.get("pivot_verdict") == "NEEDS_FRESH_SCREEN"),
        "dropped": sum(1 for row in pivot_rows if row.get("pivot_verdict") == "DROP_PIVOT"),
    }
    if pivot_red_team is not None
    else None
)

stage_gate = {
    "stage": stage,
    "mode": mode,
    "diff_scoped": bool(diff_text),
    "diff_warnings": diff_warnings,
    "total_p0_p1_count": total_p0_p1,
    "search_verification_required": search_verification_required,
    "pivot_red_team_counts": pivot_counts,
    "blocking_reasons": blocking_reasons,
    "ready_to_advance": len(blocking_reasons) == 0,
}

output = {
    "stage": stage,
    "mode": mode,
    "iteration": iteration if stage == "stage1a" else None,
    "domain": domain,
    "cutoff_year": cutoff_year,
    "search_window": STAGE1B_SEARCH_WINDOW if stage in ("stage1", "stage1b") else None,
    "local_overlay_loaded": {
        "config": LOCAL_CFG_SOURCE,
        "markdown": LOCAL_OVERLAY_SOURCE,
        "applied": OVERLAY_APPLIED,
        "skipped_reason": OVERLAY_SKIP_REASON,
    },
    "report_paths": report_paths,
    "reviewer_count": len(reviews),
    "reviewers_run": [r["id"] for r in active_reviewers],
    "reviewer_agent_types": {r["id"]: resolve_agent_type(r["id"]) for r in active_reviewers},
    "reviewer_models": {r["id"]: resolve_model(r["id"]) for r in active_reviewers},
    "reader_two_pass_active": reader_two_pass_active,
    "preflight_lint_files_scanned": lint_report.get("files_scanned", 0) if lint_report else 0,
    "stage_gate": stage_gate,
    "stage0_gate": stage0_gate,
    "stage1a_gate": stage1a_gate,
    "pivot_red_team": pivot_red_team,
    "reviews": reviews,
}
print(json.dumps(output, indent=2))
