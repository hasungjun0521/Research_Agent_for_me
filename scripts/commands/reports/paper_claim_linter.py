#!/usr/bin/env python3
"""Lint LaTeX claims against final result/evidence tables."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts.harness.project_diagnostics import csv_rows
from scripts.harness.state import project_root

QUANT_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?\s*(?:%|pp|x)?")
CLAIM_ID_RE = re.compile(r"\bclaim_[A-Za-z0-9_]+\b")
CLAIM_MACRO_RE = re.compile(r"\\claim(?:id)?\{([^}]+)\}")
CITATION_RE = re.compile(r"\\[A-Za-z]*cite[a-z]*\{", re.IGNORECASE)
STRONG_CLAIM_WORDS = (
    "outperform",
    "outperforms",
    "outperformed",
    "surpass",
    "surpasses",
    "state-of-the-art",
    "sota",
    "best-performing",
    "consistently better",
    "beats",
    "superior to",
)
STRONG_CLAIM_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(word) for word in STRONG_CLAIM_WORDS) + r")\b",
    re.IGNORECASE,
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def paper_claim_ids(text: str) -> set[str]:
    ids = set(CLAIM_ID_RE.findall(text))
    ids.update(match.strip() for match in CLAIM_MACRO_RE.findall(text) if match.strip())
    return ids


def sentence_chunks(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if c.strip()]


def normalized_number(v: str) -> str:
    return v.strip().replace(" ", "")


def result_numbers(rows: list[dict[str, str]]) -> set[str]:
    nums = set()
    for r in rows:
        for f in ("value", "delta"):
            v = str(r.get(f) or "").strip()
            if v:
                nums.add(normalized_number(v))
                try:
                    nums.add(f"{float(v):.3g}")
                except ValueError:
                    pass
    return nums


def quantitative_claim_warnings(paper: str, result_rows: list[dict[str, str]]) -> list[str]:
    if not result_rows:
        return []
    supported = result_numbers(result_rows)
    warnings = []
    triggers = (
        "improve",
        "outperform",
        "better",
        "higher",
        "lower",
        "reduce",
        "increase",
        "state-of-the-art",
        "sota",
    )
    for s in sentence_chunks(paper):
        if not any(w in s.lower() for w in triggers):
            continue
        for m in QUANT_RE.findall(s):
            n = normalized_number(m)
            b = n.removesuffix("%").removesuffix("pp").removesuffix("x")
            if n in supported or b in supported:
                continue
            warnings.append(f"No match for {m.strip()} in '{s[:120]}'.")
    return warnings


def ungrounded_statement_warnings(
    paper: str, result_rows: list[dict[str, str]], ids_in_paper: set[str]
) -> list[str]:
    chunks = sentence_chunks(paper)
    warnings = []
    for i, s in enumerate(chunks):
        if not STRONG_CLAIM_RE.search(s):
            continue
        win = s + " " + (chunks[i + 1] if i + 1 < len(chunks) else "")
        if (
            CITATION_RE.search(win)
            or (set(CLAIM_ID_RE.findall(win)) & ids_in_paper)
            or CLAIM_MACRO_RE.search(win)
            or QUANT_RE.findall(win)
        ):
            continue
        warnings.append(
            f"Ungrounded claim statement (no result number, claim_id, or citation): '{s[:120]}'."
        )
    return warnings


def lint_project(root: Path) -> list[str]:
    from scripts.commands.reports.claim_evidence_board import STRONG_STATUSES, WEAK_STATUSES

    warnings = []
    paper = read_text(root / "09_report" / "paper" / "main.tex")
    claim_rows = csv_rows(root / "09_report" / "results" / "claim_evidence.csv")
    result_rows = csv_rows(root / "09_report" / "results" / "experiment_results.csv")
    ids = paper_claim_ids(paper)
    claim_by_id = {r.get("claim_id", ""): r for r in claim_rows if r.get("claim_id", "")}
    res_claims = {r.get("claim_id", "") for r in result_rows if r.get("claim_id", "")}
    for cid, r in claim_by_id.items():
        s = str(r.get("status") or "").strip().lower()
        if s in WEAK_STATUSES and cid in ids:
            warnings.append(f"Weak claim {cid} in paper.")
        if s in STRONG_STATUSES and cid not in res_claims and cid in ids:
            warnings.append(f"No results for {cid}.")
        if s in {"supported", "validated"} and cid not in ids:
            warnings.append(f"{cid} not cited.")
    for cid in ids:
        if cid not in claim_by_id:
            warnings.append(f"Unknown {cid}.")
        cr = [r for r in result_rows if r.get("claim_id") == cid]
        if cr:
            splits = {str(r.get("split") or "").strip().lower() for r in cr}
            if splits and "test" not in splits:
                warnings.append(f"{cid} lacks test data ({', '.join(splits)}).")
    warnings.extend(quantitative_claim_warnings(paper, result_rows))
    warnings.extend(ungrounded_statement_warnings(paper, result_rows, ids))
    return warnings


def run_lint(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    warnings = lint_project(root)
    if args.json:
        print(
            json.dumps(
                {"project": args.project, "warnings": warnings}, indent=2, ensure_ascii=False
            )
        )
    elif warnings:
        print("paper claim warnings:")
        for w in warnings:
            print(f"- {w}")
    else:
        print(f"paper claim lint OK: {args.project}")
    return 1 if warnings and args.strict else 0


def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    lint = subparsers.add_parser("lint", help="Check paper claims against 09_report/results.")
    lint.add_argument("--project", required=True)
    lint.add_argument("--strict", action="store_true")
    lint.add_argument("--json", action="store_true")


def main() -> int:
    from scripts.commands.reports.claims import main as claims_main

    if len(sys.argv) < 2 or sys.argv[1] != "lint":
        sys.argv.insert(1, "lint")
    return claims_main()


if __name__ == "__main__":
    raise SystemExit(main())
