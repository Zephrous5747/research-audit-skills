# Local Lab Overlay (Example)

Copy this file to `local_overlay.md` (gitignored) to inject optional lab-specific
priors, compute-cluster constraints, domain terminology, or private workspace
conventions into `idea-novelty-screen` and `scientific-report-review`.

Both workflow scripts load `local_overlay.md` automatically when present (checking
workspace `.agents/skills/` first, then the skill suite root) and run cleanly
with generic Public Core defaults when absent.

## Domain & Benchmark Priors
- Primary domain conventions, standard baselines, proxy/surrogate models, or benchmark suites.

## Compute & Cluster Hygiene
- Local HPC/SLURM cluster names, walltime/checkpointing expectations, or thread-lock requirements.

## Local Workspace & Style Priors (Optional)
- Private manuscript conventions or recurring review priorities specific to your group.
