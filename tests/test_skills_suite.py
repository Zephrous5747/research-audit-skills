"""Fast (<5 s, zero-LLM) regression tests for the Research Audit Skill Suite."""

import ast
import asyncio
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

SUITE_ROOT = Path(__file__).resolve().parents[1]
SCREEN_SCRIPT = SUITE_ROOT / "idea-novelty-screen" / "scripts" / "screen_idea.py"
REVIEW_SCRIPT = SUITE_ROOT / "scientific-report-review" / "scripts" / "review_panel.py"
LINTER_SCRIPT = SUITE_ROOT / "scientific-report-review" / "scripts" / "preflight_lint.py"


def _load_linter():
    spec = importlib.util.spec_from_file_location("preflight_lint", str(LINTER_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_workflow_script(script_path: Path, args_dict: dict, fake_agent_fn, monkeypatch, cwd=None):
    """Execute a top-level-await workflow script locally with mocked workflow primitives."""
    src = script_path.read_text(encoding="utf-8")
    # Wrap top-level await script into an async function for deterministic unit testing
    indented = "\n".join("    " + line for line in src.splitlines())
    wrapped = "async def _workflow_main():\n" + indented + "\n"
    code_obj = compile(wrapped, str(script_path), "exec")

    logs = []

    def _log(*parts):
        logs.append(" ".join(str(p) for p in parts))

    def _phase(name):
        logs.append(f"[PHASE] {name}")

    def _agent(prompt=None, schema=None, role=None, type_name="self", workspace="inherit", model=None):
        async def _coro():
            return fake_agent_fn(prompt=prompt, schema=schema, role=role, type_name=type_name, model=model)

        return _coro()

    async def _parallel(items, fn):
        return await asyncio.gather(*(fn(item) for item in items))

    ns = {
        "__file__": str(script_path),
        "args": args_dict,
        "log": _log,
        "phase": _phase,
        "agent": _agent,
        "parallel": _parallel,
    }
    if cwd is not None:
        monkeypatch.chdir(cwd)
    exec(code_obj, ns)
    buf = io.StringIO()
    with redirect_stdout(buf):
        asyncio.run(ns["_workflow_main"]())
    return json.loads(buf.getvalue()), logs


# --- 1. Syntax & Schema Integrity ---


@pytest.mark.parametrize("script_path", [SCREEN_SCRIPT, REVIEW_SCRIPT])
def test_async_compile_and_pivot_red_team_schema(script_path):
    src = script_path.read_text(encoding="utf-8")
    compile(src, str(script_path), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    tree = ast.parse(src)
    assigns = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "PIVOT_RED_TEAM_SCHEMA" for t in n.targets)
    ]
    assert len(assigns) == 1
    schema = ast.literal_eval(assigns[0].value)
    assert set(schema["required"]) >= {"live_search_status", "summary", "pivot_audit", "design_space_constraints"}
    assert schema["properties"]["live_search_status"]["enum"] == [
        "searched_live",
        "used_supplied_brief",
        "skipped_all_dropped",
        "blocked_or_offline",
    ]
    verdict_enum = schema["properties"]["pivot_audit"]["items"]["properties"]["pivot_verdict"]["enum"]
    assert verdict_enum == ["SURVIVES_RED_TEAM", "VIABLE_WITH_PATCH", "NEEDS_FRESH_SCREEN", "DROP_PIVOT"]


# --- 2. screen_idea.py Fail-Closed Gates & Phase 2 Search Propagation ---


def test_screen_idea_blocks_proceed_when_search_offline(tmp_path, monkeypatch):
    def fake_agent(prompt, schema, role, type_name, model):
        if "Pivot Red-Team" in (role or ""):
            assert type_name == "self"
            return {
                "live_search_status": "blocked_or_offline",
                "summary": "Offline in test",
                "pivot_audit": [
                    {
                        "pivot_title": "P1",
                        "strongest_cheap_baseline": "B",
                        "primary_math_or_scaling_trap": "T",
                        "pivot_verdict": "DROP_PIVOT",
                        "one_line_patch": "N/A",
                    }
                ],
                "design_space_constraints": ["Must beat B."],
            }
        if "scout_id='literature_novelty_strategist'" in prompt:
            return {
                "scout_id": "literature_novelty_strategist",
                "scout_role": role,
                "summary": "s",
                "fatal_blocker_count": 0,
                "key_risks": [],
                "live_search_status": "blocked_or_offline",
                "novelty_verdict": "CLEAR_NOVELTY_ABOVE_BAR",
                "irreducible_novelty_wedge": "w",
                "prior_art_hits": [],
                "referee2_premortem": "Two sentences.",
                "pivot_options": [{"pivot_title": "P1", "core_twist": "t", "why_stronger": "w", "theorem_or_experiment_hook": "h"}],
            }
        sid = "baseline_feasibility_killer" if "baseline_feasibility_killer" in prompt else "theory_limits_critic"
        out = {
            "scout_id": sid,
            "scout_role": role,
            "summary": "ok",
            "fatal_blocker_count": 0,
            "key_risks": [],
        }
        if sid == "baseline_feasibility_killer":
            out.update({"strongest_cheap_baseline": "b", "day1_pilots": []})
        else:
            out.update({"scaling_and_bounds_summary": "s", "predicted_failure_modes": []})
        return out

    data, _ = _run_workflow_script(
        SCREEN_SCRIPT,
        {"track": "numerical_algorithm", "idea": "Fast Monte Carlo estimator with low variance"},
        fake_agent,
        monkeypatch,
        cwd=tmp_path,
    )
    gate = data["screen_gate"]
    assert gate["recommendation"] == "NEEDS_LIVE_SEARCH_VERIFICATION"
    assert gate["search_verification_required"] is True
    assert gate["phase2_live_search_status"] == "blocked_or_offline"
    assert gate["pivot_red_team_counts"]["dropped"] == 1
    assert gate["pivot_red_team_counts"]["needs_fresh_screen"] == 0


def test_screen_idea_phase2_offline_triggers_search_flag(tmp_path, monkeypatch):
    def fake_agent(prompt, schema, role, type_name, model):
        if "Pivot Red-Team" in (role or ""):
            return {
                "live_search_status": "blocked_or_offline",
                "summary": "offline",
                "pivot_audit": [],
                "design_space_constraints": [],
            }
        if "scout_id='literature_novelty_strategist'" in prompt:
            return {
                "scout_id": "literature_novelty_strategist",
                "scout_role": role,
                "summary": "s",
                "fatal_blocker_count": 0,
                "key_risks": [],
                "live_search_status": "searched_live",
                "novelty_verdict": "CLEAR_NOVELTY_ABOVE_BAR",
                "irreducible_novelty_wedge": "w",
                "prior_art_hits": [],
                "referee2_premortem": "Two sentences.",
                "pivot_options": [{"pivot_title": "P1", "core_twist": "t", "why_stronger": "w", "theorem_or_experiment_hook": "h"}],
            }
        sid = "baseline_feasibility_killer" if "baseline_feasibility_killer" in prompt else "theory_limits_critic"
        out = {"scout_id": sid, "scout_role": role, "summary": "ok", "fatal_blocker_count": 0, "key_risks": []}
        if sid == "baseline_feasibility_killer":
            out.update({"strongest_cheap_baseline": "b", "day1_pilots": []})
        else:
            out.update({"scaling_and_bounds_summary": "s", "predicted_failure_modes": []})
        return out

    data, _ = _run_workflow_script(
        SCREEN_SCRIPT,
        {"track": "engineering_portfolio", "idea": "Build a benchmark pipeline"},
        fake_agent,
        monkeypatch,
        cwd=tmp_path,
    )
    assert data["screen_gate"]["recommendation"] == "PROCEED_TO_PROTOTYPE"
    assert data["screen_gate"]["search_verification_required"] is True


# --- 3. review_panel.py Fail-Closed Gates, Required Schemas & Stage 2 Rules ---


def test_review_panel_stage0_blocked_by_permission_fails_closed(tmp_path, monkeypatch):
    def fake_agent(prompt, schema, role, type_name, model):
        assert type_name == "self"
        return {
            "reviewer_id": "code_math_auditor",
            "reviewer_role": role,
            "summary": "Static clean, shell blocked.",
            "findings": [],
            "stage0_verdict": "ALIGNED_FAIL_LOUD",
            "p0_p1_count": 0,
            "stage0_closed": True,
            "execution_status": "blocked_by_permission",
        }

    data, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {"stage": "stage0", "report_text": "Spec text"},
        fake_agent,
        monkeypatch,
        cwd=tmp_path,
    )
    assert data["stage0_gate"]["stage0_closed"] is False
    assert "STATIC_ALIGNED_RUN_SMOKE_IN_MAIN" in data["stage0_gate"]["next_action"]
    assert data["stage_gate"]["ready_to_advance"] is False


