"""
Deterministic 0-token pre-flight linter for scientific-report-review.

Runs locally in < 1 s with zero LLM tokens before spawning blind reviewers,
giving Reviewers 0, 4, 5, and 6 exact file:line mechanical findings so they
can spend 100% of their reasoning budget on deep code/science/craft issues.

Checks:
    - Code hygiene (for Stage 0 / Reviewer 0):
        * Bare `except:` or silent `except ...: pass`
        * Hardcoded `np.clip` / tolerance/fallback patterns
        * Parallel/cluster worker scripts missing BLAS/Rust thread locks
        * Non-atomic direct writes to shared result/checkpoint files
    - LaTeX, BibTeX & Figure hygiene (for Stage 2 / Reviewer 5):
        * Existing sibling `.log` / `.blg` warnings (Overfull hbox, undefined ref/cite, BibTeX warnings)
        * Straight ASCII double quotes `"..."` inside `.tex` prose
        * `.bib` entries missing year, volume, or pages/article-id
        * Plotting scripts using `plt.title`/`set_title` (advisory), very thin linewidths (< 1.0), or very small fontsizes (< 8 pt)
    - Prose & AI-tell mechanical scan (for Reviewers 4 & 6):
        * Sentence-initial abbreviations (`Eq.`, `Eqs.`, `Fig.`, `Figs.`, `Tab.`, `Sec.`)
        * Em-dashes (`---` or Unicode `—`)
        * High-signal AI buzzwords & hype phrases
        * Wordy filler phrases (`We decided to use`, `the fact that`, `As previously mentioned`, etc.)
        * Overlong sentences (> 35 words)
    - Storyflow & cognitive-load scan (for Reviewer 1):
        * Math-wall bursts (>= 6-line display-math block, or >= 3 clustered blocks with < 25 prose words between them)
        * Symbol-density / working-memory spikes (>= 10 inline math spans with >= 6 distinct tokens, or >= 4 compound sub/superscripts in one paragraph)
        * Unanchored long prose stretches (>= 450 words without a heading or figure/table anchor)

CLI usage:
    python preflight_lint.py path1.py path2.py --reviewer code_math_auditor
    python preflight_lint.py reports/manuscript.tex reports/refs.bib --reviewer figures_refs_format
    python preflight_lint.py reports/manuscript.tex --base-dir reports
"""

import argparse
import json
import re
import sys
from pathlib import Path

MAX_HITS_PER_CATEGORY = 25

CODE_EXTS = {".py", ".sh", ".sbatch", ".slurm", ".rs"}
TEX_EXTS = {".tex", ".md"}
BIB_EXTS = {".bib"}

# --- Patterns ---

RE_BARE_EXCEPT = re.compile(r"^\s*except\s*:")
RE_EXCEPT_PASS = re.compile(r"^\s*except\b[^:]*:\s*(pass|\.\.\.)\s*(#.*)?$")
RE_NP_CLIP = re.compile(r"\b(np\.clip|numpy\.clip|torch\.clamp)\s*\(")
RE_PARALLEL_HINT = re.compile(
    r"\b(ProcessPoolExecutor|multiprocessing|joblib|Parallel|ray\.init|sbatch|#SBATCH|Pool\s*\()"
)
RE_THREAD_LOCKS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "RAYON_NUM_THREADS")
RE_DIRECT_WRITE = re.compile(
    r"(\.write_text\s*\(|\.write_bytes\s*\(|\.to_csv\s*\(|json\.dump\s*\(|np\.savez?\s*\(|open\s*\([^)]*['\"][wa][bt+]?['\"])"
)
RE_ATOMIC_HINT = re.compile(r"\b(os\.replace|Path\.replace|\.replace\s*\(|NamedTemporaryFile|tempfile)\b")

RE_SENT_INIT_ABBR = re.compile(
    r"(?:^|[.!?]\s+)(Eqs?\.|Figs?\.|Tabs?\.|Secs?\.)\s"
)
RE_STRAIGHT_QUOTE = re.compile(r'(?<!\\)"')
RE_EM_DASH = re.compile(r"(—|(?<!-)---(?!-))")

AI_TELL_PHRASES = [
    r"\bdelve[sd]?\b",
    r"\bunderscor(?:e[sd]?|ing)\b",
    r"\btapestry\b",
    r"\btestament\b",
    r"\bpivotal\b",
    r"\bshowcas(?:e[sd]?|ing)\b",
    r"\bseamless(?:ly)?\b",
    r"\bgroundbreaking\b",
    r"\bpaves?\s+the\s+way\b",
    r"\bof\s+paramount\s+importance\b",
    r"\bsheds?\s+light\s+on\b",
    r"\bopens?\s+new\s+avenues\b",
    r"\bbridges?\s+the\s+gap\b",
    r"\bto\s+the\s+best\s+of\s+our\s+knowledge\b",
    r"\bin\s+recent\s+years\b",
    r"\bwith\s+the\s+rapid\s+development\b",
    r"\bit\s+is\s+worth\s+noting\s+that\b",
    r"\bit\s+should\s+be\s+emphasized\s+that\b",
    r"\bserves?\s+as\b",
]
RE_AI_TELLS = re.compile("|".join(AI_TELL_PHRASES), re.IGNORECASE)

