"""
Blind 3-scout pre-code literature review, novelty screening, theoretical
viability, and bounded 1-round Pivot Red-Team workflow (`idea-novelty-screen`).

Architecture (zero cross-talk between scouts; blind 1-round Pivot Red-Team):
    Phase 1 — Track-Routed Blind Scouts (parallel):
      1. `baseline_feasibility_killer` (`research`): Track-adapted killer baseline
         (minimal patch, library call, or simple <=~50-line textbook baseline /
         tightest known theorem or reduction / standard practitioner baseline +
         data-leakage guard) and 24-48h Day-1 falsification pilots.
      2. `theory_limits_critic` (`research`): Track-adapted scaling, lower bounds /
         proof gaps / validity & leakage traps, and labeled failure-mode map (FM-1, FM-2, ...).
      3. `literature_novelty_strategist` (`self`, live `search_web` only — 5-8 queries):
         Dynamic-window arXiv/journal & cross-field prior-art hunt, novelty verdict
         (hard gate on numerical_algorithm/pure_theory; secondary note on engineering_portfolio),
         crisp 2-sentence Referee #2 fatal objection, and 2-3 candidate pivots.
    Phase 2 — Bounded 1-Round Pivot Red-Team Mini-Pass (isolated `self` agent, live `search_web` only):
      Audits every candidate Pivot against the strongest cheap baseline, derived Phase 1
      constraints, and live prior-art search in the Pivot's own subfield
      (`SURVIVES_RED_TEAM` | `VIABLE_WITH_PATCH` | `NEEDS_FRESH_SCREEN` | `DROP_PIVOT`).

Expected `Args` (dict passed via run_workflow):
    idea (str): Idea pitch, hypothesis, or problem statement.
    idea_files (str | list[str]): Optional path(s) to rough notes, equations, slides, or PDFs.
    seed_papers (str | list[str]): Optional known seed papers (titles, arXiv IDs, or paths).
    track (str): "auto" (default), "numerical_algorithm", "pure_theory", or "engineering_portfolio".
    domain (str): Research domain (defaults to local_config.yaml or "computational science").
    target_venue (str): Optional target journal/conference.
    prior_art_summary (str): Optional pre-compiled prior-art brief (supplied to Scout 3 & Pivot Red-Team).
    cutoff_year (int): Optional hard upper-bound year (e.g. 2025) for retrospective pre-cutoff evaluations.
    context (str): Optional constraints (compute budget, target regime, timeline).
    previous_screen (str): Optional path or text of prior screen (for Pivot Round 2 recheck).
    candidate_pivots (list[dict | str]): Optional explicit pivots to red-team instead of Scout 3's.
    skip_pivot_red_team (bool): Optional; set True to skip Phase 2 Pivot Red-Team pass.
    skip_local_overlay (bool | str): Optional; "auto" (default: auto-suppresses lab
        `local_overlay.md` and domain-specific venues/arXiv categories when an explicit
        `domain` does not overlap `local_config.yaml`'s `default_domain`), True (always
        skip), or False (always apply if present).
    scouts (list[str]): Optional subset of scout IDs. Defaults to all 3.
    agent_type (str): "auto" (default: Scout 3 -> "self", Scouts 1-2 -> "research"),
        or explicit "research" / "self" override.
    model (str): Model tier ("inherit", "pro", "flash", "flash_lite"; default from overlay or "inherit").
"""

import datetime
import json
import re
from pathlib import Path

VALID_TRACKS = ("numerical_algorithm", "pure_theory", "engineering_portfolio")
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


def _normalize_list(value):
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if item]


def _resolve_track(raw_track: str, idea_text: str, context: str, target_venue: str):
    """Resolve user-supplied track or auto-infer upfront from pitch/context."""
    t = str(raw_track or "auto").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "numerical_algorithm": "numerical_algorithm",
        "numerical": "numerical_algorithm",
        "algorithm": "numerical_algorithm",
        "computational": "numerical_algorithm",
        "pure_theory": "pure_theory",
        "theory": "pure_theory",
        "conceptual": "pure_theory",
        "math": "pure_theory",
        "engineering_portfolio": "engineering_portfolio",
        "engineering": "engineering_portfolio",
        "portfolio": "engineering_portfolio",
        "applied": "engineering_portfolio",
    }
    if t in aliases:
        return aliases[t], "user_supplied"
    if t not in ("", "auto"):
        raise ValueError(f"Unsupported track '{raw_track}'. Use 'auto' or one of {VALID_TRACKS}.")

    blob = f"{idea_text}\n{context}\n{target_venue}".lower()
    eng_hits = len(
        re.findall(
            r"\b(portfolio|production|deployment|pipeline|dashboard|web app|mlops|kaggle|"
            r"engineering project|product|benchmark suite|end-to-end system|github repo)\b",
            blob,
        )
    )
    theory_hits = len(
        re.findall(
            r"\b(theorem|lemma|proof|conjecture|no-go|axiomatic|ontology|conceptual framework|"
            r"formalization|equivalence class|exact duality|category theory|analytic bound|"
            r"purely theoretical|closed-form proof)\b",
            blob,
        )
    )
    algo_hits = len(
        re.findall(
            r"\b(algorithm|solver|sampler|monte carlo|estimator|optimizer|benchmark|runtime|"
            r"speedup|shots|variance reduction|gradient|simulation|numerical|gpu|cluster)\b",
            blob,
        )
    )
    if eng_hits >= 1 and eng_hits >= algo_hits and theory_hits == 0:
        return "engineering_portfolio", "auto_inferred"
    if theory_hits >= 2 and algo_hits == 0:
        return "pure_theory", "auto_inferred"
    return "numerical_algorithm", "auto_inferred"


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