def test_review_panel_stage1_combined_gate_and_r9_required_fields(tmp_path, monkeypatch):
    seen_schemas = {}

    def fake_agent(prompt, schema, role, type_name, model):
        if "Pivot Red-Team" in (role or ""):
            assert type_name == "self"
            return {
                "live_search_status": "skipped_all_dropped",
                "summary": "All dropped on math.",
                "pivot_audit": [
                    {
                        "pivot_title": "P1",
                        "strongest_cheap_baseline": "B",
                        "primary_math_or_scaling_trap": "T",
                        "pivot_verdict": "DROP_PIVOT",
                        "one_line_patch": "N/A",
                    }
                ],
                "design_space_constraints": ["Must beat B."],
            }
        if "reviewer_id='baseline_killer'" in prompt:
            return {
                "reviewer_id": "baseline_killer",
                "reviewer_role": role,
                "summary": "Solid",
                "findings": [],
                "baseline_verdict": "SOLID_BASELINE",
                "p0_p1_count": 0,
                "stage1a_closed": True,
            }
        if "reviewer_id='theory_mechanism_critic'" in prompt:
            return {"reviewer_id": "theory_mechanism_critic", "reviewer_role": role, "summary": "Ok", "findings": []}
        seen_schemas["r9"] = schema
        return {
            "reviewer_id": "supervisor_strategist",
            "reviewer_role": role,
            "summary": "Overlap found",
            "findings": [],
            "live_search_status": "searched_live",
            "novelty_assessment": {
                "novelty_verdict": "OVERLAP_OR_INCREMENTAL_RISK",
                "target_venue_bar_analysis": "Below bar",
                "irreducible_new_idea": "None",
                "contributions": [],
            },
            "candidate_pivots": [{"pivot_title": "P1", "core_twist": "t", "theorem_or_experiment_hook": "h"}],
        }

    data, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {"stage": "stage1", "report_text": "Draft text"},
        fake_agent,
        monkeypatch,
        cwd=tmp_path,
    )
    assert set(seen_schemas["r9"]["required"]) >= {"live_search_status", "novelty_assessment"}
    assert data["stage1a_gate"]["closed"] is True
    assert data["stage_gate"]["ready_to_advance"] is False
    assert "novelty_verdict=OVERLAP_OR_INCREMENTAL_RISK" in data["stage_gate"]["blocking_reasons"]


def test_review_panel_stage2_prompts_schemas_and_recheck_diff_warning(tmp_path, monkeypatch):
    seen = {}

    def fake_agent(prompt, schema, role, type_name, model):
        for rid in (
            "structure_narrative",
            "reproducibility_code",
            "claims_definitions",
            "prose_style",
            "figures_refs_format",
            "conciseness_editor",
        ):
            if f"reviewer_id='{rid}'" in prompt:
                seen[rid] = (prompt, schema)
                res = {
                    "reviewer_id": rid,
                    "reviewer_role": role,
                    "domain_verdict": "ready_to_share",
                    "p0_p1_count": 0,
                    "summary": "ok",
                    "prior_issue_assessments": [],
                    "remaining_or_new_findings": [],
                }
                if rid == "reproducibility_code":
                    res["reproducibility_rating"] = "insufficient"
                if rid == "claims_definitions":
                    res["conclusion_support_assessments"] = []
                if rid == "conciseness_editor":
                    res["compression_ledger"] = []
                return res
        raise AssertionError(f"Unexpected role {role}")

    data, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {
            "stage": "stage2",
            "mode": "recheck",
            "previous_review": "prior",
            "diff_file": "missing_diff.patch",
            "report_text": "Revised text",
        },
        fake_agent,
        monkeypatch,
        cwd=tmp_path,
    )
    # R1 prompt has specimen_openings carve-out; R10 no longer checks Abstract >2 baselines
    assert "specimen_openings" in seen["structure_narrative"][0]
    assert "Flag >2 distinct baselines" not in seen["conciseness_editor"][0]
    # Required role deliverables enforced
    assert "reproducibility_rating" in seen["reproducibility_code"][1]["required"]
    assert "conclusion_support_assessments" in seen["claims_definitions"][1]["required"]
    assert "compression_ledger" in seen["conciseness_editor"][1]["required"]
    # Fail-closed on insufficient reproducibility & fail-loud on missing diff_file
    assert data["stage_gate"]["ready_to_advance"] is False
    assert "reproducibility_rating=insufficient" in data["stage_gate"]["blocking_reasons"]
    assert any("diff_file not found" in w for w in data["stage_gate"]["diff_warnings"])