WORDY_FILLERS = [
    r"\bwe\s+decided\s+to\s+use\b",
    r"\bwe\s+concluded\s+to\b",
    r"\bas\s+we\s+already\s+know\b",
    r"\bas\s+previously\s+mentioned\b",
    r"\bthe\s+reader\s+could\s+wonder\b",
    r"\bone\s+can\s+ask\b",
    r"\bthe\s+fact\s+that\b",
    r"\bin\s+fact\b",
]
RE_WORDY_FILLERS = re.compile("|".join(WORDY_FILLERS), re.IGNORECASE)

RE_PLOT_SCRIPT_HINT = re.compile(r"\b(matplotlib|pyplot|plt\.|savefig|ax\.plot)\b")
RE_PLOT_TITLE = re.compile(r"\b(plt\.title|set_title|suptitle)\s*\(")
RE_PLOT_LW = re.compile(r"\b(?:linewidth|lw)\s*=\s*([0-9]*\.?[0-9]+)")
RE_PLOT_FS = re.compile(r"\b(?:fontsize|labelsize)\s*=\s*([0-9]*\.?[0-9]+)")


def _expand_paths(paths, base_dir=None):
    resolved = []
    seen = set()
    root = Path(base_dir) if base_dir else Path.cwd()
    for raw in paths:
        if not raw:
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = root / p
        if not p.exists():
            continue
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix.lower() in (CODE_EXTS | TEX_EXTS | BIB_EXTS):
                    if "__pycache__" in child.parts or ".git" in child.parts:
                        continue
                    key = str(child.resolve())
                    if key not in seen:
                        seen.add(key)
                        resolved.append(child)
        else:
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                resolved.append(p)
    return resolved


def _rel(path, base_dir=None):
    try:
        return str(path.resolve().relative_to((Path(base_dir) if base_dir else Path.cwd()).resolve()))
    except Exception:
        return str(path)


def _strip_tex_comment(line):
    out = []
    escaped = False
    for ch in line:
        if ch == "%" and not escaped:
            break
        escaped = (ch == "\\") and not escaped
        out.append(ch)
    return "".join(out)


def _add_hit(bucket, entry):
    if len(bucket) < MAX_HITS_PER_CATEGORY:
        bucket.append(entry)


def lint_code_files(files, base_dir=None):
    hits = {
        "bare_or_silent_except": [],
        "clip_or_clamp_calls": [],
        "missing_thread_locks": [],
        "potential_non_atomic_writes": [],
        "plot_script_hygiene": [],
    }
    for p in files:
        if p.suffix.lower() not in CODE_EXTS:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        lines = text.splitlines()
        rel = _rel(p, base_dir)

        for idx, line in enumerate(lines, 1):
            if RE_BARE_EXCEPT.search(line) or RE_EXCEPT_PASS.search(line):
                _add_hit(hits["bare_or_silent_except"], f"{rel}:{idx}: {line.strip()[:120]}")
            elif line.strip().startswith("except") and idx < len(lines):
                nxt = lines[idx].strip()
                if nxt in ("pass", "..."):
                    _add_hit(hits["bare_or_silent_except"], f"{rel}:{idx}-{idx+1}: {line.strip()} -> {nxt}")
            if RE_NP_CLIP.search(line):
                _add_hit(hits["clip_or_clamp_calls"], f"{rel}:{idx}: {line.strip()[:120]}")

        if RE_PARALLEL_HINT.search(text):
            missing = [var for var in RE_THREAD_LOCKS if var not in text]
            if missing:
                _add_hit(
                    hits["missing_thread_locks"],
                    f"{rel}: uses parallel/Slurm workers but missing {', '.join(missing)}",
                )

        if RE_DIRECT_WRITE.search(text) and not RE_ATOMIC_HINT.search(text):
            if "test_" not in p.name and p.suffix.lower() == ".py":
                for idx, line in enumerate(lines, 1):
                    if RE_DIRECT_WRITE.search(line):
                        _add_hit(
                            hits["potential_non_atomic_writes"],
                            f"{rel}:{idx}: {line.strip()[:120]} (no os.replace/tempfile detected in file)",
                        )
                        break

        if p.suffix.lower() == ".py" and RE_PLOT_SCRIPT_HINT.search(text):
            for idx, line in enumerate(lines, 1):
                if RE_PLOT_TITLE.search(line):
                    _add_hit(
                        hits["plot_script_hygiene"],
                        f"{rel}:{idx}: advisory: embedded figure title ({line.strip()[:100]}) — short panel labels are fine, omit titles repeating the caption",
                    )
                m_lw = RE_PLOT_LW.search(line)
                if m_lw and float(m_lw.group(1)) < 1.0:
                    _add_hit(
                        hits["plot_script_hygiene"],
                        f"{rel}:{idx}: advisory: very thin linewidth={m_lw.group(1)} (< 1.0); verify legibility at final printed size",
                    )
                m_fs = RE_PLOT_FS.search(line)
                if m_fs and float(m_fs.group(1)) < 8.0:
                    _add_hit(
                        hits["plot_script_hygiene"],
                        f"{rel}:{idx}: advisory: very small font size={m_fs.group(1)} (< 8 pt); verify legibility at final printed size",
                    )

    return {k: v for k, v in hits.items() if v}


