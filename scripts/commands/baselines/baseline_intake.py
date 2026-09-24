#!/usr/bin/env python3
"""Ingest baseline papers, clone source repos, and scaffold adapters."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    load_baseline_registry,
    mutate_agent_messages,
    mutate_baseline_registry,
    now_iso,
    project_root,
    repo_root,
    split_values,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "wandb",
    "runs",
    "outputs",
    "checkpoints",
    "data",
    "datasets",
}
IGNORED_SUFFIXES = {
    ".pt",
    ".pth",
    ".ckpt",
    ".bin",
    ".zip",
    ".tar",
    ".gz",
    ".npy",
    ".npz",
    ".pkl",
    ".pickle",
}
DEPENDENCY_FILES = {
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "environment.yml",
    "environment.yaml",
    "package.json",
    "Pipfile",
    "poetry.lock",
}
ENTRYPOINT_NAMES = {
    "train.py",
    "main.py",
    "run.py",
    "eval.py",
    "evaluate.py",
    "test.py",
    "infer.py",
    "inference.py",
}
CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".toml", ".ini", ".cfg"}
SOURCE_SUFFIXES = {".py", ".ipynb", ".sh", ".yaml", ".yml", ".json", ".toml", ".md", ".txt"}
URL_PATTERN = re.compile(r"(https?://\S+|ssh://\S+|git@\S+:\S+|file://\S+)")


@dataclass
class BaselineSpec:
    id: str
    name: str = ""
    paper: str = ""
    repo_url: str = ""
    source_path: str = ""
    citation_key: str = ""
    method_family: str = ""
    expected_role: str = "baseline"
    owner_agent: str = "code_agent"
    datasets: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    notes: str = ""


def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    intake = subparsers.add_parser("intake", help="Manage baseline intake and inspection.")
    intake_sub = intake.add_subparsers(dest="intake_command", required=True)

    ingest = intake_sub.add_parser("ingest", help="Read a JSON/CSV/TXT baseline manifest.")
    ingest.add_argument("--project", required=True)
    ingest.add_argument("--manifest", required=True)
    ingest.add_argument("--clone", action="store_true")
    ingest.add_argument("--allow-network", action="store_true")
    ingest.add_argument("--message-missing-repos", action="store_true")
    ingest.add_argument("--write-smoke", action="store_true")
    ingest.add_argument("--owner", default="code_agent")
    ingest.add_argument("--max-files", type=int, default=500)

    discover = intake_sub.add_parser("discover", help="Create repo discovery queries.")
    discover.add_argument("--project", required=True)
    discover.add_argument("--id")
    discover.add_argument("--message-missing-repos", action="store_true")

    inspect = intake_sub.add_parser("inspect", help="Inspect registered baseline source.")
    inspect.add_argument("--project", required=True)
    inspect.add_argument("--id", required=True)
    inspect.add_argument("--write-smoke", action="store_true")
    inspect.add_argument("--max-files", type=int, default=500)


def slugify(value: str, fallback: str = "baseline") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    if not slug:
        slug = fallback
    if slug[0].isdigit():
        slug = f"baseline_{slug}"
    return slug[:60]


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return split_values([str(value)])


def normalize_spec(raw: dict[str, Any], index: int, owner: str) -> BaselineSpec:
    paper = str(raw.get("paper") or raw.get("citation") or raw.get("title") or "").strip()
    name = str(raw.get("name") or raw.get("method") or raw.get("title") or paper).strip()
    baseline_id = str(raw.get("id") or raw.get("baseline_id") or "").strip()
    if not baseline_id:
        baseline_id = slugify(name or paper or f"baseline_{index}", f"baseline_{index}")
    repo_url = str(raw.get("repo_url") or raw.get("repo") or raw.get("code_url") or "").strip()
    if Path(repo_url).is_absolute() or repo_url.startswith("file://"):
        path_text = repo_url.removeprefix("file://")
        p = Path(path_text).resolve()
        r = repo_root().resolve()
        try:
            if p.is_relative_to(r):
                repo_url = p.relative_to(r).as_posix()
        except ValueError:
            pass
    return BaselineSpec(
        id=slugify(baseline_id, f"baseline_{index}"),
        name=name,
        paper=paper,
        repo_url=repo_url,
        source_path=str(raw.get("source_path") or raw.get("local_snapshot") or "").strip(),
        citation_key=str(raw.get("citation_key") or "").strip(),
        method_family=str(raw.get("method_family") or "").strip(),
        expected_role=str(raw.get("expected_role") or raw.get("role") or "baseline").strip(),
        owner_agent=str(raw.get("owner_agent") or raw.get("owner") or owner).strip(),
        datasets=as_list(raw.get("datasets") or raw.get("dataset")),
        metrics=as_list(raw.get("metrics") or raw.get("metric")),
        notes=str(raw.get("notes") or raw.get("note") or "").strip(),
    )


def parse_text_manifest(path: Path, owner: str) -> list[BaselineSpec]:
    specs: list[BaselineSpec] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        url_match = URL_PATTERN.search(line)
        repo_url = url_match.group(1).rstrip(".,)") if url_match else ""
        if len(parts) >= 4:
            raw = {"id": parts[0], "name": parts[1], "paper": parts[2], "repo_url": parts[3]}
        elif len(parts) == 3:
            raw = {"name": parts[0], "paper": parts[1], "repo_url": parts[2]}
        elif len(parts) == 2:
            raw = {"name": parts[0], "paper": parts[1], "repo_url": repo_url}
        else:
            paper = line.replace(repo_url, "").strip(" -") if repo_url else line
            raw = {"paper": paper, "name": paper[:80], "repo_url": repo_url}
        specs.append(normalize_spec(raw, line_number, owner))
    return specs


def parse_manifest(path: Path, owner: str) -> list[BaselineSpec]:
    if not path.is_file():
        raise HarnessError(f"Manifest not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("baselines", data) if isinstance(data, dict) else data
        return [
            normalize_spec(row, i + 1, owner) for i, row in enumerate(rows) if isinstance(row, dict)
        ]
    if suffix in {".csv", ".tsv"}:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [
                normalize_spec(row, i + 1, owner)
                for i, row in enumerate(
                    csv.DictReader(handle, delimiter="\t" if suffix == ".tsv" else ",")
                )
            ]
    return parse_text_manifest(path, owner)


def resolve_manifest_path(root: Path, value: str) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    for c in [Path.cwd() / p, repo_root() / p, root / p]:
        if c.is_file():
            return c
    return root / p


def dedupe_specs(specs: list[BaselineSpec]) -> list[BaselineSpec]:
    seen: dict[str, int] = {}
    for s in specs:
        c = seen.get(s.id, 0)
        seen[s.id] = c + 1
        if c:
            s.id = f"{s.id}_{c + 1}"
    return specs


def repo_search_queries(spec: BaselineSpec) -> list[str]:
    b = spec.paper or spec.name
    q = [f'"{b}" code', f'"{b}" github', f'"{b}" official implementation']
    if spec.name and spec.name != b:
        q.append(f'"{spec.name}" "{spec.paper}" github')
    return q


def normalize_project_relative_path(v: str, f: str) -> str:
    if not v:
        return ""
    p = Path(v)
    if p.is_absolute() or ".." in p.parts:
        raise HarnessError(f"{f} must be relative: {v}")
    return p.as_posix()


def empty_registry_entry(spec: BaselineSpec) -> dict[str, Any]:
    t = now_iso()
    return {
        "id": spec.id,
        "name": "",
        "paper": "",
        "citation_key": "",
        "repo_url": "",
        "source_path": "",
        "local_snapshot": "",
        "working_dir": "",
        "license": "",
        "method_family": "",
        "expected_role": "baseline",
        "status": "candidate",
        "datasets": [],
        "dataset_paths": [],
        "metrics": [],
        "config_paths": [],
        "commands": {"inspect": [], "setup": [], "run": [], "evaluate": []},
        "result_paths": [],
        "reproduction_notes": "",
        "known_differences": "",
        "evidence_files": [],
        "repo_search_queries": [],
        "repo_commit": "",
        "structure_report": "",
        "adapter_path": "",
        "structure_score": 0,
        "owner_agent": spec.owner_agent,
        "created_at": t,
        "updated_at": t,
    }


def append_unique_list(target: list[str], values: list[str]) -> None:
    for v in values:
        if v and v not in target:
            target.append(v)


def upsert_baseline(root: Path, spec: BaselineSpec, updates: dict[str, Any] | None = None) -> None:
    def mutate(reg: dict[str, Any]) -> None:
        b = next((c for c in reg["baselines"] if c.get("id") == spec.id), None)
        if b is None:
            b = empty_registry_entry(spec)
            reg["baselines"].append(b)
        for f, v in {
            "name": spec.name,
            "paper": spec.paper,
            "citation_key": spec.citation_key,
            "repo_url": spec.repo_url,
            "source_path": spec.source_path,
            "local_snapshot": spec.source_path,
            "method_family": spec.method_family,
            "expected_role": spec.expected_role,
            "owner_agent": spec.owner_agent,
            "reproduction_notes": spec.notes,
        }.items():
            if v:
                b[f] = v
        append_unique_list(b.setdefault("datasets", []), spec.datasets)
        append_unique_list(b.setdefault("metrics", []), spec.metrics)
        append_unique_list(b.setdefault("repo_search_queries", []), repo_search_queries(spec))
        b.update(updates or {})
        cmds = b.setdefault("commands", {"inspect": [], "setup": [], "run": [], "evaluate": []})
        sp = b.get("source_path") or spec.source_path
        if sp:
            append_unique_list(
                cmds["inspect"],
                [
                    f"find {sp} -maxdepth 3 -type f | sort",
                    f'rg -n "class |def |argparse|config|dataset|metric|train|eval" {sp}',
                ],
            )
        if b.get("status") == "candidate" and (b.get("repo_url") or b.get("source_path")):
            b["status"] = "source_found"
        b["updated_at"] = now_iso()

    mutate_baseline_registry(root, mutate)


def clone_repo(root: Path, spec: BaselineSpec, allow_network: bool) -> tuple[str, str]:
    if not spec.repo_url:
        return "", "missing repo_url"
    destination = root / "08_baselines" / "source_snapshots" / spec.id
    if destination.exists() and any(destination.iterdir()):
        return destination.relative_to(root).as_posix(), "already exists"
    destination.parent.mkdir(parents=True, exist_ok=True)
    git = shutil.which("git")
    if not git:
        raise HarnessError("git required")
    subprocess.run(
        [git, "clone", "--depth", "1", spec.repo_url, str(destination)],
        check=True,
        capture_output=True,
    )
    return destination.relative_to(root).as_posix(), "cloned"


def git_commit(path: Path) -> str:
    git = shutil.which("git")
    if not git or not (path / ".git").exists():
        return ""
    r = subprocess.run(
        [git, "-C", str(path), "rev-parse", "HEAD"], text=True, capture_output=True, timeout=15
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def safe_read_snippet(path: Path, limit: int = 120_000) -> str:
    try:
        return (
            path.read_text(encoding="utf-8", errors="replace")
            if path.stat().st_size <= limit
            else ""
        )
    except OSError:
        return ""


def iter_source_files(source: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for c, ds, ns in os.walk(source):
        ds[:] = sorted(d for d in ds if d not in IGNORED_DIRS and not d.startswith("."))
        for n in sorted(ns):
            p = Path(c) / n
            if p.suffix.lower() in IGNORED_SUFFIXES:
                continue
            if p.suffix.lower() not in SOURCE_SUFFIXES and n not in DEPENDENCY_FILES:
                continue
            files.append(p)
            if len(files) >= max_files:
                return files
    return files


def inspect_source(root: Path, spec: BaselineSpec, max_files: int) -> dict[str, Any]:
    source = root / spec.source_path
    if not source.is_dir():
        raise HarnessError(f"Source not found: {spec.source_path}")
    files = iter_source_files(source, max_files)
    dep_f = []
    eps = []
    cfg_f = []
    tests = []
    docs = []
    pkgs = set()
    hits = {"data": [], "model": [], "training": [], "evaluation": [], "configuration": []}
    for p in files:
        rel = p.relative_to(source).as_posix()
        l_rel = rel.lower()
        if p.name in DEPENDENCY_FILES:
            dep_f.append(rel)
        if p.suffix.lower() in CONFIG_SUFFIXES or "config" in l_rel:
            cfg_f.append(rel)
        if "test" in l_rel:
            tests.append(rel)
        if p.suffix.lower() == ".md" or p.name.lower() in {"readme", "readme.txt"}:
            docs.append(rel)
        if p.name == "__init__.py":
            pkgs.add(str(Path(rel).parent))
        snip = safe_read_snippet(p)
        if p.name.lower() in ENTRYPOINT_NAMES or re.search(
            r"\b(argparse|click|hydra|fire)\b", snip
        ):
            eps.append(rel)
        if any(pt in {"data", "dataset", "loader"} for pt in Path(l_rel).parts):
            hits["data"].append(rel)
        if any(pt in {"model", "network", "module"} for pt in Path(l_rel).parts):
            hits["model"].append(rel)
        if any(tk in l_rel for tk in ("train", "trainer", "opt")):
            hits["training"].append(rel)
        if any(tk in l_rel for tk in ("eval", "metric", "test")):
            hits["evaluation"].append(rel)
        if p.suffix.lower() in CONFIG_SUFFIXES or "config" in l_rel:
            hits["configuration"].append(rel)
    score = (
        (2 if dep_f else 0)
        + (2 if eps else 0)
        + (2 if cfg_f else 0)
        + (1 if tests else 0)
        + (1 if docs else 0)
        + min(3, len(pkgs))
        + sum(1 for h in hits.values() if h)
    )
    return {
        "schema_version": 1,
        "project": root.name,
        "baseline_id": spec.id,
        "baseline_name": spec.name,
        "paper": spec.paper,
        "repo_url": spec.repo_url,
        "repo_commit": git_commit(source),
        "source_path": spec.source_path,
        "inspected_at": now_iso(),
        "structure_score": score,
        "file_count_inspected": len(files),
        "detected": {
            "dependency_files": dep_f[:25],
            "entrypoints": eps[:25],
            "config_files": cfg_f[:25],
            "tests": tests[:25],
            "docs": docs[:25],
            "package_dirs": sorted(pkgs)[:25],
            "components": {k: v[:25] for k, v in hits.items()},
        },
        "recommended_project_layout": {
            "source_snapshot": spec.source_path,
            "run_script_dir": "08_baselines/run_scripts",
            "patch_dir": f"08_baselines/patches/{spec.id}",
        },
        "adoption_plan": [
            "Keep source read-only.",
            "Record command/config.",
            "Document shims in code_adaptation_notes.md.",
        ],
    }


def report_paths(root: Path, bid: str) -> tuple[Path, Path]:
    d = root / "08_baselines" / "structure_reports"
    return d / f"{bid}.json", d / f"{bid}.md"


def write_structure_report(root: Path, report: dict[str, Any]) -> tuple[str, str]:
    j_p, m_p = report_paths(root, report["baseline_id"])
    j_p.parent.mkdir(parents=True, exist_ok=True)
    j_p.write_text(json.dumps(report, indent=2) + "\n")
    m_p.write_text(format_structure_report(report))
    return j_p.relative_to(root).as_posix(), m_p.relative_to(root).as_posix()


def bullet_list(vs: list[str]) -> str:
    return "".join(f"- `{v}`\n" for v in vs) if vs else "- none\n"


def format_structure_report(r: dict[str, Any]) -> str:
    d = r.get("detected", {})
    c = d.get("components", {})
    lines = [
        f"# Structure: {r['baseline_id']}",
        "",
        f"- Source: `{r.get('source_path')}`",
        f"- Score: {r.get('structure_score')}",
        "",
        "## Entry Points",
        "",
        bullet_list(d.get("entrypoints", [])),
        "## Components",
        "",
    ]
    for k in ("data", "model", "training", "evaluation", "configuration"):
        lines.extend([f"### {k.title()}", "", bullet_list(c.get(k, []))])
    return "\n".join(lines)


def smoke_runner_py(r: dict[str, Any]) -> str:
    bid = r["baseline_id"]
    sp = r.get("source_path") or ""
    eps = r.get("detected", {}).get("entrypoints", [])
    cfgs = r.get("detected", {}).get("config_files", [])
    return f"""#!/usr/bin/env python3
