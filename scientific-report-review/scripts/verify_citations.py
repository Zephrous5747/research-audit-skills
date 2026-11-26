#!/usr/bin/env python3
"""Lightweight arXiv / Crossref / Semantic Scholar citation verifier (stdlib only).

Catches hallucinated, broken, or mismatched citations in `.bib`, `.tex`, and `.md`
manuscripts before submission. Runs with zero third-party dependencies.

Usage:
    # Offline structural + undefined-key audit (instant, zero network)
    python verify_citations.py reports/refs.bib reports/manuscript.tex --offline

    # Live API check via arXiv Atom API + Crossref (optional --semantic-scholar fallback)
    python verify_citations.py reports/refs.bib reports/manuscript.tex --format md
    python verify_citations.py reports/refs.bib --semantic-scholar --fail-on-suspect
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

USER_AGENT = "ResearchAuditSkills-CitationVerifier/0.1 (mailto:research-audit-skills@users.noreply.github.com)"

RE_BIB_ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)
RE_CITE_KEYS = re.compile(r"\\(?:cite[a-zA-Z]*|parencite|textcite|autocite)\*?(?:\[[^\]]*\])*\{([^}]+)\}")
RE_BARE_ARXIV = re.compile(r"\barXiv\s*:\s*([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z-]+/[0-9]{7})\b", re.IGNORECASE)
RE_ARXIV_ID_VALID = re.compile(r"^(?:[0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z-]+(?:\.[a-z-]+)?/[0-9]{7}(?:v\d+)?)$", re.IGNORECASE)
RE_DOI_VALID = re.compile(r"^10\.\d{4,9}/\S+$")
RE_BARE_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>}\]]+)")


def _strip_tex_comment(line: str) -> str:
    out = []
    escaped = False
    for ch in line:
        if ch == "%" and not escaped:
            break
        escaped = (ch == "\\") and not escaped
        out.append(ch)
    return "".join(out)


def _clean_bib_value(raw: str) -> str:
    s = raw.strip().rstrip(",").strip()
    if (s.startswith("{") and s.endswith("}")) or (s.startswith('"') and s.endswith('"')):
        s = s[1:-1].strip()
    s = re.sub(r"[{}]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_bib_fields(body: str) -> dict:
    """Parse balanced-brace or quoted BibTeX fields inside an entry body."""
    fields = {}
    i, n = 0, len(body)
    while i < n:
        while i < n and body[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        m = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body[i:])
        if not m:
            i += 1
            continue
        name = m.group(1).lower()
        i += m.end()
        if i >= n:
            break
        if body[i] == "{":
            depth = 0
            start = i
            while i < n:
                if body[i] == "{":
                    depth += 1
                elif body[i] == "}":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            fields[name] = _clean_bib_value(body[start:i])
        elif body[i] == '"':
            start = i
            i += 1
            while i < n:
                if body[i] == '"' and body[i - 1] != "\\":
                    i += 1
                    break
                i += 1
            fields[name] = _clean_bib_value(body[start:i])
        else:
            start = i
            while i < n and body[i] not in ",\r\n}":
                i += 1
            fields[name] = _clean_bib_value(body[start:i])
    return fields


def parse_bib_text(text: str, source: str = "") -> tuple[list[dict], list[str]]:
    """Extract entries and duplicate keys from a BibTeX string."""
    entries = []
    seen_keys = set()
    duplicates = []
    pos = 0
    n = len(text)
    while pos < n:
        m = RE_BIB_ENTRY.search(text, pos)
        if not m:
            break
        etype = m.group(1).lower()
        key = m.group(2).strip()
        if etype in ("comment", "preamble", "string"):
            pos = m.end()
            continue
        # Walk balanced braces from the opening `{` after @type
        brace_open = text.find("{", m.start())
        depth = 0
        end = brace_open
        while end < n:
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
                if depth == 0:
                    break
            end += 1
        body = text[m.end() : end]
        fields = _parse_bib_fields(body)
        if key in seen_keys:
            duplicates.append(key)
        seen_keys.add(key)

        doi = fields.get("doi", "").strip()
        doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE).strip()

        arxiv_id = ""
        if "eprint" in fields:
            ep = fields["eprint"].strip()
            ep = re.sub(r"^arXiv\s*:\s*", "", ep, flags=re.IGNORECASE).strip()
            ap = fields.get("archiveprefix", "").lower()
            if ap in ("", "arxiv") or RE_ARXIV_ID_VALID.match(ep):
                arxiv_id = ep
        if not arxiv_id:
            for cand in (fields.get("journal", ""), fields.get("note", ""), fields.get("url", "")):
                ma = RE_BARE_ARXIV.search(cand)
                if ma:
                    arxiv_id = ma.group(1)
                    break
                mu = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z-]+/[0-9]{7})", cand, re.I)
                if mu:
                    arxiv_id = mu.group(1)
                    break

        entries.append(
            {
                "key": key,
                "entry_type": etype,
                "source": source,
                "title": fields.get("title", ""),
                "author": fields.get("author", "") or fields.get("editor", ""),
                "year": fields.get("year", ""),
                "doi": doi,
                "arxiv_id": arxiv_id,
            }
        )
        pos = end + 1
    return entries, duplicates


def scan_tex_citations(paths: list[Path]) -> tuple[set[str], list[dict]]:
    """Collect cited BibTeX keys plus bare arXiv/DOI mentions from .tex/.md files."""
    cited_keys = set()
    bare_refs = []
    seen_bare = set()
    for p in paths:
        if p.suffix.lower() not in (".tex", ".md"):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix.lower() == ".tex":
            text = "\n".join(_strip_tex_comment(l) for l in text.splitlines())
        for m in RE_CITE_KEYS.finditer(text):
            for k in m.group(1).split(","):
                k = k.strip()
                if k:
                    cited_keys.add(k)
        for m in RE_BARE_ARXIV.finditer(text):
            aid = m.group(1).strip()
            if ("arxiv", aid.lower()) not in seen_bare:
                seen_bare.add(("arxiv", aid.lower()))
                bare_refs.append({"key": f"arXiv:{aid}", "source": p.name, "title": "", "author": "", "year": "", "doi": "", "arxiv_id": aid, "bare": True})
        for m in RE_BARE_DOI.finditer(text):
            doi = m.group(1).rstrip(".,;)")
            if ("doi", doi.lower()) not in seen_bare:
                seen_bare.add(("doi", doi.lower()))
                bare_refs.append({"key": f"doi:{doi}", "source": p.name, "title": "", "author": "", "year": "", "doi": doi, "arxiv_id": "", "bare": True})
    return cited_keys, bare_refs


def _title_tokens(title: str) -> set[str]:
    stop = {"a", "an", "the", "of", "for", "in", "on", "to", "and", "or", "with", "via", "from", "by", "using"}
    toks = re.findall(r"[a-z0-9]+", (title or "").lower())
    return {t for t in toks if len(t) >= 3 and t not in stop}


def _title_overlap(a: str, b: str) -> float:
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 1.0
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


def _http_get(url: str, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def query_arxiv(arxiv_id: str, timeout: float = 8.0, fetcher=_http_get) -> dict | None:
    clean_id = re.sub(r"v\d+$", "", arxiv_id.strip(), flags=re.IGNORECASE)
    url = f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(clean_id)}"
    raw = fetcher(url, timeout)
    root = ET.fromstring(raw)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        return None
    title_el = entry.find("atom:title", ns)
    pub_el = entry.find("atom:published", ns)
    id_el = entry.find("atom:id", ns)
    title = re.sub(r"\s+", " ", (title_el.text or "")).strip() if title_el is not None else ""
    if not title or title.lower() == "error":
        return None
    year = (pub_el.text or "")[:4] if pub_el is not None else ""
    return {"api": "arxiv", "title": title, "year": year, "url": (id_el.text or "").strip() if id_el is not None else ""}


def query_crossref_doi(doi: str, timeout: float = 8.0, fetcher=_http_get) -> dict | None:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi.strip(), safe='')}"
    try:
        data = json.loads(fetcher(url, timeout).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    msg = data.get("message") or {}
    titles = msg.get("title") or []
    title = re.sub(r"\s+", " ", titles[0]).strip() if titles else ""
    year = ""
    for df in ("published-print", "published-online", "issued", "created"):
        parts = ((msg.get(df) or {}).get("date-parts") or [[]])[0]
        if parts:
            year = str(parts[0])
            break
    return {"api": "crossref_doi", "title": title, "year": year, "doi": msg.get("DOI", doi)}


def query_crossref_title(title: str, timeout: float = 8.0, fetcher=_http_get) -> dict | None:
    q = urllib.parse.urlencode({"query.title": title, "rows": 2})
    url = f"https://api.crossref.org/works?{q}"
    data = json.loads(fetcher(url, timeout).decode("utf-8", errors="replace"))
    items = (data.get("message") or {}).get("items") or []
    best = None
    best_score = 0.0
    for it in items:
        cand_title = ((it.get("title") or [""])[0] or "").strip()
        sc = _title_overlap(title, cand_title)
        if sc > best_score:
            best_score = sc
            parts = (((it.get("issued") or {}).get("date-parts") or [[]])[0])
            best = {
                "api": "crossref_title",
                "title": cand_title,
                "year": str(parts[0]) if parts else "",
                "doi": it.get("DOI", ""),
                "overlap": round(sc, 2),
            }
    return best if (best and best_score >= 0.65) else None


def query_semantic_scholar_title(title: str, timeout: float = 8.0, fetcher=_http_get) -> dict | None:
    q = urllib.parse.urlencode({"query": title, "limit": 2, "fields": "title,year,externalIds"})
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?{q}"
    data = json.loads(fetcher(url, timeout).decode("utf-8", errors="replace"))
    items = data.get("data") or []
    best = None
    best_score = 0.0
    for it in items:
        cand_title = (it.get("title") or "").strip()
        sc = _title_overlap(title, cand_title)
        if sc > best_score:
            best_score = sc
            best = {
                "api": "semantic_scholar",
                "title": cand_title,
                "year": str(it.get("year") or ""),
                "external_ids": it.get("externalIds") or {},
                "overlap": round(sc, 2),
            }
    return best if (best and best_score >= 0.65) else None


def _compare_entry_to_hit(entry: dict, hit: dict) -> tuple[str, str]:
    issues = []
    if entry.get("title") and hit.get("title"):
        ov = _title_overlap(entry["title"], hit["title"])
        if ov < 0.60:
            issues.append(f"title mismatch (overlap={ov:.2f}: api='{hit['title'][:90]}')")
    ey = re.search(r"\b(19|20)\d{2}\b", entry.get("year", ""))
    hy = re.search(r"\b(19|20)\d{2}\b", hit.get("year", ""))
    if ey and hy and abs(int(ey.group(0)) - int(hy.group(0))) > 1:
        issues.append(f"year mismatch (bib={ey.group(0)} vs api={hy.group(0)})")
    if issues:
        return "TITLE_OR_YEAR_MISMATCH", "; ".join(issues)
    return "VERIFIED", f"matched via {hit['api']} ({hit.get('year', '?')})"


def verify_citations(
    paths: list[str],
    offline: bool = False,
    use_semantic_scholar: bool = False,
    delay: float = 0.35,
    timeout: float = 8.0,
    max_queries: int = 50,
    fetcher=_http_get,
) -> dict:
    resolved = [Path(p) for p in paths if Path(p).exists()]
    bib_entries = []
    duplicates = []
    for p in resolved:
        if p.suffix.lower() == ".bib":
            ents, dups = parse_bib_text(p.read_text(encoding="utf-8", errors="replace"), source=p.name)
            bib_entries.extend(ents)
            duplicates.extend(dups)

    cited_keys, bare_refs = scan_tex_citations(resolved)
    bib_keys = {e["key"] for e in bib_entries}
    undefined_cite_keys = sorted(cited_keys - bib_keys) if bib_entries else []

    # Avoid re-checking bare DOIs/arXiv IDs already covered by .bib entries
    covered_dois = {e["doi"].lower() for e in bib_entries if e["doi"]}
    covered_arxiv = {re.sub(r"v\d+$", "", e["arxiv_id"].lower()) for e in bib_entries if e["arxiv_id"]}
    extra_bare = [
        b for b in bare_refs
        if (b["doi"] and b["doi"].lower() not in covered_dois)
        or (b["arxiv_id"] and re.sub(r"v\d+$", "", b["arxiv_id"].lower()) not in covered_arxiv)
    ]

    all_items = bib_entries + extra_bare
    results = []
    queries_used = 0

    for item in all_items:
        structural_issues = []
        if not item.get("bare"):
            if not item.get("title"):
                structural_issues.append("missing title")
            if not item.get("author"):
                structural_issues.append("missing author/editor")
            if not item.get("year"):
                structural_issues.append("missing year")
        if item.get("doi") and not RE_DOI_VALID.match(item["doi"]):
            structural_issues.append(f"malformed DOI '{item['doi']}'")
        if item.get("arxiv_id") and not RE_ARXIV_ID_VALID.match(item["arxiv_id"]):
            structural_issues.append(f"malformed arXiv ID '{item['arxiv_id']}'")

        if offline:
            status = "MISSING_FIELDS" if structural_issues else "UNVERIFIED_OFFLINE"
            detail = "; ".join(structural_issues) if structural_issues else "structural syntax OK (offline mode)"
            results.append({"key": item["key"], "status": status, "detail": detail, "source": item["source"]})
            continue

        if queries_used >= max_queries:
            results.append({"key": item["key"], "status": "UNVERIFIED_OFFLINE", "detail": f"max_queries={max_queries} reached", "source": item["source"]})
            continue

        hit = None
        api_error = ""
        try:
            if item.get("doi") and RE_DOI_VALID.match(item["doi"]):
                hit = query_crossref_doi(item["doi"], timeout=timeout, fetcher=fetcher)
                queries_used += 1
            elif item.get("arxiv_id") and RE_ARXIV_ID_VALID.match(item["arxiv_id"]):
                hit = query_arxiv(item["arxiv_id"], timeout=timeout, fetcher=fetcher)
                queries_used += 1
            elif item.get("title"):
                hit = query_crossref_title(item["title"], timeout=timeout, fetcher=fetcher)
                queries_used += 1
                if hit is None and use_semantic_scholar and queries_used < max_queries:
                    if delay > 0:
                        time.sleep(delay)
                    hit = query_semantic_scholar_title(item["title"], timeout=timeout, fetcher=fetcher)
                    queries_used += 1
            if delay > 0 and queries_used > 0:
                time.sleep(delay)
        except Exception as exc:
            api_error = str(exc)

        if api_error:
            results.append({"key": item["key"], "status": "UNVERIFIED_OFFLINE", "detail": f"API error: {api_error}", "source": item["source"]})
        elif hit is not None:
            st, det = _compare_entry_to_hit(item, hit)
            if structural_issues and st == "VERIFIED":
                det = f"{det} (warnings: {'; '.join(structural_issues)})"
            results.append({"key": item["key"], "status": st, "detail": det, "source": item["source"], "api_match": hit})
        elif not item.get("doi") and not item.get("arxiv_id") and not item.get("title"):
            results.append({"key": item["key"], "status": "MISSING_FIELDS", "detail": "; ".join(structural_issues), "source": item["source"]})
        else:
            results.append({"key": item["key"], "status": "NOT_FOUND_SUSPECT", "detail": "no matching arXiv/Crossref record found", "source": item["source"]})

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    return {
        "files_scanned": [p.name for p in resolved],
        "offline": offline,
        "total_checked": len(results),
        "queries_used": queries_used,
        "counts": counts,
        "duplicate_bib_keys": sorted(set(duplicates)),
        "undefined_cite_keys": undefined_cite_keys,
        "results": results,
    }


def format_markdown(report: dict) -> str:
    lines = [
        f"## Citation Verification Report ({'offline' if report['offline'] else 'live API'})",
        f"- Files: {', '.join(report['files_scanned']) or 'none'}",
        f"- Checked: {report['total_checked']} | Counts: {report['counts']}",
    ]
    if report["duplicate_bib_keys"]:
        lines.append(f"- **Duplicate `.bib` keys:** {', '.join(report['duplicate_bib_keys'])}")
    if report["undefined_cite_keys"]:
        lines.append(f"- **Undefined `\\cite` keys:** {', '.join(report['undefined_cite_keys'])}")
    flagged = [r for r in report["results"] if r["status"] not in ("VERIFIED",)]
    if flagged:
        lines.append("\n| Key | Status | Detail |")
        lines.append("| :--- | :--- | :--- |")
        for r in flagged:
            lines.append(f"| `{r['key']}` | **{r['status']}** | {r['detail']} |")
    else:
        lines.append("\nAll checked citations verified cleanly.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Lightweight arXiv / Crossref / Semantic Scholar citation verifier")
    parser.add_argument("paths", nargs="+", help=".bib, .tex, or .md files to audit")
    parser.add_argument("--offline", action="store_true", help="Run structural & undefined-cite checks only (no network)")
    parser.add_argument("--semantic-scholar", action="store_true", help="Enable Semantic Scholar fallback for title-only entries")
    parser.add_argument("--delay", type=float, default=0.35, help="Delay between live API calls in seconds (default 0.35)")
    parser.add_argument("--timeout", type=float, default=8.0, help="Per-request HTTP timeout in seconds (default 8.0)")
    parser.add_argument("--max-queries", type=int, default=50, help="Cap total live API requests (default 50)")
    parser.add_argument("--format", choices=("md", "json"), default="md", help="Output format")
    parser.add_argument("--fail-on-suspect", action="store_true", help="Exit 2 if any NOT_FOUND_SUSPECT, TITLE_OR_YEAR_MISMATCH, or undefined cite key is found")
    args = parser.parse_args()

    report = verify_citations(
        args.paths,
        offline=args.offline,
        use_semantic_scholar=args.semantic_scholar,
        delay=args.delay,
        timeout=args.timeout,
        max_queries=args.max_queries,
    )
    print(json.dumps(report, indent=2) if args.format == "json" else format_markdown(report))

    if args.fail_on_suspect:
        bad_statuses = {"NOT_FOUND_SUSPECT", "TITLE_OR_YEAR_MISMATCH"}
        if any(r["status"] in bad_statuses for r in report["results"]) or report["undefined_cite_keys"]:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