def test_review_panel_stage2_review_prompts_and_overlay_injection(tmp_path, monkeypatch):
    overlay_dir = tmp_path / ".agents" / "skills"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / "local_overlay.md").write_text("Custom lab style prior: use vector EPS.\n", encoding="utf-8")
    extra_code = tmp_path / "secret_code.py"
    extra_code.write_text("try:\n    x = 1\nexcept:\n    pass\n", encoding="utf-8")

    seen = {}
    seen_models = {}
    seen_schemas = {}

    def fake_agent(prompt, schema, role, type_name, model):
        for rid in (
            "structure_narrative",
            "reproducibility_code",
            "claims_definitions",
            "prose_style",
            "figures_refs_format",
            "conciseness_editor",
            "average_reader",
        ):
            if f"reviewer_id='{rid}'" in prompt:
                seen[rid] = prompt
                seen_models[rid] = model
                seen_schemas[rid] = schema
                res = {"reviewer_id": rid, "reviewer_role": role, "summary": "ok", "findings": []}
                if rid == "reproducibility_code":
                    res["reproducibility_rating"] = "sufficient"
                if rid == "conciseness_editor":
                    res["compression_ledger"] = []
                if rid == "average_reader":
                    res["plain_english_reconstruction"] = {
                        "problem": "p",
                        "prior_work_vs_new_delta_from_abstract": "delta",
                        "method_steps": "m",
                        "headline_result_and_baseline": "h",
                        "main_limitation": "l",
                    }
                    res["walkout_point"] = {
                        "location": "Sec 2.2",
                        "trigger": "10-line algebra wall",
                        "why_reader_stops_linear_reading": "No plain-English summary before derivation",
                    }
                    res["friction_hotspots"] = [
                        {
                            "location": "Sec 2.2",
                            "friction_type": "math_wall_no_intuition",
                            "quote_or_cue": "Eqs. (4)-(9)",
                            "why_it_breaks_flow": "Reader loses the story when skipping equations",
                            "suggested_story_fix": "Add 1-sentence intuition before Eq. (4) and move steps to SI",
                        }
                    ]
                    res["where_i_got_lost_or_bored"] = [
                        {"location": "Sec 2", "confusion_or_guess": "g", "what_is_missing": "x"}
                    ]
                    # Advisory reviewer must NOT auto-block stage_gate even if it tags an item essential
                    res["findings"] = [
                        {
                            "priority": "essential",
                            "category": "clarity",
                            "location": "Sec 2",
                            "issue": "Lost here",
                            "why_it_matters": "Bored",
                            "author_question_or_placeholder": "Clarify",
                        }
                    ]
                return res
        raise AssertionError(f"Unexpected role {role}")

    data, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {
            "stage": "stage2",
            "mode": "review",
            "report_text": "Draft text",
            "extra_files": [str(extra_code)],
        },
        fake_agent,
        monkeypatch,
        cwd=tmp_path,
    )
    # Slim Stage 2 default runs the 3 computational-paper audit pillars (R4/R5 decoupled as opt-in)
    assert set(seen.keys()) == {
        "structure_narrative",
        "reproducibility_code",
        "claims_definitions",
        "conciseness_editor",
        "average_reader",
    }
    assert "specimen_openings" in seen["structure_narrative"]
    assert "SHORT-ROUTE PARITY" in seen["structure_narrative"]
    assert "single canonical definition in SI" in seen["claims_definitions"]
    assert "three-way epistemic separation" in seen["claims_definitions"]
    assert "verify_citations.py" in seen["reproducibility_code"]
    assert "Flag >2 distinct baselines" not in seen["conciseness_editor"]
    assert "Custom lab style prior: use vector EPS." in seen["structure_narrative"]
    assert "Custom lab style prior: use vector EPS." in seen["reproducibility_code"]
    assert "Custom lab style prior: use vector EPS." in seen["conciseness_editor"]
    # Reviewer 11 (average_reader) checks: flash default, Main+SI only (zero overlay/extra_files/lint), advisory non-blocking
    assert seen_models["average_reader"] == "flash"
    assert seen_models["structure_narrative"] == "inherit"
    assert set(seen_schemas["average_reader"]["required"]) >= {
        "plain_english_reconstruction",
        "walkout_point",
        "friction_hotspots",
        "where_i_got_lost_or_bored",
    }
    assert (
        "prior_work_vs_new_delta_from_abstract"
        in seen_schemas["average_reader"]["properties"]["plain_english_reconstruction"]["required"]
    )
    assert "Custom lab style prior" not in seen["average_reader"]
    assert "secret_code.py" not in seen["average_reader"]
    assert "PRE-LINTER" not in seen["average_reader"]
    assert data["reviewer_models"]["average_reader"] == "flash"
    assert data["reader_two_pass_active"] is False
    assert data["stage_gate"]["total_p0_p1_count"] == 0
    assert data["stage_gate"]["ready_to_advance"] is True


