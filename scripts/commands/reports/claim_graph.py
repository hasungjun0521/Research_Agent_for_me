#!/usr/bin/env python3
"""Build a working claim-to-evidence graph from project result ledgers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness.project_diagnostics import csv_rows, nonstarter_rows, project_display_name
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build 05_results/claim_graph.md and claim_graph.json.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", default="result_interpreter")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def node(node_id: str, kind: str, label: str, **extra: Any) -> dict[str, Any]:
    return {"id": node_id, "kind": kind, "label": label, **extra}


def edge(source: str, target: str, relation: str, **extra: Any) -> dict[str, Any]:
    return {"source": source, "target": target, "relation": relation, **extra}


def add_unique(nodes: dict[str, dict[str, Any]], value: dict[str, Any]) -> None:
    if value["id"] not in nodes:
        nodes[value["id"]] = value


def build_graph(root: Path) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    claim_rows = csv_rows(root / "09_report" / "results" / "claim_evidence.csv")
    for row in claim_rows:
        claim_id = row.get("claim_id") or "claim_missing"
        add_unique(nodes, node(f"claim:{claim_id}", "claim", row.get("claim") or claim_id, status=row.get("status", ""), caveat=row.get("caveat", ""), next_needed=row.get("next_needed", "")))
        evidence = row.get("evidence", "")
        if evidence:
            evidence_id = f"evidence:{claim_id}:{len(edges) + 1}"
            add_unique(nodes, node(evidence_id, "evidence", evidence, source="09_report/results/claim_evidence.csv"))
            edges.append(edge(evidence_id, f"claim:{claim_id}", "supports_or_limits", status=row.get("status", "")))

    result_sources = [
        ("05_results/experiment_results.csv", root / "05_results" / "experiment_results.csv"),
        ("09_report/results/experiment_results.csv", root / "09_report" / "results" / "experiment_results.csv"),
    ]
    for source_label, path in result_sources:
        for row in nonstarter_rows(csv_rows(path)):
            exp_id = row.get("experiment_id") or row.get("experiment") or row.get("run_id") or f"row_{len(nodes) + 1}"
            result_id = f"experiment:{exp_id}"
            add_unique(nodes, node(result_id, "experiment", exp_id, source=source_label, metric=row.get("metric", ""), value=row.get("value", ""), method=row.get("method", ""), dataset=row.get("dataset", "")))
            claim_id = row.get("claim_id") or row.get("claim") or ""
            if claim_id:
                add_unique(nodes, node(f"claim:{claim_id}", "claim", claim_id, status="working"))
                edges.append(edge(result_id, f"claim:{claim_id}", "tests", metric=row.get("metric", ""), value=row.get("value", "")))
            baseline = row.get("baseline_id") or row.get("baseline") or ""
            if baseline:
                add_unique(nodes, node(f"baseline:{baseline}", "baseline", baseline))
                edges.append(edge(result_id, f"baseline:{baseline}", "compares_against"))

    for row in nonstarter_rows(csv_rows(root / "05_results" / "experiment_journal.csv")):
        exp_id = row.get("experiment") or row.get("experiment_id") or f"journal_{len(nodes) + 1}"
        result_id = f"experiment:{exp_id}"
        add_unique(nodes, node(result_id, "experiment", exp_id, source="05_results/experiment_journal.csv", result_summary=row.get("result_summary", ""), result_analysis=row.get("result_analysis", "")))
        analysis = row.get("result_analysis") or row.get("analysis") or ""
        if analysis:
            analysis_id = f"analysis:{exp_id}"
            add_unique(nodes, node(analysis_id, "analysis", analysis, source="05_results/experiment_journal.csv"))
            edges.append(edge(analysis_id, result_id, "explains"))

    graph = {
        "schema_version": 1,
        "project": project_display_name(root),
        "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
        "edges": edges,
    }
    graph["summary"] = {
        "claims": len([item for item in graph["nodes"] if item["kind"] == "claim"]),
        "experiments": len([item for item in graph["nodes"] if item["kind"] == "experiment"]),
        "analysis_nodes": len([item for item in graph["nodes"] if item["kind"] == "analysis"]),
        "edges": len(edges),
    }
    return graph


def render_markdown(graph: dict[str, Any]) -> str:
    summary = graph["summary"]
    lines = [
        "# Claim Graph",
        "",
        f"- Project: `{graph['project']}`",
        f"- Claims: {summary['claims']}",
        f"- Experiments: {summary['experiments']}",
        f"- Analysis nodes: {summary['analysis_nodes']}",
        f"- Edges: {summary['edges']}",
        "",
        "## Nodes",
        "",
        "| ID | Kind | Label |",
        "| --- | --- | --- |",
    ]
    for item in graph["nodes"]:
        label = str(item.get("label", "")).replace("|", "\\|")
        lines.append(f"| `{item['id']}` | {item['kind']} | {label} |")
    lines.extend(["", "## Edges", "", "| Source | Relation | Target |", "| --- | --- | --- |"])
    for item in graph["edges"]:
        lines.append(f"| `{item['source']}` | {item['relation']} | `{item['target']}` |")
    lines.extend([
        "",
        "## Use",
        "",
        "- Use this graph before strengthening paper claims.",
        "- Missing `analysis` nodes mean experiments have results without a causal or diagnostic interpretation.",
        "- Keep this in `05_results/` until the claim evidence is stable enough for `09_report/results/`.",
    ])
    return "\n".join(lines) + "\n"


def run_graph(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    graph = build_graph(root)
    content = render_markdown(graph)
    outputs: list[str] = []
    if args.write:
        md = root / "05_results" / "claim_graph.md"
        js = root / "05_results" / "claim_graph.json"
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(content, encoding="utf-8")
        js.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        outputs = ["05_results/claim_graph.md", "05_results/claim_graph.json"]
        try:
            update_agent_status(root, args.agent, "done", task="Build working claim graph.", stage="claim graph", outputs=outputs, notes=f"Claim graph has {graph['summary']['edges']} edge(s).")
        except HarnessError:
            pass
        append_agent_event(root, "claim_graph", args.agent, status="done", task="Build working claim graph.", stage="claim graph", outputs=outputs, notes=f"Claim graph has {graph['summary']['claims']} claim node(s).")
        refresh_report_index(root)
    if args.json:
        print(json.dumps({"written": bool(args.write), "outputs": outputs, "graph": graph}, indent=2, ensure_ascii=False))
    else:
        print(content, end="")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run_graph(args)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
