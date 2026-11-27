"""
Bounded, low-compute autonomous Generator + Falsification Loop (`idea-falsification-loop`).

Thin outer orchestrator over existing pre-compute verification skills — ZERO duplicated
rubrics or prompts. Dynamically executes verbatim:
  - `idea-novelty-screen/scripts/screen_idea.py` (3 blind scouts + 1-round Pivot Red-Team)
  - `scientific-report-review/scripts/review_panel.py` Stage 0 (`code-math-alignment`)
  - `scientific-report-review/scripts/review_panel.py` Stage 1A (`baseline-killer-audit`)

State Machine (for r = 1 .. max_rounds, default 3, hard cap <= 5):
  1. Propose (Generator): emits ONE concrete, falsifiable idea with explicit non-overlap
     against all GRAVEYARD entries and compliance with accumulated `design_space_constraints`.
  2. Screen (`screen_idea.py`):
     - `NEEDS_LIVE_SEARCH_VERIFICATION` (or offline live search on hard-novelty track) -> HALT (`BLOCKED_OFFLINE`).
     - Killed (`0/N` survivors) or only `NEEDS_FRESH_SCREEN` -> append to GRAVEYARD, advance to r + 1.
     - `PROCEED_TO_PROTOTYPE` or surviving `SURVIVES_RED_TEAM` / single-sentence `VIABLE_WITH_PATCH`:
       * `run_day1_pilot == False` -> STOP (`SURVIVOR_FOUND`).
       * `run_day1_pilot == True`  -> Step 3.
  3. Day-1 Falsification Pilot (`run_day1_pilot == True` only):
     - Hard compute ceiling: local CPU only, single-file toy script (<60 s, `--smoke` <10 s),
       no HPC/SLURM, no hyperparameter sweeps, no multi-seed tuning, matched vs. strongest
       cheap baseline (<=~50 lines or library call).
     - Stage 0 (`code-math-alignment`): MUST pass `ALIGNED_FAIL_LOUD`, `p0_p1_count == 0`,
       not `blocked_by_permission`.
     - Stage 1A (`baseline-killer-audit`): MUST pass `SOLID_BASELINE` or
       `MECHANISM_SOLID_PARITY_FIX_NEEDED` with `p0_count == 0`.
     - Any failure -> log to GRAVEYARD (no same-round patching), advance to r + 1.
     - Both pass -> STOP (`SURVIVOR_FOUND`).

Expected `Args` (dict passed via run_workflow):
    problem_space (str): Target scientific problem space or open bottleneck.
    domain (str): Explicit research domain (defaults to local_config.yaml or "computational science").
    track (str): "numerical_algorithm" (default), "pure_theory", or "engineering_portfolio".
    max_rounds (int): Default 3, hard-capped at 5 (1 <= max_rounds <= 5).
    run_day1_pilot (bool): Default False (paper-only screening); True runs <60 s toy pilot + Stage 0 + Stage 1A.
    skip_local_overlay (bool | str): "auto" (default: auto-suppresses mismatched lab overlay on
        cross-domain `domain`), True (always skip), or False (always apply if present).
    cutoff_year (int): Optional hard upper-bound year passed through to `idea-novelty-screen`.
    target_venue (str): Optional target journal/conference.
    prior_art_summary (str): Optional pre-compiled prior-art brief passed to `idea-novelty-screen`.
    context (str): Optional extra constraints or problem notes.
    pilot_dir (str): Optional directory for `<60 s` toy scripts (default ".idea_loop_pilots").
    initial_graveyard (list[dict]): Optional pre-populated killed ideas (useful for cross-host resumes).
    initial_constraints (list[str]): Optional pre-populated `design_space_constraints`.
    agent_type (str): "auto" (default) or explicit "research" / "self" override.
    model (str): Model tier ("inherit", "pro", "flash", "flash_lite"; default from overlay or "inherit").
"""

import datetime
import io
import json
import re
from contextlib import redirect_stdout
from pathlib import Path