def test_review_panel_r11_two_pass_and_r1_storyflow_linter(tmp_path, monkeypatch):
    main_tex = tmp_path / "manuscript.tex"
    si_tex = tmp_path / "supplement.tex"
    long_stretch = " ".join(f"word{i}" for i in range(470))
    main_tex.write_text(
        "\\begin{document}\n"
        "\\section{Methods}\n"
        "We start with a dense derivation.\n"
        "\\begin{align}\n"
        "a_1 &= b_1 \\\\\n"
        "a_2 &= b_2 \\\\\n"
        "a_3 &= b_3 \\\\\n"
        "a_4 &= b_4 \\\\\n"
        "a_5 &= b_5 \\\\\n"
        "a_6 &= b_6\n"
        "\\end{align}\n"
        "Next step.\n"
        "\\begin{equation}\nx = 1\n\\end{equation}\n"
        "Then.\n"
        "\\begin{equation}\ny = 2\n\\end{equation}\n"
        "Hence.\n"
        "\\begin{equation}\nz = 3\n\\end{equation}\n\n"
        "Here $A_{ij}^k$ maps $B_{mn}^p$, $C_{rs}^q$, $D_{uv}^w$, $\\alpha$, $\\beta$, $\\gamma$, $\\delta$, $\\epsilon$, $\\zeta$ into $\\eta$.\n\n"
        f"{long_stretch}.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    si_tex.write_text("\\begin{document}\n\\section{SI Details}\nFull proof here.\n\\end{document}\n", encoding="utf-8")

    calls = []
    r1_prompts = []

    def fake_agent(prompt, schema, role, type_name, model):
        calls.append((role, prompt, schema, model))
        if "PASS 1/2" in prompt:
            return {
                "main_only_summary": "Main has a math wall in Methods.",
                "plain_english_reconstruction": {
                    "problem": "p",
                    "prior_work_vs_new_delta_from_abstract": "d",
                    "method_steps": "m",
                    "headline_result_and_baseline": "h",
                    "main_limitation": "l",
                },
                "walkout_point": {
                    "location": "Methods",
                    "trigger": "6-line align wall",
                    "why_reader_stops_linear_reading": "No intuition",
                },
                "unresolved_main_gaps_and_si_jumps": [
                    {
                        "location": "Methods",
                        "missing_or_deferred_item": "Undefined alpha_k jump to SI",
                        "breaks_main_story": True,
                    }
                ],
                "friction_hotspots": [
                    {
                        "location": "Methods",
                        "friction_type": "math_wall_no_intuition",
                        "quote_or_cue": "align block",
                        "why_it_breaks_flow": "Opaque algebra",
                        "suggested_story_fix": "Move to SI",
                    }
                ],
            }
        if "reviewer_id='average_reader'" in prompt:
            out = {
                "reviewer_id": "average_reader",
                "reviewer_role": role,
                "summary": "ok",
                "findings": [],
                "plain_english_reconstruction": {
                    "problem": "p",
                    "prior_work_vs_new_delta_from_abstract": "d",
                    "method_steps": "m",
                    "headline_result_and_baseline": "h",
                    "main_limitation": "l",
                },
                "walkout_point": {
                    "location": "Methods",
                    "trigger": "6-line align wall",
                    "why_reader_stops_linear_reading": "No intuition",
                },
                "friction_hotspots": [
                    {
                        "location": "Methods",
                        "friction_type": "math_wall_no_intuition",
                        "quote_or_cue": "align block",
                        "why_it_breaks_flow": "Opaque algebra",
                        "suggested_story_fix": "Move to SI",
                    }
                ],
                "where_i_got_lost_or_bored": [],
            }
            if "PASS 2/2" in prompt:
                out["two_pass_si_audit"] = {
                    "pass1_gaps_resolved_by_si": ["alpha_k defined in SI"],
                    "pass1_gaps_still_missing": [],
                    "essential_story_buried_in_si": ["Core intuition lives only in SI"],
                    "main_si_flipping_verdict": "Requires flipping to SI mid-Methods.",
                }
            return out
        for rid in ("structure_narrative", "reproducibility_code", "claims_definitions", "prose_style", "figures_refs_format"):
            if f"reviewer_id='{rid}'" in prompt:
                if rid == "structure_narrative":
                    r1_prompts.append(prompt)
                res = {"reviewer_id": rid, "reviewer_role": role, "summary": "ok", "findings": []}
                if rid == "reproducibility_code":
                    res["reproducibility_rating"] = "sufficient"
                return res
        raise AssertionError(f"Unexpected role {role}")

    # Pass SI first to verify smart Main-vs-SI filename splitting
    data, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {"stage": "stage2a", "mode": "review", "report": [str(si_tex), str(main_tex)]},
        fake_agent,
        monkeypatch,
        cwd=tmp_path,
    )
    assert data["reader_two_pass_active"] is True

    # R1 receives all 3 0-token storyflow cognitive-load buckets
    assert len(r1_prompts) == 1
    assert "Math-wall bursts" in r1_prompts[0]
    assert "Symbol-density / working-memory spikes" in r1_prompts[0]
    assert "Long unanchored prose stretches" in r1_prompts[0]

    # R11 ran Pass 1 (Main-only, ZERO SI path or pre-linter) and Pass 2 (Main+SI + frozen Pass 1 notes)
    r11_calls = [c for c in calls if "Reviewer 11" in c[0]]
    assert len(r11_calls) == 2
    p1_role, p1_prompt, p1_schema, p1_model = r11_calls[0]
    p2_role, p2_prompt, p2_schema, p2_model = r11_calls[1]
    assert "Pass 1/2" in p1_role and p1_model == "flash"
    assert "manuscript.tex" in p1_prompt and "supplement.tex" not in p1_prompt
    assert "PRE-LINTER" not in p1_prompt
    assert set(p1_schema["required"]) >= {"walkout_point", "friction_hotspots", "unresolved_main_gaps_and_si_jumps"}
    assert "Pass 2/2" in p2_role and p2_model == "flash"
    assert "manuscript.tex" in p2_prompt and "supplement.tex" in p2_prompt
    assert "Undefined alpha_k jump to SI" in p2_prompt
    assert "PRE-LINTER" not in p2_prompt
    assert "two_pass_si_audit" in p2_schema["required"]

    r11_out = next(r for r in data["reviews"] if r["reviewer_id"] == "average_reader")
    assert "pass1_main_only" in r11_out and "two_pass_si_audit" in r11_out

    # Explicit reader_two_pass=False forces single-pass R11 even with >=2 files
    calls.clear()
    data_1p, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {"stage": "stage2a", "mode": "review", "report": [str(main_tex), str(si_tex)], "reader_two_pass": False},
        fake_agent,
        monkeypatch,
        cwd=tmp_path,
    )
    assert data_1p["reader_two_pass_active"] is False
    r11_calls_1p = [c for c in calls if "Reviewer 11" in c[0]]
    assert len(r11_calls_1p) == 1
    assert "two_pass_si_audit" not in r11_calls_1p[0][2]["required"]


# --- 4. preflight_lint.py Regression Tests (All 6 Fixed Bugs) ---


def test_preflight_lint_wb_md_emdash_bib_inline_table_and_nested_caption(tmp_path):
    linter = _load_linter()

    # 1. Binary open(..., "wb") detected
    py_file = tmp_path / "writer.py"
    py_file.write_text('with open("out.bin", "wb") as f:\n    f.write(b"x")\n', encoding="utf-8")

    # 2. Markdown frontmatter, HR, table separator, and fenced code do NOT trigger em_dashes
    md_file = tmp_path / "doc.md"
    md_file.write_text(
        "---\n"
        "title: Demo\n"
        "---\n\n"
        "---\n\n"
        "| A | B |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n\n"
        "```text\n"
        "ignored --- inside code\n"
        "```\n\n"
        "Real prose --- should trigger.\n",
        encoding="utf-8",
    )

    # 3. .bib checks actual field assignments, not substrings in title
    bib_file = tmp_path / "refs.bib"
    bib_file.write_text(
        "@article{bad2026,\n"
        "  author = {Doe, J.},\n"
        "  title = {A 20-year study of journalism and volume pages},\n"
        "}\n",
        encoding="utf-8",
    )

    # 4. Inline tabular + nested-brace \caption{}
    repeated = "Shared boilerplate caption text for \\textbf{method} evaluation across systems"
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(
        "\\begin{document}\n"
        + "\n".join(f"\\caption{{{repeated} run {i}.}}" for i in range(4))
        + "\n\\begin{tabular}{ccc}\n"
        "A & -- & 1 \\\\\n"
        "B & -- & 1 \\\\\n"
        "C & -- & 1 \\\\\n"
        "D & -- & 1 \\\\\n"
        "E & -- & 1 \\\\\n"
        "F & -- & 1 \\\\\n"
        "\\end{tabular}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )

    rep = linter.run_preflight_lint([str(py_file), str(md_file), str(bib_file), str(tex_file)], base_dir=str(tmp_path))

    # Assertions
    assert rep["code"].get("potential_non_atomic_writes"), "open(..., 'wb') must be flagged"
    em_hits = rep["tex_md"].get("em_dashes", [])
    assert len(em_hits) == 1 and "Real prose" in em_hits[0], f"Unexpected em_dash hits: {em_hits}"
    bib_hits = rep["bib"].get("bib_incomplete_entries", [])
    assert len(bib_hits) == 1 and "year" in bib_hits[0] and "journal" in bib_hits[0], bib_hits
    assert rep["compression"].get("repeated_caption_phrases"), "Nested-brace captions must be parsed"
    assert any("inline tabular" in h for h in rep["compression"].get("table_bloat_and_sparsity", [])), rep["compression"]

    # 5. Plot-script hygiene: clean 1-column PDF defaults (lw=1.5, fontsize=10) pass; extreme values (<1.0 / <8) trigger advisory hits
    clean_plot = tmp_path / "plot_clean.py"
    clean_plot.write_text(
        "import matplotlib.pyplot as plt\n"
        "plt.plot([0, 1], [0, 1], linewidth=1.5)\n"
        "plt.xlabel('x', fontsize=10)\n"
        "plt.savefig('fig.pdf')\n",
        encoding="utf-8",
    )
    tiny_plot = tmp_path / "plot_tiny.py"
    tiny_plot.write_text(
        "import matplotlib.pyplot as plt\n"
        "plt.plot([0, 1], [0, 1], lw=0.5)\n"
        "plt.xlabel('x', fontsize=6)\n"
        "plt.title('Repeat caption')\n"
        "plt.savefig('fig.pdf')\n",
        encoding="utf-8",
    )
    rep_clean = linter.run_preflight_lint([str(clean_plot)], base_dir=str(tmp_path))
    assert not rep_clean["code"].get("plot_script_hygiene"), f"Clean 1-column script should pass: {rep_clean['code']}"
    rep_tiny = linter.run_preflight_lint([str(tiny_plot)], base_dir=str(tmp_path))
    tiny_hits = rep_tiny["code"].get("plot_script_hygiene", [])
    assert len(tiny_hits) == 3 and all("advisory:" in h for h in tiny_hits), tiny_hits


# --- 5. Cross-Platform Agent Skills Compliance (Antigravity / Claude Code / Codex) ---


def test_agent_skills_standard_compliance_and_links():
    import re
    import yaml

    skill_mds = sorted(SUITE_ROOT.glob("*/SKILL.md"))
    assert len(skill_mds) == 4
    md_link_re = re.compile(r"\[[^\]]+\]\((\.\.?/[^)#]+)")

    for smd in skill_mds:
        raw = smd.read_text(encoding="utf-8")
        assert raw.startswith("---"), f"{smd} missing YAML frontmatter"
        parts = raw.split("---", 2)
        assert len(parts) == 3, f"{smd} malformed YAML frontmatter"
        meta = yaml.safe_load(parts[1])
        name = meta.get("name", "")
        desc = meta.get("description", "")
        folder = smd.parent.name
        assert name == folder, f"{smd}: name '{name}' != folder '{folder}'"
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) and len(name) <= 64
        assert 1 <= len(desc) <= 1024, f"{smd}: description len {len(desc)} > 1024"

        # Every relative markdown link inside SKILL.md must resolve to an existing file
        for rel_target in md_link_re.findall(parts[2]):
            resolved = (smd.parent / rel_target).resolve()
            assert resolved.exists(), f"{smd}: broken relative link '{rel_target}'"

    # Both scripts must include .claude/skills and .codex/skills in _skill_root_candidates
    for script_path in (SCREEN_SCRIPT, REVIEW_SCRIPT):
        src = script_path.read_text(encoding="utf-8")
        assert '".claude"' in src and '".codex"' in src, f"{script_path} missing cross-platform skill roots"


