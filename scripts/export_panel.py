#!/usr/bin/env python3
"""Cross-host pure-Python CLI bridge for Claude Code, OpenAI Codex, and custom harnesses.

Runs the exact prompt builders, JSON schemas, 0-token pre-flight linter, cross-domain
overlay isolation, and fail-closed gates from `screen_idea.py` / `review_panel.py`
without requiring Antigravity's `run_workflow` runtime (zero external dependencies).

Usage:
    # 1. Export per-reviewer prompts + JSON schemas for any stage
    python scripts/export_panel.py export --workflow review --stage stage1 \
        --report reports/manuscript.tex --extra-files src/ --out-dir .audit_prompts

    python scripts/export_panel.py export --workflow screen --track numerical_algorithm \
        --idea "Adaptive importance sampling for ..." --out-dir .screen_prompts

    # 2. Evaluate the fail-closed gate on collected JSON reviewer outputs
    python scripts/export_panel.py gate --stage stage1a --results-dir .audit_results
"""

import argparse
import asyncio
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCREEN_SCRIPT = REPO_ROOT / "idea-novelty-screen" / "scripts" / "screen_idea.py"
REVIEW_SCRIPT = REPO_ROOT / "scientific-report-review" / "scripts" / "review_panel.py"

ADVISORY_REVIEWERS = {"average_reader"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "agent").lower()).strip("_")[:48]


def _extract_id(prompt: str, role: str) -> str:
    m = re.search(r"(?:reviewer_id|scout_id)='([^']+)'", prompt or "")
    if m:
        return m.group(1)
    return _slug(role)