# --- Load Optional Local Overlay & Parse Args ---

LOCAL_CFG, LOCAL_CFG_SOURCE, LOCAL_OVERLAY_MD, LOCAL_OVERLAY_SOURCE = _load_local_overlay()

CURRENT_YEAR = datetime.date.today().year
raw_cutoff_year = args.get("cutoff_year")
cutoff_year = None
if raw_cutoff_year is not None and str(raw_cutoff_year).strip() != "":
    cutoff_year = int(raw_cutoff_year)
    if not (1900 <= cutoff_year <= CURRENT_YEAR):
        raise ValueError(f"'cutoff_year' must be between 1900 and {CURRENT_YEAR}, got {cutoff_year}.")
EFFECTIVE_YEAR = cutoff_year if cutoff_year is not None else CURRENT_YEAR
LOOKBACK_YEARS = int(LOCAL_CFG.get("prior_art_lookback_years", 6) or 6)
SEARCH_WINDOW = f"{EFFECTIVE_YEAR - LOOKBACK_YEARS}-{EFFECTIVE_YEAR}"
CUTOFF_DIRECTIVE = (
    f"\n- TEMPORAL CUTOFF ({EFFECTIVE_YEAR}-12-31): Restrict prior-art evaluation strictly to sources published "
    f"on or before {EFFECTIVE_YEAR}-12-31; ignore and NEVER cite any post-{EFFECTIVE_YEAR} work."
    if cutoff_year is not None
    else ""
)

DEFAULT_DOMAIN = str(LOCAL_CFG.get("default_domain", "computational science")).strip()
DEFAULT_MODEL = str(LOCAL_CFG.get("default_model", "inherit")).strip()

idea_text = str(args.get("idea", "") or "").strip()
idea_files = _normalize_list(args.get("idea_files"))
seed_papers = _normalize_list(args.get("seed_papers"))
prior_art_summary = str(args.get("prior_art_summary", "") or "").strip()
explicit_domain = str(args.get("domain") or "").strip()
domain = explicit_domain or DEFAULT_DOMAIN
OVERLAY_APPLIED, OVERLAY_SKIP_REASON = _resolve_local_overlay_policy(
    explicit_domain, LOCAL_CFG, LOCAL_CFG_SOURCE, LOCAL_OVERLAY_MD, args.get("skip_local_overlay")
)
ACTIVE_OVERLAY_MD = LOCAL_OVERLAY_MD if OVERLAY_APPLIED else ""
DEFAULT_VENUES = (
    (_normalize_list(LOCAL_CFG.get("default_venues")) or ["top domain-specific journals/conferences"])
    if OVERLAY_APPLIED
    else ["top domain-specific journals/conferences"]
)
ARXIV_CATS = _normalize_list(LOCAL_CFG.get("arxiv_categories")) if OVERLAY_APPLIED else []
target_venue = str(
    args.get("target_venue") or (LOCAL_CFG.get("default_target_venue", "") if OVERLAY_APPLIED else "") or ""
).strip()
context = str(args.get("context", "") or "").strip()
previous_screen = str(args.get("previous_screen", "") or "").strip()
explicit_pivots = args.get("candidate_pivots")
skip_pivot_red_team = bool(args.get("skip_pivot_red_team", False))
selected_ids = args.get("scouts")
agent_type_override = str(args.get("agent_type", "auto") or "auto").strip().lower()
model = str(args.get("model") or DEFAULT_MODEL).strip()

if not idea_text and not idea_files:
    raise ValueError("Provide 'idea' (text pitch) and/or 'idea_files' (path or list of paths).")

track, track_source = _resolve_track(args.get("track", "auto"), idea_text, context, target_venue)

SCOUT_DEFAULT_AGENT_TYPE = {
    "baseline_feasibility_killer": "research",
    "theory_limits_critic": "research",
    "literature_novelty_strategist": "self",
}


def resolve_agent_type(scout_id: str) -> str:
    if agent_type_override not in ("", "auto"):
        return agent_type_override
    return SCOUT_DEFAULT_AGENT_TYPE.get(scout_id, "research")


# --- Track-Routed Rubrics ---

VENUES_HINT = ", ".join(DEFAULT_VENUES)
ARXIV_HINT = f"arXiv ({', '.join(ARXIV_CATS)})" if ARXIV_CATS else "arXiv and domain preprints"