# --- 6. Cross-Domain Local Overlay Isolation & Stage 0/1A Evaluator Sanity Probes ---


def _write_lab_overlay(tmp_path: Path):
    overlay_dir = tmp_path / ".agents" / "skills"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    (overlay_dir / "local_config.yaml").write_text(
        'default_domain: "computational chemistry / quantum physics"\n'
        'default_venues:\n  - "PRX Quantum"\n'
        'arxiv_categories:\n  - "quant-ph"\n',
        encoding="utf-8",
    )
    (overlay_dir / "local_overlay.md").write_text(
        "Quantum lab sentinel: VQE HF CCSD Trillium.\n",
        encoding="utf-8",
    )


def test_review_panel_cross_domain_overlay_auto_suppression_and_overrides(tmp_path, monkeypatch):
    _write_lab_overlay(tmp_path)

    def make_fake(captured: dict):
        def fake_agent(prompt, schema, role, type_name, model):
            for rid in ("baseline_killer", "theory_mechanism_critic", "supervisor_strategist"):
                if f"reviewer_id='{rid}'" in prompt:
                    captured[rid] = prompt
                    if rid == "baseline_killer":
                        return {
                            "reviewer_id": rid,
                            "reviewer_role": role,
                            "summary": "ok",
                            "findings": [],
                            "baseline_verdict": "SOLID_BASELINE",
                            "p0_p1_count": 0,
                            "stage1a_closed": True,
                        }
                    if rid == "supervisor_strategist":
                        return {
                            "reviewer_id": rid,
                            "reviewer_role": role,
                            "summary": "ok",
                            "findings": [],
                            "live_search_status": "searched_live",
                            "novelty_assessment": {
                                "novelty_verdict": "CLEAR_NOVELTY_ABOVE_BAR",
                                "target_venue_bar_analysis": "ok",
                                "irreducible_new_idea": "ok",
                                "contributions": [],
                            },
                            "candidate_pivots": [],
                        }
                    return {"reviewer_id": rid, "reviewer_role": role, "summary": "ok", "findings": []}
            raise AssertionError(f"Unexpected role {role}")

        return fake_agent

    # (A) Cross-domain override auto-suppresses local_overlay.md, venues, and arXiv categories
    cap_cross = {}
    data_cross, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {
            "stage": "stage1",
            "domain": "astrophysics / exoplanet radial-velocity",
            "report_text": "RV benchmark draft",
            "skip_pivot_red_team": True,
        },
        make_fake(cap_cross),
        monkeypatch,
        cwd=tmp_path,
    )
    assert data_cross["local_overlay_loaded"]["applied"] is False
    assert data_cross["local_overlay_loaded"]["skipped_reason"] == "cross_domain_override"
    for rid, prompt in cap_cross.items():
        assert "Quantum lab sentinel" not in prompt, f"{rid} leaked local_overlay.md cross-domain"
        assert "PRX Quantum" not in prompt, f"{rid} leaked default_venues cross-domain"
        assert "quant-ph" not in prompt, f"{rid} leaked arxiv_categories cross-domain"

    # (B) In-domain run keeps local_overlay.md, venues, and arXiv categories
    cap_in = {}
    data_in, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {"stage": "stage1b", "domain": "quantum chemistry", "report_text": "VQE draft", "skip_pivot_red_team": True},
        make_fake(cap_in),
        monkeypatch,
        cwd=tmp_path,
    )
    assert data_in["local_overlay_loaded"]["applied"] is True
    assert data_in["local_overlay_loaded"]["skipped_reason"] is None
    assert "Quantum lab sentinel" in cap_in["theory_mechanism_critic"]
    assert "Quantum lab sentinel" in cap_in["supervisor_strategist"]
    assert "PRX Quantum" in cap_in["supervisor_strategist"]
    assert "quant-ph" in cap_in["supervisor_strategist"]

    # (C) Explicit skip_local_overlay=True suppresses even in-domain
    cap_skip = {}
    data_skip, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {
            "stage": "stage1b",
            "domain": "quantum chemistry",
            "skip_local_overlay": True,
            "report_text": "VQE draft",
            "skip_pivot_red_team": True,
        },
        make_fake(cap_skip),
        monkeypatch,
        cwd=tmp_path,
    )
    assert data_skip["local_overlay_loaded"]["applied"] is False
    assert data_skip["local_overlay_loaded"]["skipped_reason"] == "explicit_skip"
    assert "Quantum lab sentinel" not in cap_skip["supervisor_strategist"]
    assert "quant-ph" not in cap_skip["supervisor_strategist"]

    # (D) Explicit skip_local_overlay=False forces overlay even cross-domain
    cap_force = {}
    data_force, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {
            "stage": "stage1b",
            "domain": "astrophysics",
            "skip_local_overlay": False,
            "report_text": "RV draft",
            "skip_pivot_red_team": True,
        },
        make_fake(cap_force),
        monkeypatch,
        cwd=tmp_path,
    )
    assert data_force["local_overlay_loaded"]["applied"] is True
    assert "Quantum lab sentinel" in cap_force["supervisor_strategist"]