def lint_tex_and_md_files(files, base_dir=None):
    hits = {
        "sentence_initial_abbreviations": [],
        "straight_latex_quotes": [],
        "em_dashes": [],
        "ai_tell_phrases": [],
        "wordy_fillers": [],
        "overlong_sentences_gt35w": [],
        "latex_build_log_warnings": [],
    }
    checked_logs = set()

    for p in files:
        if p.suffix.lower() not in TEX_EXTS:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = _rel(p, base_dir)
        is_tex = p.suffix.lower() == ".tex"
        is_md = p.suffix.lower() == ".md"
        in_verbatim_or_math = False
        in_md_frontmatter = False
        in_md_fence = False
        prose_chunks = []

        for idx, raw_line in enumerate(text.splitlines(), 1):
            line = _strip_tex_comment(raw_line) if is_tex else raw_line
            stripped = line.strip()
            if not stripped:
                prose_chunks.append((idx, ""))
                continue

            if is_md:
                if idx == 1 and stripped == "---":
                    in_md_frontmatter = True
                    continue
                if in_md_frontmatter:
                    if stripped in ("---", "..."):
                        in_md_frontmatter = False
                    continue
                if stripped.startswith(("```", "~~~")):
                    in_md_fence = not in_md_fence
                    continue
                if in_md_fence:
                    continue

            if is_tex:
                if re.search(r"\\begin\{(equation|align|gather|multline|verbatim|lstlisting|tikzpicture|tabular)\*?\}", stripped):
                    in_verbatim_or_math = True
                    prose_chunks.append((idx, ""))
                if re.search(r"\\end\{(equation|align|gather|multline|verbatim|lstlisting|tikzpicture|tabular)\*?\}", stripped):
                    in_verbatim_or_math = False
                    prose_chunks.append((idx, ""))
                    continue
                if in_verbatim_or_math or stripped.startswith(("\\newcommand", "\\def", "\\usepackage", "\\label", "\\graphicspath")):
                    continue

            if RE_SENT_INIT_ABBR.search(line):
                _add_hit(hits["sentence_initial_abbreviations"], f"{rel}:{idx}: {stripped[:130]}")
            if is_tex and RE_STRAIGHT_QUOTE.search(line) and not re.search(r'\\(verb|url|href|path)\b', line):
                _add_hit(hits["straight_latex_quotes"], f"{rel}:{idx}: {stripped[:130]}")
            is_md_hr_or_table = is_md and (
                re.fullmatch(r"[-*_]{3,}", stripped) is not None
                or re.fullmatch(r"\|?[\s:-]+\|[\s|:-]*", stripped) is not None
            )
            if not is_md_hr_or_table and RE_EM_DASH.search(line):
                _add_hit(hits["em_dashes"], f"{rel}:{idx}: {stripped[:130]}")
            m_ai = RE_AI_TELLS.search(line)
            if m_ai:
                _add_hit(hits["ai_tell_phrases"], f"{rel}:{idx} [{m_ai.group(0)}]: {stripped[:120]}")
            m_wf = RE_WORDY_FILLERS.search(line)
            if m_wf:
                _add_hit(hits["wordy_fillers"], f"{rel}:{idx} [{m_wf.group(0)}]: {stripped[:120]}")

            if not stripped.startswith(("\\section", "\\subsection", "\\subsubsection", "\\caption", "#")):
                prose_chunks.append((idx, stripped))

        # Paragraph-level overlong sentence detector (> 35 words)
        para_lines = []
        para_start = None
        for idx, s in prose_chunks + [(0, "")]:
            if not s:
                if para_lines:
                    para = " ".join(para_lines)
                    # Mask common abbreviations before splitting sentences
                    masked = re.sub(r"\b(Eq|Eqs|Fig|Figs|Tab|Tabs|Sec|Secs|Ref|Refs|et al|e\.g|i\.e|vs|Dr|Prof)\.", r"\1<DOT>", para)
                    for sent in re.split(r"(?<=[.!?])\s+", masked):
                        clean = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", sent)
                        words = [w for w in re.findall(r"[A-Za-z0-9'-]+", clean) if len(w) > 0]
                        if len(words) > 35:
                            preview = sent.replace("<DOT>", ".")[:130]
                            _add_hit(
                                hits["overlong_sentences_gt35w"],
                                f"{rel}:~{para_start} ({len(words)} words): {preview}...",
                            )
                    para_lines = []
                    para_start = None
            else:
                if para_start is None:
                    para_start = idx
                para_lines.append(s)

        # Inspect sibling or _build/build .log / .blg if already present (read-only, zero compile cost)
        if is_tex:
            for ext in (".log", ".blg"):
                for log_path in (
                    p.with_suffix(ext),
                    p.parent / "_build" / (p.stem + ext),
                    p.parent / "build" / (p.stem + ext),
                ):
                    if not log_path.exists():
                        continue
                    key = str(log_path.resolve())
                    if key in checked_logs:
                        continue
                    checked_logs.add(key)
                    try:
                        log_text = log_path.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        continue
                    lrel = _rel(log_path, base_dir)
                    for lidx, lline in enumerate(log_text.splitlines(), 1):
                        if any(
                            tok in lline
                            for tok in (
                                "Overfull \\hbox",
                                "LaTeX Warning: Reference",
                                "LaTeX Warning: Citation",
                                "LaTeX Warning: There were undefined",
                                "Warning--",
                                "Multiply defined labels",
                            )
                        ):
                            _add_hit(hits["latex_build_log_warnings"], f"{lrel}:{lidx}: {lline.strip()[:140]}")

    return {k: v for k, v in hits.items() if v}