VALID_TRACKS = ("numerical_algorithm", "pure_theory", "engineering_portfolio")
HARD_MAX_ROUNDS = 5
MAX_PILOT_SECONDS = 60.0
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


def _resolve_sibling_script(rel_parts) -> Path:
    """Locate sibling workflow scripts (`screen_idea.py`, `review_panel.py`) across skill roots."""
    if "__file__" in globals():
        direct = Path(__file__).resolve().parents[2].joinpath(*rel_parts)
        if direct.is_file():
            return direct
    for root in _skill_root_candidates():
        cand = root.joinpath(*rel_parts)
        if cand.is_file():
            return cand
    raise FileNotFoundError(f"Required sibling workflow script not found: {'/'.join(rel_parts)}")


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
    """Mirror `screen_idea.py` / `review_panel.py` cross-domain local-overlay auto-suppression."""
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


def _dedup_extend(dest: list, items) -> None:
    seen = {str(x).strip().lower() for x in dest if str(x).strip()}
    for item in items or []:
        text = str(item).strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            dest.append(text)


def _format_graveyard(graveyard: list, constraints: list) -> str:
    if not graveyard and not constraints:
        return ""
    lines = ["=== GRAVEYARD (PRIOR KILLED / REJECTED ROUNDS — DO NOT REPACKAGE) ==="]
    for g in graveyard:
        lines.append(
            f"- Round {g.get('round', '?')} | {g.get('idea_title', 'untitled')} | "
            f"Killed at: {g.get('killed_at', 'unknown')} | Reason: {g.get('failure_mode', '')}"
        )
    if constraints:
        lines.append("\n=== ACCUMULATED DESIGN-SPACE CONSTRAINTS (MANDATORY COMPLIANCE) ===")
        for i, c in enumerate(constraints, 1):
            lines.append(f"{i}. {c}")
    return "\n".join(lines)


def _extract_screen_failure_and_constraints(screen_out: dict) -> tuple:
    sg = screen_out.get("screen_gate") or {}
    prt = screen_out.get("pivot_red_team") or {}
    reasons = [f"screen_recommendation={sg.get('recommendation', 'unknown')}", f"novelty={sg.get('novelty_verdict', 'unknown')}"]
    for scout in screen_out.get("results") or []:
        sid = scout.get("scout_id", "scout")
        if int(scout.get("fatal_blocker_count", 0) or 0) > 0:
            summ = str(scout.get("summary") or "").strip()[:220]
            if summ:
                reasons.append(f"{sid}: {summ}")
    dropped = [
        f"{row.get('pivot_title', 'pivot')}: {row.get('primary_math_or_scaling_trap', '')[:120]}"
        for row in (prt.get("pivot_audit") or [])
        if row.get("pivot_verdict") in ("DROP_PIVOT", "NEEDS_FRESH_SCREEN")
    ]
    if dropped:
        reasons.append("pivots_rejected=[" + "; ".join(dropped[:3]) + "]")
    constraints = list(prt.get("design_space_constraints") or [])
    return " | ".join(reasons), constraints


def _evaluate_screen_transition(screen_out: dict, track: str):
    """Fail-closed Round Screen transition: ('BLOCKED_OFFLINE' | 'CLEARED' | 'KILLED', active_pivot_or_None)."""
    sg = screen_out.get("screen_gate") or {}
    rec = str(sg.get("recommendation", "") or "")
    live_status = str(sg.get("live_search_status", "not_evaluated") or "not_evaluated")
    search_req = bool(sg.get("search_verification_required", False))
    hard_novelty = track != "engineering_portfolio"

    prt = screen_out.get("pivot_red_team") or {}
    surviving_pivots = [
        row
        for row in (prt.get("pivot_audit") or [])
        if row.get("pivot_verdict") in ("SURVIVES_RED_TEAM", "VIABLE_WITH_PATCH")
    ]

    if rec == "NEEDS_LIVE_SEARCH_VERIFICATION":
        return "BLOCKED_OFFLINE", None
    if hard_novelty and search_req and (rec == "PROCEED_TO_PROTOTYPE" or bool(surviving_pivots)):
        return "BLOCKED_OFFLINE", None
    if hard_novelty and live_status in ("blocked_or_offline", "not_evaluated") and rec != "KILL_OR_REFRAME":
        return "BLOCKED_OFFLINE", None

    if rec == "PROCEED_TO_PROTOTYPE":
        return "CLEARED", None
    if surviving_pivots:
        return "CLEARED", surviving_pivots[0]
    return "KILLED", None


