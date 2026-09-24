#!/usr/bin/env python3
"""Audit citation/source credibility signals for a research project."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index

CSV_HEADER = ["kind", "check", "status", "detail"]
ESSENTIAL_BIB_FIELDS = ("author", "title", "year")
MISSING_FIELD_DETAIL_CAP = 50
BIB_NON_REFERENCE_TYPES = {"comment", "preamble", "string"}
BIB_ARXIV_FIELDS = ("journal", "eprint", "url")


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit source and citation credibility for a project.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
            if any(str(value or "").strip() for value in row.values())
        ]


def bib_keys(root: Path) -> set[str]:
    text = read_text(root / "01_literature" / "papers.bib")
    return {match.group(1).strip() for match in re.finditer(r"@\w+\s*\{\s*([^,\s]+)", text)}


def parse_bib_entries(text: str) -> list[dict[str, Any]]:
    """Tolerantly parse hand-edited BibTeX text into entry dicts.

    Bib files in 01_literature/ are hand-edited; this parser must never raise
    on malformed input. Unclosed braces consume the remaining text for that
    entry, and unparseable fields are simply skipped.
    """
    entries: list[dict[str, Any]] = []
    for match in re.finditer(r"@([A-Za-z]+)\s*\{", text):
        entry_type = match.group(1).lower()
        if entry_type in BIB_NON_REFERENCE_TYPES:
            continue
        start = match.end()
        depth = 1
        pos = start
        while pos < len(text) and depth > 0:
            char = text[pos]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            pos += 1
        body = text[start : pos - 1] if depth == 0 else text[start:]
        raw_key, _, field_text = body.partition(",")
        key_tokens = raw_key.split()
        key = key_tokens[0] if key_tokens else ""
        entries.append({"type": entry_type, "key": key, "fields": _parse_bib_fields(field_text)})
    return entries


def _parse_bib_fields(field_text: str) -> dict[str, str]:
    """Depth-counting field parser: handles arbitrarily nested brace values."""
    fields: dict[str, str] = {}
    name_pattern = re.compile(r"\s*([A-Za-z][\w-]*)\s*=\s*")
    pos = 0
    length = len(field_text)
    while pos < length:
        match = name_pattern.match(field_text, pos)
        if not match:
            pos += 1
            continue
        name = match.group(1).lower()
        pos = match.end()
        if pos < length and field_text[pos] == "{":
            depth = 1
            pos += 1
            start = pos
            while pos < length and depth > 0:
                if field_text[pos] == "{":
                    depth += 1
                elif field_text[pos] == "}":
                    depth -= 1
                pos += 1
            value = field_text[start : pos - 1] if depth == 0 else field_text[start:]
        elif pos < length and field_text[pos] == '"':
            pos += 1
            start = pos
            while pos < length and field_text[pos] != '"':
                pos += 1
            value = field_text[start:pos]
            pos += 1
        else:
            start = pos
            while pos < length and field_text[pos] not in ",\n":
                pos += 1
            value = field_text[start:pos]
        fields.setdefault(name, value.strip())
    return fields


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def bib_hygiene(root: Path) -> dict[str, Any]:
    """Entry-level hygiene checks over 01_literature/papers.bib."""
    entries = parse_bib_entries(read_text(root / "01_literature" / "papers.bib"))

    key_counts: dict[str, int] = {}
    placeholder_keys: list[str] = []
    keys_by_title: dict[str, list[str]] = {}
    missing_field_lines: list[str] = []
    arxiv_count = 0
    for entry in entries:
        key = entry["key"] or "<missing key>"
        fields = entry["fields"]
        if entry["key"]:
            key_counts[key] = key_counts.get(key, 0) + 1
        title = fields.get("title", "")
        if (
            "placeholder" in key.lower()
            or "placeholder" in title.lower()
            or ("title" in fields and not title.strip())
        ):
            placeholder_keys.append(key)
        normalized = normalize_title(title)
        if normalized:
            keys_by_title.setdefault(normalized, []).append(key)
        absent = [field for field in ESSENTIAL_BIB_FIELDS if not fields.get(field, "").strip()]
        if absent:
            missing_field_lines.append(f"{key}: missing {', '.join(absent)}")
        haystack = " ".join(fields.get(field, "") for field in BIB_ARXIV_FIELDS).lower()
        if "arxiv" in haystack:
            arxiv_count += 1

    duplicate_keys = sorted(key for key, count in key_counts.items() if count > 1)
    near_duplicate_titles = [
        sorted(set(keys))
        for _normalized, keys in sorted(keys_by_title.items())
        if len(set(keys)) > 1
    ]
    missing_field_total = len(missing_field_lines)
    details_capped = missing_field_total > MISSING_FIELD_DETAIL_CAP
    return {
        "entries": len(entries),
        "duplicate_keys": duplicate_keys,
        "placeholder_keys": sorted(set(placeholder_keys)),
        "near_duplicate_titles": near_duplicate_titles,
        "missing_field_entries": missing_field_lines[:MISSING_FIELD_DETAIL_CAP],
        "missing_field_total": missing_field_total,
        "missing_field_details_capped": details_capped,
        "arxiv_preprint_count": arxiv_count,
    }


def citation_keys(root: Path) -> set[str]:
    keys: set[str] = set()
    search_dirs = [root / "06_writing", root / "09_report" / "paper", root / "05_results", root / "07_reviews"]
    for folder in search_dirs:
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if path.suffix.lower() not in {".md", ".tex"}:
                continue
            text = read_text(path)
            for match in re.finditer(r"\\(?:cite|citet|citep|citealp|citeauthor|citeyear)\*?\{([^}]+)\}", text):
                for key in match.group(1).split(","):
                    stripped = key.strip()
                    if stripped:
                        keys.add(stripped)
            for match in re.finditer(r"(?<![\w/@.-])@([A-Za-z0-9:_-]+)", text):
                keys.add(match.group(1).strip())
    return keys


def paper_note_count(root: Path) -> int:
    notes = root / "01_literature" / "paper_notes"
    if not notes.is_dir():
        return 0
    return sum(1 for path in notes.glob("*.md") if path.name != "README.md")


def claim_rows_without_source(root: Path) -> int:
    rows = csv_rows(root / "09_report" / "results" / "claim_evidence.csv")
    if not rows:
        return 0
    source_fields = ("citation", "citations", "source", "sources", "evidence", "evidence_files", "paper")
    missing = 0
    for row in rows:
        if not any(str(row.get(field) or "").strip() for field in source_fields):
            missing += 1
    return missing


def audit_project(root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, str]] = []

    bib = bib_keys(root)
    cited = citation_keys(root)
    missing_citations = sorted(cited - bib)
    uncited_sources = sorted(bib - cited)
    notes = paper_note_count(root)
    missing_claim_sources = claim_rows_without_source(root)

    if bib:
        checks.append({"check": "bibliography", "status": "pass", "detail": f"{len(bib)} bibliography key(s) found."})
    else:
        blockers.append("No bibliography keys found in 01_literature/papers.bib.")
        checks.append({"check": "bibliography", "status": "blocker", "detail": "Add verified sources to 01_literature/papers.bib."})

    if missing_citations:
        blockers.append(f"{len(missing_citations)} citation key(s) are used but missing from papers.bib: {', '.join(missing_citations[:8])}.")
        checks.append({"check": "citation_integrity", "status": "blocker", "detail": f"{len(missing_citations)} missing citation key(s)."})
    else:
        checks.append({"check": "citation_integrity", "status": "pass", "detail": "All detected citation keys resolve to papers.bib."})

    if notes:
        checks.append({"check": "paper_notes", "status": "pass", "detail": f"{notes} paper note file(s) found."})
    else:
        warnings.append("No paper note files found under 01_literature/paper_notes/.")
        checks.append({"check": "paper_notes", "status": "warning", "detail": "Add paper notes for important sources."})

    if missing_claim_sources:
        warnings.append(f"{missing_claim_sources} claim row(s) do not carry source/evidence references.")
        checks.append({"check": "claim_source_links", "status": "warning", "detail": f"{missing_claim_sources} claim row(s) missing source/evidence references."})
    else:
        checks.append({"check": "claim_source_links", "status": "pass", "detail": "No claim rows missing source/evidence references."})

    if uncited_sources and cited:
        warnings.append(f"{len(uncited_sources)} bibliography source(s) are not cited in writing/results surfaces.")
        checks.append({"check": "unused_sources", "status": "warning", "detail": f"{len(uncited_sources)} uncited bibliography source(s)."})
    else:
        checks.append({"check": "unused_sources", "status": "pass", "detail": "No unused-source warning triggered."})

    hygiene = bib_hygiene(root)

    if hygiene["duplicate_keys"]:
        blockers.append(
            f"{len(hygiene['duplicate_keys'])} duplicate bib key(s) in papers.bib: "
            f"{', '.join(hygiene['duplicate_keys'][:8])}."
        )
        checks.append({"check": "bib_duplicate_keys", "status": "blocker", "detail": f"{len(hygiene['duplicate_keys'])} duplicate bib key(s)."})
    else:
        checks.append({"check": "bib_duplicate_keys", "status": "pass", "detail": "No duplicate bib keys."})

    if hygiene["placeholder_keys"]:
        blockers.append(
            f"{len(hygiene['placeholder_keys'])} placeholder bib entry(ies) in papers.bib: "
            f"{', '.join(hygiene['placeholder_keys'][:8])}."
        )
        checks.append({"check": "bib_placeholder_entries", "status": "blocker", "detail": f"{len(hygiene['placeholder_keys'])} placeholder bib entry(ies)."})
    else:
        checks.append({"check": "bib_placeholder_entries", "status": "pass", "detail": "No placeholder bib entries."})

    if hygiene["near_duplicate_titles"]:
        groups = ["/".join(group) for group in hygiene["near_duplicate_titles"][:4]]
        blockers.append(
            f"{len(hygiene['near_duplicate_titles'])} near-duplicate bib title group(s) in papers.bib: "
            f"{'; '.join(groups)}."
        )
        checks.append({"check": "bib_near_duplicate_titles", "status": "blocker", "detail": f"{len(hygiene['near_duplicate_titles'])} near-duplicate title group(s)."})
    else:
        checks.append({"check": "bib_near_duplicate_titles", "status": "pass", "detail": "No near-duplicate bib titles."})

    if hygiene["missing_field_total"]:
        warnings.append(
            f"{hygiene['missing_field_total']} bib entry(ies) missing essential field(s) "
            "(title/year/author); see bib hygiene details."
        )
        checks.append({"check": "bib_missing_fields", "status": "warning", "detail": f"{hygiene['missing_field_total']} bib entry(ies) missing essential field(s)."})
    else:
        checks.append({"check": "bib_missing_fields", "status": "pass", "detail": "No bib entries missing essential fields."})

    checks.append({
        "check": "bib_arxiv_preprints",
        "status": "info",
        "detail": f"{hygiene['arxiv_preprint_count']} arXiv preprint reference(s) detected (informational).",
    })

    status = "blocked" if blockers else "warning" if warnings else "ready"
    return {
        "project": root.name,
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "summary": {
            "bibliography_keys": len(bib),
            "citation_keys": len(cited),
            "paper_notes": notes,
            "missing_citations": len(missing_citations),
            "uncited_sources": len(uncited_sources),
            "claim_rows_without_source": missing_claim_sources,
            "bib_entries": hygiene["entries"],
            "duplicate_bib_keys": len(hygiene["duplicate_keys"]),
            "placeholder_bib_entries": len(hygiene["placeholder_keys"]),
            "near_duplicate_bib_titles": len(hygiene["near_duplicate_titles"]),
            "bib_entries_missing_fields": hygiene["missing_field_total"],
            "arxiv_preprints": hygiene["arxiv_preprint_count"],
        },
        "bib_hygiene": hygiene,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Source Credibility Audit",
        "",
        f"- Project: `{report['project']}`",
        f"- Status: `{report['status']}`",
        f"- Blockers: {len(report['blockers'])}",
        f"- Warnings: {len(report['warnings'])}",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in report["checks"]:
        detail = markdown_cell(check["detail"])
        lines.append(f"| {check['check']} | {check['status']} | {detail} |")
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {item}" for item in report["blockers"]) if report["blockers"] else lines.append("- None.")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {item}" for item in report["warnings"]) if report["warnings"] else lines.append("- None.")
    hygiene = report.get("bib_hygiene") or {}
    if hygiene:
        lines.extend([
            "",
            "## Bib Entry Hygiene",
            "",
            f"- Entries parsed: {hygiene.get('entries', 0)}",
            f"- Duplicate keys: {len(hygiene.get('duplicate_keys', []))}",
            f"- Placeholder entries: {len(hygiene.get('placeholder_keys', []))}",
            f"- Near-duplicate title groups: {len(hygiene.get('near_duplicate_titles', []))}",
            f"- Entries missing essential fields: {hygiene.get('missing_field_total', 0)}",
            f"- arXiv preprints (informational): {hygiene.get('arxiv_preprint_count', 0)}",
        ])
        if hygiene.get("missing_field_entries"):
            lines.extend(["", "### Entries Missing Essential Fields", ""])
            lines.extend(f"- {markdown_cell(item)}" for item in hygiene["missing_field_entries"])
            if hygiene.get("missing_field_details_capped"):
                lines.append(
                    f"- Note: showing first {MISSING_FIELD_DETAIL_CAP} of "
                    f"{hygiene.get('missing_field_total', 0)} entries with missing essential fields."
                )
    return "\n".join(lines) + "\n"


def write_csv(root: Path, report: dict[str, Any]) -> Path:
    path = root / "09_report" / "results" / "source_credibility_audit.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerow({
            "kind": "summary",
            "check": "source_credibility",
            "status": report["status"],
            "detail": f"{len(report['blockers'])} blocker(s), {len(report['warnings'])} warning(s)",
        })
        for check in report["checks"]:
            writer.writerow({"kind": "check", **check})
        for blocker in report["blockers"]:
            writer.writerow({"kind": "blocker", "check": "", "status": "blocker", "detail": blocker})
        for warning in report["warnings"]:
            writer.writerow({"kind": "warning", "check": "", "status": "warning", "detail": warning})
    return path


def sync_source_audit_lifecycle(root: Path, report: dict[str, Any], outputs: list[str]) -> None:
    status = "blocked" if report.get("status") == "blocked" else "waiting"
    note = (
        f"Source credibility audit status is {report.get('status')} with "
        f"{len(report.get('blockers', []))} blocker(s) and {len(report.get('warnings', []))} warning(s)."
    )
    update_agent_status(
        root,
        "literature_reviewer",
        status,
        task="Review source credibility audit.",
        stage="source_credibility_audit",
        outputs=outputs,
        notes=note,
        append_note=True,
    )
    append_agent_event(
        root,
        "source_credibility_audit",
        "literature_reviewer",
        status=status,
        task="Review source credibility audit.",
        stage="source_credibility_audit",
        outputs=outputs,
        notes=note,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = project_root(args.project)
        report = audit_project(root)
        if args.write_report:
            report_path = root / "07_reviews" / "source_credibility_audit.md"
            report_path.write_text(render_markdown(report), encoding="utf-8")
            csv_path = write_csv(root, report)
            sync_source_audit_lifecycle(
                root,
                report,
                ["07_reviews/source_credibility_audit.md", csv_path.relative_to(root).as_posix()],
            )
            refresh_report_index(root, include_report=True)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(render_markdown(report).rstrip())
            if args.write_report:
                print("07_reviews/source_credibility_audit.md")
                print(csv_path.relative_to(root).as_posix())
        return 1 if args.strict and report["blockers"] else 0
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