def lint_bib_files(files, base_dir=None):
    hits = {"bib_incomplete_entries": []}
    for p in files:
        if p.suffix.lower() not in BIB_EXTS:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = _rel(p, base_dir)
        entries = re.split(r"(?=@\w+\s*\{)", text)
        for entry in entries:
            m_head = re.match(r"@(\w+)\s*\{\s*([^,\s]+)", entry)
            if not m_head:
                continue
            etype = m_head.group(1).lower()
            key = m_head.group(2)
            if etype in ("comment", "preamble", "string"):
                continue
            low = entry.lower()
            has_field = lambda fname: re.search(r"(?:^|[,\s{])" + fname + r"\s*=", low) is not None
            missing = []
            if not has_field("year"):
                missing.append("year")
            if etype == "article":
                if not has_field("journal"):
                    missing.append("journal")
                if not (has_field("volume") or has_field("eprint") or has_field("doi")):
                    missing.append("volume")
                if not (has_field("pages") or has_field("eid") or has_field("eprint")):
                    missing.append("pages/eid")
            if missing:
                _add_hit(hits["bib_incomplete_entries"], f"{rel} [{key} ({etype})]: missing {', '.join(missing)}")
    return {k: v for k, v in hits.items() if v}


def _extract_braced_commands(text, command_name):
    """Extract balanced-brace bodies for `\\command_name[opt]{...}` (handles nested `{...}`)."""
    bodies = []
    pattern = re.compile(r"\\" + re.escape(command_name) + r"\*?(?:\[[^\]]*\])?\s*\{")
    for m in pattern.finditer(text):
        i = m.end()
        depth = 1
        start = i
        while i < len(text) and depth > 0:
            ch = text[i]
            if ch == "\\" and i + 1 < len(text):
                i += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        if depth == 0:
            bodies.append(text[start : i - 1])
    return bodies


def _scan_table_lines(label, tlines, bucket):
    """Compute exact row count, '--' sparsity, and near-constant columns for a table block."""
    rows = []
    for raw_line in tlines:
        s = _strip_tex_comment(raw_line).strip()
        if not s or s.startswith(("\\hline", "\\toprule", "\\midrule", "\\bottomrule", "\\multicolumn", "\\cline", "\\addlinespace")):
            continue
        if "&" in s and "\\\\" in s:
            row_txt = s.split("\\\\", 1)[0]
            cells = [c.strip() for c in row_txt.split("&")]
            if len(cells) >= 2:
                rows.append(cells)
    if len(rows) < 4:
        return
    ncols = max(len(r) for r in rows)
    total_cells = sum(len(r) for r in rows)
    dash_cells = sum(1 for r in rows for c in r if c in ("--", "---", "-", "", r"\text{--}"))
    dash_pct = 100.0 * dash_cells / max(total_cells, 1)
    const_cols = []
    for ci in range(ncols):
        vals = [r[ci] for r in rows if ci < len(r)]
        if len(vals) >= 6:
            top_val = max(set(vals), key=vals.count)
            if vals.count(top_val) / len(vals) >= 0.85:
                const_cols.append(f"col{ci+1}='{top_val}'({vals.count(top_val)}/{len(vals)})")
    if len(rows) >= 20 or dash_pct >= 20.0 or const_cols:
        parts = [f"{len(rows)} data rows"]
        if dash_cells:
            parts.append(f"{dash_cells}/{total_cells} ({dash_pct:.0f}%) '--' cells")
        if const_cols:
            parts.append("near-constant: " + ", ".join(const_cols[:3]))
        _add_hit(bucket, f"{label}: " + "; ".join(parts))