def _evaluate_stage0_pass(stage0_out: dict) -> tuple:
    """Fail-closed Stage 0 gate: requires ALIGNED_FAIL_LOUD, p0_p1_count==0, not blocked_by_permission."""
    g = stage0_out.get("stage0_gate") or {}
    verdict = g.get("stage0_verdict", "SILENT_POLLUTION_RISK")
    p0_p1 = g.get("p0_p1_count")
    if not isinstance(p0_p1, int):
        p0_p1 = 1
    exec_status = g.get("execution_status", "blocked_by_permission")
    closed = bool(g.get("stage0_closed", False))
    passed = (
        closed
        and verdict == "ALIGNED_FAIL_LOUD"
        and p0_p1 == 0
        and exec_status in ("executed_passed", "no_runnable_targets")
    )
    if passed:
        return True, ""
    ptrs = "; ".join(str(x) for x in (g.get("blocking_pointers") or [])[:4])
    detail = f"stage0_verdict={verdict}, p0_p1_count={p0_p1}, exec={exec_status}"
    if ptrs:
        detail += f" ({ptrs})"
    return False, detail


def _evaluate_stage1a_pass(stage1a_out: dict) -> tuple:
    """Fail-closed Stage 1A gate: SOLID_BASELINE or MECHANISM_SOLID_PARITY_FIX_NEEDED with p0_count==0."""
    g = stage1a_out.get("stage1a_gate") or {}
    verdict = g.get("baseline_verdict", "REPAIR_RISK_PILOT_REQUIRED")
    p0_count = g.get("p0_count")
    p0_p1 = g.get("p0_p1_count")
    if not isinstance(p0_count, int):
        # Fail-closed if p0_count missing: trust 0 only on SOLID_BASELINE with p0_p1_count==0
        p0_count = 0 if (verdict == "SOLID_BASELINE" and p0_p1 == 0) else (p0_p1 if isinstance(p0_p1, int) else 1)

    passed = (verdict in ("SOLID_BASELINE", "MECHANISM_SOLID_PARITY_FIX_NEEDED")) and (p0_count == 0)
    if passed:
        return True, ""
    return False, f"baseline_verdict={verdict}, p0_count={p0_count}, p0_p1_count={p0_p1}"


async def _invoke_subworkflow(script_path: Path, sub_args: dict) -> dict:
    """Execute a sibling top-level-await workflow script verbatim using live workflow primitives."""
    src = script_path.read_text(encoding="utf-8")
    indented = "\n".join("    " + line for line in src.splitlines())
    wrapped = "async def _sub_workflow_main():\n" + indented + "\n"
    code_obj = compile(wrapped, str(script_path), "exec")
    ns = {
        "__file__": str(script_path),
        "args": sub_args,
        "log": log,
        "phase": phase,
        "agent": agent,
        "parallel": parallel,
    }
    exec(code_obj, ns)
    buf = io.StringIO()
    with redirect_stdout(buf):
        await ns["_sub_workflow_main"]()
    raw = buf.getvalue().strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        idx = raw.find("{")
        if idx >= 0:
            return json.loads(raw[idx:])
        raise


# --- Parse & Validate Inputs (Fail-Closed) ---

LOCAL_CFG, LOCAL_CFG_SOURCE, LOCAL_OVERLAY_MD, LOCAL_OVERLAY_SOURCE = _load_local_overlay()

problem_space = str(args.get("problem_space") or args.get("idea_space") or "").strip()
if not problem_space:
    raise ValueError("Provide 'problem_space' describing the target scientific problem space.")