TRACK_SCOUT_PROMPTS = {
    "numerical_algorithm": {
        "baseline_feasibility_killer": """You are the hostile supervisor / baseline-killer architect on track=`numerical_algorithm` (pre-code mirror of `baseline-killer-audit`).
1. STRONGEST CHEAP EXISTING BASELINE (EFFORT-BOUNDED): Identify the strongest cheap baseline a skilled practitioner would implement first — either a minimal patch (~5-20 lines), an off-the-shelf library call, or a simple single-file textbook baseline (<= ~50 lines / <= 1 hour to code, e.g., CRN, control variates, sorting, warm-start, standard iterative heuristic) at a small fraction of the proposed method's complexity/runtime. Could it capture 80-100% of the claimed gain? (Report realistic code size honestly.)
2. REPAIR VS. DISCOVERY RISK: Is the mechanism genuinely orthogonal to known heuristics, or mostly repairing a weak/strawman baseline choice?
3. INFORMATION-ASYMMETRY & EVALUATION TRAPS: Flag double standards to avoid (extra free info, symmetries, warm-starts withheld from the baseline; cherry-picking toy sizes; mismatched objectives).
4. DAY-1 FALSIFICATION PILOTS (populate `day1_pilots`): Design 2-3 cheap 24-48h numerical experiments — MUST include 1 analytically checkable toy test AND at least 1 **non-toy medium/hard instance** where bottlenecks turn on — with explicit numerical **Kill / Pivot / Build** criteria.
Set `fatal_blocker_count` to the count of unresolved showstopper baseline/feasibility flaws.""",
        "theory_limits_critic": """You are a rigorous senior theorist / computational methodologist on track=`numerical_algorithm` (pre-code mirror of Stage 1B Reviewer 8).
1. ASYMPTOTIC SCALING & FUNDAMENTAL LIMITS: Does the idea improve asymptotic scaling (with system size, term count, or norm) or only a constant factor? Audit BOTH primary resource and classical pre/post-processing scaling against known information-theoretic, variational, or no-go lower bounds.
2. EXACTNESS, BIAS & INVARIANTS: Is the estimator/algorithm strictly unbiased, or does truncation, regularization, or adaptive feedback inject systematic bias? Check exact domain invariants, conservation laws, symmetries, and analytically known limits.
3. END-TO-END BOTTLENECK & COST-SHIFTING: Does cutting one cost secretly explode another (classical optimizer runtime/RAM, circuit depth/overhead, pilot calibration, per-iteration recomputation)?
4. PREDICTED FAILURE-MODE MAP (populate `predicted_failure_modes` with concise IDs `FM-1`, `FM-2`, ...): Name the exact regimes where the idea will break, saturate, or fail catastrophically (e.g., strong coupling/ill-conditioning, wrong surrogates, noise).
Set `fatal_blocker_count` to the count of unresolved theoretical/scaling showstoppers.""",
        "literature_novelty_strategist": f"""You are a senior supervisor and top-journal referee on track=`numerical_algorithm` conducting a LIVE prior-art screen (HARD academic novelty gate).
LIVE SEARCH (STRICTLY READ-ONLY — `search_web` ONLY, NO FILE EDITS, NO SHELL):
- Read the idea/notes thoroughly first, then run 5-8 targeted `search_web` queries covering:
  (a) Direct home-field prior art ({SEARCH_WINDOW} {ARXIV_HINT}; venues such as {VENUES_HINT}, or `target_venue`),
  (b) Adjacent-field equivalents under DIFFERENT terminology (statistics, Monte Carlo variance reduction, bandits/experimental design, convex/SDP optimization, randomized/compressed sensing, tensor/graph methods), and
  (c) Known negative results, no-go theorems, or open-source baseline repos.
- Set `live_search_status` to `searched_live`, `used_supplied_brief`, or `blocked_or_offline` (if running in an offline `research` sandbox without `search_web`, rely on any supplied `prior_art_summary` / `seed_papers` and NEVER report `searched_live`). Cite ONLY verified papers with real arXiv IDs/DOIs/URLs — NEVER fabricate citations.{CUTOFF_DIRECTIVE}
DELIVERABLES:
1. PRIOR-ART & TERMINOLOGY MAP (`prior_art_hits`, `cross_field_translations`): Closest papers, exact overlap/scoop risk, what remains open.
2. NOVELTY VERDICT & VENUE-BAR FIT: Irreducible 1-2 sentence delta; set `novelty_verdict` (`CLEAR_NOVELTY_ABOVE_BAR` | `BORDERLINE_NEEDS_SHARPER_WEDGE` | `LIKELY_SCOOPED_OR_SUBSUMED`).
3. REFEREE #2 FATAL OBJECTION (`referee2_premortem`): Strictly **2 crisp sentences** stating the sharpest rejection objection (no multi-point essay).
4. CANDIDATE PIVOTS (`pivot_options`): Propose 2-3 sharp, concrete pivots (note: every pivot will be adversarially red-teamed in Phase 2).
Set `fatal_blocker_count` to the count of scoop/subsumption showstoppers.""",
    },
    "pure_theory": {
        "baseline_feasibility_killer": """You are the hostile theorist / proof-killer architect on track=`pure_theory`.
DO NOT force code benchmarks or numerical runtimes onto a purely theoretical/conceptual idea. Instead:
1. TIGHTEST KNOWN THEOREM / REDUCTION BASELINE (populate `strongest_cheap_baseline`): What is the tightest existing theorem, no-go bound, textbook inequality, or 3-line classical reduction that acts as the "cheap baseline"? Does the proposed claim collapse to a corollary or trivial relabeling of known results?
2. MINIMAL ADVERSARIAL COUNTEREXAMPLE SUITE: Construct the sharpest edge cases, degenerate limits, non-commuting/non-convex/singular cases, or regularity failures most likely to falsify the conjecture.
3. HIDDEN-ASSUMPTION & TRIVIALIZATION TRAPS: Flag circular definitions, unfalsifiable verbal framing, or hypotheses so strong they rule out all interesting instances.
4. DAY-1 ANALYTIC FALSIFICATION PILOTS (populate `day1_pilots`; set `is_non_toy=true` for non-trivial limiting/obstruction tests): Design 2-3 concrete 24-48h **analytic** tests (exact toy-model calculation, truth table, limiting-case reduction, or explicit proof-obstruction check) with crisp **Kill / Pivot / Build** criteria.
Set `fatal_blocker_count` to the count of unresolved fatal counterexamples or trivializations.""",
        "theory_limits_critic": """You are a rigorous senior mathematical/theoretical referee on track=`pure_theory`.
1. PROOF ARCHITECTURE, TIGHTNESS & NO-GO CHECK: Identify the hardest step in the proposed proof/derivation. Compare claimed scaling or bounds against known lower/upper bounds and no-go theorems.
2. EXACTNESS, REGULARITY & INVARIANTS: Check hidden hypotheses (compactness, continuity, commutativity, stationarity, independence, gauge/basis invariance, conservation laws) and analytically solvable limits.
3. SCOPE VS. SUBSTANCE: Distinguish genuine mathematical structure or unification from purely notational reformulation.
4. PREDICTED FAILURE-MODE MAP (populate `predicted_failure_modes` with concise IDs `FM-1`, `FM-2`, ...): Name the exact mathematical regimes, edge cases, or assumptions where the claim breaks or becomes vacuous.
Set `fatal_blocker_count` to the count of unresolved mathematical showstoppers.""",
        "literature_novelty_strategist": f"""You are a senior theoretical referee on track=`pure_theory` conducting a LIVE prior-art screen (HARD academic novelty gate).
LIVE SEARCH (STRICTLY READ-ONLY — `search_web` ONLY, NO FILE EDITS, NO SHELL):
- Read the idea/notes thoroughly first, then run 5-8 targeted `search_web` queries covering:
  (a) Direct home-field theorems/frameworks ({SEARCH_WINDOW} and foundational classics on {ARXIV_HINT}; venues such as {VENUES_HINT}, or `target_venue`),
  (b) Adjacent-field equivalents under DIFFERENT terminology (pure/applied math, information theory, statistical mechanics, theoretical CS, control/optimization), and
  (c) Known no-go theorems, impossibility results, or counterexamples.
- Set `live_search_status` to `searched_live`, `used_supplied_brief`, or `blocked_or_offline` (if running in an offline `research` sandbox without `search_web`, rely on any supplied `prior_art_summary` / `seed_papers` and NEVER report `searched_live`). Cite ONLY verified papers with real arXiv IDs/DOIs/URLs — NEVER fabricate citations.{CUTOFF_DIRECTIVE}
DELIVERABLES:
1. PRIOR-ART & TERMINOLOGY MAP (`prior_art_hits`, `cross_field_translations`): Closest theorems/papers, overlap/folklore risk, what remains genuinely open.
2. NOVELTY VERDICT & VENUE-BAR FIT: Irreducible 1-2 sentence theoretical delta; set `novelty_verdict` (`CLEAR_NOVELTY_ABOVE_BAR` | `BORDERLINE_NEEDS_SHARPER_WEDGE` | `LIKELY_SCOOPED_OR_SUBSUMED`).
3. REFEREE #2 FATAL OBJECTION (`referee2_premortem`): Strictly **2 crisp sentences** stating the sharpest theoretical rejection objection.
4. CANDIDATE PIVOTS (`pivot_options`): Propose 2-3 sharper conjectures, tighter bounds, or narrower theorem targets (all will be red-teamed in Phase 2).
Set `fatal_blocker_count` to the count of scoop/folklore/subsumption showstoppers.""",
    },
    "engineering_portfolio": {
        "baseline_feasibility_killer": """You are a hostile staff-engineer / applied-science reviewer on track=`engineering_portfolio`.
Academic novelty is NOT a hard kill gate here — **mathematical validity, zero data leakage, domain realism, and beating/matching standard practitioner baselines ARE hard kill gates**.
1. STANDARD PRACTITIONER BASELINE (populate `strongest_cheap_baseline`): What is the simplest off-the-shelf library call or simple single-file textbook baseline (<= ~50 lines / <= 1 hour using standard packages) a strong practitioner would deploy first?
2. DATA LEAKAGE & EVALUATION-HYGIENE AUDIT: Check aggressively for train/test leakage, temporal/group/target leakage, look-ahead bias, improper cross-validation, cherry-picked splits, or unrealistic synthetic assumptions.
3. DOMAIN REALISM & OPERATIONAL FEASIBILITY: Flag unrealistic latency/memory/data-availability assumptions, brittle hand-tuned thresholds, or evaluation metrics misaligned with real deployment value.
4. DAY-1 FALSIFICATION PILOTS (populate `day1_pilots`): Design 2-3 concrete 24-48h leakage-free benchmark tests (1 sanity/invariant check + 1 realistic non-toy stress split) comparing directly against the standard practitioner baseline with explicit **Kill / Pivot / Build** thresholds.
Set `fatal_blocker_count` to the count of unresolved validity, leakage, realism, or baseline-competitiveness blockers.""",
        "theory_limits_critic": """You are a rigorous applied-math / statistical-validity critic on track=`engineering_portfolio`.
1. MATHEMATICAL & STATISTICAL VALIDITY: Check objective formulations, estimator bias/variance, uncertainty quantification, identifiability, and metric validity (no broken approximations or invalid statistical tests).
2. LEAKAGE, SHIFT & SCALING LIMITS: Check distribution shift, out-of-sample generalization, class imbalance, numerical stability, and end-to-end latency/memory bottlenecks at realistic data scale.
3. PREDICTED FAILURE-MODE MAP (populate `predicted_failure_modes` with concise IDs `FM-1`, `FM-2`, ...): Exact regimes where the pipeline fails silently, overfits, leaks, or loses to simple heuristics.
Set `fatal_blocker_count` to the count of unresolved mathematical-validity or leakage showstoppers.""",
        "literature_novelty_strategist": f"""You are a senior applied-science mentor on track=`engineering_portfolio` conducting a LIVE landscape & open-source scan.
IMPORTANT TRACK RULE: Academic novelty is a **SECONDARY NOTE** (NOT a hard kill gate). Do NOT set `fatal_blocker_count > 0` merely because similar methods exist — flag fatal blockers ONLY if an existing off-the-shelf tool/repo strictly dominates the exact proposed artifact with zero differentiation or if the core premise is debunked.
LIVE SEARCH (STRICTLY READ-ONLY — `search_web` ONLY, NO FILE EDITS, NO SHELL):
- Run 5-8 targeted `search_web` queries covering ({SEARCH_WINDOW}):
  (a) Existing production libraries, open-source repos, and standard practitioner benchmarks in `{domain}`,
  (b) Known failure modes, leakage pitfalls, or benchmark critiques in this problem space, and
  (c) High-signal practical differentiators (reliability, domain realism, ablations, clean engineering).
- Set `live_search_status` to `searched_live`, `used_supplied_brief`, or `blocked_or_offline` (if running in an offline `research` sandbox without `search_web`, rely on any supplied `prior_art_summary` / `seed_papers` and NEVER report `searched_live`). Cite ONLY verified papers/repos with real URLs/IDs.{CUTOFF_DIRECTIVE}
DELIVERABLES:
1. LANDSCAPE & PRIOR-TOOL MAP (`prior_art_hits`, `cross_field_translations`).
2. DIFFERENTIATION & NOVELTY NOTE: Set `novelty_verdict` honestly as an informational note, and state the sharpest practical value proposition in `irreducible_novelty_wedge`.
3. CRITIC'S FATAL OBJECTION (`referee2_premortem`): Strictly **2 crisp sentences** stating the sharpest hiring-manager / senior-practitioner skepticism.
4. CANDIDATE PIVOTS (`pivot_options`): Propose 2-3 concrete ways to sharpen realism, benchmark rigor, or practical impact (all will be red-teamed in Phase 2).""",
    },
}