def lint_compression_metrics(files, base_dir=None):
    """0-token structural bloat, table sparsity/constancy, and orphan-file metrics for Stage 2B."""
    out = {
        "prose_density": [],
        "long_paragraphs_ge150w": [],
        "table_bloat_and_sparsity": [],
        "repeated_caption_phrases": [],
        "orphan_generated_tex": [],
    }
    tex_files = [p for p in files if p.suffix.lower() == ".tex"]
    if not tex_files:
        return {}

    referenced_stems = set()
    generated_dirs = set()
    caption_ngrams = {}
    table_targets = []
    seen_tables = set()
    inline_tables = []

    for p in tex_files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = _rel(p, base_dir)
        gen_dir = p.parent / "generated"
        if gen_dir.is_dir():
            generated_dirs.add(gen_dir.resolve())

        uncommented = "\n".join(_strip_tex_comment(l) for l in text.splitlines())
        for m in re.finditer(r"\\input\{([^}]+)\}", uncommented):
            raw_ref = m.group(1).strip()
            ref_path = p.parent / (raw_ref if raw_ref.endswith(".tex") else raw_ref + ".tex")
            referenced_stems.add(ref_path.name)
            if ref_path.exists():
                key = str(ref_path.resolve())
                if key not in seen_tables:
                    seen_tables.add(key)
                    table_targets.append(ref_path)

        if p.parent.name.lower() == "generated":
            key = str(p.resolve())
            if key not in seen_tables:
                seen_tables.add(key)
                table_targets.append(p)
            continue

        # Collect inline \begin{tabular}...\end{tabular} blocks directly inside main/SI .tex files
        in_tab = False
        tab_start = None
        tab_buf = []
        for idx, raw_line in enumerate(text.splitlines(), 1):
            s = _strip_tex_comment(raw_line)
            if not in_tab and re.search(r"\\begin\{tabular\*?\}", s):
                in_tab = True
                tab_start = idx
                tab_buf = [s]
                if re.search(r"\\end\{tabular\*?\}", s):
                    inline_tables.append((f"{rel}:L{tab_start} (inline tabular)", tab_buf))
                    in_tab = False
                    tab_buf = []
            elif in_tab:
                tab_buf.append(s)
                if re.search(r"\\end\{tabular\*?\}", s):
                    inline_tables.append((f"{rel}:L{tab_start} (inline tabular)", tab_buf))
                    in_tab = False
                    tab_buf = []

        # Prose density & wall-of-text paragraphs (>= 150 words)
        in_block = False
        total_words, long_parens = 0, 0
        para_words, para_start = 0, None
        for idx, raw_line in enumerate(text.splitlines(), 1):
            line = _strip_tex_comment(raw_line).strip()
            if re.search(r"\\begin\{(equation|align|gather|multline|verbatim|lstlisting|tikzpicture|tabular|table)\*?\}", line):
                in_block = True
            if re.search(r"\\end\{(equation|align|gather|multline|verbatim|lstlisting|tikzpicture|tabular|table)\*?\}", line):
                in_block = False
                continue
            if in_block or line.startswith(("\\newcommand", "\\def", "\\usepackage", "\\label")):
                continue
            if not line or line.startswith(("\\section", "\\subsection", "\\subsubsection")):
                if para_words >= 150 and para_start:
                    _add_hit(out["long_paragraphs_ge150w"], f"{rel}:L{para_start} (~{para_words} words)")
                para_words, para_start = 0, None
                continue
            for m_par in re.finditer(r"\([^()]{160,}\)", line):
                long_parens += 1
            clean = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", line)
            wc = len(re.findall(r"[A-Za-z0-9'-]+", clean))
            total_words += wc
            if para_start is None:
                para_start = idx
            para_words += wc
        if para_words >= 150 and para_start:
            _add_hit(out["long_paragraphs_ge150w"], f"{rel}:L{para_start} (~{para_words} words)")
        if total_words > 0:
            _add_hit(out["prose_density"], f"{rel}: ~{total_words} prose words, {long_parens} parenthetical(s) >= 160 chars")

        # Repeated 5-word caption boilerplate (balanced braces support nested LaTeX commands)
        for cap_body in _extract_braced_commands(uncommented, "caption"):
            if len(cap_body) < 30:
                continue
            plain_cap = re.sub(r"\\[a-zA-Z]+\*?", " ", cap_body)
            words = re.findall(r"[a-z0-9]+", plain_cap.lower())
            seen_in_cap = set()
            for i in range(max(0, len(words) - 4)):
                ng = " ".join(words[i : i + 5])
                if ng not in seen_in_cap:
                    seen_in_cap.add(ng)
                    caption_ngrams[ng] = caption_ngrams.get(ng, 0) + 1

    for ng, cnt in sorted(caption_ngrams.items(), key=lambda kv: -kv[1])[:8]:
        if cnt >= 4:
            _add_hit(out["repeated_caption_phrases"], f"'{ng}' appears in {cnt} captions")

    # Table body exact row count, '--' sparsity, and constant-column scan (file + inline)
    for tp in table_targets:
        try:
            tlines = tp.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        _scan_table_lines(_rel(tp, base_dir), tlines, out["table_bloat_and_sparsity"])
    for label, tlines in inline_tables:
        _scan_table_lines(label, tlines, out["table_bloat_and_sparsity"])

    # Orphan .tex files in sibling generated/ directories
    for gdir in sorted(generated_dirs):
        for child in sorted(gdir.glob("*.tex")):
            if child.name not in referenced_stems:
                _add_hit(out["orphan_generated_tex"], _rel(child, base_dir))

    return {k: v for k, v in out.items() if v}