def export_prompts(workflow: str, args_dict: dict, out_dir: Path, cwd: Path | None = None) -> dict:
    """Execute workflow script with a prompt-capturing shim (zero LLM calls)."""
    script_path = SCREEN_SCRIPT if workflow == "screen" else REVIEW_SCRIPT
    if not script_path.is_file():
        raise FileNotFoundError(f"Workflow script not found: {script_path}")

    # Skip Phase 2 Pivot Red-Team during dry export (it depends on Phase 1 candidate Pivots)
    export_args = dict(args_dict)
    export_args.setdefault("skip_pivot_red_team", True)

    src = script_path.read_text(encoding="utf-8")
    indented = "\n".join("    " + line for line in src.splitlines())
    wrapped = "async def _workflow_main():\n" + indented + "\n"
    code_obj = compile(wrapped, str(script_path), "exec")

    captured = []
    logs = []

    def _log(*parts):
        logs.append(" ".join(str(p) for p in parts))

    def _phase(name):
        logs.append(f"[PHASE] {name}")

    def _agent(prompt=None, schema=None, role=None, type_name="self", workspace="inherit", model=None):
        async def _coro():
            aid = _extract_id(prompt or "", role or "")
            captured.append(
                {
                    "id": aid,
                    "role": role or aid,
                    "agent_type": type_name,
                    "model": model or "inherit",
                    "requires_shell": aid == "code_math_auditor",
                    "requires_web_search": aid in ("supervisor_strategist", "literature_novelty_strategist"),
                    "prompt": prompt or "",
                    "schema": schema or {},
                }
            )
            # Minimal stub payload satisfying downstream gate aggregation during export
            stub = {"summary": "exported", "findings": [], "key_risks": [], "fatal_blocker_count": 0}
            if workflow == "screen":
                stub.update({"scout_id": aid, "scout_role": role or aid})
                if aid == "literature_novelty_strategist":
                    stub.update({"live_search_status": "searched_live", "novelty_verdict": "CLEAR_NOVELTY_ABOVE_BAR", "pivot_options": []})
            else:
                stub.update({"reviewer_id": aid, "reviewer_role": role or aid})
                if aid == "code_math_auditor":
                    stub.update({"stage0_verdict": "ALIGNED_FAIL_LOUD", "p0_p1_count": 0, "stage0_closed": True, "execution_status": "no_runnable_targets"})
                elif aid == "baseline_killer":
                    stub.update({"baseline_verdict": "SOLID_BASELINE", "p0_p1_count": 0, "stage1a_closed": True})
                elif aid == "supervisor_strategist":
                    stub.update({"live_search_status": "searched_live", "novelty_assessment": {"novelty_verdict": "CLEAR_NOVELTY_ABOVE_BAR"}, "candidate_pivots": []})
                elif aid == "reproducibility_code":
                    stub.update({"reproducibility_rating": "sufficient"})
            return stub

        return _coro()

    async def _parallel(items, fn):
        return await asyncio.gather(*(fn(item) for item in items))

    ns = {
        "__file__": str(script_path),
        "args": export_args,
        "log": _log,
        "phase": _phase,
        "agent": _agent,
        "parallel": _parallel,
    }
    prev_cwd = Path.cwd()
    try:
        if cwd is not None:
            import os
            os.chdir(cwd)
        exec(code_obj, ns)
        buf = io.StringIO()
        with redirect_stdout(buf):
            asyncio.run(ns["_workflow_main"]())
    finally:
        import os
        os.chdir(prev_cwd)

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_agents = []
    for idx, item in enumerate(captured, 1):
        stem = f"{idx:02d}_{_slug(item['id'])}"
        if "PASS 1/2" in item["prompt"]:
            stem += "_pass1_main_only"
        elif "PASS 2/2" in item["prompt"]:
            stem += "_pass2_main_si"
        prompt_file = out_dir / f"{stem}.prompt.md"
        schema_file = out_dir / f"{stem}.schema.json"
        prompt_file.write_text(item["prompt"], encoding="utf-8")
        schema_file.write_text(json.dumps(item["schema"], indent=2), encoding="utf-8")
        manifest_agents.append(
            {
                "index": idx,
                "id": item["id"],
                "role": item["role"],
                "recommended_model": item["model"],
                "requires_read_only_shell": item["requires_shell"],
                "requires_web_search": item["requires_web_search"],
                "prompt_file": prompt_file.name,
                "schema_file": schema_file.name,
            }
        )

    manifest = {
        "workflow": workflow,
        "args": export_args,
        "logs": logs,
        "agent_count": len(manifest_agents),
        "agents": manifest_agents,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def evaluate_gate(stage: str, reviews: list[dict], mode: str = "review") -> dict:
    """Deterministic fail-closed Stage 0 / 1 / 2 / 3 gate evaluator for non-Antigravity hosts."""
    items_key = "findings" if mode == "review" else "remaining_or_new_findings"
    blocking = []
    total_p0_p1 = 0

    for rev in reviews:
        rid = rev.get("reviewer_id", "")
        if rid in ADVISORY_REVIEWERS:
            continue
        p01 = (
            rev["p0_p1_count"]
            if isinstance(rev.get("p0_p1_count"), int)
            else sum(1 for it in rev.get(items_key, []) if it.get("priority") == "essential")
        )
        total_p0_p1 += p01

        if rid == "code_math_auditor":
            v = rev.get("stage0_verdict", "SILENT_POLLUTION_RISK")
            ex = rev.get("execution_status", "no_runnable_targets")
            if not (p01 == 0 and v == "ALIGNED_FAIL_LOUD" and ex in ("executed_passed", "no_runnable_targets")):
                blocking.append(f"stage0_open (verdict={v}, p0_p1={p01}, exec={ex})")
        elif rid == "baseline_killer":
            v = rev.get("baseline_verdict", "REPAIR_RISK_PILOT_REQUIRED")
            if not (p01 == 0 and v == "SOLID_BASELINE"):
                blocking.append(f"stage1a_open (verdict={v}, p0_p1={p01})")
        elif rid == "supervisor_strategist":
            nov = (rev.get("novelty_assessment") or {}).get("novelty_verdict")
            if nov == "OVERLAP_OR_INCREMENTAL_RISK":
                blocking.append("novelty_verdict=OVERLAP_OR_INCREMENTAL_RISK")
            if rev.get("live_search_status") == "blocked_or_offline":
                blocking.append("r9_live_search=blocked_or_offline")
        elif rid == "reproducibility_code":
            if rev.get("reproducibility_rating") == "insufficient":
                blocking.append("reproducibility_rating=insufficient")

        if mode == "recheck" and rev.get("domain_verdict") in (
            "not_ready_important_info_missing",
            "not_ready_major_gaps_remain",
        ):
            blocking.append(f"{rid}:{rev['domain_verdict']}")

    if total_p0_p1 > 0:
        blocking.insert(0, f"total_p0_p1_count={total_p0_p1}")

    return {
        "stage": stage,
        "mode": mode,
        "reviewers_evaluated": [r.get("reviewer_id", "unknown") for r in reviews],
        "total_p0_p1_count": total_p0_p1,
        "blocking_reasons": blocking,
        "ready_to_advance": len(blocking) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-host prompt exporter & fail-closed gate evaluator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_exp = sub.add_parser("export", help="Export exact per-agent prompts and JSON schemas")
    p_exp.add_argument("--workflow", choices=("review", "screen"), required=True)
    p_exp.add_argument("--out-dir", required=True, help="Output directory for prompts, schemas, and manifest.json")
    p_exp.add_argument("--stage", default="stage0", help="Stage for --workflow review (stage0, stage1a, stage1b, stage1, stage2, stage3)")
    p_exp.add_argument("--mode", default="review", choices=("review", "recheck"))
    p_exp.add_argument("--report", nargs="*", default=[], help="Manuscript / spec file path(s)")
    p_exp.add_argument("--extra-files", nargs="*", default=[], help="Code, configs, tests, .bib, or SI file(s)")
    p_exp.add_argument("--track", default="auto", help="Track for --workflow screen (numerical_algorithm, pure_theory, engineering_portfolio, auto)")
    p_exp.add_argument("--idea", default="", help="Idea pitch text for --workflow screen")
    p_exp.add_argument("--idea-files", nargs="*", default=[], help="Idea note file(s) for --workflow screen")
    p_exp.add_argument("--domain", default="", help="Explicit research domain (auto-suppresses mismatched local overlay)")
    p_exp.add_argument("--target-venue", default="", help="Target venue or agency")
    p_exp.add_argument("--args-json", default="", help="Optional JSON file with full workflow Args overrides")

    p_gate = sub.add_parser("gate", help="Evaluate fail-closed stage gate over collected reviewer JSON files")
    p_gate.add_argument("--stage", required=True)
    p_gate.add_argument("--mode", default="review", choices=("review", "recheck"))
    p_gate.add_argument("--results-dir", required=True, help="Directory of reviewer output *.json files")

    args = parser.parse_args()

    if args.command == "export":
        payload = {}
        if args.args_json:
            payload.update(json.loads(Path(args.args_json).read_text(encoding="utf-8")))
        if args.workflow == "review":
            payload.setdefault("stage", args.stage)
            payload.setdefault("mode", args.mode)
            if args.report:
                payload["report"] = args.report
            if args.extra_files:
                payload["extra_files"] = args.extra_files
        else:
            payload.setdefault("track", args.track)
            if args.idea:
                payload["idea"] = args.idea
            if args.idea_files:
                payload["idea_files"] = args.idea_files
        if args.domain:
            payload["domain"] = args.domain
        if args.target_venue:
            payload["target_venue"] = args.target_venue

        manifest = export_prompts(args.workflow, payload, Path(args.out_dir))
        print(json.dumps(manifest, indent=2))
        return 0

    results_dir = Path(args.results_dir)
    reviews = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(results_dir.glob("*.json"))
        if p.name != "manifest.json"
    ]
    gate = evaluate_gate(args.stage, reviews, mode=args.mode)
    print(json.dumps(gate, indent=2))
    return 0 if gate["ready_to_advance"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