raw_track = str(args.get("track") or "numerical_algorithm").strip().lower().replace("-", "_").replace(" ", "_")
if raw_track not in VALID_TRACKS:
    raise ValueError(f"Unsupported track '{args.get('track')}'. Must be one of {VALID_TRACKS}.")
track = raw_track

raw_max_rounds = args.get("max_rounds", 3)
max_rounds = 3 if raw_max_rounds is None or str(raw_max_rounds).strip() == "" else int(raw_max_rounds)
if max_rounds < 1 or max_rounds > HARD_MAX_ROUNDS:
    raise ValueError(f"'max_rounds' must be between 1 and {HARD_MAX_ROUNDS} (hard cap), got {max_rounds}.")

run_day1_pilot = bool(args.get("run_day1_pilot", False))

CURRENT_YEAR = datetime.date.today().year
raw_cutoff_year = args.get("cutoff_year")
cutoff_year = None
if raw_cutoff_year is not None and str(raw_cutoff_year).strip() != "":
    cutoff_year = int(raw_cutoff_year)
    if not (1900 <= cutoff_year <= CURRENT_YEAR):
        raise ValueError(f"'cutoff_year' must be between 1900 and {CURRENT_YEAR}, got {cutoff_year}.")

explicit_domain = str(args.get("domain", "") or "").strip()
skip_local_overlay_arg = args.get("skip_local_overlay", "auto")
OVERLAY_APPLIED, OVERLAY_SKIP_REASON = _resolve_local_overlay_policy(
    explicit_domain, LOCAL_CFG, LOCAL_CFG_SOURCE, LOCAL_OVERLAY_MD, skip_local_overlay_arg
)
DEFAULT_DOMAIN = str(LOCAL_CFG.get("default_domain", "computational science")).strip()
DEFAULT_MODEL = str(LOCAL_CFG.get("default_model", "inherit")).strip() or "inherit"
ACTIVE_OVERLAY_MD = LOCAL_OVERLAY_MD if OVERLAY_APPLIED else ""

domain = explicit_domain or DEFAULT_DOMAIN
target_venue = str(
    args.get("target_venue") or (LOCAL_CFG.get("default_target_venue", "") if OVERLAY_APPLIED else "") or ""
).strip()
prior_art_summary = str(args.get("prior_art_summary", "") or "").strip()
context = str(args.get("context", "") or "").strip()
pilot_dir = str(args.get("pilot_dir") or ".idea_loop_pilots").strip()
agent_type_override = str(args.get("agent_type", "auto") or "auto").strip().lower()
model = str(args.get("model") or DEFAULT_MODEL).strip()

SCREEN_SCRIPT = _resolve_sibling_script(("idea-novelty-screen", "scripts", "screen_idea.py"))
REVIEW_SCRIPT = _resolve_sibling_script(("scientific-report-review", "scripts", "review_panel.py"))

# --- Schemas for Outer Loop Steps (Generator & Pilot Builder Only) ---

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "idea_title": {"type": "string"},
        "core_mechanism": {"type": "string"},
        "exact_claim": {"type": "string"},
        "why_cheap_baseline_fails": {"type": "string"},
        "day1_falsification_test": {"type": "string"},
        "non_overlap_attestation": {"type": "string"},
        "pitch_markdown": {"type": "string"},
    },
    "required": [
        "idea_title",
        "core_mechanism",
        "exact_claim",
        "why_cheap_baseline_fails",
        "day1_falsification_test",
        "non_overlap_attestation",
        "pitch_markdown",
    ],
}

PILOT_BUILD_SCHEMA = {
    "type": "object",
    "properties": {
        "script_path": {"type": "string"},
        "report_path": {"type": "string"},
        "repro_command": {"type": "string"},
        "smoke_command": {"type": "string"},
        "runtime_seconds": {"type": "number"},
        "toy_comparison_summary": {"type": "string"},
        "failure_boundary_conditions": {"type": "string"},
        "pilot_status": {
            "type": "string",
            "enum": ["completed_under_60s", "exceeded_compute_budget", "failed_to_run", "falsified_by_baseline"],
        },
    },
    "required": [
        "script_path",
        "report_path",
        "repro_command",
        "smoke_command",
        "runtime_seconds",
        "toy_comparison_summary",
        "failure_boundary_conditions",
        "pilot_status",
    ],
}