import json, os, subprocess, sys; from pathlib import Path
BID = {json.dumps(bid)}; SRP = {json.dumps(sp)}; EPS = {json.dumps(eps)}; CFGS = {json.dumps(cfgs)}
def main():
    root = Path(__file__).resolve().parents[2]; src = root / SRP; missing = []
    if not src.is_dir(): missing.append(str(src))
    for r in EPS[:3] + CFGS[:3]:
        if not (src / r).is_file(): missing.append(str(src / r))
    if missing: [print(f"- {{m}}") for m in missing]; return 1
    print(f"smoke OK: {{BID}}"); return 0
if __name__ == "__main__": sys.exit(main())
"""


def write_smoke_runner(root: Path, r: dict[str, Any]) -> str:
    p = root / "08_baselines" / "run_scripts" / f"{r['baseline_id']}_smoke.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(smoke_runner_py(r))
    p.chmod(0o755)
    return p.relative_to(root).as_posix()


def write_structure_plan(root: Path) -> str:
    d = root / "08_baselines" / "structure_reports"
    rs = []
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            rs.append(json.loads(p.read_text()))
    if not rs:
        return ""
    p_path = root / "08_baselines" / "code_structure_plan.md"
    lines = ["# Structure Plan", ""]
    for i, r in enumerate(sorted(rs, key=lambda x: x.get("structure_score", 0), reverse=True), 1):
        lines.append(
            f"| {i} | `{r['baseline_id']}` | {r.get('structure_score')} | `{r.get('source_path')}` |"
        )
    lines.extend(
        [
            "",
            "## Canonical Project Layout To Apply",
            "",
            "- `04_code/src/data/`",
            "- `04_code/src/evaluation/`",
            "- `04_code/tests/smoke/`",
            "- `08_baselines/run_scripts/`",
            "",
            "## Structure Decisions To Record",
            "",
            "- Which baseline conventions should be copied into `04_code/src/`, adapted behind a wrapper, or rejected?",
        ]
    )
    p_path.write_text("\n".join(lines) + "\n")
    return p_path.relative_to(root).as_posix()


def sync_baseline_agent(root, agent, event, task, outputs, note):
    update_agent_status(
        root,
        agent,
        "waiting",
        task=task,
        stage="baseline_intake",
        outputs=outputs,
        notes=note,
        append_note=True,
    )
    append_agent_event(
        root,
        event,
        agent,
        status="waiting",
        task=task,
        stage="baseline_intake",
        outputs=outputs,
        notes=note,
    )


def send_missing_repo_message(root: Path, spec: BaselineSpec) -> None:
    message_id = f"baseline_repo_{spec.id}"

    def mutate(messages: dict[str, Any]) -> None:
        if any(m.get("id") == message_id for m in messages.get("messages", [])):
            return
        messages.setdefault("messages", []).append(
            {
                "id": message_id,
                "from_agent": "director",
                "to_agent": "literature_reviewer",
                "kind": "request",
                "priority": "high",
                "status": "open",
                "subject": f"Find official repo for baseline {spec.id}",
                "body": f"Find code for {spec.paper or spec.name}.",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
        )

    mutate_agent_messages(root, mutate)


def write_discovery_report(root: Path, specs: list[BaselineSpec]) -> str:
    path = root / "08_baselines" / "repo_discovery_plan.md"
    lines = [
        "# Baseline Repo Discovery Plan",
        "",
        "| Baseline ID | Paper | Current Repo | Search Queries |",
        "| --- | --- | --- | --- |",
    ]
    for s in specs:
        qs = "<br>".join(f"`{q}`" for q in repo_search_queries(s))
        lines.append(f"| `{s.id}` | {s.paper or s.name} | {s.repo_url or 'missing'} | {qs} |")
    path.write_text("\n".join(lines) + "\n")
    return path.relative_to(root).as_posix()


def run_ingest(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    specs = dedupe_specs(parse_manifest(resolve_manifest_path(root, args.manifest), args.owner))
    processed = []
    outputs = ["08_baselines/baseline_registry.json"]
    for spec in specs:
        spec.source_path = normalize_project_relative_path(spec.source_path, "source_path")
        s_p = ""
        note = ""
        if args.clone and spec.repo_url:
            s_p, note = clone_repo(root, spec, args.allow_network)
        if s_p:
            spec.source_path = s_p
        upsert_baseline(root, spec, {"source_path": s_p, "local_snapshot": s_p})
        if spec.source_path:
            r = inspect_source(root, spec, args.max_files)
            rj, rm = write_structure_report(root, r)
            outputs.extend([rj, rm])
            sp = write_smoke_runner(root, r) if args.write_smoke else ""
            if sp:
                outputs.append(sp)
            upsert_baseline(
                root,
                spec,
                {
                    "structure_report": rj,
                    "structure_score": r.get("structure_score", 0),
                    "repo_commit": r.get("repo_commit", ""),
                    "smoke_script": sp,
                },
            )
        processed.append(spec.id)
    plan = write_structure_plan(root)
    if plan:
        outputs.append(plan)
    sync_baseline_agent(
        root,
        args.owner,
        "baseline_ingest",
        f"Processed {len(processed)} baseline entries.",
        outputs,
        "Baseline intake registered sources and structure reports.",
    )
    refresh_report_index(root)
    print(f"processed: {', '.join(processed)}")
    return 0


def run_inspect(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    reg = load_baseline_registry(root)
    b = next((i for i in reg.get("baselines", []) if i.get("id") == args.id), None)
    if not b:
        raise HarnessError(f"Not found: {args.id}")
    spec = normalize_spec(b, 1, b.get("owner_agent") or "code_agent")
    spec.id = args.id
    spec.source_path = normalize_project_relative_path(
        b.get("source_path") or b.get("local_snapshot") or "", "source_path"
    )
    r = inspect_source(root, spec, args.max_files)
    rj, rm = write_structure_report(root, r)
    sp = write_smoke_runner(root, r) if args.write_smoke else b.get("smoke_script", "")
    upsert_baseline(
        root,
        spec,
        {
            "structure_report": rj,
            "structure_score": r.get("structure_score", 0),
            "repo_commit": r.get("repo_commit", ""),
            "smoke_script": sp,
        },
    )
    plan = write_structure_plan(root)
    outputs = [rj, rm, sp, plan]
    sync_baseline_agent(
        root,
        b.get("owner_agent") or "code_agent",
        "baseline_inspect",
        f"Inspected baseline source structure for {args.id}.",
        [o for o in outputs if o],
        "Baseline structure report is ready.",
    )
    refresh_report_index(root)
    print(f"inspected: {args.id}")
    return 0


def run_discover(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    reg = load_baseline_registry(root)
    specs = []
    for b in reg.get("baselines", []):
        if args.id and b.get("id") != args.id:
            continue
        s = normalize_spec(b, 1, b.get("owner_agent") or "code_agent")
        s.id = b.get("id", s.id)
        specs.append(s)
        if args.message_missing_repos and not s.repo_url:
            send_missing_repo_message(root, s)
        upsert_baseline(root, s, {"repo_search_queries": repo_search_queries(s)})
    if not specs:
        raise HarnessError("No matching baselines.")
    p = write_discovery_report(root, specs)
    sync_baseline_agent(
        root,
        "literature_reviewer",
        "baseline_discover",
        "Prepared baseline repository discovery queries.",
        [p, "08_baselines/baseline_registry.json"],
        "Repo discovery plan ready.",
    )
    refresh_report_index(root)
    print(f"discovery plan: {p}")
    return 0


def main() -> int:
    from scripts.commands.baselines.baselines import main as baselines_main

    if len(sys.argv) > 1 and sys.argv[1] in {"ingest", "discover", "inspect"}:
        sys.argv.insert(1, "intake")
    elif len(sys.argv) < 2 or (
        len(sys.argv) >= 2
        and sys.argv[1] not in {"lib", "intake", "compare", "sandbox", "discovery"}
    ):
        sys.argv.insert(1, "intake")
    return baselines_main()


if __name__ == "__main__":
    raise SystemExit(main())
