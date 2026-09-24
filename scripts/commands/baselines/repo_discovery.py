#!/usr/bin/env python3
"""Resolve likely code repositories for registered baseline papers."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.harness.report_lifecycle import sync_report_lifecycle
from scripts.harness.state import (
    HarnessError,
    load_baseline_registry,
    mutate_baseline_registry,
    now_iso,
    project_root,
)

URL_RE = re.compile(r"https?://[^\s\])>\"']+")
GITHUB_RE = re.compile(r"https?://github\.com/[^/\s]+/[^/\s#?]+")


@dataclass
class Candidate:
    baseline_id: str
    url: str
    source: str
    score: int
    officiality: str
    license: str = ""
    evidence: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find and score baseline repository candidates.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", default="literature_reviewer")
    parser.add_argument("--candidate-file", help="CSV/JSON file with baseline_id,url,source,officiality,license columns.")
    parser.add_argument("--allow-network", action="store_true", help="Try GitHub search for missing candidates.")
    parser.add_argument("--apply", action="store_true", help="Apply high-confidence candidates to baseline_registry.json.")
    parser.add_argument("--threshold", type=int, default=70, help="Minimum score for --apply.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def tokenize(value: str) -> set[str]:
    stop = {"the", "and", "for", "with", "from", "this", "that", "paper", "method", "model"}
    return {
        token for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 3 and token not in stop
    }


def local_text_files(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for base in (root / "01_literature", root / "08_baselines"):
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".md", ".bib", ".txt", ".json", ".csv"}:
                candidates.append(path)
    return candidates


def score_url(baseline: dict[str, Any], url: str, source: str, officiality: str = "", license_name: str = "") -> Candidate:
    title = " ".join(str(baseline.get(field) or "") for field in ("name", "paper", "citation_key", "method_family"))
    tokens = tokenize(title)
    url_tokens = tokenize(url.replace("/", " ").replace("-", " ").replace("_", " "))
    overlap = len(tokens & url_tokens)
    score = min(45, overlap * 12)
    if "github.com" in url:
        score += 15
    if officiality == "official":
        score += 35
    elif officiality == "third_party":
        score += 10
    if str(baseline.get("citation_key") or "").lower() and str(baseline.get("citation_key")).lower() in url.lower():
        score += 15
    if source.startswith("candidate_file"):
        score += 10
    if license_name:
        score += 5
    if "paperswithcode" in source.lower():
        score += 10
    official = officiality or ("third_party" if "github.com" in url else "unknown")
    return Candidate(
        baseline_id=str(baseline.get("id") or ""),
        url=url.rstrip(".,"),
        source=source,
        score=min(score, 100),
        officiality=official,
        license=license_name,
        evidence=f"token_overlap={overlap}",
    )


def load_candidate_file(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise HarnessError(f"candidate file not found: {path}")
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("candidates", data) if isinstance(data, dict) else data
        return [row for row in rows if isinstance(row, dict)]
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [{str(k or ""): str(v or "") for k, v in row.items()} for row in csv.DictReader(handle)]


def candidates_from_file(root: Path, registry: dict[str, Any], path_value: str | None) -> list[Candidate]:
    if not path_value:
        return []
    path = Path(path_value)
    if not path.is_absolute():
        path = root / path
    baselines = {str(item.get("id") or ""): item for item in registry.get("baselines", []) if isinstance(item, dict)}
    results: list[Candidate] = []
    for row in load_candidate_file(path):
        baseline_id = str(row.get("baseline_id") or row.get("id") or "").strip()
        url = str(row.get("url") or row.get("repo_url") or "").strip()
        if not baseline_id or baseline_id not in baselines or not url:
            continue
        results.append(score_url(
            baselines[baseline_id],
            url,
            f"candidate_file:{path.name}",
            str(row.get("officiality") or row.get("source_type") or "").strip(),
            str(row.get("license") or "").strip(),
        ))
    return results


def candidates_from_local_notes(root: Path, registry: dict[str, Any]) -> list[Candidate]:
    text_blobs: list[tuple[Path, str]] = []
    for path in local_text_files(root):
        try:
            text_blobs.append((path, path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    results: list[Candidate] = []
    for baseline in registry.get("baselines", []):
        if not isinstance(baseline, dict):
            continue
        baseline_id = str(baseline.get("id") or "")
        haystack = " ".join(str(baseline.get(field) or "") for field in ("id", "name", "paper", "citation_key"))
        tokens = tokenize(haystack)
        for path, text in text_blobs:
            lower = text.lower()
            if tokens and not any(token in lower for token in tokens):
                continue
            for url in URL_RE.findall(text):
                if "github.com" not in url and not GITHUB_RE.match(url):
                    continue
                results.append(score_url(baseline, url, f"local_note:{path.relative_to(root).as_posix()}"))
        repo_url = str(baseline.get("repo_url") or "").strip()
        if repo_url:
            results.append(score_url(baseline, repo_url, "registry", "official" if baseline.get("officiality") == "official" else ""))
        for query in baseline.get("repo_search_queries", []) if isinstance(baseline.get("repo_search_queries"), list) else []:
            for url in URL_RE.findall(str(query)):
                results.append(score_url(baseline, url, "registry_query"))
        if not any(candidate.baseline_id == baseline_id for candidate in results):
            for url in URL_RE.findall(haystack):
                results.append(score_url(baseline, url, "baseline_text"))
    return results


def github_search_candidates(registry: dict[str, Any]) -> list[Candidate]:
    results: list[Candidate] = []
    for baseline in registry.get("baselines", []):
        if not isinstance(baseline, dict):
            continue
        if baseline.get("repo_url"):
            continue
        query_text = str(baseline.get("paper") or baseline.get("name") or baseline.get("id") or "").strip()
        if not query_text:
            continue
        query = urllib.parse.urlencode({"q": f"{query_text} in:name,description,readme", "per_page": "5"})
        request = urllib.request.Request(
            f"https://api.github.com/search/repositories?{query}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "research-agent-workspace"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            continue
        for item in data.get("items", []):
            if not isinstance(item, dict) or not item.get("html_url"):
                continue
            license_name = ""
            if isinstance(item.get("license"), dict):
                license_name = str(item["license"].get("spdx_id") or item["license"].get("name") or "")
            officiality = "unknown"
            results.append(score_url(baseline, str(item["html_url"]), "github_search", officiality, license_name))
    return results


def dedupe(candidates: list[Candidate]) -> list[Candidate]:
    best: dict[tuple[str, str], Candidate] = {}
    for candidate in candidates:
        key = (candidate.baseline_id, candidate.url.lower().rstrip("/"))
        if key not in best or candidate.score > best[key].score:
            best[key] = candidate
    return sorted(best.values(), key=lambda item: (item.baseline_id, -item.score, item.url))


def write_reports(root: Path, candidates: list[Candidate]) -> tuple[Path, Path]:
    json_path = root / "08_baselines" / "repo_discovery_candidates.json"
    md_path = root / "08_baselines" / "repo_discovery_candidates.md"
    rows = [candidate.__dict__ for candidate in candidates]
    json_path.write_text(json.dumps({"project": root.name, "generated_at": now_iso(), "candidates": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Repo Discovery Candidates",
        "",
        "| Baseline | Score | Officiality | URL | Source | License |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for candidate in candidates:
        lines.append(
            f"| `{candidate.baseline_id}` | {candidate.score} | {candidate.officiality} | "
            f"{candidate.url} | `{candidate.source}` | {candidate.license or ''} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def apply_candidates(root: Path, candidates: list[Candidate], threshold: int) -> list[str]:
    best_by_baseline: dict[str, Candidate] = {}
    for candidate in candidates:
        if candidate.score < threshold:
            continue
        current = best_by_baseline.get(candidate.baseline_id)
        if current is None or candidate.score > current.score:
            best_by_baseline[candidate.baseline_id] = candidate
    applied: list[str] = []

    def mutate(registry: dict[str, Any]) -> None:
        for baseline in registry.get("baselines", []):
            if not isinstance(baseline, dict):
                continue
            baseline_id = str(baseline.get("id") or "")
            candidate = best_by_baseline.get(baseline_id)
            if not candidate or baseline.get("repo_url"):
                continue
            baseline["repo_url"] = candidate.url
            baseline["status"] = "source_found"
            baseline["license"] = candidate.license or baseline.get("license", "")
            baseline["repo_discovery_score"] = candidate.score
            baseline["repo_discovery_source"] = candidate.source
            baseline["repo_officiality"] = candidate.officiality
            baseline["updated_at"] = now_iso()
            applied.append(baseline_id)

    mutate_baseline_registry(root, mutate)
    return applied


def sync_repo_discovery_agent(root: Path, agent: str, candidates: list[Candidate], applied: list[str]) -> None:
    outputs = [
        "08_baselines/repo_discovery_candidates.json",
        "08_baselines/repo_discovery_candidates.md",
    ]
    if applied:
        outputs.append("08_baselines/baseline_registry.json")
    status = "blocked" if not candidates else "waiting"
    task = f"Resolved {len(candidates)} baseline repo candidate(s)."
    notes = f"Applied {len(applied)} candidate(s) to baseline_registry.json."
    sync_report_lifecycle(
        root,
        agent=agent,
        event_type="repo_discovery",
        status=status,
        task=task,
        outputs=outputs,
        notes=notes,
        refresh_report=False,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        registry = load_baseline_registry(root)
        candidates = candidates_from_local_notes(root, registry)
        candidates.extend(candidates_from_file(root, registry, args.candidate_file))
        if args.allow_network:
            candidates.extend(github_search_candidates(registry))
        candidates = dedupe(candidates)
        json_path, md_path = write_reports(root, candidates)
        applied = apply_candidates(root, candidates, args.threshold) if args.apply else []
        sync_repo_discovery_agent(root, args.agent, candidates, applied)
        payload = {
            "project": args.project,
            "candidate_count": len(candidates),
            "applied": applied,
            "json_report": json_path.relative_to(root).as_posix(),
            "markdown_report": md_path.relative_to(root).as_posix(),
            "candidates": [candidate.__dict__ for candidate in candidates],
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"repo candidates: {len(candidates)} -> {json_path.relative_to(root)}")
            if applied:
                print(f"applied: {', '.join(applied)}")
        return 0
    except (HarnessError, json.JSONDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
