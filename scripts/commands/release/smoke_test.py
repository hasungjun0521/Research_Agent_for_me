#!/usr/bin/env python3
"""End-to-end smoke test for the harness CLIs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from scripts.commands.experiments.gpu_monitor import classify_job
from scripts.commands.projects.create_project import replace_project_name
from scripts.harness.commands import python_module_command
from scripts.harness.state import repo_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the end-to-end harness smoke test.")
    parser.add_argument(
        "--keep-project",
        action="store_true",
        help="Keep the temporary smoke project for debugging failed runs.",
    )
    parser.add_argument(
        "--include-dashboard",
        action="store_true",
        help="Include optional dashboard compatibility checks.",
    )
    return parser.parse_args()


def run(
    cmd: list[str],
    *,
    expect_ok: bool = True,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd or repo_root(), env=env, text=True, capture_output=True)
    if expect_ok and result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    if not expect_ok and result.returncode == 0:
        print(result.stdout)
        raise RuntimeError(f"Command unexpectedly succeeded: {' '.join(cmd)}")
    return result


def repo_pythonpath_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(root) if not current else f"{root}{os.pathsep}{current}"
    return env


def remove_smoke_tree(path: Path) -> None:
    """Remove only generated smoke fixtures, including read-only Git objects."""
    resolved = path.resolve()
    workspace = repo_root().resolve()
    allowed = False
    for parent in (workspace / "projects", workspace / "tmp"):
        try:
            relative = resolved.relative_to(parent)
        except ValueError:
            continue
        if relative.parts and relative.parts[0].startswith(("ci_smoke_", "ci_import_")):
            allowed = True
    if not allowed:
        raise RuntimeError(f"Refusing cleanup outside generated smoke fixture: {resolved}")

    def clear_readonly(function, filename, error):
        if not isinstance(error[1], PermissionError):
            raise error[1]
        os.chmod(filename, stat.S_IWRITE | stat.S_IREAD)
        function(filename)

    shutil.rmtree(resolved, onerror=clear_readonly)


def create_local_baseline_repo(destination: Path) -> Path:
    external_repo = destination / "_external_smoke_baseline_repo"
    if external_repo.exists():
        remove_smoke_tree(external_repo)
    (external_repo / "models").mkdir(parents=True)
    (external_repo / "configs").mkdir()
    (external_repo / "tests").mkdir()
    (external_repo / "requirements.txt").write_text("torch\n", encoding="utf-8")
    (external_repo / "train.py").write_text(
        "import argparse\n\n"
        "def main():\n"
        "    argparse.ArgumentParser().parse_args()\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n",
        encoding="utf-8",
    )
    (external_repo / "models" / "model.py").write_text("class SmokeModel:\n    pass\n", encoding="utf-8")
    (external_repo / "configs" / "default.yaml").write_text("seed: 1\n", encoding="utf-8")
    (external_repo / "tests" / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    run(["git", "init"], cwd=external_repo)
    run(["git", "add", "."], cwd=external_repo)
    run([
        "git",
        "-c",
        "user.name=Smoke Test",
        "-c",
        "user.email=smoke@example.com",
        "commit",
        "-m",
        "init",
    ], cwd=external_repo)
    return external_repo


def create_import_source_repo(root: Path, name: str) -> Path:
    source = root / "tmp" / name
    if source.exists():
        remove_smoke_tree(source)
    (source / "src").mkdir(parents=True)
    (source / "results").mkdir()
    (source / ".git").mkdir()
    (source / "checkpoints").mkdir()
    (source / "README.md").write_text("# Existing Research Repo\n\nSmoke import fixture.\n", encoding="utf-8")
    (source / "train.py").write_text("print('train')\n", encoding="utf-8")
    (source / "src" / "model.py").write_text("class SmokeModel:\n    pass\n", encoding="utf-8")
    (source / "results" / "metrics.csv").write_text("metric,value\naccuracy,0.9\n", encoding="utf-8")
    (source / ".env").write_text("SECRET=do-not-copy\n", encoding="utf-8")
    (source / "checkpoints" / "model.pt").write_text("do-not-copy\n", encoding="utf-8")
    return source


def sanitize_copied_template_state(destination: Path) -> None:
    """Remove volatile harness-maintenance state from a copied template project."""

    queue_path = destination / "state" / "command_queue.json"
    if queue_path.is_file():
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        queue["commands"] = [
            command
            for command in queue.get("commands", [])
            if str(command.get("id") or "").startswith("cmd_")
        ]
        for command in queue["commands"]:
            if command.get("status") == "in progress":
                command["status"] = "open"
                command["notes"] = ""
        queue_path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")

    status_path = destination / "state" / "agent_status.json"
    if status_path.is_file():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        for agent in status.get("agents", []):
            if agent.get("status") == "running":
                agent["status"] = "idle"
                agent["started_at"] = ""
                agent["updated_at"] = ""
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


def run_publishable_check_smoke(root: Path) -> None:
    tmp_root = root / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="publishable_check_smoke_", dir=tmp_root) as fixture_dir:
        fixture = Path(fixture_dir)
        fixture.mkdir(parents=True, exist_ok=True)
        run(["git", "init"], cwd=fixture)
        check_cmd = python_module_command("check_publishable.py")
        privacy_cmd = python_module_command("privacy_audit.py")
        module_env = repo_pythonpath_env(root)

        (fixture / "README.md").write_text("# Smoke Harness\n", encoding="utf-8")
        run(check_cmd, cwd=fixture, env=module_env, expect_ok=False)

        (fixture / "HANDOFF.md").write_text("# HANDOFF\n", encoding="utf-8")
        run(check_cmd, cwd=fixture, env=module_env, expect_ok=False)

        (fixture / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
        run(check_cmd, cwd=fixture, env=module_env, expect_ok=False)

        (fixture / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
        run(check_cmd, cwd=fixture, env=module_env)
        run(privacy_cmd, cwd=fixture, env=module_env)

        (fixture / ".gitignore").write_text("projects/*\n!projects/template/\n!projects/template/**\n", encoding="utf-8")
        private_project = fixture / "projects" / "private_research"
        private_project.mkdir(parents=True)
        (private_project / "notes.md").write_text("# Private Notes\n", encoding="utf-8")
        run(check_cmd, cwd=fixture, env=module_env)

        (fixture / "README.md").write_text("# Smoke Harness\nprivate_research\n", encoding="utf-8")
        run(check_cmd, cwd=fixture, env=module_env, expect_ok=False)
        run(privacy_cmd, cwd=fixture, env=module_env, expect_ok=False)
        (fixture / "README.md").write_text("# Smoke Harness\n", encoding="utf-8")

        private_dataset_root = "/" + "scratch/private_dataset/root"
        (fixture / "README.md").write_text(f"# Smoke Harness\n{private_dataset_root}\n", encoding="utf-8")
        run(check_cmd, cwd=fixture, env=module_env, expect_ok=False)
        run(privacy_cmd, cwd=fixture, env=module_env, expect_ok=False)
        (fixture / "README.md").write_text("# Smoke Harness\n", encoding="utf-8")

        (fixture / "state.json.lock").write_text("", encoding="utf-8")
        run(check_cmd, cwd=fixture, env=module_env, expect_ok=False)
        (fixture / "state.json.lock").unlink()


def run_dashboard_js_behavior_smoke(root: Path) -> None:
    if not shutil.which("node"):
        return
    script = r"""
const fs = require('fs');
const html = fs.readFileSync('dashboard/index.html', 'utf8');
const core = fs.readFileSync('dashboard/core.js', 'utf8');
const app = fs.readFileSync('dashboard/app.js', 'utf8');
fs.readFileSync('dashboard/styles.css', 'utf8');
if (html.includes('Agent Command Flow')) throw new Error('old dashboard flow title is still visible');
if (/Harness Health/i.test(html) || /harness health/i.test(app)) {
  throw new Error('Harness Health should not be visible in the dashboard UI');
}
if (!html.includes('Pipeline & Handoff')) throw new Error('compact pipeline panel is missing');
if (!html.includes('data-view="work"')) throw new Error('work view is missing');
if (!html.includes('data-view="results"')) throw new Error('results view is missing');
if (!html.includes('data-view="console"')) throw new Error('console view is missing');
if (!html.includes('data-view="debug"')) throw new Error('debug view is missing');
if (html.includes('data-view="raw"')) throw new Error('old raw view is still exposed');
if (!html.includes('overview-console')) throw new Error('overview operations console is missing');
if (!html.includes('What is happening now') || !html.includes('What was completed') || !html.includes('Results and artifacts') || !html.includes('What is blocked')) {
  throw new Error('overview does not expose the required human summary lanes');
}
for (const required of [
  'Run Readiness Gate',
  'Research Readiness',
  'Research Phase Map',
  'Command Board',
  'Blocker Triage',
  'Command Console',
  'Command Output',
  'Evidence Map',
  'Experiment Comparison',
  'Table Preview',
  'Data Coverage'
]) {
  if (!html.includes(required)) throw new Error(`${required} surface is missing`);
}
if (!html.includes('href="styles.css"')) throw new Error('dashboard stylesheet link missing');
if (!html.includes('src="core.js"')) throw new Error('dashboard core script link missing');
if (!html.includes('src="app.js"')) throw new Error('dashboard app script link missing');
if (html.indexOf('src="core.js"') > html.indexOf('src="app.js"')) throw new Error('dashboard core script must load before app script');
if (/<style>[\s\S]*<\/style>/.test(html)) throw new Error('dashboard index still contains inline CSS');
if (/<script>[\s\S]*<\/script>/.test(html)) throw new Error('dashboard index still contains inline JS');
if (!core.includes('window.DashboardCore')) throw new Error('dashboard core namespace is missing');
const prefix = app.split("input.addEventListener('change', loadProject);")[0];
if (!prefix || prefix === app) throw new Error('dashboard app bootstrap split point not found');

const elements = new Map();
function element() {
  return {
    hidden: false,
    value: '',
    textContent: '',
    innerHTML: '',
    style: {},
    dataset: {},
    classList: { toggle() {}, add() {}, remove() {} },
    setAttribute() {},
    focus() {},
    addEventListener() {}
  };
}

global.document = {
  hidden: false,
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  },
  querySelector(selector) {
    const id = `selector:${selector}`;
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  },
  querySelectorAll() { return []; },
  addEventListener() {}
};
global.window = {
  location: { protocol: 'file:', search: '', href: 'file:///dashboard/index.html' },
  clearInterval() {},
  setInterval() { return 1; },
  setTimeout() {}
};
global.navigator = { clipboard: { writeText: async () => {} } };

const helpers = new Function(`${core}
${prefix}
return { statusData, renderActivityStack, renderLoopResults, renderKoreanSummary, renderReportSnapshot, renderTablePreviews, renderAgentFlow, renderExecutiveSummary, renderOverviewBoard, renderResearchReadiness, renderResearchPhaseTrack, renderRunReadinessGate, renderEvidenceMap, renderExperimentComparison, renderBlockerTriage, renderCommandBoard, renderCommandConsole, renderDataSources, overviewAutoSummary, applyViewMode, uiState };`)();
const fixedNow = Date.parse('2026-05-11T12:00:00+09:00');
Date.now = () => fixedNow;

const overviewSection = { dataset: { dashboardSection: 'overview' }, hidden: false };
const workSection = { dataset: { dashboardSection: 'work' }, hidden: false };
const resultsSection = { dataset: { dashboardSection: 'results' }, hidden: false };
const consoleSection = { dataset: { dashboardSection: 'console' }, hidden: false };
const debugSection = { dataset: { dashboardSection: 'debug' }, hidden: false };
document.querySelectorAll = (selector) => (
  selector === '[data-dashboard-section]'
    ? [overviewSection, workSection, resultsSection, consoleSection, debugSection]
    : []
);
helpers.uiState.view = 'overview';
helpers.applyViewMode();
if (overviewSection.hidden || !workSection.hidden || !resultsSection.hidden || !consoleSection.hidden || !debugSection.hidden) {
  throw new Error('default Overview view should hide Work, Results, Console, and Debug sections');
}

const events = [
  {
    timestamp: '2026-05-11T11:30:00+09:00',
    event: 'heartbeat',
    agent: 'director',
    status: 'running',
    task: 'old activity'
  },
  {
    timestamp: '2026-05-11T11:59:00+09:00',
    event: 'finish',
    agent: 'director',
    status: 'done',
    task: 'finished activity'
  },
  {
    timestamp: '2026-05-11T11:58:00+09:00',
    event: 'activity',
    agent: 'director',
    status: 'running',
    task: 'fresh activity'
  }
];

const data = helpers.statusData({ project: 'smoke', agents: [], agent_events: events }, '', '', 'smoke');
const stack = helpers.renderActivityStack(data);
if (data.recentActivity.length !== 1 || !stack.includes('fresh activity')) {
  throw new Error('fresh hook activity was not shown in the live fallback');
}
if (stack.includes('old activity') || stack.includes('finished activity')) {
  throw new Error('stale or terminal events leaked into the live fallback');
}
helpers.renderKoreanSummary(data);
const eventWorkSummary = elements.get('koreanWorkSummary').textContent;
if (!eventWorkSummary.includes('finished activity')) {
  throw new Error('Korean work summary did not fall back to the latest terminal agent event');
}
helpers.renderOverviewBoard(data);
const overviewNow = elements.get('overviewNow').innerHTML;
const overviewCompleted = elements.get('overviewCompleted').innerHTML;
if (!overviewNow.includes('fresh activity')) {
  throw new Error('overview did not show active hook work in the happening-now lane');
}
if (!overviewCompleted.includes('finished activity')) {
  throw new Error('overview did not show completed event fallback in the completed lane');
}

const runningData = helpers.statusData({
  project: 'smoke',
  agents: [{ name: 'director', display_name: 'Director', status: 'running', current_task: 'live work' }],
  agent_events: events
}, '', '', 'smoke');
const runningStack = helpers.renderActivityStack(runningData);
if (!runningStack.includes('live work') || runningStack.includes('fresh activity')) {
  throw new Error('running agents should take precedence over event fallback activity');
}

const resultsHtml = helpers.renderLoopResults({
  loopSummary: {
    results: [
      { title: 'old result', status: 'done', updated_at: '2026-05-11T10:00:00+09:00' },
      { title: 'new result', status: 'done', updated_at: '2026-05-11T11:00:00+09:00' }
    ]
  }
});
if (resultsHtml.indexOf('new result') > resultsHtml.indexOf('old result')) {
  throw new Error('loop results should render newest-first');
}

const reportData = helpers.statusData({
  project: 'smoke',
  workspace_profile: {
    display: {
      summary_language: 'ko',
      top_summary_labels: {
        work: '이번 instruction에서 한 일',
        result: '결과 분석',
        next: '다음 해야 할 것'
      }
    }
  },
  agents: [],
  loop_summary: { summary: '', completed_commands: [], results: [], next_actions: [] },
  report_snapshot: {
    readme_path: '09_report/README.md',
    readme_excerpt: '# Smoke Report\n\n## Final Artifact Index\n\nStable artifacts only.',
    tables: [{
      path: '09_report/results/experiment_results.csv',
      name: 'experiment_results.csv',
      rows: 1,
      updated_at: '2026-05-11T11:59:00+09:00',
      columns: ['exp_id', 'method', 'metric', 'value'],
      preview_rows: [['exp_001', 'smoke_method', 'accuracy', '0.9']],
      preview_limit: 5,
      preview_truncated: false
    }, {
      path: '09_report/results/claim_evidence.csv',
      name: 'claim_evidence.csv',
      rows: 1,
      updated_at: '2026-05-11T11:58:00+09:00',
      columns: ['claim_id', 'claim', 'status', 'evidence', 'experiments', 'robustness', 'caveat', 'next_needed'],
      preview_rows: [['claim_smoke', 'Smoke claim', 'observed', 'evidence.md', 'exp_001', 'ok', '', 'next']],
      preview_limit: 5,
      preview_truncated: false
    }],
    latest_files: [{ path: '09_report/results/experiment_results.csv', name: 'experiment_results.csv', kind: 'csv', updated_at: '2026-05-11T11:59:00+09:00' }]
  }
}, '', '', 'smoke');
helpers.renderKoreanSummary(reportData);
const resultSummary = elements.get('koreanResultSummary').textContent;
if (!resultSummary.includes('09_report') || !resultSummary.includes('1개 data row')) {
  throw new Error('Korean result summary did not use report result table data');
}
const englishData = helpers.statusData({
  project: 'smoke',
  workspace_profile: {
    display: {
      summary_language: 'en',
      top_summary_labels: {
        work: 'What happened this instruction',
        result: 'Result analysis',
        next: 'Next action'
      }
    }
  },
  agents: [],
  loop_summary: { summary: '', completed_commands: [], results: [], next_actions: [] },
  report_snapshot: reportData.reportSnapshot
}, '', '', 'smoke');
helpers.renderKoreanSummary(englishData);
if (!document.querySelector('.korean-summary-card.work .korean-summary-title').textContent.includes('What happened')) {
  throw new Error('Workspace profile did not switch dashboard summary labels to English');
}
if (!elements.get('koreanResultSummary').textContent.includes('data row') || elements.get('koreanResultSummary').textContent.includes('1개')) {
  throw new Error('Workspace profile did not switch dashboard summary body to English');
}
helpers.renderKoreanSummary(reportData);
helpers.renderExecutiveSummary(reportData);
const heroSummary = elements.get('heroSummary').textContent;
if (heroSummary.includes('No loop summary') || !heroSummary.includes('09_report/results/experiment_results.csv')) {
  throw new Error('Overview auto-summary did not fall back to report result table data');
}
helpers.renderReportSnapshot(reportData);
const reportHtml = elements.get('reportResultList').innerHTML;
if (!reportHtml.includes('실험 결과표') || !reportHtml.includes('09_report/results/experiment_results.csv')) {
  throw new Error('Report Results panel did not render report table data');
}
if (!reportHtml.includes('Columns: exp_id, method, metric, value')) {
  throw new Error('Report Results panel did not expose table columns');
}
const reportSnapshotSummary = elements.get('reportSnapshotSummary').innerHTML;
const reportReadmeExcerpt = elements.get('reportReadmeExcerpt').textContent;
if (!reportSnapshotSummary.includes('2 total data rows') || !reportReadmeExcerpt.includes('Smoke Report')) {
  throw new Error('Results view did not render the 09_report snapshot summary');
}
helpers.renderTablePreviews(reportData);
const tablePreviewHtml = elements.get('tablePreviewList').innerHTML;
if (!tablePreviewHtml.includes('smoke_method') || !tablePreviewHtml.includes('accuracy')) {
  throw new Error('Table Preview did not render CSV preview rows');
}
helpers.renderOverviewBoard(reportData);
const overviewResults = elements.get('overviewResults').innerHTML;
if (!overviewResults.includes('09_report/results/experiment_results.csv') || !overviewResults.includes('1 data row')) {
  throw new Error('overview result lane did not expose sparse-loop report tables');
}
const overviewPrompt = elements.get('overviewNextPromptText').textContent;
if (!overviewPrompt.includes('Continue the research project smoke')) {
  throw new Error('overview next prompt preview was not populated');
}
helpers.renderResearchReadiness(reportData);
helpers.renderResearchPhaseTrack(reportData);
if (!elements.get('readinessGrid').innerHTML.includes('Evidence Tables') || !elements.get('researchPhaseTrack').innerHTML.includes('Analysis')) {
  throw new Error('Research readiness or phase map did not render');
}
if (elements.get('readinessGrid').innerHTML.includes('Health') || elements.get('readinessGrid').innerHTML.includes('harness warning')) {
  throw new Error('Research readiness should not surface harness health noise');
}
helpers.renderRunReadinessGate(reportData);
helpers.renderEvidenceMap(reportData);
helpers.renderExperimentComparison(reportData);
if (!elements.get('runReadinessGate').innerHTML.includes('Needs next command')) {
  throw new Error('Run Readiness Gate did not render a decision-grade verdict');
}
if (!elements.get('evidenceMapList').innerHTML.includes('claim_smoke') || !elements.get('evidenceMapList').innerHTML.includes('exp_001')) {
  throw new Error('Evidence Map did not link claims to experiments/results');
}
if (!elements.get('experimentComparisonTable').innerHTML.includes('smoke_method') || !elements.get('experimentComparisonTable').innerHTML.includes('0.9')) {
  throw new Error('Experiment Comparison did not render metric rows');
}