COMMON_RULES = """GROUND RULES (MANDATORY):
1. ZERO PROSE OR FORMATTING NITPICKS: Focus 100% on scientific validity, baselines, theory/limits, and literature/landscape accuracy.
2. NEVER FABRICATE PAPERS, NUMBERS, OR THEOREMS: Cite only verified sources from live `search_web`, `seed_papers`, or `idea_files` (with real arXiv IDs/DOIs/URLs). Mark speculation explicitly as "Hypothesis:" or "Possibility:".
3. ANTI-SYCOPHANCY: Do not praise or soften flaws; kill weak premises early or specify concrete falsification bars.
4. BE CONCISE & NON-REPETITIVE: State each mechanism cleanly once; avoid repeating the same point across fields.
5. READ-ONLY & INDEPENDENT: Never edit/write project files and never run shell commands (`run_command`). Return structured JSON via `finish`."""

SCOUTS = [
    {
        "id": "baseline_feasibility_killer",
        "role": f"Scout 1 ({track}): Baseline Killer & Day-1 Falsification Designer",
        "focus": TRACK_SCOUT_PROMPTS[track]["baseline_feasibility_killer"],
    },
    {
        "id": "theory_limits_critic",
        "role": f"Scout 2 ({track}): Theoretical Viability, Validity & Failure-Mode Critic",
        "focus": TRACK_SCOUT_PROMPTS[track]["theory_limits_critic"],
    },
    {
        "id": "literature_novelty_strategist",
        "role": f"Scout 3 ({track}): Live Literature, Cross-Field & Pivot Strategist",
        "focus": TRACK_SCOUT_PROMPTS[track]["literature_novelty_strategist"],
    },
]