def _build_generator_prompt(round_idx: int, graveyard: list, constraints: list) -> str:
    overlay_block = (
        f"Optional local lab/domain overlay priors:\n---\n{ACTIVE_OVERLAY_MD}\n---\n\n"
        if ACTIVE_OVERLAY_MD
        else ""
    )
    graveyard_block = _format_graveyard(graveyard, constraints)
    non_overlap_rule = (
        "\nMANDATORY ROUND r > 1 NON-OVERLAP & CONSTRAINT COMPLIANCE:\n"
        "- Your proposal MUST be substantively distinct from EVERY entry in GRAVEYARD.\n"
        "- STRICTLY BAN repackaging a killed mechanism under renamed terminology or cosmetic tweaks.\n"
        "- Explicitly satisfy EVERY item in ACCUMULATED DESIGN-SPACE CONSTRAINTS and justify this in `non_overlap_attestation`.\n"
        if round_idx > 1 or graveyard or constraints
        else "\nFor Round 1, set `non_overlap_attestation` to 'Initial proposal (empty graveyard)'.\n"
    )
    cutoff_note = (
        f"\nTEMPORAL CUTOFF ({cutoff_year}-12-31): Base your proposal strictly on concepts available on or before {cutoff_year}-12-31.\n"
        if cutoff_year is not None
        else ""
    )
    return (
        f"You are the Idea Generator (Round {round_idx}/{max_rounds}, track='{track}').\n"
        "Mission: Propose EXACTLY ONE concrete, sharply falsifiable research idea inside the target problem space. "
        "Do NOT pitch a bundle of 3 vague ideas, and do NOT invent results.\n\n"
        f"Problem space: {problem_space}\n"
        f"Research domain: {domain}\n"
        f"Track: {track}\n"
        + (f"Target venue: {target_venue}\n" if target_venue else "")
        + (f"Additional context: {context}\n" if context else "")
        + cutoff_note
        + "\n"
        + overlay_block
        + (graveyard_block + "\n\n" if graveyard_block else "")
        + "REQUIRED PROPOSAL ELEMENTS:\n"
        "1. `idea_title`: Crisp name of the single proposed mechanism.\n"
        "2. `core_mechanism`: Exact mathematical/algorithmic/system mechanism (no hand-waving).\n"
        "3. `exact_claim`: Quantified, falsifiable hypothesis stating what improves and in which regime.\n"
        "4. `why_cheap_baseline_fails`: Concrete technical reason a simple cheap baseline (minimal ~5-20 line patch, "
        "off-the-shelf library call, or <=~50-line textbook baseline / tightest known theorem) cannot match this mechanism.\n"
        "5. `day1_falsification_test`: Exact local CPU `< 60 s` toy experiment (`--smoke < 10 s`, zero sweeps/tuning) "
        "(or analytic toy calculation for `pure_theory`) with hard Kill vs. Build criteria.\n"
        "6. `pitch_markdown`: Self-contained concise markdown pitch (<= 350 words) combining items 1-5 to be screened blindly.\n"
        + non_overlap_rule
        + "Return your structured JSON via `finish`."
    )