const sourceData = helpers.statusData({
  project: 'smoke',
  agents: [],
  health_warnings: ['simulated validation warning'],
  data_sources: {
    generated_at: '2026-05-11T12:00:00+09:00',
    coverage: { available: 2, total: 3, required_missing: ['state/loop_summary.json'] },
    sources: [
      { key: 'agent_status', label: 'Agent Status', path: 'state/agent_status.json', status: 'available', required: true, records: 3, updated_at: '2026-05-11T11:59:00+09:00' },
      { key: 'command_queue', label: 'Command Queue', path: 'state/command_queue.json', status: 'available', required: true, records: 2, updated_at: '2026-05-11T11:58:00+09:00' },
      { key: 'loop_summary', label: 'Loop Summary', path: 'state/loop_summary.json', status: 'missing', required: true, records: 0, updated_at: '' }
    ]
  }
}, '', '', 'smoke');
helpers.renderOverviewBoard(sourceData);
if (elements.get('overviewBlocked').innerHTML.includes('Harness') || elements.get('overviewBlocked').innerHTML.includes('simulated validation warning')) {
  throw new Error('overview blockers should hide harness health warnings');
}
helpers.renderDataSources(sourceData);
const sourceHtml = elements.get('sourceCoverageList').innerHTML;
if (!sourceHtml.includes('Agent Status') || !sourceHtml.includes('state/loop_summary.json')) {
  throw new Error('Data Coverage did not render dashboard source manifest');
}
if (!elements.get('sourceCoverageCount').textContent.includes('2/3')) {
  throw new Error('Data Coverage did not summarize source availability');
}

const blockerData = helpers.statusData({
  project: 'smoke',
  agents: [{ name: 'venue_reviewer', display_name: 'Venue Reviewer', status: 'blocked', current_task: 'Need dataset approval', stage: 'analysis' }],
  command_queue: {
    commands: [{
      id: 'cmd_blocked',
      action: 'Resolve dataset issue',
      owner_agent: 'venue_reviewer',
      priority: 'high',
      status: 'blocked',
      display_summary: 'Dataset approval is missing.',
      done_when: 'Dataset approval is recorded.'
    }]
  },
  agent_messages: {
    messages: [{
      id: 'msg_blocker',
      kind: 'blocker',
      priority: 'high',
      status: 'open',
      subject: 'Dataset approval needed',
      body: 'The experiment cannot run without approval.',
      from_agent: 'venue_reviewer',
      to_agent: 'director',
      related_command_id: 'cmd_blocked'
    }]
  }
}, '', '', 'smoke');
helpers.renderBlockerTriage(blockerData);
const triageHtml = elements.get('blockerTriageList').innerHTML;
if (!triageHtml.includes('Dataset approval') || !triageHtml.includes('Workflow') || !triageHtml.includes('Research')) {
  throw new Error('Blocker Triage did not group command/message/agent blockers');
}