def test_screen_idea_cross_domain_overlay_auto_suppression(tmp_path, monkeypatch):
    _write_lab_overlay(tmp_path)

    def make_fake(captured: dict):
        def fake_agent(prompt, schema, role, type_name, model):
            if "scout_id='literature_novelty_strategist'" in prompt:
                captured["lit"] = prompt
                return {
                    "scout_id": "literature_novelty_strategist",
                    "scout_role": role,
                    "summary": "s",
                    "fatal_blocker_count": 0,
                    "key_risks": [],
                    "live_search_status": "searched_live",
                    "novelty_verdict": "CLEAR_NOVELTY_ABOVE_BAR",
                    "irreducible_novelty_wedge": "w",
                    "prior_art_hits": [],
                    "referee2_premortem": "Two sentences.",
                    "pivot_options": [],
                }
            sid = "baseline_feasibility_killer" if "baseline_feasibility_killer" in prompt else "theory_limits_critic"
            captured[sid] = prompt
            out = {"scout_id": sid, "scout_role": role, "summary": "ok", "fatal_blocker_count": 0, "key_risks": []}
            if sid == "baseline_feasibility_killer":
                out.update({"strongest_cheap_baseline": "b", "day1_pilots": []})
            else:
                out.update({"scaling_and_bounds_summary": "s", "predicted_failure_modes": []})
            return out

        return fake_agent

    cap_cross = {}
    data_cross, _ = _run_workflow_script(
        SCREEN_SCRIPT,
        {
            "track": "numerical_algorithm",
            "domain": "astrophysics / exoplanet radial-velocity",
            "idea": "RV model fitting benchmark",
            "skip_pivot_red_team": True,
        },
        make_fake(cap_cross),
        monkeypatch,
        cwd=tmp_path,
    )
    assert data_cross["local_overlay_loaded"]["applied"] is False
    assert data_cross["local_overlay_loaded"]["skipped_reason"] == "cross_domain_override"
    for sid, prompt in cap_cross.items():
        assert "Quantum lab sentinel" not in prompt, f"{sid} leaked local_overlay.md cross-domain"
        assert "PRX Quantum" not in prompt
        assert "quant-ph" not in prompt

    cap_in = {}
    data_in, _ = _run_workflow_script(
        SCREEN_SCRIPT,
        {
            "track": "numerical_algorithm",
            "domain": "quantum physics",
            "idea": "VQE variance reduction",
            "skip_pivot_red_team": True,
        },
        make_fake(cap_in),
        monkeypatch,
        cwd=tmp_path,
    )
    assert data_in["local_overlay_loaded"]["applied"] is True
    assert "Quantum lab sentinel" in cap_in["lit"]
    assert "PRX Quantum" in cap_in["lit"]
    assert "quant-ph" in cap_in["lit"]


def test_stage0_and_stage1a_evaluator_sanity_and_parity_clauses_loaded(tmp_path, monkeypatch):
    seen = {}

    def fake_stage0(prompt, schema, role, type_name, model):
        seen["r0"] = prompt
        return {
            "reviewer_id": "code_math_auditor",
            "reviewer_role": role,
            "summary": "ok",
            "findings": [],
            "stage0_verdict": "ALIGNED_FAIL_LOUD",
            "p0_p1_count": 0,
            "stage0_closed": True,
            "execution_status": "no_runnable_targets",
        }

    def fake_stage1a(prompt, schema, role, type_name, model):
        seen["r7"] = prompt
        return {
            "reviewer_id": "baseline_killer",
            "reviewer_role": role,
            "summary": "ok",
            "findings": [],
            "baseline_verdict": "SOLID_BASELINE",
            "p0_p1_count": 0,
            "stage1a_closed": True,
        }

    def fake_stage1b(prompt, schema, role, type_name, model):
        if "reviewer_id='theory_mechanism_critic'" in prompt:
            seen["r8"] = prompt
            return {"reviewer_id": "theory_mechanism_critic", "reviewer_role": role, "summary": "ok", "findings": []}
        return {
            "reviewer_id": "supervisor_strategist",
            "reviewer_role": role,
            "summary": "ok",
            "findings": [],
            "live_search_status": "searched_live",
            "novelty_assessment": {
                "novelty_verdict": "CLEAR_NOVELTY_ABOVE_BAR",
                "target_venue_bar_analysis": "ok",
                "irreducible_new_idea": "ok",
                "contributions": [],
            },
            "candidate_pivots": [],
        }

    _run_workflow_script(REVIEW_SCRIPT, {"stage": "stage0", "report_text": "Benchmark spec"}, fake_stage0, monkeypatch, cwd=tmp_path)
    _run_workflow_script(REVIEW_SCRIPT, {"stage": "stage1a", "report_text": "Benchmark spec"}, fake_stage1a, monkeypatch, cwd=tmp_path)
    _run_workflow_script(REVIEW_SCRIPT, {"stage": "stage1b", "report_text": "Benchmark spec"}, fake_stage1b, monkeypatch, cwd=tmp_path)

    for phrase in ("Ground-Truth / Oracle Solvability", "Null/Empty-Model", "Monotonicity / Garbage-Padding", "Zero-Leakage & Denominator"):
        assert phrase in seen["r0"], f"Reviewer 0 prompt missing Stage 0 probe: {phrase}"
    for phrase in ("Interaction & input parity", "ground truth / an oracle-initialized solver", "Objective–proxy alignment"):
        assert phrase in seen["r7"], f"Reviewer 7 prompt missing Stage 1A check: {phrase}"
    for stripped in ("unshared beats shared", "magnitude-sorted ordering"):
        assert stripped not in seen["r7"], f"Reviewer 7 prompt still contains stripped domain-specific hint: {stripped}"
    assert "Objective-proxy alignment" in seen["r8"], "Reviewer 8 prompt missing Stage 1B objective-proxy alignment check"


# --- 7. Offline Prior-Art Brief Guard & Retrospective cutoff_year ---