def _build_pilot_prompt(round_idx: int, proposal: dict, active_pivot, screen_out: dict) -> str:
    round_dir = f"{pilot_dir}/round_{round_idx}"
    script_target = f"{round_dir}/pilot_round_{round_idx}.py"
    report_target = f"{round_dir}/pilot_report_round_{round_idx}.md"
    scout1 = next((r for r in (screen_out.get("results") or []) if r.get("scout_id") == "baseline_feasibility_killer"), {})
    baseline_hint = str(scout1.get("strongest_cheap_baseline") or proposal.get("why_cheap_baseline_fails") or "")
    pivot_note = (
        f"\nSURVIVING VETTED PIVOT TO IMPLEMENT INSTEAD OF ORIGINAL DRAFT:\n{json.dumps(active_pivot, indent=2)}\n"
        if active_pivot
        else ""
    )
    return (
        f"You are the Day-1 Falsification Pilot Builder (Round {round_idx}/{max_rounds}, track='{track}').\n"
        "Mission: Implement and execute a minimal, self-contained, local-CPU toy falsification pilot testing the "
        "proposed mechanism against the strongest cheap baseline under IDENTICAL inputs, noise, and compute budgets.\n\n"
        "HARD COMPUTE & HYGIENE CEILING (NON-NEGOTIABLE):\n"
        "- Local CPU ONLY — ZERO HPC/SLURM/GPU jobs, ZERO hyperparameter sweeps, ZERO multi-seed tuning.\n"
        f"- Single-file Python script at `{script_target}` that finishes end-to-end in `< 60 s` and supports `--smoke` finishing in `< 10 s`.\n"
        "- Set single-thread BLAS locks (`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`) at top of script.\n"
        "- Zero silent `except: pass`, zero unlogged solver fallbacks, atomic file writes if writing artifacts.\n"
        "- Implement the strongest cheap baseline (<=~50 lines or off-the-shelf library call) fairly with full input parity.\n"
        f"- Write a concise markdown pilot report at `{report_target}` stating exact equations/branches implemented, "
        "exact `< 60 s` repro command, `--smoke` command, observed toy comparison table, and explicit failure boundary conditions.\n"
        "- If the cheap baseline beats or matches the proposed mechanism on the toy test, report `pilot_status='falsified_by_baseline'` honestly.\n\n"
        f"Domain: {domain}\n"
        f"Proposal:\n```json\n{json.dumps(proposal, indent=2)}\n```\n"
        + pivot_note
        + f"\nStrongest cheap baseline identified in screening: {baseline_hint}\n"
        "Return your structured JSON via `finish`."
    )


# --- Bounded Outer Falsification Loop ---

graveyard = list(args.get("initial_graveyard") or [])
accumulated_constraints = []
_dedup_extend(accumulated_constraints, args.get("initial_constraints") or [])

round_history = []
terminal_status = "EXHAUSTED_NO_SURVIVOR"
survivor = None
blocked_reason = None

gen_agent_type = "research" if agent_type_override in ("", "auto") else agent_type_override
pilot_agent_type = "self" if agent_type_override in ("", "auto") else agent_type_override

log(
    f"Starting idea-falsification-loop: track={track}, domain='{domain}', max_rounds={max_rounds}, "
    f"run_day1_pilot={run_day1_pilot}, overlay_applied={OVERLAY_APPLIED}"
    + (f"[{OVERLAY_SKIP_REASON}]" if OVERLAY_SKIP_REASON else "")
    + (f", cutoff_year={cutoff_year}" if cutoff_year is not None else "")
)

