#!/usr/bin/env python3
"""Manage Public Core sync, host installation, hygiene audit, and release packaging.

Zero third-party dependencies. Never copies or overwrites private local overlays
(`local_config.yaml`, `local_overlay.md`, `*.local.*`).

Usage:
    # Install or update skills into a host directory (preserves existing local_* files)
    python scripts/manage_skills.py install --target antigravity|claude|codex|<path>

    # Maintainer: sync Public Core files from your live local skills folder into this repo
    python scripts/manage_skills.py sync --from ~/.gemini/config/skills

    # Audit Public Core hygiene, run pytest, and optionally build a clean release .zip
    python scripts/manage_skills.py check
    python scripts/manage_skills.py pack
"""

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

PUBLIC_SKILL_DIRS = [
    "baseline-killer-audit",
    "code-math-alignment",
    "idea-novelty-screen",
    "scientific-report-review",
]
PUBLIC_EXTRA_DIRS = [
    "tests",
]
PUBLIC_ROOT_FILES = [
    ".gitignore",
    "README.md",
    "DEVLOG.md",
    "config.example.yaml",
    "local_overlay.example.md",
]
REPO_ONLY_ITEMS = [
    "LICENSE",
    "VERSION",
    "examples",
    "scripts",
]

EXCLUDED_NAMES = {
    "local_config.yaml",
    "local_overlay.md",
    "__pycache__",
    ".pytest_cache",
    ".git",
    "dist",
}

RE_USER_PATH_LEAK = re.compile(
    r"(?:[A-Za-z]:\\Users\\[^\\\s\"'`]+|/Users/[^/\s\"'`]+|/home/[^/\s\"'`]+)"
)
RE_EXCLUDED_LOCAL = re.compile(r"\.local\.(?:yaml|yml|md)$", re.IGNORECASE)


def _is_excluded(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDED_NAMES or part.endswith(".pyc") or part.endswith(".pyo"):
            return True
        if RE_EXCLUDED_LOCAL.search(part):
            return True
    return False


def _copy_clean_tree(src_dir: Path, dst_dir: Path, prune: bool = True) -> int:
    """Copy src_dir -> dst_dir excluding private local overlays and caches."""
    copied = 0
    if prune and dst_dir.exists():
        shutil.rmtree(dst_dir)
    for src_file in sorted(src_dir.rglob("*")):
        rel = src_file.relative_to(src_dir)
        if _is_excluded(rel) or not src_file.is_file():
            continue
        out_file = dst_dir / rel
        out_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, out_file)
        copied += 1
    return copied


def _read_version() -> str:
    vf = REPO_ROOT / "VERSION"
    if vf.exists():
        return vf.read_text(encoding="utf-8").strip() or "0.0.0"
    return "0.0.0"


def cmd_sync(args) -> int:
    src_root = Path(args.source).expanduser().resolve()
    if not src_root.is_dir():
        print(f"ERROR: source directory not found: {src_root}", file=sys.stderr)
        return 1

    total = 0
    for dirname in PUBLIC_SKILL_DIRS + PUBLIC_EXTRA_DIRS:
        src_d = src_root / dirname
        if not src_d.is_dir():
            print(f"ERROR: expected directory missing in source: {src_d}", file=sys.stderr)
            return 1
        total += _copy_clean_tree(src_d, REPO_ROOT / dirname, prune=True)

    for fname in PUBLIC_ROOT_FILES:
        src_f = src_root / fname
        if src_f.is_file():
            shutil.copy2(src_f, REPO_ROOT / fname)
            total += 1
        else:
            print(f"WARNING: root file missing in source (skipped): {src_f}")

    # Safety sweep: ensure no private local overlays exist in repo root
    for forbidden in ("local_config.yaml", "local_overlay.md"):
        p = REPO_ROOT / forbidden
        if p.exists():
            print(f"WARNING: private overlay exists in repo root (gitignored, not synced): {p}")

    print(f"Synced {total} Public Core file(s) from {src_root} -> {REPO_ROOT}")
    return 0


def _resolve_target(target_arg: str) -> Path:
    key = target_arg.strip().lower()
    home = Path.home()
    presets = {
        "antigravity": home / ".gemini" / "config" / "skills",
        "claude": home / ".claude" / "skills",
        "codex": home / ".codex" / "skills",
    }
    if key in presets:
        return presets[key]
    return Path(target_arg).expanduser().resolve()