RE_MATH_BEGIN = re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray|flalign)\*?\}")
RE_MATH_END = re.compile(r"\\end\{(equation|align|gather|multline|eqnarray|flalign)\*?\}")
RE_NON_PROSE_BEGIN = re.compile(r"\\begin\{(verbatim|lstlisting|tikzpicture|tabular\*?|table\*?)\}")
RE_NON_PROSE_END = re.compile(r"\\end\{(verbatim|lstlisting|tikzpicture|tabular\*?|table\*?)\}")
RE_INLINE_MATH = re.compile(r"(?<!\$)\$(?!\$)([^$\n]+?)(?<!\$)\$(?!\$)|\\\((.+?)\\\)")
RE_NESTED_SCRIPTS = re.compile(r"(?:_\{[^}]+\}\^|\^\{[^}]+\}_|_[A-Za-z0-9]\^|\^[A-Za-z0-9]_)")
RE_ANCHOR_CUE = re.compile(
    r"(?:\\(?:sub)*section\*?\{|^#{1,4}\s+|\\begin\{(?:figure|table)\*?\}|\\ref\{(?:fig|tab)[^}]*\}|\b(?:Figs?\.|Figures?|Tables?|Tabs?\.)\s*\d+)",
    re.IGNORECASE,
)


def lint_storyflow_load(files, base_dir=None):
    """0-token structural cognitive-load proxies for Reviewer 1 (math walls, symbol bursts, unanchored stretches)."""
    out = {
        "math_walls": [],
        "symbol_density_spikes": [],
        "unanchored_long_stretches": [],
    }
    for p in files:
        if p.suffix.lower() not in TEX_EXTS:
            continue
        if p.parent.name.lower() == "generated":
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = _rel(p, base_dir)
        is_tex = p.suffix.lower() == ".tex"
        lines = text.splitlines()

        start_idx = 0
        if is_tex:
            for i, raw in enumerate(lines):
                if r"\begin{document}" in _strip_tex_comment(raw):
                    start_idx = i + 1
                    break

        in_math = False
        math_delim = ""
        math_start = 0
        math_nonempty = 0
        in_non_prose = False
        in_md_fence = False

        cluster_count = 0
        cluster_start = 0
        cluster_last_end = 0
        words_since_math = 9999

        para_start = None
        para_inline_tokens = []
        para_nested_scripts = 0

        stretch_start = None
        stretch_words = 0

        def _flush_para():
            nonlocal para_start, para_inline_tokens, para_nested_scripts
            if para_start is not None:
                n_spans = len(para_inline_tokens)
                n_distinct = len(set(para_inline_tokens))
                if (n_spans >= 10 and n_distinct >= 6) or para_nested_scripts >= 4:
                    _add_hit(
                        out["symbol_density_spikes"],
                        f"{rel}:L{para_start}: {n_spans} inline math spans ({n_distinct} distinct), "
                        f"{para_nested_scripts} compound sub/superscript token(s) in one paragraph",
                    )
            para_start = None
            para_inline_tokens = []
            para_nested_scripts = 0

        def _flush_cluster():
            nonlocal cluster_count, cluster_start, cluster_last_end
            if cluster_count >= 3:
                _add_hit(
                    out["math_walls"],
                    f"{rel}:L{cluster_start}-L{cluster_last_end}: {cluster_count} clustered display-math blocks with minimal intervening prose",
                )
            cluster_count = 0
            cluster_start = 0
            cluster_last_end = 0

        def _flush_stretch(end_line):
            nonlocal stretch_start, stretch_words
            if stretch_start is not None and stretch_words >= 450:
                _add_hit(
                    out["unanchored_long_stretches"],
                    f"{rel}:L{stretch_start}-L{end_line}: ~{stretch_words} prose words without a heading or figure/table anchor",
                )
            stretch_start = None
            stretch_words = 0

        def _record_math_block(b_start, b_end, n_lines):
            nonlocal cluster_count, cluster_start, cluster_last_end, words_since_math
            if n_lines >= 6:
                _add_hit(
                    out["math_walls"],
                    f"{rel}:L{b_start}-L{b_end}: dense display-math block ({n_lines} non-empty math lines)",
                )
            if words_since_math < 25 and cluster_count > 0:
                cluster_count += 1
                cluster_last_end = b_end
            else:
                _flush_cluster()
                cluster_count = 1
                cluster_start = b_start
                cluster_last_end = b_end
            words_since_math = 0

        for idx in range(start_idx + 1, len(lines) + 1):
            raw = lines[idx - 1]
            s = _strip_tex_comment(raw).strip() if is_tex else raw.strip()

            if not is_tex and s.startswith("```"):
                in_md_fence = not in_md_fence
                _flush_para()
                continue
            if in_md_fence:
                continue

            if is_tex:
                if not in_non_prose and RE_NON_PROSE_BEGIN.search(s):
                    _flush_para()
                    if RE_ANCHOR_CUE.search(s):
                        _flush_stretch(idx)
                    if not RE_NON_PROSE_END.search(s):
                        in_non_prose = True
                    continue
                if in_non_prose:
                    if RE_NON_PROSE_END.search(s):
                        in_non_prose = False
                    continue

            if in_math:
                ended = (
                    (math_delim == "env" and RE_MATH_END.search(s))
                    or (math_delim == "$$" and "$$" in s)
                    or (math_delim == "\\[" and "\\]" in s)
                )
                if s and not ended:
                    math_nonempty += 1
                elif ended:
                    body_rem = (
                        RE_MATH_END.sub("", s).strip()
                        if math_delim == "env"
                        else s.replace("$$", "").replace("\\]", "").strip()
                    )
                    if body_rem:
                        math_nonempty += 1
                    _record_math_block(math_start, idx, max(1, math_nonempty))
                    in_math = False
                    math_delim = ""
                continue

            # Detect start of a display-math block
            if is_tex and RE_MATH_BEGIN.search(s):
                _flush_para()
                if RE_MATH_END.search(s):
                    _record_math_block(idx, idx, 1)
                else:
                    in_math = True
                    math_delim = "env"
                    math_start = idx
                    rem = RE_MATH_BEGIN.sub("", s).strip()
                    math_nonempty = 1 if rem else 0
                continue
            if s.startswith("$$"):
                _flush_para()
                if s.count("$$") >= 2:
                    _record_math_block(idx, idx, 1)
                else:
                    in_math = True
                    math_delim = "$$"
                    math_start = idx
                    math_nonempty = 1 if s[2:].strip() else 0
                continue
            if is_tex and s.startswith("\\["):
                _flush_para()
                if "\\]" in s:
                    _record_math_block(idx, idx, 1)
                else:
                    in_math = True
                    math_delim = "\\["
                    math_start = idx
                    math_nonempty = 1 if s[2:].strip() else 0
                continue

            if not s:
                _flush_para()
                continue

            if is_tex and s.startswith(("\\newcommand", "\\renewcommand", "\\def", "\\usepackage", "\\label", "\\end{document}")):
                continue

            if RE_ANCHOR_CUE.search(s):
                _flush_stretch(idx - 1)
                if s.startswith(("\\section", "\\subsection", "\\subsubsection", "#")):
                    _flush_para()
                    _flush_cluster()
                    words_since_math = 9999
                    continue

            # Collect inline math metrics before stripping LaTeX commands
            if para_start is None:
                para_start = idx
            for m_im in RE_INLINE_MATH.finditer(s):
                expr = (m_im.group(1) or m_im.group(2) or "").strip()
                if expr:
                    para_inline_tokens.append(re.sub(r"\s+", "", expr))
                    if RE_NESTED_SCRIPTS.search(expr):
                        para_nested_scripts += 1

            clean = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", s)
            wc = len(re.findall(r"[A-Za-z0-9'-]+", clean))
            if wc > 0:
                words_since_math += wc
                if words_since_math >= 25:
                    _flush_cluster()
                if stretch_start is None:
                    stretch_start = idx
                stretch_words += wc

        _flush_para()
        _flush_cluster()
        _flush_stretch(len(lines))

    return {k: v for k, v in out.items() if v}


