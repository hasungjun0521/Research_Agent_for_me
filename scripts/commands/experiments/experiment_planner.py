#!/usr/bin/env python3
"""Plan smoke-first experiments and parallel launchable runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    append_agent_event,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index


def setup_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", default="experiment_designer")
    parser.add_argument("--experiment-id", default="exp_001")
    parser.add_argument("--parent-id", default="")
    parser.add_argument("--claim-id", default="claim_001")
    parser.add_argument("--hypothesis", default="")
    parser.add_argument("--dataset", default="")
    parser.add_argument("--metric", default="")
    parser.add_argument("--metric-regex", default="")
    parser.add_argument("--method", default="")
    parser.add_argument("--baseline", action="append", dest="baselines")
    parser.add_argument("--seed", action="append", dest="seeds")
    parser.add_argument("--smoke-command", default="")
    parser.add_argument("--full-command", default="")
    parser.add_argument("--gpu-type", default="auto")
    parser.add_argument("--expected-output", default="")
    parser.add_argument("--check-procedure", default="")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": args.experiment_id,
        "experiment_id": args.experiment_id,
        "parent_experiment_id": args.parent_id,
        "claim_id": args.claim_id,
        "hypothesis": args.hypothesis,
        "dataset": args.dataset,
        "metric": args.metric,
        "metric_regex": args.metric_regex,
        "method": args.method,
        "baselines": args.baselines or [],
        "seeds": args.seeds or [],
        "smoke_command": args.smoke_command,
        "full_command": args.full_command,
        "expected_output": args.expected_output,
        "check_procedure": args.check_procedure,
        "nodes": [],  # Simplified for now, real logic would build DAG nodes
    }


def render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Experiment Plan",
        "",
        f"- Experiment: `{plan['experiment_id']}`",
        f"- Parent: `{plan.get('parent_experiment_id') or 'none'}`",
        f"- Claim: `{plan['claim_id']}`",
        f"- Hypothesis: {plan.get('hypothesis') or 'missing'}",
        f"- Dataset: {plan.get('dataset') or 'missing'}",
        f"- Metric: {plan.get('metric') or 'missing'}",
    ]
    return "\n".join(lines) + "\n"


def append_plan(root: Path, plan: dict[str, Any], content: str) -> list[str]:
    path = root / "02_planning" / "experiment_plan.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    dag_path = root / "03_experiments" / "experiment_dag.json"
    dag_path.parent.mkdir(parents=True, exist_ok=True)
    dag_path.write_text(json.dumps({"plans": [plan]}, indent=2))
    return [str(path.relative_to(root)), str(dag_path.relative_to(root))]


def run_plan(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    plan = build_plan(args)
    content = render_markdown(plan)
    outputs = []
    if args.write:
        outputs = append_plan(root, plan, content)
        update_agent_status(
            root,
            args.agent,
            "done",
            task=f"Planned {args.experiment_id}.",
            stage="planning",
            outputs=outputs,
        )
        append_agent_event(
            root,
            "experiment_planner",
            args.agent,
            status="done",
            task=f"Planned {args.experiment_id}.",
            stage="planning",
            outputs=outputs,
        )
        refresh_report_index(root)
    if args.json:
        print(json.dumps({"plan": plan, "outputs": outputs}, indent=2, ensure_ascii=False))
    else:
        print(content)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan experiments.")
    setup_parser(parser)
    args = parser.parse_args()
    try:
        return run_plan(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