def cmd_install(args) -> int:
    dst_root = _resolve_target(args.target)
    dst_root.mkdir(parents=True, exist_ok=True)
    total = 0
    for dirname in PUBLIC_SKILL_DIRS:
        total += _copy_clean_tree(REPO_ROOT / dirname, dst_root / dirname, prune=True)
    for fname in ("config.example.yaml", "local_overlay.example.md", "README.md"):
        src_f = REPO_ROOT / fname
        if src_f.is_file():
            shutil.copy2(src_f, dst_root / fname)
            total += 1
    print(f"Installed {total} Public Core file(s) -> {dst_root}")
    print("Preserved any existing local_config.yaml / local_overlay.md.")
    return 0


def audit_public_core() -> list[str]:
    issues = []
    # 1. Check no private overlay files are present
    for p in REPO_ROOT.rglob("*"):
        rel = p.relative_to(REPO_ROOT)
        if ".git" in rel.parts or "dist" in rel.parts or "__pycache__" in rel.parts or ".pytest_cache" in rel.parts:
            continue
        if p.name in ("local_config.yaml", "local_overlay.md") or RE_EXCLUDED_LOCAL.search(p.name):
            issues.append(f"Private overlay present in repo tree: {rel}")

    # 2. Scan committed text files for personal absolute user paths
    for p in sorted(REPO_ROOT.rglob("*")):
        rel = p.relative_to(REPO_ROOT)
        if not p.is_file() or _is_excluded(rel) or ".git" in rel.parts or "dist" in rel.parts:
            continue
        if p.suffix.lower() not in {".md", ".py", ".yaml", ".yml", ".json", ".txt"}:
            continue
        if rel.as_posix() == "scripts/manage_skills.py":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for idx, line in enumerate(text.splitlines(), 1):
            if RE_USER_PATH_LEAK.search(line):
                issues.append(f"Absolute user-path leak in {rel}:{idx}: {line.strip()[:120]}")
    return issues


def cmd_check(_args) -> int:
    issues = audit_public_core()
    if issues:
        print("HYGIENE AUDIT FAILED:")
        for item in issues:
            print(f"  - {item}")
        return 1
    print("Hygiene audit passed: 0 private overlays, 0 absolute user-path leaks.")

    res = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short", str(REPO_ROOT / "tests" / "test_skills_suite.py")],
        cwd=str(REPO_ROOT),
    )
    return res.returncode


def cmd_pack(args) -> int:
    rc = cmd_check(args)
    if rc != 0:
        return rc

    version = _read_version()
    out_path = Path(args.output).expanduser().resolve() if args.output else (
        REPO_ROOT / "dist" / f"research-audit-skills-v{version}.zip"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    prefix = f"research-audit-skills-v{version}"
    included_roots = PUBLIC_SKILL_DIRS + PUBLIC_EXTRA_DIRS + PUBLIC_ROOT_FILES + REPO_ONLY_ITEMS
    count = 0
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in included_roots:
            p = REPO_ROOT / item
            if p.is_file():
                zf.write(p, f"{prefix}/{item}")
                count += 1
            elif p.is_dir():
                for child in sorted(p.rglob("*")):
                    rel = child.relative_to(REPO_ROOT)
                    if _is_excluded(rel) or not child.is_file():
                        continue
                    zf.write(child, f"{prefix}/{rel.as_posix()}")
                    count += 1

    print(f"Packed {count} Public Core file(s) -> {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Research Audit Skill Suite sync/install/pack tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="Sync Public Core files from local skills folder into this repo")
    p_sync.add_argument(
        "--from",
        dest="source",
        default=str(Path.home() / ".gemini" / "config" / "skills"),
        help="Source skills directory (default: ~/.gemini/config/skills)",
    )
    p_sync.set_defaults(func=cmd_sync)

    p_inst = sub.add_parser("install", help="Install/update skills into Antigravity, Claude Code, Codex, or custom dir")
    p_inst.add_argument(
        "--target",
        required=True,
        help="Target preset ('antigravity', 'claude', 'codex') or explicit directory path",
    )
    p_inst.set_defaults(func=cmd_install)

    p_chk = sub.add_parser("check", help="Run Public Core hygiene audit + pytest regression suite")
    p_chk.set_defaults(func=cmd_check)

    p_pack = sub.add_parser("pack", help="Run check and build a clean shareable .zip in dist/")
    p_pack.add_argument("--output", default="", help="Optional output zip path")
    p_pack.set_defaults(func=cmd_pack)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