const flowData = helpers.statusData({
  project: 'smoke',
  agents: [{ name: 'code_agent', display_name: 'Code Agent', status: 'running', current_task: 'Run smoke' }],
  command_queue: {
    commands: [{
      id: 'cmd_flow',
      action: 'Run the smoke experiment',
      owner_agent: 'code_agent',
      priority: 'high',
      status: 'in progress',
      display_summary: 'Run the smoke experiment.',
      done_when: 'The run log and result table exist.'
    }]
  },
  agent_votes: { votes: [{ id: 'vote_001', status: 'open' }] },
  ralph_loop: { runs: [{ id: 'ralph_smoke', status: 'complete', iterations: [], stop_reason: 'Result file condition met.' }] },
  command_runner: {
    enabled: true,
    commands: [
      { id: 'dashboard_refresh', title: 'Refresh Dashboard Inputs' },
      { id: 'project_closeout', title: 'Project Closeout Audit' },
      { id: 'validate_project', title: 'Validate Project' }
    ]
  }
}, '', '', 'smoke');
helpers.renderAgentFlow(flowData);
helpers.renderCommandBoard(flowData);
helpers.renderCommandConsole(flowData);
const flowHtml = elements.get('agentFlowDiagram').innerHTML;
if (!flowHtml.includes('pipeline-step') || flowHtml.includes('<svg')) {
  throw new Error('Pipeline panel should render compact cards instead of the old SVG flow');
}
const flowSummary = elements.get('agentFlowSummary').innerHTML;
if (!flowSummary.includes('Open votes') || !flowSummary.includes('Code Agent')) {
  throw new Error('Pipeline summary did not surface vote and owner routing');
}
const boardHtml = elements.get('commandBoard').innerHTML;
if (!boardHtml.includes('Run the smoke experiment') || !boardHtml.includes('Running')) {
  throw new Error('Command Board did not render active command lanes');
}
const consoleHtml = elements.get('consoleCommandList').innerHTML;
const consolePrompt = elements.get('consolePromptText').textContent;
const consoleEvents = elements.get('consoleEventStream').textContent;
if (!consoleHtml.includes('Ralph Loop Template') || !consoleHtml.includes('scripts.commands.projects.validate_project') || !consoleHtml.includes('scripts.commands.dashboard.dashboard_refresh') || !consoleHtml.includes('scripts.commands.projects.project_closeout')) {
  throw new Error('Command Console did not render safe runbook commands');
}
if (!consoleHtml.includes('data-run-command="validate_project"') || !consoleHtml.includes('data-run-command="dashboard_refresh"') || !consoleHtml.includes('data-run-command="project_closeout"')) {
  throw new Error('Command Console did not expose enabled safe command runner actions');
}
if (!consolePrompt.includes('Run the smoke experiment') || !consoleEvents.includes('no recent agent events')) {
  throw new Error('Command Console did not render prompt and event stream');
}
"""
    run(["node", "-e", script], cwd=root)


def run_dashboard_server_asset_smoke() -> None:
    from scripts.commands.agents.agent_dashboard import DashboardHandler

    class SmokeDashboardHandler(DashboardHandler):
        default_project = "template"
        share_token = ""
        command_runner_enabled = False

        def log_message(self, format: str, *args: object) -> None:
            return

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), SmokeDashboardHandler)
    except PermissionError as exc:
        print(f"warning: dashboard server asset smoke skipped: {exc}", file=sys.stderr)
        return
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        checks = (
            ("/", "text/html", 'src="core.js"'),
            ("/core.js", "application/javascript", "window.DashboardCore"),
            ("/app.js", "application/javascript", "projectSelect"),
            ("/styles.css", "text/css", ":root"),
            ("/api/projects", "application/json", '"projects"'),
        )
        for path, expected_type, marker in checks:
            connection = HTTPConnection(host, port, timeout=5)
            try:
                connection.request("GET", path)
                response = connection.getresponse()
                body = response.read().decode("utf-8", errors="replace")
                content_type = response.getheader("Content-Type", "")
            finally:
                connection.close()
            if response.status != 200:
                raise RuntimeError(f"Dashboard route {path} returned HTTP {response.status}.")
            if expected_type not in content_type:
                raise RuntimeError(f"Dashboard route {path} returned unexpected content type: {content_type}.")
            if marker not in body:
                raise RuntimeError(f"Dashboard route {path} did not include expected marker: {marker}.")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_dashboard_project_smoke(project_name: str, destination: Path) -> None:
    from scripts.commands.agents.agent_dashboard import build_dashboard_data
    from scripts.commands.dashboard.dashboard_command_runner import run_dashboard_command
    from scripts.commands.dashboard.dashboard_sources import build_dashboard_sources
    from scripts.commands.reports.report_snapshot import build_report_snapshot

    dashboard_payload = build_dashboard_data(project_name)
    report_snapshot = dashboard_payload.get("report_snapshot") or {}
    table_rows = {
        table.get("path"): table.get("rows")
        for table in report_snapshot.get("tables", [])
    }
    if table_rows.get("09_report/results/experiment_results.csv") != 1:
        raise RuntimeError("dashboard API did not expose the 09_report result table rows.")
    shared_snapshot = build_report_snapshot(destination)
    if report_snapshot.get("tables") != shared_snapshot.get("tables"):
        raise RuntimeError("dashboard API report snapshot drifted from the shared report snapshot helper.")
    shared_sources = build_dashboard_sources(destination)
    if dashboard_payload.get("data_sources", {}).get("coverage") != shared_sources.get("coverage"):
        raise RuntimeError("dashboard API source manifest drifted from the shared dashboard source helper.")
    required_missing = dashboard_payload.get("data_sources", {}).get("coverage", {}).get("required_missing", [])
    if required_missing:
        raise RuntimeError(f"dashboard API reported missing required sources: {required_missing}")
    command_result = run_dashboard_command(project_name, "dashboard_sources")
    if not command_result["ok"] or '"required_missing": []' not in command_result["stdout"]:
        raise RuntimeError("safe dashboard command runner did not execute the dashboard source check.")
    refresh_result = run_dashboard_command(project_name, "dashboard_refresh")
    if not refresh_result["ok"] or '"mode": "write"' not in refresh_result["stdout"]:
        raise RuntimeError("safe dashboard command runner did not execute the dashboard refresh hook.")
    closeout_result = run_dashboard_command(project_name, "project_closeout")
    if not closeout_result["ok"] or "Project Closeout Audit" not in closeout_result["stdout"]:
        raise RuntimeError("safe dashboard command runner did not execute the project closeout hook.")
    source_result = run_dashboard_command(project_name, "source_credibility")
    if not source_result["ok"] or '"citation_integrity"' not in source_result["stdout"]:
        raise RuntimeError("safe dashboard command runner did not execute the source credibility audit.")
    diagnosis_result = run_dashboard_command(project_name, "experiment_diagnosis")
    if not diagnosis_result["ok"] or '"experiments"' not in diagnosis_result["stdout"]:
        raise RuntimeError("safe dashboard command runner did not execute the experiment diagnosis hook.")
    phase_result = run_dashboard_command(project_name, "phase_gate_audit")
    if not phase_result["ok"] or '"phases"' not in phase_result["stdout"]:
        raise RuntimeError("safe dashboard command runner did not execute the phase gate audit.")
    resource_result = run_dashboard_command(project_name, "resource_ledger")
    if not resource_result["ok"] or '"totals"' not in resource_result["stdout"]:
        raise RuntimeError("safe dashboard command runner did not execute the resource ledger summary.")
    checkpoint_result = run_dashboard_command(project_name, "run_checkpoints")
    if not checkpoint_result["ok"] or "smoke_checkpoint" not in checkpoint_result["stdout"]:
        raise RuntimeError("safe dashboard command runner did not execute the checkpoint listing.")
    bad_command = run_dashboard_command(project_name, "rm -rf /")
    if bad_command["ok"] or bad_command["returncode"] == 0:
        raise RuntimeError("safe dashboard command runner accepted an unknown command id.")
    for heavy_command in ("smoke_test", "verify_harness"):
        heavy_result = run_dashboard_command(project_name, heavy_command)
        if heavy_result["ok"] or heavy_result["returncode"] == 0:
            raise RuntimeError(f"safe dashboard command runner accepted heavy harness command: {heavy_command}")


def main() -> int:
    args = parse_args()
    root = repo_root()
    project_name = f"ci_smoke_{__import__('os').getpid()}"
    import_project_name = f"ci_import_{__import__('os').getpid()}"
    template = root / "projects" / "template"
    destination = root / "projects" / project_name
    import_destination = root / "projects" / import_project_name
    import_source = root / "tmp" / f"{import_project_name}_source"
    workspace_profile_path = root / "config" / "workspace_profile.local.json"
    original_workspace_profile = (
        workspace_profile_path.read_text(encoding="utf-8")
        if workspace_profile_path.is_file()
        else None
    )

    def restore_workspace_profile() -> None:
        if original_workspace_profile is None:
            if workspace_profile_path.exists():
                workspace_profile_path.unlink()
            return
        workspace_profile_path.write_text(original_workspace_profile, encoding="utf-8")

    if destination.exists():
        remove_smoke_tree(destination)
    if import_destination.exists():
        remove_smoke_tree(import_destination)
    if import_source.exists():
        remove_smoke_tree(import_source)

    try:
        run_publishable_check_smoke(root)
        if args.include_dashboard:
            run_dashboard_js_behavior_smoke(root)
            run_dashboard_server_asset_smoke()
        import_source = create_import_source_repo(root, f"{import_project_name}_source")
        import_plan = json.loads(run([
            *python_module_command("import_research_repo.py"),
            "--source",
            str(import_source),
            "--project",
            import_project_name,
            "--dry-run",
        ]).stdout)
        if not import_plan.get("dry_run") or import_plan.get("copied_file_count") != 4:
            raise RuntimeError(f"research repo import dry-run failed: {import_plan}")
        run([
            *python_module_command("import_research_repo.py"),
            "--source",
            str(import_source),
            "--project",
            f"{import_project_name}_bad_import_dir",
            "--import-dir",
            "state",
            "--dry-run",
        ], expect_ok=False)
        import_result = json.loads(run([
            *python_module_command("import_research_repo.py"),
            "--source",
            str(import_source),
            "--project",
            import_project_name,
        ]).stdout)
        if (
            not import_result.get("ok")
            or import_result.get("project") != import_project_name
            or "README.md" not in import_result.get("entrypoints", [])
            or "train.py" not in import_result.get("entrypoints", [])
        ):
            raise RuntimeError(f"research repo import failed: {import_result}")
        for relative in [
            "04_code/imported_repo/README.md",
            "04_code/imported_repo/train.py",
            "04_code/imported_repo/src/model.py",
            "04_code/imported_repo/IMPORT_MANIFEST.json",
            "02_planning/imported_repo_inventory.md",
            "00_brief/imported_repo_notes.md",
        ]:
            if not (import_destination / relative).exists():
                raise RuntimeError(f"research repo import missing expected file: {relative}")
        for relative in [
            "04_code/imported_repo/.env",
            "04_code/imported_repo/.git",
            "04_code/imported_repo/checkpoints/model.pt",
        ]:
            if (import_destination / relative).exists():
                raise RuntimeError(f"research repo import copied an excluded file: {relative}")
        import_manifest = json.loads((import_destination / "04_code/imported_repo/IMPORT_MANIFEST.json").read_text(encoding="utf-8"))
        if import_manifest.get("source_path"):
            raise RuntimeError("research repo import recorded an absolute source path without opt-in.")
        import_queue = json.loads((import_destination / "state" / "command_queue.json").read_text(encoding="utf-8"))
        if not any(command.get("id") == "imported_repo_triage" for command in import_queue.get("commands", [])):
            raise RuntimeError("research repo import did not add the triage command.")
        import_next_actions = (import_destination / "state" / "next_actions.md").read_text(encoding="utf-8")
        if "imported_repo_triage" not in import_next_actions or "BEGIN GENERATED COMMAND QUEUE MIRROR" not in import_next_actions:
            raise RuntimeError("research repo import did not sync the generated next_actions mirror.")
        import_handoff = (import_destination / "HANDOFF.md").read_text(encoding="utf-8")
        import_current_state = (import_destination / "state" / "current_state.md").read_text(encoding="utf-8")
        if "Latest Import" not in import_handoff or "Imported Repository Snapshot" not in import_current_state:
            raise RuntimeError("research repo import did not persist import context in handoff state.")
        import_status = json.loads((import_destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        director_status = next(
            agent for agent in import_status.get("agents", [])
            if agent.get("name") == "director"
        )
        if (
            director_status.get("stage") != "import_research_repo"
            or "04_code/imported_repo/" not in director_status.get("last_output_files", [])
            or "02_planning/imported_repo_inventory.md" not in director_status.get("last_output_files", [])
        ):
            raise RuntimeError("research repo import did not sync the import lifecycle status.")
        if "import_research_repo" not in (import_destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("research repo import did not append a lifecycle event.")
        run([*python_module_command("validate_project.py"), "--project", import_project_name, "--strict"])
        shutil.copytree(template, destination)
        replace_project_name(destination, project_name)
        sanitize_copied_template_state(destination)
        run([*python_module_command("ralph_loop.py"), "reset", "--project", project_name, "--delete-prompts"])
        run([*python_module_command("report_index.py"), "refresh", "--project", project_name])
        run([*python_module_command("state_doctor.py"), "--project", project_name, "--dry-run-enqueue", "--json"])
        progress_hooks_probe = destination / "state" / "progress_hooks.jsonl"
        if progress_hooks_probe.exists():
            progress_hooks_probe.unlink()
        run([*python_module_command("state_doctor.py"), "--project", project_name, "--dry-run-repair", "--json"])
        if progress_hooks_probe.exists():
            raise RuntimeError("state doctor dry-run repair wrote a planned repair file.")
        progress_hooks_probe.write_text("", encoding="utf-8")
        run([*python_module_command("project_health.py"), "--project", project_name, "--dry-run-enqueue", "--json"])
        run([*python_module_command("brief_intake.py"), "draft", "--project", project_name])
        run([*python_module_command("experiment_planner.py"), "--project", project_name, "--json"])
        run([*python_module_command("claim_graph.py"), "--project", project_name, "--json"])
        run([*python_module_command("baseline_compare.py"), "--project", project_name, "--json"])
        run([*python_module_command("agent_quality_audit.py"), "--project", project_name, "--json"])
        run([*python_module_command("source_credibility_audit.py"), "--project", project_name, "--write-report"])
        run([*python_module_command("experiment_diagnosis.py"), "--project", project_name, "--write-report"])
        early_events = (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8")
        for expected_event in ("source_credibility_audit", "experiment_diagnosis"):
            if expected_event not in early_events:
                raise RuntimeError(f"{expected_event} did not append a lifecycle event.")
        run([*python_module_command("resource_ledger.py"), "init", "--project", project_name])
        run([
            *python_module_command("resource_ledger.py"),
            "record",
            "--project",
            project_name,
            "--id",
            "smoke_tokens",
            "--kind",
            "tokens",
            "--amount",
            "128",
            "--unit",
            "token",
            "--note",
            "Smoke resource accounting entry.",
        ])
        run([*python_module_command("resource_ledger.py"), "summary", "--project", project_name, "--write-report"])
        resource_events = (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8")
        if "resource_ledger_record" not in resource_events:
            raise RuntimeError("resource_ledger.py record did not append a lifecycle event.")
        if "resource_ledger_summary" not in resource_events:
            raise RuntimeError("resource_ledger.py summary did not append a lifecycle event.")
        run([*python_module_command("phase_gate.py"), "init", "--project", project_name])
        run([
            *python_module_command("phase_gate.py"),
            "set",
            "--project",
            project_name,
            "--phase",
            "report",
            "--status",
            "done",
            "--evidence",
            "09_report/README.md",
            "--note",
            "Smoke report gate evidence exists.",
        ])
        run([*python_module_command("phase_gate.py"), "audit", "--project", project_name, "--write-report"])
        phase_events = (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8")
        for expected_event in ("phase_gate_set", "phase_gate_audit"):
            if expected_event not in phase_events:
                raise RuntimeError(f"{expected_event} did not append a lifecycle event.")
        run([
            *python_module_command("run_checkpoint.py"),
            "create",
            "--project",
            project_name,
            "--id",
            "smoke_checkpoint",
            "--label",
            "Smoke checkpoint",
            "--note",
            "Checkpoint before smoke validation.",
        ])
        checkpoint_listing = json.loads(run([
            *python_module_command("run_checkpoint.py"),
            "list",
            "--project",
            project_name,
            "--json",
        ]).stdout)
        if not checkpoint_listing.get("checkpoints"):
            raise RuntimeError("run_checkpoint.py did not list the smoke checkpoint.")
        run([*python_module_command("run_checkpoint.py"), "audit", "--project", project_name])
        checkpoint_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        checkpoint_director_status = next(
            agent for agent in checkpoint_status.get("agents", [])
            if agent.get("name") == "director"
        )
        if (
            checkpoint_director_status.get("stage") != "run_checkpoint"
            or "state/checkpoints/smoke_checkpoint.json" not in checkpoint_director_status.get("last_output_files", [])
        ):
            raise RuntimeError("run_checkpoint.py did not sync the checkpoint lifecycle status.")
        if "run_checkpoint" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("run_checkpoint.py did not append a lifecycle event.")

        (destination / "06_writing" / "terminology.md").write_text(
            "\n".join([
                "# Terminology",
                "",
                "| term | canonical meaning | preferred usage | avoid | notes |",
                "| --- | --- | --- | --- | --- |",
                "| smoke fixture | Synthetic harness project used to verify workspace workflows. | smoke fixture | production dataset | Used only by release smoke tests. |",
                "| smoke checkpoint | File-state checkpoint created during smoke validation. | smoke checkpoint | final experiment result | Confirms checkpoint lifecycle wiring. |",
                "",
            ]),
            encoding="utf-8",
        )

        run([*python_module_command("validate_project.py"), "--project", project_name, "--strict"])
        run([
            *python_module_command("agent_dashboard.py"),
            "--project",
            project_name,
            "--host",
            "0.0.0.0",
            "--port",
            "0",
        ], expect_ok=False)
        run([*python_module_command("agent_events.py"), "validate", "--project", project_name])
        run([
            *python_module_command("agent_events.py"),
            "record",
            "--project",
            project_name,
            "--agent",
            "director",
            "--event",
            "activity",
            "--status",
            "finished",
            "--task",
            "Attempt to record a non-standard lifecycle status.",
        ], expect_ok=False)
        hook_task = "Smoke hook reports file-state-visible activity."
        run([
            *python_module_command("agent_events.py"),
            "record",
            "--project",
            project_name,
            "--agent",
            "director",
            "--event",
            "activity",
            "--status",
            "running",
            "--task",
            hook_task,
            "--stage",
            "planning",
            "--note",
            "Hook activity should refresh the live dashboard state.",
            "--sync-status",
        ])
        hook_events = json.loads(run([
            *python_module_command("agent_events.py"),
            "list",
            "--project",
            project_name,
            "--limit",
            "1",
            "--json",
        ]).stdout)
        latest_hook_event = hook_events["events"][0]
        if latest_hook_event.get("event") != "activity" or latest_hook_event.get("task") != hook_task:
            raise RuntimeError("agent_events.py record did not append the expected activity event.")
        status_doc = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        director = next(agent for agent in status_doc["agents"] if agent["name"] == "director")
        if director.get("status") != "running" or director.get("current_task") != hook_task:
            raise RuntimeError("agent_events.py record --sync-status did not refresh director status.")
        run([
            *python_module_command("research_registry.py"),
            "add-dataset",
            "--project",
            project_name,
            "--id",
            "fixture_workflow",
            "--name",
            "Fixture Workflow Dataset",
            "--status",
            "prepared",
            "--source",
            "fixture://workflow",
            "--split",
            "smoke",
            "--preprocessing",
            "Smoke fixture generated by release smoke test.",
            "--used-by-exp",
            "exp_001",
        ])
        progress_summary = "Smoke progress checkpoint records a mid-pass experiment observation."
        run([
            *python_module_command("progress_checkpoint.py"),
            "record",
            "--project",
            project_name,
            "--agent",
            "director",
            "--kind",
            "experiment_result",
            "--exp-id",
            "exp_001",
            "--summary",
            progress_summary,
            "--evidence",
            "03_experiments/exp_001/run_log.md",
            "--output",
            "03_experiments/exp_001/results/",
            "--rationale",
            "Exercise automatic experiment journal persistence.",
            "--dataset",
            "fixture_workflow",
            "--method",
            "smoke_method",
            "--baseline-id",
            "smoke_baseline",
            "--result-analysis",
            "Smoke result moved because the fixture checkpoint was recorded.",
            "--memory",
            "Smoke checkpoints preserve mid-pass experiment observations.",
            "--next-action",
            "Inspect the smoke checkpoint record.",
            "--open-question",
            "Does the smoke checkpoint expose enough evidence for handoff?",
            "--run-status",
            "succeeded",
            "--result-path",
            "03_experiments/exp_001/results/",
        ])
        run([*python_module_command("progress_checkpoint.py"), "validate", "--project", project_name])
        progress_listing = json.loads(run([
            *python_module_command("progress_checkpoint.py"),
            "list",
            "--project",
            project_name,
            "--limit",
            "1",
            "--json",
        ]).stdout)
        latest_progress = progress_listing["records"][0]
        if latest_progress.get("summary") != progress_summary or latest_progress.get("exp_id") != "exp_001":
            raise RuntimeError("progress_checkpoint.py did not list the expected checkpoint.")
        if progress_summary not in (destination / "state" / "sessions" / "progress_log.md").read_text(encoding="utf-8"):
            raise RuntimeError("progress_checkpoint.py did not append the shared progress log.")
        if progress_summary not in (destination / "03_experiments" / "exp_001" / "run_log.md").read_text(encoding="utf-8"):
            raise RuntimeError("progress_checkpoint.py did not append the experiment run log.")
        journal_text = (destination / "05_results" / "experiment_journal.md").read_text(encoding="utf-8")
        if progress_summary not in journal_text or "Smoke result moved because the fixture checkpoint was recorded." not in journal_text:
            raise RuntimeError("progress_checkpoint.py did not append the experiment journal.")
        journal_csv_text = (destination / "05_results" / "experiment_journal.csv").read_text(encoding="utf-8")
        if progress_summary not in journal_csv_text or "Smoke result moved because the fixture checkpoint was recorded." not in journal_csv_text:
            raise RuntimeError("progress_checkpoint.py did not append the experiment journal CSV.")
        progress_analysis_text = (destination / "03_experiments" / "exp_001" / "analysis.md").read_text(encoding="utf-8")
        if progress_summary not in progress_analysis_text or "Smoke result moved because the fixture checkpoint was recorded." not in progress_analysis_text:
            raise RuntimeError("progress_checkpoint.py did not append the experiment analysis note.")
        run([
            *python_module_command("progress_checkpoint.py"),
            "limit-handoff",
            "--project",
            project_name,
            "--agent",
            "director",
            "--summary",
            "This should not write because reported limits are above threshold.",
            "--five-hour-remaining-pct",
            "20",
            "--weekly-remaining-pct",
            "20",
        ])
        if (destination / "state" / "limit_handoff.md").exists():
            raise RuntimeError("progress_checkpoint.py wrote a limit handoff above threshold.")
        high_status_command = json.dumps([
            sys.executable,
            "-c",
            "import json; print(json.dumps({'limits': {'five_hour': {'remaining_pct': 20}, 'weekly': {'remaining_pct': 20}}}))",
        ])
        run([
            *python_module_command("progress_checkpoint.py"),
            "check-limits",
            "--project",
            project_name,
            "--agent",
            "director",
            "--summary",
            "This should not write because queried limits are above threshold.",
            "--status-command-json",
            high_status_command,
        ])
        if (destination / "state" / "limit_handoff.md").exists():
            raise RuntimeError("progress_checkpoint.py check-limits wrote a limit handoff above threshold.")
        low_status_command = json.dumps([
            sys.executable,
            "-c",
            "import json; print(json.dumps({'limits': {'five_hour': {'remaining_pct': 4}, 'weekly': {'remaining_pct': 50}}}))",
        ])
        checked_limit_summary = "Smoke check-limits queries local status and preserves a handoff."
        run([
            *python_module_command("progress_checkpoint.py"),
            "check-limits",
            "--project",
            project_name,
            "--agent",
            "director",
            "--summary",
            checked_limit_summary,
            "--status-command-json",
            low_status_command,
            "--next-action",
            "Resume from the checked limit handoff.",
        ])
        if checked_limit_summary not in (destination / "state" / "limit_handoff.md").read_text(encoding="utf-8"):
            raise RuntimeError("progress_checkpoint.py check-limits did not write the expected handoff.")
        limit_summary = "Smoke limit handoff preserves current session progress before quota exhaustion."
        run([
            *python_module_command("progress_checkpoint.py"),
            "limit-handoff",
            "--project",
            project_name,
            "--agent",
            "director",
            "--summary",
            limit_summary,
            "--five-hour-remaining-pct",
            "4.5",
            "--weekly-remaining-pct",
            "50",
            "--in-progress",
            "Smoke test is validating limit-aware handoff persistence.",
            "--next-action",
            "Resume from state/limit_handoff.md.",
            "--memory",
            "Limit handoffs must preserve continuation prompts before quota exhaustion.",
        ])
        limit_handoff_text = (destination / "state" / "limit_handoff.md").read_text(encoding="utf-8")
        if "Continue project" not in limit_handoff_text or limit_summary not in limit_handoff_text:
            raise RuntimeError("progress_checkpoint.py did not write the expected limit handoff prompt.")
        if "Limit handoffs must preserve continuation prompts" not in (destination / "state" / "agent_memory.md").read_text(encoding="utf-8"):
            raise RuntimeError("progress_checkpoint.py did not append limit handoff memory.")
        run([
            *python_module_command("progress_checkpoint.py"),
            "record",
            "--project",
            project_name,
            "--agent",
            "director",
            "--kind",
            "result",
            "--summary",
            "Attempt to finish progress without linking the owned command.",
            "--status",
            "done",
        ], expect_ok=False)
        run([
            *python_module_command("agent_events.py"),
            "record",
            "--project",
            project_name,
            "--agent",
            "director",
            "--event",
            "finish",
            "--status",
            "done",
            "--task",
            "Attempt to finish without linking the owned command.",
            "--sync-status",
        ], expect_ok=False)
        finish_task = "Smoke hook finishes a command-linked activity."
        run([
            *python_module_command("agent_events.py"),
            "record",
            "--project",
            project_name,
            "--agent",
            "director",
            "--event",
            "finish",
            "--status",
            "done",
            "--command-id",
            "cmd_002",
            "--task",
            finish_task,
            "--stage",
            "planning",
            "--note",
            "Hook completion should update the owned command and agent status together.",
            "--sync-status",
        ])
        status_doc = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        director = next(agent for agent in status_doc["agents"] if agent["name"] == "director")
        if director.get("status") != "done" or director.get("current_task") != finish_task:
            raise RuntimeError("agent_events.py record --sync-status --status done did not finish director status.")
        queue_doc = json.loads((destination / "state" / "command_queue.json").read_text(encoding="utf-8"))
        command = next(item for item in queue_doc["commands"] if item["id"] == "cmd_002")
        if command.get("status") != "done":
            raise RuntimeError("agent_events.py record --command-id did not finish the owned command.")
        run([*python_module_command("agent_events.py"), "validate", "--project", project_name])
        run([*python_module_command("pattern_memory.py"), "validate", "--project", project_name])
        run([
            *python_module_command("pattern_memory.py"),
            "add",
            "--project",
            project_name,
            "--id",
            "smoke_pattern",
            "--title",
            "Smoke pattern",
            "--summary",
            "Record a reusable harness lesson from the smoke test.",
            "--tag",
            "smoke",
            "--trigger",
            "When validating project-local memory.",
            "--recommendation",
            "Use pattern_memory.py instead of hand-editing the JSON state.",
            "--evidence",
            "state/pattern_memory.json",
        ])
        if "pattern_memory_add" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("pattern_memory.py add did not append a lifecycle event.")
        run([*python_module_command("pattern_memory.py"), "search", "--project", project_name, "--query", "smoke memory"])
        run([*python_module_command("pattern_memory.py"), "list", "--project", project_name])
        run([*python_module_command("ralph_loop.py"), "validate", "--project", project_name])
        run([
            *python_module_command("ralph_loop.py"),
            "run",
            "--project",
            project_name,
            "--id",
            "smoke_ralph",
            "--goal",
            "Smoke-test a bounded Ralph loop that stops on a completion promise.",
            "--command-id",
            "cmd_001",
            "--duration-minutes",
            "0.1",
            "--max-iterations",
            "2",
            "--completion-promise",
            "RALPH_COMPLETE",
            "--execute",
            "--runner-command",
            f"{sys.executable} -c \"print('<promise>RALPH_COMPLETE</promise>')\"",
        ])
        run([*python_module_command("ralph_loop.py"), "status", "--project", project_name, "--id", "smoke_ralph"])
        run([*python_module_command("ralph_loop.py"), "validate", "--project", project_name])
        run([
            *python_module_command("ralph_loop.py"),
            "run",
            "--project",
            project_name,
            "--id",
            "smoke_ralph_resume",
            "--goal",
            "Smoke-test that an interrupted manual Ralph loop can resume by id.",
            "--duration-minutes",
            "1",
            "--result-file",
            "state/smoke_ralph_resume_done.txt",
        ])
        resumed = run([
            *python_module_command("ralph_loop.py"),
            "run",
            "--project",
            project_name,
            "--id",
            "smoke_ralph_resume",
            "--goal",
            "Smoke-test that an interrupted manual Ralph loop can resume by id.",
            "--duration-minutes",
            "1",
            "--result-file",
            "state/smoke_ralph_resume_done.txt",
            "--execute",
            "--runner-command",
            f"{sys.executable} -c \"from pathlib import Path; Path('projects/{project_name}/state/smoke_ralph_resume_done.txt').write_text('done')\"",
        ])
        if "complete" not in resumed.stdout:
            raise RuntimeError("Ralph loop did not resume and complete an existing active run.")
        run([*python_module_command("ralph_loop.py"), "validate", "--project", project_name])
        run([
            *python_module_command("ralph_loop.py"),
            "run",
            "--project",
            project_name,
            "--id",
            "smoke_ralph_stale",
            "--goal",
            "Smoke-test stale active Ralph run settlement.",
            "--duration-minutes",
            "1",
            "--result-file",
            "state/smoke_ralph_stale_done.txt",
        ])
        ralph_path = destination / "state" / "ralph_loop.json"
        ralph_doc = json.loads(ralph_path.read_text(encoding="utf-8"))
        stale_run = next(run_doc for run_doc in ralph_doc["runs"] if run_doc["id"] == "smoke_ralph_stale")
        stale_run["deadline_at"] = "2000-01-01T00:00:00+00:00"
        ralph_path.write_text(json.dumps(ralph_doc, indent=2) + "\n", encoding="utf-8")
        after_stale = run([
            *python_module_command("ralph_loop.py"),
            "run",
            "--project",
            project_name,
            "--id",
            "smoke_ralph_after_stale",
            "--goal",
            "Smoke-test a new Ralph run after stale active timeout settlement.",
            "--duration-minutes",
            "0.1",
            "--max-iterations",
            "1",
            "--completion-promise",
            "STALE_SETTLED",
            "--execute",
            "--runner-command",
            f"{sys.executable} -c \"print('<promise>STALE_SETTLED</promise>')\"",
        ])
        if "complete" not in after_stale.stdout:
            raise RuntimeError("Ralph loop did not settle a stale active run before starting a new run.")
        ralph_doc = json.loads(ralph_path.read_text(encoding="utf-8"))
        stale_run = next(run_doc for run_doc in ralph_doc["runs"] if run_doc["id"] == "smoke_ralph_stale")
        if stale_run.get("status") != "timeout":
            raise RuntimeError("Stale active Ralph run was not finalized as timeout.")
        run([*python_module_command("ralph_loop.py"), "validate", "--project", project_name])
        fake_codex_bin = destination / "state" / "fake_codex_bin"
        fake_codex_bin.mkdir(parents=True)
        fake_codex = fake_codex_bin / "codex"
        fake_codex.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "prompt = sys.stdin.read()\n"
            "if 'Ralph Loop Iteration' not in prompt or 'CODEX_RALPH_COMPLETE' not in prompt:\n"
            "    raise SystemExit('Codex runner did not receive the Ralph prompt on stdin')\n"
            "print('<promise>CODEX_RALPH_COMPLETE</promise>')\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        fake_codex_executable = fake_codex
        if os.name == "nt":
            # Windows ignores extensionless shebang scripts when resolving PATH.
            # Use an explicit shim so an installed real CLI can never be chosen.
            fake_codex_executable = fake_codex_bin / "codex.cmd"
            fake_codex_executable.write_text(
                f'@echo off\n"{sys.executable}" "{fake_codex}" %*\n', encoding="utf-8",
            )
        codex_env = {
            **os.environ,
            "PATH": f"{fake_codex_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        }
        codex_runner = run([
            *python_module_command("ralph_loop.py"),
            "run",
            "--project",
            project_name,
            "--id",
            "smoke_ralph_codex",
            "--goal",
            "Smoke-test that Ralph can invoke Codex CLI with the prompt on stdin.",
            "--duration-minutes",
            "0.1",
            "--max-iterations",
            "1",
            "--completion-promise",
            "CODEX_RALPH_COMPLETE",
            "--codex-runner",
            "--codex-bin",
            str(fake_codex_executable),
        ], env=codex_env)
        if "complete" not in codex_runner.stdout:
            raise RuntimeError("Ralph Codex runner mode did not complete from the fake Codex promise.")
        run([*python_module_command("ralph_loop.py"), "validate", "--project", project_name])
        run([*python_module_command("ralph_loop.py"), "reset", "--project", project_name, "--delete-prompts"])
        reset_state = json.loads((destination / "state" / "ralph_loop.json").read_text(encoding="utf-8"))
        if reset_state.get("runs"):
            raise RuntimeError("ralph_loop.py reset did not clear stored runs.")
        if list((destination / "state" / "ralph_prompts").glob("*.md")):
            raise RuntimeError("ralph_loop.py reset --delete-prompts left generated prompt files.")
        run([*python_module_command("ralph_loop.py"), "validate", "--project", project_name])
        run([
            *python_module_command("session_state.py"),
            "start",
            "--project",
            project_name,
            "--id",
            "smoke_session",
            "--loop-id",
            "smoke_loop",
            "--goal",
            "Smoke-test isolated session workspace handling.",
            "--command-id",
            "cmd_001",
            "--note",
            "Session workspace smoke test.",
        ])
        run([
            *python_module_command("session_state.py"),
            "update",
            "--project",
            project_name,
            "--id",
            "smoke_session",
            "--command-id",
            "cmd_002",
            "--note",
            "Session workspace accepted a second command link.",
        ])
        run([*python_module_command("session_state.py"), "list", "--project", project_name])
        run([
            *python_module_command("session_state.py"),
            "finish",
            "--project",
            project_name,
            "--id",
            "smoke_session",
            "--status",
            "done",
            "--note",
            "Session workspace smoke test completed.",
        ])
        run([*python_module_command("session_state.py"), "validate", "--project", project_name])
        run([*python_module_command("session_state.py"), "prune", "--project", project_name, "--id", "smoke_session"])
        if (destination / "state" / "sessions" / "smoke_session").exists():
            raise RuntimeError("session_state.py prune did not delete the session directory.")
        session_event_log = (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8")
        for event_type in (
            "session_state_start",
            "session_state_update",
            "session_state_finish",
            "session_state_prune",
        ):
            if event_type not in session_event_log:
                raise RuntimeError(f"session_state.py did not append {event_type}.")
        run([*python_module_command("session_state.py"), "validate", "--project", project_name])
        run([
            *python_module_command("command_queue.py"),
            "add",
            "--project",
            project_name,
            "--id",
            "cmd_vote_smoke",
            "--action",
            "Smoke-test an approved multi-agent vote gate.",
            "--owner",
            "director",
            "--priority",
            "high",
            "--requires-vote",
            "--vote-id",
            "vote_smoke",
            "--risk-level",
            "high",
            "--display-summary",
            "Verify that important commands cannot dispatch until a vote approves them.",
            "--why-now",
            "High-risk workflow changes should be gated by independent agent judgement.",
            "--done-when",
            "Dispatch fails before approval and succeeds after the vote reaches its approval threshold.",
        ])
        run([
            *python_module_command("agent_vote.py"),
            "open",
            "--project",
            project_name,
            "--id",
            "vote_smoke",
            "--title",
            "Approve smoke vote gated command",
            "--rationale",
            "Exercise the high-risk command voting gate.",
            "--risk-level",
            "high",
            "--command-id",
            "cmd_vote_smoke",
            "--required-voter",
            "director",
            "--required-voter",
            "critic",
            "--min-approvals",
            "2",
        ])
        run([
            *python_module_command("agent_orchestrator.py"),
            "dispatch",
            "--project",
            project_name,
            "--id",
            "cmd_vote_smoke",
        ], expect_ok=False)
        run([
            *python_module_command("agent_vote.py"),
            "vote",
            "--project",
            project_name,
            "--id",
            "vote_smoke",
            "--agent",
            "director",
            "--vote",
            "approve",
            "--confidence",
            "high",
            "--rationale",
            "The smoke command is bounded and verified.",
        ])
        run([
            *python_module_command("agent_vote.py"),
            "vote",
            "--project",
            project_name,
            "--id",
            "vote_smoke",
            "--agent",
            "critic",
            "--vote",
            "approve",
            "--confidence",
            "medium",
            "--rationale",
            "The vote gate has a clear rollback path.",
        ])
        vote_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        critic_vote_status = next(
            agent for agent in vote_status.get("agents", [])
            if agent.get("name") == "critic"
        )
        if (
            critic_vote_status.get("stage") != "agent_vote_cast"
            or "state/agent_votes.json" not in critic_vote_status.get("last_output_files", [])
        ):
            raise RuntimeError("agent_vote.py did not sync the vote lifecycle status.")
        vote_events_text = (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8")
        for expected_event in ("agent_vote_open", "agent_vote_cast"):
            if expected_event not in vote_events_text:
                raise RuntimeError(f"agent_vote.py did not append lifecycle event: {expected_event}")
        run([*python_module_command("agent_vote.py"), "status", "--project", project_name, "--id", "vote_smoke"])
        run([
            *python_module_command("agent_orchestrator.py"),
            "dispatch",
            "--project",
            project_name,
            "--id",
            "cmd_vote_smoke",
        ])
        run([
            *python_module_command("agent_orchestrator.py"),
            "finish",
            "--project",
            project_name,
            "--id",
            "cmd_vote_smoke",
            "--status",
            "done",
            "--note",
            "Vote-gated command dispatch smoke test completed.",
            "--output",
            "state/agent_votes.json",
        ])
        for command_id, owner, output_path in (
            ("cmd_parallel_lit", "literature_reviewer", "01_literature/related_work_matrix.md"),
            ("cmd_parallel_critic", "critic", "07_reviews/critic_comments.md"),
        ):
            run([
                *python_module_command("command_queue.py"),
                "add",
                "--project",
                project_name,
                "--id",
                command_id,
                "--action",
                f"Parallel smoke task for {owner}.",
                "--owner",
                owner,
                "--priority",
                "medium",
                "--output",
                output_path,
                "--parallel-group",
                "parallel_smoke",
                "--display-summary",
                f"Verify parallel dispatch can route {owner}.",
                "--why-now",
                "Independent agent work should be batchable.",
                "--done-when",
                "A prompt is written and the command is marked in progress.",
            ])
        parallel_plan = json.loads(run([
            *python_module_command("agent_orchestrator.py"),
            "parallel",
            "--project",
            project_name,
            "--group",
            "parallel_smoke",
            "--max-agents",
            "2",
            "--json",
        ]).stdout)
        if len(parallel_plan.get("commands", [])) != 2:
            raise RuntimeError(f"agent_orchestrator.py parallel did not plan two independent commands: {parallel_plan}")
        if "open_parallel_diagnostics" not in parallel_plan:
            raise RuntimeError("agent_orchestrator.py parallel JSON did not expose open parallel diagnostics.")
        run([
            *python_module_command("agent_orchestrator.py"),
            "parallel",
            "--project",
            project_name,
            "--group",
            "parallel_smoke",
            "--max-agents",
            "2",
            "--write",
        ])
        queue_after_parallel = json.loads((destination / "state" / "command_queue.json").read_text(encoding="utf-8"))
        parallel_commands = {
            command.get("id"): command
            for command in queue_after_parallel.get("commands", [])
            if command.get("id") in {"cmd_parallel_lit", "cmd_parallel_critic"}
        }
        if any(command.get("status") != "in progress" for command in parallel_commands.values()):
            raise RuntimeError("agent_orchestrator.py parallel did not mark selected commands in progress.")
        for command_id in ("cmd_parallel_lit", "cmd_parallel_critic"):
            if not (destination / "state" / "orchestrator_prompts" / f"{command_id}.md").is_file():
                raise RuntimeError(f"agent_orchestrator.py parallel did not write prompt for {command_id}.")
        if "parallel_dispatch_plan" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("agent_orchestrator.py parallel did not append a parallel dispatch event.")
        run([
            *python_module_command("agent_orchestrator.py"),
            "finish-parallel",
            "--project",
            project_name,
            "--group",
            "parallel_smoke",
            "--status",
            "done",
            "--note",
            "Parallel smoke prompts were written and verified.",
        ])
        run([
            *python_module_command("command_queue.py"),
            "add",
            "--project",
            project_name,
            "--id",
            "cmd_auto_vote_smoke",
            "--action",
            "Smoke-test automatic vote execution before dispatch.",
            "--owner",
            "director",
            "--priority",
            "high",
            "--requires-vote",
            "--vote-id",
            "vote_auto_smoke",
            "--risk-level",
            "high",
            "--display-summary",
            "Verify that orchestrator auto-vote can approve and dispatch a gated command.",
            "--why-now",
            "The vote gate should support automatic independent voter prompts.",
            "--done-when",
            "The auto vote reaches approval and the command dispatches.",
        ])
        run([
            *python_module_command("agent_orchestrator.py"),
            "dispatch",
            "--project",
            project_name,
            "--id",
            "cmd_auto_vote_smoke",
            "--auto-vote",
            "--vote-voter",
            "director",
            "--vote-voter",
            "critic",
            "--vote-runner-command",
            f"{sys.executable} -c \"print('<vote>approve</vote><confidence>high</confidence><rationale>Smoke auto vote approves the bounded command.</rationale>')\"",
        ])
        if "agent_vote_auto" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("agent_orchestrator.py --auto-vote did not append an auto-vote lifecycle event.")
        run([
            *python_module_command("agent_orchestrator.py"),
            "finish",
            "--project",
            project_name,
            "--id",
            "cmd_auto_vote_smoke",
            "--status",
            "done",
            "--note",
            "Automatic vote execution smoke test completed.",
            "--output",
            "state/agent_votes.json",
        ])
        run([*python_module_command("agent_vote.py"), "validate", "--project", project_name])
        run([*python_module_command("agent_events.py"), "validate", "--project", project_name])
        run([*python_module_command("agent_events.py"), "summary", "--project", project_name])
        remove_smoke_tree(destination / "09_report")
        (destination / "03_experiments" / "exp_001" / "preregistration.md").unlink()
        (destination / "03_experiments" / "exp_001" / "reproducibility_manifest.json").unlink()
        (destination / "05_results" / "statistical_robustness.md").unlink()
        (destination / "05_results" / "experiment_results.csv").unlink()
        (destination / "05_results" / "experiment_journal.md").unlink()
        (destination / "05_results" / "experiment_journal.csv").unlink()
        (destination / "07_reviews" / "reviewer_attack_matrix.md").unlink()
        (destination / "03_experiments" / "data_roots.md").unlink()
        (destination / "06_writing" / "terminology.md").unlink()
        (destination / "state" / "agent_messages.json").unlink()
        (destination / "state" / "pattern_memory.json").unlink()
        (destination / "state" / "ralph_loop.json").unlink()
        (destination / "HANDOFF.md").unlink()
        (destination / "state" / "current_state.md").unlink()
        (destination / "state" / "agent_memory.md").unlink()
        (destination / "state" / "next_actions.md").unlink()
        (destination / "state" / "open_questions.md").unlink()
        run([*python_module_command("validate_project.py"), "--project", project_name, "--strict"], expect_ok=False)
        queue_path = destination / "state" / "command_queue.json"
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        for command in queue.get("commands", []):
            command.pop("display_summary", None)
            command.pop("why_now", None)
            command.pop("done_when", None)
        queue_path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
        run([*python_module_command("migrate_project.py"), "--project", project_name])
        migration_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        migration_director = next(agent for agent in migration_status["agents"] if agent["name"] == "director")
        if (
            migration_director.get("stage") != "project_migration"
            or "05_results/experiment_journal.md" not in migration_director.get("last_output_files", [])
        ):
            raise RuntimeError("migrate_project.py did not sync migration lifecycle outputs.")
        if "project_migration" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("migrate_project.py did not append a migration lifecycle event.")
        for relative in [
            "state/current_state.md",
            "state/agent_memory.md",
            "state/next_actions.md",
            "state/open_questions.md",
            "03_experiments/data_roots.md",
            "05_results/experiment_results.csv",
            "05_results/experiment_journal.md",
            "05_results/experiment_journal.csv",
            "06_writing/terminology.md",
        ]:
            if not (destination / relative).is_file():
                raise RuntimeError(f"migrate_project did not restore working artifact: {relative}")
        migrated_data_roots = (destination / "03_experiments" / "data_roots.md").read_text(encoding="utf-8")
        if "fixture_workflow" not in migrated_data_roots or "fixture://workflow" not in migrated_data_roots:
            raise RuntimeError(
                "migrate_project.py did not reconstruct data_roots.md from dataset_registry.json."
            )
        run([
            *python_module_command("preregistration_helper.py"),
            "write",
            "--project",
            project_name,
            "--exp-id",
            "exp_001",
            "--claim-id",
            "claim_smoke",
            "--claim",
            "Smoke fixture records a valid result row.",
            "--expectation",
            "The smoke metric is present and interpretable.",
            "--support",
            "A metric row is ingested and linked to smoke evidence.",
            "--falsify",
            "The metric row is missing, invalid, or unsupported.",
            "--success",
            "accuracy is recorded",
            "--failure",
            "accuracy is missing",
            "--metric",
            "accuracy",
            "--dataset",
            "fixture",
            "--split",
            "smoke",
            "--smoke-command",
            "python -c 'print(1)'",
            "--smoke-expected-output",
            "1",
            "--smoke-check-procedure",
            "Confirm stdout is 1.",
            "--analysis",
            "Compare the smoke result against the fixture expectation.",
            "--decision-rule",
            "Use this only as smoke validation evidence.",
        ])
        run([
            *python_module_command("research_registry.py"),
            "add-dataset",
            "--project",
            project_name,
            "--id",
            "fixture_workflow",
            "--name",
            "Fixture Workflow Dataset",
            "--status",
            "prepared",
            "--source",
            "fixture://workflow",
            "--split",
            "smoke",
            "--preprocessing",
            "Smoke fixture generated by release smoke test.",
            "--used-by-exp",
            "exp_001",
        ])
        run([*python_module_command("migrate_project.py"), "--project", project_name, "--dry-run"])
        run([
            *python_module_command("experiment_planner.py"),
            "--project",
            project_name,
            "--experiment-id",
            "exp_001",
            "--claim-id",
            "claim_smoke",
            "--hypothesis",
            "Smoke fixture records a valid result row.",
            "--dataset",
            "fixture",
            "--metric",
            "accuracy",
            "--method",
            "smoke_fixture",
            "--smoke-command",
            "python -c 'print(1)'",
            "--expected-output",
            "03_experiments/exp_001/results/smoke/",
            "--write",
            "--json",
        ])
        run([*python_module_command("state_doctor.py"), "--project", project_name, "--write-report", "--json"])
        run([*python_module_command("project_health.py"), "--project", project_name, "--write", "--json"])
        run([*python_module_command("project_hygiene.py"), "--project", project_name, "--write-report", "--strict", "--json"])
        run([*python_module_command("validate_project.py"), "--project", project_name, "--strict"])
        run([*python_module_command("report_index.py"), "refresh", "--project", project_name, "--dry-run"])
        run([*python_module_command("report_index.py"), "refresh", "--project", project_name])
        report_readme = destination / "09_report" / "README.md"
        report_text = report_readme.read_text(encoding="utf-8")
        if "RESEARCH_AGENT_REPORT_INDEX:START" not in report_text or "## Final Artifact Index" not in report_text:
            raise RuntimeError("report_index did not write the generated final artifact index.")

        run([
            *python_module_command("research_registry.py"),
            "add-dataset",
            "--project",
            project_name,
            "--id",
            "bad_local_path",
            "--name",
            "Bad Local Path",
            "--source",
            "/" + "scratch/private_dataset/root",
        ], expect_ok=False)
        run([
            *python_module_command("research_registry.py"),
            "add-dataset",
            "--project",
            project_name,
            "--id",
            "fixture",
            "--name",
            "Fixture Dataset",
            "--status",
            "validated",
            "--source",
            "fixture://local",
            "--split",
            "smoke",
            "--preprocessing",
            "none",
            "--checksum",
            "fixture-checksum",
        ])
        run([
            *python_module_command("research_registry.py"),
            "add-metric",
            "--project",
            project_name,
            "--id",
            "accuracy",
            "--name",
            "Accuracy",
            "--status",
            "validated",
            "--direction",
            "higher",
            "--definition",
            "Correct predictions divided by examples.",
            "--implementation",
            "projects fixture metric implementation",
        ])
        run([*python_module_command("research_registry.py"), "validate", "--project", project_name])
        data_roots_path = destination / "03_experiments" / "data_roots.md"
        data_roots_text = data_roots_path.read_text(encoding="utf-8")
        if "fixture" not in data_roots_text or "fixture://local" not in data_roots_text:
            raise RuntimeError("research_registry.py did not sync dataset provenance to data_roots.md.")
        status_doc = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        experiment_designer = next(agent for agent in status_doc["agents"] if agent["name"] == "experiment_designer")
        if experiment_designer.get("status") != "waiting" or "metric registry entry accuracy" not in experiment_designer.get("current_task", ""):
            raise RuntimeError("research_registry.py did not sync the experiment_designer lifecycle status.")
        research_registry_events = (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8")
        for event_type in ("research_registry", "research_registry_dataset", "research_registry_metric"):
            if event_type not in research_registry_events:
                raise RuntimeError(f"research_registry.py did not append {event_type}.")

        result_table = destination / "09_report" / "results" / "experiment_results.csv"
        result_header = result_table.read_text(encoding="utf-8")
        result_table.write_text(
            result_header
            + "exp_missing,claim_missing,dataset,test,method,baseline_missing,metric,1.0,0.1,supported,evidence,caveat\n",
            encoding="utf-8",
        )
        run([*python_module_command("validate_project.py"), "--project", project_name, "--strict"], expect_ok=False)
        result_table.write_text(result_header, encoding="utf-8")
        claim_table = destination / "09_report" / "results" / "claim_evidence.csv"
        claim_header = claim_table.read_text(encoding="utf-8")
        robustness_table = destination / "09_report" / "results" / "statistical_robustness.csv"
        robustness_header = robustness_table.read_text(encoding="utf-8")
        claim_table.write_text(
            claim_header
            + "claim_weak,Weak claim,unsupported,evidence,exp_001,,caveat,next\n",
            encoding="utf-8",
        )
        paper_path = destination / "09_report" / "paper" / "main.tex"
        original_paper = paper_path.read_text(encoding="utf-8")
        paper_path.write_text(original_paper + "\n% claim_weak\n", encoding="utf-8")
        run([*python_module_command("validate_project.py"), "--project", project_name, "--strict"], expect_ok=False)
        claim_table.write_text(claim_header, encoding="utf-8")
        paper_path.write_text(original_paper, encoding="utf-8")
        claim_table.write_text(
            claim_header
            + "claim_smoke,Smoke claim,observed,evidence,exp_001,,caveat,next\n",
            encoding="utf-8",
        )
        metrics_json = destination / "03_experiments" / "exp_001" / "metrics.json"
        metrics_json.write_text(json.dumps({"accuracy": 0.9}) + "\n", encoding="utf-8")
        run([
            *python_module_command("result_ingest.py"),
            "ingest",
            "--project",
            project_name,
            "--exp-id",
            "exp_001",
            "--input",
            "03_experiments/exp_001/metrics.json",
            "--claim-id",
            "claim_smoke",
            "--dataset",
            "fixture",
            "--method",
            "smoke_method",
            "--baseline-id",
            "none",
            "--status",
            "observed",
            "--final-export",
        ])
        working_result_text = (destination / "05_results" / "experiment_results.csv").read_text(encoding="utf-8")
        if "accuracy" not in working_result_text or "smoke_method" not in working_result_text:
            raise RuntimeError("result_ingest did not write the working experiment result table.")
        journal_after_ingest = (destination / "05_results" / "experiment_journal.md").read_text(encoding="utf-8")
        if (
            "accuracy=0.9" not in journal_after_ingest
            or "analysis pending; explain why performance improved" not in journal_after_ingest
        ):
            raise RuntimeError("result_ingest did not append the experiment journal through the shared writer.")
        journal_csv_after_ingest = (destination / "05_results" / "experiment_journal.csv").read_text(encoding="utf-8")
        if (
            "accuracy=0.9" not in journal_csv_after_ingest
            or "analysis pending; explain why performance improved" not in journal_csv_after_ingest
        ):
            raise RuntimeError("result_ingest did not append the experiment journal CSV through the shared writer.")
        analysis_after_ingest = (destination / "03_experiments" / "exp_001" / "analysis.md").read_text(encoding="utf-8")
        if (
            "accuracy=0.9" not in analysis_after_ingest
            or "analysis pending; explain why performance improved" not in analysis_after_ingest
        ):
            raise RuntimeError("result_ingest did not append the experiment analysis note through the shared writer.")
        run_state_after_ingest = json.loads((destination / "03_experiments" / "exp_001" / "run_state.json").read_text(encoding="utf-8"))
        if "Analyze why performance improved" not in run_state_after_ingest.get("next_action", ""):
            raise RuntimeError("result_ingest did not preserve an analysis follow-up when analysis is pending.")
        status_doc = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        data_analyst = next(agent for agent in status_doc["agents"] if agent["name"] == "data_analyst")
        if data_analyst.get("status") != "waiting" or "Ingested 1 result rows" not in data_analyst.get("current_task", ""):
            raise RuntimeError("result_ingest did not sync the data_analyst lifecycle status.")
        if "result_ingest" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("result_ingest did not append a lifecycle event.")
        completion_metrics = destination / "03_experiments" / "exp_001" / "results" / "completion_metrics.json"
        completion_metrics.parent.mkdir(parents=True, exist_ok=True)
        completion_metrics.write_text(json.dumps({"completion_accuracy": 0.91}) + "\n", encoding="utf-8")
        run([
            *python_module_command("research_registry.py"),
            "add-dataset",
            "--project",
            project_name,
            "--id",
            "fixture_completion",
            "--name",
            "Fixture Completion Dataset",
            "--status",
            "prepared",
            "--source",
            "fixture://completion",
            "--split",
            "smoke",
            "--preprocessing",
            "Smoke completion fixture generated by release smoke test.",
            "--used-by-exp",
            "exp_001",
        ])
        run([
            *python_module_command("research_registry.py"),
            "add-metric",
            "--project",
            project_name,
            "--id",
            "completion_accuracy",
            "--name",
            "Completion Accuracy",
            "--status",
            "validated",
            "--direction",
            "higher",
            "--definition",
            "Smoke completion accuracy for the completion workflow fixture.",
            "--implementation",
            "experiment_complete smoke fixture",
        ])
        completion_payload = json.loads(run([
            *python_module_command("experiment_complete.py"),
            "--project",
            project_name,
            "--exp-id",
            "exp_001",
            "--status",
            "succeeded",
            "--summary",
            "Completion smoke result improved over the baseline.",
            "--result-analysis",
            "Completion accuracy improved because the smoke method used the fixture evidence path.",
            "--metric",
            "completion_accuracy=0.91",
            "--claim-id",
            "claim_smoke",
            "--dataset",
            "fixture_completion",
            "--method",
            "completion_method",
            "--baseline-id",
            "none",
            "--result-path",
            "03_experiments/exp_001/results/completion_metrics.json",
            "--expected-output",
            "completion metrics",
            "--check-procedure",
            "Inspect completion_metrics.json and the experiment journal.",
            "--next-action",
            "Compare completion_method against baseline variants.",
            "--artifact",
            "completion_metrics:metrics=03_experiments/exp_001/results/completion_metrics.json",
            "--data-root",
            "fixture_completion=fixture://completion",
            "--data-split",
            "smoke",
            "--json",
        ]).stdout)
        if completion_payload.get("status") != "succeeded" or completion_payload.get("exp_id") != "exp_001":
            raise RuntimeError(f"experiment_complete.py returned unexpected JSON: {completion_payload}")
        completion_result_text = (destination / "05_results" / "experiment_results.csv").read_text(encoding="utf-8")
        if "completion_accuracy" not in completion_result_text or "completion_method" not in completion_result_text:
            raise RuntimeError("experiment_complete.py did not append the working result table.")
        completion_journal_text = (destination / "05_results" / "experiment_journal.md").read_text(encoding="utf-8")
        if "Completion accuracy improved because" not in completion_journal_text:
            raise RuntimeError("experiment_complete.py did not append the result analysis to the journal.")
        completion_analysis_text = (destination / "03_experiments" / "exp_001" / "analysis.md").read_text(encoding="utf-8")
        if "Completion accuracy improved because" not in completion_analysis_text:
            raise RuntimeError("experiment_complete.py did not append the experiment analysis note.")
        artifact_registry_text = (destination / "03_experiments" / "artifact_registry.csv").read_text(encoding="utf-8")
        if "completion_metrics" not in artifact_registry_text or "completion_metrics.json" not in artifact_registry_text:
            raise RuntimeError("experiment_complete.py did not register the completion artifact.")
        data_roots_text = (destination / "03_experiments" / "data_roots.md").read_text(encoding="utf-8")
        if "fixture_completion" not in data_roots_text or "fixture://completion" not in data_roots_text:
            raise RuntimeError("experiment_complete.py did not register the completion data root.")
        completion_run_state = json.loads((destination / "03_experiments" / "exp_001" / "run_state.json").read_text(encoding="utf-8"))
        if (
            completion_run_state.get("status") != "succeeded"
            or completion_run_state.get("judgement") != "Completion accuracy improved because the smoke method used the fixture evidence path."
            or completion_run_state.get("next_action") != "Compare completion_method against baseline variants."
        ):
            raise RuntimeError("experiment_complete.py did not sync run_state status, analysis, and next action.")
        if "experiment_complete" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("experiment_complete.py did not append a lifecycle event.")
        robustness_json = destination / "03_experiments" / "exp_001" / "robustness.json"
        robustness_json.write_text(json.dumps({"seed_variance": 0.02}) + "\n", encoding="utf-8")
        run([
            *python_module_command("result_ingest.py"),
            "robustness",
            "--project",
            project_name,
            "--exp-id",
            "exp_001",
            "--input",
            "03_experiments/exp_001/robustness.json",
            "--claim-id",
            "claim_smoke",
            "--next-needed",
            "Inspect whether seed variance is small enough for the claim.",
        ])
        robustness_working_text = (destination / "05_results" / "statistical_robustness.md").read_text(encoding="utf-8")
        if "seed_variance" not in robustness_working_text or "Inspect whether seed variance" not in robustness_working_text:
            raise RuntimeError("result_ingest robustness did not append the working robustness notes.")
        robustness_analysis_text = (destination / "03_experiments" / "exp_001" / "analysis.md").read_text(encoding="utf-8")
        if "Robustness checks" not in robustness_analysis_text or "seed_variance" not in robustness_analysis_text:
            raise RuntimeError("result_ingest robustness did not append the experiment analysis note.")
        if robustness_table.read_text(encoding="utf-8") != robustness_header:
            raise RuntimeError("result_ingest robustness working ingest leaked into the final robustness table.")
        robustness_status_doc = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        robustness_data_analyst = next(agent for agent in robustness_status_doc["agents"] if agent["name"] == "data_analyst")
        if "09_report/results/statistical_robustness.csv" in robustness_data_analyst.get("last_output_files", []):
            raise RuntimeError("result_ingest robustness working ingest leaked a final report output.")
        run([
            *python_module_command("result_ingest.py"),
            "robustness",
            "--project",
            project_name,
            "--exp-id",
            "exp_001",
            "--input",
            "03_experiments/exp_001/robustness.json",
            "--claim-id",
            "claim_smoke",
            "--next-needed",
            "Inspect whether seed variance is small enough for the claim.",
            "--final-export",
        ])
        if "seed_variance" not in robustness_table.read_text(encoding="utf-8"):
            raise RuntimeError("result_ingest robustness final export did not write the final robustness table.")
        final_robustness_status_doc = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        final_robustness_data_analyst = next(agent for agent in final_robustness_status_doc["agents"] if agent["name"] == "data_analyst")
        if "09_report/results/statistical_robustness.csv" not in final_robustness_data_analyst.get("last_output_files", []):
            raise RuntimeError("result_ingest robustness final export did not sync the report-facing output.")
        report_text = report_readme.read_text(encoding="utf-8")
        if "experiment_results.csv](results/experiment_results.csv): 1 data row(s)" not in report_text:
            raise RuntimeError("result_ingest did not refresh the report README table count.")
        if args.include_dashboard:
            run_dashboard_project_smoke(project_name, destination)
        run([*python_module_command("data_metric_audit.py"), "--project", project_name, "--strict", "--write-report"])
        data_metric_report = (destination / "05_results" / "data_metric_audit.md").read_text(encoding="utf-8")
        if "Working journal rows:" not in data_metric_report:
            raise RuntimeError("data_metric_audit.py did not include working journal row coverage.")
        if "Working result rows:" not in data_metric_report:
            raise RuntimeError("data_metric_audit.py did not include working result row coverage.")
        data_metric_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        data_analyst_status = next(
            agent for agent in data_metric_status.get("agents", [])
            if agent.get("name") == "data_analyst"
        )
        if (
            data_analyst_status.get("stage") != "data_metric_audit"
            or "05_results/data_metric_audit.md" not in data_analyst_status.get("last_output_files", [])
        ):
            raise RuntimeError("data_metric_audit.py did not sync the data/metric audit lifecycle status.")
        if "data_metric_audit" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("data_metric_audit.py did not append a lifecycle event.")
        run([*python_module_command("paper_claim_linter.py"), "--project", project_name, "--strict"])
        result_table.write_text(result_header, encoding="utf-8")
        claim_table.write_text(claim_header, encoding="utf-8")
        robustness_table.write_text(robustness_header, encoding="utf-8")
        run([*python_module_command("report_index.py"), "refresh", "--project", project_name])

        run([
            *python_module_command("agent_messages.py"),
            "send",
            "--project",
            project_name,
            "--id",
            "msg_001",
            "--from-agent",
            "director",
            "--to-agent",
            "experiment_designer",
            "--kind",
            "question",
            "--priority",
            "medium",
            "--subject",
            "Confirm exp_001 claim mapping",
            "--body",
            "Please confirm which claim_id exp_001 should test before execution.",
            "--related-exp-id",
            "exp_001",
            "--required-response",
            "Return the claim_id or mark the experiment blocked.",
        ])
        run([
            *python_module_command("agent_messages.py"),
            "respond",
            "--project",
            project_name,
            "--id",
            "msg_001",
            "--from-agent",
            "experiment_designer",
            "--response",
            "No claim_id is set yet; keep exp_001 blocked until contribution_candidates.md is narrowed.",
        ])
        run([
            *python_module_command("agent_messages.py"),
            "list",
            "--project",
            project_name,
            "--agent",
            "experiment_designer",
        ])
        run([
            *python_module_command("agent_messages.py"),
            "send",
            "--project",
            project_name,
            "--id",
            "msg_002",
            "--from-agent",
            "director",
            "--to-agent",
            "code_agent",
            "--kind",
            "blocker",
            "--priority",
            "high",
            "--subject",
            "Block execution until dataset path is known",
            "--body",
            "Do not run exp_001 until the dataset path is recorded in the reproducibility manifest.",
            "--related-exp-id",
            "exp_001",
        ])
        run([*python_module_command("validate_project.py"), "--project", project_name, "--strict"], expect_ok=False)
        run([
            *python_module_command("agent_messages.py"),
            "respond",
            "--project",
            project_name,
            "--id",
            "msg_002",
            "--from-agent",
            "code_agent",
            "--response",
            "Acknowledged; execution remains blocked until the manifest records the dataset path.",
        ])
        message_event_log = (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8")
        for event_type in ("agent_message_send", "agent_message_respond"):
            if event_type not in message_event_log:
                raise RuntimeError(f"agent_messages.py did not append {event_type}.")
        run([*python_module_command("validate_project.py"), "--project", project_name, "--strict"])
        run([
            *python_module_command("progress_checkpoint.py"),
            "record",
            "--project",
            project_name,
            "--agent",
            "director",
            "--kind",
            "observation",
            "--summary",
            "Smoke hooked next action preservation after migration.",
            "--next-action",
            "Inspect the smoke checkpoint record.",
            "--no-current-state",
        ])
        run([
            *python_module_command("command_queue.py"),
            "update",
            "--project",
            project_name,
            "--id",
            "cmd_001",
            "--display-summary",
            "Smoke-test a human-readable command summary.",
            "--why-now",
            "The harness should preserve plain-language next-action context.",
            "--done-when",
            "The command queue stores display_summary, why_now, and done_when.",
        ])
        report_text = report_readme.read_text(encoding="utf-8")
        if "Smoke-test a human-readable command summary." in report_text or ("## Current" + " Work") in report_text:
            raise RuntimeError("command_queue working state leaked into the final report README index.")
        next_actions_text = (destination / "state" / "next_actions.md").read_text(encoding="utf-8")
        if "Smoke-test a human-readable command summary." not in next_actions_text:
            raise RuntimeError("command_queue updates did not sync the human-readable next_actions mirror.")
        if "Inspect the smoke checkpoint record." not in next_actions_text:
            raise RuntimeError("command_queue updates did not preserve hooked next_actions notes.")
        if "command_queue_update" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("command_queue.py update did not append a queue lifecycle event.")
        command_queue_json = run([
            *python_module_command("command_queue.py"),
            "list",
            "--project",
            project_name,
            "--json",
        ])
        command_queue_payload = json.loads(command_queue_json.stdout)
        if not command_queue_payload.get("commands") or "dependency_ready" not in command_queue_payload["commands"][0]:
            raise RuntimeError("command_queue list --json did not expose dependency readiness.")
        if "unfinished_dependencies" not in command_queue_payload["commands"][0]:
            raise RuntimeError("command_queue list --json did not expose unfinished dependencies.")
        queue_path = destination / "state" / "command_queue.json"
        original_queue_text = queue_path.read_text(encoding="utf-8")
        dependency_queue = json.loads(original_queue_text)
        dependency_queue["commands"][0]["depends_on"] = ["missing_command_dependency"]
        queue_path.write_text(json.dumps(dependency_queue, indent=2) + "\n", encoding="utf-8")
        run([*python_module_command("validate_project.py"), "--project", project_name, "--strict"], expect_ok=False)
        queue_path.write_text(original_queue_text, encoding="utf-8")
        run([*python_module_command("agent_orchestrator.py"), "next", "--project", project_name])
        next_json = run([
            *python_module_command("agent_orchestrator.py"),
            "next",
            "--project",
            project_name,
            "--json",
        ])
        next_payload = json.loads(next_json.stdout)
        if "open_parallel_diagnostics" not in next_payload:
            raise RuntimeError("agent_orchestrator.py next --json did not expose open parallel diagnostics.")
        prompt_result = run([
            *python_module_command("agent_orchestrator.py"),
            "prompt",
            "--project",
            project_name,
            "--id",
            "cmd_001",
            "--write",
        ])
        prompt_rel = prompt_result.stdout.strip().splitlines()[-1]
        prompt_text = (destination / prompt_rel).read_text(encoding="utf-8")
        for expected in [
            "Research Routing Matrix",
            "Research Handoff Graph",
            "Research Leader Dispatch Protocol",
            "Research Risk And Confidence Matrix",
            "Research Brain Protocol",
        ]:
            if expected not in prompt_text:
                raise RuntimeError(f"orchestrator prompt did not include shared contract: {expected}")

        dispatch_sample = destination / "state" / "sessions" / "leader_dispatch_smoke.md"
        dispatch_sample.parent.mkdir(parents=True, exist_ok=True)
        dispatch_sample.write_text(
            "=== LEADER DISPATCH ===\n"
            "type: dispatch_workers\n\n"
            "workers:\n"
            "  - name: code_agent\n"
            "    command_id: cmd_leader_smoke\n"
            "    depends_on: none\n"
            "    parallel_group: 1\n"
            "    expected_outputs: 03_experiments/exp_001/run_log.md\n"
            "    prompt: |\n"
            "      Run the smoke command and report evidence paths.\n"
            "  - name: critic\n"
            "    command_id: cmd_leader_smoke_critic\n"
            "    depends_on: none\n"
            "    parallel_group: 1\n"
            "    expected_outputs: 07_reviews/critic_comments.md\n"
            "    prompt: |\n"
            "      Review the smoke command plan and report critique evidence paths.\n"
            "next_turn_expects: A compact WORKER RESULT block.\n"
            "plan_file: state/sessions/leader_dispatch_smoke.md\n"
            "risk_level: low\n"
            "confidence: HIGH\n"
            "=== END LEADER DISPATCH ===\n",
            encoding="utf-8",
        )
        run([*python_module_command("leader_dispatch.py"), "validate", "--file", str(dispatch_sample)])
        run([*python_module_command("leader_dispatch.py"), "apply", "--project", destination.name, "--file", str(dispatch_sample), "--write-parallel-prompts"])
        dispatch_queue = json.loads((destination / "state" / "command_queue.json").read_text(encoding="utf-8"))
        leader_command = next(
            (
                command for command in dispatch_queue["commands"]
                if command.get("id") == "cmd_leader_smoke"
            ),
            None,
        )
        if not leader_command:
            raise RuntimeError("leader_dispatch apply did not create the worker command")
        if leader_command.get("owner_agent") != "code_agent":
            raise RuntimeError("leader_dispatch apply did not preserve worker owner")
        if leader_command.get("depends_on") != []:
            raise RuntimeError("leader_dispatch apply did not normalize depends_on=none")
        if leader_command.get("parallel_group") != "1":
            raise RuntimeError("leader_dispatch apply did not preserve parallel_group")
        if "03_experiments/exp_001/run_log.md" not in leader_command.get("expected_outputs", []):
            raise RuntimeError("leader_dispatch apply did not preserve expected_outputs")
        leader_critic_command = next(
            (
                command for command in dispatch_queue["commands"]
                if command.get("id") == "cmd_leader_smoke_critic"
            ),
            None,
        )
        if not leader_critic_command:
            raise RuntimeError("leader_dispatch apply did not create the second worker command")
        if leader_command.get("status") != "in progress" or leader_critic_command.get("status") != "in progress":
            raise RuntimeError("leader_dispatch apply --write-parallel-prompts did not mark worker commands in progress")
        if not (destination / "state" / "orchestrator_prompts" / "cmd_leader_smoke.md").is_file():
            raise RuntimeError("leader_dispatch apply --write-parallel-prompts did not write the first worker prompt")
        if not (destination / "state" / "orchestrator_prompts" / "cmd_leader_smoke_critic.md").is_file():
            raise RuntimeError("leader_dispatch apply --write-parallel-prompts did not write the second worker prompt")
        explicit_parallel_failure = run([
            *python_module_command("agent_orchestrator.py"),
            "parallel",
            "--project",
            destination.name,
            "--id",
            "cmd_leader_smoke",
        ], expect_ok=False)
        if "not safe for parallel dispatch" not in (
            explicit_parallel_failure.stdout + explicit_parallel_failure.stderr
        ):
            raise RuntimeError("explicit parallel --id failure did not explain the unsafe command.")
        parallel_manifests = sorted((destination / "state" / "orchestrator_prompts" / "parallel_batches").glob("*.json"))
        if not parallel_manifests:
            raise RuntimeError("leader_dispatch apply --write-parallel-prompts did not write a parallel batch manifest")
        parallel_manifest = json.loads(parallel_manifests[-1].read_text(encoding="utf-8"))
        manifest_command_ids = {
            command.get("id")
            for command in parallel_manifest.get("commands", [])
            if isinstance(command, dict)
        }
        if {"cmd_leader_smoke", "cmd_leader_smoke_critic"} - manifest_command_ids:
            raise RuntimeError("parallel batch manifest did not record both worker commands")
        manifest_prompts = set(parallel_manifest.get("prompts", []))
        for prompt_path in (
            "state/orchestrator_prompts/cmd_leader_smoke.md",
            "state/orchestrator_prompts/cmd_leader_smoke_critic.md",
        ):
            if prompt_path not in manifest_prompts:
                raise RuntimeError("parallel batch manifest did not record expected prompt paths")
            if not (destination / prompt_path).is_file():
                raise RuntimeError("parallel batch manifest points to a missing prompt path")
        status_parallel_result = run([
            *python_module_command("agent_orchestrator.py"),
            "status-parallel",
            "--project",
            destination.name,
            "--group",
            "1",
            "--json",
        ])
        status_parallel_payload = json.loads(status_parallel_result.stdout)
        if "open_parallel_diagnostics" not in status_parallel_payload:
            raise RuntimeError("status-parallel JSON did not expose open parallel diagnostics")
        prepared_status = status_parallel_payload.get("prepared_parallel_commands", [])
        if not prepared_status or not all(command.get("dependency_ready") for command in prepared_status):
            raise RuntimeError("status-parallel JSON did not expose ready prepared parallel commands")
        if any(command.get("unfinished_dependencies") for command in prepared_status):
            raise RuntimeError("status-parallel JSON reported unfinished dependencies for independent smoke commands")
        prepared_queue_path = destination / "state" / "command_queue.json"
        original_prepared_queue = prepared_queue_path.read_text(encoding="utf-8")
        blocked_prepared_queue = json.loads(original_prepared_queue)
        for command in blocked_prepared_queue["commands"]:
            if command.get("id") == "cmd_leader_smoke_critic":
                command["depends_on"] = ["cmd_leader_smoke"]
        prepared_queue_path.write_text(json.dumps(blocked_prepared_queue, indent=2) + "\n", encoding="utf-8")
        all_prepared_dependency_result = run([
            *python_module_command("agent_orchestrator.py"),
            "run-prepared",
            "--project",
            destination.name,
            "--all-prepared",
            "--dry-run",
        ], expect_ok=False)
        if "Prepared command dependencies are not done" not in (
            all_prepared_dependency_result.stdout + all_prepared_dependency_result.stderr
        ):
            raise RuntimeError("run-prepared --all-prepared failed for the wrong reason.")
        prepared_queue_path.write_text(original_prepared_queue, encoding="utf-8")
        run([
            *python_module_command("agent_orchestrator.py"),
            "run-prepared",
            "--project",
            destination.name,
            "--group",
            "1",
            "--dry-run",
        ])
        run([
            *python_module_command("agent_orchestrator.py"),
            "run-prepared",
            "--project",
            destination.name,
            "--group",
            "1",
            "--runner-command",
            "python -c \"import pathlib,sys; pathlib.Path(sys.argv[1]).read_text()\" {prompt_file}",
        ])
        runner_profile_command = [
            sys.executable,
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).read_text()",
            "{prompt_file}",
        ]
        workspace_profile_path.parent.mkdir(parents=True, exist_ok=True)
        workspace_profile_path.write_text(
            json.dumps(
                {
                    "agent_runners": {
                        "default_profile": "smoke_default",
                        "profiles": {
                            "smoke_default": {"command": runner_profile_command},
                            "smoke_named": {"command": runner_profile_command},
                        },
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run([
            *python_module_command("agent_orchestrator.py"),
            "run-prepared",
            "--project",
            destination.name,
            "--group",
            "1",
            "--runner-profile",
            "smoke_named",
        ])
        run([
            *python_module_command("agent_orchestrator.py"),
            "run-prepared",
            "--project",
            destination.name,
            "--group",
            "1",
        ])
        restore_workspace_profile()
        dispatch_events = [
            json.loads(line)
            for line in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not any(event.get("event") == "leader_dispatch_apply" for event in dispatch_events):
            raise RuntimeError("leader_dispatch apply did not record a lifecycle event")
        if not any(event.get("event") == "parallel_dispatch_plan" for event in dispatch_events):
            raise RuntimeError("leader_dispatch apply --write-parallel-prompts did not record a parallel dispatch plan")
        if not any(event.get("event") == "parallel_prepared_run" for event in dispatch_events):
            raise RuntimeError("agent_orchestrator run-prepared did not record a lifecycle event")
        if not any(event.get("event") == "parallel_prepared_runner_result" for event in dispatch_events):
            raise RuntimeError("agent_orchestrator run-prepared did not record a runner result event")
        runner_profile_notes = "\n".join(str(event.get("notes", "")) for event in dispatch_events)
        if "runner_profile=smoke_named" not in runner_profile_notes:
            raise RuntimeError("agent_orchestrator run-prepared did not record the explicit runner profile.")
        if "runner_profile=smoke_default" not in runner_profile_notes:
            raise RuntimeError("agent_orchestrator run-prepared did not use the default agent_runners profile.")
        finish_dry_run_result = run([
            *python_module_command("agent_orchestrator.py"),
            "finish-parallel",
            "--project",
            destination.name,
            "--group",
            "1",
            "--status",
            "done",
            "--dry-run",
        ])
        if "dry run: no command status changed" not in finish_dry_run_result.stdout:
            raise RuntimeError("agent_orchestrator finish-parallel dry run did not preserve command status.")
        run([
            *python_module_command("agent_orchestrator.py"),
            "finish-parallel",
            "--project",
            destination.name,
            "--group",
            "1",
            "--status",
            "done",
            "--result-file",
            "cmd_leader_smoke=03_experiments/exp_001/run_log.md",
            "--result-file",
            "cmd_leader_smoke_critic=07_reviews/critic_comments.md",
        ])
        finished_queue = json.loads((destination / "state" / "command_queue.json").read_text(encoding="utf-8"))
        finished_commands = {
            command.get("id"): command
            for command in finished_queue["commands"]
            if command.get("id") in {"cmd_leader_smoke", "cmd_leader_smoke_critic"}
        }
        if any(command.get("status") != "done" for command in finished_commands.values()):
            raise RuntimeError("agent_orchestrator finish-parallel did not mark prepared commands done")
        if "03_experiments/exp_001/run_log.md" not in finished_commands["cmd_leader_smoke"].get("expected_outputs", []):
            raise RuntimeError("agent_orchestrator finish-parallel did not preserve first command result file")
        if "07_reviews/critic_comments.md" not in finished_commands["cmd_leader_smoke_critic"].get("expected_outputs", []):
            raise RuntimeError("agent_orchestrator finish-parallel did not preserve second command result file")
        finish_events = [
            json.loads(line)
            for line in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not any(event.get("event") == "parallel_finish" for event in finish_events):
            raise RuntimeError("agent_orchestrator finish-parallel did not record a lifecycle event")
        worker_result_sample = destination / "state" / "sessions" / "worker_result_smoke.md"
        worker_result_sample.write_text(
            "=== WORKER RESULT ===\n"
            "status: OK\n"
            "confidence: HIGH\n"
            "summary: Smoke command completed with evidence paths.\n"
            "files_read: state/command_queue.json\n"
            "files_updated: 03_experiments/exp_001/run_log.md\n"
            "evidence: 03_experiments/exp_001/run_log.md\n"
            "blockers: none\n"
            "next: Ask result_interpreter to update claim evidence.\n"
            "=== END WORKER RESULT ===\n",
            encoding="utf-8",
        )
        run([*python_module_command("worker_result.py"), "validate", "--file", str(worker_result_sample)])
        bad_worker_result = destination / "state" / "sessions" / "worker_result_bad.md"
        bad_worker_result.write_text(
            "=== WORKER RESULT ===\n"
            "status: OK\n"
            "confidence: HIGH\n"
            "summary: Missing evidence should fail validation.\n"
            "files_read: state/command_queue.json\n"
            "files_updated: none\n"
            "evidence: none\n"
            "blockers: none\n"
            "next: none\n"
            "=== END WORKER RESULT ===\n",
            encoding="utf-8",
        )
        run([*python_module_command("worker_result.py"), "validate", "--file", str(bad_worker_result)], expect_ok=False)
        bad_dispatch = destination / "state" / "sessions" / "leader_dispatch_bad.md"
        bad_dispatch.write_text(
            "=== LEADER DISPATCH ===\n"
            "type: dispatch_workers\n",
            encoding="utf-8",
        )
        run([*python_module_command("leader_dispatch.py"), "validate", "--file", str(bad_dispatch)], expect_ok=False)
        run([
            *python_module_command("agent_status.py"),
            "start",
            "--project",
            project_name,
            "--agent",
            "director",
            "--command-id",
            "cmd_002",
            "--task",
            "Smoke-test director command.",
            "--stage",
            "planning",
            "--input",
            "state/current_state.md",
        ])
        cmd_002_action = "Run director triage after the brief is clarified and choose the next research step."
        report_text = report_readme.read_text(encoding="utf-8")
        if f"`cmd_002`: {cmd_002_action}" in report_text:
            raise RuntimeError("agent_status working state leaked into the final report README index.")

        run([
            *python_module_command("agent_status.py"),
            "finish",
            "--project",
            project_name,
            "--agent",
            "director",
            "--status",
            "done",
        ], expect_ok=False)

        run([
            *python_module_command("agent_status.py"),
            "finish",
            "--project",
            project_name,
            "--agent",
            "director",
            "--command-id",
            "cmd_002",
            "--status",
            "done",
            "--output",
            "state/current_state.md",
        ])
        report_text = report_readme.read_text(encoding="utf-8")
        if f"`cmd_002`: {cmd_002_action}" in report_text:
            raise RuntimeError("agent_status command state leaked into the final report README index.")

        run([
            *python_module_command("run_state.py"),
            "start",
            "--project",
            project_name,
            "--exp-id",
            "exp_001",
            "--owner",
            "code_agent",
            "--tmux-session",
            "ci_exp_001",
            "--slurm-job-name",
            "ci_exp_001",
            "--step",
            "Smoke-test run state.",
            "--result-path",
            "03_experiments/exp_001/results/",
            "--expected-output",
            "run_state smoke metrics",
            "--check-procedure",
            "Inspect run_state smoke metrics before marking succeeded.",
            "--display-summary",
            "Smoke-test run state tracking.",
        ])
        run([
            *python_module_command("run_state.py"),
            "finish",
            "--project",
            project_name,
            "--exp-id",
            "exp_001",
            "--status",
            "succeeded",
            "--note",
            "Smoke test finished.",
            "--judgement",
            "Run-state CLI accepted the plain-language judgement.",
            "--next-action",
            "Continue with loop summary validation.",
        ])
        status_doc = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        code_agent = next(agent for agent in status_doc["agents"] if agent["name"] == "code_agent")
        if code_agent.get("status") != "waiting" or "Smoke-test run state tracking." not in code_agent.get("current_task", ""):
            raise RuntimeError("run_state.py did not sync the owning agent lifecycle status.")
        if "run_state_finish" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("run_state.py did not append a lifecycle event.")
        run([
            *python_module_command("run_state.py"),
            "set",
            "--project",
            project_name,
            "--exp-id",
            "exp_001",
            "--status",
            "succeeded",
            "--result-path",
            "03_experiments/exp_001/missing_diagnosis_result.json",
            "--judgement",
            "Smoke fixture intentionally points at a missing result for diagnosis.",
            "--next-action",
            "Attach or ingest the result artifact before using this run as evidence.",
        ])
        run([*python_module_command("experiment_diagnosis.py"), "--project", project_name, "--write-report"])
        queue_doc = json.loads((destination / "state" / "command_queue.json").read_text(encoding="utf-8"))
        repair_command = next((command for command in queue_doc["commands"] if command.get("id") == "repair_exp_001"), None)
        if not repair_command or "Repair or resolve experiment diagnosis" not in repair_command.get("display_summary", ""):
            raise RuntimeError("experiment_diagnosis.py did not enqueue a repair action for a diagnosable run.")
        if "experiment_diagnosis" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("experiment_diagnosis.py did not append a lifecycle event.")
        run([
            *python_module_command("loop_summary.py"),
            "start",
            "--project",
            project_name,
            "--loop-id",
            "smoke_loop",
            "--goal",
            "Verify that one research loop writes file-state-visible state.",
        ])
        run([
            *python_module_command("loop_summary.py"),
            "update",
            "--project",
            project_name,
            "--summary",
            "Smoke loop is recording file-state-visible state.",
        ])
        run([
            *python_module_command("loop_summary.py"),
            "add-work",
            "--project",
            project_name,
            "--id",
            "cmd_002",
            "--action",
            "Smoke-test director command.",
            "--owner",
            "director",
            "--result",
            "Director command completed and linked to the loop summary.",
            "--output",
            "state/current_state.md",
        ])
        run([
            *python_module_command("loop_summary.py"),
            "add-result",
            "--project",
            project_name,
            "--title",
            "Dashboard loop summary recorded",
            "--status",
            "done",
            "--summary",
            "Loop goal, completed work, result, and next action were written to state/loop_summary.json.",
            "--evidence",
            "state/loop_summary.json",
        ])
        run([
            *python_module_command("loop_summary.py"),
            "add-next",
            "--project",
            project_name,
            "--action",
            "Review the dashboard loop overview.",
            "--owner",
            "director",
            "--priority",
            "medium",
            "--output",
            "state/loop_summary.json",
            "--display-summary",
            "Review the human-readable dashboard loop overview.",
            "--why-now",
            "The smoke test needs to prove that next actions can be displayed without relying on file paths.",
            "--done-when",
            "The dashboard loop overview shows the action, reason, and done condition in plain language.",
        ])
        run([
            *python_module_command("loop_summary.py"),
            "finish",
            "--project",
            project_name,
            "--status",
            "done",
            "--summary",
            "Smoke loop completed with file-state-visible work, result, and next action.",
            "--outcome",
            "Loop summary protocol works.",
        ])
        run([
            *python_module_command("loop_summary.py"),
            "validate",
            "--project",
            project_name,
            "--strict",
        ])
        loop_event_log = (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8")
        for event_type in (
            "loop_summary_start",
            "loop_summary_update",
            "loop_summary_add_work",
            "loop_summary_add_result",
            "loop_summary_add_next",
            "loop_summary_finish",
        ):
            if event_type not in loop_event_log:
                raise RuntimeError(f"loop_summary.py did not append {event_type}.")
        report_text = report_readme.read_text(encoding="utf-8")
        if "Smoke loop completed with file-state-visible work" in report_text:
            raise RuntimeError("loop_summary working state leaked into the final report README index.")
        run([
            *python_module_command("baseline_library.py"),
            "add",
            "--project",
            project_name,
            "--id",
            "bad_local_baseline",
            "--name",
            "Bad Local Baseline",
            "--source-path",
            "/" + "scratch/private_baseline/source",
        ], expect_ok=False)
        run([
            *python_module_command("baseline_library.py"),
            "add",
            "--project",
            project_name,
            "--id",
            "smoke_baseline",
            "--name",
            "Smoke Baseline",
            "--paper",
            "Smoke Test Paper",
            "--status",
            "source_found",
            "--source-path",
            "08_baselines/source_snapshots/smoke_baseline",
            "--working-dir",
            "04_code",
            "--dataset-path",
            "data/processed",
            "--owner",
            "code_agent",
        ])
        run([
            *python_module_command("baseline_library.py"),
            "update",
            "--project",
            project_name,
            "--id",
            "smoke_baseline",
            "--status",
            "runnable",
            "--run-command",
            "python -m smoke_baseline.run",
            "--result-path",
            "03_experiments/exp_001/results/smoke.json",
            "--evidence",
            "03_experiments/exp_001/run_log.md",
        ])
        (destination / "08_baselines" / "source_snapshots" / "smoke_baseline").mkdir(parents=True)
        (destination / "08_baselines" / "source_snapshots" / "smoke_baseline" / "README.md").write_text(
            "# Smoke Baseline Source\n",
            encoding="utf-8",
        )
        smoke_report = destination / "08_baselines" / "structure_reports" / "smoke_baseline.json"
        smoke_report.write_text(
            json.dumps({
                "schema_version": 1,
                "project": project_name,
                "baseline_id": "smoke_baseline",
                "source_path": "08_baselines/source_snapshots/smoke_baseline",
                "structure_score": 1,
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        run([
            *python_module_command("baseline_library.py"),
            "update",
            "--project",
            project_name,
            "--id",
            "smoke_baseline",
            "--structure-report",
            "08_baselines/structure_reports/smoke_baseline.json",
            "--structure-score",
            "1",
        ])
        run([
            *python_module_command("baseline_library.py"),
            "validate",
            "--project",
            project_name,
            "--strict",
        ])
        baseline_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        baseline_code_agent = next(agent for agent in baseline_status["agents"] if agent["name"] == "code_agent")
        baseline_outputs = set(baseline_code_agent.get("last_output_files", []))
        if (
            baseline_code_agent.get("stage") != "baseline_library_update"
            or "08_baselines/baseline_registry.json" not in baseline_outputs
            or "08_baselines/structure_reports/smoke_baseline.json" not in baseline_outputs
        ):
            raise RuntimeError("baseline_library.py did not sync baseline registry lifecycle outputs.")
        baseline_event_log = (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8")
        if "baseline_library_add" not in baseline_event_log or "baseline_library_update" not in baseline_event_log:
            raise RuntimeError("baseline_library.py did not append registry lifecycle events.")
        external_repo = create_local_baseline_repo(destination)
        manifest = destination / "08_baselines" / "smoke_baseline_manifest.csv"
        manifest.write_text(
            "id,name,paper,repo_url,dataset,metric\n"
            f"smoke_structured,Smoke Structured,Smoke Structured Paper,{external_repo},fixture,accuracy\n",
            encoding="utf-8",
        )
        run([
            *python_module_command("baseline_intake.py"),
            "ingest",
            "--project",
            project_name,
            "--manifest",
            str(manifest),
            "--clone",
            "--write-smoke",
        ])
        for relative in [
            "08_baselines/source_snapshots/smoke_structured/train.py",
            "08_baselines/structure_reports/smoke_structured.json",
            "08_baselines/structure_reports/smoke_structured.md",
            "08_baselines/code_structure_plan.md",
            "08_baselines/run_scripts/smoke_structured_smoke.py",
        ]:
            if not (destination / relative).exists():
                raise RuntimeError(f"Baseline intake did not create expected file: {relative}")
        structure_plan_text = (destination / "08_baselines" / "code_structure_plan.md").read_text(encoding="utf-8")
        for required_plan_text in (
            "Canonical Project Layout To Apply",
            "04_code/src/data/",
            "04_code/src/evaluation/",
            "04_code/tests/smoke/",
            "Which baseline conventions should be copied",
        ):
            if required_plan_text not in structure_plan_text:
                raise RuntimeError(f"Baseline code structure plan is missing canonical layout text: {required_plan_text}")
        smoke_script = destination / "08_baselines" / "run_scripts" / "smoke_structured_smoke.py"
        smoke_script.unlink()
        run([
            *python_module_command("baseline_intake.py"),
            "inspect",
            "--project",
            project_name,
            "--id",
            "smoke_structured",
            "--write-smoke",
        ])
        if not smoke_script.exists():
            raise RuntimeError("baseline_intake inspect did not recreate the dry smoke script.")
        status_doc = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        code_agent = next(agent for agent in status_doc["agents"] if agent["name"] == "code_agent")
        if code_agent.get("status") != "waiting" or (
            "Processed 1 baseline entries" not in code_agent.get("current_task", "")
            and "Inspected baseline source structure" not in code_agent.get("current_task", "")
        ):
            raise RuntimeError("baseline_intake did not sync the owning agent lifecycle status.")
        baseline_outputs = set(code_agent.get("last_output_files", []))
        for relative in [
            "08_baselines/structure_reports/smoke_structured.json",
            "08_baselines/structure_reports/smoke_structured.md",
            "08_baselines/code_structure_plan.md",
            "08_baselines/run_scripts/smoke_structured_smoke.py",
        ]:
            if relative not in baseline_outputs:
                raise RuntimeError(f"baseline_intake lifecycle outputs missed generated file: {relative}")
        baseline_event_text = (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8")
        if "baseline_ingest" not in baseline_event_text:
            raise RuntimeError("baseline_intake ingest did not append a lifecycle event.")
        if "baseline_inspect" not in baseline_event_text:
            raise RuntimeError("baseline_intake inspect did not append a lifecycle event.")
        run([sys.executable, str(destination / "08_baselines" / "run_scripts" / "smoke_structured_smoke.py")])
        run([
            *python_module_command("baseline_intake.py"),
            "discover",
            "--project",
            project_name,
            "--message-missing-repos",
        ])
        if not (destination / "08_baselines" / "repo_discovery_plan.md").exists():
            raise RuntimeError("Baseline discovery plan was not created.")
        run([*python_module_command("repo_discovery.py"), "--project", project_name, "--json"])
        discovery_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        literature_status = next(
            agent for agent in discovery_status.get("agents", [])
            if agent.get("name") == "literature_reviewer"
        )
        if (
            literature_status.get("stage") != "repo_discovery"
            or "08_baselines/repo_discovery_candidates.md" not in literature_status.get("last_output_files", [])
        ):
            raise RuntimeError("repo_discovery.py did not sync the repo discovery lifecycle status.")
        if "repo_discovery" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("repo_discovery.py did not append a lifecycle event.")
        run([*python_module_command("baseline_sandbox.py"), "--project", project_name, "--strict", "--write-policy"])
        sandbox_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        sandbox_code_agent = next(
            agent for agent in sandbox_status.get("agents", [])
            if agent.get("name") == "code_agent"
        )
        if (
            sandbox_code_agent.get("stage") != "baseline_sandbox"
            or "08_baselines/sandbox_policy.md" not in sandbox_code_agent.get("last_output_files", [])
        ):
            raise RuntimeError("baseline_sandbox.py did not sync the sandbox lifecycle status.")
        if "baseline_sandbox" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("baseline_sandbox.py did not append a lifecycle event.")
        run([*python_module_command("baseline_compare.py"), "--project", project_name, "--write", "--json"])
        run([*python_module_command("validate_project.py"), "--project", project_name, "--strict"])
        loop_plan = run([
            *python_module_command("research_loop.py"),
            "plan",
            "--project",
            project_name,
            "--json",
        ])
        loop_data = json.loads(loop_plan.stdout)
        if not loop_data["next_actions"]:
            raise RuntimeError("Research loop did not suggest any next actions for the template project.")
        run([
            *python_module_command("research_loop.py"),
            "enqueue",
            "--project",
            project_name,
            "--max-actions",
            "2",
        ])
        research_loop_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        research_loop_director = next(agent for agent in research_loop_status["agents"] if agent["name"] == "director")
        if (
            research_loop_director.get("stage") != "research_loop_enqueue"
            or "state/command_queue.json" not in research_loop_director.get("last_output_files", [])
            or "state/agent_messages.json" not in research_loop_director.get("last_output_files", [])
        ):
            raise RuntimeError("research_loop.py enqueue did not sync director lifecycle outputs.")
        if "research_loop_enqueue" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("research_loop.py enqueue did not append a lifecycle event.")
        run([
            *python_module_command("gpu_scheduler.py"),
            "add",
            "--project",
            project_name,
            "--id",
            "gpu_smoke_1",
            "--exp-id",
            "exp_001",
            "--command",
            "python -m smoke.train --config 03_experiments/exp_001/config.yaml",
            "--gpu-type",
            "a4000",
            "--priority",
            "high",
            "--result-path",
            "03_experiments/exp_001/results/gpu_smoke_1/",
            "--expected-output",
            "gpu_smoke_1 metrics",
            "--check-procedure",
            "Inspect gpu_smoke_1 metrics before marking succeeded.",
        ])
        run([
            *python_module_command("gpu_scheduler.py"),
            "add",
            "--project",
            project_name,
            "--id",
            "gpu_smoke_2",
            "--exp-id",
            "exp_001",
            "--command",
            "python -m smoke.eval --config 03_experiments/exp_001/config.yaml",
            "--gpu-type",
            "auto",
            "--priority",
            "medium",
            "--result-path",
            "03_experiments/exp_001/results/gpu_smoke_2/",
            "--expected-output",
            "gpu_smoke_2 metrics",
            "--check-procedure",
            "Inspect gpu_smoke_2 metrics before marking succeeded.",
        ])
        run([
            *python_module_command("gpu_scheduler.py"),
            "add",
            "--project",
            project_name,
            "--id",
            "gpu_smoke_3",
            "--exp-id",
            "exp_001",
            "--command",
            "python -m smoke.analyze --config 03_experiments/exp_001/config.yaml",
            "--gpu-type",
            "a4000",
            "--priority",
            "high",
            "--result-path",
            "05_results/experiment_journal.md",
            "--expected-output",
            "analysis for GPU smoke result movement",
            "--check-procedure",
            "Confirm experiment_journal.md explains the GPU smoke result.",
            "--depends-on",
            "gpu_smoke_1",
        ])
        report_text = report_readme.read_text(encoding="utf-8")
        if "GPU `gpu_smoke_1`: queued" in report_text:
            raise RuntimeError("gpu_scheduler working state leaked into the final report README index.")
        gpu_add_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        gpu_add_code_agent = next(agent for agent in gpu_add_status["agents"] if agent["name"] == "code_agent")
        if (
            gpu_add_code_agent.get("stage") != "gpu_experiment"
            or "GPU job gpu_smoke_3 is queued" not in gpu_add_code_agent.get("current_task", "")
        ):
            raise RuntimeError("GPU scheduler add did not sync queued job lifecycle status.")
        if "gpu_add" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("GPU scheduler add did not append a queued job lifecycle event.")
        gpu_list_json = run([
            *python_module_command("gpu_scheduler.py"),
            "list",
            "--project",
            project_name,
            "--json",
        ])
        gpu_list_payload = json.loads(gpu_list_json.stdout)
        gpu_list_job = next((job for job in gpu_list_payload.get("jobs", []) if job.get("id") == "gpu_smoke_3"), None)
        if not gpu_list_job or "dependency_ready" not in gpu_list_job:
            raise RuntimeError("gpu_scheduler list --json did not expose dependency readiness.")
        if "unfinished_dependencies" not in gpu_list_job:
            raise RuntimeError("gpu_scheduler list --json did not expose unfinished dependencies.")
        squeue_mock = destination / "state" / "squeue_mock.txt"
        squeue_mock.write_text("123|existing|RUNNING|gpu:2|1|node05\n", encoding="utf-8")
        scontrol_mock = destination / "state" / "scontrol_mock.txt"
        scontrol_mock.write_text(
            "NodeName=node05 State=IDLE CfgTRES=cpu=64,mem=1,gres/gpu=4 AllocTRES=cpu=0,mem=0,gres/gpu=1\n"
            "NodeName=node04 State=MIXED CfgTRES=cpu=64,mem=1,gres/gpu=4 AllocTRES=cpu=8,mem=1,gres/gpu=2\n"
            "NodeName=node06 State=DRAIN CfgTRES=cpu=64,mem=1,gres/gpu=4 AllocTRES=cpu=0,mem=0,gres/gpu=0\n",
            encoding="utf-8",
        )
        plan = run([
            *python_module_command("gpu_scheduler.py"),
            "plan",
            "--project",
            project_name,
            "--squeue-output",
            str(squeue_mock),
            "--scontrol-output",
            str(scontrol_mock),
            "--max-user-gpus",
            "8",
            "--json",
        ])
        planned = json.loads(plan.stdout)
        if [job["id"] for job in planned["planned_jobs"]] != ["gpu_smoke_1", "gpu_smoke_2"]:
            raise RuntimeError(f"Unexpected GPU plan: {plan.stdout}")
        diagnostics = planned.get("plan_diagnostics", [])
        smoke_3_diagnostic = next((item for item in diagnostics if item.get("id") == "gpu_smoke_3"), None)
        if not smoke_3_diagnostic or smoke_3_diagnostic.get("selected"):
            raise RuntimeError("GPU plan diagnostics did not report the dependent job as excluded.")
        if "unfinished_dependencies:gpu_smoke_1" not in ",".join(smoke_3_diagnostic.get("reasons") or []):
            raise RuntimeError("GPU plan diagnostics did not explain the unfinished dependency.")
        explicit_gpu_dispatch_failure = run([
            *python_module_command("gpu_scheduler.py"),
            "dispatch",
            "--project",
            project_name,
            "--squeue-output",
            str(squeue_mock),
            "--scontrol-output",
            str(scontrol_mock),
            "--max-user-gpus",
            "8",
            "--ids",
            "gpu_smoke_3",
        ], expect_ok=False)
        if "unfinished_dependencies:gpu_smoke_1" not in (
            explicit_gpu_dispatch_failure.stdout + explicit_gpu_dispatch_failure.stderr
        ):
            raise RuntimeError("GPU dispatch --ids failure did not explain why the job was not dispatchable.")
        explicit_gpu_max_parallel_failure = run([
            *python_module_command("gpu_scheduler.py"),
            "dispatch",
            "--project",
            project_name,
            "--squeue-output",
            str(squeue_mock),
            "--scontrol-output",
            str(scontrol_mock),
            "--max-user-gpus",
            "8",
            "--ids",
            "gpu_smoke_1,gpu_smoke_2",
            "--max-parallel",
            "1",
        ], expect_ok=False)
        if "Explicit GPU job count" not in (
            explicit_gpu_max_parallel_failure.stdout + explicit_gpu_max_parallel_failure.stderr
        ):
            raise RuntimeError("GPU dispatch --ids max-parallel failure did not explain the explicit cap mismatch.")
        dry_launch = run([
            *python_module_command("gpu_scheduler.py"),
            "dispatch",
            "--project",
            project_name,
            "--squeue-output",
            str(squeue_mock),
            "--scontrol-output",
            str(scontrol_mock),
            "--max-user-gpus",
            "8",
        ])
        if "sbatch --parsable" not in dry_launch.stdout:
            raise RuntimeError("GPU scheduler dry-run dispatch did not print sbatch commands.")
        if "diagnostic\tgpu_smoke_3\texcluded\tunfinished_dependencies:gpu_smoke_1" not in dry_launch.stdout:
            raise RuntimeError("GPU scheduler dry-run dispatch did not print excluded job diagnostics.")
        dry_launch_json = run([
            *python_module_command("gpu_scheduler.py"),
            "dispatch",
            "--project",
            project_name,
            "--squeue-output",
            str(squeue_mock),
            "--scontrol-output",
            str(scontrol_mock),
            "--max-user-gpus",
            "8",
            "--json",
        ])
        dry_launch_payload = json.loads(dry_launch_json.stdout)
        if [job["id"] for job in dry_launch_payload.get("selected_jobs", [])] != ["gpu_smoke_1", "gpu_smoke_2"]:
            raise RuntimeError("GPU scheduler dispatch --json did not expose selected jobs.")
        if "plan_diagnostics" not in dry_launch_payload or "launch_commands" not in dry_launch_payload:
            raise RuntimeError("GPU scheduler dispatch --json did not expose diagnostics and launch commands.")
        run([
            *python_module_command("gpu_scheduler.py"),
            "launch",
            "--project",
            project_name,
            "--squeue-output",
            str(squeue_mock),
            "--scontrol-output",
            str(scontrol_mock),
            "--max-user-gpus",
            "8",
        ], expect_ok=False)
        single_launch = run([
            *python_module_command("gpu_scheduler.py"),
            "launch",
            "--project",
            project_name,
            "--id",
            "gpu_smoke_1",
            "--squeue-output",
            str(squeue_mock),
            "--scontrol-output",
            str(scontrol_mock),
            "--max-user-gpus",
            "8",
        ])
        if (
            "--job-name=gpu_smoke_1_a4000" not in single_launch.stdout
            or "--job-name=gpu_smoke_2_gpu" in single_launch.stdout
            or single_launch.stdout.count("sbatch --parsable") != 1
        ):
            raise RuntimeError("GPU scheduler launch --id did not constrain launch output to one job.")
        fake_bin = destination / "state" / "fake_bin"
        fake_bin.mkdir()
        fake_sbatch = fake_bin / ("sbatch.cmd" if os.name == "nt" else "sbatch")
        fake_sbatch.write_text(
            "@echo off\necho 424242\n" if os.name == "nt"
            else "#!/usr/bin/env bash\nprintf '424242\\n'\n", encoding="utf-8",
        )
        fake_sbatch.chmod(0o755)
        execute_env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"}
        launched = run([
            *python_module_command("gpu_scheduler.py"),
            "dispatch",
            "--project",
            project_name,
            "--squeue-output",
            str(squeue_mock),
            "--scontrol-output",
            str(scontrol_mock),
            "--max-user-gpus",
            "8",
            "--allow-disabled-profile",
            "--execute",
        ], env=execute_env)
        if "launched: gpu_smoke_1" not in launched.stdout or "launched: gpu_smoke_2" not in launched.stdout:
            raise RuntimeError(f"GPU scheduler dispatch execute path did not launch planned jobs: {launched.stdout}")
        gpu_queue = json.loads((destination / "state" / "gpu_experiment_queue.json").read_text(encoding="utf-8"))
        running_jobs = {job["id"]: job for job in gpu_queue["jobs"] if job["id"] in {"gpu_smoke_1", "gpu_smoke_2"}}
        if any(job.get("launcher") != "sbatch" or job.get("slurm_job_id") != "424242" for job in running_jobs.values()):
            raise RuntimeError("GPU scheduler execute path did not record sbatch launcher/job id.")
        status_doc = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        code_agent = next(agent for agent in status_doc["agents"] if agent["name"] == "code_agent")
        if code_agent.get("status") != "running" or "GPU job gpu_smoke_2 is running" not in code_agent.get("current_task", ""):
            raise RuntimeError("GPU scheduler launch did not sync the owning agent status.")
        event_log = (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8")
        if "gpu_dispatch_plan" not in event_log:
            raise RuntimeError("GPU scheduler dispatch execute path did not append a dispatch-plan lifecycle event.")
        if "gpu_launch" not in event_log:
            raise RuntimeError("GPU scheduler launch did not append a GPU lifecycle event.")
        refresh_running_payload = json.loads(run([
            *python_module_command("gpu_scheduler.py"),
            "refresh",
            "--project",
            project_name,
            "--squeue-output",
            str(squeue_mock),
            "--json",
        ]).stdout)
        if "diagnostics" not in refresh_running_payload:
            raise RuntimeError("gpu_scheduler refresh --json did not expose diagnostics.")
        refresh_done_mock = destination / "state" / "squeue_refresh_done_mock.txt"
        refresh_done_mock.write_text(
            "424242|gpu_smoke_1_a4000|COMPLETED|gpu:1|1|node05\n",
            encoding="utf-8",
        )
        refresh_done_payload = json.loads(run([
            *python_module_command("gpu_scheduler.py"),
            "refresh",
            "--project",
            project_name,
            "--squeue-output",
            str(refresh_done_mock),
            "--write",
            "--json",
        ]).stdout)
        refreshed_ids = {job.get("id") for job in refresh_done_payload.get("updated_jobs", [])}
        if {"gpu_smoke_1", "gpu_smoke_2"} - refreshed_ids:
            raise RuntimeError(f"gpu_scheduler refresh --write did not update running jobs: {refresh_done_payload}")
        refreshed_queue = json.loads((destination / "state" / "gpu_experiment_queue.json").read_text(encoding="utf-8"))
        refreshed_jobs = {
            job.get("id"): job
            for job in refreshed_queue.get("jobs", [])
            if job.get("id") in {"gpu_smoke_1", "gpu_smoke_2"}
        }
        if any(job.get("status") != "succeeded" for job in refreshed_jobs.values()):
            raise RuntimeError("gpu_scheduler refresh --write did not persist terminal GPU statuses.")
        refreshed_run_state = json.loads((destination / "03_experiments" / "exp_001" / "run_state.json").read_text(encoding="utf-8"))
        if not any(row.get("event") == "gpu_refresh:succeeded" for row in refreshed_run_state.get("history", [])):
            raise RuntimeError("gpu_scheduler refresh --write did not sync experiment run_state history.")
        for job_id in ("gpu_smoke_1", "gpu_smoke_2"):
            run([
                *python_module_command("gpu_scheduler.py"),
                "update",
                "--project",
                project_name,
                "--id",
                job_id,
                "--status",
                "succeeded",
                "--note",
                "Smoke GPU job completed.",
                "--result-path",
                "03_experiments/exp_001/results/",
            ])
        dependency_plan = run([
            *python_module_command("gpu_scheduler.py"),
            "plan",
            "--project",
            project_name,
            "--squeue-output",
            str(squeue_mock),
            "--scontrol-output",
            str(scontrol_mock),
            "--max-user-gpus",
            "8",
            "--json",
        ])
        dependency_planned = json.loads(dependency_plan.stdout)
        if [job["id"] for job in dependency_planned["planned_jobs"]] != ["gpu_smoke_3"]:
            raise RuntimeError(f"GPU scheduler did not unlock dependency-gated job after success: {dependency_plan.stdout}")
        synced_run_state = json.loads((destination / "03_experiments" / "exp_001" / "run_state.json").read_text(encoding="utf-8"))
        if synced_run_state.get("status") != "succeeded" or not any(
            row.get("event") == "gpu_update:succeeded" for row in synced_run_state.get("history", [])
        ):
            raise RuntimeError("GPU scheduler update did not sync experiment run_state.json.")
        if synced_run_state.get("expected_output") != "gpu_smoke_2 metrics" or "Inspect gpu_smoke_2 metrics" not in synced_run_state.get("check_procedure", ""):
            raise RuntimeError("GPU scheduler update did not sync expected output and check procedure.")
        if (
            "Analyze why the experiment result" not in synced_run_state.get("next_action", "")
            or "05_results/experiment_journal.md" not in synced_run_state.get("next_action", "")
        ):
            raise RuntimeError("GPU scheduler success update did not set an analysis follow-up next_action.")
        status_doc = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        code_agent = next(agent for agent in status_doc["agents"] if agent["name"] == "code_agent")
        if code_agent.get("status") != "running" or "Smoke GPU job completed." not in code_agent.get("notes", ""):
            raise RuntimeError("GPU scheduler update did not preserve owning agent status while dependent work remains queued.")
        stale_active_status, stale_active_note = classify_job(
            destination,
            {
                "id": "gpu_smoke_active_stale",
                "status": "running",
                "slurm_job_id": "424242",
                "slurm_job_name": "gpu_smoke_active_stale",
                "updated_at": "2000-01-01T00:00:00+00:00",
            },
            squeue_available=True,
            active_job_ids={"424242"},
            active_job_names={"gpu_smoke_active_stale"},
            stale_after=1,
            assume_missing_finished=False,
        )
        if stale_active_status is not None or stale_active_note != "still running in scheduler":
            raise RuntimeError("GPU monitor blocked a stale-heartbeat job that is still visible in squeue.")
        run([*python_module_command("gpu_monitor.py"), "--project", project_name, "--squeue-output", str(squeue_mock), "--json"])
        run([*python_module_command("validate_project.py"), "--project", project_name, "--strict"])
        run([
            *python_module_command("review_forms.py"),
            "validate",
            "--strict",
        ])
        run([
            *python_module_command("review_forms.py"),
            "create-review",
            "--project",
            project_name,
            "--form-id",
            "venue_year_template",
            "--review-id",
            "smoke_form_review",
            "--paper",
            "06_writing/draft.md",
        ])
        review_form_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        venue_reviewer_status = next(
            agent for agent in review_form_status.get("agents", [])
            if agent.get("name") == "venue_reviewer"
        )
        if (
            venue_reviewer_status.get("stage") != "review_forms_create_review"
            or "07_reviews/form_reviews/smoke_form_review.md" not in venue_reviewer_status.get("last_output_files", [])
        ):
            raise RuntimeError("review_forms.py did not sync the form-review lifecycle status.")
        if "review_forms_create_review" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("review_forms.py did not append a lifecycle event.")
        run([*python_module_command("review_to_revision.py"), "--project", project_name, "--json"])
        if "review_to_revision" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("review_to_revision.py did not append a lifecycle event.")
        artifact_payload = json.loads(run([
            *python_module_command("artifact_packager.py"),
            "--project",
            project_name,
            "--dry-run",
            "--json",
        ]).stdout)
        artifact_files = set(artifact_payload.get("files", []))
        for required_artifact in [
            "03_experiments/data_roots.md",
            "05_results/experiment_results.csv",
            "05_results/experiment_journal.md",
            "05_results/experiment_journal.csv",
            "06_writing/terminology.md",
        ]:
            if required_artifact not in artifact_files:
                raise RuntimeError(f"artifact_packager.py omitted required artifact: {required_artifact}")
        journal_csv_path = destination / "05_results" / "experiment_journal.csv"
        original_journal_csv = journal_csv_path.read_text(encoding="utf-8")
        journal_csv_path.unlink()
        run([*python_module_command("artifact_packager.py"), "--project", project_name, "--dry-run"], expect_ok=False)
        run([*python_module_command("artifact_packager.py"), "--project", project_name, "--dry-run", "--allow-incomplete"])
        journal_csv_path.write_text(original_journal_csv, encoding="utf-8")
        run([*python_module_command("artifact_packager.py"), "--project", project_name, "--tar"])
        artifact_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        writing_agent = next(
            agent for agent in artifact_status.get("agents", [])
            if agent.get("name") == "writing_agent"
        )
        if (
            writing_agent.get("stage") != "artifact_packager"
            or "09_report/artifact_manifest.json" not in writing_agent.get("last_output_files", [])
            or f"09_report/{project_name}_artifact.tar.gz" not in writing_agent.get("last_output_files", [])
        ):
            raise RuntimeError("artifact_packager.py did not sync packaging lifecycle outputs.")
        if "artifact_packager" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("artifact_packager.py did not append a lifecycle event.")
        journal_path = destination / "05_results" / "experiment_journal.md"
        original_journal = journal_path.read_text(encoding="utf-8")
        journal_path.write_text(original_journal + "\nprivate path: " + "/" + "scratch/private_dataset/root\n", encoding="utf-8")
        run([*python_module_command("artifact_packager.py"), "--project", project_name, "--dry-run"], expect_ok=False)
        run([*python_module_command("artifact_packager.py"), "--project", project_name, "--dry-run", "--allow-local-paths"])
        journal_path.write_text(original_journal, encoding="utf-8")
        run([
            *python_module_command("project_intake.py"),
            "apply",
            "--project",
            project_name,
            "--research-question",
            "Should local absolute dataset paths be rejected?",
            "--motivation",
            "Private machine paths should not enter tracked files.",
            "--contribution",
            "The intake CLI rejects local absolute dataset source paths.",
            "--dataset-source",
            "/" + "scratch/private_dataset/root",
        ], expect_ok=False)
        run([
            *python_module_command("project_intake.py"),
            "apply",
            "--project",
            project_name,
            "--research-question",
            "Can the smoke harness preserve claim evidence from intake through preregistration and audit?",
            "--motivation",
            "Researchers need one reproducible path from an initial idea to auditable claim evidence.",
            "--contribution",
            "A file-based workflow can keep research claims, preregistration, and audit status synchronized.",
            "--claim-id",
            "claim_feature_smoke",
            "--target-venue",
            "workflow smoke test",
            "--compute-budget",
            "CPU-only fixture",
            "--dataset-id",
            "fixture_workflow",
            "--dataset-name",
            "Fixture Workflow Dataset",
            "--dataset-source",
            "fixture://workflow",
            "--dataset-split",
            "smoke",
            "--metric-id",
            "workflow_accuracy",
            "--metric-name",
            "Workflow Accuracy",
            "--metric-direction",
            "higher",
            "--metric-definition",
            "Correct workflow checks divided by total checks.",
            "--force",
        ])
        data_roots_text = (destination / "03_experiments" / "data_roots.md").read_text(encoding="utf-8")
        if "fixture_workflow" not in data_roots_text or "fixture://workflow" not in data_roots_text:
            raise RuntimeError("project_intake.py did not seed data_roots.md from dataset intake.")
        queue_doc = json.loads((destination / "state" / "command_queue.json").read_text(encoding="utf-8"))
        cmd_001 = next(command for command in queue_doc["commands"] if command["id"] == "cmd_001")
        cmd_002 = next(command for command in queue_doc["commands"] if command["id"] == "cmd_002")
        if cmd_001.get("status") != "done" or cmd_002.get("status") in {"blocked", "deferred"}:
            raise RuntimeError("project_intake.py did not advance the initial command queue after seeding the brief.")
        current_state_text = (destination / "state" / "current_state.md").read_text(encoding="utf-8")
        memory_text = (destination / "state" / "agent_memory.md").read_text(encoding="utf-8")
        handoff_text = (destination / "HANDOFF.md").read_text(encoding="utf-8")
        if (
            "Project Intake Applied" not in current_state_text
            or "Do not ask the user to repeat" not in memory_text
            or "Latest Intake" not in handoff_text
        ):
            raise RuntimeError("project_intake.py did not persist intake state for future agents.")
        agent_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        motivation_status = next(
            agent for agent in agent_status.get("agents", [])
            if agent.get("name") == "motivation_planner"
        )
        if (
            motivation_status.get("stage") != "project_intake"
            or "02_planning/intake_summary.md" not in motivation_status.get("last_output_files", [])
        ):
            raise RuntimeError("project_intake.py did not sync the intake lifecycle status.")
        if "project_intake" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("project_intake.py did not append a lifecycle event.")
        resume = run([
            *python_module_command("project_resume.py"),
            "--project",
            project_name,
        ])
        if "Project Resume" not in resume.stdout or "Continuation Prompt" not in resume.stdout:
            raise RuntimeError("project_resume.py did not print the expected markdown summary.")
        resume_json = json.loads(run([
            *python_module_command("project_resume.py"),
            "--project",
            project_name,
            "--json",
        ]).stdout)
        if resume_json.get("project") != project_name or "continuation_prompt" not in resume_json:
            raise RuntimeError("project_resume.py JSON output is missing project or continuation prompt.")
        run([
            *python_module_command("preregistration_helper.py"),
            "write",
            "--project",
            project_name,
            "--exp-id",
            "exp_001",
            "--claim-id",
            "claim_feature_smoke",
            "--claim",
            "A file-based workflow can keep research claims, preregistration, and audit status synchronized.",
            "--expectation",
            "The generated board and audit identify the claim and required evidence.",
            "--support",
            "The board contains the claim row and the preregistration audit passes.",
            "--falsify",
            "The board omits the claim or preregistration still contains placeholders.",
            "--success",
            "Claim row is present in the board and preregistration passes strict audit.",
            "--failure",
            "Generated workflow files are missing or still contain blank starter rows.",
            "--baseline",
            "No external baseline required for workflow smoke.",
            "--metric",
            "workflow_accuracy",
            "--metric-direction",
            "higher",
            "--dataset",
            "fixture_workflow",
            "--split",
            "smoke",
            "--smoke-command",
            "python -m scripts.commands.experiments.preregistration_helper audit --project "
            f"{project_name} --exp-id exp_001 --strict",
            "--smoke-expected-output",
            "Strict preregistration audit exits successfully.",
            "--smoke-check-procedure",
            "Run the audit command and confirm no warnings are printed.",
            "--analysis",
            "Check generated files and strict preregistration audit output.",
            "--decision-rule",
            "Keep claim_feature_smoke untested until a real experiment result is ingested.",
        ])
        prereg_text = (destination / "03_experiments" / "exp_001" / "preregistration.md").read_text(encoding="utf-8")
        if "05_results/experiment_results.csv" not in prereg_text:
            raise RuntimeError("preregistration_helper.py did not point success evidence at the working result table.")
        prereg_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        experiment_designer_status = next(
            agent for agent in prereg_status.get("agents", [])
            if agent.get("name") == "experiment_designer"
        )
        if (
            experiment_designer_status.get("stage") != "preregistration_helper"
            or "03_experiments/exp_001/preregistration.md" not in experiment_designer_status.get("last_output_files", [])
        ):
            raise RuntimeError("preregistration_helper.py did not sync the preregistration lifecycle status.")
        if "preregistration_helper" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("preregistration_helper.py did not append a lifecycle event.")
        run([
            *python_module_command("preregistration_helper.py"),
            "audit",
            "--project",
            project_name,
            "--exp-id",
            "exp_001",
            "--strict",
        ])
        run([
            *python_module_command("claim_evidence_board.py"),
            "build",
            "--project",
            project_name,
            "--write",
        ])
        claim_board_text = (destination / "05_results" / "claim_evidence_board.md").read_text(encoding="utf-8")
        if "Working Result Preview" not in claim_board_text or "accuracy=0.9" not in claim_board_text:
            raise RuntimeError("claim_evidence_board.py did not render working result preview rows.")
        claim_board_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        result_interpreter_status = next(
            agent for agent in claim_board_status.get("agents", [])
            if agent.get("name") == "result_interpreter"
        )
        if (
            result_interpreter_status.get("stage") != "claim_evidence_board"
            or "05_results/claim_evidence_board.md" not in result_interpreter_status.get("last_output_files", [])
        ):
            raise RuntimeError("claim_evidence_board.py did not sync the claim-board lifecycle status.")
        if "09_report/results/claim_evidence_board.csv" in result_interpreter_status.get("last_output_files", []):
            raise RuntimeError("claim_evidence_board.py working write leaked a final report output.")
        if "claim_evidence_board" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("claim_evidence_board.py did not append a lifecycle event.")
        run([
            *python_module_command("claim_evidence_board.py"),
            "build",
            "--project",
            project_name,
            "--write",
            "--final-export",
        ])
        final_claim_board_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        final_result_interpreter_status = next(
            agent for agent in final_claim_board_status.get("agents", [])
            if agent.get("name") == "result_interpreter"
        )
        if "09_report/results/claim_evidence_board.csv" not in final_result_interpreter_status.get("last_output_files", []):
            raise RuntimeError("claim_evidence_board.py final export did not sync the report-facing output.")
        run([
            *python_module_command("research_audit.py"),
            "--project",
            project_name,
            "--write-report",
        ])
        research_audit_status = json.loads((destination / "state" / "agent_status.json").read_text(encoding="utf-8"))
        research_audit_director = next(
            agent for agent in research_audit_status.get("agents", [])
            if agent.get("name") == "director"
        )
        if (
            research_audit_director.get("stage") != "research_audit"
            or "07_reviews/research_audit.md" not in research_audit_director.get("last_output_files", [])
        ):
            raise RuntimeError("research_audit.py did not sync the research audit lifecycle status.")
        if "research_audit" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("research_audit.py did not append a lifecycle event.")
        if args.include_dashboard:
            refresh_check = json.loads(run([
                *python_module_command("dashboard_refresh.py"),
                "--project",
                project_name,
                "--check",
            ]).stdout)
            if not refresh_check.get("ok") or refresh_check.get("mode") != "check":
                raise RuntimeError(f"dashboard refresh check mode failed: {refresh_check}")
            refresh_write = json.loads(run([
                *python_module_command("dashboard_refresh.py"),
                "--project",
                project_name,
            ]).stdout)
            if (
                not refresh_write.get("ok")
                or refresh_write.get("refreshed", {}).get("data_sources", {}).get("required_missing")
            ):
                raise RuntimeError(f"dashboard refresh write mode failed: {refresh_write}")
            if "09_report/README.md" in refresh_write.get("written_files", []):
                raise RuntimeError("dashboard refresh default write leaked into the final report index.")
            refresh_final_export = json.loads(run([
                *python_module_command("dashboard_refresh.py"),
                "--project",
                project_name,
                "--final-export",
            ]).stdout)
            if (
                not refresh_final_export.get("ok")
                or "09_report/README.md" not in refresh_final_export.get("written_files", [])
                or "09_report/results/claim_evidence_board.csv" not in refresh_final_export.get("written_files", [])
                or refresh_final_export.get("refreshed", {}).get("data_sources", {}).get("required_missing")
            ):
                raise RuntimeError(f"dashboard refresh final export mode failed: {refresh_final_export}")
        closeout_check = json.loads(run([
            *python_module_command("project_closeout.py"),
            "--project",
            project_name,
            "--json",
        ]).stdout)
        if closeout_check.get("project") != project_name or "recommended_skills" not in closeout_check:
            raise RuntimeError(f"project closeout JSON failed: {closeout_check}")
        run([
            *python_module_command("project_closeout.py"),
            "--project",
            project_name,
            "--write-report",
        ])
        if "project_closeout" not in (destination / "state" / "agent_events.jsonl").read_text(encoding="utf-8"):
            raise RuntimeError("project_closeout.py did not append a lifecycle event.")
        for relative in [
            "02_planning/intake_summary.md",
            "05_results/claim_evidence_board.md",
            "07_reviews/research_audit.md",
            "07_reviews/project_closeout_audit.md",
            "09_report/results/claim_evidence_board.csv",
            "09_report/results/research_audit.csv",
        ]:
            if not (destination / relative).exists():
                raise RuntimeError(f"Researcher workflow did not create expected file: {relative}")
        report_text = report_readme.read_text(encoding="utf-8")
        if "claim_evidence_board.csv" not in report_text or "research_audit.csv" not in report_text:
            raise RuntimeError("Final report outputs were not indexed in 09_report/README.md.")
        run([*python_module_command("validate_project.py"), "--project", project_name, "--strict"])
        workflow_audit = json.loads(run([*python_module_command("workflow_audit.py"), "--json"]).stdout)
        if not workflow_audit.get("ok"):
            raise RuntimeError(f"workflow audit failed: {workflow_audit}")
        print("harness smoke test OK")
        return 0
    finally:
        restore_workspace_profile()
        if destination.exists() and not args.keep_project:
            remove_smoke_tree(destination)
        if import_destination.exists() and not args.keep_project:
            remove_smoke_tree(import_destination)
        if import_source.exists() and not args.keep_project:
            remove_smoke_tree(import_source)


if __name__ == "__main__":
    raise SystemExit(main())