def build_schema(scout_id: str):
    props = {
        "scout_id": {"type": "string"},
        "scout_role": {"type": "string"},
        "summary": {"type": "string"},
        "fatal_blocker_count": {"type": "integer", "minimum": 0},
        "key_risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["fatal", "major", "minor"]},
                    "category": {"type": "string"},
                    "risk": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "concrete_check_or_question": {"type": "string"},
                },
                "required": ["severity", "category", "risk", "why_it_matters", "concrete_check_or_question"],
            },
        },
    }
    req = ["scout_id", "scout_role", "summary", "fatal_blocker_count", "key_risks"]

    if scout_id == "baseline_feasibility_killer":
        props["strongest_cheap_baseline"] = {"type": "string"}
        props["repair_vs_discovery_assessment"] = {"type": "string"}
        props["day1_pilots"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "is_non_toy": {"type": "boolean"},
                    "test_setup": {"type": "string"},
                    "cheap_baseline_to_beat": {"type": "string"},
                    "kill_criterion": {"type": "string"},
                    "build_criterion": {"type": "string"},
                },
                "required": ["name", "is_non_toy", "test_setup", "cheap_baseline_to_beat", "kill_criterion", "build_criterion"],
            },
        }
        req.extend(["strongest_cheap_baseline", "day1_pilots"])
    elif scout_id == "theory_limits_critic":
        props["scaling_and_bounds_summary"] = {"type": "string"}
        props["end_to_end_cost_shifting"] = {"type": "string"}
        props["predicted_failure_modes"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "regime": {"type": "string"},
                    "failure_mechanism": {"type": "string"},
                    "diagnostic_test": {"type": "string"},
                },
                "required": ["id", "regime", "failure_mechanism", "diagnostic_test"],
            },
        }
        req.extend(["scaling_and_bounds_summary", "predicted_failure_modes"])
    elif scout_id == "literature_novelty_strategist":
        props["live_search_status"] = {
            "type": "string",
            "enum": ["searched_live", "used_supplied_brief", "blocked_or_offline"],
        }
        props["novelty_verdict"] = {
            "type": "string",
            "enum": [
                "CLEAR_NOVELTY_ABOVE_BAR",
                "BORDERLINE_NEEDS_SHARPER_WEDGE",
                "LIKELY_SCOOPED_OR_SUBSUMED",
            ],
        }
        props["irreducible_novelty_wedge"] = {"type": "string"}
        props["prior_art_hits"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "citation_and_id": {"type": "string"},
                    "url": {"type": "string"},
                    "field": {"type": "string"},
                    "overlap_level": {"type": "string", "enum": ["direct_scoop_risk", "substantial_overlap", "adjacent_foundation"]},
                    "what_remains_open": {"type": "string"},
                },
                "required": ["citation_and_id", "field", "overlap_level", "what_remains_open"],
            },
        }
        props["cross_field_translations"] = {"type": "array", "items": {"type": "string"}}
        props["referee2_premortem"] = {"type": "string"}
        props["pivot_options"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pivot_title": {"type": "string"},
                    "core_twist": {"type": "string"},
                    "why_stronger": {"type": "string"},
                    "theorem_or_experiment_hook": {"type": "string"},
                },
                "required": ["pivot_title", "core_twist", "why_stronger", "theorem_or_experiment_hook"],
            },
        }
        req.extend([
            "live_search_status",
            "novelty_verdict",
            "irreducible_novelty_wedge",
            "prior_art_hits",
            "referee2_premortem",
            "pivot_options",
        ])

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