def test_review_panel_offline_search_status_guard_and_cutoff_year(tmp_path, monkeypatch):
    seen = {}

    def fake_agent(prompt, schema, role, type_name, model):
        assert type_name == "research"
        if "Pivot Red-Team" in (role or ""):
            seen["prt"] = prompt
            # Simulate a rogue offline agent falsely reporting 'searched_live'
            return {
                "live_search_status": "searched_live",
                "summary": "audited offline",
                "pivot_audit": [
                    {
                        "pivot_title": "P1",
                        "strongest_cheap_baseline": "B",
                        "primary_math_or_scaling_trap": "T",
                        "pivot_verdict": "VIABLE_WITH_PATCH",
                        "one_line_patch": "Trim scope.",
                    }
                ],
                "design_space_constraints": [],
            }
        if "reviewer_id='supervisor_strategist'" in prompt:
            seen["r9"] = prompt
            return {
                "reviewer_id": "supervisor_strategist",
                "reviewer_role": role,
                "summary": "ok",
                "findings": [],
                "live_search_status": "searched_live",
                "novelty_assessment": {
                    "novelty_verdict": "CLEAR_NOVELTY_ABOVE_BAR",
                    "target_venue_bar_analysis": "ok",
                    "irreducible_new_idea": "ok",
                    "contributions": [],
                },
                "candidate_pivots": [{"pivot_title": "P1", "core_twist": "t", "theorem_or_experiment_hook": "h"}],
            }
        return {"reviewer_id": "theory_mechanism_critic", "reviewer_role": role, "summary": "ok", "findings": []}

    # (A) Offline + prior_art_summary + cutoff_year=2025 -> rogue 'searched_live' normalized to 'used_supplied_brief'
    data_with_brief, logs_a = _run_workflow_script(
        REVIEW_SCRIPT,
        {
            "stage": "stage1b",
            "agent_type": "research",
            "cutoff_year": 2025,
            "prior_art_summary": "Verified pre-2026 dossier sentinel",
            "report_text": "Draft text",
        },
        fake_agent,
        monkeypatch,
        cwd=tmp_path,
    )
    assert data_with_brief["cutoff_year"] == 2025
    assert data_with_brief["search_window"] == "2022-2025"
    assert "2025-12-31" in seen["r9"]
    assert "2025-12-31" in seen["prt"]
    assert "Verified pre-2026 dossier sentinel" in seen["prt"]
    assert "NEVER report `searched_live`" in seen["prt"]
    r9 = next(r for r in data_with_brief["reviews"] if r["reviewer_id"] == "supervisor_strategist")
    assert r9["live_search_status"] == "used_supplied_brief"
    assert data_with_brief["pivot_red_team"]["live_search_status"] == "used_supplied_brief"
    assert data_with_brief["stage_gate"]["search_verification_required"] is False
    assert any("SEARCH_STATUS_GUARD" in line for line in logs_a)

    # (B) Offline WITHOUT prior_art_summary -> rogue 'searched_live' fails closed to 'blocked_or_offline'
    data_no_brief, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {
            "stage": "stage1b",
            "agent_type": "research",
            "cutoff_year": 2025,
            "report_text": "Draft text",
        },
        fake_agent,
        monkeypatch,
        cwd=tmp_path,
    )
    r9_nb = next(r for r in data_no_brief["reviews"] if r["reviewer_id"] == "supervisor_strategist")
    assert r9_nb["live_search_status"] == "blocked_or_offline"
    assert data_no_brief["pivot_red_team"]["live_search_status"] == "blocked_or_offline"
    assert data_no_brief["stage_gate"]["search_verification_required"] is True
    assert data_no_brief["stage_gate"]["ready_to_advance"] is False


def test_screen_idea_offline_search_status_guard_and_cutoff_year(tmp_path, monkeypatch):
    seen = {}

    def fake_agent(prompt, schema, role, type_name, model):
        assert type_name == "research"
        if "Pivot Red-Team" in (role or ""):
            seen["prt"] = prompt
            return {
                "live_search_status": "searched_live",
                "summary": "audited offline",
                "pivot_audit": [
                    {
                        "pivot_title": "P1",
                        "strongest_cheap_baseline": "B",
                        "primary_math_or_scaling_trap": "T",
                        "pivot_verdict": "SURVIVES_RED_TEAM",
                        "one_line_patch": "N/A",
                    }
                ],
                "design_space_constraints": [],
            }
        if "scout_id='literature_novelty_strategist'" in prompt:
            seen["lit"] = prompt
            return {
                "scout_id": "literature_novelty_strategist",
                "scout_role": role,
                "summary": "s",
                "fatal_blocker_count": 0,
                "key_risks": [],
                "live_search_status": "searched_live",
                "novelty_verdict": "CLEAR_NOVELTY_ABOVE_BAR",
                "irreducible_novelty_wedge": "w",
                "prior_art_hits": [],
                "referee2_premortem": "Two sentences.",
                "pivot_options": [{"pivot_title": "P1", "core_twist": "t", "why_stronger": "w", "theorem_or_experiment_hook": "h"}],
            }
        sid = "baseline_feasibility_killer" if "baseline_feasibility_killer" in prompt else "theory_limits_critic"
        out = {"scout_id": sid, "scout_role": role, "summary": "ok", "fatal_blocker_count": 0, "key_risks": []}
        if sid == "baseline_feasibility_killer":
            out.update({"strongest_cheap_baseline": "b", "day1_pilots": []})
        else:
            out.update({"scaling_and_bounds_summary": "s", "predicted_failure_modes": []})
        return out

    data, _ = _run_workflow_script(
        SCREEN_SCRIPT,
        {
            "track": "numerical_algorithm",
            "agent_type": "research",
            "cutoff_year": 2025,
            "prior_art_summary": "Pre-2026 idea dossier sentinel",
            "idea": "New QPE spectral amplification scheme",
        },
        fake_agent,
        monkeypatch,
        cwd=tmp_path,
    )
    assert data["cutoff_year"] == 2025
    assert data["search_window"] == "2019-2025"
    assert "2025-12-31" in seen["lit"]
    assert "2025-12-31" in seen["prt"]
    assert "Pre-2026 idea dossier sentinel" in seen["prt"]
    assert data["screen_gate"]["live_search_status"] == "used_supplied_brief"
    assert data["screen_gate"]["phase2_live_search_status"] == "used_supplied_brief"
    assert data["screen_gate"]["search_verification_required"] is False
    assert data["screen_gate"]["recommendation"] == "PROCEED_TO_PROTOTYPE"


# --- 8. Stage 1A 4-Tier R7 Calibration & Fail-Closed P0 Escalation ---