for r in range(1, max_rounds + 1):
    phase(f"Idea Falsification Loop — Round {r}/{max_rounds}: Propose & Screen")
    proposal = await agent(
        prompt=_build_generator_prompt(r, graveyard, accumulated_constraints),
        schema=PROPOSAL_SCHEMA,
        role=f"Round {r}/{max_rounds} Idea Generator ({track})",
        type_name=gen_agent_type,
        model=model,
    )
    idea_title = str(proposal.get("idea_title") or f"Round {r} Proposal")
    log(f"Round {r}/{max_rounds} proposed: {idea_title}")

    screen_args = {
        "track": track,
        "idea": proposal.get("pitch_markdown") or json.dumps(proposal, indent=2),
        "domain": domain,
        "target_venue": target_venue,
        "skip_local_overlay": skip_local_overlay_arg,
        "prior_art_summary": prior_art_summary,
        "context": context,
        "agent_type": agent_type_override,
        "model": model,
    }
    if cutoff_year is not None:
        screen_args["cutoff_year"] = cutoff_year

    screen_out = await _invoke_subworkflow(SCREEN_SCRIPT, screen_args)
    screen_status, active_pivot = _evaluate_screen_transition(screen_out, track)

    round_rec = {
        "round": r,
        "idea_title": idea_title,
        "proposal": proposal,
        "screen_gate": screen_out.get("screen_gate"),
        "screen_status": screen_status,
        "active_pivot": active_pivot,
        "pilot": None,
        "stage0_gate": None,
        "stage1a_gate": None,
    }

    if screen_status == "BLOCKED_OFFLINE":
        terminal_status = "BLOCKED_OFFLINE"
        sg = screen_out.get("screen_gate") or {}
        blocked_reason = (
            f"Round {r} halted fail-closed: live prior-art search unavailable "
            f"(recommendation={sg.get('recommendation')}, live_search_status={sg.get('live_search_status')}, "
            f"phase2={sg.get('phase2_live_search_status')})."
        )
        round_rec["outcome"] = "BLOCKED_OFFLINE"
        round_history.append(round_rec)
        log(f"HALT: {blocked_reason}")
        break

    if screen_status == "KILLED":
        failure_mode, new_constraints = _extract_screen_failure_and_constraints(screen_out)
        _dedup_extend(accumulated_constraints, new_constraints)
        graveyard.append(
            {
                "round": r,
                "idea_title": idea_title,
                "killed_at": "idea_novelty_screen",
                "failure_mode": failure_mode,
                "constraints_emitted": new_constraints,
            }
        )
        round_rec["outcome"] = "KILLED_AT_SCREEN"
        round_history.append(round_rec)
        log(f"Round {r}/{max_rounds} killed at screen -> appended to GRAVEYARD ({len(accumulated_constraints)} constraint(s)).")
        continue

    # Screen cleared! Stop immediately if paper-only mode (`run_day1_pilot == False`).
    if not run_day1_pilot:
        terminal_status = "SURVIVOR_FOUND"
        round_rec["outcome"] = "SURVIVOR_FOUND"
        round_history.append(round_rec)
        survivor = {
            "round": r,
            "idea_title": idea_title,
            "proposal": proposal,
            "active_pivot": active_pivot,
            "screen_output": screen_out,
            "pilot": None,
            "stage0_gate": None,
            "stage1a_gate": None,
        }
        log(f"Round {r}/{max_rounds} SURVIVOR_FOUND (paper-only screening mode).")
        break

    # Step 3: Day-1 Falsification Pilot (<60 s CPU) + Stage 0 + Stage 1A (no same-round patching)
    phase(f"Idea Falsification Loop — Round {r}/{max_rounds}: Day-1 Pilot + Stage 0 + Stage 1A")
    pilot_res = await agent(
        prompt=_build_pilot_prompt(r, proposal, active_pivot, screen_out),
        schema=PILOT_BUILD_SCHEMA,
        role=f"Round {r}/{max_rounds} Day-1 Pilot Builder (<60 s CPU)",
        type_name=pilot_agent_type,
        model=model,
    )
    round_rec["pilot"] = pilot_res

    p_status = pilot_res.get("pilot_status", "failed_to_run")
    p_runtime = float(pilot_res.get("runtime_seconds", 999.0) or 999.0)
    if p_status != "completed_under_60s" or p_runtime > MAX_PILOT_SECONDS:
        reason = f"pilot_status={p_status}, runtime_seconds={p_runtime:.1f}s (ceiling={MAX_PILOT_SECONDS:.0f}s): {pilot_res.get('toy_comparison_summary', '')[:200]}"
        graveyard.append(
            {
                "round": r,
                "idea_title": idea_title,
                "killed_at": "day1_pilot_execution",
                "failure_mode": reason,
                "constraints_emitted": [],
            }
        )
        round_rec["outcome"] = "KILLED_AT_PILOT"
        round_history.append(round_rec)
        log(f"Round {r}/{max_rounds} rejected at Day-1 pilot: {reason}")
        continue

    pilot_script = str(pilot_res.get("script_path") or "").strip()
    pilot_report = str(pilot_res.get("report_path") or "").strip()
    pilot_report_list = [pilot_report] if pilot_report else []
    pilot_extra_list = [pilot_script] if pilot_script else []

    # Gate A: Stage 0 (`code-math-alignment`) verbatim via review_panel.py
    stage0_args = {
        "stage": "stage0",
        "mode": "review",
        "report": pilot_report_list,
        "report_text": "" if pilot_report_list else json.dumps(pilot_res, indent=2),
        "extra_files": pilot_extra_list,
        "domain": domain,
        "skip_local_overlay": skip_local_overlay_arg,
        "agent_type": agent_type_override,
        "model": model,
    }
    stage0_out = await _invoke_subworkflow(REVIEW_SCRIPT, stage0_args)
    round_rec["stage0_gate"] = stage0_out.get("stage0_gate")
    s0_ok, s0_reason = _evaluate_stage0_pass(stage0_out)
    if not s0_ok:
        graveyard.append(
            {
                "round": r,
                "idea_title": idea_title,
                "killed_at": "stage0_code_math_alignment",
                "failure_mode": s0_reason,
                "constraints_emitted": [],
            }
        )
        round_rec["outcome"] = "KILLED_AT_STAGE0"
        round_history.append(round_rec)
        log(f"Round {r}/{max_rounds} rejected at Stage 0: {s0_reason}")
        continue

    # Gate B: Stage 1A (`baseline-killer-audit`) verbatim via review_panel.py
    stage1a_args = {
        "stage": "stage1a",
        "mode": "review",
        "iteration": 1,
        "report": pilot_report_list,
        "report_text": "" if pilot_report_list else json.dumps(pilot_res, indent=2),
        "extra_files": pilot_extra_list,
        "domain": domain,
        "skip_local_overlay": skip_local_overlay_arg,
        "agent_type": agent_type_override,
        "model": model,
    }
    stage1a_out = await _invoke_subworkflow(REVIEW_SCRIPT, stage1a_args)
    round_rec["stage1a_gate"] = stage1a_out.get("stage1a_gate")
    s1a_ok, s1a_reason = _evaluate_stage1a_pass(stage1a_out)
    if not s1a_ok:
        graveyard.append(
            {
                "round": r,
                "idea_title": idea_title,
                "killed_at": "stage1a_baseline_killer",
                "failure_mode": s1a_reason,
                "constraints_emitted": [],
            }
        )
        round_rec["outcome"] = "KILLED_AT_STAGE1A"
        round_history.append(round_rec)
        log(f"Round {r}/{max_rounds} rejected at Stage 1A: {s1a_reason}")
        continue

    # Both Stage 0 and Stage 1A passed!
    terminal_status = "SURVIVOR_FOUND"
    round_rec["outcome"] = "SURVIVOR_FOUND"
    round_history.append(round_rec)
    survivor = {
        "round": r,
        "idea_title": idea_title,
        "proposal": proposal,
        "active_pivot": active_pivot,
        "screen_output": screen_out,
        "pilot": pilot_res,
        "stage0_gate": stage0_out.get("stage0_gate"),
        "stage1a_gate": stage1a_out.get("stage1a_gate"),
    }
    log(f"Round {r}/{max_rounds} SURVIVOR_FOUND (passed Screen + <60 s CPU Pilot + Stage 0 + Stage 1A).")
    break

output = {
    "terminal_status": terminal_status,
    "blocked_reason": blocked_reason,
    "track": track,
    "domain": domain,
    "problem_space": problem_space,
    "max_rounds": max_rounds,
    "rounds_run": len(round_history),
    "run_day1_pilot": run_day1_pilot,
    "cutoff_year": cutoff_year,
    "local_overlay_loaded": {
        "config": LOCAL_CFG_SOURCE,
        "markdown": LOCAL_OVERLAY_SOURCE,
        "applied": OVERLAY_APPLIED,
        "skipped_reason": OVERLAY_SKIP_REASON,
    },
    "survivor": survivor,
    "graveyard": graveyard,
    "consolidated_design_space_constraints": accumulated_constraints,
    "round_history": round_history,
}
print(json.dumps(output, indent=2))