active_scouts = [s for s in SCOUTS if not selected_ids or s["id"] in set(selected_ids)]
if not active_scouts:
    raise ValueError(f"No matching scouts in {selected_ids}. Valid IDs: {[s['id'] for s in SCOUTS]}")


def build_inputs_block():
    lines = [
        f"Evaluation track: {track} ({track_source})",
        f"Research domain: {domain}",
    ]
    if target_venue:
        lines.append(f"Target venue: {target_venue}")
    if context:
        lines.append(f"Additional constraints/context: {context}")
    if ACTIVE_OVERLAY_MD:
        lines.append("Optional local lab/domain overlay priors:\n---\n" + ACTIVE_OVERLAY_MD + "\n---")
    if idea_text:
        lines.append("IDEA PITCH / HYPOTHESIS:\n---\n" + idea_text + "\n---")
    if idea_files:
        lines.append("Idea notes / equation / draft file(s) to read:")
        for p in idea_files:
            lines.append(f"  - {p}")
    if seed_papers:
        lines.append("User-provided seed paper(s) already known:")
        for p in seed_papers:
            lines.append(f"  - {p}")
    if prior_art_summary:
        lines.append(
            "Supplied prior-art brief (if file path, read it; otherwise treat as text — never invent citations):\n"
            + prior_art_summary
        )
    if previous_screen:
        lines.append(
            "Previous screening brief (Pivot Round 2 — if file path, read it; otherwise treat as text; "
            "verify whether prior blockers/overlaps are resolved):\n"
            + previous_screen
        )
    return "\n".join(lines)


inputs_block = build_inputs_block()


def build_prompt(scout):
    return (
        f"You are {scout['role']} (scout_id='{scout['id']}').\n"
        f"Task: Independently screen this pre-code research idea on track='{track}'.\n\n"
        f"{inputs_block}\n\n"
        f"{COMMON_RULES}\n\n"
        f"YOUR SPECIFIC SCREENING SCOPE:\n{scout['focus']}\n\n"
        f"Return your structured JSON via `finish` with scout_id='{scout['id']}' and scout_role='{scout['role']}'."
    )


def _extract_derived_constraints(scout_results):
    """Distill compact baseline & theoretical constraints proved in Phase 1 (blind to Pivot rationale)."""
    lines = []
    for r in scout_results:
        sid = r.get("scout_id", "")
        if sid == "baseline_feasibility_killer":
            if r.get("strongest_cheap_baseline"):
                lines.append(f"- Baseline constraint (Scout 1): {r['strongest_cheap_baseline']}")
            if r.get("repair_vs_discovery_assessment"):
                lines.append(f"- Repair-vs-Discovery note: {r['repair_vs_discovery_assessment']}")
        elif sid == "theory_limits_critic":
            if r.get("scaling_and_bounds_summary"):
                lines.append(f"- Scaling/bounds constraint (Scout 2): {r['scaling_and_bounds_summary']}")
            if r.get("end_to_end_cost_shifting"):
                lines.append(f"- End-to-end cost constraint: {r['end_to_end_cost_shifting']}")
            for fm in r.get("predicted_failure_modes", [])[:6]:
                lines.append(
                    f"- Failure mode [{fm.get('id', 'FM')}] ({fm.get('regime', '')}): {fm.get('failure_mechanism', '')}"
                )
        for kr in r.get("key_risks", []):
            if kr.get("severity") in ("fatal", "major"):
                lines.append(f"- [{sid} {kr.get('severity')}] {kr.get('risk', '')}")
    return "\n".join(lines) if lines else "- None extracted from Phase 1."


def _format_candidate_pivots(raw_pivots):
    """Strip sales prose so the red-teamer audits only the concrete Pivot spec."""
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