def run_preflight_lint(paths, base_dir=None):
    files = _expand_paths(paths, base_dir=base_dir)
    code_hits = lint_code_files(files, base_dir=base_dir)
    tex_hits = lint_tex_and_md_files(files, base_dir=base_dir)
    bib_hits = lint_bib_files(files, base_dir=base_dir)
    comp_hits = lint_compression_metrics(files, base_dir=base_dir)
    story_hits = lint_storyflow_load(files, base_dir=base_dir)

    return {
        "files_scanned": len(files),
        "code": code_hits,
        "tex_md": tex_hits,
        "bib": bib_hits,
        "compression": comp_hits,
        "storyflow": story_hits,
    }


def format_lint_for_reviewer(lint_report, reviewer_id):
    """Return a concise, reviewer-scoped text summary of deterministic lint hits."""
    sections = []
    code = lint_report.get("code", {})
    tex = lint_report.get("tex_md", {})
    bib = lint_report.get("bib", {})
    comp = lint_report.get("compression", {})
    story = lint_report.get("storyflow", {})

    def _add(title, items):
        if items:
            sections.append(f"[{title}] ({len(items)} hit(s)):")
            for item in items:
                sections.append(f"  - {item}")

    if reviewer_id == "code_math_auditor":
        _add("Bare or silent except blocks", code.get("bare_or_silent_except"))
        _add("np.clip / clamp calls to trace to spec", code.get("clip_or_clamp_calls"))
        _add("Parallel/Slurm scripts missing thread locks", code.get("missing_thread_locks"))
        _add("Potential non-atomic file writes", code.get("potential_non_atomic_writes"))
    elif reviewer_id == "structure_narrative":
        _add("Math-wall bursts (>=6-line display block or >=3 clustered blocks)", story.get("math_walls"))
        _add("Symbol-density / working-memory spikes (inline math/index burst in one paragraph)", story.get("symbol_density_spikes"))
        _add("Long unanchored prose stretches (>=450 words without heading or figure/table anchor)", story.get("unanchored_long_stretches"))
    elif reviewer_id == "prose_style":
        _add("Sentence-initial abbreviations (Eq./Fig./Tab./Sec.)", tex.get("sentence_initial_abbreviations"))
        _add("Wordy filler phrases", tex.get("wordy_fillers"))
    elif reviewer_id == "figures_refs_format":
        _add("Existing LaTeX/BibTeX .log/.blg warnings", tex.get("latex_build_log_warnings"))
        _add("Straight ASCII quotes in LaTeX", tex.get("straight_latex_quotes"))
        _add("Incomplete .bib entries", bib.get("bib_incomplete_entries"))
        _add("Plot script hygiene (titles, linewidth, fontsize)", code.get("plot_script_hygiene"))
    elif reviewer_id == "grammar_humanizer":
        _add("Em-dashes (--- / —)", tex.get("em_dashes"))
        _add("High-signal AI tell phrases", tex.get("ai_tell_phrases"))
        _add("Overlong sentences (> 35 words)", tex.get("overlong_sentences_gt35w"))
    elif reviewer_id == "conciseness_editor":
        _add("Prose density summary", comp.get("prose_density"))
        _add("Wall-of-text paragraphs (>= 150 words)", comp.get("long_paragraphs_ge150w"))
        _add("Large, sparse, or near-constant tables", comp.get("table_bloat_and_sparsity"))
        _add("Repeated caption boilerplate phrases", comp.get("repeated_caption_phrases"))
        _add("Unreferenced orphan .tex files in generated/", comp.get("orphan_generated_tex"))
    else:
        return ""

    if not sections:
        return (
            "0-TOKEN DETERMINISTIC PRE-LINTER: 0 mechanical hits for your scope across "
            f"{lint_report.get('files_scanned', 0)} scanned file(s). Focus on deeper semantic checks."
        )
    header = (
        "0-TOKEN DETERMINISTIC PRE-LINTER HITS (already scanned mechanically — verify each hit "
        "in context instead of manually grepping for mechanical typos):"
    )
    return header + "\n" + "\n".join(sections)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deterministic 0-token pre-flight linter")
    parser.add_argument("paths", nargs="+", help="Files or directories to scan")
    parser.add_argument("--reviewer", default="", help="Optional reviewer_id for scoped text output")
    parser.add_argument("--base-dir", default=None, help="Base directory for relative paths")
    parsed = parser.parse_args()
    report = run_preflight_lint(parsed.paths, base_dir=parsed.base_dir)
    if parsed.reviewer:
        print(format_lint_for_reviewer(report, parsed.reviewer))
    else:
        print(json.dumps(report, indent=2))