def test_review_panel_stage1a_four_tier_verdict_and_p0_escalation(tmp_path, monkeypatch):
    seen_prompt = {}

    # (A) MECHANISM_SOLID_PARITY_FIX_NEEDED with p0_count=0 -> can_advance_to_stage1b=True, closed=False
    def fake_parity_only(prompt, schema, role, type_name, model):
        seen_prompt["r7"] = prompt
        assert "MECHANISM_SOLID_PARITY_FIX_NEEDED" in schema["properties"]["baseline_verdict"]["enum"]
        assert "p0_count" in schema["properties"]
        return {
            "reviewer_id": "baseline_killer",
            "reviewer_role": role,
            "summary": "Core Discovery survives; localized table/scope P1s only.",
            "findings": [
                {
                    "priority": "essential",
                    "category": "P1_parity",
                    "location": "Table 4",
                    "issue": "Printed norm convention mismatch",
                    "why_it_matters": "Clarity",
                    "author_question_or_placeholder": "[AUTHOR: fix column]",
                }
            ],
            "baseline_verdict": "MECHANISM_SOLID_PARITY_FIX_NEEDED",
            "p0_count": 0,
            "p0_p1_count": 1,
            "stage1a_closed": False,
        }

    data_a, _ = _run_workflow_script(
        REVIEW_SCRIPT,
        {"stage": "stage1a", "report_text": "Strong Discovery paper with table typo"},
        fake_parity_only,
        monkeypatch,
        cwd=tmp_path,
    )
    assert "Severity, Materiality & Scope Calibration" in seen_prompt["r7"]
    assert "Role Boundary vs. Reviewers 8 & 2" in seen_prompt["r7"]
    g_a = data_a["stage1a_gate"]
    assert g_a["baseline_verdict"] == "MECHANISM_SOLID_PARITY_FIX_NEEDED"
    assert g_a["p0_count"] == 0 and g_a["p0_p1_count"] == 1
    assert g_a["closed"] is False
    assert g_a["can_advance_to_stage1b"] is True
    assert "ADVANCE_TO_STAGE1B_WITH_LOCAL_FIXES" in g_a["next_action"]

    # (B) Fail-closed escalation: MECHANISM_SOLID_PARITY_FIX_NEEDED with p0_count>0 escalates to HANDICAPPED_BASELINE_RERUN_REQUIRED
    def fake_inconsistent_p0(prompt, schema, role, type_name, model):
        return {
            "reviewer_id": "baseline_killer",
            "reviewer_role": role,
            "summary": "Has a P0 leak",
            "findings": [],
            "baseline_verdict": "MECHANISM_SOLID_PARITY_FIX_NEEDED",
            "p0_count": 2,
            "p0_p1_count": 2,
            "stage1a_closed": False,
        }

    data_b, logs_b = _run_workflow_script(
        REVIEW_SCRIPT,
        {"stage": "stage1a", "report_text": "Leaky benchmark"},
        fake_inconsistent_p0,
        monkeypatch,
        cwd=tmp_path,
    )
    g_b = data_b["stage1a_gate"]
    assert g_b["baseline_verdict"] == "HANDICAPPED_BASELINE_RERUN_REQUIRED"
    assert g_b["can_advance_to_stage1b"] is False
    assert any("STAGE1A_VERDICT_GUARD" in line for line in logs_b)


# --- 7. Citation Verifier (arXiv / Crossref / Semantic Scholar) & Cross-Host Export Bridge ---


def test_verify_citations_offline_and_mocked_apis(tmp_path):
    verifier_path = SUITE_ROOT / "scientific-report-review" / "scripts" / "verify_citations.py"
    spec = importlib.util.spec_from_file_location("verify_citations", str(verifier_path))
    vc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vc)

    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{good_arxiv,\n"
        "  author = {Smith, A.},\n"
        "  title = {Adaptive Variance Reduction for Sparse Linear Solvers},\n"
        "  year = {2025},\n"
        "  eprint = {2501.01234},\n"
        "  archivePrefix = {arXiv},\n"
        "}\n"
        "@article{bad_year_doi,\n"
        "  author = {Lee, B.},\n"
        "  title = {Fast Matrix Preconditioning},\n"
        "  year = {2019},\n"
        "  doi = {10.1000/test.doi},\n"
        "}\n"
        "@article{ghost_paper,\n"
        "  author = {Fake, C.},\n"
        "  title = {Nonexistent Quantum Magic Paper},\n"
        "  year = {2026},\n"
        "}\n"
        "@article{good_arxiv,\n"
        "  title = {Duplicate key entry},\n"
        "}\n",
        encoding="utf-8",
    )
    tex = tmp_path / "paper.tex"
    tex.write_text(r"\cite{good_arxiv,missing_key_99}", encoding="utf-8")

    # Offline structural + undefined-cite audit
    off = vc.verify_citations([str(bib), str(tex)], offline=True)
    assert off["duplicate_bib_keys"] == ["good_arxiv"]
    assert off["undefined_cite_keys"] == ["missing_key_99"]
    assert off["counts"].get("MISSING_FIELDS", 0) >= 1

    # Mocked live APIs (arXiv Atom XML + Crossref DOI + Crossref title miss)
    def fake_fetcher(url: str, timeout: float = 8.0) -> bytes:
        if "export.arxiv.org" in url:
            return (
                b'<?xml version="1.0" encoding="UTF-8"?>'
                b'<feed xmlns="http://www.w3.org/2005/Atom">'
                b"<entry>"
                b"<id>http://arxiv.org/abs/2501.01234v1</id>"
                b"<published>2025-01-05T00:00:00Z</published>"
                b"<title>Adaptive Variance Reduction for Sparse Linear Solvers</title>"
                b"</entry></feed>"
            )
        if "api.crossref.org/works/10.1000" in url:
            return json.dumps(
                {
                    "message": {
                        "DOI": "10.1000/test.doi",
                        "title": ["Fast Matrix Preconditioning"],
                        "issued": {"date-parts": [[2024]]},
                    }
                }
            ).encode("utf-8")
        if "api.crossref.org/works?" in url:
            return json.dumps({"message": {"items": []}}).encode("utf-8")
        raise AssertionError(f"Unexpected URL {url}")

    live = vc.verify_citations([str(bib), str(tex)], offline=False, delay=0.0, fetcher=fake_fetcher)
    by_key = {}
    for r in live["results"]:
        by_key.setdefault(r["key"], []).append(r["status"])
    assert "VERIFIED" in by_key["good_arxiv"]
    assert by_key["bad_year_doi"] == ["TITLE_OR_YEAR_MISMATCH"]
    assert by_key["ghost_paper"] == ["NOT_FOUND_SUSPECT"]


def test_export_panel_cross_host_cli_and_gate(tmp_path):
    exporter_path = SUITE_ROOT / "scripts" / "export_panel.py"
    if not exporter_path.is_file():
        pytest.skip("export_panel.py lives in the packaged repo root")

    spec = importlib.util.spec_from_file_location("export_panel", str(exporter_path))
    ep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ep)

    draft = tmp_path / "draft.tex"
    draft.write_text("\\begin{document}\\section{Intro}Test.\\end{document}\n", encoding="utf-8")
    out_dir = tmp_path / "exported_stage1"
    manifest = ep.export_prompts(
        "review",
        {"stage": "stage1", "report": [str(draft)], "domain": "numerical linear algebra"},
        out_dir,
        cwd=tmp_path,
    )
    assert manifest["agent_count"] == 3
    ids = [a["id"] for a in manifest["agents"]]
    assert ids == ["baseline_killer", "theory_mechanism_critic", "supervisor_strategist"]
    for a in manifest["agents"]:
        assert (out_dir / a["prompt_file"]).is_file()
        assert (out_dir / a["schema_file"]).is_file()

    # Fail-closed gate check on collected results
    gate_fail = ep.evaluate_gate(
        "stage1a",
        [{"reviewer_id": "baseline_killer", "baseline_verdict": "HANDICAPPED_BASELINE_RERUN_REQUIRED", "p0_p1_count": 1}],
    )
    assert gate_fail["ready_to_advance"] is False
    gate_pass = ep.evaluate_gate(
        "stage1a",
        [{"reviewer_id": "baseline_killer", "baseline_verdict": "SOLID_BASELINE", "p0_p1_count": 0}],
    )
    assert gate_pass["ready_to_advance"] is True