def build_pivot_red_team_prompt(pivots_block: str, constraints_block: str, prt_agent_type: str):
    baseline_rule = {
        "numerical_algorithm": "the strongest cheap baseline — a minimal patch (~5-20 lines), off-the-shelf library call, or simple single-file textbook baseline (<= ~50 lines / <= 1 hour, e.g., CRN, control variates, sorting, warm-start, standard heuristic)",
        "pure_theory": "the single tightest known theorem, no-go bound, textbook inequality, or 3-line classical reduction",
        "engineering_portfolio": "the simplest off-the-shelf practitioner library call or simple single-file heuristic baseline (<= ~50 lines using standard packages)",
    }[track]
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
            f"Audit prior-art overlap ({SEARCH_WINDOW}) strictly using the supplied prior-art brief and attached files. "
            "NEVER report `searched_live`; set `live_search_status` to `used_supplied_brief` (when auditing against "
            "the supplied brief), `skipped_all_dropped` (when all Pivots fail math/baseline triage), or "
            f"`blocked_or_offline` (when no brief is supplied and live search is required). Cite only verified IDs/URLs.{CUTOFF_DIRECTIVE}\n\n"
        )
    else:
        search_block = (
            f"LIVE SEARCH (READ-ONLY — `search_web` ONLY, NO FILE EDITS, NO SHELL): Run 1-2 targeted `search_web` "
            f"queries ({SEARCH_WINDOW}) per Pivot that passes initial math/baseline triage to check prior-art overlap "
            "in the Pivot's OWN target subfield (also honoring any supplied prior-art brief; skip search for obvious "
            "`DROP_PIVOT`s; set `live_search_status` to `searched_live`, `used_supplied_brief`, "
            f"`skipped_all_dropped`, or `blocked_or_offline`; cite only verified IDs/URLs).{CUTOFF_DIRECTIVE}\n\n"
        )
    return (
        f"You are the Blind Pivot Red-Team Auditor (1-round bounded check, track='{track}').\n"
        "Mission: Adversarially audit EVERY candidate Pivot below BEFORE any Pivot is recommended. "
        "Kill any Pivot that falls to a trivial baseline, is already scooped in its own subfield, or "
        "contradicts algebraic, statistical, scaling, or conservation constraints established below. "
        "Returning 0 survivors (all `DROP_PIVOT`) is completely valid and expected when all Pivots fail — "
        "never force a survivor or rescue a dead algorithm as a generic 'benchmark/phase-diagram' study "
        "unless prior-art search proves no existing critique subsumes it.\n"
        + search_block
        + f"Research domain: {domain}\n"
        f"Track: {track}\n"
        + (f"Target venue: {target_venue}\n" if target_venue else "")
        + brief_ctx
        + (f"Original idea summary:\n{idea_text[:1800]}\n\n" if idea_text else "")
        + f"DERIVED CONSTRAINTS FROM PHASE 1 (check every Pivot for self-contradiction against these):\n"
        f"{constraints_block}\n\n"
        f"CANDIDATE PIVOTS TO AUDIT:\n{pivots_block}\n\n"
        f"{COMMON_RULES}\n\n"
        "REQUIRED AUDIT ROW FOR EVERY CANDIDATE PIVOT (populate `pivot_audit` with exact matching `pivot_title`):\n"
        f"1. `strongest_cheap_baseline`: {baseline_rule} that could kill or shrink this Pivot.\n"
        "2. `primary_math_or_scaling_trap`: Sharpest math, statistical, leakage, self-consistency, or prior-art overlap trap.\n"
        "3. `pivot_verdict`: Strictly one of:\n"
        "   - `SURVIVES_RED_TEAM` (unchanged mechanism passes prior-art check, cheap baseline, and Phase 1 constraints)\n"
        "   - `VIABLE_WITH_PATCH` (STRICTLY a single-sentence scope/parameter trim introducing ZERO new math objects, estimators, or domains, and passing prior-art check)\n"
        "   - `NEEDS_FRESH_SCREEN` (salvaging requires a new mechanism, domain switch, or >=2 bundled fixes — unvetted; must undergo a fresh blind Day-0 screen before coding)\n"
        "   - `DROP_PIVOT` (killed by cheap baseline, prior-art scoop, leakage, or Phase 1 constraints)\n"
        "4. `one_line_patch`: Single-sentence trim for `VIABLE_WITH_PATCH`, brief unvetted direction for `NEEDS_FRESH_SCREEN`, or `'N/A'` for `SURVIVES_RED_TEAM`/`DROP_PIVOT`.\n"
        "5. `design_space_constraints`: Populate with 3-4 concise necessary conditions ONLY when 0 Pivots earn `SURVIVES_RED_TEAM` or `VIABLE_WITH_PATCH` (otherwise `[]`) — strictly inverted from Phase 1/2 findings without pitching an unvetted 4th Pivot: (a) baseline floor to beat, (b) non-negotiable math/scaling/validity invariants, (c) verified open literature window, and (d) 1-line whiteboard litmus check. Keep tone colleague-safe and constructive toward the design space while staying 100% strict on verdicts.\n"
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


# --- Phase 1: Parallel Blind Scouts ---

phase(f"Phase 1: Idea Screen — track={track} ({len(active_scouts)} Blind Scouts)")
routed = [f"{s['id']}[{resolve_agent_type(s['id'])}]" for s in active_scouts]
log(
    f"Track={track} ({track_source}), overlay_cfg={LOCAL_CFG_SOURCE or 'none'}, "
    f"overlay_md={LOCAL_OVERLAY_SOURCE or 'none'}. Launching: " + ", ".join(routed)
)

results = await parallel(
    active_scouts,
    lambda s: agent(
        prompt=build_prompt(s),
        schema=build_schema(s["id"]),
        role=s["role"],
        type_name=resolve_agent_type(s["id"]),
        model=model,
    ),
)

log(f"Completed Phase 1 ({len(results)} blind scout(s)).")

# --- Phase 2: Bounded 1-Round Blind Pivot Red-Team Mini-Pass ---

lit = next((r for r in results if r.get("scout_id") == "literature_novelty_strategist"), {})
_enforce_offline_search_status(
    lit, resolve_agent_type("literature_novelty_strategist"), bool(prior_art_summary), "literature_novelty_strategist"
)
raw_pivots = explicit_pivots if explicit_pivots is not None else lit.get("pivot_options", [])
pivot_red_team = None

if not skip_pivot_red_team and raw_pivots:
    phase(f"Phase 2: Bounded 1-Round Pivot Red-Team ({len(raw_pivots)} Candidate Pivot(s))")
    constraints_block = _extract_derived_constraints(results)
    pivots_block = _format_candidate_pivots(raw_pivots)
    prt_agent_type = "self" if agent_type_override in ("", "auto") else agent_type_override
    mode_desc = (
        "with supplied prior-art brief (offline)"
        if (prt_agent_type == "research" and prior_art_summary)
        else ("in offline sandbox" if prt_agent_type == "research" else "with live search")
    )
    log(f"Red-teaming {len(raw_pivots)} candidate pivot(s) in isolated context {mode_desc}.")
    pivot_red_team = await agent(
        prompt=build_pivot_red_team_prompt(pivots_block, constraints_block, prt_agent_type),
        schema=PIVOT_RED_TEAM_SCHEMA,
        role=f"Pivot Red-Team Auditor ({track}, 1-Round)",
        type_name=prt_agent_type,
        model=model,
    )
    _enforce_offline_search_status(
        pivot_red_team, prt_agent_type, bool(prior_art_summary), "pivot_red_team"
    )
    log(f"Completed Phase 2 Pivot Red-Team ({len(pivot_red_team.get('pivot_audit', []))} row(s)).")

# --- Compute Top-Level Go / Pivot / Kill Gate ---

total_fatal = sum(int(r.get("fatal_blocker_count", 0)) for r in results)
nov_verdict = lit.get("novelty_verdict", "not_evaluated")
live_search_status = lit.get("live_search_status", "not_evaluated")
phase2_live_search_status = (
    pivot_red_team.get("live_search_status", "not_evaluated") if pivot_red_team is not None else "not_run"
)
novelty_is_hard_gate = track != "engineering_portfolio"
search_verification_required = (
    live_search_status in ("blocked_or_offline", "not_evaluated")
    or phase2_live_search_status == "blocked_or_offline"
)

if total_fatal >= 2 or (novelty_is_hard_gate and nov_verdict == "LIKELY_SCOOPED_OR_SUBSUMED"):
    recommendation = "KILL_OR_REFRAME"
elif total_fatal == 1 or (novelty_is_hard_gate and nov_verdict == "BORDERLINE_NEEDS_SHARPER_WEDGE"):
    recommendation = "PIVOT_BEFORE_CODING"
elif novelty_is_hard_gate and live_search_status in ("blocked_or_offline", "not_evaluated"):
    recommendation = "NEEDS_LIVE_SEARCH_VERIFICATION"
else:
    recommendation = "PROCEED_TO_PROTOTYPE"

pivot_rows = (pivot_red_team or {}).get("pivot_audit", [])
pivot_counts = {
    "audited": len(pivot_rows),
    "survives_red_team": sum(1 for row in pivot_rows if row.get("pivot_verdict") == "SURVIVES_RED_TEAM"),
    "viable_with_patch": sum(1 for row in pivot_rows if row.get("pivot_verdict") == "VIABLE_WITH_PATCH"),
    "needs_fresh_screen": sum(1 for row in pivot_rows if row.get("pivot_verdict") == "NEEDS_FRESH_SCREEN"),
    "dropped": sum(1 for row in pivot_rows if row.get("pivot_verdict") == "DROP_PIVOT"),
}

screen_gate = {
    "track": track,
    "track_source": track_source,
    "recommendation": recommendation,
    "novelty_gate_mode": "hard_gate" if novelty_is_hard_gate else "secondary_note",
    "novelty_verdict": nov_verdict,
    "total_fatal_blockers": total_fatal,
    "live_search_status": live_search_status,
    "phase2_live_search_status": phase2_live_search_status,
    "search_verification_required": search_verification_required,
    "pivot_red_team_counts": pivot_counts,
}
log(f"Idea Screen Gate: {screen_gate}")

output = {
    "track": track,
    "track_source": track_source,
    "domain": domain,
    "target_venue": target_venue,
    "cutoff_year": cutoff_year,
    "search_window": SEARCH_WINDOW,
    "local_overlay_loaded": {
        "config": LOCAL_CFG_SOURCE,
        "markdown": LOCAL_OVERLAY_SOURCE,
        "applied": OVERLAY_APPLIED,
        "skipped_reason": OVERLAY_SKIP_REASON,
    },
    "scouts_run": [s["id"] for s in active_scouts],
    "scout_agent_types": {s["id"]: resolve_agent_type(s["id"]) for s in active_scouts},
    "screen_gate": screen_gate,
    "results": results,
    "pivot_red_team": pivot_red_team,
}
print(json.dumps(output, indent=2))
